"""
Logging middleware for HTTP requests and security events.
"""
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from ..utils.logging_config import log_security_event, log_performance_metric, sanitize_log_message


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log HTTP requests and responses with security context.
    """
    
    def __init__(
        self,
        app,
        log_body: bool = False,
        log_headers: bool = False,
        max_body_size: int = 1024,
        exclude_paths: set = None
    ):
        super().__init__(app)
        self.log_body = log_body
        self.log_headers = log_headers
        self.max_body_size = max_body_size
        self.exclude_paths = exclude_paths or {
            "/health",
            "/static",
            "/favicon.ico",
            "/robots.txt"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process HTTP request and log details.
        
        Args:
            request: HTTP request
            call_next: Next middleware/handler
            
        Returns:
            HTTP response
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        
        # Skip logging for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
        
        # Start timing
        start_time = time.time()
        
        # Get client information
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        # Prepare request log data
        request_data = {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_ip": client_ip,
            "user_agent": user_agent[:200],  # Truncate user agent
        }
        
        # Add headers if enabled (filter sensitive ones)
        if self.log_headers:
            filtered_headers = self._filter_headers(dict(request.headers))
            request_data["headers"] = filtered_headers
        
        # Add body if enabled and present
        if self.log_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if len(body) <= self.max_body_size:
                    # Decode and sanitize body
                    body_str = body.decode('utf-8', errors='ignore')
                    request_data["body"] = sanitize_log_message(body_str)
                else:
                    request_data["body"] = f"[TRUNCATED - Size: {len(body)} bytes]"
                
                # Re-create request with body for downstream handlers
                async def receive():
                    return {"type": "http.request", "body": body}
                request._receive = receive
                
            except Exception as e:
                request_data["body_error"] = str(e)
        
        # Log incoming request
        logger.bind(**request_data).info(f"Incoming {request.method} request to {request.url.path}")
        
        # Detect potential security issues
        self._check_security_patterns(request, request_id, client_ip, user_agent)
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Prepare response log data
            response_data = {
                "request_id": request_id,
                "status_code": response.status_code,
                "process_time_ms": round(process_time * 1000, 2),
            }
            
            # Add response headers if enabled
            if self.log_headers:
                filtered_headers = self._filter_headers(dict(response.headers))
                response_data["response_headers"] = filtered_headers
            
            # Log response
            log_level = "warning" if response.status_code >= 400 else "info"
            logger.bind(**response_data).log(
                log_level.upper(),
                f"Response {response.status_code} for {request.method} {request.url.path} in {process_time * 1000:.2f}ms"
            )
            
            # Log performance metric
            log_performance_metric(
                metric_name="http_request_duration",
                value=process_time * 1000,
                unit="ms",
                tags={
                    "method": request.method,
                    "path": request.url.path,
                    "status": str(response.status_code)
                }
            )
            
            # Log security events for failed authentication/authorization
            if response.status_code in [401, 403]:
                log_security_event(
                    event_type=f"access_denied_{response.status_code}",
                    ip_address=client_ip,
                    user_agent=user_agent,
                    details={
                        "path": request.url.path,
                        "method": request.method,
                        "request_id": request_id
                    }
                )
            
            return response
            
        except Exception as e:
            # Calculate processing time for errors
            process_time = time.time() - start_time
            
            # Log error
            logger.bind(
                request_id=request_id,
                error=str(e),
                process_time_ms=round(process_time * 1000, 2)
            ).error(f"Request failed: {request.method} {request.url.path}")
            
            # Log security event for server errors
            log_security_event(
                event_type="server_error",
                ip_address=client_ip,
                user_agent=user_agent,
                details={
                    "path": request.url.path,
                    "method": request.method,
                    "error": str(e),
                    "request_id": request_id
                }
            )
            
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.
        
        Args:
            request: HTTP request
            
        Returns:
            Client IP address
        """
        # Check for forwarded headers (proxy/load balancer)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fallback to direct client
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"
    
    def _filter_headers(self, headers: dict) -> dict:
        """
        Filter sensitive headers from logging.
        
        Args:
            headers: Request/response headers
            
        Returns:
            Filtered headers dictionary
        """
        sensitive_headers = {
            "authorization", "cookie", "x-api-key", "x-auth-token",
            "x-csrf-token", "set-cookie", "www-authenticate"
        }
        
        filtered = {}
        for key, value in headers.items():
            if key.lower() in sensitive_headers:
                filtered[key] = "[REDACTED]"
            else:
                filtered[key] = value
        
        return filtered
    
    def _check_security_patterns(
        self,
        request: Request,
        request_id: str,
        client_ip: str,
        user_agent: str
    ):
        """
        Check for common security attack patterns.
        
        Args:
            request: HTTP request
            request_id: Unique request identifier
            client_ip: Client IP address
            user_agent: User agent string
        """
        suspicious_patterns = []
        
        # Check for SQL injection patterns in query parameters
        for key, value in request.query_params.items():
            if any(pattern in value.lower() for pattern in [
                "union select", "drop table", "insert into", "delete from",
                "exec(", "script>", "javascript:", "onload=", "onerror="
            ]):
                suspicious_patterns.append(f"Suspicious query parameter: {key}")
        
        # Check for path traversal attempts
        if any(pattern in request.url.path for pattern in ["../", "..\\", "%2e%2e"]):
            suspicious_patterns.append("Path traversal attempt")
        
        # Check for common attack user agents
        suspicious_user_agents = [
            "sqlmap", "nikto", "burp", "nessus", "acunetix", "nmap",
            "masscan", "zap", "w3af", "dirb", "gobuster"
        ]
        
        if any(agent in user_agent.lower() for agent in suspicious_user_agents):
            suspicious_patterns.append("Suspicious user agent")
        
        # Check for unusual HTTP methods
        if request.method in ["TRACE", "CONNECT", "OPTIONS"] and request.url.path != "/":
            suspicious_patterns.append(f"Unusual HTTP method: {request.method}")
        
        # Log security events for suspicious patterns
        if suspicious_patterns:
            log_security_event(
                event_type="suspicious_request",
                ip_address=client_ip,
                user_agent=user_agent,
                details={
                    "patterns": suspicious_patterns,
                    "path": request.url.path,
                    "method": request.method,
                    "request_id": request_id,
                    "query_params": dict(request.query_params)
                }
            )


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add request context to all log messages.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add request context to logger.
        
        Args:
            request: HTTP request
            call_next: Next middleware/handler
            
        Returns:
            HTTP response
        """
        request_id = str(uuid.uuid4())
        
        # Add request context to all logs in this request
        with logger.contextualize(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=self._get_client_ip(request)
        ):
            response = await call_next(request)
            return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address."""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"