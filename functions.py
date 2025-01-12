
import yagmail, os, tempfile, json, ast
from dotenv import load_dotenv

load_dotenv()

oauth2_credentials = ast.literal_eval(os.getenv("oauth2"))
with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.json') as temp_file:
    json.dump(oauth2_credentials, temp_file)
    temp_filename = temp_file.name
    
mail_sender = yagmail.SMTP(
    user=f'{os.getenv("OUR_EMAIL")}',
    password=f'{os.getenv("OUR_EMAIL_PASSWORD")}',
    oauth2_file=temp_filename,
)

def send_email(email, bccs, subject, message, attachment=None):
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
