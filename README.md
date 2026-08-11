<div align="center">
  <h1>Document Management System</h1>
  <p><strong>Capture, author, approve, sign and retain documents in one governed repository.</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Backend-FastAPI-2B50E2?style=flat-square" alt="FastAPI">
    <img src="https://img.shields.io/badge/UI-Zero%20dependency-2B50E2?style=flat-square" alt="UI">
    <img src="https://img.shields.io/badge/License-MIT-6B7280?style=flat-square" alt="MIT">
  </p>
</div>

---

## About

A self-hosted document management system. Documents arrive two ways — dropped
into a watched folder or uploaded through the browser, or written in the built-in
**Document Studio** on a letterhead template. Either way the text is extracted by
a vision model or Tesseract OCR, classified by an LLM, and indexed for semantic
search and question answering.

From there a document can be routed through a multi-step approval chain with
per-step signature requirements, published with the collected signatures stamped
onto the PDF, and kept as an immutable version history.

The product is organised around five sequential steps, which are also its five
main screens — the navigation *is* the process:

```
 1. Document Studio → 2. Review → 3. Approval → 4. Status & Tracking → 5. Publishing
    write it, or        confirm     choose who     watch it move          release it,
    bring a file in     the details signs, and     through the chain      signatures
                        read from it in what order                        stamped on
```

**Built with** FastAPI · SQLAlchemy · SQLite (PostgreSQL for larger installs) ·
ChromaDB for vectors · Groq / OpenAI / Azure OpenAI for AI · a local ONNX
embedding model that needs no API key · and a front end of plain HTML, CSS and
JavaScript with no build step.

The AI provider is optional. The system runs without any API key, with the AI
features switched off.

> **Full technical documentation** — architecture, data model, API reference,
> security design and operations runbooks — is in
> **[docs/DMS-Project-Documentation.md](docs/DMS-Project-Documentation.md)**,
> also split by chapter under [docs/srs/](docs/srs/README.md).

---

## Running it

### Requirements

- Python 3.12
- Tesseract OCR and Poppler, for reading scans and photos
- 4 GB RAM, 10 GB free disk

### Linux

```bash
sudo apt-get install -y tesseract-ocr poppler-utils libmagic1

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env        # then set SECRET_KEY and your AI provider key
./run.sh
```

Open **http://127.0.0.1:8000**. The first account you create becomes the
administrator.

`run.sh` honours `DOCUMENT_MANAGER_HOST` and `DOCUMENT_MANAGER_PORT`, and passes
any extra arguments through to uvicorn:

```bash
DOCUMENT_MANAGER_PORT=8080 ./run.sh          # different port
DOCUMENT_MANAGER_HOST=0.0.0.0 ./run.sh       # reachable from other machines
./run.sh --reload                            # auto-reload while editing
```

Binding to `0.0.0.0` also needs that origin added to `CORS_ORIGINS` in `.env`.

### Windows

```powershell
winget install tesseract-ocr
choco install poppler

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

copy .env.example .env
.venv\Scripts\python cli.py serve
```

Set `TESSERACT_PATH` and `POPPLER_PATH` in `.env` to wherever those two
installed.

### Docker

```bash
./setup.sh build
./setup.sh prod
```

`setup.sh` drives Docker or Podman only; use `run.sh` to start the application
directly.

---

## Configuration

Copy `.env.example` to `.env` and set at least a strong `SECRET_KEY`.

```dotenv
SECRET_KEY=replace-with-a-generated-value
ENVIRONMENT=production

DATABASE_URL=sqlite:///./data/documents.db

# AI provider: groq | openai | azure. Leave the key unset to run without AI.
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...

# Embeddings: local (default, no API key needed) | openai | azure
EMBEDDING_PROVIDER=local

# OCR: auto (PDF text layer, then vision model, then Tesseract) | vision | tesseract
OCR_ENGINE=auto

# Where the OCR tools are installed
TESSERACT_PATH=/usr/bin/tesseract
POPPLER_PATH=/usr/bin
```

**Model names are not set here.** They live in
[`config/models.json`](config/models.json). Settings resolve in this order,
lowest priority first:

```
code defaults  →  config/models.json  →  environment / .env  →  database
```

The database wins, so a value saved through the Settings screen overrides `.env`.
Run `python cli.py sync-model-config` to push `config/models.json` back over
stale database rows.

---

## Command line

```bash
.venv/bin/python cli.py init                      # create the database and folders
.venv/bin/python cli.py serve                     # start the server
.venv/bin/python cli.py status                    # folders, counts, OCR, AI, embeddings
.venv/bin/python cli.py check-ai                  # probe chat, embedding and vision models
.venv/bin/python cli.py users                     # list accounts
.venv/bin/python cli.py reset-password NAME       # set a new password
.venv/bin/python cli.py process                   # process the staging folder now
.venv/bin/python cli.py sync-model-config         # apply config/models.json
.venv/bin/python cli.py reindex-vectors --force   # rebuild embeddings after a model change
.venv/bin/python cli.py db analyze|optimize|create-indexes|size
.venv/bin/python cli.py backup create|list|restore
```

Interactive API documentation is at `/docs` (Swagger) and `/redoc` once the
server is running.

---

## License

MIT. See [LICENSE](LICENSE).

This is a derivative of the open-source
[`JayRHa/DocumentManager`](https://github.com/JayRHa/DocumentManager) project,
original work © Jannik Reinhard and Fabian Peschke, MIT licensed. All upstream
copyright notices are retained.
