from fastapi import APIRouter, Request, Cookie, Depends
from fastapi.templating import Jinja2Templates
from firebase_admin import db
from starlette.responses import HTMLResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")
user = None

@router.get("/teams", response_class=HTMLResponse)
async def teams_home(request: Request, session_token: str = Cookie(None), db: db.Reference = Depends(lambda: db.reference('/'))):
    return templates.TemplateResponse("teams.html", {"request": request, "user": user, "Teams": [], "count": 0})

@router.get("/teams/{team}", response_class=HTMLResponse)
async def get_team(request: Request, team: str, db: db.Reference = Depends(lambda: db.reference('/'))):
    teams_ref = db.child('Teams')
    team_data = teams_ref.child(team).get()
    if team_data:
        return templates.TemplateResponse("team.html", {"request": request, "user": user, "team": team, "data": team_data})
    else:
        return templates.TemplateResponse("404error.html", {"request": request})

@router.get("/team_search", response_class=HTMLResponse)
async def search_teams(request: Request, query: str, db: db.Reference = Depends(lambda: db.reference('/'))):
    teams_ref = db.child('Teams')
    teams = teams_ref.get()
    filtered_teams = {k: v for k, v in teams.items() if query.lower() in k.lower()}
    filtered_teams = [teams[team] for team in filtered_teams]
    
    return templates.TemplateResponse("teams.html", {"request": request, "user": user, "Teams": filtered_teams, "count": len(filtered_teams)})
