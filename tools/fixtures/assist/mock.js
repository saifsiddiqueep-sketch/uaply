/* Shared parts of the mock hiring-system forms (tools/test-assist.js). They copy the structure measured on real hosted forms on
   October 21, 2026 (docs/assisted-apply.md): how labels, lists, place boxes and Yes/No buttons are drawn, and where the human check sits.
   Nothing here talks to a network. Every submit, every click on Submit, and any touch of the human check is counted:
   window.__mock = {submits, submitClicks, checkTouched}. A submit shows the system's confirmation page, as the real ones do. */
(function () {
  "use strict";
  var M = window.__mock = { submits: 0, submitClicks: 0, checkTouched: 0 };
  var touch = "ontouchstart" in window;
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-submit]")) M.submitClicks++;
    if (e.target.closest("[data-check]")) M.checkTouched++;
  }, true);
  ["focusin", "mousedown", "touchstart", "keydown"].forEach(function (t) {
    document.addEventListener(t, function (e) { if (e.target.closest && e.target.closest("[data-check]")) M.checkTouched++; }, true);
  });
  window.mockSubmit = function (form, thanks) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      M.submits++;
      try { history.pushState({}, "", location.pathname.replace(/[^/]*$/, "") + "confirmation"); } catch (err) { location.hash = "confirmation"; }   // file:// pages cannot change their path
      document.body.innerHTML = '<main><h1>' + thanks + '</h1><p>We will review it and get back to you.</p></main>';
    });
  };
  /* a React Select list (Greenhouse, and Workable's readonly lists): opens on mousedown on a computer, on touchend on a phone (as the
     real one does), filters as you type, sets a hidden input when an option is clicked. async: options arrive after a wait (place search) */
  window.mockCombo = function (id, label, options, required, async) {
    var wrap = document.createElement("div");
    wrap.className = "field";
    wrap.innerHTML = '<label id="' + id + '-label" for="' + id + '">' + label + (required ? '<span class="req">*</span>' : '') + '</label>' +
      '<div class="select__container"><div class="select__control"><div class="select__value"></div>' +
      '<input id="' + id + '" class="select__input" role="combobox" aria-expanded="false" aria-autocomplete="list" aria-haspopup="true" aria-labelledby="' + id + '-label"' + (required ? ' aria-required="true"' : '') + ' autocomplete="off"></div></div>' +
      '<input type="hidden" name="' + id + '">';
    var ctl = wrap.querySelector(".select__control"), inp = wrap.querySelector("input[role=combobox]"), hid = wrap.querySelector("input[type=hidden]"), val = wrap.querySelector(".select__value");
    var menu = null, timer = 0;
    function close() { if (menu) menu.remove(); menu = null; inp.setAttribute("aria-expanded", "false"); }
    function draw() {
      if (!menu) { menu = document.createElement("div"); menu.className = "select__menu"; menu.setAttribute("role", "listbox"); wrap.querySelector(".select__container").appendChild(menu); }
      var q = inp.value.toLowerCase();
      var list = options.filter(function (o) { return !q || o.toLowerCase().indexOf(q) >= 0; });
      menu.innerHTML = list.length ? list.map(function (o) { return '<div class="select__option" role="option">' + o + '</div>'; }).join("") : '<div class="select__menu-notice--no-options">No options</div>';
      inp.setAttribute("aria-expanded", "true");
    }
    function open() { if (async) { clearTimeout(timer); timer = setTimeout(draw, 400); } else draw(); }
    if (touch) ctl.addEventListener("touchend", open); else ctl.addEventListener("mousedown", open);
    inp.addEventListener("input", function () { if (async) { if (inp.value.length >= 3) open(); } else draw(); });
    inp.addEventListener("keydown", function (e) { if (e.key === "ArrowDown") open(); if (e.key === "Escape") close(); });
    wrap.addEventListener("click", function (e) {
      var o = e.target.closest("[role=option]"); if (!o) return;
      hid.value = o.textContent; val.textContent = o.textContent; inp.value = ""; close();
    });
    return wrap;
  };
})();
