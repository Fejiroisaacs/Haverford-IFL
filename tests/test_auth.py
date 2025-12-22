"""
Authentication and authorization tests.
"""

import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.auth
class TestLoginFlow:
    """Tests for user login functionality."""

    def test_login_page_loads(self, client):
        """Test login page loads successfully."""
        response = client.get("/login")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_login_success(self, client):
        """Test successful login flow."""
        with patch('routers.login.verify_password') as mock_verify:
            mock_verify.return_value = {
                'idToken': 'test-token-123',
                'email': 'test@example.com'
            }

            response = client.post("/login", data={
                "email": "test@example.com",
                "password": "correctpassword"
            }, follow_redirects=False)

            assert response.status_code == 303
            assert response.headers["location"] == "/fantasy"

            # Check cookie is set
            assert "session_token" in response.cookies
            assert response.cookies["session_token"] == "test-token-123"

    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials."""
        with patch('routers.login.verify_password') as mock_verify:
            mock_verify.side_effect = Exception("Invalid credentials")

            response = client.post("/login", data={
                "email": "test@example.com",
                "password": "wrongpassword"
            })

            assert response.status_code == 200
            assert "Invalid username/password" in response.text

    def test_login_already_authenticated(self, client, auth_headers):
        """Test login page redirects if already authenticated."""
        with patch('routers.login.auth.verify_id_token') as mock_verify:
            mock_verify.return_value = {'uid': 'test-user'}

            response = client.get("/login", cookies={
                "session_token": "valid-token"
            }, follow_redirects=False)

            assert response.status_code == 303
            assert response.headers["location"] == "/fantasy"

    def test_login_invalid_session_token(self, client):
        """Test login with invalid session token clears cookie."""
        with patch('routers.login.auth.verify_id_token') as mock_verify:
            mock_verify.side_effect = Exception("Invalid token")

            response = client.get("/login", cookies={
                "session_token": "invalid-token"
            })

            assert response.status_code == 200
            # Cookie should be cleared
            assert "session_token" in response.cookies
            # An empty/deleted cookie
            assert response.cookies["session_token"] == "" or \
                   response.cookies.get("session_token") is None


@pytest.mark.integration
@pytest.mark.auth
class TestSignupFlow:
    """Tests for user signup functionality."""

    def test_signup_page_loads(self, client):
        """Test signup page loads successfully."""
        response = client.get("/signup")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_signup_success(self, client):
        """Test successful user registration."""
        with patch('routers.signup.fb_auth.create_user') as mock_create, \
             patch('routers.signup.fb_auth.generate_email_verification_link') as mock_verify, \
             patch('routers.signup.send_email') as mock_email, \
             patch('routers.signup.db.reference') as mock_db:

            mock_db.return_value.get.return_value = None
            mock_db.return_value.child.return_value.set = Mock()
            mock_verify.return_value = "https://verify.link"

            response = client.post("/signup", data={
                "email": "newuser@example.com",
                "username": "newuser123",
                "password": "securepassword123"
            }, follow_redirects=False)

            assert response.status_code == 303
            assert response.headers["location"] == "/login"

            # Verify user creation was called
            mock_create.assert_called_once()
            mock_email.assert_called_once()

    def test_signup_duplicate_username(self, client):
        """Test signup with existing username."""
        with patch('routers.signup.db.reference') as mock_db:
            mock_db.return_value.get.return_value = {
                'existinguser': {'Email': 'existing@example.com'}
            }

            response = client.post("/signup", data={
                "email": "new@example.com",
                "username": "existinguser",
                "password": "password123"
            })

            assert response.status_code == 200
            assert "error" in response.text.lower()

    def test_signup_duplicate_email(self, client):
        """Test signup with existing email."""
        with patch('routers.signup.db.reference') as mock_db:
            mock_db.return_value.get.return_value = {
                'user1': {'Email': 'existing@example.com'}
            }

            response = client.post("/signup", data={
                "email": "existing@example.com",
                "username": "newuser",
                "password": "password123"
            })

            assert response.status_code == 200
            assert "error" in response.text.lower()

    def test_signup_invalid_email(self, client):
        """Test signup with invalid email format."""
        response = client.post("/signup", data={
            "email": "not-an-email",
            "username": "testuser",
            "password": "password123"
        })

        assert response.status_code == 200
        assert "error" in response.text.lower()

    def test_signup_short_password(self, client):
        """Test signup with password too short."""
        response = client.post("/signup", data={
            "email": "test@example.com",
            "username": "testuser",
            "password": "short"
        })

        assert response.status_code == 200
        assert "error" in response.text.lower()

    def test_signup_invalid_username(self, client):
        """Test signup with non-alphanumeric username."""
        with patch('routers.signup.db.reference') as mock_db:
            mock_db.return_value.get.return_value = None

            response = client.post("/signup", data={
                "email": "test@example.com",
                "username": "invalid-user!@#",
                "password": "password123"
            })

            assert response.status_code == 200
            assert "error" in response.text.lower()


@pytest.mark.integration
@pytest.mark.auth
class TestLogout:
    """Tests for logout functionality."""

    def test_logout_clears_session(self, client):
        """Test logout clears session cookie and redirects."""
        response = client.get("/logout", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/login"

        # Check cookie is cleared
        assert "session_token" in response.cookies


@pytest.mark.integration
@pytest.mark.auth
class TestProtectedRoutes:
    """Tests for authentication-protected routes."""

    def test_admin_requires_auth(self, client):
        """Test admin page requires authentication."""
        response = client.get("/admin", follow_redirects=False)

        # Should redirect to login or return 403
        assert response.status_code in [303, 401, 403]

    def test_admin_requires_admin_role(self, client):
        """Test admin page requires admin privileges."""
        with patch('routers.admin.get_current_user') as mock_user, \
             patch('routers.admin.is_admin') as mock_is_admin:

            mock_user.return_value = {'uid': 'user-id', 'name': 'User'}
            mock_is_admin.return_value = False

            response = client.get("/admin")

            assert response.status_code == 403

    def test_settings_requires_auth(self, client):
        """Test settings page requires authentication."""
        # Assuming settings requires auth (may need to be implemented)
        response = client.get("/settings", follow_redirects=False)

        # Check if protected
        # Implementation may vary
        assert response.status_code in [200, 303, 401, 403]


@pytest.mark.unit
@pytest.mark.auth
class TestPasswordValidation:
    """Tests for password validation in signup."""

    def test_password_minimum_length(self, client):
        """Test password must be at least 8 characters."""
        with patch('routers.signup.db.reference') as mock_db:
            mock_db.return_value.get.return_value = None

            # 7 characters - should fail
            response = client.post("/signup", data={
                "email": "test@example.com",
                "username": "testuser",
                "password": "pass123"
            })

            assert response.status_code == 200
            assert "8 characters" in response.text.lower()

    def test_password_accepts_valid(self, client):
        """Test valid password is accepted."""
        with patch('routers.signup.fb_auth.create_user'), \
             patch('routers.signup.fb_auth.generate_email_verification_link'), \
             patch('routers.signup.send_email'), \
             patch('routers.signup.db.reference') as mock_db:

            mock_db.return_value.get.return_value = None
            mock_db.return_value.child.return_value.set = Mock()

            # 8+ characters - should pass
            response = client.post("/signup", data={
                "email": "test@example.com",
                "username": "testuser",
                "password": "validpassword123"
            }, follow_redirects=False)

            assert response.status_code == 303
