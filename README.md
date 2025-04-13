
## Event-Driven Approach

We explored an **asynchronous, event-driven saga** using a fully decoupled message-passing model. It achieves zero inconsistencies and is resilient against database/service restarts while being faster than the synchronous SAGA approach. As I spent the entire time trying to get this to work, if you could check it out briefly along with the main branch, that would be amazing!!!!!

### Technical Overview

- The application was rewritten using **Quart**, an async web framework similar to Flask. 
- Uses **RabbitMQ** as the message broker
- Events are published and consumed asynchronously using `aio-pika`
- Checkout responses are handled asynchronously using a pub/sub mechanism
- Lua script for atomic database transactions

When running docker-compose, please wait a moment to allow the producer and consumer to initialize properly. 
