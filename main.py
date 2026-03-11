"""FixJeICT - Single File FastAPI Application"""
import os
import uuid
import secrets
import hashlib
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key
import shutil

from models import (
    Base, User, Ticket, Comment, MagicLink, AdminSession, Setting,
    Attachment, AuditLog,
    get_engine, get_session_local, init_db
)
from email_service import send_magic_link_email, send_ticket_notification, create_email_forwarding

# Load environment variables
load_dotenv()

# Configuration

# Setup FastAPI
app = FastAPI(title="FixJeICT", version="2.0.0")

# Ensure static directory exists before mounting
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
            with open(".env", "w") as f: f.write(f"ENCRYPTION_KEY={key}\n")
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
        return data

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
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/setup")
    finally:
        db.close()
    return await call_next(request)

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



def check_staff_access(request: Request, db: Session):
    # 1. Check Super Admin session
    session_id = request.cookies.get("admin_session")
    if session_id:
        admin_session = db.query(AdminSession).filter(AdminSession.session_id == session_id, AdminSession.expires_at > datetime.utcnow()).first()
        if admin_session:
            return True, True  # is_staff, is_admin

    # 2. Check Magic Link (User model)
    user_id = request.cookies.get("user_id")
    if user_id:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user and user.role in ["admin", "fixer"]:
            return True, user.role == "admin"
            
    return False, False

def get_dashboard_context(request: Request, db: Session):
    # Check Admin Session first
    session_id = request.cookies.get("admin_session")
    if session_id:
        admin_session = db.query(AdminSession).filter(AdminSession.session_id == session_id, AdminSession.expires_at > datetime.utcnow()).first()
        if admin_session:
            return {"name": get_setting(db, "ADMIN_USERNAME") or "Admin", "is_admin": True, "is_staff": True}
            
    # Check Magic Link
    user_id = request.cookies.get("user_id")
    if user_id:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user and user.role in ["admin", "fixer"]:
            return {"name": user.name, "is_admin": user.role == "admin", "is_staff": True}
            
    return None

# Helper functions
def generate_ticket_number():
    """Generate unique ticket number"""
    return f"TICK-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


def hash_password(password: str) -> str:
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == hashed


def create_admin_session():
    """Create new admin session"""
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    with get_db() as db:
        session = AdminSession(session_id=session_id, expires_at=expires_at)
        db.add(session)
        db.commit()
    
    return session_id, expires_at


def validate_admin_session(request: Request):
    """Validate admin session from cookie"""
    session_id = request.cookies.get("admin_session")
    if not session_id:
        return None
    
    with get_db() as db:
        session = db.query(AdminSession).filter(
            AdminSession.session_id == session_id,
            AdminSession.expires_at > datetime.utcnow()
        ).first()
        
        if session:
            return session
    
    return None


def get_current_user(request: Request):
    """Get current user from magic link session"""
    user_id = request.cookies.get("user_id")
    if user_id:
        with get_db() as db:
            return db.query(User).filter(User.id == int(user_id)).first()
    return None


# Jinja2 filters
def status_color(status: str) -> str:
    colors = {
        "open": "primary",
        "in_progress": "warning",
        "resolved": "success",
        "closed": "secondary"
    }
    return colors.get(status, "secondary")


def status_label(status: str) -> str:
    labels = {
        "open": "Open",
        "in_progress": "In Behandeling",
        "resolved": "Opgelost",
        "closed": "Gesloten"
    }
    return labels.get(status, status)


def priority_color(priority: str) -> str:
    colors = {
        "low": "success",
        "medium": "info",
        "high": "warning",
        "urgent": "danger"
    }
    return colors.get(priority, "secondary")


def priority_label(priority: str) -> str:
    labels = {
        "low": "Laag",
        "medium": "Normaal",
        "high": "Hoog",
        "urgent": "Spoed"
    }
    return labels.get(priority, priority)


def format_datetime(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime("%d-%m-%Y %H:%M")


# Register filters
templates.env.filters["status_color"] = status_color
templates.env.filters["status_label"] = status_label
templates.env.filters["priority_color"] = priority_color
templates.env.filters["priority_label"] = priority_label
templates.env.filters["datetime"] = format_datetime


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    os.makedirs("data", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    init_db()
    print("Database initialized")



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
    """Homepage"""
    user = get_current_user(request)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user
    })


@app.get("/services", response_class=HTMLResponse)
async def services(request: Request):
    """Services page"""
    user = get_current_user(request)
    return templates.TemplateResponse("base.html", {
        "request": request,
        "user": user,
        "title": "Diensten"
    })


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page"""
    user = get_current_user(request)
    return templates.TemplateResponse("base.html", {
        "request": request,
        "user": user,
        "title": "Over Ons"
    })


@app.get("/contact", response_class=HTMLResponse)
async def contact(request: Request):
    """Contact page"""
    user = get_current_user(request)
    return templates.TemplateResponse("base.html", {
        "request": request,
        "user": user,
        "title": "Contact"
    })


@app.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
    """Blog page"""
    user = get_current_user(request)
    return templates.TemplateResponse("base.html", {
        "request": request,
        "user": user,
        "title": "Blog"
    })


@app.get("/knowledge-base", response_class=HTMLResponse)
async def knowledge_base(request: Request):
    """Knowledge base page"""
    user = get_current_user(request)
    return templates.TemplateResponse("base.html", {
        "request": request,
        "user": user,
        "title": "Knowledge Base"
    })


# User Authentication Routes
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    """User login page (magic link)"""
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error
    })


@app.post("/login")
async def login_post(request: Request, background_tasks: BackgroundTasks, email: str = Form(...)):
    """Send magic link"""
    with get_db() as db:
        user = db.query(User).filter(User.email == email).first()
        is_new_user = False
        if not user:
            is_new_user = True
            name = email.split("@")[0]
            user = User(email=email, name=name)
            db.add(user)
            db.commit()
            db.refresh(user)

        # Create Cloudflare forwarding for new users
        if is_new_user:
            try:
                background_tasks.add_task(create_email_forwarding, user.email, user.name, get_setting(db, "CLOUDFLARE_API_TOKEN", decrypt=True), get_setting(db, "CLOUDFLARE_ZONE_ID"), get_setting(db, "CLOUDFLARE_ACCOUNT_ID"), get_setting(db, "EMAIL_DOMAIN"))
                if result.get("alias"):
                    user.forward_email = result["alias"]
                    db.commit()
            except Exception as e:
                print(f"[WARNING] Email forwarding setup failed: {e}")

        # Create magic link
        token = secrets.token_urlsafe(32)
        magic_link = MagicLink(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        db.add(magic_link)
        db.commit()

        # Build magic link URL
        base_url = str(request.base_url).rstrip("/")
        magic_link_url = f"{base_url}/auth/magic/{token}"

        # Send magic link email via Resend
        if get_setting(db, "RESEND_API_KEY"):
            background_tasks.add_task(send_magic_link_email, user.email, magic_link_url, user.name, get_setting(db, "RESEND_API_KEY", decrypt=True), get_setting(db, "EMAIL_FROM"))
            return templates.TemplateResponse("login_sent.html", {
                "request": request,
                "email": email
            })
        else:
            # Fallback: auto-login (demo mode)
            response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
            response.set_cookie(key="user_id", value=str(user.id), max_age=86400, httponly=True, secure=False)
            return response


@app.get("/auth/magic/{token}")
async def magic_link_verify(request: Request, token: str):
    """Verify magic link and log in user"""
    with get_db() as db:
        magic_link = db.query(MagicLink).filter(
            MagicLink.token == token,
            MagicLink.used.is_(False),
            MagicLink.expires_at > datetime.utcnow()
        ).first()

        if not magic_link:
            return RedirectResponse(url="/login?error=invalid_link", status_code=status.HTTP_302_FOUND)

        magic_link.used = True
        db.commit()

        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="user_id", value=str(magic_link.user_id), max_age=86400, httponly=True, secure=False)
        return response


@app.get("/logout")
async def logout():
    """Logout user"""
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("user_id")
    return response


# Ticket Routes
@app.get("/tickets", response_class=HTMLResponse)
async def tickets_list(request: Request):
    """User tickets list"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:
        tickets = db.query(Ticket).filter(Ticket.user_id == user.id).order_by(Ticket.created_at.desc()).all()
    
    return templates.TemplateResponse("tickets.html", {
        "request": request,
        "user": user,
        "tickets": tickets
    })


@app.get("/tickets/new", response_class=HTMLResponse)
async def ticket_new_page(request: Request, error: str = None):
    """New ticket form"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse("ticket_form.html", {
        "request": request,
        "user": user,
        "error": error
    })


@app.post("/tickets/new")
async def ticket_new_post(
    request: Request,
    background_tasks: BackgroundTasks,
    subject: str = Form(...),
    category: str = Form(...),
    priority: str = Form(...),
    description: str = Form(...)
):
    """Create new ticket"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:
        ticket = Ticket(
            ticket_number=generate_ticket_number(),
            user_id=user.id,
            subject=subject,
            category=category,
            priority=priority,
            description=description,
            status="open"
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        try:
            background_tasks.add_task(send_ticket_notification, user.email, ticket.ticket_number, ticket.subject, user.name, get_setting(db, "RESEND_API_KEY", decrypt=True), get_setting(db, "EMAIL_FROM"))
        except Exception as e:
            print(f"[WARNING] Failed to send ticket notification: {e}")

    return RedirectResponse(url=f"/tickets/{ticket.id}", status_code=status.HTTP_302_FOUND)


@app.get("/tickets/{ticket_id}", response_class=HTMLResponse)
async def ticket_detail(request: Request, ticket_id: int):
    """Ticket detail page"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user.id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        comments = db.query(Comment).filter(Comment.ticket_id == ticket_id).order_by(Comment.created_at).all()
    
    return templates.TemplateResponse("ticket_detail.html", {
        "request": request,
        "user": user,
        "ticket": ticket,
        "comments": comments
    })


@app.post("/tickets/{ticket_id}/comment")
async def ticket_add_comment(request: Request, ticket_id: int, content: str = Form(...)):
    """Add comment to ticket"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user.id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        comment = Comment(
            ticket_id=ticket_id,
            author_type="user",
            author_name=user.name,
            content=content
        )
        db.add(comment)
        db.commit()
    
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=status.HTTP_302_FOUND)



@app.post("/tickets/{ticket_id}/upload")
async def upload_attachment(request: Request, ticket_id: int, file: UploadFile = File(...)):
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        user = get_current_user(request)
        if not is_staff and not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket or (not is_staff and ticket.user_id != user.id):
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        file_path = f"data/uploads/{ticket_id}_{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        attachment = Attachment(ticket_id=ticket_id, filename=file.filename, file_path=file_path)
        db.add(attachment)
        db.commit()
        
    return RedirectResponse(url=f"/tickets/{ticket_id}" if not is_staff else f"/admin/tickets/{ticket_id}", status_code=status.HTTP_302_FOUND)

# Admin Routes - Login
@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request, error: str = None):
    """Admin login page"""
    # Check if already logged in
    session = validate_admin_session(request)
    if session:
        return RedirectResponse(url="/admin/", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse("admin/login.html", {
        "request": request,
        "error": error
    })


@app.post("/admin/login")
async def admin_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    """Admin login handler"""

    with get_db() as db:
        admin_username = get_setting(db, "ADMIN_USERNAME")
        admin_password_hash = get_setting(db, "ADMIN_PASSWORD_HASH")
        
        if username != admin_username or not verify_password(password, admin_password_hash):
            return templates.TemplateResponse("admin/login.html", {
                "request": request,
                "error": "Ongeldige gebruikersnaam of wachtwoord"
            }, status_code=401)

    
    # Create session
    session_id, expires_at = create_admin_session()
    
    response = RedirectResponse(url="/admin/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="admin_session",
        value=session_id,
        expires=int(expires_at.timestamp()),
        httponly=True,
        secure=False  # Set to True in production with HTTPS
    )
    return response


@app.get("/admin/logout")
async def admin_logout(request: Request):
    """Admin logout"""
    session_id = request.cookies.get("admin_session")
    if session_id:
        with get_db() as db:
            db.query(AdminSession).filter(AdminSession.session_id == session_id).delete()
            db.commit()
    
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("admin_session")
    return response


# Admin Routes - Dashboard & Management
@app.get("/admin/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Admin dashboard"""
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:
        total_tickets = db.query(Ticket).count()
        open_tickets = db.query(Ticket).filter(Ticket.status == "open").count()
        in_progress_tickets = db.query(Ticket).filter(Ticket.status == "in_progress").count()
        resolved_tickets = db.query(Ticket).filter(Ticket.status.in_(["resolved", "closed"])).count()
        
        recent_tickets = db.query(Ticket).order_by(Ticket.created_at.desc()).limit(10).all()
    
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "admin_username": ctx["name"], "is_admin": ctx["is_admin"],
        "stats": {
            "total_tickets": total_tickets,
            "open_tickets": open_tickets,
            "in_progress_tickets": in_progress_tickets,
            "resolved_tickets": resolved_tickets
        },
        "recent_tickets": recent_tickets
    })


@app.get("/admin/tickets", response_class=HTMLResponse)
async def admin_tickets(
    request: Request,
    page: int = 1,
    status: str = None,
    priority: str = None,
    category: str = None,
    search: str = None
):
    """Admin tickets list"""
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    per_page = 20
    
    with get_db() as db:
        query = db.query(Ticket)
        
        if status:
            query = query.filter(Ticket.status == ticket_status)
        if priority:
            query = query.filter(Ticket.priority == priority)
        if category:
            query = query.filter(Ticket.category == category)
        if search:
            query = query.filter(Ticket.subject.contains(search) | Ticket.ticket_number.contains(search))
        
        total = query.count()
        tickets = query.order_by(Ticket.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
        
        total_pages = (total + per_page - 1) // per_page
    
    return templates.TemplateResponse("admin/tickets.html", {
        "request": request,
        "admin_username": ctx["name"], "is_admin": ctx["is_admin"],
        "tickets": tickets,
        "pagination": {
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "has_prev": page > 1,
            "has_next": page < total_pages
        },
        "filters": {
            "status": ticket_status,
            "priority": priority,
            "category": category,
            "search": search
        }
    })


@app.get("/admin/tickets/{ticket_id}", response_class=HTMLResponse)
async def admin_ticket_detail(request: Request, ticket_id: int):
    """Admin ticket detail"""
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        comments = db.query(Comment).filter(Comment.ticket_id == ticket_id).order_by(Comment.created_at).all()
    
    return templates.TemplateResponse("admin/ticket_detail.html", {
        "request": request,
        "admin_username": ctx["name"], "is_admin": ctx["is_admin"],
        "ticket": ticket,
        "comments": comments
    })


@app.post("/admin/tickets/{ticket_id}/update")
async def admin_ticket_update(
    request: Request,
    ticket_id: int,
    status: str = Form(...),
    priority: str = Form(...)
):
    """Update ticket status and priority"""
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        ticket.status = ticket_status
        ticket.priority = priority
        
        if ticket_status == "resolved" and not ticket.resolved_at:
            ticket.resolved_at = datetime.utcnow()
        
        db.commit()
    
    return RedirectResponse(url=f"/admin/tickets/{ticket_id}", status_code=status.HTTP_302_FOUND)


@app.post("/admin/tickets/{ticket_id}/comment")
async def admin_add_comment(
    request: Request,
    ticket_id: int,
    content: str = Form(...),
    is_internal: str = Form(None)
):
    """Add admin comment"""
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:
        comment = Comment(
            ticket_id=ticket_id,
            author_type="admin",
            author_name=ctx["name"],
            content=content,
            is_internal=(is_internal == "true")
        )
        db.add(comment)
        db.commit()
    
    return RedirectResponse(url=f"/admin/tickets/{ticket_id}", status_code=status.HTTP_302_FOUND)


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request, page: int = 1, search: str = None):
    """Admin users list"""
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    per_page = 20
    
    with get_db() as db:
        query = db.query(User)
        
        if search:
            query = query.filter(
                User.name.contains(search) | 
                User.email.contains(search) |
                User.company.contains(search)
            )
        
        total = query.count()
        users = query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
        
        total_pages = (total + per_page - 1) // per_page
    
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "admin_username": ctx["name"], "is_admin": ctx["is_admin"],
        "users": users,
        "search": search,
        "pagination": {
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "has_prev": page > 1,
            "has_next": page < total_pages
        }
    })


@app.get("/admin/users/{user_id}", response_class=HTMLResponse)
async def admin_user_detail(request: Request, user_id: int):
    """Admin user detail"""
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        tickets = db.query(Ticket).filter(Ticket.user_id == user_id).order_by(Ticket.created_at.desc()).all()
    
    return templates.TemplateResponse("admin/user_detail.html", {
        "request": request,
        "admin_username": ctx["name"], "is_admin": ctx["is_admin"],
        "user": user,
        "tickets": tickets
    })


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request):
    """Admin settings page"""
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        if not is_admin: return RedirectResponse(url="/admin/", status_code=status.HTTP_302_FOUND)
        ctx = get_dashboard_context(request, db)
        settings_dict = {
            "ADMIN_USERNAME": get_setting(db, "ADMIN_USERNAME"),
            "RESEND_API_KEY": get_setting(db, "RESEND_API_KEY", decrypt=True),
            "EMAIL_FROM": get_setting(db, "EMAIL_FROM"),
            "EMAIL_DOMAIN": get_setting(db, "EMAIL_DOMAIN"),
            "CLOUDFLARE_API_TOKEN": get_setting(db, "CLOUDFLARE_API_TOKEN", decrypt=True),
            "CLOUDFLARE_ZONE_ID": get_setting(db, "CLOUDFLARE_ZONE_ID"),
            "CLOUDFLARE_ACCOUNT_ID": get_setting(db, "CLOUDFLARE_ACCOUNT_ID")
        }
    
    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "admin_username": ctx["name"], "is_admin": ctx["is_admin"],
        "settings": settings_dict,
        "message": request.query_params.get("message")
    })

@app.post("/admin/settings")
async def admin_settings_post(
    request: Request,
    admin_username: str = Form(...),
    admin_password: str = Form(""),
    resend_api_key: str = Form(...),
    email_from: str = Form(...),
    email_domain: str = Form(""),
    cloudflare_api_token: str = Form(""),
    cloudflare_zone_id: str = Form(""),
    cloudflare_account_id: str = Form("")
):
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        if not is_admin: return RedirectResponse(url="/admin/", status_code=status.HTTP_302_FOUND)
        set_setting(db, "ADMIN_USERNAME", admin_username)
        if admin_password:
            set_setting(db, "ADMIN_PASSWORD_HASH", hash_password(admin_password))
        set_setting(db, "RESEND_API_KEY", resend_api_key, encrypt=True)
        set_setting(db, "EMAIL_FROM", email_from)
        set_setting(db, "EMAIL_DOMAIN", email_domain)
        set_setting(db, "CLOUDFLARE_API_TOKEN", cloudflare_api_token, encrypt=True)
        set_setting(db, "CLOUDFLARE_ZONE_ID", cloudflare_zone_id)
        set_setting(db, "CLOUDFLARE_ACCOUNT_ID", cloudflare_account_id)
        db.commit()

    return RedirectResponse(url="/admin/settings?message=Instellingen+succesvol+opgeslagen", status_code=status.HTTP_302_FOUND)

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse("base.html", {
        "request": request,
        "title": "Pagina niet gevonden",
        "user": None
    }, status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
