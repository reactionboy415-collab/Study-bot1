import telebot
import requests
import time
import os
from threading import Thread
from flask import Flask

app = Flask(__name__)
@app.route('/')
def health(): return "SnapStudy AI: Online", 200

# APPLIED YOUR TOKEN
BOT_TOKEN = "8264213109:AAH_Ntyloaj6Xirj9wf0Opt7d4B0prYBW1c"
VERCEL_API = "https://study-bot-phi.vercel.app/fetch"
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(func=lambda m: True)
def handle_request(message):
    topic = message.text
    chat_id = message.chat.id
    try: bot.set_message_reaction(chat_id, message.message_id, [telebot.types.ReactionTypeEmoji("👀")])
    except: pass

    status_msg = bot.send_message(chat_id, "🔍 *Status:* Preparing Unlimited Engine...", parse_mode="Markdown")

    def run_flow():
        try:
            # Phase 1: Initiation
            res = requests.get(f"{VERCEL_API}?topic={topic}", timeout=150).json()
            if "error" in res:
                bot.edit_message_text("❌ *Error:* Engine failed. Try again.", chat_id, status_msg.message_id)
                return

            scenes = res.get('scenes', [])
            cid = res.get('cid')
            aid = res.get('anon_id')
            tid = res.get('tid')

            # Deliver Images/Text
            if scenes:
                bot.edit_message_text("✅ *Status:* Research Complete. Delivering insights...", chat_id, status_msg.message_id, parse_mode="Markdown")
                for s in scenes:
                    cap = f"📖 *{s.get('scene_title')}*\n\n{s.get('scene_text')}"
                    img = s.get('scene_image', [None])[0]
                    if img: bot.send_photo(chat_id, img, caption=cap, parse_mode="Markdown")
                    else: bot.send_message(chat_id, cap, parse_mode="Markdown")
                    time.sleep(1.2)

            # Phase 2: Live Polling
            bot.edit_message_text("🎬 *Live Process:* Starting Video Generation...", chat_id, status_msg.message_id, parse_mode="Markdown")
            
            last_step = ""
            for _ in range(35): # Up to 8 minutes
                time.sleep(15)
                # Polling with same IDs to keep session alive for this CID
                poll = requests.get(f"{VERCEL_API}?cid={cid}&anon_id={aid}&tid={tid}").json()
                
                if poll.get('status') == "success":
                    v_url = poll.get('video_url')
                    bot.delete_message(chat_id, status_msg.message_id)
                    bot.send_video(chat_id, v_url, caption=f"🎥 *Full Lesson:* {topic}\n✨ *Unlimited Session*", parse_mode="Markdown")
                    return

                step = str(poll.get('step', 'Processing')).replace('_', ' ').title()
                if step != last_step:
                    bot.edit_message_text(f"🎬 *Live Process:* {step}...\n\n⏳ No-Watermark Rendering in progress...", chat_id, status_msg.message_id, parse_mode="Markdown")
                    last_step = step

            bot.edit_message_text("⚠️ *Notice:* Video taking too long, but it's on its way.", chat_id, status_msg.message_id)

        except Exception as e:
            bot.edit_message_text("❌ *System Alert:* Connection reset. Retrying suggested.", chat_id, status_msg.message_id)

    Thread(target=run_flow).start()

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))).start()
    bot.infinity_polling()
