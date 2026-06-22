from datetime import datetime
from pydantic import BaseModel
from db.client import get_db
class UpdateProfilePayload(BaseModel):
    fullname: str    
    id: int

class ProfileService:
    @staticmethod
    async def update_profile(payload: UpdateProfilePayload):
        db = get_db()

        try:
            result = (
                db.table("users")
                .update(
                    {
                        "fullname": payload.fullname,                        
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", payload.id)
                .execute()
            )

            if not result.data or len(result.data) == 0:
                raise Exception("Failed to update user")

            return result.data[0]
        except Exception as e:
            raise Exception(f"Error updating user: {str(e)}")