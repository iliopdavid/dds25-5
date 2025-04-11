import json
import aio_pika
from quart import current_app


class StockProducer:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.exchange = None

    async def init(self):
        from app import app

        try:
            self.connection = await aio_pika.connect_robust(
                "amqp://guest:guest@rabbitmq/"
            )
            self.channel = await self.connection.channel()

            # Declare the exchange
            self.exchange = await self.channel.declare_exchange(
                "stock.exchange", aio_pika.ExchangeType.DIRECT, durable=True
            )

            app.logger.info("Successfully connected to RabbitMQ (StockProducer)")
        except Exception as e:
            app.logger.error(f"Failed to connect to RabbitMQ (StockProducer): {e}")
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            self.connection = None
            self.channel = None
            self.exchange = None

    async def send_message(self, routing_key, event_data):
        from app import app

        if not self.connection or self.connection.is_closed:
            app.logger.warning("RabbitMQ connection lost. Reconnecting...")
            await self.init()

        if not self.exchange:
            app.logger.error("RabbitMQ exchange unavailable. Message not sent.")
            return

        try:
            message_body = json.dumps(event_data)

            # Create message with content_type
            message = aio_pika.Message(
                body=message_body.encode(), content_type="application/json"
            )

            # Publish the message asynchronously
            await self.exchange.publish(
                message,
                routing_key=routing_key,
            )

            app.logger.debug(
                f"Message sent to exchange 'stock.exchange' with key '{routing_key}': {message_body}"
            )
        except Exception as e:
            error_context = (
                f"Error sending message with routing key '{routing_key}' to RabbitMQ."
            )
            app.logger.exception(error_context)
            raise

    async def close(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            current_app.logger.info("StockProducer: RabbitMQ connection closed")
