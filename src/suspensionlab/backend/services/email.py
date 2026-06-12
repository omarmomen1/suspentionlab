import logging
import httpx
from pydantic import EmailStr
from suspensionlab.backend.config import settings

logger = logging.getLogger(__name__)

async def send_welcome_email(email: EmailStr, user_id: str):
    """
    Sends a welcome email to newly registered PRO users via SendGrid API.
    """
    if not settings.sendgrid_api_key or settings.environment == "TEST":
        logger.info(f"Mocking welcome email to {email} (user: {user_id})")
        return True

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {settings.sendgrid_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "personalizations": [{"to": [{"email": email}]}],
        "from": {"email": "welcome@suspensionlab.pro", "name": "SuspensionLab PRO"},
        "subject": "Welcome to SuspensionLab PRO",
        "content": [{"type": "text/plain", "value": "Your high-performance physics environment is ready."}]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Welcome email successfully sent to {email}")
            return True
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {str(e)}")
        # We don't raise here to prevent blocking the user flow on an email error
        return False

async def send_password_reset_email(email: EmailStr, reset_token: str):
    """
    Sends a password reset email via SendGrid API.
    """
    if not settings.sendgrid_api_key or settings.environment == "TEST":
        logger.info(f"Mocking password reset email to {email}")
        return True

    reset_link = f"{settings.app_base_url}/auth/reset?token={reset_token}"
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {settings.sendgrid_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "personalizations": [{"to": [{"email": email}]}],
        "from": {"email": "support@suspensionlab.pro", "name": "SuspensionLab PRO Support"},
        "subject": "Password Reset Request",
        "content": [{"type": "text/plain", "value": f"Click here to reset your password: {reset_link}"}]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Password reset email successfully sent to {email}")
            return True
    except Exception as e:
        logger.error(f"Failed to send reset email to {email}: {str(e)}")
        return False
