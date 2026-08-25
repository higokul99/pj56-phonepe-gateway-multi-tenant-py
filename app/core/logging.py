import logging
import re
import sys
from typing import Any

# Patterns to redact in log messages
SECRET_PATTERNS = [
    (re.compile(r"(pg_(?:live|test)_[a-zA-Z0-9]{4})[a-zA-Z0-9]+"), r"\1...[REDACTED]"),
    (re.compile(r"(whsec_)[a-zA-Z0-9]+"), r"\1...[REDACTED]"),
    (re.compile(r"(['\"]?client_secret['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1[REDACTED]\2"),
    (re.compile(r"(['\"]?access_token['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1[REDACTED]\2"),
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(X-API-Key:\s*)[^\s,]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(X-Admin-API-Key:\s*)[^\s,]+", re.IGNORECASE), r"\1[REDACTED]"),
]


class SensitiveDataRedactor(logging.Filter):
    """Logging filter that redacts sensitive API keys, tokens, and secrets from all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.redact(v) for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self.redact(item) for item in record.args)
        return True

    @staticmethod
    def redact(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        result = text
        for pattern, replacement in SECRET_PATTERNS:
            result = pattern.sub(replacement, result)
        return result


def setup_logging(debug: bool = False) -> logging.Logger:
    """Configures structured logging with secret redaction."""
    logger = logging.getLogger("phonepe_gateway")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG if debug else logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataRedactor())
    logger.addHandler(handler)

    return logger


logger = setup_logging()
