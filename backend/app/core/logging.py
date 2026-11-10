"""Process-wide logging setup with a per-request correlation id."""

from contextvars import ContextVar
import json
import logging
import logging.config

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_STANDARD_RECORD_KEYS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_id"}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Small JSON formatter so log shippers can parse structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_RECORD_KEYS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Readable format that still shows the structured ``extra`` fields."""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extras = {
            key: value
            for key, value in vars(record).items()
            if key not in _STANDARD_RECORD_KEYS and not key.startswith("_")
        }
        if extras:
            line += " " + " ".join(f"{key}={value}" for key, value in extras.items())
        return line


_configured = False


def configure_logging(level: str = "INFO", *, json_logs: bool = False) -> None:
    """Configure the root ``app`` logger once per process."""

    global _configured
    if _configured:
        return
    formatter = "json" if json_logs else "text"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "text": {
                    "()": TextFormatter,
                    "format": "%(asctime)s %(levelname)s [%(name)s] [req=%(request_id)s] %(message)s",
                },
                "json": {"()": JsonFormatter},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter,
                    "filters": ["request_id"],
                }
            },
            "loggers": {
                "app": {
                    "handlers": ["console"],
                    "level": level.upper(),
                    "propagate": False,
                }
            },
        }
    )
    _configured = True
