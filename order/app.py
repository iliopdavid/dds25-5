import atexit
import logging
import os
import random
import uuid

import grpc
import redis
import requests
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from msgspec import msgpack, Struct

from protos import order_pb2_grpc
from protos import order_pb2, stock_pb2_grpc, payment_pb2_grpc, stock_pb2
from protos.order_pb2_grpc import OrderServiceServicer
from protos.stock_pb2_grpc import StockService

DB_ERROR_STR = "DB error"
REQ_ERROR_STR = "Requests error"

#GATEWAY_URL = os.environ['GATEWAY_URL']

app = FastAPI()
logger = logging.getLogger("uvicorn")
gunicorn_logger = logging.getLogger("gunicorn.error")
app.logger = gunicorn_logger
# Load environment variables from .env file
load_dotenv(dotenv_path="../env/order_redis.env")

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

def send_post_request(url: str):
    try:
        response = requests.post(url)
    except requests.exceptions.RequestException:
        app.logger.error(REQ_ERROR_STR)
        raise HTTPException(status_code=400, detail=REQ_ERROR_STR)
    else:
        return response


def send_get_request(url: str):
    try:
        response = requests.get(url)
    except requests.exceptions.RequestException:
        app.logger.error(REQ_ERROR_STR)
        raise HTTPException(status_code=400, detail=REQ_ERROR_STR)
    else:
        return response

def get_order_from_db(order_id: str) -> OrderValue | None:
    try:
        # get serialized data
        entry: bytes = db.get(order_id)
    except redis.exceptions.RedisError:
        app.logger.error(DB_ERROR_STR)
        raise HTTPException(status_code=400, detail=DB_ERROR_STR)
    # deserialize data if it exists else return null
    entry: OrderValue | None = msgpack.decode(entry, type=OrderValue) if entry else None
    if entry is None:
        # if order does not exist in the database; abort
        app.logger.error(f"Order: {order_id} not found!")
        raise HTTPException(status_code=400, detail=f"Order: {order_id} not found!")
    return entry

def rollback_stock(removed_items: dict[str, int]):
    stockstub = stock_pb2_grpc.StockServiceStub(StockService)
    for item_id, quantity in removed_items.items():
        stockstub.add_stock(item_id, quantity)
        #send_post_request(f"{GATEWAY_URL}/stock/add/{item_id}/{quantity}")

@app.post('/create/{user_id}')
async def handle_http_request_create(user_id: str):
    try:
        grpc_request = order_pb2.CreateOrderRequest(user_id=str(user_id))  # Convert HTTP data to gRPC format

        async with grpc.aio.insecure_channel('localhost:50050', options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = order_pb2_grpc.OrderServiceStub(channel=channel)
            response = await stub.create_order(grpc_request)
        return {"order_id": response.order_id}  # Convert gRPC response to JSON
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}

@app.post('/checkout/<order_id>')
async def handle_http_request_checkout(order_id: str):
    try:
        grpc_request = order_pb2.OrderIdRequest(order_id=str(order_id))  # Convert HTTP data to gRPC format

        async with grpc.aio.insecure_channel('localhost:50050', options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = order_pb2_grpc.OrderServiceStub(channel=channel)
            response = await stub.checkout(grpc_request)
        return {"message": response.message, "statuscode": response.statuscode}  # Convert gRPC response to JSON
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}

class OrderService(OrderServiceServicer):
    def batch_init_users(self, request, context):
        n = int(request.n)
        n_items = int(request.n_items)
        n_users = int(request.n_users)
        item_price = int(request.item_price)

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
            db.mset(kv_pairs)
        except redis.exceptions.RedisError:
            app.logger.error(DB_ERROR_STR)
            raise HTTPException(status_code=400, detail=DB_ERROR_STR)
        return order_pb2.BatchInitOrderResponse(message="Batch init for orders successful")

    def create_order(self, request, context):
        key = str(uuid.uuid4())
        value = msgpack.encode(OrderValue(paid=False, items={}, user_id=request.user_id, total_cost=0))
        try:
            db.set(key, value)
        except redis.exceptions.RedisError:
            app.logger.error(DB_ERROR_STR)
            raise HTTPException(status_code=400, detail=DB_ERROR_STR)
        return order_pb2.CreateOrderResponse(order_id=key)

    def find_order(self, request, context):
        order_entry: OrderValue = get_order_from_db(request.order_id)
        return order_pb2.FindOrderResponse(order_id=request.order_id, paid=order_entry.paid,
                                                        items=list(order_entry.items.keys()), user_id=order_entry.user_id,
                                                        total_cost=order_entry.total_cost)

    def add_item(self, request, context):
        with grpc.aio.insecure_channel('localhost:50052') as channel:
            stockstub = stock_pb2_grpc.StockServiceStub(channel)
            order_entry: OrderValue = get_order_from_db(request.order_id)
            item_reply = stockstub.find_item(request.item_id)
            #item_reply = send_get_request(f"{GATEWAY_URL}/stock/find/{request.item_id}")
            if item_reply.status_code != 200:
                # Request failed because item does not exist
                app.logger.error(f"Item: {request.item_id} does not exist!")
                raise HTTPException(status_code=400, detail=f"Item: {request.item_id} does not exist!")
            item_json: dict = item_reply.json()
            if request.item_id in order_entry.items:
                order_entry.items[request.item_id] += int(request.quantity)
            else:
                order_entry.items[request.item_id] = int(request.quantity)
            order_entry.total_cost += int(request.quantity) * item_json["price"]
            try:
                db.set(request.order_id, msgpack.encode(order_entry))
            except redis.exceptions.RedisError:
                app.logger.error(DB_ERROR_STR)
                raise HTTPException(status_code=400, detail=DB_ERROR_STR)
            return order_pb2.StatuscodeResponse(message=f"Item: {request.item_id} added to: {request.order_id} price updated to: {order_entry.total_cost}",
                            statuscode=200)

    def checkout(self, request, context):
        with grpc.aio.insecure_channel('localhost:50052') as channelstock:
            stockstub = stock_pb2_grpc.StockServiceStub(channelstock)
            with grpc.aio.insecure_channel('localhost:50051') as channelpay:
                paymentstub = payment_pb2_grpc.PaymentServiceStub(channelpay)
                app.logger.debug(f"Checking out {request.order_id}")
                order_entry: OrderValue = get_order_from_db(request.order_id)
                # The removed items will contain the items that we already have successfully subtracted stock from
                # for rollback purposes.
                removed_items: dict[str, int] = {}
                for item_id, quantity in order_entry.items.items():
                    stock_reply = stockstub.remove_stock(stock_pb2.StockRequest(item_id, quantity))
                    #stock_reply = send_post_request(f"{GATEWAY_URL}/stock/subtract/{item_id}/{quantity}")
                    if stock_reply.status_code != 200:
                        # If one item does not have enough stock we need to rollback
                        rollback_stock(removed_items)
                        app.logger.error(f'Out of stock on item_id: {item_id}')
                        raise HTTPException(status_code=400, detail=f'Out of stock on item_id: {item_id}')
                    removed_items[item_id] = quantity
                user_reply = paymentstub.remove_credit(order_entry.user_id, order_entry.total_cost)
                #user_reply = send_post_request(f"{GATEWAY_URL}/payment/pay/{order_entry.user_id}/{order_entry.total_cost}")
                if user_reply.status_code != 200:
                    # If the user does not have enough credit we need to rollback all the item stock subtractions
                    rollback_stock(removed_items)
                    app.logger.error("User out of credit")
                    raise HTTPException(status_code=400, detail="User out of credit")
                order_entry.paid = True
                try:
                    db.set(request.order_id, msgpack.encode(order_entry))
                except redis.exceptions.RedisError:
                    app.logger.error(DB_ERROR_STR)
                    raise HTTPException(status_code=400, detail=DB_ERROR_STR)
                app.logger.debug("Checkout successful")
                return order_pb2.StatuscodeResponse(message="Checkout successful", statuscode=200)

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
