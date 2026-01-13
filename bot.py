import telebot
import requests
import time
import os
from threading import Thread
from flask import Flask

# ---------------- HEALTH CHECK ----------------
app = Flask(__name__)

@app.route("/")
def health():
    return "SnapStudy Bot Alive", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ---------------- BOT CONFIG ----------------
BOT_TOKEN = "8264213109:AAGo_Bqe7q_84iUbsz2bvnQbP7iHBJ8MNWQ"
API_URL = "https://study-bot-phi.vercel.app/fetch"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=["start"])
def start(m):
    bot.reply_to(
        m,
        "📚 *SnapStudy AI*\n\nSend me any topic.\nI’ll research + generate a full explainer video 🎬",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: True)
def handle(m):
    chat_id = m.chat.id
    topic = m.text

    status_msg = bot.send_message(
        chat_id,
        f"🔍 *Researching:* `{topic}`",
        parse_mode="Markdown"
    )

    def work():
        try:
            while True:
                r = requests.get(
                    API_URL,
                    params={"topic": topic},
                    timeout=40
                )

                # PROCESSING
                if r.status_code == 202:
                    d = r.json()
                    bot.edit_message_text(
                        f"🎬 *Generating video…*\n\n"
                        f"⏳ Step: `{d.get('step')}`",
                        chat_id,
                        status_msg.message_id,
                        parse_mode="Markdown"
                    )
                    time.sleep(10)
                    continue

                # ERROR
                if r.status_code != 200:
                    bot.edit_message_text(
                        f"❌ *Backend Error*\n\n`{r.text}`",
                        chat_id,
                        status_msg.message_id,
                        parse_mode="Markdown"
                    )
                    return

                d = r.json()

                if not d.get("ok"):
                    bot.edit_message_text(
                        f"❌ *Engine Failed*\n\n`{d}`",
                        chat_id,
                        status_msg.message_id,
                        parse_mode="Markdown"
                    )
                    return

                if d.get("status") != "success":
                    bot.edit_message_text(
                        f"❌ *Unexpected State
