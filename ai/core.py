"""
AI Core — centralised Gemini + OpenRouter clients.
All AI calls across the app go through here.
"""
from openai import OpenAI
from google import genai
from google.genai import types
from core.config import settings
import json
import logging

logger = logging.getLogger(__name__)

# ── Clients ───────────────────────────────────────────────────────────────────
gemini_client = genai.Client(api_key=settings.gemini_api_key)

openrouter_client = None
if settings.openrouter_api_key:
    openrouter_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    )

# ── Models ────────────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"
OPENROUTER_MODEL = "deepseek/deepseek-r1:free"


def _parse_json_response(raw: str) -> dict:
    """Extract and parse JSON from a model response, handling markdown fences."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(lines)
    return json.loads(text)


def call_gemini(prompt: str, system_prompt: str = "", max_tokens: int = 500) -> dict:
    """Call Gemini 2.5 Flash and return parsed JSON."""
    config = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        temperature=0.3,
    )
    if system_prompt:
        config.system_instruction = system_prompt

    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return _parse_json_response(response.text)


def call_openrouter(prompt: str, system_prompt: str = "", max_tokens: int = 500) -> dict:
    """Call DeepSeek-R1 via OpenRouter and return parsed JSON."""
    if not openrouter_client:
        raise RuntimeError("OpenRouter API key not configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = openrouter_client.chat.completions.create(
        model=OPENROUTER_MODEL,
        max_tokens=max_tokens,
        temperature=0.3,
        messages=messages,
        # extra_headers={
            # "HTTP-Referer": "https://malimind.onrender.com",
            # "X-Title": "MaliMind",
        # },
    )
    return _parse_json_response(response.choices[0].message.content)


def call_ai(prompt: str, system_prompt: str = "", max_tokens: int = 500) -> dict:
    """
    Call AI with Gemini as primary and OpenRouter as fallback.
    Returns parsed JSON dict.
    """
    # ── Primary: Gemini ───────────────────────────────────────────────────
    try:
        result = call_gemini(prompt, system_prompt, max_tokens)
        logger.info("AI call succeeded via Gemini 2.5 Flash")
        return result
    except Exception as e:
        logger.warning("Gemini failed (%s), falling back to OpenRouter...", e)

    # ── Fallback: OpenRouter (DeepSeek-R1) ────────────────────────────────
    try:
        result = call_openrouter(prompt, system_prompt, max_tokens)
        logger.info("AI call succeeded via OpenRouter (DeepSeek-R1)")
        return result
    except Exception as e:
        logger.error("OpenRouter fallback also failed: %s", e)
        raise RuntimeError(f"All AI providers failed. Last error: {e}")