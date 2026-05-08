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
- persist state to `backend/data/store.json`

## Test

```bash
python manage.py test
```

## Implemented API Surface

- `POST /api/auth/login`
- `POST /api/auth/signup`
- `POST /api/auth/oauth/start`
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

`index.html` still uses its local `window.SkillForgeApp.request()` stub, so the Django backend is ready now but not yet wired into those frontend actions.
