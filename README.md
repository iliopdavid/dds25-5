# Team 5 Distributed Data Assignment 2025
For this project we started making a synchronous implementation using a Choreography-based saga. Some effort went it to this, so we kept this implementation on a separate branch called `synchronous`. Eventually we switched to an event driven approach and stuck to that.

### Event Driven Approach
This project was rewritting with Quart, an asynchronous Python web framework that is similar to Flask but powered by asyncio. It allows for non-blocking operations, making the application more efficient and scalable. 

To keep the services decoupled, this system leverages RabbitMQ as a message broker. Events are published and consumed asynchronously, ensuring high performance and responsiveness even under load. Asynchronous RabbitMQ with `aio-pika` was used for this.

#### Key Components
- Implemented the entire **saga flow** in `order-service`, which:
  - Initiates stock subtraction (`stock-service`)
  - Initiates payment deduction (`payment-service`)
  - Finalizes the order upon success
  - Performs **compensation** in case of failure (refund payment or restore stock)
- Followed a **choreography-based pattern**: services coordinate through direct HTTP requests rather than a central orchestrator.
- Workflow is **synchronous and request-driven** — not event-based — to keep flow deterministic.
- Leveraged **Redis pipelines and optimistic locking** (`WATCH` / `MULTI` / `EXEC`) in `stock-service` and `payment-service` to:
  - Prevent race conditions in concurrent updates
  - Ensure atomicity and consistency in high-concurrency scenarios
  - Support safe retries when conflicts are detected

### Highlights

- **Choreography-based Saga**: There is no standalone orchestrator service. Instead, the `order-service` **initiates** and **coordinates** the checkout workflow as part of its domain logic.
- While the `order-service` drives the saga flow, it is still a **participant** in the system — not a central controller — so the design follows a **choreographed** rather than orchestrated pattern.
- **Synchronous choreography** simplifies tracing and debugging.
- **Optimistic concurrency control** with Redis ensures correctness without locks.