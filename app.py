from flask import Flask, render_template_string, request, jsonify, session
import cloudscraper
import uuid
import time
import json
from datetime import date

app = Flask(__name__)
app.secret_key = "snapstudy_secret_key_99" # Session security ke liye

# --- DATABASE (In-Memory for demo, replace with JSON/SQLite for persistence) ---
stats = {
    "total_requests": 0,
    "success_count": 0,
    "failed_count": 0,
    "logs": [] # Format: {ip, topic, status, time}
}
user_limits = {} # Format: {ip: {date: count}}

# --- SETTINGS ---
ADMIN_PASS = "admin123"
DAILY_LIMIT = 3

# --- UI TEMPLATES ---
BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SnapStudy AI - Professional</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>.loader { border-top-color: #3b82f6; animation: spin 1s linear infinite; } @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style>
</head>
<body class="bg-slate-900 text-white min-h-screen">
    {% block content %}{% endblock %}
</body>
</html>
"""

INDEX_HTML = """
{% extends "BASE_HTML" %}
{% block content %}
<div class="container mx-auto px-4 py-12">
    <div class="text-center mb-10">
        <h1 class="text-5xl font-extrabold text-blue-500 mb-2">SnapStudy AI</h1>
        <p class="text-slate-400">Daily Limit: <span class="text-blue-400">{{ limit_left }}/3</span></p>
    </div>
    <div class="max-w-xl mx-auto bg-slate-800 p-6 rounded-2xl shadow-xl border border-slate-700">
        <div class="flex gap-2">
            <input type="text" id="topic" placeholder="Enter topic..." class="w-full p-4 bg-slate-700 rounded-xl outline-none border border-slate-600 focus:border-blue-500">
            <button onclick="generate()" id="btn" class="bg-blue-600 hover:bg-blue-700 px-6 rounded-xl font-bold transition">Start</button>
        </div>
        <div id="status-box" class="mt-4 hidden flex items-center gap-3 text-blue-400">
            <div class="loader w-5 h-5 border-2 border-slate-500 rounded-full"></div>
            <span id="status-text">Processing...</span>
        </div>
    </div>
    <div id="results" class="max-w-3xl mx-auto mt-10 space-y-6"></div>
</div>
<script>
async function generate() {
    const topic = document.getElementById('topic').value;
    const btn = document.getElementById('btn');
    const statusBox = document.getElementById('status-box');
    const results = document.getElementById('results');

    if(!topic) return;
    btn.disabled = true; statusBox.classList.remove('hidden'); results.innerHTML = '';

    try {
        const res = await fetch(`/api/generate?topic=${encodeURIComponent(topic)}`);
        const data = await res.json();
        if(data.error) throw new Error(data.error);

        data.scenes.forEach(s => {
            results.innerHTML += `<div class="bg-slate-800 p-5 rounded-xl border border-slate-700">
                <h3 class="text-lg font-bold text-blue-400 mb-2">${s.scene_title}</h3>
                <div class="flex flex-col md:flex-row gap-4">
                    <img src="${s.scene_image[0]}" class="w-full md:w-48 rounded-lg">
                    <p class="text-slate-300 text-sm">${s.scene_text}</p>
                </div>
            </div>`;
        });
        pollVideo(data.cid, data.anon_id);
    } catch(e) {
        alert(e.message); btn.disabled = false; statusBox.classList.add('hidden');
    }
}
async function pollVideo(cid, aid) {
    const statusText = document.getElementById('status-text');
    while(true) {
        const res = await fetch(`/api/status?cid=${cid}&aid=${aid}`);
        const data = await res.json();
        if(data.status === "success") {
            document.getElementById('results').innerHTML = `<div class="bg-blue-600/20 border border-blue-500 p-4 rounded-xl mb-4 text-center">
                <video controls class="w-full rounded-lg mb-2"><source src="${data.video_url}"></video>
                <p class="font-bold">✨ No-Watermark Lesson Ready</p>
            </div>` + document.getElementById('results').innerHTML;
            document.getElementById('status-box').classList.add('hidden');
            document.getElementById('btn').disabled = false;
            break;
        }
        statusText.innerText = "Live: " + (data.step || "Rendering").replace(/_/g, ' ');
        await new Promise(r => setTimeout(r, 10000));
    }
}
</script>
{% endblock %}
"""

ADMIN_HTML = """
{% extends "BASE_HTML" %}
{% block content %}
<div class="p-8">
    <div class="flex justify-between items-center mb-8">
        <h1 class="text-3xl font-bold text-blue-500">Admin Control Panel</h1>
        <div class="text-right">
            <p class="text-slate-400">Server IP: <span class="text-white font-mono">{{ server_ip }}</span></p>
        </div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8 text-center">
        <div class="bg-slate-800 p-6 rounded-xl border border-slate-700">
            <p class="text-slate-400">Total Requests</p><h2 class="text-4xl font-bold">{{ stats.total_requests }}</h2>
        </div>
        <div class="bg-slate-800 p-6 rounded-xl border border-green-900">
            <p class="text-slate-400 text-green-500">Success</p><h2 class="text-4xl font-bold text-green-500">{{ stats.success_count }}</h2>
        </div>
        <div class="bg-slate-800 p-6 rounded-xl border border-red-900">
            <p class="text-slate-400 text-red-500">Failed</p><h2 class="text-4xl font-bold text-red-500">{{ stats.failed_count }}</h2>
        </div>
    </div>
    <div class="bg-slate-800 rounded-xl overflow-hidden border border-slate-700">
        <table class="w-full text-left">
            <thead class="bg-slate-700 text-slate-300">
                <tr><th class="p-4">Time</th><th class="p-4">User IP</th><th class="p-4">Topic</th><th class="p-4">Status</th></tr>
            </thead>
            <tbody class="divide-y divide-slate-700">
                {% for log in stats.logs[::-1] %}
                <tr>
                    <td class="p-4 text-sm">{{ log.time }}</td>
                    <td class="p-4 font-mono text-blue-300">{{ log.ip }}</td>
                    <td class="p-4">{{ log.topic }}</td>
                    <td class="p-4"><span class="px-3 py-1 rounded-full text-xs {{ 'bg-green-900 text-green-300' if log.status=='Success' else 'bg-red-900 text-red-300' }}">{{ log.status }}</span></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
"""

# --- UTILS ---
def get_user_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)

def check_limit(ip):
    today = str(date.today())
    if ip not in user_limits: user_limits[ip] = {}
    if today not in user_limits[ip]: user_limits[ip][today] = 0
    return user_limits[ip][today]

# --- ROUTES ---
@app.route('/')
def home():
    ip = get_user_ip()
    used = check_limit(ip)
    return render_template_string(INDEX_HTML, limit_left=(DAILY_LIMIT - used), BASE_HTML=BASE_HTML)

@app.route('/admin')
def admin():
    # Simple pass check via query: /admin?pass=admin123
    if request.args.get('pass') != ADMIN_PASS:
        return "Unauthorized Access", 403
    server_ip = request.host.split(':')[0]
    return render_template_string(ADMIN_HTML, stats=stats, server_ip=server_ip, BASE_HTML=BASE_HTML)

@app.route('/api/generate')
def generate_api():
    ip = get_user_ip()
    today = str(date.today())
    used = check_limit(ip)
    
    if used >= DAILY_LIMIT:
        return jsonify({"error": "Daily limit 3/3 reached! Kal aana bhai."}), 403

    topic = request.args.get('topic')
    aid = uuid.uuid4().hex
    scraper = cloudscraper.create_scraper()
    
    stats["total_requests"] += 1
    log_entry = {"ip": ip, "topic": topic, "time": time.strftime("%H:%M:%S"), "status": "Pending"}
    
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

        # Update stats
        user_limits[ip][today] += 1
        log_entry["status"] = "Success"
        stats["success_count"] += 1
        stats["logs"].append(log_entry)
        
        return jsonify({"scenes": script_data.get("scenes", []), "cid": cid, "anon_id": aid})
    except:
        log_entry["status"] = "Failed"
        stats["failed_count"] += 1
        stats["logs"].append(log_entry)
        return jsonify({"error": "Bypass Failed. Retry."}), 500

@app.route('/api/status')
def status_api():
    cid = request.args.get('cid')
    aid = request.args.get('aid')
    res = cloudscraper.create_scraper().get(f"https://notegpt.io/api/v2/pdf-to-video/status?conversation_id={cid}", cookies={'anonymous_user_id': aid}).json()
    data = res.get("data", {})
    return jsonify({"status": data.get("status"), "video_url": data.get("cdn_video_url") or data.get("video_url"), "step": data.get("step")})

if __name__ == '__main__':
    app.run(debug=True)
