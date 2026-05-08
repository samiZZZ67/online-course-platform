# SkillForge Backend

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

Authentication design for the next implementation step is documented in `docs/authentication-architecture.md`.
The custom user model design is documented in `docs/custom-user-model.md`.

## Test

```bash
python manage.py test
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

Then sign in at `http://localhost:3000/admin/`.

## Implemented API Surface

- `POST /api/auth/login`
- `POST /api/auth/signup`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `POST /api/auth/oauth/start`
- `POST /api/auth/password/reset-request`
- `POST /api/auth/password/reset-confirm`
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
- `GET /api/courses`
- `GET /api/courses/:id`
- `GET|POST /api/courses/:id/resources`
- `POST /api/dashboard/tab`
- `POST /api/certificates/share`
- `POST /api/certificates/preview`
- `GET /api/health`

## Note

`index.html` still remains untouched on disk.

Authentication supports Django-backed users plus API session tokens, current-user lookup, logout, and a local-development password reset flow.

The served page also injects a small runtime auth bridge that adds the logout button and connects the frontend auth UI to the Django session endpoints without modifying `index.html` on disk.
