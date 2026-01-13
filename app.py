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
app.secret_key = os.environ.get("SECRET_KEY", "ultra_secure_chirag_rathi_99")

# --- DATABASE & LOGS ---
stats = {"total_requests": 0, "success_count": 0, "failed_count": 0, "logs": []}
user_limits = {}
ADMIN_PASS = "admin123"
DAILY_LIMIT = 3

def get_pro_ua():
    # Modern high-authority user agents
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    return random.choice(uas)

def get_server_public_ip():
    try: return requests.get('https://api.ipify.org', timeout=5).text
    except: return "Detecting..."

# --- UI CONSTANTS ---
CSS_JS = """
<script src="https://cdn.tailwindcss.com"></script>
<style>
    .loader { border-top-color: #3b82f6; animation: spin 1s linear infinite; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    .glass { background: rgba(15, 23, 42, 0.8); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.1); }
    .video-container { position: relative; width: 100%; border-radius: 12px; overflow: hidden; background: #000; }
    .brand-overlay { position: absolute; bottom: 15px; right: 15px; background: #000; padding: 5px 15px; border-radius: 6px; z-index: 99; border: 1px solid #333; }
    .brand-text { color: #fff; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }
</style>
"""

@app.route('/')
def home():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    today = str(date.today())
    if ip not in user_limits: user_limits[ip] = {}
    used = user_limits[ip].get(today, 0)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SnapStudy Pro AI</title>{CSS_JS}
    </head>
    <body class="bg-[#020617] text-slate-300 min-h-screen">
        <div class="max-w-xl mx-auto px-6 py-20">
            <div class="text-center mb-12">
                <h1 class="text-5xl font-black text-white mb-2 italic">SnapStudy AI</h1>
                <p class="text-blue-500 font-bold uppercase text-xs tracking-[0.2em]">{DAILY_LIMIT - used}/3 Daily Credits Remaining</p>
            </div>
            <div class="glass p-8 rounded-3xl shadow-2xl">
                <div class="flex flex-col gap-4">
                    <input type="text" id="topic" placeholder="Explain Photosynthesis..." 
                           class="w-full p-4 bg-slate-900 rounded-xl outline-none border border-slate-700 focus:border-blue-500 text-white transition-all">
                    <button onclick="generate()" id="btn" class="w-full bg-blue-600 hover:bg-blue-500 p-4 rounded-xl font-black text-white transition-transform active:scale-95 uppercase">Start Rendering</button>
                </div>
                <div id="status-box" class="mt-6 hidden flex items-center justify-center gap-4 bg-black/40 p-3 rounded-xl">
                    <div class="loader w-4 h-4 border-2 border-slate-700 rounded-full"></div>
                    <span id="status-text" class="text-xs font-bold text-blue-400 uppercase italic">Initializing...</span>
                </div>
            </div>
            <div id="results" class="mt-10 space-y-6"></div>
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
            }} catch(e) {{ 
                alert("Error: " + e.message); 
                btn.disabled = false; 
                statusBox.classList.add('hidden'); 
            }}
        }}
        async function pollVideo(cid, aid) {{
            const statusText = document.getElementById('status-text');
            while(true) {{
                const res = await fetch(`/api/status?cid=${{cid}}&aid=${{aid}}`);
                const data = await res.json();
                if(data.status === "success") {{
                    document.getElementById('results').innerHTML = `
                    <div class="glass p-2 rounded-2xl overflow-hidden mb-6">
                        <div class="video-container">
                            <video controls class="w-full"><source src="${{data.video_url}}"></video>
                            <div class="brand-overlay"><span class="brand-text">Chirag Rathi</span></div>
                        </div>
                    </div>` + document.getElementById('results').innerHTML;
                    document.getElementById('status-box').classList.add('hidden');
                    document.getElementById('btn').disabled = false;
                    break;
                }}
                statusText.innerText = (data.step || "Rendering").toUpperCase();
                await new Promise(r => setTimeout(r, 8000));
            }}
        }}
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/admin')
def admin():
    if request.args.get('pass') != ADMIN_PASS: return "Access Denied", 403
    server_ip = get_server_public_ip()
    log_rows = "".join([f'<tr class="border-b border-slate-800"><td class="p-4 text-[10px] text-slate-500 font-mono">{l["time"]}</td><td class="p-4 text-blue-400 font-mono text-xs">{l["ip"]}</td><td class="p-4 font-bold text-sm">{l["topic"]}</td><td class="p-4"><span class="px-3 py-1 rounded text-[9px] font-bold uppercase {"bg-green-900/30 text-green-400" if l["status"]=="Success" else "bg-red-900/30 text-red-400"}">{l["status"]}</span></td></tr>' for l in stats["logs"][::-1]])
    
    return render_template_string(f"""
    <!DOCTYPE html>
    <html><head><title>Admin Console</title>{CSS_JS}</head>
    <body class="bg-[#020617] text-white p-10 uppercase tracking-tighter">
        <div class="max-w-6xl mx-auto">
            <div class="flex justify-between items-end mb-10 border-b border-slate-800 pb-6">
                <h1 class="text-3xl font-black italic text-blue-500">System Dashboard</h1>
                <div class="text-right"><p class="text-[10px] text-slate-500">Server_IP</p><p class="text-xl font-mono text-blue-400">{server_ip}</p></div>
            </div>
            <div class="grid grid-cols-3 gap-6 mb-10 text-center">
                <div class="glass p-6 rounded-2xl">Total: {stats['total_requests']}</div>
                <div class="glass p-6 rounded-2xl text-green-400">Success: {stats['success_count']}</div>
                <div class="glass p-6 rounded-2xl text-red-400">Failed: {stats['failed_count']}</div>
            </div>
            <div class="glass rounded-2xl overflow-hidden">
                <table class="w-full text-left"><thead class="bg-slate-900/50 text-[10px] text-slate-500"><tr><th class="p-4">Time</th><th class="p-4">User_IP</th><th class="p-4">Topic</th><th class="p-4">Status</th></tr></thead><tbody>{log_rows}</tbody></table>
            </div>
        </div>
    </body></html>
    """)

@app.route('/api/generate')
def generate_api():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    today = str(date.today())
    if ip not in user_limits: user_limits[ip] = {}
    if user_limits[ip].get(today, 0) >= DAILY_LIMIT: return jsonify({"error": "Daily Limit 3/3 Reached"}), 403

    topic, aid, ua = request.args.get('topic'), uuid.uuid4().hex, get_pro_ua()
    stats["total_requests"] += 1
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    
    try:
        # Step 1: Init with headers
        headers = {'User-Agent': ua, 'Referer': 'https://notegpt.io/pdf-to-video'}
        init = scraper.post("https://notegpt.io/api/v2/pdf-to-video", json={
            "source_url": "", "source_type": "text", "input_prompt": topic,
            "setting": {"frame_size": "16:9", "duration": 1, "lang": "en", "gen_flow": "edit_script", "add_watermark": False}
        }, headers=headers, cookies={'anonymous_user_id': aid}).json()
        
        cid = init.get("data", {}).get("conversation_id")
        if not cid: raise Exception("Server rejected request")
        
        time.sleep(10) # Human-like wait

        # Step 2: Get Script
        script_res = scraper.get(f"https://notegpt.io/api/v2/pdf-to-video/script/get?conversation_id={cid}", headers=headers, cookies={'anonymous_user_id': aid}).json()
        script_data = script_res.get("data", {})
        
        # Step 3: Edit and Force Watermark Disable
        if 'setting' in script_data: script_data['setting']['add_watermark'] = False
        scraper.post("https://notegpt.io/api/v2/pdf-to-video/script/edit", 
                     json={"conversation_id": cid, "script_data": json.dumps(script_data), "is_force_save": True}, 
                     headers=headers, cookies={'anonymous_user_id': aid})

        user_limits[ip][today] = user_limits[ip].get(today, 0) + 1
        stats["success_count"] += 1
        stats["logs"].append({"ip": ip, "topic": topic, "time": time.strftime("%H:%M:%S"), "status": "Success"})
        return jsonify({"cid": cid, "anon_id": aid})
    except Exception as e:
        stats["failed_count"] += 1
        stats["logs"].append({"ip": ip, "topic": topic, "time": time.strftime("%H:%M:%S"), "status": "Failed"})
        return jsonify({"error": "Engine Reset - NoteGPT Blocked Request. Try again in 1 min."}), 500

@app.route('/api/status')
def status_api():
    cid, aid = request.args.get('cid'), request.args.get('aid')
    res = cloudscraper.create_scraper().get(f"https://notegpt.io/api/v2/pdf-to-video/status?conversation_id={cid}", cookies={'anonymous_user_id': aid}).json()
    data = res.get("data", {})
    return jsonify({"status": data.get("status"), "video_url": data.get("cdn_video_url") or data.get("video_url"), "step": data.get("step")})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
