import os
from dataclasses import dataclass
from dotenv import load_dotenv as _load_dotenv
import yaml


@dataclass
class Config:
    deepseek_api_key: str = ""
    wecom_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    exploration_rate: float = 0.15
    cluster_threshold: float = 0.6
    max_daily_articles: int = 20
    host: str = "127.0.0.1"
    port: int = 8765
    full_text_retention_days: int = 90
    analysis_cache_retention_days: int = 180


def load_config(env_path: str = ".env", yaml_path: str = "config.yaml") -> Config:
    cfg = Config()

    if os.path.isfile(env_path):
        _load_dotenv(env_path, override=True)
    cfg.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    cfg.wecom_webhook_url = os.getenv("WECOM_WEBHOOK_URL", "")
    cfg.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    cfg.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if os.path.isfile(yaml_path):
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        pipeline = data.get("pipeline", {})
        if pipeline:
            cfg.exploration_rate = pipeline.get("exploration_rate", cfg.exploration_rate)
            cfg.cluster_threshold = pipeline.get("cluster_threshold", cfg.cluster_threshold)
            cfg.max_daily_articles = pipeline.get("max_daily_articles", cfg.max_daily_articles)

        web = data.get("web", {})
        if web:
            cfg.host = web.get("host", cfg.host)
            cfg.port = web.get("port", cfg.port)

        d = data.get("data", {})
        if d:
            cfg.full_text_retention_days = d.get("full_text_retention_days", cfg.full_text_retention_days)
            cfg.analysis_cache_retention_days = d.get("analysis_cache_retention_days", cfg.analysis_cache_retention_days)

    return cfg
