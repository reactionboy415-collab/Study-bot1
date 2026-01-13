import telebot
import requests
import time
import os
from threading import Thread
from flask import Flask

app = Flask(__name__)
@app.route('/')
def health(): return "AI Engine Live", 200

BOT_TOKEN = "8264213109:AAH_Ntyloaj6Xirj9wf0Opt7d4B0prYBW1c"
VERCEL_API = "https://study-bot-phi.vercel.app/fetch"
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(func=lambda m: True)
def process(message):
    topic = message.text
    chat_id = message.chat.id
    try: bot.set_message_reaction(chat_id, message.message_id, [telebot.types.ReactionTypeEmoji("👀")])
    except: pass

    status_msg = bot.send_message(chat_id, "🚀 *System:* Deploying Advanced Session Identities...", parse_mode="Markdown")

    def thread_engine():
        try:
            # 1. Start Initial Fetch
            r = requests.get(f"{VERCEL_API}?topic={topic}", timeout=150).json()
            if "error" in r:
                bot.edit_message_text("❌ *Engine Error:* Identities flagged. Retrying auto...", chat_id, status_msg.message_id)
                return

            cid, aid, tid, ua = r['cid'], r['anon_id'], r['tid'], r['ua']
            
            # Send Insights
            bot.edit_message_text("✅ *Status:* Research Finished. Syncing Visuals...", chat_id, status_msg.message_id, parse_mode="Markdown")
            for s in r.get('scenes', []):
                cap = f"📖 *{s['scene_title']}*\n\n{s['scene_text']}"
                img = s['scene_image'][0] if s.get('scene_image') else None
                if img: bot.send_photo(chat_id, img, caption=cap, parse_mode="Markdown")
                else: bot.send_message(chat_id, cap, parse_mode="Markdown")
                time.sleep(1.2)

            # 2. Live Polling with Step Updates
            last_step = ""
            bot.edit_message_text("🎬 *Live Process:* Initializing Rendering Engine...", chat_id, status_msg.message_id, parse_mode="Markdown")
            
            for _ in range(40): # Extended wait for High-Quality
                time.sleep(15)
                p = requests.get(f"{VERCEL_API}?cid={cid}&anon_id={aid}&tid={tid}&ua={ua}").json()
                
                if p.get('status') == "success":
                    bot.delete_message(chat_id, status_msg.message_id)
                    bot.send_video(chat_id, p['video_url'], caption=f"🎥 *Full Lesson:* {topic}\n✨ *No Watermark | AI Synthesized*", parse_mode="Markdown")
                    return

                step = str(p.get('step', 'Synthesizing')).replace('_', ' ').title()
                if step != last_step:
                    bot.edit_message_text(f"🎬 *Live Process:* {step}...\n\n⌛ Rendering (Upto 5 mins)...", chat_id, status_msg.message_id, parse_mode="Markdown")
                    last_step = step

        except Exception as e:
            bot.edit_message_text("⚠️ *System Notice:* Connection reset by NoteGPT. Please retry.", chat_id, status_msg.message_id)

    Thread(target=thread_engine).start()

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))).start()
    bot.infinity_polling()
