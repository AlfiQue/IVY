import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Final

from app.core.config import get_settings
from app.core.trace import get_trace_id

LOG_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

settings = get_settings()
LOG_ROTATE_MB: Final[int] = settings.log_rotate_mb
LOG_RETENTION_DAYS: Final[int] = settings.log_retention_days


class JsonFormatter(logging.Formatter):
    """Formateur qui sÃ©rialise les entrÃ©es en JSON."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "category": record.name,
            "message": record.getMessage(),
            "trace_id": get_trace_id() or None,
        }
        return json.dumps(log_record, ensure_ascii=False)


class SizeAndTimeRotatingFileHandler(TimedRotatingFileHandler):
    """Rotation basÃ©e sur la taille et le temps."""

    def __init__(
        self,
        filename: str | Path,
        max_bytes: int = 0,
        backup_count: int = 0,
        when: str = "midnight",
        interval: int = 1,
        encoding: str | None = None,
        delay: bool = False,
        utc: bool = False,
        atTime=None,
    ) -> None:
        self.maxBytes = max_bytes
        super().__init__(
            str(filename),
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding=encoding,
            delay=delay,
            utc=utc,
            atTime=atTime,
        )

    def shouldRollover(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        if self.maxBytes > 0:
            if self.stream is None:  # pragma: no cover - sÃ©curitÃ©
                self.stream = self._open()
            msg = f"{self.format(record)}\n"
            enc = self.encoding
            if not isinstance(enc, str) or enc.lower() == "locale":
                enc = "utf-8"
            if (self.stream.tell() + len(msg.encode(enc))) >= self.maxBytes:
                return True
        return super().shouldRollover(record)


def _build_logger(name: str, file_path: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # Ã©viter doublons
        return logger

    if file_path is None:
        file_path = LOG_DIR / f"{name}.jsonl"
    handler = SizeAndTimeRotatingFileHandler(
        file_path,
        max_bytes=LOG_ROTATE_MB * 1024 * 1024,
        backup_count=LOG_RETENTION_DAYS,
    )
    handler.setFormatter(JsonFormatter())
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger



_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger existant ou le crÃ©e si nÃ©cessaire."""
    if name not in _LOGGERS:
        _LOGGERS[name] = _build_logger(name)
    return _LOGGERS[name]


server = get_logger("server")
plugin = get_logger("plugin")
llm = get_logger("llm")
audit = get_logger("audit")

