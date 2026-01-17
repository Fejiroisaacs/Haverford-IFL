from fastapi import APIRouter, Request, Form, Depends, Cookie, HTTPException
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from firebase_admin import db
from models.fantasy import FantasyUser
from firebase_admin import auth
from datetime import datetime
import os
from functions import send_email

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


def get_pending_verifications():
    """Get all pending player verification requests"""
    try:
        links_ref = db.reference('PlayerLinks')
        all_links = links_ref.get() or {}
        pending = []
        for user_id, link_data in all_links.items():
            if link_data.get('status') == 'pending':
                pending.append({
                    'user_id': user_id,
                    **link_data
                })
        # Sort by requested_at descending
        pending.sort(key=lambda x: x.get('requested_at', ''), reverse=True)
        return pending
    except Exception:
        return []


@router.get("/admin", response_class=None)
async def admin_panel(request: Request, success: str = None, error: str = None, user: dict = Depends(get_current_user)):
    """Admin panel page for updating week and deadline (admin only)"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    # Get pending player verifications
    pending_verifications = get_pending_verifications()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "success": success,
        "error": error,
        "pending_verifications": pending_verifications
    })

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


@router.post("/admin/verify-player/approve")
async def approve_player_verification(
    request: Request,
    user_id: str = Form(...),
    user: dict = Depends(get_current_user)
):
    """Approve a player verification request"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        link_ref = db.reference(f'PlayerLinks/{user_id}')
        link_data = link_ref.get()

        if not link_data:
            return RedirectResponse(url="/admin?error=Verification+request+not+found", status_code=303)

        if link_data.get('status') != 'pending':
            return RedirectResponse(url="/admin?error=Request+already+processed", status_code=303)

        # Update the link status
        admin_name = user.get('name', 'Admin')
        link_ref.update({
            'status': 'approved',
            'reviewed_at': datetime.now().isoformat(),
            'reviewed_by': admin_name
        })

        # Remove from pending verifications queue
        pending_ref = db.reference('PendingPlayerVerifications')
        pending_data = pending_ref.get() or {}
        for key, val in pending_data.items():
            if val.get('user_id') == user_id:
                db.reference(f'PendingPlayerVerifications/{key}').delete()
                break

        # Send approval email to user
        user_email = link_data.get('user_email')
        user_name = link_data.get('user_name', 'User')
        player_name = link_data.get('player_name')

        if user_email:
            approval_message = f"""
            <h2>Player Verification Approved!</h2>
            <p>Hi {user_name},</p>
            <p>Great news! Your request to link your account to the player profile <strong>{player_name}</strong> has been approved.</p>
            <p>You can now access your personal stats dashboard by visiting <a href="https://haverfordifl.com/my-stats">My Stats</a>.</p>
            <br>
            <p>Best regards,<br>Haverford IFL Team</p>
            """
            try:
                send_email(
                    email=user_email,
                    bccs=[],
                    subject="IFL Player Verification Approved!",
                    message=approval_message
                )
            except Exception as e:
                print(f"Failed to send approval email: {e}")

        return RedirectResponse(url=f"/admin?success=Approved+verification+for+{player_name}", status_code=303)

    except Exception as e:
        return RedirectResponse(url=f"/admin?error=Error+approving:+{str(e)}", status_code=303)


@router.post("/admin/verify-player/deny")
async def deny_player_verification(
    request: Request,
    user_id: str = Form(...),
    reason: str = Form(""),
    user: dict = Depends(get_current_user)
):
    """Deny a player verification request"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        link_ref = db.reference(f'PlayerLinks/{user_id}')
        link_data = link_ref.get()

        if not link_data:
            return RedirectResponse(url="/admin?error=Verification+request+not+found", status_code=303)

        if link_data.get('status') != 'pending':
            return RedirectResponse(url="/admin?error=Request+already+processed", status_code=303)

        user_email = link_data.get('user_email')
        user_name = link_data.get('user_name', 'User')
        player_name = link_data.get('player_name')

        # Delete the link request
        link_ref.delete()

        # Remove from pending verifications queue
        pending_ref = db.reference('PendingPlayerVerifications')
        pending_data = pending_ref.get() or {}
        for key, val in pending_data.items():
            if val.get('user_id') == user_id:
                db.reference(f'PendingPlayerVerifications/{key}').delete()
                break

        # Send denial email to user
        if user_email:
            reason_text = f"<p><strong>Reason:</strong> {reason}</p>" if reason else ""
            denial_message = f"""
            <h2>Player Verification Request Denied</h2>
            <p>Hi {user_name},</p>
            <p>Unfortunately, your request to link your account to the player profile <strong>{player_name}</strong> has been denied.</p>
            {reason_text}
            <p>If you believe this was a mistake, please contact us or submit a new request with additional verification information.</p>
            <br>
            <p>Best regards,<br>Haverford IFL Team</p>
            """
            try:
                send_email(
                    email=user_email,
                    bccs=[],
                    subject="IFL Player Verification Request Update",
                    message=denial_message
                )
            except Exception as e:
                print(f"Failed to send denial email: {e}")

        return RedirectResponse(url=f"/admin?success=Denied+verification+for+{player_name}", status_code=303)

    except Exception as e:
        return RedirectResponse(url=f"/admin?error=Error+denying:+{str(e)}", status_code=303)
