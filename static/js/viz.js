/*
 * viz.js - shared graphics library for the SQMA tool.
 * Every graph on every page (and on the Report page) is drawn by the functions
 * below, so a chart looks identical wherever it appears.
 *
 *   Chart.js (local copy)  -> doughnut, bar, histogram, line (control chart), scatter
 *   Pure SVG (no library)   -> box plot, decision-tree flowchart, security
 *                              "database + padlock" diagram, correlation reference
 *
 * Every function takes the id of an empty container <div> and draws inside it,
 * and shows a friendly message instead of a blank box when there is no data.
 */
window.SQMA = (function () {
  const COLOR = {
    blue: '#2f5fdb', teal: '#1c7293', green: '#16a34a', amber: '#d97706',
    red: '#dc2626', darkred: '#7f1d1d', navy: '#0f1b33', grey: '#6b7280',
  };
  const SEVERITY = { Low: '#16a34a', Medium: '#d97706', High: '#dc2626', Critical: '#7f1d1d' };
  const CLASS_COLOR = { Low: '#16a34a', Medium: '#d97706', High: '#dc2626' };
  const NS = 'http://www.w3.org/2000/svg';

  if (typeof Chart !== 'undefined') {
    Chart.defaults.animation = false;            // draw instantly (also needed for printing)
    Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
    Chart.defaults.font.size = 12;
  }

  // ---------- helpers ----------
  function box(id) { return document.getElementById(id); }

  function empty(id, message) {
    const b = box(id); if (!b) return;
    b.innerHTML = '<div class="chart-empty"><i class="fa-solid fa-chart-column"></i><span>' + message + '</span></div>';
  }

  function canvas(id) {
    const b = box(id); if (!b) return null;
    if (typeof Chart === 'undefined') { empty(id, 'Chart library failed to load.'); return null; }
    b.innerHTML = '';
    const c = document.createElement('canvas');
    b.appendChild(c);
    return c.getContext('2d');
  }

  function svg(tag, attrs, parent, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }

  function svgRoot(id, w, h) {
    const b = box(id); if (!b) return null;
    b.innerHTML = '';
    const s = svg('svg', { viewBox: '0 0 ' + w + ' ' + h, width: '100%', role: 'img',
                           style: 'max-width:' + w + 'px;display:block;margin:0 auto;' });
    b.appendChild(s);
    return s;
  }

  // small inline Chart.js plugin: print the value on top of each bar
  const valueLabels = {
    id: 'valueLabels',
    afterDatasetsDraw(chart, args, opts) {
      if (!opts || !opts.enabled) return;
      const { ctx } = chart;
      ctx.save();
      ctx.font = 'bold 12px Segoe UI, sans-serif';
      ctx.fillStyle = '#1f2937';
      chart.getDatasetMeta(0).data.forEach((bar, i) => {
        const v = chart.data.datasets[0].data[i];
        if (v === null || v === undefined || (v === 0 && opts.hideZero)) return;
        const txt = (opts.format ? opts.format(v) : v);
        if (chart.options.indexAxis === 'y') {
          ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
          ctx.fillText(txt, bar.x + 6, bar.y);
        } else {
          ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
          ctx.fillText(txt, bar.x, bar.y - 4);
        }
      });
      ctx.restore();
    },
  };

  // =====================================================================
  // 1. Defect severity doughnut
  // =====================================================================
  function severityDoughnut(id, labels, values) {
    const total = (values || []).reduce((a, b) => a + b, 0);
    if (!total) { empty(id, 'No bugs logged yet. Add bugs in <b>Bug Management</b> (or load demo data) to see the severity split.'); return; }
    const ctx = canvas(id); if (!ctx) return;
    new Chart(ctx, {
      type: 'doughnut',
      data: { labels, datasets: [{ data: values, backgroundColor: labels.map(l => SEVERITY[l] || COLOR.blue), borderColor: '#fff', borderWidth: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '58%',
                 plugins: { legend: { position: 'bottom' },
                            tooltip: { callbacks: { label: c => ' ' + c.label + ': ' + c.parsed + ' bug(s)' } } } },
    });
  }

  // =====================================================================
  // 2. Quality score components (0-100 bars, coloured by level)
  // =====================================================================
  function qualityBars(id, comps) {
    const labels = ['Maintainability', 'Complexity', 'Defects', 'Security'];
    const keys = ['maintainability', 'complexity', 'defects', 'security'];
    const values = keys.map(k => comps[k]);
    const colour = v => v >= 80 ? COLOR.green : v >= 60 ? COLOR.blue : v >= 40 ? COLOR.amber : COLOR.red;
    const ctx = canvas(id); if (!ctx) return;
    new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets: [{ label: 'Score (0-100)', data: values, backgroundColor: values.map(colour), borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false,
                 scales: { y: { beginAtZero: true, max: 110, ticks: { stepSize: 20, callback: v => v <= 100 ? v : '' }, title: { display: true, text: 'Score (0 - 100)' } },
                           x: { grid: { display: false } } },
                 plugins: { legend: { display: false }, valueLabels: { enabled: true } } },
      plugins: [valueLabels],
    });
  }

  // =====================================================================
  // 3. Histogram - touching bars, one per class interval (like the reference)
  // =====================================================================
  function histogram(id, labels, counts, xTitle, yTitle) {
    if (!counts || !counts.length || counts.every(c => c === 0)) {
      empty(id, 'No data yet. Upload source files so functions can be measured.'); return;
    }
    const palette = ['#7aa6d6', '#a5d86e', '#5b9a3c', '#f0a04b', '#d9542c', '#7aa6d6', '#a5d86e', '#5b9a3c'];
    const ctx = canvas(id); if (!ctx) return;
    new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets: [{ label: 'Frequency', data: counts, backgroundColor: counts.map((_, i) => palette[i % palette.length]),
                                   borderColor: '#fff', borderWidth: 2, categoryPercentage: 1.0, barPercentage: 1.0 }] },
      options: { responsive: true, maintainAspectRatio: false,
                 scales: { y: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: yTitle || 'Frequency (number of functions)' } },
                           x: { grid: { display: false }, title: { display: true, text: xTitle || 'Value ranges (bins)' } } },
                 plugins: { legend: { display: false }, valueLabels: { enabled: true, hideZero: true },
                            tooltip: { callbacks: { title: i => (xTitle || 'Range') + ': ' + i[0].label, label: c => ' ' + c.parsed.y + ' function(s)' } } } },
      plugins: [valueLabels],
    });
  }

  // =====================================================================
  // 4. Horizontal / vertical simple bars (importances, probabilities)
  // =====================================================================
  function bars(id, labels, values, opts) {
    opts = opts || {};
    if (!values || !values.length) { empty(id, opts.emptyMsg || 'No data available.'); return; }
    const ctx = canvas(id); if (!ctx) return;
    const horizontal = !!opts.horizontal;
    const colors = opts.colors || labels.map(() => COLOR.blue);
    const fmt = opts.format || (v => v);
    new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets: [{ label: opts.label || 'Value', data: values, backgroundColor: colors, borderRadius: 5 }] },
      options: { indexAxis: horizontal ? 'y' : 'x', responsive: true, maintainAspectRatio: false,
                 layout: { padding: { right: horizontal ? 46 : 0, top: horizontal ? 0 : 18 } },
                 scales: horizontal
                   ? { x: { beginAtZero: true, max: opts.max, title: { display: !!opts.xTitle, text: opts.xTitle } }, y: { grid: { display: false } } }
                   : { y: { beginAtZero: true, max: opts.max, ticks: opts.tickMax ? { callback: t => t <= opts.tickMax ? t : '' } : {}, title: { display: !!opts.yTitle, text: opts.yTitle } }, x: { grid: { display: false } } },
                 plugins: { legend: { display: false }, valueLabels: { enabled: true, format: fmt },
                            tooltip: { callbacks: { label: c => ' ' + fmt(c.parsed[horizontal ? 'x' : 'y']) } } } },
      plugins: [valueLabels],
    });
  }

  // =====================================================================
  // 5. Control chart (X chart): data line + CL / UCL / LCL
  // =====================================================================
  function controlChart(id, d) {
    if (!d || d.error) { empty(id, (d && d.error) || 'No data.'); return; }
    const ctx = canvas(id); if (!ctx) return;
    const n = d.values.length;
    const ooc = new Set((d.out_of_control_points || []).map(p => p.index));
    const line = v => d.values.map(() => v);
    const zone = {   // light green band between LCL and UCL
      id: 'zone',
      beforeDatasetsDraw(chart) {
        const { ctx, chartArea, scales } = chart;
        const y1 = scales.y.getPixelForValue(d.ucl), y2 = scales.y.getPixelForValue(d.lcl);
        ctx.save(); ctx.fillStyle = 'rgba(33,195,154,0.08)';
        ctx.fillRect(chartArea.left, Math.min(y1, y2), chartArea.width, Math.abs(y2 - y1)); ctx.restore();
      },
      afterDatasetsDraw(chart) {            // right-hand labels UCL / X-bar / LCL
        const { ctx, chartArea, scales } = chart;
        ctx.save(); ctx.font = 'bold 12px Segoe UI, sans-serif'; ctx.textAlign = 'right';
        [[d.ucl, 'UCL = ' + d.ucl, COLOR.red], [d.center_line, 'CL (mean) = ' + d.center_line, COLOR.green], [d.lcl, 'LCL = ' + d.lcl, COLOR.red]].forEach(([v, t, c]) => {
          const yy = scales.y.getPixelForValue(v) - 6, w = ctx.measureText(t).width;
          ctx.fillStyle = 'rgba(255,255,255,0.85)'; ctx.fillRect(chartArea.right - w - 10, yy - 12, w + 8, 16);
          ctx.fillStyle = c; ctx.fillText(t, chartArea.right - 6, yy);
        });
        ctx.restore();
      },
    };
    const ymax = Math.max(d.ucl, ...d.values) * 1.15 || 1;
    new Chart(ctx, {
      type: 'line',
      data: { labels: d.labels, datasets: [
        { label: 'Bugs reported', data: d.values, borderColor: '#1e4fa8', backgroundColor: '#1e4fa8', borderWidth: 2, tension: 0,
          pointRadius: d.values.map((_, i) => ooc.has(i) ? 8 : 4), pointBackgroundColor: d.values.map((_, i) => ooc.has(i) ? COLOR.red : '#1e4fa8'),
          pointBorderColor: d.values.map((_, i) => ooc.has(i) ? '#fff' : '#1e4fa8'), pointBorderWidth: 2 },
        { label: 'UCL (upper control limit)', data: line(d.ucl), borderColor: COLOR.red, borderWidth: 2.5, pointRadius: 0 },
        { label: 'CL (centre line / mean)', data: line(d.center_line), borderColor: COLOR.green, borderWidth: 2.5, pointRadius: 0 },
        { label: 'LCL (lower control limit)', data: line(d.lcl), borderColor: COLOR.red, borderWidth: 2.5, pointRadius: 0 },
      ] },
      options: { responsive: true, maintainAspectRatio: false,
                 scales: { y: { beginAtZero: true, max: Math.ceil(ymax), ticks: { precision: 0 }, title: { display: true, text: d.y_title || 'Bugs reported' } },
                           x: { title: { display: true, text: d.x_title || 'Sub-group (time period)' }, ticks: { maxTicksLimit: 14, maxRotation: 45 } } },
                 plugins: { legend: { position: 'bottom' } } },
      plugins: [zone],
    });
  }

  // =====================================================================
  // 6. Scatter + least-squares trend line (correlation)
  // =====================================================================
  function scatter(id, pts, trend, xTitle, yTitle) {
    if (!pts || pts.length < 2) { empty(id, 'Need at least 2 functions to draw a scatter plot. Upload more source code.'); return; }
    const ctx = canvas(id); if (!ctx) return;
    const ds = [{ label: 'Functions', data: pts, backgroundColor: '#5aa83c', borderColor: '#2f6f1e', pointRadius: 6, pointHoverRadius: 8 }];
    if (trend) ds.push({ label: 'Trend line (least squares)', data: trend, type: 'scatter', showLine: true, pointRadius: 0,
                         borderColor: COLOR.red, borderDash: [8, 5], borderWidth: 2.5, backgroundColor: COLOR.red });
    new Chart(ctx, {
      type: 'scatter', data: { datasets: ds },
      options: { responsive: true, maintainAspectRatio: false,
                 scales: { x: { title: { display: true, text: xTitle } }, y: { title: { display: true, text: yTitle } } },
                 plugins: { legend: { position: 'bottom' },
                            tooltip: { callbacks: { label: c => c.raw.name ? ' ' + c.raw.name + ' (' + c.raw.x + ', ' + c.raw.y + ')' : ' (' + c.raw.x + ', ' + c.raw.y + ')' } } } },
    });
  }

  // =====================================================================
  // 7. Correlation reference diagram: positive / zero / negative
  // =====================================================================
  function correlationRef(id, kind) {
    const W = 810, H = 250, s = svgRoot(id, W, H); if (!s) return;
    const panels = [
      { key: 'positive', title: 'Positive correlation', note: 'both rise together',
        pts: [[18,78],[26,70],[30,74],[38,58],[44,62],[52,48],[58,50],[66,36],[72,38],[80,22]], arrow: [10, 86, 88, 14] },
      { key: 'zero', title: 'Zero correlation', note: 'no relationship',
        pts: [[18,30],[30,62],[36,22],[44,50],[52,70],[58,28],[66,58],[72,40],[80,66],[26,48]], arrow: [10, 48, 88, 46] },
      { key: 'negative', title: 'Negative correlation', note: 'one rises, other falls',
        pts: [[18,20],[26,30],[30,26],[38,42],[44,38],[52,52],[58,50],[66,64],[72,62],[80,78]], arrow: [10, 14, 88, 86] },
    ];
    const pw = 240, gap = 30;
    panels.forEach((p, i) => {
      const g = svg('g', { transform: 'translate(' + (i * (pw + gap) + 10) + ',6)' }, s);
      const active = p.key === kind;
      svg('rect', { x: 0, y: 0, width: pw, height: 238, rx: 10, fill: active ? '#f0fdf4' : '#ffffff',
                    stroke: active ? COLOR.green : '#d6dce5', 'stroke-width': active ? 3 : 1 }, g);
      const ox = 26, oy = 150, sx = 1.9, sy = 1.35;
      svg('line', { x1: ox, y1: oy, x2: ox, y2: 18, stroke: '#111', 'stroke-width': 2 }, g);
      svg('line', { x1: ox, y1: oy, x2: pw - 16, y2: oy, stroke: '#111', 'stroke-width': 2 }, g);
      svg('polygon', { points: ox + ',12 ' + (ox - 5) + ',22 ' + (ox + 5) + ',22', fill: '#111' }, g);
      svg('polygon', { points: (pw - 10) + ',' + oy + ' ' + (pw - 20) + ',' + (oy - 5) + ' ' + (pw - 20) + ',' + (oy + 5), fill: '#111' }, g);
      p.pts.forEach(q => svg('rect', { x: ox + q[0] * sx - 3, y: 14 + q[1] * sy - 3, width: 7, height: 7, fill: '#5aa83c' }, g));
      const a = p.arrow;
      svg('line', { x1: ox + a[0] * sx, y1: 14 + a[1] * sy, x2: ox + a[2] * sx, y2: 14 + a[3] * sy, stroke: '#111', 'stroke-width': 3 }, g);
      const ex = ox + a[2] * sx, ey = 14 + a[3] * sy, ang = Math.atan2(a[3] - a[1], (a[2] - a[0])) ;
      const hx = [ex, ex - 12 * Math.cos(ang - 0.45), ex - 12 * Math.cos(ang + 0.45)];
      const hy = [ey, ey - 12 * Math.sin(ang - 0.45), ey - 12 * Math.sin(ang + 0.45)];
      svg('polygon', { points: hx.map((x, k) => x + ',' + hy[k]).join(' '), fill: '#111' }, g);
      svg('text', { x: pw / 2, y: 188, 'text-anchor': 'middle', 'font-size': 16, 'font-weight': 700, fill: active ? '#15803d' : '#5aa83c' }, g, p.title);
      svg('text', { x: pw / 2, y: 208, 'text-anchor': 'middle', 'font-size': 12, fill: '#6b7280' }, g, p.note);
      if (active) svg('text', { x: pw / 2, y: 228, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 700, fill: '#15803d' }, g, '\u25B2 your project falls here');
    });
  }

  // =====================================================================
  // 8. Box plot (horizontal box-and-whisker, annotated like the reference)
  // =====================================================================
  function niceTicks(lo, hi, target) {
    const span = hi - lo || 1, raw = span / (target || 8);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 5, 10].map(m => m * mag).find(s => s >= raw) || raw;
    const ticks = []; for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) ticks.push(+t.toFixed(6));
    return ticks;
  }

  function boxplot(id, b, unit) {
    if (!b || b.error) { empty(id, (b && b.error) || 'No data.'); return; }
    const W = 900, H = 400, L = 50, R = 40, s = svgRoot(id, W, H); if (!s) return;
    const all = (b.values || [b.min, b.max]).concat([b.min, b.max]);
    let d0 = Math.min(...all), d1 = Math.max(...all);
    if (d0 === d1) { d0 -= 1; d1 += 1; }
    const pad = (d1 - d0) * 0.06; d0 -= pad; d1 += pad;
    const X = v => L + (v - d0) / (d1 - d0) * (W - L - R);
    const yMid = 170, boxTop = 135, boxBot = 205, axisY = 335;

    svg('rect', { x: 0, y: 0, width: W, height: H, fill: '#fff' }, s);
    // axis
    svg('line', { x1: L, y1: axisY, x2: W - R, y2: axisY, stroke: '#222', 'stroke-width': 2 }, s);
    niceTicks(d0, d1, 9).forEach(t => {
      svg('line', { x1: X(t), y1: axisY, x2: X(t), y2: axisY + 7, stroke: '#222', 'stroke-width': 1.5 }, s);
      svg('text', { x: X(t), y: axisY + 25, 'text-anchor': 'middle', 'font-size': 14, fill: '#15803d', 'font-weight': 600 }, s, t);
      svg('line', { x1: X(t), y1: 40, x2: X(t), y2: axisY, stroke: '#eef0f4', 'stroke-width': 1 }, s);
    });
    svg('text', { x: (L + W - R) / 2, y: 380, 'text-anchor': 'middle', 'font-size': 14, fill: '#374151' }, s, unit || 'Value');

    // fences (dashed)
    [[b.lower_fence, 'Q1 \u2212 1.5\u00b7IQR'], [b.upper_fence, 'Q3 + 1.5\u00b7IQR']].forEach(([f, t]) => {
      if (f >= d0 && f <= d1) {
        svg('line', { x1: X(f), y1: 100, x2: X(f), y2: axisY, stroke: '#9ca3af', 'stroke-width': 1.5, 'stroke-dasharray': '5 4' }, s);
        svg('text', { x: X(f), y: 94, 'text-anchor': 'middle', 'font-size': 11, fill: '#6b7280' }, s, t + ' = ' + f);
      }
    });

    // whiskers
    const lw = b.lower_whisker, uw = b.upper_whisker;
    svg('line', { x1: X(lw), y1: yMid, x2: X(b.q1), y2: yMid, stroke: '#111', 'stroke-width': 2 }, s);
    svg('line', { x1: X(b.q3), y1: yMid, x2: X(uw), y2: yMid, stroke: '#111', 'stroke-width': 2 }, s);
    [lw, uw].forEach(v => svg('line', { x1: X(v), y1: yMid - 18, x2: X(v), y2: yMid + 18, stroke: '#111', 'stroke-width': 3 }, s));
    // labels sit on the OUTER side of each whisker end (min -> left, max -> right) so they cannot overlap
    svg('text', { x: X(lw) - 6, y: yMid - 24, 'text-anchor': 'end', 'font-size': 12, 'font-weight': 700, fill: '#15803d' }, s, 'Minimum = ' + lw);
    svg('text', { x: X(uw) + 6, y: yMid - 24, 'text-anchor': 'start', 'font-size': 12, 'font-weight': 700, fill: '#15803d' }, s, 'Maximum = ' + uw);

    // box + median
    const defs = svg('defs', {}, s);
    const grad = svg('radialGradient', { id: 'bxg' + id }, defs);
    svg('stop', { offset: '0%', 'stop-color': '#bfe3c8' }, grad); svg('stop', { offset: '100%', 'stop-color': '#f4fbf6' }, grad);
    const bw = Math.max(X(b.q3) - X(b.q1), 3);
    svg('rect', { x: X(b.q1), y: boxTop, width: bw, height: boxBot - boxTop, fill: 'url(#bxg' + id + ')', stroke: '#6b7280', 'stroke-width': 1.5 }, s);
    svg('line', { x1: X(b.median), y1: boxTop, x2: X(b.median), y2: boxBot, stroke: '#111', 'stroke-width': 3.5 }, s);

    // IQR arrow
    const ay = 62;
    svg('line', { x1: X(b.q1), y1: ay, x2: X(b.q3), y2: ay, stroke: '#111', 'stroke-width': 2 }, s);
    [[X(b.q1), 1], [X(b.q3), -1]].forEach(([x, dir]) => svg('polygon', { points: x + ',' + ay + ' ' + (x + 9 * dir) + ',' + (ay - 5) + ' ' + (x + 9 * dir) + ',' + (ay + 5), fill: '#111' }, s));
    svg('text', { x: (X(b.q1) + X(b.q3)) / 2, y: 44, 'text-anchor': 'middle', 'font-size': 14, 'font-weight': 700, fill: '#15803d' }, s, 'Interquartile range (IQR) = ' + b.iqr);

    // outliers
    (b.outliers || []).forEach(v => {
      svg('circle', { cx: X(v), cy: yMid, r: 8, fill: COLOR.red, stroke: '#fff', 'stroke-width': 2 }, s);
    });
    if ((b.outliers || []).length) {
      const ox = X(b.outliers[b.outliers.length - 1]);
      svg('text', { x: ox, y: yMid + 34, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 700, fill: COLOR.red }, s, 'Outlier(s): ' + b.outliers.join(', '));
    }

    // staggered leader labels under the box (so close values never overlap)
    [[b.q1, 'Q1 (25th percentile) = ' + b.q1, 232], [b.median, 'Median (50th percentile) = ' + b.median, 262], [b.q3, 'Q3 (75th percentile) = ' + b.q3, 292]].forEach(([v, t, y]) => {
      svg('line', { x1: X(v), y1: boxBot, x2: X(v), y2: y - 14, stroke: '#15803d', 'stroke-width': 1, 'stroke-dasharray': '3 3' }, s);
      const flip = X(v) > W * 0.62;
      svg('text', { x: X(v) + (flip ? -6 : 6), y: y, 'text-anchor': flip ? 'end' : 'start', 'font-size': 13, 'font-weight': 600, fill: '#15803d' }, s, t);
    });
  }

  // =====================================================================
  // 9. Decision-tree flowchart (root / decision / leaf nodes + highlighted path)
  // =====================================================================
  function treeDiagram(id, tree, pathIds, opts) {
    if (!tree) { empty(id, 'No tree available.'); return; }
    opts = opts || {};
    const path = new Set(pathIds || []);
    const NW = 158, NH = 50, HG = 22, VG = 78, PADX = 24, TOP = 20;
    let leafCount = 0;
    (function assign(n, depth) {
      n.depth = depth;
      if (!n.children || !n.children.length) { n.x = leafCount++; return; }
      n.children.forEach(c => assign(c, depth + 1));
      n.x = (n.children[0].x + n.children[n.children.length - 1].x) / 2;
    })(tree, 0);
    let maxDepth = 0; (function m(n) { maxDepth = Math.max(maxDepth, n.depth); (n.children || []).forEach(m); })(tree);
    const W = PADX * 2 + leafCount * (NW + HG) - HG, H = TOP * 2 + (maxDepth + 1) * NH + maxDepth * VG + 30;
    const b = box(id); if (!b) return; b.innerHTML = '';
    // toolbar: switch between readable actual size (scrolls sideways) and a fit-to-screen overview
    const bar = document.createElement('div'); bar.className = 'tree-toolbar d-print-none';
    bar.innerHTML = '<button type="button" class="btn btn-sm btn-primary" data-m="actual"><i class="fa-solid fa-magnifying-glass-plus"></i> Actual size (scroll sideways)</button> ' +
                    '<button type="button" class="btn btn-sm btn-outline-primary" data-m="fit"><i class="fa-solid fa-expand"></i> Fit whole tree to screen</button>' +
                    '<span class="small text-muted ms-2">Tip: ' + leafCount + ' leaf nodes - drag the scroll bar to see all branches.</span>';
    b.appendChild(bar);
    const wrap = document.createElement('div'); wrap.className = 'tree-scroll'; b.appendChild(wrap);
    const s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, role: 'img' }, wrap);
    const rootX = PADX + tree.x * (NW + HG) + NW / 2;
    const setMode = m => {
      if (m === 'fit') { s.style.width = '100%'; s.style.height = 'auto'; wrap.scrollLeft = 0; }
      else { s.style.width = W + 'px'; s.style.height = H + 'px'; wrap.scrollLeft = Math.max(0, rootX - wrap.clientWidth / 2); }
      bar.querySelectorAll('button').forEach(x => { x.className = 'btn btn-sm ' + (x.dataset.m === m ? 'btn-primary' : 'btn-outline-primary'); });
    };
    bar.querySelectorAll('button').forEach(x => x.addEventListener('click', () => setMode(x.dataset.m)));
    setTimeout(() => setMode('actual'), 0);
    const cx = n => PADX + n.x * (NW + HG) + NW / 2;
    const cy = n => TOP + n.depth * (NH + VG) + NH / 2;
    const arrow = svg('defs', {}, s);
    const mk = (idn, col) => { const m = svg('marker', { id: idn + id, markerUnits: 'userSpaceOnUse', markerWidth: 11, markerHeight: 11, refX: 10, refY: 5.5, orient: 'auto' }, arrow); svg('path', { d: 'M0,0 L11,5.5 L0,11 z', fill: col }, m); };
    mk('ah', '#374151'); mk('ao', '#f97316');

    (function edges(n) {
      (n.children || []).forEach((c, i) => {
        const on = path.has(n.id) && path.has(c.id);
        const x1 = cx(n), y1 = cy(n) + NH / 2, x2 = cx(c), y2 = cy(c) - NH / 2 - (c.children && c.children.length ? 0 : -2), my = (y1 + y2) / 2;
        svg('path', { d: 'M' + x1 + ',' + y1 + ' L' + x1 + ',' + my + ' L' + x2 + ',' + my + ' L' + x2 + ',' + (y2 - 1),
                      fill: 'none', stroke: on ? '#f97316' : '#374151', 'stroke-width': on ? 3.5 : 1.6, 'marker-end': 'url(#' + (on ? 'ao' : 'ah') + id + ')' }, s);
        svg('text', { x: (x1 + x2) / 2 + (i === 0 ? -6 : 6), y: my - 5, 'text-anchor': i === 0 ? 'end' : 'start', 'font-size': 11, 'font-weight': 700, fill: on ? '#c2410c' : '#6b7280' }, s, i === 0 ? 'Yes' : 'No');
        edges(c);
      });
    })(tree);

    (function nodes(n) {
      const on = path.has(n.id), leaf = !n.children || !n.children.length, x = cx(n), y = cy(n);
      if (leaf) {
        svg('ellipse', { cx: x, cy: y, rx: NW / 2 - 6, ry: NH / 2, fill: CLASS_COLOR[n.cls] || '#2e7d32', stroke: on ? '#f97316' : '#14532d', 'stroke-width': on ? 4 : 1.5 }, s);
        svg('text', { x, y: y - 3, 'text-anchor': 'middle', 'font-size': 13, 'font-weight': 700, fill: '#fff' }, s, 'Leaf: ' + n.cls + ' risk');
        svg('text', { x, y: y + 13, 'text-anchor': 'middle', 'font-size': 10.5, fill: '#fff' }, s, 'samples = ' + n.samples);
      } else {
        svg('rect', { x: x - NW / 2, y: y - NH / 2, width: NW, height: NH, rx: 9, fill: n.depth === 0 ? '#b7dfae' : '#d4ecce', stroke: on ? '#f97316' : '#6aa66a', 'stroke-width': on ? 4 : 1.5 }, s);
        svg('text', { x, y: y - 4, 'text-anchor': 'middle', 'font-size': 12.5, 'font-weight': 700, fill: '#14301a' }, s, n.label);
        svg('text', { x, y: y + 13, 'text-anchor': 'middle', 'font-size': 10.5, fill: '#355c38' }, s, (n.depth === 0 ? 'Root node \u2022 ' : 'Decision node \u2022 ') + 'n = ' + n.samples);
      }
      (n.children || []).forEach(nodes);
    })(tree);
  }

  // linear "path taken" chain (compact version used on the Report page)
  function treePath(id, steps, finalClass) {
    if (!steps || !steps.length) { empty(id, 'No decision path.'); return; }
    const NW = 210, NH = 56, G = 52, W = steps.length * NW + (steps.length) * G + 150, H = 150;
    const s = svgRoot(id, Math.max(W, 700), H); if (!s) return;
    let x = 10;
    steps.forEach((st, i) => {
      svg('rect', { x, y: 40, width: NW, height: NH, rx: 10, fill: i === 0 ? '#b7dfae' : '#d4ecce', stroke: '#f97316', 'stroke-width': 3 }, s);
      svg('text', { x: x + NW / 2, y: 62, 'text-anchor': 'middle', 'font-size': 13, 'font-weight': 700, fill: '#14301a' }, s, st.text);
      svg('text', { x: x + NW / 2, y: 82, 'text-anchor': 'middle', 'font-size': 11, fill: '#355c38' }, s, (i === 0 ? 'Root node' : 'Decision node') + ' \u2022 your value = ' + st.value);
      svg('line', { x1: x + NW, y1: 68, x2: x + NW + G - 6, y2: 68, stroke: '#f97316', 'stroke-width': 3 }, s);
      svg('polygon', { points: (x + NW + G) + ',68 ' + (x + NW + G - 12) + ',62 ' + (x + NW + G - 12) + ',74', fill: '#f97316' }, s);
      svg('text', { x: x + NW + G / 2, y: 58, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 700, fill: '#c2410c' }, s, st.answer);
      x += NW + G;
    });
    svg('ellipse', { cx: x + 70, cy: 68, rx: 70, ry: 30, fill: CLASS_COLOR[finalClass] || '#2e7d32', stroke: '#f97316', 'stroke-width': 3 }, s);
    svg('text', { x: x + 70, y: 64, 'text-anchor': 'middle', 'font-size': 13, 'font-weight': 700, fill: '#fff' }, s, 'Leaf node');
    svg('text', { x: x + 70, y: 82, 'text-anchor': 'middle', 'font-size': 13, 'font-weight': 700, fill: '#fff' }, s, finalClass + ' risk');
  }

  // =====================================================================
  // 10. Security "database + padlock" diagram
  // =====================================================================
  function securityStack(id, d) {
    const W = 900, H = 470, s = svgRoot(id, W, H); if (!s) return;
    const defs = svg('defs', {}, s);
    const g1 = svg('linearGradient', { id: 'cyl' + id, x1: 0, x2: 1, y1: 0, y2: 0 }, defs);
    svg('stop', { offset: '0%', 'stop-color': '#0d8fd0' }, g1); svg('stop', { offset: '45%', 'stop-color': '#4fc3f7' }, g1); svg('stop', { offset: '100%', 'stop-color': '#0b78b3' }, g1);
    const cx = 400, rx = 150, ry = 34, top = 90, H1 = 62;
    const layers = [
      { name: 'HIGH severity', val: d.counts.High, col: '#dc2626', txt: d.notes.High },
      { name: 'MEDIUM severity', val: d.counts.Medium, col: '#d97706', txt: d.notes.Medium },
      { name: 'LOW severity', val: d.counts.Low, col: '#16a34a', txt: d.notes.Low },
      { name: 'FILES scanned', val: d.files, col: '#0b78b3', txt: 'Each uploaded .py file is parsed and checked.' },
      { name: 'RULES applied', val: d.rules, col: '#0d8fd0', txt: 'AST call checks + regex line checks.' },
    ];
    svg('text', { x: 20, y: 34, 'font-size': 20, 'font-weight': 700, fill: '#0f1b33' }, s, 'Security Analysis \u2013 Process Representation');

    // soft floor shadow
    svg('ellipse', { cx, cy: top + 5 * H1 + 22, rx: rx + 60, ry: 40, fill: '#e5e7eb' }, s);
    // 3-D bands first
    layers.forEach((L, i) => {
      const y0 = top + i * H1, y1 = y0 + H1;
      svg('path', { d: 'M' + (cx - rx) + ',' + y0 + ' A' + rx + ',' + ry + ' 0 0 0 ' + (cx + rx) + ',' + y0 + ' L' + (cx + rx) + ',' + y1 + ' A' + rx + ',' + ry + ' 0 0 1 ' + (cx - rx) + ',' + y1 + ' Z',
                    fill: 'url(#cyl' + id + ')', stroke: '#fff', 'stroke-width': 3 }, s);
    });
    // cylinder cap (drawn BEFORE the circles so it cannot hide the first one)
    svg('ellipse', { cx, cy: top, rx, ry, fill: '#0b6aa3', stroke: '#fff', 'stroke-width': 3 }, s);
    svg('text', { x: cx, y: top - 2, 'text-anchor': 'middle', 'font-size': 15, 'font-weight': 800, fill: '#fff' }, s, 'Security posture');
    svg('text', { x: cx, y: top + 15, 'text-anchor': 'middle', 'font-size': 13, fill: '#e0f2fe' }, s, d.files === 0 ? 'NOT SCANNED' : (d.level === 'None' ? 'NO ISSUES FOUND' : d.level.toUpperCase() + ' RISK'));
    // count circles + explanatory text on top
    layers.forEach((L, i) => {
      const y0 = top + i * H1, cyc = y0 + H1 / 2 + 22;
      svg('circle', { cx, cy: cyc, r: 22, fill: L.col, stroke: '#fff', 'stroke-width': 3 }, s);
      svg('text', { x: cx, y: cyc + 7, 'text-anchor': 'middle', 'font-size': 20, 'font-weight': 800, fill: '#fff' }, s, L.val);
      const ty = cyc - 6;
      svg('line', { x1: 250, y1: ty + 6, x2: cx - 30, y2: cyc, stroke: '#9ca3af', 'stroke-dasharray': '3 3' }, s);
      svg('text', { x: 20, y: ty, 'font-size': 14, 'font-weight': 800, fill: L.col }, s, L.name + ' : ' + L.val);
      const words = (L.txt || '').split(' '); let line = '', row = 0;
      words.forEach(w => { if ((line + w).length > 34) { svg('text', { x: 20, y: ty + 16 + row * 14, 'font-size': 11, fill: '#4b5563' }, s, line.trim()); line = ''; row++; } line += w + ' '; });
      if (line.trim() && row < 2) svg('text', { x: 20, y: ty + 16 + row * 14, 'font-size': 11, fill: '#4b5563' }, s, line.trim());
    });

    // padlock (open + red when any High finding, closed + green when none)
    const lx = 640, ly = 215, open = d.level === 'High';
    const none = d.files === 0;
    const body = none ? '#9ca3af' : (open ? '#f5b301' : (d.level === 'Medium' ? '#f59e0b' : '#22c55e'));
    const shackle = 'M' + (lx + 20) + ',' + (ly + 10) + ' L' + (lx + 20) + ',' + (ly - 22) + ' A30,30 0 0 1 ' + (lx + 80) + ',' + (ly - 22) + ' L' + (lx + 80) + ',' + (ly + 10);
    svg('path', { d: shackle, fill: 'none', stroke: '#9aa0a6', 'stroke-width': 15, 'stroke-linecap': 'round',
                  transform: open ? 'rotate(-32 ' + (lx + 20) + ' ' + (ly + 6) + ')' : '' }, s);
    svg('rect', { x: lx, y: ly, width: 100, height: 88, rx: 14, fill: body, stroke: '#b45309', 'stroke-width': 2 }, s);
    svg('circle', { cx: lx + 50, cy: ly + 36, r: 10, fill: '#1f2937' }, s);
    svg('rect', { x: lx + 46, y: ly + 40, width: 8, height: 26, rx: 3, fill: '#1f2937' }, s);
    svg('text', { x: lx + 50, y: ly + 118, 'text-anchor': 'middle', 'font-size': 15, 'font-weight': 800, fill: none ? COLOR.grey : (open ? COLOR.red : (d.level === 'Medium' ? COLOR.amber : COLOR.green)) }, s,
        none ? 'NO FILES SCANNED YET' : (open ? 'UNLOCKED \u2013 fix High issues' : (d.level === 'Medium' ? 'PARTLY SECURE' : 'LOCKED \u2013 secure')));
  }


  // ---------- release comparison (grouped bars: total / open / Critical+High / escaped per release) ----------
  function releaseComparison(id, d) {
    if (!d || !d.labels || !d.labels.length) {
      empty(id, 'No releases yet. Add a release (and tag bugs with it) to compare releases side by side.'); return;
    }
    const ctx = canvas(id); if (!ctx) return;
    new Chart(ctx, {
      type: 'bar',
      data: { labels: d.labels, datasets: [
        { label: 'Total bugs', data: d.total, backgroundColor: COLOR.blue, borderRadius: 4 },
        { label: 'Open bugs', data: d.open, backgroundColor: COLOR.amber, borderRadius: 4 },
        { label: 'Critical + High', data: d.critical_high, backgroundColor: COLOR.red, borderRadius: 4 },
        { label: 'Escaped (found in Production)', data: d.escaped, backgroundColor: COLOR.darkred, borderRadius: 4 },
      ] },
      options: { responsive: true, maintainAspectRatio: false,
                 plugins: { legend: { position: 'bottom' } },
                 scales: { x: { title: { display: true, text: 'Release' } },
                           y: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: 'Number of bugs' } } } },
    });
  }

  // ---------- open vs closed bar (small stacked bar drawn in plain HTML) ----------
  function openClosedBar(id, open, closed) {
    const b = box(id); if (!b) return;
    const t = open + closed;
    if (!t) { b.innerHTML = '<div class="text-muted small">No bugs yet.</div>'; return; }
    const po = (open / t * 100).toFixed(1), pc = (closed / t * 100).toFixed(1);
    b.innerHTML = '<div class="oc-bar"><span style="width:' + po + '%;background:' + COLOR.amber + '"></span><span style="width:' + pc + '%;background:' + COLOR.green + '"></span></div>';
  }

  // ---------- sub-folder comparison (grouped bars; two axes would hide small values, so metrics are shown as 2 charts) ----------
  function folderComparison(id, d) {
    if (!d || !d.labels || !d.labels.length) { empty(id, 'No source files yet. Upload a project folder to compare its sub-folders.'); return; }
    const ctx = canvas(id); if (!ctx) return;
    new Chart(ctx, {
      type: 'bar',
      data: { labels: d.labels, datasets: [
        { label: 'Files', data: d.files, backgroundColor: COLOR.blue, borderRadius: 4, yAxisID: 'y' },
        { label: 'Issues', data: d.issues, backgroundColor: COLOR.red, borderRadius: 4, yAxisID: 'y' },
        { label: 'Avg complexity', data: d.avg_cc, backgroundColor: COLOR.amber, borderRadius: 4, yAxisID: 'y' },
        { label: 'Maintainability (0-100)', data: d.mi, backgroundColor: COLOR.green, borderRadius: 4, yAxisID: 'y2' },
      ] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } },
                 scales: { x: { title: { display: true, text: 'Sub-folder' } },
                           y: { beginAtZero: true, title: { display: true, text: 'Files / issues / complexity' } },
                           y2: { beginAtZero: true, max: 100, position: 'right', grid: { drawOnChartArea: false },
                                 title: { display: true, text: 'Maintainability' } } } },
    });
  }

  return { folderComparison, releaseComparison, openClosedBar, severityDoughnut, qualityBars, histogram, bars, controlChart, scatter, correlationRef, boxplot, treeDiagram, treePath, securityStack, empty, COLOR, CLASS_COLOR, SEVERITY };
})();
