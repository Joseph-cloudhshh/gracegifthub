// ─── Backend location ───────────────────────────────────────────────────
// Everything (frontend + API) now runs on the SAME Netlify site, so this
// stays blank — the Netlify Function is reached via same-origin paths
// (/api/..., /admin/api/..., /webhooks/...). Only set this to a different
// URL if you ever split the backend out to its own separate host again.
window.APP_CONFIG = {
  BACKEND_URL: ""
};
