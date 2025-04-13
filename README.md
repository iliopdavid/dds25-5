
## Event-Driven Approach

We explored an **asynchronous, event-driven saga** using a fully decoupled message-passing model. It achieves zero inconsistencies and is resilient against database/service restarts while being faster than the synchronous SAGA approach. As I spent the entire time trying to get this to work, if you could check it out briefly along with the main branch, that would be amazing!!!!!

### Technical Overview

- The application was rewritten using **Quart**, an async web framework similar to Flask. 
- Uses **RabbitMQ** as the message broker
- Events are published and consumed asynchronously using `aio-pika`
- Checkout responses are handled asynchronously using a pub/sub mechanism
- Lua script for atomic database transactions

### Workflow 
- The Order Service sends a checkout event to the Payment Service.
- The Payment Service deducts the total cost from the user's credit. If successful, it triggers an event to the Stock Service for inventory processing.
- The Stock Service attempts to deduct stock for all items. If any item has insufficient stock, it rolls back all stock changes and sends a rollback event to the Payment Service, which then restores the user's credit.
- If all operations succeed, the Stock Service sends a success event back to the Order Service, confirming the checkout was completed successfully.


When running docker-compose, please wait a moment to allow the producer and consumer to initialize properly. 
