# bot.py
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from datetime import datetime, timedelta
import json
import os

# ===== CONFIG =====
TOKEN = "8538428429:AAEg8GAbItNk34BIuwv_XdBomh1ZNr2chrs"
GROUP_ID = -1003391942384  # your order group ID (you provided this)

# Put your Telegram numeric user id(s) here — these users can use admin commands.
ADMIN_IDS = [7616942737]  # e.g. [123456789, 987654321] — add your id(s)

# ===== STATES =====
LANG, MENU, QUANTITY, ADD_MORE, DELIVERY_TYPE, BRANCH, LOCATION, PAYMENT, PAYMENT_CONFIRM, PAYMENT_SCREENSHOT, PHONE = range(11)

# ===== PRICES (so'm) =====
PRICES = {
    "Qiyma": 8000,
    "Tovuq": 8000,
    "O'rama": 10000,
    "Jigar": 12000,
    "Jaz": 15000,
}

CARD_TEXT = "9860 0801 2644 1023"  # your card number

# ===== PICKUP LINKS =====
LINK_3MKR = "https://www.google.com/maps/place/40%C2%B013'04.2%22N+69%C2%B014'43.7%22E/@40.217836,69.245463,16z"
LINK_BOZOR = "https://www.google.com/maps/place/40%C2%B012'49.3%22N+69%C2%B016'00.3%22E/@40.213703,69.266747,16z"
LINK_KVARTAL = "https://google.com/maps?q=40.220912,69.262417&ll=40.220912,69.262417&z=16"

# ===== ORDER STORAGE =====
ORDERS_FILE = "orders.json"
# structure: {"last_id": 0, "orders": [ {order dict}, ... ] }

def load_orders_data():
    if not os.path.exists(ORDERS_FILE):
        data = {"last_id": 0, "orders": []}
        with open(ORDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data
    with open(ORDERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_orders_data(data):
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

orders_data = load_orders_data()

def get_next_order_number():
    orders_data["last_id"] += 1
    save_orders_data(orders_data)
    return orders_data["last_id"]

def record_order(order_dict):
    orders_data["orders"].append(order_dict)
    save_orders_data(orders_data)

# ===== ANTI-SPAM =====
# allow up to N orders within PERIOD (timedelta)
ANTISPAM_LIMIT = 3
ANTISPAM_PERIOD = timedelta(hours=1)
recent_orders_by_user = {}  # user_id -> [datetime, datetime, ...]

def can_place_order(user_id):
    now = datetime.now()
    times = recent_orders_by_user.get(user_id, [])
    # remove old
    times = [t for t in times if now - t <= ANTISPAM_PERIOD]
    if len(times) >= ANTISPAM_LIMIT:
        recent_orders_by_user[user_id] = times
        return False
    times.append(now)
    recent_orders_by_user[user_id] = times
    return True

# ===== HELPERS =====
def fmt_price(n: int) -> str:
    return f"{n:,} so'm"

def lang_text(ctx, uz_text, ru_text):
    return uz_text if ctx.user_data.get("lang") == "uz" else ru_text

def is_work_time():
    now = datetime.now()
    # work hours 11:00 - 22:00 inclusive start, exclusive end
    return 11 <= now.hour < 22

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["🇺🇿 O'zbekcha", "🇷🇺 Русский"]]
    await update.message.reply_text(
        "Tilni tanlang / Выберите язык:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
    )
    return LANG

async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if "O'zbek" in text or "O‘zbek" in text or "O'zbekcha" in text:
        context.user_data["lang"] = "uz"
    else:
        context.user_data["lang"] = "ru"

    # init order session data
    context.user_data["orders"] = []         # list of "Product xN"
    context.user_data["orders_total"] = []   # list of prices
    context.user_data["total"] = 0
    context.user_data["delivery"] = None
    context.user_data["branch"] = ""
    context.user_data["location"] = ""
    context.user_data["payment"] = ""
    context.user_data["payment_screenshot"] = None
    context.user_data["phone"] = ""

    kb = [["Qiyma", "Tovuq"], ["O'rama", "Jigar"], ["Jaz"]]
    await update.message.reply_text(
        lang_text(context, "🍢 Qaysi kabobni buyurtma qilasiz?", "🍢 Какой шашлык хотите заказать?"),
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
    )
    return MENU

async def menu_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = (update.message.text or "").strip()
    if product not in PRICES:
        await update.message.reply_text(lang_text(context, "Iltimos menyudan tanlang.", "Пожалуйста, выберите из меню."))
        return MENU
    context.user_data["product"] = product
    await update.message.reply_text(
        lang_text(context, "Nechta buyurtma qilasiz? (raqam yozing, masalan: 2)",
                  "Сколько штук вы хотите заказать? (введите число, например: 2)")
    )
    return QUANTITY

async def quantity_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not can_place_order(user.id):
        await update.message.reply_text(
            "❌ Siz juda ko'p buyurtma qildingiz. Iltimos bir soat ichida yana urinib ko'ring."
        )
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    try:
        qty = int(text)
        if qty <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text(
            lang_text(context, "Iltimos, toʻgʻri son kiriting (masalan: 1, 2, 3).",
                      "Пожалуйста, введите корректное число (например: 1, 2, 3).")
        )
        return QUANTITY

    product = context.user_data.get("product", "")
    price_each = PRICES.get(product, 0)
    total = price_each * qty

    # append order item
    context.user_data["orders"].append(f"{product} x{qty}")
    context.user_data["orders_total"].append(total)
    # update running total
    context.user_data["total"] = sum(context.user_data["orders_total"])

    await update.message.reply_text(
        lang_text(context, "Yana buyurtma qo‘shasizmi?", "Хотите добавить ещё шашлык?"),
        reply_markup=ReplyKeyboardMarkup(
            [["➕ Ha, yana buyurtma qo‘shish", "❌ Yo‘q, tugatdim"]],
            resize_keyboard=True, one_time_keyboard=True),
    )
    return ADD_MORE

async def add_more_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if "Ha" in text or "yana" in text or "ещё" in text:
        kb = [["Qiyma", "Tovuq"], ["O'rama", "Jigar"], ["Jaz"]]
        await update.message.reply_text(
            lang_text(context, "🍢 Qaysi kabobni buyurtma qilasiz?", "🍢 Какой шашлык хотите заказать?"),
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
        )
        return MENU
    # finish and ask delivery
    total = context.user_data.get("total", 0)
    await update.message.reply_text(
        lang_text(context, f"Jami summa: {fmt_price(total)}.\nQanday olasiz?",
                  f"Итого: {fmt_price(total)}.\nКак будете забирать?"),
        reply_markup=ReplyKeyboardMarkup(
            [["🚗 Yetkazib berish", "🏃 O'zim olib ketaman"]],
            resize_keyboard=True, one_time_keyboard=True),
    )
    return DELIVERY_TYPE

async def delivery_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # working hours check
    if not is_work_time():
        await update.message.reply_text(
            lang_text(context,
                      "❌ Biz 11:00 dan 22:00 gacha ishlaymiz. Iltimos shu vaqt oralig‘ida buyurtma bering.",
                      "❌ Мы работаем с 11:00 до 22:00. Пожалуйста, заказывайте в это время."),
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    if "Yetkazib" in text or "Доставка" in text:
        context.user_data["delivery"] = "delivery"
        kb = [
            [KeyboardButton("📍 Lokatsiyani yuborish", request_location=True)],
            ["Manzilni yozish"]  # exact text user provided
        ]
        await update.message.reply_text(
            lang_text(context, "Iltimos, manzilingizni yuboring yoki yozing:", "Пожалуйста, отправьте ваш адрес или геолокацию:"),
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
        )
        return LOCATION
    else:
        context.user_data["delivery"] = "pickup"
        # show simple pickup choices (user asked to keep old functions; these are the same names)
        kb = [["1 Kvartal Kids City", "2 Bozor"], ["3 3-MKR"]]
        await update.message.reply_text(
            lang_text(context, "Qaysi filialdan olasiz?", "Из какого филиала заберёте?"),
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
        )
        return BRANCH

async def branch_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    branch = (update.message.text or "").strip()
    context.user_data["branch"] = branch

    # send correct link based on selection
    if "Kvartal" in branch:
        await update.message.reply_text(f"📍 {LINK_KVARTAL}")
        context.user_data["location"] = LINK_KVARTAL
    elif "Bozor" in branch:
        await update.message.reply_text(f"📍 {LINK_BOZOR}")
        context.user_data["location"] = LINK_BOZOR
    elif "3-MKR" in branch or "3 3-MKR" in branch:
        await update.message.reply_text(f"📍 {LINK_3MKR}")
        context.user_data["location"] = LINK_3MKR

    # proceed to payment
    await update.message.reply_text(
        lang_text(context, "To'lov turini tanlang:", "Выберите способ оплаты:"),
        reply_markup=ReplyKeyboardMarkup([["💵 Naqd", "💳 Karta"]], resize_keyboard=True, one_time_keyboard=True),
    )
    return PAYMENT

async def location_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # If user pressed the "Manzilni yozish" button, we should not save that button text.
    text = (update.message.text or "").strip()
    if text == "Manzilni yozish":
        # Prompt to type actual address and wait for it
        await update.message.reply_text(
            lang_text(context, "Iltimos, manzilingizni yozing (masalan: Bekobod, 3-mkr, 12-uy):",
                      "Пожалуйста, введите ваш адрес (например: Бекабад, 3-й квартал, дом 12):"),
            reply_markup=ReplyKeyboardRemove(),
        )
        return LOCATION

    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude
        context.user_data["location"] = f"https://www.google.com/maps?q={lat},{lon}"
    else:
        # user typed address (not the "Manzilni yozish" button)
        context.user_data["location"] = text

    await update.message.reply_text(
        lang_text(context, "To'lov turini tanlang:", "Выберите способ оплаты:"),
        reply_markup=ReplyKeyboardMarkup([["💵 Naqd", "💳 Karta"]], resize_keyboard=True, one_time_keyboard=True),
    )
    return PAYMENT

async def payment_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pay = (update.message.text or "").strip()
    if "Karta" in pay or "Карта" in pay:
        context.user_data["payment"] = lang_text(context, "Karta", "Карта")
        await update.message.reply_text(
            lang_text(context,
                      f"💳 To'lov uchun karta raqami: {CARD_TEXT}\nTo'lovni amalga oshirgach, skrinshot yuboring:",
                      f"💳 Оплата на карту: {CARD_TEXT}\nПосле оплаты отправьте скриншот:"),
            reply_markup=ReplyKeyboardMarkup([["📸 Skrinshot yuborish"]], resize_keyboard=True, one_time_keyboard=True),
        )
        return PAYMENT_SCREENSHOT
    else:
        context.user_data["payment"] = lang_text(context, "Naqd", "Наличные")
        contact_button = KeyboardButton(text=lang_text(context, "📲 Kontaktni yuborish", "📲 Отправить контакт"), request_contact=True)
        await update.message.reply_text(
            lang_text(context, "Iltimos, telefon raqamingizni yuboring:", "Пожалуйста, отправьте ваш номер телефона:"),
            reply_markup=ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True),
        )
        return PHONE

async def payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text(lang_text(context, "Iltimos, to'lov skrinshotini yuboring.", "Пожалуйста, отправьте скриншот оплаты."))
        return PAYMENT_SCREENSHOT

    # save the file_id for admin
    file_id = update.message.photo[-1].file_id
    context.user_data["payment_screenshot"] = file_id

    # ask phone next
    contact_button = KeyboardButton(text=lang_text(context, "📲 Kontaktni yuborish", "📲 Отправить контакт"), request_contact=True)
    await update.message.reply_text(
        lang_text(context, "To'lov qabul qilindi. Iltimos telefon raqamingizni yuboring:", "Платёж получен. Пожалуйста, отправьте номер телефона:"),
        reply_markup=ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True),
    )
    return PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = (update.message.text or "").strip()
    context.user_data["phone"] = phone

    # finalize
    await finalize_order(update, context)
    return ConversationHandler.END

async def finalize_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = context.user_data.get("lang", "uz")
    orders_list = context.user_data.get("orders", [])
    total = context.user_data.get("total", 0)
    payment = context.user_data.get("payment", "")
    phone = context.user_data.get("phone", "—")
    branch = context.user_data.get("branch", "")
    location = context.user_data.get("location", "")
    screenshot = context.user_data.get("payment_screenshot")

    # order number
    order_id = get_next_order_number()
    order_code = f"#{order_id:05d}"

    # build user message (receipt)
    order_lines = "\n".join(orders_list)
    user_msg = (
        f"✅ Buyurtmangiz qabul qilindi! {order_code}\n\n{order_lines}\n💰 Umumiy summa: {fmt_price(total)}\n📞 Telefon: {phone}\n📍 Joylashuv: {branch or location or '—'}\n💳 To'lov turi: {payment}\n\nKabob House siz bilan tez orada bog'lanadi!"
        if lang == "uz" else
        f"✅ Ваш заказ принят! {order_code}\n\n{order_lines}\n💰 Сумма: {fmt_price(total)}\n📞 Телефон: {phone}\n📍 Адрес: {branch or location or '—'}\n💳 Оплата: {payment}\n\nМы свяжемся с вами в ближайшее время!"
    )
    await update.message.reply_text(user_msg, reply_markup=ReplyKeyboardRemove())

    # prepare admin message
    admin_text = (
        f"📩 Yangi buyurtma {order_code}\n\n"
        f"👤 {user.first_name or '—'} (@{user.username or '—'})\n"
        f"📞 {phone}\n"
        f"{order_lines}\n"
        f"💰 Jami: {fmt_price(total)}\n"
        f"📍 {branch or location or '—'}\n"
        f"💳 {payment}"
    )

    # send to group (with screenshot if provided)
    try:
        if screenshot:
            await context.bot.send_photo(chat_id=GROUP_ID, photo=screenshot, caption=admin_text)
        else:
            await context.bot.send_message(chat_id=GROUP_ID, text=admin_text)
    except Exception as e:
        # best effort: if sending fails, notify the user (but don't crash)
        await update.message.reply_text("⚠️ Xatolik: buyurtma guruhga jo'natilmadi. Iltimos, adminga xabar bering.")
        print("Error sending to group:", e)

    # record order in orders.json
    order_record = {
        "order_code": order_code,
        "time": datetime.now().isoformat(),
        "user": {"id": user.id, "name": user.first_name, "username": user.username},
        "phone": phone,
        "items": orders_list,
        "total": total,
        "payment": payment,
        "branch": branch,
        "location": location,
        "screenshot": screenshot,
    }
    record_order(order_record)

    # clear session user_data so they can order again
    # keep admin/client preferences if you want, but we'll reset session fields
    keys_to_keep = ["lang"]
    saved = {k: context.user_data.get(k) for k in keys_to_keep}
    context.user_data.clear()
    context.user_data.update(saved)

# CANCEL
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(lang_text(context, "Buyurtma bekor qilindi.", "Заказ отменён."), reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# ===== ADMIN COMMANDS =====
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("Siz admin emassiz.")
        return
    # show last 10 orders
    data = load_orders_data()
    last = data.get("orders", [])[-10:]
    if not last:
        await update.message.reply_text("Hech qanday buyurtma yo'q.")
        return
    text = "So'nggi buyurtmalar:\n\n"
    for o in reversed(last):
        text += f"{o['order_code']} — {o['time']} — {fmt_price(o['total'])}\n"
    await update.message.reply_text(text)

async def cmd_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("Siz admin emassiz.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Foydalanish: /order <order_code_without_hash>  (misol: /order 1)")
        return
    code = args[0]
    if code.isdigit():
        code_str = f"#{int(code):05d}"
    else:
        code_str = code
    data = load_orders_data()
    for o in data.get("orders", []):
        if o["order_code"] == code_str:
            text = json.dumps(o, ensure_ascii=False, indent=2)
            await update.message.reply_text(f"Order {code_str}:\n\n{text}")
            return
    await update.message.reply_text("Buyurtma topilmadi.")

# ===== APP SETUP =====
app = ApplicationBuilder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        LANG: [MessageHandler(filters.TEXT & ~filters.COMMAND, language_selected)],
        MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_selected)],
        QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_selected)],
        ADD_MORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_more_choice)],
        DELIVERY_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_choice)],
        BRANCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, branch_selected)],
        LOCATION: [
            # button press "Manzilni yozish" will be text - handled in location_received
            MessageHandler(filters.LOCATION | (filters.TEXT & ~filters.COMMAND), location_received)
        ],
        PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_selected)],
        PAYMENT_SCREENSHOT: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), payment_screenshot)],
        PHONE: [MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), phone_received)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

app.add_handler(conv)
app.add_handler(CommandHandler("admin", cmd_admin))
app.add_handler(CommandHandler("order", cmd_order_details))

print("✅ Kabob House Bot is running...")
app.run_polling()
