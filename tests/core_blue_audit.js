() => {
  // Core-Blue text audit: dark blue (#0091CA) must sit on light bg; bright (#19CDFF) text on light bg is a miss.
  const parse = (s) => { const m = s && s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const grad = (bi) => (bi && bi !== 'none' ? (bi.match(/rgba?\([^)]+\)/g) || []).map(parse) : []);
  const effBg = (el) => {
    let e = el;
    while (e && e.nodeType === 1) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage.includes('url(')) return { img: true, r: 0, g: 0, b: 0 };
      const gc = grad(cs.backgroundImage).filter(c => c.a > 0.5);
      if (gc.length) return gc[0];
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0.5) return c;
      e = e.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  };
  const sel = (el) => {
    const t = el.closest('[data-testid]');
    const cls = (el.className && typeof el.className === 'string') ? '.' + el.className.trim().split(/\s+/).slice(0, 4).join('.') : '';
    return (t ? `[data-testid="${t.getAttribute('data-testid')}"] ` : '') + el.tagName.toLowerCase() + cls;
  };
  const vis = (el) => { const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false; const cs = getComputedStyle(el); return cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.1; };
  const dark = [], bright = [], ok = { darkOnLight: 0, brightOnDark: 0 };
  const near = (c, r, g, b) => c && Math.abs(c.r - r) < 4 && Math.abs(c.g - g) < 4 && Math.abs(c.b - b) < 4;
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const cs = getComputedStyle(el);
    const direct = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    const isSvg = ['svg', 'path'].includes(el.tagName.toLowerCase());
    if (!direct && !isSvg) continue;
    const fg = parse(isSvg ? (cs.stroke !== 'none' ? cs.stroke : cs.fill) : cs.color);
    if (!fg) continue;
    if (isSvg && el.tagName.toLowerCase() === 'path') continue;
    const bg = effBg(el);
    const L = lum(bg);
    if (near(fg, 0, 145, 202)) {
      if (L < 0.2 || bg.img) dark.push({ sel: sel(el), text: direct.slice(0, 40), bg: `rgb(${bg.r},${bg.g},${bg.b})${bg.img ? ' img' : ''}`, ratio: +ratio(fg, bg).toFixed(2) });
      else ok.darkOnLight++;
    } else if (near(fg, 25, 205, 255)) {
      if (L > 0.5 && !bg.img && !isSvg) bright.push({ sel: sel(el), text: direct.slice(0, 40), bg: `rgb(${bg.r},${bg.g},${bg.b})`, ratio: +ratio(fg, bg).toFixed(2) });
      else ok.brightOnDark++;
    }
  }
  return { url: location.pathname + location.search, theme: document.documentElement.getAttribute('data-theme'), ok, darkBlueOnDark: dark.slice(0, 30), darkCount: dark.length, brightOnLight: bright.slice(0, 30), brightCount: bright.length };
}
