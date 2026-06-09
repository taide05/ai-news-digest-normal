_db_conn = None
_ai_client = None
_config = None


def get_db():
    return _db_conn


def get_ai():
    return _ai_client


def get_config():
    return _config


def set_globals(db_conn, ai_client, config):
    global _db_conn, _ai_client, _config
    _db_conn = db_conn
    _ai_client = ai_client
    _config = config
