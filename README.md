
## Event-Driven Approach

We explored an **asynchronous, event-driven saga** using a fully decoupled message-passing model. It achieves zero inconsistencies and is resilient against database/service restarts. 

### Technical Overview

- Rewritten using **Quart**, an async web framework similar to Flask but built on `asyncio`
- Uses **RabbitMQ** as the message broker
- Events are published and consumed asynchronously using `aio-pika`

This architecture aimed to provide:

- **High concurrency and responsiveness**
- **Loose coupling between services**
- **Non-blocking message handling**
