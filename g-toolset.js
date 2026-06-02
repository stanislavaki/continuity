// g-toolset.js — design dev tools toggled by G.
// Tools: (1) N-column grid overlay, (2) hover/click element inspector with live CSS controls.
// Self-contained: injects its own styles + markup + listeners once. Press G to toggle.
(() => {
  if (typeof document === 'undefined') return;
  if (document.getElementById('gridOverlay')) return;

  const N = 8;
  const OVERLAY_ID   = 'gridOverlay';
  const HIGHLIGHT_ID = 'gridInspectorHighlight';
  const PANEL_ID     = 'gridInspectorPanel';
  const BODY_CLASS   = 'gx-inspect-on';

  const style = document.createElement('style');
  style.textContent = `
    .grid-overlay {
      position: fixed; inset: 0; z-index: 9999;
      pointer-events: none; display: none;
      max-width: var(--maxw, 100%);
      margin: 0 auto;
      padding: 0 var(--gutter, 24px);
      box-sizing: border-box;
    }
    .grid-overlay.is-on {
      display: grid;
      grid-template-columns: repeat(${N}, 1fr);
      gap: var(--col-gap, 24px);
    }
    .grid-overlay .col {
      background: rgba(255, 0, 80, 0.08);
      outline: 1px dashed rgba(255, 0, 80, 0.5);
      height: 100%;
    }

    body.${BODY_CLASS}, body.${BODY_CLASS} * { cursor: crosshair !important; }
    body.${BODY_CLASS} ::selection { background: transparent; }

    #${HIGHLIGHT_ID} {
      position: fixed; pointer-events: none; z-index: 10000;
      outline: 2px solid rgba(0, 150, 255, 0.9);
      background: rgba(0, 150, 255, 0.12);
      box-sizing: border-box; display: none;
      transition: left .04s linear, top .04s linear, width .04s linear, height .04s linear;
    }

    #${PANEL_ID} {
      position: fixed; bottom: 16px; right: 16px;
      width: 240px; max-height: 80vh; overflow: auto;
      background: #fff; color: #111;
      border: 1px solid #ccc; border-radius: 8px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.18);
      font: 12px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      z-index: 10001; padding: 10px; display: none;
      opacity: 0.96;
    }
    #${PANEL_ID} * { box-sizing: border-box; }
    #${PANEL_ID} .gx-h { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; cursor: move; user-select: none; }
    #${PANEL_ID} .gx-sel { font-family: ui-monospace, Menlo, monospace; font-size: 11px; color: #555; word-break: break-all; }
    #${PANEL_ID} .gx-close { background: none; border: 0; cursor: pointer; font-size: 18px; line-height: 1; padding: 0 4px; color: #888; }
    #${PANEL_ID} .gx-close:hover { color: #111; }
    #${PANEL_ID} .gx-section { border-top: 1px solid #eee; padding: 8px 0; }
    #${PANEL_ID} .gx-section:first-of-type { border-top: 0; padding-top: 0; }
    #${PANEL_ID} .gx-section h4 { margin: 0 0 6px; font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: #888; font-weight: 600; }
    #${PANEL_ID} .gx-row { display: grid; grid-template-columns: 80px minmax(0, 1fr); gap: 6px; align-items: center; margin: 3px 0; }
    #${PANEL_ID} .gx-row label { color: #555; font-size: 11px; }
    #${PANEL_ID} .gx-row input[type=text] { width: 100%; padding: 3px 6px; border: 1px solid #ddd; border-radius: 4px; font: 11px/1.4 ui-monospace, Menlo, monospace; cursor: ew-resize; }
    #${PANEL_ID} .gx-row input[type=text]:focus { cursor: text; }
    #${PANEL_ID} .gx-row input[type=color] { width: 26px; height: 20px; padding: 0; border: 1px solid #ddd; border-radius: 4px; cursor: pointer; background: #fff; flex: 0 0 auto; }
    #${PANEL_ID} .gx-color { display: flex; gap: 4px; align-items: center; }
    #${PANEL_ID} .gx-color input[type=range] { flex: 1 1 auto; min-width: 0; height: 16px; padding: 0; cursor: pointer; }
    #${PANEL_ID} .gx-pct { font: 10px/1 ui-monospace, Menlo, monospace; color: #666; min-width: 26px; text-align: right; flex: 0 0 auto; }
    #${PANEL_ID} .gx-slider { display: flex; gap: 4px; align-items: center; }
    #${PANEL_ID} .gx-slider input[type=range] { flex: 1 1 auto; min-width: 0; height: 16px; padding: 0; cursor: pointer; }
    #${PANEL_ID} .gx-select { width: 100%; padding: 3px 6px; border: 1px solid #ddd; border-radius: 4px; font: 11px/1.4 inherit; background: #fff; cursor: pointer; }
    #${PANEL_ID} .gx-actions { margin-top: 10px; display: flex; gap: 6px; }
    #${PANEL_ID} .gx-actions button { flex: 1; padding: 6px 8px; border: 1px solid #ccc; background: #f6f6f6; border-radius: 4px; cursor: pointer; font: 11px/1.2 inherit; }
    #${PANEL_ID} .gx-actions button:hover { background: #ececec; }
  `;
  document.head.appendChild(style);

  const overlay = document.createElement('div');
  overlay.id = OVERLAY_ID;
  overlay.className = 'grid-overlay';
  overlay.setAttribute('aria-hidden', 'true');
  for (let i = 0; i < N; i++) {
    const col = document.createElement('div');
    col.className = 'col';
    overlay.appendChild(col);
  }
  document.body.appendChild(overlay);

  const highlight = document.createElement('div');
  highlight.id = HIGHLIGHT_ID;
  document.body.appendChild(highlight);

  const panel = document.createElement('div');
  panel.id = PANEL_ID;
  document.body.appendChild(panel);

  let panelDrag = null;
  panel.addEventListener('mousedown', (e) => {
    if (!e.target.closest('.gx-h') || e.target.closest('button, input')) return;
    const r = panel.getBoundingClientRect();
    panelDrag = { dx: e.clientX - r.left, dy: e.clientY - r.top };
    panel.style.left = r.left + 'px';
    panel.style.top  = r.top  + 'px';
    panel.style.right = 'auto';
    panel.style.bottom = 'auto';
    e.preventDefault();
  });
  document.addEventListener('mousemove', (e) => {
    if (!panelDrag) return;
    const x = Math.max(0, Math.min(window.innerWidth  - panel.offsetWidth,  e.clientX - panelDrag.dx));
    const y = Math.max(0, Math.min(window.innerHeight - panel.offsetHeight, e.clientY - panelDrag.dy));
    panel.style.left = x + 'px';
    panel.style.top  = y + 'px';
  });
  document.addEventListener('mouseup', () => { panelDrag = null; });

  let selected = null;
  let active   = false;

  function describe(el) {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    if (el.className && typeof el.className === 'string' && el.className.trim()) {
      s += '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.');
    }
    return s;
  }

  function placeHighlight(el) {
    const r = el.getBoundingClientRect();
    highlight.style.display = 'block';
    highlight.style.left   = r.left   + 'px';
    highlight.style.top    = r.top    + 'px';
    highlight.style.width  = r.width  + 'px';
    highlight.style.height = r.height + 'px';
  }

  function isOurUI(el) {
    return !el || el === overlay || el === highlight || el === panel
      || overlay.contains(el) || panel.contains(el) || highlight.contains(el)
      || (el.closest && el.closest('[data-g-toolset-modal]'));
  }

  function isImage(el) {
    return el.tagName === 'IMG' || /url\(/.test(getComputedStyle(el).backgroundImage);
  }

  function hasOwnText(el) {
    for (const node of el.childNodes) {
      if (node.nodeType === 3 && node.textContent.trim()) return true;
    }
    return false;
  }

  function parseRgba(s) {
    const m = (s || '').match(/(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?/);
    if (!m) return { r: 0, g: 0, b: 0, a: 1 };
    return {
      r: parseInt(m[1], 10),
      g: parseInt(m[2], 10),
      b: parseInt(m[3], 10),
      a: m[4] === undefined ? 1 : parseFloat(m[4]),
    };
  }
  function toHex(n) { return n.toString(16).padStart(2, '0'); }

  function makeRow(label, input) {
    const r = document.createElement('div');
    r.className = 'gx-row';
    const l = document.createElement('label');
    l.textContent = label;
    r.appendChild(l);
    r.appendChild(input);
    return r;
  }

  function parseFirstNumber(str) {
    const m = (str || '').match(/(-?\d+(?:\.\d+)?)/);
    if (!m) return null;
    const after = str.slice(m.index + m[0].length);
    const unitMatch = after.match(/^([a-z%]*)/i);
    const unit = unitMatch ? unitMatch[1] : '';
    return { num: parseFloat(m[1]), unit, start: m.index, end: m.index + m[0].length + unit.length };
  }
  function formatNum(n, step) {
    if (step >= 1)   return Math.round(n).toString();
    if (step >= 0.1) return (Math.round(n * 10) / 10).toString();
    return (Math.round(n * 100) / 100).toString();
  }
  function replaceFirstNumber(str, newNum, step) {
    const m = parseFirstNumber(str);
    if (!m) return str;
    return str.slice(0, m.start) + formatNum(newNum, step) + m.unit + str.slice(m.end);
  }
  function attachNumberScrubAndKeys(input) {
    input.title = 'Drag or ↑/↓ to nudge.  Shift = ×10,  Alt = ÷10';
    input.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
      const m = parseFirstNumber(input.value);
      if (!m) return;
      const step = e.shiftKey ? 10 : e.altKey ? 0.1 : 1;
      const dir  = e.key === 'ArrowUp' ? 1 : -1;
      input.value = replaceFirstNumber(input.value, m.num + dir * step, step);
      e.preventDefault();
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    input.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      const startX = e.clientX;
      let dragging = false, baseNum = 0, baseStr = '';
      const onMove = (ev) => {
        const dx = ev.clientX - startX;
        if (!dragging) {
          if (Math.abs(dx) < 4) return;
          const m = parseFirstNumber(input.value);
          if (!m) {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            return;
          }
          baseNum = m.num;
          baseStr = input.value;
          dragging = true;
          document.body.style.cursor = 'ew-resize';
          input.blur();
          try { window.getSelection().removeAllRanges(); } catch {}
        }
        const step = ev.shiftKey ? 10 : ev.altKey ? 0.1 : 1;
        input.value = replaceFirstNumber(baseStr, baseNum + dx * step, step);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        if (dragging) document.body.style.cursor = '';
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  function makeText(value, onInput) {
    const i = document.createElement('input');
    i.type = 'text';
    i.value = value || '';
    i.addEventListener('input', e => onInput(e.target.value));
    attachNumberScrubAndKeys(i);
    return i;
  }

  function makeColor(value, onChange) {
    const wrap = document.createElement('div');
    wrap.className = 'gx-color';
    const { r, g, b, a } = parseRgba(value);

    const swatch = document.createElement('input');
    swatch.type = 'color';
    swatch.value = '#' + toHex(r) + toHex(g) + toHex(b);

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.min = '0'; slider.max = '1'; slider.step = '0.01';
    slider.value = String(a);
    slider.title = 'Opacity';

    const pct = document.createElement('span');
    pct.className = 'gx-pct';
    pct.textContent = Math.round(a * 100) + '%';

    function emit() {
      const hex = swatch.value;
      const rr = parseInt(hex.slice(1, 3), 16);
      const gg = parseInt(hex.slice(3, 5), 16);
      const bb = parseInt(hex.slice(5, 7), 16);
      const aa = parseFloat(slider.value);
      pct.textContent = Math.round(aa * 100) + '%';
      onChange(`rgba(${rr}, ${gg}, ${bb}, ${aa})`);
    }
    swatch.addEventListener('input', emit);
    slider.addEventListener('input', emit);

    wrap.appendChild(swatch);
    wrap.appendChild(slider);
    wrap.appendChild(pct);
    return wrap;
  }

  function makeSlider(value, min, max, step, unit, onChange) {
    const wrap = document.createElement('div');
    wrap.className = 'gx-slider';
    const slider = document.createElement('input');
    slider.type = 'range';
    slider.min = String(min); slider.max = String(max); slider.step = String(step);
    slider.value = String(value);
    const valSpan = document.createElement('span');
    valSpan.className = 'gx-pct';
    valSpan.textContent = value + (unit || '');
    slider.addEventListener('input', e => {
      const v = parseFloat(e.target.value);
      valSpan.textContent = v + (unit || '');
      onChange(v);
    });
    wrap.appendChild(slider);
    wrap.appendChild(valSpan);
    return wrap;
  }

  function makeSelect(value, options, onChange) {
    const sel = document.createElement('select');
    sel.className = 'gx-select';
    for (const opt of options) {
      const o = document.createElement('option');
      o.value = opt; o.textContent = opt;
      if (opt === value) o.selected = true;
      sel.appendChild(o);
    }
    sel.addEventListener('change', e => onChange(e.target.value));
    return sel;
  }

  function buildPanel() {
    panel.innerHTML = '';
    if (!selected) { panel.style.display = 'none'; return; }
    panel.style.display = 'block';

    const cs = getComputedStyle(selected);

    const header = document.createElement('div');
    header.className = 'gx-h';
    const sel = document.createElement('span');
    sel.className = 'gx-sel';
    sel.textContent = describe(selected);
    const close = document.createElement('button');
    close.className = 'gx-close';
    close.type = 'button';
    close.textContent = '×';
    close.title = 'Deselect';
    close.addEventListener('click', () => {
      selected = null;
      highlight.style.display = 'none';
      buildPanel();
    });
    header.appendChild(sel);
    header.appendChild(close);
    panel.appendChild(header);

    const colorSec = document.createElement('div');
    colorSec.className = 'gx-section';
    const ch = document.createElement('h4'); ch.textContent = 'Color'; colorSec.appendChild(ch);
    colorSec.appendChild(makeRow('color',      makeColor(cs.color,           v => selected.style.color = v)));
    colorSec.appendChild(makeRow('background', makeColor(cs.backgroundColor, v => selected.style.backgroundColor = v)));
    panel.appendChild(colorSec);

    if (hasOwnText(selected)) {
      const typo = document.createElement('div');
      typo.className = 'gx-section';
      const th = document.createElement('h4'); th.textContent = 'Typography'; typo.appendChild(th);
      typo.appendChild(makeRow('font-size',      makeText(cs.fontSize,      v => selected.style.fontSize      = v)));
      typo.appendChild(makeRow('line-height',    makeText(cs.lineHeight,    v => selected.style.lineHeight    = v)));
      typo.appendChild(makeRow('letter-spacing', makeText(cs.letterSpacing, v => selected.style.letterSpacing = v)));
      typo.appendChild(makeRow('font-weight',    makeText(cs.fontWeight,    v => selected.style.fontWeight    = v)));
      panel.appendChild(typo);
    }

    const borderSec = document.createElement('div');
    borderSec.className = 'gx-section';
    const brh = document.createElement('h4'); brh.textContent = 'Border'; borderSec.appendChild(brh);
    const bw = parseFloat(cs.borderTopWidth) || 0;
    const bs = cs.borderTopStyle || 'none';
    const bc = cs.borderTopColor || 'rgb(0, 0, 0)';
    const styleSelect = makeSelect(bs, ['none', 'solid', 'dashed', 'dotted', 'double'], v => selected.style.borderStyle = v);
    borderSec.appendChild(makeRow('width', makeSlider(bw, 0, 50, 1, 'px', v => {
      selected.style.borderWidth = v + 'px';
      if (v > 0 && getComputedStyle(selected).borderTopStyle === 'none') {
        selected.style.borderStyle = 'solid';
        styleSelect.value = 'solid';
      }
    })));
    borderSec.appendChild(makeRow('style', styleSelect));
    borderSec.appendChild(makeRow('color', makeColor(bc, v => selected.style.borderColor = v)));
    panel.appendChild(borderSec);

    const box = document.createElement('div');
    box.className = 'gx-section';
    const bh = document.createElement('h4'); bh.textContent = 'Box'; box.appendChild(bh);
    box.appendChild(makeRow('radius',  makeText(cs.borderRadius, v => selected.style.borderRadius = v)));
    box.appendChild(makeRow('padding', makeText(cs.padding,      v => selected.style.padding      = v)));
    box.appendChild(makeRow('margin',  makeText(cs.margin,       v => selected.style.margin       = v)));
    panel.appendChild(box);

    const actions = document.createElement('div');
    actions.className = 'gx-actions';
    const copy = document.createElement('button');
    copy.type = 'button';
    copy.textContent = 'Copy CSS';
    copy.addEventListener('click', async () => {
      const sel = describe(selected);
      // unique CSS path so the element can be relocated even when `sel` matches multiple
      const segs = [];
      let cur = selected;
      while (cur && cur !== document.body && cur.nodeType === 1) {
        let s = cur.tagName.toLowerCase();
        if (cur.id) { s = '#' + cur.id; segs.unshift(s); break; }
        if (cur.className && typeof cur.className === 'string') {
          const cls = cur.className.trim().split(/\s+/).slice(0, 2).join('.');
          if (cls) s += '.' + cls;
        }
        if (cur.parentNode) {
          const same = [...cur.parentNode.children].filter(c => c.tagName === cur.tagName);
          if (same.length > 1) s += `:nth-of-type(${same.indexOf(cur) + 1})`;
        }
        segs.unshift(s);
        cur = cur.parentNode;
      }
      const path = segs.join(' > ');
      const text = (selected.textContent || '').trim().replace(/\s+/g, ' ');
      const textShort = text.length > 80 ? text.slice(0, 77) + '...' : text;
      const inline = (selected.getAttribute('style') || '')
        .split(';').map(s => s.trim()).filter(Boolean);
      const meta = '/* g-skill | ' + sel
        + (textShort ? ' | text: ' + JSON.stringify(textShort) : '')
        + ' | path: ' + path + ' */';
      const css = meta + '\n' + sel + ' {\n' + inline.map(s => '  ' + s + ';').join('\n') + '\n}';

      let ok = false;
      try { await navigator.clipboard.writeText(css); ok = true; } catch {}
      if (!ok) {
        const ta = document.createElement('textarea');
        ta.value = css;
        ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        try { ok = document.execCommand('copy'); } catch {}
        ta.remove();
      }
      if (!ok) {
        // Both APIs blocked (typically the user denied clipboard permission for this origin).
        // Show a manual-copy modal — pre-selected textarea, user presses ⌘C / Ctrl+C.
        const modal = document.createElement('div');
        modal.dataset.gToolsetModal = '1';
        modal.style.cssText = 'position:fixed;inset:0;z-index:10002;background:rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;font:12px/1.5 -apple-system,system-ui,sans-serif;';
        const inner = document.createElement('div');
        inner.style.cssText = 'background:#fff;color:#111;padding:14px;border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,0.3);width:480px;max-width:90vw;';
        const msg = document.createElement('div');
        msg.style.cssText = 'margin-bottom:8px;color:#333;font-size:12px;';
        msg.textContent = 'Browser blocked the clipboard. Press ⌘C / Ctrl+C to copy, then close.';
        const taM = document.createElement('textarea');
        taM.value = css;
        taM.style.cssText = 'width:100%;height:160px;box-sizing:border-box;font:11px/1.4 ui-monospace,Menlo,monospace;padding:8px;border:1px solid #ddd;border-radius:4px;color:#111;background:#f8f8f8;';
        const closeBtn = document.createElement('button');
        closeBtn.textContent = 'Close';
        closeBtn.style.cssText = 'margin-top:8px;padding:6px 12px;border:1px solid #ccc;background:#f6f6f6;border-radius:4px;cursor:pointer;font:11px/1.2 inherit;';
        const dismiss = () => modal.remove();
        closeBtn.addEventListener('click', dismiss);
        modal.addEventListener('click', (e) => { if (e.target === modal) dismiss(); });
        inner.appendChild(msg); inner.appendChild(taM); inner.appendChild(closeBtn);
        modal.appendChild(inner);
        document.body.appendChild(modal);
        taM.focus(); taM.select();
        ok = true; // user can copy manually
      }

      copy.textContent = ok ? '✓ Copied!' : 'Copy failed';
      copy.style.background = ok ? '#22c55e' : '#ef4444';
      copy.style.color = '#fff';
      copy.style.borderColor = ok ? '#22c55e' : '#ef4444';
      setTimeout(() => {
        copy.textContent = 'Copy CSS';
        copy.style.background = '';
        copy.style.color = '';
        copy.style.borderColor = '';
      }, 1500);
    });
    const reset = document.createElement('button');
    reset.type = 'button';
    reset.textContent = 'Reset';
    reset.addEventListener('click', () => {
      selected.removeAttribute('style');
      buildPanel();
      placeHighlight(selected);
    });
    actions.appendChild(copy);
    actions.appendChild(reset);
    panel.appendChild(actions);
  }

  function onMove(e) {
    if (!active) return;
    if (panelDrag) return;
    if (isOurUI(e.target)) { if (!selected) highlight.style.display = 'none'; return; }
    if (selected) return;
    placeHighlight(e.target);
  }

  function onClickCapture(e) {
    if (!active) return;
    if (isOurUI(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    if (selected === e.target) {
      selected = null;
      highlight.style.display = 'none';
      buildPanel();
      return;
    }
    selected = e.target;
    placeHighlight(selected);
    buildPanel();
  }

  function onMouseDownCapture(e) {
    if (!active) return;
    if (isOurUI(e.target)) return;
    e.preventDefault();
  }

  function activate() {
    active = true;
    overlay.classList.add('is-on');
    document.body.classList.add(BODY_CLASS);
    document.addEventListener('mousemove',  onMove,             true);
    document.addEventListener('mousedown',  onMouseDownCapture, true);
    document.addEventListener('click',      onClickCapture,     true);
  }

  function deactivate() {
    active = false;
    overlay.classList.remove('is-on');
    document.body.classList.remove(BODY_CLASS);
    document.removeEventListener('mousemove',  onMove,             true);
    document.removeEventListener('mousedown',  onMouseDownCapture, true);
    document.removeEventListener('click',      onClickCapture,     true);
    highlight.style.display = 'none';
    panel.style.display = 'none';
    selected = null;
  }

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'g' && e.key !== 'G') return;
    if (e.target.matches && e.target.matches('input, textarea, [contenteditable]')) return;
    active ? deactivate() : activate();
  });
})();
