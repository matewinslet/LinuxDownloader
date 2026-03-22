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
  function detectStream() {
    const video = document.querySelector('video');
    if (!video) return { url: null, isHLS: false };
    let url = null, isHLS = false;
    if (video.src && !video.src.startsWith('blob:')) {
      url = video.src; isHLS = url.includes('.m3u8');
    } else {
      const source = document.querySelector('video source');
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

  // Overlay suppression rules for social platforms
  // Returns true if overlay should be suppressed on this page
  function isSuppressedPage(url) {
    if (isStoryUrl(url)) return true;
    // facebook.com/reels/ is a feed page (login redirect) -- not downloadable
    // facebook.com/reel/ID is a specific reel -- yt-dlp handles it, show overlay
    if (/facebook\.com\/reels\/?$/.test(url)) return true;
    if (/facebook\.com\/reels\/\?/.test(url)) return true;
    return false;
  }

  // Social domains — use CDN store + yt-dlp fallback, not direct page URL
  var SOCIAL_DOMAINS = ['facebook.com', 'fb.watch', 'twitter.com', 'x.com', 'instagram.com'];
  function isSocialDomain(url) {
    try { var h = new URL(url).hostname; return SOCIAL_DOMAINS.some(function(d) { return h.includes(d); }); }
    catch(e) { return false; }
  }

  // CF domains (luluvdo etc.) — always page URL → yt-dlp
  var CF_DOMAINS = ['luluvdo.com', 'lulustream.com', 'doodstream.com', 'dood.watch', 'dood.to'];
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
      patterns = [/\/(?:reel|watch|videos)\//, /[?&]v=\d+/];
    } else if (host.includes('twitter.com') || host.includes('x.com')) {
      patterns = [/\/status\/\d+/];
    }
    if (!patterns.length) return null;
    var el = videoEl.parentElement;
    var depth = 0;
    while (el && depth < 20) {
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

    // Social domains (Facebook, Instagram, Twitter)
    if (isSocialDomain(pageUrl)) {
      return new Promise((resolve, reject) => {
        // Priority 1: CDN entry on THIS video element (set at play time)
        // Most accurate for feed pages with multiple videos
        if (videoEl && videoEl._ldmCdnEntry) {
          const entry    = videoEl._ldmCdnEntry;
          const type     = entry.isTwimg ? 'stream_hls' : 'video_stream';
          const filename = resolveSocialFilename(entry, pageUrl);
          resolve(relayToBridge(entry.cdnUrl, type, filename));
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
              const type     = entry.isTwimg ? 'stream_hls' : 'video_stream';
              const filename = resolveSocialFilename(entry, pageUrl);
              resolve(relayToBridge(entry.cdnUrl, type, filename));
              return;
            }
            // Priority 4: page URL -> yt-dlp
            // StreamDialog handles the Facebook feed hint message.
            const url4     = postUrl || pageUrl;
            const filename = resolveFilename(url4, document.title);
            resolve(relayToBridge(url4, 'stream_hls', filename));
          }
        );
      });
    }

    // Non-social: check m3u8 store (vidara, vidnest etc.)
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ action: 'getM3u8' }, (resp) => {
        if (!chrome.runtime.lastError && resp && resp.url) {
          const filename = resolveFilename(resp.url, document.title);
          resolve(relayToBridge(resp.url, 'stream_hls', filename));
          return;
        }
        const result = detectStream();
        if (result.url) {
          const type     = result.isHLS ? 'stream_hls' : 'video_stream';
          const filename = resolveFilename(result.url, document.title);
          resolve(relayToBridge(result.url, type, filename));
          return;
        }
        const filename = resolveFilename(pageUrl, document.title);
        resolve(relayToBridge(pageUrl, 'stream_hls', filename));
      });
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
      if (playing) {
        playing._ldmCdnEntry = request.entry;
      } else if (window._ldmLastHoveredVideo) {
        window._ldmLastHoveredVideo._ldmCdnEntry = request.entry;
      }
      sendResponse({ ok: true });
    }
    return true;
  });

  // ── Floating overlay ──────────────────────────────────────────────────────
  function createOverlay(video) {
    if (video.hasAttribute('data-ldm-overlay')) return;
    if (video.hasAttribute('data-ldm-dismissed')) return;

    // Suppress overlay on story pages, Facebook dedicated reel pages etc.
    if (isSuppressedPage(window.location.href)) return;

    // Suppress on videos too small to be meaningful (ads, thumbnails)
    const r0 = video.getBoundingClientRect();
    if (r0.width < 120 || r0.height < 80) return;
    // Suppress tiny portrait autoplay story card previews
    if (r0.height > r0.width && video.autoplay && !video.hasAttribute('controls') && r0.width < 160) return;

    video.setAttribute('data-ldm-overlay', '1');
    const isYT    = isYouTubePage();
    const accent  = isYT ? '#dc2626' : '#38bdf8';
    const label   = isYT ? '&#9654; YouTube' : '&#11015;&#65038; Capture';
    const hoverBg = isYT ? 'rgba(220,38,38,0.18)' : 'rgba(56,189,248,0.18)';

    // ── Wrapper ───────────────────────────────────────────────────────────────
    const wrapper = document.createElement('div');
    Object.assign(wrapper.style, {
      position:      'fixed',
      zIndex:        '2147483647',
      display:       'flex',
      alignItems:    'stretch',
      pointerEvents: 'all',
      userSelect:    'none',
      borderRadius:  '5px',
      overflow:      'hidden',
      border:        `1px solid rgba(255,255,255,0.1)`,
      boxShadow:     '0 2px 10px rgba(0,0,0,0.6)',
    });

    // ── LDM badge ─────────────────────────────────────────────────────────────
    const badge = document.createElement('div');
    badge.innerHTML = 'LDM';
    Object.assign(badge.style, {
      background:  '#0f172a',
      color:       '#475569',
      fontFamily:  'sans-serif',
      fontSize:    '9px',
      fontWeight:  '700',
      padding:     '0 7px',
      letterSpacing: '0.1em',
      display:     'flex',
      alignItems:  'center',
      borderRight: '1px solid rgba(255,255,255,0.06)',
    });

    // ── Main button ───────────────────────────────────────────────────────────
    const btn = document.createElement('div');
    btn.innerHTML = label;
    Object.assign(btn.style, {
      background:  '#0f172a',
      color:       accent,
      fontFamily:  'sans-serif',
      fontSize:    '12px',
      fontWeight:  '700',
      padding:     '6px 12px',
      cursor:      'pointer',
      lineHeight:  '1.4',
      display:     'flex',
      alignItems:  'center',
      gap:         '5px',
      borderRight: '1px solid rgba(255,255,255,0.06)',
    });
    btn.addEventListener('mouseenter', () => { btn.style.background = hoverBg.replace('rgba','rgba').replace('0.18','0.25'); });
    btn.addEventListener('mouseleave', () => { btn.style.background = '#0f172a'; });
    btn.addEventListener('click', e => {
      e.stopPropagation(); e.preventDefault();
      btn.innerHTML = '&#8987; Sending...';
      btn.style.opacity = '0.7';
      captureVideo(video)
        .then(() => {
          btn.innerHTML = '&#10003; Sent!';
          btn.style.color = '#22c55e';
          btn.style.opacity = '1';
          setTimeout(() => removeOverlay(video), 1500);
        })
        .catch(() => {
          btn.innerHTML = '&#10007; Failed';
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
      background:  '#0f172a',
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
      closeBtn.style.background = '#0f172a';
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
    document.body.appendChild(wrapper);

    positionOverlay(video, wrapper);
    const reposition = () => positionOverlay(video, wrapper);
    window.addEventListener('scroll', reposition, { passive: true });
    window.addEventListener('resize', reposition, { passive: true });
    const ro = new ResizeObserver(() => positionOverlay(video, wrapper));
    ro.observe(video);
    wrapper._cleanup = () => {
      ro.disconnect();
      window.removeEventListener('scroll', reposition);
      window.removeEventListener('resize', reposition);
    };
    video._ldmBtn = wrapper;
  }

  function positionOverlay(video, wrapper) {
    const r = video.getBoundingClientRect();
    if (r.width < 100 || r.height < 60) { wrapper.style.display = 'none'; return; }
    wrapper.style.display = 'flex';
    const btnH = wrapper.offsetHeight || 28;
    // IDM style: sit just ABOVE the video top-right corner
    // If too close to top of viewport, place inside instead
    if (r.top > btnH + 4) {
      wrapper.style.top  = `${r.top - btnH - 4}px`;
    } else {
      wrapper.style.top  = `${r.top + 6}px`;
    }
    wrapper.style.left = `${r.right - 160}px`;
  }

  function removeOverlay(video) {
    if (video._ldmBtn) {
      if (video._ldmBtn._cleanup) video._ldmBtn._cleanup();
      video._ldmBtn.remove();
      delete video._ldmBtn;
    }
    // Only remove overlay attribute if not permanently dismissed —
    // dismissed videos should never get the overlay back until page reload.
    if (!video.hasAttribute('data-ldm-dismissed')) {
      video.removeAttribute('data-ldm-overlay');
    }
  }

  // Track play events — associate video element with CDN entry at play time
  function fetchAndStoreCdnEntry(video) {
    chrome.runtime.sendMessage({ action: 'getSocialVideo' }, function(resp) {
      if (!chrome.runtime.lastError && resp && resp.entry) {
        video._ldmCdnEntry = resp.entry;
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

  function attachToVideos() {
    if (isSuppressedPage(window.location.href)) return;
    document.querySelectorAll('video').forEach(function(v) {
      createOverlay(v);
      attachPlayTracker(v);
      if (!v._ldmHoverTracked) {
        v._ldmHoverTracked = true;
        v.addEventListener('mouseenter', function() {
          window._ldmLastHoveredVideo = v;
        }, { passive: true });
      }
    });
  }

  new MutationObserver(attachToVideos).observe(
    document.body || document.documentElement,
    { childList: true, subtree: true }
  );

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attachToVideos);
  } else {
    attachToVideos();
  }

})();
