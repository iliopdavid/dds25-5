import json
import pika
from rabbitmq_connection import RabbitMQConnection


class OrderProducer:
    def __init__(self, max_retries=5, retry_delay=5):
        from app import app

        app.logger.debug("OrderProducer initialized and ready to send messages.")

        self.rabbitmq = RabbitMQConnection(
            max_retries=max_retries, retry_delay=retry_delay
        )

        # Declare all necessary exchanges
        self.rabbitmq.declare_exchanges(
            {
                "orders": "direct",
                "order-status": "direct",
                "order-created-payment": "direct",
                "order-created-stock": "direct",
            }
        )

    def send_event(self, exchange, routing_key, message):
        """Send a message to a specified exchange with retry logic."""
        from app import app

        if not self.rabbitmq.channel or self.rabbitmq.channel.is_closed:
            app.logger.error("RabbitMQ channel is closed. Reconnecting...")
            self.rabbitmq._connect()

        try:
            # Create a new channel for this operation
            with self.rabbitmq.connection.channel() as channel:
                message_body = json.dumps(message)
                channel.basic_publish(
                    exchange=exchange,
                    routing_key=routing_key,
                    body=message_body,
                    properties=pika.BasicProperties(
                        delivery_mode=2  # Make message persistent
                    ),
                )
                app.logger.debug(
                    f"Message sent to exchange '{exchange}' with key '{routing_key}': {message_body}"
                )
        except Exception as e:
            app.logger.error(f"Error sending event to RabbitMQ: {e}")
            raise

    def send_order_created(self, order_id, user_id, total_amount):
        """Notify other services that an order has been created."""
        message = {
            "order_id": order_id,
            "user_id": user_id,
            "total_amount": total_amount,
        }
        self.send_event("orders", "order.created", message)

    def send_order_completed(self, order_id):
        """Notify that an order is completed."""
        message = {"order_id": order_id, "status": "COMPLETED"}
        self.send_event("order-status", "order.completed", message)

    def send_order_failed(self, order_id, reason):
        """Notify that an order has failed."""
        message = {"order_id": order_id, "status": "FAILED", "reason": reason}
        self.send_event("order-status", "order.failed", message)

    def close_connection(self):
        """Close the RabbitMQ connection safely."""
        from app import app

        try:
            self.rabbitmq.close()
            app.logger.debug("RabbitMQ connection closed successfully.")
        except Exception as e:
            app.logger.error(f"Error closing RabbitMQ connection: {e}")
