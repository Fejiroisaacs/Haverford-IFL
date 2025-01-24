from fastapi import Request, Form
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
from fastapi import APIRouter
from functions import send_email
import os
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

templates = Jinja2Templates(directory="templates")
user = None

@router.get("/contact", response_class=HTMLResponse)
async def read_contact(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request, "user": user})


@router.post("/send-message", response_class=HTMLResponse)
async def send_feedback(request: Request, email: str = Form(...), textarea: str = Form(...)):
    try:
        if not email or not textarea:
            return templates.TemplateResponse("contact.html", {"request": request, 
                                                            "error": 'All fields are required.', 
                                                            "success": None})
            
        emails = ['fanigboro@haverford.edu', 'gdevries@haverford.edu']
        if '@' in email:emails.append(email)
        
        send_email(email=f'{os.getenv("OUR_EMAIL")}', bccs=emails, subject=f'{email} left a message', message=textarea)
        
        return templates.TemplateResponse("contact.html", {"request": request, 
                                                        "success": f"Thank you, {email}. We've received your message.", 
                                                        "error": None})
    except:
        return templates.TemplateResponse("contact.html", {"request": request, 
                                                        "success": None, 
                                                        "error": 'Email not sent, something happened'})
