// Section 1: Unlock right-click
document.getElementById('unlockBtn').addEventListener('click', async () => {
  let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { action: "unlock" });
  document.getElementById('unlockBtn').innerHTML = "&#10003; Unlocked!";
  document.getElementById('unlockBtn').style.background = "#8e44ad";
});

// Section 1: Send to LDM
document.getElementById('sendBtn').addEventListener('click', async () => {
  let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { action: "grab" }, (response) => {
    if (response && response.url) {
      const bridgeUrl = `http://127.0.0.1:9999/?url=${encodeURIComponent(response.url)}&filename=captured_video.mp4&type=video_stream`;
      fetch(bridgeUrl).then(() => {
        document.getElementById('sendBtn').innerHTML = "&#10003; Sent to LDM!";
      }).catch(() => {
        document.getElementById('sendBtn').innerText = "Error: App Closed?";
        document.getElementById('sendBtn').style.background = "#c0392b";
      });
    } else {
      document.getElementById('sendBtn').innerText = "No Video Found";
      document.getElementById('sendBtn').style.background = "#c0392b";
    }
  });
});

// Section 2: Capture YouTube
document.getElementById('youtubeBtn').addEventListener('click', async () => {
  let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab.url;
  const lowerUrl = url.toLowerCase();
  const isYoutube = lowerUrl.includes("youtube.com/watch") ||
                    lowerUrl.includes("youtu.be/") ||
                    lowerUrl.includes("youtube.com/shorts");

  if (!isYoutube) {
    document.getElementById('youtubeBtn').innerText = "Not a YouTube page";
    document.getElementById('youtubeBtn').style.background = "#7f8c8d";
    return;
  }

  const bridgeUrl = `http://127.0.0.1:9999/?url=${encodeURIComponent(url)}&filename=youtube&type=youtube`;
  fetch(bridgeUrl).then(() => {
    document.getElementById('youtubeBtn').innerHTML = "&#10003; Sent to LDM!";
  }).catch(() => {
    document.getElementById('youtubeBtn').innerText = "Error: App Closed?";
    document.getElementById('youtubeBtn').style.background = "#c0392b";
  });
});

// Toggle
const toggle = document.getElementById('interceptToggle');
const sub = document.getElementById('toggleSub');

browser.storage.local.get("interceptEnabled").then((result) => {
  const enabled = result.interceptEnabled !== false;
  toggle.checked = enabled;
  sub.textContent = enabled ? "Sending to Linux DM" : "Firefox handles downloads";
});

toggle.addEventListener("change", () => {
  const enabled = toggle.checked;
  browser.storage.local.set({ interceptEnabled: enabled });
  sub.textContent = enabled ? "Sending to Linux DM" : "Firefox handles downloads";
});