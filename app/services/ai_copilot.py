import json
import httpx
from app.core.config import settings


import os
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = "llama3.2"


async def _ask(prompt: str, system: str) -> str:
    """Send a prompt to local Ollama and return the response."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(OLLAMA_URL, json={
            "model": MODEL,
            "system": system,
            "prompt": prompt,
            "stream": False,
        })
        resp.raise_for_status()
        return resp.json()["response"].strip()


def _format_thread(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        author = m.get("author", {}).get("username", "unknown")
        content = m.get("content", "")
        lines.append(f"{author}: {content}")
    return "\n".join(lines)


async def summarize(messages: list[dict]) -> str:
    transcript = _format_thread(messages)
    return await _ask(
        prompt=f"Summarize this chat thread in exactly 2 sentences:\n\n{transcript}",
        system="You summarize chat threads. Always respond in exactly 2 sentences. Be concise and factual. No preamble."
    )


async def suggest_replies(message_content: str, context: list[dict]) -> list[str]:
    context_text = _format_thread(context[-5:])
    raw = await _ask(
        prompt=(
            f"Recent context:\n{context_text}\n\n"
            f"Last message: {message_content}\n\n"
            "Write exactly 3 short reply options, one per line, no numbering, no quotes, each under 10 words."
        ),
        system="You generate smart reply suggestions for a team chat. Be professional and concise."
    )
    replies = [r.strip() for r in raw.split("\n") if r.strip()]
    return replies[:3]


async def classify(message_content: str) -> dict:
    raw = await _ask(
        prompt=f"Classify this message: {message_content}",
        system=(
            "You classify chat messages. "
            "Respond with ONLY a JSON object with exactly these keys: "
            "urgency (low/medium/high), "
            "intent (question/action_item/information/escalation), "
            "sentiment (positive/neutral/negative). "
            "No explanation, no markdown, just raw JSON."
        )
    )
    try:
        # Extract JSON even if model adds extra text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except (json.JSONDecodeError, ValueError):
        return {"urgency": "low", "intent": "information", "sentiment": "neutral"}
