# Superseded screens

These are no longer routed or served. They are kept here rather than deleted so
the work is recoverable, and so it is clear what happened to them.

| Screen | Why it went | Where the job is done now |
|---|---|---|
| `home.html` | Duplicated the Studio start screen (the entry point) and the Tracking screen (approvals in flight, activity). One home page, not two. | `/studio` |
| `workflows.html` | A no-code process designer that designed nothing: the board was static and saved no route. | `/templates` — Approval Routes, which do build real chains |
| `retention.html` | A retention console with no retention engine behind it. Every schedule, hold and disposition date on it was invented. | Retention policy is recorded on the approval and shown on `/track` |
| `records.html` | Physical records and warehousing: boxes, shelves and chain-of-custody for a module that does not exist. | — |
| `integrations.html` | A catalogue of SAP, Salesforce and SharePoint feeds with daily arrival counts, none of which were real. | `/upload` — the intake folder, which is real |

Their URLs still resolve: `app/main.py` 301-redirects each one to the screen
that does the nearest real job, so no bookmark or demo script breaks.

If any of these becomes a real module, bring the file back and add its route.
`home.html` in particular is complete and reads live data — it was retired for
being redundant, not for being wrong.
