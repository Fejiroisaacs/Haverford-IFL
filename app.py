from fastapi import FastAPI, Request, Depends, HTTPException, Form, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import firebase_admin
from fastapi.responses import RedirectResponse
from starlette.responses import HTMLResponse, RedirectResponse
import pyrebase, json
from routers import matches, signup, login, contact, fantasy, players, settings, teams
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

firebase_config = json.load(open("cred.json"))

firebase = pyrebase.initialize_app("firebase_config")
db = firebase.database()
fb_storage = firebase.storage()
auth = firebase.auth()

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="templates/static"), name="static")

user = None
templates = Jinja2Templates(directory="templates")

app.include_router(matches.router)
app.include_router(signup.router)
app.include_router(login.router)
app.include_router(contact.router)
app.include_router(fantasy.router)
app.include_router(players.router)
app.include_router(settings.router)
app.include_router(teams.router)

class User(BaseModel):
    email: str

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    if exc.status_code == 404:
        return templates.TemplateResponse("404error.html", {"request": request, "error": f"{exc.status_code} {str(exc.detail)}"})
    return templates.TemplateResponse("error.html", {"request": request, "error": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    if exc.status_code == 404:
        return templates.TemplateResponse("404error.html", {"request": request, "error": f"{exc.status_code} {str(exc.detail)}"})
    return templates.TemplateResponse("error.html", {"request": request, "error": str(exc.detail)})


@app.post("/token")
async def token():
    # Handle user authentication with Firebase here
    pass

@app.get("/", response_class=HTMLResponse)
@app.get("/index", response_class=HTMLResponse)
@app.get("/home", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/logout", response_class=HTMLResponse)
async def get_logout(request: Request):
    global user
    user = None
    return RedirectResponse("/", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
