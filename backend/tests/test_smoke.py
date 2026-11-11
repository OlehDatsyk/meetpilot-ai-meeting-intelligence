from conftest import Account


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["database"] == "ok"


def test_register_and_dashboard(client):
    a = Account(client, "smoke@example.com")
    r = a.get(f"/api/v1/dashboard?workspace_id={a.workspace_id}")
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["total_meetings"] == 0
