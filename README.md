# HackersAcademy Backend

This backend now runs on Python Django and mirrors the API contract already defined inside `index.html`, without changing that file.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python manage.py runserver 3000
```

Then open `http://localhost:3000/`. The Django server will:

- serve the existing `index.html`
- expose the frontend-matching API routes under `/api/*`
- persist application state in `db.sqlite3` through Django models
- expose the Django admin at `/admin/`

The root dispatcher lives in `backend/urls.py`, while the actual site and API routes live in `academy/urls.py`.
The domain models, admin registrations, tests, static assets, and seed logic now live in the `academy` app.

## Groq AI Tutor

`POST /api/ai/tutor` calls Groq when `GROQ_API_KEY` is configured. Without a key, local development keeps using the built-in fallback tutor reply.

Set these environment variables before running the server:

```bash
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

PowerShell example:

```powershell
$env:GROQ_API_KEY="your_groq_api_key_here"
$env:GROQ_MODEL="llama-3.3-70b-versatile"
python manage.py runserver 3000
```

Optional settings are listed in `.env.example`: API base URL, timeout, max completion tokens, temperature, and whether failed Groq calls should fall back locally.

You can also copy `.env.example` to `.env`, put your real key there, and restart the Django server.

Authentication design for the next implementation step is documented in `docs/authentication-architecture.md`.
The custom user model design is documented in `docs/custom-user-model.md`.
The role-based access control design is documented in `docs/rbac-architecture.md`.
The authentication API reference is documented in `docs/authentication-api.md`.
The final authentication flow checklist is documented in `docs/final-authentication-flow.md`.

## Test

```bash
python manage.py test
```

## Deploy On Render

This repo includes `render.yaml`, `build.sh`, `Procfile`, and production-ready Django settings for Render.

Fast path:

1. Push this repository to GitHub.
2. In Render, create a new Blueprint from the repo. Render will read `render.yaml`.
3. Add `GROQ_API_KEY` when Render asks for unsynced environment variables.
4. Deploy.

Manual web service settings, if you do not use the Blueprint:

```bash
Build Command: bash build.sh
Start Command: python -m gunicorn backend.asgi:application -k uvicorn.workers.UvicornWorker
```

Required production environment variables:

```bash
SECRET_KEY=<generate a long random value>
DEBUG=false
DATABASE_URL=<Render Postgres internal connection string>
GROQ_API_KEY=<your Groq key>
GROQ_MODEL=llama-3.3-70b-versatile
```

Production deploys do not create the local demo learner account unless you set `SEED_DEMO_USER=true`.

Render sets `RENDER_EXTERNAL_HOSTNAME`, so the default Render URL is allowed automatically. For a custom domain, set:

```bash
ALLOWED_HOSTS=your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com
```

`build.sh` installs dependencies, collects static files, runs migrations, and loads starter SkillForge data.

Course uploads and user media need persistent storage. Add a Render Disk or external file storage before relying on uploads in production; otherwise files written to the Render instance can disappear after deploys/restarts. With a Render Disk mounted at `/var/data`, set:

```bash
MEDIA_ROOT=/var/data/media
```

## Seed Data

```bash
python manage.py seed_skillforge
```

Run that after `migrate` to load the starter catalog, coupons, and notifications.

## Admin

```bash
python manage.py createsuperuser
```

Then sign in at `http://localhost:3000/admin/` or `http://localhost:3000/site-admin/`.

## API Docs

- Swagger UI: `http://localhost:3000/api/docs/swagger/`
- ReDoc: `http://localhost:3000/api/docs/redoc/`
- OpenAPI JSON: `http://localhost:3000/api/docs/openapi.json`
- OpenAPI YAML: `http://localhost:3000/api/docs/openapi.yaml`

## Implemented API Surface

- `POST /api/auth/login`
- `POST /api/auth/signup`
- `POST /api/auth/refresh`
- `POST /api/auth/verify-email/request`
- `GET|POST /api/auth/verify-email/confirm`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `POST /api/auth/oauth/start`
- `POST /api/auth/password/reset-request`
- `POST /api/auth/password/reset-confirm`
- `POST /api/register`
- `POST /api/login`
- `POST /api/refresh-token`
- `POST /api/forgot-password`
- `GET|POST /api/reset-password`
- `GET|POST /api/verify-email`
- `GET /api/profile`
- `PUT|PATCH /api/profile/update`
- `POST /api/change-password`
- `POST /api/logout`
- `GET /api/users`
- `PATCH /api/users/suspend`
- `PATCH /api/users/verify`
- `PATCH /api/users/change-role`
- `POST /api/newsletter/subscribe`
- `POST /api/enrollments`
- `GET|POST /api/wishlist`
- `POST /api/ai/tutor`
- `POST /api/courses/share`
- `POST /api/gifts`
- `POST /api/coupons/validate`
- `GET|POST /api/notes`
- `GET /api/notifications`
- `POST /api/instructor/courses/drafts`
- `GET|POST /api/instructor/courses`
- `POST /api/instructor/courses/thumbnail`
- `GET /api/categories`
- `GET /api/courses`
- `GET /api/courses/:id`
- `GET|POST /api/courses/:id/resources`
- `POST /api/dashboard/tab`
- `POST /api/certificates/share`
- `POST /api/certificates/preview`
- `GET /api/health`

## Note

`index.html` still remains untouched on disk.

Authentication now uses short-lived JWT access tokens plus rotating refresh tokens in an `HttpOnly` cookie, with current-user lookup, refresh rotation, logout revocation, reuse detection, and a local-development password reset flow.

The served page also injects a small runtime auth bridge that adds the logout button, keeps the access token in memory, restores sessions through `/api/auth/refresh`, and connects the frontend auth UI to Django without modifying `index.html` on disk.

Registration now validates passwords with Django validators, generates email-verification tokens, sends verification emails through Django mail, and rate-limits signup and verification-related requests.

The backend now also exposes mobile-friendly auth aliases, profile management APIs, admin user-management APIs, console-backed verification and password-reset emails, and JWT request middleware for protected API routes.

Authentication is now documented through OpenAPI plus Swagger/ReDoc, and the backend is ready to move into course-management work once the auth contract is considered stable.

Course management now uses real Django models for categories, courses, modules, lessons, enrollments, and lesson-level progress tracking while preserving the existing frontend-facing `/api/courses` and `/api/enrollments` contract.
