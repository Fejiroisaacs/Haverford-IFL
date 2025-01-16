from dataclasses import dataclass, field
import firebase_admin.db

@dataclass
class User:
    username: str
    email: str
    verified: bool
    db: firebase_admin.db
    admin: bool = field(init=False) 
    user_data: dict = field(init=False) 
    
    def __post_init__(self): 
        self.admin, self.user_data = self.get_admin_status(self.username)
    
    def get_admin_status(self, username):
        users_ref = self.db.reference('Users').child(username)
        user_data = users_ref.get()
        
        if 'Admin' in user_data: return user_data['Admin'], user_data  
        else: return None, user_data
    
    def update_users(self):
        if not self.admin: return None
        all_users = self.db.reference('Users').get()
    
    def __repr__(self):
        return (f'''This is a {self.__class__.__name__} called {self.username}.''')
    