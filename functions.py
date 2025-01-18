import yagmail
import os, tempfile
import json, ast, random, pandas as pd
from dotenv import load_dotenv

load_dotenv()

def send_email(email, bccs, subject, message, attachment=None):
    oauth2_credentials = ast.literal_eval(os.getenv("oauth2"))
    with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.json') as temp_file:
        json.dump(oauth2_credentials, temp_file)
        temp_filename = temp_file.name
        
    mail_sender = yagmail.SMTP(
        user=f'{os.getenv("OUR_EMAIL")}',
        password=f'{os.getenv("OUR_EMAIL_PASSWORD")}',
        oauth2_file=temp_filename,
    )
    try:
        mail_sender.send(
            to=email,
            bcc=bccs,
            subject=subject,
            contents=message,
            attachments=attachment,
            
        )
        print('Email sent')    
    except Exception as e:
        print(str(e))
        print('Email not sent')    

    os.remove(temp_filename)

def get_random_potm_images(k):
    images = random.sample(os.listdir('templates/static/Images/POTM'), k=k)
    images = [int(image.split('.png')[0]) for image in images if image.endswith('.png')]
    
    with open('data/player_match_stats.csv') as file:
        data = pd.read_csv(file)
    data = data[(data['POTM'] == 1) & (data['Match Number (All Seasons)'].isin(images))]
    return data[['Name', 'Match Number (All Seasons)']].to_dict(orient='records')

def get_player_potm(player):
    data = pd.read_csv('data/player_match_stats.csv')
    match_data = pd.read_csv('data/Match_Results.csv', usecols=['Team 1', 'Team 2', 'Match ID'])
    
    data = data.rename(columns={'Match Number (All Seasons)': 'Match ID'})
    data = data[(data['POTM'] == 1) & (data['Name'] == player)][['Name', 'Match ID']]
    
    merged_data = pd.merge(data, match_data, on='Match ID', how='inner')
    
    return merged_data.to_dict(orient='records')

import pandas as pd

def get_potm_match(match_id):
    match_data = pd.read_csv('data/player_match_stats.csv', usecols=['Name', 'Match Number (All Seasons)', 'POTM'])
    filtered_data = match_data[(match_data['POTM'] == 1) & (match_data['Match Number (All Seasons)'] == int(match_id))]
    
    if not filtered_data.empty:
        return filtered_data.to_dict(orient='records')[0]
    else:
        return None 