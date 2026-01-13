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
app.secret_key = os.environ.get("SECRET_KEY", str(uuid.uuid4()))

# --- DATABASE & LOGS ---
stats = {"total_requests": 0, "success_count": 0, "failed_count": 0, "logs": []}
user_limits = {}
ADMIN_PASS = "admin123"
DAILY_LIMIT = 3

def get_extreme_ua():
    chrome_ver = random.randint(115, 122)
    android_ver = random.randint(11, 14)
    devices = ["SM-S918B", "Pixel 8 Pro", "KB2003", "SM-G998B", "Xiaomi 13T", "Nothing Phone (2)"]
    return f"Mozilla/5.0 (Linux; Android {android_ver}; {random.choice(devices)}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver}.0.0.0 Mobile Safari/537.36"

def get_server_public_ip():
    try: return requests.get('https://api.ipify.org', timeout=5).text
    except: return "127.0.0.1"

# --- UI CONSTANTS ---
CSS_JS = """
<script src="https://cdn.tailwindcss.com"></script>
<style>
    .loader { border-top-color: #3b82f6; animation: spin 1s linear infinite; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); }
    
    /* Branding Overlay Style */
    .video-container { position: relative; width: 100%; border-radius: 1rem; overflow: hidden; }
    .brand-overlay {
        position: absolute;
        bottom: 12px;
        right: 12px;
        background: black;
        padding: 4px 12px;
        border-radius: 4px;
        z-index: 50;
        pointer-events: none;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 1px solid #1e293b;
    }
    .brand-text {
        color: white;
        font-size: 11px;
        font-weight: 900;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        font-family: 'Inter', sans-serif;
    }
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
        <title>SnapStudy AI | Branding Mode</title>{CSS_JS}
    </head>
    <body class="bg-[#0f172a] text-slate-200 min-h-screen font-sans">
        <div class="container mx-auto px-4 py-16 max-w-2xl">
            <div class="text-center mb-12">
                <h1 class="text-6xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-500 mb-4 italic tracking-tighter">SnapStudy</h1>
                <div class="inline-block px-4 py-1 bg-blue-500/10 border border-blue-500/20 rounded-full">
                    <p class="text-blue-400 text-xs font-bold tracking-widest uppercase italic">{DAILY_LIMIT - used}/3 Free Credits Left</p>
                </div>
            </div>
            
            <div class="glass p-8 rounded-3xl border border-slate-700 shadow-2xl">
                <div class="flex flex-col gap-4">
                    <input type="text" id="topic" placeholder="Enter topic for video lesson..." 
                           class="w-full p-5 bg-slate-900/50 rounded-2xl outline-none border-2 border-slate-700 focus:border-blue-500 transition-all text-white placeholder-slate-500">
                    <button onclick="generate()" id="btn" class="w-full bg-blue-600 hover:bg-blue-500 p-4 rounded-xl font-black tracking-widest transition-all active:scale-95 shadow-lg shadow-blue-900/20">CREATE VIDEO</button>
                </div>
                <div id="status-box" class="mt-6 hidden flex items-center justify-center gap-4 py-3 bg-slate-900/50 rounded-xl">
                    <div class="loader w-4 h-4 border-2 border-slate-600 rounded-full"></div>
                    <span id="status-text" class="text-xs font-bold text-blue-400 tracking-widest uppercase italic">Initializing Engine...</span>
                </div>
            </div>
            <div id="results" class="mt-12 space-y-8"></div>
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
                
                // Show Scenes
                data.scenes.forEach(s => {{
                    document.getElementById('results').innerHTML += `<div class="glass p-6 rounded-3xl border border-slate-700">
                        <h3 class="text-xl font-bold text-blue-400 mb-4 tracking-tight">${{s.scene_title}}</h3>
                        <img src="${{s.scene_image[0]}}" class="w-full rounded-2xl mb-4 border border-slate-700 shadow-lg">
                        <p class="text-slate-400 leading-relaxed text-sm">${{s.scene_text}}</p>
                    </div>`;
                }});
                pollVideo(data.cid, data.anon_id);
            }} catch(e) {{ alert(e.message); btn.disabled = false; statusBox.classList.add('hidden'); }}
        }}
        
        async function pollVideo(cid, aid) {{
            const statusText = document.getElementById('status-text');
            while(true) {{
                const res = await fetch(`/api/status?cid=${{cid}}&aid=${{aid}}`);
                const data = await res.json();
                if(data.status === "success") {{
                    document.getElementById('results').innerHTML = `
                    <div class="glass p-4 rounded-3xl border-2 border-blue-500/30 mb-8 overflow-hidden">
                        <div class="video-container">
                            <video controls class="w-full">
                                <source src="${{data.video_url}}">
                            </video>
                            <div class="brand-overlay">
                                <span class="brand-text">Chirag Rathi</span>
                            </div>
                        </div>
                        <p class="text-center text-blue-400 font-black italic tracking-tighter uppercase mt-4">Video Optimized & Branded</p>
                    </div>` + document.getElementById('results').innerHTML;
                    document.getElementById('status-box').classList.add('hidden');
                    document.getElementById('btn').disabled = false;
                    break;
                }}
                statusText.innerText = (data.step || "Synthesizing").toUpperCase();
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
    log_rows = "".join([f'<tr><td class="p-4 text-xs font-mono text-slate-500">{l["time"]}</td><td class="p-4 font-mono text-blue-400 text-xs">{l["ip"]}</td><td class="p-4 text-sm font-bold tracking-tight">{l["topic"]}</td><td class="p-4"><span class="px-3 py-1 rounded-lg text-[9px] font-black uppercase {"bg-green-500/10 text-green-500" if l["status"]=="Success" else "bg-red-500/10 text-red-500"}">{l["status"]}</span></td></tr>' for l in stats["logs"][::-1]])
    
    return render_template_string(f"""
    <!DOCTYPE html>
    <html lang="en"><head><meta charset="UTF-8"><title>Admin Console</title>{CSS_JS}</head>
    <body class="bg-[#020617] text-slate-300 p-8 font-sans uppercase">
        <div class="max-w-6xl mx-auto">
            <div class="flex justify-between items-center mb-12 border-b border-slate-800 pb-8">
                <div><h1 class="text-4xl font-black text-blue-500 italic">SYSTEM_CORE</h1></div>
                <div class="text-right bg-blue-600/5 p-4 rounded-2xl border border-blue-500/20"><p class="text-[9px] font-bold text-slate-500 tracking-widest uppercase">Node_Public_IP</p><p class="text-xl font-mono text-blue-400 font-bold">{server_ip}</p></div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-8 mb-12 text-center">
                <div class="bg-slate-900 p-8 rounded-[2rem] border border-slate-800">Hits: {stats['total_requests']}</div>
                <div class="bg-slate-900 p-8 rounded-[2rem] border border-green-500/20 text-green-500">OK: {stats['success_count']}</div>
                <div class="bg-slate-900 p-8 rounded-[2rem] border border-red-500/20 text-red-500">ERR: {stats['failed_count']}</div>
            </div>
            <div class="bg-slate-900 rounded-[2rem] overflow-hidden border border-slate-800">
                <table class="w-full text-left">
                    <thead class="bg-slate-800/50 text-slate-500 text-[10px] font-black"><tr><th class="p-6">Timestamp</th><th class="p-6">Origin_IP</th><th class="p-6">Payload_Topic</th><th class="p-6">Outcome</th></tr></thead>
                    <tbody class="divide-y divide-slate-800/50">{log_rows}</tbody>
                </table>
            </div>
        </div>
    </body></html>
    """)

@app.route('/api/generate')
def generate_api():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    today = str(date.today())
    if ip not in user_limits: user_limits[ip] = {}
    if user_limits[ip].get(today, 0) >= DAILY_LIMIT: return jsonify({"error": "Limit Reached"}), 403

    topic, aid, ua = request.args.get('topic'), uuid.uuid4().hex, get_extreme_ua()
    stats["total_requests"] += 1
    scraper = cloudscraper.create_scraper()
    
    try:
        # Step 1: Initial Post
        init = scraper.post("https://notegpt.io/api/v2/pdf-to-video", json={
            "source_url": "", "source_type": "text", "input_prompt": topic,
            "setting": {"frame_size": "16:9", "duration": 1, "lang": "en", "gen_flow": "edit_script", "add_watermark": False}
        }, headers={'User-Agent': ua, 'Cookie': f'anonymous_user_id={aid}'}).json()
        
        cid = init.get("data", {}).get("conversation_id")
        time.sleep(8)
        
        # Step 2: Get and Edit Metadata
        script_res = scraper.get(f"https://notegpt.io/api/v2/pdf-to-video/script/get?conversation_id={cid}", headers={'User-Agent': ua}, cookies={'anonymous_user_id': aid}).json()
        script_data = script_res.get("data", {})
        
        # Force watermark disable in script
        if 'setting' in script_data: script_data['setting']['add_watermark'] = False
        
        scraper.post("https://notegpt.io/api/v2/pdf-to-video/script/edit", 
                     json={"conversation_id": cid, "script_data": json.dumps(script_data), "is_force_save": True}, 
                     headers={'User-Agent': ua}, cookies={'anonymous_user_id': aid})

        user_limits[ip][today] = user_limits[ip].get(today, 0) + 1
        stats["success_count"] += 1
        stats["logs"].append({"ip": ip, "topic": topic, "time": time.strftime("%H:%M:%S"), "status": "Success"})
        return jsonify({"scenes": script_data.get("scenes", []), "cid": cid, "anon_id": aid})
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
