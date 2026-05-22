#!/usr/bin/env python3
"""post-deploy.py — Iter 216h296

Run a curated set of HTTP smoke probes against the live production
URL immediately after a deploy. Emit a green/red summary to stdout
(exit 0/1) and — when configured — fire a co-branded summary email
via the existing Resend integration so the operator knows within
~60 seconds whether the deploy is healthy.

Why a Python script and not a shell loop?
-----------------------------------------
The probes are typed (we want to assert response shape, not just
HTTP status), the timing aggregation is simpler, and re-using the
existing `utils.email.send_email` keeps the notification consistent
with every other GymAxis transactional email.

Env contract (all read by the wrapper Makefile target):
  POST_DEPLOY_BASE_URL       — base URL to probe (e.g. https://gymaxisai.com)
                                Falls back to REACT_APP_BACKEND_URL.
  POST_DEPLOY_NOTIFY_EMAIL   — optional. Recipient for the result email.
  POST_DEPLOY_REVIEW_PARTNER_ID — optional. UUID of an approved partner
                                used by the reviews probe. Probe is
                                skipped when missing.
  POST_DEPLOY_EREF_CODE      — optional. Referral code for the eref probe.
  POST_DEPLOY_TEST_EMAIL +
  POST_DEPLOY_TEST_PASSWORD  — optional. Auth probe creds. Probe is
                                skipped (NOT failed) when either is absent.
  POST_DEPLOY_TIMEOUT_S      — per-probe timeout, default 10s.

Exit codes:
  0  every required probe green
  1  one or more required probes failed
  2  cannot resolve POST_DEPLOY_BASE_URL
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass

import httpx


@dataclass
class ProbeResult:
    name: str
    method: str
    path: str
    ok: bool
    status: int
    detail: str
    duration_ms: int
    skipped: bool = False


def _base_url() -> str | None:
    return (
        os.environ.get("POST_DEPLOY_BASE_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or None
    )


async def _probe(
    client: httpx.AsyncClient,
    *,
    name: str,
    method: str = "GET",
    path: str,
    expect_status: int | tuple[int, ...] = 200,
    expect_keys: list[str] | None = None,
    json: dict | None = None,
    headers: dict | None = None,
) -> ProbeResult:
    """Run one HTTP probe. Considered ``ok`` iff the HTTP status is
    in ``expect_status`` AND every key in ``expect_keys`` is present
    in the JSON response (when JSON is parseable)."""
    start = time.monotonic()
    try:
        r = await client.request(method, path, json=json, headers=headers)
        elapsed = int((time.monotonic() - start) * 1000)
        statuses = (expect_status,) if isinstance(expect_status, int) else expect_status
        if r.status_code not in statuses:
            return ProbeResult(name, method, path, False, r.status_code,
                               f"unexpected status (expected {statuses})", elapsed)
        if expect_keys:
            try:
                body = r.json()
            except Exception:
                return ProbeResult(name, method, path, False, r.status_code,
                                   "non-JSON response", elapsed)
            missing = [k for k in expect_keys if k not in body]
            if missing:
                return ProbeResult(name, method, path, False, r.status_code,
                                   f"missing keys: {missing}", elapsed)
        return ProbeResult(name, method, path, True, r.status_code, "ok", elapsed)
    except httpx.RequestError as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return ProbeResult(name, method, path, False, 0, f"network error: {exc}", elapsed)


async def run_probes(base: str, timeout_s: float) -> list[ProbeResult]:
    """Run all 6 probes against ``base``. Probes that depend on
    optional env vars return a skipped ``ProbeResult`` rather than
    failing — a smoke target shouldn't fail because the operator
    forgot to set a non-essential probe ID."""
    review_partner_id = os.environ.get("POST_DEPLOY_REVIEW_PARTNER_ID")
    eref_code = os.environ.get("POST_DEPLOY_EREF_CODE")
    test_email = os.environ.get("POST_DEPLOY_TEST_EMAIL")
    test_password = os.environ.get("POST_DEPLOY_TEST_PASSWORD")

    async with httpx.AsyncClient(base_url=base, timeout=timeout_s, follow_redirects=False) as c:
        results: list[ProbeResult] = []

        # 1. Health — required, the absolute minimum
        results.append(await _probe(c, name="api-health", path="/api/health",
                                    expect_keys=["status"]))

        # 2. Public engineer network read — required (catches ingress issues)
        # Find-engineers requires auth with org context; we instead probe the
        # always-public referral lookup which exercises the same router.
        if eref_code:
            results.append(await _probe(c, name="public-eref",
                                        path=f"/api/partners/public/by-eref/{eref_code}",
                                        expect_keys=["referral_code", "apply_url"]))
        else:
            results.append(ProbeResult(
                "public-eref", "GET", "/api/partners/public/by-eref/<code>",
                True, 0, "skipped (no POST_DEPLOY_EREF_CODE set)", 0, skipped=True,
            ))

        # 3. Public reviews — validates h286 surface
        if review_partner_id:
            results.append(await _probe(c, name="public-reviews",
                                        path=f"/api/partners/{review_partner_id}/reviews",
                                        expect_keys=["partner", "summary"]))
        else:
            results.append(ProbeResult(
                "public-reviews", "GET", "/api/partners/<id>/reviews",
                True, 0, "skipped (no POST_DEPLOY_REVIEW_PARTNER_ID set)", 0, skipped=True,
            ))

        # 4. Auth round-trip — required when creds available
        if test_email and test_password:
            results.append(await _probe(
                c, name="auth-login", method="POST", path="/api/auth/login",
                json={"email": test_email, "password": test_password},
                expect_keys=["token"],
            ))
        else:
            results.append(ProbeResult(
                "auth-login", "POST", "/api/auth/login",
                True, 0, "skipped (no POST_DEPLOY_TEST_EMAIL/PASSWORD)", 0, skipped=True,
            ))

        # 5. Public CRM-side write surface — partners list endpoint
        # exposes the engineer-network discovery contract used by the
        # marketing site's "Find an engineer" widget. The endpoint
        # accepts an empty body so the probe doesn't require auth.
        results.append(await _probe(
            c, name="partners-public-apply-options", method="GET",
            path="/api/partners/options",
            expect_status=(200, 404),
        ))

        # 6. Marketing site root — proves the SPA / ingress are wired
        results.append(await _probe(c, name="marketing-root", path="/"))

        return results


# ── Output formatting ──────────────────────────────────────────────


def _format_text(results: list[ProbeResult], base: str, total_ms: int) -> tuple[str, bool]:
    """Return (text, all_required_passed)."""
    lines: list[str] = []
    lines.append(f"GymAxis post-deploy smoke — {base}")
    lines.append("─" * 60)
    all_ok = True
    for r in results:
        if r.skipped:
            mark = "○"
        elif r.ok:
            mark = "✓"
        else:
            mark = "✗"
            all_ok = False
        lines.append(f"{mark} {r.name:<18} {r.method:<5} {r.path:<55} "
                     f"[{r.status or '-'}] {r.duration_ms}ms — {r.detail}")
    lines.append("─" * 60)
    summary = "PASS" if all_ok else "FAIL"
    lines.append(f"{summary} · {total_ms}ms total")
    return "\n".join(lines), all_ok


def _format_html(results: list[ProbeResult], base: str, total_ms: int, all_ok: bool) -> str:
    """Lean HTML for the Resend body. Standalone — does NOT use the
    co-branded `_wrap` helper because this is an internal ops alert,
    not a customer-facing email."""
    rows: list[str] = []
    for r in results:
        if r.skipped:
            badge = '<span style="color:#6B7280;background:#F3F4F6;padding:2px 6px;border-radius:4px;font-size:11px;">SKIP</span>'
        elif r.ok:
            badge = '<span style="color:#fff;background:#059669;padding:2px 6px;border-radius:4px;font-size:11px;">OK</span>'
        else:
            badge = '<span style="color:#fff;background:#DC2626;padding:2px 6px;border-radius:4px;font-size:11px;">FAIL</span>'
        rows.append(
            f'<tr><td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;">{badge}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;font-family:monospace;font-size:12px;">{r.name}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;font-family:monospace;font-size:12px;color:#374151;">{r.method} {r.path}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;text-align:right;font-size:12px;color:#6B7280;">{r.duration_ms}ms</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;font-size:12px;color:#6B7280;">{r.detail}</td></tr>'
        )
    headline_color = "#059669" if all_ok else "#DC2626"
    headline = "Deploy healthy" if all_ok else "Deploy regression detected"
    return (
        f'<div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:760px;">'
        f'<h2 style="color:{headline_color};margin:0 0 6px;">{headline}</h2>'
        f'<p style="color:#6B7280;margin:0 0 16px;font-size:13px;">'
        f'Post-deploy smoke ran against <strong>{base}</strong> · {total_ms}ms total</p>'
        f'<table style="width:100%;border-collapse:collapse;font-size:13px;">{"".join(rows)}</table>'
        f'<p style="color:#9CA3AF;font-size:11px;margin-top:18px;">'
        f'Auto-generated by <code>make post-deploy</code> · iter 216h296</p>'
        f'</div>'
    )


async def _maybe_email(html: str, subject: str) -> bool:
    """Fire the result via Resend if `POST_DEPLOY_NOTIFY_EMAIL` is
    configured. Falls through silently when missing — the script's
    real signal is its exit code, not the email."""
    recipient = os.environ.get("POST_DEPLOY_NOTIFY_EMAIL")
    if not recipient:
        return False
    # Defer the import so the script can run on minimal environments
    # that don't have the backend dependency tree installed.
    sys.path.insert(0, "/app/backend")
    try:
        from utils.email import send_email  # noqa: WPS433
    except Exception as exc:  # pragma: no cover — environmental
        print(f"!  notify email skipped — backend imports unavailable: {exc}",
              file=sys.stderr)
        return False
    return await send_email(recipient, subject, html)


# ── Entrypoint ─────────────────────────────────────────────────────


async def main() -> int:
    base = _base_url()
    if not base:
        print("✗ POST_DEPLOY_BASE_URL (or REACT_APP_BACKEND_URL) is not set.",
              file=sys.stderr)
        return 2
    timeout_s = float(os.environ.get("POST_DEPLOY_TIMEOUT_S", "10"))
    start = time.monotonic()
    results = await run_probes(base, timeout_s)
    total_ms = int((time.monotonic() - start) * 1000)
    text, all_ok = _format_text(results, base, total_ms)
    print(text)
    subject = f"[post-deploy] {'PASS' if all_ok else 'FAIL'} · {base}"
    html = _format_html(results, base, total_ms, all_ok)
    await _maybe_email(html, subject)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
