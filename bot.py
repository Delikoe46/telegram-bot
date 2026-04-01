import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler
)

TOKEN = "8687430803:AAGuuwryIXvbMSKDlJxc2eIwTe2NExLILDM"
CHANNEL_ID = -1003870607173

OWNER_ID = 5052230816
ALLOWED_USERS = [5052230816, 5510741509]

# 👇 OLDALAK (linkek maradnak)
SITES = {
    "1": "https://ddspn.lynmonkel.com/?mid=28093_2098891",
    "2": "https://ddspn.lynmonkel.com/?mid=28093_2098891",
    "3": "https://redirspinner.com/2Mt3?p=%2Fregistration%2F"
}

# 👇 FIX KÉP (EZT CSERÉLHETED)
FIX_IMAGE = "bh.png"

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

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Szia! 🎉")


# /create
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

    site_link = SITES[site_key]

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
    giveaway["site_link"] = site_link

    keyboard = [[InlineKeyboardButton("🎉 Részvétel (0)", callback_data="join")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    giveaway["reply_markup"] = reply_markup

    text = f"""🎉 GIVEAWAY! 🎉

🔗 {site_link}

🎁 {prize}
👥 Nyertesek: {winners_count}

⏳ Hátralévő idő: {duration_minutes} perc
"""

    msg = await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=FIX_IMAGE,
        caption=text,
        reply_markup=reply_markup
    )

    giveaway["message_id"] = msg.message_id

    await update.message.reply_text("✅ Giveaway kirakva!")

    context.job_queue.run_repeating(update_timer, interval=60, first=60)
    context.job_queue.run_once(end_giveaway, giveaway["remaining"])


# gomb
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not giveaway["active"]:
        return

    user = query.from_user
    username = user.username or str(user.id)

    if username in giveaway["participants"]:
        return

    giveaway["participants"].add(username)

    count = len(giveaway["participants"])

    keyboard = [[InlineKeyboardButton(f"🎉 Részvétel ({count})", callback_data="join")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    giveaway["reply_markup"] = reply_markup

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID,
            message_id=giveaway["message_id"],
            reply_markup=reply_markup
        )
    except:
        pass


# visszaszámláló
async def update_timer(context: ContextTypes.DEFAULT_TYPE):
    if not giveaway["active"]:
        return

    giveaway["remaining"] -= 60

    minutes = max(giveaway["remaining"] // 60, 0)

    text = f"""🎉 GIVEAWAY! 🎉

🔗 {giveaway['site_link']}

🎁 {giveaway['prize']}
👥 Nyertesek: {giveaway['winners_count']}

⏳ Hátralévő idő: {minutes} perc
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


# end
async def end_giveaway(context: ContextTypes.DEFAULT_TYPE):
    if not giveaway["active"]:
        return

    participants = list(giveaway["participants"])

    if not participants:
        await context.bot.send_message(CHANNEL_ID, "Nincs résztvevő 😅")
        giveaway["active"] = False
        return

    winners = random.sample(
        participants,
        min(len(participants), giveaway["winners_count"])
    )

    winners_text = "\n".join([f"@{w}" for w in winners])

    await context.bot.send_message(
        CHANNEL_ID,
        f"""🏆 GIVEAWAY LEZÁRVA!

🎁 {giveaway['prize']}

🎉 Nyertesek:
{winners_text}"""
    )

    giveaway["active"] = False


# indítás
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("create", create))
app.add_handler(CallbackQueryHandler(button))

print("Bot elindult... 🚀")

app.run_polling()
