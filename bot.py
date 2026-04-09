import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = -1003870607173

SITES = {
    "1": "https://ddspn.lynmonkel.com/?mid=28093_2098891",
    "2": "https://redirspinner.com/2Mt3?p=%2Fregistration%2F"
}

giveaways = {}

# CREATE
async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args

        winners = int(args[0])
        prize = args[1]
        minutes = int(args[2])
        site_id = args[3] if len(args) > 3 else "1"

        site = SITES.get(site_id, SITES["1"])

        gid = str(update.message.id)

        giveaways[gid] = {
            "participants": {},
            "winners": winners,
            "prize": prize,
            "site": site,
            "remaining": minutes * 60,
            "message_id": None,
            "active": True
        }

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎉 Részt veszek (0)", callback_data=f"join_{gid}")]
        ])

        text = f"""🎉 GIVEAWAY!

🎁 {prize}
👥 Nyertesek: {winners}
⏳ {minutes}:00

🔗 {site}

👇 Jelentkezz!"""

        msg = await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=open("image.jpg", "rb"),
            caption=text,
            reply_markup=keyboard
        )

        giveaways[gid]["message_id"] = msg.message_id

        context.application.create_task(timer(context, gid))

    except Exception as e:
        print("CREATE HIBA:", e)


# JOIN + COUNTER
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    gid = query.data.split("_")[1]
    g = giveaways.get(gid)

    if not g or not g["active"]:
        return

    uid = query.from_user.id
    name = query.from_user.first_name

    if uid in g["participants"]:
        await query.answer("❗ Már benne vagy", show_alert=True)
        return

    g["participants"][uid] = name
    count = len(g["participants"])

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🎉 Részt veszek ({count})", callback_data=f"join_{gid}")]
    ])

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID,
            message_id=g["message_id"],
            reply_markup=keyboard
        )
    except:
        pass

    await query.answer("✅ Jelentkeztél!")


# ⏳ TIMER (másodperces + fix end)
async def timer(context, gid):
    try:
        while True:
            g = giveaways.get(gid)

            if not g or not g["active"]:
                return

            if g["remaining"] <= 0:
                break

            await asyncio.sleep(1)
            g["remaining"] -= 1

            if g["remaining"] % 5 != 0:
                continue

            minutes = g["remaining"] // 60
            seconds = g["remaining"] % 60

            text = f"""🎉 GIVEAWAY!

🎁 {g['prize']}
👥 Nyertesek: {g['winners']}
⏳ {minutes}:{seconds:02d}

🔗 {g['site']}

👇 Jelentkezz!"""

            try:
                await context.bot.edit_message_caption(
                    chat_id=CHANNEL_ID,
                    message_id=g["message_id"],
                    caption=text
                )
            except:
                pass

        await end_giveaway(context, gid)

    except Exception as e:
        print("TIMER HIBA:", e)


# END
async def end_giveaway(context, gid):
    g = giveaways.get(gid)

    if not g or not g["active"]:
        return

    g["active"] = False

    if not g["participants"]:
        await context.bot.send_message(CHANNEL_ID, "❌ Nincs résztvevő")
        return

    users = list(g["participants"].keys())

    winners = random.sample(
        users,
        min(len(users), g["winners"])
    )

    text = "\n".join(
        [f"<a href='tg://user?id={u}'>{g['participants'][u]}</a>" for u in winners]
    )

    await context.bot.send_message(
        CHANNEL_ID,
        f"""🏆 GIVEAWAY VÉGE!

🎁 {g['prize']}

🎉 Nyertesek:
{text}""",
        parse_mode="HTML"
    )


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot fut 🚀")


# MAIN
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("create", create))
app.add_handler(CallbackQueryHandler(button))

print("Bot elindult 🚀")
app.run_polling()
