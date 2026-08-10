# Groq setup and model configuration

The application runs on **Groq** by default:

| Role | Model | Where it is used |
|------|-------|------------------|
| Chat + reasoning | `openai/gpt-oss-120b` | RAG answers, metadata extraction |
| Vision | `qwen/qwen3.6-27b` | OCR of scanned PDFs and images |
| Embeddings | `all-MiniLM-L6-v2` (local, CPU) | Semantic search |

> **Groq has no embeddings endpoint.** Semantic search therefore runs a small
> ONNX model locally instead. It needs no API key and no GPU; the ~80 MB model
> is downloaded once on first use and cached. See
> [Embeddings](#embeddings) to switch to a hosted backend.

---

## 1. Put your API key in `.env`

Create a key at <https://console.groq.com/keys>, then edit `.env`:

```dotenv
GROQ_API_KEY=gsk_your_key_here
```

That is the only value you must set. `.env` is gitignored.

## 2. Change model names in `config/models.json`

Model **names** live in `config/models.json`; API **keys** live in `.env`.

```jsonc
{
  "active_provider": "groq",
  "models": {
    "chat":     "openai/gpt-oss-120b",
    "analysis": "openai/gpt-oss-120b",
    "vision":   "qwen/qwen3.6-27b"
  }
}
```

To use a different model, change the string and restart. That is all, because model
keys are deliberately **not** written to the database on install, so the file
stays authoritative.

The full precedence chain, lowest to highest:

```
code defaults  <  config/models.json  <  environment / .env  <  database
```

You only need the sync command in two situations:

1. someone saved a model name through **Settings → AI Configuration** in the
   UI (that writes a database row, which then wins), or
2. the install predates this layout and already has model rows in its
   settings table.

```bash
python cli.py sync-model-config    # push the file's values into the database
```

`GET /api/settings/models` always shows the effective values, so you can see
exactly what is in force.

> Note: `.env` sits *above* the config file. The shipped `.env` keeps the model
> and OCR lines commented out for that reason. Uncomment them only if you
> deliberately want an environment override.

## 3. Verify

```bash
python cli.py check-ai     # probes chat, embeddings and vision for real
python cli.py status       # configuration overview
```

`check-ai` sends one tiny request to each configured model and prints the
result, so a wrong model name shows up immediately as a 404 rather than as a
failed document import later.

---

## Embeddings

`config/models.json` → `embeddings.provider`:

| Value | Model | Dimensions | Needs a key |
|-------|-------|-----------:|-------------|
| `local` (default) | `all-MiniLM-L6-v2` | 384 | no |
| `openai` | `text-embedding-3-small` | 1536 | `OPENAI_API_KEY` |
| `azure` | your deployment | varies | `AZURE_OPENAI_API_KEY` |

Changing the backend changes the vector size, which the existing ChromaDB
collection cannot accept. After switching, re-index:

```bash
python cli.py reindex-vectors --force
```

If you forget, the app raises an explicit "Embedding dimension mismatch" error
that names this command rather than failing obscurely.

If the local model cannot be downloaded (offline host), semantic search is
disabled and search automatically falls back to SQL full-text search. The
health endpoint reports this under `services.embeddings`.

---

## OCR engine

`config/models.json` → `ocr.engine`:

| Value | Behaviour |
|-------|-----------|
| `auto` (default) | PDF text layer → vision model → Tesseract |
| `vision` | Always use the vision model (Tesseract only as a hard fallback) |
| `tesseract` | Never call the vision model |

`auto` is the cheapest correct option: digital PDFs are read directly with
PyPDF2 (no API call, no poppler, exact text), and only scanned pages or images
are sent to the vision model.

Relevant knobs:

- `ocr.vision_max_pages` caps the pages sent per document (default 20)
- `ocr.vision_max_image_bytes`: images are downscaled to fit this budget
- `ocr.pdf_text_layer_first`: set `false` to always OCR

### Local tools

Vision OCR removes the hard dependency on Tesseract, but Poppler is still
needed to rasterise **scanned** PDFs into page images:

```powershell
winget install UB-Mannheim.TesseractOCR   # fallback OCR engine
winget install oschwartz10612.Poppler     # required for scanned PDFs
```

Both are auto-detected, including winget's versioned package directory,
Chocolatey, scoop and `PATH`, so `.env` normally needs no paths. Set them
explicitly only to override:

```dotenv
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
POPPLER_PATH=...\WinGet\Packages\oschwartz10612.Poppler_...\poppler-25.07.0\Library\bin
```

Note that winget's poppler directory contains the version number, so a pinned
`POPPLER_PATH` goes stale after an upgrade. Deleting the line is safer than
maintaining it.

Digital PDFs, `.txt` and `.md` need neither tool.

`python cli.py status` prints which engines are actually available.

### Rate limits on multi-page scans

The vision model's free tier allows 8000 tokens per minute, which a two-page
scan can exhaust. When that happens the API reports how long to wait and the
transcriber honours it, retrying up to 3 times per page rather than skipping
ahead. A page that still fails is recorded inline as
`[Page N of M could not be transcribed: ...]` so a gap is never mistaken for a
blank page.

Practical effect on the free tier: scanning is correct but slow, roughly one
page per 20-30 seconds once the budget is saturated. `ocr.vision_max_pages`
caps how much of a long document is sent.

---

## Reasoning

`openai/gpt-oss-120b` is a reasoning model. `config/models.json` →
`generation.reasoning_effort` accepts `none` | `low` | `medium` | `high`
(default `medium`). Use `none` to omit the parameter entirely.

If a model rejects `reasoning_effort`, the app detects the 400, remembers it
for that model, and retries without the parameter, so no configuration change
needed. The same happens for `response_format` (structured outputs): the JSON
schema then moves into the prompt instead.

---

## Switching providers

Set `active_provider` in `config/models.json` (or `AI_PROVIDER` in `.env`) to
`groq`, `openai` or `azure`, and supply the matching key. The per-provider
request quirks such as `max_completion_tokens` vs `max_tokens`, Azure not accepting
`temperature`, and deployment names instead of model names, are handled in
`app/services/ai_client_factory.py` and `config/models.json` → `providers`.

---

## Docker

`config/` is copied into the image. To edit models without rebuilding, mount
over it:

```bash
docker run -d \
  --name documentmanager \
  -p 127.0.0.1:8000:8000 \
  --env-file .env \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  documentmanager:local
```

The `data` volume also caches the local embedding model, so it downloads once
rather than on every container start.

---

## Troubleshooting

| Symptom | Cause and fix |
|---------|---------------|
| `Groq API key is missing` | Set `GROQ_API_KEY` in `.env` |
| 404 on the chat model | Model name not available to your account. Change it in `config/models.json` |
| Model change has no effect | A `.env` override or a database row set via the UI is winning. Check `GET /api/settings/models`, then run `python cli.py sync-model-config` |
| `Embedding dimension mismatch` | Embedding backend changed. Run `python cli.py reindex-vectors --force` |
| Search returns keyword hits only | Local embedding model unavailable. Check `GET /api/health/` → `services.embeddings` |
| Scanned PDFs fail | Poppler missing. Run `winget install oschwartz10612.Poppler`. Check `python cli.py status` |
| `No OCR engine available` | Neither Tesseract nor a vision model is usable; add a key or install Tesseract |
| Scanned pages are slow | Free-tier vision limit is 8000 TPM; the transcriber waits out each 429 rather than dropping pages |
| `[Page N could not be transcribed]` in a document | That page exhausted its retries. Re-run OCR for the document, or upgrade the Groq tier |
