import unittest
import utils as tu
import uuid


class TestMicroservices(unittest.TestCase):

    def test_stock(self):
        # Test /stock/item/create/<price>
        item: dict = tu.create_item(5)
        self.assertIn('item_id', item)

        item_id: str = item['item_id']

        # Test /stock/find/<item_id>
        item: dict = tu.find_item(item_id)
        self.assertEqual(item['price'], 5)
        self.assertEqual(item['stock'], 0)

        # Test /stock/add/<item_id>/<number>
        add_stock_response = tu.add_stock(item_id, 50)
        self.assertTrue(200 <= int(add_stock_response) < 300)

        stock_after_add: int = tu.find_item(item_id)['stock']
        self.assertEqual(stock_after_add, 50)

        # Test /stock/subtract/<item_id>/<number>
        over_subtract_stock_response = tu.subtract_stock(item_id, 200)
        self.assertTrue(tu.status_code_is_failure(int(over_subtract_stock_response)))

        subtract_stock_response = tu.subtract_stock(item_id, 15)
        self.assertTrue(tu.status_code_is_success(int(subtract_stock_response)))

        stock_after_subtract: int = tu.find_item(item_id)['stock']
        self.assertEqual(stock_after_subtract, 35)

    def test_payment(self):
        # Test /payment/pay/<user_id>/<order_id>
        user: dict = tu.create_user()
        self.assertIn('user_id', user)

        user_id: str = user['user_id']

        # Test /users/credit/add/<user_id>/<amount>
        add_credit_response = tu.add_credit_to_user(user_id, 15)
        self.assertTrue(tu.status_code_is_success(add_credit_response))

        # add item to the stock service
        item: dict = tu.create_item(5)
        self.assertIn('item_id', item)

        item_id: str = item['item_id']

        add_stock_response = tu.add_stock(item_id, 50)
        self.assertTrue(tu.status_code_is_success(add_stock_response))

        # create order in the order service and add item to the order
        order: dict = tu.create_order(user_id)
        self.assertIn('order_id', order)

        order_id: str = order['order_id']

        add_item_response = tu.add_item_to_order(order_id, item_id, 1)
        self.assertTrue(tu.status_code_is_success(add_item_response))

        add_item_response = tu.add_item_to_order(order_id, item_id, 1)
        self.assertTrue(tu.status_code_is_success(add_item_response))
        add_item_response = tu.add_item_to_order(order_id, item_id, 1)
        self.assertTrue(tu.status_code_is_success(add_item_response))

        payment_response = tu.payment_pay(user_id, 10)
        self.assertTrue(tu.status_code_is_success(payment_response))

        credit_after_payment: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit_after_payment, 5)

    def test_order(self):
        # Test /payment/pay/<user_id>/<order_id>
        user: dict = tu.create_user()
        self.assertIn('user_id', user)

        user_id: str = user['user_id']

        # create order in the order service and add item to the order
        order: dict = tu.create_order(user_id)
        self.assertIn('order_id', order)

        order_id: str = order['order_id']

        # add item to the stock service
        item1: dict = tu.create_item(5)
        self.assertIn('item_id', item1)
        item_id1: str = item1['item_id']
        add_stock_response = tu.add_stock(item_id1, 15)
        self.assertTrue(tu.status_code_is_success(add_stock_response))

        # add item to the stock service
        item2: dict = tu.create_item(5)
        self.assertIn('item_id', item2)
        item_id2: str = item2['item_id']
        add_stock_response = tu.add_stock(item_id2, 1)
        self.assertTrue(tu.status_code_is_success(add_stock_response))

        add_item_response = tu.add_item_to_order(order_id, item_id1, 1)
        self.assertTrue(tu.status_code_is_success(add_item_response))
        add_item_response = tu.add_item_to_order(order_id, item_id2, 1)
        self.assertTrue(tu.status_code_is_success(add_item_response))
        subtract_stock_response = tu.subtract_stock(item_id2, 1)
        self.assertTrue(tu.status_code_is_success(subtract_stock_response))

        checkout_response = tu.checkout_order(order_id).status_code
        self.assertTrue(tu.status_code_is_failure(checkout_response))

        stock_after_subtract: int = tu.find_item(item_id1)['stock']
        self.assertEqual(stock_after_subtract, 15)

        add_stock_response = tu.add_stock(item_id2, 15)
        self.assertTrue(tu.status_code_is_success(int(add_stock_response)))

        credit_after_payment: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit_after_payment, 0)

        checkout_response = tu.checkout_order(order_id).status_code
        self.assertTrue(tu.status_code_is_failure(checkout_response))

        add_credit_response = tu.add_credit_to_user(user_id, 15)
        self.assertTrue(tu.status_code_is_success(int(add_credit_response)))

        credit: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit, 15)

        stock: int = tu.find_item(item_id1)['stock']
        self.assertEqual(stock, 15)

        checkout_response = tu.checkout_order(order_id)
        print(checkout_response.text)
        self.assertTrue(tu.status_code_is_success(checkout_response.status_code))

        stock_after_subtract: int = tu.find_item(item_id1)['stock']
        self.assertEqual(stock_after_subtract, 14)

        credit: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit, 5)
    
    def test_saga_checkout_happy_path(self):
        user = tu.create_user()
        user_id = user['user_id']
        tu.add_credit_to_user(user_id, 20)

        item = tu.create_item(5)
        item_id = item['item_id']
        tu.add_stock(item_id, 10)

        order = tu.create_order(user_id)
        order_id = order['order_id']
        tu.add_item_to_order(order_id, item_id, 2)  # total = 10

        response = tu.checkout_order(order_id)
        self.assertTrue(tu.status_code_is_success(response.status_code), "Checkout should succeed")

        remaining_stock = tu.find_item(item_id)['stock']
        self.assertEqual(remaining_stock, 8, "Stock should be reduced by 2")

        remaining_credit = tu.find_user(user_id)['credit']
        self.assertEqual(remaining_credit, 10, "Credit should be reduced by 10")

    def test_saga_checkout_stock_failure(self):
        user = tu.create_user()
        user_id = user['user_id']
        tu.add_credit_to_user(user_id, 20)

        item = tu.create_item(5)
        item_id = item['item_id']
        tu.add_stock(item_id, 1)  # only 1 item

        order = tu.create_order(user_id)
        order_id = order['order_id']
        tu.add_item_to_order(order_id, item_id, 2)  # try to buy 2

        response = tu.checkout_order(order_id)
        self.assertTrue(tu.status_code_is_failure(response.status_code), "Checkout should fail due to stock")

        remaining_stock = tu.find_item(item_id)['stock']
        self.assertEqual(remaining_stock, 1, "Stock should not be reduced")

        remaining_credit = tu.find_user(user_id)['credit']
        self.assertEqual(remaining_credit, 20, "Credit should not be charged")

    def test_saga_checkout_payment_failure(self):
        user = tu.create_user()
        user_id = user['user_id']
        tu.add_credit_to_user(user_id, 5)  # not enough for total

        item = tu.create_item(10)
        item_id = item['item_id']
        tu.add_stock(item_id, 5)

        order = tu.create_order(user_id)
        order_id = order['order_id']
        tu.add_item_to_order(order_id, item_id, 1)  # total = 10

        response = tu.checkout_order(order_id)
        self.assertTrue(tu.status_code_is_failure(response.status_code), "Checkout should fail due to insufficient credit")

        remaining_stock = tu.find_item(item_id)['stock']
        self.assertEqual(remaining_stock, 5, "Stock should be compensated (rollback)")

        remaining_credit = tu.find_user(user_id)['credit']
        self.assertEqual(remaining_credit, 5, "Credit should not be deducted")


if __name__ == '__main__':
    unittest.main()