from fastapi import APIRouter, HTTPException
from api.services.auth import User
from fastapi import Depends
from api.services.profile import ProfileService, UpdateProfilePayload
from firebase.auth import is_authenticated

router = APIRouter(prefix="/profile", tags=["profile"], dependencies=[Depends(is_authenticated)])

@router.put("/update-profile", response_model=User)
async def update_profile(payload: UpdateProfilePayload):
    """
    Updates user in database.
    """
    try:
        user = await ProfileService.update_profile(payload)
        return user
    except Exception as e:             
        raise HTTPException(status_code=400, detail=str(e))