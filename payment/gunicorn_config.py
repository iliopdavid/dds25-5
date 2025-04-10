# gunicorn_config.py
import threading
from consumer import PaymentConsumer
import redis
import os


def on_starting(server):
    from app import app, on_start

    with app.app_context():
        on_start()


def post_fork(server, worker):
    """
    Server hook that executes after a worker has been forked
    """
    worker.db = redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        password=os.environ["REDIS_PASSWORD"],
        db=int(os.environ["REDIS_DB"]),
    )
    worker.consumer = PaymentConsumer(worker.db)
    worker.consumer_thread = threading.Thread(
        target=worker.consumer.consume_messages, daemon=True
    )
    worker.consumer_thread.start()

    # Create a single producer for this worker
    from app import app

    app.logger.info(f"Worker {worker.pid} initialized with consumer and producer")


def worker_exit(server, worker):
    """
    Server hook that executes when a worker exits
    """
    # Stop the consumer thread
    if hasattr(worker, "consumer"):
        worker.consumer.cleanup()
        worker.consumer_thread.join(timeout=1.0)
