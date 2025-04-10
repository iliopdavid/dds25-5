import base64
import logging
import os
import atexit
import uuid
import redis
import requests

from msgspec import msgpack, Struct
from flask import Flask, jsonify, abort, Response

DB_ERROR_STR = "DB error"
REQ_ERROR_STR = "Requests error"

GATEWAY_URL = os.environ["GATEWAY_URL"]

LOG_DIR = "logging"
LOG_FILENAME = "order_log.txt"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILENAME)

app = Flask("order-service")
app.logger.setLevel(logging.INFO)

db = redis.Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(os.environ["REDIS_DB"]),
)


# Helper functions and classes
def recover_from_logs():
    with open(LOG_PATH, "r") as file:
        for line in file:
            info = line.split(", ")
            db.set(info[0], base64.b64decode(info[1]))


def on_start():
    if os.path.exists(LOG_PATH):
        recover_from_logs()
    else:
        try:
            with open(LOG_PATH, "x"):
                pass
            app.logger.debug(f"Log file created at: {LOG_PATH}")
        except FileExistsError:
            return abort(400, DB_ERROR_STR)


def close_db_connection():
    db.close()


atexit.register(close_db_connection)


class OrderValue(Struct):
    paid: bool
    items: dict[str, int]
    user_id: str
    total_cost: int


def get_order_from_db(order_id: str) -> OrderValue | None:
    try:
        entry: bytes = db.get(order_id)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    entry: OrderValue | None = msgpack.decode(entry, type=OrderValue) if entry else None
    if entry is None:
        abort(400, f"Order: {order_id} not found!")
    return entry


def log(kv_pairs: dict):
    with open(LOG_PATH, "a") as log_file:
        for k, v in kv_pairs.items():
            log_file.write(k + ", " + base64.b64encode(v).decode("utf-8") + "\n")


def send_post_request(url: str):
    try:
        response = requests.post(url)
    except requests.exceptions.RequestException:
        abort(400, REQ_ERROR_STR)
    else:
        return response


def send_get_request(url: str):
    try:
        response = requests.get(url)
    except requests.exceptions.RequestException:
        abort(400, REQ_ERROR_STR)
    else:
        return response


# Route handlers
@app.post("/create/<user_id>")
def create_order(user_id: str):
    key = str(uuid.uuid4())
    value = msgpack.encode(
        OrderValue(
            paid=False,
            items={},
            user_id=user_id,
            total_cost=0,
        )
    )
    try:
        log({key: value})
        db.set(key, value)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({"order_id": key})


@app.post("/batch_init/<n>/<n_items>/<n_users>/<item_price>")
def batch_init_users(n: int, n_items: int, n_users: int, item_price: int):
    import random

    n = int(n)
    n_items = int(n_items)
    n_users = int(n_users)
    item_price = int(item_price)

    def generate_entry() -> OrderValue:
        user_id = random.randint(0, n_users - 1)
        item1_id = random.randint(0, n_items - 1)
        item2_id = random.randint(0, n_items - 1)
        value = OrderValue(
            paid=False,
            items={f"{item1_id}": 1, f"{item2_id}": 1},
            user_id=f"{user_id}",
            total_cost=2 * item_price,
        )
        return value

    kv_pairs: dict[str, bytes] = {
        f"{i}": msgpack.encode(generate_entry()) for i in range(n)
    }
    try:
        log(kv_pairs)
        db.mset(kv_pairs)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for orders successful"})


@app.get("/find/<order_id>")
def find_order(order_id: str):
    order_entry: OrderValue = get_order_from_db(order_id)
    return jsonify(
        {
            "order_id": order_id,
            "paid": order_entry.paid,
            "items": list(order_entry.items.keys()),
            "user_id": order_entry.user_id,
            "total_cost": order_entry.total_cost,
        }
    )


@app.post("/addItem/<order_id>/<item_id>/<quantity>")
def add_item(order_id: str, item_id: str, quantity: int):
    order_entry: OrderValue = get_order_from_db(order_id)
    item_reply = send_get_request(f"{GATEWAY_URL}/stock/find/{item_id}")
    if item_reply.status_code != 200:
        # Request failed because item does not exist
        abort(400, f"Item: {item_id} does not exist!")
    item_json: dict = item_reply.json()
    if item_id in order_entry.items:
        order_entry.items[item_id] += int(quantity)
    else:
        order_entry.items[item_id] = int(quantity)
    order_entry.total_cost += int(quantity) * item_json["price"]
    value = msgpack.encode(order_entry)
    try:
        log({order_id: value})
        db.set(order_id, value)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return Response(
        f"Item: {item_id} added to: {order_id} price updated to: {order_entry.total_cost}",
        status=200,
    )


@app.post("/checkout/<order_id>")
def checkout(order_id: str):
    try:
        order_entry: OrderValue = get_order_from_db(order_id)
        # Access the worker's producer pool via the worker
        # This relies on the worker attribute set in the gunicorn config
        app.producer.send_checkout_called(
            order_id, order_entry.user_id, order_entry.total_cost, order_entry.items
        )

        return jsonify({"message": "Order checkout initiated"}), 200
    except ConnectionError as e:
        app.logger.error(
            f"Checkout initiation failed for order {order_id}: Could not publish event - {e}"
        )
        return (
            jsonify(
                {"error": "Failed to initiate checkout process due to messaging issue."}
            ),
            503,
        )
    except Exception as e:
        app.logger.error(f"Checkout initiation failed for order {order_id}: {e}")
        return jsonify({"error": "Internal server error during checkout."}), 500


def rollback_stock(removed_items: dict[str, int]):
    for item_id, quantity in removed_items.items():
        send_post_request(f"{GATEWAY_URL}/stock/add/{item_id}/{quantity}")


# Initialize the app if running directly
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    # When running with gunicorn
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
