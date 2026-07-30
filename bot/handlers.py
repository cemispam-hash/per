"""Основные хендлеры: меню, каталог, заказы, профиль."""

import html
import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import db
import keyboards as kb
import paypalych
import texts
from config import MAX_QTY, MSK, ORDER_TTL_MINUTES

log = logging.getLogger(__name__)

AWAIT_PROMO = "await_promo"
AWAIT_TOPUP = "await_topup"


# --- утилиты ----------------------------------------------------------------

async def _edit(update: Update, text: str, markup=None) -> None:
    """Безопасно редактирует сообщение под инлайн-кнопкой."""
    try:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=markup,
            disable_web_page_preview=True,
        )
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(MSK)


# --- главное меню -----------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name)
    context.user_data.clear()
    await update.effective_message.reply_text(
        texts.WELCOME, parse_mode=ParseMode.HTML, reply_markup=kb.main_menu()
    )


async def home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.delete()
        except BadRequest:
            pass
    await update.effective_chat.send_message(
        texts.WELCOME, parse_mode=ParseMode.HTML, reply_markup=kb.main_menu()
    )


async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(AWAIT_PROMO, None)
    if update.callback_query:
        await update.callback_query.answer()
        await _edit(update, texts.BUY, kb.buy_menu())
    else:
        await update.effective_message.reply_text(
            texts.BUY, parse_mode=ParseMode.HTML, reply_markup=kb.buy_menu()
        )


async def subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    context.user_data.pop(AWAIT_PROMO, None)
    await _edit(update, texts.SUBSCRIPTIONS, kb.subscriptions(db.list_products()))


# --- карточка товара --------------------------------------------------------

def _clamp_qty(qty: int, stock: int) -> int:
    return max(1, min(qty, MAX_QTY, stock or 1))


async def _show_product(update: Update, product_id: int, qty: int) -> None:
    product = db.get_product(product_id)
    if not product:
        await update.callback_query.answer("Товар недоступен", show_alert=True)
        return
    stock = db.stock_count(product_id)
    qty = _clamp_qty(qty, stock)
    await _edit(
        update,
        texts.product_card(product["title"], stock, product["price"], product["duration_days"]),
        kb.product_card(product_id, qty, product["price"], product["title"]),
    )


async def product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    context.user_data.pop(AWAIT_PROMO, None)
    _, product_id, qty = update.callback_query.data.split(":")
    await _show_product(update, int(product_id), int(qty))


async def change_qty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _, product_id, qty, delta = update.callback_query.data.split(":")
    product_id, qty, delta = int(product_id), int(qty), int(delta)
    stock = db.stock_count(product_id)
    new_qty = _clamp_qty(qty + delta, stock)
    if new_qty == qty:
        limit = "Минимум 1 шт" if delta < 0 else f"Доступно {stock} шт"
        await update.callback_query.answer(limit)
        return
    await update.callback_query.answer()
    await _show_product(update, product_id, new_qty)


async def noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()


# --- промокод ---------------------------------------------------------------

async def ask_promo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    _, product_id, qty = update.callback_query.data.split(":")
    context.user_data[AWAIT_PROMO] = (int(product_id), int(qty))
    await _edit(update, texts.PROMO_ASK, kb.back_to(f"prod:{product_id}:{qty}"))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ввод промокода или суммы пополнения."""
    text = (update.effective_message.text or "").strip()

    if AWAIT_PROMO in context.user_data:
        product_id, qty = context.user_data.pop(AWAIT_PROMO)
        promo = db.get_promo(text)
        if not promo or not db.promo_is_valid(promo):
            await update.effective_message.reply_text(texts.PROMO_BAD)
            context.user_data[AWAIT_PROMO] = (product_id, qty)
            return
        context.user_data["promo"] = promo["code"]
        await update.effective_message.reply_text(
            f"✅ Промокод <b>{html.escape(promo['code'])}</b> применён: "
            f"−{promo['percent']}% к заказу.",
            parse_mode=ParseMode.HTML,
        )
        await _create_order(update, context, product_id, qty)
        return

    if AWAIT_TOPUP in context.user_data:
        if not text.isdigit() or int(text) <= 0:
            await update.effective_message.reply_text("Введите сумму числом, например: 790")
            return
        context.user_data.pop(AWAIT_TOPUP)
        await update.effective_message.reply_text(
            f"💰 Пополнение на <b>{int(text)}₽</b>.\n\n" + texts.PAYMENT_UNAVAILABLE,
            parse_mode=ParseMode.HTML,
            reply_markup=kb.link_menu("support"),
        )
        return

    await update.effective_message.reply_text(
        "Выберите раздел на клавиатуре ниже.", reply_markup=kb.main_menu()
    )


# --- заказ ------------------------------------------------------------------

def _amount(price: int, qty: int, percent: int) -> int:
    total = price * qty
    return max(1, round(total * (100 - percent) / 100))


async def buy_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    _, product_id, qty = update.callback_query.data.split(":")
    await _create_order(update, context, int(product_id), int(qty))


async def _create_order(
    update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int, qty: int
) -> None:
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name)
    product = db.get_product(product_id)
    if not product:
        await update.effective_chat.send_message("Товар недоступен.")
        return

    promo_code = context.user_data.get("promo")
    promo = db.get_promo(promo_code) if promo_code else None
    if promo and not db.promo_is_valid(promo):
        promo = None
        context.user_data.pop("promo", None)
    percent = promo["percent"] if promo else 0

    qty = _clamp_qty(qty, db.stock_count(product_id))
    amount = _amount(product["price"], qty, percent)
    order = db.create_order(user.id, product_id, qty, amount, promo["id"] if promo else None)

    if not db.reserve_codes(order["id"], product_id, qty):
        db.set_order_status(order["id"], "cancelled")
        await update.effective_chat.send_message(texts.NO_STOCK)
        return

    expires = _parse_dt(order["expires_at"])
    context.job_queue.run_once(
        expire_order_job,
        when=expires,
        data={"order_id": order["id"], "chat_id": update.effective_chat.id},
        name=f"expire:{order['id']}",
    )
    await update.effective_chat.send_message(
        texts.order_card(
            order["id"], product["title"], qty, amount, ORDER_TTL_MINUTES, expires,
            promo["code"] if promo else None,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.order_card(order["id"]),
    )


async def expire_order_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    order_id = context.job.data["order_id"]
    order = db.get_order(order_id)
    if not order or order["status"] != "pending":
        return
    db.set_order_status(order_id, "expired")
    db.release_codes(order_id)
    await context.bot.send_message(
        context.job.data["chat_id"],
        f"{texts.ORDER_EXPIRED}\nНомер заказа: <code>{order_id}</code>",
        parse_mode=ParseMode.HTML,
    )


def _cancel_expire_job(context: ContextTypes.DEFAULT_TYPE, order_id: str) -> None:
    for job in context.job_queue.get_jobs_by_name(f"expire:{order_id}"):
        job.schedule_removal()


async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _, order_id, action = update.callback_query.data.split(":")
    order = db.get_order(order_id)
    if not order or order["user_id"] != update.effective_user.id:
        await update.callback_query.answer("Заказ не найден", show_alert=True)
        return
    if order["status"] != "pending":
        await update.callback_query.answer("Заказ уже закрыт", show_alert=True)
        return

    if action == "cancel":
        await update.callback_query.answer()
        db.set_order_status(order_id, "cancelled")
        db.release_codes(order_id)
        _cancel_expire_job(context, order_id)
        await _edit(update, f"{texts.ORDER_CANCELLED}\n<code>{order_id}</code>")
        return

    if action == "bal":
        user = db.get_user(update.effective_user.id)
        if user["balance"] < order["amount"]:
            await update.callback_query.answer(texts.NOT_ENOUGH_BALANCE, show_alert=True)
            return
        await update.callback_query.answer()
        db.change_balance(user["tg_id"], -order["amount"])
        await complete_order(update, context, order_id)
        return

    if action == "pp":
        await update.callback_query.answer()
        product = db.get_product(order["product_id"])
        bill = await paypalych.create_bill(
            order_id, order["amount"], f"{product['title']} × {order['qty']}"
        )
        if not bill:
            await update.callback_query.answer(texts.PAYMENT_UNAVAILABLE, show_alert=True)
            return
        db.create_payment(order_id, "paypalych", bill["id"], bill["url"])
        await update.callback_query.edit_message_reply_markup(
            reply_markup=kb.order_card(order_id, bill["url"])
        )
        return

    if action == "chk":
        payment_row = db.get_payment(order_id)
        if not payment_row:
            await update.callback_query.answer(texts.PAYMENT_PENDING, show_alert=True)
            return
        status = await paypalych.bill_status(payment_row["external_id"])
        if status != "SUCCESS":
            await update.callback_query.answer(texts.PAYMENT_PENDING, show_alert=True)
            return
        await update.callback_query.answer()
        db.set_payment_status(payment_row["id"], "paid")
        await complete_order(update, context, order_id)


async def complete_order(
    update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str
) -> None:
    order = db.get_order(order_id)
    product = db.get_product(order["product_id"])
    db.set_order_status(order_id, "paid")
    _cancel_expire_job(context, order_id)
    if order["promo_id"]:
        db.execute("UPDATE promos SET uses = uses + 1 WHERE id = ?", (order["promo_id"],))
    context.user_data.pop("promo", None)

    codes = db.order_codes(order_id)
    codes_block = "\n".join(f"<code>{html.escape(code)}</code>" for code in codes)
    text = (
        f"✅ <b>Заказ оплачен</b> · <code>{order_id}</code>\n\n"
        f"Товар: <b>{product['title']}</b>\n"
        f"Кол-во: {order['qty']} шт\n"
        f"Сумма: <b>{order['amount']}₽</b>\n\n"
        f"🔑 Код активации:\n{codes_block}\n\n"
        "Коды всегда доступны в разделе «Мой профиль» → «Мои покупки»."
    )
    if update.callback_query:
        await _edit(update, text, kb.link_menu("manual"))
    else:
        await update.effective_chat.send_message(
            text, parse_mode=ParseMode.HTML, reply_markup=kb.link_menu("manual")
        )


# --- профиль ----------------------------------------------------------------

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    user = db.upsert_user(tg_user.id, tg_user.username, tg_user.first_name)
    text = texts.profile(user["tg_id"], user["balance"], db.purchases_count(user["tg_id"]))
    if update.callback_query:
        await update.callback_query.answer()
        await _edit(update, text, kb.profile())
    else:
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=kb.profile()
        )


async def purchases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    orders = db.user_orders(update.effective_user.id)
    if not orders:
        await _edit(update, texts.NO_PURCHASES, kb.back_to("profile"))
        return
    blocks = []
    for order in orders[:20]:
        codes = "\n".join(f"<code>{html.escape(c)}</code>" for c in db.order_codes(order["id"]))
        blocks.append(
            f"🧾 <code>{order['id']}</code> · {html.escape(order['title'])}\n"
            f"{_parse_dt(order['created_at']).strftime('%d.%m.%Y %H:%M')} · "
            f"{order['qty']} шт · {order['amount']}₽\n{codes}"
        )
    await _edit(update, "🗂 <b>Мои покупки</b>\n\n" + "\n\n".join(blocks), kb.back_to("profile"))


async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    context.user_data[AWAIT_TOPUP] = True
    await _edit(update, texts.TOPUP_ASK, kb.back_to("profile"))


# --- статические разделы ----------------------------------------------------

async def manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        texts.MANUAL, parse_mode=ParseMode.HTML, reply_markup=kb.link_menu("manual")
    )


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        texts.NEWS, parse_mode=ParseMode.HTML, reply_markup=kb.link_menu("news")
    )


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        texts.SUPPORT, parse_mode=ParseMode.HTML, reply_markup=kb.link_menu("support")
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Ошибка обработки апдейта", exc_info=context.error)
