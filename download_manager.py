#!/usr/bin/env python3
# Linux Download Manager
# Copyright (c) 2026 Tanjim — tpodbcs@gmail.com
# Licensed under the MIT License. See LICENSE.txt for details.

import sys, time, os, threading, queue, subprocess, re, shutil, json, glob

# curl_cffi gives Firefox TLS fingerprinting — required for Lulu CDN
try:
    from curl_cffi import requests
    _CURL_CFFI = True
except ImportError:
    import requests
    _CURL_CFFI = False

# AES-128 decryption for encrypted HLS segments
try:
    from Crypto.Cipher import AES as _AES
    _HAS_AES = True
except ImportError:
    _HAS_AES = False
import yt_dlp
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, unquote
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMenu,
    QMessageBox, QListWidget, QListWidgetItem, QLabel, QAbstractItemView,
    QStyledItemDelegate, QStyle, QMenuBar, QMainWindow,
    QDialog, QComboBox, QRadioButton, QGroupBox,
    QProgressBar, QTextEdit, QSizePolicy, QCheckBox, QFileDialog, QFrame,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QStackedWidget
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QSize, QRect, QPointF, QRectF
from PyQt6.QtGui import (
    QIcon, QColor, QFont, QPainter, QAction, QPixmap, QPen,
    QLinearGradient, QRadialGradient, QPalette, QPainterPath, QBrush,
    QFontDatabase, QFontMetrics
)

HOME = os.path.expanduser("~")

def get_firefox_profile():
    """Auto-detect Firefox profile directory across different Linux setups."""
    candidates = [
        os.path.join(HOME, '.mozilla', 'firefox'),
        os.path.join(HOME, '.var', 'app', 'org.mozilla.firefox', 'config', 'mozilla', 'firefox'),
        os.path.join(HOME, '.var', 'app', 'org.mozilla.firefox', '.mozilla', 'firefox'),
        os.path.join(HOME, 'snap', 'firefox', 'common', '.mozilla', 'firefox'),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return os.path.join(HOME, '.mozilla', 'firefox')  # fallback
CONFIG_DIR = os.path.join(HOME, ".config", "ldm")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
# yt-dlp writes fragment + .part files here instead of the user's Downloads
# folder, so file managers don't flicker through dozens of throwaway files.
YT_DLP_TEMP_DIR = os.path.join(HOME, ".cache", "ldm", "ytdlp-tmp")

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(YT_DLP_TEMP_DIR, exist_ok=True)



# ── Theme definitions ────────────────────────────────────────────────────────
THEMES = {
    "light": {
        "bg":                "#f8fafc",
        "sidebar":           "#ffffff",
        "border":            "#e2e8f0",
        "text":              "#1e293b",
        "muted":             "#64748b",
        "faint":             "#94a3b8",
        "alt_row":           "#f8fafc",
        "selected":          "#eff6ff",
        "selected_text":     "#2563eb",
        "header":            "#f8fafc",
        "menu_bg":           "#ffffff",
        "menu_hover":        "#eff6ff",
        "menu_hover_text":   "#2563eb",
        "input_bg":          "#ffffff",
        "input_focus":       "#ffffff",
        "progress_track":    "#f1f5f9",
        "scrollbar":         "#f8fafc",
        "scrollbar_handle":  "#cbd5e1",
        "grid":              "#f1f5f9",
        "status_bar":        "#ffffff",
        "category_hover":    "#f1f5f9",
        "category_hover_text": "#334155",
        "category_sel":      "#eff6ff",
        "category_sel_text": "#2563eb",
        "toolbar_bg":        "#ffffff",
        "surface":           "#ffffff",
        "accent":            "#2563eb",
    },
    "dark": {
        "bg":                "#0f172a",
        "sidebar":           "#1e293b",
        "border":            "#334155",
        "text":              "#e2e8f0",
        "muted":             "#94a3b8",
        "faint":             "#64748b",
        "alt_row":           "#0f172a",
        "selected":          "rgba(59,130,246,0.15)",
        "selected_text":     "#60a5fa",
        "header":            "#1e293b",
        "menu_bg":           "#1e293b",
        "menu_hover":        "rgba(59,130,246,0.15)",
        "menu_hover_text":   "#60a5fa",
        "input_bg":          "#1e293b",
        "input_focus":       "#1e293b",
        "progress_track":    "rgba(255,255,255,0.06)",
        "scrollbar":         "#0f172a",
        "scrollbar_handle":  "#475569",
        "grid":              "#1e293b",
        "status_bar":        "#1e293b",
        "category_hover":    "rgba(59,130,246,0.08)",
        "category_hover_text": "#cbd5e1",
        "category_sel":      "rgba(59,130,246,0.15)",
        "category_sel_text": "#60a5fa",
        "toolbar_bg":        "#1e293b",
        "surface":           "#1e293b",
        "accent":            "#3b82f6",
    }
}

file_types = {
    "Videos":     ["mp4", "mkv", "avi", "mov", "webm", "ts"],
    "Music":      ["mp3", "flac", "aac", "wav", "ogg", "m4a"],
    "Documents":  ["pdf", "doc", "docx", "txt", "ppt", "pptx"],
    "Compressed": ["zip", "rar", "7z", "tar", "gz"],
    "Programs":   ["exe", "bin", "appimage", "deb", "rpm", "iso"]
}

STATUS_COLORS = {
    "Downloading":  "#2563eb",
    "Finished":     "#16a34a",
    "Paused":       "#d97706",
    "Queued":       "#64748b",
    "Cancelled":    "#dc2626",
    "Error":        "#dc2626",
    "File Missing": "#dc2626",
}

CATEGORIES = [
    ("All Downloads", "⬇", "#2563eb"),
    ("Videos",        "🎬", "#dc2626"),
    ("Music",         "🎵", "#7c3aed"),
    ("Documents",     "📄", "#db2777"),
    ("Compressed",    "🗜", "#0891b2"),
    ("Programs",      "⚙",  "#4f46e5"),
]

# Squircle icon file (in assets/category_icons/) for each sidebar category.
CATEGORY_ICON_FILE = {
    "All Downloads": "all.svg",
    "Videos":        "videos.svg",
    "Music":         "music.svg",
    "Documents":     "documents.svg",
    "Compressed":    "compressed.svg",
    "Programs":      "programs.svg",
    "Others":        "others.svg",
}

# Visual tokens for the file-list redesign (LDM_file_list_v1/README.md).
# Each app status maps to dot/text/bg/bar/accent colors used by the row
# delegates. Aliases below collapse non-canonical states onto Error tokens.
FL_STATUS_TOKENS = {
    "Downloading":  {"key": "active", "dot": "#3b82f6", "text": "#1d4ed8", "bg": "#dbeafe",
                     "bar": ("#60a5fa", "#2563eb"), "accent": "#2563eb"},
    "Paused":       {"key": "paused", "dot": "#d97706", "text": "#92400e", "bg": "#fef3c7",
                     "bar": ("#fbbf24", "#d97706"), "accent": "#d97706"},
    "Queued":       {"key": "queued", "dot": "#64748b", "text": "#475569", "bg": "#e2e8f0",
                     "bar": None,                      "accent": "#94a3b8"},
    "Finished":     {"key": "done",   "dot": "#16a34a", "text": "#166534", "bg": "#dcfce7",
                     "bar": ("#4ade80", "#16a34a"), "accent": "#16a34a"},
    "Error":        {"key": "error",  "dot": "#dc2626", "text": "#991b1b", "bg": "#fee2e2",
                     "bar": ("#f87171", "#dc2626"), "accent": "#dc2626"},
}
_FL_STATUS_ALIASES = {
    "Cancelled":    "Error",
    "File Missing": "Error",
    "Interrupted":  "Error",
    "Failed":       "Error",
}

def fl_status_token(status):
    if status in FL_STATUS_TOKENS:
        return FL_STATUS_TOKENS[status]
    return FL_STATUS_TOKENS[_FL_STATUS_ALIASES.get(status, "Error")]

# App-folder label → cat id used by category_icons.jsx
CATEGORY_ID_FOR_FOLDER = {
    "All Downloads": "all", "Videos": "vid", "Music": "mus",
    "Documents": "doc", "Compressed": "zip", "Programs": "pgm", "Others": "oth",
}

_CATEGORY_PIXMAP_CACHE = {}

def get_category_pixmap(category, size=28):
    """Return the cached squircle pixmap for an app folder category."""
    key = (category, size)
    cached = _CATEGORY_PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached
    fname = CATEGORY_ICON_FILE.get(category) or CATEGORY_ICON_FILE.get("Others")
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "category_icons", fname)
    if not os.path.exists(icon_path):
        return None
    try:
        pix = _render_svg_pixmap(icon_path, size)
    except Exception:
        return None
    _CATEGORY_PIXMAP_CACHE[key] = pix
    return pix


# Extra data roles used by the file-list delegates.
FL_ROLE_CATEGORY = Qt.ItemDataRole.UserRole + 4   # set on column 0
FL_ROLE_TOTAL    = Qt.ItemDataRole.UserRole + 5   # set on column 0 (sub-meta)

# Row metrics
# Single source of truth for the download-table row height. Must match the
# value _apply_table_style() pushes into the vertical header — otherwise rows
# inserted at runtime (setRowHeight in _insert_row_items) end up taller than
# the rows already laid out at the header's default section size.
FL_ROW_HEIGHT     = 40
FL_ROW_LEFT_PAD   = 14
FL_ROW_RIGHT_PAD  = 18

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
    Uses DBus FileManager1 interface (works on GNOME/KDE/XFCE/Nautilus/Dolphin/Thunar).
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
    Also rewrite Dailymotion geo-player URLs to the canonical video URL
    that yt-dlp's extractor recognizes.
    """
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        host = p.netloc.lower()
        # Dailymotion geo player:
        #   https://geo.dailymotion.com/player/<player_skin>.html?video=<vid>
        # → https://www.dailymotion.com/video/<vid>
        # The path basename is the player skin ID, NOT the video ID — two
        # different videos sharing one skin would dedup against each other,
        # so only rewrite when the real video ID is present in the query.
        if "geo.dailymotion.com" in host:
            qs = parse_qs(p.query)
            video_id = (qs.get("video") or [None])[0]
            if video_id:
                return f"https://www.dailymotion.com/video/{video_id}"
        # Replace /e/ID or /embed/ID with /ID
        clean = re.sub(r'^/e/', '/', p.path)
        clean = re.sub(r'^/embed/', '/', clean)
        if clean != p.path:
            return urlunparse(p._replace(path=clean))
    except Exception:
        pass
    return url


def is_twimg_dash_segment(url):
    """video.twimg.com serves DASH .m4s media segments — they advertise
    content-type: video/mp4 and look downloadable, but contain only
    styp/moof/mdat boxes (no ftyp/moov), so they're not playable on
    their own. Detect them so we can route to the tweet status URL
    (which yt-dlp's TwitterIE can extract properly) instead."""
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        return (
            'video.twimg.com' in p.netloc.lower()
            and p.path.lower().endswith('.m4s')
        )
    except Exception:
        return False


def _unpack_packed_js(packed_args_str):
    """Decode a Dean-Edwards p,a,c,k,e,d packed JavaScript payload.
    Input is everything between the outer `(` and `)` of the packer call."""
    m = re.match(
        r"\s*'((?:[^'\\]|\\.)*)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*"
        r"'((?:[^'\\]|\\.)*)'\.split\('\|'\)",
        packed_args_str,
        re.DOTALL,
    )
    if not m:
        return None
    p_raw, a_str, c_str, k_str = m.groups()
    a, c = int(a_str), int(c_str)
    p = re.sub(r"\\(.)", lambda mo: mo.group(1), p_raw)
    k = k_str.split('|')
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    def encode(n):
        s = ""
        if n == 0:
            return digits[0]
        while n > 0:
            s = digits[n % a] + s
            n //= a
        return s
    for i in range(c - 1, -1, -1):
        if i < len(k) and k[i]:
            token = encode(i)
            p = re.sub(rf"\b{re.escape(token)}\b", lambda _m, v=k[i]: v, p)
    return p


def resolve_luluvdo_url(url):
    """Luluvdo / Lulustream pages hide the m3u8 inside packed JS — yt-dlp
    has no extractor for them. Fetch the embed page, decode the packer,
    and return (direct_m3u8_url, page_origin) so the caller can hand the
    HLS stream to yt-dlp's generic extractor with the right Referer."""
    m = re.match(
        r'(https?://(?:luluvdo|lulustream)\.com)/(?:e/)?([A-Za-z0-9]+)',
        url,
    )
    if not m:
        return None
    base, vid = m.groups()
    embed_url = f"{base}/e/{vid}"
    headers = {
        'User-Agent': HEADERS['User-Agent'],
        'Referer': base + '/',
    }
    try:
        resp = requests.get(embed_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception:
        return None
    pm = re.search(
        r"function\(p,a,c,k,e,d\)\{.*?\}\((.+\.split\('\|'\)\))\)",
        html,
        re.DOTALL,
    )
    if not pm:
        return None
    unpacked = _unpack_packed_js(pm.group(1))
    if not unpacked:
        return None
    sm = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', unpacked)
    if not sm:
        return None
    # The CDN expects the bare origin as Referer (verified against Firefox traffic).
    return sm.group(1), base + '/'


_PNG_SIG = b'\x89PNG\r\n\x1a\n'


def _strip_png_disguised_segments(path):
    """Some adult-stream CDNs (wishonly.site → tiktokcdn.com via qooglecdn.com)
    serve every HLS segment with Content-Type: image/png and a 70-byte 1x1 PNG
    prepended to the TS bytes — an ad-block evasion trick. yt-dlp downloads the
    bytes verbatim and concatenates, so the final .mp4 is N tiny PNGs interleaved
    with TS chunks. VLC sniffs the leading PNG, treats the file as a 1x1 image,
    and reports a ~10s duration.

    If the output starts with a PNG signature, walk the file: at each PNG, parse
    chunks until IEND and discard them; keep the TS bytes between. Then remux
    the cleaned .ts to .mp4 with ffmpeg -c copy. Replace the original on success.

    Returns True if the file was rewritten, False if no PNG prefix was present.
    """
    try:
        with open(path, 'rb') as f:
            head = f.read(8)
        if head != _PNG_SIG:
            return False
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return False
    out, i, n = bytearray(), 0, len(data)
    while i < n:
        if data[i:i+8] == _PNG_SIG:
            j = i + 8
            while j + 8 <= n:
                clen = int.from_bytes(data[j:j+4], 'big')
                ctype = data[j+4:j+8]
                j += 8 + clen + 4
                if ctype == b'IEND':
                    break
            i = j
            continue
        k = data.find(_PNG_SIG, i)
        if k < 0:
            out.extend(data[i:])
            break
        out.extend(data[i:k])
        i = k
    if not out or out[0] != 0x47:
        return False  # not MPEG-TS — leave the file alone
    ts_path = path + '.clean.ts'
    mp4_path = path + '.clean.mp4'
    try:
        with open(ts_path, 'wb') as f:
            f.write(bytes(out))
        res = subprocess.run(
            ['ffmpeg', '-y', '-fflags', '+genpts', '-i', ts_path,
             '-c', 'copy', '-bsf:a', 'aac_adtstoasc', mp4_path],
            capture_output=True,
        )
        if res.returncode != 0 or not os.path.exists(mp4_path):
            return False
        os.replace(mp4_path, path)
        return True
    finally:
        for p in (ts_path, mp4_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


# Hosts whose downloads must never be routed through LDM. Matched against the
# URL's hostname (exact or any subdomain). Mirrors the same list in the
# Firefox/Chrome extensions — defense in depth in case an older extension
# build forwards a URL anyway.
BRIDGE_BLOCKED_HOSTS = ("claude.ai", "anthropic.com", "figma.com")


def _is_blocked_bridge_host(url):
    if not url:
        return False
    # blob:/filesystem: wrap an inner origin; urlparse().hostname is None for
    # them, so peel the wrapper before parsing.
    u = url
    low = u.lower()
    if low.startswith("blob:") or low.startswith("filesystem:"):
        u = u[u.find(":") + 1:]
    try:
        host = (urlparse(u).hostname or "").lower()
    except Exception:
        return False
    for h in BRIDGE_BLOCKED_HOSTS:
        if host == h or host.endswith("." + h):
            return True
    return False


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
            if url and _is_blocked_bridge_host(url):
                # Silently drop — the extension shouldn't have forwarded this.
                self.send_response(200); self.end_headers()
                self.wfile.write(b"BLOCKED")
                return
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


# ── Gofile.io: guest-token auth ──────────────────────────────────────────────
# Gofile's CDN rejects requests without an `accountToken` cookie — without
# auth it serves an HTML landing page that the downloader would save as
# `.mp4`. Three steps are required (mirrors yt-dlp's gofile extractor):
#   1. POST /accounts → mint a guest token
#   2. Fetch /dist/js/global.js → extract `appdata.wt` (website token)
#   3. GET /contents/{contentId}?wt=… with Authorization: Bearer {token}
#      — this is the step that AUTHORIZES the token for that content.
# Skipping step 3 was the recent bug: the CDN served the landing page.
_GOFILE_TOKEN = None
_GOFILE_WT = None
_GOFILE_AUTHED_CONTENT = set()
_GOFILE_LAST_ERR = ""
_GOFILE_LOCK = threading.Lock()

def is_gofile_url(url):
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host == "gofile.io" or host.endswith(".gofile.io")

def gofile_content_id(url):
    """Extract the content ID from a Gofile URL. Handles both the CDN
    download form `/download/web/{id}/{name}` and the landing form `/d/{id}`."""
    try:
        path = urlparse(url).path
    except Exception:
        return None
    m = re.search(r"/download/web/([\w-]+)/", path)
    if m:
        return m.group(1)
    m = re.match(r"^/d/([\w-]+)", path)
    if m:
        return m.group(1)
    return None

def _firefox_gofile_token():
    """Pull the user's gofile accountToken from Firefox's localStorage.
    The browser-stored token has already been associated with content the
    user visited (the page's own /contents/ call did that), so it works
    where a freshly-minted guest token gets 401-notPremium — especially
    when Gofile is rate-limiting our IP. Returns None if not found."""
    import glob, sqlite3, shutil, tempfile
    # Firefox 150+ uses XDG paths (~/.config/mozilla/firefox); the legacy
    # ~/.mozilla path is only present on older installs. Glob both, plus
    # snap/flatpak variants, then pick the most-recently-modified match so
    # an active session's profile beats a stale one (e.g. leftover Flatpak
    # data after switching to apt).
    patterns = [
        os.path.expanduser("~/.config/mozilla/firefox/*/storage/default/https+++gofile.io/ls/data.sqlite"),
        os.path.expanduser("~/.mozilla/firefox/*/storage/default/https+++gofile.io/ls/data.sqlite"),
        os.path.expanduser("~/snap/firefox/common/.mozilla/firefox/*/storage/default/https+++gofile.io/ls/data.sqlite"),
        os.path.expanduser("~/.var/app/org.mozilla.firefox/config/mozilla/firefox/*/storage/default/https+++gofile.io/ls/data.sqlite"),
    ]
    candidates = []
    for pat in patterns:
        for path in glob.glob(pat):
            try:
                candidates.append((os.path.getmtime(path), path))
            except OSError:
                pass
    candidates.sort(reverse=True)
    for _, path in candidates:
        tmp = None
        try:
            # Copy out — Firefox holds a write lock while running.
            tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False).name
            shutil.copy2(path, tmp)
            con = sqlite3.connect(tmp)
            row = con.execute(
                "SELECT value FROM data WHERE key='appdataAccount'"
            ).fetchone()
            con.close()
            if not row:
                continue
            raw = row[0]
            blob = raw if isinstance(raw, (bytes, bytearray)) else raw.encode("latin-1", "replace")
            # Firefox stores localStorage values in Snappy-compressed
            # form. Rather than depend on a snappy lib, scan for the
            # literal `…token":"<value>"` — the value is unique and is
            # nearly always emitted as a literal run, not a back-ref.
            m = re.search(rb'oken"\s*:\s*"([A-Za-z0-9]{20,})"', blob)
            if m:
                return m.group(1).decode("ascii")
        except Exception:
            pass
        finally:
            if tmp:
                try: os.unlink(tmp)
                except Exception: pass
    return None

def get_gofile_token(content_id=None):
    """Return a Gofile guest token, pre-authorizing it for `content_id` so
    the CDN serves the actual file rather than the landing page.

    On failure, sets `_GOFILE_LAST_ERR` so the caller can surface the
    specific step that broke (accounts API / global.js / contents API)."""
    global _GOFILE_TOKEN, _GOFILE_WT, _GOFILE_LAST_ERR
    ua = HEADERS["User-Agent"]
    with _GOFILE_LOCK:
        # Reset so a stale error from a prior content doesn't leak into the
        # current attempt's "server returned HTML" detail.
        _GOFILE_LAST_ERR = ""
        token_from_browser = False
        if not _GOFILE_TOKEN:
            # 1) Prefer the user's Firefox-resident token — it works even
            # when Gofile is rate-limiting fresh /accounts mints from this
            # IP. Falls back to minting if no browser token found.
            ff = _firefox_gofile_token()
            if ff:
                _GOFILE_TOKEN = ff
                token_from_browser = True
        if not _GOFILE_TOKEN:
            try:
                r = requests.post(
                    "https://api.gofile.io/accounts",
                    headers={"User-Agent": ua},
                    timeout=15,
                )
                data = r.json()
                if data.get("status") == "ok":
                    _GOFILE_TOKEN = data["data"].get("token")
                    if not _GOFILE_TOKEN:
                        _GOFILE_LAST_ERR = "accounts API: no token in response"
                else:
                    _GOFILE_LAST_ERR = f"accounts API: status={data.get('status')!r}"
            except Exception as e:
                _GOFILE_LAST_ERR = f"accounts API: {type(e).__name__}: {str(e)[:80]}"
        if not _GOFILE_TOKEN:
            return None
        if content_id and content_id not in _GOFILE_AUTHED_CONTENT:
            if not _GOFILE_WT:
                # Gofile moved `appdata.wt` from global.js to config.js
                # (sometime before 2026). Probe both so a future move is
                # easier to spot from the error log.
                for js_path in ("/dist/js/config.js", "/dist/js/global.js"):
                    try:
                        gjs = requests.get(
                            f"https://gofile.io{js_path}",
                            headers={"User-Agent": ua},
                            timeout=15,
                        ).text
                        m = re.search(r'appdata\.wt\s*=\s*["\']([^"\']+)', gjs)
                        if m:
                            _GOFILE_WT = m.group(1)
                            break
                    except Exception as e:
                        _GOFILE_LAST_ERR = f"{js_path}: {type(e).__name__}: {str(e)[:80]}"
                if not _GOFILE_WT and not _GOFILE_LAST_ERR:
                    _GOFILE_LAST_ERR = "wt not found in config.js/global.js"
            try:
                r = requests.get(
                    f"https://api.gofile.io/contents/{content_id}",
                    params={"wt": _GOFILE_WT} if _GOFILE_WT else None,
                    headers={
                        "User-Agent": ua,
                        "Authorization": f"Bearer {_GOFILE_TOKEN}",
                    },
                    timeout=15,
                )
                jd = r.json()
                if jd.get("status") == "ok":
                    pwd = (jd.get("data") or {}).get("passwordStatus")
                    if pwd and pwd != "passwordOk":
                        _GOFILE_LAST_ERR = f"content needs password ({pwd})"
                    else:
                        _GOFILE_AUTHED_CONTENT.add(content_id)
                elif jd.get("status") == "error-notPremium" and token_from_browser:
                    # /contents/ returns notPremium for files marked
                    # premium-only — but the Firefox-resident token's
                    # cookie often still downloads them via the CDN
                    # (auth was established when the user loaded the d/
                    # page). Trust the cookie and let HEAD/GET decide.
                    _GOFILE_AUTHED_CONTENT.add(content_id)
                elif jd.get("status") == "error-notPremium":
                    _GOFILE_LAST_ERR = (
                        "Premium-only file (guests can stream-preview "
                        "but not download)"
                    )
                else:
                    _GOFILE_LAST_ERR = (
                        f"contents API: status={jd.get('status')!r}"
                        f" wt={'set' if _GOFILE_WT else 'missing'}"
                    )
            except Exception as e:
                _GOFILE_LAST_ERR = f"contents API: {type(e).__name__}: {str(e)[:80]}"
        return _GOFILE_TOKEN


# ── Gradient text label (wordmark) ───────────────────────────────────────────
class GradientTextLabel(QLabel):
    """QLabel that paints its text with a vertical gradient derived from an accent
    color, plus a soft drop-shadow effect. Theme-aware — call set_accent() on
    dark/light toggle to re-sample stops."""

    def __init__(self, text="", family="Sans", size=18, weight=QFont.Weight.ExtraBold,
                 letter_spacing=4, parent=None):
        super().__init__(text, parent)
        self._accent = QColor("#3b82f6")
        self._family = family
        self._size = size
        self._weight = weight
        self._letter_spacing = letter_spacing
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(8)
        shadow.setOffset(0, 1)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(shadow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._refresh_size()

    def set_accent(self, color_hex):
        self._accent = QColor(color_hex)
        self.update()

    def set_family(self, family):
        self._family = family
        self._refresh_size()
        self.update()

    def _make_font(self):
        font = QFont(self._family)
        font.setPixelSize(self._size)
        font.setWeight(self._weight)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self._letter_spacing)
        return font

    def _refresh_size(self):
        # Use tight glyph bounds (no descent waste) for accurate visual sizing.
        font = self._make_font()
        path = QPainterPath()
        path.addText(QPointF(0, 0), font, self.text())
        br = path.boundingRect()
        # Width: glyph ink + trailing letter-spacing + a small right pad for the
        # shadow halo. No LEFT pad — the wordmark's left edge must sit at
        # widget x=0 so a sibling FlatBearingLabel below aligns to the same
        # gridline.
        w = int(br.width() + self._letter_spacing * max(0, len(self.text()) - 1) + 6)
        h = int(br.height() + 10)  # small vertical padding for shadow halo
        self.setFixedSize(w, h)

    @staticmethod
    def _shift_lightness(color, amt):
        h, s, l, a = color.getHslF()
        return QColor.fromHslF(h, s, max(0.0, min(1.0, l + amt)), a)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        font = self._make_font()
        path = QPainterPath()
        path.addText(QPointF(0, 0), font, self.text())
        br = path.boundingRect()
        # Vertically center the glyph bounds; horizontally, cancel the left
        # side bearing so the first ink pixel sits at widget x=0 — the
        # sibling FlatBearingLabel below uses the same trick to stay aligned.
        offset_y = (self.height() - br.height()) / 2.0 - br.top()
        p.translate(-br.left(), offset_y)
        grad = QLinearGradient(0, br.top(), 0, br.bottom())
        grad.setColorAt(0.0, self._shift_lightness(self._accent,  0.08))
        grad.setColorAt(1.0, self._shift_lightness(self._accent, -0.10))
        p.fillPath(path, QBrush(grad))


class FlatBearingLabel(QLabel):
    """Plain-text label that paints with the left side bearing cancelled, so
    it lines up flush with a GradientTextLabel above it. Used for the
    DOWNLOAD MANAGER subtitle in the sidebar."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._color = QColor("#94a3b8")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def setColor(self, color_hex):
        self._color = QColor(color_hex)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        path = QPainterPath()
        path.addText(QPointF(0, 0), self.font(), self.text())
        br = path.boundingRect()
        offset_y = (self.height() - br.height()) / 2.0 - br.top()
        p.translate(-br.left(), offset_y)
        p.fillPath(path, QBrush(self._color))


# ── File-list redesign delegates (LDM_file_list_v1/README.md) ────────────────
#
# Each row column gets its own painter so the table can render the card-style
# layout — accent bar, two-line filename with squircle icon, striped progress
# bar, mono numeric cells, status pill — without leaving QTableWidget land.
# A shared 25 fps timer drives the stripe and pulse animations.


class _FlBaseDelegate(QStyledItemDelegate):
    """Common helpers + shared animation timer used by every column delegate."""

    _shared_timer = None
    _shared_views = set()

    def __init__(self, parent=None, sans_family="IBM Plex Sans",
                 mono_family="IBM Plex Mono"):
        super().__init__(parent)
        self._sans = sans_family
        self._mono = mono_family
        self._start_anim(parent)

    @classmethod
    def _start_anim(cls, view):
        if view is None or not hasattr(view, "viewport"):
            return
        cls._shared_views.add(view)
        if cls._shared_timer is None:
            t = QTimer()
            t.timeout.connect(cls._tick)
            t.start(40)
            cls._shared_timer = t

    @classmethod
    def _tick(cls):
        dead = []
        for v in list(cls._shared_views):
            try:
                vp = v.viewport()
                if vp is None:
                    dead.append(v)
                    continue
                if cls._any_row_animating(v):
                    vp.update()
            except RuntimeError:
                dead.append(v)
        for v in dead:
            cls._shared_views.discard(v)

    @staticmethod
    def _any_row_animating(view):
        try:
            model = view.model()
        except Exception:
            return False
        if model is None:
            return False
        for r in range(model.rowCount()):
            s = model.index(r, 5).data(Qt.ItemDataRole.DisplayRole)
            if s == "Downloading":
                return True
        return False

    @staticmethod
    def _status_from(index):
        return index.siblingAtColumn(5).data(Qt.ItemDataRole.DisplayRole) or "Finished"

    @staticmethod
    def _pct_from(index):
        v = index.siblingAtColumn(1).data(Qt.ItemDataRole.UserRole + 1)
        try:
            return max(0, min(100, int(v)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _font(family, px, weight=QFont.Weight.Normal, letter_spacing=None):
        f = QFont(family)
        f.setPixelSize(px)
        f.setWeight(weight)
        if letter_spacing is not None:
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
        return f

    def _paint_cell_chrome(self, painter, option, draw_bottom_border=True):
        # Card-style row: white bg, soft blue tint when selected, hairline
        # bottom border that matches the body-row divider in the spec.
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#eff6ff"))
        else:
            painter.fillRect(option.rect, QColor("#ffffff"))
        if draw_bottom_border:
            painter.setPen(QPen(QColor("#f1f5f9"), 1))
            y = option.rect.bottom()
            painter.drawLine(option.rect.left(), y, option.rect.right(), y)


class FlNameDelegate(_FlBaseDelegate):
    """Column 0 — 28px squircle icon, filename, EXT · TOTAL_SIZE sub-meta,
    plus the row's left accent bar painted on the leading edge."""

    _fallbacks_cached = None

    @classmethod
    def _fallbacks(cls):
        if cls._fallbacks_cached is not None:
            return cls._fallbacks_cached
        try:
            WS = QFontDatabase.WritingSystem
            skip = {WS.Any, WS.Latin, WS.Symbol}
            seen, ordered = set(), []
            for f in QFontDatabase.families(WS.Bengali) or []:
                if 'Noto Sans Bengali UI' in f and f not in seen:
                    seen.add(f); ordered.append(f)
            for ws in WS:
                if ws in skip:
                    continue
                for f in QFontDatabase.families(ws) or []:
                    if f not in seen:
                        seen.add(f); ordered.append(f)
            cls._fallbacks_cached = ordered
        except Exception:
            cls._fallbacks_cached = []
        return cls._fallbacks_cached

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._paint_cell_chrome(painter, option)

        status = self._status_from(index)
        token = fl_status_token(status)

        # Left status accent bar — 3px wide, inset 8px top/bottom, hidden on Finished.
        if status != "Finished":
            bar_rect = QRectF(
                option.rect.left() + 0.0,
                option.rect.top() + 8.0,
                3.0,
                max(0.0, option.rect.height() - 16.0),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(token["accent"]))
            painter.drawRoundedRect(bar_rect, 2.0, 2.0)

        category = index.data(FL_ROLE_CATEGORY) or "Others"
        filename = (index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        total    = index.data(FL_ROLE_TOTAL) or ""

        # Icon at 28px.
        icon_size = 28
        icon_x = option.rect.left() + FL_ROW_LEFT_PAD
        icon_y = option.rect.top() + (option.rect.height() - icon_size) // 2
        pix = get_category_pixmap(category, icon_size)
        if pix is not None:
            painter.drawPixmap(icon_x, icon_y, pix)

        text_x = icon_x + icon_size + 11
        text_right = option.rect.right() - 8
        text_width = max(0, text_right - text_x)

        ext = ""
        if "." in filename:
            ext = filename.rsplit(".", 1)[-1].upper()
        sub_meta = " · ".join([p for p in (ext, str(total)) if p])

        # Layout the two text lines centred vertically within the row.
        primary_font = self._font(self._sans, 13, QFont.Weight.DemiBold)
        primary_font.setFamilies([self._sans] + self._fallbacks())
        secondary_font = self._font(self._mono, 10, QFont.Weight.Medium, letter_spacing=0.2)
        fm_p = QFontMetrics(primary_font)
        fm_s = QFontMetrics(secondary_font)

        line_gap = 1
        total_h = fm_p.height() + line_gap + fm_s.height()
        top = option.rect.top() + (option.rect.height() - total_h) // 2

        # Primary line — filename.
        painter.setFont(primary_font)
        painter.setPen(QColor("#0f172a"))
        elided = fm_p.elidedText(filename, Qt.TextElideMode.ElideRight, text_width)
        painter.drawText(text_x, top + fm_p.ascent(), elided)

        # Secondary line — EXT · TOTAL_SIZE.
        if sub_meta:
            painter.setFont(secondary_font)
            painter.setPen(QColor("#94a3b8"))
            sub_y = top + fm_p.height() + line_gap + fm_s.ascent()
            elided_sub = fm_s.elidedText(sub_meta, Qt.TextElideMode.ElideRight, text_width)
            painter.drawText(text_x, sub_y, elided_sub)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), FL_ROW_HEIGHT)


class FlProgressDelegate(_FlBaseDelegate):
    """Column 1 — striped/gradient/dashed progress bar + mono percent label."""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_cell_chrome(painter, option)

        status = self._status_from(index)
        token = fl_status_token(status)
        pct = self._pct_from(index)

        cell_left = option.rect.left() + 6
        cell_right = option.rect.right() - 12
        bar_w = max(0, cell_right - cell_left)
        bar_h = 6
        pct_font = self._font(self._mono, 10, QFont.Weight.DemiBold, letter_spacing=0.2)
        fm = QFontMetrics(pct_font)

        stack_h = bar_h + 4 + fm.height()
        bar_top = option.rect.top() + (option.rect.height() - stack_h) // 2
        bar_rect = QRectF(cell_left, bar_top, bar_w, bar_h)

        is_queued = (status == "Queued")
        is_error  = (token["key"] == "error")

        if is_queued:
            # Empty 6px box with 1px dashed #cbd5e1 border, no fill.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(QColor("#cbd5e1"), 1, Qt.PenStyle.DashLine)
            pen.setDashPattern([4, 3])
            painter.setPen(pen)
            painter.drawRoundedRect(bar_rect, 3.0, 3.0)
        else:
            # Track.
            track = QColor("#fee2e2") if is_error else QColor("#e2e8f0")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(track)
            painter.drawRoundedRect(bar_rect, 3.0, 3.0)

            # Fill.
            if pct > 0 and token["bar"] is not None:
                fill_w = bar_rect.width() * (pct / 100.0)
                fill_rect = QRectF(bar_rect.left(), bar_rect.top(), fill_w, bar_rect.height())
                grad = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
                grad.setColorAt(0.0, QColor(token["bar"][0]))
                grad.setColorAt(1.0, QColor(token["bar"][1]))
                painter.save()
                clip = QPainterPath()
                clip.addRoundedRect(bar_rect, 3.0, 3.0)
                painter.setClipPath(clip)
                if is_error:
                    painter.setOpacity(0.55)
                painter.setBrush(grad)
                painter.drawRect(fill_rect)

                # Inset highlight (1px white-ish line along the top edge).
                if not is_error and fill_w > 1:
                    painter.setOpacity(0.45)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(255, 255, 255, 115))
                    painter.drawRect(QRectF(fill_rect.left(), fill_rect.top(),
                                            fill_rect.width(), 1.0))
                    painter.setOpacity(1.0)

                # Animated diagonal stripes for active downloads.
                if status == "Downloading" and fill_w > 0:
                    offset = (time.time() / 1.2) * 24.0
                    painter.setOpacity(1.0)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(255, 255, 255, 64))
                    stripe_w = 6
                    spacing = 12
                    # Cover the full fill with 45° stripes, shifted by offset.
                    y0 = fill_rect.top() - bar_rect.height()
                    y1 = fill_rect.bottom() + bar_rect.height()
                    x_start = int(fill_rect.left() - bar_rect.height() - (offset % spacing) - spacing)
                    x_end = int(fill_rect.right() + bar_rect.height() + spacing)
                    for x in range(x_start, x_end, spacing):
                        poly = QPainterPath()
                        poly.moveTo(x, y1)
                        poly.lineTo(x + bar_rect.height(), y0)
                        poly.lineTo(x + bar_rect.height() + stripe_w, y0)
                        poly.lineTo(x + stripe_w, y1)
                        poly.closeSubpath()
                        painter.drawPath(poly)
                painter.restore()

        # Percent label.
        painter.setFont(pct_font)
        if status == "Finished":
            painter.setPen(QColor("#16a34a"))
        else:
            painter.setPen(QColor("#64748b"))
        pct_text = f"{pct}%"
        painter.drawText(int(cell_left),
                         int(bar_top + bar_h + 4 + fm.ascent()),
                         pct_text)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(180, FL_ROW_HEIGHT)


class FlDownloadedDelegate(_FlBaseDelegate):
    """Column 2 — `done` (bold, dark) ` / total` (muted), or just total when done."""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_cell_chrome(painter, option)

        text = (index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        status = self._status_from(index)
        font = self._font(self._mono, 11, QFont.Weight.Medium)
        fm = QFontMetrics(font)
        avail = option.rect.width() - 8
        y = option.rect.top() + (option.rect.height() + fm.ascent() - fm.descent()) // 2

        def _center_x(w):
            # Center content under the centered "DOWNLOADED" header, matching
            # the Status/Date columns.
            return option.rect.left() + (option.rect.width() - w) // 2

        if status == "Finished":
            # Spec: finished rows show only the total size, not "size / size".
            if " / " in text:
                a, b = text.split(" / ", 1)
                if a.strip() == b.strip():
                    text = a.strip()
            shown = fm.elidedText(text, Qt.TextElideMode.ElideRight, avail)
            painter.setFont(font)
            painter.setPen(QColor("#334155"))
            painter.drawText(_center_x(fm.horizontalAdvance(shown)), y, shown)
        else:
            # Try to split "done / total". Falls back to plain rendering.
            if " / " in text:
                done, total = text.split(" / ", 1)
                bold = self._font(self._mono, 11, QFont.Weight.DemiBold)
                fm_b = QFontMetrics(bold)
                rest = f" / {total}"
                group_w = fm_b.horizontalAdvance(done) + fm.horizontalAdvance(rest)
                x = _center_x(group_w)
                painter.setFont(bold)
                painter.setPen(QColor("#0f172a"))
                painter.drawText(x, y, done)
                painter.setFont(font)
                painter.setPen(QColor("#94a3b8"))
                painter.drawText(x + fm_b.horizontalAdvance(done), y, rest)
            else:
                shown = fm.elidedText(text, Qt.TextElideMode.ElideRight, avail)
                painter.setFont(font)
                painter.setPen(QColor("#334155"))
                painter.drawText(_center_x(fm.horizontalAdvance(shown)), y, shown)
        painter.restore()


class FlSpeedDelegate(_FlBaseDelegate):
    """Column 3 — mono. Active rows show ↓ green/bold; otherwise muted dash."""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_cell_chrome(painter, option)

        text = (index.data(Qt.ItemDataRole.DisplayRole) or "—").strip() or "—"
        status = self._status_from(index)
        active = (status == "Downloading") and text not in ("—", "")
        if active:
            font = self._font(self._mono, 11, QFont.Weight.Bold)
            painter.setPen(QColor("#16a34a"))
            shown = f"↓ {text}" if not text.startswith("↓") else text
        else:
            font = self._font(self._mono, 11, QFont.Weight.Medium)
            painter.setPen(QColor("#94a3b8"))
            shown = "—" if text in ("—", "") else text
        painter.setFont(font)
        fm = QFontMetrics(font)
        x = option.rect.left() + 4
        y = option.rect.top() + (option.rect.height() + fm.ascent() - fm.descent()) // 2
        painter.drawText(x, y, fm.elidedText(shown, Qt.TextElideMode.ElideRight,
                                              option.rect.width() - 8))
        painter.restore()


class FlEtaDelegate(_FlBaseDelegate):
    """Column 4 — mono ETA. Slate for active, muted dash otherwise."""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_cell_chrome(painter, option)

        text = (index.data(Qt.ItemDataRole.DisplayRole) or "—").strip() or "—"
        status = self._status_from(index)
        font = self._font(self._mono, 11, QFont.Weight.Medium)
        if status == "Downloading" and text != "—":
            painter.setPen(QColor("#475569"))
        else:
            painter.setPen(QColor("#94a3b8"))
            text = "—" if text in ("—", "") else text
        painter.setFont(font)
        fm = QFontMetrics(font)
        x = option.rect.left() + 4
        y = option.rect.top() + (option.rect.height() + fm.ascent() - fm.descent()) // 2
        painter.drawText(x, y, fm.elidedText(text, Qt.TextElideMode.ElideRight,
                                              option.rect.width() - 8))
        painter.restore()


class FlStatusDelegate(_FlBaseDelegate):
    """Column 5 — rounded pill with leading colored dot + status label.
    Active rows get a pulsing halo around the dot."""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_cell_chrome(painter, option)

        raw_status = (index.data(Qt.ItemDataRole.DisplayRole) or "Finished").strip()
        # Verbose error messages ("Error: ERROR: [generic] HTTP 503 …") would
        # blow out the pill — collapse them to the canonical "Error" token while
        # still resolving the right color tokens.
        if raw_status.lower().startswith("error"):
            status, label = "Error", "Error"
        else:
            status, label = raw_status, raw_status
        token = fl_status_token(status)

        font = self._font(self._sans, 11, QFont.Weight.Bold, letter_spacing=0.2)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(label)
        # Uniform pill width: size for the widest status label so every pill
        # matches regardless of text length.
        widest = max(
            fm.horizontalAdvance(s)
            for s in ("Downloading", "File Missing", "Finished", "Error",
                      "Cancelled", "Paused", "Queued")
        )

        pad_left, pad_right = 8, 9
        dot_d = 6
        gap = 6
        pill_h = max(fm.height() + 2, 18)
        pill_w = pad_left + dot_d + gap + widest + pad_right

        pill_x = option.rect.left() + (option.rect.width() - pill_w) / 2.0
        pill_y = option.rect.top() + (option.rect.height() - pill_h) // 2
        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)

        # Pill body.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(token["bg"]))
        painter.drawRoundedRect(pill_rect, pill_h / 2.0, pill_h / 2.0)

        # Center dot+label as a group inside the fixed-width pill.
        content_w = dot_d + gap + text_w
        content_x = pill_x + (pill_w - content_w) / 2.0
        dot_cx = content_x + dot_d / 2.0
        dot_cy = pill_y + pill_h / 2.0

        # Pulsing halo for active downloads.
        if status == "Downloading":
            phase = (time.time() / 1.6) % 1.0
            halo_r = (dot_d / 2.0) + (phase * 6.0)
            halo_alpha = int(140 * (1.0 - phase))
            painter.setBrush(QColor(token["dot"]))
            painter.setOpacity(halo_alpha / 255.0)
            painter.drawEllipse(QPointF(dot_cx, dot_cy), halo_r, halo_r)
            painter.setOpacity(1.0)

        # Dot.
        painter.setBrush(QColor(token["dot"]))
        painter.drawEllipse(QPointF(dot_cx, dot_cy), dot_d / 2.0, dot_d / 2.0)

        # Label.
        painter.setFont(font)
        painter.setPen(QColor(token["text"]))
        text_x = content_x + dot_d + gap
        text_y = pill_y + (pill_h + fm.ascent() - fm.descent()) // 2 - 1
        painter.drawText(int(text_x), int(text_y), label)
        painter.restore()


class FlDateDelegate(_FlBaseDelegate):
    """Column 6 — mono date string in muted slate."""

    @staticmethod
    def _humanize(text):
        # Convert app-stored "YYYY-MM-DD HH:MM" to "Today, HH:MM" / "Yesterday"
        # / "MMM DD" per the spec; leave other formats untouched.
        if not text:
            return ""
        try:
            import datetime as _dt
            parts = text.split(" ")
            d = _dt.datetime.strptime(parts[0], "%Y-%m-%d").date()
            today = _dt.date.today()
            delta = (today - d).days
            if delta == 0:
                return "Today"
            if delta == 1:
                return "Yesterday"
            if 0 <= delta < 365 and d.year == today.year:
                return d.strftime("%b %d").replace(" 0", " ")
            return d.strftime("%b %d, %Y")
        except Exception:
            return text

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_cell_chrome(painter, option)
        text = self._humanize((index.data(Qt.ItemDataRole.DisplayRole) or "").strip())
        font = self._font(self._mono, 11, QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor("#64748b"))
        fm = QFontMetrics(font)
        elided = fm.elidedText(text, Qt.TextElideMode.ElideRight,
                               option.rect.width() - 8)
        text_w = fm.horizontalAdvance(elided)
        x = option.rect.left() + (option.rect.width() - text_w) // 2
        y = option.rect.top() + (option.rect.height() + fm.ascent() - fm.descent()) // 2
        painter.drawText(x, y, elided)
        painter.restore()


# Back-compat aliases — older code references the original class names.
class NumericFontDelegate(_FlBaseDelegate):
    def __init__(self, family="Sans", weight=QFont.Weight.Medium, parent=None):
        super().__init__(parent)
        self._family = family
        self._weight = weight

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        f = QFont(option.font)
        f.setFamily(self._family)
        f.setWeight(self._weight)
        option.font = f


# Legacy filename delegate — superseded by FlNameDelegate but kept so any
# stray reference still resolves.
class FilenameFontDelegate(FlNameDelegate):
    pass


# Legacy progress delegate — superseded by FlProgressDelegate.
class ProgressDelegate(FlProgressDelegate):
    pass


# ── Combo hover delegate (Linux Qt6 workaround) ─────────────────────────────
class ComboHoverDelegate(QStyledItemDelegate):
    """Paints hover/selection highlight directly, bypassing platform style."""
    def __init__(self, accent_color="#2f81f7", parent=None):
        super().__init__(parent)
        self._accent = QColor(accent_color)

    def paint(self, painter, option, index):
        painter.save()
        is_hover = option.state & QStyle.StateFlag.State_MouseOver
        is_selected = option.state & QStyle.StateFlag.State_Selected
        if is_hover or is_selected:
            painter.fillRect(option.rect, self._accent)
            painter.setPen(QColor("#ffffff"))
        else:
            painter.setPen(option.palette.color(QPalette.ColorRole.Text))
        text = index.data(Qt.ItemDataRole.DisplayRole)
        text_rect = option.rect.adjusted(12, 0, -12, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        sh.setHeight(max(sh.height(), 32))
        return sh


# ── Fetch formats thread ─────────────────────────────────────────────────────
class FetchFormatsThread(QThread):
    formats_ready = pyqtSignal(str)
    info_ready    = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            print(f"[YT-FETCH] URL: {self.url}", flush=True)
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'http_headers': {'User-Agent': HEADERS['User-Agent']},
                'cookiesfrombrowser': ('firefox', get_firefox_profile()),
            }
            print("[YT-FETCH] Calling extract_info...", flush=True)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if info is None:
                    self.error.emit("Could not fetch video info")
                    return
                title = info.get('title', 'video')
                print(f"[YT-FETCH] Success: {title}", flush=True)
                duration = info.get('duration') or 0
                formats = info.get('formats') or []

                def _fmt_bytes(f):
                    sz = f.get('filesize') or f.get('filesize_approx')
                    if sz:
                        return int(sz)
                    tbr = f.get('tbr')  # kbps (total bitrate)
                    if tbr and duration:
                        return int(tbr * 1000 * duration / 8)
                    return None

                # Best audio (we always merge an audio track for non-progressive video)
                audio_only = [
                    f for f in formats
                    if (f.get('vcodec') in (None, 'none'))
                    and (f.get('acodec') and f.get('acodec') != 'none')
                ]
                audio_bytes = 0
                audio_kbps  = 0
                if audio_only:
                    best_aud = max(audio_only, key=lambda f: f.get('abr') or 0)
                    audio_bytes = _fmt_bytes(best_aud) or 0
                    abr = best_aud.get('abr') or best_aud.get('tbr')
                    if abr:
                        audio_kbps = int(round(abr))
                    elif audio_bytes and duration:
                        audio_kbps = int(round(audio_bytes * 8 / duration / 1000))

                # Per-height best video format size
                heights = set()
                size_by_height = {}
                video_fmts = [
                    f for f in formats
                    if f.get('vcodec') and f.get('vcodec') != 'none'
                ]
                grouped = {}
                for f in video_fmts:
                    h = f.get('height')
                    if isinstance(h, int) and h > 0:
                        heights.add(h)
                        grouped.setdefault(h, []).append(f)
                for h, fmts in grouped.items():
                    best = max(fmts, key=lambda f: f.get('tbr') or 0)
                    vsize = _fmt_bytes(best)
                    if not vsize:
                        continue
                    is_progressive = (
                        best.get('acodec') and best.get('acodec') != 'none'
                    )
                    size_by_height[h] = (
                        vsize if is_progressive else vsize + audio_bytes
                    )

                payload = {
                    'title':         title,
                    'channel':       info.get('uploader') or info.get('channel') or '',
                    'duration':      duration,
                    'view_count':    info.get('view_count') or 0,
                    'upload_date':   info.get('upload_date') or '',
                    'thumbnail':     info.get('thumbnail') or '',
                    'video_id':      info.get('id') or '',
                    'heights':       sorted(heights, reverse=True),
                    'size_by_height': size_by_height,
                    'audio_bytes':   audio_bytes,
                    'audio_kbps':    audio_kbps,
                    'has_subs':      bool(info.get('subtitles') or info.get('automatic_captions')),
                    'categories':    info.get('categories') or [],
                }
                self.info_ready.emit(payload)
                self.formats_ready.emit(title)
        except Exception as e:
            print(f"[YT-FETCH ERROR] {e}", flush=True)
            self.error.emit(str(e)[:200])


# ── YouTube download thread ──────────────────────────────────────────────────
class _YTCancelled(Exception):
    """Raised inside the yt-dlp progress hook when the user clicks Stop.
    Caught in ``YouTubeDownloadThread.run`` and reported as a clean
    cancellation instead of an error."""
    pass


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
            self.ydl_opts['noplaylist'] = True
            self.ydl_opts['cookiesfrombrowser'] = ('firefox', get_firefox_profile())
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if info is None:
                    raise Exception("Could not download video")
            self.finished.emit("Finished")
        except _YTCancelled:
            self.finished.emit("Cancelled")
        except Exception as e:
            # yt-dlp wraps the cancellation in its own DownloadError; detect it
            # by checking self.running rather than the exception type.
            if not self.running:
                self.finished.emit("Cancelled")
            else:
                self.finished.emit(f"Error: {str(e)[:80]}")

    def hook(self, d):
        if not self.running:
            raise _YTCancelled()
        ansi_escape = re.compile(r'\x1b\[[0-9;]*m|\[[0-9;]*m')
        def clean(s): return ansi_escape.sub('', s).strip()
        if d['status'] == 'downloading':
            p = clean(d.get('_percent_str', '0%')).replace('%', '').strip()
            try:
                self.progress.emit(int(float(p)))
            except Exception:
                pass
            speed_str = clean(d.get('_speed_str', '—'))
            self.speed.emit(speed_str)
            dl = d.get('downloaded_bytes') or 0
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            if total:
                self.size_info.emit(f"{format_size(dl)} / {format_size(total)}")
                eta_secs = d.get('eta') or 0
                self.eta.emit(format_eta(eta_secs))
            else:
                self.size_info.emit(format_size(dl))
                self.eta.emit("—")
            self.log.emit(f"Downloading... {p}% at {speed_str}")
        elif d['status'] == 'finished':
            self.progress.emit(100)
            self.eta.emit("—")
            self.log.emit("Processing / merging...")


# ── Dialog style ─────────────────────────────────────────────────────────────
def make_dialog_style(dark=True):
    if dark:
        bg        = "#161b22"
        surface   = "#0d1117"
        border    = "#30363d"
        text      = "#e6edf3"
        muted     = "#8b949e"
        accent    = "#2f81f7"
        sel_bg    = "#1c2b3a"
        sel_text  = "#58a6ff"
        prog_track = "#21262d"
        prog_fill  = "#3fb950"
        input_bg  = "#010409"
        input_focus = "#0d1117"
    else:
        bg        = "#ffffff"
        surface   = "#f6f8fa"
        border    = "#d0d7de"
        text      = "#1f2328"
        muted     = "#656d76"
        accent    = "#0969da"
        sel_bg    = "#ddf4ff"
        sel_text  = "#0969da"
        prog_track = "#e5e7eb"
        prog_fill  = "#1a7f37"
        input_bg  = "#ffffff"
        input_focus = "#ffffff"

    return f"""
    QDialog {{
        background-color: {bg};
        color: {text};
    }}
    QDialog QWidget {{
        background-color: {bg};
        color: {text};
    }}
    QLabel {{
        color: {text};
        font-size: 13px;
        background-color: transparent;
    }}
    QLineEdit {{
        background-color: {input_bg};
        color: {text};
        border: 1px solid {border};
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 13px;
    }}
    QLineEdit:focus {{
        border: 1px solid {accent};
        background-color: {input_focus};
    }}
    QPushButton {{
        border-radius: 8px;
        font-size: 13px;
        font-weight: 600;
        padding: 8px 18px;
        border: none;
    }}
    QComboBox {{
        background-color: {input_bg};
        color: {text};
        border: 1px solid {border};
        border-radius: 8px;
        padding: 7px 12px;
        font-size: 13px;
        min-height: 34px;
    }}
    QComboBox::drop-down {{ border: none; }}
    QComboBox QAbstractItemView {{
        background-color: {bg};
        color: {text};
        border: 1px solid {border};
        outline: none;
        selection-background-color: {accent};
        selection-color: #ffffff;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 6px 12px;
        min-height: 28px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: {accent};
        color: #ffffff;
    }}
    QGroupBox {{
        border: 1px solid {border};
        border-radius: 8px;
        margin-top: 18px;
        padding: 12px 10px 8px 10px;
        font-size: 12px;
        color: {muted};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 1px;
        top: -1px;
        padding: 0 6px;
        background-color: {bg};
    }}
    QRadioButton {{ color: {text}; font-size: 13px; spacing: 6px; }}
    QTextEdit {{
        background-color: {surface};
        color: {muted};
        border: 1px solid {border};
        border-radius: 8px;
        font-size: 12px;
        font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
        padding: 8px;
    }}
    QProgressBar {{
        background-color: {prog_track};
        border-radius: 5px;
        height: 8px;
        text-align: center;
        font-size: 11px;
        color: {text};
        border: none;
    }}
    QProgressBar::chunk {{
        background-color: {prog_fill};
        border-radius: 5px;
    }}
    QScrollBar:vertical {{
        background: transparent; width: 6px; margin: 4px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {border}; border-radius: 3px; min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px; border: none; background: none;
    }}
"""

# Legacy alias — used by any code that still references DIALOG_STYLE directly
DIALOG_STYLE = make_dialog_style(dark=True)


def make_close_btn_style(dark=True):
    if dark:
        return (
            "QPushButton { background-color: #21262d; color: #e6edf3; border: 1px solid #30363d; }"
            "QPushButton:hover { background-color: #30363d; }"
        )
    return (
        "QPushButton { background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }"
        "QPushButton:hover { background-color: #e2e8f0; }"
    )


# ── Main download thread ─────────────────────────────────────────────────────

# ── Redesigned downloader-dialog shared infrastructure ──────────────────────
# DIALOG_THEMES are scoped to the three redesigned downloader dialogs (Core,
# Stream, YouTube). They intentionally stay separate from the main app's THEMES
# so the dialogs can evolve their visual language without touching the rest.
DIALOG_THEMES = {
    "light": {
        "bg":        "#f1f5f9",
        "surface":   "#ffffff",
        "surface2":  "#f8fafc",
        "title_bg":  "#eef2f5",
        "card":      "#f8fafc",
        "input_bg":  "#ffffff",
        "border":    "#e2e8f0",
        "text":      "#0f172a",
        "muted":     "#64748b",
        "subtle":    "#94a3b8",
        "close_btn": "#e2e8f0",
        "bar_track": "#e2e8f0",
    },
    "dark": {
        "bg":        "#020617",
        "surface":   "#0f172a",
        "surface2":  "#020617",
        "title_bg":  "#0a121f",
        # Cards are LIGHTER than the surface in dark mode, so they pop forward.
        "card":      "#1e293b",
        "input_bg":  "#1e293b",
        "border":    "#334155",
        "text":      "#f1f5f9",
        "muted":     "#94a3b8",
        "subtle":    "#64748b",
        "close_btn": "#334155",
        "bar_track": "#0b1220",
    },
}

PLEX_SANS = '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif'
PLEX_MONO = '"IBM Plex Mono", "SF Mono", "DejaVu Sans Mono", Menlo, monospace'


def _svg_rgba_to_qt(path):
    """Rewrite rgba() colors in an SVG to rgb() + matching *-opacity attrs so
    Qt's QSvgRenderer (which can't parse rgba()) renders them correctly.
    Returns a QByteArray ready to pass to QSvgRenderer."""
    from PyQt6.QtCore import QByteArray
    with open(path, "rb") as f:
        svg = f.read().decode("utf-8")
    rgba_re = re.compile(
        r'\b(fill|stroke|stop-color)\s*=\s*"\s*rgba\(\s*'
        r'(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)\s*"'
    )

    def repl(m):
        attr, r, g, b, a = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        opacity_attr = "stop-opacity" if attr == "stop-color" else f"{attr}-opacity"
        return f'{attr}="rgb({r},{g},{b})" {opacity_attr}="{a}"'

    return QByteArray(rgba_re.sub(repl, svg).encode("utf-8"))


# ── Inline SVG tile glyphs (replace OS-dependent emoji in dialog tiles) ──────
# Each SVG uses `currentColor` placeholders that get substituted with the
# active tone color at render time.  Kept tiny so QSvgRenderer can parse them
# without any external dependency.
_TILE_SVG_LINK = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2.2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0 -5.7 -5.7l-1.2 1.2"/>'
    '<path d="M14 10a4 4 0 0 0 -5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.2 -1.2"/>'
    '</svg>'
)
_TILE_SVG_FOLDER = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2.0" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2v9a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2z"/>'
    '</svg>'
)
_TILE_SVG_CATEGORY = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2.0" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="3.5"  y="3.5"  width="7" height="7" rx="1.6"/>'
    '<rect x="13.5" y="3.5"  width="7" height="7" rx="1.6"/>'
    '<rect x="3.5"  y="13.5" width="7" height="7" rx="1.6"/>'
    '<rect x="13.5" y="13.5" width="7" height="7" rx="1.6"/>'
    '</svg>'
)
_TILE_SVG_CHEVRON_DOWN = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2.6" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="6 9 12 15 18 9"/>'
    '</svg>'
)
_TILE_SVG_HDD = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round">'
    # Trapezoid roof + chassis as one continuous outline.
    '<path d="M21 13 L17.6 7.1 C17.2 6.4 16.5 6 15.7 6 H8.3 '
    'C7.5 6 6.8 6.4 6.4 7.1 L3 13 V17 C3 18.1 3.9 19 5 19 '
    'H19 C20.1 19 21 18.1 21 17 Z"/>'
    # Shelf where the sloped roof meets the chassis.
    '<line x1="3" y1="13" x2="21" y2="13"/>'
    # Two LED dots on the chassis (filled, no stroke).
    '<circle cx="7" cy="16" r="0.9" fill="currentColor" stroke="none"/>'
    '<circle cx="10" cy="16" r="0.9" fill="currentColor" stroke="none"/>'
    '</svg>'
)


def _render_svg_str_pixmap(svg_str, color_hex, size=18):
    """Render an inline SVG string into a transparent QPixmap, substituting
    ``currentColor`` placeholders with ``color_hex`` first. Used by dialog
    tiles so we don't depend on the user's emoji font."""
    from PyQt6.QtCore import QByteArray
    from PyQt6.QtSvg import QSvgRenderer
    svg = svg_str.replace("currentColor", color_hex)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    render_size = max(size * 4, 96)
    pix = QPixmap(render_size, render_size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(p)
    p.end()
    return pix.scaled(size, size,
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def _make_glyph_tile(svg_str, tone_color, dark, size=28, glyph_size=18):
    """Build a small rounded tile QLabel with a tinted SVG glyph centered
    inside. Used as the leading icon for URL / folder / category fields."""
    tile = QLabel()
    tile.setFixedSize(size, size)
    r, g, b = int(tone_color[1:3], 16), int(tone_color[3:5], 16), int(tone_color[5:7], 16)
    bg_alpha = 0.20 if dark else 0.12
    tile.setStyleSheet(
        f"background: rgba({r},{g},{b},{bg_alpha}); border-radius: 8px;"
    )
    tile.setPixmap(_render_svg_str_pixmap(svg_str, tone_color, size=glyph_size))
    tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return tile


def _render_svg_pixmap(icon_path, size):
    """Render an SVG file to a transparent QPixmap at the requested square size.
    Uses 4× super-sampling for crisp edges at typical UI sizes."""
    from PyQt6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(_svg_rgba_to_qt(icon_path))
    render_size = max(size * 4, 192)
    pix = QPixmap(render_size, render_size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(p)
    p.end()
    return pix.scaled(size, size,
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


class DownloaderDialogBase(QDialog):
    """Frameless, draggable chrome shared by the Core / Stream / YouTube
    downloader dialogs. Subclasses fill ``self.body`` with their content and
    set the footer via ``self._set_footer(widgets)``.
    """

    def __init__(self, parent=None, dark=False, window_title="LDM Downloader"):
        super().__init__(parent)
        self.dark = dark
        self.theme = DIALOG_THEMES["dark" if dark else "light"]
        self.setWindowTitle(window_title)
        # QDialog hides min/max by default — opt into the full system menu so
        # the OS title bar shows Minimize / Maximize / Close.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self._build_chrome()

    def _build_chrome(self):
        t = self.theme

        self.setStyleSheet(
            f"QDialog {{ background-color: {t['surface']}; }}"
        )

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Body region — subclasses populate this via body_layout.
        self.body = QWidget()
        self.body.setStyleSheet(f"background: {t['surface']};")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        outer_layout.addWidget(self.body, 1)

        # Footer — populated by subclasses via footer_layout.
        self.footer = QWidget()
        self.footer.setStyleSheet(
            f"background: {t['surface2']}; "
            f"border-top: 1px solid {t['border']};"
        )
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(22, 14, 22, 14)
        self.footer_layout.setSpacing(10)
        outer_layout.addWidget(self.footer)


def _make_hero_band(parent, dark, icon_path, title, subtitle="", chip_label="",
                    accent_color="#3b82f6", accent_soft="rgba(0,0,0,0)"):
    """Engine-coloured band at the top of each downloader dialog: 56px squircle
    icon on the left, title (+ optional chip + subtitle) on the right, tinted
    gradient bg. When both ``subtitle`` and ``chip_label`` are empty, the title
    is vertically centred against the icon for a clean header-only look."""
    t = DIALOG_THEMES["dark" if dark else "light"]
    band = QWidget(parent)
    band.setStyleSheet(f"""
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {accent_soft}, stop:0.75 transparent);
        border-bottom: 1px solid {t['border']};
    """)
    layout = QHBoxLayout(band)
    layout.setContentsMargins(22, 18, 22, 18)
    layout.setSpacing(16)

    icon_lbl = QLabel()
    icon_lbl.setFixedSize(56, 56)
    icon_lbl.setStyleSheet("background: transparent;")
    if icon_path and os.path.exists(icon_path):
        icon_lbl.setPixmap(_render_svg_pixmap(icon_path, 56))
    layout.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"font-family: {PLEX_SANS}; font-size: 19px; font-weight: 800; "
        f"color: {t['text']}; letter-spacing: -0.2px; background: transparent;"
    )

    if not subtitle and not chip_label:
        # Title-only header — center it vertically alongside the icon.
        layout.addWidget(title_lbl, 1, Qt.AlignmentFlag.AlignVCenter)
        return band

    text_col = QVBoxLayout()
    text_col.setSpacing(3)

    header_row = QHBoxLayout()
    header_row.setSpacing(10)
    header_row.addWidget(title_lbl)

    if chip_label:
        chip = QLabel(chip_label)
        chip.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 0.8px; padding: 3px 8px; border-radius: 10px; "
            f"background: rgba(148,163,184,0.18); color: {accent_color};"
        )
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(chip)
    header_row.addStretch()
    text_col.addLayout(header_row)

    if subtitle:
        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 12px; color: {t['muted']}; "
            f"background: transparent;"
        )
        sub_lbl.setWordWrap(True)
        text_col.addWidget(sub_lbl)

    layout.addLayout(text_col, 1)
    return band


class StripedProgressBar(QWidget):
    """Thick progress bar with a diagonal-stripe overlay.

    Replaces QProgressBar so we can: (a) guarantee the fill renders even at
    very small percentages, (b) draw the slanted highlight pattern that the
    design handoff calls for, and (c) keep the corners crisp via clipping
    instead of relying on QSS border-radius math.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._color_a = QColor("#22c55e")
        self._color_b = QColor("#16a34a")
        self._track   = QColor("#e2e8f0")
        self._border  = QColor("#cbd5e1")
        self._stripe  = QColor(255, 255, 255, 70)
        self.setFixedHeight(14)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_colors(self, a, b, track, border, stripe_alpha=70):
        self._color_a = QColor(a)
        self._color_b = QColor(b)
        self._track   = QColor(track)
        self._border  = QColor(border)
        self._stripe  = QColor(255, 255, 255, stripe_alpha)
        self.update()

    def setValue(self, pct):
        self._value = max(0, min(100, int(pct)))
        self.update()

    def value(self):
        return self._value

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rf = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rf.height() / 2.0

        # Track
        track_path = QPainterPath()
        track_path.addRoundedRect(rf, radius, radius)
        p.setClipPath(track_path)
        p.fillRect(rf, self._track)

        # Fill
        fw = rf.width() * (self._value / 100.0)
        if fw > 0.5:
            fill = QRectF(rf.left(), rf.top(), fw, rf.height())
            grad = QLinearGradient(0, rf.top(), 0, rf.bottom())
            grad.setColorAt(0, self._color_a)
            grad.setColorAt(1, self._color_b)
            p.fillRect(fill, grad)

            # Diagonal stripes inside the fill
            p.save()
            p.setClipRect(fill)
            p.setPen(QPen(self._stripe, 6))
            step = 14
            h = rf.height()
            x = rf.left() - h
            end = rf.left() + fw + h
            while x < end:
                p.drawLine(QPointF(x, rf.bottom()),
                           QPointF(x + h, rf.top()))
                x += step
            p.restore()

        # Border (drawn on top so it stays crisp at any fill level)
        p.setClipping(False)
        p.setPen(QPen(self._border, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rf, radius, radius)
        p.end()


class ProgressSection(QWidget):
    """Shared progress card at the bottom of every downloader dialog.

    States:
      - idle:        0% with the bar shown but flat
      - downloading: green bar, percentage + size + speed + ETA
      - complete:    blue bar, "✓ Complete" label, speed/ETA hidden
      - error:       red bar with an error message in place of size

    Sizes are flexible — callers pass either a human-readable string via
    ``set_size_text`` or numeric (downloaded, total) via ``update_progress``.
    """

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self.dark = dark
        self.theme = DIALOG_THEMES["dark" if dark else "light"]
        self._state = "idle"
        self._build_ui()
        # Ensure the parent layout can't squish us below the room needed for
        # 22px-bold pct label + bar + 12px speed/eta row + margins + spacing.
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Minimum)

    def _build_ui(self):
        t = self.theme
        # Plain strip (no card chrome) so the bar's edges line up with the
        # controls above it in the dialog body.
        self.setStyleSheet("background: transparent;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 6)
        outer.setSpacing(8)

        top = QHBoxLayout()
        # 3px left inset on the text row only (bar stays flush) — guards
        # against bold-italic glyph negative LSB clipping the leading digit.
        top.setContentsMargins(3, 0, 0, 0)
        top.setSpacing(8)

        self.pct_lbl = QLabel("0%")
        _pct_font = QFont("IBM Plex Sans")
        _pct_font.setPixelSize(22)
        _pct_font.setWeight(QFont.Weight.Bold)
        self.pct_lbl.setFont(_pct_font)
        self.pct_lbl.setStyleSheet(
            f"color: {t['text']}; background: transparent;"
        )
        # Force the full 22px-bold line box. Parent's QVBoxLayout was
        # squishing the row to 15px, hiding the glyphs under the bar.
        _fm = self.pct_lbl.fontMetrics()
        self.pct_lbl.setFixedHeight(_fm.height() + 4)
        top.addWidget(self.pct_lbl)

        self.label_lbl = QLabel("ready")
        self.label_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 12px; color: {t['muted']}; "
            f"background: transparent;"
        )
        top.addWidget(self.label_lbl)
        top.addStretch()

        self.size_lbl = QLabel("")
        self.size_lbl.setStyleSheet(
            f"font-family: {PLEX_MONO}; font-size: 12px; color: {t['muted']}; "
            f"background: transparent;"
        )
        top.addWidget(self.size_lbl)
        outer.addLayout(top)

        self.bar = StripedProgressBar()
        self.bar.setValue(0)
        outer.addWidget(self.bar)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        self.speed_lbl = QLabel("")
        self.eta_lbl = QLabel("")
        for lbl in (self.speed_lbl, self.eta_lbl):
            lbl.setStyleSheet(
                f"font-family: {PLEX_MONO}; font-size: 11.5px; color: {t['muted']}; "
                f"background: transparent;"
            )
        bottom.addWidget(self.speed_lbl)
        bottom.addStretch()
        bottom.addWidget(self.eta_lbl)
        outer.addLayout(bottom)

        self._apply_bar_style("idle")

    def _apply_bar_style(self, state):
        t = self.theme
        if state == "error":
            grad_from, grad_to, border = "#ef4444", "#b91c1c", "#dc2626"
        elif state in ("downloading", "complete"):
            grad_from, grad_to, border = "#22c55e", "#16a34a", t['border']
        else:  # idle
            grad_from, grad_to, border = t['bar_track'], t['bar_track'], t['border']
        self.bar.set_colors(grad_from, grad_to, t['bar_track'], border)

    def set_pct(self, pct):
        pct = max(0, min(100, int(pct)))
        self.bar.setValue(pct)
        self.pct_lbl.setText(f"{pct}%")
        if pct >= 100 and self._state != "complete":
            self.mark_complete()
        elif 0 < pct < 100 and self._state not in ("downloading", "error"):
            self.mark_active()

    def set_size_text(self, text):
        self.size_lbl.setText(text or "")

    def set_speed_text(self, text):
        self.speed_lbl.setText(f"\u2193 {text}" if text else "")

    def set_eta_text(self, text):
        self.eta_lbl.setText(f"{text} remaining" if text else "")

    def mark_idle(self):
        self._state = "idle"
        self._apply_bar_style("idle")
        self.label_lbl.setText("ready")
        self.label_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 12px; color: {self.theme['muted']}; "
            f"background: transparent;"
        )
        self.speed_lbl.show(); self.eta_lbl.show()

    def mark_active(self):
        self._state = "downloading"
        self._apply_bar_style("downloading")
        self.label_lbl.setText("downloaded")
        self.label_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 12px; color: {self.theme['muted']}; "
            f"background: transparent;"
        )
        self.speed_lbl.show(); self.eta_lbl.show()

    def mark_complete(self):
        self._state = "complete"
        self._apply_bar_style("complete")
        self.pct_lbl.setText("100%")
        self.bar.setValue(100)
        self.label_lbl.setText("Complete")
        self.label_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 12px; color: #16a34a; "
            f"font-weight: 700; background: transparent;"
        )
        self.speed_lbl.hide(); self.eta_lbl.hide()

    def mark_error(self, msg=""):
        self._state = "error"
        self._apply_bar_style("error")
        self.label_lbl.setText(msg or "Error")
        self.label_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 12px; color: #dc2626; "
            f"font-weight: 700; background: transparent;"
        )
        self.speed_lbl.hide(); self.eta_lbl.hide()


def _dialog_btn_qss(theme, kind="secondary"):
    """Return a QSS string for one of the five primary button variants. Apply
    with btn.setStyleSheet(_dialog_btn_qss(self.theme, 'primaryGreen'))."""
    t = theme
    base = (
        f"QPushButton {{"
        f" padding: 9px 18px; border-radius: 10px;"
        f" font-family: {PLEX_SANS}; font-size: 13px; font-weight: 600;"
        f" border: none; outline: none;"
        f"}}"
    )
    variants = {
        "secondary":
            f" QPushButton {{ background: {t['surface']}; color: {t['text']};"
            f"   border: 1px solid {t['border']}; }}"
            f" QPushButton:hover {{ background: {t['card']}; }}"
            f" QPushButton:disabled {{ color: {t['subtle']}; background: {t['surface2']}; }}",
        "primaryGreen":
            " QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 #22c55e, stop:1 #16a34a); color: white; }"
            " QPushButton:hover { background: #16a34a; }"
            " QPushButton:disabled { background: #94a3b8; color: #f1f5f9; }",
        "primaryRed":
            " QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 #ef4444, stop:1 #dc2626); color: white; }"
            " QPushButton:hover { background: #dc2626; }"
            " QPushButton:disabled { background: #94a3b8; color: #f1f5f9; }",
        "primaryViolet":
            " QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 #8b5cf6, stop:1 #6d28d9); color: white; }"
            " QPushButton:hover { background: #6d28d9; }"
            " QPushButton:disabled { background: #94a3b8; color: #f1f5f9; }",
        "primaryBlue":
            " QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 #3b82f6, stop:1 #1d4ed8); color: white; }"
            " QPushButton:hover { background: #1d4ed8; }"
            " QPushButton:disabled { background: #94a3b8; color: #f1f5f9; }",
        "destructive":
            " QPushButton { background: rgba(239,68,68,0.08); color: #dc2626;"
            "   border: 1px solid rgba(239,68,68,0.30); }"
            " QPushButton:hover { background: rgba(239,68,68,0.16); }",
    }
    return base + variants.get(kind, variants["secondary"])


def _dialog_combo_inline_qss(theme, accent="#3b82f6", hide_arrow=False):
    """Style for a QComboBox sitting inside a tile-styled wrapper (no border
    of its own, transparent background). When ``hide_arrow`` is True the
    native chevron is fully suppressed so the wrapper can draw its own."""
    t = theme
    arrow_block = (
        " QComboBox::drop-down { width: 0; border: none; background: transparent; }"
        " QComboBox::down-arrow { image: none; width: 0; height: 0; }"
        if hide_arrow else
        f" QComboBox::drop-down {{"
        f"  subcontrol-origin: padding; subcontrol-position: center right;"
        f"  width: 22px; border: none; background: transparent;"
        f" }}"
        f" QComboBox::down-arrow {{"
        f"  image: none; width: 0; height: 0;"
        f"  border-left: 4px solid transparent; border-right: 4px solid transparent;"
        f"  border-top: 5px solid {accent}; margin-right: 8px;"
        f" }}"
    )
    return (
        f"QComboBox {{"
        f"  background: transparent; border: none; color: {t['text']};"
        f"  padding: 6px 4px 6px 4px; font-family: {PLEX_SANS}; font-size: 13.5px;"
        f"}}"
        f" QComboBox:hover {{ color: {t['text']}; }}"
        + arrow_block
    )


def _style_combo_popup(combo, theme, accent):
    """Style the QComboBox popup so hover/selection highlights work reliably.
    Sets stylesheet on the *view* directly (Qt's QStyleSheetStyle sometimes
    skips item :hover when set via the combo's parent stylesheet) and forces
    mouse-tracking + a vanilla QStyledItemDelegate so QSS wins over the
    native item painter."""
    t = theme
    r, g, b = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
    hover_bg = f"rgba({r},{g},{b},0.12)"
    sel_bg   = f"rgba({r},{g},{b},0.20)"
    view = combo.view()
    view.setMouseTracking(True)
    view.setCursor(Qt.CursorShape.PointingHandCursor)
    view.setSpacing(2)
    # A plain QStyledItemDelegate forces QSS to take effect on item rendering
    # (without this, Qt's QComboBoxDelegate uses native styling on some
    # platforms and ignores :hover / :selected backgrounds).
    view.setItemDelegate(QStyledItemDelegate(view))
    view.setStyleSheet(
        f"QAbstractItemView, QListView {{"
        f"  background: {t['surface']}; color: {t['text']};"
        f"  border: 1px solid {t['border']}; border-radius: 10px;"
        f"  padding: 6px; outline: none;"
        f"  selection-background-color: {sel_bg}; selection-color: {accent};"
        f"  font-family: {PLEX_SANS}; font-size: 13.5px;"
        f"}}"
        f" QAbstractItemView::item, QListView::item {{"
        f"  min-height: 30px; padding: 6px 10px; border-radius: 6px;"
        f"  color: {t['text']}; background: transparent;"
        f"}}"
        f" QAbstractItemView::item:hover, QListView::item:hover {{"
        f"  background: {hover_bg}; color: {t['text']};"
        f"}}"
        f" QAbstractItemView::item:selected, QListView::item:selected {{"
        f"  background: {sel_bg}; color: {accent}; font-weight: 600;"
        f"}}"
    )
    # The popup window itself wraps the view in a QFrame container ("PopupFrame"
    # on most Qt builds). Without explicit styling, that frame paints with the
    # default window palette — visible as black/dark bars above and below the
    # rounded view. Paint it to match the surface and drop its border so only
    # the inner QListView's rounded rect shows.
    container = view.parent()
    if container is not None:
        container.setStyleSheet(
            f"background: {t['surface']}; border: 1px solid {t['border']}; "
            f"border-radius: 10px;"
        )


def _dialog_input_qss(theme):
    t = theme
    return (
        f"QLineEdit, QComboBox {{"
        f" background: {t['input_bg']}; color: {t['text']};"
        f" border: 1px solid {t['border']}; border-radius: 10px;"
        f" padding: 10px 12px; font-family: {PLEX_SANS}; font-size: 13.5px;"
        f"}}"
        f" QLineEdit:focus, QComboBox:focus {{"
        f" border: 1px solid #3b82f6;"
        f"}}"
        f" QLineEdit:read-only {{ color: {t['text']}; }}"
        f" QComboBox::drop-down {{ border: none; width: 22px; }}"
        f" QComboBox::down-arrow {{ image: none; width: 0; height: 0;"
        f"   border-left: 4px solid transparent; border-right: 4px solid transparent;"
        f"   border-top: 5px solid {t['muted']}; margin-right: 8px; }}"
        f" QComboBox QAbstractItemView {{"
        f"   background: {t['surface']}; color: {t['text']};"
        f"   border: 1px solid {t['border']}; selection-background-color: rgba(59,130,246,0.16);"
        f"   selection-color: {t['text']}; padding: 4px; outline: none;"
        f" }}"
    )


# ── Stream dialog ─────────────────────────────────────────────────────────────
class StreamDialog(DownloaderDialogBase):
    download_started  = pyqtSignal(str, str, str)
    download_progress = pyqtSignal(str, int, str, str, str)
    download_finished = pyqtSignal(str, str)
    download_name_updated = pyqtSignal(str, str, str)  # url, new_filename, new_path

    def __init__(self, parent=None, url="", filename="", page_referer="", dark=True):
        super().__init__(parent, dark=dark, window_title="LDM Stream Downloader")
        self._url          = url
        self._filename     = filename
        self._page_referer = page_referer
        self._last_size    = ""
        self._last_speed   = ""
        self._last_eta     = ""
        self._dl_path      = ""
        self.dl_thread     = None
        self._retried      = False
        self._force_retry  = False
        self._finished_reported = False   # guards closeEvent from stomping Finished with Cancelled
        self._elapsed_start = None
        self._elapsed_timer = None

        self.resize(740, 480)
        self.setMinimumSize(620, 420)
        # Pre-resolve the display name so the user sees the final filename
        # before clicking Download.
        try:
            self._resolved_name = self._resolve_display_name(self._url, self._filename)
        except Exception:
            self._resolved_name = self._filename
        self._build_body()
        self._wire_footer()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_body(self):
        t = self.theme

        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets", "toolbar_icons", "stream.svg",
        )
        hero = _make_hero_band(
            self.body, self.dark, icon_path,
            title="Stream Downloader",
            subtitle="Captured video / HLS streams via yt-dlp.",
            chip_label="HLS",
            accent_color="#7c3aed",
            accent_soft=("rgba(139,92,246,0.16)" if self.dark else "rgba(139,92,246,0.10)"),
        )
        self.body_layout.addWidget(hero)

        content = QWidget()
        content.setStyleSheet(f"background: {t['surface']};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(22, 16, 22, 16)
        cl.setSpacing(10)

        cl.addLayout(self._field_label("URL"))
        cl.addWidget(self._url_field(self._url, tone="violet"))

        # Save as + Save in (two columns). Filename is editable so the user
        # can rename before yt-dlp starts; Save-In has a folder tile + Browse.
        save_row = QHBoxLayout()
        save_row.setSpacing(12)

        as_col = QVBoxLayout(); as_col.setSpacing(6)
        as_col.addLayout(self._field_label("Save as"))
        self.filename_edit = QLineEdit(self._resolved_name or self._filename)
        self.filename_edit.setStyleSheet(_dialog_input_qss(t))
        self.filename_edit.setPlaceholderText("Filename")
        as_col.addWidget(self.filename_edit)
        save_row.addLayout(as_col, 16)

        dir_col = QVBoxLayout(); dir_col.setSpacing(6)
        dir_col.addLayout(self._field_label("Save in"))
        self.save_dir_edit = QLineEdit(os.path.join(HOME, "Downloads", "Videos"))
        self.save_dir_edit.setStyleSheet(_dialog_input_qss(t))
        self.save_dir_edit.setCursorPosition(0)
        dir_col.addWidget(self._dir_field(self.save_dir_edit, tone="violet"))
        save_row.addLayout(dir_col, 12)
        cl.addLayout(save_row)

        # Live stats strip — colored dot + status label on the left, elapsed
        # clock on the right. Matches the design handoff (Stream window).
        stats = QFrame()
        stats.setObjectName("statsCard")
        stats.setStyleSheet(
            f"QFrame#statsCard {{ background: {t['card']}; "
            f"border: 1px solid {t['border']}; border-radius: 10px; }}"
        )
        sl = QHBoxLayout(stats)
        sl.setContentsMargins(16, 11, 16, 11)
        sl.setSpacing(12)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(12, 12)
        self.status_dot.setStyleSheet(
            "background: #22c55e; border-radius: 6px; border: 1px solid rgba(0,0,0,0.10);"
        )
        sl.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self.status_text = QLabel("READY")
        sl.addWidget(self.status_text, 0, Qt.AlignmentFlag.AlignVCenter)
        sl.addStretch()

        elapsed_col = QVBoxLayout()
        elapsed_col.setSpacing(2)
        elapsed_col.setContentsMargins(0, 0, 0, 0)
        elapsed_cap = QLabel("ELAPSED")
        elapsed_cap.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 0.8px; color: {t['subtle']}; background: transparent;"
        )
        elapsed_cap.setAlignment(Qt.AlignmentFlag.AlignRight)
        elapsed_col.addWidget(elapsed_cap)
        self.elapsed_lbl = QLabel("00:00")
        self.elapsed_lbl.setStyleSheet(
            f"font-family: {PLEX_MONO}; font-size: 13px; font-weight: 700; "
            f"color: {t['text']}; background: transparent;"
        )
        self.elapsed_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        elapsed_col.addWidget(self.elapsed_lbl)
        sl.addLayout(elapsed_col)
        cl.addWidget(stats)
        self._set_status("READY", "idle")

        # Recovery row — hidden until a Facebook URL needs manual paste.
        self.paste_row = QWidget()
        pl = QVBoxLayout(self.paste_row)
        pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(6)
        self.paste_hint = QLabel()
        self.paste_hint.setWordWrap(True)
        self.paste_hint.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 12px; color: #f59e0b; "
            f"background: transparent;"
        )
        pl.addWidget(self.paste_hint)
        paste_inner = QHBoxLayout(); paste_inner.setSpacing(8)
        self.paste_input = QLineEdit()
        self.paste_input.setPlaceholderText("Paste the copied link here\u2026")
        self.paste_input.setStyleSheet(_dialog_input_qss(t))
        self.paste_input.returnPressed.connect(self._on_paste_submit)
        paste_inner.addWidget(self.paste_input, 1)
        self.paste_go_btn = QPushButton("Download")
        self.paste_go_btn.setStyleSheet(_dialog_btn_qss(t, "primaryViolet"))
        self.paste_go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.paste_go_btn.clicked.connect(self._on_paste_submit)
        paste_inner.addWidget(self.paste_go_btn)
        pl.addLayout(paste_inner)
        self.paste_row.setVisible(False)
        cl.addWidget(self.paste_row)

        # Hidden log buffer — keeps existing log_box.append() calls valid
        # without rendering a console panel (the user prefers a clean UI).
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.hide()

        self.progress = ProgressSection(content, dark=self.dark)
        self.progress.mark_idle()
        cl.addWidget(self.progress)
        cl.addStretch(1)

        self.body_layout.addWidget(content, 1)

    def _wire_footer(self):
        t = self.theme
        # Force Download — shown only when yt-dlp bails on unusual extensions.
        self.force_dl_btn = QPushButton("Force Download")
        self.force_dl_btn.setStyleSheet(_dialog_btn_qss(t, "primaryViolet"))
        self.force_dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.force_dl_btn.clicked.connect(self._start_force_download)
        self.force_dl_btn.setVisible(False)
        self.footer_layout.addWidget(self.force_dl_btn)

        self.open_file_btn = QPushButton("Open File")
        self.open_file_btn.setStyleSheet(_dialog_btn_qss(t, "primaryBlue"))
        self.open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_file_btn.clicked.connect(self._open_downloaded_file)
        self.open_file_btn.setVisible(False)
        self.footer_layout.addWidget(self.open_file_btn)

        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setStyleSheet(_dialog_btn_qss(t, "secondary"))
        self.open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_folder_btn.clicked.connect(self._open_downloaded_folder)
        self.open_folder_btn.setVisible(False)
        self.footer_layout.addWidget(self.open_folder_btn)

        self.footer_layout.addStretch(1)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet(_dialog_btn_qss(t, "destructive"))
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.clicked.connect(self._cancel)
        self.stop_btn.setVisible(False)
        self.footer_layout.addWidget(self.stop_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.setStyleSheet(_dialog_btn_qss(t, "secondary"))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)
        self.footer_layout.addWidget(self.close_btn)

        self.download_btn = QPushButton("Download")
        self.download_btn.setStyleSheet(_dialog_btn_qss(t, "primaryViolet"))
        self.download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_btn.clicked.connect(self._start_download)
        self.download_btn.setDefault(True)
        self.footer_layout.addWidget(self.download_btn)

    def _field_label(self, text):
        t = self.theme
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 0.8px; color: {t['muted']}; background: transparent;"
        )
        layout.addWidget(lbl); layout.addStretch()
        return layout

    def _url_field(self, value, tone="violet"):
        t = self.theme
        tone_color = {"blue": "#3b82f6", "violet": "#8b5cf6", "red": "#ef4444"}[tone]
        sel_rgb = (
            "rgba(59,130,246,0.35)"  if tone == "blue"  else
            "rgba(139,92,246,0.35)"  if tone == "violet" else
            "rgba(239,68,68,0.35)"
        )
        frame = QFrame()
        frame.setStyleSheet(
            f"background: {t['input_bg']}; border: 1px solid {t['border']}; "
            f"border-radius: 10px;"
        )
        h = QHBoxLayout(frame)
        h.setContentsMargins(10, 8, 12, 8); h.setSpacing(12)
        h.addWidget(_make_glyph_tile(_TILE_SVG_LINK, tone_color, self.dark))
        self.url_edit = QLineEdit(value)
        self.url_edit.setReadOnly(True)
        self.url_edit.setCursorPosition(0)
        self.url_edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {t['text']}; "
            f"font-family: {PLEX_SANS}; font-size: 13.5px; "
            f"selection-background-color: {sel_rgb}; "
            f"selection-color: {t['text']}; }}"
        )
        h.addWidget(self.url_edit, 1)
        return frame

    def _dir_field(self, line_edit, tone="violet", browse_label="Browse"):
        """Wrap a directory QLineEdit in a tile-styled frame: folder glyph on
        the left, the editable path in the middle, a small Browse button on
        the right that pops QFileDialog.getExistingDirectory."""
        t = self.theme
        tone_color = {"blue": "#3b82f6", "violet": "#8b5cf6", "red": "#ef4444"}[tone]
        hover_bg = (
            "rgba(59,130,246,0.10)"  if tone == "blue"  else
            "rgba(139,92,246,0.10)"  if tone == "violet" else
            "rgba(239,68,68,0.10)"
        )
        sel_rgb = (
            "rgba(59,130,246,0.35)"  if tone == "blue"  else
            "rgba(139,92,246,0.35)"  if tone == "violet" else
            "rgba(239,68,68,0.35)"
        )
        frame = QFrame()
        frame.setStyleSheet(
            f"background: {t['input_bg']}; border: 1px solid {t['border']}; "
            f"border-radius: 10px;"
        )
        h = QHBoxLayout(frame)
        h.setContentsMargins(10, 8, 8, 8); h.setSpacing(10)
        h.addWidget(_make_glyph_tile(_TILE_SVG_FOLDER, tone_color, self.dark))

        line_edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {t['text']}; "
            f"font-family: {PLEX_SANS}; font-size: 13.5px; "
            f"selection-background-color: {sel_rgb}; "
            f"selection-color: {t['text']}; }}"
        )
        h.addWidget(line_edit, 1)

        browse = QPushButton(browse_label)
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setStyleSheet(
            f"QPushButton {{ background: {t['card']}; color: {t['text']}; "
            f"border: 1px solid {t['border']}; border-radius: 7px; "
            f"padding: 4px 10px; font-family: {PLEX_SANS}; font-size: 12px; "
            f"font-weight: 600; }} "
            f"QPushButton:hover {{ background: {hover_bg}; "
            f"border-color: {tone_color}; color: {tone_color}; }}"
        )
        browse.clicked.connect(lambda: self._pick_dir(line_edit))
        h.addWidget(browse)
        return frame

    def _pick_dir(self, line_edit):
        start = line_edit.text().strip() or os.path.join(HOME, "Downloads", "Videos")
        chosen = QFileDialog.getExistingDirectory(self, "Select folder", start)
        if chosen:
            line_edit.setText(chosen)

    # ── Status / elapsed helpers ──────────────────────────────────────────────
    def _set_status(self, text, accent="active"):
        t = self.theme
        colors = {
            "active": "#22c55e",
            "retry":  "#f59e0b",
            "error":  "#ef4444",
            "idle":   t['muted'],
            "done":   "#3b82f6",
        }
        c = colors.get(accent, t['muted'])
        self.status_dot.setStyleSheet(
            f"background: {c}; border-radius: 6px; "
            f"border: 1px solid rgba(0,0,0,0.10);"
        )
        self.status_text.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 0.8px; color: {c}; background: transparent;"
        )
        self.status_text.setText(text.upper())

    def _start_elapsed(self):
        if self._elapsed_timer is not None:
            return
        self._elapsed_start = time.monotonic()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._elapsed_timer.start(1000)
        self._tick_elapsed()

    def _stop_elapsed(self):
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None

    def _tick_elapsed(self):
        if not self._elapsed_start:
            return
        secs = int(time.monotonic() - self._elapsed_start)
        mm, ss = divmod(secs, 60)
        hh, mm = divmod(mm, 60)
        self.elapsed_lbl.setText(f"{hh:02d}:{mm:02d}:{ss:02d}" if hh else f"{mm:02d}:{ss:02d}")

    # ── Behaviour (preserves legacy logic verbatim) ──────────────────────────
    def _start_force_download(self):
        """Bypass yt-dlp and download directly via HTTP (curl/requests).
        Used when yt-dlp refuses due to an unusual extension (e.g. .php redirect
        that actually serves video/mp4 content)."""
        self._force_retry = True
        self.force_dl_btn.setVisible(False)
        self.download_btn.setVisible(False)
        self.stop_btn.setVisible(True)
        self.stop_btn.setEnabled(True)
        self.progress.mark_active()
        self.log_box.append("Bypassing yt-dlp \u2014 downloading directly via HTTP\u2026")
        self._set_status("DOWNLOADING (FORCE)", "active")

        folder = self.save_dir_edit.text().strip() or os.path.join(HOME, "Downloads", "Videos")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            folder = os.path.join(HOME, "Downloads", "Videos")
            os.makedirs(folder, exist_ok=True)
            self.save_dir_edit.setText(folder)
        user_name = self.filename_edit.text().strip()
        display_name = user_name or self._resolve_display_name(self._url, self._filename)
        base, _ = os.path.splitext(display_name)
        display_name = f"{base}.mp4"
        self.filename_edit.setText(display_name)
        self._dl_path = os.path.join(folder, display_name)
        self.open_file_btn.setVisible(False)
        self.open_folder_btn.setVisible(False)
        # Update the existing table row instead of creating a second one
        self.download_name_updated.emit(self._url, display_name, self._dl_path)
        # is_video=False → uses curl/requests (bypasses yt-dlp entirely)
        self.dl_thread = DownloadThread(
            self._url, display_name, is_video=False,
            referer=self._page_referer or ""
        )
        self.dl_thread.progress.connect(self._on_progress)
        self.dl_thread.speed.connect(self._on_speed)
        self.dl_thread.downloaded.connect(self._on_size)
        self.dl_thread.eta.connect(self._on_eta)
        self.dl_thread.finished.connect(self._on_finished)
        self.dl_thread.start()

    def _on_paste_submit(self):
        pasted = self.paste_input.text().strip()
        if not pasted:
            return
        self._url = pasted
        self._page_referer = pasted
        self.paste_row.setVisible(False)
        self.url_edit.setText(pasted)
        self.url_edit.setCursorPosition(0)
        # Reset for a fresh attempt
        self._retried = False
        self._force_retry = False
        self.progress.mark_idle()
        self._set_status("STARTING\u2026", "active")
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

            # pvvstream / pvvstream CDN  —  URL pattern:
            #   /videos/{VIDEO_ID}/{RES_ID}/vid_{quality}.mp4
            # Extract both IDs + quality so every video gets a unique name,
            # e.g.  pvv_-174844737_456240335_480p.mp4
            _pv = re.search(
                r'/videos/([^/]+)/([^/]+)/vid_(\w+)\.mp4', url, re.I
            )
            if _pv:
                vid_id, res_id, quality = _pv.group(1), _pv.group(2), _pv.group(3)
                return f'pvv_{vid_id}_{res_id}_{quality}.mp4'

            # Generic — strip only filesystem-unsafe chars. A whitelist on
            # \w would drop Unicode combining marks (Bengali vowel signs,
            # candrabindu, halant etc. are category M, not L).
            safe = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', filename)[:80].strip()
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
        folder = self.save_dir_edit.text().strip() or os.path.join(HOME, "Downloads", "Videos")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            folder = os.path.join(HOME, "Downloads", "Videos")
            os.makedirs(folder, exist_ok=True)
            self.save_dir_edit.setText(folder)
        # Luluvdo / Lulustream: handled by a dedicated downloader (see
        # LuluHLSDownloadThread). yt-dlp/ffmpeg both 403 against this CDN.
        _is_lulu_page = bool(re.search(
            r'(?:luluvdo|lulustream)\.com', self._url, re.I
        ))
        user_name = self.filename_edit.text().strip()
        display_name = user_name or self._resolve_display_name(self._url, self._filename)
        base, ext = os.path.splitext(display_name)
        if not ext:
            ext = ".mp4"
            display_name = f"{base}{ext}"
        # If a file with this name already exists on disk it almost certainly
        # contains a *different* video (CDNs like pvvstream reuse generic names
        # such as vid_480p.mp4 for every video).  Increment (1), (2), … until
        # we find a free slot so we never silently overwrite existing content.
        _base, _ext = os.path.splitext(display_name)
        _counter = 1
        while os.path.exists(os.path.join(folder, display_name)):
            display_name = f"{_base} ({_counter}){_ext}"
            _counter += 1
        base = os.path.splitext(display_name)[0]   # keep base in sync for outtmpl below
        self.filename_edit.setText(display_name)
        http_hdrs = {'User-Agent': HEADERS['User-Agent']}
        # TikTok CDN requires Referer header to avoid 403
        if 'tiktok.com' in self._url:
            http_hdrs['Referer'] = 'https://www.tiktok.com/'
        if self._page_referer:
            http_hdrs['Referer'] = self._page_referer
        # Lulustream/Luluvdo CDNs (e.g. *.tnmr.org) reject requests without
        # an Origin and Sec-Fetch-* set — match what Firefox sends.
        _is_lulu = bool(re.search(
            r'(?:luluvdo|lulustream)\.com|\btnmr\.org',
            self._url + ' ' + (self._page_referer or ''),
            re.I,
        ))
        if _is_lulu:
            http_hdrs.update({
                'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64; rv:151.0) '
                               'Gecko/20100101 Firefox/151.0'),
                'Referer':         'https://luluvdo.com/',
                'Origin':          'https://luluvdo.com',
                'Accept':          '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Sec-Fetch-Dest':  'empty',
                'Sec-Fetch-Mode':  'cors',
                'Sec-Fetch-Site':  'cross-site',
            })
        self._dl_path = os.path.join(folder, display_name)
        self.open_file_btn.setVisible(False)
        self.open_folder_btn.setVisible(False)
        self.download_btn.setVisible(False)
        self.stop_btn.setVisible(True)
        self.stop_btn.setEnabled(True)
        self.progress.mark_active()
        self._set_status("DOWNLOADING", "active")
        self._start_elapsed()
        self.download_started.emit(self._url, display_name, folder)
        # Lulustream / Luluvdo page URL: dedicated downloader fetches the
        # whole HLS via Python requests and muxes locally.
        if _is_lulu_page:
            self._retried = True  # don't auto-retry through page-URL fallback
            self.dl_thread = LuluHLSDownloadThread(self._url, self._dl_path)
            self.dl_thread.progress.connect(self._on_progress)
            self.dl_thread.speed.connect(self._on_speed)
            self.dl_thread.size_info.connect(self._on_size)
            self.dl_thread.eta.connect(self._on_eta)
            self.dl_thread.log.connect(lambda msg: self.log_box.append(msg))
            self.dl_thread.finished.connect(self._on_finished)
            self.dl_thread.start()
            return
        ydl_opts = {
            'format':              'bestvideo+bestaudio/best',
            'outtmpl':             os.path.join(folder, f"{base}.%(ext)s"),
            'paths':               {'temp': YT_DLP_TEMP_DIR},
            'merge_output_format': 'mp4',
            'quiet':               True,
            'no_warnings':         True,
            'cookiesfrombrowser':  ('firefox', get_firefox_profile()),
            'http_headers':        http_hdrs,
            # Survive transient packet drops (BD ISP-level SNI/DPI filtering on
            # adult/social CDNs occasionally kills mid-segment fetches).
            'retries':             10,
            'fragment_retries':    10,
            'socket_timeout':      30,
            # CDNs commonly ship a leaf cert without the intermediate chain
            # (e.g. masahub.cc serves a valid Sectigo cert but omits the
            # intermediate, breaking strict verification). Our requests path
            # already uses verify=False — match that here so yt-dlp doesn't
            # bail on the same servers we'd otherwise download from fine.
            'nocheckcertificate':  True,
        }
        self.dl_thread = YouTubeDownloadThread(self._url, ydl_opts)
        self.dl_thread.progress.connect(self._on_progress)
        self.dl_thread.speed.connect(self._on_speed)
        self.dl_thread.size_info.connect(self._on_size)
        self.dl_thread.eta.connect(self._on_eta)
        self.dl_thread.log.connect(lambda msg: self.log_box.append(msg))
        self.dl_thread.finished.connect(self._on_finished)
        self.dl_thread.start()
        self.log_box.append("Starting stream download\u2026")

    def _on_progress(self, pct):
        self.progress.set_pct(pct)
        self.download_progress.emit(
            self._url, pct, self._last_size, self._last_speed, self._last_eta,
        )

    def _on_speed(self, spd):
        self._last_speed = spd
        self.progress.set_speed_text(spd)

    def _on_size(self, sz):
        self._last_size = sz
        self.progress.set_size_text(sz)

    def _on_eta(self, eta):
        self._last_eta = eta
        self.progress.set_eta_text(eta if eta != "\u2014" else "")

    def closeEvent(self, event):
        """Handle window X button — cancel thread and save to history."""
        self._stop_elapsed()
        if self.dl_thread and self.dl_thread.isRunning() and not self._finished_reported:
            # Cooperative cancel — workers check self.running and exit on
            # their own. QThread.terminate() can deadlock the GIL when the
            # worker is mid-call inside a C extension.
            self.dl_thread.running = False
            try:
                self.dl_thread.blockSignals(True)
            except Exception:
                pass
            self.download_finished.emit(self._url, "Cancelled")
        event.accept()

    def _cancel(self):
        if not self.dl_thread or not self.dl_thread.isRunning():
            return
        # Cooperative cancel — the worker's own loop polls ``running``;
        # the UI finalizes in _on_finished("Cancelled") when run() exits.
        self.dl_thread.running = False
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Cancelling\u2026")
        self.log_box.append("Cancelling download\u2026")
        self._set_status("CANCELLING", "retry")

    def _friendly_error(self, msg):
        """Translate raw yt-dlp error strings into clean user-facing messages."""
        m = msg.lower()
        # Unusual extension safety block (e.g. .php) — offer force download
        if "unusual" in m and "extension" in m and "skipped" in m:
            return (
                "yt-dlp skipped this URL because the file extension looks unusual "
                "(e.g. .php instead of .mp4).\n\n"
                "Click \"Force Download\" to ignore the extension check and "
                "download anyway."
            ), "__force_ext__"
        # Facebook feed URL (bare facebook.com) -- needs manual paste
        if "unsupported url" in m and self._url and (
            'facebook.com' in self._url or 'fb.watch' in self._url
        ):
            is_reel = '/reel/' in self._url
            if is_reel:
                return (
                    "Facebook Reels — cannot download automatically on first entry.\n\n"
                    "On the reel, click Share \u2192 Copy link\n"
                    "(or \u22ef (3 dots) \u2192 Copy link),\n"
                    "then paste the link in the box below and click Start Download."
                ), "Paste the reel link below to download"
            return (
                "Facebook feed video — cannot download automatically.\n\n"
                "On the video, click \u22ef (3 dots) \u2192 Copy link,\n"
                "then paste the link in the box below and click Start Download."
            ), "Paste the video link below to download"
        # Outdated yt-dlp on a major host — extractor returns "no formats" when
        # YouTube/Facebook change their delivery flow. Press-Play won't fix this.
        if "no video formats" in m and self._url and any(
            h in self._url for h in ('youtube.com', 'youtu.be', 'facebook.com', 'fb.watch')
        ):
            return (
                "yt-dlp is out of date and can no longer read this site.\n\n"
                "Open a terminal and run:\n"
                "  pip install -U yt-dlp --break-system-packages\n\n"
                "Then restart LDM and try again."
            ), "yt-dlp out of date — run pip install -U yt-dlp"
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

    def _open_downloaded_file(self):
        path = getattr(self, '_dl_path', '')
        if path and os.path.exists(path):
            subprocess.Popen(['xdg-open', path])
        elif path:
            subprocess.Popen(['xdg-open', os.path.dirname(path)])
        self.close()

    def _open_downloaded_folder(self):
        path = getattr(self, '_dl_path', '')
        folder = os.path.dirname(path) if path else ''
        if folder and os.path.exists(folder):
            subprocess.Popen(['xdg-open', folder])
        self.close()

    def _on_finished(self, msg):
        self.stop_btn.setEnabled(False)
        # Cancellation arrives here as either "Cancelled" (curl path) or
        # "Error: Cancelled" (yt-dlp hook path). Treat both the same.
        if msg == "Cancelled" or msg.startswith("Error: Cancelled"):
            self._stop_elapsed()
            self.log_box.append("Download cancelled.")
            self.progress.mark_error("Cancelled")
            self._set_status("CANCELLED", "error")
            self.stop_btn.setVisible(False)
            self.stop_btn.setEnabled(True)
            self.stop_btn.setText("Stop")
            self.download_btn.setVisible(True)
            self._finished_reported = True
            self.download_finished.emit(self._url, "Cancelled")
            return
        if msg == "Finished":
            self._stop_elapsed()
            self.progress.mark_complete()
            self._set_status("DONE", "done")
            self.log_box.append("Download complete!")
            self.stop_btn.setVisible(False)
            self.force_dl_btn.setVisible(False)
            self.open_file_btn.setVisible(True)
            self.open_folder_btn.setVisible(True)
            # If force-downloaded via DownloadThread, the thread may have resolved
            # a better filename from Content-Disposition — sync _dl_path and label.
            if self._force_retry and self.dl_thread and hasattr(self.dl_thread, 'filename'):
                resolved = self.dl_thread.filename
                folder   = choose_folder(resolved)
                self._dl_path = os.path.join(folder, resolved)
                self.filename_edit.setText(resolved)
                self.download_name_updated.emit(self._url, resolved, self._dl_path)
            try:
                if _strip_png_disguised_segments(self._dl_path):
                    self.log_box.append("Stripped PNG-disguised HLS segments and remuxed.")
            except Exception as _e:
                self.log_box.append(f"PNG-strip post-process failed: {_e}")
            self._finished_reported = True
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
            self.log_box.append("Stream URL expired (403) \u2014 retrying with page URL\u2026")
            self._set_status("RETRYING\u2026", "retry")
            self._url = self._page_referer
            self.url_edit.setText(self._url)
            self.url_edit.setCursorPosition(0)
            self.progress.mark_idle()
            self.stop_btn.setEnabled(True)
            self._start_download()
            return
        # Show clean error message
        self._stop_elapsed()
        log_msg, label_msg = self._friendly_error(msg)
        self.log_box.append(log_msg)
        # Unusual extension — offer force download button
        if label_msg == "__force_ext__" and not self._force_retry:
            self.progress.mark_error("Unusual extension")
            self._set_status("UNUSUAL EXTENSION", "error")
            self.force_dl_btn.setVisible(True)
            self.stop_btn.setVisible(False)
            self.download_btn.setVisible(False)
        # Facebook paste hint -- show input row so user can paste link
        elif 'Paste the video link' in label_msg or 'Paste the reel link' in label_msg:
            self.progress.mark_error(label_msg)
            self._set_status("PASTE LINK BELOW", "retry")
            if 'reel link' in label_msg:
                self.paste_hint.setText(
                    "Share \u2192 Copy link (or \u22ef \u2192 Copy link) on the reel \u2192 paste below:"
                )
            else:
                self.paste_hint.setText(
                    "\u22ef (3 dots) on video \u2192 Copy link \u2192 paste below:"
                )
            self.paste_row.setVisible(True)
            self.paste_input.setFocus()
            self.stop_btn.setVisible(False)
            self.download_btn.setVisible(False)
        else:
            self.progress.mark_error(label_msg)
            self._set_status("ERROR", "error")
            self.stop_btn.setVisible(False)
            self.download_btn.setVisible(True)
            self.download_finished.emit(self._url, msg)


class _ThumbnailFetchThread(QThread):
    """Tiny worker that downloads a video thumbnail and emits the bytes.

    yt-dlp gives us the canonical thumbnail URL in info_dict; loading it here
    keeps the main UI thread responsive even on slow links."""
    loaded = pyqtSignal(bytes)
    failed = pyqtSignal()

    def __init__(self, url):
        super().__init__()
        self._url = url

    def run(self):
        try:
            r = requests.get(self._url, timeout=8, verify=False)
            if r.status_code == 200 and r.content:
                self.loaded.emit(r.content)
                return
        except Exception:
            pass
        self.failed.emit()


class _ClickableFrame(QFrame):
    """QFrame variant that emits ``clicked`` on left mouse release.
    Used for the format/quality picker cards in the YouTube dialog."""
    clicked = pyqtSignal()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and getattr(self, "_pressed", False):
            self._pressed = False
            if self.rect().contains(e.pos()):
                self.clicked.emit()
        super().mouseReleaseEvent(e)


class _RadioGlyph(QWidget):
    """16x16 radio button glyph. Unchecked: ring outline. Checked: ring +
    inner dot, both in the accent colour."""

    def __init__(self, parent=None, accent="#dc2626", border="#cbd5e1"):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._checked = False
        self._accent = QColor(accent)
        self._border = QColor(border)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_checked(self, checked: bool):
        self._checked = checked
        self.update()

    def set_colors(self, accent: str, border: str):
        self._accent = QColor(accent)
        self._border = QColor(border)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(Qt.BrushStyle.NoBrush)
        ring = self._accent if self._checked else self._border
        pen = QPen(ring)
        pen.setWidthF(1.6)
        p.setPen(pen)
        p.drawEllipse(1, 1, 14, 14)
        if self._checked:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._accent)
            p.drawEllipse(5, 5, 6, 6)
        p.end()


class YouTubeDialog(DownloaderDialogBase):
    download_started     = pyqtSignal(str, str, str)
    download_progress    = pyqtSignal(str, int, str, str, str)
    download_finished    = pyqtSignal(str, str)
    yt_settings_captured = pyqtSignal(str, dict)  # url, {mode, quality, audio_fmt, ...}

    # (id, sub-label, est-size placeholder, yt-dlp height filter)
    QUALITIES = [
        ('2160p',   '4K \u00b7 VP9',    '~1.8 GB', 2160),
        ('1440p',   'QHD \u00b7 VP9',   '~920 MB', 1440),
        ('1080p60', 'FHD \u00b7 h264',  '~480 MB', 1080),
        ('720p',    'HD \u00b7 h264',   '~210 MB', 720),
        ('480p',    'SD \u00b7 h264',   '~92 MB',  480),
        ('360p',    'mobile',           '~54 MB',  360),
    ]

    # (id, title, sub-label, codec, kbps — None for m4a "original")
    AUDIO_CHOICES = [
        ('mp3_320', 'MP3 320',  'high quality',    'mp3', 320),
        ('mp3_256', 'MP3 256',  'standard',        'mp3', 256),
        ('mp3_128', 'MP3 128',  'smaller file',    'mp3', 128),
        ('m4a',     'M4A',      'AAC \u00b7 original', 'm4a', None),
    ]

    def __init__(self, parent=None, prefill_url="", dark=True, skip_fetch=False):
        super().__init__(parent, dark=dark, window_title="LDM YouTube Downloader")
        self.video_title  = ""
        self.fetch_thread = None
        self.thumb_thread = None
        self.dl_thread    = None
        self._last_size   = ""
        self._last_speed  = ""
        self._last_eta    = ""
        self._current_url = ""
        self._dl_folder   = ""
        self._dl_base     = ""
        self._mode        = "video"     # "video" | "audio"
        self._quality_id  = "1080p60"
        self._audio_id    = "mp3_320"
        self._info        = None        # populated by FetchFormatsThread
        self._format_cards  = {}
        self._quality_cards = {}
        self._audio_cards   = {}

        self.resize(720 + 48, 760 + 48)
        self.setMinimumSize(640 + 48, 700 + 48)

        self._build_body()
        self._wire_footer()
        self._select_format("video")
        self._select_quality("1080p60")
        self._select_audio("mp3_320")
        self._refresh_summary()

        if prefill_url:
            self.url_input.setText(prefill_url)
            if not skip_fetch:
                self.fetch_formats()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_body(self):
        t = self.theme
        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets", "toolbar_icons", "youtube.svg",
        )
        hero = _make_hero_band(
            self.body, self.dark, icon_path,
            title="YouTube Downloader",
            accent_color="#dc2626",
            accent_soft=("rgba(239,68,68,0.16)" if self.dark else "rgba(239,68,68,0.08)"),
        )
        self.body_layout.addWidget(hero)

        content = QWidget()
        content.setStyleSheet(f"background: {t['surface']};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(22, 16, 22, 16)
        cl.setSpacing(12)

        # URL row
        cl.addLayout(self._field_label("Video URL"))
        url_row = QHBoxLayout(); url_row.setSpacing(8)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste YouTube URL here\u2026")
        self.url_input.setStyleSheet(_dialog_input_qss(t))
        self.url_input.returnPressed.connect(self._on_paste_or_fetch)
        url_row.addWidget(self.url_input, 1)
        self.fetch_btn = QPushButton("Paste")
        self.fetch_btn.setStyleSheet(_dialog_btn_qss(t, "secondary"))
        self.fetch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fetch_btn.clicked.connect(self._on_paste_or_fetch)
        url_row.addWidget(self.fetch_btn)
        cl.addLayout(url_row)

        # Fetched video card (skeleton until fetch_formats completes)
        cl.addWidget(self._build_video_card())

        # Format picker (Video + audio | Audio only)
        cl.addLayout(self._field_label("Format"))
        fmt_row = QHBoxLayout(); fmt_row.setSpacing(8)
        for fid, label, sub in (
            ("video", "Video + audio", "mp4 \u00b7 combined"),
            ("audio", "Audio only",    "MP3 / M4A"),
        ):
            card = self._make_format_card(fid, label, sub)
            self._format_cards[fid] = card
            fmt_row.addWidget(card, 1)
        cl.addLayout(fmt_row)

        # Quality grid — only shown when format = video
        self.quality_label_layout = self._field_label("Quality")
        cl.addLayout(self.quality_label_layout)
        self.quality_grid = QWidget()
        qg = QHBoxLayout(self.quality_grid)
        qg.setContentsMargins(0, 0, 0, 0); qg.setSpacing(6)
        for qid, sub, size, _h in self.QUALITIES:
            card = self._make_quality_card(qid, sub, size)
            self._quality_cards[qid] = card
            qg.addWidget(card, 1)
        cl.addWidget(self.quality_grid)

        # Audio grid — only shown when format = audio
        self.audio_grid = QWidget()
        ag = QHBoxLayout(self.audio_grid)
        ag.setContentsMargins(0, 0, 0, 0); ag.setSpacing(6)
        for aid, title_, sub, _codec, _kbps in self.AUDIO_CHOICES:
            card = self._make_audio_card(aid, title_, sub)
            self._audio_cards[aid] = card
            ag.addWidget(card, 1)
        cl.addWidget(self.audio_grid)
        self.audio_grid.setVisible(False)

        # Extras row — checkboxes
        extras = QHBoxLayout(); extras.setSpacing(22)
        tick_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets", "check_tick.svg",
        ).replace("\\", "/")
        chk_qss = (
            f"QCheckBox {{ font-family: {PLEX_SANS}; font-size: 13px; "
            f"color: {t['text']}; spacing: 8px; background: transparent; }}"
            f" QCheckBox::indicator {{ width: 17px; height: 17px; "
            f"border-radius: 5px; border: 1.5px solid {t['border']}; "
            f"background: {t['input_bg']}; }}"
            f" QCheckBox::indicator:checked {{ "
            f"background: #dc2626; border: 1.5px solid #dc2626; "
            f"image: url({tick_path}); }}"
        )
        self.subs_chk = QCheckBox("Embed subtitles")
        self.subs_chk.setStyleSheet(chk_qss)
        self.subs_chk.setChecked(False)
        self.thumb_chk = QCheckBox("Embed thumbnail")
        self.thumb_chk.setStyleSheet(chk_qss)
        self.thumb_chk.setChecked(True)
        extras.addWidget(self.subs_chk)
        extras.addWidget(self.thumb_chk)
        extras.addStretch()
        cl.addLayout(extras)

        # Hidden log buffer — preserves legacy log_box.append calls.
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.hide()

        self.progress = ProgressSection(content, dark=self.dark)
        self.progress.mark_idle()
        cl.addWidget(self.progress)

        # Back-compat aliases (older code paths reference these directly).
        self.progress_bar = self.progress.bar
        self.info_label   = self.progress.label_lbl

        self.body_layout.addWidget(content, 1)

    def _wire_footer(self):
        t = self.theme

        # Summary string — "Will download ~480 MB to ~/Downloads/Videos/"
        self.summary_lbl = QLabel("")
        self.summary_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 12px; color: {t['muted']}; "
            f"background: transparent;"
        )
        self.summary_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.footer_layout.addWidget(self.summary_lbl, 1)

        self.open_file_btn = QPushButton("Open File")
        self.open_file_btn.setStyleSheet(_dialog_btn_qss(t, "primaryBlue"))
        self.open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_file_btn.clicked.connect(self._open_downloaded_file)
        self.open_file_btn.setVisible(False)
        self.footer_layout.addWidget(self.open_file_btn)

        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setStyleSheet(_dialog_btn_qss(t, "secondary"))
        self.open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_folder_btn.clicked.connect(self._open_downloaded_folder)
        self.open_folder_btn.setVisible(False)
        self.footer_layout.addWidget(self.open_folder_btn)

        self.cancel_dl_btn = QPushButton("Stop")
        self.cancel_dl_btn.setStyleSheet(_dialog_btn_qss(t, "destructive"))
        self.cancel_dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_dl_btn.clicked.connect(self.cancel_download)
        self.cancel_dl_btn.setVisible(False)
        self.footer_layout.addWidget(self.cancel_dl_btn)

        self.close_btn = QPushButton("Cancel")
        self.close_btn.setStyleSheet(_dialog_btn_qss(t, "secondary"))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)
        self.footer_layout.addWidget(self.close_btn)

        self.download_btn = QPushButton("Download")
        self.download_btn.setStyleSheet(_dialog_btn_qss(t, "primaryRed"))
        self.download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setDefault(True)
        self.footer_layout.addWidget(self.download_btn)

    def _field_label(self, text):
        t = self.theme
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 0.8px; color: {t['muted']}; background: transparent;"
        )
        layout.addWidget(lbl); layout.addStretch()
        return layout

    def _build_video_card(self):
        t = self.theme
        card = QFrame()
        card.setObjectName("ytVideoCard")
        card.setStyleSheet(
            f"QFrame#ytVideoCard {{ background: {t['card']}; "
            f"border: 1px solid {t['border']}; border-radius: 12px; }}"
        )
        h = QHBoxLayout(card)
        h.setContentsMargins(12, 12, 12, 12); h.setSpacing(14)

        # Thumbnail tile (gradient placeholder until a real thumb loads)
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(132, 74)
        self.thumb_lbl.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            "stop:0 #4338ca, stop:0.6 #ec4899, stop:1 #f59e0b); "
            "border-radius: 8px;"
        )
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setText("\u25B6")
        self.thumb_lbl.setStyleSheet(self.thumb_lbl.styleSheet() + (
            f" color: rgba(255,255,255,0.85); font-size: 22px;"
        ))
        h.addWidget(self.thumb_lbl)

        info_col = QVBoxLayout(); info_col.setSpacing(4)
        self.video_title_lbl = QLabel("Paste a YouTube URL above to fetch video info\u2026")
        self.video_title_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 14px; font-weight: 700; "
            f"color: {t['text']}; background: transparent;"
        )
        self.video_title_lbl.setWordWrap(False)
        info_col.addWidget(self.video_title_lbl)

        self.video_meta_lbl = QLabel("")
        self.video_meta_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 11.5px; color: {t['muted']}; "
            f"background: transparent;"
        )
        info_col.addWidget(self.video_meta_lbl)

        self.tag_row = QHBoxLayout()
        self.tag_row.setContentsMargins(0, 4, 0, 0); self.tag_row.setSpacing(6)
        self.tag_row.addStretch()
        tag_wrap = QWidget()
        tag_wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        tag_wrap.setStyleSheet("background: transparent;")
        tag_wrap.setLayout(self.tag_row)
        info_col.addWidget(tag_wrap)

        h.addLayout(info_col, 1)

        # Back-compat: external code reads title_label.text() in some paths.
        self.title_label = self.video_title_lbl
        return card

    def _set_tags(self, tags):
        t = self.theme
        # Clear out any existing tag chips, then re-add.
        while self.tag_row.count() > 0:
            item = self.tag_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for tag in tags:
            chip = QLabel(tag)
            chip.setStyleSheet(
                f"font-family: {PLEX_SANS}; font-size: 10px; font-weight: 600; "
                f"padding: 3px 7px; border-radius: 999px; "
                f"background: rgba(148,163,184,0.18); color: {t['muted']};"
            )
            self.tag_row.addWidget(chip)
        self.tag_row.addStretch()

    def _make_format_card(self, fid, label, sub):
        t = self.theme
        card = _ClickableFrame()
        card.setObjectName(f"ytFmt_{fid}")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        h = QHBoxLayout(card)
        h.setContentsMargins(12, 10, 12, 10); h.setSpacing(10)

        radio = _RadioGlyph(accent="#dc2626", border=t['border'])
        card._radio = radio  # keep handle for selection refresh
        h.addWidget(radio, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout(); text_col.setSpacing(1)
        title = QLabel(label)
        title.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 13.5px; font-weight: 700; "
            f"color: {t['text']}; background: transparent;"
        )
        text_col.addWidget(title)
        sub_lbl = QLabel(sub)
        sub_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 11px; color: {t['muted']}; "
            f"background: transparent;"
        )
        text_col.addWidget(sub_lbl)
        h.addLayout(text_col, 1)

        card.clicked.connect(lambda fid=fid: self._select_format(fid))
        return card

    def _make_quality_card(self, qid, sub, size):
        t = self.theme
        card = _ClickableFrame()
        card.setObjectName(f"ytQ_{qid}")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        v = QVBoxLayout(card)
        v.setContentsMargins(8, 8, 8, 8); v.setSpacing(2)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(qid); title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName(f"ytQTitle_{qid}")
        v.addWidget(title)
        sub_lbl = QLabel(sub); sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 9.5px; color: {t['muted']}; "
            f"background: transparent;"
        )
        v.addWidget(sub_lbl)
        size_lbl = QLabel(size); size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        size_lbl.setStyleSheet(
            f"font-family: {PLEX_MONO}; font-size: 10px; font-weight: 700; "
            f"color: {t['subtle']}; background: transparent;"
        )
        v.addWidget(size_lbl)

        card._title_lbl = title
        card._size_lbl  = size_lbl
        card.clicked.connect(lambda qid=qid: self._select_quality(qid))
        return card

    def _make_audio_card(self, aid, title_text, sub_text):
        t = self.theme
        card = _ClickableFrame()
        card.setObjectName(f"ytA_{aid}")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        v = QVBoxLayout(card)
        v.setContentsMargins(8, 8, 8, 8); v.setSpacing(2)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(title_text); title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName(f"ytATitle_{aid}")
        v.addWidget(title)
        sub_lbl = QLabel(sub_text); sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 9.5px; color: {t['muted']}; "
            f"background: transparent;"
        )
        v.addWidget(sub_lbl)
        size_lbl = QLabel(""); size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        size_lbl.setStyleSheet(
            f"font-family: {PLEX_MONO}; font-size: 10px; font-weight: 700; "
            f"color: {t['subtle']}; background: transparent;"
        )
        v.addWidget(size_lbl)

        card._title_lbl = title
        card._sub_lbl   = sub_lbl
        card._size_lbl  = size_lbl
        card.clicked.connect(lambda aid=aid: self._select_audio(aid))
        return card

    @staticmethod
    def _humanize_size(n):
        if not n or n < 0:
            return ""
        if n >= 1024**3:
            return f"~{n / 1024**3:.1f} GB"
        if n >= 1024**2:
            return f"~{int(round(n / 1024**2))} MB"
        if n >= 1024:
            return f"~{int(round(n / 1024))} KB"
        return f"~{n} B"

    # ── Selection helpers ─────────────────────────────────────────────────────
    def _select_format(self, fid):
        self._mode = fid
        t = self.theme
        for cid, card in self._format_cards.items():
            active = (cid == fid)
            bg = (
                ("rgba(220,38,38,0.16)" if self.dark else "rgba(220,38,38,0.08)")
                if active else t['input_bg']
            )
            border = "#dc2626" if active else t['border']
            card.setStyleSheet(
                f"QFrame#{card.objectName()} {{ background: {bg}; "
                f"border: 1.5px solid {border}; border-radius: 10px; }}"
            )
            card._radio.set_checked(active)
        # Swap which grid is shown — quality (video) vs audio choices
        audio_mode = (fid == "audio")
        self.quality_grid.setVisible(not audio_mode)
        self.audio_grid.setVisible(audio_mode)
        # The "QUALITY" caption is shared by both grids
        for i in range(self.quality_label_layout.count()):
            w = self.quality_label_layout.itemAt(i).widget()
            if w is not None:
                w.setVisible(True)
        self._refresh_summary()

    def _select_quality(self, qid):
        self._quality_id = qid
        t = self.theme
        for cid, card in self._quality_cards.items():
            active = (cid == qid)
            bg = (
                ("rgba(220,38,38,0.16)" if self.dark else "rgba(220,38,38,0.08)")
                if active else t['input_bg']
            )
            border = "#dc2626" if active else t['border']
            card.setStyleSheet(
                f"QFrame#{card.objectName()} {{ background: {bg}; "
                f"border: 1.5px solid {border}; border-radius: 9px; }}"
            )
            card._title_lbl.setStyleSheet(
                f"font-family: {PLEX_SANS}; font-size: 12.5px; font-weight: 800; "
                f"color: {'#dc2626' if active else t['text']}; "
                f"background: transparent;"
            )
        self._refresh_summary()

    def _select_audio(self, aid):
        self._audio_id = aid
        t = self.theme
        for cid, card in self._audio_cards.items():
            active = (cid == aid)
            bg = (
                ("rgba(220,38,38,0.16)" if self.dark else "rgba(220,38,38,0.08)")
                if active else t['input_bg']
            )
            border = "#dc2626" if active else t['border']
            card.setStyleSheet(
                f"QFrame#{card.objectName()} {{ background: {bg}; "
                f"border: 1.5px solid {border}; border-radius: 9px; }}"
            )
            card._title_lbl.setStyleSheet(
                f"font-family: {PLEX_SANS}; font-size: 12.5px; font-weight: 800; "
                f"color: {'#dc2626' if active else t['text']}; "
                f"background: transparent;"
            )
        self._refresh_summary()

    def _audio_choice(self):
        for aid, _t, _s, codec, kbps in self.AUDIO_CHOICES:
            if aid == self._audio_id:
                return codec, kbps
        return 'mp3', 320

    def _estimate_audio_bytes(self):
        codec, kbps = self._audio_choice()
        duration = getattr(self, '_duration', 0) or 0
        if codec == 'm4a':
            # Native AAC stream — use yt-dlp's reported audio_bytes if available
            return getattr(self, '_audio_bytes', 0) or (
                int(duration * 128 * 1000 / 8) if duration else 0
            )
        if duration and kbps:
            return int(duration * kbps * 1000 / 8)
        return 0

    def _selected_height(self):
        for qid, _sub, _size, h in self.QUALITIES:
            if qid == self._quality_id:
                return h
        return 1080

    def _refresh_summary(self):
        t = self.theme
        size_by_h = getattr(self, '_size_by_height', {}) or {}
        audio_bytes = getattr(self, '_audio_bytes', 0) or 0
        duration = getattr(self, '_duration', 0) or 0

        if self._mode == "audio":
            folder = "~/Downloads/Music/"
            est = self._estimate_audio_bytes()
            size = self._humanize_size(est) if est else "~5\u201310 MB"
        else:
            folder = "~/Downloads/Videos/"
            # Find target height for the selected quality card
            target = self._selected_height()
            matching = [hh for hh in size_by_h if hh >= target]
            chosen = min(matching) if matching else None
            if chosen is not None:
                size = self._humanize_size(size_by_h[chosen])
            else:
                size = "—"
        self.summary_lbl.setText(
            f"<span>Will download </span>"
            f"<b style='color:{t['text']}; font-family: {PLEX_MONO};'>{size}</b>"
            f"<span> to </span>"
            f"<b style='color:{t['text']}; font-family: {PLEX_MONO};'>{folder}</b>"
        )

    # ── Fetch flow ────────────────────────────────────────────────────────────
    def _on_paste_or_fetch(self):
        if not self.url_input.text().strip():
            txt = QApplication.clipboard().text().strip()
            if txt:
                self.url_input.setText(txt)
        self.fetch_formats()

    def fetch_formats(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching\u2026")
        self.video_title_lbl.setText("Fetching video info\u2026")
        self.video_meta_lbl.setText("")
        self._set_tags([])
        self.fetch_thread = FetchFormatsThread(url)
        self.fetch_thread.info_ready.connect(self._on_info_ready)
        self.fetch_thread.error.connect(self._on_fetch_error)
        self.fetch_thread.start()

    def _on_info_ready(self, info):
        self._info = info
        self.video_title = info.get('title', '') or 'video'
        self.video_title_lbl.setText(self.video_title)

        channel = info.get('channel', '') or ''
        views   = info.get('view_count', 0) or 0
        ud      = info.get('upload_date', '') or ''
        upload_str = ''
        if ud and len(ud) == 8:
            upload_str = f"{ud[:4]}-{ud[4:6]}-{ud[6:]}"
        bits = []
        if channel:
            bits.append(channel)
        if views:
            bits.append(f"{views:,} views")
        if upload_str:
            bits.append(f"Uploaded {upload_str}")
        self.video_meta_lbl.setText("  \u00b7  ".join(bits))

        tags = []
        cats = info.get('categories') or []
        if cats:
            tags.append(cats[0])
        heights = info.get('heights') or []
        if heights:
            top = max(heights)
            tags.append(f"{top}p available")
        if info.get('has_subs'):
            tags.append("CC available")
        self._set_tags(tags)

        # Update each quality card with the real size mined from yt-dlp.
        self._size_by_height = info.get('size_by_height') or {}
        self._audio_bytes    = info.get('audio_bytes') or 0
        self._audio_kbps     = info.get('audio_kbps') or 0
        self._duration       = info.get('duration') or 0
        for qid, _sub, fallback, h in self.QUALITIES:
            avail = (not heights) or any(hh >= h for hh in heights)
            self._quality_cards[qid].setEnabled(avail)
            self._quality_cards[qid].setVisible(True)
            # Pick the closest available height >= card's target
            matching = [hh for hh in self._size_by_height if hh >= h]
            chosen = min(matching) if matching else None
            if chosen is not None:
                self._quality_cards[qid]._size_lbl.setText(
                    self._humanize_size(self._size_by_height[chosen])
                )
            else:
                self._quality_cards[qid]._size_lbl.setText("—")

        # Audio card sizes — mp3 sizes derive from duration × bitrate, m4a
        # uses the actual best-audio size yt-dlp reports.
        duration = self._duration
        for aid, _t, _s, codec, kbps in self.AUDIO_CHOICES:
            if codec == 'm4a':
                bytes_ = self._audio_bytes
            elif duration and kbps:
                bytes_ = int(duration * kbps * 1000 / 8)
            else:
                bytes_ = 0
            card = self._audio_cards[aid]
            card._size_lbl.setText(
                self._humanize_size(bytes_) if bytes_ else "—"
            )
            if codec == 'm4a':
                card._sub_lbl.setText(
                    f"AAC \u00b7 {self._audio_kbps} kbps"
                    if self._audio_kbps else "AAC \u00b7 original"
                )

        self._refresh_summary()

        # Fetch the thumbnail off the UI thread
        thumb_url = info.get('thumbnail') or ''
        if thumb_url:
            self.thumb_thread = _ThumbnailFetchThread(thumb_url)
            self.thumb_thread.loaded.connect(self._on_thumb_loaded)
            self.thumb_thread.start()

        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Refresh")

    def _on_thumb_loaded(self, data):
        try:
            pm = QPixmap()
            if pm.loadFromData(data):
                w, h = self.thumb_lbl.width(), self.thumb_lbl.height()
                scaled = pm.scaled(
                    w, h,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # Center-crop
                x = max(0, (scaled.width() - w) // 2)
                y = max(0, (scaled.height() - h) // 2)
                cropped = scaled.copy(x, y, w, h)
                # Round the corners via a clip-path mask
                rounded = QPixmap(w, h)
                rounded.fill(Qt.GlobalColor.transparent)
                p = QPainter(rounded)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                path = QPainterPath()
                path.addRoundedRect(0, 0, w, h, 8, 8)
                p.setClipPath(path)
                p.drawPixmap(0, 0, cropped)
                p.end()
                self.thumb_lbl.setPixmap(rounded)
                self.thumb_lbl.setText("")
        except Exception:
            pass

    def _on_fetch_error(self, err):
        self.video_title_lbl.setText("Could not fetch video info")
        self.video_meta_lbl.setText(err)
        self._set_tags([])
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Retry")

    # ── Download flow ─────────────────────────────────────────────────────────
    def _build_yt_params(self, settings, safe_title):
        """Return (ydl_opts, folder, display_name) for the given settings."""
        mode          = settings.get("mode", "combined")
        quality       = settings.get("quality", "Best")
        audio_fmt     = settings.get("audio_fmt", "mp3")
        audio_quality = settings.get("audio_quality", "320")
        embed_subs    = bool(settings.get("embed_subs", False))
        embed_thumb   = bool(settings.get("embed_thumb", True))

        if mode == "audio":
            folder = os.path.join(HOME, "Downloads", "Music")
            os.makedirs(folder, exist_ok=True)
            display_name = f"{safe_title}.{audio_fmt}"
            postprocessors = []
            if audio_fmt == "m4a":
                # Prefer the native M4A audio stream so no re-encode happens.
                fmt_selector = 'bestaudio[ext=m4a]/bestaudio'
            else:
                fmt_selector = 'bestaudio/best'
                postprocessors.append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': audio_fmt,
                    'preferredquality': audio_quality,
                })
            if embed_thumb:
                postprocessors.append({'key': 'EmbedThumbnail'})
            ydl_opts = {
                'format':            fmt_selector,
                'outtmpl':           os.path.join(folder, f"{safe_title}.%(ext)s"),
                'paths':             {'temp': YT_DLP_TEMP_DIR},
                'postprocessors':    postprocessors,
                'writethumbnail':    embed_thumb,
                'quiet':             True,
                'no_warnings':       True,
                'http_headers':      {'User-Agent': HEADERS['User-Agent']},
            }
        else:
            folder = os.path.join(HOME, "Downloads", "Videos")
            os.makedirs(folder, exist_ok=True)
            display_name = f"{safe_title}.mp4"
            # Map the quality id (e.g. "1080p60") to a yt-dlp height filter.
            height = None
            for qid, _sub, _size, h in self.QUALITIES:
                if qid == quality:
                    height = h
                    break
            if quality == "Best" or height is None:
                fmt = "bestvideo+bestaudio/best"
            else:
                fmt = (
                    f"bestvideo[height<={height}]+bestaudio/"
                    f"bestvideo[height<={height}]/best"
                )
            postprocessors = []
            if embed_thumb:
                postprocessors.append({'key': 'EmbedThumbnail'})
            if embed_subs:
                postprocessors.append({'key': 'FFmpegEmbedSubtitle'})
            ydl_opts = {
                'format':              fmt,
                'outtmpl':             os.path.join(folder, f"{safe_title}.%(ext)s"),
                'paths':               {'temp': YT_DLP_TEMP_DIR},
                'merge_output_format': 'mp4',
                'postprocessors':      postprocessors,
                'writethumbnail':      embed_thumb,
                'writesubtitles':      embed_subs,
                'writeautomaticsub':   embed_subs,
                'subtitleslangs':      ['en'] if embed_subs else [],
                'quiet':               True,
                'no_warnings':         True,
                'http_headers':        {'User-Agent': HEADERS['User-Agent']},
            }
        return ydl_opts, folder, display_name

    def _current_settings(self):
        codec, kbps = self._audio_choice()
        return {
            "mode":          "audio" if self._mode == "audio" else "combined",
            "quality":       self._quality_id,
            "audio_fmt":     codec,
            "audio_quality": str(kbps) if kbps else "0",
            "embed_subs":    self.subs_chk.isChecked(),
            "embed_thumb":   self.thumb_chk.isChecked(),
        }

    def _kick_off(self, url, settings, safe_title):
        self._current_url = url
        self.download_btn.setVisible(False)
        self.fetch_btn.setEnabled(False)
        self.cancel_dl_btn.setVisible(True)
        self.cancel_dl_btn.setEnabled(True)
        self.progress.set_pct(0)
        self.progress.mark_active()
        self.log_box.clear()
        self._last_size = self._last_speed = self._last_eta = ""

        ydl_opts, folder, display_name = self._build_yt_params(settings, safe_title)
        self._dl_folder = folder
        self._dl_base   = safe_title
        self.open_file_btn.setVisible(False)
        self.open_folder_btn.setVisible(False)
        self.download_started.emit(url, display_name, folder)
        self.yt_settings_captured.emit(url, settings)
        self.dl_thread = YouTubeDownloadThread(url, ydl_opts)
        self.dl_thread.progress.connect(self._on_progress)
        self.dl_thread.speed.connect(self._on_speed)
        self.dl_thread.size_info.connect(self._on_size)
        self.dl_thread.eta.connect(self._on_eta)
        self.dl_thread.log.connect(lambda msg: self.log_box.append(msg))
        self.dl_thread.finished.connect(self.on_download_finished)
        self.dl_thread.start()
        self.log_box.append("Starting download\u2026")

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            return
        title = self.video_title or "video"
        safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', title)[:80].strip() or "video"
        self._kick_off(url, self._current_settings(), safe_title)

    def start_with_saved_settings(self, url, settings, safe_title):
        """Resume path: skip fetch, apply settings, start downloading."""
        self.url_input.setText(url)
        mode = settings.get("mode", "combined")
        self._select_format("audio" if mode == "audio" else "video")
        q = settings.get("quality", "1080p60")
        if q in self._quality_cards:
            self._select_quality(q)
        self.subs_chk.setChecked(bool(settings.get("embed_subs", False)))
        self.thumb_chk.setChecked(bool(settings.get("embed_thumb", True)))
        self.video_title = safe_title
        self.video_title_lbl.setText(f"Resuming: {safe_title}")
        self._kick_off(url, settings, safe_title)

    # ── Progress / completion ────────────────────────────────────────────────
    def _on_progress(self, pct):
        self.progress.set_pct(pct)
        self.download_progress.emit(
            self._current_url, pct, self._last_size, self._last_speed, self._last_eta,
        )

    def _on_speed(self, spd):
        self._last_speed = spd
        self.progress.set_speed_text(spd)
        self.download_progress.emit(
            self._current_url, self.progress.bar.value(),
            self._last_size, spd, self._last_eta,
        )

    def _on_size(self, sz):
        self._last_size = sz
        self.progress.set_size_text(sz)

    def _on_eta(self, eta):
        self._last_eta = eta
        self.progress.set_eta_text(eta if eta != "\u2014" else "")

    def cancel_download(self):
        if not self.dl_thread or not self.dl_thread.isRunning():
            return
        # Cooperative cancel: flag the worker, then let yt-dlp's next
        # progress hook raise out of the network loop. on_download_finished
        # ("Cancelled") will reset the UI when the thread exits.
        self.dl_thread.running = False
        self.cancel_dl_btn.setEnabled(False)
        self.cancel_dl_btn.setText("Cancelling\u2026")
        self.log_box.append("Cancelling download\u2026")
        self.progress.mark_error("Cancelling\u2026")

    def on_download_finished(self, msg):
        self.fetch_btn.setEnabled(True)
        self.cancel_dl_btn.setVisible(False)
        # Restore the Stop button to its default state for the next download.
        self.cancel_dl_btn.setEnabled(True)
        self.cancel_dl_btn.setText("Stop")
        if msg == "Finished":
            self.progress.mark_complete()
            self.log_box.append("Download complete!")
            self.download_btn.setVisible(False)
            self.open_file_btn.setVisible(True)
            self.open_folder_btn.setVisible(True)
        elif msg == "Cancelled":
            self.log_box.append("Download cancelled.")
            self.progress.mark_error("Cancelled")
            self.download_btn.setVisible(True)
        else:
            self.log_box.append(msg)
            self.progress.mark_error(msg[:80])
            self.download_btn.setVisible(True)
        self.download_finished.emit(self._current_url, msg)

    def _open_downloaded_file(self):
        import glob as _glob
        folder = getattr(self, '_dl_folder', '')
        base   = getattr(self, '_dl_base', '')
        if folder and base:
            matches = _glob.glob(os.path.join(folder, f"{base}.*"))
            if matches:
                subprocess.Popen(['xdg-open', matches[0]])
                self.close()
                return
        if folder:
            subprocess.Popen(['xdg-open', folder])
        self.close()

    def _open_downloaded_folder(self):
        folder = getattr(self, '_dl_folder', '')
        if folder and os.path.exists(folder):
            subprocess.Popen(['xdg-open', folder])
        self.close()


class LuluHLSDownloadThread(QThread):
    """Download a Luluvdo / Lulustream HLS video entirely via Python
    requests within one session, then mux locally with ffmpeg.

    Why not yt-dlp or ffmpeg's network: the Lulu CDN (*.tnmr.org) returns
    403 to ffmpeg, yt-dlp, and even fresh Python requests calls if there
    is too much delay or session reuse mismatch between resolving the
    page and fetching the manifest. Doing the embed-page fetch and the
    manifest/segment fetch back-to-back in the same requests.Session
    keeps the CDN happy. ffmpeg is only invoked at the end to remux the
    concatenated .ts file into .mp4 — no network involved."""

    progress  = pyqtSignal(int)
    speed     = pyqtSignal(str)
    size_info = pyqtSignal(str)
    eta       = pyqtSignal(str)
    log       = pyqtSignal(str)
    finished  = pyqtSignal(str)

    UA = ('Mozilla/5.0 (X11; Linux x86_64; rv:151.0) '
          'Gecko/20100101 Firefox/151.0')

    def __init__(self, page_url, output_path):
        super().__init__()
        self.page_url = page_url
        self.output_path = output_path
        self.running = True

    def _make_session(self):
        if _CURL_CFFI:
            return requests.Session(impersonate="firefox")
        s = requests.Session()
        s.headers.clear()
        s.headers.update({'User-Agent': self.UA})
        return s

    def _cdn_headers(self, base):
        return {
            'Referer':         base + '/',
            'Origin':          base,
            'Accept':          '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Dest':  'empty',
            'Sec-Fetch-Mode':  'cors',
            'Sec-Fetch-Site':  'cross-site',
        }

    def _resolve(self, session, base, vid):
        embed_url = f'{base}/e/{vid}'
        r = session.get(embed_url, headers={'Referer': base + '/'}, timeout=15)
        r.raise_for_status()
        pm = re.search(
            r"function\(p,a,c,k,e,d\)\{.*?\}\((.+\.split\('\|'\)\))\)",
            r.text, re.DOTALL,
        )
        if not pm:
            raise Exception("Player config not found on embed page")
        unp = _unpack_packed_js(pm.group(1))
        if not unp:
            raise Exception("Failed to decode packed JS")
        sm = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', unp)
        if not sm:
            raise Exception("No m3u8 URL in player config")
        return sm.group(1)

    def _select_variant(self, master_text, master_url):
        from urllib.parse import urljoin
        # Prefer highest BANDWIDTH; fall back to first non-comment line.
        best_url, best_bw = None, -1
        lines = master_text.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith('#EXT-X-STREAM-INF'):
                m = re.search(r'BANDWIDTH=(\d+)', ln)
                bw = int(m.group(1)) if m else 0
                # The URL is the next non-comment line
                for j in range(i + 1, len(lines)):
                    nxt = lines[j].strip()
                    if nxt and not nxt.startswith('#'):
                        if bw > best_bw:
                            best_bw, best_url = bw, urljoin(master_url, nxt)
                        break
        if best_url:
            return best_url
        # No variants — master is itself a media playlist
        return master_url

    def run(self):
        try:
            m = re.match(
                r'(https?://(?:luluvdo|lulustream)\.com)/(?:e/)?([A-Za-z0-9]+)',
                self.page_url,
            )
            if not m:
                raise Exception("Not a Luluvdo / Lulustream URL")
            base, vid = m.groups()
            session = self._make_session()
            cdn = self._cdn_headers(base)

            # 1) Resolve packed-JS → master.m3u8
            self.log.emit("Resolving stream URL...")
            master_url = self._resolve(session, base, vid)

            # 2) Fetch master playlist
            self.log.emit("Fetching master playlist...")
            r = session.get(master_url, headers=cdn, timeout=20)
            if r.status_code != 200:
                raise Exception(
                    f"Master playlist returned HTTP {r.status_code}"
                )
            master_text = r.text

            # 3) Pick best variant
            variant_url = self._select_variant(master_text, master_url)

            # 4) Fetch variant playlist (or treat master as media playlist)
            if variant_url != master_url:
                r = session.get(variant_url, headers=cdn, timeout=20)
                if r.status_code != 200:
                    raise Exception(
                        f"Variant playlist returned HTTP {r.status_code}"
                    )
                playlist_text = r.text
            else:
                playlist_text = master_text

            # 5) Parse segment URLs + encryption keys
            from urllib.parse import urljoin
            seg_entries = []  # (url, key_bytes_or_None, iv_bytes_or_None, seq)
            cur_key, cur_iv = None, None
            seq = 0
            for ln in playlist_text.splitlines():
                ln = ln.strip()
                if ln.startswith('#EXT-X-KEY'):
                    method_m = re.search(r'METHOD=([^,\s]+)', ln)
                    if method_m and method_m.group(1) == 'NONE':
                        cur_key, cur_iv = None, None
                    else:
                        uri_m = re.search(r'URI="([^"]+)"', ln)
                        iv_m  = re.search(r'IV=0x([0-9a-fA-F]+)', ln)
                        if uri_m:
                            key_r = session.get(uri_m.group(1), headers=cdn, timeout=10)
                            cur_key = key_r.content
                        cur_iv = bytes.fromhex(iv_m.group(1).zfill(32)) if iv_m else None
                elif ln and not ln.startswith('#'):
                    seg_entries.append((urljoin(variant_url, ln), cur_key, cur_iv, seq))
                    seq += 1

            if not seg_entries:
                raise Exception("No segments in playlist")
            encrypted = any(e[1] is not None for e in seg_entries)
            if encrypted and not _HAS_AES:
                raise Exception(
                    "Stream is AES-128 encrypted but pycryptodome is not installed. "
                    "Run:  pip install pycryptodome --break-system-packages"
                )
            self.log.emit(f"Downloading {len(seg_entries)} segments "
                          f"({'encrypted' if encrypted else 'plain'})...")

            # 6) Download + decrypt segments to a temp .ts file with progress
            tmp_ts = self.output_path + '.lulu.tmp.ts'
            total_bytes = 0
            t0 = time.time()
            with open(tmp_ts, 'wb') as fh:
                for i, (seg_url, seg_key, seg_iv, seg_seq) in enumerate(seg_entries):
                    if not self.running:
                        try: os.remove(tmp_ts)
                        except Exception: pass
                        self.finished.emit("Cancelled")
                        return
                    last_err = None
                    for attempt in range(5):
                        try:
                            r = session.get(seg_url, headers=cdn, timeout=30)
                            if r.status_code == 200:
                                last_err = None
                                break
                            last_err = f"HTTP {r.status_code}"
                        except Exception as exc:
                            last_err = str(exc)
                        if attempt < 4:
                            time.sleep(min(2 ** attempt, 8))
                    if last_err is not None:
                        raise Exception(
                            f"Segment {i+1}/{len(seg_entries)} failed "
                            f"after 5 attempts: {last_err}"
                        )
                    data = r.content
                    if seg_key is not None:
                        iv = seg_iv if seg_iv is not None else seg_seq.to_bytes(16, 'big')
                        data = _AES.new(seg_key, _AES.MODE_CBC, iv).decrypt(data)
                    fh.write(data)
                    total_bytes += len(data)
                    pct = int(100 * (i + 1) / len(seg_entries))
                    self.progress.emit(pct)
                    self.size_info.emit(format_size(total_bytes))
                    elapsed = max(time.time() - t0, 0.001)
                    bps = total_bytes / elapsed
                    self.speed.emit(f"{format_size(int(bps))}/s")
                    if i + 1 < len(seg_entries):
                        rem = (len(seg_entries) - (i + 1)) * (elapsed / (i + 1))
                        self.eta.emit(format_eta(int(rem)))
                    else:
                        self.eta.emit("—")

            # 7) Remux to MP4 via ffmpeg locally (no network)
            self.log.emit("Muxing to MP4...")
            try:
                subprocess.run(
                    ['ffmpeg', '-y', '-i', tmp_ts,
                     '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
                     self.output_path],
                    check=True, capture_output=True, timeout=300,
                )
                try: os.remove(tmp_ts)
                except Exception: pass
            except subprocess.CalledProcessError as e:
                err = (e.stderr or b'').decode('utf-8', 'replace').strip()
                self.log.emit(f"ffmpeg mux failed: {err[:200]}")
                # Even if mux fails, keep the .ts file as a fallback.
                if os.path.exists(tmp_ts):
                    os.replace(tmp_ts, self.output_path)

            self.progress.emit(100)
            self.finished.emit("Finished")

        except FileNotFoundError:
            self.finished.emit("Error: ffmpeg not installed")
        except Exception as e:
            if any(x in type(e).__module__ for x in ('requests', 'curl')):
                self.finished.emit(f"Error: network error — {str(e)[:120]}")
                return
        except Exception as e:
            self.finished.emit(f"Error: {str(e)[:160]}")



class DownloadThread(QThread):
    progress       = pyqtSignal(int)
    speed          = pyqtSignal(str)
    downloaded     = pyqtSignal(str)
    eta            = pyqtSignal(str)
    finished       = pyqtSignal(str)
    # Emitted when the worker locks in the final on-disk filename/path
    # (after Content-Disposition parsing, CT sniffing, and the second
    # uniqueness check).  The row started with an enqueue-time guess;
    # this signal lets the UI sync display name, icon, and stored path
    # so Open File / Show in Folder / Resume use the truth.
    name_finalized = pyqtSignal(str, str)  # filename, full_path

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
                'paths': {'temp': YT_DLP_TEMP_DIR},
                'restrictfilenames': False,
                'progress_hooks': [self.yt_dlp_hook],
                'no_warnings': False,
                'ignoreerrors': False,
                'http_headers': {'User-Agent': HEADERS['User-Agent']},
                'nocheckcertificate': True,
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
            if is_gofile_url(self.url):
                token = get_gofile_token(gofile_content_id(self.url))
                if token:
                    cmd += ["-b", f"accountToken={token}"]
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
            if is_gofile_url(self.url):
                token = get_gofile_token(gofile_content_id(self.url))
                if token:
                    try:
                        session.cookies.set("accountToken", token, domain=".gofile.io")
                    except Exception:
                        session.headers["Cookie"] = (
                            (session.headers.get("Cookie", "") + "; " if session.headers.get("Cookie") else "")
                            + f"accountToken={token}"
                        )
                else:
                    reason = _GOFILE_LAST_ERR or "unknown"
                    self.finished.emit(
                        f"Error: Gofile auth failed — {reason}"
                    )
                    return
            try:
                head = session.head(self.url, allow_redirects=True, timeout=10, verify=False)
                # If the server hands us an HTML page for what should be a
                # binary file, auth failed (e.g. Gofile token not authorized
                # for this content). Bail instead of saving an 11KB landing
                # page as `.mp4`.
                _ct_head = head.headers.get("Content-Type", "").split(";")[0].strip().lower()
                _url_ext = os.path.splitext(urlparse(self.url).path)[1].lower()
                if _ct_head in ("text/html", "application/xhtml+xml") and _url_ext not in (".html", ".htm"):
                    detail = (
                        f" [{_GOFILE_LAST_ERR}]"
                        if is_gofile_url(self.url) and _GOFILE_LAST_ERR
                        else ""
                    )
                    self.finished.emit(
                        f"Error: server returned HTML, not the file{detail}"
                    )
                    return
                cd = head.headers.get("Content-Disposition", "")
                # `filename*=` (RFC 5987) does not contain the substring
                # "filename=", so a plain `in` check would skip it. Match on
                # the bare token instead and let the regexes pick the form.
                if "filename" in cd.lower():
                    m = re.search(r"filename\*\s*=\s*[\w-]+'[^']*'([^;\r\n]+)", cd, re.I)
                    if m:
                        self.filename = unquote(m.group(1).strip())
                    else:
                        m = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.I)
                        if not m:
                            m = re.search(r"filename\s*=\s*([^;\s\"']+)", cd, re.I)
                        if m:
                            candidate = m.group(1).strip().strip("'\"")
                            if candidate.lower() not in ("utf-8", "utf8", "ascii", "iso-8859-1"):
                                self.filename = candidate
                # Captured "UTF-8" from a broken Content-Disposition parser
                # upstream — derive the real name from the URL path instead.
                if self.filename.strip().lower() in ("utf-8", "utf8", "ascii", "iso-8859-1"):
                    url_name = unquote(urlparse(self.url).path.rsplit("/", 1)[-1])
                    if url_name:
                        self.filename = url_name
                # Fix 6: Some servers put the real filename in a ?name= query
                # parameter (e.g. upfiles.download) rather than Content-Disposition.
                # Only use it when our current filename still has no extension.
                if not os.path.splitext(self.filename)[1]:
                    try:
                        qs_name = parse_qs(urlparse(self.url).query).get("name", [None])[0]
                        if qs_name and os.path.splitext(qs_name)[1]:
                            self.filename = qs_name
                    except Exception:
                        pass
                # Fix 7: If the filename STILL has no extension, sniff from
                # Content-Type.  Handles opaque force-download tokens (krakencloud
                # etc.) where the URL path is a hash with no extension at all.
                # application/octet-stream defaults to .mp4 only for video CDNs;
                # real binary types like zip are already caught by Content-Disposition.
                if not os.path.splitext(self.filename)[1]:
                    ct = head.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    _ct_ext = {
                        "video/mp4": ".mp4", "video/webm": ".webm",
                        "video/x-matroska": ".mkv", "video/x-msvideo": ".avi",
                        "video/quicktime": ".mov", "video/x-flv": ".flv",
                        "video/mp2t": ".ts", "video/m4v": ".m4v",
                        "application/zip": ".zip",
                        "application/x-zip-compressed": ".zip",
                        "application/x-rar-compressed": ".rar",
                        "application/x-7z-compressed": ".7z",
                        "application/x-tar": ".tar",
                        "application/gzip": ".gz",
                        "application/pdf": ".pdf",
                        "application/vnd.android.package-archive": ".apk",
                        "application/octet-stream": ".mp4",   # last-resort for video CDNs
                    }
                    ext = _ct_ext.get(ct, "")
                    if not ext and ct.startswith("video/"):
                        ext = ".mp4"
                    if ext:
                        self.filename += ext
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
            # Re-run uniqueness check here — the Content-Disposition block
            # above may have reset self.filename to the server's original
            # name, discarding any (1)/(2) suffix computed before the thread
            # started.  We must guarantee a unique path before opening the
            # file for writing.
            if self.resume_from == 0:
                _ub, _ue = os.path.splitext(self.filename)
                _un, _uc = self.filename, 1
                while os.path.exists(os.path.join(folder, _un)):
                    _un = f"{_ub} ({_uc}){_ue}"
                    _uc += 1
                self.filename = _un
            filepath = os.path.join(folder, self.filename)
            # Tell the UI the authoritative on-disk filename so the row,
            # icon, and stored path match what we're about to write.  Must
            # fire before the first byte hits disk; otherwise Open File /
            # Show in Folder / clear_item all act on the stale enqueue-time
            # path.
            try:
                self.name_finalized.emit(self.filename, filepath)
            except Exception:
                pass
            # Some CDNs cap concurrent connections per-IP and reject the
            # second handshake with SSL EOF. Retry with backoff so a queued
            # download just waits for a slot instead of hard-failing.
            MAX_ATTEMPTS = 60
            RETRY_DELAY  = 5
            current_resume = self.resume_from
            attempt = 0
            while True:
                attempt += 1
                if current_resume > 0:
                    session.headers["Range"] = f"bytes={current_resume}-"
                    mode = "ab"
                else:
                    session.headers.pop("Range", None)
                    mode = "wb"
                downloaded_bytes = current_resume
                try:
                    # curl_cffi Response has no __enter__/__exit__, so
                    # `with session.get(...) as r` crashes immediately.
                    # Plain assignment + try/finally works for both libraries.
                    r = session.get(self.url, stream=True, allow_redirects=True, timeout=30, verify=False)
                    try:
                        if current_resume > 0 and r.status_code == 416:
                            # Range not satisfiable — file already complete
                            self.finished.emit("Finished")
                            return
                        if r.status_code not in (200, 206):
                            r.raise_for_status()
                        total_from_header = int(r.headers.get("content-length", 0) or 0)
                        total = total_from_header + current_resume if total_from_header > 0 else 0
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
                                        downloaded_since_start = downloaded_bytes - current_resume
                                        if elapsed > 0 and downloaded_since_start > 0:
                                            rate = downloaded_since_start / elapsed
                                            remaining_bytes = total - downloaded_bytes
                                            self.eta.emit(format_eta(remaining_bytes / rate))
                                    else:
                                        self.downloaded.emit(format_size(downloaded_bytes))
                                        self.eta.emit("—")
                                    elapsed = time.time() - start_time
                                    downloaded_since_start = downloaded_bytes - current_resume
                                    if elapsed > 0:
                                        spd = downloaded_since_start / elapsed
                                        if spd >= 1024 * 1024:
                                            self.speed.emit(f"{spd / (1024 * 1024):.2f} MB/s")
                                        else:
                                            self.speed.emit(f"{spd / 1024:.1f} KB/s")
                    finally:
                        try:
                            r.close()
                        except Exception:
                            pass
                    break  # full stream consumed without error
                except (requests.exceptions.SSLError,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.ChunkedEncodingError) as e:
                    if not self.running:
                        self.finished.emit("Cancelled")
                        return
                    if attempt >= MAX_ATTEMPTS:
                        raise
                    # Pick up where we left off on the next attempt.
                    current_resume = downloaded_bytes
                    self.eta.emit(f"Waiting for slot (retry {attempt})")
                    self.speed.emit("—")
                    for _ in range(RETRY_DELAY):
                        if not self.running:
                            self.finished.emit("Cancelled")
                            return
                        time.sleep(1)
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




# ── Core downloader dialog ────────────────────────────────────────────────────
class CoreDownloaderDialog(DownloaderDialogBase):
    """Non-modal dialog for direct file downloads (zip, exe, pdf, etc.).
    Uses DownloadThread (requests/curl) — not yt-dlp."""

    download_started  = pyqtSignal(str, str, str)            # url, display_name, folder
    download_progress = pyqtSignal(str, int, str, str, str)  # url, pct, size, speed, eta
    download_finished = pyqtSignal(str, str)                 # url, status

    def __init__(self, parent=None, url="", filename="", referer="", dark=True):
        super().__init__(parent, dark=dark, window_title="LDM Core Downloader")
        self._url       = url
        self._filename  = filename
        self._referer   = referer
        self._dl_path   = ""
        self._save_dir  = choose_folder(filename) if filename else os.path.join(HOME, "Downloads")
        self._user_dir_override = False
        self.dl_thread  = None
        self._last_size = ""
        self._last_speed = ""
        self._last_eta  = ""

        self.resize(680, 520)
        self.setMinimumSize(580, 460)
        self._build_body()
        self._wire_footer()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_body(self):
        t = self.theme

        # Hero band — blue/HTTP for the Core engine.
        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets", "toolbar_icons", "core.svg",
        )
        hero = _make_hero_band(
            self.body, self.dark, icon_path,
            title="Core Downloader",
            subtitle="Multi-segment HTTP / HTTPS / FTP downloads.",
            chip_label="HTTP",
            accent_color="#1d4ed8",
            accent_soft=("rgba(59,130,246,0.16)" if self.dark else "rgba(59,130,246,0.10)"),
        )
        self.body_layout.addWidget(hero)

        content = QWidget()
        content.setStyleSheet(f"background: {t['surface']};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(22, 16, 22, 16)
        cl.setSpacing(10)

        # URL row — read-only field with a tinted link icon on the left.
        cl.addLayout(self._field_label("URL"))
        cl.addWidget(self._url_field(self._url, tone="blue"))

        # Save as + Category (two columns).
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        save_as_col = QVBoxLayout()
        save_as_col.setSpacing(6)
        save_as_col.addLayout(self._field_label("Save as"))
        self.filename_edit = QLineEdit(self._filename)
        self.filename_edit.setStyleSheet(_dialog_input_qss(t))
        self.filename_edit.textChanged.connect(self._on_filename_changed)
        save_as_col.addWidget(self.filename_edit)
        row1.addLayout(save_as_col, 16)

        cat_col = QVBoxLayout()
        cat_col.setSpacing(6)
        cat_col.addLayout(self._field_label("Category"))
        self.category_combo = QComboBox()
        # Skip "All Downloads" — it's not a real folder. Items get their per-
        # category SVG icon (assets/category_icons/) so the dropdown rows show
        # a proper icon instead of the OS-dependent emoji glyph.
        for label, _emoji, _color in CATEGORIES[1:]:
            icon_file = CATEGORY_ICON_FILE.get(label)
            if icon_file:
                icon_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "assets", "category_icons", icon_file,
                )
                if os.path.exists(icon_path):
                    self.category_combo.addItem(
                        QIcon(_render_svg_pixmap(icon_path, 18)),
                        f"  {label}", label,
                    )
                    continue
            self.category_combo.addItem(label, label)
        current_cat = get_category(self._filename) if self._filename else "Others"
        idx = self.category_combo.findData(current_cat)
        if idx >= 0:
            self.category_combo.setCurrentIndex(idx)
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        cat_col.addWidget(self._category_field(self.category_combo, tone="blue"))
        row1.addLayout(cat_col, 10)

        cl.addLayout(row1)

        # Save in — folder tile + path + Browse, matching the URL tile style.
        cl.addLayout(self._field_label("Save in"))
        self.save_dir_edit = QLineEdit(self._save_dir)
        self.save_dir_edit.textEdited.connect(lambda _t: setattr(self, "_user_dir_override", True))
        cl.addWidget(self._dir_field(self.save_dir_edit, tone="blue"))

        # Progress section.
        self.progress = ProgressSection(content, dark=self.dark)
        self.progress.mark_idle()
        cl.addWidget(self.progress)
        cl.addStretch(1)

        self.body_layout.addWidget(content, 1)

    def _wire_footer(self):
        t = self.theme
        self.footer_layout.addStretch(1)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(_dialog_btn_qss(t, "secondary"))
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.footer_layout.addWidget(self.cancel_btn)

        self.primary_btn = QPushButton("Download")
        self.primary_btn.setStyleSheet(_dialog_btn_qss(t, "primaryGreen"))
        self.primary_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_btn.clicked.connect(self._on_primary_clicked)
        self.footer_layout.addWidget(self.primary_btn)

        # Post-finish buttons — hidden until the download succeeds, mirroring
        # the Stream / YouTube dialogs.
        self.open_file_btn = QPushButton("Open File")
        self.open_file_btn.setStyleSheet(_dialog_btn_qss(t, "primaryBlue"))
        self.open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_file_btn.clicked.connect(self._open_downloaded_file)
        self.open_file_btn.setVisible(False)
        self.footer_layout.addWidget(self.open_file_btn)

        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setStyleSheet(_dialog_btn_qss(t, "secondary"))
        self.open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_folder_btn.clicked.connect(self._open_downloaded_folder)
        self.open_folder_btn.setVisible(False)
        self.footer_layout.addWidget(self.open_folder_btn)

    def _field_label(self, text):
        t = self.theme
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"font-family: {PLEX_SANS}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 0.8px; color: {t['muted']}; background: transparent;"
        )
        layout.addWidget(lbl)
        layout.addStretch()
        return layout

    def _url_field(self, value, tone="blue"):
        t = self.theme
        tone_color = {"blue": "#3b82f6", "violet": "#8b5cf6", "red": "#ef4444"}[tone]
        sel_rgb = (
            "rgba(59,130,246,0.35)"  if tone == "blue"  else
            "rgba(139,92,246,0.35)"  if tone == "violet" else
            "rgba(239,68,68,0.35)"
        )
        frame = QFrame()
        frame.setStyleSheet(
            f"background: {t['input_bg']}; border: 1px solid {t['border']}; "
            f"border-radius: 10px;"
        )
        h = QHBoxLayout(frame)
        h.setContentsMargins(10, 8, 12, 8)
        h.setSpacing(12)
        h.addWidget(_make_glyph_tile(_TILE_SVG_LINK, tone_color, self.dark))

        edit = QLineEdit(value)
        edit.setReadOnly(True)
        edit.setCursorPosition(0)
        edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; "
            f"color: {t['text']}; font-family: {PLEX_SANS}; font-size: 13.5px; "
            f"selection-background-color: {sel_rgb}; selection-color: {t['text']}; }}"
        )
        h.addWidget(edit, 1)
        return frame

    def _category_field(self, combo, tone="blue"):
        """Wrap the category QComboBox in a tile-styled frame, mirroring the
        URL row — a tinted 4-square 'category' glyph on the left, the combo
        in the middle (transparent), and a real SVG chevron button on the
        right (Qt's CSS-triangle chevron renders inconsistently)."""
        t = self.theme
        tone_color = {"blue": "#3b82f6", "violet": "#8b5cf6", "red": "#ef4444"}[tone]
        frame = QFrame()
        frame.setStyleSheet(
            f"background: {t['input_bg']}; border: 1px solid {t['border']}; "
            f"border-radius: 10px;"
        )
        h = QHBoxLayout(frame)
        h.setContentsMargins(10, 6, 6, 6)
        h.setSpacing(10)
        h.addWidget(_make_glyph_tile(_TILE_SVG_CATEGORY, tone_color, self.dark))

        # Transparent combo + themed popup. Hide the native drop-down arrow
        # entirely — we draw our own chevron button to the right.
        combo.setStyleSheet(_dialog_combo_inline_qss(t, tone_color, hide_arrow=True))
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        _style_combo_popup(combo, t, tone_color)
        h.addWidget(combo, 1)

        chevron = QPushButton()
        chevron.setCursor(Qt.CursorShape.PointingHandCursor)
        chevron.setFlat(True)
        chevron.setFixedSize(28, 28)
        chevron.setIcon(QIcon(_render_svg_str_pixmap(
            _TILE_SVG_CHEVRON_DOWN, tone_color, size=18
        )))
        chevron.setIconSize(QSize(18, 18))
        chevron.setStyleSheet(
            "QPushButton { background: transparent; border: none; padding: 0; }"
            f" QPushButton:hover {{ background: rgba("
            f"{int(tone_color[1:3], 16)},{int(tone_color[3:5], 16)},"
            f"{int(tone_color[5:7], 16)},0.12); border-radius: 6px; }}"
        )
        chevron.clicked.connect(combo.showPopup)
        h.addWidget(chevron)
        return frame

    def _pick_dir(self, line_edit):
        start = line_edit.text().strip() or os.path.join(HOME, "Downloads")
        chosen = QFileDialog.getExistingDirectory(self, "Save in", start)
        if chosen:
            line_edit.setText(chosen)
            self._user_dir_override = True

    def _dir_field(self, line_edit, tone="blue", browse_label="Browse\u2026"):
        """Same tile-styled wrapper as StreamDialog._dir_field, scoped to the
        Core (blue) accent.  We keep this duplicated rather than inheriting
        because the two dialogs don't share a useful UI base."""
        t = self.theme
        tone_color = {"blue": "#3b82f6", "violet": "#8b5cf6", "red": "#ef4444"}[tone]
        hover_bg = (
            "rgba(59,130,246,0.10)"  if tone == "blue"  else
            "rgba(139,92,246,0.10)"  if tone == "violet" else
            "rgba(239,68,68,0.10)"
        )
        sel_rgb = (
            "rgba(59,130,246,0.35)"  if tone == "blue"  else
            "rgba(139,92,246,0.35)"  if tone == "violet" else
            "rgba(239,68,68,0.35)"
        )
        frame = QFrame()
        frame.setStyleSheet(
            f"background: {t['input_bg']}; border: 1px solid {t['border']}; "
            f"border-radius: 10px;"
        )
        h = QHBoxLayout(frame)
        h.setContentsMargins(10, 8, 8, 8); h.setSpacing(10)
        h.addWidget(_make_glyph_tile(_TILE_SVG_FOLDER, tone_color, self.dark))

        line_edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {t['text']}; "
            f"font-family: {PLEX_SANS}; font-size: 13.5px; "
            f"selection-background-color: {sel_rgb}; "
            f"selection-color: {t['text']}; }}"
        )
        h.addWidget(line_edit, 1)

        browse = QPushButton(browse_label)
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setStyleSheet(
            f"QPushButton {{ background: {t['card']}; color: {t['text']}; "
            f"border: 1px solid {t['border']}; border-radius: 7px; "
            f"padding: 4px 10px; font-family: {PLEX_SANS}; font-size: 12px; "
            f"font-weight: 600; }} "
            f"QPushButton:hover {{ background: {hover_bg}; "
            f"border-color: {tone_color}; color: {tone_color}; }}"
        )
        browse.clicked.connect(lambda: self._pick_dir(line_edit))
        h.addWidget(browse)
        return frame

    # ── Behaviour ─────────────────────────────────────────────────────────────
    def _on_filename_changed(self, text):
        if self._state() == "idle" and not self._user_dir_override:
            auto = choose_folder(text)
            self._save_dir = auto
            self.save_dir_edit.setText(auto)
            # Sync category dropdown to the detected one for the new filename.
            cat = get_category(text)
            idx = self.category_combo.findData(cat)
            if idx >= 0 and idx != self.category_combo.currentIndex():
                # Block recursion: changing the combo would otherwise re-call us.
                self.category_combo.blockSignals(True)
                self.category_combo.setCurrentIndex(idx)
                self.category_combo.blockSignals(False)

    def _on_category_changed(self, _idx):
        if self._state() != "idle" or self._user_dir_override:
            return
        chosen = self.category_combo.currentData()
        if chosen:
            new_dir = os.path.join(HOME, "Downloads", chosen)
            self._save_dir = new_dir
            self.save_dir_edit.setText(new_dir)

    def _on_browse(self):
        start = self.save_dir_edit.text().strip() or os.path.join(HOME, "Downloads")
        chosen = QFileDialog.getExistingDirectory(self, "Save in", start)
        if chosen:
            self.save_dir_edit.setText(chosen)
            self._user_dir_override = True

    def _state(self):
        """idle | active | complete | error — mirrors progress section state."""
        return self.progress._state if hasattr(self, "progress") else "idle"

    def _on_primary_clicked(self):
        state = self._state()
        if state == "complete":
            self._open_folder()
        elif state == "idle":
            self._start_download()

    def _on_cancel_clicked(self):
        state = self._state()
        if state in ("downloading",):
            resp = QMessageBox.question(
                self, "Cancel download?",
                "Cancel this download? The partial file will be deleted.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
            if self.dl_thread and self.dl_thread.isRunning():
                self.dl_thread.stop()
            if self._dl_path and os.path.exists(self._dl_path):
                try:
                    os.remove(self._dl_path)
                except OSError:
                    pass
        self.close()

    def _start_download(self):
        filename = self.filename_edit.text().strip() or self._filename
        folder = self.save_dir_edit.text().strip() or self._save_dir
        os.makedirs(folder, exist_ok=True)

        base, ext = os.path.splitext(filename)
        unique_name, counter = filename, 1
        while os.path.exists(os.path.join(folder, unique_name)):
            unique_name = f"{base} ({counter}){ext}"
            counter += 1

        self._dl_path = os.path.join(folder, unique_name)
        self._display_name = unique_name
        self.progress.mark_active()
        self.primary_btn.setEnabled(False)

        self.download_started.emit(self._url, unique_name, folder)

        self.dl_thread = DownloadThread(self._url, unique_name, is_video=False, referer=self._referer)
        self.dl_thread.progress.connect(self._on_progress)
        self.dl_thread.speed.connect(self._on_speed)
        self.dl_thread.downloaded.connect(self._on_downloaded)
        self.dl_thread.eta.connect(self._on_eta)
        self.dl_thread.finished.connect(self._on_finished)
        self.dl_thread.start()

    def _on_progress(self, pct):
        self.progress.set_pct(pct)
        self.download_progress.emit(
            self._url, pct, self._last_size, self._last_speed, self._last_eta,
        )

    def _on_speed(self, s):
        self._last_speed = s
        self.progress.set_speed_text(s)

    def _on_downloaded(self, s):
        self._last_size = s
        self.progress.set_size_text(s)

    def _on_eta(self, s):
        self._last_eta = s
        self.progress.set_eta_text(s)

    def _on_finished(self, msg):
        if msg == "Finished":
            self.progress.mark_complete()
            # Swap the in-flight footer (Cancel / Download) for the post-finish
            # pair (Open Folder / Open File), matching Stream + YouTube.
            self.cancel_btn.setVisible(False)
            self.primary_btn.setVisible(False)
            self.open_folder_btn.setVisible(True)
            self.open_file_btn.setVisible(True)
        else:
            self.progress.mark_error(f"Status: {msg}")
            self.primary_btn.setText("Retry")
            self.primary_btn.setStyleSheet(_dialog_btn_qss(self.theme, "primaryGreen"))
            self.primary_btn.setEnabled(True)
            self.primary_btn.clicked.disconnect()
            self.primary_btn.clicked.connect(self._retry)
        self.download_finished.emit(self._url, msg)

    def _retry(self):
        # Reset progress state and reconnect the primary button to start.
        self.progress.mark_idle()
        self.primary_btn.setText("Download")
        self.primary_btn.setStyleSheet(_dialog_btn_qss(self.theme, "primaryGreen"))
        self.primary_btn.clicked.disconnect()
        self.primary_btn.clicked.connect(self._on_primary_clicked)
        self._start_download()

    def _open_folder(self):
        folder = os.path.dirname(self._dl_path) if self._dl_path else self.save_dir_edit.text().strip()
        if folder and os.path.exists(folder):
            subprocess.Popen(['xdg-open', folder])
        self.close()

    def _open_downloaded_file(self):
        path = getattr(self, '_dl_path', '')
        if path and os.path.exists(path):
            subprocess.Popen(['xdg-open', path])
        elif path:
            subprocess.Popen(['xdg-open', os.path.dirname(path)])
        self.close()

    def _open_downloaded_folder(self):
        path = getattr(self, '_dl_path', '')
        folder = os.path.dirname(path) if path else self.save_dir_edit.text().strip()
        if folder and os.path.exists(folder):
            subprocess.Popen(['xdg-open', folder])
        self.close()


# ── Variant C sidebar hero card ──────────────────────────────────────────────
class _HeroBarColumn(QWidget):
    """One clickable day-column in the hero card's 7-bar week chart."""
    def __init__(self, hero, idx):
        super().__init__(hero)
        self._hero = hero
        self._idx = idx
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(58)  # bar(42) + gap(4) + label(~12)
        self.setMinimumWidth(16)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._hero.set_selected(self._idx)
        super().mousePressEvent(ev)

    def paintEvent(self, ev):
        from PyQt6.QtGui import QFont as _QFont
        day = self._hero._days[self._idx] if self._idx < len(self._hero._days) else None
        if day is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        bar_area_h = 42
        gap = 4
        label_h = h - bar_area_h - gap
        is_sel = (self._idx == self._hero._selected_idx)
        is_today = day["is_today"]
        # Column background tint when selected
        if is_sel:
            col_path = QPainterPath()
            col_path.addRoundedRect(QRectF(0, 0, w, bar_area_h + gap + label_h), 6, 6)
            p.fillPath(col_path, QColor(96, 165, 250, int(0.12 * 255)))
        # Bar geometry
        v = max(0.0, min(1.0, float(day.get("v", 0.0))))
        bar_h = max(3, int(round(bar_area_h * v))) if v > 0 else 3
        bar_w = max(6, w - 6)
        bar_x = (w - bar_w) // 2
        bar_y = bar_area_h - bar_h
        bar_rect = QRectF(bar_x, bar_y, bar_w, bar_h)
        bar_path = QPainterPath()
        bar_path.addRoundedRect(bar_rect, 2, 2)
        if is_sel:
            grad = QLinearGradient(0, bar_y, 0, bar_y + bar_h)
            grad.setColorAt(0.0, QColor("#60a5fa"))
            grad.setColorAt(1.0, QColor("#2563eb"))
            # Glow
            for i, alpha in ((4, 30), (2, 70)):
                glow = QPainterPath()
                glow.addRoundedRect(bar_rect.adjusted(-i, -i, i, i), 4, 4)
                p.fillPath(glow, QColor(59, 130, 246, alpha))
            p.fillPath(bar_path, QBrush(grad))
        elif is_today:
            p.fillPath(bar_path, QColor(96, 165, 250, int(0.45 * 255)))
        else:
            p.fillPath(bar_path, QColor(255, 255, 255, int(0.18 * 255)))
        # Day label
        if is_sel:
            label_color = QColor("#60a5fa")
            weight = QFont.Weight.ExtraBold
        elif is_today:
            label_color = QColor("#cbd5e1")
            weight = QFont.Weight.Medium
        else:
            label_color = QColor("#64748b")
            weight = QFont.Weight.Medium
        font = _QFont(self._hero._font_family)
        font.setPointSizeF(7.5)
        font.setWeight(weight)
        p.setFont(font)
        p.setPen(label_color)
        from PyQt6.QtCore import QRectF as _QRectF
        p.drawText(_QRectF(0, bar_area_h + gap, w, label_h),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                   day["label"])
        p.end()


class _SidebarHeroCard(QWidget):
    """Variant C dashboard hero card: gradient bg + orb + day stats + week chart."""
    def __init__(self, parent=None, font_family="IBM Plex Sans", mono_family="IBM Plex Mono",
                 bolt_svg_path=None):
        super().__init__(parent)
        self.setObjectName("heroCard")
        self._font_family = font_family
        self._mono_family = mono_family
        self._bolt_path = bolt_svg_path
        self._days = []
        self._selected_idx = 6
        self.setMinimumHeight(220)
        self._build()

    def _build(self):
        from PyQt6.QtWidgets import QGridLayout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 14)
        outer.setSpacing(0)

        # Header: bolt + day label + date
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(6)
        self._bolt_lbl = QLabel()
        self._bolt_lbl.setFixedSize(12, 12)
        self._bolt_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if self._bolt_path and os.path.exists(self._bolt_path):
            try:
                self._bolt_lbl.setPixmap(_render_svg_pixmap(self._bolt_path, 12))
            except Exception:
                pass
        hdr.addWidget(self._bolt_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        self._day_lbl = QLabel("TODAY")
        self._day_lbl.setStyleSheet(
            f"color:#cbd5e1; font-family:'{self._font_family}'; font-size:10px;"
            "font-weight:800; letter-spacing:1.2px; background:transparent;"
        )
        hdr.addWidget(self._day_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        hdr.addStretch()
        self._date_lbl = QLabel("")
        self._date_lbl.setStyleSheet(
            f"color:#64748b; font-family:'{self._mono_family}'; font-size:10px;"
            "background:transparent;"
        )
        hdr.addWidget(self._date_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(hdr)
        outer.addSpacing(10)

        # Big number
        self._big_lbl = QLabel("0.00")
        self._big_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._big_lbl.setStyleSheet("background:transparent;")
        outer.addWidget(self._big_lbl)
        outer.addSpacing(12)

        # 3-stat grid
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(5)
        self._stat_cells = []
        self._stat_value_lbls = []
        for label_text in ("FILES", "ACTIVE", "UPTIME"):
            cell = QWidget()
            cell.setObjectName("heroStatCell")
            cell.setStyleSheet("""
                QWidget#heroStatCell {
                    background: rgba(255,255,255,0.06);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 8px;
                }
            """)
            cv = QVBoxLayout(cell)
            cv.setContentsMargins(3, 7, 3, 7)
            cv.setSpacing(2)
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color:#94a3b8; font-family:'{self._font_family}'; font-size:8px;"
                "font-weight:700; letter-spacing:0.8px; background:transparent;"
                "border: none;"
            )
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                f"color:#f1f5f9; font-family:'{self._mono_family}'; font-size:11px;"
                "font-weight:700; background:transparent; border:none;"
            )
            cv.addWidget(lbl)
            cv.addWidget(val)
            stats_row.addWidget(cell, 1)
            self._stat_cells.append(cell)
            self._stat_value_lbls.append(val)
        outer.addLayout(stats_row)
        outer.addSpacing(12)

        # 7-bar chart
        chart_row = QHBoxLayout()
        chart_row.setContentsMargins(0, 0, 0, 0)
        chart_row.setSpacing(4)
        self._bars = []
        for i in range(7):
            col = _HeroBarColumn(self, i)
            chart_row.addWidget(col, 1)
            self._bars.append(col)
        outer.addLayout(chart_row)

    def set_data(self, days, selected_idx=None):
        """days: list of 7 dicts. Selected resets to today when bounds shift."""
        self._days = days
        if selected_idx is not None:
            self._selected_idx = max(0, min(6, selected_idx))
        elif self._selected_idx >= len(days):
            self._selected_idx = len(days) - 1
        self._refresh()

    def set_selected(self, idx):
        if 0 <= idx < len(self._days):
            self._selected_idx = idx
            self._refresh()

    def _refresh(self):
        if not self._days:
            return
        d = self._days[self._selected_idx]
        # Header
        if d["is_today"]:
            self._day_lbl.setText("TODAY")
            self._date_lbl.setText("")
        else:
            self._day_lbl.setText(d["weekday_full"].upper())
            self._date_lbl.setText(d["date_str"])
        # Big number
        gb = d["gb"]
        self._big_lbl.setText(
            f"<span style=\"font-family:'{self._font_family}';font-size:28px;font-weight:800;color:#ffffff;letter-spacing:-1px;\">{gb:.2f}</span>"
            f"<span style=\"font-family:'{self._font_family}';font-size:13px;color:#94a3b8;\">&nbsp;GB</span>"
            f"<span style=\"font-family:'{self._font_family}';font-size:11px;color:#94a3b8;\">&nbsp;downloaded</span>"
        )
        # 3-stat values
        files_val, active_val, uptime_val = d["files_text"], d["active_text"], d["uptime_text"]
        active_color = "#22c55e" if d.get("active_nonzero") else "#f1f5f9"
        self._stat_value_lbls[0].setStyleSheet(
            f"color:#f1f5f9; font-family:'{self._mono_family}'; font-size:11px;"
            "font-weight:700; background:transparent; border:none;"
        )
        self._stat_value_lbls[0].setText(files_val)
        self._stat_value_lbls[1].setStyleSheet(
            f"color:{active_color}; font-family:'{self._mono_family}'; font-size:11px;"
            "font-weight:700; background:transparent; border:none;"
        )
        self._stat_value_lbls[1].setText(active_val)
        self._stat_value_lbls[2].setStyleSheet(
            f"color:#f1f5f9; font-family:'{self._mono_family}'; font-size:11px;"
            "font-weight:700; background:transparent; border:none;"
        )
        self._stat_value_lbls[2].setText(uptime_val)
        # Repaint chart
        for b in self._bars:
            b.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect()
        path = QPainterPath()
        path.addRoundedRect(QRectF(r), 14, 14)
        p.setClipPath(path)
        grad = QLinearGradient(QPointF(r.left(), r.top()), QPointF(r.right(), r.bottom()))
        grad.setColorAt(0.0, QColor("#1e3a8a"))
        grad.setColorAt(0.70, QColor("#0f172a"))
        grad.setColorAt(1.0, QColor("#0f172a"))
        p.fillPath(path, QBrush(grad))
        # Decorative orb: right:-30, top:-30, 100x100
        cx = r.width() - 30 + 50
        cy = -30 + 50
        orb = QRadialGradient(QPointF(cx, cy), 50)
        orb.setColorAt(0.0, QColor(59, 130, 246, int(0.30 * 255)))
        orb.setColorAt(0.70, QColor(59, 130, 246, 0))
        orb.setColorAt(1.0, QColor(59, 130, 246, 0))
        p.setBrush(QBrush(orb))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 50, 50)
        p.end()


# ── Main window ──────────────────────────────────────────────────────────────
class DownloadManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle("Linux Download Manager")
        self.resize(1200, 680)
        self.recent_urls = {}
        self.finished_urls = {}
        self.all_rows = []
        self.row_progress = {}
        self.yt_url_to_row = {}
        self.history = load_history()
        self._session_start = time.time()
        # URL → {mode, quality, audio_fmt} for YT resume without re-fetching formats
        self.yt_settings = {e["url"]: e["yt_settings"] for e in self.history
                            if e.get("url") and e.get("yt_settings")}
        self._settings = load_settings()
        self.dark_mode = self._settings.get("dark_mode", False)
        self.notify_enabled = self._settings.get("notifications", True)
        # Session-only: deliberately not persisted so a forgotten toggle can't
        # unexpectedly power off the machine on a later launch.
        self.shutdown_on_finish = False
        self._shutdown_dialog = None

        script_dir = os.path.dirname(os.path.abspath(__file__))
        app_icon = QIcon()
        # Prefer the pre-rendered PNG set over the SVG. Qt's QSvgRenderer mangles
        # the app icon's radial gradients / rounded-corner clip-path (renders it
        # as a harsh near-rectangle); the PNGs are rendered with librsvg so they
        # match the design exactly. Feed every size so Qt picks the right bitmap.
        for sz in (16, 32, 48, 64, 128, 256, 512):
            candidate = os.path.join(script_dir, "icons", "linux-downloader-%d.png" % sz)
            if os.path.exists(candidate):
                app_icon.addFile(candidate, QSize(sz, sz))
        if app_icon.isNull():
            app_icon = QIcon.fromTheme("linux-downloader")
        if app_icon.isNull():
            for candidate in [
                os.path.join(script_dir, "icons", "linux-downloader.svg"),
                os.path.join(script_dir, "linux-downloader.svg"),
            ]:
                if os.path.exists(candidate):
                    app_icon = QIcon(candidate)
                    break
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
            QApplication.setWindowIcon(app_icon)
        self.app_icon = app_icon

        # Load bundled wordmark font (Rajdhani Bold); fall back silently if missing
        self._title_font_family = "Sans"
        rajdhani_path = os.path.join(script_dir, "fonts", "Rajdhani-Bold.ttf")
        if os.path.exists(rajdhani_path):
            fid = QFontDatabase.addApplicationFont(rajdhani_path)
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams:
                self._title_font_family = fams[0]

        # Load bundled IBM Plex Sans + Mono for the Variant C dashboard sidebar.
        self._plex_sans_family = "IBM Plex Sans"
        self._mono_font_family = "IBM Plex Mono"
        fonts_dir = os.path.join(script_dir, "assets", "fonts")
        plex_sans_files = [
            "IBMPlexSans-Regular.ttf", "IBMPlexSans-Medium.ttf",
            "IBMPlexSans-SemiBold.ttf", "IBMPlexSans-Bold.ttf",
        ]
        plex_mono_files = [
            "IBMPlexMono-Regular.ttf", "IBMPlexMono-SemiBold.ttf",
        ]
        for fname in plex_sans_files:
            fpath = os.path.join(fonts_dir, fname)
            if os.path.exists(fpath):
                fid = QFontDatabase.addApplicationFont(fpath)
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    self._plex_sans_family = fams[0]
        for fname in plex_mono_files:
            fpath = os.path.join(fonts_dir, fname)
            if os.path.exists(fpath):
                fid = QFontDatabase.addApplicationFont(fpath)
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    self._mono_font_family = fams[0]

        self._build_ui()
        self._load_history_into_table()
        self._apply_theme()
        self._update_category_counts()
        self._update_empty_state()
        self.threads = []
        start_bridge_server()
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_queue)
        self.timer.start(500)
        self.taskbar_timer = QTimer()
        self.taskbar_timer.timeout.connect(self._update_taskbar_progress)
        self.taskbar_timer.start(1000)
        # Refresh the hero card every 30s so the UPTIME stat ticks even when
        # no downloads are active.
        self._hero_timer = QTimer()
        self._hero_timer.timeout.connect(self._refresh_hero_card)
        self._hero_timer.start(30_000)

    def _theme(self):
        return THEMES["dark"] if self.dark_mode else THEMES["light"]

    def _show_toast(self, message, duration=2400):
        """Show a floating toast notification that fades in then out."""
        toast = QLabel(message, self)
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = self._theme()
        toast.setStyleSheet(f"""
            QLabel {{
                background-color: {t['sidebar']};
                color: {t['text']};
                border: 1px solid {t['border']};
                border-radius: 20px;
                padding: 0px 22px;
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        toast.setFixedHeight(40)
        toast.adjustSize()
        w = max(toast.sizeHint().width() + 48, 280)
        toast.setFixedSize(w, 40)
        toast.move((self.width() - w) // 2, self.height() - 80)

        effect = QGraphicsOpacityEffect(toast)
        toast.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        toast.show()
        toast.raise_()

        opacity = [0.0]

        def fade_in():
            opacity[0] = min(1.0, opacity[0] + 0.12)
            effect.setOpacity(opacity[0])
            if opacity[0] >= 1.0:
                timer_in.stop()
                QTimer.singleShot(duration, start_fade_out)

        def start_fade_out():
            opacity[0] = 1.0
            timer_out.start(25)

        def fade_out():
            opacity[0] = max(0.0, opacity[0] - 0.08)
            effect.setOpacity(opacity[0])
            if opacity[0] <= 0.0:
                timer_out.stop()
                toast.deleteLater()

        timer_in  = QTimer(self)
        timer_out = QTimer(self)
        timer_in.timeout.connect(fade_in)
        timer_out.timeout.connect(fade_out)
        timer_in.start(20)

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
            elif status == "Downloading":
                # Session may have ended right as the file finished writing,
                # leaving the DB entry stuck as "Downloading". Promote to
                # "Finished" when the file is actually present on disk.
                if path and os.path.exists(path):
                    status = "Finished"
                else:
                    status = "Interrupted"

            date     = entry.get("date", "")
            progress = entry.get("progress", None)
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._insert_row_items(row, filename, path, url, status, size, category, date, progress)
            # Only mark as "already downloaded" if the download truly
            # finished AND the file still exists on disk.  Interrupted /
            # cancelled / file-missing entries must NOT block re-downloads.
            if url and status == "Finished":
                self.finished_urls[self._social_dedup_key(url)] = path

    def _apply_status_style(self, item, status_text):
        if item is None:
            return
        color = STATUS_COLORS.get(status_text)
        if color is None:
            color = self._theme().get("muted", "#64748b")
        item.setForeground(QColor(color))
        f = item.font()
        f.setBold(True)
        item.setFont(f)
        item.setToolTip(status_text)

    def _insert_row_items(self, row, filename, path, url, status, size, category, date="", progress=None):
        # The file-list delegate paints the icon and sub-meta itself, so the
        # display string is the bare filename and the icon comes from the
        # category data role rather than QTableWidgetItem.setIcon().
        name_item = QTableWidgetItem(filename)
        name_item.setData(Qt.ItemDataRole.UserRole, path)
        name_item.setData(Qt.ItemDataRole.UserRole + 2, url)
        name_item.setData(FL_ROLE_CATEGORY, category)
        # Sub-meta shows the file's intrinsic size — strip any "done / " prefix
        # that the size string might carry (e.g. finished rows save "X / X").
        meta_size = size.split(" / ", 1)[1].strip() if isinstance(size, str) and " / " in size else size
        name_item.setData(FL_ROLE_TOTAL, meta_size)
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
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        self._apply_status_style(stat_item, status)

        self.table.setItem(row, 0, name_item)
        self.table.setItem(row, 1, prog_item)
        self.table.setItem(row, 2, dl_item)
        self.table.setItem(row, 3, spd_item)
        self.table.setItem(row, 4, eta_item)
        date_item = QTableWidgetItem(date)
        date_item.setFlags(date_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 5, stat_item)
        self.table.setItem(row, 6, date_item)
        self.table.setRowHeight(row, FL_ROW_HEIGHT)

        self.all_rows.append({"row": row, "category": category})
        self.row_progress[row] = _progress

    def _add_to_history(self, url, filename, path, status, size, category, progress=0):
        entry = {"url": url, "filename": filename, "path": path,
                 "status": status, "size": size, "category": category,
                 "date": time.strftime("%Y-%m-%d %H:%M"),
                 "progress": progress}
        if self.yt_settings.get(url):
            entry["yt_settings"] = self.yt_settings[url]
        self.history = [e for e in self.history if e.get("url") != url]
        self.history.append(entry)
        save_history(self.history)

    def _load_svg_qt_compatible(self, path):
        """Read an SVG and rewrite rgba() colors that Qt's SVG renderer can't parse.

        Qt's QSvgRenderer treats `rgba(r,g,b,a)` as an invalid color and falls back
        to opaque black, which makes white-with-alpha highlights render as black
        blotches and silently drops detail strokes. Convert each rgba(...) value
        on attributes Qt does understand (rgb() + a separate *-opacity attribute).
        """
        import re
        from PyQt6.QtCore import QByteArray
        with open(path, "rb") as f:
            svg = f.read().decode("utf-8")

        rgba_re = re.compile(
            r'\b(fill|stroke|stop-color)\s*=\s*"\s*rgba\(\s*'
            r'(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)\s*"'
        )

        def repl(m):
            attr, r, g, b, a = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            opacity_attr = "stop-opacity" if attr == "stop-color" else f"{attr}-opacity"
            return f'{attr}="rgb({r},{g},{b})" {opacity_attr}="{a}"'

        return QByteArray(rgba_re.sub(repl, svg).encode("utf-8"))

    def _render_category_icon(self, label, size):
        """Render the gorgeous squircle SVG for a sidebar category at `size` px."""
        filename = CATEGORY_ICON_FILE.get(label)
        if not filename:
            return None
        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets", "category_icons", filename,
        )
        if not os.path.exists(icon_path):
            return None
        try:
            return _render_svg_pixmap(icon_path, size)
        except Exception:
            return None

    def _parse_size_to_bytes(self, size_str):
        """Parse strings like '12.0 MB / 12.0 MB' or '285.9 MB' → bytes (first number)."""
        if not size_str:
            return 0
        try:
            first = size_str.split("/")[0].strip()
            parts = first.split()
            if len(parts) < 2:
                return 0
            num = float(parts[0])
            unit = parts[1].upper()
        except Exception:
            return 0
        mult = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
        return int(num * mult.get(unit, 0))

    def _format_uptime(self, seconds):
        seconds = max(0, int(seconds))
        h, rem = divmod(seconds, 3600)
        m = rem // 60
        return f"{h}h {m:02d}m"

    def _compute_week_data(self):
        """Build the 7-day list (Monday → Sunday of the current week) for the hero card."""
        import datetime as _dt
        today = _dt.date.today()
        monday = today - _dt.timedelta(days=today.weekday())
        weekday_initials = ["M", "T", "W", "T", "F", "S", "S"]
        weekday_full = [
            "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
            "FRIDAY", "SATURDAY", "SUNDAY",
        ]
        # Aggregate finished history entries by YYYY-MM-DD
        per_day_bytes = {}
        per_day_files = {}
        for entry in self.history:
            date_str = entry.get("date", "")
            if not date_str:
                continue
            day_key = date_str.split(" ")[0]
            per_day_bytes[day_key] = per_day_bytes.get(day_key, 0) + self._parse_size_to_bytes(entry.get("size", ""))
            per_day_files[day_key] = per_day_files.get(day_key, 0) + 1
        # Active counts from the live table
        active_now = 0
        total_now = 0
        if hasattr(self, "table"):
            for row in range(self.table.rowCount()):
                total_now += 1
                stat = self.table.item(row, 5)
                if stat and stat.text() == "Downloading":
                    active_now += 1
        # Build week dicts
        days = []
        gb_values = []
        for i in range(7):
            d = monday + _dt.timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            gb = per_day_bytes.get(key, 0) / (1024 ** 3)
            gb_values.append(gb)
            days.append({
                "date": d,
                "key": key,
                "label": weekday_initials[i],
                "weekday_full": weekday_full[i],
                "date_str": d.strftime("%b %d").lstrip("0").replace(" 0", " "),
                "is_today": (d == today),
                "gb": gb,
                "files": per_day_files.get(key, 0),
            })
        max_gb = max(gb_values) if gb_values else 0
        for d in days:
            d["v"] = (d["gb"] / max_gb) if max_gb > 0 else 0.0
            d["files_text"] = str(d["files"])
            if d["is_today"]:
                d["active_text"] = f"{active_now}/{total_now}" if total_now else "0/0"
                d["active_nonzero"] = active_now > 0
                d["uptime_text"] = self._format_uptime(time.time() - self._session_start)
            else:
                d["active_text"] = "—"
                d["active_nonzero"] = False
                d["uptime_text"] = "—"
        return days

    def _refresh_hero_card(self):
        if not hasattr(self, "_hero_card"):
            return
        days = self._compute_week_data()
        prev_idx = getattr(self._hero_card, "_selected_idx", 6)
        # On first paint, default to today (last bar). After that, preserve user click.
        if not getattr(self, "_hero_initialized", False):
            today_idx = next((i for i, d in enumerate(days) if d["is_today"]), 6)
            self._hero_card.set_data(days, selected_idx=today_idx)
            self._hero_initialized = True
        else:
            self._hero_card.set_data(days, selected_idx=prev_idx)

    def _build_storage_card(self):
        """Create the bottom-of-sidebar storage usage card (Variant A spec)."""
        from PyQt6.QtWidgets import QProgressBar

        card = QWidget()
        card.setObjectName("storageCard")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(14, 8, 14, 14)
        outer.setSpacing(0)

        inner = QWidget()
        inner.setObjectName("storageInner")
        v = QVBoxLayout(inner)
        v.setContentsMargins(13, 12, 13, 12)
        v.setSpacing(7)

        # Header row: HDD glyph + caption
        cap_row = QHBoxLayout()
        cap_row.setContentsMargins(0, 0, 0, 0)
        cap_row.setSpacing(7)
        glyph_color = "#cbd5e1" if self.dark_mode else "#475569"
        self._storage_glyph = QLabel()
        self._storage_glyph.setObjectName("storageGlyph")
        self._storage_glyph.setPixmap(
            _render_svg_str_pixmap(_TILE_SVG_HDD, glyph_color, size=14)
        )
        self._storage_glyph.setFixedSize(14, 14)
        cap_row.addWidget(self._storage_glyph)
        cap = QLabel("DOWNLOAD STORAGE")
        cap.setObjectName("storageCap")
        cap_row.addWidget(cap)
        cap_row.addStretch()
        v.addLayout(cap_row)

        # Value row: "142.8 GB" + "of 500 GB"
        val_row = QHBoxLayout()
        val_row.setContentsMargins(0, 0, 0, 0)
        val_row.setSpacing(0)
        self._storage_value = QLabel("— GB")
        self._storage_value.setObjectName("storageValue")
        val_row.addWidget(self._storage_value)
        val_row.addStretch()
        self._storage_total = QLabel("")
        self._storage_total.setObjectName("storageTotal")
        val_row.addWidget(self._storage_total)
        v.addLayout(val_row)

        # Progress bar
        self._storage_bar = QProgressBar()
        self._storage_bar.setObjectName("storageBar")
        self._storage_bar.setRange(0, 100)
        self._storage_bar.setValue(0)
        self._storage_bar.setTextVisible(False)
        self._storage_bar.setFixedHeight(6)
        v.addWidget(self._storage_bar)

        # Footer: "% used"  + "GB free"
        foot_row = QHBoxLayout()
        foot_row.setContentsMargins(0, 0, 0, 0)
        foot_row.setSpacing(0)
        self._storage_pct = QLabel("")
        self._storage_pct.setObjectName("storagePct")
        foot_row.addWidget(self._storage_pct)
        foot_row.addStretch()
        self._storage_free = QLabel("")
        self._storage_free.setObjectName("storageFree")
        foot_row.addWidget(self._storage_free)
        v.addLayout(foot_row)

        outer.addWidget(inner)
        self._refresh_storage_card()
        return card

    def _refresh_storage_card(self):
        """Recompute disk-usage figures for the storage card."""
        if not hasattr(self, "_storage_value"):
            return
        target = os.path.join(HOME, "Downloads")
        if not os.path.exists(target):
            target = HOME
        try:
            usage = shutil.disk_usage(target)
        except Exception:
            return
        gb = 1024 ** 3
        used_gb = (usage.total - usage.free) / gb
        total_gb = usage.total / gb
        free_gb = usage.free / gb
        pct = (used_gb / total_gb * 100) if total_gb else 0
        self._storage_value.setText(
            f"<span style='font-size:15px;font-weight:700;'>{used_gb:.1f}</span> "
            f"<span style='font-size:11px;font-weight:500;color:#64748b;'>GB</span>"
        )
        self._storage_total.setText(f"of {total_gb:.0f} GB")
        self._storage_pct.setText(f"{pct:.0f}% used")
        self._storage_free.setText(f"{free_gb:.1f} GB free")
        self._storage_bar.setValue(int(round(pct)))

    def _make_toolbar_svg_btn(self, icon_filename, tooltip, label_text,
                              _unused_color=None, _unused_bg=None):
        """Create a toolbar button that loads a full SVG icon file."""
        from PyQt6.QtSvg import QSvgRenderer

        LABEL_CLR   = "#3b82f6"
        HOVER_LIGHT = "rgba(100, 116, 139, 0.10)"
        HOVER_DARK  = "rgba(59, 130, 246, 0.13)"
        hover_bg = HOVER_DARK if self.dark_mode else HOVER_LIGHT

        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets", "toolbar_icons", icon_filename,
        )

        wrapper = QWidget()
        wrapper.setFixedSize(86, 84)
        wrapper.setStyleSheet("background: transparent;")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(2, 2, 2, 4)
        wrapper_layout.setSpacing(0)

        btn = QPushButton()
        btn.setFixedSize(82, 80)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        render_size  = 192
        display_size = 48

        renderer = QSvgRenderer(self._load_svg_qt_compatible(icon_path))
        pixmap = QPixmap(render_size, render_size)
        pixmap.fill(QColor(0, 0, 0, 0))
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        renderer.render(p)
        p.end()
        display_pixmap = pixmap.scaled(
            display_size, display_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        icon_lbl = QLabel()
        icon_lbl.setPixmap(display_pixmap)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        icon_lbl.setFixedSize(display_size, display_size)
        icon_lbl.setStyleSheet("background: transparent; border: none;")

        text_lbl = QLabel(label_text)
        text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_lbl.setStyleSheet(
            f"background: transparent; border: none; color: {LABEL_CLR};"
            "font-size: 9px; font-weight: 800; letter-spacing: 0.5px;")

        vbox = QVBoxLayout(btn)
        vbox.setContentsMargins(0, 5, 0, 4)
        vbox.setSpacing(1)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(icon_lbl)
        vbox.addWidget(text_lbl)

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 16px;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
            }}
            QPushButton:pressed {{
                background-color: {hover_bg};
                padding-top: 1px;
            }}
            QPushButton:disabled {{
                background-color: transparent;
            }}
            QToolTip {{
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
            }}
        """)

        wrapper_layout.addWidget(btn)
        wrapper._inner_btn = btn
        btn._icon_lbl = icon_lbl
        btn._text_lbl = text_lbl
        btn._icon_path = icon_path
        return wrapper

    def _open_selected_folder(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            open_and_select(path)
        elif path and os.path.isdir(os.path.dirname(path)):
            subprocess.Popen(['xdg-open', os.path.dirname(path)])
            self._show_toast("File missing — opened its folder")
        else:
            self._show_toast("Folder not found on disk")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.table.hasFocus():
            self.clear_item()
        super().keyPressEvent(event)

    def _build_ui(self):
        t = self._theme()
        central = QWidget()
        central.setObjectName("mainWindow")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
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
        self._shutdown_action = QAction("Shut Down When Downloads Finish", self)
        self._shutdown_action.setCheckable(True)
        self._shutdown_action.setChecked(self.shutdown_on_finish)
        self._shutdown_action.triggered.connect(self._toggle_shutdown_on_finish)
        view_menu.addAction(self._shutdown_action)
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
        self._sidebar.setFixedWidth(250)
        self._sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        from PyQt6.QtWidgets import QFrame, QScrollArea

        self._sidebar_title = QWidget()
        title_layout = QHBoxLayout(self._sidebar_title)
        title_layout.setContentsMargins(18, 16, 18, 12)
        title_layout.setSpacing(11)

        icon_label = QLabel()
        icon_label.setFixedSize(34, 34)
        icon_label.setScaledContents(True)
        pix = self.app_icon.pixmap(34, 34) if not self.app_icon.isNull() else None
        if pix is None or pix.isNull():
            script_dir = os.path.dirname(os.path.abspath(__file__))
            png_path = os.path.join(script_dir, "icons", "linux-downloader-128.png")
            if os.path.exists(png_path):
                pix = QPixmap(png_path).scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if pix and not pix.isNull():
            icon_label.setPixmap(pix)
        title_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        wordmark_col = QVBoxLayout()
        wordmark_col.setContentsMargins(0, 0, 0, 0)
        wordmark_col.setSpacing(1)
        self._title_label = GradientTextLabel(
            "LDM", family=self._title_font_family,
            size=16, letter_spacing=3,
        )
        wordmark_col.addWidget(self._title_label, 0, Qt.AlignmentFlag.AlignLeft)
        self._title_subtitle = FlatBearingLabel("DOWNLOAD MANAGER")
        self._title_subtitle.setObjectName("brandSubtitle")
        wordmark_col.addWidget(self._title_subtitle, 0, Qt.AlignmentFlag.AlignLeft)
        title_layout.addLayout(wordmark_col)
        title_layout.addStretch()
        sidebar_layout.addWidget(self._sidebar_title)

        # ── Variant C hero (dashboard) card ───────────────────────────────────
        hero_wrap = QWidget()
        hero_wrap_layout = QHBoxLayout(hero_wrap)
        hero_wrap_layout.setContentsMargins(14, 0, 14, 14)
        hero_wrap_layout.setSpacing(0)
        bolt_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets", "sidebar_icons", "bolt.svg",
        )
        self._hero_card = _SidebarHeroCard(
            font_family=getattr(self, "_plex_sans_family", "IBM Plex Sans"),
            mono_family=getattr(self, "_mono_font_family", "IBM Plex Mono"),
            bolt_svg_path=bolt_path,
        )
        hero_wrap_layout.addWidget(self._hero_card)
        sidebar_layout.addWidget(hero_wrap)

        # CATEGORIES caption row: "CATEGORIES"  ……  "72 total"
        cat_caption_wrap = QWidget()
        cat_caption_layout = QHBoxLayout(cat_caption_wrap)
        cat_caption_layout.setContentsMargins(14, 0, 14, 8)
        cat_caption_layout.setSpacing(0)
        self._cat_section_label = QLabel("CATEGORIES")
        self._cat_section_label.setObjectName("catSectionLabel")
        cat_caption_layout.addWidget(self._cat_section_label)
        cat_caption_layout.addStretch()
        self._cat_total_label = QLabel("0 total")
        self._cat_total_label.setObjectName("catTotalLabel")
        cat_caption_layout.addWidget(self._cat_total_label)
        sidebar_layout.addWidget(cat_caption_wrap)

        # Hidden sentinel kept for backwards compatibility (older code may touch it).
        self._sidebar_sep = QFrame()
        self._sidebar_sep.setObjectName("sidebarSep")
        self._sidebar_sep.setFixedHeight(0)
        self._sidebar_sep.setVisible(False)

        self._cat_scroll = QWidget()
        self._cat_scroll.setObjectName("catScroll")
        cat_layout = QVBoxLayout(self._cat_scroll)
        cat_layout.setContentsMargins(8, 0, 8, 0)
        cat_layout.setSpacing(2)

        self._cat_buttons = []
        self._cat_badges = []
        self._cat_accents = []  # kept (always invisible) so theme code can address them
        self._cat_icons = []
        self._cat_text_labels = []
        self._current_cat_row = 0
        for i, (label, emoji, color) in enumerate(CATEGORIES):
            btn = QWidget()
            btn.setObjectName(f"catBtn_{i}")
            btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_layout = QHBoxLayout(btn)
            btn_layout.setContentsMargins(8, 5, 8, 5)
            btn_layout.setSpacing(9)

            # Accent kept zero-width — Variant C has no left-bar accent.
            accent = QWidget()
            accent.setObjectName(f"catAccent_{i}")
            accent.setFixedWidth(0)
            accent.setFixedHeight(0)
            accent.setVisible(False)

            icon_lbl = QLabel()
            icon_lbl.setObjectName(f"catIcon_{i}")
            icon_lbl.setFixedSize(22, 22)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            pix22 = self._render_category_icon(label, 22)
            if pix22 is not None:
                icon_lbl.setPixmap(pix22)
            btn_layout.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

            text_label = QLabel(label)
            text_label.setObjectName(f"catText_{i}")
            text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            btn_layout.addWidget(text_label, 1, Qt.AlignmentFlag.AlignVCenter)

            badge = QLabel("")
            badge.setObjectName(f"catBadge_{i}")
            badge.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            badge.setVisible(False)
            btn_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

            btn.mousePressEvent = lambda e, idx=i: self._on_cat_clicked(idx)
            cat_layout.addWidget(btn)
            self._cat_buttons.append(btn)
            self._cat_badges.append(badge)
            self._cat_accents.append(accent)
            self._cat_icons.append(icon_lbl)
            self._cat_text_labels.append(text_label)

        cat_layout.addStretch()
        sidebar_layout.addWidget(self._cat_scroll, 1)

        # ── Storage card ──────────────────────────────────────────────────────
        self._storage_card = self._build_storage_card()
        sidebar_layout.addWidget(self._storage_card)

        root.addWidget(self._sidebar)

        self._content_widget = QWidget()
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(16, 14, 16, 10)
        content_layout.setSpacing(10)

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
        toolbar_layout.setContentsMargins(8, 8, 8, 8)
        toolbar_layout.setSpacing(6)

        # Toolbar buttons — squircle SVG icons loaded from assets/toolbar_icons/
        self._start_wrap       = self._make_toolbar_svg_btn("start.svg",   "Start Download",      "START")
        self._resume_wrap      = self._make_toolbar_svg_btn("resume.svg",  "Resume Download",     "RESUME")
        self._cancel_wrap      = self._make_toolbar_svg_btn("cancel.svg",  "Cancel Download",     "CANCEL")
        self._clear_item_wrap  = self._make_toolbar_svg_btn("remove.svg",  "Remove Item",         "REMOVE")
        self._clear_wrap       = self._make_toolbar_svg_btn("clear.svg",   "Clear All",           "CLEAR")
        self._open_folder_wrap = self._make_toolbar_svg_btn("folder.svg",  "Open Folder",         "OPEN")
        self._yt_wrap          = self._make_toolbar_svg_btn("youtube.svg", "YouTube Downloader",  "YOUTUBE")
        self._about_wrap       = self._make_toolbar_svg_btn("about.svg",   "About",               "ABOUT")
        self._donate_wrap      = self._make_toolbar_svg_btn("donate.svg",  "Support Development", "DONATE")

        # Extract inner buttons for signal connections
        self.start_btn = self._start_wrap._inner_btn
        self.resume_btn = self._resume_wrap._inner_btn
        self.cancel_btn = self._cancel_wrap._inner_btn
        self.clear_item_btn = self._clear_item_wrap._inner_btn
        self.clear_btn = self._clear_wrap._inner_btn
        self.open_folder_btn = self._open_folder_wrap._inner_btn
        self.yt_btn = self._yt_wrap._inner_btn
        self.about_btn = self._about_wrap._inner_btn
        self.donate_btn = self._donate_wrap._inner_btn

        for w in [self._start_wrap, self._resume_wrap, self._cancel_wrap,
                  self._clear_item_wrap, self._clear_wrap,
                  self._open_folder_wrap, self._yt_wrap,
                  self._about_wrap, self._donate_wrap]:
            toolbar_layout.addWidget(w)
        toolbar_layout.addStretch()

        self.start_btn.clicked.connect(self.start_manual)
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
        self.table.setHorizontalHeaderLabels(["FILE NAME", "PROGRESS", "DOWNLOADED", "SPEED", "ETA", "STATUS", "DATE"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for col in range(self.table.columnCount()):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 360)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 0)
        self.table.setColumnWidth(4, 0)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(6, 160)
        # Speed / ETA live in the bottom status chip instead of dedicated
        # columns — see _refresh_status_chip().
        self.table.setColumnHidden(3, True)
        self.table.setColumnHidden(4, True)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # ── Restore saved column widths ──────────────────────────────
        saved_widths = self._settings.get("column_widths", {})
        for col_str, width in saved_widths.items():
            self.table.setColumnWidth(int(col_str), width)
        self.table.horizontalHeader().setMinimumSectionSize(50)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(FL_ROW_HEIGHT)
        self.table.setIconSize(QSize(28, 28))
        self.table.setAlternatingRowColors(False)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().sectionClicked.connect(self._sort_by_column)
        self.table.horizontalHeader().sectionResized.connect(self._on_column_resized)

        # File-list redesign delegates — one per column. See the README in
        # LDM_file_list_v1/ for the visual spec they implement.
        sans = getattr(self, "_plex_sans_family", "IBM Plex Sans")
        mono = getattr(self, "_mono_font_family", "IBM Plex Mono")
        self._fl_name_delegate     = FlNameDelegate(self.table, sans, mono)
        self._fl_progress_delegate = FlProgressDelegate(self.table, sans, mono)
        self._fl_downloaded_delegate = FlDownloadedDelegate(self.table, sans, mono)
        self._fl_speed_delegate    = FlSpeedDelegate(self.table, sans, mono)
        self._fl_eta_delegate      = FlEtaDelegate(self.table, sans, mono)
        self._fl_status_delegate   = FlStatusDelegate(self.table, sans, mono)
        self._fl_date_delegate     = FlDateDelegate(self.table, sans, mono)
        self.table.setItemDelegateForColumn(0, self._fl_name_delegate)
        self.table.setItemDelegateForColumn(1, self._fl_progress_delegate)
        self.table.setItemDelegateForColumn(2, self._fl_downloaded_delegate)
        self.table.setItemDelegateForColumn(3, self._fl_speed_delegate)
        self.table.setItemDelegateForColumn(4, self._fl_eta_delegate)
        self.table.setItemDelegateForColumn(5, self._fl_status_delegate)
        self.table.setItemDelegateForColumn(6, self._fl_date_delegate)
        # Kept for compatibility with code that reads `progress_delegate`.
        self.progress_delegate = self._fl_progress_delegate

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        self._table_stack = QStackedWidget()
        self._table_stack.addWidget(self.table)

        self._empty_state = QWidget()
        self._empty_state.setObjectName("emptyState")
        empty_layout = QVBoxLayout(self._empty_state)
        empty_layout.setContentsMargins(20, 20, 20, 20)
        empty_layout.setSpacing(12)
        empty_layout.addStretch()

        self._empty_icon = QLabel("⬇")
        self._empty_icon.setObjectName("emptyIcon")
        self._empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._empty_icon)

        self._empty_title = QLabel("No downloads yet")
        self._empty_title.setObjectName("emptyTitle")
        self._empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._empty_title)

        self._empty_hint = QLabel("Paste a URL above or use the browser extension")
        self._empty_hint.setObjectName("emptyHint")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setWordWrap(True)
        empty_layout.addWidget(self._empty_hint)

        empty_layout.addStretch()
        self._table_stack.addWidget(self._empty_state)

        content_layout.addWidget(self._table_stack)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.model().rowsInserted.connect(lambda *_: self._update_empty_state())
        self.table.model().rowsRemoved.connect(lambda *_: self._update_empty_state())

        # Status bar — summary text on the left, speed/ETA chip on the right.
        # The chip surfaces speed and ETA for the currently selected
        # downloading row (the columns themselves are hidden from the table).
        self._status_row = QWidget()
        self._status_row.setFixedHeight(28)
        status_row_layout = QHBoxLayout(self._status_row)
        status_row_layout.setContentsMargins(4, 0, 4, 0)
        status_row_layout.setSpacing(12)

        self._status_bar = QLabel("Ready")
        status_row_layout.addWidget(self._status_bar, 1)

        self._status_metric = QWidget()
        self._status_metric.setObjectName("statusMetric")
        metric_layout = QHBoxLayout(self._status_metric)
        metric_layout.setContentsMargins(0, 0, 0, 0)
        metric_layout.setSpacing(14)
        mono = getattr(self, "_mono_font_family", "IBM Plex Mono")
        speed_font = QFont(mono); speed_font.setPixelSize(12); speed_font.setWeight(QFont.Weight.Bold)
        eta_font   = QFont(mono); eta_font.setPixelSize(12); eta_font.setWeight(QFont.Weight.Medium)
        self._status_speed_label = QLabel("")
        self._status_speed_label.setFont(speed_font)
        self._status_speed_label.setStyleSheet("color: #16a34a; background: transparent;")
        self._status_eta_label = QLabel("")
        self._status_eta_label.setFont(eta_font)
        self._status_eta_label.setStyleSheet("color: #475569; background: transparent;")
        metric_layout.addWidget(self._status_speed_label)
        metric_layout.addWidget(self._status_eta_label)
        self._status_metric.hide()
        status_row_layout.addWidget(self._status_metric, 0, Qt.AlignmentFlag.AlignRight)

        content_layout.addWidget(self._status_row)

        root.addWidget(self._content_widget)
        outer.addWidget(body)

    def _update_menubar_style(self):
        t = self._theme()
        accent = t.get("accent", "#2f81f7")
        self._menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {t['menu_bg']};
                color: {t['text']};
                border-bottom: 1px solid {t['border']};
                font-size: 13px;
                padding: 2px 6px;
            }}
            QMenuBar::item {{
                padding: 5px 12px;
                border-radius: 6px;
            }}
            QMenuBar::item:selected {{
                background-color: {t['menu_hover']};
                color: {t['menu_hover_text']};
            }}
            QMenu {{
                background-color: {t['surface']};
                color: {t['text']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 5px;
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 8px 22px;
                border-radius: 5px;
            }}
            QMenu::item:selected {{
                background-color: {t['menu_hover']};
                color: {t['menu_hover_text']};
            }}
            QMenu::separator {{
                height: 1px;
                background: {t['border']};
                margin: 4px 8px;
            }}
            QMenu::indicator {{
                width: 14px;
                height: 14px;
            }}
            QToolTip {{
                background-color: {t['surface']};
                color: {t['text']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
            }}
        """)

    def _apply_table_style(self):
        t = self._theme()

        # Card chrome — white surface, 14px radius, thin border, soft shadow.
        # Delegates paint each row's interior; the table itself only provides
        # the outer card and the header strip.
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                gridline-color: transparent;
                outline: none;
                selection-background-color: #eff6ff;
                selection-color: #1d4ed8;
                font-size: 13px;
                color: {t['text']};
            }}
            QTableWidget::item {{
                padding: 0px;
                border: none;
            }}
            QTableWidget::item:selected {{
                background-color: #eff6ff;
                color: #1d4ed8;
            }}
            QHeaderView::section {{
                background-color: #f8fafc;
                color: #94a3b8;
                font-size: 10px;
                font-weight: 700;
                padding: 11px 14px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                text-transform: uppercase;
            }}
            QHeaderView::section:first {{
                border-top-left-radius: 14px;
                padding-left: 14px;
            }}
            QHeaderView::section:last {{
                border-top-right-radius: 14px;
                padding-right: 18px;
            }}
            QHeaderView::section:hover {{
                background-color: #f1f5f9;
                color: #475569;
            }}
            QHeaderView {{
                background-color: {t['header']};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 4px 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['scrollbar_handle']};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t['muted']};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0; border: none; background: none;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 8px;
                margin: 2px 4px;
            }}
            QScrollBar::handle:horizontal {{
                background: {t['scrollbar_handle']};
                border-radius: 4px;
                min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {t['muted']};
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0; border: none; background: none;
            }}
        """)

        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(FL_ROW_HEIGHT)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)

        # Qt CSS doesn't support letter-spacing reliably on headers — apply via QFont
        header_font = QFont(getattr(self, "_plex_sans_family", self.font().family()))
        header_font.setPixelSize(10)
        header_font.setWeight(QFont.Weight.Bold)
        header_font.setCapitalization(QFont.Capitalization.AllUppercase)
        header_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.9)
        self.table.horizontalHeader().setFont(header_font)
        self.table.horizontalHeader().setFixedHeight(36)

    def _apply_theme(self):
        t = self._theme()
        accent = t.get("accent", "#2f81f7")

        # ── Main window ───────────────────────────────────────────────────────
        self.centralWidget().setStyleSheet(f"""
            QWidget#mainWindow {{
                background-color: {t['bg']};
                color: {t['text']};
                font-family: -apple-system, 'Segoe UI', Ubuntu, sans-serif;
            }}
        """)

        # ── Menubar ────────────────────────────────────────────────────────────
        self._update_menubar_style()

        # ── Sidebar ────────────────────────────────────────────────────────────
        self._sidebar.setStyleSheet(f"""
            QWidget#sidebar {{
                background-color: {t['sidebar']};
                border-right: none;
            }}
        """)
        self._sidebar_title.setStyleSheet(f"""
            background-color: transparent;
            border-bottom: none;
        """)
        self._title_label.set_accent(accent)
        # Color is applied via setColor() (FlatBearingLabel ignores QSS color
        # because it does its own painting). The QSS only sets font geometry.
        self._title_subtitle.setColor(t['faint'])
        self._title_subtitle.setStyleSheet(f"""
            QLabel#brandSubtitle {{
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.5px;
                background: transparent;
            }}
        """)

        # Hidden — kept for compatibility with the old layout.
        self._sidebar_sep.setStyleSheet("QFrame#sidebarSep { background: transparent; }")

        self._cat_section_label.setStyleSheet(f"""
            QLabel#catSectionLabel {{
                color: {t['faint']};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.2px;
                background: transparent;
            }}
        """)
        if hasattr(self, "_cat_total_label"):
            self._cat_total_label.setStyleSheet(f"""
                QLabel#catTotalLabel {{
                    color: {t['faint']};
                    font-family: '{getattr(self, '_mono_font_family', 'IBM Plex Mono')}';
                    font-size: 10px;
                    font-weight: 600;
                    background: transparent;
                }}
            """)
        self._cat_scroll.setStyleSheet(f"""
            QWidget#catScroll {{ background: transparent; }}
        """)
        self._style_cat_buttons()
        self._style_storage_card()
        self._style_empty_state()

        # ── Content area ───────────────────────────────────────────────────────
        self._content_widget.setStyleSheet(f"background-color: {t['bg']};")

        # ── Inputs ─────────────────────────────────────────────────────────────
        input_style = f"""
            QLineEdit {{
                background-color: {t['input_bg']};
                color: {t['text']};
                border: 2px solid {t['border']};
                border-radius: 14px;
                padding: 11px 16px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 2px solid {accent};
                background-color: {t['input_focus']};
            }}
            QLineEdit::placeholder {{
                color: {t['faint']};
            }}
        """
        self.url_input.setStyleSheet(input_style)
        self._search_input.setStyleSheet(input_style)

        # ── Toolbar ────────────────────────────────────────────────────────────
        self._toolbar.setStyleSheet(f"""
            QWidget#toolbar {{
                background-color: {t.get('toolbar_bg', t['surface'])};
                border: none;
                border-radius: 20px;
            }}
        """)
        # Toolbar drop shadow
        toolbar_shadow = QGraphicsDropShadowEffect(self._toolbar)
        toolbar_shadow.setBlurRadius(24)
        toolbar_shadow.setOffset(0, 4)
        toolbar_shadow.setColor(QColor(0, 0, 0, 30))
        self._toolbar.setGraphicsEffect(toolbar_shadow)

        # Sidebar shadow for floating depth
        sidebar_shadow = QGraphicsDropShadowEffect(self._sidebar)
        sidebar_shadow.setBlurRadius(20)
        sidebar_shadow.setOffset(3, 0)
        sidebar_shadow.setColor(QColor(0, 0, 0, 18))
        self._sidebar.setGraphicsEffect(sidebar_shadow)

        # ── Table ──────────────────────────────────────────────────────────────
        self._apply_table_style()

        # ── Status bar ─────────────────────────────────────────────────────────
        self._status_bar.setStyleSheet(f"""
            QLabel {{
                background-color: {t['status_bar']};
                color: {t['muted']};
                border: none;
                border-radius: 12px;
                font-size: 11px;
                padding: 4px 12px;
                letter-spacing: 0.3px;
            }}
        """)

        # ── Update progress delegate dark flag ─────────────────────────────────
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

    def _toggle_shutdown_on_finish(self):
        self.shutdown_on_finish = not self.shutdown_on_finish
        self._shutdown_action.setChecked(self.shutdown_on_finish)
        if self.shutdown_on_finish:
            self._show_toast("PC will shut down when all downloads finish")
        else:
            self._show_toast("Auto shutdown disabled")

    def _has_active_downloads(self):
        for row in range(self.table.rowCount()):
            stat = self.table.item(row, 5)
            if stat and stat.text() in ("Downloading", "Queued"):
                return True
        return False

    def _maybe_shutdown(self):
        if not self.shutdown_on_finish:
            return
        if self._has_active_downloads():
            return
        if self._shutdown_dialog is not None:
            return
        self._begin_shutdown_countdown()

    def _begin_shutdown_countdown(self):
        seconds = 30
        dlg = QDialog(self)
        dlg.setWindowTitle("Shutting Down")
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)
        label = QLabel()
        label.setWordWrap(True)
        layout.addWidget(label)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        state = {"remaining": seconds}
        def render():
            label.setText(
                f"All downloads finished.\n\n"
                f"PC will shut down in {state['remaining']} seconds."
            )
        render()

        timer = QTimer(dlg)
        timer.setInterval(1000)

        def tick():
            state["remaining"] -= 1
            if state["remaining"] <= 0:
                timer.stop()
                dlg.accept()
                self._do_shutdown()
                return
            render()
        timer.timeout.connect(tick)

        def on_cancel():
            timer.stop()
            self.shutdown_on_finish = False
            self._shutdown_action.setChecked(False)
            dlg.reject()
        cancel_btn.clicked.connect(on_cancel)
        dlg.finished.connect(lambda _=None: setattr(self, "_shutdown_dialog", None))

        self._shutdown_dialog = dlg
        timer.start()
        dlg.show()

    def _do_shutdown(self):
        try:
            subprocess.Popen(
                ["systemctl", "poweroff"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            self._show_toast(f"Shutdown failed: {e}")

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
            badge = self._cat_badges[i]
            if count > 0:
                badge.setText(str(count))
                badge.setVisible(True)
            else:
                badge.setText("")
                badge.setVisible(False)

        if hasattr(self, "_cat_total_label"):
            self._cat_total_label.setText(f"{counts.get('All Downloads', 0)} total")
        self._refresh_hero_card()

    def _on_column_resized(self, col, old_width, new_width):
        widths = self._settings.setdefault("column_widths", {})
        widths[str(col)] = new_width
        save_settings(self._settings)

    def _sort_by_column(self, col):
        if col == 1:
            return  # Don't sort progress bar column
        self.table.sortItems(col, Qt.SortOrder.AscendingOrder)

    def _on_cat_clicked(self, index):
        self._current_cat_row = index
        self._style_cat_buttons()
        self.filter_by_category(index)

    def _style_cat_buttons(self):
        t = THEMES["dark" if self.dark_mode else "light"]
        text_color = "#0f172a" if not self.dark_mode else t['text']
        mono = getattr(self, "_mono_font_family", "IBM Plex Mono")
        for i, (label, emoji, color) in enumerate(CATEGORIES):
            btn = self._cat_buttons[i]
            badge = self._cat_badges[i]
            is_sel = (i == self._current_cat_row)
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            if is_sel:
                btn.setStyleSheet(f"""
                    QWidget#catBtn_{i} {{
                        background: rgba({r},{g},{b}, 0.10);
                        border-radius: 7px;
                    }}
                    QLabel#catText_{i} {{
                        color: {color};
                        font-size: 12px;
                        font-weight: 700;
                        background: transparent;
                    }}
                """)
                badge.setStyleSheet(f"""
                    QLabel#catBadge_{i} {{
                        color: {color};
                        font-family: '{mono}';
                        font-size: 10.5px;
                        font-weight: 700;
                        background: transparent;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QWidget#catBtn_{i} {{
                        background: transparent;
                        border-radius: 7px;
                    }}
                    QWidget#catBtn_{i}:hover {{
                        background: rgba({r},{g},{b}, 0.06);
                    }}
                    QLabel#catText_{i} {{
                        color: {text_color};
                        font-size: 12px;
                        font-weight: 500;
                        background: transparent;
                    }}
                """)
                badge.setStyleSheet(f"""
                    QLabel#catBadge_{i} {{
                        color: #94a3b8;
                        font-family: '{mono}';
                        font-size: 10.5px;
                        font-weight: 600;
                        background: transparent;
                    }}
                """)

    def _style_storage_card(self):
        if not hasattr(self, "_storage_card"):
            return
        if hasattr(self, "_storage_glyph"):
            glyph_color = "#cbd5e1" if self.dark_mode else "#475569"
            self._storage_glyph.setPixmap(
                _render_svg_str_pixmap(_TILE_SVG_HDD, glyph_color, size=14)
            )
        t = THEMES["dark" if self.dark_mode else "light"]
        if self.dark_mode:
            bg_top, bg_bot = "rgba(255,255,255,0.04)", "rgba(255,255,255,0.02)"
            border = "rgba(255,255,255,0.08)"
            cap_color = "#cbd5e1"
            value_color = t['text']
            unit_color = "#94a3b8"
            total_color = "#64748b"
            pct_color = "#94a3b8"
            track_color = "rgba(255,255,255,0.08)"
        else:
            bg_top, bg_bot = "#f8fafc", "#f1f5f9"
            border = "#e2e8f0"
            cap_color = "#475569"
            value_color = "#0f172a"
            unit_color = "#64748b"
            total_color = "#94a3b8"
            pct_color = "#64748b"
            track_color = "#e2e8f0"
        self._storage_card.setStyleSheet(f"""
            QWidget#storageCard {{ background: transparent; }}
            QWidget#storageInner {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {bg_top}, stop:1 {bg_bot});
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QLabel#storageCap {{
                color: {cap_color};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.8px;
                background: transparent;
            }}
            QLabel#storageValue {{
                color: {value_color};
                background: transparent;
            }}
            QLabel#storageTotal {{
                color: {total_color};
                font-size: 10px;
                background: transparent;
            }}
            QLabel#storagePct, QLabel#storageFree {{
                color: {pct_color};
                font-size: 10px;
                background: transparent;
            }}
            QProgressBar#storageBar {{
                background-color: {track_color};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar#storageBar::chunk {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #2563eb);
                border-radius: 3px;
            }}
        """)

    def _update_empty_state(self):
        if not hasattr(self, "_table_stack"):
            return
        is_empty = self.table.rowCount() == 0
        self._table_stack.setCurrentIndex(1 if is_empty else 0)

    def _style_empty_state(self):
        if not hasattr(self, "_empty_state"):
            return
        t = THEMES["dark" if self.dark_mode else "light"]
        self._empty_state.setStyleSheet(f"QWidget#emptyState {{ background-color: {t['bg']}; }}")
        self._empty_icon.setStyleSheet(
            f"QLabel#emptyIcon {{ color: {t['faint']}; font-size: 56px; background: transparent; }}"
        )
        self._empty_title.setStyleSheet(
            f"QLabel#emptyTitle {{ color: {t['muted']}; font-size: 16px; font-weight: 600; background: transparent; }}"
        )
        self._empty_hint.setStyleSheet(
            f"QLabel#emptyHint {{ color: {t['faint']}; font-size: 13px; background: transparent; }}"
        )

    def filter_by_search(self, text):
        text = text.lower().strip()
        current_cat = CATEGORIES[self._current_cat_row][0]
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
    ("1. System packages  (ffmpeg, curl, PyQt6 SVG)",
     "sudo apt install -y ffmpeg curl python3-pyqt6.qtsvg"),
    ("2. Python packages  (PyQt6, requests, yt-dlp, browser-cookie3)",
     "pip install -U PyQt6 requests yt-dlp browser-cookie3 --break-system-packages"),
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
        t = self._theme()
        accent = t.get("accent", "#2563eb")
        dialog = QDialog(self)
        dialog.setWindowTitle("About")
        dialog.setFixedWidth(380)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {t['surface']};
                color: {t['text']};
            }}
            QLabel {{ color: {t['text']}; background: transparent; }}
            QPushButton {{ border-radius: 14px; font-size: 13px; font-weight: 600; padding: 10px 24px; border: none; }}
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if not self.app_icon.isNull():
            icon_label = QLabel()
            icon_label.setPixmap(self.app_icon.pixmap(56, 56))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet("background: transparent;")
            layout.addWidget(icon_label)

        layout.addSpacing(8)

        name_label = QLabel("Linux Download Manager")
        name_label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {t['text']};")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        version_label = QLabel("Version 1.0")
        version_label.setStyleSheet(f"font-size: 12px; color: {t['muted']};")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        layout.addSpacing(12)

        dev_card = QWidget()
        dev_card.setStyleSheet(f"background-color: {t['bg']}; border-radius: 14px; padding: 12px 16px;")
        dev_layout = QVBoxLayout(dev_card)
        dev_layout.setContentsMargins(16, 12, 16, 12)
        dev_layout.setSpacing(4)
        dev_title = QLabel("Developer")
        dev_title.setStyleSheet(f"font-size: 11px; color: {t['faint']}; background: transparent;")
        dev_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_name = QLabel("Tanjim")
        dev_name.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {t['text']}; background: transparent;")
        dev_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_email = QLabel("tpodbcs@gmail.com")
        dev_email.setStyleSheet(f"font-size: 12px; color: {t['muted']}; background: transparent;")
        dev_email.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_layout.addWidget(dev_title)
        dev_layout.addWidget(dev_name)
        dev_layout.addWidget(dev_email)
        layout.addWidget(dev_card)

        layout.addSpacing(12)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['bg']};
                color: {t['muted']};
                border: none;
                border-radius: 14px;
                padding: 10px 24px;
            }}
            QPushButton:hover {{
                background-color: {t['category_hover']};
                color: {t['text']};
            }}
        """)
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

    def open_youtube_dialog(self, prefill_url="", skip_fetch=False):
        dialog = YouTubeDialog(self, prefill_url=prefill_url, dark=self.dark_mode, skip_fetch=skip_fetch)
        dialog.download_started.connect(self._on_yt_download_started)
        dialog.download_progress.connect(self._on_yt_progress)
        dialog.download_finished.connect(self._on_yt_finished)
        dialog.yt_settings_captured.connect(self._on_yt_settings)
        if not hasattr(self, '_yt_dialogs'):
            self._yt_dialogs = []
        self._yt_dialogs.append(dialog)
        self._yt_dialogs = [d for d in self._yt_dialogs if d.isVisible() or d is dialog]
        dialog.finished.connect(lambda: self._yt_dialogs.remove(dialog) if dialog in self._yt_dialogs else None)
        dialog.show()
        return dialog

    def _on_yt_settings(self, url, settings):
        self.yt_settings[url] = dict(settings)
        # If this URL already has a history row, update it so resume survives restart
        for e in self.history:
            if e.get("url") == url:
                e["yt_settings"] = dict(settings)
        save_history(self.history)

    def open_stream_dialog(self, url="", filename="", page_referer=""):
        # If already downloaded, show the same "Already Downloaded" dialog the
        # core downloader uses — let the user choose to skip or download with a
        # new name.  "rename" → proceed with a unique filename; anything else →
        # abort so the user isn't surprised by a silent duplicate.
        existing_path = self.check_already_finished(url)
        if existing_path:
            if self._show_already_downloaded_dialog(existing_path) != "rename":
                return
            filename = self._resolve_unique_name(filename or os.path.basename(url.split("?")[0]) or "video.mp4")
        dialog = StreamDialog(self, url=url, filename=filename, page_referer=page_referer, dark=self.dark_mode)
        dialog.download_started.connect(self._on_yt_download_started)
        dialog.download_progress.connect(self._on_yt_progress)
        dialog.download_finished.connect(self._on_yt_finished)
        dialog.download_name_updated.connect(self._on_download_name_updated)
        if not hasattr(self, '_stream_dialogs'):
            self._stream_dialogs = []
        self._stream_dialogs.append(dialog)
        self._stream_dialogs = [d for d in self._stream_dialogs if d.isVisible() or d is dialog]
        dialog.finished.connect(lambda: self._stream_dialogs.remove(dialog) if dialog in self._stream_dialogs else None)
        dialog.show()

    def _resolve_unique_name(self, filename):
        """Return a filename that is unique against both disk and in-progress
        table rows, so concurrent downloads never collide on the same name."""
        folder = choose_folder(filename)
        base, ext = os.path.splitext(filename)
        # Collect all names currently shown in the table (any status)
        active_names = set()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                active_names.add(item.text().strip())
        unique_name = filename
        counter = 1
        while (
            os.path.exists(os.path.join(folder, unique_name))
            or unique_name in active_names
        ):
            unique_name = f"{base} ({counter}){ext}"
            counter += 1
        return unique_name

    def open_core_dialog(self, url="", filename="", referer=""):
        existing_path = self.check_already_finished(url)
        if existing_path:
            if self._show_already_downloaded_dialog(existing_path) != "rename":
                return
            # "Download with New Name" chosen -- proceed with a unique filename below
        # Pre-resolve a globally unique name (disk + in-progress table rows)
        unique_filename = self._resolve_unique_name(filename)
        dialog = CoreDownloaderDialog(self, url=url, filename=unique_filename, referer=referer, dark=self.dark_mode)
        dialog.download_started.connect(self._on_yt_download_started)
        dialog.download_progress.connect(self._on_yt_progress)
        dialog.download_finished.connect(self._on_yt_finished)
        if not hasattr(self, '_core_dialogs'):
            self._core_dialogs = []
        self._core_dialogs.append(dialog)
        self._core_dialogs = [d for d in self._core_dialogs if d.isVisible() or d is dialog]
        dialog.finished.connect(lambda: self._core_dialogs.remove(dialog) if dialog in self._core_dialogs else None)
        dialog.show()


    def _on_yt_download_started(self, url, display_name, folder):
        full_path = os.path.join(folder, display_name)
        category = get_category(display_name)

        # Resume path (or repeat-download of same URL): an existing row is
        # already registered — reuse it instead of inserting a duplicate.
        existing = self.yt_url_to_row.get(url)
        if existing is not None and 0 <= existing < self.table.rowCount():
            row = existing
            name_item = self.table.item(row, 0)
            if name_item:
                name_item.setText(f"  {display_name}")
                name_item.setIcon(get_file_icon(display_name))
                name_item.setData(Qt.ItemDataRole.UserRole, full_path)
            stat_item = self.table.item(row, 5)
            if stat_item:
                stat_item.setText("Downloading")
                self._apply_status_style(stat_item, "Downloading")
            self.row_progress[row] = 0
            self._update_progress(row, 0)
            self._update_cell(row, 2, "—")
            self._update_cell(row, 3, "—")
            self._update_cell(row, 4, "—")
            return

        row = self.table.rowCount()
        self.table.insertRow(row)
        _now = time.strftime("%Y-%m-%d %H:%M")
        self._insert_row_items(row, display_name, full_path, url, "Downloading", "—", category, _now)
        self.row_progress[row] = 0
        self.yt_url_to_row[url] = row
        current_cat = CATEGORIES[self._current_cat_row][0]
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
            print(f"[warn] _on_yt_finished dropped: no row for status={status} url={url[:120]}", flush=True)
            return
        stat_item = self.table.item(row, 5)
        if stat_item:
            stat_item.setText(status)
            self._apply_status_style(stat_item, status)
            if status == "Finished":
                self._update_progress(row, 100)
                self._update_cell(row, 4, "—")
                name_item = self.table.item(row, 0)
                filename = name_item.text().strip() if name_item else ""
                path = name_item.data(Qt.ItemDataRole.UserRole) if name_item else ""
                # yt-dlp reports per-stream bytes during progress (audio track
                # alone for a/v merges), so the final merged size is only known
                # after the file is written — read it off disk now.
                if path and os.path.exists(path):
                    disk_size = format_size(os.path.getsize(path))
                    self._update_cell(row, 2, f"{disk_size} / {disk_size}")
                size = self.table.item(row, 2).text() if self.table.item(row, 2) else "—"
                category = get_category(filename)
                self._add_to_history(url, filename, path, "Finished", size, category)
                self.finished_urls[self._social_dedup_key(url)] = path
                self._notify("Download Complete", f"{filename} finished downloading.")
                self._maybe_shutdown()
            else:
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

    def _on_download_name_updated(self, url, new_filename, new_path):
        row = self.yt_url_to_row.get(url)
        if row is None:
            return
        name_item = self.table.item(row, 0)
        if name_item:
            name_item.setText(f"  {new_filename}")
            name_item.setIcon(get_file_icon(new_filename))
            name_item.setData(Qt.ItemDataRole.UserRole, new_path)
        self._update_progress(row, 0)
        stat_item = self.table.item(row, 5)
        if stat_item:
            stat_item.setText("Downloading")
            self._apply_status_style(stat_item, "Downloading")

    def _on_worker_name_finalized(self, row, filename, path):
        """Sync row display + stored path with the worker's authoritative
        on-disk filename.  Called after the worker passes its final
        uniqueness check, before the first byte is written."""
        if row is None or row < 0 or row >= self.table.rowCount():
            return
        name_item = self.table.item(row, 0)
        if name_item:
            name_item.setText(f"  {filename}")
            name_item.setIcon(get_file_icon(filename))
            name_item.setData(Qt.ItemDataRole.UserRole, path)

    def _reconcile_stalled_downloads(self):
        # A row can be stuck on "Downloading" if the worker thread hung
        # after writing the file, or if the finished signal was dropped
        # (yt_url_to_row mapping missing). Reconcile from on-disk state.
        for row_info in self.all_rows:
            row = row_info["row"]
            stat_item = self.table.item(row, 5)
            if not stat_item or stat_item.text() != "Downloading":
                continue
            name_item = self.table.item(row, 0)
            if not name_item:
                continue
            path = name_item.data(Qt.ItemDataRole.UserRole) or ""
            url  = name_item.data(Qt.ItemDataRole.UserRole + 2) or ""
            if not path or not os.path.exists(path) or os.path.getsize(path) <= 0:
                continue
            if any(getattr(t, "url", None) == url and t.isRunning() for t in self.threads):
                continue
            filename  = name_item.text().strip()
            disk_size = format_size(os.path.getsize(path))
            self._update_cell(row, 2, f"{disk_size} / {disk_size}")
            self._update_cell(row, 3, "—")
            self._update_cell(row, 4, "—")
            stat_item.setText("Finished")
            self._apply_status_style(stat_item, "Finished")
            self._update_progress(row, 100)
            if url:
                self.finished_urls[self._social_dedup_key(url)] = path
            self._add_to_history(url, filename, path, "Finished",
                                 f"{disk_size} / {disk_size}",
                                 get_category(filename))
            print(f"[reconcile] Marked stalled download Finished: {filename}", flush=True)

    def _update_taskbar_progress(self):
        self._reconcile_stalled_downloads()
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
        self._refresh_status_chip()

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
            # pvvstream CDN — same video is re-issued with a fresh ?secure= token
            # on every page load.  Key on VIDEO_ID + RES_ID so recaptures of the
            # same video are correctly recognised across token refreshes.
            _pv = re.search(r'/videos/([^/]+)/([^/]+)/vid_\w+\.mp4', url, re.I)
            if _pv:
                return f'pvv_{_pv.group(1)}_{_pv.group(2)}'
        except Exception:
            pass
        return url

    def check_already_finished(self, url):
        key = self._social_dedup_key(url)
        path = self.finished_urls.get(key)
        if path is None:
            return None
        # If the file no longer exists on disk (deleted, moved, renamed),
        # treat it as never downloaded and remove the stale entry so it
        # never causes a false-positive again.
        if not os.path.exists(path):
            del self.finished_urls[key]
            return None
        return path

    def _show_already_downloaded_dialog(self, existing_path):
        """
        Show a themed dialog when a URL was already downloaded.
        Returns 'rename'  → proceed with a new auto-generated filename.
        Returns 'skip'    → do nothing.
        """
        t = self._theme()
        accent = t.get("accent", "#2563eb")

        dialog = QDialog(self)
        dialog.setWindowTitle("Already Downloaded")
        dialog.setFixedWidth(400)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {t['surface']};
                color: {t['text']};
            }}
            QLabel {{ color: {t['text']}; background: transparent; }}
            QPushButton {{
                border-radius: 10px;
                font-size: 13px;
                font-weight: 600;
                padding: 9px 22px;
                border: none;
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        # -- Icon + title row
        title_row = QHBoxLayout()
        icon_lbl = QLabel("\u26a0\ufe0f")
        icon_lbl.setStyleSheet("font-size: 26px; background: transparent;")
        title_lbl = QLabel("Already Downloaded")
        title_lbl.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {t['text']};")
        title_row.addWidget(icon_lbl)
        title_row.addSpacing(8)
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        layout.addLayout(title_row)

        # -- Body
        fname = os.path.basename(existing_path)
        body = QLabel(
            f"<b>{fname}</b> has already been downloaded.<br>"
            f"<span style='color:{t['muted']};font-size:12px;'>"
            f"What would you like to do with this new download?</span>"
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size: 13px; color: {t['text']};")
        layout.addWidget(body)

        layout.addSpacing(6)

        # -- Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_rename = QPushButton("\u2b07  Download with New Name")
        btn_rename.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: #ffffff;
            }}
            QPushButton:hover {{
                background-color: {accent}cc;
            }}
        """)

        btn_skip = QPushButton("Skip")
        btn_skip.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['bg']};
                color: {t['muted']};
                border: 1px solid {t['border']};
            }}
            QPushButton:hover {{
                background-color: {t['category_hover']};
                color: {t['text']};
            }}
        """)

        result = ["skip"]
        btn_rename.clicked.connect(lambda: (result.__setitem__(0, "rename"), dialog.accept()))
        btn_skip.clicked.connect(dialog.reject)

        btn_row.addStretch()
        btn_row.addWidget(btn_skip)
        btn_row.addWidget(btn_rename)
        layout.addLayout(btn_row)

        dialog.exec()
        return result[0]

    def show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        t = self._theme()
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {t['surface']};
                color: {t['text']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 5px;
                font-size: 13px;
            }}
            QMenu::item {{ padding: 8px 18px; border-radius: 5px; }}
            QMenu::item:selected {{
                background-color: {t['menu_hover']};
                color: {t['menu_hover_text']};
            }}
        """)

        stat_item = self.table.item(row, 5)
        status = stat_item.text() if stat_item else ""

        open_act        = menu.addAction("Open")
        open_folder_act = menu.addAction("Open in Folder")
        menu.addSeparator()
        rename_act = menu.addAction("Rename")
        remove_act = menu.addAction("Remove")
        menu.addSeparator()
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

        path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) if self.table.item(row, 0) else None

        if action == open_act:
            if path and os.path.exists(path):
                subprocess.Popen(['xdg-open', path])
            else:
                self._show_toast("File not found on disk")

        elif action == open_folder_act:
            if path and os.path.exists(path):
                open_and_select(path)
            elif path and os.path.isdir(os.path.dirname(path)):
                # File gone but its folder still exists — open the folder
                # (no highlight is possible without the file) and tell the
                # user why nothing got selected.
                subprocess.Popen(['xdg-open', os.path.dirname(path)])
                self._show_toast("File missing — opened its folder")
            else:
                self._show_toast("Folder not found on disk")

        elif action == rename_act:
            if path and os.path.exists(path):
                from PyQt6.QtWidgets import QInputDialog
                old_name = os.path.basename(path)
                new_name, ok = QInputDialog.getText(self, "Rename", "New filename:", text=old_name)
                if ok and new_name.strip() and new_name.strip() != old_name:
                    new_path = os.path.join(os.path.dirname(path), new_name.strip())
                    try:
                        os.rename(path, new_path)
                        name_item = self.table.item(row, 0)
                        if name_item:
                            name_item.setText(new_name.strip())
                            name_item.setData(Qt.ItemDataRole.UserRole, new_path)
                            # Update history so the new name/path persists across restarts
                            url = name_item.data(Qt.ItemDataRole.UserRole + 2) or ''
                            for entry in self.history:
                                if entry.get('url') == url or entry.get('path') == path:
                                    entry['filename'] = new_name.strip()
                                    entry['path']     = new_path
                                    break
                            save_history(self.history)
                    except Exception as e:
                        QMessageBox.warning(self, "Rename", f"Could not rename:\n{e}")

        elif action == remove_act:
            self.table.removeRow(row)
            self.all_rows = [r for r in self.all_rows if r.get('row') != row]

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

        # Reset row status
        stat_item = self.table.item(row, 5)
        if stat_item:
            stat_item.setText("Downloading")
            self._apply_status_style(stat_item, "Downloading")
        self._update_cell(row, 3, "—")
        self._update_cell(row, 4, "—")
        category = get_category(filename)

        # YouTube: restart from scratch via the full YT dialog.
        # Saved settings (if any) let us skip the Fetch/quality step.
        if is_youtube_url(url):
            folder = os.path.dirname(path) if path else os.path.join(HOME, "Downloads", "Videos")
            os.makedirs(folder, exist_ok=True)
            base = os.path.splitext(os.path.basename(path or filename))[0] or "video"
            # Scrub partial files so yt-dlp truly starts fresh.
            for partial in glob.glob(os.path.join(folder, glob.escape(base) + ".*")):
                try:
                    os.remove(partial)
                except OSError:
                    pass

            self.row_progress[row] = 0
            self._update_progress(row, 0)
            self._update_cell(row, 2, "—")
            self.yt_url_to_row[url] = row

            # Close any leftover YT dialog (and Stream dialog) for this URL so
            # the user isn't juggling the old cancelled window alongside the new one.
            for d in list(getattr(self, "_yt_dialogs", [])):
                try:
                    d_url = getattr(d, "_current_url", "") or d.url_input.text().strip()
                    if d_url == url:
                        d.close()
                except Exception:
                    pass
            for d in list(getattr(self, "_stream_dialogs", [])):
                try:
                    if getattr(d, "_url", "") == url:
                        d.close()
                except Exception:
                    pass

            settings = self.yt_settings.get(url)
            dialog = self.open_youtube_dialog(prefill_url=url, skip_fetch=bool(settings))
            if settings:
                dialog.start_with_saved_settings(url, settings, base)
            return

        # HLS/DASH manifests can't be byte-resumed — the URL points to a
        # playlist, not the media. Curling it would save the manifest text
        # as the .mp4 (pseudo file). Re-run through the stream downloader
        # from scratch instead, after scrubbing any garbage left behind.
        url_path_lower = url.split("?", 1)[0].lower()
        if url_path_lower.endswith(".m3u8") or url_path_lower.endswith(".mpd"):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
            self.row_progress[row] = 0
            self._update_progress(row, 0)
            self._update_cell(row, 2, "—")
            self.open_stream_dialog(
                url=url,
                filename=filename or "stream.mp4",
                page_referer="",
            )
            return

        # HTTP download: use byte-offset resume
        resume_from = 0
        if path and os.path.exists(path):
            resume_from = os.path.getsize(path)
        self._update_progress(row, 0 if resume_from == 0 else int(resume_from / max(resume_from + 1, 1) * 100))
        thread = DownloadThread(url, filename, False, "", resume_from)
        self.threads.append(thread)
        thread.progress.connect(  lambda v, r=row: self._update_progress(r, v))
        thread.downloaded.connect(lambda s, r=row: self._update_cell(r, 2, s))
        thread.speed.connect(     lambda s, r=row: self._update_cell(r, 3, s))
        thread.eta.connect(       lambda e, r=row: self._update_cell(r, 4, e))
        thread.name_finalized.connect(lambda n, p, r=row: self._on_worker_name_finalized(r, n, p))
        thread.finished.connect(  lambda m, r=row, u=url, c=category: self._on_finished(m, r, u, c))
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
                # video.twimg.com .m4s URLs are DASH media segments — even
                # though they return content-type: video/mp4, they only
                # contain styp/moof/mdat boxes, no ftyp/moov, so they're not
                # playable standalone. The extension also forwards the tweet
                # page URL as referer; yt-dlp's TwitterIE can extract the
                # full video from that. Swap the .m4s for the status URL.
                if is_twimg_dash_segment(norm_url) and re.search(
                    r'(?:twitter\.com|x\.com)/[^/]+/status/\d+', norm_referer or ''
                ):
                    norm_url = norm_referer
                self.open_stream_dialog(
                    url=norm_url,
                    filename=filename if filename else "stream.mp4",
                    page_referer=norm_referer,
                )
                continue
            # Browser-intercepted file download → Core Downloader dialog
            if msg_type == "file":
                _url_name    = url.split("?")[0].split("/")[-1] or ""
                default_name = filename if filename else (_url_name or "download")
                self.raise_(); self.activateWindow()
                self.open_core_dialog(url=url, filename=default_name, referer=referer)
                continue
            # video_stream: direct video URL from capture button → main table
            default_name = "video.mp4" if msg_type == "video_stream" else "download"
            self._check_and_enqueue(url, filename if filename else default_name, False, referer)
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
        # No extension or page extension = video hosting page, try yt-dlp
        if not ext or ext in page_exts:
            ts = time.strftime("%Y-%m-%d_%H-%M-%S")
            self.open_stream_dialog(url=normalize_stream_url(url), filename=f"video_{ts}.mp4")
            return
        # Direct video files (mp4/mkv/...) download via HTTP — yt-dlp's generic
        # extractor fetches the URL as a webpage first, which adds no value here
        # and breaks on CDNs with non-clean TLS shutdowns (SSL EOF).
        is_video = ".m3u8" in lurl or "vimeo" in lurl
        if not name:
            name = "download"
        self._check_and_enqueue(url, name, is_video, "")

    def _check_and_enqueue(self, url, filename, is_video=False, referer=""):
        existing_path = self.check_already_finished(url)
        if existing_path:
            if self._show_already_downloaded_dialog(existing_path) != "rename":
                return
            # "Download with New Name" chosen -- _enqueue auto-resolves a unique filename
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
        self.row_progress[row] = 0

        current_cat = CATEGORIES[self._current_cat_row][0]
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
        thread.name_finalized.connect(lambda n, p, r=row: self._on_worker_name_finalized(r, n, p))
        thread.finished.connect(  lambda m, r=row, u=url, c=category: self._on_finished(m, r, u, c))
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
            new_item.setFlags(new_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col == 5:
                new_item.setToolTip(text)
            self.table.setItem(row, col, new_item)
        # Keep the file-list sub-meta (EXT · TOTAL_SIZE) in sync with the
        # Downloaded cell. Use the total side of "done / total" when present.
        if col == 2:
            name_item = self.table.item(row, 0)
            if name_item is not None and text:
                total = text.split(" / ", 1)[1].strip() if " / " in text else text.strip()
                if total and total != "—":
                    name_item.setData(FL_ROLE_TOTAL, total)
        # Speed/ETA/status changes on the selected row need to flow into the
        # bottom status chip (since those columns are hidden from the table).
        if col in (3, 4, 5) and row == self.table.currentRow():
            self._refresh_status_chip()

    def _on_finished(self, msg, row, url, category):
        # Read filename and path from the live row — the worker may have
        # finalized a different name than what was captured at enqueue
        # (Content-Disposition override, second uniqueness pass, etc).
        # Using stale captured values caused Open File to silently open the
        # wrong path and history to record bogus filenames.
        name_item = self.table.item(row, 0)
        filename  = name_item.text().strip() if name_item else ""
        path      = name_item.data(Qt.ItemDataRole.UserRole) if name_item else ""
        item = self.table.item(row, 5)
        if item:
            item.setText(msg)
            self._apply_status_style(item, msg)
            if msg == "Finished":
                self._update_progress(row, 100)
                self._update_cell(row, 4, "—")
                if path:
                    self.finished_urls[self._social_dedup_key(url)] = path
                # Use the actual on-disk size; multi-stream YT downloads report
                # per-stream bytes during progress, so the final merged size is
                # only known after the file is written.
                if path and os.path.exists(path):
                    disk_size = format_size(os.path.getsize(path))
                    self._update_cell(row, 2, f"{disk_size} / {disk_size}")
                size = self.table.item(row, 2).text() if self.table.item(row, 2) else "—"
                self._add_to_history(url, filename, path, "Finished", size, category)
                self._notify("Download Complete", f"{filename} finished downloading.")
                self._maybe_shutdown()
            else:
                self._update_cell(row, 3, "—")
                self._update_cell(row, 4, "—")
                # save cancelled/failed so they survive restart and can be resumed
                size = self.table.item(row, 2).text() if self.table.item(row, 2) else "—"
                pct  = self.row_progress.get(row, 0)
                self._add_to_history(url, filename, path, msg, size, category, pct)

    def _resume_selected(self):
        row = self.table.currentRow()
        if row < 0:
            self._show_toast("Select a download to resume")
            return
        stat_item = self.table.item(row, 5)
        status = stat_item.text() if stat_item else ""
        if status == "Downloading":
            self._show_toast("Already downloading")
        elif status in ("Finished", "File Missing"):
            self._show_toast("Nothing to resume — download is already finished")
        elif status == "":
            self._show_toast("Select an interrupted download to resume")
        else:
            self._resume_download(row)

    def _on_selection_changed(self):
        self._refresh_status_chip()

    def _refresh_status_chip(self):
        """Show speed + ETA in the bottom status row when the selected row
        is currently downloading. Hide the chip otherwise."""
        if not hasattr(self, "_status_metric"):
            return
        row = self.table.currentRow()
        if row < 0:
            self._status_metric.hide()
            return
        stat_item = self.table.item(row, 5)
        if not stat_item or stat_item.text() != "Downloading":
            self._status_metric.hide()
            return
        speed = (self.table.item(row, 3).text() if self.table.item(row, 3) else "").strip()
        eta   = (self.table.item(row, 4).text() if self.table.item(row, 4) else "").strip()
        if (not speed or speed == "—") and (not eta or eta == "—"):
            self._status_metric.hide()
            return
        self._status_speed_label.setText(f"↓ {speed}" if speed and speed != "—" else "")
        self._status_eta_label.setText(f"{eta} left" if eta and eta != "—" else "")
        self._status_metric.show()
    
    def _open_donate(self):
        t = self._theme()
        accent = t.get("accent", "#2563eb")
        dialog = QDialog(self)
        dialog.setWindowTitle("Support Development")
        dialog.setFixedWidth(420)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {t['surface']};
                color: {t['text']};
            }}
            QLabel {{ color: {t['text']}; background: transparent; }}
            QPushButton {{ border-radius: 14px; font-size: 13px; font-weight: 600; padding: 10px 24px; border: none; }}
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(8)

        title = QLabel("Support Development")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {t['text']};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Scan with Binance App to donate")
        sub.setStyleSheet(f"font-size: 12px; color: {t['muted']};")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        layout.addSpacing(6)

        qr_label = QLabel()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        qr_path = os.path.join(script_dir, "icons", "binance_pay.png")
        qr_pix = QPixmap(qr_path)
        if not qr_pix.isNull():
            qr_pix = qr_pix.scaled(340, 340, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        qr_label.setPixmap(qr_pix)
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_label.setStyleSheet(f"border: 1px solid {t['border']}; border-radius: 12px; padding: 8px; background: #ffffff;")
        layout.addWidget(qr_label)

        layout.addSpacing(6)

        user_card = QWidget()
        user_card.setStyleSheet(f"background-color: {t['bg']}; border-radius: 14px;")
        user_card_layout = QVBoxLayout(user_card)
        user_card_layout.setContentsMargins(16, 10, 16, 10)
        user_label = QLabel("User-ec639")
        user_label.setStyleSheet(f"font-size: 14px; font-weight: 700; color: #d97706;")
        user_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_card_layout.addWidget(user_label)
        layout.addWidget(user_card)

        layout.addSpacing(4)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['bg']};
                color: {t['muted']};
                border: none;
                border-radius: 14px;
                padding: 10px 24px;
            }}
            QPushButton:hover {{
                background-color: {t['category_hover']};
                color: {t['text']};
            }}
        """)
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

    def _other_row_owns_path(self, exclude_row, path):
        """True if any other row stores the same on-disk path. Prevents
        deleting a different row's properly-downloaded file when the user
        clears an unrelated incomplete entry that happens to share filename
        (e.g. enqueue computed a stale (1)/(2) suffix, or two history rows
        point at the same name)."""
        if not path:
            return False
        try:
            norm = os.path.normpath(os.path.abspath(path))
        except Exception:
            norm = path
        for r in range(self.table.rowCount()):
            if r == exclude_row:
                continue
            it = self.table.item(r, 0)
            if not it:
                continue
            p = it.data(Qt.ItemDataRole.UserRole)
            if not p:
                continue
            try:
                if os.path.normpath(os.path.abspath(p)) == norm:
                    return True
            except Exception:
                if p == path:
                    return True
        return False

    def _delete_partials_for_row(self, row):
        """Delete any on-disk partial files for an unfinished download row."""
        name_item = self.table.item(row, 0)
        stat_item = self.table.item(row, 5)
        if not name_item or not stat_item:
            return
        status = stat_item.text()
        if status == "Finished":
            return
        path = name_item.data(Qt.ItemDataRole.UserRole)
        url  = name_item.data(Qt.ItemDataRole.UserRole + 2)
        if not path:
            return
        folder = os.path.dirname(path)
        if url and is_youtube_url(url) and folder and os.path.isdir(folder):
            # yt-dlp produces <base>.mp4, <base>.f137.mp4, <base>.f251.m4a,
            # <base>.*.part, <base>.*.ytdl ...  — glob-clean the lot, but skip
            # any artefact another row claims as its final on-disk file.
            base = os.path.splitext(os.path.basename(path))[0]
            if base:
                for f in glob.glob(os.path.join(folder, glob.escape(base) + ".*")):
                    if self._other_row_owns_path(row, f):
                        continue
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            return
        # Plain HTTP download: the file and any sibling .part
        if self._other_row_owns_path(row, path):
            # Another row owns the same final path — only the .part is safe
            # to remove (the completed file belongs to the other row).
            part = path + ".part"
            if os.path.exists(part):
                try:
                    os.remove(part)
                except OSError:
                    pass
            return
        for candidate in (path, path + ".part"):
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    def clear_item(self):
        row = self.table.currentRow()
        if row >= 0:
            self._delete_partials_for_row(row)
            name_item = self.table.item(row, 0)
            if name_item:
                url  = name_item.data(Qt.ItemDataRole.UserRole + 2)
                path = name_item.data(Qt.ItemDataRole.UserRole)
                if url:
                    # Filter history by (url, path) pair — a single URL can
                    # legitimately have multiple history entries (re-download
                    # after rename, "Download with New Name", etc).  Removing
                    # by URL alone wiped the still-good sibling entry.
                    before = len(self.history)
                    self.history = [
                        e for e in self.history
                        if not (e.get("url") == url and e.get("path") == path)
                    ]
                    if len(self.history) == before and path:
                        # No (url, path) match — fall back to URL-only so
                        # legacy entries without a path field still clear.
                        self.history = [e for e in self.history if e.get("url") != url]
                    save_history(self.history)
                    # Only drop the cached "already finished" mapping if no
                    # other row still owns that URL's final file.
                    if not any(
                        self.table.item(r, 0)
                        and self.table.item(r, 0).data(Qt.ItemDataRole.UserRole + 2) == url
                        for r in range(self.table.rowCount()) if r != row
                    ):
                        self.finished_urls.pop(self._social_dedup_key(url), None)
                        self.yt_settings.pop(url, None)
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
        for row in range(self.table.rowCount()):
            self._delete_partials_for_row(row)
        self.history = []
        save_history(self.history)
        self.finished_urls = {}
        self.yt_settings = {}
        self.table.setRowCount(0)
        self.all_rows = []
        self.row_progress = {}
        self.yt_url_to_row = {}
        self.threads = [t for t in self.threads if t.isRunning()]
        self._update_category_counts()


def _ensure_ytdlp_config():
    """YouTube's current bot protection needs a JS challenge solver that yt-dlp
    fetches from GitHub on first use. Without --remote-components ejs:github
    the fetch is blocked and extraction silently returns no formats."""
    cfg_dir = os.path.expanduser("~/.config/yt-dlp")
    cfg_path = os.path.join(cfg_dir, "config")
    flag = "--remote-components ejs:github"
    try:
        os.makedirs(cfg_dir, exist_ok=True)
        existing = ""
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                existing = f.read()
        if flag not in existing:
            with open(cfg_path, "a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write(flag + "\n")
    except OSError:
        pass


def _load_dialog_fonts():
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
    if not os.path.isdir(fonts_dir):
        return
    for fname in os.listdir(fonts_dir):
        if fname.lower().endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(fonts_dir, fname))


if __name__ == "__main__":
    if not os.environ.get("QT_QPA_PLATFORMTHEME"):
        os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"
    _ensure_ytdlp_config()
    app = QApplication(sys.argv)
    app.setApplicationName("Linux Download Manager")
    # Ties the window to its .desktop file so the correct icon/app-id is used
    # under Wayland (and X11 WM_CLASS) — required for Flatpak icon association.
    app.setDesktopFileName("io.github.matewinslet.LinuxDownloader")
    _load_dialog_fonts()
    window = DownloadManager()
    window.show()
    sys.exit(app.exec())
