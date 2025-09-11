from __future__ import annotations

from fastapi import APIRouter, Response

try:
    from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
    from prometheus_client import Counter
except Exception:  # pragma: no cover
    CollectorRegistry = None  # type: ignore
    generate_latest = None  # type: ignore
    CONTENT_TYPE_LATEST = "text/plain"  # type: ignore
    Counter = None  # type: ignore

from app.core.config import Settings

router = APIRouter()


REQUESTS = Counter("ivy_requests_total", "Nombre de requêtes", ["endpoint"]) if Counter else None


@router.get("/metrics")
def metrics() -> Response:
    settings = Settings()
    if not settings.enable_metrics or generate_latest is None:
        return Response(status_code=404)
    reg = CollectorRegistry()
    # generate_latest utilisera le registry par défaut si aucun collector ajouté
    data = generate_latest()  # type: ignore
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

