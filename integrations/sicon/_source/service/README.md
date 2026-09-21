# Service Management WebAPI Plugin — Bruno collection

Manual smoke testing and shared docs for `Sicon.Sage200.ServiceManagement.WebAPI.Plugin` controllers.

Authentication and the shared host environment live in **Sicon.WebApi.Platform** (`Sicon.Sage200.WebApi.Platform/bruno`). This collection has no committed environment — only Service Management routes.

## Setup

1. Import the global environment from Platform (once per machine):

   Bruno → Environments → Configure → Import →  
   `Sicon.WebApi.Platform/Sicon.Sage200.WebApi.Platform/bruno/import/Plugin Platform.json`

2. Select **Plugin Platform** as the global environment; set `baseUrl`, `username`, `password`, and Sage `companyId` (sent as `?companyId=` on requests).
3. Open the Platform collection, run **Auth → Authenticate** (sets `BEARER_TOKEN` on the global env).
4. Open this collection (`Sicon.Sage200.ServiceManagement.WebAPI.Plugin/bruno`). Set **collection variables** for Service entity ids (Vars on the collection):

   - `caseId`, `caseNumber`, `appointmentId`, `timeBookingId`, `trackingNoteId`, `equipmentId`
   - `caseTypeId`, `priorityId`, `trackingStatusId`, `statusId`, `employeeId`

   Defaults are `0` so Put requests do not target live records until you set real ids.

5. Call Service requests (Bearer auth uses `{{BEARER_TOKEN}}`). **Core → Ping** is anonymous and does not require a Sage connection.

## Variable split

| Variable | Where | Used for |
|----------|--------|----------|
| `companyId` | Global (Plugin Platform) | Sage company connection: `?companyId=` |
| `caseId`, `appointmentId`, … | Service collection vars | Service entity ids in paths / filters |
| `baseUrl`, `BEARER_TOKEN`, credentials | Global | Host + auth |

You can override a collection var on an individual request if needed.

## Maintenance

When a plugin controller action is added, renamed, or removed, update the matching folder under this collection in the same change. Do not add platform Auth or a committed host environment here — keep those in the Platform Bruno collection.
