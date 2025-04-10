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
                exchange="stock.exchange", queue=queue, routing_key="stock.order.#"
            )
            self.channel.queue_bind(
                exchange="payment.exchange", queue=queue, routing_key="payment.order.#"
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

        self._ensure_connection()

        try:
            message = json.loads(body)
            topic = method.routing_key
            order_id = message.get("order_id")
            message_id = message.get("message_id")

            if self.is_duplicate_message(message_id):
                app.logger.info(f"Duplicate message detected and skipped: {message_id}")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            app.logger.debug(
                f"message received with topic {topic} and content {message}"
            )

            if topic == "stock.order.processed":
                self.complete_order(order_id)

            # Acknowledge message only after successful processing
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except json.JSONDecodeError as e:
            app.logger.error(f"Failed to decode message: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def is_duplicate_message(self, message_id, expiration_seconds=3600):
        key = f"processed_msg:{message_id}"
        result = self.redis_client.setnx(key, 1)
        if result == 1:
            self.redis_client.expire(key, expiration_seconds)
        return result == 0

    def complete_order(self, order_id):
        from app import app

        try:
            # Lua script to update the order's paid status atomically
            complete_order_lua = """
                local order_id = KEYS[1]
                local order_data = redis.call("GET", order_id)

                if not order_data then
                    return {err = "order_not_found"}
                end

                local order = cmsgpack.unpack(order_data)
                order.paid = true

                -- Save the updated order back to Redis
                redis.call("SET", order_id, cmsgpack.pack(order))

                return {ok = "order_completed"}
            """

            # Run the script
            result = self.redis_client.eval(
                complete_order_lua,
                1,
                order_id,
            )

            # Handle Lua script result
            if isinstance(result, dict) and result.get("err") == "order_not_found":
                app.logger.warning(f"No order found to complete: {order_id}")
                return {"status": "failure", "message": "Order not found"}

            app.logger.debug(f"Order {order_id} successfully completed.")

            return {"status": "success", "message": "Order completed"}

        except Exception as e:
            app.logger.exception(f"Error completing order {order_id}: {str(e)}")
            return {"status": "failure", "message": f"Error completing order: {str(e)}"}

    def get_order_from_db(self, order_id):
        from app import OrderValue

        entry: bytes = self.redis_client.get(order_id)
        entry: OrderValue | None = (
            msgpack.decode(entry, type=OrderValue) if entry else None
        )
        return entry

    def cleanup(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
