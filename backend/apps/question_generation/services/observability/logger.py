import logging
from typing import Dict


logger = logging.getLogger("question_generation.observability")


def log_metrics(event: str, payload: Dict[str, object]) -> None:
    logger.info("%s | %s", event, payload)
