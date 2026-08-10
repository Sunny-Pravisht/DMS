<div align="center">
  <h1>Document Management System</h1>
  <p><strong>An enterprise content platform for capture, governance, automation, and intelligent retrieval of enterprise documents and records.</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Backend-FastAPI-2B50E2?style=flat-square" alt="FastAPI">
    <img src="https://img.shields.io/badge/UI-Zero%20dependency-2B50E2?style=flat-square" alt="UI">
    <img src="https://img.shields.io/badge/License-MIT-6B7280?style=flat-square" alt="MIT">
  </p>
</div>

---

> ### 📘 Full specification & design documentation
> **[docs/DMS-Project-Documentation.md](docs/DMS-Project-Documentation.md)** —
> the complete, standalone SRS + HLD + LLD: scope, functional and non-functional
> requirements, architecture, data model, low-level design, API reference,
> frontend design, security design, operations runbooks and the handover
> register. It opens with a reading guide telling you which part to read for
> your role.
>
> That document is versioned and dated independently of this README, and is
> **the authoritative description of the system**. This README tracks
> day-to-day development and changes often; where the two disagree, the
> specification was verified against the source and is correct.
>
> *(The same content is also available split into eleven chapter files under
> [docs/srs/](docs/srs/README.md) for anyone who prefers navigating by file.)*

---

## About this repository

This project is a **commercial derivative** built on top of the open-source
[`JayRHa/DocumentManager`](https://github.com/JayRHa/DocumentManager) project (MIT licensed).
The upstream project provides an excellent AI-assisted personal document manager: OCR,
auto-tagging, semantic search and a RAG chat. **It is not an enterprise content platform.**

We are transforming it into one. This README is the single source of truth for that
transformation: what is **inherited**, what is being **modified**, what is being **added**,
and what has been **removed**.

> **Upstream attribution:** original work © Jannik Reinhard and Fabian Peschke, MIT License.
> See [LICENSE](LICENSE). All upstream copyright notices are retained.

---

## Product vision

A single governed repository that owns the **full document lifecycle**, from capture across
every department, through classification, workflow and collaboration, to long-term retention,
records disposition and secure third-party exchange.

```
 Capture  →  Index & Classify  →  Core Repository  →  Govern & Access  →  Integrate
 Structured &    Metadata, OCR,     Versioning,        Org / department    APIs to
 unstructured    AI tagging         workflow,          permissions         3rd-party
 sources                            retention                              systems
```

---

## Transformation at a glance

| # | Capability pillar | Status | Summary |
|---|---|---|---|
| 1 | User Management (org & department wise) | 🟠 **Major rework** | Flat users/roles → multi-level org hierarchy, department repositories, folder- and document-level ACLs |
| 2 | Data Sources (structured + unstructured) | 🟠 **Extended** | Upload + folder watcher → connector framework (ERP, CRM, DB, HR, email, LOB apps) |
| 3 | Indexing & Sorting | 🟢 **Inherited, hardened** | OCR → metadata → classification → full-text + vector index already works; adding rule engine and department-aware routing |
| 4 | Workflow Automation | 🔴 **New** | Submit → Review → Approve → Route → Archive, no-code designer, SLA timers, escalation |
| 5 | Versioning & Annotations | 🔴 **New** | Immutable version history, compare/restore, inline comments, markup, approval stamps, @mentions |
| 6 | AI Capabilities | 🟢 **Inherited, extended** | OCR/classification/NL search/chat exist; adding template-free field extraction, duplicate & anomaly detection |
| 7 | Retention Policy | 🔴 **New** | Active → Retention → Archive → Disposition, rule-driven, legal holds override schedules |
| 8 | Records & Warehousing | 🔴 **New** | Physical box/file tracking, records schedules, chain-of-custody, cold tiering, compliance reports |
| 9 | API & Integrations | 🟠 **Extended** | REST exists; adding webhooks, SSO/SAML/OIDC, bulk import/export, SOAP bridge |
| 10 | User Interface | 🔴 **Rebuilt** | Bootstrap/CDN single-file SPA → new zero-dependency design system (white / royal blue / grey / red) |

Legend: 🟢 inherited and kept · 🟠 modified/extended · 🔴 net-new module

---

## 1. User Management by organization and department

**Inherited:** `User`, `Role`, `Session`, `AuditLog` models, bcrypt passwords, session cookies,
CSRF + rate-limit middleware, a flat "is_admin" permission check.

**What changes**

- `User.is_admin` boolean is demoted to a fallback; **role permissions become authoritative**.
- Roles gain a scoped assignment (`role @ organization` / `role @ department`) instead of a global grant.

**What is added**

| Feature | Detail |
|---|---|
| Organization-wide hierarchy | New `Organization` + `OrgUnit` models, multi-level tree, **inherited permission rules** flow down the tree |
| Department-wise repositories | New `Department` model; each department owns an isolated document space with explicit **cross-links** for shared documents |
| Granular access control | New `AccessControlEntry`, mapping subject (user/role/department) × resource (folder/document/doctype) × permission (`view`, `download`, `edit`, `delete`, `approve`, `manage_permissions`) |
| Source-document ownership | Every document records owning org unit, owning department and a named document owner |
| Audit-ready visibility | Every read, download, permission change and export written to `AuditLog` against the user identity, exposed on a new **Audit Trail** page |
| Access review | Per-user "what can this person see" and per-document "who can see this" effective-permission explorer |

---

## 2. Data Sources: structured and unstructured, from every source

**Inherited:** drag-and-drop upload, a staging-folder file watcher, PDF/image/text ingestion.

**What changes**

- `ALLOWED_EXTENSIONS` extended with Office formats (`docx`, `xlsx`, `pptx`, `eml`, `msg`, `csv`).
- The single ingestion path is refactored into a **normalizing pipeline** so structured rows and
  unstructured files land in the same governed repository with the same metadata contract.

**What is added: a connector framework**

| Structured | Unstructured |
|---|---|
| ERP & finance systems | Scanned paper & PDFs *(inherited)* |
| CRM records | Email + attachments (IMAP/Graph) |
| Databases & data warehouses (JDBC/ODBC pull) | Images & scanned forms *(inherited)* |
| HR & payroll systems | Office documents (Word, Excel, PowerPoint) |
| Line-of-business apps (REST pull) | Collaboration content (SharePoint/Drive) |

Each connector is scheduled, credential-scoped, department-mapped, and reports run history,
row/file counts and failures to a new **Capture & Data Sources** page.

---

## 3. Indexing & Sorting

**Inherited and kept. This is the strongest part of the upstream project.**

`Capture → Metadata Tagging → Classification & Sorting → Full-Text Indexing`

- Tesseract + vision-model OCR (`app/services/ocr_service.py`, `vision_ocr.py`)
- AI metadata extraction: title, summary, correspondent, document type, document date, tags
- ChromaDB vector index + local ONNX embeddings (`vector_db_service.py`, `embedding_service.py`)
- Full-text and fuzzy search (`search_service.py`, `fuzzy_search.py`)

**What is added**

- A **classification rule engine** (deterministic rules evaluated before the model) so
  regulated document types never depend on a probabilistic call.
- Department-aware auto-filing: classification result decides the destination department folder.
- Confidence thresholds with a **human-in-the-loop review queue** for low-confidence classifications.

---

## 4. Workflow Automation *(new module)*

The upstream project has a single `is_approved` flag. That is replaced by a real process engine.

`Submit → Review → Approve → Route → Archive`

| Feature | Detail |
|---|---|
| Configurable process flows | No-code, multi-step approval chains; serial, parallel and conditional branches |
| Role-based task routing | Automatic assignment by department, role or org unit, never to a hard-coded user |
| SLA tracking & escalation | Per-step timers, reminders, auto-escalation to the next approver on breach |
| End-to-end automation | Intake → archival with no manual handoffs; workflow completion can trigger retention start |
| Task inbox | Per-user **Approvals** queue with delegate/reassign and full decision history |

New models: `WorkflowDefinition`, `WorkflowStep`, `WorkflowInstance`, `WorkflowTask`, `WorkflowEvent`.
The legacy `is_approved` / `approved_by` columns are kept and driven by the engine for backwards compatibility.

---

## 5. Document Versioning & Annotations *(new module)*

**Versioning**

- Every save is preserved as an immutable `DocumentVersion` (`v1.0 → v1.1 → v2.0`).
- Compare, restore, or branch from any prior version; full change log with author and reason.
- Approved versions can be **locked**, and locking is enforced server-side, not in the UI.

**Annotations**

| Feature | Detail |
|---|---|
| Inline comments | Threaded discussion anchored to a page, region or extracted field |
| Highlights & markup | Freehand and shape annotation stored as an overlay, never burned into the source file |
| Approval stamps | Digital sign-off rendered on the document and recorded in the audit trail |
| @mentions & notifications | Route feedback to the right reviewer instantly |

New models: `DocumentVersion`, `Annotation`, `AnnotationThread`, `Mention`, `Notification`.

---

## 6. AI Capabilities

**Inherited and kept:** intelligent capture (OCR), auto-classification, natural-language search,
conversational assistant (RAG), AI-generated summaries, multi-provider support (Groq / OpenAI / Azure OpenAI).

**What is added**

| Feature | Detail |
|---|---|
| Smart extraction | Template-free key-field extraction (invoice number, dates, parties, amounts) into typed, queryable metadata |
| Predictive insights | Volume/backlog trends, SLA-risk prediction, anomaly detection |
| Duplicate detection | Near-duplicate clustering on top of the existing embedding index (upstream only detects exact hash collisions) |
| Sensitivity classification | AI assigns a sensitivity label that feeds the access-control and retention engines |
| Grounded answers | Assistant responses cite document + page and respect the caller's permissions, so there is **no cross-department leakage** |

---

## 7. Retention Policy Management *(new module)*

`Active → Retention Period → Archive → Disposition`

| Feature | Detail |
|---|---|
| Rule-driven policies | Scoped by document type, department or regulation; trigger on create, close or event date |
| Retention clock | Automatic state transitions with a preview of everything due in the next N days |
| Archive tier | Automatic move to long-term, low-cost storage at end of the active period |
| Disposition review | Dual-approval destruction with a certificate of destruction, or mark for permanent preservation |
| Legal hold | **Overrides any schedule.** Disposition is suspended instantly and cannot be bypassed |

New models: `RetentionPolicy`, `RetentionRule`, `RetentionSchedule`, `DispositionAction`, `LegalHold`.

---

## 8. Records Management & Warehousing *(new module)*

| Feature | Detail |
|---|---|
| Physical & digital warehousing | Track warehouse → rack → shelf → box → file locations alongside the digital counterpart |
| Records classification | Formal records schedules aligned to regulatory categories |
| Chain-of-custody | Immutable, append-only trail for every record movement, issue, return and access |
| Legal hold management | Suspend disposition instantly for litigation or investigation |
| Cold storage tiering | Automatic migration to low-cost archival storage over time |
| Compliance reporting | Ready-made reports for audits and regulatory review, exportable as PDF/CSV |
| Request & retrieval | Request a physical file, track issue/return, and flag overdue items |

New models: `Record`, `RecordSeries`, `PhysicalLocation`, `Box`, `CustodyEvent`, `StorageTier`, `RetrievalRequest`.

---

## 9. API & Integrations

**Inherited:** a documented REST API (OpenAPI 3.0 at `/docs`) covering documents, search,
tags, doctypes, correspondents, settings, backup and health.

**What is added**

| Feature | Detail |
|---|---|
| Webhooks & event triggers | Subscribe to `document.created`, `workflow.completed`, `retention.due`, `hold.applied`, … with signed payloads and retries |
| SSO / identity federation | SAML 2.0 and OIDC login, SCIM user/department provisioning |
| Bulk import & export | Manifest-driven bulk ingest and governed bulk export with audit records |
| API keys & scopes | Per-integration keys with scoped, department-bound permissions and rate limits |
| SOAP bridge | Thin SOAP facade over core REST operations for legacy ERP clients |
| Integration console | New page showing connected systems, key health, webhook delivery status and failures |

---

## 10. User interface, rebuilt

The upstream UI is a single 222 KB `index.html` plus a 395 KB `app.js`, styled with
CDN-hosted Bootstrap 5, Font Awesome and Google Fonts, using a purple/violet gradient theme.
It is being **replaced**, not restyled.

### Design system

Apple-inspired structure. Quiet surfaces, generous whitespace, one accent,
motion only to explain state. Strictly **four colours**:

| Token | Value | Use |
|---|---|---|
| White | `#FFFFFF` | Every content page is white |
| HARMAN blue | `#00A7E4` | Fills, rails, progress, charts, active states |
| Deep blue | `#006499` | Primary buttons, links, headings, contrast-safe on white |
| Navy | `#0A2A3D` | Sidebar and dark chrome |
| Grey | `#FAFAFB` → `#16181D` | Structure, borders, text hierarchy |
| Red | `#E5484D` | Reject, overdue, legal hold, destructive only |

`#00A7E4` is only ~2.6:1 on white, so it never carries body text or sits behind white text.
That work goes to `#006499` (~5.6:1). No icon fonts, **no CDN dependencies**. System font stack,
inline SVG icon sprite, hairline borders, soft elevation.

The product is branded **DMS** for HARMAN, with the HARMAN mark in the sidebar, the sign-in
screen and the browser tab. Vendor colours (Maruti `#00559B`, Mahindra `#C8102E`, Tata `#486AAE`)
exist **only inside a document's letterhead**, never in the application chrome: the product is
HARMAN's, the paper may be somebody else's.

> The marks in `frontend/ui/assets/brand/` are stand-ins so the Studio and the rendered PDFs have
> something real to show. Swap in the official artwork keeping the filenames, re-run
> `scripts/seed_brand_assets.py --force`, and every template, thumbnail and PDF picks it up.

### Screens, organised as a journey rather than a feature list

The first demo was judged too technical. The interface is now built around one memorable path a
business user actually walks. See **[docs/ux-redesign-plan.md](docs/ux-redesign-plan.md)**.

| Area | Screens |
|---|---|
| **Workflow** (the spine) | **1 Document Studio** · **2 Review** · **3 Approval** · **4 Status & Tracking** · **5 Publishing** |
| Find & do | My Tasks · All Documents · Search · Ask AI |
| Set up | Approval Routes · People · Activity Log · Settings |
| Reading | Full-screen document viewer (`/documents/view`) |
| Access | Sign in |

Thirteen destinations, and every one is a screen that does real work against real
data. Screens that only illustrated an idea — a process designer that designed nothing, a records
warehouse with no boxes in it, a retention console with no schedule behind it, an integrations
catalogue listing feeds that did not exist — have been removed rather than left to teach people
that half the product is decorative. Their URLs 301 to the screen that does the nearest real job.

**Step 1 is the Studio, and it is where the product opens.** A document begins one of two ways —
written on a letterhead, or brought in as a file — and both are the same step. Splitting them
across two destinations was the largest single source of "which screen do I need?" in the old
navigation.

Each of the five steps ends with a single primary action that leads to the next, a persistent
1-2-3-4-5 stepper shows position, and the document added in step 1 is carried through to step 5
so a walkthrough reads as one continuous act.

### Two products in one, chosen by who signs in

An administrator and an approver want different things, and giving both the same
eighteen destinations serves neither. Navigation and the landing page follow the
signed-in user.

| | Administrator | Approver |
|---|---|---|
| Lands on | Document Studio (step 1) | **My Tasks** |
| Sees | The five steps, Find & do, Set up — 13 destinations | My Tasks · Status & Tracking · All Documents · Search · Ask AI — 5 |
| "New document" button | Yes | No |

Somebody whose job is to read documents and decide on them has no use for the
authoring spine, the route designer, user administration or the publishing
queue. Every extra destination is a chance to get lost on the way to a decision
that is waiting.

The restriction is enforced **on the server**, not just hidden in the menu:
`/templates`, `/organization`, `/audit`, `/settings`, `/publish` and `/process`
redirect an approver to their task list. A hidden link is a courtesy; a redirect
is a rule. Nothing else is blocked, so no in-app link dead-ends — an approver
asked to fix a document still reaches the Studio from the document itself.

### Browser storage is per-user

`localStorage` is per-origin, not per-user, and that had a sharp edge: on a
shared machine, whoever signed in next was offered the **previous person's
signature** to reuse. An approver could have signed a document with a
colleague's mark and name without either of them noticing.

Every key is now scoped to the signed-in user (`dms.signature.v1::<user-id>`),
reads return nothing until identity is known, and signing out clears everything
this product put in the browser.

### Nothing on screen is invented

Every number, list and status in the interface is read from the database. There are no
placeholder figures anywhere, and a panel with nothing to report says so rather than filling
itself in. Removed in this pass, among others:

| Was | Now |
|---|---|
| A repository scope tree claiming 53,075 documents across five departments | Views and suppliers, each with the real count |
| "Extracted fields" with a fixed ₹1,84,00,000 and 98% confidence on every document | The text that was actually read, plus the AI summary when there is one |
| Version history, annotations, access and audit tabs of invented entries | Real version history, and the real approval trail |
| SAP / Salesforce / SharePoint feeds with daily arrival counts | Removed. The intake folder, which is real, remains |
| An audit trail of nine hard-coded rows | The `audit_logs` table, now actually written to |
| "94% set-up time saved", "1,913 approvals", "60% faster" | Removed |
| Approval routes claiming 1,284 uses | Counted from the approvals genuinely started from each route |
| Department cards showing 18,402 documents | People per department, and how many of them can sign |

`log_audit_event` had been writing to the application log with the database insert left as a
`TODO`, so the Activity Log had nothing behind it and every audit claim the product made was
unbacked. It now persists, and the screen reads it.

---

## 11. The approval workflow *(new module)*

The workflow used to live in the browser's `localStorage`, which meant it was a demonstration
rather than a process: the approver who signs step 2 is not the author who built it, and neither
can see the other's browser. It now lives on the server, and every screen reads the same state.

### The model

A workflow is one document's ordered chain of steps. **Exactly one step is `current`** at any
moment; the rest are pending ahead of it or decided behind it. That single invariant answers
every question the product asks — where is it, who has it, is it done, may I act — without
reconstructing history.

| Status | Meaning |
|---|---|
| `active` | In flight, sitting on its current step |
| `changes_requested` | Back with the author. Resubmitting restarts the chain **from step 1** |
| `approved` | Every step acted on. Eligible to publish |
| `rejected` | Ended. A reason was required |
| `published` | Released, and the approved version is locked |

Restarting from step 1 on resubmission is deliberate: an approver who signed version 1 has not
seen version 2, and treating their old signature as still valid would misrepresent what they
agreed to.

### Two permissions, not one

The thing that makes "approve with or without signature" real:

| Permission | Grants |
|---|---|
| `can_approve` | May act on an approval step addressed to them |
| `can_sign` | May apply a signature to that approval |

They are different authorities. A clerk can verify an invoice without being allowed to bind the
company; only a signatory does that. Each **step** independently declares `requires_signature`,
and the two are checked against each other:

* A step requiring a signature **cannot be assigned** to somebody who may not sign — the approval
  designer refuses it while the author is still designing, not three days later when the document
  is stuck.
* Approving a signature step **without** a signature is refused by the API.
* A step that does *not* require one **never asks for one**. A dialog that demands a signature
  nobody asked for teaches people to sign without reading.

Every step arrives at the browser carrying `can_act` and, when false, `blocked_reason`. The screen
never re-derives permission from roles; two implementations of one rule is one too many.

A **role** is granted alongside these, matching the authority: `reader`, `approver` or
`signatory`. Without it a new member could sign in, be assigned an approval, and then get a 403
opening the document.

### Version control

Versions are append-only. A version is written on capture, on every save from the Studio, and
when an approval completes. Restoring an old version does not rewind history — it writes a *new*
version carrying the old content, so the restore is itself part of the record. Approved versions
are locked: they can be superseded, never overwritten.

Any version can be re-read from Tracking or the document page.

### API

```
POST   /api/workflow                        build a chain and start it
GET    /api/workflow?status=&priority=&q=   the tracking list, with search
GET    /api/workflow/stats                  the Home counters
GET    /api/workflow/tasks/mine             what is waiting on me
GET    /api/workflow/by-document/{id}
POST   /api/workflow/{id}/steps/{sid}/decide   approve · reject · changes
POST   /api/workflow/{id}/resubmit          author has made the changes
POST   /api/workflow/{id}/remind · /cancel
GET    /api/workflow/people/approvers       who may be put on a step

GET    /api/publishing/queue                approved, and already published
POST   /api/publishing/{id}/publish · /unpublish
GET    /api/publishing/export/{doc}?format=pdf|docx|txt
GET    /api/publishing/formats/{doc}        which exports work, and why not

GET    /api/documents/{id}/versions
GET    /api/documents/{id}/versions/{vid}/file
POST   /api/documents/{id}/versions/{vid}/restore
```

### Export

| Format | What it is |
|---|---|
| **PDF** | The document of record. Letterhead and all. Served as filed, never re-rendered |
| **DOCX** | The editable text, written directly as OOXML — no extra dependency. The letterhead is *not* carried over, and the screen says so |
| **TXT** | The words only, for another system to consume |

---

## 12. Demo data

`scripts/seed_demo_data.py` builds a working HARMAN Manufacturing scenario. Everything it creates
is real to the system: real users who can sign in, real files on disk, real chains the engine runs.

```
python scripts/seed_demo_data.py            # create anything missing
python scripts/seed_demo_data.py --reset    # remove it and rebuild
```

**6 people** across five departments — with `m.raghavan` and `d.varma` deliberately *unable to
sign*, so the difference between the two permissions is visible rather than theoretical.

**5 documents**, one per department, covering all three formats: a supplier invoice and a Maruti
purchase order on letterhead (PDF), a quality inspection report (PDF, controlled), a Mahindra
supply-agreement amendment (DOCX) and a line-3 shift handover (TXT).

**4 approvals**, each left in a different state so every screen has something real to show:
waiting on a member, part-approved and waiting on a signer, fully approved and queued to publish,
and sent back for changes.

Sign in as any member with `Harman@2026`.

Renamed for a non-technical reader. Dashboard → **Home**, My Approvals → **My Tasks**,
Capture & Sources → **Upload Document**, Audit Trail → **Activity Log**, Organization →
**People & Departments**, Integrations & APIs → **Connected Systems**. The old URLs 301-redirect,
so no existing link or demo script breaks.

---

## 13. Document Studio *(new module)*

Until now a document could only *arrive*. It can now also be **written**, on a real letterhead,
and edited afterwards — and the result is an ordinary `Document`: filed, indexed, searchable,
routable for approval, subject to retention. Nothing about a composed document is a special case.

One surface serves both jobs, because they are the same job:

| Route | Opens |
|---|---|
| `/studio` | The start screen: pick a template, or resume a draft |
| `/studio?template=<id>` | A new document on that letterhead, with starter content |
| `/studio?id=<document_id>` | An existing document, opened for editing |
| `/studio?draft=<draft_id>` | Unfinished work, exactly as it was left |

### What you can do on the page

| | |
|---|---|
| **Edit by hand** | Headings, body, quotes, bold/italic/underline/strike, colour, alignment, bullet and numbered lists, tables, rules, dates. Paste from Word arrives as clean text, not as Word's stylesheet. |
| **Edit with AI** | Summarise · Rewrite · Fix grammar & spelling · Make it formal · Make it concise · Expand · Convert to bullets · Continue writing · Translate · plus a free-text instruction and **Draft this for me** from a blank page. Works on a selection or the whole document. **Nothing is applied until you accept it** — every result is shown first with Replace / Insert below / Discard. |
| **Templates** | Blank, **HARMAN official letterhead**, **HARMAN quality report**, **Maruti Suzuki**, **Mahindra**, **Tata**. Each carries its masthead, brand rail, footer, watermark and margins. Switching one re-skins the page and never touches your words. |
| **Images** | A library of company and vendor marks and seals, seeded on first run, plus **Browse my computer** for anything else. Placed at the cursor at three sizes. |
| **Signature** | Draw, type or upload — the same signature pad used for approvals, so one signature is reused everywhere. Inserts a proper block: *For and on behalf of…*, the mark, the rule, the name, the role and the date. Or insert a blank line for the printed copy. |
| **Save** | Preview the PDF without committing · Save draft (autosaved every couple of seconds) · Save to the repository, then optionally continue straight into **Review** or **Set up process**. |

### One template definition, two renderers

`app/services/doc_templates.py` is the only place a letterhead is described — colours, masthead
height, logo, side rail, watermark, footer lines, margins, all in millimetres. The browser canvas
and the ReportLab PDF renderer both read that same spec. The preview is therefore not an
approximation of the output; it is the output, drawn twice.

### Editing an existing document

| Source | Behaviour |
|---|---|
| Written in the Studio | Round-trips exactly — the sanitised body is stored on the document. |
| Arrived as a file (PDF, scan, Word) | The extracted text is laid out for editing, and the screen **says so plainly** rather than implying a lossless round trip. |

Saving an edit never overwrites: it files a **new version** (`v1.0 → v1.1`), links it to the
original in both directions, and leaves the original file untouched. Approved documents cannot be
rewritten, only superseded.

### API

```
GET    /api/studio/templates            every letterhead, with its full spec
GET    /api/studio/templates/{id}/starter
GET    /api/studio/assets               the image library
POST   /api/studio/assets               upload an image (multipart)
GET    /api/studio/ai/actions           what "Edit with AI" can do
POST   /api/studio/ai                   run one editing action
GET    /api/studio/drafts               ·  POST /api/studio/drafts
GET|PUT|DELETE /api/studio/drafts/{id}
GET    /api/studio/source/{document_id} open a document for editing
POST   /api/studio/preview              render to PDF without saving
POST   /api/studio/publish              file it in the repository
```

Bodies are sanitised on the way in **and** again at render time (`bleach` with a strict tag,
attribute and CSS allow-list). Images are referenced by asset id, never by path, so a body can only
ever embed a file the server already knows about — and the renderer makes no outbound requests.

---

## 14. Approval signatures on the document

An approval that only records a signature in a database is an approval nobody
outside the system can see. Signatures are stamped onto the document itself.

### How it works

Signatures are drawn as a **PDF overlay** and merged onto the existing pages,
never re-flowed into the source. That matters: it means a scanned invoice that
went through three approvers gets the same signed rendition as a letter written
in the Studio. Nothing about the approach assumes the document came from here.

| | |
|---|---|
| **Position** | Held as a **fraction of the page**, not in millimetres. A block sits in the same visual place whether the paper is A4, Letter, or a scan at some arbitrary size |
| **Automatic placement** | Along the bottom of the last page, three across. The page is measured first: if the body text reaches too far down, the signatures go on a titled **Approval signatures** sheet instead of on top of somebody's paragraph |
| **Footer awareness** | Text lying wholly in the footer band is treated as page furniture, not content. Without that, every letterheaded page looks full to the bottom edge and nothing ever qualifies for its own last page |
| **Adjusting** | A placement editor: the real page rendered as an image, with the blocks draggable on top. Drag, resize, preview, save — or reset to automatic |
| **Designation** | Captured **at the moment of signing**, not read from the user record later. Someone who signs as Head of Finance and is promoted next year must still read as Head of Finance on the document they signed. Correctable, and the correction is audited |

### What a block carries

The mark, a rule, the signatory's name, their designation, and which step they
approved with the timestamp. Steps marked *approval only* produce no signature
and correctly contribute nothing.

### Publishing

Publishing produces **two locked versions**, deliberately:

```
v1.0  "Approved v1.0 · 2 approver(s)"                  ← what the approvers saw
v1.1  "Published with 2 approval signatures stamped on" ← what went out
```

Collapsing them into one would lose the ability to prove either. The approved
bytes are never overwritten; the signed rendition is a new file alongside them.
A published document refuses further re-placement until the publication is
withdrawn.

If stamping fails — a corrupt PDF, a missing file — the document still
publishes, unsigned, and the failure is logged. Publishing is the point of the
exercise and a rendering problem must not block a release.

### API

```
GET    /api/signatures/{workflow_id}/layout        where each signature sits
PUT    /api/signatures/{workflow_id}/layout        move them
POST   /api/signatures/{workflow_id}/layout/reset  back to automatic
PUT    /api/signatures/{workflow_id}/designation   correct a title
GET    /api/signatures/{workflow_id}/preview       the signed PDF, unsaved
GET    /api/signatures/{workflow_id}/page/{n}      a page image, for the editor
```

Page images come from **PDFium** (`pypdfium2`), which is BSD/Apache licensed and
ships as a self-contained wheel — deliberately not PyMuPDF, which is AGPL and
would be a licensing problem for a commercial derivative.

---

## 15. Document viewer, fixed

The preview used to show a slice of *extracted text* dressed up as a page, so it never matched the
document. It now shows the document:

| Format | Rendered as |
|---|---|
| PDF | The browser's own PDF engine, full stage — real pages, zoom, search, selection, print |
| Image | The image at full resolution, with zoom and fit-to-width |
| Text, Markdown, CSV | The file itself, line breaks intact, on a real sheet |
| Word, Excel | An honest "a browser cannot display this faithfully" plus the download, and the extracted text clearly labelled as *not* the layout |
| File missing | Says so, rather than rendering an empty page |

`GET /api/documents/{id}/preview-info` tells the front end what the file actually is and how to
show it, so nothing is guessed from a filename. Text documents used to be served with
`Content-Disposition: attachment`, which is why they downloaded instead of displaying; they are now
served inline with an explicit charset.

**Open the whole document** opens `/documents/view?id=…` — a full-screen reader with no sidebar and
no page chrome, for documents too long to read in a panel.

---

### New in this pass

| Feature | Detail |
|---|---|
| **Document Studio** | Create and edit documents on HARMAN and vendor letterheads, with AI editing, an image library and in-document signatures. See section 11. |
| **Working viewer** | The preview shows the real file, whatever the format, plus a full-screen reader. See section 12. |
| **Approval Routes** | A saved route holding steps, approvers, deadlines, whether a signature is required, and the retention rule to apply on completion. Picked as the first choice in step 3; the system suggests one from the document type. (Renamed from "Templates" now that document templates also exist.) |
| **Signature** | Draw, type or upload. Saved once and reused. Rendered in the status trail, on the document and in the approval certificate. |
| **Three-way decision** | **Approve & Sign** / **Request Changes** / **Reject** on one bar, identical on My Tasks, Track Status and the document page. Rejection requires a reason; request-changes requires a note and routes back one step. |
| **Live status trail** | Every step with who acted, when, their comment and their signature, with rejections in red and the reason quoted. |

---

## Removed / retired

Trimmed as out of scope for an enterprise deployment:

| Removed | Reason |
|---|---|
| Legacy `frontend/index.html`, `app.js`, `styles.css`, `login.html` and supporting assets | Replaced by the new design system; moved out of the served directory to [`legacy-ui/`](legacy-ui/) |
| "About" tab (author bios, donation and social links) | Not appropriate in a customer-deployed product |
| Upstream marketing/branding header, buy-me-a-coffee and star-the-repo calls-to-action | Same |
| Bootstrap, Font Awesome, Google Fonts CDN links | External network calls from an on-prem product; also a supply-chain and offline-install problem |
| Purple/violet gradient theme and gradient text | Replaced by the four-colour system |
| Personal-use framing ("tax relevance" as a first-class field) | Demoted to a normal metadata field, not a top-level concept |
| `app/routers/admin_fix.py` ad-hoc repair endpoints | Superseded by the CLI maintenance commands |
| Screenshot gallery of the old UI | Obsolete |

Nothing is deleted destructively. The retired frontend files were moved to
[`legacy-ui/`](legacy-ui/), outside the directory the application serves, so they remain
available for comparison until the new interface reaches full parity, but are unreachable
over HTTP and referenced by no code.

---

## Architecture

```
DMS/
├── app/                      # FastAPI backend
│   ├── middleware/           # Auth, CSRF, rate limiting, logging, error handling
│   ├── routers/              # REST API endpoints
│   │   ├── (existing)        # auth, documents, search, tags, doctypes,
│   │   │                     # correspondents, settings, health, backup, security
│   │   └── (new)             # organizations, departments, permissions, workflows,
│   │                         # versions, annotations, retention, records, holds,
│   │                         # connectors, webhooks, audit
│   │   ├── studio.py         # Document Studio: templates, assets, AI, drafts,
│   │   │                     # PDF preview, publish
│   │   ├── workflow.py       # Approvals: build, decide, my tasks, search, stats
│   │   └── publishing.py     # Step 5: publish queue and PDF/DOCX/TXT export
│   │   └── audit.py          # The activity log, read from audit_logs
│   ├── services/             # AI, OCR, search, processing
│   │   ├── workflow_service.py  # THE approval engine. Every state change.
│   │   ├── version_service.py   # Append-only version history
│   │   ├── role_service.py      # Standard roles, kept in step with authority
│   │   ├── doc_templates.py  # Letterhead specs, read by BOTH renderers
│   │   ├── pdf_render.py     # Sanitised HTML → letterheaded PDF (ReportLab)
│   │   ├── docx_render.py    # The same HTML → .docx, via stdlib zipfile
│   │   ├── authoring_ai.py   # "Edit with AI": rewrite, summarise, correct, draft
│   │   └── media_service.py  # The image library and its upload rules
│   └── utils/                # Backup, validation, file security,
│                             # additive schema migrations
├── config/models.json        # Model names per provider
├── frontend/
│   └── ui/                   # The interface, zero dependencies, no build step
│       ├── css/dms.css       # Design system (palette, components)
│       ├── css/studio.css    # The Studio: ribbon, paper, letterhead chrome
│       ├── js/shell.js       # Shell, nav, journey stepper, flow state,
│       │                     # signature pad, decision bar, API helper
│       ├── js/studio.js      # The editor
│       ├── js/viewer.js      # Document rendering, shared by detail + full screen
│       ├── assets/brand/     # HARMAN and vendor marks (SVG for web, PNG for PDF)
│       ├── studio · review · process · track · publish   # the five-step spine
│       ├── studio.html       # Step 1 and the home page: write it or bring it in
│       ├── viewer.html       # Full-screen reader
│       ├── tasks.html        # The member's side: decide, with or without a signature
│       └── *.html            # one file per remaining screen
├── legacy-ui/                # Retired upstream interface + superseded screens
├── scripts/
│   ├── seed_brand_assets.py  # Redraw the brand PNGs the PDF renderer embeds
│   └── seed_demo_data.py     # A working HARMAN scenario: people, docs, approvals
├── docs/
│   ├── ux-redesign-plan.md   # Why the journey is shaped this way
│   └── groq-setup.md         # Provider, embedding and OCR configuration
├── tests/                    # Regression + end-to-end tests
└── Dockerfile / setup.sh / setup.ps1
```

### Technology stack

| Layer | Choice |
|---|---|
| Backend | FastAPI, SQLAlchemy, Pydantic |
| AI / ML | Groq (default), OpenAI, Azure OpenAI, ChromaDB |
| OCR | Vision model (Qwen on Groq) with Tesseract fallback |
| Document rendering | ReportLab (pure Python wheels, no system libraries) |
| HTML sanitising | bleach + tinycss2, applied on input **and** at render time |
| Database | SQLite (dev) → PostgreSQL (enterprise deployment) |
| Frontend | Vanilla JavaScript + custom design system, no build step, no CDN |
| Deployment | Docker / Podman |

### AI models

Defaults, all configurable in [`config/models.json`](config/models.json):

| Role | Model |
|------|-------|
| Chat + reasoning | `openai/gpt-oss-120b` (Groq) |
| Vision / OCR | `qwen/qwen3.6-27b` (Groq) |
| Embeddings | `all-MiniLM-L6-v2` (local, CPU, no key) |

Groq does not offer an embeddings endpoint, so semantic search runs a small ONNX model locally
by default. See **[docs/groq-setup.md](docs/groq-setup.md)** for the full guide.

---

## Delivery roadmap

Aligned to the four proposed next steps:

| Phase | Scope |
|---|---|
| **1. Discovery workshop** | Map departments, roles and current source documents; finalise the org model, records schedule and retention rules |
| **2. Pilot rollout** | New UI + org/department access control + workflow automation for one priority process |
| **3. AI configuration** | Tune capture, classification and search models; enable smart extraction and the review queue |
| **4. Enterprise scale-up** | All departments, full retention & records governance, connectors, SSO and webhooks |

### Business value targets

`70%` faster document retrieval · `60%` less manual approval time · `100%` audit-ready trail · open, API-first architecture.

> Illustrative targets, to be validated against the organisation's current baselines during discovery.

---

## Quickstart

### Prerequisites
- Docker installed and running
- 4 GB+ RAM, 10 GB+ free disk

### Docker

```bash
./setup.sh build
./setup.sh prod
```

Or manually:

```bash
docker build -t dms:local .
cp .env.example .env          # set a strong SECRET_KEY first
docker run -d --name dms-local -p 127.0.0.1:8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/backups:/app/data/backups \
  dms:local
```

The application is available at `http://localhost:8000`.

### Windows

```powershell
./setup.ps1 build
./setup.ps1 prod
```

Or without Docker:

```powershell
python -m venv venv
venv\Scripts\Activate
pip install -r requirements.txt
python cli.py serve
```

OCR tooling on Windows:
- Tesseract: `winget install tesseract-ocr` or `choco install tesseract`
- Poppler (PDF OCR): `choco install poppler`, then point `Settings.poppler_path` at the poppler `bin` folder

### Local development

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## Initial setup

1. **Add an AI provider key.** Get a Groq key at [console.groq.com/keys](https://console.groq.com/keys),
   put it in `.env` as `GROQ_API_KEY=gsk_...`, verify with `python cli.py check-ai`.
2. **Create the first administrator.** Open `http://localhost:8000`; the first registration becomes admin.
3. **Define the organization.** Create org units and departments before inviting users, so
   permissions inherit correctly from the top of the tree.
4. **Load the records schedule.** Import retention policies per document type before bulk ingest.
5. **Start capturing.** Upload or connect a source; AI extracts title, summary, correspondent,
   document type, document date and tags automatically.

---

## Configuration

Copy `.env.example` to `.env` (the setup script does this and generates a strong `SECRET_KEY`).

```dotenv
SECRET_KEY=replace-with-generated-value
ENVIRONMENT=production

DATABASE_URL=sqlite:///./data/documents.db

# AI provider: groq | openai | azure
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...

# Embeddings: local (default, no key) | openai | azure
EMBEDDING_PROVIDER=local

# OCR: auto (text layer -> vision -> tesseract) | vision | tesseract
OCR_ENGINE=auto

LOG_LEVEL=INFO
MAX_FILE_SIZE=100MB
ALLOWED_EXTENSIONS=pdf,png,jpg,jpeg,tiff,bmp,txt,text,md,markdown,docx,xlsx,pptx,eml,csv
```

**Model names are not set here.** They live in [`config/models.json`](config/models.json).
Precedence, lowest to highest: code defaults → `config/models.json` → environment/`.env` →
database settings. Run `python cli.py sync-model-config` if a model was previously saved
through the Settings UI.

### CLI reference

```bash
python cli.py init                      # create database + folders
python cli.py serve                     # start the web server
python cli.py status                    # configuration and health overview
python cli.py check-ai                  # probe chat, embedding and vision models
python cli.py sync-model-config         # push config/models.json into the database
python cli.py reindex-vectors --force   # rebuild embeddings after a model change
python cli.py process                   # process staging folder now
python cli.py db analyze|optimize|create-indexes|size
python cli.py backup create|list|restore
```

---

## API documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

```python
import requests

BASE_URL = "http://localhost:8000"

session = requests.Session()
session.post(f"{BASE_URL}/api/auth/login",
             json={"username": "admin", "password": "your-password"})

# Upload
with open("document.pdf", "rb") as f:
    doc_id = session.post(f"{BASE_URL}/api/documents/upload",
                          files={"file": f},
                          data={"title": "Q4 Report", "tags": "finance,quarterly"}
                          ).json()["id"]

# Semantic search
results = session.get(f"{BASE_URL}/api/search/semantic",
                      params={"query": "What were the Q4 revenue numbers?", "limit": 5}).json()

# Ask a question
answer = session.post(f"{BASE_URL}/api/ai/ask",
                      json={"question": "Summarize the key findings from Q4 reports",
                            "document_ids": [doc_id]}).json()["answer"]
```

---

## License

MIT. See [LICENSE](LICENSE). This derivative work retains the original copyright of
Jannik Reinhard and Fabian Peschke for the upstream `DocumentManager` codebase.
