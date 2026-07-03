"""Idempotent MongoDB index helpers.

On MongoDB Atlas an index built by an earlier deploy persists across
redeploys. Re-creating an index on the SAME key with a different name or
options (e.g. adding a TTL to an auto-named ``created_at_1``) raises
``OperationFailure`` with code 85 (IndexOptionsConflict) or 86
(IndexKeySpecsConflict). Fresh preview Mongo never hits this because the
collection starts empty. These helpers reconcile the difference so boot
stays clean in every environment.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def ensure_ttl_index(coll, field: str, name: str, expire_seconds: int) -> None:
    """Ensure a single TTL index ``name`` on ``{field: 1}``.

    Reconciles any pre-existing index on the same key (typically an
    auto-named plain index like ``created_at_1``) by dropping it before
    (re)creating the named TTL index. A plain btree index on ``created_at``
    is redundant once the TTL index exists — the TTL index serves the same
    sorts/range queries AND expires old rows. Never raises.
    """
    want_key = [(field, 1)]
    try:
        info = await coll.index_information()
    except Exception as exc:
        logger.warning("index_information failed for %s: %s", coll.name, exc)
        info = {}

    for idx_name, spec in info.items():
        if idx_name == "_id_":
            continue
        key = [tuple(k) for k in spec.get("key", [])]
        if key != want_key:
            continue
        # Already exactly what we want — nothing to do.
        if idx_name == name and spec.get("expireAfterSeconds") == expire_seconds:
            return
        try:
            await coll.drop_index(idx_name)
            logger.info("Reconciled index on %s.%s — dropped conflicting %r", coll.name, field, idx_name)
        except Exception as exc:
            logger.warning("drop_index %r on %s failed: %s", idx_name, coll.name, exc)

    try:
        await coll.create_index(want_key, name=name, expireAfterSeconds=expire_seconds, background=True)
    except Exception as exc:
        logger.warning("create TTL index %r on %s failed (non-fatal): %s", name, coll.name, exc)
