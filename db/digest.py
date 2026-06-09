import sqlite3
from datetime import datetime


def has_digest_today(conn: sqlite3.Connection) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT 1 FROM daily_digests WHERE date = ?", (today,)
    ).fetchone()
    return row is not None


def create_digest(conn: sqlite3.Connection, article_ids: list[str]) -> int | None:
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        cur = conn.execute(
            "INSERT INTO daily_digests (date) VALUES (?)", (today,)
        )
        digest_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO digest_articles (digest_id, article_id) VALUES (?, ?)",
            [(digest_id, aid) for aid in article_ids]
        )
        conn.commit()
        return digest_id
    except sqlite3.IntegrityError:
        return None


def mark_webhook_sent(conn: sqlite3.Connection):
    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        "UPDATE daily_digests SET webhook_sent = 1 WHERE date = ?", (today,)
    )
    conn.commit()


def insert_cluster(conn: sqlite3.Connection, cid: str, label: str, date_str: str):
    conn.execute(
        "INSERT INTO clusters (id, label, digest_date) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET label = ?",
        (cid, label, date_str, label)
    )


def insert_cluster_article(conn: sqlite3.Connection, cid: str, article_id: str):
    conn.execute(
        "INSERT OR IGNORE INTO cluster_articles (cluster_id, article_id) VALUES (?, ?)",
        (cid, article_id)
    )


def mark_article_exploration(conn: sqlite3.Connection, article_id: str):
    conn.execute(
        "UPDATE articles SET summary = '[探索] ' || COALESCE(summary, '') WHERE id = ?",
        (article_id,)
    )
