import pika
import json
from producer import PaymentProducer
from msgspec import msgpack


class PaymentConsumer:
    def __init__(self):
        self.queue_names = ["order-created-payment", "stock-failure"]
        self.connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
        self.channel = self.connection.channel()

        for queue in self.queue_names:
            self.channel.queue_declare(queue=queue)

        self.producer = PaymentProducer()

    def consume_messages(self):
        for queue in self.queue_names:
            self.channel.basic_consume(
                queue=queue, on_message_callback=self.callback, auto_ack=True
            )
        self.channel.start_consuming()

    def callback(self, ch, method, properties, body):
        message = json.loads(body)
        if method.routing_key == "order-created-payment":
            self.process_payment(message)
        elif method.routing_key == "stock-failure":
            self.handle_stock_failure(message)

    def process_payment(self, payment_data):
        from app import get_user_from_db, log, db, app

        app.logger.debug(f"Consuming event", payment_data)

        user_id = payment_data.get("user_id")
        amount = payment_data.get("total_amount")

        try:
            user_entry = get_user_from_db(user_id)
            user_entry.credit -= int(amount)
            value = msgpack.encode(user_entry)

            if user_entry.credit < 0:
                self.send_payment_processed_event(user_id, "FAILURE", amount)
                return {
                    "status": "failure",
                    "message": "User credit cannot get reduced below zero!",
                }

            log({user_id: value})
            db.set(user_id, value)
            self.send_payment_processed_event(user_id, "SUCCESS", amount)
            return {"status": "success", "message": "User credit updated successfully"}

        except Exception as e:
            error_message = str(e)
            log({"error": error_message})
            self.send_payment_processed_event(user_id, "FAILURE", amount)
            return {"status": "failure", "message": error_message}

    def send_payment_processed_event(self, user_id, status, total_amount):
        event_data = {
            "user_id": user_id,
            "status": status,
            "total_amount": total_amount,
        }
        self.producer.send_message("payment-processed", event_data)

    def handle_stock_failure(self, stock_failure_data):
        user_id = stock_failure_data.get("user_id")
        amount = stock_failure_data.get("total_amount")
        self.rollback_credit(user_id, amount)
        print(f"Stock failure event received. Rolled back credit for user {user_id}.")

    def rollback_credit(self, user_id, amount):
        from app import get_user_from_db, db, log

        try:
            user_entry = get_user_from_db(user_id)
            user_entry.credit += int(amount)
            log({user_id: amount})
            print({"rollback": f"Credit for {user_id} rolled back. Amount: {amount}"})
            db.set(user_id, msgpack.encode(user_entry))

        except Exception as e:
            log({"error": f"Error rolling back credit for {user_id}: {str(e)}"})
