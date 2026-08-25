"""Central logging setup.

Set LOG_LEVEL=DEBUG to see every upstream BirdNET-Go request, cache hits,
and per-action timing. Default is INFO.
"""
from __future__ import annotations

import logging
import sys

_LOGGER_NAME = "avian"


def configure_logging(level: str) -> logging.Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )

    root = logging.getLogger()
    root.setLevel(lvl)
    root.handlers[:] = [handler]

    # Keep uvicorn's loggers aligned with our level so DEBUG is honoured
    # and INFO stays readable.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(lvl)

    log = logging.getLogger(_LOGGER_NAME)
    log.debug("Logging configured at level %s", level.upper())
    return log


def get_logger(suffix: str | None = None) -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME if not suffix else f"{_LOGGER_NAME}.{suffix}")
