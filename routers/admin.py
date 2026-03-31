from fastapi import APIRouter, Request, Form, Depends, Cookie, HTTPException, Query
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse, HTMLResponse
from firebase_admin import db
from models.fantasy import FantasyUser, FantasyService, FantasyPointsCalculator
from firebase_admin import auth
from datetime import datetime
import os
import urllib.parse
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

    # Load fantasy_user for the fantasy_base.html navigation sidebar
    user_id = user.get('user_id') or user.get('uid')
    username = user.get('name', 'User')
    fantasy_user = FantasyUser.load_from_firebase(user_id, username)

    try:
        week_data = db.reference('Fantasy/current_week').get() or {}
    except Exception:
        week_data = {}

    if not week_data.get('Week'):
        week_data['Week'] = 1

    if not week_data.get('Season'):
        try:
            import pandas as pd
            df = pd.read_csv('data/matchweeks.csv')
            df.columns = [c.strip() for c in df.columns]
            week_data['Season'] = int(df['Season'].max())
        except Exception:
            week_data['Season'] = week_data.get('Week', 1)  # last resort

    return templates.TemplateResponse(request=request, name="admin.html", context={
        "request": request,
        "success": success,
        "error": error,
        "pending_verifications": pending_verifications,
        "fantasy_user": fantasy_user,
        "user": user,
        "week_data": week_data
    })




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


# ===========================
# MATCH DATA ENTRY
# ===========================

import pandas as pd
import json
from starlette.responses import JSONResponse

def get_teams_for_season(season=None):
    """Get list of teams for a given season"""
    try:
        standings = pd.read_csv('data/season_standings.csv', encoding='utf-8-sig')
        if season:
            standings = standings[standings['Season'] == int(season)]
        teams = standings['Team'].unique().tolist()
        return sorted(teams)
    except Exception as e:
        print(f"Error loading teams: {e}")
        return []

def get_players_for_team(team_name, season=None):
    """Get list of players for a given team"""
    try:
        stats = pd.read_csv('data/season_player_stats.csv', encoding='utf-8-sig')
        if season:
            stats = stats[stats['Season'] == str(season)]
        else:
            stats = stats[stats['Season'] != 'Total']
        team_players = stats[stats['Team'] == team_name]['Name'].unique().tolist()
        return sorted(team_players)
    except Exception as e:
        print(f"Error loading players: {e}")
        return []


@router.get("/admin/data-entry")
async def data_entry_page(request: Request, success: str = None, error: str = None, user: dict = Depends(get_current_user)):
    """Match data entry form page"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    # Get current season
    try:
        standings = pd.read_csv('data/season_standings.csv', encoding='utf-8-sig')
        current_season = int(standings['Season'].max())
    except Exception:
        try:
            df = pd.read_csv('data/matchweeks.csv')
            df.columns = [c.strip() for c in df.columns]
            current_season = int(df['Season'].max())
        except Exception:
            current_season = 1

    teams = get_teams_for_season(current_season)

    # Get next match ID
    try:
        results = pd.read_csv('data/Match_Results.csv', encoding='utf-8-sig')
        next_match_id = int(results['Match ID'].max()) + 1
    except Exception:
        next_match_id = 1

    return templates.TemplateResponse(request=request, name="admin_data_entry.html", context={
        "request": request,
        "teams": teams,
        "current_season": current_season,
        "next_match_id": next_match_id,
        "success": success,
        "error": error
    })


@router.get("/api/admin/players/{team}")
async def get_team_players(team: str, season: int = None, user: dict = Depends(get_current_user)):
    """API endpoint to get players for a team"""
    if not is_admin(user):
        return JSONResponse(content={"error": "Forbidden"}, status_code=403)

    players = get_players_for_team(team, season)
    return JSONResponse(content={"players": players})


def get_next_match_id():
    """Get the next match ID by checking both CSV and Firebase"""
    csv_max_id = 0
    firebase_max_id = 0

    # Get max from CSV
    try:
        results_path = 'data/Match_Results.csv'
        results_df = pd.read_csv(results_path, encoding='utf-8-sig')
        csv_max_id = int(results_df['Match ID'].max())
    except Exception as e:
        print(f"Could not read CSV for match ID: {e}")

    # Get max from Firebase
    try:
        game_day_ref = db.reference('game_day_stats')
        all_matchdays = game_day_ref.get() or {}
        for matchday_key, matches in all_matchdays.items():
            if isinstance(matches, dict):
                for match_id_str in matches.keys():
                    try:
                        match_id = int(match_id_str)
                        firebase_max_id = max(firebase_max_id, match_id)
                    except ValueError:
                        continue
    except Exception as e:
        print(f"Could not read Firebase for match ID: {e}")

    return max(csv_max_id, firebase_max_id) + 1


@router.post("/admin/submit-match")
async def submit_match_result(request: Request, user: dict = Depends(get_current_user)):
    """Submit a new match result to Firebase game_day_stats"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        form_data = await request.form()
        data = dict(form_data)

        # Parse the JSON data
        match_data = json.loads(data.get('match_data', '{}'))

        # Validate required fields
        required = ['team1', 'team2', 'score1', 'score2', 'matchday', 'group', 'season']
        for field in required:
            if field not in match_data:
                return RedirectResponse(url=f"/admin/data-entry?error=Missing+field:+{field}", status_code=303)

        # Get next match ID (checks both CSV and Firebase)
        next_id = get_next_match_id()
        matchday = int(match_data['matchday'])
        season = int(match_data['season'])

        # Build the match data for Firebase
        # Schema: game_day_stats / MD{matchday}_S{season} / {match_id} / data
        firebase_match_data = {
            'match_id': next_id,
            'team1': match_data['team1'],
            'score1': int(match_data['score1']),
            'team2': match_data['team2'],
            'score2': int(match_data['score2']),
            'matchday': matchday,
            'group': match_data['group'],
            'season': season,
            'potm': match_data.get('potm', ''),
            'referee': match_data.get('referee', ''),
            'data_collector': match_data.get('data_collector', ''),
            'submitted_by': user.get('email', 'unknown'),
            'submitted_at': datetime.now().isoformat(),
            'player_stats': [],
            'external_subs': []
        }

        # Handle penalty shootout data
        if match_data.get('has_penalties'):
            firebase_match_data['has_penalties'] = True
            firebase_match_data['penalty1'] = int(match_data.get('penalty1', 0))
            firebase_match_data['penalty2'] = int(match_data.get('penalty2', 0))

        # Process player stats from team rosters
        player_stats = match_data.get('player_stats', [])
        for player_stat in player_stats:
            stat_entry = {
                'player': player_stat.get('name', ''),
                'team': player_stat.get('team', ''),
                'goals': int(player_stat.get('goals', 0)),
                'assists': int(player_stat.get('assists', 0)),
                'saves': int(player_stat.get('saves', 0)),
                'yellow_cards': int(player_stat.get('yellow', 0)),
                'red_cards': int(player_stat.get('red', 0)),
                'is_potm': player_stat.get('potm', False),
                'is_manual': player_stat.get('is_manual', False)
            }
            firebase_match_data['player_stats'].append(stat_entry)

        # Process external subs
        external_subs = match_data.get('external_subs', [])
        for ext_sub in external_subs:
            sub_entry = {
                'player': ext_sub.get('name', ''),
                'team': ext_sub.get('team', ''),
                'goals': int(ext_sub.get('goals', 0)),
                'assists': int(ext_sub.get('assists', 0)),
                'saves': int(ext_sub.get('saves', 0)),
                'yellow_cards': int(ext_sub.get('yellow', 0)),
                'red_cards': int(ext_sub.get('red', 0)),
                'is_potm': ext_sub.get('potm', False),
                'is_external': True
            }
            firebase_match_data['external_subs'].append(sub_entry)

        # Save to Firebase game_day_stats
        # Schema: game_day_stats / MD{matchday}_S{season} / {match_id}
        matchday_key = f"MD{matchday}_S{season}"
        game_day_ref = db.reference(f'game_day_stats/{matchday_key}/{next_id}')
        game_day_ref.set(firebase_match_data)

        # Also save to local CSV for backwards compatibility (dev environment)
        try:
            results_path = 'data/Match_Results.csv'
            results_df = pd.read_csv(results_path, encoding='utf-8-sig')

            new_match = {
                'Match ID': next_id,
                'Team 1': match_data['team1'],
                'Score Team 1': int(match_data['score1']),
                'Team 2': match_data['team2'],
                'Score Team 2': int(match_data['score2']),
                'MD': matchday,
                'Group': match_data['group'],
                'Season': season
            }
            results_df = pd.concat([results_df, pd.DataFrame([new_match])], ignore_index=True)
            results_df.to_csv(results_path, index=False, encoding='utf-8-sig')

            # Also save player stats to CSV (both roster players and external subs)
            all_player_stats = player_stats + external_subs
            if all_player_stats:
                stats_path = 'data/player_match_stats.csv'
                try:
                    stats_df = pd.read_csv(stats_path, encoding='utf-8-sig')
                except FileNotFoundError:
                    stats_df = pd.DataFrame(columns=['Match ID', 'Player', 'Team', 'Goals', 'Assists', 'Saves', 'Yellow', 'Red', 'POTM', 'External'])

                for player_stat in all_player_stats:
                    stat_entry = {
                        'Match ID': next_id,
                        'Player': player_stat.get('name', ''),
                        'Team': player_stat.get('team', ''),
                        'Goals': int(player_stat.get('goals', 0)),
                        'Assists': int(player_stat.get('assists', 0)),
                        'Saves': int(player_stat.get('saves', 0)),
                        'Yellow': int(player_stat.get('yellow', 0)),
                        'Red': int(player_stat.get('red', 0)),
                        'POTM': 1 if player_stat.get('potm', False) else 0,
                        'External': 1 if player_stat.get('is_external', False) else 0
                    }
                    stats_df = pd.concat([stats_df, pd.DataFrame([stat_entry])], ignore_index=True)
                stats_df.to_csv(stats_path, index=False, encoding='utf-8-sig')
        except Exception as csv_error:
            # CSV save failed but Firebase succeeded - log but don't fail
            print(f"CSV save failed (Firebase succeeded): {csv_error}")

        # Log the action to audit trail
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'user': user.get('email', 'unknown'),
            'data_collector': match_data.get('data_collector', ''),
            'action': 'match_entry',
            'match_id': next_id,
            'matchday_key': matchday_key,
            'summary': f"{match_data['team1']} {match_data['score1']}-{match_data['score2']} {match_data['team2']}"
        }
        try:
            audit_ref = db.reference('AdminAuditLog')
            audit_ref.push(log_entry)
        except Exception as e:
            print(f"Failed to log audit entry: {e}")

        success_msg = f"Match+{next_id}+saved:+{match_data['team1']}+{match_data['score1']}-{match_data['score2']}+{match_data['team2']}"
        return RedirectResponse(url=f"/admin/data-entry?success={success_msg}", status_code=303)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return RedirectResponse(url=f"/admin/data-entry?error=Error+saving+match:+{str(e)}", status_code=303)


# ===========================
# FANTASY USER MANAGEMENT
# ===========================

@router.get("/admin/fantasy-users", response_class=HTMLResponse)
async def fantasy_users_list(
    request: Request,
    user: dict = Depends(get_current_user),
    success: str = None,
    error: str = None
):
    """View all fantasy users with their stats"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        users_ref = db.reference('Fantasy/Users')
        all_users = users_ref.get() or {}

        # Get current week settings
        week_ref = db.reference('Fantasy/current_week')
        week_data = week_ref.get() or {}

        users_list = []
        for user_id, user_data in all_users.items():
            users_list.append({
                'user_id': user_id,
                'username': user_data.get('username', 'Unknown'),
                'total_points': user_data.get('total_points', 0),
                'week_points': user_data.get('week_points', 0),
                'total_balance': user_data.get('total_balance', 100.0),
                'free_transfers': user_data.get('free_transfers', 2),
                'team_size': len(user_data.get('all_players', [])),
                'starting_size': len(user_data.get('current_team', [])),
                'captain': user_data.get('captain', 'None'),
                'admin': user_data.get('admin', False)
            })

        # Sort by total points descending
        users_list.sort(key=lambda x: x['total_points'], reverse=True)

        return templates.TemplateResponse(request=request, name="admin_fantasy_users.html", context={
            "request": request,
            "users": users_list,
            "week_data": week_data,
            "total_users": len(users_list),
            "success": urllib.parse.unquote(success) if success else None,
            "error": urllib.parse.unquote(error) if error else None
        })

    except Exception as e:
        return templates.TemplateResponse(request=request, name="admin_fantasy_users.html", context={
            "request": request,
            "users": [],
            "week_data": {},
            "total_users": 0,
            "error": str(e)
        })


@router.get("/admin/fantasy-user/{user_id}", response_class=HTMLResponse)
async def fantasy_user_detail(
    request: Request,
    user_id: str,
    user: dict = Depends(get_current_user),
    success: str = None,
    error: str = None
):
    """View and edit a specific fantasy user"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        user_ref = db.reference(f'Fantasy/Users/{user_id}')
        user_data = user_ref.get()

        if not user_data:
            return RedirectResponse(url="/admin/fantasy-users?error=User+not+found", status_code=303)

        # Get player details for the user's team
        fantasy_service = FantasyService()
        all_players_data = fantasy_service.get_players_by_names(user_data.get('all_players', []))
        starting_team_data = fantasy_service.get_players_by_names(user_data.get('current_team', []))

        return templates.TemplateResponse(request=request, name="admin_fantasy_user_detail.html", context={
            "request": request,
            "target_user_id": user_id,
            "target_user": user_data,
            "all_players_data": all_players_data,
            "starting_team_data": starting_team_data,
            "success": urllib.parse.unquote(success) if success else None,
            "error": urllib.parse.unquote(error) if error else None
        })

    except Exception as e:
        return RedirectResponse(url=f"/admin/fantasy-users?error={urllib.parse.quote(str(e))}", status_code=303)


@router.post("/admin/fantasy-user/{user_id}/update")
async def update_fantasy_user(
    request: Request,
    user_id: str,
    user: dict = Depends(get_current_user),
    total_points: int = Form(None),
    week_points: int = Form(None),
    total_balance: float = Form(None),
    free_transfers: int = Form(None)
):
    """Update a fantasy user's stats"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        user_ref = db.reference(f'Fantasy/Users/{user_id}')
        user_data = user_ref.get()

        if not user_data:
            return RedirectResponse(url="/admin/fantasy-users?error=User+not+found", status_code=303)

        updates = {}
        if total_points is not None:
            updates['total_points'] = total_points
        if week_points is not None:
            updates['week_points'] = week_points
        if total_balance is not None:
            updates['total_balance'] = total_balance
        if free_transfers is not None:
            updates['free_transfers'] = free_transfers

        if updates:
            user_ref.update(updates)

        # Log the action
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'admin': user.get('email', 'unknown'),
            'action': 'update_fantasy_user',
            'target_user_id': user_id,
            'updates': updates
        }
        db.reference('AdminAuditLog').push(log_entry)

        success_msg = f"Updated user {user_data.get('username', user_id)}"
        return RedirectResponse(url=f"/admin/fantasy-user/{user_id}?success={urllib.parse.quote(success_msg)}", status_code=303)

    except Exception as e:
        return RedirectResponse(url=f"/admin/fantasy-user/{user_id}?error={urllib.parse.quote(str(e))}", status_code=303)


@router.post("/admin/fantasy-user/{user_id}/reset-team")
async def reset_fantasy_user_team(
    request: Request,
    user_id: str,
    user: dict = Depends(get_current_user)
):
    """Reset a user's fantasy team completely"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        user_ref = db.reference(f'Fantasy/Users/{user_id}')
        user_data = user_ref.get()

        if not user_data:
            return RedirectResponse(url="/admin/fantasy-users?error=User+not+found", status_code=303)

        # Reset team data
        user_ref.update({
            'all_players': [],
            'current_team': [],
            'captain': None,
            'total_balance': 100.0,
            'free_transfers': 2
        })

        # Log the action
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'admin': user.get('email', 'unknown'),
            'action': 'reset_fantasy_team',
            'target_user_id': user_id,
            'target_username': user_data.get('username', 'Unknown')
        }
        db.reference('AdminAuditLog').push(log_entry)

        success_msg = f"Reset team for {user_data.get('username', user_id)}"
        return RedirectResponse(url=f"/admin/fantasy-users?success={urllib.parse.quote(success_msg)}", status_code=303)

    except Exception as e:
        return RedirectResponse(url=f"/admin/fantasy-users?error={urllib.parse.quote(str(e))}", status_code=303)


@router.post("/admin/fantasy-user/{user_id}/delete")
async def delete_fantasy_user(
    request: Request,
    user_id: str,
    user: dict = Depends(get_current_user)
):
    """Delete a fantasy user completely"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        user_ref = db.reference(f'Fantasy/Users/{user_id}')
        user_data = user_ref.get()

        if not user_data:
            return RedirectResponse(url="/admin/fantasy-users?error=User+not+found", status_code=303)

        username = user_data.get('username', 'Unknown')

        # Delete the user
        user_ref.delete()

        # Log the action
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'admin': user.get('email', 'unknown'),
            'action': 'delete_fantasy_user',
            'target_user_id': user_id,
            'target_username': username
        }
        db.reference('AdminAuditLog').push(log_entry)

        success_msg = f"Deleted fantasy user {username}"
        return RedirectResponse(url=f"/admin/fantasy-users?success={urllib.parse.quote(success_msg)}", status_code=303)

    except Exception as e:
        return RedirectResponse(url=f"/admin/fantasy-users?error={urllib.parse.quote(str(e))}", status_code=303)


# ===========================
# WEEK & SEASON MANAGEMENT
# ===========================

@router.get("/admin/week-management", response_class=HTMLResponse)
async def week_management_page(
    request: Request,
    user: dict = Depends(get_current_user),
    success: str = None,
    error: str = None
):
    """Week and season management page"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        # Get current week settings
        week_ref = db.reference('Fantasy/current_week')
        week_data = week_ref.get() or {}

        # Get team lock status
        lock_ref = db.reference('Fantasy/settings/team_lock')
        team_locked = lock_ref.get() or False

        # Load matchweeks data grouped by season
        try:
            matchweeks_df = pd.read_csv('data/matchweeks.csv')
            matchweeks_df.columns = [col.strip() for col in matchweeks_df.columns]
            available_matchweeks = matchweeks_df.to_dict('records')

            # Group matchweeks by season for dynamic dropdown
            season_matchweeks = {}
            for row in available_matchweeks:
                season = int(row['Season'])
                mw = int(row['MW'])
                if season not in season_matchweeks:
                    season_matchweeks[season] = []
                season_matchweeks[season].append(mw)
            # Sort matchweeks within each season
            for season in season_matchweeks:
                season_matchweeks[season] = sorted(season_matchweeks[season])
        except Exception as e:
            print(f"Error loading matchweeks: {e}")
            available_matchweeks = []
            season_matchweeks = {}

        # Get user counts
        users_ref = db.reference('Fantasy/Users')
        all_users = users_ref.get() or {}
        users_with_teams = sum(1 for u in all_users.values() if u.get('current_team'))

        return templates.TemplateResponse(request=request, name="admin_week_management.html", context={
            "request": request,
            "week_data": week_data,
            "team_locked": team_locked,
            "available_matchweeks": available_matchweeks,
            "season_matchweeks": season_matchweeks,
            "total_users": len(all_users),
            "users_with_teams": users_with_teams,
            "success": urllib.parse.unquote(success) if success else None,
            "error": urllib.parse.unquote(error) if error else None
        })

    except Exception as e:
        return templates.TemplateResponse(request=request, name="admin_week_management.html", context={
            "request": request,
            "week_data": {},
            "team_locked": False,
            "available_matchweeks": [],
            "season_matchweeks": {},
            "total_users": 0,
            "users_with_teams": 0,
            "error": str(e)
        })


@router.post("/admin/set-current-week")
async def set_current_week(
    request: Request,
    user: dict = Depends(get_current_user),
    season: int = Form(...),
    matchweek: int = Form(...),
    deadline: str = Form("")
):
    """Set the current active season and matchweek.
    Also saves current week_points to history, resets week_points to 0, and resets free transfers to 2.
    """
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        # Validate player data exists for this season
        fantasy_service = FantasyService(season=season)
        if not fantasy_service.has_players_for_season(season):
            error_msg = f"No player data found in Fantasy_Data.csv for Season {season}. Please update the CSV first."
            return RedirectResponse(url=f"/admin/week-management?error={urllib.parse.quote(error_msg)}", status_code=303)

        week_ref = db.reference('Fantasy/current_week')
        previous_weeks_ref = db.reference('Fantasy/previous_weeks')
        history_ref = db.reference('Fantasy/UserHistory')

        # Archive current week data
        current_data = week_ref.get()
        if current_data:
            previous_weeks_ref.push(current_data)

        # Save each user's current week_points to history before reset
        users_ref = db.reference('Fantasy/Users')
        all_users = users_ref.get() or {}
        
        if current_data:
            old_season = current_data.get('Season')
            old_week = current_data.get('Week')
            if old_season and old_week:
                history_key = f"S{old_season}_MW{old_week}"
                for uid, udata in all_users.items():
                    current_wp = udata.get('week_points', 0)
                    # Save all users regardless of points to maintain a complete audit trail.
                    # Only skip if a history entry already exists (e.g. saved by process_all_users_matchweek).
                    existing = history_ref.child(uid).child(history_key).get()
                    if not existing:
                        history_ref.child(uid).child(history_key).set({
                            'season': old_season,
                            'matchweek': old_week,
                            'points': current_wp,
                            'saved_at': datetime.now().isoformat()
                        })

        # Reset week_points to 0 and free_transfers to 2 for all users
        reset_count = 0
        for uid in all_users.keys():
            users_ref.child(uid).update({
                'week_points': 0,
                'free_transfers': 2
            })
            reset_count += 1

        # Set new week data
        week_ref.set({
            'Season': season,
            'Week': matchweek,
            'Deadline': deadline,
            'updated_at': datetime.now().isoformat(),
            'updated_by': user.get('email', 'unknown')
        })

        # Log the action
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'admin': user.get('email', 'unknown'),
            'action': 'set_current_week',
            'season': season,
            'matchweek': matchweek,
            'users_reset': reset_count
        }
        db.reference('AdminAuditLog').push(log_entry)

        success_msg = f"Set to Season {season} MW{matchweek}. Reset week_points and free_transfers for {reset_count} users."
        return RedirectResponse(url=f"/admin/week-management?success={urllib.parse.quote(success_msg)}", status_code=303)

    except Exception as e:
        return RedirectResponse(url=f"/admin/week-management?error={urllib.parse.quote(str(e))}", status_code=303)


@router.post("/admin/toggle-team-lock")
async def toggle_team_lock(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Toggle team editing lock on/off. When locking, auto-snapshot all teams."""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        lock_ref = db.reference('Fantasy/settings/team_lock')
        current_lock = lock_ref.get() or False

        # Toggle the lock
        new_lock = not current_lock
        lock_ref.set(new_lock)

        snapshot_msg = ""
        # Auto-snapshot all teams when LOCKING
        if new_lock:
            week_data = db.reference('Fantasy/current_week').get() or {}
            season = week_data.get('Season')
            matchweek = week_data.get('Week')

            if season and matchweek:
                users_ref = db.reference('Fantasy/Users')
                snapshots_ref = db.reference('Fantasy/TeamSnapshots')
                all_users = users_ref.get() or {}
                snapshot_key = f"S{season}_MW{matchweek}"
                snapshot_count = 0

                for uid, user_data in all_users.items():
                    current_team = user_data.get('current_team', [])
                    if current_team and len(current_team) == 5:
                        snapshots_ref.child(uid).child(snapshot_key).set({
                            'team': current_team,
                            'captain': user_data.get('captain'),
                            'all_players': user_data.get('all_players', []),
                            'snapshot_at': datetime.now().isoformat()
                        })
                        snapshot_count += 1

                snapshot_msg = f" Snapshotted {snapshot_count} teams for S{season}_MW{matchweek}."

        # Log the action
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'admin': user.get('email', 'unknown'),
            'action': 'toggle_team_lock',
            'new_status': 'locked' if new_lock else 'unlocked'
        }
        db.reference('AdminAuditLog').push(log_entry)

        status = "locked" if new_lock else "unlocked"
        success_msg = f"Team editing is now {status}.{snapshot_msg}"
        return RedirectResponse(url=f"/admin/week-management?success={urllib.parse.quote(success_msg)}", status_code=303)

    except Exception as e:
        return RedirectResponse(url=f"/admin/week-management?error={urllib.parse.quote(str(e))}", status_code=303)


@router.post("/admin/reset-free-transfers")
async def reset_all_free_transfers(
    request: Request,
    user: dict = Depends(get_current_user),
    transfer_count: int = Form(2)
):
    """Reset free transfers for all users"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        users_ref = db.reference('Fantasy/Users')
        all_users = users_ref.get() or {}

        reset_count = 0
        for uid in all_users.keys():
            users_ref.child(uid).update({'free_transfers': transfer_count})
            reset_count += 1

        # Log the action
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'admin': user.get('email', 'unknown'),
            'action': 'reset_free_transfers',
            'transfer_count': transfer_count,
            'users_affected': reset_count
        }
        db.reference('AdminAuditLog').push(log_entry)

        success_msg = f"Reset free transfers to {transfer_count} for {reset_count} users"
        return RedirectResponse(url=f"/admin/week-management?success={urllib.parse.quote(success_msg)}", status_code=303)

    except Exception as e:
        return RedirectResponse(url=f"/admin/week-management?error={urllib.parse.quote(str(e))}", status_code=303)


# ===========================
# SEASON MANAGEMENT
# ===========================

@router.post("/admin/fantasy/new-season")
async def start_new_season(
    request: Request,
    user: dict = Depends(get_current_user),
    new_season: int = Form(...)
):
    """Start a new fantasy season — archive current data and reset all teams"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    try:
        # Get current season
        current_week_data = db.reference('Fantasy/current_week').get() or {}
        current_season = int(current_week_data.get('Season', 1))
        if new_season <= current_season:
            error_msg = f"New season ({new_season}) must be greater than current season ({current_season})."
            return RedirectResponse(url=f"/admin/week-management?error={urllib.parse.quote(error_msg)}", status_code=303)

        # Validate player data exists for the new season
        fantasy_service = FantasyService(season=new_season)
        if not fantasy_service.has_players_for_season(new_season):
            error_msg = f"No player data found in Fantasy_Data.csv for Season {new_season}. Please update the CSV first."
            return RedirectResponse(url=f"/admin/week-management?error={urllib.parse.quote(error_msg)}", status_code=303)

        # Get current season info
        week_ref = db.reference('Fantasy/current_week')
        current_week_data = week_ref.get() or {}
        current_season = current_week_data.get('Season', new_season - 1)

        # Archive current season data for all users
        users_ref = db.reference('Fantasy/Users')
        archive_ref = db.reference(f'Fantasy/SeasonArchive/S{current_season}')
        all_users = users_ref.get() or {}

        archived_count = 0
        for uid, user_data in all_users.items():
            # Archive user's current state
            archive_ref.child(uid).set({
                'username': user_data.get('username', 'Unknown'),
                'all_players': user_data.get('all_players', []),
                'current_team': user_data.get('current_team', []),
                'captain': user_data.get('captain'),
                'total_balance': user_data.get('total_balance', 100.0),
                'total_points': user_data.get('total_points', 0),
                'season_points': user_data.get('season_points', {}),
                'week_points': user_data.get('week_points', 0),
                'archived_at': datetime.now().isoformat()
            })

            # Reset user for new season — preserve total_points, season_points, UserHistory
            users_ref.child(uid).update({
                'all_players': [],
                'current_team': [],
                'captain': None,
                'total_balance': 100.0,
                'free_transfers': 2,
                'week_points': 0
            })
            archived_count += 1

        # Unlock teams for the new season
        db.reference('Fantasy/settings/team_lock').set(False)

        # Set new season week 1
        week_ref.set({
            'Season': new_season,
            'Week': 1,
            'Deadline': '',
            'updated_at': datetime.now().isoformat(),
            'updated_by': user.get('email', 'unknown')
        })

        # Log the action
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'admin': user.get('email', 'unknown'),
            'action': 'start_new_season',
            'old_season': current_season,
            'new_season': new_season,
            'users_archived': archived_count
        }
        db.reference('AdminAuditLog').push(log_entry)

        success_msg = f"Started Season {new_season}! Archived {archived_count} users from Season {current_season}. All teams reset."
        return RedirectResponse(url=f"/admin/week-management?success={urllib.parse.quote(success_msg)}", status_code=303)

    except Exception as e:
        return RedirectResponse(url=f"/admin/week-management?error={urllib.parse.quote(str(e))}", status_code=303)
