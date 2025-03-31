import atexit
import logging
import os
import uuid

import grpc
import redis
import requests
from flask import Flask, abort
from msgspec import msgpack, Struct

from protos import payment_pb2, payment_pb2_grpc

DB_ERROR_STR = "DB error"
REQ_ERROR_STR = "Requests error"

app = Flask("payment-service")

db: redis.Redis = redis.Redis(host=os.environ['REDIS_HOST'],
                              port=int(os.environ['REDIS_PORT']),
                              password=os.environ['REDIS_PASSWORD'],
                              db=int(os.environ['REDIS_DB']))
async def pay_start():
    server = grpc.aio.server()
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(payment_pb2_grpc.PaymentService(), server)
    server.add_insecure_port('[::]:50051')
    await server.start()
    await server.wait_for_termination()

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

class PaymentService(payment_pb2_grpc.PaymentServiceServicer):
    def batch_init_users(self, request, context):
        n = int(request.n)
        starting_money = int(request.starting_money)
        kv_pairs: dict[str, bytes] = {f"{i}": msgpack.encode(UserValue(credit=starting_money))
                                      for i in range(n)}
        try:
            db.mset(kv_pairs)
        except redis.exceptions.RedisError:
            return abort(400, DB_ERROR_STR)
        return payment_pb2.BatchInitPayResponse(message="Batch init for users successful")

    def create_user(self, request, context):
        key = str(uuid.uuid4())
        value = msgpack.encode(UserValue(credit=0))
        try:
            db.set(key, value)
        except redis.exceptions.RedisError:
            return abort(400, DB_ERROR_STR)
        return payment_pb2.CreateUserResponse(user_id=key)

    def find_user(self, request, context):
        user_entry: UserValue = get_user_from_db(request.user_id)
        return payment_pb2.FindUserResponse(user_id=request.user_id, credit=user_entry.credit)

    def add_credit(self, request, context):
        user_entry: UserValue = get_user_from_db(request.user_id)
        # update credit, serialize and update database
        user_entry.credit += int(request.amount)
        try:
            db.set(request.user_id, msgpack.encode(user_entry))
        except redis.exceptions.RedisError:
            return abort(400, DB_ERROR_STR)
        return payment_pb2.FundsResponse(message=f"User: {request.user_id} credit updated to: {user_entry.credit}", statuscode=200)

    def remove_credit(self, request, context):
        app.logger.debug(f"Removing {request.amount} credit from user: {request.user_id}")
        user_entry: UserValue = get_user_from_db(request.user_id)
        # update credit, serialize and update database
        user_entry.credit -= int(request.amount)
        if user_entry.credit < 0:
            abort(400, f"User: {request.user_id} credit cannot get reduced below zero!")
        try:
            db.set(request.user_id, msgpack.encode(user_entry))
        except redis.exceptions.RedisError:
            return abort(400, DB_ERROR_STR)
        return payment_pb2.FundsResponse(message=f"User: {request.user_id} credit updated to: {user_entry.credit}", statuscode=200)


if __name__ == '__main__':
    pay_start()
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
