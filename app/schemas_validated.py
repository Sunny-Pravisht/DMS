"""
Extended schemas with comprehensive validation.
This module extends the base schemas with additional validation logic.
"""
import re
from pydantic import BaseModel, validator, Field

from app.schemas import (
    CorrespondentCreate, CorrespondentUpdate,
    TagCreate, TagUpdate,
    DocumentCreate, DocumentUpdate,
    SettingCreate, UserCreate, UserUpdate
)
from app.utils.validators import (
    validate_email, validate_hex_color, validate_filename, detect_sql_injection, detect_xss,
    ValidationError as ValidatorError
)


class ValidatedCorrespondentCreate(CorrespondentCreate):
    """Correspondent creation with enhanced validation"""
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        
        # Check for malicious patterns
        if detect_sql_injection(v) or detect_xss(v):
            raise ValueError("Name contains invalid characters")
        
        # Sanitize but preserve legitimate characters
        return v.strip()
    
    @validator('email')
    def validate_email_field(cls, v):
        if v:
            try:
                return validate_email(v)
            except ValidatorError as e:
                raise ValueError(str(e))
        return v
    
    @validator('address')
    def validate_address(cls, v):
        if v:
            if detect_sql_injection(v) or detect_xss(v):
                raise ValueError("Address contains invalid characters")
            return v.strip()
        return v


class ValidatedCorrespondentUpdate(CorrespondentUpdate):
    """Correspondent update with enhanced validation"""
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Name cannot be empty")
            if detect_sql_injection(v) or detect_xss(v):
                raise ValueError("Name contains invalid characters")
            return v.strip()
        return v
    
    @validator('email')
    def validate_email_field(cls, v):
        if v:
            try:
                return validate_email(v)
            except ValidatorError as e:
                raise ValueError(str(e))
        return v
    
    @validator('address')
    def validate_address(cls, v):
        if v:
            if detect_sql_injection(v) or detect_xss(v):
                raise ValueError("Address contains invalid characters")
            return v.strip()
        return v


class ValidatedTagCreate(TagCreate):
    """Tag creation with enhanced validation"""
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Tag name cannot be empty")
        
        if detect_sql_injection(v) or detect_xss(v):
            raise ValueError("Tag name contains invalid characters")
        
        # Tags should be simple identifiers
        if len(v) > 50:
            raise ValueError("Tag name too long (max 50 characters)")
        
        return v.strip().lower()
    
    @validator('color')
    def validate_color_field(cls, v):
        if v:
            try:
                return validate_hex_color(v)
            except ValidatorError as e:
                raise ValueError(str(e))
        return v


class ValidatedTagUpdate(TagUpdate):
    """Tag update with enhanced validation"""
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Tag name cannot be empty")
            if detect_sql_injection(v) or detect_xss(v):
                raise ValueError("Tag name contains invalid characters")
            if len(v) > 50:
                raise ValueError("Tag name too long (max 50 characters)")
            return v.strip().lower()
        return v
    
    @validator('color')
    def validate_color_field(cls, v):
        if v:
            try:
                return validate_hex_color(v)
            except ValidatorError as e:
                raise ValueError(str(e))
        return v


class ValidatedDocumentCreate(DocumentCreate):
    """Document creation with enhanced validation"""
    
    @validator('title')
    def validate_title(cls, v):
        if v:
            if detect_sql_injection(v) or detect_xss(v):
                raise ValueError("Title contains invalid characters")
            return v.strip()
        return v
    
    @validator('original_filename')
    def validate_filename(cls, v):
        if v:
            try:
                return validate_filename(v)
            except ValidatorError as e:
                raise ValueError(str(e))
        return v
    
    @validator('summary')
    def validate_summary(cls, v):
        if v:
            if detect_sql_injection(v) or detect_xss(v):
                raise ValueError("Summary contains invalid characters")
            # Limit summary length
            if len(v) > 1000:
                raise ValueError("Summary too long (max 1000 characters)")
            return v.strip()
        return v


class ValidatedDocumentUpdate(DocumentUpdate):
    """Document update with enhanced validation"""
    
    @validator('title')
    def validate_title(cls, v):
        if v is not None:
            if detect_sql_injection(v) or detect_xss(v):
                raise ValueError("Title contains invalid characters")
            return v.strip()
        return v
    
    @validator('summary')
    def validate_summary(cls, v):
        if v is not None:
            if detect_sql_injection(v) or detect_xss(v):
                raise ValueError("Summary contains invalid characters")
            if len(v) > 1000:
                raise ValueError("Summary too long (max 1000 characters)")
            return v.strip()
        return v


class ValidatedSettingCreate(SettingCreate):
    """Setting creation with enhanced validation"""
    
    @validator('key')
    def validate_key(cls, v):
        if not v or not v.strip():
            raise ValueError("Setting key cannot be empty")
        
        # Setting keys should be simple identifiers
        if not v.replace('_', '').replace('.', '').isalnum():
            raise ValueError("Setting key contains invalid characters")
        
        if len(v) > 100:
            raise ValueError("Setting key too long (max 100 characters)")
        
        return v.strip()
    
    @validator('value')
    def validate_value(cls, v):
        if v:
            # Validate based on common setting patterns
            if isinstance(v, str):
                # Check for malicious patterns in string values
                if detect_sql_injection(v) or detect_xss(v):
                    # Only block if it's clearly malicious, not just technical content
                    if not any(safe in v.lower() for safe in ['select', 'update', 'delete']):
                        raise ValueError("Setting value contains invalid patterns")
                
                # Limit setting value length
                if len(v) > 5000:
                    raise ValueError("Setting value too long (max 5000 characters)")
            
            # Validate JSON size if it's a dict or list
            if isinstance(v, (dict, list)):
                from app.utils.validators import validate_json_size
                try:
                    validate_json_size(v, max_size_mb=1.0)
                except ValidatorError as e:
                    raise ValueError(str(e))
        
        return v


class ValidatedUserCreate(UserCreate):
    """User creation with enhanced validation"""
    
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    
    @validator('username')
    def validate_username(cls, v):
        if not v or not v.strip():
            raise ValueError("Username cannot be empty")
        
        # Username should only contain alphanumeric, underscore, and hyphen
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Username can only contain letters, numbers, underscore, and hyphen")
        
        # Reserved usernames
        reserved = ['admin', 'root', 'system', 'api', 'test']
        if v.lower() in reserved and v != 'admin':  # Allow 'admin' for initial setup
            raise ValueError("This username is reserved")
        
        return v.strip()
    
    @validator('password')
    def validate_password(cls, v):
        if not v:
            raise ValueError("Password cannot be empty")
        
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        
        # Check password complexity
        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)
        has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in v)
        
        complexity_score = sum([has_upper, has_lower, has_digit, has_special])
        if complexity_score < 3:
            raise ValueError("Password must contain at least 3 of: uppercase, lowercase, digit, special character")
        
        return v
    
    @validator('email')
    def validate_email_field(cls, v):
        if v:
            try:
                return validate_email(v)
            except ValidatorError as e:
                raise ValueError(str(e))
        return v
    
    @validator('full_name')
    def validate_full_name(cls, v):
        if v:
            if detect_sql_injection(v) or detect_xss(v):
                raise ValueError("Full name contains invalid characters")
            if len(v) > 100:
                raise ValueError("Full name too long (max 100 characters)")
            return v.strip()
        return v


class ValidatedUserUpdate(UserUpdate):
    """User update with enhanced validation"""
    
    @validator('password')
    def validate_password(cls, v):
        if v is not None:
            if len(v) < 8:
                raise ValueError("Password must be at least 8 characters long")
            
            # Check password complexity
            has_upper = any(c.isupper() for c in v)
            has_lower = any(c.islower() for c in v)
            has_digit = any(c.isdigit() for c in v)
            has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in v)
            
            complexity_score = sum([has_upper, has_lower, has_digit, has_special])
            if complexity_score < 3:
                raise ValueError("Password must contain at least 3 of: uppercase, lowercase, digit, special character")
        
        return v
    
    @validator('email')
    def validate_email_field(cls, v):
        if v:
            try:
                return validate_email(v)
            except ValidatorError as e:
                raise ValueError(str(e))
        return v
    
    @validator('full_name')
    def validate_full_name(cls, v):
        if v is not None:
            if detect_sql_injection(v) or detect_xss(v):
                raise ValueError("Full name contains invalid characters")
            if len(v) > 100:
                raise ValueError("Full name too long (max 100 characters)")
            return v.strip()
        return v


# Search request validation
class ValidatedSearchRequest(BaseModel):
    """Validated search request"""
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    
    @validator('query')
    def validate_query(cls, v):
        if not v or not v.strip():
            raise ValueError("Search query cannot be empty")
        
        # Allow some SQL-like terms in search but sanitize
        cleaned = v.strip()
        
        # Check for obvious injection attempts
        dangerous_patterns = [
            r';\s*(drop|create|alter|exec)',
            r'--[^-]',
            r'/\*.*\*/',
            r'<script',
            r'javascript:',
            r'on\w+\s*='
        ]
        
        import re
        for pattern in dangerous_patterns:
            if re.search(pattern, cleaned, re.IGNORECASE):
                raise ValueError("Search query contains invalid patterns")
        
        return cleaned