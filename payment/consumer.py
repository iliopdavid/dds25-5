import json
import uuid
import aio_pika
import asyncio
from msgspec import msgpack
from quart import current_app


class PaymentConsumer:
    def __init__(self, db):
        self.redis_client = db
        self.queue_names = ["payment_queue"]
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

            # Declare exchanges to prevent binding before initialization
            order_exchange = await self.channel.declare_exchange(
                "order.exchange", aio_pika.ExchangeType.TOPIC, durable=True
            )
            stock_exchange = await self.channel.declare_exchange(
                "stock.exchange", aio_pika.ExchangeType.DIRECT, durable=True
            )

            await self.channel.set_qos(prefetch_count=10)

            # Declare and bind queues
            for queue_name in self.queue_names:
                queue = await self.channel.declare_queue(queue_name)

                # Bind to order exchange
                await queue.bind(order_exchange, routing_key="order.payment.#")

                # Bind to stock exchange
                await queue.bind(stock_exchange, routing_key="stock.payment.rollback")

            app.logger.info("Successfully connected to RabbitMQ (PaymentConsumer)")

            # Initialize the producer
            from producer import PaymentProducer

            self.producer = PaymentProducer()
            await self.producer.init()

        except Exception as e:
            app.logger.error(f"Failed to connect to RabbitMQ (PaymentConsumer): {e}")
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

    async def is_duplicate_message(self, message_id, expiration_seconds=3600):
        key = f"processed_msg:{message_id}"

        # For async Redis client
        result = await self.redis_client.setnx(key, 1)
        if result == 1:
            await self.redis_client.expire(key, expiration_seconds)
        return result == 0

    async def handle_message(self, message):
        from app import app

        app.logger.debug(
            f"Payment consumer received message with routing key {message.routing_key} and content {message.body}"
        )

        try:
            message_data = json.loads(message.body.decode())
            message_id = message_data.get("message_id")

            if await self.is_duplicate_message(message_id):
                app.logger.info(f"Duplicate message detected and skipped: {message_id}")
                return

            if message.routing_key == "order.payment.checkout":
                await self.process_payment(message_data)
            elif message.routing_key == "stock.payment.rollback":
                await self.handle_payment_rollback(message_data)
        except Exception as e:
            app.logger.error(f"Error processing message: {e}")

    async def send_payment_processed_event(
        self, order_id, items, total_amount, user_id
    ):
        event_data = {
            "message_id": str(uuid.uuid4()),
            "order_id": order_id,
            "items": items,
            "total_amount": total_amount,
            "user_id": user_id,
        }
        await self.producer.send_message("payment.stock.processed", event_data)

    async def send_payment_failed_event(self, order_id):
        event_data = {
            "message_id": str(uuid.uuid4()),
            "order_id": order_id,
        }
        await self.producer.send_message("payment.order.failed", event_data)

    async def process_payment(self, payment_data):
        from app import app, log

        order_id = payment_data.get("order_id")
        user_id = payment_data.get("user_id")
        amount = payment_data.get("total_amount")
        items = payment_data.get("items")

        if not all([order_id, user_id, amount, items]):
            app.logger.error(f"Missing required payment data: {payment_data}")
            return {"status": "FAILURE", "reason": "invalid_data"}

        try:
            deduct_credit_lua = """
                local user_key = KEYS[1]
                local amount = tonumber(ARGV[1])
                
                local encoded = redis.call("GET", user_key)
                if not encoded then
                    return redis.status_reply("user_not_found")
                end
                
                local msgpack = cmsgpack.unpack(encoded)
                if msgpack.credit < amount then
                    return redis.status_reply("insufficient_credit")
                end
                
                -- Update credit
                msgpack.credit = msgpack.credit - amount
                redis.call("SET", user_key, cmsgpack.pack(msgpack))
                
                return redis.status_reply("success")
            """

            result = await self.redis_client.eval(
                deduct_credit_lua,
                1,
                str(user_id),
                amount,
            )

            # Convert bytes to string if needed
            if isinstance(result, bytes):
                result = result.decode("utf-8")

            if result == "success":
                app.logger.info(
                    f"Credit for user {user_id} successfully reduced by {amount}."
                )

                # # ADDED
                # user_bytes = await self.redis_client.get(str(user_id))
                # if user_bytes:
                #     log({user_id: user_bytes})

                await self.send_payment_processed_event(
                    order_id, items, amount, user_id
                )
                return {"status": "SUCCESS"}
            else:
                await self.send_payment_failed_event(order_id)
                app.logger.debug(f"Deducting credit failed")
                return {"status": "FAILURE"}

        except Exception as e:
            await self.send_payment_failed_event(order_id)
            app.logger.error(f"Error processing payment: {e}")
            return {"status": "FAILURE"}

    async def handle_payment_rollback(self, stock_failure_data):
        user_id = stock_failure_data.get("user_id")
        amount = stock_failure_data.get("total_amount")
        order_id = stock_failure_data.get("order_id")

        if not all([user_id, amount, order_id]):
            from app import app

            app.logger.error(
                f"Invalid rollback data: missing required fields - {stock_failure_data}"
            )
            return {"status": "FAILURE"}

        await self.rollback_credit(user_id, amount, order_id)

    async def rollback_credit(self, user_id, amount, order_id):
        from app import app, log

        if not all([user_id, amount, order_id]):
            app.logger.error("Missing required rollback data")
            return {"status": "FAILURE"}

        try:
            rollback_credit_lua = """
                local user_key = KEYS[1]
                local amount = tonumber(ARGV[1])
                
                local user_data = redis.call("GET", user_key)
                if not user_data then
                    return redis.status_reply("user_not_found")
                end
                
                local user = cmsgpack.unpack(user_data)
                
                -- Rollback the user's credit by adding the specified amount
                user.credit = user.credit + amount
                
                -- Update the user data in Redis
                redis.call("SET", user_key, cmsgpack.pack(user))
                
                return redis.status_reply("success")
            """

            result = await self.redis_client.eval(
                rollback_credit_lua, 1, str(user_id), amount
            )

            # Convert bytes to string if needed
            if isinstance(result, bytes):
                result = result.decode("utf-8")

            if result == "success":
                app.logger.info(
                    f"Credit rollback successful for user {user_id}, order {order_id}. Amount: {amount}"
                )
                # # ADDED
                # user_bytes = await self.redis_client.get(str(user_id))
                # if user_bytes:
                #     log({user_id: user_bytes})

                await self.producer.send_message(
                    "payment.order.rollbacked",
                    {
                        "message_id": str(uuid.uuid4()),
                        "order_id": order_id,
                        "user_id": user_id,
                        "amount": amount,
                    },
                )
                return {"status": "SUCCESS"}
            else:
                app.logger.debug(
                    f"There was an issue with rolling back user credit {result}"
                )
                await self.producer.send_message(
                    "payment.rollback.failed",
                    {
                        "message_id": str(uuid.uuid4()),
                        "order_id": order_id,
                        "user_id": user_id,
                        "amount": amount,
                    },
                )
                return {"status": "FAILURE"}

        except Exception as e:
            app.logger.error(
                f"Error rolling back credit for user {user_id}, order {order_id}: {str(e)}"
            )
            await self.producer.send_message(
                "payment.rollback.failed",
                {
                    "message_id": str(uuid.uuid4()),
                    "order_id": order_id,
                    "user_id": user_id,
                    "amount": amount,
                },
            )
            return {"status": "FAILURE", "reason": "exception"}

    async def close(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            current_app.logger.info("PaymentConsumer: RabbitMQ connection closed")


async def run_payment_consumer(db):
    consumer = PaymentConsumer(db)
    await consumer.init()

    try:
        await consumer.consume_messages()
    except KeyboardInterrupt:
        current_app.logger.info("Payment consumer stopping due to keyboard interrupt")
    finally:
        await consumer.close()
