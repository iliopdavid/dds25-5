import pika
import time


class RabbitMQConnection:
    def __init__(self, host="rabbitmq", max_retries=5, retry_delay=5):
        self.host = host
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connection = None
        self.channel = None
        self._connect()

    def _connect(self):
        from app import app

        app.logger.debug("Trying to connect....")

        """Attempt to connect to RabbitMQ with retry logic."""
        retries = 0
        while retries < self.max_retries:
            try:
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(host=self.host)
                )
                self.channel = self.connection.channel()
                app.logger.debug("Successfully connected to RabbitMQ.")
                return
            except pika.exceptions.AMQPConnectionError as e:
                retries += 1
                app.logger.error(
                    f"Attempt {retries}/{self.max_retries} - Error connecting to RabbitMQ: {e}"
                )
                if retries < self.max_retries:
                    app.logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    app.logger.error(
                        "Max retries reached. Could not connect to RabbitMQ."
                    )
                    raise e

    def declare_exchanges(self, exchanges):
        from app import app

        """Declare multiple exchanges."""
        for exchange, exchange_type in exchanges.items():
            self.channel.exchange_declare(
                exchange=exchange, exchange_type=exchange_type
            )
            app.logger.debug(
                f"Declared exchange '{exchange}' of type '{exchange_type}'."
            )

    def declare_queues(self, queues):
        from app import app

        """Declare multiple queues."""
        for queue in queues:
            self.channel.queue_declare(queue=queue)
            app.logger.debug(f"Declared queue '{queue}'.")

    def close(self):
        from app import app

        """Close the connection."""
        if self.connection and self.connection.is_open:
            self.connection.close()
            app.logger.debug("RabbitMQ connection closed.")
