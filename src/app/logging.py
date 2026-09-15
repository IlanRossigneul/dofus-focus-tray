import logging
import sys


class ComponentFormatter(logging.Formatter):
    """Format application logs with a component tag."""

    def format(self, record: logging.LogRecord) -> str:
        parts = record.name.split(".")

        if len(parts) >= 2:
            component = parts[-1].replace("_", " ").upper()
        else:
            component = record.name.upper()

        return f"[{record.levelname}] [{component}] {record.getMessage()}"


def setup_logger(level: int = logging.INFO) -> None:
    """Configure application logging."""

    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stdout,
    )

    formatter = ComponentFormatter()

    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)
