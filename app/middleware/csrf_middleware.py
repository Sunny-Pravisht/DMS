"""
CSRF (Cross-Site Request Forgery) protection middleware for FastAPI.
"""
import secrets
from typing import Optional, Set
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import hashlib
import hmac

class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware that implements double-submit cookie pattern.
    
    How it works:
    1. For state-changing requests (POST, PUT, DELETE, PATCH), requires a CSRF token
    2. Token must be present in both cookie and header/form data
    3. Tokens must match to proceed with request
    4. New tokens are generated for each session
    """
    
    def __init__(
        self, 
        app, 
        cookie_name: str = "csrf_token",
        header_name: str = "X-CSRF-Token",
        form_field_name: str = "csrf_token",
        secret_key: str = None,
        secure: bool = True,
        httponly: bool = False,  # Must be False for JavaScript to read
        samesite: str = "strict",
        token_length: int = 32,
        max_age: int = 3600 * 24,  # 24 hours
        exclude_paths: Optional[Set[str]] = None,
        exclude_methods: Optional[Set[str]] = None
    ):
        super().__init__(app)
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.form_field_name = form_field_name
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.secure = secure
        self.httponly = httponly
        self.samesite = samesite
        self.token_length = token_length
        self.max_age = max_age
        self.exclude_paths = exclude_paths or {
            "/api/auth/login",
            "/api/auth/logout", 
            "/api/auth/check-session",
            "/api/auth/setup/check",
            "/api/auth/setup/initial-user",
            "/api/documents/upload",  # File uploads are authenticated via session cookies
            "/api/health",
            "/api/settings/test/ai",  # AI test endpoint
            "/api/settings/test/ai-simple",
            "/api/settings/test/ai-noauth",
            "/api/settings/test/ai-diagnostic",
            "/api/settings/test/ai-basic",
            "/api/test-ai",  # All test AI endpoints
            "/api/test-openai",  # All test OpenAI endpoints
            "/docs",
            "/openapi.json",
            "/redoc"
        }
        self.exclude_methods = exclude_methods or {"GET", "HEAD", "OPTIONS"}
        
    def generate_csrf_token(self) -> str:
        """Generate a new CSRF token."""
        return secrets.token_urlsafe(self.token_length)
    
    def sign_token(self, token: str) -> str:
        """Sign a token with the secret key."""
        signature = hmac.new(
            self.secret_key.encode(),
            token.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"{token}.{signature}"
    
    def verify_token(self, signed_token: str) -> Optional[str]:
        """Verify a signed token and return the original token if valid."""
        try:
            token, signature = signed_token.rsplit(".", 1)
            expected_signature = hmac.new(
                self.secret_key.encode(),
                token.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if hmac.compare_digest(signature, expected_signature):
                return token
            return None
        except (ValueError, AttributeError):
            return None
    
    def get_token_from_request(self, request: Request) -> Optional[str]:
        """Extract CSRF token from request headers or form data."""
        # Check header first (preferred method)
        token = request.headers.get(self.header_name)
        if token:
            return token
        
        # Check form data for form submissions
        if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
            # Form data will be parsed by FastAPI
            return None  # Let FastAPI handle form parsing
        
        # Check JSON body for API requests
        if request.headers.get("content-type", "").startswith("application/json"):
            # JSON body will be parsed by FastAPI
            return None  # Let FastAPI handle JSON parsing
        
        return None
    
    def should_check_csrf(self, request: Request) -> bool:
        """Determine if CSRF check should be performed for this request."""
        # Skip for excluded methods
        if request.method in self.exclude_methods:
            return False
        
        # Get the request path
        path = request.url.path
        
        # Skip for exact match excluded paths
        if path in self.exclude_paths:
            return False
        
        # Skip for paths starting with excluded prefixes
        for excluded_path in self.exclude_paths:
            if path.startswith(excluded_path):
                return False
        
        return True
    
    async def dispatch(self, request: Request, call_next):
        """Process the request and check CSRF token if needed."""
        # Get or generate CSRF token from cookie
        cookie_token = request.cookies.get(self.cookie_name)

        if not cookie_token:
            # Generate new token for new sessions
            new_token = self.generate_csrf_token()
            signed_token = self.sign_token(new_token)

            # Expose the token that this response's cookie will carry so the
            # /api/csrf-token endpoint hands out the same value.
            request.state.csrf_token = new_token

            # Process request
            response = await call_next(request)
            
            # Set CSRF cookie
            response.set_cookie(
                key=self.cookie_name,
                value=signed_token,
                max_age=self.max_age,
                secure=self.secure,
                httponly=self.httponly,
                samesite=self.samesite,
                path="/"
            )
            
            # Add token to response header for JavaScript to read
            response.headers["X-CSRF-Token"] = new_token
            
            return response
        
        # Verify existing token
        verified_token = self.verify_token(cookie_token)
        if not verified_token:
            # Invalid token, generate new one
            new_token = self.generate_csrf_token()
            signed_token = self.sign_token(new_token)

            request.state.csrf_token = new_token

            response = await call_next(request)
            
            response.set_cookie(
                key=self.cookie_name,
                value=signed_token,
                max_age=self.max_age,
                secure=self.secure,
                httponly=self.httponly,
                samesite=self.samesite,
                path="/"
            )
            
            response.headers["X-CSRF-Token"] = new_token
            
            return response
        
        request.state.csrf_token = verified_token

        # For state-changing requests, verify CSRF token
        if self.should_check_csrf(request):
            # Get token from request
            request_token = request.headers.get(self.header_name)
            
            if not request_token:
                # Try to get from JSON body for API requests
                if request.headers.get("content-type", "").startswith("application/json"):
                    # Store request body for later parsing
                    body = await request.body()
                    
                    # Create new request with stored body
                    async def receive():
                        return {"type": "http.request", "body": body}
                    
                    request._receive = receive
                    
                    try:
                        import json
                        data = json.loads(body)
                        request_token = data.get(self.form_field_name)
                    except (json.JSONDecodeError, AttributeError):
                        pass
            
            if not request_token or request_token != verified_token:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "CSRF token validation failed",
                        "error": "missing_or_invalid_csrf_token"
                    }
                )
        
        # Process request
        response = await call_next(request)
        
        # Refresh token in header for JavaScript
        response.headers["X-CSRF-Token"] = verified_token
        
        return response


class CSRFProtect:
    """
    Helper class for CSRF protection in FastAPI applications.
    """
    
    def __init__(self, app=None, **kwargs):
        self.app = app
        self.config = kwargs
        self.middleware = None
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize CSRF protection for the FastAPI app."""
        # Pin the signing key up front. Without this, every CSRFMiddleware built
        # from this config would fall back to its own random secret, so tokens
        # signed by one instance could never be verified by another.
        self.config.setdefault("secret_key", secrets.token_urlsafe(32))

        # Store middleware configuration
        self.middleware_config = self.config

        # Add CSRF middleware
        app.add_middleware(CSRFMiddleware, **self.config)

        # Add CSRF token generator endpoint
        @app.get("/api/csrf-token")
        async def get_csrf_token(request: Request):
            """Get current CSRF token for forms and AJAX requests."""
            # The middleware already resolved (or regenerated) this request's
            # token and owns the csrf_token cookie, so hand back exactly what
            # the cookie will carry. Minting a token here instead would race the
            # middleware's own Set-Cookie and leave the client holding a token
            # that no longer matches its cookie - which fails every subsequent
            # POST with a 403.
            return {"csrf_token": getattr(request.state, "csrf_token", None)}


def get_csrf_token(request: Request) -> Optional[str]:
    """Extract CSRF token from request for use in templates."""
    cookie_token = request.cookies.get("csrf_token")
    
    if cookie_token:
        csrf_middleware = CSRFMiddleware(None)
        return csrf_middleware.verify_token(cookie_token)
    
    return None