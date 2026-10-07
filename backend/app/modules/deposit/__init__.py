"""占用档（hold）底座。

借出通过前先开占用档：占用期间物品 status 仍是 available（停在可借栏）、
loans 不增行，但占用即占住该物可借额度（见 engines.borrow_rules.RESERVES_CAPACITY），
他人再开占用或直接借出一律失败。确认占用时在同一笔事务里生成唯一在借行并把
物品置为 on_loan；任何一步失败整体回滚，占用档与可借栏一起回到确认前。
"""
from datetime import datetime, timezone

from app.db import connect
from app.engines.borrow_rules import can_confirm_hold, can_hold

STATUS_HELD = "held"
STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"


class HoldError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_hold(item_id: int, borrower: str, due_date: str, qty: int = 1) -> int:
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        item = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not item:
            raise HoldError("item_not_found")
        held = c.execute(
            "SELECT COUNT(*) c FROM holds WHERE item_id=? AND status=?",
            (item_id, STATUS_HELD)).fetchone()["c"]
        check = can_hold(dict(item), held)
        if not check["ok"]:
            raise HoldError(check["reason"])
        active = c.execute(
            "SELECT COUNT(*) c FROM loans WHERE item_id=? AND status='active'",
            (item_id,)).fetchone()["c"]
        if active > 0:
            raise HoldError("already_on_loan")
        cur = c.execute(
            "INSERT INTO holds(item_id,borrower,qty,due_date,status,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (item_id, borrower, qty, due_date, STATUS_HELD, _now()))
        c.commit()
        return cur.lastrowid
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def confirm_hold(hold_id: int) -> int:
    """确认占用 -> 同一事务内：唯一在借 loan + 物品 on_loan + 占用档 confirmed。"""
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        hold = c.execute("SELECT * FROM holds WHERE id=?", (hold_id,)).fetchone()
        if not hold:
            raise HoldError("hold_not_found")
        if hold["status"] != STATUS_HELD:
            raise HoldError("hold_not_open")
        item = c.execute("SELECT * FROM items WHERE id=?", (hold["item_id"],)).fetchone()
        if not item:
            raise HoldError("item_not_found")
        check = can_confirm_hold(dict(item), hold["qty"])
        if not check["ok"]:
            raise HoldError(check["reason"])
        active = c.execute(
            "SELECT COUNT(*) c FROM loans WHERE item_id=? AND status='active'",
            (hold["item_id"],)).fetchone()["c"]
        if active > 0:
            raise HoldError("already_on_loan")
        now = _now()
        cur = c.execute(
            "INSERT INTO loans(item_id,borrower,status,due_date,lent_at) VALUES (?,?,?,?,?)",
            (hold["item_id"], hold["borrower"], "active", hold["due_date"], now))
        loan_id = cur.lastrowid
        c.execute(
            "UPDATE holds SET status=?, loan_id=?, confirmed_at=? WHERE id=?",
            (STATUS_CONFIRMED, loan_id, now, hold_id))
        c.execute("UPDATE items SET status='on_loan' WHERE id=?", (hold["item_id"],))
        c.commit()
        return loan_id
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def cancel_hold(hold_id: int) -> None:
    """取消未确认占用，释放可借额度（物品本就停在可借栏，无需改 items.status）。"""
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        hold = c.execute("SELECT * FROM holds WHERE id=?", (hold_id,)).fetchone()
        if not hold:
            raise HoldError("hold_not_found")
        if hold["status"] != STATUS_HELD:
            raise HoldError("hold_not_open")
        c.execute(
            "UPDATE holds SET status=?, cancelled_at=? WHERE id=?",
            (STATUS_CANCELLED, _now(), hold_id))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def list_holds(open_only: bool = False) -> list[dict]:
    c = connect()
    sql = ("SELECT holds.*, items.title, items.owner FROM holds "
           "JOIN items ON items.id=holds.item_id")
    if open_only:
        sql += " WHERE holds.status='held'"
    sql += " ORDER BY CASE holds.status WHEN 'held' THEN 0 ELSE 1 END, holds.id DESC"
    rows = [dict(r) for r in c.execute(sql)]
    c.close()
    return rows
