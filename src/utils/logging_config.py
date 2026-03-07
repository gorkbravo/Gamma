import logging
import os


def setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("kaleido").setLevel(logging.WARNING)
    logging.getLogger("choreographer").setLevel(logging.WARNING)
    logging.getLogger("ib_insync").setLevel(logging.WARNING)
    logging.getLogger("ib_insync.wrapper").setLevel(logging.WARNING)
    logging.getLogger("ib_insync.client").setLevel(logging.WARNING)
