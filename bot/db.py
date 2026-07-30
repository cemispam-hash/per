"""Слой доступа к данным (SQLite)."""

import random
import sqlite3
import string
import threading
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from config import DB_PATH, MSK, ORDER_TTL_MINUTES

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id      INTEGER PRIMARY KEY,
    username   TEXT,
    first_name TEXT,
    balance    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    price         INTEGER NOT NULL,
    duration_days INTEGER NOT NULL,
    sort          INTEGER NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS stock (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    value      TEXT NOT NULL,
    order_id   TEXT REFERENCES orders(id),
    issued_at  TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id         TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(tg_id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty        INTEGER NOT NULL,
    amount     INTEGER NOT NULL,
    promo_id   INTEGER REFERENCES promos(id),
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    paid_at    TEXT
);

CREATE TABLE IF NOT EXISTS promos (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    code     TEXT UNIQUE NOT NULL,
    percent  INTEGER NOT NULL DEFAULT 0,
    max_uses INTEGER NOT NULL DEFAULT 0,
    uses     INTEGER NOT NULL DEFAULT 0,
    active   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT NOT NULL REFERENCES orders(id),
    provider    TEXT NOT NULL,
    external_id TEXT,
    url         TEXT,
    status      TEXT NOT NULL DEFAULT 'created',
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stock_free ON stock(product_id, order_id);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, status);
"""

SEED_PRODUCTS = [
    ("dde_1m", "DDE Store • Месяц", 790, 30, 1),
    ("dde_3m", "DDE Store • 3 Месяц", 1490, 90, 2),
    ("dde_6m", "DDE Store • 6 Месяц", 2490, 180, 3),
]


def now() -> datetime:
    return datetime.now(MSK)


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.execute("PRAGMA journal_mode = WAL")
    return _conn


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    conn = connect()
    with _lock:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    conn = connect()
    with _lock:
        return conn.execute(sql, tuple(params)).fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    rows = query(sql, params)
    return rows[0] if rows else None


def init() -> None:
    conn = connect()
    with _lock:
        conn.executescript(SCHEMA)
        conn.commit()
    for code, title, price, days, sort in SEED_PRODUCTS:
        execute(
            "INSERT OR IGNORE INTO products (code, title, price, duration_days, sort)"
            " VALUES (?, ?, ?, ?, ?)",
            (code, title, price, days, sort),
        )


# --- пользователи -----------------------------------------------------------

def upsert_user(tg_id: int, username: Optional[str], first_name: Optional[str]) -> sqlite3.Row:
    execute(
        "INSERT INTO users (tg_id, username, first_name, created_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(tg_id) DO UPDATE SET username = excluded.username,"
        " first_name = excluded.first_name",
        (tg_id, username, first_name, now().isoformat()),
    )
    return get_user(tg_id)


def get_user(tg_id: int) -> Optional[sqlite3.Row]:
    return query_one("SELECT * FROM users WHERE tg_id = ?", (tg_id,))


def change_balance(tg_id: int, delta: int) -> None:
    execute("UPDATE users SET balance = balance + ? WHERE tg_id = ?", (delta, tg_id))


# --- товары -----------------------------------------------------------------

def list_products() -> list[sqlite3.Row]:
    return query("SELECT * FROM products WHERE active = 1 ORDER BY sort, id")


def get_product(product_id: int) -> Optional[sqlite3.Row]:
    return query_one("SELECT * FROM products WHERE id = ?", (product_id,))


def get_product_by_code(code: str) -> Optional[sqlite3.Row]:
    return query_one("SELECT * FROM products WHERE code = ?", (code,))


def stock_count(product_id: int) -> int:
    row = query_one(
        "SELECT COUNT(*) AS c FROM stock WHERE product_id = ? AND order_id IS NULL",
        (product_id,),
    )
    return row["c"] if row else 0


def add_stock(product_id: int, values: list[str]) -> int:
    for value in values:
        execute("INSERT INTO stock (product_id, value) VALUES (?, ?)", (product_id, value))
    return len(values)


# --- промокоды --------------------------------------------------------------

def get_promo(code: str) -> Optional[sqlite3.Row]:
    return query_one("SELECT * FROM promos WHERE code = ? COLLATE NOCASE", (code,))


def promo_is_valid(promo: sqlite3.Row) -> bool:
    if not promo["active"]:
        return False
    return promo["max_uses"] == 0 or promo["uses"] < promo["max_uses"]


def add_promo(code: str, percent: int, max_uses: int) -> None:
    execute(
        "INSERT INTO promos (code, percent, max_uses) VALUES (?, ?, ?)"
        " ON CONFLICT(code) DO UPDATE SET percent = excluded.percent,"
        " max_uses = excluded.max_uses, active = 1",
        (code.upper(), percent, max_uses),
    )


# --- заказы -----------------------------------------------------------------

ORDER_ID_ALPHABET = string.ascii_uppercase + string.digits


def new_order_id() -> str:
    while True:
        oid = "".join(random.choice(ORDER_ID_ALPHABET) for _ in range(9))
        if not query_one("SELECT 1 FROM orders WHERE id = ?", (oid,)):
            return oid


def create_order(
    user_id: int,
    product_id: int,
    qty: int,
    amount: int,
    promo_id: Optional[int] = None,
) -> sqlite3.Row:
    oid = new_order_id()
    created = now()
    expires = created + timedelta(minutes=ORDER_TTL_MINUTES)
    execute(
        "INSERT INTO orders (id, user_id, product_id, qty, amount, promo_id, created_at,"
        " expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            oid,
            user_id,
            product_id,
            qty,
            amount,
            promo_id,
            created.isoformat(),
            expires.isoformat(),
        ),
    )
    return get_order(oid)


def get_order(order_id: str) -> Optional[sqlite3.Row]:
    return query_one("SELECT * FROM orders WHERE id = ?", (order_id,))


def set_order_status(order_id: str, status: str) -> None:
    paid_at = now().isoformat() if status == "paid" else None
    execute(
        "UPDATE orders SET status = ?, paid_at = COALESCE(?, paid_at) WHERE id = ?",
        (status, paid_at, order_id),
    )


def expire_stale_orders() -> list[str]:
    rows = query(
        "SELECT id FROM orders WHERE status = 'pending' AND expires_at < ?",
        (now().isoformat(),),
    )
    for row in rows:
        set_order_status(row["id"], "expired")
    return [row["id"] for row in rows]


def reserve_codes(order_id: str, product_id: int, qty: int) -> list[str]:
    """Закрепляет за заказом qty кодов. Пустой список — если товара не хватило."""
    conn = connect()
    with _lock:
        cur = conn.execute(
            "SELECT id, value FROM stock WHERE product_id = ? AND order_id IS NULL"
            " ORDER BY id LIMIT ?",
            (product_id, qty),
        )
        rows = cur.fetchall()
        if len(rows) < qty:
            conn.rollback()
            return []
        stamp = now().isoformat()
        conn.executemany(
            "UPDATE stock SET order_id = ?, issued_at = ? WHERE id = ?",
            [(order_id, stamp, row["id"]) for row in rows],
        )
        conn.commit()
        return [row["value"] for row in rows]


def release_codes(order_id: str) -> None:
    """Возвращает зарезервированные коды на склад (отмена/просрочка заказа)."""
    execute(
        "UPDATE stock SET order_id = NULL, issued_at = NULL WHERE order_id = ?", (order_id,)
    )


def order_codes(order_id: str) -> list[str]:
    return [
        row["value"]
        for row in query("SELECT value FROM stock WHERE order_id = ? ORDER BY id", (order_id,))
    ]


def user_orders(user_id: int, status: str = "paid") -> list[sqlite3.Row]:
    return query(
        "SELECT o.*, p.title FROM orders o JOIN products p ON p.id = o.product_id"
        " WHERE o.user_id = ? AND o.status = ? ORDER BY o.created_at DESC",
        (user_id, status),
    )


def purchases_count(user_id: int) -> int:
    row = query_one(
        "SELECT COALESCE(SUM(qty), 0) AS c FROM orders WHERE user_id = ? AND status = 'paid'",
        (user_id,),
    )
    return row["c"] if row else 0


# --- платежи ----------------------------------------------------------------

def create_payment(order_id: str, provider: str, external_id: str, url: str) -> None:
    execute(
        "INSERT INTO payments (order_id, provider, external_id, url, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (order_id, provider, external_id, url, now().isoformat()),
    )


def get_payment(order_id: str) -> Optional[sqlite3.Row]:
    return query_one(
        "SELECT * FROM payments WHERE order_id = ? ORDER BY id DESC LIMIT 1", (order_id,)
    )


def set_payment_status(payment_id: int, status: str) -> None:
    execute("UPDATE payments SET status = ? WHERE id = ?", (status, payment_id))


# --- статистика -------------------------------------------------------------

def stats() -> dict:
    users = query_one("SELECT COUNT(*) AS c FROM users")["c"]
    paid = query_one("SELECT COUNT(*) AS c FROM orders WHERE status = 'paid'")["c"]
    revenue = query_one(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM orders WHERE status = 'paid'"
    )["s"]
    return {"users": users, "paid": paid, "revenue": revenue}
