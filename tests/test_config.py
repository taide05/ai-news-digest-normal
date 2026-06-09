import os
import tempfile
import pytest
from config import Config, load_config


def test_load_config_loads_yaml_and_env():
    with tempfile.TemporaryDirectory() as tmp:
        yaml_path = os.path.join(tmp, "config.yaml")
        with open(yaml_path, "w") as f:
            f.write("pipeline:\n  cluster_threshold: 0.7\nweb:\n  port: 9999\n")

        env_path = os.path.join(tmp, ".env")
        with open(env_path, "w") as f:
            f.write("DEEPSEEK_API_KEY=sk-test-123\nWECOM_WEBHOOK_URL=https://example.com/hook\n")

        cfg = load_config(env_path=env_path, yaml_path=yaml_path)

        assert cfg.deepseek_api_key == "sk-test-123"
        assert cfg.wecom_webhook_url == "https://example.com/hook"
        assert cfg.cluster_threshold == 0.7
        assert cfg.port == 9999


def test_load_config_defaults_when_no_yaml():
    with tempfile.TemporaryDirectory() as tmp:
        env_path = os.path.join(tmp, ".env")
        with open(env_path, "w") as f:
            f.write("DEEPSEEK_API_KEY=sk-test\nWECOM_WEBHOOK_URL=https://example.com/hook\n")

        cfg = load_config(env_path=env_path, yaml_path="/nonexistent/config.yaml")

        assert cfg.cluster_threshold == 0.6
        assert cfg.port == 8765


def test_config_nested_defaults():
    cfg = Config()
    assert cfg.scheduler.cron == "0 9 * * *"
    assert cfg.scheduler.run_on_startup is True
    assert cfg.ranking.cold_start_threshold == 15
    assert cfg.ranking.blend_max == 25
    assert cfg.ranking.exploration_floor == 2
    assert cfg.discovery.max_pending == 50


def test_config_existing_fields_preserved():
    cfg = Config()
    assert cfg.exploration_rate == 0.15
    assert cfg.cluster_threshold == 0.6
    assert cfg.max_daily_articles == 20
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8765


def test_config_nested_from_yaml():
    with tempfile.TemporaryDirectory() as tmp:
        yaml_path = os.path.join(tmp, "config.yaml")
        with open(yaml_path, "w") as f:
            f.write("scheduler:\n  cron: 0 8 * * *\n  run_on_startup: false\n")
            f.write("ranking:\n  cold_start_threshold: 10\n  blend_max: 30\n  exploration_floor: 3\n")
            f.write("discovery:\n  max_pending: 25\n")
        cfg = load_config(env_path="/nonexistent/.env", yaml_path=yaml_path)
        assert cfg.scheduler.cron == "0 8 * * *"
        assert cfg.scheduler.run_on_startup is False
        assert cfg.ranking.cold_start_threshold == 10
        assert cfg.ranking.blend_max == 30
        assert cfg.ranking.exploration_floor == 3
        assert cfg.discovery.max_pending == 25


def test_source_candidates_schema():
    from db.schema import init_db
    import tempfile, os
    path = os.path.join(tempfile.gettempdir(), "test_v05_schema.db")
    conn = init_db(path)
    cols = conn.execute("PRAGMA table_info(source_candidates)").fetchall()
    col_names = [c[1] for c in cols]
    assert "url" in col_names
    assert "verified" in col_names
    assert "relevance_score" in col_names
    assert "discovered_at" in col_names
    cols2 = conn.execute("PRAGMA table_info(read_records)").fetchall()
    col_names2 = [c[1] for c in cols2]
    assert "topics" in col_names2
    conn.close()
    os.unlink(path)
