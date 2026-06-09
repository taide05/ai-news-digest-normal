import sqlite3
from datetime import datetime, timedelta


def cleanup_old_data(conn: sqlite3.Connection, full_text_days: int = 90,
                     analysis_days: int = 180):
    ft_cutoff = (datetime.now() - timedelta(days=full_text_days)).strftime("%Y-%m-%d")
    conn.execute(
        "UPDATE articles SET full_text = NULL WHERE published_at < ? AND full_text IS NOT NULL",
        (ft_cutoff,)
    )
    ac_cutoff = (datetime.now() - timedelta(days=analysis_days)).strftime("%Y-%m-%d")
    conn.execute(
        "DELETE FROM analysis_cache WHERE created_at < ?", (ac_cutoff,)
    )
    conn.commit()
