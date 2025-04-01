import pika
import json
import uuid


class StockProducer:
    def __init__(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue="stock-processed")

    def send_stock_update(self, order_id: str, stock_status: str):
        # Create the stock update message
        message = {
            "stock_id": str(uuid.uuid4()),
            "order_id": order_id,
            "stock_status": stock_status,
        }

        # Send message to RabbitMQ queue
        self.channel.basic_publish(
            exchange="", routing_key="stock-processed", body=json.dumps(message)
        )

        print(f"Sent stock update message: {message}")
