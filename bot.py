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
# Using your Vercel URL
VERCEL_API = "https://study-bot-phi.vercel.app/fetch"
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def welcome(message):
    msg = (
        "📚 *Welcome to SnapStudy AI*\n\n"
        "I am your professional visual learning assistant. Submit any academic topic to receive a high-quality video lesson and detailed summary."
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def process_topic(message):
    topic = message.text
    chat_id = message.chat.id

    # 1. Professional Reaction 👀
    try:
        bot.set_message_reaction(chat_id, message.message_id, [telebot.types.ReactionTypeEmoji("👀")], is_big=False)
    except:
        pass

    # 2. Initial Status Message
    status_msg = bot.send_message(chat_id, "🔍 *Status:* Initiating research and synthesizing video content...", parse_mode="Markdown")

    def engine_thread():
        # Step-by-step polling to avoid timeouts
        max_attempts = 15  # Total wait time ~150 seconds
        
        for attempt in range(max_attempts):
            try:
                # Update status text every few attempts to keep user engaged
                if attempt == 4:
                    bot.edit_message_text("⏳ *Status:* Generating high-quality visual frames...", chat_id, status_msg.message_id, parse_mode="Markdown")
                elif attempt == 8:
                    bot.edit_message_text("🎙️ *Status:* Synthesizing professional voiceover...", chat_id, status_msg.message_id, parse_mode="Markdown")
                elif attempt == 12:
                    bot.edit_message_text("🎬 *Status:* Finalizing video rendering...", chat_id, status_msg.message_id, parse_mode="Markdown")

                # Call Vercel API
                response = requests.get(f"{VERCEL_API}?topic={topic}", timeout=40)
                
                if response.status_code == 200:
                    data = response.json()
                    video_url = data.get("video_url")
                    title = data.get("title", "Educational Insight")
                    transcript_list = data.get("transcript", [])
                    notes = "\n\n".join(transcript_list)

                    # Delete status and send final video
                    bot.delete_message(chat_id, status_msg.message_id)
                    
                    caption = f"🎬 *{title}*\n\n📖 *Detailed Notes:*\n{notes[:900]}..."
                    bot.send_video(chat_id, video_url, caption=caption, parse_mode="Markdown")
                    return # Exit thread successfully

                elif response.status_code == 202:
                    # Video is still processing on NoteGPT side
                    time.sleep(10)
                    continue
                
                else:
                    bot.edit_message_text("❌ *System Error:* Unable to process this specific topic. Please try another.", chat_id, status_msg.message_id, parse_mode="Markdown")
                    return

            except Exception as e:
                # If a timeout occurs, we don't stop; we wait and retry
                time.sleep(10)
                continue

        bot.edit_message_text("⚠️ *Notice:* The synthesis is taking longer than usual. Please try again in a few minutes.", chat_id, status_msg.message_id, parse_mode="Markdown")

    # Run the engine in background to keep bot responsive
    Thread(target=engine_thread).start()

if __name__ == "__main__":
    # Start web server for Render health check
    Thread(target=run_web_server).start()
    print("🚀 SnapStudy AI Bot is operational.")
    bot.infinity_polling()
