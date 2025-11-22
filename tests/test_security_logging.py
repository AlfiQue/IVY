import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.core import security  # noqa: E402


def test_regenerate_password_creates_log(caplog):
    with caplog.at_level(logging.INFO, logger="audit"):
        security.regenerate_password("secret", source="unittest")
    assert any(
        record.message == "Mot de passe régénéré" and record.source == "unittest"
        for record in caplog.records
    )
    assert any(hasattr(record, "timestamp") for record in caplog.records)
