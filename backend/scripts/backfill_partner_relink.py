"""Iter 272 — backfill: relink stale/placeholder partner_engineers rows.

Proactively fixes the "Become a Partner Engineer / Apply now" loop for
engineers who haven't signed in yet, by relinking each partner row whose
``user_id`` is a ``pending:`` placeholder or a dead/stale id to the real
user that owns the row's email. Idempotent and conservative (never steals
a row from another live account). See utils/partner_claim.backfill_partner_relink.

Usage:
    python -m scripts.backfill_partner_relink --dry-run
    python -m scripts.backfill_partner_relink --commit
"""
from __future__ import annotations

import argparse
import asyncio
import sys


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit", action="store_true")
    args = p.parse_args()

    from utils.partner_claim import backfill_partner_relink

    stats = asyncio.get_event_loop().run_until_complete(
        backfill_partner_relink(dry_run=args.dry_run)
    )
    mode = "DRY-RUN" if args.dry_run else "COMMIT"
    print(f"== Partner relink backfill ({mode}) ==")
    for k, v in stats.items():
        print(f"   {k:>22}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
