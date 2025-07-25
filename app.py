from flask import Flask, render_template, request, jsonify, Response, stream_with_context, send_from_directory
from flask_cors import CORS
from task_store import tasks, load_tasks, save_tasks, task_lock, delete_task, get_all_tasks, add_task
from download_manager import enqueue_download, executor
from utils import get_output_template
from download_manager import delete_temp_files
import yt_dlp
import os
import uuid
import json
import time
import requests
import threading
import signal
import sys

app = Flask(__name__)
CORS(app)

os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

# Load and resume
load_tasks()

with task_lock:
    for task_id, task in list(tasks.items()):
        task.pop("should_abort", None)
        if task.get("status") in ("queued", "running") and not task.get("paused"):
            task["status"] = "running"
            enqueue_download(task_id, task["url"], task["quality"], task["format"])
        elif task.get("paused"):
            task["status"] = "paused"
    save_tasks()

# Graceful shutdown

def shutdown_handler(sig, frame):
    print("\n[EXIT] Shutting down cleanly...")
    with task_lock:
        for task in tasks.values():
            if task.get("status") in ("running", "queued"):
                task["paused"] = True
                task["status"] = "paused"
                task["progress"] = "Paused"
        save_tasks()
    try:
        executor.shutdown(wait=False)
    except Exception:
        pass
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

# Internet monitoring
def monitor_internet():
    fail_count = 0
    while True:
        try:
            requests.get("https://www.google.com", timeout=3)
            fail_count = 0
        except:
            fail_count += 1
            if fail_count >= 3:
                with task_lock:
                    for task in tasks.values():
                        if task.get("status") in ("running", "queued"):
                            task["paused"] = True
                            task["status"] = "paused"
                            task["progress"] = "Paused"
                    save_tasks()
        time.sleep(5)

threading.Thread(target=monitor_internet, daemon=True).start()

# Routes
@app.route('/')
def home():
    return render_template('platform/youtube.html')


@app.route('/tasks')
def tasks_page():
    return render_template('platform/tasks.html')


@app.route('/get-tasks')
def get_tasks():
    return jsonify({"tasks": get_all_tasks()})


@app.route('/control-task/<task_id>/<action>', methods=['POST'])
def control_task(task_id, action):
    with task_lock:
        if task_id not in tasks:
            return jsonify({"error": "Task not found"}), 404

        task = tasks[task_id]

        if action == 'pause':
            task['paused'] = True
            task['status'] = 'paused'
            task['progress'] = 'Paused'
            task['should_abort'] = True

        elif action == 'resume':
            if task.get('paused') and task.get('progress') != '100%':
                task['paused'] = False
                task['should_abort'] = False
                task['status'] = 'running'
                
                enqueue_download(task_id, task['url'], task['quality'], task['format'])

        elif action == 'delete':
            task['paused'] = True
            task['status'] = 'deleted'
            task['should_abort'] = True

        save_tasks()

    time.sleep(0.5)  # Allow hooks to process the abort signal

    if action == 'delete':
        with task_lock:
            task = tasks.get(task_id)
            if task:
                temp_path = get_output_template("temp_downloads", task["format"])
                delete_temp_files(task_id, temp_path)

            delete_task(task_id)


    return jsonify({"success": True})

@app.route('/control-task/delete-all', methods=['POST'])
def delete_all_tasks():
    with task_lock:
        for task_id in list(tasks):
            tasks[task_id]['paused'] = True
            tasks[task_id]['status'] = 'deleted'
            tasks[task_id]['should_abort'] = True
        save_tasks()

        time.sleep(0.5)
        with task_lock:
            for task_id, task in tasks.items():
                temp_path = get_output_template("temp_downloads", task["format"])
                delete_temp_files(task_id, temp_path)

            for task_id in list(tasks):
                delete_task(task_id)

    return jsonify({"success": True})

@app.route('/control-task/pause-all', methods=['POST'])
def pause_all_tasks():
    with task_lock:
        for task in tasks.values():
            if task['status'] in ('running', 'queued'):
                task['paused'] = True
                task['status'] = 'paused'
                task['progress'] = 'Paused'
                task['should_abort'] = True
        save_tasks()
    return jsonify({"success": True})

@app.route('/control-task/resume-all', methods=['POST'])
def resume_all_tasks():
    
    max_parallel = 4
    resumed = 0
    with task_lock:
        for task in tasks.values():
            if task.get('paused') and task.get('progress') != '100%':
                task['paused'] = False
                task['should_abort'] = False
                if resumed < max_parallel:
                    task['status'] = 'running'
                    enqueue_download(task['id'], task['url'], task['quality'], task['format'])
                    resumed += 1
                else:
                    task['status'] = 'queued'
        save_tasks()
 
    return jsonify({"success": True})

@app.route('/download-selected', methods=['POST'])
def download_selected():
    data = request.get_json()
    if not data or 'videos' not in data:
        return jsonify(success=False, error="No videos provided"), 400

    for video in data['videos']:
        task_id = uuid.uuid4().hex[:8]
        video_url = video['url']
        quality = video['quality']
        fmt = video['format']
        title = video.get('title', video_url)
        thumb_url = video.get('thumbnail')
        thumb_path = None

        if thumb_url:
            try:
                ext = os.path.splitext(thumb_url.split("?")[0])[1]
                filename = f"{task_id}{ext}"
                thumb_path = os.path.join("thumbnails", filename)
                r = requests.get(thumb_url, timeout=5)
                if r.status_code == 200:
                    with open(thumb_path, "wb") as f:
                        f.write(r.content)
            except:
                thumb_path = None

        add_task(task_id, {
            'id': task_id,
            'progress': '0%',
            'filename': None,
            'url': video_url,
            'type': fmt,
            'quality': quality,
            'format': fmt,
            'title': title,
            'status': 'queued',
            'paused': False,
            'should_abort': False,
            'thumbnail_path': thumb_path
        })

        enqueue_download(task_id, video_url, quality, fmt)

    return jsonify(success=True)

@app.route("/contact")
def contact():
    return render_template("platform/contact.html")

@app.route("/privacy")
def privacy():
    return render_template("platform/privacy.html")

@app.route('/detect', methods=['POST'])
def detect():
    data = request.get_json()
    video_url = data.get('video_url')
    if not video_url:
        return jsonify({"error": "Missing 'video_url' field"}), 400

    is_playlist = "playlist" in video_url
    try:
        if is_playlist:
            return jsonify({"type": "playlist"})
        ydl_opts = {'quiet': True, 'noplaylist': True, 'extract_flat': False}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
        return jsonify({
            "type": "video",
            "video": {
                "title": info.get("title") or "Untitled",
                "duration": info.get("duration") or 0,
                "id": info.get("id"),
                "url": info.get("webpage_url"),
                "thumbnail": info.get("thumbnail"),
                "qualities": ["144", "240", "360", "480", "720", "1080"]
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/detect-playlist-stream')
def detect_playlist_stream():
    video_url = request.args.get("video_url")
    if not video_url:
        return jsonify({"error": "Missing video_url"}), 400

    def generate():
        try:
            ydl_opts = {'quiet': True, 'extract_flat': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

            if info.get('_type') != 'playlist':
                yield f"data: {json.dumps({'error': 'Not a playlist'})}\n\n"
                return

            for entry in info.get("entries", []):
                video_data = {
                    "title": entry.get("title"),
                    "duration": entry.get("duration") or 0,
                    "url": entry.get("url") or entry.get("webpage_url"),
                    "thumbnail": entry.get("thumbnail") or '/static/images/default-thumbnail.png',
                    "qualities": ["144", "240", "360", "480", "720", "1080"]
                }
                yield f"data: {json.dumps(video_data)}\n\n"
                time.sleep(0.1)

            yield "event: done\ndata: end\n\n"
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')



@app.route('/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    return send_from_directory("thumbnails", filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3451, threaded=True)
