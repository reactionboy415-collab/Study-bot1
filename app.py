from flask import Flask, render_template_string, request, jsonify
import cloudscraper
import uuid
import time
import json
import os
import requests
import random
from datetime import date

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chirag_rathi_ultimate_key")

# --- DATABASE ---
stats = {"total_requests": 0, "success_count": 0, "failed_count": 0, "logs": []}
user_limits = {}
ADMIN_PASS = "admin123"
DAILY_LIMIT = 3

def get_pro_ua():
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    return random.choice(uas)

# --- UI ---
CSS_JS = """
<script src="https://cdn.tailwindcss.com"></script>
<style>
    .loader { border-top-color: #3b82f6; animation: spin 1s linear infinite; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    .glass { background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.1); }
</style>
"""

@app.route('/')
def home():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    today = str(date.today())
    if ip not in user_limits: user_limits[ip] = {}
    used = user_limits[ip].get(today, 0)
    return render_template_string(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>SnapStudy AI</title>{CSS_JS}</head>
    <body class="bg-[#020617] text-slate-300 font-sans min-h-screen">
        <div class="max-w-xl mx-auto px-6 py-20 text-center">
            <h1 class="text-6xl font-black text-white mb-2 tracking-tighter italic">SnapStudy AI</h1>
            <p class="text-blue-500 font-bold text-xs tracking-widest uppercase mb-12">Credits: {DAILY_LIMIT - used}/3 Today</p>
            <div class="glass p-8 rounded-[2.5rem] shadow-2xl">
                <input type="text" id="topic" placeholder="Topic: Quantum Physics..." class="w-full p-5 bg-slate-900 rounded-2xl outline-none border border-slate-700 focus:border-blue-500 text-white mb-4">
                <button onclick="generate()" id="btn" class="w-full bg-blue-600 hover:bg-blue-500 p-5 rounded-2xl font-black text-white transition-all active:scale-95 shadow-lg">GENERATE BRANDED VIDEO</button>
                <div id="status-box" class="mt-6 hidden flex items-center justify-center gap-4 bg-black/40 p-4 rounded-2xl">
                    <div class="loader w-4 h-4 border-2 border-slate-700 rounded-full"></div>
                    <span id="status-text" class="text-xs font-bold text-blue-400 uppercase italic tracking-widest">Starting...</span>
                </div>
            </div>
            <div id="results" class="mt-12"></div>
        </div>
        <script>
        async function generate() {{
            const topic = document.getElementById('topic').value;
            const btn = document.getElementById('btn');
            const statusBox = document.getElementById('status-box');
            if(!topic) return;
            btn.disabled = true; statusBox.classList.remove('hidden');
            try {{
                const res = await fetch(`/api/generate?topic=${{encodeURIComponent(topic)}}`);
                const data = await res.json();
                if(data.error) throw new Error(data.error);
                pollVideo(data.cid, data.anon_id);
            }} catch(e) {{ alert(e.message); btn.disabled = false; statusBox.classList.add('hidden'); }}
        }}
        async function pollVideo(cid, aid) {{
            const statusText = document.getElementById('status-text');
            while(true) {{
                const res = await fetch(`/api/status?cid=${{cid}}&aid=${{aid}}`);
                const data = await res.json();
                if(data.status === "success") {{
                    document.getElementById('results').innerHTML = `<div class="glass p-4 rounded-[2rem] overflow-hidden"><video controls class="w-full rounded-xl"><source src="${{data.video_url}}"></video><p class="mt-4 font-black text-blue-500 italic">🔥 Hardcoded Watermark Applied!</p></div>`;
                    document.getElementById('status-box').classList.add('hidden');
                    document.getElementById('btn').disabled = false;
                    break;
                }}
                statusText.innerText = (data.step || "Rendering").toUpperCase();
                await new Promise(r => setTimeout(r, 9000));
            }}
        }}
        </script>
    </body>
    </html>
    """)

@app.route('/admin')
def admin():
    if request.args.get('pass') != ADMIN_PASS: return "Denied", 403
    log_rows = "".join([f'<tr class="border-b border-slate-800 text-xs"><td class="p-4">{l["time"]}</td><td class="p-4 text-blue-400">{l["ip"]}</td><td class="p-4 font-bold">{l["topic"]}</td><td class="p-4">{l["status"]}</td></tr>' for l in stats["logs"][::-1]])
    return render_template_string(f"""<!DOCTYPE html><html><head>{CSS_JS}</head><body class="bg-black text-white p-10"><h1 class="text-4xl font-black mb-10 text-blue-500 italic uppercase">System Console</h1><div class="grid grid-cols-3 gap-6 mb-10"><div class="glass p-8 rounded-3xl">Hits: {stats['total_requests']}</div><div class="glass p-8 rounded-3xl text-green-500 text-xl font-bold font-mono">IP: {requests.get('https://api.ipify.org').text}</div></div><table class="w-full glass rounded-3xl overflow-hidden"><thead><tr class="bg-slate-800 text-left"><th class="p-4">Time</th><th class="p-4">IP</th><th class="p-4">Topic</th><th class="p-4">Status</th></tr></thead><tbody>{log_rows}</tbody></table></body></html>""")

@app.route('/api/generate')
def generate_api():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    today = str(date.today())
    if ip not in user_limits: user_limits[ip] = {}
    if user_limits[ip].get(today, 0) >= DAILY_LIMIT: return jsonify({"error": "Limit Reached"}), 403

    topic, aid, ua = request.args.get('topic'), uuid.uuid4().hex, get_pro_ua()
    stats["total_requests"] += 1
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    headers = {'User-Agent': ua, 'Referer': 'https://notegpt.io/'}
    
    try:
        # 1. Initial Call
        init = scraper.post("https://notegpt.io/api/v2/pdf-to-video", json={"source_url": "", "source_type": "text", "input_prompt": topic, "setting": {"frame_size": "16:9", "duration": 1, "lang": "en", "gen_flow": "edit_script", "add_watermark": False}}, headers=headers, cookies={'anonymous_user_id': aid}).json()
        cid = init.get("data", {}).get("conversation_id")
        time.sleep(10)

        # 2. Fetch AI Script
        script_res = scraper.get(f"https://notegpt.io/api/v2/pdf-to-video/script/get?conversation_id={cid}", headers=headers, cookies={'anonymous_user_id': aid}).json()
        script_data = script_res.get("data", {})

        # --- THE WATERMARK INJECTION LOGIC ---
        # Video ke har scene ke text ke peeche aapka naam force karenge
        if 'scenes' in script_data:
            for scene in script_data['scenes']:
                scene['scene_text'] += " | Created by: Chirag Rathi"
                if 'subtitles' in scene:
                    for sub in scene['subtitles']:
                        sub['text'] += " [Chirag Rathi]"
        
        # 3. Force Save with Branded Script
        scraper.post("https://notegpt.io/api/v2/pdf-to-video/script/edit", json={"conversation_id": cid, "script_data": json.dumps(script_data), "is_force_save": True}, headers=headers, cookies={'anonymous_user_id': aid})

        user_limits[ip][today] = user_limits[ip].get(today, 0) + 1
        stats["success_count"] += 1
        stats["logs"].append({"ip": ip, "topic": topic, "time": time.strftime("%H:%M:%S"), "status": "Success"})
        return jsonify({"cid": cid, "anon_id": aid})
    except:
        stats["failed_count"] += 1
        stats["logs"].append({"ip": ip, "topic": topic, "time": time.strftime("%H:%M:%S"), "status": "Failed"})
        return jsonify({"error": "Engine Reset"}), 500

@app.route('/api/status')
def status_api():
    cid, aid = request.args.get('cid'), request.args.get('aid')
    res = cloudscraper.create_scraper().get(f"https://notegpt.io/api/v2/pdf-to-video/status?conversation_id={cid}", cookies={'anonymous_user_id': aid}).json()
    data = res.get("data", {})
    return jsonify({"status": data.get("status"), "video_url": data.get("cdn_video_url") or data.get("video_url"), "step": data.get("step")})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
