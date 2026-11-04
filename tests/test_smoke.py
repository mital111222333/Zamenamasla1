"""Сайт целиком загружается, и важные защиты на месте. Ловит, например,
загрузку старой версии файла, которая молча откатила исправление."""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def app():
    import database as db
    db.init_db()
    import webapp
    webapp.app.config["TESTING"] = True
    return webapp.app


def test_site_imports_and_db_initialises(app):
    assert app is not None


@pytest.mark.parametrize("path", ["/login", "/register", "/app", "/privacy", "/privacy?lang=uz"])
def test_public_pages_open(app, path):
    r = app.test_client().get(path)
    assert r.status_code == 200, path


def test_panel_requires_login(app):
    r = app.test_client().get("/api/cars")
    assert r.status_code in (302, 401, 403)


@pytest.mark.parametrize("path", ["/admin", "/api/admin/shops", "/api/admin/restore_backup"])
def test_admin_routes_registered_and_closed(app, path):
    # маршруты админки вынесены в admin_routes.py — они должны быть подключены
    # и по-прежнему закрыты для всех, кто не вошёл администратором
    assert any(r.rule == path for r in app.url_map.iter_rules()), path
    r = app.test_client().get(path)
    assert r.status_code in (302, 401, 403, 405), path


def test_security_headers(app):
    r = app.test_client().get("/login")
    assert "frame-ancestors" in r.headers.get("Content-Security-Policy", "")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_cross_site_post_rejected(app):
    r = app.test_client().post("/api/add", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_oversized_upload_rejected(app):
    r = app.test_client().post("/api/products/import_preview", data=b"0" * (21 * 1024 * 1024))
    assert r.status_code == 413


# Защитные места кода: если чья-то правка или загрузка старого файла их
# удалит — тест упадёт и подскажет, что именно пропало.
GUARDS = {
    "webapp.py": [
        r"def _csrf_origin_check", r"def _security_headers", r"def _limit_request_size",
        r"db\.sanitize_items\(", r"_reset_request_limited\(", r"def _employee_record_guard",
        r"@employee_blocked\s+def api_delete_car", r"@employee_blocked\s+def api_sms_settings",
        r"islice\(ws\.iter_rows", r"backup_store\.is_encrypted",
        r"escapeHtml\(it\.qty\)",
        # разделы, вынесенные в отдельные файлы, должны быть подключены
        r"^import display\b", r"^import registration\b", r"^import subscription\b",
        r"^import admin_routes\b",
    ],
    "subscription.py": [r"own_ext and ext == own_ext"],
    "database.py": [r"def sanitize_items", r"def split_backup", r"def log_action"],
    "bot.py": [r"backup_store\.to_gdrive", r"db\.split_backup"],
}


@pytest.mark.parametrize("fname,pattern", [(f, p) for f, ps in GUARDS.items() for p in ps])
def test_security_guards_present(fname, pattern):
    src = open(os.path.join(ROOT, fname), encoding="utf-8").read()
    assert re.search(pattern, src, re.M), f"{fname}: пропала защита /{pattern}/"
