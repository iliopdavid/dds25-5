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
                queue=queue, on_message_callback=self.handle_message, auto_ack=True
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
        except Exception as e:
            app.logger.error(f"Error processing message: {e}")

    def process_payment(self, payment_data):
        from app import get_user_from_db, app

        order_id = payment_data.get("order_id")
        user_id = payment_data.get("user_id")
        amount = payment_data.get("total_amount")

        try:
            user_entry = get_user_from_db(user_id)

            # Check credit before proceeding
            if user_entry.credit < int(amount):
                app.logger.debug(
                    f"Credit for user {user_id} insufficient. Payment failed."
                )
                self.send_payment_processed_event(order_id, user_id, "FAILURE", amount)
                return {
                    "status": "failure",
                    "message": "Insufficient credit for user!",
                }

            # Deduct credit
            user_entry.credit -= int(amount)

            # Update Redis with new credit value
            self.redis_client.set(user_id, msgpack.encode(user_entry))

            app.logger.debug(
                f"Credit for user {user_id} reduced by {amount}. New credit: {user_entry.credit}"
            )

            # Send success event to RabbitMQ
            self.send_payment_processed_event(order_id, user_id, "SUCCESS", amount)
            return {"status": "success", "message": "User credit updated successfully"}

        except Exception as e:
            app.logger.error(f"Error processing payment: {e}")
            self.send_payment_processed_event(order_id, user_id, "FAILURE", amount)
            return {"status": "failure", "message": str(e)}

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
        self.rollback_credit(user_id, amount)

    def rollback_credit(self, user_id, amount):
        from app import get_user_from_db, app

        try:
            user_entry = get_user_from_db(user_id)
            user_entry.credit += int(amount)

            # Update Redis with the rolled-back credit
            self.redis_client.set(user_id, msgpack.encode(user_entry))

            app.logger.debug(
                f"Credit for user {user_id} rolled back by {amount}. New credit: {user_entry.credit}"
            )
        except Exception as e:
            app.logger.error(f"Error rolling back credit for {user_id}: {str(e)}")

    def cleanup(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
