"""Feature pipeline: raw data -> model input."""

from ds_project.utils.config import Config, get_config
from ds_project.utils.log import get_logger


def run(config: Config | None = None) -> None:
    """Run the feature pipeline.

    Args:
        config: Project configuration. Loaded from ``conf/base.yaml`` if omitted.
    """
    config = config or get_config()
    logger = get_logger(__name__, config.logging.level)
    logger.info("Reading from %s", config.paths.raw)
    # TODO: implement the feature pipeline steps using functions from ds_project.
    logger.info("Writing to %s", config.paths.model_input)
