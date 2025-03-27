import unittest
import utils as tu
import uuid


class TestMicroservices(unittest.TestCase):

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

    def test_manual_payment_and_cancel(self):
        user = tu.create_user()
        user_id = user['user_id']
        tu.add_credit_to_user(user_id, 20)

        order_id = str(uuid.uuid4())  # Unique order ID
        status = tu.payment_pay(user_id, order_id, 10)
        self.assertTrue(tu.status_code_is_success(status), "Payment should succeed")

        credit_after_pay = tu.find_user(user_id)['credit']
        self.assertEqual(credit_after_pay, 10)

        status = tu.payment_cancel(user_id, order_id)
        self.assertTrue(tu.status_code_is_success(status), "Cancel should succeed")

        credit_after_cancel = tu.find_user(user_id)['credit']
        self.assertEqual(credit_after_cancel, 20)



if __name__ == '__main__':
    unittest.main()
