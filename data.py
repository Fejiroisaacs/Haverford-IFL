import requests, pyrebase, json, pandas as pd


firebase = pyrebase.initialize_app(json.load(open("cred.json")))
fb_storage = firebase.storage()
database = firebase.database()

def upload_player_data():
    data = pd.read_csv("data/test_stats.csv")
    print(data["OVR Rating"])
    data["OVR Rating"] = data["OVR Rating"].apply(lambda x: int(x) if "Not Enough Data" not in x else -1)
    data["ATT Rating"] = data["ATT Rating"].apply(lambda x: float(x) if "Not Enough Data" not in x else -1)
    data["GLK Rating"] = data["GLK Rating"].apply(lambda x: float(x) if "Not Enough Data" not in x else -1)
    data["AST Rating"] = data["AST Rating"].apply(lambda x: float(x) if "Not Enough Data" not in x else -1)
    data["DEF Rating"] = data["DEF Rating"].apply(lambda x: float(x) if "Not Enough Data" not in x else -1)
    print(data["OVR Rating"])

    
    for i in range(data.shape[0]):
        player_data = data.iloc[i].to_dict()
        player_name = player_data["Name"]#.split(" ")
        name = player_name.split(" ")
        player_data["First Name"] = name[0]
        player_data["Last Name"] = name[-1] if len(name) > 1 else ""
        database.child("Players").child(player_name).set(player_data) 

    print("Done updating data")
    
# upload_player_data()