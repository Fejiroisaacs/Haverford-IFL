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
                                                       "active_season": CURRENT_SEASON,
                                                       "current_season": CURRENT_SEASON})

@router.get("/matches/{season}", response_class=HTMLResponse)
async def read_matches(request: Request, season: int):
    if season <= CURRENT_SEASON and season > 0:
        return templates.TemplateResponse("matches.html", {"request": request, 
                                                        "groups": get_table(season),
                                                        "active_season": season,
                                                        "current_season": CURRENT_SEASON})
    else:
        return templates.TemplateResponse("matches.html", {"request": request, 
                                                        "groups": get_table(CURRENT_SEASON),
                                                        "active_season": CURRENT_SEASON,
                                                        "current_season": CURRENT_SEASON})

def get_table(season):
    data = pd.read_csv("data/season_standings.csv")
    data = data[data['Season'] == season]
    groupA = data[data["Group"] == 'A'].to_dict(orient='records')
    groupB = data[data["Group"] == 'B'].to_dict(orient='records')
    
    return [groupA, groupB]
    