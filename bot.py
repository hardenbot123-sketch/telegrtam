import os
import sqlite3
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

DB_FILE = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photo_cache (
            photo_id TEXT PRIMARY KEY,
            file_id TEXT,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_user_to_db(user_id, username, first_name, last_name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        conn.commit()
    except Exception as e:
        logger.error(f"Error adding user to database: {e}")
    finally:
        conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_user_info(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT username, first_name, last_name FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_admin_ids():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM admins')
    admins = [row[0] for row in cursor.fetchall()]
    conn.close()
    return admins

def add_admin(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (user_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Error adding admin: {e}")
    finally:
        conn.close()

def cache_photo(photo_id, file_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO photo_cache (photo_id, file_id)
            VALUES (?, ?)
        ''', (photo_id, file_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Error caching photo: {e}")
    finally:
        conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the bot! I'm monitoring the channel for photos."
    )

async def channel_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post and update.channel_post.photo:
        photo = update.channel_post.photo[-1]
        cache_photo(photo.file_id, photo.file_id)
        keyboard = [
            [InlineKeyboardButton("Have 👍", callback_data=f"photo_{photo.file_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=update.channel_post.chat_id,
                message_id=update.channel_post.message_id,
                reply_markup=reply_markup
            )
            logger.info(f"Added button to photo in channel {update.channel_post.chat_id}")
        except Exception as e:
            logger.error(f"Error adding button to channel photo: {e}")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or "N/A"
    first_name = query.from_user.first_name or ""
    last_name = query.from_user.last_name or ""
    
    add_user_to_db(user_id, username, first_name, last_name)
    photo_file_id = query.data.replace("photo_", "")
    
    try:
        await context.bot.send_photo(
            chat_id=user_id,
            photo=photo_file_id,
            caption="Here's the photo from the channel!"
        )
    except Exception as e:
        logger.error(f"Error sending photo to user {user_id}: {e}")
    
    admin_ids = get_admin_ids()
    notification = (
        f"📌 New user interaction:\n"
        f"👤 Name: {first_name} {last_name}\n"
        f"📱 Username: @{username}\n"
        f"🆔 User ID: {user_id}"
    )
    
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(chat_id=admin_id, text=notification)
        except Exception as e:
            logger.error(f"Error sending notification to admin {admin_id}: {e}")
    
    await query.edit_message_text(text="✅ Photo sent to your private chat!")

async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.chat.type == "private":
        user_id = update.message.from_user.id
        username = update.message.from_user.username or "N/A"
        first_name = update.message.from_user.first_name or ""
        last_name = update.message.from_user.last_name or ""
        
        admin_ids = get_admin_ids()
        
        if user_id in admin_ids:
            all_users = get_all_users()
            
            if update.message.text:
                for user in all_users:
                    try:
                        await context.bot.send_message(chat_id=user, text=update.message.text)
                    except Exception as e:
                        logger.error(f"Error sending message to user {user}: {e}")
            
            elif update.message.photo:
                photo = update.message.photo[-1]
                for user in all_users:
                    try:
                        await context.bot.send_photo(
                            chat_id=user,
                            photo=photo.file_id,
                            caption=update.message.caption or ""
                        )
                    except Exception as e:
                        logger.error(f"Error sending photo to user {user}: {e}")
            
            elif update.message.video:
                video = update.message.video
                for user in all_users:
                    try:
                        await context.bot.send_video(
                            chat_id=user,
                            video=video.file_id,
                            caption=update.message.caption or ""
                        )
                    except Exception as e:
                        logger.error(f"Error sending video to user {user}: {e}")
            
            elif update.message.document:
                document = update.message.document
                for user in all_users:
                    try:
                        await context.bot.send_document(
                            chat_id=user,
                            document=document.file_id,
                            caption=update.message.caption or ""
                        )
                    except Exception as e:
                        logger.error(f"Error sending document to user {user}: {e}")
            
            await update.message.reply_text("✅ Message broadcasted to all users!")
        
        else:
            admin_ids = get_admin_ids()
            
            if not admin_ids:
                await update.message.reply_text("❌ No admins configured yet.")
                return
            
            user_info = (
                f"📨 Message from user:\n"
                f"👤 Name: {first_name} {last_name}\n"
                f"📱 Username: @{username}\n"
                f"🆔 User ID: {user_id}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
            )
            
            for admin_id in admin_ids:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=user_info)
                    
                    if update.message.text:
                        await context.bot.send_message(chat_id=admin_id, text=update.message.text)
                    elif update.message.photo:
                        photo = update.message.photo[-1]
                        await context.bot.send_photo(
                            chat_id=admin_id,
                            photo=photo.file_id,
                            caption=update.message.caption or ""
                        )
                    elif update.message.video:
                        video = update.message.video
                        await context.bot.send_video(
                            chat_id=admin_id,
                            video=video.file_id,
                            caption=update.message.caption or ""
                        )
                    elif update.message.document:
                        document = update.message.document
                        await context.bot.send_document(
                            chat_id=admin_id,
                            document=document.file_id,
                            caption=update.message.caption or ""
                        )
                except Exception as e:
                    logger.error(f"Error forwarding message to admin {admin_id}: {e}")
            
            await update.message.reply_text("✅ Your message has been sent to admins!")

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    admin_ids = get_admin_ids()
    
    if user_id not in admin_ids and len(admin_ids) > 0:
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return
    
    try:
        new_admin_id = int(context.args[0])
        add_admin(new_admin_id)
        await update.message.reply_text(f"✅ User {new_admin_id} added as admin!")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a valid integer.")

async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    admin_ids = get_admin_ids()
    
    if user_id not in admin_ids:
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    users = get_all_users()
    if not users:
        await update.message.reply_text("No users in database yet.")
        return
    
    message = "📋 Registered Users:\n━━━━━━━━━━━━━━━━━━\n"
    for uid in users:
        user_info = get_user_info(uid)
        if user_info:
            username, first_name, last_name = user_info
            message += f"👤 {first_name} {last_name}\n📱 @{username}\n🆔 {uid}\n\n"
    
    await update.message.reply_text(message)

def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addadmin", add_admin_command))
    application.add_handler(CommandHandler("listusers", list_users_command))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.ALL, user_message))
    application.add_handler(MessageHandler(filters.UPDATE.CHANNEL_POST, channel_photo))
    
    logger.info("Bot started. Polling for updates...")
    application.run_polling(allowed_updates=["message", "callback_query", "channel_post"])

if __name__ == "__main__":
    main()
