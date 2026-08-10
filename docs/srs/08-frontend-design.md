# 08 · Frontend Design

> **Audience:** front-end developers, UX, QA.
> The interface is **vanilla JavaScript with no build step, no bundler, no CDN
> and no framework**. Everything in `frontend/ui/` is served as-is. What you
> read in the browser's Sources panel is what is in the repository.

---

## 1. Why no framework

| Decision | Reason |
|---|---|
| No bundler | Nothing to install, nothing to compile, nothing to go stale. Edit a file, reload. |
| No CDN | The product runs on an air-gapped network without changing anything |
| No framework | No upgrade treadmill, no version pinning across a five-year retention product |
| A shared shell instead | One 2 800-line `shell.js` supplies navigation, the API client, toasts, modals, the signature pad, the decision bar and the date system to all 16 pages |

The cost is manual DOM work and discipline. The benefit is that a developer who
has never seen the project can open `tasks.html`, read it top to bottom, and
understand the whole screen.

---

## 2. File layout

```
frontend/ui/
├── css/
│   ├── dms.css        design system — palette, type scale, components
│   └── studio.css     the editor: ribbon, paper, letterhead chrome
├── js/
│   ├── shell.js       the application shell  (2 780 lines)
│   ├── studio.js      the WYSIWYG editor     (1 723 lines)
│   └── viewer.js      document rendering, shared by detail + full screen
├── assets/brand/      HARMAN and vendor marks — SVG for web, PNG for PDF
├── login.html
├── studio.html · review.html · process.html · track.html · publish.html   ← the five steps
├── tasks.html · documents.html · document.html · viewer.html · search.html · assistant.html
└── templates.html · organization.html · audit.html · settings.html
```

---

## 3. Page routing

Declared in `UI_PAGES` (`app/main.py:234`). Every route except `/login` requires
a session; six are admin-only.

| Route | File | Step | Admin only |
|---|---|---|---|
| `/studio` | `studio.html` | 1 | |
| `/review` | `review.html` | 2 | |
| `/process` | `process.html` | 3 | ✔ |
| `/track` | `track.html` | 4 | |
| `/publish` | `publish.html` | 5 | ✔ |
| `/tasks` | `tasks.html` | | |
| `/documents` | `documents.html` | | |
| `/documents/detail` | `document.html` | | |
| `/documents/view` | `viewer.html` | | |
| `/search` | `search.html` | | |
| `/assistant` | `assistant.html` | | |
| `/templates` | `templates.html` | | ✔ |
| `/organization` | `organization.html` | | ✔ |
| `/audit` | `audit.html` | | ✔ |
| `/settings` | `settings.html` | | ✔ |
| `/login` | `login.html` | | 🔓 |

Pages are served with `Cache-Control: no-cache, must-revalidate` so a redeploy
is picked up immediately.

---

## 4. The shell — `js/shell.js`

An IIFE that exposes one global, `window.DMS`.

### 4.1 Public surface

```js
window.DMS = {
  workflow, placeSignatures, isAdmin, ready, combobox, markdown, designation,
  refreshDates, icon, api, toast, fmt, escapeHtml, confirmDanger,
  openOverlay, closeOverlays, initials, NAV, JOURNEY,
  flow, signaturePad, signatureMark, decide, renderJourney,
  templates, dir, peoplePicker, DEPARTMENTS, SLA_OPTIONS,
  get TEMPLATES() { … },
};
```

### 4.2 Page contract

A page declares itself with `data-` attributes on `<body>`, and the shell reads
them in `mount()`:

```html
<body data-page="track" data-title="Status & Tracking"
      data-crumb="Workflow" data-crumb-href="/process" data-step="4">
  <aside id="sidebar"></aside>
  <header id="topbar"></header>
  <div id="topbar-actions"> … page-specific buttons … </div>
  <div data-journey></div>
  <main> … </main>
</body>
```

`mount()` then:
1. Renders the sidebar for the active page.
2. Renders the topbar, and **moves** the page's own action nodes into it —
   moving rather than copying markup, so any handler or reference the page
   attached to them keeps working.
3. Renders the journey stepper when `data-step` is present, and marks the step
   reached.
4. Replaces every `<i data-icon="name">` with an inline SVG.
5. Wires the date system.
6. Loads the current user and the live badge counts.

`mount()` runs on `DOMContentLoaded`, or immediately if the document is already
parsed.

### 4.3 Icons

~90 inline SVG paths in an `ICONS` map. Every generated icon carries the `.ic`
class for a sane default size; component rules (`.btn svg`, `.tile-icon svg`,
`.badge svg`) are more specific and win, so an icon is never unsized wherever it
is dropped.

### 4.4 Navigation

Two menus, chosen by who signed in.

**`NAV_ADMIN`** — three groups, thirteen destinations:
- *Workflow*: the five journey steps
- *Find & do*: My Tasks (with a live count), All Documents, Search, Ask AI
- *Set up*: Approval Routes, People, Activity Log

Settings is deliberately **not** listed — it is reached by pressing your own
name at the foot of the menu, which is where an account's own preferences belong
and where people look for them.

**`NAV_MEMBER`** — what an approver sees:
- *My work*: My Tasks, Status & Tracking
- *Find*: All Documents, Search, Ask AI

> The default before the server answers is `NAV_MEMBER`. Growing a menu once
> identity is known reads as the product waking up; shrinking one reads as
> something being taken away.

### 4.5 The API client

`DMS.api` wraps `fetch` with four behaviours that matter:

1. **JSON by default.** A non-`FormData` body is stringified and gets
   `Content-Type: application/json`.
2. **CSRF, correctly.** The `csrf_token` cookie carries a **signed** token
   (`<token>.<hmac>`), but the server compares the header against the
   **unsigned** token. `csrfFromCookie()` strips the signature — sending the
   cookie value verbatim fails every write with 403. The freshest value from the
   `X-CSRF-Token` **response** header is kept for the next call.
3. **401 → `/login`**, except when already on `/login` (never bounce the login
   page back to itself).
4. **403 + "csrf" in the body → refresh the token and retry once.** A rotated
   token is recoverable and should not surface to the user.

Responses are parsed as JSON when the content type says so, otherwise as text.

### 4.6 Per-user browser storage

```js
function userKey(base)      // namespaces localStorage by the signed-in user
function clearUserStorage() // called on sign-out
```

Two people sharing a machine never see each other's drafts, filters or flow
state.

### 4.7 Dates — the IST contract

- Stored UTC, displayed **`DD-MM-YYYY` in IST**.
- `wireDates()` / `refreshDates()` / `istParts()` / `parseTime()` handle
  conversion and re-rendering.
- **Every date input spells the chosen date out underneath in day-month-year.**
  The one thing no web page can control is the little calendar box a browser
  draws for a date field — that follows the browser's own language setting — so
  `06-08` must never be left to read as June.

### 4.8 Shared components

| Component | Purpose |
|---|---|
| `toast(title, message, variant)` | Transient feedback |
| `openOverlay` / `closeOverlays` / `scrim()` | Modals and drawers |
| `confirmDanger(opts)` | Typed confirmation for destructive actions |
| `signaturePad(userName, userRole)` | Draw / type / upload, on a DPI-aware canvas; `typedToDataUrl` renders a typed name as an image |
| `signatureMark(sig, subtitle)` | Renders a stored signature with its name and designation |
| `decide(action, opts)` | The approve / reject / request-changes bar, including the signature step |
| `confirmReuse(sig)` | Offers a previously drawn signature rather than making the user redraw |
| `combobox(input, opts)` | Filter-as-you-type with keyboard navigation and *Add "…" as new* |
| `peoplePicker(host, opts)` | Multi-select assignees with department grouping and sign-authority awareness |
| `placeSignatures(workflowId)` | The drag-to-place editor over a rendered page image |
| `markdown(src, opts)` | Renders the assistant's answer — headings, tables, lists, inline code — and turns `[Doc N]` markers into links |
| `flow` | Journey progress state, persisted per user |
| `templates` | Approval-route templates, with `validate(tpl)` returning a list of problems |
| `dir` / `DEPARTMENTS` / `SLA_OPTIONS` | The organisation directory used to fill department, role and SLA options consistently everywhere |

### 4.9 Approval-route validation

`templates.validate(tpl)` returns the problems, empty when sound:

- a name, an owning department, at least one step;
- every step needs a name, a department, a role and a deadline;
- **at least one step must capture a signature, otherwise nothing is signed off.**

---

## 5. The five journey screens

| # | Screen | What it does |
|---|---|---|
| 1 | **Document Studio** (`studio.html`) | Start writing on a template, **or** drop files in. Recent tiles show the file's own first page, with Review · Edit · Open · Replace · Discard. Landing page for administrators. |
| 2 | **Review** (`review.html`) | Document on the left, what the AI read underneath, details on the right. Edit supplier (combobox with *add new*), document date (defaults to today in IST, spelled out), tags (Enter adds one, a comma adds several). Ends with **Confirm & set up approval**. |
| 3 | **Approval** (`process.html`) | Add steps, choose people, pick *Everyone must approve* or *Any one of them*, tick *Signature required*, set priority and SLA. Section 4 restates the whole route in plain words before it starts. |
| 4 | **Status & Tracking** (`track.html`) | *One at a time* — a document's full history with every decision, comment and signature. *All in one table* — every approval at once, with **Waiting on** naming only the people who have not yet signed. |
| 5 | **Publishing** (`publish.html`) | Only fully approved documents appear. Adjust placement, Preview signed, Publish, then export as PDF / Word / text or print. **Already published** lists what went out, with who approved it. |

---

## 6. Find & do

| Screen | What it does |
|---|---|
| **My Tasks** (`tasks.html`) | The approver's whole product. Each card shows the document, the step, the deadline and the decision bar. Landing page for non-administrators. |
| **All Documents** (`documents.html`) | Repository with view and supplier filters that highlight on hover and stay marked when chosen |
| **Document detail** (`document.html`) | Metadata, version history, relations, approval state, download, edit |
| **Viewer** (`viewer.html`) | Full-screen reader, driven by `viewer.js` |
| **Search** (`search.html`) | Keyword or semantic, with facets |
| **Ask AI** (`assistant.html`) | The answer is rendered as a document — headings, tables, bullets — and every `[Doc N]` marker links to the file the claim came from |

## 7. Set up (admin only)

| Screen | What it does |
|---|---|
| **Approval Routes** (`templates.html`) | Design and validate reusable routes |
| **People** (`organization.html`) | Users, departments, job titles, approve/sign authority |
| **Activity Log** (`audit.html`) | The audit trail, filterable |
| **Settings** (`settings.html`) | AI provider, models, limits, OCR paths, folders, backup |

---

## 8. The editor — `js/studio.js`

`contenteditable`-based WYSIWYG, roughly 1 700 lines.

| Concern | Implementation |
|---|---|
| **Paper** | The template spec drives the visible page: size, margins, header, side rail, watermark, footer — the same numbers the PDF renderer uses, in CSS `mm` |
| **Ribbon** | Bold, italic, headings, alignment, bullet and numbered lists, tables, images, page break, undo/redo |
| **Images** | Inserted from the library by **asset id**, never by path |
| **Signature** | Draw one and place it in the body |
| **AI panel** | Menu built from `GET /api/studio/ai/actions`, so it can never drift from the API. Result replaces the selection when the action declares `replaces: true`. |
| **Autosave** | Debounced `PUT /api/studio/drafts/{id}` |
| **Preview** | `POST /api/studio/preview` → the PDF in a new tab |
| **Publish** | `POST /api/studio/publish` with title, template, body and metadata |

> **What-you-see-is-what-you-get is a consequence of the architecture, not an
> effort.** One template definition, two renderers reading it — the browser
> canvas and ReportLab. Change a colour once and both follow.

---

## 9. Design system — `css/dms.css`

| Token group | Contents |
|---|---|
| Palette | Ink, quiet, faint, accent (`#00A7E4`), plus semantic danger / warn / success |
| Type | A single scale used across every screen |
| Components | `.btn`, `.card`, `.tile`, `.badge`, `.chip`, `.table`, `.field`, `.drawer`, `.modal`, `.toast`, `.stepper` |
| Layout | Sidebar + topbar + main, responsive down to tablet width |

`css/studio.css` adds the editor's own vocabulary: ribbon, paper, letterhead
chrome.

---

## 10. Front-end principles enforced in code

1. **Never offer a link that will silently redirect.** `isAdmin()` and the
   `data-admin-only` sweep both exist for this reason — the second is a one-time
   sweep, the first is for anything rendered later.
2. **Never offer an action the API will refuse.** Every step arrives with
   `can_act` and `blocked_reason` already resolved on the server.
3. **Nothing on screen is invented.** Badge counts come from the server on every
   page load; an empty log says it is empty.
4. **Move nodes, don't copy markup**, when relocating a page's action buttons —
   handlers survive.
5. **A refusal must say what to do about it**, not merely that it happened.
6. **Storage is per-user and cleared on sign-out.**

---

## 11. Browser support and accessibility

| Aspect | Position |
|---|---|
| Browsers | Modern evergreen. Uses `fetch`, `async/await`, template literals, `Object.assign`, optional chaining. No transpilation, therefore no IE11. |
| Responsive | Sidebar collapses; the tables scroll. Designed for desktop first — this is an approval product used at a desk. |
| Keyboard | Combobox and people-picker support arrow keys, Enter and Escape; overlays close on Escape |
| Screen readers | Semantic HTML and focus states are present. ⚠️ **No formal WCAG audit has been done and no conformance level is claimed.** |
| Print | Publishing offers a print path; the letterhead prints as rendered |

---

## 12. Legacy interface

[legacy-ui/](../../legacy-ui/) holds the retired upstream single-file interface
(`index.html`, `app.js`, `styles.css`) and, under `superseded/`, the screens that
were removed. **None of it is routed.** It is retained for reference only and
can be deleted once nobody needs to compare behaviour.
