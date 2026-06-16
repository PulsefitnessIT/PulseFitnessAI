"""Iter 216h138 — Bulk-import pipeline for 1000+ MOD sites.

When the MOD onboards (e.g. all 700 PT facilities across UK Strategic
Command), the master admin needs a one-shot way to:

  1. Download a CSV template tailored for MOD sites.
  2. Upload a filled-in CSV with site_code / name / branch / address /
     postcode / contacts / etc.
  3. Get a **dry-run preview** before persisting anything.
  4. **Commit** the lot in a single bulk-insert that scales to 1000+
     rows (motor `insert_many` for organizations + users).
  5. Receive back a **credentials CSV** the HQ team can email to
     individual base PTIs.

All four endpoints live behind `require_master_admin`. The two write
endpoints (commit + commit) are idempotent on `site_code` — re-running
the same CSV will skip sites that already exist.

CSV columns (canonical order, extras tolerated):

  site_code, site_name, branch, address_line1, address_line2,
  city, county, postcode, country, phone, email,
  site_manager_name, site_manager_email, oncall_phone,
  password   (← optional; auto-generated when blank)
"""
from __future__ import annotations

import base64
import csv
import io
import logging
import re
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from routes.master_admin import require_master_admin
from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Valid MOD branches (sticks to the same taxonomy as the demo seed)
BRANCHES = {"Army", "Navy", "RAF"}
BRANCH_ALIASES = {
    "army": "Army", "british army": "Army",
    "navy": "Navy", "royal navy": "Navy", "rn": "Navy",
    "raf": "RAF", "royal air force": "RAF",
}


_CSV_HEADERS = [
    "site_code", "site_name", "branch",
    "address_line1", "address_line2", "city", "county", "postcode", "country",
    "phone", "email", "site_manager_name", "site_manager_email", "oncall_phone",
    "access_notes", "password",
]

_CSV_EXAMPLE = [
    [
        "raf-conningsby", "RAF Coningsby Gym", "RAF",
        "RAF Coningsby", "", "Coningsby", "Lincolnshire", "LN4 4SY", "United Kingdom",
        "01526 000000", "site@example.com",
        "Sgt J. Bloggs", "j.bloggs@mod.gov.uk", "+44 7700 900000",
        "Pass required at main gate.", "",  # blank password → auto-generated
    ],
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kebab(s: str) -> str:
    """Convert 'RAF Brize Norton' → 'raf-brize-norton'."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", s or "").strip("-").lower()
    return s


def _gen_password(n: int = 14) -> str:
    """Strong but readable: 14 chars, letters+digits, no ambiguous 0/O/1/l."""
    alphabet = (string.ascii_letters + string.digits).translate(
        str.maketrans("", "", "0Oo1lIi")
    )
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _normalise_branch(value: str) -> Optional[str]:
    v = (value or "").strip().lower()
    return BRANCH_ALIASES.get(v) or (v.title() if v.title() in BRANCHES else None)


def _parse_csv(raw: str) -> tuple[list[dict], list[dict]]:
    """Returns (rows, errors). Validates required fields. Does NOT touch the DB."""
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV is empty or has no header row")
    fields_lc = [(h or "").strip().lower() for h in reader.fieldnames]
    if "site_name" not in fields_lc:
        raise HTTPException(400, "CSV must include a 'site_name' column")
    rows: list[dict] = []
    errors: list[dict] = []
    seen_codes: set[str] = set()
    for i, raw_row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        name = row.get("site_name", "")
        if not name:
            errors.append({"line": i, "error": "Missing site_name"})
            continue
        branch = _normalise_branch(row.get("branch", ""))
        if not branch:
            errors.append({"line": i, "error": "Missing or invalid branch (Army/Navy/RAF)"})
            continue
        site_code = row.get("site_code", "") or _kebab(name)
        site_code = _kebab(site_code)
        if not site_code:
            errors.append({"line": i, "error": "Could not derive site_code"})
            continue
        if site_code in seen_codes:
            errors.append({"line": i, "error": f"Duplicate site_code in CSV: {site_code}"})
            continue
        seen_codes.add(site_code)
        rows.append({
            "site_code": site_code,
            "site_name": name,
            "branch": branch,
            "address_line1": row.get("address_line1", "") or row.get("address", ""),
            "address_line2": row.get("address_line2", ""),
            "city": row.get("city", ""),
            "county": row.get("county", ""),
            "postcode": row.get("postcode", ""),
            "country": row.get("country", "") or "United Kingdom",
            "phone": row.get("phone", ""),
            "email": row.get("email", ""),
            "site_manager_name": row.get("site_manager_name", "")
                                  or row.get("manager_name", ""),
            "site_manager_email": row.get("site_manager_email", "")
                                   or row.get("manager_email", ""),
            "oncall_phone": row.get("oncall_phone", ""),
            "access_notes": row.get("access_notes", ""),
            "password": row.get("password", ""),
            "line": i,
        })
    return rows, errors


def _credentials_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["site_code", "site_name", "branch", "username", "password",
                 "login_url"])
    for r in rows:
        w.writerow([
            r["site_code"], r["site_name"], r["branch"],
            r["username"], r["password_plain"],
            "https://gymaxis.com/login",
        ])
    return buf.getvalue()


# ───────────────────────────── endpoints ─────────────────────────────


@router.get("/master-admin/mod-sites/template.csv")
async def mod_sites_template_csv(user: dict = Depends(get_current_user)):
    """Return a starter CSV with the canonical column headers + one example row."""
    require_master_admin(user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_CSV_HEADERS)
    for row in _CSV_EXAMPLE:
        w.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="gymaxis-mod-sites-template.csv"'},
    )


@router.post("/master-admin/mod-sites/preview-csv")
async def mod_sites_preview_csv(
    file: UploadFile = File(...), user: dict = Depends(get_current_user),
):
    """Dry-run validation: parse the CSV, check for duplicates and
    pre-existing site_codes, return up to 100 sample rows + total
    counts so the operator can review before committing."""
    require_master_admin(user)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")
    try:
        raw = (await file.read()).decode("utf-8-sig", errors="replace")
    except Exception as exc:
        raise HTTPException(400, f"Could not read file: {exc}")
    rows, errors = _parse_csv(raw)
    if not rows:
        return {"sites": [], "count": 0, "errors": errors, "would_skip": 0}

    # Detect site_codes that already exist in Mongo so the operator
    # knows what'll be skipped on commit
    codes = [r["site_code"] for r in rows]
    existing = set()
    async for o in db.organizations.find(
        {"site_code": {"$in": codes}, "account_type": "mod_site"},
        {"_id": 0, "site_code": 1},
    ):
        existing.add(o["site_code"])
    for r in rows:
        r["already_exists"] = r["site_code"] in existing

    return {
        "sites": rows[:100],
        "count": len(rows),
        "would_skip": len(existing),
        "would_create": len(rows) - len(existing),
        "errors": errors,
    }


@router.post("/master-admin/mod-sites/bulk-import")
async def mod_sites_bulk_import(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mod_root_id: str = "mod-root-uk",
    sync: bool = False,
    user: dict = Depends(get_current_user),
):
    """Commit. By default runs in a background task and returns
    immediately with a `batch_id` so we don't hit the ingress 60 s
    timeout on 1000-row uploads. Poll `/bulk-import/{batch_id}/status`
    for progress.

    Pass `?sync=true` for small CSVs (<50 rows) when an immediate
    synchronous response is preferred — used by the test suite.

    Idempotent on `site_code` — duplicates are silently skipped, never
    overwritten.
    """
    require_master_admin(user)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")
    try:
        raw = (await file.read()).decode("utf-8-sig", errors="replace")
    except Exception as exc:
        raise HTTPException(400, f"Could not read file: {exc}")
    rows, errors = _parse_csv(raw)
    if not rows:
        return {"created": 0, "skipped": 0, "errors": errors,
                "credentials_csv_b64": None, "status": "done", "batch_id": None}

    # Confirm root exists (we don't auto-create it — that's a sales op step)
    root = await db.organizations.find_one(
        {"id": mod_root_id, "account_type": "mod_org"}, {"_id": 0, "id": 1},
    )
    if not root:
        raise HTTPException(
            400, f"mod_root_id '{mod_root_id}' not found — create the MOD root first",
        )

    batch_id = str(uuid.uuid4())
    now = _now()
    await db.mod_bulk_import_batches.insert_one({
        "id": batch_id,
        "imported_by": user.get("id"),
        "mod_root_id": mod_root_id,
        "total_rows": len(rows),
        "processed": 0,
        "created_count": 0,
        "skipped_count": 0,
        "error_count": len(errors),
        "errors": errors,
        "status": "running",
        "credentials_csv_b64": None,
        "created_at": now,
        "updated_at": now,
    })

    if sync:
        # Run inline for small batches / tests
        await _run_bulk_import(batch_id, rows, mod_root_id)
        fresh = await db.mod_bulk_import_batches.find_one(
            {"id": batch_id}, {"_id": 0},
        ) or {}
        return {
            "batch_id": batch_id,
            "status": fresh.get("status"),
            "created": fresh.get("created_count", 0),
            "skipped": fresh.get("skipped_count", 0),
            "errors": (fresh.get("errors") or []),
            "credentials_csv_b64": fresh.get("credentials_csv_b64"),
        }

    # Async — return now, work in background
    background_tasks.add_task(_run_bulk_import, batch_id, rows, mod_root_id)
    return {
        "batch_id": batch_id,
        "status": "running",
        "total_rows": len(rows),
        "errors": errors,
        # `created` and `credentials_csv_b64` arrive via the status poll
        "created": 0,
        "skipped": 0,
        "credentials_csv_b64": None,
    }


async def _run_bulk_import(batch_id: str, rows: list[dict], mod_root_id: str) -> None:
    """Heavy lift: bulk-build org + user docs, insert in chunks, update
    the batch doc as progress markers so the UI can show a progress
    bar."""
    now = _now()
    # Resolve existing site_codes to skip
    codes = [r["site_code"] for r in rows]
    skip_codes: set[str] = set()
    async for o in db.organizations.find(
        {"site_code": {"$in": codes}, "account_type": "mod_site"},
        {"_id": 0, "site_code": 1},
    ):
        skip_codes.add(o["site_code"])

    org_docs: list[dict] = []
    user_docs: list[dict] = []
    credentials: list[dict] = []
    for r in rows:
        if r["site_code"] in skip_codes:
            continue
        site_id = f"mod-site-{r['site_code']}"
        pwd_plain = r["password"] or _gen_password()
        synthetic_email = f"{r['site_code']}@site.mod.local"
        org_docs.append({
            "id": site_id,
            "name": r["site_name"],
            "account_type": "mod_site",
            "mod_root_id": mod_root_id,
            "mod_branch": r["branch"],
            "site_code": r["site_code"],
            "address": ", ".join([
                r["address_line1"], r["address_line2"], r["city"],
                r["county"], r["postcode"], r["country"]
            ]).strip(", "),
            "address_line1": r["address_line1"],
            "address_line2": r["address_line2"],
            "city": r["city"],
            "county": r["county"],
            "postcode": r["postcode"],
            "country": r["country"] or "United Kingdom",
            "phone": r["phone"],
            "email": r["email"],
            "site_manager_name": r["site_manager_name"],
            "site_manager_email": r["site_manager_email"],
            "oncall_phone": r["oncall_phone"],
            "access_notes": r["access_notes"],
            "subscription_tier": "lite",
            "imported_via": "mod_bulk_import_csv",
            "import_batch_id": batch_id,
            "created_at": now,
        })
        user_docs.append({
            "id": f"mod-user-{r['site_code']}",
            "username": r["site_code"],
            "email": synthetic_email,
            "password": pwd_ctx.hash(pwd_plain),
            "full_name": r["site_name"],
            "organization_id": site_id,
            "role": "owner",
            "account_type": "mod_site",
            "mod_site_code": r["site_code"],
            "is_username_login": True,
            "imported_via": "mod_bulk_import_csv",
            "import_batch_id": batch_id,
            "created_at": now,
            "password_updated_at": now,
        })
        credentials.append({
            "site_code": r["site_code"],
            "site_name": r["site_name"],
            "branch": r["branch"],
            "username": r["site_code"],
            "password_plain": pwd_plain,
        })
        # Heartbeat for the progress poller
        if len(org_docs) % 50 == 0:
            await db.mod_bulk_import_batches.update_one(
                {"id": batch_id},
                {"$set": {"processed": len(org_docs), "updated_at": _now()}},
            )

    created = 0
    insert_errors: list[dict] = []
    if org_docs:
        # Chunked insert keeps memory predictable AND lets the progress
        # bar advance for very large CSVs.
        CHUNK = 200
        for i in range(0, len(org_docs), CHUNK):
            o_chunk = org_docs[i:i + CHUNK]
            u_chunk = user_docs[i:i + CHUNK]
            try:
                res_org = await db.organizations.insert_many(o_chunk, ordered=False)
                await db.users.insert_many(u_chunk, ordered=False)
                created += len(res_org.inserted_ids)
            except Exception as exc:
                logger.exception("[mod_bulk_import] chunk insert failed: %s", exc)
                insert_errors.append(
                    {"line": 0, "error": f"Insert error around row {i}: {exc}"},
                )
            await db.mod_bulk_import_batches.update_one(
                {"id": batch_id},
                {"$set": {"processed": min(i + CHUNK, len(org_docs)),
                           "created_count": created,
                           "updated_at": _now()}},
            )

    credentials_csv = _credentials_csv(credentials) if credentials else ""
    await db.mod_bulk_import_batches.update_one(
        {"id": batch_id},
        {"$set": {
            "status": "done",
            "created_count": created,
            "skipped_count": len(skip_codes),
            "processed": len(rows),
            "error_count": len(insert_errors),
            "credentials_csv_b64": base64.b64encode(
                credentials_csv.encode("utf-8"),
            ).decode("ascii") if credentials_csv else None,
            "updated_at": _now(),
        }, "$push": {"errors": {"$each": insert_errors}}},
    )


@router.get("/master-admin/mod-sites/bulk-import/{batch_id}/status")
async def mod_sites_bulk_import_status(
    batch_id: str, user: dict = Depends(get_current_user),
):
    """Poll endpoint for the background importer."""
    require_master_admin(user)
    batch = await db.mod_bulk_import_batches.find_one(
        {"id": batch_id},
        {"_id": 0, "credentials_csv_b64": 1, "status": 1, "total_rows": 1,
         "processed": 1, "created_count": 1, "skipped_count": 1, "errors": 1,
         "error_count": 1, "created_at": 1, "updated_at": 1,
         "delivery_status": 1, "delivery_total": 1,
         "delivery_sent": 1, "delivery_failed": 1, "delivery_missing": 1,
         "delivery_started_at": 1, "delivery_updated_at": 1,
         "delivery_receipt_csv_b64": 1},
    )
    if not batch:
        raise HTTPException(404, "Import batch not found")
    return {
        "batch_id": batch_id,
        "status": batch.get("status", "unknown"),
        "total_rows": batch.get("total_rows", 0),
        "processed": batch.get("processed", 0),
        "created": batch.get("created_count", 0),
        "skipped": batch.get("skipped_count", 0),
        "errors": batch.get("errors", []),
        "credentials_csv_b64": batch.get("credentials_csv_b64"),
        "started_at": batch.get("created_at"),
        "updated_at": batch.get("updated_at"),
        # Iter 216h139 — credentials-by-email dispatch
        "delivery_status":   batch.get("delivery_status"),  # None | running | done
        "delivery_total":    batch.get("delivery_total", 0),
        "delivery_sent":     batch.get("delivery_sent", 0),
        "delivery_failed":   batch.get("delivery_failed", 0),
        "delivery_missing":  batch.get("delivery_missing", 0),
        "delivery_started_at": batch.get("delivery_started_at"),
        "delivery_updated_at": batch.get("delivery_updated_at"),
        "delivery_receipt_available": bool(batch.get("delivery_receipt_csv_b64")),
    }


@router.get("/master-admin/mod-sites/bulk-import/{batch_id}/credentials.csv")
async def mod_sites_download_credentials(
    batch_id: str, user: dict = Depends(get_current_user),
):
    """Re-download the credentials CSV for a previous batch. The plain
    passwords are stored only in this batch document — they are NOT
    stored on the user docs (those carry only the bcrypt hash).
    """
    require_master_admin(user)
    batch = await db.mod_bulk_import_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(404, "Import batch not found")
    csv_text = base64.b64decode(batch["credentials_csv_b64"]).decode("utf-8")
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition":
                  f'attachment; filename="gymaxis-mod-credentials-{batch_id[:8]}.csv"'},
    )


# ─────────────────────── credentials dispatch ───────────────────────


CREDENTIALS_EMAIL_HTML = """<!DOCTYPE html><html><body style="font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; color: #0f172a; line-height: 1.55;">
<div style="max-width: 560px; margin: 0 auto; padding: 28px 24px;">
  <h1 style="font-size: 20px; font-weight: 800; margin: 0 0 8px;">Welcome to Pulse Fitness — {site_name}</h1>
  <p style="font-size: 14px; color: #334155; margin: 0 0 16px;">
    Your base has been set up on the Pulse Fitness Defence Estate Management platform.
    Below are the credentials your team uses to log faults, view repair status,
    and escalate to DIO.
  </p>
  <div style="background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 10px; padding: 16px; margin: 16px 0;">
    <p style="margin: 0; font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: #64748b; font-weight: 700;">Login</p>
    <p style="font-family: ui-monospace, SFMono-Regular, monospace; font-size: 15px; font-weight: 600; color: #0f172a; margin: 6px 0 12px;">{username}</p>
    <p style="margin: 0; font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: #64748b; font-weight: 700;">Password</p>
    <p style="font-family: ui-monospace, SFMono-Regular, monospace; font-size: 15px; font-weight: 600; color: #0f172a; margin: 6px 0 0;">{password}</p>
  </div>
  <p style="font-size: 13px; color: #334155;">Log in at:
    <a href="{login_url}" style="color: #1d4ed8; font-weight: 700;">{login_url}</a>
  </p>
  <div style="background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; padding: 12px; margin: 18px 0;">
    <p style="margin: 0; font-size: 12px; color: #9a3412;">
      <strong>OFFICIAL — SECURITY</strong>: Please change your password on first login.
      This message is the only record of the temporary password.
    </p>
  </div>
  <p style="font-size: 12px; color: #64748b; margin-top: 24px;">— The Pulse Fitness team</p>
</div>
</body></html>"""


class SendCredentialsIn(BaseModel):
    subject_override: str | None = Field(default=None, max_length=240)
    test_only_email: str | None = Field(
        default=None,
        description="If set, send ONE test email to this address instead of "
                     "the real recipients. Used to verify rendering before "
                     "a full network blast.",
    )


@router.post("/master-admin/mod-sites/bulk-import/{batch_id}/send-credentials")
async def mod_sites_send_credentials(
    batch_id: str,
    background_tasks: BackgroundTasks,
    body: SendCredentialsIn | None = None,
    user: dict = Depends(get_current_user),
):
    """Email each base PTI their unique credentials.

    Recipient resolution per site:
      * If `site_manager_email` was supplied in the CSV → use that.
      * Else fall back to the site's primary `email` column.
      * If neither is set, the row is recorded as `missing_email`
        in the delivery receipt — nothing is sent.

    The dispatcher runs in a `BackgroundTask` because Resend's REST API
    is sync per call and we don't want the K8s ingress to time out on
    1000-recipient batches.
    """
    require_master_admin(user)
    body = body or SendCredentialsIn()
    batch = await db.mod_bulk_import_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(404, "Import batch not found")
    if not batch.get("credentials_csv_b64"):
        raise HTTPException(409, "Batch has no credentials to send "
                                   "(import may still be running)")
    if batch.get("delivery_status") == "running":
        raise HTTPException(409, "A previous send is already in progress")

    # Decode credentials CSV
    creds_csv = base64.b64decode(batch["credentials_csv_b64"]).decode("utf-8")
    reader = csv.DictReader(io.StringIO(creds_csv))
    creds = list(reader)
    if not creds:
        raise HTTPException(409, "No credential rows in this batch")

    now = _now()
    await db.mod_bulk_import_batches.update_one(
        {"id": batch_id},
        {"$set": {
            "delivery_status":   "running",
            "delivery_total":    len(creds),
            "delivery_sent":     0,
            "delivery_failed":   0,
            "delivery_missing":  0,
            "delivery_started_at": now,
            "delivery_updated_at": now,
            "delivery_receipt_csv_b64": None,
        }},
    )

    background_tasks.add_task(
        _run_credentials_dispatch,
        batch_id, creds,
        body.subject_override or "Your Pulse Fitness login for {site_name}",
        body.test_only_email,
    )
    return {
        "batch_id": batch_id,
        "delivery_status": "running",
        "delivery_total": len(creds),
        "test_only_email": body.test_only_email,
    }


async def _run_credentials_dispatch(
    batch_id: str, creds: list[dict], subject_tpl: str,
    test_only_email: str | None,
) -> None:
    """Per-row Resend send + delivery-receipt accumulation."""
    receipt: list[dict] = []
    sent = failed = missing = 0
    # Cache recipient emails (one Mongo round-trip per site_code)
    codes = [c["site_code"] for c in creds]
    orgs: dict[str, dict] = {}
    async for o in db.organizations.find(
        {"site_code": {"$in": codes}, "account_type": "mod_site"},
        {"_id": 0, "site_code": 1, "site_manager_email": 1, "email": 1,
         "site_manager_name": 1, "id": 1},
    ):
        orgs[o["site_code"]] = o

    for i, row in enumerate(creds):
        org = orgs.get(row["site_code"]) or {}
        target = test_only_email or (org.get("site_manager_email")
                                       or org.get("email") or "")
        if not target or "@" not in target:
            missing += 1
            receipt.append({
                "site_code": row["site_code"],
                "site_name": row["site_name"],
                "username":  row["username"],
                "recipient": "",
                "status":    "missing_email",
                "error":     "No site_manager_email or email on file",
            })
            continue
        subject = subject_tpl.format(
            site_name=row["site_name"], site_code=row["site_code"],
            branch=row["branch"],
        )
        html = CREDENTIALS_EMAIL_HTML.format(
            site_name=row["site_name"],
            username=row["username"],
            password=row["password"],
            login_url=(row.get("login_url") or "https://gymaxis.com/login"),
        )
        try:
            ok = await send_email(target, subject, html,
                                    organization_id=org.get("id"))
        except Exception as exc:
            logger.warning("[mod_bulk_import] send_email errored for %s: %s",
                            target, exc)
            ok = False
        if ok:
            sent += 1
            receipt.append({"site_code": row["site_code"],
                             "site_name": row["site_name"],
                             "username":  row["username"],
                             "recipient": target,
                             "status":    "sent",
                             "error":     ""})
        else:
            failed += 1
            receipt.append({"site_code": row["site_code"],
                             "site_name": row["site_name"],
                             "username":  row["username"],
                             "recipient": target,
                             "status":    "failed",
                             "error":     "Resend rejected or unconfigured"})

        # Heartbeat
        if (i + 1) % 25 == 0 or (i + 1) == len(creds):
            await db.mod_bulk_import_batches.update_one(
                {"id": batch_id},
                {"$set": {
                    "delivery_sent":    sent,
                    "delivery_failed":  failed,
                    "delivery_missing": missing,
                    "delivery_updated_at": _now(),
                }},
            )
        if test_only_email:
            break  # we only fire one test email and stop

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=[
        "site_code", "site_name", "username", "recipient", "status", "error",
    ])
    w.writeheader()
    for r in receipt:
        w.writerow(r)
    receipt_b64 = base64.b64encode(buf.getvalue().encode("utf-8")).decode("ascii")
    await db.mod_bulk_import_batches.update_one(
        {"id": batch_id},
        {"$set": {
            "delivery_status":  "done",
            "delivery_sent":    sent,
            "delivery_failed":  failed,
            "delivery_missing": missing,
            "delivery_receipt_csv_b64": receipt_b64,
            "delivery_updated_at": _now(),
        }},
    )


@router.get("/master-admin/mod-sites/bulk-import/{batch_id}/delivery-receipt.csv")
async def mod_sites_download_delivery_receipt(
    batch_id: str, user: dict = Depends(get_current_user),
):
    """Re-download the per-recipient delivery receipt for an earlier send."""
    require_master_admin(user)
    batch = await db.mod_bulk_import_batches.find_one(
        {"id": batch_id}, {"_id": 0, "id": 1, "delivery_receipt_csv_b64": 1},
    )
    if not batch:
        raise HTTPException(404, "Batch not found")
    if not batch.get("delivery_receipt_csv_b64"):
        raise HTTPException(409, "No delivery receipt yet — send first")
    csv_text = base64.b64decode(batch["delivery_receipt_csv_b64"]).decode("utf-8")
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition":
                  f'attachment; filename="gymaxis-mod-delivery-{batch_id[:8]}.csv"'},
    )


__all__ = ["router"]
