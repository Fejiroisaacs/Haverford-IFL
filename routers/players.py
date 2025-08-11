from fastapi import APIRouter, Request, Cookie, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from firebase_admin import db as firebase_db
from starlette.responses import HTMLResponse
import pandas as pd
from functions import get_random_potm_images, get_player_potm
import time
from collections import defaultdict

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Simple rate limiting
_api_calls = defaultdict(list)
API_RATE_LIMIT = 10  # 10 calls per minute
API_WINDOW = 60  # 60 seconds

@router.get("/players", response_class=HTMLResponse)
async def read_players(request: Request, session_token: str = Cookie(None), db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    potm_images = get_random_potm_images(k=5)
    return templates.TemplateResponse("players.html", {"request": request, 
                                                       "Players": [],
                                                       'potm_images': potm_images,
                                                       "count": 0})
    
@router.get("/players/{player}", response_class=HTMLResponse)
async def get_player(request: Request, player: str, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    player_rating_data = get_player_rating_stats(player)
    season_data = get_player_season_data(player)
    potm_images = get_player_potm(player)
    awards = get_awards(player)
    previous_matches = get_previous_matches(player)
    if player_rating_data:
        return templates.TemplateResponse("player.html", {"request": request, 
                                                          "rating_data": player_rating_data,
                                                          'potm_images': potm_images, 
                                                          'season_data': season_data,
                                                          'awards': awards,
                                                          'previous_matches': previous_matches
                                                          })
    else:
        return templates.TemplateResponse("404error.html", {"request": request, 'error': f'Player {player} not found'})

@router.get("/api/players/{player}")
async def get_player_data(player: str, request: Request, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    """API endpoint to get player data as JSON for fantasy modal"""
    
    # Simple rate limiting by IP
    client_ip = request.client.host
    current_time = time.time()
    
    # Clean old requests
    _api_calls[client_ip] = [
        call_time for call_time in _api_calls[client_ip] 
        if current_time - call_time < API_WINDOW
    ]
    
    # Check rate limit
    if len(_api_calls[client_ip]) >= API_RATE_LIMIT:
        raise HTTPException(
            status_code=429, 
            detail="Too many requests. Please try again later."
        )
    
    # Record this request
    _api_calls[client_ip].append(current_time)
    
    try:
        player = player.replace("  ", " ").strip()
        player_rating_data = get_player_rating_stats(player)
        season_data = get_player_season_data(player)
        awards = get_awards(player)
        previous_matches = get_previous_matches(player)
        
        if not player_rating_data:
            return JSONResponse(
                status_code=404,
                content={"error": f"Player {player} not found"}
            )
        
        latest_season_data = season_data[-1] if season_data else {}
        
        recent_matches = []
        if previous_matches:
            all_matches = []
            for season_matches in previous_matches.values():
                all_matches.extend(season_matches)
            recent_matches = sorted(all_matches, key=lambda x: (x.get('Season', 0), x.get('Match ID', 0)), reverse=True)[:5]
        
        response_data = {
            "name": player_rating_data.get("Name", ""),
            "team": player_rating_data.get("Latest Team", "N/A"),
            "position": player_rating_data.get("Primary Position", "N/A"),
            "overall": player_rating_data.get("OVR Rating", 0),
            "ratings": {
                "attack": player_rating_data.get("ATT Rating", 0),
                "assist": player_rating_data.get("AST Rating", 0),
                "defense": player_rating_data.get("DEF Rating", 0),
                "goalkeeping": player_rating_data.get("GLK Rating", 0)
            },
            "season_stats": {
                "goals": latest_season_data.get("Goals", 0),
                "assists": latest_season_data.get("Assists", 0),
                "saves": latest_season_data.get("Saves", 0),
                "matches_played": latest_season_data.get("MP", 0),
                "record": latest_season_data.get("Record", "N/A")
            },
            "potm_count": player_rating_data.get("POTM", 0),
            "awards": awards or [],
            "recent_matches": recent_matches
        }
        return JSONResponse(content=response_data)
        
    except Exception as e:
        print(f"Error fetching player data: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error fetching player data: {str(e)}"}
        )

@router.get("/player_search", response_class=HTMLResponse)
async def search_players(request: Request, query: str, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    players = get_players()
    filtered_players = [player for player in players if query.lower() in player['Name'].lower()]
    potm_images = get_random_potm_images(k=5)

    return templates.TemplateResponse("players.html", {"request": request, 
                                                       "Players": filtered_players,
                                                       'potm_images': potm_images, 
                                                       "count": len(filtered_players)})

def get_player_season_data(player):
    data = pd.read_csv('data/season_player_stats.csv')
    data = data[data['Name'] == player]
    data = data[data['Team'] != 0]
    
    return data.to_dict(orient='records')

def get_player_rating_stats(player):
    data = pd.read_csv('data/player_ratings.csv', na_filter=False)
    data = data[data['Name'] == player]

    return data.to_dict(orient='records')[0] if data.shape[0] > 0 else None
    
def get_players():
    data = pd.read_csv('data/player_ratings.csv')
    data.drop_duplicates(subset=['Name'])

    return data[['Name', 'Latest Team']].to_dict(orient='records')

def get_awards(player):
    data = pd.read_csv('data/IFL_Awards.csv')
    data = data[data['Name'] == player][['Award']]
    
    return data['Award'].to_list() if data.shape[0] > 0 else None

def get_previous_matches(player, season=False):
    data = pd.read_csv('data/player_match_stats.csv')
    data = data[data['Name'] == player][['Season', 'My Team', 'Match ID', 'Opponent', 'External Sub', 'P', 'Y-R', 'POTM', 'G', 'A', 'S']]
    
    if data.shape[0] > 0:
        result = {}
        for season, group in data.groupby('Season'):
            if not season:
                result[season] = group.drop(columns='Season').to_dict(orient='records')
            else:
                result[season] = group.to_dict(orient='records')
        return result
    else:
        return None