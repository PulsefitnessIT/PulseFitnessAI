# Sicon WebAPI Platform — Bruno collection

Host-level Bruno collection for `Sicon.Sage200.WebApi.Platform`. Plugin collections (CRM, Approvals, etc.) call APIs on this host and should obtain a token here first.

## Setup (recommended)

1. In Bruno, open **Environments** → **Configure** → **Import** (global), then import:

   `Sicon.Sage200.WebApi.Platform/bruno/import/Plugin Platform.json`

2. Select the **Plugin Platform** global environment.
3. Set `baseUrl`, `username`, `password`, and Sage `companyId` (leave `BEARER_TOKEN` empty).
4. Open this collection (`Sicon.Sage200.WebApi.Platform/bruno`) and run **Auth → Authenticate**. On success it sets `BEARER_TOKEN` on the global environment via `bru.setGlobalEnvVar`.

`companyId` is the Sage company for the API connection (`?companyId=`). CRM entity ids (person, case, etc.) live as **collection variables** on each plugin collection, not in this global env.

## Using with plugin collections

Keep **Plugin Platform** selected as the global environment, then open a plugin collection (e.g. CRM at `Sicon.Sage200.CRM.WebAPI.Plugin/bruno`), set that collection’s entity id vars, and run requests.

- `Sicon.Sage200.WebApi.Platform.Approvals.Plugin/bruno`
- `Sicon.Sage200.WebApi.Platform.Common.Plugin/bruno`
- `Sicon.Sage200.WebApi.Platform.Configuration.Plugin/bruno`
- `Sicon.Sage200.WebApi.Platform.Core.Plugin/bruno`
- `Sicon.Sage200.WebApi.Plugin/bruno` (Example)
- CRM (external): `Sicon.Sage200.CRM.WebAPI.Plugin/bruno`

Do not commit real passwords or tokens. The JSON template in git stays empty for secrets.

## Maintenance

Auth and the importable global environment template live in this project. Plugin repos own only their controller routes and collection entity vars.
