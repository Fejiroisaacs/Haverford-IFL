"""
Unit tests for utility functions in functions.py
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from functions import get_k_recent_potm, get_player_potm, get_potm_match


@pytest.mark.unit
class TestPOTMFunctions:
    """Tests for Player of the Match (POTM) functions."""

    @patch('functions.pd.read_csv')
    def test_get_k_recent_potm_basic(self, mock_read_csv):
        """Test getting recent POTM winners."""
        # Mock match results
        mock_results = pd.DataFrame({
            'Season': [6, 6, 6],
            'Match ID': [1, 2, 3],
            'Time': ['7:00 PM', '8:00 PM', '7:00 PM']
        })

        # Mock player stats
        mock_stats = pd.DataFrame({
            'Name': ['John Doe', 'Jane Smith', 'Bob Wilson'],
            'Match ID': [1, 2, 3],
            'POTM': [1, 1, 1]
        })

        mock_read_csv.side_effect = [mock_results, mock_stats]

        result = get_k_recent_potm(2, season=6)

        assert len(result) == 2
        assert all('Name' in item and 'Match ID' in item for item in result)

    @patch('functions.pd.read_csv')
    def test_get_k_recent_potm_excludes_forfeits(self, mock_read_csv):
        """Test that forfeited matches are excluded from POTM."""
        mock_results = pd.DataFrame({
            'Season': [6, 6, 6],
            'Match ID': [1, 2, 3],
            'Time': ['7:00 PM', 'Forfeit', '8:00 PM']
        })

        mock_stats = pd.DataFrame({
            'Name': ['John Doe', 'Bob Wilson'],
            'Match ID': [1, 3],
            'POTM': [1, 1]
        })

        mock_read_csv.side_effect = [mock_results, mock_stats]

        result = get_k_recent_potm(3, season=6)

        # Should only return 2 results (forfeit excluded)
        assert len(result) == 2
        assert all(item['Match ID'] in [1, 3] for item in result)

    @patch('functions.pd.read_csv')
    def test_get_player_potm(self, mock_read_csv):
        """Test getting POTM wins for a specific player."""
        mock_player_stats = pd.DataFrame({
            'Name': ['John Doe', 'John Doe', 'Jane Smith'],
            'Match ID': [1, 3, 2],
            'POTM': [1, 1, 1]
        })

        mock_match_data = pd.DataFrame({
            'Team 1': ['Team A', 'Team C', 'Team B'],
            'Team 2': ['Team B', 'Team D', 'Team D'],
            'Match ID': [1, 2, 3]
        })

        mock_read_csv.side_effect = [mock_player_stats, mock_match_data]

        result = get_player_potm('John Doe')

        assert len(result) == 2
        assert all(item['Name'] == 'John Doe' for item in result)
        assert all('Team 1' in item and 'Team 2' in item for item in result)

    @patch('functions.pd.read_csv')
    def test_get_potm_match_found(self, mock_read_csv):
        """Test getting POTM for a specific match."""
        mock_data = pd.DataFrame({
            'Name': ['John Doe', 'Jane Smith'],
            'Match ID': [1, 2],
            'POTM': [1, 0]
        })

        mock_read_csv.return_value = mock_data

        result = get_potm_match(1)

        assert result is not None
        assert result['Name'] == 'John Doe'
        assert result['Match ID'] == 1
        assert result['POTM'] == 1

    @patch('functions.pd.read_csv')
    def test_get_potm_match_not_found(self, mock_read_csv):
        """Test getting POTM when none exists for match."""
        mock_data = pd.DataFrame({
            'Name': ['John Doe'],
            'Match ID': [1],
            'POTM': [0]
        })

        mock_read_csv.return_value = mock_data

        result = get_potm_match(999)

        assert result is None


@pytest.mark.unit
class TestEmailFunction:
    """Tests for email sending functionality."""

    @patch('functions.yagmail.SMTP')
    @patch('functions.tempfile.NamedTemporaryFile')
    @patch('functions.os.getenv')
    def test_send_email_success(self, mock_getenv, mock_temp_file, mock_smtp):
        """Test successful email sending."""
        from functions import send_email

        # Setup mocks
        mock_getenv.side_effect = lambda key: {
            'oauth2': '{"token": "test"}',
            'OUR_EMAIL': 'test@example.com',
            'OUR_EMAIL_PASSWORD': 'password'
        }.get(key)

        mock_temp = MagicMock()
        mock_temp.name = 'temp_file.json'
        mock_temp_file.return_value.__enter__.return_value = mock_temp

        mock_mailer = MagicMock()
        mock_smtp.return_value = mock_mailer

        # Call function
        send_email(
            email='sender@example.com',
            bccs=['recipient@example.com'],
            subject='Test Subject',
            message='Test Message'
        )

        # Verify email was sent
        mock_mailer.send.assert_called_once()
        call_args = mock_mailer.send.call_args
        assert call_args[1]['subject'] == 'Test Subject'
        assert call_args[1]['contents'] == 'Test Message'

    @patch('functions.os.getenv')
    def test_send_email_missing_credentials(self, mock_getenv):
        """Test email sending with missing OAuth credentials."""
        from functions import send_email

        mock_getenv.return_value = None

        with pytest.raises(ValueError, match="OAuth2 credentials not found"):
            send_email(
                email='test@example.com',
                bccs=[],
                subject='Test',
                message='Test'
            )
