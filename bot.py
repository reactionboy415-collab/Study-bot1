import telebot
import requests
import time
import os
from threading import Thread
from flask import Flask

# --- HEALTH CHECK SERVER ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "SnapStudy AI Engine: Operational", 200

def run_web_server():
    # Explicitly binding to port 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT CONFIGURATION ---
BOT_TOKEN = "8264213109:AAFc_enx3eqne8K-8powbh90zBUsP3k_6Tc"
VERCEL_API = "https://study-bot-phi.vercel.app/fetch"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "📚 *Welcome to SnapStudy AI*\n\n"
        "I am your professional visual learning assistant. I transform academic topics into structured insights.\n\n"
        "🔍 *Instructions:*\n"
        "Please provide a topic you wish to study (e.g., 'Thermodynamics' or 'Cell Mitosis')."
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_topic(message):
    topic = message.text
    chat_id = message.chat.id
    
    # --- ADDED REACTION LOGIC ---
    bot.set_message_reaction(chat_id, message.message_id, [telebot.types.ReactionTypeEmoji("👀")], is_big=False)
    
    status_msg = bot.send_message(chat_id, f"🔍 *Analysis in Progress:* Researching '{topic}'...", parse_mode="Markdown")

    def call_engine(retry=0):
        try:
            response = requests.get(f"{VERCEL_API}?topic={topic}", timeout=45)
            if response.status_code == 200:
                scenes = response.json()
                if isinstance(scenes, list) and len(scenes) > 0:
                    bot.delete_message(chat_id, status_msg.message_id)
                    for scene in scenes:
                        title = scene.get('scene_title', 'Insight')
                        text = scene.get('scene_text', '')
                        image_url = scene.get('scene_image', [None])[0]
                        caption = f"📖 *{title}*\n\n{text}"
                        if image_url:
                            bot.send_photo(chat_id, image_url, caption=caption, parse_mode="Markdown")
                        else:
                            bot.send_message(chat_id, caption, parse_mode="Markdown")
                        time.sleep(1.5)
                    return
            elif response.status_code == 202 and retry < 2:
                time.sleep(10)
                return call_engine(retry + 1)
            bot.edit_message_text("❌ *System Notice:* Data retrieval failed. Please try again.", chat_id, status_msg.message_id, parse_mode="Markdown")
        except Exception:
            bot.edit_message_text("⚠️ *Network Alert:* Connection timed out.", chat_id, status_msg.message_id, parse_mode="Markdown")

    call_engine()

if __name__ == "__main__":
    # Launching health check server on port 10000 in a background thread
    print("🌐 Launching health check server on port 10000...")
    Thread(target=run_web_server).start()
    
    print("🚀 SnapStudy AI Bot is operational...")
    bot.infinity_polling()
