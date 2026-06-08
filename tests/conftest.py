import pytest
import sqlite3
import tempfile
import os
from db.schema import init_db
from config import Config


@pytest.fixture
def test_db():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        conn = init_db(path)
        yield conn
        conn.close()


@pytest.fixture
def test_config():
    return Config(
        deepseek_api_key="",
        wecom_webhook_url="",
        exploration_rate=0.0,
        cluster_threshold=0.6,
        max_daily_articles=20,
        host="127.0.0.1",
        port=8765,
        full_text_retention_days=90,
        analysis_cache_retention_days=180,
    )
