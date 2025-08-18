from fastapi import Request, Form, APIRouter, Depends, Cookie, HTTPException
from firebase_admin import auth, db
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, RedirectResponse
from models.fantasy import FantasyUser, FantasyService
from datetime import datetime
import urllib.parse
from functools import lru_cache
import time

router = APIRouter()
templates = Jinja2Templates(directory="templates")

fantasy_service = FantasyService()

_players_cache = {"data": None, "timestamp": 0}
_teams_cache = {"data": None, "timestamp": 0}
CACHE_DURATION = 300  # 5 minutes

def get_current_user(session_token: str = Cookie(None)):
    if not session_token:
        raise HTTPException(status_code=303, detail="Not authenticated", headers={"Location": "/login"})
    try:
        user = auth.verify_id_token(session_token)
        return user
    except Exception as e:
        print("Invalid session token:", str(e))
        raise HTTPException(status_code=303, detail="Not authenticated", headers={"Location": "/login"})

def get_cached_players():
    """Get all players with caching to reduce database calls"""
    current_time = time.time()
    
    if (_players_cache["data"] is None or 
        current_time - _players_cache["timestamp"] > CACHE_DURATION):
        
        _players_cache["data"] = fantasy_service.get_all_players()
        _players_cache["timestamp"] = current_time
        print("Refreshed players cache")
    
    return _players_cache["data"]

def get_cached_teams():
    """Get all teams with caching"""
    current_time = time.time()
    
    if (_teams_cache["data"] is None or 
        current_time - _teams_cache["timestamp"] > CACHE_DURATION):
        
        all_players = get_cached_players()
        _teams_cache["data"] = sorted(list(set(
            player.get('Team', 'Unknown') 
            for player in all_players 
            if player.get('Team')
        )))
        _teams_cache["timestamp"] = current_time
        print("Refreshed teams cache")
    
    return _teams_cache["data"]

@router.get("/fantasy", response_class=HTMLResponse)
async def fantasy_home(request: Request, user: dict = Depends(get_current_user), error: str = None, success: str = None):
    """Main fantasy page - shows different views based on user's team status"""
    fantasy_user = FantasyUser.load_from_firebase(user['user_id'], user.get('name', 'User'))
    current_week = db.reference('Fantasy').child('current_week').child('Week').get() or 1
    
    all_players = get_cached_players()
    teams = get_cached_teams()
    
    context = {
        "request": request, 
        "user": user, 
        "fantasy_user": fantasy_user,
        "current_week": current_week,
        "all_players": all_players,
        "teams": teams,
        "has_team": bool(fantasy_user.team.all_players),
        "has_starting_team": bool(fantasy_user.team.current_team),
        "players_data": get_user_players_data(fantasy_user),
        "error": error,  # Pass error message to template
        "success": success  # Pass success message to template
    }
    
    return templates.TemplateResponse("fantasy.html", context)

@router.post("/fantasy/create-team")
async def create_team(
    request: Request, 
    user: dict = Depends(get_current_user),
    selected_players: str = Form(...)
):
    """Create initial fantasy team"""
    fantasy_user = FantasyUser.load_from_firebase(user['user_id'], user.get('name', 'User'))
    
    try:
        player_names = [name.strip() for name in selected_players.split(',') if name.strip()]
        
        is_valid, message = fantasy_service.validate_team_creation(player_names, fantasy_user.total_balance)
        
        if not is_valid:
            all_players = fantasy_service.get_all_players()
            teams = sorted(list(set(player.get('Team', 'Unknown') for player in all_players if player.get('Team'))))
            context = {
                "request": request,
                "user": user,
                "fantasy_user": fantasy_user,
                "all_players": all_players,
                "teams": teams,
                "error": message,
                "has_team": False,
                "has_starting_team": False
            }
            return templates.TemplateResponse("fantasy.html", context)
        
        players_data = fantasy_service.get_players_by_names(player_names)
        total_cost = sum(player['Fantasy Cost'] for player in players_data)
        
        fantasy_user.team.all_players = player_names
        fantasy_user.total_balance -= total_cost
        fantasy_user.save_to_firebase()
        
        log_user_action(user['user_id'], "Team created", f"Players: {', '.join(player_names)}")
        
        success_message = urllib.parse.quote("Team created successfully! Now select your starting 5.")
        return RedirectResponse(url=f"/fantasy?success={success_message}", status_code=303)
        
    except Exception as e:
        print(f"Error creating team: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy?error={error_message}", status_code=303)

@router.post("/fantasy/select-weekly-team")
async def select_weekly_team(
    request: Request,
    user: dict = Depends(get_current_user),
    starting_team: str = Form(...)
):
    """Select starting team for the week"""
    fantasy_user = FantasyUser.load_from_firebase(user['user_id'], user.get('name', 'User'))
    
    try:
        starting_players = [name.strip() for name in starting_team.split(',') if name.strip()]
        
        is_valid, message = fantasy_service.validate_weekly_team(starting_players, fantasy_user.team.all_players)
        
        if not is_valid:
            all_players = fantasy_service.get_all_players()
            teams = sorted(list(set(player.get('Team', 'Unknown') for player in all_players if player.get('Team'))))
            context = {
                "request": request,
                "user": user,
                "fantasy_user": fantasy_user,
                "all_players": all_players,
                "teams": teams,
                "error": message,
                "has_team": True,
                "has_starting_team": bool(fantasy_user.team.current_team),
                "players_data": get_user_players_data(fantasy_user)
            }
            return templates.TemplateResponse("fantasy.html", context)
        
        fantasy_user.team.current_team = starting_players
        fantasy_user.save_to_firebase()
        
        log_user_action(user['user_id'], "Weekly team selected", f"Starting: {', '.join(starting_players)}")
        
        return RedirectResponse(url="/fantasy", status_code=303)
        
    except Exception as e:
        print(f"Error selecting weekly team: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy?error={error_message}", status_code=303)

@router.post("/fantasy/set-captain")
async def set_captain(
    request: Request,
    user: dict = Depends(get_current_user),
    captain: str = Form(...)
):
    """Set team captain"""
    fantasy_user = FantasyUser.load_from_firebase(user['user_id'], user.get('name', 'User'))
    
    try:
        captain = captain.strip()
        
        if captain not in fantasy_user.team.current_team:
            raise ValueError("Captain must be in your starting team")
        
        fantasy_user.team.captain = captain
        fantasy_user.save_to_firebase()
        
        log_user_action(user['user_id'], "Captain selected", f"Captain: {captain}")
        
        return RedirectResponse(url="/fantasy", status_code=303)
        
    except Exception as e:
        print(f"Error setting captain: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy?error={error_message}", status_code=303)

@router.post("/fantasy/make-substitution")
async def make_substitution(
    request: Request,
    user: dict = Depends(get_current_user),
    players_out: str = Form(...),
    players_in: str = Form(...)
):
    """Make substitutions between starting team and bench"""
    fantasy_user = FantasyUser.load_from_firebase(user['user_id'], user.get('name', 'User'))
    
    try:
        out_players = [name.strip() for name in players_out.split(',') if name.strip()]
        in_players = [name.strip() for name in players_in.split(',') if name.strip()]
        
        if len(out_players) != len(in_players):
            raise ValueError("Number of players in and out must match")
        
        test_starting_team = fantasy_user.team.current_team.copy()
        for player_out, player_in in zip(out_players, in_players):
            if player_out not in test_starting_team:
                raise ValueError(f"{player_out} is not in starting team")
            if player_in not in fantasy_user.team.all_players:
                raise ValueError(f"{player_in} is not in your squad")
            if player_in in test_starting_team:
                raise ValueError(f"{player_in} is already in starting team")
            
            test_starting_team.remove(player_out)
            test_starting_team.append(player_in)
        
        is_valid, message = fantasy_service.validate_weekly_team(test_starting_team, fantasy_user.team.all_players)
        
        if not is_valid:
            raise ValueError(message)
        
        fantasy_user.team.current_team = test_starting_team
        fantasy_user.save_to_firebase()
        
        log_user_action(user['user_id'], "Substitution made", 
                       f"Out: {', '.join(out_players)}, In: {', '.join(in_players)}")
        
        return RedirectResponse(url="/fantasy", status_code=303)
        
    except Exception as e:
        print(f"Error making substitution: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy?error={error_message}", status_code=303)

@router.post("/fantasy/make-transfer")
async def make_transfer(
    request: Request,
    user: dict = Depends(get_current_user),
    player_out: str = Form(...),
    player_in: str = Form(...)
):
    """Make a transfer (buy/sell player)"""
    fantasy_user = FantasyUser.load_from_firebase(user['user_id'], user.get('name', 'User'))
    
    try:
        player_out = player_out.strip()
        player_in = player_in.strip()
        
        is_valid, message = fantasy_service.validate_transfer(player_in, player_out, fantasy_user)
        
        if not is_valid:
            all_players = fantasy_service.get_all_players()
            teams = sorted(list(set(player.get('Team', 'Unknown') for player in all_players if player.get('Team'))))
            context = {
                "request": request,
                "user": user,
                "fantasy_user": fantasy_user,
                "all_players": all_players,
                "teams": teams,
                "error": message,
                "has_team": True,
                "has_starting_team": bool(fantasy_user.team.current_team),
                "players_data": get_user_players_data(fantasy_user)
            }
            return templates.TemplateResponse("fantasy.html", context)
        
        player_in_data = fantasy_service.get_player_by_name(*player_in.split(" ", 1))
        player_out_data = fantasy_service.get_player_by_name(*player_out.split(" ", 1))
        
        cost_difference = player_in_data['Fantasy Cost'] - player_out_data['Fantasy Cost']
        
        fantasy_user.team.all_players.remove(player_out)
        fantasy_user.team.all_players.append(player_in)
        fantasy_user.total_balance -= cost_difference
        
        if player_out in fantasy_user.team.current_team:
            idx = fantasy_user.team.current_team.index(player_out)
            fantasy_user.team.current_team[idx] = player_in
        
        if fantasy_user.team.captain == player_out:
            fantasy_user.team.captain = None
        
        if fantasy_user.free_transfers > 0:
            fantasy_user.free_transfers -= 1
        else:
            fantasy_user.total_points -= 4  
        
        fantasy_user.save_to_firebase()
        
        log_user_action(user['user_id'], "Transfer made", 
                       f"Out: {player_out}, In: {player_in}, Cost: {cost_difference}")
        
        return RedirectResponse(url="/fantasy", status_code=303)
        
    except Exception as e:
        print(f"Error making transfer: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy?error={error_message}", status_code=303)

def get_user_players_data(fantasy_user: FantasyUser):
    """Get formatted player data for template"""
    if not fantasy_user.team.all_players:
        return {
            'all_players': [],
            'starting_team': [],
            'bench_players': [],
            'total_value': 0
        }
    
    all_players_data = fantasy_service.get_players_by_names(fantasy_user.team.all_players)
    starting_team_data = fantasy_service.get_players_by_names(fantasy_user.team.current_team)
    bench_players_data = fantasy_service.get_players_by_names(fantasy_user.team.bench_players)
    
    return {
        'all_players': all_players_data,
        'starting_team': starting_team_data,
        'bench_players': bench_players_data,
        'total_value': sum(player['Fantasy Cost'] for player in all_players_data)
    }

def log_user_action(user_id: str, action: str, details: str):
    """Log user actions to Firebase"""
    try:
        log_ref = db.reference(f'Fantasy/UserLogs/{user_id}')
        log_ref.push({
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'details': details
        })
    except Exception as e:
        print(f"Error logging action: {e}")

@router.get("/fantasy/leaderboard", response_class=HTMLResponse)
async def fantasy_leaderboard(request: Request, user: dict = Depends(get_current_user)):
    """Show fantasy leaderboard"""
    try:
        users_ref = db.reference('Fantasy/Users')
        all_users = users_ref.get() or {}
        
        leaderboard = []
        for user_id, user_data in all_users.items():
            leaderboard.append({
                'username': user_data.get('username', 'Unknown'),
                'total_points': user_data.get('total_points', 0),
                'week_points': user_data.get('week_points', 0)
            })
        
        leaderboard.sort(key=lambda x: x['total_points'], reverse=True)
        
        context = {
            "request": request,
            "user": user,
            "leaderboard": leaderboard
        }
        
        return templates.TemplateResponse("fantasy_leaderboard.html", context)
        
    except Exception as e:
        print(f"Error loading leaderboard: {e}")
        return templates.TemplateResponse("fantasy_leaderboard.html", {
            "request": request,
            "user": user,
            "leaderboard": [],
            "error": "Error loading leaderboard"
        })

@router.get("/fantasy/api/players")
async def get_players_api(user: dict = Depends(get_current_user)):
    """API endpoint to get all players data"""
    return {"players": fantasy_service.get_all_players()}
