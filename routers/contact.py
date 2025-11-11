from fastapi import Request, Form, Depends
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, JSONResponse
from fastapi import APIRouter
from functions import send_email
from firebase_admin import db as firebase_db
from pydantic import BaseModel
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

templates = Jinja2Templates(directory="templates")
user = None

# Pydantic model for feedback data validation
class FeedbackData(BaseModel):
    type: str
    name: str = None
    email: str = None
    timestamp: str
    page: str
    feature: str = None
    rating: int = None
    feedback: str = None
    featureName: str = None
    description: str = None
    priority: str = None

@router.get("/contact", response_class=HTMLResponse)
async def read_contact(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request, "user": user})


@router.post("/send-message", response_class=HTMLResponse)
async def send_feedback(request: Request, email: str = Form(...), textarea: str = Form(...)):
    try:
        if not email or not textarea:
            return templates.TemplateResponse("contact.html", {"request": request,
                                                            "error": 'All fields are required.',
                                                            "success": None})

        emails = ['fanigboro@haverford.edu', 'gdevries@haverford.edu']
        if '@' in email:emails.append(email)

        send_email(email=f'{os.getenv("OUR_EMAIL")}', bccs=emails, subject=f'{email} left a message', message=textarea)

        return templates.TemplateResponse("contact.html", {"request": request,
                                                        "success": f"Thank you, {email}. We've received your message.",
                                                        "error": None})
    except:
        return templates.TemplateResponse("contact.html", {"request": request,
                                                        "success": None,
                                                        "error": 'Email not sent, something happened'})


@router.post("/api/feedback")
async def submit_feedback(feedback: FeedbackData, db: firebase_db.Reference = Depends(lambda: firebase_db.reference('/'))):
    """Handle feedback submissions - send email and store in Firebase"""
    try:
        # Prepare email content based on feedback type
        if feedback.type == 'rate':
            # Rating feedback
            email_subject = f"Feature Rating: {feedback.feature}"
            star_display = "⭐" * feedback.rating
            email_body = f"""
                    New Feature Rating Received

                    Feature: {feedback.feature}
                    Rating: {star_display} ({feedback.rating}/5)
                    Feedback: {feedback.feedback}

                    Page: {feedback.page}
                    User Name: {feedback.name if feedback.name else 'Not provided'}
                    User Email: {feedback.email if feedback.email else 'Not provided'}
                    Timestamp: {feedback.timestamp}
                    """
        else:
            # Feature request
            email_subject = f"Feature Request: {feedback.featureName}"
            email_body = f"""
                New Feature Request Received

                Feature Name: {feedback.featureName}
                Description: {feedback.description}
                Priority: {feedback.priority.upper()}

                Page: {feedback.page}
                User Name: {feedback.name if feedback.name else 'Not provided'}
                User Email: {feedback.email if feedback.email else 'Not provided'}
                Timestamp: {feedback.timestamp}
                """

        # Send email notification to administrators
        admin_emails = ['fanigboro@haverford.edu', 'gdevries@haverford.edu']
        if feedback.email and '@' in feedback.email:
            admin_emails.append(feedback.email)

        send_email(
            email=f'{os.getenv("OUR_EMAIL")}',
            bccs=admin_emails,
            subject=email_subject,
            message=email_body
        )

        # Store feedback in Firebase Realtime Database
        feedback_ref = db.child('feedback')

        # Create a unique ID for this feedback entry
        feedback_id = feedback_ref.push().key

        # Prepare data for Firebase
        firebase_data = {
            'id': feedback_id,
            'type': feedback.type,
            'timestamp': feedback.timestamp,
            'page': feedback.page,
            'name': feedback.name if feedback.name else 'anonymous',
            'email': feedback.email if feedback.email else 'anonymous',
            'created_at': datetime.now().isoformat()
        }

        # Add type-specific fields
        if feedback.type == 'rate':
            firebase_data['feature'] = feedback.feature
            firebase_data['rating'] = feedback.rating
            firebase_data['feedback'] = feedback.feedback
        else:
            firebase_data['featureName'] = feedback.featureName
            firebase_data['description'] = feedback.description
            firebase_data['priority'] = feedback.priority

        # Save to Firebase
        feedback_ref.child(feedback_id).set(firebase_data)

        return JSONResponse({
            "success": True,
            "message": "Feedback submitted successfully"
        })

    except Exception as e:
        print(f"Error submitting feedback: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Error submitting feedback: {str(e)}"
            }
        )
