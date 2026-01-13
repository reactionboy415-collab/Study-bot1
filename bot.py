import telebot
import requests
import time
import os
from threading import Thread
from flask import Flask

BOT_TOKEN = "8264213109:AAGo_Bqe7q_84iUbsz2bvnQbP7iHBJ8MNWQ"
API_BASE = "https://study-bot-phi.vercel.app"

bot = telebot.TeleBot(BOT_TOKEN)

# health server
app = Flask(__name__)
@app.route("/")
def health():
    return "Bot alive"

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(m, "📘 Send any topic to generate study video")

@bot.message_handler(func=lambda m: True)
def handle(m):
    topic = m.text
    chat = m.chat.id

    try:
        r = requests.get(
            f"{API_BASE}/fetch",
            params={"topic": topic},
            timeout=40
        )
        data = r.json()

        if "error" in data:
            bot.send_message(chat, f"❌ Error: {data}")
            return

        cid = data["conversation_id"]
        scenes = data.get("scenes", [])

        # send images + text
        for s in scenes:
            txt = f"📖 *{s.get('scene_title')}*\n\n{s.get('scene_text')}"
            imgs = s.get("scene_image", [])
            if imgs:
                bot.send_photo(chat, imgs[0], caption=txt, parse_mode="Markdown")
            else:
                bot.send_message(chat, txt, parse_mode="Markdown")
            time.sleep(1.5)

        msg = bot.send_message(chat, "🎬 Generating video… please wait (up to 5 minutes)")

        # ======================
        # POLLING (5 MIN SAFE)
        # ======================
        start = time.time()
        while time.time() - start < 300:
            time.sleep(12)
            s = requests.get(
                f"{API_BASE}/video-status",
                params={"cid": cid},
                timeout=30
            ).json()

            if s.get("status") == "success":
                bot.delete_message(chat, msg.message_id)
                v = s["video"]["video_url"]
                bot.send_video(chat, v, caption="✅ Video Ready")
                return

            if "error" in s:
                bot.edit_message_text(
                    f"❌ Video error:\n{s}",
                    chat,
                    msg.message_id
                )
                return

        bot.edit_message_text(
            "⚠️ Timeout: video took too long",
            chat,
            msg.message_id
        )

    except Exception as e:
        bot.send_message(chat, f"⚠️ Unexpected error:\n{e}")

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
