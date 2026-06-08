from datetime import datetime, timedelta


def get_week_bounds(reference_date: datetime | None = None) -> tuple[str, str]:
    today = reference_date or datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def get_partial_week_end() -> str:
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")
