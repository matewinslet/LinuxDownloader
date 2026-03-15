#!/usr/bin/env python3

# Linux Download Manager
# Copyright (c) 2025 Tanjim — tpodbcs@gmail.com
# All rights reserved. See LICENSE.txt for details.

import sys, requests, time, os, threading, queue, subprocess, re, shutil
import yt_dlp
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMenu,
    QMessageBox, QListWidget, QListWidgetItem, QLabel, QAbstractItemView,
    QStyledItemDelegate, QStyle, QMenuBar,
    QDialog, QComboBox, QRadioButton, QGroupBox,
    QProgressBar, QTextEdit
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QSize, QRect
from PyQt6.QtGui import QIcon, QColor, QFont, QPainter, QAction

HOME = os.path.expanduser("~")

file_types = {
    "Videos":     ["mp4", "mkv", "avi", "mov", "webm"],
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
        "webm": "video-x-generic",
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

url_queue = queue.Queue()

class BridgeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            q = parse_qs(urlparse(self.path).query)
            url = q.get("url", [None])[0]
            filename = q.get("filename", [None])[0]
            msg_type = q.get("type", ["file"])[0]
            if url:
                url_queue.put((url, filename, msg_type))
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
    def paint(self, painter, option, index):
        value = index.data(Qt.ItemDataRole.UserRole + 1)
        if value is None:
            super().paint(painter, option, index)
            return
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#dbeafe"))
        else:
            painter.fillRect(option.rect, QColor("#ffffff") if index.row() % 2 == 0 else QColor("#f8fafc"))
        bar_rect = option.rect.adjusted(8, 6, -8, -6)
        bar_h = bar_rect.height()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e2e8f0"))
        painter.drawRoundedRect(bar_rect, bar_h // 2, bar_h // 2)
        if value > 0:
            filled_w = int(bar_rect.width() * value / 100)
            filled_rect = QRect(bar_rect.x(), bar_rect.y(), filled_w, bar_rect.height())
            color = QColor("#16a34a") if value >= 100 else QColor("#22c55e")
            painter.setBrush(color)
            painter.drawRoundedRect(filled_rect, bar_h // 2, bar_h // 2)
        painter.setPen(QColor("#1e293b"))
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
            else:
                self.size_info.emit(format_size(dl))
            self.log.emit(f"Downloading... {p}% at {d.get('_speed_str', '—')}")
        elif d['status'] == 'finished':
            self.progress.emit(100)
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
    download_progress = pyqtSignal(str, int, str, str)
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
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': audio_fmt,
                    'preferredquality': '0',
                }],
                'quiet': True,
                'no_warnings': True,
                'http_headers': {'User-Agent': HEADERS['User-Agent']},
            }
        elif self.radio_video_only.isChecked():
            folder = os.path.join(HOME, "Downloads", "Videos")
            os.makedirs(folder, exist_ok=True)
            display_name = f"{safe_title}.mp4"
            if quality == "Best":
                fmt = "bestvideo/best"
            else:
                h = quality.replace("p", "")
                fmt = f"bestvideo[height<={h}]/bestvideo/best"
            ydl_opts = {
                'format': fmt,
                'outtmpl': os.path.join(folder, f"{safe_title}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'http_headers': {'User-Agent': HEADERS['User-Agent']},
            }
        else:
            folder = os.path.join(HOME, "Downloads", "Videos")
            os.makedirs(folder, exist_ok=True)
            display_name = f"{safe_title}.mp4"
            if quality == "Best":
                fmt = "bestvideo+bestaudio/best"
            else:
                h = quality.replace("p", "")
                fmt = f"bestvideo[height<={h}]+bestaudio/bestvideo[height<={h}]/best"
            ydl_opts = {
                'format': fmt,
                'outtmpl': os.path.join(folder, f"{safe_title}.%(ext)s"),
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
                'http_headers': {'User-Agent': HEADERS['User-Agent']},
            }

        self.download_started.emit(url, display_name, folder)

        self.dl_thread = YouTubeDownloadThread(url, ydl_opts)
        self.dl_thread.progress.connect(self._on_progress)
        self.dl_thread.speed.connect(self._on_speed)
        self.dl_thread.size_info.connect(self._on_size)
        self.dl_thread.log.connect(lambda msg: self.log_box.append(msg))
        self.dl_thread.finished.connect(self.on_download_finished)
        self.dl_thread.start()
        self.log_box.append("Starting download...")

    def _on_progress(self, pct):
        self.progress_bar.setValue(pct)
        self.download_progress.emit(self._current_url, pct, self._last_size, self._last_speed)

    def _on_speed(self, spd):
        self._last_speed = spd
        self._refresh_info()
        self.download_progress.emit(self._current_url, self.progress_bar.value(), self._last_size, spd)

    def _on_size(self, sz):
        self._last_size = sz
        self._refresh_info()

    def _refresh_info(self):
        parts = []
        if self._last_size:
            parts.append(self._last_size)
        if self._last_speed:
            parts.append(self._last_speed)
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
class DownloadThread(QThread):
    progress   = pyqtSignal(int)
    speed      = pyqtSignal(str)
    downloaded = pyqtSignal(str)
    finished   = pyqtSignal(str)

    def __init__(self, url, filename, is_video=False):
        super().__init__()
        self.url = url
        self.filename = filename
        self.is_video = is_video
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
            else:
                self.downloaded.emit(format_size(dl_bytes))
        elif d['status'] == 'finished':
            self.progress.emit(100)
            self.downloaded.emit(format_size(d.get('total_bytes') or 0))

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
                "-A", HEADERS["User-Agent"], self.url
            ]
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
                self.finished.emit("Finished")
            else:
                self.finished.emit("curl Failed")
        except Exception as e:
            self.finished.emit(f"Error: {str(e)[:60]}")

    def download_with_requests(self):
        try:
            session = requests.Session()
            session.headers.update(HEADERS)
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
                    m = re.search(r'filename\*?=["\'`]?(?:UTF-\d[\'"]*)?([^;"\'`\n]+)', cd, re.I)
                    if m:
                        self.filename = m.group(1).strip().strip('"\'')
            except Exception:
                pass
            folder = choose_folder(self.filename)
            filepath = os.path.join(folder, self.filename)
            with session.get(self.url, stream=True, allow_redirects=True, timeout=30, verify=False) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0) or 0)
                downloaded_bytes = 0
                start_time = time.time()
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if not self.running:
                            self.finished.emit("Cancelled")
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            if total > 0:
                                self.progress.emit(int(downloaded_bytes * 100 / total))
                                self.downloaded.emit(
                                    f"{format_size(downloaded_bytes)} / {format_size(total)}"
                                )
                            else:
                                self.downloaded.emit(format_size(downloaded_bytes))
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                spd = downloaded_bytes / elapsed
                                if spd >= 1024 * 1024:
                                    self.speed.emit(f"{spd / (1024 * 1024):.2f} MB/s")
                                else:
                                    self.speed.emit(f"{spd / 1024:.1f} KB/s")
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
        self.resize(1100, 620)
        self.recent_urls = {}
        self.finished_urls = {}
        self.all_rows = []
        self.row_progress = {}
        self.yt_url_to_row = {}

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

        self.app_icon = app_icon  # save for use in show_about and sidebar
        self._build_ui()
        self.threads = []
        start_bridge_server()
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_queue)
        self.timer.start(500)
        self.taskbar_timer = QTimer()
        self.taskbar_timer.timeout.connect(self._update_taskbar_progress)
        self.taskbar_timer.start(1000)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        menubar = QMenuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #f8fafc; color: #1e293b;
                border-bottom: 1px solid #e2e8f0;
                font-size: 13px; padding: 2px 4px;
            }
            QMenuBar::item { padding: 4px 10px; border-radius: 4px; }
            QMenuBar::item:selected { background-color: #eff6ff; color: #2563eb; }
            QMenu {
                background-color: #ffffff; color: #1e293b;
                border: 1px solid #e2e8f0; border-radius: 6px;
                padding: 4px; font-size: 13px;
            }
            QMenu::item { padding: 7px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #eff6ff; color: #2563eb; }
            QMenu::separator { height: 1px; background: #e2e8f0; margin: 4px 8px; }
        """)

        file_menu = menubar.addMenu("File")
        yt_action = QAction("YouTube Downloader", self)
        yt_action.setShortcut("Ctrl+Y")
        yt_action.triggered.connect(lambda: self.open_youtube_dialog())
        file_menu.addAction(yt_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(QApplication.quit)
        file_menu.addAction(quit_action)

        help_menu = menubar.addMenu("Help")
        deps_action = QAction("Install Dependencies", self)
        deps_action.triggered.connect(self.install_dependencies)
        help_menu.addAction(deps_action)
        help_menu.addSeparator()
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        outer.addWidget(menubar)

        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QWidget()
        sidebar.setFixedWidth(180)
        sidebar.setStyleSheet("""
            QWidget#sidebar { background-color: #f8fafc; border-right: 1px solid #e2e8f0; }
        """)
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        title_widget = QWidget()
        title_widget.setStyleSheet("background-color: #ffffff; border-bottom: 1px solid #e2e8f0;")
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(10, 8, 10, 8)
        title_layout.setSpacing(8)

        # App icon next to LDM text
        icon_label = QLabel()
        icon_label.setFixedSize(28, 28)
        icon_label.setScaledContents(True)
        # Try theme icon first, then direct PNG file
        pix = self.app_icon.pixmap(28, 28) if not self.app_icon.isNull() else None
        if pix is None or pix.isNull():
            script_dir = os.path.dirname(os.path.abspath(__file__))
            png_path = os.path.join(script_dir, "icons", "linux-downloader-48.png")
            if os.path.exists(png_path):
                from PyQt6.QtGui import QPixmap
                pix = QPixmap(png_path).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if pix and not pix.isNull():
            icon_label.setPixmap(pix)
        title_layout.addWidget(icon_label)

        title_label = QLabel("LDM")
        title_label.setStyleSheet("color: #2563eb; font-size: 16px; font-weight: bold; letter-spacing: 2px;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        sidebar_layout.addWidget(title_widget)

        self.category_list = QListWidget()
        self.category_list.setStyleSheet("""
            QListWidget { background: transparent; border: none; outline: none; padding: 6px 0px; }
            QListWidget::item { color: #64748b; padding: 8px 10px 8px 14px; border-radius: 6px; margin: 1px 8px; font-size: 13px; }
            QListWidget::item:hover { background-color: #f1f5f9; color: #334155; }
            QListWidget::item:selected { background-color: #eff6ff; color: #2563eb; font-weight: bold; }
        """)
        self.category_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label, emoji, color in CATEGORIES:
            item = QListWidgetItem(f"  {emoji}  {label}")
            item.setData(Qt.ItemDataRole.UserRole, label)
            self.category_list.addItem(item)
        self.category_list.setCurrentRow(0)
        self.category_list.currentRowChanged.connect(self.filter_by_category)
        sidebar_layout.addWidget(self.category_list)
        sidebar_layout.addStretch()
        root.addWidget(sidebar)

        content = QWidget()
        content.setStyleSheet("background-color: #ffffff;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 12, 14, 12)
        content_layout.setSpacing(8)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste URL here — YouTube links open the YouTube Downloader automatically...")
        self.url_input.setStyleSheet("""
            QLineEdit {
                background-color: #f8fafc; color: #1e293b;
                border: 1px solid #e2e8f0; border-radius: 6px;
                padding: 7px 12px; font-size: 13px;
            }
            QLineEdit:focus { border: 1px solid #2563eb; background-color: #ffffff; }
        """)
        content_layout.addWidget(self.url_input)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_base = "font-weight: 600; border-radius: 6px; font-size: 12px; min-width: 100px; min-height: 56px; border: none;"

        self.start_btn      = QPushButton("START\nDOWNLOAD")
        self.cancel_btn     = QPushButton("CANCEL\nDOWNLOAD")
        self.clear_item_btn = QPushButton("CLEAR\nITEM")
        self.clear_btn      = QPushButton("CLEAR\nLIST")

        self.start_btn.setStyleSheet(f"QPushButton {{ {btn_base} background-color: #16a34a; color: white; }} QPushButton:hover {{ background-color: #15803d; }}")
        self.cancel_btn.setStyleSheet(f"QPushButton {{ {btn_base} background-color: #dc2626; color: white; }} QPushButton:hover {{ background-color: #b91c1c; }}")
        self.clear_item_btn.setStyleSheet(f"QPushButton {{ {btn_base} background-color: #f97316; color: white; }} QPushButton:hover {{ background-color: #ea580c; }}")
        self.clear_btn.setStyleSheet(f"QPushButton {{ {btn_base} background-color: #fb923c; color: white; }} QPushButton:hover {{ background-color: #f97316; }}")

        for b in [self.start_btn, self.cancel_btn, self.clear_item_btn, self.clear_btn]:
            btn_layout.addWidget(b)

        self.start_btn.clicked.connect(self.start_manual)
        self.cancel_btn.clicked.connect(self.cancel_last)
        self.clear_item_btn.clicked.connect(self.clear_item)
        self.clear_btn.clicked.connect(self.clear_list)
        content_layout.addLayout(btn_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["File Name", "Progress", "Downloaded", "Speed", "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 130)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(18, 18))
        self.table.setAlternatingRowColors(True)
        self.progress_delegate = ProgressDelegate(self.table)
        self.table.setItemDelegateForColumn(1, self.progress_delegate)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff; alternate-background-color: #f8fafc;
                color: #1e293b; border: 1px solid #e2e8f0; border-radius: 6px;
                font-size: 13px; gridline-color: #f1f5f9; outline: none;
            }
            QTableWidget::item { padding: 6px 10px; border: none; }
            QTableWidget::item:selected { background-color: #dbeafe; color: #1e293b; }
            QHeaderView::section {
                background-color: #f8fafc; color: #94a3b8;
                padding: 7px 10px; border: none;
                border-bottom: 1px solid #e2e8f0;
                font-size: 11px; font-weight: bold; letter-spacing: 1px;
            }
            QScrollBar:vertical { background: #f8fafc; width: 6px; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 3px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        content_layout.addWidget(self.table)
        root.addWidget(content)
        outer.addWidget(body)

    def install_dependencies(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Install Dependencies")
        dialog.setMinimumWidth(520)
        dialog.setStyleSheet("""
            QDialog { background-color: #ffffff; color: #1e293b; }
            QLabel { color: #1e293b; font-size: 13px; }
            QPushButton {
                border-radius: 6px; font-size: 12px;
                font-weight: 600; padding: 6px 14px; border: none;
            }
            QLineEdit {
                border-radius: 6px;
                padding: 7px 10px;
                font-family: monospace;
                font-size: 12px;
                border: 1px solid #334155;
            }
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
            (
                "1. System packages  (ffmpeg, curl)",
                "sudo apt install -y ffmpeg curl"
            ),
            (
                "2. Python packages  (PyQt6, requests, yt-dlp)",
                "pip install PyQt6 requests yt-dlp --break-system-packages"
            ),
            (
                "3. Deno  —  JavaScript runtime required for YouTube",
                "curl -fsSL https://deno.land/install.sh | sh && sudo ln -sf ~/.deno/bin/deno /usr/local/bin/deno"
            ),
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
                    background-color: #1e293b;
                    color: #22c55e;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 7px 10px;
                    font-family: monospace;
                    font-size: 12px;
                }
            """)
            copy_btn = QPushButton("Copy")
            copy_btn.setFixedWidth(64)
            copy_btn.setStyleSheet(
                "QPushButton { background-color: #2563eb; color: white; }"
                "QPushButton:hover { background-color: #1d4ed8; }"
            )
            copy_btn.clicked.connect(lambda _, c=cmd, b=copy_btn: self._copy_cmd(c, b))
            cmd_row.addWidget(cmd_box)
            cmd_row.addWidget(copy_btn)
            layout.addLayout(cmd_row)

        note = QLabel("After installing, restart the app. Deno is required for YouTube downloads.")
        note.setStyleSheet("color: #94a3b8; font-size: 11px; margin-top: 4px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "QPushButton { background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }"
            "QPushButton:hover { background-color: #e2e8f0; }"
        )
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
            QPushButton {
                border-radius: 6px; font-size: 12px;
                font-weight: 600; padding: 6px 14px; border: none;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icon
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
        close_btn.setStyleSheet(
            "QPushButton { background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }"
            "QPushButton:hover { background-color: #e2e8f0; }"
        )
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
            btn.setStyleSheet(
                "QPushButton { background-color: #2563eb; color: white; }"
                "QPushButton:hover { background-color: #1d4ed8; }"
            )
        ))

    def open_youtube_dialog(self, prefill_url=""):
        dialog = YouTubeDialog(self, prefill_url=prefill_url)
        dialog.download_started.connect(self._on_yt_download_started)
        dialog.download_progress.connect(self._on_yt_progress)
        dialog.download_finished.connect(self._on_yt_finished)
        dialog.exec()

    def _on_yt_download_started(self, url, display_name, folder):
        full_path = os.path.join(folder, display_name)
        category = get_category(display_name)
        row = self.table.rowCount()
        self.table.insertRow(row)

        name_item = QTableWidgetItem(f"  {display_name}")
        name_item.setData(Qt.ItemDataRole.UserRole, full_path)
        name_item.setIcon(get_file_icon(display_name))
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        prog_item = QTableWidgetItem()
        prog_item.setData(Qt.ItemDataRole.UserRole + 1, 0)
        prog_item.setFlags(prog_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        dl_item   = QTableWidgetItem("—")
        spd_item  = QTableWidgetItem("—")
        stat_item = QTableWidgetItem("Downloading")

        for item in [dl_item, spd_item, stat_item]:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        stat_item.setForeground(QColor("#dc2626"))

        self.table.setItem(row, 0, name_item)
        self.table.setItem(row, 1, prog_item)
        self.table.setItem(row, 2, dl_item)
        self.table.setItem(row, 3, spd_item)
        self.table.setItem(row, 4, stat_item)
        self.table.setRowHeight(row, 38)

        self.all_rows.append({"row": row, "category": category})
        self.row_progress[row] = 0
        self.yt_url_to_row[url] = row

        current_cat = CATEGORIES[self.category_list.currentRow()][0]
        if current_cat != "All Downloads" and current_cat != category:
            self.table.setRowHidden(row, True)

    def _on_yt_progress(self, url, pct, size, speed):
        row = self.yt_url_to_row.get(url)
        if row is None:
            return
        self._update_progress(row, pct)
        if size:
            self._update_cell(row, 2, size)
        if speed:
            self._update_cell(row, 3, speed)

    def _on_yt_finished(self, url, status):
        row = self.yt_url_to_row.get(url)
        if row is None:
            return
        stat_item = self.table.item(row, 4)
        if stat_item:
            stat_item.setText(status)
            if status == "Finished":
                stat_item.setForeground(QColor("#16a34a"))
                self._update_progress(row, 100)
            else:
                stat_item.setForeground(QColor("#dc2626"))
                self._update_cell(row, 3, "—")

    def _update_taskbar_progress(self):
        active = [t for t in self.threads if t.isRunning()]
        if not active:
            self.setWindowTitle("Linux Download Manager")
            return
        total_pct, count = 0, 0
        for row_info in self.all_rows:
            row = row_info["row"]
            stat_item = self.table.item(row, 4)
            if stat_item and stat_item.text() == "Downloading":
                total_pct += self.row_progress.get(row, 0)
                count += 1
        if count > 0:
            self.setWindowTitle(f"Linux Download Manager  [{int(total_pct/count)}% — {count} active]")
        else:
            self.setWindowTitle("Linux Download Manager")

    def filter_by_category(self, index):
        selected = CATEGORIES[index][0]
        for row_info in self.all_rows:
            row = row_info["row"]
            cat = row_info["category"]
            self.table.setRowHidden(row, False if selected == "All Downloads" else cat != selected)

    def is_duplicate(self, url):
        now = time.time()
        if url in self.recent_urls and now - self.recent_urls[url] < 5.0:
            return True
        self.recent_urls[url] = now
        self.recent_urls = {k: v for k, v in self.recent_urls.items() if now - v < 5.0}
        return False

    def check_already_finished(self, url):
        return self.finished_urls.get(url, None)

    def show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row >= 0:
            menu = QMenu()
            menu.setStyleSheet("""
                QMenu { background-color: #ffffff; color: #1e293b; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; font-size: 13px; }
                QMenu::item { padding: 7px 16px; border-radius: 4px; }
                QMenu::item:selected { background-color: #eff6ff; color: #2563eb; }
            """)
            open_act = menu.addAction("Open in Folder")
            if menu.exec(self.table.viewport().mapToGlobal(pos)) == open_act:
                path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if path and os.path.exists(os.path.dirname(path)):
                    subprocess.Popen(['xdg-open', os.path.dirname(path)])

    def check_queue(self):
        while not url_queue.empty():
            url, filename, msg_type = url_queue.get()
            if self.is_duplicate(url):
                continue
            if msg_type == "youtube":
                self.raise_()
                self.activateWindow()
                self.open_youtube_dialog(prefill_url=url)
                continue
            is_video = (msg_type == "video_stream")
            default_name = "video.mp4" if is_video else "download"
            self._check_and_enqueue(url, filename if filename else default_name, is_video)
            if not is_video:
                self.url_input.setText(url)

    def start_manual(self):
        url = self.url_input.text().strip()
        if not url:
            return
        if is_youtube_url(url):
            self.open_youtube_dialog(prefill_url=url)
            return
        lurl = url.lower()
        is_video = any(x in lurl for x in [".mp4", ".mkv", ".webm", ".m3u8", "vimeo"])
        name = url.split("?")[0].split("/")[-1] or "download"
        self._check_and_enqueue(url, name, is_video)

    def _check_and_enqueue(self, url, filename, is_video=False):
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
        self._enqueue(url, filename, is_video)

    def _enqueue(self, url, filename, is_video=False):
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

        name_item = QTableWidgetItem(unique_name)
        name_item.setData(Qt.ItemDataRole.UserRole, full_path)
        name_item.setIcon(get_file_icon(unique_name))
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        prog_item = QTableWidgetItem()
        prog_item.setData(Qt.ItemDataRole.UserRole + 1, 0)
        prog_item.setFlags(prog_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        dl_item   = QTableWidgetItem("—")
        spd_item  = QTableWidgetItem("—")
        stat_item = QTableWidgetItem("Downloading")

        for item in [dl_item, spd_item, stat_item]:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        stat_item.setForeground(QColor("#2563eb"))

        self.table.setItem(row, 0, name_item)
        self.table.setItem(row, 1, prog_item)
        self.table.setItem(row, 2, dl_item)
        self.table.setItem(row, 3, spd_item)
        self.table.setItem(row, 4, stat_item)
        self.table.setRowHeight(row, 38)

        self.all_rows.append({"row": row, "category": category})
        self.row_progress[row] = 0

        current_cat = CATEGORIES[self.category_list.currentRow()][0]
        if current_cat != "All Downloads" and current_cat != category:
            self.table.setRowHidden(row, True)

        self.raise_()
        self.activateWindow()

        thread = DownloadThread(url, unique_name, is_video)
        self.threads.append(thread)
        thread.progress.connect(  lambda v, r=row: self._update_progress(r, v))
        thread.downloaded.connect(lambda s, r=row: self._update_cell(r, 2, s))
        thread.speed.connect(     lambda s, r=row: self._update_cell(r, 3, s))
        thread.finished.connect(  lambda m, r=row, u=url: self._on_finished(m, r, u))
        thread.start()

    def _update_progress(self, row, value):
        self.row_progress[row] = value
        item = self.table.item(row, 1)
        if item:
            item.setData(Qt.ItemDataRole.UserRole + 1, value)
            self.table.viewport().update()

    def _update_cell(self, row, col, text):
        item = self.table.item(row, col)
        if item:
            item.setText(text)
        else:
            new_item = QTableWidgetItem(text)
            new_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            new_item.setFlags(new_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col, new_item)

    def _on_finished(self, msg, row, url):
        item = self.table.item(row, 4)
        if item:
            item.setText(msg)
            if msg == "Finished":
                item.setForeground(QColor("#16a34a"))
                self._update_progress(row, 100)
            else:
                item.setForeground(QColor("#dc2626"))
                self._update_cell(row, 3, "—")
        if msg == "Finished":
            name_item = self.table.item(row, 0)
            path = name_item.data(Qt.ItemDataRole.UserRole) if name_item else ""
            self.finished_urls[url] = path or url

    def cancel_last(self):
        for t in reversed(self.threads):
            if t.isRunning():
                t.stop()
                break

    def clear_item(self):
        row = self.table.currentRow()
        if row >= 0:
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

    def clear_list(self):
        self.table.setRowCount(0)
        self.all_rows = []
        self.row_progress = {}
        self.yt_url_to_row = {}
        self.threads = [t for t in self.threads if t.isRunning()]


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DownloadManager()
    window.show()
    sys.exit(app.exec())