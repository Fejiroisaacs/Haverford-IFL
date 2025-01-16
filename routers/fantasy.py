from fastapi import Request, Form, APIRouter, Depends, Cookie, HTTPException
from firebase_admin import auth, db
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
from models import User

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_current_user(session_token: str = Cookie(None)):
    if not session_token:
        raise HTTPException(status_code=303, detail="Not authenticated", headers={"Location": "/login"})
    try:
        user = auth.verify_id_token(session_token)
        return user
    except Exception as e:
        print("Invalid session token:", str(e))
        raise HTTPException(status_code=303, detail="Not authenticated", headers={"Location": "/login"})

@router.get("/fantasy", response_class=HTMLResponse)
async def fantasy_loading(request: Request, user: dict = Depends(get_current_user)):
    current_week = db.reference('Fantasy').child('current_week').child('Week').get()
    return templates.TemplateResponse("fantasy.html", {"request": request, "user": user, 'data': get_user_data(user)})

@router.post("/fantasy/update-team")
async def update_team(request: Request, user: dict = Depends(get_current_user), starting_team: str = Form(...), bench: str = Form(...)):
    return templates.TemplateResponse("fantasy.html", {"request": request, "user": user, 'data': get_user_data(user)})

@router.post("/fantasy/transfer-team")
async def transfer_team(request: Request, user: dict = Depends(get_current_user), my_player: str = Form(...), new_player: str = Form(...)):
    return templates.TemplateResponse("fantasy.html", {"request": request, "user": user, 'data': get_user_data(user)})

def get_user_data(user):
    if user:
        userObject = User(user['name'], user['email'], user['email_verified'], db)
    dummy_data = {
        'Name': 'Dummy',
        'Average': 40,
        'curr_pts' : 197,
        'record': 62,
        'team': [('Rami', 25), ('Yass', 12), ('Will', 5), ('Fej', 17), ('Grant', -4)],
        'MW': 5,
        'Deadline': '1/17',
        'starting_team': [
            {'name': 'Rami', 'pos': 'F', 'team': 'NPC', 'mw_points': 8, 'total_points': 40},
            {'name': 'Yass', 'pos': 'M', 'team': 'NPC', 'mw_points': 7, 'total_points': 32},
            {'name': 'Will', 'pos': 'D', 'team': 'NPC', 'mw_points': 6, 'total_points': 28},
            {'name': 'Fej', 'pos': 'D', 'team': 'NPC', 'mw_points': 5, 'total_points': 35},
            {'name': 'Grant', 'pos': 'GK', 'team': 'NPC', 'mw_points': -1, 'total_points': -15}
        ],
        'bench': [
            {'name': 'Jake', 'pos': 'D', 'team': 'Team F', 'mw_points': 4, 'total_points': 20},
            {'name': 'Leon', 'pos': 'M', 'team': 'Team G', 'mw_points': 3, 'total_points': 18},
            {'name': 'Mike', 'pos': 'F', 'team': 'Team H', 'mw_points': 2, 'total_points': 10},
        ]
    }

    return dummy_data
