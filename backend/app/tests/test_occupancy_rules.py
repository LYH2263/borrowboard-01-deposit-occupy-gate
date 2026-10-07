from app.engines.borrow_rules import can_lend
from app.engines.occupancy_rules import PENDING_HOLDS_QUOTA, can_confirm, can_open_occupancy

def test_algorithm_pinned():
    # 钉死：未确认占用占住可借额度。翻成 False 即另一套算法，禁止双活并存。
    assert PENDING_HOLDS_QUOTA is True

def test_open_occupancy():
    assert can_open_occupancy("available", 0, 0)["ok"]
    assert can_open_occupancy("available", 0, 1)["reason"] == "occupied"
    assert can_open_occupancy("available", 1, 0)["reason"] == "already_on_loan"
    assert can_open_occupancy("on_loan", 0, 0)["reason"] == "item_not_available"

def test_pending_occupancy_blocks_direct_lend():
    assert can_lend("available", 0, 0)["ok"]
    assert can_lend("available", 0, 1)["reason"] == "occupied"

def test_confirm_qty_must_be_positive():
    for bad in (0, -1, -99, None, "2", 1.5, True):
        assert can_confirm("pending", bad, "available", 0, "clean")["reason"] == "bad_qty"
    assert can_confirm("pending", 1, "available", 0, "clean")["ok"]
    assert can_confirm("pending", 5, "available", 0, "clean")["ok"]

def test_confirm_rejects_dirty_item():
    r = can_confirm("pending", 1, "available", 0, "dirty")
    assert not r["ok"] and r["reason"] == "dirty_item"

def test_confirm_requires_pending_and_available():
    assert can_confirm("confirmed", 1, "available", 0, "clean")["reason"] == "not_pending"
    assert can_confirm("pending", 1, "on_loan", 0, "clean")["reason"] == "item_not_available"
    assert can_confirm("pending", 1, "available", 1, "clean")["reason"] == "already_on_loan"
