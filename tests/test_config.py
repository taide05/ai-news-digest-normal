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
