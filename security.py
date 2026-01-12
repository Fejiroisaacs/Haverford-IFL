"""
Security middleware and utilities for the Haverford IFL application.
Includes CSRF protection, security headers, and rate limiting.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from fastapi import HTTPException, Header
import secrets
import hashlib
import time
from typing import Dict, Optional
from collections import defaultdict

# CSRF token storage (use Redis in production)
_csrf_tokens: Dict[str, float] = {}
CSRF_TOKEN_EXPIRY = 3600  # 1 hour

# Rate limiting storage
_rate_limit_store = defaultdict(list)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: HTTPS enforcement
    - Content-Security-Policy: XSS prevention
    - Referrer-Policy: Privacy protection
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Enable XSS filter in older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Enforce HTTPS (only in production)
        if not request.url.hostname in ['localhost', '127.0.0.1']:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Content Security Policy - adjust based on your needs
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' cdnjs.cloudflare.com cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' cdnjs.cloudflare.com cdn.jsdelivr.net fonts.googleapis.com",
            "img-src 'self' data: https:",
            "font-src 'self' cdnjs.cloudflare.com fonts.gstatic.com data:",
            "connect-src 'self' cdn.jsdelivr.net",
            "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'"
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy (previously Feature-Policy)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware using double-submit cookie pattern.

    For state-changing operations (POST, PUT, DELETE, PATCH):
    - Validates CSRF token from request header/form matches cookie
    - Excludes certain paths (API endpoints with other auth)
    """

    EXCLUDED_PATHS = [
        "/api/feedback",  # Has its own rate limiting
        "/health",
        "/robots.txt",
        "/sitemap.xml",
        "/static/"
    ]

    async def dispatch(self, request: Request, call_next):
        # Skip CSRF for safe methods
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return await call_next(request)

        # Skip CSRF for excluded paths
        if any(request.url.path.startswith(path) for path in self.EXCLUDED_PATHS):
            return await call_next(request)

        # Get CSRF token from cookie
        csrf_cookie = request.cookies.get("csrf_token")

        # Get CSRF token from header or form
        csrf_header = request.headers.get("X-CSRF-Token")

        # If no token in header, try to get from form data
        if not csrf_header and request.headers.get("content-type") == "application/x-www-form-urlencoded":
            # Token will be validated after form parsing in route handler
            # For now, we'll allow it through and validate in routes
            return await call_next(request)

        # Validate CSRF token
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token validation failed"}
            )

        # Validate token hasn't expired
        if csrf_cookie in _csrf_tokens:
            token_time = _csrf_tokens[csrf_cookie]
            if time.time() - token_time > CSRF_TOKEN_EXPIRY:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token expired"}
                )

        return await call_next(request)


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    token = secrets.token_urlsafe(32)
    _csrf_tokens[token] = time.time()

    # Clean up expired tokens (keep only last 1000)
    if len(_csrf_tokens) > 1000:
        sorted_tokens = sorted(_csrf_tokens.items(), key=lambda x: x[1])
        _csrf_tokens.clear()
        _csrf_tokens.update(dict(sorted_tokens[-500:]))

    return token


def verify_csrf_token(token: str, cookie_token: str) -> bool:
    """Verify CSRF token matches cookie and hasn't expired."""
    if not token or not cookie_token or token != cookie_token:
        return False

    if token in _csrf_tokens:
        token_time = _csrf_tokens[token]
        if time.time() - token_time > CSRF_TOKEN_EXPIRY:
            del _csrf_tokens[token]
            return False

    return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware to prevent abuse.

    Limits:
    - 100 requests per minute per IP
    - Stricter limits for authentication endpoints
    """

    RATE_LIMITS = {
        "/login": (5, 60),  # 5 requests per minute
        "/signup": (3, 60),  # 3 requests per minute
        "/send-message": (3, 3600),  # 3 per hour
        "default": (100, 60)  # 100 per minute default
    }

    async def dispatch(self, request: Request, call_next):
        # Get client IP
        client_ip = self._get_client_ip(request)
        path = request.url.path

        # Get rate limit for this path
        limit, window = self._get_rate_limit(path)

        # Create key for rate limiting
        key = f"{client_ip}:{path}"
        current_time = time.time()

        # Clean old requests
        _rate_limit_store[key] = [
            req_time for req_time in _rate_limit_store[key]
            if current_time - req_time < window
        ]

        # Check rate limit
        if len(_rate_limit_store[key]) >= limit:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Maximum {limit} requests per {window} seconds."
                },
                headers={
                    "Retry-After": str(window)
                }
            )

        # Record this request
        _rate_limit_store[key].append(current_time)

        # Add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(limit - len(_rate_limit_store[key]))
        response.headers["X-RateLimit-Reset"] = str(int(current_time + window))

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_rate_limit(self, path: str) -> tuple:
        """Get rate limit configuration for path."""
        for rate_path, limits in self.RATE_LIMITS.items():
            if rate_path != "default" and path.startswith(rate_path):
                return limits
        return self.RATE_LIMITS["default"]


def sanitize_html_input(text: str) -> str:
    """
    Basic HTML sanitization to prevent XSS attacks.
    Removes potentially dangerous HTML tags and attributes.

    For production, consider using bleach library for more robust sanitization.
    """
    if not text:
        return text

    # Replace dangerous characters
    replacements = {
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '&': '&amp;'
    }

    for char, replacement in replacements.items():
        text = text.replace(char, replacement)

    return text
