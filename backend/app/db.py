import os, sqlite3
from contextlib import contextmanager
from pathlib import Path

def db_path() -> Path:
    d = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "borrowboard.db"

def connect():
    c = sqlite3.connect(db_path())
    c.row_factory = sqlite3.Row
    return c

@contextmanager
def tx():
    """写路径专用：BEGIN IMMEDIATE 先拿写锁再校验，检查+落库同事务，
    保证同一件物品只会留下一种 items.status 与一笔在借行；异常即整体回滚。"""
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()
