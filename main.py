"""FixJeICT - Single File FastAPI Application"""
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
from dotenv import load_dotenv

from models import (
    Base, User, Ticket, Comment, MagicLink, AdminSession, Setting,
    get_engine, get_session_local, init_db
)
from email_service import send_magic_link_email, send_ticket_notification, create_email_forwarding

# Load environment variables
load_dotenv()

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/fixjeict.db")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID", "")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
EMAIL_DOMAIN = os.getenv("EMAIL_DOMAIN", "fixjeict.nl")

# Setup FastAPI
app = FastAPI(title="FixJeICT", version="2.0.0")

# Ensure static directory exists before mounting
os.makedirs("static", exist_ok=True)

# Setup static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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
async def login_post(request: Request, email: str = Form(...)):
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
                result = await create_email_forwarding(user.email, user.name)
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
        if RESEND_API_KEY:
            send_magic_link_email(user.email, magic_link_url, user.name)
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
            send_ticket_notification(user.email, ticket.ticket_number, ticket.subject, user.name)
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
    if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
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
        "admin_username": ADMIN_USERNAME,
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
            query = query.filter(Ticket.status == status)
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
        "admin_username": ADMIN_USERNAME,
        "tickets": tickets,
        "pagination": {
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "has_prev": page > 1,
            "has_next": page < total_pages
        },
        "filters": {
            "status": status,
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
        "admin_username": ADMIN_USERNAME,
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
        
        ticket.status = status
        ticket.priority = priority
        
        if status == "resolved" and not ticket.resolved_at:
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
            author_name="Administrator",
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
        "admin_username": ADMIN_USERNAME,
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
        "admin_username": ADMIN_USERNAME,
        "user": user,
        "tickets": tickets
    })


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request):
    """Admin settings page"""
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "admin_username": ADMIN_USERNAME
    })


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
