"""Logging setup shared by pipelines, the API and the app."""

import logging

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def get_logger(name: str, level: str | int = "INFO") -> logging.Logger:
    """Return a logger with a single console handler.

    Calling it repeatedly with the same name does not add duplicate handlers.

    Args:
        name: Logger name, usually ``__name__``.
        level: Logging level name or number.

    Returns:
        The configured logger.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(level)
    return logger
