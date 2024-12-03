import pyrebase, json, pandas as pd, ast


firebase = pyrebase.initialize_app(json.load(open("cred.json")))
fb_storage = firebase.storage()
database = firebase.database()

def upload_player_data():
    data = pd.read_csv("data/test_stats.csv")
    print(data["OVR Rating"])
    data["OVR Rating"] = data["OVR Rating"].apply(lambda x: int(x) if "Not Enough Data" not in x else -1)
    data["ATT Rating"] = data["ATT Rating"].apply(lambda x: round(float(x)) if "Not Enough Data" not in x else -1)
    data["GLK Rating"] = data["GLK Rating"].apply(lambda x: round(float(x)) if "Not Enough Data" not in x else -1)
    data["AST Rating"] = data["AST Rating"].apply(lambda x: round(float(x)) if "Not Enough Data" not in x else -1)
    data["DEF Rating"] = data["DEF Rating"].apply(lambda x: round(float(x)) if "Not Enough Data" not in x else -1)
    print(data["OVR Rating"])

    
    for i in range(data.shape[0]):
        player_data = data.iloc[i].to_dict()
        player_name = player_data["Name"]#.split(" ")
        name = player_name.split(" ")
        player_data["First Name"] = name[0]
        player_data["Last Name"] = name[-1] if len(name) > 1 else ""
        print("Player:", player_name)
        database.child("Players").child(player_name).set(player_data) 

    print("Done updating data")
    
    
def upload_team_data():
    data = pd.read_csv("data/test_stats.csv")#.sort_values(by=["Latest Team"])
    cols = ['Name', 'Team(s)', 'Latest Team', 'Latest Team Rating']
    data = data[cols]
    team_data = {}
    
    for i in range(data.shape[0]):
        player_data = data.iloc[i].to_dict()
        latest_team: str = player_data["Latest Team"]
        all_teams: list = ast.literal_eval(player_data["Team(s)"])
        if latest_team not in team_data: team_data[latest_team] = {"current_players": [], 
                                                    "previous_players": [], "Name": latest_team,
                                                    "Rating": round(player_data["Latest Team Rating"])}
        
        team_data[latest_team]["current_players"].append(player_data["Name"])
        if "Rating" not in team_data[latest_team]: team_data[latest_team]["Rating"] = round(player_data["Latest Team Rating"])
        for team in all_teams:
            if team != latest_team:
                if team not in team_data: team_data[team] = {"current_players": [], "Name" : team,
                                                            "previous_players": []}
                team_data[team]["previous_players"].append(player_data["Name"])
             
    print("Adding Team data")
    for team in team_data:   
        print("Team:", team)
        database.child("Teams").child(team).set(team_data[team]) 


def clean_data():
    data = pd.read_csv("data/player_stats.csv")
    print(data.columns)
    data = data.sort_values(by=["Season"])
    data = data[data.Season != "DNP"]
    data.to_csv("data/player_stats.csv", index=False)
    
    print(data["Season"].tolist())

if __name__ == "__main__":
    # upload_player_data()
    # upload_team_data()
    clean_data()