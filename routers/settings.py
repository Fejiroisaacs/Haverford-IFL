from fastapi import Request, HTTPException, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from starlette.responses import HTMLResponse, RedirectResponse
from fastapi import APIRouter
import re
import os
import pandas as pd
from datetime import datetime
from firebase_admin import db, auth
from functions import send_email

router = APIRouter()

templates = Jinja2Templates(directory="templates")
user = None


def get_all_players_list():
    """Get list of all player names for the dropdown"""
    try:
        players_df = pd.read_csv('data/player_ratings.csv')
        return sorted(players_df['Name'].unique().tolist())
    except Exception:
        return []


def get_user_player_link(user_id):
    """Get the linked player for a user, if any"""
    try:
        link_ref = db.reference(f'PlayerLinks/{user_id}')
        link_data = link_ref.get()
        return link_data
    except Exception:
        return None


def is_player_already_linked(player_name):
    """Check if a player is already linked or has a pending request from another user"""
    try:
        links_ref = db.reference('PlayerLinks')
        all_links = links_ref.get() or {}
        for user_id, link_data in all_links.items():
            if link_data.get('player_name') == player_name:
                status = link_data.get('status')
                if status in ('approved', 'pending'):
                    return {
                        'is_linked': True,
                        'status': status,
                        'user_id': user_id
                    }
        return {'is_linked': False}
    except Exception:
        return {'is_linked': False}


def get_available_players():
    """Get list of players that are not yet linked to any user"""
    try:
        all_players = get_all_players_list()
        links_ref = db.reference('PlayerLinks')
        all_links = links_ref.get() or {}

        # Get players that are already linked or pending
        linked_players = set()
        for user_id, link_data in all_links.items():
            if link_data.get('status') in ('approved', 'pending'):
                linked_players.add(link_data.get('player_name'))

        # Return only available players
        return [p for p in all_players if p not in linked_players]
    except Exception:
        return get_all_players_list()


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
    user_id = user.get('user_id') or user.get('uid')

    # Get available players for linking dropdown (excludes already linked players)
    available_players = get_available_players()

    # Get current player link status
    player_link = get_user_player_link(user_id)

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "all_players": available_players,
        "player_link": player_link
    })

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


@router.post("/settings/link-player", response_class=HTMLResponse)
async def link_player_request(request: Request, player_name: str = Form(...)):
    """Submit a request to link account to a player profile"""
    user = get_current_user(request)
    user_id = user.get('user_id') or user.get('uid')
    user_email = user.get('email', 'Unknown')
    user_name = user.get('name', 'Unknown')

    all_players = get_all_players_list()
    player_link = get_user_player_link(user_id)
    success = None
    error = None

    # Check if player name is valid
    if player_name not in all_players:
        error = "Invalid player selected."
    # Check if user already has a pending or approved link
    elif player_link:
        if player_link.get('status') == 'approved':
            error = "You already have a linked player profile."
        elif player_link.get('status') == 'pending':
            error = "You already have a pending verification request."
    else:
        # Check if this player is already linked to another user
        existing_link = is_player_already_linked(player_name)
        if existing_link.get('is_linked'):
            if existing_link.get('status') == 'approved':
                error = f"{player_name} is already linked to another account."
            else:
                error = f"{player_name} has a pending verification request from another user."

    if not error:
        try:
            # Create verification request in Firebase
            request_data = {
                'user_id': user_id,
                'user_email': user_email,
                'user_name': user_name,
                'player_name': player_name,
                'status': 'pending',
                'requested_at': datetime.now().isoformat(),
                'reviewed_at': None,
                'reviewed_by': None
            }

            # Save to PlayerLinks collection
            db.reference(f'PlayerLinks/{user_id}').set(request_data)

            # Also add to pending verifications for easy admin access
            db.reference('PendingPlayerVerifications').push({
                'user_id': user_id,
                'user_email': user_email,
                'user_name': user_name,
                'player_name': player_name,
                'requested_at': datetime.now().isoformat()
            })

            # Send notification emails
            admin_email = os.getenv("OUR_EMAIL")

            # Email to user
            user_message = f"""
            <h2>Player Verification Request Submitted</h2>
            <p>Hi {user_name},</p>
            <p>Your request to link your account to the player profile <strong>{player_name}</strong> has been submitted.</p>
            <p>An administrator will review your request shortly. You will receive another email once your request has been processed.</p>
            <br>
            <p>Best regards,<br>Haverford IFL Team</p>
            """

            try:
                send_email(
                    email=user_email,
                    bccs=[],
                    subject="IFL Player Verification Request Submitted",
                    message=user_message
                )
            except Exception as e:
                print(f"Failed to send user email: {e}")

            # Email to admin
            admin_message = f"""
            <h2>New Player Verification Request</h2>
            <p>A new player verification request has been submitted:</p>
            <ul>
                <li><strong>User Name:</strong> {user_name}</li>
                <li><strong>User Email:</strong> {user_email}</li>
                <li><strong>User ID:</strong> {user_id}</li>
                <li><strong>Requested Player:</strong> {player_name}</li>
                <li><strong>Requested At:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
            </ul>
            <p>Please review this request in the admin dashboard.</p>
            """

            try:
                send_email(
                    email=admin_email,
                    bccs=[],
                    subject=f"IFL Verification Request: {user_name} -> {player_name}",
                    message=admin_message
                )
            except Exception as e:
                print(f"Failed to send admin email: {e}")

            success = f"Verification request submitted for {player_name}. You will receive an email once approved."
            player_link = request_data

        except Exception as e:
            error = f"Error submitting request: {str(e)}"

    # Use available players for the dropdown (excludes already linked players)
    available_players = get_available_players()

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "all_players": available_players,
        "player_link": player_link,
        "success": success,
        "error": error
    })


@router.get("/my-stats", response_class=HTMLResponse)
async def my_stats(request: Request):
    """Personal stats dashboard for verified players"""
    user = get_current_user(request)
    user_id = user.get('user_id') or user.get('uid')

    # Check if user has an approved player link
    player_link = get_user_player_link(user_id)

    if not player_link or player_link.get('status') != 'approved':
        # Redirect to settings with message
        return RedirectResponse(url="/settings?error=Link+your+player+profile+first", status_code=303)

    # Get the linked player name and redirect to their player page
    player_name = player_link.get('player_name')

    # We could create a custom "my stats" page, but for now redirect to player page
    return RedirectResponse(url=f"/players/{player_name}", status_code=303)
