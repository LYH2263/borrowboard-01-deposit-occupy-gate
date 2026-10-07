import pytest
from fastapi.testclient import TestClient
from app.main import app

# 种子：1 电钻(clean) 2 折叠桌(clean) 3 脏数据-无主(dirty) 4 已外借样例(on_loan, loan#1 active)

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with TestClient(app) as c:
        yield c

def open_occ(client, iid=1, **kw):
    body = {"borrower": "邻居乙", "due_date": "2026-12-31", "qty": 1}
    body.update(kw)
    return client.post(f"/api/items/{iid}/occupancy", json=body)

def test_preview_keeps_item_available_and_no_loan_row(client):
    before = client.get("/api/loans").json()
    r = open_occ(client, 1, qty=2)
    assert r.status_code == 200
    b = client.get("/api/board").json()
    drill = next(i for i in b["available"] if i["title"] == "电钻")
    assert drill["status"] == "available" and drill["occupancy"]["status"] == "pending"
    assert b["counts"]["occupied"] == 1
    after = client.get("/api/loans").json()
    # loans 不增行
    assert after == before

def test_pending_occupancy_blocks_parallel_paths(client):
    assert open_occ(client, 1).status_code == 200
    # 另一人直接借出通过 → 失败（占住算法）
    r = client.post("/api/items/1/lend", json={"borrower": "邻居丙", "due_date": "2026-12-31"})
    assert r.status_code == 409 and r.json()["detail"] == "occupied"
    # 再开一份占用 → 失败
    assert open_occ(client, 1).status_code == 409
    # 别件不受影响
    assert open_occ(client, 2).status_code == 200

def test_confirm_lands_single_status_and_loan_row(client):
    oid = open_occ(client, 1).json()["occupancy_id"]
    r = client.post(f"/api/occupancies/{oid}/confirm")
    assert r.status_code == 200
    lid = r.json()["loan_id"]
    b = client.get("/api/board").json()
    assert all(i["id"] != 1 for i in b["available"])
    active = [l for l in b["active"] if l["item_id"] == 1]
    assert len(active) == 1 and active[0]["id"] == lid and active[0]["borrower"] == "邻居乙"
    # 借还记录与看板对上同一笔
    loans = client.get("/api/loans").json()
    assert [l["id"] for l in loans["active"] if l["item_id"] == 1] == [lid]
    items = {i["id"]: i for i in client.get("/api/items").json()}
    assert items[1]["status"] == "on_loan"
    # 确认后占用档不再 pending；重复确认失败
    occs = client.get("/api/occupancies").json()
    assert occs["pending"] == [] and occs["confirmed"][0]["loan_id"] == lid
    assert client.post(f"/api/occupancies/{oid}/confirm").status_code == 409
    # 在借中直接借出也失败：同一件只剩一种 status 与一笔在借行
    assert client.post("/api/items/1/lend",
                       json={"borrower": "x", "due_date": "2026-01-01"}).status_code == 409
    # 归还后回到可借
    assert client.post(f"/api/loans/{lid}/return").status_code == 200
    items = {i["id"]: i for i in client.get("/api/items").json()}
    assert items[1]["status"] == "available"

def test_bad_qty_confirm_fails_and_reverts(client):
    oid = open_occ(client, 1, qty=0).json()["occupancy_id"]
    r = client.post(f"/api/occupancies/{oid}/confirm")
    assert r.status_code == 409 and r.json()["detail"] == "bad_qty"
    # 失败路径：占用档仍 pending、可借栏仍有电钻、loans 不增行
    occs = client.get("/api/occupancies").json()
    assert [o["id"] for o in occs["pending"]] == [oid]
    b = client.get("/api/board").json()
    assert any(i["id"] == 1 for i in b["available"])
    assert all(l["item_id"] != 1 for l in client.get("/api/loans").json()["active"])

def test_dirty_item_confirm_fails_and_stays_dirty(client):
    oid = open_occ(client, 3).json()["occupancy_id"]
    r = client.post(f"/api/occupancies/{oid}/confirm")
    assert r.status_code == 409 and r.json()["detail"] == "dirty_item"
    item = next(i for i in client.get("/api/items").json() if i["id"] == 3)
    # 脏数据-无主不得被确认改成 clean，状态也不动
    assert item["data_quality"] == "dirty" and item["status"] == "available"

def test_open_occupancy_rejects_unavailable(client):
    r = open_occ(client, 4)  # 已外借样例 on_loan
    assert r.status_code == 409 and r.json()["detail"] == "item_not_available"
    assert open_occ(client, 999).status_code == 404
