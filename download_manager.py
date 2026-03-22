#!/usr/bin/env python3
# Linux Download Manager
# Copyright (c) 2026 Tanjim — tpodbcs@gmail.com
# All rights reserved. See LICENSE.txt for details.

import sys, requests, time, os, threading, queue, subprocess, re, shutil, json
import yt_dlp
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, unquote
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMenu,
    QMessageBox, QListWidget, QListWidgetItem, QLabel, QAbstractItemView,
    QStyledItemDelegate, QStyle, QMenuBar,
    QDialog, QComboBox, QRadioButton, QGroupBox,
    QProgressBar, QTextEdit, QSizePolicy,
    QGraphicsOpacityEffect
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QSize, QRect
from PyQt6.QtGui import (
    QIcon, QColor, QFont, QPainter, QAction, QPixmap,
    QLinearGradient, QPalette
)

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME, ".config", "ldm")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

os.makedirs(CONFIG_DIR, exist_ok=True)



# ── Theme definitions ────────────────────────────────────────────────────────
THEMES = {
    "light": {
        "bg":                "#ffffff",
        "sidebar":           "#f8fafc",
        "border":            "#e2e8f0",
        "text":              "#1e293b",
        "muted":             "#64748b",
        "faint":             "#94a3b8",
        "alt_row":           "#f8fafc",
        "selected":          "#dbeafe",
        "selected_text":     "#1e293b",
        "header":            "#f8fafc",
        "menu_bg":           "#f8fafc",
        "menu_hover":        "#eff6ff",
        "menu_hover_text":   "#2563eb",
        "input_bg":          "#f8fafc",
        "input_focus":       "#ffffff",
        "progress_track":    "#e2e8f0",
        "scrollbar":         "#f8fafc",
        "scrollbar_handle":  "#cbd5e1",
        "grid":              "#f1f5f9",
        "status_bar":        "#f8fafc",
        "category_hover":    "#f1f5f9",
        "category_hover_text": "#334155",
        "category_sel":      "#eff6ff",
        "category_sel_text": "#2563eb",
    },
    "dark": {
        "bg":                "#1e293b",
        "sidebar":           "#0f172a",
        "border":            "#334155",
        "text":              "#e2e8f0",
        "muted":             "#94a3b8",
        "faint":             "#475569",
        "alt_row":           "#162032",
        "selected":          "#1e3a5f",
        "selected_text":     "#e2e8f0",
        "header":            "#0f172a",
        "menu_bg":           "#1e293b",
        "menu_hover":        "#1e3a5f",
        "menu_hover_text":   "#60a5fa",
        "input_bg":          "#0f172a",
        "input_focus":       "#1e293b",
        "progress_track":    "#334155",
        "scrollbar":         "#1e293b",
        "scrollbar_handle":  "#475569",
        "grid":              "#334155",
        "status_bar":        "#0f172a",
        "category_hover":    "#1e293b",
        "category_hover_text": "#cbd5e1",
        "category_sel":      "#1e3a5f",
        "category_sel_text": "#60a5fa",
    }
}

file_types = {
    "Videos":     ["mp4", "mkv", "avi", "mov", "webm", "ts"],
    "Music":      ["mp3", "flac", "aac", "wav", "ogg", "m4a"],
    "Documents":  ["pdf", "doc", "docx", "txt", "ppt", "pptx"],
    "Compressed": ["zip", "rar", "7z", "tar", "gz"],
    "Programs":   ["exe", "bin", "appimage", "deb", "rpm"]
}

CATEGORIES = [
    ("All Downloads", "⬇", "#2563eb"),
    ("Videos",        "🎬", "#dc2626"),
    ("Music",         "🎵", "#7c3aed"),
    ("Documents",     "📄", "#d97706"),
    ("Compressed",    "🗜", "#059669"),
    ("Programs",      "⚙",  "#4f46e5"),
    ("Others",        "📦", "#6b7280"),
]

def choose_folder(filename):
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    for folder, extensions in file_types.items():
        if ext in extensions:
            path = os.path.join(HOME, "Downloads", folder)
            os.makedirs(path, exist_ok=True)
            return path
    path = os.path.join(HOME, "Downloads", "Others")
    os.makedirs(path, exist_ok=True)
    return path

def get_category(filename):
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    for folder, extensions in file_types.items():
        if ext in extensions:
            return folder
    return "Others"

def get_file_icon(filename):
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    icon_map = {
        "mp4": "video-x-generic", "mkv": "video-x-generic",
        "avi": "video-x-generic", "mov": "video-x-generic",
        "webm": "video-x-generic", "ts": "video-x-generic",
        "mp3": "audio-x-generic", "flac": "audio-x-generic",
        "aac": "audio-x-generic", "wav": "audio-x-generic",
        "ogg": "audio-x-generic", "m4a": "audio-x-generic",
        "pdf": "application-pdf",
        "doc": "application-msword", "docx": "application-msword",
        "txt": "text-x-generic",
        "ppt": "application-vnd.ms-powerpoint",
        "pptx": "application-vnd.ms-powerpoint",
        "zip": "application-zip", "rar": "application-zip",
        "7z": "application-zip", "tar": "application-zip",
        "gz": "application-zip",
        "exe": "application-x-executable",
        "deb": "application-x-deb",
        "rpm": "application-x-rpm",
        "appimage": "application-x-executable",
    }
    theme_name = icon_map.get(ext, "text-x-generic")
    icon = QIcon.fromTheme(theme_name)
    if icon.isNull():
        icon = QIcon.fromTheme("text-x-generic")
    return icon

def is_youtube_url(url):
    lower = url.lower()
    return any(x in lower for x in ["youtube.com/watch", "youtu.be/", "youtube.com/shorts"])

def format_eta(seconds):
    if seconds <= 0 or seconds > 86400:
        return "—"
    elif seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds//60)}m {int(seconds%60)}s"
    else:
        return f"{int(seconds//3600)}h {int((seconds%3600)//60)}m"

def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass

def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "dark_mode": False,
        "notifications": True,
    }

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass



url_queue = queue.Queue()

def open_and_select(path):
    """
    Open the file manager and select the specific file.
    Uses DBus FileManager1 interface (works on Zorin/GNOME/Nautilus).
    Falls back to xdg-open on the folder if DBus is unavailable.
    """
    if not path:
        return
    # Try DBus FileManager1 ShowItems (selects the file in the manager)
    try:
        file_uri = 'file://' + os.path.abspath(path)
        subprocess.Popen([
            'dbus-send', '--session',
            '--dest=org.freedesktop.FileManager1',
            '--type=method_call',
            '/org/freedesktop/FileManager1',
            'org.freedesktop.FileManager1.ShowItems',
            f'array:string:{file_uri}',
            'string:'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    except Exception:
        pass
    # Fallback: open folder (file not selected but at least folder opens)
    folder = os.path.dirname(path)
    if folder and os.path.exists(folder):
        subprocess.Popen(['xdg-open', folder])

def normalize_stream_url(url):
    """
    Strip embed path prefixes (/e/, /embed/) that iframe players add.
    e.g. https://luluvdo.com/e/abc123 → https://luluvdo.com/abc123
    """
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        # Replace /e/ID or /embed/ID with /ID
        clean = re.sub(r'^/e/', '/', p.path)
        clean = re.sub(r'^/embed/', '/', clean)
        if clean != p.path:
            return urlunparse(p._replace(path=clean))
    except Exception:
        pass
    return url

class BridgeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Serve PAC file for Firefox proxy auto-config
            if self.path == '/proxy.pac' or self.path.startswith('/proxy.pac?'):
                try:
                    with open(PAC_FILE, 'rb') as f:
                        pac_data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/x-ns-proxy-autoconfig')
                    self.send_header('Content-Length', str(len(pac_data)))
                    self.end_headers()
                    self.wfile.write(pac_data)
                except Exception:
                    self.send_response(404); self.end_headers()
                return
            q = parse_qs(urlparse(self.path).query)
            url = q.get("url", [None])[0]
            filename = q.get("filename", [None])[0]
            msg_type = q.get("type", ["file"])[0]
            referer = q.get("referer", [""])[0]
            if url:
                url_queue.put((url, filename, msg_type, referer))
                self.send_response(200); self.end_headers()
                self.wfile.write(b"OK")
        except Exception:
            self.send_response(500); self.end_headers()

    def log_message(self, *args): pass

def start_bridge_server(port=9999):
    server = HTTPServer(("127.0.0.1", port), BridgeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

def format_size(bytes_count):
    if not bytes_count or bytes_count <= 0:
        return "—"
    elif bytes_count < 1024:
        return f"{bytes_count} B"
    elif bytes_count < 1024 ** 2:
        return f"{bytes_count / 1024:.1f} KB"
    elif bytes_count < 1024 ** 3:
        return f"{bytes_count / (1024 ** 2):.1f} MB"
    else:
        return f"{bytes_count / (1024 ** 3):.2f} GB"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}

CURL_DOMAINS = [
    "claude.ai", "anthropic.com",
    "chat.openai.com", "chatgpt.com",
    "drive.google.com", "docs.google.com",
    "dropbox.com", "sharepoint.com",
    "onedrive.live.com",
]

def needs_curl(url):
    lower = url.lower()
    return any(d in lower for d in CURL_DOMAINS)


# ── Progress bar delegate ────────────────────────────────────────────────────
class ProgressDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shimmer_timer = QTimer()
        self._shimmer_timer.timeout.connect(self._tick)
        self._shimmer_timer.start(40)

    def _tick(self):
        if self.parent() and self.parent().viewport():
            self.parent().viewport().update()

    def paint(self, painter, option, index):
        value = index.data(Qt.ItemDataRole.UserRole + 1)
        if value is None:
            super().paint(painter, option, index)
            return

        dark = index.data(Qt.ItemDataRole.UserRole + 3)
        if dark:
            bg_even  = QColor("#1e293b")
            bg_odd   = QColor("#162032")
            sel_color = QColor("#1e3a5f")
            track_color = QColor("#334155")
        else:
            bg_even  = QColor("#ffffff")
            bg_odd   = QColor("#f8fafc")
            sel_color = QColor("#dbeafe")
            track_color = QColor("#e2e8f0")

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, sel_color)
        else:
            painter.fillRect(option.rect, bg_even if index.row() % 2 == 0 else bg_odd)

        bar_rect = option.rect.adjusted(8, 6, -8, -6)
        bar_h = bar_rect.height()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(bar_rect, 2, 2)

        if value > 0:
            filled_w = int(bar_rect.width() * value / 100)
            filled_rect = QRect(bar_rect.x(), bar_rect.y(), filled_w, bar_rect.height())
            color = QColor("#16a34a") if value >= 100 else QColor("#22c55e")
            painter.setBrush(color)
            painter.drawRoundedRect(filled_rect, 2, 2)

            # Shimmer on active downloads
            if 0 < value < 100 and filled_w > 0:
                phase = (time.time() % 1.2) / 1.2
                shimmer_w = max(30, filled_w // 3)
                shimmer_x = bar_rect.x() + int((filled_w - shimmer_w) * phase)
                shimmer_rect = QRect(shimmer_x, bar_rect.y(), shimmer_w, bar_rect.height())
                grad = QLinearGradient(shimmer_x, 0, shimmer_x + shimmer_w, 0)
                grad.setColorAt(0.0, QColor(255, 255, 255, 0))
                grad.setColorAt(0.5, QColor(255, 255, 255, 55))
                grad.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.setBrush(grad)
                painter.drawRoundedRect(bar_rect, 2, 2)

        text_color = QColor("#e2e8f0") if dark else QColor("#1e293b")
        painter.setPen(text_color)
        painter.setFont(QFont("sans-serif", 8, QFont.Weight.Bold))
        painter.drawText(bar_rect, Qt.AlignmentFlag.AlignCenter, f"{value}%")

    def sizeHint(self, option, index):
        return QSize(120, 36)


# ── Fetch formats thread ─────────────────────────────────────────────────────
class FetchFormatsThread(QThread):
    formats_ready = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'http_headers': {'User-Agent': HEADERS['User-Agent']},
                'cookiesfrombrowser': ('firefox',),
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if info is None:
                    self.error.emit("Could not fetch video info")
                    return
                title = info.get('title', 'video')
                self.formats_ready.emit(title)
        except Exception as e:
            self.error.emit(str(e)[:120])


# ── YouTube download thread ──────────────────────────────────────────────────
class YouTubeDownloadThread(QThread):
    progress  = pyqtSignal(int)
    speed     = pyqtSignal(str)
    size_info = pyqtSignal(str)
    eta       = pyqtSignal(str)
    log       = pyqtSignal(str)
    finished  = pyqtSignal(str)

    def __init__(self, url, ydl_opts):
        super().__init__()
        self.url = url
        self.ydl_opts = ydl_opts
        self.running = True

    def run(self):
        try:
            self.ydl_opts['progress_hooks'] = [self.hook]
            self.ydl_opts['cookiesfrombrowser'] = ('firefox',)
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if info is None:
                    raise Exception("Could not download video")
            self.finished.emit("Finished")
        except Exception as e:
            self.finished.emit(f"Error: {str(e)[:80]}")

    def hook(self, d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%', '').strip()
            try:
                self.progress.emit(int(float(p)))
            except Exception:
                pass
            self.speed.emit(d.get('_speed_str', '—'))
            dl = d.get('downloaded_bytes') or 0
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            if total:
                self.size_info.emit(f"{format_size(dl)} / {format_size(total)}")
                eta_secs = d.get('eta') or 0
                self.eta.emit(format_eta(eta_secs))
            else:
                self.size_info.emit(format_size(dl))
                self.eta.emit("—")
            self.log.emit(f"Downloading... {p}% at {d.get('_speed_str', '—')}")
        elif d['status'] == 'finished':
            self.progress.emit(100)
            self.eta.emit("—")
            self.log.emit("Processing / merging...")


# ── Dialog style ─────────────────────────────────────────────────────────────
DIALOG_STYLE = """
    QDialog { background-color: #ffffff; color: #1e293b; }
    QLabel { color: #1e293b; font-size: 13px; }
    QLineEdit {
        background-color: #f8fafc; color: #1e293b;
        border: 1px solid #e2e8f0; border-radius: 6px;
        padding: 7px 12px; font-size: 13px;
    }
    QLineEdit:focus { border: 1px solid #2563eb; background-color: #ffffff; }
    QPushButton {
        border-radius: 6px; font-size: 13px;
        font-weight: 600; padding: 8px 18px; border: none;
    }
    QComboBox {
        background-color: #f8fafc; color: #1e293b;
        border: 1px solid #e2e8f0; border-radius: 6px;
        padding: 6px 12px; font-size: 13px; min-height: 32px;
    }
    QComboBox::drop-down { border: none; }
    QComboBox QAbstractItemView {
        background-color: #ffffff; color: #1e293b;
        border: 1px solid #e2e8f0;
        selection-background-color: #eff6ff; selection-color: #2563eb;
    }
    QGroupBox {
        border: 1px solid #e2e8f0; border-radius: 6px;
        margin-top: 8px; padding: 8px;
        font-size: 12px; color: #64748b;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
    QRadioButton { color: #1e293b; font-size: 13px; spacing: 6px; }
    QTextEdit {
        background-color: #f8fafc; color: #475569;
        border: 1px solid #e2e8f0; border-radius: 6px;
        font-size: 12px; font-family: monospace; padding: 6px;
    }
    QProgressBar {
        background-color: #e2e8f0; border-radius: 4px;
        height: 8px; text-align: center;
        font-size: 11px; color: #1e293b;
    }
    QProgressBar::chunk { background-color: #22c55e; border-radius: 4px; }
"""


# ── YouTube dialog ───────────────────────────────────────────────────────────
class YouTubeDialog(QDialog):
    download_started  = pyqtSignal(str, str, str)
    download_progress = pyqtSignal(str, int, str, str, str)
    download_finished = pyqtSignal(str, str)

    def __init__(self, parent=None, prefill_url=""):
        super().__init__(parent)
        self.setWindowTitle("YouTube Downloader")
        self.setMinimumWidth(540)
        self.setMinimumHeight(480)
        self.setStyleSheet(DIALOG_STYLE)
        self.video_title = ""
        self.fetch_thread = None
        self.dl_thread = None
        self._last_size = ""
        self._last_speed = ""
        self._last_eta = ""
        self._current_url = ""
        self._build_ui()
        if prefill_url:
            self.url_input.setText(prefill_url)
            self.fetch_formats()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("YouTube Downloader")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #dc2626;")
        layout.addWidget(title)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste YouTube URL here...")
        self.fetch_btn = QPushButton("Fetch")
        self.fetch_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
            "QPushButton:disabled { background-color: #94a3b8; }"
        )
        self.fetch_btn.setFixedWidth(80)
        self.fetch_btn.clicked.connect(self.fetch_formats)
        url_row.addWidget(self.url_input)
        url_row.addWidget(self.fetch_btn)
        layout.addLayout(url_row)

        self.title_label = QLabel("")
        self.title_label.setStyleSheet("color: #64748b; font-size: 12px; font-style: italic;")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        type_group = QGroupBox("Download Type")
        type_layout = QHBoxLayout(type_group)
        self.radio_video      = QRadioButton("Video + Audio")
        self.radio_audio      = QRadioButton("Audio Only")
        self.radio_video_only = QRadioButton("Video Only")
        self.radio_video.setChecked(True)
        self.radio_audio.toggled.connect(self._on_type_changed)
        type_layout.addWidget(self.radio_video)
        type_layout.addWidget(self.radio_audio)
        type_layout.addWidget(self.radio_video_only)
        layout.addWidget(type_group)

        quality_row = QHBoxLayout()
        quality_label = QLabel("Quality:")
        quality_label.setFixedWidth(55)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Best", "1080p", "720p", "480p", "360p"])
        quality_row.addWidget(quality_label)
        quality_row.addWidget(self.quality_combo)
        layout.addLayout(quality_row)

        self.audio_fmt_widget = QWidget()
        audio_fmt_row = QHBoxLayout(self.audio_fmt_widget)
        audio_fmt_row.setContentsMargins(0, 0, 0, 0)
        audio_fmt_label = QLabel("Format:")
        audio_fmt_label.setFixedWidth(55)
        self.audio_fmt_combo = QComboBox()
        self.audio_fmt_combo.addItems(["mp3", "m4a", "flac", "wav", "ogg", "aac"])
        audio_fmt_row.addWidget(audio_fmt_label)
        audio_fmt_row.addWidget(self.audio_fmt_combo)
        self.audio_fmt_widget.setVisible(False)
        layout.addWidget(self.audio_fmt_widget)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #64748b; font-size: 12px;")
        self.info_label.setVisible(False)
        layout.addWidget(self.info_label)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(90)
        self.log_box.setVisible(False)
        layout.addWidget(self.log_box)

        btn_row = QHBoxLayout()
        self.cancel_dl_btn = QPushButton("Cancel Download")
        self.cancel_dl_btn.setStyleSheet(
            "QPushButton { background-color: #dc2626; color: white; }"
            "QPushButton:hover { background-color: #b91c1c; }"
        )
        self.cancel_dl_btn.setVisible(False)
        self.cancel_dl_btn.clicked.connect(self.cancel_download)

        self.download_btn = QPushButton("Download")
        self.download_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: white; }"
            "QPushButton:hover { background-color: #15803d; }"
            "QPushButton:disabled { background-color: #94a3b8; }"
        )
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self.start_download)

        self.close_btn = QPushButton("Close")
        self.close_btn.setStyleSheet(
            "QPushButton { background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }"
            "QPushButton:hover { background-color: #e2e8f0; }"
        )
        self.close_btn.clicked.connect(self.close)

        btn_row.addWidget(self.cancel_dl_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.close_btn)
        btn_row.addWidget(self.download_btn)
        layout.addLayout(btn_row)

    def _on_type_changed(self):
        self.audio_fmt_widget.setVisible(self.radio_audio.isChecked())

    def fetch_formats(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching...")
        self.title_label.setText("Fetching video info...")
        self.download_btn.setEnabled(False)
        self.fetch_thread = FetchFormatsThread(url)
        self.fetch_thread.formats_ready.connect(self.on_formats_ready)
        self.fetch_thread.error.connect(self.on_fetch_error)
        self.fetch_thread.start()

    def on_formats_ready(self, title):
        self.video_title = title
        self.title_label.setText(f"Ready: {title}")
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Fetch")
        self.download_btn.setEnabled(True)

    def on_fetch_error(self, error):
        self.title_label.setText(f"Error: {error}")
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Fetch")

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self._current_url = url
        self.download_btn.setEnabled(False)
        self.fetch_btn.setEnabled(False)
        self.cancel_dl_btn.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.info_label.setVisible(True)
        self.log_box.setVisible(True)
        self.log_box.clear()
        self._last_size = ""
        self._last_speed = ""
        self._last_eta = ""

        safe_title = re.sub(r'[^\w\s\-.]', '', self.video_title)[:80].strip() or "video"
        quality = self.quality_combo.currentText()

        if self.radio_audio.isChecked():
            audio_fmt = self.audio_fmt_combo.currentText()
            folder = os.path.join(HOME, "Downloads", "Music")
            os.makedirs(folder, exist_ok=True)
            display_name = f"{safe_title}.{audio_fmt}"
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(folder, f"{safe_title}.%(ext)s"),
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': audio_fmt, 'preferredquality': '0'}],
                'quiet': True, 'no_warnings': True,
                'http_headers': {'User-Agent': HEADERS['User-Agent']},
            }
        elif self.radio_video_only.isChecked():
            folder = os.path.join(HOME, "Downloads", "Videos")
            os.makedirs(folder, exist_ok=True)
            display_name = f"{safe_title}.mp4"
            fmt = "bestvideo/best" if quality == "Best" else f"bestvideo[height<={quality[:-1]}]/bestvideo/best"
            ydl_opts = {
                'format': fmt,
                'outtmpl': os.path.join(folder, f"{safe_title}.%(ext)s"),
                'quiet': True, 'no_warnings': True,
                'http_headers': {'User-Agent': HEADERS['User-Agent']},
            }
        else:
            folder = os.path.join(HOME, "Downloads", "Videos")
            os.makedirs(folder, exist_ok=True)
            display_name = f"{safe_title}.mp4"
            fmt = "bestvideo+bestaudio/best" if quality == "Best" else f"bestvideo[height<={quality[:-1]}]+bestaudio/bestvideo[height<={quality[:-1]}]/best"
            ydl_opts = {
                'format': fmt,
                'outtmpl': os.path.join(folder, f"{safe_title}.%(ext)s"),
                'merge_output_format': 'mp4',
                'quiet': True, 'no_warnings': True,
                'http_headers': {'User-Agent': HEADERS['User-Agent']},
            }

        self.download_started.emit(url, display_name, folder)
        self.dl_thread = YouTubeDownloadThread(url, ydl_opts)
        self.dl_thread.progress.connect(self._on_progress)
        self.dl_thread.speed.connect(self._on_speed)
        self.dl_thread.size_info.connect(self._on_size)
        self.dl_thread.eta.connect(self._on_eta)
        self.dl_thread.log.connect(lambda msg: self.log_box.append(msg))
        self.dl_thread.finished.connect(self.on_download_finished)
        self.dl_thread.start()
        self.log_box.append("Starting download...")

    def _on_progress(self, pct):
        self.progress_bar.setValue(pct)
        self.download_progress.emit(self._current_url, pct, self._last_size, self._last_speed, self._last_eta)

    def _on_speed(self, spd):
        self._last_speed = spd
        self._refresh_info()
        self.download_progress.emit(self._current_url, self.progress_bar.value(), self._last_size, spd, self._last_eta)

    def _on_size(self, sz):
        self._last_size = sz
        self._refresh_info()

    def _on_eta(self, eta):
        self._last_eta = eta
        self._refresh_info()

    def _refresh_info(self):
        parts = []
        if self._last_size: parts.append(self._last_size)
        if self._last_speed: parts.append(self._last_speed)
        if self._last_eta and self._last_eta != "—": parts.append(f"ETA {self._last_eta}")
        self.info_label.setText("  ".join(parts))

    def cancel_download(self):
        if self.dl_thread and self.dl_thread.isRunning():
            self.dl_thread.running = False
            self.dl_thread.terminate()
            self.log_box.append("Download cancelled.")
            self.cancel_dl_btn.setVisible(False)
            self.download_btn.setEnabled(True)
            self.fetch_btn.setEnabled(True)
            self.download_finished.emit(self._current_url, "Cancelled")

    def on_download_finished(self, msg):
        self.fetch_btn.setEnabled(True)
        self.download_btn.setEnabled(True)
        self.cancel_dl_btn.setVisible(False)
        if msg == "Finished":
            self.progress_bar.setValue(100)
            self.log_box.append("Download complete!")
            self.info_label.setText("Download complete!")
        else:
            self.log_box.append(msg)
            self.info_label.setText(msg)
        self.download_finished.emit(self._current_url, msg)


# ── Main download thread ─────────────────────────────────────────────────────

# ── Stream dialog ─────────────────────────────────────────────────────────────
class StreamDialog(QDialog):
    download_started  = pyqtSignal(str, str, str)
    download_progress = pyqtSignal(str, int, str, str, str)
    download_finished = pyqtSignal(str, str)

    def __init__(self, parent=None, url="", filename="", page_referer=""):
        super().__init__(parent)
        self.setWindowTitle("Stream Downloader")
        self.setMinimumWidth(520)
        self.setMinimumHeight(460)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(DIALOG_STYLE)
        self._url          = url
        self._filename     = filename
        self._page_referer = page_referer
        self._last_size    = ""
        self._last_speed   = ""
        self._last_eta     = ""
        self.dl_thread     = None
        self._retried      = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("Stream Downloader")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0369a1;")
        layout.addWidget(title)
        url_short = (self._url[:80] + "...") if len(self._url) > 80 else self._url
        self.url_label = QLabel(url_short)
        self.url_label.setStyleSheet("color: #64748b; font-size: 11px;")
        self.url_label.setWordWrap(True)
        layout.addWidget(self.url_label)
        self.file_label = QLabel(f"Saving as: {self._filename}")
        self.file_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #1e293b;")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.info_label)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(160)
        layout.addWidget(self.log_box)
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Download")
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: white; }"
            "QPushButton:hover { background-color: #15803d; }"
            "QPushButton:disabled { background-color: #94a3b8; }"
        )
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(
            "QPushButton { background-color: #dc2626; color: white; }"
            "QPushButton:hover { background-color: #b91c1c; }"
        )
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.close_btn = QPushButton("Close")
        self.close_btn.setStyleSheet(
            "QPushButton { background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }"
            "QPushButton:hover { background-color: #e2e8f0; }"
        )
        self.close_btn.clicked.connect(self.close)
        # Hidden paste row — shown when Facebook URL needs manual paste
        self.paste_row = QWidget()
        paste_layout = QVBoxLayout(self.paste_row)
        paste_layout.setContentsMargins(0, 0, 0, 0)
        paste_layout.setSpacing(6)
        self.paste_hint = QLabel()
        self.paste_hint.setWordWrap(True)
        self.paste_hint.setStyleSheet("color: #f97316; font-size: 12px;")
        paste_layout.addWidget(self.paste_hint)
        self.paste_input = QLineEdit()
        self.paste_input.setPlaceholderText("Paste the copied link here...")
        self.paste_input.setStyleSheet(
            "QLineEdit { background-color: #f8fafc; color: #1e293b;"
            "  border: 1px solid #f97316; border-radius: 5px;"
            "  padding: 6px 10px; font-size: 12px; }"
            "QLineEdit:focus { border: 1px solid #ea580c; }"
        )
        paste_layout.addWidget(self.paste_input)
        self.paste_row.setVisible(False)
        layout.addWidget(self.paste_row)

        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def _on_start_clicked(self):
        # If paste row is visible, use the pasted URL
        if self.paste_row.isVisible():
            pasted = self.paste_input.text().strip()
            if pasted:
                self._url = pasted
                self._page_referer = pasted
                self.paste_row.setVisible(False)
                url_short = (pasted[:80] + '...') if len(pasted) > 80 else pasted
                self.url_label.setText(url_short)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.close_btn.setEnabled(True)
        self._start_download()

    def _resolve_display_name(self, url, filename):
        """
        Generate a meaningful filename for social/stream downloads.
        Handles both CDN URLs (fbcdn.net, twimg.com) and page URLs.
        Priority: social ID from URL/referer -> efg decode -> timestamp.
        """
        import base64, json as _json
        try:
            from urllib.parse import urlparse, parse_qs
            p    = urlparse(url)
            host = p.netloc.lower()
            ref  = self._page_referer or ''
            ts   = time.strftime('%Y-%m-%d_%H-%M-%S')

            # Twitter/X
            is_twitter = any(d in host for d in ('twimg.com', 'twitter.com', 'x.com'))
            is_twitter_ref = any(d in ref for d in ('twitter.com', 'x.com'))
            if is_twitter or is_twitter_ref:
                for src in (url, ref):
                    m = re.search(r'/status/(\d+)', src)
                    if m: return f'twitter_{m.group(1)}.mp4'
                return f'twitter_{ts}.mp4'

            # Instagram
            is_insta_host = 'instagram.com' in host or 'cdninstagram.com' in host
            is_insta_cdn  = 'fbcdn.net' in host and 'instagram' in ref
            if is_insta_host or is_insta_cdn:
                for src in (url, ref):
                    m = re.search(r'/(?:reels?|p|tv)/([A-Za-z0-9_\-]+)', src)
                    if m and len(m.group(1)) > 4:
                        return f'instagram_{m.group(1)}.mp4'
                if 'fbcdn.net' in host:
                    qs  = parse_qs(p.query)
                    efg = qs.get('efg', [None])[0]
                    if efg:
                        try:
                            meta = _json.loads(base64.b64decode(efg + '==').decode())
                            vid  = meta.get('video_id')
                            if vid: return f'instagram_{vid}.mp4'
                        except Exception:
                            pass
                return f'instagram_{ts}.mp4'

            # Facebook
            is_fb_host = any(d in host for d in ('facebook.com', 'fb.watch', 'fbcdn.net'))
            is_fb_ref  = any(d in ref for d in ('facebook.com', 'fb.watch'))
            if is_fb_host or is_fb_ref:
                for src in (url, ref):
                    m = re.search(r'/(?:reel|videos)/([\d]+)', src)
                    if not m: m = re.search(r'[?&]v=([\d]+)', src)
                    if not m: m = re.search(r'/share/[vr]/([A-Za-z0-9_\-]+)', src)
                    if m: return f'facebook_{m.group(1)}.mp4'
                if 'fbcdn.net' in host:
                    qs  = parse_qs(p.query)
                    efg = qs.get('efg', [None])[0]
                    if efg:
                        try:
                            meta = _json.loads(base64.b64decode(efg + '==').decode())
                            vid  = meta.get('video_id')
                            if vid: return f'facebook_{vid}.mp4'
                        except Exception:
                            pass
                return f'facebook_{ts}.mp4'

            # Generic
            safe = re.sub(r'[^\w\s\.\-]', '', filename)[:80].strip()
            blocked = {'stream', 'download', 'video', 'instagram',
                       'facebook', 'twitter', 'index', 'media'}
            if safe and safe.lower().split('.')[0] not in blocked:
                base, ext = os.path.splitext(safe)
                return f'{base}{ext or ".mp4"}'
            return f'video_{ts}.mp4'
        except Exception:
            ts = time.strftime('%Y-%m-%d_%H-%M-%S')
            return f'video_{ts}.mp4'

    def _start_download(self):
        folder = os.path.join(HOME, "Downloads", "Videos")
        os.makedirs(folder, exist_ok=True)
        display_name = self._resolve_display_name(self._url, self._filename)
        base, ext = os.path.splitext(display_name)
        if not ext:
            ext = ".mp4"
            display_name = f"{base}{ext}"
        # Update the dialog label to show the resolved filename
        self.file_label.setText(f"Saving as: {display_name}")
        ydl_opts = {
            'format':              'bestvideo+bestaudio/best',
            'outtmpl':             os.path.join(folder, f"{base}.%(ext)s"),
            'merge_output_format': 'mp4',
            'quiet':               True,
            'no_warnings':         True,
            'cookiesfrombrowser':  ('firefox',),
            'http_headers':        {'User-Agent': HEADERS['User-Agent']},
        }
        self.download_started.emit(self._url, display_name, folder)
        self.dl_thread = YouTubeDownloadThread(self._url, ydl_opts)
        self.dl_thread.progress.connect(self._on_progress)
        self.dl_thread.speed.connect(self._on_speed)
        self.dl_thread.size_info.connect(self._on_size)
        self.dl_thread.eta.connect(self._on_eta)
        self.dl_thread.log.connect(lambda msg: self.log_box.append(msg))
        self.dl_thread.finished.connect(self._on_finished)
        self.dl_thread.start()
        self.log_box.append("Starting stream download...")

    def _on_progress(self, pct):
        self.progress_bar.setValue(pct)
        self.download_progress.emit(self._url, pct, self._last_size, self._last_speed, self._last_eta)

    def _on_speed(self, spd):  self._last_speed = spd;  self._refresh_info()
    def _on_size(self, sz):    self._last_size  = sz;   self._refresh_info()
    def _on_eta(self, eta):    self._last_eta   = eta;  self._refresh_info()

    def _refresh_info(self):
        parts = []
        if self._last_size:  parts.append(self._last_size)
        if self._last_speed: parts.append(self._last_speed)
        if self._last_eta and self._last_eta != "—": parts.append(f"ETA {self._last_eta}")
        self.info_label.setText("  ".join(parts))

    def closeEvent(self, event):
        """Handle window X button — cancel thread and save to history."""
        if self.dl_thread and self.dl_thread.isRunning():
            self.dl_thread.running = False
            self.dl_thread.terminate()
            self.download_finished.emit(self._url, "Cancelled")
        event.accept()

    def _cancel(self):
        if self.dl_thread and self.dl_thread.isRunning():
            self.dl_thread.running = False
            self.dl_thread.terminate()
            self.log_box.append("Download cancelled.")
            self.cancel_btn.setEnabled(False)
            self.close_btn.setEnabled(True)
            self.download_finished.emit(self._url, "Cancelled")

    def _friendly_error(self, msg):
        """Translate raw yt-dlp error strings into clean user-facing messages."""
        m = msg.lower()
        # Facebook feed URL (bare facebook.com) -- needs manual paste
        if "unsupported url" in m and self._url and (
            'facebook.com' in self._url or 'fb.watch' in self._url
        ):
            return (
                "Facebook feed video — cannot download automatically.\n\n"
                "On the video, click \u22ef (3 dots) \u2192 Copy link,\n"
                "then paste the link in the box below and click Start Download."
            ), "Paste the video link below to download"
        # Play-first errors — yt-dlp couldn't extract because stream not loaded yet
        if "unsupported url" in m or "no video formats" in m or "no suitable" in m:
            return (
                "Could not download automatically.\n\n"
                "Press Play on the video first, then click Capture again —\n"
                "this lets LDM grab the stream directly from the player."
            ), "Press Play first, then Capture again"
        # Auth / access errors
        if "403" in msg or "forbidden" in m:
            return (
                "Access denied (403).\n\n"
                "Press Play on the video first, then click Capture again —\n"
                "a fresh stream URL will be used instead."
            ), "Access denied — press Play first, then Capture"
        if "401" in msg or "unauthorized" in m:
            return "Not authorised to download this video.", "Not authorised (401)"
        if "404" in msg or "not found" in m:
            return "Video not found or the link has expired.", "Video not found (404)"
        if "429" in msg or "too many" in m:
            return "Too many requests — wait a moment and try again.", "Rate limited (429)"
        # Network errors
        if "ssl" in m:
            return "SSL error — could not establish a secure connection.", "SSL error"
        if "connection" in m or "network" in m:
            return "Connection error — check your internet and try again.", "Connection error"
        if "timeout" in m:
            return "Connection timed out — try again.", "Timeout"
        # Generic fallback — show a shortened version, never the full raw dump
        short = msg.replace("ERROR:", "").strip()
        short = short.split("\n")[0][:120]
        return short, short

    def _on_finished(self, msg):
        self.cancel_btn.setEnabled(False)
        self.close_btn.setEnabled(True)
        if msg == "Finished":
            self.progress_bar.setValue(100)
            self.log_box.append("Download complete!")
            self.info_label.setText("Download complete!")
            self.info_label.setStyleSheet("color: #16a34a; font-size: 12px;")
            self.download_finished.emit(self._url, msg)
            return
        # Auto-retry with page URL on 403 — needed when direct m3u8 requires
        # page-level cookie context (intercepted stream URL has expired).
        _is_403    = "403" in msg or "Forbidden" in msg.lower()
        _can_retry = (
            not self._retried and _is_403
            and self._page_referer and self._page_referer != self._url
        )
        if _can_retry:
            self._retried = True
            self.log_box.append("Stream URL expired (403) — retrying with page URL...")
            self.info_label.setText("Retrying with page URL...")
            self.info_label.setStyleSheet("color: #f97316; font-size: 12px;")
            self.start_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.close_btn.setEnabled(False)
            self._url = self._page_referer
            self.progress_bar.setValue(0)
            self._start_download()
            return
        # Show clean error message
        log_msg, label_msg = self._friendly_error(msg)
        self.log_box.append(log_msg)
        self.info_label.setText(label_msg)
        self.info_label.setStyleSheet("color: #dc2626; font-size: 12px;")
        # Facebook paste hint -- show input row so user can paste link
        if 'Paste the video link' in label_msg:
            self.paste_hint.setText(
                "\u22ef (3 dots) on video \u2192 Copy link \u2192 paste below:"
            )
            self.paste_row.setVisible(True)
            self.start_btn.setEnabled(True)
            self.close_btn.setEnabled(True)
        else:
            self.download_finished.emit(self._url, msg)

class DownloadThread(QThread):
    progress   = pyqtSignal(int)
    speed      = pyqtSignal(str)
    downloaded = pyqtSignal(str)
    eta        = pyqtSignal(str)
    finished   = pyqtSignal(str)

    def __init__(self, url, filename, is_video=False, referer="", resume_from=0):
        super().__init__()
        self.url = url
        self.filename = filename
        self.is_video = is_video
        self.referer = referer
        self.resume_from = resume_from
        self.running = True
        self._proc = None

    def run(self):
        if self.is_video:
            self.download_video()
        else:
            self.download_file()

    def download_video(self):
        try:
            folder = choose_folder(self.filename)
            base = os.path.splitext(self.filename)[0]
            out_template = os.path.join(folder, f"{base}.%(ext)s")
            ydl_opts = {
                'outtmpl': out_template,
                'restrictfilenames': False,
                'progress_hooks': [self.yt_dlp_hook],
                'no_warnings': False,
                'ignoreerrors': False,
                'http_headers': {'User-Agent': HEADERS['User-Agent']},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if info is None:
                    raise Exception("Could not extract video info")
            self.finished.emit("Finished")
        except Exception as e:
            self.finished.emit(f"Error: {str(e)[:60]}")

    def yt_dlp_hook(self, d):
        if not self.running:
            raise Exception("Cancelled")
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%', '').strip()
            try:
                self.progress.emit(int(float(p)))
            except Exception:
                pass
            self.speed.emit(d.get('_speed_str', 'N/A'))
            dl_bytes = d.get('downloaded_bytes') or 0
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            if total_bytes:
                self.downloaded.emit(f"{format_size(dl_bytes)} / {format_size(total_bytes)}")
                self.eta.emit(format_eta(d.get('eta') or 0))
            else:
                self.downloaded.emit(format_size(dl_bytes))
                self.eta.emit("—")
        elif d['status'] == 'finished':
            self.progress.emit(100)
            self.downloaded.emit(format_size(d.get('total_bytes') or 0))
            self.eta.emit("—")

    def download_file(self):
        if needs_curl(self.url):
            self.download_with_curl()
        else:
            self.download_with_requests()

    def download_with_curl(self):
        try:
            folder = choose_folder(self.filename)
            filepath = os.path.join(folder, self.filename)
            if not shutil.which("curl"):
                self.download_with_requests()
                return
            cmd = [
                "curl", "-L", "-o", filepath,
                "--progress-bar", "--retry", "3",
                "--retry-delay", "2", "--connect-timeout", "15",
                "-A", HEADERS["User-Agent"],
            ]
            if self.referer:
                cmd += ["-e", self.referer]
            if self.resume_from > 0:
                cmd += ["-C", str(self.resume_from)]
            cmd.append(self.url)
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            for line in self._proc.stderr:
                if not self.running:
                    self._proc.kill()
                    self.finished.emit("Cancelled")
                    return
                pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
                if pct_match:
                    try:
                        self.progress.emit(int(float(pct_match.group(1))))
                        if os.path.exists(filepath):
                            self.downloaded.emit(format_size(os.path.getsize(filepath)))
                    except Exception:
                        pass
            self._proc.wait()
            if self._proc.returncode == 0 and os.path.exists(filepath):
                self.progress.emit(100)
                self.downloaded.emit(format_size(os.path.getsize(filepath)))
                self.eta.emit("—")
                self.finished.emit("Finished")
            else:
                self.finished.emit("curl Failed")
        except Exception as e:
            self.finished.emit(f"Error: {str(e)[:60]}")

    def download_with_requests(self):
        try:
            session = requests.Session()
            headers = HEADERS.copy()
            if self.referer:
                headers["Referer"] = self.referer
            if self.resume_from > 0:
                headers["Range"] = f"bytes={self.resume_from}-"
            session.headers.update(headers)
            try:
                import browser_cookie3
                cookies = browser_cookie3.firefox()
                session.cookies.update(cookies)
            except Exception:
                pass
            try:
                head = session.head(self.url, allow_redirects=True, timeout=10, verify=False)
                cd = head.headers.get("Content-Disposition", "")
                if "filename=" in cd:
                    m = re.search(r"filename\*=(?:UTF-8|utf-8)''([^;\n]+)", cd, re.I)
                    if m:
                        self.filename = unquote(m.group(1).strip())
                    else:
                        m = re.search(r'filename="([^"]+)"', cd, re.I)
                        if not m:
                            m = re.search(r"filename=([^;\s\"']+)", cd, re.I)
                        if m:
                            candidate = m.group(1).strip().strip("'\"")
                            if candidate.lower() not in ("utf-8", "utf8", "ascii", "iso-8859-1"):
                                self.filename = candidate
            except Exception:
                pass

            # replace generic / captured names with timestamp
            _generic = {
                "download", "video.mp4", "video.mkv", "video.webm",
                "captured_video.mp4", "captured_video.mkv",
                "captured_video.webm", "captured_video.avi",
                "captured_video.ts", "captured_video.m4v",
            }
            _base = os.path.basename(self.filename).lower().split('?')[0]
            if _base in _generic or _base.startswith('captured_video'):
                _ext = os.path.splitext(self.filename)[1] or '.mp4'
                _ts  = time.strftime('%Y-%m-%d_%H-%M-%S')
                self.filename = f'video_{_ts}{_ext}'

            folder = choose_folder(self.filename)
            filepath = os.path.join(folder, self.filename)
            mode = "ab" if self.resume_from > 0 else "wb"
            with session.get(self.url, stream=True, allow_redirects=True, timeout=30, verify=False) as r:
                if self.resume_from > 0 and r.status_code == 416:
                    # Range not satisfiable — file already complete
                    self.finished.emit("Finished")
                    return
                if r.status_code not in (200, 206):
                    r.raise_for_status()
                total_from_header = int(r.headers.get("content-length", 0) or 0)
                total = total_from_header + self.resume_from if total_from_header > 0 else 0
                downloaded_bytes = self.resume_from
                start_time = time.time()
                with open(filepath, mode) as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if not self.running:
                            self.finished.emit("Cancelled")
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            if total > 0:
                                pct = int(downloaded_bytes * 100 / total)
                                self.progress.emit(pct)
                                self.downloaded.emit(f"{format_size(downloaded_bytes)} / {format_size(total)}")
                                elapsed = time.time() - start_time
                                downloaded_since_start = downloaded_bytes - self.resume_from
                                if elapsed > 0 and downloaded_since_start > 0:
                                    rate = downloaded_since_start / elapsed
                                    remaining_bytes = total - downloaded_bytes
                                    self.eta.emit(format_eta(remaining_bytes / rate))
                            else:
                                self.downloaded.emit(format_size(downloaded_bytes))
                                self.eta.emit("—")
                            elapsed = time.time() - start_time
                            downloaded_since_start = downloaded_bytes - self.resume_from
                            if elapsed > 0:
                                spd = downloaded_since_start / elapsed
                                if spd >= 1024 * 1024:
                                    self.speed.emit(f"{spd / (1024 * 1024):.2f} MB/s")
                                else:
                                    self.speed.emit(f"{spd / 1024:.1f} KB/s")
            self.eta.emit("—")
            self.finished.emit("Finished")
        except requests.exceptions.SSLError:
            self.finished.emit("SSL Error")
        except requests.exceptions.ConnectionError:
            self.finished.emit("Connection Error")
        except requests.exceptions.Timeout:
            self.finished.emit("Timeout")
        except requests.exceptions.HTTPError as e:
            self.finished.emit(f"HTTP {e.response.status_code}")
        except Exception as e:
            self.finished.emit(f"Error: {str(e)[:50]}")

    def stop(self):
        self.running = False
        if self._proc:
            try:
                self._proc.kill()
            except Exception:
                pass



# ── Main window ──────────────────────────────────────────────────────────────
class DownloadManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Linux Download Manager")
        self.resize(1150, 640)
        self.recent_urls = {}
        self.finished_urls = {}
        self.all_rows = []
        self.row_progress = {}
        self.yt_url_to_row = {}
        self.history = load_history()
        self._settings = load_settings()
        self.dark_mode = self._settings.get("dark_mode", False)
        self.notify_enabled = self._settings.get("notifications", True)

        app_icon = QIcon.fromTheme("linux-downloader")
        if app_icon.isNull():
            script_dir = os.path.dirname(os.path.abspath(__file__))
            for candidate in [
                os.path.join(script_dir, "icons", "linux-downloader-256.png"),
                os.path.join(script_dir, "linux-downloader.svg"),
                os.path.join(script_dir, "icons", "linux-downloader-128.png"),
            ]:
                if os.path.exists(candidate):
                    app_icon = QIcon(candidate)
                    break
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
            QApplication.setWindowIcon(app_icon)
        self.app_icon = app_icon

        self._build_ui()
        self._load_history_into_table()
        self._apply_theme()
        self._update_category_counts()
        self.threads = []
        start_bridge_server()
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_queue)
        self.timer.start(500)
        self.taskbar_timer = QTimer()
        self.taskbar_timer.timeout.connect(self._update_taskbar_progress)
        self.taskbar_timer.start(1000)

    def _theme(self):
        return THEMES["dark"] if self.dark_mode else THEMES["light"]

    def _notify(self, title, message):
        if self.notify_enabled:
            try:
                subprocess.Popen(
                    ['notify-send', '-a', 'Linux Download Manager',
                     '-i', 'linux-downloader', title, message],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

    def _load_history_into_table(self):
        for entry in self.history:
            filename = entry.get("filename", "Unknown")
            path     = entry.get("path", "")
            status   = entry.get("status", "Finished")
            size     = entry.get("size", "—")
            category = entry.get("category", get_category(filename))
            url      = entry.get("url", "")

            if status == "Finished" and path and not os.path.exists(path):
                status = "File Missing"

            date     = entry.get("date", "")
            progress = entry.get("progress", None)
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._insert_row_items(row, filename, path, url, status, size, category, date, progress)
            if url:
                self.finished_urls[url] = path

    def _insert_row_items(self, row, filename, path, url, status, size, category, date="", progress=None):
        name_item = QTableWidgetItem(f"  {filename}")
        name_item.setData(Qt.ItemDataRole.UserRole, path)
        name_item.setData(Qt.ItemDataRole.UserRole + 2, url)
        name_item.setIcon(get_file_icon(filename))
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        prog_item = QTableWidgetItem()
        _progress = 100 if status == "Finished" else (progress if progress is not None else 0)
        prog_item.setData(Qt.ItemDataRole.UserRole + 1, _progress)
        prog_item.setData(Qt.ItemDataRole.UserRole + 3, self.dark_mode)
        prog_item.setFlags(prog_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        dl_item   = QTableWidgetItem(size)
        spd_item  = QTableWidgetItem("—")
        stat_item = QTableWidgetItem(status)
        stat_item.setToolTip(status)
        eta_item  = QTableWidgetItem("—")

        for item in [dl_item, spd_item, stat_item, eta_item]:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        if status == "Finished":
            stat_item.setForeground(QColor("#16a34a"))
        elif status == "File Missing":
            stat_item.setForeground(QColor("#f97316"))
        else:
            stat_item.setForeground(QColor("#dc2626"))

        self.table.setItem(row, 0, name_item)
        self.table.setItem(row, 1, prog_item)
        self.table.setItem(row, 2, dl_item)
        self.table.setItem(row, 3, spd_item)
        self.table.setItem(row, 4, eta_item)
        date_item = QTableWidgetItem(date)
        date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        date_item.setFlags(date_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 5, stat_item)
        self.table.setItem(row, 6, date_item)
        self.table.setRowHeight(row, 38)

        self.all_rows.append({"row": row, "category": category})
        self.row_progress[row] = _progress

    def _add_to_history(self, url, filename, path, status, size, category, progress=0):
        entry = {"url": url, "filename": filename, "path": path,
                 "status": status, "size": size, "category": category,
                 "date": time.strftime("%Y-%m-%d %H:%M"),
                 "progress": progress}
        self.history = [e for e in self.history if e.get("url") != url]
        self.history.append(entry)
        save_history(self.history)

    def _make_toolbar_svg_btn(self, svg_path_data, stroke_or_fill, tooltip, hover_rgba, filled=False):
        """Create toolbar button with SVG icon rendered via QSvgRenderer."""
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QByteArray
        btn = QPushButton()
        btn.setFixedSize(68, 64)
        btn.setToolTip(tooltip)
        if filled:
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="{stroke_or_fill}">{svg_path_data}</svg>'''
        else:
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="{stroke_or_fill}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{svg_path_data}</svg>'''
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        pixmap = QPixmap(40, 40)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(pixmap)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        vbox = QVBoxLayout(btn)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(icon_lbl)
        hover2 = hover_rgba.replace("0.1)", "0.2)")
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{ background-color: {hover_rgba}; }}
            QPushButton:pressed {{ background-color: {hover2}; }}
            QToolTip {{
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: bold;
            }}
        """)
        btn._icon_lbl = icon_lbl
        return btn

    def _open_selected_folder(self):
        row = self.table.currentRow()
        if row >= 0:
            item = self.table.item(row, 0)
            if item:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    open_and_select(path)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.table.hasFocus():
            self.clear_item()
        super().keyPressEvent(event)

    def _build_ui(self):
        t = self._theme()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._menubar = QMenuBar()
        self._update_menubar_style()

        file_menu = self._menubar.addMenu("File")
        yt_action = QAction("YouTube Downloader", self)
        yt_action.setShortcut("Ctrl+Y")
        yt_action.triggered.connect(lambda: self.open_youtube_dialog())
        file_menu.addAction(yt_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(QApplication.quit)
        file_menu.addAction(quit_action)

        view_menu = self._menubar.addMenu("View")
        self._dark_action = QAction("Dark Mode", self)
        self._dark_action.setCheckable(True)
        self._dark_action.setChecked(self.dark_mode)
        self._dark_action.triggered.connect(self._toggle_dark_mode)
        view_menu.addAction(self._dark_action)
        view_menu.addSeparator()
        self._notif_action = QAction("Download Notifications", self)
        self._notif_action.setCheckable(True)
        self._notif_action.setChecked(self.notify_enabled)
        self._notif_action.triggered.connect(self._toggle_notifications)
        view_menu.addAction(self._notif_action)
        view_menu.addSeparator()
        reset_cols_action = QAction("Reset Column Widths", self)
        reset_cols_action.triggered.connect(self._reset_column_widths)
        view_menu.addAction(reset_cols_action)

        help_menu = self._menubar.addMenu("Help")
        deps_action = QAction("Install Dependencies", self)
        deps_action.triggered.connect(self.install_dependencies)
        help_menu.addAction(deps_action)
        help_menu.addSeparator()
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        outer.addWidget(self._menubar)

        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._sidebar = QWidget()
        self._sidebar.setFixedWidth(190)
        self._sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self._sidebar_title = QWidget()
        title_layout = QHBoxLayout(self._sidebar_title)
        title_layout.setContentsMargins(10, 8, 10, 8)
        title_layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setFixedSize(28, 28)
        icon_label.setScaledContents(True)
        pix = self.app_icon.pixmap(28, 28) if not self.app_icon.isNull() else None
        if pix is None or pix.isNull():
            script_dir = os.path.dirname(os.path.abspath(__file__))
            png_path = os.path.join(script_dir, "icons", "linux-downloader-48.png")
            if os.path.exists(png_path):
                pix = QPixmap(png_path).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if pix and not pix.isNull():
            icon_label.setPixmap(pix)
        title_layout.addWidget(icon_label)

        self._title_label = QLabel("LDM")
        self._title_label.setStyleSheet("font-size: 16px; font-weight: bold; letter-spacing: 2px;")
        title_layout.addWidget(self._title_label)
        title_layout.addStretch()
        sidebar_layout.addWidget(self._sidebar_title)

        self._category_list = QListWidget()
        self._category_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label, emoji, color in CATEGORIES:
            item = QListWidgetItem(f"  {emoji}  {label}")
            item.setData(Qt.ItemDataRole.UserRole, label)
            self._category_list.addItem(item)
        self._category_list.setCurrentRow(0)
        self._category_list.currentRowChanged.connect(self.filter_by_category)
        sidebar_layout.addWidget(self._category_list)
        sidebar_layout.addStretch()
        root.addWidget(self._sidebar)

        self._content_widget = QWidget()
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(14, 12, 14, 8)
        content_layout.setSpacing(8)

        # Search + URL row
        top_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍  Search downloads...")
        self._search_input.setFixedWidth(220)
        self._search_input.textChanged.connect(self.filter_by_search)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste URL here — YouTube links open the YouTube Downloader automatically...")
        self.url_input.returnPressed.connect(self.start_manual)
        top_row.addWidget(self._search_input)
        top_row.addSpacing(8)
        top_row.addWidget(self.url_input)
        content_layout.addLayout(top_row)

        # ── Toolbar ──────────────────────────────────────────────────────────
        self._toolbar = QWidget()
        self._toolbar.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(self._toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(4)

        self.start_btn = self._make_toolbar_svg_btn(
            '<path d="M12 4v13"/><polyline points="7,14 12,19 17,14"/><line x1="5" y1="21" x2="19" y2="21"/>',
            "#059669", "Start Download", "rgba(5,150,105,0.1)")
        self.resume_btn = self._make_toolbar_svg_btn(
            '<path d="M5 4l14 8-14 8V4z"/>',
            "#059669", "Resume Download", "rgba(5,150,105,0.1)", filled=True)
        self.cancel_btn = self._make_toolbar_svg_btn(
            '<rect x="3" y="3" width="18" height="18" rx="3"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/>',
            "#e11272", "Cancel Download", "rgba(225,18,114,0.1)")
        self.clear_item_btn = self._make_toolbar_svg_btn(
            '<path d="M3 6h18M9 6V4h6v2M20 6l-.9 13.1A2 2 0 0117.1 21H6.9a2 2 0 01-2-1.9L4 6"/>',
            "#f97316", "Remove Item", "rgba(251,146,60,0.1)")
        self.clear_btn = self._make_toolbar_svg_btn(
            '<path d="M3 6h18M9 6V4h6v2M20 6l-.9 13.1A2 2 0 0117.1 21H6.9a2 2 0 01-2-1.9L4 6"/><line x1="3" y1="21" x2="21" y2="3"/>',
            "#ea580c", "Clear All", "rgba(234,88,12,0.1)")
        self.open_folder_btn = self._make_toolbar_svg_btn(
            '<path d="M3 7c0-1.1.9-2 2-2h4l2 3h8a2 2 0 012 2v7a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/>',
            "#ca8a04", "Open Folder", "rgba(202,138,4,0.1)", filled=True)
        self.yt_btn = self._make_toolbar_svg_btn(
            '<path d="M19.6 3H4.4C3.1 3 2 4.1 2 5.4v13.2C2 19.9 3.1 21 4.4 21h15.2c1.3 0 2.4-1.1 2.4-2.4V5.4C22 4.1 20.9 3 19.6 3zm-9.6 13V8l7 4-7 4z"/>',
            "#dc2626", "YouTube Downloader", "rgba(220,38,38,0.1)", filled=True)
        self.about_btn = self._make_toolbar_svg_btn(
            '<circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="8" stroke-width="3"/><line x1="12" y1="12" x2="12" y2="16"/>',
            "#64748b", "About", "rgba(100,116,139,0.1)")
        self.donate_btn = self._make_toolbar_svg_btn(
            '<path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/>',
            "#d97706", "Support Development", "rgba(217,119,6,0.1)", filled=True)

        for w in [self.start_btn, self.resume_btn, self.cancel_btn,
                  self.clear_item_btn, self.clear_btn,
                  self.open_folder_btn, self.yt_btn,
                  self.about_btn, self.donate_btn]:
            toolbar_layout.addWidget(w)
        toolbar_layout.addStretch()

        self.start_btn.clicked.connect(self.start_manual)
        self.resume_btn.setEnabled(False)
        self._set_btn_opacity(self.resume_btn, 0.3)
        self.resume_btn.clicked.connect(self._resume_selected)
        self.cancel_btn.clicked.connect(self.cancel_last)
        self.clear_item_btn.clicked.connect(self.clear_item)
        self.clear_btn.clicked.connect(self.clear_list)
        self.open_folder_btn.clicked.connect(self._open_selected_folder)
        self.yt_btn.clicked.connect(lambda: self.open_youtube_dialog())
        self.about_btn.clicked.connect(self.show_about)
        self.donate_btn.clicked.connect(self._open_donate)

        content_layout.addWidget(self._toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["File Name", "Progress", "Downloaded", "Speed", "ETA", "Status", "Date"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for col in range(self.table.columnCount()):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 270)
        self.table.setColumnWidth(1, 162)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 85)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 90)
        self.table.setColumnWidth(6, 145)
        self.table.horizontalHeader().setStretchLastSection(False)
        # ── Restore saved column widths ──────────────────────────────
        saved_widths = self._settings.get("column_widths", {})
        for col_str, width in saved_widths.items():
            self.table.setColumnWidth(int(col_str), width)
        self.table.horizontalHeader().setMinimumSectionSize(50)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(18, 18))
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().sectionClicked.connect(self._sort_by_column)
        self.table.horizontalHeader().sectionResized.connect(self._on_column_resized)
        self.progress_delegate = ProgressDelegate(self.table)
        self.table.setItemDelegateForColumn(1, self.progress_delegate)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        content_layout.addWidget(self.table)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        # Status bar
        self._status_bar = QLabel("Ready")
        self._status_bar.setFixedHeight(24)
        self._status_bar.setContentsMargins(4, 0, 4, 0)
        content_layout.addWidget(self._status_bar)

        root.addWidget(self._content_widget)
        outer.addWidget(body)

    def _update_menubar_style(self):
        t = self._theme()
        self._menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {t['menu_bg']}; color: {t['text']};
                border-bottom: 1px solid {t['border']};
                font-size: 13px; padding: 2px 4px;
            }}
            QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; }}
            QMenuBar::item:selected {{ background-color: {t['menu_hover']}; color: {t['menu_hover_text']}; }}
            QMenu {{
                background-color: {t['bg']}; color: {t['text']};
                border: 1px solid {t['border']}; border-radius: 6px;
                padding: 4px; font-size: 13px;
            }}
            QMenu::item {{ padding: 7px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {t['menu_hover']}; color: {t['menu_hover_text']}; }}
            QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}
            QMenu::indicator {{ width: 14px; height: 14px; }}
        """)

    def _apply_theme(self):
        t = self._theme()


        # Main window
        self.setStyleSheet(f"QWidget {{ background-color: {t['bg']}; color: {t['text']}; }}")

        # Menubar
        self._update_menubar_style()

        # Sidebar
        self._sidebar.setStyleSheet(f"QWidget#sidebar {{ background-color: {t['sidebar']}; border-right: 1px solid {t['border']}; }}")
        self._sidebar_title.setStyleSheet(f"background-color: {t['bg']}; border-bottom: 1px solid {t['border']};")
        self._title_label.setStyleSheet(f"color: #2563eb; font-size: 16px; font-weight: bold; letter-spacing: 2px;")

        self._category_list.setStyleSheet(f"""
            QListWidget {{ background: transparent; border: none; outline: none; padding: 6px 0px; }}
            QListWidget::item {{ color: {t['muted']}; padding: 8px 10px 8px 14px; border-radius: 6px; margin: 1px 8px; font-size: 13px; }}
            QListWidget::item:hover {{ background-color: {t['category_hover']}; color: {t['category_hover_text']}; }}
            QListWidget::item:selected {{ background-color: {t['category_sel']}; color: {t['category_sel_text']}; font-weight: bold; }}
        """)

        # Content area
        self._content_widget.setStyleSheet(f"background-color: {t['bg']};")

        # URL and search inputs
        input_style = f"""
            QLineEdit {{
                background-color: {t['input_bg']}; color: {t['text']};
                border: 1px solid {t['border']}; border-radius: 6px;
                padding: 7px 12px; font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid #2563eb; background-color: {t['input_focus']}; }}
        """
        self.url_input.setStyleSheet(input_style)
        self._search_input.setStyleSheet(input_style)

        # Table
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {t['bg']}; alternate-background-color: {t['alt_row']};
                color: {t['text']}; border: 1px solid {t['border']}; border-radius: 6px;
                font-size: 13px; gridline-color: {t['grid']}; outline: none;
            }}
            QTableWidget::item {{ padding: 6px 10px; border: none; }}
            QTableWidget::item:selected {{ background-color: {t['selected']}; color: {t['selected_text']}; }}
            QHeaderView::section {{
                background-color: {t['header']}; color: {t['faint']};
                padding: 7px 10px; border: none;
                border-bottom: 1px solid {t['border']};
                font-size: 11px; font-weight: bold; letter-spacing: 1px;
                cursor: pointer;
            }}
            QHeaderView::section:hover {{ background-color: {t['menu_hover']}; color: {t['menu_hover_text']}; }}
            QScrollBar:vertical {{ background: {t['scrollbar']}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {t['scrollbar_handle']}; border-radius: 4px; min-height: 20px; margin: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; border: none; background: none; }}
            QScrollBar:horizontal {{ background: {t['scrollbar']}; height: 8px; border-radius: 4px; }}
            QScrollBar::handle:horizontal {{ background: {t['scrollbar_handle']}; border-radius: 4px; min-width: 20px; margin: 2px; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; border: none; background: none; }}
        """)
        # Status bar
        self._status_bar.setStyleSheet(f"""
            QLabel {{
                background-color: {t['status_bar']}; color: {t['muted']};
                border-top: 1px solid {t['border']}; font-size: 11px;
                padding: 2px 8px;
            }}
        """)

        # Toolbar separator color
        sep_color = "#334155" if self.dark_mode else "#e2e8f0"
        # no separators

        # Update dark mode flag in progress items
        for row_info in self.all_rows:
            row = row_info["row"]
            prog_item = self.table.item(row, 1)
            if prog_item:
                prog_item.setData(Qt.ItemDataRole.UserRole + 3, self.dark_mode)
        self.table.viewport().update()

    def _toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self._dark_action.setChecked(self.dark_mode)
        self._settings["dark_mode"] = self.dark_mode
        save_settings(self._settings)
        self._apply_theme()

    def _toggle_notifications(self):
        self.notify_enabled = not self.notify_enabled
        self._notif_action.setChecked(self.notify_enabled)
        self._settings["notifications"] = self.notify_enabled
        save_settings(self._settings)

    def _reset_column_widths(self):
        defaults = {0: 270, 1: 199, 2: 100, 3: 85, 4: 70, 5: 90, 6: 110}
        for col, width in defaults.items():
            self.table.setColumnWidth(col, width)


    def _update_category_counts(self):
        counts = {cat[0]: 0 for cat in CATEGORIES}
        for row_info in self.all_rows:
            cat = row_info.get("category", "Others")
            if cat in counts:
                counts[cat] += 1
            counts["All Downloads"] += 1

        for i, (label, emoji, color) in enumerate(CATEGORIES):
            count = counts.get(label, 0)
            item = self._category_list.item(i)
            if item:
                if count > 0:
                    item.setText(f"  {emoji}  {label} ({count})")
                else:
                    item.setText(f"  {emoji}  {label}")

    def _on_column_resized(self, col, old_width, new_width):
        widths = self._settings.setdefault("column_widths", {})
        widths[str(col)] = new_width
        save_settings(self._settings)

    def _sort_by_column(self, col):
        if col == 1:
            return  # Don't sort progress bar column
        self.table.sortItems(col, Qt.SortOrder.AscendingOrder)

    def filter_by_search(self, text):
        text = text.lower().strip()
        current_cat = CATEGORIES[self._category_list.currentRow()][0]
        for row_info in self.all_rows:
            row = row_info["row"]
            cat = row_info["category"]
            name_item = self.table.item(row, 0)
            filename = name_item.text().lower() if name_item else ""
            cat_match = (current_cat == "All Downloads" or cat == current_cat)
            search_match = (not text or text in filename)
            self.table.setRowHidden(row, not (cat_match and search_match))

    def filter_by_category(self, index):
        selected = CATEGORIES[index][0]
        search_text = self._search_input.text().lower().strip()
        for row_info in self.all_rows:
            row = row_info["row"]
            cat = row_info["category"]
            name_item = self.table.item(row, 0)
            filename = name_item.text().lower() if name_item else ""
            cat_match = (selected == "All Downloads" or cat == selected)
            search_match = (not search_text or search_text in filename)
            self.table.setRowHidden(row, not (cat_match and search_match))

    def install_dependencies(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Install Dependencies")
        dialog.setMinimumWidth(520)
        dialog.setStyleSheet("""
            QDialog { background-color: #ffffff; color: #1e293b; }
            QLabel { color: #1e293b; font-size: 13px; }
            QPushButton { border-radius: 6px; font-size: 12px; font-weight: 600; padding: 6px 14px; border: none; }
            QLineEdit { border-radius: 6px; padding: 7px 10px; font-family: monospace; font-size: 12px; border: 1px solid #334155; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Install Dependencies")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2563eb;")
        layout.addWidget(title)

        intro = QLabel("Open a terminal and run these 3 commands one by one:")
        intro.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(intro)

        commands = [
            ("1. System packages  (ffmpeg, curl)",
             "sudo apt install -y ffmpeg curl"),
            ("2. Python packages  (PyQt6, requests, yt-dlp, browser-cookie3)",
             "pip install PyQt6 requests yt-dlp browser-cookie3 --break-system-packages"),
            ("3. Deno  —  JavaScript runtime required for YouTube",
             "curl -fsSL https://deno.land/install.sh | sh && sudo ln -sf ~/.deno/bin/deno /usr/local/bin/deno"),
        ]

        for label_text, cmd in commands:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #334155; margin-top: 4px;")
            layout.addWidget(lbl)
            cmd_row = QHBoxLayout()
            cmd_box = QLineEdit(cmd)
            cmd_box.setReadOnly(True)
            cmd_box.setStyleSheet("""
                QLineEdit {
                    background-color: #1e293b; color: #22c55e;
                    border: 1px solid #334155; border-radius: 6px;
                    padding: 7px 10px; font-family: monospace; font-size: 12px;
                }
            """)
            copy_btn = QPushButton("Copy")
            copy_btn.setFixedWidth(64)
            copy_btn.setStyleSheet("QPushButton { background-color: #2563eb; color: white; } QPushButton:hover { background-color: #1d4ed8; }")
            copy_btn.clicked.connect(lambda _, c=cmd, b=copy_btn: self._copy_cmd(c, b))
            cmd_row.addWidget(cmd_box)
            cmd_row.addWidget(copy_btn)
            layout.addLayout(cmd_row)

        note = QLabel("After installing, restart the app. Deno is required for YouTube downloads.")
        note.setStyleSheet("color: #94a3b8; font-size: 11px; margin-top: 4px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("QPushButton { background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; } QPushButton:hover { background-color: #e2e8f0; }")
        close_btn.clicked.connect(dialog.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dialog.exec()

    def show_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("About")
        dialog.setFixedWidth(340)
        dialog.setStyleSheet("""
            QDialog { background-color: #ffffff; color: #1e293b; }
            QLabel { color: #1e293b; }
            QPushButton { border-radius: 6px; font-size: 12px; font-weight: 600; padding: 6px 14px; border: none; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if not self.app_icon.isNull():
            icon_label = QLabel()
            icon_label.setPixmap(self.app_icon.pixmap(64, 64))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)

        name_label = QLabel("Linux Download Manager")
        name_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #2563eb;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        version_label = QLabel("Version 1.0")
        version_label.setStyleSheet("font-size: 12px; color: #64748b;")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        layout.addSpacing(6)

        dev_label = QLabel("Developer")
        dev_label.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: bold;")
        dev_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(dev_label)

        email_label = QLabel("tpodbcs@gmail.com")
        email_label.setStyleSheet("font-size: 13px; color: #1e293b;")
        email_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(email_label)

        layout.addSpacing(10)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("QPushButton { background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; } QPushButton:hover { background-color: #e2e8f0; }")
        close_btn.clicked.connect(dialog.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        dialog.exec()

    def _copy_cmd(self, cmd, btn):
        QApplication.clipboard().setText(cmd)
        btn.setText("Copied!")
        btn.setStyleSheet("QPushButton { background-color: #16a34a; color: white; }")
        QTimer.singleShot(2000, lambda: (
            btn.setText("Copy"),
            btn.setStyleSheet("QPushButton { background-color: #2563eb; color: white; } QPushButton:hover { background-color: #1d4ed8; }")
        ))

    def open_youtube_dialog(self, prefill_url=""):
        dialog = YouTubeDialog(self, prefill_url=prefill_url)
        dialog.download_started.connect(self._on_yt_download_started)
        dialog.download_progress.connect(self._on_yt_progress)
        dialog.download_finished.connect(self._on_yt_finished)
        dialog.exec()

    def open_stream_dialog(self, url="", filename="", page_referer=""):
        dialog = StreamDialog(self, url=url, filename=filename, page_referer=page_referer)
        dialog.download_started.connect(self._on_yt_download_started)
        dialog.download_progress.connect(self._on_yt_progress)
        dialog.download_finished.connect(self._on_yt_finished)
        if not hasattr(self, '_stream_dialogs'):
            self._stream_dialogs = []
        self._stream_dialogs.append(dialog)
        self._stream_dialogs = [d for d in self._stream_dialogs if d.isVisible() or d is dialog]
        dialog.finished.connect(lambda: self._stream_dialogs.remove(dialog) if dialog in self._stream_dialogs else None)
        dialog.show()



    def _on_yt_download_started(self, url, display_name, folder):
        full_path = os.path.join(folder, display_name)
        category = get_category(display_name)
        row = self.table.rowCount()
        self.table.insertRow(row)
        _now = time.strftime("%Y-%m-%d %H:%M")
        self._insert_row_items(row, display_name, full_path, url, "Downloading", "—", category, _now)
        stat_item = self.table.item(row, 5)
        if stat_item:
            stat_item.setForeground(QColor("#dc2626"))
        self.row_progress[row] = 0
        self.yt_url_to_row[url] = row
        current_cat = CATEGORIES[self._category_list.currentRow()][0]
        if current_cat != "All Downloads" and current_cat != category:
            self.table.setRowHidden(row, True)
        self._update_category_counts()

    def _on_yt_progress(self, url, pct, size, speed, eta):
        row = self.yt_url_to_row.get(url)
        if row is None:
            return
        self._update_progress(row, pct)
        if size:  self._update_cell(row, 2, size)
        if speed: self._update_cell(row, 3, speed)
        if eta:   self._update_cell(row, 4, eta)

    def _on_yt_finished(self, url, status):
        row = self.yt_url_to_row.get(url)
        if row is None:
            return
        stat_item = self.table.item(row, 5)
        if stat_item:
            stat_item.setText(status)
            if status == "Finished":
                stat_item.setForeground(QColor("#16a34a"))
                self._update_progress(row, 100)
                self._update_cell(row, 4, "—")
                name_item = self.table.item(row, 0)
                filename = name_item.text().strip() if name_item else ""
                path = name_item.data(Qt.ItemDataRole.UserRole) if name_item else ""
                size = self.table.item(row, 2).text() if self.table.item(row, 2) else "—"
                category = get_category(filename)
                self._add_to_history(url, filename, path, "Finished", size, category)
                self.finished_urls[self._social_dedup_key(url)] = path
                self._notify("Download Complete", f"{filename} finished downloading.")
            else:
                stat_item.setForeground(QColor("#dc2626"))
                self._update_cell(row, 3, "—")
                self._update_cell(row, 4, "—")
                # save cancelled/failed so they survive restart
                name_item = self.table.item(row, 0)
                filename  = name_item.text().strip() if name_item else ""
                path      = name_item.data(Qt.ItemDataRole.UserRole) if name_item else ""
                size      = self.table.item(row, 2).text() if self.table.item(row, 2) else "—"
                category  = get_category(filename)
                pct       = self.row_progress.get(row, 0)
                self._add_to_history(url, filename, path, status, size, category, pct)

    def _update_taskbar_progress(self):
        active = [t for t in self.threads if t.isRunning()]
        total_pct, count = 0, 0
        total_size = 0

        for row_info in self.all_rows:
            row = row_info["row"]
            stat_item = self.table.item(row, 5)
            if stat_item and stat_item.text() == "Downloading":
                total_pct += self.row_progress.get(row, 0)
                count += 1

        total_rows = len(self.all_rows)
        finished_rows = sum(1 for r in self.all_rows
                           if self.table.item(r["row"], 5) and
                           self.table.item(r["row"], 5).text() == "Finished")

        if count > 0:
            avg = int(total_pct / count)
            self.setWindowTitle(f"Linux Download Manager  [{avg}% — {count} active]")
            self._status_bar.setText(f"  ⬇ {count} active  |  ✓ {finished_rows} completed  |  Total: {total_rows} downloads")
        else:
            self.setWindowTitle("Linux Download Manager")
            self._status_bar.setText(f"  ✓ {finished_rows} completed  |  Total: {total_rows} downloads")

    def is_duplicate(self, url):
        now = time.time()
        if url in self.recent_urls and now - self.recent_urls[url] < 5.0:
            return True
        self.recent_urls[url] = now
        self.recent_urls = {k: v for k, v in self.recent_urls.items() if now - v < 5.0}
        return False

    def _social_dedup_key(self, url):
        """
        For social CDN URLs that change tokens on every request, extract
        a stable key (video ID) for dedup instead of the full URL.
        """
        try:
            import base64, json as _json
            from urllib.parse import urlparse, parse_qs
            p    = urlparse(url)
            host = p.netloc.lower()
            if 'twimg.com' in host:
                m = re.search(r'/(\d{15,})', p.path)
                if m: return f'twimg_{m.group(1)}'
            if 'fbcdn.net' in host or 'cdninstagram.com' in host:
                qs  = parse_qs(p.query)
                efg = qs.get('efg', [None])[0]
                if efg:
                    try:
                        meta = _json.loads(base64.b64decode(efg + '==').decode())
                        vid  = meta.get('video_id')
                        if vid: return f'fbcdn_{vid}'
                    except Exception:
                        pass
            if any(d in host for d in ('instagram.com', 'facebook.com', 'fb.watch')):
                m = re.search(r'/(?:reels?|p|tv|reel|videos)/([A-Za-z0-9_\-]+)', url)
                if m: return f'fb_{m.group(1)}'
                m = re.search(r'[?&]v=(\d+)', url)
                if m: return f'fb_{m.group(1)}'
            if any(d in host for d in ('twitter.com', 'x.com')):
                m = re.search(r'/status/(\d+)', url)
                if m: return f'tw_{m.group(1)}'
        except Exception:
            pass
        return url

    def check_already_finished(self, url):
        key = self._social_dedup_key(url)
        return self.finished_urls.get(key, None)

    def show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        t = self._theme()
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {t['bg']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px; font-size: 13px; }}
            QMenu::item {{ padding: 7px 16px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {t['menu_hover']}; color: {t['menu_hover_text']}; }}
        """)

        stat_item = self.table.item(row, 5)
        status = stat_item.text() if stat_item else ""

        open_act  = menu.addAction("Open in Folder")
        props_act = menu.addAction("Properties")

        # Copy Error — only for error statuses
        copy_err_act = None
        non_error = {"Finished", "File Missing", "Downloading", "Cancelled", ""}
        if status and status not in non_error:
            menu.addSeparator()
            copy_err_act = menu.addAction("Copy Error Message")

        # Show Resume for failed/cancelled downloads
        resume_act = None
        if status not in ("Finished", "File Missing", "Downloading"):
            menu.addSeparator()
            resume_act = menu.addAction("▶  Resume Download")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))

        if action == open_act:
            path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if path:
                open_and_select(path)

        elif action == props_act:
            self._show_properties(row)

        elif copy_err_act and action == copy_err_act:
            QApplication.clipboard().setText(status)

        elif resume_act and action == resume_act:
            self._resume_download(row)

    def _show_properties(self, row):
        name_item = self.table.item(row, 0)
        if not name_item:
            return
        filename = name_item.text().strip()
        path     = name_item.data(Qt.ItemDataRole.UserRole) or ''
        url      = name_item.data(Qt.ItemDataRole.UserRole + 2) or ''
        status   = self.table.item(row, 5).text() if self.table.item(row, 5) else ''
        size     = self.table.item(row, 2).text() if self.table.item(row, 2) else ''
        date     = self.table.item(row, 6).text() if self.table.item(row, 6) else ''
        category = next((r['category'] for r in self.all_rows if r['row'] == row), '')
        folder   = os.path.dirname(path) if path else ''
        disk_size = ''
        if path and os.path.exists(path):
            try:
                b = os.path.getsize(path)
                if b >= 1024**3:   disk_size = f'{b/(1024**3):.2f} GB'
                elif b >= 1024**2: disk_size = f'{b/(1024**2):.1f} MB'
                elif b >= 1024:    disk_size = f'{b/1024:.1f} KB'
                else:              disk_size = f'{b} B'
            except Exception:
                pass
        t = self._theme()
        dialog = QDialog(self)
        dialog.setWindowTitle('Properties')
        dialog.setMinimumWidth(580)
        bg   = t['bg']
        txt  = t['text']
        ibg  = t['input_bg']
        bdr  = t['border']
        muted = t['muted']
        dialog.setStyleSheet(
            f'QDialog {{ background-color: {bg}; color: {txt}; }}'
            f'QLabel  {{ color: {txt}; font-size: 13px; }}'
            f'QLineEdit {{ background-color: {ibg}; color: {txt};'
            f'  border: 1px solid {bdr}; border-radius: 5px;'
             '  padding: 5px 10px; font-size: 12px; }}'
             'QPushButton { border-radius: 5px; font-size: 12px;'
             '  font-weight: 600; padding: 6px 14px; border: none; }'
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(4)
        title_lbl = QLabel(filename)
        title_lbl.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {txt}; margin-bottom: 6px;')
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)
        from PyQt6.QtWidgets import QFrame
        def _divider():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet(f'color: {bdr}; margin: 4px 0;')
            layout.addWidget(line)
        def _field(label_text, value, copyable=True):
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 3, 0, 3)
            hl.setSpacing(10)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(88)
            lbl.setStyleSheet(f'color: {muted}; font-size: 12px; font-weight: bold;')
            hl.addWidget(lbl)
            if copyable:
                fld = QLineEdit(value)
                fld.setReadOnly(True)
                hl.addWidget(fld)
                btn = QPushButton('Copy')
                btn.setFixedWidth(70)
                btn.setStyleSheet('QPushButton { background-color: #2563eb; color: white; padding: 6px 10px; }'
                                  'QPushButton:hover { background-color: #1d4ed8; }')
                # Use QLineEdit select+copy so clipboard works reliably
                def _make_copy_fn(field, button):
                    def _do_copy():
                        field.selectAll()
                        field.copy()
                        button.setText('Copied!')
                        button.setStyleSheet('QPushButton { background-color: #16a34a; color: white; padding: 6px 10px; }')
                        def _reset():
                            button.setText('Copy')
                            button.setStyleSheet('QPushButton { background-color: #2563eb; color: white; padding: 6px 10px; }'
                                                'QPushButton:hover { background-color: #1d4ed8; }')
                        QTimer.singleShot(1800, _reset)
                    return _do_copy
                btn.clicked.connect(_make_copy_fn(fld, btn))
                hl.addWidget(btn)
            else:
                vl = QLabel(value or '—')
                vl.setStyleSheet(f'color: {txt}; font-size: 12px;')
                vl.setWordWrap(True)
                hl.addWidget(vl)
            layout.addWidget(w)
        _field('File',      filename,  copyable=False)
        _field('Status',    status,    copyable=False)
        _field('Category',  category,  copyable=False)
        _divider()
        _field('Size',      disk_size or size or '—', copyable=False)
        _field('Date',      date or '—', copyable=False)
        _field('Folder',    folder,    copyable=True)
        _field('Full Path', path,      copyable=True)
        _divider()
        _field('Source URL', url,      copyable=True)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 10, 0, 0)
        if folder and os.path.exists(folder):
            ob = QPushButton('Open Folder')
            ob.setStyleSheet(
                'QPushButton { background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }'
                'QPushButton:hover { background-color: #e2e8f0; }'
            )
            ob.clicked.connect(lambda: subprocess.Popen(['xdg-open', folder]))
            btn_row.addWidget(ob)
        btn_row.addStretch()
        cb = QPushButton('Close')
        cb.setStyleSheet(
            'QPushButton { background-color: #2563eb; color: white; }'
            'QPushButton:hover { background-color: #1d4ed8; }'
        )
        cb.clicked.connect(dialog.close)
        btn_row.addWidget(cb)
        layout.addLayout(btn_row)
        dialog.exec()

    def _resume_download(self, row):
        name_item = self.table.item(row, 0)
        if not name_item:
            return
        url = name_item.data(Qt.ItemDataRole.UserRole + 2)
        path = name_item.data(Qt.ItemDataRole.UserRole)
        filename = name_item.text().strip()
        if not url:
            return

        # Check for partial file
        resume_from = 0
        if path and os.path.exists(path):
            resume_from = os.path.getsize(path)

        # Reset row status
        stat_item = self.table.item(row, 5)
        if stat_item:
            stat_item.setText("Downloading")
            stat_item.setForeground(QColor("#2563eb"))
        self._update_progress(row, 0 if resume_from == 0 else int(resume_from / max(resume_from + 1, 1) * 100))
        self._update_cell(row, 3, "—")
        self._update_cell(row, 4, "—")

        category = get_category(filename)
        thread = DownloadThread(url, filename, False, "", resume_from)
        self.threads.append(thread)
        thread.progress.connect(  lambda v, r=row: self._update_progress(r, v))
        thread.downloaded.connect(lambda s, r=row: self._update_cell(r, 2, s))
        thread.speed.connect(     lambda s, r=row: self._update_cell(r, 3, s))
        thread.eta.connect(       lambda e, r=row: self._update_cell(r, 4, e))
        thread.finished.connect(  lambda m, r=row, u=url, n=filename, p=path or "", c=category: self._on_finished(m, r, u, n, p, c))
        thread.start()

    def check_queue(self):
        while not url_queue.empty():
            item = url_queue.get()
            url      = item[0]
            filename = item[1]
            msg_type = item[2]
            referer  = item[3] if len(item) > 3 else ""
            if self.is_duplicate(url):
                continue
            if msg_type == "youtube":
                self.raise_()
                self.activateWindow()
                self.open_youtube_dialog(prefill_url=url)
                continue
            if msg_type == "stream_hls":
                self.raise_()
                self.activateWindow()
                # Normalize embed URLs — strips /e/, /embed/ added by iframe players
                norm_url     = normalize_stream_url(url)
                norm_referer = normalize_stream_url(referer) if referer else ""
                self.open_stream_dialog(
                    url=norm_url,
                    filename=filename if filename else "stream.mp4",
                    page_referer=norm_referer,
                )
                continue
            is_video = False  # video_stream = direct file URL, use requests/curl
            default_name = "video.mp4" if msg_type == "video_stream" else "download"
            self._check_and_enqueue(url, filename if filename else default_name, is_video, referer)
            if not is_video:
                self.url_input.setText(url)

    def start_manual(self):
        url = self.url_input.text().strip()
        if not url:
            return
        if is_youtube_url(url):
            self.open_youtube_dialog(prefill_url=url)
            return
        lurl  = url.lower()
        path  = url.split("?")[0]
        name  = path.split("/")[-1] or ""
        ext   = name.split(".")[-1].lower() if "." in name else ""
        page_exts  = {"html", "htm", "php", "asp", "aspx", "jsp"}
        video_exts = {"mp4", "mkv", "webm", "avi", "mov", "ts", "flv", "m4v"}
        # No extension or page extension = video hosting page, try yt-dlp
        if not ext or ext in page_exts:
            ts = time.strftime("%Y-%m-%d_%H-%M-%S")
            self.open_stream_dialog(url=url, filename=f"video_{ts}.mp4")
            return
        is_video = ext in video_exts or ".m3u8" in lurl or "vimeo" in lurl
        if not name:
            name = "download"
        self._check_and_enqueue(url, name, is_video, "")

    def _check_and_enqueue(self, url, filename, is_video=False, referer=""):
        existing_path = self.check_already_finished(url)
        if existing_path:
            msg = QMessageBox(self)
            msg.setWindowTitle("Already Downloaded")
            msg.setText(f"<b>{os.path.basename(existing_path)}</b> has already been downloaded.")
            msg.setInformativeText("Do you want to download it again?")
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if msg.exec() != QMessageBox.StandardButton.Yes:
                return
        self._enqueue(url, filename, is_video, referer)

    def _enqueue(self, url, filename, is_video=False, referer=""):
        folder = choose_folder(filename)
        base, ext = os.path.splitext(filename)
        unique_name, counter = filename, 1
        while os.path.exists(os.path.join(folder, unique_name)):
            unique_name = f"{base} ({counter}){ext}"
            counter += 1
        full_path = os.path.join(folder, unique_name)
        category = get_category(unique_name)
        row = self.table.rowCount()
        self.table.insertRow(row)
        _now = time.strftime("%Y-%m-%d %H:%M")
        self._insert_row_items(row, unique_name, full_path, url, "Downloading", "—", category, _now)
        stat_item = self.table.item(row, 5)
        if stat_item:
            stat_item.setForeground(QColor("#2563eb"))
        self.row_progress[row] = 0

        current_cat = CATEGORIES[self._category_list.currentRow()][0]
        if current_cat != "All Downloads" and current_cat != category:
            self.table.setRowHidden(row, True)

        self.raise_()
        self.activateWindow()
        self._update_category_counts()

        thread = DownloadThread(url, unique_name, is_video, referer)
        self.threads.append(thread)
        thread.progress.connect(  lambda v, r=row: self._update_progress(r, v))
        thread.downloaded.connect(lambda s, r=row: self._update_cell(r, 2, s))
        thread.speed.connect(     lambda s, r=row: self._update_cell(r, 3, s))
        thread.eta.connect(       lambda e, r=row: self._update_cell(r, 4, e))
        thread.finished.connect(  lambda m, r=row, u=url, n=unique_name, p=full_path, c=category: self._on_finished(m, r, u, n, p, c))
        thread.start()

    def _update_progress(self, row, value):
        # Never go backwards unless resetting to 0 (new download start)
        current = self.row_progress.get(row, 0)
        if value < current and value != 0:
            return
        self.row_progress[row] = value
        item = self.table.item(row, 1)
        if item:
            item.setData(Qt.ItemDataRole.UserRole + 1, value)
            item.setData(Qt.ItemDataRole.UserRole + 3, self.dark_mode)
            self.table.viewport().update()

    def _update_cell(self, row, col, text):
        item = self.table.item(row, col)
        if item:
            item.setText(text)
            if col == 5:
                item.setToolTip(text)
        else:
            new_item = QTableWidgetItem(text)
            new_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            new_item.setFlags(new_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col == 5:
                new_item.setToolTip(text)
            self.table.setItem(row, col, new_item)

    def _on_finished(self, msg, row, url, filename, path, category):
        item = self.table.item(row, 5)
        if item:
            item.setText(msg)
            if msg == "Finished":
                item.setForeground(QColor("#16a34a"))
                self._update_progress(row, 100)
                self._update_cell(row, 4, "—")
                self.finished_urls[self._social_dedup_key(url)] = path
                size = self.table.item(row, 2).text() if self.table.item(row, 2) else "—"
                self._add_to_history(url, filename, path, "Finished", size, category)
                self._notify("Download Complete", f"{filename} finished downloading.")
            else:
                item.setForeground(QColor("#dc2626"))
                self._update_cell(row, 3, "—")
                self._update_cell(row, 4, "—")
                # save cancelled/failed so they survive restart and can be resumed
                size = self.table.item(row, 2).text() if self.table.item(row, 2) else "—"
                pct  = self.row_progress.get(row, 0)
                self._add_to_history(url, filename, path, msg, size, category, pct)

    def _resume_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            self._resume_download(row)
            
    def _on_selection_changed(self):
        row = self.table.currentRow()
        if row < 0:
            self.resume_btn.setEnabled(False)
            self._set_btn_opacity(self.resume_btn, 0.3)
            return
        stat_item = self.table.item(row, 5)
        status = stat_item.text() if stat_item else ""
        resumable = status not in ("Finished", "File Missing", "Downloading", "")
        self.resume_btn.setEnabled(resumable)
        self._set_btn_opacity(self.resume_btn, 1.0 if resumable else 0.3)
    
    def _set_btn_opacity(self, btn, opacity):
        effect = QGraphicsOpacityEffect(btn)
        effect.setOpacity(opacity)
        btn.setGraphicsEffect(effect)

    def _open_donate(self):
        t = self._theme()
        dialog = QDialog(self)
        dialog.setWindowTitle("Support Development")
        dialog.setFixedWidth(460)
        dialog.setStyleSheet(f"QDialog {{ background-color: {t['bg']}; color: {t['text']}; }}"
                             f"QLabel {{ color: {t['text']}; }}"
                              "QPushButton { border-radius: 6px; font-size: 12px; font-weight: 600; padding: 6px 14px; border: none; }")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Support Development ❤")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #d97706;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Scan with Binance App to donate")
        sub.setStyleSheet(f"font-size: 12px; color: {t['muted']};")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        qr_label = QLabel()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        qr_path = os.path.join(script_dir, "icons", "binance_pay.png")
        pix = QPixmap(qr_path).scaled(420, 420, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        qr_label.setPixmap(pix)
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(qr_label)

        user_label = QLabel("User-ec639")
        user_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #d97706;")
        user_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(user_label)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(f"QPushButton {{ background-color: {t['input_bg']}; color: {t['muted']}; border: 1px solid {t['border']}; }}"
                                 f"QPushButton:hover {{ background-color: {t['menu_hover']}; }}")
        close_btn.clicked.connect(dialog.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        dialog.exec()

    def cancel_last(self):
        for t in reversed(self.threads):
            if t.isRunning():
                t.stop()
                break

    def clear_item(self):
        row = self.table.currentRow()
        if row >= 0:
            name_item = self.table.item(row, 0)
            if name_item:
                url = name_item.data(Qt.ItemDataRole.UserRole + 2)
                if url:
                    self.history = [e for e in self.history if e.get("url") != url]
                    save_history(self.history)
                    self.finished_urls.pop(url, None)
            self.table.removeRow(row)
            self.row_progress.pop(row, None)
            self.all_rows = [r for r in self.all_rows if r["row"] != row]
            for r in self.all_rows:
                if r["row"] > row:
                    r["row"] -= 1
            new_progress = {}
            for r, v in self.row_progress.items():
                new_r = r - 1 if r > row else r
                new_progress[new_r] = v
            self.row_progress = new_progress
            self._update_category_counts()

    def clear_list(self):
        self.history = []
        save_history(self.history)
        self.finished_urls = {}
        self.table.setRowCount(0)
        self.all_rows = []
        self.row_progress = {}
        self.yt_url_to_row = {}
        self.threads = [t for t in self.threads if t.isRunning()]
        self._update_category_counts()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DownloadManager()
    window.show()
    sys.exit(app.exec())