from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordBearer
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, auth as fb_auth
from fastapi.responses import RedirectResponse
from starlette.responses import HTMLResponse, RedirectResponse
import pyrebase, json
from fastapi import APIRouter
from exceptions import UserNameAlreadyExists, InvalidUserName
from routers import login

cred = credentials.Certificate('cred.json')
firebase_admin.initialize_app(cred)


router = APIRouter()
firebase_config = json.load(open("cred.json"))
firebase = pyrebase.initialize_app(firebase_config)
database = firebase.database()
auth = firebase.auth()

templates = Jinja2Templates(directory="templates")
user = None

@router.get("/signup", response_class=HTMLResponse)
async def get_signup(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "user": user})

@router.post("/signup")
async def post_signup(request: Request, email: str = Form(...), username: str = Form(...), password: str = Form(...)):
    try:
        print(email, password)
        user_data = {"Email": email}
        all_users = database.child("Users").get()
        
        if username.lower() in [name.key() for name in all_users.each()]:
            raise UserNameAlreadyExists()
        
        if not username.isalnum():
            raise InvalidUserName()
        
        # user = auth.create_user_with_email_and_password(email=email, password=password)
        fb_auth.create_user(email=email, password=password, display_name=username)
        print(fb_auth.generate_email_verification_link(email=email))
        # auth.send_email_verification(user['idToken'])
        database.child("Users").child(username).set(user_data)
        
        return RedirectResponse("login", status_code=303)
    
    except Exception as e:
        print(str(e))
        return templates.TemplateResponse("signup.html", {"request": request, "error": str(e)})
        