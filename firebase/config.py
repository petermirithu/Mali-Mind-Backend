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
        if settings.app_env == "prod":
            # Production: Load from environment variable
            firebase_json_str = os.environ.get("firebase_service_account_json")
            if not firebase_json_str:
                _firebase_error = "Firebase service account JSON not found in environment variable 'firebase_service_account_json'"
                raise Exception(_firebase_error)                                
            try:
                firebase_json_dict = json.loads(firebase_json_str)
            except json.JSONDecodeError as e:
                _firebase_error = f"Invalid JSON in 'firebase_service_account_json' environment variable: {e}"
                raise Exception(_firebase_error)
                
            cred = credentials.Certificate(firebase_json_dict)
        else:
            # Development: Load from local file
            if not SERVICE_ACCOUNT_PATH.exists():
                _firebase_error = f"Firebase service account file not found at: {SERVICE_ACCOUNT_PATH}"
                raise Exception(_firebase_error)
                
            cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
        
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True        
    except Exception as e:
        _firebase_error = f"Failed to initialize Firebase: {str(e)}"
        raise Exception(_firebase_error)


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


# Initialize Firebase on module load (don't crash if it fails)
_initialize_firebase()