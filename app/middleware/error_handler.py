"""
Global error handling middleware and exception handlers.
"""
import traceback
from typing import Union
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from loguru import logger
from datetime import datetime

from ..utils.logging_config import log_security_event


class ErrorHandler:
    """
    Global error handler for the application.
    """
    
    @staticmethod
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """
        Handle HTTP exceptions with user-friendly messages.
        
        Args:
            request: FastAPI request object
            exc: HTTP exception
            
        Returns:
            JSON response with error details
        """
        # Log the error with full details for 500 errors
        if exc.status_code == 500:
            logger.error(
                f"HTTP 500 error on {request.method} {request.url.path}",
                status_code=exc.status_code,
                detail=exc.detail,
                headers=dict(request.headers) if hasattr(request, 'headers') else {},
                exc_info=True  # This will log the full traceback
            )
        else:
            logger.error(
                f"HTTP {exc.status_code} error on {request.method} {request.url.path}",
                status_code=exc.status_code,
                detail=exc.detail,
                headers=dict(request.headers) if hasattr(request, 'headers') else {}
            )
        
        # Log security events for certain status codes
        if exc.status_code in [401, 403, 429]:
            log_security_event(
                event_type=f"http_error_{exc.status_code}",
                ip_address=request.client.host if hasattr(request, 'client') and request.client else None,
                user_agent=request.headers.get("user-agent"),
                details={
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": exc.status_code,
                    "detail": str(exc.detail)
                }
            )
        
        # Create user-friendly error messages
        user_messages = {
            400: "Bad Request - The request contains invalid data.",
            401: "Authentication Required - Please log in to access this resource.",
            403: "Access Forbidden - You don't have permission to access this resource.",
            404: "Not Found - The requested resource could not be found.",
            405: "Method Not Allowed - This HTTP method is not allowed for this endpoint.",
            409: "Conflict - The request conflicts with the current state of the resource.",
            422: "Validation Error - The submitted data contains errors.",
            429: "Too Many Requests - Please slow down and try again later.",
            500: "Internal Server Error - Something went wrong on our end.",
            502: "Bad Gateway - The server received an invalid response.",
            503: "Service Unavailable - The service is temporarily unavailable.",
            504: "Gateway Timeout - The server took too long to respond."
        }
        
        user_message = user_messages.get(exc.status_code, "An error occurred while processing your request.")
        
        # Include original detail for debugging in non-production
        error_response = {
            "error": {
                "status_code": exc.status_code,
                "message": user_message,
                "detail": exc.detail if exc.status_code != 500 else "Internal server error",
                "path": request.url.path,
                "method": request.method,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response,
            headers=getattr(exc, 'headers', None)
        )
    
    @staticmethod
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """
        Handle Pydantic validation errors with detailed field information.
        
        Args:
            request: FastAPI request object
            exc: Validation exception
            
        Returns:
            JSON response with validation error details
        """
        # Log validation error
        logger.warning(
            f"Validation error on {request.method} {request.url.path}",
            errors=exc.errors(),
            body=await request.body() if hasattr(request, 'body') else None
        )
        
        # Format validation errors for user
        formatted_errors = []
        for error in exc.errors():
            field_path = " -> ".join(str(x) for x in error["loc"])
            formatted_errors.append({
                "field": field_path,
                "message": error["msg"],
                "type": error["type"],
                "input": error.get("input")
            })
        
        error_response = {
            "error": {
                "status_code": 422,
                "message": "Validation failed for the submitted data.",
                "detail": "Please check the highlighted fields and try again.",
                "validation_errors": formatted_errors,
                "path": request.url.path,
                "method": request.method,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response
        )
    
    @staticmethod
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Handle unexpected exceptions with proper logging and user-friendly messages.
        
        Args:
            request: FastAPI request object
            exc: General exception
            
        Returns:
            JSON response with error information
        """
        # Log the full exception with traceback
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            traceback=traceback.format_exc(),
            request_headers=dict(request.headers) if hasattr(request, 'headers') else {}
        )
        
        # Log as security event (potential attack or system issue)
        log_security_event(
            event_type="unhandled_exception",
            ip_address=request.client.host if hasattr(request, 'client') and request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={
                "path": request.url.path,
                "method": request.method,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:500]  # Truncate for security
            }
        )
        
        error_response = {
            "error": {
                "status_code": 500,
                "message": "An unexpected error occurred while processing your request.",
                "detail": "Please check the server logs for more information.",
                "error_id": datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
                "path": request.url.path,
                "method": request.method,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response
        )
    
    @staticmethod
    async def starlette_exception_handler(request: Request, exc: StarletteHTTPException) -> Union[JSONResponse, HTMLResponse]:
        """
        Handle Starlette HTTP exceptions (usually from middleware).
        
        Args:
            request: FastAPI request object
            exc: Starlette HTTP exception
            
        Returns:
            JSON or HTML response based on request type
        """
        # Check if this is an API request or browser request
        content_type = request.headers.get("content-type", "")
        accept = request.headers.get("accept", "")
        
        is_api_request = (
            content_type.startswith("application/json") or
            "application/json" in accept or
            request.url.path.startswith("/api/")
        )
        
        # Log the error
        logger.error(
            f"Starlette HTTP {exc.status_code} error on {request.method} {request.url.path}",
            status_code=exc.status_code,
            detail=exc.detail
        )
        
        if is_api_request:
            # Return JSON response for API requests
            error_response = {
                "error": {
                    "status_code": exc.status_code,
                    "message": "An error occurred while processing your request.",
                    "detail": exc.detail,
                    "path": request.url.path,
                    "method": request.method,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
            return JSONResponse(
                status_code=exc.status_code,
                content=error_response
            )
        else:
            # Return HTML error page for browser requests
            return ErrorHandler.create_error_page(
                status_code=exc.status_code,
                title=f"Error {exc.status_code}",
                message=str(exc.detail),
                request=request
            )
    
    @staticmethod
    def create_error_page(status_code: int, title: str, message: str, request: Request) -> HTMLResponse:
        """
        Create a user-friendly HTML error page.
        
        Args:
            status_code: HTTP status code
            title: Error page title
            message: Error message
            request: FastAPI request object
            
        Returns:
            HTML response with error page
        """
        # Error page templates
        error_descriptions = {
            400: "The request you sent was invalid or malformed.",
            401: "You need to log in to access this page.",
            403: "You don't have permission to access this resource.",
            404: "The page you're looking for doesn't exist.",
            429: "You've made too many requests. Please slow down.",
            500: "We're experiencing technical difficulties.",
            502: "Our servers are having trouble communicating.",
            503: "The service is temporarily unavailable."
        }
        
        description = error_descriptions.get(status_code, "An unexpected error occurred.")
        
        # Determine appropriate actions based on error type
        actions = []
        if status_code == 401:
            actions.append('<a href="/login" class="btn btn-primary">Login</a>')
        elif status_code == 404:
            actions.append('<a href="/" class="btn btn-primary">Go Home</a>')
        else:
            actions.append('<a href="javascript:history.back()" class="btn btn-secondary">Go Back</a>')
            actions.append('<a href="/" class="btn btn-primary">Go Home</a>')
        
        actions_html = " ".join(actions)
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title} - Document Management System</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
            <style>
                body {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }}
                .error-container {{
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
                    padding: 3rem;
                    text-align: center;
                    max-width: 600px;
                    margin: 0 auto;
                }}
                .error-icon {{
                    font-size: 4rem;
                    color: #dc3545;
                    margin-bottom: 1.5rem;
                }}
                .error-code {{
                    font-size: 6rem;
                    font-weight: bold;
                    color: #6c757d;
                    margin: 0;
                    line-height: 1;
                }}
                .error-title {{
                    font-size: 2rem;
                    font-weight: 600;
                    color: #495057;
                    margin: 1rem 0;
                }}
                .error-description {{
                    font-size: 1.1rem;
                    color: #6c757d;
                    margin-bottom: 2rem;
                    line-height: 1.6;
                }}
                .btn {{
                    margin: 0.25rem;
                    border-radius: 10px;
                    padding: 0.75rem 1.5rem;
                    font-weight: 500;
                    text-decoration: none;
                    display: inline-block;
                }}
                .btn-primary {{
                    background: linear-gradient(45deg, #667eea, #764ba2);
                    border: none;
                    color: white;
                }}
                .btn-secondary {{
                    background: #6c757d;
                    border: none;
                    color: white;
                }}
                .btn:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
                    text-decoration: none;
                    color: white;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-container">
                    <i class="fas fa-exclamation-triangle error-icon"></i>
                    <h1 class="error-code">{status_code}</h1>
                    <h2 class="error-title">{title}</h2>
                    <p class="error-description">{description}</p>
                    <div class="error-actions">
                        {actions_html}
                    </div>
                    <hr class="my-4">
                    <small class="text-muted">
                        If this problem persists, please check the server logs.<br>
                        Error occurred at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                    </small>
                </div>
            </div>
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
        """
        
        return HTMLResponse(
            content=html_content,
            status_code=status_code
        )


# Custom exception classes
class DocumentNotFoundError(HTTPException):
    """Exception for when a document is not found"""
    def __init__(self, document_id: str):
        super().__init__(
            status_code=404,
            detail=f"Document with ID '{document_id}' not found"
        )


class InsufficientPermissionsError(HTTPException):
    """Exception for insufficient permissions"""
    def __init__(self, required_permission: str):
        super().__init__(
            status_code=403,
            detail=f"Insufficient permissions. Required: {required_permission}"
        )




class ConfigurationError(HTTPException):
    """Exception for configuration errors"""
    def __init__(self, message: str):
        super().__init__(
            status_code=500,
            detail=f"Configuration error: {message}"
        )


class ServiceUnavailableError(HTTPException):
    """Exception for when a service is unavailable"""
    def __init__(self, service_name: str):
        super().__init__(
            status_code=503,
            detail=f"Service '{service_name}' is currently unavailable"
        )