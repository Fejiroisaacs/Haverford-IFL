from fastapi import APIRouter, Request, Cookie
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
import pandas as pd
from functions import get_potm_match
import ast

router = APIRouter()
templates = Jinja2Templates(directory="templates")
CURRENT_SEASON = max(pd.read_csv("data/season_standings.csv")['Season'].tolist())
seasons_played = None

@router.get("/teams", response_class=HTMLResponse)
async def teams_home(request: Request, session_token: str = Cookie(None)):
    return templates.TemplateResponse("teams.html", {"request": request, "Teams": [], "count": 0})

@router.get("/teams/{team}", response_class=HTMLResponse)
async def team_page(request: Request, team: str):
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

@router.get("/teams/{team_name}/{match_details}", response_class=HTMLResponse)
async def team_page(request: Request, team_name: str, match_details: str):
    try:
        match_data = get_match_data(*match_details.split('-'))
        player_data = get_player_data(*match_details.split('-'))
        potm = get_potm_match(match_details.split('-')[-1])
        
        return templates.TemplateResponse("match.html", {"request": request, 
                                                        "match_data": match_data, 
                                                        "player_data": player_data,
                                                        "potm": potm,
                                                        "match_details": match_details.split('-')})
    except Exception as e:
        return templates.TemplateResponse("404error.html", {"request": request, 'error': str(e)})


@router.get("/team_search", response_class=HTMLResponse)
async def search_teams(request: Request, query: str):
    teams = get_teams()
    filtered_teams = [team for team in teams if query.lower() in team['Name'].lower()]
    
    return templates.TemplateResponse("teams.html", {"request": request, 
                                                     "Teams": filtered_teams, 
                                                     "count": len(filtered_teams)})

def get_standings(team):
    global seasons_played
    data = pd.read_csv("data/season_standings.csv")
    data['L5'] = data['L5'].apply(lambda x: ast.literal_eval(x))
    seasons_played = data[data['Team'] == team]['Season'].to_list()
    team_data = {}
    
    for season in seasons_played:
        sub_data = data[data['Season'] == season]
        table = None
        
        groupA = sub_data[sub_data["Group"] == 'A']
        groupB = sub_data[sub_data["Group"] == 'B']
        groupC = sub_data[sub_data["Group"] == 'C']
        
        if groupA['Team'].isin([team]).any():
            table = groupA.to_dict(orient='records')
        elif groupB['Team'].isin([team]).any():
            table = groupB.to_dict(orient='records')
        elif groupC['Team'].isin([team]).any():
            table = groupC.to_dict(orient='records')
            
        if table: team_data[season] = table
        
    return team_data

def get_matches(team):
    global seasons_played
    with open("data/Match_Results.csv") as file:
        data = pd.read_csv(file)
    match_data = {}
    
    for season in seasons_played:
        sub_data = data[data['Season'] == season]
        sub_data = sub_data[(sub_data['Team 1'] == team) | (sub_data['Team 2'] == team)].to_dict(orient='records')
        if sub_data: match_data[season] = sub_data
    return match_data

def get_match_data(team, opponent, match):
    with open("data/team_match_stats.csv") as file:
        data = pd.read_csv(file)
    
    team_data = data[(data['Team'] == team) & (data['Opponent'] == opponent) & (data['Match'] == int(match))].copy()
    opponent_data = data[(data['Team'] == opponent) & (data['Opponent'] == team) & (data['Match'] == int(match))].copy()
    
    dropped_cols = ['Season', 'Match', 'Team', 'Opponent']
    team_data.drop(dropped_cols, axis=1, inplace=True)
    opponent_data.drop(dropped_cols, axis=1, inplace=True)
    
    if team_data.shape[0] > 0 and opponent_data.shape[0] > 0: return [team_data.to_dict(orient='records')[0], opponent_data.to_dict(orient='records')[0]]

def get_teams():
    with open('data/team_ratings.csv') as file:
        data = pd.read_csv(file)
    return data.to_dict(orient='records')

def get_team(team):
    with open('data/team_ratings.csv') as file:
        data = pd.read_csv(file)
        data = data[data['Name'] == team]   
    return data.to_dict(orient='records')[0] if data.shape[0] > 0 else None

def get_players(team):
    global seasons_played
    data = pd.read_csv("data/season_player_stats.csv")
    players_data = {}
    for season in seasons_played:
        sub_data:pd.DataFrame = data[data['Season'] == str(season)]
        sub_data = sub_data[sub_data['Team'] == team]
        if sub_data.shape[0] > 0: players_data[season] = sub_data['Name'].tolist()
    return players_data

def get_player_data(team, opponent, match):
    with open("data/player_match_stats.csv") as file:
        data = pd.read_csv(file)
        
    team_data = data[(data['My Team'] == team) & (data['Match ID'] == int(match))].copy()
    opponent_data = data[(data['My Team'] == opponent) & (data['Match ID'] == int(match))].copy()
    
    dropped_cols = ['Season', 'Match ID']
    team_data.drop(dropped_cols, axis=1, inplace=True)
    opponent_data.drop(dropped_cols, axis=1, inplace=True)
    
    team_extended_data = [[], [], []] # [start, team subs, external subs]
    opponent_extended_data = [[], [], []]
    
    for player_stat in team_data.to_dict(orient='records'):
        if player_stat['External Sub'] == 'Y': team_extended_data[2].append(player_stat)
        elif player_stat['Start?'] == '0': team_extended_data[1].append(player_stat)
        else: team_extended_data[0].append(player_stat)
        
    for player_stat in opponent_data.to_dict(orient='records'):
        if player_stat['External Sub'] == 'Y': opponent_extended_data[2].append(player_stat)
        elif player_stat['Start?'] == '0': opponent_extended_data[1].append(player_stat)
        else: opponent_extended_data[0].append(player_stat)
    
    return {team: team_extended_data, opponent: opponent_extended_data}
