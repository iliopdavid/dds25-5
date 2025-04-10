import json
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
                exchange="order.exchange", queue=queue, routing_key="order.checkout"
            )
            self.channel.queue_bind(
                exchange="order.exchange", queue=queue, routing_key="order.payment.#"
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

            if method.routing_key == "order.checkout":
                self.process_payment(message)
            elif method.routing_key == "order.payment.rollback":
                self.handle_payment_rollback(message)

            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            app.logger.error(f"Error processing message: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def send_payment_processed_event(self, order_id, user_id, status, total_amount):
        event_data = {
            "order_id": order_id,
            "user_id": user_id,
            "status": status,
            "total_amount": total_amount,
        }
        self.producer.send_message("payment.processed", event_data)

    def handle_payment_rollback(self, stock_failure_data):
        user_id = stock_failure_data.get("user_id")
        amount = stock_failure_data.get("total_amount")
        order_id = stock_failure_data.get("order_id")

        if not all([user_id, amount, order_id]):
            from app import app

            app.logger.error(
                f"Invalid rollback data: missing required fields - {stock_failure_data}"
            )
            return

        self.rollback_credit(user_id, amount, order_id)

    def process_payment(self, payment_data):
        from app import app

        order_id = payment_data.get("order_id")
        user_id = payment_data.get("user_id")
        amount = payment_data.get("total_amount")

        if not all([order_id, user_id, amount]):
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

            if result == "insufficient_credit":
                app.logger.debug(
                    f"Insufficient credit for user {user_id}. Payment failed."
                )
                self.send_payment_processed_event(order_id, user_id, "FAILURE", amount)
                return {"status": "FAILURE", "reason": "insufficient_credit"}
            elif result == "user_not_found":
                app.logger.debug(f"User {user_id} not found. Payment failed.")
                self.send_payment_processed_event(order_id, user_id, "FAILURE", amount)
                return {"status": "FAILURE", "reason": "user_not_found"}
            elif result == "success":
                app.logger.debug(f"Credit for user {user_id} reduced by {amount}.")
                self.send_payment_processed_event(order_id, user_id, "SUCCESS", amount)
                return {"status": "SUCCESS"}
            else:
                app.logger.error(f"Unexpected result from Redis: {result}")
                self.send_payment_processed_event(order_id, user_id, "FAILURE", amount)
                return {"status": "FAILURE", "reason": "unexpected_result"}

        except Exception as e:
            app.logger.error(f"Error processing payment: {e}")
            self.send_payment_processed_event(order_id, user_id, "FAILURE", amount)
            return {"status": "FAILURE", "reason": "exception"}

    def rollback_credit(self, user_id, amount, order_id):
        from app import app

        if not all([user_id, amount, order_id]):
            app.logger.error("Missing required rollback data")
            return {"status": "FAILURE", "reason": "invalid_data"}

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

            if result == "user_not_found":
                app.logger.warning(
                    f"Rollback failed: user not found for user {user_id}, order {order_id}"
                )
                self.producer.send_message(
                    "payment.rollback.failed",
                    {
                        "order_id": order_id,
                        "user_id": user_id,
                        "amount": amount,
                        "status": "FAILURE",
                        "error": "user_not_found",
                    },
                )
                return {"status": "FAILURE", "reason": "user_not_found"}
            elif result == "success":
                app.logger.info(
                    f"Credit rollback successful for user {user_id}, order {order_id}. Amount: {amount}"
                )
                self.producer.send_message(
                    "payment.rollback.completed",
                    {
                        "order_id": order_id,
                        "user_id": user_id,
                        "amount": amount,
                        "status": "SUCCESS",
                    },
                )
                return {"status": "SUCCESS"}
            else:
                app.logger.error(f"Unexpected result from Redis: {result}")
                self.producer.send_message(
                    "payment.rollback.failed",
                    {
                        "order_id": order_id,
                        "user_id": user_id,
                        "amount": amount,
                        "status": "FAILURE",
                        "error": "unexpected_result",
                    },
                )
                return {"status": "FAILURE", "reason": "unexpected_result"}

        except Exception as e:
            app.logger.error(
                f"Error rolling back credit for user {user_id}, order {order_id}: {str(e)}"
            )
            self.producer.send_message(
                "payment.rollback.failed",
                {
                    "order_id": order_id,
                    "user_id": user_id,
                    "amount": amount,
                    "status": "FAILURE",
                    "error": str(e),
                },
            )
            return {"status": "FAILURE", "reason": "exception"}

    def cleanup(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
