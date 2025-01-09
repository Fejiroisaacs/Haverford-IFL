from fastapi import APIRouter, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, RedirectResponse
from firebase_admin import auth as fb_auth, db
from exceptions import UserNameAlreadyExists, InvalidUserName

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/signup", response_class=HTMLResponse)
async def get_signup(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None, "Login": False})

@router.post("/signup")
async def post_signup(request: Request, email: str = Form(...), username: str = Form(...), password: str = Form(...)):
    try:
        user_data = {"Email": email}
        users_ref = db.reference('Users')
        all_users = users_ref.get()
        
        if username.lower() in [name.lower() for name in all_users.keys()]:
            raise UserNameAlreadyExists()
        
        if not username.isalnum():
            raise InvalidUserName()
        
        user_record = fb_auth.create_user(email=email, password=password)
        verification_link = fb_auth.generate_email_verification_link(email=email)
        print(verification_link)
        
        users_ref.child(username).set(user_data)
        
        return RedirectResponse("fantasy", status_code=303)
    
    except Exception as e:
        print(str(e))
        return templates.TemplateResponse("login.html", {"request": request, "error": str(e), "user": None})
