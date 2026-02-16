import os
import re
import requests
import datetime
import json
import uuid
import secrets
import unicodedata
from urllib.parse import urlparse, urlencode
from dataclasses import dataclass
from fastapi import FastAPI, HTTPException, Depends, status, Body
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, HttpUrl, Field, EmailStr, ValidationError
from typing import List, Optional, Any, Literal
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
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
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
        raise HTTPException(status_code=400, detail="Hasło jest za długie (limit 72 znaki)")
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
        raise HTTPException(status_code=400, detail="Nieprawidlowy token stanu OAuth")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Brak użytkownika w tokenie OAuth")
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Nieprawidłowy identyfikator użytkownika")


def get_google_token_record(db: Session, user_id: int) -> GoogleCalendarDB:
    record = db.query(GoogleCalendarDB).filter(GoogleCalendarDB.owner_id == user_id).first()
    if not record:
        raise HTTPException(status_code=400, detail="Brak polaczenia z Google Calendar")
    return record


def refresh_google_access_token(db: Session, record: GoogleCalendarDB) -> str:
    if record.expires_at and record.expires_at > datetime.datetime.utcnow() + datetime.timedelta(seconds=60):
        return record.access_token
    if not record.refresh_token:
        raise HTTPException(status_code=401, detail="Brak refresh token. Polacz Google ponownie.")

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
        raise HTTPException(status_code=502, detail="Nie udało się odświeżyć tokenu Google")
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
            detail="Brak uprawnien administratora",
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
    servings_unit: Optional[Literal["servings", "people"]] = "servings"


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
    servings_unit: Optional[str] = None
    yield_display_label: Optional[str] = None
    yield_assumption_reason: Optional[str] = None
    total_weight_g: Optional[float] = None
    portion_weight_g: Optional[float] = None
    piece_weight_g: Optional[float] = None
    pan_diameter_min_cm: Optional[float] = None
    pan_diameter_max_cm: Optional[float] = None
    nutrition_protein_g: Optional[float] = None
    nutrition_carbs_g: Optional[float] = None
    nutrition_fat_g: Optional[float] = None
    nutrition_fiber_g: Optional[float] = None
    nutrition_glycemic_load: Optional[float] = None
    nutrition_calories_kcal: Optional[float] = None
    nutrition_source: Optional[Literal["page_100g", "ai", "mixed"]] = None
    nutrition_confidence_score: Optional[float] = None
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
    portions: int = Field(..., gt=0, le=500, description="Liczba porcji (1-500)")


class PlannerRequest(BaseModel):
    selections: List[RecipeSelection] = Field(..., min_items=1, max_items=50)


class ShoppingCategory(BaseModel):
    category: str
    items: List[str]


class ShoppingListResponse(BaseModel):
    shopping_list: List[ShoppingCategory]
    total_recipes: int
    generated_at: datetime.datetime
    generation_mode: Optional[Literal["ai", "fallback"]] = None
    warning: Optional[str] = None


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
@dataclass
class YieldContext:
    mode: Literal["explicit_servings", "explicit_people", "explicit_pieces", "pan_size", "total_weight_only", "unknown"] = "unknown"
    base_portions: int = 1
    servings_unit: Literal["servings", "people"] = "servings"
    yield_display_label: Optional[str] = None
    total_weight_g: Optional[float] = None
    portion_weight_g: Optional[float] = None
    piece_weight_g: Optional[float] = None
    pan_diameter_min_cm: Optional[float] = None
    pan_diameter_max_cm: Optional[float] = None
    assumption_reason: Optional[str] = None


PAN_DIAMETER_PORTION_TABLE = [
    (16.0, 18.0, 8),
    (20.0, 22.0, 10),
    (24.0, 26.0, 12),
    (28.0, 30.0, 14),
]
DEFAULT_PAN_PORTIONS = 12
RECTANGULAR_PAN_CM2_PER_PORTION = 70.0
MIN_RECTANGULAR_PAN_PORTIONS = 4
MAX_RECTANGULAR_PAN_PORTIONS = 20
DEFAULT_PORTION_WEIGHT_BY_TYPE_G = {
    "soup": 350.0,
    "dessert": 120.0,
    "main": 400.0,
    "default": 250.0,
}
YIELD_NUMBER_LIMIT = 200
SNACK_PORTION_WEIGHT_G = 30.0
GENERAL_DESSERT_PORTION_WEIGHT_G = 40.0
SNACK_TOTAL_WEIGHT_THRESHOLD_G = 500.0
SNACK_MAX_KCAL_PER_PORTION = 800.0
MEAL_MAX_KCAL_PER_PORTION = 900.0
MEAL_MIN_PORTION_WEIGHT_G = 140.0
GL_MAX_DISPLAY_VALUE = 50.0
PLANNER_MAX_PORTIONS = 500
LOW_CONFIDENCE_TERMS = (
    "dowolna ilosc",
    "dowolna ilość",
    "garść",
    "garsc",
    "szczypta",
    "do smaku",
    "wedlug uznania",
    "według uznania",
)


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    transliterated = str(value).translate(
        str.maketrans(
            {
                "ł": "l",
                "Ł": "l",
                "ß": "ss",
            }
        )
    )
    normalized = unicodedata.normalize("NFKD", transliterated)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _parse_number_token(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _safe_portion_count(value: Optional[float], fallback: int = 1) -> int:
    if value is None:
        return fallback
    count = int(round(value))
    if count <= 0:
        return fallback
    if count > YIELD_NUMBER_LIMIT:
        return fallback
    return count


def _detect_recipe_type(title: str, ingredients: List[str], instructions: List[str]) -> Literal["soup", "dessert", "main", "default"]:
    blob = _normalize_text(" ".join([title, " ".join(ingredients), " ".join(instructions)]))

    soup_keywords = ("zupa", "krem", "rosol", "barszcz", "bulion")
    hearty_main_keywords = (
        "fasol",
        "kielbas",
        "boczek",
        "gulasz",
        "bigos",
        "leczo",
        "grochow",
        "ziemniak",
        "zupa",
    )
    dessert_keywords = (
        "tort",
        "ciasto",
        "deser",
        "paczek",
        "oponk",
        "babeczk",
        "muffin",
        "sernik",
        "slodk",
        "karmel",
        "migdal",
        "czekolad",
    )
    main_keywords = ("obiad", "danie", "makaron", "kurczak", "mieso", "ryz", "ryba")

    if any(keyword in blob for keyword in soup_keywords):
        return "soup"
    if any(keyword in blob for keyword in hearty_main_keywords):
        return "main"
    if any(keyword in blob for keyword in dessert_keywords):
        return "dessert"
    if any(keyword in blob for keyword in main_keywords):
        return "main"
    return "default"


def _is_snack_like_recipe(title: str, ingredients: List[str], instructions: List[str]) -> bool:
    blob = _normalize_text(" ".join([title, " ".join(ingredients), " ".join(instructions)]))
    snack_keywords = (
        "przekask",
        "snack",
        "baton",
        "kulk",
        "orzech",
        "migdal",
        "karmel",
        "cukierki",
        "ciasteczk",
    )
    meal_keywords = (
        "zupa",
        "fasol",
        "kielbas",
        "boczek",
        "gulasz",
        "bigos",
        "obiad",
        "danie",
        "kurczak",
        "mieso",
        "ziemniak",
        "makaron",
        "ryz",
    )
    has_snack = any(keyword in blob for keyword in snack_keywords)
    has_meal = any(keyword in blob for keyword in meal_keywords)
    return has_snack and not has_meal


def _is_sweet_snack_recipe(title: str, ingredients: List[str], instructions: List[str]) -> bool:
    blob = _normalize_text(" ".join([title, " ".join(ingredients), " ".join(instructions)]))
    has_sweet_tokens = any(token in blob for token in ("cukier", "miod", "miód", "karmel", "slodycz", "słodycz"))
    has_nut_tokens = any(token in blob for token in ("orzech", "migdal", "migdał", "migdal", "migdaly"))
    has_meal_tokens = any(token in blob for token in ("mieso", "mięso", "kurczak", "ziemniak", "makaron", "ryz", "ryż"))
    return (has_sweet_tokens and has_nut_tokens) and not has_meal_tokens


def _get_snack_standard_portion_weight_g(title: str, ingredients: List[str], instructions: List[str]) -> float:
    if _is_sweet_snack_recipe(title, ingredients, instructions):
        return SNACK_PORTION_WEIGHT_G
    return GENERAL_DESSERT_PORTION_WEIGHT_G


def _get_standard_portion_weight_g(title: str, ingredients: List[str], instructions: List[str]) -> float:
    if _is_snack_like_recipe(title, ingredients, instructions):
        return _get_snack_standard_portion_weight_g(title, ingredients, instructions)
    recipe_type = _detect_recipe_type(title, ingredients, instructions)
    return DEFAULT_PORTION_WEIGHT_BY_TYPE_G.get(recipe_type, DEFAULT_PORTION_WEIGHT_BY_TYPE_G["default"])


def _map_pan_size_to_portions(min_cm: float, max_cm: float) -> int:
    avg = (min_cm + max_cm) / 2.0
    for range_min, range_max, portions in PAN_DIAMETER_PORTION_TABLE:
        if range_min <= avg <= range_max:
            return portions
    return DEFAULT_PAN_PORTIONS


def _map_rectangular_pan_to_portions(width_cm: float, height_cm: float) -> int:
    area_cm2 = max(1.0, width_cm * height_cm)
    estimated = int(round(area_cm2 / RECTANGULAR_PAN_CM2_PER_PORTION))
    if estimated <= 0:
        return DEFAULT_PAN_PORTIONS
    return max(MIN_RECTANGULAR_PAN_PORTIONS, min(MAX_RECTANGULAR_PAN_PORTIONS, estimated))


def _extract_piece_weight_g(norm_text: str) -> Optional[float]:
    patterns = [
        r"(?:waga\s*)?(?:do|okolo|ponad|~)?\s*(\d+(?:[.,]\d+)?)\s*g(?:\b|\s)",
        r"(\d+(?:[.,]\d+)?)\s*g\s*(?:kazd\w*|szt\w*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, norm_text)
        if not match:
            continue
        value = _parse_number_token(match.group(1))
        if value is None or value <= 0:
            continue
        return round(value, 1)
    return None


def _extract_total_weight_g(norm_text: str) -> Optional[float]:
    contextual_patterns = [
        r"(?:liczba\s+porcji|porcji|porcje|yield|servings?)\s*[:\-]?\s*(?:okolo|ponad|do|~)?\s*(\d+(?:[.,]\d+)?)\s*(kg|g)\b",
        r"(?:okolo|ponad|do|~)?\s*(\d+(?:[.,]\d+)?)\s*(kg|g)\b[^.\n]{0,24}(?:dania|zupy|calosci|calosc)\b",
    ]
    matches: List[tuple[str, str]] = []
    for pattern in contextual_patterns:
        matches.extend(re.findall(pattern, norm_text))

    totals: List[float] = []
    for number_raw, unit in matches:
        value = _parse_number_token(number_raw)
        if value is None or value <= 0:
            continue
        totals.append(value * 1000.0 if unit == "kg" else value)

    # Fallback for short yield labels like "do 500 g".
    if not totals and len(norm_text.split()) <= 8:
        bare_match = re.search(
            r"^(?:liczba\s+porcji\s*[:\-]?\s*)?(?:okolo|ponad|do|~)?\s*(\d+(?:[.,]\d+)?)\s*(kg|g)\b",
            norm_text,
        )
        if bare_match:
            value = _parse_number_token(bare_match.group(1))
            unit = bare_match.group(2)
            if value is not None and value > 0:
                totals.append(value * 1000.0 if unit == "kg" else value)

    if not totals:
        return None
    return round(max(totals), 1)


def _line_has_yield_keyword(norm_line: str) -> bool:
    return bool(
        re.search(
            r"\b(liczba porcji|porcj\w*|servings?|dla\s+\d+\s+osob|osob\w*|tortownica|forma|blacha|szt\w*)\b",
            norm_line,
        )
    )


def _line_has_yield_value(norm_line: str) -> bool:
    return bool(re.search(r"\d", norm_line)) and bool(
        re.search(r"\b(kg|g|cm|porcj\w*|osob\w*|szt\w*|servings?|people|person)\b", norm_line)
    )


def extract_yield_text_from_text_blob(text_blob: str, raw_fallback: str = "") -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in re.split(r"[\r\n]+", text_blob or "")]
    lines = [line for line in lines if line]
    norms = [_normalize_text(line) for line in lines]

    # Primary: keyword + value in one or adjacent lines.
    for idx, line in enumerate(lines):
        norm = norms[idx]
        if _line_has_yield_keyword(norm) and _line_has_yield_value(norm):
            return line
        if _line_has_yield_keyword(norm) and idx + 1 < len(lines) and _line_has_yield_value(norms[idx + 1]):
            return f"{line} {lines[idx + 1]}"
        if _line_has_yield_value(norm) and idx > 0 and _line_has_yield_keyword(norms[idx - 1]):
            return f"{lines[idx - 1]} {line}"

    # Secondary: single-line weight labels like "do 500 g".
    for idx, line in enumerate(lines):
        norm = norms[idx]
        if re.match(r"^(?:okolo|ponad|do|~)?\s*\d+(?:[.,]\d+)?\s*(kg|g)\b(?:\s+\w+){0,3}$", norm):
            return line

    if raw_fallback:
        norm_fallback = _normalize_text(raw_fallback)
        if _line_has_yield_keyword(norm_fallback) or _line_has_yield_value(norm_fallback):
            return raw_fallback

    return ""


def extract_yield_text_from_page(scraper: Any, html_content: str) -> str:
    raw = ""
    try:
        raw = (scraper.yields() or "").strip()
        raw_norm = _normalize_text(raw)
        if raw and _line_has_yield_keyword(raw_norm) and _line_has_yield_value(raw_norm):
            return raw
        if raw and re.match(r"^(?:okolo|ponad|do|~)?\s*\d+(?:[.,]\d+)?\s*(kg|g)\b(?:\s+\w+){0,3}$", raw_norm):
            return raw
    except Exception:
        raw = ""

    try:
        text_blob = scraper.soup.get_text("\n", strip=True)
    except Exception:
        text_blob = re.sub(r"<[^>]+>", " ", html_content or "")

    extracted = extract_yield_text_from_text_blob(text_blob=text_blob, raw_fallback=raw)
    if extracted:
        return extracted

    if raw:
        return raw
    return ""


def _extract_ingredient_weight_breakdown(ingredients: List[str]) -> dict:
    total_g = 0.0
    water_g = 0.0
    oil_g = 0.0
    dry_starch_g = 0.0

    for ingredient in ingredients:
        norm = _normalize_text(ingredient)
        if not norm:
            continue

        unit_matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b", norm)
        ingredient_weight_g = 0.0
        if unit_matches:
            for number_raw, unit in unit_matches:
                value = _parse_number_token(number_raw)
                if value is None or value <= 0:
                    continue
                if unit in ("kg", "l"):
                    ingredient_weight_g += value * 1000.0
                else:
                    ingredient_weight_g += value
            total_g += ingredient_weight_g

            if "woda" in norm:
                water_g += ingredient_weight_g
            if any(token in norm for token in ("olej", "oliwa", "maslo klarowane", "masło klarowane", "smalec")):
                oil_g += ingredient_weight_g
            if any(token in norm for token in ("makaron", "ryz", "kasz", "bulgur", "quinoa")):
                dry_starch_g += ingredient_weight_g
            continue

        if "jaj" in norm:
            eggs_match = re.search(r"(\d+)\s*(?:szt|sztuk|jaj\w*)", norm)
            if eggs_match:
                total_g += int(eggs_match.group(1)) * 60.0

    return {
        "total_g": round(total_g, 1),
        "water_g": round(water_g, 1),
        "oil_g": round(oil_g, 1),
        "dry_starch_g": round(dry_starch_g, 1),
    }


def _infer_process_tags(title: str, ingredients: List[str], instructions: List[str]) -> set[str]:
    text_blob = _normalize_text(" ".join([title, " ".join(ingredients), " ".join(instructions)]))
    tags: set[str] = set()

    if re.search(r"\b(karmeliz|reduk|odpar|piec|piekarnik|zapiec)\w*", text_blob):
        tags.add("reduction")
    if re.search(r"\b(ugotuj|gotuj|gotowac|wrzacej wodzie|wrzatku)\b", text_blob) and re.search(
        r"\b(makaron|ryz|kasz|bulgur|quinoa)\b", text_blob
    ):
        tags.add("hydration")
    if re.search(r"\b(smaz|smazenie|podsmaz|fryt)\w*", text_blob):
        tags.add("frying")
    return tags


def _adjust_weight_for_process(
    *,
    total_weight_g: float,
    title: str,
    ingredients: List[str],
    instructions: List[str],
) -> tuple[float, List[str]]:
    breakdown = _extract_ingredient_weight_breakdown(ingredients)
    process_tags = _infer_process_tags(title, ingredients, instructions)
    adjusted_weight = float(total_weight_g)
    assumptions: List[str] = []

    if "reduction" in process_tags and breakdown["water_g"] > 0:
        retention = 0.05 if "karmel" in _normalize_text(title) else 0.2
        evaporated = breakdown["water_g"] * (1.0 - retention)
        adjusted_weight -= evaporated
        assumptions.append(f"Proces redukcji/pieczenia: odparowano ~{evaporated:.0f} g wody")

    if "frying" in process_tags and breakdown["oil_g"] > 0:
        retained_oil = breakdown["oil_g"] * 0.1
        discarded_oil = breakdown["oil_g"] - retained_oil
        adjusted_weight -= discarded_oil
        assumptions.append(f"Smażenie: przyjęto absorpcję ~{retained_oil:.0f} g tłuszczu")

    if "hydration" in process_tags and breakdown["dry_starch_g"] > 0:
        absorbed_water = breakdown["dry_starch_g"] * 1.5
        adjusted_weight += absorbed_water
        assumptions.append(f"Hydratacja: dodano ~{absorbed_water:.0f} g wchłoniętej wody")

    adjusted_weight = max(1.0, adjusted_weight)
    return round(adjusted_weight, 1), assumptions


def _estimate_total_weight_from_ingredients(ingredients: List[str]) -> Optional[float]:
    breakdown = _extract_ingredient_weight_breakdown(ingredients)
    total_g = breakdown["total_g"]
    if total_g <= 0:
        return None
    return round(total_g, 1)


def estimate_total_weight_with_ai(
    title: str, ingredients: List[str], instructions: List[str]
) -> Optional[float]:
    if client is None or not ingredients:
        return None

    prompt = "\n".join(
        [
            "Zwroc wylacznie JSON.",
            "Oszacuj calkowita mase gotowego dania w gramach.",
            f"title: {title or ''}",
            f"ingredients: {json.dumps(ingredients, ensure_ascii=False)}",
            f"instructions: {json.dumps(instructions, ensure_ascii=False)}",
            "",
            "Wymagany format:",
            '{ "estimated_total_weight_g": number }',
            "",
            "Zasady:",
            "- liczba >= 0",
            "- bez komentarzy i dodatkowych pol",
        ]
    )

    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or "{}"
        parsed_raw = json.loads(raw)
        value = _coerce_nutrition_number(parsed_raw.get("estimated_total_weight_g"))
        if value is None:
            return None
        return round(value, 1)
    except Exception as exc:
        logger.warning("Total weight request failed: %s", str(exc))
        return None


def parse_yield_context(
    yield_text: str,
    title: str,
    ingredients: List[str],
    instructions: List[str],
) -> YieldContext:
    raw = (yield_text or "").strip()
    context = YieldContext(yield_display_label=raw or None)
    if not raw:
        return context

    norm = _normalize_text(raw)

    people_patterns = [
        r"(?:dla\s*)?(\d+)\s*(?:osob|osoby|osoba|people|person)\b",
        r"(?:osob|osoby|osoba|people|person)\s*[:\-]?\s*(\d+)\b",
    ]
    for pattern in people_patterns:
        match = re.search(pattern, norm)
        if match:
            count = _safe_portion_count(_parse_number_token(match.group(1)))
            return YieldContext(
                mode="explicit_people",
                base_portions=count,
                servings_unit="people",
                yield_display_label=raw,
            )

    servings_patterns = [
        r"\b(\d+)\s*(?:porcj\w*|servings?)\b",
        r"(?:porcj\w*|servings?)\s*[:\-]?\s*(\d+)\b",
    ]
    for pattern in servings_patterns:
        match = re.search(pattern, norm)
        if match:
            # Guardrail: "forma 20 x 29 cm" should be interpreted as pan size, not serving count.
            if re.search(r"\b(?:tortownica|forma|blacha|naczynie|brytfanna)\b", norm) and re.search(r"\bcm\b", norm):
                continue
            if re.search(r"\b\d+(?:[.,]\d+)?\s*[x×]\s*\d+(?:[.,]\d+)?\s*cm\b", norm):
                continue
            count = _safe_portion_count(_parse_number_token(match.group(1)))
            if re.search(
                rf"(?:porcj\w*|servings?)\s*[:\-]?\s*(?:okolo|ponad|do|~)?\s*{count}\s*(?:kg|g)\b",
                norm,
            ):
                continue
            piece_hint = re.search(
                rf"\b{count}\s*(?:\w+\s+){{0,2}}(?:szt|sztuk\w*|opon\w*|paczk\w*|kawal\w*|babeczk\w*)\b",
                norm,
            )
            if piece_hint:
                piece_weight_g = _extract_piece_weight_g(norm)
                total_weight_g = round(piece_weight_g * count, 1) if piece_weight_g else None
                return YieldContext(
                    mode="explicit_pieces",
                    base_portions=count,
                    servings_unit="servings",
                    yield_display_label=raw,
                    total_weight_g=total_weight_g,
                    portion_weight_g=piece_weight_g,
                    piece_weight_g=piece_weight_g,
                )
            return YieldContext(
                mode="explicit_servings",
                base_portions=count,
                servings_unit="servings",
                yield_display_label=raw,
            )

    piece_patterns = [
        r"\b(\d+)\s*(?:szt|sztuk\w*|pieces?)\b",
        r"\b(\d+)\s*(?:\w+\s+){0,2}(?:opon\w*|paczk\w*|kawal\w*|babeczk\w*)\b",
    ]
    for pattern in piece_patterns:
        match = re.search(pattern, norm)
        if match:
            count = _safe_portion_count(_parse_number_token(match.group(1)))
            piece_weight_g = _extract_piece_weight_g(norm)
            total_weight_g = round(piece_weight_g * count, 1) if piece_weight_g else None
            return YieldContext(
                mode="explicit_pieces",
                base_portions=count,
                servings_unit="servings",
                yield_display_label=raw,
                total_weight_g=total_weight_g,
                portion_weight_g=piece_weight_g,
                piece_weight_g=piece_weight_g,
            )

    rectangular_pan_patterns = [
        r"(?:tortownica|forma|blacha|naczynie|brytfanna)[^\d]{0,20}(\d{2}(?:[.,]\d+)?)\s*[x×]\s*(\d{2}(?:[.,]\d+)?)\s*cm\b",
        r"\b(\d{2}(?:[.,]\d+)?)\s*[x×]\s*(\d{2}(?:[.,]\d+)?)\s*cm\b[^\n]{0,24}(?:tortownica|forma|blacha|naczynie|brytfanna)",
    ]
    for pattern in rectangular_pan_patterns:
        match = re.search(pattern, norm)
        if match:
            width = _parse_number_token(match.group(1))
            height = _parse_number_token(match.group(2))
            if width is None or height is None:
                continue
            min_cm = round(min(width, height), 1)
            max_cm = round(max(width, height), 1)
            portions = _map_rectangular_pan_to_portions(min_cm, max_cm)
            return YieldContext(
                mode="pan_size",
                base_portions=portions,
                servings_unit="servings",
                yield_display_label=raw,
                pan_diameter_min_cm=min_cm,
                pan_diameter_max_cm=max_cm,
                assumption_reason=f"Rectangular pan {min_cm:g}x{max_cm:g} cm mapped to {portions} portions",
            )

    round_pan_patterns = [
        r"(?:tortownica|forma|blacha|naczynie|brytfanna)[^\d]{0,20}(\d{2}(?:[.,]\d+)?)(?:\s*[-–]\s*(\d{2}(?:[.,]\d+)?))?\s*cm\b",
        r"\b(\d{2}(?:[.,]\d+)?)(?:\s*[-–]\s*(\d{2}(?:[.,]\d+)?))?\s*cm\b[^\n]{0,24}(?:tortownica|forma|blacha|naczynie|brytfanna)",
    ]
    for pattern in round_pan_patterns:
        match = re.search(pattern, norm)
        if match:
            min_raw = _parse_number_token(match.group(1))
            max_raw = _parse_number_token(match.group(2) or match.group(1))
            if min_raw is None or max_raw is None:
                continue
            min_cm = float(min_raw)
            max_cm = float(max_raw)
            portions = _map_pan_size_to_portions(min_cm, max_cm)
            return YieldContext(
                mode="pan_size",
                base_portions=portions,
                servings_unit="servings",
                yield_display_label=raw,
                pan_diameter_min_cm=min_cm,
                pan_diameter_max_cm=max_cm,
                assumption_reason=f"Pan size {min_cm:g}-{max_cm:g} cm mapped to {portions} portions",
            )

    total_weight_g = _extract_total_weight_g(norm)
    if total_weight_g:
        standard_weight_g = _get_standard_portion_weight_g(title, ingredients, instructions)
        portions = max(1, round(total_weight_g / standard_weight_g))
        portion_weight_g = round(total_weight_g / portions, 1)
        return YieldContext(
            mode="total_weight_only",
            base_portions=portions,
            servings_unit="servings",
            yield_display_label=raw,
            total_weight_g=total_weight_g,
            portion_weight_g=portion_weight_g,
            assumption_reason=f"Used standard portion weight {standard_weight_g:.0f} g",
        )

    return context


def resolve_yield_context_weights(
    context: YieldContext,
    title: str,
    ingredients: List[str],
    instructions: List[str],
) -> YieldContext:
    if context.portion_weight_g and context.total_weight_g:
        return context

    total_weight_from_context = context.total_weight_g is not None
    total_weight_g = context.total_weight_g
    if total_weight_g is None:
        total_weight_g = _estimate_total_weight_from_ingredients(ingredients)
        if total_weight_g is not None:
            adjusted_weight_g, assumptions = _adjust_weight_for_process(
                total_weight_g=total_weight_g,
                title=title,
                ingredients=ingredients,
                instructions=instructions,
            )
            total_weight_g = adjusted_weight_g
            if assumptions and not context.assumption_reason:
                context.assumption_reason = "; ".join(assumptions)
    if total_weight_g is None:
        total_weight_g = estimate_total_weight_with_ai(title, ingredients, instructions)

    if total_weight_g is None:
        return context

    portions = max(1, int(context.base_portions or 1))
    if context.mode == "unknown" and portions <= 1:
        standard_weight_g = _get_standard_portion_weight_g(title, ingredients, instructions)
        portions = max(1, round(total_weight_g / standard_weight_g))
        context.base_portions = portions
        context.mode = "total_weight_only"
        context.assumption_reason = f"Estimated portions from total weight using standard {standard_weight_g:.0f} g"

    # Guardrail: snacks/desserts should not default to one giant portion.
    if (
        context.mode in ("unknown", "total_weight_only")
        and portions <= 1
        and total_weight_g >= SNACK_TOTAL_WEIGHT_THRESHOLD_G
        and _is_snack_like_recipe(title, ingredients, instructions)
    ):
        standard_snack_portion = _get_snack_standard_portion_weight_g(title, ingredients, instructions)
        portions = max(1, round(total_weight_g / standard_snack_portion))
        context.base_portions = portions
        context.mode = "total_weight_only"
        context.assumption_reason = f"Snack-like recipe: used {standard_snack_portion:.0f} g per portion"

    portion_weight = round(total_weight_g / portions, 1)
    context.total_weight_g = round(total_weight_g, 1)
    context.portion_weight_g = portion_weight
    if context.mode == "unknown":
        context.assumption_reason = "Estimated total and per-portion weight from ingredients"
    if total_weight_from_context and not context.assumption_reason:
        context.assumption_reason = "Used total weight provided by recipe yield"
    return context


def extract_portion_count(yield_text: str) -> int:
    context = parse_yield_context(yield_text, "", [], [])
    return max(1, int(context.base_portions or 1))


def detect_servings_unit(text: Optional[str]) -> str:
    context = parse_yield_context(text or "", "", [], [])
    return context.servings_unit


def normalize_servings_unit(value: Optional[str]) -> str:
    if value == "people":
        return "people"
    return "servings"


def _coerce_nutrition_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        normalized = value.strip().replace(",", ".")
        if not normalized:
            return None
        try:
            result = float(normalized)
        except ValueError:
            return None
    else:
        return None

    if result < 0:
        return None
    return round(result, 1)


def _parse_nutrition_payload(payload: dict) -> Optional[dict]:
    keys = ("protein_g", "carbs_g", "fat_g", "fiber_g", "glycemic_load", "calories_kcal")
    parsed = {}
    for key in keys:
        value = _coerce_nutrition_number(payload.get(key))
        if value is None:
            return None
        parsed[key] = value
    return parsed


def _extract_kcal_value(value: str) -> Optional[float]:
    norm = _normalize_text(value)
    kcal_match = re.search(r"(\d+(?:[.,]\d+)?)\s*kcal", norm)
    if kcal_match:
        return _coerce_nutrition_number(kcal_match.group(1))
    return None


def _extract_gram_value(value: str) -> Optional[float]:
    norm = _normalize_text(value)
    gram_match = re.search(r"(\d+(?:[.,]\d+)?)\s*g\b", norm)
    if gram_match:
        return _coerce_nutrition_number(gram_match.group(1))
    return _coerce_nutrition_number(value)


def extract_nutrition_per_100g_from_page(scraper: Any, html_content: str) -> dict:
    parsed: dict = {}

    try:
        nutrients = scraper.nutrients() or {}
    except Exception:
        nutrients = {}

    for key, raw_value in nutrients.items():
        key_norm = _normalize_text(str(key))
        value_text = str(raw_value or "")

        if any(token in key_norm for token in ("calories", "kalori", "energia", "energetyczna", "energy")):
            kcal = _extract_kcal_value(value_text)
            if kcal is not None:
                parsed["calories_kcal"] = kcal
            continue
        if any(token in key_norm for token in ("carbohydrate", "weglowodan", "carbs")):
            carbs = _extract_gram_value(value_text)
            if carbs is not None:
                parsed["carbs_g"] = carbs
            continue
        if any(token in key_norm for token in ("protein", "bialko")):
            protein = _extract_gram_value(value_text)
            if protein is not None:
                parsed["protein_g"] = protein
            continue
        if any(token in key_norm for token in ("fat", "tluszcz", "tluszcze")):
            fat = _extract_gram_value(value_text)
            if fat is not None:
                parsed["fat_g"] = fat
            continue
        if any(token in key_norm for token in ("fiber", "fibre", "blonnik")):
            fiber = _extract_gram_value(value_text)
            if fiber is not None:
                parsed["fiber_g"] = fiber

    if parsed:
        return parsed

    try:
        text_source = scraper.soup.get_text(" ", strip=True)
    except Exception:
        text_source = html_content or ""
    normalized_text = _normalize_text(text_source)
    section_match = re.search(r"w\s*100\s*g(.{0,900})", normalized_text)
    if not section_match:
        return parsed
    section = section_match.group(1)

    energy_match = re.search(
        r"(?:wartosc\s*energetyczna|energia|energy)[^0-9]{0,40}(\d+(?:[.,]\d+)?)\s*kcal",
        section,
    )
    if energy_match:
        value = _coerce_nutrition_number(energy_match.group(1))
        if value is not None:
            parsed["calories_kcal"] = value

    carbs_match = re.search(r"(?:weglowodany|carbohydrate|carbs)[^0-9]{0,30}(\d+(?:[.,]\d+)?)\s*g\b", section)
    if carbs_match:
        value = _coerce_nutrition_number(carbs_match.group(1))
        if value is not None:
            parsed["carbs_g"] = value

    protein_match = re.search(r"(?:bialko|protein)[^0-9]{0,30}(\d+(?:[.,]\d+)?)\s*g\b", section)
    if protein_match:
        value = _coerce_nutrition_number(protein_match.group(1))
        if value is not None:
            parsed["protein_g"] = value

    fat_match = re.search(r"(?:tluszcz\w*|fat)[^0-9]{0,30}(\d+(?:[.,]\d+)?)\s*g\b", section)
    if fat_match:
        value = _coerce_nutrition_number(fat_match.group(1))
        if value is not None:
            parsed["fat_g"] = value

    fiber_match = re.search(r"(?:blonnik|fiber|fibre)[^0-9]{0,30}(\d+(?:[.,]\d+)?)\s*g\b", section)
    if fiber_match:
        value = _coerce_nutrition_number(fiber_match.group(1))
        if value is not None:
            parsed["fiber_g"] = value

    return parsed


def convert_nutrition_per_100g_to_portion(per_100g: dict, portion_weight_g: Optional[float]) -> dict:
    if not per_100g or not portion_weight_g or portion_weight_g <= 0:
        return {}
    ratio = portion_weight_g / 100.0
    converted: dict = {}
    for key in ("calories_kcal", "protein_g", "carbs_g", "fat_g", "fiber_g"):
        value = _coerce_nutrition_number(per_100g.get(key))
        if value is None:
            continue
        converted[key] = round(value * ratio, 1)
    return converted


def estimate_nutrition_with_ai(
    *,
    title: str,
    ingredients: List[str],
    instructions: List[str],
    base_portions: int,
    portion_weight_g: Optional[float],
) -> Optional[dict]:
    if client is None:
        return None
    if not ingredients:
        return None

    portions = max(1, int(base_portions or 1))
    prompt = "\n".join(
        [
            "Zwróć WYŁĄCZNIE poprawny JSON.",
            "Jesteś dietetykiem klinicznym i analitykiem procesów kulinarnych.",
            "Oblicz SZACUNKOWE wartości odżywcze NA 1 PORCJĘ.",
            f"title: {title or ''}",
            f"portions: {portions}",
            f"portion_weight_g: {portion_weight_g if portion_weight_g else 'null'}",
            f"ingredients: {json.dumps(ingredients, ensure_ascii=False)}",
            f"instructions: {json.dumps(instructions, ensure_ascii=False)}",
            "",
            "Wymagany format:",
            "{",
            '  "protein_g": number,',
            '  "carbs_g": number,',
            '  "fat_g": number,',
            '  "fiber_g": number,',
            '  "glycemic_load": number,',
            '  "calories_kcal": number',
            "}",
            "",
            "Zasady analityczne:",
            "- Uwzględnij proces: redukcja/odparowanie, hydratacja, smażenie",
            "- Wszystkie wartości >= 0",
            "- liczby, nie stringi",
            "- zaokrąglij do 1 miejsca po przecinku",
        ]
    )

    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or "{}"
        parsed_raw = json.loads(raw)
        parsed = _parse_nutrition_payload(parsed_raw)
        if not parsed:
            logger.warning("Nutrition request returned invalid payload")
            return None
        return parsed
    except Exception as exc:
        logger.warning("Nutrition request failed: %s", str(exc))
        return None


def _estimate_glycemic_index(title: str, ingredients: List[str], instructions: List[str]) -> float:
    blob = _normalize_text(" ".join([title, " ".join(ingredients), " ".join(instructions)]))
    high_tokens = ("cukier", "maka pszenna", "maka", "bialy ryz", "syrop", "slodycz", "slodk")
    medium_tokens = ("pelnoziarn", "makaron", "sok", "kasz")
    low_tokens = ("straczk", "warzyw", "bialko", "tluszcz", "orzech", "migdal")

    if any(token in blob for token in high_tokens):
        return 72.0
    if any(token in blob for token in medium_tokens):
        return 62.0
    if any(token in blob for token in low_tokens):
        return 45.0
    return 55.0


def _estimate_glycemic_load_fallback(
    *,
    title: str,
    ingredients: List[str],
    instructions: List[str],
    carbs_g: Optional[float],
    fiber_g: Optional[float],
) -> Optional[float]:
    carbs = _coerce_nutrition_number(carbs_g)
    if carbs is None:
        return None
    fiber = _coerce_nutrition_number(fiber_g) or 0.0
    net_carbs = max(0.0, carbs - fiber)
    gi = _estimate_glycemic_index(title, ingredients, instructions)
    return round((gi * net_carbs) / 100.0, 1)


def _contains_low_confidence_terms(ingredients: List[str], instructions: List[str]) -> bool:
    text_blob = _normalize_text(" ".join(ingredients + instructions))
    return any(term in text_blob for term in LOW_CONFIDENCE_TERMS)


def _apply_nutrition_guardrails(
    nutrition: Optional[dict], portion_weight_g: Optional[float]
) -> Optional[dict]:
    if not nutrition:
        return None

    protein = _coerce_nutrition_number(nutrition.get("protein_g")) or 0.0
    carbs = _coerce_nutrition_number(nutrition.get("carbs_g")) or 0.0
    fat = _coerce_nutrition_number(nutrition.get("fat_g")) or 0.0
    fiber = _coerce_nutrition_number(nutrition.get("fiber_g")) or 0.0
    calories = _coerce_nutrition_number(nutrition.get("calories_kcal"))
    glycemic_load = _coerce_nutrition_number(nutrition.get("glycemic_load"))

    if fiber > carbs:
        fiber = carbs
    net_carbs = max(0.0, carbs - fiber)
    if glycemic_load is not None and net_carbs >= 0 and glycemic_load > net_carbs:
        glycemic_load = round(net_carbs, 1)
    if glycemic_load is not None and glycemic_load > GL_MAX_DISPLAY_VALUE:
        glycemic_load = round(GL_MAX_DISPLAY_VALUE, 1)

    # Guardrail: sum of macros cannot exceed portion mass by a meaningful margin.
    if portion_weight_g and portion_weight_g > 0:
        macro_mass = protein + carbs + fat + fiber
        if macro_mass > portion_weight_g * 1.05:
            return None

    # Guardrail: Atwater consistency when calories and fat are available.
    if calories is not None and fat > 0:
        atwater = (protein * 4.0) + (carbs * 4.0) + (fat * 9.0)
        if atwater > 0:
            rel_diff = abs(calories - atwater) / atwater
            if rel_diff > 0.55:
                return None

    return {
        "protein_g": round(protein, 1),
        "carbs_g": round(carbs, 1),
        "fat_g": round(fat, 1),
        "fiber_g": round(fiber, 1),
        "glycemic_load": round(glycemic_load, 1) if glycemic_load is not None else None,
        "calories_kcal": calories,
    }


def _compute_nutrition_confidence_score(
    *,
    nutrition_source: Optional[str],
    ingredients: List[str],
    instructions: List[str],
    portion_weight_g: Optional[float],
) -> Optional[float]:
    if not nutrition_source:
        return None
    base_score = 35.0
    if nutrition_source == "page_100g":
        base_score = 100.0
    elif nutrition_source == "mixed":
        base_score = 70.0
    elif nutrition_source == "ai":
        base_score = 35.0

    if _contains_low_confidence_terms(ingredients, instructions):
        base_score -= 30.0
    if not portion_weight_g or portion_weight_g <= 0:
        base_score -= 10.0

    return round(max(5.0, min(100.0, base_score)), 1)


def _rebalance_portions_for_dense_snack_if_needed(
    *,
    context: YieldContext,
    title: str,
    ingredients: List[str],
    instructions: List[str],
    nutrition_per_portion: Optional[dict],
) -> bool:
    calories = _coerce_nutrition_number((nutrition_per_portion or {}).get("calories_kcal"))
    if calories is None:
        return False

    recipe_type = _detect_recipe_type(title, ingredients, instructions)
    snack_like = _is_snack_like_recipe(title, ingredients, instructions) or _is_sweet_snack_recipe(
        title, ingredients, instructions
    )
    if not (recipe_type == "dessert" or snack_like):
        return False
    if calories <= SNACK_MAX_KCAL_PER_PORTION:
        return False

    total_weight_g = context.total_weight_g
    if total_weight_g is None or total_weight_g <= 0:
        return False

    current_portions = max(1, int(context.base_portions or 1))
    standard_portion_g = _get_snack_standard_portion_weight_g(title, ingredients, instructions)
    target_portions = max(current_portions, round(total_weight_g / standard_portion_g))
    if target_portions <= current_portions:
        return False

    context.base_portions = target_portions
    context.portion_weight_g = round(total_weight_g / target_portions, 1)
    context.mode = "total_weight_only"
    context.assumption_reason = (
        f"Auto-correction: {calories:.0f} kcal/portion too high, "
        f"set ~{standard_portion_g:.0f} g per portion ({target_portions} portions)"
    )
    return True


def _rebalance_portions_for_meal_if_needed(
    *,
    context: YieldContext,
    title: str,
    ingredients: List[str],
    instructions: List[str],
    nutrition_per_portion: Optional[dict],
) -> bool:
    recipe_type = _detect_recipe_type(title, ingredients, instructions)
    if recipe_type not in ("soup", "main"):
        return False

    total_weight_g = context.total_weight_g
    if total_weight_g is None or total_weight_g <= 0:
        return False

    current_portions = max(1, int(context.base_portions or 1))
    current_portion_weight = total_weight_g / current_portions
    calories = _coerce_nutrition_number((nutrition_per_portion or {}).get("calories_kcal"))

    standard_portion_g = DEFAULT_PORTION_WEIGHT_BY_TYPE_G.get(recipe_type, DEFAULT_PORTION_WEIGHT_BY_TYPE_G["main"])
    oversized = current_portion_weight > (standard_portion_g * 1.6)
    undersized = current_portions > 1 and current_portion_weight < MEAL_MIN_PORTION_WEIGHT_G
    too_many_calories = calories is not None and calories > MEAL_MAX_KCAL_PER_PORTION

    if not (oversized or undersized or too_many_calories):
        return False

    target_portions = max(1, round(total_weight_g / standard_portion_g))
    if target_portions == current_portions:
        return False

    context.base_portions = target_portions
    context.portion_weight_g = round(total_weight_g / target_portions, 1)
    context.mode = "total_weight_only"
    context.assumption_reason = (
        f"Auto-correction meal: set ~{standard_portion_g:.0f} g per portion ({target_portions} portions)"
    )
    return True


def merge_nutrition_sources(
    page_nutrition_per_portion: dict,
    ai_nutrition_per_portion: Optional[dict],
) -> tuple[Optional[dict], Optional[str]]:
    keys = ("protein_g", "carbs_g", "fat_g", "fiber_g", "glycemic_load", "calories_kcal")
    merged: dict = {}
    used_page = False
    used_ai = False

    for key in keys:
        page_value = _coerce_nutrition_number(page_nutrition_per_portion.get(key))
        if page_value is not None:
            merged[key] = page_value
            used_page = True
            continue
        ai_value = _coerce_nutrition_number((ai_nutrition_per_portion or {}).get(key))
        if ai_value is not None:
            merged[key] = ai_value
            used_ai = True

    if not merged:
        return None, None

    if used_page and used_ai:
        source = "mixed"
    elif used_page:
        source = "page_100g"
    elif used_ai:
        source = "ai"
    else:
        source = None

    return merged, source


def apply_nutrition_to_recipe(
    recipe: RecipeDB,
    nutrition: Optional[dict],
    nutrition_source: Optional[str],
    nutrition_confidence_score: Optional[float],
) -> None:
    recipe.nutrition_protein_g = _coerce_nutrition_number((nutrition or {}).get("protein_g"))
    recipe.nutrition_carbs_g = _coerce_nutrition_number((nutrition or {}).get("carbs_g"))
    recipe.nutrition_fat_g = _coerce_nutrition_number((nutrition or {}).get("fat_g"))
    recipe.nutrition_fiber_g = _coerce_nutrition_number((nutrition or {}).get("fiber_g"))
    recipe.nutrition_glycemic_load = _coerce_nutrition_number((nutrition or {}).get("glycemic_load"))
    recipe.nutrition_calories_kcal = _coerce_nutrition_number((nutrition or {}).get("calories_kcal"))
    recipe.nutrition_source = nutrition_source
    recipe.nutrition_confidence_score = _coerce_nutrition_number(nutrition_confidence_score)


def estimate_recipe_nutrition(
    title: str,
    ingredients: List[str],
    instructions: List[str],
    base_portions: int,
    page_nutrition_per_100g: Optional[dict] = None,
    portion_weight_g: Optional[float] = None,
) -> tuple[Optional[dict], Optional[str], Optional[float]]:
    page_nutrition_per_portion = convert_nutrition_per_100g_to_portion(
        page_nutrition_per_100g or {}, portion_weight_g
    )
    required_keys = ("protein_g", "carbs_g", "fat_g", "fiber_g", "glycemic_load", "calories_kcal")
    needs_ai = any(key not in page_nutrition_per_portion for key in required_keys)

    ai_nutrition = None
    if needs_ai:
        ai_nutrition = estimate_nutrition_with_ai(
            title=title,
            ingredients=ingredients,
            instructions=instructions,
            base_portions=base_portions,
            portion_weight_g=portion_weight_g,
        )

    merged_nutrition, nutrition_source = merge_nutrition_sources(page_nutrition_per_portion, ai_nutrition)
    if not merged_nutrition:
        return None, None, None

    if _coerce_nutrition_number(merged_nutrition.get("glycemic_load")) is None:
        fallback_gl = _estimate_glycemic_load_fallback(
            title=title,
            ingredients=ingredients,
            instructions=instructions,
            carbs_g=merged_nutrition.get("carbs_g"),
            fiber_g=merged_nutrition.get("fiber_g"),
        )
        if fallback_gl is not None:
            merged_nutrition["glycemic_load"] = fallback_gl
            if nutrition_source == "page_100g":
                nutrition_source = "mixed"
            elif nutrition_source is None:
                nutrition_source = "mixed"

    guarded_nutrition = _apply_nutrition_guardrails(merged_nutrition, portion_weight_g)
    if not guarded_nutrition:
        return None, None, None

    confidence_score = _compute_nutrition_confidence_score(
        nutrition_source=nutrition_source,
        ingredients=ingredients,
        instructions=instructions,
        portion_weight_g=portion_weight_g,
    )
    return guarded_nutrition, nutrition_source, confidence_score


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
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")

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
        raise HTTPException(status_code=502, detail="Nie udało się połączyć z Google")

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
        raise HTTPException(status_code=502, detail="Nie udało się pobrać kalendarzy")
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
        raise HTTPException(status_code=400, detail="Nie znaleziono kalendarza lub brak uprawnien")
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
        raise HTTPException(status_code=400, detail="Brak wydarzen do synchronizacji")

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
            raise HTTPException(status_code=400, detail=f"Nieprawidlowa data: {event.date}")

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
            raise HTTPException(status_code=502, detail="Nie udało się pobrać wydarzeń z Google")
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

        image_url = scraper.image()
        instructions_raw = scraper.instructions()
        instructions_list = _normalize_instruction_list(instructions_raw)
        instructions_text = "\n".join(instructions_list).strip()
        if not instructions_text:
            if isinstance(instructions_raw, str):
                instructions_text = instructions_raw.strip()
            elif isinstance(instructions_raw, list):
                instructions_text = "\n".join(
                    str(item).strip() for item in instructions_raw if str(item).strip()
                )
        yields_text = extract_yield_text_from_page(scraper=scraper, html_content=html_content)
        yield_context = parse_yield_context(
            yield_text=yields_text,
            title=title,
            ingredients=ingredients,
            instructions=instructions_list,
        )
        yield_context = resolve_yield_context_weights(
            context=yield_context,
            title=title,
            ingredients=ingredients,
            instructions=instructions_list,
        )

        base_portions = max(1, int(yield_context.base_portions or 1))
        servings_unit = yield_context.servings_unit
        page_nutrition_per_100g = extract_nutrition_per_100g_from_page(
            scraper=scraper,
            html_content=html_content,
        )
        nutrition_estimate, nutrition_source, nutrition_confidence_score = estimate_recipe_nutrition(
            title=title,
            ingredients=ingredients,
            instructions=instructions_list,
            base_portions=base_portions,
            page_nutrition_per_100g=page_nutrition_per_100g,
            portion_weight_g=yield_context.portion_weight_g,
        )
        rebalanced_portions = False
        if _rebalance_portions_for_dense_snack_if_needed(
            context=yield_context,
            title=title,
            ingredients=ingredients,
            instructions=instructions_list,
            nutrition_per_portion=nutrition_estimate,
        ):
            rebalanced_portions = True
        if _rebalance_portions_for_meal_if_needed(
            context=yield_context,
            title=title,
            ingredients=ingredients,
            instructions=instructions_list,
            nutrition_per_portion=nutrition_estimate,
        ):
            rebalanced_portions = True
        if rebalanced_portions:
            base_portions = max(1, int(yield_context.base_portions or base_portions))
            nutrition_estimate, nutrition_source, nutrition_confidence_score = estimate_recipe_nutrition(
                title=title,
                ingredients=ingredients,
                instructions=instructions_list,
                base_portions=base_portions,
                page_nutrition_per_100g=page_nutrition_per_100g,
                portion_weight_g=yield_context.portion_weight_g,
            )

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
            recipe.instructions = instructions_text
            recipe.base_portions = base_portions
            recipe.servings_unit = servings_unit
            recipe.yield_display_label = yield_context.yield_display_label
            recipe.yield_assumption_reason = yield_context.assumption_reason
            recipe.total_weight_g = yield_context.total_weight_g
            recipe.portion_weight_g = yield_context.portion_weight_g
            recipe.piece_weight_g = yield_context.piece_weight_g
            recipe.pan_diameter_min_cm = yield_context.pan_diameter_min_cm
            recipe.pan_diameter_max_cm = yield_context.pan_diameter_max_cm
            apply_nutrition_to_recipe(
                recipe,
                nutrition_estimate,
                nutrition_source,
                nutrition_confidence_score,
            )
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
                instructions=instructions_text,
                base_portions=base_portions,
                servings_unit=servings_unit,
                yield_display_label=yield_context.yield_display_label,
                yield_assumption_reason=yield_context.assumption_reason,
                total_weight_g=yield_context.total_weight_g,
                portion_weight_g=yield_context.portion_weight_g,
                piece_weight_g=yield_context.piece_weight_g,
                pan_diameter_min_cm=yield_context.pan_diameter_min_cm,
                pan_diameter_max_cm=yield_context.pan_diameter_max_cm,
                nutrition_protein_g=_coerce_nutrition_number((nutrition_estimate or {}).get("protein_g")),
                nutrition_carbs_g=_coerce_nutrition_number((nutrition_estimate or {}).get("carbs_g")),
                nutrition_fat_g=_coerce_nutrition_number((nutrition_estimate or {}).get("fat_g")),
                nutrition_fiber_g=_coerce_nutrition_number((nutrition_estimate or {}).get("fiber_g")),
                nutrition_glycemic_load=_coerce_nutrition_number((nutrition_estimate or {}).get("glycemic_load")),
                nutrition_calories_kcal=_coerce_nutrition_number((nutrition_estimate or {}).get("calories_kcal")),
                nutrition_source=nutrition_source,
                nutrition_confidence_score=nutrition_confidence_score,
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


SHOPPING_CATEGORIES_ORDER = [
    "Warzywa i owoce",
    "Mieso i ryby",
    "Nabial i jaja",
    "Pieczywo i makarony",
    "Oleje i tluszcze",
    "Przyprawy i dodatki",
    "Produkty sypkie",
    "Inne",
]

SHOPPING_PIECE_UNITS = {
    "szt",
    "zabek",
    "glowka",
    "puszka",
    "paczka",
    "opakowanie",
    "plasterek",
    "kromka",
}

SHOPPING_UNIT_MAP = {
    "kg": "kg",
    "g": "g",
    "l": "l",
    "ml": "ml",
    "szt": "szt",
    "sztuk": "szt",
    "sztuki": "szt",
    "lyzka": "lyzka",
    "lyzki": "lyzka",
    "lyzek": "lyzka",
    "lyzeczka": "lyzeczka",
    "lyzeczki": "lyzeczka",
    "lyzeczek": "lyzeczka",
    "szklanka": "szklanka",
    "szklanki": "szklanka",
    "opakowanie": "opakowanie",
    "opakowania": "opakowanie",
    "zabek": "zabek",
    "zabki": "zabek",
    "glowka": "glowka",
    "glowki": "glowka",
    "puszka": "puszka",
    "puszki": "puszka",
    "paczka": "paczka",
    "paczki": "paczka",
    "plasterek": "plasterek",
    "plasterki": "plasterek",
    "kromka": "kromka",
    "kromki": "kromka",
}

SHOPPING_CATEGORY_CANONICAL_MAP = {
    "warzywa i owoce": "Warzywa i owoce",
    "warzywa": "Warzywa i owoce",
    "owoce": "Warzywa i owoce",
    "mieso i ryby": "Mieso i ryby",
    "mieso": "Mieso i ryby",
    "ryby": "Mieso i ryby",
    "nabial i jaja": "Nabial i jaja",
    "nabial": "Nabial i jaja",
    "jaja": "Nabial i jaja",
    "pieczywo i makarony": "Pieczywo i makarony",
    "pieczywo": "Pieczywo i makarony",
    "makarony": "Pieczywo i makarony",
    "oleje i tluszcze": "Oleje i tluszcze",
    "oleje": "Oleje i tluszcze",
    "tluszcze": "Oleje i tluszcze",
    "przyprawy i dodatki": "Przyprawy i dodatki",
    "przyprawy": "Przyprawy i dodatki",
    "dodatki": "Przyprawy i dodatki",
    "produkty sypkie": "Produkty sypkie",
    "sypkie": "Produkty sypkie",
    "inne": "Inne",
}


def _format_float_compact(value: float, precision: int = 1) -> str:
    rounded = round(value, precision)
    if abs(rounded - int(rounded)) < 1e-9:
        return str(int(rounded))
    return f"{rounded:.{precision}f}".rstrip("0").rstrip(".")


def _parse_quantity_token(token: str) -> Optional[float]:
    if not token:
        return None
    token = token.strip()
    fraction_match = re.match(r"^(\d+)\s*/\s*(\d+)$", token)
    if fraction_match:
        denominator = int(fraction_match.group(2))
        if denominator == 0:
            return None
        return int(fraction_match.group(1)) / denominator
    return _parse_number_token(token)


def _normalize_shopping_unit(raw_unit: Optional[str]) -> Optional[str]:
    if not raw_unit:
        return None
    normalized = _normalize_text(raw_unit)
    return SHOPPING_UNIT_MAP.get(normalized)


def _normalize_shopping_name(raw_name: str) -> str:
    cleaned = (raw_name or "").strip(" ,.-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _should_default_to_piece_unit(norm_name: str) -> bool:
    piece_keywords = (
        "cebul",
        "jaj",
        "papryk",
        "pomidor",
        "ziemniak",
        "marchew",
        "ogorek",
        "cytryn",
        "limonk",
        "banan",
        "jablk",
        "czosnek",
    )
    return any(keyword in norm_name for keyword in piece_keywords)


def _parse_shopping_ingredient_line(ingredient: str, factor: float) -> Optional[dict]:
    line = _normalize_shopping_name(ingredient)
    if not line:
        return None

    match = re.match(
        r"^\s*(\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)?)(?:\s*[-–]\s*(\d+(?:[.,]\d+)?))?\s*(kg|g|ml|l|szt(?:uk(?:i)?)?|lyzki?|lyzek|lyzeczki?|lyzeczek|szklanki?|opakowani(?:e|a)|zabki?|glowki?|puszki?|paczki?|plasterki?|kromki?)?\b[\s,.-]*(.*)$",
        line,
        flags=re.IGNORECASE,
    )
    if not match:
        return {"name": line, "quantity": None, "unit": None}

    primary_raw = match.group(1)
    range_max_raw = match.group(2)
    unit_raw = match.group(3)
    name_raw = match.group(4) or line

    quantity = _parse_quantity_token(primary_raw) if primary_raw else None
    if range_max_raw:
        range_max = _parse_quantity_token(range_max_raw)
        if range_max is not None and range_max > 0:
            quantity = range_max

    if quantity is not None:
        quantity = max(0.0, quantity * max(0.0, factor))

    unit = _normalize_shopping_unit(unit_raw)
    name = _normalize_shopping_name(name_raw)
    if not name:
        name = line

    if quantity is not None and unit is None and _should_default_to_piece_unit(_normalize_text(name)):
        unit = "szt"

    return {"name": name, "quantity": quantity, "unit": unit}


def _format_shopping_amount(quantity: Optional[float], unit: Optional[str]) -> str:
    if quantity is None or quantity <= 0.0:
        return ""

    if unit in SHOPPING_PIECE_UNITS:
        rounded = int(quantity) if float(quantity).is_integer() else int(quantity) + 1
        rounded = max(1, rounded)
        return f"{rounded} {unit}" if unit else str(rounded)

    if unit in {"g", "ml"}:
        if quantity >= 10:
            value = str(int(round(quantity)))
        else:
            value = _format_float_compact(quantity, precision=1)
    elif unit in {"kg", "l"}:
        value = _format_float_compact(quantity, precision=2)
    else:
        value = _format_float_compact(quantity, precision=1)
    return f"{value} {unit}".strip() if unit else value


def _categorize_shopping_item(name: str) -> str:
    normalized = _normalize_text(name)
    category_rules = {
        "Warzywa i owoce": (
            "cebula",
            "cebul",
            "czosnek",
            "marchew",
            "ziemniak",
            "pomidor",
            "papryk",
            "ogorek",
            "cytryn",
            "limonk",
            "pietruszk",
            "szpinak",
            "brokul",
            "kalafior",
            "jablk",
            "banan",
            "owoc",
            "warzyw",
        ),
        "Mieso i ryby": (
            "kurczak",
            "wolowin",
            "wieprz",
            "kielbas",
            "boczek",
            "szynk",
            "ryba",
            "losos",
            "tunczyk",
            "mieso",
            "indyk",
        ),
        "Nabial i jaja": (
            "mleko",
            "jogurt",
            "smietan",
            "ser",
            "serek",
            "mozzarella",
            "feta",
            "mascarpone",
            "twarog",
            "jaj",
            "maslo",
        ),
        "Pieczywo i makarony": (
            "makaron",
            "chleb",
            "bulka",
            "pieczywo",
            "tortilla",
            "kasza",
            "ryz",
            "platki",
            "kuskus",
            "gnocchi",
        ),
        "Oleje i tluszcze": (
            "olej",
            "oliwa",
            "tluszcz",
            "smalec",
            "maslo klarowane",
            "ghee",
        ),
        "Przyprawy i dodatki": (
            "sol",
            "pieprz",
            "papryka",
            "kurkuma",
            "curry",
            "przypraw",
            "ziola",
            "ocet",
            "sos",
            "musztard",
            "ketchup",
        ),
        "Produkty sypkie": (
            "maka",
            "cukier",
            "kasza",
            "ryz",
            "platki",
            "kakao",
            "proszek",
            "soda",
            "drozdze",
            "fasol",
            "soczewic",
            "ciecierzyc",
        ),
    }
    for category, keywords in category_rules.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return "Inne"


def _canonicalize_shopping_category(raw_category: str) -> Optional[str]:
    normalized = _normalize_text(raw_category).strip()
    if not normalized:
        return None
    return SHOPPING_CATEGORY_CANONICAL_MAP.get(normalized)


def _validate_ai_shopping_list_payload(payload: Any) -> Optional[List[dict]]:
    if not isinstance(payload, dict):
        return None
    raw_shopping_list = payload.get("shopping_list")
    if not isinstance(raw_shopping_list, list):
        return None

    validated_map: dict[str, List[str]] = {}
    for category_entry in raw_shopping_list:
        if not isinstance(category_entry, dict):
            continue
        category_name = str(category_entry.get("category") or "").strip()
        canonical_category = _canonicalize_shopping_category(category_name)
        raw_items = category_entry.get("items")
        if not isinstance(raw_items, list):
            continue
        items: List[str] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, str):
                continue
            item = raw_item.strip()
            if item:
                items.append(item)
        if items:
            for item in items:
                target_category = canonical_category
                if target_category in (None, "Inne"):
                    target_category = _categorize_shopping_item(item)
                validated_map.setdefault(target_category, []).append(item)

    if not validated_map:
        return None

    validated: List[dict] = []
    for category in SHOPPING_CATEGORIES_ORDER:
        items = validated_map.get(category)
        if not items:
            continue
        validated.append({"category": category, "items": items})
    return validated or None


def _extract_json_object_from_text(text: str) -> Optional[dict]:
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    end = None
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end is None:
        return None

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def _extract_failed_generation_snippet(error_message: str) -> Optional[str]:
    if not error_message or "failed_generation" not in error_message:
        return None
    match = re.search(r'"failed_generation"\s*:\s*"([^"]+)"', error_message)
    if not match:
        return "failed_generation present"
    snippet = match.group(1).replace('\\"', '"')
    return snippet[:500]


def _build_shopping_prompt(compiled_data: List[dict], compact: bool = False) -> str:
    compiled_json = json.dumps(compiled_data, ensure_ascii=False)
    base_lines = [
        "You are KitchenOS shopping list assistant.",
        "Return valid JSON object only.",
        'Expected shape: {"shopping_list":[{"category":"...","items":["..."]}]}',
        "Never add products that are not in input.",
        "Merge identical ingredients and scale by factor.",
        "Round up piece counts.",
    ]
    if compact:
        base_lines = [
            "Return JSON only.",
            'Use shape {"shopping_list":[{"category":"...","items":["..."]}]}',
            "Use only ingredients from input.",
            "Do not include markdown.",
        ]
    return "\n".join(base_lines + ["INPUT:", compiled_json])


def _generate_shopping_list_with_ai(compiled_data: List[dict]) -> tuple[Optional[List[dict]], Optional[str]]:
    if client is None:
        return None, "AI niedostepne, wlaczono tryb awaryjny."

    attempts = [
        {"compact": False, "temperature": 0.0, "response_format": True},
        {"compact": True, "temperature": 0.0, "response_format": True},
        {"compact": True, "temperature": 0.0, "response_format": False},
    ]

    for attempt_number, attempt in enumerate(attempts, start=1):
        prompt = _build_shopping_prompt(compiled_data, compact=attempt["compact"])
        try:
            completion_kwargs = {
                "messages": [{"role": "user", "content": prompt}],
                "model": GROQ_MODEL,
                "temperature": attempt["temperature"],
            }
            if attempt["response_format"]:
                completion_kwargs["response_format"] = {"type": "json_object"}

            chat_completion = client.chat.completions.create(**completion_kwargs)
            content = (chat_completion.choices[0].message.content or "").strip()
            if attempt["response_format"]:
                parsed = json.loads(content)
            else:
                parsed = _extract_json_object_from_text(content)
                if parsed is None:
                    raise ValueError("No JSON object in AI response")

            validated = _validate_ai_shopping_list_payload(parsed)
            if validated:
                return validated, None

            logger.warning("Shopping AI attempt %s returned invalid payload shape", attempt_number)
        except Exception as exc:
            raw_error = str(exc)
            failed_generation = _extract_failed_generation_snippet(raw_error)
            if failed_generation:
                logger.warning(
                    "Shopping AI attempt %s failed_generation: %s",
                    attempt_number,
                    failed_generation,
                )
            else:
                logger.warning("Shopping AI attempt %s failed: %s", attempt_number, raw_error[:500])

    return None, "Tryb awaryjny: AI nie zwrocilo poprawnego JSON."


def _generate_shopping_list_fallback(compiled_data: List[dict]) -> List[dict]:
    aggregated: dict[tuple[str, str], dict] = {}

    for recipe_entry in compiled_data:
        factor = _coerce_nutrition_number(recipe_entry.get("factor")) or 1.0
        ingredients = recipe_entry.get("ingredients") or []
        if not isinstance(ingredients, list):
            continue

        for ingredient in ingredients:
            if not isinstance(ingredient, str):
                continue
            parsed = _parse_shopping_ingredient_line(ingredient, factor)
            if not parsed:
                continue

            name = _normalize_shopping_name(parsed.get("name") or "")
            if not name:
                continue
            quantity = _coerce_nutrition_number(parsed.get("quantity"))
            unit = parsed.get("unit") or ""

            if quantity is not None and quantity < 0.05:
                continue

            key = (_normalize_text(name), unit)
            existing = aggregated.get(key)
            if existing is None:
                aggregated[key] = {"name": name, "quantity": quantity, "unit": unit}
                continue

            existing_qty = _coerce_nutrition_number(existing.get("quantity"))
            if quantity is None or existing_qty is None:
                existing["quantity"] = existing_qty if existing_qty is not None else quantity
            else:
                existing["quantity"] = existing_qty + quantity

    if not aggregated:
        return []

    categorized: dict[str, List[str]] = {category: [] for category in SHOPPING_CATEGORIES_ORDER}
    for entry in sorted(aggregated.values(), key=lambda item: _normalize_text(item["name"])):
        amount = _format_shopping_amount(
            _coerce_nutrition_number(entry.get("quantity")),
            entry.get("unit") or None,
        )
        label = entry["name"] if not amount else f"{entry['name']} ({amount})"
        category = _categorize_shopping_item(entry["name"])
        categorized.setdefault(category, []).append(label)

    shopping_list: List[dict] = []
    for category in SHOPPING_CATEGORIES_ORDER:
        items = categorized.get(category) or []
        if items:
            shopping_list.append({"category": category, "items": items})

    if shopping_list:
        return shopping_list
    return []


def _filter_out_water_items(shopping_list: List[dict]) -> List[dict]:
    filtered_list: List[dict] = []
    removed_count = 0

    for entry in shopping_list:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "").strip()
        raw_items = entry.get("items")
        if not category or not isinstance(raw_items, list):
            continue

        next_items: List[str] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, str):
                continue
            item = raw_item.strip()
            if not item:
                continue
            normalized = _normalize_text(item)
            if re.search(r"\bwod\w*\b", normalized):
                removed_count += 1
                continue
            next_items.append(item)

        if next_items:
            filtered_list.append({"category": category, "items": next_items})

    if removed_count:
        logger.info("Filtered %s water item(s) from shopping list", removed_count)
    return filtered_list


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
            requested_portions = max(1, min(PLANNER_MAX_PORTIONS, int(item.portions)))
            base_portions = max(1, int(recipe.base_portions or 1))
            factor = requested_portions / base_portions
            compiled_data.append(
                {
                    "title": recipe.title,
                    "factor": round(factor, 3),
                    "base_portions": base_portions,
                    "requested_portions": requested_portions,
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

    warning: Optional[str] = None
    generation_mode: Literal["ai", "fallback"] = "ai"
    shopping_list_data: Optional[List[dict]] = None

    try:
        shopping_list_data, warning = _generate_shopping_list_with_ai(compiled_data)
    except Exception as e:
        logger.error(f"Unexpected AI shopping generator error: {str(e)}", exc_info=True)
        warning = "Tryb awaryjny: nie udalo sie uruchomic AI."

    if not shopping_list_data:
        generation_mode = "fallback"
        shopping_list_data = _generate_shopping_list_fallback(compiled_data)
        if not warning:
            warning = "Lista wygenerowana bez AI. Sprawdz ilosci."

    shopping_list_data = _filter_out_water_items(shopping_list_data)

    response = ShoppingListResponse(
        shopping_list=shopping_list_data,
        total_recipes=len(compiled_data),
        generated_at=datetime.datetime.utcnow(),
        generation_mode=generation_mode,
        warning=warning if generation_mode == "fallback" else None,
    )

    logger.info(
        "Generated shopping list with %s categories (mode=%s)",
        len(response.shopping_list),
        generation_mode,
    )
    return response


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


# --- ENDPOINTY PLANERA (PRZENIESIONE NA GÓRĘ) ---


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
            model=GROQ_MODEL,
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        parsed_data = json.loads(chat_completion.choices[0].message.content or "{}")
        raw_ingredients = parsed_data.get("ingredients") or []
        if isinstance(raw_ingredients, list):
            parsed_ingredients = [str(item).strip() for item in raw_ingredients if str(item).strip()]
        else:
            parsed_ingredients = []

        instructions_list = _normalize_instruction_list(parsed_data.get("instructions"))
        instructions_text = "\n".join(instructions_list).strip()
        parsed_title = (parsed_data.get("title") or "Przepis Własny").strip()
        yield_label = extract_yield_text_from_text_blob(content)
        yield_context = parse_yield_context(
            yield_text=yield_label,
            title=parsed_title,
            ingredients=parsed_ingredients,
            instructions=instructions_list,
        )
        if yield_context.mode == "unknown":
            try:
                fallback_portions = int(parsed_data.get("portions") or 1)
            except (TypeError, ValueError):
                fallback_portions = 1
            yield_context.base_portions = max(1, fallback_portions)
        yield_context = resolve_yield_context_weights(
            context=yield_context,
            title=parsed_title,
            ingredients=parsed_ingredients,
            instructions=instructions_list,
        )
        base_portions = max(1, int(yield_context.base_portions or 1))
        servings_unit = yield_context.servings_unit
        nutrition_estimate, nutrition_source, nutrition_confidence_score = estimate_recipe_nutrition(
            title=parsed_title,
            ingredients=parsed_ingredients,
            instructions=instructions_list,
            base_portions=base_portions,
            page_nutrition_per_100g=None,
            portion_weight_g=yield_context.portion_weight_g,
        )
        rebalanced_portions = False
        if _rebalance_portions_for_dense_snack_if_needed(
            context=yield_context,
            title=parsed_title,
            ingredients=parsed_ingredients,
            instructions=instructions_list,
            nutrition_per_portion=nutrition_estimate,
        ):
            rebalanced_portions = True
        if _rebalance_portions_for_meal_if_needed(
            context=yield_context,
            title=parsed_title,
            ingredients=parsed_ingredients,
            instructions=instructions_list,
            nutrition_per_portion=nutrition_estimate,
        ):
            rebalanced_portions = True
        if rebalanced_portions:
            base_portions = max(1, int(yield_context.base_portions or base_portions))
            nutrition_estimate, nutrition_source, nutrition_confidence_score = estimate_recipe_nutrition(
                title=parsed_title,
                ingredients=parsed_ingredients,
                instructions=instructions_list,
                base_portions=base_portions,
                page_nutrition_per_100g=None,
                portion_weight_g=yield_context.portion_weight_g,
            )

        # Ikona domyślna
        generic_icon = "https://cdn-icons-png.flaticon.com/512/3081/3081557.png"

        # --- KLUCZOWE: unikalny URL, bo w bazie url ma unique=True ---
        custom_url = f"custom:{uuid.uuid4()}"

        recipe = RecipeDB(
            owner_id=current_user.id,
            title=parsed_title,
            url=custom_url,
            image_url=generic_icon,
            ingredients=parsed_ingredients,
            instructions=instructions_text,
            base_portions=base_portions,
            servings_unit=servings_unit,
            yield_display_label=yield_context.yield_display_label,
            yield_assumption_reason=yield_context.assumption_reason,
            total_weight_g=yield_context.total_weight_g,
            portion_weight_g=yield_context.portion_weight_g,
            piece_weight_g=yield_context.piece_weight_g,
            pan_diameter_min_cm=yield_context.pan_diameter_min_cm,
            pan_diameter_max_cm=yield_context.pan_diameter_max_cm,
            nutrition_protein_g=_coerce_nutrition_number((nutrition_estimate or {}).get("protein_g")),
            nutrition_carbs_g=_coerce_nutrition_number((nutrition_estimate or {}).get("carbs_g")),
            nutrition_fat_g=_coerce_nutrition_number((nutrition_estimate or {}).get("fat_g")),
            nutrition_fiber_g=_coerce_nutrition_number((nutrition_estimate or {}).get("fiber_g")),
            nutrition_glycemic_load=_coerce_nutrition_number((nutrition_estimate or {}).get("glycemic_load")),
            nutrition_calories_kcal=_coerce_nutrition_number((nutrition_estimate or {}).get("calories_kcal")),
            nutrition_source=nutrition_source,
            nutrition_confidence_score=nutrition_confidence_score,
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


def _looks_like_instruction_noise(norm_line: str) -> bool:
    patterns = (
        r"^(czas przygotowania|czas pieczenia|czas gotowania|czas smazenia)\b",
        r"^(liczba porcji|porcje|dla osob)\b",
        r"^(w\s*100\s*g|wartosc energetyczna|wartosc odzywcza)\b",
        r"^(weglowodany|bialko|tluszcz\w*|blonnik|dieta)\b",
        r"^-?\s*w tym cukry\b",
    )
    return any(re.search(pattern, norm_line) for pattern in patterns)


def _normalize_instruction_entries(entries: List[str]) -> List[str]:
    prepared: List[str] = []
    for item in entries:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if not text:
            continue
        text = re.sub(r"^(?:krok\s*\d+[:.)-]*\s*|\d+[.)-]\s*|[-*•]\s*)", "", text, flags=re.IGNORECASE).strip()
        text = text.strip(" -:;")
        if not text:
            continue
        if _looks_like_instruction_noise(_normalize_text(text)):
            continue
        prepared.append(text)

    if not prepared:
        return []

    merged: List[str] = []
    for line in prepared:
        if not merged:
            merged.append(line)
            continue

        prev = merged[-1]
        prev_words = len(prev.split())
        line_words = len(line.split())
        prev_ends_sentence = bool(re.search(r"[.!?]$", prev))
        line_starts_sentence = bool(re.match(r"^[A-ZĄĆĘŁŃÓŚŹŻ]", line))

        should_merge = (
            line_words <= 4
            or len(line) < 24
            or prev_words <= 2
            or len(prev) < 18
        ) and not (prev_ends_sentence and line_starts_sentence)

        if should_merge:
            merged[-1] = re.sub(r"\s+", " ", f"{prev} {line}").strip()
        else:
            merged.append(line)

    # Remove consecutive duplicates that may appear after merging.
    deduped: List[str] = []
    for line in merged:
        if not deduped or _normalize_text(deduped[-1]) != _normalize_text(line):
            deduped.append(line)
    return deduped


def _normalize_instruction_list(raw: Any) -> List[str]:
    entries: List[str] = []
    if isinstance(raw, list):
        for item in raw:
            text = str(item or "").strip()
            if not text:
                continue
            entries.extend([line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()])
        return _normalize_instruction_entries(entries)
    if isinstance(raw, str):
        entries = [line.strip() for line in re.split(r"[\r\n]+", raw) if line.strip()]
        return _normalize_instruction_entries(entries)
    return []


def _build_inspire_response(payload: dict, user_ingredients: List[str]) -> InspireRecipeResponse:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="AI zwróciło nieprawidłowe dane")

    title = str(payload.get("title") or "Inspiracja z lodówki").strip()
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
        raise HTTPException(status_code=502, detail="AI zwróciło niekompletny przepis")

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
        raise HTTPException(status_code=400, detail="Lista składników nie może być pusta")

    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI jest niedostępne. Skonfiguruj GROQ_API_KEY.",
        )

    prompt = f"""
Role: Jesteś kreatywnym Szefem Kuchni i ekspertem Zero Waste współpracującym z systemem KitchenOS.
Task: Na podstawie listy składników podanych przez użytkownika, zaproponuj JEDEN konkretny, smaczny i realistyczny przepis.

ZASADY:
1. Składniki: Maksymalnie wykorzystaj to, co podał użytkownik. Możesz założyć, że użytkownik posiada "bazę" (sól, pieprz, woda, olej, podstawowe przyprawy).
2. Format: Zwróć ODPOWIEDŹ WYŁĄCZNIE W FORMACIE JSON. Nie pisz żadnych wstępów ani podsumowań.
3. Język: Odpowiadaj w języku polskim.
4. Kreatywność: Jeśli składniki do siebie nie pasują, spróbuj znaleźć najbardziej sensowne połączenie (np. kuchnia fusion).

STRUKTURA JSON:
{{
  "title": "Nazwa dania",
  "description": "Krótki, apetyczny opis (max 2 zdania).",
  "difficulty": "Łatwe/Średnie/Trudne",
  "prep_time": "czas w minutach",
  "ingredients": [
    {{"item": "nazwa", "amount": "ilość", "is_extra": true/false}}
  ],
  "instructions": ["Krok 1...", "Krok 2..."],
  "tips": "Opcjonalna porada szefa kuchni."
}}

*is_extra: oznacz jako true, jeśli składnika nie ma na liście użytkownika, ale jest niezbędny do wykonania dania.*

SKŁADNIKI UŻYTKOWNIKA:
{json.dumps(ingredients, ensure_ascii=False)}
"""

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL,
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
                raise HTTPException(status_code=502, detail="AI zwróciło nieprawidłowy JSON")
            parsed = json.loads(ai_response[start : end + 1])

        return _build_inspire_response(parsed, ingredients)
    except HTTPException:
        raise
    except ValidationError:
        raise HTTPException(status_code=502, detail="AI zwróciło niepoprawny format danych")
    except Exception as e:
        logger.error(f"Error inspiring recipe: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nie udało się wygenerować inspiracji",
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
        raise HTTPException(status_code=400, detail="Tytuł nie może być pusty")

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
        raise HTTPException(status_code=400, detail="Lista składników nie może być pusta")

    instructions_list = _normalize_instruction_list(payload.instructions)
    instructions_text = "\n".join(instructions_list).strip()
    if not instructions_text:
        raise HTTPException(status_code=400, detail="Instrukcje nie moga byc puste")

    base_portions = max(1, int(payload.base_portions or 1))
    servings_unit = normalize_servings_unit(payload.servings_unit)
    yield_context = YieldContext(
        mode="explicit_people" if servings_unit == "people" else "explicit_servings",
        base_portions=base_portions,
        servings_unit="people" if servings_unit == "people" else "servings",
        yield_display_label=f"{base_portions} {'osob' if servings_unit == 'people' else 'porcji'}",
    )
    yield_context = resolve_yield_context_weights(
        context=yield_context,
        title=title,
        ingredients=ingredients,
        instructions=instructions_list,
    )

    nutrition_estimate, nutrition_source, nutrition_confidence_score = estimate_recipe_nutrition(
        title=title,
        ingredients=ingredients,
        instructions=instructions_list,
        base_portions=base_portions,
        page_nutrition_per_100g=None,
        portion_weight_g=yield_context.portion_weight_g,
    )
    rebalanced_portions = False
    if _rebalance_portions_for_dense_snack_if_needed(
        context=yield_context,
        title=title,
        ingredients=ingredients,
        instructions=instructions_list,
        nutrition_per_portion=nutrition_estimate,
    ):
        rebalanced_portions = True
    if _rebalance_portions_for_meal_if_needed(
        context=yield_context,
        title=title,
        ingredients=ingredients,
        instructions=instructions_list,
        nutrition_per_portion=nutrition_estimate,
    ):
        rebalanced_portions = True
    if rebalanced_portions:
        base_portions = max(1, int(yield_context.base_portions or base_portions))
        nutrition_estimate, nutrition_source, nutrition_confidence_score = estimate_recipe_nutrition(
            title=title,
            ingredients=ingredients,
            instructions=instructions_list,
            base_portions=base_portions,
            page_nutrition_per_100g=None,
            portion_weight_g=yield_context.portion_weight_g,
        )

    generic_icon = "https://cdn-icons-png.flaticon.com/512/3081/3081557.png"
    recipe = RecipeDB(
        owner_id=current_user.id,
        title=title,
        url=f"ai:{uuid.uuid4()}",
        image_url=generic_icon,
        ingredients=ingredients,
        instructions=instructions_text,
        base_portions=base_portions,
        servings_unit=servings_unit,
        yield_display_label=yield_context.yield_display_label,
        yield_assumption_reason=yield_context.assumption_reason,
        total_weight_g=yield_context.total_weight_g,
        portion_weight_g=yield_context.portion_weight_g,
        piece_weight_g=yield_context.piece_weight_g,
        pan_diameter_min_cm=yield_context.pan_diameter_min_cm,
        pan_diameter_max_cm=yield_context.pan_diameter_max_cm,
        nutrition_protein_g=_coerce_nutrition_number((nutrition_estimate or {}).get("protein_g")),
        nutrition_carbs_g=_coerce_nutrition_number((nutrition_estimate or {}).get("carbs_g")),
        nutrition_fat_g=_coerce_nutrition_number((nutrition_estimate or {}).get("fat_g")),
        nutrition_fiber_g=_coerce_nutrition_number((nutrition_estimate or {}).get("fiber_g")),
        nutrition_glycemic_load=_coerce_nutrition_number((nutrition_estimate or {}).get("glycemic_load")),
        nutrition_calories_kcal=_coerce_nutrition_number((nutrition_estimate or {}).get("calories_kcal")),
        nutrition_source=nutrition_source,
        nutrition_confidence_score=nutrition_confidence_score,
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
