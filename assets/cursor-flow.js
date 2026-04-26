import { prepareWithSegments, layoutNextLine } from "./pretext.js";

const SELECTOR = ".intro-text p, .intro-lead, .article-body p, .quote-text";
const CURSOR_RADIUS = 10;
const CURSOR_PAD_H = 18;
const CURSOR_PAD_V = 6;
const MIN_SLOT_WIDTH = 50;

function carveSlots(base, blocked) {
  let slots = [base];
  for (const iv of blocked) {
    const next = [];
    for (const s of slots) {
      if (iv.right <= s.left || iv.left >= s.right) { next.push(s); continue; }
      if (iv.left > s.left) next.push({ left: s.left, right: iv.left });
      if (iv.right < s.right) next.push({ left: iv.right, right: s.right });
    }
    slots = next;
  }
  return slots.filter(s => s.right - s.left >= MIN_SLOT_WIDTH);
}

function circleIntervalForBand(cx, cy, r, bandTop, bandBottom, hPad, vPad) {
  const top = bandTop - vPad;
  const bottom = bandBottom + vPad;
  if (top >= cy + r || bottom <= cy - r) return null;
  const minDy = cy >= top && cy <= bottom ? 0 : cy < top ? top - cy : cy - bottom;
  if (minDy >= r) return null;
  const maxDx = Math.sqrt(r * r - minDy * minDy);
  return { left: cx - maxDx - hPad, right: cx + maxDx + hPad };
}

function layoutColumn(prepared, regionW, lineHeight, maxLines, circle) {
  const lines = [];
  if (regionW < MIN_SLOT_WIDTH) return lines;
  let cursor = { segmentIndex: 0, graphemeIndex: 0 };
  let lineTop = 0;
  let iterations = 0;
  const iterationCap = maxLines * 4;
  while (lines.length < maxLines && iterations < iterationCap) {
    iterations++;
    const bandTop = lineTop;
    const bandBottom = lineTop + lineHeight;
    const blocked = [];
    if (circle) {
      const iv = circleIntervalForBand(circle.cx, circle.cy, circle.r, bandTop, bandBottom, CURSOR_PAD_H, CURSOR_PAD_V);
      if (iv !== null) blocked.push(iv);
    }
    const slots = carveSlots({ left: 0, right: regionW }, blocked);
    if (slots.length === 0) { lineTop += lineHeight; continue; }
    slots.sort((a, b) => a.left - b.left);
    let producedAny = false;
    for (const slot of slots) {
      const slotWidth = slot.right - slot.left;
      const line = layoutNextLine(prepared, cursor, slotWidth);
      if (line === null) return lines;
      lines.push({ x: Math.round(slot.left), y: Math.round(lineTop), text: line.text, width: line.width });
      cursor = line.end;
      producedAny = true;
    }
    lineTop += lineHeight;
    if (!producedAny) break;
  }
  return lines;
}

const blocks = [];

function fontString(cs) {
  return `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
}

function prepareBlock(el) {
  const cs = getComputedStyle(el);
  const font = fontString(cs);
  const lineHeight = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4;
  const text = el.textContent.replace(/\s+/g, " ").trim();
  if (!text) return null;
  const prepared = prepareWithSegments(text, font);
  el.textContent = "";
  el.style.position = "relative";
  const layer = document.createElement("span");
  layer.className = "flow-layer";
  layer.style.cssText = "display:block; position:relative; width:100%;";
  el.appendChild(layer);
  return { el, layer, prepared, font, lineHeight, text, lines: [], naturalHeight: 0, width: 0 };
}

function sizeBlock(b) {
  const rect = b.el.getBoundingClientRect();
  b.width = rect.width;
}

function reflow(b, cursor) {
  const cs = getComputedStyle(b.el);
  const font = fontString(cs);
  if (font !== b.font) {
    b.font = font;
    b.prepared = prepareWithSegments(b.text, font);
  }
  b.lineHeight = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4;
  const rect = b.el.getBoundingClientRect();
  b.width = rect.width;
  let relCursor = null;
  if (cursor) {
    const cx = cursor.x - rect.left;
    const cy = cursor.y - rect.top;
    if (cx > -CURSOR_RADIUS && cx < rect.width + CURSOR_RADIUS && cy > -CURSOR_RADIUS && cy < rect.height + CURSOR_RADIUS * 2) {
      relCursor = { cx, cy, r: CURSOR_RADIUS };
    }
  }
  const maxLines = 400;
  const lines = layoutColumn(b.prepared, b.width, b.lineHeight, maxLines, relCursor);
  while (b.layer.childElementCount < lines.length) {
    const s = document.createElement("span");
    s.className = "flow-line";
    s.style.cssText = "position:absolute; white-space:pre; top:0; left:0; will-change:transform;";
    b.layer.appendChild(s);
  }
  while (b.layer.childElementCount > lines.length) {
    b.layer.lastChild.remove();
  }
  const children = b.layer.children;
  for (let i = 0; i < lines.length; i++) {
    const L = lines[i];
    const c = children[i];
    c.style.transform = `translate(${L.x}px, ${L.y}px)`;
    if (c.textContent !== L.text) c.textContent = L.text;
  }
  const h = lines.length ? lines[lines.length - 1].y + b.lineHeight : b.lineHeight;
  b.layer.style.height = h + "px";
}

function init() {
  const els = document.querySelectorAll(SELECTOR);
  els.forEach(el => {
    const b = prepareBlock(el);
    if (b) {
      sizeBlock(b);
      blocks.push(b);
      reflow(b, null);
    }
  });
}

let pending = false;
let lastCursor = null;
function schedule() {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => {
    pending = false;
    for (const b of blocks) reflow(b, lastCursor);
  });
}

window.addEventListener("pointermove", (e) => {
  lastCursor = { x: e.clientX, y: e.clientY };
  schedule();
}, { passive: true });

window.addEventListener("pointerleave", () => {
  lastCursor = null;
  schedule();
}, { passive: true });

let resizeT;
window.addEventListener("resize", () => {
  clearTimeout(resizeT);
  resizeT = setTimeout(() => { for (const b of blocks) reflow(b, lastCursor); }, 100);
});

if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(init);
} else {
  init();
}
