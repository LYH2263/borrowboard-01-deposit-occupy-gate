"""One active loan per item + overdue detection + hold policy.

占用档策略（钉死）：未确认占用即占住该物的可借额度（RESERVES_CAPACITY=True）。
占用期间物品仍是 available（停在可借栏）、loans 不增行，但任何人再开占用或
直接借出都失败；只有确认（生成唯一在借行、物品转 on_loan）或取消（释放额度）
才能改变状态。所有入口共用这一套判定，禁止一处占额度、另一处又能借出成功。
"""

# 钉死的唯一策略：未确认占用占住可借额度。
RESERVES_CAPACITY = True


def can_hold(item: dict, active_holds: int) -> dict:
    """开占用前校验：必须是有主、可借、且没有在借/未确认占用的物品。"""
    if not (item.get("owner") or "").strip():
        return {"ok": False, "reason": "ownerless_item"}
    if item.get("status") != "available":
        return {"ok": False, "reason": "item_not_available"}
    if active_holds > 0:
        # 占用即占住额度：已有未确认占用时拒绝并行占用。
        return {"ok": False, "reason": "already_held"}
    return {"ok": True, "reason": ""}


def can_confirm_hold(item: dict, qty: int) -> dict:
    """确认占用前校验：物品仍有主且可借，占用数量为正整数。"""
    if not (item.get("owner") or "").strip():
        return {"ok": False, "reason": "ownerless_item"}
    if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
        return {"ok": False, "reason": "invalid_quantity"}
    if item.get("status") != "available":
        return {"ok": False, "reason": "item_not_available"}
    return {"ok": True, "reason": ""}


def can_lend(item_status: str, active_loans: int, active_holds: int = 0) -> dict:
    if item_status != "available":
        return {"ok": False, "reason": "item_not_available"}
    if active_holds > 0:
        # 占用占住额度：直接借出遇未确认占用必须失败，杜绝双活。
        return {"ok": False, "reason": "item_held"}
    if active_loans > 0:
        return {"ok": False, "reason": "already_on_loan"}
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
