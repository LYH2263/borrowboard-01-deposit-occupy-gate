"""One active loan per item + overdue detection."""
from app.engines.occupancy_rules import PENDING_HOLDS_QUOTA

def can_lend(item_status: str, active_loans: int, pending_occupancies: int = 0) -> dict:
    if item_status != "available":
        return {"ok": False, "reason": "item_not_available"}
    if active_loans > 0:
        return {"ok": False, "reason": "already_on_loan"}
    # 与占用档同一套口径：pending 占用占住额度时，直接借出必须失败
    if PENDING_HOLDS_QUOTA and pending_occupancies > 0:
        return {"ok": False, "reason": "occupied"}
    return {"ok": True, "reason": ""}

def is_overdue(due_date: str, today: str, loan_status: str) -> bool:
    if loan_status != "active":
        return False
    return bool(due_date) and due_date < today

def classify_loans(loans: list[dict], today: str) -> dict:
    active, overdue, returned = [], [], []
    for L in loans:
        st = L.get("status")
        if st == "returned":
            returned.append(L)
        elif is_overdue(L.get("due_date"), today, st):
            overdue.append({**L, "overdue": True})
        elif st == "active":
            active.append({**L, "overdue": False})
    return {"active": active, "overdue": overdue, "returned": returned}
