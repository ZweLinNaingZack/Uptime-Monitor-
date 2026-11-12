"""The /monitors endpoints, with fake checks so results are predictable."""

import ipaddress

from app import url_safety

from .conftest import down, up


def create(client, **kw):
    body = {"name": "Example", "url": "https://example.com/", "intervalSeconds": 60} | kw
    return client.post("/monitors", json=body)


def test_create_list_get_delete(logged_in, scheduled):
    response = create(logged_in)
    assert response.status_code == 201
    monitor = response.json()
    assert monitor["latestCheck"] is None and monitor["isActive"] and not monitor["inMaintenance"]
    assert scheduled == [monitor["id"]]  # its first check is scheduled straight away

    assert [m["id"] for m in logged_in.get("/monitors").json()] == [monitor["id"]]
    assert logged_in.get(f"/monitors/{monitor['id']}").json()["name"] == "Example"
    assert logged_in.delete(f"/monitors/{monitor['id']}").status_code == 204
    assert logged_in.get(f"/monitors/{monitor['id']}").status_code == 404


def test_invalid_input_is_rejected(logged_in):
    assert create(logged_in, name="").status_code == 422
    assert create(logged_in, url="not a url").status_code == 422
    assert create(logged_in, intervalSeconds=5).status_code == 422
    assert create(logged_in, unknownField=1).status_code == 422


def test_private_urls_are_refused_when_created(logged_in, monkeypatch):
    monkeypatch.setattr(url_safety, "_resolve_host", lambda h, p: [ipaddress.ip_address("192.168.1.1")])
    response = create(logged_in, url="https://router.example/")
    assert response.status_code == 400 and "private" in response.json()["detail"]


def test_check_now_records_a_check(logged_in, checker):
    monitor_id = create(logged_in).json()["id"]
    checker.then(down(503))
    check = logged_in.post(f"/monitors/{monitor_id}/check").json()
    assert (check["isUp"], check["statusCode"]) == (False, 503)
    assert logged_in.get(f"/monitors/{monitor_id}").json()["latestCheck"]["id"] == check["id"]
    assert len(logged_in.get(f"/monitors/{monitor_id}/checks").json()) == 1


def test_stats_leave_out_maintenance(logged_in, checker):
    monitor_id = create(logged_in).json()["id"]
    checker.then(up(), down())
    logged_in.post(f"/monitors/{monitor_id}/check")
    logged_in.patch(f"/monitors/{monitor_id}", json={"inMaintenance": True})
    logged_in.post(f"/monitors/{monitor_id}/check")
    stats = logged_in.get(f"/monitors/{monitor_id}/stats?hours=24").json()
    assert (stats["totalChecks"], stats["uptimePercent"]) == (1, 100.0)
    history = logged_in.get(f"/monitors/{monitor_id}/checks").json()
    assert [c["duringMaintenance"] for c in history] == [True, False]


def test_patch_needs_at_least_one_field(logged_in):
    monitor_id = create(logged_in).json()["id"]
    assert logged_in.patch(f"/monitors/{monitor_id}", json={}).status_code == 422
    assert logged_in.patch(f"/monitors/{monitor_id}", json={"isActive": False}).json()["isActive"] is False


def test_down_alert_waits_for_two_failures(logged_in, checker, sent):
    logged_in.put("/alerts/channels/discord", json={"webhookUrl": "https://discord.com/api/webhooks/1/abc"})
    monitor_id = create(logged_in).json()["id"]

    def check(result):
        checker.then(result)
        logged_in.post(f"/monitors/{monitor_id}/check")

    check(down())
    assert logged_in.get("/alerts").json() == []
    check(down())
    assert [a["kind"] for a in logged_in.get("/alerts").json()] == ["down"]
    check(down())
    check(up())
    assert [a["kind"] for a in logged_in.get("/alerts").json()] == ["recovered", "down"]


def test_check_now_has_a_rate_limit(logged_in):
    monitor_id = create(logged_in).json()["id"]
    codes = [logged_in.post(f"/monitors/{monitor_id}/check").status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
