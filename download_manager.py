#!/usr/bin/env python3
# Linux Download Manager
# Copyright (c) 2026 Tanjim — tpodbcs@gmail.com
# All rights reserved. See LICENSE.txt for details.

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
    QProgressBar, QTextEdit, QSizePolicy,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QStackedWidget
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QSize, QRect, QPointF, QRectF
from PyQt6.QtGui import (
    QIcon, QColor, QFont, QPainter, QAction, QPixmap,
    QLinearGradient, QPalette, QPainterPath, QBrush, QFontDatabase, QFontMetrics
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

os.makedirs(CONFIG_DIR, exist_ok=True)



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
    "Programs":   ["exe", "bin", "appimage", "deb", "rpm"]
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
        w = int(br.width() + self._letter_spacing * max(0, len(self.text()) - 1) + 10)
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
        path.addText(QPointF(4, 0), font, self.text())
        br = path.boundingRect()
        # Vertically center the glyph bounds inside the widget.
        offset_y = (self.height() - br.height()) / 2.0 - br.top()
        p.translate(0, offset_y)
        grad = QLinearGradient(0, br.top(), 0, br.bottom())
        grad.setColorAt(0.0, self._shift_lightness(self._accent,  0.08))
        grad.setColorAt(1.0, self._shift_lightness(self._accent, -0.10))
        p.fillPath(path, QBrush(grad))


# ── Numeric column delegate (font override only) ─────────────────────────────
class NumericFontDelegate(QStyledItemDelegate):
    """Applies a given font family/weight to its column without changing
    colors, selection, or any other native rendering."""

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


class FilenameFontDelegate(QStyledItemDelegate):
    """Keeps the primary Latin font but appends every installed non-Latin
    family as a fallback. Qt picks a fallback per-glyph only when the
    primary font lacks the glyph, so Latin rendering is unchanged and
    any script (Bengali, CJK, Arabic, Devanagari, Thai, Hebrew, …) gets
    a real glyph instead of tofu."""

    _fallbacks_cached = None

    @classmethod
    def _fallbacks(cls):
        if cls._fallbacks_cached is not None:
            return cls._fallbacks_cached
        try:
            WS = QFontDatabase.WritingSystem
            # Latin is covered by the primary font; Any/Symbol aren't scripts.
            skip = {WS.Any, WS.Latin, WS.Symbol}
            seen = set()
            ordered = []
            # Pin Noto Sans Bengali UI first when present (matches Firefox's pick).
            for f in QFontDatabase.families(WS.Bengali) or []:
                if 'Noto Sans Bengali UI' in f and f not in seen:
                    seen.add(f)
                    ordered.append(f)
            for ws in WS:
                if ws in skip:
                    continue
                for f in QFontDatabase.families(ws) or []:
                    if f not in seen:
                        seen.add(f)
                        ordered.append(f)
            cls._fallbacks_cached = ordered
        except Exception:
            cls._fallbacks_cached = []
        return cls._fallbacks_cached

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        fallbacks = self._fallbacks()
        if not fallbacks:
            return
        f = QFont(option.font)
        f.setFamilies([f.family()] + fallbacks)
        option.font = f


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
            bg_even  = QColor("#0f172a")
            bg_odd   = QColor("#0f172a")
            sel_color = QColor(59, 130, 246, 38)
            track_color = QColor(255, 255, 255, 15)
        else:
            bg_even  = QColor("#ffffff")
            bg_odd   = QColor("#f8fafc")
            sel_color = QColor("#eff6ff")
            track_color = QColor("#f1f5f9")

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, sel_color)
        else:
            painter.fillRect(option.rect, bg_even if index.row() % 2 == 0 else bg_odd)

        # Thin 6 px bar, centered vertically, full width — blue = in-progress, green = done
        bar_h = 6
        bar_rect = QRect(
            option.rect.x() + 12,
            option.rect.y() + (option.rect.height() - bar_h) // 2,
            option.rect.width() - 24,
            bar_h,
        )
        radius = bar_h // 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(bar_rect, radius, radius)

        finished = value >= 100
        if value > 0:
            filled_w = int(bar_rect.width() * value / 100)
            filled_rect = QRect(bar_rect.x(), bar_rect.y(), filled_w, bar_rect.height())
            grad = QLinearGradient(bar_rect.x(), 0, bar_rect.right(), 0)
            if finished:
                grad.setColorAt(0.0, QColor("#16a34a"))
                grad.setColorAt(1.0, QColor("#4ade80"))
            else:
                grad.setColorAt(0.0, QColor("#3b82f6"))
                grad.setColorAt(1.0, QColor("#60a5fa"))
            painter.setBrush(grad)
            painter.drawRoundedRect(filled_rect, radius, radius)

            if 0 < value < 100 and filled_w > 0:
                phase = (time.time() % 1.2) / 1.2
                shimmer_w = max(30, filled_w // 3)
                shimmer_x = bar_rect.x() + int((filled_w - shimmer_w) * phase)
                shimmer_grad = QLinearGradient(shimmer_x, 0, shimmer_x + shimmer_w, 0)
                shimmer_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
                shimmer_grad.setColorAt(0.5, QColor(255, 255, 255, 70))
                shimmer_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.setBrush(shimmer_grad)
                painter.drawRoundedRect(filled_rect, radius, radius)

    def sizeHint(self, option, index):
        return QSize(180, 40)


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
                self.formats_ready.emit(title)
        except Exception as e:
            print(f"[YT-FETCH ERROR] {e}", flush=True)
            self.error.emit(str(e)[:200])


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
            self.ydl_opts['noplaylist'] = True
            self.ydl_opts['cookiesfrombrowser'] = ('firefox', get_firefox_profile())
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if info is None:
                    raise Exception("Could not download video")
            self.finished.emit("Finished")
        except Exception as e:
            self.finished.emit(f"Error: {str(e)[:80]}")

    def hook(self, d):
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


# ── YouTube dialog ───────────────────────────────────────────────────────────
class YouTubeDialog(QDialog):
    download_started    = pyqtSignal(str, str, str)
    download_progress   = pyqtSignal(str, int, str, str, str)
    download_finished   = pyqtSignal(str, str)
    yt_settings_captured = pyqtSignal(str, dict)  # url, {mode, quality, audio_fmt}

    def __init__(self, parent=None, prefill_url="", dark=True, skip_fetch=False):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle("LDM YouTube Downloader")
        self.setMinimumWidth(540)
        self.setMinimumHeight(552)
        self._dark = dark
        self.setStyleSheet(make_dialog_style(dark))
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
            if not skip_fetch:
                self.fetch_formats()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("YouTube Downloader")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {'#f85149' if self._dark else '#cf222e'};")
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
        self.title_label.setStyleSheet(f"color: {'#8b949e' if self._dark else '#656d76'}; font-size: 12px;")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        type_group = QGroupBox("Download Type")
        type_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        type_layout = QHBoxLayout(type_group)
        type_layout.setContentsMargins(8, 10, 8, 6)
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
        quality_row.setContentsMargins(0, 0, 0, 0)
        quality_row.setSpacing(6)
        quality_label = QLabel("Quality:")
        quality_label.setFixedWidth(55)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Best", "1080p", "720p", "480p", "360p"])
        self.quality_combo.setStyleSheet("QComboBox { min-height: 27px; max-height: 27px; padding: 4px 12px; }")
        _accent = '#2f81f7' if self._dark else '#0969da'
        self.quality_combo.view().setMouseTracking(True)
        self.quality_combo.view().viewport().setMouseTracking(True)
        self.quality_combo.view().setItemDelegate(ComboHoverDelegate(_accent, self.quality_combo))
        quality_row.addWidget(quality_label)
        quality_row.addWidget(self.quality_combo)
        layout.addLayout(quality_row)

        self.audio_fmt_widget = QWidget()
        self.audio_fmt_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        audio_fmt_row = QHBoxLayout(self.audio_fmt_widget)
        audio_fmt_row.setContentsMargins(0, 0, 0, 0)
        audio_fmt_row.setSpacing(6)
        audio_fmt_label = QLabel("Format:")
        audio_fmt_label.setFixedWidth(55)
        self.audio_fmt_combo = QComboBox()
        self.audio_fmt_combo.setStyleSheet("QComboBox { min-height: 27px; max-height: 27px; padding: 4px 12px; }")
        self.audio_fmt_combo.addItems(["mp3", "m4a", "flac", "wav", "ogg", "aac"])
        self.audio_fmt_combo.view().setMouseTracking(True)
        self.audio_fmt_combo.view().viewport().setMouseTracking(True)
        self.audio_fmt_combo.view().setItemDelegate(ComboHoverDelegate(_accent, self.audio_fmt_combo))
        audio_fmt_row.addWidget(audio_fmt_label)
        audio_fmt_row.addWidget(self.audio_fmt_combo)
        self.audio_fmt_widget.setVisible(False)
        layout.addWidget(self.audio_fmt_widget)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet(f"color: {'#8b949e' if self._dark else '#656d76'}; font-size: 12px;")
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
        self.close_btn.setStyleSheet(make_close_btn_style(self._dark))
        self.close_btn.clicked.connect(self.close)

        self.open_file_btn = QPushButton("Open")
        self.open_file_btn.setStyleSheet(
            "QPushButton { background-color: #0ea5e9; color: white; }"
            "QPushButton:hover { background-color: #0284c7; }"
        )
        self.open_file_btn.setVisible(False)
        self.open_file_btn.clicked.connect(self._open_downloaded_file)

        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setStyleSheet(
            "QPushButton { background-color: #64748b; color: white; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._open_downloaded_folder)

        btn_row.addWidget(self.cancel_dl_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.open_file_btn)
        btn_row.addWidget(self.open_folder_btn)
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

    def _build_yt_params(self, settings, safe_title):
        """Return (ydl_opts, folder, display_name) for the given settings."""
        mode      = settings.get("mode", "combined")
        quality   = settings.get("quality", "Best")
        audio_fmt = settings.get("audio_fmt", "mp3")
        if mode == "audio":
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
        elif mode == "video_only":
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
        return ydl_opts, folder, display_name

    def _current_settings(self):
        if self.radio_audio.isChecked():
            mode = "audio"
        elif self.radio_video_only.isChecked():
            mode = "video_only"
        else:
            mode = "combined"
        return {
            "mode":      mode,
            "quality":   self.quality_combo.currentText(),
            "audio_fmt": self.audio_fmt_combo.currentText(),
        }

    def _kick_off(self, url, settings, safe_title):
        """Build opts, show progress UI, and launch the yt-dlp thread."""
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

        ydl_opts, folder, display_name = self._build_yt_params(settings, safe_title)
        self._dl_folder = folder
        self._dl_base   = safe_title
        self.open_file_btn.setVisible(False)
        self.open_folder_btn.setVisible(False)
        self.download_btn.setVisible(True)
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
        self.log_box.append("Starting download...")

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            return
        safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', self.video_title)[:80].strip() or "video"
        self._kick_off(url, self._current_settings(), safe_title)

    def start_with_saved_settings(self, url, settings, safe_title):
        """Resume path: skip format fetch, jump straight to downloading."""
        self.url_input.setText(url)
        mode = settings.get("mode", "combined")
        if mode == "audio":
            self.radio_audio.setChecked(True)
        elif mode == "video_only":
            self.radio_video_only.setChecked(True)
        else:
            self.radio_video.setChecked(True)
        q = settings.get("quality", "Best")
        idx = self.quality_combo.findText(q)
        if idx >= 0:
            self.quality_combo.setCurrentIndex(idx)
        af = settings.get("audio_fmt", "mp3")
        idx = self.audio_fmt_combo.findText(af)
        if idx >= 0:
            self.audio_fmt_combo.setCurrentIndex(idx)
        self.video_title = safe_title
        self.title_label.setText(f"Resuming: {safe_title}")
        self._kick_off(url, settings, safe_title)

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
            self.download_btn.setVisible(False)
            self.open_file_btn.setVisible(True)
            self.open_folder_btn.setVisible(True)
        else:
            self.log_box.append(msg)
            self.info_label.setText(msg)
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


# ── Main download thread ─────────────────────────────────────────────────────

# ── Stream dialog ─────────────────────────────────────────────────────────────
class StreamDialog(QDialog):
    download_started  = pyqtSignal(str, str, str)
    download_progress = pyqtSignal(str, int, str, str, str)
    download_finished = pyqtSignal(str, str)
    download_name_updated = pyqtSignal(str, str, str)  # url, new_filename, new_path

    def __init__(self, parent=None, url="", filename="", page_referer="", dark=True):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle("LDM Stream Downloader")
        self.setMinimumWidth(520)
        self.setMinimumHeight(460)
        self._dark = dark
        self.setStyleSheet(make_dialog_style(dark))
        self._url          = url
        self._filename     = filename
        self._page_referer = page_referer
        self._last_size    = ""
        self._last_speed   = ""
        self._last_eta     = ""
        self.dl_thread     = None
        self._retried      = False
        self._force_retry  = False
        self._finished_reported = False   # guards closeEvent from stomping Finished with Cancelled
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("Stream Downloader")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {'#58a6ff' if self._dark else '#0969da'};")
        layout.addWidget(title)
        self.url_label = QLineEdit(self._url)
        self.url_label.setReadOnly(True)
        self.url_label.setStyleSheet(
            f"color: {'#8b949e' if self._dark else '#656d76'}; font-size: 12px;"
            " border: none; background: transparent; padding: 0;"
        )
        layout.addWidget(self.url_label)
        self.file_label = QLabel(f"Saving as: {self._filename}")
        self.file_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {'#e6edf3' if self._dark else '#1f2328'};")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.info_label = QLabel("")
        self.info_label.setStyleSheet(f"color: {'#8b949e' if self._dark else '#64748b'}; font-size: 12px;")
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
        self.close_btn.setStyleSheet(make_close_btn_style(self._dark))
        self.close_btn.clicked.connect(self.close)
        # Hidden paste row — shown when Facebook URL needs manual paste
        self.paste_row = QWidget()
        paste_layout = QVBoxLayout(self.paste_row)
        paste_layout.setContentsMargins(0, 0, 0, 0)
        paste_layout.setSpacing(6)
        self.paste_hint = QLabel()
        self.paste_hint.setWordWrap(True)
        self.paste_hint.setStyleSheet("color: #e3b341; font-size: 12px;")
        paste_layout.addWidget(self.paste_hint)
        self.paste_input = QLineEdit()
        self.paste_input.setPlaceholderText("Paste the copied link here...")
        _paste_bg = "#0d1117" if self._dark else "#f8fafc"
        _paste_fg = "#e6edf3" if self._dark else "#1e293b"
        self.paste_input.setStyleSheet(
            f"QLineEdit {{ background-color: {_paste_bg}; color: {_paste_fg};"
            "  border: 1px solid #f97316; border-radius: 5px;"
            "  padding: 6px 10px; font-size: 12px; }"
            "QLineEdit:focus { border: 1px solid #ea580c; }"
        )
        paste_layout.addWidget(self.paste_input)
        self.paste_row.setVisible(False)
        layout.addWidget(self.paste_row)

        self.open_file_btn = QPushButton("Open")
        self.open_file_btn.setStyleSheet(
            "QPushButton { background-color: #0ea5e9; color: white; }"
            "QPushButton:hover { background-color: #0284c7; }"
        )
        self.open_file_btn.setVisible(False)
        self.open_file_btn.clicked.connect(self._open_downloaded_file)

        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setStyleSheet(
            "QPushButton { background-color: #64748b; color: white; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._open_downloaded_folder)

        self.force_dl_btn = QPushButton("Force Download")
        self.force_dl_btn.setStyleSheet(
            "QPushButton { background-color: #d97706; color: white; }"
            "QPushButton:hover { background-color: #b45309; }"
        )
        self.force_dl_btn.setVisible(False)
        self.force_dl_btn.clicked.connect(self._start_force_download)

        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.force_dl_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.open_file_btn)
        btn_row.addWidget(self.open_folder_btn)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def _start_force_download(self):
        """Bypass yt-dlp and download directly via HTTP (curl/requests).
        Used when yt-dlp refuses due to an unusual extension (e.g. .php redirect
        that actually serves video/mp4 content)."""
        self._force_retry = True
        self.force_dl_btn.setVisible(False)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.close_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_box.append("Bypassing yt-dlp — downloading directly via HTTP...")
        self.info_label.setText("Downloading...")
        self.info_label.setStyleSheet("color: #e3b341; font-size: 12px;")

        folder = os.path.join(HOME, "Downloads", "Videos")
        os.makedirs(folder, exist_ok=True)
        display_name = self._resolve_display_name(self._url, self._filename)
        base, _ = os.path.splitext(display_name)
        display_name = f"{base}.mp4"
        self.file_label.setText(f"Saving as: {display_name}")
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

    def _on_start_clicked(self):
        # If paste row is visible, use the pasted URL
        if self.paste_row.isVisible():
            pasted = self.paste_input.text().strip()
            if pasted:
                self._url = pasted
                self._page_referer = pasted
                self.paste_row.setVisible(False)
                self.url_label.setText(pasted)
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
        folder = os.path.join(HOME, "Downloads", "Videos")
        os.makedirs(folder, exist_ok=True)
        # Luluvdo / Lulustream: handled by a dedicated downloader (see
        # LuluHLSDownloadThread). yt-dlp/ffmpeg both 403 against this CDN.
        _is_lulu_page = bool(re.search(
            r'(?:luluvdo|lulustream)\.com', self._url, re.I
        ))
        display_name = self._resolve_display_name(self._url, self._filename)
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
        # Update the dialog label to show the resolved filename
        self.file_label.setText(f"Saving as: {display_name}")
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
        if self.dl_thread and self.dl_thread.isRunning() and not self._finished_reported:
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
        self.cancel_btn.setEnabled(False)
        self.close_btn.setEnabled(True)
        if msg == "Finished":
            self.progress_bar.setValue(100)
            self.log_box.append("Download complete!")
            self.info_label.setText("Download complete!")
            self.info_label.setStyleSheet("color: #3fb950; font-size: 12px;")
            self.start_btn.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.open_file_btn.setVisible(True)
            self.open_folder_btn.setVisible(True)
            # If force-downloaded via DownloadThread, the thread may have resolved
            # a better filename from Content-Disposition — sync _dl_path and label.
            if self._force_retry and self.dl_thread and hasattr(self.dl_thread, 'filename'):
                resolved = self.dl_thread.filename
                folder   = choose_folder(resolved)
                self._dl_path = os.path.join(folder, resolved)
                self.file_label.setText(f"Saving as: {resolved}")
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
            self.log_box.append("Stream URL expired (403) — retrying with page URL...")
            self.info_label.setText("Retrying with page URL...")
            self.info_label.setStyleSheet("color: #e3b341; font-size: 12px;")
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
        self.info_label.setStyleSheet("color: #f85149; font-size: 12px;")
        # Unusual extension — offer force download button
        if label_msg == "__force_ext__" and not self._force_retry:
            self.info_label.setText("Unusual extension — force download?")
            self.force_dl_btn.setVisible(True)
            self.close_btn.setEnabled(True)
        # Facebook paste hint -- show input row so user can paste link
        elif 'Paste the video link' in label_msg or 'Paste the reel link' in label_msg:
            self.info_label.setText(label_msg)
            if 'reel link' in label_msg:
                self.paste_hint.setText(
                    "Share \u2192 Copy link (or \u22ef \u2192 Copy link) on the reel \u2192 paste below:"
                )
            else:
                self.paste_hint.setText(
                    "\u22ef (3 dots) on video \u2192 Copy link \u2192 paste below:"
                )
            self.paste_row.setVisible(True)
            self.start_btn.setEnabled(True)
            self.close_btn.setEnabled(True)
        else:
            self.info_label.setText(label_msg)
            self.download_finished.emit(self._url, msg)

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
class CoreDownloaderDialog(QDialog):
    """Non-modal dialog for direct file downloads (zip, exe, pdf, etc.)
    Uses DownloadThread (requests/curl) — not yt-dlp."""
    download_started  = pyqtSignal(str, str, str)   # url, display_name, folder
    download_progress = pyqtSignal(str, int, str, str, str)  # url, pct, size, speed, eta
    download_finished = pyqtSignal(str, str)         # url, status

    def __init__(self, parent=None, url="", filename="", referer="", dark=True):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle("LDM Core Downloader")
        self.setMinimumWidth(520)
        self.setMinimumHeight(320)
        self._dark = dark
        self.setStyleSheet(make_dialog_style(dark))
        self._url      = url
        self._filename = filename
        self._referer  = referer
        self._dl_path  = ""
        self.dl_thread = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Core Downloader")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {'#58a6ff' if self._dark else '#0369a1'};")
        layout.addWidget(title)

        url_label = QLineEdit(self._url)
        url_label.setReadOnly(True)
        url_label.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        url_label.setStyleSheet(
            f"color: {'#8b949e' if self._dark else '#64748b'}; font-size: 11px;"
            " border: none; background: transparent; padding: 2px 4px;"
            " selection-background-color: #1f6feb; selection-color: #ffffff;"
        )
        url_label.setCursorPosition(0)
        layout.addWidget(url_label)

        self.file_label = QLabel(f"Saving as: {self._filename}")
        self.file_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {'#e6edf3' if self._dark else '#1e293b'};")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet(f"color: {'#8b949e' if self._dark else '#64748b'}; font-size: 12px;")
        layout.addWidget(self.info_label)

        layout.addStretch()

        btn_row = QHBoxLayout()

        self.start_btn = QPushButton("Start Download")
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: white; }"
            "QPushButton:hover { background-color: #15803d; }"
            "QPushButton:disabled { background-color: #94a3b8; }"
        )
        self.start_btn.clicked.connect(self._start_download)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(
            "QPushButton { background-color: #dc2626; color: white; }"
            "QPushButton:hover { background-color: #b91c1c; }"
            "QPushButton:disabled { background-color: #94a3b8; }"
        )
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)

        self.open_file_btn = QPushButton("Open")
        self.open_file_btn.setStyleSheet(
            "QPushButton { background-color: #0ea5e9; color: white; }"
            "QPushButton:hover { background-color: #0284c7; }"
        )
        self.open_file_btn.setVisible(False)
        self.open_file_btn.clicked.connect(self._open_file)

        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setStyleSheet(
            "QPushButton { background-color: #64748b; color: white; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._open_folder)

        self.close_btn = QPushButton("Close")
        self.close_btn.setStyleSheet(make_close_btn_style(self._dark))
        self.close_btn.clicked.connect(self.close)

        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.open_file_btn)
        btn_row.addWidget(self.open_folder_btn)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def _start_download(self):
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        folder = choose_folder(self._filename)
        base, ext = os.path.splitext(self._filename)
        unique_name, counter = self._filename, 1
        while os.path.exists(os.path.join(folder, unique_name)):
            unique_name = f"{base} ({counter}){ext}"
            counter += 1
        self._dl_path = os.path.join(folder, unique_name)
        self._display_name = unique_name
        self.file_label.setText(f"Saving as: {unique_name}")
        self.download_started.emit(self._url, unique_name, folder)

        self.dl_thread = DownloadThread(self._url, unique_name, is_video=False, referer=self._referer)
        self.dl_thread.progress.connect(self._on_progress)
        self.dl_thread.speed.connect(self._on_speed)
        self.dl_thread.downloaded.connect(self._on_downloaded)
        self.dl_thread.eta.connect(self._on_eta)
        self.dl_thread.finished.connect(self._on_finished)
        self.dl_thread.start()

    def _on_progress(self, pct):
        self.progress_bar.setValue(pct)
        self.download_progress.emit(self._url, pct,
            getattr(self, '_last_size', ''),
            getattr(self, '_last_speed', ''),
            getattr(self, '_last_eta', ''))

    def _on_speed(self, s):
        self._last_speed = s
        self._refresh_info()

    def _on_downloaded(self, s):
        self._last_size = s
        self._refresh_info()

    def _on_eta(self, s):
        self._last_eta = s
        self._refresh_info()

    def _refresh_info(self):
        parts = []
        if getattr(self, '_last_size', ''):  parts.append(self._last_size)
        if getattr(self, '_last_speed', ''): parts.append(self._last_speed)
        if getattr(self, '_last_eta', ''):   parts.append(f"ETA {self._last_eta}")
        self.info_label.setText("  •  ".join(parts))

    def _on_finished(self, msg):
        self.start_btn.setVisible(False)
        self.cancel_btn.setVisible(False)
        if msg == "Finished":
            self.progress_bar.setValue(100)
            self.info_label.setText("Download complete.")
            self.open_file_btn.setVisible(True)
            self.open_folder_btn.setVisible(True)
        else:
            self.info_label.setText(f"Status: {msg}")
        self.download_finished.emit(self._url, msg)

    def _cancel(self):
        if self.dl_thread and self.dl_thread.isRunning():
            self.dl_thread.stop()
        self.cancel_btn.setEnabled(False)

    def _open_file(self):
        if self._dl_path and os.path.exists(self._dl_path):
            subprocess.Popen(['xdg-open', self._dl_path])
        self.close()

    def _open_folder(self):
        folder = os.path.dirname(self._dl_path) if self._dl_path else ''
        if folder and os.path.exists(folder):
            subprocess.Popen(['xdg-open', folder])
        self.close()


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
        # URL → {mode, quality, audio_fmt} for YT resume without re-fetching formats
        self.yt_settings = {e["url"]: e["yt_settings"] for e in self.history
                            if e.get("url") and e.get("yt_settings")}
        self._settings = load_settings()
        self.dark_mode = self._settings.get("dark_mode", False)
        self.notify_enabled = self._settings.get("notifications", True)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        app_icon = QIcon()
        for candidate in [
            os.path.join(script_dir, "icons", "linux-downloader.svg"),
            os.path.join(script_dir, "linux-downloader.svg"),
        ]:
            if os.path.exists(candidate):
                app_icon = QIcon(candidate)
                break
        if app_icon.isNull():
            app_icon = QIcon.fromTheme("linux-downloader")
        if app_icon.isNull():
            for candidate in [
                os.path.join(script_dir, "icons", "linux-downloader-256.png"),
                os.path.join(script_dir, "icons", "linux-downloader-128.png"),
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

        self._apply_status_style(stat_item, status)

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
        self.table.setRowHeight(row, 40)

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
        self._sidebar.setFixedWidth(210)
        self._sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(12, 0, 12, 12)
        sidebar_layout.setSpacing(0)

        from PyQt6.QtWidgets import QFrame

        self._sidebar_title = QWidget()
        title_layout = QHBoxLayout(self._sidebar_title)
        title_layout.setContentsMargins(8, 16, 8, 16)
        title_layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setFixedSize(36, 36)
        icon_label.setScaledContents(True)
        pix = self.app_icon.pixmap(36, 36) if not self.app_icon.isNull() else None
        if pix is None or pix.isNull():
            script_dir = os.path.dirname(os.path.abspath(__file__))
            png_path = os.path.join(script_dir, "icons", "linux-downloader-128.png")
            if os.path.exists(png_path):
                pix = QPixmap(png_path).scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if pix and not pix.isNull():
            icon_label.setPixmap(pix)
        title_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self._title_label = GradientTextLabel(
            "LDM", family=self._title_font_family,
            size=22, letter_spacing=5,
        )
        title_layout.addWidget(self._title_label, 0, Qt.AlignmentFlag.AlignVCenter)
        title_layout.addStretch()
        sidebar_layout.addWidget(self._sidebar_title)

        self._sidebar_sep = QFrame()
        self._sidebar_sep.setObjectName("sidebarSep")
        self._sidebar_sep.setFixedHeight(1)
        sidebar_layout.addSpacing(4)
        sidebar_layout.addWidget(self._sidebar_sep)
        sidebar_layout.addSpacing(10)

        self._cat_section_label = QLabel("CATEGORIES")
        self._cat_section_label.setObjectName("catSectionLabel")
        sidebar_layout.addWidget(self._cat_section_label)

        self._cat_scroll = QWidget()
        self._cat_scroll.setObjectName("catScroll")
        cat_layout = QVBoxLayout(self._cat_scroll)
        cat_layout.setContentsMargins(0, 4, 0, 4)
        cat_layout.setSpacing(2)

        self._cat_buttons = []
        self._cat_badges = []
        self._cat_accents = []
        self._current_cat_row = 0
        for i, (label, emoji, color) in enumerate(CATEGORIES):
            btn = QWidget()
            btn.setObjectName(f"catBtn_{i}")
            btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(40)
            btn_layout = QHBoxLayout(btn)
            btn_layout.setContentsMargins(0, 0, 14, 0)
            btn_layout.setSpacing(0)

            accent = QWidget()
            accent.setObjectName(f"catAccent_{i}")
            accent.setFixedWidth(3)
            accent.setFixedHeight(22)
            btn_layout.addWidget(accent)
            btn_layout.addSpacing(15)

            text_label = QLabel(f"{emoji}  {label}")
            text_label.setObjectName(f"catText_{i}")
            btn_layout.addWidget(text_label)
            btn_layout.addStretch()

            badge = QLabel("")
            badge.setObjectName(f"catBadge_{i}")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedHeight(20)
            badge.setMinimumWidth(22)
            badge.setVisible(False)
            btn_layout.addWidget(badge)

            btn.mousePressEvent = lambda e, idx=i: self._on_cat_clicked(idx)
            cat_layout.addWidget(btn)
            self._cat_buttons.append(btn)
            self._cat_badges.append(badge)
            self._cat_accents.append(accent)

        cat_layout.addStretch()
        sidebar_layout.addWidget(self._cat_scroll, 1)
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
        self.table.setColumnWidth(0, 270)
        self.table.setColumnWidth(1, 190)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 85)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 90)
        self.table.setColumnWidth(6, 145)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # ── Restore saved column widths ──────────────────────────────
        saved_widths = self._settings.get("column_widths", {})
        for col_str, width in saved_widths.items():
            self.table.setColumnWidth(int(col_str), width)
        self.table.horizontalHeader().setMinimumSectionSize(50)
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(18, 18))
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().sectionClicked.connect(self._sort_by_column)
        self.table.horizontalHeader().sectionResized.connect(self._on_column_resized)
        self.progress_delegate = ProgressDelegate(self.table)
        self.table.setItemDelegateForColumn(1, self.progress_delegate)
        self._filename_delegate = FilenameFontDelegate(parent=self.table)
        self.table.setItemDelegateForColumn(0, self._filename_delegate)  # File Name (Bangla fallback)
        self._numeric_delegate = NumericFontDelegate(
            family=self._title_font_family, weight=QFont.Weight.Medium, parent=self.table)
        self.table.setItemDelegateForColumn(2, self._numeric_delegate)  # Downloaded
        self.table.setItemDelegateForColumn(3, self._numeric_delegate)  # Speed
        self.table.setItemDelegateForColumn(4, self._numeric_delegate)  # ETA
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

        # Status bar
        self._status_bar = QLabel("Ready")
        self._status_bar.setFixedHeight(24)
        self._status_bar.setContentsMargins(4, 0, 4, 0)
        content_layout.addWidget(self._status_bar)

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

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {t['surface']};
                border: 1px solid {t['border']};
                border-radius: 12px;
                gridline-color: transparent;
                outline: none;
                selection-background-color: {t['selected']};
                selection-color: {t['selected_text']};
                font-size: 13px;
                color: {t['text']};
            }}
            QTableWidget::item {{
                padding: 10px 14px;
                border: none;
                border-bottom: 1px solid {t['grid']};
            }}
            QTableWidget::item:alternate {{
                background-color: {t['alt_row']};
            }}
            QTableWidget::item:selected {{
                background-color: {t['selected']};
                color: {t['selected_text']};
            }}
            QHeaderView::section {{
                background-color: {t['header']};
                color: {t['muted']};
                font-size: 11px;
                font-weight: 700;
                padding: 10px 14px;
                border: none;
                border-bottom: 1px solid {t['border']};
            }}
            QHeaderView::section:first {{
                border-top-left-radius: 12px;
            }}
            QHeaderView::section:last {{
                border-top-right-radius: 12px;
            }}
            QHeaderView::section:hover {{
                background-color: {t['menu_hover']};
                color: {t['menu_hover_text']};
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
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)

        # Qt CSS doesn't support letter-spacing reliably on headers — apply via QFont
        header_font = QFont(self.font().family())
        header_font.setPixelSize(11)
        header_font.setBold(True)
        header_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.5)
        self.table.horizontalHeader().setFont(header_font)

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

        # Subtle separator between wordmark and categories
        sep_color = t.get("border", "#cbd5e1")
        self._sidebar_sep.setStyleSheet(f"""
            QFrame#sidebarSep {{
                background-color: {sep_color};
                border: none;
                margin: 0 10px;
            }}
        """)

        self._cat_section_label.setStyleSheet(f"""
            QLabel#catSectionLabel {{
                color: {t['faint']};
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 1.5px;
                padding: 4px 20px 6px 20px;
                background: transparent;
            }}
        """)
        self._cat_scroll.setStyleSheet(f"""
            QWidget#catScroll {{ background: transparent; }}
        """)
        self._style_cat_buttons()
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
        for i, (label, emoji, color) in enumerate(CATEGORIES):
            btn = self._cat_buttons[i]
            badge = self._cat_badges[i]
            accent = self._cat_accents[i]
            is_sel = (i == self._current_cat_row)
            if is_sel:
                r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                btn.setStyleSheet(f"""
                    QWidget#catBtn_{i} {{
                        background: rgba({r},{g},{b}, 0.15);
                        border-radius: 12px;
                    }}
                    QLabel#catText_{i} {{
                        color: {color};
                        font-size: 14px;
                        font-weight: 700;
                        background: transparent;
                    }}
                """)
                accent.setStyleSheet(f"""
                    QWidget#catAccent_{i} {{
                        background-color: {color};
                        border-radius: 1px;
                    }}
                """)
                badge.setStyleSheet(f"""
                    QLabel#catBadge_{i} {{
                        background: rgba({r},{g},{b}, 0.18);
                        color: {color};
                        font-size: 11px;
                        font-weight: 600;
                        border-radius: 10px;
                        padding: 0px 6px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QWidget#catBtn_{i} {{
                        background: transparent;
                        border-radius: 12px;
                    }}
                    QLabel#catText_{i} {{
                        color: {t['muted']};
                        font-size: 14px;
                        font-weight: 500;
                        background: transparent;
                    }}
                """)
                accent.setStyleSheet(f"""
                    QWidget#catAccent_{i} {{
                        background-color: transparent;
                    }}
                """)
                badge.setStyleSheet(f"""
                    QLabel#catBadge_{i} {{
                        background: rgba(255,255,255,0.06);
                        color: {t['faint']};
                        font-size: 11px;
                        font-weight: 600;
                        border-radius: 10px;
                        padding: 0px 6px;
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
            new_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            new_item.setFlags(new_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col == 5:
                new_item.setToolTip(text)
            self.table.setItem(row, col, new_item)

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
        pass
    
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


if __name__ == "__main__":
    if not os.environ.get("QT_QPA_PLATFORMTHEME"):
        os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"
    _ensure_ytdlp_config()
    app = QApplication(sys.argv)
    window = DownloadManager()
    window.show()
    sys.exit(app.exec())
