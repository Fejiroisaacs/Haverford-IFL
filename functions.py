import yagmail
import os, tempfile
import json, ast, pandas as pd
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()

def send_email(email, bccs, subject, message, attachment=None):
    """
    Send email using yagmail with OAuth2 authentication.

    Args:
        email: Sender email
        bccs: List of BCC recipients
        subject: Email subject
        message: Email body
        attachment: Optional attachment

    Raises:
        ValueError: If credentials are missing
        Exception: If email sending fails
    """
    temp_filename = None
    try:
        oauth2_str = os.getenv("oauth2")
        if not oauth2_str:
            raise ValueError("OAuth2 credentials not found in environment")

        oauth2_credentials = ast.literal_eval(oauth2_str)

        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.json') as temp_file:
            json.dump(oauth2_credentials, temp_file)
            temp_filename = temp_file.name

        mail_sender = yagmail.SMTP(
            user=f'{os.getenv("OUR_EMAIL")}',
            password=f'{os.getenv("OUR_EMAIL_PASSWORD")}',
            oauth2_file=temp_filename,
        )

        mail_sender.send(
            to=email,
            bcc=bccs,
            subject=subject,
            contents=message,
            attachments=attachment,
        )

    except (ValueError, KeyError) as e:
        raise
    except Exception as e:
        raise
    finally:
        if temp_filename and os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except OSError as e:
                print(f"Failed to remove temp file: {str(e)}")

@lru_cache(maxsize=5)
def get_k_recent_potm(k, season=None):
    match_results = pd.read_csv('data/Match_Results.csv')
    if season:
        match_results = match_results[(match_results["Season"] == int(season)) & (match_results["Time"] != "Forfeit")]
    recent_matches = match_results.tail(k) 
    recent_ids = recent_matches['Match ID'].tolist()

    player_stats = pd.read_csv('data/player_match_stats.csv')
    recent_potm = player_stats[(player_stats['POTM'] == 1) & (player_stats['Match ID'].isin(recent_ids))]

    return recent_potm[['Name', 'Match ID']].to_dict(orient='records')

def get_player_potm(player):
    data = pd.read_csv('data/player_match_stats.csv')
    match_data = pd.read_csv('data/Match_Results.csv', usecols=['Team 1', 'Team 2', 'Match ID'])
    
    data = data.rename(columns={'Match ID': 'Match ID'})
    data = data[(data['POTM'] == 1) & (data['Name'] == player)][['Name', 'Match ID']]
    
    merged_data = pd.merge(data, match_data, on='Match ID', how='inner')
    
    return merged_data.to_dict(orient='records')

def get_potm_match(match_id):
    match_data = pd.read_csv('data/player_match_stats.csv', usecols=['Name', 'Match ID', 'POTM'])
    filtered_data = match_data[(match_data['POTM'] == 1) & (match_data['Match ID'] == int(match_id))]
    
    if not filtered_data.empty:
        return filtered_data.to_dict(orient='records')[0]
    else:
        return None 