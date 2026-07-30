"""Проверка бизнес-логики: каталог, заказ, оплата с баланса, промокод, просрочка."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.sqlite3")

import db  # noqa: E402
from handlers import _amount, _clamp_qty  # noqa: E402


class FlowTest(unittest.TestCase):
    def setUp(self):
        db._conn = None
        if os.path.exists(db.DB_PATH):
            os.remove(db.DB_PATH)
        db.init()
        self.product = db.get_product_by_code("dde_1m")
        db.add_stock(self.product["id"], [f"CODE-{i}" for i in range(5)])
        self.user = db.upsert_user(1001, "tester", "Тест")

    def test_seed_products(self):
        titles = [p["title"] for p in db.list_products()]
        self.assertEqual(
            titles, ["DDE Store • Месяц", "DDE Store • 3 Месяц", "DDE Store • 6 Месяц"]
        )
        self.assertEqual(self.product["price"], 790)

    def test_qty_clamped_by_stock(self):
        self.assertEqual(_clamp_qty(100, 5), 5)
        self.assertEqual(_clamp_qty(0, 5), 1)
        self.assertEqual(_clamp_qty(3, 5), 3)

    def test_order_id_format(self):
        oid = db.new_order_id()
        self.assertEqual(len(oid), 9)
        self.assertTrue(oid.isalnum() and oid.upper() == oid)

    def test_reserve_reduces_stock_and_release_returns_it(self):
        order = db.create_order(1001, self.product["id"], 2, 1580)
        codes = db.reserve_codes(order["id"], self.product["id"], 2)
        self.assertEqual(len(codes), 2)
        self.assertEqual(db.stock_count(self.product["id"]), 3)
        db.release_codes(order["id"])
        self.assertEqual(db.stock_count(self.product["id"]), 5)

    def test_reserve_fails_when_not_enough_stock(self):
        order = db.create_order(1001, self.product["id"], 9, 7110)
        self.assertEqual(db.reserve_codes(order["id"], self.product["id"], 9), [])
        self.assertEqual(db.stock_count(self.product["id"]), 5)

    def test_promo_discount(self):
        db.add_promo("sale10", 10, 1)
        promo = db.get_promo("SALE10")
        self.assertTrue(db.promo_is_valid(promo))
        self.assertEqual(_amount(790, 2, promo["percent"]), 1422)
        db.execute("UPDATE promos SET uses = 1 WHERE id = ?", (promo["id"],))
        self.assertFalse(db.promo_is_valid(db.get_promo("SALE10")))

    def test_paid_order_appears_in_purchases(self):
        order = db.create_order(1001, self.product["id"], 1, 790)
        db.reserve_codes(order["id"], self.product["id"], 1)
        db.change_balance(1001, 790)
        db.change_balance(1001, -790)
        db.set_order_status(order["id"], "paid")
        self.assertEqual(db.get_user(1001)["balance"], 0)
        self.assertEqual(db.purchases_count(1001), 1)
        self.assertEqual(len(db.user_orders(1001)), 1)
        self.assertEqual(len(db.order_codes(order["id"])), 1)

    def test_stale_order_expires(self):
        order = db.create_order(1001, self.product["id"], 1, 790)
        db.reserve_codes(order["id"], self.product["id"], 1)
        db.execute(
            "UPDATE orders SET expires_at = '2000-01-01T00:00:00+03:00' WHERE id = ?",
            (order["id"],),
        )
        expired = db.expire_stale_orders()
        self.assertIn(order["id"], expired)
        for oid in expired:
            db.release_codes(oid)
        self.assertEqual(db.get_order(order["id"])["status"], "expired")
        self.assertEqual(db.stock_count(self.product["id"]), 5)


if __name__ == "__main__":
    unittest.main()
