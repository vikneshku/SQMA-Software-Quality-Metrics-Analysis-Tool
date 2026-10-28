/*
 * ai.js - shared helpers for the AI features.
 *   SQMA_AI.post(url, body)   POST JSON with the CSRF header, returns parsed JSON (never throws)
 *   SQMA_AI.render(el, text)  safe mini-markdown (escape first, then **bold**, "- " bullets, line breaks)
 */
window.SQMA_AI = (function () {
  var CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function render(el, text) {
    var html = esc(text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      .replace(/^[\*\-] (.*)$/gm, '&bull; $1').replace(/\n/g, '<br>');
    el.innerHTML = html;
  }
  async function post(url, body) {
    try {
      var r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF },
                                 body: JSON.stringify(body || {}) });
      return await r.json();
    } catch (e) {
      return { ok: false, message: 'Network problem - check your connection and try again.' };
    }
  }
  return { post: post, render: render };
})();
