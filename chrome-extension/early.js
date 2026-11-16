// early.js - Ferospark LDM
// Runs at document_start, before any of the page's own scripts.
//
// Some sites (pop-up ad scripts, mostly) listen for clicks on the window in the
// capture phase and stop them there, so a click on the floating Download button
// never reaches the button. A listener added before the page's scripts runs
// first, so this one sees clicks on the LDM button before the page can swallow
// them, runs the button's action itself and keeps the click from the page
// (which also means no ad pop-up from clicking Download).
//
// content.js marks the clickable parts of the overlay with _ldmOnClick, and the
// overlay itself with _ldmSuppressing (true right after a drag, so letting go
// of a dragged button doesn't also press it).
(function () {
  if (window.__ldmEarlyClick) return;
  window.__ldmEarlyClick = true;

  window.addEventListener('click', function (e) {
    var path = e.composedPath ? e.composedPath() : [];
    var action = null, suppressing = null;
    for (var i = 0; i < path.length; i++) {
      var el = path[i];
      if (!el || el === window || el === document) break;
      if (!action && typeof el._ldmOnClick === 'function') action = el._ldmOnClick;
      if (!suppressing && typeof el._ldmSuppressing === 'function') suppressing = el._ldmSuppressing;
      if (el.hasAttribute && el.hasAttribute('data-ldm-host')) break;
    }
    if (!action && !suppressing) return;   // not our button
    e.stopImmediatePropagation();
    e.preventDefault();
    if (suppressing && suppressing()) return;
    if (action) action(e);
  }, true);
})();
