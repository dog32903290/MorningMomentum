import os
import subprocess
import json
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

CONFIG_FILE = "config.json"
UPLOAD_FOLDER = "uploads"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def get_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

# Global tracker for the afplay process
alarm_process = None

def wake_monitor():
    """Detects when the system wakes from sleep by monitoring time jumps."""
    last_time = time.time()
    while True:
        time.sleep(1)
        current_time = time.time()
        # If the gap is > 10s, we likely just woke up from sleep
        if (current_time - last_time) > 10:
            print("🕒 偵測到系統喚醒，啟動 2 分鐘防休眠 (caffeinate)...")
            subprocess.Popen(["caffeinate", "-di", "-t", "120"])
        last_time = current_time

# Start monitor thread
threading.Thread(target=wake_monitor, daemon=True).start()

def get_saved_password():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data.get("mac_password", "")
        except:
            return ""
    return ""

def save_password(pwd):
    data = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
        except:
            pass
    data["mac_password"] = pwd
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

def clear_password():
    data = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            data["mac_password"] = ""
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f)
        except:
            pass

# ─── Helper ───────────────────────────────────────────────────────────────────

SWITCHAUDIO_PATHS = [
    "./switchaudio-osx",
    "switchaudio-osx",
    "/opt/homebrew/bin/switchaudio-osx",
    "/usr/local/bin/switchaudio-osx",
]

def find_switchaudio():
    """Return the path to switchaudio-osx, or None if not found."""
    for path in SWITCHAUDIO_PATHS:
        result = subprocess.run(["which", path] if "/" not in path else ["test", "-x", path],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return path
    return None


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/get_outputs", methods=["GET"])
def get_outputs():
    """Return a list of audio output device names."""
    sa = find_switchaudio()
    if not sa:
        return jsonify({
            "error": "switchaudio-osx not found. Install via: brew install switchaudio-osx"
        }), 500

    result = subprocess.run(
        [sa, "-a", "-t", "output"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return jsonify({"error": result.stderr.strip()}), 500

    devices = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return jsonify({"devices": devices})


@app.route("/set_output", methods=["POST"])
def set_output():
    """Switch the default audio output device."""
    data = request.get_json(force=True)
    device = data.get("device", "").strip()
    if not device:
        return jsonify({"error": "Missing 'device' field"}), 400

    sa = find_switchaudio()
    if not sa:
        return jsonify({
            "error": "switchaudio-osx not found. Install via: brew install switchaudio-osx"
        }), 500

    result = subprocess.run(
        [sa, "-s", device],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return jsonify({"error": result.stderr.strip()}), 500

    return jsonify({"ok": True, "device": device})


@app.route("/upload_reminders", methods=["POST"])
def upload_reminders():
    """
    Accept a list of {hour, text} objects and add them to Mac Reminders
    via AppleScript. Due date is set to today at the given hour.
    """
    items = request.get_json(force=True)
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Expect a non-empty JSON array"}), 400

    today = datetime.now().strftime("%Y-%m-%d")
    added = []
    errors = []

    for item in items:
        hour = item.get("hour")
        text = item.get("text", "").strip()
        
        if not text or hour is None:
            continue
            
        # Build AppleScript — create list if it doesn't exist, then add reminder
        safe_text = text.replace('"', '\\"')
        script = f"""
tell application "Reminders"
    set myDate to current date
    set hours of myDate to {int(hour)}
    set minutes of myDate to 0
    set seconds of myDate to 0
    
    if not (exists list "Morning Momentum") then
        make new list with properties {{name:"Morning Momentum"}}
    end if
    set theList to list "Morning Momentum"
    set newReminder to make new reminder at end of reminders of theList
    set name of newReminder to "{safe_text}"
    set due date of newReminder to myDate
end tell
"""
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            errors.append({"hour": hour, "error": result.stderr.strip()})
        else:
            added.append({"hour": hour, "text": text})

    return jsonify({"added": added, "errors": errors})


# ─── Entry ────────────────────────────────────────────────────────────────────

@app.route("/save_password", methods=["POST"])
def save_password_route():
    data = request.get_json(force=True)
    pwd = data.get("password", "")
    if pwd:
        save_password(pwd)
        return jsonify({"ok": True})
    return jsonify({"error": "No password provided"}), 400

@app.route("/set_wake_schedule", methods=["POST"])
def set_wake_schedule():
    """
    Schedules a wake event before the given hour and minute.
    Uses sudo -S and local config.json to bypass prompts.
    """
    data = request.get_json(force=True)
    hour = int(data.get("hour", 7))
    minute = int(data.get("minute", 0))
    enabled = data.get("enabled", True)

    pwd = get_saved_password()
    if not pwd:
        return jsonify({"error": "NO_PASSWORD"}), 401

    if not enabled:
        # Cancel all scheduled wake/poweron events
        try:
            result = subprocess.run(
                ["sudo", "-S", "pmset", "repeat", "cancel"],
                input=f"{pwd}\n",
                capture_output=True, text=True
            )
            if result.returncode != 0:
                err_lower = result.stderr.lower()
                if "incorrect" in err_lower or "sorry" in err_lower or "try again" in err_lower:
                    clear_password()
                    return jsonify({"error": "AUTH_FAILED"}), 401
                return jsonify({"error": result.stderr.strip()}), 500
            
            return jsonify({"status": "cancelled"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # 1 minute before the requested time
    wake_time = target - timedelta(minutes=1)
    wake_h = wake_time.hour
    wake_m = wake_time.minute
    wake_str = f"{wake_h:02d}:{wake_m:02d}:00"
    
    try:
        result = subprocess.run(
            ["sudo", "-S", "pmset", "repeat", "wakeorpoweron", "MTWRFSU", wake_str],
            input=f"{pwd}\n",
            capture_output=True, text=True
        )
        if result.returncode != 0:
            err_lower = result.stderr.lower()
            if "incorrect" in err_lower or "sorry" in err_lower or "try again" in err_lower:
                clear_password()
                return jsonify({"error": "AUTH_FAILED"}), 401
            return jsonify({"error": result.stderr.strip()}), 500
            
        return jsonify({"status": "success", "wake_time": wake_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Audio ────────────────────────────────────────────────────────────────────

@app.route("/upload_audio", methods=["POST"])
def upload_audio():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    
    ext = os.path.splitext(file.filename)[1]
    if not ext: ext = ".mp3"
    
    filename = "alarm_sound" + ext
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)
    
    cfg = get_config()
    cfg["alarm_file_path"] = os.path.abspath(path)
    save_config(cfg)
    
    return jsonify({"ok": True, "path": path})

@app.route("/play_alarm", methods=["POST"])
def play_alarm():
    global alarm_process
    if alarm_process and alarm_process.poll() is None:
        alarm_process.terminate()
    
    cfg = get_config()
    path = cfg.get("alarm_file_path")
    
    if path and os.path.exists(path):
        try:
            alarm_process = subprocess.Popen(["afplay", path])
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": f"No alarm file found at {path}"}), 404

@app.route("/stop_alarm", methods=["POST"])
def stop_alarm_route():
    global alarm_process
    if alarm_process and alarm_process.poll() is None:
        alarm_process.terminate()
        alarm_process = None
    subprocess.run(["killall", "afplay"], capture_output=True)
    return jsonify({"ok": True})


# ─── Entry ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not find_switchaudio():
        print("⚠️  switchaudio-osx 未安裝，音訊切換功能將無法使用。")
        print("   安裝方式：brew install switchaudio-osx")
    app.run(host="127.0.0.1", port=5001, debug=False)
