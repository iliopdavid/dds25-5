import base64
import logging
import os
import atexit
import uuid
import asyncio

import redis

from msgspec import msgpack, Struct
from quart import Quart, jsonify, abort, Response
from producer import PaymentProducer
from consumer import run_payment_consumer

DB_ERROR_STR = "DB error"
REQ_ERROR_STR = "Requests error"

LOG_DIR = "logging"
LOG_FILENAME = "payment_log.txt"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILENAME)

app = Quart("payment-service")

producer = PaymentProducer()

db: redis.Redis = redis.asyncio.Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(os.environ["REDIS_DB"]),
)


async def recover_from_logs():
    app.logger.debug(f"Recovering using {LOG_PATH}")
    with open(LOG_PATH, "r") as file:
        for line in file:
            info = line.split(", ")
            await db.set(info[0], base64.b64decode(info[1]))


# For debugging
async def count_lines_in_log():
    app.logger.debug(f"Counting lines in {LOG_PATH}")
    line_count = 0
    with open(LOG_PATH, "r") as file:
        for line in file:
            line_count += 1
    app.logger.debug(f"Total lines in log: {line_count}")
    return line_count


class UserValue(Struct):
    credit: int


async def get_user_from_db(user_id: str) -> UserValue | None:
    try:
        # Get serialized data
        entry: bytes = await db.get(user_id)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    # Deserialize data if it exists else return null
    entry: UserValue | None = msgpack.decode(entry, type=UserValue) if entry else None
    if entry is None:
        # If user does not exist in the database; abort
        abort(400, f"User: {user_id} not found!")
    return entry


def log(kv_pairs: dict):
    with open(LOG_PATH, "a") as log_file:
        for k, v in kv_pairs.items():
            log_file.write(k + ", " + base64.b64encode(v).decode("utf-8") + "\n")


async def wait_for_redis(max_attempts=30, delay=1):
    for attempt in range(max_attempts):
        try:
            await db.ping()
            # app.logger.info("Redis connection established")
            return True
        except (redis.exceptions.ConnectionError, redis.exceptions.RedisError) as e:
            # app.logger.warning(
            #     f"Redis not available, attempt {attempt+1}/{max_attempts}: {e}"
            # )
            await asyncio.sleep(delay)

    app.logger.error(f"Redis connection failed after {max_attempts} attempts")
    return False


@app.before_serving
async def startup():
    if not await wait_for_redis():
        app.logger.error("Cannot start application without Redis")

    """App startup logic."""
    if os.path.exists(LOG_PATH):
        await recover_from_logs()
    else:
        try:
            with open(LOG_PATH, "x"):
                pass
            app.logger.debug(f"Log file created at: {LOG_PATH}")
        except FileExistsError:
            app.logger.warning(f"Log file already created by another worker.")

    await count_lines_in_log()

    await producer.init()

    asyncio.create_task(run_payment_consumer(db))

    app.logger.info("producer and consumer initialized successfully.")


@app.after_serving
async def shutdown():
    await db.close()


@app.post("/internal/recover-from-logs")
async def on_start():
    if not await wait_for_redis():
        app.logger.error("Redis connection failed during log recovery request.")
        return jsonify({"error": "Failed to connect to database"}), 500
    if os.path.exists(LOG_PATH):
        await recover_from_logs()
        return jsonify({"msg": "Recovered from logs successfully"})
    else:
        try:
            with open(LOG_PATH, "x"):
                pass
            app.logger.debug(f"Log file created at: {LOG_PATH}")
            return jsonify({"msg": "Log file created successfully"})
        except FileExistsError:
            app.logger.error("FileExistsError: Log file already exists unexpectedly")


@app.post("/create_user")
async def create_user():
    if not await wait_for_redis():
        app.logger.error("Redis connection failed")
        return jsonify({"error": "Failed to connect to database"}), 500
    key = str(uuid.uuid4())
    value = msgpack.encode(UserValue(credit=0))
    try:
        log({key: value})
        await db.set(key, value)
    except redis.exceptions.RedisError as e:
        app.logger.error(e)
        return abort(400, DB_ERROR_STR)
    return jsonify({"user_id": key})


@app.post("/batch_init/<int:n>/<int:starting_money>")
async def batch_init_users(n: int, starting_money: int):
    if not await wait_for_redis():
        app.logger.error("Redis connection failed")
        return jsonify({"error": "Failed to connect to database"}), 500

    kv_pairs: dict[str, bytes] = {
        f"{i}": msgpack.encode(UserValue(credit=starting_money)) for i in range(n)
    }
    try:
        log(kv_pairs)
        await db.mset(kv_pairs)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for users successful"})


@app.get("/find_user/<user_id>")
async def find_user(user_id: str):
    if not await wait_for_redis():
        app.logger.error("Redis connection failed")
        return jsonify({"error": "Failed to connect to database"}), 500

    user_entry: UserValue = await get_user_from_db(user_id)
    return jsonify({"user_id": user_id, "credit": user_entry.credit})


@app.post("/add_funds/<user_id>/<int:amount>")
async def add_credit(user_id: str, amount: int):
    if not await wait_for_redis():
        app.logger.error("Redis connection failed")
        return jsonify({"error": "Failed to connect to database"}), 500

    user_entry: UserValue = await get_user_from_db(user_id)
    user_entry.credit += amount
    value = msgpack.encode(user_entry)
    try:
        log({user_id: value})
        await db.set(user_id, value)
    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)
    return Response(
        f"User: {user_id} credit updated to: {user_entry.credit}", status=200
    )


@app.post("/pay/<user_id>/<int:amount>")
async def pay(user_id: str, amount: int):
    if not await wait_for_redis():
        app.logger.error("Redis connection failed")
        return jsonify({"error": "Failed to connect to database"}), 500
    """
    Based on:
        Pipelines and transactions. (n.d.). Redis Docs. https://redis.io/docs/latest/develop/clients/redis-py/transpipe/

    :param user_id:
    :param amount:
    :return:
    """
    try:
        async with db.pipeline() as pipe:
            # Repeat until successful.
            while True:
                try:
                    # Watch the key we are about to change.
                    pipe.watch(user_id)

                    # The pipeline executes commands directly (instead of buffering them) from immediately after the
                    # `watch()` call until we begin the transaction.
                    user_bytes = await pipe.get(user_id)
                    if not user_bytes:
                        pipe.unwatch()
                        abort(400, f"User {user_id} not found!")

                    user_entry = msgpack.decode(user_bytes, type=UserValue)

                    if user_entry.credit < amount:
                        pipe.unwatch()
                        abort(400, f"User {user_id} does not have enough credit.")

                    # Apply deduction
                    user_entry.credit -= amount
                    encoded_user = msgpack.encode(user_entry)

                    # Start the transaction, which will enable buffering again for the remaining commands.
                    pipe.multi()
                    pipe.set(user_id, encoded_user)
                    await pipe.execute()

                    log({user_id: encoded_user})

                    # The transaction succeeded, so break out of the loop.
                    break
                except redis.WatchError:
                    # The transaction failed, so continue with the next attempt.
                    continue

    except redis.exceptions.RedisError:
        return abort(400, DB_ERROR_STR)

    return jsonify({"paid": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
