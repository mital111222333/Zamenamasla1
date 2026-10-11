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
    if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 100_000:
        return
    import requests
    log("Скачиваю модель распознавания…")
    r = requests.get(server + "/ocr/v1/plate_ocr_uz.onnx", timeout=120)
    r.raise_for_status()
    tmp = MODEL_PATH + ".part"
    with open(tmp, "wb") as f:
        f.write(r.content)
    os.replace(tmp, MODEL_PATH)
    log(f"Модель скачана ({len(r.content) // 1024} КБ)")


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
    print("=== Настройка камеры для табло OilBook ===")
    print("1) Откройте панель OilBook → «Моя точка» → «Табло у входа»")
    print("   и скопируйте ссылку «Для телефона у въезда».")
    while True:
        link = ask("Вставьте эту ссылку")
        server, token = parse_scanner_link(link)
        if server:
            break
        print("   Ссылка должна выглядеть так: https://ваш-сайт/scanner/AbC123… — попробуйте ещё раз.")

    print()
    print("2) Какая камера?  1 — Hikvision   2 — Dahua   3 — другая (вставлю RTSP-адрес)")
    kind = ask("Номер варианта", "1")
    if kind in ("1", "2"):
        ip = ask("IP-адрес камеры (например 192.168.1.64)")
        user = ask("Логин камеры", "admin")
        password = ask("Пароль камеры")
        url = hikvision_rtsp(ip, user, password) if kind == "1" else dahua_rtsp(ip, user, password)
    else:
        url = ask("RTSP-адрес камеры (rtsp://…)")

    print()
    log("Подключаюсь к камере, это может занять до 20 секунд…")
    frame = grab_one_frame(url)
    if frame is None:
        print("Не удалось получить кадр с камеры. Проверьте IP, логин, пароль и что компьютер")
        print("в той же сети, что и камера. Затем запустите setup.bat ещё раз.")
        sys.exit(1)

    print()
    print("3) Сейчас откроется кадр с камеры. Поставьте машину на место остановки,")
    print("   обведите мышкой её НОМЕР (плотно, по краям таблички) и нажмите ENTER.")
    print("   Если машины сейчас нет — обведите место, где обычно оказывается номер.")
    input("   Нажмите ENTER, чтобы открыть кадр… ")
    h, w = frame.shape[:2]
    scale = min(1.0, 1280 / w, 720 / h)
    view = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1 else frame
    title = "Draw a box around the plate, then press ENTER"
    x, y, bw, bh = cv2.selectROI(title, view, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()
    if bw < 10 or bh < 5:
        print("Зона не выбрана. Запустите setup.bat ещё раз.")
        sys.exit(1)
    zone = [x / view.shape[1], y / view.shape[0], bw / view.shape[1], bh / view.shape[0]]
    plate_px = int(bw / scale)
    if plate_px < 120:
        print(f"Внимание: номер на кадре всего ~{plate_px} пикселей в ширину — может читаться плохо.")
        print("Лучше поставить камеру ближе или выбрать основной поток высокого качества.")

    cfg.update({"server": server, "token": token, "rtsp": url, "zone": zone})
    save_config(cfg)
    ensure_model(server)
    print()
    print("Готово! Настройки сохранены в config.json. Теперь запустите start.bat.")


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
    if not cfg or not all(cfg.get(k) for k in ("server", "token", "rtsp", "zone")):
        print("Сначала настройка: запустите setup.bat")
        sys.exit(1)
    import onnxruntime as ort
    ensure_model(cfg["server"])
    sess = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
    inp, out = sess.get_inputs()[0].name, sess.get_outputs()[0].name

    reader = FrameReader(cfg["rtsp"])
    reader.start()
    log("Жду машину… (закройте окно, чтобы остановить)")
    hits, last_hit, last_sent, last_no, tick = {}, 0.0, {}, 0, 0
    lock_idx, lock_miss = 0, 0
    while True:
        frame, no = reader.latest()
        if frame is None or no == last_no:
            time.sleep(FRAME_PAUSE)
            continue
        last_no = no
        tick += 1
        wins = search_windows(frame.shape[1], frame.shape[0], cfg["zone"])
        # за кадр — «удачная» рамка и следующая по очереди; берём лучшее прочтение
        lock = lock_idx if lock_idx < len(wins) else 0
        rot = tick % len(wins)
        if rot == lock:
            rot = (rot + 1) % len(wins)
        plate, conf, best_idx = None, 0.0, lock
        for idx in (lock, rot):
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
                    log(f"На табло: {pretty(plate)}  ({round(conf * 100)}%)")
                except Exception as e:
                    log(f"Не удалось отправить номер ({e}) — проверьте интернет")
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
