import logging
import os
from datetime import datetime
from modules.paths import get_base_dir

LOG_DIR = os.path.join(get_base_dir(), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

log_filename = os.path.join(LOG_DIR, f"provision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("provisioning_tool")


def log(message: str, level: str = "info"):
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    elif level == "success":
        logger.info(f"[SUCCESS] {message}")


CHANGES_LOG = os.path.join(LOG_DIR, "changes.log")


def log_change(category: str, action: str, before: str = None, after: str = None):
    """Append a structured change entry to the persistent changes.log file."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [ts, category, action]
    if before:
        parts.append(f"BEFORE: {before}")
    if after:
        parts.append(f"AFTER: {after}")
    with open(CHANGES_LOG, "a", encoding="utf-8") as f:
        f.write(" | ".join(parts) + "\n")
    logger.info(f"CHANGE: {category} — {action}")
