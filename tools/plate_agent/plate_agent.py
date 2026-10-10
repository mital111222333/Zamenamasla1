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
MODEL_PATH = os.path.join(HERE, "plate_ocr.onnx")

# --- распознавание: то же, что в сканере в браузере (webapp.py, decode) ---
ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"
FORMATS = ("DDLDDDLL", "DDDDDLLL")  # новые узбекские: 01 A 123 BC и 01 123 ABC
REGIONS = {"01", "10", "20", "25", "30", "40", "50", "60", "70", "75", "80", "85", "90", "95"}
FREE_MARGIN = 2.5     # насколько свободное чтение должно быть лучше узбекского формата
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


def decode(probs):
    """probs — 370 чисел (10 позиций × 37 символов). Возвращает (номер, уверенность).
    Сначала подгоняем под узбекский формат; если свободное чтение заметно
    лучше — это российский, старый узбекский или другой номер."""
    def lp(k, j):
        return math.log(probs[k * 37 + j] + 1e-9)

    reg_score, reg_code = None, None
    for a in range(10):
        for b in range(10):
            code = f"{a}{b}"
            sc = lp(0, a) + lp(1, b) - (0 if code in REGIONS else 3)
            if reg_score is None or sc > reg_score:
                reg_score, reg_code = sc, code
    best_score, best_plate = None, None
    for f in FORMATS:
        score, out = reg_score, reg_code
        for k in range(2, 10):
            if k >= len(f):
                score += lp(k, 36)
                continue
            lo, hi = (0, 10) if f[k] == "D" else (10, 36)
            bj = max(range(lo, hi), key=lambda j: probs[k * 37 + j])
            score += lp(k, bj)
            out += ALPHA[bj]
        if best_score is None or score > best_score:
            best_score, best_plate = score, out

    free_score, free_plate = 0.0, ""
    for k in range(10):
        bj = max(range(37), key=lambda j: probs[k * 37 + j])
        free_score += lp(k, bj)
        if bj != 36:
            free_plate += ALPHA[bj]
    if len(free_plate) >= 4 and free_score - best_score > FREE_MARGIN:
        return free_plate, math.exp(free_score / 10)
    return best_plate, math.exp(best_score / 10)


def pretty(p):
    if re.fullmatch(r"[0-9]{2}[A-Z][0-9]{3}[A-Z]{2}", p):
        return f"{p[:2]} {p[2]} {p[3:6]} {p[6:]}"
    if re.fullmatch(r"[0-9]{5}[A-Z]{3}", p):
        return f"{p[:2]} {p[2:5]} {p[5:]}"
    return p


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
    r = requests.get(server + "/ocr/v1/plate_ocr.onnx", timeout=120)
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
