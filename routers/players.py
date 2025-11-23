from fastapi import APIRouter, Request, Cookie, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from firebase_admin import db as firebase_db
from starlette.responses import HTMLResponse
import pandas as pd
from functions import get_k_recent_potm, get_player_potm
import time
from collections import defaultdict

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Data caching system
class DataCache:
    def __init__(self, ttl=300):  # 5 minutes TTL by default
        self.cache = {}
        self.timestamps = {}
        self.ttl = ttl

    def get(self, key, loader_func):
        """Get data from cache or load it using loader_func"""
        current_time = time.time()

        # Check if cached and not expired
        if key in self.cache and key in self.timestamps:
            if current_time - self.timestamps[key] < self.ttl:
                return self.cache[key]

        # Load fresh data
        data = loader_func()
        self.cache[key] = data
        self.timestamps[key] = current_time
        return data

    def invalidate(self, key=None):
        """Invalidate cache for a specific key or all keys"""
        if key:
            self.cache.pop(key, None)
            self.timestamps.pop(key, None)
        else:
            self.cache.clear()
            self.timestamps.clear()

# Initialize cache
data_cache = DataCache(ttl=6000)

# Cache loader functions
def load_player_ratings():
    return pd.read_csv('data/player_ratings.csv')

def load_season_player_stats():
    return pd.read_csv('data/season_player_stats.csv')

def load_player_match_stats():
    return pd.read_csv('data/player_match_stats.csv')

def load_match_results():
    return pd.read_csv('data/Match_Results.csv')

def load_ifl_awards():
    return pd.read_csv('data/IFL_Awards.csv', encoding='utf-8-sig')

# Get current season, filtering out 'Total' and non-numeric values
season_data = data_cache.get('season_player_stats', load_season_player_stats)
valid_seasons = [s for s in season_data['Season'].unique() if s != 'Total' and str(s).replace('.', '').isdigit()]
CURRENT_SEASON = max(valid_seasons) if valid_seasons else 1

# Pagination settings
PLAYERS_PER_PAGE = 8

# Simple rate limiting
_api_calls = defaultdict(list)
API_RATE_LIMIT = 10  # 10 calls per minute
API_WINDOW = 60  # 60 seconds

@router.get("/players", response_class=HTMLResponse)
async def read_players(request: Request, session: int = None, page: int = 1, position_filter: str = None, sort_by: str = None, session_token: str = Cookie(None), db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    # Get selected season (default to current)
    selected_season = session if session else CURRENT_SEASON

    # Get all players with stats for the selected season with filters/sorting
    pagination_result = get_all_players_with_stats(
        selected_season,
        page=page,
        position_filter=position_filter,
        sort_by=sort_by
    )

    players_with_stats = pagination_result['players']
    total_pages = pagination_result['total_pages']
    total_count = pagination_result['total_count']
    current_page = page

    # Get available seasons
    all_seasons = get_all_seasons()

    # Get league leaders for the selected season
    league_leaders = get_league_leaders(selected_season)

    # Get POTM highlights
    potm_images = get_k_recent_potm(k=5, season=selected_season)

    return templates.TemplateResponse("players.html", {"request": request,
                                                       "Players": players_with_stats,
                                                       'potm_images': potm_images,
                                                       "count": total_count,
                                                       "league_leaders": league_leaders,
                                                       "current_season": CURRENT_SEASON,
                                                       "selected_season": selected_season,
                                                       "all_seasons": all_seasons,
                                                       "current_page": current_page,
                                                       "total_pages": total_pages,
                                                       "position_filter": position_filter,
                                                       "sort_by": sort_by})
    
@router.get("/players/{player}", response_class=HTMLResponse)
async def get_player(request: Request, player: str, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    player_rating_data = get_player_rating_stats(player)
    season_data = get_player_season_data(player)
    potm_images = get_player_potm(player)
    awards = get_awards(player)
    previous_matches = get_previous_matches(player)

    # Get all new enhanced statistics
    career_totals = get_career_totals(player)
    best_performances = get_best_performances(player)
    recent_form = get_recent_form(player, num_matches=5)
    league_rankings = get_league_rankings(player)
    team_contribution = get_team_contribution(player)
    teammates = get_teammates(player)
    opponent_stats = get_opponent_stats(player)
    previous_teams = get_previous_teams(player)

    if player_rating_data:
        return templates.TemplateResponse("player.html", {
            "request": request,
            "rating_data": player_rating_data,
            'potm_images': potm_images,
            'season_data': season_data,
            'awards': awards,
            'previous_matches': previous_matches,
            'career_totals': career_totals,
            'best_performances': best_performances,
            'recent_form': recent_form,
            'league_rankings': league_rankings,
            'team_contribution': team_contribution,
            'teammates': teammates,
            'opponent_stats': opponent_stats,
            'previous_teams': previous_teams
        })
    else:
        return templates.TemplateResponse("404error.html", {"request": request, 'error': f'Player {player} not found'})

@router.get("/api/players/{player}")
async def get_player_data(player: str, request: Request, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    """API endpoint to get player data as JSON for fantasy modal"""
    
    # Simple rate limiting by IP
    client_ip = request.client.host
    current_time = time.time()
    
    # Clean old requests
    _api_calls[client_ip] = [
        call_time for call_time in _api_calls[client_ip] 
        if current_time - call_time < API_WINDOW
    ]
    
    # Check rate limit
    if len(_api_calls[client_ip]) >= API_RATE_LIMIT:
        raise HTTPException(
            status_code=429, 
            detail="Too many requests. Please try again later."
        )
    
    # Record this request
    _api_calls[client_ip].append(current_time)
    
    try:
        player = player.replace("  ", " ").strip()
        player_rating_data = get_player_rating_stats(player)
        season_data = get_player_season_data(player)
        awards = get_awards(player)
        previous_matches = get_previous_matches(player)
        
        if not player_rating_data:
            return JSONResponse(
                status_code=404,
                content={"error": f"Player {player} not found"}
            )
        latest_season_data = season_data[-2] if season_data else {}
        
        recent_matches = []
        if previous_matches:
            all_matches = []
            for season_matches in previous_matches.values():
                all_matches.extend(season_matches)
            recent_matches = sorted(all_matches, key=lambda x: (x.get('Season', 0), x.get('Match ID', 0)), reverse=True)[:5]
        
        response_data = {
            "name": player_rating_data.get("Name", ""),
            "team": player_rating_data.get("Latest Team", "N/A"),
            "position": player_rating_data.get("Primary Position", "N/A"),
            "overall": player_rating_data.get("OVR Rating", 0),
            "ratings": {
                "attack": player_rating_data.get("ATT Rating", 0),
                "assist": player_rating_data.get("AST Rating", 0),
                "defense": player_rating_data.get("DEF Rating", 0),
                "goalkeeping": player_rating_data.get("GLK Rating", 0)
            },
            "season_stats": {
                "goals": latest_season_data.get("Goals", 0),
                "assists": latest_season_data.get("Assists", 0),
                "saves": latest_season_data.get("Saves", 0),
                "matches_played": latest_season_data.get("MP", 0),
                "record": latest_season_data.get("Record", "N/A")
            },
            "potm_count": player_rating_data.get("POTM", 0),
            "awards": awards or [],
            "recent_matches": recent_matches
        }
        return JSONResponse(content=response_data)
        
    except Exception as e:
        print(f"Error fetching player data: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error fetching player data: {str(e)}"}
        )

@router.get("/player_search", response_class=HTMLResponse)
async def search_players(request: Request, query: str, session: int = None, page: int = 1, position_filter: str = None, sort_by: str = None, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    # Get selected season (default to current)
    selected_season = session if session else CURRENT_SEASON

    # Get all players with stats for searching (no pagination here since we need to filter first)
    all_players_result = get_all_players_with_stats(selected_season, page=None, position_filter=position_filter, sort_by=sort_by)
    all_players = all_players_result['players']
    filtered_players = [player for player in all_players if query.lower() in player['Name'].lower()]

    # Apply pagination to filtered results
    total_count = len(filtered_players)
    total_pages = (total_count + PLAYERS_PER_PAGE - 1) // PLAYERS_PER_PAGE if total_count > 0 else 1
    start_idx = (page - 1) * PLAYERS_PER_PAGE
    end_idx = start_idx + PLAYERS_PER_PAGE
    paginated_players = filtered_players[start_idx:end_idx]
    current_page = page

    # Get available seasons
    all_seasons = get_all_seasons()

    # Get league leaders for the selected season
    league_leaders = get_league_leaders(selected_season)

    # Get POTM highlights
    potm_images = get_k_recent_potm(k=5, season=selected_season)

    return templates.TemplateResponse("players.html", {"request": request,
                                                       "Players": paginated_players,
                                                       'potm_images': potm_images,
                                                       "count": total_count,
                                                       "league_leaders": league_leaders,
                                                       "current_season": CURRENT_SEASON,
                                                       "selected_season": selected_season,
                                                       "all_seasons": all_seasons,
                                                       "current_page": current_page,
                                                       "total_pages": total_pages,
                                                       "search_query": query,
                                                       "position_filter": position_filter,
                                                       "sort_by": sort_by})

def get_player_season_data(player):
    data = data_cache.get('season_player_stats', load_season_player_stats)
    data = data[data['Name'] == player]
    data = data[data['Team'] != 0]

    return data.to_dict(orient='records')

def get_player_rating_stats(player):
    data = data_cache.get('player_ratings', load_player_ratings)
    data = data[data['Name'] == player]

    return data.to_dict(orient='records')[0] if data.shape[0] > 0 else None
    
def get_players():
    data = data_cache.get('player_ratings', load_player_ratings)
    data.drop_duplicates(subset=['Name'])

    return data[['Name', 'Latest Team']].to_dict(orient='records')

def get_awards(player):
    data = data_cache.get('ifl_awards', load_ifl_awards)
    data = data[data['Name'] == player][['Award']]

    return data['Award'].to_list() if data.shape[0] > 0 else None

def get_previous_matches(player, season=False):
    data = data_cache.get('player_match_stats', load_player_match_stats)
    data = data[data['Name'] == player][['Season', 'My Team', 'Match ID', 'Opponent', 'External Sub', 'P', 'Y-R', 'POTM', 'G', 'A', 'S']]

    if data.shape[0] > 0:
        result = {}
        for season, group in data.groupby('Season'):
            if not season:
                result[season] = group.drop(columns='Season').to_dict(orient='records')
            else:
                result[season] = group.to_dict(orient='records')
        return result
    else:
        return None

def get_career_totals(player):
    """Calculate career totals for a player"""
    season_data = data_cache.get('season_player_stats', load_season_player_stats)
    player_data = season_data[(season_data['Name'] == player) & (season_data['Season'] == "Total")]
    match_data = data_cache.get('player_match_stats', load_player_match_stats)
    player_matches = match_data[match_data['Name'] == player]

    if player_data.empty:
        return None
    # Calculate totals
    total_goals = int(player_data['Goals'].sum())
    total_assists = int(player_data['Assists'].sum())
    total_saves = int(player_data['Saves'].sum())
    total_potm = int(player_data['POTM'].sum())
    total_matches = int(player_data['MP'].sum())

    # Parse Y-R cards (format: "Y-R")
    total_yellows = 0
    total_reds = 0
    for yr in player_data['Y-R'].dropna():
        if '-' in str(yr):
            parts = str(yr).split('-')
            total_yellows += int(parts[0]) if parts[0].isdigit() else 0
            total_reds += int(parts[1]) if parts[1].isdigit() else 0

    # Calculate win/loss/draw record from match data
    wins = 0
    draws = 0
    losses = 0

    matches_df = data_cache.get('match_results', load_match_results)
    for _, match in player_matches.iterrows():
        match_id = match['Match ID']
        team = match['My Team']
        match_result = matches_df[matches_df['Match ID'] == match_id]

        if not match_result.empty:
            match_result = match_result.iloc[0]
            if match_result['Team 1'] == team and match_result['Win Team 1'] == 1:
                wins += 1
            elif match_result['Team 2'] == team and match_result['Win Team 2'] == 1:
                wins += 1
            elif match_result['Win Team 1'] == 0 and match_result['Win Team 2'] == 0:
                draws += 1
            else:
                losses += 1

    # Calculate averages
    goals_per_game = round(total_goals / total_matches, 2) if total_matches > 0 else 0
    assists_per_game = round(total_assists / total_matches, 2) if total_matches > 0 else 0
    saves_per_game = round(total_saves / total_matches, 2) if total_matches > 0 else 0
    win_rate = round((wins / total_matches) * 100, 1) if total_matches > 0 else 0

    return {
        'total_goals': total_goals,
        'total_assists': total_assists,
        'total_saves': total_saves,
        'total_potm': total_potm,
        'total_matches': total_matches,
        'total_yellows': total_yellows,
        'total_reds': total_reds,
        'wins': wins,
        'draws': draws,
        'losses': losses,
        'win_rate': win_rate,
        'goals_per_game': goals_per_game,
        'assists_per_game': assists_per_game,
        'saves_per_game': saves_per_game
    }

def get_best_performances(player):
    """Get player's best individual performances"""
    match_data = data_cache.get('player_match_stats', load_player_match_stats)
    player_matches = match_data[match_data['Name'] == player].copy()

    if player_matches.empty:
        return None

    # Best goals in a match
    best_goals_match = player_matches.nlargest(1, 'G')
    best_goals = {
        'goals': int(best_goals_match['G'].values[0]),
        'opponent': best_goals_match['Opponent'].values[0],
        'season': best_goals_match['Season'].values[0],
        'match_id': int(best_goals_match['Match ID'].values[0]),
        'team': best_goals_match['My Team'].values[0]
    } if not best_goals_match.empty and best_goals_match['G'].values[0] > 0 else None

    # Best assists in a match
    best_assists_match = player_matches.nlargest(1, 'A')
    best_assists = {
        'assists': int(best_assists_match['A'].values[0]),
        'opponent': best_assists_match['Opponent'].values[0],
        'season': best_assists_match['Season'].values[0],
        'match_id': int(best_assists_match['Match ID'].values[0]),
        'team': best_assists_match['My Team'].values[0]
    } if not best_assists_match.empty and best_assists_match['A'].values[0] > 0 else None

    # Best saves in a match
    best_saves_match = player_matches.nlargest(1, 'S')
    best_saves = {
        'saves': int(best_saves_match['S'].values[0]),
        'opponent': best_saves_match['Opponent'].values[0],
        'season': best_saves_match['Season'].values[0],
        'match_id': int(best_saves_match['Match ID'].values[0]),
        'team': best_saves_match['My Team'].values[0]
    } if not best_saves_match.empty and best_saves_match['S'].values[0] > 0 else None

    # Most goal contributions (G+A) in a match
    player_matches['contributions'] = player_matches['G'] + player_matches['A']
    best_contributions_match = player_matches.nlargest(1, 'contributions')
    best_contributions = {
        'goals': int(best_contributions_match['G'].values[0]),
        'assists': int(best_contributions_match['A'].values[0]),
        'total': int(best_contributions_match['contributions'].values[0]),
        'opponent': best_contributions_match['Opponent'].values[0],
        'season': best_contributions_match['Season'].values[0],
        'match_id': int(best_contributions_match['Match ID'].values[0]),
        'team': best_contributions_match['My Team'].values[0]
    } if not best_contributions_match.empty and best_contributions_match['contributions'].values[0] > 0 else None

    return {
        'best_goals': best_goals,
        'best_assists': best_assists,
        'best_saves': best_saves,
        'best_contributions': best_contributions
    }

def get_recent_form(player, num_matches=5):
    """Get recent match form for the player"""
    match_data = data_cache.get('player_match_stats', load_player_match_stats)
    player_matches = match_data[match_data['Name'] == player].copy()
    matches_df = data_cache.get('match_results', load_match_results)

    if player_matches.empty:
        return None

    # Sort by season and match ID descending
    player_matches = player_matches.sort_values(['Season', 'Match ID'], ascending=[False, False])
    recent_matches = player_matches.head(num_matches)

    form = []
    for _, match in recent_matches.iterrows():
        match_id = match['Match ID']
        team = match['My Team']
        opponent = match['Opponent']

        # Get match result
        match_result = matches_df[matches_df['Match ID'] == match_id]
        if not match_result.empty:
            match_result = match_result.iloc[0]
            result = 'D'  # Default draw

            if match_result['Team 1'] == team:
                if match_result['Win Team 1'] == 1:
                    result = 'W'
                elif match_result['Win Team 2'] == 1:
                    result = 'L'
            else:
                if match_result['Win Team 2'] == 1:
                    result = 'W'
                elif match_result['Win Team 1'] == 1:
                    result = 'L'

            form.append({
                'result': result,
                'opponent': opponent,
                'goals': int(match['G']),
                'assists': int(match['A']),
                'saves': int(match['S']),
                'potm': bool(match['POTM']),
                'season': match['Season'],
                'match_id': int(match_id)
            })

    return form

def get_league_rankings(player):
    """Get player's rankings in various league-wide categories"""
    season_data = data_cache.get('season_player_stats', load_season_player_stats)

    # Calculate career totals for all players
    all_players_totals = season_data.groupby('Name').agg({
        'Goals': 'sum',
        'Assists': 'sum',
        'Saves': 'sum',
        'POTM': 'sum',
        'MP': 'sum'
    }).reset_index()

    # Calculate per-game stats
    all_players_totals['Goals_Per_Game'] = all_players_totals['Goals'] / all_players_totals['MP']
    all_players_totals['Assists_Per_Game'] = all_players_totals['Assists'] / all_players_totals['MP']
    all_players_totals['Saves_Per_Game'] = all_players_totals['Saves'] / all_players_totals['MP']

    # Get player's data
    player_stats = all_players_totals[all_players_totals['Name'] == player]

    if player_stats.empty:
        return None

    # Calculate rankings
    goals_rank = int((all_players_totals['Goals'] > player_stats['Goals'].values[0]).sum() + 1)
    assists_rank = int((all_players_totals['Assists'] > player_stats['Assists'].values[0]).sum() + 1)
    saves_rank = int((all_players_totals['Saves'] > player_stats['Saves'].values[0]).sum() + 1)
    potm_rank = int((all_players_totals['POTM'] > player_stats['POTM'].values[0]).sum() + 1)
    goals_per_game_rank = int((all_players_totals['Goals_Per_Game'] > player_stats['Goals_Per_Game'].values[0]).sum() + 1)

    total_players = len(all_players_totals)

    return {
        'goals_rank': goals_rank,
        'assists_rank': assists_rank,
        'saves_rank': saves_rank,
        'potm_rank': potm_rank,
        'goals_per_game_rank': goals_per_game_rank,
        'total_players': total_players
    }

def get_team_contribution(player):
    """Calculate player's contribution to their team(s)"""
    season_data = data_cache.get('season_player_stats', load_season_player_stats)
    player_data = season_data[season_data['Name'] == player]

    if player_data.empty:
        return None

    contributions = []

    # Group by team and season
    for (team, season), group in player_data.groupby(['Team', 'Season']):
        if team == 0:  # Skip invalid teams
            continue

        # Get team totals for that season
        team_season_data = season_data[(season_data['Team'] == team) & (season_data['Season'] == season)]

        team_total_goals = team_season_data['Goals'].sum()
        team_total_assists = team_season_data['Assists'].sum()

        player_goals = int(group['Goals'].sum())
        player_assists = int(group['Assists'].sum())

        goal_contribution = round((player_goals / team_total_goals) * 100, 1) if team_total_goals > 0 else 0
        assist_contribution = round((player_assists / team_total_assists) * 100, 1) if team_total_assists > 0 else 0
        contributions.append({
            'team': team,
            'season': season,
            'player_goals': player_goals,
            'team_goals': int(team_total_goals),
            'goal_percentage': goal_contribution,
            'player_assists': player_assists,
            'team_assists': int(team_total_assists),
            'assist_percentage': assist_contribution
        })
        contributions.sort(
            key=lambda x: (x['season'] == 'Total', int(x['season']) if str(x['season']).isdigit() else float('inf'))
        )

    return contributions

def get_teammates(player):
    """Get current and past teammates"""
    season_data = data_cache.get('season_player_stats', load_season_player_stats)
    player_data = season_data[season_data['Name'] == player]

    if player_data.empty:
        return None

    # Get all teams the player has played for
    player_teams = player_data[['Team', 'Season']].drop_duplicates()

    current_teammates = []
    all_teammates = set()

    for _, row in player_teams.iterrows():
        team = row['Team']
        season = row['Season']
        if season == "Total":
            continue
        if team == 0:  # Skip invalid teams
            continue

        # Get all players from the same team and season
        teammates_data = season_data[(season_data['Team'] == team) &
                                     (season_data['Season'] == season) &
                                     (season_data['Name'] != player)]
        for teammate in teammates_data['Name'].unique():
            all_teammates.add(teammate)

            if season == CURRENT_SEASON and team == player_data[player_data['Season'] == CURRENT_SEASON]['Team'].values[0]:
                current_teammates.append({
                    'name': teammate,
                    'team': team
                })

    return {
        'current': current_teammates,
        'old': all_teammates,
        'all_time_count': len(all_teammates)
    }

def get_opponent_stats(player):
    """Get head-to-head stats vs each opponent"""
    match_data = data_cache.get('player_match_stats', load_player_match_stats)
    player_matches = match_data[match_data['Name'] == player].copy()
    matches_df = data_cache.get('match_results', load_match_results)

    if player_matches.empty:
        return None

    opponent_stats = {}

    for _, match in player_matches.iterrows():
        opponent = match['Opponent']
        match_id = match['Match ID']
        team = match['My Team']

        if opponent not in opponent_stats:
            opponent_stats[opponent] = {
                'opponent': opponent,
                'matches': 0,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'goals': 0,
                'assists': 0,
                'saves': 0,
                'potm': 0
            }

        opponent_stats[opponent]['matches'] += 1
        opponent_stats[opponent]['goals'] += int(match['G'])
        opponent_stats[opponent]['assists'] += int(match['A'])
        opponent_stats[opponent]['saves'] += int(match['S'])
        opponent_stats[opponent]['potm'] += int(match['POTM'])

        # Get match result
        match_result = matches_df[matches_df['Match ID'] == match_id]
        if not match_result.empty:
            match_result = match_result.iloc[0]

            if match_result['Team 1'] == team:
                if match_result['Win Team 1'] == 1:
                    opponent_stats[opponent]['wins'] += 1
                elif match_result['Win Team 2'] == 1:
                    opponent_stats[opponent]['losses'] += 1
                else:
                    opponent_stats[opponent]['draws'] += 1
            else:
                if match_result['Win Team 2'] == 1:
                    opponent_stats[opponent]['wins'] += 1
                elif match_result['Win Team 1'] == 1:
                    opponent_stats[opponent]['losses'] += 1
                else:
                    opponent_stats[opponent]['draws'] += 1

    # Convert to list and sort by matches played
    opponent_list = list(opponent_stats.values())
    opponent_list.sort(key=lambda x: x['matches'], reverse=True)

    return opponent_list

def get_previous_teams(player):
    """Get all teams the player has played for"""
    season_data = data_cache.get('season_player_stats', load_season_player_stats)
    player_data = season_data[season_data['Name'] == player]

    if player_data.empty:
        return None

    teams = []
    for (team, seasons_group) in player_data.groupby('Team'):
        if team == 0:  # Skip invalid teams
            continue

        seasons_list = sorted(seasons_group['Season'].unique().tolist())
        teams.append({
            'team': team,
            'seasons': seasons_list,
            'matches': int(seasons_group['MP'].sum()),
            'goals': int(seasons_group['Goals'].sum()),
            'assists': int(seasons_group['Assists'].sum())
        })

    # Sort by most recent season
    teams.sort(key=lambda x: max(x['seasons']), reverse=True)

    return teams

def get_all_seasons():
    """Get list of all seasons"""
    season_data = data_cache.get('season_player_stats', load_season_player_stats)
    seasons = sorted(season_data['Season'].unique().tolist(), reverse=True)
    if 'Total' in seasons:
        seasons.remove('Total')
    return seasons

def get_all_players_with_stats(season=None, page=None, position_filter=None, sort_by=None):
    """Get all players with their season stats and ratings (with optional pagination, filtering, and sorting)"""
    if season is None:
        season = CURRENT_SEASON

    # Get player ratings from cache
    players_df = data_cache.get('player_ratings', load_player_ratings).copy()

    # Get season stats from cache
    season_data = data_cache.get('season_player_stats', load_season_player_stats).copy()
    season_data['Season'] = season_data['Season'].astype(str)

    season_df = season_data[season_data['Season'] == str(season)].copy()

    # Merge players with their season stats
    players_with_stats = players_df.merge(
        season_df[['Name', 'Team', 'MP', 'Goals', 'Assists', 'Saves', 'Y-R']],
        on='Name',
        how='inner'  # Only show players that played in this season
    )

    # Apply position filter if specified
    if position_filter and position_filter != 'all':
        players_with_stats = players_with_stats[players_with_stats['Primary Position'] == position_filter]

    # Get most recent POTM image for each player in this season from cache
    match_stats = data_cache.get('player_match_stats', load_player_match_stats)
    potm_data = match_stats[(match_stats['Season'] == int(season)) & (match_stats['POTM'] != 0)].copy()
    # For each player, get their most recent POTM match ID

    player_potm_images = {}
    for player_name in players_with_stats['Name'].unique():
        player_potms = potm_data[potm_data['Name'] == player_name]
        if not player_potms.empty:
            # Get the most recent (highest) match ID
            most_recent_potm = player_potms.nlargest(1, 'Match ID')
            player_potm_images[player_name] = int(most_recent_potm['Match ID'].values[0])
        else:
            player_potm_images[player_name] = "ford"

    # Add POTM image to dataframe
    players_with_stats['POTM_Image'] = players_with_stats['Name'].map(player_potm_images)

    # Apply sorting if specified
    if sort_by:
        if sort_by == 'name':
            players_with_stats = players_with_stats.sort_values('Name', ascending=True)
        elif sort_by == 'rating':
            players_with_stats = players_with_stats.sort_values('OVR Rating', ascending=False)
        elif sort_by == 'goals':
            players_with_stats = players_with_stats.sort_values('Goals', ascending=False)
        elif sort_by == 'assists':
            players_with_stats = players_with_stats.sort_values('Assists', ascending=False)
        elif sort_by == 'saves':
            players_with_stats = players_with_stats.sort_values('Saves', ascending=False)
        elif sort_by == 'potm':
            players_with_stats = players_with_stats.sort_values('POTM', ascending=False)
    else:
        # Default sort by rating
        players_with_stats = players_with_stats.sort_values('OVR Rating', ascending=False)

    # Convert to list of dicts
    all_players = players_with_stats.to_dict(orient='records')
    total_count = len(all_players)

    # Apply pagination if page is specified
    if page is not None:
        total_pages = (total_count + PLAYERS_PER_PAGE - 1) // PLAYERS_PER_PAGE if total_count > 0 else 1
        start_idx = (page - 1) * PLAYERS_PER_PAGE
        end_idx = start_idx + PLAYERS_PER_PAGE
        paginated_players = all_players[start_idx:end_idx]

        return {
            'players': paginated_players,
            'total_count': total_count,
            'total_pages': total_pages
        }
    else:
        # No pagination - return all players
        return {
            'players': all_players,
            'total_count': total_count,
            'total_pages': 1
        }

def get_league_leaders(season=None):
    """Get league-wide leaders in various categories"""
    if season is None:
        season = CURRENT_SEASON

    player_stats_df = data_cache.get('season_player_stats', load_season_player_stats).copy()
    player_stats_df = player_stats_df[player_stats_df["Season"] != "Total"]

    # Parse Y-R cards
    player_stats_df['Yellow'] = player_stats_df['Y-R'].apply(lambda x: int(str(x).split('-')[0]) if pd.notna(x) and str(x) != 'nan' else 0)
    player_stats_df['Red'] = player_stats_df['Y-R'].apply(lambda x: int(str(x).split('-')[1]) if pd.notna(x) and '-' in str(x) else 0)

    # Group by player across all teams and seasons
    all_time_stats = player_stats_df.groupby('Name').agg({
        'Goals': 'sum',
        'Assists': 'sum',
        'Saves': 'sum',
        'POTM': 'sum',
        'MP': 'sum',
        'Team': 'last',
        'Yellow': 'sum',
        'Red': 'sum'
    }).reset_index()

    # Get selected season stats
    season_stats_df = player_stats_df[player_stats_df['Season'] == str(season)].copy()
    season_agg = season_stats_df.groupby('Name').agg({
        'Goals': 'sum',
        'Assists': 'sum',
        'Saves': 'sum',
        'POTM': 'sum',
        'Team': 'last'
    }).reset_index()

    return {
        'all_time': {
            'top_scorers': all_time_stats.nlargest(10, 'Goals')[['Name', 'Goals', 'Team']].to_dict(orient='records'),
            'top_assists': all_time_stats.nlargest(10, 'Assists')[['Name', 'Assists', 'Team']].to_dict(orient='records'),
            'top_saves': all_time_stats.nlargest(10, 'Saves')[['Name', 'Saves', 'Team']].to_dict(orient='records'),
            'most_potm': all_time_stats.nlargest(10, 'POTM')[['Name', 'POTM', 'Team']].to_dict(orient='records')
        },
        'current_season': {
            'top_scorers': season_agg.nlargest(5, 'Goals')[['Name', 'Goals', 'Team']].to_dict(orient='records'),
            'top_assists': season_agg.nlargest(5, 'Assists')[['Name', 'Assists', 'Team']].to_dict(orient='records'),
            'top_saves': season_agg.nlargest(5, 'Saves')[['Name', 'Saves', 'Team']].to_dict(orient='records')
        }
    }