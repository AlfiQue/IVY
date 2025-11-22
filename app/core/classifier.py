from __future__ import annotations

import json
import re
from typing import Any, Dict

from app.core.websearch import refine_search_query

from app.core.config import Settings
from app.core.llm import LLMClient, build_chat_messages

_LLMC_SYSTEM = (
    "Tu es un classifieur. Pour une question donnée, réponds uniquement en JSON avec au moins les clés "
    "'is_variable' (booléen) et 'needs_search' (booléen). Ajoute également la clé optionnelle "
    "'refresh_interval_days' (entier >= 0) pour indiquer le délai conseillé avant qu'une réponse devienne périmée. "
    "Utilise 0 pour indiquer qu'aucun rafraîchissement automatique n'est requis."
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

    def _parse_refresh(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            if value < 0:
                return None
            return int(value)
        if isinstance(value, str):
            try:
                parsed = int(value.strip())
            except ValueError:
                return None
            return parsed if parsed >= 0 else None
        return None

    refresh_interval = _parse_refresh(data.get("refresh_interval_days"))
    return {
        "is_variable": bool(data.get("is_variable")),
        "needs_search": bool(data.get("needs_search")),
        "raw": text,
        "provider": result.get("provider"),
        "refresh_interval_days": refresh_interval,
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

_SEARCH_KEYWORDS = {
    "actu",
    "actualite",
    "actualites",
    "news",
    "ia",
    "intelligence",
    "artificielle",
    "conference",
    "evenement",
    "evenements",
    "activite",
    "activites",
    "mission",
    "missions",
    "veille",
    "tendance",
    "tendances",
    "innovation",
    "innovations",
}

_WEATHER_KEYWORDS = {
    "meteo",
    "météo",
    "temperature",
    "température",
    "pluie",
    "temps",
}
_WEATHER_HINTS = {
    "demain",
    "aujourd",
    "ce soir",
    "ce matin",
    "cette nuit",
    "prochain",
    "prochaine",
    "week-end",
    "heure",
}


def _tokenize(question: str) -> list[str]:
    normalized = refine_search_query(question)
    return [token for token in normalized.lower().split() if token]


def classify_with_heuristic(question: str) -> Dict[str, Any]:
    normalized = question.strip()
    is_variable = any(p.search(normalized) for p in _VARIABLE_PATTERNS)
    needs_search = any(p.search(normalized) for p in _SEARCH_PATTERNS)
    tokens = _tokenize(question)
    lowered = normalized.lower()
    if any(keyword in lowered for keyword in _WEATHER_KEYWORDS) and any(hint in lowered for hint in _WEATHER_HINTS):
        needs_search = True
        is_variable = True
    if tokens:
        keyword_hit = any(token in _SEARCH_KEYWORDS for token in tokens)
        needs_search = needs_search or keyword_hit
        if keyword_hit and len(tokens) < 2:
            # Eviter les requetes du type "quels ?" qui se reduisent a 1 token
            needs_search = False
    refresh_interval: int | None = None
    if is_variable:
        refresh_interval = 1 if needs_search else 7
    return {
        "is_variable": is_variable,
        "needs_search": needs_search,
        "refresh_interval_days": refresh_interval,
    }
