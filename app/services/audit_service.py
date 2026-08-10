"""
Audit Service - Handles audit logging for security and compliance
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
from loguru import logger

def log_audit_event(
    db: Session,
    user_id: Optional[int],
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> None:
    """
    Log an audit event for security and compliance tracking
    
    Args:
        db: Database session
        user_id: ID of the user performing the action
        action: Action being performed (e.g., "document.upload", "user.login")
        resource_type: Type of resource being acted upon (e.g., "document", "user")
        resource_id: ID of the specific resource
        details: Additional details about the action
        ip_address: IP address of the user
        user_agent: User agent string
    """
    logger.info(f"AUDIT: {action} by user {user_id} on {resource_type}:{resource_id}")

    # Persist it. This used to log to the application log only, with the
    # database write left as a TODO - which meant the Activity Log screen had
    # nothing behind it and every audit claim the product made was unbacked.
    # An audit trail that is not written down is not an audit trail.
    try:
        import json as _json

        from ..models import AuditLog

        db.add(AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=_json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:400] or None,
        ))
        db.commit()
    except Exception as e:
        # Auditing must never break the action being audited. Roll back only
        # the audit row so the caller's own transaction is left usable.
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(f"Failed to record audit event '{action}': {e}")

def log_security_event(
    event_type: str,
    severity: str,
    message: str,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log a security-related event
    
    Args:
        event_type: Type of security event (e.g., "failed_login", "suspicious_activity")
        severity: Severity level (e.g., "low", "medium", "high", "critical")
        message: Human-readable message
        user_id: ID of the user involved (if applicable)
        ip_address: IP address involved
        details: Additional details
    """
    try:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "user_id": user_id,
            "ip_address": ip_address,
            "details": details or {}
        }
        
        # Log with appropriate level based on severity
        if severity in ["critical", "high"]:
            logger.error(f"SECURITY: {message}", extra=log_entry)
        elif severity == "medium":
            logger.warning(f"SECURITY: {message}", extra=log_entry)
        else:
            logger.info(f"SECURITY: {message}", extra=log_entry)
            
    except Exception as e:
        logger.error(f"Failed to log security event: {e}")

def log_data_access(
    user_id: int,
    resource_type: str,
    resource_id: int,
    access_type: str,
    db: Session,
    success: bool = True,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log data access events for compliance
    
    Args:
        user_id: ID of the user accessing the data
        resource_type: Type of resource (e.g., "document", "user_data")
        resource_id: ID of the specific resource
        access_type: Type of access (e.g., "read", "write", "delete")
        db: Database session
        success: Whether the access was successful
        details: Additional details
    """
    action = f"{resource_type}.{access_type}"
    if not success:
        action += ".failed"
        
    log_audit_event(
        db=db,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details
    )