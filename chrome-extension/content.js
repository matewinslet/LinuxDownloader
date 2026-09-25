// content.js - Linux Download Manager
// Smart floating button: YouTube → YouTubeDialog, stream → StreamDialog

(function () {
  'use strict';

  const YOUTUBE_HOSTS = ['youtube.com', 'youtu.be', 'youtube-nocookie.com'];

  function isYouTubePage() {
    const host = window.location.hostname.replace('www.', '');
    const path = window.location.pathname;
    return YOUTUBE_HOSTS.some(h => host.includes(h)) &&
      (path.includes('/watch') || path.includes('/shorts') || host === 'youtu.be');
  }

  // ── Stream detection ──────────────────────────────────────────────────────
  function detectStream(video) {
    if (!video) video = document.querySelector('video');
    if (!video) return { url: null, isHLS: false };
    let url = null, isHLS = false;
    if (video.src && !video.src.startsWith('blob:')) {
      url = video.src; isHLS = url.includes('.m3u8');
    } else {
      const source = video.querySelector('source');
      if (source && source.src && !source.src.startsWith('blob:')) {
        url = source.src; isHLS = url.includes('.m3u8');
      }
    }
    if (!url && window.hls && window.hls.url) { url = window.hls.url; isHLS = true; }
    if (!url) { try { if (window.videojs) {
      const p = Object.values(window.videojs.getPlayers ? window.videojs.getPlayers() : {})[0];
      if (p) { url = p.currentSrc(); isHLS = url && url.includes('.m3u8'); }
    }} catch(e) {} }
    if (!url) { try { if (window.jwplayer) {
      const p = window.jwplayer(), item = p && p.getPlaylistItem && p.getPlaylistItem();
      if (item) { url = item.file || (item.sources && item.sources[0] && item.sources[0].file); isHLS = url && url.includes('.m3u8'); }
    }} catch(e) {} }
    return { url: url || null, isHLS: !!isHLS };
  }

  // ── Relay through background.js (avoids iframe CORS) ─────────────────────
  function relayToBridge(url, type, filename) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(
        { action: 'bridge', url, type, filename },
        (resp) => {
          if (chrome.runtime.lastError) reject(chrome.runtime.lastError);
          else if (resp && resp.ok) resolve();
          else reject(new Error('bridge failed'));
        }
      );
    });
  }

  function resolveFilename(url, pageTitle) {
    const videoExts = ['mp4','mkv','webm','avi','mov','ts','flv','m4v'];
    const pathPart = url.split('?')[0].split('/').pop();
    if (pathPart && pathPart.includes('.')) {
      const ext = pathPart.split('.').pop().toLowerCase();
      if (videoExts.includes(ext)) return pathPart;
    }
    const urlExt = (() => {
      const e = url.split('?')[0].split('.').pop().toLowerCase();
      return videoExts.includes(e) ? e : 'mp4';
    })();
    if (pageTitle && pageTitle.trim()) {
      const safe = pageTitle.trim()
        .replace(/[^\w\s\-]/g, '').replace(/\s+/g, '_')
        .slice(0, 60).replace(/_+$/, '');
      if (safe) return `${safe}.${urlExt}`;
    }
    const now = new Date();
    const ts = now.getFullYear() + '-' +
      String(now.getMonth() + 1).padStart(2, '0') + '-' +
      String(now.getDate()).padStart(2, '0') + '_' +
      String(now.getHours()).padStart(2, '0') + '-' +
      String(now.getMinutes()).padStart(2, '0') + '-' +
      String(now.getSeconds()).padStart(2, '0');
    return `video_${ts}.${urlExt}`;
  }

  // ── URL normalizer — strips /e/, /embed/ iframe prefixes ─────────────────
  function normalizeStreamUrl(url) {
    try {
      var u = new URL(url);
      u.pathname = u.pathname.replace(/^\/e\//, '/').replace(/^\/embed\//, '/');
      ['__cft__', '__tn__', '_nc_cat', '_nc_sid', 'paipv', 'eav'].forEach(function(p) {
        u.searchParams.delete(p);
      });
      return u.toString();
    } catch(e) { return url; }
  }

  // Story URL patterns — no overlay, no download attempt
  var STORY_PATTERNS = [
    /facebook\.com\/stories\//,
    /facebook\.com\/story\.php/,
    /instagram\.com\/stories\//,
  ];
  function isStoryUrl(url) {
    return STORY_PATTERNS.some(function(p) { return p.test(url); });
  }

  // Returns true if the current URL is a specific Facebook video/reel page
  // (not the homepage, feed, groups, or /reels/ browse page).
  function isFacebookVideoPage(url) {
    try {
      var u    = new URL(url);
      var host = u.hostname;
      if (!host.includes('facebook.com') && !host.includes('fb.watch')) return false;
      if (host.includes('fb.watch')) return true;   // fb.watch/XXXX short links
      var path = u.pathname;
      return (
        /[?&]v=\d+/.test(u.search)           ||  // /watch?v=123
        /\/reel(\/|$)/.test(path)             ||  // /reel/ID or bare /reel/ (LDM shows paste dialog for bare)
        /\/videos\/\d+/.test(path)            ||  // /username/videos/ID
        /\/share\/[vr]\//.test(path)              // /share/v/ID or /share/r/ID
      );
    } catch(e) { return false; }
  }

  // Overlay suppression rules for social platforms
  // Returns true if overlay should be suppressed on this page
  function isSuppressedPage(url) {
    if (isStoryUrl(url)) return true;
    // Facebook: only show capture button on specific video/reel pages.
    // Suppress homepage, feed, groups, /reels/ browse — anything not a video page.
    try {
      var h = new URL(url).hostname;
      if (h.includes('facebook.com')) {
        if (!isFacebookVideoPage(url)) return true;
      }
      // MEGA: player uses blob: URLs backed by client-side decryption;
      // neither direct capture nor yt-dlp can handle it.
      if (h.endsWith('mega.nz') || h.endsWith('mega.co.nz')) return true;
    } catch(e) {}
    return false;
  }

  // YouTube homepage/browse — suppress overlay per-video (not in isSuppressedPage,
  // because YouTube SPA may mutate DOM before URL updates, blocking attachToVideos).
  function isYouTubeNonVideo() {
    const host = window.location.hostname.replace('www.', '');
    return YOUTUBE_HOSTS.some(h => host.includes(h)) && !isYouTubePage();
  }

  // Social domains — use CDN store + yt-dlp fallback, not direct page URL
  var SOCIAL_DOMAINS = ['facebook.com', 'fb.watch', 'twitter.com', 'x.com', 'instagram.com', 'tiktok.com'];
  function isSocialDomain(url) {
    try { var h = new URL(url).hostname; return SOCIAL_DOMAINS.some(function(d) { return h.includes(d); }); }
    catch(e) { return false; }
  }

  // CF domains (luluvdo etc.) — always page URL → yt-dlp
  var CF_DOMAINS = ['luluvid.com', 'luluvdo.com', 'lulustream.com', 'doodstream.com', 'dood.watch', 'dood.to'];
  function isCFProtected(url) {
    try { var h = new URL(url).hostname; return CF_DOMAINS.some(function(d) { return h.includes(d); }); }
    catch(e) { return false; }
  }

  // Extract Twitter status ID from page URL
  function getTwitterStatusId(url) {
    var m = url.match(/\/status\/(\d+)/);
    return m ? m[1] : null;
  }

  // Extract Facebook/Instagram video ID from page URL
  function getFbVideoId(url) {
    // Numeric ID: /videos/ID, /reel/ID, watch?v=ID
    var m = url.match(/(?:reel|video|watch(?:\?v=)|videos)\/?([\d]+)/);
    if (m) return m[1];
    // Alphanumeric share URLs: /share/v/ID or /share/r/ID
    m = url.match(/\/share\/[vr]\/([A-Za-z0-9_\-]+)/);
    if (m) return m[1];
    return null;
  }
  // ── Smart capture ─────────────────────────────────────────────────────────
  // Walk up from video element to find nearest post permalink in feed DOM.
  function extractPostUrl(videoEl) {
    if (!videoEl) return null;
    var host = window.location.hostname;
    var patterns = [];
    if (host.includes('instagram.com')) {
      patterns = [/^\/(?:p|reel|reels|tv)\/[A-Za-z0-9_\-]+\/?$/];
    } else if (host.includes('facebook.com') || host.includes('fb.watch')) {
      // Require an ID after reel/watch/videos — bare /reel/ anchors are useless
      patterns = [/\/(?:reel|videos)\/\d+/, /\/watch\/\?v=\d+/, /[?&]v=\d+/];
    } else if (host.includes('twitter.com') || host.includes('x.com')) {
      patterns = [/\/status\/\d+/];
    }
    if (!patterns.length) return null;
    var el = videoEl.parentElement;
    var depth = 0;
    while (el && depth < 40) {
      var links = el.querySelectorAll('a[href]');
      for (var i = 0; i < links.length; i++) {
        var href = links[i].getAttribute('href') || '';
        for (var j = 0; j < patterns.length; j++) {
          if (patterns[j].test(href)) {
            try { return new URL(href, window.location.origin).toString(); }
            catch(e) { return null; }
          }
        }
      }
      el = el.parentElement;
      depth++;
    }
    return null;
  }

  function captureVideo(videoEl) {
    if (isYouTubePage()) {
      return relayToBridge(window.location.href, 'youtube', 'youtube');
    }

    const pageUrl = normalizeStreamUrl(window.location.href);

    if (isStoryUrl(pageUrl)) {
      return Promise.reject(new Error('Story — not downloadable'));
    }

    // CF-only domains (luluvdo etc.) — page URL → yt-dlp
    if (isCFProtected(pageUrl)) {
      const filename = resolveFilename(pageUrl, document.title);
      return relayToBridge(pageUrl, 'stream_hls', filename);
    }

    // Facebook video page: address bar URL → yt-dlp directly.
    // isFacebookVideoPage requires an ID in the URL, so this is always a valid permalink.
    if (isFacebookVideoPage(pageUrl)) {
      const filename = resolveFilename(pageUrl, document.title);
      return Promise.resolve(relayToBridge(pageUrl, 'stream_hls', filename));
    }

    // Social domains (Instagram, Twitter, TikTok — not Facebook feed, handled above)
    if (isSocialDomain(pageUrl)) {
      return new Promise((resolve, reject) => {
        // Priority 1: CDN entry on THIS video element (set at play time)
        // Most accurate for feed pages with multiple videos
        if (videoEl && videoEl._ldmCdnEntry) {
          const entry    = videoEl._ldmCdnEntry;
          const filename = resolveSocialFilename(entry, pageUrl);
          resolve(relayToBridge(entry.cdnUrl, 'stream_hls', filename));
          return;
        }
        // Priority 2: DOM traversal -- find post permalink from feed article
        // e.g. instagram.com/reels/ID/ from the <a> wrapping the video
        const postUrl = extractPostUrl(videoEl);
        if (postUrl && postUrl !== pageUrl) {
          const filename = resolveFilename(postUrl, document.title);
          resolve(relayToBridge(postUrl, 'stream_hls', filename));
          return;
        }
        // Priority 3: tab-level CDN store (post/reel pages, single video)
        const videoId = getFbVideoId(pageUrl) || getTwitterStatusId(pageUrl);
        chrome.runtime.sendMessage(
          { action: 'getSocialVideo', videoId: videoId },
          (resp) => {
            if (!chrome.runtime.lastError && resp && resp.entry) {
              const entry    = resp.entry;
              const filename = resolveSocialFilename(entry, pageUrl);
              resolve(relayToBridge(entry.cdnUrl, 'stream_hls', filename));
              return;
            }
            // Priority 4: page URL -> yt-dlp
            const url4     = postUrl || pageUrl;
            const filename = resolveFilename(url4, document.title);
            resolve(relayToBridge(url4, 'stream_hls', filename));
          }
        );
      });
    }

    // Non-social: check this specific video's own src first (handles pages
    // with multiple <video> elements — tab-level m3u8 store is shared and
    // would otherwise return the same URL for every Capture button).
    const own = detectStream(videoEl);
    if (own.url) {
      const filename = resolveFilename(own.url, document.title);
      return relayToBridge(own.url, 'stream_hls', filename);
    }
    // No direct src (blob-backed player) — fall back to tab-level m3u8 store.
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ action: 'getM3u8' }, (resp) => {
        if (!chrome.runtime.lastError && resp && resp.url) {
          const filename = resolveFilename(resp.url, document.title);
          resolve(relayToBridge(resp.url, 'stream_hls', filename));
          return;
        }
        const filename = resolveFilename(pageUrl, document.title);
        resolve(relayToBridge(pageUrl, 'stream_hls', filename));
      });
    });
  }

  // What the Download button will hand LDM for this video: the same routing
  // as captureVideo, reduced to a label for the overlay's tag. PAGE means no
  // stream was found and LDM will resolve the page link itself (yt-dlp).
  function kindFromUrl(url) {
    var path = '';
    try { path = new URL(url, window.location.href).pathname.toLowerCase(); } catch (e) { path = String(url).toLowerCase(); }
    if (path.indexOf('.m3u8') !== -1) return 'HLS';
    if (path.indexOf('.mpd')  !== -1) return 'DASH';
    var m = path.match(/\.(mp4|webm|mkv|mov|m4v|flv|ts)$/);
    return m ? m[1].toUpperCase() : 'VIDEO';
  }

  function streamKind(video, cb) {
    var pageUrl = normalizeStreamUrl(window.location.href);
    if (isCFProtected(pageUrl) || isFacebookVideoPage(pageUrl)) return cb('PAGE');

    function ask(msg, pick) {
      try {
        chrome.runtime.sendMessage(msg, function(resp) {
          if (chrome.runtime.lastError) return cb('PAGE');
          cb(pick(resp));
        });
      } catch (e) { cb('PAGE'); }   // extension reloaded under the page
    }

    if (isSocialDomain(pageUrl)) {
      if (video._ldmCdnEntry) return cb(kindFromUrl(video._ldmCdnEntry.cdnUrl));
      var postUrl = extractPostUrl(video);
      if (postUrl && postUrl !== pageUrl) return cb('PAGE');
      var videoId = getFbVideoId(pageUrl) || getTwitterStatusId(pageUrl);
      return ask({ action: 'getSocialVideo', videoId: videoId }, function(resp) {
        return resp && resp.entry ? kindFromUrl(resp.entry.cdnUrl) : 'PAGE';
      });
    }

    var own = detectStream(video);
    if (own.url) return cb(own.isHLS ? 'HLS' : kindFromUrl(own.url));
    ask({ action: 'getM3u8' }, function(resp) {
      return resp && resp.url ? kindFromUrl(resp.url) : 'PAGE';
    });
  }

  // Generate meaningful social media filenames
  function resolveSocialFilename(entry, pageUrl) {
    try {
      var host = new URL(pageUrl).hostname;
      var ts   = new Date().toISOString().slice(0,19).replace(/[:T]/g,'-');
      if (host.includes('twitter.com') || host.includes('x.com')) {
        var sid = getTwitterStatusId(pageUrl);
        return sid ? 'twitter_' + sid + '.mp4' : 'twitter_' + ts + '.mp4';
      }
      if (host.includes('tiktok.com')) {
        var m = pageUrl.match(/\/video\/(\d+)/);
        return m ? 'tiktok_' + m[1] + '.mp4' : 'tiktok_' + ts + '.mp4';
      }
      if (entry.videoId) {
        if (host.includes('instagram')) return 'instagram_' + entry.videoId + '.mp4';
        if (host.includes('facebook') || host.includes('fb.watch')) return 'facebook_' + entry.videoId + '.mp4';
      }
      return 'social_video_' + ts + '.mp4';
    } catch(e) {
      return 'social_video.mp4';
    }
  }

  // ── Message listener (for popup grab/unlock actions) ──────────────────────
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'unlock') {
      window.addEventListener('contextmenu', e => e.stopPropagation(), true);
      sendResponse({ status: 'unlocked' });
    } else if (request.action === 'grab') {
      sendResponse(detectStream());
    } else if (request.action === 'storeCdnEntry' && request.entry) {
      // Background intercepted a social CDN URL -- assign to playing video
      var playing = null;
      document.querySelectorAll('video').forEach(function(v) {
        if (!v.paused && !v.ended) playing = v;
      });
      var target = playing || window._ldmLastHoveredVideo;
      if (target) {
        target._ldmCdnEntry = request.entry;
        if (target._ldmRefreshKind) target._ldmRefreshKind();
      }
      sendResponse({ ok: true });
    }
    return true;
  });

  // Overlay icons, drawn rather than emoji so they look the same everywhere.
  var LDM_SVG = '<svg width="13" height="13" viewBox="0 0 16 16" style="flex:none" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" ';
  var LDM_ICON_DL   = LDM_SVG + 'stroke-width="1.8" color="#38bdf8"><path d="M8 2v8m0 0L4.5 6.5M8 10l3.5-3.5M3 13.5h10"/></svg>';
  var LDM_ICON_SPIN = LDM_SVG + 'stroke-width="1.8"><g><path d="M8 2a6 6 0 1 1-6 6"/><animateTransform attributeName="transform" type="rotate" from="0 8 8" to="360 8 8" dur="1s" repeatCount="indefinite"/></g></svg>';
  var LDM_ICON_OK   = LDM_SVG + 'stroke-width="2"><path d="M3 8.5l3 3 7-7"/></svg>';
  var LDM_ICON_FAIL = LDM_SVG + 'stroke-width="2"><path d="M4 4l8 8M12 4l-8 8"/></svg>';

  // ── Floating overlay ──────────────────────────────────────────────────────
  function createOverlay(video) {
    if (video.hasAttribute('data-ldm-overlay')) return;
    if (video.hasAttribute('data-ldm-dismissed')) return;

    // Suppress overlay on story pages, Facebook dedicated reel pages etc.
    if (isSuppressedPage(window.location.href)) return;

    // YouTube: only show on /watch and /shorts, not homepage/browse/search
    if (isYouTubeNonVideo()) return;

    // Suppress on videos too small to be meaningful (ads, thumbnails)
    const r0 = video.getBoundingClientRect();
    if (r0.width < 120 || r0.height < 80) return;
    // Suppress tiny portrait autoplay story card previews
    if (r0.height > r0.width && video.autoplay && !video.hasAttribute('controls') && r0.width < 160) return;

    video.setAttribute('data-ldm-overlay', '1');
    const isYT = isYouTubePage();
    // YouTube keeps its original look. Everywhere else the left tag names the
    // stream LDM will be sent (see streamKind), so it's clear before clicking
    // whether a real stream was found or LDM will fall back to the page link.
    const baseBg    = '#0f172a';
    const accent    = isYT ? '#dc2626' : '#e0f2fe';
    const hoverBg   = isYT ? 'rgba(220,38,38,0.25)' : '#12334a';
    const label     = isYT ? '&#9654; YouTube'   : LDM_ICON_DL + 'Download';
    const sendingTx = isYT ? '&#8987; Sending...' : LDM_ICON_SPIN + 'Sending';
    const sentTx    = isYT ? '&#10003; Sent!'     : LDM_ICON_OK + 'Sent to LDM';
    const failedTx  = isYT ? '&#10007; Failed'    : LDM_ICON_FAIL + 'Failed';

    // ── Wrapper ───────────────────────────────────────────────────────────────
    const wrapper = document.createElement('div');
    Object.assign(wrapper.style, {
      position:      'absolute',
      zIndex:        '2147483647',
      display:       'flex',
      alignItems:    'stretch',
      pointerEvents: 'all',
      userSelect:    'none',
      touchAction:   'none',
      borderRadius:  isYT ? '5px' : '6px',
      overflow:      'hidden',
      background:    baseBg,
      border:        isYT ? '1px solid rgba(255,255,255,0.1)' : '1px solid rgba(56,189,248,0.35)',
      boxShadow:     isYT ? '0 2px 10px rgba(0,0,0,0.6)' : '0 2px 12px rgba(0,0,0,0.6)',
    });

    // ── Left tag: "LDM" on YouTube, stream type + LDM elsewhere ───────────────
    // It is also the drag handle, hence the grab cursor.
    const badge = document.createElement('div');
    let kindLbl = null;
    if (isYT) {
      badge.innerHTML = 'LDM';
      Object.assign(badge.style, {
        background:  baseBg,
        color:       '#475569',
        fontFamily:  'sans-serif',
        fontSize:    '9px',
        fontWeight:  '700',
        padding:     '0 7px',
        letterSpacing: '0.1em',
        display:     'flex',
        alignItems:  'center',
        borderRight: '1px solid rgba(255,255,255,0.06)',
        cursor:      'grab',
      });
    } else {
      kindLbl = document.createElement('div');
      const brand = document.createElement('div');
      brand.textContent = 'LDM';
      Object.assign(kindLbl.style, {
        font: '700 10px/1.1 ui-monospace, monospace', color: '#7dd3fc', letterSpacing: '0.04em',
      });
      Object.assign(brand.style, {
        font: '500 8.5px/1.2 ui-monospace, monospace', color: '#5f89a3',
      });
      badge.appendChild(kindLbl);
      badge.appendChild(brand);
      Object.assign(badge.style, {
        background:     '#0b2536',
        display:        'flex',
        flexDirection:  'column',
        justifyContent: 'center',
        padding:        '0 9px',
        borderRight:    '1px solid rgba(56,189,248,0.25)',
        cursor:         'grab',
      });
    }

    // ── Main button ───────────────────────────────────────────────────────────
    const btn = document.createElement('div');
    btn.innerHTML = label;
    Object.assign(btn.style, {
      background:  baseBg,
      color:       accent,
      fontFamily:  'sans-serif',
      fontSize:    '12px',
      fontWeight:  '700',
      padding:     '6px 12px',
      cursor:      'pointer',
      lineHeight:  '1.4',
      display:     'flex',
      alignItems:  'center',
      gap:         isYT ? '5px' : '6px',
      borderRight: '1px solid rgba(255,255,255,0.06)',
    });
    btn.addEventListener('mouseenter', () => { btn.style.background = hoverBg; });
    btn.addEventListener('mouseleave', () => { btn.style.background = baseBg; });
    btn.addEventListener('click', e => {
      e.stopPropagation(); e.preventDefault();
      btn.innerHTML = sendingTx;
      btn.style.opacity = '0.7';
      captureVideo(video)
        .then(() => {
          btn.innerHTML = sentTx;
          btn.style.color = '#22c55e';
          btn.style.opacity = '1';
          // Retire it like ×: removeOverlay alone clears data-ldm-overlay, and
          // the next DOM mutation would attach a fresh button to this video.
          video.setAttribute('data-ldm-dismissed', '1');
          setTimeout(() => removeOverlay(video), 1500);
        })
        .catch(() => {
          btn.innerHTML = failedTx;
          btn.style.color = '#ef4444';
          btn.style.opacity = '1';
          setTimeout(() => {
            btn.innerHTML = label;
            btn.style.color = accent;
            btn.style.opacity = '1';
          }, 2000);
        });
    });

    // ── Dismiss button ────────────────────────────────────────────────────────
    const closeBtn = document.createElement('div');
    closeBtn.innerHTML = '&#215;';
    Object.assign(closeBtn.style, {
      background:  baseBg,
      color:       '#475569',
      fontFamily:  'sans-serif',
      fontSize:    '13px',
      fontWeight:  '700',
      padding:     '4px 8px',
      cursor:      'pointer',
      display:     'flex',
      alignItems:  'center',
    });
    closeBtn.addEventListener('mouseenter', () => {
      closeBtn.style.background = 'rgba(239,68,68,0.2)';
      closeBtn.style.color = '#ef4444';
    });
    closeBtn.addEventListener('mouseleave', () => {
      closeBtn.style.background = baseBg;
      closeBtn.style.color = '#475569';
    });
    closeBtn.addEventListener('click', e => {
      e.stopPropagation(); e.preventDefault();
      video.setAttribute('data-ldm-dismissed', '1');
      removeOverlay(video);
    });

    wrapper.appendChild(badge);
    wrapper.appendChild(btn);
    wrapper.appendChild(closeBtn);
    makeDraggable(video, wrapper, badge);

    if (kindLbl) {
      // Streams are often only sniffed once playback starts, so the tag is
      // re-checked on play and whenever the pointer comes to the button.
      const refreshKind = () => {
        if (video._ldmBtn !== wrapper) return;
        streamKind(video, k => { kindLbl.textContent = k; positionOverlay(video, wrapper); });
      };
      kindLbl.textContent = '…';
      video._ldmRefreshKind = refreshKind;
      wrapper.addEventListener('pointerenter', refreshKind);
      if (!video._ldmKindTracked) {
        video._ldmKindTracked = true;
        ['loadedmetadata', 'playing'].forEach(function(t) {
          video.addEventListener(t, function() {
            if (video._ldmRefreshKind) video._ldmRefreshKind();
          }, { passive: true });
        });
      }
    }

    // Isolate from page CSS (e.g. bunkr rules that override flex-row layout).
    var host = document.createElement('div');
    host.attachShadow({ mode: 'open' }).appendChild(wrapper);
    document.body.appendChild(host);

    positionOverlay(video, wrapper);
    video._ldmBtn  = wrapper;
    video._ldmHost = host;
    if (video._ldmRefreshKind) video._ldmRefreshKind();
    _ldmActiveOverlays.push({ host: host, video: video });
  }

  // IDM-style: the overlay can be dragged off whatever part of the player it
  // covers (seek bar, captions, the site's own buttons). Any part of it is a
  // handle; a press only turns into a drag past a few pixels, so ordinary
  // clicks on Capture / × behave exactly as before.
  function makeDraggable(video, wrapper, handle) {
    var DRAG_SLOP = 4;
    var start = null;
    var dragging = false;
    var suppressClick = false;

    wrapper.addEventListener('pointerdown', function(e) {
      if (e.button !== 0) return;
      // Players toggle play/pause on press; the overlay isn't part of them.
      e.stopPropagation();
      start = {
        id: e.pointerId, x: e.clientX, y: e.clientY,
        left: parseFloat(wrapper.style.left) || 0,
        top:  parseFloat(wrapper.style.top)  || 0,
      };
      dragging = false;
      // Follow the press on window, not the wrapper: the overlay is ~30px
      // tall, so a quick flick leaves it before the slop is crossed and the
      // wrapper would never see the moves that start the drag — or the
      // release, leaving a press stuck open.
      window.addEventListener('pointermove', onMove, true);
      window.addEventListener('pointerup', endDrag, true);
      window.addEventListener('pointercancel', endDrag, true);
    });
    wrapper.addEventListener('mousedown', function(e) { e.stopPropagation(); });

    function onMove(e) {
      if (!start || e.pointerId !== start.id) return;
      var dx = e.clientX - start.x, dy = e.clientY - start.y;
      if (!dragging) {
        if (Math.abs(dx) < DRAG_SLOP && Math.abs(dy) < DRAG_SLOP) return;
        dragging = true;
        // Capture only once it's really a drag: capturing on press retargets
        // the click to the wrapper, which would swallow plain button clicks.
        try { wrapper.setPointerCapture(e.pointerId); } catch (_) {}
        handle.style.cursor = 'grabbing';
      }
      e.preventDefault();
      // Keep it on screen so it can't be dropped somewhere unreachable.
      var sx = window.scrollX || window.pageXOffset || 0;
      var sy = window.scrollY || window.pageYOffset || 0;
      var vw = document.documentElement.clientWidth  || window.innerWidth;
      var vh = document.documentElement.clientHeight || window.innerHeight;
      var left = Math.min(Math.max(start.left + dx, sx), sx + vw - wrapper.offsetWidth);
      var top  = Math.min(Math.max(start.top  + dy, sy), sy + vh - wrapper.offsetHeight);
      wrapper.style.left = left + 'px';
      wrapper.style.top  = top  + 'px';
    }

    function endDrag(e) {
      if (!start || e.pointerId !== start.id) return;
      window.removeEventListener('pointermove', onMove, true);
      window.removeEventListener('pointerup', endDrag, true);
      window.removeEventListener('pointercancel', endDrag, true);
      if (dragging) {
        try { wrapper.releasePointerCapture(e.pointerId); } catch (_) {}
        handle.style.cursor = 'grab';
        // Remember the spot relative to the video, so the reposition that
        // runs when it scrolls back into view keeps the user's placement.
        var r  = video.getBoundingClientRect();
        var sx = window.scrollX || window.pageXOffset || 0;
        var sy = window.scrollY || window.pageYOffset || 0;
        video._ldmDragOffset = {
          dx: (parseFloat(wrapper.style.left) || 0) - (r.left + sx),
          dy: (parseFloat(wrapper.style.top)  || 0) - (r.top  + sy),
        };
        suppressClick = e.type === 'pointerup';
        // Not every drag ends in a click (released off the overlay), so don't
        // let a stale flag eat the next real one.
        setTimeout(function() { suppressClick = false; }, 0);
      }
      start = null;
      dragging = false;
    }

    // The click that ends a drag must not also fire Capture or ×.
    wrapper.addEventListener('click', function(e) {
      if (!suppressClick) return;
      suppressClick = false;
      e.stopPropagation(); e.preventDefault();
    }, true);
  }

  function positionOverlay(video, wrapper) {
    const r = video.getBoundingClientRect();
    if (r.width < 100 || r.height < 60) { wrapper.style.display = 'none'; return; }
    wrapper.style.display = 'flex';
    const btnH   = wrapper.offsetHeight || 28;
    const scrollX = window.scrollX || window.pageXOffset || 0;
    const scrollY = window.scrollY || window.pageYOffset || 0;
    if (video._ldmDragOffset) {
      wrapper.style.left = `${r.left + scrollX + video._ldmDragOffset.dx}px`;
      wrapper.style.top  = `${r.top  + scrollY + video._ldmDragOffset.dy}px`;
      return;
    }
    if (r.top > btnH + 4) {
      wrapper.style.top  = `${r.top + scrollY - btnH - 4}px`;
    } else {
      wrapper.style.top  = `${r.top + scrollY + 6}px`;
    }
    wrapper.style.left = `${r.right + scrollX - 160}px`;
  }

  // Active overlay registry — used to purge hosts orphaned by SPA re-renders
  var _ldmActiveOverlays = [];

  function _cleanOrphanedOverlays() {
    _ldmActiveOverlays = _ldmActiveOverlays.filter(function(item) {
      if (!item.video.isConnected) {
        try { item.host.remove(); } catch(e) {}
        return false;
      }
      return true;
    });
  }

  function removeOverlay(video) {
    if (video._ldmHost) {
      video._ldmHost.remove();
      _ldmActiveOverlays = _ldmActiveOverlays.filter(function(item) { return item.video !== video; });
      delete video._ldmHost;
      delete video._ldmBtn;
      delete video._ldmRefreshKind;
    }
    if (!video.hasAttribute('data-ldm-dismissed')) {
      video.removeAttribute('data-ldm-overlay');
    }
  }

  // Track play events — associate video element with CDN entry at play time
  function fetchAndStoreCdnEntry(video) {
    chrome.runtime.sendMessage({ action: 'getSocialVideo' }, function(resp) {
      if (!chrome.runtime.lastError && resp && resp.entry) {
        video._ldmCdnEntry = resp.entry;
        if (video._ldmRefreshKind) video._ldmRefreshKind();
      }
    });
  }
  function attachPlayTracker(video) {
    if (video._ldmPlayTracked) return;
    video._ldmPlayTracked = true;
    // Already autoplaying — fetch CDN entry immediately
    if (!video.paused && !video.ended) {
      fetchAndStoreCdnEntry(video);
    }
    // Also track future play/playing events
    video.addEventListener('play',    function() { fetchAndStoreCdnEntry(video); }, { passive: true });
    video.addEventListener('playing', function() { fetchAndStoreCdnEntry(video); }, { passive: true });
  }

  // IntersectionObserver: with position:absolute the button scrolls with its
  // video naturally. We only need to CREATE on first entry and REPOSITION on
  // re-entry (layout shifts from lazy-load). On Facebook reel pages we ALSO
  // hide the button when its video drops out of view — reels are full-viewport
  // so stale buttons from prior reels otherwise stack on top of the active one.
  const videoVisibilityObserver = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
      const v = entry.target;
      if (entry.isIntersecting) {
        if (!v.hasAttribute('data-ldm-dismissed')) {
          setTimeout(function() {
            if (v.hasAttribute('data-ldm-overlay') && v._ldmBtn) {
              positionOverlay(v, v._ldmBtn);
              if (v._ldmHost) v._ldmHost.style.display = '';
            } else if (!v.hasAttribute('data-ldm-overlay')) {
              createOverlay(v);
              attachPlayTracker(v);
            }
          }, 200);
        }
      } else if (isFacebookVideoPage(window.location.href) && v._ldmHost) {
        v._ldmHost.style.display = 'none';
      }
    });
  }, { threshold: 0.8 });

  function attachToVideos() {
    if (isSuppressedPage(window.location.href)) return;
    _cleanOrphanedOverlays();
    document.querySelectorAll('video').forEach(function(v) {
      createOverlay(v);
      attachPlayTracker(v);
      if (!v._ldmVisibilityTracked) {
        v._ldmVisibilityTracked = true;
        videoVisibilityObserver.observe(v);
      }
      if (!v._ldmHoverTracked) {
        v._ldmHoverTracked = true;
        v.addEventListener('mouseenter', function() {
          window._ldmLastHoveredVideo = v;
        }, { passive: true });
      }
    });
  }

  // Debounce MutationObserver so React/SPA DOM bursts collapse into one call
  var _ldmAttachTimer = null;
  function _debouncedAttach() {
    clearTimeout(_ldmAttachTimer);
    _ldmAttachTimer = setTimeout(attachToVideos, 120);
  }

  new MutationObserver(_debouncedAttach).observe(
    document.body || document.documentElement,
    { childList: true, subtree: true }
  );

  // SPA URL change detector. Facebook Reels swaps videos via pushState; on each
  // reel the URL updates to /reel/ID. Without this poll the FIRST reel can miss
  // its overlay (attachToVideos may have run while URL was still the suppressed
  // feed page), and stale overlays from prior reels stack on the active one.
  // Polling location.href is simpler than patching history from a content
  // script's isolated world (page-side references survive the patch).
  var _ldmLastUrl = window.location.href;
  setInterval(function() {
    if (window.location.href === _ldmLastUrl) return;
    _ldmLastUrl = window.location.href;
    if (window.location.hostname.includes('facebook.com')) {
      _ldmActiveOverlays.forEach(function(item) {
        try { item.host.remove(); } catch(e) {}
        try {
          item.video.removeAttribute('data-ldm-overlay');
          delete item.video._ldmHost;
          delete item.video._ldmBtn;
        } catch(e) {}
      });
      _ldmActiveOverlays = [];
    }
    setTimeout(attachToVideos, 300);
  }, 250);

  // Facebook reel backstop. The IntersectionObserver only fires when the
  // video crosses the 0.8 visibility threshold — if FB mounts the first reel's
  // <video> with size 0 and lays it out without re-crossing the threshold
  // (or never crosses it because of CSS transforms), createOverlay is never
  // re-attempted after its initial size-check bail-out. Poll once a second for
  // visible videos missing an overlay and attach one.
  setInterval(function() {
    if (!isFacebookVideoPage(window.location.href)) return;
    document.querySelectorAll('video').forEach(function(v) {
      if (v.hasAttribute('data-ldm-overlay')) return;
      if (v.hasAttribute('data-ldm-dismissed')) return;
      var r = v.getBoundingClientRect();
      if (r.width >= 120 && r.height >= 80) {
        createOverlay(v);
        attachPlayTracker(v);
      }
    });
  }, 1000);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attachToVideos);
  } else {
    attachToVideos();
  }

})();
