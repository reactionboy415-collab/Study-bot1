import telebot
import requests
import time
import os
from threading import Thread
from flask import Flask

# ===============================
# 🔐 BOT CONFIG
# ===============================
BOT_TOKEN = "8264213109:AAGo_Bqe7q_84iUbsz2bvnQbP7iHBJ8MNWQ"
API_BASE = "https://study-bot-phi.vercel.app/fetch"  # <-- apna Vercel backend

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ===============================
# 🌐 HEALTH CHECK (RENDER SAFE)
# ===============================
app = Flask(__name__)

@app.route("/")
def health():
    return "SnapStudy Telegram Bot is Running 🚀", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ===============================
# 🤖 BOT COMMANDS
# ===============================
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "📚 *Welcome to SnapStudy AI*\n\n"
        "Send me *any topic* and I will:\n"
        "• Research it\n"
        "• Show images + explanations\n"
        "• Generate a professional video 🎬\n\n"
        "_Example:_ `Black Hole Formation`"
    )

# ===============================
# 📩 HANDLE USER TOPIC
# ===============================
@bot.message_handler(func=lambda m: True)
def handle_topic(message):
    topic = message.text.strip()
    chat_id = message.chat.id

    status_msg = bot.send_message(
        chat_id,
        f"🔍 *Researching:* `{topic}`\nPlease wait…"
    )

    def process():
        try:
            res = requests.get(
                API_BASE,
                params={"topic": topic},
                timeout=120
            )

            if res.status_code != 200:
                bot.edit_message_text(
                    f"❌ *API Error*\n`HTTP {res.status_code}`",
                    chat_id,
                    status_msg.message_id
                )
                return

            data = res.json()

            # ===============================
            # ❌ ERROR FROM BACKEND
            # ===============================
            if "error" in data:
                bot.edit_message_text(
                    f"❌ *Generation Failed*\n\n"
                    f"*Reason:* `{data['error']}`\n\n"
                    f"`{data.get('message','')}`",
                    chat_id,
                    status_msg.message_id
                )
                return

            scenes = data.get("scenes", [])
            video = data.get("video")

            # ===============================
            # 📸 SEND SCENES FIRST
            # ===============================
            bot.edit_message_text(
                "📖 *Research Complete!*\nSending explanations…",
                chat_id,
                status_msg.message_id
            )

            for sc in scenes:
                title = sc.get("scene_title", "Insight")
                text = sc.get("scene_text", "")
                imgs = sc.get("scene_image", [])

                caption = f"*{title}*\n\n{text}"

                if imgs:
                    bot.send_photo(
                        chat_id,
                        imgs[0],
                        caption=caption[:1024]
                    )
                else:
                    bot.send_message(chat_id, caption)

                time.sleep(1.2)

            # ===============================
            # 🎬 VIDEO GENERATION MESSAGE
            # ===============================
            bot.send_message(
                chat_id,
                "🎬 *Generating video…*\nThis may take a few minutes ⏳"
            )

            # ===============================
            # 🎥 SEND VIDEO
            # ===============================
            if video and video.get("video_url"):
                bot.send_video(
                    chat_id,
                    video["video_url"],
                    caption=f"🎥 *{video.get('title','Generated Video')}*"
                )
            else:
                bot.send_message(
                    chat_id,
                    "⚠️ Video URL missing, but scenes were generated successfully."
                )

        except Exception as e:
            bot.edit_message_text(
                f"⚠️ *Unexpected Error*\n\n`{str(e)}`",
                chat_id,
                status_msg.message_id
            )

    Thread(target=process).start()

# ===============================
# 🚀 START BOT
# ===============================
if __name__ == "__main__":
    print("🌐 Starting health server...")
    Thread(target=run_web).start()

    print("🤖 SnapStudy Bot is LIVE!")
    bot.infinity_polling(skip_pending=True)
