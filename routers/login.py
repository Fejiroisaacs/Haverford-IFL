from fastapi import Request, Form, APIRouter, Response
import requests
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from dotenv import load_dotenv
import os

router = APIRouter()
templates = Jinja2Templates(directory="templates")
user = None

# Load environment variables
load_dotenv()
FIREBASE_API_KEY = os.getenv("apiKey")
def verify_password(email: str, password: str):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Invalid username/password: {response.text}")

@router.post("/login")
async def post_login(request: Request, email: str = Form(...), password: str = Form(...)):
    global user
    try:
        user = verify_password(email, password)
        response = RedirectResponse(url="/fantasy", status_code=303)
        response.set_cookie(key="session_token", value=user['idToken'], httponly=True, secure=True, max_age=86400)
        return response
    except Exception as e:
        print(str(e))
        user = None
        return templates.TemplateResponse("fantasy.html", {"request": request, "error": "Invalid username/password"})

@router.get("/logout")
async def logout(request: Request, response: Response):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="session_token")
    response.delete_cookie(key="user_email")
    return response
