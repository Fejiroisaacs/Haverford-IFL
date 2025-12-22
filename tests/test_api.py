"""
Integration tests for API endpoints.
"""

import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.api
class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check_success(self, client):
        """Test health check returns success when app is healthy."""
        with patch('app.get_cached_data') as mock_cache:
            mock_cache.return_value = {
                'schedule': Mock(),
                'last_updated': Mock()
            }

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'healthy'
            assert 'timestamp' in data
            assert 'cache_status' in data

    def test_health_check_degraded(self, client):
        """Test health check returns degraded status when cache is cold."""
        with patch('app.get_cached_data') as mock_cache:
            mock_cache.return_value = {
                'schedule': None,
                'last_updated': None
            }

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'degraded'

    def test_health_check_unhealthy(self, client):
        """Test health check returns unhealthy on exception."""
        with patch('app.get_cached_data') as mock_cache:
            mock_cache.side_effect = Exception("Database error")

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'unhealthy'
            assert 'error' in data


@pytest.mark.integration
@pytest.mark.api
class TestStaticEndpoints:
    """Tests for static endpoints."""

    def test_robots_txt(self, client):
        """Test robots.txt is accessible."""
        response = client.get("/robots.txt")

        assert response.status_code == 200
        assert "User-agent" in response.text
        assert "Allow" in response.text

    def test_sitemap_xml(self, client):
        """Test sitemap.xml is accessible."""
        response = client.get("/sitemap.xml")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/xml; charset=utf-8"
        assert "<urlset" in response.text
        assert "<loc>" in response.text


@pytest.mark.integration
@pytest.mark.api
class TestHomepage:
    """Tests for homepage endpoint."""

    def test_homepage_loads(self, client):
        """Test homepage loads successfully."""
        with patch('app.get_season_progress') as mock_progress, \
             patch('app.get_next_matchday') as mock_matchday, \
             patch('app.get_group_leaders') as mock_leaders, \
             patch('app.get_latest_results') as mock_results, \
             patch('app.get_season_stats') as mock_stats, \
             patch('app.get_season_top_performers') as mock_performers:

            # Mock all dashboard data functions
            mock_progress.return_value = {'current_matchday': 1, 'total_matchdays': 10}
            mock_matchday.return_value = {'matchday': 2, 'matches': []}
            mock_leaders.return_value = {'A': [], 'B': [], 'C': []}
            mock_results.return_value = []
            mock_stats.return_value = {'total_goals': 0}
            mock_performers.return_value = {'scorers': [], 'assisters': [], 'goalkeepers': []}

            response = client.get("/")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]


@pytest.mark.integration
@pytest.mark.api
class TestRateLimiting:
    """Tests for rate limiting on various endpoints."""

    def test_login_rate_limit(self, client, reset_rate_limits):
        """Test login endpoint has rate limiting."""
        # Login limit is 5 per minute
        for i in range(5):
            response = client.post("/login", data={
                "email": "test@example.com",
                "password": "password"
            })
            # May fail authentication, but shouldn't be rate limited
            assert response.status_code in [200, 303, 422]

        # 6th request should be rate limited
        response = client.post("/login", data={
            "email": "test@example.com",
            "password": "password"
        })

        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()['detail']

    def test_contact_form_rate_limit(self, client, reset_rate_limits):
        """Test contact form has rate limiting."""
        # Contact form limit is 3 per hour
        for i in range(3):
            response = client.post("/send-message", data={
                "email": "test@example.com",
                "textarea": "Test message"
            })
            assert response.status_code in [200, 422]

        # 4th request should be rate limited
        response = client.post("/send-message", data={
            "email": "test@example.com",
            "textarea": "Test message"
        })

        assert response.status_code == 429


@pytest.mark.integration
@pytest.mark.security
class TestSecurityHeaders:
    """Test security headers are present in responses."""

    def test_security_headers_on_homepage(self, client):
        """Test security headers are present on homepage."""
        with patch('app.get_season_progress'), \
             patch('app.get_next_matchday'), \
             patch('app.get_group_leaders'), \
             patch('app.get_latest_results'), \
             patch('app.get_season_stats'), \
             patch('app.get_season_top_performers'):

            response = client.get("/")

            # Check security headers
            assert response.headers.get("X-Content-Type-Options") == "nosniff"
            assert response.headers.get("X-Frame-Options") == "DENY"
            assert "Content-Security-Policy" in response.headers
            assert "X-RateLimit-Limit" in response.headers

    def test_security_headers_on_api(self, client):
        """Test security headers are present on API endpoints."""
        response = client.get("/health")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"


@pytest.mark.integration
@pytest.mark.api
class TestErrorHandling:
    """Test error handling and responses."""

    def test_404_page(self, client):
        """Test 404 error page is rendered."""
        response = client.get("/nonexistent-page")

        assert response.status_code == 404

    def test_validation_error(self, client):
        """Test validation errors are handled properly."""
        # POST without required fields
        response = client.post("/login", data={})

        assert response.status_code == 422  # Validation error
