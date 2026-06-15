from db.client import get_db

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