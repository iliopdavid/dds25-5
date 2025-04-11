import json
import uuid
import aio_pika
from quart import current_app


class OrderProducer:
    def __init__(self):
        self.connection = None
        self.channel = None

    async def init(self):
        from app import app

        try:
            self.connection = await aio_pika.connect_robust(
                "amqp://guest:guest@rabbitmq/"
            )
            self.channel = await self.connection.channel()
            self.exchange = await self.channel.declare_exchange(
                "order.exchange", aio_pika.ExchangeType.TOPIC, durable=True
            )
            app.logger.info("Successfully connected to RabbitMQ")
        except Exception as e:
            app.logger.error(f"Failed to connect to RabbitMQ: {e}")

    async def send_event(self, routing_key, message):
        from app import app

        if not self.connection or self.connection.is_closed:
            app.logger.warning("RabbitMQ connection lost. Reconnecting...")
            await self.init()

        try:
            message_body = json.dumps(message)

            # Publish the message asynchronously
            await self.exchange.publish(
                aio_pika.Message(body=message_body.encode()),
                routing_key=routing_key,
            )
            app.logger.debug(
                f"Message sent to exchange 'order.exchange' with key '{routing_key}': {message_body}"
            )
        except Exception as e:
            error_context = (
                f"Error sending event with routing key '{routing_key}' to RabbitMQ."
            )
            app.logger.exception(error_context)
            raise

    async def send_checkout_called(self, order_id, user_id, total_amount, items):
        message = {
            "message_id": str(uuid.uuid4()),
            "order_id": order_id,
            "user_id": user_id,
            "total_amount": total_amount,
            "items": items,
        }
        await self.send_event("order.payment.checkout", message)

    async def close(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            current_app.logger.info("RabbitMQ connection closed")
