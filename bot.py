import time
import json
import html
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------
# CONFIG
# ---------------------------------------
BOT_TOKEN = "Bot Token"
CHANNEL_ID = "channel ID"
OWNER_ID = "admin ID"
RATE_LIMIT_SECONDS = 15

COMMENTS_FILE = "comments.json"
BOT_USERNAME = "dduconfession2bot"

PROFANITY_WORDS = {"badword1", "badword2"}

_last_submission = {}
_confession_counter = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------
# COMMENTS STORAGE
# ---------------------------------------
def load_comments():
    try:
        with open(COMMENTS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_comments(data):
    with open(COMMENTS_FILE, "w") as f:
        json.dump(data, f, indent=4)

comments_db = load_comments()

# ---------------------------------------
# MAIN MENU
# ---------------------------------------
def main_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ Send Confession", callback_data="send_confession")],
            [InlineKeyboardButton("💬 Comment System", callback_data="comment_info")],
            [InlineKeyboardButton("📞 Contact Admin", callback_data="contact")],
            [InlineKeyboardButton("🛡 Privacy & Rules", callback_data="rules")],
            [InlineKeyboardButton("ℹ️ About", callback_data="about")],
            [InlineKeyboardButton("📢 Channel", url="https://t.me/dduconfessions2")],
        ]
    )

# ---------------------------------------
# HELPERS
# ---------------------------------------
def is_allowed_submission(uid):
    now = time.time()
    last = _last_submission.get(uid)
    if last and now - last < RATE_LIMIT_SECONDS:
        return False, f"⏳ Wait {int(RATE_LIMIT_SECONDS - (now - last))} seconds."
    return True, ""

def record_submission(uid):
    _last_submission[uid] = time.time()

def contains_profanity(text):
    return any(w in text.lower() for w in PROFANITY_WORDS)

def format_confession(text, kind):
    global _confession_counter
    _confession_counter += 1
    safe = html.escape(text)
    return (
        f"🔒 <b>Anonymous Confession #{_confession_counter}</b>\n"
        f"<b>Type:</b> {kind}\n\n{safe}"
    )

# ---------------------------------------
# START — HANDLE DEEP LINKS
# ---------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle ?start=comment_XX
    if context.args:
        arg = context.args[0]

        # COMMENT deep link
        if arg.startswith("comment_"):
            confession_id = arg.split("_")[1]
            context.user_data["comment_for"] = confession_id

            await update.message.reply_text(
                f"✍️ Write your comment for confession #{confession_id}:"
            )
            return

        # VIEW COMMENTS deep link
        if arg.startswith("view_"):
            confession_id = arg.split("_")[1]

            if confession_id not in comments_db or len(comments_db[confession_id]) == 0:
                await update.message.reply_text("📭 No comments yet.")
            else:
                msgs = "\n\n".join(
                    [f"• {html.escape(c)}" for c in comments_db[confession_id]]
                )

                await update.message.reply_text(
                    f"💬 <b>Comments for Confession #{confession_id}</b>\n\n{msgs}",
                    parse_mode=ParseMode.HTML,
                )
            return

    # Normal /start
    banner = (
        "🌟 <b>Welcome to DDU Confession Bot</b>\n\n"
        "💬 Submit confessions anonymously\n"
        "🔒 No tracking • No logs\n\n"
        "📢 Channel: @dduconfessions2"
    )
    await update.message.reply_text(banner, parse_mode=ParseMode.HTML, reply_markup=main_menu())

# ---------------------------------------
# CALLBACK HANDLER (Menu Buttons)
# ---------------------------------------
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "send_confession":
        await q.message.reply_text("✏️ Send your confession:")

    elif data == "comment_info":
        await q.message.reply_text(
            "💬 How Comment System Works:\n\n"
            "• Tap 'Comment' under any confession → bot opens\n"
            "• Write your comment inside bot\n"
            "• Tap 'View Comments' → bot opens and shows all comments",
            reply_markup=main_menu(),
        )

    elif data == "contact":
        context.user_data["contact_mode"] = True
        await q.message.reply_text("📩 Send your message to admin:")

    elif data == "rules":
        await q.message.reply_text(
            "🛡 Privacy Rules:\n"
            "• Fully anonymous\n"
            "• No IDs stored\n"
            "• No logs\n"
            "• No harassment allowed",
            reply_markup=main_menu(),
        )

    elif data == "about":
        await q.message.reply_text("🤖 DDU Confession Bot\nBuilt for privacy.", reply_markup=main_menu())

# ---------------------------------------
# HANDLE COMMENT MESSAGE
# ---------------------------------------
async def handle_comment_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "comment_for" not in context.user_data:
        return False

    confess_id = context.user_data["comment_for"]
    text = update.message.text

    if confess_id not in comments_db:
        comments_db[confess_id] = []

    comments_db[confess_id].append(text)
    save_comments(comments_db)

    await update.message.reply_text("✅ Comment posted anonymously!")

    context.user_data.pop("comment_for")
    return True

# ---------------------------------------
# CONTACT ADMIN
# ---------------------------------------
async def handle_contact_admin(update, context):
    if not context.user_data.get("contact_mode"):
        return False

    text = update.message.text

    await context.bot.send_message(
        OWNER_ID,
        f"📩 <b>New Admin Message</b>\n\n{html.escape(text)}",
        parse_mode=ParseMode.HTML,
    )

    await update.message.reply_text("📤 Sent to admin!")
    context.user_data["contact_mode"] = False
    return True

# ---------------------------------------
# CONFESSION HANDLER
# ---------------------------------------
async def handle_text(update, context):
    if await handle_contact_admin(update, context):
        return
    if await handle_comment_message(update, context):
        return

    text = update.message.text
    uid = update.message.from_user.id

    allowed, msg = is_allowed_submission(uid)
    if not allowed:
        await update.message.reply_text(msg)
        return

    if contains_profanity(text):
        await update.message.reply_text("❌ Contains banned words")
        return

    confession_text = format_confession(text, "Text")

    # BUTTONS: COMMENT + VIEW COMMENTS
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💬 Comment",
                url=f"https://t.me/{BOT_USERNAME}?start=comment_{_confession_counter}"
            ),
            InlineKeyboardButton(
                "👀 View Comments",
                url=f"https://t.me/{BOT_USERNAME}?start=view_{_confession_counter}"
            ),
        ]
    ])

    await context.bot.send_message(
        CHANNEL_ID,
        confession_text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

    record_submission(uid)
    await update.message.reply_text("✅ Posted anonymously!")

# ---------------------------------------
# MEDIA HANDLERS (Photo, Voice, Sticker)
# ---------------------------------------

async def handle_photo(update, context):
    if await handle_contact_admin(update, context):
        return

    uid = update.message.from_user.id
    allowed, msg = is_allowed_submission(uid)
    if not allowed:
        await update.message.reply_text(msg)
        return

    caption = update.message.caption or "(photo)"
    text = format_confession(caption, "Image")
    file_id = update.message.photo[-1].file_id

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Comment", url=f"https://t.me/{BOT_USERNAME}?start=comment_{_confession_counter}"),
            InlineKeyboardButton("👀 View Comments", url=f"https://t.me/{BOT_USERNAME}?start=view_{_confession_counter}")
        ]
    ])

    await context.bot.send_photo(
        CHANNEL_ID,
        file_id,
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

    record_submission(uid)
    await update.message.reply_text("📷 Posted anonymously!")

async def handle_voice(update, context):
    if await handle_contact_admin(update, context):
        return

    uid = update.message.from_user.id
    allowed, msg = is_allowed_submission(uid)
    if not allowed:
        await update.message.reply_text(msg)
        return

    file = update.message.voice.file_id
    text = format_confession("(voice message)", "Voice")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Comment", url=f"https://t.me/{BOT_USERNAME}?start=comment_{_confession_counter}"),
            InlineKeyboardButton("👀 View Comments", url=f"https://t.me/{BOT_USERNAME}?start=view_{_confession_counter}")
        ]
    ])

    await context.bot.send_message(
        CHANNEL_ID,
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await context.bot.send_voice(CHANNEL_ID, file)

    record_submission(uid)
    await update.message.reply_text("🎤 Posted anonymously!")

async def handle_sticker(update, context):
    if await handle_contact_admin(update, context):
        return

    uid = update.message.from_user.id
    allowed, msg = is_allowed_submission(uid)
    if not allowed:
        await update.message.reply_text(msg)
        return

    sticker = update.message.sticker.file_id
    text = format_confession("(sticker)", "Sticker")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Comment", url=f"https://t.me/{BOT_USERNAME}?start=comment_{_confession_counter}"),
            InlineKeyboardButton("👀 View Comments", url=f"https://t.me/{BOT_USERNAME}?start=view_{_confession_counter}")
        ]
    ])

    await context.bot.send_message(
        CHANNEL_ID,
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await context.bot.send_sticker(CHANNEL_ID, sticker)

    record_submission(uid)
    await update.message.reply_text("👍 Sticker posted anonymously!")

# ---------------------------------------
# MAIN
# ---------------------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()





