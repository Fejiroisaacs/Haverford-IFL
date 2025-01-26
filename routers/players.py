from fastapi import APIRouter, Request, Cookie, Depends
from fastapi.templating import Jinja2Templates
from firebase_admin import db as firebase_db
from starlette.responses import HTMLResponse
import pandas as pd
from functions import get_random_potm_images, get_player_potm

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/players", response_class=HTMLResponse)
async def read_players(request: Request, session_token: str = Cookie(None), db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    potm_images = get_random_potm_images(k=20)
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

@router.get("/player_search", response_class=HTMLResponse)
async def search_players(request: Request, query: str, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    players = get_players()
    filtered_players = [player for player in players if query.lower() in player['Name'].lower()]
    potm_images = get_random_potm_images(k=20)

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

def get_previous_matches(player):
    data = pd.read_csv('data/player_match_stats.csv')
    data = data[data['Name'] == player][['Season', 'My Team', 'Match ID', 'Opponent', 'External Sub', 'P', 'Y-R', 'POTM', 'G', 'A', 'S']]
    
    if data.shape[0] > 0:
        result = {}
        for season, group in data.groupby('Season'):
            result[season] = group.drop(columns='Season').to_dict(orient='records')
        return result
    else:
        return None