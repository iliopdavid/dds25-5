# Team 5 Distributed Data Assignment 2025  

We have implemented two different approaches: one using the synchronous Saga pattern and the other following an asynchronous event-driven architecture.

We would greatly appreciate it if you could also check out the event-driven implementation briefly, as it also provides fault tolerance while ensuring consistency. Main difference is that logging is better implemented for the checkout workflow in this branch, and therefore we are using it as main but the event-driven approach has a slightly better RPS. 

The event-driven approach is implemented in [rabbitmq-final branch](https://github.com/iliopdavid/dds25-5/tree/rabbitmq-final)

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

