from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
import pandas as pd
from fastapi import APIRouter
import ast

router = APIRouter()

templates = Jinja2Templates(directory="templates")
CURRENT_SEASON = max(pd.read_csv("data/season_standings.csv")['Season'].tolist())

@router.get("/matches", response_class=HTMLResponse)
async def read_matches(request: Request):
    return templates.TemplateResponse("matches.html", {"request": request, 
                                                       "groups": get_table(CURRENT_SEASON),
                                                       "matches_data": get_matches(CURRENT_SEASON),
                                                       "upcoming_matches_data": get_upcoming_matches(),
                                                       "active_season": CURRENT_SEASON,
                                                       "current_season": CURRENT_SEASON})

@router.get("/matches/{season}", response_class=HTMLResponse)
async def read_matches(request: Request, season: int):
    if season <= CURRENT_SEASON and season > 0:
        return templates.TemplateResponse("matches.html", {"request": request, 
                                                        "groups": get_table(season),
                                                        "matches_data": get_matches(season),
                                                        "upcoming_matches_data": get_upcoming_matches(),
                                                        "active_season": season,
                                                        "current_season": CURRENT_SEASON})
    else:
        return templates.TemplateResponse("matches.html", {"request": request, 
                                                        "groups": get_table(CURRENT_SEASON),
                                                        "matches_data": get_matches(CURRENT_SEASON),
                                                        "upcoming_matches_data": get_upcoming_matches(),
                                                        "active_season": CURRENT_SEASON,
                                                        "current_season": CURRENT_SEASON})

def get_table(season):
    with open("data/season_standings.csv") as file:
        data = pd.read_csv(file)
        data['L5'] = data['L5'].apply(lambda x: ast.literal_eval(x))
    data = data[data['Season'] == season]
    groupA = data[data["Group"] == 'A'].to_dict(orient='records')
    groupB = data[data["Group"] == 'B'].to_dict(orient='records')
    groupC = data[data["Group"] == 'C'].to_dict(orient='records')
    
    return [groupA, groupB, groupC] if len(groupC) > 0 else [groupA, groupB]

def get_matches(season):
    with open("data/Match_Results.csv") as file:
        data = pd.read_csv(file)
    data = data[data['Season'] == season]
    subsets = ['Playoff', 'A', 'B', 'C']
    match_data = {}
    
    for subset in subsets:
        sub_data = data[data['Group'] == subset].to_dict(orient='records')
        if len(sub_data) > 0: match_data[subset] = sub_data

    return match_data

def get_upcoming_matches():
    match_dict = {}
    with open("data/F25 Futsal Schedule.csv") as file:
        data = pd.read_csv(file)[['MD', 'Team 1', 'Team 2', 'Day', 'Time']]
        
    for k, gb in data.groupby(by='MD'):
        match_dict[k] = gb.to_dict(orient='records')
    
    return {
        "Max": data['MD'].max(),
        "data": match_dict
    }