import json
import pika


class OrderProducer:
    def __init__(self, max_retries=5, retry_delay=5):
        self.connection = None
        self.channel = None
        self._connect()

        self.channel.exchange_declare(
            exchange="order.exchange", exchange_type="topic", durable=True
        )

    def _connect(self):
        from app import app

        try:
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters("rabbitmq")
            )
            self.channel = self.connection.channel()
            self.channel.exchange_declare(
                exchange="order.exchange", exchange_type="topic", durable=True
            )
        except Exception as e:
            app.logger.error(f"Failed to connect to RabbitMQ: {e}")
            self.connection = None
            self.channel = None

    def _ensure_connection(self):
        from app import app

        if not self.connection or self.connection.is_closed:
            app.logger.warning("RabbitMQ connection lost. Reconnecting...")
            self._connect()

    def send_event(self, routing_key, message):
        from app import app

        if not self.connection or self.connection.is_closed:
            app.logger.error("RabbitMQ channel is closed. Reconnecting...")
            # Note: _connect might fail and leave self.channel as None, which could cause errors below.
            # Consider adding a check after _connect() or more robust error handling.
            try:
                self._connect()
                if not self.channel:
                    # If connection failed, raise an error immediately or handle appropriately
                    raise ConnectionError(
                        "Failed to reconnect to RabbitMQ in send_event"
                    )
            except Exception as connect_err:
                # Log connection error and re-raise or handle
                app.logger.error(
                    f"Error during reconnect attempt in send_event: {connect_err}",
                    exc_info=True,
                )
                raise ConnectionError(
                    f"Failed to reconnect: {connect_err}"
                ) from connect_err

        try:
            # Ensure channel is usable after potential reconnect attempt
            if not self.channel or self.channel.is_closed:
                # This condition might occur if _connect fails silently or channel closes again quickly
                raise pika.exceptions.ChannelWrongStateError(
                    "Channel is not available or closed after connection check."
                )

            # Attempt to serialize the message
            try:
                message_body = json.dumps(message)
            except TypeError as json_err:
                # Catch specific JSON serialization errors
                app.logger.error(
                    f"Failed to serialize message to JSON for routing key '{routing_key}'. Check data types. Error: {json_err}",
                    exc_info=True,
                )
                # Re-raise or handle as appropriate - maybe don't raise to avoid crashing worker? Depends on desired behavior.
                raise  # Re-raise by default

            # Attempt to publish
            self.channel.basic_publish(
                exchange="order.exchange",
                routing_key=routing_key,
                body=message_body,
            )
            app.logger.debug(
                f"Message sent to exchange 'order.exchange' with key '{routing_key}': {message_body}"
            )

        # --- MODIFIED EXCEPTION BLOCK ---
        except Exception as e:
            # Use logger.exception() to automatically include traceback
            error_context = (
                f"Error sending event with routing key '{routing_key}' to RabbitMQ."
            )
            # Log the context message along with exception info + traceback
            app.logger.exception(error_context)

            # Optional: Log specific details if needed (be careful with sensitive data in 'message')
            # app.logger.debug(f"Exception type: {type(e).__name__}")
            # app.logger.debug(f"Message content during error (partial): {str(message)[:200]}") # Log truncated message if safe

            # Re-raise the exception so the caller knows something went wrong
            raise
        # --- END MODIFICATION ---

    # Notify that the order checkout has been placed.
    def send_checkout_called(self, order_id, user_id, total_amount, items):
        message = {
            "order_id": order_id,
            "user_id": user_id,
            "total_amount": total_amount,
            "items": items,
        }
        self.send_event("order.checkout", message)

    # Send an event notifying other services that checkout has been completed
    def send_checkout_completed(self, order_id):
        message = {"order_id": order_id, "status": "COMPLETED"}
        self.send_event("order.completed", message)

    # Send an event notifying other services that checkout has failed
    def send_checkout_failed(self, order_id, reason):
        message = {"order_id": order_id, "status": "FAILED", "reason": reason}
        self.send_event("order.failed", message)

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
