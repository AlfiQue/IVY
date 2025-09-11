import json

from app.api.messaging import send_error, send_status, send_token


def _decode(msg: str) -> dict:
    data = json.loads(msg)
    data.pop("ts", None)
    return data


def test_send_token_format() -> None:
    msg = _decode(send_token("1", "server", "bonjour"))
    assert msg == {
        "type": "event",
        "req_id": "1",
        "source": "server",
        "event": "token",
        "payload": "bonjour",
    }


def test_send_status_format() -> None:
    msg = _decode(send_status("1", "server", "ok"))
    assert msg == {
        "type": "event",
        "req_id": "1",
        "source": "server",
        "event": "status",
        "payload": "ok",
    }


def test_send_error_format() -> None:
    msg = _decode(send_error("1", "server", "oops"))
    assert msg == {
        "type": "error",
        "req_id": "1",
        "source": "server",
        "event": "error",
        "payload": "oops",
    }
