import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

TOKEN = "8687430803:AAGuuwryIXvbMSKDlJxc2eIwTe2NExLILDM"
CHANNEL_ID = -1003870607173

ALLOWED_USERS = [5052230816, 5510741509]

SITES = {
    "1": "https://ddspn.lynmonkel.com/?mid=28093_2098891",
    "2": "https://ddspn.lynmonkel.com/?mid=28093_2098891",
    "3": "https://redirspinner.com/2Mt3?p=%2Fregistration%2F"
}

FIX_IMAGE = "https://via.placeholder.com/600x300.png?text=GIVEAWAY"

giveaway = {
    "active": False,
    "prize": "",
    "winners_count": 0,
    "participants": set(),
    "message_id": None,
    "remaining": 0,
    "site_link": "",
    "reply_markup": None
}

print("BOT ELINDUL...")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Szia! 🎉")

async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("Nincs jogosultságod ❌")
        return

    if giveaway["active"]:
        await update.message.reply_text("Már fut egy giveaway ❗")
        return

    if len(context.args) < 4:
        await update.message.reply_text("Használat: /create oldal nyeremény nyertesek perc")
        return

    site_key = context.args[0]
    if site_key not in SITES:
        await update.message.reply_text("Hibás oldal ❌")
        return

    try:
        winners_count = int(context.args[-2])
        duration_minutes = int(context.args[-1])
    except:
        await update.message.reply_text("Hibás szám ❌")
        return

    prize = " ".join(context.args[1:-2])

    giveaway["active"] = True
    giveaway["prize"] = prize
    giveaway["winners_count"] = winners_count
    giveaway["participants"].clear()
    giveaway["remaining"] = duration_minutes * 60
    giveaway["site_link"] = SITES[site_key]

    keyboard = [[InlineKeyboardButton("🎉 Részvétel (0)", callback_data="join")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    giveaway["reply_markup"] = reply_markup

    text = f"""🎉 GIVEAWAY!

🔗 {giveaway['site_link']}

🎁 {prize}
👥 Nyertesek: {winners_count}

⏳ {duration_minutes} perc
"""

    msg = await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=FIX_IMAGE,
        caption=text,
        reply_markup=reply_markup
    )

    giveaway["message_id"] = msg.message_id

    context.job_queue.run_repeating(update_timer, interval=60)
    context.job_queue.run_once(end_giveaway, giveaway["remaining"])

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not giveaway["active"]:
        return

    user = query.from_user.username or str(query.from_user.id)

    if user in giveaway["participants"]:
        return

    giveaway["participants"].add(user)
    count = len(giveaway["participants"])

    keyboard = [[InlineKeyboardButton(f"🎉 Részvétel ({count})", callback_data="join")]]

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID,
            message_id=giveaway["message_id"],
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except:
        pass

async def update_timer(context: ContextTypes.DEFAULT_TYPE):
    if not giveaway["active"]:
        return

    giveaway["remaining"] -= 60
    minutes = max(giveaway["remaining"] // 60, 0)

    text = f"""🎉 GIVEAWAY!

🔗 {giveaway['site_link']}

🎁 {giveaway['prize']}
👥 Nyertesek: {giveaway['winners_count']}

⏳ {minutes} perc
"""

    try:
        await context.bot.edit_message_caption(
            chat_id=CHANNEL_ID,
            message_id=giveaway["message_id"],
            caption=text,
            reply_markup=giveaway["reply_markup"]
        )
    except:
        pass

async def end_giveaway(context: ContextTypes.DEFAULT_TYPE):
    if not giveaway["active"]:
        return

    participants = list(giveaway["participants"])

    if not participants:
        await context.bot.send_message(CHANNEL_ID, "Nincs résztvevő")
        giveaway["active"] = False
        return

    winners = random.sample(participants, min(len(participants), giveaway["winners_count"]))

    await context.bot.send_message(
        CHANNEL_ID,
        "🏆 NYERTESEK:\n" + "\n".join([f"@{w}" for w in winners])
    )

    giveaway["active"] = False

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("create", create))
app.add_handler(CallbackQueryHandler(button))

print("Bot elindult... 🚀")

app.run_polling()
