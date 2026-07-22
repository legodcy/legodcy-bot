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
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Legodcy_Bot")  # یوزرنیم ربات بدون @ (برای ساخت لینک دعوت)

ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

# پلن‌ها را همینجا ویرایش کن (قیمت‌ها به تومان)
PLANS = {
    "u1": {"title": "♾️ نامحدود | تک‌کاربره", "price": 350_000},
    "u2": {"title": "♾️ نامحدود | دو‌کاربره", "price": 430_000},
    "v10": {"title": "📦 حجمی 10G | تک‌کاربره", "price": 100_000},
    "v20": {"title": "📦 حجمی 20G | تک‌کاربره", "price": 160_000},
    "v10m": {"title": "📦 حجمی 10G | چندکاربره", "price": 145_000},
    "v20m": {"title": "📦 حجمی 20G | چندکاربره", "price": 225_000},
}

# پلن‌های نامحدود یک ماه اعتبار دارند (برای نمایش توضیح در پیام خرید)
UNLIMITED_PLAN_KEYS = {"u1", "u2"}
# خرید این پلن‌ها در شمارش «معرفی موفق» برای هدیه‌ی یک‌ماهه حساب نمی‌شود
EXCLUDED_FROM_REFERRAL = {"v10", "v10m"}

WELCOME_TEXT = (
    "🔥 به *LeGodcy* خوش اومدی 🔥\n\n"
    "اینجا می‌تونی سرویس VPN اختصاصی با آی‌پی آلمان 🇩🇪 و آمریکا 🇺🇸 تهیه کنی.\n"
    "سرعت بالا، پینگ پایین و تحویل فوری بعد از تایید پرداخت 🚀\n"
    "📱 پیشنهاد: اگه با سیم‌کارت ایرانسل استفاده می‌کنی، اپ *v2rayTun* اتصال پایدارتری می‌ده.\n"
    "🎁 پیش از خرید، ۱۳ دقیقه تست رایگان داری — برای دریافت کافیه گزینه‌ی آخر «صحبت مستقیم با ادمین» رو ضربه بزنی و فقط بنویسی: تست\n\n"
    "👇 یکی از پلن‌ها رو انتخاب کن:"
)

# awaiting_admin_reply[admin_id] = order_id  -> پیام بعدی ادمین برای این سفارش فرستاده می‌شود
awaiting_admin_reply: dict[int, str] = {}
# awaiting_gift_reply[admin_id] = referrer_user_id  -> پیام بعدی ادمین به‌عنوان هدیه‌ی معرفی برای این کاربر فرستاده می‌شود
awaiting_gift_reply: dict[int, int] = {}
REFERRALS_FOR_GIFT = 3  # هر چند تا معرفیِ موفق (خریدِ تاییدشده)، یک ماه هدیه بگیرد


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


# ========= کاربران و معرفی به دوستان =========
def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_users(users: dict) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"


async def register_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict:
    """کاربر را ثبت می‌کند و اگر از طریق لینک معرفی آمده باشد، رابطه‌ی معرف/زیرمجموعه را ذخیره می‌کند."""
    user = update.effective_user
    users = load_users()
    uid = str(user.id)
    is_new = uid not in users

    if is_new:
        users[uid] = {
            "username": user.username or "",
            "full_name": user.full_name,
            "referred_by": None,
            "referral_count": 0,
            "joined_at": datetime.utcnow().isoformat(),
        }
    else:
        users[uid]["username"] = user.username or ""
        users[uid]["full_name"] = user.full_name

    # پردازش لینک معرفی — فقط بار اول که کاربر وارد می‌شود (شمارش واقعی بعداً و فقط با خرید تاییدشده انجام می‌شود)
    if is_new and context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg[4:])
            except ValueError:
                referrer_id = None
            if referrer_id and referrer_id != user.id and str(referrer_id) in users:
                users[uid]["referred_by"] = referrer_id

    save_users(users)
    return users[uid]


# ========= کیبورد پلن‌ها =========
def plans_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, plan in PLANS.items():
        label = f"{plan['title']} — {plan['price']:,} تومان"
        rows.append([InlineKeyboardButton(label, callback_data=f"plan:{key}")])
    rows.append([InlineKeyboardButton("💬 صحبت مستقیم با ادمین", url=f"https://t.me/{ADMIN_CONTACT.lstrip('@')}")])
    rows.append([InlineKeyboardButton("🔄 تمدید اشتراک", callback_data="start_renewal")])
    rows.append([InlineKeyboardButton("🎁 معرفی به دوستان", callback_data="referral")])
    return InlineKeyboardMarkup(rows)


def renewal_plans_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, plan in PLANS.items():
        label = f"{plan['title']} — {plan['price']:,} تومان"
        rows.append([InlineKeyboardButton(label, callback_data=f"renew:{key}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_plans")])
    return InlineKeyboardMarkup(rows)


# ========= هندلرها =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_plan", None)
    context.user_data.pop("pending_order", None)
    await register_user(update, context)
    await update.message.reply_text(
        WELCOME_TEXT, parse_mode=ParseMode.MARKDOWN, reply_markup=plans_keyboard()
    )


async def on_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    users = load_users()
    record = users.get(str(user.id), {"referral_count": 0})
    link = referral_link(user.id)

    text = (
        "🎁 *معرفی به دوستان*\n\n"
        "لینک اختصاصی خودت رو برای دوستات بفرست؛ وقتی خرید یکی از دوستات *تایید* بشه،\n"
        "به حساب تو ثبت می‌شه 👇\n\n"
        f"`{link}`\n"
        "👆 با یک کلیک کپی کن\n\n"
        f"👥 تعداد معرفی‌های موفق تو: *{record.get('referral_count', 0)} نفر*\n"
        f"🎁 هر {REFERRALS_FOR_GIFT} معرفی موفق = یک ماه سرویس رایگان (به‌جز پلن حجمی 10G)"
    )
    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها", callback_data="back_to_plans")]]
    )
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb)


async def on_plan_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.split(":", 1)[1]
    plan = PLANS[plan_key]

    context.user_data["pending_plan"] = plan_key
    context.user_data.pop("is_renewal", None)
    context.user_data.pop("renewal_link", None)
    context.user_data.pop("awaiting_renewal_link", None)

    volume_note = "\n⏳ توجه: سرویس‌های نامحدود یک ماه اعتبار دارند." if plan_key in UNLIMITED_PLAN_KEYS else ""

    text = (
        f"✅ پلن انتخابی: *{plan['title']}*\n"
        f"💰 مبلغ: *{plan['price']:,} تومان*{volume_note}\n\n"
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


async def on_start_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🔄 *تمدید اشتراک*\n\n"
        "پلنی که می‌خوای تمدید کنی رو انتخاب کن:"
    )
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=renewal_plans_keyboard())


async def on_renew_plan_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.split(":", 1)[1]
    plan = PLANS[plan_key]

    context.user_data["pending_plan"] = plan_key
    context.user_data["is_renewal"] = True
    context.user_data["awaiting_renewal_link"] = True
    context.user_data.pop("renewal_link", None)

    volume_note = "\n⏳ توجه: سرویس‌های نامحدود یک ماه اعتبار دارند." if plan_key in UNLIMITED_PLAN_KEYS else ""

    text = (
        f"🔄 تمدید پلن: *{plan['title']}*\n"
        f"💰 مبلغ: *{plan['price']:,} تومان*{volume_note}\n\n"
        f"1️⃣ اول *لینک اشتراک (Subscription) فعلی‌تون* رو به‌صورت متن همینجا بفرستید.\n"
        f"2️⃣ بعد رسید پرداخت رو ارسال کنید.\n\n"
        f"💳 شماره کارت برای واریز:\n`{CARD_NUMBER}`\n👆 با یک کلیک کپی کن"
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
    context.user_data.pop("is_renewal", None)
    context.user_data.pop("renewal_link", None)
    context.user_data.pop("awaiting_renewal_link", None)
    await query.edit_message_text(
        WELCOME_TEXT, parse_mode=ParseMode.MARKDOWN, reply_markup=plans_keyboard()
    )


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیام‌های متنی عادی مشتری‌ها؛ فقط برای گرفتن لینک اشتراک فعلی در فرآیند تمدید استفاده می‌شود."""
    if context.user_data.get("awaiting_renewal_link"):
        link_text = (update.message.text or "").strip()
        context.user_data["renewal_link"] = link_text
        context.user_data["awaiting_renewal_link"] = False
        await update.message.reply_text(
            "✅ لینک اشتراک فعلی ثبت شد.\n📸 حالا رسید پرداخت رو ارسال کن تا برای بررسی به ادمین بفرستم."
        )
        return
    await update.message.reply_text("برای شروع یا مشاهده‌ی پلن‌ها /start رو بزن 🙂")


async def on_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی کاربر عکس/فایل رسید می‌فرستد."""
    plan_key = context.user_data.get("pending_plan")
    if not plan_key:
        await update.message.reply_text(
            "اول یه پلن رو از منو انتخاب کن 🙂 برای شروع /start رو بزن."
        )
        return

    if context.user_data.get("awaiting_renewal_link"):
        await update.message.reply_text(
            "قبل از رسید، لطفاً لینک اشتراک فعلی‌تون رو به‌صورت متن ارسال کنید 🙏"
        )
        return

    is_renewal = context.user_data.get("is_renewal", False)
    renewal_link = context.user_data.get("renewal_link")

    user = update.effective_user
    plan = PLANS[plan_key]
    order_id = create_order(user.id, user.username or user.full_name, plan_key)
    update_order(order_id, status="pending_review", is_renewal=is_renewal, renewal_link=renewal_link)
    context.user_data["pending_order"] = order_id
    context.user_data.pop("pending_plan", None)
    context.user_data.pop("is_renewal", None)
    context.user_data.pop("renewal_link", None)

    users = load_users()
    referred_by = users.get(str(user.id), {}).get("referred_by")
    referral_line = ""
    if referred_by:
        ref_record = users.get(str(referred_by), {})
        ref_name = ref_record.get("username") or ref_record.get("full_name") or referred_by
        referral_line = f"\n🔗 معرفی شده توسط: @{ref_name} (id: {referred_by})"

    order_type_line = "🔄 نوع سفارش: تمدید اشتراک" if is_renewal else "🆕 نوع سفارش: خرید جدید"
    renewal_link_line = f"\n🔗 لینک فعلی برای تمدید: {renewal_link}" if is_renewal and renewal_link else ""

    caption = (
        f"🧾 رسید جدید — سفارش `{order_id}`\n"
        f"👤 کاربر: {user.full_name} (@{user.username or 'ندارد'} | id: {user.id})\n"
        f"📦 پلن: {plan['title']}\n"
        f"💰 مبلغ: {plan['price']:,} تومان\n"
        f"{order_type_line}"
        f"{renewal_link_line}"
        f"{referral_line}"
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

        # شمارش معرفی موفق — فقط اگر پلن خریداری‌شده جزو پلن‌های مستثنا (حجمی 10G) نباشد
        plan_key = order.get("plan")
        if plan_key not in EXCLUDED_FROM_REFERRAL:
            users = load_users()
            referrer_id = users.get(str(customer_id), {}).get("referred_by")
            if referrer_id and str(referrer_id) in users:
                ref_key = str(referrer_id)
                users[ref_key]["referral_count"] = users[ref_key].get("referral_count", 0) + 1
                save_users(users)
                count = users[ref_key]["referral_count"]
                if count % REFERRALS_FOR_GIFT == 0:
                    ref_name = users[ref_key].get("username") or users[ref_key].get("full_name") or referrer_id
                    gift_kb = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🎁 ارسال هدیه یک‌ماهه", callback_data=f"send_gift:{referrer_id}")]]
                    )
                    await context.bot.send_message(
                        ADMIN_ID,
                        f"🎉 کاربر @{ref_name} (id: {referrer_id}) به {count} معرفی موفق رسید!\n"
                        f"طبق قانون، مستحق یک ماه سرویس رایگانه. برای ارسال هدیه دکمه زیر رو بزن:",
                        reply_markup=gift_kb,
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


async def on_send_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        await query.answer("فقط ادمین می‌تونه این کارو انجام بده.", show_alert=True)
        return

    referrer_id = int(query.data.split(":", 1)[1])
    awaiting_gift_reply[ADMIN_ID] = referrer_id
    await context.bot.send_message(
        ADMIN_ID,
        f"🎁 حالا هر چیزی (متن/لینک/فایل اشتراک هدیه) که باید برای کاربر `{referrer_id}` ارسال بشه رو همینجا بفرست.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def on_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هر پیامی که ادمین بعد از تایید سفارش یا رسیدن به سقف معرفی می‌فرستد، عیناً برای مشتری/معرف ارسال می‌شود."""
    if update.effective_user.id != ADMIN_ID:
        return

    msg = update.message

    # حالت ۱: ارسال محتوای سفارش عادی
    order_id = awaiting_admin_reply.get(ADMIN_ID)
    if order_id:
        orders = load_orders()
        order = orders.get(order_id)
        if not order:
            return
        customer_id = order["user_id"]

        if msg.text:
            await context.bot.send_message(customer_id, f"🎉 سرویس شما آماده است:\n\n{msg.text}")
        elif msg.photo:
            await context.bot.send_photo(customer_id, msg.photo[-1].file_id, caption="🎉 سرویس شما آماده است.")
        elif msg.document:
            await context.bot.send_document(customer_id, msg.document.file_id, caption="🎉 سرویس شما آماده است.")
        else:
            await msg.reply_text("این نوع پیام پشتیبانی نمی‌شه، لطفاً متن یا فایل بفرست.")
            return

        again_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🛒 خرید / تمدید سرویس جدید", callback_data="back_to_plans")]]
        )
        await context.bot.send_message(
            customer_id,
            "🙏 ممنون که از *LeGodcy* خرید کردی!\nهر وقت خواستی سرویس جدید بگیری یا تمدید کنی، همینجا بزن 👇",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=again_kb,
        )

        update_order(order_id, status="fulfilled")
        awaiting_admin_reply.pop(ADMIN_ID, None)
        await msg.reply_text(f"✅ برای مشتری سفارش `{order_id}` ارسال شد.", parse_mode=ParseMode.MARKDOWN)
        return

    # حالت ۲: ارسال هدیه‌ی یک‌ماهه به یک معرف موفق
    gift_user_id = awaiting_gift_reply.get(ADMIN_ID)
    if gift_user_id:
        if msg.text:
            await context.bot.send_message(gift_user_id, f"🎁 اشتراک هدیه‌ی شما آماده است:\n\n{msg.text}")
        elif msg.photo:
            await context.bot.send_photo(gift_user_id, msg.photo[-1].file_id, caption="🎁 اشتراک هدیه‌ی شما آماده است.")
        elif msg.document:
            await context.bot.send_document(gift_user_id, msg.document.file_id, caption="🎁 اشتراک هدیه‌ی شما آماده است.")
        else:
            await msg.reply_text("این نوع پیام پشتیبانی نمی‌شه، لطفاً متن یا فایل بفرست.")
            return

        awaiting_gift_reply.pop(ADMIN_ID, None)
        await msg.reply_text(f"✅ هدیه برای کاربر `{gift_user_id}` ارسال شد.", parse_mode=ParseMode.MARKDOWN)
        return


async def cancel_admin_wait(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        awaiting_admin_reply.pop(ADMIN_ID, None)
        awaiting_gift_reply.pop(ADMIN_ID, None)
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
    app.add_handler(CallbackQueryHandler(on_referral, pattern=r"^referral$"))
    app.add_handler(CallbackQueryHandler(on_start_renewal, pattern=r"^start_renewal$"))
    app.add_handler(CallbackQueryHandler(on_renew_plan_chosen, pattern=r"^renew:"))
    app.add_handler(CallbackQueryHandler(on_admin_decision, pattern=r"^(approve|reject):"))
    app.add_handler(CallbackQueryHandler(on_send_gift, pattern=r"^send_gift:"))
    # پیام‌های ادمین (وقتی منتظر ارسال محتوا/هدیه هستیم) باید قبل از هندلرهای عمومی چک بشن
    app.add_handler(MessageHandler(filters.User(user_id=ADMIN_ID) & (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, on_admin_message))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, on_receipt))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))

    logger.info("LeGodcy bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
