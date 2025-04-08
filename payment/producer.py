import pika
import json


class PaymentProducer:
    def __init__(self):
        # Connect to RabbitMQ server
        self.connection = None
        self.channel = None
        self._connect()

        # Declare the exchange and queue
        self.channel.exchange_declare(
            exchange="payment.exchange", exchange_type="direct", durable=True
        )

    def _connect(self):
        from app import app

        try:
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters("rabbitmq")
            )
            self.channel = self.connection.channel()
        except Exception as e:
            app.logger.error(f"Failed to connect to RabbitMQ: {e}")
            self.connection = None
            self.channel = None

    def _ensure_connection(self):
        from app import app

        if not self.connection or self.connection.is_closed:
            app.logger.warning("RabbitMQ connection closed. Reconnecting...")
            self._connect()

    # Send message to RabbitMQ exchange
    def send_message(self, key, event_data):
        from app import app

        self._ensure_connection()

        if not self.channel:
            app.logger.error("RabbitMQ channel unavailable. Message not sent.")
            return

        try:
            # Convert data to JSON and send to the RabbitMQ exchange
            message = json.dumps(event_data)
            self.channel.basic_publish(
                exchange="payment.exchange",
                routing_key=key,
                body=message,
                properties=pika.BasicProperties(content_type="application/json"),
            )

            app.logger.debug(
                f"Message sent to exchange 'payment.exchange' with key '{key}': {message}"
            )
        except Exception as e:
            app.logger.error(f"Error sending message to RabbitMQ: {str(e)}")

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
