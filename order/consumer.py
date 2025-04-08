import redis
from producer import OrderProducer
import json
import pika
from msgspec import msgpack


class OrderConsumer:
    def __init__(self, db):
        self.redis_client = db
        self.queue_names = ["order_queue"]
        self.connection = None
        self.channel = None
        self.producer = OrderProducer()

        self._connect()

        # Ensure the exchanges exist
        self.channel.exchange_declare(
            exchange="stock.exchange", exchange_type="direct", durable=True
        )
        self.channel.exchange_declare(
            exchange="payment.exchange", exchange_type="direct", durable=True
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

    def handle_payment_processed(self, order_id, value):
        payment_status = value["status"]
        self.update_order_status(order_id, "payment_status", payment_status)
        self.evaluate_order_state(order_id)

    def handle_stock_updated(self, order_id, value):
        stock_status = value["status"]
        self.update_order_status(order_id, "stock_status", stock_status)
        self.evaluate_order_state(order_id)

    def evaluate_order_state(self, order_id):
        from app import app, OrderValue

        order: OrderValue = self.get_order_from_db(order_id)

        stock_status = order.stock_status
        payment_status = order.payment_status

        app.logger.debug(f"Evaluating order state: stock={order}")

        app.logger.debug(
            f"Evaluating order state: stock={stock_status} and payment={payment_status}"
        )
        app.logger.info(
            f"output: {stock_status == 'SUCCESS' and payment_status == 'FAILED'} or {stock_status == 'FAILED' and payment_status == 'SUCCESS'}"
        )

        if stock_status == "SUCCESS" and payment_status == "SUCCESS":
            self.complete_order(order_id)
        elif stock_status == "SUCCESS" and payment_status == "FAILURE":
            self.initiate_rollback(order_id, "order.stock.rollback")
        elif stock_status == "FAILURE" and payment_status == "SUCCESS":
            self.initiate_rollback(order_id, "order.payment.rollback")

    def handle_stock_rollbacked(self, order_id, value):
        self.update_order_status(order_id, "rollback_status", "COMPLETED")

    def handle_payment_rollbacked(self, order_id, value):
        self.update_order_status(order_id, "rollback_status", "COMPLETED")

    def update_order_status(self, order_id, field, status):
        from app import OrderValue

        try:
            # Retry the transaction using watch and multi for atomicity
            while True:
                with self.redis_client.pipeline() as pipe:
                    try:
                        # Watch the order key
                        pipe.watch(order_id)

                        # Fetch the current order entry
                        user_bytes = pipe.get(order_id)
                        if not user_bytes:
                            pipe.unwatch()
                            return

                        order: OrderValue = msgpack.decode(user_bytes, type=OrderValue)
                        setattr(order, field, status)

                        # Start the transaction
                        pipe.multi()
                        pipe.set(order_id, msgpack.encode(order))
                        pipe.execute()

                        break  # Break out of loop if transaction is successful
                    except redis.WatchError:
                        # Transaction failed, retry
                        continue
        except redis.exceptions.RedisError:
            from app import app

            app.logger.exception(f"Error updating order {order_id} status")

    def initiate_rollback(self, order_id, event):
        from app import app, OrderValue

        try:
            while True:
                with self.redis_client.pipeline() as pipe:
                    try:
                        pipe.watch(order_id)
                        entry = pipe.get(order_id)
                        if not entry:
                            pipe.unwatch()
                            app.logger.warning(
                                f"No order found in Redis to rollback: {order_id}"
                            )
                            return

                        order: OrderValue = msgpack.decode(entry, type=OrderValue)

                        app.logger.debug(
                            f"rollback initiated!!!!! event: {event}, orderid {order_id}, order entry {order}"
                        )

                        if event == "order.stock.rollback":
                            self.producer.send_event(
                                "order.stock.rollback",
                                {"order_id": order_id, "items": order.items},
                            )
                        elif event == "order.payment.rollback":
                            self.producer.send_event(
                                "order.payment.rollback",
                                {
                                    "user_id": order.user_id,
                                    "order_id": order_id,
                                    "total_amount": order.total_cost,
                                },
                            )

                        order.rollback_status = "INITIATED"
                        pipe.multi()
                        pipe.set(order_id, msgpack.encode(order))
                        pipe.execute()
                        break  # Exit the loop if successful
                    except redis.WatchError:
                        continue
        except redis.exceptions.RedisError:
            app.logger.exception(f"Error initiating rollback for order {order_id}")

    def complete_order(self, order_id):
        from app import app, OrderValue

        try:
            while True:
                with self.redis_client.pipeline() as pipe:
                    try:
                        pipe.watch(order_id)
                        entry = pipe.get(order_id)
                        if not entry:
                            pipe.unwatch()
                            return

                        order: OrderValue = msgpack.decode(entry, type=OrderValue)
                        order.stock_status = "COMPLETED"
                        order.payment_status = "COMPLETED"

                        pipe.multi()
                        pipe.set(order_id, msgpack.encode(order))
                        pipe.execute()
                        break
                    except redis.WatchError:
                        continue
        except redis.exceptions.RedisError:
            app.logger.exception(f"Error completing order {order_id}")

    def get_order_from_db(self, order_id):
        from app import OrderValue

        # get serialized data
        entry: bytes = self.redis_client.get(order_id)
        entry: OrderValue | None = (
            msgpack.decode(entry, type=OrderValue) if entry else None
        )
        return entry

    def set_idempotency_key(self, order_id, topic):
        key = f"idempotency:{order_id}:{topic}"
        return self.redis_client.setnx(key, "processed")

    def cleanup(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
