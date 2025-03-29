from kafka import KafkaConsumer
import json
from producer import PaymentProducer
from msgspec import msgpack


class PaymentConsumer:
    def __init__(self):
        self.topics = ["order-created-payment", "stock-failure"]
        self.group_id = "payment"
        self.consumer = KafkaConsumer(
            *self.topics,
            bootstrap_servers=["kafka:9092"],
            auto_offset_reset="earliest",
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
        )

        self.producer = PaymentProducer()

    def consume_messages(self):
        for message in self.consumer:
            if message.topic == "order-created-payment":
                self.process_payment(message.value)
            elif message.topic == "stock-failure":
                self.handle_stock_failure(message.value)

    def process_payment(self, payment_data):
        from app import get_user_from_db, log, db, app

        app.logger.debug(f"Consuming event", payment_data)

        # order_id = payment_data.get("order_id")
        user_id = payment_data.get("user_id")
        amount = payment_data.get("total_amount")

        try:
            user_entry = get_user_from_db(user_id)
            # update credit, serialize and update database
            user_entry.credit -= int(amount)
            # Encode user_entry
            value = msgpack.encode(user_entry)

            # Check if the user's credit is less than 0
            if user_entry.credit < 0:
                # If credit is less than 0, send a failure event and return
                self.send_payment_processed_event(user_id, "FAILURE", amount)
                return {
                    "status": "failure",
                    "message": "User credit cannot get reduced below zero!",
                }

            # Log the event
            log({user_id: value})

            # Save the encoded value to the database
            db.set(user_id, value)

            # If everything succeeds, send a success event
            self.send_payment_processed_event(user_id, "SUCCESS", amount)

            return {"status": "success", "message": "User credit updated successfully"}

        except Exception as e:
            # Log the error and send a failure event
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

        # Rollback the credit in case of stock failure
        self.rollback_credit(user_id, amount)

        print(f"Stock failure event received. Rolled back credit for user {user_id}.")

    def rollback_credit(self, user_id, amount):
        from app import get_user_from_db, db, log

        try:
            user_entry = get_user_from_db(user_id)
            user_entry.credit += int(amount)

            log({user_id: amount})
            print({"rollback": f"Credit for {user_id} rolled back. Amount: {amount}"})

            # Save the updated value to databse
            db.set(user_id, msgpack.encode(user_entry))

        except Exception as e:
            log({"error": f"Error rolling back credit for {user_id}: {str(e)}"})
