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

## Notes
- `.env` is ignored by git.
- Default DB is SQLite at `backend/kitchen_os.db`.
  For Postgres set `DATABASE_URL` in `backend/.env`.
