from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, JSONResponse
import pandas as pd
from fastapi import APIRouter
import ast

router = APIRouter()

templates = Jinja2Templates(directory="templates")
CURRENT_SEASON = max(pd.read_csv("data/season_standings.csv")['Season'].tolist())

@router.get("/matches", response_class=HTMLResponse)
async def read_matches(request: Request):
    return templates.TemplateResponse("matches.html", {"request": request, 
                                                       "groups": get_table(CURRENT_SEASON),
                                                       "matches_data": get_matches(CURRENT_SEASON),
                                                       "upcoming_matches_data": get_upcoming_matches(),
                                                       "active_season": CURRENT_SEASON,
                                                       "current_season": CURRENT_SEASON})

@router.get("/matches/{season}", response_class=HTMLResponse)
async def read_matches(request: Request, season: int):
    if season <= CURRENT_SEASON and season > 0:
        return templates.TemplateResponse("matches.html", {"request": request, 
                                                        "groups": get_table(season),
                                                        "matches_data": get_matches(season),
                                                        "upcoming_matches_data": get_upcoming_matches(),
                                                        "active_season": season,
                                                        "current_season": CURRENT_SEASON})
    else:
        return templates.TemplateResponse("matches.html", {"request": request, 
                                                        "groups": get_table(CURRENT_SEASON),
                                                        "matches_data": get_matches(CURRENT_SEASON),
                                                        "upcoming_matches_data": get_upcoming_matches(),
                                                        "active_season": CURRENT_SEASON,
                                                        "current_season": CURRENT_SEASON})

def get_table(season):
    with open("data/season_standings.csv") as file:
        data = pd.read_csv(file)
        data['L5'] = data['L5'].apply(lambda x: ast.literal_eval(x))
    data = data[data['Season'] == season]
    groupA = data[data["Group"] == 'A'].to_dict(orient='records')
    groupB = data[data["Group"] == 'B'].to_dict(orient='records')
    groupC = data[data["Group"] == 'C'].to_dict(orient='records')
    
    return [groupA, groupB, groupC] if len(groupC) > 0 else [groupA, groupB]

def get_matches(season):
    with open("data/Match_Results.csv") as file:
        data = pd.read_csv(file)
    data = data[data['Season'] == season]
    subsets = ['Playoff', 'A', 'B', 'C']
    match_data = {}
    
    for subset in subsets:
        sub_data = data[data['Group'] == subset].to_dict(orient='records')
        if len(sub_data) > 0: match_data[subset] = sub_data

    return match_data

def get_upcoming_matches():
    match_dict = {}
    with open("data/F25 Futsal Schedule.csv") as file:
        data = pd.read_csv(file)[['MD', 'Team 1', 'Team 2', 'Day', 'Time']]

    for k, gb in data.groupby(by='MD'):
        match_dict[k] = gb.to_dict(orient='records')

    return {
        "Max": data['MD'].max(),
        "data": match_dict
    }

@router.get("/api/match-preview")
async def get_match_preview(team1: str, team2: str, matchday: int = None, time: str = None):
    """Get comprehensive match preview data for two teams"""

    # Load necessary data
    match_results_df = pd.read_csv("data/Match_Results.csv")
    standings_df = pd.read_csv("data/season_standings.csv")
    player_stats_df = pd.read_csv("data/season_player_stats.csv")
    team_ratings_df = pd.read_csv("data/team_ratings.csv")
    awards_df = pd.read_csv("data/IFL_Awards.csv")

    # Convert L5 string to list for standings
    standings_df['L5'] = standings_df['L5'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    
    # Get current season data
    current_standings = standings_df[standings_df["Season"] == CURRENT_SEASON]
    group = current_standings.loc[current_standings["Team"] == team1, "Group"].iat[0]
    current_standings = current_standings[current_standings["Group"] == group].reset_index(drop=True)

    current_player_stats = player_stats_df[player_stats_df['Season'] == str(CURRENT_SEASON)]

    # Essential Information
    team1_rating = team_ratings_df[team_ratings_df['Name'] == team1]['Rating'].values
    team2_rating = team_ratings_df[team_ratings_df['Name'] == team2]['Rating'].values

    essential_info = {
        "team1": team1,
        "team2": team2,
        "matchday": matchday,
        "time": time,
        "team1_rating": float(team1_rating[0]) if len(team1_rating) > 0 else None,
        "team2_rating": float(team2_rating[0]) if len(team2_rating) > 0 else None
    }

    # Head-to-Head Statistics
    h2h_matches = match_results_df[
        ((match_results_df['Team 1'] == team1) & (match_results_df['Team 2'] == team2)) |
        ((match_results_df['Team 1'] == team2) & (match_results_df['Team 2'] == team1))
    ].copy()

    team1_wins = len(h2h_matches[
        ((h2h_matches['Team 1'] == team1) & (h2h_matches['Win Team 1'] == 1)) |
        ((h2h_matches['Team 2'] == team1) & (h2h_matches['Win Team 2'] == 1))
    ])

    team2_wins = len(h2h_matches[
        ((h2h_matches['Team 1'] == team2) & (h2h_matches['Win Team 1'] == 1)) |
        ((h2h_matches['Team 2'] == team2) & (h2h_matches['Win Team 2'] == 1))
    ])

    draws = len(h2h_matches) - team1_wins - team2_wins

    # Calculate goals scored/conceded in H2H
    team1_goals = 0
    team2_goals = 0
    for _, match in h2h_matches.iterrows():
        t1_goals = match['Score Team 1']
        t2_goals = match['Score Team 2']
        if "(" in t1_goals:
            t1_goals = t1_goals.split("(")[0]
            t2_goals = t2_goals.split("(")[0]
        t1_goals = int(t1_goals)
        t2_goals = int(t2_goals)
        
        if match['Team 1'] == team1:
            team1_goals += t1_goals
            team2_goals += t2_goals
        else:
            team1_goals += t2_goals
            team2_goals += t1_goals

    # Last 5 H2H matches
    last_5_h2h = []
    for _, match in h2h_matches.tail(5).iterrows():
        if match['Team 1'] == team1:
            result = {
                "team1_score": int(match['Score Team 1']),
                "team2_score": int(match['Score Team 2']),
                "winner": team1 if match['Win Team 1'] == 1 else (team2 if match['Win Team 2'] == 1 else "Draw")
            }
        else:
            result = {
                "team1_score": int(match['Score Team 2']),
                "team2_score": int(match['Score Team 1']),
                "winner": team1 if match['Win Team 2'] == 1 else (team2 if match['Win Team 1'] == 1 else "Draw")
            }
        last_5_h2h.append(result)

    head_to_head = {
        "total_matches": len(h2h_matches),
        "team1_wins": team1_wins,
        "team2_wins": team2_wins,
        "draws": draws,
        "team1_goals_scored": int(team1_goals),
        "team2_goals_scored": int(team2_goals),
        "team1_goals_conceded": int(team2_goals),
        "team2_goals_conceded": int(team1_goals),
        "last_5": last_5_h2h
    }

    # Current Form & Standings
    team1_standing = current_standings[current_standings['Team'] == team1]
    team2_standing = current_standings[current_standings['Team'] == team2]

    def get_form_data(team_df):
        if len(team_df) == 0:
            return None
        row = team_df.iloc[0]
        return {
            "position": int(row.name + 1) if hasattr(row, 'name') else None,
            "points": int(row['PTS']),
            "goal_difference": int(row['GD']),
            "games_played": int(row['MP']),
            "wins": int(row['W']),
            "draws": int(row['D']),
            "losses": int(row['L']),
            "last_5": row['L5']
        }

    current_form = {
        "team1": get_form_data(team1_standing),
        "team2": get_form_data(team2_standing)
    }

    # Statistical Comparison
    team1_season_matches = match_results_df[
        (match_results_df['Season'] == CURRENT_SEASON) &
        ((match_results_df['Team 1'] == team1) | (match_results_df['Team 2'] == team1))
    ]

    team2_season_matches = match_results_df[
        (match_results_df['Season'] == CURRENT_SEASON) &
        ((match_results_df['Team 1'] == team2) | (match_results_df['Team 2'] == team2))
    ]

    def get_team_stats(team, matches_df):
        if len(matches_df) == 0:
            return None

        goals_scored = 0
        goals_conceded = 0
        clean_sheets = 0
        wins = 0

        for _, match in matches_df.iterrows():
            t1_goals = match['Score Team 1']
            t2_goals = match['Score Team 2']
            if "(" in t1_goals:
                t1_goals = t1_goals.split("(")[0]
                t2_goals = t2_goals.split("(")[0]
            t1_goals = int(t1_goals)
            t2_goals = int(t2_goals)
                
            if match['Team 1'] == team:
                goals_scored += t1_goals
                goals_conceded += t2_goals
                if t2_goals == 0:
                    clean_sheets += 1
                if int(match['Win Team 1']) == 1:
                    wins += 1
            else:
                goals_scored += t2_goals
                goals_conceded += t1_goals
                if t1_goals == 0:
                    clean_sheets += 1
                if int(match['Win Team 2']) == 1:
                    wins += 1

        games = len(matches_df)
        return {
            "goals_scored": int(goals_scored),
            "goals_conceded": int(goals_conceded),
            "goals_per_game": round(goals_scored / games, 2) if games > 0 else 0,
            "goals_conceded_per_game": round(goals_conceded / games, 2) if games > 0 else 0,
            "clean_sheets": int(clean_sheets),
            "win_percentage": round((wins / games) * 100, 1) if games > 0 else 0
        }

    # Get POTM awards count
    team1_potm = current_player_stats[
        (current_player_stats['Season'] == str(CURRENT_SEASON)) &
        (current_player_stats['POTM'] != 0) &
        (current_player_stats['Team'] == team1)
    ]['POTM'].sum()

    team2_potm = current_player_stats[
        (current_player_stats['Season'] == str(CURRENT_SEASON)) &
        (current_player_stats['POTM'] != 0) &
        (current_player_stats['Team'] == team2)
    ]['POTM'].sum()

    stats_comparison = {
        "team1": get_team_stats(team1, team1_season_matches),
        "team2": get_team_stats(team2, team2_season_matches),
        "team1_potm_count": int(team1_potm),
        "team2_potm_count": int(team2_potm)
    }

    # Key Players
    def get_top_players(team):
        team_players = current_player_stats[current_player_stats['Team'] == team].copy()
        # Aggregate stats by player
        player_agg = team_players.groupby('Name').agg({
            'Goals': 'sum',
            'Assists': 'sum',
            'POTM': 'sum'
        }).reset_index()

        top_scorers = player_agg.nlargest(3, 'Goals')[['Name', 'Goals', 'Assists']].to_dict(orient='records')

        # Recent POTM winners
        recent_potm = team_players[
            (team_players['Season'] == str(CURRENT_SEASON)) &
            (team_players['POTM'] != 0)
        ].tail(3)[['Name']].to_dict(orient='records')

        return {
            "top_scorers": top_scorers,
            "recent_potm": recent_potm
        }

    key_players = {
        "team1": get_top_players(team1),
        "team2": get_top_players(team2)
    }

    return JSONResponse({
        "essential_info": essential_info,
        "head_to_head": head_to_head,
        "current_form": current_form,
        "stats_comparison": stats_comparison,
        "key_players": key_players
    })