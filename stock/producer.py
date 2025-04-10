import pika
import json


class StockProducer:
    def __init__(self):
        self.connection = None
        self.channel = None
        self._connect()

        # Declare the exchange
        self.channel.exchange_declare(
            exchange="stock.exchange", exchange_type="direct", durable=True
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

    def send_message(self, key, event_data):
        from app import app

        self._ensure_connection()

        if not self.channel:
            app.logger.error("RabbitMQ channel unavailable. Message not sent.")
            return

        try:
            message = json.dumps(event_data)
            self.channel.basic_publish(
                exchange="stock.exchange",
                routing_key=key,
                body=message,
                properties=pika.BasicProperties(content_type="application/json"),
            )

            app.logger.debug(
                f"Message sent to exchange 'stock.exchange' with key '{key}': {message}"
            )
        except Exception as e:
            app.logger.error(f"Error sending message to RabbitMQ: {str(e)}")

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
