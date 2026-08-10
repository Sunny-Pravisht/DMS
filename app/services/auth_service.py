"""
Authentication and Authorization Service
Handles user authentication, session management, and RBAC
"""

import secrets
import json
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..models import User, Role, Session as UserSession, AuditLog
from ..database import get_db
from ..utils.logging_config import log_security_event
from loguru import logger

# Security configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
SESSION_EXPIRE_HOURS = 24

def get_secret_key(db: Session) -> str:
    """Get JWT secret key from database settings"""
    from ..config import get_settings
    settings = get_settings(db)
    # Generate a secure random key if not set
    if not hasattr(settings, 'jwt_secret_key') or not settings.jwt_secret_key:
        secret_key = secrets.token_urlsafe(32)
        # Save to database
        from ..models import Settings
        setting = db.query(Settings).filter(Settings.key == "jwt_secret_key").first()
        if not setting:
            setting = Settings(key="jwt_secret_key", value=secret_key, description="JWT secret key for authentication")
            db.add(setting)
        else:
            setting.value = secret_key
        db.commit()
        return secret_key
    return settings.jwt_secret_key

security = HTTPBearer()

class AuthService:
    """Authentication and Authorization Service"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        secret_key = get_secret_key(self.db)
        encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[str]:
        """Verify JWT token and return username"""
        try:
            secret_key = get_secret_key(self.db)
            payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                return None
            return username
        except JWTError:
            return None
    
    def authenticate_user(self, username: str, password: str, ip_address: str = None, user_agent: str = None) -> Optional[User]:
        """Authenticate user with username/password"""
        user = self.db.query(User).filter(
            (User.username == username) | (User.email == username)
        ).first()
        
        if not user:
            # Log failed login attempt - user not found
            log_security_event(
                event_type="login_failed_user_not_found",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"attempted_username": username[:50]}  # Truncate for security
            )
            logger.warning(f"Login attempt with non-existent username: {username[:20]}...")
            return None
        
        if not user.verify_password(password):
            # Log failed login attempt - wrong password
            log_security_event(
                event_type="login_failed_wrong_password",
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"username": user.username}
            )
            logger.warning(f"Failed login attempt for user: {user.username}")
            return None
        
        if not user.is_active:
            # Log failed login attempt - inactive user
            log_security_event(
                event_type="login_failed_inactive_user",
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"username": user.username}
            )
            logger.warning(f"Login attempt for inactive user: {user.username}")
            return None
        
        # Successful authentication
        log_security_event(
            event_type="login_successful",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"username": user.username}
        )
        logger.info(f"Successful login for user: {user.username}")
        
        # Update last login
        user.last_login = datetime.utcnow()
        self.db.commit()
        
        return user
    
    def create_session(self, user: User, ip_address: str = None, user_agent: str = None) -> str:
        """Create user session"""
        session_token = secrets.token_urlsafe(32)
        
        session = UserSession(
            user_id=user.id,
            session_token=session_token,
            expires_at=datetime.utcnow() + timedelta(hours=SESSION_EXPIRE_HOURS),
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.db.add(session)
        self.db.commit()
        
        return session_token
    
    def get_session(self, session_token: str) -> Optional[UserSession]:
        """Get valid session"""
        session = self.db.query(UserSession).filter(
            UserSession.session_token == session_token,
            UserSession.expires_at > datetime.utcnow()
        ).first()
        
        return session
    
    def invalidate_session(self, session_token: str):
        """Invalidate session"""
        session = self.db.query(UserSession).filter(
            UserSession.session_token == session_token
        ).first()
        
        if session:
            self.db.delete(session)
            self.db.commit()
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        self.db.query(UserSession).filter(
            UserSession.expires_at <= datetime.utcnow()
        ).delete()
        self.db.commit()
    
    def log_audit_event(self, user_id: str, action: str, resource_type: str = None, 
                       resource_id: str = None, details: dict = None, 
                       ip_address: str = None, user_agent: str = None):
        """Log audit event"""
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.db.add(audit_log)
        self.db.commit()
    
    def create_default_roles(self):
        """Create default roles if they don't exist"""
        default_roles = [
            {
                "name": "admin",
                "description": "Full system administrator",
                "permissions": ["*"]  # All permissions
            },
            {
                "name": "editor",
                "description": "Can view, create, and edit documents",
                "permissions": [
                    "documents.read", "documents.create", "documents.update",
                    "documents.delete", "correspondents.read", "correspondents.create",
                    "correspondents.update", "doctypes.read", "doctypes.create",
                    "doctypes.update", "tags.read", "tags.create", "tags.update"
                ]
            },
            {
                "name": "viewer",
                "description": "Can only view documents",
                "permissions": [
                    "documents.read", "correspondents.read", "doctypes.read", "tags.read"
                ]
            }
        ]
        
        for role_data in default_roles:
            existing_role = self.db.query(Role).filter(Role.name == role_data["name"]).first()
            if not existing_role:
                role = Role(
                    name=role_data["name"],
                    description=role_data["description"],
                    permissions=json.dumps(role_data["permissions"])
                )
                self.db.add(role)
        
        self.db.commit()
    
    def create_admin_user(self, username: str, email: str, password: str, full_name: str = None) -> User:
        """Create admin user"""
        # Check if user already exists
        existing_user = self.db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            raise ValueError("User with this username or email already exists")
        
        # Create user
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            is_admin=True,
            is_active=True
        )
        user.set_password(password)
        
        self.db.add(user)
        self.db.flush()  # Get the user ID
        
        # Assign admin role
        admin_role = self.db.query(Role).filter(Role.name == "admin").first()
        if admin_role:
            user.roles.append(admin_role)
        
        self.db.commit()
        return user

# Dependency to get current user from token
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        auth_service = AuthService(db)
        username = auth_service.verify_token(credentials.credentials)
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception
    
    return user

# Dependency to get current user from session
def get_user_from_session_token(
    request: Request,
    db: Session
) -> Optional[User]:
    """Get current user from session cookie (without FastAPI dependency)"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        return None
    
    auth_service = AuthService(db)
    session = auth_service.get_session(session_token)
    if not session:
        return None
    
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not user.is_active:
        return None
    
    return user

async def get_current_user_from_session(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user from session cookie (FastAPI dependency)"""
    return get_user_from_session_token(request, db)

# Flexible authentication that supports both JWT and session
async def get_current_user_flexible(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))
) -> User:
    """Get current user from either JWT token or session cookie"""
    user = None
    
    # Try JWT authentication first
    if credentials:
        try:
            auth_service = AuthService(db)
            username = auth_service.verify_token(credentials.credentials)
            if username:
                user = db.query(User).filter(User.username == username).first()
                if user and user.is_active:
                    return user
        except Exception:
            pass  # Fall through to session authentication
    
    # Try session authentication
    user = get_user_from_session_token(request, db)
    if user and user.is_active:
        return user
    
    # Neither authentication method worked
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

# Permission checker dependency
def require_permission(permission: str):
    """Dependency factory for permission checking"""
    def permission_checker(current_user: User = Depends(get_current_user)):
        if not current_user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}"
            )
        return current_user
    return permission_checker

# Flexible permission checker that supports both JWT and session authentication
def require_permission_flexible(permission: str):
    """Dependency factory for permission checking with flexible authentication"""
    def permission_checker(current_user: User = Depends(get_current_user_flexible)):
        if not current_user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}"
            )
        return current_user
    return permission_checker

# Admin only dependency
def require_admin(current_user: User = Depends(get_current_user)):
    """Dependency for admin-only endpoints"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def require_admin_flexible(current_user: User = Depends(get_current_user_flexible)):
    """Dependency for admin-only endpoints with flexible authentication"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user