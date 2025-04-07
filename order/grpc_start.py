import asyncio
import base64
import os

import grpc

from app import OrderService
from protos import order_pb2_grpc

LOG_DIR = "../logging"
LOG_FILENAME = "stock_log.txt"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILENAME)

def log(kv_pairs: dict):
    with open(LOG_PATH, 'a') as log_file:
        for (k, v) in kv_pairs.items():
            log_file.write(k + ", " + base64.b64encode(v).decode('utf-8') + "\n")

async def order_start():
    server = grpc.aio.server()
    order_pb2_grpc.add_OrderServiceServicer_to_server(OrderService(), server)
    server.add_insecure_port('[::]:50050')

    # Start HTTP Server (FastAPI)
    config = {"host": "0.0.0.0", "port": 8000}
    # fastapi_task = asyncio.create_task(app.__call__("lifespan", config))

    # Run gRPC Server
    await server.start()
    # log({str(1): "Running"})

    # Delay here ensures server is started before FastAPI tries to connect
    await asyncio.sleep(0.1)

    await server.wait_for_termination()

if __name__ == '__main__':
    asyncio.run(order_start())