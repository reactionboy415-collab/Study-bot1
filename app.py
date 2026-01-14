from flask import Flask, render_template_string, request, jsonify
import cloudscraper
import uuid
import time
import json
import os
import requests
import random
import traceback
from datetime import date

app = Flask(__name__)

# --- CONFIG & STATS ---
stats = {"total_requests": 0, "success_count": 0, "failed_count": 0, "logs": []}
ADMIN_PASS = "admin123"
BRAND_LOGO = "https://placehold.jp/24/000000/ffffff/200x50.png?text=Chirag%20Rathi"

CSS_JS = """
<script src="https://cdn.tailwindcss.com"></script>
<style>
    .loader { border-top-color: #3b82f6; animation: spin 1s linear infinite; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    .glass { background: #0f172a; border: 1px solid #1e293b; border-radius: 24px; }
</style>
"""

@app.route('/')
def home():
    return render_template_string(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>SnapStudy Debug Mode</title>{CSS_JS}</head>
    <body class="bg-[#020617] text-white min-h-screen flex items-center justify-center p-6">
        <div class="max-w-md w-full">
            <h1 class="text-4xl font-black mb-8 italic text-blue-500 text-center">SnapStudy Debug</h1>
            <div class="glass p-8 shadow-2xl">
                <input type="text" id="topic" placeholder="Topic..." class="w-full p-4 bg-slate-900 rounded-xl mb-4 border border-slate-700 outline-none">
                <button onclick="generate()" id="btn" class="w-full bg-blue-600 p-4 rounded-xl font-bold uppercase hover:bg-blue-500 transition-all">Start Gen</button>
                <div id="status" class="mt-4 hidden flex items-center justify-center gap-2 text-blue-400 font-bold text-xs">
                    <div class="loader w-4 h-4 border-2 border-slate-700 rounded-full"></div>
                    <span id="st-text">Processing...</span>
                </div>
            </div>
            <div id="debug-info" class="mt-4 text-[10px] text-red-400 font-mono break-words"></div>
            <div id="video-res" class="mt-8"></div>
        </div>
        <script>
        async function generate() {{
            const t = document.getElementById('topic').value;
            const debugBox = document.getElementById('debug-info');
            debugBox.innerText = ""; // Clear old errors
            if(!t) return;
            document.getElementById('btn').disabled = true;
            document.getElementById('status').classList.remove('hidden');
            try {{
                const res = await fetch(`/api/generate?topic=${{encodeURIComponent(t)}}`);
                const data = await res.json();
                if(data.error) {{
                    debugBox.innerText = "SERVER ERROR: " + data.details;
                    throw new Error(data.error);
                }}
                poll(data.cid, data.aid);
            }} catch(e) {{ 
                console.error(e);
                document.getElementById('btn').disabled = false;
                document.getElementById('status').classList.add('hidden');
            }}
        }}
        async function poll(cid, aid) {{
            const st = document.getElementById('st-text');
            const debugBox = document.getElementById('debug-info');
            while(true) {{
                try {{
                    const res = await fetch(`/api/status?cid=${{cid}}&aid=${{aid}}`);
                    const data = await res.json();
                    if(data.status === "success") {{
                        document.getElementById('video-res').innerHTML = `<video controls class="w-full rounded-2xl border-2 border-blue-500 shadow-2xl"><source src="${{data.video_url}}"></video>`;
                        reset(); break;
                    }} else if (data.status === "failed") {{
                        debugBox.innerText = "POLLING ERROR: Render Failed on NoteGPT side.";
                        reset(); break;
                    }}
                    st.innerText = (data.step || "Rendering").toUpperCase();
                }} catch(err) {{
                    debugBox.innerText = "POLLING FAILED: Check Connection.";
                    reset(); break;
                }}
                await new Promise(r => setTimeout(r, 8000));
            }}
        }}
        function reset() {{
            document.getElementById('btn').disabled = false;
            document.getElementById('status').classList.add('hidden');
        }}
        </script>
    </body>
    </html>
    """)

@app.route('/api/generate')
def generate_api():
    topic = request.args.get('topic')
    aid = uuid.uuid4().hex
    scraper = cloudscraper.create_scraper()
    
    payload = {
        "source_url": "", "source_type": "text", "input_prompt": topic,
        "setting": {
            "frame_size": "16:9", "duration": 1, "voice_key": "9e12f68d85f347808f76637a",
            "no_watermark": True, "background_color": "#000000", "title_text_color": "#FFFFFF",
            "body_text_color": "#E7EAFA", "brand_logo_url": BRAND_LOGO,
            "brand_logo_position": "bottom-right", "lang": "en", "gen_flow": "edit_script"
        }
    }

    headers = {
        "host": "notegpt.io",
        "user-agent": "Mozilla/5.0 (Linux; Android 12; LAVA Blaze) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.7499.146 Mobile Safari/537.36",
        "accept": "application/json, text/plain, */*",
        "origin": "https://notegpt.io",
        "x-requested-with": "mark.via.gp"
    }

    try:
        stats["total_requests"] += 1
        r = scraper.post("https://notegpt.io/api/v2/pdf-to-video", json=payload, headers=headers, cookies={'anonymous_user_id': aid})
        
        # Debugging Response
        if r.status_code != 200:
            raise Exception(f"NoteGPT HTTP {r.status_code}: {r.text[:100]}")
            
        data = r.json()
        cid = data.get("data", {}).get("conversation_id")
        
        if not cid:
            raise Exception(f"No CID returned. Full Resp: {json.dumps(data)}")

        stats["success_count"] += 1
        stats["logs"].append({"ip": request.remote_addr, "topic": topic, "time": time.strftime("%H:%M:%S"), "status": "Success"})
        return jsonify({"cid": cid, "aid": aid})

    except Exception as e:
        full_error = str(e)
        stats["failed_count"] += 1
        stats["logs"].append({"ip": request.remote_addr, "topic": topic, "time": time.strftime("%H:%M:%S"), "status": "Failed", "error": full_error})
        return jsonify({"error": "Generation Failed", "details": full_error}), 500

@app.route('/api/status')
def status_api():
    cid, aid = request.args.get('cid'), request.args.get('aid')
    try:
        r = cloudscraper.create_scraper().get(f"https://notegpt.io/api/v2/pdf-to-video/status?conversation_id={cid}", cookies={'anonymous_user_id': aid})
        return jsonify(r.json().get("data", {}))
    except Exception as e:
        return jsonify({"status": "error", "details": str(e)}), 500

@app.route('/admin')
def admin():
    if request.args.get('pass') != ADMIN_PASS: return "Denied", 403
    return jsonify(stats)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
