"""
Comprehensive input validation and sanitization utilities.
"""
import re
import html
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import bleach
from urllib.parse import urlparse

# Allowed HTML tags for rich text content (if needed)
ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'a']
ALLOWED_ATTRIBUTES = {'a': ['href', 'title']}

# Regex patterns for validation
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
PHONE_PATTERN = re.compile(r'^\+?1?\d{9,15}$')
HEX_COLOR_PATTERN = re.compile(r'^#(?:[0-9a-fA-F]{3}){1,2}$')
SAFE_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9._\-\s]+$')
SQL_INJECTION_PATTERNS = [
    re.compile(r'(union|select|insert|update|delete|drop|create|alter|exec|script)', re.IGNORECASE),
    re.compile(r'(-{2}|\/\*|\*\/|;)', re.IGNORECASE),  # SQL comments and statement separator
]
XSS_PATTERNS = [
    re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
    re.compile(r'javascript:', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),  # Event handlers
    re.compile(r'<iframe', re.IGNORECASE),
    re.compile(r'<object', re.IGNORECASE),
    re.compile(r'<embed', re.IGNORECASE),
]

class ValidationError(Exception):
    """Custom validation error"""
    pass

def sanitize_html(text: str, allowed_tags: Optional[List[str]] = None, 
                  allowed_attributes: Optional[Dict[str, List[str]]] = None) -> str:
    """
    Sanitize HTML content to prevent XSS attacks.
    
    Args:
        text: Input text that may contain HTML
        allowed_tags: List of allowed HTML tags (defaults to ALLOWED_TAGS)
        allowed_attributes: Dict of allowed attributes per tag
        
    Returns:
        Sanitized HTML string
    """
    if not text:
        return ""
    
    tags = allowed_tags or ALLOWED_TAGS
    attrs = allowed_attributes or ALLOWED_ATTRIBUTES
    
    # Use bleach for HTML sanitization
    cleaned = bleach.clean(
        text,
        tags=tags,
        attributes=attrs,
        strip=True,
        strip_comments=True
    )
    
    return cleaned

def escape_html(text: str) -> str:
    """
    Escape HTML special characters to prevent XSS.
    Use this when you want to display user input as plain text.
    
    Args:
        text: Input text to escape
        
    Returns:
        HTML-escaped string
    """
    if not text:
        return ""
    return html.escape(text, quote=True)

def validate_email(email: str) -> str:
    """
    Validate and normalize email address.
    
    Args:
        email: Email address to validate
        
    Returns:
        Normalized email address
        
    Raises:
        ValidationError: If email is invalid
    """
    if not email:
        raise ValidationError("Email cannot be empty")
    
    email = email.strip().lower()
    
    if len(email) > 254:  # RFC 5321
        raise ValidationError("Email address too long")
    
    if not EMAIL_PATTERN.match(email):
        raise ValidationError("Invalid email format")
    
    return email

def validate_phone(phone: str) -> str:
    """
    Validate and normalize phone number.
    
    Args:
        phone: Phone number to validate
        
    Returns:
        Normalized phone number
        
    Raises:
        ValidationError: If phone number is invalid
    """
    if not phone:
        return ""
    
    # Remove common formatting characters
    phone = re.sub(r'[\s\-\(\).]', '', phone)
    
    if not PHONE_PATTERN.match(phone):
        raise ValidationError("Invalid phone number format")
    
    return phone

def validate_hex_color(color: str) -> str:
    """
    Validate hex color code.
    
    Args:
        color: Hex color code to validate
        
    Returns:
        Validated color code
        
    Raises:
        ValidationError: If color code is invalid
    """
    if not color:
        return ""
    
    color = color.strip()
    
    if not HEX_COLOR_PATTERN.match(color):
        raise ValidationError("Invalid hex color format")
    
    return color.lower()

def validate_safe_path(path: str, base_path: str, allow_create: bool = False) -> Path:
    """
    Validate that a path is safe and within allowed boundaries.
    Prevents path traversal attacks.
    
    Args:
        path: Path to validate
        base_path: Base directory that the path must be within
        allow_create: Whether to allow paths that don't exist yet
        
    Returns:
        Validated Path object
        
    Raises:
        ValidationError: If path is unsafe or outside boundaries
    """
    if not path:
        raise ValidationError("Path cannot be empty")
    
    # Convert to Path objects
    base = Path(base_path).resolve()
    target = Path(base_path, path).resolve()
    
    # Check if path is within base directory
    try:
        target.relative_to(base)
    except ValueError:
        raise ValidationError("Path traversal detected - access denied")
    
    # Check for suspicious patterns in the relative path
    # Use the original path parameter, not the resolved absolute path
    if '..' in path or path.startswith('/'):
        raise ValidationError("Invalid path format")
    
    # Check existence if required
    if not allow_create and not target.exists():
        raise ValidationError("Path does not exist")
    
    return target

def validate_filename(filename: str, allow_spaces: bool = True) -> str:
    """
    Validate and sanitize filename.
    
    Args:
        filename: Filename to validate
        allow_spaces: Whether to allow spaces in filename
        
    Returns:
        Sanitized filename
        
    Raises:
        ValidationError: If filename is invalid
    """
    if not filename:
        raise ValidationError("Filename cannot be empty")
    
    # Remove path components
    filename = os.path.basename(filename)
    
    # Replace spaces if not allowed
    if not allow_spaces:
        filename = filename.replace(' ', '_')
    
    # Check length
    if len(filename) > 255:
        raise ValidationError("Filename too long")
    
    # Check for safe characters
    if not SAFE_FILENAME_PATTERN.match(filename):
        # Sanitize by replacing unsafe characters
        filename = re.sub(r'[^a-zA-Z0-9._\-\s]', '_', filename)
    
    # Ensure it has an extension
    if '.' not in filename:
        raise ValidationError("Filename must have an extension")
    
    return filename

def detect_sql_injection(text: str) -> bool:
    """
    Detect potential SQL injection patterns.
    
    Args:
        text: Text to check
        
    Returns:
        True if suspicious patterns detected
    """
    if not text:
        return False
    
    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    
    return False

def detect_xss(text: str) -> bool:
    """
    Detect potential XSS patterns.
    
    Args:
        text: Text to check
        
    Returns:
        True if suspicious patterns detected
    """
    if not text:
        return False
    
    for pattern in XSS_PATTERNS:
        if pattern.search(text):
            return True
    
    return False

def validate_url(url: str, allowed_schemes: Optional[List[str]] = None) -> str:
    """
    Validate and sanitize URL.
    
    Args:
        url: URL to validate
        allowed_schemes: List of allowed URL schemes (default: ['http', 'https'])
        
    Returns:
        Validated URL
        
    Raises:
        ValidationError: If URL is invalid
    """
    if not url:
        raise ValidationError("URL cannot be empty")
    
    schemes = allowed_schemes or ['http', 'https']
    
    try:
        parsed = urlparse(url)
        
        if not parsed.scheme:
            raise ValidationError("URL must include scheme (http/https)")
        
        if parsed.scheme not in schemes:
            raise ValidationError(f"URL scheme must be one of: {', '.join(schemes)}")
        
        if not parsed.netloc:
            raise ValidationError("URL must include domain")
        
        # Check for suspicious patterns
        if detect_xss(url) or detect_sql_injection(url):
            raise ValidationError("URL contains suspicious patterns")
        
        return url
        
    except Exception as e:
        raise ValidationError(f"Invalid URL format: {str(e)}")

def sanitize_dict(data: Dict[str, Any], max_depth: int = 10) -> Dict[str, Any]:
    """
    Recursively sanitize dictionary values.
    
    Args:
        data: Dictionary to sanitize
        max_depth: Maximum recursion depth
        
    Returns:
        Sanitized dictionary
    """
    if max_depth <= 0:
        raise ValidationError("Maximum recursion depth exceeded")
    
    sanitized = {}
    
    for key, value in data.items():
        # Sanitize key
        if not isinstance(key, str):
            continue
        
        if detect_sql_injection(key) or detect_xss(key):
            continue
        
        # Sanitize value based on type
        if isinstance(value, str):
            sanitized[key] = escape_html(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, max_depth - 1)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict(item, max_depth - 1) if isinstance(item, dict)
                else escape_html(item) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            sanitized[key] = value
    
    return sanitized

def validate_json_size(data: Any, max_size_mb: float = 10.0) -> None:
    """
    Validate JSON data size to prevent DoS attacks.
    
    Args:
        data: JSON data to validate
        max_size_mb: Maximum allowed size in MB
        
    Raises:
        ValidationError: If data exceeds size limit
    """
    import json
    
    try:
        json_str = json.dumps(data)
        size_mb = len(json_str.encode('utf-8')) / (1024 * 1024)
        
        if size_mb > max_size_mb:
            raise ValidationError(f"Data size ({size_mb:.2f}MB) exceeds limit ({max_size_mb}MB)")
    except Exception as e:
        raise ValidationError(f"Invalid JSON data: {str(e)}")

def validate_pagination(offset: int, limit: int, max_limit: int = 100) -> tuple[int, int]:
    """
    Validate pagination parameters.
    
    Args:
        offset: Starting offset
        limit: Number of items to return
        max_limit: Maximum allowed limit
        
    Returns:
        Tuple of (validated_offset, validated_limit)
        
    Raises:
        ValidationError: If parameters are invalid
    """
    if offset < 0:
        raise ValidationError("Offset must be non-negative")
    
    if limit < 1:
        raise ValidationError("Limit must be at least 1")
    
    if limit > max_limit:
        raise ValidationError(f"Limit cannot exceed {max_limit}")
    
    return offset, min(limit, max_limit)