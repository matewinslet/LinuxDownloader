// popup.js - Linux Download Manager

const api = (typeof browser !== 'undefined') ? browser : chrome;

document.getElementById('version').textContent = 'v' + api.runtime.getManifest().version;

// ── Power button: Active / Paused ──────────────────────────────────────────
// interceptEnabled is read by background.js: when false, Firefox keeps every
// download. While active, also ping the app so a closed LDM shows up here.
const activeBtn = document.getElementById('activeBtn');
let activeOn = true;

function pingLdm() {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 1500);
  return fetch('http://127.0.0.1:9999/ping', { signal: ctl.signal })
    .then(r => r.text()).then(body => body.trim() === 'LDM-OK')
    .catch(() => false)
    .finally(() => clearTimeout(t));
}

function renderActive(ldmUp) {
  const title = document.getElementById('activeTitle');
  const sub   = document.getElementById('activeSub');
  if (!activeOn) {
    document.body.dataset.state = 'off';
    title.textContent = 'Paused';
    sub.textContent   = 'Firefox handles downloads';
  } else if (ldmUp === false) {
    document.body.dataset.state = 'warn';
    title.textContent = 'LDM not running';
    sub.textContent   = 'Open LDM to receive downloads';
  } else {
    document.body.dataset.state = 'on';
    title.textContent = 'Active';
    sub.textContent   = ldmUp ? 'Forwarding downloads to LDM' : 'Checking LDM…';
  }
}

function refreshActive() {
  renderActive(null);
  if (activeOn) pingLdm().then(up => { if (activeOn) renderActive(up); });
}

api.storage.local.get('interceptEnabled').then(r => {
  activeOn = r.interceptEnabled !== false;
  refreshActive();
});
activeBtn.addEventListener('click', () => {
  activeOn = !activeOn;
  api.storage.local.set({ interceptEnabled: activeOn });
  refreshActive();
});

// ── Video buttons (floating LDM buttons on videos) ─────────────────────────
// content.js listens for videoButtons changes and hides/shows them live.
const videoBtn = document.getElementById('videoBtnsBtn');
let videoBtnsOn = true;

function renderVideoBtns() {
  videoBtn.classList.toggle('is-on', videoBtnsOn);
  document.getElementById('videoBtnsSub').textContent = videoBtnsOn ? 'Shown on videos' : 'Hidden on all sites';
  document.getElementById('videoBtnsEnd').textContent = videoBtnsOn ? 'ON' : 'OFF';
}

api.storage.local.get('videoButtons').then(r => {
  videoBtnsOn = r.videoButtons !== false;
  renderVideoBtns();
});
videoBtn.addEventListener('click', () => {
  videoBtnsOn = !videoBtnsOn;
  api.storage.local.set({ videoButtons: videoBtnsOn });
  renderVideoBtns();
});

// ── Unlock right-click ─────────────────────────────────────────────────────
const unlockBtn = document.getElementById('unlockBtn');

function showUnlocked() {
  unlockBtn.classList.remove('fail');
  unlockBtn.classList.add('is-on');
  document.getElementById('lockIcon').setAttribute('href', '#lockOpen');
  unlockBtn.querySelector('.btn-title').textContent = 'Right-click unlocked';
  unlockBtn.querySelector('.btn-sub').textContent = 'Until this page reloads';
  document.getElementById('unlockEnd').textContent = 'OPEN';
}
unlockBtn.addEventListener('click', async () => {
  try {
    const [tab] = await api.tabs.query({ active: true, currentWindow: true });
    // All frames get it (embedded players etc.); success = at least one answered.
    const resp = await api.tabs.sendMessage(tab.id, { action: 'unlock' });
    if (!resp) throw new Error('no content script');
    showUnlocked();
  } catch(e) {
    unlockBtn.classList.add('fail');
    unlockBtn.querySelector('.btn-title').textContent = "Can't unlock here";
    unlockBtn.querySelector('.btn-sub').textContent = 'Firefox pages are off-limits';
    document.getElementById('unlockEnd').textContent = 'N/A';
  }
});
// The unlock lives in the page, so ask the top frame whether it's still on.
(async () => {
  try {
    const [tab] = await api.tabs.query({ active: true, currentWindow: true });
    const resp = await api.tabs.sendMessage(tab.id, { action: 'unlockStatus' }, { frameId: 0 });
    if (resp && resp.unlocked) showUnlocked();
  } catch(e) {}  // no content script here (about:, addons page) -> leave as locked
})();
