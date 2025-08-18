from fastapi import APIRouter, Request, Form, Depends, Cookie, HTTPException
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from firebase_admin import db
from models.fantasy import FantasyUser
from firebase_admin import auth

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_current_user(session_token: str = Cookie(None)):
    if not session_token:
        raise HTTPException(status_code=303, detail="Not authenticated", headers={"Location": "/login"})
    try:
        user = auth.verify_id_token(session_token)
        return user
    except Exception as e:
        print("Invalid session token:", str(e))
        raise HTTPException(status_code=303, detail="Not authenticated", headers={"Location": "/login"})

def is_admin(user: dict):
    # Use FantasyUser to check admin status from Firebase
    user_id = user.get('user_id')
    username = user.get('name', 'User')
    if not user_id:
        return False
    fantasy_user = FantasyUser.load_from_firebase(user_id, username)
    return bool(getattr(fantasy_user, 'admin', False))

@router.get("/admin", response_class=None)
async def admin_panel(request: Request, success: str = None, error: str = None, user: dict = Depends(get_current_user)):
    """Admin panel page for updating week and deadline (admin only)"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    return templates.TemplateResponse("admin.html", {"request": request, "success": success, "error": error})

@router.post("/admin/update-week")
async def update_week(request: Request, current_week: int = Form(...), deadline: str = Form(...), user: dict = Depends(get_current_user)):
    """Update current week and deadline in Firebase, and archive previous week"""
    # Only allow admin
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    try:
        week_ref = db.reference('Fantasy/current_week')
        previous_weeks_ref = db.reference('Fantasy/previous_weeks')
        
        current_week_data = week_ref.get()
        if current_week_data:
            previous_weeks_ref.push(current_week_data)
        
        week_ref.update({
            'Week': current_week,
            'Deadline': deadline
        })
        
        success_message = "Week and deadline updated successfully."
        return RedirectResponse(url=f"/admin?success={success_message}", status_code=303)
    except Exception as e:
        error_message = f"Error updating week: {str(e)}"
        return RedirectResponse(url=f"/admin?error={error_message}", status_code=303)

@router.post("/admin/update-week-performance")
async def update_week_performance(request: Request, current_week: int = Form(...), user: dict = Depends(get_current_user)):
    # Only allow admin
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    try:
        import pandas as pd
        df = pd.read_csv('data/Fantasy_Data.csv')
        week_col = f"MW{current_week}"
        if week_col not in df.columns:
            error_message = f"Week column {week_col} not found in Fantasy_Data.csv."
            return RedirectResponse(url=f"/admin?error={error_message}", status_code=303)
        # Get all users
        users_ref = db.reference('Fantasy/Users')
        all_users = users_ref.get() or {}
        updated_count = 0
        for user_id, user_data in all_users.items():
            team = user_data.get('team', {})
            current_team = team.get('current_team', [])
            # Sum up MW{current_week} for each player in current_team
            total_points = 0
            for player_name in current_team:
                # Find player row
                player_row = df[(df['First Name'] + ' ' + df['Last Name']) == player_name]
                if not player_row.empty:
                    points = player_row.iloc[0][week_col]
                    try:
                        total_points += float(points)
                    except Exception:
                        continue
            # Update user's week_points and total_points
            users_ref.child(user_id).update({
                'week_points': total_points,
                'total_points': user_data.get('total_points', 0) + total_points
            })
            updated_count += 1
        success_message = f"Updated {updated_count} users with week {current_week} performance."
        return RedirectResponse(url=f"/admin?success={success_message}", status_code=303)
    except Exception as e:
        error_message = f"Error updating week performance: {str(e)}"
        return RedirectResponse(url=f"/admin?error={error_message}", status_code=303)
