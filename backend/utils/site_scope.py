"""Centralised per-request site-scope engine (multi-site data isolation).

This is the SINGLE source of truth for site-level RBAC across the
**Memberships, CRM, Marketing and Operations/Equipment** modules — all
now read the same source of truth: ``users.allowed_site_ids`` + the
``sites`` collection. (Operations/Equipment reach it via
``utils.mod_scope.resolve_mod_query_filter``, which delegates its
non-MOD branch to :func:`build_site_filter`; the legacy
``utils.auth.apply_site_lock`` is retired for route use.)

How it works
------------
1. Every auth dependency that can reach an isolated module's data calls
   :func:`set_request_site_scope` (or :func:`set_request_site_scope_from`)
   exactly once per request. This stamps a :class:`SiteScope` onto a
   ``ContextVar`` for the lifetime of the request.
2. Every list / dashboard / aggregate / create endpoint in the three
   modules calls :func:`build_site_filter` to obtain the Mongo filter
   fragment — never a bare ``{"site_id": x}``.

RBAC rules (enforced centrally in :func:`build_site_filter`)
------------------------------------------------------------
* A user is **restricted** only when they are NOT privileged AND carry a
  non-empty ``allowed_site_ids``. Privileged = owner / org-owner /
  master / platform / Pulse admin — these are *never* restricted. A
  manager with an empty ``allowed_site_ids`` is unrestricted (opt-in via
  assignment; nobody is locked out of everything by default).
* Specific site requested:
    - restricted & site ∉ allowed  → HTTP 403 ``site_access_denied``
    - else                         → ``{"site_id": site_id}``
* "All sites" / no site requested:
    - privileged   → ``{}`` (everything in their org)
    - restricted   → ``{"site_id": {"$in": allowed}}`` (narrowed)

.. warning::
   If the app grows another auth dependency that can reach an isolated
   module's data, it MUST call :func:`set_request_site_scope`. Forgetting
   this is the classic data-leak: an unset scope defaults to *unrestricted*
   so a restricted user would silently see every site.
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException, Query, Request

# Roles / flags that are NEVER site-restricted. Kept deliberately in sync
# with utils.auth.apply_site_lock's privileged set (minus "manager" — the
# whole point of this engine is that managers ARE restrictable).
_PRIVILEGED_ROLES = frozenset({"owner", "master_admin", "master", "pulse_master_admin"})


@dataclass
class SiteScope:
    """The resolved site scope for the current request."""
    restricted: bool = False
    allowed: list[str] = field(default_factory=list)


# default=None lets us detect (and, in tests, assert) that an auth path
# populated the scope. ``build_site_filter`` treats None as unrestricted
# but every isolated-module auth dependency sets it explicitly.
_site_scope_ctx: contextvars.ContextVar[Optional[SiteScope]] = contextvars.ContextVar(
    "site_scope", default=None,
)

# The site explicitly requested for THIS request (via X-Site-Id header or a
# ?site_id= param), resolved by the auth dependency. None = "All sites".
_requested_site_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "requested_site", default=None,
)

_ALL_SENTINELS = {"", "all", "all_sites", "all-sites", "null", "undefined", "none"}


def set_requested_site(site_id: Optional[str]) -> None:
    """Stash the request's active site (from X-Site-Id / ?site_id=). Called
    by the auth dependencies so header-driven endpoints (e.g. CRM, which
    scope via the shared ``_org_filter``) honour the active site + RBAC."""
    sid = (site_id or "").strip()
    _requested_site_ctx.set(None if sid.lower() in _ALL_SENTINELS else sid)


def get_requested_site() -> Optional[str]:
    return _requested_site_ctx.get()


def effective_site_filter() -> dict:
    """Site filter for the request's active site (header/param driven),
    enforcing RBAC. Use in shared org-filter helpers that don't take an
    explicit site_id argument (CRM)."""
    return build_site_filter(_requested_site_ctx.get())


def _is_privileged(user: dict) -> bool:
    if not user:
        return False
    if user.get("is_master_admin") or user.get("is_pulse_admin") or user.get("is_org_owner"):
        return True
    return (user.get("role") or "").lower() in _PRIVILEGED_ROLES


def set_request_site_scope(user: dict) -> SiteScope:
    """Resolve + stash the site scope for ``user`` on the request context.

    Returns the resolved :class:`SiteScope` (handy for tests / logging).
    Call this from every auth dependency that reaches isolated data.
    """
    allowed = [str(s) for s in (user.get("allowed_site_ids") or []) if s]
    restricted = bool(allowed) and not _is_privileged(user)
    scope = SiteScope(restricted=restricted, allowed=allowed)
    _site_scope_ctx.set(scope)
    return scope


def set_request_site_scope_from(*, role: Optional[str], allowed_site_ids,
                                is_privileged: bool = False) -> SiteScope:
    """Lower-level variant for auth paths that don't hold a full user dict
    (e.g. a secondary token type). Mirror ``role`` + ``allowed_site_ids``
    from the primary user record before calling this."""
    return set_request_site_scope({
        "role": role,
        "allowed_site_ids": allowed_site_ids or [],
        "is_org_owner": is_privileged,
    })


def clear_request_site_scope() -> None:
    _site_scope_ctx.set(None)
    _requested_site_ctx.set(None)


def get_request_site_scope() -> SiteScope:
    """Return the current request's scope (unrestricted default)."""
    return _site_scope_ctx.get() or SiteScope(restricted=False, allowed=[])


def build_site_filter(site_id: Optional[str] = None) -> dict:
    """Return the Mongo filter FRAGMENT for the requested site, enforcing
    RBAC against the current request scope.

    Merge the result into your existing org filter, e.g.::

        q = {"organization_id": org_id, **build_site_filter(site_id)}

    Raises 403 ``site_access_denied`` when a restricted user asks for a
    site outside their allow-list.
    """
    scope = get_request_site_scope()
    site_id = (site_id or "").strip() or None

    if site_id:
        if scope.restricted and site_id not in scope.allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "site_access_denied",
                    "site_id": site_id,
                    "message": "You do not have access to this site.",
                },
            )
        return {"site_id": site_id}

    # No specific site → "All sites" / "All my sites".
    if scope.restricted:
        return {"site_id": {"$in": list(scope.allowed)}}
    return {}


def resolve_stamp_site_id(requested_site_id: Optional[str], primary_site_id: Optional[str]) -> Optional[str]:
    """Pick the ``site_id`` to stamp onto a NEW record.

    Prefers the active/requested site; falls back to the org's primary
    site so records are never left siteless. A restricted user requesting
    a disallowed site is rejected by :func:`build_site_filter` upstream.
    """
    sid = (requested_site_id or "").strip() or None
    if sid:
        # Reuse the RBAC gate so a restricted user can't stamp a record
        # onto a site they can't access.
        build_site_filter(sid)
        return sid
    scope = get_request_site_scope()
    if scope.restricted and scope.allowed:
        # Restricted user with no explicit site → stamp their first allowed site.
        return scope.allowed[0]
    return (primary_site_id or "").strip() or None


__all__ = [
    "SiteScope",
    "set_request_site_scope",
    "set_request_site_scope_from",
    "clear_request_site_scope",
    "get_request_site_scope",
    "build_site_filter",
    "resolve_stamp_site_id",
    "get_requested_site_id",
    "set_requested_site",
    "get_requested_site",
    "effective_site_filter",
]


_ALL_SENTINELS = {"", "all", "all_sites", "all-sites", "null", "undefined", "none"}


def get_requested_site_id(
    request: Request,
    site_id: Optional[str] = Query(None),
) -> Optional[str]:
    """FastAPI dependency — resolve the active site for the request.

    A ``site_id`` query param wins; otherwise the ``X-Site-Id`` header
    (set once by the frontend axios interceptor) is used. Returns None for
    the "All sites" aggregate so :func:`build_site_filter` widens the scope.
    """
    if site_id and site_id.strip().lower() not in _ALL_SENTINELS:
        return site_id.strip()
    hdr = request.headers.get("x-site-id")
    if hdr and hdr.strip().lower() not in _ALL_SENTINELS:
        return hdr.strip()
    return None
