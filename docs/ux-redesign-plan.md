# UX redesign plan, from feature catalogue to guided journey

**Trigger:** CTO feedback after the first demo, *"the UI is written from a technical point of view;
we need a common-user point of view. The workflow must be simple and logically connected so we can
demo it to a prospective enterprise client. Management must understand it with ease."*

**Audience for the next demo:** business stakeholders at a prospective enterprise client, not engineers.

---

## 1. What is wrong today

| Problem | Evidence in the current build |
|---|---|
| **No starting point** | The app opens on a Dashboard full of metrics. A first-time viewer doesn't know what to click. |
| **IT vocabulary** | "Capture & Sources", "Records & Warehousing", "Integrations & APIs", "Retention", "Audit Trail". None of these are how a Finance or HR manager speaks. |
| **Features, not a story** | Thirteen sibling menu items in four groups. Each screen is complete on its own but nothing points to the next. |
| **The demo has to jump around** | To show one document end-to-end you must visit Capture → Documents → Document detail → Workflows → Approvals → Audit. Six screens, no thread between them. |
| **Missing what business people expect** | No reusable templates, no signature, no clearly-placed reject-with-reason. |
| **Unbranded** | Generic royal blue says nothing to an enterprise audience. |

---

## 2. Design principles for this pass

1. **One spine, four steps.** The product has a single memorable path. Everything else is a side road.
2. **Every screen ends with one obvious next action.** The presenter never hunts through a menu.
3. **Plain English.** If a Finance manager wouldn't say it, don't label it that.
4. **Show, don't configure.** Defaults are pre-filled by AI; the user *confirms* rather than *fills in*.
5. **Nothing is removed.** Technical capability is relocated to where a business user expects it,
   never deleted.
6. **State carries across screens.** The document you upload in step 1 is the document you see in
   steps 2, 3 and 4, so the demo feels like one continuous act, not four disconnected screens.

---

## 3. The demo narrative

> *"A vendor invoice arrives at the Finance team. Watch it go from an email attachment
> to an approved, signed, retained record, in four screens."*

| Step | Screen | What the audience sees | The one CTA |
|---|---|---|---|
| **1** | **Upload Document** | Drag the invoice in. Immediate ✓ *Uploaded successfully*, or ✗ with a **Re-upload** button if the wrong file went in. | **Review details →** |
| **2** | **Review & Confirm** | The system already read the document: title, vendor, date, amount, type, department, tags, related documents. Every field is editable inline. Wrong file? **Replace document**. | **Confirm & set up process →** |
| **3** | **Set Up Process** | Pick a ready-made **template** ("Invoice Approval, Finance") or build the chain. See exactly who it goes to, person, role or department hierarchy, with due dates. | **Start process →** |
| **4** | **Track Status** | A live journey: each step, who acted, **their signature**, when, and their comment. Rejections show in red with the reason. | **Open my tasks →** |

Then the supporting act:

| Screen | Role in the demo |
|---|---|
| **My Tasks** | Switch to the approver's seat. **Approve & Sign** (signature pad) / **Request Changes** / **Reject**, all three on the same bar, no hunting. |
| **Home** | The manager's view: *"3 documents need your signature"*, not *"pending_ocr: 4"*. |
| **Templates** | "You never build that chain twice." |
| Governance / Admin | Depth on demand, retention, records, activity log, people, connected systems. |

---

## 4. Information architecture, before and after

### Before (feature groups)

```
Workspace        Dashboard · Documents · Capture & Sources · Search · AI Assistant
Automation       Workflows · My Approvals
Governance       Retention · Records & Warehouse · Audit Trail
Administration   Organization · Integrations & APIs · Settings
```

### After (journey first, plain English)

```
START HERE          ← the numbered demo spine, always visible
  1 Upload Document
  2 Review & Confirm
  3 Set Up Process
  4 Track Status

MY WORK
  Home                    (was Dashboard, rewritten for a business reader)
  My Tasks                (was My Approvals, now with sign / changes / reject)
  All Documents
  Search
  Ask AI                  (was AI Assistant)

BUILD & REUSE
  Templates               NEW
  Process Designer        (was Workflows)

GOVERNANCE
  Retention & Archival    (was Retention)
  Records & Warehouse
  Activity Log            (was Audit Trail)

ADMINISTRATION
  People & Departments    (was Organization)
  Connected Systems       (was Integrations & APIs, now also hosts source connectors)
  Settings
```

### Where the old "Capture & Sources" content went, nothing lost

| Was on Capture & Sources | Now lives on |
|---|---|
| Drag-and-drop upload | **1 Upload Document**, the main event |
| Capture options (department, type, sensitivity, OCR toggles) | **1 Upload Document**, right rail |
| Watched-folder / "Process now" | **1 Upload Document**, right rail |
| Connected sources (ERP, CRM, mailbox, SharePoint…) | **1 Upload Document → "From connected systems"** tab, and **Connected Systems** |
| Processing queue | **1 Upload Document → "Processing" tab** |
| Low-confidence review queue | **2 Review & Confirm → "Needs review" list** (exactly where a person would look) |

---

## 5. New capabilities in this pass

### 5.1 Templates
A template captures a process so nobody rebuilds it: **steps, approvers (person / role / department),
SLA per step, signature required?, retention policy to apply on completion, required metadata**.

- **Templates** screen: gallery of cards by department, with usage counts.
- Used from **3 Set Up Process** as the first and default choice, "Start from a template".
- "Save as new template" at the end of building a custom chain.

### 5.2 Signature & approval
- **Signature pad** modal: **Draw** (canvas), **Type** (rendered in a script face), or **Upload** an image.
- Saved once per user, reused for later approvals (demo persists it locally).
- The signature is rendered in the document's journey, on the status card, and in the approval
  trail as *"Approved & signed by R. Menon · 31 Jul 2026, 11:04"* with the signature image beside it.

### 5.3 Decision bar, approve / request changes / reject
One consistent bar wherever a decision is made (My Tasks, Track Status, Document detail):

| Action | Colour | Requires |
|---|---|---|
| **Approve & Sign** | Brand blue, primary | Signature |
| **Request Changes** | Outline | A comment |
| **Reject** | Red | A reason (mandatory) + optional comment |

Rejections and change-requests appear in the journey in red/amber with the reason quoted, and route
the document back to the previous step.

---

## 6. Visual identity

A cool blue palette on white. It reads as enterprise software rather than a consumer app, and it
sits comfortably next to whatever brand a prospective client already uses.

| Token | Hex | Use |
|---|---|---|
| Signature blue | `#00A7E4` | Accent, active states, progress, charts, highlights |
| Deep blue | `#006499` | Primary buttons, links, headings on white (text-safe contrast) |
| Navy | `#0A2A3D` | Sidebar and dark surfaces, giving an enterprise feel without darkening the work area |
| White | `#FFFFFF` | Every content page stays white |
| Grey scale | `#FAFAFB` → `#16181D` | Structure, borders, text hierarchy |
| Red | `#E5484D` | Reject, overdue, legal hold, destructive only |

`#00A7E4` on white is only ~2.6:1, so it is never used for body text or as a fill behind white text.
Text and primary buttons use `#006499` (~5.6:1). The bright blue carries fills, rails and graphics.

The palette is chosen to sit comfortably alongside a prospective client's own brand. No third-party
logo or company name appears anywhere in the product.

---

## 7. Implementation order

1. **Design system.** Brand tokens; new components: journey stepper, decision bar, signature block,
   template card, assignee row, status pill with signer avatars; dark navy sidebar.
2. **Shell**, new nav IA, persistent journey stepper, `DMS.flow` state carried across steps
   (localStorage), signature-pad module, decision-bar module.
3. **Journey screens**, `upload` → `review` → `process` → `track`.
4. **Templates**, library + builder.
5. **Rework**, `home` (was dashboard), `tasks` (was approvals) with the decision bar and signatures;
   decision bar added to document detail.
6. **Carry over**, documents, search, assistant, process designer, retention, records, activity log,
   people, connected systems, settings: re-themed, relabelled, feature-complete.
7. **Routing**, new URLs; old URLs redirect so no link breaks.
8. **Verify**, backend test suite + headless-browser pass over every screen.

---

## 8. What remains front-end only

The workflow engine, templates, signatures and retention are **not yet backed by server modules**.
They are Phase 2 to 4 in the main README. In this build they run on `DMS.flow`, a small local state
store, layered on top of the **real** document the user uploaded. Upload, metadata, tags, search,
AI and users are genuinely live against the API.

This is stated on-screen so a demo never implies more than exists.
