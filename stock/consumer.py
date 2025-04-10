import json
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

        app.logger.debug(
            f"Stock consumer received message with routing key {method.routing_key} and content {body}"
        )

        try:
            message = json.loads(body)
            if method.routing_key == "order.checkout":
                self.process_stock(message)
            elif method.routing_key == "order.stock.rollback":
                self.handle_stock_rollback(message)
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
                    self.send_stock_processed_event(order_id, user_id, "FAILURE", items)
                    return

            app.logger.debug(f"Stock reduced for order {order_id}")
            self.send_stock_processed_event(order_id, user_id, "SUCCESS", items)

        except Exception as e:
            app.logger.error(f"Error processing stock for order {order_id}: {e}")
            self.send_stock_processed_event(order_id, user_id, "FAILURE", items)

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
        from app import app

        try:
            # Lua script to rollback stock atomically
            rollback_stock_lua = """
                local items = cmsgpack.unpack(ARGV[1])
                local errors = {}

                -- Iterate over items and rollback stock
                for item_id, quantity in pairs(items) do
                    local item_key = item_id
                    local item_data = redis.call("GET", item_key)

                    if not item_data then
                        errors[item_id] = "item_not_found"
                    else
                        local item = cmsgpack.unpack(item_data)
                        -- Rollback stock (increment)
                        item.stock = item.stock + quantity
                        redis.call("SET", item_key, cmsgpack.pack(item))
                    end
                end

                -- If there are any errors, return the error table
                if next(errors) then
                    return cmsgpack.pack(errors)
                end

                -- If no errors, return nil (successful operation)
                return nil
            """

            # Execute the Lua script
            result = self.redis_client.eval(
                rollback_stock_lua,
                len(items),
                *[str(item_id) for item_id in items],
                msgpack.encode(items),
            )

            # Handle the result of the Lua script
            if result:
                errors = msgpack.decode(result)
                if len(errors) > 0:
                    app.logger.debug("Error rolling back some items.")
                    for item_id, error in errors.items():
                        if error == "item_not_found":
                            app.logger.debug(
                                f"Item {item_id} not found in stock during rollback."
                            )
                    return

            app.logger.debug(f"Stock successfully rolled back for items.")
            return

        except Exception as e:
            app.logger.error(f"Error rolling back stock for items: {str(e)}")
            return

    def cleanup(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
