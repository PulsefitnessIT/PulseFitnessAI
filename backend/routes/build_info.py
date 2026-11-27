"""Non-sensitive release identifiers so staff can confirm which code a running environment is serving."""
import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user

router = APIRouter(prefix="/build-info", tags=["build-info"])
_ROOT = Path(__file__).resolve().parent.parent
# Release-critical modules: identical fingerprints ⇒ identical code for these workflows.
_FILES = ["routes/crm_aftersales.py", "utils/cm_quote_import.py", "utils/afs_doc_sections.py", "routes/files_chunked.py",
          "utils/cm_renewals.py", "routes/mod_ops_quotes.py", "utils/mod_quote_chase.py", "utils/mod_schedule_b_bootstrap.py",
          "routes/bfpo.py", "utils/bfpo_coverage.py", "utils/crm_workspace.py"]
_STARTED = datetime.now(timezone.utc).isoformat()


def _commit() -> str | None:
    if os.environ.get("GIT_COMMIT"):
        return os.environ["GIT_COMMIT"]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=_ROOT, capture_output=True, text=True, timeout=3).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _fingerprint() -> dict:
    out = {}
    for f in _FILES:
        p = _ROOT / f
        out[f] = hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p.exists() else None
    out["combined"] = hashlib.sha256("".join(v or "-" for v in out.values()).encode()).hexdigest()[:16]
    return out


_INFO = {"commit": _commit(), "started_at": _STARTED, "fingerprint": _fingerprint()}


@router.get("")
async def build_info(user=Depends(get_current_user)):
    if not (user.get("is_master_admin") or user.get("is_pulse_admin") or (user.get("role") or "").lower() in ("owner", "admin")):
        raise HTTPException(403, "Administrators only")
    flags = {k: os.environ.get(k, "").lower() == "true" for k in ("CM_RENEWAL_EMAIL_LIVE", "MOD_QUOTE_NOTIFY_LIVE", "SICON_ALLOW_WRITES", "SAGE_ALLOW_WRITES", "SICON_NIGHTLY_SYNC_ENABLED", "INVITATION_EMAILS_LIVE", "IMPORTED_CUSTOMER_PURCHASES_ENABLED")}
    return {**_INFO, "flags": flags, "afs_import_max_mb": int(os.environ.get("AFS_IMPORT_MAX_MB", "50"))}
