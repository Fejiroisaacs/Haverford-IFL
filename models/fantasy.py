from pydantic import BaseModel, Field
from typing import List, Optional, Dict, ClassVar, Tuple
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
    total_points: int = 0  # All-time total points
    week_points: int = 0
    season_points: Dict[str, int] = Field(default_factory=dict)  # Points per season: {"1": 50, "2": 75, ...}
    free_transfers: int = 2
    team: FantasyTeam = Field(default_factory=FantasyTeam)

    # Team creation rules (ClassVar to distinguish from model fields in Pydantic V2)
    CREATING_TEAM_RULES: ClassVar[str] = ("You need to have players from at least 5 different teams, "
                          "you need at least 2 Goalkeepers, at least 2 Defenders, "
                          "at least 1 Midfielder, and at least 2 Forward players.")

    WEEKLY_TEAM_RULES: ClassVar[str] = ("You need to start players from 4 different teams, you need a Goalkeeper, "
                        "at least 2 defenders + midfielders, at least 1 Forward player.")

    TRANSFER_ACTIVE_RULES: ClassVar[str] = ("Your starting team needs to have players from at least 4 different teams, "
                           "you need a Goalkeeper, at least 2 defenders + midfielders combined (must include a defender), "
                           "and at least 1 Forward player.")
    
    def save_to_firebase(self):
        """Save user data to Firebase"""
        user_data = {
            'username': self.username,
            'admin': self.admin,
            'total_balance': self.total_balance,
            'total_points': self.total_points,
            'week_points': self.week_points,
            'season_points': self.season_points,
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
            season_points=user_data.get('season_points', {}),
            free_transfers=user_data.get('free_transfers', 2),
            team=team
        )

class FantasyService:
    def __init__(self, season: int = None):
        self.players_df = None
        self.season = season
        self.load_players_data()
    
    @staticmethod
    def get_current_season() -> int:
        """Get the current season from Firebase settings"""
        try:
            week_data = db.reference('Fantasy/current_week').get() or {}
            season = week_data.get('Season')
            if season:
                return int(season)
        except Exception:
            pass
        # Fall back to most recent season in Fantasy_Data.csv
        try:
            df = pd.read_csv('data/Fantasy_Data.csv')
            df.columns = [c.strip() for c in df.columns]
            return int(df['Season'].max())
        except Exception:
            return 1
    
    @staticmethod
    def get_min_different_teams(context: str = 'squad') -> int:
        """Get minimum different teams requirement from Firebase settings.
        context: 'squad' for full squad (8 players), 'starting' for weekly team (5 players)
        """
        try:
            settings = db.reference('Fantasy/settings').get() or {}
            if context == 'squad':
                return settings.get('min_different_teams_squad', 5)
            return settings.get('min_different_teams_starting', 4)
        except Exception:
            return 5 if context == 'squad' else 4
    
    def load_players_data(self):
        """Load players data from CSV, filtered by season"""
        try:
            full_df = pd.read_csv('data/Fantasy_Data.csv')
            # Clean column names
            full_df.columns = [col.strip() for col in full_df.columns]
            
            # Filter by season if specified
            if self.season is not None:
                season_df = full_df[full_df['Season'] == self.season]
                if season_df.empty:
                    max_season = full_df['Season'].max()
                    print(f"Warning: No players found for Season {self.season}. Falling back to Season {max_season}")
                    full_df = full_df[full_df['Season'] == max_season]
                else:
                    full_df = season_df
            
            # Rename for consistency
            column_mapping = {
                'First Name': 'First',
                'Last Name': 'Last',
                'Primary Position': 'Primary_Position'
            }
            full_df.rename(columns=column_mapping, inplace=True)
            
            # Clean OVR Rating column - replace '-' with NaN and convert to numeric
            full_df['OVR Rating'] = pd.to_numeric(
                full_df['OVR Rating'].replace('-', np.nan), 
                errors='coerce'
            )
            full_df['OVR Rating'] = full_df['OVR Rating'].fillna(50)
            
            # Create full name column
            full_df['full_name'] = full_df['First'] + ' ' + full_df['Last']
            
            # Keep only core columns
            core_columns = ['First', 'Last', 'Team', 'Season', 'Primary_Position', 
                          'OVR Rating', 'Fantasy Cost', 'full_name']
            available_cols = [col for col in core_columns if col in full_df.columns]
            self.players_df = full_df[available_cols].copy()
                
        except Exception as e:
            print(f"Error loading players data: {e}")
            self.players_df = pd.DataFrame()
    
    def has_players_for_season(self, season: int) -> bool:
        """Check if Fantasy_Data.csv has players for a given season"""
        try:
            full_df = pd.read_csv('data/Fantasy_Data.csv')
            full_df.columns = [col.strip() for col in full_df.columns]
            return not full_df[full_df['Season'] == season].empty
        except Exception:
            return False
    
    def get_all_players(self) -> List[Dict]:
        """Get all available fantasy players for the current season"""
        if self.players_df is None or self.players_df.empty:
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
        
        min_teams = self.get_min_different_teams('squad')
        if len(set(teams)) < min_teams:
            return False, f"You need players from at least {min_teams} different teams"
        
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
        
        min_teams = self.get_min_different_teams('starting')
        if len(set(teams)) < min_teams:
            return False, f"You need to start players from at least {min_teams} different teams"
        
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
        
        min_teams = self.get_min_different_teams('squad')
        if len(set(teams)) < min_teams:
            return False, f"Transfer would violate team diversity rule (need {min_teams} different teams)"
        
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
            
            min_starting_teams = self.get_min_different_teams('starting')
            if len(set(starting_teams)) < min_starting_teams:
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
        """Save prediction to Firebase with indexed paths for efficient queries"""
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
        # Primary storage
        db.reference(f'Predictions/{self.prediction_id}').set(prediction_data)
        # Indexed by user + match for fast lookups
        db.reference(f'UserPredictions/{self.user_id}/{self.match_id}').set({
            'prediction_id': self.prediction_id,
            **prediction_data
        })
        # Indexed by match for fast match-level queries
        db.reference(f'MatchPredictions/{self.match_id}/{self.prediction_id}').set(prediction_data)

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
        """Get a user's prediction for a specific match (indexed lookup)"""
        # Try indexed path first
        indexed_ref = db.reference(f'UserPredictions/{user_id}/{match_id}')
        indexed_data = indexed_ref.get()
        
        if indexed_data and 'prediction_id' in indexed_data:
            return MatchPrediction(
                prediction_id=indexed_data['prediction_id'],
                user_id=indexed_data.get('user_id', user_id),
                username=indexed_data.get('username', ''),
                match_id=indexed_data.get('match_id', match_id),
                home_team=indexed_data.get('home_team', ''),
                away_team=indexed_data.get('away_team', ''),
                predicted_home_score=indexed_data.get('predicted_home_score', 0),
                predicted_away_score=indexed_data.get('predicted_away_score', 0),
                predicted_at=indexed_data.get('predicted_at', ''),
                points_earned=indexed_data.get('points_earned', 0),
                is_processed=indexed_data.get('is_processed', False)
            )
        
        # Fallback to legacy full scan for old data
        preds_ref = db.reference('Predictions')
        all_preds = preds_ref.get() or {}
        for pred_id, pred_data in all_preds.items():
            if pred_data.get('user_id') == user_id and pred_data.get('match_id') == match_id:
                return MatchPrediction.load_from_firebase(pred_id)
        return None

    @staticmethod
    def get_user_predictions(user_id: str) -> List['MatchPrediction']:
        """Get all predictions for a user (indexed lookup)"""
        # Try indexed path first
        user_preds_ref = db.reference(f'UserPredictions/{user_id}')
        user_preds_data = user_preds_ref.get() or {}
        
        user_preds = []
        if user_preds_data:
            for match_id, pred_data in user_preds_data.items():
                try:
                    pred = MatchPrediction(
                        prediction_id=pred_data.get('prediction_id', ''),
                        user_id=pred_data.get('user_id', user_id),
                        username=pred_data.get('username', ''),
                        match_id=pred_data.get('match_id', match_id),
                        home_team=pred_data.get('home_team', ''),
                        away_team=pred_data.get('away_team', ''),
                        predicted_home_score=pred_data.get('predicted_home_score', 0),
                        predicted_away_score=pred_data.get('predicted_away_score', 0),
                        predicted_at=pred_data.get('predicted_at', ''),
                        points_earned=pred_data.get('points_earned', 0),
                        is_processed=pred_data.get('is_processed', False)
                    )
                    user_preds.append(pred)
                except Exception:
                    continue
        else:
            # Fallback to legacy full scan
            preds_ref = db.reference('Predictions')
            all_preds = preds_ref.get() or {}
            for pred_id, pred_data in all_preds.items():
                if pred_data.get('user_id') == user_id:
                    pred = MatchPrediction.load_from_firebase(pred_id)
                    if pred:
                        user_preds.append(pred)

        user_preds.sort(key=lambda x: x.predicted_at, reverse=True)
        return user_preds

    @staticmethod
    def get_match_predictions(match_id: str) -> List['MatchPrediction']:
        """Get all predictions for a specific match (indexed lookup)"""
        # Try indexed path first
        match_preds_ref = db.reference(f'MatchPredictions/{match_id}')
        match_preds_data = match_preds_ref.get() or {}
        
        match_preds = []
        if match_preds_data:
            for pred_id, pred_data in match_preds_data.items():
                try:
                    pred = MatchPrediction(
                        prediction_id=pred_id,
                        user_id=pred_data.get('user_id', ''),
                        username=pred_data.get('username', ''),
                        match_id=pred_data.get('match_id', match_id),
                        home_team=pred_data.get('home_team', ''),
                        away_team=pred_data.get('away_team', ''),
                        predicted_home_score=pred_data.get('predicted_home_score', 0),
                        predicted_away_score=pred_data.get('predicted_away_score', 0),
                        predicted_at=pred_data.get('predicted_at', ''),
                        points_earned=pred_data.get('points_earned', 0),
                        is_processed=pred_data.get('is_processed', False)
                    )
                    match_preds.append(pred)
                except Exception:
                    continue
        else:
            # Fallback to legacy full scan
            preds_ref = db.reference('Predictions')
            all_preds = preds_ref.get() or {}
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


# ============ Fantasy Points Calculator ============

class FantasyPointsCalculator:
    """Handles all fantasy points calculation based on match performance"""

    # Points configuration constants
    GOAL_POINTS = {'F': 3, 'M': 4, 'D': 5, 'GK': 6}
    ASSIST_POINTS = {'F': 2, 'M': 1, 'D': 2, 'GK': 2}
    CLEAN_SHEET_POINTS = {'F': 1, 'M': 2, 'D': 3, 'GK': 5}
    WIN_BONUS = 1
    START_BONUS = 1
    POTM_BONUS = 3
    RED_CARD_PENALTY = -5
    YELLOW_CARD_PENALTY = -2
    CAPTAIN_MULTIPLIER = 2

    def __init__(self):
        self.player_stats_df = None
        self.match_results_df = None
        self.matchweeks_df = None
        self.fantasy_data_df = None
        self._load_data()

    def _load_data(self):
        """Load all required CSV data files"""
        try:
            # Load player match stats
            self.player_stats_df = pd.read_csv('data/player_match_stats.csv')
            self.player_stats_df.columns = [col.strip() for col in self.player_stats_df.columns]

            # Load match results
            self.match_results_df = pd.read_csv('data/Match_Results.csv')
            self.match_results_df.columns = [col.strip() for col in self.match_results_df.columns]

            # Load matchweeks
            self.matchweeks_df = pd.read_csv('data/matchweeks.csv')
            self.matchweeks_df.columns = [col.strip() for col in self.matchweeks_df.columns]

            # Load fantasy data for team mapping
            self.fantasy_data_df = pd.read_csv('data/Fantasy_Data.csv')
            self.fantasy_data_df.columns = [col.strip() for col in self.fantasy_data_df.columns]

        except Exception as e:
            print(f"Error loading data for points calculation: {e}")

    def get_match_ids_for_matchweek(self, season: int, matchweek: int) -> List[int]:
        """Get all match IDs within a matchweek range"""
        if self.matchweeks_df is None:
            return []

        mw_row = self.matchweeks_df[
            (self.matchweeks_df['Season'] == season) &
            (self.matchweeks_df['MW'] == matchweek)
        ]

        if mw_row.empty:
            return []

        start_id = int(mw_row.iloc[0]['Start ID'])
        end_id = int(mw_row.iloc[0]['End ID'])

        return list(range(start_id, end_id + 1))

    def get_player_team(self, player_name: str) -> Optional[str]:
        """Get the 3-letter team code for a player from Fantasy_Data.csv"""
        if self.fantasy_data_df is None:
            return None

        # Create full name from First Name and Last Name
        self.fantasy_data_df['full_name'] = (
            self.fantasy_data_df['First Name'].fillna('') + ' ' +
            self.fantasy_data_df['Last Name'].fillna('')
        ).str.strip()

        player_row = self.fantasy_data_df[self.fantasy_data_df['full_name'] == player_name]

        if player_row.empty:
            return None

        return player_row.iloc[0]['Team']

    def did_team_win(self, team_code: str, match_id: int) -> bool:
        """Check if a team won a specific match"""
        if self.match_results_df is None:
            return False

        match_row = self.match_results_df[self.match_results_df['Match ID'] == match_id]

        if match_row.empty:
            return False

        row = match_row.iloc[0]

        # Check if team is Team 1 and won
        if row['Team 1'] == team_code and row['Win Team 1'] == 1:
            return True

        # Check if team is Team 2 and won
        if row['Team 2'] == team_code and row['Win Team 2'] == 1:
            return True

        return False

    def is_clean_sheet(self, team_code: str, match_id: int) -> bool:
        """Check if team kept a clean sheet (opponent scored 0)"""
        if self.match_results_df is None:
            return False

        match_row = self.match_results_df[self.match_results_df['Match ID'] == match_id]

        if match_row.empty:
            return False

        row = match_row.iloc[0]

        # If team is Team 1, check if Team 2 scored 0
        if row['Team 1'] == team_code:
            return int(row['Score Team 2']) == 0

        # If team is Team 2, check if Team 1 scored 0
        if row['Team 2'] == team_code:
            return int(row['Score Team 1']) == 0

        return False

    def parse_card_info(self, yr_value) -> Tuple[int, int]:
        """Parse Y-R column to get yellow and red card counts
        Returns (yellow_count, red_count)
        """
        if pd.isna(yr_value) or yr_value == '-' or yr_value == '':
            return (0, 0)

        yr_str = str(yr_value).strip().upper()

        # Handle various formats
        if yr_str == 'Y':
            return (1, 0)
        elif yr_str == 'R':
            return (0, 1)
        elif yr_str == 'YY' or yr_str == '2Y':
            return (2, 0)
        elif yr_str == 'YR':
            return (1, 1)

        # Try to parse as number (yellow cards)
        try:
            yellows = int(yr_str)
            return (yellows, 0)
        except:
            pass

        return (0, 0)

    def calculate_player_match_points(
        self,
        player_name: str,
        match_id: int,
        is_captain: bool = False
    ) -> Dict:
        """
        Calculate points for a single player in a single match.
        Returns breakdown dict with total and component points.
        """
        result = {
            'goals': 0,
            'assists': 0,
            'start': 0,
            'potm': 0,
            'cards': 0,
            'win': 0,
            'clean_sheet': 0,
            'total': 0,
            'played': False
        }

        if self.player_stats_df is None:
            return result

        # Find player's match stats
        player_stats = self.player_stats_df[
            (self.player_stats_df['Name'] == player_name) &
            (self.player_stats_df['Match ID'] == match_id)
        ]

        if player_stats.empty:
            return result  # Player didn't play

        row = player_stats.iloc[0]
        position = row['P']

        if position == '-' or pd.isna(position) or position == '':
            return result  # Non-playing sub

        result['played'] = True
        team_code = row['My Team']

        # Goals
        goals = int(row['G']) if pd.notna(row['G']) else 0
        result['goals'] = goals * self.GOAL_POINTS.get(position, 0)

        # Assists
        assists = int(row['A']) if pd.notna(row['A']) else 0
        result['assists'] = assists * self.ASSIST_POINTS.get(position, 0)

        # Starting bonus
        if row['Start?'] == 'Y':
            result['start'] = self.START_BONUS

        # POTM bonus
        if row['POTM'] == 1 or row['POTM'] == '1':
            result['potm'] = self.POTM_BONUS

        # Cards
        yellows, reds = self.parse_card_info(row['Y-R'])
        result['cards'] = (yellows * self.YELLOW_CARD_PENALTY) + (reds * self.RED_CARD_PENALTY)

        # Win bonus
        if self.did_team_win(team_code, match_id):
            result['win'] = self.WIN_BONUS

        # Clean sheet
        if position in self.CLEAN_SHEET_POINTS and self.is_clean_sheet(team_code, match_id):
            result['clean_sheet'] = self.CLEAN_SHEET_POINTS[position]

        # Calculate total
        result['total'] = sum([
            result['goals'],
            result['assists'],
            result['start'],
            result['potm'],
            result['cards'],
            result['win'],
            result['clean_sheet']
        ])

        # Captain multiplier
        if is_captain:
            original_total = result['total']
            result['total'] *= self.CAPTAIN_MULTIPLIER
            result['captain_bonus'] = result['total'] - original_total

        return result

    def calculate_player_matchweek_points(
        self,
        player_name: str,
        season: int,
        matchweek: int,
        is_captain: bool = False
    ) -> int:
        """Calculate total points for a player across all matches in a matchweek"""
        match_ids = self.get_match_ids_for_matchweek(season, matchweek)

        total_points = 0
        for match_id in match_ids:
            result = self.calculate_player_match_points(player_name, match_id, is_captain)
            total_points += result['total']

        return total_points

    def calculate_user_matchweek_points(
        self,
        current_team: List[str],
        captain: Optional[str],
        season: int,
        matchweek: int
    ) -> Dict:
        """Calculate total matchweek points for a user's starting 5"""
        breakdown = {
            'players': {},
            'total': 0
        }

        for player_name in current_team:
            is_captain = (player_name == captain)
            points = self.calculate_player_matchweek_points(
                player_name, season, matchweek, is_captain
            )
            breakdown['players'][player_name] = {
                'points': points,
                'is_captain': is_captain
            }
            breakdown['total'] += points

        return breakdown

    def bulk_compute_all_player_points(self, season: int, matchweek: int) -> Dict:
        """Compute points for ALL players who appeared in the matchweek's matches.
        Returns {player_name: {goals, assists, start, potm, cards, win, clean_sheet, total, matches_played, position, team}}
        """
        match_ids = self.get_match_ids_for_matchweek(season, matchweek)
        if not match_ids:
            return {}

        all_player_points = {}

        for match_id in match_ids:
            if self.player_stats_df is None:
                continue

            # Get all players who appeared in this match
            match_players = self.player_stats_df[
                self.player_stats_df['Match ID'] == match_id
            ]

            for _, player_row in match_players.iterrows():
                player_name = player_row['Name']
                position = player_row['P']

                # Skip non-playing entries
                if position == '-' or pd.isna(position) or position == '':
                    continue

                # Calculate this player's points for this match (without captain bonus)
                result = self.calculate_player_match_points(player_name, match_id, is_captain=False)

                if not result['played']:
                    continue

                # Accumulate points across matches in the matchweek
                if player_name not in all_player_points:
                    team_code = self.get_player_team(player_name)
                    all_player_points[player_name] = {
                        'goals': 0, 'assists': 0, 'start': 0, 'potm': 0,
                        'cards': 0, 'win': 0, 'clean_sheet': 0, 'total': 0,
                        'matches_played': 0, 'position': position, 'team': team_code or ''
                    }

                pp = all_player_points[player_name]
                pp['goals'] += result['goals']
                pp['assists'] += result['assists']
                pp['start'] += result['start']
                pp['potm'] += result['potm']
                pp['cards'] += result['cards']
                pp['win'] += result['win']
                pp['clean_sheet'] += result['clean_sheet']
                pp['total'] += result['total']
                pp['matches_played'] += 1

        return all_player_points

    def cache_player_points_to_firebase(self, season: int, matchweek: int, all_player_points: Dict):
        """Save pre-computed player points to Firebase for the explore page"""
        cache_key = f"S{season}_MW{matchweek}"
        cache_ref = db.reference(f'Fantasy/PlayerPoints/{cache_key}')

        # Convert to Firebase-safe format (no dots in keys)
        firebase_data = {}
        for player_name, points_data in all_player_points.items():
            safe_key = player_name.replace('.', '_')
            firebase_data[safe_key] = {
                'player_name': player_name,
                **points_data
            }

        cache_ref.set(firebase_data)

    @staticmethod
    def get_cached_player_points(season: int, matchweek: int) -> Dict:
        """Read pre-computed player points from Firebase (for the explore page)"""
        cache_key = f"S{season}_MW{matchweek}"
        cache_ref = db.reference(f'Fantasy/PlayerPoints/{cache_key}')
        cached_data = cache_ref.get() or {}

        # Convert back from Firebase format
        result = {}
        for safe_key, points_data in cached_data.items():
            player_name = points_data.get('player_name', safe_key.replace('_', '.'))
            result[player_name] = points_data

        return result

    def process_all_users_matchweek(self, season: int, matchweek: int) -> Dict:
        """Process matchweek points for all fantasy users using bulk pre-compute"""
        users_ref = db.reference('Fantasy/Users')
        history_ref = db.reference('Fantasy/UserHistory')
        snapshots_ref = db.reference('Fantasy/TeamSnapshots')
        all_users = users_ref.get() or {}
        all_snapshots = snapshots_ref.get() or {}
        snapshot_key = f"S{season}_MW{matchweek}"

        results = {
            'processed_count': 0,
            'total_points_awarded': 0,
            'errors': [],
            'user_results': []
        }

        # Step 1: Bulk pre-compute all player points for this matchweek (once)
        all_player_points = self.bulk_compute_all_player_points(season, matchweek)

        # Step 2: Cache to Firebase for the explore page
        self.cache_player_points_to_firebase(season, matchweek, all_player_points)

        # Step 3: For each user, look up their team's players from pre-computed dict
        for user_id, user_data in all_users.items():
            try:
                # Try to use snapshotted team first, fall back to current team
                user_snapshot = all_snapshots.get(user_id, {}).get(snapshot_key)
                if user_snapshot:
                    current_team = user_snapshot.get('team', [])
                    captain = user_snapshot.get('captain')
                else:
                    current_team = user_data.get('current_team', [])
                    captain = user_data.get('captain')

                # Skip users without valid starting team
                if not current_team or len(current_team) != 5:
                    continue

                # Step 4: Look up points from pre-computed dict + apply captain
                player_breakdown = {}
                week_points = 0

                for player_name in current_team:
                    is_captain = (player_name == captain)
                    base_points = all_player_points.get(player_name, {}).get('total', 0)

                    if is_captain:
                        player_points = base_points * self.CAPTAIN_MULTIPLIER
                    else:
                        player_points = base_points

                    player_breakdown[player_name] = {
                        'points': player_points,
                        'is_captain': is_captain
                    }
                    week_points += player_points

                # Update user in Firebase
                current_total = user_data.get('total_points', 0)
                current_season_points = user_data.get('season_points', {})
                season_key = str(season)
                current_season_points[season_key] = current_season_points.get(season_key, 0) + week_points

                users_ref.child(user_id).update({
                    'week_points': week_points,
                    'total_points': current_total + week_points,
                    'season_points': current_season_points
                })

                # Save to user history
                history_key = f"S{season}_MW{matchweek}"
                history_ref.child(user_id).child(history_key).set({
                    'season': season,
                    'matchweek': matchweek,
                    'points': week_points,
                    'breakdown': player_breakdown,
                    'team': current_team,
                    'captain': captain,
                    'processed_at': datetime.now().isoformat()
                })

                results['processed_count'] += 1
                results['total_points_awarded'] += week_points
                results['user_results'].append({
                    'user_id': user_id,
                    'username': user_data.get('username', 'Unknown'),
                    'week_points': week_points,
                    'breakdown': {'players': player_breakdown, 'total': week_points}
                })

            except Exception as e:
                results['errors'].append({
                    'user_id': user_id,
                    'error': str(e)
                })

        return results

    def reset_all_week_points(self) -> int:
        """Reset week_points to 0 for all users. Returns count of users reset."""
        users_ref = db.reference('Fantasy/Users')
        all_users = users_ref.get() or {}

        reset_count = 0
        for user_id in all_users.keys():
            users_ref.child(user_id).update({'week_points': 0})
            reset_count += 1

        return reset_count

    def preview_user_points(
        self,
        user_id: str,
        season: int,
        matchweek: int
    ) -> Optional[Dict]:
        """Preview points calculation for a specific user without saving"""
        user_ref = db.reference(f'Fantasy/Users/{user_id}')
        user_data = user_ref.get()

        if not user_data:
            return None

        current_team = user_data.get('current_team', [])
        if not current_team or len(current_team) != 5:
            return None

        captain = user_data.get('captain')

        breakdown = self.calculate_user_matchweek_points(
            current_team, captain, season, matchweek
        )

        return {
            'user_id': user_id,
            'username': user_data.get('username', 'Unknown'),
            'current_team': current_team,
            'captain': captain,
            'week_points': breakdown['total'],
            'breakdown': breakdown
        }
