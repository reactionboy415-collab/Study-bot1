import os
import uuid
import time
from datetime import datetime

from flask import Flask, request, render_template_string
import cloudscraper
import requests

app = Flask(__name__)

# =========================
# Global in-memory storage
# =========================
stats = {
    "logs": [],           # list of dicts: {timestamp, ip, topic, status, error}
    "ip_requests": {}     # {ip: {"date": date_str, "count": int}}
}

# ==============
# Config
# ==============
NOTEGPT_BASE = "https://notegpt.io"
INIT_URL = f"{NOTEGPT_BASE}/api/v2/pdf-to-video"
SCRIPT_GET_URL = f"{NOTEGPT_BASE}/api/v2/pdf-to-video/script/get"
SCRIPT_EDIT_URL = f"{NOTEGPT_BASE}/api/v2/pdf-to-video/script/edit"

BRAND_LOGO_URL = "https://placehold.jp/24/000000/ffffff/200x50.png?text=Chirag%20Rathi"


# =========================
# Utility functions
# =========================
def get_real_ip(req):
    xff = req.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return req.remote_addr or "unknown"


def check_rate_limit(ip):
    """Limit: 3 requests per day per IP."""
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
    headers = {
        "Host": "notegpt.io",
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 12; LAVA Blaze Build/SP1A.210812.016) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.7499.146 Mobile Safari/537.36"
        ),
        "Sec-Ch-Ua-Platform": '"Android"',
        "X-Requested-With": "mark.via.gp",
        "Referer": "https://notegpt.io/explainer-video-maker",
    }
    scraper.headers.update(headers)
    return scraper


def add_anonymous_cookie(scraper):
    anon_id = str(uuid.uuid4())
    scraper.cookies.set("anonymous_user_id", anon_id, domain="notegpt.io")
    return anon_id


def notegpt_init(scraper, topic):
    add_anonymous_cookie(scraper)
    payload = {
        "topic": topic,
        "no_watermark": True,
        "brand_logo_url": BRAND_LOGO_URL,
        "brand_logo_position": "bottom-right",
        "gen_flow": "edit_script",
    }
    resp = scraper.post(INIT_URL, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    cid = data.get("conversation_id") or data.get("data", {}).get("conversation_id")
    if not cid:
        raise RuntimeError(f"conversation_id missing in init response: {data}")
    return cid


def notegpt_fetch_script(scraper, conversation_id):
    add_anonymous_cookie(scraper)
    params = {"conversation_id": conversation_id}
    resp = scraper.get(SCRIPT_GET_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    script_data = data.get("data") or data
    if not script_data:
        raise RuntimeError(f"script_data missing in fetch response: {data}")
    return script_data


def notegpt_edit_script(scraper, conversation_id, script_data):
    script = script_data.get("script", script_data.get("data", script_data))

    scenes = None
    if isinstance(script, dict):
        scenes = script.get("scenes") or script.get("slides") or script.get("items")

    if isinstance(scenes, list):
        for scene in scenes:
            if isinstance(scene, dict) and "text" in scene:
                if " | By Chirag Rathi" not in scene["text"]:
                    scene["text"] = scene["text"].rstrip() + " | By Chirag Rathi"

    post_body = {
        "conversation_id": conversation_id,
        "script": script,
        "is_force_save": True,
    }

    add_anonymous_cookie(scraper)
    resp = scraper.post(SCRIPT_EDIT_URL, json=post_body, timeout=60)
    resp.raise_for_status()
    return resp.json()


def notegpt_poll_video(scraper, conversation_id, timeout_sec=300, interval_sec=8):
    start = time.time()
    last_data = None
    while time.time() - start < timeout_sec:
        add_anonymous_cookie(scraper)
        params = {"conversation_id": conversation_id}
        resp = scraper.get(INIT_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        last_data = data

        status = (
            data.get("status")
            or data.get("data", {}).get("status")
            or data.get("data", {}).get("task_status")
        )
        if status == "success":
            video_url = (
                data.get("video_url")
                or data.get("data", {}).get("video_url")
                or data.get("data", {}).get("result_url")
            )
            if not video_url:
                outputs = data.get("data", {}).get("outputs") or []
                if isinstance(outputs, list) and outputs:
                    video_url = outputs[0].get("url") or outputs[0].get("video_url")
            if not video_url:
                raise RuntimeError(
                    f"Video status success but no URL found: {data}"
                )
            return video_url
        elif status in ("failed", "error"):
            raise RuntimeError(f"Video generation failed: {data}")
        time.sleep(interval_sec)

    raise TimeoutError(f"Polling timed out, last response: {last_data}")


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
                {% if rate_limited or loading %}disabled{% endif %}>
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m0 0A7 7 0 0112 5h0a7 7 0 016.418 4.027M4.582 9H9m11 11v-5h-.581m0 0A7 7 0 0112 19h0a7 7 0 01-6.418-4.027M19.418 15H15" />
                </svg>
                {% if loading %}Generating...{% else %}Generate Video{% endif %}
              </button>
              <p class="text-[10px] text-slate-500">
                3 requests/day per IP enforced.
              </p>
            </div>
          </form>

          <div id="debugBox" class="mt-2 text-xs rounded-md border border-red-500/50 bg-red-950/60 px-3 py-2 text-red-100 {% if not error %}hidden{% endif %}">
            <div class="flex items-center justify-between mb-1">
              <span class="font-semibold">Debug Mode</span>
              <button onclick="document.getElementById('debugBox').classList.add('hidden');" class="text-[10px] text-red-300 hover:text-red-100">
                Hide
              </button>
            </div>
            <pre class="whitespace-pre-wrap text-[11px] leading-snug">{{ error or "" }}</pre>
          </div>
        </div>

        <div class="space-y-4">
          <div class="border border-slate-700 rounded-md bg-slate-950/60 p-3">
            <div class="flex items-center justify-between mb-2">
              <h2 class="text-xs font-semibold text-slate-200">Render Status</h2>
              {% if status_message %}
              <span class="text-[11px] text-neon-green">{{ status_message }}</span>
              {% else %}
              <span class="text-[11px] text-slate-500">Waiting for your next request...</span>
              {% endif %}
            </div>
            {% if video_url %}
            <video id="videoPlayer" class="w-full rounded-md border border-slate-700 bg-black" controls playsinline>
              <source src="{{ video_url }}" type="video/mp4">
              Your browser does not support HTML5 video.
            </video>
            <p class="mt-2 text-[10px] text-slate-400">
              Branded script: <span class="text-neon-yellow">| By Chirag Rathi</span> appended to scenes.
            </p>
            <a href="{{ video_url }}" target="_blank" class="inline-flex mt-2 items-center px-2.5 py-1.5 rounded-md bg-slate-800 text-[11px] text-neon-blue border border-slate-600 hover:bg-slate-700">
              Open video in new tab
            </a>
            {% else %}
            <div class="text-xs text-slate-500">
              Generated video will appear here once ready. Typical turnaround ~1–3 minutes.
            </div>
            {% endif %}
          </div>

          <div class="border border-slate-700 rounded-md bg-slate-950/60 p-3">
            <h3 class="text-xs font-semibold text-slate-200 mb-1">Session Info</h3>
            <p class="text-[11px] text-slate-400">
              Your IP: <span class="text-neon-blue">{{ user_ip }}</span>
            </p>
            <p class="text-[11px] text-slate-500 mt-1">
              This interface mimics Android headers and rotates anonymous_user_id per request while preserving your IP-based quota.
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

  <script>
    {% if error %}
      document.addEventListener("DOMContentLoaded", function() {
        document.getElementById("debugBox").classList.remove("hidden");
      });
    {% endif %}
  </script>
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
    video_url = None
    error = ""
    status_message = ""
    rate_limited = False
    loading = False

    if request.method == "POST":
        topic = (request.form.get("topic") or "").strip()
        if not topic:
            error = "Topic cannot be empty."
        else:
            if not check_rate_limit(user_ip):
                rate_limited = True
                error = "Daily limit reached for your IP. Please try again tomorrow."
            else:
                loading = True
                try:
                    scraper = create_scraper()
                    cid = notegpt_init(scraper, topic)
                    time.sleep(10)
                    script_data = notegpt_fetch_script(scraper, cid)
                    notegpt_edit_script(scraper, cid, script_data)
                    status_message = "Waiting for render completion..."
                    video_url = notegpt_poll_video(scraper, cid)
                    status_message = "Video generation completed successfully."
                    log_request(user_ip, topic, "success", "")
                    loading = False
                except Exception as e:
                    error = f"{type(e).__name__}: {str(e)}"
                    log_request(user_ip, topic, "fail", error)
                    loading = False

    return render_template_string(
        TEMPLATE,
        topic=topic,
        video_url=video_url,
        error=error,
        status_message=status_message,
        user_ip=user_ip,
        rate_limited=rate_limited,
        loading=loading,
        year=datetime.utcnow().year,
    )


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
