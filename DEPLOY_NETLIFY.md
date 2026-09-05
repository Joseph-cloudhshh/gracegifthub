# Running the whole thing on Netlify (frontend + backend + admin)

Everything now lives under **one Netlify site**:
- `frontend/` → static pages, deployed as-is (customer site + `/admin/*.html`)
- `netlify/functions/api/` → your Flask backend, wrapped as a single Netlify
  Python Function, reached at the same-origin paths `/api/*`, `/admin/api/*`,
  `/webhooks/*` (see `netlify.toml`)

Because it's all one site, **changes made in the admin panel write to the
same database the storefront reads from** — add a product in `/admin`, it
shows up on the live site immediately. No syncing step needed.

## Why SQLite had to go

Netlify Functions are serverless: every request can land on a fresh,
throwaway container with no disk of its own. The original SQLite file
(`gracegifthub.db`) would get silently wiped/reset constantly. The backend
now requires a real hosted Postgres database via a `DATABASE_URL` — nothing
else in the code changed, since SQLAlchemy talks to Postgres the same way.

## 1. Get a free Postgres database

Easiest: **[Neon](https://neon.tech)** (or Supabase) — free tier, ready in
under a minute.
1. Create a project.
2. Copy the connection string it gives you — looks like:
   `postgresql://user:password@ep-xxxx.neon.tech/dbname?sslmode=require`

## 2. Push this project to GitHub, then connect it to Netlify

1. Push the whole folder (as-is) to a new GitHub repo.
2. Netlify → "Add new site" → "Import an existing project" → pick the repo.
3. Netlify reads `netlify.toml` automatically — no manual build settings
   needed (base directory `frontend`, Python function in
   `netlify/functions/api`).

## 3. Set environment variables in Netlify

Site settings → Environment variables → add:

| Key | Value |
|---|---|
| `DATABASE_URL` | the Postgres connection string from step 1 |
| `SECRET_KEY` | a long random string |
| `ADMIN_EMAIL` | the email you'll log into `/admin` with |
| `ADMIN_PASSWORD` | a strong password (only used once, to create the first admin — change it after via Settings → Account) |
| `PAYSCRIBE_API_KEY` | from your Payscribe dashboard |
| `PAYSCRIBE_BASE_URL` | `https://api.payscribe.com/v1` |
| `PAYSCRIBE_WEBHOOK_SECRET` | from your Payscribe dashboard |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | your email sending details |
| `ALLOWED_ORIGINS` | your Netlify URL, e.g. `https://your-site.netlify.app` (add your custom domain here too once you buy one, comma-separated) |

None of these live in any file that gets committed to GitHub — they only
exist inside Netlify's dashboard.

## 4. Deploy

Trigger a deploy (push to GitHub, or "Trigger deploy" in Netlify). First
deploy creates the database tables automatically and creates your admin
account from `ADMIN_EMAIL`/`ADMIN_PASSWORD`.

Visit:
- `https://your-site.netlify.app/` — storefront
- `https://your-site.netlify.app/admin` — admin login

Test: log into `/admin`, add a product, then check it appears on the
storefront's shop section — that round-trip confirms the shared database is
working end-to-end.

## 5. Buy and connect your domain

1. Buy the domain anywhere.
2. Netlify → Site settings → Domain management → Add a custom domain →
   follow the DNS instructions Netlify shows you.
3. Netlify auto-issues a free HTTPS certificate once DNS propagates.
4. Add the new domain to `ALLOWED_ORIGINS` (step 3) and redeploy.
5. Update the Payscribe webhook URL in their dashboard to
   `https://yourdomain.com/webhooks/payscribe`.

## Notes / limits worth knowing

- **Cold starts:** the first request after a period of inactivity takes an
  extra second or two while the function boots — normal for serverless,
  not a bug.
- **10-second execution limit** per request on Netlify's free tier — fine
  for this app's normal API calls.
- The old `backend/` folder (Flask app + PythonAnywhere setup) is still in
  this project untouched, in case you ever want a traditional
  single-server deployment instead — it's just no longer what Netlify uses.
