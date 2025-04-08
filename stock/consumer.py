import json
import pika
import redis
from msgspec import msgpack
from producer import StockProducer


class StockConsumer:
    def __init__(self, db):
        self.redis_client = db
        self.queues = ["stock_queue"]
        self.connection = None
        self.channel = None
        self.producer = StockProducer()

        # Initialize RabbitMQ connection
        self._connect()

        # Ensure the exchange exists
        self.channel.exchange_declare(
            exchange="order.exchange", exchange_type="topic", durable=True
        )

        # Declare and bind queues
        for queue in self.queues:
            self.channel.queue_declare(queue=queue)
            self.channel.queue_bind(
                exchange="order.exchange", queue=queue, routing_key="order.checkout"
            )
            self.channel.queue_bind(
                exchange="order.exchange", queue=queue, routing_key="order.stock.#"
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

        for queue in self.queues:
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
            f"Stock consumer received message with routing key {method.routing_key} and content {body}"
        )

        try:
            message = json.loads(body)
            if method.routing_key == "order.checkout":
                self.process_stock(message)
            elif method.routing_key == "order.stock.rollback":
                self.handle_stock_rollback(message)
        except Exception as e:
            app.logger.error(f"Error processing message: {e}")

    def process_stock(self, stock_data):
        from app import app, get_item_from_db

        app.logger.debug(f"Consuming event {stock_data}")

        order_id = stock_data.get("order_id")
        user_id = stock_data.get("user_id")
        items = stock_data.get("items")

        try:
            while True:
                pipeline = self.redis_client.pipeline()

                try:
                    # Watch the item stock entries
                    for item_id in items:
                        pipeline.watch(item_id)

                    # Check stock levels for each item
                    for item_id, quantity in items.items():
                        # Get item details from Redis database
                        item_entry = get_item_from_db(item_id)
                        if item_entry.stock < int(quantity):
                            pipeline.unwatch()
                            app.logger.debug(
                                f"Item {item_id} stock is reduced to below 0."
                            )
                            self.send_stock_processed_event(
                                order_id, user_id, "FAILURE", items
                            )
                            return {
                                "status": "failure",
                                "message": f"Not enough stock for item {item_id}.",
                            }

                    # Start the transaction
                    pipeline.multi()

                    # Update stock for each item
                    for item_id, quantity in items.items():
                        item_entry = get_item_from_db(item_id)
                        item_entry.stock -= int(quantity)
                        value = msgpack.encode(item_entry)
                        pipeline.set(
                            item_id, value
                        )  # Queue the command to update stock in Redis
                        app.logger.debug(
                            f"Item {item_id} stock reduced by {quantity}. New stock: {item_entry.stock}"
                        )

                    # Execute the pipeline
                    pipeline.execute()

                    # If everything succeeds, send a success event
                    self.send_stock_processed_event(order_id, user_id, "SUCCESS", items)
                    return {
                        "status": "success",
                        "message": "Stock updated successfully",
                    }

                except redis.WatchError:
                    # Retry if the watched key was modified by another transaction
                    app.logger.info(f"Retrying due to WatchError for order {order_id}")

        except Exception as e:
            app.logger.error(f"Error processing stock for order {order_id}: {e}")
            self.send_stock_processed_event(order_id, user_id, "FAILURE", items)
            return {"status": "failure", "message": str(e)}

    def send_stock_processed_event(self, order_id, user_id, status, items):
        event_data = {
            "order_id": order_id,
            "user_id": user_id,
            "status": status,
            "items": items,
        }
        self.producer.send_message("stock.processed", event_data)

    def handle_stock_rollback(self, payment_failure_data):
        from app import app

        order_id = payment_failure_data.get("order_id")
        items = payment_failure_data.get("items")

        # Rollback stock in case of payment failure
        self.rollback_stock(items)
        app.logger.debug(
            f"Payment failure event received. Rolled back stock for order {order_id}."
        )

    def rollback_stock(self, items):
        from app import app, get_item_from_db

        try:
            for item_id, quantity in items.items():
                # Fetch item from DB (likely Redis or your data store)
                item_entry = get_item_from_db(item_id)

                # Increment stock
                item_entry.stock += int(quantity)

                # Encode and store it back
                value = msgpack.encode(item_entry)
                self.redis_client.set(item_id, value)

                app.logger.debug(
                    f"Rolled back stock for item {item_id}. Quantity: {quantity}. New stock: {item_entry.stock}"
                )

        except Exception as e:
            app.logger.error(f"Error rolling back stock for items: {str(e)}")

    def cleanup(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
