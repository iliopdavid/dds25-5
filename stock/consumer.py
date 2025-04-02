import json
import pika
from msgspec import msgpack
from producer import StockProducer


class StockConsumer:
    def __init__(self):
        self.queues = ["order.checkout", "payment.failure"]
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host="rabbitmq")
        )
        self.channel = self.connection.channel()

        self.producer = StockProducer()

        # Declare queues
        for queue in self.queues:
            self.channel.queue_declare(queue=queue, durable=True)
            self.channel.queue_bind(exchange="order.exchange", queue=queue)

    def consume_messages(self):
        for queue in self.queues:
            self.channel.basic_consume(
                queue=queue, on_message_callback=self.callback, auto_ack=True
            )

        print("Waiting for messages. To exit, press CTRL+C")
        self.channel.start_consuming()

    def callback(self, ch, method, properties, body):
        from app import app

        message = json.loads(body)
        queue_name = method.routing_key

        if queue_name == "order.checkout":
            self.process_stock(message)
        elif queue_name == "payment.failure":
            self.handle_payment_failure(message)

    def process_stock(self, stock_data):
        from app import get_item_from_db, log, db, app

        app.logger.debug(f"Consuming event {stock_data}")

        order_id = stock_data.get("order_id")
        user_id = stock_data.get("user_id")
        items = stock_data.get("items")

        try:
            for item_id, quantity in items.items():
                # Get item details from Redis database
                item_entry = get_item_from_db(item_id)
                item_entry.stock -= int(quantity)
                value = msgpack.encode(item_entry)

                if item_entry.stock < 0:
                    self.send_stock_processed_event(order_id, user_id, "FAILURE", items)
                    return {
                        "status": "failure",
                        "message": "There is not enough stock",
                    }

                log({item_id: value})
                db.set(item_id, value)

                # If everything succeeds, send a success event
                self.send_stock_processed_event(order_id, user_id, "SUCCESS", items)

                return {
                    "status": "success",
                    "message": "User credit updated successfully",
                }
        except Exception as e:
            # Log the error and send a failure event
            error_message = str(e)
            log({"error": error_message.encode("utf-8")})

            self.send_stock_processed_event(order_id, user_id, "FAILURE", items)
            return {"status": "failure", "message": error_message}

    def send_stock_processed_event(self, order_id, user_id, status, items):
        event_data = {
            "order_id": order_id,
            "user_id": user_id,
            "status": status,
            "items": items,
        }
        self.producer.send_message("payment.processed", event_data)

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
