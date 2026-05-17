import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = "8759550786:AAE1T-FqhBrd-yhzy6UQa0sk93JiufQznaw"

BOT_USERNAME = "Spooky_stake_bot"

# Only this admin can manage the bot
ADMIN_IDS = [
    8196147769
]

CHANNEL_ID = -1003717278830

DB_NAME = "have_users.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            message_id INTEGER PRIMARY KEY,
            file_id TEXT,
            caption TEXT
        )
    """)

    conn.commit()
    conn.close()


def add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_NAME)

    conn.execute(
        """
        INSERT OR REPLACE INTO users
        (user_id, username, first_name)
        VALUES (?, ?, ?)
        """,
        (user_id, username, first_name)
    )

    conn.commit()
    conn.close()


def save_post(message_id, file_id, caption):
    conn = sqlite3.connect(DB_NAME)

    conn.execute(
        """
        INSERT OR REPLACE INTO posts
        (message_id, file_id, caption)
        VALUES (?, ?, ?)
        """,
        (message_id, file_id, caption)
    )

    conn.commit()
    conn.close()


def get_post(message_id):
    conn = sqlite3.connect(DB_NAME)

    post = conn.execute(
        "SELECT file_id, caption FROM posts WHERE message_id = ?",
        (message_id,)
    ).fetchone()

    conn.close()

    return post


def get_all_users():
    conn = sqlite3.connect(DB_NAME)

    users = conn.execute(
        "SELECT user_id FROM users"
    ).fetchall()

    conn.close()

    return [u[0] for u in users]


# =========================
# CHANNEL POSTS
# =========================

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    post = update.channel_post

    if not post:
        return

    if not post.photo:
        return

    file_id = post.photo[-1].file_id
    caption = post.caption or ""

    save_post(
        post.message_id,
        file_id,
        caption
    )

    deep_link = (
        f"https://t.me/{BOT_USERNAME}"
        f"?start=have_{post.message_id}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Have 👍",
                url=deep_link
            )
        ]
    ])

    await context.bot.edit_message_reply_markup(
        chat_id=post.chat_id,
        message_id=post.message_id,
        reply_markup=keyboard
    )


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if (
        context.args
        and context.args[0].startswith("have_")
    ):

        post_id = int(
            context.args[0].replace("have_", "")
        )

        add_user(
            user.id,
            user.username,
            user.first_name
        )

        post = get_post(post_id)

        if not post:
            await update.message.reply_text(
                "Match not found."
            )
            return

        file_id, caption = post

        await context.bot.send_photo(
            chat_id=user.id,
            photo=file_id,
            caption=(
                f"{caption}\n\n"
                "📌 Match Notification Bot 📌\n\n"
                "1️⃣ Reply to this photo with your bet amount.\n"
                "Example: €10\n\n"
                "2️⃣ To remove your bet, reply:\n"
                "delete bet"
            )
        )

        username = (
            f"@{user.username}"
            if user.username
            else "No username"
        )

        for admin_id in ADMIN_IDS:

            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    "🔥 New Have Click\n\n"
                    f"Name: {user.first_name}\n"
                    f"Username: {username}\n"
                    f"User ID: {user.id}\n"
                    f"Post ID: {post_id}"
                )
            )

    else:
        await update.message.reply_text(
            "Welcome 🙂"
        )


# =========================
# ADMIN BROADCAST
# =========================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id not in ADMIN_IDS:
        return

    users = get_all_users()

    sent = 0
    failed = 0

    for user_id in users:

        try:
            await update.message.copy(
                chat_id=user_id
            )

            sent += 1

        except Exception as e:
            print(e)
            failed += 1

    await update.message.reply_text(
        f"Sent to {sent} users\n"
        f"Failed for {failed}"
    )


# =========================
# USER REPLIES
# =========================

async def user_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if user.id in ADMIN_IDS:
        return

    if not update.message.reply_to_message:
        return

    username = (
        f"@{user.username}"
        if user.username
        else "No username"
    )

    message_text = (
        update.message.text
        if update.message.text
        else "Non-text message"
    )

    for admin_id in ADMIN_IDS:

        await context.bot.send_message(
            chat_id=admin_id,
            text=(
                "📩 New Bet Reply\n\n"
                f"Name: {user.first_name}\n"
                f"Username: {username}\n"
                f"User ID: {user.id}\n\n"
                f"Reply:\n{message_text}"
            )
        )

        await context.bot.forward_message(
            chat_id=admin_id,
            from_chat_id=user.id,
            message_id=update.message.message_id
        )


# =========================
# MAIN
# =========================

def main():

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.Chat(CHANNEL_ID)
            & filters.PHOTO,
            channel_post_handler
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.User(user_id=ADMIN_IDS)
            & ~filters.COMMAND,
            broadcast
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & ~filters.User(user_id=ADMIN_IDS)
            & ~filters.COMMAND,
            user_reply
        )
    )

    print("Bot is running...")

    app.run_polling(
        allowed_updates=[
            "message",
            "channel_post"
        ]
    )


if __name__ == "__main__":
    main()
