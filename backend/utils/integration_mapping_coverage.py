"""
Iter 216h238 — Integration field-mapping coverage helper.

Re-uses the same logic the CI lint at
`/app/backend/scripts/check_integration_mapping.py` runs (the
``check_pydantic_annotations`` function in particular) so the
master-admin Integrations Hub can surface live coverage figures
without shelling out to the script.

Returns a structured dict:
    {
      "fields_total":      316,
      "fields_annotated":  307,
      "fields_pct":        97.2,
      "files_total":       32,
      "files_manifested":  12,
      "files_pct":         37.5,
      "by_module": {
          "sicon": {"fields": 142, "annotated": 138, "pct": 97.2},
          "sage":  {"fields": 174, "annotated": 169, "pct": 97.1},
          "gymaxis_only": {"fields": 9}
      },
      "doc_sections":      29,
      "computed_at":       "<iso-utc>"
    }

The route at `routes/master_admin_integration_health.py` calls
:func:`compute_mapping_coverage` and ships the dict to the UI.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/app")
SVC_ROUTES = ROOT / "backend" / "routes" / "svc"
MASTER_DOC = ROOT / "memory" / "INTEGRATION_FIELD_MAPPING.md"

_PYDANTIC_FIELD_RE = re.compile(r"Field\([^)]*description=[\"\']([^\"\']*)[\"\']")
_MANIFEST_RE = re.compile(r"__integration_fields__\s*=\s*\{([\s\S]*?)\n\}", re.M)
_MANIFEST_ENTRY_RE = re.compile(r"[\"\']([^\"\']+)[\"\']\s*:\s*[\"\']([^\"\']*)[\"\']")
_SECTION_RE = re.compile(r"^## (\d+)\.", re.M)


def _classify(descr: str) -> str:
    """Return one of ``sicon`` / ``sage`` / ``both`` / ``gymaxis_only`` /
    ``unannotated`` based on the field description."""
    d = descr.lower()
    has_sicon = "sicon:" in d
    has_sage = "sage:" in d
    if has_sicon and has_sage:
        return "both"
    if has_sicon:
        return "sicon"
    if has_sage:
        return "sage"
    if "gymaxis_only" in d:
        return "gymaxis_only"
    return "unannotated"


def compute_mapping_coverage() -> dict:
    """Walk ``routes/svc/*.py`` and ``INTEGRATION_FIELD_MAPPING.md`` and
    compute the annotation coverage stats used by the master-admin UI."""
    fields_total = 0
    fields_annotated = 0
    files_total = 0
    files_manifested = 0
    by_module = {
        "sicon":        {"fields": 0, "annotated": 0},
        "sage":         {"fields": 0, "annotated": 0},
        "both":         {"fields": 0, "annotated": 0},
        "gymaxis_only": {"fields": 0},
    }

    if SVC_ROUTES.is_dir():
        for p in SVC_ROUTES.rglob("*.py"):
            if p.name == "__init__.py":
                continue
            files_total += 1
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            # Pattern 1 — Pydantic Field(description=…)
            for m in _PYDANTIC_FIELD_RE.finditer(text):
                fields_total += 1
                kind = _classify(m.group(1))
                if kind == "unannotated":
                    continue
                fields_annotated += 1
                if kind in by_module and "fields" in by_module[kind]:
                    by_module[kind]["fields"] += 1
                    if "annotated" in by_module[kind]:
                        by_module[kind]["annotated"] += 1

            # Pattern 2 — __integration_fields__ manifest
            manifest = _MANIFEST_RE.search(text)
            if manifest:
                files_manifested += 1
                for _name, descr in _MANIFEST_ENTRY_RE.findall(manifest.group(1)):
                    fields_total += 1
                    kind = _classify(descr)
                    if kind == "unannotated":
                        continue
                    fields_annotated += 1
                    if kind in by_module and "fields" in by_module[kind]:
                        by_module[kind]["fields"] += 1
                        if "annotated" in by_module[kind]:
                            by_module[kind]["annotated"] += 1

    fields_pct = round(fields_annotated / fields_total * 100, 1) if fields_total else 0.0
    files_pct = round(files_manifested / files_total * 100, 1) if files_total else 0.0

    # Per-module percentages
    for key, info in by_module.items():
        total = info["fields"]
        ann = info.get("annotated", total)  # gymaxis_only has no separate annotated counter
        info["pct"] = round(ann / total * 100, 1) if total else 0.0

    # Section count in master doc — a proxy for how comprehensive the doc is.
    doc_sections = 0
    if MASTER_DOC.is_file():
        try:
            doc_sections = len({int(m.group(1)) for m in _SECTION_RE.finditer(MASTER_DOC.read_text(encoding="utf-8"))})
        except OSError:
            doc_sections = 0

    return {
        "fields_total":      fields_total,
        "fields_annotated":  fields_annotated,
        "fields_pct":        fields_pct,
        "files_total":       files_total,
        "files_manifested":  files_manifested,
        "files_pct":         files_pct,
        "by_module":         by_module,
        "doc_sections":      doc_sections,
        "computed_at":       datetime.now(timezone.utc).isoformat(),
    }
