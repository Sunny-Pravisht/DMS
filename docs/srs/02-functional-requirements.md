# 02 · Functional Requirements

> **Audience:** business analysts, QA, project managers, developers.
> Every requirement is numbered, testable, and carries a pointer to the code
> that implements it. ⚠️ marks a gap or limitation.

---

## Requirement numbering

`FR-<module>.<n>` — for example **FR-3.4** is the fourth requirement of module 3
(Approval Workflow). The traceability matrix at the end maps every requirement
to its implementation and its test.

| Module | Area |
|---|---|
| FR-1 | Authentication, users and authorisation |
| FR-2 | Document capture and processing |
| FR-3 | Approval workflow |
| FR-4 | Digital signatures |
| FR-5 | Document Studio (authoring) |
| FR-6 | Publishing and export |
| FR-7 | Versioning |
| FR-8 | Search and retrieval |
| FR-9 | AI assistant (RAG) |
| FR-10 | Metadata management (correspondents, doctypes, tags) |
| FR-11 | Audit and activity log |
| FR-12 | Settings and configuration |
| FR-13 | Backup and restore |
| FR-14 | Health, monitoring and administration |

---

## FR-1 · Authentication, users and authorisation

### FR-1.1 First-run setup
On a database with zero users, the system **shall** allow one unauthenticated
call to create the first administrator, and **shall** refuse every subsequent
attempt.
→ `app/routers/auth.py:381` · The check is `db.query(User).count() > 0`.

### FR-1.2 Sign in
A user **shall** authenticate with **username or email** plus password. On
success the system issues:
- a **session cookie** (`session_token`, HttpOnly, 24-hour lifetime, `Secure` in production mode), and
- a **JWT bearer token** (30-minute lifetime) in the response body.

→ `app/routers/auth.py:54`, `app/services/auth_service.py:76`

### FR-1.3 Dual authentication
Every protected API endpoint **shall** accept *either* a valid `Authorization:
Bearer <jwt>` header *or* a valid session cookie. JWT is tried first; the
session is the fallback.
→ `get_current_user_flexible`, `app/services/auth_service.py:318`

### FR-1.4 Sign out
Signing out **shall** delete the server-side session row and clear the cookie.
→ `app/routers/auth.py:119`

### FR-1.5 Password management
- Passwords **shall** be stored only as bcrypt hashes (`app/models.py:446`).
- A user **shall** be able to change their own password after presenting the current one.
- A `must_change_password` flag **shall** be honoured and cleared on change.
- An administrator **shall** be able to reset any password via the CLI (`cli.py reset-password`).
- ⚠️ There is **no self-service password reset by email**. `password_reset_token` / `password_reset_expires` columns exist but no endpoint uses them.

### FR-1.6 User administration (admin only)
An administrator **shall** be able to create, list, read, update and delete
users, setting: username, email, full name, department, job title, `is_admin`,
`can_approve`, `can_sign`.
→ `app/routers/auth.py:206–370`

### FR-1.7 Signature authority is granted, never inherited
- `can_sign` **shall** default to false for new users; an administrator always gets it (`user_data.can_sign or user_data.is_admin`, `app/routers/auth.py:238`).
- The schema migration that introduced these columns **shall** grant `can_approve` to existing users but **not** `can_sign` (`app/utils/schema_migrations.py:40`).

### FR-1.8 Role assignment follows authority
When a user is created, or when `can_approve` / `can_sign` / `is_admin` changes,
the system **shall** assign the matching standard role:

| Authority | Role granted | Permissions |
|---|---|---|
| `can_sign` | `signatory` | contribute + `documents.approve` + `documents.sign` |
| `can_approve` only | `approver` | contribute + `documents.approve` |
| neither | `reader` | read-only |

Non-standard roles an administrator granted deliberately **shall not** be
removed. → `app/services/role_service.py:91`

### FR-1.9 Role backfill on startup
Any active, non-admin user holding **no** role **shall** be given one at
startup, so nobody can sign in yet be unable to read anything.
→ `app/services/role_service.py:112`, called from `app/main.py:174`

### FR-1.10 Self-deletion is refused
A user **shall not** be able to delete their own account.
→ `app/routers/auth.py:345`

### FR-1.11 Server-side page gating
The screens `/templates`, `/organization`, `/audit`, `/settings`, `/publish`,
`/process` **shall** be reachable only by administrators. A non-admin requesting
one **shall** be redirected to `/tasks` — enforced on the server, not merely
hidden in the menu.
→ `ADMIN_ONLY_PAGES`, `app/main.py:312`

### FR-1.12 Role-based landing
`/`, `/home` and `/dashboard` **shall** send an administrator to `/studio` and
everyone else to `/tasks`; an unauthenticated visitor **shall** go to `/login`.
→ `app/main.py:384`

---

## FR-2 · Document capture and processing

### FR-2.1 Two capture paths, one pipeline
A document **shall** enter the system either by browser upload
(`POST /api/documents/upload`) or by a file appearing in the staging folder.
Both **shall** converge on the same `DocumentProcessor.process_file` pipeline.
→ `app/services/file_watcher.py`, `app/services/document_processor.py:58`

### FR-2.2 Upload validation
An upload **shall** be rejected unless it passes:
1. Extension allow-list (default: `pdf, png, jpg, jpeg, tiff, bmp, txt, text, md, markdown`)
2. Size limit (default 100 MB)
3. Content/magic-byte validation and filename sanitisation
→ `app/utils/file_security.py`, called at `app/routers/documents.py:371`

### FR-2.3 Duplicate detection at upload
Before writing to staging, the system **shall** compute the SHA-256 of the
content and, if a document with that hash already exists **and its file is still
present**, return status `duplicate` with the existing document's id — rather
than silently accepting an upload that will produce nothing.
→ `app/routers/documents.py:383`

### FR-2.4 Duplicate, orphan and retry handling in the pipeline
On hash collision the processor **shall**:
- **File still present, processing succeeded** → treat as duplicate, move the new copy to `staging/duplicates/`, return the existing document.
- **File still present, any status is `failed`** → delete the failed record (and its vectors) and reprocess.
- **File missing** → delete the orphaned record and process as new.
→ `app/services/document_processor.py:89–142`

### FR-2.5 Text extraction (OCR)
Text **shall** be extracted using a configurable engine chain:

| `ocr_engine` | PDFs | Images |
|---|---|---|
| `auto` (default) | embedded text layer → vision model → Tesseract | vision model → Tesseract |
| `vision` | vision model, Tesseract only as last resort | same |
| `tesseract` | Tesseract only; the vision model is never called | same |

A PDF text layer is considered usable above **100 non-whitespace characters**.
Plain-text and Markdown files are read directly.
→ `app/services/ocr_service.py`

### FR-2.6 AI classification
When text is available and an AI service is configured, the system **shall**
extract: `title`, `summary`, `document_date`, `correspondent_name`,
`doctype_name`, `tag_names[]`, `is_tax_relevant`.
→ `AIService.extract_document_metadata`, `app/services/ai_service.py:524`

### FR-2.7 Auto-creation of metadata entities
A correspondent, doctype or tag named by the classifier **shall** be created if
it does not exist, and reused if it does.
→ `app/services/document_processor.py:392–420`

### FR-2.8 Storage layout
A processed file **shall** be moved to
`{storage_folder}/{correspondent}/{YYYY-MM-DD}/{document_id}_{filename}`,
falling back to `unknown_correspondent/{today}/` when the classifier found no
counterparty. Folder names are sanitised and capped at 50 characters; name
collisions get a numeric suffix.
→ `app/services/document_processor.py:291`

### FR-2.9 Independent processing status
Each document **shall** carry three independent statuses — `ocr_status`,
`ai_status`, `vector_status` — each one of `pending | processing | completed |
failed | skipped`. A failure in one **shall not** abort the others.

### FR-2.10 Semantic indexing
When text exists, the system **shall** build an enriched embedding string
(title ×2, filename, correspondent, doctype + synonyms, date in three forms,
tags individually, tax flag, summary, then up to 4 000–8 000 chars of body) and
store it in ChromaDB with metadata for filtering.
→ `app/services/document_processor.py:422`

### FR-2.11 Reprocessing
An administrator **shall** be able to re-run OCR, AI extraction or vectorisation
independently, or all three.
→ `POST /api/documents/{id}/reprocess`, `/reprocess-ai`, `/reprocess-ocr`, `/reprocess-vector`

### FR-2.12 Orphan cleanup
The system **shall** provide an operation that removes document records whose
physical file no longer exists, together with their vectors, processing logs and
tag links. → `POST /api/documents/cleanup/orphaned`

### FR-2.13 Document retrieval and viewing
Users **shall** be able to list, filter, read, download, preview, view a
thumbnail of, and extract the text of any document; viewing **shall** increment
`view_count` and stamp `last_viewed`.

### FR-2.14 Document relationships
A document **shall** be linkable to related documents (parent/child), and the
system **shall** offer "similar documents" computed from vector proximity.
→ `app/routers/documents.py:1286–1478`

---

## FR-3 · Approval workflow

> The rules live in exactly one module, `app/services/workflow_service.py`.
> Nothing else in the codebase moves a step from `current` to `approved`.

### FR-3.1 The chain invariant
A workflow **shall** be an ordered chain of steps in which **exactly one step is
`current`** at any time. Every other step is `pending` ahead of it or decided
behind it. This single invariant answers *where is it, who has it, is it done,
may I act*.

### FR-3.2 One live workflow per document
Creating a workflow for a document that already has a live one **shall** cancel
the existing one first. A document never has two competing chains.
→ `app/services/workflow_service.py:119`

### FR-3.3 Step addressing
A step **shall** be addressed either to **named individuals** (`assignee_ids`)
or to a **department + role**. Named individuals take precedence.

### FR-3.4 Approval mode (quorum)
Each step **shall** declare `approval_mode`:
- `any` — the first decision closes the step (**default**, and the default for every step created before this feature existed);
- `all` — every named assignee must approve before the chain advances.

`all` **shall** silently degrade to `any` when fewer than two individuals are
named, because a role has no roll to call.
→ `app/services/workflow_service.py:180`

### FR-3.5 Signature requirement validated at design time
If a step requires a signature, the system **shall refuse to create it** with
any assignee who lacks `can_sign` (admins excepted), naming the blocked people
and offering the three ways out. An unworkable approval cannot be designed.
→ `_reject_unsignable`, `app/services/workflow_service.py:186`

### FR-3.6 Who may act, and why not
`can_act(user, step)` **shall** return both a boolean and a human-readable
reason. It refuses when: the step is not current; the user has already decided
(admins included); the user lacks approve permission; the step is addressed to
other named people; the step is for another department; or the step needs a
signature the user may not give.
→ `app/services/workflow_service.py:270`

### FR-3.7 Nobody decides twice
A user who has already recorded a decision on a step **shall not** be able to
record another — otherwise one signatory could close a three-person step.

### FR-3.8 Decision outcomes
| Action | Effect |
|---|---|
| `approve` | Records a `StepDecision`. If people are still outstanding, the step **stays current** and the chain does not move. Otherwise the step closes and the next step becomes current, or the whole workflow becomes `approved`. |
| `reject` | **Requires a reason.** Ends the workflow immediately regardless of mode; all undecided steps become `skipped`. |
| `changes` | **Requires a comment.** Workflow → `changes_requested`; returns to the author. |

→ `app/services/workflow_service.py:306`

### FR-3.9 Approval propagates to the document
When the final step approves, the system **shall** set `documents.is_approved`,
`approved_at` and `approved_by`, so lists and search need no join.
→ `_advance`, `app/services/workflow_service.py:441`

### FR-3.10 Resubmission restarts from step 1
When an author resubmits after `changes_requested`, **every** step **shall** be
reset — status, decision, comment, reason and **all individual `StepDecision`
rows deleted**. An approver who signed version 1 has not seen version 2.
→ `app/services/workflow_service.py:467`

### FR-3.11 SLA and deadlines
A step **may** carry an SLA (4h, 8h, 1/2/3/5/10 days). Its `due_date` is stamped
when it becomes current. The workflow's own due date defaults to the sum of all
step SLAs (24h each where unset). A current step past its due date **shall** be
reported as overdue.

### FR-3.12 Task list
`GET /api/workflow/tasks/mine` **shall** return every current step waiting on
the caller, soonest deadline first, excluding steps they have already decided.
Administrators see everything, so a process can always be unblocked.
→ `tasks_for`, `app/services/workflow_service.py:557`

### FR-3.13 Reminders
An administrator **shall** be able to send a reminder, which records a
`reminded` workflow event naming the outstanding people.
⚠️ **No email or notification is actually sent** — the event is the whole action.

### FR-3.14 Cancellation
An active or draft workflow **shall** be cancellable; an `approved` or
`published` one **shall not** be.

### FR-3.15 The trail
Every state change **shall** append a `WorkflowEvent` (started, approved,
rejected, changes, reminded, published, cancelled, restarted) written in
business language for the tracking screen — kept separate from the security
`audit_logs`.

### FR-3.16 Consistent serialisation
Every workflow response **shall** be produced by `_workflow_json` /
`_step_json`, so Tracking, My Tasks and the document page can never disagree
about a document's state. Each step carries `can_act` and `blocked_reason`
resolved **server-side**, so a button and the API cannot diverge.
→ `app/routers/workflow.py:97–214`

---

## FR-4 · Digital signatures

### FR-4.1 Capture methods
A signature **shall** be capturable by drawing on a canvas, typing a name
rendered in a script face, or uploading an image. Stored as a PNG data URL,
maximum 2 MB. → `signaturePad`, `frontend/ui/js/shell.js:1310`

### FR-4.2 Immutability of the record
A signature **shall** be stored **per use**, not only on the user. A document
signed last March keeps exactly the mark that was applied then, even if the
person later draws a new one.

### FR-4.3 Designation frozen at signing
The signatory's designation **shall** be copied into the signature row at the
moment of signing, never looked up later. Someone who signed as *Head of
Finance* must still read as Head of Finance after they move on.
→ `app/services/workflow_service.py:499`

### FR-4.4 Resolution-independent placement
Placement **shall** be stored as fractions of the page (`x_pct`, `y_pct`,
`width_pct`, `page_number`), not millimetres, so a block sits in the same visual
place on A4, Letter or an arbitrarily sized scan. `NULL` means "let the
automatic layout decide".

### FR-4.5 Automatic layout
Unplaced signatures **shall** be laid out in a band across the bottom of the
page, three per row, above the footer furniture. Beyond two rows they **shall**
be given their own page. Content-bottom detection ignores the bottom 80 pt as
page furniture. → `app/services/signature_stamp.py`

### FR-4.6 Placement editor
An administrator **shall** be able to drag each signature to its exact position
over a rendered image of the real page, and reset to automatic.
→ `GET/PUT /api/signatures/{workflow_id}/layout`, `placeSignatures`, `frontend/ui/js/shell.js:2484`

### FR-4.7 Stamping is non-destructive
Stamping **shall** draw an overlay and merge it onto the existing pages,
returning **new bytes**. It never edits in place, and it works on any PDF —
including a scan that was never composed in the Studio.

### FR-4.8 Stamping failure must not block release
If stamping fails, the document **shall** be published unsigned and the error
logged. Publishing is the point of the exercise.
→ `app/routers/publishing.py:170`

---

## FR-5 · Document Studio (authoring)

### FR-5.1 Two ways to begin, one screen
The Studio **shall** offer "start writing" (a blank page) and "drop files here"
(bring a file in) side by side, because choosing a file and checking you chose
the right one are one act.

### FR-5.2 Templates
The system **shall** ship six letterhead templates — `blank`,
`harman-letterhead`, `maruti-suzuki`, `mahindra`, `tata`, `harman-quality` —
each specifying page size, margins, header, side rail, watermark and footer in
**millimetres**. → `app/services/doc_templates.py`

### FR-5.3 One template definition, two renderers
The browser canvas and the PDF renderer **shall** read the **same** template
spec. Changing a colour once **shall** change both. This is what makes preview
the output rather than an impression of it.

### FR-5.4 Image library
Users **shall** be able to place built-in brand marks or upload their own
images. Bodies reference assets **by id, never by path**, so a body can only
embed a file the server already knows about. Built-ins resolve to SVG for the
web (crisp at any zoom) and PNG for the PDF (ReportLab cannot read SVG).
→ `app/services/media_service.py`, `app/routers/studio.py:113`

### FR-5.5 AI writing assistance
The Studio **shall** offer AI actions over the selection or the whole body:
summarise, rewrite, fix grammar, translate, and draft from an instruction.
→ `app/services/authoring_ai.py`, `POST /api/studio/ai`

### FR-5.6 Drafts
Work in progress **shall** be saved as a private draft, autosaved, listed newest
first (30 most recent), and readable only by its owner or an administrator.
On publish the draft is marked `published` and keeps a pointer to the resulting
document.

### FR-5.7 HTML sanitising, twice
Body HTML **shall** be sanitised with `bleach` + `tinycss2` **on input and again
at render time**, so a body stored before a rule changed cannot bypass it.
Maximum body size 900 000 characters.

### FR-5.8 Preview without committing
`POST /api/studio/preview` **shall** render the exact PDF that publishing would
produce, without saving anything.

### FR-5.9 Publishing a composed document
Publishing from the Studio **shall not** invent a second ingest path. It
renders the PDF, writes it into the same storage tree the watcher uses, creates
the same `Document` row (`origin = composed`, `ocr_status = completed` because
the body is authoritative), captures version 1.0, and hands classification and
indexing to a **background task** so the author is not left waiting on a model.
→ `app/routers/studio.py:479`

### FR-5.10 The author's choices win
Background enrichment **shall** fill in only what the author left blank —
summary, doctype, correspondent, tags. The model saves typing; it does not
argue. → `_enrich`, `app/routers/studio.py:744`

### FR-5.11 Editing an existing document
"Edit" **shall** return the original body for a composed document (lossless =
true). For an uploaded file there is no editable original, so the extracted text
is laid out as paragraphs and the response is flagged `lossless: false` with an
explicit notice. Saving creates a **new version**; the original file is
untouched. → `GET /api/studio/source/{id}`

---

## FR-6 · Publishing and export

### FR-6.1 Publishing is earned
Only a workflow in status `approved` **shall** be publishable. Nothing can jump
the queue. → `app/services/workflow_service.py:601`

### FR-6.2 Two versions, two meanings
On publish the system **shall**:
1. **Lock** the current version — this is what the approvers saw and agreed to;
2. Stamp the signatures onto the PDF, write it as a **new** version, and make
   that the current file.

Collapsing these would lose the ability to prove either.
→ `app/routers/publishing.py:111`

### FR-6.3 Publish queue
`GET /api/publishing/queue` **shall** return both what is ready and what has
already gone out, in one call.

### FR-6.4 Unpublish
A publication **shall** be withdrawable; the approval itself stands, only the
release is undone.

### FR-6.5 Export formats
| Format | Behaviour |
|---|---|
| **PDF** | If a PDF exists on disk it is served **as-is** — the bytes that were approved are the bytes that go out. Otherwise re-rendered from the body. |
| **DOCX** | Generated from the body (or from extracted text). Letterhead is **not** carried over, and the UI says so. |
| **TXT** | Plain content, for another system to consume. |

### FR-6.6 Honest format availability
`GET /api/publishing/formats/{id}` **shall** report which exports actually work
for this document and why not for the others, so the screen never offers a
button that will fail.

---

## FR-7 · Versioning

### FR-7.1 Append-only
The version table **shall** be append-only. Nothing is ever updated in place.

### FR-7.2 When a version is written
On capture, on every Studio save, and when an approval locks a version.

### FR-7.3 Files are copied, not referenced
A version's bytes **shall** be copied into a per-document `versions/` folder,
because the live path is overwritten by the next save and a history pointing at
overwritten bytes is worse than no history.

### FR-7.4 Locking
An approved version **shall** be locked: it can be superseded by a newer version
but never overwritten.

### FR-7.5 Restore is forward-only
Restoring v1.1 **shall** write a *new* version whose content matches v1.1. It
never rewinds, so the restore itself is visible in the history.
→ `app/services/version_service.py:144`

### FR-7.6 Version numbering
`next_version("1.3")` → `1.4`; major bump → `2.0`.

---

## FR-8 · Search and retrieval

### FR-8.1 Semantic first, always a result
Search **shall** attempt vector search first and **shall** fall back to
full-text search when vector search returns nothing or the AI service is
unavailable. A search never returns an error page instead of results.
→ `app/services/search_service.py:377`

### FR-8.2 Query enhancement and variants
The system **shall** enhance the query for semantic matching and generate
tolerant variants — accent folding (NFD normalisation), typo variants for words
over three characters — capped at 20 variants to prevent query explosion.

### FR-8.3 Filters
Search **shall** support filtering by correspondent, doctype, tags, tax
relevance, reminder state (`has` / `overdue` / `none`), a custom date range, and
14 named ranges (today, yesterday, last 7/30/90 days, this/last week, month,
quarter, year, last 2 years).

### FR-8.4 AI circuit breaker
After **3** consecutive AI failures the system **shall** disable AI-dependent
search paths for **300 seconds**, then retry. Search degrades to full-text
rather than hanging.

### FR-8.5 Suggestions
`GET /api/search/suggestions` **shall** return matching correspondents, doctypes
and tags for a partial query, tolerant of accented characters.

### FR-8.6 Similar documents
The system **shall** recommend documents similar to a given one, from vector
proximity.

### FR-8.7 Re-indexing
`cli.py reindex-vectors [--force]` and `POST /api/search/rebuild-embeddings`
**shall** rebuild the vector store. `--force` is required after changing the
embedding model, because the dimension changes.

---

## FR-9 · AI assistant (RAG)

### FR-9.1 Answer from the repository
The assistant **shall** answer a natural-language question by retrieving
relevant documents (semantic search, or an explicit document list) and
generating an answer grounded in their text.

### FR-9.2 Citations must be correct
The model is told to cite as `[Doc1]`, `[Doc2]`, numbered by position in what it
was given. The returned `sources` array **shall** therefore contain exactly the
documents actually sent, in that order — not every match. A document with no
text is excluded from both, so `[DocN]` is always `sources[N-1]`.
→ `app/services/search_service.py:739`

### FR-9.3 Rendered as a document
The answer **shall** be rendered with headings, tables and bullets, and every
`[Doc N]` marker **shall** be a link to the source file.

### FR-9.4 Honest failure
When no AI service is configured the assistant **shall** say exactly which key
to set, rather than failing silently. When the circuit breaker is open it
**shall** say how many seconds remain.

### FR-9.5 Confidence
A confidence score **shall** be returned as
`min(documents_used / max_documents, 1.0)`.

---

## FR-10 · Metadata management

### FR-10.1 CRUD with counts
Correspondents, document types and tags **shall** each support create, read,
update, delete and list-with-document-count.

### FR-10.2 Default document types
A standard set of document types **shall** be ensured at startup and on first
setup. → `app/services/doctype_manager.py`

### FR-10.3 Referential safety
Deleting a metadata entity **shall not** orphan documents; the delete endpoints
check usage first.

### FR-10.4 Tagging
A document **shall** accept tags one at a time or as a batch, and the response
**shall** return what was added, what was already present, and the document's
full tag list afterwards — so the caller needs no second round trip.
→ `TagAddResponse`, `app/schemas.py:88`

### FR-10.5 Combobox behaviour
Selecting a correspondent **shall** list everyone on file, filter as the user
types, and offer *Add "…" as new* for a name that does not exist.

---

## FR-11 · Audit and activity log

### FR-11.1 What is recorded
`login_success`, `login_failed`, `logout`, `password_changed`, `initial_setup`,
`user_created`, `user_updated`, `user_deleted`, `document.upload`,
`document.download`, `document.compose`, `document.revise`, `document.publish`,
`document.version.restore`, `workflow.approve`, `workflow.reject`,
`workflow.changes`.
→ `ACTIONS`, `app/routers/audit.py:27`

### FR-11.2 What each entry carries
Actor, action, resource type, resource id, JSON details, IP address, user agent,
timestamp.

### FR-11.3 Nothing is invented
An action that was not recorded **shall not** appear. The screen says the log is
empty rather than inventing a history.

### FR-11.4 Filtering
The log **shall** be filterable by free text, action type and a window of 1–365
days, returning at most 1 000 entries.

### FR-11.5 Auditing must never block the work
A failure to write an audit entry **shall** be logged and swallowed, never
propagated to the user's operation.
→ `app/routers/studio.py:740`

### FR-11.6 Two trails, deliberately separate
`workflow_events` is the business trail shown to users on the tracking screen;
`audit_logs` is the security record. They are not merged.

---

## FR-12 · Settings and configuration

### FR-12.1 Configuration precedence
Effective value = **code default < `config/models.json` < environment / `.env` <
database `settings` table**. → `app/config.py:120`

### FR-12.2 Runtime reconfiguration
An administrator **shall** be able to change AI provider, API keys, models,
generation limits, file settings, OCR tool paths and folder paths through the
UI, persisted to the database, without restarting.

### FR-12.3 Connection test
`POST /api/settings/test/ai` **shall** verify the configured provider actually
answers, and report what failed if not.

### FR-12.4 Dual Groq keys with automatic failover
Two Groq keys **shall** be supported. On a quota error the next request goes out
on the second key automatically. Blank and **duplicate** keys are removed from
the list — two identical keys give one quota, and the code says so.
→ `AIClientFactory.groq_keys`, `app/services/ai_client_factory.py:36`

### FR-12.5 Daily-cap awareness
A **per-day** cap **shall** be distinguished from a per-minute one. A per-minute
limit clears on its own and is worth waiting out; a daily cap will not clear
today, so the system stops retrying and logs exactly what to do.
→ `app/services/ai_service.py:315`

### FR-12.6 Capability negotiation
When a model rejects a request parameter with HTTP 400, the system **shall**
remember that (provider, model) does not support it and stop sending it — for
`reasoning_effort`, `response_format`, `temperature`, `max_completion_tokens`,
`max_tokens`. → `app/services/ai_service.py:196`

### FR-12.7 Reasoning-token headroom
For reasoning-capable models the completion budget **shall** be floored at
**512** tokens, because reasoning tokens are billed against it and a smaller
budget returns an empty message.

### FR-12.8 Import / export of configuration
Configuration **shall** be exportable and importable as JSON.

---

## FR-13 · Backup and restore

### FR-13.1 On-demand backup
An administrator **shall** be able to create a backup covering the database,
storage, configuration or all of them.

### FR-13.2 Scheduled backup
A scheduler **shall** exist, configurable and **disabled by default**.
→ `app/main.py:133`

### FR-13.3 List, restore, delete
Backups **shall** be listable, restorable and deletable, with path-traversal
protection on the filename. → `tests/test_backup_security.py`

### FR-13.4 Recommendations and health
The system **shall** report backup health and recommendations.

---

## FR-14 · Health, monitoring and administration

### FR-14.1 Probes
`/api/health/liveness`, `/readiness`, `/startup`, `/simple` **shall** be
provided for orchestration.

### FR-14.2 Detailed health
`GET /api/health/` **shall** report database, vector store, AI provider, OCR
tooling, disk and folder status.

### FR-14.3 Metrics
`GET /api/health/metrics` **shall** report CPU, memory, disk and document counts.

### FR-14.4 Security posture
`GET /api/health/security` and the `/api/security/*` endpoints **shall** report
directory permissions, recent uploads and access logs, and allow quarantining a
document.

### FR-14.5 CLI
The following commands **shall** be available:
`init`, `serve`, `process`, `status`, `setup-root`, `users`, `reset-password`,
`sync-model-config`, `check-ai`, `reindex-vectors [--force]`,
`db {create-indexes|analyze|optimize|size}`,
`backup {create|restore|list}`. → [cli.py](../../cli.py)

---

## Business rules digest

The rules that would be expensive to rediscover, in one place:

| # | Rule | Enforced at |
|---|---|---|
| BR-1 | Exactly one step is `current` per workflow | `workflow_service.py` |
| BR-2 | A document has at most one live workflow | `create_workflow` |
| BR-3 | A signature step cannot be assigned to a non-signatory | `_reject_unsignable` (design time) |
| BR-4 | Nobody, including an admin, decides twice on a step | `can_act` |
| BR-5 | Rejection is decisive regardless of quorum mode | `decide` |
| BR-6 | Resubmission clears **all** prior decisions | `resubmit` |
| BR-7 | Only a fully approved workflow may be published | `publish` |
| BR-8 | The approved version is locked before signatures are stamped | `publishing.py` |
| BR-9 | Restore is forward-only | `version_service.restore` |
| BR-10 | A signature's designation is frozen at signing | `_store_signature` |
| BR-11 | Placement is a page fraction, never an absolute coordinate | `signature_stamp.py` |
| BR-12 | The author's metadata wins over the classifier's | `studio.py:_enrich` |
| BR-13 | Duplicate Groq keys collapse to one — no false headroom | `groq_keys` |
| BR-14 | Successful login clears that IP's failed-attempt budget | `rate_limit_middleware.py:226` |
| BR-15 | `all` mode degrades to `any` below two named assignees | `_build_step` |

---

## Traceability matrix

| Requirement | Implementation | Test |
|---|---|---|
| FR-1.1–1.5 | `routers/auth.py`, `services/auth_service.py` | `tests/test_end_to_end.py` |
| FR-1.6–1.10 | `routers/auth.py`, `services/role_service.py` | `tests/test_end_to_end.py` |
| FR-1.11–1.12 | `app/main.py:312,384` | ⚠️ none |
| FR-2.1–2.4 | `services/file_watcher.py`, `services/document_processor.py` | `tests/test_file_watcher.py` |
| FR-2.5 | `services/ocr_service.py`, `services/vision_ocr.py` | `tests/test_ocr_service.py`, `tests/test_vision_ocr.py` |
| FR-2.6–2.10 | `services/ai_service.py`, `services/document_processor.py` | `tests/test_groq_provider.py` |
| FR-3.* | `services/workflow_service.py`, `routers/workflow.py` | ⚠️ partial — `tests/test_end_to_end.py` |
| FR-4.* | `services/signature_stamp.py`, `routers/signatures.py` | ⚠️ none |
| FR-5.* | `routers/studio.py`, `services/doc_templates.py`, `pdf_render.py` | ⚠️ none |
| FR-6.* | `routers/publishing.py`, `services/docx_render.py` | ⚠️ none |
| FR-7.* | `services/version_service.py` | ⚠️ none |
| FR-8.* | `services/search_service.py`, `vector_db_service.py`, `fuzzy_search.py` | `tests/test_embedding_service.py` |
| FR-9.* | `services/search_service.py:681`, `ai_service.py:721` | `tests/test_reasoning_behaviour.py` |
| FR-10.* | `routers/{correspondents,doctypes,tags}.py` | `tests/test_end_to_end.py` |
| FR-11.* | `routers/audit.py`, `services/audit_service.py` | ⚠️ none |
| FR-12.* | `app/config.py`, `services/model_config.py`, `ai_client_factory.py` | `tests/test_model_config.py`, `tests/test_runtime_configuration.py`, `tests/test_sdk_compat.py` |
| FR-13.* | `routers/backup.py`, `utils/backup.py` | `tests/test_backup_security.py` |
| FR-14.* | `routers/health.py`, `routers/security.py`, `cli.py` | `tests/test_rate_limiting.py` |

⚠️ **Coverage gap:** the approval engine, signature stamping, the Studio,
publishing and versioning — the modules carrying the most business risk — have
the least automated coverage. See doc 11 §3.
