from __future__ import annotations
from .base import BaseCollector, Article

_collectors: dict[str, BaseCollector] = {}


def register(collector: BaseCollector):
    _collectors[collector.name] = collector


def get_all() -> list[BaseCollector]:
    return list(_collectors.values())


def get_enabled(enabled_ids: list[str]) -> list[BaseCollector]:
    return [c for c in _collectors.values() if c.name in enabled_ids]
