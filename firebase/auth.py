from fastapi import Header, HTTPException, status
from firebase.config import verify_firebase_token

async def is_authenticated(authorization: str = Header(None)):
    """
    Middleware dependency that extracts the Authorization header,
    validates the Firebase token, and blocks unauthorized users.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Header"
        )
    
    # Expecting header format: "Bearer <YOUR_FIREBASE_TOKEN>"
    try:
        token_type, token = authorization.split(" ")
        if token_type.lower() != "bearer":
            raise ValueError()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Use 'Bearer <token>'"
        )

    # Verify the token via Firebase Admin SDK
    user_data = verify_firebase_token(token)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired Firebase token"
        )

    # Return the user's decoded information (contains uid, email, etc.)
    return user_data
