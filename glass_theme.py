"""
Тема «Тёмное стекло» для панели точки (PAGE).

Как устроено:
- Слой 1 (автоматический). При запуске сервера берём ВСЕ стили страницы
  (блоки <style> и встроенные style="..."), и каждый цвет пересчитываем в
  тёмную гамму: белые фоны → полупрозрачное стекло, тёмный текст → светлый,
  цветной текст → осветлённый, светлые рамки → тонкие светящиеся. Так тема
  ложится на каждую вкладку и каждое окно, а не только на те, что
  перерисованы вручную, и новые экраны автоматически получают тёмный вид.
- Слой 2 (ручной). Фон с цветными пятнами, стеклянные меню и панели,
  карточки, кнопки, анимации, инфографика.

Всё действует только при классе html.gl — «Классическая тема» (переключатель
в меню) просто снимает класс, и страница выглядит как раньше.

Скорость: файл стилей собирается один раз при запуске, отдаётся отдельным
адресом с версией и кэшируется телефоном надолго (до следующего обновления).
Размытие (backdrop-filter) — только на нижней панели и шторках; карточки —
без размытия (на Android Chrome оно давало пустые белые блоки и тормозило).
Анимации — только transform/opacity, короткие, отключаются при «уменьшить
движение» и на слабых телефонах.
"""

import colorsys
import hashlib
import re

# ---------------------------------------------------------------- цвета ----

_NAMED = {"white": (255, 255, 255), "black": (0, 0, 0)}
_COLOR_RE = re.compile(
    r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3,4}\b|rgba?\([^)]*\)|\b(?:white|black)\b"
)


def _parse_color(tok):
    t = tok.strip()
    if t in _NAMED:
        r, g, b = _NAMED[t]
        return r, g, b, 1.0
    if t.startswith("#"):
        h = t[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return r, g, b, a
    inner = t[t.index("(") + 1:-1].replace("/", ",")
    parts = [p.strip() for p in re.split(r"[,\s]+", inner) if p.strip()]
    if len(parts) < 3:
        return None
    try:
        nums = []
        for p in parts[:3]:
            nums.append(float(p[:-1]) * 2.55 if p.endswith("%") else float(p))
        a = 1.0
        if len(parts) > 3:
            a = float(parts[3][:-1]) / 100 if parts[3].endswith("%") else float(parts[3])
        return nums[0], nums[1], nums[2], a
    except ValueError:
        return None


def _fmt(r, g, b, a=1.0):
    r, g, b = (max(0, min(255, round(x))) for x in (r, g, b))
    a = max(0.0, min(1.0, a))
    if a >= 0.999:
        return "#%02x%02x%02x" % (r, g, b)
    return "rgba(%d,%d,%d,%s)" % (r, g, b, ("%.3f" % a).rstrip("0").rstrip("."))


def _hls(r, g, b):
    return colorsys.rgb_to_hls(r / 255, g / 255, b / 255)


def _from_hls(h, l, s, a=1.0):
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s)))
    return _fmt(r * 255, g * 255, b * 255, a)


def _white(a):
    return _fmt(255, 255, 255, a)


def _chroma(r, g, b):
    """Насколько цвет «цветной» (0 — серый). Надёжнее насыщенности HLS:
    у почти белых серо-голубых (#F1F5F9) насыщенность HLS высокая, а цвета нет."""
    return (max(r, g, b) - min(r, g, b)) / 255


def _map_bg(r, g, b, a):
    h, l, s = _hls(r, g, b)
    c = _chroma(r, g, b)
    if a == 0:
        return None
    if l >= 0.97 and c < 0.06:
        return _white(0.055 * a)
    if l >= 0.78:
        if c < 0.1:
            return _white((0.06 + (0.97 - l) * 0.5) * a)
        return _from_hls(h, 0.56, min(1, s), 0.16 * a)
    if l >= 0.35:
        if c < 0.14:
            return _white(0.16 * a)
        return None  # насыщенные кнопки/метки — свой цвет, на тёмном смотрится
    # тёмное
    if a < 0.95 and l < 0.22:
        return _fmt(2, 6, 20, min(0.8, a + 0.12))  # затемнение под окнами
    if c < 0.3 or l < 0.2:
        return _white(0.07 * a)
    return None


def _map_fg(r, g, b, a):
    h, l, s = _hls(r, g, b)
    c = _chroma(r, g, b)
    if a == 0 or l >= 0.85:
        return None
    if l < 0.3 and c < 0.35:
        return _from_hls(h, 0.94, min(s, 0.25), a)  # основной текст
    if c < 0.16:
        return _from_hls(h, 0.74, min(s, 0.2), a)  # приглушённый (подсказки)
    if l >= 0.68:
        return None
    return _from_hls(h, 0.71, min(s, 0.95), a)  # цветной текст — осветляем


def _map_border(r, g, b, a):
    h, l, s = _hls(r, g, b)
    c = _chroma(r, g, b)
    if a == 0:
        return None
    if l >= 0.75:
        if c < 0.1:
            return _white(0.10 * max(a, 0.6))
        return _from_hls(h, 0.62, min(1, s), 0.38 * max(a, 0.6))
    if l >= 0.35:
        if c < 0.14:
            return _white(0.18 * a)
        return None if l >= 0.5 else _from_hls(h, 0.55, s, a)
    if a < 0.95:
        return None
    return _white(0.10)


def _map_shadow(r, g, b, a):
    h, l, s = _hls(r, g, b)
    if _chroma(r, g, b) > 0.35 and 0.3 <= l <= 0.72:
        return None  # цветное свечение (красная кнопка и т.п.) — оставляем
    return _fmt(0, 0, 0, min(0.55, a * 2.2 + 0.05))


def _map_accent(r, g, b, a):
    h, l, s = _hls(r, g, b)
    c = _chroma(r, g, b)
    if a == 0:
        return None
    if l >= 0.8:
        return _map_bg(r, g, b, a) if c < 0.1 else _from_hls(h, 0.6, s, 0.35 * a)
    if l < 0.35 and c < 0.3:
        return _from_hls(h, 0.85, min(s, 0.3), a)
    if l < 0.55:
        return _from_hls(h, 0.58, s, a)
    return None


_ROLE_BY_PROP = {
    "color": _map_fg, "-webkit-text-fill-color": _map_fg, "caret-color": _map_fg,
    "text-decoration-color": _map_fg,
    "background": _map_bg, "background-color": _map_bg, "background-image": _map_bg,
    "box-shadow": _map_shadow, "text-shadow": _map_shadow,
    "fill": _map_accent, "stroke": _map_accent,
}


def _role(prop):
    if prop in _ROLE_BY_PROP:
        return _ROLE_BY_PROP[prop]
    if prop.startswith("border") or prop.startswith("outline") or prop == "column-rule":
        return _map_border
    if prop.startswith("--"):
        return _map_accent
    return None


def _map_value(prop, value):
    """Пересчитать цвета в значении свойства. None — менять нечего."""
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


# ------------------------------------------------------- разбор стилей ----

def _split_top(s, sep):
    out, depth, cur, quote = [], 0, [], None
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    out.append("".join(cur))
    return out


def _prefix_selector(sel):
    out = []
    for s in _split_top(sel, ","):
        s = s.strip()
        if not s or s.startswith(":root"):
            continue
        if s.startswith("html"):
            rest = s[4:]
            out.append(s if rest.startswith(".gl") else "html.gl" + rest)
        else:
            out.append("html.gl " + s)
    return ",".join(out)


def _decls_to_dark(body):
    res = []
    for d in _split_top(body, ";"):
        if ":" not in d:
            continue
        prop, val = d.split(":", 1)
        prop = prop.strip().lower()
        val = val.strip()
        imp = ""
        if val.lower().endswith("!important"):
            val = val[: -len("!important")].strip()
            imp = "!important"
        new = _map_value(prop, val)
        if new is not None:
            res.append("%s:%s%s" % (prop, new, imp))
    return ";".join(res)


def _match_brace(css, i):
    depth = 0
    while i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(css) - 1


def _convert_css(css):
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
                inner = _convert_css(css[j + 1:end])
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
        sel = _prefix_selector(prelude)
        dark = _decls_to_dark(body)
        if sel and dark:
            out.append("%s{%s}" % (sel, dark))
    return "".join(out)


_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)
_INLINE_RE = re.compile(r"""style=(?:"([^"]*)"|'([^']*)')""")
_JINJA_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.S)
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
# свойства, для которых цвет приходит в style="..." из JS (переменная ${...})
_DYNAMIC_PROPS = ("color", "background", "background-color", "border-color")
_JS_HEX_RE = re.compile(r"""(?<=['"`])#[0-9A-Fa-f]{6}(?=['"`])""")
_DYN_RE = re.compile(r"(color|background|background-color|border-color)\s*:\s*\$\{")


def _attr_sel(prop, decl):
    q = decl.replace("\\", "\\\\").replace('"', '\\"')
    if prop == "color":
        # не путать с background-color / border-color
        return 'html.gl [style^="%s"],html.gl [style*=" %s"],html.gl [style*=";%s"]' % (q, q, q)
    return 'html.gl [style*="%s"]' % q


def _inline_rules(markup):
    seen = {}
    for m in _INLINE_RE.finditer(markup):
        txt = m.group(1) if m.group(1) is not None else m.group(2)
        if "#" not in txt and "rgb" not in txt and "white" not in txt:
            continue
        for d in txt.split(";"):
            if "${" in d or "{{" in d or ":" not in d:
                continue
            prop, val = d.split(":", 1)
            p = prop.strip().lower()
            new = _map_value(p, val.strip().replace("!important", "").strip())
            if new is None:
                continue
            key = d.strip()
            if key and key not in seen:
                seen[key] = (p, new)
    # цвета, которые JS подставляет в style="color:${...}": берём из кода все
    # литералы вида '#RRGGBB' и готовим правило на каждый возможный вариант
    if _DYN_RE.search(markup):
        for hexc in sorted(set(_JS_HEX_RE.findall(markup))):
            for p in _DYNAMIC_PROPS:
                new = _map_value(p, hexc)
                if new is None:
                    continue
                key = "%s:%s" % (p, hexc)
                if key not in seen:
                    seen[key] = (p, new)
    rules = []
    for decl, (p, new) in seen.items():
        rules.append("%s{%s:%s!important}" % (_attr_sel(p, decl), p, new))
    return "".join(rules)


def build_auto_css(page):
    css_parts = []
    for m in _STYLE_BLOCK_RE.finditer(page):
        css_parts.append(_COMMENT_RE.sub("", _JINJA_RE.sub("", m.group(1))))
    return _convert_css("\n".join(css_parts)) + _inline_rules(page)


# ------------------------------------------------------ ручной слой CSS ----

MANUAL_CSS = r"""
html.gl{color-scheme:dark;
  --gl-bg:#060a18; --gl-surface:rgba(255,255,255,.055);
  --gl-line:rgba(255,255,255,.09); --gl-line-2:rgba(255,255,255,.14);
  --gl-text:#f4f7ff; --gl-muted:rgba(226,232,255,.62); --gl-accent:#4d9bff;
  --gl-red:#ff5a5f;
  --gl-spec:linear-gradient(180deg,rgba(255,255,255,.07),rgba(255,255,255,0) 46%);
  --gl-shadow:0 10px 34px rgba(0,0,0,.38);
  --gl-spring:cubic-bezier(.34,1.56,.64,1); --gl-ease:cubic-bezier(.22,1,.36,1);
  --bg:var(--gl-bg); --text:var(--gl-text); --hint:var(--gl-muted); --card:rgba(255,255,255,.055);
  --border:var(--gl-line); --field-bg:rgba(255,255,255,.06); --darkblue:#e6edff; --blue:#5aa2ff;
  --accent2:#5aa2ff; --ok:#34d399; --ok-bg:rgba(52,211,153,.14); --danger:#ff7b7f; --danger-bg:rgba(255,90,95,.14);
  --btn:#ff4d57; --carbon:rgba(255,255,255,.06);
  --tg-theme-bg-color:#060a18; --tg-theme-text-color:#f4f7ff; --tg-theme-hint-color:rgba(226,232,255,.62);
  background:var(--gl-bg);
}
html.gl body{background:transparent;color:var(--gl-text);}
/* низ бокового меню: «Тема» и язык — в одну строку, выход — под ними */
.side-foot .gl-theme-btn{display:none;}
@media (min-width:900px){
  .side-foot{display:grid!important;grid-template-columns:1fr 1fr;}
  .side-foot .gl-theme-btn{display:block;}
  .side-foot .logout{grid-column:1/-1;}
}
/* Фон: неподвижные цветные пятна. Это обычные радиальные градиенты (без
   filter:blur и без анимации) — рисуются один раз и не нагружают телефон. */
html.gl body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:
    radial-gradient(60vmax 50vmax at 4% -6%, rgba(36,87,255,.42), transparent 62%),
    radial-gradient(48vmax 42vmax at 104% 30%, rgba(0,184,255,.26), transparent 64%),
    radial-gradient(46vmax 40vmax at 30% 108%, rgba(255,90,60,.20), transparent 62%),
    radial-gradient(40vmax 36vmax at -8% 68%, rgba(122,60,255,.24), transparent 64%),
    var(--gl-bg);}
html.gl .speedline{height:3px;opacity:.85;background:linear-gradient(90deg,#2457ff,#00b8ff 40%,#ff5a3c 75%,#7a3cff);}
html.gl ::selection{background:rgba(77,155,255,.35);}
html.gl *{scrollbar-color:rgba(255,255,255,.18) transparent;}

/* --- стеклянные поверхности --- */
html.gl .card, html.gl .af-sec, html.gl .af-rcpt, html.gl .st-card, html.gl .st-today,
html.gl .known-client, html.gl .cross-network-card{
  background-color:var(--gl-surface);background-image:var(--gl-spec);border:1px solid var(--gl-line);
  box-shadow:var(--gl-shadow);}
html.gl .card{border-radius:22px;}
html.gl .card-header{background:linear-gradient(120deg,rgba(77,155,255,.28),rgba(34,211,238,.12));border-bottom:1px solid var(--gl-line);}
html.gl h1, html.gl h2, html.gl h3, html.gl h4{color:var(--gl-text);}
html.gl label{color:var(--gl-muted);}

/* поля ввода */
html.gl input, html.gl select, html.gl textarea{background-color:rgba(255,255,255,.06);border-color:var(--gl-line-2);color:var(--gl-text);}
html.gl input::placeholder, html.gl textarea::placeholder{color:rgba(226,232,255,.38);}
html.gl input:focus, html.gl select:focus, html.gl textarea:focus{border-color:var(--gl-accent);box-shadow:0 0 0 3px rgba(77,155,255,.22);background-color:rgba(255,255,255,.09);}
html.gl select option{background:#121a33;color:var(--gl-text);}
html.gl input[type=date]::-webkit-calendar-picker-indicator{filter:invert(1) opacity(.7);}
html.gl input[type=checkbox], html.gl input[type=radio]{accent-color:#4d9bff;}

/* кнопки */
html.gl button.submit{background:linear-gradient(135deg,#3b82f6 0%,#2457ff 55%,#5b3cff 100%);box-shadow:0 10px 26px rgba(36,87,255,.38),inset 0 1px 0 rgba(255,255,255,.25);}
html.gl .af-save, html.gl .sv-next{background:radial-gradient(circle at 30% 20%,#ff8a80,#ff3b30 55%,#d91e14);box-shadow:0 10px 26px rgba(255,59,48,.38),inset 0 1px 0 rgba(255,255,255,.3);}

/* таблицы */
html.gl th{background:#141b36;color:var(--gl-muted);}
html.gl td{border-bottom-color:var(--gl-line);}
html.gl .table-wrap{border-color:var(--gl-line);background:rgba(255,255,255,.025);}

/* подвкладки */
html.gl .subtab{background:rgba(255,255,255,.05);border:1px solid var(--gl-line);color:var(--gl-muted);border-radius:999px;transition:background .25s,color .25s,transform .35s var(--gl-spring);}
html.gl .subtab:active{transform:scale(.96);}
html.gl .subtab.active{background:linear-gradient(135deg,#3b82f6,#2457ff);border-color:transparent;color:#fff;box-shadow:0 6px 18px rgba(36,87,255,.35),inset 0 1px 0 rgba(255,255,255,.3);}

/* --- телефон: шапка и нижняя панель --- */
html.gl .topbar{background:rgba(14,20,42,.55);border:1px solid var(--gl-line);border-radius:999px;padding:8px 10px;
  box-shadow:0 8px 28px rgba(0,0,0,.35);}
html.gl .logo-badge{background:linear-gradient(135deg,#2457ff,#22d3ee);color:#fff;box-shadow:0 6px 18px rgba(36,87,255,.45);transform:none;border-radius:13px;}
html.gl .wordmark .wm-book{color:#fff;}
html.gl .wordmark .wm-oil{background:linear-gradient(135deg,#7dd3fc,#4d9bff);-webkit-background-clip:text;background-clip:text;color:transparent;}
html.gl .lang-btn{background:rgba(255,255,255,.08);border-color:var(--gl-line-2);color:#fff;}
html.gl .bottom-bar{left:12px;right:12px;bottom:calc(10px + env(safe-area-inset-bottom,0px));padding:6px 4px;border-radius:26px;
  background:rgba(16,22,44,.62);border:1px solid var(--gl-line-2);box-shadow:0 14px 40px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.08);
  -webkit-backdrop-filter:blur(16px) saturate(160%);backdrop-filter:blur(16px) saturate(160%);}
html.gl .bb-item{color:rgba(226,232,255,.55);transition:color .25s,transform .35s var(--gl-spring);}
html.gl .bb-item:active{transform:scale(.9);}
html.gl .bb-item.active{color:#fff;}
html.gl .bb-item.active:not(.bb-add)::before{top:auto;bottom:-3px;width:18px;height:3px;background:linear-gradient(90deg,#4d9bff,#22d3ee);box-shadow:0 0 10px rgba(77,155,255,.8);}
html.gl .bb-plus{border:0;background:radial-gradient(circle at 30% 25%,#ff8a80,#ff3b30 55%,#d91e14);box-shadow:0 10px 24px rgba(255,59,48,.5),inset 0 2px 0 rgba(255,255,255,.4);transition:transform .45s var(--gl-spring);}
html.gl .bb-add:active .bb-plus{transform:scale(.88) rotate(90deg);}
html.gl .bb-add.active span{color:#ff8a8e;}
html.gl .container{padding-bottom:calc(110px + env(safe-area-inset-bottom,0px));}
html.gl .af-bar{bottom:calc(90px + env(safe-area-inset-bottom,0px));background:rgba(18,24,48,.9);border-color:var(--gl-line-2);}
html.gl .more-backdrop, html.gl .ob-sheet-bg{background:rgba(2,6,20,.55);}
html.gl .more-sheet, html.gl .ob-sheet{background:rgba(18,24,48,.9);border-top:1px solid var(--gl-line-2);
  -webkit-backdrop-filter:blur(20px) saturate(160%);backdrop-filter:blur(20px) saturate(160%);box-shadow:0 -14px 40px rgba(0,0,0,.5);}
html.gl .more-sheet.open{transition:transform .38s var(--gl-ease);}
html.gl .more-item{border-bottom-color:var(--gl-line);color:var(--gl-text);}
html.gl .more-item i{color:rgba(226,232,255,.6);}
html.gl .more-item.active, html.gl .more-item.active i{color:#7db6ff;}
html.gl .more-logout, html.gl .more-logout i{color:#ff8a8e;}
html.gl .more-grab{background:rgba(255,255,255,.25);}

/* --- компьютер и планшет: боковое меню-стекло --- */
@media (min-width:900px){
  html.gl .side-nav{top:12px;left:12px;bottom:12px;width:236px;border-radius:26px;background:rgba(14,20,42,.62);
    border:1px solid var(--gl-line-2);box-shadow:0 18px 50px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.07);}
  html.gl .container{margin-left:256px;padding-bottom:28px;}
  html.gl .af-bar{bottom:14px;}
  html.gl .side-brand{border-bottom-color:var(--gl-line);}
  html.gl .side-brand .logo-badge{background:linear-gradient(135deg,#2457ff,#22d3ee);}
  html.gl .side-item{color:rgba(226,232,255,.72);border-radius:12px;transition:background .2s,color .2s,transform .35s var(--gl-spring);}
  html.gl .side-item i{color:rgba(226,232,255,.5);}
  html.gl .side-item:hover{background:rgba(255,255,255,.06);color:#fff;}
  html.gl .side-item:active{transform:scale(.97);}
  html.gl .side-item.active{background:linear-gradient(135deg,rgba(77,155,255,.32),rgba(77,155,255,.12));color:#fff;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.12),0 0 0 1px rgba(77,155,255,.28);}
  html.gl .side-item.active i{color:#8fc1ff;}
  html.gl .side-add, html.gl .side-add.active{background:radial-gradient(circle at 30% 20%,#ff8a80,#ff3b30 55%,#d91e14);color:#fff;
    box-shadow:0 10px 24px rgba(255,59,48,.38),inset 0 1px 0 rgba(255,255,255,.3);}
  html.gl .side-add:hover{filter:brightness(1.08);background:radial-gradient(circle at 30% 20%,#ff8a80,#ff3b30 55%,#d91e14);}
  html.gl .side-add i{color:#fff;}
  html.gl .side-group{color:rgba(226,232,255,.4);}
  html.gl .side-foot{border-top-color:var(--gl-line);}
  html.gl .side-foot .lang-btn{background:rgba(255,255,255,.07);border-color:var(--gl-line-2);}
}

/* места, где тёмная переменная (--darkblue/--text) служила фоном */
html.gl .hp-head{background:linear-gradient(135deg,rgba(36,87,255,.55),rgba(34,211,238,.22));border:1px solid var(--gl-line-2);box-shadow:var(--gl-shadow);}
html.gl .hp-head .hp-for{color:rgba(226,232,255,.75);}
html.gl .hp-search input{background:rgba(6,10,24,.55);color:var(--gl-text);}
html.gl .dtabs button.on{background:linear-gradient(135deg,#3b82f6,#2457ff);border-color:transparent;color:#fff;box-shadow:0 6px 18px rgba(36,87,255,.35);}
html.gl .rv-legend i[style*="#0F52BA"]{background:#4d9bff!important;}

/* окна */
html.gl .modal-overlay{background:rgba(2,6,20,.62);}
html.gl .modal{background:#141b36;border:1px solid var(--gl-line-2);box-shadow:0 30px 80px rgba(0,0,0,.6);}
html.gl .modal img{background:#fff;}
html.gl .sv-wrap{background:var(--gl-bg);}

html.gl .nav-badge{background:var(--gl-red);box-shadow:0 0 0 2px rgba(6,10,24,.9),0 0 12px rgba(255,90,95,.6);}

/* --- Статистика --- */
html.gl .st-today{border-radius:24px;position:relative;overflow:hidden;}
html.gl .st-today::after{content:"";position:absolute;right:-60px;top:-80px;width:220px;height:220px;border-radius:50%;
  background:radial-gradient(circle,rgba(77,155,255,.35),transparent 65%);pointer-events:none;}
html.gl .st-split{background:rgba(255,255,255,.07);}
html.gl .st-card{border-radius:22px;transition:border-color .25s;}
html.gl .st-card:hover{border-color:rgba(77,155,255,.35);}
html.gl .rv-box{background:rgba(255,255,255,.05);border:1px solid var(--gl-line);}
html.gl .rv-box.best{background:linear-gradient(135deg,rgba(255,90,95,.2),rgba(255,90,95,.06));border-color:rgba(255,90,95,.3);}

/* --- Склад --- */
html.gl .wh-kpi{background:rgba(255,255,255,.05);border:1px solid var(--gl-line);}
html.gl .wh-kpi.bad{background:linear-gradient(135deg,rgba(255,90,95,.22),rgba(255,90,95,.06));border-color:rgba(255,90,95,.32);}
html.gl .wh-kpi.good{background:linear-gradient(135deg,rgba(52,211,153,.2),rgba(52,211,153,.05));border-color:rgba(52,211,153,.3);}

/* ======================= инфографика (обе темы) ======================= */
.ig-health{margin:12px 0 4px;padding:12px 14px;border-radius:16px;background:#F8FAFC;border:1px solid #E2E8F0;}
.ig-health-h{display:flex;justify-content:space-between;align-items:baseline;gap:8px;font-size:12px;font-weight:700;color:#64748B;text-transform:uppercase;letter-spacing:.05em;margin-bottom:9px;}
.ig-health-h b{font-size:13px;color:#0F172A;text-transform:none;letter-spacing:0;}
.ig-bar{display:flex;height:12px;border-radius:999px;overflow:hidden;background:#E2E8F0;gap:2px;}
.ig-bar i{display:block;height:100%;transform-origin:left;}
.ig-legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:9px;font-size:12px;color:#475569;}
.ig-legend span{display:inline-flex;align-items:center;gap:6px;}
.ig-legend span::before{content:"";width:9px;height:9px;border-radius:3px;background:var(--c);}
.ig-legend b{color:#0F172A;}
.ig-wd-wrap{margin-top:14px;padding:12px 14px 10px;border-radius:16px;background:#F8FAFC;border:1px solid #E2E8F0;}
.ig-wd-h{display:flex;flex-wrap:wrap;justify-content:space-between;gap:2px 8px;font-size:12px;font-weight:700;color:#64748B;text-transform:uppercase;letter-spacing:.05em;}
.ig-wd-h b{color:#0F172A;text-transform:none;letter-spacing:0;white-space:nowrap;}
.ig-wd{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;align-items:end;height:96px;margin-top:10px;}
.ig-wd div{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:5px;height:100%;min-width:0;}
.ig-wd em{flex:1;width:100%;display:flex;align-items:flex-end;justify-content:center;}
.wh-kpis .ig-health{grid-column:1/-1;}
.gl-on-only{display:none;}
html.gl .gl-on-only{display:inline;}
html.gl .gl-off-only{display:none;}
.ig-wd i{display:block;width:100%;max-width:34px;border-radius:8px 8px 4px 4px;background:linear-gradient(180deg,#60A5FA,#2563EB);transform-origin:bottom;min-height:3px;}
.ig-wd .top i{background:linear-gradient(180deg,#FB7185,#E11D48);}
.ig-wd span{font-size:11px;font-weight:700;color:#64748B;}
html.gl .ig-health, html.gl .ig-wd-wrap{background:rgba(255,255,255,.04);border-color:var(--gl-line);}
html.gl .ig-health-h, html.gl .ig-wd-h{color:var(--gl-muted);}
html.gl .ig-health-h b, html.gl .ig-legend b, html.gl .ig-wd-h b{color:#fff;}
html.gl .ig-bar{background:rgba(255,255,255,.07);}
html.gl .ig-legend, html.gl .ig-wd span{color:var(--gl-muted);}
html.gl .ig-wd i{background:linear-gradient(180deg,#7db6ff,#2457ff);box-shadow:0 0 14px rgba(77,155,255,.35);}
html.gl .ig-wd .top i{background:linear-gradient(180deg,#ff9aa0,#ff3b30);box-shadow:0 0 14px rgba(255,59,48,.45);}

/* ================================ движение ================================ */
@keyframes glRise{from{opacity:0;transform:translate3d(0,14px,0) scale(.985)}to{opacity:1;transform:none}}
@keyframes glGrowX{from{transform:scaleX(0)}to{transform:none}}
@keyframes glGrowY{from{transform:scaleY(0)}to{transform:none}}
html.gl .gl-enter > *{animation:glRise .5s var(--gl-ease) both;}
html.gl .gl-enter > *:nth-child(2){animation-delay:.04s}
html.gl .gl-enter > *:nth-child(3){animation-delay:.08s}
html.gl .gl-enter > *:nth-child(4){animation-delay:.12s}
html.gl .gl-enter > *:nth-child(5){animation-delay:.16s}
html.gl .gl-enter > *:nth-child(n+6){animation-delay:.2s}
html.gl .st-grid > .st-card{animation:glRise .55s var(--gl-ease) both;}
html.gl .st-grid > .st-card:nth-child(2){animation-delay:.07s}
html.gl .st-grid > .st-card:nth-child(3){animation-delay:.14s}
html.gl .st-split i, .ig-bar i{animation:glGrowX .9s var(--gl-ease) both;animation-delay:.15s;}
.ig-wd i{animation:glGrowY .8s var(--gl-spring) both;}
.ig-wd div:nth-child(2) i{animation-delay:.04s}.ig-wd div:nth-child(3) i{animation-delay:.08s}
.ig-wd div:nth-child(4) i{animation-delay:.12s}.ig-wd div:nth-child(5) i{animation-delay:.16s}
.ig-wd div:nth-child(6) i{animation-delay:.2s}.ig-wd div:nth-child(7) i{animation-delay:.24s}
html.gl .wh-kpi{animation:glRise .5s var(--gl-ease) both;}
html.gl .wh-kpi:nth-child(2){animation-delay:.05s}html.gl .wh-kpi:nth-child(3){animation-delay:.1s}html.gl .wh-kpi:nth-child(4){animation-delay:.15s}
html.gl .wh-tbtn, html.gl .km-chip, html.gl .pay-seg button, html.gl .flt-tile{transition:transform .35s var(--gl-spring),background .2s,border-color .2s;}
html.gl .wh-tbtn:active, html.gl .km-chip:active, html.gl .pay-seg button:active, html.gl .flt-tile:active{transform:scale(.95);}

/* лёгкий режим: слабый телефон — без размытия, без анимаций */
html.gl.gl-lite .bottom-bar, html.gl.gl-lite .more-sheet, html.gl.gl-lite .ob-sheet{-webkit-backdrop-filter:none;backdrop-filter:none;background:rgba(16,22,44,.97);}
html.gl.gl-lite *, html.gl.gl-lite *::before, html.gl.gl-lite *::after{animation:none!important;}
@media (prefers-reduced-motion:reduce){
  html.gl *, html.gl *::before, html.gl *::after, .ig-wd i, .ig-bar i{animation:none!important;transition-duration:.01s!important;}
}
"""

# --------------------------------------------------------------- JS ----

GLASS_JS = r"""
(function(){
  var root = document.documentElement;
  function on(){ return root.classList.contains('gl'); }
  function calm(){
    return !on() || root.classList.contains('gl-lite') ||
      (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  }
  // появление раздела: только transform/opacity, один раз при открытии
  window.glEnter = function(id){
    if (calm()) return;
    var v = document.getElementById(id);
    if (!v) return;
    v.classList.remove('gl-enter'); void v.offsetWidth; v.classList.add('gl-enter');
    clearTimeout(v._glT); v._glT = setTimeout(function(){ v.classList.remove('gl-enter'); }, 900);
  };
  // счётчик: крупные суммы «набегают» от 0 до значения
  window.glCount = function(scope){
    if (calm()) return;
    var els = (scope || document).querySelectorAll('.st-today-amount, .st-money-v, .wh-kpi b');
    els.forEach(function(el){
      var node = el.firstChild;
      if (!node || node.nodeType !== 3) return;
      var m = node.nodeValue.match(/^([+−-]?)([\d\s  ]+)(.*)$/);
      if (!m) return;
      var target = parseInt(m[2].replace(/\D/g, ''), 10);
      if (!target || target < 10) return;
      var pre = m[1], post = m[3], t0 = null, dur = 900;
      function f(t){ if (!t0) t0 = t; var p = Math.min(1, (t - t0) / dur); p = 1 - Math.pow(1 - p, 3);
        node.nodeValue = pre + Math.round(target * p).toLocaleString('ru-RU') + post;
        if (p < 1) requestAnimationFrame(f); }
      requestAnimationFrame(f);
    });
  };
  // графики Chart.js: тёмные оси, светлые столбики, мягкое появление
  var MAP = {'#0f52ba':'#4d9bff','#0a3d8f':'#7db6ff','#e63946':'#ff5a5f','#c81e2b':'#ff8a8e','#1d3557':'#93a7ff',
             '#cbd5e1':'rgba(255,255,255,.22)','#94a3b8':'rgba(226,232,255,.55)','#f1f5f9':'rgba(255,255,255,.06)',
             '#64748b':'rgba(226,232,255,.62)','#0f172a':'#f4f7ff','#fff':'#0c1330','#ffffff':'#0c1330',
             '#e2e8f0':'rgba(255,255,255,.08)','#8e44ad':'#b583ff','#2a9d8f':'#34d3b8'};
  function mc(c){ return (typeof c === 'string' && MAP[c.toLowerCase()]) || c; }
  function mArr(v){ return Array.isArray(v) ? v.map(mc) : mc(v); }
  window.glColor = function(c){ return on() ? mc(c) : c; };
  window.glChartTheme = function(){
    if (typeof Chart === 'undefined' || Chart._glDone) return;
    Chart._glDone = true;
    if (!on()) return;
    Chart.register({ id: 'glTheme', beforeInit: function(chart){
      var o = chart.options, d = chart.config.data;
      (d.datasets || []).forEach(function(ds){
        ['backgroundColor','hoverBackgroundColor','borderColor','pointBackgroundColor'].forEach(function(k){ if (ds[k]) ds[k] = mArr(ds[k]); });
      });
      var sc = o.scales || {};
      Object.keys(sc).forEach(function(k){ var s = sc[k];
        if (s.grid) s.grid.color = 'rgba(255,255,255,.06)';
        if (s.ticks) s.ticks.color = 'rgba(226,232,255,.55)'; });
      var t = o.plugins && o.plugins.tooltip;
      if (t) { t.backgroundColor = 'rgba(16,22,44,.95)'; t.borderColor = 'rgba(255,255,255,.14)';
        t.borderWidth = 1; t.titleColor = '#fff'; t.bodyColor = 'rgba(226,232,255,.85)'; t.cornerRadius = 12; }
    }});
    Chart.defaults.color = 'rgba(226,232,255,.62)';
    Chart.defaults.borderColor = 'rgba(255,255,255,.08)';
    Chart.defaults.animation.duration = 900;
    Chart.defaults.animation.easing = 'easeOutQuart';
  };
  // переключатель темы (Стекло / Классика)
  window.glToggle = function(){
    try { localStorage.setItem('ob_theme', on() ? 'classic' : 'glass'); } catch (e) {}
    location.reload();
  };
})();
"""

# ранний скрипт в <head>: класс ставится ДО отрисовки — без вспышки белым
HEAD_BOOT = """<script>
(function(){var t=null;try{t=localStorage.getItem('ob_theme');}catch(e){}
if(t!=='classic'){var d=document.documentElement;d.classList.add('gl');
if((navigator.hardwareConcurrency||8)<=4||(navigator.deviceMemory||8)<=2)d.classList.add('gl-lite');
var m=document.querySelector('meta[name=theme-color]');if(m)m.setAttribute('content','#060a18');}})();
</script>"""


class Theme:
    def __init__(self, page):
        self.css = (build_auto_css(page) + MANUAL_CSS).encode("utf-8")
        self.js = GLASS_JS.encode("utf-8")
        self.css_v = hashlib.sha1(self.css).hexdigest()[:10]
        self.js_v = hashlib.sha1(self.js).hexdigest()[:10]

    def install(self, page):
        """Вставить в страницу ранний скрипт (класс темы — сразу после
        theme-color), а стили и скрипт темы — последними в <head>, после всех
        встроенных <style>, чтобы перекрывать их."""
        meta = '<meta name="theme-color" content="#0A2540">'
        page = page.replace(meta, meta + HEAD_BOOT, 1)
        tail = ('<link rel="stylesheet" href="/ui/glass.css?v=%s">' % self.css_v
                + '<script src="/ui/glass.js?v=%s" defer></script>' % self.js_v)
        return page.replace("</head>", tail + "</head>", 1)
