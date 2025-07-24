import os
import time

last_update_times = {}

def get_output_template(filename_dir, stream_type):
    """Download file ka output path/template"""
    if not filename_dir:
        filename_dir = os.getcwd()

    # 🛠️ Use ID to prevent overwrite: allow same video to download again
    return os.path.join(filename_dir, '%(title).50s_%(id)s.%(ext)s')


def get_postprocessors(stream_type):
    """Audio/Video ke liye postprocessors"""
    if stream_type == 'audio':
        return [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }]
    elif stream_type == 'video':
        return [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4'  # ✅ fixed typo
        }]
    return []


def get_format_string(quality, stream_type):
    """yt-dlp format string generator based on quality/stream"""
    if stream_type == 'audio':
        return 'bestaudio[ext=m4a]/bestaudio'
    elif stream_type in ('video', 'playlist'):
        try:
            int(quality)
            return (
                f"bestvideo[ext=mp4][vcodec^=avc1][height<={quality}]+"
                f"bestaudio[ext=m4a]/best[ext=mp4]/best"
            )
        except:
            return "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    else:
        return "bestvideo+bestaudio"


def format_eta(seconds):
    """ETA ko readable time format me convert karo"""
    if not seconds or seconds < 0:
        return "N/A"
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hrs:02}:{mins:02}:{secs:02}" if hrs > 0 else f"{mins:02}:{secs:02}"


def generate_progress_hook(task_id):
    """Download progress ko real-time update karo"""
    from task_store import tasks, save_tasks, task_lock

    def hook(d):
        current_time = time.time()
        last_time = last_update_times.get(task_id, 0)
        if current_time - last_time < 0.5:
            return

        with task_lock:
            task = tasks.get(task_id)
            if not task:
                return

            if task.get("should_abort"):
                raise Exception("Download aborted manually")
            if task.get("paused"):
                raise Exception("Download paused manually")

            status = d.get("status")
            if status == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                percent = (downloaded / total) * 100 if total else 0
                task['progress'] = f"{percent:.2f}%"
                task['downloaded_bytes'] = downloaded
                task['total_bytes'] = total
                speed = d.get('speed')
                task['speed'] = f"{(speed / 1024):.2f} KBps" if speed else "N/A"
                task['eta'] = format_eta(d.get('eta')) if d.get('eta') else "N/A"

            elif status == 'finished':
                task['progress'] = '100%'
                task['status'] = 'completed'
                task['filename'] = d.get('filename')

            # ✅ Update thumbnail only if no saved thumbnail_path
            if 'thumbnail' in d and d['thumbnail'] and not task.get("thumbnail_path"):
                task['thumbnail'] = d['thumbnail']

            save_tasks()
            last_update_times[task_id] = current_time

    return hook
