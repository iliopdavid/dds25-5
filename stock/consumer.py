import json
import uuid
import pika
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
                exchange="payment.exchange",
                queue=queue,
                routing_key="payment.stock.processed",
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
                queue=queue, on_message_callback=self.handle_message, auto_ack=False
            )

        app.logger.info("Waiting for messages. To exit press CTRL+C")
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            app.logger.info("Stopping consumer...")
            self.cleanup()

    def is_duplicate_message(self, message_id, expiration_seconds=3600):
        key = f"processed_msg:{message_id}"
        result = self.redis_client.setnx(key, 1)
        if result == 1:
            self.redis_client.expire(key, expiration_seconds)
        return result == 0

    def handle_message(self, ch, method, properties, body):
        from app import app

        app.logger.debug(
            f"Stock consumer received message with routing key {method.routing_key} and content {body}"
        )

        try:
            message = json.loads(body)

            message_id = message.get("message_id")

            if self.is_duplicate_message(message_id):
                app.logger.info(f"Duplicate message detected and skipped: {message_id}")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            if method.routing_key == "payment.stock.processed":
                self.process_stock(message)

            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            app.logger.error(f"Error processing message: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def process_stock(self, stock_data):
        from app import app

        app.logger.debug(f"Consuming event {stock_data}")

        order_id = stock_data.get("order_id")
        user_id = stock_data.get("user_id")
        items = stock_data.get("items")
        total_amount = stock_data.get("total_amount")

        try:
            process_stock_lua = """
                local items = cmsgpack.unpack(ARGV[1])
                local errors = {}
                local rollback_data = {}

                for item_id, quantity in pairs(items) do
                    local item_data = redis.call("GET", item_id)
                    if not item_data then
                        errors[item_id] = "item_not_found"
                    else
                        local item = cmsgpack.unpack(item_data)
                        if item.stock < quantity then
                            errors[item_id] = "insufficient_stock"
                        else
                            rollback_data[item_id] = item.stock
                            item.stock = item.stock - quantity
                            redis.call("SET", item_id, cmsgpack.pack(item))
                        end
                    end
                end

                if next(errors) then
                    for item_id, prev_stock in pairs(rollback_data) do
                        local item_data = redis.call("GET", item_id)
                        local item = cmsgpack.unpack(item_data)
                        item.stock = prev_stock
                        redis.call("SET", item_id, cmsgpack.pack(item))
                    end
                    return cmsgpack.pack(errors)
                end

                return nil
            """

            result = self.redis_client.eval(
                process_stock_lua,
                len(items),
                *[str(item_id) for item_id in items],
                msgpack.encode(items),
            )

            if result:
                errors = msgpack.decode(result)
                if errors:
                    app.logger.debug("Stock check failed: " + str(errors))
                    self.send_stock_failure_event(order_id, user_id, total_amount)
                    return

            app.logger.debug(f"Stock reduced for order {order_id}")
            self.send_stock_processed_event(order_id)

        except Exception as e:
            app.logger.error(f"Error processing stock for order {order_id}: {e}")
            self.send_stock_failure_event(order_id, user_id, total_amount)

    def send_stock_processed_event(self, order_id):
        event_data = {
            "message_id": str(uuid.uuid4()),
            "order_id": order_id,
            "status": "SUCCESS",
        }
        self.producer.send_message("stock.order.processed", event_data)

    def send_stock_failure_event(self, order_id, user_id, total_amount):
        event_data = {
            "message_id": str(uuid.uuid4()),
            "order_id": order_id,
            "total_amount": total_amount,
            "user_id": user_id,
        }
        self.producer.send_message("stock.payment.rollback", event_data)

    def cleanup(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
