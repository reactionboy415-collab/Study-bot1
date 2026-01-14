from flask import Flask, render_template_string, request, jsonify
import cloudscraper
import uuid
import time
import json
import os
import requests
from datetime import date

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "snapstudy_ultra_secret_99")

# --- DATABASE & LOGS ---
stats = {
    "total_requests": 0,
    "success_count": 0,
    "failed_count": 0,
    "logs": []
}
user_limits = {}
ADMIN_PASS = "admin123"
DAILY_LIMIT = 3

# --- UTILS ---
def get_server_public_ip():
    try:
        # Fetching actual public IP of the Render server
        return requests.get('https://api.ipify.org', timeout=5).text
    except:
        return "Detection Failed"

# --- UI CONSTANTS ---
CSS_JS = """
<script src="https://cdn.tailwindcss.com"></script>
<style>
    .loader { border-top-color: #3b82f6; animation: spin 1s linear infinite; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
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
        <title>SnapStudy AI</title>
        {CSS_JS}
    </head>
    <body class="bg-slate-900 text-white min-h-screen">
        <div class="container mx-auto px-4 py-12 text-center">
            <h1 class="text-5xl font-extrabold text-blue-500 mb-2">SnapStudy AI</h1>
            <p class="text-slate-400 mb-10">Daily Limit: <span class="text-blue-400">{DAILY_LIMIT - used}/3</span></p>
            <div class="max-w-xl mx-auto bg-slate-800 p-6 rounded-2xl shadow-xl border border-slate-700">
                <div class="flex gap-2">
                    <input type="text" id="topic" placeholder="Enter topic..." class="w-full p-4 bg-slate-700 rounded-xl outline-none border border-slate-600 focus:border-blue-500">
                    <button onclick="generate()" id="btn" class="bg-blue-600 hover:bg-blue-700 px-6 rounded-xl font-bold transition">Start</button>
                </div>
                <div id="status-box" class="mt-4 hidden flex items-center justify-center gap-3 text-blue-400">
                    <div class="loader w-5 h-5 border-2 border-slate-500 rounded-full"></div>
                    <span id="status-text">Processing...</span>
                </div>
            </div>
            <div id="results" class="max-w-3xl mx-auto mt-10 space-y-6 text-left"></div>
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
                data.scenes.forEach(s => {{
                    document.getElementById('results').innerHTML += `<div class="bg-slate-800 p-5 rounded-xl border border-slate-700">
                        <h3 class="text-lg font-bold text-blue-400 mb-2">${{s.scene_title}}</h3>
                        <div class="flex flex-col md:flex-row gap-4">
                            <img src="${{s.scene_image[0]}}" class="w-full md:w-48 rounded-lg shadow-md">
                            <p class="text-slate-300 text-sm">${{s.scene_text}}</p>
                        </div>
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
                    document.getElementById('results').innerHTML = `<div class="bg-blue-600/20 border border-blue-500 p-4 rounded-xl mb-4 text-center">
                        <video controls class="w-full rounded-lg shadow-xl mb-3"><source src="${{data.video_url}}"></video>
                        <p class="font-bold text-blue-400 italic">✨ Your No-Watermark Lesson is Ready!</p>
                    </div>` + document.getElementById('results').innerHTML;
                    document.getElementById('status-box').classList.add('hidden');
                    document.getElementById('btn').disabled = false;
                    break;
                }}
                statusText.innerText = "Live: " + (data.step || "Synthesizing Video").replace(/_/g, ' ').toUpperCase();
                await new Promise(r => setTimeout(r, 10000));
            }}
        }}
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/admin')
def admin():
    if request.args.get('pass') != ADMIN_PASS:
        return "Unauthorized Access.", 403
    
    server_ip = get_server_public_ip()
    log_rows = ""
    for log in stats["logs"][::-1]:
        color = "bg-green-900 text-green-300" if log["status"] == "Success" else "bg-red-900 text-red-300"
        log_rows += f"""
        <tr>
            <td class="p-4 text-sm font-mono text-slate-400">{log['time']}</td>
            <td class="p-4 font-mono text-blue-400">{log['ip']}</td>
            <td class="p-4 font-medium">{log['topic']}</td>
            <td class="p-4"><span class="px-3 py-1 rounded-full text-[10px] font-bold uppercase {color}">{log['status']}</span></td>
        </tr>
        """

    admin_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8"><title>SnapStudy | Admin Panel</title>{CSS_JS}
    </head>
    <body class="bg-slate-900 text-white min-h-screen p-8 font-sans">
        <div class="max-w-6xl mx-auto">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-10 gap-4">
                <div>
                    <h1 class="text-4xl font-black text-blue-500 tracking-tight">ADMIN PANEL</h1>
                    <p class="text-slate-500 text-sm">Real-time System Monitoring</p>
                </div>
                <div class="bg-slate-800 px-6 py-3 rounded-2xl border border-slate-700 shadow-lg">
                    <p class="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Server Public IP</p>
                    <p class="text-xl font-mono text-blue-400 font-bold">{server_ip}</p>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
                <div class="bg-slate-800 p-8 rounded-3xl border border-slate-700">
                    <p class="text-slate-500 text-xs font-bold uppercase mb-1">Total Hits</p>
                    <h2 class="text-5xl font-black">{stats['total_requests']}</h2>
                </div>
                <div class="bg-slate-800 p-8 rounded-3xl border border-green-900/50">
                    <p class="text-green-600 text-xs font-bold uppercase mb-1">Successful</p>
                    <h2 class="text-5xl font-black text-green-500">{stats['success_count']}</h2>
                </div>
                <div class="bg-slate-800 p-8 rounded-3xl border border-red-900/50">
                    <p class="text-red-600 text-xs font-bold uppercase mb-1">Failed</p>
                    <h2 class="text-5xl font-black text-red-500">{stats['failed_count']}</h2>
                </div>
            </div>

            <div class="bg-slate-800 rounded-3xl overflow-hidden border border-slate-700 shadow-2xl">
                <div class="bg-slate-700/50 p-5 border-b border-slate-700"><h3 class="font-bold">Recent Activity Logs</h3></div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left">
                        <thead class="bg-slate-800/50 text-slate-500 text-[10px] uppercase font-bold">
                            <tr><th class="p-4">Timestamp</th><th class="p-4">User IP</th><th class="p-4">Request Topic</th><th class="p-4">Outcome</th></tr>
                        </thead>
                        <tbody class="divide-y divide-slate-700">{log_rows}</tbody>
                    </table>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(admin_html)

@app.route('/api/generate')
def generate_api():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    today = str(date.today())
    if ip not in user_limits: user_limits[ip] = {}
    if user_limits[ip].get(today, 0) >= DAILY_LIMIT:
        return jsonify({"error": "Limit 3/3 Reached! Come back tomorrow."}), 403

    topic = request.args.get('topic')
    aid = uuid.uuid4().hex
    scraper = cloudscraper.create_scraper()
    stats["total_requests"] += 1
    
    try:
        init = scraper.post("https://notegpt.io/api/v2/pdf-to-video", json={
            "source_url": "", "source_type": "text", "input_prompt": topic,
            "setting": {"frame_size": "16:9", "duration": 1, "lang": "en", "gen_flow": "edit_script", "add_watermark": False}
        }, headers={'User-Agent': request.headers.get('User-Agent'), 'Cookie': f'anonymous_user_id={aid}'}).json()
        
        cid = init.get("data", {}).get("conversation_id")
        time.sleep(7)
        script_res = scraper.get(f"https://notegpt.io/api/v2/pdf-to-video/script/get?conversation_id={cid}", cookies={'anonymous_user_id': aid}).json()
        script_data = script_res.get("data", {})
        
        scraper.post("https://notegpt.io/api/v2/pdf-to-video/script/edit", 
                     json={"conversation_id": cid, "script_data": json.dumps(script_data)}, cookies={'anonymous_user_id': aid})

        user_limits[ip][today] = user_limits[ip].get(today, 0) + 1
        stats["success_count"] += 1
        stats["logs"].append({"ip": ip, "topic": topic, "time": time.strftime("%H:%M:%S"), "status": "Success"})
        return jsonify({"scenes": script_data.get("scenes", []), "cid": cid, "anon_id": aid})
    except:
        stats["failed_count"] += 1
        stats["logs"].append({"ip": ip, "topic": topic, "time": time.strftime("%H:%M:%S"), "status": "Failed"})
        return jsonify({"error": "System overloaded. Try again."}), 500

@app.route('/api/status')
def status_api():
    cid, aid = request.args.get('cid'), request.args.get('aid')
    res = cloudscraper.create_scraper().get(f"https://notegpt.io/api/v2/pdf-to-video/status?conversation_id={cid}", cookies={'anonymous_user_id': aid}).json()
    data = res.get("data", {})
    return jsonify({"status": data.get("status"), "video_url": data.get("cdn_video_url") or data.get("video_url"), "step": data.get("step")})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
