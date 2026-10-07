from datetime import date, datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect, tx
from app.engines.borrow_rules import can_lend, classify_loans
from app.engines.occupancy_rules import can_confirm, can_open_occupancy

app = FastAPI(title="Borrowboard", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

@app.get("/api/health")
def health(): return {"ok": True, "project": "borrowboard"}

@app.get("/api/items")
def items():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM items")]; c.close(); return rows

def _counts(c, item_id: int) -> tuple[int, int]:
    active = c.execute("SELECT COUNT(*) c FROM loans WHERE item_id=? AND status='active'", (item_id,)).fetchone()["c"]
    pending = c.execute("SELECT COUNT(*) c FROM occupancies WHERE item_id=? AND status='pending'", (item_id,)).fetchone()["c"]
    return active, pending

@app.get("/api/board")
def board():
    c = connect()
    available = [dict(r) for r in c.execute("SELECT * FROM items WHERE status='available'")]
    pendings = [dict(r) for r in c.execute("SELECT * FROM occupancies WHERE status='pending'")]
    by_item = {o["item_id"]: o for o in pendings}
    # 预览口径：占用未确认前物品仍停在可借栏，仅标注占用信息，不产生 loans 行
    for i in available:
        i["occupancy"] = by_item.get(i["id"])
    loans = [dict(r) for r in c.execute(
        """SELECT loans.*, items.title FROM loans JOIN items ON items.id=loans.item_id
           WHERE loans.status='active'""")]
    c.close()
    cls = classify_loans(loans, date.today().isoformat())
    return {
        "available": available,
        "active": cls["active"],
        "overdue": cls["overdue"],
        "counts": {"available": len(available), "active": len(cls["active"]),
                   "overdue": len(cls["overdue"]), "occupied": len(pendings)},
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
    with tx() as c:
        item = c.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
        if not item: raise HTTPException(404, "item")
        active, pending = _counts(c, iid)
        check = can_lend(item["status"], active, pending)
        if not check["ok"]:
            raise HTTPException(409, check["reason"])
        cur = c.execute(
            "INSERT INTO loans(item_id,borrower,status,due_date,lent_at) VALUES (?,?,?,?,?)",
            (iid, body.borrower, "active", body.due_date, datetime.now(timezone.utc).isoformat()))
        c.execute("UPDATE items SET status='on_loan' WHERE id=?", (iid,))
        return {"loan_id": cur.lastrowid}

class OccupancyIn(BaseModel):
    borrower: str
    due_date: str
    qty: int = 1

@app.post("/api/items/{iid}/occupancy")
def open_occupancy(iid: int, body: OccupancyIn):
    """借出通过前先开占用档：只落 pending 占用，物品仍 available、loans 不增行。"""
    with tx() as c:
        item = c.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
        if not item: raise HTTPException(404, "item")
        active, pending = _counts(c, iid)
        check = can_open_occupancy(item["status"], active, pending)
        if not check["ok"]:
            raise HTTPException(409, check["reason"])
        cur = c.execute(
            "INSERT INTO occupancies(item_id,borrower,qty,due_date,status,created_at) VALUES (?,?,?,?,?,?)",
            (iid, body.borrower, body.qty, body.due_date, "pending", datetime.now(timezone.utc).isoformat()))
        return {"occupancy_id": cur.lastrowid}

@app.get("/api/occupancies")
def occupancies():
    c = connect()
    rows = [dict(r) for r in c.execute(
        """SELECT occupancies.*, items.title FROM occupancies
           JOIN items ON items.id=occupancies.item_id ORDER BY occupancies.id DESC""")]
    c.close()
    return {
        "pending": [r for r in rows if r["status"] == "pending"],
        "confirmed": [r for r in rows if r["status"] == "confirmed"],
    }

@app.post("/api/occupancies/{oid}/confirm")
def confirm_occupancy(oid: int):
    """确认=原子落地：占用档置 confirmed + 落一笔在借行 + 物品置 on_loan，
    任一校验不过则整体回滚，占用档与可借栏一起回到确认前。"""
    with tx() as c:
        occ = c.execute("SELECT * FROM occupancies WHERE id=?", (oid,)).fetchone()
        if not occ: raise HTTPException(404, "occupancy")
        item = c.execute("SELECT * FROM items WHERE id=?", (occ["item_id"],)).fetchone()
        if not item: raise HTTPException(404, "item")
        active, _ = _counts(c, occ["item_id"])
        check = can_confirm(occ["status"], occ["qty"], item["status"], active, item["data_quality"])
        if not check["ok"]:
            raise HTTPException(409, check["reason"])
        now = datetime.now(timezone.utc).isoformat()
        cur = c.execute(
            "INSERT INTO loans(item_id,borrower,status,due_date,lent_at) VALUES (?,?,?,?,?)",
            (occ["item_id"], occ["borrower"], "active", occ["due_date"], now))
        c.execute("UPDATE items SET status='on_loan' WHERE id=?", (occ["item_id"],))
        c.execute("UPDATE occupancies SET status='confirmed', confirmed_at=?, loan_id=? WHERE id=?",
                  (now, cur.lastrowid, oid))
        return {"loan_id": cur.lastrowid}

@app.post("/api/loans/{lid}/return")
def return_loan(lid: int):
    with tx() as c:
        loan = c.execute("SELECT * FROM loans WHERE id=?", (lid,)).fetchone()
        if not loan: raise HTTPException(404, "loan")
        if loan["status"] != "active":
            raise HTTPException(400, "not_active")
        c.execute("UPDATE loans SET status='returned', returned_at=? WHERE id=?",
                  (datetime.now(timezone.utc).isoformat(), lid))
        c.execute("UPDATE items SET status='available' WHERE id=?", (loan["item_id"],))
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
