import telebot
import requests
import time
import os
from threading import Thread
from flask import Flask

# --- HEALTH CHECK SERVER ---
app = Flask(__name__)
@app.route('/')
def health(): return "SnapStudy AI Engine: Operational", 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT CONFIGURATION ---
BOT_TOKEN = "8264213109:AAFc_enx3eqne8K-8powbh90zBUsP3k_6Tc"
VERCEL_API = "https://study-bot-phi.vercel.app/fetch"
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "📚 *Welcome to SnapStudy AI*\n\nSubmit a topic to receive structured insights and a professional video lesson.", parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_topic(message):
    topic = message.text
    chat_id = message.chat.id
    
    try:
        bot.set_message_reaction(chat_id, message.message_id, [telebot.types.ReactionTypeEmoji("👀")], is_big=False)
    except: pass

    status_msg = bot.send_message(chat_id, "🔍 *Status:* Initializing SnapStudy Engine...", parse_mode="Markdown")

    def call_engine():
        try:
            bot.edit_message_text(f"⚡ *Status:* Analyzing '{topic}'...", chat_id, status_msg.message_id, parse_mode="Markdown")
            
            response = requests.get(f"{VERCEL_API}?topic={topic}", timeout=120)
            if response.status_code == 200:
                data = response.json()
                scenes = data.get('scenes', [])
                
                # 1. Deliver Visual Insights (Images + Text)
                if scenes:
                    bot.edit_message_text("✅ *Status:* Delivering visual insights...", chat_id, status_msg.message_id, parse_mode="Markdown")
                    for scene in scenes:
                        title = scene.get('scene_title', 'Insight')
                        text = scene.get('scene_text', '')
                        img = scene.get('scene_image', [None])[0]
                        bot.send_photo(chat_id, img, caption=f"📖 *{title}*\n\n{text}", parse_mode="Markdown") if img else bot.send_message(chat_id, f"📖 *{title}*\n\n{text}", parse_mode="Markdown")
                        time.sleep(1.2)

                # 2. Video Generation Phase with Loading Updates
                bot.edit_message_text("🎬 *Status:* Generating Full AI Video...\n\n⌛ *Synthesis in progress. Please wait...*", chat_id, status_msg.message_id, parse_mode="Markdown")
                
                video_url = data.get('video_url')
                # Polling for the video if not ready in first call
                for _ in range(10): 
                    if video_url: break
                    time.sleep(15)
                    poll = requests.get(f"{VERCEL_API}?topic={topic}").json()
                    video_url = poll.get('video_url')

                if video_url:
                    bot.delete_message(chat_id, status_msg.message_id)
                    bot.send_video(chat_id, video_url, caption=f"🎥 *Full Lesson:* {topic}", parse_mode="Markdown")
                else:
                    bot.edit_message_text("⚠️ *Notice:* Video rendering is slow. It will be sent shortly.", chat_id, status_msg.message_id)
            else:
                bot.edit_message_text("❌ *Error:* Failed to retrieve data.", chat_id, status_msg.message_id)
        except Exception:
            bot.edit_message_text("⚠️ *Network Alert:* Request timed out.", chat_id, status_msg.message_id)

    Thread(target=call_engine).start()

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
