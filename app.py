import os
import uuid
import time
import json
import random
from datetime import datetime
import threading

from flask import Flask, request, render_template_string, jsonify
import cloudscraper
import requests

app = Flask(__name__)

# =========================
# Global in-memory storage
# =========================
stats = {
    "logs": [],
    "ip_requests": {},
    "jobs": {}  # {job_id: {status, video_url, error, topic}}
}

# ==============
# Config
# ==============
NOTEGPT_BASE = "https://notegpt.io/api/v2/pdf-to-video"


# =========================
# Utility functions
# =========================
def get_real_ip(req):
    xff = req.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return req.remote_addr or "unknown"


def check_rate_limit(ip):
    today = datetime.utcnow().date().isoformat()
    rec = stats["ip_requests"].get(ip)
    if not rec or rec.get("date") != today:
        stats["ip_requests"][ip] = {"date": today, "count": 0}
        rec = stats["ip_requests"][ip]
    if rec["count"] >= 3:
        return False
    rec["count"] += 1
    return True


def log_request(ip, topic, status, error_details=""):
    stats["logs"].append({
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "ip": ip,
        "topic": topic,
        "status": status,
        "error": error_details
    })


def create_scraper():
    scraper = cloudscraper.create_scraper()
    return scraper


def get_ghost_headers():
    fake_ip = f"{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}"
    return {
        'User-Agent': "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        'Accept': 'application/json, text/plain, */*',
        'X-Forwarded-For': fake_ip,
        'Origin': 'https://notegpt.io',
        'Referer': 'https://notegpt.io/ai-animation-maker',
        'X-Requested-With': 'mark.via.gp'
    }


def get_fresh_cookies():
    anon_id = uuid.uuid4().hex
    return {'anonymous_user_id': anon_id}


def notegpt_init(scraper, topic):
    headers = get_ghost_headers()
    cookies = get_fresh_cookies()
    
    payload = {
        "source_url": "",
        "source_type": "text",
        "input_prompt": topic,
        "setting": {
            "frame_size": "16:9",
            "duration": 1,
            "voice_key": "9e12f68d85f347808f76637a",
            "no_watermark": True,
            "lang": "en",
            "gen_flow": "edit_script"
        }
    }
    
    resp = scraper.post(NOTEGPT_BASE, headers=headers, cookies=cookies, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    
    if not isinstance(data, dict):
        raise RuntimeError(f"Init API returned non-dict response: {data}")
    
    if data.get("code") != 100000:
        raise RuntimeError(f"NoteGPT API Error: {data.get('message')} (Code: {data.get('code')})")
    
    cid = data.get("data", {}).get("conversation_id")
    if not cid:
        raise RuntimeError(f"conversation_id missing in init response: {data}")
    
    return cid, headers, cookies


def wait_for_script(scraper, cid, headers, cookies, timeout_sec=30):
    start_time = time.time()
    
    while time.time() - start_time < timeout_sec:
        try:
            resp = scraper.get(
                f"{NOTEGPT_BASE}/status",
                params={"conversation_id": cid},
                headers=headers,
                cookies=cookies,
                timeout=30
            )
            data = resp.json().get("data", {})
            step = data.get("step")
            
            if step in ["edit_script", "pause"]:
                return True
            
            time.sleep(3)
        except Exception:
            time.sleep(3)
    
    return True


def fetch_script_data(scraper, cid, headers, cookies):
    resp = scraper.get(
        f"{NOTEGPT_BASE}/script/get",
        params={"conversation_id": cid},
        headers=headers,
        cookies=cookies,
        timeout=60
    )
    resp.raise_for_status()
    data = resp.json()
    
    if not isinstance(data, dict):
        raise RuntimeError(f"Fetch script API returned non-dict response: {data}")
    
    script_data = data.get("data")
    if not script_data:
        raise RuntimeError(f"script_data missing in fetch response: {data}")
    
    return script_data


def trigger_video_render(scraper, cid, script_data, headers, cookies):
    for scene in script_data.get('scenes', []):
        scene_text = scene.get('scene_text', '')
        if " | By Chirag Rathi" not in scene_text:
            scene['scene_text'] = scene_text.rstrip() + " | By Chirag Rathi"
    
    payload = {
        "conversation_id": cid,
        "script_data": json.dumps(script_data),
        "is_force_save": True
    }
    
    resp = scraper.post(
        f"{NOTEGPT_BASE}/script/edit",
        headers=headers,
        cookies=cookies,
        json=payload,
        timeout=60
    )
    resp.raise_for_status()
    return resp.json()


def poll_final_video(scraper, cid, headers, cookies, timeout_sec=300):
    start_time = time.time()
    
    while time.time() - start_time < timeout_sec:
        try:
            resp = scraper.get(
                f"{NOTEGPT_BASE}/status",
                params={"conversation_id": cid},
                headers=headers,
                cookies=cookies,
                timeout=30
            )
            data = resp.json().get("data", {})
            status = data.get("status")
            
            if status == "success":
                video_url = data.get("cdn_video_url") or data.get("video_url")
                if not video_url:
                    raise RuntimeError(f"Video status success but no URL found: {data}")
                return video_url
            
            if status == "failed":
                raise RuntimeError(f"Video rendering failed on server: {data}")
            
            time.sleep(5)
        except requests.exceptions.RequestException:
            time.sleep(5)
    
    raise TimeoutError(f"Polling timed out after {timeout_sec}s")


# Background worker function
def process_video_generation(job_id, topic, user_ip):
    stats["jobs"][job_id] = {
        "status": "processing",
        "video_url": None,
        "error": None,
        "topic": topic,
        "progress": "Initializing..."
    }
    
    try:
        scraper = create_scraper()
        
        stats["jobs"][job_id]["progress"] = "Getting conversation ID..."
        cid, headers, cookies = notegpt_init(scraper, topic)
        
        stats["jobs"][job_id]["progress"] = "Waiting for script generation..."
        wait_for_script(scraper, cid, headers, cookies)
        
        stats["jobs"][job_id]["progress"] = "Fetching script data..."
        script_data = fetch_script_data(scraper, cid, headers, cookies)
        
        stats["jobs"][job_id]["progress"] = "Triggering video render..."
        trigger_video_render(scraper, cid, script_data, headers, cookies)
        
        stats["jobs"][job_id]["progress"] = "Rendering video (this may take 2-3 minutes)..."
        video_url = poll_final_video(scraper, cid, headers, cookies)
        
        stats["jobs"][job_id]["status"] = "completed"
        stats["jobs"][job_id]["video_url"] = video_url
        stats["jobs"][job_id]["progress"] = "Done!"
        log_request(user_ip, topic, "success", "")
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        stats["jobs"][job_id]["status"] = "failed"
        stats["jobs"][job_id]["error"] = error_msg
        stats["jobs"][job_id]["progress"] = "Failed"
        log_request(user_ip, topic, "fail", error_msg)


# =========================
# HTML Template
# =========================
TEMPLATE = """
<!doctype html>
<html lang="en" class="h-full bg-slate-950">
<head>
  <meta charset="utf-8">
  <title>SnapStudy AI Pro - Text to Video</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            neon: {
              pink: '#ff4bcb',
              green: '#39ff14',
              blue: '#00e5ff',
              yellow: '#ffe700'
            }
          }
        }
      }
    };
  </script>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
    }
    .cyber-border {
      border-image: linear-gradient(135deg, #ff4bcb, #00e5ff, #39ff14) 1;
      border-width: 1px;
      border-style: solid;
    }
    .scanlines {
      background-image: linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px);
      background-size: 100% 2px;
    }
    .glow {
      box-shadow: 0 0 10px rgba(0,229,255,0.4), 0 0 30px rgba(255,75,203,0.3);
    }
  </style>
</head>
<body class="h-full text-slate-100 scanlines">
  <div class="min-h-screen flex flex-col items-center justify-center px-4 py-8">
    <div class="w-full max-w-4xl cyber-border rounded-xl bg-slate-900/80 backdrop-blur-md glow">
      <div class="border-b border-slate-700 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 class="text-xl md:text-2xl font-semibold tracking-tight">
            <span class="text-neon-pink">Snap</span><span class="text-neon-blue">Study</span>
            <span class="text-neon-green">AI</span> <span class="text-slate-200">Pro</span>
          </h1>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            Android-mimic Text-to-Video automation with branded scripts.
          </p>
        </div>
        <div class="text-right">
          <span class="inline-flex items-center px-2 py-1 text-[10px] font-semibold rounded-full bg-slate-800 text-neon-yellow border border-slate-600">
            LIVE • BETA
          </span>
          <p class="mt-1 text-[10px] text-slate-500">
            Powered by NoteGPT workflow
          </p>
        </div>
      </div>

      <div class="px-6 py-6 grid gap-6 md:grid-cols-2">
        <div class="space-y-4">
          <form id="topicForm" class="space-y-4" method="POST" action="/">
            <div>
              <label for="topic" class="block text-xs font-semibold text-slate-300 mb-1">
                Topic / Prompt
              </label>
              <textarea id="topic" name="topic" rows="4"
                class="w-full rounded-md bg-slate-950/70 border border-slate-700/80 text-sm px-3 py-2 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-neon-blue focus:border-neon-blue"
                placeholder="Explain Quantum Computing for beginners, generate an explainer video..."
                required>{{ topic or "" }}</textarea>
            </div>

            {% if rate_limited %}
            <div class="text-xs text-red-400 font-semibold border border-red-500/60 bg-red-950/50 rounded-md px-3 py-2">
              Daily limit reached for your IP. Please try again tomorrow.
            </div>
            {% endif %}

            <div class="flex items-center justify-between">
              <button type="submit"
                class="inline-flex items-center px-4 py-2 rounded-md bg-gradient-to-r from-neon-pink to-neon-blue text-slate-950 text-xs font-semibold shadow-md hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-neon-pink focus:ring-offset-slate-900 disabled:opacity-40 disabled:cursor-not-allowed"
                {% if rate_limited %}disabled{% endif %}>
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m0 0A7 7 0 0112 5h0a7 7 0 016.418 4.027M4.582 9H9m11 11v-5h-.581m0 0A7 7 0 0112 19h0a7 7 0 01-6.418-4.027M19.418 15H15" />
                </svg>
                Generate Video
              </button>
              <p class="text-[10px] text-slate-500">
                3 requests/day per IP enforced.
              </p>
            </div>
          </form>
        </div>

        <div class="space-y-4">
          <div class="border border-slate-700 rounded-md bg-slate-950/60 p-3">
            <div class="flex items-center justify-between mb-2">
              <h2 class="text-xs font-semibold text-slate-200">Render Status</h2>
              <span class="text-[11px] text-slate-500" id="statusText">
                {% if job_id %}Processing...{% else %}Ready{% endif %}
              </span>
            </div>
            
            <div id="videoContainer">
              {% if job_id %}
              <div class="text-xs text-slate-400 mb-2">
                <div class="flex items-center space-x-2">
                  <div class="animate-spin h-4 w-4 border-2 border-neon-blue border-t-transparent rounded-full"></div>
                  <span id="progressText">Starting...</span>
                </div>
              </div>
              <div class="text-[10px] text-slate-500 mt-2">
                Job ID: <code class="bg-slate-900 px-1 py-0.5 rounded">{{ job_id }}</code>
              </div>
              {% else %}
              <div class="text-xs text-slate-500">
                Enter a topic and click "Generate Video" to start. Processing takes 2-3 minutes.
              </div>
              {% endif %}
            </div>
          </div>

          <div class="border border-slate-700 rounded-md bg-slate-950/60 p-3">
            <h3 class="text-xs font-semibold text-slate-200 mb-1">Session Info</h3>
            <p class="text-[11px] text-slate-400">
              Your IP: <span class="text-neon-blue">{{ user_ip }}</span>
            </p>
            <p class="text-[11px] text-slate-500 mt-1">
              Fresh UUID and headers generated per request for maximum reliability.
            </p>
          </div>
        </div>
      </div>

      <div class="border-t border-slate-800 px-6 py-3 text-[10px] text-slate-500 flex items-center justify-between">
        <span>SnapStudy AI Pro &copy; {{ year }} • Internal tooling stub for NoteGPT text-to-video automation.</span>
        <span class="text-slate-600">
          Admin: <code class="bg-slate-900 px-1.5 py-0.5 rounded border border-slate-700 text-[10px]">/XYZ</code>
        </span>
      </div>
    </div>
  </div>

  {% if job_id %}
  <script>
    const jobId = "{{ job_id }}";
    
    function checkStatus() {
      fetch('/status/' + jobId)
        .then(res => res.json())
        .then(data => {
          const statusText = document.getElementById('statusText');
          const progressText = document.getElementById('progressText');
          const videoContainer = document.getElementById('videoContainer');
          
          progressText.textContent = data.progress || 'Processing...';
          
          if (data.status === 'completed') {
            statusText.textContent = 'Completed';
            statusText.className = 'text-[11px] text-neon-green';
            videoContainer.innerHTML = `
              <video class="w-full rounded-md border border-slate-700 bg-black" controls playsinline>
                <source src="${data.video_url}" type="video/mp4">
              </video>
              <p class="mt-2 text-[10px] text-slate-400">
                Branded script: <span class="text-neon-yellow">| By Chirag Rathi</span> appended to scenes.
              </p>
              <a href="${data.video_url}" target="_blank" class="inline-flex mt-2 items-center px-2.5 py-1.5 rounded-md bg-slate-800 text-[11px] text-neon-blue border border-slate-600 hover:bg-slate-700">
                Open video in new tab
              </a>
            `;
          } else if (data.status === 'failed') {
            statusText.textContent = 'Failed';
            statusText.className = 'text-[11px] text-red-400';
            videoContainer.innerHTML = `
              <div class="text-xs text-red-400 border border-red-500/50 bg-red-950/60 rounded-md px-3 py-2">
                <div class="font-semibold mb-1">Error</div>
                <pre class="text-[11px] whitespace-pre-wrap">${data.error}</pre>
              </div>
            `;
          } else {
            setTimeout(checkStatus, 3000);
          }
        })
        .catch(err => {
          console.error('Status check failed:', err);
          setTimeout(checkStatus, 5000);
        });
    }
    
    checkStatus();
  </script>
  {% endif %}
</body>
</html>
"""


ADMIN_TEMPLATE = """
<!doctype html>
<html lang="en" class="h-full bg-slate-950">
<head>
  <meta charset="utf-8">
  <title>SnapStudy AI Pro - Admin</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            neon: {
              pink: '#ff4bcb',
              green: '#39ff14',
              blue: '#00e5ff',
              yellow: '#ffe700'
            }
          }
        }
      }
    };
  </script>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
    }
    .cyber-border {
      border-image: linear-gradient(135deg, #ff4bcb, #00e5ff, #39ff14) 1;
      border-width: 1px;
      border-style: solid;
    }
    .scanlines {
      background-image: linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px);
      background-size: 100% 2px;
    }
  </style>
</head>
<body class="h-full text-slate-100 scanlines">
  <div class="min-h-screen flex flex-col items-center justify-center px-4 py-8">
    <div class="w-full max-w-5xl cyber-border rounded-xl bg-slate-900/85 backdrop-blur-md">
      <div class="border-b border-slate-700 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 class="text-xl font-semibold tracking-tight text-neon-yellow">
            SnapStudy AI Pro - Admin
          </h1>
          <p class="text-xs text-slate-400 mt-1">
            Server diagnostics and request telemetry.
          </p>
        </div>
      </div>

      <div class="px-6 py-4 space-y-6">
        <div class="border border-slate-700 rounded-md bg-slate-950/70 p-3">
          <h2 class="text-sm font-semibold text-slate-200 mb-1">Server Public IP</h2>
          <p class="text-xs text-neon-blue">{{ server_ip }}</p>
          <p class="text-[11px] text-slate-500 mt-1">
            Pulled from https://api.ipify.org for proxy / networking verification.
          </p>
        </div>

        <div class="border border-slate-700 rounded-md bg-slate-950/70 p-3">
          <div class="flex items-center justify-between mb-2">
            <h2 class="text-sm font-semibold text-slate-200">Request Log</h2>
            <span class="text-[11px] text-slate-500">Total entries: {{ logs|length }}</span>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-full text-[11px]">
              <thead class="bg-slate-900">
                <tr>
                  <th class="px-3 py-2 text-left font-semibold border-b border-slate-700">Timestamp</th>
                  <th class="px-3 py-2 text-left font-semibold border-b border-slate-700">User IP</th>
                  <th class="px-3 py-2 text-left font-semibold border-b border-slate-700">Topic</th>
                  <th class="px-3 py-2 text-left font-semibold border-b border-slate-700">Status</th>
                  <th class="px-3 py-2 text-left font-semibold border-b border-slate-700">Error Details</th>
                </tr>
              </thead>
              <tbody>
                {% if logs %}
                  {% for row in logs|reverse %}
                  <tr class="border-b border-slate-800 hover:bg-slate-900/70">
                    <td class="px-3 py-1.5 align-top text-slate-300">{{ row.timestamp }}</td>
                    <td class="px-3 py-1.5 align-top text-neon-blue">{{ row.ip }}</td>
                    <td class="px-3 py-1.5 align-top text-slate-200 max-w-xs truncate" title="{{ row.topic }}">{{ row.topic }}</td>
                    <td class="px-3 py-1.5 align-top">
                      {% if row.status == 'success' %}
                      <span class="inline-flex items-center px-2 py-0.5 rounded-full bg-emerald-900/60 text-emerald-300 border border-emerald-500/70">SUCCESS</span>
                      {% else %}
                      <span class="inline-flex items-center px-2 py-0.5 rounded-full bg-red-900/60 text-red-300 border border-red-500/70">FAIL</span>
                      {% endif %}
                    </td>
                    <td class="px-3 py-1.5 align-top text-slate-400 max-w-xs truncate" title="{{ row.error }}">{{ row.error }}</td>
                  </tr>
                  {% endfor %}
                {% else %}
                  <tr>
                    <td colspan="5" class="px-3 py-3 text-center text-slate-500">No logged requests yet.</td>
                  </tr>
                {% endif %}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="border-t border-slate-800 px-6 py-3 text-[10px] text-slate-500 flex items-center justify-between">
        <span>SnapStudy AI Pro &copy; {{ year }} • Admin diagnostics.</span>
        <span class="text-slate-600">Route: /XYZ</span>
      </div>
    </div>
  </div>
</body>
</html>
"""


# =========================
# Main routes
# =========================
@app.route("/", methods=["GET", "POST"])
def index():
    user_ip = get_real_ip(request)
    topic = ""
    job_id = None
    rate_limited = False

    if request.method == "POST":
        topic = (request.form.get("topic") or "").strip()
        if not topic:
            pass
        else:
            if not check_rate_limit(user_ip):
                rate_limited = True
            else:
                job_id = str(uuid.uuid4())
                thread = threading.Thread(
                    target=process_video_generation,
                    args=(job_id, topic, user_ip)
                )
                thread.daemon = True
                thread.start()

    return render_template_string(
        TEMPLATE,
        topic=topic,
        job_id=job_id,
        user_ip=user_ip,
        rate_limited=rate_limited,
        year=datetime.utcnow().year,
    )


@app.route("/status/<job_id>", methods=["GET"])
def job_status(job_id):
    job = stats["jobs"].get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify(job)


@app.route("/XYZ", methods=["GET"])
def admin_page():
    try:
        server_ip = requests.get("https://api.ipify.org", timeout=10).text.strip()
    except Exception as e:
        server_ip = f"Error fetching IP: {type(e).__name__}: {str(e)}"
    return render_template_string(
        ADMIN_TEMPLATE,
        server_ip=server_ip,
        logs=stats["logs"],
        year=datetime.utcnow().year,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
