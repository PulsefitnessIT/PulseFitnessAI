"""SSRF guard — Iter 220aw / F-26.

Block any outbound URL fetch that resolves to an internal address.
Used by every server-side URL fetcher (Companies House lookup, AI URL
summariser, public-widget remote-image proxy, OG-image scraper, etc.)
to defeat the OWASP API10 Server-Side Request Forgery attack family.

Rejected destinations:

  * Schemes other than ``http`` / ``https``
  * Hostnames that resolve to RFC1918 (10/8, 172.16/12, 192.168/16)
  * Loopback / localhost (127/8, ::1)
  * Link-local incl. AWS / GCP IMDS (169.254.169.254, fe80::/10)
  * Multicast (224/4, ff00::/8) + reserved + unspecified
  * Literal-IP URLs that fall in any of the above
  * Userinfo-bearing URLs (``http://attacker@evil.example``)
  * Embedded ports < 1 or > 65535
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
from typing import Iterable
from urllib.parse import urlparse

from fastapi import HTTPException

log = logging.getLogger(__name__)


# Explicit additional denylist (one host per env entry, comma-separated).
# Use this to forbid e.g. ``metadata.google.internal`` even though it
# wouldn't resolve to a private CIDR in every Kubernetes setup.
_EXTRA_DENYLIST_HOSTS = frozenset(
    h.strip().lower()
    for h in (os.environ.get("SSRF_EXTRA_DENYLIST_HOSTS", "metadata.google.internal,metadata,169.254.169.254") or "").split(",")
    if h.strip()
)

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class SSRFBlocked(HTTPException):
    """Raised when an outbound URL is rejected for SSRF reasons."""

    def __init__(self, detail: str):
        super().__init__(status_code=400, detail=detail)


def _ip_is_dangerous(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified,
    )


def _resolve_all(host: str) -> list[str]:
    """DNS-resolve ``host`` to every A / AAAA. Idempotent and bounded
    by the standard 5-second socket timeout on the caller side."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFBlocked(f"DNS resolution failed for {host!r}: {exc}") from exc
    seen: set[str] = set()
    out: list[str] = []
    for info in infos:
        sockaddr = info[4]
        ip = sockaddr[0]
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out


def is_safe_external_url(url: str | None) -> bool:
    """Return True when ``url`` is safe to fetch from server-side code.

    Performs the full check chain. Use ``assert_safe_external_url``
    when you want the precise rejection reason in the response body.
    """
    try:
        assert_safe_external_url(url)
        return True
    except HTTPException:
        return False
    except Exception:  # noqa: BLE001 — defensive
        return False


def assert_safe_external_url(url: str | None) -> None:
    """Raise SSRFBlocked when ``url`` is unsafe to fetch.

    Idempotent + cheap (single DNS lookup). Callers should invoke this
    BEFORE handing ``url`` to httpx / requests / aiohttp.
    """
    if not url or not isinstance(url, str):
        raise SSRFBlocked("URL is required.")
    if len(url) > 2048:
        raise SSRFBlocked("URL is too long (>2048 chars).")
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise SSRFBlocked(f"URL is malformed: {exc}") from exc
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise SSRFBlocked(f"Scheme {scheme!r} not allowed; only http/https.")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise SSRFBlocked("URL has no hostname.")
    if parsed.username or parsed.password:
        raise SSRFBlocked("URLs with credentials are not allowed.")
    # Port sanity.
    port = parsed.port
    if port is not None and (port < 1 or port > 65535):
        raise SSRFBlocked(f"URL port {port} out of range.")
    # Explicit host denylist (covers DNS-rebind-resistant magic names
    # like ``metadata.google.internal`` that the IP check alone misses).
    if host in _EXTRA_DENYLIST_HOSTS:
        raise SSRFBlocked(f"Host {host!r} is on the SSRF denylist.")

    # Literal-IP host? Check directly without DNS.
    try:
        ip_obj = ipaddress.ip_address(host)
        if _ip_is_dangerous(ip_obj):
            raise SSRFBlocked(
                f"URL resolves to a non-public IP ({host}) — refused.",
            )
        return
    except ValueError:
        pass

    # DNS-resolve and check every returned address.
    addrs = _resolve_all(host)
    if not addrs:
        raise SSRFBlocked(f"DNS resolution for {host!r} returned no addresses.")
    for addr in addrs:
        try:
            ip_obj = ipaddress.ip_address(addr)
        except ValueError:
            raise SSRFBlocked(f"Unparseable IP {addr!r} for host {host!r}.")
        if _ip_is_dangerous(ip_obj):
            raise SSRFBlocked(
                f"Host {host!r} resolves to a non-public IP ({addr}) — refused.",
            )


def assert_safe_urls(urls: Iterable[str | None]) -> None:
    """Convenience wrapper to validate a batch of URLs up-front."""
    for u in urls:
        assert_safe_external_url(u)


__all__ = [
    "SSRFBlocked",
    "is_safe_external_url",
    "assert_safe_external_url",
    "assert_safe_urls",
]
