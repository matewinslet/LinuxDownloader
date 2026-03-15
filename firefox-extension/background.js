// background.js - Version 2.4.1

const handledUrls = new Set();
let interceptEnabled = true;

browser.storage.local.get("interceptEnabled").then(function(result) {
  interceptEnabled = result.interceptEnabled !== false;
});

browser.storage.onChanged.addListener(function(changes) {
  if (changes.interceptEnabled !== undefined) {
    interceptEnabled = changes.interceptEnabled.newValue;
  }
});

// Context menu for regular download links
browser.contextMenus.create({
  id: "send-to-linux-dm",
  title: "Download with Linux Manager",
  contexts: ["link"]
});

// Context menu for YouTube — shows on all pages, works on YouTube
browser.contextMenus.create({
  id: "capture-youtube",
  title: "Capture YouTube with LDM",
  contexts: ["page", "link"]
});

// Single combined listener for all context menu clicks
browser.contextMenus.onClicked.addListener(function(info) {
  if (info.menuItemId === "send-to-linux-dm") {
    var url = info.linkUrl;
    var filename = url.split("?")[0].split("/").pop() || "download";
    sendToPython(url, filename, "file");
  }
  if (info.menuItemId === "capture-youtube") {
    var url = info.linkUrl || info.pageUrl;
    sendToPython(url, "youtube", "youtube");
  }
});

browser.webRequest.onHeadersReceived.addListener(
  function(details) {
    if (!interceptEnabled) return {};
    var url = details.url;
    var lowerUrl = url.toLowerCase();
    if (
      lowerUrl.includes("googlevideo.com") ||
      lowerUrl.includes("youtube.com") ||
      lowerUrl.includes("youtu.be") ||
      lowerUrl.includes("google.com") ||
      lowerUrl.includes("googleapis.com") ||
      lowerUrl.includes("gstatic.com") ||
      lowerUrl.includes("googleusercontent.com") ||
      lowerUrl.includes("lh3.google") ||
      lowerUrl.includes("lh4.google") ||
      lowerUrl.includes("lh5.google") ||
      lowerUrl.includes("lh6.google")
    ) return {};
    if (lowerUrl.startsWith("blob:") || lowerUrl.startsWith("data:")) return {};
    var allowedTypes = ["main_frame", "sub_frame", "other"];
    if (allowedTypes.indexOf(details.type) === -1) return {};
    var headers = details.responseHeaders || [];
    var contentDisposition = null;
    var contentType = null;
    for (var i = 0; i < headers.length; i++) {
      var name = headers[i].name.toLowerCase();
      if (name === "content-disposition") contentDisposition = headers[i];
      if (name === "content-type") contentType = headers[i];
    }
    var isAttachment = contentDisposition &&
      contentDisposition.value.toLowerCase().includes("attachment");
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
      "video/quicktime"
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
    if (!isAttachment && !isBinaryType) return {};
    if (contentType) {
      var ct = contentType.value.toLowerCase();
      if (ct.startsWith("image/")) return {};
      if (ct.startsWith("text/")) return {};
      if (ct.includes("application/json")) return {};
      if (ct.includes("application/javascript")) return {};
      if (ct.includes("application/xhtml")) return {};
    }
    var imageExts = [".jpg", ".jpeg", ".png", ".gif", ".webp",
                     ".bmp", ".svg", ".avif", ".tiff", ".ico"];
    var urlPath = url.split("?")[0].toLowerCase();
    for (var k = 0; k < imageExts.length; k++) {
      if (urlPath.endsWith(imageExts[k])) return {};
    }
    if (handledUrls.has(url)) {
      handledUrls.delete(url);
      return { cancel: true };
    }
    var filename = "";
    if (contentDisposition) {
      var match = contentDisposition.value.match(/filename[^=]*=\s*["']?([^"'\s;]+)/i);
      if (match) filename = decodeURIComponent(match[1].trim());
    }
    if (!filename) {
      filename = url.split("?")[0].split("/").pop() || "download";
    }
    for (var m = 0; m < imageExts.length; m++) {
      if (filename.toLowerCase().endsWith(imageExts[m])) return {};
    }
    handledUrls.add(url);
    sendToPython(url, filename, "file");
    return { cancel: true };
  },
  { urls: ["<all_urls>"] },
  ["blocking", "responseHeaders"]
);

browser.downloads.onCreated.addListener(function(downloadItem) {
  var url = downloadItem.url || "";
  var lowerUrl = url.toLowerCase();
  if (!lowerUrl.startsWith("blob:") && !lowerUrl.startsWith("data:")) {
    if (!interceptEnabled) return;
    browser.downloads.erase({ id: downloadItem.id });
    return;
  }
  var filename = (downloadItem.filename || "").split(/[\\/]/).pop() || "";
  var imageExts = [".jpg", ".jpeg", ".png", ".gif", ".webp",
                   ".bmp", ".svg", ".avif", ".tiff", ".ico"];
  for (var i = 0; i < imageExts.length; i++) {
    if (filename.toLowerCase().endsWith(imageExts[i])) return;
  }
  var mime = (downloadItem.mime || "").toLowerCase();
  if (mime.startsWith("image/")) return;
  if (mime.startsWith("text/")) return;
  var hasExt = filename.includes(".");
  if (!hasExt && mime === "application/octet-stream") return;
  if (!hasExt && mime === "") return;
  if (!interceptEnabled) return;
  sendToPython(url, filename || "download", "file");
  browser.downloads.erase({ id: downloadItem.id });
});

function sendToPython(url, filename, type) {
  var bridgeUrl = "http://127.0.0.1:9999/?url=" + encodeURIComponent(url) +
    "&filename=" + encodeURIComponent(filename) + "&type=" + type;
  fetch(bridgeUrl).catch(function() {
    console.error("Linux Download Manager is not running.");
  });
}