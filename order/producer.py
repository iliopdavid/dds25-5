import time
from kafka import KafkaProducer
import json


class OrderProducer:

    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers=["kafka:9092"],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            retries=5,
            request_timeout_ms=60000,  # Increase the timeout
            batch_size=16384,  # Increase batch size if necessary
            linger_ms=5,
        )

    def send_event(self, topic, key, value):
        from app import app

        app.logger.debug(
            f"Attempting to send event to topic '{topic}' with key '{key}' and value '{value}'"
        )

        try:
            app.logger.debug(f"Sending message to Kafka topic '{topic}'")
            self.producer.send(topic, key=key.encode("utf-8"), value=value)
            app.logger.debug(f"Message sent to Kafka. Waiting for flush...")
            # this flushing does not work
            self.producer.flush(timeout=30)
            app.logger.debug(f"Flush complete.")

        except Exception as e:
            # Log any exception that occurs during the send/flush process
            app.logger.error(f"Error sending event to Kafka: {e}")
            raise  # Optionally re-raise the exception if you want to propagate it

        app.logger.debug(f"Event successfully sent to topic '{topic}'")

    def send_order_created(self, order_id, user_id, total_amount):
        message = {
            "order_id": order_id,
            "user_id": user_id,
            "total_amount": total_amount,
        }
        self.send_event("orders", order_id, message)

    def send_order_completed(self, order_id):
        message = {"order_id": order_id, "status": "COMPLETED"}
        self.send_event("order-status", order_id, message)

    def send_order_failed(self, order_id, reason):
        message = {"order_id": order_id, "status": "FAILED", "reason": reason}
        self.send_event("order-status", order_id, message)
