# 03 · Non-Functional Requirements

> **Audience:** architects, QA, operations. These are the qualities the system
> must have, as opposed to the behaviours in doc 02. Each carries how it is
> achieved and how to verify it. ⚠️ marks a requirement that is aspirational or
> unverified rather than measured.

---

## NFR-1 · Performance

| # | Requirement | How it is achieved | Verify |
|---|---|---|---|
| NFR-1.1 | Server start-up **shall not** block on database, AI or OCR initialisation | Startup schedules `ensure_defaults()` after 2 s and the file watcher after 3 s as background asyncio tasks (`app/main.py:122`) | Server answers `/health` within ~1 s of launch |
| NFR-1.2 | An interactive page load **should** complete in under 2 s on a repository of ~10 000 documents | Indexed columns, pagination capped at 100, `joinedload` on workflow steps | Load `/documents` against a seeded set |
| NFR-1.3 | Document upload **shall** return before OCR/AI run | Upload writes to staging and returns; the watcher does the work | `POST /api/documents/upload` latency ≈ write time |
| NFR-1.4 | Studio publish **shall** return before classification and indexing | `BackgroundTasks.add_task(_enrich, …)` (`app/routers/studio.py:605`) | Publish latency = render + write |
| NFR-1.5 | An AI request **shall** time out at `ai_request_timeout` (default **60 s**) and retry at most `ai_max_retries` (default **2**) with exponential backoff capped at 8 s | `_make_ai_request_with_retry` (`app/services/ai_service.py:221`) | `tests/test_groq_provider.py` |
| NFR-1.6 | Semantic search **shall** abandon further strategies after **45 s** total | `max_search_time` (`app/services/search_service.py:567`) | — |
| NFR-1.7 | Repeated AI failure **shall not** degrade unrelated requests | Circuit breaker: 3 failures → 300 s open | `search_service.py:159` |
| NFR-1.8 | Expensive process-wide discovery **shall** be cached | Tesseract binary, Poppler path and the local ONNX embedder are resolved once per process and cached under a lock | `ocr_service.py:53`, `embedding_service.py:44` |
| NFR-1.9 | AI worker threads **shall not** leak | One shared `ThreadPoolExecutor(max_workers=8)` for the whole process, not one per `AIService` | `ai_service.py:28` |
| NFR-1.10 | Vector search **shall** retrieve up to 100 candidates then re-rank locally | `_semantic_search` | — |

⚠️ NFR-1.2 is a design intent, not a measured figure. No load test exists.

---

## NFR-2 · Capacity and scalability

| # | Requirement | Current position |
|---|---|---|
| NFR-2.1 | Maximum file size | **100 MB**, configurable (`max_file_size`) |
| NFR-2.2 | Maximum composed-document body | **900 000 characters** (`MAX_BODY_CHARS`) |
| NFR-2.3 | Maximum signature image | **2 MB** data URL |
| NFR-2.4 | Vision OCR page cap | **20 pages**, image cap 4 MB |
| NFR-2.5 | Workflow list cap | **500** per request |
| NFR-2.6 | Audit log query cap | **1 000** entries, 365-day window |
| NFR-2.7 | Search page size | 1–100, default 20 |
| NFR-2.8 | Database | SQLite is the default and **serialises writes**. PostgreSQL via `DATABASE_URL` is the path to concurrency. ⚠️ No Alembic migration chain exists for Postgres — `alembic` is a listed dependency but there is no `alembic/` directory; schema is created by `create_all` plus additive DDL. |
| NFR-2.9 | Horizontal scaling | ⚠️ **Not supported as-is.** Rate-limit counters, the AI capability cache and the ChromaDB persistent client are all per-process in-memory state. Multi-worker deployment needs shared stores first. |
| NFR-2.10 | Vector store | Embedded ChromaDB scales to the low hundreds of thousands of documents; a remote Chroma server is configurable via `chroma_host` / `chroma_port` |

---

## NFR-3 · Availability and resilience

| # | Requirement | Mechanism |
|---|---|---|
| NFR-3.1 | No single AI failure **shall** take the product down | Every AI path has a non-AI fallback: full-text search, Tesseract OCR, filename-derived titles |
| NFR-3.2 | Quota exhaustion **shall** trigger key failover, then stop | `_switch_key` then `_is_daily_cap` short-circuit |
| NFR-3.3 | ChromaDB failure **shall** degrade, not crash | Falls back to an in-memory collection (`vector_db_service.py:74`) |
| NFR-3.4 | Missing `libmagic` **shall** degrade, not crash | Extension-based MIME detection |
| NFR-3.5 | Missing Tesseract/Poppler **shall** be reported, not fatal | Logged with install instructions per OS |
| NFR-3.6 | A per-document processing failure **shall not** stop the batch | Each stage try/except, status recorded on the document |
| NFR-3.7 | Startup **shall** survive an uninitialised database | `init_db` failures are logged; the app still serves |
| NFR-3.8 | Signature stamping failure **shall not** block publication | Publishes unsigned, logs the error |
| NFR-3.9 | Audit write failure **shall not** fail the user's action | Wrapped and swallowed |
| NFR-3.10 | Graceful shutdown | File watcher and backup scheduler stopped on shutdown event |

---

## NFR-4 · Security

Fully specified in [doc 09](09-security-design.md). Summary of the requirements:

| # | Requirement |
|---|---|
| NFR-4.1 | Passwords stored only as bcrypt hashes |
| NFR-4.2 | Sessions server-side, HttpOnly cookie, 24 h; JWT 30 min |
| NFR-4.3 | CSRF protection via signed double-submit cookie on all state-changing requests |
| NFR-4.4 | Rate limiting: 100 req/min default; **5 login attempts / 5 min**, counting failures only |
| NFR-4.5 | Uploaded files written `0600` (owner-only) — invoices and contracts must not be world-readable |
| NFR-4.6 | Path-traversal protection on every filename that reaches the filesystem |
| NFR-4.7 | HTML sanitised on input **and** at render |
| NFR-4.8 | CORS restricted to a configured origin list; `X-Forwarded-For` honoured **only** from trusted proxy IPs |
| NFR-4.9 | No static default secret key — a random per-process key when unset |
| NFR-4.10 | `X-Content-Type-Options: nosniff` on every file response |
| NFR-4.11 | Container runs as a non-root user (uid 1000) |

---

## NFR-5 · Usability

| # | Requirement | How |
|---|---|---|
| NFR-5.1 | The navigation **shall** be the process | Five numbered steps as the primary menu |
| NFR-5.2 | Each role **shall** see only what it can act on | Admin gets the full spine; an approver gets My Tasks first, and lands there |
| NFR-5.3 | The UI **shall not** offer an action the API will refuse | `can_act` / `blocked_reason` resolved server-side and returned with every step |
| NFR-5.4 | A refusal **shall** say what to do about it | e.g. "Grant signature authority, choose someone else, or turn the signature requirement off for this step." |
| NFR-5.5 | Dates **shall** be unambiguous | Displayed `DD-MM-YYYY` in IST, and every date field spells the chosen date out underneath, because a browser's own date picker follows its locale and `06-08` must never read as June |
| NFR-5.6 | Preview **shall** be the output, not an impression of it | One template spec, two renderers |
| NFR-5.7 | Nothing on screen **shall** be invented | Counts come from the server; an empty log says it is empty |
| NFR-5.8 | Browser storage **shall** be per-user | Keys namespaced by user; cleared on sign-out (`shell.js:629`) |
| NFR-5.9 | Retired URLs **shall** keep working | 301 redirects to the nearest real screen |
| NFR-5.10 | Accessibility | ⚠️ No formal WCAG conformance claim. Semantic HTML, focus states and keyboard navigation in the combobox/people-picker are present; a full audit has not been done. |

---

## NFR-6 · Maintainability

| # | Requirement | How |
|---|---|---|
| NFR-6.1 | Business rules **shall** live in exactly one place | `workflow_service.py` is the only module that changes workflow state; routers validate and serialise |
| NFR-6.2 | Responses **shall** be built by one serialiser per entity | `_workflow_json` / `_step_json` |
| NFR-6.3 | Configuration **shall** be declarative and layered | `config/models.json` + env + DB, precedence documented in code |
| NFR-6.4 | Schema evolution **shall** be additive and idempotent | `utils/schema_migrations.py` — add a column if missing, never drop or retype, so an older build still runs against a migrated database |
| NFR-6.5 | No build step on the front end | Vanilla JS, no bundler, no CDN, no framework upgrade treadmill |
| NFR-6.6 | Intent **shall** be recorded next to the code | The codebase carries unusually dense explanatory comments stating *why*, not *what* |
| NFR-6.7 | Provider differences **shall** be isolated | `ai_client_factory.py` + `sdk_compat.py` + `model_config.py` |
| NFR-6.8 | ⚠️ Dead/duplicated code | `middleware/auth_middleware.py` and `middleware/logging_middleware.py` are imported-then-disabled; `schemas_validated.py` partly duplicates `schemas.py`. See doc 11. |

---

## NFR-7 · Portability

| # | Requirement | How |
|---|---|---|
| NFR-7.1 | Runs on Linux, Windows and macOS | Tesseract/Poppler discovery probes OS-specific paths; `libmagic` optional |
| NFR-7.2 | No system libraries for document rendering | ReportLab and pypdfium2 ship as self-contained wheels |
| NFR-7.3 | Container-first deployment | Multi-stage Dockerfile, non-root, healthcheck, `config/` mountable to change models without rebuild |
| NFR-7.4 | Database portable | SQLAlchemy; switch with `DATABASE_URL` |
| NFR-7.5 | AI provider portable | Groq / OpenAI / Azure behind one factory; models named in `config/models.json` |
| NFR-7.6 | Licence hygiene | pypdfium2 (BSD/Apache) chosen deliberately over PyMuPDF (AGPL) |

---

## NFR-8 · Compliance and auditability

| # | Requirement | How |
|---|---|---|
| NFR-8.1 | Every significant action attributable to a person | `audit_logs`: actor, action, resource, IP, user agent, timestamp |
| NFR-8.2 | The approval trail **shall** be complete and ordered | `workflow_events` + `step_decisions` — one row per person per step |
| NFR-8.3 | An audit trail **shall not** mutate | Signatures stored per use; designations frozen; versions append-only |
| NFR-8.4 | "This is the version they signed" **shall** be provable | The approved version is locked before the signed rendition is written as a new version |
| NFR-8.5 | Timestamps stored UTC | Displayed in IST — correct if the server ever moves (`app/utils/ist.py`) |
| NFR-8.6 | ⚠️ Retention enforcement | **Not implemented.** A retention label can be stored; nothing acts on it. |
| NFR-8.7 | ⚠️ Legal hold | Not implemented. |
| NFR-8.8 | ⚠️ Audit log immutability | `audit_logs` rows are ordinary database rows. Anyone with database access can alter them. Append-only storage or signing would be needed for a hard guarantee. |

---

## NFR-9 · Observability

| # | Requirement | How |
|---|---|---|
| NFR-9.1 | Structured application logging | `loguru`, configured in `utils/logging_config.py`; files under `data/logs/` |
| NFR-9.2 | Security events logged separately | `log_security_event` for login outcomes |
| NFR-9.3 | Per-document processing log | `processing_logs` table: operation, status, message, duration |
| NFR-9.4 | Orchestration probes | liveness / readiness / startup |
| NFR-9.5 | System metrics | CPU, memory, disk, document counts via `psutil` |
| NFR-9.6 | Log download | `GET /api/settings/logs/download` |
| NFR-9.7 | ⚠️ No metrics export | No Prometheus endpoint, no tracing, no alerting integration |

---

## NFR-10 · Data integrity

| # | Requirement | How |
|---|---|---|
| NFR-10.1 | No duplicate content | `documents.file_hash` unique, SHA-256, checked at upload and in the pipeline |
| NFR-10.2 | Cascading deletes where correct | Workflow → steps → decisions, and → events, use `cascade="all, delete-orphan"` |
| NFR-10.3 | Version files never overwritten | Copied into `versions/` on capture |
| NFR-10.4 | Vector store kept in step | Deletes remove vectors; `upsert` keeps re-indexing idempotent |
| NFR-10.5 | Embedding dimension mismatch detected and explained | The error names the fix: `python cli.py reindex-vectors --force` |
| NFR-10.6 | ⚠️ No foreign-key enforcement in SQLite by default | SQLite does not enforce FKs unless `PRAGMA foreign_keys=ON` is set per connection; it is not set here. Referential integrity relies on application code. |

---

## Acceptance thresholds summary

For a QA sign-off, these are the numbers that matter:

| Metric | Target |
|---|---|
| Server responds to `/health` after launch | < 2 s |
| Upload API response (100 MB file excluded) | < 1 s |
| Studio publish response | < 3 s |
| Search response with AI available | < 10 s |
| Search response with AI unavailable (full-text) | < 2 s |
| AI request hard timeout | 60 s |
| Login attempts before lockout | 5 per 5 min per IP |
| Default request budget | 100 per minute per IP |
| Session lifetime | 24 h |
| JWT lifetime | 30 min |
