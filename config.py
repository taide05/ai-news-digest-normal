import os
from dataclasses import dataclass, field
from dotenv import load_dotenv as _load_dotenv
import yaml


@dataclass
class SchedulerConfig:
    cron: str = "0 9 * * *"
    enabled: bool = True
    run_on_startup: bool = True


@dataclass
class RankingConfig:
    interest_weight: float = 0.7
    freshness_decay: float = 0.3
    exploration_floor: int = 2
    cold_start_threshold: int = 15
    blend_max: int = 25


@dataclass
class DiscoveryConfig:
    enabled: bool = True
    max_candidates: int = 50
    max_pending: int = 50


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
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    ranking: RankingConfig = field(default_factory=RankingConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)


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

        # v0.5 nested configs
        sched = data.get("scheduler", {})
        if sched:
            cfg.scheduler.cron = sched.get("cron", cfg.scheduler.cron)
            cfg.scheduler.enabled = sched.get("enabled", cfg.scheduler.enabled)
            cfg.scheduler.run_on_startup = sched.get("run_on_startup", cfg.scheduler.run_on_startup)

        rank = data.get("ranking", {})
        if rank:
            cfg.ranking.interest_weight = rank.get("interest_weight", cfg.ranking.interest_weight)
            cfg.ranking.freshness_decay = rank.get("freshness_decay", cfg.ranking.freshness_decay)
            cfg.ranking.exploration_floor = rank.get("exploration_floor", cfg.ranking.exploration_floor)
            cfg.ranking.cold_start_threshold = rank.get("cold_start_threshold", cfg.ranking.cold_start_threshold)
            cfg.ranking.blend_max = rank.get("blend_max", cfg.ranking.blend_max)

        disc = data.get("discovery", {})
        if disc:
            cfg.discovery.enabled = disc.get("enabled", cfg.discovery.enabled)
            cfg.discovery.max_candidates = disc.get("max_candidates", cfg.discovery.max_candidates)
            cfg.discovery.max_pending = disc.get("max_pending", cfg.discovery.max_pending)

    return cfg
