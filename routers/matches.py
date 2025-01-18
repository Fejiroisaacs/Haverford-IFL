from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
import pandas as pd
from fastapi import APIRouter

router = APIRouter()

templates = Jinja2Templates(directory="templates")
CURRENT_SEASON = max(pd.read_csv("data/season_standings.csv")['Season'].tolist())

@router.get("/matches", response_class=HTMLResponse)
async def read_matches(request: Request):
    return templates.TemplateResponse("matches.html", {"request": request, 
                                                       "groups": get_table(CURRENT_SEASON),
                                                       "matches_data": get_matches(CURRENT_SEASON),
                                                       "active_season": CURRENT_SEASON,
                                                       "current_season": CURRENT_SEASON})

@router.get("/matches/{season}", response_class=HTMLResponse)
async def read_matches(request: Request, season: int):
    if season <= CURRENT_SEASON and season > 0:
        return templates.TemplateResponse("matches.html", {"request": request, 
                                                        "groups": get_table(season),
                                                        "matches_data": get_matches(season),
                                                        "active_season": season,
                                                        "current_season": CURRENT_SEASON})
    else:
        return templates.TemplateResponse("matches.html", {"request": request, 
                                                        "groups": get_table(CURRENT_SEASON),
                                                        "matches_data": get_matches(CURRENT_SEASON),
                                                        "active_season": CURRENT_SEASON,
                                                        "current_season": CURRENT_SEASON})

def get_table(season):
    with open("data/season_standings.csv") as file:
        data = pd.read_csv(file)
    data = data[data['Season'] == season]
    groupA = data[data["Group"] == 'A'].to_dict(orient='records')
    groupB = data[data["Group"] == 'B'].to_dict(orient='records')
    
    return [groupA, groupB]

def get_matches(season):
    with open("data/Match_Results.csv") as file:
        data = pd.read_csv(file)
    data = data[data['Season'] == season]
    subsets = ['Playoff', 'A', 'B']
    match_data = {}
    
    for subset in subsets:
        match_data[subset] = data[data['Group'] == subset].to_dict(orient='records')
        
    return match_data
