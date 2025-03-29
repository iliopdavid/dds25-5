from kafka import KafkaProducer
import json


class PaymentProducer:
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers=["kafka:9092"],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

    # Send message to Kafka topic
    def send_message(self, event_data):
        self.producer.send("payment-processed", value=event_data)
        self.producer.flush()

        print(f"Message sent: {event_data}")
