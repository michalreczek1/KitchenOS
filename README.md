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

## Deploy on Railway (step-by-step)
This repo is a monorepo, so create two Railway services:
one for the backend and one for the frontend.

1) Create a new Railway project from this GitHub repo.
2) Add a **PostgreSQL** plugin (Railway provides `DATABASE_URL`).
3) Create a **Backend** service:
   - Root Directory: `/backend`
   - Env vars:
     - `DATABASE_URL` (Reference from Postgres plugin)
     - `JWT_SECRET_KEY`
     - `ADMIN_BOOTSTRAP_TOKEN` (optional, first admin)
     - `ALLOWED_ORIGINS` = your frontend URL
     - `GROQ_API_KEY` (optional, enables AI)
   - Procfile runs migrations on start:
     - `web` runs `alembic upgrade head` then Uvicorn on `$PORT`
   - If Railway uses Python 3.13, add:
     - `NIXPACKS_PYTHON_VERSION=3.11.9`
4) Create a **Frontend** service:
   - Root Directory: `/`
   - Env vars:
     - `NEXT_PUBLIC_API_URL` = your backend URL
5) Deploy backend first:
   - Check `https://<backend-domain>/health` → `status: ok`
6) Deploy frontend:
   - Open the frontend URL and create the first admin user (Bootstrap admin).

## Railway checklist (quick)
- Repo connected
- Postgres plugin added
- Backend root dir `/backend`
- Frontend root dir `/`
- Backend env: `DATABASE_URL`, `JWT_SECRET_KEY`, `ALLOWED_ORIGINS`
- Frontend env: `NEXT_PUBLIC_API_URL`
- Backend health OK before frontend

## Custom domain + HTTPS (Railway)
1) Decide domains:
   - Example: `app.yourdomain.com` (frontend)
   - Optional: `api.yourdomain.com` (backend)
2) In Railway, open the service → **Settings/Networking** → **Custom Domain**.
3) Add your domain and copy the DNS instructions.
4) In your DNS provider, create the required records (usually CNAME).
5) Wait for verification (Railway will issue HTTPS automatically).
6) Update env vars and redeploy:
   - Backend `ALLOWED_ORIGINS = https://app.yourdomain.com`
   - Frontend `NEXT_PUBLIC_API_URL = https://api.yourdomain.com`

## Notes
- `.env` is ignored by git.
- Default DB is SQLite at `backend/kitchen_os.db`.
  For Postgres set `DATABASE_URL` in `backend/.env`.
