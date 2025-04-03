import base64
import logging
import os
import atexit
import uuid

import redis
import requests

from msgspec import msgpack, Struct
from flask import Flask, jsonify, abort, Response, request

DB_ERROR_STR = "DB error"
REQ_ERROR_STR = "Requests error"

LOG_DIR = "logging"
LOG_FILENAME = "payment_log.txt"
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


app = Flask("payment-service")

db: redis.Redis = redis.Redis(host=os.environ['REDIS_HOST'],
                              port=int(os.environ['REDIS_PORT']),
                              password=os.environ['REDIS_PASSWORD'],
                              db=int(os.environ['REDIS_DB']))


def close_db_connection():
    db.close()


atexit.register(close_db_connection)


class UserValue(Struct):
    credit: int


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


def get_user_from_db(user_id: str) -> UserValue | None:
    try:
        # get serialized data
        entry: bytes = db.get(user_id)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    # deserialize data if it exists else return null
    entry: UserValue | None = msgpack.decode(entry, type=UserValue) if entry else None
    if entry is None:
        # if user does not exist in the database; abort
        abort(400, f"User: {user_id} not found!")
    return entry


def log(kv_pairs: dict):
    with open(LOG_PATH, 'a') as log_file:
        for (k, v) in kv_pairs.items():
            log_file.write(k + ", " + base64.b64encode(v).decode('utf-8') + "\n")


@app.post('/create_user')
def create_user():
    key = str(uuid.uuid4())
    value = msgpack.encode(UserValue(credit=0))
    try:
        log({key: value})
        db.set(key, value)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({'user_id': key})


@app.post('/batch_init/<n>/<starting_money>')
def batch_init_users(n: int, starting_money: int):
    n = int(n)
    starting_money = int(starting_money)
    kv_pairs: dict[str, bytes] = {f"{i}": msgpack.encode(UserValue(credit=starting_money))
                                  for i in range(n)}
    try:
        log(kv_pairs)
        db.mset(kv_pairs)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for users successful"})


@app.get('/find_user/<user_id>')
def find_user(user_id: str):
    user_entry: UserValue = get_user_from_db(user_id)
    return jsonify(
        {
            "user_id": user_id,
            "credit": user_entry.credit
        }
    )


@app.post('/add_funds/<user_id>/<amount>')
def add_credit(user_id: str, amount: int):
    user_entry: UserValue = get_user_from_db(user_id)
    # update credit, serialize and update database
    user_entry.credit += int(amount)
    value = msgpack.encode(user_entry)
    try:
        log({user_id: value})
        db.set(user_id, value)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return Response(f"User: {user_id} credit updated to: {user_entry.credit}", status=200)


@app.post('/pay/<user_id>/<order_id>/<amount>')
def pay(user_id: str, order_id: str, amount: int):
    amount = int(amount)

    data = request.get_json()
    if not data or "order_id" not in data:
        abort(400, "Missing order_id in request body")

    order_id = data["order_id"]

    payment_key = f"payment:{user_id}:{order_id}"

    try:
        # Avoid double payment
        if db.exists(payment_key):
            return jsonify({"paid": True})

        with db.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(user_id)

                    user_bytes = pipe.get(user_id)
                    if not user_bytes:
                        pipe.unwatch()
                        abort(400, f"User {user_id} not found!")

                    user_entry = msgpack.decode(user_bytes, type=UserValue)

                    if user_entry.credit < amount:
                        pipe.unwatch()
                        abort(400, f"User {user_id} does not have enough credit.")

                    # Apply deduction
                    user_entry.credit -= amount
                    encoded_user = msgpack.encode(user_entry)

                    pipe.multi()
                    pipe.set(user_id, encoded_user)
                    pipe.set(payment_key, amount, nx=True)  # mark payment done
                    pipe.execute()

                    log({user_id: encoded_user})
                    break

                except redis.WatchError:
                    continue  # Retry on concurrent modification

    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)

    return jsonify({"paid": True})


@app.post('/cancel/<user_id>/<order_id>')
def cancel_payment(user_id: str, order_id: str):
    data = request.get_json()
    if not data or "order_id" not in data:
        abort(400, "Missing order_id in request body")

    order_id = data["order_id"]

    payment_key = f"payment:{user_id}:{order_id}"

    try:
        with db.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(user_id, payment_key)

                    amount_bytes = pipe.get(payment_key)
                    if amount_bytes is None:
                        pipe.unwatch()
                        return jsonify({"cancelled": False})

                    amount = int(amount_bytes)
                    user_bytes = pipe.get(user_id)

                    if not user_bytes:
                        pipe.unwatch()
                        abort(400, f"User: {user_id} not found!")

                    user_entry = msgpack.decode(user_bytes, type=UserValue)
                    user_entry.credit += amount
                    encoded_user = msgpack.encode(user_entry)

                    pipe.multi()
                    pipe.set(user_id, encoded_user)
                    pipe.delete(payment_key)
                    pipe.execute()

                    log({user_id: encoded_user})
                    break

                except redis.WatchError:
                    continue

    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)

    return jsonify({"cancelled": True})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
