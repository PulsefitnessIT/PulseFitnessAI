# Production Mongo → Atlas migration runbook (zero data loss)

Goal: move the live production database from Emergent's managed MongoDB to YOUR
OWN Atlas cluster, so the pulsefitness.ai and MODService deployments can share it.

## GOLDEN RULES
1. The SOURCE (managed prod) is only ever READ. Never run --drop, delete, or
   restore AGAINST the source. This guarantees rollback.
2. mongodump is a point-in-time snapshot, NOT continuous sync. Writes made to the
   source AFTER the dump are NOT migrated. => do the final dump inside a short
   write-freeze (maintenance window), then cut over immediately.
3. Restore into a FRESH/EMPTY Atlas DB. Verify collection counts match before cutover.

--------------------------------------------------------------------------------
## STEP 0 — Install the official MongoDB Database Tools (on your laptop/VM)
mongodump/mongorestore ship in "mongodb-database-tools" (separate from the server).
- macOS:   brew install mongodb-database-tools
- Ubuntu:  https://www.mongodb.com/try/download/database-tools  (or apt)
- Verify:  mongodump --version   &&   mongorestore --version
Also handy: mongosh (MongoDB shell) for the count checks.

## STEP 1 — Get the SOURCE (managed prod) connection details
In your MAIN pulsefitness.ai job: Manage Publishes -> Secrets -> System keys.
Copy the exact values of:
  - MONGO_URL   (this is SRC_URI)
  - DB_NAME     (this is SRC_DB)
NOTE: If the managed MONGO_URL is only reachable from inside the deployment
network (connection refused/timeout from your laptop), do NOT guess — message
support@emergent.sh and ask for an externally-reachable read connection string
for a one-off migration, or ask them to run the dump for you. (I'll help you draft
that message if needed.)

## STEP 2 — Get the TARGET (Atlas) connection details
In Atlas: cluster -> Connect -> Drivers -> copy the mongodb+srv://... string.
  - Replace <password> with your real DB-user password  => DST_URI
  - Pick a DB name (reuse SRC_DB, or e.g. pulse_prod)     => DST_DB
Atlas -> Network Access -> add YOUR CURRENT IP (so your laptop can restore).

## STEP 3 — Set shell variables (edit these)
```bash
export SRC_URI='<paste managed MONGO_URL>'
export SRC_DB='<paste managed DB_NAME>'
export DST_URI='mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority'
export DST_DB='pulse_prod'          # or same as SRC_DB
export DUMP_DIR="./pulse_dump_$(date +%Y%m%d_%H%M%S)"
```

## STEP 4 — DRY-RUN dump (rehearsal, NOT the final one)
Do a full rehearsal first WITHOUT freezing writes, so you know the commands work,
how long it takes, and roughly how big it is.
```bash
mongodump --uri="$SRC_URI" --db="$SRC_DB" --gzip --out="$DUMP_DIR"
ls -lah "$DUMP_DIR/$SRC_DB" | head
```
Then restore into Atlas to validate the pipeline end-to-end:
```bash
mongorestore --uri="$DST_URI" --gzip \
  --nsInclude="$SRC_DB.*" \
  --nsFrom="$SRC_DB.*" --nsTo="$DST_DB.*" \
  --drop \
  --dir="$DUMP_DIR"
```
- --drop clears each target collection before load => safe & idempotent on an
  EMPTY/rehearsal Atlas DB, and lets you re-run cleanly. NEVER point --drop at the source.
- --nsFrom/--nsTo renames the DB during restore (omit both if DST_DB == SRC_DB).

## STEP 5 — Verify the rehearsal (counts must match)
Run this against BOTH and compare. Using mongosh:
```bash
# SOURCE counts
mongosh "$SRC_URI" --quiet --eval '
  db = db.getSiblingDB(process.env.SRC_DB);
  db.getCollectionNames().sort().forEach(c => print(c, db[c].countDocuments()));
' SRC_DB="$SRC_DB"

# TARGET counts
mongosh "$DST_URI" --quiet --eval '
  db = db.getSiblingDB(process.env.DST_DB);
  db.getCollectionNames().sort().forEach(c => print(c, db[c].countDocuments()));
' DST_DB="$DST_DB"
```
Diff the two lists — every collection and count must match. Investigate any gap
before proceeding. (Also spot-check indexes: mongorestore restores them from the
dump automatically; confirm with db.<coll>.getIndexes() on a key collection.)

--------------------------------------------------------------------------------
## STEP 6 — THE REAL CUTOVER (zero data loss)  ⚠️ maintenance window
This is the only part that must be done carefully & quickly.

6a. Announce a short maintenance window (5–20 min depending on data size from
    your rehearsal timing).

6b. FREEZE WRITES to the source. Easiest reliable option on Emergent: temporarily
    PAUSE / stop the main pulsefitness.ai deployment (Manage Publishes) so nothing
    writes to the managed DB. (If you prefer not to pause, put the app in a
    read-only/maintenance state — but pausing is the simplest guarantee.)

6c. FINAL dump + restore (same commands as STEP 4, fresh $DUMP_DIR). Because
    writes are frozen, this snapshot is complete with no trailing writes lost.

6d. Re-run STEP 5 count verification on the FINAL data. Must match.

6e. Repoint BOTH deployments to Atlas:
    Manage Publishes -> Secrets -> System keys on EACH deployment:
      MONGO_URL = $DST_URI
      DB_NAME   = $DST_DB
    (MODService deployment also keeps REACT_APP_PORTAL_MODE=modservice etc.)

6f. Ensure Atlas Network Access allowlists BOTH deployments' egress IPs
    (https://app.emergent.sh/ip-addresses) — do this BEFORE republishing.

6g. Republish the main deployment (un-pause). Republish MODService too.

6h. Smoke test on the LIVE site: log in, load the dashboard, view a few records,
    create ONE harmless record and confirm it lands in Atlas. End maintenance.

--------------------------------------------------------------------------------
## STEP 7 — ROLLBACK (if anything looks wrong)
You changed nothing on the source, so rollback is instant:
  - Set MONGO_URL/DB_NAME back to the original managed values on the deployment(s)
  - Republish
The old managed DB still holds all data exactly as before the cutover.

## STEP 8 — Retire the old DB (only after days of confidence)
Keep the managed DB untouched for at least a few days/weeks as a safety net.
Also keep the final $DUMP_DIR archived offline as a cold backup.

--------------------------------------------------------------------------------
## Common gotchas
- Tools version: use current mongodb-database-tools; very old mongodump can't read
  newer servers. If you hit a compatibility error, upgrade the tools.
- Auth/db in URI: if SRC_URI already ends with /<db>?..., you can drop --db and use
  --nsInclude only; keep it explicit to avoid dumping admin/local.
- TLS: Atlas requires TLS (handled automatically by mongodb+srv). If the managed
  source needs ?tls=true or ?authSource=admin, keep those params in SRC_URI exactly
  as shown in Secrets.
- Large data: add --numParallelCollections=4 to speed up; add --readPreference=secondary
  if the source is a replica set and you want to avoid loading the primary.
- Never migrate the admin/local/config databases — restore only your app DB namespace.
