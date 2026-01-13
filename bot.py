import telebot
import requests
import time
import os
from threading import Thread
from flask import Flask

# --- RENDER HEALTH CHECK SERVER ---
app = Flask(__name__)
@app.route('/')
def health(): return "SnapStudy AI: Online", 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT SETUP ---
BOT_TOKEN = "8264213109:AAFc_enx3eqne8K-8powbh90zBUsP3k_6Tc"
VERCEL_API = "https://study-bot-phi.vercel.app/fetch"
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def welcome(message):
    msg = (
        "📚 *Welcome to SnapStudy AI*\n\n"
        "I am your professional visual learning assistant. Submit any topic to receive a complete video lesson and summary."
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def process_topic(message):
    topic = message.text
    chat_id = message.chat.id

    # 1. Professional Reaction
    try:
        bot.set_message_reaction(chat_id, message.message_id, [telebot.types.ReactionTypeEmoji("👀")])
    except: pass

    # 2. Status Update
    status_msg = bot.send_message(chat_id, f"🔍 *Status:* Synthesizing professional video for '{topic}'... This may take up to 2 minutes.", parse_mode="Markdown")

    def engine_thread():
        try:
            # High timeout because video generation takes time
            response = requests.get(f"{VERCEL_API}?topic={topic}", timeout=180)
            
            if response.status_code == 200:
                data = response.json()
                video_url = data.get("video_url")
                title = data.get("title", "Educational Insight")
                notes = "\n\n".join(data.get("transcript", []))

                bot.delete_message(chat_id, status_msg.message_id)

                # 3. Deliver Video + Title + Script
                caption = f"🎬 *{title}*\n\n📖 *Full Script & Notes:*\n{notes[:900]}..."
                bot.send_video(chat_id, video_url, caption=caption, parse_mode="Markdown")
            
            elif response.status_code == 202:
                bot.edit_message_text("⚠️ *Update:* The video is taking longer than expected. Please wait a moment and try the topic again.", chat_id, status_msg.message_id, parse_mode="Markdown")
            else:
                bot.edit_message_text("❌ *Error:* The engine failed to process the request. Please try a different topic.", chat_id, status_msg.message_id, parse_mode="Markdown")
        
        except Exception:
            bot.edit_message_text("⚠️ *Connection Alert:* The request timed out during synthesis. Please retry.", chat_id, status_msg.message_id, parse_mode="Markdown")

    Thread(target=engine_thread).start()

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    print("🚀 SnapStudy AI Bot Started...")
    bot.infinity_polling()
