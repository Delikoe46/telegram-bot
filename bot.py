import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8080))

CHANNEL_ID = -1003870607173

SITES = {
    "spinbetter": "https://redirspinner.com/2Mt3?p=%2Fregistration%2F",
    "dudespin": "https://ddspn.lynmonkel.com/?mid=28093_2098891",
    "betmatch": "https://trackmyaff.com/?serial=61343867&creative_id=3540"
}

giveaways = {}
LAST_GIVEAWAY = None

# CREATE
async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_GIVEAWAY

    try:
        args = context.args
        winners = int(args[0])

        possible_site = args[-1].lower()

        if possible_site in SITES:
            site_id = possible_site
            minutes = int(args[-2])
            prize = " ".join(args[1:-2])
        else:
            site_id = None
            minutes = int(args[-1])
            prize = " ".join(args[1:-1])

        site = SITES.get(site_id)

        gid = str(update.message.id)
        LAST_GIVEAWAY = gid

        giveaways[gid] = {
            "participants": {},
            "winners": winners,
            "prize": prize,
            "site": site,
            "site_id": site_id,
            "remaining": minutes,
            "message_id": None,
            "active": True,
            "last_winners": []
        }

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎉 Részt veszek (0)", callback_data=f"join_{gid}")]
        ])

        text = f"""🎉 GIVEAWAY!

🎁 {prize}
👥 Nyertesek: {winners}
⏳ {minutes} perc
"""

        if site:
            text += f"\n🔗 {site}"

        if site_id == "spinbetter":
            text += "\n\n🎁 Használd a promo kódot: BETHUNTERS"

        text += "\n\n👇 Jelentkezz!"

        msg = await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=open("image.jpg", "rb"),
            caption=text,
            reply_markup=keyboard
        )

        giveaways[gid]["message_id"] = msg.message_id
        context.application.create_task(timer(context, gid))

    except Exception as e:
        print("CREATE ERROR:", e)


# JOIN
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


# TIMER
async def timer(context, gid):
    try:
        while True:
            g = giveaways.get(gid)

            if not g or not g["active"]:
                return

            if g["remaining"] <= 0:
                break

            await asyncio.sleep(60)
            g["remaining"] -= 1

            count = len(g["participants"])

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🎉 Részt veszek ({count})", callback_data=f"join_{gid}")]
            ])

            text = f"""🎉 GIVEAWAY!

🎁 {g['prize']}
👥 Nyertesek: {g['winners']}
⏳ {g['remaining']} perc
"""

            if g["site"]:
                text += f"\n🔗 {g['site']}"

            if g.get("site_id") == "spinbetter":
                text += "\n\n🎁 Promo kód: BETHUNTERS"

            text += "\n\n👇 Jelentkezz!"

            try:
                await context.bot.edit_message_caption(
                    chat_id=CHANNEL_ID,
                    message_id=g["message_id"],
                    caption=text,
                    reply_markup=keyboard
                )
            except:
                pass

        await end_giveaway(context, gid)

    except Exception as e:
        print("TIMER ERROR:", e)


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

    g["last_winners"] = winners  # 🔥 fontos

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


# 🔄 SMART REROLL
async def reroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_GIVEAWAY

    gid = LAST_GIVEAWAY
    g = giveaways.get(gid)

    if not g or not g["participants"]:
        await update.message.reply_text("❌ Nincs kit újrahúzni")
        return

    try:
        reroll_count = int(context.args[0]) if context.args else g["winners"]
    except:
        reroll_count = g["winners"]

    users = list(g["participants"].keys())
    old_winners = g.get("last_winners", [])

    available = [u for u in users if u not in old_winners]

    if not available:
        await update.message.reply_text("❌ Nincs új ember a rerollhoz")
        return

    new_winners = random.sample(
        available,
        min(len(available), reroll_count)
    )

    final_winners = old_winners.copy()
    final_winners = final_winners[: g["winners"] - len(new_winners)]
    final_winners.extend(new_winners)

    g["last_winners"] = final_winners

    text = "\n".join(
        [f"<a href='tg://user?id={u}'>{g['participants'][u]}</a>" for u in final_winners]
    )

    await context.bot.send_message(
        CHANNEL_ID,
        f"""🔄 REROLL!

🎁 {g['prize']}

🎉 Friss nyertesek:
{text}""",
        parse_mode="HTML"
    )


# CANCEL
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_GIVEAWAY

    gid = LAST_GIVEAWAY
    g = giveaways.get(gid)

    if not g:
        await update.message.reply_text("❌ Nincs aktív giveaway")
        return

    g["active"] = False

    try:
        await context.bot.delete_message(
            chat_id=CHANNEL_ID,
            message_id=g["message_id"]
        )
    except:
        pass

    await update.message.reply_text("🛑 Giveaway törölve")


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot fut 🚀")


# MAIN
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("create", create))
app.add_handler(CommandHandler("reroll", reroll))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(CallbackQueryHandler(button))

print("Webhook indul 🚀")

app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_url=WEBHOOK_URL
)
