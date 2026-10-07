import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def _active_loans(client, iid):
    rows = [l for l in client.get("/api/loans").json()["active"]
            if l["item_id"] == iid]
    return rows


def test_hold_preview_keeps_item_available_without_loan(client):
    board = client.get("/api/board").json()
    drill = next(i for i in board["available"] if i["title"] == "电钻")
    assert not drill.get("held")
    assert board["counts"]["held"] == 0

    r = client.post(f"/api/items/{drill['id']}/holds",
                    json={"borrower": "邻居乙", "due_date": "2026-12-31", "qty": 1})
    assert r.status_code == 200
    hid = r.json()["hold_id"]

    board = client.get("/api/board").json()
    drill = next(i for i in board["available"] if i["title"] == "电钻")
    # 预览时电钻仍停在可借栏，但带上占用标记，占用计数 +1。
    assert drill["held"] and drill["hold_id"] == hid and drill["held_by"] == "邻居乙"
    assert board["counts"]["held"] == 1
    # loans 不增行。
    assert _active_loans(client, drill["id"]) == []


def test_hold_blocks_parallel_lend_and_second_hold(client):
    iid = client.get("/api/items").json()[0]["id"]
    assert client.post(f"/api/items/{iid}/holds",
                       json={"borrower": "邻居乙", "due_date": "2026-12-31"}).status_code == 200
    # 另一人直接借出必须失败（占住额度，禁止双活）。
    r = client.post(f"/api/items/{iid}/lend",
                    json={"borrower": "邻居丙", "due_date": "2026-12-31"})
    assert r.status_code == 409 and r.json()["detail"] == "item_held"
    # 并行再开占用同样失败。
    r = client.post(f"/api/items/{iid}/holds",
                    json={"borrower": "邻居丙", "due_date": "2026-12-31"})
    assert r.status_code == 409 and r.json()["detail"] == "already_held"
    # 失败后物品仍 available 且无在借行。
    assert client.get("/api/items").json()[0]["status"] == "available"
    assert _active_loans(client, iid) == []


def test_ownerless_item_cannot_be_held(client):
    items = client.get("/api/items").json()
    ownerless = next(i for i in items if i["title"] == "脏数据-无主")
    # 种子脏数据已改 clean；无主由规则拦截而非数据标记。
    assert ownerless["data_quality"] == "clean"
    r = client.post(f"/api/items/{ownerless['id']}/holds",
                    json={"borrower": "邻居乙", "due_date": "2026-12-31"})
    assert r.status_code == 409 and r.json()["detail"] == "ownerless_item"


def test_invalid_quantity_confirm_rolls_back(client):
    items = client.get("/api/items").json()
    table = next(i for i in items if i["title"] == "折叠桌")
    hid = client.post(f"/api/items/{table['id']}/holds",
                      json={"borrower": "邻居乙", "due_date": "2026-12-31", "qty": 0}).json()["hold_id"]
    # 占用数量非正 -> 确认失败。
    r = client.post(f"/api/holds/{hid}/confirm", json={})
    assert r.status_code == 400 and r.json()["detail"] == "invalid_quantity"
    # 失败路径：占用档与可借栏一起回到确认前。
    h = next(h for h in client.get("/api/holds").json() if h["id"] == hid)
    assert h["status"] == "held" and h["loan_id"] is None
    table = next(i for i in client.get("/api/items").json() if i["title"] == "折叠桌")
    assert table["status"] == "available"
    assert _active_loans(client, table["id"]) == []
    # 取消后额度释放，可直接借出。
    assert client.post(f"/api/holds/{hid}/cancel", json={}).status_code == 200
    assert client.post(f"/api/items/{table['id']}/lend",
                       json={"borrower": "邻居丁", "due_date": "2026-12-31"}).status_code == 200


def test_confirm_creates_single_loan_then_return_releases(client):
    items = client.get("/api/items").json()
    drill = next(i for i in items if i["title"] == "电钻")
    hid = client.post(f"/api/items/{drill['id']}/holds",
                      json={"borrower": "邻居乙", "due_date": "2026-12-31", "qty": 2}).json()["hold_id"]
    r = client.post(f"/api/holds/{hid}/confirm", json={})
    assert r.status_code == 200
    loan_id = r.json()["loan_id"]

    # 同一件只留下一种 items.status 与一条在借行。
    drill = next(i for i in client.get("/api/items").json() if i["title"] == "电钻")
    assert drill["status"] == "on_loan"
    active = _active_loans(client, drill["id"])
    assert len(active) == 1 and active[0]["id"] == loan_id and active[0]["borrower"] == "邻居乙"
    h = next(h for h in client.get("/api/holds").json() if h["id"] == hid)
    # 占用档与借据对上同一笔。
    assert h["status"] == "confirmed" and h["loan_id"] == loan_id
    board = client.get("/api/board").json()
    assert all(i["id"] != drill["id"] for i in board["available"])
    assert any(l["id"] == loan_id for l in board["active"])
    # 确认后不能再借出形成双活。
    assert client.post(f"/api/items/{drill['id']}/lend",
                       json={"borrower": "邻居丙", "due_date": "2026-12-31"}).status_code == 409
    # 归还打到同一件后回到可借，占用计数归零，可再开占用。
    assert client.post(f"/api/loans/{loan_id}/return", json={}).status_code == 200
    drill = next(i for i in client.get("/api/items").json() if i["title"] == "电钻")
    assert drill["status"] == "available"
    assert client.get("/api/board").json()["counts"]["held"] == 0
    assert client.post(f"/api/items/{drill['id']}/holds",
                       json={"borrower": "邻居戊", "due_date": "2026-12-31"}).status_code == 200


def test_cancel_releases_capacity(client):
    iid = client.get("/api/items").json()[0]["id"]
    hid = client.post(f"/api/items/{iid}/holds",
                      json={"borrower": "邻居乙", "due_date": "2026-12-31"}).json()["hold_id"]
    assert client.post(f"/api/holds/{hid}/cancel", json={}).status_code == 200
    assert client.get("/api/board").json()["counts"]["held"] == 0
    assert client.post(f"/api/items/{iid}/lend",
                       json={"borrower": "邻居乙", "due_date": "2026-12-31"}).status_code == 200
