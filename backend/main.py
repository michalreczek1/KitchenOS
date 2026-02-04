import os
import re
import requests
import datetime
import json
import uuid
import secrets
from urllib.parse import urlparse, urlencode
from fastapi import FastAPI, HTTPException, Depends, status, Body
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, HttpUrl, Field, EmailStr, ValidationError
from typing import List, Optional, Any
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
    logger.warning("GROQ_API_KEY nie jest ustawiony. Endpointy AI bÄdÄ niedostÄpne.")
else:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logger.error(f"BÅÄd inicjalizacji Groq client: {e}")
        # Fallback - sprÃ³buj bez dodatkowych parametrÃ³w
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
    logger.info("ð KitchenOS Backend uruchamia siÄ...")
    # Uwaga: w produkcji uruchamiaj migracje Alembic (create_all nie jest zalecane).
    yield
    # Shutdown
    logger.info("ð KitchenOS Backend wyÅÄcza siÄ...")


app = FastAPI(
    title="KitchenOS API",
    version="2.0.0",
    description="Inteligentny system planowania posiÅkÃ³w i zakupÃ³w",
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
        raise HTTPException(status_code=400, detail="HasÄ¹âo jest za dÄ¹âugie (limit 72 znaki)")
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
        detail="NieprawidÅowe dane uwierzytelniajÄce",
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
        raise HTTPException(status_code=400, detail="NieprawidÄ¹âowy token stanu OAuth")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Brak uÄ¹Ä½ytkownika w tokenie OAuth")
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="NieprawidÄ¹âowy identyfikator uÄ¹Ä½ytkownika")


def get_google_token_record(db: Session, user_id: int) -> GoogleCalendarDB:
    record = db.query(GoogleCalendarDB).filter(GoogleCalendarDB.owner_id == user_id).first()
    if not record:
        raise HTTPException(status_code=400, detail="Brak poÄ¹âÃâ¦czenia z Google Calendar")
    return record


def refresh_google_access_token(db: Session, record: GoogleCalendarDB) -> str:
    if record.expires_at and record.expires_at > datetime.datetime.utcnow() + datetime.timedelta(seconds=60):
        return record.access_token
    if not record.refresh_token:
        raise HTTPException(status_code=401, detail="Brak refresh token. PoÄ¹âÃâ¦cz Google ponownie.")

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
        raise HTTPException(status_code=502, detail="Nie udaÄ¹âo siÃâ¢ odÄ¹âºwieÄ¹Ä½yÃâ¡ tokenu Google")
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
            detail="Brak uprawnieÅ administratora",
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
        logger.error("Nie udaÅo siÄ zapisaÄ logu parsowania", exc_info=True)
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


class InspireRequest(BaseModel):
    ingredients: List[str] = Field(..., min_items=1)


class InspireIngredient(BaseModel):
    item: str
    amount: str = ""
    is_extra: bool = False


class InspireRecipeResponse(BaseModel):
    title: str
    description: Optional[str] = None
    difficulty: Optional[str] = None
    prep_time: Optional[str] = None
    ingredients: List[InspireIngredient]
    instructions: List[str]
    tips: Optional[str] = None


class RecipeCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    ingredients: List[InspireIngredient] | List[str] = Field(..., min_items=1)
    instructions: List[str] | str
    description: Optional[str] = None
    prep_time: Optional[str] = None
    difficulty: Optional[str] = None
    base_portions: Optional[int] = 1


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
    WyciÄga liczbÄ porcji z tekstu yield.
    Zawiera zabezpieczenie (Sanity Check) przed pomyleniem gramÃ³w z porcjami.
    """
    if not yield_text:
        return 1

    # 1. PrÃ³bujemy dopasowaÄ wzÃ³r: "4 porcji" lub "porcji 4"
    # Ignorujemy wielkoÅÄ liter (re.IGNORECASE)
    match = re.search(
        r"(?:porcj|osÃ³b|serving|porcji?)\D*?(\d+)|(\d+)\D*?(?:porcj|osÃ³b|serving|porcji?)",
        yield_text,
        re.IGNORECASE,
    )

    if match:
        val = match.group(1) if match.group(1) else match.group(2)
        count = int(val)

        # --- SANITY CHECK ---
        # JeÅli przepis jest na wiÄcej niÅ¼ 50 osÃ³b, to prawdopodobnie bÅÄd (np. 380g zamiast 4 porcji)
        if count > 50:
            print(
                f"â ï¸ WARNING: Wykryto podejrzanÄ iloÅÄ porcji ({count}) w tekÅcie: '{yield_text}'. ZaÅoÅ¼yÅem, Å¼e to jest waga. ResetujÄ do 1."
            )
            return 1

        return count

    # 2. Fallback: JeÅli nie znalazÅo sÅowa kluczowego, bierze pierwszÄ cyfrÄ
    match = re.search(r"\d+", yield_text)
    if match:
        count = int(match.group())

        # Takie samo sprawdzenie bezpieczeÅstwa
        if count > 50:
            print(f"â ï¸ WARNING: Fallback wykryÅ duÅ¼Ä liczbÄ ({count}). ResetujÄ do 1.")
            return 1

        return count

    return 1


def fetch_html_safely(url: str, timeout: int = 10) -> str:
    """Bezpieczne pobieranie HTML z obsÅugÄ bÅÄdÃ³w"""
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
        logger.error(f"BÅÄd pobierania URL {url}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nie moÅ¼na pobraÄ strony: {str(e)}",
        )

def ics_escape(text: str) -> str:
    """Ucieczka znakÃ³w zgodna z iCalendar (Å¼eby nie psuÄ pliku ICS)."""
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
    """SzczegÃ³Åowy health check z testowaniem bazy danych"""
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
        raise HTTPException(status_code=403, detail="NieprawidÅowy token bootstrap")

    existing_users = db.query(UserDB).count()
    if existing_users > 0:
        raise HTTPException(status_code=400, detail="Administrator juÅ¼ istnieje")

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
        raise HTTPException(status_code=400, detail="UÅ¼ytkownik juÅ¼ istnieje")

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
        raise HTTPException(status_code=401, detail="NieprawidÅowy email lub hasÅo")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Konto nieaktywne. Skontaktuj siÄ z administratorem")

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
        raise HTTPException(status_code=404, detail="UÄ¹Ä½ytkownik nie znaleziony")

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
        raise HTTPException(status_code=502, detail="Nie udaÄ¹âo siÃâ¢ poÄ¹âÃâ¦czyÃâ¡ z Google")

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
        raise HTTPException(status_code=502, detail="Nie udaÄ¹âo siÃâ¢ pobraÃâ¡ kalendarzy")
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
        raise HTTPException(status_code=400, detail="Nie znaleziono kalendarza lub brak uprawnieÄ¹â")
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
        raise HTTPException(status_code=400, detail="Brak wydarzeÄ¹â do synchronizacji")

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
            raise HTTPException(status_code=400, detail=f"NieprawidÄ¹âowa data: {event.date}")

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
            raise HTTPException(status_code=502, detail="Nie udaÄ¹âo siÃâ¢ pobraÃâ¡ wydarzeÄ¹â z Google")
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
        raise HTTPException(status_code=400, detail="UÅ¼ytkownik juÅ¼ istnieje")

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
        raise HTTPException(status_code=404, detail="UÅ¼ytkownik nie znaleziony")
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
        raise HTTPException(status_code=404, detail="UÅ¼ytkownik nie znaleziony")

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
        raise HTTPException(status_code=404, detail="UÅ¼ytkownik nie znaleziony")

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
    JeÅli przepis juÅ¼ istnieje, aktualizuje jego dane.
    """
    url_str = str(recipe_in.url)

    logger.info(f"Parsing recipe from: {url_str}")

    try:
        # Pobierz HTML
        html_content = fetch_html_safely(url_str)

        # Parsuj przepis
        scraper = scrape_html(html=html_content, org_url=url_str)

        # WyciÄgnij dane
        title = scraper.title()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nie moÅ¼na wyciÄgnÄÄ tytuÅu przepisu z tej strony",
            )

        ingredients = scraper.ingredients()
        if not ingredients:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nie moÅ¼na wyciÄgnÄÄ skÅadnikÃ³w z tej strony",
            )

        try:
            base_portions = extract_portion_count(scraper.yields())
        except Exception:
            base_portions = 1
            logger.warning("Nie udaÅo siÄ odczytaÄ porcji z przepisu, ustawiam 1")
        image_url = scraper.image()
        instructions = scraper.instructions()

        # SprawdÅº czy przepis juÅ¼ istnieje
        recipe = (
            db.query(RecipeDB)
            .filter(RecipeDB.owner_id == current_user.id, RecipeDB.url == url_str)
            .first()
        )

        if recipe:
            logger.info(f"Recipe already exists, updating: {title}")
            # Aktualizuj istniejÄcy przepis
            recipe.title = title
            recipe.ingredients = ingredients
            recipe.instructions = instructions
            recipe.base_portions = base_portions
            recipe.image_url = image_url
            recipe.updated_at = datetime.datetime.utcnow()
        else:
            logger.info(f"Creating new recipe: {title}")
            # UtwÃ³rz nowy przepis
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
            detail=f"BÅÄd podczas przetwarzania przepisu: {str(e)}",
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
    Zwraca listÄ wszystkich dostÄpnych przepisÃ³w z paginacjÄ.
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
            detail="BÅÄd podczas pobierania przepisÃ³w",
        )


@app.get("/api/recipes/{recipe_id}", response_model=RecipeResponse, tags=["Recipes"])
async def get_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """
    Zwraca szczegÃ³Åy konkretnego przepisu.
    """
    recipe = (
        db.query(RecipeDB)
        .filter(RecipeDB.id == recipe_id, RecipeDB.owner_id == current_user.id)
        .first()
    )
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Przepis o ID {recipe_id} nie zostaÅ znaleziony",
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
    Ustawia ocenÄ przepisu (1-5) dla aktualnego uÅ¼ytkownika.
    """
    recipe = (
        db.query(RecipeDB)
        .filter(RecipeDB.id == recipe_id, RecipeDB.owner_id == current_user.id)
        .first()
    )
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Przepis o ID {recipe_id} nie zostaÅ znaleziony",
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
            detail=f"Przepis o ID {recipe_id} nie zostaÅ znaleziony",
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
    Generuje zoptymalizowanÄ listÄ zakupÃ³w na podstawie wybranych przepisÃ³w.
    UÅ¼ywa AI do inteligentnego ÅÄczenia i kategoryzacji skÅadnikÃ³w.
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
            detail=f"Nie znaleziono przepisÃ³w o ID: {missing_recipes}",
        )

    if not compiled_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Brak danych do wygenerowania listy zakupÃ³w",
        )

    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI jest niedostÄpne. Skonfiguruj GROQ_API_KEY.",
        )

    # Ulepszone prompt dla AI
    prompt = f"""
Dzia?asz jako ekspert logistyki kuchennej KitchenOS. Twoim zadaniem jest skonsolidowanie sk?adnik?w z wielu przepis?w w jedn?, przejrzyst? list? zakup?w.

DANE WEJ?CIOWE:
{json.dumps(compiled_data, indent=2, ensure_ascii=False)}

RESTRYKCYJNE ZASADY GENEROWANIA:

0. ZERO HALUCYNACJI (KRYTYCZNE):
   - NIE DODAWAJ ?adnych produkt?w, kt?rych nie ma w danych wej?ciowych.
   - Je?li sk?adnik w wej?ciu jest nieprecyzyjny (np. "oliwa truflowa"), zachowaj go dok?adnie jako osobny produkt.
   - Nie dodawaj og?lnik?w typu "mi?so", "sos", "makaron" itp., je?li nie wyst?puj? w wej?ciu.

1. FILTRACJA ZER (KRYTYCZNE):
   - Je?li po przeliczeniu ilo?? jakiegokolwiek sk?adnika wynosi 0, jest bliska 0 (np. 0.1) lub tekst sugeruje brak (np. "opcjonalnie"), CA?KOWICIE USU? ten produkt z listy.
   - NIE WOLNO wypisywa? produkt?w z ilo?ci? "0".

2. INTELIGENTNE ZAOKR?GLANIE W G?R?:
   - Produkty liczone w sztukach (cebula, czosnek, jaja, warzywa w ca?o?ci) ZAWSZE zaokr?glaj do najbli?szej LICZBY CA?KOWITEJ W G?R?.
   - NIE zamieniaj jednostek wagowych (g, ml) na "sztuki". Je?li wej?cie ma gramy lub ?y?ki - zachowaj te jednostki.
   - Przyk?ad: 0.2 cebuli -> 1 cebula, 1.1 pora -> 2 pory.

3. AGREGACJA I JEDNOSTKI:
   - Zsumuj identyczne sk?adniki (np. s?l z 3 przepis?w).
   - Format: "Nazwa produktu (Ilo?? Jednostka)".
   - Je?li sk?adnik w wej?ciu nie ma ilo?ci, wypisz sam? nazw? bez nawiasu.
   - U?ywaj czytelnych u?amk?w (1/2, 1/4) dla szklanek/?y?ek, ale liczb ca?kowitych dla sztuk.

4. KATEGORYZACJA:
   - Przypisz produkty do kategorii: Warzywa i owoce, Mi?so i ryby, Nabia? i jaja, Pieczywo i makarony, Oleje i t?uszcze, Przyprawy i dodatki, Produkty sypkie, Inne.

ZWR?? WY??CZNIE CZYSTY JSON:
{
  "shopping_list": [
    {
      "category": "Warzywa i owoce",
      "items": ["Cebula (2 sztuki)", "Czosnek (1 g??wka)"]
    }
  ]
}
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
            detail="AI zwrÃ³ciÅo nieprawidÅowy format danych",
        )
    except Exception as e:
        logger.error(f"Error generating shopping list: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"BÅÄd podczas generowania listy: {str(e)}",
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
            detail="BÅÄd podczas pobierania statystyk",
        )


# --- ENDPOINTY PLANERA (POPRZEÅIONE NA GÃRÄ) ---


@app.get("/api/plan/load", tags=["Planner"])
async def load_plan(
    db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)
):
    """Åaduje zapisany plan uÅ¼ytkownika."""
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
    """Zapisuje plan uÅ¼ytkownika."""
    # Walidacja wejÅcia
    selections = plan_data.get("selections", [])
    if not isinstance(selections, list):
        raise HTTPException(status_code=400, detail="Plan musi byÄ listÄ")

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
    Pozwala uÅ¼ytkownikowi wkleiÄ surowy tekst przepisu.
    AI parsuje tytuÅ, skÅadniki i instrukcje.
    """
    content = (raw_data.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Tekst przepisu nie moÅ¼e byÄ pusty")

    logger.info("Parsing custom recipe from raw text...")

    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI jest niedostÄpne. Skonfiguruj GROQ_API_KEY.",
        )

    prompt = f"""
Zanalizuj poniÅ¼szy tekst przepisu kucharskiego.
WyodrÄbnij dane i zwrÃ³Ä je jako JSON.

Zasady:
1. JeÅli nie ma tytuÅu, nadaj wÅasny np. "Przepis Domowy".
2. SkÅadniki: ZwrÃ³Ä listÄ stringÃ³w. UsuÅ numery z wierszy skÅadnikÃ³w.
3. Porcje: JeÅli nie jest podane, przyjmij 1.

TEKST WEJÅCIOWY:
{content}

ZWROT (tylko JSON):
{{
  "title": "TytuÅ",
  "portions": 1,
  "ingredients": ["SkÅadnik 1", "SkÅadnik 2"],
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

        # Ikona domyÅlna
        generic_icon = "https://cdn-icons-png.flaticon.com/512/3081/3081557.png"

        # --- KLUCZOWE: unikalny URL, bo w bazie url ma unique=True ---
        custom_url = f"custom:{uuid.uuid4()}"

        recipe = RecipeDB(
            owner_id=current_user.id,
            title=(parsed_data.get("title") or "Przepis WÅasny").strip(),
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
            detail="AI nie poradziÅo sobie z tekstem. SprÃ³buj formatu: 'TytuÅ\\nSkÅadniki...\\nInstrukcje...'",
        )

def _normalize_inspire_ingredients(raw: Any) -> List[str]:
    ingredients: List[str] = []
    if isinstance(raw, list):
        for item in raw:
            text = str(item or "").strip()
            if text:
                ingredients.append(text)
    elif isinstance(raw, dict):
        value = raw.get("ingredients")
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip()
                if text:
                    ingredients.append(text)
    return ingredients


def _normalize_instruction_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return [line.strip() for line in re.split(r"[\\r\\n]+", raw) if line.strip()]
    return []


def _build_inspire_response(payload: dict, user_ingredients: List[str]) -> InspireRecipeResponse:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="AI zwrÄÅciÄ¹âo nieprawidÄ¹âowe dane")

    title = str(payload.get("title") or "Inspiracja z lodÄÅwki").strip()
    description = str(payload.get("description") or "").strip() or None
    difficulty = str(payload.get("difficulty") or "").strip() or None
    prep_time = str(payload.get("prep_time") or "").strip() or None
    tips = str(payload.get("tips") or "").strip() or None

    normalized_user = {item.lower().strip() for item in user_ingredients if item.strip()}
    ingredients_raw = payload.get("ingredients") or []
    ingredients: List[InspireIngredient] = []
    if isinstance(ingredients_raw, list):
        for entry in ingredients_raw:
            if isinstance(entry, dict):
                item_name = str(entry.get("item") or "").strip()
                amount = str(entry.get("amount") or "").strip()
                is_extra = bool(entry.get("is_extra", False))
            else:
                item_name = str(entry or "").strip()
                amount = ""
                is_extra = False

            if not item_name:
                continue
            if not is_extra:
                is_extra = item_name.lower().strip() not in normalized_user
            ingredients.append(
                InspireIngredient(item=item_name, amount=amount, is_extra=is_extra)
            )

    instructions = _normalize_instruction_list(payload.get("instructions"))
    if not ingredients or not instructions:
        raise HTTPException(status_code=502, detail="AI zwrÄÅciÄ¹âo niekompletny przepis")

    return InspireRecipeResponse(
        title=title,
        description=description,
        difficulty=difficulty,
        prep_time=prep_time,
        ingredients=ingredients,
        instructions=instructions,
        tips=tips,
    )


@app.post("/api/ai/inspire", response_model=InspireRecipeResponse, tags=["AI"])
async def inspire_recipe(
    raw_payload: Any = Body(...),
    current_user: UserDB = Depends(get_current_user),
):
    ingredients = _normalize_inspire_ingredients(raw_payload)
    if not ingredients:
        raise HTTPException(status_code=400, detail="Lista skÄ¹âadnikÄÅw nie moÄ¹Ä½e byÃâ¡ pusta")

    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI jest niedostÃâ¢pne. Skonfiguruj GROQ_API_KEY.",
        )

    prompt = f"""
Role: JesteÄ¹âº kreatywnym Szefem Kuchni i ekspertem Zero Waste wspÄÅÄ¹âpracujÃâ¦cym z systemem KitchenOS.
Task: Na podstawie listy skÄ¹âadnikÄÅw podanych przez uÄ¹Ä½ytkownika, zaproponuj JEDEN konkretny, smaczny i realistyczny przepis.

ZASADY:
1. SkÄ¹âadniki: Maksymalnie wykorzystaj to, co podaÄ¹â uÄ¹Ä½ytkownik. MoÄ¹Ä½esz zaÄ¹âoÄ¹Ä½yÃâ¡, Ä¹Ä½e uÄ¹Ä½ytkownik posiada "bazÃâ¢" (sÄÅl, pieprz, woda, olej, podstawowe przyprawy).
2. Format: ZwrÄÅÃâ¡ ODPOWIEDÄ¹Â¹ WYÄ¹ÂÃâCZNIE W FORMACIE JSON. Nie pisz Ä¹Ä½adnych wstÃâ¢pÄÅw ani podsumowaÄ¹â.
3. JÃâ¢zyk: Odpowiadaj w jÃâ¢zyku polskim.
4. KreatywnoÄ¹âºÃâ¡: JeÄ¹âºli skÄ¹âadniki do siebie nie pasujÃâ¦, sprÄÅbuj znaleÄ¹ÅÃâ¡ najbardziej sensowne poÄ¹âÃâ¦czenie (np. kuchnia fusion).

STRUKTURA JSON:
{{
  "title": "Nazwa dania",
  "description": "KrÄÅtki, apetyczny opis (max 2 zdania).",
  "difficulty": "Ä¹Âatwe/Ä¹Å¡rednie/Trudne",
  "prep_time": "czas w minutach",
  "ingredients": [
    {{"item": "nazwa", "amount": "iloÄ¹âºÃâ¡", "is_extra": true/false}}
  ],
  "instructions": ["Krok 1...", "Krok 2..."],
  "tips": "Opcjonalna porada szefa kuchni."
}}

*is_extra: oznacz jako true, jeÄ¹âºli skÄ¹âadnika nie ma na liÄ¹âºcie uÄ¹Ä½ytkownika, ale jest niezbÃâ¢dny do wykonania dania.*

SKÄ¹ÂADNIKI UÄ¹Â»YTKOWNIKA:
{json.dumps(ingredients, ensure_ascii=False)}
"""

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        ai_response = chat_completion.choices[0].message.content or "{}"
        try:
            parsed = json.loads(ai_response)
        except json.JSONDecodeError:
            start = ai_response.find("{")
            end = ai_response.rfind("}")
            if start == -1 or end == -1:
                raise HTTPException(status_code=502, detail="AI zwrÄÅciÄ¹âo nieprawidÄ¹âowy JSON")
            parsed = json.loads(ai_response[start : end + 1])

        return _build_inspire_response(parsed, ingredients)
    except HTTPException:
        raise
    except ValidationError:
        raise HTTPException(status_code=502, detail="AI zwrÄÅciÄ¹âo niepoprawny format danych")
    except Exception as e:
        logger.error(f"Error inspiring recipe: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nie udaÄ¹âo siÃâ¢ wygenerowaÃâ¡ inspiracji",
        )


@app.post(
    "/api/recipes",
    response_model=RecipeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Recipes"],
)
async def create_recipe(
    payload: RecipeCreateRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="TytuÄ¹â nie moÄ¹Ä½e byÃâ¡ pusty")

    ingredients: List[str] = []
    if payload.ingredients:
        if isinstance(payload.ingredients[0], InspireIngredient):
            for item in payload.ingredients:
                amount = item.amount.strip() if item.amount else ""
                if amount:
                    ingredients.append(f"{item.item} ({amount})")
                else:
                    ingredients.append(item.item)
        else:
            ingredients = [str(item).strip() for item in payload.ingredients if str(item).strip()]

    if not ingredients:
        raise HTTPException(status_code=400, detail="Lista skÄ¹âadnikÄÅw nie moÄ¹Ä½e byÃâ¡ pusta")

    instructions_list = _normalize_instruction_list(payload.instructions)
    instructions_text = "\n".join(instructions_list).strip()
    if not instructions_text:
        raise HTTPException(status_code=400, detail="Instrukcje nie mogÃâ¦ byÃâ¡ puste")

    generic_icon = "https://cdn-icons-png.flaticon.com/512/3081/3081557.png"
    recipe = RecipeDB(
        owner_id=current_user.id,
        title=title,
        url=f"ai:{uuid.uuid4()}",
        image_url=generic_icon,
        ingredients=ingredients,
        instructions=instructions_text,
        base_portions=int(payload.base_portions or 1),
    )

    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe

@app.post("/api/plan/export-ics", tags=["Planner"])
async def export_calendar(
    plan_data: dict,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """
    Generuje poprawny plik ICS:
    - DTEND jest dniem nastÄpnym (dla zdarzeÅ caÅodniowych)
    - UID jest stabilny (brak duplikatÃ³w po ponownym imporcie)
    - tekst jest escapowany (bez psucia formatu)
    """
    selections = plan_data.get("selections", [])
    if not selections:
        raise HTTPException(status_code=400, detail="Plan jest pusty")

    today = datetime.date.today()
    day_map = {
        "PoniedziaÅek": 0, "Wtorek": 1, "Åroda": 2, "Czwartek": 3,
        "PiÄtek": 4, "Sobota": 5, "Niedziela": 6
    }

    now_str = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//KitchenOS//PL//PL\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "X-WR-CALNAME:Plan ObiadÃ³w KitchenOS\r\n"
    )

    # Licznik, Å¼eby ten sam przepis tego samego dnia mÃ³gÅ wystÄpiÄ kilka razy
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

        day_name = item.get("day") or "PoniedziaÅek"
        day_offset = day_map.get(day_name, 0)

        # wyznacz datÄ docelowÄ w tym/na nastÄpnym tygodniu
        days_since_monday = day_offset - today.weekday()
        target_date = today + datetime.timedelta(days=days_since_monday)
        if target_date < today:
            target_date += datetime.timedelta(days=7)

        date_str = target_date.strftime("%Y%m%d")
        end_date_str = (target_date + datetime.timedelta(days=1)).strftime("%Y%m%d")  # DTEND = dzieÅ nastÄpny

        portions_val = int(item.get("portions") or 1)

        # stabilny UID: przepis + data + kolejnoÅÄ wystÄpienia w danym dniu
        key = (recipe.id, date_str)
        uid_counters[key] = uid_counters.get(key, 0) + 1
        occ = uid_counters[key]
        uid = f"{recipe.id}-{date_str}-{occ}@kitchenos.local"

        ing_str = " | ".join((recipe.ingredients or [])[:5]) if recipe.ingredients else ""
        if recipe.ingredients and len(recipe.ingredients) > 5:
            ing_str += "..."

        summary = ics_escape(f"ð³ {recipe.title} ({portions_val} porcji)")
        description = ics_escape(f"SkÅadniki: {ing_str}\n\nID Przepisu: {recipe.id}")

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
