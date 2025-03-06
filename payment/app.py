import logging
import os
import atexit
import uuid

import redis

from msgspec import msgpack, Struct
from flask import Flask, jsonify, abort, Response

from order.app import send_get_request, GATEWAY_URL, OrderValue, get_order_from_db, send_post_request

DB_ERROR_STR = "DB error"

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


@app.post('/create_user')
def create_user():
    key = str(uuid.uuid4())
    value = msgpack.encode(UserValue(credit=0))
    try:
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
        db.mset(kv_pairs)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for users successful"})


@app.post('/cancel/{user_id}/{order_id}')
def cancel(user_id: str, order_id: str):
    app.logger.debug(f"Cancelling payment of order {order_id} of user {user_id}")
    user_entry: UserValue = get_user_from_db(user_id)
    order_reply = send_get_request(f"{GATEWAY_URL}/order/find/{order_id}")
    if order_reply.status_code != 200:
        # Request failed because item does not exist
        abort(400, f"Order: {order_id} does not exist!")
    if order_reply.json["user_id"] != user_id:
        abort(400, f"Order: {order_id} does not belong to user: {user_id}")
    if order_reply.json["paid"]:
        rollback_cost = order_reply.json["total_cost"]
        pay_reply = send_post_request(f"{GATEWAY_URL}/add_funds/{user_id}/{rollback_cost}")
        if pay_reply.status_code != 200:
            # Request failed because item does not exist
            abort(400, f"User: {user_id} does not exist!")
    else:
        # TODO: think about what can be used to verify cancelled payment if money wasn't deducted yet (e.g. use logger in some way)
        return Response(f"Payment of order: {order_id} of user: {user_id} was not paid yet, but is cancelled", status=200)
    return Response(f"Payment of order: {order_id} of user: {user_id} is rolled back", status=200)


@app.get('/status/{user_id}/{order_id}')
def status(user_id: str, order_id: str):
    app.logger.debug(f"Checking status of order {order_id} of user {user_id}")
    user_entry: UserValue = get_user_from_db(user_id)
    order_reply: OrderValue = get_order_from_db(order_id)
    return order_reply.paid


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
    try:
        db.set(user_id, msgpack.encode(user_entry))
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return Response(f"User: {user_id} credit updated to: {user_entry.credit}", status=200)


@app.post('/pay/<user_id>/<amount>')
def remove_credit(user_id: str, amount: int):
    app.logger.debug(f"Removing {amount} credit from user: {user_id}")
    user_entry: UserValue = get_user_from_db(user_id)
    # update credit, serialize and update database
    user_entry.credit -= int(amount)
    if user_entry.credit < 0:
        abort(400, f"User: {user_id} credit cannot get reduced below zero!")
    try:
        db.set(user_id, msgpack.encode(user_entry))
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return Response(f"User: {user_id} credit updated to: {user_entry.credit}", status=200)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
