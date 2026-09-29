Subject: PulseFitness.ai ↔ Sicon Service / Sage 200 WebAPI — Requirements to Move to Live Integration

Hi [Sicon contact name],

We've completed and successfully validated the read-side of the PulseFitness.ai integration against the Sicon Service WebAPI using your Bruno collection (authentication, reference data, equipment pagination, case search, and the Case → Equipment → Appointment → Resource → Time Booking relationship chain all confirmed working). We're now ready to connect PulseFitness.ai to a live Sicon environment.

To do that safely and reliably, we need a few things confirmed or provided from your side. I've grouped them by priority.

── 1. Connectivity (blocker for go-live) ──────────────────────────
Our platform is cloud-hosted and makes all Sicon calls server-to-server (credentials and bearer tokens are never exposed to the browser). Your current WebAPI is at http://localhost:51080, which is only reachable on your local network.

Please confirm:
  • The production/externally-reachable base URL and port for the Sicon Service WebAPI.
  • How you'd like us to connect securely — options we can support:
      - A public HTTPS endpoint restricted by IP allow-list (we can provide our fixed egress IPs), or
      - A site-to-site VPN, or
      - A reverse proxy / API gateway you host.
  • A valid TLS/SSL certificate on the endpoint (we verify certificates).

── 2. Authentication ──────────────────────────────────────────────
  • Confirm the production authentication endpoint (we currently use POST /api/v1/authentication/authenticate returning accessToken).
  • Bearer token lifetime (TTL) so we can cache efficiently and re-authenticate before expiry. We already re-authenticate once automatically on a 401 and retry.
  • A dedicated integration service account (username/password) for PulseFitness.ai, rather than a named user, plus the companyId to use in production.

── 3. Contract Management plugin (currently unavailable) ───────────
The Sicon Contract Management WebAPI returns 404 on the current host:
  • /api/v1/SiconContract/Ping
  • /api/v1/SiconContract/Contract
  • /api/v1/SiconContract/Contract/{contractId}

Please confirm:
  • Whether the Contract Management WebAPI plugin/controller is installed and enabled.
  • If it runs on a different host/port/base URL, please provide it (we support a separate contract base URL).
  • The intended contract data model (Customer → Site → Equipment → Contract → Contract Line → Cover Type → SLA) so we can map cover/entitlement correctly when it becomes available.

We will NOT infer contract cover from case "project" descriptions (e.g. "Warranty Project", "Gold Contract"), as these have proven unreliable. Contract entitlement will only ever come from the Contract API.

── 4. Data volume, pagination & incremental sync ──────────────────
We understand the estate is ~111,000+ equipment records.
  • Confirm the recommended page size ($max) for large pulls and any per-minute/second rate limits or concurrency caps so we can stay within them.
  • Confirm the paging format is stable in production: query=$skip=N%26$max=50 (the ampersand between $skip and $max is intentionally URL-encoded as %26 inside the single "query" parameter).
  • Do the list endpoints (Equipment, CaseSearch, TrackingNote, Appointment) support a reliable "modified since" / last-changed-date filter? If so, please share the exact parameter name and format — this lets us run fast incremental syncs instead of full estate sweeps.

── 5. Field semantics & identifiers ───────────────────────────────
  • Equipment "make": we see values such as 200E-AAA, 260G-AAP, 576H-ADS. These look like item/product codes, not manufacturer names. Please confirm what this field represents, and whether an authoritative manufacturer field exists we should use instead. (We currently store your value verbatim and never treat it as a manufacturer.)
  • Confirm the permanent/immutable keys we should rely on: siconEquipmentId (equipment), siSMCaseId (cases — we never key on caseNumber), plus the stable identifiers for Appointments, Tracking Notes, and Resources.
  • Engineer/Resource mapping: please confirm which identifier(s) on an Appointment Resource we should use to map to our engineers (e.g. employee id, employee number, email), so a Sicon resource resolves to the correct person in PulseFitness.ai.

── 6. Minor / diagnostic ──────────────────────────────────────────
  • TrackingStatus GetOne: we saw a single ID-extraction quirk in the Bruno test script (not an API failure). No action needed unless you're aware of a known issue — our production parser handles it defensively.

── 7. Phase 2 — future write-back (NOT enabled yet) ───────────────
The current integration is strictly READ-ONLY (SICON_ALLOW_WRITES=false); no data is written back to Sicon. For planning only, when we later enable controlled write-back (cases, appointments, tracking notes, time bookings), please confirm:
  • Whether PUT behaves as a full replacement or a partial update (we will design for full-replacement semantics unless told otherwise).
  • Availability of a test/sandbox company or disposable test records so we can validate writes without touching live data.

── Summary of what we need first (to start live read-only sync) ────
  1) Externally-reachable production base URL + secure connection method (IP allow-list / VPN).
  2) Integration service account credentials + production companyId + token TTL.
  3) Confirmation of rate limits / recommended page size, and whether "modified since" filtering is available.
Everything else (contracts, write-back) can follow.

Happy to jump on a short call to align on the connectivity approach. Thanks very much for your help getting this live.

Best regards,
[Your name]
[Your title] — PulseFitness.ai / GymAxisAI
[Phone] · [Email]
