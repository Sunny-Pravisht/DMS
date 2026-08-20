/* ==========================================================================
   Document Studio
   Create a document, or edit one that already exists. Same surface for both.

   Three ideas hold this together:

   1. The paper is real. The template spec that draws the letterhead here is
      the same JSON the server's PDF renderer reads, so the preview is not an
      approximation of the output - it is the output, drawn twice.

   2. Editing and creating are one act. Opening an existing document loads its
      body; opening nothing loads a blank one. Every tool - AI, images,
      signatures, templates - works identically either way.

   3. Saving joins the existing journey. A published document is an ordinary
      Document: it appears in the repository, it can be routed for approval,
      it is indexed and searchable. Nothing about it is a special case.
   ========================================================================== */
(function () {
  'use strict';

  const { api, icon, toast, escapeHtml, fmt, flow, signaturePad, confirmDanger } = DMS;

  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));

  const body = $('#body');
  const paper = $('#paper');
  const chrome = $('#chrome');
  const canvas = $('#canvas');

  /* ------------------------------------------------------------------ state */

  const state = {
    templates: [],
    template: null,          // the active spec
    assets: [],
    aiActions: [],
    draftId: null,
    documentId: null,        // set when editing an existing document
    sourceDocumentId: null,  // the document a save would supersede
    lossless: true,
    version: '1.0',
    imageSize: 'medium',
    zoom: 1,
    dirty: false,
    saving: false,
    savedAt: null,
    lastRange: null,         // the caret, remembered across panel clicks
  };

  const params = new URLSearchParams(location.search);

  /* ------------------------------------------------- letterhead rendering */

  /**
   * Draw the template's chrome onto the page.
   *
   * Every number here comes from the spec, in millimetres, so the browser and
   * ReportLab are laying out the same page. Nothing about the letterhead is
   * hard-coded in this file, which is why adding a template is a server-side
   * change only.
   */
  function paintChrome(spec) {
    const page = spec.page || {};
    const header = spec.header || { kind: 'none' };
    const footer = spec.footer || {};
    const rail = spec.siderail;
    const wm = spec.watermark;

    paper.style.setProperty('--pad-top', (page.margin_top || 25) + 'mm');
    paper.style.setProperty('--pad-bottom', (page.margin_bottom || 22) + 'mm');
    paper.style.setProperty('--pad-left', (page.margin_left || 22) + 'mm');
    paper.style.setProperty('--pad-right', (page.margin_right || 20) + 'mm');
    paper.style.setProperty('--ink', spec.ink || '#16181D');
    paper.style.setProperty('--accent-ink', spec.accent_dark || spec.accent || '#006499');

    let html = '';

    if (wm && wm.text) {
      html += '<div class="paper__watermark' + (wm.text.length > 8 ? ' paper__watermark--small' : '') +
        '" style="color:' + esc(wm.color || '#0A2A3D') + ';opacity:' + Number(wm.opacity || 0.05) + '">' +
        '<span>' + escapeHtml(wm.text) + '</span></div>';
    }

    if (rail) {
      const side = rail.side === 'right' ? 'right:0' : 'left:0';
      html += '<div class="paper__rail" style="' + side + ';width:' + Number(rail.width || 4) +
        'mm;background:' + esc(rail.color || '#00A7E4') + '"></div>';
    }

    if (header.kind && header.kind !== 'none') {
      const filled = header.kind === 'band' || header.kind === 'tinted';
      const logo = header.logo || {};
      html += '<div class="paper__header" style="height:' + Number(header.height || 26) + 'mm;' +
        (filled ? 'background:' + esc(header.background || '#FFFFFF') + ';' : '') + '">' +
        (logo.web ? '<img src="' + esc(logo.web) + '" alt="' + escapeHtml(spec.org || '') + '">' : '') +
        ((header.title || header.subtitle)
          ? '<div class="paper__header-text">' +
            (header.title
              ? '<div class="paper__header-title" style="color:' +
                esc(header.title_color || (filled ? '#FFFFFF' : '#16181D')) + '">' +
                escapeHtml(header.title) + '</div>' : '') +
            (header.subtitle
              ? '<div class="paper__header-sub" style="color:' +
                esc(header.subtitle_color || '#6B707A') + '">' +
                escapeHtml(header.subtitle) + '</div>' : '') +
            '</div>'
          : '') +
        (header.rule
          ? '<div class="paper__header-rule" style="background:' + esc(header.rule) + '"></div>' : '') +
        '</div>';
    }

    const lines = (footer.lines || []).slice(0, 2);
    if (lines.length || footer.page_numbers) {
      const band = footer.kind === 'band';
      html += '<div class="paper__footer' + (band ? ' paper__footer--band' : '') + '" style="' +
        (band ? 'background:' + esc(footer.background || '#00559B') + ';' : '') +
        'color:' + esc(footer.color || '#6B707A') + '">' +
        (footer.kind === 'rule' ? '<div class="paper__footer-rule"></div>' : '') +
        lines.map(l => '<div>' + escapeHtml(l) + '</div>').join('') +
        (footer.page_numbers !== false ? '<div class="paper__footer-page">Page 1</div>' : '') +
        '</div>';
    }

    chrome.innerHTML = html;
  }

  /** A miniature of a template, drawn from the same spec as the real thing. */
  function thumbnail(spec) {
    const header = spec.header || {};
    const footer = spec.footer || {};
    const rail = spec.siderail;
    const wm = spec.watermark;
    const filled = header.kind === 'band' || header.kind === 'tinted';
    const headerPct = header.kind && header.kind !== 'none'
      ? ((header.height || 26) / 297 * 100) : 0;

    return '<div class="tpl-thumb">' +
      (wm && wm.text
        ? '<div class="tpl-thumb__wm" style="color:' + esc(wm.color || '#0A2A3D') +
          ';opacity:' + (Number(wm.opacity || 0.05) * 4) + '">' + escapeHtml(wm.text.slice(0, 10)) + '</div>'
        : '') +
      (rail
        ? '<div class="tpl-thumb__rail" style="' + (rail.side === 'right' ? 'right:0' : 'left:0') +
          ';width:' + (Number(rail.width || 4) / 210 * 100) + '%;background:' + esc(rail.color) + '"></div>'
        : '') +
      (headerPct
        ? '<div class="tpl-thumb__band" style="height:' + headerPct + '%;' +
          (filled ? 'background:' + esc(header.background) : '') + '">' +
          (header.logo && header.logo.web
            ? '<img src="' + esc(header.logo.web) + '" alt="">' : '') +
          (header.rule
            ? '<div class="tpl-thumb__rule" style="bottom:0;background:' + esc(header.rule) + '"></div>' : '') +
          '</div>'
        : '') +
      '<div class="tpl-thumb__lines" style="top:' + (headerPct + 9) + '%">' +
        '<i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i>' +
      '</div>' +
      (footer.kind === 'band'
        ? '<div class="tpl-thumb__foot" style="background:' + esc(footer.background || '#00559B') + '"></div>'
        : '<div class="tpl-thumb__foot" style="border-top:1px solid var(--grey-200);height:6%"></div>') +
      '</div>';
  }

  /** Only ever used inside a style attribute we build ourselves. */
  function esc(v) {
    return String(v == null ? '' : v).replace(/["'<>();]/g, '');
  }

  /* --------------------------------------------------------------- editing */

  /**
   * execCommand is deprecated but it is also the only thing every browser
   * agrees on for contenteditable, and it is what the whole rich-text web
   * still runs on. The mode matters: presentational tags for bold and italic
   * so the PDF renderer sees <b> and <i>, CSS only for colour.
   */
  function exec(command, value, useCss) {
    body.focus();
    restoreRange();
    try { document.execCommand('styleWithCSS', false, !!useCss); } catch (e) { /* older engines */ }
    document.execCommand(command, false, value == null ? undefined : value);
    touch();
    syncToolbar();
  }

  function rememberRange() {
    const sel = window.getSelection();
    if (sel && sel.rangeCount && body.contains(sel.anchorNode)) {
      state.lastRange = sel.getRangeAt(0).cloneRange();
    }
  }

  function restoreRange() {
    if (!state.lastRange) return;
    // The remembered range points at nodes that may since have been replaced -
    // by a template switch, or by AI replacing the whole body. A stale range
    // throws, so drop it and let the caret fall wherever the browser puts it.
    if (!body.contains(state.lastRange.startContainer)) {
      state.lastRange = null;
      return;
    }
    try {
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(state.lastRange);
    } catch (e) {
      state.lastRange = null;
    }
  }

  /** Put a node where the caret is, then leave the caret after it. */
  function insertNode(node) {
    body.focus();
    restoreRange();
    const sel = window.getSelection();
    if (!sel.rangeCount || !body.contains(sel.anchorNode)) {
      body.appendChild(node);
    } else {
      const range = sel.getRangeAt(0);
      range.deleteContents();
      range.insertNode(node);
      range.setStartAfter(node);
      range.collapse(true);
      sel.removeAllRanges();
      sel.addRange(range);
    }
    rememberRange();
    touch();
  }

  function insertHtml(html) {
    const holder = document.createElement('div');
    holder.innerHTML = html;
    const frag = document.createDocumentFragment();
    let last = null;
    while (holder.firstChild) { last = holder.firstChild; frag.appendChild(last); }
    insertNode(frag);
    if (last && last.scrollIntoView) last.scrollIntoView({ block: 'nearest' });
  }

  /** Reflect the caret's context in the ribbon, so the toolbar never lies. */
  function syncToolbar() {
    const check = name => {
      try { return document.queryCommandState(name); } catch (e) { return false; }
    };
    [['bold', 'bold'], ['italic', 'italic'], ['underline', 'underline'],
     ['strikeThrough', 'strikeThrough'], ['justifyLeft', 'justifyLeft'],
     ['justifyCenter', 'justifyCenter'], ['justifyRight', 'justifyRight'],
     ['insertUnorderedList', 'insertUnorderedList'], ['insertOrderedList', 'insertOrderedList']]
      .forEach(([cmd]) => {
        const btn = document.querySelector('[data-cmd="' + cmd + '"]');
        if (btn) btn.classList.toggle('is-active', check(cmd));
      });

    let block = 'p';
    try {
      const value = (document.queryCommandValue('formatBlock') || '').toLowerCase();
      if (['h1', 'h2', 'h3', 'blockquote'].includes(value)) block = value;
    } catch (e) { /* not supported */ }
    $('#rb-style').value = block;
  }

  /* ----------------------------------------------------------- bookkeeping */

  function touch() {
    state.dirty = true;
    setSaveState('unsaved');
    updateStats();
    scheduleSave();
    body.dataset.empty = body.textContent.trim() ? 'false' : 'true';
  }

  function updateStats() {
    const text = body.innerText || '';
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    $('#stat-words').textContent = words + (words === 1 ? ' word' : ' words');
    // Matches the server's estimate so the two never disagree on screen.
    const pages = Math.max(1, Math.round(text.length / 2600 + 0.4));
    $('#stat-pages').textContent = pages + (pages === 1 ? ' page' : ' pages');
  }

  function setSaveState(kind, when) {
    const dot = $('#save-dot');
    const label = $('#save-label');
    dot.className = 'studio-status__dot' +
      (kind === 'saving' ? ' is-saving' : kind === 'saved' ? ' is-saved' : '');
    label.textContent =
      kind === 'saving' ? 'Saving…' :
      kind === 'saved' ? ('Draft saved ' + fmt.ago(when || new Date().toISOString())) :
      state.draftId ? 'Unsaved changes' : 'Not saved yet';
  }

  let saveTimer = null;
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveDraft(true), 2200);
  }

  function payload() {
    return {
      title: ($('#f-title').value || '').trim() || 'Untitled document',
      template_id: state.template ? state.template.id : 'blank',
      html: body.innerHTML,
      meta: {
        doctype_id: $('#f-doctype').value || '',
        correspondent_name: ($('#f-corr').value || '').trim(),
        department: $('#f-dept').value || '',
        document_date: $('#f-date').value || '',
        sensitivity: $('#f-sens').value || '',
        tags: ($('#f-tags').value || '').split(',').map(t => t.trim()).filter(Boolean),
      },
      source_document_id: state.sourceDocumentId || null,
    };
  }

  /** Autosaves are quiet; an explicit save says so. */
  async function saveDraft(silent) {
    if (state.saving) return;
    if (!body.textContent.trim() && !state.draftId) return;

    state.saving = true;
    setSaveState('saving');
    try {
      const data = state.draftId
        ? await api.put('/api/studio/drafts/' + state.draftId, payload())
        : await api.post('/api/studio/drafts', payload());
      state.draftId = data.id;
      state.dirty = false;
      state.savedAt = data.updated_at || new Date().toISOString();
      setSaveState('saved', state.savedAt);
      if (!silent) toast('Draft saved', 'Pick it up from the Studio at any time.');
    } catch (err) {
      setSaveState('unsaved');
      if (!silent) toast('Could not save the draft', String(err.message || err), 'danger');
    } finally {
      state.saving = false;
    }
  }

  /* -------------------------------------------------------------- template */

  function applyTemplate(id, opts) {
    opts = opts || {};
    const spec = state.templates.find(t => t.id === id) || state.templates[0];
    if (!spec) return;
    state.template = spec;
    paintChrome(spec);

    $$('#tpl-grid .tpl-card').forEach(card => {
      card.classList.toggle('is-active', card.dataset.tpl === spec.id);
    });

    // A template carries a sensible default department and type. Suggest them,
    // never overwrite a choice the author has already made.
    const meta = spec.meta || {};
    if (meta.department && !$('#f-dept').value) $('#f-dept').value = meta.department;

    if (!opts.silent) touch();
    fitPaper();
  }

  function renderTemplates() {
    const card = spec =>
      '<button class="tpl-card" data-tpl="' + escapeHtml(spec.id) + '">' +
        thumbnail(spec) +
        '<div class="tpl-card__body">' +
          '<div class="tpl-card__name">' + escapeHtml(spec.name) + '</div>' +
          (spec.org ? '<div class="tpl-card__org">' + escapeHtml(spec.org) + '</div>' : '') +
          '<div class="tpl-card__desc">' + escapeHtml(spec.description || '') + '</div>' +
        '</div>' +
      '</button>';

    $('#tpl-grid').innerHTML = state.templates.map(card).join('');
    renderHeadChips();
  }

  /**
   * Letterhead shortcuts on the start screen.
   *
   * The full gallery lives in the editor's side panel, where it belongs: you
   * cannot judge a letterhead until you can see your own words on it, and
   * switching later costs nothing because a template only re-skins the page.
   * These chips exist purely so somebody who already knows which one they
   * want can skip a click.
   */
  function renderHeadChips() {
    const host = $('#start-heads');
    if (!host) return;

    // Blank is the button above, not a chip.
    const heads = state.templates.filter(t => t.id !== 'blank');
    if (!heads.length) { $('#write-foot').hidden = true; return; }

    // Label by organisation, which is what people recognise - but two HARMAN
    // letterheads both labelled "HARMAN International" are two chips that look
    // like the same chip, so a shared name falls back to the template's own.
    const seen = {};
    heads.forEach(t => { seen[t.org || ''] = (seen[t.org || ''] || 0) + 1; });

    host.innerHTML = heads.map(t => {
      const label = (t.org && seen[t.org] === 1) ? t.org : t.name;
      return '<button class="chip" data-tpl="' + escapeHtml(t.id) + '" title="' +
        escapeHtml(t.description || t.name) + '">' +
        '<span class="chip__swatch" style="background:' + esc(t.accent || '#006499') + '"></span>' +
        escapeHtml(label) +
      '</button>';
    }).join('');
  }

  /* ---------------------------------------------------------------- images */

  function renderAssets() {
    const grid = $('#asset-grid');
    if (!state.assets.length) {
      grid.innerHTML = '<div class="t-sm muted-2" style="grid-column:1/-1">' +
        'No images yet. Browse your computer to add one.</div>';
      return;
    }
    grid.innerHTML = state.assets.map(a =>
      '<button class="asset" data-asset="' + escapeHtml(a.id) + '" title="' + escapeHtml(a.name) + '">' +
        '<span class="asset__thumb"><img src="' + escapeHtml(a.web_url || a.url) +
          '" alt="' + escapeHtml(a.name) + '"></span>' +
        '<span class="asset__name">' + escapeHtml(a.name) + '</span>' +
        (a.builtin ? '' :
          '<span class="asset__x" data-remove="' + escapeHtml(a.id) + '" title="Remove">' + icon('x') + '</span>') +
      '</button>').join('');
  }

  function insertAsset(asset) {
    // The src points at the API, not at a path, so the PDF renderer can resolve
    // it back to a file it is allowed to read.
    const img = document.createElement('img');
    img.src = asset.url;
    img.alt = asset.name;
    img.setAttribute('data-asset', asset.id);
    img.setAttribute('data-size', state.imageSize);

    const wrap = document.createElement('p');
    wrap.appendChild(img);
    insertNode(wrap);
    toast('Image placed', asset.name);
  }

  /* ------------------------------------------------------------- signature */

  function signatureBlock(sig) {
    const name = ($('#sig-name').value || '').trim() ||
      (sig && sig.name) || (document.querySelector('[data-user-name]') || {}).textContent || '';
    const role = ($('#sig-role').value || '').trim();
    const onBehalf = $('#sig-onbehalf').checked;
    const org = (state.template && state.template.org) || 'HARMAN International';

    const el = document.createElement('div');
    el.className = 'sig-block';
    el.setAttribute('data-sig-block', '1');
    el.innerHTML =
      (onBehalf ? '<div class="sig-block__role">For and on behalf of ' + escapeHtml(org) + '</div>' : '') +
      (sig ? '<img src="' + sig.dataUrl + '" alt="Signature of ' + escapeHtml(name) + '">' : '') +
      '<div class="sig-block__line"></div>' +
      '<div class="sig-block__name">' + escapeHtml(name || 'Name') + '</div>' +
      (role ? '<div class="sig-block__role">' + escapeHtml(role) + '</div>' : '') +
      '<div class="sig-block__role">' + escapeHtml(fmt.date(new Date().toISOString())) + '</div>';
    return el;
  }

  function renderSignaturePreview() {
    const sig = flow.signature();
    const host = $('#sig-preview');
    if (!sig) {
      host.innerHTML = '<div class="card card--flat card--pad" style="text-align:center">' +
        '<div class="t-sm muted">No signature on file yet.</div>' +
        '<div class="t-xs muted-2 mt-1">Draw, type or upload one and it is reused everywhere.</div>' +
        '</div>';
      return;
    }
    host.innerHTML = '<div class="card card--pad" style="text-align:center">' +
      '<img src="' + sig.dataUrl + '" alt="Your signature" ' +
      'style="max-height:80px;margin:0 auto;mix-blend-mode:multiply">' +
      '<div class="t-xs muted-2 mt-2">' + escapeHtml(sig.name || '') + ' · saved</div>' +
      '</div>';
  }

  /* -------------------------------------------------------------------- AI */

  function selectionText() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return '';
    if (!body.contains(sel.anchorNode)) return '';
    return sel.toString().trim();
  }

  function refreshScope() {
    const selected = selectionText();
    const scope = $('#ai-scope');
    scope.innerHTML = icon('info') + '<span>' + (selected
      ? 'Working on the ' + selected.split(/\s+/).length + ' selected words'
      : 'Working on the whole document') + '</span>';
  }

  function renderAiActions() {
    // The free-text box below already covers custom and draft.
    const shown = state.aiActions.filter(a => !['custom', 'draft'].includes(a.id));
    $('#ai-actions').innerHTML = shown.map(a =>
      '<button class="ai-action" data-ai="' + escapeHtml(a.id) + '">' + icon('magic') +
        '<span>' + escapeHtml(a.label) + '</span>' +
        '<span class="ai-action__tag">' + (a.replaces ? 'Replaces' : 'Adds') + '</span>' +
      '</button>').join('');
  }

  let aiBusy = false;

  async function runAi(action, extra) {
    if (aiBusy) return;
    extra = extra || {};

    const selected = selectionText();
    const scoped = !!selected;
    const source = selected || body.innerText;

    aiBusy = true;
    $('#ai-out').innerHTML =
      '<div class="ai-result"><div class="ai-result__head">' + icon('magic') +
      'Working…</div><div class="ai-result__body">' +
      '<div class="skeleton" style="height:12px;width:90%"></div>' +
      '<div class="skeleton mt-2" style="height:12px;width:80%"></div>' +
      '<div class="skeleton mt-2" style="height:12px;width:88%"></div>' +
      '</div></div>';

    try {
      const result = await api.post('/api/studio/ai', {
        action: action,
        text: source,
        instruction: extra.instruction || null,
        target: extra.target || null,
        title: ($('#f-title').value || '').trim(),
      });
      showAiResult(result, scoped);
    } catch (err) {
      $('#ai-out').innerHTML =
        '<div class="banner banner--danger mt-3">' + icon('alert') +
        '<div>' + escapeHtml(String(err.message || err).slice(0, 300)) + '</div></div>';
    } finally {
      aiBusy = false;
    }
  }

  /**
   * Nothing is applied automatically. The author reads what came back and
   * decides, which is the difference between an assistant and an accident.
   */
  function showAiResult(result, scoped) {
    const out = $('#ai-out');
    out.innerHTML =
      '<div class="ai-result">' +
        '<div class="ai-result__head">' + icon('magic') + escapeHtml(result.label) +
          '<span class="spacer"></span>' +
          '<span class="t-xs" style="font-weight:500">' +
            (scoped ? 'from your selection' : 'from the whole document') + '</span>' +
        '</div>' +
        '<div class="ai-result__body" data-ai-body></div>' +
        '<div class="ai-result__foot">' +
          '<button class="btn btn--primary btn--sm" data-apply="replace">' +
            (result.replaces && scoped ? 'Replace selection'
              : result.replaces ? 'Replace document' : 'Replace') + '</button>' +
          '<button class="btn btn--outline btn--sm" data-apply="after">Insert below</button>' +
          '<button class="btn btn--ghost btn--sm" data-apply="discard">Discard</button>' +
        '</div>' +
      '</div>';

    // The server already sanitised this; assigning it here is deliberate and
    // is what lets headings and lists survive into the document.
    out.querySelector('[data-ai-body]').innerHTML = result.html;

    out.querySelectorAll('[data-apply]').forEach(btn => {
      btn.onclick = () => {
        const how = btn.dataset.apply;
        if (how === 'discard') { out.innerHTML = ''; return; }

        if (how === 'replace' && scoped) {
          body.focus();
          restoreRange();
          document.execCommand('insertHTML', false, result.html);
        } else if (how === 'replace') {
          body.innerHTML = result.html;
        } else {
          body.insertAdjacentHTML('beforeend', result.html);
        }
        out.innerHTML = '';
        touch();
        toast(result.label + ' applied', 'Undo with Ctrl+Z if it is not what you wanted.');
      };
    });
  }

  /* ------------------------------------------------------------ zoom / fit */

  /**
   * The sheet is a fixed 210 mm wide. When the window is narrower than that,
   * scale it down rather than making the author scroll sideways to read their
   * own letter. Transform does not affect layout, so the wrapper's box is
   * resized to match or the canvas would scroll to the wrong place.
   */
  function fitPaper() {
    const wrap = $('#paper-wrap');
    if (!wrap) return;

    const available = canvas.clientWidth - 52;
    const natural = paper.offsetWidth || 794;
    const fit = Math.min(1, available / natural);
    const scale = Math.max(0.35, Math.min(2, fit * state.zoom));

    paper.style.transform = 'scale(' + scale + ')';
    wrap.style.width = (natural * scale) + 'px';
    wrap.style.height = (paper.offsetHeight * scale) + 'px';

    $('#zoom-label').textContent = Math.round(scale * 100) + '%';
  }

  /* ------------------------------------------------------------- publishing */

  async function publish(next) {
    const data = payload();
    if (!body.textContent.trim()) {
      toast('Nothing to save yet', 'Write something first.', 'danger');
      return;
    }

    const btn = $('#btn-publish');
    btn.disabled = true;
    btn.innerHTML = icon('clock') + 'Saving…';

    try {
      const result = await api.post('/api/studio/publish',
        Object.assign({}, data, { draft_id: state.draftId }));

      // Carry it into the four-step journey, so a written document and an
      // uploaded one arrive at Review, Process and Track the same way.
      flow.patch({ doc: { id: result.id, title: result.title }, confirmed: false });
      flow.complete(1);

      // Keep the Studio's tile strip pointing at what was actually saved. When
      // this was a revision of an uploaded file, the tile must follow the new
      // version rather than keep opening the superseded one.
      if (state.sourceDocumentId) flow.forgetUpload(state.sourceDocumentId);
      flow.rememberUpload({ id: result.id, name: result.title || 'Document', size: 0 });

      toast('Saved to the repository', result.message);

      if (next === 'process') location.href = '/process?id=' + encodeURIComponent(result.id);
      else if (next === 'review') location.href = '/review?id=' + encodeURIComponent(result.id);
      else location.href = '/documents/detail?id=' + encodeURIComponent(result.id);
    } catch (err) {
      toast('Could not save', String(err.message || err).slice(0, 200), 'danger');
      btn.disabled = false;
      btn.innerHTML = icon('check') + 'Save to repository';
    }
  }

  /** Ask where it should go next, rather than assuming. */
  function publishDialog() {
    const el = document.createElement('div');
    el.className = 'modal';
    const isRevision = !!state.sourceDocumentId;
    el.innerHTML =
      '<div class="modal__head">' +
        '<h3 class="t-h2">' + (isRevision ? 'Save as a new version' : 'Save to the repository') + '</h3>' +
        '<p class="t-sm muted mt-1">' + (isRevision
          ? 'The original stays exactly as it is. This is filed alongside it as version ' +
            escapeHtml(nextVersion(state.version)) + ', linked to it.'
          : 'The document is rendered to PDF, filed, indexed and made searchable.') +
        '</p>' +
      '</div>' +
      '<div class="modal__body">' +
        '<div class="stack-sm">' +
          '<button class="draft-row" data-next="detail">' +
            '<span class="tile-icon">' + icon('documents') + '</span>' +
            '<span class="draft-row__body"><span class="draft-row__title">Just file it</span>' +
            '<span class="draft-row__meta">Open the document afterwards</span></span>' +
            icon('chevronRight') + '</button>' +
          '<button class="draft-row" data-next="review">' +
            '<span class="tile-icon">' + icon('eye') + '</span>' +
            '<span class="draft-row__body"><span class="draft-row__title">File it and check the details</span>' +
            '<span class="draft-row__meta">Step 2 · confirm what was read</span></span>' +
            icon('chevronRight') + '</button>' +
          '<button class="draft-row" data-next="process">' +
            '<span class="tile-icon">' + icon('workflow') + '</span>' +
            '<span class="draft-row__body"><span class="draft-row__title">File it and send for approval</span>' +
            '<span class="draft-row__meta">Step 3 · choose who signs it</span></span>' +
            icon('chevronRight') + '</button>' +
        '</div>' +
      '</div>';

    document.body.appendChild(el);
    DMS.openOverlay(el);

    const close = () => { DMS.closeOverlays(); setTimeout(() => el.remove(), 260); };
    el.querySelectorAll('[data-next]').forEach(b => {
      b.onclick = () => { close(); publish(b.dataset.next); };
    });
  }

  function nextVersion(current) {
    const parts = String(current || '1.0').split('.');
    const major = parseInt(parts[0], 10) || 1;
    const minor = parseInt(parts[1], 10) || 0;
    return major + '.' + (minor + 1);
  }

  async function previewPdf() {
    const data = payload();
    if (!body.textContent.trim()) {
      toast('Nothing to preview yet', 'Write something first.', 'danger');
      return;
    }
    toast('Rendering the PDF…');
    try {
      const res = await fetch('/api/studio/preview', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': await api.fetchCsrf(),
        },
        body: JSON.stringify({ title: data.title, template_id: data.template_id, html: data.html }),
      });
      if (!res.ok) throw new Error((await res.text()).slice(0, 200));
      const url = URL.createObjectURL(await res.blob());
      window.open(url, '_blank', 'noopener');
      // The tab needs the blob long enough to load it, then it is dead weight.
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      toast('Could not render the PDF', String(err.message || err).slice(0, 200), 'danger');
    }
  }

  /* ------------------------------------------------------------------ boot */

  async function boot() {
    // Wait until the shell knows the signed-in user before reading/writing the
    // user-scoped workflow state. Without this, flow.clear() can run before
    // currentUserId is known and the old document pointer survives.
    if (DMS.ready) {
      try { await DMS.ready; } catch (e) { /* page can still render */ }
    }

    // /studio without an id is always the clean start screen. Existing
    // documents are opened only through /studio?id=<document_id>.
    const isExistingDocument = new URLSearchParams(location.search).has('id');
    if (!isExistingDocument) {
      flow.clear();
    }

    // Templates first: nothing else can render without a spec.
    const data = await api.safe('/api/studio/templates', { templates: [] });
    state.templates = data.templates || [];
    renderTemplates();

    fillPickers();
    loadAssets();
    loadAiActions();
    renderSignaturePreview();
    prefillSignatory();

    const isNewDocument = params.get('new') === '1';
    const docId = isNewDocument ? null : params.get('id');
    const draftId = isNewDocument ? null : params.get('draft');
    const templateId = isNewDocument ? null : params.get('template');

    // /studio?new=1 is an explicit request to start a completely new document.
    // Never reopen the document from the previous workflow just because an old
    // URL, browser history entry, or flow pointer is still present.
    if (isNewDocument) {
      flow.patch({ doc: null, confirmed: false });
      await showStart();
    } else if (docId) await openDocument(docId);
    else if (draftId) await openDraft(draftId);
    else if (templateId) await startFromTemplate(templateId);
    else await showStart();

    updateStats();
    fitPaper();
  }

  async function openDocument(id) {
    hideStart();
    $('#doc-state').textContent = 'Loading…';
    try {
      const src = await api.get('/api/studio/source/' + encodeURIComponent(id));
      state.documentId = id;
      state.sourceDocumentId = id;
      state.lossless = src.lossless;
      state.version = src.version || '1.0';

      $('#f-title').value = src.title || '';
      body.innerHTML = src.html || '<p></p>';
      applyTemplate(src.template_id, { silent: true });
      if (src.file_url && (src.file_mime === 'application/pdf' || /\.pdf$/i.test(src.file_url))) {
        const preview = document.createElement('div');
        preview.className = 'studio-file-preview';
        preview.innerHTML = '<div class="studio-file-preview__head">Original PDF preview <a href="' +
          escapeHtml(src.file_url) + '" target="_blank" rel="noopener">Open PDF</a></div>' +
          '<iframe title="Original PDF preview" src="' + escapeHtml(src.file_url) + '"></iframe>';
        body.prepend(preview);
      }

      const meta = src.meta || {};
      if (meta.doctype_id) $('#f-doctype').value = meta.doctype_id;
      if (meta.correspondent_name) $('#f-corr').value = meta.correspondent_name;
      if (meta.document_date) $('#f-date').value = String(meta.document_date).slice(0, 10);
      if ((meta.tags || []).length) $('#f-tags').value = meta.tags.join(', ');

      $('#doc-state').textContent = 'Editing v' + state.version;
      $('#doc-state').className = 'badge badge--accent';
      $('#btn-publish').innerHTML = icon('check') + 'Save as v' + nextVersion(state.version);

      $('#lineage').innerHTML =
        '<div class="rail__title">Version</div>' +
        '<p class="rail__hint">Saving files a new version and links it to the original. ' +
        'Nothing already approved is ever overwritten.</p>' +
        '<div class="row"><span class="version__tag">v' + escapeHtml(state.version) + '</span>' +
        icon('arrowRight') +
        '<span class="version__tag" style="background:var(--blue-100)">v' +
        escapeHtml(nextVersion(state.version)) + '</span></div>' +
        '<a class="btn btn--ghost btn--sm mt-2" href="/documents/detail?id=' +
        encodeURIComponent(id) + '">' + icon('external') + 'Open the original</a>';

      if (src.notice) {
        // Say plainly that this is a conversion, not a round trip.
        showNotice(src.notice);
      }
      updateStats();
    } catch (err) {
      toast('Could not open that document', String(err.message || err), 'danger');
      await showStart();
    }
  }

  function showNotice(text) {
    const banner = document.createElement('div');
    banner.className = 'banner';
    banner.style.margin = '0 14px 0';
    banner.innerHTML = icon('info') + '<div>' + escapeHtml(text) +
      '</div><button class="icon-btn" data-dismiss>' + icon('x') + '</button>';
    canvas.parentNode.insertBefore(banner, canvas);
    banner.querySelector('[data-dismiss]').onclick = () => banner.remove();
  }

  async function openDraft(id) {
    hideStart();
    try {
      const draft = await api.get('/api/studio/drafts/' + encodeURIComponent(id));
      state.draftId = draft.id;
      state.sourceDocumentId = draft.source_document_id || null;
      $('#f-title').value = draft.title || '';
      body.innerHTML = draft.html || '<p></p>';
      applyTemplate(draft.template_id, { silent: true });

      const meta = draft.meta || {};
      if (meta.doctype_id) $('#f-doctype').value = meta.doctype_id;
      if (meta.correspondent_name) $('#f-corr').value = meta.correspondent_name;
      if (meta.department) $('#f-dept').value = meta.department;
      if (meta.document_date) $('#f-date').value = meta.document_date;
      if (meta.sensitivity) $('#f-sens').value = meta.sensitivity;
      if ((meta.tags || []).length) $('#f-tags').value = meta.tags.join(', ');

      $('#doc-state').textContent = 'Draft';
      setSaveState('saved', draft.updated_at);
      updateStats();
    } catch (err) {
      toast('Could not open that draft', String(err.message || err), 'danger');
      await showStart();
    }
  }

  async function startFromTemplate(id) {
    hideStart();
    applyTemplate(id, { silent: true });
    try {
      const starter = await api.get('/api/studio/templates/' + encodeURIComponent(id) + '/starter');
      body.innerHTML = starter.html || '<p></p>';
    } catch (e) {
      body.innerHTML = '<p></p>';
    }

    const spec = state.template;
    if (spec && spec.meta && spec.meta.doctype) {
      const select = $('#f-doctype');
      const match = Array.from(select.options)
        .find(o => o.textContent.toLowerCase() === spec.meta.doctype.toLowerCase());
      if (match) select.value = match.value;
    }
    // Today in India, not in UTC. Past 05:30 IST the two are the same date, but
    // before it toISOString() hands back yesterday.
    $('#f-date').value = fmt.today();
    $('#doc-state').textContent = 'New document';
    body.dataset.empty = body.textContent.trim() ? 'false' : 'true';
    updateStats();
    body.focus();
  }

  /**
   * The start screen, which is also the product's home.
   *
   * Everything on it is either a way to begin a document or a true statement
   * about this person's work. No counter is estimated and no panel is shown
   * unless it has something to say.
   */
  async function showStart() {
    $('#start').hidden = false;
    // The editor's own actions mean nothing on the start screen.
    editorActions(false);

    // Neither a greeting nor a workflow summary is fetched any more. What is
    // waiting on this person is counted on the menu, by the shell, on every
    // screen - not restated here in banners that had to be dismissed by
    // reading them.
    //
    // Nor is a list of recent documents: the tile strip below is that list,
    // and the repository screen is where a longer one belongs.
    const list = await api.safe('/api/studio/drafts', { drafts: [] });

    renderDrafts(list.drafts || []);
    restoreIntake();

    // "Add a file" in the New menu arrives with #add, meaning: I already know
    // I am uploading. Put the cursor where the file goes.
    if (location.hash === '#add') {
      const zone = $('#dropzone');
      zone.scrollIntoView({ block: 'center', behavior: 'smooth' });
      zone.focus({ preventScroll: true });
    }
  }

  function renderDrafts(drafts) {
    if (!drafts.length) { $('#start-drafts').hidden = true; return; }

    $('#start-drafts').hidden = false;
    $('#draft-count').textContent = drafts.length + (drafts.length === 1 ? ' draft' : ' drafts');
    $('#draft-list').innerHTML = drafts.map(d =>
      '<button class="draft-row" data-draft="' + escapeHtml(d.id) + '">' +
        '<span class="tile-icon">' + icon('compose') + '</span>' +
        '<span class="draft-row__body">' +
          '<span class="draft-row__title">' + escapeHtml(d.title || 'Untitled document') + '</span>' +
          '<span class="draft-row__meta">Edited ' + fmt.ago(d.updated_at) + ' · ' +
            d.pages + (d.pages === 1 ? ' page' : ' pages') + '</span>' +
        '</span>' +
        '<span class="icon-btn is-danger" data-drop="' + escapeHtml(d.id) + '">' + icon('trash') + '</span>' +
        icon('chevronRight') +
      '</button>').join('');
  }

  /* ---------------------------------------------------------------- intake

     Bringing a file in used to be its own screen. It is now part of this one,
     because the two halves of "add a file" - choosing it and checking you
     chose the right one - belong together. Each file becomes a card showing a
     picture of its own first page, and everything you might want to do about
     a wrong file is on that card.
  */

  // Keyed by a local id so a card can be found again while its upload is in
  // flight, before the server has told us the document id.
  const intake = new Map();
  let intakeSeq = 0;

  function intakeAdd(files) {
    if (!files || !files.length) return;
    $('#intake').hidden = false;
    Array.from(files).forEach(file => {
      const key = 'f' + (++intakeSeq);
      intake.set(key, { key: key, file: file, name: file.name, size: file.size,
                        state: 'uploading', progress: 12, fresh: true });
      renderIntake();
      uploadOne(key);
    });
  }

  /**
   * Put back the tiles for whatever this person last brought in.
   *
   * Uploading a file, stepping into Review and pressing Back used to land on
   * an empty Studio with no trace of the file - which reads as "it did not
   * work". The ids are remembered locally; everything shown is re-read from
   * the server, so anything deleted since is simply dropped rather than shown
   * as a tile that leads nowhere.
   */
  async function restoreIntake() {
    const remembered = flow.recentUploads();
    if (!remembered.length) return;

    const docs = await Promise.all(remembered.map(e =>
      api.safe('/api/documents/' + encodeURIComponent(e.id), null)));

    for (let n = 0; n < remembered.length; n += 1) {
      const entry = remembered[n];
      const doc = docs[n];
      if (!doc) { flow.forgetUpload(entry.id); continue; }   // gone since

      const workflow = await DMS.workflow.forDocument(doc.id);
      if (workflow && workflow.status === 'published') {
        flow.forgetUpload(entry.id);
        continue;
      }

      const key = 'r' + (++intakeSeq);
      intake.set(key, {
        key: key,
        docId: doc.id,
        name: doc.original_filename || doc.filename || entry.name || 'Document',
        title: doc.title || entry.name,
        size: doc.file_size || entry.size || 0,
        state: 'ready',
        fresh: false,
      });
    }

    if (intake.size) renderIntake();
  }

  async function uploadOne(key) {
    const item = intake.get(key);
    if (!item) return;

    const form = new FormData();
    form.append('file', item.file);

    try {
      const res = await api.upload('/api/documents/upload', form, fraction => {
        // Move only the bar. Re-rendering the whole list on every progress
        // event would tear down the card being looked at.
        item.progress = Math.max(6, Math.round(fraction * 100));
        const bar = document.querySelector('[data-shot="' + item.key + '"] .filecard__progress i');
        if (bar) bar.style.width = item.progress + '%';
      });
      item.progress = 100;

      // The same bytes are already filed. Show that copy rather than making a
      // second record of it, and do not offer Discard for a document this
      // upload did not create.
      if (res && res.status === 'duplicate' && res.document_id) {
        item.docId = res.document_id;
        item.title = res.filename || item.name;
        item.state = 'duplicate';
        renderIntake();
        return;
      }

      item.state = 'reading';
      renderIntake();

      const doc = await findUploaded((res && res.filename) || item.file.name);
      if (!intake.has(key)) return;          // discarded while it was uploading
      if (doc) {
        item.docId = doc.id;
        item.title = doc.title || item.name;
        item.state = 'ready';
        // Carry the newest one into step 2 so Review opens on it.
        flow.patch({ doc: { id: doc.id, title: item.title }, confirmed: false });
        flow.complete(1);
        // And keep it on this screen, so coming back from step 2 still shows
        // what was brought in.
        flow.rememberUpload({ id: doc.id, name: item.name, size: item.size });
      } else {
        // Stored, but the record has not appeared yet. Say exactly that
        // instead of implying the file is lost or that it is ready.
        item.state = 'stored';
      }
    } catch (err) {
      item.state = 'failed';
      item.error = String(err.message || err).slice(0, 120);
    }
    renderIntake();
  }

  /**
   * Match the upload to the Document row the server just created.
   *
   * Storing a file and indexing it are separate steps, so the record does not
   * exist for a second or two after the upload returns. `stored` is the name
   * the server actually filed it under - uploads are sanitised, and a clash
   * gets a "_1" suffix - which is what the Document row carries, so the match
   * is exact rather than a guess at which recent row is ours.
   */
  async function findUploaded(stored) {
    const claimed = new Set(
      Array.from(intake.values()).map(i => i.docId).filter(Boolean));

    for (let attempt = 0; attempt < 12; attempt++) {
      const list = await api.safe('/api/documents/?limit=10', []);
      const docs = (Array.isArray(list) ? list : []).filter(d => !claimed.has(d.id));
      const hit = docs.find(d => d.original_filename === stored || d.filename === stored);
      if (hit) return hit;
      await new Promise(r => setTimeout(r, 700));
    }
    return null;
  }

  const FILE_GLYPH = { pdf: 'file', doc: 'file', docx: 'file', xls: 'grid', xlsx: 'grid',
                       txt: 'file', png: 'image', jpg: 'image', jpeg: 'image' };

  /**
   * The tiles, in the order they should be read.
   *
   * Files added in this visit come first, in the order they were dropped, then
   * the ones remembered from last time, newest first. Dropping a file that is
   * already remembered would otherwise show it twice - once as a restored tile
   * and once as the duplicate the server just reported - so the live card wins
   * and the restored one is dropped.
   */
  function intakeItems() {
    const all = Array.from(intake.values());
    const ordered = all.filter(i => i.fresh).concat(all.filter(i => !i.fresh));

    const seen = new Set();
    return ordered.filter(i => {
      if (!i.docId) return true;                 // still uploading, no id yet
      if (seen.has(i.docId)) { intake.delete(i.key); return false; }
      seen.add(i.docId);
      return true;
    });
  }

  function renderIntake() {
    const items = intakeItems();
    $('#intake').hidden = !items.length;
    if (!items.length) {
      // Hiding the section is not enough: the cards would still be in the
      // document, and the next file added would flash the discarded one.
      $('#intake-list').innerHTML = '';
      $('#intake-next').hidden = true;
      return;
    }

    const failed = items.filter(i => i.state === 'failed').length;
    const dupes = items.filter(i => i.state === 'duplicate').length;
    const fresh = items.filter(i => i.fresh);

    // The heading stays "Recent documents" either way; only the line under it
    // changes, because checking a file you dropped a second ago and returning
    // to one you dropped yesterday are different jobs.
    $('#intake-hint').textContent = fresh.length
      ? 'Check you brought in the right ones, then take one on to review.'
      : 'The last few you brought in. Anything older is in All Documents.';

    $('#intake-count').textContent =
      items.length + (items.length === 1 ? ' file' : ' files') +
      (dupes ? ' · ' + dupes + ' already here' : '') +
      (failed ? ' · ' + failed + ' failed' : '');

    $('#intake-list').innerHTML = items.map(card).join('');

    items.forEach(i => { if (i.docId) loadShot(i); });

    // The bar along the bottom announces an arrival, so it belongs to files
    // added just now. Restored tiles carry their own Review button instead.
    const first = fresh.find(i => i.state === 'ready');
    $('#intake-next').hidden = !first;
    if (first) {
      $('#intake-next-name').textContent = first.title || first.name;
      const reviewUrl = '/review?id=' + encodeURIComponent(first.docId);
      $('#btn-intake-next').href = reviewUrl;
      // Keep the selected document in the URL immediately. This avoids losing
      // it if the browser follows the link while the shell is still finishing
      // its user/session initialization.
      $('#btn-intake-next').dataset.reviewUrl = reviewUrl;
    }
  }

  // Only these can be pictured: the server renders PDFs with PDFium and scales
  // images down. Word, Excel and text would need an office suite, so they keep
  // the typed glyph and are never asked for a picture at all.
  const PICTURABLE = /\.(pdf|png|jpe?g|gif|webp|bmp|tiff?)$/i;

  /**
   * Load the first-page picture into a card, out of band.
   *
   * A Document row is created before its file has finished being filed, so the
   * first few requests legitimately 404. Because the file type already tells
   * us whether a picture will ever exist, a 404 here means "not yet" and is
   * worth waiting out - up to about a minute, which covers a slow OCR and AI
   * pass on a large scan.
   */
  function loadShot(item, attempt) {
    attempt = attempt || 0;
    if (item.noShot || !PICTURABLE.test(item.name)) return;

    const host = document.querySelector('[data-shot="' + item.key + '"]');
    if (!host || host.dataset.loaded) return;

    const img = new Image();
    img.alt = 'First page of ' + item.name;
    img.onload = () => {
      const now = document.querySelector('[data-shot="' + item.key + '"]');
      if (!now || now.dataset.loaded) return;
      now.dataset.loaded = '1';
      // Keep the badge and the progress bar; only the placeholder goes.
      const glyph = now.querySelector('.filecard__glyph');
      if (glyph) glyph.remove();
      now.insertBefore(img, now.firstChild);
    };
    img.onerror = () => {
      if (attempt >= 24 || !intake.has(item.key)) { item.noShot = true; return; }
      setTimeout(() => loadShot(item, attempt + 1), attempt < 6 ? 900 : 2500);
    };
    // The cache-buster stops the browser reusing an earlier 404.
    img.src = '/api/documents/' + encodeURIComponent(item.docId) +
      '/thumbnail?t=' + attempt;
  }

  const BADGES = {
    uploading: '<span class="badge">Uploading…</span>',
    reading:   '<span class="badge">Reading…</span>',
    ready:     '<span class="badge badge--accent">' + icon('check') + 'Ready</span>',
    stored:    '<span class="badge">Stored · still indexing</span>',
    duplicate: '<span class="badge badge--warn">' + icon('info') + 'Already here</span>',
    failed:    '<span class="badge badge--danger">' + icon('alert') + 'Failed</span>',
  };

  const NOTES = {
    stored: 'Saved. Its details are still being read, so it may take a moment to appear ' +
            'in the repository.',
    duplicate: 'The identical file is already in the repository. Nothing new was added.',
  };

  function card(i) {
    const ext = (i.name.split('.').pop() || '').toLowerCase();
    const working = i.state === 'uploading' || i.state === 'reading';
    const note = i.error || NOTES[i.state];

    return '<div class="filecard' + (i.state === 'failed' ? ' filecard--failed' : '') + '">' +
      '<div class="filecard__shot" data-shot="' + escapeHtml(i.key) + '">' +
        '<span class="filecard__glyph">' + icon(FILE_GLYPH[ext] || 'file') +
          '<span class="filecard__ext">' + escapeHtml(ext || 'file') + '</span></span>' +
        '<span class="filecard__badge">' + (BADGES[i.state] || BADGES.uploading) + '</span>' +
        (working
          ? '<span class="filecard__progress"><i style="width:' + i.progress + '%"></i></span>'
          : '') +
      '</div>' +
      // The document's title is its identity everywhere else in the product,
      // so the tile leads with it. Indexing renames an uploaded file from what
      // it says inside, which is usually more useful than the filename and
      // occasionally unrecognisable - so the filename stays underneath.
      '<div class="filecard__body">' +
        '<div class="filecard__name">' + escapeHtml(i.title || i.name) + '</div>' +
        // The filename is always here, whether or not indexing has renamed the
        // document yet. It is the one thing that does not change under you.
        '<div class="filecard__meta truncate">' + escapeHtml(i.name) +
          (i.size ? ' · ' + fmt.bytes(i.size) : '') + '</div>' +
        (note ? '<div class="filecard__' + (i.error ? 'err' : 'note') + '">' +
                  escapeHtml(note) + '</div>' : '') +
      '</div>' +
      '<div class="filecard__acts">' + actions(i) + '</div>' +
    '</div>';
  }

  /**
   * What can be done to this card.
   *
   * A duplicate offers no Discard: this upload created nothing, and deleting
   * the document it matched would destroy a record somebody else may already
   * be working on.
   */
  /**
   * What can be done to this card.
   *
   * The two things anyone actually wants next are here as full buttons, in the
   * order the product works: Review carries the file into step 2, and Edit
   * opens it in this same editor - the letterhead, images, signature and AI
   * panels all apply to an uploaded document exactly as they do to one written
   * from scratch. Everything else is a quieter second row.
   *
   * A duplicate offers no Discard: this upload created nothing, and deleting
   * the document it matched would destroy a record somebody else may be
   * working on.
   */
  function actions(i) {
    if (i.state === 'failed') {
      return '<div class="filecard__row">' +
        '<button class="btn btn--sm btn--danger-soft" data-retry="' + escapeHtml(i.key) +
          '">' + icon('refresh') + 'Try again</button>' +
        '<button class="btn btn--sm btn--ghost is-danger" data-discard="' + escapeHtml(i.key) +
          '">' + icon('trash') + 'Remove</button>' +
      '</div>';
    }

    const id = i.docId ? encodeURIComponent(i.docId) : '';
    const off = i.docId ? '' : ' is-disabled';

    // Reading the whole document is a separate act from filing it, so it gets
    // its own tab and this screen keeps its place.
    const open = '<a class="btn btn--sm btn--ghost' + off + '"' +
      (id ? ' href="/documents/view?id=' + id + '" target="_blank" rel="noopener"' : '') +
      '>' + icon('external') + 'Open' + '</a>';

    if (i.state === 'duplicate') {
      return '<div class="filecard__row">' +
          '<a class="btn btn--sm btn--outline' + off + '"' +
            (id ? ' href="/documents/detail?id=' + id + '"' : '') + '>' +
            icon('file') + 'See the copy</a>' +
          '<button class="btn btn--sm btn--ghost" data-replace="' + escapeHtml(i.key) +
            '">' + icon('refresh') + 'Choose another</button>' +
        '</div>';
    }

    return '<div class="filecard__row">' +
        '<a class="btn btn--sm btn--primary' + off + '"' +
          (id ? ' href="/review?id=' + id + '"' : '') +
          ' data-review="' + id + '">' +
          'Review' + icon('arrowRight') + '</a>' +
        '<a class="btn btn--sm btn--outline' + off + '"' +
          (id ? ' href="/studio?id=' + id + '"' : '') + '>' +
          icon('compose') + 'Edit</a>' +
      '</div>' +
      '<div class="filecard__row filecard__row--minor">' +
        open +
        '<button class="btn btn--sm btn--ghost" data-replace="' + escapeHtml(i.key) +
          '">' + icon('refresh') + 'Replace</button>' +
        '<button class="btn btn--sm btn--ghost is-danger" data-discard="' + escapeHtml(i.key) +
          '">' + icon('trash') + 'Discard</button>' +
      '</div>';
  }

  /**
   * Remove the card, and the stored document behind it when there is one.
   *
   * Discarding a file you have just added should leave no trace. Leaving the
   * record in the repository is how a system ends up full of "test" and
   * "wrong version" documents nobody dares delete later.
   */
  async function intakeDiscard(key, opts) {
    opts = opts || {};
    const item = intake.get(key);
    if (!item) return true;

    if (!opts.silent && item.state !== 'duplicate') {
      const ok = await confirmDanger({
        title: 'Discard this file?',
        message: item.docId
          ? 'It is removed from the repository. Nothing has been reviewed or approved yet, ' +
            'so nothing else is affected.'
          : 'The upload is abandoned.',
        confirmLabel: 'Discard file',
      });
      if (!ok) return false;
    }

    intake.delete(key);
    if (item.docId) flow.forgetUpload(item.docId);
    renderIntake();

    // A duplicate's document belongs to whoever filed it first. This upload
    // added nothing, so removing the card must remove nothing else.
    if (item.docId && item.state !== 'duplicate') {
      try {
        await api.del('/api/documents/' + encodeURIComponent(item.docId));
      } catch (err) {
        toast('Removed from this list, but not from the repository',
          String(err.message || err).slice(0, 140), 'danger');
      }
    }
    return true;
  }

  function hideStart() {
    $('#start').hidden = true;
    editorActions(true);
  }

  /** Show or hide the editor-only buttons in the top bar. */
  function editorActions(on) {
    ['#btn-preview', '#btn-draft', '#btn-publish', '#doc-state', '#btn-cancel-doc'].forEach(sel => {
      const el = $(sel);
      if (el) el.hidden = !on;
    });
  }

  async function fillPickers() {
    const [types, corrs] = await Promise.all([
      api.safe('/api/doctypes/', []),
      api.safe('/api/correspondents/', []),
    ]);

    const doctype = $('#f-doctype');
    (Array.isArray(types) ? types : []).forEach(t => {
      const option = document.createElement('option');
      option.value = t.id;
      option.textContent = t.name;
      doctype.appendChild(option);
    });

    // A visible dropdown rather than a datalist, which drew no control of its
    // own and so kept its own contents secret.
    DMS.combobox($('#f-corr'), {
      options: (Array.isArray(corrs) ? corrs : [])
        .map(c => c.name).sort((a, b) => a.localeCompare(b)),
      allowNew: true,
    });

    const dept = $('#f-dept');
    (DMS.DEPARTMENTS || []).forEach(d => {
      const option = document.createElement('option');
      option.value = d;
      option.textContent = d;
      dept.appendChild(option);
    });
  }

  async function loadAssets() {
    const data = await api.safe('/api/studio/assets', { assets: [] });
    state.assets = data.assets || [];
    renderAssets();
  }

  async function loadAiActions() {
    const data = await api.safe('/api/studio/ai/actions', { actions: [] });
    state.aiActions = data.actions || [];
    renderAiActions();
  }

  function prefillSignatory() {
    const name = (document.querySelector('[data-user-name]') || {}).textContent;
    const role = (document.querySelector('[data-user-role]') || {}).textContent;
    // The shell fills these in asynchronously, so wait a beat for them.
    setTimeout(() => {
      const who = (document.querySelector('[data-user-name]') || {}).textContent;
      if (who && who !== 'Signed in') $('#sig-name').value = who;
      const what = (document.querySelector('[data-user-role]') || {}).textContent;
      if (what && what !== 'Loading…') $('#sig-role').value = what;
    }, 500);
    if (name && name !== 'Signed in') $('#sig-name').value = name;
    if (role && role !== 'Loading…') $('#sig-role').value = role;
  }

  /* ---------------------------------------------------------------- events */

  // Ribbon commands
  document.addEventListener('click', e => {
    const cmd = e.target.closest('[data-cmd]');
    if (cmd) { e.preventDefault(); exec(cmd.dataset.cmd); return; }

    const zoom = e.target.closest('[data-zoom]');
    if (zoom) {
      state.zoom = Math.max(0.5, Math.min(2, state.zoom + Number(zoom.dataset.zoom) * 0.1));
      fitPaper();
      return;
    }

    const railTo = e.target.closest('[data-rail]');
    if (railTo) { openRail(railTo.dataset.rail); return; }

    const insert = e.target.closest('[data-insert]');
    if (insert) { e.preventDefault(); doInsert(insert.dataset.insert); return; }
  });

  $('#rb-style').addEventListener('change', e => {
    exec('formatBlock', '<' + e.target.value + '>');
  });

  $('#rb-color').addEventListener('input', e => {
    exec('foreColor', e.target.value, true);
    e.target.closest('.rb-swatch').style.color = e.target.value;
  });

  function doInsert(kind) {
    if (kind === 'image') { openRail('images'); return; }
    if (kind === 'signature') { openRail('signature'); return; }
    if (kind === 'date') { insertHtml(escapeHtml(fmt.date(new Date().toISOString()))); return; }
    if (kind === 'rule') { insertHtml('<hr>'); return; }
    if (kind === 'table') {
      insertHtml(
        '<table><thead><tr><th>Item</th><th>Description</th><th>Quantity</th><th>Value</th></tr></thead>' +
        '<tbody>' +
          '<tr><td>1</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>' +
          '<tr><td>2</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>' +
          '<tr><td>3</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>' +
        '</tbody></table><p><br></p>');
    }
  }

  // Body editing
  body.addEventListener('input', touch);
  body.addEventListener('keyup', () => { rememberRange(); syncToolbar(); refreshScope(); });
  body.addEventListener('mouseup', () => { rememberRange(); syncToolbar(); refreshScope(); });
  body.addEventListener('blur', rememberRange);

  // Paste as text unless it is already our own markup: pasting from Word drags
  // in a stylesheet's worth of junk that the letterhead then has to fight.
  body.addEventListener('paste', e => {
    const html = e.clipboardData && e.clipboardData.getData('text/html');
    if (!html) return;
    e.preventDefault();
    const text = e.clipboardData.getData('text/plain');
    const cleaned = text
      .split(/\n{2,}/)
      .map(p => '<p>' + escapeHtml(p).replace(/\n/g, '<br>') + '</p>')
      .join('');
    document.execCommand('insertHTML', false, cleaned);
    touch();
  });

  // Selecting an image lets its size be changed from the Images panel.
  body.addEventListener('click', e => {
    body.querySelectorAll('img.is-selected').forEach(i => i.classList.remove('is-selected'));
    const img = e.target.closest('img');
    if (img) { img.classList.add('is-selected'); openRail('images'); }
  });

  // Keyboard: the shortcuts a writer already has in their fingers.
  document.addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const key = e.key.toLowerCase();
    if (key === 's') { e.preventDefault(); saveDraft(false); }
    else if (key === 'enter') { e.preventDefault(); publishDialog(); }
    else if (key === 'p' && e.shiftKey) { e.preventDefault(); previewPdf(); }
  });

  // Rail tabs
  $('#rail').addEventListener('click', e => {
    const tab = e.target.closest('.rail__tab');
    if (!tab) return;
    openRail(tab.dataset.tabid);
  });

  function openRail(id) {
    $$('.rail__tab').forEach(t => t.classList.toggle('is-active', t.dataset.tabid === id));
    $$('.rail__panel').forEach(p => p.classList.toggle('is-active', p.dataset.panelid === id));
    $('#rail').classList.add('is-open');
    if (id === 'ai') refreshScope();
  }

  $('#btn-rail').onclick = () => $('#rail').classList.toggle('is-open');

  // Templates: the gallery in the rail, the shortcut chips on the start screen
  document.addEventListener('click', e => {
    const card = e.target.closest('[data-tpl]');
    if (!card) return;
    const id = card.dataset.tpl;
    if ($('#start').hidden) {
      applyTemplate(id);
      toast('Letterhead changed', (state.template || {}).name);
    } else {
      hideStart();
      startFromTemplate(id);
      history.replaceState({}, '', '/studio?template=' + encodeURIComponent(id));
    }
  });

  /* ------------------------------------------------- start screen: write */

  // A blank page is what most people want, so it is one click and no choice.
  $('#btn-write').onclick = () => {
    hideStart();
    startFromTemplate('blank');
    history.replaceState({}, '', '/studio?template=blank');
  };

  /* ------------------------------------------------ start screen: intake */

  const zone = $('#dropzone');
  const fileInput = $('#file-input');

  zone.onclick = () => fileInput.click();
  zone.onkeydown = e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
  };
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('is-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('is-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    // The whole start screen is also a drop target. Without this the drop
    // bubbles up to it and the same file is uploaded twice.
    e.stopPropagation();
    zone.classList.remove('is-over');
    intakeAdd(e.dataTransfer && e.dataTransfer.files);
  });

  fileInput.onchange = () => { intakeAdd(fileInput.files); fileInput.value = ''; };

  // Dropping anywhere on the start screen works too. Aiming at a rectangle is
  // a skill the product should not require.
  const startScreen = $('#start');
  startScreen.addEventListener('dragover', e => {
    if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes('Files')) return;
    e.preventDefault();
    zone.classList.add('is-over');
  });
  startScreen.addEventListener('dragleave', e => {
    if (e.target === startScreen) zone.classList.remove('is-over');
  });
  startScreen.addEventListener('drop', e => {
    if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
    e.preventDefault();
    zone.classList.remove('is-over');
    intakeAdd(e.dataTransfer.files);
  });

  $('#btn-add-more').onclick = () => fileInput.click();
  $('#btn-intake-more').onclick = () => fileInput.click();

  $('#intake-list').addEventListener('click', async e => {
    const retry = e.target.closest('[data-retry]');
    if (retry) {
      const item = intake.get(retry.dataset.retry);
      if (!item) return;
      item.state = 'uploading';
      item.progress = 12;
      item.error = null;
      renderIntake();
      uploadOne(item.key);
      return;
    }

    // Replace means "I picked the wrong file": drop this one, then choose again.
    const replace = e.target.closest('[data-replace]');
    if (replace) {
      const removed = await intakeDiscard(replace.dataset.replace, { silent: true });
      if (removed) fileInput.click();
      return;
    }

    const discard = e.target.closest('[data-discard]');
    if (discard) { intakeDiscard(discard.dataset.discard); }
  });

  // Drafts on the start screen
  document.addEventListener('click', async e => {
    const drop = e.target.closest('[data-drop]');
    if (drop) {
      e.preventDefault(); e.stopPropagation();
      const ok = await confirmDanger({
        title: 'Discard this draft?',
        message: 'The draft and everything written in it are removed. Published documents are not affected.',
        confirmLabel: 'Discard draft',
      });
      if (!ok) return;
      try {
        await api.del('/api/studio/drafts/' + encodeURIComponent(drop.dataset.drop));
        toast('Draft discarded');
        showStart();
      } catch (err) { toast('Could not discard it', String(err.message || err), 'danger'); }
      return;
    }

    const row = e.target.closest('[data-draft]');
    if (row) {
      hideStart();
      openDraft(row.dataset.draft);
      history.replaceState({}, '', '/studio?draft=' + encodeURIComponent(row.dataset.draft));
    }
  });

  // Images
  $('#asset-grid').addEventListener('click', async e => {
    const remove = e.target.closest('[data-remove]');
    if (remove) {
      e.preventDefault(); e.stopPropagation();
      try {
        await api.del('/api/studio/assets/' + encodeURIComponent(remove.dataset.remove));
        toast('Image removed');
        loadAssets();
      } catch (err) { toast('Could not remove it', String(err.message || err), 'danger'); }
      return;
    }
    const pick = e.target.closest('[data-asset]');
    if (!pick) return;
    const asset = state.assets.find(a => a.id === pick.dataset.asset);
    if (asset) insertAsset(asset);
  });

  $('#img-size').addEventListener('segment', e => {
    state.imageSize = e.detail;
    // If an image is selected, resize that one rather than only the next.
    const selected = body.querySelector('img.is-selected');
    if (selected) { selected.setAttribute('data-size', e.detail); touch(); }
  });

  $('#btn-upload-image').onclick = () => $('#image-input').click();
  $('#image-input').onchange = async () => {
    const file = $('#image-input').files && $('#image-input').files[0];
    $('#image-input').value = '';
    if (!file) return;

    const form = new FormData();
    form.append('file', file);
    form.append('kind', 'image');
    try {
      const asset = await api.request('/api/studio/assets', { method: 'POST', body: form });
      state.assets.unshift(asset);
      renderAssets();
      insertAsset(asset);
    } catch (err) {
      toast('Could not add that image', String(err.message || err).slice(0, 200), 'danger');
    }
  };

  // Signature
  $('#btn-sign').onclick = async () => {
    const existing = flow.signature();
    let sig = existing;
    if (!existing) sig = await signaturePad($('#sig-name').value);
    if (!sig) return;
    flow.saveSignature(sig);
    renderSignaturePreview();
    insertNode(signatureBlock(sig));
    toast('Signature placed', 'It stays with the document when it is filed.');
  };

  $('#btn-sign-block').onclick = () => {
    insertNode(signatureBlock(null));
    toast('Signature line added', 'Whoever signs the printed copy signs here.');
  };

  // Anything typed in Details belongs to the document, so mark it dirty too.
  ['#f-title', '#f-doctype', '#f-corr', '#f-dept', '#f-date', '#f-sens', '#f-tags']
    .forEach(sel => {
      const el = $(sel);
      if (el) el.addEventListener('input', () => { state.dirty = true; scheduleSave(); });
    });

  // AI
  $('#ai-actions').addEventListener('click', e => {
    const btn = e.target.closest('[data-ai]');
    if (!btn) return;
    if (btn.dataset.ai === 'translate') {
      const target = prompt('Translate into which language?', 'Hindi');
      if (!target) return;
      runAi('translate', { target: target });
      return;
    }
    runAi(btn.dataset.ai);
  });

  $('#ai-run').onclick = () => {
    const instruction = ($('#ai-prompt').value || '').trim();
    if (!instruction) { toast('Type an instruction first', '', 'danger'); return; }
    runAi('custom', { instruction: instruction });
  };

  $('#ai-draft').onclick = () => {
    const instruction = ($('#ai-prompt').value || '').trim();
    if (!instruction) { toast('Describe the document you want', '', 'danger'); return; }
    runAi('draft', { instruction: instruction });
  };

  // Top bar
  $('#btn-draft').onclick = () => saveDraft(false);
  $('#btn-publish').onclick = publishDialog;
  $('#btn-preview').onclick = previewPdf;
    const newDocument = $('#doc-state');
    if (newDocument) newDocument.onclick = () => { window.location.href = '/studio?new=1'; };
    $('#btn-cancel-doc').onclick = () => {
    window.location.href = '/home';
  };

  // Layout
  window.addEventListener('resize', fitPaper);
  if (window.ResizeObserver) new ResizeObserver(fitPaper).observe(body);

  window.addEventListener('beforeunload', e => {
    if (!state.dirty) return;
    e.preventDefault();
    e.returnValue = '';
  });

  boot();
})();
