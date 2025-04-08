import json
import pika


class OrderProducer:
    def __init__(self, max_retries=5, retry_delay=5):
        self.connection = None
        self.channel = None
        self._connect()

        self.channel.exchange_declare(
            exchange="order.exchange", exchange_type="topic", durable=True
        )

    def _connect(self):
        from app import app

        try:
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters("rabbitmq")
            )
            self.channel = self.connection.channel()
            self.channel.exchange_declare(
                exchange="order.exchange", exchange_type="topic", durable=True
            )
        except Exception as e:
            app.logger.error(f"Failed to connect to RabbitMQ: {e}")
            self.connection = None
            self.channel = None

    def _ensure_connection(self):
        from app import app

        if not self.connection or self.connection.is_closed:
            app.logger.warning("RabbitMQ connection lost. Reconnecting...")
            self._connect()

    def send_event(self, routing_key, message):
        from app import app

        if not self.connection or self.connection.is_closed:
            app.logger.error("RabbitMQ channel is closed. Reconnecting...")
            self._connect()

        try:
            # Create a new channel for this operation
            message_body = json.dumps(message)
            self.channel.basic_publish(
                exchange="order.exchange",
                routing_key=routing_key,
                body=message_body,
            )
            app.logger.debug(
                f"Message sent to exchange 'order.exchange' with key '{routing_key}': {message_body}"
            )
        except Exception as e:
            app.logger.error(f"Error sending event to RabbitMQ: {e}")
            raise

    # Notify that the order checkout has been placed.
    def send_checkout_called(self, order_id, user_id, total_amount, items):
        message = {
            "order_id": order_id,
            "user_id": user_id,
            "total_amount": total_amount,
            "items": items,
        }
        self.send_event("order.checkout", message)

    # Send an event notifying other services that checkout has been completed
    def send_checkout_completed(self, order_id):
        message = {"order_id": order_id, "status": "COMPLETED"}
        self.send_event("order.completed", message)

    # Send an event notifying other services that checkout has failed
    def send_checkout_failed(self, order_id, reason):
        message = {"order_id": order_id, "status": "FAILED", "reason": reason}
        self.send_event("order.failed", message)

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
