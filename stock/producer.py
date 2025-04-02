import pika
import json


class StockProducer:
    def __init__(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
        self.channel = self.connection.channel()

        self.channel.exchange_declare(exchange="stock.exchange", exchange_type="direct")

    def send_message(self, key, event_data):
        try:
            # Convert data to JSON and send to the RabbitMQ exchange
            message = json.dumps(event_data)
            self.channel.basic_publish(
                exchange="stock.exchange",
                routing_key=key,
                body=message,
            )

            print(f"Message sent: {event_data}")
        except Exception as e:
            print(f"Error sending message: {str(e)}")
        # finally:
        #     # Ensure that the message is properly sent
        #     self.connection.close()
