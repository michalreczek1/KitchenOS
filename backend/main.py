import os
import re
import requests
import datetime
import json
import uuid
import secrets
from urllib.parse import urlparse, urlencode
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, HttpUrl, Field, EmailStr
from typing import List, Optional
from recipe_scrapers import scrape_html
from groq import Groq
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from dotenv import load_dotenv
from fastapi.responses import Response, HTMLResponse, RedirectResponse

from db import SessionLocal
from models import UserDB, RecipeDB, RecipeRatingDB, PlanDB, ParseLogDB, GoogleCalendarDB


# Load environment variables from .env file
load_dotenv()

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- KONFIGURACJA ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = None
if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY nie jest ustawiony. Endpointy AI będą niedostępne.")
else:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logger.error(f"Błąd inicjalizacji Groq client: {e}")
        # Fallback - spróbuj bez dodatkowych parametrów
        import groq

        client = groq.Groq(api_key=GROQ_API_KEY)

# --- AUTH CONFIG ---
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    logger.error("JWT_SECRET_KEY nie jest ustawiony w pliku .env!")
    raise ValueError("Brak JWT_SECRET_KEY! Dodaj go do pliku .env")

JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "7"))
ADMIN_BOOTSTRAP_TOKEN = os.environ.get("ADMIN_BOOTSTRAP_TOKEN")

# --- GOOGLE CALENDAR CONFIG ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
FRONTEND_URL = os.environ.get("FRONTEND_URL")
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# --- LIFECYCLE ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 KitchenOS Backend uruchamia się...")
    # Uwaga: w produkcji uruchamiaj migracje Alembic (create_all nie jest zalecane).
    yield
    # Shutdown
    logger.info("🛑 KitchenOS Backend wyłącza się...")


app = FastAPI(
    title="KitchenOS API",
    version="2.0.0",
    description="Inteligentny system planowania posiłków i zakupów",
    lifespan=lifespan,
)

# --- CORS ---
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DEPENDENCY ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- AUTH HELPERS ---
def _password_too_long(password: str) -> bool:
    return len(password.encode("utf-8")) > 72


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if _password_too_long(plain_password):
        return False
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    if _password_too_long(password):
        raise HTTPException(status_code=400, detail="HasĹ‚o jest za dĹ‚ugie (limit 72 znaki)")
    return pwd_context.hash(password)


def create_access_token(user_id: int) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(days=JWT_EXPIRE_DAYS)
    to_encode = {"sub": str(user_id), "exp": expire}
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> UserDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Nieprawidłowe dane uwierzytelniające",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise credentials_exception

    user = db.query(UserDB).filter(UserDB.id == user_id_int).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def ensure_google_config() -> None:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth nie jest skonfigurowany. Ustaw GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI.",
        )


def create_google_state_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "nonce": secrets.token_urlsafe(8),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_google_state_token(state: str) -> int:
    try:
        payload = jwt.decode(state, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=400, detail="NieprawidĹ‚owy token stanu OAuth")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Brak uĹĽytkownika w tokenie OAuth")
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="NieprawidĹ‚owy identyfikator uĹĽytkownika")


def get_google_token_record(db: Session, user_id: int) -> GoogleCalendarDB:
    record = db.query(GoogleCalendarDB).filter(GoogleCalendarDB.owner_id == user_id).first()
    if not record:
        raise HTTPException(status_code=400, detail="Brak poĹ‚Ä…czenia z Google Calendar")
    return record


def refresh_google_access_token(db: Session, record: GoogleCalendarDB) -> str:
    if record.expires_at and record.expires_at > datetime.datetime.utcnow() + datetime.timedelta(seconds=60):
        return record.access_token
    if not record.refresh_token:
        raise HTTPException(status_code=401, detail="Brak refresh token. PoĹ‚Ä…cz Google ponownie.")

    ensure_google_config()
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": record.refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if not response.ok:
        raise HTTPException(status_code=502, detail="Nie udaĹ‚o siÄ™ odĹ›wieĹĽyÄ‡ tokenu Google")
    data = response.json()
    record.access_token = data.get("access_token", record.access_token)
    expires_in = data.get("expires_in")
    if expires_in:
        record.expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=int(expires_in))
    record.token_type = data.get("token_type", record.token_type)
    record.scope = data.get("scope", record.scope)
    db.commit()
    db.refresh(record)
    return record.access_token


def google_api_request(
    db: Session,
    record: GoogleCalendarDB,
    method: str,
    url: str,
    params: Optional[dict] = None,
    payload: Optional[dict] = None,
    timeout: int = 20,
) -> requests.Response:
    token = refresh_google_access_token(db, record)
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.request(
        method=method,
        url=url,
        params=params,
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    if response.status_code == 401:
        token = refresh_google_access_token(db, record)
        headers["Authorization"] = f"Bearer {token}"
        response = requests.request(
            method=method,
            url=url,
            params=params,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
    return response


def require_admin(user: UserDB = Depends(get_current_user)) -> UserDB:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Brak uprawnień administratora",
        )
    return user


def log_parse_attempt(user_id: int, url: str, status_value: str, error: Optional[str] = None) -> None:
    log_db = SessionLocal()
    try:
        domain = urlparse(url).netloc.lower()
        log_db.add(
            ParseLogDB(
                owner_id=user_id,
                url=url,
                domain=domain,
                status=status_value,
                error_message=error,
            )
        )
        log_db.commit()
    except Exception:
        logger.error("Nie udało się zapisać logu parsowania", exc_info=True)
        log_db.rollback()
    finally:
        log_db.close()


# --- MODELE PYDANTIC ---
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_days: int


class UserResponse(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: EmailStr
    is_admin: bool
    is_active: bool
    created_at: datetime.datetime
    last_login_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class BootstrapRequest(BaseModel):
    email: EmailStr
    password: str
    token: Optional[str] = None


class RegisterRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class DeleteAccountRequest(BaseModel):
    password: str = Field(..., min_length=1)


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: Optional[str] = None
    is_admin: bool = False


class AdminUserUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class AdminUserCreateResponse(BaseModel):
    user: UserResponse
    temporary_password: Optional[str] = None


class GoogleStatusResponse(BaseModel):
    connected: bool
    calendar_id: Optional[str] = None
    calendar_summary: Optional[str] = None


class GoogleAuthUrlResponse(BaseModel):
    url: str


class GoogleCalendarItem(BaseModel):
    id: str
    summary: str
    primary: Optional[bool] = None


class GoogleCalendarListResponse(BaseModel):
    calendars: List[GoogleCalendarItem]


class GoogleCalendarSelectRequest(BaseModel):
    calendar_id: str


class GoogleSyncEvent(BaseModel):
    recipe_id: int
    date: str
    portions: int = 1


class GoogleSyncRequest(BaseModel):
    calendar_id: Optional[str] = None
    events: List[GoogleSyncEvent]


class GoogleSyncResponse(BaseModel):
    created: int
    deleted: int
    calendar_id: str


class RecipeInput(BaseModel):
    url: HttpUrl


class RecipeResponse(BaseModel):
    id: int
    title: str
    url: str
    image_url: Optional[str] = None
    base_portions: int
    created_at: datetime.datetime
    ingredients: List[str] = []
    instructions: Optional[str] = None
    rating: Optional[int] = None

    class Config:
        from_attributes = True


class RecipeRatingRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Ocena w skali 1-5")


class RecipeRatingResponse(BaseModel):
    recipe_id: int
    rating: int


class RecipeSelection(BaseModel):
    id: int = Field(..., gt=0, description="ID przepisu")
    portions: int = Field(..., gt=0, le=100, description="Liczba porcji (1-100)")


class PlannerRequest(BaseModel):
    selections: List[RecipeSelection] = Field(..., min_items=1, max_items=50)


class ShoppingCategory(BaseModel):
    category: str
    items: List[str]


class ShoppingListResponse(BaseModel):
    shopping_list: List[ShoppingCategory]
    total_recipes: int
    generated_at: datetime.datetime


class ParseLogResponse(BaseModel):
    id: int
    owner_id: int
    url: str
    domain: Optional[str]
    status: str
    error_message: Optional[str] = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class DomainStat(BaseModel):
    domain: str
    count: int


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users_dau: int
    active_users_mau: int
    total_recipes: int
    recipes_with_images: int
    top_domains: List[DomainStat]


# --- POMOCNICZE FUNKCJE ---
def extract_portion_count(yield_text: str) -> int:
    """
    Wyciąga liczbę porcji z tekstu yield.
    Zawiera zabezpieczenie (Sanity Check) przed pomyleniem gramów z porcjami.
    """
    if not yield_text:
        return 1

    # 1. Próbujemy dopasować wzór: "4 porcji" lub "porcji 4"
    # Ignorujemy wielkość liter (re.IGNORECASE)
    match = re.search(
        r"(?:porcj|osób|serving|porcji?)\D*?(\d+)|(\d+)\D*?(?:porcj|osób|serving|porcji?)",
        yield_text,
        re.IGNORECASE,
    )

    if match:
        val = match.group(1) if match.group(1) else match.group(2)
        count = int(val)

        # --- SANITY CHECK ---
        # Jeśli przepis jest na więcej niż 50 osób, to prawdopodobnie błąd (np. 380g zamiast 4 porcji)
        if count > 50:
            print(
                f"⚠️ WARNING: Wykryto podejrzaną ilość porcji ({count}) w tekście: '{yield_text}'. Założyłem, że to jest waga. Resetuję do 1."
            )
            return 1

        return count

    # 2. Fallback: Jeśli nie znalazło słowa kluczowego, bierze pierwszą cyfrę
    match = re.search(r"\d+", yield_text)
    if match:
        count = int(match.group())

        # Takie samo sprawdzenie bezpieczeństwa
        if count > 50:
            print(f"⚠️ WARNING: Fallback wykrył dużą liczbę ({count}). Resetuję do 1.")
            return 1

        return count

    return 1


def fetch_html_safely(url: str, timeout: int = 10) -> str:
    """Bezpieczne pobieranie HTML z obsługą błędów"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    }

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Błąd pobierania URL {url}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nie można pobrać strony: {str(e)}",
        )

def ics_escape(text: str) -> str:
    """Ucieczka znaków zgodna z iCalendar (żeby nie psuć pliku ICS)."""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\n")
            .replace("\n", "\\n")
    )



# --- ENDPOINTY ---


@app.get("/", tags=["System"])
async def root():
    """Health check endpoint"""
    return {
        "system": "KitchenOS",
        "status": "Online",
        "version": "2.0.0",
        "mode": "Smart Automation",
    }


@app.get("/health", tags=["System"])
async def health_check(db: Session = Depends(get_db)):
    """Szczegółowy health check z testowaniem bazy danych"""
    try:
        # Test DB connection
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        db_status = "unhealthy"

    return {
        "status": "ok" if db_status == "healthy" else "degraded",
        "database": db_status,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


# --- AUTH ---
@app.post("/api/auth/bootstrap", response_model=UserResponse, tags=["Auth"])
async def bootstrap_admin(request: BootstrapRequest, db: Session = Depends(get_db)):
    if ADMIN_BOOTSTRAP_TOKEN and request.token != ADMIN_BOOTSTRAP_TOKEN:
        raise HTTPException(status_code=403, detail="Nieprawidłowy token bootstrap")

    existing_users = db.query(UserDB).count()
    if existing_users > 0:
        raise HTTPException(status_code=400, detail="Administrator już istnieje")

    user = UserDB(
        email=request.email.lower(),
        hashed_password=get_password_hash(request.password),
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Auth"])
async def register_user(request: RegisterRequest, db: Session = Depends(get_db)):
    email = request.email.lower()
    existing = db.query(UserDB).filter(UserDB.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Użytkownik już istnieje")

    user = UserDB(
        first_name=request.first_name.strip(),
        last_name=request.last_name.strip(),
        email=email,
        hashed_password=get_password_hash(request.password),
        is_admin=False,
        is_active=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Nieprawidłowy email lub hasło")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Konto nieaktywne. Skontaktuj się z administratorem")

    user.last_login_at = datetime.datetime.utcnow()
    db.commit()

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in_days=JWT_EXPIRE_DAYS)


@app.get("/api/auth/me", response_model=UserResponse, tags=["Auth"])
async def get_me(current_user: UserDB = Depends(get_current_user)):
    return current_user


@app.post("/api/auth/change-password", tags=["Auth"])
async def change_password(
    payload: ChangePasswordRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Obecne has\u0142o jest nieprawid\u0142owe")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="Nowe has\u0142o musi by\u0107 inne ni\u017c obecne")

    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    return {"status": "ok"}


@app.post("/api/auth/delete-account", tags=["Auth"])
async def delete_account(
    payload: DeleteAccountRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Has\u0142o jest nieprawid\u0142owe")

    db.delete(current_user)
    db.commit()
    return {"status": "deleted"}


# --- GOOGLE CALENDAR ---
@app.get("/api/google/status", response_model=GoogleStatusResponse, tags=["Google"])
async def google_status(current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.query(GoogleCalendarDB).filter(GoogleCalendarDB.owner_id == current_user.id).first()
    if not record:
        return GoogleStatusResponse(connected=False)
    return GoogleStatusResponse(
        connected=True,
        calendar_id=record.calendar_id,
        calendar_summary=record.calendar_summary,
    )


@app.get("/api/google/oauth/start", response_model=GoogleAuthUrlResponse, tags=["Google"])
async def google_oauth_start(current_user: UserDB = Depends(get_current_user)):
    ensure_google_config()
    state = create_google_state_token(current_user.id)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return GoogleAuthUrlResponse(url=url)


@app.get("/api/google/oauth/callback", tags=["Google"])
async def google_oauth_callback(code: str, state: str, db: Session = Depends(get_db)):
    ensure_google_config()
    user_id = decode_google_state_token(state)
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="UĹĽytkownik nie znaleziony")

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if not response.ok:
        raise HTTPException(status_code=502, detail="Nie udaĹ‚o siÄ™ poĹ‚Ä…czyÄ‡ z Google")

    data = response.json()
    expires_in = data.get("expires_in")
    expires_at = None
    if expires_in:
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=int(expires_in))

    record = db.query(GoogleCalendarDB).filter(GoogleCalendarDB.owner_id == user.id).first()
    if record:
        record.access_token = data.get("access_token", record.access_token)
        record.refresh_token = data.get("refresh_token") or record.refresh_token
        record.token_type = data.get("token_type", record.token_type)
        record.scope = data.get("scope", record.scope)
        record.expires_at = expires_at
    else:
        record = GoogleCalendarDB(
            owner_id=user.id,
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type"),
            scope=data.get("scope"),
            expires_at=expires_at,
        )
        db.add(record)

    db.commit()

    if FRONTEND_URL:
        return RedirectResponse(url=f"{FRONTEND_URL}?google=connected", status_code=302)
    return HTMLResponse(
        content=(
            "<!doctype html><meta charset='utf-8'/>"
            "<title>KitchenOS</title>"
            "<p>Po\u0142\u0105czono z Google Calendar. Mo\u017cesz wr\u00f3ci\u0107 do aplikacji.</p>"
        ),
        media_type="text/html; charset=utf-8",
    )


@app.get("/api/google/calendars", response_model=GoogleCalendarListResponse, tags=["Google"])
async def google_calendars(current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    record = get_google_token_record(db, current_user.id)
    response = google_api_request(
        db,
        record,
        "GET",
        "https://www.googleapis.com/calendar/v3/users/me/calendarList",
    )
    if not response.ok:
        raise HTTPException(status_code=502, detail="Nie udaĹ‚o siÄ™ pobraÄ‡ kalendarzy")
    data = response.json()
    calendars = [
        GoogleCalendarItem(
            id=item.get("id"),
            summary=item.get("summary", "Bez nazwy"),
            primary=item.get("primary"),
        )
        for item in data.get("items", [])
    ]
    return GoogleCalendarListResponse(calendars=calendars)


@app.post("/api/google/calendar/select", response_model=GoogleStatusResponse, tags=["Google"])
async def google_calendar_select(
    payload: GoogleCalendarSelectRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_google_token_record(db, current_user.id)
    response = google_api_request(
        db,
        record,
        "GET",
        f"https://www.googleapis.com/calendar/v3/users/me/calendarList/{payload.calendar_id}",
    )
    if not response.ok:
        raise HTTPException(status_code=400, detail="Nie znaleziono kalendarza lub brak uprawnieĹ„")
    data = response.json()
    record.calendar_id = payload.calendar_id
    record.calendar_summary = data.get("summary")
    db.commit()
    db.refresh(record)
    return GoogleStatusResponse(
        connected=True,
        calendar_id=record.calendar_id,
        calendar_summary=record.calendar_summary,
    )


@app.post("/api/google/plan/sync", response_model=GoogleSyncResponse, tags=["Google"])
async def google_plan_sync(
    payload: GoogleSyncRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.events:
        raise HTTPException(status_code=400, detail="Brak wydarzeĹ„ do synchronizacji")

    record = get_google_token_record(db, current_user.id)
    calendar_id = payload.calendar_id or record.calendar_id
    if not calendar_id:
        raise HTTPException(status_code=400, detail="Najpierw wybierz kalendarz")
    if payload.calendar_id and payload.calendar_id != record.calendar_id:
        record.calendar_id = payload.calendar_id
        db.commit()

    unique_events = {}
    for event in payload.events:
        unique_events[(event.recipe_id, event.date)] = event
    events = list(unique_events.values())

    dates = []
    for event in events:
        try:
            dates.append(datetime.date.fromisoformat(event.date))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"NieprawidĹ‚owa data: {event.date}")

    date_min = min(dates)
    date_max = max(dates)
    time_min = f"{date_min.isoformat()}T00:00:00Z"
    time_max = f"{(date_max + datetime.timedelta(days=1)).isoformat()}T00:00:00Z"

    # delete existing KitchenOS events in range
    deleted = 0
    page_token = None
    while True:
        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "maxResults": 2500,
            "privateExtendedProperty": f"kitchenos_user_id={current_user.id}",
        }
        if page_token:
            params["pageToken"] = page_token
        response = google_api_request(
            db,
            record,
            "GET",
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            params=params,
        )
        if not response.ok:
            raise HTTPException(status_code=502, detail="Nie udaĹ‚o siÄ™ pobraÄ‡ wydarzeĹ„ z Google")
        data = response.json()
        for item in data.get("items", []):
            event_id = item.get("id")
            if not event_id:
                continue
            delete_response = google_api_request(
                db,
                record,
                "DELETE",
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
            )
            if delete_response.ok:
                deleted += 1
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    created = 0
    for event in events:
        recipe = (
            db.query(RecipeDB)
            .filter(RecipeDB.id == event.recipe_id, RecipeDB.owner_id == current_user.id)
            .first()
        )
        if not recipe:
            continue
        event_date = datetime.date.fromisoformat(event.date)
        description_lines = [f"Porcje: {event.portions}"]
        if recipe.ingredients:
            ingredients = recipe.ingredients[:12]
            suffix = "..." if len(recipe.ingredients) > 12 else ""
            description_lines.append("Skladniki: " + ", ".join(ingredients) + suffix)
        if recipe.url and not recipe.url.startswith("custom:"):
            description_lines.append(f"Link: {recipe.url}")
        body = {
            "summary": recipe.title,
            "description": "\n".join(description_lines),
            "start": {"date": event_date.isoformat()},
            "end": {"date": (event_date + datetime.timedelta(days=1)).isoformat()},
            "extendedProperties": {
                "private": {
                    "kitchenos_user_id": str(current_user.id),
                    "kitchenos_source": "planner",
                }
            },
        }
        response = google_api_request(
            db,
            record,
            "POST",
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            payload=body,
        )
        if response.ok:
            created += 1

    return GoogleSyncResponse(created=created, deleted=deleted, calendar_id=calendar_id)


# --- ADMIN ---
@app.get("/api/admin/users", response_model=List[UserResponse], tags=["Admin"])
async def list_users(_: UserDB = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(UserDB).order_by(UserDB.created_at.desc()).all()


@app.post("/api/admin/users", response_model=AdminUserCreateResponse, tags=["Admin"])
async def create_user(
    payload: AdminUserCreate, _: UserDB = Depends(require_admin), db: Session = Depends(get_db)
):
    email = payload.email.lower()
    existing = db.query(UserDB).filter(UserDB.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Użytkownik już istnieje")

    password = payload.password or secrets.token_urlsafe(10)
    user = UserDB(
        email=email,
        hashed_password=get_password_hash(password),
        is_admin=payload.is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "user": user,
        "temporary_password": None if payload.password else password,
    }


@app.patch("/api/admin/users/{user_id}", response_model=UserResponse, tags=["Admin"])
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    _: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/admin/users/{user_id}/reset-password", tags=["Admin"])
async def reset_user_password(
    user_id: int, _: UserDB = Depends(require_admin), db: Session = Depends(get_db)
):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")

    temp_password = secrets.token_urlsafe(10)
    user.hashed_password = get_password_hash(temp_password)
    db.commit()
    return {"user_id": user.id, "temporary_password": temp_password}


@app.delete("/api/admin/users/{user_id}", tags=["Admin"])
async def delete_user(
    user_id: int, _: UserDB = Depends(require_admin), db: Session = Depends(get_db)
):
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")

    db.query(ParseLogDB).filter(ParseLogDB.owner_id == user_id).delete()
    db.query(PlanDB).filter(PlanDB.owner_id == user_id).delete()
    db.query(RecipeDB).filter(RecipeDB.owner_id == user_id).delete()
    db.delete(user)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/admin/parse-logs", response_model=List[ParseLogResponse], tags=["Admin"])
async def list_parse_logs(
    limit: int = 100,
    _: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return (
        db.query(ParseLogDB)
        .order_by(ParseLogDB.created_at.desc())
        .limit(limit)
        .all()
    )


@app.get("/api/admin/stats", response_model=AdminStatsResponse, tags=["Admin"])
async def admin_stats(_: UserDB = Depends(require_admin), db: Session = Depends(get_db)):
    now = datetime.datetime.utcnow()
    dau_since = now - datetime.timedelta(days=1)
    mau_since = now - datetime.timedelta(days=30)

    total_users = db.query(UserDB).count()
    active_users_dau = (
        db.query(UserDB)
        .filter(UserDB.last_login_at.isnot(None), UserDB.last_login_at >= dau_since)
        .count()
    )
    active_users_mau = (
        db.query(UserDB)
        .filter(UserDB.last_login_at.isnot(None), UserDB.last_login_at >= mau_since)
        .count()
    )
    total_recipes = db.query(RecipeDB).count()
    recipes_with_images = (
        db.query(RecipeDB).filter(RecipeDB.image_url.isnot(None)).count()
    )

    top_domains_rows = (
        db.query(ParseLogDB.domain, func.count(ParseLogDB.id))
        .filter(ParseLogDB.status == "success", ParseLogDB.domain.isnot(None))
        .group_by(ParseLogDB.domain)
        .order_by(func.count(ParseLogDB.id).desc())
        .limit(5)
        .all()
    )
    top_domains = [DomainStat(domain=row[0], count=row[1]) for row in top_domains_rows]

    return AdminStatsResponse(
        total_users=total_users,
        active_users_dau=active_users_dau,
        active_users_mau=active_users_mau,
        total_recipes=total_recipes,
        recipes_with_images=recipes_with_images,
        top_domains=top_domains,
    )


@app.post(
    "/api/parse-recipe",
    response_model=RecipeResponse,
    tags=["Recipes"],
    status_code=status.HTTP_201_CREATED,
)
async def parse_and_save_recipe(
    recipe_in: RecipeInput,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """
    Parsuje przepis z podanego URL i zapisuje w bazie danych.
    Jeśli przepis już istnieje, aktualizuje jego dane.
    """
    url_str = str(recipe_in.url)

    logger.info(f"Parsing recipe from: {url_str}")

    try:
        # Pobierz HTML
        html_content = fetch_html_safely(url_str)

        # Parsuj przepis
        scraper = scrape_html(html=html_content, org_url=url_str)

        # Wyciągnij dane
        title = scraper.title()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nie można wyciągnąć tytułu przepisu z tej strony",
            )

        ingredients = scraper.ingredients()
        if not ingredients:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nie można wyciągnąć składników z tej strony",
            )

        try:
            base_portions = extract_portion_count(scraper.yields())
        except Exception:
            base_portions = 1
            logger.warning("Nie udało się odczytać porcji z przepisu, ustawiam 1")
        image_url = scraper.image()
        instructions = scraper.instructions()

        # Sprawdź czy przepis już istnieje
        recipe = (
            db.query(RecipeDB)
            .filter(RecipeDB.owner_id == current_user.id, RecipeDB.url == url_str)
            .first()
        )

        if recipe:
            logger.info(f"Recipe already exists, updating: {title}")
            # Aktualizuj istniejący przepis
            recipe.title = title
            recipe.ingredients = ingredients
            recipe.instructions = instructions
            recipe.base_portions = base_portions
            recipe.image_url = image_url
            recipe.updated_at = datetime.datetime.utcnow()
        else:
            logger.info(f"Creating new recipe: {title}")
            # Utwórz nowy przepis
            recipe = RecipeDB(
                owner_id=current_user.id,
                title=title,
                url=url_str,
                image_url=image_url,
                ingredients=ingredients,
                instructions=instructions,
                base_portions=base_portions,
            )
            db.add(recipe)

        db.commit()
        db.refresh(recipe)
        log_parse_attempt(current_user.id, url_str, "success")
        return recipe

    except HTTPException as exc:
        log_parse_attempt(current_user.id, url_str, "error", str(exc.detail))
        raise
    except Exception as e:
        logger.error(f"Error parsing recipe: {str(e)}", exc_info=True)
        db.rollback()
        log_parse_attempt(current_user.id, url_str, "error", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Błąd podczas przetwarzania przepisu: {str(e)}",
        )


@app.get(
    "/api/recipes/available", response_model=List[RecipeResponse], tags=["Recipes"]
)
async def get_available_recipes(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """
    Zwraca listę wszystkich dostępnych przepisów z paginacją.
    """
    try:
        recipes = (
            db.query(RecipeDB)
            .filter(RecipeDB.owner_id == current_user.id)
            .offset(skip)
            .limit(limit)
            .all()
        )
        if recipes:
            recipe_ids = [recipe.id for recipe in recipes]
            ratings = (
                db.query(RecipeRatingDB.recipe_id, RecipeRatingDB.rating)
                .filter(
                    RecipeRatingDB.owner_id == current_user.id,
                    RecipeRatingDB.recipe_id.in_(recipe_ids),
                )
                .all()
            )
            rating_map = {recipe_id: rating for recipe_id, rating in ratings}
            for recipe in recipes:
                setattr(recipe, "rating", rating_map.get(recipe.id))
        logger.info(f"Retrieved {len(recipes)} recipes")
        return recipes
    except Exception as e:
        logger.error(f"Error fetching recipes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Błąd podczas pobierania przepisów",
        )


@app.get("/api/recipes/{recipe_id}", response_model=RecipeResponse, tags=["Recipes"])
async def get_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """
    Zwraca szczegóły konkretnego przepisu.
    """
    recipe = (
        db.query(RecipeDB)
        .filter(RecipeDB.id == recipe_id, RecipeDB.owner_id == current_user.id)
        .first()
    )
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Przepis o ID {recipe_id} nie został znaleziony",
        )
    rating = (
        db.query(RecipeRatingDB)
        .filter(
            RecipeRatingDB.owner_id == current_user.id,
            RecipeRatingDB.recipe_id == recipe.id,
        )
        .first()
    )
    if rating:
        setattr(recipe, "rating", rating.rating)
    return recipe


@app.put(
    "/api/recipes/{recipe_id}/rating",
    response_model=RecipeRatingResponse,
    tags=["Recipes"],
)
async def set_recipe_rating(
    recipe_id: int,
    payload: RecipeRatingRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """
    Ustawia ocenę przepisu (1-5) dla aktualnego użytkownika.
    """
    recipe = (
        db.query(RecipeDB)
        .filter(RecipeDB.id == recipe_id, RecipeDB.owner_id == current_user.id)
        .first()
    )
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Przepis o ID {recipe_id} nie został znaleziony",
        )

    existing = (
        db.query(RecipeRatingDB)
        .filter(
            RecipeRatingDB.owner_id == current_user.id,
            RecipeRatingDB.recipe_id == recipe_id,
        )
        .first()
    )
    if existing:
        existing.rating = payload.rating
        existing.updated_at = datetime.datetime.utcnow()
        rating_value = existing.rating
    else:
        rating = RecipeRatingDB(
            owner_id=current_user.id,
            recipe_id=recipe_id,
            rating=payload.rating,
        )
        db.add(rating)
        rating_value = rating.rating

    db.commit()
    return RecipeRatingResponse(recipe_id=recipe_id, rating=rating_value)


@app.delete(
    "/api/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Recipes"]
)
async def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """
    Usuwa przepis z bazy danych.
    """
    recipe = (
        db.query(RecipeDB)
        .filter(RecipeDB.id == recipe_id, RecipeDB.owner_id == current_user.id)
        .first()
    )
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Przepis o ID {recipe_id} nie został znaleziony",
        )

    db.delete(recipe)
    db.commit()
    logger.info(f"Deleted recipe: {recipe.title} (ID: {recipe_id})")


@app.post(
    "/api/planner/generate", response_model=ShoppingListResponse, tags=["Planner"]
)
async def generate_shopping_list(
    request: PlannerRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """
    Generuje zoptymalizowaną listę zakupów na podstawie wybranych przepisów.
    Używa AI do inteligentnego łączenia i kategoryzacji składników.
    """
    logger.info(f"Generating shopping list for {len(request.selections)} recipes")

    compiled_data = []
    missing_recipes = []

    for item in request.selections:
        recipe = (
            db.query(RecipeDB)
            .filter(RecipeDB.id == item.id, RecipeDB.owner_id == current_user.id)
            .first()
        )
        if recipe:
            factor = item.portions / recipe.base_portions
            compiled_data.append(
                {
                    "title": recipe.title,
                    "factor": round(factor, 2),
                    "base_portions": recipe.base_portions,
                    "requested_portions": item.portions,
                    "ingredients": recipe.ingredients,
                }
            )
        else:
            missing_recipes.append(item.id)

    if missing_recipes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nie znaleziono przepisów o ID: {missing_recipes}",
        )

    if not compiled_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Brak danych do wygenerowania listy zakupów",
        )

    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI jest niedostępne. Skonfiguruj GROQ_API_KEY.",
        )

    # Ulepszone prompt dla AI
    prompt = f"""
Działasz jako ekspert logistyki kuchennej KitchenOS. Twoim zadaniem jest skonsolidowanie składników z wielu przepisów w jedną, przejrzystą listę zakupów.

DANE WEJŚCIOWE:
{json.dumps(compiled_data, indent=2, ensure_ascii=False)}

RESTRYKCYJNE ZASADY GENEROWANIA:

1. FILTRACJA ZER (KRYTYCZNE):
   - Jeśli po przeliczeniu ilość jakiegokolwiek składnika wynosi 0, jest bliska 0 (np. 0.1) lub tekst sugeruje brak (np. "opcjonalnie"), CAŁKOWICIE USUŃ ten produkt z listy.
   - NIE WOLNO wypisywać produktów z ilością "0".

2. INTELIGENTNE ZAOKRĄGLANIE W GÓRĘ:
   - Produkty liczone w sztukach (cebula, czosnek, jaja, warzywa w całości) ZAWSZE zaokrąglaj do najbliższej LICZBY CAŁKOWITEJ W GÓRĘ. 
   - Przykład: 0.2 cebuli -> 1 cebula, 1.1 pora -> 2 pory.

3. AGREGACJA I JEDNOSTKI:
   - Zsumuj identyczne składniki (np. sól z 3 przepisów).
   - Format: "Nazwa produktu (Ilość Jednostka)".
   - Używaj czytelnych ułamków (1/2, 1/4) dla szklanek/łyżek, ale liczb całkowitych dla sztuk.

4. KATEGORYZACJA:
   - Przypisz produkty do kategorii: Warzywa i owoce, Mięso i ryby, Nabiał i jaja, Pieczywo i makarony, Oleje i tłuszcze, Przyprawy i dodatki, Produkty sypkie, Inne.

ZWRÓĆ WYŁĄCZNIE CZYSTY JSON:
{{
  "shopping_list": [
    {{
      "category": "Warzywa i owoce",
      "items": ["Cebula (2 sztuki)", "Czosnek (1 główka)"]
    }}
  ]
}}
"""

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        ai_response = chat_completion.choices[0].message.content
        result = json.loads(ai_response)

        # Dodaj metadane
        response = ShoppingListResponse(
            shopping_list=result.get("shopping_list", []),
            total_recipes=len(compiled_data),
            generated_at=datetime.datetime.utcnow(),
        )

        logger.info(
            f"Successfully generated shopping list with {len(response.shopping_list)} categories"
        )
        return response

    except json.JSONDecodeError as e:
        logger.error(f"AI returned invalid JSON: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI zwróciło nieprawidłowy format danych",
        )
    except Exception as e:
        logger.error(f"Error generating shopping list: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Błąd podczas generowania listy: {str(e)}",
        )


# --- STATYSTYKI ---
@app.get("/api/stats", tags=["Stats"])
async def get_stats(
    db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)
):
    """
    Zwraca statystyki systemu.
    """
    try:
        total_recipes = (
            db.query(RecipeDB).filter(RecipeDB.owner_id == current_user.id).count()
        )
        plan_entry = (
            db.query(PlanDB).filter(PlanDB.owner_id == current_user.id).first()
        )
        planned_meals = len(plan_entry.value) if plan_entry and plan_entry.value else 0

        return {
            "total_recipes": total_recipes,
            "planned_meals": planned_meals,
            "shopping_items": 0,
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Błąd podczas pobierania statystyk",
        )


# --- ENDPOINTY PLANERA (POPRZEŃIONE NA GÓRĘ) ---


@app.get("/api/plan/load", tags=["Planner"])
async def load_plan(
    db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)
):
    """Ładuje zapisany plan użytkownika."""
    plan_entry = (
        db.query(PlanDB).filter(PlanDB.owner_id == current_user.id).first()
    )
    if plan_entry and plan_entry.value:
        return {"plan": plan_entry.value}
    return {"plan": []}


@app.post("/api/plan/save", tags=["Planner"])
async def save_plan(
    plan_data: dict,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """Zapisuje plan użytkownika."""
    # Walidacja wejścia
    selections = plan_data.get("selections", [])
    if not isinstance(selections, list):
        raise HTTPException(status_code=400, detail="Plan musi być listą")

    plan_entry = (
        db.query(PlanDB).filter(PlanDB.owner_id == current_user.id).first()
    )

    if not plan_entry:
        plan_entry = PlanDB(owner_id=current_user.id, value=selections)
        db.add(plan_entry)
    else:
        plan_entry.value = selections
        plan_entry.updated_at = datetime.datetime.utcnow()

    db.commit()
    logger.info(f"Plan saved with {len(selections)} items")
    return {"status": "success", "items": len(selections)}


@app.post(
    "/api/recipes/custom",
    response_model=RecipeResponse,
    tags=["Recipes"],
    status_code=status.HTTP_201_CREATED,
)
async def create_custom_recipe(
    raw_data: dict,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """
    Pozwala użytkownikowi wkleić surowy tekst przepisu.
    AI parsuje tytuł, składniki i instrukcje.
    """
    content = (raw_data.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Tekst przepisu nie może być pusty")

    logger.info("Parsing custom recipe from raw text...")

    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI jest niedostępne. Skonfiguruj GROQ_API_KEY.",
        )

    prompt = f"""
Zanalizuj poniższy tekst przepisu kucharskiego.
Wyodrębnij dane i zwróć je jako JSON.

Zasady:
1. Jeśli nie ma tytułu, nadaj własny np. "Przepis Domowy".
2. Składniki: Zwróć listę stringów. Usuń numery z wierszy składników.
3. Porcje: Jeśli nie jest podane, przyjmij 1.

TEKST WEJŚCIOWY:
{content}

ZWROT (tylko JSON):
{{
  "title": "Tytuł",
  "portions": 1,
  "ingredients": ["Składnik 1", "Składnik 2"],
  "instructions": "Instrukcje krok po kroku..."
}}
"""

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        parsed_data = json.loads(chat_completion.choices[0].message.content or "{}")

        # Ikona domyślna
        generic_icon = "https://cdn-icons-png.flaticon.com/512/3081/3081557.png"

        # --- KLUCZOWE: unikalny URL, bo w bazie url ma unique=True ---
        custom_url = f"custom:{uuid.uuid4()}"

        recipe = RecipeDB(
            owner_id=current_user.id,
            title=(parsed_data.get("title") or "Przepis Własny").strip(),
            url=custom_url,
            image_url=generic_icon,
            ingredients=parsed_data.get("ingredients") or [],
            instructions=parsed_data.get("instructions") or "",
            base_portions=int(parsed_data.get("portions") or 1),
        )

        db.add(recipe)
        db.commit()
        db.refresh(recipe)

        return recipe

    except Exception as e:
        logger.error(f"Error parsing custom recipe: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="AI nie poradziło sobie z tekstem. Spróbuj formatu: 'Tytuł\\nSkładniki...\\nInstrukcje...'",
        )

@app.post("/api/plan/export-ics", tags=["Planner"])
async def export_calendar(
    plan_data: dict,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """
    Generuje poprawny plik ICS:
    - DTEND jest dniem następnym (dla zdarzeń całodniowych)
    - UID jest stabilny (brak duplikatów po ponownym imporcie)
    - tekst jest escapowany (bez psucia formatu)
    """
    selections = plan_data.get("selections", [])
    if not selections:
        raise HTTPException(status_code=400, detail="Plan jest pusty")

    today = datetime.date.today()
    day_map = {
        "Poniedziałek": 0, "Wtorek": 1, "Środa": 2, "Czwartek": 3,
        "Piątek": 4, "Sobota": 5, "Niedziela": 6
    }

    now_str = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//KitchenOS//PL//PL\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "X-WR-CALNAME:Plan Obiadów KitchenOS\r\n"
    )

    # Licznik, żeby ten sam przepis tego samego dnia mógł wystąpić kilka razy
    uid_counters = {}

    for item in selections:
        recipe_id = item.get("id")
        if not recipe_id:
            continue

        recipe = (
            db.query(RecipeDB)
            .filter(RecipeDB.id == recipe_id, RecipeDB.owner_id == current_user.id)
            .first()
        )
        if not recipe:
            continue

        day_name = item.get("day") or "Poniedziałek"
        day_offset = day_map.get(day_name, 0)

        # wyznacz datę docelową w tym/na następnym tygodniu
        days_since_monday = day_offset - today.weekday()
        target_date = today + datetime.timedelta(days=days_since_monday)
        if target_date < today:
            target_date += datetime.timedelta(days=7)

        date_str = target_date.strftime("%Y%m%d")
        end_date_str = (target_date + datetime.timedelta(days=1)).strftime("%Y%m%d")  # DTEND = dzień następny

        portions_val = int(item.get("portions") or 1)

        # stabilny UID: przepis + data + kolejność wystąpienia w danym dniu
        key = (recipe.id, date_str)
        uid_counters[key] = uid_counters.get(key, 0) + 1
        occ = uid_counters[key]
        uid = f"{recipe.id}-{date_str}-{occ}@kitchenos.local"

        ing_str = " | ".join((recipe.ingredients or [])[:5]) if recipe.ingredients else ""
        if recipe.ingredients and len(recipe.ingredients) > 5:
            ing_str += "..."

        summary = ics_escape(f"🍳 {recipe.title} ({portions_val} porcji)")
        description = ics_escape(f"Składniki: {ing_str}\n\nID Przepisu: {recipe.id}")

        ics_content += (
            "BEGIN:VEVENT\r\n"
            f"DTSTART;VALUE=DATE:{date_str}\r\n"
            f"DTEND;VALUE=DATE:{end_date_str}\r\n"
            f"DTSTAMP:{now_str}\r\n"
            f"UID:{uid}\r\n"
            f"SUMMARY:{summary}\r\n"
            f"DESCRIPTION:{description}\r\n"
            "END:VEVENT\r\n"
        )

    ics_content += "END:VCALENDAR\r\n"

    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="kitchenos_plan.ics"'},
    )



# --- URUCHOMIENIE (NA SAMYM DOLE) ---
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
