# HARMAN DMS — Technology Stack

| | |
|---|---|
| **Document** | Technology Stack Reference |
| **Version** | 1.0 |
| **Application version covered** | 1.1.0 (`app/main.py`) |
| **Verified against source** | 2026-08-07 |
| **Sources of truth** | [requirements.txt](../requirements.txt) · [Dockerfile](../Dockerfile) · [config/models.json](../config/models.json) |

> **Scope.** Every technology this system actually uses, with the version pinned
> in the repository and the reason it was chosen where the choice was not
> obvious. Section 11 lists dependencies that are declared but **not imported by
> application code** — read it before assuming a library is in play.
>
> For architecture, see
> **[DMS-Project-Documentation.md](DMS-Project-Documentation.md)** Part 4.

---

## Contents

1. [At a glance](#1-at-a-glance)
2. [Runtime & platform](#2-runtime--platform)
3. [Backend framework & data](#3-backend-framework--data)
4. [AI / ML](#4-ai--ml)
5. [OCR & document processing](#5-ocr--document-processing)
6. [Document rendering](#6-document-rendering)
7. [Security](#7-security)
8. [Frontend](#8-frontend)
9. [Testing, CI & tooling](#9-testing-ci--tooling)
10. [External services & system binaries](#10-external-services--system-binaries)
11. [Declared but unused dependencies](#11-declared-but-unused-dependencies)
12. [Why these choices](#12-why-these-choices)
13. [Complete dependency inventory](#13-complete-dependency-inventory)

---

## 1. At a glance

| Layer | Choice |
|---|---|
| **Language** | Python 3.12 |
| **Backend** | FastAPI · SQLAlchemy · Pydantic |
| **Database** | SQLite (default) → PostgreSQL (enterprise) |
| **Vector store** | ChromaDB, cosine, 384 dimensions |
| **AI** | Groq (default) / OpenAI / Azure OpenAI, all via the OpenAI SDK |
| **Embeddings** | `all-MiniLM-L6-v2` — local ONNX, CPU, no API key |
| **OCR** | Vision model → Tesseract fallback |
| **Rendering** | ReportLab (PDF) · stdlib `zipfile` (DOCX) |
| **Frontend** | Vanilla JavaScript — no framework, no bundler, no build step, no CDN |
| **Deployment** | Docker / Podman, multi-stage, non-root |
| **CI** | GitHub Actions |

**Three defining constraints** that explain most of the list below:

1. **No system libraries for document rendering.** Everything ships as a
   self-contained Python wheel, so the application installs identically on
   Linux, Windows and macOS.
2. **No build step on the front end.** What you read in the repository is what
   the browser runs.
3. **The AI provider is swappable and optional.** The product runs with no API
   key at all, with AI features off.

---

## 2. Runtime & platform

| Component | Version | Notes |
|---|---|---|
| **Python** | 3.12 | Enforced by the Docker image and CI |
| **Uvicorn** | 0.24.0 (`uvicorn[standard]`) | ASGI server; default bind `127.0.0.1:8000` |
| **Docker base** | `python:3.12-slim` | Multi-stage: the compiler toolchain never reaches the runtime image |
| **Container user** | uid/gid 1000, non-root | |
| **Host OS** | Linux · Windows 10/11 · macOS | All three exercised — OS-specific fallbacks exist for `libmagic`, Tesseract and Poppler discovery |

---

## 3. Backend framework & data

| Component | Version | Role |
|---|---|---|
| **FastAPI** | 0.136.1 | HTTP framework — 16 routers, 167 route declarations |
| **SQLAlchemy** | 2.0.23 | ORM — 22 tables (18 entity + 4 association) |
| **Pydantic** | 2.12.5 | Request/response validation |
| **pydantic-settings** | 2.12.0 | Four-layer configuration precedence |
| **ChromaDB** | 0.4.22 | Vector store — embedded persistent client, or remote HTTP |
| **loguru** | 0.7.2 | Structured application and security logging |
| **schedule** | 1.2.1 | Backup scheduler (disabled by default) |
| **psutil** | 5.9.8 | CPU/memory/disk metrics for the health endpoints |
| **python-multipart** | 0.0.28 | File upload parsing |

### Database

| Environment | Engine |
|---|---|
| Development / single-node | **SQLite** — `sqlite:///./data/documents.db` |
| Enterprise | **PostgreSQL** — set `DATABASE_URL` |

⚠️ SQLite **serialises writes**, and SQLite does not enforce foreign keys unless
`PRAGMA foreign_keys=ON` (which this application does not set). Referential
integrity relies on application code.

⚠️ There is **no Alembic migration chain** — see §11.

---

## 4. AI / ML

### Providers

| Provider | Status | Reached via |
|---|---|---|
| **Groq** | Default | `openai` SDK with a custom `base_url` |
| **OpenAI** | Supported | `openai` SDK |
| **Azure OpenAI** | Supported | `AzureOpenAI` client |

One SDK for all three — Groq and Azure are OpenAI-compatible. Differences are
absorbed by `services/sdk_compat.py` and runtime capability negotiation.

| Component | Version |
|---|---|
| **openai** | 1.59.6 — 1.3.7 predates the `base_url` kwarg and vision content blocks |
| **onnxruntime** | ≥ 1.16.0 |
| **tokenizers** | ≥ 0.15.0 |

### Models — defaults from [config/models.json](../config/models.json)

| Role | Model | Where it runs |
|---|---|---|
| Chat + reasoning | `openai/gpt-oss-120b` | Groq |
| Analysis / classification | `openai/gpt-oss-120b` | Groq |
| Vision / OCR | `qwen/qwen3.6-27b` | Groq |
| Embeddings | `all-MiniLM-L6-v2` | **Local, CPU, ONNX, 384 dimensions** |

### Generation defaults

| Setting | Value | Why |
|---|---|---|
| `reasoning_effort` | `medium` | |
| `temperature_extraction` | 0.1 | Classification should be deterministic |
| `temperature_chat` | 0.3 | |
| `max_tokens_extraction` / `_chat` | 4096 | |
| `max_tokens_vision` | **2048** | ⚠️ **Do not raise.** Groq counts `prompt + max_tokens` against the per-minute token limit, and the vision model's free-tier TPM is 8 000. Setting 8192 made every vision request fail with HTTP 413. |
| Reasoning-token floor | 512 | Reasoning tokens are billed against the completion budget; a smaller budget returns an empty message |

Model names are read from `config/models.json`, which is **mounted into the
container** — models can be changed without a rebuild.

---

## 5. OCR & document processing

| Component | Version | Role |
|---|---|---|
| **pytesseract** | 0.3.10 | Python binding for the Tesseract binary |
| **pdf2image** | 1.17.0 | Renders PDF pages to images (needs Poppler) |
| **PyPDF2** | 3.0.1 | Page geometry, text-layer extraction, overlay merge |
| **pypdfium2** | 5.12.1 | Renders a PDF page to PNG for the signature placement editor |
| **Pillow** | 12.2.0 | Image manipulation and thumbnails |
| **python-magic** | 0.4.27 | MIME detection — optional, needs native `libmagic` |
| **watchdog** | 4.0.0 | Observes the staging folder for incoming files |

### The OCR engine chain

| `ocr_engine` | PDFs | Images |
|---|---|---|
| `auto` (default) | embedded text layer → vision model → Tesseract | vision model → Tesseract |
| `vision` | vision model, Tesseract only as a last resort | same |
| `tesseract` | Tesseract only; the vision model is never called | same |

A PDF text layer is accepted above **100 non-whitespace characters** — the
threshold that stops a scanned PDF with a stray "Page 1 of 4" text layer being
treated as machine-readable.

---

## 6. Document rendering

| Component | Version | Role |
|---|---|---|
| **ReportLab** | 4.2.5 | HTML → letterheaded PDF, and signature stamping |
| **stdlib `zipfile`** | — | DOCX generation — **no `python-docx` dependency** |
| **bleach** | 6.1.0 | HTML sanitising |
| **tinycss2** | 1.5.1 | Inline-CSS filtering inside bleach |

`tinycss2` lets bleach **filter** inline CSS rather than discard the `style`
attribute outright — which is how alignment and colour survive from the editor
into the PDF.

Six letterhead templates are defined once in `services/doc_templates.py` and
read by **both** renderers — the browser canvas and ReportLab. That is what
makes preview the output rather than an impression of it.

---

## 7. Security

| Component | Version | Role |
|---|---|---|
| **bcrypt** | 4.1.2 | Password hashing |
| **passlib[bcrypt]** | 1.7.4 | Hashing context |
| **python-jose[cryptography]** | 3.5.0 | JWT, HS256, 30-minute lifetime |

**Built in-house rather than taken from a library:**

| Control | Implementation |
|---|---|
| Sessions | Server-side `sessions` rows + HttpOnly cookie, 24 h |
| CSRF | Signed double-submit cookie, HMAC-SHA256 (`middleware/csrf_middleware.py`) |
| Rate limiting | Sliding window per IP per endpoint (`middleware/rate_limit_middleware.py`) |
| File safety | Path-traversal guards, magic-byte validation, `0600` permissions (`utils/file_security.py`) |

⚠️ Rate-limit counters are **per-process, in memory** — a prerequisite to fix
before running multiple workers.

---

## 8. Frontend

**Vanilla JavaScript. No framework, no bundler, no build step, no CDN, no
`package.json`, no `node_modules`.**

| Asset | Size | Role |
|---|---|---|
| `js/shell.js` | 2,780 lines | Navigation, API client, toasts, modals, signature pad, decision bar, date system, people picker, combobox |
| `js/studio.js` | 1,723 lines | The `contenteditable` WYSIWYG editor |
| `js/viewer.js` | 250 lines | Document rendering, shared by detail and full-screen views |
| `css/dms.css` | — | Design system: palette, type scale, components |
| `css/studio.css` | — | Editor: ribbon, paper, letterhead chrome |
| `*.html` | 16 files | One file per screen, served statically by FastAPI |

| Aspect | Detail |
|---|---|
| Icons | ~90 inline SVG paths in `shell.js` — no icon library |
| Global surface | One: `window.DMS` |
| Browser floor | Modern evergreen — uses `fetch`, `async/await`, template literals. No transpilation, therefore **no IE11**. |
| Charts / UI libraries | None |

---

## 9. Testing, CI & tooling

| Component | Version | Role |
|---|---|---|
| **pytest** | 9.0.3 | 160 tests across 12 files |
| **pytest-asyncio** | 1.3.0 | Async test support |
| **httpx** | 0.26.0 | Test client, and the HTTP transport under the OpenAI SDK |

### CI — [.github/workflows/ci.yml](../.github/workflows/ci.yml)

GitHub Actions, Ubuntu, Python 3.12, on push and PR to `main`:

1. Install `libmagic1`, `tesseract-ocr`, `poppler-utils`
2. `pip install -r requirements.txt`
3. Validate `config/models.json` parses
4. `python -m pytest tests -q`
5. Parse every `.ps1` / `.psm1` with the PowerShell parser

⚠️ No linting, type checking, coverage measurement or security scanning.

### Other tooling

| Item | Purpose |
|---|---|
| `cli.py` | `argparse`-based operational CLI — 13 command groups |
| `setup.sh` / `setup.ps1` | Scripted installation |
| `docker-entrypoint.sh` | Container initialisation |

---

## 10. External services & system binaries

| Dependency | Required? | Consequence if absent |
|---|---|---|
| **AI provider API** (Groq / OpenAI / Azure) | No | Classification, summaries, semantic search and the assistant are disabled; capture, storage, full-text search and the entire approval workflow still work |
| **Tesseract OCR** | No | Image OCR falls back to the vision model |
| **Poppler** (`pdftoppm`) | No | No PDF→image, so no vision OCR and no thumbnails |
| **libmagic** | No | MIME detection falls back to the file-extension map |
| **ChromaDB** | Bundled | Falls back to an in-memory collection |
| **Internet access** | Only for AI | Everything else is local |

The Docker image installs Tesseract (English), Poppler and `libmagic1` so none
of these fallbacks are needed in a container deployment.

---

## 11. Declared but unused dependencies

Five packages are pinned in [requirements.txt](../requirements.txt) but are
**not imported anywhere** in `app/`, `cli.py`, `scripts/` or `tests/`. Verified
by scanning every import statement in the source tree.

| Package | Version | Status |
|---|---|---|
| **alembic** | 1.13.1 | ⚠️ **The significant one.** There is no `alembic/` directory and no migration chain. Schema is managed by `Base.metadata.create_all` plus hand-written additive DDL in `app/utils/schema_migrations.py`. This blocks PostgreSQL at scale — tracked as **D-5** in the main specification. |
| **jinja2** | 3.1.6 | Unused — the UI is static HTML, not templated |
| **aiofiles** | 23.2.1 | Unused |
| **tabulate** | 0.9.0 | Unused |
| **numpy** | 1.26.4 | Not imported directly; pinned as a transitive dependency of ChromaDB / onnxruntime |

Removing the first four would shrink the image and reduce the dependency
surface. `numpy` should stay pinned.

---

## 12. Why these choices

| Choice | Reason |
|---|---|
| **Modular monolith, not microservices** | The five-step document journey is one transactional story. Splitting it buys distributed-transaction problems and no benefit at this scale. Every future service boundary (AI, vector store, storage) already sits behind an interface. |
| **SQLite by default** | Zero setup — the product runs from a folder. PostgreSQL is one environment variable away. |
| **Local ONNX embeddings** | **Groq has no embeddings endpoint.** Defaulting to OpenAI embeddings would make semantic search require a second vendor and a second API key. Local means 384 dimensions, CPU-bound, and nothing leaves the network for indexing. |
| **One SDK for three AI providers** | Groq and Azure are OpenAI-compatible. Differences are handled by capability negotiation at runtime rather than three code paths. |
| **ReportLab for PDF** | Pure-Python wheels. No wkhtmltopdf, no headless Chrome, no system libraries — so the same install works on every host. |
| **pypdfium2, not PyMuPDF** | PyMuPDF is **AGPL**. This is a commercial deployment. pypdfium2 is BSD/Apache and ships as a self-contained wheel. |
| **stdlib `zipfile` for DOCX** | A `.docx` is a zip of XML. A dedicated library would be one more dependency for something the standard library already does. |
| **Vanilla JS, no build step** | No bundler to install, no framework upgrade treadmill across a product with multi-year retention obligations, and no CDN — so it runs on an air-gapped network unchanged. The cost is manual DOM work; the benefit is that a new developer can open one HTML file and understand the whole screen. |
| **bcrypt over argon2** | Ubiquitous, well-understood, and `passlib` handles the upgrade path if that changes. |
| **Custom CSRF and rate limiting** | Both needed behaviour off-the-shelf middleware does not provide: CSRF tokens signed with the application secret so they survive restarts and multiple workers, and login limiting that counts **failures only** — charging successful sign-ins locks users out of their own account after five logins. |

---

## 13. Complete dependency inventory

Verbatim from [requirements.txt](../requirements.txt), grouped by role.

```
# Web framework and server
fastapi==0.136.1
uvicorn[standard]==0.24.0
python-multipart==0.0.28

# Data
sqlalchemy==2.0.23
alembic==1.13.1              # ⚠️ declared, no migration chain exists
chromadb==0.4.22
pydantic==2.12.5
pydantic-settings==2.12.0
numpy==1.26.4                # transitive pin

# AI / ML
openai==1.59.6               # Groq reached via custom base_url
onnxruntime>=1.16.0          # local MiniLM embeddings
tokenizers>=0.15.0

# OCR and document processing
pytesseract==0.3.10
pdf2image==1.17.0
PyPDF2==3.0.1
pypdfium2==5.12.1            # BSD/Apache — deliberately not AGPL PyMuPDF
Pillow==12.2.0
python-magic==0.4.27
watchdog==4.0.0

# Rendering and sanitising
reportlab==4.2.5             # pure Python wheels, no system libraries
bleach==6.1.0
tinycss2==1.5.1              # lets bleach filter inline CSS, not discard it

# Security
bcrypt==4.1.2
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.5.0

# Operations
loguru==0.7.2
psutil==5.9.8
schedule==1.2.1

# Testing
pytest==9.0.3
pytest-asyncio==1.3.0
httpx==0.26.0

# Declared, not imported by application code
jinja2==3.1.6
aiofiles==23.2.1
tabulate==0.9.0
```

---

## Related documents

| Document | Contents |
|---|---|
| [DMS-Project-Documentation.md](DMS-Project-Documentation.md) | The full specification — requirements, HLD, LLD, API, security, operations |
| ↳ Part 4 §5 | The fifteen architectural decisions, with consequences |
| ↳ Part 10 §3 | Configuration precedence and every environment variable |
| ↳ Part 11 §4 | The technical-debt register, including **D-5** (no migration chain) |
| [groq-setup.md](groq-setup.md) | AI provider, embedding and OCR configuration in depth |
| [../README.md](../README.md) | Repository overview — changes frequently |
