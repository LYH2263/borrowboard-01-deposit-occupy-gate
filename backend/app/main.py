from datetime import date, datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.borrow_rules import can_lend, classify_loans
from app.modules import deposit
from app.modules.deposit import HoldError

app = FastAPI(title="Borrowboard", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def _hold_http_error(e: HoldError) -> HTTPException:
    if e.reason in ("item_not_found", "hold_not_found"):
        return HTTPException(404, e.reason)
    if e.reason == "invalid_quantity":
        return HTTPException(400, e.reason)
    return HTTPException(409, e.reason)

@app.get("/api/health")
def health(): return {"ok": True, "project": "borrowboard"}

@app.get("/api/items")
def items():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM items")]; c.close(); return rows

@app.get("/api/board")
def board():
    c = connect()
    available = [dict(r) for r in c.execute("SELECT * FROM items WHERE status='available'")]
    # 占用不产生 loan、物品仍 available；把未确认占用标记带给可借栏。
    open_holds = {r["item_id"]: dict(r) for r in c.execute(
        "SELECT * FROM holds WHERE status='held'")}
    for a in available:
        h = open_holds.get(a["id"])
        if h:
            a["held"] = True
            a["hold_id"] = h["id"]
            a["held_by"] = h["borrower"]
            a["hold_qty"] = h["qty"]
    loans = [dict(r) for r in c.execute(
        """SELECT loans.*, items.title FROM loans JOIN items ON items.id=loans.item_id
           WHERE loans.status='active'""")]
    c.close()
    cls = classify_loans(loans, date.today().isoformat())
    return {
        "available": available,
        "active": cls["active"],
        "overdue": cls["overdue"],
        "counts": {
            "available": len(available),
            "active": len(cls["active"]),
            "overdue": len(cls["overdue"]),
            "held": len(open_holds),
        },
    }

class ItemIn(BaseModel):
    title: str
    owner: str

@app.post("/api/items")
def add_item(body: ItemIn):
    c = connect()
    cur = c.execute("INSERT INTO items(title,owner,status,data_quality) VALUES (?,?,?,?)",
                    (body.title, body.owner, "available", "clean"))
    c.commit(); iid = cur.lastrowid; c.close(); return {"id": iid}

class LendIn(BaseModel):
    borrower: str
    due_date: str

@app.post("/api/items/{iid}/lend")
def lend(iid: int, body: LendIn):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        item = c.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
        if not item:
            raise HTTPException(404, "item")
        active = c.execute("SELECT COUNT(*) c FROM loans WHERE item_id=? AND status='active'", (iid,)).fetchone()["c"]
        held = c.execute("SELECT COUNT(*) c FROM holds WHERE item_id=? AND status='held'", (iid,)).fetchone()["c"]
        check = can_lend(item["status"], active, held)
        if not check["ok"]:
            raise HTTPException(409, check["reason"])
        cur = c.execute(
            "INSERT INTO loans(item_id,borrower,status,due_date,lent_at) VALUES (?,?,?,?,?)",
            (iid, body.borrower, "active", body.due_date, datetime.now(timezone.utc).isoformat()))
        c.execute("UPDATE items SET status='on_loan' WHERE id=?", (iid,))
        c.commit()
        lid = cur.lastrowid
        return {"loan_id": lid}
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

class HoldIn(BaseModel):
    borrower: str
    due_date: str
    qty: int = 1

@app.post("/api/items/{iid}/holds")
def create_hold(iid: int, body: HoldIn):
    try:
        hid = deposit.create_hold(iid, body.borrower, body.due_date, body.qty)
    except HoldError as e:
        raise _hold_http_error(e)
    return {"hold_id": hid}

@app.get("/api/holds")
def holds(open_only: bool = False):
    return deposit.list_holds(open_only=open_only)

@app.post("/api/holds/{hid}/confirm")
def confirm_hold(hid: int):
    try:
        loan_id = deposit.confirm_hold(hid)
    except HoldError as e:
        raise _hold_http_error(e)
    return {"loan_id": loan_id}

@app.post("/api/holds/{hid}/cancel")
def cancel_hold(hid: int):
    try:
        deposit.cancel_hold(hid)
    except HoldError as e:
        raise _hold_http_error(e)
    return {"ok": True}

@app.post("/api/loans/{lid}/return")
def return_loan(lid: int):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        loan = c.execute("SELECT * FROM loans WHERE id=?", (lid,)).fetchone()
        if not loan:
            raise HTTPException(404, "loan")
        if loan["status"] != "active":
            raise HTTPException(400, "not_active")
        c.execute("UPDATE loans SET status='returned', returned_at=? WHERE id=?",
                  (datetime.now(timezone.utc).isoformat(), lid))
        c.execute("UPDATE items SET status='available' WHERE id=?", (loan["item_id"],))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return {"ok": True}

@app.get("/api/loans")
def loans():
    c = connect()
    rows = [dict(r) for r in c.execute(
        "SELECT loans.*, items.title FROM loans JOIN items ON items.id=loans.item_id ORDER BY loans.id DESC")]
    c.close()
    return classify_loans(rows, date.today().isoformat())

@app.get("/api/settings")
def settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows
