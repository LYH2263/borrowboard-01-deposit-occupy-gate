"""占用档规则。

钉死的算法（两种里只准交付这一套，全库唯一口径）：
    未确认(pending)占用 == 已占住该物的可借额度。
    - 同一件物品存在 pending 占用时：直接借出、再开占用一律拒绝（409 occupied）；
    - 可借栏仍列出该物、loans 不增行（确认前不产生借出事实），但额度已被占住；
    - 确认通过才落 loans 行并把物品置 on_loan；确认失败一切回到确认前。
禁止一处占额度、另一处又能借出成功的双活：lend / occupancy / confirm
全部只调本模块与 borrow_rules.can_lend 的同一套判断。
"""

# True  = 占住：pending 占用即锁定可借额度（本仓库钉死这一套）
# False = 不占住：允许并行直到确认（禁止切到这一侧，会与现有调用方形成双活）
PENDING_HOLDS_QUOTA = True


def can_open_occupancy(item_status: str, active_loans: int, pending_occupancies: int) -> dict:
    if item_status != "available":
        return {"ok": False, "reason": "item_not_available"}
    if active_loans > 0:
        return {"ok": False, "reason": "already_on_loan"}
    if PENDING_HOLDS_QUOTA and pending_occupancies > 0:
        return {"ok": False, "reason": "occupied"}
    return {"ok": True, "reason": ""}


def can_confirm(occ_status: str, qty, item_status: str, active_loans: int, data_quality: str) -> dict:
    """确认前置校验；任一不过则整单不落地（占用档与可借栏保持确认前）。"""
    if occ_status != "pending":
        return {"ok": False, "reason": "not_pending"}
    # 占用数量非正（或不是整数）则确认失败
    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
        return {"ok": False, "reason": "bad_qty"}
    # 脏数据不得被确认洗成 clean：直接拒绝，data_quality 保持原样
    if data_quality != "clean":
        return {"ok": False, "reason": "dirty_item"}
    if item_status != "available":
        return {"ok": False, "reason": "item_not_available"}
    if active_loans > 0:
        return {"ok": False, "reason": "already_on_loan"}
    return {"ok": True, "reason": ""}
