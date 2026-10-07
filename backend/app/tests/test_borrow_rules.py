from app.engines.borrow_rules import can_lend, is_overdue, classify_loans

def test_mutex():
    assert can_lend("available", 0)["ok"]
    assert can_lend("available", 1)["reason"] == "already_on_loan"
    assert can_lend("retired", 0)["ok"] is False
    # 占用档同一套口径：pending 占用占住额度，直接借出失败
    assert can_lend("available", 0, 1)["reason"] == "occupied"

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
