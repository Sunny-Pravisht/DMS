/* ==========================================================================
   HARMAN DMS application shell
   Renders the sidebar + topbar, provides the icon sprite, API helper,
   toasts, modals, drawers and tab wiring. No dependencies.
   ========================================================================== */
(function () {
  'use strict';

  /* ---------------------------------------------------------------- icons */
  const ICONS = {
    logo: '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.5 0 1 .2 1.4.6l1.2 1.2h7.2A2.5 2.5 0 0 1 21 9.3v8.2a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/>',
    dashboard: '<rect x="3" y="3" width="7.5" height="8.5" rx="1.6"/><rect x="13.5" y="3" width="7.5" height="5" rx="1.6"/><rect x="3" y="14.5" width="7.5" height="6.5" rx="1.6"/><rect x="13.5" y="11" width="7.5" height="10" rx="1.6"/>',
    documents: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/>',
    capture: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5-5 5 5"/><path d="M12 5v11"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
    ai: '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
    workflow: '<rect x="3" y="3" width="6" height="5" rx="1.4"/><rect x="15" y="8" width="6" height="5" rx="1.4"/><rect x="3" y="16" width="6" height="5" rx="1.4"/><path d="M9 5.5h3a2 2 0 0 1 2 2v3M9 18.5h3a2 2 0 0 0 2-2v-3"/>',
    approvals: '<path d="M9 11.5l2.2 2.2L15.5 9.5"/><circle cx="12" cy="12" r="9"/>',
    retention: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.2l3.3 2"/>',
    records: '<path d="M3 8.5 12 4l9 4.5"/><path d="M4.5 10.5V19h15v-8.5"/><path d="M3 19h18"/><path d="M9 19v-4.5h6V19"/>',
    audit: '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H15l5 5v9.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5z"/><path d="M15 4v5h5"/><path d="M8.5 13.5h7M8.5 16.5h4.5"/>',
    org: '<circle cx="12" cy="5.5" r="2.5"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/><path d="M12 8v3.5M5.5 16V13h13v3"/>',
    integrations: '<path d="M9 3v5M15 3v5"/><rect x="6.5" y="8" width="11" height="6.5" rx="2"/><path d="M12 14.5V21"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 14.5a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.56-1.1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1-1.56V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.56 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1.03z"/>',

    bell: '<path d="M18 8.5a6 6 0 1 0-12 0c0 6-2 7.5-2 7.5h16s-2-1.5-2-7.5"/><path d="M13.7 19.5a2 2 0 0 1-3.4 0"/>',
    logout: '<path d="M9 21H5.5A1.5 1.5 0 0 1 4 19.5v-15A1.5 1.5 0 0 1 5.5 3H9"/><path d="m15.5 16.5 4.5-4.5-4.5-4.5"/><path d="M20 12H9"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    minus: '<path d="M5 12h14"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    chevronRight: '<path d="m9 5 7 7-7 7"/>',
    chevronDown: '<path d="m5 9 7 7 7-7"/>',
    chevronLeft: '<path d="m15 5-7 7 7 7"/>',
    arrowRight: '<path d="M4 12h16"/><path d="m14 6 6 6-6 6"/>',
    arrowUp: '<path d="M12 20V4"/><path d="m6 10 6-6 6 6"/>',
    arrowDown: '<path d="M12 4v16"/><path d="m6 14 6 6 6-6"/>',
    external: '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v5a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V7.5A1.5 1.5 0 0 1 5 6h5"/>',
    filter: '<path d="M4 5h16l-6.4 7.6V19l-3.2 1.8v-8.2z"/>',
    more: '<circle cx="5.5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="18.5" cy="12" r="1.4"/>',
    download: '<path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M4 20h16"/>',
    upload: '<path d="M12 20V8"/><path d="m7 12 5-5 5 5"/><path d="M4 4h16"/>',
    trash: '<path d="M4 6.5h16"/><path d="M9.5 6.5V4.5A1 1 0 0 1 10.5 3.5h3a1 1 0 0 1 1 1v2"/><path d="M6.5 6.5 7.4 20a1.5 1.5 0 0 0 1.5 1.4h6.2a1.5 1.5 0 0 0 1.5-1.4l.9-13.5"/><path d="M10.5 10.5v6.5M13.5 10.5v6.5"/>',
    edit: '<path d="M4 20h4.5L20 8.5a2.1 2.1 0 0 0-3-3L5.5 17z"/><path d="M15 6.5 17.5 9"/>',
    eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12"/><circle cx="12" cy="12" r="3"/>',
    lock: '<rect x="4.5" y="10" width="15" height="10.5" rx="2"/><path d="M8 10V7.5a4 4 0 0 1 8 0V10"/>',
    unlock: '<rect x="4.5" y="10" width="15" height="10.5" rx="2"/><path d="M8 10V7.5a4 4 0 0 1 7.6-1.8"/>',
    shield: '<path d="M12 3 4.5 6v6c0 4.4 3.1 8.2 7.5 9.3 4.4-1.1 7.5-4.9 7.5-9.3V6z"/>',
    alert: '<path d="M12 3.5 21 19.5H3z"/><path d="M12 10v4"/><circle cx="12" cy="17" r=".6" fill="currentColor"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11.5v5"/><circle cx="12" cy="8" r=".7" fill="currentColor"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.2l3.3 2"/>',
    calendar: '<rect x="3.5" y="5" width="17" height="16" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    folder: '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.5 0 1 .2 1.4.6l1.2 1.2h7.2A2.5 2.5 0 0 1 21 9.3v8.2a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    tag: '<path d="M11.5 3H20a1 1 0 0 1 1 1v8.5a2 2 0 0 1-.6 1.4l-6.5 6.5a2 2 0 0 1-2.8 0l-7-7a2 2 0 0 1 0-2.8l6.5-6.5A2 2 0 0 1 11.5 3"/><circle cx="16.5" cy="7.5" r="1.3"/>',
    link: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l2.6-2.6a4.5 4.5 0 0 0-6.4-6.4L11 6.6"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0L5 12.6a4.5 4.5 0 0 0 6.4 6.4L13 17.4"/>',
    send: '<path d="M21 3 3 10.5l7 3 3 7z"/><path d="M21 3 10 13.5"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-13.6-5L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 13.6 5L20 16"/><path d="M20 20v-4h-4"/>',
    database: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 6.5 8.5 6 8.5-6"/>',
    image: '<rect x="3" y="4.5" width="18" height="15" rx="2"/><circle cx="8.5" cy="9.5" r="1.6"/><path d="m4 17 5-5 4.5 4.5L16.5 13l3.5 3.5"/>',
    building: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8.5 7.5h2M13.5 7.5h2M8.5 11.5h2M13.5 11.5h2M8.5 15.5h2M13.5 15.5h2"/>',
    users: '<circle cx="9" cy="8" r="3.2"/><path d="M2.8 20a6.2 6.2 0 0 1 12.4 0"/><path d="M16.5 5.2a3.2 3.2 0 0 1 0 5.9"/><path d="M18 14.4a6.2 6.2 0 0 1 3.2 5.6"/>',
    user: '<circle cx="12" cy="8" r="3.5"/><path d="M4.8 20a7.2 7.2 0 0 1 14.4 0"/>',
    key: '<circle cx="8" cy="12" r="4"/><path d="M12 12h9"/><path d="M17.5 12v3.5M20.5 12v2.5"/>',
    box: '<path d="M3.5 7.5 12 3.5l8.5 4v9L12 20.5l-8.5-4z"/><path d="m3.5 7.5 8.5 4 8.5-4M12 11.5v9"/>',
    pin: '<path d="M12 21s7-6.2 7-11a7 7 0 0 0-14 0c0 4.8 7 11 7 11"/><circle cx="12" cy="10" r="2.6"/>',
    play: '<path d="M7 4.5 19 12 7 19.5z"/>',
    pause: '<rect x="7" y="4.5" width="3.5" height="15" rx="1"/><rect x="13.5" y="4.5" width="3.5" height="15" rx="1"/>',
    copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="2"/><path d="M15.5 8.5v-3a2 2 0 0 0-2-2h-8a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3"/>',
    layers: '<path d="m12 3 9 4.5-9 4.5-9-4.5z"/><path d="m3 12.5 9 4.5 9-4.5"/>',
    scale: '<path d="M12 3v18M7 21h10"/><path d="M12 6 4.5 8 2 14h11z"/><path d="M12 6 19.5 8 22 14H11z"/>',
    archive: '<rect x="3" y="4" width="18" height="4.5" rx="1.5"/><path d="M4.5 8.5V19a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5V8.5"/><path d="M10 12.5h4"/>',
    grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.6"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.6"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.6"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.6"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1.1" fill="currentColor"/><circle cx="4" cy="12" r="1.1" fill="currentColor"/><circle cx="4" cy="18" r="1.1" fill="currentColor"/>',
    comment: '<path d="M20.5 12a7.5 7.5 0 0 1-10.9 6.7L4 20l1.4-5A7.5 7.5 0 1 1 20.5 12"/>',
    history: '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1L3.5 8.5"/><path d="M3.5 3.5v5h5"/><path d="M12 7.5V12l3 1.8"/>',
    stamp: '<path d="M6 20.5h12"/><path d="M8 17h8v-2H8z"/><path d="M9.5 15c0-2-2.5-3-2.5-5.5a5 5 0 0 1 10 0C17 12 14.5 13 14.5 15"/>',
    zap: '<path d="M13 2 4 13.5h6L11 22l9-11.5h-6z"/>',
    trend: '<path d="M3 17 9.5 10.5l4 4L21 7"/><path d="M15 7h6v6"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18"/>',
    sitemap: '<rect x="9" y="3" width="6" height="4.5" rx="1.2"/><rect x="2.5" y="16.5" width="6" height="4.5" rx="1.2"/><rect x="15.5" y="16.5" width="6" height="4.5" rx="1.2"/><path d="M12 7.5v4.5M5.5 16.5V12h13v4.5"/>',
    sliders: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',

    /* Authoring: the Document Studio's own vocabulary. */
    compose: '<path d="M5 3.5h9.5L19 8v12.5a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 4 20.5v-15A1.5 1.5 0 0 1 5.5 4"/><path d="M14 3.5V8h4.5"/><path d="M8.5 13.5h7M8.5 17h4.5"/><path d="m17.5 14.5 2.6-2.6a1.4 1.4 0 0 1 2 2L19.5 16.5l-2.6.6z"/>',
    template: '<rect x="3.5" y="3.5" width="17" height="17" rx="2.2"/><path d="M3.5 9h17"/><path d="M9.5 9v11.5"/>',
    blank: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    signature: '<path d="M3 18.5c3.5 0 4-13 6.5-13S12 17 14.5 17s2-4.5 3.5-4.5S20 16 21 16.5"/><path d="M3 21h18"/>',
    bold: '<path d="M7 4.5h6a3.75 3.75 0 0 1 0 7.5H7z"/><path d="M7 12h7a3.75 3.75 0 0 1 0 7.5H7z"/>',
    alignLeft: '<path d="M4 6h16M4 10.5h10M4 15h16M4 19.5h10"/>',
    alignCenter: '<path d="M4 6h16M7 10.5h10M4 15h16M7 19.5h10"/>',
    alignRight: '<path d="M4 6h16M10 10.5h10M4 15h16M10 19.5h10"/>',
    listBullet: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1.4" fill="currentColor"/><circle cx="4.5" cy="12" r="1.4" fill="currentColor"/><circle cx="4.5" cy="18" r="1.4" fill="currentColor"/>',
    listNumber: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 4.5h1V8M3.4 11.2c.2-.7 1.6-.9 1.9-.1.3.7-1.7 1.6-1.9 2.4H5.4M3.5 16.6h1.6l-1 1.2 1 1.3H3.4"/>',
    undo: '<path d="M4 9h9.5a5 5 0 0 1 0 10H7"/><path d="M8 4.5 3.5 9 8 13.5"/>',
    redo: '<path d="M20 9h-9.5a5 5 0 0 0 0 10H17"/><path d="m16 4.5 4.5 4.5L16 13.5"/>',
    table: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 10h17M3.5 15h17M9.5 4.5v15"/>',
    magic: '<path d="M4 20 15 9"/><path d="m13.5 4 .9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4-2.4-.9 2.4-.9z"/><path d="m19.5 12.5.6 1.6 1.6.6-1.6.6-.6 1.6-.6-1.6-1.6-.6 1.6-.6z"/><path d="m16 17 2.5 2.5"/>',
    pageBreak: '<path d="M6 3.5h9L18.5 7v3"/><path d="M15 3.5V7h3.5"/><path d="M2.5 14h19"/><path d="M6 21h12"/><path d="M18.5 17.5V21M5.5 17.5V21"/>',
    expand: '<path d="M4 9V4h5"/><path d="M20 15v5h-5"/><path d="M4 4 10 10"/><path d="m20 20-6-6"/>',
  };

  // Every generated icon carries `.ic`, which gives it a sane default size.
  // Component rules (.btn svg, .tile-icon svg, .badge svg, …) are more specific
  // and override it, so an icon is never unsized wherever it is dropped.
  function icon(name, cls) {
    const path = ICONS[name] || ICONS.file;
    const klass = 'ic' + (cls ? ' ' + cls : '');
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" ' +
      'stroke-linecap="round" stroke-linejoin="round" class="' + klass + '">' +
      path + '</svg>';
  }

  /* ------------------------------------------------------------ navigation */

  // The five numbered steps are the product's spine: the order a document
  // actually moves through the business, and the order every screen follows.
  //
  // Step 1 is the Studio, which is also where the product opens. A document
  // starts life one of two ways - written here, or brought in as a file - and
  // both belong to the same step. Splitting them into two destinations was the
  // single biggest source of "which screen do I use?" in the old navigation.
  const JOURNEY = [
    { id: 'studio',  n: 1, label: 'Upload Document',  hint: 'Add a document',          href: '/studio',  icon: 'compose' },
    { id: 'review',  n: 2, label: 'Review & Confirm', hint: 'Check extracted details', href: '/review',  icon: 'eye' },
    { id: 'process', n: 3, label: 'Set Up Approval',  hint: 'Choose who approves',     href: '/process', icon: 'workflow' },
    { id: 'track',   n: 4, label: 'Track Status',     hint: 'Follow approvals',       href: '/track',   icon: 'approvals' },
    { id: 'publish', n: 5, label: 'Publish',           hint: 'Release the record',      href: '/publish', icon: 'send' },
  ];

  // The sidebar should stay focused on the starting action, while the top
  // journey header continues to show the full document workflow.
  const WORKFLOW_SIDEBAR = [
    { id: 'studio', n: 1, label: 'Create Document', hint: 'Start a document', href: '/studio', icon: 'compose' },
  ];

  const STEP_COUNT = JOURNEY.length;

  /**
   * The navigation.
   *
   * Every destination here is a screen that does real work against real data.
   * Screens that only illustrated an idea - a process designer that designed
   * nothing, a warehouse with no boxes in it, a retention engine with no
   * schedule behind it - have been taken out rather than left to teach people
   * that half this product is decorative.
   *
   * Three groups, thirteen destinations: the five steps a document takes, the
   * four places you go to find something, and the four you go to set things up.
   */
  const FIND_AND_DO = [
    // The count is filled in from the server on every page load; it is
    // never a fixed number, because a badge that lies is worse than none.
    { id: 'tasks', label: 'My Tasks', icon: 'approvals', href: '/tasks' },
    { id: 'documents', label: 'All Documents', icon: 'documents', href: '/documents' },
    { id: 'my-folder', label: 'My Folder', icon: 'folder', href: '/documents?personal=1' },
    { id: 'search', label: 'Search', icon: 'search', href: '/search' },
    { id: 'assistant', label: 'Ask AI', icon: 'ai', href: '/assistant' },
  ];

  const NAV_ADMIN = [
    { label: 'Workflow', journey: true, items: WORKFLOW_SIDEBAR },
    { label: 'Find & Do', items: FIND_AND_DO },
    // Settings is not listed. It is reached by pressing your own name at the
    // foot of this menu, which is where an account's own preferences belong
    // and where people look for them.
    {
      label: 'Set Up', items: [
        { id: 'templates', label: 'Approval Routes', icon: 'layers', href: '/templates' },
        { id: 'organization', label: 'People', icon: 'org', href: '/organization' },
        { id: 'audit', label: 'Activity Log', icon: 'audit', href: '/audit' },
      ]
    },
  ];

  /**
   * What an approver sees.
   *
   * Somebody whose job is to read documents and decide on them has no use for
   * the authoring spine, the route designer, user administration or the
   * publishing queue. Showing all of it buries the one screen they actually
   * came for, and every extra destination is a chance to get lost on the way
   * to a decision that is waiting.
   *
   * They keep everything needed to *do* the job: the tasks, the repository,
   * search, the assistant, and the status of anything they have touched.
   */
  const NAV_MEMBER = [
    {
      label: 'My Work', items: [
        { id: 'tasks', label: 'My Tasks', icon: 'approvals', href: '/tasks' },
        { id: 'track', label: 'Status & Tracking', icon: 'workflow', href: '/track' },
      ]
    },
    {
      label: 'Find', items: [
        { id: 'documents', label: 'All Documents', icon: 'documents', href: '/documents' },
        { id: 'my-folder', label: 'My Folder', icon: 'folder', href: '/documents?personal=1' },
        { id: 'search', label: 'Search', icon: 'search', href: '/search' },
        { id: 'assistant', label: 'Ask AI', icon: 'ai', href: '/assistant' },
      ]
    },
  ];

  // Until the server says who is signed in, assume the smaller menu. Growing a
  // menu once identity is known reads as the product waking up; shrinking one
  // reads as something being taken away.
  let NAV = NAV_MEMBER;

  /* ------------------------------------------------------------- directory */

  // The organisation directory. Everything that needs to know which roles and
  // which people exist in a department reads it from here, so a department
  // chosen anywhere fills in the same options everywhere.
  const DEPARTMENTS = [
    'Finance', 'Legal', 'Operations', 'Human Resources',
    'Procurement', 'Compliance & Internal Audit',
  ];

  const DIRECTORY = {
    'Finance': {
      retention: 'Financial records, 8 years',
      docTypes: ['Invoice', 'Credit note', 'Payment advice', 'Bank statement', 'Tax filing'],
      roles: ['AP Clerk', 'AP Manager', 'Cost Controller', 'Head of Finance'],
      people: [
        { name: 'Sudha Iyer', role: 'Head of Finance' },
        { name: 'Arun Prasad', role: 'AP Manager' },
        { name: 'Meena Raghavan', role: 'AP Clerk' },
        { name: 'Karthik Nair', role: 'AP Clerk' },
        { name: 'Vidya Menon', role: 'Cost Controller' },
      ],
      steps: [
        { name: 'Verify invoice', who: 'AP Clerk', sla: '8 hours', sign: false },
        { name: 'Approve payment', who: 'Head of Finance', sla: '2 days', sign: true },
      ],
    },
    'Legal': {
      retention: 'Commercial contracts, 7 years',
      docTypes: ['Contract', 'NDA', 'Master services agreement', 'Legal notice', 'Statutory filing'],
      roles: ['Legal Executive', 'Legal Counsel', 'Contract Manager', 'Head of Legal'],
      people: [
        { name: 'Rahul Menon', role: 'Head of Legal' },
        { name: 'Ananya Kapoor', role: 'Legal Counsel' },
        { name: 'Imran Sheikh', role: 'Contract Manager' },
        { name: 'Priya Deshmukh', role: 'Legal Executive' },
      ],
      steps: [
        { name: 'Legal review', who: 'Legal Counsel', sla: '3 days', sign: false },
        { name: 'Approve & sign', who: 'Head of Legal', sla: '2 days', sign: true },
      ],
    },
    'Operations': {
      retention: 'Operational records, 3 years',
      docTypes: ['Delivery note', 'Goods receipt', 'Maintenance log', 'Capex request', 'Quality report'],
      roles: ['Shift Supervisor', 'Plant Engineer', 'Business Owner', 'Head of Operations'],
      people: [
        { name: 'Prakash Krishnan', role: 'Head of Operations' },
        { name: 'Sunil Bhatt', role: 'Plant Engineer' },
        { name: 'Farah Qureshi', role: 'Business Owner' },
        { name: 'Ravi Shankar', role: 'Shift Supervisor' },
      ],
      steps: [
        { name: 'Operational check', who: 'Shift Supervisor', sla: '1 day', sign: false },
        { name: 'Approve & sign', who: 'Head of Operations', sla: '2 days', sign: true },
      ],
    },
    'Human Resources': {
      retention: 'Employee records, 7 years',
      docTypes: ['Offer letter', 'Personnel file', 'Payroll register', 'Appraisal', 'Exit form'],
      roles: ['HR Executive', 'HR Business Partner', 'Payroll Officer', 'HR Manager'],
      people: [
        { name: 'Divya Varma', role: 'HR Manager' },
        { name: 'Sanjay Rao', role: 'HR Business Partner' },
        { name: 'Neha Gupta', role: 'HR Executive' },
        { name: 'Tarun Singh', role: 'Payroll Officer' },
        { name: 'Lakshmi Pillai', role: 'HR Executive' },
      ],
      steps: [
        { name: 'HR verification', who: 'HR Executive', sla: '1 day', sign: false },
        { name: 'Approve & file', who: 'HR Manager', sla: '2 days', sign: true },
      ],
    },
    'Procurement': {
      retention: 'Procurement and tenders, 6 years',
      docTypes: ['Purchase requisition', 'Purchase order', 'Tender response', 'Vendor agreement'],
      roles: ['Buyer', 'Category Lead', 'Procurement Lead', 'Head of Procurement'],
      people: [
        { name: 'Nikhil Sharma', role: 'Head of Procurement' },
        { name: 'Ayesha Khan', role: 'Procurement Lead' },
        { name: 'Gaurav Joshi', role: 'Category Lead' },
        { name: 'Deepa Suresh', role: 'Buyer' },
      ],
      steps: [
        { name: 'Budget check', who: 'Buyer', sla: '1 day', sign: false },
        { name: 'Authorise spend', who: 'Head of Procurement', sla: '2 days', sign: true },
      ],
    },
    'Compliance & Internal Audit': {
      retention: 'Statutory records, permanent',
      docTypes: ['Audit report', 'Compliance certificate', 'Policy', 'Regulatory filing'],
      roles: ['Auditor', 'Compliance Officer', 'Head of Compliance'],
      people: [
        { name: 'Vikram Chandra', role: 'Head of Compliance' },
        { name: 'Shalini Rao', role: 'Compliance Officer' },
        { name: 'Joseph Mathew', role: 'Auditor' },
      ],
      steps: [
        { name: 'Compliance review', who: 'Compliance Officer', sla: '3 days', sign: false },
        { name: 'Approve & sign', who: 'Head of Compliance', sla: '3 days', sign: true },
      ],
    },
  };

  const SLA_OPTIONS = ['4 hours', '8 hours', '1 day', '2 days', '3 days', '5 days', '10 days'];

  const dir = {
    departments() { return DEPARTMENTS.slice(); },
    of(dept) { return DIRECTORY[dept] || null; },
    roles(dept) { return (DIRECTORY[dept] || {}).roles || []; },
    docTypes(dept) { return (DIRECTORY[dept] || {}).docTypes || []; },
    retention(dept) { return (DIRECTORY[dept] || {}).retention || 'Default, 5 years'; },
    defaultSteps(dept) {
      const s = (DIRECTORY[dept] || {}).steps || [];
      return s.map(x => Object.assign({}, x, { dept: dept, people: [] }));
    },
    /** Everyone in a department, or only those holding a given role. */
    people(dept, role) {
      const list = (DIRECTORY[dept] || {}).people || [];
      if (!role) return list.slice();
      const matched = list.filter(p => p.role === role);
      return matched.length ? matched : list.slice();
    },
    /** Which department a person belongs to, used when a step names a person. */
    departmentOf(name) {
      for (const d of DEPARTMENTS) {
        if ((DIRECTORY[d].people || []).some(p => p.name === name)) return d;
      }
      return null;
    },
  };

  /* ------------------------------------------------------------- templates */

  // Shared so the Templates library and step 3 always show the same thing.
  // A template is "who approves, in what order, by when, and what happens after".
  const BUILT_IN_TEMPLATES = [
    {
      id: 'inv-approval',
      name: 'Invoice Approval',
      department: 'Finance',
      description: 'Three-way match, then value-banded sign-off. The standard route for supplier invoices.',
      appliesTo: ['Invoice', 'Credit note'],
      retention: 'Financial records, 8 years',
      steps: [
        { name: 'Verify invoice', who: 'AP Clerk', type: 'role', dept: 'Finance', sla: '8 hours', sign: false },
        { name: 'Match to purchase order', who: 'AP Manager', type: 'role', dept: 'Finance', sla: '1 day', sign: false },
        { name: 'Approve payment', who: 'Head of Finance', type: 'role', dept: 'Finance', sla: '2 days', sign: true },
      ],
    },
    {
      id: 'contract-review',
      name: 'Contract Review & Signature',
      department: 'Legal',
      description: 'Parallel legal and commercial review, then counter-signature and lock.',
      appliesTo: ['Contract', 'NDA', 'MSA'],
      retention: 'Commercial contracts, 7 years',
      steps: [
        { name: 'Legal review', who: 'Legal Counsel', type: 'role', dept: 'Legal', sla: '3 days', sign: false },
        { name: 'Commercial review', who: 'Business Owner', type: 'role', dept: 'Operations', sla: '3 days', sign: false },
        { name: 'Approve & sign', who: 'Head of Legal', type: 'role', dept: 'Legal', sla: '2 days', sign: true },
      ],
    },
    {
      id: 'purchase-req',
      name: 'Purchase Requisition',
      department: 'Procurement',
      description: 'Budget check followed by value-banded authorisation before a PO is raised.',
      appliesTo: ['Purchase requisition', 'Purchase order'],
      retention: 'Procurement and tenders, 6 years',
      steps: [
        { name: 'Budget check', who: 'Cost Controller', type: 'role', dept: 'Finance', sla: '1 day', sign: false },
        { name: 'Category approval', who: 'Procurement Lead', type: 'role', dept: 'Procurement', sla: '2 days', sign: false },
        { name: 'Authorise spend', who: 'Department Head', type: 'hierarchy', dept: 'Requester\'s department', sla: '2 days', sign: true },
      ],
    },
    {
      id: 'employee-doc',
      name: 'Employee Document',
      department: 'Human Resources',
      description: 'Restricted route for personnel files. HR only, with confidential handling.',
      appliesTo: ['Offer letter', 'Personnel file', 'Payroll'],
      retention: 'Employee records, 7 years',
      steps: [
        { name: 'HR verification', who: 'HR Executive', type: 'role', dept: 'Human Resources', sla: '1 day', sign: false },
        { name: 'Approve & file', who: 'HR Manager', type: 'role', dept: 'Human Resources', sla: '2 days', sign: true },
      ],
    },
    {
      id: 'simple-approval',
      name: 'Simple Approval',
      department: 'Any',
      description: 'One reviewer, one approver. The quickest route when nothing else fits.',
      appliesTo: ['Any document'],
      retention: 'Default, 5 years',
      steps: [
        { name: 'Review', who: 'Reviewer', type: 'person', dept: 'Any', sla: '1 day', sign: false },
        { name: 'Approve & sign', who: 'Approver', type: 'person', dept: 'Any', sla: '2 days', sign: true },
      ],
    },
    {
      id: 'record-only',
      name: 'File Without Approval',
      department: 'Any',
      description: 'No approval chain. Classify, index and apply retention, for reference material.',
      appliesTo: ['Policy', 'Reference', 'Report'],
      retention: 'Per document type',
      steps: [
        { name: 'Auto-classify & file', who: 'System', type: 'system', dept: 'None', sla: 'Immediate', sign: false },
      ],
    },
  ];

  // Templates a user creates are kept alongside the built-in ones, so a route
  // built on the Templates page is immediately offered in step 3.
  const TPL_KEY = 'dms.templates.v1';

  const templates = {
    custom() {
      try { return JSON.parse(localStorage.getItem(TPL_KEY)) || []; }
      catch (e) { return []; }
    },
    all() { return BUILT_IN_TEMPLATES.concat(templates.custom()); },
    get(id) { return templates.all().find(t => t.id === id) || null; },
    save(tpl) {
      const list = templates.custom();
      const id = tpl.id || ('tpl-' + Math.random().toString(36).slice(2, 9));
      const record = Object.assign({ custom: true }, tpl, { id: id });
      const at = list.findIndex(t => t.id === id);
      if (at >= 0) list[at] = record; else list.push(record);
      try { localStorage.setItem(TPL_KEY, JSON.stringify(list)); } catch (e) { /* private mode */ }
      return record;
    },
    remove(id) {
      const list = templates.custom().filter(t => t.id !== id);
      try { localStorage.setItem(TPL_KEY, JSON.stringify(list)); } catch (e) { /* ignore */ }
    },
    /**
     * A template is only usable if every step says who acts and by when.
     * Returns a list of problems, empty when the template is sound.
     */
    validate(tpl) {
      const problems = [];
      if (!tpl.name || !tpl.name.trim()) problems.push('Give the template a name.');
      if (!tpl.department) problems.push('Choose the owning department.');
      if (!tpl.steps || !tpl.steps.length) problems.push('Add at least one step.');
      (tpl.steps || []).forEach((s, i) => {
        const at = 'Step ' + (i + 1);
        if (!s.name || !s.name.trim()) problems.push(at + ' needs a name.');
        if (!s.dept) problems.push(at + ' needs a department.');
        if (!s.who) problems.push(at + ' needs a role to go to.');
        if (!s.sla) problems.push(at + ' needs a deadline.');
      });
      if ((tpl.steps || []).length && !tpl.steps.some(s => s.sign)) {
        problems.push('At least one step must capture a signature, otherwise nothing is signed off.');
      }
      return problems;
    },
  };

  /* ------------------------------------------------------------------- api */

  // The csrf_token cookie carries a SIGNED token ("<token>.<hmac>"), but the
  // server compares the X-CSRF-Token header against the UNSIGNED token. Sending
  // the cookie value verbatim fails every write with 403, so strip the
  // signature, and keep the freshest value the server hands back in the
  // X-CSRF-Token response header.
  let csrfToken = null;

  function csrfFromCookie() {
    const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    if (!m) return null;
    const signed = decodeURIComponent(m[1]);
    const dot = signed.lastIndexOf('.');
    return dot > 0 ? signed.slice(0, dot) : signed;
  }

  const api = {
    async request(path, options, _retried) {
      const opts = Object.assign({ credentials: 'same-origin' }, options || {});
      opts.headers = Object.assign({}, options && options.headers);

      if (opts.body && !(opts.body instanceof FormData)) {
        opts.headers['Content-Type'] = 'application/json';
        if (typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
      }

      const mutating = opts.method && opts.method !== 'GET';
      if (mutating) {
        const token = csrfToken || csrfFromCookie() || await api.fetchCsrf();
        if (token) opts.headers['X-CSRF-Token'] = token;
      }

      const res = await fetch(path, opts);

      const fresh = res.headers.get('X-CSRF-Token');
      if (fresh) csrfToken = fresh;

      if (res.status === 401) {
        // Never bounce the login page back to itself.
        if (window.location.pathname !== '/login') window.location.href = '/login';
        throw new Error('Not authenticated');
      }

      if (!res.ok) {
        const text = await res.text();
        // A rotated CSRF token is recoverable, so refresh it once and retry.
        if (res.status === 403 && !_retried && /csrf/i.test(text)) {
          csrfToken = null;
          await api.fetchCsrf();
          return api.request(path, options, true);
        }
        throw new Error(text || res.statusText);
      }

      const type = res.headers.get('content-type') || '';
      return type.includes('json') ? res.json() : res.text();
    },
    get(p) { return api.request(p); },
    post(p, body) { return api.request(p, { method: 'POST', body: body }); },
    put(p, body) { return api.request(p, { method: 'PUT', body: body }); },
    del(p) { return api.request(p, { method: 'DELETE' }); },

    /**
     * POST a FormData and report how much of it has gone up.
     *
     * fetch() cannot report upload progress, and a 40 MB scan uploading behind
     * a bar that does not move looks broken. XHR can, so this one case uses it
     * - and reuses the same CSRF token and the same one-shot refresh, because
     * a second copy of that logic is a second thing to get wrong.
     */
    upload(path, formData, onProgress, _retried) {
      return Promise.resolve(csrfToken || csrfFromCookie() || api.fetchCsrf())
        .then(token => new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open('POST', path, true);
          xhr.withCredentials = true;
          if (token) xhr.setRequestHeader('X-CSRF-Token', token);

          if (onProgress) {
            xhr.upload.onprogress = e => {
              if (e.lengthComputable) onProgress(e.loaded / e.total);
            };
          }

          xhr.onload = () => {
            const fresh = xhr.getResponseHeader('X-CSRF-Token');
            if (fresh) csrfToken = fresh;

            if (xhr.status === 401) {
              if (window.location.pathname !== '/login') window.location.href = '/login';
              reject(new Error('Not authenticated'));
              return;
            }
            if (xhr.status >= 200 && xhr.status < 300) {
              const type = xhr.getResponseHeader('content-type') || '';
              try {
                resolve(type.includes('json') ? JSON.parse(xhr.responseText) : xhr.responseText);
              } catch (e) { resolve(xhr.responseText); }
              return;
            }
            if (xhr.status === 403 && !_retried && /csrf/i.test(xhr.responseText || '')) {
              csrfToken = null;
              api.fetchCsrf()
                .then(() => api.upload(path, formData, onProgress, true))
                .then(resolve, reject);
              return;
            }
            reject(new Error(xhr.responseText || xhr.statusText || 'Upload failed'));
          };
          xhr.onerror = () => reject(new Error('The connection dropped during the upload'));
          xhr.onabort = () => reject(new Error('Upload cancelled'));
          xhr.send(formData);
        }));
    },
    async fetchCsrf() {
      try {
        const res = await fetch('/api/csrf-token', { credentials: 'same-origin' });
        const data = await res.json();
        csrfToken = data.csrf_token || res.headers.get('X-CSRF-Token') || csrfFromCookie();
      } catch (e) {
        csrfToken = csrfFromCookie();
      }
      return csrfToken;
    },
    /** Never throws. Returns `fallback` when the endpoint is not available yet. */
    async safe(path, fallback) {
      try { return await api.get(path); } catch (e) { return fallback; }
    },
  };

  /* ------------------------------------------------------------------ flow */

  // Demo continuity. The document uploaded in step 1 is the same one shown in
  // steps 2, 3 and 4, so a walkthrough reads as one continuous act instead of
  // four disconnected screens.
  //
  // Documents, metadata, tags and search are real API data. Process, template
  // and signature state has no server module yet (Phase 2-4 in the README) and
  // lives here until it does.
  /**
   * Browser storage is per-origin, not per-user.
   *
   * That matters more than it sounds. An unscoped signature key meant that
   * whoever signed in next on the same machine was offered the *previous*
   * person's signature to reuse - so an approver could sign a document with
   * their colleague's mark and name without either of them noticing. Every key
   * is therefore scoped to the signed-in user, and everything is cleared on
   * sign-out.
   *
   * `currentUserId` is set by loadUser() during mount, long before anybody can
   * click Approve. While it is unknown, per-user reads return nothing rather
   * than risk handing over somebody else's signature.
   */
  let currentUserId = null;

  const FLOW_KEY = 'dms.flow.v1';
  const SIG_KEY = 'dms.signature.v1';
  const INTAKE_KEY = 'dms.intake.v1';

  // One row of tiles on the Studio. Enough to see what you brought in without
  // the start screen turning into a second document list - that already exists,
  // and it is All Documents.
  const INTAKE_KEEP = 4;

  function userKey(base) {
    return currentUserId ? base + '::' + currentUserId : null;
  }

  /** Wipe every trace of the previous user from this browser. */
  function clearUserStorage() {
    try {
      Object.keys(localStorage)
        .filter(k => k.indexOf('dms.') === 0)
        .forEach(k => localStorage.removeItem(k));
    } catch (e) { /* private mode */ }
  }

  const flow = {
    get() {
      const key = userKey(FLOW_KEY);
      if (!key) return {};
      try { return JSON.parse(localStorage.getItem(key)) || {}; }
      catch (e) { return {}; }
    },
    set(state) {
      const key = userKey(FLOW_KEY);
      if (!key) return state;
      try { localStorage.setItem(key, JSON.stringify(state)); } catch (e) { /* private mode */ }
      return state;
    },
    patch(partial) {
      const next = Object.assign(flow.get(), partial);
      return flow.set(next);
    },
    /**
     * Completion is deliberately different from "the user visited this page".
     * A step becomes unlocked only after its primary action succeeds.
     */
    completedSteps() {
      const s = flow.get();
      return Array.isArray(s.completedSteps) ? s.completedSteps.map(Number).filter(Boolean) : [];
    },
    isComplete(step) {
      return flow.completedSteps().includes(Number(step));
    },
    complete(step) {
      step = Number(step);
      if (!step || step < 1 || step > STEP_COUNT) return flow.get();
      const done = flow.completedSteps();
      if (!done.includes(step)) done.push(step);
      done.sort((a, b) => a - b);
      return flow.patch({
        completedSteps: done,
        step: Math.max.apply(null, done.concat([1]))
      });
    },
    /**
     * Highest contiguous step that is available. Step 1 is always available.
     * Example: completed [1,2] => step 3 is unlocked; completed [1] => step 2.
     */
    reached() {
      const done = new Set(flow.completedSteps());
      let unlocked = 1;
      while (done.has(unlocked) && unlocked < STEP_COUNT) unlocked += 1;
      return unlocked;
    },
    canEnter(step) {
      step = Number(step);
      if (!step || step <= 1) return true;
      const done = new Set(flow.completedSteps());
      for (let n = 1; n < step; n++) {
        if (!done.has(n)) return false;
      }
      return !!flow.doc();
    },
    doc() { return flow.get().doc || null; },
    clear() {
      const key = userKey(FLOW_KEY);
      try { if (key) localStorage.removeItem(key); } catch (e) { /* ignore */ }
    },
    clearForUser(userId) {
      if (!userId) return;
      try { localStorage.removeItem(FLOW_KEY + '::' + userId); } catch (e) { /* ignore */ }
    },

    /* ------------------------------------------------------ recent intake

       What this person last brought into the system, newest first.

       The Studio used to lose its tiles the moment you navigated away, so
       stepping into Review and pressing Back left an empty screen and no sign
       that anything had been uploaded at all. This is deliberately a short
       FIFO queue rather than a full history: the oldest falls off once the row
       is full, because the row is a reminder of what you were just doing, not
       a second repository.

       Only ids are kept. Titles and pictures are re-read from the server on
       the way back, so a document renamed or deleted elsewhere is never
       described here from a stale copy.
    */
    recentUploads() {
      const key = userKey(INTAKE_KEY);
      if (!key) return [];
      try {
        const list = JSON.parse(localStorage.getItem(key));
        return Array.isArray(list) ? list.slice(0, INTAKE_KEEP) : [];
      } catch (e) { return []; }
    },
    rememberUpload(entry) {
      const key = userKey(INTAKE_KEY);
      if (!key || !entry || !entry.id) return;
      // Re-adding the same document moves it to the front rather than
      // appearing twice.
      const next = [entry].concat(
        flow.recentUploads().filter(e => e.id !== entry.id)).slice(0, INTAKE_KEEP);
      try { localStorage.setItem(key, JSON.stringify(next)); } catch (e) { /* full */ }
    },
    forgetUpload(id) {
      const key = userKey(INTAKE_KEY);
      if (!key) return;
      const next = flow.recentUploads().filter(e => e.id !== id);
      try { localStorage.setItem(key, JSON.stringify(next)); } catch (e) { /* ignore */ }
    },

    /**
     * This signer's saved signature.
     *
     * Scoped to the signed-in user. Returns nothing until we know who that is,
     * because offering the wrong person's signature is far worse than making
     * somebody draw theirs again.
     */
    signature() {
      const key = userKey(SIG_KEY);
      if (!key) return null;
      try { return JSON.parse(localStorage.getItem(key)) || null; }
      catch (e) { return null; }
    },
    saveSignature(sig) {
      const key = userKey(SIG_KEY);
      if (!key) return sig;
      try { localStorage.setItem(key, JSON.stringify(sig)); } catch (e) { /* ignore */ }
      return sig;
    },
  };

  /* ---------------------------------------------------------------- toasts */
  function toast(title, message, variant) {
    let host = document.querySelector('.toasts');
    if (!host) {
      host = document.createElement('div');
      host.className = 'toasts';
      document.body.appendChild(host);
    }
    const el = document.createElement('div');
    el.className = 'toast' + (variant === 'danger' ? ' is-danger' : '');
    el.innerHTML = icon(variant === 'danger' ? 'alert' : 'check') +
      '<div><div class="toast__title"></div>' +
      (message ? '<div class="toast__msg"></div>' : '') + '</div>';
    el.querySelector('.toast__title').textContent = title;
    if (message) el.querySelector('.toast__msg').textContent = message;
    host.appendChild(el);
    setTimeout(() => {
      el.classList.add('is-out');
      setTimeout(() => el.remove(), 240);
    }, 3600);
  }

  /* --------------------------------------------------- overlays: modal etc */
  function scrim() {
    let s = document.querySelector('.scrim');
    if (!s) {
      s = document.createElement('div');
      s.className = 'scrim';
      s.addEventListener('click', closeOverlays);
      document.body.appendChild(s);
    }
    return s;
  }

  function openOverlay(el) {
    if (!el) return;
    scrim().classList.add('is-open');
    el.classList.add('is-open');
    const first = el.querySelector('input, textarea, select, button');
    if (first) setTimeout(() => first.focus(), 60);
  }

  function closeOverlays() {
    document.querySelectorAll('.modal.is-open, .drawer.is-open').forEach(m => m.classList.remove('is-open'));
    const s = document.querySelector('.scrim');
    if (s) s.classList.remove('is-open');
  }

  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeOverlays(); });

  /* ------------------------------------------------------------ shell HTML */
  function initials(name) {
    if (!name) return 'U';
    return name.trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
  }

  function renderSidebar(active) {
    const reached = flow.reached();
    const personalFolderPage =
      window.location.pathname === '/documents' &&
      new URLSearchParams(window.location.search).get('personal') === '1';

    const groups = NAV.map(group => {
      const items = group.items.map(item => {
        const isActive = personalFolderPage
          ? item.id === 'my-folder'
          : item.id === active;
        const count = item.count
          ? '<span class="nav-link__count' + (item.alert ? ' is-alert' : '') +
            '" data-nav-count="' + item.id + '">' + item.count + '</span>'
          // A placeholder the loader fills in, so the badge appears only when
          // there is genuinely something to show.
          : '<span class="nav-link__count is-alert" data-nav-count="' + item.id + '" hidden></span>';
        const done = group.journey && flow.isComplete(item.n);
        const locked = group.journey && item.n > reached;
        const lead = group.journey
          ? '<span class="nav-link__step">' + (done ? '&#10003;' : item.n) + '</span>'
          : icon(item.icon);
        const href = group.journey
          ? (locked ? '#' : journeyHref(item.href))
          : item.href;
        return '<li><a class="nav-link' + (isActive ? ' is-active' : '') +
          (done ? ' is-done' : '') + (locked ? ' is-locked' : '') +
          '" href="' + href + '"' +
          (locked ? ' data-journey-locked="1" aria-disabled="true" title="Complete the previous step first"' : '') +
          '>' + lead + '<span>' + item.label + '</span>' + count + '</a></li>';
      }).join('');
      return '<div class="nav-group"><div class="nav-group__label">' + group.label + '</div><ul>' + items + '</ul></div>';
    }).join('');

    // The real wordmark, at the size it was drawn to be read. Squeezing a
    // horizontal logo into a square tile destroys it, so the brand gets the
    // width it needs and the product name sits underneath.
    //
    // There is no "New document" button here. Document Studio is the first
    // item in the menu directly below and does exactly the same job, so the
    // button was a second door onto the same room.
    return '' +
      '<a class="sidebar__brand" href="/">' +
        '<img class="sidebar__logo" src="/static/ui/assets/brand/harman-white.png" alt="HARMAN">' +
        '<span class="sidebar__product">Document Management</span>' +
      '</a>' +
      '<nav class="sidebar__nav">' + groups + '</nav>' +
      '<div class="sidebar__foot">' + renderUserChip() + '</div>';
  }

  /**
   * Who is signed in, and the way into Settings.
   *
   * Settings has no menu entry of its own: it lives behind this chip, which is
   * where people look for the things that belong to their own account. That
   * makes the cog worth showing - the chip is now the only route there, so it
   * has to look like a control rather than a caption.
   *
   * Settings is administrator-only, so for anybody else this is a plain label.
   * It used to be a link for everyone, and a member who pressed their own name
   * was silently bounced to their task list.
   */
  function renderUserChip() {
    const inner =
      '<span class="avatar" data-user-initials></span>' +
      '<span class="user-chip__meta">' +
        '<span class="user-chip__name truncate" data-user-name>Signed in</span>' +
        '<span class="user-chip__role truncate" data-user-role>Loading…</span>' +
      '</span>';

    return NAV === NAV_ADMIN
      ? '<a class="user-chip" href="/settings#profile">' + inner +
          icon('settings', 'user-chip__cog') + '</a>'
      : '<div class="user-chip user-chip--static">' + inner + '</div>';
  }

  /** Keep the current document attached while moving through the five-step journey. */
  function journeyHref(href) {
    try {
      if (!href) return href;
      const u = new URL(href, window.location.origin);

      // Step 1 always means "start a new document". Never carry the current
      // document id back into Studio, otherwise a fresh upload reopens the last
      // document instead of showing the clean start screen.
      if (u.pathname === '/studio') return '/studio?new=1';

      const current = new URLSearchParams(window.location.search).get('id') ||
        (flow.doc() && flow.doc().id);
      if (!current) return u.pathname + u.search + u.hash;

      u.searchParams.set('id', current);
      return u.pathname + u.search + u.hash;
    } catch (e) { return href; }
  }

  /** The horizontal five-step spine shown at the top of every journey screen. */
  function renderJourney(activeId) {
    const reached = flow.reached();
    const parts = JOURNEY.map(step => {
      let state = '';
      const done = flow.isComplete(step.n);
      const locked = step.n > reached;
      if (step.id === activeId) state = ' is-current';
      else if (done) state = ' is-done';
      else if (locked) state = ' is-locked';
      const mark = (done && step.id !== activeId) ? icon('check') : step.n;
      const href = locked ? '#' : journeyHref(step.href);
      return '<a class="journey__step' + state + '" href="' + href + '"' +
        (locked ? ' data-journey-locked="1" aria-disabled="true" title="Complete the previous step first"' : '') + '>' +
        '<span class="journey__num">' + mark + '</span>' +
        '<span><span class="journey__label">' + step.label + '</span>' +
        '<span class="journey__hint" style="display:block">' + step.hint + '</span></span></a>';
    });
    return '<nav class="journey">' +
      parts.join('<span class="journey__sep">' + icon('chevronRight') + '</span>') +
      '</nav>';
  }

  /**
   * Hard gate the five-step journey. The visual lock is not enough: a user can
   * type /review, /process, /track or /publish directly into the address bar.
   */
  function enforceJourneyAccess() {
    const stepNo = Number(document.body && document.body.dataset.step || 0);
    if (!stepNo || stepNo <= 1) return true;
    if (flow.canEnter(stepNo)) return true;

    const reached = flow.reached();
    const doc = flow.doc();
    const target = reached <= 1
      ? '/studio?new=1'
      : JOURNEY[Math.max(0, reached - 1)].href +
        (doc && doc.id ? '?id=' + encodeURIComponent(doc.id) : '');
    window.location.replace(target);
    return false;
  }

  /**
   * The top bar, including the way back out of this screen.
   *
   * A page declares its parent with data-crumb + data-crumb-href on <body>.
   * The crumb used to be a bare <span>: it looked like a breadcrumb and did
   * nothing, which is worse than having none, because a detail screen reached
   * by a deep link then had no way back at all. Given an href it becomes a
   * real link, preceded by a chevron so it is unmistakably a way back.
   *
   * A page with no declared parent gets no crumb. That is correct for the
   * destinations named in the sidebar, which are where the sidebar takes you.
   */
  function renderTopbar(title, crumb, crumbHref, actions) {
    const back = crumb
      ? (crumbHref
          ? '<a class="topbar__back" href="' + crumbHref + '">' +
              icon('chevronLeft') + '<span>' + crumb + '</span></a>' +
            icon('chevronRight', 'topbar__sep')
          : '<span class="topbar__crumb">' + crumb + '</span>' +
            icon('chevronRight', 'topbar__sep'))
      : '';

    // No bell. There is no notifications module behind one, and what it would
    // have announced is now counted on the menu items it concerns - next to
    // the screen that can actually do something about it.
    //
    // Sign out says "Sign out". It was a 17px glyph with a tooltip, which is
    // small for the one action you cannot undo by pressing Back.
    return '' +
      '<button class="icon-btn sidebar-toggle" data-sidebar-toggle aria-label="Menu">' + icon('menu') + '</button>' +
      back +
      '<span class="topbar__title">' + title + '</span>' +
      '<div class="topbar__actions">' +
        (actions || '') +
        '<button class="btn signout" data-logout>' +
          icon('logout') + '<span>Sign out</span></button>' +
      '</div>';
  }

  /* ------------------------------------------------------------------ init */
  /**
   * Make every date field say what it means.
   *
   * A browser draws <input type="date"> in ITS OWN locale, and no page can
   * change that - on a machine set to US English the box reads mm/dd/yyyy
   * however the rest of the product is written. So each one gets a line
   * underneath spelling the chosen date out in day-month-year, and "06-08" is
   * never left to be read as either August or June.
   *
   *   data-today     start on today's date in India rather than empty
   *   data-not-past  refuse a date already gone, for deadlines
   */
  function wireDates() {
    document.querySelectorAll('input[type="date"]').forEach(input => {
      if (input.dataset.dateWired) return;
      input.dataset.dateWired = '1';

      if (input.hasAttribute('data-today') && !input.value) input.value = fmt.today();
      if (input.hasAttribute('data-not-past')) input.min = fmt.today();

      // The echo goes in the field's existing hint when it has one, so a field
      // that already explains itself does not grow a second line.
      const field = input.closest('.field') || input.parentElement;
      let echo = field && field.querySelector('[data-date-echo]');
      if (!echo && field) {
        echo = document.createElement('span');
        echo.className = 'field__hint';
        echo.setAttribute('data-date-echo', '');
        const existing = field.querySelector('.field__hint');
        if (existing && existing !== echo) existing.insertAdjacentElement('afterend', echo);
        else input.insertAdjacentElement('afterend', echo);
      }

      const show = () => {
        if (!echo) return;
        const readable = fmt.fromInput(input.value);
        echo.textContent = readable ? readable + '  (day-month-year, IST)' : '';
      };
      input.addEventListener('change', show);
      input.addEventListener('input', show);
      // Setting .value from code fires neither event, so a page that fills the
      // field in later would leave the line beneath it describing the previous
      // value. refreshDates() is how those pages put it right.
      input._dateEcho = show;
      show();
    });
  }

  /** Re-read every date field after code has changed one. */
  function refreshDates() {
    wireDates();
    document.querySelectorAll('input[type="date"]').forEach(i => {
      if (typeof i._dateEcho === 'function') i._dateEcho();
    });
  }

  function mount() {
    const body = document.body;
    const active = body.dataset.page || '';
    const title = body.dataset.title || 'DMS';
    const crumb = body.dataset.crumb || '';
    const crumbHref = body.dataset.crumbHref || '';

    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.innerHTML = renderSidebar(active);

    const topbar = document.getElementById('topbar');
    if (topbar) {
      topbar.innerHTML = renderTopbar(title, crumb, crumbHref, '');
      // Move the page's own action nodes rather than copying their markup, so
      // any handler or reference a page attached to them keeps working.
      const slot = document.getElementById('topbar-actions');
      if (slot) {
        const host = topbar.querySelector('.topbar__actions');
        const frag = document.createDocumentFragment();
        while (slot.firstChild) frag.appendChild(slot.firstChild);
        host.insertBefore(frag, host.firstChild);
        slot.remove();
      }
    }

    // Journey screens are gated by completed actions, not by page visits.
    const stepNo = Number(body.dataset.step || 0);
    const host = document.querySelector('[data-journey]');
    if (stepNo && host) host.innerHTML = renderJourney(active);

    // Inline icons declared as <i data-icon="name"></i>
    document.querySelectorAll('[data-icon]').forEach(el => {
      el.outerHTML = icon(el.dataset.icon, el.className || '');
    });

    wireDates();

    // Sidebar toggle (mobile)
    document.addEventListener('click', e => {
      const t = e.target.closest('[data-sidebar-toggle]');
      if (t && sidebar) sidebar.classList.toggle('is-open');
      else if (sidebar && sidebar.classList.contains('is-open') && !e.target.closest('.sidebar')) {
        sidebar.classList.remove('is-open');
      }
    });

    // Locked workflow items are deliberately non-navigable. Give the user a
    // short explanation instead of a dead-looking click.
    document.addEventListener('click', e => {
      const locked = e.target.closest('[data-journey-locked]');
      if (!locked) return;
      e.preventDefault();
      toast('Step is locked', 'Complete the previous step before opening this one.');
    });

    // Logout. Everything this user left in the browser goes with them: the
    // next person to sign in on this machine must not inherit a signature, a
    // half-finished document or a saved approval route.
    document.addEventListener('click', async e => {
      if (!e.target.closest('[data-logout]')) return;
      try { await api.post('/api/auth/logout', {}); } catch (err) { /* sign out locally anyway */ }
      clearUserStorage();
      currentUserId = null;
      window.location.href = '/login';
    });

    // Tabs: [data-tabs] container, buttons carry data-tab, panels carry data-panel
    document.querySelectorAll('[data-tabs]').forEach(group => {
      group.addEventListener('click', e => {
        const btn = e.target.closest('[data-tab]');
        if (!btn) return;
        const scope = group.dataset.tabs;
        group.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('is-active', b === btn));
        document.querySelectorAll('[data-panel][data-scope="' + scope + '"]').forEach(p => {
          p.classList.toggle('is-active', p.dataset.panel === btn.dataset.tab);
        });
      });
    });

    // Segmented controls
    document.querySelectorAll('.segmented').forEach(seg => {
      seg.addEventListener('click', e => {
        const btn = e.target.closest('button');
        if (!btn) return;
        seg.querySelectorAll('button').forEach(b => b.classList.toggle('is-active', b === btn));
        seg.dispatchEvent(new CustomEvent('segment', { detail: btn.dataset.value, bubbles: true }));
      });
    });

    // Org tree expand / collapse
    document.addEventListener('click', e => {
      const row = e.target.closest('.org-node__row');
      if (!row) return;
      const node = row.parentElement;
      if (node.querySelector('.org-node__kids')) node.classList.toggle('is-open');
      document.querySelectorAll('.org-node__row.is-active').forEach(r => r.classList.remove('is-active'));
      row.classList.add('is-active');
    });

    // Overlay openers / closers
    document.addEventListener('click', e => {
      const opener = e.target.closest('[data-open]');
      if (opener) { openOverlay(document.getElementById(opener.dataset.open)); return; }
      if (e.target.closest('[data-close]')) closeOverlays();
    });

    // Kept so a page can await the answer before it draws anything that
    // depends on who is signed in. Without it, isAdmin() is a race: a page
    // that renders quickly hides an administrator's own buttons.
    resolveReady(loadUser());
  }

  let resolveReady;
  const ready = new Promise(res => { resolveReady = p => res(p); });

  async function loadUser() {
    const me = await api.safe('/api/auth/me', null);

    // Everything user-scoped in this browser hangs off this. It is set before
    // anything can read a saved signature or an in-progress document.
    currentUserId = me ? me.id : null;
    window.DMS.me = me;

    // A successful login starts a fresh document journey. This prevents the
    // previous browser session from reopening its last document on Review,
    // Process, Track or Publish. Repository data is untouched.
    let workflowReset = false;
    try {
      workflowReset = sessionStorage.getItem('dms.resetWorkflowOnLogin') === '1';
      if (workflowReset) sessionStorage.removeItem('dms.resetWorkflowOnLogin');
    } catch (e) { /* private mode */ }

    // Opening Studio without a document id is also an explicit new-document
    // entry point. Only an /studio?id=... URL means edit an existing document.
    const studioIsNew = window.location.pathname === '/studio' &&
      !new URLSearchParams(window.location.search).get('id');

    if (me && (workflowReset || studioIsNew)) {
      flow.clear();
    }

    // Screens like Approval and Publishing are administrator-only and redirect
    // anyone else to their task list. A button that silently sends you
    // somewhere you did not ask to go reads as a broken product, so anything
    // marked data-admin-only is removed for everybody else.
    if (!(me && me.is_admin)) {
      document.querySelectorAll('[data-admin-only]').forEach(el => el.remove());
    }

    // The navigation follows who is signed in, so re-render now that we know.
    // mount() drew the smaller menu; this grows it for an administrator.
    const wanted = me && me.is_admin ? NAV_ADMIN : NAV_MEMBER;
    const navChanged = wanted !== NAV;
    if (navChanged) NAV = wanted;

    // Re-render after loadUser because the flow may have just been reset.
    // Otherwise the first paint could still show the previous session's
    // completed steps.
    if (navChanged || workflowReset || studioIsNew) {
      const sidebar = document.getElementById('sidebar');
      if (sidebar) sidebar.innerHTML = renderSidebar(document.body.dataset.page || '');
      const journeyHost = document.querySelector('[data-journey]');
      if (journeyHost) journeyHost.innerHTML = renderJourney(document.body.dataset.page || '');
    }

    // Enforce the same gate for direct URLs after the signed-in user is known.
    // This also prevents an old URL from bypassing the disabled sidebar.
    if (!enforceJourneyAccess()) return;

    if (document.querySelector('[data-user-name]')) {
      const name = (me && (me.full_name || me.username)) || 'Signed in';
      const role = me
        ? (me.is_admin ? 'System administrator'
           : [me.job_title, me.department].filter(Boolean).join(', ') || 'Member')
        : 'Session';
      document.querySelectorAll('[data-user-name]').forEach(el => el.textContent = name);
      document.querySelectorAll('[data-user-role]').forEach(el => el.textContent = role);
      document.querySelectorAll('[data-user-initials]')
        .forEach(el => el.textContent = initials(name));
    }

    loadCounts();
  }

  /**
   * The sidebar badges, counted on the server.
   *
   * These replace the row of banners that used to sit across the top of the
   * Studio. A banner announces something and then makes you find the screen
   * that deals with it; a count sits on that screen's own menu entry, so the
   * notice and the way to act on it are the same thing.
   *
   * A navigation badge is a promise that something is waiting. It must
   * therefore be real, and it must disappear when the work is done - so every
   * number here comes from the server and a zero hides the badge entirely.
   */
  async function loadCounts() {
    if (!document.querySelector('[data-nav-count]')) return;
    const stats = await api.safe('/api/workflow/stats', null);

    // id, how many, and whether it is late rather than merely waiting.
    const badges = stats ? [
      ['tasks', stats.my_tasks, stats.my_tasks_overdue > 0],
      ['publish', stats.ready_to_publish, false],
      ['track', stats.awaiting_changes, false],
    ] : [];

    document.querySelectorAll('[data-nav-count]').forEach(el => { el.hidden = true; });

    badges.forEach(([id, count, alert]) => {
      const el = document.querySelector('[data-nav-count="' + id + '"]');
      if (!el || !count) return;
      el.hidden = false;
      el.textContent = count > 99 ? '99+' : count;
      el.classList.toggle('is-alert', !!alert);
    });
  }

  /* --------------------------------------------------------------- helpers */

  /**
   * Parse a timestamp the server sent.
   *
   * The API stores and returns UTC, but its timestamps carry no zone: they
   * look like "2026-08-05T08:34:13" or "2026-08-05 08:34:13". JavaScript reads
   * the first form as UTC and the second as LOCAL time, and reads neither the
   * way the server meant. In IST that made a draft saved a moment ago read
   * "5h ago", and dates near midnight land on the wrong day.
   *
   * So: normalise the separator, and mark it UTC unless it already says
   * otherwise. A value that already carries "Z" or "+05:30" is left alone,
   * because that one is telling the truth about itself.
   */
  function parseTime(v) {
    if (!v) return null;
    if (v instanceof Date) return isNaN(v) ? null : v;
    if (typeof v === 'number') return new Date(v);

    let s = String(v).trim().replace(' ', 'T');
    if (!/(Z|[+-]\d{2}:?\d{2})$/.test(s)) s += 'Z';
    const d = new Date(s);
    if (!isNaN(d)) return d;

    const raw = new Date(v);          // last resort: whatever the browser makes of it
    return isNaN(raw) ? null : raw;
  }

  /* ------------------------------------------------------------ time zone

     Everything is stored in UTC and shown in India Standard Time, in
     day-month-year. Both are stated explicitly rather than left to the
     machine: `toLocaleDateString(undefined, …)` follows whatever locale and
     zone the computer happens to carry, so the same document read on a laptop
     set to US English showed a different date from the same document on the
     one next to it - and "06/08" meant August on one and June on the other.
     A document management system cannot be ambiguous about dates. */
  const ZONE = 'Asia/Kolkata';

  /** The IST calendar parts of an instant, as numbers. */
  function istParts(d) {
    const bits = {};
    new Intl.DateTimeFormat('en-GB', {
      timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }).formatToParts(d).forEach(p => { bits[p.type] = p.value; });
    // Midnight comes back as "24" from some engines.
    if (bits.hour === '24') bits.hour = '00';
    return bits;
  }

  const fmt = {
    bytes(n) {
      if (!n && n !== 0) return 'Not set';
      const u = ['B', 'KB', 'MB', 'GB', 'TB'];
      let i = 0;
      while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
      return (i === 0 ? n : n.toFixed(1)) + ' ' + u[i];
    },

    /** 06-08-2026 */
    date(v) {
      const d = parseTime(v);
      if (!d) return 'Not set';
      const p = istParts(d);
      return p.day + '-' + p.month + '-' + p.year;
    },

    /** 06-08-2026, 14:30 */
    dateTime(v) {
      const d = parseTime(v);
      if (!d) return 'Not set';
      const p = istParts(d);
      return p.day + '-' + p.month + '-' + p.year + ', ' + p.hour + ':' + p.minute;
    },

    /** 06 Aug 2026 - for prose, where a run of digits reads poorly. */
    dateLong(v) {
      const d = parseTime(v);
      return d ? new Intl.DateTimeFormat('en-GB', {
        timeZone: ZONE, day: '2-digit', month: 'short', year: 'numeric',
      }).format(d) : 'Not set';
    },

    ago(v) {
      const d = parseTime(v);
      if (!d) return 'Not set';
      const s = (Date.now() - d.getTime()) / 1000;
      // Clocks drift and a record written this instant can read a second into
      // the future. "in 1s ago" is nonsense; "just now" is true.
      if (s < 60) return 'just now';
      if (s < 3600) return Math.floor(s / 60) + 'm ago';
      if (s < 86400) return Math.floor(s / 3600) + 'h ago';
      if (s < 604800) return Math.floor(s / 86400) + 'd ago';
      return fmt.date(v);
    },

    /**
     * Today in India, as YYYY-MM-DD.
     *
     * That spelling is not a display format - it is the only value an
     * <input type="date"> accepts. Taken from the IST calendar rather than the
     * machine's, so somebody working late in India gets today's date and not
     * yesterday's off a laptop still set to UTC.
     */
    today() {
      const p = istParts(new Date());
      return p.year + '-' + p.month + '-' + p.day;
    },

    /** Turn an input's YYYY-MM-DD back into 06-08-2026 for reading. */
    fromInput(value) {
      const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || '').trim());
      return m ? m[3] + '-' + m[2] + '-' + m[1] : '';
    },

    num(n) { return (n == null ? 'Not set' : Number(n).toLocaleString()); },
    parse: parseTime,
    zone: ZONE,
  };

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  /** Confirmation dialog for destructive actions. Always red, always explicit. */
  function confirmDanger(opts) {
    return new Promise(resolve => {
      const el = document.createElement('div');
      el.className = 'modal';
      el.innerHTML =
        '<div class="modal__head"><div class="row-top">' +
          '<span class="tile-icon tile-icon--danger">' + icon('alert') + '</span>' +
          '<div><h3 class="t-h2">' + escapeHtml(opts.title) + '</h3>' +
          '<p class="t-sm muted mt-1">' + escapeHtml(opts.message || '') + '</p></div>' +
        '</div></div>' +
        '<div class="modal__foot"><div class="btn-row">' +
          '<button class="btn btn--outline" data-no>Cancel</button>' +
          '<button class="btn btn--danger" data-yes>' + escapeHtml(opts.confirmLabel || 'Delete') + '</button>' +
        '</div></div>';
      document.body.appendChild(el);
      openOverlay(el);
      const done = v => { closeOverlays(); setTimeout(() => el.remove(), 260); resolve(v); };
      el.querySelector('[data-yes]').onclick = () => done(true);
      el.querySelector('[data-no]').onclick = () => done(false);
    });
  }

  /* ------------------------------------------------------------- signature */

  /**
   * Signature pad. Draw, type, or upload an image.
   * Resolves to { dataUrl, name, method } and remembers it for next time.
   */
  function signaturePad(userName, userRole) {
    return new Promise(resolve => {
      const name = userName || (document.querySelector('[data-user-name]') || {}).textContent || 'Approver';
      // The designation printed under the mark. Defaults to the signer's job
      // title and is editable, because the title that belongs on a document is
      // the one they hold for *this* signature.
      const role = userRole !== undefined && userRole !== null
        ? userRole
        : ((document.querySelector('[data-user-role]') || {}).textContent || '');
      const cleanRole = ['Loading…', 'Session', 'Member'].includes(role) ? '' : role;
      const el = document.createElement('div');
      el.className = 'modal';
      el.innerHTML =
        '<div class="modal__head">' +
          '<h3 class="t-h2">Sign this approval</h3>' +
          '<p class="t-sm muted mt-1">Your signature is recorded against your identity and shown ' +
          'in the document\'s status trail.</p>' +
        '</div>' +
        '<div class="modal__body">' +
          '<div class="tabs" data-sig-tabs>' +
            '<button data-sig="draw" class="is-active">Draw</button>' +
            '<button data-sig="type">Type</button>' +
            '<button data-sig="upload">Upload image</button>' +
          '</div>' +
          '<div data-sig-panel="draw">' +
            '<div class="sig-pad" data-pad>' +
              '<canvas></canvas>' +
              '<div class="sig-pad__baseline"></div>' +
              '<div class="sig-pad__hint">Draw your signature above the line</div>' +
            '</div>' +
            '<div class="row mt-2"><button class="btn btn--sm btn--ghost" data-clear>Clear</button></div>' +
          '</div>' +
          '<div data-sig-panel="type" hidden>' +
            '<label class="field"><span class="field__label">Full name as it should appear</span>' +
            '<input class="input" data-typed value="' + escapeHtml(name) + '"></label>' +
            '<div class="card card--flat card--pad mt-2" style="text-align:center">' +
              '<div class="sig-typed" data-typed-preview>' + escapeHtml(name) + '</div>' +
            '</div>' +
          '</div>' +
          '<div data-sig-panel="upload" hidden>' +
            '<div class="dropzone" data-upload-zone style="padding:30px">' +
              '<h3 class="t-h3">Choose a signature image</h3>' +
              '<p class="t-sm muted mt-1">PNG with a transparent background works best</p>' +
              '<input type="file" accept="image/*" hidden data-sig-file>' +
            '</div>' +
            '<div class="mt-2 hidden" data-upload-preview style="text-align:center"></div>' +
          '</div>' +
          '<div class="divider"></div>' +
          '<div class="grid grid-2">' +
            '<label class="field" style="margin:0"><span class="field__label">Name as it appears</span>' +
              '<input class="input" data-sig-name value="' + escapeHtml(name) + '"></label>' +
            '<label class="field" style="margin:0"><span class="field__label">Designation</span>' +
              '<input class="input" data-sig-role value="' + escapeHtml(cleanRole) + '" ' +
              'placeholder="e.g. Head of Finance">' +
              '<span class="field__hint">Printed under your signature on the document.</span></label>' +
          '</div>' +
          '<label class="check mt-2"><input type="checkbox" checked data-remember>' +
            '<span class="check__box">' + icon('check') + '</span>' +
            '<span class="check__text">Remember my signature for future approvals</span></label>' +
        '</div>' +
        '<div class="modal__foot"><div class="btn-row">' +
          '<button class="btn btn--outline" data-cancel>Cancel</button>' +
          '<button class="btn btn--primary" data-confirm>' + icon('stamp') + 'Apply signature</button>' +
        '</div></div>';

      document.body.appendChild(el);
      openOverlay(el);

      let method = 'draw';
      let uploaded = null;

      // Tabs
      el.querySelector('[data-sig-tabs]').addEventListener('click', e => {
        const btn = e.target.closest('[data-sig]');
        if (!btn) return;
        method = btn.dataset.sig;
        el.querySelectorAll('[data-sig]').forEach(b => b.classList.toggle('is-active', b === btn));
        el.querySelectorAll('[data-sig-panel]').forEach(p => {
          p.hidden = p.dataset.sigPanel !== method;
        });
      });

      // Draw
      const pad = el.querySelector('[data-pad]');
      const canvas = pad.querySelector('canvas');
      const ctx = canvas.getContext('2d');
      let drawing = false, dirty = false;

      function sizeCanvas() {
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.scale(dpr, dpr);
        ctx.lineWidth = 2.4;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.strokeStyle = '#0A2A3D';
      }
      setTimeout(sizeCanvas, 30);

      const point = e => {
        const r = canvas.getBoundingClientRect();
        return { x: e.clientX - r.left, y: e.clientY - r.top };
      };
      canvas.addEventListener('pointerdown', e => {
        drawing = true; dirty = true;
        pad.classList.add('is-signed');
        canvas.setPointerCapture(e.pointerId);
        const p = point(e);
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
      });
      canvas.addEventListener('pointermove', e => {
        if (!drawing) return;
        const p = point(e);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
      });
      canvas.addEventListener('pointerup', () => { drawing = false; });
      canvas.addEventListener('pointerleave', () => { drawing = false; });

      el.querySelector('[data-clear]').onclick = () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        pad.classList.remove('is-signed');
        dirty = false;
      };

      // Type
      const typed = el.querySelector('[data-typed]');
      const typedPreview = el.querySelector('[data-typed-preview]');
      typed.addEventListener('input', () => { typedPreview.textContent = typed.value; });

      // Upload
      const zone = el.querySelector('[data-upload-zone]');
      const file = el.querySelector('[data-sig-file]');
      const preview = el.querySelector('[data-upload-preview]');
      zone.onclick = () => file.click();
      file.onchange = () => {
        const f = file.files && file.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = () => {
          uploaded = reader.result;
          preview.classList.remove('hidden');
          preview.innerHTML = '<img src="' + uploaded + '" alt="Signature" style="max-height:110px;margin:0 auto">';
        };
        reader.readAsDataURL(f);
      };

      /** Render the typed name onto a canvas so every method yields an image. */
      function typedToDataUrl(text) {
        const c = document.createElement('canvas');
        c.width = 640; c.height = 200;
        const g = c.getContext('2d');
        g.fillStyle = '#0A2A3D';
        g.font = 'italic 64px "Segoe Script", "Brush Script MT", cursive';
        g.textAlign = 'center';
        g.textBaseline = 'middle';
        g.fillText(text, 320, 100);
        return c.toDataURL('image/png');
      }

      const finish = value => {
        closeOverlays();
        setTimeout(() => el.remove(), 260);
        resolve(value);
      };

      el.querySelector('[data-cancel]').onclick = () => finish(null);

      el.querySelector('[data-confirm]').onclick = () => {
        let dataUrl = null;
        if (method === 'draw') {
          if (!dirty) { toast('Nothing drawn yet', 'Draw your signature, or switch to Type.', 'danger'); return; }
          dataUrl = canvas.toDataURL('image/png');
        } else if (method === 'type') {
          if (!typed.value.trim()) { toast('Enter a name', '', 'danger'); return; }
          dataUrl = typedToDataUrl(typed.value.trim());
        } else {
          if (!uploaded) { toast('Choose an image first', '', 'danger'); return; }
          dataUrl = uploaded;
        }
        const sig = {
          dataUrl: dataUrl,
          name: (el.querySelector('[data-sig-name]').value || '').trim() ||
                (method === 'type' ? typed.value.trim() : name),
          designation: (el.querySelector('[data-sig-role]').value || '').trim(),
          method: method,
          signedAt: new Date().toISOString(),
        };
        if (el.querySelector('[data-remember]').checked) flow.saveSignature(sig);
        finish(sig);
      };
    });
  }

  /** Small HTML block that renders a signature in a trail or status card. */
  function signatureMark(sig, subtitle) {
    if (!sig) return '';
    return '<div class="sig-mark">' +
      '<span class="sig-mark__seal">' + icon('stamp') + '</span>' +
      '<img src="' + sig.dataUrl + '" alt="Signature of ' + escapeHtml(sig.name) + '">' +
      '<span class="sig-mark__meta"><strong>' + escapeHtml(sig.name) + '</strong>' +
      escapeHtml(subtitle || ('Signed ' + fmt.dateTime(sig.signedAt))) + '</span>' +
      '</div>';
  }

  /* -------------------------------------------------------------- decision */

  /**
   * The one decision surface used everywhere: approve & sign, request changes,
   * or reject. Reject always requires a reason, which is the whole point of it.
   * Resolves to { action, reason, comment, signature } or null if cancelled.
   */
  function decide(action, opts) {
    opts = opts || {};
    // Whether this approval needs a signature is a property of the step, not
    // of the person or the screen. Steps that do not require one must not ask
    // for one: a dialog that demands a signature nobody asked for teaches
    // people to sign without reading.
    const needsSignature = opts.requiresSignature !== false;

    const config = {
      approve: {
        title: needsSignature ? 'Approve and sign' : 'Approve',
        lead: 'You are approving <strong>' + escapeHtml(opts.subject || 'this document') + '</strong>.' +
              (needsSignature
                ? ' This step requires your signature.'
                : ' This step records your approval without a signature.'),
        confirm: needsSignature ? 'Continue to signature' : 'Approve',
        btn: 'btn--primary', icon: needsSignature ? 'stamp' : 'check',
        reasons: null, commentLabel: 'Comment (optional)', commentRequired: false,
      },
      changes: {
        title: 'Request changes',
        lead: 'This goes back to the previous step with your notes.',
        confirm: 'Send back', btn: 'btn--warn', icon: 'refresh',
        reasons: ['Missing supporting document', 'Incorrect amount or figure',
                  'Wrong approver or department', 'Metadata needs correction', 'Other'],
        commentLabel: 'What needs to change?', commentRequired: true,
      },
      reject: {
        title: 'Reject this document',
        lead: 'Rejection ends the process. The requester is notified with your reason.',
        confirm: 'Reject document', btn: 'btn--danger', icon: 'x',
        reasons: ['Duplicate submission', 'Not a valid business document',
                  'Policy or compliance breach', 'Commercially not acceptable',
                  'Superseded by a newer version', 'Other'],
        commentLabel: 'Add a comment', commentRequired: false,
      },
    }[action];

    return new Promise(resolve => {
      const el = document.createElement('div');
      el.className = 'modal';
      el.innerHTML =
        '<div class="modal__head">' +
          '<div class="row-top">' +
            '<span class="tile-icon ' +
              (action === 'reject' ? 'tile-icon--danger' : action === 'changes' ? 'tile-icon--warn' : '') + '">' +
              icon(config.icon) + '</span>' +
            '<div><h3 class="t-h2">' + config.title + '</h3>' +
            '<p class="t-sm muted mt-1">' + config.lead + '</p></div>' +
          '</div>' +
        '</div>' +
        '<div class="modal__body">' +
          (config.reasons
            ? '<label class="field"><span class="field__label">Reason ' +
              (action === 'reject' ? '(required)' : '') + '</span><select class="select" data-reason>' +
              '<option value="">Select a reason…</option>' +
              config.reasons.map(r => '<option>' + escapeHtml(r) + '</option>').join('') +
              '</select></label>'
            : '') +
          '<label class="field"><span class="field__label">' + config.commentLabel + '</span>' +
            '<textarea class="textarea" data-comment placeholder="Recorded in the status trail and the activity log"></textarea></label>' +
          (action === 'approve'
            ? '<div class="banner mt-2">' + icon('info') + '<div>' +
              (needsSignature
                ? 'Your signature is applied on the next screen and locks this version.'
                : 'Your approval is recorded against your name in the status trail. ' +
                  'No signature is required for this step.') +
              '</div></div>'
            : '') +
        '</div>' +
        '<div class="modal__foot"><div class="btn-row">' +
          '<button class="btn btn--outline" data-cancel>Cancel</button>' +
          '<button class="btn ' + config.btn + '" data-go>' + icon(config.icon) + config.confirm + '</button>' +
        '</div></div>';

      document.body.appendChild(el);
      openOverlay(el);

      const finish = value => {
        closeOverlays();
        setTimeout(() => el.remove(), 260);
        resolve(value);
      };

      el.querySelector('[data-cancel]').onclick = () => finish(null);

      el.querySelector('[data-go]').onclick = async () => {
        const reasonEl = el.querySelector('[data-reason]');
        const comment = el.querySelector('[data-comment]').value.trim();
        const reason = reasonEl ? reasonEl.value : '';

        if (action === 'reject' && !reason) {
          toast('A reason is required', 'Rejections must say why.', 'danger');
          return;
        }
        if (config.commentRequired && !comment) {
          toast('Add a note', 'Say what needs to change.', 'danger');
          return;
        }

        if (action !== 'approve') {
          finish({ action: action, reason: reason, comment: comment, at: new Date().toISOString() });
          return;
        }

        closeOverlays();
        setTimeout(() => el.remove(), 260);

        // Approval without a signature is a complete decision on its own.
        if (!needsSignature) {
          resolve({ action: 'approve', reason: '', comment: comment,
                    signature: null, at: new Date().toISOString() });
          return;
        }

        // Approve & sign → collect the signature.
        const existing = flow.signature();
        let sig = existing;
        if (existing) {
          const reuse = await confirmReuse(existing);
          if (reuse === null) { resolve(null); return; }
          if (reuse === false) sig = await signaturePad();
        } else {
          sig = await signaturePad();
        }
        if (!sig) { resolve(null); return; }
        resolve({ action: 'approve', reason: '', comment: comment, signature: sig, at: new Date().toISOString() });
      };
    });
  }

  /** Offer the stored signature rather than making people re-draw every time. */
  function confirmReuse(sig) {
    return new Promise(resolve => {
      const el = document.createElement('div');
      el.className = 'modal';
      el.innerHTML =
        '<div class="modal__head"><h3 class="t-h2">Apply your signature</h3>' +
        '<p class="t-sm muted mt-1">Use the signature on file, or draw a new one.</p></div>' +
        '<div class="modal__body"><div style="text-align:center">' +
          '<img src="' + sig.dataUrl + '" alt="Your saved signature" ' +
          'style="max-height:120px;margin:0 auto;mix-blend-mode:multiply">' +
          '<div class="t-sm mt-2" style="font-weight:600">' + escapeHtml(sig.name) + '</div>' +
          (sig.designation
            ? '<div class="t-xs muted-2">' + escapeHtml(sig.designation) + '</div>' : '') +
        '</div>' +
        '<label class="field mt-3"><span class="field__label">Designation on this document</span>' +
          '<input class="input" data-reuse-role value="' + escapeHtml(sig.designation || '') + '" ' +
          'placeholder="e.g. Head of Finance"></label>' +
        '</div>' +
        '<div class="modal__foot"><div class="btn-row">' +
          '<button class="btn btn--ghost" data-cancel>Cancel</button>' +
          '<button class="btn btn--outline" data-new>Draw a new one</button>' +
          '<button class="btn btn--primary" data-use>' + icon('stamp') + 'Sign &amp; approve</button>' +
        '</div></div>';
      document.body.appendChild(el);
      openOverlay(el);
      const finish = v => { closeOverlays(); setTimeout(() => el.remove(), 260); resolve(v); };
      el.querySelector('[data-use]').onclick = () => {
        // Carry any correction to the designation back onto the signature that
        // is about to be applied. The saved mark is reused; the title is not
        // assumed to be the same on every document.
        sig.designation = (el.querySelector('[data-reuse-role]').value || '').trim();
        finish(true);
      };
      el.querySelector('[data-new]').onclick = () => finish(false);
      el.querySelector('[data-cancel]').onclick = () => finish(null);
    });
  }

  /**
   * How to describe somebody's place in the organisation.
   *
   * An administrator often has no department and no job title, because they
   * belong to the system rather than to a line of business. Printing "No
   * department set" against them reads as a misconfigured account when it is
   * simply the wrong question - so their standing is stated instead. Anybody
   * else with nothing recorded is still told plainly that nothing is recorded,
   * because for them it IS missing.
   */
  function designation(person, opts) {
    opts = opts || {};
    const parts = [person && person.job_title, person && person.department].filter(Boolean);
    if (parts.length) return parts.join(' · ');
    if (person && (person.is_admin || person.role === 'admin')) return 'System administrator';
    return opts.fallback || 'No department set';
  }

  /* ------------------------------------------------------------- markdown */

  /**
   * Render the Markdown a language model actually produces.
   *
   * The assistant's answers come back as Markdown - headings, bold, bullets,
   * tables, block quotes - and were being escaped and printed verbatim, so a
   * reply arrived as a wall of `##`, `**` and `|---|---|`. This turns it into
   * the document it was written as.
   *
   * SAFETY: the source is escaped FIRST and every tag below is one this
   * function wrote itself. Model output is not trusted markup - it can repeat
   * anything it read in an uploaded file - so there is no path by which a
   * `<script>` in a document becomes a `<script>` on the page.
   *
   * Deliberately not a full CommonMark implementation. It covers what the
   * models here emit; anything it does not recognise falls through as plain
   * text, which is the same thing the old code did and is never worse.
   *
   * `opts.citations` maps the [Doc1], [Doc2] markers the RAG prompt asks for
   * onto the documents behind them, so a claim links to its evidence.
   */
  function markdown(src, opts) {
    opts = opts || {};
    const cites = opts.citations || [];

    const lines = String(src == null ? '' : src)
      .replace(/\r\n?/g, '\n')
      .replace(/\t/g, '    ')
      .split('\n');

    let out = '';
    let i = 0;

    /** Text that is part of a paragraph, flushed when the block ends. */
    let para = [];
    function flush() {
      if (!para.length) return;
      out += '<p>' + inline(para.join('\n')) + '</p>';
      para = [];
    }

    while (i < lines.length) {
      const line = lines[i];

      // Fenced code. Taken verbatim, so nothing inside is interpreted.
      const fence = line.match(/^\s*(```+|~~~+)\s*([A-Za-z0-9+#._-]*)\s*$/);
      if (fence) {
        flush();
        const close = fence[1][0];
        const body = [];
        i++;
        while (i < lines.length && !new RegExp('^\\s*' + close + '{3,}\\s*$').test(lines[i])) {
          body.push(lines[i]);
          i++;
        }
        i++;                                    // step over the closing fence
        out += '<pre class="md-pre"><code>' + escapeHtml(body.join('\n')) + '</code></pre>';
        continue;
      }

      // Table: a row of pipes whose next line is the |---|---| rule.
      if (line.indexOf('|') >= 0 && i + 1 < lines.length &&
          /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(lines[i + 1]) &&
          lines[i + 1].indexOf('-') >= 0) {
        flush();
        const head = cells(line);
        const align = cells(lines[i + 1]).map(c =>
          /^:-+:$/.test(c.trim()) ? 'center' : /-+:$/.test(c.trim()) ? 'right' : '');
        i += 2;
        const body = [];
        while (i < lines.length && lines[i].indexOf('|') >= 0 && lines[i].trim()) {
          body.push(cells(lines[i]));
          i++;
        }
        out += '<div class="md-tablewrap"><table class="md-table"><thead><tr>' +
          head.map((c, n) => '<th' + (align[n] ? ' style="text-align:' + align[n] + '"' : '') +
            '>' + inline(c) + '</th>').join('') +
          '</tr></thead><tbody>' +
          body.map(r => '<tr>' + r.map((c, n) =>
            '<td' + (align[n] ? ' style="text-align:' + align[n] + '"' : '') +
            '>' + inline(c) + '</td>').join('') + '</tr>').join('') +
          '</tbody></table></div>';
        continue;
      }

      // Heading
      const head = line.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/);
      if (head) {
        flush();
        const level = Math.min(6, head[1].length);
        out += '<h' + level + ' class="md-h md-h' + level + '">' +
          inline(head[2]) + '</h' + level + '>';
        i++;
        continue;
      }

      // Horizontal rule
      if (/^\s{0,3}([-*_])\s*(\1\s*){2,}$/.test(line)) {
        flush();
        out += '<hr class="md-hr">';
        i++;
        continue;
      }

      // Block quote. Collected whole, then rendered by this same function so
      // a quote can contain lists, headings or anything else.
      if (/^\s{0,3}>/.test(line)) {
        flush();
        const body = [];
        while (i < lines.length && /^\s{0,3}>/.test(lines[i])) {
          body.push(lines[i].replace(/^\s{0,3}>\s?/, ''));
          i++;
        }
        out += '<blockquote class="md-quote">' +
          markdown(body.join('\n'), opts) + '</blockquote>';
        continue;
      }

      // Lists, bulleted or numbered, to any depth.
      if (/^\s*([-*+]|\d{1,9}[.)])\s+/.test(line)) {
        flush();
        const consumed = list(lines, i);
        out += consumed.html;
        i = consumed.next;
        continue;
      }

      if (!line.trim()) { flush(); i++; continue; }

      para.push(line);
      i++;
    }
    flush();
    return out;

    /* ------------------------------------------------------------ blocks */

    function cells(row) {
      return row.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|');
    }

    /**
     * One list, starting at `start`.
     *
     * Items indented further than the first belong to a nested list, which is
     * built by calling back into this function - so "- a / - b / ..2 spaces.. - c"
     * nests rather than flattening.
     */
    function list(all, start) {
      const first = all[start].match(/^(\s*)([-*+]|\d{1,9}[.)])\s+/);
      const indent = first[1].length;
      const ordered = /\d/.test(first[2]);
      const startAt = ordered ? parseInt(first[2], 10) : 1;

      let n = start;
      const items = [];

      while (n < all.length) {
        const m = all[n].match(/^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/);

        if (m && m[1].length === indent && (/\d/.test(m[2]) === ordered)) {
          const body = [m[3]];
          n++;
          // Everything more deeply indented, and lazy continuation lines,
          // belong to the item just opened.
          while (n < all.length) {
            const next = all[n];
            const deeper = next.match(/^(\s*)([-*+]|\d{1,9}[.)])\s+/);
            if (deeper && deeper[1].length > indent) { body.push(next.slice(indent + 2)); n++; continue; }
            if (deeper && deeper[1].length <= indent) break;
            if (!next.trim()) {
              // A blank line ends the list unless the next line continues it.
              const after = all[n + 1] || '';
              if (!after.trim() || (after.match(/^(\s*)/)[1].length < indent + 2 &&
                                    !/^\s*([-*+]|\d{1,9}[.)])\s+/.test(after))) break;
              body.push('');
              n++;
              continue;
            }
            if (next.match(/^(\s*)/)[1].length >= indent + 2) { body.push(next.slice(indent + 2)); n++; continue; }
            body.push(next);          // lazy continuation of the same item
            n++;
          }
          items.push(body.join('\n'));
          continue;
        }
        break;
      }

      const html = items.map(body => {
        // An item whose body is a single line is inline text; anything longer
        // may hold a nested list or its own paragraphs.
        const simple = body.indexOf('\n') < 0;
        return '<li>' + (simple ? inline(body) : markdown(body, opts)) + '</li>';
      }).join('');

      return {
        html: ordered
          ? '<ol class="md-list"' + (startAt !== 1 ? ' start="' + startAt + '"' : '') + '>' + html + '</ol>'
          : '<ul class="md-list">' + html + '</ul>',
        next: n,
      };
    }

    /* ------------------------------------------------------------ inline */

    function inline(text) {
      // Escape before anything else. Every tag added after this point is one
      // written here, so nothing from the source can become markup.
      let s = escapeHtml(text);

      // Code spans are lifted out first and put back last, so their contents
      // are never touched by the emphasis or link rules below.
      const code = [];
      s = s.replace(/(`+)([\s\S]*?)\1/g, (m, ticks, body) => {
        code.push(body.replace(/^ | $/g, ''));
        return '\u0000' + (code.length - 1) + '\u0000';
      });

      // Links. Only http(s), mailto and same-site paths: a model repeating
      // what it read in a document must not be able to emit javascript:.
      s = s.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, (m, label, href) => {
        const url = href.replace(/&amp;/g, '&');
        if (!/^(https?:\/\/|mailto:|\/|#)/i.test(url)) return label;
        const external = /^https?:/i.test(url);
        return '<a class="md-link" href="' + escapeHtml(url) + '"' +
          (external ? ' target="_blank" rel="noopener noreferrer"' : '') + '>' + label + '</a>';
      });

      // [Doc1] - the citation format the RAG prompt asks the model for. Turned
      // into a link to the document it names, so a claim can be checked
      // against its source in one click.
      s = s.replace(/\[Doc\s*(\d{1,2})\]/gi, (m, num) => {
        const doc = cites[Number(num) - 1];
        if (!doc || !doc.id) return '<span class="md-cite">' + m + '</span>';
        const title = doc.title || doc.original_filename || ('Document ' + num);
        return '<a class="md-cite md-cite--link" ' +
          'href="/documents/detail?id=' + encodeURIComponent(doc.id) + '" ' +
          'title="' + escapeHtml(title) + '">Doc ' + num + '</a>';
      });

      s = s
        .replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/__([^_]+)__/g, '<strong>$1</strong>')
        .replace(/~~([^~]+)~~/g, '<del>$1</del>')
        // Single * or _ for emphasis, but not inside a word: snake_case_names
        // and 2*3 are not italics.
        .replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=$|[\s).,;:!?])/g, '$1<em>$2</em>')
        .replace(/(^|[\s(])_([^_\s][^_]*?)_(?=$|[\s).,;:!?])/g, '$1<em>$2</em>');

      // A line break inside a paragraph.
      s = s.replace(/ {2,}\n/g, '<br>').replace(/\n/g, ' ');

      return s.replace(/\u0000(\d+)\u0000/g,
        (m, n) => '<code class="md-code">' + code[Number(n)] + '</code>');
    }
  }

  /* ------------------------------------------------------------- combobox */

  /**
   * Turn a text input into a list you can also type into.
   *
   * These fields used to be `<input list="...">` with a `<datalist>`. That is
   * the right *idea* - pick a known supplier, or name one that does not exist
   * yet - but the browser draws no control for it: the field looks like a
   * plain text box, and the options only appear once you have typed enough of
   * one to guess it. So the list was there and nobody could see it.
   *
   * This keeps the same input element, and the same value semantics, so every
   * caller that reads `input.value` carries on working. It adds a chevron that
   * opens the list, filtering as you type, arrow keys, Enter, Escape, and an
   * explicit "add it as new" row so creating a supplier is a decision rather
   * than a side effect of a typo.
   *
   *    combobox(input, { options: ['Maruti Suzuki', …], allowNew: true })
   *
   * Returns a handle with setOptions(), so a caller can refresh the list after
   * creating something without rebuilding the control.
   */
  function combobox(input, opts) {
    opts = opts || {};
    if (!input || input.dataset.combo) return null;
    input.dataset.combo = '1';

    // Options may be plain strings, or {value, label} when the caller needs an
    // id behind the name - a document type, say, where the list shows "Invoice"
    // and the filter needs its id. Normalised once here so the rest of this
    // function only ever deals with one shape.
    const normalise = list => (list || []).map(
      o => (o && typeof o === 'object') ? { value: o.value, label: o.label } : { value: o, label: o });

    let options = normalise(opts.options);
    const allowNew = opts.allowNew !== false;
    let active = -1;
    // The field usually already holds a value. Filtering by it the moment the
    // list opens would show one row - the value itself - and hide every other
    // choice, which is the opposite of what pressing a dropdown is for. So the
    // list narrows only once somebody actually types.
    let filtering = false;

    // The datalist is now redundant, and leaving it attached means two lists
    // fighting over the same field.
    input.removeAttribute('list');
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'false');

    const wrap = document.createElement('div');
    wrap.className = 'combo';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'combo__toggle';
    toggle.tabIndex = -1;
    toggle.setAttribute('aria-label', 'Show the list');
    toggle.innerHTML = icon('chevronDown');
    wrap.appendChild(toggle);

    const panel = document.createElement('div');
    panel.className = 'combo__panel';
    wrap.appendChild(panel);

    function matches() {
      const typed = input.value.trim().toLowerCase();
      if (!filtering || !typed) return options.slice();
      return options.filter(o => o.label.toLowerCase().indexOf(typed) >= 0);
    }

    function draw() {
      const typed = input.value.trim();
      const list = matches();
      const exact = options.some(o => o.label.toLowerCase() === typed.toLowerCase());

      let html = list.map((o, n) =>
        '<button type="button" class="combo__opt' + (n === active ? ' is-active' : '') +
          (o.label.toLowerCase() === typed.toLowerCase() ? ' is-chosen' : '') +
          '" data-pick="' + escapeHtml(o.label) + '"' +
          ' data-value="' + escapeHtml(o.value == null ? o.label : o.value) + '"' +
          ' data-n="' + n + '">' +
          escapeHtml(o.label) + '</button>').join('');

      // Only offered once they are typing. Showing "add X as new" the instant
      // the list opens would invite creating a duplicate of the value already
      // in the field.
      if (allowNew && filtering && typed && !exact) {
        html += '<button type="button" class="combo__opt combo__opt--new' +
          (active === list.length ? ' is-active' : '') +
          '" data-pick="' + escapeHtml(typed) + '" data-value="' + escapeHtml(typed) +
          '" data-n="' + list.length + '">' +
          icon('plus') + 'Add “<strong>' + escapeHtml(typed) + '</strong>” as new</button>';
      }

      if (!html) {
        html = '<div class="combo__empty">' +
          (options.length ? 'Nothing matches that.' : 'No entries yet.') + '</div>';
      }
      panel.innerHTML = html;
    }

    function rows() { return Array.from(panel.querySelectorAll('[data-pick]')); }

    function open() {
      if (wrap.classList.contains('is-open')) return;
      active = -1;
      draw();
      wrap.classList.add('is-open');
      input.setAttribute('aria-expanded', 'true');
    }

    function close() {
      wrap.classList.remove('is-open');
      input.setAttribute('aria-expanded', 'false');
      active = -1;
    }

    function choose(label, value) {
      input.value = label;
      // The id behind the name, for callers that need one. Readable as
      // input.dataset.value, alongside the ordinary input.value.
      input.dataset.value = value == null ? label : value;
      close();
      // Callers listen for the ordinary events, so a pick is indistinguishable
      // from typing the same thing by hand.
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      input.focus();
    }

    function move(by) {
      const list = rows();
      if (!list.length) return;
      active = (active + by + list.length + 1) % (list.length + 1) - 1;
      if (active < 0) active = by > 0 ? 0 : list.length - 1;
      draw();
      const el = rows()[active];
      if (el) el.scrollIntoView({ block: 'nearest' });
    }

    input.addEventListener('focus', () => { filtering = false; open(); });
    input.addEventListener('input', () => { filtering = true; active = -1; open(); draw(); });
    toggle.addEventListener('mousedown', e => {
      e.preventDefault();
      if (wrap.classList.contains('is-open')) { close(); return; }
      filtering = false;
      input.focus();
      open();
      draw();
    });

    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { e.preventDefault(); open(); move(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); open(); move(-1); }
      else if (e.key === 'Escape') { if (wrap.classList.contains('is-open')) { e.stopPropagation(); close(); } }
      else if (e.key === 'Enter') {
        const el = rows()[active];
        if (el) { e.preventDefault(); choose(el.dataset.pick, el.dataset.value); }
        else close();
      }
    });

    // mousedown, not click: the input blurs first otherwise and the panel is
    // already gone by the time the click lands.
    panel.addEventListener('mousedown', e => {
      const el = e.target.closest('[data-pick]');
      if (!el) return;
      e.preventDefault();
      choose(el.dataset.pick, el.dataset.value);
    });
    panel.addEventListener('mousemove', e => {
      const el = e.target.closest('[data-pick]');
      if (!el) return;
      const n = Number(el.dataset.n);
      if (n !== active) { active = n; draw(); }
    });

    document.addEventListener('mousedown', e => {
      if (!wrap.contains(e.target)) close();
    });

    return {
      el: wrap,
      setOptions(next) { options = normalise(next); if (wrap.classList.contains('is-open')) draw(); },
      close: close,
    };
  }

  /* --------------------------------------------------------- people picker */

  /**
   * Multi-select for people. Renders a closed control showing the chosen names,
   * and a panel of checkboxes so one person, several, or the whole team can be
   * picked. Suggestions come from the department, narrowed to the chosen role
   * when anyone holds it.
   *
   * Markup contract: a host element carrying data-people. The current value is
   * kept on the element as a JSON array in data-value, and a `peoplechange`
   * event bubbles whenever it changes.
   */
  function peoplePicker(host, opts) {
    opts = opts || {};
    const selected = new Set(opts.selected || []);

    /**
     * Everyone in the department, with the people who hold the step's role
     * listed first. Narrowing to only the role would hide colleagues a user
     * legitimately wants to add, so the whole team stays reachable.
     */
    function candidates() {
      const dept = host.dataset.dept || '';
      const role = host.dataset.role || '';
      if (!dept || dept === 'None') return [];
      const all = dir.people(dept);
      if (!role) return all;
      return all.slice().sort((a, b) =>
        (b.role === role ? 1 : 0) - (a.role === role ? 1 : 0));
    }

    function commit() {
      host.dataset.value = JSON.stringify([...selected]);
      host.dispatchEvent(new CustomEvent('peoplechange', {
        bubbles: true, detail: [...selected],
      }));
    }

    /** Label and chips only. Never touches the checkbox list. */
    function paintSummary() {
      const list = candidates();
      const chosen = [...selected];
      const label = !list.length
        ? 'Choose a department first'
        : chosen.length === 0 ? 'Anyone with this role'
        : chosen.length === 1 ? chosen[0]
        : chosen.length === list.length ? 'Everyone in the team (' + list.length + ')'
        : chosen.length + ' people';

      const control = host.querySelector('.picker__label');
      if (control) control.textContent = label;

      const all = host.querySelector('[data-all]');
      if (all) all.checked = list.length > 0 && chosen.length === list.length;

      const old = host.querySelector('.picker__chips');
      if (old) old.remove();
      if (chosen.length) {
        host.insertAdjacentHTML('beforeend',
          '<div class="picker__chips">' + chosen.map(n =>
            '<span class="chip">' + escapeHtml(n) +
            '<button type="button" class="chip__x" data-drop="' + escapeHtml(n) + '">' +
            icon('x') + '</button></span>').join('') + '</div>');
      }
    }

    /** Full rebuild. Only on construction or when the candidate list changes. */
    function paintAll() {
      const list = candidates();
      const role = host.dataset.role || '';

      // Drop anyone who is no longer in the department.
      [...selected].forEach(n => { if (!list.some(p => p.name === n)) selected.delete(n); });

      host.innerHTML =
        '<button type="button" class="picker__control' + (list.length ? '' : ' is-empty') + '" data-toggle>' +
          '<span class="picker__label"></span>' +
          icon('chevronDown', 'picker__caret') +
        '</button>' +
        '<div class="picker__panel" hidden>' +
          (list.length
            ? '<label class="picker__opt picker__opt--all"><input type="checkbox" data-all>' +
                '<span class="check__box">' + icon('check') + '</span>' +
                '<span>Select everyone in this team (' + list.length + ')</span></label>' +
              '<div class="picker__list">' +
              list.map(p =>
                '<label class="picker__opt"><input type="checkbox" data-name="' + escapeHtml(p.name) + '"' +
                (selected.has(p.name) ? ' checked' : '') + '>' +
                '<span class="check__box">' + icon('check') + '</span>' +
                '<span class="avatar">' + escapeHtml(initials(p.name)) + '</span>' +
                '<span class="picker__who"><strong>' + escapeHtml(p.name) + '</strong>' +
                '<small>' + escapeHtml(p.role) + '</small></span>' +
                (role && p.role === role
                  ? '<span class="badge badge--accent" style="margin-left:auto">Suggested</span>' : '') +
                '</label>').join('') +
              '</div>'
            : '<div class="picker__empty">No people listed for this department yet.</div>') +
        '</div>';

      paintSummary();
    }

    host.addEventListener('click', e => {
      const toggle = e.target.closest('[data-toggle]');
      if (toggle) {
        const panel = host.querySelector('.picker__panel');
        panel.hidden = !panel.hidden;
        // Only one picker open at a time.
        document.querySelectorAll('[data-people] .picker__panel').forEach(p => {
          if (p !== panel) p.hidden = true;
        });
        // The control is often near the bottom of a scrolling dialog, so bring
        // the freshly opened list into view rather than leaving it below the fold.
        if (!panel.hidden) {
          requestAnimationFrame(() => panel.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
        }
        return;
      }
      const drop = e.target.closest('[data-drop]');
      if (drop) {
        e.preventDefault();
        selected.delete(drop.dataset.drop);
        const box = host.querySelector('[data-name="' + CSS.escape(drop.dataset.drop) + '"]');
        if (box) box.checked = false;
        paintSummary();
        commit();
      }
    });

    host.addEventListener('change', e => {
      if (e.target.matches('[data-all]')) {
        selected.clear();
        if (e.target.checked) candidates().forEach(p => selected.add(p.name));
        host.querySelectorAll('[data-name]').forEach(b => { b.checked = e.target.checked; });
      } else if (e.target.matches('[data-name]')) {
        if (e.target.checked) selected.add(e.target.dataset.name);
        else selected.delete(e.target.dataset.name);
      } else {
        return;
      }
      // Summary only, so the checkbox the user just clicked survives.
      paintSummary();
      commit();
    });

    paintAll();
    commit();

    return {
      /** Called when the step's department or role changes. */
      refresh(dept, role) {
        host.dataset.dept = dept || '';
        host.dataset.role = role || '';
        paintAll();
        commit();
      },
      value() { return [...selected]; },
    };
  }

  // Close any open picker when clicking elsewhere.
  document.addEventListener('click', e => {
    if (e.target.closest('[data-people]')) return;
    document.querySelectorAll('[data-people] .picker__panel').forEach(p => { p.hidden = true; });
  });

  /* -------------------------------------------------------------- workflow */

  /**
   * The approval process, as the screens see it.
   *
   * Every rule about *who may do what* lives on the server: each step arrives
   * carrying `can_act` and, when it is false, `blocked_reason`. Nothing here
   * re-derives permission from roles, because two implementations of one rule
   * is one implementation too many.
   */
  const WORKFLOW_STATUS = {
    draft:             { label: 'Not started',      cls: '',              icon: 'clock' },
    active:            { label: 'In progress',      cls: 'badge--accent', icon: 'clock' },
    changes_requested: { label: 'Changes needed',   cls: 'badge--warn',   icon: 'refresh' },
    approved:          { label: 'Approved',         cls: 'badge--accent', icon: 'check' },
    rejected:          { label: 'Rejected',         cls: 'badge--danger', icon: 'x' },
    cancelled:         { label: 'Cancelled',        cls: '',              icon: 'x' },
    published:         { label: 'Published',        cls: 'badge--accent', icon: 'send' },
  };

  const PRIORITIES = [
    { id: 'low',    label: 'Low',    hint: 'No deadline pressure' },
    { id: 'normal', label: 'Normal', hint: 'The standard route' },
    { id: 'high',   label: 'High',   hint: 'Ahead of normal work' },
    { id: 'urgent', label: 'Urgent', hint: 'Same day, chase actively' },
  ];

  const workflow = {
    STATUS: WORKFLOW_STATUS,
    PRIORITIES: PRIORITIES,

    statusBadge(status) {
      const s = WORKFLOW_STATUS[status] || { label: status || 'Unknown', cls: '', icon: 'info' };
      return '<span class="badge ' + s.cls + '">' + icon(s.icon) + escapeHtml(s.label) + '</span>';
    },

    priorityBadge(priority) {
      const p = String(priority || 'normal').toLowerCase();
      if (p === 'urgent') return '<span class="badge badge--danger">' + icon('zap') + 'Urgent</span>';
      if (p === 'high') return '<span class="badge badge--warn">' + icon('arrowUp') + 'High</span>';
      if (p === 'low') return '<span class="badge">Low</span>';
      return '<span class="badge">Normal</span>';
    },

    /** Who a step is addressed to, in the words a person would use. */
    /**
     * Who a step is addressed to.
     *
     * Every name, spelled out. It used to read "Sudha Iyer +1", which tells
     * you that somebody else is involved and then refuses to say who - the one
     * question the line exists to answer. Names are joined with "and" when all
     * of them must act and "or" when any one of them may, so the wording says
     * what the step actually requires.
     *
     * `opts.short` keeps the old abbreviation for places where the width is
     * genuinely fixed, such as a narrow table cell.
     */
    addressee(step, opts) {
      opts = opts || {};
      if (!step) return 'Nobody';

      const names = (step.assignees || []).map(a => a.name).filter(Boolean);
      if (names.length === 1) return names[0];

      if (names.length > 1) {
        if (opts.short && names.length > 2) {
          return names[0] + ' and ' + (names.length - 1) + ' others';
        }
        const joiner = step.approval_mode === 'any' ? 'or' : 'and';
        return names.slice(0, -1).join(', ') + ' ' + joiner + ' ' + names[names.length - 1];
      }

      if (step.role && step.department) return step.role + ', ' + step.department;
      return step.role || step.department || 'Anyone who can approve';
    },

    dueBadge(step) {
      if (!step || !step.due_date) return '';
      if (step.overdue) {
        return '<span class="badge badge--danger">' + icon('alert') + 'Overdue</span>';
      }
      return '<span class="badge">' + icon('clock') + 'Due ' + fmt.date(step.due_date) + '</span>';
    },

    /** GET, never throwing: an absent workflow is a normal state, not an error. */
    async forDocument(documentId) {
      const data = await api.safe('/api/workflow/by-document/' +
        encodeURIComponent(documentId), { workflow: null });
      return data.workflow || null;
    },

    async load(id) {
      return api.get('/api/workflow/' + encodeURIComponent(id));
    },

    /**
     * Run one decision through the server, collecting a signature only when
     * the step demands one. The step itself carries that requirement, so a
     * screen never has to guess whether to open the signature pad.
     */
    async decide(wf, step, action, opts) {
      opts = opts || {};
      const result = await decide(action, {
        subject: opts.subject || (wf.document && wf.document.title) || 'this document',
        requiresSignature: !!step.requires_signature,
      });
      if (!result) return null;

      try {
        return await api.post('/api/workflow/' + encodeURIComponent(wf.id) +
          '/steps/' + encodeURIComponent(step.id) + '/decide', {
          action: result.action,
          comment: result.comment || '',
          reason: result.reason || '',
          signature: result.signature || null,
        });
      } catch (err) {
        // Two windows open, or a list left sitting all morning: somebody else
        // moved this document on. Say that in words, and let the caller
        // refresh rather than leaving a raw server message on screen.
        const text = String(err.message || err);
        if (/not the one waiting|not active|no such step|step not found/i.test(text)) {
          const stale = new Error(
            'This document has already moved on — somebody else acted on it, ' +
            'or it was decided in another window. The list has been refreshed.');
          stale.stale = true;
          throw stale;
        }
        // Anything else: keep the server's own words, which are written for
        // the person reading them, but drop the JSON wrapper if there is one.
        try {
          const parsed = JSON.parse(text);
          const detail = (parsed.error && parsed.error.detail) || parsed.detail;
          if (detail) throw new Error(detail);
        } catch (e) {
          if (e instanceof Error && e.message !== text) throw e;
        }
        throw err;
      }
    },
  };

  /* ------------------------------------------------------ signature placing */

  /**
   * Move the approval signatures around on the document.
   *
   * The backdrop is the real page, rendered server-side, because you cannot
   * judge whether a signature is sitting on top of a paragraph against a blank
   * rectangle. Positions are held as a fraction of the page, so what you see
   * here is what lands in the PDF whatever size the paper is.
   *
   * Resolves true if anything was saved.
   */
  function placeSignatures(workflowId) {
    return new Promise(async resolve => {
      let layout;
      try {
        layout = await api.get('/api/signatures/' + encodeURIComponent(workflowId) + '/layout');
      } catch (err) {
        toast('Could not open the signatures', String(err.message || err).slice(0, 200), 'danger');
        resolve(false);
        return;
      }

      if (!layout.signatures.length) {
        toast('No signatures to place',
          'Every step on this approval was approval-only, so nothing is stamped.', 'danger');
        resolve(false);
        return;
      }

      // A block may be addressed to a page after the last one: that is the
      // appended signature sheet.
      const pageCount = Math.max(
        layout.page_count,
        ...layout.signatures.map(s => s.page_number)
      );

      const sigs = layout.signatures.map(s => Object.assign({}, s));
      let page = sigs[0].page_number;
      let selected = sigs[0].signature_id;
      let dirty = false;

      const el = document.createElement('div');
      el.className = 'placer';
      el.innerHTML =
        '<div class="placer__bar">' +
          '<span class="tile-icon tile-icon--solid">' + icon('signature') + '</span>' +
          '<div style="min-width:0">' +
            '<div class="placer__title truncate">Signature placement</div>' +
            '<div class="placer__sub truncate">' + escapeHtml(layout.title || 'Document') + '</div>' +
          '</div>' +
          '<span class="spacer"></span>' +
          '<div class="placer__pages" data-pages></div>' +
          '<button class="btn btn--ghost btn--sm" data-reset>' + icon('refresh') + 'Auto position</button>' +
          '<button class="btn btn--outline btn--sm" data-preview>' + icon('eye') + 'Preview signed PDF</button>' +
          '<button class="btn btn--outline btn--sm" data-close-placer>Cancel</button>' +
          '<button class="btn btn--primary btn--sm" data-save>' + icon('check') + 'Save positions</button>' +
        '</div>' +
        '<div class="placer__body">' +
          '<div class="placer__stage" data-stage>' +
            '<div class="placer__page" data-page>' +
              '<img data-backdrop alt="Page">' +
              '<div class="placer__layer" data-layer></div>' +
            '</div>' +
          '</div>' +
          '<aside class="placer__rail">' +
            '<div class="rail__title">Signatures</div>' +
            '<p class="rail__hint">Drag a block on the page. Everything is stored as a ' +
              'proportion of the page, so it prints exactly where you put it.</p>' +
            '<div data-list></div>' +
            '<div class="divider"></div>' +
            '<label class="field"><span class="field__label">Block width</span>' +
              '<input type="range" min="12" max="60" step="1" data-width style="width:100%">' +
              '<span class="field__hint" data-width-label></span></label>' +
            '<div class="divider"></div>' +
            '<div class="banner banner--grey">' + icon('info') +
              '<div>Signatures are stamped onto the document when it is published. ' +
              'The version that was approved is kept separately and never overwritten.</div></div>' +
          '</aside>' +
        '</div>';

      document.body.appendChild(el);
      requestAnimationFrame(() => el.classList.add('is-open'));

      const stage = el.querySelector('[data-stage]');
      const pageEl = el.querySelector('[data-page]');
      const backdrop = el.querySelector('[data-backdrop]');
      const layer = el.querySelector('[data-layer]');

      function pageUrl(n) {
        return '/api/signatures/' + encodeURIComponent(workflowId) + '/page/' + n + '?scale=1.6';
      }

      function paintPages() {
        const buttons = [];
        for (let n = 1; n <= pageCount; n++) {
          const isExtra = n > layout.page_count;
          buttons.push('<button class="placer__page-btn' + (n === page ? ' is-active' : '') +
            '" data-goto="' + n + '">' + (isExtra ? 'Signature sheet' : 'Page ' + n) + '</button>');
        }
        el.querySelector('[data-pages]').innerHTML = buttons.join('');
      }

      function paintPage() {
        backdrop.src = pageUrl(page);
        // Keep the sheet's aspect ratio even before the image loads.
        const geo = layout.pages[Math.min(page, layout.page_count) - 1];
        pageEl.style.aspectRatio = geo.width + ' / ' + geo.height;
        paintBlocks();
        paintPages();
      }

      function paintBlocks() {
        const here = sigs.filter(s => s.page_number === page);
        layer.innerHTML = here.map(s =>
          '<div class="sigblock' + (s.signature_id === selected ? ' is-selected' : '') +
            '" data-sig="' + escapeHtml(s.signature_id) + '" style="' +
            'left:' + (s.x_pct * 100) + '%;top:' + (s.y_pct * 100) + '%;' +
            'width:' + (s.width_pct * 100) + '%">' +
            '<img src="' + s.dataUrl + '" alt="">' +
            '<div class="sigblock__rule"></div>' +
            '<div class="sigblock__name">' + escapeHtml(s.name) + '</div>' +
            (s.designation
              ? '<div class="sigblock__role">' + escapeHtml(s.designation) + '</div>' : '') +
            '<div class="sigblock__meta">' + escapeHtml(s.step || '') + '</div>' +
          '</div>').join('');
        paintList();
      }

      function paintList() {
        el.querySelector('[data-list]').innerHTML = sigs.map(s =>
          '<button class="placer__item' + (s.signature_id === selected ? ' is-active' : '') +
            '" data-pick="' + escapeHtml(s.signature_id) + '">' +
            '<span class="placer__num">' + s.order + '</span>' +
            '<span class="placer__who"><strong>' + escapeHtml(s.name) + '</strong>' +
            '<small>' + escapeHtml(s.designation || 'No designation') + '</small></span>' +
            '<span class="badge">' +
              (s.page_number > layout.page_count ? 'Sheet' : 'p' + s.page_number) + '</span>' +
          '</button>').join('');

        const current = sigs.find(s => s.signature_id === selected);
        if (current) {
          el.querySelector('[data-width]').value = Math.round(current.width_pct * 100);
          el.querySelector('[data-width-label]').textContent =
            Math.round(current.width_pct * 100) + '% of the page width';
        }
      }

      /* ------------------------------------------------------------ dragging */
      let drag = null;

      layer.addEventListener('pointerdown', e => {
        const block = e.target.closest('[data-sig]');
        if (!block) return;
        e.preventDefault();

        selected = block.dataset.sig;
        const sig = sigs.find(s => s.signature_id === selected);
        const box = layer.getBoundingClientRect();
        const rect = block.getBoundingClientRect();

        drag = {
          sig: sig,
          // Grab offset, so the block does not jump to the cursor.
          dx: e.clientX - rect.left,
          dy: e.clientY - rect.top,
          w: box.width,
          h: box.height,
          blockW: rect.width,
          blockH: rect.height,
        };
        block.setPointerCapture(e.pointerId);
        block.classList.add('is-dragging');
        paintBlocks();
      });

      layer.addEventListener('pointermove', e => {
        if (!drag) return;
        const box = layer.getBoundingClientRect();
        let x = e.clientX - box.left - drag.dx;
        let y = e.clientY - box.top - drag.dy;

        // Keep the whole block on the page.
        x = Math.max(0, Math.min(x, drag.w - drag.blockW));
        y = Math.max(0, Math.min(y, drag.h - drag.blockH));

        drag.sig.x_pct = x / drag.w;
        drag.sig.y_pct = y / drag.h;

        const node = layer.querySelector('[data-sig="' + CSS.escape(drag.sig.signature_id) + '"]');
        if (node) {
          node.style.left = (drag.sig.x_pct * 100) + '%';
          node.style.top = (drag.sig.y_pct * 100) + '%';
        }
        dirty = true;
      });

      const endDrag = () => {
        if (!drag) return;
        drag = null;
        layer.querySelectorAll('.is-dragging').forEach(n => n.classList.remove('is-dragging'));
      };
      layer.addEventListener('pointerup', endDrag);
      layer.addEventListener('pointercancel', endDrag);

      /* ------------------------------------------------------------ controls */
      el.addEventListener('click', async e => {
        const goto = e.target.closest('[data-goto]');
        if (goto) { page = Number(goto.dataset.goto); paintPage(); return; }

        const pick = e.target.closest('[data-pick]');
        if (pick) {
          selected = pick.dataset.pick;
          const sig = sigs.find(s => s.signature_id === selected);
          if (sig && sig.page_number !== page) { page = sig.page_number; paintPage(); }
          else paintBlocks();
          return;
        }

        if (e.target.closest('[data-reset]')) {
          try {
            await api.post('/api/signatures/' + encodeURIComponent(workflowId) + '/layout/reset', {});
            toast('Back to automatic positions');
            close(true);
          } catch (err) {
            toast('Could not reset', String(err.message || err).slice(0, 180), 'danger');
          }
          return;
        }

        if (e.target.closest('[data-preview]')) {
          if (dirty) await save(false);
          window.open('/api/signatures/' + encodeURIComponent(workflowId) + '/preview',
            '_blank', 'noopener');
          return;
        }

        if (e.target.closest('[data-save]')) { await save(true); return; }
        if (e.target.closest('[data-close-placer]')) { close(false); return; }
      });

      el.querySelector('[data-width]').addEventListener('input', e => {
        const sig = sigs.find(s => s.signature_id === selected);
        if (!sig) return;
        sig.width_pct = Number(e.target.value) / 100;
        dirty = true;
        paintBlocks();
      });

      async function save(andClose) {
        try {
          await api.put('/api/signatures/' + encodeURIComponent(workflowId) + '/layout', {
            placements: sigs.map(s => ({
              signature_id: s.signature_id,
              page_number: s.page_number,
              x_pct: s.x_pct,
              y_pct: s.y_pct,
              width_pct: s.width_pct,
            })),
          });
          dirty = false;
          if (andClose) { toast('Signature positions saved'); close(true); }
          return true;
        } catch (err) {
          toast('Could not save the positions', String(err.message || err).slice(0, 200), 'danger');
          return false;
        }
      }

      function close(saved) {
        el.classList.remove('is-open');
        setTimeout(() => el.remove(), 220);
        document.removeEventListener('keydown', onKey);
        resolve(!!saved);
      }

      function onKey(e) { if (e.key === 'Escape') close(false); }
      document.addEventListener('keydown', onKey);

      paintPage();
    });
  }

  /* ---------------------------------------------------------------- export */
  /**
   * Whether the signed-in account may reach the administrator-only screens.
   *
   * Pages that build their actions after loadUser() ask this rather than
   * relying on the data-admin-only sweep, which only runs once. Both exist for
   * the same reason: never offer a link that will silently redirect.
   */
  function isAdmin() {
    return !!(window.DMS.me && window.DMS.me.is_admin);
  }

  window.DMS = {
    workflow, placeSignatures, isAdmin, ready, combobox, markdown, designation,
    refreshDates,
    icon, api, toast, fmt, escapeHtml, confirmDanger,
    openOverlay, closeOverlays, initials, NAV, JOURNEY,
    flow, signaturePad, signatureMark, decide, renderJourney, journeyHref,
    templates, dir, peoplePicker, DEPARTMENTS, SLA_OPTIONS,
    // Kept for anything still reading the flat list.
    get TEMPLATES() { return templates.all(); },
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
