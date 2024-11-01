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
firebase_config = json.load(open("firebase/cred.json"))
firebase = pyrebase.initialize_app(firebase_config)
auth = firebase.auth()

templates = Jinja2Templates(directory="templates")
user = None

@router.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": user})


@router.post("/login")
async def post_login(request: Request, email: str = Form(...), password: str = Form(...)):
    global user
    try:
        print(email, password)
        print(user, auth.requests)
        user = auth.sign_in_with_email_and_password(email, password)
        print(user)
        return RedirectResponse("/", status_code=303)
    except Exception as e:
        print(str(e))
        user = None
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username/password"})
