# 10 · Deployment & Operations

> **Audience:** operations, DevOps, anyone who has to make this run and keep it
> running. Everything here is executable.

---

## 1. Prerequisites

| Component | Version | Required? |
|---|---|---|
| Python | 3.12 | Yes |
| Tesseract OCR | any recent | Optional — needed for local OCR fallback |
| Poppler (`pdftoppm`) | any recent | Optional — needed for PDF→image (vision OCR, thumbnails) |
| `libmagic` | any | Optional — MIME detection falls back to file extension |
| AI provider key | — | Optional — the product runs without one, with AI features off |
| Docker / Podman | — | Only for container deployment |

**Installing the optional binaries**

```bash
# Debian / Ubuntu
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng poppler-utils libmagic1

# macOS
brew install tesseract poppler libmagic

# Windows
winget install tesseract-ocr        # or: choco install tesseract
winget install oschwartz10612.Poppler
```

On Windows, set `POPPLER_PATH` to the Poppler `Library\bin` directory — see the
example already present in [`.env`](../../.env).

---

## 2. Installation

### 2.1 Scripted

```bash
./setup.sh          # Linux / macOS
```
```powershell
.\setup.ps1         # Windows
```

### 2.2 Manual

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then edit it
python cli.py init               # create the database and folder tree
python cli.py serve              # http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000>. On a database with no users you are taken through
first-run administrator setup.

### 2.3 Docker

```bash
docker build -t harman-dms .

docker run -d --name dms -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/config:/app/config" \
  -e GROQ_API_KEY=gsk_… \
  -e ENVIRONMENT=production \
  -e SECRET_KEY="$(openssl rand -base64 32)" \
  -e CORS_ORIGINS=https://dms.example.com \
  -e TRUSTED_PROXY_IPS=10.0.0.5 \
  harman-dms
```

Mounting `config/` means **model names can be changed without a rebuild**.
Mounting `data/` keeps the database, documents, vectors, logs and the cached
ONNX embedding model across container restarts.

The image already: builds in two stages, runs as uid 1000, installs Tesseract
and Poppler, defines a `HEALTHCHECK` against `/api/health`, and caches the
embedding model under `/app/data/.cache` so it downloads once.

---

## 3. Configuration

### 3.1 Precedence — memorise this

```
code defaults  <  config/models.json  <  environment / .env  <  database settings table
```

> **The single most common support question** is "I changed the config and
> nothing happened". The answer is almost always that a value was saved through
> **Settings → AI Configuration** in the UI, which writes to the database and
> therefore beats `.env`. Either change it in the UI too, or run
> `python cli.py sync-model-config` to push `config/models.json` into the
> database so it wins.

### 3.2 Environment variables

Full list in [.env.example](../../.env.example).

**Security**
| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | random per process | **Set a stable value in production** — CSRF tokens are signed with it |
| `JWT_SECRET_KEY` | generated and persisted to the DB on first use | |
| `ENVIRONMENT` | `development` | `production` turns on `Secure` cookies |
| `PRODUCTION_MODE` | derived from `ENVIRONMENT` | Explicit override |
| `CORS_ORIGINS` | localhost set | Comma-separated; must be exact — CORS is credentialed |
| `TRUSTED_PROXY_IPS` | `127.0.0.1,::1` | Only these peers may set `X-Forwarded-For` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | |

**Storage**
| Variable | Default |
|---|---|
| `DATABASE_URL` | `sqlite:///./data/documents.db` |
| `DATA_FOLDER` / `STAGING_FOLDER` / `STORAGE_FOLDER` / `LOGS_FOLDER` / `BACKUP_FOLDER` | under `./data` |

**AI**
| Variable | Default | Notes |
|---|---|---|
| `AI_PROVIDER` | `groq` | `groq` \| `openai` \| `azure` |
| `GROQ_API_KEY` | — | Primary key |
| `GROQ_API_KEY_2` | — | **A key on a different account.** Automatic failover on quota. Identical to key 1 = no extra headroom, and the code collapses the duplicate. |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | |
| `OPENAI_API_KEY` / `AZURE_OPENAI_*` | — | |
| `EMBEDDING_PROVIDER` | `local` | `local` needs no key and sends nothing externally |
| `OCR_ENGINE` | `auto` | `auto` \| `vision` \| `tesseract` |
| `AI_REQUEST_TIMEOUT` | `60` | Seconds |
| `AI_MAX_RETRIES` | `2` | |
| `AI_TEXT_LIMIT` | `16000` | Characters sent for classification |

**Tooling**
| Variable | Default |
|---|---|
| `TESSERACT_PATH` | `/usr/bin/tesseract` |
| `POPPLER_PATH` | `/usr/bin` |
| `MAX_FILE_SIZE` | `100MB` |
| `ALLOWED_EXTENSIONS` | `pdf,png,jpg,jpeg,tiff,bmp,txt,text,md,markdown` |
| `CHROMA_HOST` / `CHROMA_PORT` / `CHROMA_COLLECTION_NAME` | `localhost` / `8001` / `documents` |
| `LOG_LEVEL` | `INFO` |

### 3.3 `config/models.json`

Model names and provider capabilities. Editing it and restarting is enough —
or run `python cli.py sync-model-config` to push the values into the database.

```jsonc
{
  "active_provider": "groq",
  "models": { "chat": "openai/gpt-oss-120b",
              "analysis": "openai/gpt-oss-120b",
              "vision": "qwen/qwen3.6-27b" },
  "embeddings": { "provider": "local", "local_model": "all-MiniLM-L6-v2" },
  "ocr": { "engine": "auto", "vision_enabled": true,
           "vision_max_pages": 20, "vision_max_image_bytes": 4194304 },
  "generation": { "reasoning_effort": "medium",
                  "max_tokens_extraction": 4096,
                  "max_tokens_chat": 4096,
                  "max_tokens_vision": 2048 }
}
```

> **Do not raise `max_tokens_vision`.** Groq counts `prompt + max_tokens`
> against the per-minute token limit, and the vision model's free-tier TPM is
> 8 000. Setting it to 8192 made every vision request fail with HTTP 413.

### 3.4 Adding the second Groq key

1. Create a key on a **different** Groq account: <https://console.groq.com/keys>
2. Put it on the `GROQ_API_KEY_2=` line in [`.env`](../../.env)
3. Restart

Two identical keys give one quota; `AIClientFactory.groq_keys` removes the
duplicate rather than pretending otherwise. Check nothing is stored in the
database that would override `.env`:

```bash
python -c "import sqlite3;c=sqlite3.connect('data/documents.db');\
print([r for r in c.execute(\"select key from settings where key like '%groq%'\")])"
```

---

## 4. CLI reference

```bash
python cli.py init                      # database + folder structure
python cli.py serve                     # start the web server
python cli.py status                    # system status report
python cli.py process                   # process everything in staging now
python cli.py setup-root                # set up the root folder

python cli.py users                     # list accounts and their authority
python cli.py reset-password <user> [--password X]

python cli.py check-ai                  # does the provider actually answer?
python cli.py sync-model-config         # push config/models.json into the DB

python cli.py reindex-vectors [--force] # rebuild the vector store

python cli.py db create-indexes         # performance indexes
python cli.py db analyze                # query-plan statistics
python cli.py db optimize               # VACUUM, ANALYZE, REINDEX
python cli.py db size                   # database size report

python cli.py backup create [--type full|database|storage|config]
python cli.py backup list
python cli.py backup restore <file>
```

---

## 5. Day-one operations

### 5.1 First run

1. `python cli.py init`
2. `python cli.py serve`
3. Open <http://127.0.0.1:8000> → create the first administrator
4. Sign in, go to **Settings** and confirm the AI provider answers
   (or `python cli.py check-ai`)
5. **People** → add the real users, setting `can_approve` / `can_sign`
   deliberately
6. **Approval Routes** → design the routes each department needs

### 5.2 Demo data

```bash
python scripts/seed_demo_data.py --reset
```

Creates six people, five documents and four approvals in four different states
(in progress, approved, changes requested, published). All demo accounts share
the password printed by the script.

⚠️ **Never run this against production**, and remove the demo accounts before
go-live.

### 5.3 Brand assets

```bash
python scripts/seed_brand_assets.py     # redraw the PNGs the PDF renderer embeds
python scripts/import_brand_logo.py     # import a supplied logo
```

---

## 6. Monitoring

### 6.1 Probes

| Endpoint | Use |
|---|---|
| `GET /api/health/liveness` | Is the process alive? Restart on failure. |
| `GET /api/health/readiness` | **Gate traffic with this.** Start-up defers database initialisation by ~2 s. |
| `GET /api/health/startup` | Start-up progress |
| `GET /api/health/` | Full report: DB, vectors, AI, OCR, disk, folders |
| `GET /api/health/metrics` | CPU, memory, disk, document counts (admin) |

### 6.2 Logs

| Path | Contents |
|---|---|
| `data/logs/server.log` | Application log (loguru) |
| `data/logs/` | Security and access logs |
| `processing_logs` table | Per-document pipeline events with durations |
| `audit_logs` table | Who did what, when, from where |

`GET /api/settings/logs/download` downloads them from the UI.

### 6.3 What to alert on

| Signal | Meaning |
|---|---|
| `readiness` failing > 60 s | Database or folder problem |
| `"Groq daily token allowance is exhausted"` | AI features are down until reset — add a second-account key |
| `"AI circuit breaker opened"` | 3 consecutive AI failures; search has degraded to full-text |
| `"Embedding dimension mismatch"` | Someone changed the embedding model — run `reindex-vectors --force` |
| Rising `ocr_status = failed` | Tesseract/Poppler missing, or the vision quota is gone |
| Rising `vector_status = failed` | ChromaDB problem |
| Disk > 85 % | Versions and thumbnails accumulate; there is no compaction |
| 429 rate | Either an attack or a limit set too low |

---

## 7. Backup and recovery

### 7.1 What must be backed up

| Item | Why |
|---|---|
| `data/documents.db` | Everything except the bytes |
| `data/storage/` | The document bytes **and all version history** |
| `data/assets/` | The Studio image library |
| `.env` / `config/models.json` | Configuration |
| `data/chroma/` | Optional — rebuildable with `reindex-vectors` |

### 7.2 Taking a backup

```bash
python cli.py backup create --type full
# or POST /api/backup/create, or enable the scheduler (disabled by default)
```

### 7.3 Restoring

```bash
python cli.py backup list
python cli.py backup restore <filename>
```

### 7.4 Recovery drills — run these before go-live

| Scenario | Procedure |
|---|---|
| Database lost, files intact | Restore the database backup. Any document created after the backup is orphaned on disk — re-drop those files into `data/staging` and let the watcher re-ingest them. |
| Vector store lost | `python cli.py reindex-vectors --force`. No data loss: vectors are derived. |
| A file lost, record intact | `POST /api/documents/cleanup/orphaned` removes the dangling record, or restore the file from a version copy under `…/versions/`. |
| Whole system lost | Restore `data/` and `.env`, `pip install -r requirements.txt`, `python cli.py serve`. |
| Embedding model changed by mistake | Change it back, or `reindex-vectors --force`. |

---

## 8. Routine maintenance

| Cadence | Task |
|---|---|
| Daily | Check `readiness`; check for AI quota warnings in the log |
| Weekly | Verify backups exist **and can be restored**; review the activity log |
| Monthly | `python cli.py db optimize`; check disk headroom; review user accounts and their sign authority |
| Quarterly | Rotate API keys; re-test a full restore; review the security checklist in [doc 09 §9](09-security-design.md) |
| As needed | `POST /api/documents/cleanup/orphaned`; `reindex-vectors` after an embedding change |

---

## 9. Troubleshooting runbook

| Symptom | Cause | Fix |
|---|---|---|
| **Configuration change has no effect** | A value in the `settings` table overrides `.env` | Change it in the UI, or `python cli.py sync-model-config` |
| **Every write returns 403 "CSRF token validation failed"** | Client sending the signed cookie value instead of the unsigned token | The shell's `api()` strips the signature; a custom client must too. `GET /api/csrf-token` returns the correct value. |
| **CSRF fails after every restart** | `SECRET_KEY` is random per process | Set a stable `SECRET_KEY` |
| **Locked out after five sign-in attempts** | Login rate limit | Wait 5 minutes. A *successful* sign-in clears the IP's failures. |
| **Uploads succeed but nothing appears** | The file watcher did not start | Check the log for `"Could not start file watcher"`; verify `data/staging` exists and is writable; `python cli.py process` to sweep manually |
| **`ai_status = failed` on everything** | No key, wrong key, or quota exhausted | `python cli.py check-ai`. If it is a **daily** cap, add a key from a second Groq account in `GROQ_API_KEY_2`. |
| **Semantic search returns nothing, full-text works** | AI circuit breaker open, or the vector store is empty | Wait 300 s; check `GET /api/search/vector-stats`; `reindex-vectors` |
| **"Embedding dimension mismatch"** | Embedding model changed | `python cli.py reindex-vectors --force` |
| **Every vision OCR request fails with 413** | `max_tokens_vision` too high | Set it back to 2048 |
| **`ocr_status = failed` on scans** | Tesseract or Poppler missing | Install them; set `TESSERACT_PATH` / `POPPLER_PATH`; the log prints the install command for your OS |
| **PDF preview blank or wrong** | Sanitiser stripped unsupported markup | The renderer supports a deliberate subset — see [doc 06 §14](06-low-level-design.md#14-rendering-pdf-and-docx) |
| **"Step X requires a signature, but N is not permitted to sign"** | Working as designed | Grant `can_sign`, choose someone else, or turn the signature requirement off |
| **An approver cannot see a task** | They already decided it, it is not the current step, or it is addressed elsewhere | `GET /api/workflow/{id}` and read `blocked_reason` on the step |
| **A document will not publish** | Its workflow is not `approved` | Check `GET /api/workflow/by-document/{id}` |
| **Signatures do not appear on the published PDF** | Stamping failed, or the file is not a PDF | Search the log for `"Could not stamp signatures"` — publication deliberately proceeds unsigned |
| **Windows: `libmagic` import error** | No native library | Harmless — MIME falls back to the extension map |
| **Slow start** | First run downloads the ONNX embedding model | One-off; cached under `data/.cache` |

---

## 10. Upgrading

```bash
git pull
pip install -r requirements.txt
python cli.py init          # runs create_all + additive migrations, idempotent
python cli.py serve
```

Schema changes are **additive only**, so an older build still runs against a
migrated database. Check the migration list in
[doc 05 §7](05-data-model.md#7-schema-evolution) to see what a release added.

**Back up `data/` before every upgrade.**

---

## 11. Performance tuning

| Lever | When |
|---|---|
| `python cli.py db create-indexes` | Always, once |
| `python cli.py db optimize` | Monthly, or after a bulk delete |
| Move to PostgreSQL | When writes contend — SQLite serialises them |
| `OCR_ENGINE=tesseract` | When vision quota is the bottleneck, or nothing may leave the network |
| `AI_TEXT_LIMIT` down | To fit a tighter token budget |
| `reasoning_effort: low` | Faster, cheaper classification |
| Remote ChromaDB | When the vector store outgrows the process |
| `MAX_FILE_SIZE` down | To bound worst-case processing time |

⚠️ **Do not run multiple uvicorn workers yet.** Rate-limit counters, the AI
capability cache and the embedded ChromaDB client are per-process state. See
[doc 04 §6.2](04-high-level-design.md#62-enterprise-target-not-yet-built) for
what must change first.

---

## 12. Current demo accounts

The demo seed script creates these. They exist in the working database at the
time of writing and **must be removed before go-live**.

| Username | Person | Approve | Sign |
|---|---|---|---|
| `Aryan` | System administrator | ✔ | ✔ (admin) |
| `s.iyer` | Sudha Iyer · Head of Finance | ✔ | ✔ |
| `r.menon` | Rahul Menon · Head of Legal | ✔ | ✔ |
| `p.krishnan` | Prakash Krishnan · Head of Operations | ✔ | ✔ |
| `a.khan` | Ayesha Khan · Procurement Lead | ✔ | ✔ |
| `m.raghavan` | Meena Raghavan · AP Clerk | ✔ | ✖ |
| `d.varma` | Divya Varma · HR Manager | ✔ | ✖ |

The last two exist deliberately: they demonstrate that the product enforces the
difference between *approving* a document and *signing* it.

Passwords: the shared demo password is defined in
[scripts/seed_demo_data.py](../../scripts/seed_demo_data.py) and printed when
the script runs. `Aryan` keeps whatever password was set at first-run setup.
