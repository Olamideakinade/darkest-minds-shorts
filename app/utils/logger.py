"""Structured, secure logging utility with automatic secrets redaction."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from app.config import config

# Regex patterns matching potential secret strings
SENSITIVE_PATTERNS = [
    re.compile(r"(AIzaSy[0-9A-Za-z-_]{33})"),                         # Google/YouTube API Key
    re.compile(r"(\d{8,10}:[a-zA-Z0-9_-]{35})"),                    # Telegram Bot Token
    re.compile(r'(Bearer\s+)[a-zA-Z0-9_\-\.]+'),                     # Bearer Tokens
    re.compile(r'("?(?:client_secret|access_token|refresh_token)"?\s*[:=]\s*"?[^"\s,]+"?[\'"]?)', re.IGNORECASE),
]


class SecretRedactionFilter(logging.Filter):
    """Logging filter that redacts sensitive API keys and tokens."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.redact(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.redact(str(v)) for v in record.args)
        return True

    @staticmethod
    def redact(text: str) -> str:
        for pattern in SENSITIVE_PATTERNS:
            text = pattern.sub(r"[REDACTED_SECRET]", text)
        return text


def setup_logger(name: str = "mhide") -> logging.Logger:
    """Set up and return a configured logger with console and file handlers."""
    logger = logging.getLogger(name)

    # Return existing logger if already configured
    if logger.handlers:
        return logger

    level = getattr(logging, config.log_level, logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | [%(name)s:%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    redaction_filter = SecretRedactionFilter()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redaction_filter)
    logger.addHandler(console_handler)

    # File Handler (rotating 5MB files, keep 5 backups)
    log_file = config.logs_dir / "mhide.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction_filter)
    logger.addHandler(file_handler)

    return logger


# Global application logger
logger = setup_logger("mhide")
