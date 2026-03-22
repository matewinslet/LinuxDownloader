// popup.js - Linux Download Manager

// Capture Stream — smart routing: YouTube → YouTubeDialog, else stream
document.getElementById('captureBtn').addEventListener('click', async () => {
  const btn = document.getElementById('captureBtn');
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const lower = tab.url.toLowerCase();
  const isYT  = lower.includes('youtube.com/watch') ||
                lower.includes('youtu.be/') ||
                lower.includes('youtube.com/shorts');

  // YouTube — route directly to YouTubeDialog
  if (isYT) {
    const bridgeUrl = `http://127.0.0.1:9999/?url=${encodeURIComponent(tab.url)}&filename=youtube&type=youtube`;
    fetch(bridgeUrl)
      .then(() => {
        btn.innerHTML = '&#10003; Sent to YouTube Downloader!';
        btn.style.background = '#dc2626';
        setTimeout(() => { btn.innerHTML = '&#11015; Capture Stream'; btn.style.background = ''; }, 2500);
      })
      .catch(() => { btn.innerText = 'Error: App Closed?'; btn.style.background = '#c0392b'; });
    return;
  }

  // CF-only domains (luluvdo etc.) — page URL → yt-dlp
  const cfDomains = ['luluvdo.com', 'lulustream.com', 'doodstream.com', 'dood.watch', 'dood.to'];
  const isCF = cfDomains.some(d => tab.url.includes(d));
  if (isCF) {
    const pageUrl = normalizeUrl(tab.url);
    const bridgeUrl = `http://127.0.0.1:9999/?url=${encodeURIComponent(pageUrl)}&filename=${encodeURIComponent(resolveFilename(pageUrl, tab.title))}&type=stream_hls&referer=${encodeURIComponent(pageUrl)}`;
    fetch(bridgeUrl)
      .then(() => {
        btn.innerHTML = '&#10003; Sent to LDM!';
        btn.style.background = '#27ae60';
        setTimeout(() => { btn.innerHTML = '&#11015; Capture Stream'; btn.style.background = ''; }, 2500);
      })
      .catch(() => { btn.innerText = 'Error: App Closed?'; btn.style.background = '#c0392b'; });
    return;
  }

  // Social domains (Facebook, Instagram, Twitter/X) — try CDN store first
  const socialDomains = ['facebook.com', 'fb.watch', 'instagram.com', 'twitter.com', 'x.com'];
  const isSocial = socialDomains.some(d => tab.url.includes(d));
  if (isSocial) {
    const videoId = (tab.url.match(/\/status\/(\d+)/) || tab.url.match(/(?:reel|video|videos)\/?([\d]+)/) || [])[1] || null;
    const socialResp = await new Promise(r =>
      chrome.runtime.sendMessage({ action: 'getSocialVideoForTab', tabId: tab.id, videoId: videoId }, r)
    );
    if (socialResp && socialResp.entry) {
      const entry      = socialResp.entry;
      const pageUrl    = normalizeUrl(tab.url);
      const type       = entry.isTwimg ? 'stream_hls' : 'video_stream';
      const filename   = resolveSocialFilename(entry, tab.url, tab.title);
      const bridgeUrl  = `http://127.0.0.1:9999/?url=${encodeURIComponent(entry.cdnUrl)}&filename=${encodeURIComponent(filename)}&type=${type}&referer=${encodeURIComponent(pageUrl)}`;
      fetch(bridgeUrl)
        .then(() => {
          btn.innerHTML = '&#10003; Sent to LDM!';
          btn.style.background = '#27ae60';
          setTimeout(() => { btn.innerHTML = '&#11015; Capture Stream'; btn.style.background = ''; }, 2500);
        })
        .catch(() => { btn.innerText = 'Error: App Closed?'; btn.style.background = '#c0392b'; });
      return;
    }
    // No CDN URL — fall through to page URL → yt-dlp below
  }

  // Check background for a passively stored m3u8 (vidara etc.)
  const stored = await new Promise(r =>
    chrome.runtime.sendMessage({ action: 'getM3u8ForTab', tabId: tab.id }, r)
  );
  if (stored && stored.url) {
    const captureFilename = resolveFilename(stored.url, tab.title);
    const bridgeUrl = `http://127.0.0.1:9999/?url=${encodeURIComponent(stored.url)}&filename=${encodeURIComponent(captureFilename)}&type=stream_hls&referer=${encodeURIComponent(tab.url)}`;
    fetch(bridgeUrl)
      .then(() => {
        btn.innerHTML = '&#10003; Sent to LDM!';
        btn.style.background = '#27ae60';
        setTimeout(() => { btn.innerHTML = '&#11015; Capture Stream'; btn.style.background = ''; }, 2500);
      })
      .catch(() => { btn.innerText = 'Error: App Closed?'; btn.style.background = '#c0392b'; });
    return;
  }

  // No m3u8 stored — try DOM scan across frames
  let found = null;
  try {
    const frames = await browser.webNavigation.getAllFrames({ tabId: tab.id });
    for (const frame of frames) {
      try {
        const resp = await browser.tabs.sendMessage(
          tab.id, { action: 'grab' }, { frameId: frame.frameId }
        );
        if (resp && resp.url) { found = resp; break; }
      } catch(e) {}
    }
  } catch(e) {}

  if (found && found.url) {
    const captureUrl      = found.url;
    const captureFilename = resolveFilename(captureUrl, tab.title);
    const captureType     = found.isHLS ? 'stream_hls' : 'video_stream';
    const bridgeUrl = `http://127.0.0.1:9999/?url=${encodeURIComponent(captureUrl)}&filename=${encodeURIComponent(captureFilename)}&type=${captureType}&referer=${encodeURIComponent(tab.url)}`;
    fetch(bridgeUrl)
      .then(() => {
        btn.innerHTML = '&#10003; Sent to LDM!';
        btn.style.background = '#27ae60';
        setTimeout(() => { btn.innerHTML = '&#11015; Capture Stream'; btn.style.background = ''; }, 2500);
      })
      .catch(() => { btn.innerText = 'Error: App Closed?'; btn.style.background = '#c0392b'; });
    return;
  }

  // Nothing found — likely a site that needs play pressed first (vidara etc.)
  // Try page URL anyway; StreamDialog will show a clear message if it fails.
  const pageUrl     = normalizeUrl(tab.url);
  const pageFilename = resolveFilename(pageUrl, tab.title);
  const bridgeUrl = `http://127.0.0.1:9999/?url=${encodeURIComponent(pageUrl)}&filename=${encodeURIComponent(pageFilename)}&type=stream_hls&referer=${encodeURIComponent(pageUrl)}`;
  fetch(bridgeUrl)
    .then(() => {
      btn.innerHTML = '&#9654; Sent — press Play if no window opens';
      btn.style.background = '#f97316';
      setTimeout(() => { btn.innerHTML = '&#11015; Capture Stream'; btn.style.background = ''; }, 3000);
    })
    .catch(() => { btn.innerText = 'Error: App Closed?'; btn.style.background = '#c0392b'; });
});

function normalizeUrl(url) {
  try {
    var u = new URL(url);
    u.pathname = u.pathname.replace(/^\/e\//, '/').replace(/^\/embed\//, '/');
    ['__cft__', '__tn__', '_nc_cat', '_nc_sid', 'paipv', 'eav'].forEach(p => u.searchParams.delete(p));
    return u.toString();
  } catch(e) { return url; }
}

function resolveSocialFilename(entry, pageUrl, pageTitle) {
  try {
    var host = new URL(pageUrl).hostname;
    var ts   = new Date().toISOString().slice(0,19).replace(/[:T]/g,'-');
    if (host.includes('twitter.com') || host.includes('x.com')) {
      var m = pageUrl.match(/\/status\/(\d+)/);
      return m ? 'twitter_' + m[1] + '.mp4' : 'twitter_' + ts + '.mp4';
    }
    if (entry && entry.videoId) {
      if (host.includes('instagram')) return 'instagram_' + entry.videoId + '.mp4';
      if (host.includes('facebook') || host.includes('fb.watch')) return 'facebook_' + entry.videoId + '.mp4';
    }
    return 'social_video_' + ts + '.mp4';
  } catch(e) { return 'social_video.mp4'; }
}

// Unlock Right-click
document.getElementById('unlockBtn').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { action: 'unlock' });
  const titleEl = document.querySelector('#unlockBtn .btn-title');
  if (titleEl) titleEl.textContent = '\u2713 Unlocked!';
  document.getElementById('unlockBtn').style.borderColor = '#27ae60';
});

// Capture YouTube
document.getElementById('youtubeBtn').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab.url, lower = url.toLowerCase();
  const isYoutube = lower.includes('youtube.com/watch') || lower.includes('youtu.be/') || lower.includes('youtube.com/shorts');
  if (!isYoutube) {
    document.getElementById('youtubeBtn').innerText = 'Not a YouTube page';
    document.getElementById('youtubeBtn').style.background = '#7f8c8d';
    return;
  }
  const bridgeUrl = `http://127.0.0.1:9999/?url=${encodeURIComponent(url)}&filename=youtube&type=youtube`;
  fetch(bridgeUrl)
    .then(() => { document.getElementById('youtubeBtn').innerHTML = '&#10003; Sent to LDM!'; })
    .catch(() => { document.getElementById('youtubeBtn').innerText = 'Error: App Closed?'; document.getElementById('youtubeBtn').style.background = '#c0392b'; });
});

// Auto Intercept toggle
const toggle = document.getElementById('interceptToggle');
const sub    = document.getElementById('toggleSub');
browser.storage.local.get('interceptEnabled').then((result) => {
  const enabled = result.interceptEnabled !== false;
  toggle.checked = enabled;
  sub.textContent = enabled ? 'Sending to Linux DM' : 'Firefox handles downloads';
});
toggle.addEventListener('change', () => {
  const enabled = toggle.checked;
  browser.storage.local.set({ interceptEnabled: enabled });
  sub.textContent = enabled ? 'Sending to Linux DM' : 'Firefox handles downloads';
});

// Filename resolver
function resolveFilename(url, pageTitle) {
  const videoExts = ['mp4','mkv','webm','avi','mov','ts','flv','m4v'];
  const pathPart = url.split('?')[0].split('/').pop();
  if (pathPart && pathPart.includes('.')) {
    const ext = pathPart.split('.').pop().toLowerCase();
    if (videoExts.includes(ext)) return pathPart;
  }
  const urlExt = (() => { const e = url.split('?')[0].split('.').pop().toLowerCase(); return videoExts.includes(e) ? e : 'mp4'; })();
  if (pageTitle && pageTitle.trim()) {
    const safe = pageTitle.trim().replace(/[^\w\s\-]/g,'').replace(/\s+/g,'_').slice(0,60).replace(/_+$/,'');
    if (safe) return `${safe}.${urlExt}`;
  }
  const now = new Date();
  const ts = now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0')+'-'+String(now.getDate()).padStart(2,'0')+'_'+String(now.getHours()).padStart(2,'0')+'-'+String(now.getMinutes()).padStart(2,'0')+'-'+String(now.getSeconds()).padStart(2,'0');
  return `video_${ts}.${urlExt}`;
}
