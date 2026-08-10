# 06 · Low-Level Design

> **Audience:** developers. Module by module: what it is responsible for, how it
> works internally, what it assumes, how it fails, and where to extend it.
> Read [doc 04](04-high-level-design.md) first for the shape; this is the inside.

---

## Contents

1. [Configuration subsystem](#1-configuration-subsystem)
2. [Database and migrations](#2-database-and-migrations)
3. [Authentication and authorisation](#3-authentication-and-authorisation)
4. [Middleware](#4-middleware)
5. [Capture pipeline](#5-capture-pipeline)
6. [OCR subsystem](#6-ocr-subsystem)
7. [AI subsystem](#7-ai-subsystem)
8. [Embeddings and vector store](#8-embeddings-and-vector-store)
9. [Search and RAG](#9-search-and-rag)
10. [Approval engine](#10-approval-engine)
11. [Signature subsystem](#11-signature-subsystem)
12. [Versioning](#12-versioning)
13. [Document Studio](#13-document-studio)
14. [Rendering: PDF and DOCX](#14-rendering-pdf-and-docx)
15. [Publishing and export](#15-publishing-and-export)
16. [Audit](#16-audit)
17. [Backup](#17-backup)
18. [File security](#18-file-security)
19. [CLI](#19-cli)
20. [Extension recipes](#20-extension-recipes)

---

## 1. Configuration subsystem

**Files:** [app/config.py](../../app/config.py) ·
[app/services/model_config.py](../../app/services/model_config.py) ·
[config/models.json](../../config/models.json)

### 1.1 Precedence

```
code defaults  <  config/models.json  <  environment / .env  <  database settings table
```

Implemented in two places:

- `Settings.model_post_init` (`app/config.py:120`) overlays `models.json` onto
  fields **not** explicitly set. `self.model_fields_set` is the discriminator —
  an env var or constructor kwarg always wins over the file.
- `DatabaseSettings._load_from_database` (`app/config.py:212`) then overrides
  everything from the `settings` table, coercing to the current attribute's
  type (bool / int / float / str). Empty strings are ignored for `*_api_key`
  fields so a blank row cannot wipe a working key.

### 1.2 Access pattern

```python
get_settings()        # cached process-wide singleton, no DB layer
get_settings(db)      # ALWAYS a fresh DatabaseSettings — picks up live changes
reset_settings()      # drops the cache AND the models.json cache
```

> **The trap.** `get_settings(db)` constructs a new `DatabaseSettings` on every
> call, which means a database round-trip per call. Services take `db` in their
> constructor and resolve settings **once**, not per operation.

### 1.3 Secret key

`secret_key` defaults to `secrets.token_urlsafe(32)` generated **per process**.
There is deliberately no static default — anything signed with a well-known key
would be forgeable by anyone who read the source. For a stable value across
restarts and workers, set it in the database settings table.

CSRF tokens are signed with `app_settings.secret_key` for exactly this reason
(`app/main.py:63`): a per-process random key would invalidate every browser's
cookie on restart.

### 1.4 Extension point

Add a field to `Settings`, and (optionally) a mapping in
`model_config.as_settings_overrides()` if it should be configurable from
`models.json`. Nothing else is needed — the DB layer picks it up by name.

---

## 2. Database and migrations

**Files:** [app/database.py](../../app/database.py) ·
[app/utils/schema_migrations.py](../../app/utils/schema_migrations.py)

### 2.1 Engine

```python
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if sqlite else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

`check_same_thread=False` is required because the file watcher and background
tasks run on other threads.

### 2.2 Session lifecycle

- **Request scope:** `Depends(get_db)` — yield/close.
- **Background scope:** `SessionLocal()` explicitly, in a `try/finally`, or
  `with SessionLocal() as db:`.

> ⚠️ **Never pass a request-scoped session into a background task.** FastAPI
> closes it when the response is sent. `_enrich` in the Studio router opens its
> own (`app/routers/studio.py:751`) — follow that pattern.

### 2.3 `init_db()`

1. Import `models` so every table is registered on the metadata.
2. `Base.metadata.create_all(bind=engine)`.
3. `apply_migrations(engine)` — additive DDL.
4. `initialize_default_settings(db)`.
5. `ensure_default_document_types(db)`.

Failures at steps 4–5 roll back and log, but do not prevent start-up.

### 2.4 `apply_migrations`

For each `(table, column, ddl)` in `ADDITIONS`: skip if the table does not exist
(`create_all` will build it complete), skip if the column already exists,
otherwise `ALTER TABLE … ADD COLUMN …`. Failures are logged as warnings — a
parallel worker may have won the race.

---

## 3. Authentication and authorisation

**File:** [app/services/auth_service.py](../../app/services/auth_service.py)

### 3.1 Two credentials, one resolution

| Credential | Lifetime | Storage | Used by |
|---|---|---|---|
| Session token | 24 h | `sessions` row + HttpOnly cookie | The browser UI, and every server-rendered page route |
| JWT | 30 min | Stateless, HS256 | API clients, scripts |

`get_current_user_flexible` tries the bearer token first, then falls back to the
session cookie, then raises 401.

### 3.2 The JWT secret

`get_secret_key(db)` reads `jwt_secret_key` from settings. **If unset it
generates one and writes it to the database**, so it survives restarts. This is
a side effect inside a getter — surprising, but deliberate: a JWT secret that
changes on restart invalidates every issued token.

### 3.3 Dependency ladder

```
get_current_user            JWT only, raises 401
get_current_user_from_session   session only, returns None (no raise)
get_user_from_session_token     non-dependency version, used by page routes
get_current_user_flexible   JWT or session, raises 401       ← the default
require_permission(p)       JWT + permission
require_permission_flexible(p)  either + permission          ← the default
require_admin / require_admin_flexible
```

### 3.4 Permission resolution

`User.has_permission(perm)` (`app/models.py:514`):

```
if is_admin: return True
for role in roles:
    perms = json.loads(role.permissions)
    if perm in perms: return True
return False
```

⚠️ The `"*"` permission held by the legacy `admin` role is **not** special-cased
here — it only matches a literal `"*"` request. Admin authority comes from
`is_admin`, not from the role.

### 3.5 Page-route authorisation

Page routes do not use `Depends`; `_make_page_route` (`app/main.py:317`) calls
`get_user_from_session_token` directly, redirects to `/login` when absent, and
redirects non-admins away from `ADMIN_ONLY_PAGES`. A redirect is a rule; a
hidden link is only a courtesy.

---

## 4. Middleware

### 4.1 CSRF — `app/middleware/csrf_middleware.py`

Signed double-submit cookie:

1. Cookie `csrf_token` = `<token>.<HMAC-SHA256(token, secret)>`, `httponly=False`
   so JavaScript can read it, `samesite=strict`, 24 h.
2. On a state-changing request the middleware compares the `X-CSRF-Token` header
   (or a `csrf_token` field in a JSON body) against the verified cookie token.
3. `request.state.csrf_token` carries the resolved token so
   `GET /api/csrf-token` hands back **exactly** what the cookie will carry —
   minting a fresh one there would race the middleware's own `Set-Cookie` and
   fail every subsequent POST with 403.

**Excluded paths** (`app/main.py:65`): login, logout, check-session, setup
endpoints, `/api/health`, `/api/settings/test/ai`, `/docs`, `/openapi.json`,
`/redoc`, `/api/csrf-token`.

> ⚠️ Exclusion matching is `path in exclude_paths` **or**
> `path.startswith(excluded)` (`csrf_middleware.py:131`). Prefix matching means
> `/api/health` also excludes `/api/health/anything`. Keep exclusions specific.

### 4.2 Rate limiting — `app/middleware/rate_limit_middleware.py`

Sliding window per `(ip, path)`, held in an in-process dict under a `Lock`,
with a cleanup coroutine every 300 s.

| Path | Limit |
|---|---|
| default | 100 / 60 s |
| `/api/auth/login`, `/api/auth/setup/initial-user` | 5 / 300 s |
| `/api/documents/upload` | 20 / 60 s |
| `/api/ai/chat` | 30 / 60 s |
| `/api/ai/extract` | 20 / 60 s |

**Two behaviours worth knowing:**

1. **Auth endpoints count failures only.** The limit exists to stop password
   guessing; charging successful sign-ins locks legitimate users out of their
   own account after five logins. The check runs *before* the request, the
   charge *after*, based on the status code (401/403/422).
2. **A successful sign-in clears that IP's failures**, so a user who mistyped a
   few times is not locked out afterwards (`rate_limit_middleware.py:226`).

**Proxy handling:** `X-Forwarded-For` / `X-Real-IP` are honoured **only** when
the direct peer is in `trusted_proxy_ips`. Otherwise a client could choose its
own rate-limit bucket.

⚠️ State is per-process — see doc 11 for the multi-worker implication.

### 4.3 Error handling — `app/middleware/error_handler.py`

Four handlers registered on the app. API paths (`/api/…`) get JSON; everything
else gets a styled HTML error page (`ErrorHandler.create_error_page`). The
catch-all route `GET /{path:path}` is registered **last** so it cannot shadow a
real route.

---

## 5. Capture pipeline

**Files:** [app/services/document_processor.py](../../app/services/document_processor.py) ·
[app/services/file_watcher.py](../../app/services/file_watcher.py)

### 5.1 `FileWatcher`

- `watchdog` `Observer` on `data/staging`, **non-recursive**.
- `FileWatcherHandler.on_created` and `on_moved` trigger processing.
- `start()` also runs `_process_existing_files()` — a recovery scan for anything
  that arrived while the process was down. This is why `main.py` starts it with
  `asyncio.to_thread`: the scan can be CPU-heavy and must stay off the loop.
- Each file gets its **own** `SessionLocal()`.

### 5.2 `DocumentProcessor.process_file` — the eight steps

| Step | Action | On failure |
|---|---|---|
| 0 | File still exists? | Return `None` |
| 1 | `_validate_file` — extension allow-list, size limit | Return `None` |
| 2 | SHA-256 → duplicate/orphan/retry decision (see FR-2.4) | — |
| 3 | `get_file_info`, `_get_mime_type` (libmagic → extension map → `mimetypes`) | Falls back |
| 4 | Create the `Document` row with `file_path=""` | Raise |
| 5 | **OCR** — `ocr_status = processing → completed/failed` | `ocr_status = failed`, continue |
| 6 | **AI classification** → `_apply_extracted_metadata` | `ai_status = failed`, continue. No AI service → `skipped` |
| 7 | **Move to storage** — done *after* classification, because the folder path needs the correspondent and the document date | Raise |
| 8 | **Embeddings** → ChromaDB, `vector_status` | `vector_status = failed`, continue |

> **Why step 7 is where it is.** The storage path is
> `{correspondent}/{document_date}/`. Both come from the classifier. Moving the
> file first would file every document under `unknown_correspondent`.

### 5.3 `reprocess_existing`

Same stages, but only for statuses in `("pending", "failed")`, with no duplicate
check. OCR failure short-circuits — AI and vectorisation have nothing to work on.

### 5.4 `cleanup_orphaned_documents`

Walks every document; where `file_path` no longer exists, removes the vectors,
the processing logs, the tag links, and the row.

---

## 6. OCR subsystem

**Files:** [app/services/ocr_service.py](../../app/services/ocr_service.py) ·
[app/services/vision_ocr.py](../../app/services/vision_ocr.py)

### 6.1 Engine chain

| `ocr_engine` | PDF | Image |
|---|---|---|
| `auto` | text layer → vision → tesseract | vision → tesseract |
| `vision` | vision → tesseract (hard failure only) | same |
| `tesseract` | tesseract only | tesseract only |

Text/Markdown files are read directly, never OCR'd.

### 6.2 The text-layer threshold

`MIN_TEXT_LAYER_CHARS = 100` non-whitespace characters. Below that the PDF is
treated as a scan. This single constant is what stops a scanned PDF with a
stray "Page 1 of 4" text layer being accepted as machine-readable.

### 6.3 Binary discovery, cached

`_resolve_tesseract` probes, in order: the configured path (unless it is the
Linux default), Homebrew, `/usr/local`, `/usr/bin`, both Windows Program Files
locations, then bare `tesseract` on `PATH`. Each candidate is validated by
running `--version` with a 5-second timeout. **The answer is cached
process-wide under a lock**, because constructing an `OCRService` per request
must stay cheap. `reset_tesseract_cache()` / `reset_poppler_cache()` force
re-detection after a settings change.

### 6.4 Vision OCR

Renders PDF pages to images via `pdf2image` (Poppler), caps at
`vision_max_pages` (20) and `vision_max_image_bytes` (4 MB), and sends them as
OpenAI-style vision content blocks.

> ⚠️ `ai_max_tokens_vision` is **2048**, deliberately low. Groq counts
> `prompt + max_tokens` against the per-minute token limit, and the vision
> model's free-tier TPM is 8 000 — 8192 made every vision request fail with
> HTTP 413.

---

## 7. AI subsystem

**Files:** [app/services/ai_service.py](../../app/services/ai_service.py) ·
[ai_client_factory.py](../../app/services/ai_client_factory.py) ·
[sdk_compat.py](../../app/services/sdk_compat.py) ·
[model_config.py](../../app/services/model_config.py)

### 7.1 `AIClientFactory`

- `groq_keys(db)` → the ordered key list with blanks **and duplicates** removed.
  Two identical keys are one quota; collapsing them means the code never
  pretends to have headroom it does not have.
- `create_client(db, key_index=0)` builds an `OpenAI` (Groq uses a custom
  `base_url`) or `AzureOpenAI` client, with an `httpx` client carrying explicit
  timeouts (connect 10 s, read = `ai_request_timeout`, write 30 s for base64
  image uploads) and connection limits.
- `get_capabilities(settings)` returns the provider's declared capabilities from
  `config/models.json` — `token_param`, `supports_json_schema`,
  `supports_temperature`, `supports_reasoning_effort`.

### 7.2 Capability negotiation — the retry ladder

`_execute(params)` (`ai_service.py:196`) runs one completion and, on an HTTP 400
that names a parameter, **remembers** that `(provider, model)` rejects it,
removes it, and retries — up to `len(_OPTIONAL_PARAMS)+1` times. The memory is
process-wide (`_unsupported_params`, guarded by a lock), so the second request
to the same model never sends the bad parameter again.

Negotiable parameters: `reasoning_effort`, `response_format`, `temperature`,
`max_completion_tokens`, `max_tokens`.

When `response_format` is dropped the service logs that it is *"falling back to
prompt-guided JSON (no structured outputs)"* and relies on `_extract_json` to
recover the object from the text.

### 7.3 Retry, timeout and key failover

`_make_ai_request_with_retry` (`ai_service.py:221`):

```
enforce ≥100 ms between requests
for attempt in 0..max_retries:
    submit to the SHARED ThreadPoolExecutor(8)
    wait ai_request_timeout (60 s)
      timeout      → retry
      fatal (401/403) → break immediately, retrying will never help
      quota (429 / "rate limit" / "quota" / "tokens per day")
            → _switch_key(); if it worked, retry NOW with no backoff
            → else if it is a DAILY cap, break and log exactly what to do
      other        → backoff min(2**attempt, 8) s
```

> **Why the daily-cap distinction matters.** A per-minute limit clears on its
> own and is worth waiting out. A per-day cap will not clear before tomorrow, so
> backing off 1 s, 2 s, 4 s only makes every upload take eight seconds longer to
> fail.

`_switch_key` also rebuilds `self.embeddings`' client — otherwise embeddings
would carry on hammering the exhausted key.

### 7.4 Reasoning-token headroom

`MIN_REASONING_COMPLETION_TOKENS = 512`. Reasoning models spend part of the
completion budget on hidden reasoning tokens before emitting visible content
(~9 tokens at `low`, ~38 at `medium` for a trivial prompt on
`openai/gpt-oss-120b`). A budget below this floor returns an empty message with
`finish_reason='length'`, so the floor is enforced in `_build_completion_params`.
`_is_starved_by_reasoning(response)` detects it happening anyway.

### 7.5 `extract_document_metadata`

Prompts with the **existing** doctypes and correspondents from the database, so
the model reuses vocabulary rather than inventing a near-duplicate. Returns an
`AIExtractedData`. `_validate_and_fix_title` guards against a title that is
merely the filename or is empty.

### 7.6 `answer_question` (RAG)

Given the question, the context documents, their titles and their ids, it
instructs the model to cite as `[Doc1]`, `[Doc2]` **numbered by position in what
it was given**. `_log_rag_prompt` records the prompt for debugging.

### 7.7 `sdk_compat`

`adapt_params(client, params)` reshapes arguments for the installed OpenAI SDK
version; `strip_reasoning_blocks(text)` removes reasoning scaffolding some models
emit around the answer.

---

## 8. Embeddings and vector store

**Files:** [embedding_service.py](../../app/services/embedding_service.py) ·
[vector_db_service.py](../../app/services/vector_db_service.py)

### 8.1 `EmbeddingService`

Three providers: `local` (default), `openai`, `azure`.

- **local** — `_LocalEmbedder`, a process-wide singleton wrapping an ONNX
  `all-MiniLM-L6-v2` (384 dimensions, CPU). Loaded lazily on first use and
  cached under `HF_HOME` inside the data volume so it downloads once.
- **hosted** — reuses the chat client only when the embedding provider equals
  the chat provider; otherwise builds a dedicated `OpenAI` / `AzureOpenAI`
  client. The error message when a key is missing names the escape hatch:
  *set `embeddings.provider` to `local`*.

Inputs are trimmed to 8 000 characters. Hosted responses are re-sorted by
`index` to preserve request order explicitly.

> **Why local is the default.** Groq — the default chat provider — has **no**
> embeddings endpoint. Defaulting to OpenAI embeddings would make semantic
> search require a second vendor and a second key.

### 8.2 `VectorDBService`

A **singleton** (`__new__` returns the same instance). Persistent client at
`data/chroma`, or an HTTP client when `chroma_host`/`chroma_port` differ from
the defaults. If neither can be opened it falls back to an **in-memory**
collection — degraded but alive.

- `add_document` uses `upsert`, so re-indexing is idempotent.
- `search_similar` converts cosine distance to a score:
  `score = max(0, 1 − distance/2)`.
- Dimension mismatches are detected (`_is_dimension_error`) and re-raised as a
  `RuntimeError` whose message names the fix.

---

## 9. Search and RAG

**File:** [app/services/search_service.py](../../app/services/search_service.py)

### 9.1 `search_documents` decision tree

```
apply filters to the base query
if no text query   → newest first, paginate, return
semantic_search(query, filters, max(limit, 20))
if results         → fetch those documents, order by semantic rank, paginate
else               → _full_text_search (SQL ILIKE over title/summary/full_text/filename,
                      with up to 20 fuzzy variants OR-ed together)
```

A search **always** returns a `SearchResult`; there is no error path that shows
the user nothing.

### 9.2 `_semantic_search` strategies

1. **Composite** — enhanced query plus the top 5 tolerant variants, embedded
   once, queried against ChromaDB with `limit=100` and **no** metadata filters
   (filters are applied afterwards in SQL, to maximise recall).
2. **Original query only** — if the composite returned nothing.

A `max_search_time` of 45 s gates whether later strategies are attempted at all
(60 % and 80 % thresholds).

### 9.3 Tolerant matching

- `_normalize_text_for_search` — lowercase, NFD normalise, fold accents to ASCII
  so a query typed on an English keyboard matches text scanned from any document.
- `FuzzyMatcher.generate_typo_variants` — for words longer than three
  characters, capped at 5 variants per word and 20 in total, "to prevent query
  explosion".

### 9.4 Circuit breaker

3 consecutive AI failures → open for 300 s. While open, `_semantic_search`
returns `[]` immediately (so search silently degrades to full-text) and
`rag_query` returns a message saying how many seconds remain.

### 9.5 `rag_query` — the citation invariant

The critical loop (`search_service.py:751`):

```python
for doc in search_result.documents:
    context_text = doc.full_text or doc.summary or ""
    if context_text:                 # ← documents with NO text are skipped
        context_documents.append(context_text)
        document_titles.append(...)
        document_ids.append(...)
        used_documents.append(doc)   # ← kept in lockstep
...
return RAGResponse(answer=answer, sources=used_documents, confidence=...)
```

`sources` is `used_documents`, **not** `search_result.documents`. Returning
every match would break `[DocN] → sources[N-1]` the moment one document had no
text: every citation after it would point at the wrong file.

---

## 10. Approval engine

**File:** [app/services/workflow_service.py](../../app/services/workflow_service.py)
— **the single source of truth for approval state.**

### 10.1 Vocabulary

```python
DRAFT, ACTIVE, APPROVED, REJECTED, CHANGES, CANCELLED, PUBLISHED
PENDING, CURRENT
ANY_OF, ALL_OF = "any", "all"
TERMINAL = {APPROVED, REJECTED, CANCELLED, PUBLISHED}
PRIORITIES = ["low", "normal", "high", "urgent"]
SLA_CHOICES = {"4 hours": 4, "8 hours": 8, "1 day": 24, "2 days": 48,
               "3 days": 72, "5 days": 120, "10 days": 240}
```

Naming them once means a typo cannot invent a new status.

### 10.2 `create_workflow`

1. Reject an empty step list.
2. Normalise an unknown priority to `normal`.
3. **Cancel any existing live workflow** for the document.
4. Build steps via `_build_step`, then commit, then `start_workflow` unless
   `start=False`.

### 10.3 `_build_step`

- Normalises `approval_mode`; anything unrecognised becomes `any`.
- Resolves `assignee_ids` to **active** users only.
- `_reject_unsignable` raises if the step requires a signature and any assignee
  lacks `can_sign` (admins excepted) — **at design time**.
- Degrades `all` → `any` when fewer than two individuals are named.

### 10.4 `can_act(user, step)` → `(bool, reason)`

Ordered checks, first failure wins:

1. Step is not `current`.
2. `has_decided(step, user)` — **nobody answers twice, admins included.** On an
   `all` step a second approval from the same person would count towards the
   total and let one signatory close a step meant for three.
3. `user.is_admin` → allowed.
4. `can_approve` or the `documents.approve` permission.
5. If the step names people, the user must be among them; otherwise if the step
   names a department, it must match the user's.
6. If the step requires a signature, `can_sign`.

Returning a *reason* rather than a bare `False` is what lets the interface say
what is wrong instead of just disabling a button.

### 10.5 `decide` — the whole algorithm

```
workflow must be ACTIVE
can_act(user, step) or raise WorkflowError(reason)
action ∈ {approve, reject, changes}
reject  requires a reason
changes requires a comment

stamp step.decided_at / decided_by / comment / reason

APPROVE:
    if step.requires_signature:
        signature payload required, and user must be able to sign
    if signature supplied: _store_signature() → step.signature_id
    _record(StepDecision)          ← flushed, so outstanding() sees it
    still = outstanding(step)
    if still:
        event "approved · still waiting on X, Y"
        RETURN — the step stays CURRENT and the chain does not move
    step.status = APPROVED; event; _advance()

REJECT:
    _record; step + workflow = REJECTED; all undecided steps = skipped
    (decisive regardless of mode — waiting for two more people to agree with
     a "no" that has already stopped the document changes nothing)

CHANGES:
    _record; step = CHANGES; workflow = CHANGES; undecided steps back to PENDING
```

`_record` **flushes** before returning; without it the last approver of three
would still be reported as outstanding.

### 10.6 `_advance`

Next `PENDING` step with a higher `order_index` becomes `current` and gets its
due date. If there is none: workflow → `approved`, `completed_at` stamped, and
the **document** gets `is_approved`, `approved_at`, `approved_by`.

### 10.7 `resubmit`

Resets every step: status, `decided_*`, comment, reason, `signature_id`, and
`step.decisions.clear()`. Then `DRAFT` → `start_workflow`.

> Clearing `decisions` is the part that is easy to miss. An approver who signed
> version 1 has not seen version 2; leaving their row would count them towards
> the new round and let a step close without them ever looking at it.

### 10.8 `tasks_for(user)`

Queries every `CURRENT` step on an `ACTIVE` workflow, then filters in Python:
skip anything the user has already decided; admins see all; otherwise require
approve authority and either membership in `assignees`, or a department match,
or a step addressed to nobody in particular. Sorted by due date, `datetime.max`
for unset.

⚠️ This filters in Python rather than SQL. Fine at hundreds of live steps;
revisit at tens of thousands.

---

## 11. Signature subsystem

**Files:** [signature_stamp.py](../../app/services/signature_stamp.py) ·
[app/routers/signatures.py](../../app/routers/signatures.py)

### 11.1 The `Block`

```python
@dataclass
class Block:
    signature_id, name, designation, data_url, signed_at, step_name, order
    page_number, x_pct, y_pct, width_pct     # None = automatic layout
    resolved: dict                           # always concrete after resolve()
```

Geometry constants (points): block width 158, image height 30, total height
≈ 61, side margin 46, band bottom 88, 3 columns, gaps 18 × 12, max 2 automatic
rows, footer zone 80.

### 11.2 `content_bottom` and the footer zone

To decide whether the last page has room, the renderer must know where the body
actually ends. Anything wholly inside the bottom **80 points** is treated as page
furniture — a running footer, an address line, a page number — not content.
Counting it would make every letterheaded page look full to the bottom edge, and
no document would ever qualify for signatures on its last page.

### 11.3 `resolve(blocks, geometry, …)`

Converts fractional placement to absolute points against each page's real
mediabox; unplaced blocks are laid out in the automatic band; beyond
`MAX_AUTO_ROWS` they are moved to a dedicated signature page with its own
header.

### 11.4 `stamp(pdf_bytes, blocks, title)`

1. Read geometry with `PyPDF2`.
2. `resolve` the blocks.
3. For each affected page, draw an overlay canvas with ReportLab
   (`_overlay` → `_draw_block`: image, rule, name, designation, signed-at meta,
   with `_fit` truncating text to the block width).
4. `merge_page` the overlay onto the original page.
5. Return **new bytes** — never an in-place edit.

Works on any PDF, including a scan that was never composed in the Studio.

### 11.5 `render_page_png`

`pypdfium2` renders one page at a scale (default 1.6) so the placement editor
shows the real page behind the draggable blocks.

---

## 12. Versioning

**File:** [app/services/version_service.py](../../app/services/version_service.py)

| Function | Behaviour |
|---|---|
| `next_version("1.3")` | `"1.4"`; `major=True` → `"2.0"`; unparseable → `"1.1"` |
| `capture(...)` | Idempotent per `(document, version)` — the same label twice returns the existing row. Copies the file into `…/versions/`, clears `is_current` on all rows, inserts the new one. |
| `history` | Newest first |
| `lock_current` | Sets `is_locked` on the current row, or captures a locked one if none exists |
| `restore` | Copies the snapshot over the live file, bumps the version, recomputes the hash, then **captures a new version** — forward-only |

---

## 13. Document Studio

**Files:** [app/routers/studio.py](../../app/routers/studio.py) ·
[doc_templates.py](../../app/services/doc_templates.py) ·
[media_service.py](../../app/services/media_service.py) ·
[authoring_ai.py](../../app/services/authoring_ai.py)

### 13.1 Templates

Six templates (`blank`, `harman-letterhead`, `maruti-suzuki`, `mahindra`,
`tata`, `harman-quality`). A template spec describes **the paper, never the
words**: page size and margins in millimetres, header kind, side rail,
watermark, footer, accent and ink colours, and a `starter` body offered on a
blank page.

`_logo(key)` resolves a mark for both renderers: SVG for the web where one
exists (crisp at any zoom), PNG for ReportLab (which cannot read SVG at all).
Checking the file rather than hard-coding the extension means dropping in new
artwork needs no code change.

### 13.2 Media assets

`store_upload` validates and writes to `data/assets`. `resolver(db, user)`
returns a closure the PDF renderer uses to turn an asset **id** into a file
path. Bodies never carry paths.

### 13.3 `authoring_ai`

11 actions: `summarize`, `regenerate`, `grammar`, `formal`, `concise`, `expand`,
`bullets`, `continue`, `translate`, `draft`, `custom`. Each declares `replaces`
(does the result replace the selection?), and the action list drives the UI menu
so it can never drift from the API.

Two guardrails matter:

- **`_FORMAT_RULE`** restricts the model to `<h2> <h3> <p> <ul> <ol> <li>
  <strong> <em> <br>` and forbids preamble, explanation and closing remarks —
  otherwise the editor pastes the model's manners into the letter.
- **`_NO_NEW_STRUCTURE`** is added to correction-shaped actions
  (`keep_structure: true`). A proofread that silently grows a heading is not a
  proofread, and the author has to notice and undo it.

Output is run through the **same sanitiser the PDF renderer uses**, so a
prompt-injected `<script>` in a source document cannot come back as markup the
browser would run. Input is capped at 24 000 characters.

### 13.4 Publish

See [doc 04 §3.2](04-high-level-design.md#32-authoring--a-document-is-written).
The two design points: it reuses the *same* storage tree and `Document` shape as
the watcher (a composed document is a first-class document from the moment it is
saved), and enrichment runs in a `BackgroundTask` filling in **only blanks**.

---

## 14. Rendering: PDF and DOCX

### 14.1 `pdf_render.py`

- `sanitize_html(html)` — `bleach` with an allow-list, plus `tinycss2` for
  inline CSS. Filtering style rather than discarding the `style` attribute is
  how alignment and colour survive from the editor into the PDF.
- `_HTMLToFlowables` (an `HTMLParser` subclass) converts the body into ReportLab
  flowables: headings, paragraphs, lists, tables, images, signature blocks —
  translating CSS points, legacy `<font size>`, and alignment.
- `_load_image(src)` resolves an asset **id** through the resolver; nothing else
  is loadable.
- `_paint_chrome(canvas, doc, spec, title)` paints the letterhead: header,
  side rail, watermark, footer, page numbers.
- `render_pdf(html, template_id, title, author, asset_resolver)` → `bytes`.
- `page_estimate(html)` → a cheap page count for the UI.
- `RenderError` is raised for anything unrenderable; routers map it to 400.

### 14.2 `docx_render.py`

Builds a `.docx` with the **standard library's `zipfile`** — no `python-docx`
dependency. `render_docx(html, title, author, subtitle)` and
`html_to_plain(html, title)`. The letterhead is deliberately not carried over,
and the UI says so.

---

## 15. Publishing and export

**File:** [app/routers/publishing.py](../../app/routers/publishing.py)

### 15.1 `publish`

```
wf.publish(db, workflow, user)        # refuses unless status == approved
version_service.lock_current(...)     # ← the version the approvers saw
_apply_signatures(...)                # ← what actually goes out
audit "document.publish"
```

`_apply_signatures` returns **0** — a normal outcome, not a failure — when there
are no signatures, the file is missing, or it is not a PDF. On `StampError` it
logs and returns 0: publishing is the point of the exercise and a stamping
failure must not undo it.

On success it writes `{stem}_signed.pdf`, sets `0600`, repoints the document,
recomputes the hash, bumps the version and captures it **locked**.

### 15.2 `export_document`

An existing PDF on disk is served **as-is** — the bytes that were approved are
the bytes that go out. Only DOCX and TXT are generated, and only when there is a
body or extracted text to generate from. A scan with no body falls back to the
original file rather than inventing a PDF that is not the document.

---

## 16. Audit

**Files:** [audit_service.py](../../app/services/audit_service.py) ·
[app/routers/audit.py](../../app/routers/audit.py)

`log_audit_event(db, user_id, action, resource_type, resource_id, details)`
serialises `details` to JSON. Callers wrap it in `try/except` — **auditing must
never block the save** (`app/routers/studio.py:740`).

The router maps each action to `(label, icon, tone)` via the `ACTIONS` table.
An unknown action falls back to its raw name, dressed only by replacing `_` and
`.` — never dressed up as something it is not.

---

## 17. Backup

**Files:** [app/utils/backup.py](../../app/utils/backup.py) ·
[backup_scheduler.py](../../app/services/backup_scheduler.py) ·
[app/routers/backup.py](../../app/routers/backup.py)

Backup types: `database`, `storage`, `config`, `full`. Restore validates the
filename against path traversal — see `tests/test_backup_security.py`. The
scheduler is built on `schedule` and is **configured disabled at startup**.

---

## 18. File security

**File:** [app/utils/file_security.py](../../app/utils/file_security.py)

| Function | Purpose |
|---|---|
| `validate_file_upload(filename, content, user, max_size)` | Extension allow-list, size, magic-byte/content check, filename sanitisation → `(safe_filename, mime_type)` |
| `secure_file_path(base, filename)` | Resolves and asserts the result stays under `base` — path-traversal defence |
| `set_secure_permissions(path, is_private=True)` | `0600` for documents. Uploaded documents frequently contain invoices, contracts and tax data; owner-only is the correct default, not `0644`. |
| `calculate_file_hash(path)` | SHA-256 |

Exceptions: `FileTypeNotAllowedError`, `FileSecurityError` → HTTP 400.

---

## 19. CLI

**File:** [cli.py](../../cli.py)

| Command | Does |
|---|---|
| `init` | Initialise the database and folder structure |
| `serve` | Start uvicorn |
| `process` | Process everything sitting in staging |
| `status` | System status report |
| `setup-root` | Set up the root folder |
| `users` | List accounts with their authority |
| `reset-password <username> [--password]` | Reset a password |
| `sync-model-config` | Push `config/models.json` into the DB settings table, so it beats stale rows |
| `check-ai` | Verify the AI provider actually answers |
| `reindex-vectors [--force]` | Rebuild the vector store; `--force` after an embedding-model change |
| `db create-indexes \| analyze \| optimize \| size` | Database maintenance |
| `backup create \| restore \| list` | Backup management |

---

## 20. Extension recipes

### 20.1 Add an API endpoint

1. Add the handler to the right router with
   `Depends(require_permission_flexible("…"))`.
2. Put any rule in a **service**, not in the router.
3. Add request/response models to `app/schemas.py`.
4. If it is state-changing and called from the browser, ensure the front end
   sends `X-CSRF-Token` (the `api()` helper in `shell.js` does this).
5. Document it in [doc 07](07-api-reference.md).

### 20.2 Add a database column

1. Add it to the model in `app/models.py`.
2. Add it to `ADDITIONS` in `app/utils/schema_migrations.py` with a default that
   **preserves existing behaviour**.
3. Add it to the Pydantic schema if it should be exposed.
4. Never drop, rename or retype.

### 20.3 Add an approval rule

Change `workflow_service.py` and nothing else. If you find yourself adding a
state check in a router, the rule is in the wrong place.

### 20.4 Add a letterhead template

Append a spec to `TEMPLATES` in `doc_templates.py`. Both renderers pick it up.
Drop the artwork into `frontend/ui/assets/brand/` as `{key}.svg` and
`{key}.png`.

### 20.5 Add an AI authoring action

Add an entry to `ACTIONS` in `authoring_ai.py`. The Studio menu is generated
from `available_actions()`, so it cannot drift.

### 20.6 Add an AI provider

1. Add a block to `providers` in `config/models.json` declaring `base_url`,
   `api_key_env`, `token_param` and the three `supports_*` flags.
2. Add the branch to `AIClientFactory.create_client`.
3. Add the key field to `Settings`.
4. If the SDK shape differs, extend `sdk_compat.adapt_params`.

### 20.7 Add a front-end screen

1. Create `frontend/ui/<name>.html`.
2. Register it in `UI_PAGES` in `app/main.py`; add it to `ADMIN_ONLY_PAGES` if
   it is administrative.
3. Add a nav entry in `shell.js` (`NAV_ADMIN` / `NAV_MEMBER`).
4. Use `DMS.api()`, `DMS.toast()`, `DMS.mount()` from the shell.
