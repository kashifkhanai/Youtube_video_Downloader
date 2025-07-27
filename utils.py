import os
import time
import yt_dlp
from task_store import tasks, save_tasks, task_lock

last_update_times = {}


def get_output_template(filename_dir, stream_type):
    """📁 Returns yt-dlp output template path based on stream type"""
    if not filename_dir:
        filename_dir = os.getcwd()
    
    return os.path.join(filename_dir, '%(title).50s_%(id)s.%(ext)s')


def get_postprocessors(stream_type):
    """🔄 Postprocessing config for audio/video conversion"""
    if stream_type == 'audio':
        return [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }]
    elif stream_type == 'video':
        return [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4'
        }]
    return []


def get_format_string(quality, stream_type):
    """🎚 Format string for yt-dlp based on quality input"""
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
    
    return "bestvideo+bestaudio"


def format_eta(seconds):
    """⏳ Convert ETA seconds to human-readable string"""
    if not seconds or seconds < 0:
        return "N/A"
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hrs:02}:{mins:02}:{secs:02}" if hrs else f"{mins:02}:{secs:02}"


def can_start_new_task():
    """Check if less than 4 downloads are currently running"""
    with task_lock:
        return sum(1 for t in tasks.values() if t.get('status') == 'running') < 4


def generate_progress_hook(task_id):
    """⚙️ Generates yt-dlp progress hook for a specific task"""

   
    def hook(d):
        current_time = time.time()
        last_time = last_update_times.get(task_id, 0)
        if current_time - last_time < 0.5:
            return

        with task_lock:
            task = tasks.get(task_id)
            if not task:
                return

            # 🛑 Abort/Pause/Delete Logic
            if task.get("should_abort") or task.get("paused") or task.get("status") == "deleted":
                print(f"[{task_id}] ❌ Download cancelled due to abort/pause/delete.")
                
                part_path = d.get("filename")
                if part_path and os.path.exists(part_path):
                    try:
                        os.remove(part_path)
                        print(f"[{task_id}] 🗑️ Deleted part file: {part_path}")
                    except Exception as e:
                        print(f"[{task_id}] ⚠️ Could not delete part file: {e}")
                
                raise yt_dlp.utils.DownloadCancelled()

            # 🔄 Update Progress
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
                task['progress'] = 'Post-processing'
                task['status'] = 'processing'

            # 🔍 Thumbnail
            if 'thumbnail' in d and d['thumbnail'] and not task.get("thumbnail"):
                task['thumbnail'] = d['thumbnail']

            save_tasks()
            last_update_times[task_id] = current_time

            # ✅ Trigger next task if finished
            if status == 'finished':
                try:
                    from download_manager import enqueue_download  # ✅ safe to import here
                    for next_id, t in tasks.items():
                        if t['status'] == 'queued' and not t.get('paused') and can_start_new_task():
                            t['status'] = 'running'
                            enqueue_download(next_id, t['url'], t['quality'], t['format'])
                            break
                except Exception as e:
                    print(f"[{task_id}] ⚠️ Failed to queue next task: {e}")

    return hook
