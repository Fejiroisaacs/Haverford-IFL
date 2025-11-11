import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from logging_config import log_request
from urllib.parse import parse_qs, urlparse

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all HTTP requests with minimal overhead.

    Captures:
    - Route, method, status code
    - Response time
    - Client IP and user agent
    - Query parameters
    """

    async def dispatch(self, request: Request, call_next):
        # Start timer
        start_time = time.time()

        # Get request info
        route = request.url.path
        method = request.method
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get('user-agent', '')
        query_params = dict(request.query_params)

        response = None
        status_code = None
        error_details = None

        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
            error_details = None

        except Exception as e:
            # Log exceptions
            status_code = 500
            error_details = str(e)
            # Re-raise to let FastAPI handle it
            raise

        finally:
            # Calculate response time
            response_time_ms = round((time.time() - start_time) * 1000, 2)

            # Queue log entry (non-blocking)
            request_data = {
                'route': route,
                'method': method,
                'status_code': status_code,
                'response_time_ms': response_time_ms,
                'ip': client_ip,
                'user_agent': user_agent,
                'query_params': query_params,
                'error_details': error_details
            }

            # Non-blocking log call
            log_request(request_data)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP, checking for proxy headers.

        Returns anonymized IP (last octet removed for privacy).
        """
        # Check common proxy headers
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            # Get first IP in chain
            ip = forwarded_for.split(',')[0].strip()
        else:
            ip = request.client.host if request.client else 'unknown'

        # Anonymize IP (remove last octet for privacy)
        # e.g., "192.168.1.100" becomes "192.168.1.xxx"
        if ip != 'unknown' and '.' in ip:
            parts = ip.split('.')
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"

        return ip


class RateLimitLoggingMiddleware(BaseHTTPMiddleware):
    """
    Optional: Enhance rate limiting with logging.

    You can use this to track rate limit violations.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Check if rate limit was hit (429 status)
        if response.status_code == 429:
            client_ip = request.client.host if request.client else 'unknown'
            route = request.url.path

            # Log rate limit hit
            log_request({
                'route': route,
                'method': request.method,
                'status_code': 429,
                'response_time_ms': 0,
                'ip': client_ip,
                'user_agent': request.headers.get('user-agent', ''),
                'query_params': {},
                'error_details': 'Rate limit exceeded'
            })

        return response
