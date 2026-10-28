# Vanishquer Tuitions — Wasmer Edge (free tier)

Ready-to-deploy copy of the live Flask site, adapted for Wasmer.

## What changed vs the Vercel version
- Entry point moved to `app.py` at the project root (Wasmer's Python
  detection looks for `requirements.txt` + `app.py`).
- Database: if `DATABASE_URL` is not set, the app builds it from
  Wasmer's auto-attached Postgres variables (`DB_HOST`, `DB_PORT`,
  `DB_NAME`, `DB_USERNAME`, `DB_PASSWORD`).
- S3: media-upload client creation is now guarded, so a missing S3
  config does not break the public pages.
- Google verification files (`google*.html`) are included at the root.
- No secrets are included in this folder. Do NOT copy `env.txt` here.

## Files
- `app.py` — Flask app (same routes, admin, blog, gallery, sitemap)
- `requirements.txt` — Flask, Flask-SQLAlchemy, psycopg, dotenv, boto3
- `google0bd254d159ad95bf.html`, `google8c6c685808935f55.html`

## Deploy (free)
1. Sign up / sign in at wasmer.io (Hobby / free plan).
2. Create a new app from this folder (or push it to a repo and
   connect that repo in the Wasmer dashboard).
3. App name suggestion: `vanishquer-tuitions` — the URL will be
   `https://vanishquer-tuitions-<your-username>.wasmer.app`
   (or `https://vanishquer-tuitions.wasmer.app` if free).
4. Environment variables, only if you want the live data instead of
   a fresh Wasmer database:
   - Reuse the existing Neon Postgres: set `DATABASE_URL` to the
     existing Neon URL, plus `SECRET_KEY` and `ADMIN_PASSWORD`.
   - For media uploads, set the existing `AWS_*` / S3 variables.
   - If you leave `DATABASE_URL` unset, Wasmer attaches its own
     Postgres (100 MB on the free plan) and the site starts empty —
     you will need to re-add content via the admin panel.
5. Deploy, then check `/`, `/robots.txt`, and `/sitemap.xml`.

## Free-tier fit (checked 28 Oct 2026)
Wasmer's free plan lists 1 app, 1,000,000 requests, 150 GB bandwidth
and 6 hours active CPU — ample for this tuition site's traffic.
The Vercel site at vanishqertuitions.vercel.app is NOT touched by
this; Wasmer would be a second, separate address unless you later
point a domain at it.

## Local test (done 28 Oct 2026)
Syntax-checked, and run in a clean venv with a test database:
`/` → 200, `/robots.txt` → 200, verification file → 200.
