from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import firebase_admin
from firebase_admin import credentials, auth, storage, db
from starlette.responses import HTMLResponse, FileResponse, RedirectResponse
from routers import matches, signup, login, contact, fantasy, players, settings, teams
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.errors import ServerErrorMiddleware
import json, os, random
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

load_dotenv()

firebase_config_str = os.getenv("FIREBASE_CONFIG")
firebase_config = json.loads(firebase_config_str)
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)

db = db.reference('/')
bucket = storage.bucket()

secret_key = os.getenv("SECRET_KEY")

app = FastAPI()

app.mount("/static", StaticFiles(directory="templates/static"), name="static")

user = None
templates = Jinja2Templates(directory="templates")

app.add_middleware(SessionMiddleware, secret_key=secret_key)

app.include_router(matches.router, dependencies=[Depends(lambda: db)])
app.include_router(signup.router, dependencies=[Depends(lambda: db), Depends(lambda: auth)])
app.include_router(login.router, dependencies=[Depends(lambda: db), Depends(lambda: auth)])
app.include_router(contact.router)
app.include_router(fantasy.router, dependencies=[Depends(lambda: db), Depends(lambda: auth)])
app.include_router(players.router, dependencies=[Depends(lambda: db)])
app.include_router(settings.router)
app.include_router(teams.router, dependencies=[Depends(lambda: db)])


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    try:
        if exc.status_code == 404:
            return templates.TemplateResponse("404error.html", {"request": request, "error": f"{exc.status_code} {str(exc.detail)}"})
    except Exception:
        return templates.TemplateResponse("error.html", {"request": request})
    
app.add_middleware(ServerErrorMiddleware, handler=http_exception_handler)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print(exec)
    try:
        if exc.status_code == 404:
            return templates.TemplateResponse("404error.html", {"request": request, "error": f"{exc.status_code} {str(exc.detail)}"})
    except Exception as e:
        return templates.TemplateResponse("error.html", {"request": request})

@app.exception_handler(HTTPException) 
async def http_exception_handler(request: Request, exc: HTTPException): 
    if exc.status_code == 401: 
        return RedirectResponse(url="/login") 
    return templates.TemplateResponse("login.html", {"request": request, "user": None, "Login": True})

@app.get("/", response_class=HTMLResponse)
@app.get("/index", response_class=HTMLResponse)
@app.get("/home", response_class=HTMLResponse)
async def read_root(request: Request):
    images = get_random_potm_images()
    return templates.TemplateResponse("index.html", {"request": request, "user": user, 'images': images})

@app.get("/pdf")
async def get_pdf():
    return FileResponse("data/IFL_Rule_Book.pdf")

def get_random_potm_images():
    images = os.listdir('templates/static/Images/POTM')
    return random.sample(images, k=9)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
