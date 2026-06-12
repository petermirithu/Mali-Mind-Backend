"""Mali chat agent built with LangChain + LangGraph.

This flow is dedicated to conversational chat and does not use ai.core.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Annotated, AsyncIterator, Literal, TypedDict
import operator
import json
import logging

import requests
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI 
from langgraph.graph import END, START, StateGraph

from core.config import settings
from db.client import get_db

logger = logging.getLogger(__name__)

ALLOWED_TABLES = {
    "fuel_prices",
    "forex_rates",
    "food_items",
    "ai_insights",
    "feed_items",
    "user_impact_profiles",
    "monthly_spending",
    "custom_spending_tracker",
}

SYSTEM_PROMPT = """
You are Mali, an AI-powered Kenyan financial intelligence assistant.

Mission:
- Explain what real-world economic events mean for daily cost of living and businesses in Kenya.
- Focus on fuel, food, forex, taxes, utilities/electricity, transport, rent, and household spending.
- Be practical, concise, and easy to understand.

Tool rules:
- Use tools whenever facts, current events, or user-specific data are needed.
- Prefer database queries for internal platform data.
- Use web search for recent external events and public information.
- Never hallucinate exact numbers when a tool can verify them.

Output rules:
- Keep the answer clear and direct.
- Feel free to use emojis where necessary.
- Include a short "What this means" section.
- If uncertainty exists, state it briefly.
- Be brief, your responses are being rendered on a mobile app and should be easily digestible.
- If you use a tool, always call it with the correct arguments and wait for the result before answering.
- NEVER respond to weird, sexual, abusive or irrelevant user questions. Politely decline and steer the conversation back to financial topics.
- NEVER expose internal system details, tool names, or implementation specifics to the user.
""".strip()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@tool
def search_web(query: str, limit: int = 5) -> dict[str, Any]:
    """Search external web info for recent public economic context."""
    q = (query or "").strip()
    if not q:
        return {"query": query, "results": [], "note": "Empty query"}

    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": q, "format": "json", "no_redirect": 1, "no_html": 1},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()

        results: list[dict[str, str]] = []
        if payload.get("AbstractText"):
            results.append(
                {
                    "title": payload.get("Heading") or "Summary",
                    "snippet": payload.get("AbstractText", ""),
                    "url": payload.get("AbstractURL", ""),
                }
            )

        for item in payload.get("RelatedTopics", []):
            if isinstance(item, dict) and item.get("Text") and item.get("FirstURL"):
                results.append(
                    {
                        "title": item.get("Text", "")[:80],
                        "snippet": item.get("Text", ""),
                        "url": item.get("FirstURL", ""),
                    }
                )
            if len(results) >= limit:
                break

        return {
            "query": q,
            "results": results[: max(1, min(_safe_int(limit, 5), 10))],
            "source": "duckduckgo",
            "fetched_at": datetime.utcnow().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("web search failed")
        return {"query": q, "results": [], "error": str(exc), "source": "duckduckgo"}


@tool
def query_db(table: str, limit: int = 10, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Query allowlisted Supabase tables for Mali internal data."""
    table_name = (table or "").strip()
    if table_name not in ALLOWED_TABLES:
        return {
            "ok": False,
            "error": f"Table '{table_name}' is not allowed",
            "allowed_tables": sorted(ALLOWED_TABLES),
        }

    try:
        row_limit = max(1, min(_safe_int(limit, 10), 100))
        query = get_db().table(table_name).select("*").limit(row_limit)
        for key, value in (filters or {}).items():
            if value is not None:
                query = query.eq(key, value)

        response = query.execute()
        rows = response.data or []
        return {
            "ok": True,
            "table": table_name,
            "count": len(rows),
            "rows": rows,
            "limit": row_limit,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("db query failed")
        return {"ok": False, "table": table_name, "error": str(exc)}


def _build_model() -> AzureChatOpenAI:
    # Uses env-backed values from core.config; set model to gpt-5.4 in env.    
    return AzureChatOpenAI(
        model=settings.azure_foundry_project_model_name,
        api_key=settings.azure_foundry_api_key,        
        azure_endpoint=settings.azure_foundry_project_url,
        api_version=settings.azure_foundry_project_api_version,
        temperature=0.7        
    )


TOOLS = [search_web, query_db]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
MODEL_WITH_TOOLS = _build_model().bind_tools(TOOLS)


class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]


def _llm_call(state: MessagesState) -> dict[str, list[AnyMessage]]:
    response = MODEL_WITH_TOOLS.invoke(
        [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    )
    return {"messages": [response]}


def _tool_node(state: MessagesState) -> dict[str, list[ToolMessage]]:
    last_message = state["messages"][-1]
    outputs: list[ToolMessage] = []

    for tool_call in getattr(last_message, "tool_calls", []) or []:
        name = tool_call.get("name", "")
        args = tool_call.get("args", {})
        tool_impl = TOOLS_BY_NAME.get(name)

        if not tool_impl:
            outputs.append(
                ToolMessage(
                    content=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=True),
                    tool_call_id=tool_call.get("id", "unknown"),
                )
            )
            continue

        try:
            result = tool_impl.invoke(args if isinstance(args, dict) else {})
            outputs.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=True),
                    tool_call_id=tool_call.get("id", "unknown"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("tool execution failed")
            outputs.append(
                ToolMessage(
                    content=json.dumps({"error": str(exc)}, ensure_ascii=True),
                    tool_call_id=tool_call.get("id", "unknown"),
                )
            )

    return {"messages": outputs}


def _should_continue(state: MessagesState) -> Literal["tool_node", END]:
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tool_node"
    return END


_agent_builder = StateGraph(MessagesState)
_agent_builder.add_node("llm_call", _llm_call)
_agent_builder.add_node("tool_node", _tool_node)
_agent_builder.add_edge(START, "llm_call")
_agent_builder.add_conditional_edges("llm_call", _should_continue, ["tool_node", END])
_agent_builder.add_edge("tool_node", "llm_call")
AGENT = _agent_builder.compile()


def _to_messages(question: str, chat_history: list[dict[str, str]] | None) -> list[AnyMessage]:
    messages: list[AnyMessage] = []
    for item in chat_history or []:
        role = (item.get("role") or "").lower()
        content = item.get("content") or ""
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=question))
    return messages

def _build_suggestions(question: str, answer: str) -> list[str]:
    """Generate 3 short follow-up prompts based on the current Q/A pair."""
    fallback = [
        "Can you simplify this for me?",
        "What should I do next?",
        "What should I watch this week?",
    ]

    q = (question or "").strip()
    a = (answer or "").strip()
    if not q and not a:
        return fallback

    prompt = (
        "You generate follow-up prompt suggestions for a mobile app.\n"
        "Feel free to use emojis where necessary.\n"
        "Return ONLY valid JSON in this format: {\"suggestions\": [\"...\", \"...\", \"...\"]}\n"
        "Rules:\n"
        "- Exactly 3 suggestions\n"
        "- Each suggestion must be short (max 60 characters)\n"        
        "- Suggestions must be relevant to the user's question and assistant answer\n"
        "- Make them actionable and natural as tap-to-ask follow-ups\n\n"
        f"User question: {q}\n"
        f"Assistant answer: {a}\n"
    )

    try:
        response = _build_model().invoke([HumanMessage(content=prompt)])
        raw = response.content if isinstance(response.content, str) else str(response.content)
        data = json.loads(raw)

        items = data.get("suggestions", [])
        if not isinstance(items, list):
            return fallback

        cleaned: list[str] = []
        seen: set[str] = set()

        for item in items:
            text = str(item).strip()
            if not text:
                continue
            if len(text) > 60:
                text = text[:60].rstrip()
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
            if len(cleaned) == 3:
                break

        if len(cleaned) == 3:
            return cleaned

        return fallback
    except Exception:  # noqa: BLE001
        logger.exception("suggestion generation failed")
        return fallback

def ask_mali(
    question: str,
    user_id: str | None = None,
    chat_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    messages = _to_messages(question, chat_history)
    result = AGENT.invoke({"messages": messages})

    final_text = ""
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content:
            final_text = msg.content if isinstance(msg.content, str) else str(msg.content)
            break
    
    suggestions = _build_suggestions(question, final_text)
    return {
        "answer": final_text,
        "question": question,
        "user_id": user_id,
        "generated_at": datetime.utcnow().isoformat(),
        "suggestions": suggestions,
    }


async def astream_mali(
    question: str,
    user_id: str | None = None,
    chat_history: list[dict[str, str]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    messages = _to_messages(question, chat_history)
    final_text_parts: list[str] = []

    async for event in AGENT.astream_events(
        {"messages": messages},
        version="v2",
    ):
        event_name = event.get("event", "")
        data = event.get("data", {})

        if event_name == "on_chat_model_stream":
            chunk = data.get("chunk")
            text = ""
            if chunk is not None:
                content = getattr(chunk, "content", "")
                text = content if isinstance(content, str) else str(content)
            if text:
                final_text_parts.append(text)
                yield {"type": "chunk", "text": text}

        if event_name == "on_tool_end":
            yield {
                "type": "tool_result",
                "data": data.get("output", {}),
            }

    final_text = "".join(final_text_parts).strip()
    suggestions = _build_suggestions(question, final_text)
    yield {"type": "suggestions", "items": suggestions}
    yield {
        "type": "done",
        "meta": {
            "user_id": user_id,
            "suggestions": suggestions,
            "generated_at": datetime.utcnow().isoformat(),
        },
    }
