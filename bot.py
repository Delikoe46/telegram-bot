import os
import random
import asyncio

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)


# ================= CONFIG =================

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8080))

CHANNEL_ID = -1003870607173


# ================= STORAGE =================

giveaways = {}
LAST_GIVEAWAY = None
user_states = {}


# ================= HELPERS =================

def escape_html(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ================= PANEL =================

async def panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎁 Giveaway indítása",
                callback_data="panel_create"
            )
        ]
    ])

    await update.message.reply_text(
        "⚙️ Giveaway panel:",
        reply_markup=keyboard
    )


# ================= CREATE COMMAND =================

async def create(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global LAST_GIVEAWAY

    try:
        args = context.args

        if len(args) < 3:
            await update.message.reply_text(
                "❗ Használat:\n"
                "/create <nyertesek> <nyeremény> <percek>\n\n"
                "Példa:\n"
                "/create 2 50 USDT 10"
            )
            return

        winners = int(args[0])
        minutes = int(args[-1])
        prize = " ".join(args[1:-1]).strip()

        if winners <= 0:
            await update.message.reply_text(
                "❗ A nyertesek száma legalább 1 legyen."
            )
            return

        if minutes <= 0:
            await update.message.reply_text(
                "❗ Az idő legalább 1 perc legyen."
            )
            return

        if not prize:
            await update.message.reply_text(
                "❗ A nyeremény nem lehet üres."
            )
            return

        gid = f"{update.message.message_id}_{update.effective_user.id}"

        while gid in giveaways:
            gid = f"{gid}_{random.randint(1000, 9999)}"

        LAST_GIVEAWAY = gid

        giveaways[gid] = {
            "participants": {},
            "winners": winners,
            "prize": prize,
            "remaining": minutes,
            "message_id": None,
            "active": True
        }

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🎉 Részt veszek (0)",
                    callback_data=f"join_{gid}"
                )
            ]
        ])

        caption = f"""🎉 GIVEAWAY!

🎁 {prize}
👥 Nyertesek: {winners}
⏳ {minutes} perc

🔗 https://abethunters.com/

👇 Jelentkezz!"""

        with open("image.jpg", "rb") as photo:
            msg = await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo,
                caption=caption,
                reply_markup=keyboard,
                connect_timeout=30,
                read_timeout=60,
                write_timeout=60,
                pool_timeout=30
            )

        giveaways[gid]["message_id"] = msg.message_id

        context.application.create_task(
            timer(context, gid)
        )

        await update.message.reply_text(
            "✅ A giveaway sikeresen elindult!"
        )

    except FileNotFoundError:
        await update.message.reply_text(
            "❌ Az image.jpg fájl nem található."
        )

    except ValueError:
        await update.message.reply_text(
            "❗ A nyertesek és a percek helyére számot írj."
        )

    except Exception as e:
        print(
            "CREATE ERROR:",
            type(e).__name__,
            repr(e)
        )

        await update.message.reply_text(
            f"❌ Nem sikerült elindítani a giveawayt.\n\n"
            f"Hiba: {type(e).__name__}: {e}"
        )


# ================= CALLBACK BUTTONS =================

async def button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global LAST_GIVEAWAY

    query = update.callback_query

    if not query:
        return

    user_id = query.from_user.id
    callback_data = query.data or ""

    # ================= PANEL START =================

    if callback_data == "panel_create":
        await query.answer()

        user_states[user_id] = {
            "step": "prize"
        }

        await query.message.reply_text(
            "🎁 Írd be a nyereményt:"
        )
        return

    # ================= TIME SELECT =================

    if callback_data.startswith("time_"):
        state = user_states.get(user_id)

        if not state:
            await query.answer(
                "❗ A panel lejárt. Indítsd újra a /panel paranccsal.",
                show_alert=True
            )
            return

        try:
            minutes = int(
                callback_data.split("_", 1)[1]
            )
        except (ValueError, IndexError):
            await query.answer(
                "❌ Hibás időbeállítás.",
                show_alert=True
            )
            return

        await query.answer()

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
                "❗ A panel lejárt. Indítsd újra a /panel paranccsal.",
                show_alert=True
            )
            return

        winners = state["winners"]
        prize = state["prize"]
        minutes = state["minutes"]

        # Fontos: azonnal válaszolunk a callbackre
        await query.answer(
            "⏳ Giveaway indítása..."
        )

        gid = f"{query.message.message_id}_{user_id}"

        while gid in giveaways:
            gid = f"{gid}_{random.randint(1000, 9999)}"

        LAST_GIVEAWAY = gid

        giveaways[gid] = {
            "participants": {},
            "winners": winners,
            "prize": prize,
            "remaining": minutes,
            "message_id": None,
            "active": True
        }

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🎉 Részt veszek (0)",
                    callback_data=f"join_{gid}"
                )
            ]
        ])

        caption = f"""🎉 GIVEAWAY!

🎁 {prize}
👥 Nyertesek: {winners}
⏳ {minutes} perc

🔗 https://abethunters.com/

👇 Jelentkezz!"""

        try:
            with open("image.jpg", "rb") as photo:
                msg = await context.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=photo,
                    caption=caption,
                    reply_markup=keyboard,
                    connect_timeout=30,
                    read_timeout=60,
                    write_timeout=60,
                    pool_timeout=30
                )

            giveaways[gid]["message_id"] = msg.message_id

            user_states.pop(user_id, None)

            context.application.create_task(
                timer(context, gid)
            )

            await query.message.reply_text(
                "✅ A giveaway sikeresen elindult!"
            )

        except FileNotFoundError:
            giveaways.pop(gid, None)

            await query.message.reply_text(
                "❌ Az image.jpg fájl nem található."
            )

        except Exception as e:
            giveaways.pop(gid, None)

            print(
                "PANEL CREATE ERROR:",
                type(e).__name__,
                repr(e)
            )

            await query.message.reply_text(
                f"❌ Nem sikerült elindítani a giveawayt.\n\n"
                f"Hiba: {type(e).__name__}: {e}"
            )

        return

    # ================= CONFIRM NO =================

    if callback_data == "confirm_no":
        await query.answer()

        user_states.pop(user_id, None)

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
            count = len(
                giveaway["participants"]
            )

            await query.answer(
                f"❗ Már csatlakoztál ehhez a giveawayhez!\n\n"
                f"Jelenlegi résztvevők: {count}",
                show_alert=True
            )
            return

        giveaway["participants"][uid] = name

        count = len(
            giveaway["participants"]
        )

        # Először azonnal visszajelzünk a felhasználónak
        await query.answer(
            f"✅ Sikeresen csatlakoztál a giveawayhez!\n\n"
            f"Jelenlegi résztvevők: {count}",
            show_alert=True
        )

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
                reply_markup=keyboard,
                connect_timeout=30,
                read_timeout=30,
                write_timeout=30,
                pool_timeout=30
            )

        except Exception as e:
            print(
                "JOIN BUTTON UPDATE ERROR:",
                type(e).__name__,
                repr(e)
            )

        return

    # ================= UNKNOWN =================

    await query.answer(
        "❌ Ismeretlen művelet.",
        show_alert=True
    )


# ================= PANEL MESSAGE INPUT =================

async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return

    if not update.message.text:
        return

    user_id = update.message.from_user.id
    state = user_states.get(user_id)

    if not state:
        return

    step = state.get("step")
    text = update.message.text.strip()

    # ================= PRIZE =================

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

    # ================= WINNERS =================

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

async def timer(
    context: ContextTypes.DEFAULT_TYPE,
    gid: str
):
    while True:
        giveaway = giveaways.get(gid)

        if not giveaway:
            return

        if not giveaway["active"]:
            return

        if giveaway["remaining"] <= 0:
            break

        await asyncio.sleep(60)

        giveaway = giveaways.get(gid)

        if not giveaway:
            return

        if not giveaway["active"]:
            return

        giveaway["remaining"] -= 1

        if giveaway["remaining"] < 0:
            giveaway["remaining"] = 0

        count = len(
            giveaway["participants"]
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"🎉 Részt veszek ({count})",
                    callback_data=f"join_{gid}"
                )
            ]
        ])

        caption = f"""🎉 GIVEAWAY!

🎁 {giveaway['prize']}
👥 Nyertesek: {giveaway['winners']}
⏳ {giveaway['remaining']} perc

🔗 https://abethunters.com/

👇 Jelentkezz!"""

        try:
            await context.bot.edit_message_caption(
                chat_id=CHANNEL_ID,
                message_id=giveaway["message_id"],
                caption=caption,
                reply_markup=keyboard,
                connect_timeout=30,
                read_timeout=30,
                write_timeout=30,
                pool_timeout=30
            )

        except Exception as e:
            print(
                "TIMER EDIT ERROR:",
                type(e).__name__,
                repr(e)
            )

    await end_giveaway(
        context,
        gid
    )


# ================= END GIVEAWAY =================

async def end_giveaway(
    context: ContextTypes.DEFAULT_TYPE,
    gid: str
):
    giveaway = giveaways.get(gid)

    if not giveaway:
        return

    if not giveaway["active"]:
        return

    giveaway["active"] = False

    count = len(
        giveaway["participants"]
    )

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
            reply_markup=ended_keyboard,
            connect_timeout=30,
            read_timeout=30,
            write_timeout=30,
            pool_timeout=30
        )

    except Exception as e:
        print(
            "END BUTTON ERROR:",
            type(e).__name__,
            repr(e)
        )

    if not giveaway["participants"]:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"""❌ GIVEAWAY VÉGE!

🎁 {giveaway['prize']}

Nem volt egyetlen résztvevő sem."""
        )
        return

    users = list(
        giveaway["participants"].keys()
    )

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

    giveaway = giveaways.get(
        LAST_GIVEAWAY
    )

    if not giveaway:
        await update.message.reply_text(
            "❌ A giveaway nem található."
        )
        return

    if not giveaway["participants"]:
        await update.message.reply_text(
            "❌ A giveawaynek nincs résztvevője."
        )
        return

    users = list(
        giveaway["participants"].keys()
    )

    try:
        if context.args:
            count = int(context.args[0])
        else:
            count = giveaway["winners"]

        if count <= 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❗ Használat:\n"
            "/reroll\n"
            "vagy\n"
            "/reroll 2"
        )
        return

    count = min(
        count,
        len(users)
    )

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
        f"✅ Reroll elküldve. Új nyertesek: {count}"
    )


# ================= CANCEL =================

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global LAST_GIVEAWAY

    if not LAST_GIVEAWAY:
        await update.message.reply_text(
            "❌ Nincs aktív giveaway."
        )
        return

    giveaway = giveaways.get(
        LAST_GIVEAWAY
    )

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
            message_id=giveaway["message_id"],
            connect_timeout=30,
            read_timeout=30,
            write_timeout=30,
            pool_timeout=30
        )

        await update.message.reply_text(
            "✅ A giveaway leállítva és törölve lett."
        )

    except Exception as e:
        print(
            "CANCEL ERROR:",
            type(e).__name__,
            repr(e)
        )

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

Parancsok:

/panel – Giveaway létrehozása panellel
/create – Giveaway létrehozása paranccsal
/reroll – Új nyertes húzása
/cancel – Giveaway megszakítása"""
    )


# ================= ERROR HANDLER =================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):
    print(
        "BOT ERROR:",
        type(context.error).__name__,
        repr(context.error)
    )


# ================= MAIN =================

if not TOKEN:
    raise RuntimeError(
        "A TOKEN környezeti változó nincs beállítva."
    )

if not WEBHOOK_URL:
    raise RuntimeError(
        "A WEBHOOK_URL környezeti változó nincs beállítva."
    )

app = (
    ApplicationBuilder()
    .token(TOKEN)
    .connect_timeout(30)
    .read_timeout(30)
    .write_timeout(30)
    .pool_timeout(30)
    .build()
)

app.add_handler(
    CommandHandler(
        "start",
        start
    )
)

app.add_handler(
    CommandHandler(
        "panel",
        panel
    )
)

app.add_handler(
    CommandHandler(
        "create",
        create
    )
)

app.add_handler(
    CommandHandler(
        "reroll",
        reroll
    )
)

app.add_handler(
    CommandHandler(
        "cancel",
        cancel
    )
)

app.add_handler(
    CallbackQueryHandler(
        button
    )
)

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        message_handler
    )
)

app.add_error_handler(
    error_handler
)

print("Webhook indul 🚀")

app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_url=WEBHOOK_URL
)
