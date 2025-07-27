import os
import json
import glob
from threading import RLock
import time

TASKS_FILE = "tasks.json"
tasks = {}
task_lock = RLock()


def load_tasks():
    """📥 Load all tasks from disk"""
    global tasks
    if not os.path.exists(TASKS_FILE):
        print("No tasks.json found. Starting with empty task list.")
        return

    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                print("tasks.json is empty. Starting fresh.")
                return

            parsed_data = json.loads(content)
            if isinstance(parsed_data, dict):
                with task_lock:
                    tasks.clear()
                    tasks.update(parsed_data)
                print(f"✅ Loaded {len(tasks)} tasks from disk.")
            else:
                print("⚠️ Invalid tasks.json structure.")
    except Exception as e:
        print(f"[ERROR] Failed to load tasks: {e}")
        with task_lock:
            tasks.clear()


def save_tasks():
    """💾 Save tasks safely to disk"""
    try:
        with task_lock:
            tmp_file = TASKS_FILE + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(tasks, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, TASKS_FILE)
    except Exception as e:
        print(f"[ERROR] Failed to save tasks: {e}")


def add_task(task_id, task_data):
    """➕ Add new task to memory + disk"""
    with task_lock:
        tasks[task_id] = task_data
    save_tasks()


def update_task(task_id, updates):
    """📝 Update an existing task"""
    with task_lock:
        if task_id in tasks:
            tasks[task_id].update(updates)
    save_tasks()


def delete_temp_files_for_task(task):
    """🧹 Delete .part, .f*, .m4a, .frag* from temp_downloads"""
    video_id = task.get("video_id")
    title = task.get("title", "")
    deleted = False
    search_patterns = []

    if video_id:
        search_patterns.extend([
            f"temp_downloads/*{video_id}*.part",
            f"temp_downloads/*{video_id}*.f*",
            f"temp_downloads/*{video_id}*.m4a",
            f"temp_downloads/*{video_id}*.frag*"
        ])

    if title:
        search_patterns.append(f"temp_downloads/{title}*")

    for pattern in search_patterns:
        for file in glob.glob(pattern):
            try:
                os.remove(file)
                print(f"🧹 Deleted temp file: {file}")
                deleted = True
            except Exception as e:
                print(f"⚠️ Failed to delete temp file {file}: {e}")

    return deleted


def delete_task(task_id):
    """
    🗑️ Full delete of task: abort, temp files, thumbnail
    """
    with task_lock:
        task = tasks.get(task_id)
        if not task:
            return

        
        task["should_abort"] = True

    
    time.sleep(0.5)  # Allow hooks to process the abort signal

    with task_lock:
        task = tasks.get(task_id)
        if not task:
            return

        # Delete thumbnail if exists
        thumb_path = task.get("thumbnail_path")
        if thumb_path:
            # Convert relative path if necessary
            if thumb_path.startswith("/thumbnails/"):
                thumb_path = thumb_path.lstrip("/")
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                    print(f"[{task_id}] 🗑️ Deleted thumbnail: {thumb_path}")
                except Exception as e:
                    print(f"[{task_id}] ⚠️ Failed to delete thumbnail: {e}")

        # Remove all associated temp files
        delete_temp_files_for_task(task)

        # Remove from task list
        del tasks[task_id]
        save_tasks()


def get_all_tasks():
    """📤 Return all task copies with resolved thumbnail URLs"""
    with task_lock:
        result = {}
        for task_id, task in tasks.items():
            task_copy = task.copy()

            # Convert internal thumbnail_path to frontend-accessible thumbnail_url
            path = task_copy.get("thumbnail_path")
            if path and os.path.exists(path):
                if not path.startswith("/thumbnails/"):
                    path = "/" + path.replace("\\", "/").lstrip("/")
                task_copy["thumbnail_url"] = path
            else:
                task_copy["thumbnail_url"] = "/static/images/default-thumbnail.png"

            result[task_id] = task_copy
        return result
