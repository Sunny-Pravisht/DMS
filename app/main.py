from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.orm import Session
import os
import uvicorn
from pathlib import Path

from .database import get_db
from .routers import (
    search, settings, doctypes, tags, health, auth, backup, documents,
    correspondents, security, admin_fix, studio, workflow, publishing, audit,
    signatures,
)
from .services.backup_scheduler import backup_scheduler
# from .middleware.auth_middleware import AuthMiddleware  # Disabled for now
from .middleware.error_handler import ErrorHandler
from .config import get_settings
# Temporarily disable complex middleware for fast startup
from .middleware.csrf_middleware import CSRFProtect
from .middleware.rate_limit_middleware import RateLimitProtect
# from .middleware.logging_middleware import LoggingMiddleware, RequestContextMiddleware
# from .utils.logging_config import configure_application_logging, log_security_event
# from loguru import logger

# Tables will be created when needed

app = FastAPI(
    title="HARMAN Document Management System",
    description=(
        "Capture, author, approve and retain documents. OCR and AI-assisted "
        "classification on the way in; a template-driven Document Studio for "
        "everything written in-house."
    ),
    version="1.1.0",
)

app_settings = get_settings()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],  # Restrict headers
)

# Add global exception handlers
app.add_exception_handler(HTTPException, ErrorHandler.http_exception_handler)
app.add_exception_handler(RequestValidationError, ErrorHandler.validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, ErrorHandler.starlette_exception_handler)
app.add_exception_handler(Exception, ErrorHandler.general_exception_handler)

# Enable CSRF protection
csrf_protect = CSRFProtect(
    # Sign CSRF tokens with the configured application secret so tokens stay
    # valid across restarts and across multiple worker processes. A per-process
    # random key invalidates every browser's cookie on restart.
    secret_key=app_settings.secret_key,
    secure=app_settings.production_mode,  # Use secure cookies in production
    exclude_paths={
        "/api/auth/login",
        "/api/auth/logout", 
        "/api/auth/check-session",
        "/api/auth/setup/check",
        "/api/auth/setup/initial-user",
        "/api/health",
        "/api/settings/test/ai",  # Exclude the original test endpoint
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/csrf-token"
    }
)
csrf_protect.init_app(app)

# Enable rate limiting
rate_limit = RateLimitProtect(
    default_limit=100,  # 100 requests per minute for general endpoints
    window_seconds=60,
    login_limit=5,  # 5 login attempts per 5 minutes
    login_window_seconds=300,
    trusted_proxy_ips=app_settings.trusted_proxy_ips_list,
)
rate_limit.init_app(app)

# Authentication middleware (disabled for now)
# app.add_middleware(AuthMiddleware)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(doctypes.router, prefix="/api/doctypes", tags=["doctypes"])
app.include_router(tags.router, prefix="/api/tags", tags=["tags"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(backup.router, prefix="/api/backup", tags=["backup"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(correspondents.router, prefix="/api/correspondents", tags=["correspondents"])
app.include_router(security.router, prefix="/api/security", tags=["security"])
app.include_router(admin_fix.router, prefix="/api/admin", tags=["admin"])
app.include_router(studio.router, prefix="/api/studio", tags=["studio"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["workflow"])
app.include_router(publishing.router, prefix="/api/publishing", tags=["publishing"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(signatures.router, prefix="/api/signatures", tags=["signatures"])

# Serve static files
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

# Global file watcher instance
file_watcher = None

# Removed vector database check for faster startup

@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup"""
    global file_watcher
    
    print("🚀 Document Management System starting...")
    print("📊 All initialization will happen on first access")
    print("⚡ Fast startup mode - no database operations")
    
    # Initialize backup scheduler (but don't start it automatically)
    try:
        backup_scheduler.configure(enabled=False)  # Disabled by default
        print("📦 Backup scheduler initialized (disabled by default)")
    except Exception as e:
        print(f"⚠️  Could not initialize backup scheduler: {e}")
    
    # Schedule default document types check in background
    import asyncio
    from .database import SessionLocal
    from .services.doctype_manager import ensure_default_document_types
    
    async def ensure_defaults():
        await asyncio.sleep(2)  # Wait 2 seconds to not impact startup
        # First ensure database tables exist
        from .database import init_db
        try:
            init_db()
            print("✅ Database tables initialized")
        except Exception as e:
            print(f"⚠️  Could not initialize database: {e}")
            return
            
        db = SessionLocal()
        try:
            # Ensure folders are created in the right location
            from .services.folder_setup import setup_folders
            setup_folders(db)
            print("✅ Folder structure initialized")
            
            ensure_default_document_types(db)
            print("✅ Default document types ensured")

            # The Studio's image library: the brand marks and seals users can
            # place in a document. Idempotent, so this is safe on every boot.
            from .services.media_service import seed_builtins
            seed_builtins(db)
            print("✅ Document Studio image library ready")

            # Standard roles, and a role for anyone who somehow has none.
            # A user who can sign in but cannot read anything is a dead end.
            from .services.role_service import backfill, ensure_standard_roles
            ensure_standard_roles(db)
            backfill(db)
            print("✅ Roles and approval permissions ensured")
        except Exception as e:
            print(f"⚠️  Could not ensure default document types: {e}")
        finally:
            db.close()
    
    # Run in background without blocking startup
    asyncio.create_task(ensure_defaults())
    
    # Initialize file watcher for automatic document processing
    async def start_file_watcher():
        await asyncio.sleep(3)  # Wait for database initialization
        try:
            from .services.file_watcher import FileWatcher

            watcher = FileWatcher()
            # FileWatcher.start also recovers files that arrived before the
            # observer was ready. Run the initial scan off the event loop
            # because OCR can be CPU intensive.
            await asyncio.to_thread(watcher.start)
            if not watcher.is_running:
                raise RuntimeError("File watcher did not start")

            global file_watcher
            file_watcher = watcher
            print(f"📁 File watcher started monitoring: {watcher.settings.staging_folder}")
        except Exception as e:
            print(f"⚠️  Could not start file watcher: {e}")
    
    # Start file watcher in background
    asyncio.create_task(start_file_watcher())

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    global file_watcher
    if file_watcher:
        file_watcher.stop()
    
    # Stop backup scheduler
    try:
        backup_scheduler.stop()
        print("📦 Backup scheduler stopped")
    except Exception as e:
        print(f"⚠️  Error stopping backup scheduler: {e}")

# ---------------------------------------------------------------------------
# User interface
#
# The interface lives in frontend/ui as one HTML file per page, sharing a
# design system (css/dms.css) and an application shell (js/shell.js). Each
# route below maps a clean URL to its page file; everything except /login
# requires an authenticated session.
#
# The legacy single-file interface (frontend/index.html + app.js + styles.css)
# is retired and no longer routed. See README.md → "Removed / retired".
# ---------------------------------------------------------------------------
UI_DIR = Path(__file__).parent.parent / "frontend" / "ui"

UI_PAGES = {
    # The five-step spine. Step 1 is the Studio, which is also where the
    # product opens: a document is written there or brought in there, and both
    # are the same step.
    "/studio": "studio.html",            # 1 · write it, or bring a file in
    "/review": "review.html",            # 2 · confirm what was read
    "/process": "process.html",          # 3 · choose the approvers
    "/track": "track.html",              # 4 · watch it get signed
    "/publish": "publish.html",          # 5 · release it
    # Find & do
    "/tasks": "tasks.html",
    "/documents": "documents.html",
    "/documents/detail": "document.html",
    "/documents/view": "viewer.html",    # the whole document, full screen
    "/search": "search.html",
    "/assistant": "assistant.html",
    # Set up
    "/templates": "templates.html",
    "/organization": "organization.html",
    "/audit": "audit.html",
    "/settings": "settings.html",
}

# Screens that were renamed, merged or retired. Keeping the old URLs alive
# means no bookmark, demo script or shared link breaks.
#
# The retired ones - a process designer, a records warehouse, a retention
# console, an integrations catalogue - had no working module behind them. They
# now point at the screen that does the nearest real job, rather than at a
# convincing picture of one.
UI_REDIRECTS = {
    # "/", "/home" and "/dashboard" are not listed here: they land somewhere
    # different depending on who is signed in, so they get their own handler
    # below. An unauthenticated visitor must reach the sign-in page rather than
    # be bounced to a screen that will only bounce them again.
    # Adding a file was its own screen once. It is now the right-hand half of
    # the Studio, because choosing a file and checking you chose the right one
    # are one act, and splitting them across two screens made people upload
    # twice to be sure.
    "/upload": "/studio",
    "/capture": "/studio",
    "/compose": "/studio",
    "/editor": "/studio",
    "/approvals": "/tasks",
    "/workflows": "/templates",     # route design lives on Approval Routes
    "/retention": "/documents",
    "/records": "/documents",
    "/integrations": "/settings",
}


def _ui_file(filename: str) -> FileResponse:
    """Serve a page from frontend/ui, no-cache so redeploys are picked up."""
    return FileResponse(
        str(UI_DIR / filename),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Serve the sign-in page (also handles first-run administrator setup)."""
    login_path = UI_DIR / "login.html"
    if login_path.exists():
        return _ui_file("login.html")
    return HTMLResponse(
        "<html><head><title>Sign in</title></head>"
        "<body><h1>Sign in</h1><p>Interface files not found.</p></body></html>"
    )


# Screens that only make sense to somebody administering the system: setting up
# routes and people, reading the audit log, changing configuration, and running
# the publishing queue. An approver sent to one of these has nothing to do
# there, so they are returned to the screen they actually came to use.
#
# Enforced on the server, not just hidden in the menu. A hidden link is a
# courtesy; a redirect is a rule.
ADMIN_ONLY_PAGES = {
    "/templates", "/organization", "/audit", "/settings", "/publish", "/process",
}


def _make_page_route(filename: str, route: str = ""):
    async def page(request: Request, db: Session = Depends(get_db)):
        from .services.auth_service import get_user_from_session_token

        user = get_user_from_session_token(request, db)
        if not user:
            return RedirectResponse(url="/login", status_code=302)

        if route in ADMIN_ONLY_PAGES and not user.is_admin:
            return RedirectResponse(url="/tasks", status_code=302)

        if not (UI_DIR / filename).exists():
            return HTMLResponse(
                "<html><head><title>Document Management System</title></head><body>"
                "<h1>Document Management System</h1>"
                "<p>API is running. Interface files not found.</p>"
                '<p>Visit <a href="/docs">/docs</a> for API documentation.</p>'
                "</body></html>"
            )
        return _ui_file(filename)

    return page


for _route, _filename in UI_PAGES.items():
    app.get(_route, response_class=HTMLResponse)(_make_page_route(_filename, _route))


def _make_redirect_route(target: str):
    async def redirect():
        return RedirectResponse(url=target, status_code=301)

    return redirect


for _old, _new in UI_REDIRECTS.items():
    app.get(_old)(_make_redirect_route(_new))


@app.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Entry point, chosen by what the person is here to do.

    An administrator lands on the Studio, at the top of the five steps. An
    approver lands on their task list, because that is the whole of their job
    and making them navigate to it every morning is a small daily insult.
    """
    from .services.auth_service import get_user_from_session_token

    return _landing(request, db)


@app.get("/home", response_class=HTMLResponse)
async def home_page(request: Request, db: Session = Depends(get_db)):
    """The old dashboard URL. Sends each person to their own starting screen."""
    return _landing(request, db)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, db: Session = Depends(get_db)):
    return _landing(request, db)


def _landing(request: Request, db: Session):
    from .services.auth_service import get_user_from_session_token

    user = get_user_from_session_token(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/studio" if user.is_admin else "/tasks", status_code=302)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Document Management System is running"}

@app.get("/api/health")
async def api_health_check():
    """API health check endpoint - redirects to full health check"""
    return {"status": "healthy", "message": "Document Management System is running", "note": "For detailed health check, use /api/health/"}

@app.get("/{path:path}")
async def catch_all(request: Request, path: str):
    """Catch-all route for undefined paths"""
    # For API paths, return JSON 404
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # For other paths, return HTML 404 page
    return ErrorHandler.create_error_page(
        status_code=404,
        title="Page Not Found",
        message="The page you're looking for doesn't exist.",
        request=request
    )

if __name__ == "__main__":
    host = os.getenv("DOCUMENT_MANAGER_HOST", "127.0.0.1")
    uvicorn.run("app.main:app", host=host, port=8000, reload=True)
