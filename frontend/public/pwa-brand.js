// Iter 215bx — swap the PWA manifest + apple-touch-icon to the Pulse Fitness
// brand when the user is on a /pulse route, so "Add to Home Screen" installs
// with the right icon, name, and theme. Externalised from index.html (CSP
// hardening — removes the last inline <script> so script-src can drop
// 'unsafe-inline'). Runs synchronously (render-blocking) before the SW registers.
(function () {
  try {
    var path = location.pathname.toLowerCase();
    var m = document.getElementById('app-manifest');
    var t = document.getElementById('apple-app-title');
    var i = document.getElementById('apple-touch-icon');
    if (path.startsWith('/pulse')) {
      if (m) m.setAttribute('href', '/manifest-pulse.json');
      if (t) t.setAttribute('content', 'Pulse Fitness');
      if (i) i.setAttribute('href', "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 180 180'><rect width='180' height='180' rx='40' fill='%231B1C1D'/><text x='50%25' y='56%25' dominant-baseline='middle' text-anchor='middle' font-family='sans-serif' font-weight='700' font-size='100' fill='%2319CDFF'>P</text></svg>");
      document.documentElement.setAttribute('data-brand', 'pulse');
      document.body && document.body.setAttribute('data-brand', 'pulse');
    } else if (path.startsWith('/service-desk')) {
      // Iter 275 — Service Desk PWA: install with the orange Service Desk
      // icon/name, launching to /service-desk.
      if (m) m.setAttribute('href', '/manifest-servicedesk.json');
      if (t) t.setAttribute('content', 'Service Desk');
      if (i) i.setAttribute('href', "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 180 180'><rect width='180' height='180' rx='40' fill='%23f97316'/><path d='M56 106 v-8 a34 34 0 0 1 68 0 v8' fill='none' stroke='%23ffffff' stroke-width='12' stroke-linecap='round'/><rect x='45' y='102' width='19' height='34' rx='8' fill='%23ffffff'/><rect x='116' y='102' width='19' height='34' rx='8' fill='%23ffffff'/></svg>");
      document.documentElement.setAttribute('data-brand', 'servicedesk');
    }
  } catch (_) { /* best-effort */ }
})();
