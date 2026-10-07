import json
import os
from pathlib import Path

from core.config import settings
import firebase_admin
from firebase_admin import credentials, auth

# Build absolute path from this file's directory
SERVICE_ACCOUNT_PATH = Path(__file__).resolve().parent / "firebase-service-account.json"
_firebase_initialized = False
_firebase_error = None

def _initialize_firebase():
    """Initialize Firebase based on environment configuration."""
    global _firebase_initialized, _firebase_error
    
    if firebase_admin._apps:
        _firebase_initialized = True
        return  # Already initialized
    
    try:
        firebase_json_str = settings.firebase_service_account_json
        if firebase_json_str and firebase_json_str.strip():
            try:
                firebase_json_dict = json.loads(firebase_json_str)
                if not isinstance(firebase_json_dict, dict):
                    raise ValueError("Expected a JSON object")
                cred = credentials.Certificate(firebase_json_dict)
            except (ValueError, TypeError):
                raise RuntimeError(
                    "FIREBASE_SERVICE_ACCOUNT_JSON must contain a valid service-account JSON object"
                ) from None
        elif os.getenv("VERCEL") == "1" or settings.app_env.lower() in {"prod", "production"}:
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is required in production")
        else:
            if not SERVICE_ACCOUNT_PATH.exists():
                raise RuntimeError(
                    "Set FIREBASE_SERVICE_ACCOUNT_JSON or provide the local Firebase service-account file"
                )
            cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))

        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        _firebase_error = None
    except Exception as e:
        _firebase_error = f"Failed to initialize Firebase: {str(e)}"
        raise RuntimeError(_firebase_error) from None


def _ensure_firebase():
    """Ensure Firebase is initialized, raise error if initialization failed."""
    if not _firebase_initialized and _firebase_error:
        raise RuntimeError(f"Firebase is not available: {_firebase_error}")
    if not firebase_admin._apps:
        raise RuntimeError("Firebase has not been initialized")
    
def verify_firebase_token(token: str):
    """Verifies the JWT token from the frontend and returns user data."""
    _ensure_firebase()
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception:
        return None


def update_firebase_user_password(uid: str, new_password: str):
    """Updates a Firebase user's password and revokes existing refresh tokens."""
    _ensure_firebase()
    updated_user = auth.update_user(uid, password=new_password)
    auth.revoke_refresh_tokens(uid)
    return updated_user


# Fail fast on invalid credentials instead of deploying a broken authentication API.
_initialize_firebase()