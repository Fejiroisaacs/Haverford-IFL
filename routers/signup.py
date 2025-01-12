from fastapi import APIRouter, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, RedirectResponse
from firebase_admin import auth as fb_auth, db
from exceptions import UserNameAlreadyExists, InvalidUserName, EmailAlreadyExists
import re, os
from functions import send_email

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/signup", response_class=HTMLResponse)
async def get_signup(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None, "Login": False})

@router.post("/signup")
async def post_signup(request: Request, email: str = Form(...), username: str = Form(...), password: str = Form(...)):
    try:
        email_regex = re.compile(r"[^@]+@[^@]+\.[^@]+")
        if not email_regex.match(email):
            raise ValueError("Invalid email format")
        
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        
        user_data = {"Email": email, 'Username': username}
        users_ref = db.reference('Users')
        all_users = users_ref.get()
        print(all_users)
        if username.lower() in [name.lower() for name in all_users.keys()]:
            raise UserNameAlreadyExists()
        
        if not username.isalnum():
            raise InvalidUserName()
        
        if email.lower() in [all_users[userdata]['Email'].lower() for userdata in all_users]:
            raise EmailAlreadyExists()
        
        user_record = fb_auth.create_user(email=email, password=password)
        verification_link = fb_auth.generate_email_verification_link(email=email)
        
        # Create the email template
        email_template = f"""
        Dear {username},

        Welcome to our Fantasy App! We are glad to have you join our community.

        To complete your registration, please verify your email address by clicking the link below:
        {verification_link}

        If you did not create an account with us, please disregard this email.

        Thank you,
        Grant, Kabir, Ben, and Fejiro.
        """

        send_email(email=f'{os.getenv("OUR_EMAIL")}', bccs=email, subject="Welcome to Haverford IFL Fantasy! Verify Your Email", message=email_template)
        
        users_ref.child(username).set(user_data)
        
        return RedirectResponse("/login", status_code=303)
    except Exception as e:
        print(str(e))
        return templates.TemplateResponse("login.html", {"request": request, "error": str(e), "user": None})
