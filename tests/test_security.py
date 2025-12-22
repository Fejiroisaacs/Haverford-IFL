"""
Security tests for middleware and utilities.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from starlette.requests import Request
from starlette.responses import Response
from security import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    generate_csrf_token,
    verify_csrf_token,
    sanitize_html_input
)


@pytest.mark.unit
@pytest.mark.security
class TestSecurityHeaders:
    """Test security headers middleware."""

    @pytest.mark.asyncio
    async def test_security_headers_added(self):
        """Test that all security headers are added to responses."""
        middleware = SecurityHeadersMiddleware(app=None)

        mock_request = Mock(spec=Request)
        mock_request.url.hostname = 'example.com'

        async def call_next(request):
            return Response()

        response = await middleware.dispatch(mock_request, call_next)

        # Check all security headers are present
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert "Content-Security-Policy" in response.headers
        assert "Referrer-Policy" in response.headers
        assert "Permissions-Policy" in response.headers

    @pytest.mark.asyncio
    async def test_hsts_not_on_localhost(self):
        """Test HSTS header is not added for localhost."""
        middleware = SecurityHeadersMiddleware(app=None)

        mock_request = Mock(spec=Request)
        mock_request.url.hostname = 'localhost'

        async def call_next(request):
            return Response()

        response = await middleware.dispatch(mock_request, call_next)

        assert "Strict-Transport-Security" not in response.headers

    @pytest.mark.asyncio
    async def test_hsts_on_production(self):
        """Test HSTS header is added for production domains."""
        middleware = SecurityHeadersMiddleware(app=None)

        mock_request = Mock(spec=Request)
        mock_request.url.hostname = 'example.com'

        async def call_next(request):
            return Response()

        response = await middleware.dispatch(mock_request, call_next)

        assert "Strict-Transport-Security" in response.headers
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]


@pytest.mark.unit
@pytest.mark.security
class TestRateLimiting:
    """Test rate limiting middleware."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_normal_traffic(self):
        """Test that normal traffic passes through."""
        middleware = RateLimitMiddleware(app=None)

        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/test"
        mock_request.method = "GET"
        mock_request.client.host = "192.168.1.1"
        mock_request.headers.get = Mock(return_value=None)

        call_count = 0

        async def call_next(request):
            nonlocal call_count
            call_count += 1
            return Response()

        # Should allow first request
        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 200
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_excessive_requests(self):
        """Test that excessive requests are blocked."""
        middleware = RateLimitMiddleware(app=None)

        mock_request = Mock(spec=Request)
        mock_request.url.path = "/login"
        mock_request.method = "POST"
        mock_request.client.host = "192.168.1.1"
        mock_request.headers.get = Mock(return_value=None)

        async def call_next(request):
            return Response()

        # Login has limit of 5 per minute
        for i in range(5):
            response = await middleware.dispatch(mock_request, call_next)
            assert response.status_code == 200

        # 6th request should be blocked
        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.body.decode()

    @pytest.mark.asyncio
    async def test_rate_limit_includes_headers(self):
        """Test that rate limit headers are included."""
        middleware = RateLimitMiddleware(app=None)

        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/test"
        mock_request.method = "GET"
        mock_request.client.host = "192.168.1.1"
        mock_request.headers.get = Mock(return_value=None)

        async def call_next(request):
            return Response()

        response = await middleware.dispatch(mock_request, call_next)

        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers


@pytest.mark.unit
@pytest.mark.security
class TestCSRFProtection:
    """Test CSRF token generation and validation."""

    def test_generate_csrf_token(self):
        """Test CSRF token generation."""
        token1 = generate_csrf_token()
        token2 = generate_csrf_token()

        # Tokens should be unique
        assert token1 != token2

        # Tokens should be sufficient length
        assert len(token1) > 20
        assert len(token2) > 20

    def test_verify_csrf_token_valid(self):
        """Test validating a valid CSRF token."""
        token = generate_csrf_token()

        # Same token should validate
        assert verify_csrf_token(token, token) is True

    def test_verify_csrf_token_mismatch(self):
        """Test validating mismatched tokens."""
        token1 = generate_csrf_token()
        token2 = generate_csrf_token()

        assert verify_csrf_token(token1, token2) is False

    def test_verify_csrf_token_empty(self):
        """Test validation fails with empty tokens."""
        assert verify_csrf_token("", "") is False
        assert verify_csrf_token("valid", "") is False
        assert verify_csrf_token("", "valid") is False


@pytest.mark.unit
@pytest.mark.security
class TestHTMLSanitization:
    """Test HTML input sanitization."""

    def test_sanitize_basic_xss(self):
        """Test sanitization of basic XSS attempts."""
        dangerous = '<script>alert("XSS")</script>'
        safe = sanitize_html_input(dangerous)

        assert '<script>' not in safe
        assert '&lt;script&gt;' in safe

    def test_sanitize_img_onerror(self):
        """Test sanitization of img onerror XSS."""
        dangerous = '<img src=x onerror="alert(1)">'
        safe = sanitize_html_input(dangerous)

        assert '<img' not in safe
        assert '&lt;img' in safe
        assert 'onerror' in safe  # Content preserved, just escaped

    def test_sanitize_preserves_safe_text(self):
        """Test that safe text is preserved."""
        safe_text = "Hello, this is a normal message!"
        result = sanitize_html_input(safe_text)

        assert result == safe_text

    def test_sanitize_handles_quotes(self):
        """Test sanitization of quotes (for attribute injection)."""
        text = 'Text with "quotes" and \'apostrophes\''
        result = sanitize_html_input(text)

        assert '"' not in result
        assert "'" not in result
        assert '&quot;' in result
        assert '&#x27;' in result

    def test_sanitize_empty_string(self):
        """Test sanitization of empty string."""
        assert sanitize_html_input("") == ""

    def test_sanitize_none(self):
        """Test sanitization of None value."""
        assert sanitize_html_input(None) is None
