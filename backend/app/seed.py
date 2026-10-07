from app.db import connect

def init_db():
    c = connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS items(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, owner TEXT, status TEXT, data_quality TEXT
    );
    CREATE TABLE IF NOT EXISTS loans(
      id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INT, borrower TEXT, status TEXT,
      due_date TEXT, lent_at TEXT, returned_at TEXT
    );
    CREATE TABLE IF NOT EXISTS holds(
      id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INT, borrower TEXT, qty INT,
      due_date TEXT, status TEXT, loan_id INT, created_at TEXT, confirmed_at TEXT, cancelled_at TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    # 历史脏数据修复：无主样例不再标 dirty，占用资格改由规则（无主不得占用）强制。
    c.execute(
        "UPDATE items SET data_quality='clean' WHERE title='脏数据-无主' AND data_quality='dirty'")
    if c.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] == 0:
        c.executemany("INSERT INTO items(title,owner,status,data_quality) VALUES (?,?,?,?)", [
            ("电钻", "老周", "available", "clean"),
            ("折叠桌", "小陈", "available", "clean"),
            ("脏数据-无主", "", "available", "clean"),
            ("已外借样例", "阿强", "on_loan", "clean"),
        ])
        c.execute(
            "INSERT INTO loans(item_id,borrower,status,due_date,lent_at) VALUES (?,?,?,?,?)",
            (4, "邻居甲", "active", "2020-06-01", "2020-05-01"),
        )
        c.execute("INSERT INTO settings(key,value) VALUES ('board_name','木色邻里板')")
        c.commit()
    else:
        c.commit()
    c.close()
