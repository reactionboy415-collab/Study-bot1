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
    
    # 1. Add 'Eyes' Reaction to the user's message
    try:
        bot.set_message_reaction(chat_id, message.message_id, [telebot.types.ReactionTypeEmoji("👀")], is_big=False)
    except Exception as e:
        print(f"Reaction Error: {e}")

    # 2. Initial Status Message
    status_msg = bot.send_message(chat_id, "🔍 *Status:* Initializing SnapStudy Engine...", parse_mode="Markdown")

    def call_engine(retry=0):
        try:
            # Update status to show active processing
            bot.edit_message_text(f"⚡ *Status:* Analyzing content for '{topic}'...", chat_id, status_msg.message_id, parse_mode="Markdown")
            
            # Note: Ensure your Vercel API is updated to return BOTH scenes and video data
            response = requests.get(f"{VERCEL_API}?topic={topic}", timeout=120)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for scenes (Images + Text)
                scenes = data.get('scenes') if isinstance(data, dict) else data
                
                if isinstance(scenes, list) and len(scenes) > 0:
                    bot.edit_message_text("✅ *Status:* Visual assets generated. Delivering now...", chat_id, status_msg.message_id, parse_mode="Markdown")
                    
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
                    
                    # --- NEW VIDEO LOGIC STARTS HERE ---
                    video_url = data.get('video_url') if isinstance(data, dict) else None
                    if video_url:
                        bot.edit_message_text("🎬 *Status:* Visuals delivered. Finalizing high-quality video synthesis...", chat_id, status_msg.message_id, parse_mode="Markdown")
                        time.sleep(2)
                        bot.send_video(chat_id, video_url, caption=f"🎥 *Full Video Lesson:* {topic}", parse_mode="Markdown")
                    
                    bot.delete_message(chat_id, status_msg.message_id)
                    return
            
            elif response.status_code == 202 and retry < 5:
                bot.edit_message_text(f"⏳ *Status:* Generating visual frames (Attempt {retry+1})...", chat_id, status_msg.message_id, parse_mode="Markdown")
                time.sleep(15)
                return call_engine(retry + 1)
            
            bot.edit_message_text("❌ *System Notice:* Data retrieval failed. Please try a different topic.", chat_id, status_msg.message_id, parse_mode="Markdown")
        
        except Exception as e:
            print(f"Engine Error: {e}")
            bot.edit_message_text("⚠️ *Network Alert:* The request timed out. Please try again.", chat_id, status_msg.message_id, parse_mode="Markdown")

    # Use a Thread to prevent blocking the whole bot
    Thread(target=call_engine).start()

if __name__ == "__main__":
    print("🌐 Launching health check server on port 10000...")
    Thread(target=run_web_server).start()
    
    print("🚀 SnapStudy AI Bot is operational...")
    bot.infinity_polling()
