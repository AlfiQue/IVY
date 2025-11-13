from __future__ import annotations

import json
import re
from typing import Any, Dict

from app.core.config import Settings
from app.core.llm import LLMClient, build_chat_messages

_LLMC_SYSTEM = (
    "Tu es un classifieur. Pour une question donnée, réponds en JSON avec les clés "
    "'is_variable' (booléen) et 'needs_search' (booléen). 'is_variable' doit être vrai si la réponse change souvent "
    "ou dépend du contexte temps/réseau. 'needs_search' doit être vrai seulement si une recherche internet est nécessaire."
)


async def classify_with_llm(question: str) -> Dict[str, Any]:
    client = LLMClient()
    prompt = (
        "Question:"
        + "\n"
        + question
        + "\nRéponds uniquement par un JSON."
    )
    messages = build_chat_messages(system=_LLMC_SYSTEM, prompt=prompt)
    try:
        result = await client.chat(messages, temperature=0.0, max_tokens=128)
    except RuntimeError as exc:
        message = str(exc)
        return {
            "is_variable": False,
            "needs_search": False,
            "raw": message,
            "provider": "llm_unavailable",
            "error": message,
        }
    text = result.get("text", "").strip()
    try:
        data = json.loads(_extract_json(text))
    except Exception:
        data = {}
    return {
        "is_variable": bool(data.get("is_variable")),
        "needs_search": bool(data.get("needs_search")),
        "raw": text,
        "provider": result.get("provider"),
    }


def _extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return "{}"


_VARIABLE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^quand",
        r"^quelle? heure",
        r"^quelle? date",
        r"^quel temps",
        r"(?<!pas )possible",
        r"combien",
        r"temperature",
        r"meteo",
        r"prix",
        r"disponible",
        r"resultat",
    ]
]

_SEARCH_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"meteo",
        r"actualit",
        r"news",
        r"recherche",
        r"internet",
        r"google",
        r"web",
    ]
]


def classify_with_heuristic(question: str) -> Dict[str, Any]:
    normalized = question.strip()
    is_variable = any(p.search(normalized) for p in _VARIABLE_PATTERNS)
    needs_search = any(p.search(normalized) for p in _SEARCH_PATTERNS)
    return {
        "is_variable": is_variable,
        "needs_search": needs_search,
    }


async def full_classification(question: str) -> Dict[str, Any]:
    llm_result = await classify_with_llm(question)
    heuristic = classify_with_heuristic(question)
    combined = {
        "is_variable": llm_result.get("is_variable", False) or heuristic.get("is_variable", False),
        "needs_search": llm_result.get("needs_search", False) or heuristic.get("needs_search", False),
        "details": {
            "llm": llm_result,
            "heuristic": heuristic,
        },
    }
    return combined



