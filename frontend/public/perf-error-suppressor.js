// Suppress a noisy, harmless PerformanceServerTiming DataCloneError that some
// browsers throw when structured-cloning performance entries. Externalised
// from index.html for CSP hardening (no inline scripts → script-src can drop
// 'unsafe-inline'). Must run early to catch the error during startup.
window.addEventListener("error", function (e) {
  if (e.error instanceof DOMException && e.error.name === "DataCloneError" && e.message && e.message.includes("PerformanceServerTiming")) {
    e.stopImmediatePropagation();
    e.preventDefault();
  }
}, true);
