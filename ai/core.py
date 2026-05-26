"""
AI Core — centralised Gemini + OpenRouter clients.
All AI calls across the app go through here.
"""
from openai import OpenAI
from google import genai
from google.genai import types
from core.config import settings
import json
import re
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Clients ───────────────────────────────────────────────────────────────────
huggingface_client = None
if settings.huggingface_api_key:
    huggingface_client = OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=settings.huggingface_api_key,
    )

openrouter_client = None
if settings.openrouter_api_key:
    openrouter_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    )

# ── Models ────────────────────────────────────────────────────────────────────
HUGGINGFACE_MODEL = "openai/gpt-oss-120b:groq"
OPENROUTER_MODEL = "openai/gpt-oss-120b:free"


def _parse_json_response(raw: str) -> dict:
    """Extract and parse JSON from a model response, handling markdown fences."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: extract the first JSON object via regex
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise

def call_huggingface(prompt: str, system_prompt: str = "", max_tokens: int = 500) -> dict:
    """Call HuggingFace free models and return parsed JSON."""            
    if not huggingface_client:
        raise RuntimeError("HuggingFace API key not configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    completion = huggingface_client.chat.completions.create(
        model=HUGGINGFACE_MODEL,
        # max_tokens=max_tokens,
        temperature=0.5,
        messages=messages                    
    )
    return _parse_json_response(completion.choices[0].message.content)


def call_openrouter(prompt: str, system_prompt: str = "", max_tokens: int = 500) -> dict:
    """Call OpenRouter free models and return parsed JSON."""
    if not openrouter_client:
        raise RuntimeError("OpenRouter API key not configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = openrouter_client.chat.completions.create(
        model=OPENROUTER_MODEL,
        # max_tokens=max_tokens,
        temperature=0.5,
        messages=messages
    )
    return _parse_json_response(response.choices[0].message.content)

def call_azure_openai(prompt: str, system_prompt: str = "", max_tokens: int = 500) -> dict:
    """Call Azure OpenAI models and return parsed JSON."""
    if not settings.azure_foundry_api_key or not settings.azure_foundry_project_url:
        raise RuntimeError("Azure Foundry API key or project URL not configured")

    client = OpenAI(
        base_url=settings.azure_foundry_project_url,
        api_key=settings.azure_foundry_api_key,
    )

    messages = [] 
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=settings.azure_foundry_project_model_name,
        # max_tokens=max_tokens,
        temperature=0.5,
        messages=messages
    )
    return _parse_json_response(response.choices[0].message.content)

def call_ai(prompt: str, system_prompt: str = "", max_tokens: int = 500) -> dict:
    """
    Call AI with Azure OpenAI as primary, HuggingFace and OpenRouter as fallback.
    Returns parsed JSON dict.
    """
    # ── Primary: Azure OpenAI ───────────────────────────────────────────────────
    try:        
        result = call_azure_openai(prompt, system_prompt, max_tokens)
        logger.info("AI call succeeded via Azure OpenAI")
        return result
    except Exception as e:
        logger.warning("Azure OpenAI call failed (%s), falling back to HuggingFace/OpenRouter...", e)
    
    # ── Fallback: HuggingFace ───────────────────────────────────────────────────
    try:
        result = call_huggingface(prompt, system_prompt, max_tokens)
        logger.info("AI call succeeded via HuggingFace")
        return result
    except Exception as e:
        logger.warning("HuggingFace failed (%s), falling back to OpenRouter...", e)

    # ── Fallback: OpenRouter ────────────────────────────────
    try:
        result = call_openrouter(prompt, system_prompt, max_tokens)
        logger.info("AI call succeeded via OpenRouter")
        return result
    except Exception as e:
        logger.error("OpenRouter fallback also failed: %s", e)
        raise RuntimeError(f"All AI providers failed. Last error: {e}")