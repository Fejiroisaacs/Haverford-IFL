

class UserNameAlreadyExists(Exception):
    
    def __init__(self, message="Username already exists."):
        self.message = message
        super().__init__(self.message)
        
class InvalidUserName(Exception):
    
    def __init__(self, message="Invalid Username."):
        self.message = message
        super().__init__(self.message)
    