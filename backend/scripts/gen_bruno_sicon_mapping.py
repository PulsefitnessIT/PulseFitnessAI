#!/usr/bin/env python3
"""Generate a secret-safe Bruno package + Sicon↔Pulse field-mapping artifacts.

Reads:
  • Sicon's official Bruno collection (their .bru request bodies) — the SOURCE of
    real Sicon WebAPI field names.
  • Our platform mapping table routes/sicon_mapping.py (SICON_FIELD_MAPPING).

Writes to OUT (default /app/integrations/sicon-bruno):
  • collection/…            copy of Sicon's Bruno collection
  • collection/environments/Plugin Platform.bru  (baseUrl/username/companyId +
    password via {{process.env.SICON_PASSWORD}} — NEVER the literal secret)
  • collection/.env.example  (blank SICON_PASSWORD placeholder)
  • collection/.gitignore    (ignores .env)
  • FIELD_MAPPING.md, mapping.csv  (Sicon field → Pulse field, per entity)

No credentials are ever written to any file.
"""
import csv
import json
import re
import shutil
import sys
from pathlib import Path

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/brunoSVC/bruno")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/app/integrations/sicon-bruno")

sys.path.insert(0, "/app/backend")
from routes.sicon_mapping import SICON_FIELD_MAPPING  # noqa: E402


def _leaf(sicon_field: str) -> str:
    """'case.CaseNumber' -> 'casenumber'; 'caseType.siSMCaseTypeId' -> 'sismcasetypeid'."""
    return re.sub(r"[^a-z0-9]", "", sicon_field.split(".")[-1].lower())


# Index our mapping by normalized leaf key of the Sicon field.
by_leaf: dict[str, list[dict]] = {}
for r in SICON_FIELD_MAPPING:
    by_leaf.setdefault(_leaf(r["sicon_field"]), []).append(r)


def parse_bru_body_keys(text: str) -> list[str]:
    """Extract JSON leaf keys from a .bru body:json block (best effort)."""
    m = re.search(r"body:json\s*\{(.*)\n\}", text, re.S)
    if not m:
        return []
    return re.findall(r'"([A-Za-z0-9_]+)"\s*:', m.group(1))


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "collection").mkdir(parents=True)
    # 1. copy Sicon's collection verbatim
    for p in SRC.rglob("*"):
        if p.is_file() and ".git" not in p.parts and p.suffix != ".zip":
            dest = OUT / "collection" / p.relative_to(SRC)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)

    # 2. secure environment (password via dotenv — never literal)
    envdir = OUT / "collection" / "environments"
    envdir.mkdir(exist_ok=True)
    (envdir / "Plugin Platform.bru").write_text(
        "vars {\n"
        "  baseUrl: http://localhost:51080\n"
        "  username: Administrator\n"
        "  companyId: 2\n"
        "  BEARER_TOKEN: \n"
        "}\n\n"
        "vars:secret [\n"
        "  password\n"
        "]\n\n"
        "docs {\n"
        "  password is read from the collection .env (SICON_PASSWORD) — never committed.\n"
        "  Run Auth > Authenticate to populate BEARER_TOKEN. Confirm the exact auth path\n"
        "  against the Sicon.WebApi.Platform collection Sicon provided.\n"
        "}\n", encoding="utf-8")
    (OUT / "collection" / ".env.example").write_text(
        "# Copy to .env and paste the Sicon password locally. .env is git-ignored.\n"
        "SICON_PASSWORD=\n", encoding="utf-8")
    (OUT / "collection" / ".gitignore").write_text(".env\n", encoding="utf-8")

    # 2b. best-effort Authenticate request (verify path w/ Sicon Platform collection)
    authdir = OUT / "collection" / "Auth"
    authdir.mkdir(exist_ok=True)
    (authdir / "Authenticate.bru").write_text(
        "meta {\n  name: Authenticate\n  type: http\n  seq: 1\n}\n\n"
        "post {\n  url: {{baseUrl}}/api/v1/Auth/Authenticate?companyId={{companyId}}\n"
        "  body: json\n  auth: none\n}\n\n"
        "headers {\n  Content-Type: application/json\n}\n\n"
        "body:json {\n  {\n    \"username\": \"{{username}}\",\n"
        "    \"password\": \"{{process.env.SICON_PASSWORD}}\"\n  }\n}\n\n"
        "script:post-response {\n"
        "  if (res.body && (res.body.token || res.body.access_token)) {\n"
        "    bru.setEnvVar('BEARER_TOKEN', res.body.token || res.body.access_token);\n"
        "  }\n}\n\n"
        "docs {\n  VERIFY the auth URL/body against the Sicon.WebApi.Platform collection.\n"
        "  Sets BEARER_TOKEN on the Plugin Platform environment on success.\n}\n",
        encoding="utf-8")

    # 3. join Sicon body fields -> our platform fields
    rows_out = []
    for bru in sorted(SRC.rglob("*.bru")):
        rel = bru.relative_to(SRC)
        entity = rel.parts[0] if len(rel.parts) > 1 else "Core"
        keys = parse_bru_body_keys(bru.read_text(encoding="utf-8", errors="ignore"))
        for k in keys:
            matches = by_leaf.get(_leaf(k), [])
            if matches:
                for mrow in matches:
                    rows_out.append({
                        "sicon_entity": entity, "sicon_request": str(rel),
                        "sicon_field": k, "pulse_field": mrow["gymaxis_field"],
                        "direction": mrow["direction"], "type": mrow["type"],
                        "status": "MAPPED", "notes": mrow["notes"],
                    })
            else:
                rows_out.append({
                    "sicon_entity": entity, "sicon_request": str(rel),
                    "sicon_field": k, "pulse_field": "", "direction": "",
                    "type": "", "status": "UNMAPPED", "notes": "No Pulse mapping — confirm with Sicon",
                })

    # de-dup identical rows
    seen = set(); uniq = []
    for r in rows_out:
        key = (r["sicon_request"], r["sicon_field"], r["pulse_field"])
        if key not in seen:
            seen.add(key); uniq.append(r)
    rows_out = uniq

    # 4. CSV
    with (OUT / "mapping.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sicon_entity", "sicon_request", "sicon_field",
                                          "pulse_field", "direction", "type", "status", "notes"])
        w.writeheader(); w.writerows(rows_out)

    # 5. Markdown grouped per entity
    md = ["# Sicon ↔ Pulse — Bruno field mapping", "",
          "Auto-generated by `backend/scripts/gen_bruno_sicon_mapping.py` from Sicon's",
          "Bruno collection bodies joined to `routes/sicon_mapping.py`. `→` push, `←` pull, `↔` both.", ""]
    ents = {}
    for r in rows_out:
        ents.setdefault(r["sicon_entity"], []).append(r)
    total = len(rows_out); mapped = sum(1 for r in rows_out if r["status"] == "MAPPED")
    md.append(f"**Coverage: {mapped}/{total} Sicon body fields have a Pulse mapping "
              f"({round(mapped/total*100)}%).**\n")
    for ent in sorted(ents):
        md.append(f"## {ent}")
        md.append("| Sicon field | Pulse field | Dir | Status | Notes |")
        md.append("|---|---|---|---|---|")
        for r in sorted(ents[ent], key=lambda x: (x["status"] != "UNMAPPED", x["sicon_field"])):
            md.append(f"| `{r['sicon_field']}` | `{r['pulse_field']}` | {r['direction']} "
                      f"| {r['status']} | {r['notes']} |")
        md.append("")
    (OUT / "FIELD_MAPPING.md").write_text("\n".join(md), encoding="utf-8")

    print(f"OUT: {OUT}")
    print(f"Sicon body fields: {total} | mapped: {mapped} | unmapped: {total - mapped}")
    print(f"entities: {sorted(ents)}")


if __name__ == "__main__":
    main()
