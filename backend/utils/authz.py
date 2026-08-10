"""Central Authorisation Engine (Zero-Trust, deny-by-default).

The single authoritative server-side authorisation layer for object-level
(BOLA/IDOR), tenant, site and ownership checks, plus protected state
transitions and mass-assignment defence. It CONSOLIDATES the fragmented
``get_organization_filter`` / ``apply_site_lock`` / ad-hoc ``find_one``
patterns into one reusable, auditable primitive:

    resource = await authorize_resource(user, "issue", issue_id, "update", request=request)

The default outcome is ALWAYS deny. Access is granted only when there is an
explicit, valid entitlement for THIS user against THIS exact object.

Key rules (see PulseFitness security programme sections 2-9):
  * Cross-tenant access → 404 (never leak existence).
  * Cross-site access for a site-restricted user → 403.
  * Ownership-scoped resources (member bookings etc.) require the caller to
    own the object.
  * Master/Pulse admins bypass tenant/site (they are a superset) but the
    access is still audited.
  * Invalid workflow state transitions → 409; privileged-only transitions by
    a non-privileged user → 403. Every privileged transition is logged.

This module NEVER trusts a client-supplied tenant/site/owner id: scope is
always derived from the authenticated ``user`` dict (populated server-side by
``utils.auth``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from fastapi import HTTPException

from utils.auth import get_organization_filter
from utils.security_events import log_security_event, SEV_CRITICAL, SEV_WARNING

# ──────────────────────────── Resource registry ────────────────────────────


@dataclass(frozen=True)
class ResourceSpec:
    collection: str
    # First org field found on the doc is used for the tenant check. Some
    # resources (MOD faults) carry both organization_id AND mod_site_id.
    org_fields: tuple = ("organization_id",)
    site_field: Optional[str] = None
    member_field: Optional[str] = None
    id_field: str = "id"
    sensitive: bool = False  # extra-audited (MOD, financial, admin)


# The registry is deliberately explicit — a resource with no entry is DENIED
# (fail-closed), forcing every new sensitive route to declare its scope.
RESOURCE_REGISTRY: dict[str, ResourceSpec] = {
    "issue":         ResourceSpec("issues", ("organization_id", "mod_site_id"), site_field="site_id"),
    "equipment":     ResourceSpec("equipment", ("organization_id",), site_field="site_id"),
    "booking":       ResourceSpec("bookings", ("organization_id",), site_field="site_id", member_field="member_id"),
    "member":        ResourceSpec("members", ("organization_id",), site_field="site_id"),
    "document":      ResourceSpec("documents", ("organization_id",)),
    "file":          ResourceSpec("files", ("organization_id",), site_field="site_id"),
    "supplier_case": ResourceSpec("supplier_cases", ("organization_id",)),
    "quote":         ResourceSpec("crm2_quotes", ("organization_id",), sensitive=True),
    "contract":      ResourceSpec("crm2_contracts", ("organization_id",), sensitive=True),
    "svc_case":      ResourceSpec("svc_cases", ("organization_id",)),
    "invoice":       ResourceSpec("invoices", ("organization_id",), sensitive=True),
    "site":          ResourceSpec("sites", ("organization_id",)),
    # MOD sites ARE organisations; personnel are keyed by their site (org) id.
    "mod_site_staff": ResourceSpec("mod_site_staff", ("site_id", "organization_id"), sensitive=True),
    "mod_incident":  ResourceSpec("mod_incidents", ("site_id", "organization_id"), sensitive=True),
}

READ_ACTIONS = frozenset({"read", "view", "list", "download"})
WRITE_ACTIONS = frozenset({
    "create", "update", "delete", "cancel", "approve", "reject",
    "assign", "transition", "status_change", "transfer", "close", "reopen",
})

_PRIVILEGED_ROLES = frozenset({"owner", "manager", "master_admin", "master", "pulse_master_admin", "admin"})


def _is_admin(user: dict) -> bool:
    return bool(user.get("is_master_admin") or user.get("is_pulse_admin"))


def _is_privileged(user: dict) -> bool:
    if _is_admin(user):
        return True
    return (user.get("role") or "").lower() in _PRIVILEGED_ROLES


def _allowed_org_ids(user: dict) -> Optional[set]:
    """Return the set of org ids the caller may touch, or None when the
    caller is scoped by user_id only (personal data, no org isolation)."""
    f = get_organization_filter(user)
    if "organization_id" in f:
        v = f["organization_id"]
        if isinstance(v, dict) and "$in" in v:
            return {str(x) for x in v["$in"]}
        return {str(v)}
    return None


async def authorize_resource(
    user: dict,
    resource_type: str,
    resource_id: str,
    action: str = "read",
    *,
    request=None,
    require_roles: Optional[Iterable[str]] = None,
    owner_id: Optional[str] = None,
):
    """Load ``resource_id`` and prove the caller may perform ``action`` on it.

    Returns the resource document (so the caller need not re-fetch). Raises
    ``HTTPException`` (404/403) and writes a security event on any denial.
    """
    from utils.database import db  # local import keeps engine import-light

    spec = RESOURCE_REGISTRY.get(resource_type)
    if spec is None:
        # Fail closed — an unregistered resource type is a programming error,
        # never an implicit allow.
        raise HTTPException(status_code=500, detail="Authorization not configured for this resource")

    # ── Abuse escalation ladder (§33): if this actor has been tripping denials,
    #     enforce throttle/step-up/suspend on WRITE actions before doing work.
    if action in WRITE_ACTIONS and not _is_admin(user):
        from utils.abuse_guard import check_abuse
        await check_abuse(user, request, action=action)

    doc = await db[spec.collection].find_one({spec.id_field: resource_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=f"{resource_type} not found")

    # ── Master / Pulse admin: superset identity, bypass tenant+site but audit.
    if _is_admin(user):
        if spec.sensitive and action in WRITE_ACTIONS:
            await log_security_event(
                "privileged_admin_write", user=user, request=request, severity=SEV_WARNING,
                resource_type=resource_type, resource_id=resource_id, action=action,
                result="allowed", detail="master-admin bypass",
            )
        return doc

    # ── Tenant isolation (deny-by-default). ──────────────────────────────
    allowed = _allowed_org_ids(user)
    doc_org = next((str(doc[f]) for f in spec.org_fields if doc.get(f)), None)
    if allowed is not None:
        if doc_org is None or doc_org not in allowed:
            await log_security_event(
                "bola_cross_tenant_denied", user=user, request=request, severity=SEV_CRITICAL,
                resource_type=resource_type, resource_id=resource_id, action=action,
                result="denied", detail=f"resource tenant {doc_org} outside caller scope",
            )
            # 404, not 403 — never confirm the object exists to an outsider.
            from utils.abuse_guard import record_denial
            await record_denial(user, request, reason="cross_tenant")
            raise HTTPException(status_code=404, detail=f"{resource_type} not found")
    else:
        # user_id-scoped fallback (no org): require personal ownership.
        personal_owner = doc.get("user_id") or doc.get("created_by")
        if personal_owner and str(personal_owner) != str(user.get("id")):
            await log_security_event(
                "bola_cross_owner_denied", user=user, request=request, severity=SEV_CRITICAL,
                resource_type=resource_type, resource_id=resource_id, action=action,
                result="denied",
            )
            from utils.abuse_guard import record_denial
            await record_denial(user, request, reason="cross_owner")
            raise HTTPException(status_code=404, detail=f"{resource_type} not found")

    # ── Site isolation. Only enforced when the doc carries a site and the
    #     caller is site-restricted (see utils.site_scope). ───────────────
    if spec.site_field and doc.get(spec.site_field):
        try:
            from utils.site_scope import build_site_filter
            build_site_filter(str(doc[spec.site_field]))  # raises 403 if disallowed
        except HTTPException:
            await log_security_event(
                "cross_site_denied", user=user, request=request, severity=SEV_CRITICAL,
                resource_type=resource_type, resource_id=resource_id, action=action,
                result="denied", site_id=str(doc.get(spec.site_field)),
            )
            from utils.abuse_guard import record_denial
            await record_denial(user, request, reason="cross_site")
            raise HTTPException(status_code=403, detail="You do not have access to this site")

    # ── Ownership check for member-owned resources (explicit owner_id). ──
    if owner_id is not None and spec.member_field:
        doc_owner = doc.get(spec.member_field)
        if doc_owner is not None and str(doc_owner) != str(owner_id):
            await log_security_event(
                "ownership_denied", user=user, request=request, severity=SEV_WARNING,
                resource_type=resource_type, resource_id=resource_id, action=action,
                result="denied",
            )
            raise HTTPException(status_code=404, detail=f"{resource_type} not found")

    # ── Function-level role gate (optional, deny-by-default when supplied).
    if require_roles:
        wanted = {r.lower() for r in require_roles}
        role = (user.get("role") or "").lower()
        if role not in wanted and not _is_admin(user):
            await log_security_event(
                "role_denied", user=user, request=request, severity=SEV_WARNING,
                resource_type=resource_type, resource_id=resource_id, action=action,
                result="denied", detail=f"role {role or 'none'} not in {sorted(wanted)}",
            )
            raise HTTPException(status_code=403, detail="You are not permitted to perform this action")

    return doc


# ─────────────────────── Protected state machines ──────────────────────────

# Allowed transitions per resource. `*` on the source side means "from any
# known state". A target not in the source's set is rejected (409). Sources
# listed under PRIVILEGED_ONLY require a privileged caller (owner/manager/admin).
STATE_MACHINES: dict[str, dict[str, set]] = {
    "issue": {
        "open":           {"in_progress", "allocated", "on_hold", "awaiting_parts", "attended", "resolved", "closed", "cancelled"},
        "in_progress":    {"awaiting_parts", "on_hold", "allocated", "attended", "resolved", "closed", "cancelled", "open"},
        "allocated":      {"in_progress", "attended", "awaiting_parts", "on_hold", "resolved", "closed", "cancelled"},
        "attended":       {"in_progress", "awaiting_parts", "on_hold", "resolved", "closed", "cancelled"},
        "awaiting_parts": {"in_progress", "allocated", "attended", "on_hold", "resolved", "closed", "cancelled"},
        "on_hold":        {"open", "in_progress", "allocated", "awaiting_parts", "resolved", "closed", "cancelled"},
        "resolved":       {"closed", "reopened", "open"},
        "reopened":       {"in_progress", "allocated", "awaiting_parts", "on_hold", "resolved", "closed", "cancelled"},
        "closed":         {"reopened"},   # closed→open is not allowed; must reopen
        "cancelled":      {"reopened"},
    },
    "quote": {
        # CRM v2 quote lifecycle. The critical protection (section 8): a
        # draft can NOT jump straight to 'approved' — it must pass through
        # 'pending_approval', and an already-finalised quote can't be re-approved.
        "draft":            {"pending_approval", "sent", "superseded", "cancelled"},
        "pending_approval": {"approved", "rejected", "draft", "superseded", "cancelled"},
        "approved":         {"sent", "accepted", "superseded", "cancelled"},
        "rejected":         {"draft", "pending_approval", "superseded", "cancelled"},
        "sent":             {"accepted", "rejected", "superseded", "cancelled"},
        "accepted":         {"superseded", "cancelled"},
        "superseded":       set(),
        "cancelled":        set(),
    },
    "contract": {
        # Enforced lifecycle: draft → (negotiation/amended) → pending_approval
        # → approved → sent → signed/active. A contract can NOT be sent,
        # signed or activated until it has been APPROVED — no request can skip
        # the approval step (Contract Workflow Lock).
        "draft":            {"negotiation", "amended", "pending_approval", "cancelled"},
        "negotiation":      {"draft", "amended", "pending_approval", "cancelled"},
        "amended":          {"draft", "negotiation", "pending_approval", "cancelled"},
        "pending_approval": {"approved", "rejected", "draft", "cancelled"},
        "rejected":         {"draft", "negotiation", "amended", "pending_approval", "cancelled"},
        "approved":         {"sent", "signed", "active", "cancelled"},
        "sent":             {"signed", "active", "approved", "expired", "cancelled"},
        "signed":           {"active", "expired", "cancelled"},
        "active":           {"amended", "expired", "terminated", "cancelled"},
        "expired":          {"active", "draft", "cancelled"},   # renewal
        "terminated":       set(),
        "cancelled":        set(),
    },
    "mod_incident": {
        "open":          {"investigating", "closed"},
        "investigating": {"open", "closed"},
        "closed":        {"open", "reopened"},   # reopen = privileged-only (below)
        "reopened":      {"investigating", "closed"},
    },
    "invoice": {
        # Service/engineer invoice lifecycle. Blocks illegal financial jumps
        # such as paid→draft (mark endpoint previously allowed any transition).
        "draft":   {"sent", "paid", "void"},
        "sent":    {"paid", "overdue", "void"},
        "overdue": {"paid", "void", "sent"},
        "paid":    {"void"},        # a paid invoice can only be voided (correction)
        "void":    set(),           # terminal
    },
}

# Transitions only a privileged caller (owner/manager/admin) may perform.
# NOTE: quote/contract approval authority in CRM is governed by the CRM's own
# approver model (crm_permissions), so we do NOT add an engine-level role gate
# there — only the state machine (which blocks skip-approval) applies.
PRIVILEGED_ONLY_TRANSITIONS: dict[str, set] = {
    "issue": {("closed", "reopened"), ("cancelled", "reopened"), ("resolved", "open")},
    "mod_incident": {("closed", "open"), ("closed", "reopened")},
}


async def assert_transition(
    resource_type: str,
    current: Optional[str],
    target: Optional[str],
    user: dict,
    *,
    resource_id: Optional[str] = None,
    request=None,
) -> None:
    """Enforce the server-side state machine for ``resource_type``.

    No-op when there is no status change. Raises 409 for an invalid
    transition, 403 when a privileged-only transition is attempted by a
    non-privileged caller. Every privileged transition is audited.
    """
    machine = STATE_MACHINES.get(resource_type)
    if not machine or not target:
        return
    cur = (current or "").lower()
    tgt = (target or "").lower()
    if cur == tgt:
        return  # idempotent no-op

    allowed_targets = machine.get(cur)
    if allowed_targets is None:
        # Unknown current state (legacy data) — allow but audit so we learn.
        await log_security_event(
            "state_transition_unknown_source", user=user, request=request, severity=SEV_WARNING,
            resource_type=resource_type, resource_id=resource_id, action="transition",
            result="allowed", detail=f"{cur or 'none'}→{tgt}",
        )
        return

    if tgt not in allowed_targets:
        await log_security_event(
            "invalid_state_transition", user=user, request=request, severity=SEV_WARNING,
            resource_type=resource_type, resource_id=resource_id, action="transition",
            result="denied", detail=f"{cur}→{tgt} not permitted",
        )
        raise HTTPException(status_code=409, detail=f"Cannot change status from '{cur}' to '{tgt}'")

    if (cur, tgt) in PRIVILEGED_ONLY_TRANSITIONS.get(resource_type, set()) and not _is_privileged(user):
        await log_security_event(
            "privileged_transition_denied", user=user, request=request, severity=SEV_WARNING,
            resource_type=resource_type, resource_id=resource_id, action="transition",
            result="denied", detail=f"{cur}→{tgt} requires owner/manager",
        )
        raise HTTPException(status_code=403, detail=f"Only a manager can change status from '{cur}' to '{tgt}'")

    # Audit every accepted privileged transition.
    if (cur, tgt) in PRIVILEGED_ONLY_TRANSITIONS.get(resource_type, set()):
        await log_security_event(
            "privileged_transition", user=user, request=request, severity=SEV_WARNING,
            resource_type=resource_type, resource_id=resource_id, action="transition",
            result="allowed", detail=f"{cur}→{tgt}",
        )


# ─────────────────────── Mass-assignment defence ───────────────────────────

# Fields a client may NEVER write via a normal update, regardless of role.
# (Tenant/site/owner rebinding, privilege escalation, financial/approval
# state, security metadata.) Section 9 — object property level authorisation.
PROTECTED_FIELDS = frozenset({
    "id", "_id",
    "organization_id", "org_id", "tenant_id", "company_id", "site_id",
    "owner_id", "user_id", "created_by", "created_at",
    "role", "roles", "is_admin", "isAdmin", "is_master_admin", "is_pulse_admin",
    "is_operator_company", "account_type", "permissions", "module_overrides",
    "allowed_site_ids", "is_service_desk", "is_inventory",
    "password", "password_hash", "mfa_secret", "mfa_backup_codes",
    "tokens_revoked_before",
    "approval_status", "approved_by", "approved_at",
    "warranty_status", "warranty_active", "warranty_expiry",
    "billing_status", "supplier_id", "dealer_id",
    "stripe_customer_id", "stripe_subscription_id", "stripe_account_id",
})


async def filter_writable(
    payload: dict,
    allowed_fields: Iterable[str],
    *,
    user: Optional[dict] = None,
    request=None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
) -> dict:
    """Return only the ``allowed_fields`` from ``payload``.

    Any attempt to send a PROTECTED_FIELD (or a field outside the allow-list
    that collides with a protected name) is dropped and audited. This is the
    server-side guard against mass-assignment / privilege escalation.
    """
    allow = set(allowed_fields)
    clean: dict = {}
    rejected_protected: list[str] = []
    for k, v in (payload or {}).items():
        if k in PROTECTED_FIELDS and k not in allow:
            rejected_protected.append(k)
            continue
        if k in allow:
            clean[k] = v
    if rejected_protected:
        await log_security_event(
            "mass_assignment_blocked", user=user, request=request, severity=SEV_WARNING,
            resource_type=resource_type, resource_id=resource_id, action="update",
            result="stripped", detail="rejected protected fields",
            extra={"fields": rejected_protected},
        )
    return clean


__all__ = [
    "ResourceSpec", "RESOURCE_REGISTRY",
    "authorize_resource",
    "READ_ACTIONS", "WRITE_ACTIONS",
    "STATE_MACHINES", "PRIVILEGED_ONLY_TRANSITIONS", "assert_transition",
    "PROTECTED_FIELDS", "filter_writable",
]
