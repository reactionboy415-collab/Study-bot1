import telebot
import requests
import time
import os
from threading import Thread
from flask import Flask

app = Flask(__name__)
@app.route('/')
def health(): return "SnapStudy AI: Online", 200

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

BOT_TOKEN = "8264213109:AAH_Ntyloaj6Xirj9wf0Opt7d4B0prYBW1c"
VERCEL_API = "https://study-bot-phi.vercel.app/fetch"
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "📚 *SnapStudy AI Ready*\n\nTopic bhejein, main visuals aur No-Watermark video lesson banata hoon.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle_request(message):
    topic = message.text
    chat_id = message.chat.id
    try: bot.set_message_reaction(chat_id, message.message_id, [telebot.types.ReactionTypeEmoji("👀")])
    except: pass

    status_msg = bot.send_message(chat_id, "🔍 *Status:* Starting research...", parse_mode="Markdown")

    def execution_flow():
        try:
            # Phase 1: Images & Text
            res = requests.get(f"{VERCEL_API}?topic={topic}", timeout=120).json()
            scenes = res.get('scenes', [])
            cid = res.get('cid')
            aid = res.get('anon_id')

            if scenes:
                bot.edit_message_text("✅ *Status:* Delivering visual insights...", chat_id, status_msg.message_id, parse_mode="Markdown")
                for s in scenes:
                    cap = f"📖 *{s.get('scene_title')}*\n\n{s.get('scene_text')}"
                    img = s.get('scene_image', [None])[0]
                    if img: bot.send_photo(chat_id, img, caption=cap, parse_mode="Markdown")
                    else: bot.send_message(chat_id, cap, parse_mode="Markdown")
                    time.sleep(1.2)

            # Phase 2: Live Video Polling
            last_step = ""
            for i in range(30): # Up to 7-8 minutes wait
                time.sleep(15)
                poll = requests.get(f"{VERCEL_API}?cid={cid}&anon_id={aid}").json()
                
                current_step = str(poll.get('step', 'Synthesizing Video')).replace('_', ' ').title()
                
                if poll.get('status') == "success":
                    final_video = poll.get('video_url')
                    bot.delete_message(chat_id, status_msg.message_id)
                    bot.send_video(chat_id, final_video, caption=f"🎥 *Full Lesson:* {topic}\n✨ *No Watermark*", parse_mode="Markdown")
                    return

                # Only update if the step has changed to avoid spamming API
                if current_step != last_step:
                    bot.edit_message_text(f"🎬 *Live Process:* {current_step}...\n\n⏳ Video generation may take up to 5 minutes.", chat_id, status_msg.message_id, parse_mode="Markdown")
                    last_step = current_step

            bot.edit_message_text("⚠️ *Notice:* Video is taking longer than usual, but it's processing.", chat_id, status_msg.message_id)

        except Exception as e:
            bot.edit_message_text("❌ *Error:* Processing interrupted. Try again.", chat_id, status_msg.message_id)

    Thread(target=execution_flow).start()

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
