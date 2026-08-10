# 01 · Introduction & Scope

> **Audience:** everyone. This is the only document a non-technical reader must
> finish. It explains what the system is for, who uses it, what it does and does
> not cover, and the vocabulary the rest of the set relies on.

---

## 1. Purpose of this document set

This is the Software Requirements Specification (SRS) and design record for the
**HARMAN Document Management System (DMS)**. It exists so that:

1. A business stakeholder can confirm the system does what was asked.
2. A development team that has never seen the code can take ownership of it,
   extend it, and be confident about what they will break.
3. Operations can install, configure, run, back up and recover it.
4. Auditors can trace a control (who approved what, when) to the mechanism that
   enforces it.

It documents the system **as built**, not as aspired to. Where a feature is
partial, planned, or was retired, it is marked as such.

---

## 2. Business context and problem statement

A manufacturing business generates documents continuously — supplier invoices,
contracts, delivery notes, quality reports, HR letters, statutory filings. In
most organisations these live in four incompatible places at once: a shared
drive, an email inbox, a filing cabinet, and someone's laptop. The consequences
are predictable and expensive:

| Problem | Cost |
|---|---|
| Nobody can find a document without knowing where it was filed | Hours per retrieval; duplicated work |
| Approvals happen over email | No reliable record of who agreed to what |
| A signed PDF and its editable source drift apart | Disputes cannot be settled from the record |
| Retention and audit are manual | Compliance exposure |
| Classification is typed by hand | Inconsistent metadata; search degrades over time |

**HARMAN DMS addresses this by making the document's whole life happen in one
place**: it is captured or written there, classified there, approved there,
signed there, published there, and searched there — with an append-only trail
behind every step.

### 2.1 The product's spine

The entire product is organised around five sequential steps, which are also the
five primary screens. This is deliberate: the navigation is the process.

```
   1. Document Studio  →  2. Review  →  3. Approval  →  4. Status & Tracking  →  5. Publishing
      write it, or         confirm       choose who        watch it move           release it,
      bring a file in      the details   signs, in         through the chain       signatures
                           read from it  what order                                stamped on
```

Everything else in the product — search, the AI assistant, the repository, the
audit log, settings — exists to serve one of those five steps or to find
something that has already been through them.

### 2.2 Stated business value targets

From the project charter (root `README.md`):

- **70%** faster document retrieval
- **60%** less manual approval time
- **100%** audit-ready trail
- Open, API-first architecture (no vendor lock-in on the AI provider)

---

## 3. System scope

### 3.1 In scope — implemented and working

| Capability | Summary |
|---|---|
| **Document capture** | Browser upload, or drop a file into a watched staging folder; automatic deduplication by SHA-256 hash |
| **Text extraction (OCR)** | PDF embedded text layer → vision LLM → Tesseract, in that order, configurable |
| **AI classification** | Title, summary, document date, correspondent, document type, tags, tax relevance |
| **Document authoring** | In-app WYSIWYG editor on six letterhead templates, with AI writing assistance |
| **Approval workflows** | Ordered multi-step chains, named or department-addressed, any/all quorum, per-step SLA, signature requirement |
| **Digital signatures** | Drawn, typed or uploaded; stored per decision; positioned as page fractions; stamped onto the published PDF |
| **Version control** | Append-only version history; approved versions locked; restore is forward-only |
| **Publishing & export** | Publish gated on full approval; export as PDF / DOCX / TXT |
| **Search** | Semantic (vector) search with full-text and fuzzy fallback; faceted filters |
| **AI assistant (RAG)** | Natural-language questions answered across the repository with citations |
| **User & role management** | Users, departments, job titles, standard roles, separate approve/sign authority |
| **Audit trail** | Every significant action recorded with actor, target, IP and user agent |
| **Backup & restore** | On-demand and scheduled system backups, with restore |
| **Health & metrics** | Liveness, readiness, startup probes and system metrics endpoints |

### 3.2 Out of scope — explicitly not built

These are named because the root `README.md` and some retired screens reference
them; a new team must not assume they exist.

| Not built | Current behaviour |
|---|---|
| **Retention policy engine** | A retention label can be stored on a workflow (`approval_workflows.retention_policy`) but **nothing acts on it**. `/retention` redirects to `/documents`. |
| **Records warehousing** | `/records` redirects to `/documents`. No physical-storage module. |
| **Integrations / connectors catalogue** | `/integrations` redirects to `/settings`. No connector framework, no webhooks. |
| **Visual workflow designer** | `/workflows` redirects to `/templates`. Routes are designed on the Approval screen, not on a canvas. |
| **Annotations** | No annotation model or endpoints. |
| **SSO / LDAP / SAML** | Local username + password only. |
| **Email or push notification** | The "remind" action writes a workflow event; **no email is sent**. |
| **Multi-tenancy** | Single organisation per deployment. |
| **Per-document access control** | Any user holding `documents.read` can read **every** document. Access is by role, not by document, department or ownership. See doc 09 §6. |

### 3.3 Deliberately retired

The following screens existed and were removed because they had no working
module behind them. Their URLs still resolve (301 redirect) so no bookmark or
demo script breaks — see `app/main.py:264`.

`/upload`, `/capture`, `/compose`, `/editor` → `/studio` ·
`/approvals` → `/tasks` · `/workflows` → `/templates` ·
`/retention`, `/records` → `/documents` · `/integrations` → `/settings`

The old single-file interface lives in [legacy-ui/](../../legacy-ui/) and is no
longer routed.

---

## 4. Stakeholders and user classes

### 4.1 Human actors

| Actor | Description | What the product gives them |
|---|---|---|
| **Administrator** (`is_admin = true`) | Runs the system: sets up people, designs approval routes, configures AI, publishes | The full five-step spine, plus Approval Routes, People, Activity Log, Settings. Lands on `/studio`. |
| **Signatory** (`can_approve` + `can_sign`) | A department head or authorised officer who binds the company | My Tasks, Status & Tracking, repository, search, assistant. Lands on `/tasks`. |
| **Approver** (`can_approve` only) | A clerk or reviewer who verifies but may not sign | Same as signatory, but the system refuses to place them on a step requiring a signature |
| **Reader** | Can find and read, nothing else | Repository, search, assistant |
| **Auditor** | Reads the activity log | `/audit` (admin-gated today — see doc 09 §6) |

> **The central authority distinction.** `can_approve` and `can_sign` are two
> separate flags on `users`, not one. A clerk can verify an invoice without
> being permitted to bind the company; only a signatory does that. The workflow
> engine refuses at *design time* to place a non-signatory on a step that
> requires a signature (`app/services/workflow_service.py:186`), so an
> unworkable process cannot be created in the first place.

### 4.2 System actors

| Actor | Role |
|---|---|
| **File watcher** | A background thread that notices files appearing in the staging folder and processes them |
| **Background enrichment task** | Classifies and indexes a document after the user's request has already returned |
| **Backup scheduler** | Optional timer that creates system backups |
| **AI provider** | Groq (default), OpenAI or Azure OpenAI — chat, analysis and vision models |
| **Vector store** | ChromaDB, embedded (persistent local) or remote HTTP |

---

## 5. Operating environment

| Aspect | Value |
|---|---|
| Server runtime | Python 3.12 |
| Web server | Uvicorn (ASGI), default `127.0.0.1:8000` |
| Database | SQLite (default, `data/documents.db`); PostgreSQL supported via `DATABASE_URL` |
| Vector store | ChromaDB persistent client at `data/chroma`, or remote HTTP |
| Browser | Any modern evergreen browser. No build step, no CDN, no framework. |
| Host OS | Linux (Docker image), Windows 10/11, macOS. All three are exercised — Windows-specific fallbacks exist for `libmagic`, Tesseract and Poppler discovery. |
| External services | The configured AI provider's HTTPS endpoint. Everything else is local. |
| Network | Runs fully offline except for AI calls; degrades gracefully when the AI provider is unreachable |

---

## 6. Glossary

| Term | Meaning in this system |
|---|---|
| **Document** | A filed artefact: a row in `documents` plus its bytes in the storage tree |
| **Origin** | How a document came to exist: `uploaded` (a file arrived) or `composed` (written in the Studio) |
| **Correspondent** | The counterparty — supplier, customer, authority. Doubles as the first level of the storage folder tree. |
| **DocType** | The kind of document: Invoice, Contract, Delivery note… Auto-created by the classifier when it meets a new one. |
| **Draft** | Unfinished Studio work, private to its author, not yet a Document |
| **Workflow** | One document's journey through an ordered chain of approval steps |
| **Step** | One link in that chain, addressed to named people or to a department/role |
| **Approval mode** | `any` (first decision closes the step) or `all` (every named person must approve) |
| **Decision** | One person's answer on one step: approve / reject / changes |
| **Signature** | A PNG mark plus the signatory's name and designation, frozen at the moment of signing |
| **Placement** | Where a signature sits on the page, held as a fraction of page width/height so it survives any paper size |
| **Version** | An immutable snapshot of a document's bytes. Append-only; approved versions are locked. |
| **Publishing** | Releasing a fully approved document, with its signatures stamped onto the PDF |
| **Staging** | The watched inbox folder (`data/staging`) — files land here and are pulled in automatically |
| **Storage** | The permanent tree (`data/storage/{correspondent}/{YYYY-MM-DD}/`) |
| **RAG** | Retrieval-Augmented Generation — the "Ask AI" feature: retrieve relevant documents, then answer from them with citations |
| **Template** | A letterhead *specification* (paper size, margins, header, side rail, watermark, footer). Describes the paper, never the words. |
| **IST** | Indian Standard Time. All dates are displayed as `DD-MM-YYYY` in IST; stored timestamps are UTC. |

---

## 7. Assumptions and dependencies

### 7.1 Assumptions

1. **Trusted internal network.** The product has no per-document access control;
   everyone who can sign in and holds `documents.read` can read every document.
   The deployment is assumed to be inside an organisational boundary.
2. **One organisation per deployment.** There is no tenant discriminator.
3. **Modest concurrency.** SQLite is the default database; it serialises writes.
   Multi-worker or high-write deployments must move to PostgreSQL.
4. **AI is an accelerator, not a dependency.** Every AI-assisted path has a
   non-AI fallback. If the provider is down or out of quota, capture still
   works — the file is stored, text extracted (via Tesseract), and made
   searchable by full-text; only the AI-written title/summary are missing.
5. **Documents of record are PDFs.** DOCX and TXT exports are conveniences and
   are labelled as such on screen.

### 7.2 External dependencies

| Dependency | Required? | Consequence if absent |
|---|---|---|
| Groq / OpenAI / Azure API key | No | Classification, summaries, semantic search and the assistant are disabled; the rest works |
| Tesseract binary | No | Image OCR falls back to the vision model; if both absent, no text is extracted from scans |
| Poppler (`pdftoppm`) | No | PDF pages cannot be rendered to images for vision OCR or thumbnails |
| `libmagic` | No | MIME detection falls back to file extension (`app/services/document_processor.py:243`) |
| ChromaDB | Bundled | Falls back to an in-memory collection if the persistent store cannot be opened |
| Internet access | Only for AI | — |

### 7.3 Key third-party libraries

| Library | Used for | Note |
|---|---|---|
| `fastapi` 0.136.1 | HTTP framework | |
| `sqlalchemy` 2.0.23 | ORM | |
| `pydantic` / `pydantic-settings` | Validation, layered configuration | |
| `chromadb` 0.4.22 | Vector store | |
| `onnxruntime` + `tokenizers` | Local CPU embeddings (`all-MiniLM-L6-v2`, 384-dim) | Chosen because Groq has no embeddings endpoint |
| `openai` 1.59.6 | Client for all three providers (Groq via custom `base_url`) | |
| `reportlab` 4.2.5 | PDF generation and signature stamping | Pure-Python wheels — no system libraries |
| `pypdfium2` 5.12.1 | Rendering a PDF page to PNG for the placement editor | BSD/Apache — chosen deliberately over AGPL PyMuPDF |
| `PyPDF2` 3.0.1 | Reading page geometry, merging the signature overlay | |
| `bleach` + `tinycss2` | HTML sanitising, on input *and* at render time | |
| `passlib[bcrypt]` | Password hashing | |
| `python-jose` | JWT | |
| `watchdog` 4.0.0 | Staging folder observer | |

Full list: [requirements.txt](../../requirements.txt).

---

## 8. Document history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-08-07 | Generated from source analysis | Initial complete specification, verified against application v1.1.0 |
