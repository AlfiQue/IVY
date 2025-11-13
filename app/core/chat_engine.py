from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from app.core import chat_store
from app.core.classifier import classify_with_heuristic, classify_with_llm
from app.core.config import Settings
from app.core.embeddings import embed_text
from app.core.llm import LLMClient, build_chat_messages
from app.core.websearch import search_duckduckgo


async def _compute_embedding(question: str):
    try:
        return await embed_text(question)
    except Exception:
        return None


async def process_question(
    question: str,
    *,
    conversation_id: Optional[int] = None,
    user: str | None = None,
) -> Dict[str, Any]:
    settings = Settings()
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

    embedding = await _compute_embedding(question)
    existing = await chat_store.similar_questions(embedding, limit=5) if embedding is not None else []
    threshold = float(getattr(settings, "qa_similarity_threshold", 0.90))
    best = None
    for item in existing:
        if item["similarity"] >= threshold:
            if best is None or item["similarity"] > best["similarity"]:
                best = item
    # Réutilisation directe
    if best and not best.get("is_variable"):
        qa_id = best["id"]
        answer = best["answer"]
        await chat_store.record_usage(qa_id)
        assistant_msg = await chat_store.add_message(
            conv_id,
            role="assistant",
            content=answer,
            origin="database",
            is_variable=False,
            metadata={"qa_id": qa_id, "similarity": best["similarity"]},
        )
        return {
            "conversation_id": conv_id,
            "question_message": user_msg,
            "answer_message": assistant_msg,
            "origin": "database",
            "qa_id": qa_id,
            "reused": True,
        }

    # Classification
    llm_task = asyncio.create_task(classify_with_llm(question))
    heuristic = classify_with_heuristic(question)
    llm_try = await llm_task
    is_variable = llm_try.get("is_variable", False) or heuristic.get("is_variable", False)
    needs_search = llm_try.get("needs_search", False) or heuristic.get("needs_search", False)

    search_results = []
    if needs_search:
        try:
            search_results = await search_duckduckgo(question, max_results=int(getattr(settings, "duckduckgo_max_results", 5)))
        except Exception:
            search_results = []

    history = await chat_store.list_messages(conv_id, limit=int(getattr(settings, "chat_history_max_messages", 10)))
    history_pairs = [(msg["role"], msg["content"]) for msg in history if msg["id"] != user_msg["id"]]

    system_prompt = getattr(settings, "chat_system_prompt", "Tu es IVY, assistant local.")
    prompt = question
    if search_results:
        context_lines = [f"Resultat {i+1}: {item.get('title')} - {item.get('body')}" for i, item in enumerate(search_results)]
        context = "\n".join(context_lines)
        prompt = f"Question:\n{question}\n\nInformations externes:\n{context}\n\nUtilise-les si elles sont pertinentes."

    messages = build_chat_messages(system=system_prompt, history=history_pairs, prompt=prompt)
    client = LLMClient(settings)
    llm_response = await client.chat(messages)
    answer = llm_response.get("text", "").strip()

    origin = "internet" if search_results else llm_response.get("provider", "llm")

    qa_metadata = {
        "classification": {
            "llm": llm_try,
            "heuristic": heuristic,
        },
    }
    if search_results:
        qa_metadata["search_results"] = search_results

    qa_id = await chat_store.save_qa(
        question=question,
        answer=answer,
        is_variable=is_variable,
        origin=origin,
        embedding=embedding,
        metadata=qa_metadata,
    )

    assistant_msg = await chat_store.add_message(
        conv_id,
        role="assistant",
        content=answer,
        origin=origin,
        is_variable=is_variable,
        metadata={
            "qa_id": qa_id,
            "classification": qa_metadata["classification"],
            "search_results_count": len(search_results),
        },
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
    }

