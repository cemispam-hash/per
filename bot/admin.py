"""Админ-команды: склад, промокоды, баланс, ручное подтверждение оплаты."""

import html

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import db
import keyboards as kb
from config import is_admin

HELP = (
    "<code>/stats</code> — статистика\n"
    "<code>/addstock КОД_ТОВАРА</code> + коды со следующих строк\n"
    "<code>/addpromo КОД ПРОЦЕНТ [ЛИМИТ]</code> — промокод\n"
    "<code>/balance TG_ID СУММА</code> — изменить баланс (можно минус)\n"
    "<code>/paid ID_ЗАКАЗА</code> — подтвердить оплату вручную"
)


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    lines = ["🛠 <b>Админ-панель</b>", ""]
    for product in db.list_products():
        lines.append(
            f"<code>{product['code']}</code> · {html.escape(product['title'])} · "
            f"{product['price']}₽ · остаток {db.stock_count(product['id'])}"
        )
    lines += ["", HELP]
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    data = db.stats()
    await update.effective_message.reply_text(
        f"📊 Пользователей: <b>{data['users']}</b>\n"
        f"Оплаченных заказов: <b>{data['paid']}</b>\n"
        f"Выручка: <b>{data['revenue']}₽</b>",
        parse_mode=ParseMode.HTML,
    )


async def addstock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    raw = (update.effective_message.text or "").split("\n")
    parts = raw[0].split()
    if len(parts) < 2 or len(raw) < 2:
        await update.effective_message.reply_text(
            "Формат:\n/addstock dde_1m\nКОД-1\nКОД-2"
        )
        return
    product = db.get_product_by_code(parts[1])
    if not product:
        await update.effective_message.reply_text("Товар с таким кодом не найден.")
        return
    values = [line.strip() for line in raw[1:] if line.strip()]
    added = db.add_stock(product["id"], values)
    await update.effective_message.reply_text(
        f"✅ Добавлено {added} шт. Остаток: {db.stock_count(product['id'])}."
    )


async def addpromo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) < 2 or not args[1].isdigit():
        await update.effective_message.reply_text("Формат: /addpromo SALE10 10 100")
        return
    max_uses = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0
    db.add_promo(args[0], int(args[1]), max_uses)
    await update.effective_message.reply_text(
        f"✅ Промокод {args[0].upper()} на −{int(args[1])}% сохранён."
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) != 2 or not args[0].isdigit():
        await update.effective_message.reply_text("Формат: /balance 123456789 790")
        return
    try:
        delta = int(args[1])
    except ValueError:
        await update.effective_message.reply_text("Сумма должна быть числом.")
        return
    tg_id = int(args[0])
    if not db.get_user(tg_id):
        await update.effective_message.reply_text("Пользователь ещё не запускал бота.")
        return
    db.change_balance(tg_id, delta)
    user = db.get_user(tg_id)
    await update.effective_message.reply_text(f"✅ Баланс {tg_id}: {user['balance']}₽")
    await context.bot.send_message(
        tg_id, f"💰 Баланс изменён на {delta:+d}₽. Текущий баланс: {user['balance']}₽"
    )


async def mark_paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_message.reply_text("Формат: /paid N1PHFR28L")
        return
    order_id = context.args[0].upper()
    order = db.get_order(order_id)
    if not order:
        await update.effective_message.reply_text("Заказ не найден.")
        return
    if order["status"] == "paid":
        await update.effective_message.reply_text("Заказ уже оплачен.")
        return
    if order["status"] != "pending":
        codes = db.reserve_codes(order_id, order["product_id"], order["qty"])
        if not codes:
            await update.effective_message.reply_text("Не хватает кодов на складе.")
            return
    db.set_order_status(order_id, "paid")
    for job in context.job_queue.get_jobs_by_name(f"expire:{order_id}"):
        job.schedule_removal()

    product = db.get_product(order["product_id"])
    codes_block = "\n".join(
        f"<code>{html.escape(code)}</code>" for code in db.order_codes(order_id)
    )
    await context.bot.send_message(
        order["user_id"],
        f"✅ <b>Заказ оплачен</b> · <code>{order_id}</code>\n\n"
        f"Товар: <b>{html.escape(product['title'])}</b>\n"
        f"Кол-во: {order['qty']} шт\n\n"
        f"🔑 Код активации:\n{codes_block}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb.link_menu("manual"),
    )
    await update.effective_message.reply_text(f"✅ Заказ {order_id} подтверждён.")
