// background.js - Linux Download Manager (Chrome MV3)
// Key differences from Firefox version:
//   - All browser.* replaced with chrome.*
//   - webRequest is non-blocking (MV3 restriction); downloads intercepted via
//     chrome.downloads.onCreated + chrome.downloads.cancel() instead
//   - Background is a service worker; in-memory stores are backed by
//     chrome.storage.session so they survive SW termination

// ---------------------------------------------------------------------------
// In-memory caches (fast path) — written through to chrome.storage.session
// ---------------------------------------------------------------------------
var tabM3u8Store      = {};  // tabId -> m3u8 URL string
var tabSocialStore    = {};  // tabId -> array of {cdnUrl, videoId, isTwimg, ts}
var interceptEnabled  = true;
var SOCIAL_STORE_MAX  = 5;

// URLs detected via webRequest as needing interception.
// Key: url, Value: { filename, referer, ts }
// webRequest fires first and wakes the SW; downloads.onCreated then finds the
// URL here and cancels it while the SW is still alive.
var pendingIntercepts = {};

// Keep service worker alive so downloads.onCreated fires reliably.
// Chrome requires periodInMinutes >= 1 for alarms, but even registering it
// forces Chrome to keep the SW registered for download events.
chrome.alarms.create('ldm-keepalive', { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(function (alarm) {
  if (alarm.name === 'ldm-keepalive') {
    // Intentionally empty — just wakes the SW
  }
});

// Restore state on SW startup (session storage survives SW idle termination)
chrome.storage.session.get(['tabM3u8Store', 'tabSocialStore', 'pendingIntercepts'],
  function (result) {
    if (result.tabM3u8Store)      tabM3u8Store      = result.tabM3u8Store;
    if (result.tabSocialStore)    tabSocialStore    = result.tabSocialStore;
    if (result.pendingIntercepts) pendingIntercepts = result.pendingIntercepts;
  }
);

// interceptEnabled is persisted in local storage (by popup), not session storage.
// Read it on every SW startup so toggling OFF survives SW idle termination.
chrome.storage.local.get('interceptEnabled', function (result) {
  if (result.interceptEnabled !== undefined) interceptEnabled = result.interceptEnabled;
});

// Listen for toggle changes from popup
chrome.storage.onChanged.addListener(function (changes, area) {
  if (area === 'local' && changes.interceptEnabled !== undefined) {
    interceptEnabled = changes.interceptEnabled.newValue;
  }
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function saveSession() {
  chrome.storage.session.set({ tabM3u8Store, tabSocialStore, pendingIntercepts });
}

function socialStoreAdd(tabId, entry) {
  if (!tabSocialStore[tabId]) tabSocialStore[tabId] = [];
  tabSocialStore[tabId] = tabSocialStore[tabId]
    .filter(function (e) { return e.cdnUrl !== entry.cdnUrl; });
  tabSocialStore[tabId].unshift(entry);
  if (tabSocialStore[tabId].length > SOCIAL_STORE_MAX)
    tabSocialStore[tabId] = tabSocialStore[tabId].slice(0, SOCIAL_STORE_MAX);
  saveSession();
}

var SOCIAL_CDN_DOMAINS = [
  'fbcdn.net',
  'cdninstagram.com',
  'video.twimg.com',
];

function isSocialCDN(url) {
  try {
    var host = new URL(url).hostname;
    if (SOCIAL_CDN_DOMAINS.some(function (d) { return host.endsWith(d); })) return true;
    if (/^v\d+[-\w]*\.tiktok\.com$/.test(host)) return true;
    return false;
  } catch (e) { return false; }
}

function decodeFbVideoId(url) {
  try {
    var efg = new URL(url).searchParams.get('efg');
    if (!efg) return null;
    var decoded = JSON.parse(atob(efg));
    return decoded.video_id ? String(decoded.video_id) : null;
  } catch (e) { return null; }
}

var cfProtectedDomains = [
  'luluvdo.com', 'lulustream.com',
  'doodstream.com', 'dood.watch', 'dood.to',
];

function isCFProtected(url) {
  try {
    var host = new URL(url).hostname;
    return cfProtectedDomains.some(function (d) { return host.includes(d); });
  } catch (e) { return false; }
}

var skipExts = [
  '.jpg', '.jpeg', '.png', '.gif', '.webp',
  '.bmp', '.svg', '.avif', '.tiff', '.ico',
  '.py', '.sh', '.js', '.css', '.html', '.htm',
  '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg',
  '.md', '.rst', '.tex', '.csv', '.log', '.env',
  '.c', '.cpp', '.h', '.java', '.rb', '.go', '.rs', '.php',
  '.wasm', '.map',
  '.enc', '.key', '.aes', '.m4s', '.frag', '.chunk',
];

var videoAudioMimes = [
  'video/mp4', 'video/x-matroska', 'video/webm', 'video/avi',
  'video/quicktime', 'video/mp2t', 'video/vnd.dlna.mpeg-tts',
  'audio/mpeg', 'audio/flac', 'audio/wav', 'audio/aac',
  'audio/ogg', 'audio/x-m4a',
];
var videoAudioExts = [
  '.mp4', '.mkv', '.webm', '.avi', '.mov', '.ts', '.flv', '.m4v',
  '.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a',
];

function isVideoAudio(url, contentType) {
  if (contentType) {
    var ct = contentType.toLowerCase();
    for (var i = 0; i < videoAudioMimes.length; i++) {
      if (ct.includes(videoAudioMimes[i])) return true;
    }
  }
  var path = url.split('?')[0].toLowerCase();
  for (var j = 0; j < videoAudioExts.length; j++) {
    if (path.endsWith(videoAudioExts[j])) return true;
  }
  return false;
}

// Extensions that map to one of LDM's download categories
// (Videos / Music / Documents / Compressed / Programs — mirrors file_types in
// download_manager.py). Files outside this set are left to the browser's own
// downloader: we only auto-capture types LDM actually sorts into a category.
var allowedCategoryExts = [
  // Videos
  '.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts',
  // Music
  '.mp3', '.flac', '.aac', '.wav', '.ogg', '.m4a',
  // Documents
  '.pdf', '.doc', '.docx', '.txt', '.ppt', '.pptx',
  // Compressed
  '.zip', '.rar', '.7z', '.tar', '.gz',
  // Programs
  '.exe', '.bin', '.appimage', '.deb', '.rpm', '.iso',
];
function inAllowedCategory(filename) {
  if (!filename) return false;
  var name = filename.split('?')[0].toLowerCase().replace(/\.(v?\d{6,})$/i, '');
  for (var i = 0; i < allowedCategoryExts.length; i++) {
    if (name.endsWith(allowedCategoryExts[i])) return true;
  }
  return false;
}

// Hosts whose downloads must never be routed through LDM (Claude artifacts,
// design handoffs, etc. — the user explicitly opted these out).
var BLOCKED_HOSTS = ['claude.ai', 'anthropic.com', 'figma.com'];

function isBlockedHost(url) {
  if (!url) return false;
  // blob:/filesystem: wrap an inner origin; URL.hostname returns "" for them,
  // so peel the wrapper before parsing.
  var u = url;
  var low = u.toLowerCase();
  if (low.indexOf('blob:') === 0 || low.indexOf('filesystem:') === 0) {
    u = u.slice(u.indexOf(':') + 1);
  }
  try {
    var host = new URL(u).hostname.toLowerCase();
    for (var i = 0; i < BLOCKED_HOSTS.length; i++) {
      var h = BLOCKED_HOSTS[i];
      if (host === h || host.endsWith('.' + h)) return true;
    }
  } catch (e) {}
  return false;
}

// Collect cookies for the target (and page) URL so LDM can authenticate
// downloads without reading the browser profile from disk — required for the
// Flatpak build, which is sandboxed away from the browser's cookie store.
function collectBridgeCookies(url, referer) {
  var urls = [];
  if (url) urls.push(url);
  if (referer && referer !== url) urls.push(referer);
  if (!urls.length || !chrome.cookies || !chrome.cookies.getAll) {
    return Promise.resolve([]);
  }
  var jobs = urls.map(function (u) {
    return Promise.resolve(chrome.cookies.getAll({ url: u })).catch(function () { return []; });
  });
  return Promise.all(jobs).then(function (lists) {
    var seen = {}, out = [];
    lists.forEach(function (list) {
      (list || []).forEach(function (c) {
        var k = c.domain + '|' + c.path + '|' + c.name;
        if (seen[k]) return;
        seen[k] = 1;
        out.push({
          domain: c.domain, name: c.name, value: c.value, path: c.path,
          secure: c.secure, httpOnly: c.httpOnly, hostOnly: c.hostOnly,
          expirationDate: c.expirationDate, session: c.session
        });
      });
    });
    return out;
  }).catch(function () { return []; });
}

function sendToPython(url, filename, type, referer) {
  if (isBlockedHost(url)) return;
  referer = referer || '';
  collectBridgeCookies(url, referer).then(function (cookies) {
    // text/plain keeps it a "simple" request (no CORS preflight); the app
    // parses the body as JSON regardless of the declared content type.
    fetch('http://127.0.0.1:9999/', {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify({
        url: url, filename: filename, type: type,
        referer: referer, cookies: cookies
      })
    }).catch(function () {
      console.error('Linux Download Manager is not running.');
    });
  });
}

// ---------------------------------------------------------------------------
// Context menus
// ---------------------------------------------------------------------------
chrome.runtime.onInstalled.addListener(function () {
  chrome.contextMenus.create({
    id: 'send-to-linux-dm',
    title: 'Download with Linux Manager',
    contexts: ['link'],
  });
  chrome.contextMenus.create({
    id: 'capture-youtube',
    title: 'Capture YouTube with LDM',
    contexts: ['page', 'link'],
    documentUrlPatterns: [
      '*://www.youtube.com/watch*',
      '*://www.youtube.com/shorts/*',
      '*://youtu.be/*',
      '*://youtube.com/watch*',
      '*://youtube.com/shorts/*',
    ],
  });
});

chrome.contextMenus.onClicked.addListener(function (info) {
  if (info.menuItemId === 'send-to-linux-dm') {
    var url      = info.linkUrl;
    var filename = url.split('?')[0].split('/').pop() || 'download';
    var referer  = info.pageUrl || '';
    sendToPython(url, filename, 'file', referer);
  }
  if (info.menuItemId === 'capture-youtube') {
    var url = info.linkUrl || info.pageUrl;
    sendToPython(url, 'youtube', 'youtube', '');
  }
});

// ---------------------------------------------------------------------------
// Tab navigation — clear per-tab stores on new page load
// ---------------------------------------------------------------------------
chrome.tabs.onUpdated.addListener(function (tabId, changeInfo) {
  if (changeInfo.status === 'loading') {
    delete tabM3u8Store[tabId];
    delete tabSocialStore[tabId];
    saveSession();
  }
});

// ---------------------------------------------------------------------------
// webRequest — NON-blocking observer (MV3 does not support webRequestBlocking)
// We use this to passively capture m3u8 manifests and social CDN URLs per tab.
// File download interception is handled by chrome.downloads.onCreated below.
// ---------------------------------------------------------------------------
var downloadTypes = [
  'application/octet-stream',
  'application/zip', 'application/x-zip',
  'application/x-rar', 'application/x-7z-compressed',
  'application/x-tar', 'application/gzip', 'application/x-bzip2',
  'application/vnd.android.package-archive',
  'application/x-msdownload', 'application/x-debian-package',
  'application/x-rpm',
  'application/dash+xml', 'application/x-mpegurl',
  'application/vnd.apple.mpegurl', 'application/vnd.ms-sstr+xml',
];

var segmentPatterns = [
  /\/seg[-_]?\d+/i, /\/chunk[-_]?\d+/i, /\/fragment[-_]?\d+/i,
  /\/media[-_]?\d+/i, /[&?]segment=\d+/i,
  /\/\d+\.enc(\?|$)/i, /\/\d+\.ts(\?|$)/i, /\/\d+\.m4s(\?|$)/i,
];

chrome.webRequest.onHeadersReceived.addListener(
  function (details) {
    var url      = details.url;
    var lowerUrl = url.toLowerCase();

    // Skip known-safe domains
    if (
      lowerUrl.includes('claude.ai') || lowerUrl.includes('anthropic.com') ||
      lowerUrl.includes('chatgpt.com') || lowerUrl.includes('chat.openai.com') ||
      lowerUrl.includes('googlevideo.com') || lowerUrl.includes('youtube.com') ||
      lowerUrl.includes('youtu.be') || lowerUrl.includes('googleapis.com') ||
      lowerUrl.includes('gstatic.com') || lowerUrl.includes('googleusercontent.com') ||
      lowerUrl.includes('edge-chat.facebook.com') || lowerUrl.includes('mqtt')
    ) return;

    if (lowerUrl.startsWith('blob:') || lowerUrl.startsWith('data:')) return;

    var headers         = details.responseHeaders || [];
    var contentType     = null;
    var contentDisp     = null;

    for (var i = 0; i < headers.length; i++) {
      var n = headers[i].name.toLowerCase();
      if (n === 'content-type')        contentType = headers[i].value;
      if (n === 'content-disposition') contentDisp = headers[i].value;
    }

    // ── Attachment download detection — mark URL as pending intercept ────
    // webRequest fires BEFORE Chrome starts saving the file, waking the SW.
    // downloads.onCreated will find the URL here and cancel it reliably.
    var isAttachment = contentDisp && contentDisp.toLowerCase().includes('attachment');
    var ctLower      = (contentType || '').toLowerCase();
    var isBinaryMime = downloadTypes.some(function (t) { return ctLower.includes(t); });
    var isNotMediaOrText = ctLower &&
      !ctLower.startsWith('video/') && !ctLower.startsWith('audio/') &&
      !ctLower.startsWith('image/') && !ctLower.startsWith('text/') &&
      !ctLower.includes('application/json') && !ctLower.includes('application/javascript');
    var urlPath  = url.split('?')[0].toLowerCase();
    var isSkippedExt = skipExts.some(function (e) { return urlPath.endsWith(e); });
    var isSegment    = segmentPatterns.some(function (p) { return p.test(url); });

    if (!isSkippedExt && !isSegment && interceptEnabled &&
        (isAttachment || isBinaryMime) && isNotMediaOrText) {
      var fname = '';
      if (contentDisp) {
        var m = contentDisp.match(/filename[^=]*=\s*["']?([^"'\s;]+)/i);
        if (m) fname = decodeURIComponent(m[1].trim());
      }
      if (!fname) fname = url.split('?')[0].split('/').pop() || 'download';
      // Also check content-disposition filename against skipExts
      // (URL path may be a generic CDN route that doesn't reveal the real extension)
      var fnameLower = fname.toLowerCase();
      var isSkippedName = skipExts.some(function (e) { return fnameLower.endsWith(e); });
      if (isSkippedName) return;
      // Category allow-list: only auto-capture files whose extension maps to one
      // of LDM's download categories. Anything else is left to the browser.
      if (!inAllowedCategory(fname)) return;
      var dlReferer = details.documentUrl || details.initiator || '';
      pendingIntercepts[url] = { filename: fname, referer: dlReferer, ts: Date.now() };
      saveSession();
    }

    // ── Social CDN passive store ──────────────────────────────────────────
    if (isSocialCDN(url)) {
      var isFbcdn = url.includes('fbcdn.net') || url.includes('cdninstagram.com');
      if (isFbcdn) return;  // FB DASH byte-range chunks — useless for capture

      var isTwimg  = url.includes('video.twimg.com');
      var isTikTok = false;
      try { isTikTok = /^v\d+[-\w]*\.tiktok\.com$/.test(new URL(url).hostname); } catch (e) {}

      var contentLen = 0;
      for (var ci = 0; ci < headers.length; ci++) {
        if (headers[ci].name.toLowerCase() === 'content-length')
          contentLen = parseInt(headers[ci].value) || 0;
      }

      var isVideoUrl = isTwimg || isTikTok ||
        url.split('?')[0].toLowerCase().endsWith('.mp4') ||
        (contentType && contentType.toLowerCase().includes('video/'));
      var isTikTokVideo = isTikTok && url.includes('mime_type=video_mp4');
      var sizeOk = isTikTok ? isTikTokVideo : contentLen > 100000;

      if (isVideoUrl && sizeOk) {
        var entry = {
          cdnUrl:  url,
          videoId: decodeFbVideoId(url),
          isTwimg: isTwimg,
          ts:      Date.now(),
        };
        socialStoreAdd(details.tabId, entry);
        chrome.tabs.sendMessage(details.tabId, {
          action: 'storeCdnEntry',
          entry:  entry,
        }, function () { chrome.runtime.lastError; }); // suppress error if no content script
      }
      return;
    }

    // ── HLS/DASH manifest passive store ──────────────────────────────────
    var urlPathLower = url.split('?')[0].toLowerCase();
    var isManifest   = urlPathLower.endsWith('.m3u8') || urlPathLower.endsWith('.mpd');
    var isHLSType    = contentType && (
      contentType.toLowerCase().includes('mpegurl') ||
      contentType.toLowerCase().includes('dash+xml')
    );

    if ((isManifest || isHLSType) && !isCFProtected(url)) {
      // Skip segment URLs
      if (!segmentPatterns.some(function (p) { return p.test(url); })) {
        tabM3u8Store[details.tabId] = url;
        saveSession();
      }
    }
    // Non-blocking — no return value needed; download interception is
    // handled by chrome.downloads.onCreated below.
  },
  { urls: ['<all_urls>'] },
  ['responseHeaders']  // No "blocking" — not supported in Chrome MV3
);

// ---------------------------------------------------------------------------
// Download interception — replaces webRequestBlocking from Firefox version.
// chrome.downloads.onCreated fires before the file is saved; we cancel it
// and forward the URL to LDM.
// ---------------------------------------------------------------------------
chrome.downloads.onCreated.addListener(function (downloadItem) {
  if (!interceptEnabled) return;

  var url      = downloadItem.url || '';
  var lowerUrl = url.toLowerCase();
  var mime     = (downloadItem.mime || '').toLowerCase();
  var filename = (downloadItem.filename || '').split(/[/\\]/).pop() || '';

  // ── Priority path: URL was pre-marked by webRequest (SW already awake) ──
  // This is the reliable path — webRequest fired first, stored the URL,
  // so cancel() runs while the SW is still alive.
  // Chrome may redirect before downloads.onCreated fires, so check finalUrl too.
  // We always send the key URL (the one webRequest observed), not downloadItem.url,
  // so that redirect chains (e.g. force-download → view page) send the right URL.
  var finalUrl    = downloadItem.finalUrl || '';
  var pendingKey  = pendingIntercepts[url] ? url : (pendingIntercepts[finalUrl] ? finalUrl : null);
  var pending     = pendingKey ? pendingIntercepts[pendingKey] : null;
  if (pending) {
    delete pendingIntercepts[url];
    if (finalUrl) delete pendingIntercepts[finalUrl];
    // Clean stale entries older than 30s
    var now = Date.now();
    Object.keys(pendingIntercepts).forEach(function (k) {
      if (now - pendingIntercepts[k].ts > 30000) delete pendingIntercepts[k];
    });
    saveSession();
    chrome.downloads.cancel(downloadItem.id, function () {
      chrome.downloads.erase({ id: downloadItem.id }, function () {});
      sendToPython(pendingKey, pending.filename, 'file', pending.referer);
    });
    return;
  }

  // ── Fallback path: SW happened to be awake (blob URIs, etc.) ────────────
  if (!interceptEnabled) return;

  // ── Blob / data URIs ─────────────────────────────────────────────────────
  if (lowerUrl.startsWith('blob:') || lowerUrl.startsWith('data:')) {
    if (mime.startsWith('image/') || mime.startsWith('text/')) return;
    var hasExt = filename.includes('.');
    if (!hasExt && (mime === 'application/octet-stream' || mime === '')) return;
    for (var s = 0; s < skipExts.length; s++) {
      if (filename.toLowerCase().endsWith(skipExts[s])) return;
    }
    // Only route category files through LDM; let the browser keep the rest.
    if (!inAllowedCategory(filename)) return;
    chrome.downloads.cancel(downloadItem.id, function () {
      chrome.downloads.erase({ id: downloadItem.id }, function () {});
      sendToPython(url, filename || 'download', 'file', '');
    });
    return;
  }

  // ── Skip video/audio — handled by Capture button, not auto-intercept ─────
  if (isVideoAudio(url, mime)) return;

  // ── Skip images and text ─────────────────────────────────────────────────
  if (mime.startsWith('image/') || mime.startsWith('text/')) return;
  if (mime.includes('application/json') || mime.includes('application/javascript')) return;

  // ── Skip known non-download extensions ──────────────────────────────────
  var urlPath = url.split('?')[0].toLowerCase();
  for (var k = 0; k < skipExts.length; k++) {
    if (urlPath.endsWith(skipExts[k])) return;
  }
  if (filename) {
    for (var m = 0; m < skipExts.length; m++) {
      if (filename.toLowerCase().endsWith(skipExts[m])) return;
    }
  }

  // ── Skip HLS/DASH segment URLs ──────────────────────────────────────────
  if (segmentPatterns.some(function (p) { return p.test(url); })) return;

  // ── Skip YouTube / Google domains ────────────────────────────────────────
  if (
    lowerUrl.includes('googlevideo.com') ||
    lowerUrl.includes('youtube.com') ||
    lowerUrl.includes('youtu.be') ||
    lowerUrl.includes('googleapis.com')
  ) return;

  // ── Check MIME is a known download type ─────────────────────────────────
  if (mime) {
    var isKnownDownload = downloadTypes.some(function (t) { return mime.includes(t); });
    if (!isKnownDownload) return;
  }

  // ── Intercept: cancel and send to LDM ───────────────────────────────────
  var referer = downloadItem.referrer || '';
  if (!filename) filename = url.split('?')[0].split('/').pop() || 'download';

  // Category allow-list: only auto-capture files LDM sorts into a category.
  if (!inAllowedCategory(filename)) return;

  chrome.downloads.cancel(downloadItem.id, function () {
    chrome.downloads.erase({ id: downloadItem.id }, function () {});
    sendToPython(url, filename, 'file', referer);
  });
});

// ---------------------------------------------------------------------------
// Message relay from content scripts and popup
// ---------------------------------------------------------------------------
chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  if (message.action === 'bridge') {
    sendToPython(message.url, message.filename || 'download', message.type || 'file', '');
    sendResponse({ ok: true });
  }

  if (message.action === 'getM3u8') {
    var tabId = sender.tab ? sender.tab.id : null;
    sendResponse({ url: tabId ? (tabM3u8Store[tabId] || null) : null });
  }

  if (message.action === 'getM3u8ForTab') {
    sendResponse({ url: tabM3u8Store[message.tabId] || null });
  }

  if (message.action === 'getSocialVideo') {
    var tabId = sender.tab ? sender.tab.id : null;
    var entry = tabId && tabSocialStore[tabId] && tabSocialStore[tabId].length
      ? tabSocialStore[tabId][0] : null;
    sendResponse({ entry: entry });
  }

  if (message.action === 'getSocialVideoForTab') {
    var entries = tabSocialStore[message.tabId] || [];
    var entry   = null;
    if (message.videoId) {
      entry = entries.find(function (e) { return e.videoId === message.videoId; }) || null;
    }
    if (!entry) entry = entries[0] || null;
    sendResponse({ entry: entry });
  }

  return true; // keep channel open for async sendResponse
});
