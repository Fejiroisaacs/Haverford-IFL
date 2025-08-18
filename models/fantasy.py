from pydantic import BaseModel
from typing import List, Optional, Dict
import pandas as pd
import numpy as np
from firebase_admin import db

class FantasyPlayer(BaseModel):
    first_name: str
    last_name: str
    team: str
    season: int
    primary_position: str
    ovr_rating: Optional[int]
    fantasy_cost: float
    total_points: int = 0
    mw_points: Dict[str, int] = {}

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

class FantasyTeam(BaseModel):
    current_team: List[str] = []  # List of player names in starting lineup
    all_players: List[str] = []   # List of all owned player names
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
    team: FantasyTeam = FantasyTeam()
    
    # Team creation rules
    CREATING_TEAM_RULES = ("You need to have players from at least 5 different teams, "
                          "you need at least 2 Goalkeepers, at least 2 Defenders, "
                          "at least 1 Midfielder, and at least 2 Forward players.")
    
    WEEKLY_TEAM_RULES = ("You need to start players from 5 different teams, you need a Goalkeeper, "
                        "at least 2 defenders + midfielders, at least 1 Forward player.")
    
    TRANSFER_ACTIVE_RULES = ("Your starting team needs to have players from at least 5 different teams, "
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
                
                # Aggregate stats by player name (sum across all seasons)
                stats_aggregated = stats_df.groupby('full_name').agg({
                    'Goals': 'sum',
                    'Assists': 'sum', 
                    'Saves': 'sum'
                }).reset_index()
                
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
