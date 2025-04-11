import asyncio
import base64
import logging
import os
import atexit
import uuid
import redis.asyncio as redis
from msgspec import msgpack, Struct
from quart import Quart, jsonify, abort, Response
from producer import StockProducer
from consumer import run_stock_consumer

DB_ERROR_STR = "DB error"

LOG_DIR = "logging"
LOG_FILENAME = "stock_log.txt"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILENAME)


async def recover_from_logs():
    """Recover stock data from the log file."""
    with open(LOG_PATH, "r") as file:
        for line in file:
            info = line.strip().split(", ")
            await db.set(info[0], base64.b64decode(info[1]))


app = Quart("stock-service")

db: redis.Redis = redis.asyncio.Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(os.environ["REDIS_DB"]),
)

producer = StockProducer()


def close_db_connection():
    """Close Redis connection when app shuts down."""
    db.close()


atexit.register(close_db_connection)


class StockValue(Struct):
    stock: int
    price: int


async def get_item_from_db(item_id: str) -> StockValue:
    """Retrieve an item from the Redis database."""
    try:
        entry: bytes = await db.get(item_id)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)

    entry: StockValue | None = msgpack.decode(entry, type=StockValue) if entry else None
    if entry is None:
        abort(400, f"Item: {item_id} not found!")
    return entry


def log(kv_pairs: dict):
    """Log the key-value pairs into the log file."""
    with open(LOG_PATH, "a") as log_file:
        for k, v in kv_pairs.items():
            log_file.write(k + ", " + base64.b64encode(v).decode("utf-8") + "\n")


@app.before_serving
async def startup():
    """App startup logic."""
    if os.path.exists(LOG_PATH):
        await recover_from_logs()
    else:
        try:
            with open(LOG_PATH, "x"):
                pass
            app.logger.debug(f"Log file created at: {LOG_PATH}")
        except FileExistsError:
            app.logger.error("FileExistsError: Log file already exists unexpectedly")

    await producer.init()

    asyncio.create_task(run_stock_consumer(db))

    app.logger.info("Producer and Consumer initialized successfully.")


@app.post("/internal/recover-from-logs")
async def on_start():
    """Recover the logs if the file exists."""
    if os.path.exists(LOG_PATH):
        await recover_from_logs()
        return jsonify({"msg": "Recovered from logs successfully"})
    else:
        try:
            with open(LOG_PATH, "x"):
                pass
            app.logger.debug(f"Log file created at: {LOG_PATH}")
            return jsonify({"msg": "Log file created successfully"})
        except FileExistsError:
            app.logger.warning(f"Log file already created by another worker.")


@app.post("/item/create/<int:price>")
async def create_item(price: int):
    """Create a new stock item."""
    key = str(uuid.uuid4())
    app.logger.debug(f"Item: {key} created")
    value = msgpack.encode(StockValue(stock=0, price=price))
    try:
        log({key: value})
        await db.set(key, value)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({"item_id": key})


@app.post("/batch_init/<int:n>/<int:starting_stock>/<int:item_price>")
async def batch_init_users(n: int, starting_stock: int, item_price: int):
    """Initialize multiple stock items in batch."""
    kv_pairs: dict[str, bytes] = {
        f"{i}": msgpack.encode(StockValue(stock=starting_stock, price=item_price))
        for i in range(n)
    }
    try:
        log(kv_pairs)
        await db.mset(kv_pairs)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for stock successful"})


@app.get("/find/<item_id>")
async def find_item(item_id: str):
    """Find a specific item by its ID."""
    item_entry: StockValue = await get_item_from_db(item_id)
    return jsonify({"stock": item_entry.stock, "price": item_entry.price})


@app.post("/add/<item_id>/<int:amount>")
async def add_stock(item_id: str, amount: int):
    """Add stock to an item."""
    item_entry: StockValue = await get_item_from_db(item_id)
    item_entry.stock += amount
    value = msgpack.encode(item_entry)
    try:
        log({item_id: value})
        await db.set(item_id, value)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return Response(f"Item: {item_id} stock updated to: {item_entry.stock}", status=200)


@app.post("/subtract/<item_id>/<int:amount>")
async def remove_stock(item_id: str, amount: int):
    """Remove stock from an item with a transaction."""
    try:
        async with db.pipeline() as pipe:
            # Repeat until successful.
            while True:
                try:
                    # Watch the key we are about to change.
                    pipe.watch(item_id)

                    # The pipeline executes commands directly (instead of buffering them) from immediately after the
                    # `watch()` call until we begin the transaction.
                    item_bytes = await pipe.get(item_id)
                    if not item_bytes:
                        pipe.unwatch()
                        abort(400, f"Item: {item_id} not found!")

                    item_entry = msgpack.decode(item_bytes, type=StockValue)

                    if item_entry.stock < amount:
                        pipe.unwatch()
                        abort(400, f"Item: {item_id} does not have enough stock.")

                    item_entry.stock -= amount
                    encoded_item = msgpack.encode(item_entry)

                    # Start the transaction, which will enable buffering again for the remaining commands.
                    pipe.multi()
                    pipe.set(item_id, encoded_item)
                    await pipe.execute()

                    log({item_id: encoded_item})

                    # The transaction succeeded, so break out of the loop.
                    break
                except redis.WatchError:
                    # The transaction failed, so continue with the next attempt.
                    continue

    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)

    return Response(f"Item: {item_id} stock updated to: {item_entry.stock}", status=200)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
