from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordBearer
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
from starlette.responses import HTMLResponse, RedirectResponse
import pyrebase, json
from fastapi import APIRouter

router = APIRouter()

templates = Jinja2Templates(directory="templates")
user = None
firebase_config = json.load(open("firebase/cred.json"))

firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database() 
players = db.child("Players").get()
players = {player.key(): player.val() for player in players}
print("Doing this")

@router.get("/players", response_class=HTMLResponse)
async def read_players(request: Request):
    return templates.TemplateResponse("players.html", {"request": request, "user": user, "Players": [], "count": 0})

@router.get("/search", response_class=HTMLResponse)
async def search_players(request: Request, query: str):
    filtered_players = [players[player] for player in players if query.lower() in player.lower()]
    return templates.TemplateResponse("players.html", {"request": request, "user": user, "Players": filtered_players, "count": len(filtered_players)})