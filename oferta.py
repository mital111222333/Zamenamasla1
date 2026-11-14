"""
Соглашение OilBook (ommaviy oferta) — страница /oferta и учёт согласий.

Текст соглашения лежит в docs/foydalanish_shartlari_uz.md (официальный —
на узбекском). Перед оплатой подписки владелец точки ставит галочку
«согласен» — без неё сервер платёж не принимает (см. subscription.py), а
каждое согласие записывается: кто, когда, с какого адреса, какую редакцию
принял и к какому платежу.

Меняете текст соглашения по существу — увеличьте OFERTA_VERSION и строку
«Tahrir:» в начале файла соглашения (тест следит, чтобы они совпадали).
"""

import html
import os
import re
from datetime import datetime

from flask import Response, request, session

import database as db
import i18n
from webapp import _client_ip, app

OFERTA_VERSION = "1.0"
OFERTA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "foydalanish_shartlari_uz.md")
_APPENDIX_MARK = "<!-- ILOVA"  # дальше — служебные тексты для программы, на странице не показываем

_table_ready = [False]
app.jinja_env.globals["oferta_version"] = OFERTA_VERSION


def _ensure_table(conn):
    if _table_ready[0]:
        return
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oferta_acceptances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL,
            username TEXT,
            version TEXT NOT NULL,
            accepted_at TEXT NOT NULL,
            ip TEXT,
            user_agent TEXT,
            payment_id INTEGER
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oferta_shop ON oferta_acceptances(shop_id, version)")
    _table_ready[0] = True


def record_acceptance(shop_id, username, payment_id=None):
    """Записывает согласие с текущей редакцией. Возвращает id записи."""
    with db.WRITE_LOCK, db.get_conn() as conn:
        _ensure_table(conn)
        cur = conn.execute(
            "INSERT INTO oferta_acceptances (shop_id, username, version, accepted_at, ip, user_agent, payment_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (shop_id, (username or "")[:64] or None, OFERTA_VERSION, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             _client_ip(), (request.headers.get("User-Agent") or "")[:200] or None, payment_id))
        conn.commit()
        return cur.lastrowid


def latest_acceptance(shop_id):
    with db.get_conn() as conn:
        _ensure_table(conn)
        row = conn.execute("SELECT * FROM oferta_acceptances WHERE shop_id=? ORDER BY id DESC LIMIT 1",
                           (shop_id,)).fetchone()
    return dict(row) if row else None


def agreed(data) -> bool:
    """Пришло ли с формы согласие именно с ТЕКУЩЕЙ редакцией."""
    val = str((data or {}).get("agree") or "").lower()
    return val in ("1", "true", "on", "yes") and str((data or {}).get("oferta_version") or "") == OFERTA_VERSION


# ---------- Страница /oferta ----------

def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def md_to_html(md: str) -> str:
    """Небольшой перевод Markdown в HTML — ровно для того, что есть в тексте
    соглашения (заголовки, абзацы, списки, цитаты, линии). Весь текст
    экранируется: посторонний HTML из файла на страницу не попадёт."""
    md = md.split(_APPENDIX_MARK, 1)[0]
    out, para, items, kind = [], [], [], None

    def flush():
        nonlocal para, items, kind
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para = []
        if items:
            out.append(f"<{kind}>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + f"</{kind}>")
            items, kind = [], None

    for raw in md.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            flush()
            continue
        m = re.match(r"^(#{1,3}) (.*)$", s)
        if m:
            flush()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
            continue
        if s == "---":
            flush()
            out.append("<hr>")
            continue
        m_ul = re.match(r"^- (.*)$", s)
        m_ol = re.match(r"^\d+\. (.*)$", s)
        if m_ul or m_ol:
            new_kind = "ul" if m_ul else "ol"
            if para or (kind and kind != new_kind):
                flush()
            kind = new_kind
            items.append((m_ul or m_ol).group(1))
            continue
        if items and raw.startswith("  "):
            items[-1] += " " + s  # продолжение пункта списка
            continue
        if s.startswith(">"):
            flush()
            out.append("<blockquote>" + _inline(s.lstrip("> ")) + "</blockquote>")
            continue
        para.append(s)
    flush()
    return "\n".join(out)


def _oferta_text():
    with open(OFERTA_PATH, encoding="utf-8") as f:
        return f.read()


PAGE = """<!DOCTYPE html>
<html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin:0; background:#F4F6FA; color:#0A2540; font:16px/1.6 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }}
  .wrap {{ max-width:760px; margin:0 auto; padding:20px 16px 60px; }}
  .doc {{ background:#fff; border-radius:16px; padding:22px 20px; box-shadow:0 2px 10px rgba(10,37,64,.06); }}
  h1 {{ font-size:22px; line-height:1.3; margin:0 0 4px; }}
  h2 {{ font-size:18px; margin:26px 0 8px; color:#0F52BA; }}
  h3 {{ font-size:16px; margin:20px 0 6px; }}
  p, li {{ margin:6px 0; }}
  ol, ul {{ padding-left:22px; }}
  hr {{ border:0; border-top:1px solid #E3E8F0; margin:20px 0; }}
  blockquote {{ margin:8px 0; padding:8px 12px; border-left:3px solid #0F52BA; background:#F4F7FD; }}
  .note {{ background:#FFF8E6; border:1px solid #F5DFA0; border-radius:12px; padding:10px 14px; margin-bottom:14px; font-size:14px; }}
  .ok {{ background:#ECFDF3; border:1px solid #A7E8C3; border-radius:12px; padding:10px 14px; margin-bottom:14px; font-size:14px; }}
  .top {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; font-size:14px; }}
  a {{ color:#0F52BA; }}
</style></head>
<body><div class="wrap">
  <div class="top"><a href="/subscription">← OilBook</a><span>Tahrir {version}</span></div>
  {extra}
  <div class="doc">{body}</div>
</div></body></html>"""


@app.route("/oferta")
def oferta_page():
    lang = request.args.get("lang")
    shop = db.get_shop(session["shop_id"]) if session.get("shop_id") and session.get("role") in ("shop", "branch") else None
    if lang not in ("ru", "uz"):
        lang = (shop or {}).get("language") or "uz"
    extra = ""
    note = i18n.t("oferta_ru_note", lang) if lang == "ru" else ""
    if note:
        extra += f'<div class="note">{html.escape(note)}</div>'
    if shop:
        acc = latest_acceptance(shop["id"])
        if acc:
            when = acc["accepted_at"][:16].replace("-", ".")
            extra += (f'<div class="ok">✅ Siz {html.escape(acc["version"])}-tahrirga {html.escape(when)} da '
                      f'rozilik bergansiz.</div>')
    page = PAGE.format(title=html.escape(i18n.t("oferta_title", lang)), version=OFERTA_VERSION,
                       extra=extra, body=md_to_html(_oferta_text()))
    return Response(page, mimetype="text/html")
