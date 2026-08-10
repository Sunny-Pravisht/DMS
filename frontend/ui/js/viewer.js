/* ==========================================================================
   Document rendering, shared by the detail page and the full-screen viewer.

   The rule this file exists to enforce: show the document, not a description
   of it. A PDF is handed to the browser's own PDF engine, an image is the
   image at full fidelity, text is the text with its line breaks intact. When
   a format genuinely cannot be displayed - Word, Excel - it says so plainly
   and offers the download, rather than printing extracted text and letting
   the reader believe that is the document.
   ========================================================================== */
(function () {
  'use strict';

  const { api, icon, escapeHtml, fmt, toast } = DMS;

  /**
   * Render a document into `host`.
   *
   * @param {HTMLElement} host  a .viewer element
   * @param {string} id         document id
   * @param {object} opts       { full: boolean } - full drops the framing so
   *                            the document owns the whole window
   * @returns {Promise<object>} the preview-info payload, for the caller's chrome
   */
  async function mount(host, id, opts) {
    opts = opts || {};

    host.innerHTML = '<div class="viewer__stage">' +
      '<div class="viewer__page">' +
        '<div class="skeleton" style="height:22px;width:56%"></div>' +
        '<div class="skeleton mt-3" style="height:12px;width:92%"></div>' +
        '<div class="skeleton mt-2" style="height:12px;width:88%"></div>' +
        '<div class="skeleton mt-2" style="height:12px;width:61%"></div>' +
      '</div></div>';

    let info;
    try {
      info = await api.get('/api/documents/' + encodeURIComponent(id) + '/preview-info');
    } catch (err) {
      host.innerHTML = fallback('alert', 'This document could not be opened',
        String(err.message || err).slice(0, 200), null);
      return null;
    }

    if (info.mode === 'pdf') renderPdf(host, info, opts);
    else if (info.mode === 'image') await renderImage(host, info, opts);
    else if (info.mode === 'text') await renderText(host, info, opts);
    else if (info.mode === 'missing') renderMissing(host, info);
    else await renderUnsupported(host, info);

    wireToolbar(host, info);
    return info;
  }

  /* ------------------------------------------------------------------ PDF */

  function renderPdf(host, info, opts) {
    // The browser's PDF viewer already does pages, zoom, search, selection and
    // printing, and does them better than a reimplementation would. Hand it the
    // whole stage and add nothing on top.
    host.innerHTML =
      '<div class="viewer__stage viewer__stage--flush">' +
        '<iframe class="viewer__frame" src="' + escapeHtml(info.file_url) +
        '#view=FitH" title="' + escapeHtml(info.title || 'Document') + '"></iframe>' +
      '</div>' +
      // Full screen hands the whole window to the browser's PDF engine, which
      // already has its own toolbar. Ours would only duplicate it.
      (opts.full ? '' : toolbar(info, {
        pages: info.page_hint,
        note: info.page_hint ? info.page_hint + (info.page_hint === 1 ? ' page' : ' pages') : '',
      }));
  }

  /* ---------------------------------------------------------------- image */

  async function renderImage(host, info, opts) {
    host.innerHTML =
      '<div class="viewer__stage" data-stage>' +
        '<img class="viewer__image" data-zoomable src="' + escapeHtml(info.file_url) +
        '" alt="' + escapeHtml(info.title || 'Document') + '">' +
      '</div>' + toolbar(info, { zoom: true });
  }

  /* ----------------------------------------------------------------- text */

  async function renderText(host, info, opts) {
    // Read the file itself rather than the extracted text: for a text document
    // the file *is* the content, and the extraction is a copy that may lag.
    let content = '';
    try {
      const res = await fetch(info.file_url, { credentials: 'same-origin' });
      if (!res.ok) throw new Error(res.statusText);
      content = await res.text();
    } catch (err) {
      const data = await api.safe('/api/documents/' + info.document_id + '/text', { text: '' });
      content = data.text || '';
    }

    if (!content.trim()) {
      host.innerHTML = fallback('file', 'This document is empty',
        'There is no text in the file.', info);
      return;
    }

    const mono = /csv|log/i.test(info.mime_type || '') ||
      /\.(csv|log)$/i.test(info.filename || '');

    // Split on form feeds where they exist; a plain text file rarely has them,
    // so most documents render as one continuous sheet, which is honest.
    const pages = content.split('\f').filter(p => p.trim().length);

    host.innerHTML =
      '<div class="viewer__stage" data-stage>' +
        pages.map(page =>
          '<div class="viewer__page" data-zoomable>' +
            '<pre class="viewer__text' + (mono ? ' viewer__text--mono' : '') + '">' +
            escapeHtml(page) + '</pre>' +
          '</div>').join('') +
      '</div>' +
      toolbar(info, {
        zoom: true,
        pages: pages.length > 1 ? pages.length : null,
        note: fmt.bytes(info.file_size),
      });
  }

  /* ---------------------------------------------------------- can't render */

  async function renderUnsupported(host, info) {
    const kind = (info.filename || '').split('.').pop().toUpperCase();
    let extract = '';
    if (info.has_text) {
      const data = await api.safe('/api/documents/' + info.document_id + '/text', { text: '' });
      extract = (data.text || '').slice(0, 4000);
    }

    host.innerHTML =
      '<div class="viewer__stage" data-stage>' +
        '<div class="viewer__page">' +
          '<div class="empty" style="padding:26px 0 30px">' +
            '<span class="tile-icon tile-icon--grey">' + icon('file') + '</span>' +
            '<h3>' + escapeHtml(kind || 'This format') + ' files open in their own application</h3>' +
            '<p>A browser cannot display ' + escapeHtml(kind || 'this format') +
              ' faithfully, and showing you an approximation would be worse than saying so. ' +
              'Download it to see the document exactly as written.</p>' +
            '<div class="btn-row">' +
              '<a class="btn btn--primary" href="' + escapeHtml(info.download_url) + '">' +
                icon('download') + 'Download ' + escapeHtml(kind || 'file') + '</a>' +
            '</div>' +
          '</div>' +
          (extract
            ? '<div class="divider"></div>' +
              '<div class="t-eyebrow">Text read from the file</div>' +
              '<p class="t-xs muted-2 mt-1 mb-2">Extracted for search. It is not the layout.</p>' +
              '<pre class="viewer__text">' + escapeHtml(extract) +
              (info.text_length > 4000 ? '\n\n… ' + fmt.num(info.text_length - 4000) +
                ' more characters' : '') + '</pre>'
            : '') +
        '</div>' +
      '</div>' + toolbar(info, { note: fmt.bytes(info.file_size) });
  }

  function renderMissing(host, info) {
    host.innerHTML = fallback('alert', 'The file is missing from storage',
      'This document\'s record still exists, but the file it points to is not on disk. ' +
      'An administrator can restore it from a backup.', info);
  }

  function fallback(iconName, title, message, info) {
    return '<div class="viewer__stage"><div class="viewer__fallback">' +
      '<span class="tile-icon tile-icon--grey">' + icon(iconName) + '</span>' +
      '<h3 class="t-h3">' + escapeHtml(title) + '</h3>' +
      '<p class="t-sm muted mt-2">' + escapeHtml(message) + '</p>' +
      (info ? '<div class="btn-row mt-3" style="justify-content:center">' +
        '<a class="btn btn--outline btn--sm" href="' + escapeHtml(info.download_url) + '">' +
        icon('download') + 'Download</a></div>' : '') +
      '</div></div>';
  }

  /* -------------------------------------------------------------- toolbar */

  function toolbar(info, opts) {
    opts = opts || {};
    return '<div class="viewer__toolbar">' +
      (opts.zoom
        ? '<button class="icon-btn tip" data-tip="Zoom out" data-vz="-1">' + icon('minus') + '</button>' +
          '<span class="viewer__zoom" data-zoom-label>100%</span>' +
          '<button class="icon-btn tip" data-tip="Zoom in" data-vz="1">' + icon('plus') + '</button>' +
          '<button class="icon-btn tip" data-tip="Fit to width" data-vz="0">' + icon('expand') + '</button>' +
          '<span class="divider--v" style="margin:0 4px"></span>'
        : '') +
      (opts.pages ? '<span class="viewer__pageno">' + opts.pages +
        (opts.pages === 1 ? ' page' : ' pages') + '</span>' +
        '<span class="divider--v" style="margin:0 4px"></span>' : '') +
      (opts.note && !opts.pages
        ? '<span class="viewer__pageno">' + escapeHtml(opts.note) + '</span>' +
          '<span class="divider--v" style="margin:0 4px"></span>' : '') +
      '<a class="icon-btn tip" data-tip="Open the whole document in a new tab" target="_blank" ' +
        'rel="noopener" href="/documents/view?id=' + encodeURIComponent(info.document_id) + '">' +
        icon('external') + '</a>' +
      '<a class="icon-btn tip" data-tip="Download" href="' + escapeHtml(info.download_url) + '">' +
        icon('download') + '</a>' +
      '<button class="icon-btn tip" data-tip="Print" data-vprint>' + icon('file') + '</button>' +
      '</div>';
  }

  /** Zoom, when the mode offers it, plus print for every mode. */
  function wireToolbar(host, info) {
    let zoom = 1;
    const label = host.querySelector('[data-zoom-label]');
    const apply = () => {
      host.querySelectorAll('[data-zoomable]').forEach(el => {
        el.style.transform = 'scale(' + zoom + ')';
        // Transform does not change layout, so scaling up would overlap what
        // follows. Give the element back the room it now visually occupies.
        el.style.marginBottom = zoom > 1 ? (el.offsetHeight * (zoom - 1)) + 'px' : '';
      });
      if (label) label.textContent = Math.round(zoom * 100) + '%';
    };

    host.querySelectorAll('[data-vz]').forEach(btn => {
      btn.onclick = () => {
        const step = Number(btn.dataset.vz);
        zoom = step === 0 ? 1 : Math.max(0.4, Math.min(3, zoom + step * 0.15));
        apply();
      };
    });

    const print = host.querySelector('[data-vprint]');
    if (!print) return;
    print.onclick = () => {
      // A PDF lives in an iframe, and printing the page around it would print
      // the application chrome instead of the document. Print the frame.
      const frame = host.querySelector('iframe');
      if (frame) {
        try {
          frame.contentWindow.focus();
          frame.contentWindow.print();
          return;
        } catch (e) {
          window.open(info.file_url, '_blank', 'noopener');
          return;
        }
      }
      window.print();
    };
  }

  window.DMSViewer = { mount: mount };
})();
