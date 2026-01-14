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
    "jobs": {}
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
# HTML Templates
# =========================
TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SnapStudy AI — Video Synthesis Studio</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Crimson+Pro:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  
  <style>
    :root {
      --ink: #0a0a0a;
      --paper: #fdfcf9;
      --amber: #f59e0b;
      --rust: #dc2626;
      --forest: #065f46;
      --slate: #475569;
      --cream: #fef3c7;
    }
    
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    
    body {
      font-family: 'Manrope', sans-serif;
      background: var(--paper);
      color: var(--ink);
      line-height: 1.6;
      overflow-x: hidden;
    }
    
    /* Grain texture overlay */
    body::before {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-image: 
        repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,.02) 2px, rgba(0,0,0,.02) 4px),
        repeating-linear-gradient(90deg, transparent, transparent 2px, rgba(0,0,0,.02) 2px, rgba(0,0,0,.02) 4px);
      pointer-events: none;
      z-index: 9999;
      opacity: 0.4;
    }
    
    /* Typography */
    .serif {
      font-family: 'Crimson Pro', Georgia, serif;
    }
    
    .mono {
      font-family: 'IBM Plex Mono', monospace;
    }
    
    /* Layout */
    .container {
      max-width: 1400px;
      margin: 0 auto;
      padding: 3rem 2rem;
    }
    
    /* Header */
    .masthead {
      text-align: center;
      padding: 4rem 0 6rem;
      border-bottom: 3px solid var(--ink);
      margin-bottom: 4rem;
      position: relative;
    }
    
    .masthead::after {
      content: '';
      position: absolute;
      bottom: -6px;
      left: 0;
      right: 0;
      height: 3px;
      background: var(--amber);
    }
    
    .masthead h1 {
      font-size: clamp(2.5rem, 8vw, 5rem);
      font-weight: 800;
      letter-spacing: -0.03em;
      line-height: 0.95;
      margin-bottom: 1rem;
    }
    
    .masthead .tagline {
      font-family: 'Crimson Pro', serif;
      font-size: clamp(1.1rem, 3vw, 1.5rem);
      color: var(--slate);
      font-style: italic;
      max-width: 600px;
      margin: 0 auto;
    }
    
    /* Two column grid */
    .studio-grid {
      display: grid;
      grid-template-columns: 1fr 1.2fr;
      gap: 4rem;
      align-items: start;
    }
    
    @media (max-width: 968px) {
      .studio-grid {
        grid-template-columns: 1fr;
        gap: 3rem;
      }
    }
    
    /* Section headers */
    .section-label {
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.15em;
      color: var(--slate);
      margin-bottom: 1.5rem;
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    
    .section-label::before {
      content: '';
      width: 32px;
      height: 2px;
      background: var(--amber);
    }
    
    /* Form styling */
    .prompt-box {
      margin-bottom: 2rem;
    }
    
    .prompt-box label {
      display: block;
      font-weight: 600;
      margin-bottom: 0.75rem;
      color: var(--ink);
    }
    
    .prompt-box textarea {
      width: 100%;
      min-height: 180px;
      padding: 1.25rem;
      border: 2px solid var(--ink);
      background: var(--paper);
      font-family: 'Crimson Pro', serif;
      font-size: 1.125rem;
      line-height: 1.7;
      resize: vertical;
      transition: all 0.2s;
    }
    
    .prompt-box textarea:focus {
      outline: none;
      border-color: var(--amber);
      box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.1);
    }
    
    .prompt-box textarea::placeholder {
      color: var(--slate);
      opacity: 0.5;
    }
    
    /* Button */
    .btn-generate {
      width: 100%;
      padding: 1.5rem 2rem;
      background: var(--ink);
      color: var(--paper);
      border: none;
      font-family: 'Manrope', sans-serif;
      font-weight: 700;
      font-size: 1rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      overflow: hidden;
    }
    
    .btn-generate::before {
      content: '';
      position: absolute;
      top: 0;
      left: -100%;
      width: 100%;
      height: 100%;
      background: var(--amber);
      transition: left 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    .btn-generate span {
      position: relative;
      z-index: 1;
    }
    
    .btn-generate:hover::before {
      left: 0;
    }
    
    .btn-generate:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(10, 10, 10, 0.3);
    }
    
    .btn-generate:active {
      transform: translateY(0);
    }
    
    .btn-generate:disabled {
      opacity: 0.4;
      cursor: not-allowed;
      transform: none;
    }
    
    .btn-generate:disabled::before {
      display: none;
    }
    
    /* Alert box */
    .alert {
      padding: 1.25rem;
      border-left: 4px solid var(--rust);
      background: rgba(220, 38, 38, 0.05);
      margin-bottom: 1.5rem;
    }
    
    .alert-text {
      font-weight: 600;
      color: var(--rust);
      font-size: 0.95rem;
    }
    
    /* Metadata */
    .meta-info {
      margin-top: 1.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid rgba(10, 10, 10, 0.1);
    }
    
    .meta-item {
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.8rem;
      color: var(--slate);
      margin-bottom: 0.5rem;
    }
    
    /* Canvas (right side) */
    .canvas {
      position: sticky;
      top: 2rem;
      border: 3px solid var(--ink);
      background: #fff;
      padding: 2rem;
      min-height: 500px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      text-align: center;
    }
    
    /* Empty state */
    .empty-state {
      max-width: 400px;
    }
    
    .empty-state-icon {
      width: 120px;
      height: 120px;
      margin: 0 auto 2rem;
      background: var(--cream);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 2px solid var(--amber);
    }
    
    .empty-state-icon svg {
      width: 60px;
      height: 60px;
      stroke: var(--amber);
      stroke-width: 1.5;
    }
    
    .empty-state h3 {
      font-family: 'Crimson Pro', serif;
      font-size: 1.75rem;
      margin-bottom: 0.75rem;
      font-weight: 700;
    }
    
    .empty-state p {
      color: var(--slate);
      line-height: 1.6;
    }
    
    /* Processing state */
    .processing-state {
      width: 100%;
    }
    
    .spinner {
      width: 80px;
      height: 80px;
      margin: 0 auto 2rem;
      border: 3px solid var(--cream);
      border-top-color: var(--amber);
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
    
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    
    .progress-text {
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.9rem;
      color: var(--slate);
      margin-top: 1rem;
    }
    
    .job-id {
      margin-top: 2rem;
      padding-top: 2rem;
      border-top: 1px solid rgba(10, 10, 10, 0.1);
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.75rem;
      color: var(--slate);
    }
    
    /* Video complete state */
    .video-complete {
      width: 100%;
      animation: fadeSlideIn 0.6s ease-out;
    }
    
    @keyframes fadeSlideIn {
      from {
        opacity: 0;
        transform: translateY(20px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    
    .video-complete video {
      width: 100%;
      border: 2px solid var(--ink);
      margin-bottom: 1.5rem;
    }
    
    .video-actions {
      display: flex;
      gap: 1rem;
      margin-top: 1.5rem;
    }
    
    .btn-download {
      flex: 1;
      padding: 1rem 1.5rem;
      background: var(--forest);
      color: white;
      text-decoration: none;
      font-weight: 600;
      text-align: center;
      transition: all 0.2s;
      border: 2px solid var(--forest);
    }
    
    .btn-download:hover {
      background: white;
      color: var(--forest);
    }
    
    .credit {
      margin-top: 1rem;
      padding: 0.75rem;
      background: var(--cream);
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.8rem;
      border-left: 3px solid var(--amber);
    }
    
    /* Error state */
    .error-state {
      max-width: 500px;
    }
    
    .error-icon {
      width: 80px;
      height: 80px;
      margin: 0 auto 1.5rem;
      background: rgba(220, 38, 38, 0.1);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    
    .error-icon svg {
      width: 40px;
      height: 40px;
      stroke: var(--rust);
    }
    
    .error-details {
      margin-top: 1.5rem;
      padding: 1rem;
      background: rgba(10, 10, 10, 0.03);
      border: 1px solid rgba(10, 10, 10, 0.1);
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.75rem;
      color: var(--slate);
      text-align: left;
      max-height: 200px;
      overflow-y: auto;
    }
    
    /* Footer */
    .colophon {
      margin-top: 6rem;
      padding-top: 2rem;
      border-top: 1px solid rgba(10, 10, 10, 0.1);
      text-align: center;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.75rem;
      color: var(--slate);
    }
  </style>
</head>
<body>
  <div class="container">
    
    <header class="masthead">
      <h1>SnapStudy AI</h1>
      <p class="tagline">Transform written ideas into narrated visual stories, powered by intelligent synthesis</p>
    </header>
    
    <div class="studio-grid">
      
      <!-- Left: Input -->
      <div>
        <div class="section-label">
          <span>Input</span>
        </div>
        
        <form method="POST" action="/">
          <div class="prompt-box">
            <label for="topic">Describe your video concept</label>
            <textarea 
              id="topic" 
              name="topic" 
              placeholder="Example: A cinematic explanation of how photosynthesis works, starting from sunlight hitting a leaf to the creation of glucose molecules..."
              required
              {% if rate_limited %}disabled{% endif %}
            >{{ topic or "" }}</textarea>
          </div>
          
          {% if rate_limited %}
          <div class="alert">
            <p class="alert-text">You've reached your daily limit of 3 videos. Please return tomorrow.</p>
          </div>
          {% endif %}
          
          <button 
            type="submit" 
            class="btn-generate"
            {% if rate_limited %}disabled{% endif %}
          >
            <span>Synthesize Video</span>
          </button>
          
          <div class="meta-info">
            <div class="meta-item">→ Average processing time: 2–3 minutes</div>
            <div class="meta-item">→ Daily quota: 3 videos per session</div>
            <div class="meta-item">→ Output format: MP4, branded with attribution</div>
          </div>
        </form>
      </div>
      
      <!-- Right: Output Canvas -->
      <div>
        <div class="section-label">
          <span>Output</span>
        </div>
        
        <div class="canvas" id="canvas">
          {% if job_id %}
          <!-- Processing -->
          <div class="processing-state">
            <div class="spinner"></div>
            <h3>Synthesis in Progress</h3>
            <p class="progress-text" id="progressText">Initializing pipeline...</p>
            <div class="job-id">Session: {{ job_id[:12] }}...</div>
          </div>
          {% else %}
          <!-- Empty State -->
          <div class="empty-state">
            <div class="empty-state-icon">
              <svg fill="none" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z"/>
              </svg>
            </div>
            <h3>Awaiting Input</h3>
            <p>Your synthesized video will materialize here once the generation pipeline completes.</p>
          </div>
          {% endif %}
        </div>
      </div>
      
    </div>
    
    <footer class="colophon">
      <p>SnapStudy AI Pro © 2026 — A creative tool for educational video synthesis</p>
    </footer>
    
  </div>

  {% if job_id %}
  <script>
    const jobId = "{{ job_id }}";
    
    function checkStatus() {
      fetch('/status/' + jobId)
        .then(res => res.json())
        .then(data => {
          const progressText = document.getElementById('progressText');
          const canvas = document.getElementById('canvas');
          
          if (progressText) {
            progressText.textContent = data.progress || 'Processing...';
          }
          
          if (data.status === 'completed') {
            canvas.innerHTML = `
              <div class="video-complete">
                <video controls playsinline>
                  <source src="${data.video_url}" type="video/mp4">
                </video>
                <h3>Synthesis Complete</h3>
                <p>Your video is ready for download and distribution.</p>
                <div class="video-actions">
                  <a href="${data.video_url}" target="_blank" download class="btn-download">
                    Download Video
                  </a>
                </div>
                <div class="credit">
                  Attribution applied: "By Chirag Rathi"
                </div>
              </div>
            `;
          } else if (data.status === 'failed') {
            canvas.innerHTML = `
              <div class="error-state">
                <div class="error-icon">
                  <svg fill="none" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/>
                  </svg>
                </div>
                <h3>Synthesis Failed</h3>
                <p>An error occurred during processing. Please try again with different input.</p>
                <details class="error-details">
                  <summary style="cursor: pointer; font-weight: 600; margin-bottom: 0.5rem;">Technical Details</summary>
                  <pre style="white-space: pre-wrap; word-wrap: break-word;">${data.error}</pre>
                </details>
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
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Control Room — SnapStudy AI</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://fonts.googleapis.com/css2?family=Crimson+Pro:wght@600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Manrope:wght@600;700;800&display=swap" rel="stylesheet">
  
  <style>
    :root {
      --terminal-bg: #0a0a0a;
      --terminal-text: #00ff41;
      --terminal-dim: #007a1f;
      --warning: #ff9500;
      --danger: #ff3b30;
      --info: #00c7ff;
    }
    
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    
    body {
      font-family: 'IBM Plex Mono', monospace;
      background: var(--terminal-bg);
      color: var(--terminal-text);
      padding: 2rem;
      line-height: 1.6;
    }
    
    /* Scanline effect */
    body::before {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: repeating-linear-gradient(
        0deg,
        rgba(0, 255, 65, 0.03),
        rgba(0, 255, 65, 0.03) 1px,
        transparent 1px,
        transparent 2px
      );
      pointer-events: none;
      z-index: 9999;
    }
    
    /* Flicker effect */
    @keyframes flicker {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.97; }
    }
    
    body {
      animation: flicker 0.15s infinite;
    }
    
    .container {
      max-width: 1600px;
      margin: 0 auto;
    }
    
    /* Header */
    .header {
      border: 2px solid var(--terminal-text);
      padding: 2rem;
      margin-bottom: 2rem;
      position: relative;
    }
    
    .header::before {
      content: '[ CLASSIFIED ]';
      position: absolute;
      top: -12px;
      left: 20px;
      background: var(--terminal-bg);
      padding: 0 10px;
      font-size: 0.75rem;
      color: var(--danger);
      letter-spacing: 0.2em;
    }
    
    .header h1 {
      font-family: 'Manrope', sans-serif;
      font-size: 2.5rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      margin-bottom: 0.5rem;
      text-transform: uppercase;
    }
    
    .header .subtitle {
      color: var(--terminal-dim);
      font-size: 0.9rem;
    }
    
    .status-indicator {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      margin-top: 1rem;
      font-size: 0.85rem;
    }
    
    .pulse-dot {
      width: 8px;
      height: 8px;
      background: var(--terminal-text);
      border-radius: 50%;
      animation: pulse 2s ease-in-out infinite;
    }
    
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
    
    /* Stats Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1.5rem;
      margin-bottom: 3rem;
    }
    
    .stat-card {
      border: 1px solid var(--terminal-dim);
      padding: 1.5rem;
      position: relative;
      background: rgba(0, 255, 65, 0.02);
    }
    
    .stat-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 4px;
      height: 100%;
      background: var(--terminal-text);
    }
    
    .stat-label {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.15em;
      color: var(--terminal-dim);
      margin-bottom: 0.75rem;
    }
    
    .stat-value {
      font-family: 'Manrope', sans-serif;
      font-size: 2.5rem;
      font-weight: 700;
      line-height: 1;
    }
    
    .stat-meta {
      margin-top: 0.5rem;
      font-size: 0.8rem;
      color: var(--terminal-dim);
    }
    
    /* Table */
    .table-container {
      border: 2px solid var(--terminal-text);
      overflow: hidden;
      margin-bottom: 2rem;
    }
    
    .table-header {
      background: var(--terminal-text);
      color: var(--terminal-bg);
      padding: 1rem 1.5rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      font-size: 0.85rem;
    }
    
    table {
      width: 100%;
      border-collapse: collapse;
    }
    
    thead {
      background: rgba(0, 255, 65, 0.1);
    }
    
    th {
      padding: 1rem 1.5rem;
      text-align: left;
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      border-bottom: 1px solid var(--terminal-dim);
    }
    
    td {
      padding: 1rem 1.5rem;
      border-bottom: 1px solid rgba(0, 122, 31, 0.3);
      font-size: 0.85rem;
    }
    
    tr:hover {
      background: rgba(0, 255, 65, 0.05);
    }
    
    .status-badge {
      display: inline-block;
      padding: 0.25rem 0.75rem;
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      border: 1px solid;
    }
    
    .status-success {
      color: var(--terminal-text);
      border-color: var(--terminal-text);
      background: rgba(0, 255, 65, 0.1);
    }
    
    .status-failed {
      color: var(--danger);
      border-color: var(--danger);
      background: rgba(255, 59, 48, 0.1);
    }
    
    .ip-address {
      font-family: 'IBM Plex Mono', monospace;
      color: var(--info);
      font-weight: 500;
    }
    
    .truncate {
      max-width: 300px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    
    .empty-state {
      padding: 4rem 2rem;
      text-align: center;
      color: var(--terminal-dim);
      border: 1px dashed var(--terminal-dim);
    }
    
    /* Footer */
    .footer {
      text-align: center;
      padding: 2rem;
      color: var(--terminal-dim);
      font-size: 0.75rem;
      border-top: 1px solid var(--terminal-dim);
      margin-top: 3rem;
    }
  </style>
</head>
<body>
  <div class="container">
    
    <div class="header">
      <h1>Control Room</h1>
      <p class="subtitle">SnapStudy AI Pro — System Monitoring & Analytics</p>
      <div class="status-indicator">
        <span class="pulse-dot"></span>
        <span>ALL SYSTEMS OPERATIONAL</span>
      </div>
    </div>
    
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Total Requests Logged</div>
        <div class="stat-value">{{ logs|length }}</div>
        <div class="stat-meta">Since system initialization</div>
      </div>
      
      <div class="stat-card">
        <div class="stat-label">Server IP Address</div>
        <div class="stat-value ip-address" style="font-size: 1.5rem;">{{ server_ip }}</div>
        <div class="stat-meta">External network identifier</div>
      </div>
      
      <div class="stat-card">
        <div class="stat-label">Active IP Sessions (24h)</div>
        <div class="stat-value">{{ ip_requests|length }}</div>
        <div class="stat-meta">Unique client connections today</div>
      </div>
    </div>
    
    <div class="table-container">
      <div class="table-header">Request Activity Log</div>
      <table>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Client IP</th>
            <th>Topic</th>
            <th>Status</th>
            <th>Error Details</th>
          </tr>
        </thead>
        <tbody>
          {% if logs %}
            {% for row in logs|reverse %}
            <tr>
              <td>{{ row.timestamp }}</td>
              <td><span class="ip-address">{{ row.ip }}</span></td>
              <td class="truncate" title="{{ row.topic }}">{{ row.topic }}</td>
              <td>
                {% if row.status == 'success' %}
                <span class="status-badge status-success">Success</span>
                {% else %}
                <span class="status-badge status-failed">Failed</span>
                {% endif %}
              </td>
              <td class="truncate" title="{{ row.error }}">{{ row.error if row.error else '—' }}</td>
            </tr>
            {% endfor %}
          {% else %}
            <tr>
              <td colspan="5" class="empty-state">
                NO ACTIVITY RECORDED<br>
                <span style="font-size: 0.8rem; margin-top: 0.5rem; display: inline-block;">Awaiting first request...</span>
              </td>
            </tr>
          {% endif %}
        </tbody>
      </table>
    </div>
    
    <div class="footer">
      © 2026 SNAPSTUDY AI PRO — CONFIDENTIAL SYSTEM MONITORING INTERFACE<br>
      UNAUTHORIZED ACCESS PROHIBITED
    </div>
    
  </div>
</body>
</html>
"""


# =========================
# Routes
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
        rate_limited=rate_limited,
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
        server_ip = f"ERROR: {str(e)}"
    
    return render_template_string(
        ADMIN_TEMPLATE,
        server_ip=server_ip,
        logs=stats["logs"],
        ip_requests=stats["ip_requests"],
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
