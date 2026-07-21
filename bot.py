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
    filters,
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
        [
            InlineKeyboardButton(
                "🎁 Giveaway indítása",
                callback_data="panel_create"
            )
        ]
    ])

    await update.message.reply_text(
        "⚙️ Panel:",
        reply_markup=keyboard
    )


# ================= CREATE =================

async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_GIVEAWAY

    try:
        args = context.args

        if len(args) < 3:
            if update.message:
                await update.message.reply_text(
                    "❗ Használat:\n/create <nyertesek> <nyeremény> <percek>\n\n"
                    "Példa:\n/create 2 50 USDT 10"
                )
            return

        winners = int(args[0])
        minutes = int(args[-1])
        prize = " ".join(args[1:-1])

        if winners <= 0:
            raise ValueError("A nyertesek száma legalább 1 legyen.")

        if minutes <= 0:
            raise ValueError("Az idő legalább 1 perc legyen.")

        if not prize.strip():
            raise ValueError("A nyeremény nem lehet üres.")

        # Parancsból vagy panelből indított giveaway azonosítója
        if update.message:
            gid = str(update.message.id)
        elif update.callback_query:
            gid = str(update.callback_query.message.message_id)
        else:
            gid = str(random.randint(100000, 999999))

        # Ha ugyanarról a panelüzenetről többször indítanának
        while gid in giveaways:
            gid = f"{gid}_{random.randint(1000, 9999)}"

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
            [
                InlineKeyboardButton(
                    "🎉 Részt veszek (0)",
                    callback_data=f"join_{gid}"
                )
            ]
        ])

        text = f"""🎉 GIVEAWAY!

🎁 {prize}
👥 Nyertesek: {winners}
⏳ {minutes} perc

🔗 https://abethunters.com/

👇 Jelentkezz!"""

        with open("image.jpg", "rb") as photo:
            msg = await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo,
                caption=text,
                reply_markup=keyboard
            )

        giveaways[gid]["message_id"] = msg.message_id

        context.application.create_task(
            timer(context, gid)
        )

        if update.message:
            await update.message.reply_text(
                "✅ A giveaway sikeresen elindult!"
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "✅ A giveaway sikeresen elindult!"
            )

    except (ValueError, IndexError) as e:
        print("CREATE INPUT ERROR:", e)

        message = (
            "❗ Hibás adatok.\n\n"
            "Parancs használata:\n"
            "/create <nyertesek> <nyeremény> <percek>\n\n"
            "Példa:\n"
            "/create 2 50 USDT 10"
        )

        if update.message:
            await update.message.reply_text(message)
        elif update.callback_query:
            await update.callback_query.message.reply_text(message)

    except FileNotFoundError:
        print("CREATE ERROR: image.jpg nem található")

        message = "❌ Az image.jpg fájl nem található."

        if update.message:
            await update.message.reply_text(message)
        elif update.callback_query:
            await update.callback_query.message.reply_text(message)

    except Exception as e:
        print("CREATE ERROR:", e)

        message = "❌ Hiba történt a giveaway létrehozásakor."

        if update.message:
            await update.message.reply_text(message)
        elif update.callback_query:
            await update.callback_query.message.reply_text(message)


# ================= BUTTON =================

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query:
        return

    user_id = query.from_user.id
    callback_data = query.data or ""

    # ================= PANEL START =================

    if callback_data == "panel_create":
        user_states[user_id] = {
            "step": "prize"
        }

        await query.answer()

        await query.message.reply_text(
            "🎁 Írd be a nyereményt:"
        )
        return

    # ================= TIME SELECT =================

    if callback_data.startswith("time_"):
        state = user_states.get(user_id)

        if not state:
            await query.answer(
                "❗ A panel lejárt. Indítsd el újra a /panel paranccsal.",
                show_alert=True
            )
            return

        try:
            minutes = int(callback_data.split("_", 1)[1])
        except (ValueError, IndexError):
            await query.answer(
                "❌ Hibás időbeállítás.",
                show_alert=True
            )
            return

        state["minutes"] = minutes
        state["step"] = "confirm"

        preview = f"""👀 ELŐNÉZET:

🎁 {state['prize']}
👥 Nyertesek: {state['winners']}
⏳ {minutes} perc

🔗 https://abethunters.com/

Elindítod?"""

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Igen",
                    callback_data="confirm_yes"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Nem",
                    callback_data="confirm_no"
                )
            ]
        ])

        await query.answer()

        await query.message.reply_text(
            preview,
            reply_markup=keyboard
        )
        return

    # ================= CONFIRM YES =================

    if callback_data == "confirm_yes":
        state = user_states.get(user_id)

        if not state:
            await query.answer(
                "❗ A panel lejárt. Indítsd el újra a /panel paranccsal.",
                show_alert=True
            )
            return

        context.args = [
            str(state["winners"]),
            *state["prize"].split(),
            str(state["minutes"])
        ]

        del user_states[user_id]

        await query.answer(
            "⏳ Giveaway indítása..."
        )

        await create(update, context)
        return

    # ================= CONFIRM NO =================

    if callback_data == "confirm_no":
        user_states.pop(user_id, None)

        await query.answer()

        await query.message.reply_text(
            "❌ Giveaway létrehozása megszakítva."
        )
        return

    # ================= JOIN =================

    if callback_data.startswith("join_"):
        gid = callback_data.split("_", 1)[1]
        giveaway = giveaways.get(gid)

        if not giveaway or not giveaway["active"]:
            await query.answer(
                "❌ Ez a giveaway már véget ért.",
                show_alert=True
            )
            return

        uid = query.from_user.id

        name = (
            query.from_user.full_name
            or query.from_user.first_name
            or query.from_user.username
            or "Ismeretlen felhasználó"
        )

        if uid in giveaway["participants"]:
            count = len(giveaway["participants"])

            await query.answer(
                f"❗ Már csatlakoztál ehhez a giveawayhez!\n\n"
                f"Jelenlegi résztvevők: {count}",
                show_alert=True
            )
            return

        giveaway["participants"][uid] = name
        count = len(giveaway["participants"])

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"🎉 Részt veszek ({count})",
                    callback_data=f"join_{gid}"
                )
            ]
        ])

        try:
            await context.bot.edit_message_reply_markup(
                chat_id=CHANNEL_ID,
                message_id=giveaway["message_id"],
                reply_markup=keyboard
            )
        except Exception as e:
            print("JOIN BUTTON UPDATE ERROR:", e)

        await query.answer(
            f"✅ Sikeresen csatlakoztál a giveawayhez!\n\n"
            f"Jelenlegi résztvevők: {count}",
            show_alert=True
        )
        return

    await query.answer(
        "❌ Ismeretlen művelet.",
        show_alert=True
    )


# ================= PANEL INPUT =================

async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.text:
        return

    user_id = update.message.from_user.id
    state = user_states.get(user_id)

    if not state:
        return

    step = state.get("step")
    text = update.message.text.strip()

    # ================= PRIZE INPUT =================

    if step == "prize":
        if not text:
            await update.message.reply_text(
                "❗ A nyeremény nem lehet üres."
            )
            return

        state["prize"] = text
        state["step"] = "winners"

        await update.message.reply_text(
            "👥 Hány nyertes legyen?"
        )
        return

    # ================= WINNERS INPUT =================

    if step == "winners":
        try:
            winners = int(text)

            if winners <= 0:
                raise ValueError

        except ValueError:
            await update.message.reply_text(
                "❗ Pozitív egész számot írj!\n\n"
                "Példa: 2"
            )
            return

        state["winners"] = winners
        state["step"] = "time"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "1 perc",
                    callback_data="time_1"
                )
            ],
            [
                InlineKeyboardButton(
                    "5 perc",
                    callback_data="time_5"
                )
            ],
            [
                InlineKeyboardButton(
                    "10 perc",
                    callback_data="time_10"
                )
            ],
            [
                InlineKeyboardButton(
                    "30 perc",
                    callback_data="time_30"
                )
            ],
            [
                InlineKeyboardButton(
                    "60 perc",
                    callback_data="time_60"
                )
            ]
        ])

        await update.message.reply_text(
            "⏳ Válassz időt:",
            reply_markup=keyboard
        )
        return


# ================= TIMER =================

async def timer(context: ContextTypes.DEFAULT_TYPE, gid: str):
    while True:
        giveaway = giveaways.get(gid)

        if not giveaway or not giveaway["active"]:
            return

        if giveaway["remaining"] <= 0:
            break

        await asyncio.sleep(60)

        giveaway = giveaways.get(gid)

        if not giveaway or not giveaway["active"]:
            return

        giveaway["remaining"] -= 1

        if giveaway["remaining"] < 0:
            giveaway["remaining"] = 0

        count = len(giveaway["participants"])

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"🎉 Részt veszek ({count})",
                    callback_data=f"join_{gid}"
                )
            ]
        ])

        text = f"""🎉 GIVEAWAY!

🎁 {giveaway['prize']}
👥 Nyertesek: {giveaway['winners']}
⏳ {giveaway['remaining']} perc

🔗 https://abethunters.com/

👇 Jelentkezz!"""

        try:
            await context.bot.edit_message_caption(
                chat_id=CHANNEL_ID,
                message_id=giveaway["message_id"],
                caption=text,
                reply_markup=keyboard
            )
        except Exception as e:
            print("TIMER EDIT ERROR:", e)

    await end_giveaway(context, gid)


# ================= END =================

async def end_giveaway(
    context: ContextTypes.DEFAULT_TYPE,
    gid: str
):
    giveaway = giveaways.get(gid)

    if not giveaway or not giveaway["active"]:
        return

    giveaway["active"] = False

    count = len(giveaway["participants"])

    ended_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"🔒 Giveaway véget ért ({count})",
                callback_data=f"join_{gid}"
            )
        ]
    ])

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID,
            message_id=giveaway["message_id"],
            reply_markup=ended_keyboard
        )
    except Exception as e:
        print("END BUTTON ERROR:", e)

    if not giveaway["participants"]:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"""❌ GIVEAWAY VÉGE!

🎁 {giveaway['prize']}

Nem volt egyetlen résztvevő sem."""
        )
        return

    users = list(giveaway["participants"].keys())

    winner_count = min(
        len(users),
        giveaway["winners"]
    )

    winners = random.sample(
        users,
        winner_count
    )

    winner_text = "\n".join([
        (
            f"• <a href='tg://user?id={uid}'>"
            f"{escape_html(giveaway['participants'][uid])}"
            f"</a>"
        )
        for uid in winners
    ])

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"""🏆 GIVEAWAY VÉGE!

🎁 {escape_html(giveaway['prize'])}
👥 Résztvevők: {count}

🎉 Nyertesek:
{winner_text}""",
        parse_mode="HTML"
    )


# ================= REROLL =================

async def reroll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global LAST_GIVEAWAY

    if not LAST_GIVEAWAY:
        await update.message.reply_text(
            "❌ Még nem volt giveaway."
        )
        return

    giveaway = giveaways.get(LAST_GIVEAWAY)

    if not giveaway or not giveaway["participants"]:
        await update.message.reply_text(
            "❌ Nincs olyan giveaway, amelyben vannak résztvevők."
        )
        return

    users = list(giveaway["participants"].keys())

    try:
        count = (
            int(context.args[0])
            if context.args
            else giveaway["winners"]
        )

        if count <= 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❗ Használat:\n/reroll\nvagy\n/reroll 2"
        )
        return

    count = min(count, len(users))

    new_winners = random.sample(
        users,
        count
    )

    winner_text = "\n".join([
        (
            f"• <a href='tg://user?id={uid}'>"
            f"{escape_html(giveaway['participants'][uid])}"
            f"</a>"
        )
        for uid in new_winners
    ])

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"""🔄 REROLL!

🎁 {escape_html(giveaway['prize'])}

🎉 ÚJ NYERTESEK:
{winner_text}""",
        parse_mode="HTML"
    )

    await update.message.reply_text(
        f"✅ Reroll elküldve. Új nyertesek száma: {count}"
    )


# ================= CANCEL =================

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global LAST_GIVEAWAY

    if not LAST_GIVEAWAY:
        await update.message.reply_text(
            "❌ Nincs leállítható giveaway."
        )
        return

    giveaway = giveaways.get(LAST_GIVEAWAY)

    if not giveaway:
        await update.message.reply_text(
            "❌ A giveaway nem található."
        )
        return

    if not giveaway["active"]:
        await update.message.reply_text(
            "❌ Ez a giveaway már véget ért."
        )
        return

    giveaway["active"] = False

    try:
        await context.bot.delete_message(
            chat_id=CHANNEL_ID,
            message_id=giveaway["message_id"]
        )

        await update.message.reply_text(
            "✅ A giveaway leállítva és törölve lett."
        )

    except Exception as e:
        print("CANCEL ERROR:", e)

        await update.message.reply_text(
            "⚠️ A giveaway leállt, de az üzenetet nem sikerült törölni."
        )


# ================= START =================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        """Bot fut 🚀

Elérhető parancsok:

/panel – Giveaway létrehozása panellel
/create – Giveaway létrehozása paranccsal
/reroll – Új nyertes húzása
/cancel – Aktív giveaway megszakítása"""
    )


# ================= HTML ESCAPE =================

def escape_html(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ================= MAIN =================

if not TOKEN:
    raise RuntimeError("A TOKEN környezeti változó nincs beállítva.")

if not WEBHOOK_URL:
    raise RuntimeError("A WEBHOOK_URL környezeti változó nincs beállítva.")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("panel", panel))
app.add_handler(CommandHandler("create", create))
app.add_handler(CommandHandler("reroll", reroll))
app.add_handler(CommandHandler("cancel", cancel))

app.add_handler(CallbackQueryHandler(button))

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        message_handler
    )
)

print("Webhook indul 🚀")

app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_url=WEBHOOK_URL
)
