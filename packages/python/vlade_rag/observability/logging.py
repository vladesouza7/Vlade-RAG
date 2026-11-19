"""JSON logs on stdout with the current trace id (docs/ARCHITECTURE.md section 16.3)."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_SECRET_KEYS = re.compile(r"(?i)(api[_-]?key|authorization|password|secret|token|pepper)")
_STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message"}


def _trace_ids() -> tuple[str | None, str | None]:
    try:
        from opentelemetry import trace
    except ImportError:
        return None, None
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None, None
    return f"{ctx.trace_id:032x}", f"{ctx.span_id:016x}"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        trace_id, span_id = _trace_ids()
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        if trace_id:
            payload["trace_id"] = trace_id
            payload["span_id"] = span_id
        for key, value in record.__dict__.items():
            if key in _STANDARD or key.startswith("_"):
                continue
            payload[key] = "[REDACTED]" if _SECRET_KEYS.search(key) else value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
