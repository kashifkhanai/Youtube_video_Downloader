import os
import yt_dlp
import shutil
import glob
import requests
from pathlib import Path
from threading import Event
import threading

from task_store import tasks, save_tasks, task_lock
from utils import (
    get_output_template,
    get_format_string,
    get_postprocessors,
    generate_progress_hook
)

# Paths
downloads_dir = str(Path.home() / "Downloads")
temp_dir = os.path.join(os.getcwd(), "temp_downloads")
os.makedirs(temp_dir, exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)


# ------------------------
# Utility Functions
# ------------------------

def delete_temp_files(task_id, base_path):
    base = os.path.splitext(base_path)[0]
    patterns = [
        f"{base}.*.f*", f"{base}.m4a", f"{base}.mp4", f"{base}.mp3",
        f"{base}.part", f"{base}.webm", f"{base}.frag*"
    ]
    for pattern in patterns:
        for temp_file in glob.glob(pattern):
            try:
                os.remove(temp_file)
                print(f"[{task_id}] 🧹 Deleted temp file: {temp_file}")
            except Exception as e:
                print(f"[{task_id}] ⚠️ Failed to delete temp file {temp_file}: {e}")


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


def check_abort(task_id):
    with task_lock:
        task = tasks.get(task_id)
        if task and (task.get("should_abort") or task.get("paused")):
            raise yt_dlp.utils.DownloadCancelled()


# ------------------------
# Main Download Function
# ------------------------

def enqueue_custom_download(task_id, video_url, quality, fmt):
    def download():
        ext = 'mp3' if fmt == 'audio' else 'mp4'
        temp_output_template = get_output_template(temp_dir, fmt)
        base_template = os.path.splitext(temp_output_template)[0]

        ydl_opts = {
            'format': get_format_string(quality, fmt),
            'outtmpl': temp_output_template,
            'merge_output_format': ext,
            'continuedl': True,
            'ignoreerrors': True,
            'retries': 10,
            'fragment_retries': 10,
            'noplaylist': (fmt != 'playlist'),
            'progress_hooks': [generate_progress_hook(task_id)],
            'postprocessor_hooks': [lambda d: check_abort(task_id)],
            'postprocessors': get_postprocessors(fmt),
            'quiet': True,
            'nopart': False,
            'concurrent_fragment_downloads': 1
        }

        try:
            with task_lock:
                task = tasks.get(task_id)
                if not task or task.get("should_abort"):
                    print(f"[{task_id}] 🚩 Aborted before start.")
                    delete_temp_files(task_id, base_template)
                    return

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"[{task_id}] 🎥 Downloading...")
                info = ydl.extract_info(video_url, download=True)
                if not info:
                    print(f"[{task_id}] ❌ No info extracted.")
                    delete_temp_files(task_id, base_template)
                    return

                base = os.path.splitext(ydl.prepare_filename(info))[0]
                temp_file = f"{base}.{ext}"

                with task_lock:
                    task = tasks.get(task_id)
                    if not task or task.get("should_abort") or task.get("status") == "deleted":
                        print(f"[{task_id}] ❌ Aborted mid-download.")
                        delete_temp_files(task_id, base)
                        return

                # Save to Downloads folder
                base_name = os.path.splitext(os.path.basename(base))[0]
                final_path = os.path.join(downloads_dir, f"{base_name}.{ext}")
                counter = 1
                while os.path.exists(final_path):
                    final_path = os.path.join(downloads_dir, f"{base_name}_{counter}.{ext}")
                    counter += 1

                if os.path.exists(temp_file):
                    shutil.move(temp_file, final_path)
                else:
                    print(f"[{task_id}] ❌ Missing file during move.")
                    final_path = None

                delete_temp_files(task_id, base)

                with task_lock:
                    if not task:
                        return
                    if task.get("should_abort") or task.get("paused"):
                        task['progress'] = "Aborted"
                        task['status'] = 'aborted'
                    else:
                        if final_path:
                            task['filename'] = final_path
                            task['progress'] = '100%'
                            task['status'] = 'completed'
                        else:
                            task['progress'] = 'Paused'
                            task['status'] = 'paused'

                    if not task.get("thumbnail_path"):
                        thumb = download_thumbnail(info.get("thumbnail"), task_id)
                        if thumb:
                            task['thumbnail_path'] = thumb

                    save_tasks()

        except yt_dlp.utils.DownloadCancelled:
            print(f"[{task_id}] ❌ Cancelled by user.")
            with task_lock:
                if task_id in tasks and tasks[task_id].get("status") == "deleted":
                    print(f"[{task_id}] 🧹 Cleanup after cancel+delete.")
                    delete_temp_files(task_id, base_template)
                    thumb = tasks[task_id].get("thumbnail_path")
                    if thumb and os.path.exists(thumb):
                        os.remove(thumb)
                    tasks.pop(task_id, None)
                    save_tasks()

        except Exception as e:
            print(f"[{task_id}] ❌ Error: {e}")
            with task_lock:
                if task_id in tasks:
                    tasks[task_id]['progress'] = f"Error: {str(e)}"
                    tasks[task_id]['status'] = 'error'
                    save_tasks()

    Event().set()
    threading.Thread(target=download, daemon=True).start()


# ------------------------
# Exported Symbols
# ------------------------

__all__ = ['enqueue_custom_download', 'delete_temp_files']
