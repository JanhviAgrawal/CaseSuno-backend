# CASE SUNO — Backend API (Django)

Single source of truth for the casesuno.in website: enquiries, tracking links, customer ⇄ team
messages, internal notes, lawyers/professionals, Razorpay platform-fee payments, matters and audit logs.

```
Browser ──► casesuno.in (Next.js website + admin panel)
                │  server-to-server, X-Website-Key
                ▼
        CASE SUNO API on Render (this project) ──► PostgreSQL (Render)
                ▲
Razorpay ───────┘  webhook: /api/payments/webhooks/payment/
```

## Deploy on Render (recommended: Blueprint)

1. Push this folder to a GitHub repository.
2. Render dashboard → **New → Blueprint** → pick the repo. `render.yaml` creates
   * `casesuno-db` (PostgreSQL) and
   * `casesuno-api` (Python web service, build `./build.sh`, health check `/health/`).
3. Fill in the secret values Render asks for:

| Variable | What to put |
|---|---|
| `WEBSITE_API_KEY` | a long random string — **same value** goes into the website's `WEBSITE_API_KEY` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | the login for **casesuno.in/admin** (created automatically on every deploy) |
| `ADMIN_NOTIFY_EMAILS` | optional: e-mails alerted on new enquiries / client replies |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | Razorpay → Account & Settings → API Keys |
| `RAZORPAY_WEBHOOK_SECRET` | the secret you type when creating the Razorpay webhook (step 5) |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | e.g. a Hostinger mailbox like `no-reply@casesuno.in` (until set, e-mails are only logged) |

4. After the first deploy, open `https://<service>.onrender.com/health/` → `{"status":"ok","database":true,...}`.
5. Razorpay → Webhooks → Add: URL `https://<service>.onrender.com/api/payments/webhooks/payment/`,
   events `payment.captured`, `payment.failed`, `order.paid`, secret = `RAZORPAY_WEBHOOK_SECRET`.

### Optional: api.casesuno.in
Render service → Settings → Custom Domains → add `api.casesuno.in`, then in **Hostinger → DNS Zone**
add `CNAME  api  →  <service>.onrender.com`. `ALLOWED_HOSTS` in `render.yaml` already includes it.
(The `*.onrender.com` host is always allowed automatically.)

### Manual setup (without Blueprint)
* Build command: `./build.sh` · Start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
* Environment: `DATABASE_URL` (Render Postgres *Internal* URL), `SECRET_KEY`, `DEBUG=False`, plus the table above.

> Free Render instances sleep after ~15 minutes without traffic; the first request then takes 30–50 s.
> The website waits up to 60 s, but for a live business the **Starter** plan (always on) is recommended.
> Free Render Postgres databases expire after 30 days — upgrade the database before going live.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                    # set DB_* and ADMIN_* values
python manage.py migrate
python manage.py ensure_admin --if-configured
python manage.py runserver                              # http://127.0.0.1:8000
python manage.py test                                   # 58 tests
```

`docker compose up` also works (Postgres, Redis, Celery worker, ClamAV).

## What runs where

| Feature | Notes |
|---|---|
| Redis / Celery | Optional. Without `CELERY_BROKER_URL` e-mails are sent inline; without `DJANGO_CACHE_REDIS_URL` an in-memory cache is used. |
| S3 + ClamAV document upload | Optional (`/api/documents/…`). Returns 503 until configured. |
| Django admin | `https://<api-host>/admin/` with the same ADMIN_EMAIL / ADMIN_PASSWORD. |

## API overview

* `/api/web/…` — used by the website server only (requires `X-Website-Key` when `WEBSITE_API_KEY` is set):
  `enquiries/`, `track-lookup/`, `track/<token>/`, `track/<token>/messages/`, `payments/create-order/`,
  `payments/verify/`, `admin/login|logout|me|dashboard/`, `admin/enquiries/…`, `admin/lawyers/…`, `admin/payments/`.
* Original Build Plan endpoints are unchanged: `/api/requirements/`, `/api/proposals/`, `/api/payments/`,
  `/api/matters/`, `/api/professionals/`, `/api/documents/`, `/api/tasks/`, `/api/audit/`, `/api/accounts/`.

### Status mapping (website ⇄ database)
| Website | Database `Requirement.status` |
|---|---|
| NEW | new |
| IN_REVIEW | reviewed (also shows contacted / information_received) |
| AWAITING_PAYMENT | payment_pending (also shows service_proposed) |
| PAID | converted (a Matter is created automatically) |
| IN_PROGRESS · FORWARDED · RESOLVED · CLOSED · REJECTED | in_progress · forwarded · resolved · closed · rejected |

Requesting a platform fee in the admin creates/updates the requirement's **ServiceProposal**;
the Razorpay order is its **Payment**; a successful payment converts the requirement and opens a **Matter**
with the assigned lawyer attached.
