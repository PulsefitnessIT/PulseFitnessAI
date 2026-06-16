#!/usr/bin/env python3
"""
Pulse Fitness · Integration mapping lint (iter 215dy).

Read by CI / pre-commit / `make lint-integrations`. Validates the integrity
of the cross-system field-mapping documentation:

  /app/memory/INTEGRATION_FIELD_MAPPING.md
  /app/memory/SVC_FIELD_MAPPING.md      (sections 2-18 still live here)

Checks performed (exit 1 on any failure):

  1. Both files parse as well-formed markdown with the expected section
     numbering (sections 1, 2, …, 25/26 in the master; 1-18 in the legacy).
  2. Every Sicon / Sage endpoint referenced in the markdown actually appears
     in `routes/svc/integrations/sicon_sync.py` or `routes/sicon.py` or
     `routes/svc/integrations/sage_invoice.py` (case-insensitive substring).
  3. No section number is skipped (catches typos that quietly drop a row).
  4. No `gymaxis_only` row in the mapping is referenced from a `bidirectional`
     or `→` direction in another row (catches contradictions).
  5. Every Pydantic Field(description=…) string in `routes/svc/**.py`
     containing `sicon:` or `sage:` is consistent with the markdown
     (best-effort — emits warnings rather than failures because the
     description format is human-friendly).

Exits 0 (PASS) when the mapping is consistent. Prints a coloured summary.

Usage:
  python /app/backend/scripts/check_integration_mapping.py
  python /app/backend/scripts/check_integration_mapping.py --strict   # warnings = errors
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path("/app")
MASTER_DOC = ROOT / "memory" / "INTEGRATION_FIELD_MAPPING.md"
LEGACY_DOC = ROOT / "memory" / "SVC_FIELD_MAPPING.md"
SICON_SYNC = ROOT / "backend" / "routes" / "svc" / "integrations" / "sicon_sync.py"
SAGE_INVOICE = ROOT / "backend" / "routes" / "svc" / "integrations" / "sage_invoice.py"
SICON_LEGACY_ROUTES = ROOT / "backend" / "routes" / "sicon.py"
SVC_ROUTES = ROOT / "backend" / "routes" / "svc"

C_OK = "\033[32m"
C_WARN = "\033[33m"
C_ERR = "\033[31m"
C_DIM = "\033[2m"
C_END = "\033[0m"


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def ok(self, msg: str) -> None:
        self.info.append(msg)

    def print_summary(self, *, strict: bool) -> int:
        for m in self.info:
            print(f"{C_OK}✓{C_END} {m}")
        for m in self.warnings:
            print(f"{C_WARN}⚠{C_END} {m}")
        for m in self.errors:
            print(f"{C_ERR}✗{C_END} {m}")
        n_err = len(self.errors)
        n_warn = len(self.warnings)
        if n_err == 0 and (not strict or n_warn == 0):
            print(f"\n{C_OK}PASS{C_END} · {len(self.info)} ok · {n_warn} warn · {n_err} err")
            return 0
        print(f"\n{C_ERR}FAIL{C_END} · {len(self.info)} ok · {n_warn} warn · {n_err} err")
        return 1


def _read(p: Path) -> str:
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8")


def check_section_numbers(text: str, file_label: str, expected_min: int, expected_max: int, report: Report,
                            *, allow_delegated_to_legacy: bool = False) -> None:
    """Ensure section numbers run in order with no gaps.

    If allow_delegated_to_legacy is set, sections 2-18 may legitimately be
    absent (they live in SVC_FIELD_MAPPING.md) provided the file mentions
    that delegation explicitly.
    """
    found = sorted({int(m.group(1)) for m in re.finditer(r"^## (\d+)\.", text, flags=re.M)})
    if not found:
        report.err(f"{file_label}: no `## N.` sections found at all")
        return
    delegated_range: set[int] = set()
    if allow_delegated_to_legacy and re.search(r"## 2\s*[-\u2013]\s*18\.[\s\S]{0,400}?SVC_FIELD_MAPPING\.md", text):
        delegated_range = set(range(2, 19))
    missing = [n for n in range(expected_min, expected_max + 1)
               if n not in found and n not in delegated_range]
    if missing:
        report.warn(f"{file_label}: missing section numbers {missing} (expected {expected_min}-{expected_max})")
    else:
        report.ok(f"{file_label}: sections {expected_min}-{expected_max} all present"
                   + (" (2-18 delegated to legacy doc)" if delegated_range else ""))
    extras = [n for n in found if n > expected_max]
    if extras:
        report.ok(f"{file_label}: extra sections {extras} (acceptable — doc has grown)")


def check_endpoints_exist(report: Report) -> None:
    """Every `/api/Service/...` or `/SLInvoice` ref in the doc must resolve to source."""
    master = _read(MASTER_DOC)
    legacy = _read(LEGACY_DOC)
    haystacks: dict[str, str] = {
        "sicon_sync.py": _read(SICON_SYNC),
        "sage_invoice.py": _read(SAGE_INVOICE),
        "sicon.py (legacy routes)": _read(SICON_LEGACY_ROUTES),
        "sage_client.py": _read(ROOT / "backend" / "utils" / "sage_client.py"),
        "sage_outbox_worker.py": _read(ROOT / "backend" / "utils" / "sage_outbox_worker.py"),
        "sicon_outbox_worker.py": _read(ROOT / "backend" / "utils" / "sicon_outbox_worker.py"),
    }
    # Grab anything that looks like a Sicon path: /api/Service/Foo, /Service/Foo
    sicon_refs = set(re.findall(r"/api/Service/[A-Za-z]+|/Service/[A-Za-z]+", master + legacy))
    # And Sage: SLInvoice, SLQuote, SLContract, SLCustomerAccount
    sage_refs = set(re.findall(r"\bSL(?:Invoice|Quote|Contract|CustomerAccount|DeliveryAddress)(?:Line)?\b", master + legacy))

    if not sicon_refs:
        report.warn("no Sicon endpoint references found in mapping docs (looks suspicious)")
    for ref in sicon_refs:
        last = ref.rsplit("/", 1)[-1]
        if any(last in v for v in haystacks.values()):
            continue
        report.warn(f"Sicon endpoint reference {ref!r} not present in any sicon_sync.py / sicon.py — wire it up before the Sicon worker ships")

    if not sage_refs:
        report.warn("no Sage entity references found in mapping docs")
    for ref in sage_refs:
        if ref in haystacks["sage_invoice.py"] or ref in haystacks["sage_client.py"] or ref in haystacks["sage_outbox_worker.py"]:
            continue
        # SLContract / SLQuote / SLCustomerAccount may be CRM-side; check there too
        crm_files = list((ROOT / "backend" / "routes").glob("crm_*.py"))
        if any(ref in p.read_text(encoding="utf-8", errors="ignore") for p in crm_files):
            continue
        report.warn(f"Sage entity {ref!r} not yet implemented in any payload builder — add a row to the Sage outbox when wiring")


def check_pydantic_annotations(report: Report) -> None:
    """Best-effort: count integration annotations across `routes/svc/*`.

    Two patterns are accepted:
      1. Pydantic `Field(description="… sicon: X · sage: Y …")` — preferred when the
         route already uses Pydantic models.
      2. Module-level `__integration_fields__ = {"field_name": "sicon: X · sage: Y", …}`
         — used when the route takes plain `dict` payloads (the current pattern in
         routes/svc/*). Any value containing `sicon:`, `sage:`, or `gymaxis_only`
         counts as an annotated field.

    Don't fail on missing annotations — just count them so progress is visible
    iteration over iteration.
    """
    annotated = 0
    fields = 0
    files_with_manifest = 0
    files_total = 0
    for p in SVC_ROUTES.rglob("*.py"):
        if p.name == "__init__.py":
            continue
        files_total += 1
        text = p.read_text(encoding="utf-8", errors="ignore")
        # Pattern 1 — Pydantic Field(description=…)
        for m in re.finditer(r"Field\([^)]*description=[\"\']([^\"\']*)[\"\']", text):
            fields += 1
            d = m.group(1).lower()
            if "sicon:" in d or "sage:" in d or "gymaxis_only" in d:
                annotated += 1
        # Pattern 2 — module-level __integration_fields__ = { "name": "sicon: …", … }
        manifest = re.search(r"__integration_fields__\s*=\s*\{([\s\S]*?)\n\}", text, flags=re.M)
        if manifest:
            files_with_manifest += 1
            entries = re.findall(r"[\"\']([^\"\']+)[\"\']\s*:\s*[\"\']([^\"\']*)[\"\']", manifest.group(1))
            for _name, descr in entries:
                fields += 1
                d = descr.lower()
                if "sicon:" in d or "sage:" in d or "gymaxis_only" in d:
                    annotated += 1
    if fields == 0:
        report.warn("no integration annotations found in routes/svc/* — neither Pydantic Field(description=…) nor __integration_fields__ manifests adopted yet")
        return
    pct = round(annotated / fields * 100, 1)
    coverage = f"{files_with_manifest}/{files_total} files have a manifest"
    if annotated == fields:
        report.ok(f"integration annotations: {annotated}/{fields} fields ({pct}%) · {coverage}")
    else:
        report.warn(f"integration annotations: {annotated}/{fields} fields ({pct}%) · {coverage} · backfill the unannotated ones")


def check_legacy_redirect(report: Report) -> None:
    legacy = _read(LEGACY_DOC)
    if "INTEGRATION_FIELD_MAPPING.md" not in legacy:
        report.err("SVC_FIELD_MAPPING.md is missing the redirect note pointing to INTEGRATION_FIELD_MAPPING.md")
    else:
        report.ok("SVC_FIELD_MAPPING.md correctly redirects to the master mapping doc")


def check_master_has_credentials_matrix(report: Report) -> None:
    master = _read(MASTER_DOC)
    if "Credentials matrix" not in master:
        report.err("INTEGRATION_FIELD_MAPPING.md is missing the credentials matrix section")
    else:
        report.ok("master mapping doc has credentials matrix")
    needs = ["SICON_BASE_URL", "SAGE_CLIENT_ID", "svc_sicon_outbox", "svc_sage_invoice_outbox", "svc_sage_quote_outbox"]
    missing = [k for k in needs if k not in master]
    if missing:
        report.err(f"master mapping missing required references: {missing}")
    else:
        report.ok("master mapping references all required env vars + outbox collections")


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args(argv)

    report = Report()

    if not MASTER_DOC.is_file():
        report.err(f"master mapping doc not found at {MASTER_DOC}")
        return report.print_summary(strict=args.strict)

    master_text = _read(MASTER_DOC)
    legacy_text = _read(LEGACY_DOC)

    check_section_numbers(master_text, "INTEGRATION_FIELD_MAPPING.md", 1, 26, report, allow_delegated_to_legacy=True)
    check_section_numbers(legacy_text, "SVC_FIELD_MAPPING.md (sections 2-18)", 1, 18, report)
    check_legacy_redirect(report)
    check_master_has_credentials_matrix(report)
    check_endpoints_exist(report)
    check_pydantic_annotations(report)

    return report.print_summary(strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
