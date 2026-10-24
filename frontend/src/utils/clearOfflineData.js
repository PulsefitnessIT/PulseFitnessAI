// Remove offline copies of signed-in data (service-worker API cache, MOD/BFPO
// outbox + saved photos) so the next person on a shared device can't read them.
const OFFLINE_KEY_PREFIXES = ['bfpo_outbox', 'bfpo_blob_'];

export async function clearOfflineData() {
  try {
    Object.keys(localStorage)
      .filter((k) => OFFLINE_KEY_PREFIXES.some((p) => k.startsWith(p)))
      .forEach((k) => localStorage.removeItem(k));
  } catch { /* storage unavailable */ }
  try {
    if (typeof caches !== 'undefined') {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k.includes('-api-')).map((k) => caches.delete(k)));
    }
  } catch { /* cache API unavailable */ }
}
