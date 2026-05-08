"""Iter 215bz — MongoDB backup script for production deployments.

Produces a timestamped, gzipped `mongodump` of the entire database to
`./backups/`. Designed to be invoked from a cron job or systemd timer
(e.g. nightly). Retains the most recent N backups and prunes older.

Usage:
    python -m scripts.mongo_backup --retain 7
    python -m scripts.mongo_backup --retain 14 --dest /var/backups/gymaxis

Env required: MONGO_URL, DB_NAME (read from backend/.env).

Operator runbook for a production deploy:
    1. Cron job: 02:00 UTC nightly → run this script with --retain 14
    2. After write, copy to off-site (S3/B2/etc) with bucket lifecycle
       to glacier after 7 days
    3. Test restore monthly by running `mongorestore` in a staging env
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retain", type=int, default=7,
                        help="How many recent backups to keep (default 7)")
    parser.add_argument("--dest", default=str(Path(__file__).parent.parent / "backups"),
                        help="Backup destination directory")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name   = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL and DB_NAME must be set", file=sys.stderr)
        return 2

    if not shutil.which("mongodump"):
        print("ERROR: mongodump not on PATH. Install with `apt install mongodb-database-tools`",
              file=sys.stderr)
        return 3

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = dest / f"{db_name}-{ts}.gz"

    cmd = ["mongodump", f"--uri={mongo_url}", f"--db={db_name}",
           f"--archive={archive}", "--gzip"]
    print(f"Running: mongodump → {archive}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"mongodump failed:\n{res.stderr}", file=sys.stderr)
        return res.returncode

    size_mb = archive.stat().st_size / 1024 / 1024
    print(f"OK — wrote {size_mb:.1f} MB to {archive.name}")

    # Retention
    backups = sorted(
        [p for p in dest.iterdir() if p.name.startswith(f"{db_name}-") and p.suffix == ".gz"],
        reverse=True,
    )
    pruned = 0
    for old in backups[args.retain:]:
        old.unlink()
        pruned += 1
    if pruned:
        print(f"Pruned {pruned} backups older than --retain={args.retain}")
    print(f"Retained {min(len(backups), args.retain)} backup(s) in {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
