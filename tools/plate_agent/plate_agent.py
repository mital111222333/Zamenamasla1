"""OilBook — распознавание госномера с IP-камеры для табло у входа.

Работает на компьютере точки: берёт видео с IP-камеры (Hikvision, Dahua и
любой другой с RTSP) по локальной сети, вырезает «зону номера», распознаёт
номер той же моделью, что и сканер в браузере, и отправляет его на табло
(/api/anpr/<токен>). Дальше — как со сканером на телефоне: приветствие на
телевизоре и карточка мастеру в панели. Видео никуда не отправляется, на
сервер уходит только текст номера.

    python plate_agent.py setup   — первая настройка (ссылка, камера, зона)
    python plate_agent.py         — работа (запускайте start.bat)
"""
import json
import math
import os
import re
import sys
import threading
import time
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
MODEL_PATH = os.path.join(HERE, "plate_ocr_uz.onnx")
DET_PATH = os.path.join(HERE, "plate_det_s256.onnx")   # «искатель» номера во всём кадре
DET = 256
DET_MIN = 0.4

# --- распознавание: то же, что в сканере в браузере (webapp.py, plateDecode) ---
ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"
RU_LET = "ABEKMHOPCTYX"
TEMPLATES = [
    ("DDLDDDLL", 0.0),    # UZ физлица:            01 A 123 BC
    ("DDDDDLLL", 0.0),    # UZ юрлица (и KG):      01 123 ABC
    ("DDLDDDD", 0.4),     # UZ старый 1996–2008:   23 G 8107
    ("DDLDDDDDD", 0.8),   # UZ иностранцы/фирмы:   01 H 123456
    ("RDDDRRDD", 0.6),    # RU:                    A 123 BC 77
    ("RDDDRRDDD", 0.6),   # RU:                    A 123 BC 777
    ("DDDLLLDD", 0.6),    # KZ:                    123 ABC 01
    ("DDDLLDD", 0.8),     # KZ:                    123 AB 01
    ("DDDDLLDD", 0.6),    # TJ:                    1234 AB 01
]
JUNK = 2.0
FREE_MARGIN = 3.0
CLASSES = {"D": list(range(10)), "L": list(range(10, 36)),
           "R": [ALPHA.index(c) for c in RU_LET], "A": list(range(36))}
NEG = -1e18


def decode(probs):
    """probs — 370 чисел (10 позиций × 37) или массив 10×37. Возвращает (номер, уверенность)."""
    flat = [float(x) for x in (probs.reshape(-1) if hasattr(probs, "reshape") else probs)]
    L = [[math.log(flat[k * 37 + j] + 1e-9) for j in range(37)] for k in range(10)]
    best = []
    for row in L:
        o = {}
        for c, idx in CLASSES.items():
            bj = idx[0]
            for j in idx:
                if row[j] > row[bj]:
                    bj = j
            o[c] = bj
        best.append(o)
    cand = None
    for tpl, prior in TEMPLATES:
        n = len(tpl)
        dp = [[NEG] * (n + 1) for _ in range(11)]
        bk = [[None] * (n + 1) for _ in range(11)]
        dp[0][0] = 0.0
        for i in range(10):
            for t in range(n + 1):
                s = dp[i][t]
                if s == NEG:
                    continue
                if t < n:
                    j = best[i][tpl[t]]; v = L[i][j]
                    if s + v > dp[i + 1][t + 1]:
                        dp[i + 1][t + 1] = s + v; bk[i + 1][t + 1] = (t, j, v)
                else:
                    v = L[i][36]
                    if s + v > dp[i + 1][t]:
                        dp[i + 1][t] = s + v; bk[i + 1][t] = (t, -2, v)
                jj = best[i]["A"]; vj = L[i][jj]
                if s + vj - JUNK > dp[i + 1][t]:
                    dp[i + 1][t] = s + vj - JUNK; bk[i + 1][t] = (t, -1, vj)
        sc = dp[10][n]
        if sc == NEG:
            continue
        out, raw, t = "", 0.0, n
        for i in range(10, 0, -1):
            pt, j, v = bk[i][t]
            raw += v
            if j >= 0:
                out = ALPHA[j] + out
            t = pt
        if tpl.startswith("DD") and out.startswith("00"):
            sc -= 4; raw -= 4
        sc -= prior
        if cand is None or sc > cand[0]:
            cand = (sc, raw, out)
    fs, fp = 0.0, ""
    for k in range(10):
        bj = 0
        for j in range(1, 37):
            if L[k][j] > L[k][bj]:
                bj = j
        fs += L[k][bj]
        if bj != 36:
            fp += ALPHA[bj]
    if len(fp) >= 4 and (cand is None or fs - FREE_MARGIN > cand[0]):
        return fp, math.exp(fs / 10)
    return cand[2], math.exp(cand[1] / 10)


_PRETTY = [
    (r"^([0-9]{2})([A-Z])([0-9]{3})([A-Z]{2})$", r"\1 \2 \3 \4"),
    (r"^([0-9]{2})([0-9]{3})([A-Z]{3})$", r"\1 \2 \3"),
    (r"^([0-9]{2})([A-Z])([0-9]{4})$", r"\1 \2 \3"),
    (r"^([0-9]{2})([A-Z])([0-9]{6})$", r"\1 \2 \3"),
    (r"^([A-Z])([0-9]{3})([A-Z]{2})([0-9]{2,3})$", r"\1 \2 \3 \4"),
    (r"^([0-9]{3})([A-Z]{2,3})([0-9]{2})$", r"\1 \2 \3"),
    (r"^([0-9]{4})([A-Z]{2})([0-9]{2})$", r"\1 \2 \3"),
]


def pretty(p):
    p = re.sub(r"[^A-Z0-9]", "", str(p or "").upper())
    for rx, f in _PRETTY:
        if re.match(rx, p):
            return re.sub(rx, f, p)
    return p


MIN_CONF = 0.6        # кадр учитываем при такой уверенности
NEED_HITS = 2         # два одинаковых прочтения подряд — и номер на табло
INSTANT_CONF = 0.95   # при такой уверенности хватает одного кадра
HIT_WINDOW = 2.0      # секунды: прочтения должны идти подряд
RESEND = 90           # секунды: тот же номер повторно на табло не шлём
FRAME_PAUSE = 0.1     # секунды между кадрами
# Окна поиска номера вокруг зоны — как рамка сканера в панели: ширина = ширина
# номера, высота = ширина / 3.2 (запас сверху и снизу). Плюс рамки крупнее,
# мельче и со сдвигом — машина не всегда встаёт точно в одно место.
WIN_SCALES = (1.0, 1.3, 0.8)
WIN_SHIFTS = (0.0, -0.25, 0.25)
WIN_INSETS = ((0.0, 0.0), (0.06, 0.14))
LOCK_MISSES = 15      # столько кадров подряд без номера — отпускаем «удачную» рамку


def parse_scanner_link(link):
    """Ссылка из «Моя точка» → (адрес сайта, токен табло)."""
    m = re.match(r"^\s*(https?://[^/\s]+)/scanner/([A-Za-z0-9_\-]+)\s*$", link or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def hikvision_rtsp(ip, user, password, channel="101"):
    return f"rtsp://{quote(user, safe='')}:{quote(password, safe='')}@{ip}:554/Streaming/Channels/{channel}"


def dahua_rtsp(ip, user, password):
    return f"rtsp://{quote(user, safe='')}:{quote(password, safe='')}@{ip}:554/cam/realmonitor?channel=1&subtype=0"


def hide_password(url):
    return re.sub(r"(rtsp://[^:/@]+:)[^@]*@", r"\1***@", url)


def log(text):
    print(time.strftime("%H:%M:%S"), text, flush=True)


# --- конфигурация ---
def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# --- модель распознавания: скачиваем один раз с сайта точки ---
def ensure_model(server):
    """Две модели, как у сканера в панели: «искатель» находит номер во всём
    кадре, вторая читает найденный номер."""
    import requests
    for path in (MODEL_PATH, DET_PATH):
        if os.path.exists(path) and os.path.getsize(path) > 100_000:
            continue
        name = os.path.basename(path)
        log(f"Скачиваю модель {name}… / {name} modeli yuklanmoqda…")
        r = requests.get(server + "/ocr/v1/" + name, timeout=180)
        r.raise_for_status()
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(r.content)
        os.replace(tmp, path)
        log(f"Готово ({len(r.content) // 1024} КБ) / Tayyor")


def detect_plate(det, frame):
    """«Искатель»: весь кадр вписан в квадрат 256×256 с серыми полями →
    самый уверенный и крупный номер в пикселях кадра (x1, y1, x2, y2) или None."""
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    r = min(DET / w, DET / h)
    nw, nh = int(round(w * r)), int(round(h * r))
    dx, dy = (DET - nw) // 2, (DET - nh) // 2
    canvas = np.full((DET, DET, 3), 114, dtype=np.uint8)
    canvas[dy:dy + nh, dx:dx + nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255.0
    rows = det.run(None, {det.get_inputs()[0].name: x})[0].reshape(-1, 7)
    best, best_rank = None, 0.0
    for row in rows:
        score = float(row[6])
        if score < DET_MIN:
            continue
        x1, y1 = (row[1] - dx) / r, (row[2] - dy) / r
        x2, y2 = (row[3] - dx) / r, (row[4] - dy) / r
        if x2 - x1 < 12 or y2 - y1 < 5:
            continue
        rank = score + min((x2 - x1) * (y2 - y1) / (w * h) * 4, 0.15)
        if rank > best_rank:
            best, best_rank = (x1, y1, x2, y2), rank
    return best


def box_window(box, pad):
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    return (x1 - bw * pad[0], y1 - bh * pad[1], bw * (1 + 2 * pad[0]), bh * (1 + 2 * pad[1]))


# --- камера: отдельный поток всегда держит самый свежий кадр ---
class FrameReader(threading.Thread):
    """RTSP-поток буферизуется: если читать медленнее, чем камера отдаёт,
    кадры начинают отставать на секунды. Поэтому читаем без остановки в
    отдельном потоке и отдаём распознаванию только последний кадр."""

    def __init__(self, url):
        super().__init__(daemon=True)
        self.url = url
        self.frame = None
        self.frame_no = 0
        self.lock = threading.Lock()
        self.connected = False

    def run(self):
        import cv2
        while True:
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                self.connected = False
                log("Камера не отвечает — проверьте IP, логин и пароль. Повтор через 10 с…")
                time.sleep(10)
                continue
            self.connected = True
            log("Камера подключена: " + hide_password(self.url))
            fails = 0
            while fails < 50:
                ok, frame = cap.read()
                if not ok or frame is None:
                    fails += 1
                    time.sleep(0.1)
                    continue
                fails = 0
                with self.lock:
                    self.frame = frame
                    self.frame_no += 1
            cap.release()
            self.connected = False
            log("Связь с камерой потеряна — переподключаюсь…")
            time.sleep(3)

    def latest(self):
        with self.lock:
            return self.frame, self.frame_no


def grab_one_frame(url, timeout=20):
    reader = FrameReader(url)
    reader.start()
    end = time.time() + timeout
    while time.time() < end:
        frame, _ = reader.latest()
        if frame is not None:
            return frame
        time.sleep(0.2)
    return None


# --- первая настройка ---
def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def setup():
    import cv2
    cfg = load_config() or {}
    print()
    print("=== Настройка камеры для табло OilBook / OilBook tablosi uchun kamerani sozlash ===")
    print("1) Панель OilBook → «Моя точка» → «Табло у входа»: скопируйте ссылку для телефона (/scanner/…).")
    print("   OilBook paneli → «Mening nuqtam» → «Kirishdagi tablo»: telefon uchun havolani (/scanner/…) nusxalang.")
    while True:
        link = ask("Вставьте ссылку / Havolani joylang")
        server, token = parse_scanner_link(link)
        if server:
            break
        print("   Нужна ссылка вида / Havola shunday bo'lishi kerak: https://oilbook.uz/scanner/AbC123…")

    print()
    print("2) Какая камера? / Qaysi kamera?   1 — Hikvision   2 — Dahua   3 — другая / boshqa (RTSP)")
    kind = ask("Номер варианта / Variant raqami", "1")
    if kind in ("1", "2"):
        ip = ask("IP камеры / Kamera IP manzili (192.168.1.64)")
        user = ask("Логин / Login", "admin")
        password = ask("Пароль / Parol")
        url = hikvision_rtsp(ip, user, password) if kind == "1" else dahua_rtsp(ip, user, password)
    else:
        url = ask("RTSP-адрес / RTSP manzil (rtsp://…)")

    print()
    log("Подключаюсь к камере (до 20 с)… / Kameraga ulanmoqda (20 soniyagacha)…")
    frame = grab_one_frame(url)
    if frame is None:
        print("Не удалось получить кадр с камеры. Проверьте IP, логин, пароль и что компьютер в той же сети.")
        print("Kameradan kadr olib bo'lmadi. IP, login, parolni va kompyuter shu tarmoqdaligini tekshiring.")
        sys.exit(1)

    # рамку больше не рисуем: номер в кадре находит «искатель» сам
    cfg.update({"server": server, "token": token, "rtsp": url})
    cfg.pop("zone", None)
    save_config(cfg)
    ensure_model(server)
    import onnxruntime as ort
    det = ort.InferenceSession(DET_PATH, providers=["CPUExecutionProvider"])
    box = detect_plate(det, frame)
    print()
    if box:
        plate_px = int(box[2] - box[0])
        print(f"Номер на кадре найден автоматически (~{plate_px} пикс.). / Raqam avtomatik topildi (~{plate_px} piksel).")
        if plate_px < 120:
            print("Номер мелкий — лучше поставить камеру ближе. / Raqam kichik — kamerani yaqinroq qo'ying.")
    else:
        print("Сейчас номера в кадре нет — это нормально, если машины нет. Рамку рисовать не нужно, номер найдётся сам.")
        print("Hozir kadrda raqam yo'q — mashina bo'lmasa, bu normal. Ramka chizish shart emas, raqam o'zi topiladi.")
    print()
    print("Готово! Теперь запустите start.bat. / Tayyor! Endi start.bat ni ishga tushiring.")


# --- работа ---
def search_windows(frame_w, frame_h, zone):
    """Список окон (x, y, w, h) в пикселях кадра; [0] — основная рамка по центру зоны."""
    zw = zone[2] * frame_w
    cx = (zone[0] + zone[2] / 2) * frame_w
    cy = (zone[1] + zone[3] / 2) * frame_h
    wins = []
    for s in WIN_SCALES:
        for dx in WIN_SHIFTS:
            for ix, iy in WIN_INSETS:
                w = zw * s
                h = w / 3.2
                x = cx - w / 2 + dx * zw
                y = cy - h / 2
                x += w * ix
                w *= 1 - 2 * ix
                y += h * iy
                h *= 1 - 2 * iy
                # окно, вылезающее за кадр, прижимаем к краю (размер не меняем)
                x = min(max(0.0, x), max(0.0, frame_w - w))
                y = min(max(0.0, y), max(0.0, frame_h - h))
                wins.append((x, y, min(w, frame_w), min(h, frame_h)))
    return wins


def crop_tensor(frame, win):
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    x, y, ww, wh = win
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(w, int(x + ww)), min(h, int(y + wh))
    if x1 - x0 < 4 or y1 - y0 < 2:
        return None
    crop = cv2.resize(frame[y0:y1, x0:x1], (128, 64), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return np.ascontiguousarray(rgb, dtype=np.uint8)[None, ...]


def send_plate(cfg, plate):
    import requests
    r = requests.post(f"{cfg['server']}/api/anpr/{cfg['token']}", json={"plate": plate}, timeout=10)
    r.raise_for_status()


def run():
    cfg = load_config()
    if not cfg or not all(cfg.get(k) for k in ("server", "token", "rtsp")):
        print("Сначала настройка: запустите setup.bat / Avval sozlash: setup.bat ni ishga tushiring")
        sys.exit(1)
    import onnxruntime as ort
    ensure_model(cfg["server"])
    sess = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
    inp, out = sess.get_inputs()[0].name, sess.get_outputs()[0].name
    det = None
    try:
        det = ort.InferenceSession(DET_PATH, providers=["CPUExecutionProvider"])
    except Exception as e:
        log(f"«Искатель» номера не загрузился ({e}) — работаю по зоне из настройки")
        if not cfg.get("zone"):
            print("Запустите setup.bat ещё раз. / setup.bat ni qayta ishga tushiring.")
            sys.exit(1)

    reader = FrameReader(cfg["rtsp"])
    reader.start()
    log("Жду машину… / Mashina kutilmoqda… (закройте окно, чтобы остановить)")
    hits, last_hit, last_sent, last_no, tick = {}, 0.0, {}, 0, 0
    lock_idx, lock_miss = 0, 0
    while True:
        frame, no = reader.latest()
        if frame is None or no == last_no:
            time.sleep(FRAME_PAUSE)
            continue
        last_no = no
        tick += 1
        plate, conf, best_idx = None, 0.0, 0
        if det is not None:
            # «искатель» находит номер во всём кадре — читаем его место
            # (два варианта запаса вокруг), как сканер в панели
            box = detect_plate(det, frame)
            if box is None:
                time.sleep(FRAME_PAUSE)
                continue
            wins = [box_window(box, (0.08, 0.2)), box_window(box, (0.03, 0.1))]
            candidates = (0, 1)
        else:
            wins = search_windows(frame.shape[1], frame.shape[0], cfg["zone"])
            # за кадр — «удачная» рамка и следующая по очереди; берём лучшее прочтение
            lock = lock_idx if lock_idx < len(wins) else 0
            rot = tick % len(wins)
            if rot == lock:
                rot = (rot + 1) % len(wins)
            candidates, best_idx = (lock, rot), lock
        for idx in candidates:
            tensor = crop_tensor(frame, wins[idx])
            if tensor is None:
                continue
            probs = sess.run([out], {inp: tensor})[0].reshape(-1).tolist()
            p, c = decode(probs)
            if plate is None or c > conf:
                plate, conf, best_idx = p, c, idx
        if plate is None:
            time.sleep(FRAME_PAUSE)
            continue
        if conf >= MIN_CONF:
            lock_idx, lock_miss = best_idx, 0
        else:
            lock_miss += 1
            if lock_miss > LOCK_MISSES:
                lock_idx, lock_miss = 0, 0
        now = time.time()
        if now - last_hit > HIT_WINDOW:
            hits = {}
        if conf >= MIN_CONF:
            last_hit = now
            hits[plate] = hits.get(plate, 0) + 1
            if (hits[plate] >= NEED_HITS or conf >= INSTANT_CONF) and now - last_sent.get(plate, 0) > RESEND:
                hits = {}
                try:
                    send_plate(cfg, plate)
                    last_sent[plate] = now
                    log(f"На табло / Tabloda: {pretty(plate)}  ({round(conf * 100)}%)")
                except Exception as e:
                    log(f"Не удалось отправить номер ({e}) — проверьте интернет / Internetni tekshiring")
        time.sleep(FRAME_PAUSE)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    # RTSP по TCP: стабильнее по Wi-Fi и через роутеры, меньше «рассыпанных» кадров
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "setup":
            setup()
        else:
            run()
    except KeyboardInterrupt:
        print()
        log("Остановлено.")


if __name__ == "__main__":
    main()
