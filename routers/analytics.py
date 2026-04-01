from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
from auth_utils import get_current_user
from firebase_admin import db as firebase_db
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

IS_PRODUCTION = os.getenv('KOYEB_PUBLIC_DOMAIN') is not None or os.getenv('ENVIRONMENT') == 'production'


def _check_admin(user):
    """Check if user is an admin. Returns False if user is None or not admin."""
    if not user or 'user_id' not in user:
        return False
    try:
        from models.fantasy import FantasyUser
        user_id = user.get('user_id')
        username = user.get('name', 'User')
        fantasy_user = FantasyUser.load_from_firebase(user_id, username)
        return bool(getattr(fantasy_user, 'admin', False))
    except Exception:
        return False


def get_analytics_data(include_admin=False):
    """
    Fetch analytics data from Firebase.

    Args:
        include_admin: If True, include sensitive data (errors, detailed logs).

    Returns:
        Dict with analytics data. Returns demo/empty data in local dev.
    """
    try:
        db_ref = firebase_db.reference('/analytics')

        # Public data — always fetched
        daily_stats = db_ref.child('daily_stats').get() or {}
        player_views = db_ref.child('player_views').get() or {}
        team_views = db_ref.child('team_views').get() or {}
        page_views_raw = db_ref.child('page_views').get() or {}
        match_preview_views = db_ref.child('match_preview_views').get() or {}

        print(f"[Analytics] Fetched data - daily_stats: {len(daily_stats)} days, player_views: {len(player_views)}, team_views: {len(team_views)}, page_views: {len(page_views_raw)}")

        # Filter to only flat int/float values (Firebase may have nested dicts)
        # Sort descending and limit to top entries
        page_views = dict(sorted(
            ((k, v) for k, v in page_views_raw.items() if isinstance(v, (int, float))),
            key=lambda x: x[1], reverse=True
        )[:25])

        # Sort player/team views descending, take top 20
        player_views_sorted = dict(sorted(
            ((k, v) for k, v in player_views.items() if isinstance(v, (int, float))),
            key=lambda x: x[1], reverse=True
        )[:20]) if player_views else {}
        team_views_sorted = dict(sorted(
            ((k, v) for k, v in team_views.items() if isinstance(v, (int, float))),
            key=lambda x: x[1], reverse=True
        )[:20]) if team_views else {}

        # Calculate totals
        total_requests = 0
        for day_data in daily_stats.values():
            if isinstance(day_data, dict):
                total_requests += day_data.get('total_requests', 0)
            elif isinstance(day_data, (int, float)):
                total_requests += day_data

        total_player_views = sum(v for v in player_views.values() if isinstance(v, (int, float)))
        total_team_views = sum(v for v in team_views.values() if isinstance(v, (int, float)))
        total_page_views = sum(v for v in page_views.values() if isinstance(v, (int, float)))

        data = {
            'daily_stats': daily_stats,
            'player_views': player_views_sorted,
            'team_views': team_views_sorted,
            'page_views': page_views,
            'match_preview_views': match_preview_views,
            'totals': {
                'requests': total_requests,
                'player_views': total_player_views,
                'team_views': total_team_views,
                'page_views': total_page_views,
            },
            'is_production': True,
        }

        # Admin-only data
        if include_admin:
            errors = db_ref.child('errors').get() or {}
            detailed_logs_today = {}
            today = datetime.now().strftime('%Y-%m-%d')
            try:
                detailed_logs_today = db_ref.child(f'detailed_logs/{today}').get() or {}
            except Exception:
                pass

            # Get recent errors (last 50)
            error_list = []
            for error_id, error_data in errors.items():
                if isinstance(error_data, dict):
                    error_data['id'] = error_id
                    error_list.append(error_data)
            error_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            error_list = error_list[:50]

            # Get detailed log entries
            log_list = []
            for log_id, log_data in detailed_logs_today.items():
                if isinstance(log_data, dict):
                    log_data['id'] = log_id
                    log_list.append(log_data)
            log_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            log_list = log_list[:100]

            # Calculate performance metrics from detailed logs
            response_times = [
                entry.get('response_time_ms', 0)
                for entry in log_list
                if entry.get('response_time_ms')
            ]
            avg_response_time = round(sum(response_times) / len(response_times), 1) if response_times else 0
            max_response_time = max(response_times) if response_times else 0

            # User agent breakdown
            user_agents = {}
            methods = {}
            status_codes = {}
            for entry in log_list:
                ua = _parse_device(entry.get('user_agent', ''))
                user_agents[ua] = user_agents.get(ua, 0) + 1

                method = entry.get('method', 'UNKNOWN')
                methods[method] = methods.get(method, 0) + 1

                status = str(entry.get('status_code', 0))
                status_bucket = status[0] + 'xx' if len(status) == 3 else status
                status_codes[status_bucket] = status_codes.get(status_bucket, 0) + 1

            data['errors'] = error_list
            data['error_count'] = len(errors)
            data['detailed_logs'] = log_list
            data['performance'] = {
                'avg_response_ms': avg_response_time,
                'max_response_ms': max_response_time,
                'sample_count': len(response_times),
            }
            data['user_agents'] = dict(sorted(user_agents.items(), key=lambda x: x[1], reverse=True))
            data['methods'] = methods
            data['status_codes'] = status_codes

        return data

    except Exception as e:
        import traceback
        print(f"[Analytics] ERROR fetching analytics data: {e}")
        traceback.print_exc()
        return {
            'daily_stats': {},
            'player_views': {},
            'team_views': {},
            'page_views': {},
            'match_preview_views': {},
            'totals': {'requests': 0, 'player_views': 0, 'team_views': 0, 'page_views': 0},
            'is_production': True,
            'errors': [],
            'error_count': 0,
            'detailed_logs': [],
            'performance': {'avg_response_ms': 0, 'max_response_ms': 0, 'sample_count': 0},
            'user_agents': {},
            'methods': {},
            'status_codes': {},
        }


def _parse_device(user_agent: str) -> str:
    """Parse user agent string into a simple device category."""
    ua = user_agent.lower()
    if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
        return 'Mobile'
    elif 'tablet' in ua or 'ipad' in ua:
        return 'Tablet'
    elif 'bot' in ua or 'crawler' in ua or 'spider' in ua:
        return 'Bot'
    elif ua:
        return 'Desktop'
    return 'Unknown'


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request, user=Depends(get_current_user)):
    """Analytics Dashboard page — public with admin-only sections."""
    is_admin = _check_admin(user)
    analytics_data = get_analytics_data(include_admin=is_admin)

    return templates.TemplateResponse(request=request, name="analytics.html", context={
        "request": request,
        "user": user,
        "is_admin": is_admin,
        "analytics_data": analytics_data,
        "is_production": IS_PRODUCTION,
    })

