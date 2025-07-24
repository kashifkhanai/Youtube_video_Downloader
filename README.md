# 🎬 YouTube Video Downloader

A professional, browser-based YouTube video downloader built with Python (Flask), supporting playlists, resolution/format selection, real-time progress, pause/resume functionality, and persistent download management.

---

## 📌 Features

- 🎥 Download single videos or entire playlists.
- 🎚️ Choose resolution (144p to 1080p) and format (Video/Audio).
- ⏸️ Pause, resume, delete, or bulk-control tasks.
- 🔄 Automatic resume from partial downloads.
- 📂 Thumbnails saved and displayed for all tasks.
- ✅ Full support for repeated downloads of same video.
- 📁 Persistent storage (JSON-based) of all download tasks.
- 📱 Mobile & desktop responsive interface using Bootstrap.
- 📦 Clean folder structure for easy navigation and deployment.

---

## 🛠️ Technologies Used

- **Backend**: Python, Flask
- **Downloader Core**: yt-dlp
- **Frontend**: HTML, CSS, Bootstrap 5, Vanilla JS
- **Data Store**: JSON (persistent tasks)
- **Others**: Threads, SSE (Server-Sent Events), Templates, File I/O

---

## 🚀 How to Run the Project

### 1. 📥 Clone the Repository

```bash
git clone https://github.com/yourusername/youtube_video_downloader.git
cd youtube_video_downloader
```

### 2. 🐍 Create Virtual Environment

```bash
python3 -m venv downloader_env
source downloader_env/bin/activate
```

### 3. 📦 Install Dependencies

```bash
pip install -r requirements.txt
```

> Make sure `ffmpeg` is installed on your system and accessible via PATH.

### 4. ▶️ Run the Application

```bash
python app.py

```

Then open your browser and visit:

```baash
http://127.0.0.1:5000/

```

---

## ⚙️ Folder Structure

```bash
youtube_video_downloader/
│
├── app.py                  # Main Flask app
├── download_manager.py     # Download logic and control
├── task_store.py           # Persistent task management (JSON)
├── utils.py                # Helper functions
├── requirements.txt
├── logs.txt                # Error and debug logs
├── tasks.json              # Stored task metadata
│
├── templates/
│   └── platform/
│       ├── youtube.html    # Main download interface
│       ├── tasks.html      # Task manager UI
│       ├── contact.html    # Contact page
│       └── privacy.html    # Privacy policy page
│
├── static/
│   ├── images/             # Icons & thumbnails
│   │   ├── youtube.png
│   │   └── default-thumbnail.png
│   └── youtube.css         # Centralized custom styling
│
├── downloads/              # Final downloaded files
└── thumbnails/             # Thumbnail cache
```

---

## 💡 Usage

1. Paste a YouTube video or playlist link.
2. Wait for detection (playlist videos stream in one by one).
3. Choose format and quality for each video.
4. Select videos (all are selected by default).
5. Click **Download Selected**.
6. Go to the **Tasks** tab to monitor or manage them.

---

## 📩 Contact

For feedback, issues, or suggestions, please email:  
📧 <support@example.com>  
Or visit the [Contact Us](/contact) page inside the app.

---

## 👨‍💻 Author

**Kashif Khan**  
Developer & UI Designer  
Location: Pakistan 🇵🇰  
GitHub: [@yourusername](https://github.com/yourusername)

---

## 📄 License

This project is licensed under the **MIT License**.  
You are free to use, modify, and distribute with proper attribution.
