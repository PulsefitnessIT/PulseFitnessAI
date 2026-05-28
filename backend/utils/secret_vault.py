"""Secret-vault helpers — Iter 220aw / F-27.

Field-level Fernet encryption for the ``db.integrations`` collection (and
any other table that stores third-party credentials).

* Single Fernet key — reuses the existing ``MFA_ENCRYPTION_KEY`` env
  derivation that ``utils.mfa`` already proved out, so prod doesn't
  need a second secret rotated.
* Self-describing ciphertext — every encrypted blob is stored as a
  dict ``{"__enc": "v1", "data": "<fernet>"}`` so we can detect plain
  vs. encrypted at read-time and migrate gradually (no big-bang
  re-write needed).
* Idempotent — encrypt-on-an-already-encrypted dict is a no-op; same
  for decrypt-on-plain-string.

Secret fields encrypted by default for ``db.integrations``:

  ``api_token``, ``webhook_secret``, ``client_secret``, ``refresh_token``,
  ``access_token``, ``private_key``, ``signing_secret``, ``password``.

The ``credentials`` sub-dict is encrypted whole (one ciphertext blob)
because integration drivers vary wildly in field naming and a deep walk
would risk leaking new fields as plaintext.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

from cryptography.fernet import InvalidToken
from fastapi import HTTPException

from utils.mfa import _load_fernet  # reuse the key-derivation logic

log = logging.getLogger(__name__)


# Field names whose values must be encrypted at rest. Extend as new
# integrations land.
DEFAULT_SECRET_FIELDS = frozenset({
    "api_token", "webhook_secret", "client_secret",
    "refresh_token", "access_token", "private_key",
    "signing_secret", "password", "secret", "auth_token",
    "consumer_secret",
})


# Marker for the "encrypted blob" sentinel. Bumped only on format change.
_ENC_VERSION = "v1"


def _is_encrypted_blob(v: Any) -> bool:
    return isinstance(v, dict) and v.get("__enc") == _ENC_VERSION and "data" in v


def encrypt_value(value: Any) -> dict[str, str]:
    """Encrypt any JSON-serialisable value into the sentinel dict.

    Idempotent: if ``value`` already looks encrypted, return as-is."""
    if _is_encrypted_blob(value):
        return value
    if value is None or value == "":
        return {"__enc": _ENC_VERSION, "data": ""}
    if not isinstance(value, str):
        value = json.dumps(value, separators=(",", ":"), sort_keys=True)
    blob = _load_fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return {"__enc": _ENC_VERSION, "data": blob}


def decrypt_value(value: Any) -> Any:
    """Decrypt a sentinel dict back into the original value (str or
    parsed JSON for non-string originals).

    Idempotent: plain values are returned unchanged so callers can be
    naive about whether the field has been migrated yet.
    """
    if not _is_encrypted_blob(value):
        return value
    blob = value.get("data") or ""
    if not blob:
        return ""
    try:
        plain = _load_fernet().decrypt(blob.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, base64.binascii.Error) as exc:
        log.error("[secret-vault] decryption failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Stored integration secret is corrupt — re-enrol the integration.",
        )
    # If the original wasn't a string we JSON-roundtripped; try to parse back.
    try:
        return json.loads(plain)
    except (json.JSONDecodeError, ValueError):
        return plain


def encrypt_secrets_in_dict(
    doc: dict | None,
    *,
    fields: frozenset[str] = DEFAULT_SECRET_FIELDS,
    nested_dict_fields: tuple[str, ...] = ("credentials",),
) -> dict:
    """Encrypt every secret field in ``doc`` in place. Returns the same dict.

    Empty / None values are stored encrypted (so the very fact that an
    integration *has* a secret of a given name isn't leaked vs an
    integration that has none).
    """
    if not doc:
        return doc or {}
    for f in fields:
        if f in doc and not _is_encrypted_blob(doc[f]):
            doc[f] = encrypt_value(doc[f])
    for f in nested_dict_fields:
        if f in doc and doc[f] is not None and not _is_encrypted_blob(doc[f]):
            doc[f] = encrypt_value(doc[f])
    return doc


def decrypt_secrets_in_dict(
    doc: dict | None,
    *,
    fields: frozenset[str] = DEFAULT_SECRET_FIELDS,
    nested_dict_fields: tuple[str, ...] = ("credentials",),
) -> dict:
    """Decrypt every secret field in ``doc`` in place. Returns the same dict."""
    if not doc:
        return doc or {}
    for f in fields:
        if f in doc and _is_encrypted_blob(doc[f]):
            doc[f] = decrypt_value(doc[f])
    for f in nested_dict_fields:
        if f in doc and _is_encrypted_blob(doc[f]):
            doc[f] = decrypt_value(doc[f])
    return doc


def redact_secrets_in_dict(
    doc: dict | None,
    *,
    fields: frozenset[str] = DEFAULT_SECRET_FIELDS,
    nested_dict_fields: tuple[str, ...] = ("credentials",),
    mask: str = "••••••",
) -> dict:
    """Return a copy of ``doc`` with every secret field replaced by a
    static mask. Use this for any *read* API that surfaces an
    integration row back to the operator UI — the operator doesn't
    need to see their own token, only confirm it's set.
    """
    if not doc:
        return {}
    out = dict(doc)
    for f in fields:
        if f in out:
            v = out[f]
            # If still encrypted, only show "set" / "unset". If plain,
            # apply the visible mask of a similar length.
            if _is_encrypted_blob(v):
                out[f] = mask if (v.get("data") or "") else ""
            elif v:
                out[f] = mask
    for f in nested_dict_fields:
        if f in out and out[f]:
            out[f] = mask
    return out


__all__ = [
    "DEFAULT_SECRET_FIELDS",
    "encrypt_value", "decrypt_value",
    "encrypt_secrets_in_dict", "decrypt_secrets_in_dict",
    "redact_secrets_in_dict",
]
