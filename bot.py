import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = -1003870607173  # ide a te channel id

giveaways = {}

# CREATE
async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        winners_count = int(args[0])
        prize = args[1]
        duration = int(args[2])

        giveaway_id = str(update.message.id)

        giveaways[giveaway_id] = {
            "participants": {},
            "winners_count": winners_count,
            "prize": prize,
            "active": True,
            "message_id": None
        }

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎉 Részt veszek (0)", callback_data=f"join_{giveaway_id}")]
        ])

        msg = await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=open("image.jpg", "rb"),
            caption=f"""🎉 GIVEAWAY!

🎁 Nyeremény: {prize}
👥 Nyertesek: {winners_count}
⏳ Idő: {duration} perc

👇 Jelentkezz!""",
            reply_markup=keyboard
        )

        giveaways[giveaway_id]["message_id"] = msg.message_id

        # timer
        context.job_queue.run_once(end_giveaway, duration * 60, data=giveaway_id)

    except Exception as e:
        print(e)


# BUTTON (JOIN + LIVE COUNTER)
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("join_"):
        giveaway_id = data.split("_")[1]

        if giveaway_id in giveaways:
            giveaway = giveaways[giveaway_id]

            user_id = query.from_user.id
            user_name = query.from_user.first_name

            # mentjük usert
            giveaway["participants"][user_id] = user_name

            count = len(giveaway["participants"])

            # új gomb (live counter)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🎉 Részt veszek ({count})", callback_data=f"join_{giveaway_id}")]
            ])

            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=CHANNEL_ID,
                    message_id=giveaway["message_id"],
                    reply_markup=keyboard
                )
            except:
                pass

            await query.answer("✅ Jelentkeztél!", show_alert=True)


# END GIVEAWAY
async def end_giveaway(context: ContextTypes.DEFAULT_TYPE):
    giveaway_id = context.job.data
    giveaway = giveaways.get(giveaway_id)

    if not giveaway or not giveaway["participants"]:
        await context.bot.send_message(CHANNEL_ID, "❌ Nincs résztvevő!")
        return

    participants = list(giveaway["participants"].keys())

    winners = random.sample(
        participants,
        min(len(participants), giveaway["winners_count"])
    )

    # TAGELÉS
    winners_text = "\n".join(
        [f"<a href='tg://user?id={uid}'>{giveaway['participants'][uid]}</a>" for uid in winners]
    )

    await context.bot.send_message(
        CHANNEL_ID,
        f"""🏆 GIVEAWAY VÉGE!

🎁 {giveaway['prize']}

🎉 Nyertesek:
{winners_text}""",
        parse_mode="HTML"
    )


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot működik 🚀")


# MAIN
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("create", create))
app.add_handler(CallbackQueryHandler(button))

print("Bot elindult 🚀")
app.run_polling()
