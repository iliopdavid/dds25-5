# Team 5 Distributed Data Assignment 2025  
## Saga Workflow and Choreography Logic

This repository contains our primary implementation of a distributed checkout system using the **Saga pattern** with **synchronous choreography**.

### Key Components

- Implemented the entire saga flow in **order-service**, which:
  - Initiates stock subtraction (**stock-service**)
  - Initiates payment deduction (**payment-service**)
  - Finalizes the order upon success
  - Performs **compensation** in case of failure (refund payment or restore stock)

- Followed a **choreography-based pattern**: Services coordinate through **direct HTTP requests**, not a central orchestrator.

- Workflow is **synchronous and request-driven** (not event-based), which keeps the flow **deterministic** and easier to debug.

- Leveraged **Redis pipelines** and **optimistic locking** (`WATCH` / `MULTI` / `EXEC`) in `stock-service` and `payment-service` to:
  - Prevent **race conditions** in concurrent updates
  - Ensure **atomicity** and **consistency** in high-concurrency scenarios
  - Support **safe retries** when conflicts are detected

---

### Highlights

- **Choreography-based Saga**: No standalone orchestrator. Instead, `order-service` drives the workflow, coordinating the saga while also being a domain-bound participant.  This maintains a **choreographed design** rather than an orchestrated one.

- **Synchronous choreography** simplifies **tracing**, **error handling**, and **debugging**.

- **Optimistic concurrency control** using Redis prevents conflicts and maintains performance without locking.

---

## Logging and Recovery Logic

To ensure **fault tolerance** and **state recoverability**, each service implements logging:

- All state transitions (e.g., order placed, stock reserved, payment processed) are written to **log files**:
  ```
  logging/
  ├── order_log.txt
  ├── stock_log.txt
  └── payment_log.txt
  ```

- These logs are:
  - **Append-only** and human-readable
  - **Chronologically ordered** for replay
  - Used for **recovery after crashes**

- On startup or failure recovery, each service runs:
  ```bash
  ./start_redis_with_recovery.sh
  ```
  This script:
  - Parses the service’s log file
  - Reconstructs Redis state deterministically
  - Allows the service to resume as if it never crashed

- This decentralized logging model ensures:
  - Fast recovery with no coordination overhead
  - **No single point of failure**
  - **Replay-safe** execution aligned with the last committed operation

---

## Event-Driven Approach (Alternative Option)

> ⚠️ **Important:**  
> This version was a **parallel implementation** located in the `rabbitmq-final` branch.  

We explored an **asynchronous, event-driven saga** using a fully decoupled message-passing model:

### Technical Overview

- Rewritten using **Quart**, an async web framework similar to Flask but built on `asyncio`
- Uses **RabbitMQ** as the message broker
- Events are published and consumed asynchronously using **`aio-pika`**

This architecture aimed to provide:

- **High concurrency and responsiveness**
- **Loose coupling between services**
- **Non-blocking message handling**

### Why We Did Not Use It

While technically promising, the asynchronous version faced several **fault tolerance limitations**, such as:

- Complex compensation logic across asynchronous boundaries
- Message loss during service crashes
- Difficulties with exactly-once guarantees and recovery

Despite our efforts, these trade-offs made the async version less stable than our synchronous choreography model, so we chose **not to use it as our final submission**.

Still, feel free to test it — it’s a great example of a more reactive architecture, and we invested many hours trying to make it work.
