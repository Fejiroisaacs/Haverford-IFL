from fastapi import APIRouter, Request, Cookie, Depends
from fastapi.templating import Jinja2Templates
from firebase_admin import db as firebase_db
from starlette.responses import HTMLResponse
import pandas as pd

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/players", response_class=HTMLResponse)
async def read_players(request: Request, session_token: str = Cookie(None), db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    return templates.TemplateResponse("players.html", {"request": request, "Players": [], "count": 0})
    
@router.get("/players/{player}", response_class=HTMLResponse)
async def get_player(request: Request, player: str, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    player_rating_data = get_player_rating_stats(player)
    season_data = get_player_season_data(player)
    if player_rating_data:
        return templates.TemplateResponse("player.html", {"request": request, 
                                                          "rating_data": player_rating_data,
                                                          'season_data': season_data,
                                                          })
    else:
        return templates.TemplateResponse("404error.html", {"request": request, 'error': f'Player {player} not found'})

@router.get("/player_search", response_class=HTMLResponse)
async def search_players(request: Request, query: str, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    players = get_players()
    filtered_players = [player for player in players if query.lower() in player['Name'].lower()]

    return templates.TemplateResponse("players.html", {"request": request, "Players": filtered_players, "count": len(filtered_players)})

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

    