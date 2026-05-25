# KitchenOS

Nowoczesna aplikacja do planowania posiłków, list zakupów i inspiracji AI.

## Najważniejsze funkcje
- plan tygodniowy posiłków + automatyczna lista zakupów
- przeglądanie i ocenianie przepisów (1–5 gwiazdek)
- tagowanie przepisów (Obiady, Śniadania, Lunchbox, Sałatki, Pieczywo, Desery, Inne)
- własne przepisy + podgląd składników/instrukcji
- inspiracje AI na podstawie składników z lodówki
- integracja z Google Calendar (opcjonalnie)
- panel admina (użytkownicy, statystyki, logi importu)

## Stack
- Frontend: Next.js (React)
- Backend: FastAPI
- DB: SQLite lokalnie / PostgreSQL produkcyjnie
- AI: Groq (opcjonalnie)

## Wymagania
- Node.js 18+
- Python 3.11+

## Szybki start (lokalnie)

### Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
python -m alembic upgrade head
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```powershell
cd ..
npm install
copy .env.example .env.local
npm run dev
```

Frontend: http://localhost:3000
Backend: http://localhost:8000

## Jedno polecenie (dev)
Uruchamia backend + frontend jednocześnie:
```powershell
npm run start:dev
```

Opcjonalne zmienne:
- `BACKEND_PORT` (domyślnie 8000)
- `FRONTEND_PORT` (domyślnie 3000)

## Konfiguracja środowiska (backend/.env)
Najważniejsze:
- `JWT_SECRET_KEY` (wymagane)
- `DATABASE_URL` (opcjonalne; domyślnie SQLite)
- `ENVIRONMENT` lub `APP_ENV` (`development` lokalnie, `production` w produkcji)
- `ALLOWED_ORIGINS` (w produkcji wymagany dokładny adres frontendu, np. `https://kitchenos.pl`; bez `*`)
- `BOOTSTRAP_ENABLED` (`true` tylko na czas tworzenia pierwszego admina)
- `ADMIN_BOOTSTRAP_TOKEN` (wymagane, gdy `BOOTSTRAP_ENABLED=true`)

### AI (Inspiracje)
- `GROQ_API_KEY` (wymagane do inspiracji AI)

### Google Calendar (opcjonalnie)
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI` (np. `http://localhost:8000/api/google/oauth/callback`)
- `FRONTEND_URL` (np. `http://localhost:3000`)

## Pierwszy admin
Na ekranie logowania włącz „Bootstrap admin”.
Backend utworzy pierwszego admina tylko wtedy, gdy `BOOTSTRAP_ENABLED=true` i podany token zgadza się z `ADMIN_BOOTSTRAP_TOKEN`.
Po utworzeniu pierwszego admina ustaw `BOOTSTRAP_ENABLED=false` i zrestartuj backend.

## Migracje DB
Po pobraniu nowych zmian uruchom:
```powershell
python -m alembic upgrade head
```

## Deploy na Railway (skrót)
Repo to monorepo: dwa serwisy (backend + frontend).

### Backend
- Root Directory: `/backend`
- Zmienne:
  - `DATABASE_URL` (z pluginu Postgres)
  - `JWT_SECRET_KEY`
  - `ENVIRONMENT=production`
  - `ALLOWED_ORIGINS` = dokładny URL frontendu, bez `*`
  - `BOOTSTRAP_ENABLED=false` po utworzeniu pierwszego admina
  - `ADMIN_BOOTSTRAP_TOKEN` (wymagane tylko, gdy bootstrap jest czasowo włączony)
  - `GROQ_API_KEY` (opcjonalnie)
  - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` (opcjonalnie)
  - `FRONTEND_URL` (opcjonalnie, dla OAuth)
- Jeśli Railway użyje Python 3.13 ustaw:
  - `NIXPACKS_PYTHON_VERSION=3.11.9`

### Frontend
- Root Directory: `/`
- Zmienne:
  - `NEXT_PUBLIC_API_URL` = URL backendu

### Check
- Backend: `https://<backend>/health` -> `status: ok`
- Potem frontend i bootstrap admin.

## Domena + HTTPS (Railway)
1) Railway → Service → Settings/Networking → Custom Domain
2) Dodaj domenę i ustaw rekordy DNS (CNAME/ALIAS)
3) Po weryfikacji Railway automatycznie doda HTTPS
4) Zaktualizuj env i redeploy

## Notes
- `.env` jest ignorowany przez git.
- Lokalnie domyślnie SQLite: `backend/kitchen_os.db`.
- Produkcyjnie zalecany PostgreSQL.
- Import przepisów akceptuje publiczne strony `http`/`https`, ale blokuje adresy lokalne, prywatne, link-local, zarezerwowane i przekierowania do takich adresów.
