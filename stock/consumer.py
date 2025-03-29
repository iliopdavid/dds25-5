from kafka import KafkaConsumer
import json
from msgspec import msgpack
from producer import StockProducer


class StockConsumer:
    def __init__(self):
        self.topics = ["order-created-stock", "payment-failure"]
        self.group_id = "stock"

        # Initialize Kafka consumer
        self.consumer = KafkaConsumer(
            *self.topics,
            bootstrap_servers=["kafka:9092"],
            group_id=self.group_id,
            auto_offset_reset="earliest",
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
        )

        self.producer = StockProducer()

    def consume_messages(self):
        for message in self.consumer:
            if message.topic == "order-created-stock":
                self.process_stock(message.value)
            elif message.topic == "payment-failure":
                self.handle_payment_failure(message.value)

    def process_stock(self, stock_data):
        from app import get_item_from_db, log, db, app

        app.logger.debug(f"Consuming event", stock_data)

        order_id = stock_data.get("order_id")
        items = stock_data.get("items")

        try:
            for item in items:
                item_id = item.get("item_id")
                quantity = item.get("quantity")

                # Get item details from Redis database
                item_entry = get_item_from_db(item_id)
                item_entry.stock -= int(quantity)
                value = msgpack.encode(item_entry)

                if item_entry.stock < 0:
                    self.send_stock_processed_event(order_id, "FAILURE", items)
                    return {
                        "status": "failure",
                        "message": "There is not enough stock",
                    }

                log({item_id: value})
                db.set(item_id, value)

                # If everything succeeds, send a success event
                self.send_stock_processed_event(order_id, "SUCCESS", items)

                return {
                    "status": "success",
                    "message": "User credit updated successfully",
                }
        except Exception as e:
            # Log the error and send a failure event
            error_message = str(e)
            log({"error": error_message})

            self.send_stock_processed_event(order_id, "FAILURE", items)
            return {"status": "failure", "message": error_message}

    def send_stock_processed_event(self, order_id, status, items):
        event_data = {
            "order_id": order_id,
            "status": status,
            "items": items,
        }
        self.producer.send_message("payment-processed", event_data)

    def handle_payment_failure(self, payment_failure_data):
        order_id = payment_failure_data.get("order_id")
        items = payment_failure_data.get("items")

        # Rollback stock in case of payment failure
        self.rollback_stock(items)
        print(
            f"Payment failure event received. Rolled back stock for order {order_id}."
        )

    def rollback_stock(self, items):
        from app import get_item_from_db, db, log

        try:
            for item in items:
                item_id = item.get("item_id")
                quantity = item.get("quantity")

                # Get the item from the database
                item_entry = get_item_from_db(item_id)

                # Rollback the stock by adding the quantity back
                item_entry.stock += int(quantity)
                value = msgpack.encode(item_entry)

                # log and write to database
                log({item_id: value})
                print(
                    {
                        "rollback": f"Stock for {item_id} rolled back. Quantity: {quantity}"
                    }
                )
                db.set(item_id, value)

        except Exception as e:
            log({"error": f"Error rolling back stock: {str(e)}"})
