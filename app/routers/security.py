"""
Security management routes for administrators.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
from pathlib import Path

from ..database import get_db
from ..models import User
from ..services.auth_service import require_admin_flexible, require_permission_flexible
from ..config import get_settings
from ..utils.file_security import scan_directory_security, check_file_permissions
from loguru import logger

router = APIRouter()


@router.get("/scan/directories", response_model=Dict[str, List[Dict[str, str]]])
def scan_directories(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible)
):
    """Scan document directories for security issues (admin only)"""
    settings = get_settings(db)
    
    issues = {}
    
    # Scan storage directory
    storage_path = Path(settings.storage_folder)
    if storage_path.exists():
        storage_issues = scan_directory_security(storage_path)
        if storage_issues:
            issues["storage"] = storage_issues
    
    # Scan staging directory
    staging_path = Path(settings.staging_folder)
    if staging_path.exists():
        staging_issues = scan_directory_security(staging_path)
        if staging_issues:
            issues["staging"] = staging_issues
    
    # Log security scan
    from ..services.audit_service import log_audit_event
    log_audit_event(
        db=db,
        user_id=current_user.id,
        action="security.scan",
        resource_type="system",
        resource_id=None,
        details={
            "directories_scanned": ["storage", "staging"],
            "issues_found": sum(len(v) for v in issues.values())
        }
    )
    
    return issues


@router.get("/permissions/check")
def check_permissions(
    file_path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Check if current user has permission to access a file"""
    try:
        path = Path(file_path)
        
        # Validate path is within allowed directories
        settings = get_settings(db)
        allowed = False
        
        for base_dir in [settings.storage_folder, settings.staging_folder]:
            try:
                path.relative_to(Path(base_dir))
                allowed = True
                break
            except ValueError:
                continue
        
        if not allowed:
            return {
                "has_permission": False,
                "reason": "Path outside allowed directories"
            }
        
        # Check file permissions
        has_permission = check_file_permissions(path, current_user)
        
        return {
            "has_permission": has_permission,
            "user": current_user.username,
            "is_admin": current_user.is_admin,
            "file_exists": path.exists()
        }
        
    except Exception as e:
        logger.error(f"Error checking permissions: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/audit/recent-uploads")
def get_recent_uploads(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible)
):
    """Get recent file upload audit logs (admin only)"""
    from ..models import AuditLog
    
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.action == "document.upload")
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "timestamp": log.created_at,
            "details": log.details
        }
        for log in logs
    ]


@router.get("/audit/access-logs")
def get_access_logs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible)
):
    """Get recent document access logs (admin only)"""
    from ..models import AuditLog
    
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(["document.view", "document.download"]))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "resource_id": log.resource_id,
            "timestamp": log.created_at,
            "details": log.details
        }
        for log in logs
    ]


@router.post("/quarantine/{document_id}")
def quarantine_document(
    document_id: str,
    reason: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible)
):
    """Quarantine a suspicious document (admin only)"""
    from ..models import Document
    from ..utils.file_security import quarantine_file
    
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found")
    
    try:
        # Quarantine the file
        quarantine_file(file_path, reason)
        
        # Update document status
        document.ocr_status = "quarantined"
        document.ai_status = "quarantined"
        
        # Log quarantine action
        from ..services.audit_service import log_audit_event
        log_audit_event(
            db=db,
            user_id=current_user.id,
            action="document.quarantine",
            resource_type="document", 
            resource_id=document_id,
            details={
                "filename": document.original_filename,
                "reason": reason
            }
        )
        
        db.commit()
        
        return {
            "message": "Document quarantined successfully",
            "document_id": document_id,
            "reason": reason
        }
        
    except Exception as e:
        logger.error(f"Failed to quarantine document: {e}")
        raise HTTPException(status_code=500, detail=str(e))