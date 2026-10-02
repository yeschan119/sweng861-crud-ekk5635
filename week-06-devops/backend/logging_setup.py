"""JSON log lines on stdout, one object per record, each tagged with the request ID."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Set by the request middleware; any log call made while serving a request picks it up.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes every LogRecord has; anything else on a record came from extra=.
_STANDARD_ATTRIBUTES = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extras = {
            key: value
            for key, value in vars(record).items()
            if key not in _STANDARD_ATTRIBUTES and not key.startswith("_")
        }
        # Core fields go last so an extra named "level" or "request_id" cannot overwrite them.
        entry = {
            **extras,
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        # default=str: an unserialisable extra must not cost the whole line.
        return json.dumps(entry, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Send every logger's records to stdout as JSON. Safe to call more than once."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # httpx logs every URL it calls at INFO, query string included.
    logging.getLogger("httpx").setLevel(logging.WARNING)
