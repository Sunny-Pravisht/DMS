"""
Structured logging configuration with sensitive data filtering.
"""
import logging
import sys
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger
import traceback

from ..config import get_settings


# Sensitive data patterns to redact from logs
SENSITIVE_PATTERNS = [
    # Passwords and tokens
    (re.compile(r'"password":\s*"[^"]*"', re.IGNORECASE), '"password": "[REDACTED]"'),
    (re.compile(r'"token":\s*"[^"]*"', re.IGNORECASE), '"token": "[REDACTED]"'),
    (re.compile(r'"api_key":\s*"[^"]*"', re.IGNORECASE), '"api_key": "[REDACTED]"'),
    (re.compile(r'"secret":\s*"[^"]*"', re.IGNORECASE), '"secret": "[REDACTED]"'),
    (re.compile(r'"csrf_token":\s*"[^"]*"', re.IGNORECASE), '"csrf_token": "[REDACTED]"'),
    
    # Email addresses (partial redaction)
    (re.compile(r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', re.IGNORECASE), 
     lambda m: f"{m.group(1)[:2]}***@{m.group(2)}"),
    
    # Session cookies
    (re.compile(r'session_token=([^;,\s]+)', re.IGNORECASE), 'session_token=[REDACTED]'),
    
    # IP addresses (partial redaction)
    (re.compile(r'\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b'), 
     lambda m: f"{m.group(1)}.{m.group(2)}.xxx.xxx"),
    
    # File paths containing usernames
    (re.compile(r'/Users/([^/\s]+)', re.IGNORECASE), '/Users/[USERNAME]'),
    (re.compile(r'C:\\\\Users\\\\([^\\\\s]+)', re.IGNORECASE), 'C:\\\\Users\\\\[USERNAME]'),
]

# Additional patterns for form data
FORM_SENSITIVE_PATTERNS = [
    (re.compile(r'password=[^&\s]*', re.IGNORECASE), 'password=[REDACTED]'),
    (re.compile(r'token=[^&\s]*', re.IGNORECASE), 'token=[REDACTED]'),
    (re.compile(r'api_key=[^&\s]*', re.IGNORECASE), 'api_key=[REDACTED]'),
]


def sanitize_log_message(message: str) -> str:
    """
    Remove sensitive data from log messages.
    
    Args:
        message: Original log message
        
    Returns:
        Sanitized log message
    """
    sanitized = message
    
    # Apply sensitive patterns
    for pattern, replacement in SENSITIVE_PATTERNS:
        if callable(replacement):
            sanitized = pattern.sub(replacement, sanitized)
        else:
            sanitized = pattern.sub(replacement, sanitized)
    
    # Apply form data patterns
    for pattern, replacement in FORM_SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    
    return sanitized


def sanitize_log_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a structured log record.
    
    Args:
        record: Log record dictionary
        
    Returns:
        Sanitized log record
    """
    sanitized = record.copy()
    
    # Sanitize message
    if 'message' in sanitized:
        sanitized['message'] = sanitize_log_message(str(sanitized['message']))
    
    # Sanitize extra fields
    sensitive_keys = ['password', 'token', 'api_key', 'secret', 'csrf_token']
    
    for key in list(sanitized.keys()):
        if key.lower() in sensitive_keys:
            sanitized[key] = '[REDACTED]'
        elif isinstance(sanitized[key], str):
            sanitized[key] = sanitize_log_message(sanitized[key])
        elif isinstance(sanitized[key], dict):
            sanitized[key] = sanitize_dict_recursive(sanitized[key])
    
    return sanitized


def sanitize_dict_recursive(data: Dict[str, Any], max_depth: int = 5) -> Dict[str, Any]:
    """
    Recursively sanitize dictionary data.
    
    Args:
        data: Dictionary to sanitize
        max_depth: Maximum recursion depth
        
    Returns:
        Sanitized dictionary
    """
    if max_depth <= 0:
        return data
    
    sanitized = {}
    sensitive_keys = ['password', 'token', 'api_key', 'secret', 'csrf_token']
    
    for key, value in data.items():
        if key.lower() in sensitive_keys:
            sanitized[key] = '[REDACTED]'
        elif isinstance(value, str):
            sanitized[key] = sanitize_log_message(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict_recursive(value, max_depth - 1)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict_recursive(item, max_depth - 1) if isinstance(item, dict)
                else sanitize_log_message(str(item)) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            sanitized[key] = value
    
    return sanitized


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter to remove sensitive data from log records.
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record to remove sensitive data.
        
        Args:
            record: Log record to filter
            
        Returns:
            True to allow the record, False to block it
        """
        # Sanitize the message
        if hasattr(record, 'msg') and record.msg:
            record.msg = sanitize_log_message(str(record.msg))
        
        # Sanitize args if present
        if hasattr(record, 'args') and record.args:
            sanitized_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    sanitized_args.append(sanitize_log_message(arg))
                elif isinstance(arg, dict):
                    sanitized_args.append(sanitize_dict_recursive(arg))
                else:
                    sanitized_args.append(arg)
            record.args = tuple(sanitized_args)
        
        return True


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Args:
            record: Log record to format
            
        Returns:
            Formatted JSON string
        """
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                          'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                          'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                          'thread', 'threadName', 'processName', 'process', 'getMessage']:
                log_data[key] = value
        
        # Sanitize the entire log data
        log_data = sanitize_log_record(log_data)
        
        return json.dumps(log_data, default=str)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_json: bool = False,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> None:
    """
    Setup comprehensive logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        enable_json: Whether to use JSON formatting
        max_file_size: Maximum log file size in bytes
        backup_count: Number of backup files to keep
    """
    # Clear existing loguru handlers
    logger.remove()
    
    # Setup log directory
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Console handler with color
    if enable_json:
        logger.add(
            sys.stderr,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            colorize=True,
            filter=lambda record: sanitize_log_message(record["message"])
        )
    else:
        logger.add(
            sys.stderr,
            level=log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
            colorize=True,
            filter=lambda record: sanitize_log_message(record["message"])
        )
    
    # File handler
    if log_file:
        if enable_json:
            # JSON format for structured logging
            logger.add(
                log_file,
                level=log_level,
                format=lambda record: json.dumps({
                    'timestamp': record['time'].isoformat(),
                    'level': record['level'].name,
                    'logger': record['name'],
                    'module': record['module'],
                    'function': record['function'],
                    'line': record['line'],
                    'message': sanitize_log_message(record['message']),
                    'extra': sanitize_dict_recursive(record.get('extra', {}))
                }, default=str),
                rotation=max_file_size,
                retention=backup_count,
                compression="gz"
            )
        else:
            # Standard format
            logger.add(
                log_file,
                level=log_level,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
                rotation=max_file_size,
                retention=backup_count,
                compression="gz",
                filter=lambda record: sanitize_log_message(record["message"])
            )
    
    # Intercept standard logging
    intercept_standard_logging()


def intercept_standard_logging():
    """
    Intercept standard library logging and route to loguru.
    """
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            # Get corresponding Loguru level if it exists
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Find caller from where originated the logged message
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    # Set up interception
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # Add sensitive data filter to all handlers
    sensitive_filter = SensitiveDataFilter()
    for handler in logging.root.handlers:
        handler.addFilter(sensitive_filter)


def get_audit_logger() -> logger:
    """
    Get logger specifically for audit events.
    
    Returns:
        Configured audit logger
    """
    audit_logger = logger.bind(audit=True)
    return audit_logger


def log_security_event(
    event_type: str,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """
    Log security-related events with standardized format.
    
    Args:
        event_type: Type of security event
        user_id: User ID involved in the event
        ip_address: IP address of the request
        user_agent: User agent string
        details: Additional event details
    """
    # Sanitize IP address
    sanitized_ip = None
    if ip_address:
        ip_pattern = re.compile(r'\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b')
        match = ip_pattern.match(ip_address)
        if match:
            sanitized_ip = f"{match.group(1)}.{match.group(2)}.xxx.xxx"
    
    security_logger = logger.bind(
        security_event=True,
        event_type=event_type,
        user_id=user_id,
        ip_address=sanitized_ip,
        user_agent=user_agent[:100] if user_agent else None,  # Truncate user agent
        details=sanitize_dict_recursive(details or {})
    )
    
    security_logger.info(f"Security event: {event_type}")


def log_performance_metric(
    metric_name: str,
    value: float,
    unit: str = "ms",
    tags: Optional[Dict[str, str]] = None
):
    """
    Log performance metrics.
    
    Args:
        metric_name: Name of the metric
        value: Metric value
        unit: Unit of measurement
        tags: Additional tags for the metric
    """
    perf_logger = logger.bind(
        performance=True,
        metric_name=metric_name,
        value=value,
        unit=unit,
        tags=tags or {}
    )
    
    perf_logger.info(f"Performance metric: {metric_name} = {value}{unit}")


def configure_application_logging():
    """
    Configure logging for the entire application.
    """
    try:
        # Get settings (use defaults if not available)
        try:
            settings = get_settings()
            log_level = getattr(settings, 'log_level', 'INFO')
            enable_json = getattr(settings, 'log_json_format', False)
        except (AttributeError, ImportError):
            log_level = 'INFO'
            enable_json = False
        
        # Setup logging
        setup_logging(
            log_level=log_level,
            log_file="data/logs/application.log",
            enable_json=enable_json
        )
        
        # Log startup
        logger.info("Logging system initialized", 
                   log_level=log_level, 
                   json_format=enable_json)
        
        # Log security notice
        log_security_event(
            event_type="application_start",
            details={"log_level": log_level, "json_format": enable_json}
        )
        
    except Exception as e:
        # Fallback to basic logging
        setup_logging(log_level="INFO", log_file="data/logs/application.log")
        logger.error(f"Failed to configure advanced logging: {e}")


# Test function to verify sanitization
def test_sanitization():
    """Test the sanitization functions with sample data."""
    test_data = {
        'password': 'secret123',
        'email': 'user@example.com',
        'api_key': 'sk-1234567890abcdef',
        'message': 'User john@doe.com logged in with password secret123',
        'nested': {
            'token': 'bearer-token-here',
            'data': 'normal data'
        }
    }
    
    sanitized = sanitize_dict_recursive(test_data)
    logger.info("Sanitization test", original=test_data, sanitized=sanitized)