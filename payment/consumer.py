import json
import uuid
import pika
from producer import PaymentProducer
from msgspec import msgpack


class PaymentConsumer:
    def __init__(self, db):
        self.redis_client = db
        self.queue_names = ["payment_queue"]
        self.connection = None
        self.channel = None
        self.producer = PaymentProducer()

        # Initialize RabbitMQ connection
        self._connect()

        # Ensure the exchange exists
        self.channel.exchange_declare(
            exchange="order.exchange", exchange_type="topic", durable=True
        )

        self.channel.basic_qos(prefetch_count=10)

        # Declare and bind queues
        for queue in self.queue_names:
            self.channel.queue_declare(queue=queue)

            self.channel.queue_bind(
                exchange="order.exchange", queue=queue, routing_key="order.payment.#"
            )
            self.channel.queue_bind(
                exchange="stock.exchange",
                queue=queue,
                routing_key="stock.payment.rollback",
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

    def consume_messages(self):
        from app import app

        for queue in self.queue_names:
            self.channel.basic_consume(
                queue=queue, on_message_callback=self.handle_message, auto_ack=False
            )

        app.logger.info("Waiting for messages. To exit press CTRL+C")
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            app.logger.info("Stopping consumer...")
            self.cleanup()

    def handle_message(self, ch, method, properties, body):
        from app import app

        app.logger.debug(
            f"Payment consumer received messaged with routing key {method.routing_key} and content {body}"
        )
        try:
            message = json.loads(body)
            message_id = message.get("message_id")

            if self.is_duplicate_message(message_id):
                app.logger.info(f"Duplicate message detected and skipped: {message_id}")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            if method.routing_key == "order.payment.checkout":
                self.process_payment(message)
            elif method.routing_key == "stock.payment.rollback":
                self.handle_payment_rollback(message)

            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            app.logger.error(f"Error processing message: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def send_payment_processed_event(self, order_id, items, total_amount, user_id):
        event_data = {
            "message_id": str(uuid.uuid4()),
            "order_id": order_id,
            "items": items,
            "total_amount": total_amount,
            "user_id": user_id,
        }
        self.producer.send_message("payment.stock.processed", event_data)

    def is_duplicate_message(self, message_id, expiration_seconds=3600):
        key = f"processed_msg:{message_id}"
        result = self.redis_client.setnx(key, 1)
        if result == 1:
            self.redis_client.expire(key, expiration_seconds)
        return result == 0

    def process_payment(self, payment_data):
        from app import app

        order_id = payment_data.get("order_id")
        user_id = payment_data.get("user_id")
        amount = payment_data.get("total_amount")
        items = payment_data.get("items")
        total_amount = payment_data.get("total_amount")

        if not all([order_id, user_id, amount, items]):
            app.logger.error("Missing required payment data")
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

            result = self.redis_client.eval(
                deduct_credit_lua,
                1,
                str(user_id),
                amount,
            )

            # Convert bytes to string if needed
            if isinstance(result, bytes):
                result = result.decode("utf-8")

            if result == "success":
                app.logger.debug(f"Credit for user {user_id} reduced by {amount}.")
                self.send_payment_processed_event(
                    order_id, items, total_amount, user_id
                )
                return {"status": "SUCCESS"}
            else:
                app.logger.error(f"There was an error with processing payment")
                # self.send_payment_processed_event(order_id, "FAILURE")
                return {"status": "FAILURE"}

        except Exception as e:
            app.logger.error(f"Error processing payment: {e}")
            # self.send_payment_processed_event(order_id, "FAILURE")
            return {"status": "FAILURE"}

    def handle_payment_rollback(self, stock_failure_data):
        user_id = stock_failure_data.get("user_id")
        amount = stock_failure_data.get("total_amount")
        order_id = stock_failure_data.get("order_id")

        if not all([user_id, amount, order_id]):
            from app import app

            app.logger.error(
                f"Invalid rollback data: missing required fields - {stock_failure_data}"
            )
            return {"status": "FAILURE"}

        self.rollback_credit(user_id, amount, order_id)

    def rollback_credit(self, user_id, amount, order_id):
        from app import app

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

            result = self.redis_client.eval(
                rollback_credit_lua, 1, str(user_id), amount
            )

            # Convert bytes to string if needed
            if isinstance(result, bytes):
                result = result.decode("utf-8")

            if result == "success":
                app.logger.info(
                    f"Credit rollback successful for user {user_id}, order {order_id}. Amount: {amount}"
                )
                self.producer.send_message(
                    "payment.rollback.completed",
                    {
                        "message_id": str(uuid.uuid4()),
                        "order_id": order_id,
                        "user_id": user_id,
                        "amount": amount,
                    },
                )
                return {"status": "SUCCESS"}
            else:
                app.logger.error(
                    f"There was an issue with rolling back user credit {result}"
                )
                self.producer.send_message(
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
            self.producer.send_message(
                "payment.rollback.failed",
                {
                    "message_id": str(uuid.uuid4()),
                    "order_id": order_id,
                    "user_id": user_id,
                    "amount": amount,
                },
            )
            return {"status": "FAILURE", "reason": "exception"}

    def cleanup(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
