import subprocess
import sys
import threading
import webbrowser
import time
from app import app  # Import your existing Flask app
from task_store import add_task
import uuid

def run_server():
    # Start the Flask app on localhost without debug mode
    app.run(host='127.0.0.1', port=3452, threaded=True)

def open_chrome():
    time.sleep(1)  # Give server time to start
    url = "http://127.0.0.1:3452"
    
    # Paths to Chrome across different OS
    chrome_paths = [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",  # Windows 64-bit
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",  # Windows 32-bit
        "/usr/bin/google-chrome",  # Ubuntu
        "/usr/bin/chromium-browser",  # Ubuntu alternative
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"  # macOS
    ]

    for chrome in chrome_paths:
        try:
            subprocess.Popen([chrome, f"--app={url}"])
            return
        except Exception:
            continue

    # Fallback: open in default browser if Chrome not found
    webbrowser.open(url)

def add_dummy_tasks():
    dummy_tasks = [
        {
            "id": str(uuid.uuid4()),
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "quality": "720",
            "format": "video",
            "status": "queued",
            "progress": "0%",
            "paused": False
        },
        {
            "id": str(uuid.uuid4()),
            "url": "https://www.youtube.com/watch?v=3JZ_D3ELwOQ",
            "quality": "audio",
            "format": "audio",
            "status": "queued",
            "progress": "0%",
            "paused": False
        }
    ]

    for task in dummy_tasks:
        add_task(task["id"], task)

if __name__ == '__main__':
    add_dummy_tasks()
    threading.Thread(target=run_server).start()
    open_chrome()
