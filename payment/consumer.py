import pika
import json
from producer import PaymentProducer
from msgspec import msgpack


class PaymentConsumer:
    def __init__(self):
        self.queue_names = ["payment_queue"]
        self.connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
        self.channel = self.connection.channel()

        self.producer = PaymentProducer()

        # make sure that the exchange exists
        self.channel.exchange_declare(exchange="order.exchange", exchange_type="topic")

        for queue in self.queue_names:
            self.channel.queue_declare(queue=queue)
            # for broadcasting event
            self.channel.queue_bind(
                exchange="order.exchange", queue=queue, routing_key="order.checkout"
            )
            # for payment specific event
            self.channel.queue_bind(
                exchange="order.exchange",
                queue=queue,
                routing_key="order.payment.#",
            )

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
        message = json.loads(body)
        if method.routing_key == "order.checkout":
            self.process_payment(message)
        elif method.routing_key == "stock.failure":
            self.handle_stock_failure(message)

    def process_payment(self, payment_data):
        from app import get_user_from_db, log, db, app

        app.logger.debug(f"Consuming event {payment_data}")

        order_id = payment_data.get("order_id")
        user_id = payment_data.get("user_id")
        amount = payment_data.get("total_amount")

        try:
            user_entry = get_user_from_db(user_id)
            user_entry.credit -= int(amount)
            value = msgpack.encode(user_entry)

            if user_entry.credit < 0:
                app.logger.debug(
                    f"credit status of user with id {user_id} would be reduced to below 0"
                )
                self.send_payment_processed_event(user_id, "FAILURE", amount)
                return {
                    "status": "failure",
                    "message": "User credit cannot get reduced below zero!",
                }

            log({user_id: value})
            db.set(user_id, value)
            app.logger.debug(
                f"credit status of user with id {user_id} reduced by {amount} to {user_entry.credit}"
            )
            self.send_payment_processed_event(order_id, user_id, "SUCCESS", amount)
            return {"status": "success", "message": "User credit updated successfully"}

        except Exception as e:
            error_message = str(e)
            log({"error": error_message.encode("utf-8")})
            self.send_payment_processed_event(order_id, user_id, "FAILURE", amount)
            return {"status": "failure", "message": error_message}

    def send_payment_processed_event(self, order_id, user_id, status, total_amount):
        event_data = {
            "order_id": order_id,
            "user_id": user_id,
            "status": status,
            "total_amount": total_amount,
        }
        self.producer.send_message("payment.processed", event_data)

    def handle_stock_failure(self, stock_failure_data):
        from app import app

        user_id = stock_failure_data.get("user_id")
        amount = stock_failure_data.get("total_amount")
        self.rollback_credit(user_id, amount)
        app.logger.debug(
            f"Stock failure event received. Rolled back credit for user {user_id}."
        )

    def rollback_credit(self, user_id, amount):
        from app import get_user_from_db, db, log, app

        try:
            user_entry = get_user_from_db(user_id)
            user_entry.credit += int(amount)
            log({user_id: amount})
            app.logger.debug(
                {"rollback": f"Credit for {user_id} rolled back. Amount: {amount}"}
            )
            db.set(user_id, msgpack.encode(user_entry))

        except Exception as e:
            log({"error": f"Error rolling back credit for {user_id}: {str(e)}"})
