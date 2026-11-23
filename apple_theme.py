"""
Тема в стиле Apple (iOS / iPadOS / macOS) для панели точки — тема по умолчанию.

Как устроено (так же, как тёмная тема в glass_theme.py):
- Слой 1 (автоматический). При запуске сервера берём ВСЕ стили страницы
  (блоки <style> и style="..."), и каждый цвет переводим в системную палитру
  Apple: синие → #007AFF, красные → #FF3B30, зелёные → #34C759, серые
  Tailwind → серые Apple (#F2F2F7, #E5E5EA, #8E8E93, #1D1D1F) и т.д. Заодно
  убираем «крик»: заглавные буквы, курсив, разрядку в подписях. Так новый вид
  получают все вкладки и окна сразу, в том числе будущие.
- Слой 2 (ручной). Шрифт системы (SF Pro на iPhone и Mac), большие заголовки,
  панель вкладок как на iPhone, боковое меню как на iPad, сегменты, поля,
  кнопки, окна-шторки.
- Тёмный режим: тот же слой 1 из glass_theme.py (класс html.gl) + здесь
  поверх него — тёмная палитра Apple (#000 / #1C1C1E) вместо цветных пятен.

Всё действует только при классе html.ap (его ставит ранний скрипт в <head>).

Скорость: файл стилей собирается один раз при запуске, отдаётся отдельным
адресом с версией и кэшируется телефоном надолго. Размытие (backdrop-filter)
есть только у шапки, нижней панели и шторок; на слабых телефонах (gl-lite)
и при «уменьшить движение» — без размытия и анимаций.
"""

import hashlib
import json
import re

from glass_theme import (_COLOR_RE, _COMMENT_RE, _DYN_RE, _DYNAMIC_PROPS, _INLINE_RE, _JINJA_RE, _JS_HEX_RE,
                         _STYLE_BLOCK_RE, _chroma, _fmt, _hls, _match_brace, _parse_color, _split_top)

PREFIX = "html.ap:not(.gl)"

# ------------------------------------------------------ палитра Apple ----
# (оттенок фона, светлый, основной, для текста на белом)
PALETTE = {
    "blue":   ("#E5F1FF", "#B8D9FF", "#007AFF", "#007AFF"),
    "indigo": ("#EEEEFC", "#CFCEF5", "#5856D6", "#5856D6"),
    "purple": ("#F6EDFC", "#E5CCF4", "#AF52DE", "#8944AB"),
    "pink":   ("#FFE9EE", "#FFC2CF", "#FF2D55", "#D30F45"),
    "red":    ("#FFECEB", "#FFC7C3", "#FF3B30", "#D70015"),
    "orange": ("#FFF3E3", "#FFDDB0", "#FF9500", "#C93400"),
    "yellow": ("#FFF8DB", "#FFEC9E", "#FFCC00", "#A05A00"),
    "green":  ("#E8F8EC", "#BDEBC9", "#34C759", "#248A3D"),
    "teal":   ("#E5F6F9", "#BCE6EE", "#30B0C7", "#0071A4"),
    "cyan":   ("#E6F5FC", "#BDE5F7", "#32ADE6", "#0071A4"),
}
_HUES = [(14, "red"), (42, "orange"), (62, "yellow"), (170, "green"), (192, "teal"), (204, "cyan"),
         (236, "blue"), (262, "indigo"), (305, "purple"), (338, "pink"), (361, "red")]


def _hue_name(h):
    deg = h * 360
    for top, name in _HUES:
        if deg < top:
            return name
    return "red"


def _with_alpha(hexc, a):
    r, g, b = int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16)
    return _fmt(r, g, b, a)


def _is_gray(r, g, b):
    """Серый ли цвет. Серые Tailwind (slate) слегка синие (#64748B, #94A3B8):
    их нельзя путать с синими — порог по «цветности» зависит от светлоты."""
    h, l, s = _hls(r, g, b)
    c = _chroma(r, g, b)
    if l >= 0.9:
        return c < 0.06
    if l >= 0.72:
        return c < 0.12
    return c < 0.17


def _gray_bg(l):
    if l >= 0.985:
        return None
    if l >= 0.93:
        return "#F2F2F7"
    if l >= 0.86:
        return "#E5E5EA"
    if l >= 0.72:
        return "#D1D1D6"
    if l >= 0.5:
        return "#AEAEB2"
    if l >= 0.3:
        return "#636366"
    return "#1C1C1E"


def _gray_fg(l):
    if l >= 0.85:
        return None
    if l >= 0.6:
        return "#8E8E93"
    if l >= 0.38:
        return "#6E6E73"
    if l >= 0.25:
        return "#3A3A3C"
    return "#1D1D1F"


def _gray_border(l):
    if l >= 0.985:
        return None
    if l >= 0.86:
        return "#E5E5EA"
    if l >= 0.72:
        return "#D1D1D6"
    if l >= 0.45:
        return "#AEAEB2"
    return "#3A3A3C"


def map_bg(r, g, b, a):
    if a == 0:
        return None
    h, l, s = _hls(r, g, b)
    if _is_gray(r, g, b):
        out = _gray_bg(l)
    else:
        tint, light, base, _t = PALETTE[_hue_name(h)]
        out = tint if l >= 0.93 else light if l >= 0.8 else base if l >= 0.2 else "#1C1C1E"
    return None if out is None else _with_alpha(out, a)


def map_fg(r, g, b, a):
    if a == 0:
        return None
    h, l, s = _hls(r, g, b)
    if _is_gray(r, g, b):
        out = _gray_fg(l)
    else:
        if l >= 0.85:
            return _with_alpha("#FFFFFF", a)  # бледно-цветной текст на яркой кнопке — белый, как у Apple
        if l >= 0.72:
            return None  # светлый цветной текст — на тёмной плашке, оставляем
        out = PALETTE[_hue_name(h)][3] if l >= 0.2 else "#1D1D1F"
    return None if out is None else _with_alpha(out, a)


def map_border(r, g, b, a):
    if a == 0:
        return None
    h, l, s = _hls(r, g, b)
    if _is_gray(r, g, b):
        out = _gray_border(l)
    else:
        tint, light, base, _t = PALETTE[_hue_name(h)]
        out = tint if l >= 0.9 else light if l >= 0.75 else base if l >= 0.2 else "#3A3A3C"
    return None if out is None else _with_alpha(out, a)


def map_shadow(r, g, b, a):
    # тени у Apple нейтральные и мягкие — без цветного свечения
    return _fmt(0, 0, 0, min(0.12, a * 0.6))


def map_accent(r, g, b, a):
    if a == 0:
        return None
    h, l, s = _hls(r, g, b)
    if l >= 0.8:
        return map_bg(r, g, b, a)
    if _is_gray(r, g, b):
        return _with_alpha(_gray_fg(l) or "#8E8E93", a)
    return _with_alpha(PALETTE[_hue_name(h)][2], a) if l >= 0.2 else _with_alpha("#1D1D1F", a)


_ROLE_BY_PROP = {
    "color": map_fg, "-webkit-text-fill-color": map_fg, "caret-color": map_fg,
    "text-decoration-color": map_fg,
    "background": map_bg, "background-color": map_bg, "background-image": map_bg,
    "box-shadow": map_shadow, "text-shadow": map_shadow,
    "fill": map_accent, "stroke": map_accent,
}


def _role(prop):
    if prop in _ROLE_BY_PROP:
        return _ROLE_BY_PROP[prop]
    if prop.startswith("border") or prop.startswith("outline") or prop == "column-rule":
        return map_border
    if prop.startswith("--"):
        return map_accent
    return None


def map_color_value(prop, value):
    fn = _role(prop)
    if not fn or "url(" in value:
        return None
    changed = False

    def sub(m):
        nonlocal changed
        c = _parse_color(m.group(0))
        if not c:
            return m.group(0)
        out = fn(*c)
        if out is None:
            return m.group(0)
        changed = True
        return out

    new = _COLOR_RE.sub(sub, value)
    return new if changed else None


_KEEP_CAPS = re.compile(r"plate|vin|kbd", re.I)
_OLD_FONTS = ("space grotesk", "plus jakarta", "ibm plex mono", "var(--font-display)", "var(--font-body)",
              "var(--font-mono)", "inter")


_THICK = re.compile(r"\b(?:1\.5|2)px(?=\s+(?:solid|dashed))")


TYPE_PREFIX = "html.ap.ap"


def map_decl(prop, val, sel="", mode="color"):
    """Новое значение свойства (или None — менять нечего).
    mode="type" — только шрифт и регистр (для светлой и тёмной темы),
    mode="color" — только цвета и толщина рамок (для светлой)."""
    low = val.lower()
    if mode == "color":
        if prop in ("text-transform", "font-style", "font-family", "font", "font-weight"):
            return None
    elif _role(prop) is not None and prop not in ("font",):
        return None
    if prop in ("border", "border-top", "border-bottom", "border-left", "border-right") and _THICK.search(val):
        # толстые серые рамки (1.5–2px) у Apple — тонкие (1px); цветные (выбор) не трогаем
        col = _COLOR_RE.search(val)
        c = _parse_color(col.group(0)) if col else None
        if c is None and "var(--border)" in val or (c and _is_gray(*c[:3])):
            thin = _THICK.sub("1px", val)
            return map_color_value(prop, thin) or thin
    if prop == "text-transform" and "uppercase" in low and not _KEEP_CAPS.search(sel):
        return "none"
    if prop == "font-style" and "italic" in low:
        return "normal"
    if prop == "font-family" and "sora" not in low and any(f in low for f in _OLD_FONTS):
        return "var(--ap-font)"
    if prop == "font" and "sora" not in low and any(f in low for f in _OLD_FONTS):
        return re.sub(r"(var\(--font-(?:display|body|mono)\)|'[^']*'|\"[^\"]*\")[^;]*$", "var(--ap-font)", val)
    if prop == "font-weight" and low.strip() in ("800", "900"):
        return "700"
    return map_color_value(prop, val)


def _decls(body, sel, mode="color"):
    res = []
    caps = False
    parts = _split_top(body, ";")
    for d in parts:
        if ":" not in d:
            continue
        prop, val = d.split(":", 1)
        prop = prop.strip().lower()
        val = val.strip()
        imp = ""
        if val.lower().endswith("!important"):
            val = val[: -len("!important")].strip()
            imp = "!important"
        new = map_decl(prop, val, sel, mode)
        if prop == "text-transform" and new == "none":
            caps = True
        if new is not None:
            res.append("%s:%s%s" % (prop, new, imp))
    if caps:
        res.append("letter-spacing:normal")
    return ";".join(res)


def _prefix_selector(sel, prefix=PREFIX):
    out = []
    for s in _split_top(sel, ","):
        s = s.strip()
        if not s or s.startswith(":root") or s.startswith("@"):
            continue
        if s.startswith("html"):
            rest = s[4:]
            if rest.startswith(".gl") or rest.startswith(".in-tg"):
                continue
            out.append(prefix + rest)
        elif s.startswith("body"):
            out.append(prefix + " " + s)
        else:
            out.append(prefix + " " + s)
    return ",".join(out)


def _convert_css(css, mode="color"):
    out = []
    i = 0
    n = len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        prelude = css[i:j].strip()
        if prelude.startswith("@"):
            end = _match_brace(css, j)
            if prelude.startswith(("@media", "@supports")):
                inner = _convert_css(css[j + 1:end], mode)
                if inner:
                    out.append("%s{%s}" % (prelude, inner))
            i = end + 1
            continue
        k = css.find("}", j)
        if k < 0:
            break
        body = css[j + 1:k]
        i = k + 1
        if "${" in prelude or "${" in body or not prelude:
            continue
        sel = _prefix_selector(prelude, PREFIX if mode == "color" else TYPE_PREFIX)
        decl = _decls(body, prelude, mode)
        if sel and decl:
            out.append("%s{%s}" % (sel, decl))
    return "".join(out)


def _attr_sel(prop, decl, prefix=PREFIX):
    q = decl.replace("\\", "\\\\").replace('"', '\\"')
    if prop in ("color", "font"):
        return '{p} [style^="{q}"],{p} [style*=" {q}"],{p} [style*=";{q}"]'.format(p=prefix, q=q)
    return '%s [style*="%s"]' % (prefix, q)


def _inline_rules(markup):
    seen = {}
    for m in _INLINE_RE.finditer(markup):
        txt = m.group(1) if m.group(1) is not None else m.group(2)
        for d in txt.split(";"):
            if "${" in d or "{{" in d or ":" not in d:
                continue
            prop, val = d.split(":", 1)
            p = prop.strip().lower()
            for mode in ("type", "color"):
                new = map_decl(p, val.strip().replace("!important", "").strip(), "", mode)
                if new is None:
                    continue
                key = d.strip()
                if key and key not in seen:
                    seen[key] = (p, new, PREFIX if mode == "color" else TYPE_PREFIX)
    if _DYN_RE.search(markup):
        for hexc in sorted(set(_JS_HEX_RE.findall(markup))):
            for p in _DYNAMIC_PROPS:
                new = map_color_value(p, hexc)
                if new is None:
                    continue
                key = "%s:%s" % (p, hexc)
                if key not in seen:
                    seen[key] = (p, new, PREFIX)
    rules = []
    for decl, (p, new, pref) in seen.items():
        rules.append("%s{%s:%s!important}" % (_attr_sel(p, decl, pref), p, new))
    return "".join(rules)


def build_auto_css(page):
    css_parts = []
    for m in _STYLE_BLOCK_RE.finditer(page):
        css_parts.append(_COMMENT_RE.sub("", _JINJA_RE.sub("", m.group(1))))
    css = "\n".join(css_parts)
    return _convert_css(css, "type") + _convert_css(css, "color") + _inline_rules(page)


def js_color_map(page):
    """Цвета, которые рисует JS (графики, canvas): старый цвет → цвет Apple."""
    out = {}
    for hexc in set(re.findall(r"""['"`](#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{3})['"`]""", page)):
        c = _parse_color(hexc)
        if not c:
            continue
        new = map_accent(*c)
        if new and new.lower() != hexc.lower():
            out[hexc.lower()] = new
    return out


# ------------------------------------------------------ ручной слой CSS ----

FONT = ('-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Inter", "Segoe UI", '
        'Roboto, "Helvetica Neue", Arial, sans-serif')

MANUAL_CSS = r"""
/* ====================== общее для светлой и тёмной темы ====================== */
html.ap.ap{
  --ap-font:__FONT__;
  --font-display:var(--ap-font); --font-body:var(--ap-font); --font-mono:var(--ap-font);
  --ap-ease:cubic-bezier(.32,.72,0,1); --ap-spring:cubic-bezier(.34,1.4,.64,1);
  -webkit-text-size-adjust:100%; text-size-adjust:100%;
}
html.ap.ap body{font-family:var(--ap-font);-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;
  font-variant-numeric:tabular-nums;letter-spacing:-.01em;}
html.ap.ap input, html.ap.ap select, html.ap.ap textarea, html.ap.ap button{font-family:var(--ap-font);}
html.ap.ap .speedline{display:none;}
html.ap.ap h1, html.ap.ap h2, html.ap.ap h3, html.ap.ap h4{font-family:var(--ap-font);font-style:normal;letter-spacing:-.02em;}
/* общие правила — через :where(), чтобы не перебивать особые поля и подписи
   (поиск с лупой слева, крупная сумма в «Закрыть день» и т.п.) */
:where(html.ap) label{text-transform:none;letter-spacing:-.005em;font-size:13px;font-weight:500;}
:where(html.ap) label > i:first-child{display:none;}

/* логотип — значок приложения: синий, скруглённый, без наклона */
html.ap.ap .logo-badge{transform:none;border-radius:10px;color:#fff;
  background:linear-gradient(180deg,#3D9BFF 0%,#007AFF 55%,#0062E0 100%);
  box-shadow:inset 0 0 0 .5px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.12);}

/* --- телефон: шапка как «большой заголовок» iOS --- */
@media (max-width:899px){
  html.ap.ap .container{padding-left:16px;padding-right:16px;}
  html.ap.ap .topbar{position:sticky;top:0;z-index:45;margin:0 -16px 10px;padding:calc(10px + env(safe-area-inset-top,0px)) 16px 10px;
    -webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px);}
  html.ap.ap .topbar .logo-badge{width:36px;height:36px;font-size:16px;border-radius:9px;}
  html.ap.ap .topbar h1{font-size:22px;font-weight:700;letter-spacing:-.025em;line-height:1.15;}
  html.ap.ap .topbar .brand-line{margin-top:1px;}
  html.ap.ap .lang-btn{border:0;border-radius:999px;font-size:13px;font-weight:600;padding:6px 12px;min-height:30px;}
  /* нижняя панель — Tab Bar iPhone */
  html.ap.ap .bottom-bar{padding:5px 2px calc(4px + env(safe-area-inset-bottom,0px));box-shadow:none;border-top:0;
    -webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px);}
  html.ap.ap .bb-item{font-size:10px;font-weight:500;letter-spacing:.01em;gap:2px;min-height:49px;justify-content:center;
    transition:color .2s,transform .3s var(--ap-spring);}
  html.ap.ap .bb-item i{font-size:21px;line-height:26px;}
  html.ap.ap .bb-item:active{transform:scale(.92);}
  html.ap.ap .bb-item.active:not(.bb-add)::before{display:none;}
  html.ap.ap .bb-plus{width:50px;height:50px;margin-top:-20px;border:0;font-size:22px;transition:transform .35s var(--ap-spring);}
  html.ap.ap .bb-add:active .bb-plus{transform:scale(.9);}
  html.ap.ap .bb-add span{font-weight:600;}
  html.ap.ap .container{padding-bottom:calc(100px + env(safe-area-inset-bottom,0px));}
}
/* планшет (600–899): панель вкладок — плавающая «капсула» по центру, как на iPad */
@media (min-width:600px) and (max-width:899px){
  html.ap.ap .bottom-bar{left:50%;right:auto;width:min(560px,calc(100% - 48px));transform:translateX(-50%);
    bottom:calc(14px + env(safe-area-inset-bottom,0px));border-radius:26px;padding:6px 8px;}
  html.ap.ap .container{max-width:760px;padding-bottom:calc(120px + env(safe-area-inset-bottom,0px));}
  html.ap.ap .more-sheet{left:50%;right:auto;width:min(600px,100%);transform:translate(-50%,105%);}
  html.ap.ap .more-sheet.open{transform:translate(-50%,0);}
}

/* --- компьютер: боковое меню как на iPad/Mac --- */
@media (min-width:900px){
  html.ap.ap .side-nav{top:0;width:260px;padding:18px 12px 14px;
    -webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px);}
  html.ap.ap .container{margin-left:260px;padding-left:36px;padding-right:36px;padding-top:26px;}
  html.ap.ap .side-brand{border-bottom:0;padding:2px 8px 14px;margin-bottom:2px;gap:11px;}
  html.ap.ap .side-brand .logo-badge{width:38px;height:38px;border-radius:9px;background:linear-gradient(180deg,#3D9BFF 0%,#007AFF 55%,#0062E0 100%);}
  html.ap.ap .side-shop{font-size:15px;font-weight:600;letter-spacing:-.015em;}
  html.ap.ap .side-list{gap:2px;}
  html.ap.ap .side-group{font-size:12px;font-weight:600;letter-spacing:0;text-transform:none;padding:16px 10px 5px;}
  html.ap.ap .side-item{padding:7px 10px;border-radius:8px;font-size:14px;font-weight:500;gap:11px;transition:background .15s,color .15s;}
  html.ap.ap .side-item i{width:20px;font-size:15px;}
  html.ap.ap .side-add{font-size:14px;font-weight:600;padding:10px 12px;border-radius:10px;margin:6px 0 2px;box-shadow:none;}
  html.ap.ap .side-kbd{font-family:var(--ap-font);font-size:11px;border-radius:5px;}
  html.ap.ap .side-foot{border-top:0;padding-top:10px;gap:6px;}
  html.ap.ap .side-foot .lang-btn, html.ap.ap .side-foot .logout{border:0;border-radius:8px;font-size:13px;font-weight:500;padding:8px 10px;}
}

/* --- карточки и заголовки --- */
html.ap.ap .card{border:0;border-radius:18px;padding:18px;}
html.ap.ap .card-header{background:none;margin:-4px 0 14px;padding:0;border-radius:0;gap:10px;}
html.ap.ap .card-header h3{font-size:20px;font-weight:700;text-transform:none;letter-spacing:-.02em;}
html.ap.ap .card-header .dot{display:none;}

/* --- поля ввода --- */
html.ap.ap input, html.ap.ap select, html.ap.ap textarea{transition:border-color .15s,box-shadow .15s,background-color .15s;}
:where(html.ap) input, :where(html.ap) select, :where(html.ap) textarea{border-radius:10px;font-size:16px;padding:11px 12px;}
html.ap.ap input[type=checkbox], html.ap.ap input[type=radio]{accent-color:#007AFF;}
html.ap.ap select:not([multiple]):not([size]){-webkit-appearance:none;appearance:none;padding-right:34px;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1.5l5 5 5-5' fill='none' stroke='%238E8E93' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")!important;
  background-repeat:no-repeat!important;background-position:right 12px center!important;background-size:12px 8px!important;}

/* --- кнопки --- */
html.ap.ap button.submit{border-radius:12px;font-size:17px;font-weight:600;letter-spacing:-.01em;text-transform:none;padding:14px;
  transition:transform .3s var(--ap-spring),filter .15s;}
html.ap.ap button.submit:active{transform:scale(.97);filter:brightness(.92);}

/* --- сегменты (подвкладки) — Segmented Control --- */
html.ap.ap .subtabs{gap:0;padding:2px;border-radius:10px;flex-wrap:wrap;}
html.ap.ap .subtab{border:0;border-radius:8px;padding:8px 8px;font-size:13px;font-weight:600;letter-spacing:-.005em;min-height:34px;
  transition:background .2s,color .2s,box-shadow .2s;}
html.ap.ap .pc-tabs button, html.ap.ap .pr-seg button{border-radius:8px;}

/* --- таблицы --- */
html.ap.ap th{font-size:12px;font-weight:600;text-transform:none;letter-spacing:0;}
:where(html.ap) th, :where(html.ap) td{padding:10px 10px;}
html.ap.ap .table-wrap{border-radius:14px;}
html.ap.ap .badge{text-transform:none;letter-spacing:0;font-size:12px;}

/* --- окна --- */
html.ap.ap .modal{border:0;border-radius:20px;padding:22px;}
html.ap.ap .modal-overlay{-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px);}

/* --- движение: короткое появление раздела при открытии --- */
@keyframes apIn{from{opacity:0;transform:translate3d(0,8px,0)}to{opacity:1;transform:none}}
html.ap:not(.gl) .gl-enter > *{animation:apIn .32s var(--ap-ease) both;}
html.ap:not(.gl) .gl-enter > *:nth-child(2){animation-delay:.03s}
html.ap:not(.gl) .gl-enter > *:nth-child(n+3){animation-delay:.06s}

/* =============================== светлая =============================== */
html.ap:not(.gl){color-scheme:light;
  --bg:#F2F2F7; --text:#1D1D1F; --hint:#8E8E93; --btn:#FF3B30; --btn-text:#fff; --blue:#007AFF; --darkblue:#1D1D1F;
  --cyan:#32ADE6; --darkred:#D70015; --carbon:#1C1C1E; --card:#FFFFFF; --border:#E5E5EA; --field-bg:#F2F2F7;
  --ok:#248A3D; --ok-bg:#E8F8EC; --danger:#D70015; --danger-bg:#FFECEB; --accent2:#007AFF;
  --ap-label:#1D1D1F; --ap-2:#6E6E73; --ap-3:#8E8E93; --ap-sep:rgba(60,60,67,.18); --ap-fill:rgba(118,118,128,.12);
  background:#F2F2F7;}
html.ap:not(.gl) body{background:#F2F2F7;color:#1D1D1F;}
html.ap:not(.gl) ::selection{background:rgba(0,122,255,.22);}
html.ap:not(.gl) .wordmark .wm-oil{background:none;-webkit-background-clip:initial;background-clip:initial;color:#007AFF;}
html.ap:not(.gl) .wordmark .wm-book{color:#1D1D1F;}
html.ap:not(.gl) h1, html.ap:not(.gl) h2, html.ap:not(.gl) h3{color:#1D1D1F;}
html.ap:not(.gl) label{color:#6E6E73;}
html.ap:not(.gl) .role-tag{color:#C93400;}
@media (max-width:899px){
  html.ap:not(.gl) .topbar{background:rgba(242,242,247,.82);box-shadow:0 .5px 0 rgba(0,0,0,.1);}
  html.ap:not(.gl) .lang-btn{background:rgba(118,118,128,.12);color:#007AFF;}
  html.ap:not(.gl) .bottom-bar{background:rgba(250,250,252,.86);box-shadow:0 -.5px 0 rgba(0,0,0,.16);}
  html.ap:not(.gl) .bb-item{color:#8E8E93;}
  html.ap:not(.gl) .bb-item.active{color:#007AFF;}
  html.ap:not(.gl) .bb-plus{background:#FF3B30;box-shadow:0 4px 14px rgba(255,59,48,.35);}
  html.ap:not(.gl) .bb-add span, html.ap:not(.gl) .bb-add.active span{color:#FF3B30;}
}
@media (min-width:600px) and (max-width:899px){
  html.ap:not(.gl) .bottom-bar{background:rgba(255,255,255,.82);box-shadow:0 0 0 .5px rgba(0,0,0,.08),0 10px 30px rgba(0,0,0,.12);}
}
@media (min-width:900px){
  html.ap:not(.gl) .side-nav{background:rgba(246,246,248,.92);color:#1D1D1F;box-shadow:inset -.5px 0 0 rgba(0,0,0,.12);scrollbar-color:#D1D1D6 transparent;}
  html.ap:not(.gl) .side-shop{color:#1D1D1F;}
  html.ap:not(.gl) .side-brand .wordmark .wm-oil{color:#007AFF;}
  html.ap:not(.gl) .side-brand .wordmark .wm-book{color:#1D1D1F;}
  html.ap:not(.gl) .side-brand .role-tag{color:#C93400;}
  html.ap:not(.gl) .side-group{color:#8E8E93;}
  html.ap:not(.gl) .side-item{color:#1D1D1F;}
  html.ap:not(.gl) .side-item i{color:#007AFF;}
  html.ap:not(.gl) .side-item:hover{background:rgba(0,0,0,.05);color:#1D1D1F;}
  html.ap:not(.gl) .side-item.active{background:#007AFF;color:#fff;}
  html.ap:not(.gl) .side-item.active i{color:#fff;}
  html.ap:not(.gl) .side-add, html.ap:not(.gl) .side-add.active{background:#FF3B30;color:#fff;box-shadow:none;}
  html.ap:not(.gl) .side-add:hover{background:#F2362C;}
  html.ap:not(.gl) .side-add i{color:#fff;}
  html.ap:not(.gl) .side-kbd{background:rgba(255,255,255,.25);color:#fff;}
  html.ap:not(.gl) .side-foot .lang-btn{background:rgba(118,118,128,.12);color:#007AFF;}
  html.ap:not(.gl) .side-foot .logout{background:transparent;color:#FF3B30;}
}
html.ap:not(.gl) .card{background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04),0 0 0 .5px rgba(0,0,0,.03);}
html.ap:not(.gl) .card-header{color:#1D1D1F;}
html.ap:not(.gl) .card-header i{color:#007AFF;}
html.ap:not(.gl) input::placeholder, html.ap:not(.gl) textarea::placeholder{color:#AEAEB2;}
html.ap:not(.gl) input:focus, html.ap:not(.gl) select:focus, html.ap:not(.gl) textarea:focus{background-color:#fff;border-color:#007AFF;box-shadow:0 0 0 3px rgba(0,122,255,.18);}
html.ap:not(.gl) button.submit{background:#007AFF;box-shadow:none;color:#fff;}
html.ap:not(.gl) .subtabs{background:rgba(118,118,128,.12);}
html.ap:not(.gl) .subtab{background:transparent;color:#1D1D1F;}
html.ap:not(.gl) .subtab.active{background:#fff;color:#1D1D1F;box-shadow:0 3px 8px rgba(0,0,0,.12),0 3px 1px rgba(0,0,0,.04),0 0 0 .5px rgba(0,0,0,.04);}
html.ap:not(.gl) th{background:#F9F9FB;color:#6E6E73;border-bottom:.5px solid rgba(60,60,67,.2);}
html.ap:not(.gl) td{border-bottom:.5px solid rgba(60,60,67,.14);}
html.ap:not(.gl) .table-wrap{border:0;background:#fff;box-shadow:0 0 0 .5px rgba(0,0,0,.06);}
html.ap:not(.gl) .modal{background:#fff;box-shadow:0 24px 64px rgba(0,0,0,.22);}
html.ap:not(.gl) .modal-overlay{background:rgba(0,0,0,.32);}
html.ap:not(.gl) .more-backdrop{background:rgba(0,0,0,.32);}
html.ap:not(.gl) .nav-badge{background:#FF3B30;color:#fff;}

/* --- главные карточки на сером фоне: без рамки, мягкая тень --- */
html.ap.ap .af-sec, html.ap.ap .dp, html.ap.ap .st-card, html.ap.ap .st-today{border:0;border-radius:18px;}
html.ap:not(.gl) .af-sec, html.ap:not(.gl) .dp, html.ap:not(.gl) .st-card, html.ap:not(.gl) .st-today{box-shadow:0 1px 2px rgba(0,0,0,.04),0 0 0 .5px rgba(0,0,0,.03);}
/* сегменты «Неделя / Месяц / Год» */
html.ap.ap .pc-tabs{gap:0;padding:2px;border-radius:10px;}
html.ap.ap .pc-tabs button{height:34px;border-radius:8px;font-size:13.5px;font-weight:600;}
html.ap:not(.gl) .pc-tabs{background:rgba(118,118,128,.12);}
html.ap:not(.gl) .pc-tabs button{color:#1D1D1F;}
html.ap:not(.gl) .pc-tabs button.on, html.ap:not(.gl) .st-card.orange .pc-tabs button.on{background:#fff;color:#1D1D1F;box-shadow:0 3px 8px rgba(0,0,0,.12),0 3px 1px rgba(0,0,0,.04);}
html.ap.gl .pc-tabs{background:rgba(118,118,128,.24);}
html.ap.gl .pc-tabs button.on, html.ap.gl .st-card.orange .pc-tabs button.on{background:#636366;color:#fff;box-shadow:none;}
/* заголовок раздела «Внести замену» — крупный, как в iOS */
html.ap.ap .af-title{font-size:28px;font-weight:700;letter-spacing:-.025em;margin:6px 2px 14px;}
html.ap.ap .af-title .dot{display:none;}
html.ap.ap .af-t{flex:1 0 auto;}
html.ap.ap .af-price{border:0;min-height:34px;padding:0 13px;font-size:14px;font-weight:600;}
html.ap:not(.gl) .af-title{color:#1D1D1F;}
html.ap:not(.gl) .af-price{background:rgba(0,122,255,.1);color:#007AFF;}
html.ap.gl .af-price{background:rgba(10,132,255,.18);color:#0A84FF;border:0;}
@media (max-width:480px){ html.ap.ap .af-title{font-size:24px;} }
html.ap.ap .af-h{font-size:17px;font-weight:600;letter-spacing:-.015em;}
html.ap.ap .af-h i{border-radius:8px;}
html.ap.ap .af-bar{border:0;border-radius:16px;}
html.ap:not(.gl) .af-bar{background:rgba(255,255,255,.92);box-shadow:0 0 0 .5px rgba(0,0,0,.06),0 8px 28px rgba(0,0,0,.12);
  -webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px);}
@media (max-width:899px){ html.ap.ap .af-bar{bottom:calc(64px + env(safe-area-inset-bottom,0px));} }
@media (min-width:600px) and (max-width:899px){ html.ap.ap .af-bar{bottom:calc(86px + env(safe-area-inset-bottom,0px));} }

html.ap.ap .ig-health-h, html.ap.ap .ig-wd-h{text-transform:none;letter-spacing:-.005em;font-size:13px;font-weight:600;}
html.ap.ap .ig-health, html.ap.ap .ig-wd-wrap{border:0;}
html.ap.gl .af-bar{background:#1C1C1E;border:0;box-shadow:0 0 0 .5px rgba(255,255,255,.1),0 8px 28px rgba(0,0,0,.5);}

/* --- «База»: кому пора на замену --- */
html.ap.ap .bd-card{border:0;border-radius:18px;padding:16px;}
html.ap.ap .bd-head b{font-size:17px;font-weight:700;letter-spacing:-.02em;}
html.ap.ap .bd-tabs button{border:0;padding:7px 13px;font-weight:600;}
html.ap.ap .bd-row{border-top-style:solid;border-top-width:.5px;}
html.ap.ap .bd-b{border:0;border-radius:999px;padding:8px 11px;gap:5px;}
html.ap.ap .bd-r{border:0;padding:6px 11px;}
html.ap.ap .bd-act{gap:6px;}
html.ap:not(.gl) .bd-card{background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04);}
html.ap:not(.gl) .bd-tabs button{background:rgba(118,118,128,.12);color:#1D1D1F;}
html.ap:not(.gl) .bd-tabs button em{background:rgba(255,255,255,.8);}
html.ap:not(.gl) .bd-tabs button.on{background:#007AFF;color:#fff;}
html.ap:not(.gl) .bd-tabs button.on em{background:rgba(255,255,255,.25);color:#fff;}
html.ap:not(.gl) .bd-row{border-top-color:rgba(60,60,67,.16);}
html.ap:not(.gl) .bd-b{background:rgba(118,118,128,.12);color:#1D1D1F;}
html.ap:not(.gl) .bd-b.call{background:#34C759;color:#fff;}
html.ap:not(.gl) .bd-b.wa{background:#E8F8EC;color:#248A3D;}
html.ap:not(.gl) .bd-b.tg{background:#E6F5FC;color:#0071A4;}
html.ap:not(.gl) .bd-b.bot{background:#E5F1FF;color:#007AFF;}
html.ap:not(.gl) .bd-r{background:rgba(118,118,128,.1);color:#6E6E73;}
html.ap:not(.gl) .bd-r.on{background:#E5F1FF;color:#007AFF;}
html.ap.gl .bd-card{background:#1C1C1E;border:0;}
html.ap.gl .bd-tabs button, html.ap.gl .bd-b, html.ap.gl .bd-r{background:rgba(118,118,128,.24);}
html.ap.gl .bd-tabs button.on{background:#0A84FF;color:#fff;}
html.ap.gl .bd-b.call{background:#30D158;color:#000;}

/* ========================= тёмная (iOS Dark) =========================
   Слой glass_theme (html.gl) уже перевёл все цвета в тёмные; здесь — вместо
   цветных пятен и стекла — спокойная тёмная палитра Apple. */
html.ap.gl{--gl-bg:#000; --gl-surface:#1C1C1E; --gl-line:rgba(84,84,88,.36); --gl-line-2:rgba(84,84,88,.5);
  --gl-text:#F5F5F7; --gl-muted:rgba(235,235,245,.6); --gl-accent:#0A84FF; --gl-red:#FF453A;
  --gl-spec:none; --gl-shadow:none; --blue:#0A84FF; --btn:#FF453A; --accent2:#0A84FF; --card:#1C1C1E;
  --ok:#30D158; --danger:#FF6961; background:#000;}
html.ap.gl .card, html.ap.gl .af-sec, html.ap.gl .af-rcpt, html.ap.gl .st-card, html.ap.gl .st-today,
html.ap.gl .known-client, html.ap.gl .cross-network-card, html.ap.gl .dp{background:#1C1C1E;background-image:none;border:0;box-shadow:none;}
html.ap.gl .st-today::after{display:none;}
html.ap.gl .card-header{background:none;border-bottom:0;}
html.ap.gl .card-header i{color:#0A84FF;}
html.ap.gl input, html.ap.gl select, html.ap.gl textarea{background-color:#2C2C2E;border-color:transparent;}
html.ap.gl input:focus, html.ap.gl select:focus, html.ap.gl textarea:focus{border-color:#0A84FF;box-shadow:0 0 0 3px rgba(10,132,255,.3);background-color:#2C2C2E;}
html.ap.gl button.submit{background:#0A84FF;box-shadow:none;}
html.ap.gl .af-save, html.ap.gl .sv-next{background:#FF453A;box-shadow:none;}
html.ap.gl .subtabs{background:rgba(118,118,128,.24);}
html.ap.gl .subtab{background:transparent;border:0;color:#F5F5F7;box-shadow:none;}
html.ap.gl .subtab.active{background:#636366;color:#fff;box-shadow:0 3px 8px rgba(0,0,0,.3);}
html.ap.gl .logo-badge{background:linear-gradient(180deg,#409CFF,#0A84FF);box-shadow:none;}
html.ap.gl .wordmark .wm-oil{background:none;-webkit-background-clip:initial;background-clip:initial;color:#0A84FF;}
@media (max-width:899px){
  html.ap.gl .topbar{background:rgba(0,0,0,.72);border:0;border-radius:0;box-shadow:0 .5px 0 rgba(255,255,255,.12);}
  html.ap.gl .bottom-bar{left:0;right:0;bottom:0;border-radius:0;border:0;padding:5px 2px calc(4px + env(safe-area-inset-bottom,0px));
    background:rgba(22,22,24,.86);box-shadow:0 -.5px 0 rgba(255,255,255,.14);}
  html.ap.gl .bb-item{color:rgba(235,235,245,.6);}
  html.ap.gl .bb-item.active{color:#0A84FF;}
  html.ap.gl .bb-plus{background:#FF453A;box-shadow:0 4px 14px rgba(255,69,58,.35);}
  html.ap.gl .bb-add span{color:#FF453A;}
  html.ap.gl .lang-btn{background:rgba(118,118,128,.24);border:0;color:#0A84FF;}
}
@media (min-width:600px) and (max-width:899px){
  html.ap.gl .bottom-bar{left:50%;right:auto;bottom:calc(14px + env(safe-area-inset-bottom,0px));border-radius:26px;padding:6px 8px;
    box-shadow:0 0 0 .5px rgba(255,255,255,.12),0 10px 30px rgba(0,0,0,.5);}
}
@media (min-width:900px){
  html.ap.gl .side-nav{top:0;left:0;bottom:0;width:260px;border-radius:0;border:0;background:rgba(28,28,30,.92);box-shadow:inset -.5px 0 0 rgba(255,255,255,.1);}
  html.ap.gl .container{margin-left:260px;}
  html.ap.gl .side-item{color:#F5F5F7;border-radius:8px;}
  html.ap.gl .side-item i{color:#0A84FF;}
  html.ap.gl .side-item:hover{background:rgba(255,255,255,.07);}
  html.ap.gl .side-item.active{background:#0A84FF;color:#fff;box-shadow:none;}
  html.ap.gl .side-item.active i{color:#fff;}
  html.ap.gl .side-add, html.ap.gl .side-add.active{background:#FF453A;box-shadow:none;}
  html.ap.gl .side-group{color:rgba(235,235,245,.45);}
  html.ap.gl .side-foot .lang-btn{background:rgba(118,118,128,.24);border:0;color:#0A84FF;}
}
html.ap.gl .more-sheet{background:#000;border-top:0;box-shadow:none;}
html.ap.gl .more-head, html.ap.gl .more-gl{background:#1C1C1E;}
html.ap.gl .more-head-t b{color:#F5F5F7;}
html.ap.gl .more-gh{color:rgba(235,235,245,.6);}
html.ap.gl .more-item{color:#F5F5F7;border:0;}
html.ap.gl .more-item::after{background:rgba(84,84,88,.6);}
html.ap.gl .more-item:active{background:#2C2C2E;}
html.ap.gl .more-item .mi-ic i{color:#fff;}
html.ap.gl .more-item.active .mi-t{color:#0A84FF;}
html.ap.gl .more-logout{color:#FF453A;}
html.ap.gl .more-x{background:rgba(118,118,128,.24);color:rgba(235,235,245,.6);}
html.ap.gl .modal{background:#1C1C1E;border:0;}
html.ap.gl th{background:#1C1C1E;}
html.ap.gl .speedline{display:none;}

/* ================== «Жидкое стекло» Apple (iOS 26 / macOS) ==================
   Правила, чтобы прозрачность не мешала работе с данными:
   1) Размытие (backdrop-filter) — ТОЛЬКО у «рамки» приложения: шапка, панель
      вкладок, боковое меню, шторки, окна, полоса «Итого». Под ними двигается
      содержимое — стекло там уместно и почти ничего не стоит.
   2) Карточки с данными — «матовые»: белые на 76% без размытия. Фон за ними
      неподвижный и мягкий, поэтому цифры всегда на почти белом.
   3) Списки, таблицы, выпадающие подсказки, меню и полоса «Итого» — сплошные
      (100%): там читают строки и цифры, и ничего не должно просвечивать.
   4) Текст на стекле — темнее обычного серого (#3A3A3C вместо #8E8E93), чтобы
      контраст не падал, когда под стеклом что-то яркое.
   5) Слабый телефон и «Уменьшить прозрачность» в системе — всё сплошное. */
html.ap{--gx-card:rgba(255,255,255,.76);--gx-card-edge:rgba(255,255,255,.75);
  --gx-chrome:rgba(250,250,253,.72);--gx-blur:saturate(190%) blur(30px);
  --gx-shadow:0 1px 1px rgba(0,0,0,.03),0 10px 30px rgba(28,39,72,.07);
  --gx-hl:inset 0 1px 0 rgba(255,255,255,.9),inset 0 0 0 .5px rgba(255,255,255,.55);}
html.ap:not(.gl), html.ap:not(.gl) body{background:#EDF0F7;}
html.ap:not(.gl) body{background:transparent;}
/* фон — неподвижные мягкие пятна (обычные градиенты: без анимации и без filter) */
html.ap body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;}
html.ap:not(.gl) body::before{background:
  radial-gradient(55vmax 45vmax at 0% 0%, rgba(122,184,255,.42), transparent 62%),
  radial-gradient(45vmax 40vmax at 100% 18%, rgba(120,226,222,.30), transparent 64%),
  radial-gradient(50vmax 42vmax at 85% 100%, rgba(255,196,168,.32), transparent 62%),
  radial-gradient(42vmax 38vmax at 8% 82%, rgba(196,182,255,.30), transparent 64%),
  #EDF0F7;}

/* матовые карточки с данными */
html.ap:not(.gl) :is(.card,.af-sec,.af-rcpt,.dp,.st-card,.st-today,.bd-card,.car-card,.debt-card,.pr-card,.dc-card,
  .uo-tile,.known-client,.cross-network-card,.q-col,.q-add,.an-card,.ws-cart,.whc,.sp-list,.sp-orders,.sp-det,.sp-form,
  .cash-card,.tm-card,.tm-tile,.sv-card,.oc-list){
  background-color:var(--gx-card);background-image:none;border:1px solid var(--gx-card-edge);
  box-shadow:var(--gx-shadow),var(--gx-hl);}
/* то, что читают строками, — сплошное */
html.ap:not(.gl) :is(.table-wrap,.plate-suggest,.sup-menu,.ps-list,.pick-results .pick-item){background-color:#fff;}
html.ap:not(.gl) .table-wrap{box-shadow:var(--gx-shadow);}
html.ap:not(.gl) th{background:#F7F8FB;}

/* «рамка» приложения — настоящее стекло */
@media (max-width:899px){
  html.ap:not(.gl) .topbar{background:rgba(237,240,247,.66);-webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);
    box-shadow:0 .5px 0 rgba(0,0,0,.08);}
  /* панель вкладок — плавающая «капсула», как в iOS 26 */
  html.ap.ap .bottom-bar{left:12px;right:12px;bottom:calc(8px + env(safe-area-inset-bottom,0px));border-radius:30px;
    padding:6px 6px;grid-template-columns:repeat(5,minmax(0,1fr));}
  html.ap:not(.gl) .bottom-bar{background:var(--gx-chrome);border:.5px solid rgba(255,255,255,.7);
    -webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);
    box-shadow:0 10px 34px rgba(28,39,72,.16),0 1px 2px rgba(0,0,0,.06),inset 0 1px 0 rgba(255,255,255,.85);}
  html.ap.ap .bb-item{border-radius:22px;min-height:50px;}
  html.ap:not(.gl) .bb-item{color:#3A3A3C;}
  /* выбранная вкладка — «линза» за значком */
  html.ap:not(.gl) .bb-item.active:not(.bb-add){color:#007AFF;background:rgba(118,118,128,.13);}
  html.ap.ap .bb-plus{margin-top:0;width:34px;height:34px;font-size:16px;border-radius:12px;}
  html.ap.ap .bb-plus i{font-size:16px;}
  html.ap:not(.gl) .bb-plus{background:linear-gradient(180deg,#FF5F55,#FF3B30);box-shadow:0 4px 12px rgba(255,59,48,.35),inset 0 1px 0 rgba(255,255,255,.35);}
  html.ap.ap .container{padding-bottom:calc(108px + env(safe-area-inset-bottom,0px));}
  html.ap.ap .af-bar{bottom:calc(84px + env(safe-area-inset-bottom,0px));}
}
@media (min-width:600px) and (max-width:899px){
  html.ap.ap .bottom-bar{left:50%;right:auto;width:min(520px,calc(100% - 48px));transform:translateX(-50%);bottom:calc(14px + env(safe-area-inset-bottom,0px));}
  html.ap.ap .af-bar{bottom:calc(92px + env(safe-area-inset-bottom,0px));}
}
html.ap:not(.gl) .af-bar{background:#fff;border:.5px solid rgba(255,255,255,.8);
  -webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);
  box-shadow:0 10px 30px rgba(28,39,72,.14),inset 0 1px 0 rgba(255,255,255,.9);}
/* шторки и окна: стекло, но плотное — под ними не видно текста страницы */
html.ap:not(.gl) .more-sheet{background:rgba(242,242,247,.86);-webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);
  box-shadow:0 -12px 40px rgba(28,39,72,.16),inset 0 1px 0 rgba(255,255,255,.8);}
html.ap:not(.gl) .more-head, html.ap:not(.gl) .more-gl{background:rgba(255,255,255,.9);}
html.ap:not(.gl) .more-backdrop, html.ap:not(.gl) .modal-overlay{background:rgba(20,24,40,.22);}
html.ap:not(.gl) .modal{background:rgba(255,255,255,.92);-webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);
  border:.5px solid rgba(255,255,255,.8);box-shadow:0 30px 80px rgba(28,39,72,.25),inset 0 1px 0 rgba(255,255,255,.9);}
/* сегменты — стеклянная дорожка */
html.ap:not(.gl) :is(.subtabs,.pc-tabs){background:rgba(118,118,128,.12);box-shadow:inset 0 .5px 0 rgba(0,0,0,.04);}
html.ap:not(.gl) .subtab.active, html.ap:not(.gl) .pc-tabs button.on{background:#fff;box-shadow:0 3px 10px rgba(0,0,0,.1),0 0 0 .5px rgba(0,0,0,.04);}
/* кнопки-«стёкла» (Цена, Очередь, язык) */
html.ap:not(.gl) .af-price, html.ap:not(.gl) .lang-btn{background:rgba(255,255,255,.6);color:#007AFF;
  box-shadow:0 1px 3px rgba(0,0,0,.06),inset 0 0 0 .5px rgba(255,255,255,.8);}
/* поля ввода на матовых карточках — светлая заливка с тонкой рамкой (видно границы) */
html.ap:not(.gl) :is(.card,.af-sec,.dc-card,.pr-card,.sp-form) :is(input,select,textarea):not([type=checkbox]):not([type=radio]){
  background-color:rgba(255,255,255,.85);border-color:rgba(60,60,67,.14);}
html.ap:not(.gl) :is(.card,.af-sec,.dc-card,.pr-card,.sp-form) :is(input,select,textarea):focus{background-color:#fff;border-color:#007AFF;}

/* компьютер: боковое меню — плавающая стеклянная панель */
@media (min-width:900px){
  html.ap.ap .side-nav{top:12px;left:12px;bottom:12px;width:256px;border-radius:24px;}
  html.ap.ap .container{margin-left:280px;}
  html.ap:not(.gl) .side-nav{background:rgba(250,250,253,.6);-webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);
    border:.5px solid rgba(255,255,255,.75);box-shadow:0 14px 44px rgba(28,39,72,.12),inset 0 1px 0 rgba(255,255,255,.85);}
  html.ap:not(.gl) .side-item:hover{background:rgba(118,118,128,.12);}
  html.ap:not(.gl) .side-item.active{box-shadow:0 4px 12px rgba(0,122,255,.3);}
  html.ap.ap .side-foot .lang-btn{box-shadow:none;}
}

/* --- тёмное стекло --- */
html.ap.gl{--gx-card:rgba(30,30,34,.74);--gx-card-edge:rgba(255,255,255,.07);}
html.ap.gl body::before{background:
  radial-gradient(55vmax 45vmax at 0% 0%, rgba(10,132,255,.22), transparent 62%),
  radial-gradient(45vmax 40vmax at 100% 25%, rgba(100,210,255,.12), transparent 64%),
  radial-gradient(48vmax 40vmax at 80% 100%, rgba(255,120,90,.12), transparent 62%),
  radial-gradient(42vmax 38vmax at 6% 85%, rgba(140,110,255,.16), transparent 64%),
  #000;}
html.ap.gl :is(.card,.af-sec,.af-rcpt,.dp,.st-card,.st-today,.bd-card,.car-card,.debt-card,.pr-card,.dc-card,
  .uo-tile,.known-client,.cross-network-card,.q-col,.q-add,.an-card,.ws-cart,.whc,.sp-list,.sp-orders,.sp-det,.sp-form,
  .cash-card,.tm-card,.tm-tile,.sv-card,.oc-list){
  background-color:var(--gx-card);background-image:none;border:1px solid var(--gx-card-edge);box-shadow:inset 0 1px 0 rgba(255,255,255,.06);}
html.ap.gl :is(.table-wrap,.plate-suggest){background-color:#1C1C1E;}
@media (max-width:899px){
  html.ap.gl .topbar{background:rgba(0,0,0,.5);-webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);}
  html.ap.gl .bottom-bar{background:rgba(36,36,40,.72);border:.5px solid rgba(255,255,255,.1);
    -webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);
    box-shadow:0 10px 34px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.08);}
  html.ap.gl .bb-item{color:rgba(235,235,245,.75);}
  html.ap.gl .bb-item.active:not(.bb-add){color:#0A84FF;background:rgba(118,118,128,.26);}
}
@media (min-width:600px) and (max-width:899px){
  html.ap.gl .bottom-bar{left:50%;right:auto;}
}
@media (min-width:900px){
  html.ap.gl .side-nav{top:12px;left:12px;bottom:12px;border-radius:24px;background:rgba(30,30,34,.6);
    -webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);border:.5px solid rgba(255,255,255,.1);}
  html.ap.gl .container{margin-left:280px;}
}
html.ap.gl .more-sheet{background:rgba(18,18,20,.86);-webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);}
html.ap.gl .modal{background:rgba(36,36,40,.92);-webkit-backdrop-filter:var(--gx-blur);backdrop-filter:var(--gx-blur);}

/* «Уменьшить прозрачность» в системе — всё сплошное */
@media (prefers-reduced-transparency:reduce){
  html.ap:not(.gl) :is(.topbar,.bottom-bar,.side-nav,.more-sheet,.modal,.af-bar){background:#F9F9FB;-webkit-backdrop-filter:none;backdrop-filter:none;}
  html.ap:not(.gl) :is(.card,.af-sec,.dp,.st-card,.st-today,.bd-card,.car-card){background-color:#fff;}
}

/* слабый телефон: без размытия */
html.ap.gl-lite :is(.topbar,.bottom-bar,.side-nav,.modal-overlay,.modal,.more-sheet,.af-bar){-webkit-backdrop-filter:none;backdrop-filter:none;}
html.ap.gl-lite:not(.gl) .topbar{background:rgba(237,240,247,.97);}
html.ap.gl-lite:not(.gl) :is(.bottom-bar,.side-nav,.modal){background:rgba(252,252,254,.97);}
html.ap.gl-lite:not(.gl) .more-sheet{background:#F2F2F7;}
html.ap.gl-lite.gl :is(.topbar,.bottom-bar,.side-nav,.more-sheet,.modal){background:#1C1C1E;}
html.ap.gl-lite *, html.ap.gl-lite *::before, html.ap.gl-lite *::after{animation:none!important;}
@media (prefers-reduced-motion:reduce){
  html.ap *, html.ap *::before, html.ap *::after{animation:none!important;transition-duration:.01s!important;}
}
""".replace("__FONT__", FONT)

APPLE_JS = r"""
(function(){
  var root = document.documentElement;
  var MAP = __MAP__;
  function light(){ return root.classList.contains('ap') && !root.classList.contains('gl'); }
  window.apColor = function(c){ return (light() && typeof c === 'string' && MAP[c.toLowerCase()]) || c; };
  window.apChartTheme = function(){
    if (typeof Chart === 'undefined' || Chart._apDone || !light()) return;
    Chart._apDone = true;
    function mArr(v){ return Array.isArray(v) ? v.map(apColor) : apColor(v); }
    Chart.register({ id: 'apTheme', beforeInit: function(chart){
      var o = chart.options, d = chart.config.data;
      (d.datasets || []).forEach(function(ds){
        ['backgroundColor','hoverBackgroundColor','borderColor','pointBackgroundColor'].forEach(function(k){ if (ds[k] && typeof ds[k] !== 'function') ds[k] = mArr(ds[k]); });
      });
      var sc = o.scales || {};
      Object.keys(sc).forEach(function(k){ var s = sc[k];
        if (s.grid) s.grid.color = 'rgba(60,60,67,.1)';
        if (s.ticks) s.ticks.color = '#8E8E93'; });
      var t = o.plugins && o.plugins.tooltip;
      if (t) { t.backgroundColor = 'rgba(255,255,255,.98)'; t.borderColor = 'rgba(0,0,0,.08)'; t.borderWidth = 1;
        t.titleColor = '#1D1D1F'; t.bodyColor = '#3A3A3C'; t.cornerRadius = 12; t.padding = 10; }
    }});
    Chart.defaults.font.family = getComputedStyle(root).getPropertyValue('--ap-font') || Chart.defaults.font.family;
    Chart.defaults.color = '#8E8E93';
    Chart.defaults.borderColor = 'rgba(60,60,67,.1)';
  };
})();
"""

# ранний скрипт в <head>: классы ставятся ДО отрисовки — без вспышки
HEAD_BOOT = """<script>
(function(){var d=document.documentElement,t=null;try{t=localStorage.getItem('ob_scheme');}catch(e){}
d.classList.add('ap');if(t==='dark')d.classList.add('gl');
if((navigator.hardwareConcurrency||8)<=4||(navigator.deviceMemory||8)<=2)d.classList.add('gl-lite');
var m=document.querySelector('meta[name=theme-color]');if(m)m.setAttribute('content',t==='dark'?'#000000':'#F2F2F7');})();
</script>"""


def _shared_from_glass():
    """Инфографика (.ig-*) и переключатель подписей темы (.gl-on-only) лежат в
    glass_theme и нужны ОБЕИМ темам. glass.css теперь грузится только в тёмной
    теме, поэтому эти правила (без html.gl) берём оттуда и кладём сюда."""
    import glass_theme
    src = glass_theme.MANUAL_CSS
    a = src.index("/* ======================= инфографика (обе темы)")
    b = src.index("/* ================================ движение")
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _COMMENT_RE.sub("", src[a:b])):
        sels = [x.strip() for x in m.group(1).split(",") if x.strip() and "html.gl" not in x]
        if sels:
            out.append("%s{%s}" % (",".join(sels), m.group(2).strip()))
    out.append("@keyframes glGrowX{from{transform:scaleX(0)}to{transform:none}}")
    out.append("@keyframes glGrowY{from{transform:scaleY(0)}to{transform:none}}")
    out.append(".ig-bar i{animation:glGrowX .9s cubic-bezier(.22,1,.36,1) both;animation-delay:.15s;}")
    out.append(".ig-wd i{animation:glGrowY .8s cubic-bezier(.34,1.4,.64,1) both;}")
    out.append("".join(".ig-wd div:nth-child(%d) i{animation-delay:%.2fs}" % (n, (n - 1) * .04) for n in range(2, 8)))
    out.append("@media (prefers-reduced-motion:reduce){.ig-wd i,.ig-bar i{animation:none!important}}")
    out.append("html.gl-lite .ig-wd i, html.gl-lite .ig-bar i{animation:none!important}")
    return "\n".join(out) + "\n"


class Theme:
    def __init__(self, page):
        shared = _shared_from_glass()
        # общие правила тоже переводим в палитру Apple — вместе со стилями страницы
        self.css = (shared + build_auto_css(page + "<style>" + shared + "</style>") + MANUAL_CSS).encode("utf-8")
        self.js = APPLE_JS.replace("__MAP__", json.dumps(js_color_map(page), sort_keys=True)).encode("utf-8")
        self.css_v = hashlib.sha1(self.css).hexdigest()[:10]
        self.js_v = hashlib.sha1(self.js).hexdigest()[:10]

    def install(self, page):
        """Ранний скрипт — сразу после theme-color; стили и скрипт — последними
        в <head> (после glass.css), чтобы перекрывать встроенные стили."""
        meta = '<meta name="theme-color" content="#0A2540">'
        assert page.count(meta) == 1
        page = page.replace(meta, '<meta name="theme-color" content="#F2F2F7">' + HEAD_BOOT, 1)
        tail = ('<link rel="stylesheet" href="/ui/apple.css?v=%s">' % self.css_v
                + '<script src="/ui/apple.js?v=%s" defer></script>' % self.js_v)
        return page.replace("</head>", tail + "</head>", 1)


# ------------------------------------- малые страницы (регистрация, оплата) ----
# Регистрация была тёмной, «Подписка» и «Пригласи друга» — светлыми со своими
# шрифтами. Этот блок вставляется в их <head> последним и приводит их к тому
# же виду, что и панель: шрифт системы, палитра Apple, поля «как в iOS».
SUBPAGE_CSS = """<style>
:root{--line:#E5E5EA;--text:#1D1D1F;--muted:#6E6E73;--blue:#007AFF;--blue-bg:#E5F1FF;--green:#248A3D;--green-bg:#E8F8EC;
  --warn:#C93400;--warn-bg:#FFF3E3;--red:#D70015;--red-bg:#FFECEB;--mono:__FONT__;}
body{font-family:__FONT__;-webkit-font-smoothing:antialiased;letter-spacing:-.01em;font-variant-numeric:tabular-nums;background:#F2F2F7;}
.top{background:rgba(237,240,247,.66);border-bottom:0;box-shadow:0 .5px 0 rgba(0,0,0,.12);-webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px);}
.back{color:#007AFF;}
.ttl{font-size:17px;font-weight:600;}
body{background:radial-gradient(55vmax 45vmax at 0% 0%, rgba(122,184,255,.42), transparent 62%),radial-gradient(45vmax 40vmax at 100% 18%, rgba(120,226,222,.30), transparent 64%),radial-gradient(50vmax 42vmax at 85% 100%, rgba(255,196,168,.32), transparent 62%),radial-gradient(42vmax 38vmax at 8% 82%, rgba(196,182,255,.30), transparent 64%),#EDF0F7;background-attachment:fixed;}
.card{border:1px solid rgba(255,255,255,.7);border-radius:18px;background:rgba(255,255,255,.78);box-shadow:0 1px 1px rgba(0,0,0,.03),0 10px 30px rgba(28,39,72,.07),inset 0 1px 0 rgba(255,255,255,.9);}
.big{font-weight:700;letter-spacing:-.02em;}
.opt{border-width:1.5px;border-radius:16px;}
input,select,textarea{font-family:inherit;}
</style>""".replace("__FONT__", FONT)

REGISTER_CSS = """<style>
:root{color-scheme:light;}
body{background:radial-gradient(55vmax 45vmax at 0% 0%, rgba(122,184,255,.42), transparent 62%),radial-gradient(45vmax 40vmax at 100% 18%, rgba(120,226,222,.30), transparent 64%),radial-gradient(50vmax 42vmax at 85% 100%, rgba(255,196,168,.32), transparent 62%),radial-gradient(42vmax 38vmax at 8% 82%, rgba(196,182,255,.30), transparent 64%),#EDF0F7;background-attachment:fixed;color:#1D1D1F;font-family:__FONT__;-webkit-font-smoothing:antialiased;letter-spacing:-.01em;}
.wm-oil{background:none;-webkit-background-clip:initial;background-clip:initial;color:#007AFF;}
.wm-book{color:#1D1D1F;}
.box{background:rgba(255,255,255,.8);border:1px solid rgba(255,255,255,.7);border-radius:22px;box-shadow:0 12px 34px rgba(28,39,72,.08),inset 0 1px 0 rgba(255,255,255,.9);padding:24px 20px;}
input{background:rgba(255,255,255,.9)!important;border:1px solid rgba(60,60,67,.14)!important;}input:focus{border-color:#007AFF!important;}
h1{font-size:24px;font-weight:700;letter-spacing:-.02em;}
.step{color:#007AFF;font-size:13px;}
.intro{color:#6E6E73;font-size:15px;}
label{color:#1D1D1F;font-size:15px;font-weight:600;}
input{background:#F2F2F7;border:1px solid transparent;border-radius:12px;color:#1D1D1F;padding:13px 14px;font-size:17px;font-family:inherit;}
input:focus{border-color:#007AFF;background:#fff;box-shadow:0 0 0 3px rgba(0,122,255,.18);}
input.bad{border-color:#FF3B30;}
.hint{color:#8E8E93;font-size:13px;}
.ferr{color:#D70015;}
button,.btn{background:#007AFF;border-radius:12px;font-size:17px;min-height:50px;font-family:inherit;}
.btn-tg{background:#2AABEE;}
.btn-ghost{background:rgba(0,122,255,.1);border:0;color:#007AFF;}
.error{background:#FFECEB;color:#D70015;border-radius:12px;}
ol{color:#3A3A3C;}
.code{background:#F2F2F7;border:1px dashed #007AFF;color:#1D1D1F;border-radius:12px;}
.wait{color:#3A3A3C;}
.spin{border-color:#007AFF;border-top-color:transparent;}
.note{background:#E5F1FF;color:#0040DD;border-radius:12px;}
.links a{color:#8E8E93;}
.links a.pri{color:#007AFF;}
.locrow{background:#F2F2F7;border:0;border-radius:12px;}
.loct{color:#1D1D1F;}
.refnote{background:#FFF8DB;border:0;color:#A05A00;border-radius:12px;}
.refnote b{color:#1D1D1F;}
</style>""".replace("__FONT__", FONT)


def style_subpage(page, css=None):
    """Вставить стили Apple последними в <head> малой страницы."""
    css = css or SUBPAGE_CSS
    assert page.count("</head>") == 1
    page = page.replace('<meta name="theme-color" content="#0A2540">', '<meta name="theme-color" content="#F2F2F7">', 1)
    return page.replace("</head>", css + "</head>", 1)
