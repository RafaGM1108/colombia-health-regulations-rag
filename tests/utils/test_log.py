import logging

from colombia_health_rag.utils.log import get_logger


def test_get_logger_does_not_duplicate_handlers() -> None:
    first = get_logger("colombia_health_rag.test", "DEBUG")
    second = get_logger("colombia_health_rag.test")
    assert first is second
    assert len(second.handlers) == 1
    assert second.level == logging.INFO
