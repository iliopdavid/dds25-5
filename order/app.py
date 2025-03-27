import base64
import logging
import os
import atexit
import random
import uuid
import time
import redis
import requests

from msgspec import msgpack, Struct
from flask import Flask, jsonify, abort, Response

DB_ERROR_STR = "DB error"
REQ_ERROR_STR = "Requests error"

GATEWAY_URL = os.environ['GATEWAY_URL']
STOCK_URL = os.environ['STOCK_URL']
PAYMENT_URL = os.environ['PAYMENT_URL']

LOG_DIR = "logging"
LOG_FILENAME = "order_log.txt"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILENAME)


def recover_from_logs():
    with open(LOG_PATH, 'r') as file:
        for line in file:
            info = line.split(", ")
            db.set(info[0], base64.b64decode(info[1]))


def on_start():
    if os.path.exists(LOG_PATH):
        recover_from_logs()
    else:
        try:
            with open(LOG_PATH, 'x'):
                pass
            app.logger.debug(f"Log file created at: {LOG_PATH}")
        except FileExistsError:
            return abort(400, DB_ERROR_STR)


app = Flask("order-service")

db: redis.Redis = redis.Redis(host=os.environ['REDIS_HOST'],
                              port=int(os.environ['REDIS_PORT']),
                              password=os.environ['REDIS_PASSWORD'],
                              db=int(os.environ['REDIS_DB']))


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
        # get serialized data
        entry: bytes = db.get(order_id)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    # deserialize data if it exists else return null
    entry: OrderValue | None = msgpack.decode(entry, type=OrderValue) if entry else None
    if entry is None:
        # if order does not exist in the database; abort
        abort(400, f"Order: {order_id} not found!")
    return entry


def log(kv_pairs: dict):
    with open(LOG_PATH, 'a') as log_file:
        for (k, v) in kv_pairs.items():
            log_file.write(k + ", " + base64.b64encode(v).decode('utf-8') + "\n")


@app.post('/create/<user_id>')
def create_order(user_id: str):
    key = str(uuid.uuid4())
    value = msgpack.encode(OrderValue(paid=False, items={}, user_id=user_id, total_cost=0))
    try:
        log({key: value})
        db.set(key, value)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({'order_id': key})


@app.post('/batch_init/<n>/<n_items>/<n_users>/<item_price>')
def batch_init_users(n: int, n_items: int, n_users: int, item_price: int):
    n = int(n)
    n_items = int(n_items)
    n_users = int(n_users)
    item_price = int(item_price)

    def generate_entry() -> OrderValue:
        user_id = random.randint(0, n_users - 1)
        item1_id = random.randint(0, n_items - 1)
        item2_id = random.randint(0, n_items - 1)
        value = OrderValue(paid=False,
                           items={f"{item1_id}": 1, f"{item2_id}": 1},
                           user_id=f"{user_id}",
                           total_cost=2 * item_price)
        return value

    kv_pairs: dict[str, bytes] = {f"{i}": msgpack.encode(generate_entry())
                                  for i in range(n)}
    try:
        log(kv_pairs)
        db.mset(kv_pairs)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for orders successful"})


@app.get('/find/<order_id>')
def find_order(order_id: str):
    order_entry: OrderValue = get_order_from_db(order_id)
    return jsonify(
        {
            "order_id": order_id,
            "paid": order_entry.paid,
            "items": list(order_entry.items.keys()),
            "user_id": order_entry.user_id,
            "total_cost": order_entry.total_cost
        }
    )


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


@app.post('/addItem/<order_id>/<item_id>/<quantity>')
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
    return Response(f"Item: {item_id} added to: {order_id} price updated to: {order_entry.total_cost}",
                    status=200)


def rollback_stock(removed_items: dict[str, int]):
    for item_id, quantity in removed_items.items():
        send_post_request(f"{GATEWAY_URL}/stock/add/{item_id}/{quantity}")


# @app.post('/checkout/<order_id>')
# def checkout(order_id: str):
#     app.logger.debug(f"Checking out {order_id}")
#     order_entry: OrderValue = get_order_from_db(order_id)
#     # The removed items will contain the items that we already have successfully subtracted stock from
#     # for rollback purposes.
#     removed_items: dict[str, int] = {}
#     for item_id, quantity in order_entry.items.items():
#         stock_reply = send_post_request(f"{GATEWAY_URL}/stock/subtract/{item_id}/{quantity}")
#         if stock_reply.status_code != 200:
#             # If one item does not have enough stock we need to rollback
#             rollback_stock(removed_items)
#             abort(400, f'Out of stock on item_id: {item_id}')
#         removed_items[item_id] = quantity
#     user_reply = send_post_request(f"{GATEWAY_URL}/payment/pay/{order_entry.user_id}/{order_entry.total_cost}")
#     if user_reply.status_code != 200:
#         # If the user does not have enough credit we need to rollback all the item stock subtractions
#         rollback_stock(removed_items)
#         abort(400, "User out of credit")
#     order_entry.paid = True
#     value = msgpack.encode(order_entry)
#     try:
#         log({order_id: value})
#         db.set(order_id, value)
#     except redis.exceptions.RedisError:
#         return abort(400, DB_ERROR_STR)
#     app.logger.debug("Checkout successful")
#     return Response("Checkout successful", status=200)

def safe_post(url, retries=3, delay=0.05):
    for _ in range(retries):
        try:
            r = requests.post(url)
            if r.status_code == 200:
                return r
        except:
            time.sleep(delay)
    return None


@app.post('/checkout/<order_id>')
def checkout(order_id: str):
    app.logger.debug(f"Checking out order: {order_id}")
    order_entry: OrderValue = get_order_from_db(order_id)

    removed_items: dict[str, int] = {}
    payment_successful = False

    try:
        # Step 1: Try subtracting stock
        for item_id, quantity in order_entry.items.items():
            stock_response = safe_post(f"{STOCK_URL}/subtract/{item_id}/{quantity}")
            if not stock_response:
                raise Exception(f"Stock error on item: {item_id}")
            removed_items[item_id] = quantity

        # Step 2: Try payment
        payment_response = safe_post(
            f"{PAYMENT_URL}/pay/{order_entry.user_id}/{order_id}/{order_entry.total_cost}"
        )
        if not payment_response:
            raise Exception("Payment error")
        payment_successful = True

        # Step 3: Mark order as paid
        order_entry.paid = True
        value = msgpack.encode(order_entry)
        log({order_id: value})
        db.set(order_id, value)
        app.logger.debug("Checkout successful")
        return Response("Checkout successful", status=200)

    except Exception as e:
        app.logger.error(f"[CHECKOUT FAILED] {e}")

        # Compensation
        for item_id, quantity in removed_items.items():
            safe_post(f"{STOCK_URL}/add/{item_id}/{quantity}")
            app.logger.info(f"[ROLLBACK] Stock for {item_id}")

        if payment_successful:
            safe_post(f"{PAYMENT_URL}/cancel/{order_entry.user_id}/{order_id}")
            app.logger.info(f"[ROLLBACK] Payment for user {order_entry.user_id}")

        return Response(f"Checkout failed and compensated: {e}", status=400)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
