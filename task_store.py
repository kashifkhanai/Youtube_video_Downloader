import os
import json
from threading import RLock

TASKS_FILE = "tasks.json"
tasks = {}
task_lock = RLock()


def load_tasks():
    """tasks.json se tasks load karo"""
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
                print("⚠️ Invalid tasks.json structure. Starting with empty.")
    except Exception as e:
        print(f"[ERROR] Failed to load tasks: {e}")
        with task_lock:
            tasks.clear()


def save_tasks():
    """Thread-safe save to disk (atomically)"""
    try:
        with task_lock:
            tmp_file = TASKS_FILE + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(tasks, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, TASKS_FILE)
    except Exception as e:
        print(f"[ERROR] Failed to save tasks: {e}")


def add_task(task_id, task_data):
    """Naya task add karo"""
    with task_lock:
        tasks[task_id] = task_data
    save_tasks()


def update_task(task_id, updates):
    """Existing task update karo"""
    with task_lock:
        if task_id in tasks:
            tasks[task_id].update(updates)
    save_tasks()


def delete_task(task_id):
    """Task permanently delete karo (but keep downloaded file)"""
    with task_lock:
        task = tasks.get(task_id)
        if not task:
            return

        # ✅ Delete thumbnail only
        thumb_path = task.get("thumbnail_path")
        if thumb_path and os.path.exists(thumb_path):
            try:
                os.remove(thumb_path)
                print(f"[{task_id}] 🗑️ Deleted thumbnail: {thumb_path}")
            except Exception as e:
                print(f"[{task_id}] ⚠️ Failed to delete thumbnail: {e}")

        # ❌ Do NOT delete downloaded video/audio
        del tasks[task_id]
        save_tasks()


def get_all_tasks():
    """Return all tasks with thumbnail URLs"""
    with task_lock:
        result = {}
        for task_id, task in tasks.items():
            task_copy = task.copy()

            thumb = task_copy.get("thumbnail_path")
            if thumb and os.path.exists(thumb):
                task_copy["thumbnail_url"] = "/" + thumb.replace("\\", "/").lstrip("/")
            else:
                task_copy["thumbnail_url"] = "/static/images/default-thumbnail.png"

            result[task_id] = task_copy
        return result
