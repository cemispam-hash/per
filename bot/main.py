"""Точка входа Telegram-бота DIYORDE Store."""

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import admin
import db
import handlers
import keyboards as kb
from config import BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def on_startup(application: Application) -> None:
    """Закрываем заказы, которые протухли, пока бот был выключен."""
    for order_id in db.expire_stale_orders():
        db.release_codes(order_id)


def build_application() -> Application:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан — заполните bot/.env")

    db.init()
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("menu", handlers.home))

    app.add_handler(CommandHandler("admin", admin.admin))
    app.add_handler(CommandHandler("stats", admin.stats))
    app.add_handler(CommandHandler("addstock", admin.addstock))
    app.add_handler(CommandHandler("addpromo", admin.addpromo))
    app.add_handler(CommandHandler("balance", admin.balance))
    app.add_handler(CommandHandler("paid", admin.mark_paid))

    text = filters.TEXT & ~filters.COMMAND
    for label, handler in (
        (kb.BTN_BUY, handlers.buy_menu),
        (kb.BTN_PROFILE, handlers.profile),
        (kb.BTN_MANUAL, handlers.manual),
        (kb.BTN_NEWS, handlers.news),
        (kb.BTN_SUPPORT, handlers.support),
    ):
        app.add_handler(MessageHandler(filters.Text([label]), handler))

    app.add_handler(CallbackQueryHandler(handlers.home, pattern=r"^home$"))
    app.add_handler(CallbackQueryHandler(handlers.buy_menu, pattern=r"^buy$"))
    app.add_handler(CallbackQueryHandler(handlers.subscriptions, pattern=r"^subs$"))
    app.add_handler(CallbackQueryHandler(handlers.product, pattern=r"^prod:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.change_qty, pattern=r"^qty:\d+:\d+:-?\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.buy_now, pattern=r"^buyit:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.ask_promo, pattern=r"^promo:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(handlers.payment, pattern=r"^pay:[A-Z0-9]+:\w+$"))
    app.add_handler(CallbackQueryHandler(handlers.profile, pattern=r"^profile$"))
    app.add_handler(CallbackQueryHandler(handlers.purchases, pattern=r"^purchases$"))
    app.add_handler(CallbackQueryHandler(handlers.topup, pattern=r"^topup$"))
    app.add_handler(CallbackQueryHandler(handlers.noop, pattern=r"^noop$"))

    app.add_handler(MessageHandler(text, handlers.on_text))
    app.add_error_handler(handlers.on_error)
    return app


def main() -> None:
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
