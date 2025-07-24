from flask import Flask, render_template, request, jsonify, Response, stream_with_context, send_from_directory
from flask_cors import CORS
from task_store import tasks, load_tasks, save_tasks, task_lock
from task_store import add_task, update_task, delete_task, get_all_tasks
from download_manager import enqueue_download
from concurrent.futures import ThreadPoolExecutor
import yt_dlp
import os
import uuid
import json
import time
import requests

app = Flask(__name__)
CORS(app)

os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

load_tasks()

with task_lock:
    for task_id, task in tasks.items():
        if task.get("status") in ("queued", "running") and not task.get("paused") and not task.get("should_abort"):
            print(f"[RESUME] Re-enqueuing task: {task_id}")
            enqueue_download(task_id, task["url"], task["quality"], task["format"])
        elif task.get("paused"):
            print(f"[SKIP] Task {task_id} is paused, not resuming.")


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

        if action == 'pause':
            update_task(task_id, {'paused': True, 'status': 'paused'})

        elif action == 'resume':
            task = tasks[task_id]
            if task.get('paused') and task.get('progress') != '100%' and not task.get('should_abort'):
                task['paused'] = False
                task['status'] = 'running'
                save_tasks()
                enqueue_download(task_id, task['url'], task['quality'], task['format'])

        elif action == 'delete':
            tasks[task_id]['should_abort'] = True
            tasks[task_id]['status'] = 'deleted'
            save_tasks()
            time.sleep(0.2)
            delete_task(task_id)

        return jsonify({"success": True})


@app.route('/download-selected', methods=['POST'])
def download_selected():
    data = request.get_json()
    if not data or 'videos' not in data:
        return jsonify(success=False, error="No videos provided"), 400

    for video in data['videos']:
        video_url = video['url']
        quality = video['quality']
        fmt = video['format']
        title = video.get('title', video_url)
        task_id = uuid.uuid4().hex[:8]

        thumbnail_url = video.get("thumbnail")
        thumbnail_filename = None
        thumbnail_path = None

        if thumbnail_url:
            try:
                ext = os.path.splitext(thumbnail_url.split("?")[0])[1]
                thumbnail_filename = f"{task_id}{ext}"
                thumbnail_path = os.path.join("thumbnails", thumbnail_filename)
                r = requests.get(thumbnail_url, timeout=5)
                if r.status_code == 200:
                    with open(thumbnail_path, "wb") as f:
                        f.write(r.content)
            except Exception as e:
                print(f"[WARN] Failed to fetch thumbnail: {e}")
                thumbnail_path = None

        add_task(task_id, {
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
            'thumbnail_path': thumbnail_path if thumbnail_path else None
        })

        enqueue_download(task_id, video_url, quality, fmt)

    return jsonify(success=True)


@app.route('/detect', methods=['POST'])
def detect():
    data = request.get_json()
    video_url = data.get('video_url')
    if not video_url:
        return jsonify({"error": "Missing 'video_url' field"}), 400

    is_playlist = (
        "youtube.com/playlist" in video_url or
        "youtu.be/playlist" in video_url
    )

    try:
        if is_playlist:
            return jsonify({"type": "playlist"})
        else:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'noplaylist': True,
                'timeout': 10
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

            return jsonify({
                "type": "video",
                "video": {
                    "title": info.get('title') or 'Unknown Title',
                    "duration": info.get('duration') or 0,
                    "id": info.get('id'),
                    "url": info.get('webpage_url') or '#',
                    "thumbnail": info.get('thumbnail') or '/static/images/default-thumbnail.png',
                    "qualities": ["144", "240", "360", "480", "720", "1080"]
                }
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/detect-playlist-stream')
def detect_playlist_stream():
    video_url = request.args.get('video_url')
    if not video_url:
        return jsonify({"error": "Missing video_url"}), 400

    def generate():
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'timeout': 10
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

            if info.get('_type') != 'playlist':
                yield f"data: {json.dumps({'error': 'Not a playlist'})}\n\n"
                return

            for entry in info.get('entries', []):
                video_data = {
                    "title": entry.get('title') or 'Untitled',
                    "duration": entry.get('duration') or 0,
                    "url": entry.get('url') or entry.get('webpage_url'),
                    "thumbnail": (
                        entry.get('thumbnail') or
                        (entry.get('thumbnails', [{}])[0].get('url')) or
                        '/static/images/default-thumbnail.png'
                    ),
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
    return send_from_directory('thumbnails', filename)


@app.route('/control-task/delete-all', methods=['POST'])
def delete_all_tasks():
    with task_lock:
        task_ids = list(tasks.keys())
        for task_id in task_ids:
            tasks[task_id]['should_abort'] = True
            tasks[task_id]['status'] = 'deleted'
        save_tasks()
    time.sleep(0.5)
    with task_lock:
        for task_id in task_ids:
            delete_task(task_id)
    return jsonify({"success": True})

@app.route("/contact")
def contact():
    return render_template("platform/contact.html")

@app.route("/privacy")
def privacy():
    return render_template("platform/privacy.html")



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3454,threaded=True)
