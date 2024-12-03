from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordBearer
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import firebase_admin
from fastapi.responses import RedirectResponse
from starlette.responses import HTMLResponse, RedirectResponse
import pyrebase, json
from fastapi import APIRouter

router = APIRouter()

templates = Jinja2Templates(directory="templates")
user = None
firebase_config = json.load(open("cred.json"))

firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database() 
teams = db.child("Teams").get()
teams = {team.key(): team.val() for team in teams}

@router.get("/teams", response_class=HTMLResponse)
async def read_players(request: Request):
    return templates.TemplateResponse("teams.html", {"request": request, "user": user, "Teams": [], "count": 0})

@router.get("/team_search", response_class=HTMLResponse)
async def search_players(request: Request, query: str):
    filtered_players = [teams[team] for team in teams if query.lower() in team.lower()]
    return templates.TemplateResponse("teams.html", {"request": request, "user": user, "Teams": filtered_players, "count": len(filtered_players)})
