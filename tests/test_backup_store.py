"""Резервные копии: шифрование и очистка Google Диска (без сети)."""
import gzip
import os
from datetime import datetime, timedelta, timezone

import pytest

import backup_store as bs


def _roundtrip(tmp_path, data, monkeypatch, chunk=None):
    if chunk:
        monkeypatch.setattr(bs, "CHUNK", chunk)
    src, dst = tmp_path / "b.db.gz", tmp_path / "b.db.gz.enc"
    src.write_bytes(data)
    bs.encrypt_file(str(src), str(dst), "верный пароль")
    enc = dst.read_bytes()
    assert bs.is_encrypted(enc) and (not data or data[:50] not in enc)
    return enc


@pytest.mark.parametrize("size,chunk", [(0, None), (100, None), (1000, 100), (1050, 100), (5, 4)])
def test_encrypt_decrypt_roundtrip(tmp_path, monkeypatch, size, chunk):
    data = os.urandom(size)
    enc = _roundtrip(tmp_path, data, monkeypatch, chunk)
    assert bs.decrypt_bytes(enc, "верный пароль") == data


def test_wrong_password_rejected(tmp_path, monkeypatch):
    enc = _roundtrip(tmp_path, gzip.compress(b"x" * 1000), monkeypatch)
    with pytest.raises(ValueError):
        bs.decrypt_bytes(enc, "чужой пароль")


def test_truncated_file_rejected(tmp_path, monkeypatch):
    enc = _roundtrip(tmp_path, os.urandom(1000), monkeypatch, chunk=100)
    # обрезка ровно по границе фрагмента — «последний» фрагмент не тот
    cut = len(bs.MAGIC) + 16 + (4 + 12 + 100 + 16) * 5
    with pytest.raises(ValueError):
        bs.decrypt_bytes(enc[:cut], "верный пароль")


def test_missing_server_password(tmp_path, monkeypatch):
    enc = _roundtrip(tmp_path, b"data", monkeypatch)
    with pytest.raises(ValueError):
        bs.decrypt_bytes(enc, "")


def test_prepare_without_password_keeps_file(tmp_path, monkeypatch):
    monkeypatch.delenv("BACKUP_PASSWORD", raising=False)
    p = tmp_path / "a.db.gz"
    p.write_bytes(b"abc")
    assert bs.prepare(str(p), "a.db.gz") == (str(p), "a.db.gz", False)


def test_prepare_with_password_encrypts(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_PASSWORD", "секрет")
    p = tmp_path / "a.db.gz"
    p.write_bytes(b"abc" * 100)
    path, name, enc = bs.prepare(str(p), "a.db.gz")
    assert enc and name == "a.db.gz.enc" and path.endswith(".enc")
    assert bs.decrypt_bytes(open(path, "rb").read(), "секрет") == b"abc" * 100


def _files(days_ago_list, now):
    return [{"id": str(i), "name": f"b{i}", "createdTime": (now - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
            for i, d in enumerate(days_ago_list)]


def test_retention_deletes_only_older_than_30_days():
    now = datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc)
    files = _files(range(0, 45), now)  # копия каждый день 45 дней
    old = bs.select_old(files, 30, now)
    assert sorted(int(f["id"]) for f in old) == list(range(31, 45))


def test_retention_keeps_30_newest_even_if_old():
    now = datetime(2026, 11, 3, tzinfo=timezone.utc)
    files = _files([40 + d for d in range(35)], now)  # сервер долго не делал копий
    old = bs.select_old(files, 30, now)
    assert len(old) == 5  # 30 самых свежих остаются, хоть им и > 30 дней


def test_gdrive_disabled_without_env(monkeypatch):
    for k in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert bs.to_gdrive("x", "y") == (None, None)
