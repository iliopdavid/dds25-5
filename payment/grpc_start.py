import asyncio
import base64
import os

import grpc

from protos import payment_pb2_grpc
from app import PaymentService

LOG_DIR = "../logging"
LOG_FILENAME = "stock_log.txt"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILENAME)

def log(kv_pairs: dict):
    with open(LOG_PATH, 'a') as log_file:
        for (k, v) in kv_pairs.items():
            log_file.write(k + ", " + base64.b64encode(v).decode('utf-8') + "\n")

async def pay_start():
    server = grpc.aio.server()
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentService(), server)
    server.add_insecure_port('[::]:50051')

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
    asyncio.run(pay_start())