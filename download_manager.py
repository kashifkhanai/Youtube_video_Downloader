import os
import yt_dlp
import requests
import logging
import shutil
import glob
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from task_store import tasks, save_tasks, task_lock
from utils import (
    get_output_template,
    get_format_string,
    get_postprocessors,
    generate_progress_hook
)

logging.basicConfig(level=logging.DEBUG)


downloads_dir = str(Path.home() / "Downloads")
temp_dir = os.path.join(os.getcwd(), "temp_downloads")
os.makedirs(temp_dir, exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)




executor = ThreadPoolExecutor(max_workers=4)

def download_thumbnail(thumbnail_url, task_id):
    try:
        if not thumbnail_url:
            return None
        ext = os.path.splitext(thumbnail_url.split("?")[0])[1]
        filename = f"{task_id}{ext}"
        path = os.path.join("thumbnails", filename)
        
        if os.path.exists(path):
            return path

        r = requests.get(thumbnail_url, timeout=5)
        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            return path
    except Exception as e:
        print(f"[Thumbnail Warning] {e}")
    return None

def delete_temp_files(task_id, base_path):
    base = os.path.splitext(base_path)[0]
    patterns = [f"{base}.*.f*", f"{base}.m4a", f"{base}.part", f"{base}.frag*"]
    for pattern in patterns:
        for temp_file in glob.glob(pattern):
            try:
                os.remove(temp_file)
                print(f"[{task_id}] 🧹 Deleted temp file: {temp_file}")
            except Exception as e:
                print(f"[{task_id}] ⚠️ Failed to delete temp file {temp_file}: {e}")

def common_ydl_opts(task_id, output_template, ext, stream_type, quality):
    def post_hook(d):
        with task_lock:
            task = tasks.get(task_id)
            if task and (task.get("should_abort") or task.get("paused")):
                raise yt_dlp.utils.DownloadCancelled()

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
        'postprocessor_hooks': [post_hook],
        'postprocessors': get_postprocessors(stream_type),
        'quiet': True,
        'nopart': False,
        'concurrent_fragment_downloads': 1
    }

def handle_single(video_url, quality, stream_type, task_id):
    ext = 'mp3' if stream_type == 'audio' else 'mp4'
    temp_output_template = get_output_template(temp_dir, stream_type)
    print(f"[{task_id}] 📂 Saving to temp: {temp_output_template}")

    ydl_opts = common_ydl_opts(task_id, temp_output_template, ext, stream_type, quality)

    try:
        with task_lock:
            task = tasks.get(task_id)
            if not task or task.get("should_abort"):
                print(f"[{task_id}] 🛑 Aborted before download started.")
                return

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"[{task_id}] 🎥 Starting download...")
            info = ydl.extract_info(video_url, download=True)

            if not info:
                print(f"[{task_id}] ❌ No info extracted.")
                return

            base = os.path.splitext(ydl.prepare_filename(info))[0]
            temp_file = f"{base}.{ext}"

            with task_lock:
                task = tasks.get(task_id)
                if not task or task.get("should_abort") or task.get("status") == "deleted":
                    print(f"[{task_id}] ❌ Aborted after download.")
                    delete_temp_files(task_id, base)
                    return


            # Move to Downloads folder
            base_name = os.path.splitext(os.path.basename(base))[0]
            final_file = os.path.join(downloads_dir, f"{base_name}.{ext}")
            counter = 1
            while os.path.exists(final_file):
                final_file = os.path.join(downloads_dir, f"{base_name}_{counter}.{ext}")
                counter += 1

            try:
                shutil.move(temp_file, final_file)
            except Exception as e:
                print(f"[{task_id}] ⚠️ Could not move file: {e}")
                final_file = None

            delete_temp_files(task_id, base)

            with task_lock:
                if not task:
                    return
                if task.get("should_abort") or task.get("paused"):
                    task['progress'] = "Aborted"
                    task['status'] = 'aborted'
                else:
                    if final_file:
                        task['filename'] = final_file
                        task['progress'] = '100%'
                        task['status'] = 'completed'
                    else:
                        task['progress'] = 'Paused'
                        task['status'] = 'paused'

                if not task.get("thumbnail_path"):
                    thumb_url = info.get("thumbnail")
                    thumb = download_thumbnail(thumb_url, task_id)
                    if thumb:
                        task['thumbnail_path'] = thumb

                save_tasks()

    except yt_dlp.utils.DownloadCancelled:
        print(f"[{task_id}] ❌ Manually cancelled (pause, delete, or shutdown).")
        with task_lock:
            if task_id in tasks:
                if tasks[task_id].get("status") == "deleted":
                    print(f"[{task_id}] 🧹 Cancelled + marked for deletion.")
                    delete_temp_files(task_id, get_output_template(temp_dir, stream_type))
                    thumb = tasks[task_id].get("thumbnail_path")
                    if thumb and os.path.exists(thumb):
                        os.remove(thumb)
                        print(f"[{task_id}] 🗑️ Deleted thumbnail: {thumb}")
                    tasks.pop(task_id, None)
                    save_tasks()
    except Exception as e:
        print(f"[{task_id}] ❌ Download error: {e}")
        with task_lock:
            if task_id in tasks:
                tasks[task_id]['progress'] = f"Error: {str(e)}"
                tasks[task_id]['status'] = 'error'
                save_tasks()

def enqueue_download(task_id, video_url, quality, fmt):
    start_event = Event()

    def download_task():
        print(f"[{task_id}] 🧵 Starting download thread")
        start_event.set()

        try:
            with task_lock:
                task = tasks.get(task_id)
                if not task:
                    print(f"[{task_id}] ❌ Task not found.")
                    return
                if task.get("paused") or task.get("should_abort"):
                    print(f"[{task_id}] ⏸️ Skipped (paused or aborted)")
                    return
                task['status'] = 'running'
                save_tasks()

            if fmt == 'playlist':
                print(f"[{task_id}] 📂 Playlist not supported yet.")
                return

            handle_single(video_url, quality, fmt, task_id)

            
            with task_lock:
                task = tasks.get(task_id)
                if task and task.get("status") == "deleted":
                    print(f"[{task_id}] 🧹 Cleaning up deleted task...")
                    delete_temp_files(task_id, get_output_template(temp_dir, fmt))
                    thumb = task.get("thumbnail_path")
                    if thumb and os.path.exists(thumb):
                        os.remove(thumb)
                        print(f"[{task_id}] 🗑️ Deleted thumbnail: {thumb}")
                    tasks.pop(task_id, None)
                    save_tasks()

        except Exception as e:
            print(f"[{task_id}] ❌ Thread error: {e}")
            with task_lock:
                if task_id in tasks:
                    tasks[task_id]['progress'] = f"Error: {str(e)}"
                    tasks[task_id]['status'] = 'error'
                    save_tasks()

    
    executor.submit(download_task)
    start_event.wait()
    print(f"[{task_id}] 🚀 Task submitted.")
