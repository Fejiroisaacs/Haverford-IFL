from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
import pandas as pd
import time
from numpy import linspace
import os

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# DEVELOPMENT TOGGLE
IS_DEV = os.getenv("DEV", False) == "true"

# Data caching system
class DataCache:
    def __init__(self, ttl=300):
        self.cache = {}
        self.timestamps = {}
        self.ttl = ttl

    def get(self, key, loader_func):
        """Get data from cache or load it using loader_func"""
        current_time = time.time()

        if key in self.cache and key in self.timestamps:
            if current_time - self.timestamps[key] < self.ttl:
                return self.cache[key]

        data = loader_func()
        self.cache[key] = data
        self.timestamps[key] = current_time
        return data

# Initialize cache (100 minutes TTL)
data_cache = DataCache(ttl=6000)

# Cache loader functions
def load_player_stats():
    return pd.read_csv('data/season_player_stats.csv', encoding='utf-8-sig')

def load_team_standings():
    return pd.read_csv('data/season_standings.csv', encoding='utf-8-sig')

def load_match_results():
    return pd.read_csv('data/Match_Results.csv', encoding='utf-8-sig')

def load_player_ratings():
    return pd.read_csv('data/player_ratings.csv', encoding='utf-8-sig')

def load_team_ratings():
    return pd.read_csv('data/team_ratings.csv', encoding='utf-8-sig')

def load_awards():
    return pd.read_csv('data/IFL_Awards.csv', encoding='utf-8-sig')

def load_potm():
    df = pd.read_csv('data/player_match_stats.csv', encoding='utf-8-sig')
    return df[df['POTM'] == 1]


# ===== STATISTICS DASHBOARD FUNCTIONS =====

def get_all_time_leaders():
    """Get top 10 all-time leaders in goals, assists, saves, and POTM"""
    try:
        stats_df = data_cache.get('player_stats', load_player_stats)

        # Filter for career totals
        career_df = stats_df[stats_df['Season'] == 'Total'].copy()

        # Convert to numeric
        career_df['Goals'] = pd.to_numeric(career_df['Goals'], errors='coerce').fillna(0)
        career_df['Assists'] = pd.to_numeric(career_df['Assists'], errors='coerce').fillna(0)
        career_df['Saves'] = pd.to_numeric(career_df['Saves'], errors='coerce').fillna(0)
        career_df['POTM'] = pd.to_numeric(career_df['POTM'], errors='coerce').fillna(0)

        # Get top 10 for each category
        top_goals = career_df.nlargest(10, 'Goals')[['Name', 'Goals', 'Team']].to_dict('records')
        top_assists = career_df.nlargest(10, 'Assists')[['Name', 'Assists', 'Team']].to_dict('records')
        top_saves = career_df.nlargest(10, 'Saves')[['Name', 'Saves', 'Team']].to_dict('records')
        top_potm = career_df.nlargest(10, 'POTM')[['Name', 'POTM', 'Team']].to_dict('records')

        return {
            'goals': top_goals,
            'assists': top_assists,
            'saves': top_saves,
            'potm': top_potm
        }
    except Exception as e:
        print(f"Error in get_all_time_leaders: {e}")
        return {'goals': [], 'assists': [], 'saves': [], 'potm': []}

def get_current_season_leaders(season='6'):
    """Get top 10 current season leaders"""
    try:
        stats_df = data_cache.get('player_stats', load_player_stats)

        # Filter by season
        season_df = stats_df[stats_df['Season'] == str(season)].copy()

        # Convert to numeric
        season_df['Goals'] = pd.to_numeric(season_df['Goals'], errors='coerce').fillna(0)
        season_df['Assists'] = pd.to_numeric(season_df['Assists'], errors='coerce').fillna(0)
        season_df['Saves'] = pd.to_numeric(season_df['Saves'], errors='coerce').fillna(0)
        season_df['POTM'] = pd.to_numeric(season_df['POTM'], errors='coerce').fillna(0)

        # Get top 10 for each category
        top_goals = season_df.nlargest(10, 'Goals')[['Name', 'Goals', 'Team']].to_dict('records')
        top_assists = season_df.nlargest(10, 'Assists')[['Name', 'Assists', 'Team']].to_dict('records')
        top_saves = season_df.nlargest(10, 'Saves')[['Name', 'Saves', 'Team']].to_dict('records')
        top_potm = season_df.nlargest(10, 'POTM')[['Name', 'POTM', 'Team']].to_dict('records')

        return {
            'goals': top_goals,
            'assists': top_assists,
            'saves': top_saves,
            'potm': top_potm
        }
    except Exception as e:
        print(f"Error in get_current_season_leaders: {e}")
        return {'goals': [], 'assists': [], 'saves': [], 'potm': []}

def get_team_performance_comparison(season='6'):
    """Compare all teams: win%, goals/game, defense, ratings"""
    try:
        standings_df = data_cache.get('team_standings', load_team_standings)
        ratings_df = data_cache.get('team_ratings', load_team_ratings)

        # Filter by season
        season_standings = standings_df[standings_df['Season'] == int(season)].copy()

        if season_standings.empty:
            return []

        # Calculate metrics
        season_standings['Win_Pct'] = (season_standings['W'] / season_standings['MP'] * 100).round(1)
        season_standings['Avg_GF'] = (season_standings['GF'] / season_standings['MP']).round(2)
        season_standings['Avg_GA'] = (season_standings['GA'] / season_standings['MP']).round(2)

        # Merge with ratings
        result = season_standings.merge(ratings_df, left_on='Team', right_on='Name', how='left')

        # Select and rename columns
        result = result[['Team', 'Win_Pct', 'Avg_GF', 'Avg_GA', 'Rating', 'W', 'D', 'L', 'PTS']].copy()
        result = result.fillna({'Rating': 0})

        # Sort by points descending
        result = result.sort_values('PTS', ascending=False)

        return result.to_dict('records')
    except Exception as e:
        print(f"Error in get_team_performance_comparison: {e}")
        return []

def get_season_trends():
    """Season-over-season evolution: goals, matches, teams"""
    try:
        matches_df = data_cache.get('match_results', load_match_results)

        trends = []
        for season in range(1, 7):
            season_matches = matches_df[matches_df['Season'] == season]

            if season_matches.empty:
                continue

            # Calculate total goals
            team1_goals = season_matches['Score Team 1'].apply(parse_score).sum()
            team2_goals = season_matches['Score Team 2'].apply(parse_score).sum()
            total_goals = int(team1_goals + team2_goals)
            matches_count = len(season_matches)
            avg_goals = round(total_goals / matches_count, 2) if matches_count > 0 else 0

            # Count unique teams
            teams_1 = set(season_matches['Team 1'].unique())
            teams_2 = set(season_matches['Team 2'].unique())
            unique_teams = len(teams_1.union(teams_2))

            trends.append({
                'season': season,
                'total_goals': int(total_goals),
                'matches': matches_count,
                'avg_goals': avg_goals,
                'teams_count': unique_teams
            })

        return trends
    except Exception as e:
        print(f"Error in get_season_trends: {e}")
        return []

def get_rating_distribution():
    """Player/team rating histograms"""
    try:
        player_ratings_df = data_cache.get('player_ratings', load_player_ratings)
        team_ratings_df = data_cache.get('team_ratings', load_team_ratings)

        # Define buckets
        buckets = [0, 60, 70, 80, 85, 90, 95, 100]
        labels = ['50-60', '60-70', '70-80', '80-85', '85-90', '90-95', '95+']

        # Player rating distribution
        player_ratings_df['OVR Rating'] = pd.to_numeric(player_ratings_df['OVR Rating'], errors='coerce')
        player_ratings_df = player_ratings_df.dropna(subset=['OVR Rating'])
        player_dist = pd.cut(player_ratings_df['OVR Rating'], bins=buckets, labels=labels, right=False)
        player_counts = player_dist.value_counts().sort_index()

        # Team rating distribution
        team_ratings_df['Rating'] = pd.to_numeric(team_ratings_df['Rating'], errors='coerce')
        team_ratings_df = team_ratings_df.dropna(subset=['Rating'])
        n_bins = 7
        ratings = team_ratings_df['Rating']

        bins = linspace(ratings.min(), ratings.max(), n_bins + 1)
        labels = [
            f"{int(bins[i])}-{int(bins[i+1])}"
            for i in range(len(bins) - 1)
        ]

        team_dist = pd.cut(ratings, bins=bins, labels=labels, include_lowest=True)
        team_counts = team_dist.value_counts().sort_index()


        return {
            'player_ratings': [{'bucket': bucket, 'count': int(count)} for bucket, count in player_counts.items()],
            'team_ratings': [{'bucket': bucket, 'count': int(count)} for bucket, count in team_counts.items()]
        }
    except Exception as e:
        print(f"Error in get_rating_distribution: {e}")
        return {'player_ratings': [], 'team_ratings': []}

def get_hall_of_fame_members():
    """
    Get Hall of Fame members based on:
    1. All award winners from IFL_Awards.csv
    2. Career thresholds: >30 goals OR >25 assists OR >200 saves OR >30 matches
    """
    try:
        awards_df = data_cache.get('awards', load_awards)
        stats_df = data_cache.get('player_stats', load_player_stats)
        ratings_df = data_cache.get('player_ratings', load_player_ratings)
        potm_df = data_cache.get('players_potm', load_potm)

        # Get all award winners
        award_winners = set(awards_df['Name'].unique())

        # Get career totals
        career_df = stats_df[stats_df['Season'] == 'Total'].copy()
        career_df['Goals'] = pd.to_numeric(career_df['Goals'], errors='coerce').fillna(0)
        career_df['Assists'] = pd.to_numeric(career_df['Assists'], errors='coerce').fillna(0)
        career_df['Saves'] = pd.to_numeric(career_df['Saves'], errors='coerce').fillna(0)
        career_df['POTM'] = pd.to_numeric(career_df['POTM'], errors='coerce').fillna(0)
        career_df['MP'] = pd.to_numeric(career_df['MP'], errors='coerce').fillna(0)

        # Apply thresholds
        threshold_achievers = career_df[
            (career_df['Goals'] > 30) |
            (career_df['Assists'] > 25) |
            (career_df['Saves'] > 200) |
            (career_df['MP'] > 25)
        ]['Name'].unique()

        # Union of both sets
        hof_members_set = award_winners.union(set(threshold_achievers))

        # Build HOF member profiles
        hof_members = []
        for name in hof_members_set:
            # Get awards
            player_awards = awards_df[awards_df['Name'] == name]['Award'].tolist()

            # Get career stats
            player_career = career_df[career_df['Name'] == name]
            if player_career.empty:
                continue

            player_career = player_career.iloc[0]

            # Get rating
            player_rating_row = ratings_df[ratings_df['Name'] == name]
            rating = player_rating_row.iloc[0]['OVR Rating'] if not player_rating_row.empty else 0
            if isinstance(rating, int):
                pass
            elif isinstance(rating, str) and rating.isdigit():
                rating = int(rating)
            else:
                rating = 0
            
            # Get POTM Match ID
            player_rows = potm_df[potm_df['Name'] == name]
            if player_rows.empty:
                match_id = None
            else:
                match_id = player_rows.iloc[-1]['Match ID']

            # Generate achievements
            achievements = []
            goals = int(player_career['Goals'])
            assists = int(player_career['Assists'])
            saves = int(player_career['Saves'])
            potm = int(player_career['POTM'])
            mp = int(player_career['MP'])

            if goals >= 50:
                achievements.append(f"{goals} Career Goals")
            elif goals >= 30:
                achievements.append(f"{goals} Career Goals")

            if assists >= 30:
                achievements.append(f"{assists} Career Assists")
            elif assists >= 25:
                achievements.append(f"{assists} Career Assists")

            if saves >= 250:
                achievements.append(f"{saves} Career Saves")
            elif saves >= 200:
                achievements.append(f"{saves} Career Saves")

            if potm >= 5:
                achievements.append(f"{potm} POTM Awards")

            if mp >= 50:
                achievements.append(f"{mp} Matches Played")
            elif mp >= 30:
                achievements.append(f"{mp} Matches Played")

            # Determine category for filtering
            category = []
            if any('Champion' in award for award in player_awards):
                category.append('champions')
            if any('Golden Boot' in award for award in player_awards):
                category.append('golden-boot')
            if any('Golden Glove' in award for award in player_awards):
                category.append('golden-glove')
            if achievements:
                category.append('milestones')
            if potm >= 3:
                category.append('potm')

            hof_members.append({
                'Name': name,
                'Team': player_career['Team'],
                'awards': player_awards,
                'POTM_ID': match_id if match_id else 'ford',
                'achievements': achievements,
                'career_stats': {
                    'Goals': goals,
                    'Assists': assists,
                    'Saves': saves,
                    'POTM': potm,
                    'MP': mp
                },
                'rating': rating,
                'category': ','.join(category) if category else 'all',
                'awards_count': len(player_awards)
            })

        # Sort by awards count then rating
        hof_members.sort(key=lambda x: (x['awards_count'], x['rating']), reverse=True)

        return hof_members
    except Exception as e:
        print(f"Error in get_hall_of_fame_members: {e}")
        import traceback
        traceback.print_exc()
        return []

# ===== SEASON ARCHIVES FUNCTIONS =====
def parse_score(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.split('(')[0])
        except ValueError:
            return 0
    return 0

def build_playoff_bracket(playoff_matches, champion_team):
    """
    Build playoff bracket as sequential list of matches.
    Lists all playoff matches in chronological order from first to final.
    """
    if playoff_matches.empty:
        return None

    try:
        # Sort by Match ID ascending (chronological order)
        sorted_matches = playoff_matches.sort_values('Match ID', ascending=True).reset_index(drop=True)

        # Get all unique teams in playoffs
        all_teams = set(sorted_matches['Team 1'].tolist() + sorted_matches['Team 2'].tolist())

        # Build list of all matches with details
        matches = []
        for idx, match in sorted_matches.iterrows():
            team1 = match['Team 1']
            team2 = match['Team 2']
            score1 = parse_score(match['Score Team 1'])
            score2 = parse_score(match['Score Team 2'])
            winner = team1 if score1 > score2 else team2
            match_id = match['Match ID']

            # Determine if this is the final (last match)
            is_final = (idx == len(sorted_matches) - 1)

            matches.append({
                'match_number': idx + 1,
                'team1': team1,
                'team2': team2,
                'score1': score1,
                'score2': score2,
                'winner': winner,
                'match_id': match_id,
                'link': f"/teams/{team1}/{team1}-{team2}-{match_id}",
                'is_final': is_final,
                'is_champion_match': champion_team in [team1, team2]
            })

        return {
            'matches': matches,
            'champion': champion_team,
            'total_teams': len(all_teams),
            'total_matches': len(matches)
        }

    except Exception as e:
        print(f"Error building playoff bracket: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_season_archive_data(season):
    """Get complete archive data for a specific season"""
    try:
        standings_df = data_cache.get('team_standings', load_team_standings)
        awards_df = data_cache.get('awards', load_awards)
        matches_df = data_cache.get('match_results', load_match_results)

        # Get season standings
        season_standings = standings_df[standings_df['Season'] == season].copy()

        if season_standings.empty:
            return None

        # Get top 3 teams
        top_teams = season_standings.nlargest(3, 'PTS')[['Team', 'PTS', 'W', 'D', 'L']].copy()
        top_teams['Record'] = top_teams.apply(lambda x: f"{int(x['W'])}-{int(x['D'])}-{int(x['L'])}", axis=1)
        top_teams_list = top_teams[['Team', 'PTS', 'Record']].to_dict('records')

        # Get season awards
        season_awards = awards_df[awards_df['Season'] == season]

        def get_award_winner(award_name):
            matches = season_awards[season_awards['Award'].str.contains(award_name, case=False, na=False)]
            return matches.iloc[0]['Name'] if not matches.empty else 'N/A'

        awards_data = {
            'golden_boot': get_award_winner('Golden Boot'),
            'golden_glove': get_award_winner('Golden Glove'),
            'golden_lace': get_award_winner('Golden Lace'),
            'mvp': get_award_winner('Golden Goat')
        }

        # Get season stats
        season_matches = matches_df[matches_df['Season'] == season]
        team1_goals = season_matches['Score Team 1'].apply(parse_score).sum()
        team2_goals = season_matches['Score Team 2'].apply(parse_score).sum()
        total_goals = int(team1_goals + team2_goals)

        matches_count = len(season_matches)
        avg_goals = round(total_goals / matches_count, 2) if matches_count > 0 else 0

        # Get regular season winner (top PTS)
        regular_season_winner = season_standings.nlargest(1, 'PTS').iloc[0]
        regular_season_winner_data = {
            'Team': regular_season_winner['Team'],
            'PTS': int(regular_season_winner['PTS']),
            'Record': f"{int(regular_season_winner['W'])}-{int(regular_season_winner['D'])}-{int(regular_season_winner['L'])}"
        }

        # Get actual champion (playoff winner) - team that won the match with largest Match ID
        champion_data = None
        playoff_path = []
        bracket_structure = None

        if not season_matches.empty:
            # Sort by Match ID and get the last match (championship final)
            final_match = season_matches.sort_values('Match ID').iloc[-1]

            # Determine winner of final match
            score_team1 = parse_score(final_match['Score Team 1'])
            score_team2 = parse_score(final_match['Score Team 2'])

            if score_team1 > score_team2:
                champion_team = final_match['Team 1']
            elif score_team2 > score_team1:
                champion_team = final_match['Team 2']
            else:
                # If tied, use regular season winner
                champion_team = regular_season_winner['Team']

            # Get champion's record from standings
            champion_standing = season_standings[season_standings['Team'] == champion_team]
            if not champion_standing.empty:
                champion_standing = champion_standing.iloc[0]
                champion_data = {
                    'Team': champion_team,
                    'PTS': int(champion_standing['PTS']),
                    'Record': f"{int(champion_standing['W'])}-{int(champion_standing['D'])}-{int(champion_standing['L'])}"
                }
            else:
                champion_data = {
                    'Team': champion_team,
                    'PTS': 0,
                    'Record': 'N/A'
                }

            # Get playoff path for the champion
            playoff_matches = season_matches[
                (season_matches['Group'] == 'Playoff') |
                (season_matches['Time'].str.contains('Playoff', case=False, na=False))
            ]

            # Filter to matches involving the champion
            champion_playoff_matches = playoff_matches[
                (playoff_matches['Team 1'] == champion_team) |
                (playoff_matches['Team 2'] == champion_team)
            ].sort_values('Match ID')

            for _, match in champion_playoff_matches.iterrows():
                team1 = match['Team 1']
                team2 = match['Team 2']
                match_id = match['Match ID']
                score1 = parse_score(match['Score Team 1'])
                score2 = parse_score(match['Score Team 2'])

                # Determine opponent and result
                if team1 == champion_team:
                    opponent = team2
                    result = 'W' if score1 > score2 else ('D' if score1 == score2 else 'L')
                else:
                    opponent = team1
                    result = 'W' if score2 > score1 else ('D' if score1 == score2 else 'L')

                # Create match link
                match_link = f"/teams/{champion_team}/{team1}-{team2}-{match_id}"

                playoff_path.append({
                    'opponent': opponent,
                    'score': f"{score1}-{score2}",
                    'result': result,
                    'match_id': match_id,
                    'link': match_link,
                    'full_teams': f"{team1} vs {team2}"
                })

            # Build playoff bracket (all playoff matches, not just champion's path)
            bracket_structure = build_playoff_bracket(playoff_matches, champion_team)
        else:
            bracket_structure = None

        champions_regular_season_data = season_standings[season_standings["Team"] == champion_team]
        champion_data["Record"] = f"{int(champions_regular_season_data['W'].iloc[0]) + len(playoff_path)}-" \
                          f"{int(champions_regular_season_data['D'].iloc[0])}-" \
                          f"{int(champions_regular_season_data['L'].iloc[0])}"

        if champion_data is None:
            champion_data = regular_season_winner_data

        stats_data = {
            'total_goals': total_goals,
            'matches': matches_count,
            'avg_goals': avg_goals
        }

        return {
            'season': season,
            'champion': champion_data,  # Actual playoff winner
            'regular_season_winner': regular_season_winner_data,  # Regular season top team
            'playoff_path': playoff_path,  # Champion's playoff matches
            'bracket': bracket_structure,  # Playoff bracket structure
            'awards': awards_data,
            'top_teams': top_teams_list,
            'stats': stats_data,
            'memorable_moments': []  # Can be manually added later
        }
    except Exception as e:
        print(f"Error in get_season_archive_data for season {season}: {e}")
        return None

def get_all_seasons_summary():
    """Get archive data for all seasons"""
    archives = []
    for season in range(1, 7):
        archive_data = get_season_archive_data(season)
        if archive_data:
            archives.append(archive_data)
    return archives


async def get_current_user(session_token: str = None):
    """Get current user from session (placeholder)"""
    return None

@router.get("/statistics", response_class=HTMLResponse)
async def statistics_page(request: Request, season: int = 6, user = Depends(get_current_user)):
    """Statistics Dashboard page"""
    # Check if statistics pages are enabled
    if not IS_DEV:
        return templates.TemplateResponse("coming-soon.html", {
            "request": request,
            "user": user,
            "page_name": "Statistics Dashboard",
            "page_description": "comprehensive league statistics, player rankings, and team performance analytics"
        })

    try:
        # Get all data
        all_time_leaders = get_all_time_leaders()
        current_leaders = get_current_season_leaders(str(season))
        team_comparison = get_team_performance_comparison(str(season))
        season_trends = get_season_trends()
        rating_dist = get_rating_distribution()

        return templates.TemplateResponse("statistics.html", {
            "request": request,
            "user": user,
            "selected_season": season,
            "all_seasons": list(range(1, 7)),
            "all_time_leaders": all_time_leaders,
            "current_leaders": current_leaders,
            "team_comparison": team_comparison,
            "season_trends": season_trends,
            "rating_distribution": rating_dist
        })
    except Exception as e:
        print(f"Error in statistics_page: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("statistics.html", {
            "request": request,
            "user": user,
            "selected_season": season,
            "all_seasons": list(range(1, 7)),
            "all_time_leaders": {'goals': [], 'assists': [], 'saves': [], 'potm': []},
            "current_leaders": {'goals': [], 'assists': [], 'saves': [], 'potm': []},
            "team_comparison": [],
            "season_trends": [],
            "rating_distribution": {'player_ratings': [], 'team_ratings': []}
        })

@router.get("/hall-of-fame", response_class=HTMLResponse)
async def hall_of_fame_page(request: Request, user = Depends(get_current_user)):
    """Hall of Fame page"""
    # Check if statistics pages are enabled
    if not IS_DEV:
        return templates.TemplateResponse("coming-soon.html", {
            "request": request,
            "user": user,
            "page_name": "Hall of Fame",
            "page_description": "legendary players and their incredible achievements in the league's history"
        })

    try:
        hof_members = get_hall_of_fame_members()

        # Calculate summary stats
        total_inductees = len(hof_members)
        total_awards = sum(len(member['awards']) for member in hof_members)

        return templates.TemplateResponse("hall-of-fame.html", {
            "request": request,
            "user": user,
            "hof_members": hof_members,
            "total_inductees": total_inductees,
            "total_awards": total_awards
        })
    except Exception as e:
        print(f"Error in hall_of_fame_page: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("hall-of-fame.html", {
            "request": request,
            "user": user,
            "hof_members": [],
            "total_inductees": 0,
            "total_awards": 0
        })

@router.get("/archives", response_class=HTMLResponse)
async def archives_page(request: Request, user = Depends(get_current_user)):
    """Season Archives page"""
    # Check if statistics pages are enabled
    if not IS_DEV:
        return templates.TemplateResponse("coming-soon.html", {
            "request": request,
            "user": user,
            "page_name": "Season Archives",
            "page_description": "historical data, past season standings, and memorable moments from previous campaigns"
        })

    try:
        archives = get_all_seasons_summary()

        return templates.TemplateResponse("archives.html", {
            "request": request,
            "user": user,
            "archives": archives,
            "seasons": list(range(1, 7))
        })
    except Exception as e:
        print(f"Error in archives_page: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("archives.html", {
            "request": request,
            "user": user,
            "archives": [],
            "seasons": list(range(1, 7))
        })
