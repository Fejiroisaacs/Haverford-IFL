from fastapi import APIRouter, Request, Cookie, Depends
from fastapi.templating import Jinja2Templates
from firebase_admin import db as firebase_db
from starlette.responses import HTMLResponse
import pandas as pd

router = APIRouter()
templates = Jinja2Templates(directory="templates")
user = None
CURRENT_SEASON = max(pd.read_csv("data/season_standings.csv")['Season'].tolist())
seasons_played = None

@router.get("/teams", response_class=HTMLResponse)
async def teams_home(request: Request, session_token: str = Cookie(None), db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    return templates.TemplateResponse("teams.html", {"request": request, "user": user, "Teams": [], "count": 0})

@router.get("/teams/{team}", response_class=HTMLResponse)
async def team_page(request: Request, team: str, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    # teams_ref = db.child('Teams')
    # team_data = teams_ref.child(team).get()
    team_data = get_team(team)
    if team_data:
        standings_data = get_standings(team)
        matches_data = get_matches(team)
        players_data = get_players(team)
        seasons_played = list(standings_data.keys())

        return templates.TemplateResponse("team.html", {
            "request": request, 
            "team": team, 
            "data": team_data,
            "standings_data": standings_data,
            "matches_data": matches_data,
            "players_data": players_data,
            "seasons_played": seasons_played
        })
    else:
        return templates.TemplateResponse("404error.html", {"request": request})

@router.get("/team_search", response_class=HTMLResponse)
async def search_teams(request: Request, query: str, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    teams = get_teams()
    filtered_teams = [team for team in teams if query.lower() in team['Name'].lower()]
    
    return templates.TemplateResponse("teams.html", {"request": request, 
                                                     "user": user, "Teams": filtered_teams, 
                                                     "count": len(filtered_teams)})

def get_standings(team):
    global seasons_played
    data = pd.read_csv("data/season_standings.csv")
    seasons_played = data[data['Team'] == team]['Season'].to_list()
    team_data = {}
    
    for season in seasons_played:
        sub_data = data[data['Season'] == season]
        table = None
        
        groupA = sub_data[sub_data["Group"] == 'A']
        groupB = sub_data[sub_data["Group"] == 'B']
        
        if groupA['Team'].isin([team]).any():
            table = groupA.to_dict(orient='records')
        elif groupB['Team'].isin([team]).any():
            table = groupB.to_dict(orient='records')
            
        if table: team_data[season] = table
        
    return team_data

def get_matches(team):
    global seasons_played
    data = pd.read_csv("data/Match_Results.csv")
    match_data = {}
    
    for season in seasons_played:
        sub_data = data[data['Season'] == season]
        sub_data = sub_data[(sub_data['Team 1'] == team) | (sub_data['Team 2'] == team)].to_dict(orient='records')
        
        if sub_data: match_data[season] = sub_data
    
    return match_data

def get_players(team):
    global seasons_played
    data = pd.read_csv("data/season_player_stats.csv")
    players_data = {}
    for season in seasons_played:
        sub_data:pd.DataFrame = data[data['Season'] == str(season)]
        sub_data = sub_data[sub_data['Team'] == team]
        if sub_data.shape[0] > 0: players_data[season] = sub_data['Name'].tolist()
    return players_data

def get_teams():
    with open('data/team_ratings.csv') as file:
        data = pd.read_csv(file)
    return data.to_dict(orient='records')

def get_team(team):
    with open('data/team_ratings.csv') as file:
        data = pd.read_csv(file)
        data = data[data['Name'] == team]
    return data.to_dict(orient='records')[0] if data.shape[0] > 0 else None