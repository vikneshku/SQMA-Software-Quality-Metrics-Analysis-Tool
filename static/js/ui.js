/*
 * ui.js - small helpers shared by the pages:
 *   1. sortable tables       <table class="sortable"> with <th data-sort="text|num">
 *   2. live CVSS badge       <input data-cvss-input> + <span data-cvss-badge>
 * The CVSS bands here MUST match metrics/cvss.py (None 0, Low <4, Medium <7, High <9, Critical >=9).
 */
(function () {
  function cell(row, i) { return (row.children[i] ? row.children[i].getAttribute('data-v') || row.children[i].textContent : '').trim(); }

  document.querySelectorAll('table.sortable').forEach(function (table) {
    var heads = table.querySelectorAll('th[data-sort]');
    heads.forEach(function (th) {
      th.addEventListener('click', function () {
        var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
        var num = th.getAttribute('data-sort') === 'num';
        var asc = !th.classList.contains('sorted-asc');
        heads.forEach(function (h) { h.classList.remove('sorted-asc', 'sorted-desc'); });
        th.classList.add(asc ? 'sorted-asc' : 'sorted-desc');
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          var x = cell(a, idx), y = cell(b, idx);
          if (num) { x = parseFloat(x); y = parseFloat(y); x = isNaN(x) ? -Infinity : x; y = isNaN(y) ? -Infinity : y; return asc ? x - y : y - x; }
          return asc ? x.localeCompare(y) : y.localeCompare(x);
        });
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  });

  function band(v) {
    if (v === '' || v === null || isNaN(v)) return null;
    v = parseFloat(v);
    if (v < 0 || v > 10) return 'Invalid';
    if (v <= 0) return 'None';
    if (v < 4) return 'Low';
    if (v < 7) return 'Medium';
    if (v < 9) return 'High';
    return 'Critical';
  }
  document.querySelectorAll('[data-cvss-input]').forEach(function (inp) {
    var badge = inp.parentNode.querySelector('[data-cvss-badge]') || document.querySelector('[data-cvss-badge]');
    function upd() {
      var b = band(inp.value);
      if (!badge) return;
      if (!b) { badge.className = 'cvss-badge cvss-None'; badge.textContent = 'no score'; return; }
      badge.className = 'cvss-badge cvss-' + (b === 'Invalid' ? 'Critical' : b);
      badge.textContent = b === 'Invalid' ? 'must be 0.0 - 10.0' : b;
    }
    inp.addEventListener('input', upd); upd();
  });
})();
