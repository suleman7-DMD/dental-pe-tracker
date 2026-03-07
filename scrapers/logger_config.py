import logging
import os
from datetime import datetime

_BASE = os.environ.get("DENTAL_PE_DIR",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS_DIR = os.path.join(_BASE, "logs")


def get_logger(script_name: str) -> logging.Logger:
    """Get a configured logger that writes to both terminal and daily log file."""
    logger = logging.getLogger(script_name)

    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler — one log file per day (skip if dir not writable, e.g. Streamlit Cloud)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        log_filename = f"dental_tracker_{datetime.now().strftime('%Y-%m-%d')}.log"
        log_path = os.path.join(LOGS_DIR, log_filename)
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (OSError, PermissionError):
        pass  # Cloud environments may not support file logging

    return logger
