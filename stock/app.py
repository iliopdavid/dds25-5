import atexit
import logging
import os
import uuid

import grpc
import redis
from flask import Flask, abort
from msgspec import msgpack, Struct

from protos import stock_pb2, stock_pb2_grpc

DB_ERROR_STR = "DB error"

app = Flask("stock-service")

db: redis.Redis = redis.Redis(host=os.environ['REDIS_HOST'],
                              port=int(os.environ['REDIS_PORT']),
                              password=os.environ['REDIS_PASSWORD'],
                              db=int(os.environ['REDIS_DB']))

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

async def stock_start():
    server = grpc.aio.server()
    stock_pb2_grpc.add_StockServiceServicer_to_server(stock_pb2_grpc.StockService, server)
    server.add_insecure_port('[::]:50052')
    await server.start()
    await server.wait_for_termination()

class StockService(stock_pb2_grpc.StockServiceServicer):
    def batch_init_users(self, request, context):
        n = int(request.n)
        starting_stock = int(request.starting_stock)
        item_price = int(request.item_price)
        kv_pairs: dict[str, bytes] = {f"{i}": msgpack.encode(StockValue(stock=starting_stock, price=item_price))
                                      for i in range(n)}
        try:
            db.mset(kv_pairs)
        except redis.exceptions.RedisError:
            return abort(400, DB_ERROR_STR)
        return stock_pb2.BatchInitStockResponse(message="Batch init for stock successful")

    def create_item(self, request, context):
        key = str(uuid.uuid4())
        app.logger.debug(f"Item: {key} created")
        value = msgpack.encode(StockValue(stock=0, price=int(request.price)))
        try:
            db.set(key, value)
        except redis.exceptions.RedisError:
            return abort(400, DB_ERROR_STR)
        return stock_pb2.CreateItemResponse(item_id=key)

    def find_item(self, request, context):
        item_entry: StockValue = get_item_from_db(request.item_id)
        return stock_pb2.FindItemResponse(stock=item_entry.stock, price=item_entry.price)

    def add_stock(self, request, context):
        item_entry: StockValue = get_item_from_db(request.item_id)
        # update stock, serialize and update database
        item_entry.stock += int(request.amount)
        try:
            db.set(request.item_id, msgpack.encode(item_entry))
        except redis.exceptions.RedisError:
            return abort(400, DB_ERROR_STR)
        return stock_pb2.StockResponse(message=f"Item: {request.item_id} stock updated to: {item_entry.stock}", statuscode=200)

    def remove_stock(self, request, context):
        item_entry: StockValue = get_item_from_db(request.item_id)
        # update stock, serialize and update database
        item_entry.stock -= int(request.amount)
        app.logger.debug(f"Item: {request.item_id} stock updated to: {item_entry.stock}")
        if item_entry.stock < 0:
            abort(400, f"Item: {request.item_id} stock cannot get reduced below zero!")
        try:
            db.set(request.item_id, msgpack.encode(item_entry))
        except redis.exceptions.RedisError:
            return abort(400, DB_ERROR_STR)
        return stock_pb2.StockResponse(message=f"Item: {request.item_id} stock updated to: {item_entry.stock}", statuscode=200)

def close_db_connection():
    db.close()


atexit.register(close_db_connection)


if __name__ == '__main__':
    stock_start()
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
