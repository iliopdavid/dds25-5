#!/usr/bin/env python3
import asyncio
import aiohttp
import random
import json

# Gateway URL where all requests will be sent
GATEWAY_URL = "http://localhost:8000"


async def batch_init_users(n=10, n_items=20, n_users=5, item_price=10):
    """Initialize a batch of user orders"""
    url = f"{GATEWAY_URL}/orders/batch_init/{n}/{n_items}/{n_users}/{item_price}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url) as response:
            if response.status == 200:
                result = await response.json()
                print(f"Batch initialization successful: {result}")
                return True
            else:
                print(f"Failed to initialize batch: {response.status}")
                return False


async def get_order_details(order_id):
    """Retrieve details of a specific order"""
    url = f"{GATEWAY_URL}/orders/find/{order_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                result = await response.json()
                print(f"Order details for {order_id}:")
                print(json.dumps(result, indent=2))
                return result
            else:
                print(f"Failed to get order {order_id}: {response.status}")
                return None


async def create_user():
    """Create a new user in the payment service"""
    url = f"{GATEWAY_URL}/payment/create_user"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url) as response:
                if response.status == 200:
                    result = await response.json()
                    user_id = result.get("user_id")
                    print(f"Created user with ID: {user_id}")
                    return user_id
                else:
                    error_text = await response.text()
                    print(
                        f"Failed to create user: Status {response.status}, Error: {error_text}"
                    )
                    return None
        except Exception as e:
            print(f"Error creating user: {e}")
            return None


async def create_multiple_users(count):
    """Create multiple users"""
    print(f"Creating {count} users...")
    user_ids = []
    for i in range(count):
        user_id = await create_user()
        if user_id:
            user_ids.append(user_id)

    print(f"Created {len(user_ids)} users successfully")
    return user_ids


async def create_stock_item(price=15):
    """Create a new item in the stock service"""
    url = f"{GATEWAY_URL}/stock/item/create/{price}"
    print(f"Creating stock item: {url}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url) as response:
                if response.status == 200:
                    result = await response.json()
                    item_id = result.get("item_id")
                    print(f"Created stock item with ID: {item_id}, price: {price}")
                    return item_id
                else:
                    error_text = await response.text()
                    print(
                        f"Failed to create stock item: Status {response.status}, Error: {error_text}"
                    )
                    return None
        except Exception as e:
            print(f"Error creating stock item: {e}")
            return None


async def main():
    # Create users
    print("Creating users...")
    await create_multiple_users(5)

    # Create some items
    print("Creating stock items...")
    item_ids = []
    for _ in range(10):
        price = 1
        item_id = await create_stock_item(price)
        if item_id:
            item_ids.append(item_id)

    # Initialize batch of users with orders (which has items)
    print("Initializing batch of users and orders...")
    await batch_init_users(n=5, n_items=10, n_users=3, item_price=15)


if __name__ == "__main__":
    asyncio.run(main())
