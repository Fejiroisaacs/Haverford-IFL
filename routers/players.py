from fastapi import APIRouter, Request, Cookie, Depends
from fastapi.templating import Jinja2Templates
from firebase_admin import db
from starlette.responses import HTMLResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")
user = None
@router.get("/players", response_class=HTMLResponse)
async def read_players(request: Request, session_token: str = Cookie(None), db: db.Reference = Depends(lambda: db.reference('/'))):
    return templates.TemplateResponse("players.html", {"request": request, "user": user, "Players": [], "count": 0})
    
@router.get("/players/{player}", response_class=HTMLResponse)
async def get_player(request: Request, player: str, db: db.Reference = Depends(lambda: db.reference('/'))):
    players_ref = db.child('Players')
    player_data = players_ref.child(player).get()
    if player_data:
        return templates.TemplateResponse("player.html", {"request": request, "user": user, "player": player, "data": player_data})
    else:
        return templates.TemplateResponse("404error.html", {"request": request})

@router.get("/player_search", response_class=HTMLResponse)
async def search_players(request: Request, query: str, db: db.Reference = Depends(lambda: db.reference('/'))):
    players_ref = db.child('Players')
    players = players_ref.get()
    filtered_players = {k: v for k, v in players.items() if query.lower() in k.lower()}
    filtered_players = [players[player] for player in filtered_players]

    return templates.TemplateResponse("players.html", {"request": request, "user": user, "Players": filtered_players, "count": len(filtered_players)})
