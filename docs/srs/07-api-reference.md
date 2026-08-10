# 07 · API Reference

> **Audience:** developers and integrators.
> Live interactive documentation is served at **`/docs`** (Swagger) and
> **`/redoc`**; the OpenAPI schema is at **`/openapi.json`**. This document adds
> the intent, the authorisation rules and the failure behaviour that the
> generated schema cannot express.

---

## 1. Conventions

### 1.1 Base

All API routes are under `/api`. UI page routes are documented in
[doc 08](08-frontend-design.md).

### 1.2 Authentication

Every protected endpoint accepts **either**:

```
Authorization: Bearer <jwt>          # 30-minute lifetime
```
**or**
```
Cookie: session_token=<token>        # 24-hour lifetime, HttpOnly
```

JWT is tried first, the session is the fallback.

### 1.3 CSRF

Every `POST` / `PUT` / `DELETE` / `PATCH` from a browser must send:

```
X-CSRF-Token: <token from GET /api/csrf-token>
```

Excluded: login, logout, check-session, both setup endpoints, `/api/health`,
`/api/settings/test/ai`, `/docs`, `/openapi.json`, `/redoc`, `/api/csrf-token`.

### 1.4 Authorisation legend

| Symbol | Meaning |
|---|---|
| 🔓 | No authentication |
| 🔑 | Any authenticated user |
| 📖 | `documents.read` (roles: reader, contributor, approver, signatory) |
| ✏️ | `documents.create` / `documents.update` (contributor and above) |
| 🗑️ | `documents.delete` — ⚠️ **not granted by any standard role; admin only in practice** |
| ✅ | `documents.approve` (approver, signatory) |
| 👑 | Administrator (`is_admin`) |

### 1.5 Common status codes

| Code | Meaning |
|---|---|
| 400 | Validation failed, or a business rule refused the request (the message says which) |
| 401 | Not authenticated |
| 403 | Authenticated but not permitted, or CSRF validation failed |
| 404 | Not found |
| 413 | Payload too large (body > 900 000 chars, file > `max_file_size`) |
| 422 | Request body failed Pydantic validation |
| 429 | Rate limited — see `Retry-After`, `X-RateLimit-*` headers |
| 500 | Unhandled error (logged with a traceback) |

---

## 2. Authentication — `/api/auth`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/csrf-token` | 🔓 | Read the CSRF token from the cookie |
| POST | `/login` | 🔓 | Sign in with **username or email** + password |
| POST | `/logout` | 🔑 | Delete the session, clear the cookie |
| GET | `/me` | 🔑 | Current user (`UserResponse`) |
| POST | `/change-password` | 🔑 | Requires the current password |
| GET | `/check-session` | 🔑 | `{valid, user{…}}`; 401 when expired |
| GET | `/setup/check` | 🔓 | `{setup_complete, user_count}` |
| POST | `/setup/initial-user` | 🔓 | **Only when zero users exist.** Creates the first admin, the default roles and the default doctypes |
| POST | `/users` | 👑 | Create a user |
| GET | `/users` | 👑 | List users |
| GET | `/users/{user_id}` | 👑 | Read a user |
| PUT | `/users/{user_id}` | 👑 | Update; re-applies the standard role if authority changed |
| DELETE | `/users/{user_id}` | 👑 | Delete; **refuses self-deletion** |

**`POST /login`**
```jsonc
// request
{ "username": "s.iyer", "password": "…" }
// response 200
{ "access_token": "eyJ…", "token_type": "bearer", "must_change_password": false }
// + Set-Cookie: session_token=…; HttpOnly; SameSite=Lax
```
Failures are recorded as `login_failed` audit events and count against the
5-per-5-minute budget; a success clears that IP's failures.

**`POST /users`** accepts `username`, `email`, `password`, `full_name`,
`is_admin`, `department`, `job_title`, `can_approve`, `can_sign`.
`can_sign` is forced true for an administrator.

---

## 3. Documents — `/api/documents`

### 3.1 Listing and reading

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/filter-options` | 📖 | Correspondents, doctypes, tags and date ranges for the filter UI |
| GET | `/` | 📖 | List with filters and pagination |
| GET | `/{id}` | 📖 | One document |
| GET | `/{id}/text` | 📖 | Extracted text |
| GET | `/{id}/file` | 📖 | Inline file stream |
| GET | `/{id}/download` | 📖 | Attachment download (audited) |
| GET | `/{id}/preview-info` | 📖 | What the viewer needs: page count, renderability, mime |
| GET | `/{id}/thumbnail` | 📖 | Cached first-page PNG |
| POST | `/{id}/view` | 📖 | Increment `view_count`, stamp `last_viewed` |
| GET | `/stats/overview` | 📖 | Counts by status, type, correspondent |

### 3.2 Mutation

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/upload` | ✏️ | Multipart upload → staging. Returns `status: uploaded` or `duplicate` |
| PUT | `/{id}` | ✏️ | Update metadata (title, summary, date, correspondent, doctype, tags, notes, reminder, tax flag) |
| DELETE | `/{id}` | 🗑️ | Delete the record, the file and the vectors |
| PUT | `/{id}/notes` · GET `/{id}/notes` | ✏️ / 📖 | Free-text notes |

**`POST /upload`** — `multipart/form-data`, field `file`.
```jsonc
// new
{ "message": "File uploaded successfully to staging: invoice.pdf",
  "status": "uploaded", "filename": "invoice.pdf" }
// already present
{ "message": "This file is already in the repository as “Invoice 4471”.",
  "status": "duplicate", "document_id": "…", "filename": "invoice.pdf" }
```
Processing is asynchronous — the watcher picks the file up. Poll
`GET /{id}/status`.

### 3.3 Processing

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/staging/files` | 📖 | What is sitting in staging |
| POST | `/process-staging` | ✏️ | Force a staging sweep |
| GET | `/{id}/status` | 📖 | `ocr_status`, `ai_status`, extracted data |
| GET | `/{id}/logs` | 📖 | Per-document processing log |
| POST | `/{id}/reprocess` | ✏️ | Re-run everything |
| POST | `/{id}/reprocess-ai` | ✏️ | Classification only |
| POST | `/{id}/reprocess-ocr` | ✏️ | Text extraction only |
| POST | `/{id}/reprocess-vector` | ✏️ | Re-index only |
| POST | `/cleanup/orphaned` | 🗑️ | Remove records whose file is gone |

### 3.4 Versions

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/{id}/versions` | 📖 | History, newest first |
| GET | `/{id}/versions/{version_id}/file` | 📖 | That version's bytes |
| POST | `/{id}/versions/{version_id}/restore` | ✏️ | **Forward-only** restore; writes a new version |

### 3.5 Tags and relations

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/{id}/tags` | ✏️ | Add one (`tag_name`) or many (`tag_names[]`); returns added / already present / the full list |
| POST | `/{id}/tags/{tag_id}` | ✏️ | Attach an existing tag |
| DELETE | `/{id}/tags/{tag_id}` | ✏️ | Detach |
| GET | `/{id}/relations` | 📖 | Linked documents |
| POST | `/{id}/relations/{other_id}` | ✏️ | Link |
| DELETE | `/{id}/relations/{other_id}` | ✏️ | Unlink |
| GET | `/{id}/similar` | 📖 | Vector-proximity recommendations |

### 3.6 Approval shortcuts

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/{id}/approve` | ✅ | Simple approval flag (distinct from the workflow engine) |
| GET | `/{id}/approval-status` | 📖 | Current approval state |

---

## 4. Document Studio — `/api/studio`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/templates` | 📖 | All letterhead specs + the default id |
| GET | `/templates/{id}/starter` | 📖 | The first draft for a blank page on that template |
| GET | `/assets?kind=` | 📖 | Image library (built-ins + this user's uploads) |
| GET | `/assets/{id}/file` | 📖 | Serve one image |
| POST | `/assets` | ✏️ | Upload an image (multipart: `file`, `name`, `kind`) |
| DELETE | `/assets/{id}` | ✏️ | Delete — owner or admin only |
| GET | `/ai/actions` | 📖 | The action menu, so it cannot drift from the API |
| POST | `/ai` | 📖 | Run one action |
| GET | `/drafts` | 📖 | This user's 30 most recent drafts |
| POST | `/drafts` | ✏️ | Create |
| GET | `/drafts/{id}` | 📖 | Read — owner or admin only |
| PUT | `/drafts/{id}` | ✏️ | **Autosave target** |
| DELETE | `/drafts/{id}` | ✏️ | Discard |
| GET | `/source/{document_id}` | 📖 | What to load when "Edit" is pressed |
| POST | `/preview` | 📖 | Render the PDF without saving |
| POST | `/publish` | ✏️ | File it in the repository |

**`POST /api/studio/ai`**
```jsonc
{ "action": "grammar",          // summarize|regenerate|grammar|formal|concise|
                                // expand|bullets|continue|translate|draft|custom
  "text": "<p>…</p>",
  "instruction": "…",           // required for custom and draft
  "target": "German",           // required for translate
  "title": "…" }
→ { "html": "<p>…</p>", "text": "…", "replaces": true, "action": "grammar" }
```

**`GET /api/studio/source/{id}`** — `lossless: true` for a composed document
(the original body comes back exactly); `lossless: false` for an uploaded file,
with a `notice` explaining that the extracted text has been laid out for editing
and that saving creates a new version.

**`POST /api/studio/publish`**
```jsonc
{ "title": "Supply agreement", "template_id": "harman-letterhead",
  "html": "<h2>…</h2>", "draft_id": "…", "source_document_id": null,
  "meta": { "doctype_id": "", "doctype_name": "Contract",
            "correspondent_id": "", "correspondent_name": "Acme Ltd",
            "document_date": "2026-08-07", "department": "Legal",
            "sensitivity": "internal", "tags": ["supply","2026"] } }
→ { "id": "…", "title": "…", "version": "1.0", "revision_of": null,
    "pages": 3, "file_size": 84213,
    "url": "/documents/detail?id=…",
    "message": "Document saved to the repository" }
```
Classification and indexing continue in the background after this returns.

---

## 5. Approval workflow — `/api/workflow`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/` (and `""`) | ✏️ | Build a workflow and start it |
| GET | `/` (and `""`) | 📖 | List, filterable; max 500 |
| GET | `/stats` | 📖 | Counts by status, overdue, by priority |
| GET | `/tasks/mine` | 🔑 | Steps waiting on the caller, soonest deadline first |
| GET | `/by-document/{document_id}` | 📖 | The live workflow for a document |
| GET | `/{workflow_id}` | 📖 | Full workflow with steps, signatures and events |
| POST | `/{workflow_id}/steps/{step_id}/decide` | 🔑 | Approve / reject / request changes |
| POST | `/{workflow_id}/resubmit` | ✏️ | After changes were requested — restarts from step 1 |
| POST | `/{workflow_id}/remind` | ✏️ | Records a reminder event ⚠️ *no email is sent* |
| POST | `/{workflow_id}/cancel` | ✏️ | Cancel (refused once approved or published) |
| GET | `/people/approvers` | 📖 | People who may be assigned, with their sign authority |

**`POST /api/workflow`**
```jsonc
{ "document_id": "…", "name": "Contract approval",
  "priority": "high",                 // low|normal|high|urgent
  "department": "Legal", "due_date": "2026-08-20",
  "retention_policy": "7 years", "after_approval": "publish", "notes": "",
  "start": true,
  "steps": [
    { "name": "Legal review", "assignee_ids": ["u1","u2","u3"],
      "requires_signature": true, "approval_mode": "all", "sla": "2 days" },
    { "name": "Final sign-off", "department": "Legal", "role": "Head of Legal",
      "requires_signature": true, "approval_mode": "any", "sla": "1 day" }
  ] }
```
**400** if a step requires a signature and any named assignee lacks `can_sign` —
the message names them and offers the three ways out.

**`POST /{wf}/steps/{step}/decide`**
```jsonc
{ "action": "approve",              // approve | reject | changes
  "comment": "Terms are acceptable.",
  "reason": "",                     // REQUIRED for reject
  "signature": { "dataUrl": "data:image/png;base64,…",
                 "name": "Sudha Iyer", "designation": "Head of Finance",
                 "method": "draw" } }
```
**400** with a human-readable reason when refused: not the current step, already
decided, not permitted, assigned to someone else, wrong department, signature
required but not permitted, or signature required but not supplied.

**Workflow response shape** (from `_workflow_json`) — every step carries
`can_act` and `blocked_reason` resolved server-side, plus `approved_by[]` and
`outstanding[]` for `all`-mode steps.

---

## 6. Signatures — `/api/signatures`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/{workflow_id}/layout` | 📖 | Blocks with resolved placement + page geometry |
| PUT | `/{workflow_id}/layout` | ✏️ | Save dragged placement (page fractions) |
| POST | `/{workflow_id}/layout/reset` | ✏️ | Back to automatic layout |
| PUT | `/{workflow_id}/designation` | ✏️ | Correct a signatory's designation |
| GET | `/{workflow_id}/preview` | 📖 | The stamped PDF, without publishing |
| GET | `/{workflow_id}/page/{page_number}` | 📖 | That page rendered as a PNG, for the editor |

---

## 7. Publishing — `/api/publishing`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/queue?q=` | 📖 | `{ready[], published[], ready_count, published_count}` |
| POST | `/{workflow_id}/publish` | ✏️ | Release; locks the approved version, stamps signatures, captures the signed version |
| POST | `/{workflow_id}/unpublish` | ✏️ | Withdraw the release; the approval stands |
| GET | `/export/{document_id}?format=pdf\|docx\|txt&version_id=` | 📖 | Export |
| GET | `/formats/{document_id}` | 📖 | Which exports work for this document, and why not for the others |

---

## 8. Search — `/api/search`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/` | 📖 | Search |
| GET | `/suggestions?q=` | 📖 | Correspondent / doctype / tag suggestions |
| POST | `/rag` | 📖 | Ask a question across the repository |
| GET | `/test-semantic` · `/test-fulltext` | 📖 | Diagnostics |
| GET | `/vector-stats` | 📖 | Collection size and name |
| POST | `/rebuild-embeddings` | ✏️ | Re-index |

**`POST /api/search`**
```jsonc
{ "query": "payment terms",
  "limit": 20, "offset": 0, "use_semantic_search": true,
  "filters": {
    "correspondent_ids": [], "doctype_ids": [], "tag_ids": [],
    "date_range": "last_30_days",   // or date_from / date_to
    "is_tax_relevant": null,
    "reminder_filter": null          // has | overdue | none
  } }
→ { "documents": [ … ], "total_count": 42, "query": "…", "filters": { … } }
```
Named date ranges: `today`, `yesterday`, `last_7_days`, `last_30_days`,
`last_90_days`, `this_week`, `last_week`, `this_month`, `last_month`,
`this_quarter`, `last_quarter`, `this_year`, `last_year`, `last_2_years`.

**`POST /api/search/rag`**
```jsonc
{ "question": "What are our standard payment terms with Indian suppliers?",
  "max_documents": 5, "document_ids": [], "filters": { … } }
→ { "answer": "…text with [Doc1] markers…",
    "sources": [ /* exactly the documents sent, in the order numbered */ ],
    "confidence": 0.8 }
```

---

## 9. Metadata

### Correspondents — `/api/correspondents`
`GET /` (with counts) · `GET /{id}` · `POST /` · `PUT /{id}` ·
`DELETE /{id}` ⚠️ requires `correspondents.delete` — **admin only in practice** ·
`GET /{id}/documents`

### Document types — `/api/doctypes`
Same shape, `doctypes.*` permissions.

### Tags — `/api/tags`
Same shape, plus `GET /popular/`.

---

## 10. Audit — `/api/audit`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` (and `""`) | 📖 | `?q=&action=&days=1..365&limit=≤1000` |
| GET | `/summary` | 📖 | Counts by action over the window |

> ⚠️ The activity log requires only `documents.read`, so **any signed-in user can
> read it via the API** — even though the `/audit` **page** is admin-gated. See
> doc 09 §6.

---

## 11. Settings — `/api/settings` (👑 throughout)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/` | Settings subsystem health |
| GET | `/` | Current settings |
| GET | `/extended` · PUT/POST `/extended` | Full settings read/write |
| GET | `/setup-config` · POST `/save-config` | Setup wizard |
| GET | `/models` | Available models per provider |
| POST | `/config/groq` · `/config/openai` | Provider credentials |
| POST | `/config/ai-limits` | Token, temperature and timeout budgets |
| POST | `/config/file-settings` | Max size, allowed extensions |
| POST | `/config/ocr-tools` | Tesseract and Poppler paths |
| POST | `/config/folders` | Staging, storage, data, logs, backups |
| GET | `/ai-provider/status` | Which provider is live and whether it answers |
| POST | `/ai-provider/switch` | Change provider |
| POST | `/test/ai` | Connection test (CSRF-exempt) |
| GET | `/export` · POST `/import` | Configuration as JSON |
| POST | `/backup` · GET `/backup/{id}` | Settings backup |
| GET | `/logs/download` | Download logs |
| POST | `/initialize-defaults` | Re-seed default settings |
| GET | `/debug/azure` | Azure diagnostics |

---

## 12. Backup — `/api/backup` (👑 throughout)

`GET /status` · `POST /configure` · `POST /start` · `POST /stop` ·
`POST /create` · `GET /list` · `POST /restore/{backup_filename}` ·
`DELETE /delete/{backup_filename}` · `GET /recommendations` · `GET /health`

Filenames are validated against path traversal.

---

## 13. Health — `/api/health`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | 🔓 | Full health: DB, vectors, AI, OCR, disk, folders |
| GET | `/simple` | 🔓 | `{status: healthy}` |
| GET | `/liveness` | 🔓 | Process alive |
| GET | `/readiness` | 🔓 | Ready to serve — **use this to gate traffic during the ~2 s deferred start-up** |
| GET | `/startup` | 🔓 | Start-up progress |
| GET | `/metrics` | 👑 | CPU, memory, disk, document counts |
| GET | `/security` | 👑 | Security posture |

Also `GET /health` and `GET /api/health` at the app root return a simple
`{status: healthy}`.

---

## 14. Security — `/api/security`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/scan/directories` | 👑 | Directory permission scan |
| GET | `/permissions/check` | 📖 | The caller's effective permissions |
| GET | `/audit/recent-uploads` | 👑 | Recent uploads |
| GET | `/audit/access-logs` | 👑 | Access logs |
| POST | `/quarantine/{document_id}` | 👑 | Quarantine a document |

---

## 15. Admin utilities — `/api/admin` (👑 throughout)

`POST /fix-permissions/{username}` · `GET /check-permissions/{username}` ·
`POST /make-admin/{username}`

> ⚠️ These are repair tools from an earlier era. `fix-permissions` grants the
> **legacy `editor` role**, which is outside the standard four and is therefore
> never removed by `apply_role`. Prefer the standard role model. See doc 11.

---

## 16. Integration examples

```bash
# 1 · Sign in and keep the cookie jar
curl -c jar.txt -X POST http://localhost:8000/api/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"Aryan","password":"…"}'

# 2 · CSRF token for state-changing calls
TOKEN=$(curl -b jar.txt -c jar.txt -s http://localhost:8000/api/csrf-token | jq -r .csrf_token)

# 3 · Upload
curl -b jar.txt -H "X-CSRF-Token: $TOKEN" \
     -F 'file=@invoice.pdf' http://localhost:8000/api/documents/upload

# 4 · Semantic search
curl -b jar.txt -H "X-CSRF-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"query":"payment terms","limit":10}' \
     http://localhost:8000/api/search/

# 5 · Ask a question
curl -b jar.txt -H "X-CSRF-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"question":"Which contracts expire this quarter?","max_documents":5}' \
     http://localhost:8000/api/search/rag

# 6 · Start an approval
curl -b jar.txt -H "X-CSRF-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"document_id":"…","steps":[{"name":"Approve","assignee_ids":["…"],
          "requires_signature":true,"approval_mode":"all","sla":"2 days"}]}' \
     http://localhost:8000/api/workflow

# Script clients can use the JWT instead of the cookie + CSRF pair:
curl -H "Authorization: Bearer $JWT" http://localhost:8000/api/documents/
```
