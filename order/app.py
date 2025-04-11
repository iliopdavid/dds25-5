import base64
import json
import logging
import os
import random
import uuid
import asyncio


from msgspec import msgpack, Struct
from quart import Quart, jsonify, abort, Response
import aiohttp
import redis
from producer import OrderProducer
from consumer import run_consumer

DB_ERROR_STR = "DB error"
REQ_ERROR_STR = "Requests error"

GATEWAY_URL = os.environ["GATEWAY_URL"]
STOCK_URL = os.environ["STOCK_URL"]
PAYMENT_URL = os.environ["PAYMENT_URL"]

LOG_DIR = "logging"
LOG_FILENAME = "order_log.txt"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILENAME)

app = Quart("order-service")
app.logger.setLevel(logging.INFO)

db = redis.asyncio.Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(os.environ["REDIS_DB"]),
)

producer = OrderProducer()


class OrderValue(Struct):
    paid: bool
    items: dict[str, int]
    user_id: str
    total_cost: int


@app.before_serving
async def startup():
    try:
        app.logger.debug("Startup initiated")

        if os.path.exists(LOG_PATH):
            app.logger.debug("Log file exists. Starting recover_from_logs()")
            await recover_from_logs()
            app.logger.debug("recover_from_logs() completed")
        else:
            try:
                with open(LOG_PATH, "x"):
                    pass
                app.logger.debug(f"Log file created at: {LOG_PATH}")
            except FileExistsError:
                app.logger.error(
                    "FileExistsError: Log file already exists unexpectedly"
                )
                abort(400, DB_ERROR_STR)

        app.logger.debug("Initializing producer")
        await producer.init()
        app.logger.debug("Producer initialized")

        app.logger.debug("Creating background consumer task")
        asyncio.create_task(run_consumer(db))

        app.logger.info("Producer and Consumer initialized successfully.")
    except Exception as e:
        app.logger.exception(f"Startup failed: {e}")
        raise


async def recover_from_logs():
    with open(LOG_PATH, "r") as file:
        for line in file:
            info = line.strip().split(", ")
            await db.set(info[0], base64.b64decode(info[1]))


def log(kv_pairs: dict):
    with open(LOG_PATH, "a") as log_file:
        for k, v in kv_pairs.items():
            log_file.write(k + ", " + base64.b64encode(v).decode("utf-8") + "\n")


async def get_order_from_db(order_id: str) -> OrderValue:
    try:
        entry = await db.get(order_id)
    except Exception:
        abort(400, DB_ERROR_STR)

    if not entry:
        abort(400, f"Order: {order_id} not found!")

    return msgpack.decode(entry, type=OrderValue)


async def wait_for_response(pubsub, channel_name, timeout=10.0):
    start_time = asyncio.get_event_loop().time()

    while True:
        if (asyncio.get_event_loop().time() - start_time) > timeout:
            raise asyncio.TimeoutError("Timeout waiting for message")

        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
        if message and message["type"] == "message":
            return message
        await asyncio.sleep(0.1)


async def handle_checkout_complete(order_id):
    channel_name = f"checkout-response:{order_id}"
    payload = {"status": "success"}
    try:
        await db.publish(channel_name, json.dumps(payload))
        app.logger.debug(f"Published SUCCESS to {channel_name} for order {order_id}")
    except Exception as e:
        app.logger.error(
            f"Failed to publish SUCCESS to {channel_name} for order {order_id}: {e}"
        )


async def handle_rollback_complete(order_id):
    channel_name = f"checkout-response:{order_id}"
    payload = {"status": "failure"}
    try:
        await db.publish(channel_name, json.dumps(payload))
        app.logger.debug(f"Published FAILURE to {channel_name} for order {order_id}")
    except Exception as e:
        app.logger.error(
            f"Failed to publish FAILURE to {channel_name} for order {order_id}: {e}"
        )


@app.post("/internal/recover-from-logs")
async def trigger_log_recovery():
    if os.path.exists(LOG_PATH):
        await recover_from_logs()
        return jsonify({"msg": "Recovered from logs successfully"})
    else:
        try:
            with open(LOG_PATH, "x"):
                pass
            return jsonify({"msg": "Log file created successfully"})
        except FileExistsError:
            app.logger.warning(f"Log file already created by another worker.")


@app.post("/create/<user_id>")
async def create_order(user_id: str):
    key = str(uuid.uuid4())
    value = msgpack.encode(
        OrderValue(paid=False, items={}, user_id=user_id, total_cost=0)
    )
    try:
        log({key: value})
        await db.set(key, value)
    except Exception:
        return abort(400, DB_ERROR_STR)
    return jsonify({"order_id": key})


@app.post("/batch_init/<int:n>/<int:n_items>/<int:n_users>/<int:item_price>")
async def batch_init_users(n: int, n_items: int, n_users: int, item_price: int):
    def generate_entry() -> OrderValue:
        user_id = random.randint(0, n_users - 1)
        item1_id = random.randint(0, n_items - 1)
        item2_id = random.randint(0, n_items - 1)
        return OrderValue(
            paid=False,
            items={f"{item1_id}": 1, f"{item2_id}": 1},
            user_id=str(user_id),
            total_cost=2 * item_price,
        )

    kv_pairs = {f"{i}": msgpack.encode(generate_entry()) for i in range(n)}
    try:
        log(kv_pairs)
        await db.mset(kv_pairs)
    except Exception:
        return abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for orders successful"})


@app.get("/find/<order_id>")
async def find_order(order_id: str):
    order_entry = await get_order_from_db(order_id)
    return jsonify(
        {
            "order_id": order_id,
            "paid": order_entry.paid,
            "items": list(order_entry.items.keys()),
            "user_id": order_entry.user_id,
            "total_cost": order_entry.total_cost,
        }
    )


async def send_get_request(url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                await response.read()
                return response
    except aiohttp.ClientError:
        abort(400, REQ_ERROR_STR)


@app.post("/addItem/<order_id>/<item_id>/<int:quantity>")
async def add_item(order_id: str, item_id: str, quantity: int):
    order_entry = await get_order_from_db(order_id)
    item_reply = await send_get_request(f"{GATEWAY_URL}/stock/find/{item_id}")
    if item_reply.status != 200:
        abort(400, f"Item: {item_id} does not exist!")

    item_json = await item_reply.json()
    order_entry.items[item_id] = order_entry.items.get(item_id, 0) + quantity
    order_entry.total_cost += quantity * item_json["price"]

    value = msgpack.encode(order_entry)
    try:
        log({order_id: value})
        await db.set(order_id, value)
    except Exception:
        return abort(400, DB_ERROR_STR)

    return Response(
        f"Item: {item_id} added to: {order_id} price updated to: {order_entry.total_cost}",
        status=200,
    )


@app.post("/checkout/<order_id>")
async def checkout(order_id: str):
    pubsub = None
    channel_name = f"checkout-response:{order_id}"

    try:
        order_entry = await get_order_from_db(order_id)

        pubsub = db.pubsub()
        await pubsub.subscribe(channel_name)
        app.logger.debug(f"Subscribed to {channel_name} for order {order_id}")

        await producer.send_checkout_called(
            order_id, order_entry.user_id, order_entry.total_cost, order_entry.items
        )
        message = None
        try:
            message = await wait_for_response(pubsub, channel_name, timeout=10.0)
        except asyncio.TimeoutError:
            app.logger.warning(
                f"Timeout waiting for response on {channel_name} for order {order_id}"
            )
            message = None

        if message and message.get("type") == "message":
            try:
                response_data = json.loads(message["data"])
                status = response_data.get("status")

                if status == "success":
                    app.logger.info(f"Checkout with status 200 with order {order_id}")
                    return (
                        jsonify(
                            {
                                "message": "Order checkout completed successfully",
                                "order_id": order_id,
                                "status": "SUCCESS",
                            }
                        ),
                        200,
                    )
                else:
                    app.logger.warning(f"Checkout failed checkout for order {order_id}")
                    return (
                        jsonify(
                            {
                                "message": f"Order checkout failed",
                                "order_id": order_id,
                                "status": "FAILURE",
                            }
                        ),
                        400,
                    )

            except Exception as e:
                app.logger.error(
                    f"Error processing PubSub response for {order_id}: {e}"
                )
                return (
                    jsonify({"error": "Internal server error processing response"}),
                    500,
                )
        else:
            app.logger.error(
                f"Checkout timed out for order {order_id} waiting on {channel_name}"
            )
            return (
                jsonify(
                    {
                        "message": "Order checkout failed: Timeout waiting for completion",
                        "order_id": order_id,
                        "status": "FAILURE",
                        "reason": "timeout",
                    }
                ),
                408,
            )
    except Exception as e:
        app.logger.error(f"Checkout failed for order {order_id}: {e}")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(app, host="0.0.0.0", port=8000)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
