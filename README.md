# KitchenOS

Smart meal planning and shopping list app (Next.js + FastAPI).

## Requirements
- Node.js 18+
- Python 3.11+
- (Optional) PostgreSQL if you want a production database

## Setup (backend)
```
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
```

Edit `backend/.env`:
- `JWT_SECRET_KEY` is required
- `ADMIN_BOOTSTRAP_TOKEN` is optional (only for first admin)
- `DATABASE_URL` is optional (defaults to SQLite)

Run migrations:
```
python -m alembic upgrade head
```

Start backend:
```
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Setup (frontend)
```
cd ..
npm install
copy .env.example .env.local
npm run dev
```

Frontend runs on `http://localhost:3000`.

## One command (dev)
This starts backend + frontend together:
```
npm run start:dev
```

Optional env overrides:
- `BACKEND_PORT` (default 8000)
- `FRONTEND_PORT` (default 3000)

## Bootstrap first admin
Open the app and use the "Bootstrap admin" switch on the login screen.
If `ADMIN_BOOTSTRAP_TOKEN` is set in `.env`, you must paste the same value.

## Deploy to Railway (step-by-step)
This repo is a monorepo, so you will create two Railway services:
one for the backend and one for the frontend.

1) Create a new Railway project from this GitHub repo.
2) Add a PostgreSQL plugin to the project (Railway will provide `DATABASE_URL`).
3) Create a **Backend** service:
   - Set Root Directory to `/backend`.
   - Ensure Nixpacks is used (default).
   - Environment variables:
     - `DATABASE_URL` (from the Postgres plugin)
     - `JWT_SECRET_KEY`
     - `ADMIN_BOOTSTRAP_TOKEN` (optional, for first admin)
     - `ALLOWED_ORIGINS` = your frontend URL
     - `GROQ_API_KEY` (optional, enables AI)
   - Procfile is already set:
     - `release` runs `alembic upgrade head` (migrations)
     - `web` runs Uvicorn on `$PORT`
4) Create a **Frontend** service:
   - Set Root Directory to `/`.
   - Environment variables:
     - `NEXT_PUBLIC_API_URL` = your backend URL
   - Procfile is already set (`npm run start`).
5) Deploy both services.
6) Open the frontend URL and create the first admin user (Bootstrap admin).

## Railway checklist (quick)
- Repo connected
- Postgres plugin added
- Backend root dir `/backend`
- Frontend root dir `/`
- Backend env: `DATABASE_URL`, `JWT_SECRET_KEY`, `ALLOWED_ORIGINS`
- Frontend env: `NEXT_PUBLIC_API_URL`
- Deploy backend first, then frontend

## Notes
- `.env` is ignored by git.
- Default DB is SQLite at `backend/kitchen_os.db`.
  For Postgres set `DATABASE_URL` in `backend/.env`.
