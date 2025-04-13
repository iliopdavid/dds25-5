import json
import uuid
import aio_pika
import asyncio
from msgspec import msgpack
from quart import current_app


class StockConsumer:
    def __init__(self, db):
        self.redis_client = db
        self.queues = ["stock_queue"]
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

            # Ensure the exchange exists
            payment_exchange = await self.channel.declare_exchange(
                "payment.exchange", aio_pika.ExchangeType.DIRECT, durable=True
            )

            # Declare and bind queues
            for queue_name in self.queues:
                queue = await self.channel.declare_queue(queue_name)
                await queue.bind(
                    payment_exchange, routing_key="payment.stock.processed"
                )

            app.logger.info("Successfully connected to RabbitMQ (StockConsumer)")

            # Initialize the producer
            from producer import StockProducer

            self.producer = StockProducer()
            await self.producer.init()

        except Exception as e:
            app.logger.error(f"Failed to connect to RabbitMQ (StockConsumer): {e}")
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
        for queue_name in self.queues:
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

    async def is_duplicate_message(self, message_id, expiration_seconds=3600):
        key = f"processed_msg:{message_id}"
        result = await self.redis_client.setnx(key, 1)
        if result == 1:
            await self.redis_client.expire(key, expiration_seconds)
        return result == 0

    async def handle_message(self, message):
        from app import app

        app.logger.debug(
            f"Stock consumer received message with routing key {message.routing_key} and content {message.body}"
        )

        try:
            message_data = json.loads(message.body.decode())
            message_id = message_data.get("message_id")

            if await self.is_duplicate_message(message_id):
                app.logger.info(f"Duplicate message detected and skipped: {message_id}")
                return

            if message.routing_key == "payment.stock.processed":
                await self.process_stock(message_data)
        except Exception as e:
            app.logger.error(f"Error processing message: {e}")

    async def process_stock(self, stock_data):
        from app import app, log

        app.logger.debug(f"Consuming event {stock_data}")

        order_id = stock_data.get("order_id")
        user_id = stock_data.get("user_id")
        items = stock_data.get("items")
        total_amount = stock_data.get("total_amount")

        try:
            process_stock_lua = """
                local items = cmsgpack.unpack(ARGV[1])
                local errors = {}
                local rollback_data = {}

                for item_id, quantity in pairs(items) do
                    local item_data = redis.call("GET", item_id)
                    if not item_data then
                        errors[item_id] = "item_not_found"
                    else
                        local item = cmsgpack.unpack(item_data)
                        if item.stock < quantity then
                            errors[item_id] = "insufficient_stock"
                        else
                            rollback_data[item_id] = item.stock
                            item.stock = item.stock - quantity
                            redis.call("SET", item_id, cmsgpack.pack(item))
                        end
                    end
                end

                if next(errors) then
                    for item_id, prev_stock in pairs(rollback_data) do
                        local item_data = redis.call("GET", item_id)
                        local item = cmsgpack.unpack(item_data)
                        item.stock = prev_stock
                        redis.call("SET", item_id, cmsgpack.pack(item))
                    end
                    return cmsgpack.pack(errors)
                end

                return nil
            """

            result = await self.redis_client.eval(
                process_stock_lua,
                len(items),
                *[str(item_id) for item_id in items],
                msgpack.encode(items),
            )

            if result:
                errors = msgpack.decode(result)
                if errors:
                    app.logger.debug("Stock check failed: " + str(errors))
                    await self.send_stock_failure_event(order_id, user_id, total_amount)
                    return

            # ADDED
            # for item_id, quantity in items.items():
            #     try:
            #         app.logger.debug(
            #             f"Processing item_id: {item_id}, quantity: {quantity}"
            #         )

            #         item_bytes = await self.redis_client.get(item_id)
            #         if item_bytes:
            #             app.logger.debug(
            #                 f"Retrieved item_bytes for item_id {item_id}: {item_bytes}"
            #             )
            #             app.logger.debug("You are about to write to log")

            #             # Log the new state for redo logging
            #             log({item_id: item_bytes})
            #             app.logger.debug(
            #                 f"Redo log successfully written for item_id {item_id}"
            #             )
            #         else:
            #             app.logger.warning(
            #                 f"No item found in Redis for item_id: {item_id}"
            #             )
            #     except Exception as e:
            #         app.logger.error(
            #             f"Error processing item_id {item_id}: {e}", exc_info=True
            #         )

            app.logger.debug(f"Stock reduced for order {order_id}")
            await self.send_stock_processed_event(order_id)

        except Exception as e:
            app.logger.error(f"Error processing stock for order {order_id}: {e}")
            await self.send_stock_failure_event(order_id, user_id, total_amount)

    async def send_stock_processed_event(self, order_id):
        from app import app

        event_data = {
            "message_id": str(uuid.uuid4()),
            "order_id": order_id,
            "status": "SUCCESS",
        }

        # app.logger.info(f"Stock processed for order {order_id}")
        await self.producer.send_message("stock.order.processed", event_data)

    async def send_stock_failure_event(self, order_id, user_id, total_amount):
        from app import app

        event_data = {
            "message_id": str(uuid.uuid4()),
            "order_id": order_id,
            "total_amount": total_amount,
            "user_id": user_id,
        }
        # app.logger.info(f"Stock rollback message sent for order {order_id}")
        await self.producer.send_message("stock.payment.rollback", event_data)

    async def close(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            current_app.logger.info("StockConsumer: RabbitMQ connection closed")


async def run_stock_consumer(db):
    consumer = StockConsumer(db)
    await consumer.init()

    try:
        await consumer.consume_messages()
    except KeyboardInterrupt:
        current_app.logger.info("Stock consumer stopping due to keyboard interrupt")
    finally:
        await consumer.close()
