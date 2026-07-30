"""Клавиатуры бота."""

from urllib.parse import quote

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from config import BOT_USERNAME, MANUAL_URL, NEWS_URL, SUPPORT_URL

BTN_BUY = "🛍 Купить"
BTN_PROFILE = "👤 Мой профиль"
BTN_MANUAL = "💻 Инструкции"
BTN_NEWS = "📰 Новости"
BTN_SUPPORT = "🧑‍💻 Тех.Поддержка"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_BUY), KeyboardButton(BTN_PROFILE)],
            [KeyboardButton(BTN_MANUAL), KeyboardButton(BTN_NEWS)],
            [KeyboardButton(BTN_SUPPORT)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Сообщение...",
    )


def buy_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Подписки DDE Store", callback_data="subs")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="home")],
        ]
    )


def subscriptions(products) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{p['title']} • {p['price']}₽", callback_data=f"prod:{p['id']}:1"
            )
        ]
        for p in products
    ]
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="buy")])
    return InlineKeyboardMarkup(rows)


def product_card(product_id: int, qty: int, price: int, title: str) -> InlineKeyboardMarkup:
    share_text = quote(f"{title} в DIYORDE Store")
    share_url = (
        f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}&text={share_text}"
    )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔻", callback_data=f"qty:{product_id}:{qty}:-1"),
                InlineKeyboardButton(f"{qty} шт", callback_data="noop"),
                InlineKeyboardButton("🔺", callback_data=f"qty:{product_id}:{qty}:1"),
            ],
            [
                InlineKeyboardButton("🔻 10", callback_data=f"qty:{product_id}:{qty}:-10"),
                InlineKeyboardButton("🔺 10", callback_data=f"qty:{product_id}:{qty}:10"),
            ],
            [
                InlineKeyboardButton("🔻 100", callback_data=f"qty:{product_id}:{qty}:-100"),
                InlineKeyboardButton("🔺 100", callback_data=f"qty:{product_id}:{qty}:100"),
            ],
            [
                InlineKeyboardButton(
                    f"💳 Купить за {price * qty}₽", callback_data=f"buyit:{product_id}:{qty}"
                )
            ],
            [InlineKeyboardButton("🎟 Есть промокод", callback_data=f"promo:{product_id}:{qty}")],
            [InlineKeyboardButton("🔗 Поделиться", url=share_url)],
            [InlineKeyboardButton("‹ Назад", callback_data="subs")],
        ]
    )


def order_card(order_id: str, pay_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("💸 Оплатить с баланса", callback_data=f"pay:{order_id}:bal")]]
    if pay_url:
        rows.append([InlineKeyboardButton("PayPalych • СБП", url=pay_url)])
        rows.append([InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"pay:{order_id}:chk")])
    else:
        rows.append([InlineKeyboardButton("PayPalych • СБП", callback_data=f"pay:{order_id}:pp")])
    rows.append([InlineKeyboardButton("🛑 Отменить заказ", callback_data=f"pay:{order_id}:cancel")])
    return InlineKeyboardMarkup(rows)


def profile() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🗂 Мои покупки", callback_data="purchases")],
            [InlineKeyboardButton("💰 Пополнить баланс", callback_data="topup")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="home")],
        ]
    )


def back_to(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("‹ Назад", callback_data=callback_data)]])


def link_menu(kind: str) -> InlineKeyboardMarkup:
    url = {"manual": MANUAL_URL, "news": NEWS_URL, "support": SUPPORT_URL}[kind]
    label = {
        "manual": "📖 Открыть инструкции",
        "news": "📢 Перейти в канал",
        "support": "✍️ Написать в поддержку",
    }[kind]
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, url=url)],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="home")],
        ]
    )
