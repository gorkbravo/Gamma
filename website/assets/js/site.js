/* ============================================================
   GAMMA — site behavior
   Motion is functional: a measured pour-in, a sweep that tracks
   reading position, and one live board that actually ticks.
   ============================================================ */

(function () {
  'use strict';

  document.documentElement.classList.add('js');

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ── Pour-in: rows arrive in sequence, not all at once ───────── */
  function initReveal() {
    var nodes = Array.prototype.slice.call(document.querySelectorAll('.reveal'));
    if (!nodes.length) return;

    if (reduced || !('IntersectionObserver' in window)) {
      nodes.forEach(function (n) { n.classList.add('in'); });
      return;
    }

    var io = new IntersectionObserver(function (entries) {
      // Sort so a group entering together pours top-to-bottom.
      entries
        .filter(function (e) { return e.isIntersecting; })
        .sort(function (a, b) { return a.boundingClientRect.top - b.boundingClientRect.top; })
        .forEach(function (entry, i) {
          entry.target.style.setProperty('--d', (i * 55) + 'ms');
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        });
    }, { rootMargin: '0px 0px -12% 0px', threshold: 0.08 });

    nodes.forEach(function (n) { io.observe(n); });
  }

  /* ── Time rail: an instrument scale with even divisions ─────── */
  function initRail() {
    var rail = document.querySelector('.rail');
    if (!rail) return;

    var moments = Array.prototype.slice.call(document.querySelectorAll('[data-moment]'));
    var session = document.getElementById('session');
    if (!moments.length || !session) { rail.remove(); return; }

    var ticks = rail.querySelector('.rail-ticks');
    var sweep = rail.querySelector('.rail-sweep');

    // Divisions are evenly spaced, like a graticule. Position on the rail
    // encodes order in the session, not raw document offset.
    var marks = moments.map(function (m, i) {
      var el = document.createElement('a');
      el.className = 'rail-tick';
      el.href = '#' + m.id;
      el.textContent = m.getAttribute('data-moment');
      el.setAttribute('aria-label', m.getAttribute('data-moment') + ' — ' + (m.getAttribute('data-label') || ''));
      el.style.top = (10 + (i * 80) / Math.max(1, moments.length - 1)) + '%';
      ticks.appendChild(el);
      return { el: el, target: m };
    });

    var ticking = false;

    function place() {
      var vh = window.innerHeight;
      var box = session.getBoundingClientRect();

      // The rail belongs to the session; it is not a whole-page minimap.
      var active = box.top < vh * 0.6 && box.bottom > vh * 0.35;
      rail.classList.toggle('is-active', active);

      var travelled = Math.min(1, Math.max(0, (vh * 0.5 - box.top) / Math.max(1, box.height)));
      if (sweep) sweep.style.height = (10 + travelled * 80) + '%';

      var line = vh * 0.45;
      var current = -1;
      marks.forEach(function (m, i) {
        var r = m.target.getBoundingClientRect();
        if (r.top <= line && r.bottom > line) current = i;
      });
      if (current < 0 && box.top < line) current = marks.length - 1;
      marks.forEach(function (m, i) { m.el.classList.toggle('is-live', i === current); });

      ticking = false;
    }

    function onScroll() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(place);
    }

    place();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
  }

  /* ── Live board: a running miniature of Gamma's own tape ─────── */
  function initTerminal() {
    var root = document.querySelector('[data-term]');
    if (!root) return;

    // Synthetic demonstration data. Labelled MOCK on the surface itself,
    // exactly as the application labels its own sample provider.
    var boards = {
      sitrep: {
        head: ['Market', 'Last', 'Chg', '%Chg'],
        rows: [
          ['S&P 500', 5471.28, 12.44, 0.23],
          ['NASDAQ 100', 19318.70, -41.02, -0.21],
          ['STOXX 600', 517.63, 1.88, 0.36],
          ['US 10Y', 4.79, 0.032, 0.67],
          ['2s10s', 40, -2, -4.76],
          ['DXY', 118.7, -0.40, -0.34],
          ['WTI', 74.18, 0.62, 0.84]
        ],
        prov: [['Source', 'yfinance'], ['Origin', 'provider'], ['Cache', '300 s'], ['Retrieved', null]],
        note: 'SITREP composes one operating picture from Equity Research, Macro, Commodities, Prediction Markets and News. Each panel carries its own freshness and can degrade alone.'
      },
      macro: {
        head: ['Series', 'Level', 'Δ 3M', 'Signal'],
        rows: [
          ['Headline CPI YoY', 3.54, 0.22, 'INFLATION'],
          ['Core CPI YoY', 2.79, 0.11, 'INFLATION'],
          ['Fed Funds Rate', 3.63, 0.01, 'POLICY'],
          ['US 10Y Real Yield', 2.45, 0.38, 'POLICY'],
          ['2s10s Slope', 40, -2, 'CURVE'],
          ['Unemployment', 4.10, -0.20, 'GROWTH'],
          ['HY OAS', 2.66, -0.06, 'CREDIT']
        ],
        prov: [['Source', 'FRED'], ['Origin', 'derived'], ['Transform', 'YoY from index'], ['Retrieved', null]],
        note: 'Divergence score is the strongest positive signal minus the strongest negative one. The label — coherent, narrow, fractured — is a Gamma heuristic, and says so on screen.'
      },
      options: {
        head: ['Strike', 'C IV', 'C Δ', 'P IV', 'Move'],
        rows: [
          [489.97, 14.5, 0.845, 12.0, 2.3],
          [494.97, 14.6, 0.694, 12.1, 1.7],
          [499.97, 14.7, 0.504, 12.2, 1.5],
          [504.97, 14.8, 0.318, 12.3, 1.7],
          [509.97, 14.9, 0.172, 12.4, 2.3]
        ],
        prov: [['Source', 'IBKR / TWS'], ['Origin', 'provider + derived'], ['Fit', 'Line interpolation'], ['Retrieved', null]],
        note: 'Greeks are Gamma-owned Black-Scholes when the provider does not supply them, under zero-rate and zero-dividend assumptions. The payoff matrix is research math, not broker valuation.'
      },
      commodities: {
        head: ['Contract', 'Last', 'Spread', 'Shape'],
        rows: [
          ['WTI M1', 74.18, null, 'BACKWARDATION'],
          ['WTI M2', 73.62, -0.56, null],
          ['WTI M3', 73.15, -0.47, null],
          ['Brent M1', 78.44, null, 'BACKWARDATION'],
          ['Henry Hub M1', 2.87, null, 'CONTANGO'],
          ['Gold M1', 2412.30, null, 'CONTANGO'],
          ['Copper M1', 4.412, null, 'FLAT']
        ],
        prov: [['Source', 'EIA + FRED'], ['Origin', 'derived'], ['Transform', 'front-spread proxy'], ['Retrieved', null]],
        note: 'Roll-yield, spread z-scores and seasonal inventory context are Gamma heuristics built on official but partial, release-lagged data.'
      }
    };

    var tabs = Array.prototype.slice.call(root.querySelectorAll('.term-tab'));
    var tbody = root.querySelector('[data-tape-body]');
    var thead = root.querySelector('[data-tape-head]');
    var provList = root.querySelector('[data-prov]');
    var noteEl = root.querySelector('[data-note]');
    var titleEl = root.querySelector('[data-board-title]');
    var current = 'sitrep';
    var timer = null;

    function fmt(v, dp) {
      if (v === null || v === undefined) return '—';
      if (typeof v !== 'number') return v;
      return v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
    }

    function signClass(v) {
      if (typeof v !== 'number') return 'dim';
      return v > 0 ? 'pos' : v < 0 ? 'neg' : 'dim';
    }

    function signed(v, dp) {
      if (typeof v !== 'number') return v || '—';
      return (v > 0 ? '+' : '') + fmt(v, dp);
    }

    function stamp() {
      var d = new Date();
      return String(d.getHours()).padStart(2, '0') + ':' +
             String(d.getMinutes()).padStart(2, '0') + ':' +
             String(d.getSeconds()).padStart(2, '0');
    }

    function render(key) {
      var b = boards[key];
      if (!b) return;

      thead.innerHTML = '';
      b.head.forEach(function (h) {
        var th = document.createElement('th');
        th.textContent = h;
        th.scope = 'col';
        thead.appendChild(th);
      });

      tbody.innerHTML = '';
      b.rows.forEach(function (row) {
        var tr = document.createElement('tr');
        row.forEach(function (cell, i) {
          var td = document.createElement('td');
          if (i === 0) {
            td.className = 'sym';
            td.textContent = cell;
          } else if (typeof cell === 'string') {
            td.className = cell === 'BACKWARDATION' ? 'pos' : cell === 'CONTANGO' ? 'warn' : 'dim';
            td.textContent = cell;
          } else if (key === 'options') {
            td.textContent = fmt(cell, i === 2 ? 3 : i === 4 ? 1 : 1) + (i === 1 || i === 3 || i === 4 ? '%' : '');
          } else if (i >= 2) {
            td.className = signClass(cell);
            td.textContent = signed(cell, 2) + (i === 3 && key === 'sitrep' ? '%' : '');
          } else {
            td.textContent = fmt(cell, 2);
          }
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });

      provList.innerHTML = '';
      b.prov.forEach(function (p) {
        var wrap = document.createElement('div');
        wrap.className = 'prov-row';
        var dt = document.createElement('dt');
        dt.textContent = p[0];
        var dd = document.createElement('dd');
        if (p[1] === null) {
          dd.textContent = stamp();
          dd.setAttribute('data-clock', '');
        } else {
          dd.textContent = p[1];
        }
        wrap.appendChild(dt);
        wrap.appendChild(dd);
        provList.appendChild(wrap);
      });

      noteEl.textContent = b.note;
      if (titleEl) titleEl.textContent = key === 'sitrep' ? 'Cross-asset tape'
        : key === 'macro' ? 'US snapshot · 3M'
        : key === 'options' ? 'SPY · front expiry chain'
        : 'Energy & metals · front curve';
    }

    /* One value repriced at a time — the way a tape actually moves. */
    function tick() {
      if (reduced || document.hidden) return;
      var rows = tbody.querySelectorAll('tr');
      if (!rows.length) return;
      var row = rows[Math.floor(Math.random() * rows.length)];
      var cells = row.querySelectorAll('td');
      if (cells.length < 2) return;
      var cell = cells[1];
      var raw = parseFloat(cell.textContent.replace(/,/g, ''));
      if (isNaN(raw)) return;

      var drift = (Math.random() - 0.5) * Math.max(Math.abs(raw) * 0.0012, 0.004);
      var next = raw + drift;
      var dp = (cell.textContent.split('.')[1] || '').replace('%', '').length || 2;
      cell.textContent = next.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp }) +
        (cell.textContent.indexOf('%') > -1 ? '%' : '');
      cell.classList.remove('flash');
      void cell.offsetWidth;
      cell.classList.add('flash');

      root.querySelectorAll('[data-clock]').forEach(function (n) { n.textContent = stamp(); });
    }

    tabs.forEach(function (t) {
      t.addEventListener('click', function () {
        tabs.forEach(function (o) { o.setAttribute('aria-selected', 'false'); });
        t.setAttribute('aria-selected', 'true');
        current = t.getAttribute('data-board');
        render(current);
      });
      t.addEventListener('keydown', function (e) {
        var i = tabs.indexOf(t);
        var n = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : -1;
        if (n < 0 || n >= tabs.length) return;
        e.preventDefault();
        tabs[n].focus();
        tabs[n].click();
      });
    });

    render(current);
    if (!reduced) timer = window.setInterval(tick, 1500);
    document.addEventListener('visibilitychange', function () {
      if (document.hidden && timer) { clearInterval(timer); timer = null; }
      else if (!document.hidden && !timer && !reduced) { timer = window.setInterval(tick, 1500); }
    });
  }

  /* ── Copy buttons on command blocks ──────────────────────────── */
  function initCopy() {
    document.querySelectorAll('.copy').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var pre = btn.closest('.code').querySelector('pre');
        if (!pre) return;
        var text = pre.innerText;
        var done = function () {
          var prev = btn.textContent;
          btn.textContent = 'Copied';
          btn.setAttribute('data-copied', 'true');
          window.setTimeout(function () {
            btn.textContent = prev;
            btn.removeAttribute('data-copied');
          }, 1600);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () {});
        } else {
          var ta = document.createElement('textarea');
          ta.value = text;
          document.body.appendChild(ta);
          ta.select();
          try { document.execCommand('copy'); done(); } catch (e) {}
          document.body.removeChild(ta);
        }
      });
    });
  }

  function boot() {
    initReveal();
    initRail();
    initTerminal();
    initCopy();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
