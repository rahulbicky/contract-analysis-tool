import logging
import os


def configure_logging():
    """Configure root logging once, at process start (CLI entry points and the API)."""
    level = os.environ.get("CONTRACTLENS_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
