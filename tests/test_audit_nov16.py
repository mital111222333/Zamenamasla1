"""Проверка 16.11.2026: найденные при полной проверке слабые места закрыты."""
import pytest

import database as db
import security

PW = "Zx9-mountain-oil"


@pytest.fixture(scope="module")
def app():
    import webapp
    db.init_db()
    webapp.app.config["TESTING"] = True
    return webapp.app


@pytest.fixture()
def client(app):
    security.rate_reset()
    shop = db.find_shop_by_username("audit16") or db.create_shop("audit16", PW, shop_name="Audit16")
    db.reset_shop_password(shop["id"], PW)
    c = app.test_client()
    assert c.post("/login", data={"username": "audit16", "password": PW}).status_code in (302, 303)
    return c


def _entry(**over):
    body = {"plate": "70A116AA", "owner_name": "Тест", "mileage": 50000, "next_mileage": 58000,
            "items": [{"key": "fluid_0", "name": "Масло", "qty": 4, "unit_price": 50000, "total": 200000}],
            "interval_value": 3, "interval_unit": "months", "cash_amount": 200000}
    body.update(over)
    return body


@pytest.mark.parametrize("body", [[1, 2, 3], "строка", 5])
@pytest.mark.parametrize("path", ["/api/day_close", "/api/usd_rate", "/api/queue", "/api/used_oil/pct",
                                  "/api/team/settings", "/api/store/move"])
def test_non_object_body_is_refused_not_crashed(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 400, (path, r.status_code)


def test_negative_mileage_refused(client):
    r = client.post("/api/add", json=_entry(mileage=-5, token="a16-neg"))
    assert r.status_code == 400
    r = client.post("/api/add", json=_entry(next_mileage=10 ** 9, token="a16-big"))
    assert r.status_code == 400


def test_garbage_plate_refused(client):
    r = client.post("/api/add", json=_entry(plate="<script>alert(1)</script>" * 3, token="a16-plate"))
    assert r.status_code == 400


def test_normal_entry_still_saves_and_edit_checks_mileage(client):
    r = client.post("/api/add", json=_entry(token="a16-ok"))
    assert r.status_code == 200 and r.get_json()["ok"]
    oc_id = r.get_json()["oc_id"]
    assert client.put(f"/api/oil_change/{oc_id}", json={"mileage": -1}).status_code == 400
    assert client.put(f"/api/oil_change/{oc_id}", json={"mileage": 51000}).status_code == 200


def test_client_ip_behind_cloudflare(app, monkeypatch):
    import webapp
    headers = {"X-Forwarded-For": "1.2.3.4, 104.22.17.40", "CF-Connecting-IP": "1.2.3.4"}
    # на Render настоящий адрес клиента — из CF-Connecting-IP
    monkeypatch.setenv("RENDER", "true")
    with app.test_request_context("/login", headers=headers):
        assert webapp._client_ip() == "1.2.3.4"
    # мусор в заголовке не принимаем
    with app.test_request_context("/login", headers={**headers, "CF-Connecting-IP": "<x>"}):
        assert webapp._client_ip() == "104.22.17.40"
    # на другом хостинге заголовку не верим — его мог прислать кто угодно
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("TRUST_CF_CONNECTING_IP", raising=False)
    with app.test_request_context("/login", headers=headers):
        assert webapp._client_ip() == "104.22.17.40"


def test_admin_names_bad_items_do_not_crash():
    assert db.save_name_aliases([1, "x", None]) == 0
