from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
import pandas as pd
from typing import Optional

router = APIRouter()

# Cache for search data
_search_cache = {
    'players': None,
    'teams': None,
    'last_update': None
}

def load_search_data():
    """Load and cache data for searching"""
    import time
    current_time = time.time()

    # Refresh cache every 5 minutes
    if _search_cache['last_update'] and (current_time - _search_cache['last_update']) < 300:
        return _search_cache

    try:
        # Load players
        players_df = pd.read_csv('data/season_player_stats.csv', encoding='utf-8-sig')
        # Get unique players with their teams (from Total row)
        players_total = players_df[players_df['Season'] == 'Total'][['Name', 'Team']].drop_duplicates()
        _search_cache['players'] = players_total.to_dict('records')

        # Load teams
        standings_df = pd.read_csv('data/season_standings.csv', encoding='utf-8-sig')
        teams = standings_df['Team'].unique().tolist()
        _search_cache['teams'] = teams

        _search_cache['last_update'] = current_time
    except Exception as e:
        print(f"Error loading search data: {e}")
        if _search_cache['players'] is None:
            _search_cache['players'] = []
        if _search_cache['teams'] is None:
            _search_cache['teams'] = []

    return _search_cache


@router.get("/api/search")
async def global_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results per category")
):
    """
    Global search across players, teams, and matches.
    Returns categorized results with relevance scoring.
    """
    query = q.lower().strip()

    if len(query) < 1:
        return JSONResponse(content={"results": [], "total": 0})

    data = load_search_data()
    results = []

    # Search players
    player_results = []
    for player in data['players']:
        name = player['Name'].lower()
        team = player.get('Team', '').lower() if player.get('Team') else ''

        # Calculate relevance score
        score = 0
        if name == query:
            score = 100  # Exact match
        elif name.startswith(query):
            score = 80  # Starts with query
        elif query in name:
            score = 60  # Contains query
        elif team and query in team:
            score = 40  # Team match

        if score > 0:
            player_results.append({
                'type': 'player',
                'name': player['Name'],
                'team': player.get('Team', ''),
                'url': f"/players/{player['Name']}",
                'score': score,
                'icon': 'fa-user'
            })

    # Sort by score and limit
    player_results.sort(key=lambda x: x['score'], reverse=True)
    results.extend(player_results[:limit])

    # Search teams
    team_results = []
    for team in data['teams']:
        team_lower = team.lower()

        score = 0
        if team_lower == query:
            score = 100
        elif team_lower.startswith(query):
            score = 80
        elif query in team_lower:
            score = 60

        if score > 0:
            team_results.append({
                'type': 'team',
                'name': team,
                'url': f"/teams/{team}",
                'score': score,
                'icon': 'fa-users'
            })

    team_results.sort(key=lambda x: x['score'], reverse=True)
    results.extend(team_results[:limit])

    # Add quick action suggestions based on query
    quick_actions = []

    # Stats-related queries
    stats_keywords = ['stats', 'statistics', 'leaderboard', 'top', 'best', 'scorer', 'goal']
    if any(kw in query for kw in stats_keywords):
        quick_actions.append({
            'type': 'action',
            'name': 'View Statistics Dashboard',
            'url': '/statistics',
            'icon': 'fa-chart-bar',
            'score': 50
        })

    # Match-related queries
    match_keywords = ['match', 'game', 'fixture', 'schedule', 'result', 'standing']
    if any(kw in query for kw in match_keywords):
        quick_actions.append({
            'type': 'action',
            'name': 'View Matches & Standings',
            'url': '/matches',
            'icon': 'fa-futbol',
            'score': 50
        })

    # Fantasy-related queries
    fantasy_keywords = ['fantasy', 'fpl', 'draft', 'transfer', 'captain']
    if any(kw in query for kw in fantasy_keywords):
        quick_actions.append({
            'type': 'action',
            'name': 'Fantasy League',
            'url': '/fantasy',
            'icon': 'fa-trophy',
            'score': 50
        })

    results.extend(quick_actions)

    # Sort all results by score
    results.sort(key=lambda x: x['score'], reverse=True)

    # Group results by type for frontend
    grouped = {
        'players': [r for r in results if r['type'] == 'player'][:5],
        'teams': [r for r in results if r['type'] == 'team'][:5],
        'actions': [r for r in results if r['type'] == 'action'][:3]
    }

    return JSONResponse(content={
        'results': grouped,
        'total': len(results),
        'query': q
    })


@router.get("/api/search/suggestions")
async def search_suggestions(
    q: str = Query(..., min_length=1, description="Partial query for suggestions")
):
    """Get autocomplete suggestions for search"""
    query = q.lower().strip()

    if len(query) < 1:
        return JSONResponse(content={"suggestions": []})

    data = load_search_data()
    suggestions = []

    # Get player name suggestions
    for player in data['players']:
        name = player['Name']
        if query in name.lower():
            suggestions.append({
                'text': name,
                'type': 'player',
                'url': f"/players/{name}"
            })

    # Get team suggestions
    for team in data['teams']:
        if query in team.lower():
            suggestions.append({
                'text': team,
                'type': 'team',
                'url': f"/teams/{team}"
            })

    # Sort by relevance (starts with > contains)
    suggestions.sort(key=lambda x: (
        0 if x['text'].lower().startswith(query) else 1,
        x['text'].lower()
    ))

    return JSONResponse(content={
        'suggestions': suggestions[:10]
    })
