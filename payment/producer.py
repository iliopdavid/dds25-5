import pika
import json


class PaymentProducer:
    def __init__(self):
        # Connect to RabbitMQ server
        self.connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
        self.channel = self.connection.channel()

        # Declare the exchange and queue
        self.channel.exchange_declare(
            exchange="payment.exchange", exchange_type="direct"
        )

    # Send message to RabbitMQ exchange
    def send_message(self, key, event_data):
        from app import app

        try:
            # Convert data to JSON and send to the RabbitMQ exchange
            message = json.dumps(event_data)
            self.channel.basic_publish(
                exchange="payment.exchange",
                routing_key=key,
                body=message,
            )

            app.logger.debug(
                f"Message sent to exchange 'payment.exchange' with key '{key}': {message}"
            )
        except Exception as e:
            print(f"Error sending message: {str(e)}")
        # finally:
        #     # Ensure that the message is properly sent
        #     self.connection.close()
