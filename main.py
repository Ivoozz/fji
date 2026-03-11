"""FixJeICT - Modernized FastAPI Application with Encryption & Dynamic Setup"""
import os
import uuid
import secrets
import hashlib
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key

from models import (
    Base, User, Ticket, Comment, MagicLink, AdminSession, Setting,
    get_engine, get_session_local, init_db
)
from email_service import send_magic_link_email, send_ticket_notification, create_email_forwarding

# Load environment variables
load_dotenv()

# Setup FastAPI
app = FastAPI(title="FixJeICT", version="2.0.0")

# Ensure directories exist
os.makedirs("data", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Setup static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Encryption Helper
def get_encryption_key():
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        # Save to .env for persistence
        if not os.path.exists(".env"):
            with open(".env", "w") as f: f.write(f"ENCRYPTION_KEY={key}\\n")
        else:
            set_key(".env", "ENCRYPTION_KEY", key)
        os.environ["ENCRYPTION_KEY"] = key
    return key.encode()

cipher_suite = Fernet(get_encryption_key())

def encrypt_data(data: str) -> str:
    if not data: return ""
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(data: str) -> str:
    if not data: return ""
    try:
        return cipher_suite.decrypt(data.encode()).decode()
    except Exception:
        return data # Fallback if not encrypted

# Database dependency
@contextmanager
def get_db():
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_dep():
    with get_db() as db:
        yield db

# Setting Helpers
def get_setting(db, key: str, default=None, decrypt=False):
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting:
        return decrypt_data(setting.value) if decrypt else setting.value
    return default

def set_setting(db, key: str, value: str, encrypt=False):
    val = encrypt_data(value) if encrypt else value
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting:
        setting.value = val
    else:
        db.add(Setting(key=key, value=val))

# Middleware for First Run Setup
@app.middleware("http")
async def check_setup(request: Request, call_next):
    if request.url.path.startswith("/setup") or request.url.path.startswith("/static"):
        return await call_next(request)
    
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        if get_setting(db, "SETUP_COMPLETED") != "true":
            return RedirectResponse(url="/setup")
    finally:
        db.close()
    return await call_next(request)

# Helper functions
def generate_ticket_number():
    return f"TICK-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def create_admin_session():
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    with get_db() as db:
        session = AdminSession(session_id=session_id, expires_at=expires_at)
        db.add(session)
        db.commit()
    return session_id, expires_at

def validate_admin_session(request: Request):
    session_id = request.cookies.get("admin_session")
    if not session_id: return None
    with get_db() as db:
        return db.query(AdminSession).filter(
            AdminSession.session_id == session_id,
            AdminSession.expires_at > datetime.utcnow()
        ).first()

def get_current_user(request: Request):
    user_id = request.cookies.get("user_id")
    if user_id:
        with get_db() as db:
            return db.query(User).filter(User.id == int(user_id)).first()
    return None

# Jinja2 filters
templates.env.filters["status_color"] = lambda s: {"open": "primary", "in_progress": "warning", "resolved": "success", "closed": "secondary"}.get(s, "secondary")
templates.env.filters["status_label"] = lambda s: {"open": "Open", "in_progress": "In Behandeling", "resolved": "Opgelost", "closed": "Gesloten"}.get(s, s)
templates.env.filters["priority_color"] = lambda p: {"low": "success", "medium": "info", "high": "warning", "urgent": "danger"}.get(p, "secondary")
templates.env.filters["priority_label"] = lambda p: {"low": "Laag", "medium": "Normaal", "high": "Hoog", "urgent": "Spoed"}.get(p, p)
templates.env.filters["datetime"] = lambda v: v.strftime("%d-%m-%Y %H:%M") if v else ""

# Setup Routes
@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    with get_db() as db:
        if get_setting(db, "SETUP_COMPLETED") == "true": return RedirectResponse(url="/")
    return templates.TemplateResponse("setup.html", {"request": request})

@app.post("/setup")
async def setup_post(
    request: Request,
    admin_username: str = Form(...), admin_password: str = Form(...),
    resend_api_key: str = Form(...), email_from: str = Form(...),
    email_domain: str = Form(""), cf_token: str = Form(""),
    cf_zone: str = Form(""), cf_account: str = Form("")
):
    with get_db() as db:
        set_setting(db, "ADMIN_USERNAME", admin_username)
        set_setting(db, "ADMIN_PASSWORD_HASH", hash_password(admin_password))
        set_setting(db, "RESEND_API_KEY", resend_api_key, encrypt=True)
        set_setting(db, "EMAIL_FROM", email_from)
        set_setting(db, "EMAIL_DOMAIN", email_domain)
        set_setting(db, "CLOUDFLARE_API_TOKEN", cf_token, encrypt=True)
        set_setting(db, "CLOUDFLARE_ZONE_ID", cf_zone)
        set_setting(db, "CLOUDFLARE_ACCOUNT_ID", cf_account)
        set_setting(db, "SETUP_COMPLETED", "true")
        db.commit()
    return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)

# Public Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "user": get_current_user(request)})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.post("/login")
async def login_post(request: Request, email: str = Form(...)):
    with get_db() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, name=email.split("@")[0]); db.add(user); db.commit(); db.refresh(user)
            # Create forwarding
            await create_email_forwarding(user.email, user.name, get_setting(db, "CLOUDFLARE_API_TOKEN", decrypt=True), get_setting(db, "CLOUDFLARE_ZONE_ID"), get_setting(db, "CLOUDFLARE_ACCOUNT_ID"), get_setting(db, "EMAIL_DOMAIN"))
        
        token = secrets.token_urlsafe(32)
        db.add(MagicLink(user_id=user.id, token=token, expires_at=datetime.utcnow() + timedelta(hours=24)))
        db.commit()
        
        url = f"{str(request.base_url).rstrip('/')}/auth/magic/{token}"
        send_magic_link_email(user.email, url, user.name, get_setting(db, "RESEND_API_KEY", decrypt=True), get_setting(db, "EMAIL_FROM"))
        return HTMLResponse("Login link verzonden naar uw e-mail.")

@app.get("/auth/magic/{token}")
async def magic_link_verify(request: Request, token: str):
    with get_db() as db:
        ml = db.query(MagicLink).filter(MagicLink.token == token, MagicLink.used == False, MagicLink.expires_at > datetime.utcnow()).first()
        if not ml: return RedirectResponse(url="/login?error=invalid_link")
        ml.used = True; db.commit()
        resp = RedirectResponse(url="/tickets")
        resp.set_cookie(key="user_id", value=str(ml.user_id), max_age=86400, httponly=True); return resp

@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/"); resp.delete_cookie("user_id"); return resp

# Admin Routes
@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request, error: str = None):
    if validate_admin_session(request): return RedirectResponse(url="/admin/")
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": error})

@app.post("/admin/login")
async def admin_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    with get_db() as db:
        if username == get_setting(db, "ADMIN_USERNAME") and verify_password(password, get_setting(db, "ADMIN_PASSWORD_HASH")):
            sid, exp = create_admin_session()
            resp = RedirectResponse(url="/admin/")
            resp.set_cookie(key="admin_session", value=sid, expires=int(exp.timestamp()), httponly=True); return resp
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": "Ongeldige gegevens"}, status_code=401)

@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request):
    if not validate_admin_session(request): return RedirectResponse(url="/admin/login")
    with get_db() as db:
        settings = {k: get_setting(db, k, decrypt=(k in ["RESEND_API_KEY", "CLOUDFLARE_API_TOKEN"])) for k in ["ADMIN_USERNAME", "RESEND_API_KEY", "EMAIL_FROM", "EMAIL_DOMAIN", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ZONE_ID", "CLOUDFLARE_ACCOUNT_ID"]}
    return templates.TemplateResponse("admin/settings.html", {"request": request, "admin_username": settings["ADMIN_USERNAME"], "settings": settings, "message": request.query_params.get("message")})

@app.post("/admin/settings")
async def admin_settings_post(request: Request, admin_username: str = Form(...), admin_password: str = Form(""), resend_api_key: str = Form(...), email_from: str = Form(...), email_domain: str = Form(""), cf_token: str = Form(""), cf_zone: str = Form(""), cf_account: str = Form("")):
    if not validate_admin_session(request): return RedirectResponse(url="/admin/login")
    with get_db() as db:
        set_setting(db, "ADMIN_USERNAME", admin_username)
        if admin_password: set_setting(db, "ADMIN_PASSWORD_HASH", hash_password(admin_password))
        set_setting(db, "RESEND_API_KEY", resend_api_key, encrypt=True)
        set_setting(db, "EMAIL_FROM", email_from)
        set_setting(db, "EMAIL_DOMAIN", email_domain)
        set_setting(db, "CLOUDFLARE_API_TOKEN", cf_token, encrypt=True)
        set_setting(db, "CLOUDFLARE_ZONE_ID", cf_zone)
        set_setting(db, "CLOUDFLARE_ACCOUNT_ID", cf_account); db.commit()
    return RedirectResponse(url="/admin/settings?message=Opgeslagen")

# (Other admin/ticket routes omitted for brevity - would be updated with get_setting calls)
@app.on_event("startup")
async def startup():
    init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
