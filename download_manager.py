import os
import yt_dlp
import requests
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from task_store import tasks, save_tasks, task_lock
from utils import (
    get_output_template,
    get_format_string,
    get_postprocessors,
    generate_progress_hook
)

logging.basicConfig(level=logging.DEBUG)

# System Downloads folder
downloads_dir = str(Path.home() / "Downloads")

# Thread pool for parallel downloads
executor = ThreadPoolExecutor(max_workers=4)

def download_thumbnail(thumbnail_url, task_id):
    try:
        if not thumbnail_url:
            return None
        ext = os.path.splitext(thumbnail_url.split("?")[0])[1]
        filename = f"{task_id}{ext}"
        path = os.path.join("thumbnails", filename)
        os.makedirs("thumbnails", exist_ok=True)

        if os.path.exists(path):  # 🛑 Don't download again if it already exists
            return f"thumbnails/{filename}"

        r = requests.get(thumbnail_url, timeout=5)
        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            return f"thumbnails/{filename}"
    except Exception as e:
        print(f"[Thumbnail Warning] {e}")
    return None

def common_ydl_opts(task_id, output_template, ext, stream_type, quality):
    return {
        'format': get_format_string(quality, stream_type),
        'outtmpl': output_template,
        'merge_output_format': ext,
        'continuedl': True,
        'ignoreerrors': True,
        'retries': 10,
        'fragment_retries': 10,
        'noplaylist': (stream_type != 'playlist'),
        'progress_hooks': [generate_progress_hook(task_id)],
        'postprocessors': get_postprocessors(stream_type),
        'quiet': True,
        'nopart': False,
        'concurrent_fragment_downloads': 1  # More stable downloads
    }

def handle_single(video_url, quality, stream_type, task_id):
    ext = 'mp3' if stream_type == 'audio' else 'mp4'
    output_template = get_output_template(downloads_dir, stream_type)
    print(f"[{task_id}] 📂 Saving to: {output_template}")

    ydl_opts = common_ydl_opts(task_id, output_template, ext, stream_type, quality)

    try:
        print(f"[{task_id}] 🎥 Starting single video download...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)

            filename = None
            if info:
                try:
                    base = os.path.splitext(ydl.prepare_filename(info))[0]
                    filename = f"{base}.{ext}"

                    # 🔁 Check for duplicates and make unique
                    counter = 1
                    while os.path.exists(filename):
                        filename = f"{base}_{counter}.{ext}"
                        counter += 1

                    # Rename the actual downloaded file to match new unique name
                    original_file = os.path.splitext(ydl.prepare_filename(info))[0] + f".{ext}"
                    if original_file != filename and os.path.exists(original_file):
                        os.rename(original_file, filename)

                except Exception as e:
                    print(f"[{task_id}] ⚠️ Could not prepare filename: {e}")
                    filename = None

        # ✅ Only set new thumbnail if one isn't already saved
        thumbnail_path = tasks.get(task_id, {}).get("thumbnail_path")
        if not thumbnail_path:
            thumbnail_url = info.get("thumbnail") if info else None
            thumbnail_path = download_thumbnail(thumbnail_url, task_id)

        with task_lock:
            if tasks[task_id].get('should_abort'):
                tasks[task_id]['progress'] = "Aborted"
                tasks[task_id]['status'] = 'aborted'
            else:
                if filename:
                    tasks[task_id]['filename'] = filename
                tasks[task_id]['progress'] = '100%' if filename else 'Paused'
                tasks[task_id]['status'] = 'completed' if filename else 'paused'
                if thumbnail_path:
                    tasks[task_id]['thumbnail_path'] = thumbnail_path
            save_tasks()

    except Exception as e:
        print(f"[{task_id}] ❌ Error during single download: {e}")
        with task_lock:
            tasks[task_id]['progress'] = f"Error: {str(e)}"
            tasks[task_id]['status'] = 'error'
            save_tasks()


def handle_playlist(video_url, quality, stream_type, task_id):
    try:
        print(f"[{task_id}] 🎮 Starting playlist download...")
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)

        title = info.get('title', f"playlist_{task_id}").replace('/', '_').replace('\\', '_')
        playlist_dir = os.path.join(downloads_dir, title)
        os.makedirs(playlist_dir, exist_ok=True)

        ext = 'mp3' if stream_type == 'audio' else 'mp4'
        output_template = os.path.join(playlist_dir, '%(playlist_index)03d - %(title).50s.%(ext)s')
        print(f"[{task_id}] 📂 Playlist saving to: {playlist_dir}")

        ydl_opts = common_ydl_opts(task_id, output_template, ext, stream_type, quality)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        thumbnail_path = tasks.get(task_id, {}).get("thumbnail_path")
        if not thumbnail_path:
            thumbnail_url = info.get("thumbnail")
            thumbnail_path = download_thumbnail(thumbnail_url, task_id)

        with task_lock:
            if tasks[task_id].get('should_abort'):
                tasks[task_id]['progress'] = "Aborted"
                tasks[task_id]['status'] = 'aborted'
            else:
                tasks[task_id]['filename'] = playlist_dir
                tasks[task_id]['progress'] = '100%'
                tasks[task_id]['status'] = 'completed'
                if thumbnail_path:
                    tasks[task_id]['thumbnail_path'] = thumbnail_path
            save_tasks()

    except Exception as e:
        print(f"[{task_id}] ❌ Error during playlist download: {e}")
        with task_lock:
            tasks[task_id]['progress'] = f"Error: {str(e)}"
            tasks[task_id]['status'] = 'error'
            save_tasks()

def enqueue_download(task_id, video_url, quality, fmt):
    def download_task():
        print(f"[{task_id}] 🔄 Inside download_task")
        try:
            with task_lock:
                if tasks[task_id].get('paused') or tasks[task_id].get('should_abort'):
                    print(f"[{task_id}] ⏸️ Skipped (paused or aborted)")
                    return
                tasks[task_id]['status'] = 'running'
                save_tasks()

            if fmt == 'playlist':
                handle_playlist(video_url, quality, fmt, task_id)
            else:
                handle_single(video_url, quality, fmt, task_id)

        except Exception as e:
            print(f"[{task_id}] ❌ Unhandled exception in download_task: {e}")
            with task_lock:
                tasks[task_id]['progress'] = f"Error: {str(e)}"
                tasks[task_id]['status'] = 'error'
                save_tasks()

    print(f"[{task_id}] 🚀 Task submitted to thread pool.")
    executor.submit(download_task)
