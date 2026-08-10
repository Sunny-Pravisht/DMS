"""
Temporary admin endpoint to fix user permissions
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List
import json

from ..database import get_db
from ..models import User, Role
from ..services.auth_service import require_admin_flexible

router = APIRouter()

@router.post("/fix-permissions/{username}")
def fix_user_permissions(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible)
):
    """
    Fix permissions for a specific user by ensuring they have appropriate roles.
    Admin only endpoint.
    """
    # Find the user
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {username} not found")
    
    # Check current permissions
    current_perms = {
        "documents.read": user.has_permission("documents.read"),
        "documents.update": user.has_permission("documents.update"),
        "documents.delete": user.has_permission("documents.delete"),
        "settings.read": user.has_permission("settings.read")
    }
    
    # If user already has all permissions, nothing to do
    if all(current_perms.values()):
        return {
            "message": f"User {username} already has all required permissions",
            "permissions": current_perms,
            "roles": [role.name for role in user.roles]
        }
    
    # Get editor role (has document permissions)
    editor_role = db.query(Role).filter(Role.name == "editor").first()
    if not editor_role:
        # Create editor role if it doesn't exist
        editor_role = Role(
            name="editor",
            description="Can view, create, and edit documents",
            permissions=json.dumps([
                "documents.read", "documents.create", "documents.update",
                "documents.delete", "correspondents.read", "correspondents.create",
                "correspondents.update", "doctypes.read", "doctypes.create",
                "doctypes.update", "tags.read", "tags.create", "tags.update",
                "settings.read"  # Add settings.read permission
            ])
        )
        db.add(editor_role)
        db.flush()
    
    # Add editor role to user if they don't have it
    if editor_role not in user.roles:
        user.roles.append(editor_role)
        db.commit()
        
        # Check new permissions
        new_perms = {
            "documents.read": user.has_permission("documents.read"),
            "documents.update": user.has_permission("documents.update"),
            "documents.delete": user.has_permission("documents.delete"),
            "settings.read": user.has_permission("settings.read")
        }
        
        return {
            "message": f"Added editor role to user {username}",
            "previous_permissions": current_perms,
            "new_permissions": new_perms,
            "roles": [role.name for role in user.roles]
        }
    
    return {
        "message": f"User {username} already has editor role but still lacks permissions",
        "permissions": current_perms,
        "roles": [role.name for role in user.roles]
    }

@router.get("/check-permissions/{username}")
def check_user_permissions(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible)
):
    """Check permissions for a specific user"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {username} not found")
    
    # Get all permissions
    permission_checks = [
        "documents.read", "documents.create", "documents.update", "documents.delete",
        "correspondents.read", "correspondents.create", "correspondents.update",
        "doctypes.read", "doctypes.create", "doctypes.update",
        "tags.read", "tags.create", "tags.update",
        "settings.read", "settings.update"
    ]
    
    permissions = {perm: user.has_permission(perm) for perm in permission_checks}
    
    # Get role details
    role_details = []
    for role in user.roles:
        role_perms = []
        if role.permissions:
            try:
                role_perms = json.loads(role.permissions)
            except:
                role_perms = []
        
        role_details.append({
            "name": role.name,
            "description": role.description,
            "permissions": role_perms
        })
    
    return {
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "roles": role_details,
        "effective_permissions": permissions
    }

@router.post("/make-admin/{username}")
def make_user_admin(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible)
):
    """Make a user an admin (use with caution!)"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {username} not found")
    
    if user.is_admin:
        return {"message": f"User {username} is already an admin"}
    
    user.is_admin = True
    db.commit()
    
    return {"message": f"User {username} is now an admin"}