from producer import OrderProducer
import json
import pika


class OrderConsumer:
    def __init__(self, db):
        self.redis_client = db
        self.queue_names = ["order_queue"]
        self.connection = None
        self.channel = None
        self.producer = OrderProducer()

        self._connect()

        # Ensure the exchanges exist
        self.channel.exchange_declare(exchange="stock.exchange", exchange_type="direct")
        self.channel.exchange_declare(
            exchange="payment.exchange", exchange_type="direct"
        )

        for queue in self.queue_names:
            self.channel.queue_declare(queue=queue)

            # Bind stock and payment processing events
            self.channel.queue_bind(
                exchange="stock.exchange", queue=queue, routing_key="stock.processed"
            )
            self.channel.queue_bind(
                exchange="payment.exchange",
                queue=queue,
                routing_key="payment.processed",
            )

            # Bind rollback confirmation events
            self.channel.queue_bind(
                exchange="stock.exchange", queue=queue, routing_key="stock.rollbacked"
            )
            self.channel.queue_bind(
                exchange="payment.exchange",
                queue=queue,
                routing_key="payment.rollbacked",
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

    # Start consuming messages
    def consume_messages(self):
        from app import app

        for queue in self.queue_names:
            self.channel.basic_consume(
                queue=queue, on_message_callback=self.handle_message
            )

        app.logger.info("Waiting for messages. To exit press CTRL+C")
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            app.logger.info("Stopping consumer...")
            self.cleanup()

    # Handle incoming messages
    def handle_message(self, ch, method, properties, body):
        from app import app

        # Ensure RabbitMQ connection is open before handling messages
        self._ensure_connection()

        try:
            message = json.loads(body.decode("utf-8"))
            topic = method.routing_key
            order_id = message.get("order_id")

            app.logger.debug(
                f"message received with topic {topic} and content {message}"
            )

            # Prevent duplicate processing using Redis SETNX
            if not self.set_idempotency_key(order_id, topic):
                app.logger.warning(
                    f"Duplicate message ignored: {topic} for order {order_id}"
                )
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            if topic == "payment.processed":
                self.handle_payment_processed(order_id, message)
            elif topic == "stock.processed":
                self.handle_stock_updated(order_id, message)
            elif topic == "stock.rollbacked":
                self.handle_stock_rollbacked(order_id, message)
            elif topic == "payment.rollbacked":
                self.handle_payment_rollbacked(order_id, message)

            # Acknowledge message only after successful processing
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except json.JSONDecodeError as e:
            app.logger.error(f"Failed to decode message: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    # handle the event notifying that the payment processing has been completed
    def handle_payment_processed(self, order_id, value):
        from app import app

        payment_status = value["status"]
        self.update_order_status(order_id, "payment_status", payment_status)

        if self.order_successfully_processed(order_id):
            self.complete_order(order_id)
        elif self.payment_failed_but_stock_succeeded(order_id):
            self.initiate_rollback(order_id, "order.stock.rollback")
        elif self.stock_failed_but_payment_succeeded(order_id):
            self.initiate_rollback(order_id, "order.payment.rollback")

    # handle the event notifying that the stock processing has been completed
    def handle_stock_updated(self, order_id, value):
        stock_status = value["status"]
        self.update_order_status(order_id, "stock_status", stock_status)

        if self.order_successfully_processed(order_id):
            self.complete_order(order_id)
        elif self.stock_failed_but_payment_succeeded(order_id):
            self.initiate_rollback(order_id, "order.payment.rollback")
        elif self.payment_failed_but_stock_succeeded(order_id):
            self.initiate_rollback(order_id, "order.stock.rollback")

    def handle_stock_rollbacked(self, order_id, value):
        self.update_order_status(order_id, "rollback_status", "COMPLETED")

    def handle_payment_rollbacked(self, order_id, value):
        self.update_order_status(order_id, "rollback_status", "COMPLETED")

    def update_order_status(self, order_id, field, status):
        self.redis_client.hset(f"order:{order_id}", field, status)

    def initiate_rollback(self, order_id, event):
        from app import app

        order_entry = self.get_order_from_db(order_id)

        app.logger.debug(f"rollback initiated!!!!! event: {event}")

        if event == "order.stock.rollback":
            self.producer.send_event(
                "order.stock.rollback",
                {"order_id": order_id, "items": order_entry["items"]},
            )
        elif event == "order.payment.rollback":
            self.producer.send_event(
                "order.payment.rollback",
                {
                    "user_id": order_entry["user_id"],
                    "total_amount": order_entry["total_cost"],
                },
            )
        self.update_order_status(order_id, "rollback_status", "INITIATED")

    def complete_order(self, order_id):
        from app import app

        self.update_order_status(order_id, "stock_status", "COMPLETED")
        self.update_order_status(order_id, "payment_status", "COMPLETED")
        app.logger.info(f"Order {order_id} successfully completed!")

    def get_order_from_db(self, order_id):
        order = self.redis_client.hgetall(f"order:{order_id}")
        return {
            "user_id": order.get("user_id"),
            "total_cost": order.get("total_cost"),
            "items": order.get("items"),
        }

    def order_successfully_processed(self, order_id):
        from app import app

        try:
            order_bytes = self.redis_client.hgetall(f"order:{order_id}")
            order = {
                k.decode("utf-8"): v.decode("utf-8") for k, v in order_bytes.items()
            }
            stock_status = order.get("stock_status")
            payment_status = order.get("payment_status")
            result = stock_status == "SUCCESS" and payment_status == "SUCCESS"

            app.logger.debug(
                f"success status being checked {order} with result {result}"
            )
            return result

        except Exception as e:
            app.logger.exception(
                f"Error checking success status for order {order_id}: {e}"
            )
            return False  # Fail safe if there's an error

    def payment_failed_but_stock_succeeded(self, order_id):
        from app import app

        try:
            order_bytes = self.redis_client.hgetall(f"order:{order_id}")
            order = {
                k.decode("utf-8"): v.decode("utf-8") for k, v in order_bytes.items()
            }
            stock_status = order.get("stock_status")
            payment_status = order.get("payment_status")
            result = payment_status == "FAILED" and stock_status == "SUCCESS"

            app.logger.debug(
                f"_payment_failed_but_stock_succeeded status being checked {order} with result {result}"
            )
            return result

        except Exception as e:
            app.logger.exception(
                f"Error checking payment_failed_stock_succeeded for order {order_id}: {e}"
            )
            return False

    def stock_failed_but_payment_succeeded(self, order_id):
        from app import app

        try:
            order_bytes = self.redis_client.hgetall(f"order:{order_id}")
            order = {
                k.decode("utf-8"): v.decode("utf-8") for k, v in order_bytes.items()
            }

            stock_status = order.get("stock_status")
            payment_status = order.get("payment_status")
            result = stock_status == "FAILED" and payment_status == "SUCCESS"

            app.logger.debug(
                f"_stock_failed_but_payment_succeeded status being checked {order} with result {result}"
            )
            return result

        except Exception as e:
            app.logger.exception(
                f"Error checking stock_failed_payment_succeeded for order {order_id}: {e}"
            )
            return False

    # prevents same event to be consumed multiple times (because of retry etc)
    def set_idempotency_key(self, order_id, topic):
        key = f"idempotency:{order_id}:{topic}"
        return self.redis_client.setnx(key, "processed")

    def cleanup(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
