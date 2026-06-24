from fastapi import APIRouter, HTTPException
from api.services.auth import AuthService, ForgotPasswordPayload, ForgotPasswordResponse, ResendVerificationPayload, ResendVerificationResponse, ResetPasswordPayload, ResetPasswordResponse, User, SignUpPayload, VerifyEmailPayload, VerifyEmailResponse
from fastapi import Depends
from firebase.auth import is_authenticated

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(is_authenticated)])
public_router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/sign-up", response_model=User)
async def save_email_user(payload: SignUpPayload):
    """
    Saves user to database and sends email verification code.
    """
    try:
        user = await AuthService.save_email_user(payload)
        return user
    except Exception as e:        
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/social-auth", response_model=User)
async def save_social_auth_user(payload: SignUpPayload):
    """
    Saves and returns user who signed up with google to database.
    """
    try:
        user = await AuthService.save_social_auth_user(payload)
        return user
    except Exception as e:        
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/me/{email}", response_model=User)
async def fetch_user(email: str):
    """
    Fetches user from database
    """
    try:
        user = await AuthService.fetch_user(email)
        return user
    except Exception as e:        
        raise HTTPException(status_code=400, detail=str(e))
    
@router.post("/resend-verification", response_model=ResendVerificationResponse)
async def resend_verification_code(payload: ResendVerificationPayload):
    """
    Resends verification code and updates stored hash/expiry.
    """
    try:
        result = await AuthService.resend_verification_code(payload)
        return result
    except Exception as e:        
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(payload: VerifyEmailPayload):
    """
    Verifies user email using email + verification code.
    """
    try:
        result = await AuthService.verify_email(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))    

@public_router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(payload: ForgotPasswordPayload):    
    try:
        result = await AuthService.forgot_password(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))        

@public_router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(payload: ResetPasswordPayload):
    try:
        result = await AuthService.reset_password(payload)
        return result
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=str(e))
  