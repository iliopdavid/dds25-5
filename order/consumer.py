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

        self._ensure_connection()

        try:
            message = json.loads(body.decode("utf-8"))
            topic = method.routing_key
            order_id = message.get("order_id")

            app.logger.debug(
                f"message received with topic {topic} and content {message}"
            )

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
        from app import app

        try:
            # Lua script to update the order's status atomically
            update_order_lua = """
                local order_id = KEYS[1]
                local field = ARGV[1]
                local status = ARGV[2]

                local order_data = redis.call("GET", order_id)

                if not order_data then
                    return {err = "order_not_found"}
                end

                local order = cmsgpack.unpack(order_data)

                -- Dynamically set the field value
                order[field] = status

                -- Save the updated order back to Redis
                redis.call("SET", order_id, cmsgpack.pack(order))

                return {ok = "status_updated"}
            """

            # Execute Lua script
            result = self.redis_client.eval(
                update_order_lua,
                1,
                order_id,
                field,
                status,
            )

            # Handle Lua script result
            if isinstance(result, dict) and result.get("err") == "order_not_found":
                app.logger.warning(f"No order found to update: {order_id}")
                return {"status": "failure", "message": "Order not found"}

            app.logger.debug(
                f"Order {order_id} status for field {field} successfully updated to {status}."
            )

            return {"status": "success", "message": "Order status updated"}

        except Exception as e:
            app.logger.exception(f"Error updating order {order_id} status: {str(e)}")
            return {"status": "failure", "message": f"Error updating order: {str(e)}"}

    def initiate_rollback(self, order_id, event):
        from app import app, OrderValue

        try:

            order: OrderValue = self.get_order_from_db(order_id)
            # Lua script to check the order and update rollback status
            initiate_rollback_lua = """
                local order_id = KEYS[1]
                local rollback_status = 'INITIATED'
                local order_data = redis.call("GET", order_id)

                if not order_data then
                    return {err = "order_not_found"}
                end

                local order = cmsgpack.unpack(order_data)

                -- Update rollback status and store the updated order data
                order.rollback_status = rollback_status
                redis.call("SET", order_id, cmsgpack.pack(order))

                return {ok = "rollback_initiated"}
            """

            # Execute Lua script
            result = self.redis_client.eval(
                initiate_rollback_lua,
                1,
                order_id,
            )

            # Handle Lua script result
            if isinstance(result, dict) and result.get("err") == "order_not_found":
                app.logger.warning(f"No order found to rollback: {order_id}")
                return {"status": "failure", "message": "Order not found"}

            app.logger.debug(f"Rollback initiated for order {order_id}, event: {event}")

            # Publish the event
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

            return {"status": "success", "message": "Rollback initiated"}

        except Exception as e:
            app.logger.exception(
                f"Error initiating rollback for order {order_id}: {str(e)}"
            )
            return {
                "status": "failure",
                "message": f"Error initiating rollback: {str(e)}",
            }

    def complete_order(self, order_id):
        from app import app

        try:
            # Lua script to update the order's status atomically
            complete_order_lua = """
                local order_id = KEYS[1]
                local order_data = redis.call("GET", order_id)

                if not order_data then
                    return {err = "order_not_found"}
                end

                local order = cmsgpack.unpack(order_data)

                -- Update order statuses
                order.stock_status = "COMPLETED"
                order.payment_status = "COMPLETED"

                -- Save the updated order back to Redis
                redis.call("SET", order_id, cmsgpack.pack(order))

                return {ok = "order_completed"}
            """

            # Execute Lua script
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

        # get serialized data
        entry: bytes = self.redis_client.get(order_id)
        entry: OrderValue | None = (
            msgpack.decode(entry, type=OrderValue) if entry else None
        )
        return entry

    def cleanup(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
