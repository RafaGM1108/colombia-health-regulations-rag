import logging

from ds_project.utils.log import get_logger


def test_get_logger_does_not_duplicate_handlers() -> None:
    first = get_logger("ds_project.test", "DEBUG")
    second = get_logger("ds_project.test")
    assert first is second
    assert len(second.handlers) == 1
    assert second.level == logging.INFO
