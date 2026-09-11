"""
Отправка SMS через Eskiz.uz — для клиентов без Telegram. У каждой точки
свой договор/аккаунт Eskiz (свои email+пароль, введённые в своих настройках
на сайте). Модуль сам логинится, кэширует токен и обновляет его по мере
истечения — снаружи достаточно вызвать send_sms(shop_id, phone, text).
"""

import time
import logging
import requests

logger = logging.getLogger(__name__)

ESKIZ_BASE = "https://notify.eskiz.uz/api"
TOKEN_TTL_SECONDS = 25 * 24 * 3600  # токен Eskiz живёт ~30 дней, обновляем заранее

# Токены кэшируются в памяти процесса, отдельно на каждую точку:
# {shop_id: {"token": "...", "obtained_at": <unix time>}}
_token_cache = {}


def _get_token(shop_id: int, email: str, password: str):
    cached = _token_cache.get(shop_id)
    if cached and (time.time() - cached["obtained_at"]) < TOKEN_TTL_SECONDS:
        return cached["token"]

    resp = requests.post(f"{ESKIZ_BASE}/auth/login", data={"email": email, "password": password}, timeout=10)
    resp.raise_for_status()
    token = resp.json()["data"]["token"]
    _token_cache[shop_id] = {"token": token, "obtained_at": time.time()}
    return token


def send_sms(shop_id: int, email: str, password: str, phone: str, text: str):
    """Отправляет одну SMS. Возвращает (успех: bool, сообщение_об_ошибке_или_None).
    Ничего не бросает наружу — любая ошибка сети/авторизации/API просто
    возвращает False с описанием, чтобы вызывающий код (напоминания в боте)
    не падал из-за проблем с SMS-провайдером."""
    if not email or not password:
        return False, "не заданы данные Eskiz для этой точки"

    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("998") and len(digits) == 12:
        pass  # уже в нужном формате
    elif len(digits) == 9:
        digits = "998" + digits
    else:
        return False, f"некорректный номер телефона: {phone}"

    try:
        token = _get_token(shop_id, email, password)
        resp = requests.post(
            f"{ESKIZ_BASE}/message/sms/send",
            headers={"Authorization": f"Bearer {token}"},
            data={"mobile_phone": digits, "message": text, "from": "4546"},
            timeout=10,
        )
        if resp.status_code == 401:
            # токен протух раньше срока — сбрасываем кэш и пробуем один раз ещё
            _token_cache.pop(shop_id, None)
            token = _get_token(shop_id, email, password)
            resp = requests.post(
                f"{ESKIZ_BASE}/message/sms/send",
                headers={"Authorization": f"Bearer {token}"},
                data={"mobile_phone": digits, "message": text, "from": "4546"},
                timeout=10,
            )
        resp.raise_for_status()
        return True, None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Ошибка отправки SMS через Eskiz (точка {shop_id}): {e}")
        return False, str(e)
