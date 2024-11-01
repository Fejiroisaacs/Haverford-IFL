from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordBearer
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import firebase_admin
from fastapi.responses import RedirectResponse
from starlette.responses import HTMLResponse, RedirectResponse
import pyrebase
from fastapi import APIRouter

router = APIRouter()

templates = Jinja2Templates(directory="templates")
user = None

@router.get("/settings", response_class=HTMLResponse)
async def get_login(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request, "user": user})
