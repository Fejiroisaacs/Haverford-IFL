from fastapi import Request, HTTPException, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from starlette.responses import HTMLResponse, RedirectResponse
from fastapi import APIRouter
import re
from firebase_admin import db, auth

router = APIRouter()

templates = Jinja2Templates(directory="templates")
user = None

def get_current_user(request: Request):
    session_token = request.cookies.get('session_token')
    if not session_token:
        raise HTTPException(status_code=303, detail="Not authenticated", headers={"Location": "/login"})
    try:
        user = auth.verify_id_token(session_token)
        return user
    except Exception:
        raise HTTPException(status_code=303, detail="Not authenticated", headers={"Location": "/login"})

@router.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("settings.html", {"request": request, "user": user})

@router.post("/settings/update", response_class=HTMLResponse)
async def update_settings(request: Request,
    display_name: str = Form(None),
    email: str = Form(None),
    old_password: str = Form(None),
    new_password: str = Form(None),
    confirm_password: str = Form(None)
):
    user = get_current_user(request)
    user_id = user['user_id']
    user_ref = db.reference(f'Fantasy/Users/{user_id}')
    user_data = user_ref.get() or {}
    success = None
    error = None

    # Username update
    if display_name and display_name != user_data.get('username'):
        all_users = db.reference('Users').get() or {}
        if any(name.lower() == display_name.lower() for name in all_users.keys()):
            error = "Username already exists."
        elif not display_name.isalnum():
            error = "Username must be alphanumeric."
        else:
            # Update in Auth and DB
            try:
                auth.update_user(user['uid'], display_name=display_name)
                db.reference('Users').child(display_name).set({**user_data, 'Username': display_name})
                db.reference('Users').child(user_data['username']).delete()
                user_ref.update({'username': display_name})
                success = "Username updated successfully."
                user_data['username'] = display_name
            except Exception as e:
                error = f"Error updating username: {str(e)}"

    # Email update
    if email and email != user_data.get('email'):
        all_users = db.reference('Users').get() or {}
        if any(all_users[uname]['Email'].lower() == email.lower() for uname in all_users):
            error = "Email already exists."
        elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            error = "Invalid email format."
        else:
            try:
                auth.update_user(user['uid'], email=email)
                db.reference('Users').child(user_data['username']).update({'Email': email})
                user_ref.update({'email': email})
                # Send verification email
                verification_link = auth.generate_email_verification_link(email=email)
                # You may want to send the email here using your send_email function
                success = "Email updated successfully. Please verify your new email address."
                user_data['email'] = email
            except Exception as e:
                error = f"Error updating email: {str(e)}"

    # Password update
    if old_password and new_password and confirm_password:
        try:
            if len(new_password) < 8:
                error = "Password must be at least 8 characters long."
            elif new_password != confirm_password:
                error = "Passwords do not match."
            elif old_password == new_password:
                error = "New password cannot be the same as old password."
            else:
                auth.update_user(user['uid'], password=new_password)
                success = "Password updated successfully."
        except Exception as e:
            error = f"Error updating password: {str(e)}"

    context = {"request": request, "user": user_data, "success": success if not error else None, "error": error}
    return templates.TemplateResponse("settings.html", context)

@router.post("/settings/delete", response_class=HTMLResponse)
async def delete_account(request: Request):
    user = get_current_user(request)
    user_id = user['user_id']
    db.reference(f'Fantasy/Users/{user_id}').delete()
    
    response = RedirectResponse(url="/logout", status_code=303)
    response.delete_cookie('session_token')
    return response
