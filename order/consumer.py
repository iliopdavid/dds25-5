from producer import OrderProducer
from rabbitmq_connection import RabbitMQConnection
import json


class OrderConsumer:
    def __init__(self):
        from app import app

        app.logger.debug("OrderConsumer initialized and ready to consume messages.")
        self.queue_names = ["payment-processed", "stock-processed"]
        self.order_status = {}

        # Initialize RabbitMQ connection
        self.rabbitmq = RabbitMQConnection()
        self.rabbitmq.declare_queues(self.queue_names)

        self.producer = OrderProducer()

    def consume_messages(self):
        from app import app

        """Start consuming messages from queues."""
        for queue in self.queue_names:
            self.rabbitmq.channel.basic_consume(
                queue=queue, on_message_callback=self.handle_message, auto_ack=True
            )

        app.logger.info("Waiting for messages. To exit press CTRL+C")
        try:
            self.rabbitmq.channel.start_consuming()
        except KeyboardInterrupt:
            app.logger.info("Stopping consumer...")
            self.rabbitmq.close()

    def handle_message(self, ch, method, properties, body):
        from app import app

        """Process received messages."""
        try:
            message = json.loads(body.decode("utf-8"))
            topic = method.routing_key

            if topic == "payment-processed":
                self.handle_payment_processed(message)
            elif topic == "stock-processed":
                self.handle_stock_updated(message)
        except json.JSONDecodeError as e:
            app.logger.error(f"Failed to decode message: {e}")

    def handle_payment_processed(self, value):
        from app import complete_order, get_order_from_db

        """Handle payment processing messages."""
        order_id = value["order_id"]
        payment_status = value["payment_status"]
        order_entry = get_order_from_db(order_id)

        # Initialize order status if not already present
        self.order_status.setdefault(
            order_id, {"payment_status": None, "stock_status": None}
        )

        # Update the payment status
        self.order_status[order_id]["payment_status"] = payment_status

        # Check if we have both payment and stock statuses for the order
        if self._order_successfully_processed(order_id):
            complete_order(order_id)
        elif self._payment_failed_but_stock_succeeded(order_id):
            # Rollback stock service because payment failed
            self.producer.send_event(
                "payment-failure",
                "",
                {"order_id": order_id, "items": order_entry.items},
            )

    def handle_stock_updated(self, value):
        from app import complete_order, get_order_from_db

        """Handle stock processing messages."""
        order_id = value["order_id"]
        stock_status = value["stock_status"]
        order_entry = get_order_from_db(order_id)

        # Initialize order status if not already present
        self.order_status.setdefault(
            order_id, {"payment_status": None, "stock_status": None}
        )

        # Update the stock status
        self.order_status[order_id]["stock_status"] = stock_status

        # Check if we have both payment and stock statuses for the order
        if self._order_successfully_processed(order_id):
            complete_order(order_id)
        elif self._stock_failed_but_payment_succeeded(order_id):
            # Rollback payment service because stock processing failed
            self.producer.send_event(
                "stock-failure",
                "",
                {
                    "user_id": order_entry.user_id,
                    "total_amount": order_entry.total_cost,
                },
            )

    def _order_successfully_processed(self, order_id):
        """Check if both payment and stock statuses are successful."""
        return (
            self.order_status[order_id]["payment_status"] == "SUCCESS"
            and self.order_status[order_id]["stock_status"] == "SUCCESS"
        )

    def _payment_failed_but_stock_succeeded(self, order_id):
        """Check if payment failed but stock succeeded."""
        return (
            self.order_status[order_id]["payment_status"] == "FAILED"
            and self.order_status[order_id]["stock_status"] == "SUCCESS"
        )

    def _stock_failed_but_payment_succeeded(self, order_id):
        """Check if stock failed but payment succeeded."""
        return (
            self.order_status[order_id]["payment_status"] == "SUCCESS"
            and self.order_status[order_id]["stock_status"] == "FAILED"
        )

    def close_connection(self):
        """Close the RabbitMQ connection."""
        self.rabbitmq.close()
