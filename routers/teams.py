from fastapi import APIRouter, Request, Cookie
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
import pandas as pd
from functions import get_potm_match
import ast
import time

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
def load_season_standings():
    return pd.read_csv("data/season_standings.csv")

def load_team_ratings():
    return pd.read_csv('data/team_ratings.csv')

def load_match_results():
    return pd.read_csv('data/Match_Results.csv')

def load_team_match_stats():
    return pd.read_csv('data/team_match_stats.csv')

def load_season_player_stats():
    return pd.read_csv('data/season_player_stats.csv')

def load_ifl_awards():
    return pd.read_csv('data/IFL_Awards.csv', encoding='utf-8-sig')

def load_player_match_stats():
    return pd.read_csv('data/player_match_stats.csv')

CURRENT_SEASON = max(data_cache.get('season_standings', load_season_standings)['Season'].tolist())
seasons_played = None

@router.get("/teams", response_class=HTMLResponse)
async def teams_home(request: Request, session: int = None, session_token: str = Cookie(None)):
    # Get selected season (default to current)
    selected_season = session if session else CURRENT_SEASON

    # Get all teams with stats for the selected season
    teams_with_stats = get_all_teams_with_stats(selected_season)

    # Get available seasons
    all_seasons = get_all_seasons()

    # Get league-wide statistics for the selected season
    performance_metrics = get_performance_metrics(selected_season)
    awards_stats = get_awards_statistics(selected_season)

    return templates.TemplateResponse("teams.html", {
        "request": request,
        "Teams": teams_with_stats,
        "count": len(teams_with_stats),
        "other_season_teams": [],  # No other season teams when not searching
        "performance_metrics": performance_metrics,
        "awards_stats": awards_stats,
        "current_season": CURRENT_SEASON,
        "selected_season": selected_season,
        "all_seasons": all_seasons
    })

@router.get("/teams/{team}", response_class=HTMLResponse)
async def team_page(request: Request, team: str):
    team_data = get_team(team)
    if team_data:
        standings_data = get_standings(team)
        matches_data = get_matches(team)
        players_data = get_players(team)
        seasons_played = list(standings_data.keys())

        # Get comprehensive stats
        team_stats = get_team_stats(team, seasons_played)
        player_stats = get_detailed_player_stats(team, seasons_played)
        awards_data = get_team_awards(team)
        head_to_head = get_head_to_head_records(team, seasons_played)

        return templates.TemplateResponse("team.html", {
            "request": request,
            "team": team,
            "data": team_data,
            "standings_data": standings_data,
            "matches_data": matches_data,
            "players_data": players_data,
            "seasons_played": seasons_played,
            "team_stats": team_stats,
            "player_stats": player_stats,
            "awards_data": awards_data,
            "head_to_head": head_to_head
        })
    else:
        return templates.TemplateResponse("404error.html", {"request": request, "error": "Team doesn't exist or team hasn't played a game yet"})

@router.get("/teams/{team_name}/{match_details}", response_class=HTMLResponse)
async def team_page(request: Request, team_name: str, match_details: str):
    try:
        match_data = get_match_data(*match_details.split('-'))
        player_data = get_player_data(*match_details.split('-'))
        potm = get_potm_match(match_details.split('-')[-1])
        
        return templates.TemplateResponse("match.html", {"request": request, 
                                                        "match_data": match_data, 
                                                        "player_data": player_data,
                                                        "potm": potm,
                                                        "match_details": match_details.split('-')})
    except Exception as e:
        return templates.TemplateResponse("404error.html", {"request": request, 'error': str(e)})


@router.get("/team_search", response_class=HTMLResponse)
async def search_teams(request: Request, query: str, session: int = None):
    # Get selected season (default to current)
    selected_season = session if session else CURRENT_SEASON

    # Get all teams with stats for searching
    teams_with_stats = get_all_teams_with_stats(selected_season)
    filtered_teams = [team for team in teams_with_stats if query.lower() in team['Name'].lower()]

    # If no results in selected season, search across all seasons
    other_season_teams = []
    if len(filtered_teams) == 0:
        other_season_teams = find_teams_in_other_seasons(query, selected_season)

    # Get available seasons
    all_seasons = get_all_seasons()

    # Get league-wide statistics for the selected season
    performance_metrics = get_performance_metrics(selected_season)
    awards_stats = get_awards_statistics(selected_season)

    return templates.TemplateResponse("teams.html", {
        "request": request,
        "Teams": filtered_teams,
        "count": len(filtered_teams),
        "other_season_teams": other_season_teams,
        "performance_metrics": performance_metrics,
        "awards_stats": awards_stats,
        "current_season": CURRENT_SEASON,
        "selected_season": selected_season,
        "all_seasons": all_seasons
    })

def get_standings(team):
    global seasons_played
    data = data_cache.get('season_standings', load_season_standings).copy()
    data['L5'] = data['L5'].apply(lambda x: ast.literal_eval(x))
    seasons_played = data[data['Team'] == team]['Season'].to_list()
    team_data = {}
    
    for season in seasons_played:
        sub_data = data[data['Season'] == season]
        table = None
        
        groupA = sub_data[sub_data["Group"] == 'A']
        groupB = sub_data[sub_data["Group"] == 'B']
        groupC = sub_data[sub_data["Group"] == 'C']
        
        if groupA['Team'].isin([team]).any():
            table = groupA.to_dict(orient='records')
        elif groupB['Team'].isin([team]).any():
            table = groupB.to_dict(orient='records')
        elif groupC['Team'].isin([team]).any():
            table = groupC.to_dict(orient='records')
            
        if table: team_data[season] = table
        
    return team_data

def get_matches(team):
    global seasons_played
    data = data_cache.get('match_results', load_match_results)
    match_data = {}

    for season in seasons_played:
        sub_data = data[data['Season'] == season]
        sub_data = sub_data[(sub_data['Team 1'] == team) | (sub_data['Team 2'] == team)].to_dict(orient='records')
        if sub_data: match_data[season] = sub_data
    return match_data

def get_match_data(team, opponent, match):
    data = data_cache.get('team_match_stats', load_team_match_stats)

    team_data = data[(data['Team'] == team) & (data['Opponent'] == opponent) & (data['Match'] == int(match))].copy()
    opponent_data = data[(data['Team'] == opponent) & (data['Opponent'] == team) & (data['Match'] == int(match))].copy()
    
    dropped_cols = ['Season', 'Match', 'Team', 'Opponent']
    team_data.drop(dropped_cols, axis=1, inplace=True)
    opponent_data.drop(dropped_cols, axis=1, inplace=True)
    
    if team_data.shape[0] > 0 and opponent_data.shape[0] > 0: return [team_data.to_dict(orient='records')[0], opponent_data.to_dict(orient='records')[0]]

def get_teams():
    data = data_cache.get('team_ratings', load_team_ratings)
    return data.to_dict(orient='records')

def get_team(team):
    data = data_cache.get('team_ratings', load_team_ratings)
    data = data[data['Name'] == team]
    return data.to_dict(orient='records')[0] if data.shape[0] > 0 else None

def get_players(team):
    global seasons_played
    data = data_cache.get('season_player_stats', load_season_player_stats)
    players_data = {}
    for season in seasons_played:
        sub_data:pd.DataFrame = data[data['Season'] == str(season)]
        sub_data = sub_data[sub_data['Team'] == team]
        if sub_data.shape[0] > 0: players_data[season] = sub_data['Name'].tolist()
    return players_data

def get_player_data(team, opponent, match):
    data = data_cache.get('player_match_stats', load_player_match_stats)

    team_data = data[(data['My Team'] == team) & (data['Match ID'] == int(match))].copy()
    opponent_data = data[(data['My Team'] == opponent) & (data['Match ID'] == int(match))].copy()

    dropped_cols = ['Season', 'Match ID']
    team_data.drop(dropped_cols, axis=1, inplace=True)
    opponent_data.drop(dropped_cols, axis=1, inplace=True)

    team_extended_data = [[], [], []] # [start, team subs, external subs]
    opponent_extended_data = [[], [], []]

    for player_stat in team_data.to_dict(orient='records'):
        if player_stat['External Sub'] == 'Y': team_extended_data[2].append(player_stat)
        elif player_stat['Start?'] == '0': team_extended_data[1].append(player_stat)
        else: team_extended_data[0].append(player_stat)

    for player_stat in opponent_data.to_dict(orient='records'):
        if player_stat['External Sub'] == 'Y': opponent_extended_data[2].append(player_stat)
        elif player_stat['Start?'] == '0': opponent_extended_data[1].append(player_stat)
        else: opponent_extended_data[0].append(player_stat)

    return {team: team_extended_data, opponent: opponent_extended_data}

def get_team_stats(team, seasons):
    """Calculate comprehensive team statistics"""
    standings_df = data_cache.get('season_standings', load_season_standings)
    matches_df = data_cache.get('match_results', load_match_results)
    team_match_stats_df = data_cache.get('team_match_stats', load_team_match_stats)

    # Filter for this team
    team_standings = standings_df[standings_df['Team'] == team]
    team_stats_data = team_match_stats_df[team_match_stats_df['Team'] == team]

    # Overall stats
    total_mp = team_standings['MP'].sum()
    total_w = team_standings['W'].sum()
    total_d = team_standings['D'].sum()
    total_l = team_standings['L'].sum()
    total_gf = team_standings['GF'].sum()
    total_ga = team_standings['GA'].sum()
    total_pts = team_standings['PTS'].sum()

    # Win percentage
    win_pct = round((total_w / total_mp * 100), 1) if total_mp > 0 else 0

    # Average goals
    avg_goals_for = round(total_gf / total_mp, 2) if total_mp > 0 else 0
    avg_goals_against = round(total_ga / total_mp, 2) if total_mp > 0 else 0

    # Clean sheets (goals allowed = 0)
    clean_sheets = len(team_stats_data[team_stats_data['Goals Allowed'] == 0])

    # Disciplinary record
    total_yellows = team_stats_data['Yellow Cards'].sum()
    total_reds = team_stats_data['Red Cards'].sum()

    # Current season stats
    current_season = max(seasons) if seasons else None
    current_season_data = team_standings[team_standings['Season'] == current_season].iloc[0] if current_season else None

    # Season by season progression
    season_progression = []
    for season in sorted(seasons):
        season_data = team_standings[team_standings['Season'] == season]
        if not season_data.empty:
            season_progression.append({
                'season': season,
                'pts': int(season_data['PTS'].values[0]),
                'gf': int(season_data['GF'].values[0]),
                'ga': int(season_data['GA'].values[0]),
                'rank': int(season_data.iloc[0].name + 1) if 'Rank' not in season_data.columns else int(season_data['Rank'].values[0])
            })

    return {
        'all_time': {
            'matches_played': int(total_mp),
            'wins': int(total_w),
            'draws': int(total_d),
            'losses': int(total_l),
            'goals_for': int(total_gf),
            'goals_against': int(total_ga),
            'goal_difference': int(total_gf - total_ga),
            'points': int(total_pts),
            'win_percentage': win_pct,
            'avg_goals_for': avg_goals_for,
            'avg_goals_against': avg_goals_against,
            'clean_sheets': int(clean_sheets),
            'yellow_cards': int(total_yellows),
            'red_cards': int(total_reds)
        },
        'current_season': current_season_data.to_dict() if current_season_data is not None else {},
        'season_progression': season_progression,
        'seasons_count': len(seasons)
    }

def get_detailed_player_stats(team, seasons):
    """Get detailed player statistics with goals, assists, etc."""
    season_player_stats = data_cache.get('season_player_stats', load_season_player_stats)
    team_players = (
        season_player_stats
        .query("Team == @team")
        .copy()
    )

    # Group by player across all seasons
    all_time_stats = team_players.groupby('Name').agg({
        'Goals': 'sum',
        'Assists': 'sum',
        'Saves': 'sum',
        'POTM': 'sum',
        'MP': 'sum'
    }).reset_index()

    # Parse Y-R cards
    team_players['Yellow'] = team_players['Y-R'].apply(lambda x: int(str(x).split('-')[0]) if pd.notna(x) else 0)
    team_players['Red'] = team_players['Y-R'].apply(lambda x: int(str(x).split('-')[1]) if pd.notna(x) and '-' in str(x) else 0)

    cards_stats = team_players.groupby('Name').agg({
        'Yellow': 'sum',
        'Red': 'sum'
    }).reset_index()

    all_time_stats = all_time_stats.merge(cards_stats, on='Name', how='left')

    all_time_stats = all_time_stats.sort_values('Goals', ascending=False)

    season_stats = {}
    for season in seasons:
        season_data = team_players[team_players['Season'] == str(season)]
        if season_data.empty:
            season_data = team_players[team_players['Season'] == int(season)]
            
        if not season_data.empty:
            season_stats[season] = season_data.to_dict(orient='records')

    return {
        'all_time': all_time_stats.to_dict(orient='records'),
        'by_season': season_stats,
        'top_scorer': all_time_stats.iloc[0].to_dict() if len(all_time_stats) > 0 else None,
        'top_assists': all_time_stats.sort_values('Assists', ascending=False).iloc[0].to_dict() if len(all_time_stats) > 0 else None,
        'top_saves': all_time_stats.sort_values('Saves', ascending=False).iloc[0].to_dict() if len(all_time_stats) > 0 else None
    }

def get_team_awards(team):
    """Get awards won by team members"""
    awards_df = data_cache.get('ifl_awards', load_ifl_awards)
    player_stats_df = data_cache.get('season_player_stats', load_season_player_stats)
    standings_df = data_cache.get('season_standings', load_season_standings)
    seasons_played = standings_df[standings_df['Team'] == team]['Season'].to_list()

    # Get all players who played for this team
    team_players = player_stats_df[player_stats_df['Team'] == team]['Name'].unique()

    # Get awards for these players
    team_awards = awards_df[
        (awards_df['Name'].isin(team_players)) &
        (awards_df['Season'].isin(seasons_played))
    ]

    # Group by award type
    awards_by_type = team_awards.groupby('Award').agg({
        'Name': lambda x: list(x),
        'Season': lambda x: list(x)
    }).reset_index()

    return {
        'total_awards': len(team_awards),
        'awards_list': team_awards.to_dict(orient='records'),
        'by_type': awards_by_type.to_dict(orient='records')
    }

def get_head_to_head_records(team, seasons):
    """Get head-to-head records against all opponents"""
    matches_df = data_cache.get('match_results', load_match_results)

    # Filter for matches involving this team
    team_matches = matches_df[(matches_df['Team 1'] == team) | (matches_df['Team 2'] == team)]

    h2h_records = {}

    for _, match in team_matches.iterrows():
        is_team1 = match['Team 1'] == team
        opponent = match['Team 2'] if is_team1 else match['Team 1']

        if opponent not in h2h_records:
            h2h_records[opponent] = {
                'opponent': opponent,
                'played': 0,
                'won': 0,
                'drawn': 0,
                'lost': 0,
                'gf': 0,
                'ga': 0
            }

        h2h_records[opponent]['played'] += 1
        team_score = match['Score Team 1']
        op_score = match['Score Team 2']
        if "(" in team_score:
            team_score = team_score.split("(")[0]
            op_score = op_score.split("(")[0]

        if is_team1:
            h2h_records[opponent]['gf'] += int(team_score)
            h2h_records[opponent]['ga'] += int(op_score)
            if match['Win Team 1'] == 1:
                h2h_records[opponent]['won'] += 1
            elif match['Win Team 2'] == 1:
                h2h_records[opponent]['lost'] += 1
            else:
                h2h_records[opponent]['drawn'] += 1
        else:
            h2h_records[opponent]['gf'] += int(op_score)
            h2h_records[opponent]['ga'] += int(team_score)
            if match['Win Team 2'] == 1:
                h2h_records[opponent]['won'] += 1
            elif match['Win Team 1'] == 1:
                h2h_records[opponent]['lost'] += 1
            else:
                h2h_records[opponent]['drawn'] += 1

    h2h_list = list(h2h_records.values())
    h2h_list.sort(key=lambda x: x['played'], reverse=True)

    return h2h_list

def get_league_leaders():
    """Get league-wide leaders in various categories"""
    player_stats_df = data_cache.get('season_player_stats', load_season_player_stats).copy()

    # Parse Y-R cards
    player_stats_df['Yellow'] = player_stats_df['Y-R'].apply(lambda x: int(str(x).split('-')[0]) if pd.notna(x) else 0)
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

    # Get current season stats
    current_season = CURRENT_SEASON
    current_season_stats = player_stats_df[player_stats_df['Season'] == current_season].copy()
    current_season_agg = current_season_stats.groupby('Name').agg({
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
            'top_scorers': current_season_agg.nlargest(5, 'Goals')[['Name', 'Goals', 'Team']].to_dict(orient='records'),
            'top_assists': current_season_agg.nlargest(5, 'Assists')[['Name', 'Assists', 'Team']].to_dict(orient='records'),
            'top_saves': current_season_agg.nlargest(5, 'Saves')[['Name', 'Saves', 'Team']].to_dict(orient='records')
        }
    }

def get_performance_metrics(season=None):
    """Get team performance metrics"""
    if season is None:
        season = CURRENT_SEASON

    standings_df = data_cache.get('season_standings', load_season_standings).copy()

    # All-time metrics
    team_totals = standings_df.groupby('Team').agg({
        'MP': 'sum',
        'W': 'sum',
        'D': 'sum',
        'L': 'sum',
        'GF': 'sum',
        'GA': 'sum',
        'PTS': 'sum'
    }).reset_index()

    # Calculate win percentage
    team_totals['Win_Pct'] = (team_totals['W'] / team_totals['MP'] * 100).round(1)
    team_totals['Avg_GF'] = (team_totals['GF'] / team_totals['MP']).round(2)
    team_totals['Avg_GA'] = (team_totals['GA'] / team_totals['MP']).round(2)
    team_totals['GD'] = team_totals['GF'] - team_totals['GA']

    # Selected season metrics
    season_df = standings_df[standings_df['Season'] == season].copy()
    season_df['Win_Pct'] = (season_df['W'] / season_df['MP'] * 100).round(1)
    season_df['GD'] = season_df['GF'] - season_df['GA']

    return {
        'all_time': {
            'highest_win_pct': team_totals.nlargest(5, 'Win_Pct')[['Team', 'Win_Pct', 'W', 'MP']].to_dict(orient='records'),
            'most_goals_scored': team_totals.nlargest(5, 'GF')[['Team', 'GF', 'Avg_GF']].to_dict(orient='records'),
            'best_defense': team_totals[team_totals['MP'] > 0]
                .nsmallest(5, 'GA')[['Team', 'GA', 'Avg_GA']]
                .to_dict(orient='records'),
            'most_wins': team_totals.nlargest(5, 'W')[['Team', 'W', 'MP']].to_dict(orient='records'),
            'best_goal_diff': team_totals.nlargest(5, 'GD')[['Team', 'GD', 'GF', 'GA']].to_dict(orient='records')
        },
        'current_season': {
            'top_teams': season_df.nlargest(5, 'PTS')[['Team', 'PTS', 'W', 'D', 'L', 'GF', 'GA', 'GD']].to_dict(orient='records'),
            'best_attack': season_df.nlargest(5, 'GF')[['Team', 'GF', 'MP']].to_dict(orient='records'),
            'best_defense': season_df[season_df['MP'] > 0]
                .nsmallest(5, 'GA')[['Team', 'GA', 'MP']]
                .to_dict(orient='records')
        }
    }

def get_awards_statistics(season=None):
    """Get awards statistics"""
    if season is None:
        season = CURRENT_SEASON

    awards_df = data_cache.get('ifl_awards', load_ifl_awards).copy()
    player_stats_df = data_cache.get('season_player_stats', load_season_player_stats).copy()
    awards_df['Season'] = awards_df['Season'].astype(str)
    player_stats_df['Season'] = player_stats_df['Season'].astype(str)
    player_stats_df = player_stats_df[player_stats_df['Season'] != "Total"]

    # All-time awards
    awards_with_teams = awards_df.merge(
        player_stats_df[['Name', 'Team', 'Season']].drop_duplicates(),
        on=['Name', 'Season'],
        how='left'
    )

    all_time_team_awards = awards_with_teams.groupby('Team').size().reset_index(name='Total_Awards')
    all_time_team_awards = all_time_team_awards.sort_values('Total_Awards', ascending=False)

    all_time_potm_by_team = player_stats_df.groupby('Team')['POTM'].sum().reset_index()
    all_time_potm_by_team = all_time_potm_by_team.sort_values('POTM', ascending=False)

    all_time_awards_by_type = awards_df.groupby('Award').size().reset_index(name='Count')

    # Selected season awards
    season_awards_df = awards_df[awards_df['Season'] == str(season)].copy()
    season_player_stats_df = player_stats_df[player_stats_df['Season'] == str(season)].copy()

    season_awards_with_teams = season_awards_df.merge(
        season_player_stats_df[['Name', 'Team', 'Season']].drop_duplicates(),
        on=['Name', 'Season'],
        how='left'
    )

    season_team_awards = season_awards_with_teams.groupby('Team').size().reset_index(name='Total_Awards')
    season_team_awards = season_team_awards.sort_values('Total_Awards', ascending=False)

    season_potm_by_team = season_player_stats_df.groupby('Team')['POTM'].sum().reset_index()
    season_potm_by_team = season_potm_by_team.sort_values('POTM', ascending=False)

    season_awards_by_type = season_awards_df.groupby('Award').size().reset_index(name='Count')

    return {
        'all_time': {
            'team_awards': all_time_team_awards.head(10).to_dict(orient='records'),
            'potm_by_team': all_time_potm_by_team.head(10).to_dict(orient='records'),
            'awards_by_type': all_time_awards_by_type.to_dict(orient='records'),
            'total_awards': len(awards_df)
        },
        'current_season': {
            'team_awards': season_team_awards.head(10).to_dict(orient='records'),
            'potm_by_team': season_potm_by_team.head(10).to_dict(orient='records'),
            'awards_by_type': season_awards_by_type.to_dict(orient='records'),
            'total_awards': len(season_awards_df)
        }
    }

def get_all_seasons():
    """Get list of all seasons"""
    standings_df = data_cache.get('season_standings', load_season_standings)
    seasons = sorted(standings_df['Season'].unique().tolist(), reverse=True)
    return seasons

def get_all_teams_with_stats(season=None):
    """Get all teams with their season stats and ratings"""
    if season is None:
        season = CURRENT_SEASON

    # Get team ratings
    teams_df = data_cache.get('team_ratings', load_team_ratings)

    # Get season standings
    standings_df = data_cache.get('season_standings', load_season_standings)
    season_df = standings_df[standings_df['Season'] == season].copy()

    # Merge teams with their season stats
    teams_with_stats = teams_df.merge(
        season_df[['Team', 'MP', 'W', 'D', 'L', 'GF', 'GA', 'GD', 'PTS', 'L5', 'Group']],
        left_on='Name',
        right_on='Team',
        how='inner'  
    )

    # Parse L5 (last 5 results)
    teams_with_stats['L5'] = teams_with_stats['L5'].apply(lambda x: ast.literal_eval(x) if pd.notna(x) else [])

    # Convert to dict
    return teams_with_stats.to_dict(orient='records')

def find_teams_in_other_seasons(query, current_season):
    """Find teams matching the query in other seasons (not the current selected season)"""
    # Get all standings data
    standings_df = data_cache.get('season_standings', load_season_standings)
    teams_df = data_cache.get('team_ratings', load_team_ratings)

    # Filter teams by query
    matching_teams = teams_df[teams_df['Name'].str.contains(query, case=False, na=False)]

    if matching_teams.empty:
        return []

    results = []

    for _, team_row in matching_teams.iterrows():
        team_name = team_row['Name']

        # Get all seasons this team played in
        team_seasons = standings_df[standings_df['Team'] == team_name].copy()

        if not team_seasons.empty:
            # Filter out the current selected season
            team_seasons = team_seasons[team_seasons['Season'] != current_season]

            if not team_seasons.empty:
                # Get the most recent season
                most_recent_season = team_seasons['Season'].max()
                most_recent_data = team_seasons[team_seasons['Season'] == most_recent_season].iloc[0]

                result = {
                    'Name': team_name,
                    'Found_Season': int(most_recent_season),
                    'Rating': int(team_row['Rating']),
                    'MP': int(most_recent_data['MP']),
                    'Group': most_recent_data['Group'],
                    'W': int(most_recent_data['W']),
                    'D': int(most_recent_data['D']),
                    'L': int(most_recent_data['L']),
                    'GF': int(most_recent_data['GF']),
                    'GA': int(most_recent_data['GA']),
                    'GD': int(most_recent_data['GD']),
                    'PTS': int(most_recent_data['PTS']),
                    'L5': ast.literal_eval(most_recent_data['L5']) if pd.notna(most_recent_data['L5']) else []
                }

                results.append(result)

    return results
