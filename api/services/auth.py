from datetime import datetime, timedelta
from typing import Optional
import hashlib
import hmac
import random
from pydantic import BaseModel, SecretStr
from db.client import get_db
from api.services.email_service import EmailService
from firebase.config import update_firebase_user_password

MAX_RESEND_ATTEMPTS = 3
RESEND_COOLDOWN_MINUTES = 10
CODE_EXPIRY_MINUTES = 15
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
RESET_PASSWORD_INVALID_MESSAGE = "Invalid or expired password reset code."

class User(BaseModel):
    id: Optional[int] = None
    fullname: str
    email: str
    firebase_uid: str
    is_verified: bool = False
    verification_code_hash: Optional[str] = None
    verification_expires: Optional[datetime] = None
    verification_attempts: int = 0
    reset_password_token: Optional[str] = None
    reset_password_expires: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

class SignUpPayload(BaseModel):
    fullname: str
    email: str
    firebase_uid: str

class ResendVerificationPayload(BaseModel):
    email: str

class ResendVerificationResponse(BaseModel):
    status: str
    message: str

class VerifyEmailPayload(BaseModel):
    email: str
    code: str

class VerifyEmailResponse(BaseModel):
    status: str
    message: str

class ForgotPasswordPayload(BaseModel):
    email: str    

class ForgotPasswordResponse(BaseModel):
    status: str
    message: str

class ResetPasswordPayload(BaseModel):
    email: str
    code: str
    password: SecretStr

class ResetPasswordResponse(BaseModel):
    status: str
    message: str

class AuthService:    
    @staticmethod
    def _parse_utc_datetime(value):
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return parsed
        except Exception:
            return None

    @staticmethod
    def _get_rate_limited_attempts(user: dict, now: datetime):
        attempts = user.get("verification_attempts") or 0
        updated_at_dt = AuthService._parse_utc_datetime(
            user.get("updated_at") or user.get("created_at")
        )

        if updated_at_dt is not None and (now - updated_at_dt) >= timedelta(minutes=RESEND_COOLDOWN_MINUTES):
            attempts = 0

        return attempts, updated_at_dt

    @staticmethod
    def _build_throttle_response(prefix: str, updated_at_dt: Optional[datetime], now: datetime):
        if updated_at_dt is not None:
            retry_after = timedelta(minutes=RESEND_COOLDOWN_MINUTES) - (now - updated_at_dt)
            retry_after_seconds = max(int(retry_after.total_seconds()), 0)
            retry_after_minutes = max((retry_after_seconds + 59) // 60, 1)
            return {
                "status": "warning",
                "message": f"{prefix} Try again in {retry_after_minutes} minute(s)."
            }

        return {"status": "warning", "message": f"{prefix} Try again later."}

    @staticmethod
    def _validate_password_strength(password: str):
        if len(password) < PASSWORD_MIN_LENGTH:
            return f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
        if len(password) > PASSWORD_MAX_LENGTH:
            return f"Password must be at most {PASSWORD_MAX_LENGTH} characters long."
        if any(character.isspace() for character in password):
            return "Password must not contain spaces."
        if not any(character.islower() for character in password):
            return "Password must include at least one lowercase letter."
        if not any(character.isupper() for character in password):
            return "Password must include at least one uppercase letter."
        if not any(character.isdigit() for character in password):
            return "Password must include at least one number."
        if not any(not character.isalnum() for character in password):
            return "Password must include at least one special character."

        return None

    @staticmethod
    async def save_email_user(payload: SignUpPayload):
        db = get_db()

        # Generate a 6-digit verification code.
        verification_code = f"{random.randint(0, 999999):06d}"
        verification_code_hash = hashlib.sha256(verification_code.encode("utf-8")).hexdigest()
        verification_expires = datetime.utcnow() + timedelta(minutes=15)

        user_payload = {
            "fullname": payload.fullname,
            "email": payload.email,
            "firebase_uid": payload.firebase_uid,
            "account_type": "Email",
            "is_verified": False,
            "verification_code_hash": verification_code_hash,
            "verification_expires": verification_expires.isoformat(),
            "verification_attempts": 0,
        }

        try:
            result = (
                db.table("users")
                .insert(user_payload)
                .execute()
            )

            if not result.data or len(result.data) == 0:
                raise Exception("User insert failed.")

            inserted_user = result.data[0]

            # Send verification email after successful DB insert.
            EmailService.send_verification_email(
                to_email=payload.email,
                name=payload.fullname,
                code=verification_code,
                expiry_minutes=15,
            )
            
            return inserted_user
        except Exception as e:
            raise Exception(f"Error creating user and sending verification email: {str(e)}")
    
    @staticmethod
    async def save_social_auth_user(payload: SignUpPayload):
        db = get_db()

        user_payload = {
            "fullname": payload.fullname,
            "email": payload.email,
            "account_type": "Gmail",
            "firebase_uid": payload.firebase_uid,
            "is_verified": True,
            "updated_at": datetime.utcnow().isoformat(),           
        }

        try:            
            existing = db.table("users").select("*").eq("firebase_uid", user_payload["firebase_uid"]).execute()

            if existing.data:
                # Update user                
                result = (
                    db.table("users").update(user_payload).eq("firebase_uid", user_payload["firebase_uid"]).execute()
                )

                if not result.data or len(result.data) == 0:
                    raise Exception("Failed to update user")
                
                return result.data[0]            
            else:
                # save new user
                result = (
                    db.table("users")
                    .insert(user_payload)
                    .execute()
                )

                if not result.data or len(result.data) == 0:
                    raise Exception("User insert failed.")
                
                return result.data[0]
        except Exception as e:
            raise Exception(f"Error saving/fetching user: {str(e)}")

    @staticmethod    
    async def fetch_user(email: str):
        db = get_db()
        
        try:
            user_result = (
                db.table("users")
                .select("*")
                .eq("email", email)
                .limit(1)
                .execute()
            )

            if not user_result.data or len(user_result.data) == 0:
                raise Exception("User not found.")                

            user = user_result.data[0]

            if user.get("is_verified") is not True:                
                return {"status": "error", "message": "You need to verify your email first!"}
            
            return user
        except Exception as e:            
            raise Exception(f"Error fetching user data: {str(e)}")

    @staticmethod
    async def resend_verification_code(payload: ResendVerificationPayload):
        db = get_db()
        
        try:
            user_result = (
                db.table("users")
                .select("*")
                .eq("email", payload.email)
                .limit(1)
                .execute()
            )

            if not user_result.data or len(user_result.data) == 0:
                raise Exception("User not found.")                

            user = user_result.data[0]

            if user.get("is_verified"):                
                return {"status": "info", "message": "Email is already verified."}

            now = datetime.utcnow()

            attempts, updated_at_dt = AuthService._get_rate_limited_attempts(user, now)

            # Enforce attempt limit
            if attempts >= MAX_RESEND_ATTEMPTS:
                return AuthService._build_throttle_response(
                    prefix="Too many resend attempts.",
                    updated_at_dt=updated_at_dt,
                    now=now,
                )

            verification_code = f"{random.randint(0, 999999):06d}"
            verification_code_hash = hashlib.sha256(
                verification_code.encode("utf-8")
            ).hexdigest()
            verification_expires = now + timedelta(minutes=CODE_EXPIRY_MINUTES)
                        
            update_result = (
                db.table("users")
                .update(
                    {
                        "verification_code_hash": verification_code_hash,
                        "verification_expires": verification_expires.isoformat(),
                        "verification_attempts": attempts + 1,
                        "updated_at": now.isoformat(),
                    }
                )
                .eq("id", user["id"])                
                .execute()
            )
            
            if not update_result.data or len(update_result.data) == 0:
                raise Exception("Failed to update verification code.")                

            EmailService.send_verification_email(
                to_email=user["email"],
                name=user.get("fullname"),
                code=verification_code,
                expiry_minutes=CODE_EXPIRY_MINUTES,
            )

            return {"status": "success", "message": "Verification code resent successfully."}

        except Exception as e:            
            raise Exception(f"Error resending verification code: {str(e)}")


    @staticmethod
    async def verify_email(payload: VerifyEmailPayload):
        db = get_db()

        try:
            if not payload.email:
                return {"status": "error", "message": "Email is required."}
            if not payload.code:
                return {"status": "error", "message": "Verification code is required."}

            code = payload.code.strip()
            if not code.isdigit() or len(code) != 6:
                return {"status": "error", "message": "Invalid verification code format."}

            user_result = (
                db.table("users")
                .select("*")
                .eq("email", payload.email)
                .limit(1)
                .execute()
            )

            if not user_result.data or len(user_result.data) == 0:
                return {"status": "error", "message": "User not found."}

            user = user_result.data[0]

            if user.get("is_verified"):
                return {"status": "info", "message": "Email is already verified."}

            now = datetime.utcnow()

            attempts, updated_at_dt = AuthService._get_rate_limited_attempts(user, now)

            # Block verification if attempt limit reached in active window
            if attempts >= MAX_RESEND_ATTEMPTS:
                return AuthService._build_throttle_response(
                    prefix="Too many attempts.",
                    updated_at_dt=updated_at_dt,
                    now=now,
                )

            stored_hash = user.get("verification_code_hash")
            expires_raw = user.get("verification_expires")

            if not stored_hash or not expires_raw:
                return {
                    "status": "error",
                    "message": "No active verification code. Request a new code."
                }

            expires_dt = AuthService._parse_utc_datetime(expires_raw)
            if expires_dt is None:
                return {
                    "status": "error",
                    "message": f"Invalid verification expiry. Request a new code (valid for {CODE_EXPIRY_MINUTES} minutes)."
                }

            if now > expires_dt:
                return {
                    "status": "warning",
                    "message": f"Verification code has expired. Request a new code (valid for {CODE_EXPIRY_MINUTES} minutes)."
                }

            incoming_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
            if incoming_hash != stored_hash:
                db.table("users").update(
                    {
                        "verification_attempts": attempts + 1,
                        "updated_at": now.isoformat(),
                    }
                ).eq("id", user["id"]).execute()

                return {"status": "error", "message": "Invalid verification code."}

            db.table("users").update(
                {
                    "is_verified": True,
                    "verification_code_hash": None,
                    "verification_expires": None,
                    "verification_attempts": 0,
                    "updated_at": now.isoformat(),
                }
            ).eq("id", user["id"]).execute()

            return {"status": "success", "message": "Email verified successfully."}

        except Exception as e:
            raise Exception(f"Error verifying email: {str(e)}")

    @staticmethod
    async def forgot_password(payload: ForgotPasswordPayload):
        db = get_db()

        try:
            if not payload.email:
                return {"status": "error", "message": "Email is required."}

            user_result = (
                db.table("users")
                .select("*")
                .eq("email", payload.email)
                .limit(1)
                .execute()
            )

            # Keep response generic to avoid account enumeration.
            if not user_result.data or len(user_result.data) == 0:
                return {
                    "status": "success",
                    "message": "If an account exists for that email, a reset code has been sent."
                }

            user = user_result.data[0]
            now = datetime.utcnow()

            attempts, updated_at_dt = AuthService._get_rate_limited_attempts(user, now)

            # Enforce resend limit.
            if attempts >= MAX_RESEND_ATTEMPTS:
                return AuthService._build_throttle_response(
                    prefix="Too many forgot-password attempts.",
                    updated_at_dt=updated_at_dt,
                    now=now,
                )

            reset_code = f"{random.randint(0, 999999):06d}"
            reset_code_hash = hashlib.sha256(reset_code.encode("utf-8")).hexdigest()
            reset_password_expires = now + timedelta(minutes=CODE_EXPIRY_MINUTES)

            update_result = (
                db.table("users")
                .update(
                    {
                        "reset_password_token": reset_code_hash,
                        "reset_password_expires": reset_password_expires.isoformat(),
                        "verification_attempts": attempts + 1,
                        "updated_at": now.isoformat(),
                    }
                )
                .eq("id", user["id"])
                .execute()
            )

            if not update_result.data or len(update_result.data) == 0:
                raise Exception("Failed to store reset password code.")

            EmailService.send_forgot_password_email(
                to_email=user["email"],
                name=user.get("fullname") or "there",
                code=reset_code,
                expiry_minutes=CODE_EXPIRY_MINUTES,
            )

            return {
                "status": "success",
                "message": "If an account exists for that email, a reset code has been sent."
            }

        except Exception as e:
            raise Exception(f"Error sending forgot password code: {str(e)}")

    @staticmethod
    async def reset_password(payload: ResetPasswordPayload):
        db = get_db()

        try:
            if not payload.email:
                return {"status": "error", "message": "Email is required."}
            if not payload.code:
                return {"status": "error", "message": "Reset code is required."}

            code = payload.code.strip()
            if not code.isdigit() or len(code) != 6:
                return {"status": "error", "message": "Invalid reset code format."}

            new_password = payload.password.get_secret_value() if payload.password else ""
            if not new_password:
                return {"status": "error", "message": "New password is required."}

            password_error = AuthService._validate_password_strength(new_password)
            if password_error:
                return {"status": "error", "message": password_error}

            user_result = (
                db.table("users")
                .select("*")
                .eq("email", payload.email)
                .limit(1)
                .execute()
            )

            if not user_result.data or len(user_result.data) == 0:
                return {"status": "error", "message": RESET_PASSWORD_INVALID_MESSAGE}

            user = user_result.data[0]
            now = datetime.utcnow()
            attempts, updated_at_dt = AuthService._get_rate_limited_attempts(user, now)

            if attempts >= MAX_RESEND_ATTEMPTS:
                return AuthService._build_throttle_response(
                    prefix="Too many password reset attempts.",
                    updated_at_dt=updated_at_dt,
                    now=now,
                )

            stored_hash = user.get("reset_password_token")
            expires_dt = AuthService._parse_utc_datetime(user.get("reset_password_expires"))
            firebase_uid = user.get("firebase_uid")

            if not stored_hash or expires_dt is None or now > expires_dt:
                return {"status": "error", "message": RESET_PASSWORD_INVALID_MESSAGE}

            if not firebase_uid:
                raise Exception("User account is missing a Firebase UID.")

            incoming_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(incoming_hash, stored_hash):
                db.table("users").update(
                    {
                        "verification_attempts": attempts + 1,
                        "updated_at": now.isoformat(),
                    }
                ).eq("id", user["id"]).execute()

                return {"status": "error", "message": RESET_PASSWORD_INVALID_MESSAGE}

            update_firebase_user_password(firebase_uid, new_password)

            update_result = (
                db.table("users")
                .update(
                    {
                        "reset_password_token": None,
                        "reset_password_expires": None,
                        "verification_attempts": 0,
                        "updated_at": now.isoformat(),
                    }
                )
                .eq("id", user["id"])
                .execute()
            )

            if not update_result.data or len(update_result.data) == 0:
                raise Exception("Password was updated in Firebase but cleanup failed in the database.")

            EmailService.send_password_reset_success_email(
                to_email=user["email"],
                name=user.get("fullname") or "there",
            )

            return {"status": "success", "message": "Password reset successful."}

        except Exception as e:
            raise Exception(f"Error resetting password: {str(e)}")