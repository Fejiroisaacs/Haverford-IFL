from fastapi import Request, Form, APIRouter, Depends, Cookie
from firebase_admin import auth, firestore
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")
user = None

@router.get("/fantasy", response_class=HTMLResponse)
async def fantasy_loading(request: Request, session_token: str = Cookie(None)):
    user = None
    if session_token:
        try:
            user = auth.verify_id_token(session_token)
        except Exception as e:
            print("Invalid session token:", str(e))
    
    return templates.TemplateResponse("fantasy.html", {"request": request, "user": user, 'data': get_user_data()})


def get_user_data():
    dummy_data = {
        'Name': 'Dummy',
        'Average': 40,
        'curr_pts' : 197,
        'record': 62,
        'team': ['Rami', 'Yass', 'Kab', 'Fej', 'Grant'],
        'MW': 5,
        'Deadline': '1/17'
    }
    return dummy_data