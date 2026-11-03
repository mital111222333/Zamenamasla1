"""Тесты запускаются на временной пустой базе — живые данные не трогаются."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(prefix="oilbook_test_"), "test.db"))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST")
