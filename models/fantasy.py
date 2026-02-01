from pydantic import BaseModel, Field
from typing import List, Optional, Dict, ClassVar
import pandas as pd
import numpy as np
from firebase_admin import db
from datetime import datetime
import secrets
import string

class FantasyPlayer(BaseModel):
    first_name: str
    last_name: str
    team: str
    season: int
    primary_position: str
    ovr_rating: Optional[int] = None
    fantasy_cost: float
    total_points: int = 0
    mw_points: Dict[str, int] = Field(default_factory=dict)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

class FantasyTeam(BaseModel):
    current_team: List[str] = Field(default_factory=list)  # List of player names in starting lineup
    all_players: List[str] = Field(default_factory=list)   # List of all owned player names
    captain: Optional[str] = None
    
    @property
    def bench_players(self):
        return [player for player in self.all_players if player not in self.current_team]

class FantasyUser(BaseModel):
    user_id: str
    username: str
    admin: bool = False
    total_balance: float = 100.0
    total_points: int = 0
    week_points: int = 0
    free_transfers: int = 2
    team: FantasyTeam = Field(default_factory=FantasyTeam)

    # Team creation rules (ClassVar to distinguish from model fields in Pydantic V2)
    CREATING_TEAM_RULES: ClassVar[str] = ("You need to have players from at least 5 different teams, "
                          "you need at least 2 Goalkeepers, at least 2 Defenders, "
                          "at least 1 Midfielder, and at least 2 Forward players.")

    WEEKLY_TEAM_RULES: ClassVar[str] = ("You need to start players from 5 different teams, you need a Goalkeeper, "
                        "at least 2 defenders + midfielders, at least 1 Forward player.")

    TRANSFER_ACTIVE_RULES: ClassVar[str] = ("Your starting team needs to have players from at least 5 different teams, "
                           "you need a Goalkeeper, at least 2 defenders + midfielders combined, "
                           "and at least 1 Forward player.")
    
    def save_to_firebase(self):
        """Save user data to Firebase"""
        user_data = {
            'username': self.username,
            'admin': self.admin,
            'total_balance': self.total_balance,
            'total_points': self.total_points,
            'week_points': self.week_points,
            'free_transfers': self.free_transfers,
            'current_team': self.team.current_team,
            'all_players': self.team.all_players,
            'captain': self.team.captain
        }
        db.reference(f'Fantasy/Users/{self.user_id}').set(user_data)
    
    @classmethod
    def load_from_firebase(cls, user_id: str, username: str):
        """Load user data from Firebase"""
        user_ref = db.reference(f'Fantasy/Users/{user_id}')
        user_data = user_ref.get()
        admin_ref = db.reference(f'Users/{username}').get()
        
        if not user_data:
            # Create new Fantasy user
            return cls(user_id=user_id, username=username)
        
        team = FantasyTeam(
            current_team=user_data.get('current_team', []),
            all_players=user_data.get('all_players', []),
            captain=user_data.get('captain')
        )
        
        return cls(
            user_id=user_id,
            username=username,
            admin=admin_ref.get("Admin", False),
            total_balance=user_data.get('total_balance', 100.0),
            total_points=user_data.get('total_points', 0),
            week_points=user_data.get('week_points', 0),
            free_transfers=user_data.get('free_transfers', 2),
            team=team
        )

class FantasyService:
    def __init__(self):
        self.players_df = None
        self.load_players_data()
    
    def load_players_data(self):
        """Load players data from CSV and merge with season stats"""
        try:
            self.players_df = pd.read_csv('data/Fantasy_Data.csv')
            # Clean column names
            self.players_df.columns = [col.strip() for col in self.players_df.columns]
            # Rename for consistency
            column_mapping = {
                'First Name': 'First',
                'Last Name': 'Last',
                'Primary Position': 'Primary_Position'
            }
            self.players_df.rename(columns=column_mapping, inplace=True)
            
            # Clean OVR Rating column - replace '-' with NaN and convert to numeric
            self.players_df['OVR Rating'] = pd.to_numeric(
                self.players_df['OVR Rating'].replace('-', np.nan), 
                errors='coerce'
            )
            # Fill missing OVR ratings with a default value (e.g., 50)
            self.players_df['OVR Rating'] = self.players_df['OVR Rating'].fillna(50)
            
            # Load season stats and merge
            try:
                stats_df = pd.read_csv('data/season_player_stats.csv')
                stats_df.columns = [col.strip() for col in stats_df.columns]
                
                # Create full name columns for merging
                self.players_df['full_name'] = self.players_df['First'] + ' ' + self.players_df['Last']
                stats_df['full_name'] = stats_df['Name']
                
                stats_aggregated = stats_df[stats_df['Season'] == 'Total'][['full_name', 'Goals', 'Assists', 'Saves']]
                # Merge the stats with fantasy data
                self.players_df = self.players_df.merge(
                    stats_aggregated, 
                    on='full_name', 
                    how='left'
                )
                # Fill NaN values with 0 for players without stats
                self.players_df['Goals'] = self.players_df['Goals'].fillna(0)
                self.players_df['Assists'] = self.players_df['Assists'].fillna(0)
                self.players_df['Saves'] = self.players_df['Saves'].fillna(0)
                
            except Exception as stats_error:
                print(f"Error loading season stats: {stats_error}")
                # Add default stats columns if merge fails
                self.players_df['Goals'] = 0
                self.players_df['Assists'] = 0
                self.players_df['Saves'] = 0
                
        except Exception as e:
            print(f"Error loading players data: {e}")
            self.players_df = pd.DataFrame()
    
    def get_all_players(self) -> List[Dict]:
        """Get all available fantasy players"""
        if self.players_df.empty:
            return []
        return self.players_df.fillna("").to_dict('records')
    
    def get_player_by_name(self, first_name: str, last_name: str) -> Optional[Dict]:
        """Get a specific player by name"""
        if self.players_df.empty:
            return None
        
        player = self.players_df[
            (self.players_df['First'] == first_name) & 
            (self.players_df['Last'] == last_name)
        ]
        
        if not player.empty:
            return player.iloc[0].to_dict()
        return None
    
    def get_players_by_names(self, player_names: List[str]) -> List[Dict]:
        """Get multiple players by their full names"""
        players = []
        for name in player_names:
            try:
                first, last = name.split(" ", 1)
                player = self.get_player_by_name(first, last)
                if player:
                    players.append(player)
            except ValueError:
                continue
        return players
    
    def validate_team_creation(self, selected_players: List[str], available_balance: float) -> tuple[bool, str]:
        """Validate team creation rules"""
        if len(selected_players) != 8:
            return False, "You must select exactly 8 players"
        
        players_data = self.get_players_by_names(selected_players)
        if len(players_data) != 8:
            return False, "Some selected players were not found"
        
        total_cost = sum(player['Fantasy Cost'] for player in players_data)
        if total_cost > available_balance:
            return False, f"Insufficient funds. Cost: {total_cost}, Available: {available_balance}"
        
        # Count positions and teams
        positions = [player['Primary_Position'] for player in players_data]
        teams = [player['Team'] for player in players_data]
        
        if len(set(teams)) < 5:
            return False, "You need players from at least 5 different teams"
        
        if positions.count('GK') < 2:
            return False, "You need at least 2 Goalkeepers"
        
        if positions.count('D') < 2:
            return False, "You need at least 2 Defenders"
        
        if positions.count('M') < 1:
            return False, "You need at least 1 Midfielder"
        
        if positions.count('F') < 2:
            return False, "You need at least 2 Forwards"
        
        return True, "Team creation rules satisfied"
    
    def validate_weekly_team(self, starting_team: List[str], all_players: List[str]) -> tuple[bool, str]:
        """Validate weekly team selection rules"""
        if len(starting_team) != 5:
            return False, "You must select exactly 5 players for your starting team"
        
        # Check if all starting players are in user's squad
        for player in starting_team:
            if player not in all_players:
                return False, f"{player} is not in your squad"
        
        players_data = self.get_players_by_names(starting_team)
        if len(players_data) != 5:
            return False, "Some selected players were not found"
        
        # Count positions and teams
        positions = [player['Primary_Position'] for player in players_data]
        teams = [player['Team'] for player in players_data]
        
        if len(set(teams)) < 5:
            return False, "You need to start players from 5 different teams"
        
        if positions.count('GK') != 1:
            return False, "You need exactly 1 Goalkeeper in your starting team"
        
        if positions.count('D') + positions.count('M') < 2:
            return False, "You need at least 2 defenders + midfielders in your starting team"
        
        if positions.count('F') < 1:
            return False, "You need at least 1 Forward in your starting team"
        
        return True, "Weekly team rules satisfied"
    
    def validate_transfer(self, player_in_name: str, player_out_name: str, user: FantasyUser) -> tuple[bool, str]:
        """Validate transfer rules"""
        player_in = self.get_player_by_name(*player_in_name.split(" ", 1))
        player_out = self.get_player_by_name(*player_out_name.split(" ", 1))
        
        if not player_in or not player_out:
            return False, "Player not found"
        
        if player_in_name in user.team.all_players:
            return False, "Player already in your team"
        
        if player_out_name not in user.team.all_players:
            return False, "Player not in your team"
        
        # Check balance
        cost_difference = player_in['Fantasy Cost'] - player_out['Fantasy Cost']
        if user.total_balance - cost_difference < 0:
            return False, "Insufficient funds for this transfer"
        
        # Simulate transfer and check team rules
        test_players = user.team.all_players.copy()
        test_players.remove(player_out_name)
        test_players.append(player_in_name)
        
        players_data = self.get_players_by_names(test_players)
        positions = [player['Primary_Position'] for player in players_data]
        teams = [player['Team'] for player in players_data]
        
        if len(set(teams)) < 5:
            return False, "Transfer would violate team diversity rule (need 5 different teams)"
        
        if positions.count('GK') < 2:
            return False, "Transfer would violate goalkeeper rule (need at least 2 GK)"
        
        if positions.count('D') < 2:
            return False, "Transfer would violate defender rule (need at least 2 D)"
        
        if positions.count('M') < 1:
            return False, "Transfer would violate midfielder rule (need at least 1 M)"
        
        if positions.count('F') < 2:
            return False, "Transfer would violate forward rule (need at least 2 F)"
        
        # If player being transferred out is in starting team, check starting team rules
        if player_out_name in user.team.current_team:
            test_starting = user.team.current_team.copy()
            test_starting.remove(player_out_name)
            test_starting.append(player_in_name)
            
            starting_players_data = self.get_players_by_names(test_starting)
            starting_positions = [player['Primary_Position'] for player in starting_players_data]
            starting_teams = [player['Team'] for player in starting_players_data]
            
            if len(set(starting_teams)) < 5:
                return False, "Transfer would violate starting team diversity rule"
            
            if starting_positions.count('GK') != 1:
                return False, "Transfer would violate starting team goalkeeper rule"
            
            if starting_positions.count('D') + starting_positions.count('M') < 2:
                return False, "Transfer would violate starting team defender/midfielder rule"
            
            if starting_positions.count('F') < 1:
                return False, "Transfer would violate starting team forward rule"

        return True, "Transfer is valid"


# ============ Mini-League Models ============

class MiniLeague(BaseModel):
    """Represents a fantasy mini-league"""
    league_id: str
    name: str
    creator_id: str
    creator_name: str
    created_at: str
    league_code: str  # 6-character shareable code
    members: Dict[str, str] = Field(default_factory=dict)  # {user_id: join_timestamp}
    max_members: int = 20
    is_public: bool = False
    description: str = ""

    @staticmethod
    def generate_league_code() -> str:
        """Generate a unique 6-character league code"""
        return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))

    @staticmethod
    def generate_league_id() -> str:
        """Generate a unique league ID"""
        return f"league_{secrets.token_hex(8)}"

    def save_to_firebase(self):
        """Save league to Firebase"""
        league_data = {
            'name': self.name,
            'creator_id': self.creator_id,
            'creator_name': self.creator_name,
            'created_at': self.created_at,
            'league_code': self.league_code,
            'members': self.members,
            'max_members': self.max_members,
            'is_public': self.is_public,
            'description': self.description
        }
        db.reference(f'Fantasy/MiniLeagues/{self.league_id}').set(league_data)

    @classmethod
    def load_from_firebase(cls, league_id: str) -> Optional['MiniLeague']:
        """Load league from Firebase"""
        league_ref = db.reference(f'Fantasy/MiniLeagues/{league_id}')
        league_data = league_ref.get()

        if not league_data:
            return None

        return cls(
            league_id=league_id,
            name=league_data.get('name', ''),
            creator_id=league_data.get('creator_id', ''),
            creator_name=league_data.get('creator_name', ''),
            created_at=league_data.get('created_at', ''),
            league_code=league_data.get('league_code', ''),
            members=league_data.get('members', {}),
            max_members=league_data.get('max_members', 20),
            is_public=league_data.get('is_public', False),
            description=league_data.get('description', '')
        )

    @staticmethod
    def find_by_code(code: str) -> Optional['MiniLeague']:
        """Find a league by its invite code"""
        leagues_ref = db.reference('Fantasy/MiniLeagues')
        all_leagues = leagues_ref.get() or {}

        for league_id, league_data in all_leagues.items():
            if league_data.get('league_code') == code.upper():
                return MiniLeague.load_from_firebase(league_id)
        return None

    @staticmethod
    def get_user_leagues(user_id: str) -> List['MiniLeague']:
        """Get all leagues a user is a member of"""
        leagues_ref = db.reference('Fantasy/MiniLeagues')
        all_leagues = leagues_ref.get() or {}

        user_leagues = []
        for league_id, league_data in all_leagues.items():
            members = league_data.get('members', {})
            if user_id in members:
                league = MiniLeague.load_from_firebase(league_id)
                if league:
                    user_leagues.append(league)

        return user_leagues

    @staticmethod
    def get_public_leagues() -> List['MiniLeague']:
        """Get all public leagues"""
        leagues_ref = db.reference('Fantasy/MiniLeagues')
        all_leagues = leagues_ref.get() or {}

        public_leagues = []
        for league_id, league_data in all_leagues.items():
            if league_data.get('is_public', False):
                league = MiniLeague.load_from_firebase(league_id)
                if league:
                    public_leagues.append(league)

        return public_leagues

    def add_member(self, user_id: str) -> tuple[bool, str]:
        """Add a member to the league"""
        if user_id in self.members:
            return False, "You are already a member of this league"

        if len(self.members) >= self.max_members:
            return False, f"League is full (max {self.max_members} members)"

        self.members[user_id] = datetime.now().isoformat()
        self.save_to_firebase()
        return True, "Successfully joined the league"

    def remove_member(self, user_id: str) -> tuple[bool, str]:
        """Remove a member from the league"""
        if user_id not in self.members:
            return False, "You are not a member of this league"

        if user_id == self.creator_id:
            return False, "League creator cannot leave. Delete the league instead."

        del self.members[user_id]
        self.save_to_firebase()
        return True, "Successfully left the league"

    def delete(self):
        """Delete the league"""
        db.reference(f'Fantasy/MiniLeagues/{self.league_id}').delete()

    def get_leaderboard(self) -> List[Dict]:
        """Get the league leaderboard"""
        leaderboard = []

        for user_id in self.members.keys():
            user_ref = db.reference(f'Fantasy/Users/{user_id}')
            user_data = user_ref.get()

            if user_data:
                leaderboard.append({
                    'user_id': user_id,
                    'username': user_data.get('username', 'Unknown'),
                    'total_points': user_data.get('total_points', 0),
                    'week_points': user_data.get('week_points', 0)
                })

        # Sort by total points descending
        leaderboard.sort(key=lambda x: x['total_points'], reverse=True)

        # Add positions
        for i, entry in enumerate(leaderboard):
            entry['position'] = i + 1

        return leaderboard


# ============ Match Predictions Models ============

class MatchPrediction(BaseModel):
    """Represents a user's prediction for a match"""
    prediction_id: str
    user_id: str
    username: str
    match_id: str
    home_team: str
    away_team: str
    predicted_home_score: int
    predicted_away_score: int
    predicted_at: str
    points_earned: int = 0
    is_processed: bool = False

    @staticmethod
    def generate_prediction_id() -> str:
        """Generate a unique prediction ID"""
        return f"pred_{secrets.token_hex(8)}"

    def get_predicted_result(self) -> str:
        """Get predicted result: 'home', 'draw', or 'away'"""
        if self.predicted_home_score > self.predicted_away_score:
            return 'home'
        elif self.predicted_home_score < self.predicted_away_score:
            return 'away'
        return 'draw'

    def save_to_firebase(self):
        """Save prediction to Firebase"""
        prediction_data = {
            'user_id': self.user_id,
            'username': self.username,
            'match_id': self.match_id,
            'home_team': self.home_team,
            'away_team': self.away_team,
            'predicted_home_score': self.predicted_home_score,
            'predicted_away_score': self.predicted_away_score,
            'predicted_at': self.predicted_at,
            'points_earned': self.points_earned,
            'is_processed': self.is_processed
        }
        db.reference(f'Predictions/{self.prediction_id}').set(prediction_data)

    @classmethod
    def load_from_firebase(cls, prediction_id: str) -> Optional['MatchPrediction']:
        """Load prediction from Firebase"""
        pred_ref = db.reference(f'Predictions/{prediction_id}')
        pred_data = pred_ref.get()

        if not pred_data:
            return None

        return cls(
            prediction_id=prediction_id,
            user_id=pred_data.get('user_id', ''),
            username=pred_data.get('username', ''),
            match_id=pred_data.get('match_id', ''),
            home_team=pred_data.get('home_team', ''),
            away_team=pred_data.get('away_team', ''),
            predicted_home_score=pred_data.get('predicted_home_score', 0),
            predicted_away_score=pred_data.get('predicted_away_score', 0),
            predicted_at=pred_data.get('predicted_at', ''),
            points_earned=pred_data.get('points_earned', 0),
            is_processed=pred_data.get('is_processed', False)
        )

    @staticmethod
    def get_user_prediction_for_match(user_id: str, match_id: str) -> Optional['MatchPrediction']:
        """Get a user's prediction for a specific match"""
        preds_ref = db.reference('Predictions')
        all_preds = preds_ref.get() or {}

        for pred_id, pred_data in all_preds.items():
            if pred_data.get('user_id') == user_id and pred_data.get('match_id') == match_id:
                return MatchPrediction.load_from_firebase(pred_id)
        return None

    @staticmethod
    def get_user_predictions(user_id: str) -> List['MatchPrediction']:
        """Get all predictions for a user"""
        preds_ref = db.reference('Predictions')
        all_preds = preds_ref.get() or {}

        user_preds = []
        for pred_id, pred_data in all_preds.items():
            if pred_data.get('user_id') == user_id:
                pred = MatchPrediction.load_from_firebase(pred_id)
                if pred:
                    user_preds.append(pred)

        # Sort by predicted_at descending
        user_preds.sort(key=lambda x: x.predicted_at, reverse=True)
        return user_preds

    @staticmethod
    def get_match_predictions(match_id: str) -> List['MatchPrediction']:
        """Get all predictions for a specific match"""
        preds_ref = db.reference('Predictions')
        all_preds = preds_ref.get() or {}

        match_preds = []
        for pred_id, pred_data in all_preds.items():
            if pred_data.get('match_id') == match_id:
                pred = MatchPrediction.load_from_firebase(pred_id)
                if pred:
                    match_preds.append(pred)

        return match_preds

    def calculate_points(self, actual_home_score: int, actual_away_score: int) -> int:
        """Calculate points earned for this prediction"""
        points = 0

        # Determine actual result
        if actual_home_score > actual_away_score:
            actual_result = 'home'
        elif actual_home_score < actual_away_score:
            actual_result = 'away'
        else:
            actual_result = 'draw'

        predicted_result = self.get_predicted_result()

        # Points for correct result
        if predicted_result == actual_result:
            points += 3

            # Bonus for exact score
            if self.predicted_home_score == actual_home_score and self.predicted_away_score == actual_away_score:
                points += 5

        return points

    def process_result(self, actual_home_score: int, actual_away_score: int):
        """Process the match result and update points"""
        if self.is_processed:
            return

        self.points_earned = self.calculate_points(actual_home_score, actual_away_score)
        self.is_processed = True
        self.save_to_firebase()

        # Update user's prediction points
        PredictionLeaderboard.add_points(self.user_id, self.username, self.points_earned)


class PredictionLeaderboard:
    """Manages the predictions leaderboard"""

    @staticmethod
    def get_user_stats(user_id: str) -> Dict:
        """Get a user's prediction stats"""
        stats_ref = db.reference(f'PredictionStats/{user_id}')
        stats = stats_ref.get() or {}

        return {
            'user_id': user_id,
            'username': stats.get('username', 'Unknown'),
            'total_points': stats.get('total_points', 0),
            'total_predictions': stats.get('total_predictions', 0),
            'correct_results': stats.get('correct_results', 0),
            'exact_scores': stats.get('exact_scores', 0)
        }

    @staticmethod
    def add_points(user_id: str, username: str, points: int):
        """Add points to a user's prediction total"""
        stats_ref = db.reference(f'PredictionStats/{user_id}')
        current_stats = stats_ref.get() or {}

        new_stats = {
            'username': username,
            'total_points': current_stats.get('total_points', 0) + points,
            'total_predictions': current_stats.get('total_predictions', 0) + 1,
            'correct_results': current_stats.get('correct_results', 0) + (1 if points >= 3 else 0),
            'exact_scores': current_stats.get('exact_scores', 0) + (1 if points >= 8 else 0)
        }
        stats_ref.set(new_stats)

    @staticmethod
    def increment_prediction_count(user_id: str, username: str):
        """Increment the prediction count when a user makes a prediction"""
        stats_ref = db.reference(f'PredictionStats/{user_id}')
        current_stats = stats_ref.get() or {}

        # Only update username and ensure user exists in stats
        if not current_stats:
            stats_ref.set({
                'username': username,
                'total_points': 0,
                'total_predictions': 0,
                'correct_results': 0,
                'exact_scores': 0
            })

    @staticmethod
    def get_leaderboard(limit: int = 50) -> List[Dict]:
        """Get the predictions leaderboard"""
        stats_ref = db.reference('PredictionStats')
        all_stats = stats_ref.get() or {}

        leaderboard = []
        for user_id, stats in all_stats.items():
            leaderboard.append({
                'user_id': user_id,
                'username': stats.get('username', 'Unknown'),
                'total_points': stats.get('total_points', 0),
                'total_predictions': stats.get('total_predictions', 0),
                'correct_results': stats.get('correct_results', 0),
                'exact_scores': stats.get('exact_scores', 0)
            })

        # Sort by total points descending
        leaderboard.sort(key=lambda x: x['total_points'], reverse=True)

        # Add positions
        for i, entry in enumerate(leaderboard[:limit]):
            entry['position'] = i + 1

        return leaderboard[:limit]
