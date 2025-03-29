from kafka import KafkaProducer
import json
import uuid


class StockProducer:
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers=["kafka:9092"],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

    def send_stock_update(self, order_id: str, stock_status: str):
        # Create the stock update message
        message = {
            "stock_id": str(uuid.uuid4()),
            "order_id": order_id,
            "stock_status": stock_status,
        }

        # Send message to Kafka topic
        self.producer.send("stock-processed", value=message)
        self.producer.flush()

        print(f"Sent stock update message: {message}")
