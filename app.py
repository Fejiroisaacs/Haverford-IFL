from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.errors import ServerErrorMiddleware
import firebase_admin
from firebase_admin import credentials, auth, storage, db
from starlette.responses import HTMLResponse, FileResponse, RedirectResponse
from routers import matches, signup, login, contact, fantasy, players, settings, teams, admin
import json, os
import pandas as pd
from datetime import datetime, timedelta
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from middleware import RequestLoggingMiddleware

load_dotenv()

firebase_config_str = os.getenv("FIREBASE_CONFIG")
firebase_config = json.loads(firebase_config_str)
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)

db = db.reference('/')
bucket = storage.bucket()

secret_key = os.getenv("SECRET_KEY")

app = FastAPI()

app.mount("/static", StaticFiles(directory="templates/static"), name="static")

user = None
templates = Jinja2Templates(directory="templates")

@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)

    if request.url.path.startswith('/static/'):
        path = request.url.path.lower()

        # Images: cache for 1 year
        if any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico']):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

        # Fonts: cache for 1 year
        elif any(path.endswith(ext) for ext in ['.woff', '.woff2', '.ttf', '.otf', '.eot']):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

        # CSS/JS: cache for 1 week
        elif any(path.endswith(ext) for ext in ['.css', '.js']):
            response.headers["Cache-Control"] = "public, max-age=604800"

        # Other static files: cache for 1 day
        else:
            response.headers["Cache-Control"] = "public, max-age=86400"

    return response

# Add middleware (order matters - logging should be first)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SessionMiddleware, secret_key=secret_key)

app.include_router(matches.router, dependencies=[Depends(lambda: db)])
app.include_router(signup.router, dependencies=[Depends(lambda: db), Depends(lambda: auth)])
app.include_router(login.router, dependencies=[Depends(lambda: db), Depends(lambda: auth)])
app.include_router(contact.router)
app.include_router(fantasy.router, dependencies=[Depends(lambda: db), Depends(lambda: auth)])
app.include_router(players.router, dependencies=[Depends(lambda: db)])
app.include_router(settings.router)
app.include_router(teams.router, dependencies=[Depends(lambda: db)])
app.include_router(admin.router)

_data_cache = {
    'schedule': None,
    'results': None,
    'standings': None,
    'player_stats': None,
    'last_updated': None
}

CACHE_DURATION_MINUTES = 30

def get_cached_data():
    """Load and cache CSV data. Refresh cache if expired."""
    global _data_cache

    now = datetime.now()
    if (_data_cache['last_updated'] is None or
        (now - _data_cache['last_updated']) > timedelta(minutes=CACHE_DURATION_MINUTES)):

        try:
            _data_cache['schedule'] = pd.read_csv('data/F25 Futsal Schedule.csv')
            _data_cache['results'] = pd.read_csv('data/Match_Results.csv')
            _data_cache['standings'] = pd.read_csv('data/season_standings.csv')
            _data_cache['player_stats'] = pd.read_csv('data/season_player_stats.csv')
            _data_cache['last_updated'] = now
            print(f"Cache refreshed at {now}")
        except Exception as e:
            print(f"Error loading data: {e}")
            if _data_cache['schedule'] is None:
                _data_cache['schedule'] = pd.DataFrame()
                _data_cache['results'] = pd.DataFrame()
                _data_cache['standings'] = pd.DataFrame()
                _data_cache['player_stats'] = pd.DataFrame()

    return _data_cache

# Helper functions for homepage
def get_season_progress(season=6):
    """Calculate season progress based on matchdays completed"""
    try:
        data = get_cached_data()
        schedule = data['schedule']
        results = data['results'][data['results']['Season'] == season]

        total_matchdays = schedule['MD'].max() if not schedule.empty else 10
        completed_matchdays = schedule['MD'].min() - 1 if not schedule.empty else 0
        total_matches_scheduled = len(schedule)
        matches_played = len(results)
        return {
            'current_matchday': int(completed_matchdays) if not pd.isna(completed_matchdays) else 0,
            'total_matchdays': int(total_matchdays),
            'matches_played': matches_played,
            'total_matches': total_matches_scheduled
        }
    except Exception as e:
        print(f"Error in get_season_progress: {e}")
        return {'current_matchday': 0, 'total_matchdays': 10, 'matches_played': 0, 'total_matches': 0}

def get_next_matchday():
    """Get next upcoming matchday with fixtures"""
    try:
        data = get_cached_data()
        schedule = data['schedule']
        results_s6 = data['results'][data['results']['Season'] == '6']

        # Get completed match IDs
        if not results_s6.empty and 'Match ID' in results_s6.columns:
            completed_ids = set(results_s6['Match ID'].dropna().tolist())
        else:
            completed_ids = set()

        # Filter for upcoming matches
        upcoming = schedule[~schedule.apply(lambda row: f"{row['Team 1']} vs {row['Team 2']}" in
                                            [f"{r['Team 1']} vs {r['Team 2']}" for _, r in results_s6.iterrows()], axis=1)]

        if upcoming.empty:
            return {'matchday': None, 'date': None, 'matches': []}

        # Get next matchday
        next_md = upcoming['MD'].min()
        next_matches = upcoming[upcoming['MD'] == next_md]

        matches_list = []
        for _, match in next_matches.iterrows():
            matches_list.append({
                'team1': match['Team 1'],
                'team2': match['Team 2'],
                'day': match['Day'],
                'time': match['Time']
            })

        return {
            'matchday': int(next_md),
            'date': next_matches.iloc[0]['Day'] if not next_matches.empty else None,
            'matches': matches_list[:5]  # Limit to 5 matches
        }
    except Exception as e:
        print(f"Error in get_next_matchday: {e}")
        return {'matchday': None, 'date': None, 'matches': []}

def get_group_leaders(season=6):
    """Get top 2 teams from each group"""
    try:
        data = get_cached_data()
        standings = data['standings'][data['standings']['Season'] == season]

        leaders = {}
        for group in ['A', 'B', 'C']:
            group_standings = standings[standings['Group'] == group].sort_values(
                by=['PTS', 'GD'], ascending=[False, False]
            ).head(2)

            leaders[group] = group_standings[['Team', 'MP', 'W', 'D', 'L', 'PTS', 'GD']].to_dict('records')

        return leaders
    except Exception as e:
        print(f"Error in get_group_leaders: {e}")
        return {'A': [], 'B': [], 'C': []}

def get_latest_results(season=6, limit=4):
    """Get most recent completed matches"""
    try:
        data = get_cached_data()
        results = data['results'][data['results']['Season'] == season]

        if results.empty:
            return []

        # Sort by MD (matchday) descending to get latest matches
        results = results.sort_values(by='Match ID', ascending=False).head(limit)

        matches_list = []
        for _, match in results.iterrows():
            matches_list.append({
                'team1': match['Team 1'],
                'team2': match['Team 2'],
                'score': f"{match['Score Team 1']} - {match['Score Team 2']}",
                'group': match['Group'],
                'match_id': match.get('Match ID', '')
            })

        return matches_list
    except Exception as e:
        print(f"Error in get_latest_results: {e}")
        return []

def get_season_stats(season=6):
    """Calculate aggregate season statistics"""
    try:
        data = get_cached_data()
        results = data['results'][data['results']['Season'] == season]
        standings = data['standings'][data['standings']['Season'] == season]

        if results.empty:
            return {'total_goals': 0, 'avg_goals': 0, 'biggest_win': 'TBD', 'total_teams': 0}

        # Calculate total goals from standings
        total_goals = standings['GF'].astype(int).sum() if 'GF' in standings.columns else 0
        matches_played = len(results)
        avg_goals = round(total_goals / matches_played, 1) if matches_played > 0 else 0

        # Find biggest win
        biggest_margin = 0
        biggest_win_str = 'TBD'
        for _, match in results.iterrows():
            goals = [match['Score Team 1'], match['Score Team 2']]
            try:
                margin = abs(int(goals[0]) - int(goals[1]))
                if margin > biggest_margin:
                    biggest_margin = margin
                    biggest_win_str = f"{match['Team 1']} {goals[0]} - {goals[1]} {match['Team 2']}"
            except:
                pass

        total_teams = len(standings['Team'].unique()) if not standings.empty else 18
        return {
            'total_goals': int(total_goals),
            'avg_goals': avg_goals,
            'biggest_win': biggest_win_str,
            'total_teams': total_teams
        }
    except Exception as e:
        print(f"Error in get_season_stats: {e}")
        return {'total_goals': 0, 'avg_goals': 0, 'biggest_win': 'TBD', 'total_teams': 18}

def get_season_top_performers(season='6'):
    """Get top 3 players for goals, assists, and saves"""
    try:
        data = get_cached_data()
        stats = data['player_stats'][data['player_stats']['Season'] == season]

        if stats.empty:
            return {'scorers': [], 'assisters': [], 'goalkeepers': []}

        # Top scorers
        scorers = stats.nlargest(3, 'Goals')[['Name', 'Team', 'Goals']].to_dict('records')

        # Top assisters
        assisters = stats.nlargest(3, 'Assists')[['Name', 'Team', 'Assists']].to_dict('records')

        # Top goalkeepers (by saves)
        goalkeepers = stats.nlargest(3, 'Saves')[['Name', 'Team', 'Saves']].to_dict('records')

        return {
            'scorers': scorers,
            'assisters': assisters,
            'goalkeepers': goalkeepers
        }
    except Exception as e:
        print(f"Error in get_season_top_performers: {e}")
        return {'scorers': [], 'assisters': [], 'goalkeepers': []}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    try:
        if exc.status_code == 404:
            return templates.TemplateResponse("404error.html", {"request": request, "error": f"{exc.status_code} {str(exc.detail)}"})
    except Exception:
        return templates.TemplateResponse("error.html", {"request": request})
    
app.add_middleware(ServerErrorMiddleware, handler=http_exception_handler)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    try:
        if exc.status_code == 404:
            return templates.TemplateResponse("404error.html", {"request": request, "error": f"{exc.status_code} {str(exc.detail)}"})
    except Exception as e:
        return templates.TemplateResponse("error.html", {"request": request})

@app.exception_handler(HTTPException) 
async def http_exception_handler(request: Request, exc: HTTPException): 
    if exc.status_code == 401: 
        return RedirectResponse(url="/login") 
    return templates.TemplateResponse("login.html", {"request": request, "user": None, "Login": True})

@app.get("/", response_class=HTMLResponse)
@app.get("/index", response_class=HTMLResponse)
@app.get("/home", response_class=HTMLResponse)
async def read_root(request: Request):
    # Get all dynamic data for Season 6
    season_progress = get_season_progress()
    next_matchday = get_next_matchday()
    group_leaders = get_group_leaders()
    latest_results = get_latest_results()
    season_stats = get_season_stats()
    top_performers = get_season_top_performers()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "season_progress": season_progress,
        "next_matchday": next_matchday,
        "group_leaders": group_leaders,
        "latest_results": latest_results,
        "season_stats": season_stats,
        "top_performers": top_performers
    })

@app.get("/pdf")
async def get_pdf():
    return FileResponse("data/IFL_Rule_Book.pdf")

@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    content = """User-agent: *
    Allow: /
    Sitemap: https://quickest-doralyn-haverford-167803e3.koyeb.app/sitemap.xml
    """
    return Response(content=content, media_type="text/plain")

@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    urls = [
        "https://quickest-doralyn-haverford-167803e3.koyeb.app/",
        "https://quickest-doralyn-haverford-167803e3.koyeb.app/teams",
        "https://quickest-doralyn-haverford-167803e3.koyeb.app/matches",
        "https://quickest-doralyn-haverford-167803e3.koyeb.app/players"
    ]

    xml_content = """<?xml version="1.0" encoding="UTF-8"?>\n"""
    xml_content += """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n"""

    for url in set(urls):
        xml_content += f"""    <url>
        <loc>{url}</loc>
        <priority>0.8</priority>
    </url>\n"""

    xml_content += """</urlset>"""

    return Response(content=xml_content, media_type="application/xml")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
