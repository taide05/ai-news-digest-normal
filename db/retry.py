"""SQLite write retry decorator for concurrent write conflicts."""
import sqlite3
import time
import logging
from functools import wraps

logger = logging.getLogger("db.retry")
MAX_RETRIES = 3
RETRY_DELAY = 0.1  # seconds base, exponential backoff


def db_write_retry(func):
    """Decorator: retry SQLite write operations on database-is-locked errors with exponential backoff."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (2 ** attempt)
                    logger.debug(f"DB locked, retry {attempt + 1}/{MAX_RETRIES} in {delay:.2f}s: {func.__name__}")
                    time.sleep(delay)
                    last_error = e
                else:
                    raise
        raise last_error if last_error else RuntimeError("retry exhausted")
    return wrapper
