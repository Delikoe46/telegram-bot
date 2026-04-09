import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = -1003870607173

# affiliate linkek (site szám alapján)
SITES = {
    "1": "https://ddspn.lynmonkel.com/?mid=28093_2098891",
    "2": "https://ddspn.lynmonkel.com/?mid=28093_2098891",
    "3": "https://redirspinner.com/2Mt3?p=%2Fregistration%2F"
}

# több giveaway
giveaways = {}

# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot fut 🚀")

# CREATE
async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        site = args[0]
        prize = args[1]
        winners_count = int(args[2])
        duration_minutes = int(args[3])
    except:
        await update.message.reply_text("Használat: /create [site] [nyeremény] [nyertesek] [perc]")
        return

    if site not in SITES:
        await update.message.reply_text("Hibás site ID!")
        return

    giveaway_id = str(random.randint(1000, 9999))

    keyboard = [[InlineKeyboardButton("🎉 Részvétel", callback_data=f"join_{giveaway_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"""🎉 GIVEAWAY!

🔗 {SITES[site]}

🎁 {prize}
👥 Nyertesek: {winners_count}

⏳ {duration_minutes} perc
"""

    # KÉP + POSZT
    try:
        msg = await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=open("image.jpg", "rb"),
            caption=text,
            reply_markup=reply_markup
        )
    except Exception as e:
        await update.message.reply_text(f"Hiba kép küldésnél: {e}")
        return

    giveaways[giveaway_id] = {
        "active": True,
        "participants": set(),
        "winners_count": winners_count,
        "prize": prize,
        "remaining": duration_minutes * 60,
        "message_id": msg.message_id,
        "site_link": SITES[site],
        "reply_markup": reply_markup
    }

    # TIMER INDÍTÁS
    context.application.create_task(timer_task(context, giveaway_id))

    await update.message.reply_text("Giveaway elindítva 🚀")

# JOIN
async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    giveaway_id = query.data.split("_")[1]

    if giveaway_id not in giveaways:
        return

    giveaway = giveaways[giveaway_id]

    if not giveaway["active"]:
        return

    user_id = query.from_user.id

    if user_id in giveaway["participants"]:
        await query.answer("Már részt veszel!", show_alert=True)
        return

    giveaway["participants"].add(user_id)
    await query.answer("Csatlakoztál! 🎉")

# TIMER
async def timer_task(context, giveaway_id):
    giveaway = giveaways[giveaway_id]

    while giveaway["active"] and giveaway["remaining"] > 0:
        await asyncio.sleep(60)
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

    await end_giveaway(context, giveaway_id)

# END
async def end_giveaway(context, giveaway_id):
    giveaway = giveaways[giveaway_id]

    if not giveaway["active"]:
        return

    participants = list(giveaway["participants"])

    if not participants:
        await context.bot.send_message(CHANNEL_ID, "Nincs résztvevő 😢")
        giveaway["active"] = False
        return

    winners = random.sample(
        participants,
        min(len(participants), giveaway["winners_count"])
    )

    winners_text = "\n".join([f"👤 {w}" for w in winners])

    await context.bot.send_message(
        CHANNEL_ID,
        f"""🏁 GIVEAWAY LEZÁRVA!

🎁 {giveaway['prize']}

🎉 Nyertesek:
{winners_text}
"""
    )

    giveaway["active"] = False

# MAIN
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("create", create))
app.add_handler(CallbackQueryHandler(join, pattern="join_"))

print("Bot elindult 🚀")
app.run_polling()
