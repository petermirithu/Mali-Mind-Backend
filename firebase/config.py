import json
import os
from pathlib import Path

from core.config import settings
import firebase_admin
from firebase_admin import credentials, auth

# Build absolute path from this file's directory
SERVICE_ACCOUNT_PATH = Path(__file__).resolve().parent / "firebase-service-account.json"

if not firebase_admin._apps:
    if settings.firebase_service_account_json:
        cred = credentials.Certificate(json.loads(settings.firebase_service_account_json))
    elif os.getenv("VERCEL") == "1":
        raise RuntimeError("Set FIREBASE_SERVICE_ACCOUNT_JSON in Vercel environment variables")
    elif SERVICE_ACCOUNT_PATH.exists():
        cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
    else:
        raise FileNotFoundError(
            "Set FIREBASE_SERVICE_ACCOUNT_JSON or provide a local Firebase service account file"
        )
    firebase_admin.initialize_app(cred)


def verify_firebase_token(token: str):
    """Verifies the JWT token from the frontend and returns user data."""
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception:
        return None


def update_firebase_user_password(uid: str, new_password: str):
    """Updates a Firebase user's password and revokes existing refresh tokens."""
    updated_user = auth.update_user(uid, password=new_password)
    auth.revoke_refresh_tokens(uid)
    return updated_user