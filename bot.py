"""
LeGodcy VPN — Telegram Sales Bot
---------------------------------
جریان کار:
1) مشتری /start می‌زند، پلن را از دکمه‌های شیشه‌ای انتخاب می‌کند.
2) بات از او می‌خواهد عکس/فایل رسید پرداخت را بفرستد.
3) رسید همراه با اطلاعات سفارش برای ادمین (ADMIN_ID) با دو دکمه
   «تایید ✅» و «رد ❌» ارسال می‌شود.
4) اگر ادمین «تایید» بزند، بات از او می‌خواهد محتوایی که باید
   برای مشتری فرستاده شود (لینک اشتراک / متن کانفیگ) را تایپ کند.
   هرچه ادمین در همان لحظه بفرستد، عیناً برای مشتری فوروارد می‌شود.
5) اگر ادمین «رد» بزند، به مشتری اطلاع داده می‌شود.

راه‌اندازی:
- BOT_TOKEN و ADMIN_ID را به‌صورت متغیر محیطی ست کنید (به README.md نگاه کنید).
- pip install -r requirements.txt
- python bot.py
"""

import json
import logging
import os
import uuid
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("legodcy-bot")

# ========= تنظیمات =========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT-YOUR-TOKEN-HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))  # آیدی عددی ادمین (نه یوزرنیم)
ADMIN_CONTACT = "@legodcy"
CARD_NUMBER = "6219861946601381"

ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")

# پلن‌ها را همینجا ویرایش کن (قیمت‌ها به تومان)
PLANS = {
    "u1": {"title": "♾️ نامحدود | تک‌کاربره", "price": 350_000},
    "u2": {"title": "♾️ نامحدود | دو‌کاربره", "price": 430_000},
    "v10": {"title": "📦 حجمی 10G | تک‌کاربره", "price": 100_000},
    "v20": {"title": "📦 حجمی 20G | تک‌کاربره", "price": 160_000},
    "v10m": {"title": "📦 حجمی 10G | چندکاربره", "price": 145_000},
    "v20m": {"title": "📦 حجمی 20G | چندکاربره", "price": 225_000},
}

WELCOME_TEXT = (
    "🔥 به *LeGodcy* خوش اومدی 🔥\n\n"
    "اینجا می‌تونی سرویس VPN اختصاصی با آی‌پی آلمان 🇩🇪 و آمریکا 🇺🇸 تهیه کنی.\n"
    "سرعت بالا، پینگ پایین و تحویل فوری بعد از تایید پرداخت 🚀\n"
    "🎁 پیش از خرید، ۱۳ دقیقه تست رایگان داری — برای دریافت کافیه گزینه‌ی آخر «صحبت مستقیم با ادمین» رو ضربه بزنی و فقط بنویسی: تست\n\n"
    "👇 یکی از پلن‌ها رو انتخاب کن:"
)

# awaiting_admin_reply[admin_id] = order_id  -> پیام بعدی ادمین برای این سفارش فرستاده می‌شود
awaiting_admin_reply: dict[int, str] = {}


# ========= ذخیره‌سازی ساده سفارش‌ها =========
def load_orders() -> dict:
    if not os.path.exists(ORDERS_FILE):
        return {}
    with open(ORDERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_orders(orders: dict) -> None:
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)


def create_order(user_id: int, username: str, plan_key: str) -> str:
    orders = load_orders()
    order_id = uuid.uuid4().hex[:8]
    orders[order_id] = {
        "user_id": user_id,
        "username": username or "",
        "plan": plan_key,
        "status": "awaiting_receipt",  # awaiting_receipt -> pending_review -> approved/rejected
        "created_at": datetime.utcnow().isoformat(),
    }
    save_orders(orders)
    return order_id


def update_order(order_id: str, **kwargs) -> dict:
    orders = load_orders()
    if order_id in orders:
        orders[order_id].update(kwargs)
        save_orders(orders)
    return orders.get(order_id, {})


# ========= کیبورد پلن‌ها =========
def plans_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, plan in PLANS.items():
        label = f"{plan['title']} — {plan['price']:,} تومان"
        rows.append([InlineKeyboardButton(label, callback_data=f"plan:{key}")])
    rows.append([InlineKeyboardButton("💬 صحبت مستقیم با ادمین", url=f"https://t.me/{ADMIN_CONTACT.lstrip('@')}")])
    return InlineKeyboardMarkup(rows)


# ========= هندلرها =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_plan", None)
    context.user_data.pop("pending_order", None)
    await update.message.reply_text(
        WELCOME_TEXT, parse_mode=ParseMode.MARKDOWN, reply_markup=plans_keyboard()
    )


async def on_plan_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.split(":", 1)[1]
    plan = PLANS[plan_key]

    context.user_data["pending_plan"] = plan_key

    text = (
        f"✅ پلن انتخابی: *{plan['title']}*\n"
        f"💰 مبلغ: *{plan['price']:,} تومان*\n\n"
        f"💳 لطفاً مبلغ را به کارت زیر واریز نمایید:\n"
        f"`{CARD_NUMBER}`\n"
        f"👆 با یک کلیک کپی کن\n\n"
        f"📸 سپس عکس رسید پرداخت را همین‌جا ارسال کنید.\n"
        f"⚡️ پس از تایید پرداخت، بلافاصله اشتراک براتون ارسال می‌شه."
    )
    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها", callback_data="back_to_plans")]]
    )
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb)


async def on_back_to_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """کاربر از صفحه‌ی پرداخت به لیست پلن‌ها برمی‌گردد."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_plan", None)
    await query.edit_message_text(
        WELCOME_TEXT, parse_mode=ParseMode.MARKDOWN, reply_markup=plans_keyboard()
    )


async def on_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی کاربر عکس/فایل رسید می‌فرستد."""
    plan_key = context.user_data.get("pending_plan")
    if not plan_key:
        await update.message.reply_text(
            "اول یه پلن رو از منو انتخاب کن 🙂 برای شروع /start رو بزن."
        )
        return

    user = update.effective_user
    plan = PLANS[plan_key]
    order_id = create_order(user.id, user.username or user.full_name, plan_key)
    update_order(order_id, status="pending_review")
    context.user_data["pending_order"] = order_id
    context.user_data.pop("pending_plan", None)

    caption = (
        f"🧾 رسید جدید — سفارش `{order_id}`\n"
        f"👤 کاربر: {user.full_name} (@{user.username or 'ندارد'} | id: {user.id})\n"
        f"📦 پلن: {plan['title']}\n"
        f"💰 مبلغ: {plan['price']:,} تومان"
    )
    admin_kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ تایید", callback_data=f"approve:{order_id}"),
                InlineKeyboardButton("❌ رد", callback_data=f"reject:{order_id}"),
            ]
        ]
    )

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        await context.bot.send_photo(
            ADMIN_ID, file_id, caption=caption, parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_kb,
        )
    elif update.message.document:
        file_id = update.message.document.file_id
        await context.bot.send_document(
            ADMIN_ID, file_id, caption=caption, parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_kb,
        )
    else:
        await update.message.reply_text("لطفاً رسید رو به‌صورت عکس یا فایل بفرست.")
        return

    await update.message.reply_text(
        "📨 رسیدت برای ادمین ارسال شد. به محض تایید، سرویس‌ت همینجا برات ارسال می‌شه. ممنون از صبرت! 🙏"
    )


async def on_admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        await query.answer("فقط ادمین می‌تونه این کارو انجام بده.", show_alert=True)
        return

    action, order_id = query.data.split(":", 1)
    orders = load_orders()
    order = orders.get(order_id)
    if not order:
        await query.edit_message_caption(caption="⚠️ سفارش پیدا نشد (شاید قبلاً پردازش شده).")
        return

    customer_id = order["user_id"]

    if action == "approve":
        update_order(order_id, status="approved")
        awaiting_admin_reply[ADMIN_ID] = order_id
        await query.edit_message_caption(
            caption=(query.message.caption or "") + "\n\n✅ تایید شد — منتظر ارسال محتوا توسط شما.",
        )
        await context.bot.send_message(
            ADMIN_ID,
            f"✍️ حالا هر چیزی (متن/لینک/فایل کانفیگ) که باید برای مشتری سفارش `{order_id}` ارسال بشه رو همینجا بفرست.",
            parse_mode=ParseMode.MARKDOWN,
        )
        await context.bot.send_message(
            customer_id, "✅ پرداخت شما تایید شد! سرویس‌ت داره آماده می‌شه، چند لحظه صبر کن..."
        )

    elif action == "reject":
        update_order(order_id, status="rejected")
        await query.edit_message_caption(
            caption=(query.message.caption or "") + "\n\n❌ رد شد.",
        )
        await context.bot.send_message(
            customer_id,
            f"❌ متاسفانه رسید سفارش شما تایید نشد.\nلطفاً برای پیگیری با ادمین در تماس باش: {ADMIN_CONTACT}",
        )


async def on_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هر پیامی که ادمین بعد از تایید سفارش می‌فرستد، عیناً برای مشتری ارسال می‌شود."""
    if update.effective_user.id != ADMIN_ID:
        return
    order_id = awaiting_admin_reply.get(ADMIN_ID)
    if not order_id:
        return  # پیام عادی ادمین، ربطی به سفارش نداره

    orders = load_orders()
    order = orders.get(order_id)
    if not order:
        return
    customer_id = order["user_id"]

    msg = update.message
    if msg.text:
        await context.bot.send_message(customer_id, f"🎉 سرویس شما آماده است:\n\n{msg.text}")
    elif msg.photo:
        await context.bot.send_photo(customer_id, msg.photo[-1].file_id, caption="🎉 سرویس شما آماده است.")
    elif msg.document:
        await context.bot.send_document(customer_id, msg.document.file_id, caption="🎉 سرویس شما آماده است.")
    else:
        await msg.reply_text("این نوع پیام پشتیبانی نمی‌شه، لطفاً متن یا فایل بفرست.")
        return

    update_order(order_id, status="fulfilled")
    awaiting_admin_reply.pop(ADMIN_ID, None)
    await update.message.reply_text(f"✅ برای مشتری سفارش `{order_id}` ارسال شد.", parse_mode=ParseMode.MARKDOWN)


async def cancel_admin_wait(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        awaiting_admin_reply.pop(ADMIN_ID, None)
        await update.message.reply_text("لغو شد.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "دستورها:\n/start — نمایش پلن‌ها\n/help — راهنما\n\n"
        f"در صورت هرگونه سوال با ادمین در ارتباط باش: {ADMIN_CONTACT}"
    )


def main():
    if BOT_TOKEN == "PUT-YOUR-TOKEN-HERE" or not BOT_TOKEN:
        raise SystemExit("لطفاً متغیر محیطی BOT_TOKEN را با توکن ربات‌تان تنظیم کنید.")
    if ADMIN_ID == 0:
        raise SystemExit("لطفاً متغیر محیطی ADMIN_ID را با آیدی عددی تلگرام ادمین تنظیم کنید.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel_admin_wait))
    app.add_handler(CallbackQueryHandler(on_plan_chosen, pattern=r"^plan:"))
    app.add_handler(CallbackQueryHandler(on_back_to_plans, pattern=r"^back_to_plans$"))
    app.add_handler(CallbackQueryHandler(on_admin_decision, pattern=r"^(approve|reject):"))
    # پیام‌های ادمین (وقتی منتظر ارسال محتوا هستیم) باید قبل از هندلر رسید مشتری چک بشن
    app.add_handler(MessageHandler(filters.User(user_id=ADMIN_ID) & (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, on_admin_message))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, on_receipt))

    logger.info("LeGodcy bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
