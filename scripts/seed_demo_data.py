#!/usr/bin/env python
"""
Seed a working HARMAN Manufacturing scenario: people, documents, approvals.

Everything created here is *real* to the system - real users who can sign in,
real files on disk, real approval chains the engine will run. Nothing is a
fixture that only the demo understands, which is the point: if it works here,
it works.

What it creates
---------------
  6 people   one administrator plus five members across five departments,
             with deliberately different permissions so the difference between
             "can approve" and "can sign" is visible
  5 documents one per department, covering the three formats the product
             handles: PDF (composed on a letterhead), DOCX and TXT
  4 approvals in four different states - waiting on a member, part-signed,
             sent back for changes, and fully approved and ready to publish

    python scripts/seed_demo_data.py            # create anything missing
    python scripts/seed_demo_data.py --reset    # remove the demo data first
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db                      # noqa: E402
from app.models import (                                            # noqa: E402
    ApprovalWorkflow, Correspondent, Document, DocType, Signature, User,
)
from app.services import version_service, workflow_service as wf    # noqa: E402
from app.services.role_service import apply_role                    # noqa: E402
from app.services.doc_templates import get_template                 # noqa: E402
from app.services.docx_render import html_to_plain, render_docx     # noqa: E402
from app.services.pdf_render import html_to_text, render_pdf        # noqa: E402

STORAGE = ROOT / "data" / "storage"
DEMO_TAG = "harman-demo"          # how the reset finds what this script made

TODAY = datetime.now()
def days(n: int) -> str:
    return (TODAY + timedelta(days=n)).strftime("%d %b %Y")


# ---------------------------------------------------------------- the people

PEOPLE = [
    # username, name, email, department, title, approve, sign, admin
    ("r.menon", "Rahul Menon", "rahul.menon@harman.com",
     "Legal", "Head of Legal", True, True, False),
    ("s.iyer", "Sudha Iyer", "sudha.iyer@harman.com",
     "Finance", "Head of Finance", True, True, False),
    ("m.raghavan", "Meena Raghavan", "meena.raghavan@harman.com",
     "Finance", "AP Clerk", True, False, False),      # approves, cannot sign
    ("p.krishnan", "Prakash Krishnan", "prakash.krishnan@harman.com",
     "Operations", "Head of Operations", True, True, False),
    ("a.khan", "Ayesha Khan", "ayesha.khan@harman.com",
     "Procurement", "Procurement Lead", True, True, False),
    ("d.varma", "Divya Varma", "divya.varma@harman.com",
     "Human Resources", "HR Manager", True, False, False),  # approves, cannot sign
]

DEMO_PASSWORD = "Harman@2026"


# ------------------------------------------------------------- the documents
#
# Five documents that between them exercise everything the product does:
# a letterhead PDF, a vendor PDF, a controlled report, an editable DOCX and a
# plain-text plant note. Each is short enough to read on screen in a demo and
# specific enough to be believable.

DOCUMENTS = [
    {
        "key": "invoice",
        "format": "pdf",
        "template": "harman-letterhead",
        "title": "Supplier invoice HAR-INV-2026-0417 — Bharat Precision Components",
        "doctype": "Invoice",
        "correspondent": "Bharat Precision Components Pvt Ltd",
        "department": "Finance",
        "tags": ["invoice", "accounts-payable", "three-way-match"],
        "html": f"""
<h1>Tax invoice</h1>
<p class="doc-meta">Invoice HAR-INV-2026-0417 &nbsp;·&nbsp; Purchase order HAR/PO/2026/0331
 &nbsp;·&nbsp; Date: {days(-6)}</p>
<p><strong>Supplier:</strong> Bharat Precision Components Pvt Ltd, Plot 44, Peenya Industrial
Area, Bengaluru 560058 &nbsp;·&nbsp; GSTIN 29AABCB1429P1ZK</p>
<p><strong>Bill to:</strong> HARMAN International Industries, Electronic City Phase II,
Bengaluru 560100</p>

<h2>Goods supplied</h2>
<table><thead><tr><th>Line</th><th>Part number</th><th>Description</th><th>Qty</th>
<th>Rate (INR)</th><th>Amount (INR)</th></tr></thead>
<tbody>
<tr><td>1</td><td>HAR-SPK-4412</td><td>Speaker mounting bracket, powder coated</td><td>4,800</td>
<td>142.00</td><td>681,600.00</td></tr>
<tr><td>2</td><td>HAR-GSK-2210</td><td>Acoustic gasket, EPDM 3&nbsp;mm</td><td>4,800</td>
<td>38.50</td><td>184,800.00</td></tr>
<tr><td>3</td><td>HAR-FST-0090</td><td>M4 fastener kit</td><td>9,600</td>
<td>6.25</td><td>60,000.00</td></tr>
</tbody></table>

<h2>Amount payable</h2>
<table><tbody>
<tr><td>Taxable value</td><td>926,400.00</td></tr>
<tr><td>CGST 9%</td><td>83,376.00</td></tr>
<tr><td>SGST 9%</td><td>83,376.00</td></tr>
<tr><td><strong>Total payable</strong></td><td><strong>1,093,152.00</strong></td></tr>
</tbody></table>

<h2>Terms</h2>
<ul>
<li>Payment due 30 days from receipt, on or before {days(24)}.</li>
<li>Goods receipt note GRN-2026-1188 dated {days(-7)} refers.</li>
<li>Quantities are subject to three-way match against the purchase order.</li>
</ul>

<p>Please confirm receipt and approve for payment.</p>
<div class="sig-block" data-sig-block="1">
  <div class="sig-block__role">For Bharat Precision Components Pvt Ltd</div>
  <div class="sig-block__line"></div>
  <div class="sig-block__name">Authorised signatory</div>
  <div class="sig-block__role">Accounts</div>
</div>
""",
    },
    {
        "key": "purchase-order",
        "format": "pdf",
        "template": "maruti-suzuki",
        "title": "Purchase order MSIL/PO/2026/0142 — infotainment head units",
        "doctype": "Purchase order",
        "correspondent": "Maruti Suzuki India Limited",
        "department": "Procurement",
        "tags": ["purchase-order", "vendor", "maruti"],
        "html": f"""
<h1>Purchase order</h1>
<p class="doc-meta">PO number MSIL/PO/2026/0142 &nbsp;·&nbsp; Date: {days(-3)}
 &nbsp;·&nbsp; Delivery: {days(28)}</p>
<p>This order is placed by Maruti Suzuki India Limited on HARMAN International
Industries under the terms of master supply agreement MSA-2291.</p>

<h2>Ordered items</h2>
<table><thead><tr><th>Line</th><th>Part number</th><th>Description</th><th>Qty</th>
<th>Unit price (INR)</th></tr></thead>
<tbody>
<tr><td>1</td><td>HAR-IVI-9200</td><td>Infotainment head unit, 9-inch, Baleno variant</td>
<td>2,500</td><td>18,400.00</td></tr>
<tr><td>2</td><td>HAR-AMP-4400</td><td>4-channel amplifier module</td><td>2,500</td>
<td>6,250.00</td></tr>
<tr><td>3</td><td>HAR-HRN-1120</td><td>Wiring harness, model-specific</td><td>2,500</td>
<td>1,180.00</td></tr>
</tbody></table>

<h2>Conditions</h2>
<ul>
<li>Delivery in four equal weekly lots to Gurugram Plant, Gate 3.</li>
<li>Each lot must carry a certificate of conformance and the batch traceability sheet.</li>
<li>Incoming inspection per IATF 16949 sampling plan C. AQL 0.65 major, 1.5 minor.</li>
<li>Price is firm for the duration of this order. No escalation clause applies.</li>
<li>Payment 45 days from goods receipt and accepted inspection.</li>
</ul>

<h2>Escalation</h2>
<p>Any delay of more than three working days must be notified in writing to the
buyer named below before the scheduled despatch date.</p>

<div class="sig-block" data-sig-block="1">
  <div class="sig-block__role">For and on behalf of Maruti Suzuki India Limited</div>
  <div class="sig-block__line"></div>
  <div class="sig-block__name">Authorised signatory</div>
  <div class="sig-block__role">Procurement</div>
</div>
""",
    },
    {
        "key": "quality-report",
        "format": "pdf",
        "template": "harman-quality",
        "title": "Quality inspection report HAR/QA/2026/0288 — line 3, batch B-2026-0814",
        "doctype": "Quality report",
        "correspondent": "HARMAN International",
        "department": "Operations",
        "tags": ["quality", "iatf-16949", "line-3", "controlled"],
        "html": f"""
<h1>Quality inspection report</h1>
<p class="doc-meta">Report HAR/QA/2026/0288 &nbsp;·&nbsp; Line 3 &nbsp;·&nbsp;
Batch B-2026-0814 &nbsp;·&nbsp; Date: {days(-2)}</p>

<h2>Scope</h2>
<p>Final inspection of 1,200 infotainment head units produced on line 3 between
{days(-4)} and {days(-2)}, against drawing HAR-IVI-9200 rev. F and the control
plan in force.</p>

<h2>Sampling</h2>
<p>IATF 16949 sampling plan C applied. Sample size 125 units, AQL 0.65 major,
1.5 minor. Instruments calibrated and in date.</p>

<h2>Results</h2>
<table><thead><tr><th>Characteristic</th><th>Specification</th><th>Measured</th>
<th>Cpk</th><th>Result</th></tr></thead>
<tbody>
<tr><td>Fastener torque, display bezel</td><td>4.2 ± 0.3 Nm</td><td>4.19 – 4.27 Nm</td>
<td>1.62</td><td>Pass</td></tr>
<tr><td>Bezel gap, upper edge</td><td>0.80 ± 0.10 mm</td><td>0.78 – 0.86 mm</td>
<td>1.41</td><td>Pass</td></tr>
<tr><td>Audio output, 1&nbsp;kHz reference</td><td>−0.5 to +0.5 dB</td><td>−0.31 to +0.28 dB</td>
<td>1.88</td><td>Pass</td></tr>
<tr><td>Boot time, cold start</td><td>≤ 3.5 s</td><td>2.9 – 3.3 s</td>
<td>1.55</td><td>Pass</td></tr>
<tr><td>Cosmetic, front face</td><td>No visible scoring</td><td>2 units scored</td>
<td>—</td><td>Rework</td></tr>
</tbody></table>

<h2>Non-conformances</h2>
<ul>
<li>Two units showed light scoring on the front face, traced to a worn transfer
pad on station 4. The pad was replaced on {days(-2)} and the two units reworked
and re-inspected as conforming.</li>
<li>No functional non-conformances. No customer-affecting defects.</li>
</ul>

<h2>Disposition</h2>
<p>Batch B-2026-0814 is <strong>released to despatch</strong>. The transfer pad
replacement interval on station 4 is reduced from 5,000 to 3,500 cycles with
immediate effect.</p>

<div class="sig-block" data-sig-block="1">
  <div class="sig-block__role">For and on behalf of HARMAN International</div>
  <div class="sig-block__line"></div>
  <div class="sig-block__name">Quality Engineer, Manufacturing</div>
  <div class="sig-block__role">Line 3</div>
</div>
""",
    },
    {
        "key": "supply-agreement",
        "format": "docx",
        "title": "Supply agreement amendment 2 — Mahindra & Mahindra, MSA-2291",
        "doctype": "Contract",
        "correspondent": "Mahindra & Mahindra Limited",
        "department": "Legal",
        "tags": ["contract", "amendment", "mahindra", "legal-review"],
        "html": f"""
<h1>Amendment 2 to master supply agreement MSA-2291</h1>
<p class="doc-meta">Between HARMAN International Industries and Mahindra &amp; Mahindra
Limited &nbsp;·&nbsp; Effective: {days(14)}</p>

<h2>1. Purpose</h2>
<p>This amendment varies the volume commitment and the liability cap in master
supply agreement MSA-2291 dated 04 January 2026. All other terms are unchanged
and remain in full force.</p>

<h2>2. Volume commitment</h2>
<p>Clause 4.1 is deleted and replaced with the following:</p>
<blockquote>The buyer commits to a minimum annual volume of 28,000 units, revised
from 22,000 units. The commitment is measured over the contract year ending
31 March and is subject to the tolerance in clause 4.3.</blockquote>

<h2>3. Liability</h2>
<p>Clause 7.2 is amended so that the aggregate liability cap is raised from
fifty percent to seventy-five percent of the annual contract value, calculated
on the twelve months preceding the event giving rise to the claim.</p>

<h2>4. Price</h2>
<table><thead><tr><th>Band</th><th>Annual volume</th><th>Unit price (INR)</th></tr></thead>
<tbody>
<tr><td>A</td><td>Up to 24,000</td><td>18,400.00</td></tr>
<tr><td>B</td><td>24,001 – 32,000</td><td>17,850.00</td></tr>
<tr><td>C</td><td>Above 32,000</td><td>17,200.00</td></tr>
</tbody></table>

<h2>5. Term</h2>
<p>This amendment takes effect on {days(14)} and expires with the master
agreement on 31 March 2029 unless terminated earlier under clause 12.</p>

<h2>6. Signatures</h2>
<p>Signed by the duly authorised representatives of both parties.</p>

<div class="sig-block" data-sig-block="1">
  <div class="sig-block__role">For and on behalf of HARMAN International Industries</div>
  <div class="sig-block__line"></div>
  <div class="sig-block__name">Head of Legal</div>
  <div class="sig-block__role">Legal</div>
</div>
""",
    },
    {
        "key": "shift-handover",
        "format": "txt",
        "title": "Line 3 shift handover — night shift, downtime and containment",
        "doctype": "Maintenance log",
        "correspondent": "HARMAN International",
        "department": "Operations",
        "tags": ["shift-handover", "downtime", "line-3", "maintenance"],
        "html": f"""
<h1>Line 3 shift handover</h1>
<p class="doc-meta">Night shift, {days(-1)} 22:00 to 06:00 &nbsp;·&nbsp;
Shift supervisor: R. Shankar</p>

<h2>Output</h2>
<p>Planned 640 units. Produced 574 units. Shortfall 66 units, carried to the
morning shift.</p>

<h2>Downtime</h2>
<ul>
<li>01:20 – 02:05 (45 min) — station 4 transfer pad replaced after cosmetic
scoring was found on two units during in-process check. Planned maintenance
brought forward.</li>
<li>04:10 – 04:32 (22 min) — conveyor jam at the buffer, cleared without damage.
Third occurrence this week; maintenance ticket MNT-2026-0442 raised.</li>
</ul>

<h2>Quality</h2>
<ul>
<li>Two units quarantined at 01:15, reworked and released after re-inspection.</li>
<li>Torque audit at 03:00 within specification, 4.21 to 4.25 Nm.</li>
<li>No customer-affecting defects.</li>
</ul>

<h2>Materials</h2>
<p>Acoustic gasket HAR-GSK-2210 is at 1.5 days of cover. Bharat Precision
consignment against HAR/PO/2026/0331 is due {days(2)}. Escalate if it slips.</p>

<h2>For the morning shift</h2>
<ul>
<li>Recover the 66-unit shortfall before the 14:00 despatch cut-off.</li>
<li>Watch station 4 for the first hour after the pad change.</li>
<li>Chase MNT-2026-0442 with maintenance before the conveyor stops again.</li>
</ul>
""",
    },
]


# ------------------------------------------------------------- the approvals
#
# Four workflows, each left in a different state so every screen in the product
# has something real to show without anybody having to click through first.

APPROVALS = [
    {
        "document": "invoice",
        "name": "Invoice approval",
        "priority": "high",
        "department": "Finance",
        "retention": "Financial records, 8 years",
        "steps": [
            {"name": "Verify against the purchase order", "department": "Finance",
             "role": "AP Clerk", "who": "m.raghavan", "sign": False, "sla": "8 hours"},
            {"name": "Approve for payment", "department": "Finance",
             "role": "Head of Finance", "who": "s.iyer", "sign": True, "sla": "2 days"},
        ],
        # Step 1 already approved, so it sits with the signer.
        "advance": [{"step": 0, "action": "approve",
                     "comment": "Three-way match clean. GRN-2026-1188 and PO agree on all "
                                "three lines."}],
    },
    {
        "document": "purchase-order",
        "name": "Vendor order acceptance",
        "priority": "urgent",
        "department": "Procurement",
        "retention": "Procurement and tenders, 6 years",
        "steps": [
            {"name": "Commercial review", "department": "Procurement",
             "role": "Procurement Lead", "who": "a.khan", "sign": False, "sla": "1 day"},
            {"name": "Capacity confirmation", "department": "Operations",
             "role": "Head of Operations", "who": "p.krishnan", "sign": True, "sla": "2 days"},
        ],
        # Untouched: waiting on the first approver.
        "advance": [],
    },
    {
        "document": "quality-report",
        "name": "Quality release",
        "priority": "normal",
        "department": "Operations",
        "retention": "Statutory records, permanent",
        "steps": [
            {"name": "Operations review", "department": "Operations",
             "role": "Head of Operations", "who": "p.krishnan", "sign": False, "sla": "1 day"},
            {"name": "Release the batch", "department": "Operations",
             "role": "Head of Operations", "who": "p.krishnan", "sign": True, "sla": "1 day"},
        ],
        # Fully approved: this one lands in the publish queue.
        "advance": [
            {"step": 0, "action": "approve",
             "comment": "Cpk acceptable on every measured characteristic. Rework verified."},
            {"step": 1, "action": "approve", "sign": True,
             "comment": "Batch released to despatch. Pad interval change noted and actioned."},
        ],
    },
    {
        "document": "supply-agreement",
        "name": "Contract review and signature",
        "priority": "high",
        "department": "Legal",
        "retention": "Commercial contracts, 7 years",
        "steps": [
            {"name": "Legal review", "department": "Legal",
             "role": "Head of Legal", "who": "r.menon", "sign": False, "sla": "3 days"},
            {"name": "Commercial sign-off", "department": "Finance",
             "role": "Head of Finance", "who": "s.iyer", "sign": True, "sla": "2 days"},
        ],
        # Sent back, so the "changes requested" path has a live example.
        "advance": [
            {"step": 0, "action": "changes",
             "comment": "Clause 3 raises the liability cap to 75% but clause 4 still prices "
                        "against the old volume bands. Reconcile the two before this goes "
                        "to Finance."},
        ],
    },
]


# ---------------------------------------------------------------------- work


def ensure_people(db) -> dict[str, User]:
    made = {}
    for username, name, email, dept, title, approve, sign, admin in PEOPLE:
        user = db.query(User).filter(User.username == username).first()
        if user:
            # Keep permissions in step with this file, so re-running fixes drift.
            user.department, user.job_title = dept, title
            user.can_approve, user.can_sign, user.is_admin = approve, sign, admin
            db.commit()
            apply_role(db, user)
            made[username] = user
            print(f"  · {name} already exists")
            continue

        user = User(
            username=username, email=email, full_name=name,
            department=dept, job_title=title,
            can_approve=approve, can_sign=sign, is_admin=admin, is_active=True,
        )
        user.set_password(DEMO_PASSWORD)
        db.add(user)
        db.commit()
        db.refresh(user)

        # A role, so they can actually reach the documents they must approve.
        role = apply_role(db, user)

        made[username] = user
        print(f"  + {name:22} {dept:18} {role}")
    return made


def _lookup(db, model, name: str):
    row = db.query(model).filter(model.name == name).first()
    if not row:
        row = model(name=name)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def ensure_documents(db, author: User) -> dict[str, Document]:
    from app.models import Tag
    from app.services import media_service
    from app.utils.file_security import calculate_file_hash

    made = {}
    for spec in DOCUMENTS:
        existing = db.query(Document).filter(Document.title == spec["title"]).first()
        if existing:
            made[spec["key"]] = existing
            print(f"  · {spec['title'][:60]} already exists")
            continue

        html = spec["html"].strip()
        text = html_to_text(html)
        fmt = spec["format"]

        if fmt == "pdf":
            data = render_pdf(
                html=html, template_id=spec["template"], title=spec["title"],
                author=author.full_name or author.username,
                asset_resolver=media_service.resolver(db, author),
            )
            mime, suffix = "application/pdf", ".pdf"
        elif fmt == "docx":
            data = render_docx(html, title=spec["title"],
                               author=author.full_name or author.username,
                               subtitle="HARMAN Document Management System")
            mime = ("application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document")
            suffix = ".docx"
        else:
            data = html_to_plain(html, spec["title"]).encode("utf-8")
            mime, suffix = "text/plain", ".txt"

        correspondent = _lookup(db, Correspondent, spec["correspondent"])
        doctype = _lookup(db, DocType, spec["doctype"])

        folder = STORAGE / _safe(spec["correspondent"]) / TODAY.strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)

        document = Document(
            filename="", original_filename=f"{_safe(spec['key'])}{suffix}",
            file_hash="", file_path="", file_size=len(data), mime_type=mime,
            title=spec["title"], full_text=text,
            document_date=TODAY,
            correspondent_id=correspondent.id, doctype_id=doctype.id,
            origin="composed" if fmt == "pdf" else "uploaded",
            template_id=spec.get("template"),
            source_html=html,
            version="1.0",
            created_by=author.id,
            notes=f"Department: {spec['department']}",
            ocr_status="completed", ai_status="completed", vector_status="pending",
            processed_at=TODAY,
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        path = folder / f"{document.id}_{_safe(spec['key'])}{suffix}"
        path.write_bytes(data)
        document.file_path = str(path)
        document.filename = path.name
        document.file_hash = calculate_file_hash(path)

        for tag_name in spec["tags"] + [DEMO_TAG]:
            tag = _lookup(db, Tag, tag_name)
            if tag not in document.tags:
                document.tags.append(tag)

        db.commit()
        db.refresh(document)

        version_service.capture(db, document, author=author, version="1.0",
                                note="Initial capture")

        made[spec["key"]] = document
        print(f"  + {suffix[1:].upper():4} {spec['title'][:58]}")
    return made


def ensure_approvals(db, docs: dict[str, Document], people: dict[str, User],
                     author: User) -> None:
    for spec in APPROVALS:
        document = docs.get(spec["document"])
        if not document:
            continue

        if wf.active_for_document(db, document.id):
            print(f"  · {spec['name']} already running")
            continue

        steps = [{
            "name": s["name"],
            "department": s["department"],
            "role": s["role"],
            "assignee_ids": [people[s["who"]].id] if s.get("who") in people else [],
            "requires_signature": s["sign"],
            "sla": s["sla"],
        } for s in spec["steps"]]

        try:
            workflow = wf.create_workflow(
                db, document, author,
                name=spec["name"], priority=spec["priority"],
                department=spec["department"],
                retention_policy=spec["retention"],
                after_approval="File it and start the retention clock",
                steps=steps, start=True,
            )
        except wf.WorkflowError as exc:
            print(f"  ! {spec['name']}: {exc}")
            continue

        # Play the recorded decisions so each workflow lands in its state.
        for move in spec.get("advance", []):
            workflow = wf.load(db, workflow.id)
            step = workflow.steps[move["step"]]
            actor = step.assignees[0] if step.assignees else author
            try:
                wf.decide(
                    db, workflow, step, actor, move["action"],
                    comment=move.get("comment", ""),
                    reason=move.get("reason", ""),
                    signature=_demo_signature(actor) if step.requires_signature else None,
                )
            except wf.WorkflowError as exc:
                print(f"  ! {spec['name']} step {move['step'] + 1}: {exc}")
                break

        final = wf.load(db, workflow.id)
        current = wf.current_step(final)
        where = (f"waiting on {current.assignees[0].full_name}"
                 if current and current.assignees
                 else final.status.replace("_", " "))
        print(f"  + {spec['name']:34} {spec['priority']:7} → {where}")


def _demo_signature(user: User) -> dict:
    """
    A drawn signature, generated rather than shipped as a binary.

    Each person gets a slightly different stroke, seeded from their name, so
    the signatures on a document are visibly different people.
    """
    import base64
    import io
    import math

    from PIL import Image, ImageDraw

    seed = sum(ord(c) for c in (user.full_name or user.username))
    img = Image.new("RGBA", (560, 160), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)

    points = []
    for i in range(0, 480, 8):
        x = 40 + i
        y = 100 - 34 * math.sin((i + seed) / (26 + seed % 11)) \
                - 14 * math.sin((i + seed) / 9.0)
        points.append((x, y))
    d.line(points, fill=(10, 42, 61, 255), width=5, joint="curve")
    d.line([(40, 128), (500, 128)], fill=(10, 42, 61, 60), width=2)

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {
        "dataUrl": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
        "name": user.full_name or user.username,
        "method": "draw",
    }


def _safe(name: str) -> str:
    import re

    return (re.sub(r"[^A-Za-z0-9 _-]+", "", name).strip().replace(" ", "_")[:50]
            or "document")


def reset(db) -> None:
    """Remove what this script created, so it can be re-run from clean."""
    from app.models import DocumentVersion, Tag

    tag = db.query(Tag).filter(Tag.name == DEMO_TAG).first()
    documents = list(tag.documents) if tag else []

    for document in documents:
        for workflow in db.query(ApprovalWorkflow).filter(
                ApprovalWorkflow.document_id == document.id).all():
            db.delete(workflow)
        db.query(DocumentVersion).filter(
            DocumentVersion.document_id == document.id).delete()
        try:
            path = Path(document.file_path)
            if path.exists():
                path.unlink()
        except OSError:
            pass
        db.delete(document)

    db.commit()
    print(f"  - removed {len(documents)} demo document(s) and their approvals")

    for username, *_ in PEOPLE:
        user = db.query(User).filter(User.username == username).first()
        if user:
            db.query(Signature).filter(Signature.user_id == user.id).delete()
            db.delete(user)
    db.commit()
    print(f"  - removed {len(PEOPLE)} demo people")


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        if "--reset" in sys.argv:
            print("\nRemoving the demo data")
            reset(db)
            if "--only-reset" in sys.argv:
                return 0

        admin = db.query(User).filter(User.is_admin.is_(True)).first()
        if not admin:
            print("\nNo administrator exists yet. Sign in once to create one, then re-run.")
            return 1

        print("\nPeople")
        people = ensure_people(db)

        print("\nDocuments")
        docs = ensure_documents(db, admin)

        print("\nApprovals")
        ensure_approvals(db, docs, people, admin)

        print(f"""
Done.

  Sign in as any of these to see the member side of the product:

     {'username':<14} {'password':<14} what they may do
     {'-' * 14} {'-' * 14} {'-' * 40}""")
        for username, name, _e, dept, title, approve, sign, _a in PEOPLE:
            what = "approve and sign" if sign else "approve only, cannot sign"
            print(f"     {username:<14} {DEMO_PASSWORD:<14} {what}  ({title}, {dept})")

        print("""
  Meena Raghavan and Divya Varma deliberately cannot sign. Put either of them on
  a step marked "signature required" and the Studio will refuse it - that is the
  permission model working, not a bug.
""")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
