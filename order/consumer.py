from producer import OrderProducer
from rabbitmq_connection import RabbitMQConnection
import json
import pika


class OrderConsumer:
    def __init__(self):
        self.order_status = {}
        self.queue_names = ["payment-processed", "stock-processed"]
        self.connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
        self.channel = self.connection.channel()

        for queue in self.queue_names:
            self.channel.queue_declare(queue=queue)

            self.channel.queue_bind(exchange="order-exchange", queue=queue)

        self.producer = OrderProducer()

    # Start consuming messages
    def consume_messages(self):
        from app import app

        for queue in self.queue_names:
            self.channel.basic_consume(
                queue=queue, on_message_callback=self.handle_message, auto_ack=True
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

        try:
            message = json.loads(body.decode("utf-8"))
            topic = method.routing_key

            if topic == "payment-processed":
                self.handle_payment_processed(message)
            elif topic == "stock-processed":
                self.handle_stock_updated(message)
        except json.JSONDecodeError as e:
            app.logger.error(f"Failed to decode message: {e}")

    # handle the event notifying that the payment processing has been completed
    def handle_payment_processed(self, value):
        from app import complete_order, get_order_from_db

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

    # handle the event notifying that the stock processing has been completed
    def handle_stock_updated(self, value):
        from app import complete_order, get_order_from_db

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

    # check if the order has been succesfully processed (both stock and payment processed)
    def _order_successfully_processed(self, order_id):
        return (
            self.order_status[order_id]["payment_status"] == "SUCCESS"
            and self.order_status[order_id]["stock_status"] == "SUCCESS"
        )

    # check if payment failed but stock succeeded.
    def _payment_failed_but_stock_succeeded(self, order_id):
        return (
            self.order_status[order_id]["payment_status"] == "FAILED"
            and self.order_status[order_id]["stock_status"] == "SUCCESS"
        )

    # Check if stock failed but payment succeeded.
    def _stock_failed_but_payment_succeeded(self, order_id):
        return (
            self.order_status[order_id]["payment_status"] == "SUCCESS"
            and self.order_status[order_id]["stock_status"] == "FAILED"
        )

    def cleanup(self):
        self.connection.close()
        self.producer.close()
