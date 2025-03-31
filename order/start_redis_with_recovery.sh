#!/bin/bash

# 0. Load environment variables from file
set -o allexport
source /usr/local/bin/order_redis.env
set +o allexport

# 1. Start Redis in the background
redis-server --requirepass "$REDIS_PASSWORD" --maxmemory 512mb --save "" --appendonly no &
REDIS_PID=$!

# 2. Wait until Redis responds
echo "Waiting for Redis to be available..."
until REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping | grep -q PONG; do
    echo "Redis is not ready yet. Retrying in 1s..."
    sleep 1
done
echo "Redis is up!"

# 3. Wait until order-service is up and respond to recovery endpoint
echo "Waiting for order-service to be available..."
until curl -s -X POST http://order-service:5000/internal/recover-from-logs; do
    echo "Order-service is not ready yet. Retrying in 2s..."
    sleep 2
done
echo "Order-service is up!"

echo "Recovery triggered!"

# 4. Bring Redis to foreground
wait $REDIS_PID
