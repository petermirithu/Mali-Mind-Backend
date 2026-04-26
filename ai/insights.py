"""
AI Insight Engine — turns raw economic data into household impact summaries.
Primary: Google Gemini 2.5 Flash (free tier).
Fallback: DeepSeek-R1 via OpenRouter (free tier).
"""
from datetime import datetime
from core.config import settings
from db.client import get_db
import logging
import json
from ai.core import call_ai

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are MaliMind, a Kenyan financial intelligence assistant.
Your job is to explain economic changes in simple, clear Swahili-English (Sheng optional) 
that everyday Kenyans can understand.

Always focus on:
- Real household impact (food, transport, bills)
- Practical, actionable meaning
- Avoid jargon

Respond ONLY with valid JSON matching the exact schema requested."""


def _build_prompt(trigger: str, data: dict) -> str:
    """Build the user prompt for insight generation."""
    return f"""
        Economic update in Kenya:
        Trigger: {trigger}
        Data: {json.dumps(data, indent=2)}

        Generate a household impact insight. It MUST be a valid JSON with NO syntax errors. Respond with this exact JSON:
        {{
        "summary": "1-2 sentences in plain English, easy to understand explanation of impact on a Kenyan household",
        "impact_score": <float from -1.0 (very bad) to 1.0 (very good)>,
        "affected_areas": ["transport", "food", "electricity", "imports"]  // pick relevant ones
        }}
    """

async def generate_insight(trigger: str, data: dict) -> dict:
    """
    Generate an AI insight from economic data.
    Uses Gemini (primary) with OpenRouter fallback via ai.core.
    
    trigger: e.g. "fuel_update", "forex_update", "food_update"
    data: dict with latest prices/changes
    """
    prompt = _build_prompt(trigger, data)
    parsed = call_ai(prompt, system_prompt=SYSTEM_PROMPT)
    
    insight = {
        "trigger": trigger,
        "summary": parsed["summary"],
        "impact_score": float(parsed["impact_score"]),
        "affected_areas": parsed["affected_areas"]        
    }
    return insight

async def store_insight(insight: dict) -> None:
    db = get_db()
    insight_to_store = {**insight, "affected_areas": json.dumps(insight["affected_areas"])}
    db.table("ai_insights").insert(insight_to_store).execute()
    logger.info("Insight stored: %s", insight["summary"][:60])


async def run_insight_pipeline(trigger: str, data: dict) -> dict:
    insight = await generate_insight(trigger, data)
    await store_insight(insight)
    return insight