# 11 · Testing, Quality & Handover

> **Audience:** QA, project managers, and the team taking this codebase over.
> This is the honest register: what is tested, what is not, what is broken or
> half-finished, and what to do in the first two weeks.

---

## 1. Test suite as it stands

`python -m pytest tests -q` — **160 test functions across 12 files.**

| File | Tests | Covers |
|---|---|---|
| `test_vision_ocr.py` | 32 | Vision transcription, page and byte caps, fallbacks |
| `test_end_to_end.py` | 25 | Auth, users, documents, metadata CRUD through the API |
| `test_groq_provider.py` | 24 | Client construction, key failover, quota classification, retries |
| `test_model_config.py` | 13 | `config/models.json` parsing and settings overrides |
| `test_rate_limiting.py` | 13 | Sliding window, failure-only auth counting, proxy trust |
| `test_reasoning_behaviour.py` | 13 | Reasoning-effort handling, token starvation detection |
| `test_embedding_service.py` | 11 | Local and hosted embeddings, dimensions, ordering |
| `test_runtime_configuration.py` | 10 | Configuration precedence |
| `test_sdk_compat.py` | 9 | OpenAI SDK parameter adaptation |
| `test_backup_security.py` | 4 | Path traversal on backup restore/delete |
| `test_ocr_service.py` | 4 | Engine selection, binary discovery |
| `test_file_watcher.py` | 2 | Staging observer |

`tests/conftest.py` provides the fixtures.

### 1.1 CI

[.github/workflows/ci.yml](../../.github/workflows/ci.yml) — on push and PR to
`main`, Ubuntu, Python 3.12:

1. Install `libmagic1`, `tesseract-ocr`, `poppler-utils`
2. `pip install -r requirements.txt`
3. Validate `config/models.json` parses
4. `python -m pytest tests -q`
5. Parse every `.ps1` / `.psm1` with the PowerShell parser

⚠️ No linting, no type checking, no coverage measurement, no security scanning.

---

## 2. What the tests protect well

The AI integration layer is genuinely well covered, and it is the part most
likely to break from the outside:

- Provider capability negotiation and parameter dropping
- Groq key failover, quota vs. daily-cap classification
- Reasoning-token starvation
- Embedding provider selection and dimension awareness
- Configuration precedence
- Rate limiting, including the failure-only auth rule and proxy trust
- Path traversal on backups

---

## 3. ⚠️ Coverage gaps — the important part

**The modules carrying the most business risk have the least automated
coverage.** In rough order of exposure:

| Untested area | Why it matters | Suggested first tests |
|---|---|---|
| **Approval engine** (`workflow_service.py`) | Every business rule in the product lives here. A regression silently corrupts approvals. | `can_act` refusal matrix; `all` vs `any` quorum; `outstanding()` after each decision; reject is decisive; `resubmit` clears **all** decisions; `_advance` sets `document.is_approved`; a step cannot be created with a non-signatory when it requires a signature |
| **Signature stamping** (`signature_stamp.py`) | Produces the legal artefact | `resolve()` on A4 / Letter / an odd-sized scan; automatic overflow to a signature page; `content_bottom` footer-zone logic; stamping is non-destructive |
| **Versioning** (`version_service.py`) | The immutability guarantee | `capture` is idempotent per version; exactly one `is_current`; `lock_current`; restore is forward-only and writes a new row |
| **Publishing** (`publishing.py`) | The gate that makes approval mean something | Publish refused unless approved; version locked **before** stamping; stamping failure still publishes; export format availability |
| **Studio publish** (`studio.py`) | Creates real documents | Sanitising; version chain on revision; `_enrich` fills **only** blanks; draft → published transition |
| **PDF/DOCX rendering** | User-visible output | Golden-file tests per template |
| **CSRF middleware** | Protects every write | Signed/unsigned token handling; prefix-based exclusion behaviour |
| **Page-route authorisation** (`main.py`) | The admin gate | A non-admin GET of each `ADMIN_ONLY_PAGES` entry redirects to `/tasks` |
| **Search fallbacks** | User-visible degradation | Vector empty → full-text; circuit breaker opens and recovers |
| **RAG citation invariant** | Wrong citations are worse than no citations | A document with no text is excluded from **both** context and `sources`, so `[DocN] == sources[N-1]` holds |

**Recommendation:** before any refactor of the approval engine, write the
`can_act` refusal matrix and the quorum tests. They are cheap — the engine is
pure functions over ORM objects — and they are the safety net everything else
depends on.

---

## 4. Known issues and technical debt

### 4.1 Functional gaps documented as features elsewhere

| Item | Reality |
|---|---|
| **Per-document / department access control** | ⚠️ **Not implemented.** Any `documents.read` holder sees every document. The root `README.md` claims otherwise. See [doc 09 §6.1](09-security-design.md#61-️-no-per-document-access-control--the-largest-gap). |
| **Retention policy engine** | Label can be stored; nothing acts on it |
| **Records warehousing** | Not implemented; `/records` redirects |
| **Integrations / webhooks** | Not implemented; `/integrations` redirects |
| **Annotations** | Not implemented |
| **Reminders** | Writes a workflow event; **sends no email** |
| **Password reset by email** | Columns exist; no endpoint |
| **SSO / LDAP** | Not implemented |

### 4.2 Code-level debt

| # | Issue | Impact | Effort |
|---|---|---|---|
| D-1 | **Two role systems coexist** — standard (`reader/contributor/approver/signatory`) and legacy (`admin/editor/viewer`). `apply_role` never removes the legacy ones, so `editor` granted by `/api/admin/fix-permissions` is permanent and invisible in the People screen. | Confusing, and `editor` carries `documents.delete` | Medium |
| D-2 | **No standard role grants any `*.delete`** permission, so deletion is admin-only by accident rather than by statement | Surprising; undocumented | Low |
| D-3 | **Disabled middleware left in the tree** — `auth_middleware.py` and `logging_middleware.py` are imported then commented out (`app/main.py:19,25`) | Dead code that reads as live | Low |
| D-4 | **`schemas_validated.py` duplicates `schemas.py`** in part | Two sources of truth for validation | Low |
| D-5 | **No Alembic chain** despite `alembic` being a dependency. Schema is `create_all` + additive DDL, which cannot express a data migration, a constraint change or a rename. | Blocks PostgreSQL at scale | Medium |
| D-6 | **Per-process state** — rate limits, AI capability cache, ChromaDB client | Blocks multi-worker deployment | Medium |
| D-7 | **`app/routers/admin_fix.py`** is described in its own docstring as *"Temporary admin endpoint"* | Should be folded into the People screen or removed | Low |
| D-8 | **`tasks_for` filters in Python, not SQL** | Fine at hundreds of live steps; revisit at tens of thousands | Low |
| D-9 | **Expired sessions are never cleaned up** — `cleanup_expired_sessions()` exists but is never scheduled | Table grows; rows are inert | Low |
| D-10 | **No security headers** (CSP, HSTS, frame options, referrer policy) | Add at the proxy or in middleware | Low |
| D-11 | **Deferred startup (~2 s)** means an early request can hit an uninitialised database | Use the readiness probe to gate traffic | Low |
| D-12 | **CSRF exclusion is prefix-matched** (`startswith`), so `/api/health` excludes everything beneath it | Keep exclusions specific | Low |
| D-13 | **No storage compaction** — versions, thumbnails and duplicates accumulate indefinitely | Disk grows without bound | Medium |
| D-14 | **`legacy-ui/` retained but unrouted** (~4 000 lines) | Dead weight; delete once nobody needs to compare | Low |
| D-15 | **`python.exe.stackdump` committed at the repo root** | Noise; delete | Trivial |
| D-16 | **SQLite foreign keys not enforced** (`PRAGMA foreign_keys` never set) | Integrity depends on application code | Low |
| D-17 | **A live Groq API key is present in `.env`** in the working tree | Rotate it on handover | Trivial |
| D-18 | **Audit log readable by any authenticated user** via the API, though the page is admin-gated | Tighten to `require_admin_flexible` | Trivial |

---

## 5. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Confidential document is read by someone not entitled to it | **High** | **High** | Implement per-document scoping (§4.1); until then, restrict who gets an account |
| A regression in the approval engine corrupts an approval | Medium | **High** | Write the engine test suite (§3) before touching it |
| AI daily quota exhausted mid-day | Medium | Medium | Configure a second Groq key on a different account |
| Document text sent to a third-party AI provider without sign-off | Medium | **High** | Complete the data-flow assessment in [doc 09 §7](09-security-design.md#7-data-flow-to-the-ai-provider) |
| SQLite write contention as usage grows | Medium | Medium | Move to PostgreSQL; needs a migration chain first (D-5) |
| Disk exhaustion from accumulated versions | Medium | Medium | Monitor disk; build a compaction job (D-13) |
| Audit trail altered | Low | **High** | Ship audit rows to an external append-only sink |
| Multi-worker deployment silently multiplies rate limits | Medium | Medium | Do not run multiple workers until D-6 is fixed |
| Restore has never been tested | Medium | **High** | Run the recovery drills in [doc 10 §7.4](10-deployment-and-operations.md#74-recovery-drills--run-these-before-go-live) |

---

## 6. Recommended roadmap

### Phase 1 — make it safe to change (2–3 weeks)
1. Test suite for the approval engine, versioning and publishing (§3)
2. Rotate the committed API key; tighten the audit-log API to admin (D-17, D-18)
3. Add security headers (D-10)
4. Delete dead code: disabled middleware, `legacy-ui/`, the stackdump (D-3, D-14, D-15)
5. Add linting and coverage to CI

### Phase 2 — close the largest functional gap (3–4 weeks)
6. **Per-document access control** — scope the document query, the search
   filter, RAG retrieval, and the download and file endpoints. All four
   together, or it is not access control.
7. Reconcile the two role systems into one (D-1, D-2)
8. Remove `admin_fix.py` (D-7)

### Phase 3 — production readiness (3–4 weeks)
9. Alembic migration chain (D-5)
10. PostgreSQL support verified end to end
11. Move rate limits and caches to Redis; enable multi-worker (D-6)
12. Storage compaction / retention job (D-13)
13. Metrics export and alerting

### Phase 4 — the features that were promised but not built
14. Retention policy enforcement
15. Email notifications for approvals and reminders
16. SSO
17. Webhooks / connectors
18. Annotations

---

## 7. Handover checklist

### Week 1 — orient
- [ ] Read [doc 01](01-introduction.md) and [doc 04](04-high-level-design.md)
- [ ] Install and run locally; complete first-run setup
- [ ] `python scripts/seed_demo_data.py --reset`, then walk the whole
      [DEMO.md](../../DEMO.md) script end to end — it exercises every feature in
      the order the product is meant to be used, in about 15 minutes
- [ ] `python -m pytest tests -q` and confirm it passes
- [ ] Read `app/services/workflow_service.py` **in full**. It is 655 lines and it
      is the product.

### Week 2 — go deeper
- [ ] Read [doc 05](05-data-model.md) alongside `app/models.py`
- [ ] Read [doc 06](06-low-level-design.md) alongside the services it describes
- [ ] Trace one document end to end with a debugger: upload → OCR → classify →
      index → workflow → approve → publish
- [ ] Read [doc 09](09-security-design.md) §6 and confirm the residual risks are
      acceptable to the business, in writing

### Environment and access
- [ ] Repository access, with history
- [ ] Groq (or chosen provider) account and **new** API keys
- [ ] Access to the production `data/` volume and its backups
- [ ] A restore actually performed, not merely configured
- [ ] The production `SECRET_KEY` and `JWT_SECRET_KEY` transferred securely

### Knowledge to confirm you have
- [ ] Why `can_approve` and `can_sign` are two flags
- [ ] Why exactly one step is `current`, and what depends on it
- [ ] Why `resubmit` clears every prior decision
- [ ] Why the approved version is locked **before** signatures are stamped
- [ ] Why placement is a page fraction rather than millimetres
- [ ] Why the database `settings` table beats `.env`
- [ ] Why embeddings default to a local ONNX model
- [ ] Why `max_tokens_vision` is 2048 and must not be raised

### Decisions the business must make
- [ ] Is "everyone sees every document" acceptable, or is §6.1 a blocker?
- [ ] Is sending document text to the AI provider approved?
- [ ] Which of the unbuilt modules (retention, records, integrations, SSO) are
      actually required, and by when?
- [ ] SQLite or PostgreSQL for production?
- [ ] Who owns key rotation, backups and the restore drill?

---

## 8. Where to find things

| Looking for | Go to |
|---|---|
| Business context | [doc 01](01-introduction.md) |
| A specific behaviour | [doc 02](02-functional-requirements.md) |
| A performance or security target | [doc 03](03-non-functional-requirements.md) |
| Architecture and flows | [doc 04](04-high-level-design.md) |
| A table or a column | [doc 05](05-data-model.md) |
| How a module works | [doc 06](06-low-level-design.md) |
| An endpoint | [doc 07](07-api-reference.md) or `/docs` |
| A screen | [doc 08](08-frontend-design.md) |
| A control or a risk | [doc 09](09-security-design.md) |
| How to install, configure or fix it | [doc 10](10-deployment-and-operations.md) |
| A guided 15-minute walkthrough | [DEMO.md](../../DEMO.md) |
| AI provider setup detail | [docs/groq-setup.md](../groq-setup.md) |
| Why the UI is shaped this way | [docs/ux-redesign-plan.md](../ux-redesign-plan.md) |
