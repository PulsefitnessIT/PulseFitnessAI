# CDN / Edge Infrastructure Notes

This document lists the **one** server-side infrastructure change that cannot
be made from inside the application code — it must be configured on the
Emergent / Cloudflare edge layer.

---

## 1. `/api/security/manifest` cache

**Current state (preview + production):**
- The FastAPI route sets:
  ```
  Cache-Control: public, max-age=300, s-maxage=600
  CDN-Cache-Control: public, max-age=600
  Surrogate-Control: public, max-age=600
  ```
- Cloudflare's default config strips all of these and responds to the
  client with `Cache-Control: no-store, no-cache, must-revalidate`,
  regardless of what the origin sent.
- We confirm this by inspecting the live response header:
  ```
  cf-cache-status: DYNAMIC     ← Cloudflare is not caching, even though
                                  the origin explicitly allowed it.
  ```

**What's needed in Cloudflare:**
- Add a **Page Rule** (or **Cache Rule** on newer plans) for
  `*maintenance-hub-357.preview.emergentagent.com/api/security/manifest`
  with:
  - *Cache Level*: `Cache Everything`
  - *Edge Cache TTL*: `5 minutes` (or "Respect existing headers" if
    the tier supports it — CF will then honour our `CDN-Cache-Control`).
  - *Origin Cache Control*: `On`.

**Mitigations already in place (no infra change needed):**
- Frontend uses **sessionStorage cache (5 min TTL)** in both `SecurityPage.js`
  and `HomePage.js` → avoids the network hop entirely for repeat navigation
  within a session.
- Service worker (`sw.js`) caches the response for offline support.
- The manifest itself is lightweight (< 1 KB gzipped), so even uncached the
  hit is ~60 ms.

**Impact of NOT fixing this:** minimal. A user opening `/security` or
`/` twice in a session now pays zero network cost for the manifest.
Only a first-time visitor on a cold browser cache sees the original
cost.

**Who owns this:** Emergent infra team. Flag as a low-priority ticket.

---

## 2. Expected future edge rules (for reference)

When setting up Cloudflare rules for production, the following routes
SHOULD be cached at the edge:

| Route | Rule | TTL |
|---|---|---|
| `/api/security/manifest` | Cache Everything | 5 min |
| `/api/captcha/config` | Cache Everything | 10 min |
| `/static/**` (CRA build output) | Cache Everything + immutable | 1 year |
| `/pulse-photos/**.webp` | Cache Everything | 1 year |
| `/fonts/**.otf` | Cache Everything | 1 year |

All other `/api/*` routes MUST remain `no-store` (they contain
per-request or per-user data).
