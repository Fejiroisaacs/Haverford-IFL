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
        current_season = 6

    teams = get_teams_for_season(current_season)

    # Get next match ID
    try:
        results = pd.read_csv('data/Match_Results.csv', encoding='utf-8-sig')
        next_match_id = int(results['Match ID'].max()) + 1
    except Exception:
        next_match_id = 1

    return templates.TemplateResponse("admin_data_entry.html", {
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
