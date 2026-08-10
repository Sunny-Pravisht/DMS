# Legacy interface (retired)

These are the original upstream `JayRHa/DocumentManager` frontend files. They are **no longer
served** by the application and are not referenced by any code.

They were moved here out of `frontend/` on 31 July 2026 when the interface was rebuilt as
`frontend/ui/`, a zero-dependency design system in white, royal blue, grey and red.

| File | Was |
|---|---|
| `index.html` | 222 KB single-page application shell |
| `app.js` | 395 KB of page logic |
| `styles.css` | 122 KB of Bootstrap overrides and the purple gradient theme |
| `login.html` | Old sign-in page |
| `responsive-styles.css`, `mobile-functions.js`, `search-dropdowns.js`, `utils.js`, `css/health-status.css` | Supporting assets |
| `favicon.ico`, `favicon.svg` | Old brand marks |

Kept for reference only, so behaviour can be compared while the new interface reaches full
parity. Safe to delete once that is confirmed, nothing imports from this directory.

See the repository `README.md` → **Removed / retired**.
