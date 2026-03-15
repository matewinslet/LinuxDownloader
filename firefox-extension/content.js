// content.js - Executes inside the web page

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "unlock") {
        // Force the right-click menu to work
        const forceRightClick = (e) => e.stopPropagation();
        window.addEventListener('contextmenu', forceRightClick, true);
        console.log("Linux DM: Right-click protection disabled.");
        sendResponse({status: "unlocked"});
    } 
    else if (request.action === "grab") {
        // Find the video link
        const video = document.querySelector('video');
        let finalUrl = null;

        if (video && video.src && !video.src.startsWith('blob:')) {
            finalUrl = video.src;
        } else {
            const source = document.querySelector('video source');
            if (source && source.src) finalUrl = source.src;
        }
        sendResponse({ url: finalUrl });
    }
    return true; 
});