"""
User Management Service
Handles user initialization, management, and setup
"""

from sqlalchemy.orm import Session
from typing import Optional

from ..models import User, Role
from ..services.auth_service import AuthService

class UserService:
    """User management service"""
    
    def __init__(self, db: Session):
        self.db = db
        self.auth_service = AuthService(db)
    
    def ensure_initial_setup(self) -> bool:
        """Ensure initial setup is complete with default admin user"""
        # Check if any users exist
        user_count = self.db.query(User).count()
        if user_count > 0:
            return True
        
        # Create default roles first
        self.auth_service.create_default_roles()
        
        # Create default admin user
        self.create_default_admin_user()
        
        return True
    
    def create_default_admin_user(self) -> User:
        """Create default admin user if none exists"""
        admin_user = self.db.query(User).filter(User.is_admin).first()
        if admin_user:
            return admin_user
        
        # Create default admin user
        default_admin = User(
            username="admin",
            email="admin@documanager.local",
            full_name="System Administrator",
            is_admin=True,
            is_active=True
        )
        default_admin.set_password("admin123")  # Default password - should be changed
        
        self.db.add(default_admin)
        self.db.flush()  # Get the user ID
        
        # Assign admin role
        admin_role = self.db.query(Role).filter(Role.name == "admin").first()
        if admin_role:
            default_admin.roles.append(admin_role)
        
        self.db.commit()
        
        # Log the creation
        self.auth_service.log_audit_event(
            user_id=default_admin.id,
            action="default_admin_created",
            details={
                "username": default_admin.username,
                "email": default_admin.email,
                "note": "Default admin user created during initialization"
            }
        )
        
        return default_admin
    
    def update_admin_user(self, username: str, email: str, password: str, full_name: str = None) -> User:
        """Update the default admin user with new credentials"""
        # Find the default admin user
        admin_user = self.db.query(User).filter(
            (User.username == "admin") | (User.is_admin)
        ).first()
        
        if not admin_user:
            # Create new admin user if none exists
            return self.auth_service.create_admin_user(username, email, password, full_name)
        
        # Update existing admin user
        admin_user.username = username
        admin_user.email = email
        admin_user.full_name = full_name
        admin_user.set_password(password)
        admin_user.is_active = True
        
        self.db.commit()
        
        # Log the update
        self.auth_service.log_audit_event(
            user_id=admin_user.id,
            action="admin_user_updated",
            details={
                "username": username,
                "email": email,
                "note": "Admin user updated during setup"
            }
        )
        
        return admin_user
    
    def get_admin_user(self) -> Optional[User]:
        """Get the admin user"""
        return self.db.query(User).filter(User.is_admin).first()
    
    def is_setup_complete(self) -> bool:
        """Check if initial setup is complete"""
        user_count = self.db.query(User).count()
        return user_count > 0
    
    def get_setup_status(self) -> dict:
        """Get detailed setup status"""
        user_count = self.db.query(User).count()
        admin_count = self.db.query(User).filter(User.is_admin).count()
        role_count = self.db.query(Role).count()
        
        admin_user = None
        if admin_count > 0:
            admin_user = self.db.query(User).filter(User.is_admin).first()
        
        return {
            "setup_complete": user_count > 0,
            "user_count": user_count,
            "admin_count": admin_count,
            "role_count": role_count,
            "has_default_admin": admin_user is not None and admin_user.username == "admin",
            "admin_user": {
                "username": admin_user.username if admin_user else None,
                "email": admin_user.email if admin_user else None,
                "full_name": admin_user.full_name if admin_user else None
            } if admin_user else None
        }