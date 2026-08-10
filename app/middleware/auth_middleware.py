"""
Authentication Middleware
Handles both session-based and token-based authentication
"""

from fastapi import Request, Response, status
from fastapi.responses import RedirectResponse
import re

from ..database import get_db
from ..services.auth_service import AuthService
from ..models import User

class AuthMiddleware:
    """Authentication middleware for handling auth on protected routes"""
    
    def __init__(self, app):
        self.app = app
        
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        
        # Skip authentication for certain paths
        if self.should_skip_auth(request.url.path):
            await self.app(scope, receive, send)
            return
        
        # Try to authenticate the request
        user = await self.authenticate_request(request)
        
        # For API routes, require authentication
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/auth/"):
            if not user:
                response = Response(
                    content='{"detail": "Authentication required"}',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json"
                )
                await response(scope, receive, send)
                return
        
        # For frontend routes, redirect to login if not authenticated
        elif not user and request.url.path in ["/", "/documents", "/search", "/settings"]:
            if request.method == "GET":
                response = RedirectResponse(url="/login", status_code=302)
                await response(scope, receive, send)
                return
        
        # Add user to request state if authenticated
        if user:
            scope["state"] = {"user": user}
        
        await self.app(scope, receive, send)
    
    def should_skip_auth(self, path: str) -> bool:
        """Determine if authentication should be skipped for this path"""
        skip_patterns = [
            r"^/api/auth/",
            r"^/api/health$",
            r"^/static/",
            r"^/docs",
            r"^/openapi.json",
            r"^/login",
            r"^/setup",
            r"^/favicon.ico"
        ]
        
        for pattern in skip_patterns:
            if re.match(pattern, path):
                return True
        
        return False
    
    async def authenticate_request(self, request: Request) -> User:
        """Try to authenticate the request using session or token"""
        db_gen = get_db()
        db = next(db_gen)
        
        try:
            auth_service = AuthService(db)
            
            # Try session-based authentication first
            session_token = request.cookies.get("session_token")
            if session_token:
                session = auth_service.get_session(session_token)
                if session:
                    user = db.query(User).filter(User.id == session.user_id).first()
                    if user and user.is_active:
                        return user
            
            # Try token-based authentication
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                username = auth_service.verify_token(token)
                if username:
                    user = db.query(User).filter(User.username == username).first()
                    if user and user.is_active:
                        return user
            
            return None
            
        except Exception:
            return None
        finally:
            db.close()