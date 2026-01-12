import telebot
import requests
import time
import os

# --- CONFIGURATION ---
BOT_TOKEN = "8264213109:AAFc_enx3eqne8K-8powbh90zBUsP3k_6Tc"
VERCEL_API = "https://study-bot-phi.vercel.app/fetch"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "📚 *Welcome to SnapStudy AI*\n\n"
        "I am your advanced visual learning assistant. I transform complex educational topics into structured visual insights and concise explanations.\n\n"
        "🔍 *How to Proceed:*\n"
        "Please submit a specific academic or general interest topic (e.g., 'The Water Cycle', 'Human Circulatory System', or 'Quantum Entanglement')."
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_topic(message):
    topic = message.text
    chat_id = message.chat.id
    
    # Informing the user that processing has commenced
    status_msg = bot.send_message(chat_id, f"🔍 *Processing Request:* Researching '{topic}' via SnapStudy Engine...", parse_mode="Markdown")

    def call_engine(retry=0):
        try:
            # Invoking the Vercel IP-Rotator API
            response = requests.get(f"{VERCEL_API}?topic={topic}", timeout=45)
            
            if response.status_code == 200:
                scenes = response.json()
                if isinstance(scenes, list) and len(scenes) > 0:
                    bot.delete_message(chat_id, status_msg.message_id)
                    
                    for scene in scenes:
                        title = scene.get('scene_title', 'Academic Insight')
                        explanation = scene.get('scene_text', 'No description available.')
                        image_url = scene.get('scene_image', [None])[0]
                        
                        caption = f"📖 *{title}*\n\n{explanation}"
                        
                        if image_url:
                            bot.send_photo(chat_id, image_url, caption=caption, parse_mode="Markdown")
                        else:
                            bot.send_message(chat_id, caption, parse_mode="Markdown")
                        time.sleep(1.5) # Ensuring delivery stability
                    return
            
            elif response.status_code == 202 and retry < 2:
                bot.edit_message_text("⏳ *Status Update:* Generating visual assets. Please remain patient.", chat_id, status_msg.message_id, parse_mode="Markdown")
                time.sleep(10)
                return call_engine(retry + 1)
                
            bot.edit_message_text("❌ *Error:* The engine was unable to retrieve data at this time. Please attempt your request again shortly.", chat_id, status_msg.message_id, parse_mode="Markdown")
            
        except Exception:
            bot.edit_message_text("⚠️ *Connection Error:* Request timed out. Please verify your connection and try again.", chat_id, status_msg.message_id, parse_mode="Markdown")

    call_engine()

if __name__ == "__main__":
    print("🚀 SnapStudy AI is operational.")
    bot.infinity_polling()
