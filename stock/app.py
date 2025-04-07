import atexit
import base64
import logging
import os
import uuid

import grpc
from dotenv import load_dotenv
import redis

import uvicorn
from fastapi import FastAPI, HTTPException
from msgspec import msgpack, Struct

from protos import stock_pb2, stock_pb2_grpc

# from msgspec import msgpack, Struct

DB_ERROR_STR = "DB error"
LOG_DIR = "logging"
LOG_FILENAME = "stock_log.txt"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILENAME)

app = FastAPI()
logger = logging.getLogger("uvicorn")
gunicorn_logger = logging.getLogger("gunicorn.error")
app.logger = gunicorn_logger
# Load environment variables from .env file
load_dotenv(dotenv_path="../env/stock_redis.env")
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
        app.logger.error(DB_ERROR_STR)
        raise HTTPException(status_code=400, detail=DB_ERROR_STR)
    # deserialize data if it exists else return null
    entry: StockValue | None = msgpack.decode(entry, type=StockValue) if entry else None
    if entry is None:
        # if item does not exist in the database; abort
        app.logger.error(f"Item: {item_id} not found!")
        raise HTTPException(status_code=400, detail=f"Item: {item_id} not found!")
    return entry

# async def stock_start():
#     server = grpc.aio.server()
#     stock_pb2_grpc.add_StockServiceServicer_to_server(stock_pb2_grpc.StockService, server)
#     server.add_insecure_port('[::]:50052')
#
#     # Start HTTP Server (FastAPI)
#     config = {"host": "0.0.0.0", "port": 8000}
#     # fastapi_task = asyncio.create_task(app.__call__("lifespan", config))
#
#     # Run gRPC Server
#     await server.start()
#     log({str(1): "Running"})
#
#     # Delay here ensures server is started before FastAPI tries to connect
#     await asyncio.sleep(0.1)
#
#     await server.wait_for_termination()
# #await fastapi_task

def log(kv_pairs: dict):
    with open(LOG_PATH, 'a') as log_file:
        for (k, v) in kv_pairs.items():
            log_file.write(k + ", " + base64.b64encode(v).decode('utf-8') + "\n")

@app.post("/item/create/{price}")
async def handle_http_request(price: str):
    try:
        price = int(price)
        grpc_request = stock_pb2.CreateItemRequest(price=price)  # Convert HTTP data to gRPC format

        async with grpc.aio.insecure_channel('localhost:50052', options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = stock_pb2_grpc.StockServiceStub(channel=channel)
            response = await stub.create_item(grpc_request)
        return {"item_id": response.item_id}  # Convert gRPC response to JSON
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}

@app.get('/find/{item_id}')
async def handle_http_request_find(item_id: str):
    try:
        grpc_request = stock_pb2.FindItemRequest(item_id=str(item_id))  # Convert HTTP data to gRPC format

        async with grpc.aio.insecure_channel('localhost:50052', options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = stock_pb2_grpc.StockServiceStub(channel=channel)
            response = await stub.find_item(grpc_request)
        return {"stock": response.stock, "price": response.price}  # Convert gRPC response to JSON
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}

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
            app.logger.error(DB_ERROR_STR)
            raise HTTPException(status_code=400, detail=DB_ERROR_STR)
        return stock_pb2.BatchInitStockResponse(message="Batch init for stock successful")

    def create_item(self, request, context):
        key = str(uuid.uuid4())
        app.logger.debug(f"Item: {key} created")
        value = msgpack.encode(StockValue(stock=0, price=int(request.price)))
        try:
            db.set(key, value)
        except redis.exceptions.RedisError:
            app.logger.error(DB_ERROR_STR)
            raise HTTPException(status_code=400, detail=DB_ERROR_STR)
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
            app.logger.error(DB_ERROR_STR)
            raise HTTPException(status_code=400, detail=DB_ERROR_STR)
        return stock_pb2.StockResponse(message=f"Item: {request.item_id} stock updated to: {item_entry.stock}", statuscode=200)

    def remove_stock(self, request, context):
        item_entry: StockValue = get_item_from_db(request.item_id)
        # update stock, serialize and update database
        item_entry.stock -= int(request.amount)
        app.logger.debug(f"Item: {request.item_id} stock updated to: {item_entry.stock}")
        if item_entry.stock < 0:
            app.logger.error(f"Item: {request.item_id} stock cannot get reduced below zero!")
            raise HTTPException(status_code=400, detail=f"Item: {request.item_id} stock cannot get reduced below zero!")
        try:
            db.set(request.item_id, msgpack.encode(item_entry))
        except redis.exceptions.RedisError:
            app.logger.error(DB_ERROR_STR)
            raise HTTPException(status_code=400, detail=DB_ERROR_STR)
        return stock_pb2.StockResponse(message=f"Item: {request.item_id} stock updated to: {item_entry.stock}", statuscode=200)

def close_db_connection():
    db.close()


atexit.register(close_db_connection)


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
