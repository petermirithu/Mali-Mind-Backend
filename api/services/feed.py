from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from db.client import get_db

class FeedItem(BaseModel):
    id: Optional[int] = None
    title: str
    category: str
    what_happened: str
    why_it_happened: str
    what_it_means: str
    source_url: Optional[str] = None
    published_at: datetime
    created_at: Optional[datetime] = None
    
class FeedService:
    @staticmethod
    async def fetch_feeds():
        db = get_db()
        try:
            feed_items = (
                db.table("feed_items")
                .select("*")
                .order("published_at", desc=True)
                .execute()
                .data
            )
            return feed_items or []
        except Exception as e:
            raise Exception(f"Error fetching feed data: {str(e)}")