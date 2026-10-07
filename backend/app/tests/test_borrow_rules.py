from app.engines.borrow_rules import (
    can_confirm_hold, can_hold, can_lend, classify_loans, is_overdue,
)

def test_mutex():
    assert can_lend("available", 0)["ok"]
    assert can_lend("available", 1)["reason"] == "already_on_loan"
    assert can_lend("retired", 0)["ok"] is False

def test_hold_reserves_capacity():
    # 钉死策略：未确认占用占住可借额度，直接借出必须失败。
    assert can_lend("available", 0, active_holds=1)["reason"] == "item_held"
    assert can_lend("available", 0, active_holds=0)["ok"]

def test_can_hold():
    drill = {"status": "available", "owner": "老周"}
    assert can_hold(drill, 0)["ok"]
    assert can_hold(drill, 1)["reason"] == "already_held"
    assert can_hold({"status": "on_loan", "owner": "老周"}, 0)["ok"] is False
    # 无主物品不得占用。
    assert can_hold({"status": "available", "owner": ""}, 0)["reason"] == "ownerless_item"
    assert can_hold({"status": "available", "owner": "   "}, 0)["reason"] == "ownerless_item"

def test_can_confirm_hold():
    drill = {"status": "available", "owner": "老周"}
    assert can_confirm_hold(drill, 1)["ok"]
    assert can_confirm_hold(drill, 2)["ok"]
    # 占用数量非正 -> 确认失败。
    assert can_confirm_hold(drill, 0)["reason"] == "invalid_quantity"
    assert can_confirm_hold(drill, -3)["reason"] == "invalid_quantity"
    # 确认时若已变成无主/非可借，同样失败。
    assert can_confirm_hold({"status": "available", "owner": ""}, 1)["reason"] == "ownerless_item"
    assert can_confirm_hold({"status": "on_loan", "owner": "老周"}, 1)["reason"] == "item_not_available"

def test_overdue():
    assert is_overdue("2020-01-01", "2026-01-01", "active")
    assert not is_overdue("2020-01-01", "2026-01-01", "returned")

def test_classify():
    r = classify_loans([
        {"id": 1, "status": "active", "due_date": "2020-01-01"},
        {"id": 2, "status": "active", "due_date": "2099-01-01"},
        {"id": 3, "status": "returned", "due_date": "2020-01-01"},
    ], "2026-01-01")
    assert len(r["overdue"]) == 1 and len(r["active"]) == 1 and len(r["returned"]) == 1
