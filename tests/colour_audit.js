() => {
  const parse = (s) => {
    const m = s && s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const hsl = (c) => {
    let r = c.r / 255, g = c.g / 255, b = c.b / 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b); let h = 0, s = 0; const l = (mx + mn) / 2;
    if (mx !== mn) { const d = mx - mn; s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
      if (mx === r) h = (g - b) / d + (g < b ? 6 : 0); else if (mx === g) h = (b - r) / d + 2; else h = (r - g) / d + 4; h *= 60; }
    return { h, s: s * 100, l: l * 100 };
  };
  const offBrand = (c) => {
    if (!c || c.a < 0.25) return null;
    const { h, s, l } = hsl(c);
    if (s < 18 || l < 8 || l > 96) return null;
    if (h >= 205 && h < 250) return 'navy/indigo';
    if (h >= 250 && h < 290) return 'purple/violet';
    if (h >= 290 && h < 345) return 'pink/magenta';
    if (h >= 12 && h < 30 && s > 40) return 'orange';
    if (h >= 160 && h < 186) return 'teal';
    return null;
  };
  const isStatus = (c) => { if (!c) return false; const { h, s } = hsl(c); return s > 30 && (h < 12 || h >= 345 || (h >= 30 && h < 55) || (h >= 85 && h < 160)); };
  const gradColours = (bi) => (bi && bi !== 'none' ? (bi.match(/rgba?\([^)]+\)/g) || []).map(parse) : []);
  const effBg = (el) => {
    let e = el;
    while (e && e.nodeType === 1) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage.includes('url(')) return { img: true };
      const gc = gradColours(cs.backgroundImage);
      if (gc.length) return gc[0];
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0.5) return c;
      e = e.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  };
  const sel = (el) => {
    let s = el.tagName.toLowerCase();
    const t = el.closest('[data-testid]');
    const cls = (el.className && typeof el.className === 'string') ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '';
    return (t ? `[data-testid="${t.getAttribute('data-testid')}"] ` : '') + s + cls;
  };
  const vis = (el) => { const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false; const cs = getComputedStyle(el); return cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.1; };
  const low = [], off = [];
  const seenL = new Set(), seenO = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'DEFS', 'LINEARGRADIENT', 'STOP'].includes(el.tagName.toUpperCase())) continue;
    if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') {}
    if (!vis(el)) continue;
    const cs = getComputedStyle(el);
    const direct = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (direct.length > 0 && !el.closest('[aria-hidden="true"]')) {
      const fg = parse(cs.color); const bg = effBg(el);
      if (fg && !bg.img) {
        const fgc = fg.a < 1 ? { r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a) } : fg;
        const cr = ratio(fgc, bg);
        if (cr < 2.6) { const k = sel(el) + direct.slice(0, 20); if (!seenL.has(k)) { seenL.add(k); low.push({ sel: sel(el), text: direct.slice(0, 40), fg: cs.color, bg: `rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})`, ratio: +cr.toFixed(2) }); } }
      }
    }
    const checks = [['color', direct.length ? parse(cs.color) : null], ['bg', parse(cs.backgroundColor)],
      ['border', parseFloat(cs.borderTopWidth) > 0 ? parse(cs.borderTopColor) : null]];
    gradColours(cs.backgroundImage).forEach(g => checks.push(['gradient', g]));
    if (['svg', 'path', 'circle', 'rect', 'line', 'polyline'].includes(el.tagName.toLowerCase())) { checks.push(['fill', parse(cs.fill)]); checks.push(['stroke', parse(cs.stroke)]); }
    for (const [prop, c] of checks) {
      const ob = offBrand(c);
      if (ob) { const k = sel(el) + prop + ob; if (!seenO.has(k)) { seenO.add(k); off.push({ sel: sel(el), prop, kind: ob, val: `rgb(${c.r},${c.g},${c.b})`, text: direct.slice(0, 30) }); } }
    }
  }
  return { url: location.pathname, low: low.slice(0, 25), lowCount: low.length, off: off.slice(0, 25), offCount: off.length };
}
