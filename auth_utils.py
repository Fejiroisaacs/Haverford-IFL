"""
Shared authentication utilities
"""
from fastapi import Cookie
from firebase_admin import auth


async def get_current_user(session_token: str = Cookie(None)):
    """Get current user from session token. Returns None if not authenticated."""
    if not session_token:
        return None
    try:
        user = auth.verify_id_token(session_token)
        return user
    except Exception as e:
        print(f"Invalid session token: {e}")
        return None
