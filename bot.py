import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8080))

CHANNEL_ID = -1003870607173

giveaways = {}
LAST_GIVEAWAY = None
user_states = {}

# ================= PANEL =================

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Giveaway indítása", callback_data="panel_create")]
    ])
    await update.message.reply_text("⚙️ Panel:", reply_markup=keyboard)

# ================= CREATE =================

async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_GIVEAWAY

    try:
        args = context.args
        winners = int(args[0])
        minutes = int(args[-1])
        prize = " ".join(args[1:-1])

        gid = str(update.message.id)
        LAST_GIVEAWAY = gid

        giveaways[gid] = {
            "participants": {},
            "winners": winners,
            "prize": prize,
            "remaining": minutes,
            "message_id": None,
            "active": True,
        }

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎉 Részt veszek (0)", callback_data=f"join_{gid}")]
        ])

        text = f"""🎉 GIVEAWAY!

🎁 {prize}
👥 Nyertesek: {winners}
⏳ {minutes} perc

🔗 https://abethunters.com/

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
        print("CREATE ERROR:", e)

# ================= BUTTON =================

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    # ===== PANEL START =====
    if query.data == "panel_create":
        user_states[user_id] = {"step": "prize"}
        await query.message.reply_text("🎁 Írd be a nyereményt:")
        return

    # ===== TIME SELECT =====
    if query.data.startswith("time_"):
        s = user_states.get(user_id)
        if not s:
            await query.answer("❗ Panel lejárt", show_alert=True)
            return

        minutes = int(query.data.split("_")[1])
        s["minutes"] = minutes
        s["step"] = "confirm"

        preview = f"""👀 ELŐNÉZET:

🎁 {s['prize']}
👥 Nyertesek: {s['winners']}
⏳ {minutes} perc

🔗 https://abethunters.com/

Elindítod?"""

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Igen", callback_data="confirm_yes")],
            [InlineKeyboardButton("❌ Nem", callback_data="confirm_no")]
        ])

        await query.message.reply_text(preview, reply_markup=keyboard)
        return

    # ===== CONFIRM =====
    if query.data == "confirm_yes":
        s = user_states.get(user_id)
        if not s:
            await query.answer("❗ Panel lejárt", show_alert=True)
            return

        context.args = [
            str(s["winners"]),
            *s["prize"].split(),
            str(s["minutes"])
        ]

        del user_states[user_id]
        await create(update, context)
        return

    if query.data == "confirm_no":
        if user_id in user_states:
            del user_states[user_id]

        await query.message.reply_text("❌ Megszakítva")
        return

    # ===== JOIN =====
    if query.data.startswith("join_"):
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

# ================= PANEL INPUT =================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_states:
        return

    state = user_states[user_id]
    step = state["step"]
    text = update.message.text

    if step == "prize":
        state["prize"] = text
        state["step"] = "winners"
        await update.message.reply_text("👥 Hány nyertes?")
        return

    if step == "winners":
        try:
            state["winners"] = int(text)
        except:
            await update.message.reply_text("❗ Számot írj!")
            return

        state["step"] = "time"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("1 perc", callback_data="time_1")],
            [InlineKeyboardButton("5 perc", callback_data="time_5")],
            [InlineKeyboardButton("10 perc", callback_data="time_10")]
        ])

        await update.message.reply_text("⏳ Válassz időt:", reply_markup=keyboard)
        return

# ================= TIMER =================

async def timer(context, gid):
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

🔗 https://abethunters.com/

👇 Jelentkezz!"""

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

# ================= END =================

async def end_giveaway(context, gid):
    g = giveaways.get(gid)

    if not g or not g["active"]:
        return

    g["active"] = False

    if not g["participants"]:
        await context.bot.send_message(CHANNEL_ID, "❌ Nincs résztvevő")
        return

    users = list(g["participants"].keys())
    winners = random.sample(users, min(len(users), g["winners"]))

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

# ================= REROLL =================

async def reroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_GIVEAWAY

    g = giveaways.get(LAST_GIVEAWAY)

    if not g or not g["participants"]:
        return

    users = list(g["participants"].keys())

    count = int(context.args[0]) if context.args else g["winners"]
    count = min(count, len(users))

    new = random.sample(users, count)

    text = "\n".join(
        [f"<a href='tg://user?id={u}'>{g['participants'][u]}</a>" for u in new]
    )

    await context.bot.send_message(
        CHANNEL_ID,
        f"""🔄 REROLL!

🎁 {g['prize']}

🎉 ÚJ NYERTESEK:
{text}""",
        parse_mode="HTML"
    )

# ================= CANCEL =================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_GIVEAWAY

    g = giveaways.get(LAST_GIVEAWAY)

    if not g:
        return

    g["active"] = False

    try:
        await context.bot.delete_message(
            chat_id=CHANNEL_ID,
            message_id=g["message_id"]
        )
    except:
        pass

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot fut 🚀")

# ================= MAIN =================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("panel", panel))
app.add_handler(CommandHandler("create", create))
app.add_handler(CommandHandler("reroll", reroll))
app.add_handler(CommandHandler("cancel", cancel))

app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

print("Webhook indul 🚀")

app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_url=WEBHOOK_URL
)
