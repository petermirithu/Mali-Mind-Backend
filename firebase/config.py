from pathlib import Path
import firebase_admin
from firebase_admin import credentials, auth

# Build absolute path from this file's directory
SERVICE_ACCOUNT_PATH = Path(__file__).resolve().parent / "firebase-service-account.json"

if not SERVICE_ACCOUNT_PATH.exists():
    raise FileNotFoundError(
        f"Firebase service account file not found at: {SERVICE_ACCOUNT_PATH}"
    )

if not firebase_admin._apps:
    cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
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