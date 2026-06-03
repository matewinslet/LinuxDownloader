// background.js - Version 2.5.5

const handledUrls = new Set();
let interceptEnabled = true;

// Per-tab m3u8 store — populated passively when page loads, used on Capture click.
// Manifests are NEVER cancelled so the browser player always works normally.
var tabM3u8Store = {};

// Per-tab social CDN store — stores last 5 CDN video URLs per tab.
// Used for Facebook/Instagram (fbcdn.net mp4) and Twitter (twimg.com m3u8).
// Key: tabId → array of { cdnUrl, videoId, ts } (newest first)
var tabSocialStore = {};
var SOCIAL_STORE_MAX = 5;

function socialStoreAdd(tabId, entry) {
  if (!tabSocialStore[tabId]) tabSocialStore[tabId] = [];
  tabSocialStore[tabId] = tabSocialStore[tabId]
    .filter(function(e) { return e.cdnUrl !== entry.cdnUrl; });
  tabSocialStore[tabId].unshift(entry);
  if (tabSocialStore[tabId].length > SOCIAL_STORE_MAX)
    tabSocialStore[tabId] = tabSocialStore[tabId].slice(0, SOCIAL_STORE_MAX);
}

// Social CDN domains — we intercept these passively for direct CDN download
var SOCIAL_CDN_DOMAINS = [
  "fbcdn.net",          // Facebook + Instagram video CDN
  "cdninstagram.com",   // Instagram CDN alias
  "video.twimg.com",    // Twitter video CDN
];

function isSocialCDN(url) {
  try {
    var host = new URL(url).hostname;
    if (SOCIAL_CDN_DOMAINS.some(function(d) { return host.endsWith(d); })) return true;
    // TikTok video CDN: v16-webapp-prime.tiktok.com, v19-webapp.tiktok.com, etc.
    if (/^v\d+[-\w]*\.tiktok\.com$/.test(host)) return true;
    return false;
  } catch(e) { return false; }
}

// Decode Facebook/Instagram efg param to extract video_id
function decodeFbVideoId(url) {
  try {
    var efg = new URL(url).searchParams.get('efg');
    if (!efg) return null;
    var decoded = JSON.parse(atob(efg));
    return decoded.video_id ? String(decoded.video_id) : null;
  } catch(e) { return null; }
}

// CF-protected domains (no CDN store, use yt-dlp page URL)
var cfProtectedDomains = [
  "luluvdo.com", "lulustream.com",
  "doodstream.com", "dood.watch", "dood.to",
];

function isCFProtected(url) {
  try {
    var host = new URL(url).hostname;
    return cfProtectedDomains.some(function(d) { return host.includes(d); });
  } catch(e) { return false; }
}

// Strip /e/, /embed/ iframe prefixes from URLs
function normalizeStreamUrl(url) {
  try {
    var u = new URL(url);
    u.pathname = u.pathname.replace(/^\/e\//, '/').replace(/^\/embed\//, '/');
    return u.toString();
  } catch(e) { return url; }
}

browser.storage.local.get("interceptEnabled").then(function(result) {
  interceptEnabled = result.interceptEnabled !== false;
});

browser.storage.onChanged.addListener(function(changes) {
  if (changes.interceptEnabled !== undefined) {
    interceptEnabled = changes.interceptEnabled.newValue;
  }
});

// Clear stored URLs when tab navigates to a new page
browser.tabs.onUpdated.addListener(function(tabId, changeInfo) {
  if (changeInfo.status === 'loading') {
    delete tabM3u8Store[tabId];
    delete tabSocialStore[tabId];
  }
});

// Context menu for regular download links
browser.contextMenus.create({
  id: "send-to-linux-dm",
  title: "Download with Linux Manager",
  contexts: ["link"]
});

// Context menu for YouTube pages and links — only on video/shorts pages
browser.contextMenus.create({
  id: "capture-youtube",
  title: "Capture YouTube with LDM",
  contexts: ["page", "link"],
  documentUrlPatterns: [
    "*://www.youtube.com/watch*",
    "*://www.youtube.com/shorts/*",
    "*://youtu.be/*",
    "*://youtube.com/watch*",
    "*://youtube.com/shorts/*"
  ]
});

// Single combined listener for all context menu clicks
browser.contextMenus.onClicked.addListener(function(info) {
  if (info.menuItemId === "send-to-linux-dm") {
    var url = info.linkUrl;
    var filename = url.split("?")[0].split("/").pop() || "download";
    var referer = info.pageUrl || "";
    sendToPython(url, filename, "file", referer);
  }
  if (info.menuItemId === "capture-youtube") {
    var url = info.linkUrl || info.pageUrl;
    sendToPython(url, "youtube", "youtube", "");
  }
});

var skipExts = [
  // images
  ".jpg", ".jpeg", ".png", ".gif", ".webp",
  ".bmp", ".svg", ".avif", ".tiff", ".ico",
  // code / text
  ".py", ".sh", ".js", ".css", ".html", ".htm",
  ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg",
  ".md", ".rst", ".tex", ".csv", ".log", ".env",
  ".c", ".cpp", ".h", ".java", ".rb", ".go", ".rs", ".php",
  ".wasm", ".map",
  // fonts
  ".woff", ".woff2", ".ttf", ".otf", ".eot",
  // subtitles / captions
  ".vtt", ".srt", ".ass", ".ssa", ".sub",
  // 3D / game / animation assets
  ".riv", ".glb", ".gltf", ".fbx", ".obj", ".usdz", ".spine", ".atlas",
  // data blobs
  ".bin", ".dat", ".db", ".sqlite",
  // HLS / DASH stream segments
  ".enc", ".key", ".aes", ".m4s", ".frag", ".chunk"
];

// Strip CDN cache-buster version suffixes before extension checks.
// e.g. "sw_en_1.vtt.v1737700893" → "sw_en_1.vtt"
function stripVersionSuffix(path) {
  return path.replace(/\.(v?\d{6,})$/i, "");
}

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
    var ct = contentType.value.toLowerCase();
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
  var name = stripVersionSuffix(filename.split('?')[0].toLowerCase());
  for (var i = 0; i < allowedCategoryExts.length; i++) {
    if (name.endsWith(allowedCategoryExts[i])) return true;
  }
  return false;
}

// Domains never intercepted — captcha, auth, infrastructure, AI tools
var skipDomains = [
  "claude.ai", "anthropic.com", "chatgpt.com", "chat.openai.com",
  "hcaptcha.com", "recaptcha.net", "challenges.cloudflare.com",
  "turnstile.cloudflare.com", "funcaptcha.com", "arkoselabs.com",
  "captcha.com", "mtcaptcha.com", "geetest.com",
  "accounts.google.com", "oauth2.googleapis.com",
  "auth0.com", "okta.com", "login.microsoftonline.com",
  "google.com", "googleapis.com", "gstatic.com",
  "googleusercontent.com", "googlevideo.com",
  "lh3.google", "lh4.google", "lh5.google", "lh6.google",
  "youtube.com", "youtu.be",
  "stackoverflow.com", "codepen.io", "jsfiddle.net",
  "pastebin.com", "gist.github.com",
  "edge-chat.facebook.com", "mqtt",
  "mega.co.nz", "mega.nz",
];

// Rewrite API/embed URLs to canonical watch-page URLs so yt-dlp handles them.
// api.redgifs.com/v2/gifs/{id}/sd.m3u8 → www.redgifs.com/watch/{id}
function normalizeApiUrl(url) {
  try {
    var u = new URL(url);
    if (u.hostname === 'api.redgifs.com') {
      var m = u.pathname.match(/^\/v2\/gifs\/([^\/]+)\//);
      if (m) return 'https://www.redgifs.com/watch/' + m[1];
    }
  } catch(e) {}
  return url;
}

browser.webRequest.onHeadersReceived.addListener(
  function(details) {
    if (!interceptEnabled) return {};
    var url = details.url;
    var lowerUrl = url.toLowerCase();
    console.log("LDM intercept check:", url);
    for (var sd = 0; sd < skipDomains.length; sd++) {
      if (lowerUrl.includes(skipDomains[sd])) return {};
    }
    if (lowerUrl.startsWith("blob:") || lowerUrl.startsWith("data:")) return {};
    // Tracking / fingerprinting / beacon endpoints occasionally ship a
    // Content-Disposition: attachment to dodge caches — that triggers our
    // download intercept on a request the user never asked to download.
    // Filter by common host/path signals.
    var trackingHostPrefixes = [
      "privacy-", "privacy.", "metrics.", "analytics.", "telemetry.",
      "tracking.", "beacon.", "pixel.", "tags.", "stats."
    ];
    var trackingPathPatterns = [
      "/fp/", "/fp?", "/fingerprint", "/beacon", "/pixel",
      "/telemetry", "/collect", "/track?", "/track/", "/r/collect",
      "/getcaptcha/", "/captcha/", "/challenge/", "/v2/anchor", "/v2/reload",
      "/recaptcha/", "/hcaptcha/",
    ];
    try {
      var u = new URL(url);
      var host = u.hostname.toLowerCase();
      var pathQ = (u.pathname + u.search).toLowerCase();
      for (var tp = 0; tp < trackingHostPrefixes.length; tp++) {
        if (host.startsWith(trackingHostPrefixes[tp])) return {};
      }
      for (var tq = 0; tq < trackingPathPatterns.length; tq++) {
        if (pathQ.indexOf(trackingPathPatterns[tq]) !== -1) return {};
      }
    } catch (e) {}
    var allowedTypes = ["main_frame", "sub_frame", "other", "xmlhttprequest", "media"];
    if (allowedTypes.indexOf(details.type) === -1) return {};
    var headers = details.responseHeaders || [];
    var contentDisposition = null;
    var contentType = null;
    for (var i = 0; i < headers.length; i++) {
      var name = headers[i].name.toLowerCase();
      if (name === "content-disposition") contentDisposition = headers[i];
      if (name === "content-type") contentType = headers[i];
    }
    // Also catch manifest URLs by extension regardless of MIME
    var urlPathLower = url.split("?")[0].toLowerCase();
    var isManifest = urlPathLower.endsWith(".m3u8") || urlPathLower.endsWith(".mpd");
    var isAttachment = contentDisposition &&
      contentDisposition.value.toLowerCase().includes("attachment");
    // Player-initiated loads (<video>/<audio> src): some CDNs force
    // Content-Disposition: attachment, but the user is streaming, not
    // downloading. Capture button is the explicit download path.
    if (details.type === "media") isAttachment = false;
    var downloadTypes = [
      "application/octet-stream",
      "application/zip",
      "application/x-zip",
      "application/x-rar",
      "application/x-7z-compressed",
      "application/x-tar",
      "application/gzip",
      "application/x-bzip2",
      "application/vnd.android.package-archive",
      "application/x-msdownload",
      "application/x-debian-package",
      "application/x-rpm",
      "application/pdf",
      "audio/mpeg",
      "audio/flac",
      "audio/wav",
      "audio/aac",
      "audio/ogg",
      "audio/x-m4a",
      "video/mp4",
      "video/x-matroska",
      "video/webm",
      "video/avi",
      "video/quicktime",
      "video/mp2t",
      "video/vnd.dlna.mpeg-tts",
      "application/dash+xml",
      "application/x-mpegurl",
      "application/vnd.apple.mpegurl",
      "application/vnd.ms-sstr+xml"
    ];
    var isBinaryType = false;
    if (contentType) {
      var ctLower = contentType.value.toLowerCase();
      for (var j = 0; j < downloadTypes.length; j++) {
        if (ctLower.includes(downloadTypes[j])) {
          isBinaryType = true;
          break;
        }
      }
    }
    // Auto-intercept:
    //   1. Explicit attachment downloads (Content-Disposition: attachment)
    //   2. HLS/DASH manifests
    //   3. Binary file types (zip, rar, exe, apk etc.) even without attachment header
    // Inline video/audio must NOT be cancelled -- breaks in-browser players.
    // PDF excluded from binary intercept -- user may want to view in browser.
    // Social CDN: passively store fbcdn/twimg/tiktok video URLs per tab.
    // Must run BEFORE the early return below — these are inline video, not attachments.
    // NEVER cancel — the browser player needs these to play normally.
    if (isSocialCDN(url)) {
      var videoId = decodeFbVideoId(url);
      var isTwimg = url.includes("video.twimg.com");
      var isTikTok = false;
      try { isTikTok = /^v\d+[-\w]*\.tiktok\.com$/.test(new URL(url).hostname); } catch(e) {}
      // Only store actual video files/manifests, not thumbnails or tiny clips
      var contentLen = 0;
      for (var ci = 0; ci < headers.length; ci++) {
        if (headers[ci].name.toLowerCase() === 'content-length') {
          contentLen = parseInt(headers[ci].value) || 0;
        }
      }
      // fbcdn/cdninstagram serve DASH byte-range chunks — tiny segments that
      // are useless for download. Skip storing them; capture falls through to
      // post permalink URL → yt-dlp instead.
      var isFbcdn = url.includes("fbcdn.net") || url.includes("cdninstagram.com");
      if (isFbcdn) return {};
      var isVideoUrl = isTwimg ||
        isTikTok ||
        url.split("?")[0].toLowerCase().endsWith(".mp4") ||
        (contentType && contentType.value.toLowerCase().includes("video/"));
      var isTikTokVideo = isTikTok && url.includes("mime_type=video_mp4");
      var sizeOk = isTikTok ? isTikTokVideo
                 : contentLen > 100000;
      if (isVideoUrl && sizeOk) {
        var entry = {
          cdnUrl:  url,
          videoId: videoId,
          isTwimg: isTwimg,
          ts:      Date.now(),
        };
        socialStoreAdd(details.tabId, entry);
        browser.tabs.sendMessage(details.tabId, {
          action: 'storeCdnEntry',
          entry:  entry,
        }).catch(function() {});
      }
      return {};
    }

    var isNonVideoAttachment = isBinaryType && contentType && (() => {
      var ct = contentType.value.toLowerCase();
      return !ct.startsWith('video/') && !ct.startsWith('audio/') &&
             !ct.includes('application/pdf');
    })();
    // Intercept direct navigation to video/audio files (main_frame .mp4, .mkv etc.)
    var isDirectVideoNav = details.type === "main_frame" && isVideoAudio(url, contentType);
    if (!isAttachment && !isManifest && !isNonVideoAttachment && !isDirectVideoNav) return {};
    if (contentType) {
      var ct = contentType.value.toLowerCase();
      if (ct.startsWith("image/")) return {};
      if (ct.startsWith("text/")) return {};
      if (ct.includes("application/json")) return {};
      if (ct.includes("application/javascript")) return {};
      if (ct.includes("application/wasm")) return {};
      if (ct.includes("application/xhtml")) return {};
      if (ct.includes("text/x-python")) return {};
      if (ct.includes("text/x-sh")) return {};
      if (ct.includes("application/x-python")) return {};
      if (ct.startsWith("font/")) return {};
      if (ct.includes("application/font-")) return {};
      if (ct.includes("application/x-font-")) return {};
      if (ct.includes("model/gltf")) return {};
    }
    var urlPath = stripVersionSuffix(url.split("?")[0].toLowerCase());
    for (var k = 0; k < skipExts.length; k++) {
      if (urlPath.endsWith(skipExts[k])) return {};
    }
    if (handledUrls.has(url)) {
      handledUrls.delete(url);
      return { cancel: true };
    }
    var filename = "";
    if (contentDisposition) {
      // RFC 5987 form takes priority: filename*=UTF-8''<percent-encoded>.
      // Match the charset/lang block as one unit so the value capture can't
      // bleed back into "UTF-8" (which the old regex captured as the name).
      var cdVal = contentDisposition.value;
      var rfc = cdVal.match(/filename\*\s*=\s*[\w-]+'[^']*'([^;\r\n]+)/i);
      if (rfc) {
        try { filename = decodeURIComponent(rfc[1].trim()); }
        catch (e) { filename = rfc[1].trim(); }
      }
      if (!filename) {
        var q = cdVal.match(/filename\s*=\s*"([^"]+)"/i);
        if (q) filename = q[1].trim();
      }
      if (!filename) {
        var bare = cdVal.match(/filename\s*=\s*([^;\r\n]+)/i);
        if (bare) filename = bare[1].trim().replace(/^["']|["']$/g, '');
      }
    }
    if (!filename) {
      filename = url.split("?")[0].split("/").pop() || "download";
    }
    try { filename = decodeURIComponent(filename); } catch (e) {}
    // Tracking / identity APIs (e.g. first-id.fr/firstId, .../api/v1/info) ship
    // a Content-Disposition: attachment or octet-stream body to dodge caches,
    // which trips the intercept on a request the user never asked to save —
    // they landed in the list as bogus "info" / "firstId" downloads. A genuine
    // file download resolves to a name with an extension; a bare, extension-less
    // name on an XHR/fetch ("other") request is an API response, not a file.
    if ((details.type === "xmlhttprequest" || details.type === "other") &&
        filename.indexOf(".") === -1) {
      return {};
    }
    var filenameLower = stripVersionSuffix(filename.toLowerCase());
    for (var m = 0; m < skipExts.length; m++) {
      if (filenameLower.endsWith(skipExts[m])) return {};
    }
    // Skip HLS/DASH segment URLs — numbered chunks served by CDNs
    var segmentPatterns = [
      /\/seg[-_]?\d+/i,
      /\/chunk[-_]?\d+/i,
      /\/fragment[-_]?\d+/i,
      /\/media[-_]?\d+/i,
      /[&?]segment=\d+/i,
      /\/\d+\.enc(\?|$)/i,
      /\/\d+\.ts(\?|$)/i,
      /\/\d+\.m4s(\?|$)/i,
    ];
    for (var n = 0; n < segmentPatterns.length; n++) {
      if (segmentPatterns[n].test(url)) return {};
    }
    var referer = details.documentUrl || details.originUrl || "";

    // Manifests: store silently per tab so Capture button can use them.
    // NEVER cancel — the browser player needs these to function normally.
    // Skip CF-protected domains — their m3u8 expires quickly, page URL is better.
    var isHLSType = contentType && (
      contentType.value.toLowerCase().includes("mpegurl") ||
      contentType.value.toLowerCase().includes("dash+xml")
    );
    if (isManifest || isHLSType) {
      if (!isCFProtected(url)) {
        tabM3u8Store[details.tabId] = normalizeApiUrl(url);
      }
      return {};
    }

    // Video/audio: intercept if it's a direct navigation or explicit attachment.
    // Inline video/audio (embedded players) pass through — Capture button handles them.
    if (isVideoAudio(url, contentType) && !isAttachment && !isDirectVideoNav) return {};

    // Category allow-list: only auto-capture files whose extension maps to one
    // of LDM's download categories. Anything else is left to the browser.
    if (!inAllowedCategory(filename)) return {};

    // Attachment downloads only — intercept and send to LDM
    if (handledUrls.has(url)) {
      handledUrls.delete(url);
      return { cancel: true };
    }
    handledUrls.add(url);
    sendToPython(url, filename, "file", referer);
    return { cancel: true };
  },
  { urls: ["<all_urls>"] },
  ["blocking", "responseHeaders"]
);

browser.downloads.onCreated.addListener(function(downloadItem) {
  var url = downloadItem.url || "";
  var lowerUrl = url.toLowerCase();
  if (!lowerUrl.startsWith("blob:") && !lowerUrl.startsWith("data:")) {
    return;
  }
  if (lowerUrl.startsWith("blob:https://mega.nz") ||
      lowerUrl.startsWith("blob:https://mega.co.nz")) {
    return;
  }
  var filename = (downloadItem.filename || "").split(/[\\/]/).pop() || "";
  for (var i = 0; i < skipExts.length; i++) {
    if (filename.toLowerCase().endsWith(skipExts[i])) return;
  }
  var mime = (downloadItem.mime || "").toLowerCase();
  if (mime.startsWith("image/")) return;
  if (mime.startsWith("text/")) return;
  var hasExt = filename.includes(".");
  if (!hasExt && mime === "application/octet-stream") return;
  if (!hasExt && mime === "") return;
  if (!interceptEnabled) return;
  // Blocked hosts (claude.ai, figma.com, …) are intentionally left to Firefox.
  // sendToPython() already no-ops on them, but we must also skip the erase()
  // below — otherwise Firefox downloads the file fine yet we wipe it from its
  // download list, making it look like the download vanished.
  if (isBlockedHost(url)) return;
  // Only route category files through LDM; let the browser keep the rest.
  if (!inAllowedCategory(filename)) return;
  sendToPython(url, filename || "download", "file", "");
  browser.downloads.erase({ id: downloadItem.id });
});

// Hosts whose downloads must never be routed through LDM (Claude artifacts,
// design handoffs, etc. — the user explicitly opted these out).
var BLOCKED_HOSTS = ["claude.ai", "anthropic.com", "figma.com"];

function isBlockedHost(url) {
  if (!url) return false;
  // blob:/filesystem: wrap an inner origin; URL.hostname returns "" for them,
  // so peel the wrapper before parsing.
  var u = url;
  var low = u.toLowerCase();
  if (low.indexOf("blob:") === 0 || low.indexOf("filesystem:") === 0) {
    u = u.slice(u.indexOf(":") + 1);
  }
  try {
    var host = new URL(u).hostname.toLowerCase();
    for (var i = 0; i < BLOCKED_HOSTS.length; i++) {
      var h = BLOCKED_HOSTS[i];
      if (host === h || host.endsWith("." + h)) return true;
    }
  } catch (e) {}
  return false;
}

// Collect cookies for the target (and page) URL so LDM can authenticate
// downloads without reading the browser profile from disk — required for the
// Flatpak build, which is sandboxed away from ~/.mozilla et al.
function collectBridgeCookies(url, referer) {
  var urls = [];
  if (url) urls.push(url);
  if (referer && referer !== url) urls.push(referer);
  if (!urls.length || !browser.cookies || !browser.cookies.getAll) {
    return Promise.resolve([]);
  }
  var jobs = urls.map(function(u) {
    return browser.cookies.getAll({ url: u }).catch(function() { return []; });
  });
  return Promise.all(jobs).then(function(lists) {
    var seen = {}, out = [];
    lists.forEach(function(list) {
      (list || []).forEach(function(c) {
        var k = c.domain + "|" + c.path + "|" + c.name;
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
  }).catch(function() { return []; });
}

function sendToPython(url, filename, type, referer) {
  if (isBlockedHost(url)) return;
  referer = referer || "";
  collectBridgeCookies(url, referer).then(function(cookies) {
    // text/plain keeps it a "simple" request (no CORS preflight); the app
    // parses the body as JSON regardless of the declared content type.
    fetch("http://127.0.0.1:9999/", {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: JSON.stringify({
        url: url, filename: filename, type: type,
        referer: referer, cookies: cookies
      })
    }).catch(function() {
      console.error("Linux Download Manager is not running.");
    });
  });
}

// Relay bridge calls from content scripts (avoids iframe CORS blocks)
browser.runtime.onMessage.addListener(function(message, sender, sendResponse) {
  if (message.action === 'bridge') {
    // Carry the page URL through as referer. LDM uses it both as the
    // outgoing Referer header for CDN fetches and to recover when a
    // captured CDN URL on its own can't yield a playable video (e.g.
    // Twitter DASH .m4s segments — yt-dlp's TwitterIE needs the tweet
    // status URL to extract the full video).
    var ref = (message.referer || (sender && sender.tab && sender.tab.url) || '');
    sendToPython(message.url, message.filename || 'download', message.type || 'file', ref);
    sendResponse({ ok: true });
  }
  // Return stored m3u8 for current tab (called from content.js Capture button)
  if (message.action === 'getM3u8') {
    var tabId = sender.tab ? sender.tab.id : null;
    var m3u8  = tabId ? (tabM3u8Store[tabId] || null) : null;
    sendResponse({ url: m3u8 });
  }
  // Return stored m3u8 by explicit tabId (called from popup.js)
  if (message.action === 'getM3u8ForTab') {
    var m3u8 = tabM3u8Store[message.tabId] || null;
    sendResponse({ url: m3u8 });
  }
  // Return most recent social CDN video for current tab (content.js)
  if (message.action === 'getSocialVideo') {
    var tabId = sender.tab ? sender.tab.id : null;
    var entry = tabId && tabSocialStore[tabId] && tabSocialStore[tabId].length
      ? tabSocialStore[tabId][0] : null;
    sendResponse({ entry: entry });
  }
  // Return social CDN video by explicit tabId (popup.js)
  if (message.action === 'getSocialVideoForTab') {
    var entries = tabSocialStore[message.tabId] || [];
    // Prefer entry matching videoId hint if provided
    var entry = null;
    if (message.videoId) {
      entry = entries.find(function(e) { return e.videoId === message.videoId; }) || null;
    }
    if (!entry) entry = entries[0] || null;
    sendResponse({ entry: entry });
  }
  return true;
});