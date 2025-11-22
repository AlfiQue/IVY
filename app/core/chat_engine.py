from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.core import chat_store, learning
from app.core.classifier import classify_with_heuristic, classify_with_llm
from app.core.config import Settings
from app.core.embeddings import embed_text
from app.core.history import log_event
from app.core.llm import LLMClient, build_chat_messages
from app.core.websearch import refine_search_query, search_duckduckgo_with_meta

_WEATHER_KEYWORDS = ("meteo", "météo", "météo", "temperature", "température", "pluie", "temps", "climat")
_WEATHER_HINTS = ("demain", "aujourd", "soir", "matin", "cette nuit", "prochain", "prochaine", "semaine", "heure")


def _looks_like_weather_query(question: str) -> bool:
    normalized = (question or "").lower()
    if not normalized:
        return False
    if not any(keyword in normalized for keyword in _WEATHER_KEYWORDS):
        return False
    if any(hint in normalized for hint in _WEATHER_HINTS):
        return True
    return "meteo" in normalized or "météo" in normalized


async def _polish_voice_answer(client: LLMClient, question: str, answer: str) -> str:
    candidate = (answer or "").strip()
    if not candidate:
        return candidate
    system = (
        "Tu reformules des réponses vocales pour un assistant franco-phone. "
        "Produit une réponse concise (2-3 phrases maximum) en français, sans listes symboliques, "
        "en allant directement à l'information utile. Termine par une suggestion courte si nécessaire."
    )
    prompt = (
        "Question utilisateur :\n"
        f"{question.strip()}\n\n"
        "Réponse initiale :\n"
        f"{candidate}\n\n"
        "Réécris la réponse pour une lecture vocale claire et naturelle."
    )
    try:
        rewritten = await client.chat(
            build_chat_messages(system=system, prompt=prompt),
            temperature=0.2,
            max_tokens=220,
        )
    except Exception:
        return candidate
    text = rewritten.get("text", "").strip()
    return text or candidate


async def _compute_embedding(question: str):
    try:
        return await embed_text(question)
    except Exception:
        return None


def _trim_text(value: str | None, limit: int = 640) -> str:
    if not value:
        return ""
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


async def _log_chat_event(
    *,
    conversation_id: int,
    user_msg: dict[str, Any],
    assistant_msg: dict[str, Any],
    question: str,
    answer: str,
    origin: str,
    qa_id: int | None,
    latency_ms: float,
    reused: bool,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "conversation_id": conversation_id,
        "user_message_id": user_msg.get("id"),
        "assistant_message_id": assistant_msg.get("id"),
        "question": _trim_text(question),
        "answer": _trim_text(answer),
        "origin": origin,
        "reused": reused,
        "latency_ms": round(latency_ms, 2),
    }
    if qa_id is not None:
        payload["qa_id"] = qa_id
    if extra:
        for key, value in extra.items():
            if value is not None:
                payload[key] = value
    await log_event("chat.answer", payload)


async def process_question(
    question: str,
    *,
    conversation_id: Optional[int] = None,
    user: str | None = None,
    response_mode: str | None = None,
    speculative_override: bool | None = None,
) -> Dict[str, Any]:
    settings = Settings()
    effective_settings = settings if speculative_override is None else settings.model_copy(update={"llm_speculative_enabled": bool(speculative_override)})
    conversation = await chat_store.ensure_conversation(conversation_id, title=None)
    conv_id = conversation["id"]

    # Enregistrer la question
    user_msg = await chat_store.add_message(
        conv_id,
        role="user",
        content=question,
        origin=user or "user",
        metadata=None,
    )

    latency_ms = 0.0
    speculative_used = False
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    embedding = await _compute_embedding(question)
    command_suggestions = _extract_command_requests(question)
    threshold = float(getattr(settings, "qa_similarity_threshold", 0.90))
    token_threshold = float(getattr(settings, "qa_token_similarity_threshold", 0.65))
    best = await chat_store.find_best_answer(
        question,
        embedding,
        threshold=threshold,
        token_threshold=token_threshold,
        limit=int(getattr(settings, "qa_similarity_limit", 5)),
    )
    default_refresh_days = max(int(getattr(settings, "qa_variable_refresh_days", 7)), 0)
    stale_entry: dict[str, Any] | None = None

    def _parse_timestamp(value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        candidate = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            return None

    def _parse_refresh(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            if value < 0:
                return None
            return int(value)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            try:
                parsed = int(value)
            except ValueError:
                return None
            return parsed if parsed >= 0 else None
        return None

    def _recommended_refresh(*sources: dict[str, Any] | None) -> int | None:
        for source in sources:
            if not isinstance(source, dict):
                continue
            candidate = _parse_refresh(source.get("refresh_interval_days"))
            if candidate is not None:
                return candidate
        return None

    if best:
        metadata = best.get("metadata") or {}
        if not best.get("is_variable"):
            qa_id = int(best["id"])
            answer = best["answer"]
            origin = "database"
            source_origin = best.get("origin") or origin
            await chat_store.record_usage(qa_id)
            if question.strip() != best.get("question", "").strip():
                try:
                    await chat_store.ensure_alias_entry(
                        question=question,
                        answer=answer,
                        source_qa_id=qa_id,
                        embedding=embedding,
                        match=best.get("match"),
                    )
                except Exception:
                    pass
            reuse_metadata = {"qa_id": qa_id, "source_origin": source_origin, "latency_ms": latency_ms}
            if best.get("similarity") is not None:
                reuse_metadata["similarity"] = best["similarity"]
            if best.get("match"):
                reuse_metadata["match"] = best["match"]
            assistant_msg = await chat_store.add_message(
                conv_id,
                role="assistant",
                content=answer,
                origin=origin,
                is_variable=False,
                metadata=reuse_metadata,
            )
            await _log_chat_event(
                conversation_id=conv_id,
                user_msg=user_msg,
                assistant_msg=assistant_msg,
                question=question,
                answer=answer,
                origin=origin,
                qa_id=qa_id,
                latency_ms=latency_ms,
                reused=True,
                extra={
                    "source_origin": source_origin,
                    "match": best.get("match"),
                    "similarity": best.get("similarity"),
                },
            )
            return {
                "conversation_id": conv_id,
                "question_message": user_msg,
                "answer_message": assistant_msg,
                "origin": origin,
                "qa_id": qa_id,
                "reused": True,
                "match": best.get("match"),
                "source_origin": source_origin,
                "latency_ms": latency_ms,
            }
        else:
            stored_refresh = _parse_refresh(metadata.get("refresh_interval_days"))
            refresh_interval = stored_refresh if stored_refresh is not None else default_refresh_days
            last_refresh = metadata.get("last_refreshed_at") or best.get("updated_at")
            last_refresh_dt = _parse_timestamp(last_refresh)
            is_stale = False
            if refresh_interval > 0 and last_refresh_dt is not None:
                is_stale = now_dt - last_refresh_dt >= timedelta(days=refresh_interval)
            elif refresh_interval == 0:
                is_stale = False
            else:
                # Pas d'information : on force un rafraîchissement ponctuel
                is_stale = True
            if not is_stale:
                qa_id = int(best["id"])
                answer = best["answer"]
                origin = best.get("origin") or "database"
                await chat_store.record_usage(qa_id)
                assistant_metadata = {
                    "qa_id": qa_id,
                    "source_origin": origin,
                    "latency_ms": latency_ms,
                    "refresh_interval_days": refresh_interval,
                }
                if best.get("match"):
                    assistant_metadata["match"] = best["match"]
                assistant_msg = await chat_store.add_message(
                    conv_id,
                    role="assistant",
                    content=answer,
                    origin=origin,
                    is_variable=True,
                    metadata=assistant_metadata,
                )
                await _log_chat_event(
                    conversation_id=conv_id,
                    user_msg=user_msg,
                    assistant_msg=assistant_msg,
                    question=question,
                    answer=answer,
                    origin=origin,
                    qa_id=qa_id,
                    latency_ms=latency_ms,
                    reused=True,
                    extra={
                        "refresh_interval_days": refresh_interval,
                        "match": best.get("match"),
                        "source_origin": origin,
                    },
                )
                return {
                    "conversation_id": conv_id,
                    "question_message": user_msg,
                    "answer_message": assistant_msg,
                    "origin": origin,
                    "qa_id": qa_id,
                    "reused": True,
                    "match": best.get("match"),
                    "source_origin": origin,
                    "latency_ms": latency_ms,
                }
            stale_entry = {
                **best,
                "metadata": metadata,
                "refresh_interval_days": refresh_interval,
            }

    # Classification
    llm_task = asyncio.create_task(classify_with_llm(question))
    heuristic = classify_with_heuristic(question)
    llm_try = await llm_task
    is_variable = llm_try.get("is_variable", False) or heuristic.get("is_variable", False)
    needs_search = llm_try.get("needs_search", False) or heuristic.get("needs_search", False)

    search_results: list[dict[str, Any]] = []
    search_meta: dict[str, Any] = {}
    normalized_search_query = refine_search_query(question)
    if needs_search and len(normalized_search_query.strip()) >= 3:
        try:
            search_results, search_meta = await search_duckduckgo_with_meta(
                question,
                max_results=int(getattr(settings, "duckduckgo_max_results", 5)),
            )
        except Exception:
            search_results = []
            search_meta = {
                "status": "error",
                "query": question.strip(),
                "normalized_query": normalized_search_query,
            }
    elif needs_search:
        # Requete jug�e non pertinente => ne pas lancer de recherche inutile
        needs_search = False

    history = await chat_store.list_messages(conv_id, limit=int(getattr(settings, "chat_history_max_messages", 10)))
    history_pairs = [(msg["role"], msg["content"]) for msg in history if msg["id"] != user_msg["id"]]

    system_prompt = getattr(settings, "chat_system_prompt", "Tu es IVY, assistant local.")
    prompt = question
    if search_results:
        context_lines = [f"Resultat {i+1}: {item.get('title')} - {item.get('body')}" for i, item in enumerate(search_results)]
        context = "\n".join(context_lines)
        prompt = f"Question:\n{question}\n\nInformations externes:\n{context}\n\nUtilise-les si elles sont pertinentes."

    messages = build_chat_messages(system=system_prompt, history=history_pairs, prompt=prompt)
    client = LLMClient(effective_settings)
    llm_started_at = time.perf_counter()
    llm_response = await client.chat(messages)
    latency_ms = (time.perf_counter() - llm_started_at) * 1000.0
    answer = llm_response.get("text", "").strip()
    if response_mode == "voice_concise":
        answer = await _polish_voice_answer(client, question, answer)

    origin = "internet" if search_results else llm_response.get("provider", "llm")
    speculative_used = bool(llm_response.get("speculative"))

    qa_metadata = {
        "classification": {
            "llm": llm_try,
            "heuristic": heuristic,
        },
    }
    if speculative_used:
        qa_metadata["speculative"] = True
    if search_results:
        qa_metadata["search_results"] = search_results
        qa_metadata["search_query"] = search_meta.get("normalized_query") or search_meta.get("query") or question
        if search_meta:
            qa_metadata["search_backend"] = search_meta.get("backend")
            qa_metadata["search_status"] = search_meta.get("status")
    qa_metadata["latency_ms"] = latency_ms

    is_variable = bool(is_variable or (stale_entry is not None and stale_entry.get("is_variable")))

    recommended_refresh = _recommended_refresh(llm_try, heuristic)
    refresh_interval_days = default_refresh_days
    if recommended_refresh is not None:
        refresh_interval_days = recommended_refresh
    if stale_entry:
        existing_refresh = _parse_refresh(stale_entry.get("refresh_interval_days"))
        if existing_refresh is not None:
            refresh_interval_days = existing_refresh
        elif recommended_refresh is not None:
            refresh_interval_days = recommended_refresh

    if is_variable:
        qa_metadata["refresh_interval_days"] = refresh_interval_days
        qa_metadata["last_refreshed_at"] = now_iso

    stored_metadata: dict[str, Any] = qa_metadata
    if stale_entry:
        existing_metadata = dict(stale_entry.get("metadata") or {})
        existing_metadata.update(qa_metadata)
        updated_entry = await chat_store.update_qa(
            int(stale_entry["id"]),
            answer=answer,
            is_variable=is_variable,
            origin=origin,
            metadata=existing_metadata,
            embedding=embedding,
        )
        qa_id = int(stale_entry["id"])
        if isinstance(updated_entry, dict) and isinstance(updated_entry.get("metadata"), dict):
            stored_metadata = updated_entry["metadata"]
        else:
            stored_metadata = existing_metadata
    else:
        qa_id = await chat_store.save_qa(
            question=question,
            answer=answer,
            is_variable=is_variable,
            origin=origin,
            embedding=embedding,
            metadata=qa_metadata,
        )

    assistant_metadata = {
        "qa_id": qa_id,
        "classification": qa_metadata["classification"],
        "search_results_count": len(search_results),
        "latency_ms": latency_ms,
    }
    if search_results and qa_metadata.get("search_query"):
        assistant_metadata["search_query"] = qa_metadata["search_query"]
        assistant_metadata["search_backend"] = qa_metadata.get("search_backend")
    if isinstance(stored_metadata, dict) and stored_metadata.get("refresh_interval_days") is not None:
        assistant_metadata["refresh_interval_days"] = stored_metadata.get("refresh_interval_days")
    if isinstance(stored_metadata, dict) and stored_metadata.get("last_refreshed_at"):
        assistant_metadata["last_refreshed_at"] = stored_metadata.get("last_refreshed_at")
    if isinstance(stored_metadata, dict) and stored_metadata.get("last_refreshed_at"):
        assistant_metadata["last_refreshed_at"] = stored_metadata.get("last_refreshed_at")
    if speculative_used:
        assistant_metadata["speculative"] = True
    if command_suggestions:
        assistant_metadata["commands"] = command_suggestions

    assistant_msg = await chat_store.add_message(
        conv_id,
        role="assistant",
        content=answer,
        origin=origin,
        is_variable=is_variable,
        metadata=assistant_metadata,
    )

    await _log_chat_event(
        conversation_id=conv_id,
        user_msg=user_msg,
        assistant_msg=assistant_msg,
        question=question,
        answer=answer,
        origin=origin,
        qa_id=qa_id,
        latency_ms=latency_ms,
        reused=False,
        extra={
            "classification": {
                "llm": llm_try,
                "heuristic": heuristic,
            },
            "search_results_count": len(search_results),
            "speculative": speculative_used,
            "is_variable": is_variable,
            "stale_entry_refreshed": bool(stale_entry),
        },
    )

    learning.record_event_sync(
        question=question,
        normalized_query=normalized_search_query,
        classification={
            "llm": llm_try,
            "heuristic": heuristic,
            "speculative": speculative_used,
            "is_variable": is_variable,
        },
        needs_search=needs_search,
        search_query=search_meta.get("normalized_query") or search_meta.get("query") or normalized_search_query,
        search_results_count=len(search_results),
        latency_ms=latency_ms,
        origin=origin,
    )

    return {
        "conversation_id": conv_id,
        "question_message": user_msg,
        "answer_message": assistant_msg,
        "origin": origin,
        "qa_id": qa_id,
        "classification": {
            "llm": llm_try,
            "heuristic": heuristic,
        },
        "search_results": search_results,
        "is_variable": is_variable,
        "latency_ms": latency_ms,
        "speculative": speculative_used,
    }

_COMMAND_VERBS = (
    "ouvre",
    "ouvrir",
    "lance",
    "lancer",
    "démarre",
    "demarre",
    "démarrer",
    "demarrer",
    "exécute",
    "execute",
    "exécuter",
    "executer",
    "affiche",
)

_COMMAND_LIBRARY = [
    {
        "id": "open-notepad",
        "keywords": ["bloc-notes", "bloc notes", "notepad"],
        "display_name": "Bloc-notes",
        "action": "notepad.exe",
        "type": "app_launch",
        "risk_level": "low",
    },
    {
        "id": "open-calculator",
        "keywords": ["calculatrice", "calc"],
        "display_name": "Calculatrice",
        "action": "calc.exe",
        "type": "app_launch",
        "risk_level": "low",
    },
    {
        "id": "open-browser",
        "keywords": ["navigateur", "chrome", "edge", "firefox", "internet"],
        "display_name": "Navigateur web",
        "action": "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "type": "app_launch",
        "risk_level": "medium",
        "require_confirm": True,
    },
    {
        "id": "open-files",
        "keywords": ["explorateur", "fichier", "fichiers", "documents"],
        "display_name": "Explorateur de fichiers",
        "action": "explorer.exe",
        "type": "app_launch",
        "risk_level": "low",
    },
]


def _extract_command_requests(question: str) -> list[dict[str, Any]]:
    normalized = (question or "").lower()
    if not normalized:
        return []
    if not any(trigger in normalized for trigger in _COMMAND_VERBS):
        return []
    commands: list[dict[str, Any]] = []
    for entry in _COMMAND_LIBRARY:
        if any(keyword in normalized for keyword in entry["keywords"]):
            commands.append(
                {
                    "id": entry["id"],
                    "display_name": entry["display_name"],
                    "action": entry["action"],
                    "args": entry.get("args", []),
                    "type": entry["type"],
                    "risk_level": entry.get("risk_level", "low"),
                    "require_confirm": bool(entry.get("require_confirm", False)),
                    "source": "heuristic",
                }
            )
    return commands
