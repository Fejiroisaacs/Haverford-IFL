from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.errors import ServerErrorMiddleware
import firebase_admin
from firebase_admin import credentials, auth, storage, db
from starlette.responses import HTMLResponse, FileResponse, RedirectResponse
from routers import matches, signup, login, contact, fantasy, players, settings, teams, admin
import json, os
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
app.include_router(admin.router)


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
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/pdf")
async def get_pdf():
    return FileResponse("data/IFL_Rule_Book.pdf")

@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    content = """User-agent: *
    Allow: /
    Sitemap: https://quickest-doralyn-haverford-167803e3.koyeb.app/sitemap.xml
    """
    return Response(content=content, media_type="text/plain")

@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    urls = [
        "https://quickest-doralyn-haverford-167803e3.koyeb.app/",
        "https://quickest-doralyn-haverford-167803e3.koyeb.app/teams",
        "https://quickest-doralyn-haverford-167803e3.koyeb.app/matches",
        "https://quickest-doralyn-haverford-167803e3.koyeb.app/players"
    ]

    xml_content = """<?xml version="1.0" encoding="UTF-8"?>\n"""
    xml_content += """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n"""

    for url in set(urls):
        xml_content += f"""    <url>
        <loc>{url}</loc>
        <priority>0.8</priority>
    </url>\n"""

    xml_content += """</urlset>"""

    return Response(content=xml_content, media_type="application/xml")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
