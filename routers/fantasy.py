from fastapi import Request, Form, APIRouter, Depends, Cookie, HTTPException
from firebase_admin import auth, db
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, RedirectResponse
from models.fantasy import FantasyUser, FantasyService, MiniLeague, MatchPrediction, PredictionLeaderboard
import pandas as pd
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


# ============ Mini-League Routes ============

@router.get("/fantasy/leagues", response_class=HTMLResponse)
async def leagues_home(request: Request, user: dict = Depends(get_current_user), error: str = None, success: str = None):
    """Mini-leagues home page - shows user's leagues and options to create/join"""
    user_leagues = MiniLeague.get_user_leagues(user['user_id'])
    public_leagues = MiniLeague.get_public_leagues()

    # Filter out leagues user is already a member of from public leagues
    public_leagues = [l for l in public_leagues if user['user_id'] not in l.members]

    context = {
        "request": request,
        "user": user,
        "user_leagues": user_leagues,
        "public_leagues": public_leagues[:10],  # Limit public leagues shown
        "error": urllib.parse.unquote(error) if error else None,
        "success": urllib.parse.unquote(success) if success else None
    }

    return templates.TemplateResponse("fantasy_leagues.html", context)


@router.post("/fantasy/league/create")
async def create_league(
    request: Request,
    user: dict = Depends(get_current_user),
    league_name: str = Form(...),
    description: str = Form(""),
    max_members: int = Form(20),
    is_public: bool = Form(False)
):
    """Create a new mini-league"""
    try:
        # Validate league name
        league_name = league_name.strip()
        if not league_name or len(league_name) < 3:
            raise ValueError("League name must be at least 3 characters")
        if len(league_name) > 50:
            raise ValueError("League name must be less than 50 characters")

        # Generate unique IDs
        league_id = MiniLeague.generate_league_id()
        league_code = MiniLeague.generate_league_code()

        # Create the league
        league = MiniLeague(
            league_id=league_id,
            name=league_name,
            creator_id=user['user_id'],
            creator_name=user.get('name', 'Unknown'),
            created_at=datetime.now().isoformat(),
            league_code=league_code,
            members={user['user_id']: datetime.now().isoformat()},  # Creator is first member
            max_members=min(max(5, max_members), 50),  # Between 5 and 50
            is_public=is_public,
            description=description[:200] if description else ""
        )

        league.save_to_firebase()

        log_user_action(user['user_id'], "League created", f"League: {league_name}, Code: {league_code}")

        success_message = urllib.parse.quote(f"League '{league_name}' created! Share code: {league_code}")
        return RedirectResponse(url=f"/fantasy/league/{league_id}?success={success_message}", status_code=303)

    except Exception as e:
        print(f"Error creating league: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy/leagues?error={error_message}", status_code=303)


@router.get("/fantasy/league/{league_id}", response_class=HTMLResponse)
async def league_detail(
    request: Request,
    league_id: str,
    user: dict = Depends(get_current_user),
    error: str = None,
    success: str = None
):
    """View a specific mini-league"""
    league = MiniLeague.load_from_firebase(league_id)

    if not league:
        return RedirectResponse(url="/fantasy/leagues?error=League%20not%20found", status_code=303)

    # Check if user is a member
    is_member = user['user_id'] in league.members
    is_creator = user['user_id'] == league.creator_id

    # Get leaderboard
    leaderboard = league.get_leaderboard()

    context = {
        "request": request,
        "user": user,
        "league": league,
        "is_member": is_member,
        "is_creator": is_creator,
        "leaderboard": leaderboard,
        "member_count": len(league.members),
        "error": urllib.parse.unquote(error) if error else None,
        "success": urllib.parse.unquote(success) if success else None
    }

    return templates.TemplateResponse("fantasy_league_detail.html", context)


@router.post("/fantasy/league/join")
async def join_league(
    request: Request,
    user: dict = Depends(get_current_user),
    league_code: str = Form(None),
    league_id: str = Form(None)
):
    """Join a mini-league by code or ID"""
    try:
        league = None

        if league_code:
            league = MiniLeague.find_by_code(league_code.strip().upper())
            if not league:
                raise ValueError("Invalid league code")
        elif league_id:
            league = MiniLeague.load_from_firebase(league_id)
            if not league:
                raise ValueError("League not found")
        else:
            raise ValueError("Please provide a league code")

        # Add user to league
        success, message = league.add_member(user['user_id'])

        if not success:
            raise ValueError(message)

        log_user_action(user['user_id'], "Joined league", f"League: {league.name}")

        success_message = urllib.parse.quote(f"Successfully joined '{league.name}'!")
        return RedirectResponse(url=f"/fantasy/league/{league.league_id}?success={success_message}", status_code=303)

    except Exception as e:
        print(f"Error joining league: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy/leagues?error={error_message}", status_code=303)


@router.post("/fantasy/league/{league_id}/leave")
async def leave_league(
    request: Request,
    league_id: str,
    user: dict = Depends(get_current_user)
):
    """Leave a mini-league"""
    try:
        league = MiniLeague.load_from_firebase(league_id)

        if not league:
            raise ValueError("League not found")

        success, message = league.remove_member(user['user_id'])

        if not success:
            raise ValueError(message)

        log_user_action(user['user_id'], "Left league", f"League: {league.name}")

        success_message = urllib.parse.quote(f"Successfully left '{league.name}'")
        return RedirectResponse(url=f"/fantasy/leagues?success={success_message}", status_code=303)

    except Exception as e:
        print(f"Error leaving league: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy/league/{league_id}?error={error_message}", status_code=303)


@router.post("/fantasy/league/{league_id}/delete")
async def delete_league(
    request: Request,
    league_id: str,
    user: dict = Depends(get_current_user)
):
    """Delete a mini-league (creator only)"""
    try:
        league = MiniLeague.load_from_firebase(league_id)

        if not league:
            raise ValueError("League not found")

        if league.creator_id != user['user_id']:
            raise ValueError("Only the league creator can delete the league")

        league_name = league.name
        league.delete()

        log_user_action(user['user_id'], "Deleted league", f"League: {league_name}")

        success_message = urllib.parse.quote(f"League '{league_name}' has been deleted")
        return RedirectResponse(url=f"/fantasy/leagues?success={success_message}", status_code=303)

    except Exception as e:
        print(f"Error deleting league: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy/league/{league_id}?error={error_message}", status_code=303)


@router.get("/fantasy/league/{league_id}/leaderboard")
async def league_leaderboard_api(
    league_id: str,
    user: dict = Depends(get_current_user)
):
    """API endpoint for league leaderboard"""
    league = MiniLeague.load_from_firebase(league_id)

    if not league:
        return {"error": "League not found"}

    return {"leaderboard": league.get_leaderboard()}


# ============ Match Predictions Routes ============

def get_upcoming_matches():
    """Get upcoming matches that can be predicted"""
    try:
        matches_df = pd.read_csv('data\F25 Futsal Schedule.csv')
        matches_df.columns = [col.strip() for col in matches_df.columns]

        # Get matches that haven't been played yet (no score)
        upcoming = matches_df.copy()

        if upcoming.empty:
            return []

        matches = []
        for _, row in upcoming.iterrows():
            # Use numeric Match ID for unique identification
            # This ensures same teams playing multiple times have different IDs
            match_id = str(row.get('Match ID', row.get('Match Number', '')))

            matches.append({
                'match_id': match_id,
                'home_team': row.get('Team 1', ''),
                'away_team': row.get('Team 2', ''),
                'date': row.get('Day', row.get('Date', '')),
                'time': row.get('Time', ''),
                'matchday': row.get('MD', row.get('Matchday', '')),
                'group': row.get('Group', '')
            })

        return matches
    except Exception as e:
        print(f"Error loading upcoming matches: {e}")
        return []


def get_completed_matches_with_scores():
    """Get completed matches for processing predictions"""
    try:
        matches_df = pd.read_csv('data/Match_Results.csv')
        matches_df.columns = [col.strip() for col in matches_df.columns]

        # Get matches with scores (using Score Team 1 and Score Team 2 columns)
        completed = matches_df[
            (matches_df['Score Team 1'].notna()) &
            (matches_df['Score Team 2'].notna())
        ].copy()

        matches = []
        for _, row in completed.iterrows():
            try:
                home_score = int(row.get('Score Team 1', 0))
                away_score = int(row.get('Score Team 2', 0))
            except:
                continue

            # Use numeric Match ID to match predictions
            match_id = str(row.get('Match ID', ''))

            matches.append({
                'match_id': match_id,
                'home_team': row.get('Team 1', ''),
                'away_team': row.get('Team 2', ''),
                'home_score': home_score,
                'away_score': away_score,
                'date': row.get('Date', '')
            })

        return matches
    except Exception as e:
        print(f"Error loading completed matches: {e}")
        return []


@router.get("/fantasy/predictions", response_class=HTMLResponse)
async def predictions_home(
    request: Request,
    user: dict = Depends(get_current_user),
    error: str = None,
    success: str = None
):
    """Match predictions home page"""
    # Load fantasy user for admin check
    fantasy_user = FantasyUser.load_from_firebase(user['user_id'], user.get('name', 'User'))

    # Get upcoming matches
    upcoming_matches = get_upcoming_matches()

    # Get user's predictions
    user_predictions = MatchPrediction.get_user_predictions(user['user_id'])

    # Create a set of match IDs user has already predicted
    predicted_match_ids = {p.match_id for p in user_predictions}

    # Mark which matches user has already predicted
    for match in upcoming_matches:
        match['has_prediction'] = match['match_id'] in predicted_match_ids
        if match['has_prediction']:
            pred = next((p for p in user_predictions if p.match_id == match['match_id']), None)
            if pred:
                match['user_prediction'] = {
                    'home_score': pred.predicted_home_score,
                    'away_score': pred.predicted_away_score
                }

    # Get user stats
    user_stats = PredictionLeaderboard.get_user_stats(user['user_id'])

    # Get leaderboard
    leaderboard = PredictionLeaderboard.get_leaderboard(10)

    # Get recent predictions with results
    recent_predictions = [p for p in user_predictions if p.is_processed][:10]

    context = {
        "request": request,
        "user": user,
        "fantasy_user": fantasy_user,
        "upcoming_matches": upcoming_matches,
        "user_predictions": user_predictions[:20],
        "recent_predictions": recent_predictions,
        "user_stats": user_stats,
        "leaderboard": leaderboard,
        "error": urllib.parse.unquote(error) if error else None,
        "success": urllib.parse.unquote(success) if success else None
    }

    return templates.TemplateResponse("predictions.html", context)


@router.post("/fantasy/predictions/submit")
async def submit_prediction(
    request: Request,
    user: dict = Depends(get_current_user),
    match_id: str = Form(...),
    home_team: str = Form(...),
    away_team: str = Form(...),
    home_score: int = Form(...),
    away_score: int = Form(...)
):
    """Submit a match prediction"""
    try:
        # Validate scores
        if home_score < 0 or away_score < 0:
            raise ValueError("Scores cannot be negative")
        if home_score > 20 or away_score > 20:
            raise ValueError("Scores seem unrealistic")

        # Check if user already predicted this match
        existing = MatchPrediction.get_user_prediction_for_match(user['user_id'], match_id)
        if existing:
            # Update existing prediction
            existing.predicted_home_score = home_score
            existing.predicted_away_score = away_score
            existing.predicted_at = datetime.now().isoformat()
            existing.save_to_firebase()

            log_user_action(user['user_id'], "Updated prediction",
                           f"{home_team} {home_score}-{away_score} {away_team}")

            success_message = urllib.parse.quote("Prediction updated!")
        else:
            # Create new prediction
            prediction = MatchPrediction(
                prediction_id=MatchPrediction.generate_prediction_id(),
                user_id=user['user_id'],
                username=user.get('name', 'Unknown'),
                match_id=match_id,
                home_team=home_team,
                away_team=away_team,
                predicted_home_score=home_score,
                predicted_away_score=away_score,
                predicted_at=datetime.now().isoformat()
            )
            prediction.save_to_firebase()

            # Ensure user exists in leaderboard
            PredictionLeaderboard.increment_prediction_count(user['user_id'], user.get('name', 'Unknown'))

            log_user_action(user['user_id'], "Submitted prediction",
                           f"{home_team} {home_score}-{away_score} {away_team}")

            success_message = urllib.parse.quote("Prediction submitted!")

        return RedirectResponse(url=f"/fantasy/predictions?success={success_message}", status_code=303)

    except Exception as e:
        print(f"Error submitting prediction: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy/predictions?error={error_message}", status_code=303)


@router.get("/fantasy/predictions/leaderboard", response_class=HTMLResponse)
async def predictions_leaderboard(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Full predictions leaderboard page"""
    leaderboard = PredictionLeaderboard.get_leaderboard(100)
    user_stats = PredictionLeaderboard.get_user_stats(user['user_id'])

    # Find user's position
    user_position = next(
        (entry['position'] for entry in leaderboard if entry['user_id'] == user['user_id']),
        None
    )

    context = {
        "request": request,
        "user": user,
        "leaderboard": leaderboard,
        "user_stats": user_stats,
        "user_position": user_position
    }

    return templates.TemplateResponse("predictions_leaderboard.html", context)


@router.post("/fantasy/predictions/process")
async def process_predictions(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Process predictions for completed matches (admin only)"""
    try:
        # Check if user is admin
        fantasy_user = FantasyUser.load_from_firebase(user['user_id'], user.get('name', 'User'))
        if not fantasy_user.admin:
            raise ValueError("Admin access required")

        # Get completed matches
        completed_matches = get_completed_matches_with_scores()

        processed_count = 0
        for match in completed_matches:
            # Get all unprocessed predictions for this match
            predictions = MatchPrediction.get_match_predictions(match['match_id'])

            for pred in predictions:
                if not pred.is_processed:
                    pred.process_result(match['home_score'], match['away_score'])
                    processed_count += 1

        success_message = urllib.parse.quote(f"Processed {processed_count} predictions")
        return RedirectResponse(url=f"/fantasy/predictions?success={success_message}", status_code=303)

    except Exception as e:
        print(f"Error processing predictions: {e}")
        error_message = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/fantasy/predictions?error={error_message}", status_code=303)


@router.get("/fantasy/predictions/api/matches")
async def get_predictable_matches(user: dict = Depends(get_current_user)):
    """API endpoint to get matches available for prediction"""
    return {"matches": get_upcoming_matches()}
