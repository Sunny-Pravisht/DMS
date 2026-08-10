# HARMAN DMS — how to test it, and how to demonstrate it

A single run-through that exercises every feature in the order the product is
meant to be used. Roughly 15 minutes at a walking pace.

---

## 0 · Before you start

```
.venv\Scripts\python.exe cli.py serve
```

Then open <http://127.0.0.1:8000>.

**Accounts.** All demo people share the password `Harman@2026`.

| Sign in as | Who they are | May approve | May sign |
|---|---|---|---|
| `Aryan` | System administrator (your own password) | yes | yes |
| `s.iyer` | Sudha Iyer · Head of Finance | yes | yes |
| `r.menon` | Rahul Menon · Head of Legal | yes | yes |
| `p.krishnan` | Prakash Krishnan · Head of Operations | yes | yes |
| `a.khan` | Ayesha Khan · Procurement Lead | yes | yes |
| `m.raghavan` | Meena Raghavan · AP Clerk | yes | **no** |
| `d.varma` | Divya Varma · HR Manager | yes | **no** |

The last two matter: they prove the product enforces the difference between
*approving* a document and *signing* it.

**To reset to a clean, known state at any time:**

```
.venv\Scripts\python.exe scripts\seed_demo_data.py --reset
```

That restores six people, five documents and four approvals in four different
states — in progress, approved, changes requested, and published.

---

## 1 · Document Studio — the two ways a document begins

Sign in as **Aryan**. You land on **Document Studio**.

**Write one.** Press **Start writing**. You get a blank page immediately. In the
side panel on the right:

* **Template** — switch letterhead; your words are untouched, only the paper changes
* **Images** — HARMAN and vendor marks, or browse your own
* **Signature** — draw one and place it in the document
* **AI** — summarise, rewrite, fix grammar, translate, or draft from an instruction

Press **Preview PDF** to see exactly what will be filed. The letterhead you see
on screen and the one in the PDF come from the same specification, so the
preview is the output rather than an impression of it.

**Or bring one in.** Drag a PDF onto **Drop files here**. Watch:

* a progress bar during the upload
* a **picture of the file's own first page**, so you can see you picked the right one
* **Review · Edit · Open · Replace · Discard** on the tile

**Open** opens in a new tab so you keep your place. **Edit** opens an uploaded
PDF in the same editor a written document uses.

> **Try this:** leave the Studio, then come back. The tiles are still there —
> the last four, newest first. Older ones live in All Documents.

---

## 2 · Review — confirm what was read

Press **Review** on a tile.

The document is on the left, what the AI read is underneath, the details are on
the right. Press **Edit** in Document details:

* **From / supplier** — press the chevron. Every supplier on file is listed,
  it filters as you type, and a name that does not exist offers *Add "…" as new*
* **Document date** — starts on today's date in India, with the date spelled out
  underneath in day-month-year so `06-08` can never be read as June
* **Tags** — type and press Enter. A comma adds several at once

Press **Confirm & set up approval**.

---

## 3 · Approval — who signs, and how many of them

This is the heart of the product.

Press **Add a step**, then **Choose people** and pick **three** people who can
sign. A choice appears:

* **Everyone must approve** — all three must act *(the default)*
* **Any one of them** — whoever gets there first decides

Section 4 restates it in plain words:

> Step 1 — Review: **Ayesha Khan, Prakash Krishnan and Rahul Menon** — *all 3 must approve*
> · While anyone still has to act, the document stays in Status & Tracking and cannot be published.

Tick **Signature required**, set the priority, press **Start approval**.

> **The rule worth demonstrating:** with *Everyone must approve*, the document
> reaches Publishing only after the **last** person signs. With *Any one of
> them*, the **first** signature is enough.

---

## 4 · My Tasks — approving as somebody else

Sign out. Sign in as **`a.khan`** (`Harman@2026`).

She lands straight on **My Tasks** — an approver has no use for the authoring
screens, so she does not get them.

Press **Approve**, draw a signature, confirm.

Now sign in as **`p.krishnan`**, then **`r.menon`**, and do the same.

**Watch what happens between each one.** After the first two the document is
still in progress, and it does **not** appear under Publishing. Only after the
third does it become ready to release.

> **The permission demo:** try assigning a signature step to **`m.raghavan`**.
> She may approve but may not sign, so the product will not let you put her on
> a step that requires one — an unworkable approval cannot be designed in the
> first place.

---

## 5 · Status & Tracking — where everything is

Back as **Aryan**, open **Status & Tracking**.

**One at a time** shows the chosen document's full history: every decision, who
made it, when, their comment and their signature.

**All in one table** shows every approval at once — document, status, priority,
**who is still to act**, step, signature, who started it, and the dates. Note
that *Waiting on* names only the people who have **not** yet signed, not
everyone assigned.

---

## 6 · Publishing — release it

Open **Publishing**. Only documents whose every approver has acted are here.

* **Adjust placement** — drag each signature to exactly where it belongs on the page
* **Preview signed** — see the stamped result before releasing it
* **Publish** — the signatures are stamped onto the PDF itself and a locked
  version is captured

Export as **PDF**, **Word** or **plain text**, or print it.

**Already published** lists the released record with its type, version, **who
approved it**, when it went out and who released it.

---

## 7 · Find & do

* **Download** — on any document's page or in the viewer. Works for every
  document, in its original format
* **Version history** — on a document's page. Every saved version is kept and
  can be re-read; restoring one writes a *new* version rather than rewinding,
  so nothing already approved is ever overwritten
* **All Documents** — filter by view or supplier; both highlight as you point and stay marked when chosen
* **Search** — plain keyword, or turn on semantic search to match by meaning ("payment terms" finds contracts that never use the phrase)
* **Ask AI** — ask a question across the repository. The answer comes back as a
  document — headings, tables, bullets — and every `[Doc 1]` marker is a link to
  the file the claim came from

---

## 8 · The shortest possible demonstration

If you have five minutes:

1. **Studio** → drop a PDF → the tile shows its first page
2. **Review** → the details were filled in for you
3. **Approval** → three signatories → *Everyone must approve*
4. Sign in as two of them and approve → **it is still not publishable**
5. Sign in as the third → **now it is**
6. **Publishing** → Preview signed → three signatures on the page → **Publish**

That is the whole product: capture, understand, decide, prove, release.

---

## Notes

**Dates.** Everything is displayed in India Standard Time as `DD-MM-YYYY`.
Stored timestamps stay UTC, which is what keeps them correct if the server ever
moves. The one thing no web page can control is the little calendar box a
browser draws for a date field — that follows the browser's own language
setting — which is why every date field spells the chosen date out underneath.

**AI keys.** Two Groq keys are supported. If the first is refused for quota, the
next request goes out on the second automatically. Set the second one here:

```
.env   →   GROQ_API_KEY_2=
```

Both slots currently hold the **same** key, which gives no extra headroom —
one account, one quota. Put a key from a **different** Groq account in
`GROQ_API_KEY_2` and restart the server to get the benefit.

If the daily allowance runs out with no second key, uploads still work: the file
is stored, its text extracted, indexed and searchable. Only the AI-written title
and summary are missing, so documents arrive named after their file.
