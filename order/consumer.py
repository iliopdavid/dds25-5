from kafka import KafkaConsumer
import json
from producer import OrderProducer
from msgspec import msgpack

KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"


class OrderConsumer:
    def __init__(self):
        self.topics = ["payment-processed", "stock-processed"]
        self.group_id = "order"
        # Dictionary to track order status
        self.order_status = {}

        # Initialize Kafka consumer
        self.consumer = KafkaConsumer(
            *self.topics,
            bootstrap_servers=["kafka:9092"],
            group_id=self.group_id,
            auto_offset_reset="earliest",
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
        )
        self.producer = OrderProducer()

    def consume_messages(self):
        for message in self.consumer:
            self.handle_message(message)

    def handle_message(self, message):
        topic = message.topic
        value = message.value

        if topic == "payment-processed":
            self.handle_payment_processed(value)
        elif topic == "stock-processed":
            self.handle_stock_updated(value)

    def handle_payment_processed(self, value):
        from app import complete_order, get_order_from_db

        order_id = value["order_id"]
        payment_status = value["payment_status"]

        order_entry = get_order_from_db(order_id)

        # Initialize order status if not already present
        if order_id not in self.order_status:
            self.order_status[order_id] = {"payment_status": None, "stock_status": None}

        # Update the payment status
        self.order_status[order_id]["payment_status"] = payment_status

        # Check if we have both payment and stock statuses for the order
        if (
            self.order_status[order_id]["payment_status"] == "SUCCESS"
            and self.order_status[order_id]["stock_status"] == "SUCCESS"
        ):
            complete_order(order_id)
        elif (
            self.order_status[order_id]["payment_status"] == "FAILED"
            and self.order_status[order_id]["stock_status"] == "SUCCESS"
        ):
            # rollback stock service because payment failed for the order in which
            # items have been deducted from the db.
            self.producer.send_event(
                "payment-failure",
                "",
                {"order_id": order_id, "items": order_entry.items},
            )

    def handle_stock_updated(self, value):
        from app import complete_order, get_order_from_db

        order_id = value["order_id"]
        stock_status = value["stock_status"]

        order_entry = get_order_from_db(order_id)

        # Initialize order status if not already present
        if order_id not in self.order_status:
            self.order_status[order_id] = {"payment_status": None, "stock_status": None}

        # Update the stock status
        self.order_status[order_id]["stock_status"] = stock_status

        # Check if we have both payment and stock statuses for the order
        if (
            self.order_status[order_id]["payment_status"] == "SUCCESS"
            and self.order_status[order_id]["stock_status"] == "SUCCESS"
        ):
            complete_order(order_id)

        elif (
            self.order_status[order_id]["payment_status"] == "SUCCESS"
            and self.order_status[order_id]["stock_status"] == "FAILED"
        ):
            # rolleback payment service because stock processing failed for the order
            # in which user credit has been deducted
            self.producer.send_event(
                "stock-failure",
                "",
                {
                    "user_id": order_entry.user_id,
                    "total_amount": order_entry.total_cost,
                },
            )
