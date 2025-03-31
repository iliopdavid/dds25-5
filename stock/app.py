import base64
import logging
import os
import atexit
import uuid

import redis

from msgspec import msgpack, Struct
from flask import Flask, jsonify, abort, Response, request


DB_ERROR_STR = "DB error"

LOG_DIR = "logging"
LOG_FILENAME = "stock_log.txt"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILENAME)


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


app = Flask("stock-service")
app.logger.setLevel(logging.DEBUG)

db: redis.Redis = redis.Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(os.environ["REDIS_DB"]),
)


def close_db_connection():
    db.close()


atexit.register(close_db_connection)

class StockValue(Struct):
    stock: int
    price: int


def get_item_from_db(item_id: str) -> StockValue | None:
    # get serialized data
    try:
        entry: bytes = db.get(item_id)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    # deserialize data if it exists else return null
    entry: StockValue | None = msgpack.decode(entry, type=StockValue) if entry else None
    if entry is None:
        # if item does not exist in the database; abort
        abort(400, f"Item: {item_id} not found!")
    return entry


def log(kv_pairs: dict):
    with open(LOG_PATH, "a") as log_file:
        for k, v in kv_pairs.items():
            log_file.write(k + ", " + base64.b64encode(v).decode("utf-8") + "\n")
            
@app.post('/item/create/<price>')
def create_item(price: int):
    key = str(uuid.uuid4())
    app.logger.debug(f"Item: {key} created")
    value = msgpack.encode(StockValue(stock=0, price=int(price)))
    try:
        log({key: value})
        db.set(key, value)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({"item_id": key})


@app.post('/batch_init/<n>/<starting_stock>/<item_price>')
def batch_init_users(n: int, starting_stock: int, item_price: int):
    n = int(n)
    starting_stock = int(starting_stock)
    item_price = int(item_price)
    kv_pairs: dict[str, bytes] = {
        f"{i}": msgpack.encode(StockValue(stock=starting_stock, price=item_price))
        for i in range(n)
    }
    try:
        log(kv_pairs)
        db.mset(kv_pairs)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for stock successful"})


@app.get('/find/<item_id>')
def find_item(item_id: str):
    item_entry: StockValue = get_item_from_db(item_id)
    return jsonify({"stock": item_entry.stock, "price": item_entry.price})


@app.post('/add/<item_id>/<amount>')
def add_stock(item_id: str, amount: int):
    item_entry: StockValue = get_item_from_db(item_id)
    # update stock, serialize and update database
    item_entry.stock += int(amount)
    value = msgpack.encode(item_entry)
    try:
        log({item_id: value})
        db.set(item_id, value)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return Response(f"Item: {item_id} stock updated to: {item_entry.stock}", status=200)


@app.post('/subtract/<item_id>/<amount>')
def remove_stock(item_id: str, amount: int):
    amount = int(amount)
    try:
        with db.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(item_id)

                    item_bytes = pipe.get(item_id)
                    if not item_bytes:
                        pipe.unwatch()
                        abort(400, f"Item: {item_id} not found!")

                    item_entry = msgpack.decode(item_bytes, type=StockValue)

                    if item_entry.stock < amount:
                        pipe.unwatch()
                        abort(400, f"Item: {item_id} does not have enough stock.")

                    item_entry.stock -= amount
                    encoded_item = msgpack.encode(item_entry)

                    pipe.multi()
                    pipe.set(item_id, encoded_item)
                    pipe.execute()

                    log({item_id: encoded_item})
                    break

                except redis.WatchError:
                    continue  # retry

    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)

    return Response(f"Item: {item_id} stock updated to: {item_entry.stock}", status=200)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)