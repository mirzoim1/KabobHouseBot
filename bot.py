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

# ===== CONFIG =====
TOKEN = "8538428429:AAEg8GAbItNk34BIuwv_XdBomh1ZNr2chrs"
GROUP_ID = -4995018772  # ORDERSKABOBS group

# ===== STATES =====
LANG, MENU, QUANTITY, DELIVERY_TYPE, BRANCH, LOCATION, PAYMENT, PAYMENT_CONFIRM, PHONE = range(9)

# ===== PRICES (so'm) =====
PRICES = {
    "Qiyma": 8000,
    "Tovuq": 8000,
    "O'rama": 10000,
    "Jigar": 12000,
    "Jaz": 15000,
}

CARD_TEXT = "9860 0801 2644 1023"  # your card number

# ===== HELPERS =====
def fmt_price(n: int) -> str:
    return f"{n:,} so'm"

def lang_text(ctx, uz_text, ru_text):
    return uz_text if ctx.user_data.get("lang") == "uz" else ru_text

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

    # show menu choices (clean product names)
    if context.user_data["lang"] == "uz":
        kb = [["Qiyma", "Tovuq"], ["O'rama", "Jigar"], ["Jaz"]]
        await update.message.reply_text("🍢 Qaysi kabobni buyurtma qilasiz?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    else:
        kb = [["Qiyma", "Tovuq"], ["O'rama", "Jigar"], ["Jaz"]]
        await update.message.reply_text("🍢 Какой шашлык хотите заказать?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))

    return MENU

async def menu_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = (update.message.text or "").strip()
    # store product exactly as the button text (without emoji)
    context.user_data["product"] = product

    await update.message.reply_text(
        lang_text(context,
                  "Nechta buyurtma qilasiz? (raqam yozing, masalan: 2)",
                  "Сколько штук вы хотите заказать? (введите число, например: 2)")
    )
    return QUANTITY

async def quantity_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    try:
        qty = int(text)
        if qty <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text(lang_text(context, "Iltimos, toʻgʻri son kiriting (masalan: 1, 2, 3).", "Пожалуйста, введите корректное число (например: 1, 2, 3)."))
        return QUANTITY

    context.user_data["quantity"] = qty
    product = context.user_data.get("product", "")
    price_each = PRICES.get(product, 0)
    total = price_each * qty
    context.user_data["total"] = total

    # Ask delivery or pickup
    await update.message.reply_text(
        lang_text(context,
                  f"Jami: {fmt_price(total)}.\nQanday olasiz?",
                  f"Итого: {fmt_price(total)}.\nКак будете забирать?"),
        reply_markup=ReplyKeyboardMarkup([["🚗 Yetkazib berish", "🏃 O'zim olib ketaman"]], resize_keyboard=True, one_time_keyboard=True),
    )
    return DELIVERY_TYPE

async def delivery_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if "Yetkazib" in text or "Доставка" in text:
        context.user_data["delivery"] = "delivery"
        # ask to send live location (user can press the button)
        kb_button = KeyboardButton(lang_text(context, "📍 Joylashuvni yuborish", "📍 Отправить местоположение"), request_location=True)
        await update.message.reply_text(
            lang_text(context, "Iltimos, joylashuvingizni yuboring yoki manzilni yozing:", "Пожалуйста, отправьте ваше местоположение или введите адрес:"),
            reply_markup=ReplyKeyboardMarkup([[kb_button], ["✏️ Manzilni yozish / Ввести адрес"]], resize_keyboard=True, one_time_keyboard=True),
        )
        return LOCATION
    else:
        context.user_data["delivery"] = "pickup"
        # ask which branch
        kb = [["1 Kvartal Kids City", "2 Bozor"], ["3 3-MKR"]]
        await update.message.reply_text(
            lang_text(context, "Qaysi filialdan olasiz?", "Из какого филиала заберёте?"),
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
        )
        return BRANCH

async def branch_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    branch_text = update.message.text or ""
    context.user_data["branch"] = branch_text
    # go to payment step
    await update.message.reply_text(
        lang_text(context, "To'lov turini tanlang:", "Выберите способ оплаты:"),
        reply_markup=ReplyKeyboardMarkup([["💵 Naqd", "💳 Karta"]], resize_keyboard=True, one_time_keyboard=True),
    )
    return PAYMENT

async def location_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # either a location object or text address
    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude
        maps_link = f"https://www.google.com/maps?q={lat},{lon}"
        context.user_data["location"] = maps_link
    else:
        # user typed an address
        context.user_data["location"] = update.message.text or ""

    await update.message.reply_text(
        lang_text(context, "To'lov turini tanlang:", "Выберите способ оплаты:"),
        reply_markup=ReplyKeyboardMarkup([["💵 Naqd", "💳 Karta"]], resize_keyboard=True, one_time_keyboard=True),
    )
    return PAYMENT

async def payment_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pay = update.message.text or ""
    # normalize
    if "Karta" in pay or "Карта" in pay:
        context.user_data["payment"] = lang_text(context, "Karta", "Карта")
        # send card details and ask to press confirm after paying
        card_msg = lang_text(context,
                             f"💳 To'lov uchun karta raqami: {CARD_TEXT}\nTo'lovni amalga oshirgach, pastdagi tugmani bosing ✅",
                             f"💳 Оплата на карту: {CARD_TEXT}\nПосле оплаты нажмите кнопку ✅")
        await update.message.reply_text(card_msg, reply_markup=ReplyKeyboardMarkup([["✅ To'lov qildim / Оплатил"]], resize_keyboard=True, one_time_keyboard=True))
        return PAYMENT_CONFIRM
    else:
        context.user_data["payment"] = lang_text(context, "Naqd", "Наличные")
        # ask contact directly (cash)
        contact_button = KeyboardButton(text=lang_text(context, "📲 Kontaktni yuborish", "📲 Отправить контакт"), request_contact=True)
        await update.message.reply_text(lang_text(context, "Iltimos, telefon raqamingizni yuboring:", "Пожалуйста, отправьте ваш номер телефона:"), reply_markup=ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True))
        return PHONE

async def payment_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user pressed "I paid" button
    # now ask for contact
    contact_button = KeyboardButton(text=lang_text(context, "📲 Kontaktni yuborish", "📲 Отправить контакт"), request_contact=True)
    await update.message.reply_text(lang_text(context, "To'lov tasdiqlandi. Iltimos, telefonni yuboring:", "Платёж подтвержден. Пожалуйста, отправьте контакт:"), reply_markup=ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True))
    return PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # accept contact object or typed phone
    if update.message.contact:
        phone = update.message.contact.phone_number
        # Also capture contact's first name if available
        contact_name = update.message.contact.first_name or ""
    else:
        phone = (update.message.text or "").strip()
        contact_name = ""

    context.user_data["phone"] = phone
    if contact_name:
        context.user_data["contact_name"] = contact_name

    # finalize order and send to group
    return await finalize_order(update, context)

async def finalize_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = context.user_data.get("lang", "uz")
    product = context.user_data.get("product", "")
    quantity = context.user_data.get("quantity", 0)
    total = context.user_data.get("total", 0)
    payment = context.user_data.get("payment", "")
    phone = context.user_data.get("phone", "Noma'lum / Не указан")
    delivery_type = context.user_data.get("delivery", "")
    branch = context.user_data.get("branch", "")
    location = context.user_data.get("location", "")

    # User confirmation message
    if lang == "uz":
        user_msg = (
            "✅ Buyurtmangiz qabul qilindi!\n\n"
            f"🍢 {product} — {quantity} ta\n"
            f"💰 Umumiy summa: {fmt_price(total)}\n"
            f"📞 Telefon: {phone}\n"
            f"📍 Joylashuv: {branch or location or '—'}\n"
            f"💳 To'lov turi: {payment}\n\n"
            "Kabob House siz bilan tez orada bog'lanadi!"
        )
    else:
        user_msg = (
            "✅ Ваш заказ принят!\n\n"
            f"🍢 {product} — {quantity} шт.\n"
            f"💰 Общая сумма: {fmt_price(total)}\n"
            f"📞 Телефон: {phone}\n"
            f"📍 Адрес: {branch or location or '—'}\n"
            f"💳 Оплата: {payment}\n\n"
            "Kabob House свяжется с вами в ближайшее время!"
        )

    await update.message.reply_text(user_msg, reply_markup=ReplyKeyboardRemove())

    # Build group message
    group_text = (
        f"📩 Yangi buyurtma / Новый заказ\n\n"
        f"👤 {user.first_name or '—'} (@{user.username or '—'})\n"
        f"📞 Telefon: {phone}\n"
        f"🍢 Mahsulot / Товар: {product}\n"
        f"🔢 Soni / Кол-во: {quantity}\n"
        f"💰 Jami / Всего: {fmt_price(total)}\n"
        f"📍 Joylashuv / Адрес: {branch or location or '—'}\n"
        f"💳 To'lov / Оплата: {payment}"
    )

    await context.bot.send_message(chat_id=GROUP_ID, text=group_text)

    # clear user_data for safety
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(lang_text(context, "Buyurtma bekor qilindi.", "Заказ отменён."), reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# ===== APP SETUP =====
app = ApplicationBuilder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        LANG: [MessageHandler(filters.TEXT & ~filters.COMMAND, language_selected)],
        MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_selected)],
        QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_selected)],
        DELIVERY_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_choice)],
        BRANCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, branch_selected)],
        LOCATION: [MessageHandler((filters.LOCATION | (filters.TEXT & ~filters.COMMAND)), location_received)],
        PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_selected)],
        PAYMENT_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_confirm)],
        PHONE: [MessageHandler((filters.CONTACT | (filters.TEXT & ~filters.COMMAND)), phone_received)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

app.add_handler(conv)
app.add_handler(CommandHandler("cancel", cancel))

print("✅ Kabob House Bot is running...")
app.run_polling()
