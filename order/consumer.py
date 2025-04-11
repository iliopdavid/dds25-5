import json
import asyncio
import aio_pika
from msgspec import msgpack
from quart import current_app


class OrderConsumer:
    def __init__(self, db):
        self.redis_client = db
        self.queue_names = ["order_queue"]
        self.connection = None
        self.channel = None
        self.producer = None

    async def init(self):
        from app import app

        try:
            self.connection = await aio_pika.connect_robust(
                "amqp://guest:guest@rabbitmq/"
            )
            self.channel = await self.connection.channel()

            # Ensure the exchanges exist
            stock_exchange = await self.channel.declare_exchange(
                "stock.exchange", aio_pika.ExchangeType.DIRECT, durable=True
            )
            payment_exchange = await self.channel.declare_exchange(
                "payment.exchange", aio_pika.ExchangeType.DIRECT, durable=True
            )

            # Setup queues and bindings
            for queue_name in self.queue_names:
                queue = await self.channel.declare_queue(queue_name)

                # Bind stock and payment processing events
                await queue.bind(stock_exchange, routing_key="stock.order.processed")
                await queue.bind(
                    payment_exchange, routing_key="payment.order.rollbacked"
                )
                await queue.bind(payment_exchange, routing_key="payment.order.failed")

            app.logger.info("Successfully connected to RabbitMQ and set up consumer")

            # self.producer = OrderProducer()
            # await self.producer.init()

        except Exception as e:
            app.logger.error(f"Failed to connect to RabbitMQ: {e}")
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            self.connection = None
            self.channel = None

    async def _ensure_connection(self):
        from app import app

        if not self.connection or self.connection.is_closed:
            app.logger.warning("RabbitMQ connection closed. Reconnecting...")
            await self.init()

    async def consume_messages(self):
        from app import app

        await self._ensure_connection()

        if not self.connection or self.connection.is_closed:
            app.logger.error("Failed to establish RabbitMQ connection for consuming")
            return

        # Create consumer tasks for each queue
        tasks = []
        for queue_name in self.queue_names:
            queue = await self.channel.declare_queue(queue_name)
            tasks.append(self._consume_from_queue(queue))

        app.logger.info("Waiting for messages. To exit press CTRL+C")
        await asyncio.gather(*tasks)

    async def _consume_from_queue(self, queue):
        from app import app

        async with queue.iterator() as queue_iter:
            app.logger.info(f"Started consuming from queue: {queue.name}")
            async for message in queue_iter:
                async with message.process():
                    await self.handle_message(message)

    async def handle_message(self, message):
        from app import app

        try:
            body = message.body.decode()
            message_data = json.loads(body)
            topic = message.routing_key
            order_id = message_data.get("order_id")
            message_id = message_data.get("message_id")

            if await self.is_duplicate_message(message_id):
                app.logger.info(f"Duplicate message detected and skipped: {message_id}")
                return

            app.logger.debug(
                f"Message received with topic {topic} and content {message_data}"
            )

            if topic == "stock.order.processed":
                await self.complete_order(order_id)
            elif topic == "payment.order.rollbacked":
                await self.failed_order(order_id)
            elif topic == "payment.order.failed":
                app.logger.debug("dont think about it")
                await self.failed_order(order_id)

        except json.JSONDecodeError as e:
            app.logger.error(f"Failed to decode message: {e}")
        except Exception as e:
            app.logger.error(f"Error processing message: {e}")

    async def is_duplicate_message(self, message_id, expiration_seconds=3600):
        key = f"processed_msg:{message_id}"

        result = await self.redis_client.setnx(key, 1)
        if result == 1:
            await self.redis_client.expire(key, expiration_seconds)
        return result == 0

    async def failed_order(self, order_id):
        from app import handle_rollback_complete

        await handle_rollback_complete(order_id)

    async def complete_order(self, order_id):
        from app import app, handle_checkout_complete

        try:
            # Lua script to update the order's paid status atomically
            complete_order_lua = """
                local order_id = KEYS[1]
                local order_data = redis.call("GET", order_id)

                if not order_data then
                    return {err = "order_not_found"}
                end

                local order = cmsgpack.unpack(order_data)
                order.paid = true

                -- Save the updated order back to Redis
                redis.call("SET", order_id, cmsgpack.pack(order))

                return {ok = "order_completed"}
            """

            # Run the script
            result = await self.redis_client.eval(
                complete_order_lua,
                1,
                order_id,
            )

            # Handle Lua script result
            if isinstance(result, dict) and result.get("err") == "order_not_found":
                app.logger.warning(f"No order found to complete: {order_id}")
                return {"status": "failure", "message": "Order not found"}

            app.logger.debug(f"Order {order_id} successfully completed.")

            await handle_checkout_complete(order_id)

            return {"status": "success", "message": "Order completed"}

        except Exception as e:
            app.logger.exception(f"Error completing order {order_id}: {str(e)}")
            return {"status": "failure", "message": f"Error completing order: {str(e)}"}

    async def get_order_from_db(self, order_id):
        from app import OrderValue

        entry = await self.redis_client.get(order_id)
        entry = msgpack.decode(entry, type=OrderValue) if entry else None
        return entry

    async def close(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            current_app.logger.info("RabbitMQ connection closed")


async def run_consumer(db):
    consumer = OrderConsumer(db)
    await consumer.init()

    try:
        await consumer.consume_messages()
    except KeyboardInterrupt:
        current_app.logger.info("Consumer stopping due to keyboard interrupt")
    finally:
        await consumer.close()
