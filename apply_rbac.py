import re

def refactor_rbac():
    with open("main.py", "r") as f:
        code = f.read()

    # 1. Update Helper Functions for Role Checking
    rbac_helpers = """
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

# Helper functions"""
    
    code = code.replace("# Helper functions", rbac_helpers)

    # Example: admin_dashboard
    dashboard_old = """@app.get("/admin/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:"""
    
    dashboard_new = """@app.get("/admin/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        if not is_staff: return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
        ctx = get_dashboard_context(request, db)"""
    
    code = code.replace(dashboard_old, dashboard_new)
    code = re.sub(r'"admin_username": get_setting\(db, "ADMIN_USERNAME"\),', r'"admin_username": ctx["name"], "is_admin": ctx["is_admin"],', code, count=1)

    # Do the same for /admin/tickets
    tickets_old = """@app.get("/admin/tickets", response_class=HTMLResponse)
async def admin_tickets(
    request: Request,
    page: int = 1,
    status: str = None,
    priority: str = None,
    category: str = None,
    search: str = None
):
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    per_page = 20
    
    with get_db() as db:"""
    
    tickets_new = """@app.get("/admin/tickets", response_class=HTMLResponse)
async def admin_tickets(
    request: Request,
    page: int = 1,
    ticket_status: str = None,
    priority: str = None,
    category: str = None,
    search: str = None
):
    per_page = 20
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        if not is_staff: return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
        ctx = get_dashboard_context(request, db)"""
    
    code = code.replace(tickets_old, tickets_new)
    code = code.replace('Ticket.status == status', 'Ticket.status == ticket_status')
    code = code.replace('"status": status,', '"status": ticket_status,')
    code = re.sub(r'"admin_username": get_setting\(db, "ADMIN_USERNAME"\),', r'"admin_username": ctx["name"], "is_admin": ctx["is_admin"],', code, count=1)

    # admin_ticket_detail
    ticket_detail_old = """@app.get("/admin/tickets/{ticket_id}", response_class=HTMLResponse)
async def admin_ticket_detail(request: Request, ticket_id: int):
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:"""
    
    ticket_detail_new = """@app.get("/admin/tickets/{ticket_id}", response_class=HTMLResponse)
async def admin_ticket_detail(request: Request, ticket_id: int):
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        if not is_staff: return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
        ctx = get_dashboard_context(request, db)"""
        
    code = code.replace(ticket_detail_old, ticket_detail_new)
    code = re.sub(r'"admin_username": get_setting\(db, "ADMIN_USERNAME"\),', r'"admin_username": ctx["name"], "is_admin": ctx["is_admin"],', code, count=1)

    # admin_ticket_update
    ticket_update_old = """@app.post("/admin/tickets/{ticket_id}/update")
async def admin_ticket_update(
    request: Request,
    ticket_id: int,
    status: str = Form(...),
    priority: str = Form(...)
):
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:"""
    
    ticket_update_new = """@app.post("/admin/tickets/{ticket_id}/update")
async def admin_ticket_update(
    request: Request,
    ticket_id: int,
    ticket_status: str = Form(..., alias="status"),
    priority: str = Form(...)
):
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        if not is_staff: return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)"""
        
    code = code.replace(ticket_update_old, ticket_update_new)
    code = code.replace('ticket.status = status', 'ticket.status = ticket_status')
    code = code.replace('if status == "resolved" and not ticket.resolved_at:', 'if ticket_status == "resolved" and not ticket.resolved_at:')

    # admin_add_comment
    comment_old = """@app.post("/admin/tickets/{ticket_id}/comment")
async def admin_add_comment(
    request: Request,
    ticket_id: int,
    content: str = Form(...),
    is_internal: str = Form(None)
):
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:"""
    
    comment_new = """@app.post("/admin/tickets/{ticket_id}/comment")
async def admin_add_comment(
    request: Request,
    ticket_id: int,
    content: str = Form(...),
    is_internal: str = Form(None)
):
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        if not is_staff: return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
        ctx = get_dashboard_context(request, db)"""
        
    code = code.replace(comment_old, comment_new)
    code = code.replace('author_name="Administrator",', 'author_name=ctx["name"],')

    # admin_users
    users_old = """@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request, page: int = 1, search: str = None):
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    per_page = 20
    
    with get_db() as db:"""
    
    users_new = """@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request, page: int = 1, search: str = None):
    per_page = 20
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        if not is_staff: return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
        ctx = get_dashboard_context(request, db)"""
        
    code = code.replace(users_old, users_new)
    code = re.sub(r'"admin_username": get_setting\(db, "ADMIN_USERNAME"\),', r'"admin_username": ctx["name"], "is_admin": ctx["is_admin"],', code, count=1)

    # admin_user_detail
    u_detail_old = """@app.get("/admin/users/{user_id}", response_class=HTMLResponse)
async def admin_user_detail(request: Request, user_id: int):
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:"""
    
    u_detail_new = """@app.get("/admin/users/{user_id}", response_class=HTMLResponse)
async def admin_user_detail(request: Request, user_id: int):
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        if not is_staff: return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
        ctx = get_dashboard_context(request, db)"""
        
    code = code.replace(u_detail_old, u_detail_new)
    code = re.sub(r'"admin_username": get_setting\(db, "ADMIN_USERNAME"\),', r'"admin_username": ctx["name"], "is_admin": ctx["is_admin"],', code, count=1)

    # admin_settings GET
    s_get_old = """@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request):
    \"\"\"Admin settings page\"\"\"
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    
    with get_db() as db:"""
    
    s_get_new = """@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request):
    \"\"\"Admin settings page\"\"\"
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        if not is_admin: return RedirectResponse(url="/admin/", status_code=status.HTTP_302_FOUND)
        ctx = get_dashboard_context(request, db)"""
        
    code = code.replace(s_get_old, s_get_new)
    code = re.sub(r'"admin_username": settings_dict\["ADMIN_USERNAME"\],', r'"admin_username": ctx["name"], "is_admin": ctx["is_admin"],', code, count=1)

    # admin_settings POST
    s_post_old = """@app.post("/admin/settings")
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
    session = validate_admin_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)

    with get_db() as db:"""

    s_post_new = """@app.post("/admin/settings")
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
        if not is_admin: return RedirectResponse(url="/admin/", status_code=status.HTTP_302_FOUND)"""
        
    code = code.replace(s_post_old, s_post_new)

    # Fix Upload Route
    code = code.replace(
        """@app.post("/tickets/{ticket_id}/upload")
async def upload_attachment(request: Request, ticket_id: int, file: UploadFile = File(...)):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    with get_db() as db:""",
        """@app.post("/tickets/{ticket_id}/upload")
async def upload_attachment(request: Request, ticket_id: int, file: UploadFile = File(...)):
    with get_db() as db:
        is_staff, is_admin = check_staff_access(request, db)
        user = get_current_user(request)
        if not is_staff and not user:
            raise HTTPException(status_code=401, detail="Unauthorized")"""
    )
    code = code.replace('if not ticket or (ticket.user_id != user.id and user.role == "user"):', 'if not ticket or (not is_staff and ticket.user_id != user.id):')
    code = code.replace('return {"filename": file.filename, "status": "uploaded"}', 'return RedirectResponse(url=f"/tickets/{ticket_id}" if not is_staff else f"/admin/tickets/{ticket_id}", status_code=status.HTTP_302_FOUND)')

    # Magic link routing for staff
    code = code.replace(
        """        resp = RedirectResponse(url="/tickets")
        resp.set_cookie(key="user_id", value=str(ml.user_id), max_age=86400, httponly=True); return resp""",
        """        user = db.query(User).filter(User.id == ml.user_id).first()
        target_url = "/admin/" if user and user.role in ["admin", "fixer"] else "/tickets"
        resp = RedirectResponse(url=target_url)
        resp.set_cookie(key="user_id", value=str(ml.user_id), max_age=86400, httponly=True); return resp"""
    )

    with open("main.py", "w") as f:
        f.write(code)

if __name__ == "__main__":
    refactor_rbac()
