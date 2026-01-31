"""
Follow/Unfollow functionality for teams and players.
Stores follow data in Firebase at UserFollows/{user_id}/teams and UserFollows/{user_id}/players
"""

from fastapi import APIRouter, Request, Cookie, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from firebase_admin import auth, db
from typing import Optional, List, Dict
import urllib.parse

router = APIRouter()

def get_current_user_optional(session_token: str = Cookie(None)):
    """Get current user if logged in, return None if not"""
    if not session_token:
        return None
    try:
        user = auth.verify_id_token(session_token)
        return user
    except Exception:
        return None

def get_current_user_required(session_token: str = Cookie(None)):
    """Get current user, raise exception if not logged in"""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user = auth.verify_id_token(session_token)
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")


# ============ Helper Functions ============

def get_user_follows(user_id: str) -> Dict:
    """Get all follows for a user"""
    try:
        follows_ref = db.reference(f'UserFollows/{user_id}')
        follows = follows_ref.get() or {}
        return {
            'teams': follows.get('teams', []),
            'players': follows.get('players', [])
        }
    except Exception as e:
        print(f"Error getting user follows: {e}")
        return {'teams': [], 'players': []}

def is_following_team(user_id: str, team_name: str) -> bool:
    """Check if user is following a team"""
    follows = get_user_follows(user_id)
    return team_name in follows['teams']

def is_following_player(user_id: str, player_name: str) -> bool:
    """Check if user is following a player"""
    follows = get_user_follows(user_id)
    return player_name in follows['players']

def get_team_follower_count(team_name: str) -> int:
    """Get number of followers for a team"""
    try:
        followers_ref = db.reference(f'TeamFollowers/{team_name.replace("/", "_")}')
        followers = followers_ref.get() or []
        return len(followers) if isinstance(followers, list) else 0
    except Exception:
        return 0

def get_player_follower_count(player_name: str) -> int:
    """Get number of followers for a player"""
    try:
        followers_ref = db.reference(f'PlayerFollowers/{player_name.replace("/", "_").replace(".", "_")}')
        followers = followers_ref.get() or []
        return len(followers) if isinstance(followers, list) else 0
    except Exception:
        return 0


# ============ API Endpoints ============

@router.post("/api/follow/team/{team_name}")
async def follow_team(team_name: str, user: dict = Depends(get_current_user_required)):
    """Follow a team"""
    try:
        user_id = user['user_id']
        team_name = urllib.parse.unquote(team_name)

        # Get current follows
        follows_ref = db.reference(f'UserFollows/{user_id}/teams')
        current_teams = follows_ref.get() or []

        if team_name not in current_teams:
            current_teams.append(team_name)
            follows_ref.set(current_teams)

            # Update team followers (for reverse lookup)
            safe_team_name = team_name.replace("/", "_")
            followers_ref = db.reference(f'TeamFollowers/{safe_team_name}')
            followers = followers_ref.get() or []
            if user_id not in followers:
                followers.append(user_id)
                followers_ref.set(followers)

        return JSONResponse({
            "success": True,
            "following": True,
            "follower_count": get_team_follower_count(team_name)
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error following team: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@router.post("/api/unfollow/team/{team_name}")
async def unfollow_team(team_name: str, user: dict = Depends(get_current_user_required)):
    """Unfollow a team"""
    try:
        user_id = user['user_id']
        team_name = urllib.parse.unquote(team_name)

        # Get current follows
        follows_ref = db.reference(f'UserFollows/{user_id}/teams')
        current_teams = follows_ref.get() or []

        if team_name in current_teams:
            current_teams.remove(team_name)
            follows_ref.set(current_teams)

            # Update team followers
            safe_team_name = team_name.replace("/", "_")
            followers_ref = db.reference(f'TeamFollowers/{safe_team_name}')
            followers = followers_ref.get() or []
            if user_id in followers:
                followers.remove(user_id)
                followers_ref.set(followers)

        return JSONResponse({
            "success": True,
            "following": False,
            "follower_count": get_team_follower_count(team_name)
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error unfollowing team: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@router.post("/api/follow/player/{player_name}")
async def follow_player(player_name: str, user: dict = Depends(get_current_user_required)):
    """Follow a player"""
    try:
        user_id = user['user_id']
        player_name = urllib.parse.unquote(player_name)

        # Get current follows
        follows_ref = db.reference(f'UserFollows/{user_id}/players')
        current_players = follows_ref.get() or []

        if player_name not in current_players:
            current_players.append(player_name)
            follows_ref.set(current_players)

            # Update player followers
            safe_player_name = player_name.replace("/", "_").replace(".", "_")
            followers_ref = db.reference(f'PlayerFollowers/{safe_player_name}')
            followers = followers_ref.get() or []
            if user_id not in followers:
                followers.append(user_id)
                followers_ref.set(followers)

        return JSONResponse({
            "success": True,
            "following": True,
            "follower_count": get_player_follower_count(player_name)
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error following player: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@router.post("/api/unfollow/player/{player_name}")
async def unfollow_player(player_name: str, user: dict = Depends(get_current_user_required)):
    """Unfollow a player"""
    try:
        user_id = user['user_id']
        player_name = urllib.parse.unquote(player_name)

        # Get current follows
        follows_ref = db.reference(f'UserFollows/{user_id}/players')
        current_players = follows_ref.get() or []

        if player_name in current_players:
            current_players.remove(player_name)
            follows_ref.set(current_players)

            # Update player followers
            safe_player_name = player_name.replace("/", "_").replace(".", "_")
            followers_ref = db.reference(f'PlayerFollowers/{safe_player_name}')
            followers = followers_ref.get() or []
            if user_id in followers:
                followers.remove(user_id)
                followers_ref.set(followers)

        return JSONResponse({
            "success": True,
            "following": False,
            "follower_count": get_player_follower_count(player_name)
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error unfollowing player: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@router.get("/api/user/follows")
async def get_my_follows(user: dict = Depends(get_current_user_required)):
    """Get current user's follows"""
    try:
        follows = get_user_follows(user['user_id'])
        return JSONResponse({"success": True, "follows": follows})
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting follows: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@router.get("/api/follow/status/team/{team_name}")
async def get_team_follow_status(team_name: str, user: dict = Depends(get_current_user_optional)):
    """Get follow status for a team"""
    team_name = urllib.parse.unquote(team_name)
    following = False

    if user:
        following = is_following_team(user['user_id'], team_name)

    return JSONResponse({
        "following": following,
        "follower_count": get_team_follower_count(team_name),
        "logged_in": user is not None
    })

@router.get("/api/follow/status/player/{player_name}")
async def get_player_follow_status(player_name: str, user: dict = Depends(get_current_user_optional)):
    """Get follow status for a player"""
    player_name = urllib.parse.unquote(player_name)
    following = False

    if user:
        following = is_following_player(user['user_id'], player_name)

    return JSONResponse({
        "following": following,
        "follower_count": get_player_follower_count(player_name),
        "logged_in": user is not None
    })
