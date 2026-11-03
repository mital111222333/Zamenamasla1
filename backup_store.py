"""Резервные копии базы: шифрование паролем и хранение в Google Диске.

Копия уходит в два места — Telegram (как раньше) и Google Диск, — чтобы
потеря одного не оставила без копий. Если задан BACKUP_PASSWORD, копия
шифруется (AES-256-GCM, ключ из пароля через scrypt): даже получив файл,
без пароля его не прочитать — а в нём имена и телефоны клиентов всех точек.

В Google Диске копии лежат в папке «OilBook — резервные копии». Хранятся
BACKUP_KEEP_DAYS дней (по умолчанию 30); более старые удаляются сами, но
самые свежие BACKUP_KEEP_DAYS копий не трогаем никогда — если копии какое-то
время не делались, без них не останемся. Доступ к Диску — только к файлам,
которые создала сама программа (scope drive.file), чужие файлы ей не видны.

Переменные окружения:
    BACKUP_PASSWORD        — пароль шифрования (хранить надёжно: без него копии бесполезны)
    GDRIVE_CLIENT_ID       — OAuth-клиент Google Cloud
    GDRIVE_CLIENT_SECRET
    GDRIVE_REFRESH_TOKEN   — разрешение доступа к Диску (получается один раз)
    BACKUP_KEEP_DAYS       — сколько дней хранить (по умолчанию 30)
"""
import json
import logging
import os
import secrets
import struct
from datetime import datetime, timedelta, timezone

import requests
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

logger = logging.getLogger(__name__)

MAGIC = b"OBKP1\n"          # шапка зашифрованной копии — по ней восстановление её узнаёт
CHUNK = 4 * 1024 * 1024     # шифруем кусками, чтобы не держать всю базу в памяти дважды
FOLDER_NAME = "OilBook — резервные копии"
FOLDER_MIME = "application/vnd.google-apps.folder"
GD_TOKEN_URL = "https://oauth2.googleapis.com/token"
GD_API = "https://www.googleapis.com/drive/v3"
GD_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"


def keep_days() -> int:
    try:
        return max(1, int(os.environ.get("BACKUP_KEEP_DAYS", "30")))
    except ValueError:
        return 30


# ---------- шифрование ----------

def backup_password() -> str:
    return os.environ.get("BACKUP_PASSWORD") or ""


def _key(password: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(password.encode("utf-8"))


def encrypt_file(src: str, dst: str, password: str) -> None:
    """Формат: MAGIC + соль(16) + фрагменты [длина(4) + nonce(12) + шифротекст].
    Номер фрагмента и признак «последний» входят в проверку подлинности —
    переставленный или обрезанный файл не расшифруется «молча»."""
    salt = secrets.token_bytes(16)
    aes = AESGCM(_key(password, salt))
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        fo.write(MAGIC + salt)
        idx = 0
        chunk = fi.read(CHUNK)
        while True:
            nxt = fi.read(CHUNK)
            last = not nxt
            nonce = secrets.token_bytes(12)
            ct = aes.encrypt(nonce, chunk, struct.pack(">IB", idx, int(last)))
            fo.write(struct.pack(">I", len(ct)) + nonce + ct)
            if last:
                break
            idx, chunk = idx + 1, nxt


def is_encrypted(data: bytes) -> bool:
    return data[:len(MAGIC)] == MAGIC


def decrypt_bytes(data: bytes, password: str) -> bytes:
    if not password:
        raise ValueError("копия зашифрована, а BACKUP_PASSWORD на сервере не задан")
    head = len(MAGIC) + 16
    if len(data) < head + 4:
        raise ValueError("файл копии повреждён (слишком короткий)")
    aes = AESGCM(_key(password, data[len(MAGIC):head]))
    pos, idx, out = head, 0, []
    try:
        while pos < len(data):
            (n,) = struct.unpack(">I", data[pos:pos + 4])
            nonce, ct = data[pos + 4:pos + 16], data[pos + 16:pos + 16 + n]
            pos += 16 + n
            if len(ct) != n:
                raise InvalidTag()
            out.append(aes.decrypt(nonce, ct, struct.pack(">IB", idx, int(pos >= len(data)))))
            idx += 1
    except (InvalidTag, struct.error):
        raise ValueError("неверный пароль копии или файл повреждён/обрезан")
    if not out:
        raise ValueError("файл копии повреждён (нет данных)")
    return b"".join(out)


def prepare(gz_path: str, name: str):
    """Шифрует копию, если задан пароль. → (путь, имя, зашифрована?).
    Зашифрованный файл (gz_path + '.enc') удаляет вызывающий."""
    password = backup_password()
    if not password:
        return gz_path, name, False
    enc = gz_path + ".enc"
    encrypt_file(gz_path, enc, password)
    return enc, name + ".enc", True


# ---------- Google Диск ----------

def _env(key: str) -> str:
    # при вставке в Render легко захватить пробел, кавычки или перенос строки
    return (os.environ.get(key) or "").strip().strip("'\"").strip()


def gdrive_enabled() -> bool:
    return all(_env(k) for k in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"))


def _gd_token() -> str:
    r = requests.post(GD_TOKEN_URL, data={
        "client_id": _env("GDRIVE_CLIENT_ID"),
        "client_secret": _env("GDRIVE_CLIENT_SECRET"),
        "refresh_token": _env("GDRIVE_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code != 200:
        hint = ("проверьте GDRIVE_CLIENT_ID и GDRIVE_CLIENT_SECRET (скопированы целиком?)"
                if "invalid_client" in r.text else
                "возможно, доступ отозван, нужен новый GDRIVE_REFRESH_TOKEN")
        raise RuntimeError(f"Google не пустил (HTTP {r.status_code}): {r.text[:200]} — {hint}")
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _gd_folder(token: str) -> str:
    q = f"name='{FOLDER_NAME}' and mimeType='{FOLDER_MIME}' and trashed=false"
    r = requests.get(f"{GD_API}/files", params={"q": q, "fields": "files(id)", "spaces": "drive"},
                     headers=_auth(token), timeout=30)
    r.raise_for_status()
    found = r.json().get("files") or []
    if found:
        return found[0]["id"]
    r = requests.post(f"{GD_API}/files", params={"fields": "id"}, headers=_auth(token),
                      json={"name": FOLDER_NAME, "mimeType": FOLDER_MIME}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def gdrive_upload(path: str, name: str, token: str = None, folder: str = None) -> str:
    """Загрузка с возобновлением (resumable) — подходит и для больших копий."""
    token = token or _gd_token()
    folder = folder or _gd_folder(token)
    size = os.path.getsize(path)
    r = requests.post(f"{GD_UPLOAD}?uploadType=resumable",
                      headers={**_auth(token), "Content-Type": "application/json; charset=UTF-8",
                               "X-Upload-Content-Type": "application/octet-stream",
                               "X-Upload-Content-Length": str(size)},
                      data=json.dumps({"name": name, "parents": [folder]}), timeout=30)
    if r.status_code != 200 or not r.headers.get("Location"):
        raise RuntimeError(f"Google Диск не принял копию (HTTP {r.status_code}): {r.text[:200]}")
    with open(path, "rb") as f:
        r2 = requests.put(r.headers["Location"], data=f, headers={"Content-Length": str(size)}, timeout=900)
    if r2.status_code not in (200, 201):
        raise RuntimeError(f"Загрузка в Google Диск оборвалась (HTTP {r2.status_code}): {r2.text[:200]}")
    return r2.json().get("id", "")


def _parse_time(s: str) -> datetime:
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def select_old(files: list, days: int, now: datetime = None) -> list:
    """Какие копии удалить: старше `days` дней, но `days` самых свежих
    остаются всегда (например, если сервер неделю не делал копий)."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    newest_first = sorted(files, key=lambda f: f["createdTime"], reverse=True)
    return [f for f in newest_first[days:] if _parse_time(f["createdTime"]) < cutoff]


def gdrive_prune(token: str, folder: str, days: int = None) -> int:
    days = days or keep_days()
    files, page = [], None
    while True:
        params = {"q": f"'{folder}' in parents and trashed=false",
                  "fields": "nextPageToken, files(id, name, createdTime)", "pageSize": 1000}
        if page:
            params["pageToken"] = page
        r = requests.get(f"{GD_API}/files", params=params, headers=_auth(token), timeout=30)
        r.raise_for_status()
        js = r.json()
        files += js.get("files") or []
        page = js.get("nextPageToken")
        if not page:
            break
    old = select_old(files, days)
    for f in old:
        d = requests.delete(f"{GD_API}/files/{f['id']}", headers=_auth(token), timeout=30)
        if d.status_code not in (200, 204, 404):
            logger.warning(f"Google Диск: не удалось удалить старую копию {f.get('name')}: HTTP {d.status_code}")
    return len(old)


def to_gdrive(path: str, name: str):
    """Загрузить копию и убрать старые. → (True, None) | (False, ошибка) |
    (None, None), если Google Диск не настроен."""
    if not gdrive_enabled():
        return None, None
    try:
        token = _gd_token()
        folder = _gd_folder(token)
        gdrive_upload(path, name, token, folder)
        removed = gdrive_prune(token, folder)
        logger.info(f"Копия {name} загружена в Google Диск, старых удалено: {removed}")
        return True, None
    except Exception as e:
        logger.error(f"Копия в Google Диск не загружена: {e}")
        return False, str(e)
