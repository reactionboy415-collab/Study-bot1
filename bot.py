import telebot
import requests
import time
import os
from threading import Thread
from flask import Flask

# HEALTH SERVER
app = Flask(__name__)
@app.route('/')
def health():
    return "SnapStudy AI Bot Live", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# CONFIG
BOT_TOKEN = "YOUR_BOT_TOKEN"
API = "https://study-bot-phi.vercel.app/fetch"
VIDEO_API = "https://study-bot-phi.vercel.app/video-status"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(
        m,
        "📚 *SnapStudy AI*\n\nSend any topic and I will generate:\n• Research visuals\n• Explanation\n• 🎬 Final video",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: True)
def handle(m):
    chat = m.chat.id
    topic = m.text

    bot.send_message(chat, f"🔍 Researching *{topic}*...", parse_mode="Markdown")

    r = requests.get(API, params={"topic": topic}, timeout=45).json()
    cid = r.get("conversation_id")
    scenes = r.get("scenes", [])

    # SEND SCENES (TEXT + IMAGES)
    for sc in scenes:
        title = sc.get("scene_title", "Insight")
        text = sc.get("scene_text", "")
        img = (sc.get("scene_image") or [None])[0]
        cap = f"📖 *{title}*\n\n{text}"

        if img:
            bot.send_photo(chat, img, caption=cap, parse_mode="Markdown")
        else:
            bot.send_message(chat, cap, parse_mode="Markdown")

        time.sleep(1.5)

    # VIDEO GENERATION NOTICE
    status_msg = bot.send_message(chat, "🎬 *Generating video…*\nPlease wait ⏳", parse_mode="Markdown")

    # POLL VIDEO
    for _ in range(40):  # ~4–5 min
        v = requests.get(VIDEO_API, params={"cid": cid}, timeout=20).json()

        if v.get("status") == "success" and v.get("video"):
            bot.delete_message(chat, status_msg.message_id)
            bot.send_video(
                chat,
                v["video"],
                caption=f"🎥 *{v.get('title','Your Video')}*",
                parse_mode="Markdown"
            )
            return

        time.sleep(8)

    bot.edit_message_text(
        "❌ Video generation failed. Try again later.",
        chat,
        status_msg.message_id
    )

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
