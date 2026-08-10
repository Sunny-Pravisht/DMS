# HARMAN DMS — Software Requirements & Design Specification

Complete documentation for the HARMAN Document Management System: what it is,
what it must do, how it is built, and how to run it. Written so that a person
joining this project cold — from a business sponsor to a backend engineer — can
reach the level of detail they need without reading the code first.

> **⚠️ Two copies of the same content exist.** The authoritative version is the
> single standalone file
> **[../DMS-Project-Documentation.md](../DMS-Project-Documentation.md)**.
> The eleven chapter files in this folder hold the same material split up for
> file-by-file navigation. **Edit the standalone document; treat this folder as
> a convenience copy** — or delete this folder if you would rather keep only
> one. Keeping both in sync by hand will not work.

**Document set version:** 1.0
**Covers application version:** 1.1.0 (`app/main.py`)
**Last verified against source:** 2026-08-07

---

## How to read this

Pick your row. Each document is self-contained; the ones above it are context,
the ones below it are detail.

| If you are… | Read | Why |
|---|---|---|
| **Executive / sponsor** | [01 Introduction](01-introduction.md) → §1–§4 | The problem, the scope, the value, the boundaries |
| **Business analyst / process owner** | [01](01-introduction.md), [02 Functional Requirements](02-functional-requirements.md) | Every behaviour the system promises, numbered and testable |
| **Project manager** | [01](01-introduction.md), [02](02-functional-requirements.md) §Traceability, [11 Testing & Handover](11-testing-quality-and-handover.md) | Scope, coverage, known gaps, roadmap |
| **Solution architect** | [04 High-Level Design](04-high-level-design.md), [05 Data Model](05-data-model.md), [09 Security](09-security-design.md) | Components, boundaries, data, trust model |
| **Backend developer** | [05](05-data-model.md), [06 Low-Level Design](06-low-level-design.md), [07 API Reference](07-api-reference.md) | Module-by-module internals and every endpoint |
| **Frontend developer** | [08 Frontend Design](08-frontend-design.md), [07](07-api-reference.md) | Shell, screens, state, the contracts they call |
| **DevOps / SRE** | [10 Deployment & Operations](10-deployment-and-operations.md), [09](09-security-design.md) | Install, configure, deploy, back up, monitor |
| **QA** | [02](02-functional-requirements.md), [03 Non-Functional Requirements](03-non-functional-requirements.md), [11](11-testing-quality-and-handover.md) | What to test and what "correct" means |
| **Incoming dev team (handover)** | All of it, then [11 §Handover checklist](11-testing-quality-and-handover.md) | |

---

## Contents

| # | Document | Contents |
|---|---|---|
| 01 | [Introduction & Scope](01-introduction.md) | Purpose, business context, stakeholders, scope in/out, glossary, assumptions |
| 02 | [Functional Requirements](02-functional-requirements.md) | FR-1…FR-14 by module, user roles, use cases, business rules, traceability matrix |
| 03 | [Non-Functional Requirements](03-non-functional-requirements.md) | Performance, capacity, availability, usability, compliance, portability |
| 04 | [High-Level Design](04-high-level-design.md) | Architecture, layers, component catalogue, runtime flows, deployment topology |
| 05 | [Data Model](05-data-model.md) | ERD, all 22 tables field-by-field, lifecycle states, migrations, vector store |
| 06 | [Low-Level Design](06-low-level-design.md) | Every module: responsibility, algorithm, error handling, extension points |
| 07 | [API Reference](07-api-reference.md) | All 167 route declarations: method, path, auth, payload, response, errors |
| 08 | [Frontend Design](08-frontend-design.md) | Shell architecture, 16 screens, design system, state, editor internals |
| 09 | [Security Design](09-security-design.md) | AuthN/AuthZ, session & CSRF, rate limiting, file safety, audit, threat notes |
| 10 | [Deployment & Operations](10-deployment-and-operations.md) | Install, config precedence, CLI, Docker, backup/restore, monitoring, runbooks |
| 11 | [Testing, Quality & Handover](11-testing-quality-and-handover.md) | Test strategy, coverage, known gaps and risks, roadmap, handover checklist |

---

## One-paragraph summary

HARMAN DMS is a self-hosted document management system built on **FastAPI +
SQLAlchemy + SQLite/PostgreSQL**, with a **zero-build vanilla-JavaScript**
front end. It captures documents two ways — files dropped into a watched folder
or uploaded through the browser, and documents written in an in-app **Document
Studio** on letterhead templates. Captured text is extracted by a **vision model
or Tesseract OCR**, classified by an **LLM (Groq by default)**, and indexed into
**ChromaDB** for semantic search and retrieval-augmented question answering.
Each document can be routed through a **multi-step approval workflow** with
per-step signature requirements and any/all quorum rules; approved documents are
**published** with the collected signatures stamped onto the PDF, and every
version along the way is retained immutably.

---

## Conventions used in these documents

- `path/to/file.py:123` — a clickable reference to a source location.
- **FR-x.y** — a numbered functional requirement (see doc 02).
- **NFR-x** — a numbered non-functional requirement (see doc 03).
- ⚠️ — a known gap, limitation or risk. These are stated plainly rather than
  omitted; doc 11 collects them all in one register.
- Everything stated here was verified against the source tree. Where the code
  and an older document (e.g. the root `README.md`) disagree, **the code is
  treated as the truth** and the discrepancy is noted.
