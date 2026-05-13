from __future__ import annotations

import sys

from loguru import logger

from app.config import SETTINGS

# loguru installs a default stderr sink; we replace it once with a configured sink.
# A one-element list is a deliberately boring "module-level mutable flag" so we don't
# need ``global`` in the function.
_configured: list[bool] = []


def configure_logging() -> None:
    """Install the project's loguru sink (JSON or plain), once."""
    if _configured:
        return
    logger.remove()
    logger.add(
        sys.stdout,
        level=SETTINGS.log_level,
        serialize=SETTINGS.log_serialize,
        backtrace=SETTINGS.log_backtrace,
        diagnose=SETTINGS.log_diagnose,
    )
    _configured.append(True)


configure_logging()
