import os
import random
import asyncio
from typing import Any, Callable, Optional

import psycopg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, TimedOut
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# ================= CONFIG =================

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
DEFAULT_SITE = os.getenv("DEFAULT_SITE", "AbetHunters")
PORT = int(os.environ.get("PORT", 8080))

CHANNEL_ID = -1003870607173


def parse_admin_ids() -> set[int]:
    raw = os.getenv("ADMIN_IDS", "")
    result: set[int] = set()

    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.add(int(item))
        except ValueError:
            print(f"ADMIN_IDS HIBA: '{item}' nem szám.")

    return result


ADMIN_IDS = parse_admin_ids()


# ================= MEMORY STORAGE =================

# A giveaway működését továbbra is a memória kezeli.
# A PostgreSQL csak a nyerteseket naplózza.
giveaways: dict[str, dict[str, Any]] = {}
LAST_GIVEAWAY: Optional[str] = None
user_states: dict[int, dict[str, Any]] = {}


# ================= GENERAL HELPERS =================

def escape_html(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def is_admin(user_id: Optional[int]) -> bool:
    return user_id is not None and user_id in ADMIN_IDS


async def safe_answer(query, text: Optional[str] = None, show_alert: bool = False) -> None:
    try:
        await query.answer(text=text, show_alert=show_alert)
    except (BadRequest, TimedOut) as exc:
        print("CALLBACK ANSWER SKIPPED:", type(exc).__name__, repr(exc))
    except Exception as exc:
        print("CALLBACK ANSWER ERROR:", type(exc).__name__, repr(exc))


def participant_name(participant: dict[str, Any]) -> str:
    return participant.get("name") or participant.get("username") or "Ismeretlen felhasználó"


def participant_mention(uid: int, participant: dict[str, Any]) -> str:
    return (
        f"<a href='tg://user?id={uid}'>"
        f"{escape_html(participant_name(participant))}"
        f"</a>"
    )


# ================= DATABASE =================

def init_database_sync() -> None:
    if not DATABASE_URL:
        print("DATABASE WARNING: DATABASE_URL nincs beállítva. A giveaway működik, de a nyertesek nem mentődnek.")
        return

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS winners (
                    id BIGSERIAL PRIMARY KEY,
                    giveaway_id TEXT NOT NULL,
                    channel_id BIGINT,
                    message_id BIGINT,
                    site_name TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'Telegram',
                    prize TEXT NOT NULL,
                    winner_user_id BIGINT,
                    winner_name TEXT NOT NULL,
                    winner_username TEXT,
                    draw_type TEXT NOT NULL,
                    reroll_number INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    drawn_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reviewed_by BIGINT,
                    reviewed_at TIMESTAMPTZ
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_winners_status ON winners(status)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_winners_giveaway_id ON winners(giveaway_id)"
            )

    print("DATABASE: winners tábla készen áll.")


def insert_original_winners_sync(
    gid: str,
    giveaway: dict[str, Any],
    winner_ids: list[int],
) -> None:
    if not DATABASE_URL:
        return

    rows = []
    for uid in winner_ids:
        participant = giveaway["participants"][uid]
        rows.append(
            (
                gid,
                CHANNEL_ID,
                giveaway.get("message_id"),
                giveaway.get("site", DEFAULT_SITE),
                "Telegram",
                giveaway["prize"],
                uid,
                participant_name(participant),
                participant.get("username"),
                "original",
                0,
                "pending",
            )
        )

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO winners (
                    giveaway_id,
                    channel_id,
                    message_id,
                    site_name,
                    platform,
                    prize,
                    winner_user_id,
                    winner_name,
                    winner_username,
                    draw_type,
                    reroll_number,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()


def insert_reroll_winners_sync(
    gid: str,
    giveaway: dict[str, Any],
    winner_ids: list[int],
) -> int:
    if not DATABASE_URL:
        return 0

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(MAX(reroll_number), 0)
                FROM winners
                WHERE giveaway_id = %s
                """,
                (gid,),
            )
            current_max = int(cur.fetchone()[0])
            reroll_number = current_max + 1

            # A legutóbbi, még pending nyertesek közül annyit jelölünk rerollednak,
            # ahány új nyertest húztunk. A régi rekordok ettől még megmaradnak.
            cur.execute(
                """
                UPDATE winners
                SET status = 'rerolled',
                    reviewed_at = NOW()
                WHERE id IN (
                    SELECT id
                    FROM winners
                    WHERE giveaway_id = %s
                      AND status = 'pending'
                    ORDER BY id DESC
                    LIMIT %s
                )
                """,
                (gid, len(winner_ids)),
            )

            rows = []
            for uid in winner_ids:
                participant = giveaway["participants"][uid]
                rows.append(
                    (
                        gid,
                        CHANNEL_ID,
                        giveaway.get("message_id"),
                        giveaway.get("site", DEFAULT_SITE),
                        "Telegram",
                        giveaway["prize"],
                        uid,
                        participant_name(participant),
                        participant.get("username"),
                        "reroll",
                        reroll_number,
                        "pending",
                    )
                )

            cur.executemany(
                """
                INSERT INTO winners (
                    giveaway_id,
                    channel_id,
                    message_id,
                    site_name,
                    platform,
                    prize,
                    winner_user_id,
                    winner_name,
                    winner_username,
                    draw_type,
                    reroll_number,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )

        conn.commit()

    return reroll_number


def fetch_pending_winners_sync(limit: int = 20) -> list[tuple[Any, ...]]:
    if not DATABASE_URL:
        return []

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    giveaway_id,
                    site_name,
                    prize,
                    winner_name,
                    winner_username,
                    winner_user_id,
                    draw_type,
                    reroll_number,
                    drawn_at
                FROM winners
                WHERE status = 'pending'
                ORDER BY id ASC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()


def fetch_winner_history_sync(limit: int = 30) -> list[tuple[Any, ...]]:
    if not DATABASE_URL:
        return []

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    giveaway_id,
                    site_name,
                    prize,
                    winner_name,
                    winner_username,
                    draw_type,
                    reroll_number,
                    status,
                    drawn_at
                FROM winners
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()


def review_winner_sync(winner_id: int, status: str, admin_id: int) -> bool:
    if not DATABASE_URL:
        return False

    if status not in {"approved", "rejected"}:
        return False

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE winners
                SET status = %s,
                    reviewed_by = %s,
                    reviewed_at = NOW()
                WHERE id = %s
                  AND status = 'pending'
                """,
                (status, admin_id, winner_id),
            )
            changed = cur.rowcount == 1
        conn.commit()

    return changed


async def db_safe_call(
    label: str,
    func: Callable[..., Any],
    *args: Any,
    default: Any = None,
) -> Any:
    if not DATABASE_URL:
        return default

    try:
        return await asyncio.to_thread(func, *args)
    except Exception as exc:
        print(f"DATABASE {label} ERROR:", type(exc).__name__, repr(exc))
        return default


# ================= PANEL =================

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🎁 Giveaway indítása", callback_data="panel_create")]]
    )

    await update.message.reply_text("⚙️ Giveaway panel:", reply_markup=keyboard)


# ================= CREATE COMMAND =================

async def create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global LAST_GIVEAWAY

    try:
        raw = " ".join(context.args).strip()

        if not raw:
            await update.message.reply_text(
                "❗ Használat:\n"
                "/create <nyertesek> <nyeremény> <percek> | <site>\n\n"
                "Példa:\n"
                "/create 2 50 USDT 10 | Vodka\n\n"
                f"A | site rész elhagyható. Alapértelmezett site: {DEFAULT_SITE}"
            )
            return

        if "|" in raw:
            giveaway_part, site = raw.rsplit("|", 1)
            site = site.strip()
        else:
            giveaway_part = raw
            site = DEFAULT_SITE

        args = giveaway_part.split()

        if len(args) < 3:
            raise ValueError

        winners = int(args[0])
        minutes = int(args[-1])
        prize = " ".join(args[1:-1]).strip()

        if winners <= 0 or minutes <= 0 or not prize or not site:
            raise ValueError

        gid = f"{update.message.message_id}_{update.effective_user.id}"
        while gid in giveaways:
            gid = f"{gid}_{random.randint(1000, 9999)}"

        LAST_GIVEAWAY = gid

        giveaways[gid] = {
            "participants": {},
            "winners": winners,
            "prize": prize,
            "site": site,
            "remaining": minutes,
            "message_id": None,
            "active": True,
        }

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎉 Részt veszek (0)", callback_data=f"join_{gid}")]]
        )

        caption = f"""🎉 GIVEAWAY!

🎁 {prize}
🌐 Site: {site}
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
                pool_timeout=30,
            )

        giveaways[gid]["message_id"] = msg.message_id
        context.application.create_task(timer(context, gid))

        await update.message.reply_text("✅ A giveaway sikeresen elindult!")

    except FileNotFoundError:
        await update.message.reply_text("❌ Az image.jpg fájl nem található.")
    except ValueError:
        await update.message.reply_text(
            "❗ Hibás formátum.\n\n"
            "/create <nyertesek> <nyeremény> <percek> | <site>\n\n"
            "Példa: /create 2 50 USDT 10 | Vodka"
        )
    except Exception as exc:
        print("CREATE ERROR:", type(exc).__name__, repr(exc))
        await update.message.reply_text(
            f"❌ Nem sikerült elindítani a giveawayt.\n\n"
            f"Hiba: {type(exc).__name__}: {exc}"
        )


# ================= CALLBACK BUTTONS =================

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global LAST_GIVEAWAY

    query = update.callback_query
    if not query:
        return

    user_id = query.from_user.id
    callback_data = query.data or ""

    # ================= WINNER REVIEW =================

    if callback_data.startswith("winner_approve_") or callback_data.startswith("winner_reject_"):
        if not is_admin(user_id):
            await safe_answer(query, "❌ Nincs jogosultságod ehhez.", show_alert=True)
            return

        try:
            winner_id = int(callback_data.rsplit("_", 1)[1])
        except (ValueError, IndexError):
            await safe_answer(query, "❌ Hibás nyertesazonosító.", show_alert=True)
            return

        status = "approved" if callback_data.startswith("winner_approve_") else "rejected"
        changed = await db_safe_call(
            "REVIEW",
            review_winner_sync,
            winner_id,
            status,
            user_id,
            default=False,
        )

        if not changed:
            await safe_answer(
                query,
                "⚠️ Ezt a nyertest már feldolgozták, vagy adatbázishiba történt.",
                show_alert=True,
            )
            return

        label = "✅ ELFOGADVA" if status == "approved" else "❌ ELUTASÍTVA"
        await safe_answer(query, label)

        try:
            old_text = query.message.text or "Nyertes"
            await query.edit_message_text(f"{old_text}\n\n{label}")
        except Exception as exc:
            print("REVIEW MESSAGE EDIT ERROR:", type(exc).__name__, repr(exc))
        return

    # ================= PANEL START =================

    if callback_data == "panel_create":
        await safe_answer(query)
        user_states[user_id] = {"step": "site"}
        await query.message.reply_text(
            f"🌐 Írd be a site nevét:\n\nPélda: Vodka\nAlapértelmezett: {DEFAULT_SITE}"
        )
        return

    # ================= TIME SELECT =================

    if callback_data.startswith("time_"):
        state = user_states.get(user_id)
        if not state:
            await safe_answer(
                query,
                "❗ A panel lejárt. Indítsd újra a /panel paranccsal.",
                show_alert=True,
            )
            return

        try:
            minutes = int(callback_data.split("_", 1)[1])
        except (ValueError, IndexError):
            await safe_answer(query, "❌ Hibás időbeállítás.", show_alert=True)
            return

        await safe_answer(query)
        state["minutes"] = minutes
        state["step"] = "confirm"

        preview = f"""👀 ELŐNÉZET:

🎁 {state['prize']}
🌐 Site: {state['site']}
👥 Nyertesek: {state['winners']}
⏳ {minutes} perc

🔗 https://abethunters.com/

Elindítod?"""

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Igen", callback_data="confirm_yes")],
                [InlineKeyboardButton("❌ Nem", callback_data="confirm_no")],
            ]
        )

        await query.message.reply_text(preview, reply_markup=keyboard)
        return

    # ================= CONFIRM YES =================

    if callback_data == "confirm_yes":
        state = user_states.get(user_id)
        if not state:
            await safe_answer(
                query,
                "❗ A panel lejárt. Indítsd újra a /panel paranccsal.",
                show_alert=True,
            )
            return

        winners = state["winners"]
        prize = state["prize"]
        site = state["site"]
        minutes = state["minutes"]

        await safe_answer(query, "⏳ Giveaway indítása...")

        gid = f"{query.message.message_id}_{user_id}"
        while gid in giveaways:
            gid = f"{gid}_{random.randint(1000, 9999)}"

        LAST_GIVEAWAY = gid
        giveaways[gid] = {
            "participants": {},
            "winners": winners,
            "prize": prize,
            "site": site,
            "remaining": minutes,
            "message_id": None,
            "active": True,
        }

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎉 Részt veszek (0)", callback_data=f"join_{gid}")]]
        )

        caption = f"""🎉 GIVEAWAY!

🎁 {prize}
🌐 Site: {site}
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
                    pool_timeout=30,
                )

            giveaways[gid]["message_id"] = msg.message_id
            user_states.pop(user_id, None)
            context.application.create_task(timer(context, gid))
            await query.message.reply_text("✅ A giveaway sikeresen elindult!")

        except FileNotFoundError:
            giveaways.pop(gid, None)
            await query.message.reply_text("❌ Az image.jpg fájl nem található.")
        except Exception as exc:
            giveaways.pop(gid, None)
            print("PANEL CREATE ERROR:", type(exc).__name__, repr(exc))
            await query.message.reply_text(
                f"❌ Nem sikerült elindítani a giveawayt.\n\n"
                f"Hiba: {type(exc).__name__}: {exc}"
            )
        return

    # ================= CONFIRM NO =================

    if callback_data == "confirm_no":
        await safe_answer(query)
        user_states.pop(user_id, None)
        await query.message.reply_text("❌ Giveaway létrehozása megszakítva.")
        return

    # ================= JOIN =================

    if callback_data.startswith("join_"):
        gid = callback_data.split("_", 1)[1]
        giveaway = giveaways.get(gid)

        if not giveaway or not giveaway["active"]:
            await safe_answer(query, "❌ Ez a giveaway már véget ért.", show_alert=True)
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
            await safe_answer(
                query,
                f"❗ Már csatlakoztál ehhez a giveawayhez!\n\n"
                f"Jelenlegi résztvevők: {count}",
                show_alert=True,
            )
            return

        giveaway["participants"][uid] = {
            "name": name,
            "username": query.from_user.username,
        }
        count = len(giveaway["participants"])

        await safe_answer(
            query,
            f"✅ Sikeresen csatlakoztál a giveawayhez!\n\n"
            f"Jelenlegi résztvevők: {count}",
            show_alert=True,
        )

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"🎉 Részt veszek ({count})", callback_data=f"join_{gid}")]]
        )

        try:
            await context.bot.edit_message_reply_markup(
                chat_id=CHANNEL_ID,
                message_id=giveaway["message_id"],
                reply_markup=keyboard,
                connect_timeout=30,
                read_timeout=30,
                write_timeout=30,
                pool_timeout=30,
            )
        except Exception as exc:
            print("JOIN BUTTON UPDATE ERROR:", type(exc).__name__, repr(exc))
        return

    await safe_answer(query, "❌ Ismeretlen művelet.", show_alert=True)


# ================= PANEL MESSAGE INPUT =================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = update.message.from_user.id
    state = user_states.get(user_id)
    if not state:
        return

    step = state.get("step")
    text = update.message.text.strip()

    if step == "site":
        if not text:
            await update.message.reply_text("❗ A site neve nem lehet üres.")
            return

        state["site"] = text
        state["step"] = "prize"
        await update.message.reply_text("🎁 Írd be a nyereményt:")
        return

    if step == "prize":
        if not text:
            await update.message.reply_text("❗ A nyeremény nem lehet üres.")
            return

        state["prize"] = text
        state["step"] = "winners"
        await update.message.reply_text("👥 Hány nyertes legyen?")
        return

    if step == "winners":
        try:
            winners = int(text)
            if winners <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❗ Pozitív egész számot írj!\n\nPélda: 2"
            )
            return

        state["winners"] = winners
        state["step"] = "time"

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("1 perc", callback_data="time_1")],
                [InlineKeyboardButton("5 perc", callback_data="time_5")],
                [InlineKeyboardButton("10 perc", callback_data="time_10")],
                [InlineKeyboardButton("30 perc", callback_data="time_30")],
                [InlineKeyboardButton("60 perc", callback_data="time_60")],
            ]
        )

        await update.message.reply_text("⏳ Válassz időt:", reply_markup=keyboard)


# ================= TIMER =================

async def timer(context: ContextTypes.DEFAULT_TYPE, gid: str) -> None:
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
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"🎉 Részt veszek ({count})", callback_data=f"join_{gid}")]]
        )

        caption = f"""🎉 GIVEAWAY!

🎁 {giveaway['prize']}
🌐 Site: {giveaway['site']}
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
                pool_timeout=30,
            )
        except Exception as exc:
            print("TIMER EDIT ERROR:", type(exc).__name__, repr(exc))

    await end_giveaway(context, gid)


# ================= END GIVEAWAY =================

async def end_giveaway(context: ContextTypes.DEFAULT_TYPE, gid: str) -> None:
    giveaway = giveaways.get(gid)
    if not giveaway or not giveaway["active"]:
        return

    giveaway["active"] = False
    count = len(giveaway["participants"])

    ended_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🔒 Giveaway véget ért ({count})", callback_data=f"join_{gid}")]]
    )

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID,
            message_id=giveaway["message_id"],
            reply_markup=ended_keyboard,
            connect_timeout=30,
            read_timeout=30,
            write_timeout=30,
            pool_timeout=30,
        )
    except Exception as exc:
        print("END BUTTON ERROR:", type(exc).__name__, repr(exc))

    if not giveaway["participants"]:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"""❌ GIVEAWAY VÉGE!

🎁 {giveaway['prize']}
🌐 Site: {giveaway['site']}

Nem volt egyetlen résztvevő sem.""",
        )
        return

    users = list(giveaway["participants"].keys())
    winner_count = min(len(users), giveaway["winners"])
    winners = random.sample(users, winner_count)
    giveaway["last_winners"] = winners

    winner_text = "\n".join(
        [f"• {participant_mention(uid, giveaway['participants'][uid])}" for uid in winners]
    )

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"""🏆 GIVEAWAY VÉGE!

🎁 {escape_html(giveaway['prize'])}
🌐 Site: {escape_html(giveaway['site'])}
👥 Résztvevők: {count}

🎉 Nyertesek:
{winner_text}""",
        parse_mode="HTML",
    )

    # Az adatbázis mentés külön fut. Hiba esetén a giveaway már így is rendben lezárult.
    await db_safe_call(
        "ORIGINAL WINNERS SAVE",
        insert_original_winners_sync,
        gid,
        giveaway,
        winners,
    )


# ================= REROLL =================

async def reroll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global LAST_GIVEAWAY

    if not LAST_GIVEAWAY:
        await update.message.reply_text("❌ Még nem volt giveaway.")
        return

    giveaway = giveaways.get(LAST_GIVEAWAY)
    if not giveaway:
        await update.message.reply_text("❌ A giveaway nem található.")
        return

    if giveaway["active"]:
        await update.message.reply_text("❌ Aktív giveawayt még ne rerollolj.")
        return

    if not giveaway["participants"]:
        await update.message.reply_text("❌ A giveawaynek nincs résztvevője.")
        return

    users = list(giveaway["participants"].keys())

    try:
        count = int(context.args[0]) if context.args else giveaway["winners"]
        if count <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ Használat:\n/reroll\nvagy\n/reroll 2")
        return

    count = min(count, len(users))
    new_winners = random.sample(users, count)
    giveaway["last_winners"] = new_winners

    winner_text = "\n".join(
        [f"• {participant_mention(uid, giveaway['participants'][uid])}" for uid in new_winners]
    )

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"""🔄 REROLL!

🎁 {escape_html(giveaway['prize'])}
🌐 Site: {escape_html(giveaway['site'])}

🎉 ÚJ NYERTESEK:
{winner_text}""",
        parse_mode="HTML",
    )

    reroll_number = await db_safe_call(
        "REROLL WINNERS SAVE",
        insert_reroll_winners_sync,
        LAST_GIVEAWAY,
        giveaway,
        new_winners,
        default=0,
    )

    suffix = f" (reroll #{reroll_number})" if reroll_number else ""
    await update.message.reply_text(
        f"✅ Reroll elküldve. Új nyertesek: {count}{suffix}"
    )


# ================= PENDING / HISTORY =================

async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None

    if not is_admin(user_id):
        await update.message.reply_text(
            "❌ Nincs jogosultságod.\n\n"
            "Írd be a Railway Variables részébe:\n"
            "ADMIN_IDS=saját_telegram_id\n\n"
            "A saját ID-dat a /myid paranccsal látod."
        )
        return

    rows = await db_safe_call(
        "FETCH PENDING",
        fetch_pending_winners_sync,
        20,
        default=[],
    )

    if not rows:
        await update.message.reply_text("✅ Nincs függőben lévő nyertes.")
        return

    await update.message.reply_text(f"⏳ Függőben lévő nyertesek: {len(rows)}")

    for row in rows:
        (
            winner_id,
            gid,
            site,
            prize,
            name,
            username,
            telegram_id,
            draw_type,
            reroll_number,
            drawn_at,
        ) = row

        draw_label = "Eredeti sorsolás" if draw_type == "original" else f"Reroll #{reroll_number}"
        username_text = f"@{username}" if username else "nincs username"

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Elfogadás",
                        callback_data=f"winner_approve_{winner_id}",
                    ),
                    InlineKeyboardButton(
                        "❌ Elutasítás",
                        callback_data=f"winner_reject_{winner_id}",
                    ),
                ]
            ]
        )

        await update.message.reply_text(
            f"🏆 {name}\n"
            f"Username: {username_text}\n"
            f"Telegram ID: {telegram_id}\n\n"
            f"🌐 Site: {site}\n"
            f"🎁 Nyeremény: {prize}\n"
            f"🎲 Típus: {draw_label}\n"
            f"🆔 Giveaway: {gid}\n"
            f"📅 Dátum: {drawn_at:%Y-%m-%d %H:%M}\n\n"
            f"Állapot: ⏳ pending",
            reply_markup=keyboard,
        )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None

    if not is_admin(user_id):
        await update.message.reply_text("❌ Nincs jogosultságod ehhez.")
        return

    rows = await db_safe_call(
        "FETCH HISTORY",
        fetch_winner_history_sync,
        30,
        default=[],
    )

    if not rows:
        await update.message.reply_text("📭 Még nincs elmentett nyertes.")
        return

    status_labels = {
        "pending": "⏳ pending",
        "approved": "✅ approved",
        "rejected": "❌ rejected",
        "rerolled": "🔄 rerolled",
    }

    lines = ["🏆 UTOLSÓ NYERTESEK\n"]
    for row in rows:
        (
            winner_id,
            gid,
            site,
            prize,
            name,
            username,
            draw_type,
            reroll_number,
            status,
            drawn_at,
        ) = row

        draw_label = "original" if draw_type == "original" else f"reroll #{reroll_number}"
        username_text = f" (@{username})" if username else ""
        lines.append(
            f"#{winner_id} | {name}{username_text}\n"
            f"{site} | {prize} | {draw_label} | {status_labels.get(status, status)}\n"
            f"Giveaway: {gid} | {drawn_at:%Y-%m-%d %H:%M}\n"
        )

    text = "\n".join(lines)

    # Telegram üzenethossz miatt darabolás.
    for start in range(0, len(text), 3900):
        await update.message.reply_text(text[start : start + 3900])


# ================= CANCEL =================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global LAST_GIVEAWAY

    if not LAST_GIVEAWAY:
        await update.message.reply_text("❌ Nincs aktív giveaway.")
        return

    giveaway = giveaways.get(LAST_GIVEAWAY)
    if not giveaway:
        await update.message.reply_text("❌ A giveaway nem található.")
        return

    if not giveaway["active"]:
        await update.message.reply_text("❌ Ez a giveaway már véget ért.")
        return

    giveaway["active"] = False

    try:
        await context.bot.delete_message(
            chat_id=CHANNEL_ID,
            message_id=giveaway["message_id"],
            connect_timeout=30,
            read_timeout=30,
            write_timeout=30,
            pool_timeout=30,
        )
        await update.message.reply_text("✅ A giveaway leállítva és törölve lett.")
    except Exception as exc:
        print("CANCEL ERROR:", type(exc).__name__, repr(exc))
        await update.message.reply_text(
            "⚠️ A giveaway leállt, de az üzenetet nem sikerült törölni."
        )


# ================= BASIC COMMANDS =================

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    await update.message.reply_text(f"A Telegram ID-d: {user_id}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        """Bot fut 🚀

Parancsok:

/panel – Giveaway létrehozása panellel
/create – Giveaway létrehozása paranccsal
/reroll – Új nyertes húzása
/cancel – Giveaway megszakítása
/pending – Jóváhagyásra váró nyertesek
/history – Nyerteselőzmények
/myid – Saját Telegram ID"""
    )


# ================= ERROR HANDLER =================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("BOT ERROR:", type(context.error).__name__, repr(context.error))


# ================= MAIN =================

if not TOKEN:
    raise RuntimeError("A TOKEN környezeti változó nincs beállítva.")

if not WEBHOOK_URL:
    raise RuntimeError("A WEBHOOK_URL környezeti változó nincs beállítva.")

try:
    init_database_sync()
except Exception as exc:
    # Fontos: adatbázishiba esetén is elindul a giveaway bot.
    print("DATABASE INIT ERROR:", type(exc).__name__, repr(exc))

app = (
    ApplicationBuilder()
    .token(TOKEN)
    .connect_timeout(30)
    .read_timeout(30)
    .write_timeout(30)
    .pool_timeout(30)
    .build()
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("panel", panel))
app.add_handler(CommandHandler("create", create))
app.add_handler(CommandHandler("reroll", reroll))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(CommandHandler("pending", pending))
app.add_handler(CommandHandler("history", history))
app.add_handler(CommandHandler("myid", myid))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
app.add_error_handler(error_handler)

print("Webhook indul 🚀")

app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_url=WEBHOOK_URL,
)
