# 09 · Security Design

> **Audience:** security reviewers, architects, operations.
> This documents the controls that exist, how they work, and — equally
> important — the ones that do not. ⚠️ marks a gap or a residual risk.

---

## 1. Trust model

| Zone | Trust | Notes |
|---|---|---|
| Browser / client | **Untrusted** | Every rule is enforced server-side; the UI only reflects it |
| Application process | Trusted | Holds the database, the storage tree and the AI keys |
| Database | Trusted, at rest | ⚠️ Not encrypted. Anyone with file access can read every document's extracted text and every audit row. |
| Filesystem | Trusted, `0600` | Documents are owner-only; other local users cannot browse them |
| AI provider | **Semi-trusted external** | Document text leaves the network. See §7. |
| Network | Assumed internal | ⚠️ No per-document access control — see §6.1 |

**The core assumption:** the deployment sits inside an organisational boundary.
Authentication establishes *who*; role permissions establish *what kind of
thing*; there is no *which document* dimension.

---

## 2. Authentication

### 2.1 Credentials

| Property | Value |
|---|---|
| Identifier | Username **or** email |
| Hash | bcrypt via `passlib` (`app/models.py:446`) |
| Inactive users | Cannot sign in — checked after password verification |
| Failure logging | `login_failed_user_not_found`, `login_failed_wrong_password`, `login_failed_inactive_user`, each with IP and user agent |
| ⚠️ Password policy | **None enforced.** No minimum length, complexity, history or expiry. |
| ⚠️ Account lockout | **None.** Protection is rate limiting by IP, not by account — see §4.2. |
| ⚠️ MFA | Not implemented |
| ⚠️ Self-service reset | Not implemented. `password_reset_token` / `password_reset_expires` columns exist but no endpoint uses them; an administrator resets via `cli.py reset-password`. |

> ⚠️ **Username enumeration.** `authenticate_user` logs a distinct event for
> "user not found" versus "wrong password", though the **HTTP response is the
> same 401 in both cases**, so the API does not leak. The distinction exists in
> the logs only.

### 2.2 Sessions

| Property | Value |
|---|---|
| Token | `secrets.token_urlsafe(32)` — 256 bits of entropy |
| Storage | A `sessions` row; the token is the lookup key |
| Cookie | `session_token`, `HttpOnly`, `SameSite=Lax`, `Secure` when `production_mode` |
| Lifetime | 24 hours (`SESSION_EXPIRE_HOURS`) |
| Invalidation | Deleted on logout |
| Validation | Every lookup filters `expires_at > utcnow()` |
| ⚠️ Rotation | The token is **not** rotated on privilege change |
| ⚠️ Cleanup | `cleanup_expired_sessions()` exists but is **never scheduled**. Expired rows accumulate; they are inert but they grow. |
| ⚠️ Concurrent sessions | Unlimited, and not listed or revocable from the UI |

### 2.3 JWT

| Property | Value |
|---|---|
| Algorithm | HS256 |
| Lifetime | 30 minutes |
| Claim | `sub` = username |
| Secret | `jwt_secret_key` from the settings table; **generated and persisted on first use** so it survives restarts |
| ⚠️ Revocation | Stateless — a stolen JWT is valid until it expires. There is no deny-list. |
| ⚠️ Refresh | No refresh-token flow; the client re-authenticates |

---

## 3. Authorisation

### 3.1 Three mechanisms

| Mechanism | Question it answers | Where |
|---|---|---|
| `is_admin` | May this person do anything at all? | Short-circuits every check |
| Role permissions | May they reach this **kind** of thing? | `User.has_permission` |
| `can_approve` / `can_sign` | May they act on an approval, and may they sign it? | `workflow_service.can_act` |

### 3.2 Standard roles

| Role | Permissions |
|---|---|
| `reader` | `documents.read`, `correspondents.read`, `doctypes.read`, `tags.read`, `settings.read`, `search.read` |
| `contributor` | reader + `documents.create/update`, `correspondents.create/update`, `doctypes.create`, `tags.create/update` |
| `approver` | contributor + `documents.approve` |
| `signatory` | approver + `documents.sign` |

Applied by `role_service.apply_role` whenever authority changes, and backfilled
at startup for anyone holding no role.

> ⚠️ **No standard role grants any `*.delete` permission.** `documents.delete`,
> `correspondents.delete`, `doctypes.delete` and `tags.delete` are required by
> their endpoints but appear in no role's permission list. In practice
> **deletion is administrator-only**. This may be intentional, but it is not
> stated anywhere and a new team would not guess it.

### 3.3 Legacy roles

`admin`, `editor` and `viewer` are created by `auth_service.create_default_roles`
during first-run setup, and `editor` is granted by
`POST /api/admin/fix-permissions/{username}`.

⚠️ **Two role systems coexist.** `apply_role` only ever swaps between the four
standard roles and deliberately leaves anything else alone — so a user granted
`editor` by the repair endpoint keeps `documents.delete` permanently, invisible
to the People screen. See doc 11.

### 3.4 The two-permission approval model

This is the security control the product is built around.

```
can_approve   may act on an approval step at all
can_sign      may apply a signature to that approval
```

They are checked in three places:

| Where | Check |
|---|---|
| **Design time** — `_reject_unsignable` | Refuses to create a signature step with a non-signatory assignee, naming them |
| **Decision time** — `can_act` | Refuses the decision, with a reason |
| **Signature time** — `decide` | Re-checks `can_sign or is_admin` before storing the signature |

Checking at design time is what prevents a document being stuck for three days
with somebody who was never allowed to move it.

### 3.5 Page-level authorisation

`ADMIN_ONLY_PAGES` = `/templates`, `/organization`, `/audit`, `/settings`,
`/publish`, `/process`. A non-admin requesting one is redirected to `/tasks`,
**on the server**.

---

## 4. Request-level controls

### 4.1 CSRF

Signed double-submit cookie (`app/middleware/csrf_middleware.py`):

- Cookie value = `<token>.<HMAC-SHA256(token, secret_key)>`
- `httponly=False` (JavaScript must read it), `samesite=strict`, 24 h
- The header `X-CSRF-Token` must equal the **unsigned** token
- Signed with the application `secret_key`, so tokens survive restarts and
  multiple workers — a per-process random key would invalidate every browser's
  cookie on restart

⚠️ **Exclusion matching is prefix-based** (`path.startswith(excluded)`), so
`/api/health` also excludes any deeper path under it. Keep the exclusion list
narrow and specific.

⚠️ `POST /api/settings/test/ai` is CSRF-exempt and administrator-gated. It is a
connection test that returns provider status; the exposure is limited, but it is
a state-changing method outside CSRF protection.

### 4.2 Rate limiting

| Path | Budget |
|---|---|
| Default | 100 / 60 s per IP |
| `/api/auth/login`, `/api/auth/setup/initial-user` | 5 / 300 s, **failures only** |
| `/api/documents/upload` | 20 / 60 s |
| `/api/ai/chat` | 30 / 60 s |
| `/api/ai/extract` | 20 / 60 s |

Responses carry `X-RateLimit-Limit`, `X-RateLimit-Window`,
`X-RateLimit-Remaining`, and `Retry-After` on a 429.

**Proxy handling done correctly:** `X-Forwarded-For` and `X-Real-IP` are honoured
**only** when the direct peer is listed in `trusted_proxy_ips` (default
`127.0.0.1,::1`). Otherwise an attacker could choose their own rate-limit bucket
by setting a header.

⚠️ **Counters are per-process, in memory.** A multi-worker deployment multiplies
every limit by the worker count. Moving them to Redis is a prerequisite for
horizontal scaling.

⚠️ Limiting is **per IP, not per account**. An attacker with a botnet can still
spray one account; a user behind a shared NAT can lock out their colleagues.

### 4.3 CORS

`allow_origins` from configuration (default `localhost:3000`, `localhost:8000`,
`127.0.0.1:8000`), `allow_credentials=True`, methods restricted to
`GET, POST, PUT, DELETE`, headers restricted to `Content-Type`,
`Authorization`, `X-CSRF-Token`.

⚠️ Credentialed CORS means the origin list must be exact in production. Never
add a wildcard.

---

## 5. Content and file security

### 5.1 Upload validation

`validate_file_upload` (`app/utils/file_security.py`) checks, in order:
extension allow-list → size limit → content/magic-byte validation → filename
sanitisation. Failures raise `FileTypeNotAllowedError` or `FileSecurityError`,
mapped to HTTP 400.

### 5.2 Path traversal

`secure_file_path(base, filename)` resolves and asserts the result stays under
`base`. Applied to uploads, backup restore and backup delete
(`tests/test_backup_security.py` covers the backup paths).

### 5.3 File permissions

`set_secure_permissions(path, is_private=True)` → **`0600`**.

> Uploaded documents frequently contain invoices, contracts and tax data.
> Owner-only is the correct default, not world-readable `0644`. Applied to
> staging writes, Studio publishes and signed renditions.

### 5.4 HTML sanitising

`sanitize_html` (bleach + tinycss2) is applied **twice**: when a draft or a
published body is stored, and again at render time. A body stored before a rule
changed therefore cannot bypass the new rule.

Filtering inline CSS rather than discarding the `style` attribute entirely is
what lets alignment and colour survive from the editor into the PDF.

### 5.5 Response headers

Every file response carries `X-Content-Type-Options: nosniff` and an explicit
`Content-Disposition` (`inline` for viewing, `attachment` for download).

⚠️ **No Content-Security-Policy, HSTS, X-Frame-Options or Referrer-Policy
header is set.** These should be added at the reverse proxy, or in a small
middleware. See doc 11.

### 5.6 Asset resolution by id

Composed bodies reference images by **`media_assets.id`**, never by path. The
PDF renderer resolves the id against the table, so a crafted body cannot make
the renderer read an arbitrary file.

### 5.7 Prompt-injection containment

Text extracted from an uploaded document is fed to the model. `authoring_ai`
runs **everything the model returns** through the same sanitiser the PDF
renderer uses, so a prompt-injected `<script>` in a source document cannot come
back as markup the browser would execute.

⚠️ Containment is at the **output** boundary. A malicious document can still
influence what the model says — a fabricated summary, a misleading answer in the
assistant. Treat AI-generated metadata as a suggestion, which is exactly how the
Studio treats it (author's values always win).

---

## 6. Known gaps and residual risk

### 6.1 ⚠️ No per-document access control — the largest gap

Any user holding `documents.read` can read **every** document: list it,
download it, search it, and ask the assistant about it. There is no filter by
department, correspondent, sensitivity or ownership.

| Affected | Consequence |
|---|---|
| `GET /api/documents/` | Returns everything |
| `GET /api/documents/{id}/download` | Any document |
| `POST /api/search/` and `/rag` | Search and RAG span the whole repository |

This directly contradicts the root `README.md`'s claim of *"organization and
department access control"*. **It is not implemented.**

*Mitigation until it is:* only grant accounts to people entitled to see
everything, and treat the deployment as a single confidentiality domain.

*To implement it:* add a `department` or `sensitivity` column to `documents`,
add a scoping filter to the document query, the search filter, and the RAG
retrieval, and add the corresponding check to the download and file endpoints.
All four must change together — a scoped list with an unscoped download is not
access control.

### 6.2 ⚠️ The activity log is readable by any authenticated user

The `/audit` **page** is admin-gated, but `GET /api/audit/` requires only
`documents.read`. Any signed-in user can read the full audit trail — including
who signed in, when, and from which IP — through the API.

### 6.3 ⚠️ Audit log is mutable

`audit_logs` rows are ordinary database rows. Anyone with database access can
alter or delete them. A hard guarantee needs append-only storage, row signing,
or shipping to an external log sink.

### 6.4 ⚠️ Secrets at rest

API keys live in `.env` and in the `settings` table **in plain text**. The
database file is unencrypted. Protect both with filesystem permissions and disk
encryption; consider a secrets manager for production.

> **Specific to this repository:** [`.env`](../../.env) currently contains a
> live Groq API key and is gitignored. Anyone taking this codebase over should
> rotate that key, because it has been distributed with the working tree.

### 6.5 ⚠️ No security headers

No CSP, HSTS, `X-Frame-Options` or `Referrer-Policy`. Add them at the reverse
proxy.

### 6.6 ⚠️ Rate-limit state is per-process

See §4.2.

### 6.7 ⚠️ Debug endpoints

`GET /api/settings/debug/azure` and `/api/search/test-semantic`,
`/test-fulltext` are diagnostic endpoints reachable in production. They are
permission-gated but should be reviewed before an external deployment.

### 6.8 ⚠️ SQLite foreign keys are not enforced

SQLite ignores foreign-key constraints unless `PRAGMA foreign_keys=ON` is set
per connection, which this application does not do. Referential integrity
depends on application code being correct.

---

## 7. Data flow to the AI provider

**What leaves the network** when an AI provider is configured:

| Feature | Sent |
|---|---|
| Classification | Up to `ai_text_limit` (16 000) characters of the document text, plus the filename, plus the existing doctype and correspondent names |
| Vision OCR | Page images, up to 20 pages, 4 MB each |
| RAG / assistant | The question and the **full text** of the retrieved documents |
| Studio AI | Up to 24 000 characters of the body |
| Embeddings | Nothing, with the default `local` provider — the ONNX model runs on the CPU. **With `openai` or `azure`, the enriched text is sent.** |

**Controls available:**

- Set `AI_PROVIDER` to a provider with an appropriate data agreement, or use
  Azure OpenAI inside your own tenant.
- Leave `embedding_provider: local` (the default) so nothing is sent for
  indexing.
- Set `ocr_engine: tesseract` so no page images are sent.
- Configure no API key at all: capture, storage, full-text search and the entire
  approval workflow still work.

**Assess this before go-live.** Document text is business-confidential and, with
the default configuration, it is transmitted to a third party.

---

## 8. Container and deployment hardening

Present in the shipped `Dockerfile`:

- Multi-stage build; the compiler toolchain does not reach the runtime image
- Runs as a **non-root** user (uid/gid 1000)
- Minimal runtime dependencies, apt caches removed
- `HEALTHCHECK` defined
- `PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`
- `TRUSTED_PROXY_IPS=127.0.0.1` by default

Recommended additions for production:

| Control | Why |
|---|---|
| TLS termination at a reverse proxy | The app serves plain HTTP |
| `ENVIRONMENT=production` | Turns on `Secure` cookies |
| A stable `SECRET_KEY` in the settings table | Otherwise CSRF tokens die on restart |
| Exact `CORS_ORIGINS` | Credentialed CORS |
| `TRUSTED_PROXY_IPS` = your proxy | Otherwise rate limiting buckets by the proxy's IP |
| Read-only root filesystem, writable `/app/data` only | Reduces blast radius |
| Security headers at the proxy | CSP, HSTS, frame options |
| Disk encryption on the data volume | Unencrypted database and documents |

---

## 9. Security checklist for go-live

- [ ] Rotate the Groq API key that shipped in `.env`
- [ ] `ENVIRONMENT=production` set (secure cookies)
- [ ] Stable `secret_key` and `jwt_secret_key` configured
- [ ] TLS in front of the application
- [ ] `CORS_ORIGINS` restricted to the real origin
- [ ] `TRUSTED_PROXY_IPS` set to the reverse proxy
- [ ] Security headers added at the proxy
- [ ] Data volume on encrypted storage
- [ ] Backups configured, and a restore actually tested
- [ ] Accounts issued only to people entitled to see **every** document (§6.1)
- [ ] Audit-log API exposure accepted or fixed (§6.2)
- [ ] AI data-flow assessment completed and signed off (§7)
- [ ] The first admin's password changed from whatever it was set up with
- [ ] Demo accounts removed if `seed_demo_data.py` was ever run
