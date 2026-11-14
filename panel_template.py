"""HTML, стили и скрипты панели точки — без изменений, просто вынесены из
webapp.py, чтобы правки логики и правки страницы не мешали друг другу.

HELP_* — справка внутри панели, PAGE — разметка панели, MODAL_AND_SCRIPT — окна и весь скрипт панели,
NET_GUARD_JS — защита от обрыва сети, PLATE_DECODE_JS / PLATE_SCAN_HTML —
сканер номеров, VIN_SCAN_HTML — сканер VIN. webapp.py импортирует их в тех
же местах, где они раньше стояли, и собирает из них страницу как раньше
(вставка сканеров, тема, заставка)."""


HELP_CSS = """
  #view-help { max-width:760px; }
  .hp-head { background:var(--darkblue); color:#fff; border-radius:20px; padding:18px 16px 16px; margin-bottom:12px; }
  .hp-head h2 { margin:0; font-family:var(--font-display); font-size:24px; font-weight:700; letter-spacing:-.01em; }
  .hp-head .hp-for { font-size:13px; color:#B9CBEA; margin-top:3px; }
  .hp-search { position:relative; margin-top:14px; }
  .hp-search i { position:absolute; left:14px; top:50%; transform:translateY(-50%); color:#64748B; font-size:15px; pointer-events:none; }
  .hp-search input { width:100%; height:48px; border:0; border-radius:14px; padding:0 14px 0 40px; font-size:16px; font-family:inherit; background:#fff; color:var(--text); }
  .hp-search input:focus { outline:3px solid #7DB2FF; }
  .hp-chips { display:flex; gap:6px; overflow-x:auto; padding:2px 0 10px; scrollbar-width:none; -webkit-overflow-scrolling:touch; }
  .hp-chips::-webkit-scrollbar { display:none; }
  .hp-chip { flex:none; display:flex; align-items:center; gap:6px; height:36px; padding:0 12px; border-radius:18px; border:1px solid var(--border); background:#fff; color:var(--darkblue); font-size:13px; font-weight:600; font-family:inherit; cursor:pointer; }
  .hp-chip i { color:var(--blue); font-size:12px; }
  .hp-sec { margin-bottom:16px; scroll-margin-top:12px; }
  .hp-sec-h { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:700; color:#64748B; margin:0 4px 8px; }
  .hp-sec-h i { color:var(--blue); }
  .hp-list { background:#fff; border:1px solid var(--border); border-radius:16px; overflow:hidden; }
  details.hp-art + details.hp-art { border-top:1px solid #EEF2F7; }
  details.hp-art > summary { list-style:none; display:flex; align-items:center; gap:10px; padding:14px 16px; cursor:pointer; font-weight:600; font-size:15px; line-height:1.35; color:var(--darkblue); -webkit-tap-highlight-color:transparent; }
  details.hp-art > summary::-webkit-details-marker { display:none; }
  details.hp-art > summary span { flex:1; min-width:0; }
  details.hp-art > summary .fa-chevron-down { color:#94A3B8; font-size:12px; transition:transform .2s; }
  details.hp-art[open] > summary { color:var(--blue); }
  details.hp-art[open] > summary .fa-chevron-down { transform:rotate(180deg); }
  .hp-body { padding:0 16px 16px; font-size:14.5px; line-height:1.6; color:#334155; }
  .hp-body p { margin:0 0 10px; }
  .hp-body ul { margin:0 0 10px; padding-left:20px; }
  .hp-body li { margin-bottom:5px; }
  .hp-body b { color:var(--darkblue); }
  .hp-body ol.hp-steps { list-style:none; counter-reset:hps; margin:0 0 12px; padding:0; }
  .hp-body ol.hp-steps > li { counter-increment:hps; position:relative; padding:2px 0 0 36px; margin-bottom:10px; min-height:26px; }
  .hp-body ol.hp-steps > li::before { content:counter(hps); position:absolute; left:0; top:0; width:26px; height:26px; border-radius:8px; background:#E8F0FD; color:var(--blue); font-weight:700; font-size:13px; display:flex; align-items:center; justify-content:center; }
  .hp-body ol.hp-steps ul { margin-top:6px; }
  .hp-tip, .hp-warn { border-radius:12px; padding:10px 12px; margin:4px 0 12px; font-size:14px; }
  .hp-tip { background:#EEF5FF; color:#123E7C; }
  .hp-warn { background:#FFF6E0; color:#7A4A00; }
  .hp-tip b, .hp-warn b { color:inherit; }
  .hp-go { display:inline-flex; align-items:center; gap:6px; height:38px; padding:0 14px; border-radius:10px; border:1px solid #C9DBF7; background:#fff; color:var(--blue); font-weight:600; font-size:14px; font-family:inherit; cursor:pointer; }
  .hp-empty { background:#fff; border:1px solid var(--border); border-radius:16px; padding:18px 16px; color:#64748B; font-size:14px; }
  .hp-foot { text-align:center; color:#64748B; font-size:13px; padding:6px 0 18px; }
  .hp-foot a { color:var(--blue); font-weight:600; }
  .hp-hidden { display:none !important; }
"""


HELP_VIEW = """
  <div class="hp-head">
    <h2>{{ T.tab_help }}</h2>
    <div class="hp-for">{{ T.help_for }} {{ help_role }}</div>
    <div class="hp-search">
      <i class="fa-solid fa-magnifying-glass"></i>
      <input id="hpSearch" type="search" autocomplete="off" spellcheck="false" placeholder="{{ T.help_search_ph }}" oninput="helpSearch(this.value)">
    </div>
  </div>
  <div class="hp-chips" id="hpChips">
    {% for s in help_sections %}<button type="button" class="hp-chip" onclick="helpJump('{{ s.key }}')"><i class="fa-solid {{ s.icon }}"></i>{{ s.title }}</button>{% endfor %}
  </div>
  <div id="hpEmpty" class="hp-empty hp-hidden">{{ T.help_nothing }}</div>
  {% for s in help_sections %}
  <div class="hp-sec" id="hp-sec-{{ s.key }}">
    <div class="hp-sec-h"><i class="fa-solid {{ s.icon }}"></i>{{ s.title }}</div>
    <div class="hp-list">
      {% for a in s.articles %}
      <details class="hp-art" id="hp-{{ a.id }}" data-kw="{{ a.kw }}">
        <summary><span>{{ a.title }}</span><i class="fa-solid fa-chevron-down"></i></summary>
        <div class="hp-body">{{ a.body|safe }}
          {% if a.go %}<button type="button" class="hp-go" onclick="showTab('{{ a.go }}')">{{ T.help_open }} «{{ T['tab_' ~ a.go] }}» <i class="fa-solid fa-arrow-right"></i></button>{% endif %}
        </div>
      </details>
      {% endfor %}
    </div>
  </div>
  {% endfor %}
  {% if help_support %}<div class="hp-foot">{{ T.help_support }} {% if help_support_url %}<a href="{{ help_support_url }}" target="_blank" rel="noopener">{{ help_support }}</a>{% else %}<b>{{ help_support }}</b>{% endif %}</div>{% endif %}
"""


HELP_JS = """
<script>
function helpNorm(s) { return (s || '').toLowerCase().split('ё').join('е').split('ʻ').join("'").split('‘').join("'").split('’').join("'"); }
let HELP_INDEX = null;
function helpBuildIndex() {
  HELP_INDEX = [];
  document.querySelectorAll('#view-help details.hp-art').forEach(d => {
    HELP_INDEX.push({ el: d, text: helpNorm(d.textContent + ' ' + (d.dataset.kw || '')) });
  });
}
function helpSearch(q) {
  if (!HELP_INDEX) helpBuildIndex();
  const words = helpNorm(q).trim().split(' ').filter(w => w.length > 0);
  const active = words.length > 0 && helpNorm(q).trim().length >= 2;
  let found = 0;
  HELP_INDEX.forEach(it => {
    const ok = !active || words.every(w => it.text.indexOf(w) !== -1);
    it.el.classList.toggle('hp-hidden', !ok);
    if (ok) found++;
    if (active) it.el.open = ok && found <= 3;
  });
  document.querySelectorAll('#view-help .hp-sec').forEach(sec => {
    sec.classList.toggle('hp-hidden', !sec.querySelector('details.hp-art:not(.hp-hidden)'));
  });
  const chips = document.getElementById('hpChips');
  if (chips) chips.classList.toggle('hp-hidden', active);
  document.getElementById('hpEmpty').classList.toggle('hp-hidden', found > 0);
  if (!active) HELP_INDEX.forEach(it => { it.el.open = false; });
}
function helpJump(key) {
  const sec = document.getElementById('hp-sec-' + key);
  if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
</script>
"""


PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{{ shop_name }} — OilBook</title>
<link rel="manifest" href="/static/manifest.json?v=2">
<meta name="theme-color" content="#0A2540">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="OilBook">
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
</script>
<!--__TG_PANEL_JS__-->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=Space+Grotesk:wght@600;700&family=Sora:wght@700;800&family=IBM+Plex+Mono:wght@500;600&family=Inter:wght@200;300;400;500;600&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=Space+Grotesk:wght@600;700&family=Sora:wght@700;800&family=IBM+Plex+Mono:wght@500;600&family=Inter:wght@200;300;400;500;600&display=swap"></noscript>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" crossorigin="anonymous" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"></noscript>
<style>
  :root {
    /* цвета свои, не из темы Telegram: в тёмной теме Telegram текст
       становился белым на белых карточках и пропадал */
    --bg: #F1F5F9;
    --text: #1E293B;
    --hint: #94A3B8;
    --btn: #E63946;
    --btn-text: #FFFFFF;
    --blue: #0F52BA;
    --darkblue: #0A2540;
    --cyan: #00A8E8;
    --darkred: #9B111E;
    --carbon: #181E29;
    --card: #FFFFFF;
    --border: #E2E8F0;
    --field-bg: #F4F7FA;
    --ok: #059669;
    --ok-bg: #ECFDF5;
    --danger: #B3241C;
    --danger-bg: #FDECEA;
    --accent2: #0F52BA;
    --font-display: 'Space Grotesk', sans-serif;
    --font-body: 'Plus Jakarta Sans', -apple-system, sans-serif;
    --font-mono: 'IBM Plex Mono', monospace;
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: var(--font-body); }
  .speedline {
    height:6px; width:100%;
    background: linear-gradient(90deg, var(--blue) 0%, var(--blue) 33%, #fff 33%, #fff 38%, var(--btn) 38%, var(--btn) 70%, #fff 70%, #fff 75%, var(--cyan) 75%, var(--cyan) 100%);
  }
  .container { padding: 12px; max-width: 960px; margin: 0 auto; }
  .topbar { display:flex; justify-content:space-between; align-items:center; margin: 14px 0 16px; }
  .logo-badge {
    display:inline-flex; align-items:center; justify-content:center; width:40px; height:40px;
    background:var(--darkblue); color:var(--cyan); border-radius:12px; transform:rotate(-8deg);
    box-shadow:0 4px 10px rgba(10,37,64,.25); font-size:16px; flex:none;
  }
  h1 { font-family: var(--font-display); font-weight:800; font-style:italic; letter-spacing:-0.3px; font-size: 22px; margin: 0; line-height:1.1; color:var(--darkblue); }
  h1 .accent { color:var(--btn); }
  .logo-sub { font-size:10px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase; color:var(--hint); }
  .brand-line { text-transform:none; letter-spacing:0; font-size:12px; display:flex; align-items:baseline; gap:4px; flex-wrap:wrap; margin-top:2px; }
  .brand-line .role-tag { font-size:11px; font-weight:700; letter-spacing:.8px; text-transform:uppercase; }
  .wordmark { font-family:'Sora', var(--font-display), sans-serif; font-style:normal; font-weight:800; font-size:17px; letter-spacing:-0.4px; line-height:1; white-space:nowrap; }
  .wordmark .wm-oil { background:linear-gradient(135deg, #0EA5E9 0%, #1D4ED8 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
  .wordmark .wm-book { color:#0B1B3A; }
  .logout { color: var(--btn); font-size: 12px; font-weight:700; text-decoration:none; background:var(--danger-bg); padding:6px 10px; border-radius:10px; }
  .lang-btn { background: #EFF6FF; border: 1px solid #BFDBFE; color: var(--blue); font-size: 12px; font-weight:700; padding: 6px 10px; border-radius: 10px; cursor: pointer; }
  .tabs { display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; margin-bottom: 10px; }
  /* ---- навигация: телефон ---- */
  .container { padding-bottom: calc(96px + env(safe-area-inset-bottom, 0px)); }
  .topbar { margin: 10px 0 12px; gap:10px; }
  .topbar h1 { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .side-nav { display:none; }
  .role-tag { color:#B45309; }
  .bottom-bar { position:fixed; left:0; right:0; bottom:0; z-index:50; display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); background:rgba(255,255,255,0.97); border-top:1px solid var(--border); padding:6px 4px calc(6px + env(safe-area-inset-bottom, 0px)); box-shadow:0 -4px 16px rgba(15,23,42,0.06); }
  .bb-item { position:relative; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; gap:3px; min-height:50px; font-size:11px; font-weight:600; color:#64748B; cursor:pointer; -webkit-tap-highlight-color:transparent; user-select:none; }
  .bb-item i { font-size:19px; }
  .bb-item span { max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .bb-item.active { color:var(--blue); }
  .bb-item.active:not(.bb-add)::before { content:''; position:absolute; top:-6px; width:28px; height:3px; border-radius:2px; background:var(--blue); }
  .bb-plus { width:48px; height:48px; margin-top:-22px; border-radius:50%; background:var(--btn); color:#fff; display:flex; align-items:center; justify-content:center; box-shadow:0 6px 14px rgba(200,30,43,0.35); border:3px solid #fff; }
  .bb-plus i { font-size:20px; }
  .bb-add.active span { color:var(--btn); }
  .nav-badge { display:none; position:absolute; top:0; right:calc(50% - 22px); min-width:17px; height:17px; padding:0 4px; border-radius:9px; background:var(--btn); color:#fff; font-size:10px; font-weight:800; line-height:17px; text-align:center; }
  .nav-badge.show { display:block; }
  .more-backdrop { position:fixed; inset:0; background:rgba(15,23,42,0.35); z-index:60; opacity:0; pointer-events:none; transition:opacity .2s; }
  .more-backdrop.open { opacity:1; pointer-events:auto; }
  .more-sheet { position:fixed; left:0; right:0; bottom:0; z-index:61; background:#fff; border-radius:20px 20px 0 0; padding:8px 14px calc(14px + env(safe-area-inset-bottom, 0px)); transform:translateY(105%); transition:transform .25s ease; box-shadow:0 -10px 30px rgba(15,23,42,0.15); max-height:80vh; overflow-y:auto; }
  .more-sheet:not(.open) { visibility:hidden; transition:transform .25s ease, visibility 0s .25s; }
  .more-sheet.open { transform:translateY(0); visibility:visible; }
  .more-grab { width:40px; height:5px; border-radius:3px; background:#CBD5E1; margin:2px auto 10px; }
  .more-item { position:relative; display:flex; align-items:center; gap:14px; padding:14px 6px; border-bottom:1px solid #F1F5F9; font-size:15px; font-weight:600; color:var(--text); cursor:pointer; text-decoration:none; }
  .more-item i { width:22px; text-align:center; font-size:18px; color:#64748B; }
  .more-item.active, .more-item.active i { color:var(--blue); }
  .more-item.hidden-in-more { display:none; }
  .more-item .nav-badge { position:static; margin-left:auto; }
  .more-logout, .more-logout i { color:var(--btn); border-bottom:none; }
  @media (display-mode: standalone) { .more-install { display:none; } }
  /* ---- навигация: планшет и компьютер ---- */
  @media (min-width: 900px) {
    .bottom-bar, .more-sheet, .more-backdrop, .topbar { display:none !important; }
    .container { padding-bottom:24px; margin-left:248px; max-width:1100px; padding-left:28px; padding-right:28px; }
    /* ПК: тёмно-синее меню, пункты разбиты на группы */
    .side-nav { display:flex; flex-direction:column; position:fixed; top:6px; left:0; bottom:0; width:248px; background:#0B1B3F; color:#DCE4F5; padding:18px 14px; z-index:40; overflow-y:auto; scrollbar-width:thin; scrollbar-color:#22345F transparent; }
    .side-brand { display:flex; align-items:center; gap:10px; padding:2px 6px 16px; margin-bottom:6px; border-bottom:1px solid #1C2E57; }
    .side-brand .logo-badge { background:#1D4ED8; color:#fff; transform:none; box-shadow:none; width:38px; height:38px; border-radius:11px; }
    .side-shop { font-family:var(--font-display); font-weight:700; font-size:16px; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .side-brand .wordmark .wm-oil { background:none; -webkit-background-clip:initial; background-clip:initial; color:#7FB2FF; }
    .side-brand .wordmark .wm-book { color:#fff; }
    .side-brand .role-tag { color:#FFD34D; }
    .side-list { display:flex; flex-direction:column; gap:1px; }
    .side-group { font-size:11px; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:#7D91BB; padding:14px 12px 5px; }
    .side-item { position:relative; display:flex; align-items:center; gap:12px; padding:9px 12px; border-radius:9px; font-size:14px; font-weight:500; color:#C9D4EC; cursor:pointer; transition:background .12s; }
    .side-item i { width:18px; text-align:center; color:#8296BF; }
    .side-item:hover { background:#152A55; color:#fff; }
    .side-item.active { background:#1D4ED8; color:#fff; font-weight:600; }
    .side-item.active i { color:#fff; }
    .side-add { background:#E0262F; color:#fff; font-weight:700; font-size:15px; padding:12px 14px; border-radius:12px; margin:4px 0 4px; }
    .side-add i { color:#fff; }
    .side-add:hover { background:#C81E27; }
    .side-add.active { background:#E0262F; box-shadow:0 0 0 3px rgba(224,38,47,.35); }
    .side-kbd { margin-left:auto; font-family:var(--font-mono); font-size:11px; font-weight:600; background:rgba(255,255,255,.2); border-radius:6px; padding:2px 6px; }
    .side-item .nav-badge { position:static; margin-left:auto; }
    .side-foot { margin-top:auto; padding-top:14px; border-top:1px solid #1C2E57; display:flex; flex-direction:column; gap:8px; }
    .side-foot .lang-btn, .side-foot .logout { text-align:center; padding:9px 10px; display:block; }
    .side-foot .lang-btn { background:#152A55; border-color:#22345F; color:#fff; }
    .side-foot .logout { background:transparent; color:#FF9AA0; }
  }
  @media (min-width: 1200px) { .container { max-width:1340px; } }
  .subtabs { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }
  .subtab {
    flex:1 1 0; min-width:0; text-align:center; padding:10px 8px; border-radius:10px; background:var(--field-bg);
    border:1.5px solid var(--border); cursor:pointer; font-weight:700; font-size:13px; color:var(--hint);
    line-height:1.25; overflow-wrap:anywhere; display:flex; align-items:center; justify-content:center; gap:5px;
  }
  .subtab .nav-badge { position:static; }
  /* 4 вкладки на телефоне — сетка 2×2, чтобы ничего не вылезало за экран */
  @media (max-width:599px) { .subtabs.subtabs-many .subtab { flex:1 1 calc(50% - 4px); } }
  html, body { max-width:100%; overflow-x:clip; }
  .subtab.active { background:var(--btn); color:#fff; border-color:var(--btn); }
  .tab {
    text-align:center; padding: 10px 4px; border-radius: 14px; background: var(--card);
    border:2px solid var(--border); cursor:pointer; font-weight:700; font-family: var(--font-display);
    font-size:11px; text-transform:uppercase; letter-spacing:0.2px; transition: all .15s ease;
    display:flex; flex-direction:column; align-items:center; gap:5px;
    box-shadow: 0 1px 3px rgba(20,20,25,.04);
  }
  .tab .tab-icon {
    width:30px; height:30px; border-radius:50%; background:var(--field-bg); color:var(--blue);
    display:flex; align-items:center; justify-content:center; font-size:13px; flex:none; transition: all .15s ease;
  }
  .tab#tab-add { border-color:var(--btn); }
  .tab#tab-add .tab-icon { background:var(--danger-bg); color:var(--btn); }
  .tab#tab-add span:last-child { color:var(--btn); }
  .tab.active { color: var(--btn); }
  .tab.active .tab-icon { background:var(--btn); color:#fff; transform:scale(1.08); }
  .wh-banner {
    width:100%; background:var(--carbon); border:2px solid #0d1117; border-radius:16px; padding:12px 16px;
    display:flex; align-items:center; justify-content:center; gap:12px; cursor:pointer; margin-bottom:12px;
    box-shadow:0 8px 20px rgba(0,0,0,.25);
  }
  .wh-banner .stripe-pair { display:flex; gap:4px; }
  .wh-banner .stripe-pair span { width:8px; height:26px; border-radius:2px; transform:skewX(-12deg); }
  .wh-banner .wh-label { font-family:var(--font-display); font-weight:800; font-style:italic; font-size:18px; color:#fff; text-transform:uppercase; letter-spacing:0.5px; }
  .card {
    background: #fff; border:2px solid #DBEAFE; border-radius: 22px; padding: 16px; margin-bottom: 12px;
    box-shadow: 0 10px 25px -5px rgba(15,82,186,.08); overflow:hidden;
  }
  .field { margin-bottom: 10px; }
  .row2 { display:flex; gap:10px; }
  .row2 .field { flex:1; }
  label { display:block; font-size: 12px; color: var(--hint); margin-bottom: 4px; text-transform:uppercase; letter-spacing:0.4px; }
  label i { color:var(--btn); margin-right:4px; width:12px; text-align:center; }
  input, select, textarea {
    width: 100%; padding: 10px; border-radius: 10px; border: 1.5px solid var(--border);
    background: var(--field-bg); color: var(--text); font-size: 15px; font-family: var(--font-body);
  }
  input:focus, select:focus, textarea:focus { outline:none; border-color: var(--btn); box-shadow:0 0 0 3px rgba(225,6,0,.12); }
  .card-header {
    background:linear-gradient(90deg, var(--blue), #1a6fd4); color:#fff; padding:14px 16px; border-radius:20px 20px 0 0; margin:-16px -16px 14px;
    display:flex; align-items:center; gap:10px;
  }
  .card-header .dot { width:9px; height:9px; border-radius:50%; background:var(--btn); flex:none; box-shadow:0 0 0 4px rgba(225,6,0,.25); animation: pulse 1.6s infinite; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.4; } }
  .card-header h3 { margin:0; font-family:var(--font-display); font-weight:700; font-style:italic; font-size:17px; letter-spacing:0.3px; text-transform:uppercase; }
  .plate-wrap { position:relative; }
  .plate-chip {
    position:absolute; left:10px; top:50%; transform:translateY(-50%);
    font-size:11px; font-weight:700; color:var(--hint); background:var(--border); padding:2px 6px; border-radius:5px;
  }
  #plate { padding-left:44px; font-family:var(--font-mono); font-weight:600; letter-spacing:1px; text-transform:uppercase; }
  .plate-suggest {
    position:absolute; top:100%; left:0; right:0; margin-top:4px; background:var(--card);
    border:1.5px solid var(--border); border-radius:12px; box-shadow:0 8px 20px rgba(20,20,25,.12);
    z-index:20; overflow:hidden; max-height:240px; overflow-y:auto;
  }
  .plate-suggest .ps-item { padding:10px 14px; cursor:pointer; border-bottom:1px solid var(--border); }
  .plate-suggest .ps-item:last-child { border-bottom:none; }
  .plate-suggest .ps-item:active, .plate-suggest .ps-item:hover { background:var(--field-bg); }
  .plate-suggest .ps-plate { font-family:var(--font-mono); font-weight:700; font-size:14px; letter-spacing:0.5px; color:var(--text); }
  .plate-suggest .ps-owner { font-size:12px; color:var(--hint); margin-top:2px; }
  .checkbox-row { display:flex; align-items:center; gap:8px; }
  .checkbox-row input { width:auto; }
  .item-row { display:flex; gap:8px; align-items:center; margin-bottom:8px; }
  .item-row .item-name { flex:1.3; font-size:13px; color:var(--hint); min-width:0; }
  .item-row input { flex:1; padding:8px; font-size:13px; min-width:0; }
  .item-row select { flex:1.6; padding:8px; font-size:13px; min-width:0; }
  .other-stock-row { display:flex; gap:6px; align-items:center; margin-bottom:8px; }
  .other-stock-row select { flex:2; padding:8px; font-size:13px; min-width:0; }
  .other-stock-row input { flex:1; padding:8px; font-size:13px; min-width:0; }
  .other-stock-row button { flex:none; width:32px; height:32px; border-radius:8px; border:none; background:var(--danger-bg); color:var(--danger); font-size:14px; cursor:pointer; }
  .item-row .item-total { flex:0.9; font-size:12px; color:var(--hint); text-align:right; }
  .pick-search { margin:2px 0 14px; }
  .pick-search input { width:100%; }
  .pick-results { margin-top:6px; }
  .pick-item { display:flex; justify-content:space-between; align-items:center; gap:10px; padding:10px 12px; border:1px solid var(--border); border-radius:10px; margin-bottom:6px; background:var(--field-bg); cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .pick-item:active { transform:scale(.99); border-color:var(--blue); }
  .pick-item .pi-main { min-width:0; }
  .pick-item .pi-name { font-size:14px; font-weight:600; color:var(--text); overflow-wrap:anywhere; }
  .pick-item .pi-sub { font-size:12px; color:var(--hint); margin-top:2px; }
  .pick-item .pi-sub .pi-out { color:var(--danger); font-weight:600; }
  .pick-item .pi-price { flex:none; font-size:13px; font-family:var(--font-mono); color:var(--blue); font-weight:600; text-align:right; }
  .pick-note { font-size:13px; color:var(--hint); padding:4px 2px; }
  .pick-note.ok { color:var(--ok); font-weight:600; }
  .pick-flash { animation:pickFlash 1.4s ease; border-radius:10px; }
  @keyframes pickFlash { 0% { background:rgba(15,82,186,.20); } 60% { background:rgba(15,82,186,.12); } 100% { background:transparent; } }
  button.submit {
    width: 100%; padding: 14px; border: none; border-radius: 14px;
    background: linear-gradient(135deg, #1D4ED8 0%, #1E40AF 55%, #312E81 100%); color:#fff; font-size: 15px; font-weight: 700; font-family: var(--font-display);
    letter-spacing:0.5px; text-transform:uppercase; cursor: pointer; margin-top: 6px;
    box-shadow: 0 8px 18px rgba(29,78,216,.30);
  }
  button.submit:active { transform:scale(.98); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th { color:#fff; font-weight: 700; position: sticky; top: 0; background: #1E293B; font-family: var(--font-body); letter-spacing:0.4px; font-size:10px; text-transform:uppercase; }
  .table-wrap { overflow-x: auto; border:1px solid var(--border); border-radius: 12px; }
  .badge { display:inline-block; padding: 3px 9px; border-radius: 20px; font-size: 11px; font-weight:600; cursor:pointer; border:none; text-transform:uppercase; letter-spacing:0.3px; }
  .badge.linked { background: var(--ok-bg); color: var(--ok); }
  .badge.unlinked { background: var(--danger-bg); color: var(--danger); }
  .search { margin-bottom: 10px; }
  .hint-text { color: var(--hint); font-size: 12px; margin-top: 6px; }
  .msg { padding: 12px; border-radius: 10px; margin-bottom: 10px; font-size: 14px; }
  .msg.ok { background:var(--ok-bg); color:var(--ok); }
  .msg.err { background:var(--danger-bg); color:var(--danger); }
  .modal-overlay { display:none; position:fixed; inset:0; background:rgba(20,20,25,.55); align-items:center; justify-content:center; z-index:50; }
  .modal-overlay.open { display:flex; }
  .modal { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:18px; max-width:320px; width:90%; text-align:center; box-shadow: 0 12px 34px rgba(20,20,25,.25); }
  .modal-wide { max-width:480px; max-height:85vh; overflow-y:auto; }
  .modal img { width:180px; height:180px; margin: 10px auto; display:block; border-radius:10px; background:#fff; }
  .modal .link-text { font-size:12px; word-break:break-all; color:var(--hint); background:var(--field-bg); padding:8px; border-radius:10px; margin-bottom:10px; }
  .modal button { margin-top:8px; }
  .modal a.wa-btn { display:block; text-decoration:none; }
  .close-btn { background:transparent; border:none; color:var(--hint); font-size:14px; cursor:pointer; margin-top:6px; width:100%; padding:8px; }
  .history-toggle { background:transparent; border:none; color:var(--btn); font-size:12px; cursor:pointer; text-decoration:underline; padding:0; }
  .history-entry { padding:6px 0; border-bottom:1px dashed var(--border); font-size:12px; }
  .stats-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:10px; }
  .stats-card {
    background:linear-gradient(135deg, #EFF6FF, #EEF2FF); border:1px solid #DBEAFE; border-radius:16px; padding:14px;
    text-align:center;
  }
  .stats-card .label { font-size:10px; color:#64748B; margin-bottom:4px; font-weight:700; letter-spacing:0.5px; text-transform:uppercase; }
  .stats-card .amount { font-size:22px; font-weight:800; color:var(--blue); font-family: var(--font-display); }
  .stats-card .count { font-size:11px; color:var(--hint); margin-top:4px; }
  .known-client {
    margin-top:12px; background:var(--card); border:2px solid #BFDBFE; border-radius:18px;
    overflow:hidden; box-shadow: 0 6px 16px rgba(15,82,186,.08);
  }
  .cross-network-card {
    margin-top:12px; background:var(--card); border:1.5px solid #A7F3D0; border-radius:16px;
    padding:14px; box-shadow: 0 4px 12px rgba(5,150,105,.06);
  }
  .cross-network-card .cn-header {
    display:flex; align-items:center; gap:8px; color:#047857; font-weight:700; font-size:13.5px; margin-bottom:4px;
  }
  .cross-network-card .cn-hint { font-size:11.5px; color:var(--hint); margin-bottom:10px; }
  .cross-network-card .cn-entry {
    background:var(--field-bg); border-radius:10px; padding:10px 12px; margin-bottom:6px;
  }
  .cross-network-card .cn-entry:last-child { margin-bottom:0; }
  .cross-network-card .cn-entry-shop { font-size:13px; font-weight:700; color:var(--text); }
  .cross-network-card .cn-entry-date { font-size:11.5px; color:var(--hint); margin-top:1px; }
  .cross-network-card .kc-lv-items { margin-top:6px; padding-top:6px; border-top:1px dashed var(--border); }
  .cross-network-card .kc-lv-item { font-size:12px; color:var(--text); padding:1px 0; }
  .known-client .kc-header {
    background:linear-gradient(90deg, var(--blue), #1a6fd4); color:#fff; padding:12px 14px;
    display:flex; align-items:center; gap:8px;
  }
  .known-client .kc-header i { font-size:15px; }
  .known-client .kc-header .kc-close { margin-left:auto; width:32px; height:32px; flex:none; border:none; border-radius:50%; background:rgba(255,255,255,.2); color:#fff; display:flex; align-items:center; justify-content:center; cursor:pointer; padding:0; }
  .known-client .kc-header .kc-close i { font-size:17px; }
  .known-client .kc-header .kc-close:active { background:rgba(255,255,255,.35); }
  .kc-pass-row { display:flex; justify-content:center; align-items:center; gap:8px; margin-top:10px; }
  .kc-pass-tg { display:inline-flex; align-items:center; gap:6px; padding:7px 14px; border:none; border-radius:999px; background:#229ED9; color:#fff; font-size:13px; font-weight:700; font-family:inherit; cursor:pointer; }
  .kc-pass-tg i { font-size:15px; }
  .kc-pass-open { width:34px; height:34px; border:1px solid #DBEAFE; border-radius:50%; background:#EFF6FF; color:var(--blue); display:inline-flex; align-items:center; justify-content:center; cursor:pointer; padding:0; }
  .kc-pass-tg:active, .kc-pass-open:active { transform:scale(.96); }
  .known-client .kc-header span { font-family:var(--font-display); font-weight:700; font-style:italic; font-size:14px; text-transform:uppercase; letter-spacing:0.3px; }
  .known-client .kc-body { padding:16px; }
  .known-client .kc-person { display:flex; align-items:center; gap:14px; margin-bottom:16px; }
  .known-client .kc-avatar {
    width:58px; height:58px; border-radius:50%; background:var(--field-bg); color:var(--blue);
    display:flex; align-items:center; justify-content:center; font-family:var(--font-display);
    font-weight:700; font-size:22px; flex:none; border:2px solid #DBEAFE;
  }
  .known-client .kc-name { font-size:18px; font-weight:700; color:var(--text); line-height:1.25; }
  .known-client .kc-meta { font-size:13px; color:var(--hint); margin-top:3px; }
  .known-client .kc-call { display:inline-flex; align-items:center; gap:6px; color:var(--blue); font-weight:600; text-decoration:none; background:#EFF6FF; border:1px solid #DBEAFE; border-radius:999px; padding:3px 10px; margin:2px 0; }
  .known-client .kc-call i { font-size:11px; }
  .known-client .kc-call:active { background:#DBEAFE; }
  .known-client .kc-history-label { font-size:11px; font-weight:700; color:var(--hint); text-transform:uppercase; letter-spacing:0.4px; margin-bottom:8px; }
  .known-client .kc-last-visit {
    background:var(--field-bg); border-radius:12px; padding:11px 13px; margin-bottom:14px;
  }
  .known-client .kc-last-visit .kc-lv-top { display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .known-client .kc-last-visit .kc-lv-service { font-size:14px; font-weight:700; color:var(--text); }
  .known-client .kc-last-visit .kc-lv-date { font-size:12px; color:var(--hint); margin-top:2px; }
  .known-client .kc-lv-mileage { font-size:12px; color:var(--blue); font-weight:600; margin-top:8px; }
  .mileage-compare { font-size:12.5px; margin-top:6px; padding:8px 10px; border-radius:8px; }
  .mileage-compare.over { background:#FEF2F2; color:#B3241C; font-weight:600; }
  .mileage-compare.ok { background:#F0FDF4; color:#15803D; }
  .known-client .kc-last-visit .kc-lv-cost { font-size:16px; font-weight:700; color:var(--blue); flex:none; }
  .known-client .kc-lv-items { margin-top:9px; padding-top:9px; border-top:1px dashed var(--border); }
  .kc-repeat { width:100%; margin-top:10px; padding:11px 12px; border:none; border-radius:12px; background:#16A34A; color:#fff; font-weight:800; font-size:14px; font-family:inherit; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:8px; }
  .kc-repeat:active { transform:scale(.98); }
  .kc-new-owner { margin:8px 0 12px; padding:6px 0; border:none; background:none; color:var(--hint); font-size:12.5px; font-weight:600; font-family:inherit; cursor:pointer; display:inline-flex; align-items:center; gap:6px; text-decoration:underline; }
  .kc-new-owner-box { margin-bottom:12px; padding:12px; border-radius:12px; background:#FEF3C7; color:#78350F; font-size:13px; line-height:1.4; }
  .kc-new-owner-box b { display:block; font-size:14px; margin-bottom:4px; }
  .kc-new-owner-box button { margin-top:8px; padding:7px 12px; border:1px solid #D97706; border-radius:10px; background:#fff; color:#92400E; font-weight:700; font-size:12.5px; font-family:inherit; cursor:pointer; }
  .km-chips { display:flex; flex-wrap:wrap; gap:5px; margin-top:6px; }
  .dk-row { display:flex; align-items:center; gap:8px; }
  .dk-row input { flex:1; min-width:0; }
  .dk-unit { font-size:13px; color:var(--hint); white-space:nowrap; }
  #dkSuggest .km-chip { margin-top:6px; }
  .dk-hint { font-size:12.5px; color:#475569; margin-top:6px; line-height:1.45; }
  .dk-hint b { color:var(--blue); }
  .km-chip { border:1px solid var(--border); background:#fff; border-radius:999px; padding:5px 9px; font-size:12px; font-weight:700; color:#475569; cursor:pointer; font-family:inherit; }
  .km-chip.on { background:var(--blue); border-color:var(--blue); color:#fff; }
  .add-form { max-width:760px; }
  .af-title { display:flex; align-items:center; gap:10px; font-family:var(--font-display); font-weight:700; font-style:italic; font-size:18px; text-transform:uppercase; letter-spacing:.3px; color:var(--darkblue, #0A2540); margin:2px 4px 10px; }
  .af-title .dot { width:9px; height:9px; border-radius:50%; background:var(--btn); flex:none; box-shadow:0 0 0 4px rgba(225,6,0,.18); }
  .af-sec { background:#fff; border:1px solid #E2E8F0; border-radius:18px; padding:14px; margin-bottom:12px; box-shadow:0 4px 14px -6px rgba(15,82,186,.10); }
  .af-h { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:800; color:#0F172A; text-transform:uppercase; letter-spacing:.5px; margin-bottom:12px; }
  .af-h i { width:28px; height:28px; border-radius:9px; background:#EFF6FF; color:var(--blue); display:inline-flex; align-items:center; justify-content:center; font-size:13px; }
  .af-sub { font-size:12px; color:var(--hint); text-transform:uppercase; letter-spacing:.4px; margin:12px 0 6px; }
  .sp-card { margin-top:12px; border:1px solid #cfe0fb; background:#f4f8ff; border-radius:14px; padding:12px 14px; font-size:13px; color:#1e2a44; }
  .sp-head { display:flex; align-items:flex-start; gap:8px; }
  .sp-head b { font-size:14px; flex:1; line-height:1.35; }
  .sp-head small { display:block; font-weight:400; color:#5b6b8c; font-size:12px; }
  .sp-x { border:none; background:none; color:#7a89a8; font-size:16px; padding:0 2px; cursor:pointer; }
  .sp-alt { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 2px; align-items:center; color:#5b6b8c; font-size:12px; }
  .sp-alt button { border:1px solid #cfe0fb; background:#fff; color:#1d4ed8; border-radius:999px; padding:3px 10px; font-size:12px; cursor:pointer; }
  .sp-grid { display:grid; grid-template-columns:auto minmax(0,1fr); gap:4px 10px; margin-top:8px; }
  .sp-grid span { color:#5b6b8c; }
  .sp-grid div { font-weight:600; white-space:pre-line; overflow-wrap:anywhere; }
  .sp-grid div i { font-weight:400; font-style:normal; color:#5b6b8c; }
  .sp-stock { margin-top:10px; border-top:1px dashed #cfe0fb; padding-top:8px; }
  .sp-prod { display:flex; justify-content:space-between; gap:8px; padding:3px 0; }
  .sp-prod em { font-style:normal; color:#15803d; white-space:nowrap; }
  .sp-badge { display:inline-block; font-size:11px; border-radius:6px; padding:0 6px; margin-left:4px; background:#e7f6ec; color:#15803d; font-weight:600; }
  .sp-badge.hot { background:#fff4d6; color:#92600a; }
  .sp-fill { margin-top:10px; width:100%; border:none; border-radius:10px; padding:10px; background:#1d4ed8; color:#fff; font-weight:700; font-size:14px; cursor:pointer; }
  .sp-more { margin-top:8px; }
  .sp-more summary { cursor:pointer; color:#1d4ed8; font-weight:600; }
  .sp-note { margin-top:8px; font-size:12px; color:#5b6b8c; }
  .sp-note.warn { color:#92600a; background:#fff4d6; border-radius:8px; padding:6px 8px; }
  .mil-grid { display:grid; grid-template-columns:minmax(0,1fr) 22px minmax(0,1fr); gap:6px; align-items:end; }
  .mil-arrow { text-align:center; color:#94A3B8; padding-bottom:14px; font-size:13px; }
  .mil-l { font-size:12px; color:var(--hint); margin-bottom:5px; }
  .mil-f { position:relative; }
  .mil-f input { padding-right:62px; font-size:18px; font-weight:700; font-family:var(--font-mono); }
  .mil-f input::-webkit-outer-spin-button, .mil-f input::-webkit-inner-spin-button { -webkit-appearance:none; margin:0; }
  .mil-f input[type=number] { -moz-appearance:textfield; }
  .mil-f span { position:absolute; right:12px; top:50%; transform:translateY(-50%); font-size:12px; color:var(--hint); pointer-events:none; }
  .mil-f.accent input { border-color:#93C5FD; background:#F8FBFF; }
  .km-seg { display:grid !important; grid-template-columns:repeat(auto-fit, minmax(64px, 1fr)); gap:4px; background:#EEF2F7; border-radius:12px; padding:4px; margin-top:10px; }
  .km-seg .km-chip { border:0; background:transparent; border-radius:9px; padding:9px 4px; font-size:13px; color:#475569; }
  .km-seg .km-chip.on { background:var(--blue); color:#fff; box-shadow:0 2px 6px rgba(15,82,186,.25); }
  .dk-hint:not(:empty) { background:#ECFDF5; color:#065F46; border-radius:10px; padding:9px 11px; font-size:13px; margin-top:8px; }
  .dk-hint b { color:#047857 !important; }
  .af-add { display:flex; flex-wrap:wrap; gap:6px; margin-top:4px; }
  .af-add:empty { display:none; }
  .af-add button { border:1.5px dashed #CBD5E1; background:#fff; color:#334155; border-radius:999px; padding:6px 11px; font-size:12.5px; font-weight:700; cursor:pointer; font-family:inherit; }
  .af-add button i { color:var(--blue); margin-right:3px; }
  .add-form .item-row { gap:5px; }
  .add-form .item-row .item-name { flex:1 !important; font-size:12.5px; line-height:1.2; }
  .add-form .item-row input { padding:8px 6px; }
  .add-form .item-row select { flex:1.5; padding:8px 4px; }
  .item-row .row-x { flex:none; width:26px; height:34px; border:0; background:transparent; color:#94A3B8; font-size:15px; cursor:pointer; border-radius:8px; }
  .item-row .row-x:hover { background:#F1F5F9; color:var(--btn); }
  .af-ghost { width:100%; padding:9px; border:1.5px dashed #CBD5E1; background:#fff; border-radius:12px; color:#334155; font-weight:700; font-size:13px; cursor:pointer; font-family:inherit; }
  .pay-seg { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:6px; }
  @media (min-width:480px) { .pay-seg { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .pay-seg button { border:1.5px solid var(--border); background:#fff; border-radius:12px; padding:10px 6px; font-size:13px; font-weight:700; color:#334155; cursor:pointer; font-family:inherit; }
  .pay-seg button.on { border-color:var(--blue); background:#EFF6FF; color:var(--blue); }
  .af-bar { position:sticky; bottom:calc(76px + env(safe-area-inset-bottom, 0px)); z-index:20; display:flex; align-items:center; gap:12px; background:#fff; border:1px solid #E2E8F0; border-radius:18px; padding:10px 10px 10px 16px; box-shadow:0 8px 24px rgba(15,23,42,.14); margin-top:4px; }
  @media (min-width:900px) { .af-bar { bottom:14px; } }
  .af-bar-total { flex:1; min-width:0; }
  .af-bar-total span { display:block; font-size:11px; color:var(--hint); text-transform:uppercase; letter-spacing:.4px; }
  .af-bar-total b { display:block; font-size:21px; font-weight:800; font-family:var(--font-mono); color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .af-save { flex:none; border:0; border-radius:14px; padding:13px 20px; background:linear-gradient(135deg, #E63946, #C1121F); color:#fff; font-size:15px; font-weight:800; font-family:var(--font-display); cursor:pointer; box-shadow:0 6px 14px rgba(230,57,70,.30); }
  /* ---- Ввод замены: компактная карточка клиента ---- */
  .known-client.kc-compact { border:1.5px solid #A7DCC4; box-shadow:none; padding:10px 12px; border-radius:16px; }
  .kc-compact .kc-top { display:flex; align-items:center; gap:10px; }
  .kc-compact .kc-avatar { width:40px; height:40px; font-size:15px; border:0; background:#E7F6EF; color:#0F6B4C; }
  .kc-compact .kc-top-main { flex:1; min-width:0; }
  .kc-compact .kc-name { font-size:15.5px; }
  .kc-compact .kc-visits { font-size:12px; font-weight:700; color:#0F6B4C; white-space:nowrap; }
  .kc-compact .kc-meta { font-size:12.5px; margin-top:1px; }
  .kc-more-btn { flex:none; border:0; background:transparent; color:var(--blue); font:inherit; font-size:13px; font-weight:700; padding:8px 4px; cursor:pointer; white-space:nowrap; }
  .kc-more-btn i { font-size:10px; transition:transform .15s; }
  .kc-more-btn.open i { transform:rotate(180deg); }
  .kc-last-line { margin-top:8px; font-size:12.5px; color:#334155; background:#F4F7FA; border-radius:10px; padding:7px 10px; line-height:1.4; }
  .kc-last-line b { font-family:var(--font-mono); }
  .kc-notes-box { margin-top:8px; display:flex; flex-direction:column; gap:6px; }
  .kc-note { margin-top:8px; font-size:12.5px; line-height:1.45; color:#78350F; background:#FFFBEB; border:1px solid #FCD34D; border-radius:10px; padding:7px 10px; white-space:pre-wrap; word-break:break-word; }
  .kc-notes-box .kc-note { margin-top:0; }
  .kc-note i { color:#D97706; margin-right:2px; }
  .known-client .kc-last-visit + .kc-last-visit { margin-top:8px; }
  .notes-shared-hint { font-size:11.5px; color:var(--hint); margin-top:4px; }
  .kc-quick { display:flex; gap:6px; margin-top:8px; overflow-x:auto; scrollbar-width:none; }
  .kc-quick::-webkit-scrollbar { display:none; }
  .kc-quick:empty { display:none; }
  .kc-compact .kc-repeat { width:auto; flex:none; margin:0; padding:10px 14px; font-size:13.5px; border-radius:11px; }
  .kc-presets { display:flex; gap:6px; }
  .kc-presets:empty { display:none; }
  .kc-preset { flex:none; border:1.5px solid #BFDBFE; background:#F5F9FF; color:#1E3A8A; border-radius:11px; padding:9px 12px; font:inherit; font-size:13px; font-weight:700; cursor:pointer; white-space:nowrap; }
  .kc-details { margin-top:10px; border-top:1px dashed var(--border); padding-top:10px; }
  .kc-details[hidden] { display:none; }
  .kc-detail-actions { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:10px; }
  .kc-edit-data { border:1px solid var(--border); background:#fff; border-radius:10px; padding:8px 12px; font:inherit; font-size:13px; font-weight:700; color:#334155; cursor:pointer; }
  .add-form.kc-known .af-owner { display:none; }
  /* масло: литры кнопками −/+ */
  .lit-step { display:flex; align-items:center; gap:4px; flex:1.2; min-width:0; }
  .lit-step input { flex:1; min-width:0; text-align:center; font-family:var(--font-mono); font-weight:700; }
  .lit-step button { flex:none; width:34px; height:36px; border:1px solid #BFDBFE; border-radius:9px; background:#fff; color:var(--blue); font-size:17px; font-weight:800; cursor:pointer; font-family:inherit; }
  /* поле товара: на телефоне — открываем свою шторку вместо системного списка */
  .pick-wrap { position:relative; flex:1.6; min-width:0; display:flex; }
  .pick-wrap select { flex:1; width:100%; }
  .pick-ov { display:none; position:absolute; inset:0; border:0; background:transparent; cursor:pointer; }
  /* фильтры и работы — плитки-галочки */
  /* ---- «Товары и работа»: плитки категорий + чек ---- */
  .af-legacy { display:none !important; }
  .cat-tiles { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:10px; }
  /* пробег и срок напоминания внутри окна «Моторное масло» / «АКПП» */
  #cs_extra:empty { display:none; }
  #cs_extra { margin-bottom:12px; }
  #cs_extra .af-sec { background:none; border:0; box-shadow:none; padding:0; margin:0; }
  #cs_extra .af-h { margin-bottom:8px; }
  @media (min-width:700px) { .cat-tiles { grid-template-columns:repeat(auto-fill, minmax(210px, 1fr)); } }
  .cat-tile { display:flex; flex-direction:row; align-items:center; gap:10px; min-height:72px; text-align:left; border:1.5px solid var(--border); background:#fff; border-radius:16px; padding:10px 11px; font:inherit; color:var(--text); cursor:pointer; min-width:0; transition:border-color .12s, transform .08s; }
  @media (min-width: 640px) { .cat-tile { flex-direction:column; align-items:flex-start; min-height:104px; padding:12px 12px 11px; } }
  .cat-tile:hover { border-color:var(--blue); }
  .cat-tile:active { transform:scale(.98); }
  .cat-tile .ci { width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center; flex:none; font-size:19px; background:#EFF6FF; color:var(--blue); }
  .cat-tile .ci.g { background:#ECFDF5; color:#047857; } .cat-tile .ci.v { background:#F5F3FF; color:#6D28D9; } .cat-tile .ci.y { background:#FFFBEB; color:#B45309; }
  .cat-tile div { min-width:0; width:100%; display:flex; flex-direction:column; }
  .cat-tile b { font-size:15px; font-weight:700; line-height:1.25; }
  .cat-tile small { font-size:12.5px; color:var(--hint); line-height:1.35; margin-top:3px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  @media (min-width: 640px) { .cat-tiles { grid-template-columns:repeat(3, minmax(0,1fr)); } }
  @media (min-width: 1500px) { .cat-tiles { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .cat-tile.on { border-color:var(--blue); background:#F5F9FF; }
  .cat-tile.on small { color:var(--blue); font-weight:600; }
  .it-rcpt { margin-top:14px; background:#FAFBFC; border:1px solid #E2E8F0; border-radius:16px; padding:12px 14px; position:relative; }
  .it-rcpt::before, .it-rcpt::after { content:''; position:absolute; left:14px; right:14px; height:0; border-top:2px dashed #E2E8F0; }
  .it-rcpt::before { top:-1px; border:0; }
  .it-rcpt::after { display:none; }
  .ir-h { display:flex; justify-content:space-between; align-items:baseline; font-size:12px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; color:var(--hint); padding-bottom:8px; border-bottom:1.5px dashed #CBD5E1; }
  .ir-h b { font-family:var(--font-mono); font-size:13px; letter-spacing:.08em; color:#334155; }
  .ir-line { display:flex; align-items:center; gap:8px; padding:9px 0; border-bottom:1px dotted #CBD5E1; }
  .ir-line:last-of-type { border-bottom:0; }
  .ir-main { flex:1; min-width:0; cursor:pointer; }
  .ir-main b { display:block; font-size:14px; font-weight:700; overflow-wrap:anywhere; }
  .ir-main span { display:block; font-size:12px; color:var(--hint); margin-top:1px; }
  .ir-step { display:flex; align-items:center; gap:4px; font-family:var(--font-mono); font-size:13px; font-weight:600; }
  .ir-step button { width:28px; height:28px; border:1px solid var(--border); background:#fff; border-radius:8px; font-size:15px; font-weight:700; cursor:pointer; color:var(--blue); padding:0; }
  .ir-sum { font-family:var(--font-mono); font-size:14px; font-weight:600; white-space:nowrap; min-width:70px; text-align:right; }
  .ir-x { border:0; background:none; color:#94A3B8; font-size:15px; cursor:pointer; padding:4px; }
  .ir-disc .ir-sum { color:#B3241C; }
  .ir-tot { display:flex; justify-content:space-between; align-items:baseline; padding-top:10px; margin-top:2px; border-top:1.5px dashed #CBD5E1; font-weight:800; }
  .ir-tot b { font-family:var(--font-mono); font-size:18px; }
  .ir-empty { font-size:13px; color:var(--hint); padding:12px 0 4px; line-height:1.45; }
  @media (min-width:1200px) { .it-rcpt { display:none; } }
  .cs-tabs { display:flex; gap:6px; overflow-x:auto; margin:0 0 10px; padding-bottom:2px; }
  .cs-tabs:empty { display:none; }
  .cs-tabs button { flex:none; border:1.5px solid var(--border); background:#fff; border-radius:999px; padding:8px 13px; font:inherit; font-size:13px; font-weight:700; color:#334155; cursor:pointer; }
  .cs-tabs button.on { background:var(--blue); border-color:var(--blue); color:#fff; }
  .cs-tabs button.has::after { content:'✓'; margin-left:5px; }
  .cs-freq { display:flex; flex-wrap:wrap; gap:6px; }
  .cs-freq button { border:1.5px solid #BFDBFE; background:#F5F9FF; color:#0B1B3F; border-radius:999px; padding:8px 12px; font:inherit; font-size:13px; font-weight:700; cursor:pointer; max-width:100%; text-align:left; }
  .cs-freq button em { font-style:normal; font-family:var(--font-mono); font-weight:600; font-size:12px; color:#1D4ED8; margin-left:6px; }
  .cs-freq button.on { background:var(--blue); border-color:var(--blue); color:#fff; }
  .cs-freq button.on em { color:#fff; }
  .cs-man { display:grid; grid-template-columns:minmax(0,1fr) 120px; gap:8px; }
  .cs-man input { margin:0; }
  .cs-qty { display:flex; align-items:center; gap:8px; margin:6px 0 10px; }
  .cs-qty button { width:44px; height:44px; border:1px solid var(--border); border-radius:10px; background:#fff; font:inherit; font-size:20px; font-weight:700; cursor:pointer; color:var(--blue); }
  .cs-qty b { font-family:var(--font-mono); font-size:18px; min-width:70px; text-align:center; }
  .cs-qty label { display:flex; align-items:baseline; justify-content:center; gap:6px; min-width:110px; padding:0 6px; cursor:text; font-family:var(--font-mono); font-size:18px; font-weight:700; }
  .cs-qty label { color:var(--text); }
  .cs-qty input { width:3.4em; margin:0; border:0; border-bottom:2px dashed #c8d3e6; border-radius:0; background:transparent; box-shadow:none; font:inherit; color:inherit; text-align:center; padding:2px 0; outline:none; }
  .cs-qty input:focus { border-color:transparent; border-bottom-color:var(--blue); box-shadow:none; }
  .cs-del { width:100%; margin-top:8px; height:44px; border:1.5px solid #FECACA; background:#FEF2F2; color:#B3241C; border-radius:12px; font:inherit; font-weight:700; cursor:pointer; }
  .flt-tiles { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:6px; margin:4px 0 8px; }
  @media (min-width:600px) { .flt-tiles { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .flt-tile { text-align:left; border:1.5px solid var(--border); background:#fff; border-radius:12px; padding:9px 11px; min-height:50px; font:inherit; color:var(--text); cursor:pointer; display:flex; flex-direction:column; justify-content:center; gap:2px; }
  .flt-tile b { font-size:13.5px; font-weight:700; }
  .flt-tile span { font-size:11.5px; color:var(--hint); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .flt-tile.on { border-color:var(--blue); background:#EFF6FF; }
  .flt-tile.on b::before { content:'✓ '; color:var(--blue); }
  .flt-tile.add b { color:var(--blue); }
  .labor-btn { display:inline-flex; align-items:center; gap:6px; border:1.5px solid #FDE68A; background:#FFFBEB; color:#92400E; border-radius:999px; padding:7px 13px; font:inherit; font-size:13px; font-weight:700; cursor:pointer; margin:2px 0 8px; }
  .disc-seg { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:6px; }
  .disc-seg button, .disc-unit button { border:1.5px solid var(--border); background:#fff; border-radius:12px; padding:10px 4px; font:inherit; font-size:13px; font-weight:700; color:#334155; cursor:pointer; }
  .disc-seg button.on, .disc-unit button.on { border-color:var(--blue); background:#EFF6FF; color:var(--blue); }
  .disc-custom { display:flex; gap:6px; margin-top:8px; }
  .disc-custom input { flex:1; min-width:0; margin:0; }
  .disc-unit { display:flex; gap:4px; }
  .disc-unit button { padding:8px 12px; }
  .disc-sum { margin-top:10px; padding:10px 12px; background:var(--field-bg); border-radius:12px; font-size:13px; }
  .disc-sum div { display:flex; justify-content:space-between; gap:8px; padding:2px 0; }
  .disc-sum .d-minus { color:#B3241C; font-weight:700; }
  /* сумма позиции в чеке — нажимается, чтобы вписать свою цену */
  .rc-sum { border:0; background:none; padding:2px 0; font:inherit; font-family:var(--font-mono); font-size:15px; font-weight:600; color:inherit; cursor:pointer; white-space:nowrap; border-bottom:1px dashed var(--hint); text-align:right; }
  .rc-sum:hover { color:var(--blue); border-bottom-color:var(--blue); }
  .rc-up { display:block; font-size:11px; font-weight:700; color:#16A34A; border:0; }
  .disc-sum .d-pay { font-size:16px; font-weight:800; padding-top:6px; margin-top:4px; border-top:1px dashed var(--border); }
  .disc-sum .d-pay b, .disc-sum b { font-family:var(--font-mono); }
  .disc-chip { border:1.5px solid var(--border); background:#fff; border-radius:10px; padding:0 12px; font:inherit; font-size:13px; font-weight:700; color:#334155; cursor:pointer; }
  .disc-warn { color:#B3241C; font-size:12px; margin-top:6px; }
  .rcpt-line.rcpt-disc em, .rc-line.rc-disc em { color:#B3241C; }
  .debt-terms { display:flex; gap:6px; flex-wrap:wrap; margin:4px 0 10px; }
  .debt-terms button { border:1px solid #F5D9A8; background:#fff; color:#8A4B06; border-radius:999px; padding:7px 12px; font:inherit; font-size:12.5px; font-weight:700; cursor:pointer; }
  .debt-terms button.on { background:#8A4B06; color:#fff; border-color:#8A4B06; }
  /* шторки (выбор товара, чек) и экран «Сохранено» */
  .ob-sheet-bg { position:fixed; inset:0; background:rgba(11,27,63,.5); z-index:80; opacity:0; pointer-events:none; transition:opacity .2s; }
  .ob-sheet-bg.open { opacity:1; pointer-events:auto; }
  .ob-sheet { position:fixed; left:0; right:0; bottom:0; z-index:81; background:#fff; border-radius:22px 22px 0 0; max-height:88vh; display:flex; flex-direction:column; transform:translateY(105%); transition:transform .25s ease; box-shadow:0 -10px 30px rgba(15,23,42,.18); padding-bottom:env(safe-area-inset-bottom, 0px); }
  .ob-sheet:not(.open) { visibility:hidden; transition:transform .25s ease, visibility 0s .25s; }
  .ob-sheet.open { transform:translateY(0); visibility:visible; }
  @media (min-width:900px) { .ob-sheet { left:50%; right:auto; width:480px; margin-left:-240px; bottom:auto; top:50%; border-radius:20px; transform:translateY(-40%); opacity:0; } .ob-sheet.open { transform:translateY(-50%); opacity:1; } }
  .ob-sheet-h { display:flex; align-items:center; gap:10px; padding:10px 16px 8px; }
  .ob-sheet-h::before { content:''; position:absolute; top:7px; left:50%; width:40px; height:5px; margin-left:-20px; border-radius:3px; background:#CBD5E1; }
  .ob-sheet-h b { flex:1; font-family:'Sora', var(--font-display), sans-serif; font-size:18px; font-weight:800; margin-top:6px; }
  .ob-sheet-x { width:40px; height:40px; border:0; border-radius:20px; background:#F1F5F9; font-size:16px; cursor:pointer; margin-top:6px; }
  .ob-sheet-body { overflow-y:auto; padding:4px 16px 12px; flex:1; -webkit-overflow-scrolling:touch; }
  .ob-sheet-foot { padding:10px 16px 14px; border-top:1px solid #EEF2F7; }
  .ps-grp { font-size:11px; font-weight:800; letter-spacing:.06em; color:var(--hint); text-transform:uppercase; margin:12px 0 6px; }
  .ps-item { width:100%; display:flex; align-items:center; gap:10px; min-height:58px; text-align:left; border:1.5px solid var(--border); background:#fff; border-radius:14px; padding:8px 12px; margin-bottom:6px; font:inherit; color:var(--text); cursor:pointer; }
  .ps-item.on { border-color:var(--blue); background:#EFF6FF; }
  .ps-item.out { opacity:.55; }
  .ps-item div { flex:1; min-width:0; display:flex; flex-direction:column; }
  .ps-item b { font-size:14.5px; overflow-wrap:anywhere; }
  .ps-item small { font-size:12px; color:#047857; }
  .ps-item small.low { color:#B45309; }
  .ps-item small.none { color:var(--hint); }
  .ps-item em { font-style:normal; font-family:var(--font-mono); font-weight:600; font-size:14px; }
  .ps-search { width:100%; height:46px; margin-top:2px; }
  .ps-lit { display:grid; grid-template-columns:repeat(6, minmax(0,1fr)); gap:6px; margin-bottom:10px; }
  .ps-lit button { height:44px; border:1px solid var(--border); border-radius:10px; background:#fff; font:inherit; font-weight:700; font-size:15px; cursor:pointer; }
  .ps-lit button.on { background:var(--blue); color:#fff; border-color:var(--blue); }
  .ps-go, .sv-next { width:100%; height:54px; border:0; border-radius:14px; background:#0B1B3F; color:#fff; font:inherit; font-size:16px; font-weight:800; cursor:pointer; }
  .rc-line { display:flex; align-items:center; gap:8px; padding:10px 0; border-bottom:1px dashed var(--border); }
  .rc-line div { flex:1; min-width:0; display:flex; flex-direction:column; }
  .rc-line b { font-size:14px; overflow-wrap:anywhere; }
  .rc-line span { font-size:12px; color:var(--hint); }
  .rc-line span a { color:var(--blue); font-weight:700; text-decoration:none; cursor:pointer; }
  .rc-line em { font-style:normal; font-family:var(--font-mono); font-weight:600; font-size:15px; white-space:nowrap; }
  .rc-x { flex:none; width:34px; height:34px; border:0; border-radius:9px; background:#F1F5F9; color:#64748B; font-size:13px; cursor:pointer; }
  .rc-total { display:flex; justify-content:space-between; align-items:baseline; margin:12px 0 6px; }
  .rc-total span { color:var(--hint); font-size:14px; }
  .rc-total b { font-family:var(--font-mono); font-size:28px; font-weight:600; }
  #rcPayHost .af-sec { border:0; box-shadow:none; padding:0; margin:8px 0 0; }
  .sv-wrap { position:fixed; inset:0; z-index:90; background:#F3F5FA; display:flex; flex-direction:column; align-items:center; overflow-y:auto; padding:40px 16px calc(24px + env(safe-area-inset-bottom, 0px)); }
  .sv-wrap[hidden] { display:none; }
  .sv-in { width:100%; max-width:440px; display:flex; flex-direction:column; gap:12px; }
  .sv-ok { width:76px; height:76px; border-radius:50%; background:#0F6B4C; color:#fff; display:flex; align-items:center; justify-content:center; font-size:34px; margin:0 auto; }
  .sv-title { text-align:center; font-family:'Sora', var(--font-display), sans-serif; font-size:24px; font-weight:800; }
  .sv-sub { text-align:center; color:var(--hint); font-size:14px; margin-top:-6px; }
  .sv-card { background:#fff; border-radius:16px; padding:12px 14px; display:flex; flex-direction:column; gap:8px; font-size:14px; }
  .sv-card div { display:flex; justify-content:space-between; gap:10px; }
  .sv-card div span { color:var(--hint); }
  .sv-card div b { text-align:right; }
  .sv-send { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; }
  .sv-send:has(> :nth-child(3)) { grid-template-columns:repeat(3, minmax(0,1fr)); }
  .sv-send a, .sv-send button { height:50px; border:0; border-radius:14px; color:#fff; font:inherit; font-size:15px; font-weight:800; display:flex; align-items:center; justify-content:center; gap:8px; text-decoration:none; cursor:pointer; }
  .sv-tg { background:#229ED9; } .sv-wa { background:#1FA855; } .sv-qr { background:#475569; }
  .sv-ok[hidden] { display:none; }
  .sv-badge { margin:0 auto; background:#E3F4EC; color:#0F6B4C; font-size:13px; font-weight:800; padding:6px 12px; border-radius:999px; display:inline-flex; align-items:center; gap:6px; }
  .sv-badge[hidden] { display:none; }
  .sv-qrbox { background:#fff; border-radius:20px; padding:16px; display:flex; flex-direction:column; align-items:center; gap:10px; }
  .sv-qrbox[hidden] { display:none; }
  .sv-qrbox img { width:min(68vw, 260px); height:min(68vw, 260px); display:block; image-rendering:pixelated; }
  .sv-qrhint { font-size:13px; color:var(--hint); text-align:center; }
  .sv-more { height:44px; border:1px dashed #CBD5E1; border-radius:14px; background:transparent; font:inherit; font-size:14px; font-weight:700; color:var(--text); cursor:pointer; display:flex; align-items:center; justify-content:center; gap:8px; }
  .sv-more[hidden] { display:none; }
  .sv-more.open i { transform:rotate(180deg); }
  .sv-card.sv-hide { display:none; }
  .sv-note { font-size:13px; color:#047857; text-align:center; }
  .sv-next { background:var(--btn); height:58px; font-size:17px; margin-top:6px; }
  .sv-row { display:flex; gap:8px; }
  .sv-row button { flex:1; height:46px; border:1px solid var(--border); border-radius:14px; background:#fff; font:inherit; font-size:14px; font-weight:700; cursor:pointer; color:var(--text); }
  .sv-row .sv-undo { color:var(--danger); border-color:#F3C4C7; }
  .sv-row .sv-undo:disabled { opacity:.45; cursor:default; }
  @media (max-width: 899px) {
    .pick-ov { display:block; }
    .af-bar-total { cursor:pointer; }
    .af-bar-total span::after { content:' ▲'; font-size:10px; }
    .add-form #fluidsList .item-row { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr) 30px; grid-template-areas:"n n x" "s s s" "p l l"; gap:6px 6px; align-items:center; background:#F8FAFC; border-radius:12px; padding:8px; }
    .add-form #fluidsList .item-row > .item-name { grid-area:n; font-weight:700; color:#334155; }
    .add-form #fluidsList .item-row > .row-x { grid-area:x; }
    .add-form #fluidsList .item-row > .pick-wrap, .add-form #fluidsList .item-row > select, .add-form #fluidsList .item-row > input[id^="fluid_brand_"] { grid-area:s; }
    .add-form #fluidsList .item-row > input[id^="fluid_price_"] { grid-area:p; }
    .add-form #fluidsList .item-row > .lit-step { grid-area:l; }
    .add-form #fluidsList .item-row > .pick-wrap select { padding:10px; font-size:14px; font-weight:600; }
  }
  /* Колонки формы: на телефоне — обычный поток (display:contents сохраняет
     липкую панель «Итого» внизу), на компьютере — форма слева, чек справа */
  .af-main, .af-side { display:contents; }
  .af-rcpt, .af-keys, .af-kbd { display:none; }
  .preset-box { margin:12px 0 0; }
  .preset-box[hidden] { display:none; }
  .preset-h { font-size:12px; color:var(--hint); text-transform:uppercase; letter-spacing:.4px; margin-bottom:6px; display:flex; gap:6px; align-items:baseline; flex-wrap:wrap; }
  .preset-h small { text-transform:none; letter-spacing:0; font-size:12px; }
  .preset-list { display:grid; grid-template-columns:repeat(auto-fill, minmax(180px, 1fr)); gap:8px; }
  .preset-btn { text-align:left; border:1.5px solid #BFDBFE; background:#F5F9FF; border-radius:14px; padding:10px 12px; cursor:pointer; font-family:inherit; color:var(--text); display:flex; flex-direction:column; gap:3px; }
  .preset-btn:hover { border-color:var(--blue); background:#EFF6FF; }
  .preset-btn b { font-size:13.5px; line-height:1.25; }
  .preset-btn span { font-size:12px; color:#475569; line-height:1.3; }
  .preset-btn em { font-style:normal; font-family:var(--font-mono); font-weight:600; font-size:14px; color:var(--darkblue); display:flex; justify-content:space-between; gap:6px; }
  .preset-btn em small { font-family:var(--font-body); font-weight:600; font-size:11px; color:#1D4ED8; }
  @media (min-width: 1200px) {
    .add-form { max-width:none; display:grid; grid-template-columns:minmax(0, 1fr) 380px; gap:0 20px; align-items:start; }
    .af-title { grid-column:1 / -1; }
    .af-keys { display:inline; margin-left:auto; font-family:var(--font-body); font-style:normal; text-transform:none; letter-spacing:0; font-size:12.5px; font-weight:500; color:var(--hint); }
    .af-main, .af-side { display:block; min-width:0; }
    /* колонка чека не выше экрана: длинный список товаров и блок оплаты
       прокручиваются внутри, а «Итого» и «Сохранить» всегда видны внизу */
    .af-side { position:sticky; top:14px; display:flex; flex-direction:column; gap:12px; max-height:calc(100vh - 84px); }
    .af-side .af-rcpt { flex:0 1 auto; min-height:150px; display:flex; flex-direction:column; overflow:hidden; }
    .af-side .af-pay { flex:0 3 auto; min-height:120px; overflow-y:auto; }
    .af-side .af-bar { flex:none; }
    .af-side .af-sec { margin-bottom:0; }
    .af-rcpt { display:block; background:#fff; border:1px solid #E2E8F0; border-radius:18px; padding:16px 18px; box-shadow:0 4px 14px -6px rgba(15,82,186,.10); }
    .af-rcpt-h { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px; font-size:15px; font-weight:800; color:#0F172A; }
    .af-rcpt-h b { font-family:var(--font-mono); font-size:14px; font-weight:600; letter-spacing:.06em; color:#475569; }
    #rcptLines { flex:1 1 auto; min-height:60px; overflow-y:auto; }
    .rcpt-line { display:flex; gap:10px; align-items:baseline; padding:9px 0; border-bottom:1px dashed #E2E8F0; }
    .rcpt-line:last-child { border-bottom:0; }
    .rcpt-line div { flex:1; min-width:0; display:flex; flex-direction:column; }
    .rcpt-line div b { font-size:14px; font-weight:700; overflow-wrap:anywhere; }
    .rcpt-line div span { font-size:12px; color:var(--hint); }
    .rcpt-line > em { font-style:normal; font-family:var(--font-mono); font-size:15px; font-weight:600; white-space:nowrap; }
    .rcpt-empty { font-size:13px; color:var(--hint); padding:14px 0; line-height:1.45; }
    .af-bar { position:static; flex-direction:column; align-items:stretch; padding:16px 18px; gap:12px; margin-top:0; box-shadow:0 4px 14px -6px rgba(15,82,186,.10); }
    .af-bar-total { display:flex; justify-content:space-between; align-items:baseline; }
    .af-bar-total b { font-size:30px; }
    .af-save { padding:16px 20px; font-size:17px; display:flex; align-items:center; justify-content:center; gap:10px; }
    .af-kbd { display:inline; font-family:var(--font-mono); font-size:11px; font-weight:600; background:rgba(255,255,255,.22); border-radius:6px; padding:2px 7px; }
    .pay-seg { grid-template-columns:repeat(2, minmax(0,1fr)); }
    .add-form .row2 .field { min-width:0; }
  }
  /* Компьютер: товары сразу под машиной (их выбирают всегда), пробег ниже
     и в одну строку; имя и телефон рядом. На телефоне порядок прежний */
  @media (min-width: 1200px) {
    .af-main { display:flex; flex-direction:column; }
    .af-main > .af-sec { order:1; }
    .af-main > .af-sec.af-items { order:2; }
    .af-main > .af-sec.af-mil { order:3; }
    .af-owner { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); column-gap:12px; }
    .af-owner > * { grid-column:1 / -1; }
    .af-owner > .field:nth-child(1), .af-owner > .field:nth-child(2) { grid-column:auto; }
  }
  .known-client .kc-lv-item {
    display:flex; justify-content:space-between; gap:8px; font-size:12.5px; color:var(--text);
    padding:3px 0;
  }
  .known-client .kc-lv-item span:last-child { color:var(--hint); flex:none; }
  .known-client .kc-action-btn {
    width:100%; padding:13px; border:none; border-radius:12px; background:linear-gradient(135deg, #1D4ED8 0%, #1E40AF 55%, #312E81 100%);
    color:#fff; font-size:15px; font-weight:700; font-family:var(--font-body); cursor:pointer;
    display:flex; align-items:center; justify-content:center; gap:8px; box-shadow:0 6px 14px rgba(29,78,216,.28);
  }
  .known-client .kc-action-hint { font-size:11.5px; color:var(--hint); text-align:center; margin-top:8px; }
  .car-card {
    background:var(--card); border:1.5px solid var(--border); border-radius:14px; padding:14px;
    margin-bottom:10px; cursor:pointer; transition:border-color .12s, box-shadow .12s;
  }
  .car-card:active { border-color:var(--blue); box-shadow:0 2px 10px rgba(15,82,186,.1); }
  /* «База»: кому пора на замену и обзвон */
  .bd-card { background:var(--card); border:1.5px solid var(--border); border-radius:16px; padding:14px; margin-bottom:14px; }
  .bd-head { display:flex; justify-content:space-between; align-items:baseline; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
  .bd-head b { font-size:15px; } .bd-head span { font-size:12.5px; color:var(--hint); }
  .bd-tabs { display:flex; gap:6px; overflow-x:auto; padding-bottom:4px; margin-bottom:6px; }
  .bd-tabs button { flex:none; display:flex; align-items:center; gap:6px; border:1.5px solid var(--border); background:transparent; color:var(--text); border-radius:999px; padding:7px 12px; font:inherit; font-size:13px; font-weight:600; cursor:pointer; }
  .bd-tabs button em { font-style:normal; font-family:var(--font-mono); font-size:12px; background:var(--field-bg); border-radius:999px; padding:1px 7px; }
  .bd-tabs button.on { border-color:var(--blue); color:var(--blue); }
  .bd-tabs button.warn em { color:#B3241C; }
  .bd-row { border-top:1px dashed var(--border); padding:12px 0; display:grid; gap:8px; }
  .bd-main { cursor:pointer; min-width:0; }
  .bd-top { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  .bd-late { font-size:11.5px; font-weight:700; color:#B3241C; }
  .bd-st { font-size:11.5px; font-weight:700; border-radius:999px; padding:2px 8px; background:var(--field-bg); color:var(--hint); }
  .bd-st.st-booked, .bd-st.st-called { color:#047857; } .bd-st.st-refused { color:#B3241C; } .bd-st.st-bot { color:var(--blue); }
  .bd-name { font-size:14.5px; font-weight:700; margin-top:5px; overflow-wrap:anywhere; }
  .bd-due { font-size:13px; color:var(--blue); font-weight:600; margin-top:3px; }
  .bd-last { font-size:12px; color:var(--hint); margin-top:2px; }
  .bd-act { display:flex; flex-wrap:wrap; gap:6px; }
  .bd-b { display:inline-flex; align-items:center; gap:6px; border:1.5px solid var(--border); background:transparent; color:var(--text); border-radius:10px; padding:8px 11px; font:inherit; font-size:13px; font-weight:600; text-decoration:none; cursor:pointer; }
  .bd-b.call { border-color:#16A34A; color:#16A34A; } .bd-b.wa { color:#16A34A; } .bd-b.tg { color:#0EA5E9; } .bd-b.bot { color:var(--blue); }
  .bd-nophone { font-size:12.5px; color:var(--hint); }
  .bd-res { display:flex; flex-wrap:wrap; gap:6px; }
  .bd-r { display:inline-flex; align-items:center; gap:5px; border:1px dashed var(--border); background:transparent; color:var(--hint); border-radius:999px; padding:5px 10px; font:inherit; font-size:12px; cursor:pointer; }
  .bd-r.on { border-style:solid; border-color:var(--blue); color:var(--blue); font-weight:700; }
  .bd-book label { display:block; font-size:12.5px; color:var(--hint); margin-bottom:6px; }
  .bd-book-row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  .bd-book-row input { width:auto; flex:1 1 140px; }
  @media (min-width: 900px) { .bd-row { grid-template-columns:minmax(0,1.3fr) auto; align-items:center; } .bd-res, .bd-book { grid-column:1 / -1; } }
  .car-card .cc-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:9px; gap:8px; }
  .car-card .cc-plate {
    font-family:var(--font-mono); font-weight:700; font-size:14.5px; letter-spacing:0.5px; color:var(--blue);
    background:var(--field-bg); padding:3px 9px; border-radius:7px; flex:none;
  }
  .car-card .cc-linkbtn { flex:none; }
  .car-card .cc-owner { font-size:15px; font-weight:700; color:var(--text); }
  .car-card .cc-meta { font-size:12.5px; color:var(--hint); margin-top:2px; }
  .car-card .cc-bottom {
    display:flex; justify-content:space-between; align-items:center; margin-top:10px;
    padding-top:10px; border-top:1px dashed var(--border);
  }
  .car-card .cc-cost { font-size:15px; font-weight:700; color:var(--blue); }
  .car-card .cc-cost-date { font-size:11px; color:var(--hint); font-weight:400; }
  .car-card .cc-next { font-size:11.5px; color:var(--hint); text-align:right; }
  .car-card .cc-chevron { color:var(--hint); font-size:13px; flex:none; }
  .debt-card { background:var(--card); border:1.5px solid var(--border); border-radius:14px; padding:14px; margin-bottom:10px; }
  .debt-card.overdue { border-color:#F87171; background:linear-gradient(135deg, #FFFFFF, #FEF2F2); }
  .debt-card .dc-top { display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }
  .debt-card .dc-owner { font-size:15px; font-weight:700; color:var(--text); }
  .debt-card .dc-meta { font-size:12.5px; color:var(--hint); margin-top:2px; }
  .debt-card .dc-remaining { font-size:18px; font-weight:700; color:var(--btn); font-family:var(--font-mono); text-align:right; }
  .debt-card .dc-due { font-size:11.5px; color:var(--hint); margin-top:2px; text-align:right; }
  .debt-card .dc-due.overdue-text { color:#B3241C; font-weight:700; }
  .debt-card .dc-pay-row { display:flex; gap:6px; margin-top:10px; padding-top:10px; border-top:1px dashed var(--border); }
  .brand-chips { display:flex; gap:6px; overflow-x:auto; padding-bottom:4px; margin-bottom:12px; scrollbar-width:none; }
  .brand-chips::-webkit-scrollbar { display:none; }
  .brand-chip { flex:0 0 auto; border:1px solid var(--border); background:#fff; color:var(--text); border-radius:999px; padding:7px 12px; font-size:12.5px; font-weight:600; cursor:pointer; white-space:nowrap; }
  .brand-chip.active { background:var(--blue); border-color:var(--blue); color:#fff; }
  .brand-chip .bc-sub { font-weight:500; opacity:0.7; margin-left:4px; }
  .brand-period { display:inline-flex; background:#F1F5F9; border-radius:10px; padding:3px; margin-bottom:12px; }
  .brand-period button { border:none; background:transparent; padding:6px 12px; font-size:12.5px; font-weight:600; color:#64748B; border-radius:8px; cursor:pointer; }
  .brand-period button.active { background:#fff; color:var(--text); box-shadow:0 1px 2px rgba(15,23,42,0.12); }
  .brand-summary { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-bottom:14px; }
  .brand-summary div { background:#F8FAFC; border-radius:10px; padding:10px 8px; text-align:center; }
  .brand-summary b { display:block; font-size:16px; font-family:var(--font-display); color:var(--text); }
  .brand-summary span { font-size:11px; color:#64748B; }
  .brand-donut-wrap { position:relative; max-width:240px; margin:0 auto 16px; }
  .brand-row { padding:9px 0; border-bottom:1px solid #F1F5F9; }
  .brand-row:last-child { border-bottom:none; }
  .brand-row-top { display:flex; align-items:center; gap:8px; font-size:13.5px; }
  .brand-rank { width:22px; height:22px; border-radius:50%; color:#fff; font-size:11px; font-weight:700; display:flex; align-items:center; justify-content:center; flex:0 0 auto; }
  .brand-name { flex:1; font-weight:600; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .brand-val { font-weight:700; color:var(--text); white-space:nowrap; }
  .brand-share { font-size:12px; color:#64748B; width:46px; text-align:right; }
  .brand-bar { height:6px; background:#F1F5F9; border-radius:3px; margin:6px 0 4px 30px; overflow:hidden; }
  .brand-bar i { display:block; height:100%; border-radius:3px; }
  .brand-meta { font-size:11.5px; color:#94A3B8; margin-left:30px; }
  .st-today { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px 16px; background:#fff; border:1px solid var(--border); border-radius:16px; padding:14px 18px; margin-bottom:12px; }
  .st-today-main { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
  .st-today-label { font-size:13px; font-weight:600; color:#64748B; }
  .st-today-amount { font-size:24px; font-weight:800; font-family:var(--font-display); color:var(--text); }
  .st-today-amount small, .st-amount small { font-size:0.55em; font-weight:600; color:#64748B; margin-left:3px; }
  .st-today-chips { display:flex; gap:6px; flex-wrap:wrap; }
  .st-chip { background:#F1F5F9; border-radius:999px; padding:5px 11px; font-size:12.5px; color:#334155; }
  .st-day-btn { border:1.5px solid #0F52BA; background:#EFF6FF; color:#0F52BA; border-radius:999px; padding:6px 14px; font-size:13px; font-weight:700; cursor:pointer; white-space:nowrap; }
  .st-day-btn:hover { background:#0F52BA; color:#fff; }
  #dayDetailsModal .modal { max-width:640px; }
  .dd-date { display:flex; justify-content:center; gap:8px; align-items:center; margin:-4px 0 12px; }
  .dd-date input { width:auto; padding:6px 10px; font-size:13px; }
  .dd-tot { display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:8px; margin-bottom:14px; }
  .dd-tot div { background:#F8FAFC; border:1px solid var(--border); border-radius:12px; padding:9px 11px; }
  .dd-tot span { display:block; font-size:11.5px; color:#64748B; }
  .dd-tot b { font-size:16px; font-family:var(--font-mono); }
  .dd-sec { font-size:14px; font-weight:700; margin:16px 0 8px; display:flex; justify-content:space-between; gap:8px; }
  .dd-sec small { font-weight:600; color:#64748B; }
  .dd-item { border:1px solid var(--border); border-radius:12px; padding:10px 12px; margin-bottom:8px; font-size:13px; }
  .dd-item-h { display:flex; justify-content:space-between; gap:8px; align-items:baseline; }
  .dd-plate { font-family:var(--font-mono); font-weight:800; font-size:14px; }
  .dd-sub { color:#64748B; font-size:12px; margin-top:2px; }
  .dd-lines { margin:6px 0 0; padding:0; list-style:none; }
  .dd-lines li { display:flex; justify-content:space-between; gap:8px; padding:2px 0; border-bottom:1px dashed var(--border); }
  .dd-pay { display:flex; flex-wrap:wrap; gap:5px; margin-top:7px; }
  .dd-pay span { border-radius:999px; padding:3px 9px; font-size:11.5px; background:#F1F5F9; }
  .dd-pay .debt { background:#FEF3C7; color:#92400E; font-weight:700; }
  .dd-row { display:flex; justify-content:space-between; gap:8px; padding:7px 0; border-bottom:1px dashed var(--border); font-size:13px; }
  .dd-empty { color:#94A3B8; font-size:13px; padding:4px 0 2px; }
  .st-chip b { color:var(--text); }
  .st-empty { font-size:13px; color:#94A3B8; }
  .st-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:12px; }
  .st-card { background:#fff; border:1px solid var(--border); border-radius:16px; padding:16px 16px 12px; display:flex; flex-direction:column; }
  .st-card.orange { background:#FFFBF5; border-color:#FDBA74; }
  .st-label { font-size:13px; font-weight:600; color:#64748B; }
  .st-amount { font-size:26px; font-weight:800; font-family:var(--font-display); color:var(--blue); line-height:1.15; margin:4px 0 6px; }
  .st-card.orange .st-amount { color:#9A3412; }
  .st-badge { display:inline-flex; align-items:center; gap:4px; border-radius:999px; padding:3px 9px; font-size:12px; font-weight:700; }
  .st-badge.up { background:#DCFCE7; color:#15803D; }
  .st-badge.down { background:#FEE2E2; color:#B91C1C; }
  .st-badge-note { font-size:11.5px; color:#94A3B8; margin-left:6px; }
  .st-badge-line { min-height:24px; margin-bottom:8px; }
  .st-row { display:flex; justify-content:space-between; align-items:center; gap:8px; padding:8px 0; border-top:1px solid #F1F5F9; font-size:13px; color:#64748B; }
  .st-row b { color:var(--text); font-weight:700; white-space:nowrap; }
  .st-row .st-badge { padding:1px 7px; font-size:11px; margin-left:6px; }
  .st-block { padding:8px 0; border-top:1px solid #F1F5F9; font-size:13px; color:#64748B; }
  .st-block-head { display:flex; justify-content:space-between; margin-bottom:6px; }
  .st-block-head b { color:var(--text); }
  .st-split { display:flex; height:7px; border-radius:4px; overflow:hidden; background:#F1F5F9; }
  .st-split i { display:block; height:100%; }
  .st-legend { display:flex; justify-content:space-between; gap:8px; font-size:11.5px; margin-top:5px; }
  .st-legend span::before { content:''; display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:5px; background:var(--dot); }
  .st-row.profit b { color:#15803D; }
  .st-money { display:grid; grid-template-columns:repeat(auto-fit, minmax(128px, 1fr)); gap:8px; margin:6px 0 6px; }
  .st-money > div { background:#F8FAFC; border-radius:12px; padding:8px 10px; min-width:0; }
  .st-money-k { font-size:11.5px; font-weight:600; color:#64748B; }
  .st-money-v { font-size:20px; font-weight:800; font-family:var(--font-display); line-height:1.2; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .st-money-v small { font-size:.55em; font-weight:600; color:#64748B; margin-left:3px; }
  .st-money-v.rev { color:var(--blue); }
  .st-money-v.got { color:#15803D; }
  .st-card.orange .st-money > div { background:#FFF7ED; }
  .st-card.orange .st-money-v.rev { color:#9A3412; }
  .st-money-note { font-size:12px; color:#92400E; background:#FEF3C7; border-radius:10px; padding:6px 9px; margin-bottom:6px; line-height:1.35; }
  .dsum { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-bottom:10px; }
  .dsum > div { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:9px 10px; min-width:0; }
  .dsum .k { font-size:11px; color:var(--hint); font-weight:600; }
  .dsum .v { font-size:16px; font-weight:800; font-family:var(--font-display); font-variant-numeric:tabular-nums; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .dsum .v.bad { color:#B3241C; } .dsum .v.ok { color:#15803D; }
  .dtabs { display:flex; gap:6px; margin-bottom:10px; }
  .rate-now { display:flex; align-items:baseline; gap:8px; font-family:var(--font-mono); color:var(--hint); }
  .rate-now b { font-size:30px; color:var(--text); font-weight:700; }
  .rate-h { display:flex; justify-content:space-between; gap:10px; padding:8px 0; border-top:1px solid var(--border); font-size:13px; }
  .rate-h b { font-family:var(--font-mono); }
  .rate-h .up { color:#B3241C; } .rate-h .down { color:#15803D; }
  .rate-shop { font-size:12px; font-weight:700; color:var(--hint); text-transform:uppercase; letter-spacing:.04em; margin:12px 0 4px; }
  .rate-row { display:flex; align-items:center; gap:10px; padding:9px 0; border-top:1px solid var(--border); font-size:13.5px; cursor:pointer; }
  .rate-row input[type=checkbox] { width:20px; height:20px; flex:0 0 auto; accent-color:#0F52BA; }
  .rate-row .rr-main { flex:1; min-width:0; }
  .rate-row .rr-main b { display:block; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .rate-row .rr-main span { color:var(--hint); font-size:12px; }
  .rate-row .rr-price { text-align:right; font-family:var(--font-mono); font-size:12.5px; white-space:nowrap; }
  .rate-row .rr-price input { width:92px; padding:6px 8px; font-size:13px; text-align:right; }
  .rate-how { font-size:13px; line-height:1.6; color:var(--text); }
  .rate-how p { margin:0 0 8px; }
  .rate-banner { padding:10px 12px; background:#FFFBEB; border:1px solid #FCD34D; border-radius:12px; font-size:12.5px; color:#92400E; margin-bottom:12px; }
  .rate-banner.ok { background:#F0FDF4; border-color:#86EFAC; color:#166534; }
  .cur-switch { display:flex; gap:6px; margin:0 0 8px; }
  .cur-switch button { font:inherit; font-size:12.5px; font-weight:600; padding:6px 12px; border-radius:999px; border:1px solid var(--border); background:var(--card); color:var(--hint); cursor:pointer; }
  .cur-switch button.on { background:#0F52BA; border-color:#0F52BA; color:#fff; }
  .usd-tag { display:inline-block; font-size:10.5px; font-weight:700; padding:1px 6px; border-radius:6px; background:#DBEAFE; color:#1E40AF; margin-left:4px; vertical-align:1px; }
  .dtabs button { font:inherit; font-size:13px; font-weight:600; padding:7px 14px; border-radius:999px; border:1px solid var(--border); background:var(--card); color:var(--hint); cursor:pointer; }
  .dtabs button.on { background:var(--text); border-color:var(--text); color:#fff; }
  .debt-card .dc-prog { margin-top:10px; }
  .debt-card .dc-prog .bar { height:6px; background:#F1F5F9; border-radius:4px; overflow:hidden; }
  .debt-card .dc-prog .bar i { display:block; height:100%; background:#0EA5E9; }
  .debt-card .dc-prog .t { display:flex; justify-content:space-between; gap:8px; font-size:11.5px; color:var(--hint); margin-top:4px; font-variant-numeric:tabular-nums; }
  .debt-card .dc-actions { display:flex; gap:6px; margin-top:8px; }
  .debt-card .dc-actions button { flex:1; font:inherit; font-size:12.5px; font-weight:600; padding:7px 8px; border-radius:10px; border:0; background:#F1F5F9; color:var(--text); cursor:pointer; }
  .debt-card .dc-actions button.danger { background:#FEF2F2; color:#B3241C; }
  .debt-card .dc-hist { margin-top:8px; padding-top:6px; border-top:1px dashed var(--border); }
  .debt-card .dh-row { display:flex; align-items:center; gap:8px; font-size:12.5px; padding:5px 0; }
  .debt-card .dh-row .dh-date { color:var(--hint); flex:1; }
  .debt-card .dh-row b { font-variant-numeric:tabular-nums; }
  .debt-card .dh-row.cancelled b, .debt-card .dh-row.cancelled .dh-date { text-decoration:line-through; color:var(--hint); }
  .debt-card .dh-row .dh-x { font:inherit; font-size:11.5px; font-weight:700; color:#B3241C; background:#FEF2F2; border:0; border-radius:7px; padding:3px 8px; cursor:pointer; }
  .debt-card .dh-tag { font-size:11px; color:var(--hint); }
  .debt-card.closed { background:#FAFBFC; }
  .debt-card .dc-status { font-size:12px; font-weight:600; margin-top:6px; }
  .debt-card .dc-status.ok { color:#15803D; } .debt-card .dc-status.wo { color:#B3241C; }
  .wo-reasons { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 10px; }
  .wo-reasons button { font:inherit; font-size:12.5px; padding:6px 11px; border-radius:999px; border:1px solid var(--border); background:var(--card); color:var(--text); cursor:pointer; margin:0; }
  .wo-reasons button.on { border-color:#B3241C; background:#FEF2F2; color:#B3241C; font-weight:700; }
  .wo-warn { background:#FEF3C7; color:#92400E; border-radius:10px; padding:8px 10px; font-size:12.5px; line-height:1.4; margin-bottom:10px; }
  .wo-btns { display:flex; gap:8px; }
  .wo-btns button { flex:1; }
  .wo-btns .wo-go { background:#B3241C; color:#fff; border:0; border-radius:12px; padding:12px; font:inherit; font-weight:700; cursor:pointer; }
  .rv-summary { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:8px; margin-bottom:14px; }
  .rv-box { background:#F8FAFC; border-radius:12px; padding:10px 12px; }
  .rv-box b { display:block; font-size:17px; font-family:var(--font-display); color:var(--text); line-height:1.2; }
  .rv-box span { font-size:11.5px; color:#64748B; }
  .rv-box.best { background:#FEF2F2; }
  .rv-box.best b { color:#C81E2B; }
  .rv-chart-wrap { position:relative; height:240px; }
  .rv-legend { display:flex; gap:14px; flex-wrap:wrap; font-size:11.5px; color:#64748B; margin-top:8px; }
  .rv-legend i { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:5px; vertical-align:-1px; }
  .net-cmp { width:100%; border-collapse:collapse; font-size:13px; min-width:640px; }
  .net-cmp th { text-align:right; font-size:11.5px; font-weight:600; color:#64748B; padding:8px 6px; border-bottom:1px solid var(--border); white-space:normal; line-height:1.25; vertical-align:bottom; background:none; text-transform:none; letter-spacing:0; }
  .net-cmp th:first-child, .net-cmp td:first-child { text-align:left; position:sticky; left:0; background:#fff; z-index:1; }
  .net-cmp tbody tr:hover td:first-child { background:#F8FAFC; }
  .net-cmp tbody tr.active td:first-child { background:#EFF6FF; }
  .net-cmp tfoot td:first-child { background:#F8FAFC; }
  .net-cmp td { text-align:right; padding:10px 6px; border-bottom:1px solid #F1F5F9; white-space:nowrap; color:var(--text); }
  .net-cmp tbody tr { cursor:pointer; }
  .net-cmp tbody tr:hover { background:#F8FAFC; }
  .net-cmp tbody tr.active { background:#EFF6FF; }
  .net-cmp .shop-cell { display:flex; align-items:center; gap:8px; font-weight:700; }
  .net-cmp .shop-cell small { font-weight:500; color:#94A3B8; }
  .net-cmp .best { color:#15803D; font-weight:800; }
  .net-cmp .neg { color:#B91C1C; font-weight:700; }
  .net-cmp tfoot td { font-weight:800; border-top:2px solid var(--border); border-bottom:none; background:#F8FAFC; }
  .net-cmp-chart-wrap { position:relative; margin-top:16px; }
  .net-detail-head { margin:22px 0 10px; }
  .net-detail-title { font-size:16px; font-weight:700; color:var(--text); margin-bottom:8px; }
  .modal-overlay { z-index:70 !important; }
  .modal-wide { max-height:88vh; }
  .wh-kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:8px; }
  .wh-kpi { background:#F8FAFC; border-radius:12px; padding:10px 12px; }
  .wh-kpi b { display:block; font-size:18px; font-family:var(--font-display); color:var(--text); line-height:1.2; }
  .wh-kpi span { font-size:11.5px; color:#64748B; }
  .wh-kpi .wh-kpi-usd { display:block; margin-top:3px; font-style:normal; font-size:13px; font-weight:600; font-family:var(--font-display); color:#475569; }
  .wh-kpi.good .wh-kpi-usd { color:#15803D; }
  .wh-kpi.bad .wh-kpi-usd { color:#B91C1C; }
  .wh-kpi.good b { color:#15803D; }
  .wh-kpi.bad { background:#FEF2F2; }
  .wh-kpi.bad b { color:#B91C1C; }
  .wh-kpi.muted { background:#F1F5F9; }
  .wh-att-title { font-size:12px; font-weight:700; color:#64748B; margin:14px 0 4px; }
  .wh-att { display:flex; align-items:center; gap:10px; padding:9px 0; border-bottom:1px solid #F1F5F9; font-size:13px; }
  .wh-att:last-child { border-bottom:none; }
  .wh-att i.fa-solid { width:18px; text-align:center; }
  .wh-att .wa-main { flex:1; min-width:0; }
  .wh-att .wa-main b { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text); }
  .wh-att .wa-main span { font-size:11.5px; color:#64748B; }
  .wh-toolbar { display:flex; gap:8px; margin-bottom:10px; }
  .wh-search { flex:1; display:flex; align-items:center; gap:8px; background:var(--field-bg); border:1px solid var(--border); border-radius:12px; padding:0 12px; }
  .wh-search i { color:#94A3B8; }
  .wh-search input { border:none !important; background:transparent !important; padding:10px 0 !important; margin:0 !important; box-shadow:none !important; outline:none; width:100%; font-size:14px; }
  .wh-tbtn { border:1px solid var(--border); background:#fff; color:var(--text); border-radius:12px; padding:9px 12px; font-size:13px; font-weight:700; cursor:pointer; white-space:nowrap; font-family:inherit; }
  .wh-tbtn-primary { background:var(--blue); border-color:var(--blue); color:#fff; }
  .wh-tbtn-wide { width:100%; margin-top:10px; }
  .wh-tbtn-sm { padding:6px 10px; font-size:12px; border-radius:10px; }
  .wh-tbtn-icon { padding:6px 9px; font-size:12px; border-radius:10px; color:#64748B; }
  .whc { border:1px solid var(--border); border-radius:14px; padding:12px; margin-top:8px; background:#fff; }
  .whc.st-out { border-color:#FCA5A5; background:#FFFBFB; }
  .whc.st-low { border-color:#FCD34D; }
  .whc-top { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
  .whc-name { min-width:0; }
  .whc-name b { display:block; font-size:14.5px; color:var(--text); overflow:hidden; text-overflow:ellipsis; }
  .whc-name span { font-size:11.5px; color:#94A3B8; }
  .whc-qty { font-family:var(--font-display); font-weight:800; font-size:18px; color:var(--text); white-space:nowrap; }
  .whc.st-out .whc-qty { color:#B91C1C; }
  .whc.st-low .whc-qty { color:#B45309; }
  .whc-bar { height:6px; border-radius:3px; background:#F1F5F9; margin:8px 0 6px; overflow:hidden; }
  .whc-bar i { display:block; height:100%; border-radius:3px; }
  .whc-info { font-size:12px; color:#64748B; }
  .whc-info .warn { color:#B91C1C; font-weight:700; }
  .whc-info .amber { color:#B45309; font-weight:700; }
  .whc-store { font-size:12px; color:#0F52BA; margin-top:4px; }
  .whc-store i { font-size:11px; margin-right:2px; }
  .whc-store a { color:#0F52BA; font-weight:700; text-decoration:none; }
  .sm-rows { max-height:52vh; overflow-y:auto; margin-bottom:12px; }
  .sm-row { display:flex; align-items:center; gap:10px; padding:9px 6px; border-bottom:1px solid #EEF2F7; border-radius:8px; }
  .sm-row.on { background:#EFF6FF; }
  .sm-row input[type=checkbox] { width:20px; height:20px; flex:none; accent-color:#0F52BA; }
  .sm-name { flex:1; min-width:0; display:flex; flex-direction:column; cursor:pointer; text-transform:none; letter-spacing:0; }
  .sm-name b { font-size:14px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sm-name span { font-size:12px; color:#64748B; }
  .sm-qty { width:76px !important; flex:none; text-align:center; padding:8px 6px !important; }
  .whc-bottom { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-top:8px; flex-wrap:wrap; }
  .whc-price { font-size:12px; color:#475569; }
  .whc-price .mg { color:#15803D; font-weight:700; }
  .whc-actions { display:flex; gap:6px; margin-left:auto; }
  .ord-head-row { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:6px; }
  .sup-row, .ord-row { display:flex; align-items:center; gap:10px; padding:10px 0; border-bottom:1px solid #F1F5F9; }
  .sup-row:last-child, .ord-row:last-child { border-bottom:none; }
  .ord-row { cursor:pointer; }
  .sup-main { flex:1; min-width:0; cursor:pointer; }
  .sup-main b { display:block; font-size:14px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sup-main span { display:block; font-size:12px; color:#64748B; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ord-badge { font-size:11px; font-weight:700; padding:3px 9px; border-radius:999px; white-space:nowrap; }
  .ord-title { display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .ord-title b { font-size:17px; }
  .ord-sub { font-size:12px; color:#64748B; margin-top:2px; }
  .ord-steps { display:flex; gap:4px; margin:10px 0 12px; }
  .ord-step { flex:1; text-align:center; font-size:11px; padding:5px 2px; border-radius:8px; background:#F1F5F9; color:#64748B; font-weight:600; }
  .ord-step.on { background:#DBEAFE; color:#0F52BA; }
  .ord-line { display:flex; align-items:center; gap:8px; padding:9px 0; border-bottom:1px solid #F1F5F9; font-size:13px; }
  .ord-line .pl-name, .ord-recv .pl-name, .ord-dist .pl-name { flex:1; min-width:0; }
  .ord-line .pl-name b, .ord-recv .pl-name b, .ord-dist .pl-name b { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ord-line .pl-name span, .ord-recv .pl-name span, .ord-dist .pl-name span { font-size:11px; color:#64748B; }
  .ord-line input[type=number] { width:74px !important; padding:6px 8px !important; margin:0 !important; font-size:14px; }
  .ord-unit { font-size:12px; color:#64748B; min-width:18px; }
  .ord-x { border:none; background:none; color:#94A3B8; font-size:15px; cursor:pointer; padding:4px; }
  .ord-total { display:flex; justify-content:space-between; gap:8px; font-size:13px; color:#475569; margin:12px 0; font-weight:600; }
  .ord-text { white-space:pre-wrap; background:#F8FAFC; border:1px solid var(--border); border-radius:12px; padding:12px; font-size:13px; font-family:inherit; margin:8px 0 12px; }
  .ord-recv, .ord-dist { padding:10px 0; border-bottom:1px solid #F1F5F9; }
  .ord-recv-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:6px; }
  .ord-recv-grid label { font-size:11px; color:#64748B; display:block; }
  .ord-recv-grid input { width:100% !important; margin:2px 0 0 !important; padding:7px 9px !important; }
  .ord-dist-row { display:flex; align-items:center; justify-content:space-between; gap:8px; font-size:13px; margin-top:6px; }
  .ord-dist-row input { width:84px !important; margin:0 !important; padding:6px 8px !important; }
  .ord-keep { font-size:12px; color:#15803D; margin-top:6px; font-weight:600; }
  .ord-keep.bad { color:#B91C1C; }
  .pl-group { font-size:12px; font-weight:700; color:#0F52BA; margin:12px 0 2px; }
  #orderModal select { width:100%; }
  .sup-tg { border:1px solid var(--border); border-radius:12px; padding:12px; margin:4px 0 12px; background:#F8FAFC; font-size:13px; }
  .sup-tg b { display:block; margin-bottom:4px; }
  .sup-tg .ok { color:#15803D; font-weight:700; }
  .sup-tg .no { color:#B45309; font-weight:700; }
  .sup-tg .wh-tbtn { margin:8px 6px 0 0; }
  .sup-bot { color:#15803D; font-weight:700; }
  .sc-actions { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0 4px; }
  .sd-box { border:1px solid var(--border); border-radius:14px; padding:12px; margin-top:10px; background:#F8FAFC; }
  .sd-head { font-size:12px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:.03em; margin-bottom:6px; }
  .sd-big { font-size:24px; font-weight:800; }
  .sd-big.bad { color:#B91C1C; }
  .sd-big.ok { color:#15803D; }
  .sd-cap { font-size:12px; color:#64748B; margin-bottom:6px; }
  .sd-note { font-size:13px; font-weight:600; margin:4px 0; color:#334155; }
  .sd-note.bad { color:#B91C1C; }
  .sd-note.warn { color:#B45309; }
  .pr-row { border-bottom:1px solid #F1F5F9; cursor:pointer; }
  .pr-badge { font-size:11px; font-weight:700; padding:2px 7px; border-radius:999px; white-space:nowrap; }
  .pr-badge.up { color:#B91C1C; background:#FEE2E2; }
  .pr-badge.down { color:#15803D; background:#DCFCE7; }
  .pr-hist { display:none; padding:0 0 8px; }
  .pr-row.open .pr-hist { display:block; }
  .pr-h { display:flex; justify-content:space-between; gap:8px; font-size:12px; color:#475569; padding:3px 0; }
  .sup-debt { font-weight:700; color:#B91C1C; }
  /* раздел «Поставщики» — вариант «Банк»: синий итог + список */
  .sp-top { display:flex; align-items:center; gap:8px; margin:2px 0 12px; }
  .sp-top h2 { flex:1; margin:0; font-family:var(--font-display); font-size:22px; font-weight:800; color:var(--darkblue); letter-spacing:-.01em; }
  .sp-pill { border:1px solid #BFDBFE; background:#EFF6FF; color:#0F52BA; border-radius:999px; padding:7px 12px; font:inherit; font-size:13px; font-weight:700; cursor:pointer; white-space:nowrap; }
  .sp-pill.warn { background:#FEF3C7; border-color:#FDE68A; color:#92400E; }
  .sp-icon { width:38px; height:38px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#334155; font-size:16px; cursor:pointer; display:flex; align-items:center; justify-content:center; }
  .sp-menu-wrap { position:relative; }
  .sp-menu { display:none; position:absolute; right:0; top:44px; z-index:30; background:#fff; border:1px solid var(--border); border-radius:14px; box-shadow:0 12px 30px rgba(15,23,42,.14); min-width:220px; padding:6px; }
  .sp-menu.open { display:block; }
  .sp-menu button { display:flex; align-items:center; gap:10px; width:100%; border:none; background:none; font:inherit; font-size:14px; font-weight:600; color:var(--text); padding:11px 12px; border-radius:10px; cursor:pointer; text-align:left; }
  .sp-menu button:hover { background:#F1F5F9; }
  .sp-menu button i { width:18px; color:#64748B; }
  .sp-hero { background:linear-gradient(135deg, #0A2540 0%, #0F52BA 100%); color:#fff; border-radius:20px; padding:18px 18px 16px; margin-bottom:14px; }
  .sp-hero .l { font-size:13px; color:#BFDBFE; font-weight:600; }
  .sp-hero .x { font-family:var(--font-display); font-size:32px; font-weight:800; line-height:1.15; margin:4px 0 2px; letter-spacing:-.01em; }
  .sp-hero .x small { font-size:16px; font-weight:700; color:#BFDBFE; margin-left:4px; }
  .sp-hero .u { font-size:13px; color:#BFDBFE; }
  .sp-bar { display:flex; height:8px; border-radius:4px; overflow:hidden; background:rgba(255,255,255,.22); margin-top:14px; }
  .sp-bar i { display:block; height:100%; }
  .sp-bar .o { background:#FCA5A5; } .sp-bar .k { background:#93C5FD; }
  .sp-leg { display:flex; flex-wrap:wrap; gap:4px 14px; font-size:12px; color:#DBEAFE; margin-top:8px; }
  .sp-leg span::before { content:""; display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; vertical-align:0; }
  .sp-leg .o::before { background:#FCA5A5; } .sp-leg .k::before { background:#93C5FD; }
  .sp-hero.zero { background:linear-gradient(135deg, #065F46 0%, #059669 100%); }
  .sp-list { background:#fff; border:1px solid var(--border); border-radius:18px; padding:4px 14px; }
  .sp-row { display:flex; align-items:center; gap:12px; padding:12px 0; border-bottom:1px solid #F1F5F9; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .sp-row:last-child { border-bottom:none; }
  .sp-av { width:42px; height:42px; border-radius:13px; flex:none; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:14px; font-family:var(--font-display); }
  .sp-av.r { background:#FEE2E2; color:#B91C1C; } .sp-av.a { background:#FEF3C7; color:#92400E; }
  .sp-av.b { background:#DBEAFE; color:#1D4ED8; } .sp-av.g { background:#DCFCE7; color:#15803D; }
  .sp-mid { flex:1; min-width:0; }
  .sp-nm { font-weight:700; font-size:15px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sp-chip { display:inline-block; white-space:nowrap; font-size:11.5px; font-weight:700; padding:3px 9px; border-radius:999px; margin-top:4px; }
  .sp-chip.r { background:#FEE2E2; color:#B91C1C; } .sp-chip.a { background:#FEF3C7; color:#92400E; }
  .sp-chip.b { background:#DBEAFE; color:#1D4ED8; } .sp-chip.g { background:#DCFCE7; color:#15803D; } .sp-chip.n { background:#F1F5F9; color:#475569; }
  .sp-amt { text-align:right; flex:none; }
  .sp-amt b { display:block; font-family:var(--font-display); font-size:16px; font-weight:800; color:var(--text); white-space:nowrap; }
  .sp-amt span { font-size:12px; color:#64748B; white-space:nowrap; }
  .sp-pay { flex:none; border:none; background:#0F52BA; color:#fff; font:inherit; font-size:13px; font-weight:700; padding:9px 12px; border-radius:11px; cursor:pointer; }
  .sp-amt .sp-pay { display:inline-block; margin-top:6px; font-size:12px; padding:6px 12px; border-radius:999px; }
  .sp-pay:active, .sp-row:active { transform:scale(.98); }
  .sp-empty { text-align:center; padding:22px 8px; color:#64748B; font-size:14px; }
  .sp-empty .sp-pay { margin-top:12px; padding:11px 18px; }
  .sp-sec { display:flex; align-items:center; justify-content:space-between; margin:20px 2px 8px; }
  .sp-sec b { font-size:13px; font-weight:800; color:#64748B; text-transform:uppercase; letter-spacing:.04em; }
  .sp-link { border:none; background:none; color:#0F52BA; font:inherit; font-size:13px; font-weight:700; cursor:pointer; padding:4px 0; }
  .sp-strip { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:8px; }
  .sp-strip button { border:1px solid var(--border); background:#fff; border-radius:14px; padding:10px 6px; font:inherit; font-size:12px; font-weight:600; color:#64748B; cursor:pointer; }
  .sp-strip button b { display:block; font-family:var(--font-display); font-size:20px; font-weight:800; color:var(--text); }
  .sp-strip button.on { border-color:#0F52BA; color:#0F52BA; background:#EFF6FF; }
  .sp-strip button.new { background:#0F52BA; border-color:#0F52BA; color:#DBEAFE; }
  .sp-strip button.new b { color:#fff; }
  .sp-orders { background:#fff; border:1px solid var(--border); border-radius:18px; padding:2px 14px; margin-top:10px; }
  @media (min-width:900px) { .sp-hero .x { font-size:38px; } #view-suppliers { max-width:820px; } }
  /* карточка поставщика — шторка снизу, «Оплатить» всегда под рукой */
  .sp-sheet { position:relative; text-align:left; padding:0 !important; display:flex; flex-direction:column; overflow:hidden !important; max-width:560px !important; }
  .sp-sheet-body { overflow-y:auto; padding:8px 18px 18px; -webkit-overflow-scrolling:touch; }
  .sp-grab { width:42px; height:5px; border-radius:3px; background:#CBD5E1; margin:10px auto 2px; }
  .sp-x { position:absolute; top:10px; right:12px; width:34px; height:34px; border-radius:50%; border:none; background:#F1F5F9; color:#475569; font-size:16px; cursor:pointer; z-index:2; }
  .sp-foot { display:flex; gap:8px; padding:12px 18px calc(12px + env(safe-area-inset-bottom)); border-top:1px solid var(--border); background:#fff; }
  .sp-foot:empty { display:none; }
  .sp-foot .main { flex:1; border:none; background:#0F52BA; color:#fff; font:inherit; font-size:15px; font-weight:800; padding:14px; border-radius:14px; cursor:pointer; }
  .sp-foot .sec { border:1px solid var(--border); background:#fff; color:#334155; font:inherit; font-size:13px; font-weight:700; padding:0 14px; border-radius:14px; cursor:pointer; }
  @media (max-width:899px) {
    .modal-overlay.sp-sheet-ov { align-items:flex-end; }
    .sp-sheet { width:100% !important; max-width:100% !important; max-height:92vh !important; border-radius:22px 22px 0 0 !important; border:none !important; }
  }
  @media (min-width:900px) { .sp-grab { display:none; } .sp-sheet { max-height:88vh !important; } }
  .sp-head { display:flex; align-items:center; gap:12px; padding:6px 40px 4px 0; }
  .sp-head .sp-av { width:48px; height:48px; font-size:16px; }
  .sp-head .t { font-family:var(--font-display); font-size:19px; font-weight:800; color:var(--text); line-height:1.2; }
  .sp-head .c { font-size:12.5px; color:#64748B; margin-top:2px; }
  .sp-acts { display:flex; gap:6px; overflow-x:auto; margin:12px 0 4px; padding-bottom:2px; }
  .sp-acts button { flex:none; border:1px solid var(--border); background:#fff; border-radius:999px; padding:8px 13px; font:inherit; font-size:13px; font-weight:700; color:#334155; cursor:pointer; }
  .sp-acts button i { color:#0F52BA; margin-right:5px; }
  .sp-bal { border-radius:18px; padding:16px; margin-top:10px; background:#F8FAFC; border:1px solid var(--border); }
  .sp-bal.r { background:#FEF2F2; border-color:#FECACA; } .sp-bal.g { background:#F0FDF4; border-color:#BBF7D0; } .sp-bal.b { background:#EFF6FF; border-color:#BFDBFE; }
  .sp-bal .l { font-size:12.5px; font-weight:700; color:#64748B; }
  .sp-bal .x { font-family:var(--font-display); font-size:30px; font-weight:800; line-height:1.15; margin:2px 0; }
  .sp-bal.r .x { color:#B91C1C; } .sp-bal.g .x { color:#15803D; } .sp-bal.b .x { color:#1D4ED8; }
  .sp-bal .f { font-size:12.5px; color:#475569; }
  .sp-bal .chips { margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; }
  .sp-bal .chips .sp-chip { margin-top:0; }
  .sp-det { border:1px solid var(--border); border-radius:16px; margin-top:12px; background:#fff; }
  .sp-det > summary { list-style:none; cursor:pointer; padding:14px; display:flex; align-items:center; justify-content:space-between; font-weight:800; font-size:14px; color:var(--text); }
  .sp-det > summary::-webkit-details-marker { display:none; }
  .sp-det > summary::after { content:"›"; font-size:20px; color:#94A3B8; transform:rotate(90deg); transition:transform .15s; }
  .sp-det[open] > summary::after { transform:rotate(-90deg); }
  .sp-det > summary span { font-weight:600; color:#64748B; font-size:12.5px; margin-left:auto; margin-right:10px; }
  .sp-det-in { padding:0 14px 12px; }
  .sp-form { border:2px solid #BFDBFE; background:#fff; border-radius:18px; padding:14px; margin-top:12px; }
  .sp-form-t { font-weight:800; font-size:15px; margin-bottom:2px; }
  .sp-form { scroll-margin-top:56px; }
  .sp-form-now { font-size:12.5px; color:#64748B; margin-bottom:6px; }
  #supCardBody .ord-x { color:#CBD5E1; background:none; }
  #supCardBody .ord-x:hover { color:#B91C1C; }
  .sp-seg { display:flex; gap:4px; background:#F1F5F9; border-radius:12px; padding:3px; margin:8px 0; }
  .sp-seg button { flex:1; border:none; background:transparent; padding:8px 6px; border-radius:9px; font:inherit; font-size:13px; font-weight:600; color:#64748B; cursor:pointer; }
  .sp-seg button.on { background:#fff; color:var(--text); box-shadow:0 1px 3px rgba(0,0,0,.08); }
  .sp-chips { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 8px; }
  .sp-chips button { border:1px solid var(--border); background:#fff; border-radius:999px; padding:5px 12px; font:inherit; font-size:12px; font-weight:600; color:#475569; cursor:pointer; }
  .sp-chips button.on { background:#0F52BA; border-color:#0F52BA; color:#fff; }
  .sp-eq { background:#EFF6FF; color:#0F52BA; border-radius:10px; padding:8px 10px; font-size:13px; font-weight:600; margin-top:8px; }
  .sp-after { font-size:13px; margin-top:6px; color:#334155; }
  .sp-tot { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; margin:6px 0 10px; }
  .sp-tot div { background:#F8FAFC; border-radius:10px; padding:8px 10px; font-size:12px; color:#64748B; }
  .sp-tot b { display:block; font-size:14px; color:var(--text); }
  .ord-line.cancelled .pl-name b, .ord-line.cancelled > b { text-decoration:line-through; color:#94A3B8 !important; }
  .sp-sub { font-size:11px; color:#64748B; font-weight:600; text-align:right; }
  label.pl-row, label.ord-dist-row { text-transform:none; letter-spacing:normal; font-size:13px; color:var(--text); font-weight:400; margin:0; }
  label.pl-row .pl-name b, label.ord-dist-row span { color:var(--text); font-weight:600; }
  label.pl-row .pl-name span { text-transform:none; letter-spacing:normal; }
  .pl-row { display:flex; align-items:center; gap:8px; padding:8px 0; border-bottom:1px solid #F1F5F9; font-size:13px; }
  .pl-row .pl-name { flex:1; min-width:0; }
  .pl-row .pl-name b { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .pl-row .pl-name span { font-size:11px; color:#64748B; }
  .pl-row input[type=number] { width:78px !important; padding:6px 8px !important; margin:0 !important; font-size:13px; }
  .pl-row input[type=checkbox] { width:18px; height:18px; margin:0; }
  .whn-summary { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:8px; margin-bottom:6px; }
  .whn-shop { background:#F8FAFC; border-radius:12px; padding:9px 11px; font-size:12px; color:#64748B; }
  .whn-shop { cursor:pointer; border:1px solid transparent; }
  .whn-shop.active { border-color:var(--blue); background:#EFF6FF; }
  .whn-shop b { display:block; color:var(--text); font-size:13px; }
  .whn-shop .v { color:#9A3412; font-weight:700; font-size:14px; }
  .wh-mx { border-collapse:collapse; font-size:12.5px; width:100%; }
  .wh-mx th { font-size:11.5px; font-weight:700; color:#64748B; padding:8px 6px; border-bottom:1px solid var(--border); text-align:right; white-space:normal; background:#fff; text-transform:none; letter-spacing:0; }
  .wh-mx td { padding:8px 6px; border-bottom:1px solid #F1F5F9; text-align:right; white-space:nowrap; }
  .wh-mx th:first-child, .wh-mx td:first-child { text-align:left; position:sticky; left:0; background:#fff; z-index:1; white-space:normal; min-width:130px; }
  .wh-mx td:first-child span { display:block; font-size:11px; color:#94A3B8; }
  .wh-mx td.cell { cursor:pointer; }
  .wh-mx td.cell:hover { background:#F8FAFC; }
  .wh-mx .q-out { color:#B91C1C; font-weight:800; background:#FEF2F2; border-radius:6px; padding:2px 6px; }
  .wh-mx .q-low { color:#B45309; font-weight:800; background:#FEF3C7; border-radius:6px; padding:2px 6px; }
  .wh-mx .q-none { color:#CBD5E1; }
  .ship-modal { max-width:640px; }
  .net-actions { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:8px; margin:0 0 12px; }
  .ship-list { max-height:48vh; overflow-y:auto; border:1px solid var(--border); border-radius:12px; margin-top:6px; }
  .sh-row { display:flex; align-items:center; gap:8px; padding:9px 10px; border-bottom:1px solid #F1F5F9; }
  .sh-row:last-child { border-bottom:none; }
  .sh-row.sel { background:#EFF6FF; }
  .sh-name { flex:1; min-width:0; }
  .sh-name b { display:block; font-size:13.5px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sh-name span { font-size:11.5px; color:#64748B; }
  .sh-name .need { color:#B45309; font-weight:700; }
  .sh-row input { width:76px !important; padding:6px 8px !important; margin:0 !important; font-size:13px; text-align:right; }
  .sh-row input.over { border-color:#DC2626 !important; background:#FEF2F2 !important; }
  .sh-unit { font-size:12px; color:#64748B; width:22px; }
  .ship-foot { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-top:10px; flex-wrap:wrap; }
  .ship-foot span { font-size:13px; color:#475569; font-weight:600; }
  .imp-steps { display:flex; flex-direction:column; gap:6px; font-size:13px; color:#334155; background:#F8FAFC; border-radius:12px; padding:10px 12px; }
  .imp-sum { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin:8px 0; }
  .imp-sum div { background:#F8FAFC; border-radius:10px; padding:8px; text-align:center; font-size:11.5px; color:#64748B; }
  .imp-sum b { display:block; font-size:18px; color:var(--text); }
  .imp-table { width:100%; border-collapse:collapse; font-size:12px; }
  .imp-table td, .imp-table th { padding:6px; border-bottom:1px solid #F1F5F9; text-align:left; background:none; color:var(--text); text-transform:none; letter-spacing:0; font-size:12px; }
  .imp-tag { display:inline-block; font-size:10.5px; font-weight:700; padding:2px 6px; border-radius:6px; }
  .imp-tag.new { background:#DCFCE7; color:#15803D; }
  .imp-tag.upd { background:#DBEAFE; color:#1D4ED8; }
  .imp-tag.err { background:#FEE2E2; color:#B91C1C; }
  .dash-row {
    display:flex; justify-content:space-between; align-items:center; padding:8px 0;
    border-bottom:1px dashed var(--border); font-size:13.5px;
  }
  .dash-row:last-child { border-bottom:none; }
  .dash-row .dash-row-rank {
    display:inline-flex; align-items:center; justify-content:center; width:20px; height:20px;
    background:var(--field-bg); border-radius:50%; font-size:11px; font-weight:700; color:var(--hint); margin-right:8px; flex:none;
  }
  .dash-row .dash-row-name { color:var(--text); font-weight:600; }
  .dash-row .dash-row-value { color:var(--blue); font-weight:700; flex:none; }
  .dash-row .dash-row-value.warn { color:#B3241C; }
  .dash-summary-grid { display:grid; grid-template-columns:repeat(2, 1fr); gap:10px; }
  .dash-summary-box { background:var(--field-bg); border-radius:12px; padding:12px; text-align:center; }
  .dash-summary-box .dsb-num { font-size:20px; font-weight:700; color:var(--text); font-family:var(--font-mono); }
  .dash-summary-box .dsb-num.warn { color:#B3241C; }
  .dash-summary-box .dsb-label { font-size:11px; color:var(--hint); margin-top:2px; }
  .dash-brands-panel { background:var(--field-bg); border-radius:10px; margin:4px 0 8px; padding:2px 8px; }
  .recur-exp-card {
    background:var(--field-bg); border-radius:12px; padding:12px; margin-bottom:8px;
  }
  .recur-exp-card.overdue { background:#FEF2F2; }
  .recur-exp-card .rec-top { display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }
  .recur-exp-card .rec-name { font-size:14px; font-weight:700; color:var(--text); }
  .recur-exp-card .rec-meta { font-size:11.5px; color:var(--hint); margin-top:2px; }
  .recur-exp-card .rec-amount { font-size:15px; font-weight:700; color:var(--blue); flex:none; }
  .recur-exp-card .rec-actions { display:flex; gap:6px; margin-top:10px; padding-top:10px; border-top:1px dashed var(--border); }
  .journal-row { display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px dashed var(--border); font-size:13px; }
  .journal-row:last-child { border-bottom:none; }
  .journal-row .jr-cat { font-weight:700; color:var(--text); }
  .journal-row .jr-meta { font-size:11.5px; color:var(--hint); margin-top:2px; }
  .journal-row .jr-amount { color:#B3241C; font-weight:700; flex:none; }
  .jr-icon-btn {
    background:none; border:none; cursor:pointer; font-size:13px; padding:4px; color:var(--hint); flex:none;
  }
  .jr-icon-btn:active { color:var(--blue); }
  .jr-edit-form { background:var(--field-bg); border-radius:10px; padding:12px; margin:2px 0 10px; }
  .kc-hist-list { margin-top:14px; }
  .kc-hist-entry { background:var(--field-bg); border-radius:12px; padding:12px 13px; margin-bottom:8px; }
  .kc-hist-entry .kc-he-top { display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }
  .kc-hist-entry .kc-he-service { font-size:14px; font-weight:700; color:var(--text); }
  .kc-hist-entry .kc-he-date { font-size:11.5px; color:var(--hint); margin-top:2px; }
  .kc-hist-entry .kc-he-cost { font-size:15px; font-weight:700; color:var(--blue); flex:none; white-space:nowrap; }
  .kc-hist-entry .kc-he-meta { font-size:12px; color:var(--hint); margin-top:6px; }
  .kc-hist-entry .kc-he-items { font-size:12px; color:var(--text); margin-top:6px; line-height:1.5; }
  .kc-hist-entry .kc-he-notes { font-size:12px; color:var(--hint); margin-top:6px; }
  .kc-hist-entry .kc-he-actions { margin-top:8px; padding-top:8px; border-top:1px dashed var(--border); }
  .sub-banner { display:flex; align-items:center; gap:10px; margin:0 0 12px; padding:12px 14px; border-radius:12px; background:#FEF0DC; color:#7A3A04; font-size:14px; font-weight:700; line-height:1.35; text-decoration:none; border:1.5px solid #F2C27D; }
  .sub-banner span { flex:1; }
  .sub-banner i { flex:none; }
  .sub-banner.ro { background:#FCE6EA; color:#7A0C20; border-color:#F0A3B0; }
  .ro-mode > :not(.ro-pay) { display:none !important; }
  .ro-pay { grid-column:1 / -1; max-width:560px; margin:8px auto 24px; background:#fff; border:1px solid #E3E8F0; border-radius:18px; padding:24px 20px; text-align:center; display:flex; flex-direction:column; align-items:center; gap:12px; box-shadow:0 8px 24px rgba(11,31,58,.06); }
  .ro-pay .ro-ic { width:76px; height:76px; border-radius:50%; background:#EEF3FB; color:#1D6FE0; display:flex; align-items:center; justify-content:center; font-size:30px; }
  .ro-pay h2 { margin:0; font-size:22px; font-weight:800; color:#0B1F3A; }
  .ro-pay p { margin:0; font-size:15px; line-height:1.5; color:#3E4F68; }
  .ro-offer { width:100%; background:#FFF6D6; border:1.5px solid #F5B700; color:#5C4300; border-radius:14px; padding:12px 14px; font-size:15px; font-weight:700; line-height:1.4; }
  .ro-btn { width:100%; height:52px; border:0; border-radius:12px; background:#1D6FE0; color:#fff; font:700 16px 'Plus Jakarta Sans', system-ui, sans-serif; display:flex; align-items:center; justify-content:center; gap:10px; text-decoration:none; cursor:pointer; }
  .ro-btn.ghost { background:#fff; color:#0B1F3A; border:1.5px solid #D5DDE8; height:48px; font-size:15px; }
  .ro-sheet-bg { position:fixed; inset:0; z-index:9998; background:rgba(11,31,58,.45); display:flex; align-items:flex-end; justify-content:center; }
  .ro-pay.ro-sheet { width:100%; max-width:480px; margin:0; border:0; box-shadow:none; border-radius:20px 20px 0 0; padding:22px 20px calc(20px + env(safe-area-inset-bottom, 0px)); }
  @media (min-width:900px) { .ro-sheet-bg { align-items:center; } .ro-pay.ro-sheet { border-radius:20px; } }
  #view-staff label[for] { display:block; font-size:13px; font-weight:600; color:var(--text); margin:12px 0 4px; }
  .staff-err { display:none; color:#B3241C; font-size:13px; margin-top:4px; }
  .staff-err.on { display:block; }
  .staff-creds { margin-top:14px; padding:12px; border-radius:12px; background:#ECFDF5; border:1.5px solid #86EFAC; }
  .staff-creds-t { font-size:13px; font-weight:700; color:#166534; margin-bottom:8px; }
  .staff-creds-v { white-space:pre-line; font-family:'IBM Plex Mono', ui-monospace, monospace; font-size:14px; color:#14532D; background:#fff; border-radius:8px; padding:10px; user-select:all; }
  .staff-copy { margin-top:8px; border:0; border-radius:8px; padding:8px 14px; background:#16A34A; color:#fff; font-weight:700; font-size:13px; cursor:pointer; }
  .cash-total { background:linear-gradient(135deg,#0F52BA,#1E6FD9); color:#fff; border-radius:16px; padding:16px 18px; margin-bottom:14px; }
  .cash-total .ct-l { font-size:13px; opacity:.85; font-weight:600; }
  .cash-total .ct-v { font-size:28px; font-weight:800; margin:4px 0 2px; font-family:'Space Grotesk',sans-serif; }
  .cash-total .ct-h { font-size:12px; opacity:.8; }
  .cash-card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:14px; margin-bottom:12px; }
  .cash-card.off { opacity:.75; }
  .cash-head { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
  .cash-name { font-weight:700; font-size:15px; color:var(--text); }
  .cash-sub { font-size:12px; color:var(--hint); margin-top:2px; }
  .cash-bal { text-align:right; }
  .cash-bal b { display:block; font-size:21px; font-weight:800; color:#0F52BA; font-family:'Space Grotesk',sans-serif; white-space:nowrap; }
  .cash-bal.zero b { color:#16A34A; font-size:15px; }
  .cash-bal.neg b { color:#B3241C; }
  .cash-bal span { font-size:11px; color:var(--hint); }
  .cash-lines { margin:10px 0 0; border-top:1px dashed var(--border); padding-top:8px; }
  .cash-line { display:flex; justify-content:space-between; font-size:13px; padding:3px 0; color:var(--text); }
  .cash-line.muted { color:var(--hint); }
  .cash-line b { font-weight:700; white-space:nowrap; }
  .cash-card > .cash-lines:first-child { border-top:0; margin-top:0; padding-top:0; }
  #cashAccRest { margin:6px 0 10px; }
  .cash-warn { font-size:12px; color:#92400E; background:#FEF3C7; border-radius:8px; padding:6px 8px; margin-top:8px; }
  .cash-btns { display:flex; gap:8px; margin-top:12px; }
  .cash-btns button { flex:1; border:0; border-radius:10px; padding:11px 10px; font-size:14px; font-weight:700; cursor:pointer; }
  .cash-btns .acc { background:#16A34A; color:#fff; }
  .cash-btns .acc:disabled { background:#CBD5E1; color:#fff; cursor:default; }
  .cash-btns .det { background:#EEF2F7; color:#334155; flex:0 0 auto; }
  .cash-more { margin-top:10px; }
  .cash-sec { font-size:12.5px; font-weight:700; color:var(--hint); text-transform:uppercase; letter-spacing:.3px; margin:12px 0 4px; }
  .cash-row { display:flex; justify-content:space-between; gap:8px; align-items:center; font-size:13px; padding:7px 0; border-bottom:1px solid var(--border); }
  .cash-row:last-child { border-bottom:0; }
  .cash-row .cr-l { min-width:0; }
  .cash-row .cr-l small { display:block; color:var(--hint); font-size:11.5px; }
  .cash-row .cr-r { text-align:right; white-space:nowrap; }
  .cash-row .cr-r small { display:block; color:var(--hint); font-size:11px; }
  .cash-row.cancelled { opacity:.5; text-decoration:line-through; }
  .cash-row .cr-x { border:1px solid #F5C2BE; background:#FDECEA; color:#B3241C; border-radius:8px; padding:4px 8px; font-size:11.5px; font-weight:700; cursor:pointer; margin-left:6px; text-decoration:none; }
  .cash-m-title { font-size:17px; font-weight:800; color:var(--text); }
  .cash-m-who { font-size:13px; color:var(--hint); margin:2px 0 12px; }
  .cash-m-exp { display:flex; justify-content:space-between; align-items:center; background:#EFF6FF; border-radius:10px; padding:10px 12px; margin-bottom:6px; font-size:13px; color:#1E3A8A; }
  .cash-m-exp b { font-size:18px; }
  .cash-ok-btn { background:#16A34A !important; }
  #view-cash { max-width:760px; }
  .staff-cash a { color:#16A34A; font-weight:700; text-decoration:none; }
  .staff-cash { font-size:12.5px; margin-top:4px; color:var(--hint); }
  .staff-cash b { color:#0F52BA; }
  .staff-row { padding:10px 0; border-bottom:1px dashed var(--border); }
  .staff-row:last-child { border-bottom:0; }
  .staff-row.off .staff-who b { opacity:.55; }
  .staff-who { display:flex; flex-wrap:wrap; align-items:center; gap:6px 8px; font-size:14px; color:var(--text); }
  .staff-pill { font-size:11.5px; font-weight:700; padding:2px 8px; border-radius:999px; background:#E2E8F0; color:#475569; }
  .staff-pill.on { background:#DCFCE7; color:#166534; }
  .staff-btns { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  .staff-btns button { border:1px solid var(--border); background:#F8FAFC; color:var(--text); border-radius:8px; padding:7px 10px; font-size:12.5px; font-weight:600; cursor:pointer; }
  .staff-btns button.del { color:#B3241C; border-color:#F5C2BE; background:#FDECEA; }
  #view-team { max-width:820px; }
  .tm-head { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
  .tm-month { display:flex; align-items:center; gap:6px; background:var(--card); border:1px solid var(--border); border-radius:12px; padding:4px; }
  .tm-month button { border:0; background:#EEF2F7; color:#334155; width:34px; height:34px; border-radius:9px; cursor:pointer; font-size:14px; }
  .tm-month b { min-width:118px; text-align:center; font-size:14.5px; color:var(--text); }
  .tm-head select { flex:1; min-width:150px; max-width:260px; margin:0; }
  .tm-tiles { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; margin-bottom:12px; }
  .tm-tile { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:10px 12px; min-width:0; }
  .tm-tile span { display:block; font-size:12px; color:var(--hint); font-weight:600; }
  .tm-tile b { display:block; font-size:18px; font-weight:800; color:var(--text); font-family:'Space Grotesk',sans-serif; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .tm-tile.blue { background:linear-gradient(135deg,#0F52BA,#1E6FD9); border-color:transparent; }
  .tm-tile.blue span, .tm-tile.blue b { color:#fff; }
  .tm-tile.green b { color:#16A34A; }
  .tm-leader { display:flex; align-items:center; gap:12px; background:#FFFBEB; border:1.5px solid #FCD34D; border-radius:14px; padding:12px 14px; margin-bottom:12px; }
  .tm-leader i.fa-award { font-size:28px; color:#D97706; }
  .tm-leader .tl-t { font-weight:800; font-size:15px; color:#78350F; }
  .tm-leader .tl-s { font-size:12.5px; color:#92400E; margin-top:2px; }
  .tm-leader .tl-certs { margin-left:auto; display:flex; flex-direction:column; gap:6px; flex:0 0 auto; }
  .tm-leader a { flex:0 0 auto; background:#D97706; color:#fff; text-decoration:none; font-weight:700; font-size:13px; border-radius:10px; padding:9px 12px; white-space:nowrap; }
  .tm-card { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:14px; margin-bottom:12px; }
  .tm-card-t { font-size:13px; font-weight:800; color:var(--hint); text-transform:uppercase; letter-spacing:.3px; margin-bottom:10px; display:flex; justify-content:space-between; gap:8px; }
  .tm-card-t small { text-transform:none; letter-spacing:0; font-weight:600; }
  .tm-podium { display:flex; align-items:flex-end; justify-content:center; gap:10px; padding-top:6px; }
  .tm-pod { flex:1; max-width:130px; text-align:center; min-width:0; }
  .tm-pod .av { width:46px; height:46px; margin:0 auto 4px; }
  .tm-pod .nm { font-size:13.5px; font-weight:700; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .tm-pod .pt { font-size:12px; color:var(--hint); margin-bottom:4px; }
  .tm-pod .st { border-radius:10px 10px 0 0; color:#fff; font-weight:800; font-size:22px; font-family:'Space Grotesk',sans-serif; padding-top:8px; }
  .tm-pod.p1 .st { background:#0F52BA; height:92px; }
  .tm-pod.p2 .st { background:#5B8FD9; height:68px; }
  .tm-pod.p3 .st { background:#A9C4EC; height:50px; color:#0A2540; }
  .tm-pod .crown { color:#D97706; font-size:18px; height:20px; }
  .tm-pod.empty { visibility:hidden; }
  .av { border-radius:50%; background:#DBEAFE; color:#1E40AF; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:15px; }
  .tm-row { display:flex; align-items:center; gap:10px; padding:9px 0; border-top:1px solid var(--border); font-size:13.5px; color:var(--text); }
  .tm-row .pl { width:22px; text-align:center; font-weight:800; color:var(--hint); }
  .tm-row .av { width:32px; height:32px; font-size:13px; flex:0 0 auto; }
  .tm-row .who { flex:1; min-width:0; }
  .tm-row .who b { display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .tm-row .who small { color:var(--hint); font-size:11.5px; }
  .tm-row .num { text-align:right; white-space:nowrap; }
  .tm-row .num b { display:block; }
  .tm-row .num small { color:var(--hint); font-size:11.5px; }
  .tm-mv { font-size:11.5px; font-weight:800; margin-left:4px; }
  .tm-mv.up { color:#16A34A; } .tm-mv.down { color:#DC2626; }
  .tm-row.me { background:#EFF6FF; border-radius:10px; padding-left:6px; padding-right:6px; }
  .tm-rule { font-size:12px; color:var(--hint); margin-top:8px; }
  .tm-sal { border-top:1px solid var(--border); padding:12px 0; }
  .tm-sal:first-of-type { border-top:0; padding-top:0; }
  .tm-sal-h { display:flex; align-items:center; gap:10px; }
  .tm-sal-h .av { width:38px; height:38px; flex:0 0 auto; }
  .tm-sal-h .who { flex:1; min-width:0; }
  .tm-sal-h .who b { display:block; font-size:14.5px; color:var(--text); }
  .tm-sal-h .who small { color:var(--hint); font-size:12px; }
  .tm-sal-h .sum { text-align:right; }
  .tm-sal-h .sum b { display:block; font-size:17px; font-weight:800; color:var(--text); font-family:'Space Grotesk',sans-serif; white-space:nowrap; }
  .tm-sal-h .sum small { color:var(--hint); font-size:11.5px; white-space:nowrap; }
  .tm-sal-h .sum small.due { color:#B45309; font-weight:700; }
  .tm-bar { height:7px; background:#E2E8F0; border-radius:4px; overflow:hidden; margin-top:4px; }
  .tm-bar i { display:block; height:100%; background:#0F52BA; border-radius:4px; }
  .tm-bar.done i { background:#16A34A; }
  .tm-plan { font-size:12px; color:var(--hint); margin-top:8px; }
  .tm-btns { display:flex; gap:8px; margin-top:10px; }
  .tm-btns button { flex:1; border:0; border-radius:10px; padding:10px; font-size:13.5px; font-weight:700; cursor:pointer; background:#EEF2F7; color:#334155; }
  .tm-btns button.pay { background:#16A34A; color:#fff; }
  .tm-lines { margin:6px 0 10px; }
  .tm-line { display:flex; justify-content:space-between; gap:10px; font-size:13.5px; padding:5px 0; color:var(--text); border-bottom:1px dashed var(--border); }
  .tm-line span { min-width:0; }
  .tm-line b { white-space:nowrap; }
  .tm-line.muted { color:var(--hint); }
  .tm-line.tot { border-bottom:0; font-size:15.5px; font-weight:800; padding-top:8px; }
  .tm-line.tot b { color:#16A34A; }
  .tm-sec { font-size:12.5px; font-weight:800; color:var(--hint); text-transform:uppercase; letter-spacing:.3px; margin:16px 0 6px; }
  .tm-grid2 { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
  .tm-grid2 label, #view-team label, #teamModal label { display:block; font-size:12.5px; font-weight:600; color:var(--text); margin:8px 0 4px; }
  .tm-badges { display:flex; flex-wrap:wrap; gap:6px; }
  .tm-badge { display:inline-flex; align-items:center; gap:6px; background:#EFF6FF; color:#1E3A8A; border-radius:999px; padding:5px 10px; font-size:12px; font-weight:700; }
  .tm-badge.gold { background:#FEF3C7; color:#78350F; }
  .tm-badge.off { background:#F1F5F9; color:#94A3B8; }
  .tm-hist { display:flex; justify-content:space-between; gap:8px; align-items:center; font-size:13px; padding:7px 0; border-bottom:1px solid var(--border); }
  .tm-hist.cancelled { opacity:.5; text-decoration:line-through; }
  .tm-hist small { display:block; color:var(--hint); font-size:11.5px; }
  .tm-hist button { border:1px solid #F5C2BE; background:#FDECEA; color:#B3241C; border-radius:8px; padding:4px 8px; font-size:11.5px; font-weight:700; cursor:pointer; }
  .tm-me { background:linear-gradient(135deg,#0F52BA,#1E6FD9); color:#fff; border-radius:16px; padding:16px; margin-bottom:12px; }
  .tm-me .l { font-size:13px; opacity:.85; font-weight:600; }
  .tm-me .v { font-size:30px; font-weight:800; font-family:'Space Grotesk',sans-serif; }
  .tm-me .s { font-size:12.5px; opacity:.85; }
  .tm-me .tm-bar { background:rgba(255,255,255,.25); }
  .tm-me .tm-bar i { background:#fff; }
  .tm-me .tm-plan { color:#fff; opacity:.85; }
  .tm-details summary { cursor:pointer; font-weight:700; font-size:14px; color:var(--text); list-style:none; }
  .tm-details summary::-webkit-details-marker { display:none; }
  .tm-details summary i { color:var(--hint); margin-right:6px; }
  @media (max-width:420px) { .tm-tile b { font-size:15.5px; } .tm-month b { min-width:100px; } }

  /* ---------- Обучение: карта курса ---------- */
  /* дизайн «Dala» (DESIGN.md): чёрная пустота, один фиолетовый акцент, янтарные подписи, Inter 400/300 */
  .course-wrap { --iris:#8052ff; --iris-2:#a98bff; --saffron:#ffb829; --ash:#9a9a9a; --silver:#bdbdbd; --hair:rgba(255,255,255,.12); --hair-2:rgba(255,255,255,.07);
    background:#000; color:#fff; border-radius:24px; padding:34px 22px 40px; position:relative; overflow:hidden;
    font-family:"Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; font-weight:300; font-feature-settings:"ss01" on; -webkit-font-smoothing:antialiased; }
  .course-wrap > *:not(.dala-fx) { position:relative; z-index:1; }
  .course-top { position:relative; margin:-34px -22px 0; padding:34px 22px 10px; min-height:220px; }
  .course-top > *:not(.dala-fx) { position:relative; z-index:1; max-width:620px; }
  .course-sub { font-size:13px; font-weight:600; color:var(--saffron); text-transform:uppercase; letter-spacing:.025em; }
  .course-head { font-size:clamp(32px, 5.4vw, 64px); font-weight:400; line-height:1.04; letter-spacing:-.04em; margin:12px 0 0; max-width:640px; }
  .course-note { font-size:15px; color:var(--silver); margin-top:12px; }
  .course-prog { display:flex; align-items:center; gap:12px; margin-top:22px; max-width:420px; font-size:12px; font-weight:600; color:var(--ash); text-transform:uppercase; letter-spacing:.025em; font-variant-numeric:tabular-nums; }
  .course-prog i { flex:1; height:2px; background:var(--hair); position:relative; }
  .course-prog i b { position:absolute; inset:0 auto 0 0; background:var(--iris); }
  .course-map { position:relative; margin:30px auto 0; max-width:520px; }
  .course-map svg.course-path { position:absolute; left:0; top:0; pointer-events:none; }
  .cnode { position:absolute; width:46px; height:46px; margin-left:-23px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:400; font-size:16px; text-decoration:none; cursor:pointer; -webkit-tap-highlight-color:transparent; font-variant-numeric:tabular-nums; transition:border-color .2s, color .2s; }
  .cnode.done { background:#000; color:#fff; border:1px solid var(--iris); }
  .cnode.open { background:#000; color:var(--ash); border:1px solid var(--hair); }
  .cnode.open:hover, .cnode.done:hover { border-color:var(--iris-2); color:#fff; }
  .cnode.cur { width:64px; height:64px; margin-left:-32px; background:var(--iris); color:#fff; border:0; box-shadow:0 0 0 8px rgba(128,82,255,.18), 0 0 40px rgba(128,82,255,.45); font-size:22px; }
  .cnode.lock { background:#000; color:var(--ash); border:1px dashed var(--hair); font-size:13px; opacity:.75; }
  .course-row.lock span.cr-t { color:var(--ash); }
  .course-gate { max-width:620px; margin:18px auto 6px; border:1px solid rgba(255,184,41,.45); border-radius:20px; padding:18px 18px 20px; display:flex; flex-direction:column; gap:6px; background:rgba(255,184,41,.06); }
  .course-gate .cg-tag { font-size:12px; font-weight:600; color:var(--saffron); text-transform:uppercase; letter-spacing:.025em; }
  .course-gate .cg-t { font-size:20px; font-weight:400; color:#fff; line-height:1.25; }
  .course-gate .cg-d { font-size:14px; color:var(--silver); }
  .course-gate .cg-btn { align-self:flex-start; margin-top:10px; background:var(--saffron); color:#1a1200; border-radius:24px; padding:11px 18px; font-size:12.5px; font-weight:600; text-transform:uppercase; letter-spacing:.025em; text-decoration:none; }
  .cnode .cscore { position:absolute; bottom:-20px; left:50%; transform:translateX(-50%); font-size:11px; font-weight:600; color:var(--saffron); white-space:nowrap; letter-spacing:.025em; }
  .ccard { position:absolute; width:150px; box-sizing:border-box; background:#000; color:#fff; border:1px solid var(--hair); border-radius:24px; padding:14px; display:flex; flex-direction:column; gap:8px; }
  .ccard .cc-meta { font-size:11px; font-weight:600; color:var(--saffron); text-transform:uppercase; letter-spacing:.025em; }
  .ccard .cc-title { font-size:15px; font-weight:400; line-height:1.25; letter-spacing:-.01em; }
  .ccard a { display:block; background:var(--iris); color:#fff; text-decoration:none; text-align:center; border-radius:24px; padding:11px 0; font-weight:600; font-size:12.5px; text-transform:uppercase; letter-spacing:.025em; }
  .ccard a:hover { background:#6d3ff5; }
  .course-list { margin:38px auto 0; max-width:620px; display:flex; flex-direction:column; border-top:1px solid var(--hair-2); }
  .course-row { display:flex; align-items:center; gap:16px; padding:16px 4px; color:#fff; text-decoration:none; font-size:16px; font-weight:300; border-bottom:1px solid var(--hair-2); transition:padding .2s; }
  .course-row:hover { padding-left:10px; }
  .course-row:hover span.cr-t { color:#fff; }
  .course-row b { width:28px; flex:none; font-size:13px; font-weight:600; color:var(--ash); font-variant-numeric:tabular-nums; letter-spacing:.025em; }
  .course-row.done b { color:var(--iris-2); }
  .course-row span.cr-t { flex:1; min-width:0; color:#e6e6e6; }
  .course-row span.cr-s { font-size:12px; font-weight:600; color:var(--saffron); letter-spacing:.025em; }
  .course-bonus { display:block; margin:46px auto 0; max-width:620px; text-decoration:none; color:#fff; border:1px solid var(--hair); border-radius:24px; padding:26px 22px; position:relative; overflow:hidden; transition:border-color .2s; }
  .course-bonus:hover { border-color:rgba(128,82,255,.7); }
  .course-bonus > *:not(.dala-fx) { position:relative; z-index:1; }
  .course-bonus .cb-tag { display:block; font-size:12px; font-weight:600; color:var(--saffron); text-transform:uppercase; letter-spacing:.025em; }
  .course-bonus .cb-t { display:block; font-size:clamp(24px, 3.4vw, 36px); font-weight:400; line-height:1.1; letter-spacing:-.04em; margin:10px 0 8px; max-width:420px; }
  .course-bonus .cb-d { display:block; font-size:15px; color:var(--silver); max-width:400px; }
  .course-bonus .cb-foot { display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-top:18px; }
  .course-bonus .cb-btn { background:var(--iris); color:#fff; border-radius:24px; padding:11px 18px; font-size:12.5px; font-weight:600; text-transform:uppercase; letter-spacing:.025em; }
  .course-bonus .cb-m { font-size:12px; font-weight:600; color:var(--ash); text-transform:uppercase; letter-spacing:.025em; }
  @media (max-width:560px) { .course-wrap { padding:26px 16px 30px; } .course-top { margin:-26px -16px 0; padding:26px 16px 10px; min-height:0; } }
""" + HELP_CSS + """
</style>
<script src="/static/course/dala-fx.js?v=5" defer></script>
</head>
<body>
<div class="speedline"></div>
<!-- Навигация: на телефоне — нижняя панель + шторка «Ещё», на широком экране — меню слева.
     Пункты бокового меню несут id="tab-..." (на них опирается showTab), нижняя панель и
     шторка помечены только data-tab — активный пункт подсвечивается везде сразу. -->
<aside class="side-nav">
  <div class="side-brand">
    <div class="logo-badge"><i class="fa-solid fa-droplet"></i></div>
    <div style="min-width:0;">
      <div class="side-shop">{{ shop_name }}</div>
      <div class="logo-sub brand-line"><span class="wordmark"><span class="wm-oil">Oil</span><span class="wm-book">Book</span></span>{% if is_employee %} · <span class="role-tag">{{ T.role_employee }}</span>{% elif is_branch %} · <span class="role-tag">{{ T.role_branch }}</span>{% endif %}</div>
    </div>
  </div>
  <nav class="side-list">
    <div class="side-item side-add active" id="tab-add" data-tab="add" onclick="showTab('add')"><i class="fa-solid fa-plus"></i><span>{{ T.tab_add }}</span><kbd class="side-kbd">F2</kbd></div>
    <div class="side-group">{{ T.nav_grp_work }}</div>
    <div class="side-item" id="tab-table" data-tab="table" onclick="showTab('table')"><i class="fa-solid fa-car"></i><span>{{ T.tab_table }}</span></div>
    <div class="side-item" id="tab-debts" data-tab="debts" onclick="showTab('debts')"><i class="fa-solid fa-hand-holding-dollar"></i><span>{{ T.tab_debts }}</span><b class="nav-badge" data-badge="debts"></b></div>
    {% if is_employee or has_staff %}<div class="side-item" id="tab-cash" data-tab="cash" onclick="showTab('cash')"><i class="fa-solid fa-cash-register"></i><span>{{ T.tab_cash_my if is_employee else T.tab_cash_owner }}</span></div>{% endif %}
    {% if team_on %}<div class="side-item" id="tab-team" data-tab="team" onclick="showTab('team')"><i class="fa-solid fa-trophy"></i><span>{{ T.tab_team }}</span></div>{% endif %}
    <div class="side-item" id="tab-broadcast" data-tab="broadcast" onclick="showTab('broadcast')"><i class="fa-solid fa-bullhorn"></i><span>{{ T.tab_broadcast }}</span></div>
    {% if sms_enabled %}<div class="side-item" id="tab-sms" data-tab="sms" onclick="showTab('sms')"><i class="fa-solid fa-comment-sms"></i><span>{{ T.tab_sms }}</span></div>{% endif %}
    {% if not is_employee or (warehouse_enabled and store_enabled) %}<div class="side-group">{{ T.nav_grp_business }}</div>{% endif %}
    {% if not is_employee %}<div class="side-item" id="tab-stats" data-tab="stats" onclick="showTab('stats')"><i class="fa-solid fa-chart-column"></i><span>{{ T.tab_stats }}</span></div>{% endif %}
    {% if warehouse_enabled and (not is_employee or store_enabled) %}<div class="side-item" id="tab-warehouse" data-tab="warehouse" onclick="showTab('warehouse')"><i class="fa-solid {{ 'fa-store' if is_employee else 'fa-boxes-stacked' }}"></i><span>{{ T.st_tab if is_employee else T.tab_warehouse }}</span></div>{% endif %}
    {% if warehouse_enabled and not is_employee and not is_branch %}<div class="side-item" id="tab-suppliers" data-tab="suppliers" onclick="showTab('suppliers')"><i class="fa-solid fa-truck-field"></i><span>{{ T.tab_suppliers }}</span><b class="nav-badge" data-badge="suppliers"></b></div>{% endif %}
    {% if not is_employee %}<div class="side-item" id="tab-expenses" data-tab="expenses" onclick="showTab('expenses')"><i class="fa-solid fa-receipt"></i><span>{{ T.tab_expenses }}</span></div>{% endif %}
    {% if not is_employee %}<div class="side-item" id="tab-rate" data-tab="rate" onclick="showTab('rate')"><i class="fa-solid fa-dollar-sign"></i><span>{{ T.usd_rate_title }}</span><b class="nav-badge" data-badge="rate"></b></div>{% endif %}
    {% if not is_employee %}<div class="side-item" id="tab-export" data-tab="export" onclick="showTab('export')"><i class="fa-solid fa-file-arrow-down"></i><span>{{ T.tab_export }}</span></div>{% endif %}
    <div class="side-group">{{ T.nav_grp_settings }}</div>
    {% if not is_employee %}<div class="side-item" id="tab-staff" data-tab="staff" onclick="showTab('staff')"><i class="fa-solid fa-user-group"></i><span>{{ T.tab_staff }}</span></div>{% endif %}
    {% if not is_employee %}<div class="side-item" id="tab-myshop" data-tab="myshop" onclick="showTab('myshop')"><i class="fa-solid fa-store"></i><span>{{ T.tab_myshop }}</span></div>{% endif %}
    {% if is_sub_owner %}<div class="side-item" onclick="location.href='/subscription'"><i class="fa-solid fa-credit-card"></i><span>{{ T.sub_menu }}</span></div>{% endif %}
    {% if is_sub_owner %}<div class="side-item" onclick="location.href='/referral'"><i class="fa-solid fa-gift"></i><span>{{ T.ref_menu }}</span></div>{% endif %}
    <div class="side-item" id="tab-course" data-tab="course" onclick="showTab('course')"><i class="fa-solid fa-graduation-cap"></i><span>{{ T.tab_course }}</span></div>
    <div class="side-item" id="tab-help" data-tab="help" onclick="showTab('help')"><i class="fa-solid fa-circle-question"></i><span>{{ T.tab_help }}</span></div>
  </nav>
  <div class="side-foot">
    <button class="lang-btn gl-theme-btn" onclick="glToggle()"><i class="fa-solid fa-circle-half-stroke"></i> <span class="gl-on-only" title="{{ T.theme_to_classic }}">{{ T.theme_short }}</span><span class="gl-off-only" title="{{ T.theme_to_glass }}">{{ T.theme_short }}</span></button>
    <button class="lang-btn" onclick="switchLanguage()">{{ T.lang_switch }}</button>
    <a class="logout" href="/logout"><i class="fa-solid fa-arrow-right-from-bracket"></i> {{ T.logout }}</a>
  </div>
</aside>

{% set bar_slot2 = 'debts' if is_employee else 'stats' %}
{% set bar_slot4 = 'warehouse' if (warehouse_enabled and not is_employee) else ('broadcast' if is_employee else 'debts') %}
<nav class="bottom-bar" id="bottomBar">
  <div class="bb-item" data-tab="table" onclick="showTab('table')"><i class="fa-solid fa-car"></i><span>{{ T.tab_table }}</span></div>
  {% if bar_slot2 == 'stats' %}
  <div class="bb-item" data-tab="stats" onclick="showTab('stats')"><i class="fa-solid fa-chart-column"></i><span>{{ T.tab_stats }}</span></div>
  {% else %}
  <div class="bb-item" data-tab="debts" onclick="showTab('debts')"><i class="fa-solid fa-hand-holding-dollar"></i><span>{{ T.tab_debts }}</span><b class="nav-badge" data-badge="debts"></b></div>
  {% endif %}
  <div class="bb-item bb-add active" data-tab="add" onclick="showTab('add')"><div class="bb-plus"><i class="fa-solid fa-plus"></i></div><span>{{ T.nav_add_short }}</span></div>
  {% if bar_slot4 == 'warehouse' %}
  <div class="bb-item" data-tab="warehouse" onclick="showTab('warehouse')"><i class="fa-solid fa-boxes-stacked"></i><span>{{ T.tab_warehouse }}</span></div>
  {% elif bar_slot4 == 'debts' %}
  <div class="bb-item" data-tab="debts" onclick="showTab('debts')"><i class="fa-solid fa-hand-holding-dollar"></i><span>{{ T.tab_debts }}</span><b class="nav-badge" data-badge="debts"></b></div>
  {% else %}
  <div class="bb-item" data-tab="broadcast" onclick="showTab('broadcast')"><i class="fa-solid fa-bullhorn"></i><span>{{ T.tab_broadcast }}</span></div>
  {% endif %}
  <div class="bb-item" id="bbMore" onclick="openMore()"><i class="fa-solid fa-ellipsis"></i><span>{{ T.nav_more }}</span><b class="nav-badge" id="moreBadge"></b></div>
</nav>

<div class="more-backdrop" id="moreBackdrop" onclick="closeMore()"></div>
<div class="more-sheet" id="moreSheet" data-bar="table,{{ bar_slot2 }},add,{{ bar_slot4 }}">
  <div class="more-grab"></div>
  <div class="more-list">
      {% if is_employee or has_staff %}<div class="more-item" data-tab="cash" data-more-slot="cash" onclick="showTab('cash'); closeMore();"><i class="fa-solid fa-cash-register"></i><span>{{ T.tab_cash_my if is_employee else T.tab_cash_owner }}</span></div>{% endif %}
      {% if team_on %}<div class="more-item" data-tab="team" data-more-slot="team" onclick="showTab('team'); closeMore();"><i class="fa-solid fa-trophy"></i><span>{{ T.tab_team }}</span></div>{% endif %}
      {% if warehouse_enabled and not is_employee and not is_branch %}<div class="more-item" data-tab="suppliers" onclick="showTab('suppliers'); closeMore();"><i class="fa-solid fa-truck-field"></i><span>{{ T.tab_suppliers }}</span><b class="nav-badge" data-badge="suppliers"></b></div>{% endif %}
      <div class="more-item" data-tab="table" data-more-slot="table" onclick="showTab('table'); closeMore();"><i class="fa-solid fa-car"></i><span>{{ T.tab_table }}</span></div>
      {% if not is_employee %}<div class="more-item" data-tab="stats" data-more-slot="stats" onclick="showTab('stats'); closeMore();"><i class="fa-solid fa-chart-column"></i><span>{{ T.tab_stats }}</span></div>{% endif %}
      {% if warehouse_enabled and (not is_employee or store_enabled) %}<div class="more-item" data-tab="warehouse" data-more-slot="warehouse" onclick="showTab('warehouse'); closeMore();"><i class="fa-solid {{ 'fa-store' if is_employee else 'fa-boxes-stacked' }}"></i><span>{{ T.st_tab if is_employee else T.tab_warehouse }}</span></div>{% endif %}
      <div class="more-item" data-tab="debts" data-more-slot="debts" onclick="showTab('debts'); closeMore();"><i class="fa-solid fa-hand-holding-dollar"></i><span>{{ T.tab_debts }}</span><b class="nav-badge" data-badge="debts"></b></div>
      {% if not is_employee %}<div class="more-item" data-tab="expenses" data-more-slot="expenses" onclick="showTab('expenses'); closeMore();"><i class="fa-solid fa-receipt"></i><span>{{ T.tab_expenses }}</span></div>{% endif %}
      {% if not is_employee %}<div class="more-item" data-tab="rate" data-more-slot="rate" onclick="showTab('rate'); closeMore();"><i class="fa-solid fa-dollar-sign"></i><span>{{ T.usd_rate_title }}</span><b class="nav-badge" data-badge="rate"></b></div>{% endif %}
      <div class="more-item" data-tab="broadcast" data-more-slot="broadcast" onclick="showTab('broadcast'); closeMore();"><i class="fa-solid fa-bullhorn"></i><span>{{ T.tab_broadcast }}</span></div>
      {% if sms_enabled %}<div class="more-item" data-tab="sms" data-more-slot="sms" onclick="showTab('sms'); closeMore();"><i class="fa-solid fa-comment-sms"></i><span>{{ T.tab_sms }}</span></div>{% endif %}
      <div class="more-item" data-tab="course" data-more-slot="course" onclick="showTab('course'); closeMore();"><i class="fa-solid fa-graduation-cap"></i><span>{{ T.tab_course }}</span></div>
      <div class="more-item" data-tab="help" data-more-slot="help" onclick="showTab('help'); closeMore();"><i class="fa-solid fa-circle-question"></i><span>{{ T.tab_help }}</span></div>
      {% if not is_employee %}<div class="more-item" data-tab="export" data-more-slot="export" onclick="showTab('export'); closeMore();"><i class="fa-solid fa-file-arrow-down"></i><span>{{ T.tab_export }}</span></div>{% endif %}
      {% if not is_employee %}<div class="more-item" data-tab="staff" data-more-slot="staff" onclick="showTab('staff'); closeMore();"><i class="fa-solid fa-user-group"></i><span>{{ T.tab_staff }}</span></div>{% endif %}
      {% if not is_employee %}<div class="more-item" data-tab="myshop" data-more-slot="myshop" onclick="showTab('myshop'); closeMore();"><i class="fa-solid fa-store"></i><span>{{ T.tab_myshop }}</span></div>{% endif %}
      {% if is_sub_owner %}<a class="more-item" href="/subscription"><i class="fa-solid fa-credit-card"></i><span>{{ T.sub_menu }}</span></a>{% endif %}
      {% if is_sub_owner %}<a class="more-item" href="/referral"><i class="fa-solid fa-gift"></i><span>{{ T.ref_menu }}</span></a>{% endif %}
      <a class="more-item more-install" href="/app?lang={{ lang }}"><i class="fa-solid fa-mobile-screen-button"></i><span>{{ T.inst_menu }}</span></a>
      {% if tg_bot_username %}<a class="more-item tg-only-out" href="https://t.me/{{ tg_bot_username }}?start=panel" target="_blank" rel="noopener"><i class="fa-brands fa-telegram"></i><span>{{ T.tg_open_menu }}</span></a>{% endif %}
      <div class="more-item" onclick="glToggle()"><i class="fa-solid fa-circle-half-stroke"></i><span class="gl-on-only">{{ T.theme_to_classic }}</span><span class="gl-off-only">{{ T.theme_to_glass }}</span></div>
      <div class="more-item" onclick="switchLanguage()"><i class="fa-solid fa-language"></i><span>{{ T.lang_switch }}</span></div>
      <a class="more-item more-logout" href="/logout"><i class="fa-solid fa-arrow-right-from-bracket"></i><span>{{ T.logout }}</span></a>
  </div>
</div>

<div class="container">
  <div class="topbar">
    <div style="display:flex; align-items:center; gap:10px; min-width:0;">
      <div class="logo-badge"><i class="fa-solid fa-droplet"></i></div>
      <div style="min-width:0;">
        <h1>{{ shop_name }}</h1>
        <div class="logo-sub brand-line"><span class="wordmark"><span class="wm-oil">Oil</span><span class="wm-book">Book</span></span>{% if is_employee %} · <span class="role-tag">{{ T.role_employee }}</span>{% elif is_branch %} · <span class="role-tag">{{ T.role_branch }}</span>{% endif %}</div>
      </div>
    </div>
    <button class="lang-btn" onclick="switchLanguage()">{{ T.lang_switch_short }}</button>
  </div>

  {% if sub_banner %}{% if sub_banner.link %}<a class="sub-banner{% if sub_banner.ro %} ro{% endif %}" href="/subscription"><i class="fa-solid fa-credit-card"></i><span>{{ sub_banner.text }}</span><i class="fa-solid fa-chevron-right"></i></a>{% else %}<div class="sub-banner{% if sub_banner.ro %} ro{% endif %}"><i class="fa-solid fa-circle-info"></i><span>{{ sub_banner.text }}</span></div>{% endif %}{% endif %}
  <div id="msg"></div>

  <div id="view-add" class="add-form{% if sub_ro %} ro-mode{% endif %}">
    {% if sub_ro %}
    <div class="ro-pay" id="roPay">
      <div class="ro-ic"><i class="fa-solid fa-eye"></i></div>
      <h2>{{ sub_ro.title }}</h2>
      <p>{{ sub_ro.text }}</p>
      {% if sub_ro.offer %}<div class="ro-offer">{{ sub_ro.offer }}</div>{% endif %}
      {% if sub_ro.owner %}<a class="ro-btn" href="/subscription"><i class="fa-solid fa-credit-card"></i><span>{{ T.ro_pay_btn }}</span></a>{% endif %}
      <button type="button" class="ro-btn ghost" onclick="showTab('table')"><i class="fa-solid fa-car"></i><span>{{ T.ro_view_btn }}</span></button>
    </div>
    <script>
    window.OB_RO = true;
    window.obShowRo = function () {
      if (document.getElementById('roSheetBg')) return;
      const bg = document.createElement('div');
      bg.className = 'ro-sheet-bg'; bg.id = 'roSheetBg';
      const box = document.getElementById('roPay').cloneNode(true);
      box.removeAttribute('id'); box.className = 'ro-pay ro-sheet';
      const view = box.querySelector('button.ghost');
      if (view) { view.textContent = {{ T.ro_sheet_close|tojson }}; view.onclick = function () { bg.remove(); }; }
      bg.appendChild(box);
      bg.addEventListener('click', function (e) { if (e.target === bg) bg.remove(); });
      document.body.appendChild(bg);
    };
    </script>
    {% endif %}
    <div class="af-title"><span class="dot"></span>{{ T.tab_add }}<span class="af-keys">{{ T.rcpt_keys }}</span></div>

    <div class="af-main">
    <div class="af-sec">
      <div class="af-h"><i class="fa-solid fa-car"></i>{{ T.af_car }}</div>
      <div class="field">
        <label><i class="fa-solid fa-id-card"></i>{{ T.field_plate }}</label>
        <div class="plate-wrap">
          <span class="plate-chip">UZ</span>
          <input id="plate" placeholder="01A123BC" oninput="onPlateInput()" onblur="onPlateBlur()" autocomplete="off" autocapitalize="characters" spellcheck="false" enterkeyhint="next">
          <button type="button" class="ps-cam-btn" onclick="openPlateScanner()" title="{{ T.ps_btn_title }}" aria-label="{{ T.ps_btn_title }}"><i class="fa-solid fa-camera"></i></button>
          <div id="plateSuggest" class="plate-suggest" style="display:none;"></div>
        </div>
        <div id="knownClientPanel"></div>
      </div>
      <div class="af-owner" id="afOwner">
      <div class="field">
        <label><i class="fa-solid fa-user"></i>{{ T.field_owner_name }}</label>
        <input id="owner_name" placeholder="Имя Фамилия">
      </div>
      <div class="field">
        <label><i class="fa-solid fa-phone"></i>{{ T.field_owner_phone }}</label>
        <input id="owner_phone" type="tel" inputmode="tel" placeholder="+998 90 123 45 67" enterkeyhint="next">
        <div class="hint-text">{{ T.hint_owner_phone }}</div>
      </div>
      <div class="row2" style="margin-bottom:-10px;">
        <div class="field">
          <label><i class="fa-solid fa-car"></i>{{ T.field_car_brand }}</label>
          <select id="car_brand" onchange="onBrandChange()">
            {% for b in brands %}<option value="{{b}}">{{b}}</option>{% endfor %}
          </select>
        </div>
        <div class="field">
          <label><i class="fa-solid fa-car-side"></i>{{ T.field_car_model }}</label>
          <input id="car_model" placeholder="Cobalt, Nexia, Malibu..." oninput="specSchedule(); renderQuickModels()" autocomplete="off">
        </div>
      </div>
      <div class="qm-row" id="quickModels"></div>
      <div id="presetBox" class="preset-box" hidden></div>
      <input id="vin" type="hidden" value="">
      <div id="vinHint" hidden></div>
      <div id="specCard" hidden></div>
      <a class="oil-lesson" href="/course/4"><i class="fa-solid fa-graduation-cap"></i><span>{{ T.oil_lesson_link }}</span><i class="fa-solid fa-chevron-right"></i></a>
      </div>
    </div>

    <div class="af-sec af-mil" id="afMil">
      <div class="af-h"><i class="fa-solid fa-gauge-high"></i>{{ T.af_mileage }}</div>
      <div class="mil-grid">
        <div>
          <div class="mil-l">{{ T.mil_now }}</div>
          <div class="mil-f"><input id="mileage" type="number" inputmode="numeric" placeholder="45000" oninput="checkMileageVsDue(); applyKmStep(); applyDailyKm()" enterkeyhint="next"><span>{{ T.km_short }}</span></div>
        </div>
        <div class="mil-arrow"><i class="fa-solid fa-arrow-right"></i></div>
        <div>
          <div class="mil-l">{{ T.mil_next }}</div>
          <div class="mil-f accent"><input id="next_mileage" type="number" inputmode="numeric" placeholder="55000" oninput="KM.manual = true; applyDailyKm()" enterkeyhint="next"><span>{{ T.km_short }}</span></div>
        </div>
      </div>
      <div id="mileageCompare"></div>
      <div class="km-chips km-seg" id="kmChips"></div>
      <div class="mil-daily">
      <div class="mil-l" style="margin-top:12px;">{{ T.daily_km_label }}</div>
      <div class="mil-f"><input id="daily_km" type="number" inputmode="numeric" placeholder="{{ T.daily_km_ph }}" oninput="DK.intervalManual = false; applyDailyKm()" enterkeyhint="next"><span>{{ T.km_per_day }}</span></div>
      </div>
      <div class="mil-int">
      <div class="mil-l" style="margin-top:12px;">{{ T.field_interval }}</div>
      <div style="display:flex; gap:8px;">
        <input id="interval_value" type="number" placeholder="3" value="3" style="flex:1;" oninput="DK.intervalManual = true; applyDailyKm()">
        <select id="interval_unit" style="flex:1;" onchange="DK.intervalManual = true; applyDailyKm()">
          <option value="months">{{ T.unit_months }}</option>
          <option value="days">{{ T.unit_days }}</option>
        </select>
      </div>
      </div>
      <div id="dkSuggest"></div>
      <div id="dkHint" class="dk-hint"></div>
    </div>

    <!-- Пробег и срок напоминания живут внутри окон «Моторное масло» и «АКПП»:
         блоки переносятся туда при открытии окна и возвращаются сюда (скрыто) -->
    <div id="csHold" hidden>
      <div class="af-sec af-atf" id="afAtf">
        <div class="af-h"><i class="fa-solid fa-gears"></i>{{ T.atf_block_title }}</div>
        <div class="mil-grid">
          <div>
            <div class="mil-l">{{ T.mil_now }}</div>
            <div class="mil-f"><input id="atf_cur" type="number" inputmode="numeric" placeholder="45000" oninput="atfCurInput()"><span>{{ T.km_short }}</span></div>
          </div>
          <div class="mil-arrow"><i class="fa-solid fa-arrow-right"></i></div>
          <div>
            <div class="mil-l">{{ T.atf_next_label }}</div>
            <div class="mil-f accent"><input id="atf_next_mileage" type="number" inputmode="numeric" placeholder="85000" oninput="ATF.manual = true"><span>{{ T.km_short }}</span></div>
          </div>
        </div>
        <div class="mil-l" style="margin-top:12px;">{{ T.atf_interval_label }}</div>
        <div style="display:flex; gap:8px; align-items:center;">
          <input id="atf_interval" type="number" inputmode="numeric" min="1" max="60" value="6" style="flex:1;">
          <span>{{ T.unit_months }}</span>
        </div>
      </div>
    </div>

    <div class="af-sec af-items">
      <div class="af-h"><i class="fa-solid fa-oil-can"></i>{{ T.af_items }}</div>
      <div class="cat-tiles" id="catTiles"></div>
      <div class="it-rcpt" id="itRcpt"></div>
      <div class="af-legacy" aria-hidden="true">
      {% if warehouse_enabled %}
      <div class="field pick-search">
        <input id="pickSearch" type="search" placeholder="🔍 {{ T.pick_search_ph }}" aria-label="{{ T.pick_search_label }}" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="search" oninput="renderPickResults('main')" onkeydown="onPickKey(event, 'main')">
        <div id="pickResults" class="pick-results"></div>
      </div>
      {% endif %}
      <div id="fluidsList"></div>
      <div class="af-sub">{{ T.af_filters_title }}</div>
      <div class="flt-tiles" id="filterTiles"></div>
      <div id="filtersList"></div>
      <div class="af-add" id="itemAddChips"></div>
      <div class="af-sub">{{ T.section_other }}</div>
      <button type="button" class="labor-btn" onclick="addLabor()"><i class="fa-solid fa-screwdriver-wrench"></i> {{ T.labor_btn }}</button>
      <div class="row2">
        <div class="field">
          <input id="other_name" placeholder="{{ T.field_other_name_ph }}" aria-label="{{ T.field_other_name }}">
        </div>
        <div class="field" style="flex:0 0 38%;">
          <input id="other_price" type="number" placeholder="{{ T.field_price }}" aria-label="{{ T.field_price }}" oninput="updateTotal()">
        </div>
      </div>
      {% if warehouse_enabled %}
      <div class="af-sub">{{ T.wh_other_stock_title }}</div>
      <div id="otherStockRows"></div>
      <button type="button" class="af-ghost" onclick="addOtherStockRow('other')">{{ T.wh_add_row }}</button>
      {% endif %}
      </div>
    </div>
    </div>

    <div class="af-side">
    <div class="af-rcpt" aria-live="polite">
      <div class="af-rcpt-h"><span>{{ T.rcpt_title }}</span><b id="rcptPlate"></b></div>
      <div id="rcptLines"><div class="rcpt-empty">{{ T.rcpt_empty }}</div></div>
    </div>
    <div class="af-sec af-pay">
      <div class="af-h"><i class="fa-solid fa-tag"></i>{{ T.disc_title }}</div>
      <div class="disc-seg" id="discSeg">
        <button type="button" data-p="0" class="on" onclick="setDiscount(0)">0%</button>
        <button type="button" data-p="5" onclick="setDiscount(5)">5%</button>
        <button type="button" data-p="10" onclick="setDiscount(10)">10%</button>
        <button type="button" data-p="c" onclick="setDiscountCustom()">{{ T.disc_custom }}</button>
      </div>
      <div id="discCustom" class="disc-custom" style="display:none;">
        <input id="disc_value" type="number" inputmode="decimal" placeholder="0" aria-label="{{ T.disc_title }}" oninput="onDiscInput()">
        <div class="disc-unit">
          <button type="button" data-u="pct" class="on" onclick="setDiscUnit('pct')">%</button>
          <button type="button" data-u="sum" onclick="setDiscUnit('sum')">{{ T.currency }}</button>
        </div>
      </div>
      <div id="discSummary" class="disc-sum" style="display:none;"></div>
      <div class="af-h" style="margin-top:16px;"><i class="fa-solid fa-wallet"></i>{{ T.af_payment }}</div>
      <div class="pay-seg" id="paySeg">
        <button type="button" data-m="cash" class="on" onclick="setPayMode('cash')"><i class="fa-solid fa-money-bill"></i> {{ T.payment_cash }}</button>
        <button type="button" data-m="card" onclick="setPayMode('card')"><i class="fa-solid fa-credit-card"></i> {{ T.payment_card }}</button>
        <button type="button" data-m="mix" onclick="setPayMode('mix')">{{ T.pay_mode_mix }}</button>
        <button type="button" data-m="debt" onclick="setPayMode('debt')">{{ T.pay_mode_debt }}</button>
      </div>
      <div id="payInputs" style="display:none; margin-top:10px;">
        <div class="row2">
          <div class="field">
            <label style="font-size:11px;"><i class="fa-solid fa-money-bill"></i> {{ T.payment_cash }}</label>
            <input id="pay_cash" type="number" placeholder="0" oninput="onPayCashInput()">
          </div>
          <div class="field">
            <label style="font-size:11px;"><i class="fa-solid fa-credit-card"></i> {{ T.payment_card }}</label>
            <input id="pay_card" type="number" placeholder="0" oninput="onPayCardInput()">
          </div>
        </div>
      </div>
      <div style="display:none;">
        <input type="checkbox" id="debt_enabled" onchange="toggleDebtSection()">
      </div>
      <div id="debtFields" style="display:none; margin-top:4px; padding:12px; background:var(--field-bg); border:1.5px dashed var(--border); border-radius:12px;">
        <div class="field">
          <label style="font-size:11px;">{{ T.debt_remaining_label }}</label>
          <div id="debtRemaining" style="font-size:18px; font-weight:700; color:var(--btn); font-family:var(--font-mono);">0</div>
        </div>
        <div class="row2" style="margin-bottom:-10px;">
          <div class="field">
            <label style="font-size:11px;">{{ T.debt_installment_amount }}</label>
            <input id="debt_installment_amount" type="number" placeholder="100000">
          </div>
          <div class="field">
            <label style="font-size:11px;">{{ T.debt_interval_days }}</label>
            <input id="debt_interval_days" type="number" placeholder="14">
          </div>
        </div>
        <div class="af-sub" style="margin-top:14px;">{{ T.debt_term_label }}</div>
        <div class="debt-terms" id="debtTerms">
          <button type="button" data-d="7" onclick="setDebtTerm(7)">{{ T.debt_1w }}</button>
          <button type="button" data-d="14" onclick="setDebtTerm(14)">{{ T.debt_2w }}</button>
          <button type="button" data-d="30" onclick="setDebtTerm(30)">{{ T.debt_1m }}</button>
        </div>
      </div>
      {% if is_employee or has_staff %}<div class="af-sub" style="margin-top:14px;">{{ T.team_master }}</div>
      <select id="master_id"></select>{% endif %}
      <div class="af-sub" style="margin-top:14px;">{{ T.field_notes }}</div>
      <textarea id="notes" rows="2" placeholder="{{ T.notes_ph }}"></textarea>
      <div class="notes-shared-hint"><i class="fa-solid fa-eye"></i> {{ T.notes_shared_hint }}</div>
    </div>

    <div class="af-bar">
      <div class="af-bar-total" onclick="openReceiptSheet()" role="button" tabindex="0"><span id="barCount">{{ T.field_total }}</span><b id="totalCost">0</b></div>
      <button class="af-save" onclick="submitCar()"><i class="fa-solid fa-check"></i> {{ T.btn_save }}<kbd class="af-kbd">{{ T.kbd_save }}</kbd></button>
    </div>
    </div>
  </div>

  <!-- шторки формы замены (телефон) и экран «Сохранено» -->
  <div class="ob-sheet-bg" id="obSheetBg" onclick="closeObSheets()"></div>
  <div class="ob-sheet" id="catSheet" role="dialog" aria-modal="true" aria-labelledby="cs_title">
    <div class="ob-sheet-h"><b id="cs_title"></b><button type="button" class="ob-sheet-x" onclick="closeObSheets()" aria-label="{{ T.close }}">✕</button></div>
    <div class="ob-sheet-body">
      <div class="cs-tabs" id="cs_tabs"></div>
      <div id="cs_extra"></div>
      <input id="cs_search" class="ps-search" type="search" autocomplete="off" autocapitalize="off" spellcheck="false" oninput="renderCatSheet()">
      <div id="cs_body"></div>
    </div>
    <div class="ob-sheet-foot" id="cs_foot"></div>
  </div>
  <div class="ob-sheet" id="pickSheet" role="dialog" aria-modal="true" aria-labelledby="pickSheetTitle">
    <div class="ob-sheet-h"><b id="pickSheetTitle"></b><button type="button" class="ob-sheet-x" onclick="closeObSheets()" aria-label="{{ T.close }}">✕</button></div>
    <div class="ob-sheet-body">
      <input id="pickSheetSearch" class="ps-search" type="search" placeholder="🔍 {{ T.pick_search_ph }}" autocomplete="off" autocapitalize="off" spellcheck="false" oninput="renderPickSheet()">
      <div id="pickSheetList"></div>
    </div>
    <div class="ob-sheet-foot" id="pickSheetFoot"></div>
  </div>
  <div class="ob-sheet" id="rcSheet" role="dialog" aria-modal="true" aria-labelledby="rcSheetTitle">
    <div class="ob-sheet-h"><b id="rcSheetTitle">{{ T.rcpt_title }}</b><span id="rcSheetPlate" style="font-family:var(--font-mono); color:var(--hint); margin-top:6px;"></span><button type="button" class="ob-sheet-x" onclick="closeObSheets()" aria-label="{{ T.close }}">✕</button></div>
    <div class="ob-sheet-body">
      <div id="rcSheetLines"></div>
      <button type="button" class="labor-btn" style="margin-top:10px;" onclick="closeObSheets(); addLabor()"><i class="fa-solid fa-screwdriver-wrench"></i> {{ T.labor_btn }}</button>
      <div class="rc-total"><span>{{ T.field_total }}</span><b id="rcSheetTotal">0</b></div>
      <div id="rcPayHost"></div>
    </div>
    <div class="ob-sheet-foot"><button type="button" class="af-save" style="width:100%; padding:16px;" onclick="closeObSheets(); submitCar()"><i class="fa-solid fa-check"></i> {{ T.btn_save }}</button></div>
  </div>
  <div class="sv-wrap" id="savedScreen" hidden role="dialog" aria-modal="true" aria-labelledby="svTitle">
    <div class="sv-in">
      <div class="sv-ok" id="svOk"><i class="fa-solid fa-check"></i></div>
      <div class="sv-badge" id="svBadge" hidden><i class="fa-solid fa-check"></i> {{ T.sv_title }}</div>
      <div class="sv-title" id="svTitle">{{ T.sv_title }}</div>
      <div class="sv-sub" id="svSub"></div>
      <div class="sv-qrbox" id="svQrBox" hidden>
        <img id="svQrImg" alt="QR">
        <div class="sv-qrhint">{{ T.sv_qr_hint }}</div>
      </div>
      <div id="svSend"></div>
      <button type="button" class="sv-next" id="svNext" onclick="closeSaved(true)">+ {{ T.sv_next_car }}</button>
      <button type="button" class="sv-more" id="svMore" hidden onclick="toggleSavedDetails()"><span>{{ T.sv_details }}</span> <i class="fa-solid fa-chevron-down"></i></button>
      <div class="sv-card" id="svCard"></div>
      <div class="sv-row">
        <button type="button" onclick="closeSaved(false)">{{ T.close }}</button>
        <button type="button" class="sv-undo" id="svUndo" onclick="undoSaved()"></button>
      </div>
    </div>
  </div>

  <div id="view-table" style="display:none;">
    <div id="baseDue"></div>
    <div id="baseClientCount" style="font-size:13px; color:var(--hint); margin-bottom:8px;"></div>
    <div style="position:relative;">
      <input class="search" id="search" type="search" name="oilbook_base_q" autocomplete="off" autocapitalize="off" spellcheck="false" data-lpignore="true" placeholder="{{ T.search_ph }}" oninput="onBaseSearch(); toggleSearchClearBtn();" style="padding-right:40px;">
      <button type="button" id="searchClearBtn" onclick="clearSearch()" style="display:none; position:absolute; right:10px; top:50%; transform:translateY(-50%); background:none; border:none; color:var(--hint); font-size:18px; cursor:pointer; padding:4px 6px;">✕</button>
    </div>
    <div id="clientCardPanel" style="display:none; margin-bottom:12px;"></div>
    <div id="table-body"></div>
  </div>

  <div id="view-debts" style="display:none;">
    <div id="debtsSummary" class="dsum"></div>
    <div class="dtabs">
      <button type="button" id="dtab_active" class="on" onclick="setDebtTab('active')">{{ T.debts_tab_active }}</button>
      <button type="button" id="dtab_closed" onclick="setDebtTab('closed')">{{ T.debts_tab_closed }}</button>
    </div>
    <div id="debtsList"></div>
  </div>

  {% if not is_employee %}
  <div id="view-rate" style="display:none;">
    <div class="card">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.usd_rate_title }}</label>
      <div class="hint-text" id="rateScope" style="margin:0 0 12px;"></div>
      <div class="rate-now"><span>1 $ =</span><b id="rateNow">—</b><span>{{ T.currency }}</span></div>
      {% if not is_branch %}
      <div class="field" style="margin-top:12px;">
        <label>{{ T.usd_rate_new }}</label>
        <input id="rate_input" type="number" inputmode="decimal" step="0.01" placeholder="12100">
      </div>
      <button class="submit" id="rateSaveBtn" onclick="saveNetworkRate()">{{ T.usd_rate_save }}</button>
      {% endif %}
      <div id="rateHistory" style="margin-top:14px;"></div>
    </div>
    {% if not is_branch %}
    <div class="card" id="rateSetupCard" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.usd_setup_title }}</label>
      <div class="hint-text" style="margin:0 0 10px;">{{ T.usd_setup_hint }}</div>
      <div id="rateSetupBanner"></div>
      <div class="field">
        <label>{{ T.usd_setup_entered }}</label>
        <input id="rate_setup_entered" type="number" inputmode="decimal" step="0.01" placeholder="11800">
      </div>
      <div class="wh-search" style="margin-bottom:8px;"><i class="fa-solid fa-magnifying-glass"></i><input id="rateSetupSearch" placeholder="{{ T.whs_search }}" oninput="renderRateSetup()" autocomplete="off"></div>
      <div style="display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap;">
        <button class="wh-tbtn wh-tbtn-sm" onclick="rateSetupSelect(true)">{{ T.usd_setup_all }}</button>
        <button class="wh-tbtn wh-tbtn-sm" onclick="rateSetupSelect(false)">{{ T.usd_setup_none }}</button>
        <span class="hint-text" id="rateSetupCount" style="margin:0; align-self:center;"></span>
      </div>
      <div id="rateSetupList"></div>
      <button class="submit" id="rateSetupBtn" onclick="saveRateSetup()" style="margin-top:12px;">{{ T.usd_setup_save }}</button>
    </div>
    <div class="modal-overlay" id="ratePriceModal">
      <div class="modal modal-wide" style="text-align:left;">
        <h3 style="text-align:center; margin-top:0;" id="rpTitle"></h3>
        <div class="hint-text" id="rpSub" style="text-align:center; margin:-6px 0 12px;"></div>
        <div style="display:flex; gap:8px; margin-bottom:8px;">
          <button class="wh-tbtn wh-tbtn-sm" onclick="rpSelect(true)">{{ T.usd_setup_all }}</button>
          <button class="wh-tbtn wh-tbtn-sm" onclick="rpSelect(false)">{{ T.usd_setup_none }}</button>
        </div>
        <div id="rpList"></div>
        <div class="hint-text" style="margin:8px 0 0;">{{ T.usd_rp_round }}</div>
        <button class="submit" id="rpApplyBtn" onclick="applyRatePrices()">{{ T.usd_rp_apply }}</button>
        <button class="close-btn" onclick="closeWhModal('ratePriceModal')">{{ T.usd_rp_later }}</button>
      </div>
    </div>
    {% endif %}
    <div class="card" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:8px;">{{ T.usd_how_title }}</label>
      <div class="rate-how">{{ T.usd_how_html|safe }}</div>
    </div>
  </div>
  {% endif %}

  {% if not is_employee %}
  <div id="view-expenses" style="display:none;">

    <div class="card">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.expense_add_title }}</label>
      <div class="field">
        <label>{{ T.expense_category_label }}</label>
        <select id="exp_category" onchange="onExpenseCategoryChange('exp_category', 'exp_category_custom')"></select>
        <input id="exp_category_custom" placeholder="{{ T.expense_custom_category_ph }}" style="display:none; margin-top:6px;">
      </div>
      <div class="field">
        <label>{{ T.expense_name_label }}</label>
        <input id="exp_name" placeholder="{{ T.expense_name_ph }}">
      </div>
      <div class="row2">
        <div class="field">
          <label>{{ T.expense_amount_label }}</label>
          <input id="exp_amount" type="number" placeholder="100000" oninput="onSumFieldEdited('exp_amount', 'exp_amount_usd')">
        </div>
        <div class="field">
          <label>{{ T.usd_price_label }}</label>
          <input id="exp_amount_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('exp_amount_usd', 'exp_amount')">
        </div>
      </div>
      <button class="submit" onclick="submitExpense()">{{ T.expense_add_btn }}</button>
    </div>

    <div class="card" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.expense_recurring_title }}</label>
      <div id="recurringExpensesList"></div>
      <div style="margin-top:10px; padding-top:10px; border-top:1px dashed var(--border);">
        <div class="field">
          <label>{{ T.expense_category_label }}</label>
          <select id="rec_category" onchange="onExpenseCategoryChange('rec_category', 'rec_category_custom')"></select>
          <input id="rec_category_custom" placeholder="{{ T.expense_custom_category_ph }}" style="display:none; margin-top:6px;">
        </div>
        <div class="field">
          <label>{{ T.expense_name_label }}</label>
          <input id="rec_name" placeholder="{{ T.expense_recurring_name_ph }}">
        </div>
        <div class="row2">
          <div class="field">
            <label>{{ T.expense_amount_label }}</label>
            <input id="rec_amount" type="number" placeholder="2000000" oninput="onSumFieldEdited('rec_amount', 'rec_amount_usd')">
          </div>
          <div class="field">
            <label>{{ T.expense_day_of_month_label }}</label>
            <input id="rec_day" type="number" min="1" max="28" placeholder="5">
          </div>
        </div>
        <div class="field">
          <label>{{ T.usd_price_label }}</label>
          <input id="rec_amount_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('rec_amount_usd', 'rec_amount')">
        </div>
        <button class="submit" onclick="createRecurringExpense()">{{ T.expense_recurring_add_btn }}</button>
      </div>
    </div>

    <div class="card" style="margin-top:14px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.expense_journal_title }}</label>
      <div id="expensesJournal">{{ T.stats_loading }}</div>
    </div>
  </div>
  {% endif %}

  <div id="view-broadcast" class="card" style="display:none;">
    <div class="field">
      <label>{{ T.broadcast_msg_label }}</label>
      <textarea id="broadcast_message" rows="5" placeholder="{{ T.broadcast_msg_ph }}"></textarea>
      <div class="hint-text" id="broadcastRecipients">{{ T.broadcast_loading_recipients }}</div>
    </div>
    <button class="submit" onclick="sendBroadcast()">{{ T.broadcast_send_btn }}</button>
    <div style="margin-top:18px;">
      <div class="hint-text" style="margin-bottom:8px;">{{ T.broadcast_history_title }}</div>
      <div id="broadcastHistory"></div>
    </div>
  </div>

  <div id="view-course" style="display:none;">
    <div class="course-wrap">
      <div class="course-top" id="courseTop">
        <div class="course-sub">{{ T.course_sub }}</div>
        <div class="course-head" id="courseHead">&nbsp;</div>
        {% if lang != 'uz' %}<div class="course-note">{{ T.course_lang_note }}</div>{% endif %}
        <div class="course-prog" id="courseProg" hidden><span id="courseProgN"></span><i><b id="courseProgBar"></b></i></div>
      </div>
      <div class="course-map" id="courseMap"></div>
      <div class="course-list" id="courseList"></div>
      <div id="courseBonus"></div>
    </div>
  </div>

  <div id="view-help" style="display:none;">
""" + HELP_VIEW + """
  </div>

  <div id="view-cash" style="display:none;">
    {% if is_employee %}
    <div id="cashMy">{{ T.stats_loading }}</div>
    {% else %}
    <div id="cashOwner">{{ T.stats_loading }}</div>
    <div class="modal-overlay" id="cashAcceptModal" onclick="if (event.target === this) closeCashAccept()">
      <div class="modal modal-wide" style="text-align:left;">
        <div class="cash-m-title">{{ T.cash_modal_title }}</div>
        <div class="cash-m-who" id="cashAccWho"></div>
        <div class="cash-m-exp"><span>{{ T.cash_modal_expected }}</span><b id="cashAccExp"></b></div>
        <label for="cashAccAmount">{{ T.cash_modal_got }}</label>
        <input id="cashAccAmount" type="text" inputmode="numeric" autocomplete="off" oninput="cashAccInput()">
        <div class="hint-text" id="cashAccRest" style="min-height:18px;"></div>
        <label for="cashAccNote">{{ T.cash_modal_note }}</label>
        <input id="cashAccNote" maxlength="200" autocomplete="off">
        <button class="submit cash-ok-btn" id="cashAccBtn" onclick="submitCashAccept()"></button>
        <button class="submit" style="background:#E2E8F0; color:#334155;" onclick="closeCashAccept()">{{ T.cancel }}</button>
      </div>
    </div>
    {% endif %}
  </div>

  {% if team_on %}
  <div id="view-team" style="display:none;">
    <div id="teamBox">{{ T.stats_loading }}</div>
    {% if not is_employee %}
    <div class="modal-overlay" id="teamModal" onclick="if (event.target === this) closeTeamModal()">
      <div class="modal modal-wide" style="text-align:left;">
        <div id="teamModalBody"></div>
        <button class="submit" style="background:#E2E8F0; color:#334155;" onclick="closeTeamModal()">{{ T.team_close }}</button>
      </div>
    </div>
    {% endif %}
  </div>
  {% endif %}
  {% if not is_employee %}
  <div id="view-staff" style="display:none;">
    <div class="card">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:6px;">{{ T.staff_add_title }}</label>
      <div class="hint-text" style="margin-bottom:12px;">{{ T.staff_intro }}</div>
      <label for="staff_name">{{ T.staff_name }}</label>
      <input id="staff_name" maxlength="60" placeholder="{{ T.staff_name_ph }}" autocomplete="off">
      <div class="staff-err" id="staff_err_full_name"></div>
      <label for="staff_login">{{ T.staff_login }}</label>
      <input id="staff_login" maxlength="30" placeholder="{{ T.staff_login_ph }}" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false">
      <div class="hint-text">{{ T.staff_login_hint }}</div>
      <div class="staff-err" id="staff_err_username"></div>
      <label for="staff_pw">{{ T.staff_password }}</label>
      <input id="staff_pw" maxlength="100" autocomplete="new-password">
      <div class="hint-text">{{ T.staff_password_hint }}</div>
      <div class="staff-err" id="staff_err_password"></div>
      <button class="submit" onclick="createStaff()">{{ T.staff_add_btn }}</button>
      <div id="staffCreds"></div>
    </div>
    <div class="card" style="margin-top:16px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.staff_list_title }}</label>
      <div id="staffList">{{ T.stats_loading }}</div>
    </div>
    <div class="card" style="margin-top:16px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.alog_title }}</label>
      <div class="hint-text" style="margin:0 0 10px;">{{ T.alog_hint }}</div>
      <div id="actionLog">{{ T.stats_loading }}</div>
    </div>
  </div>

  <div id="view-myshop" style="display:none;">
    <div class="card"><div class="hint-text" style="margin:0;">{{ T.myshop_intro }}</div></div>
    <div id="myshopList">{{ T.stats_loading }}</div>
  </div>

  <div id="view-export" class="card" style="display:none;">
    <p style="margin-top:0;">{{ T.export_p1 }}</p>
    <p class="hint-text">{{ T.export_p2 }}</p>
    <button class="submit" onclick="obDownload('/api/export')">{{ T.export_btn }}</button>
    <button class="submit" style="background:#1a7a3d; margin-top:8px;" onclick="obDownload('/api/export_excel')">{{ T.export_excel_btn }}</button>
    <p class="hint-text">{{ T.export_excel_hint }}</p>
  </div>

  <div id="view-stats" style="display:none;">
    <div class="subtabs">
      <div class="subtab active" id="substat-own" onclick="showStatsSubTab('own')">{{ T.stats_sub_own }}</div>
      <div class="subtab" id="substat-branches" onclick="showStatsSubTab('branches')" style="display:none;">{{ T.stats_sub_branches }}</div>
    </div>

    <div id="statsOwnView">
      <div id="statsGrid">{{ T.stats_loading }}</div>

      <div class="modal-overlay" id="dayDetailsModal" onclick="if (event.target === this) closeWhModal('dayDetailsModal')">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;"><i class="fa-solid fa-list-check" style="color:#0F52BA;"></i> {{ T.dd_title }}</h3>
          <div class="dd-date"><input type="date" id="ddDate" onchange="loadDayDetails(this.value)"></div>
          <div id="ddBody">{{ T.stats_loading }}</div>
          <button class="close-btn" onclick="closeWhModal('dayDetailsModal')">{{ T.modal_close }}</button>
        </div>
      </div>

      {% if not is_employee %}
      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.stats_brands_title }}</label>
        <div class="hint-text" style="margin-bottom:12px;">{{ T.stats_brands_hint }}</div>
        <div class="brand-period" id="brandPeriod"></div>
        <div class="brand-chips" id="brandCategoryChips"></div>
        <div id="brandBody">{{ T.stats_loading }}</div>
      </div>
      {% endif %}

      {% if not is_employee and not is_branch %}
      <div class="card" style="margin-top:16px; background:linear-gradient(135deg, #F0FDF4, #ECFDF5); border-color:#86EFAC;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_net_profit_title }}</label>
        <div id="dashNetProfit">{{ T.stats_loading }}</div>
      </div>
      {% endif %}

      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_revenue_chart_title }}</label>
        <div id="revenueSummary" class="rv-summary"></div>
        <div class="rv-chart-wrap"><canvas id="revenueChart"></canvas></div>
      </div>

      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_debt_summary_title }}</label>
        <div id="dashDebtSummary">{{ T.stats_loading }}</div>
      </div>

      {% if warehouse_enabled and not is_employee %}
      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_low_stock_title }}</label>
        <div id="dashLowStock">{{ T.stats_loading }}</div>
      </div>
      {% endif %}

      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.stats_custom_title }}</label>
        <div id="statsPresets" style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px;"></div>
        <div class="row2">
          <div class="field">
            <label>{{ T.stats_from }}</label>
            <input id="stats_from" type="date">
          </div>
          <div class="field">
            <label>{{ T.stats_to }}</label>
            <input id="stats_to" type="date">
          </div>
        </div>
        <button class="submit" onclick="applyStatsRange()">{{ T.stats_apply }}</button>
        <div id="statsRangeResult" style="margin-top:14px;"></div>
      </div>
    </div>

    <div id="statsBranchesView" style="display:none;">
      <div id="statsAggregated">
        <div class="card">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.net_compare_title }}</label>
          <div class="hint-text" style="margin-bottom:12px;">{{ T.net_compare_hint }}</div>
          <div class="brand-period" id="netComparePeriod"></div>
          <div id="netCompareBody">{{ T.stats_loading }}</div>
          <div class="net-cmp-chart-wrap" id="netCompareChartWrap"><canvas id="netCompareChart"></canvas></div>
        </div>

        <div class="net-detail-head" id="netDetailHead">
          <div class="net-detail-title">{{ T.net_detail_title }}</div>
          <div class="brand-chips" id="netScopeChips"></div>
        </div>
        <div id="netStatsGrid">{{ T.stats_loading }}</div>

        <div class="card" style="margin-top:16px; background:linear-gradient(135deg, #F0FDF4, #ECFDF5); border-color:#86EFAC;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_net_profit_title }}</label>
          <div id="netNetProfit">{{ T.stats_loading }}</div>
        </div>

        <div class="card" style="margin-top:16px;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_revenue_chart_title }}</label>
          <div id="netRevenueSummary" class="rv-summary"></div>
          <div class="rv-chart-wrap"><canvas id="netRevenueChart"></canvas></div>
        </div>

        <div class="card" style="margin-top:16px;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.stats_brands_title }}</label>
          <div class="hint-text" style="margin-bottom:12px;">{{ T.stats_brands_hint }}</div>
          <div class="brand-period" id="netBrandPeriod"></div>
          <div class="brand-chips" id="netBrandCategoryChips"></div>
          <div id="netBrandBody">{{ T.stats_loading }}</div>
        </div>

        <div class="card" style="margin-top:16px;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_debt_summary_title }}</label>
          <div id="netDebtSummary">{{ T.stats_loading }}</div>
        </div>

        <div class="card" style="margin-top:16px;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.dash_low_stock_title }}</label>
          <div id="netLowStock">{{ T.stats_loading }}</div>
        </div>
      </div>

      <div class="card" style="margin-top:16px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.stats_custom_title }}</label>
        <div id="branchStatsPresets" style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px;"></div>
        <div class="row2">
          <div class="field">
            <label>{{ T.stats_from }}</label>
            <input id="branch_stats_from" type="date">
          </div>
          <div class="field">
            <label>{{ T.stats_to }}</label>
            <input id="branch_stats_to" type="date">
          </div>
        </div>
        <button class="submit" onclick="applyBranchStatsRange()">{{ T.stats_apply }}</button>
        <div id="branchStatsRangeResult" style="margin-top:14px;"></div>
        <div id="branchChartWrap" style="margin-top:16px; display:none;">
          <canvas id="branchChart" height="220"></canvas>
        </div>
      </div>
    </div>
  </div>
  {% endif %}

  {% if sms_enabled %}
  <div id="view-sms" class="card" style="display:none;">
    <p style="margin-top:0;">{{ T.sms_intro }}</p>
    <div class="field">
      <label>{{ T.sms_email }}</label>
      <input id="eskiz_email" value="{{ eskiz_email }}" placeholder="you@example.com" autocomplete="off">
    </div>
    <div class="field">
      <label>{{ T.sms_password }}</label>
      <input id="eskiz_password" type="password" autocomplete="new-password" placeholder="{{ T.sms_password_ph }}">
      <div class="hint-text">{{ T.sms_password_hint }}</div>
    </div>
    <button class="submit" onclick="saveSmsSettings()">{{ T.btn_save }}</button>
  </div>
  {% endif %}

  {% if warehouse_enabled and (not is_employee or store_enabled) %}
  <div id="view-warehouse" style="display:none;">

    {% if not is_employee %}
    <div class="subtabs">
      <div class="subtab active" id="subwh-own" onclick="showWhSubTab('own')">{{ T.st_sub_main if store_enabled else T.wh_sub_own }}</div>
      {% if store_enabled %}<div class="subtab" id="subwh-store" onclick="showWhSubTab('store')"><i class="fa-solid fa-store"></i> {{ T.st_tab }}<b class="nav-badge" id="stTabBadge"></b></div>{% endif %}
      <div class="subtab" id="subwh-branches" onclick="showWhSubTab('branches')" style="display:none;">{{ T.wh_sub_branches }}</div>
      <div class="subtab" id="subwh-network" onclick="showWhSubTab('network')" style="display:none;">{{ T.wh_sub_network }}</div>
    </div>
    {% endif %}
    {% if store_enabled %}
    <div id="whStoreView" style="display:{{ 'block' if is_employee else 'none' }};">
      <div class="card">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;"><i class="fa-solid fa-store" style="color:#0F52BA;"></i> {{ T.st_title }}</label>
        <div class="hint-text" style="margin-bottom:10px;">{{ T.st_hint_employee if is_employee else T.st_hint }}</div>
        <div class="wh-kpis" id="stKpis">{{ T.stats_loading }}</div>
        <div id="stAttention"></div>
        {% if not is_employee %}<button class="wh-tbtn wh-tbtn-primary wh-tbtn-wide" style="margin-top:10px;" onclick="openStoreMove()"><i class="fa-solid fa-dolly"></i> <span id="stMoveBtnText">{{ T.st_move_btn }}</span></button>{% endif %}
      </div>
      <div class="card" style="margin-top:14px;">
        <div class="wh-toolbar">
          <div class="wh-search"><i class="fa-solid fa-magnifying-glass"></i><input id="stSearch" placeholder="{{ T.whs_search }}" oninput="renderStoreCards()" autocomplete="off"></div>
        </div>
        <div id="stCards"></div>
      </div>
    </div>
    {% endif %}
    {% if not is_employee %}
    <div id="whOwnView">
      <div class="card" id="whSummaryCard">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.whs_title }}</label>
        <div class="wh-kpis" id="whKpis">{{ T.stats_loading }}</div>
        <div id="whAttention"></div>
      </div>

      <div class="card" style="margin-top:14px;">
        <div class="wh-toolbar">
          <div class="wh-search"><i class="fa-solid fa-magnifying-glass"></i><input id="whSearch" placeholder="{{ T.whs_search }}" oninput="renderProductCards()" autocomplete="off"></div>
          <button class="wh-tbtn wh-tbtn-primary" onclick="openAddProductModal()"><i class="fa-solid fa-plus"></i> {{ T.whs_add_short }}</button>
          <button class="wh-tbtn" title="{{ T.imp_title }}" onclick="openImportModal()"><i class="fa-solid fa-file-excel" style="color:#15803D;"></i> Excel</button>
        </div>
        <div class="brand-chips" id="whCatChips"></div>
        <div id="whCards"></div>
        <button class="wh-tbtn wh-tbtn-wide" id="whPurchaseBtn" onclick="openPurchaseList()"><i class="fa-solid fa-clipboard-list"></i> <span>{{ T.whs_purchase_list }}</span></button>
      </div>

      <div class="card" style="margin-top:14px;">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.whs_movements }}</label>
        <div id="restockHistory"></div>
      </div>



    </div>

    <div id="whNetworkView" style="display:none;">
      <div class="card">
        <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:4px;">{{ T.whn_title }}</label>
        <div class="hint-text" style="margin-bottom:12px;">{{ T.whn_hint }}</div>
        <div class="net-actions">
          <button class="wh-tbtn wh-tbtn-primary" onclick="openShipModal()"><i class="fa-solid fa-truck"></i> {{ T.shp_title }}</button>
          <button class="wh-tbtn" onclick="openCatalogModal()"><i class="fa-solid fa-copy"></i> {{ T.cat_title }}</button>
          <button class="wh-tbtn" onclick="openTransferModal({})"><i class="fa-solid fa-right-left"></i> {{ T.whn_transfer_one }}</button>
        </div>
        <div id="whNetMatrix">{{ T.stats_loading }}</div>
      </div>
    </div>

    <div id="whBranchesView" style="display:none;">
      <div id="branchWarehouseSummary" class="whn-summary" style="margin-bottom:12px;"></div>
      <div id="whbDetail" style="display:none;">
        <div class="card">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.whs_title }} — <span id="whbTitle"></span></label>
          <div class="wh-kpis" id="whbKpis"></div>
          <div id="whbAttention"></div>
        </div>
        <div class="card" style="margin-top:14px;">
          <div class="wh-toolbar">
            <div class="wh-search"><i class="fa-solid fa-magnifying-glass"></i><input id="whbSearch" placeholder="{{ T.whs_search }}" oninput="renderProductCards('br')" autocomplete="off"></div>
          </div>
          <div class="brand-chips" id="whbCatChips"></div>
          <div id="whbCards"></div>
          <button class="wh-tbtn wh-tbtn-wide" id="whbPurchaseBtn" onclick="openPurchaseList('br')"><i class="fa-solid fa-clipboard-list"></i> <span>{{ T.whs_purchase_list }}</span></button>
        </div>
        <div class="card" style="margin-top:14px;">
          <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">{{ T.whs_movements }}</label>
          <div id="whbHistory"></div>
        </div>
      </div>

    </div>
    {% endif %}

  </div>

  {% if store_enabled and not is_employee %}
  <div class="modal-overlay" id="storeMoveModal">
    <div class="modal modal-wide" style="text-align:left;">
      <h3 style="text-align:center; margin-top:0;"><i class="fa-solid fa-dolly" style="color:#0F52BA;"></i> {{ T.st_move_title }}</h3>
      <div class="hint-text" style="text-align:center; margin:-6px 0 10px;">{{ T.st_move_hint }}</div>
      <div class="wh-search" style="margin-bottom:8px;"><i class="fa-solid fa-magnifying-glass"></i><input id="smSearch" placeholder="{{ T.whs_search }}" oninput="renderStoreMoveRows()" autocomplete="off"></div>
      <div id="smRows" class="sm-rows"></div>
      <button class="submit" onclick="submitStoreMove()"><i class="fa-solid fa-dolly"></i> <span id="smSubmitText">{{ T.st_move_submit }}</span></button>
      <button class="close-btn" onclick="closeWhModal('storeMoveModal')">{{ T.modal_close }}</button>
    </div>
  </div>
  <div class="modal-overlay" id="storeQtyModal">
    <div class="modal" style="text-align:left;">
      <h3 style="text-align:center; margin-top:0;" id="sqTitle"></h3>
      <div class="hint-text" id="sqHint" style="text-align:center; margin:-6px 0 12px;"></div>
      <div class="field"><label id="sqLabel"></label><input id="sqQty" type="number" min="0" step="0.5" inputmode="decimal"></div>
      <div class="field" id="sqReasonWrap"><label>{{ T.whe_reason_label }}</label><input id="sqReason" placeholder="{{ T.whe_reason_ph }}"></div>
      <button class="submit" onclick="submitStoreQty()">{{ T.whe_save }}</button>
      <button class="close-btn" onclick="closeWhModal('storeQtyModal')">{{ T.modal_close }}</button>
    </div>
  </div>
  {% endif %}

  {% if warehouse_enabled and not is_employee and not is_branch %}
  <div id="view-suppliers" style="display:none;">
    <div class="sp-top">
      <h2>{{ T.tab_suppliers }}</h2>
      <button class="sp-pill" id="spRatePill" onclick="openSupRate()"></button>
      <div class="sp-menu-wrap">
        <button class="sp-icon" onclick="toggleSupMenu(event)" aria-label="{{ T.nav_more }}"><i class="fa-solid fa-ellipsis"></i></button>
        <div class="sp-menu" id="spMenu">
          <button onclick="closeSupMenu(); openSupplierModal();"><i class="fa-solid fa-plus"></i>{{ T.sp_menu_add }}</button>
          <button onclick="closeSupMenu(); openNewOrder();"><i class="fa-solid fa-cart-plus"></i>{{ T.ord_new }}</button>
          <button onclick="closeSupMenu(); openSupRate();"><i class="fa-solid fa-dollar-sign"></i>{{ T.usd_rate_title }}</button>
          <button onclick="closeSupMenu(); openSupArchive();"><i class="fa-solid fa-box-archive"></i><span id="spMenuArchive">{{ T.sp_archive }}</span></button>
        </div>
      </div>
    </div>
    <div id="spHero"></div>
    <div class="sp-list" id="supList"><div class="sp-empty">{{ T.stats_loading }}</div></div>
    <div class="sp-sec"><b>{{ T.ord_list_title }}</b><button class="sp-link" id="ordToggle" onclick="toggleAllOrders()"></button></div>
    <div class="sp-strip" id="ordStrip"></div>
    <div class="sp-orders" id="ordWrap">
      <div id="ordList">{{ T.stats_loading }}</div>
      <button class="wh-tbtn wh-tbtn-wide" id="ordMoreBtn" style="display:none; margin:6px 0 10px;" onclick="loadMoreOrders()">{{ T.sp_show_more }}</button>
    </div>
  </div>
  {% endif %}

  <div id="whModals">
      <div class="modal-overlay" id="addProductModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.wh_add_product }}</h3>
          <div class="row2">
            <div class="field">
              <label>{{ T.wh_category }}</label>
              <select id="wh_new_category" onchange="onWhCategoryChanged()"></select>
            </div>
            <div class="field">
              <label>{{ T.wh_product_name }}</label>
              <input id="wh_new_name" placeholder="MITANOL 5W-30">
            </div>
          </div>
          <div class="field" id="wh_new_unit_row" style="display:none;">
            <label>{{ T.wh_unit }}</label>
            <select id="wh_new_unit">
              <option value="pc">{{ T.unit_pc }}</option>
              <option value="l">{{ T.unit_l }}</option>
            </select>
          </div>
          <div class="row2">
            <div class="field">
              <label>{{ T.wh_sell_price }}</label>
              <input id="wh_new_sell_price" type="number" placeholder="45000" oninput="onSumFieldEdited('wh_new_sell_price', 'wh_new_sell_usd')">
            </div>
            <div class="field">
              <label>{{ T.usd_sell_label }}</label>
              <input id="wh_new_sell_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('wh_new_sell_usd', 'wh_new_sell_price')">
            </div>
          </div>
          {% if not is_branch %}
          <div class="cur-switch" id="wh_new_cur"><button type="button" data-cur="UZS" class="on" onclick="curSet('wh_new', 'UZS')">{{ T.usd_cur_uzs }}</button><button type="button" data-cur="USD" onclick="curSet('wh_new', 'USD')">{{ T.usd_cur_usd }}</button></div>
          <div class="hint-text" id="wh_new_cur_hint" style="margin:-2px 0 8px;">{{ T.usd_cur_hint_uzs }}</div>
          {% endif %}
          <div class="row2" {% if is_branch %}style="display:none;"{% endif %}>
            <div class="field">
              <label>{{ T.wh_purchase_price }}</label>
              <input id="wh_new_purchase_price" type="number" placeholder="30000" oninput="onSumFieldEdited('wh_new_purchase_price', 'wh_new_purchase_usd')">
            </div>
            <div class="field" id="wh_new_purchase_usd_wrap">
              <label>{{ T.usd_buy_label }}</label>
              <input id="wh_new_purchase_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('wh_new_purchase_usd', 'wh_new_purchase_price')">
            </div>
          </div>
          <div class="field">
            <label>{{ T.wh_initial_stock }}</label>
            <input id="wh_new_stock" type="number" placeholder="0">
          </div>
          <button class="submit" onclick="createProduct()">{{ T.wh_add_btn }}</button>
          <button class="close-btn" onclick="closeWhModal('addProductModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="purchaseListModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.whs_purchase_list }}</h3>
          <div class="hint-text" style="margin-bottom:10px;">{{ T.whs_purchase_hint }}</div>
          <div id="purchaseListBody"></div>
          <button class="submit" onclick="sendPurchaseList('tg')" style="background:#2AABEE;"><i class="fa-brands fa-telegram"></i> {{ T.whs_send_tg }}</button>
          <button class="submit" onclick="sendPurchaseList('copy')" style="background:var(--border); color:var(--text);"><i class="fa-regular fa-copy"></i> {{ T.whs_copy }}</button>
          {% if not is_branch and not is_employee %}<button class="submit" id="plOrderBtn" onclick="purchaseToOrder()" style="background:#DBEAFE; color:#0F52BA; display:none;"><i class="fa-solid fa-truck-ramp-box"></i> {{ T.ord_from_purchase }}</button>{% endif %}
          <button class="close-btn" onclick="closeWhModal('purchaseListModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      {% if not is_branch and not is_employee %}
      <div class="modal-overlay" id="orderModal">
        <div class="modal modal-wide" style="text-align:left;">
          <div id="ordHead"></div>
          <div id="ordBody"></div>
          <button class="close-btn" onclick="closeWhModal('orderModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="supplierModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;" id="supModalTitle">{{ T.sup_add }}</h3>
          <div class="field">
            <label>{{ T.sup_name }}</label>
            <input id="sup_name" placeholder="MITAL" maxlength="80" autocomplete="off">
          </div>
          <div class="row2">
            <div class="field">
              <label>{{ T.sup_phone }}</label>
              <input id="sup_phone" type="tel" inputmode="tel" placeholder="+998 90 123 45 67" maxlength="40">
            </div>
            <div class="field">
              <label>{{ T.sup_telegram }}</label>
              <input id="sup_telegram" placeholder="@username" maxlength="64" autocomplete="off" autocapitalize="off">
            </div>
          </div>
          <div class="row2">
            <div class="field">
              <label>{{ T.sup_contact }}</label>
              <input id="sup_contact" maxlength="80">
            </div>
            <div class="field">
              <label>{{ T.sup_days }}</label>
              <input id="sup_delivery_days" placeholder="{{ T.sup_days_ph }}" maxlength="80">
            </div>
          </div>
          <div class="row2">
            <div class="field">
              <label>{{ T.sup_pay_days }}</label>
              <input id="sup_pay_days" type="number" inputmode="numeric" min="0" max="365" placeholder="{{ T.sup_pay_days_ph }}">
            </div>
            <div class="field">
              <label>{{ T.sup_note }}</label>
              <input id="sup_note" maxlength="300">
            </div>
          </div>
          <div id="supTgBlock" class="sup-tg" style="display:none;"></div>
          <button class="submit" onclick="saveSupplier()">{{ T.sup_save }}</button>
          <button class="submit" id="supDeleteBtn" onclick="deleteSupplierBtn()" style="background:#FEE2E2; color:#B91C1C;">{{ T.sup_delete }}</button>
          <button class="close-btn" onclick="closeWhModal('supplierModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="supProductsModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.sup_assign_title }}: <span id="supProdTitle"></span></h3>
          <div class="hint-text" style="margin-bottom:10px;">{{ T.sup_assign_hint }}</div>
          <div class="wh-search" style="margin-bottom:8px;"><i class="fa-solid fa-magnifying-glass"></i><input id="supProdSearch" placeholder="{{ T.whs_search }}" oninput="renderSupProducts()" autocomplete="off"></div>
          <div style="display:flex; gap:8px; margin-bottom:6px;">
            <button class="wh-tbtn wh-tbtn-sm" onclick="supSelectVisible(true)">{{ T.sup_all }}</button>
            <button class="wh-tbtn wh-tbtn-sm" onclick="supSelectVisible(false)">{{ T.sup_none }}</button>
            <span class="hint-text" id="supProdCount" style="margin:auto 0 auto auto;"></span>
          </div>
          <div id="supProdList"></div>
          <button class="submit" onclick="saveSupplierProducts()">{{ T.sup_save }}</button>
          <button class="close-btn" onclick="closeWhModal('supProductsModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      {% endif %}
      {% if not is_branch and not is_employee %}
      <div class="modal-overlay sp-sheet-ov" id="supCardModal" onclick="if (event.target === this) closeWhModal('supCardModal')">
        <div class="modal modal-wide sp-sheet">
          <div class="sp-grab"></div>
          <button class="sp-x" onclick="closeWhModal('supCardModal')" aria-label="{{ T.modal_close }}"><i class="fa-solid fa-xmark"></i></button>
          <div class="sp-sheet-body" id="supCardScroll"><div id="supCardBody"></div></div>
          <div class="sp-foot" id="supCardFoot"></div>
        </div>
      </div>
      <div class="modal-overlay" id="orderNewProductModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.onp_title }}</h3>
          <div class="hint-text" id="onp_hint" style="margin-bottom:10px;"></div>
          <div class="field">
            <label>{{ T.wh_category }}</label>
            <select id="onp_category" onchange="onOnpCategoryChanged()"></select>
          </div>
          <div class="field">
            <label>{{ T.wh_product_name }}</label>
            <input id="onp_name" placeholder="MITANOL 5W-30" autocomplete="off">
          </div>
          <div class="field" id="onp_unit_row" style="display:none;">
            <label>{{ T.wh_unit }}</label>
            <select id="onp_unit">
              <option value="pc">{{ T.unit_pc }}</option>
              <option value="l">{{ T.unit_l }}</option>
            </select>
          </div>
          <div class="field">
            <label>{{ T.onp_sell }}</label>
            <input id="onp_sell" type="number" inputmode="numeric" placeholder="45000">
          </div>
          <button class="submit" onclick="saveOrderNewProduct()">{{ T.onp_save }}</button>
          <button class="close-btn" onclick="closeWhModal('orderNewProductModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      {% endif %}
      <div class="modal-overlay" id="transferModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.whn_transfer }}</h3>
          <div class="row2">
            <div class="field">
              <label>{{ T.whn_from }}</label>
              <select id="tr_from" onchange="onTransferFromChanged()"></select>
            </div>
            <div class="field">
              <label>{{ T.whn_to }}</label>
              <select id="tr_to"></select>
            </div>
          </div>
          <div class="field">
            <label>{{ T.whn_product }}</label>
            <select id="tr_product" onchange="onTransferProductChanged()"></select>
            <div class="hint-text" id="tr_available"></div>
          </div>
          <div class="field">
            <label>{{ T.whn_qty }}</label>
            <input id="tr_qty" type="number" step="0.5" min="0">
          </div>
          <button class="submit" onclick="submitTransfer()">{{ T.whn_send }}</button>
          <button class="close-btn" onclick="closeWhModal('transferModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="editProductModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.whe_title }}</h3>
          <div class="hint-text" id="ep_category" style="text-align:center; margin:-6px 0 12px;"></div>
          <div class="field">
            <label>{{ T.wh_product_name }}</label>
            <input id="ep_name">
          </div>
          <div class="row2">
            <div class="field">
              <label>{{ T.wh_sell_price }}</label>
              <input id="ep_sell" type="number" min="0" oninput="onSumFieldEdited('ep_sell', 'ep_sell_usd')">
            </div>
            <div class="field" id="ep_sell_usd_wrap">
              <label>{{ T.usd_sell_label }}</label>
              <input id="ep_sell_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('ep_sell_usd', 'ep_sell')">
            </div>
          </div>
          <div id="ep_cur_wrap">
            <div class="cur-switch" id="ep_cur"><button type="button" data-cur="UZS" class="on" onclick="curSet('ep', 'UZS')">{{ T.usd_cur_uzs }}</button><button type="button" data-cur="USD" onclick="curSet('ep', 'USD')">{{ T.usd_cur_usd }}</button></div>
            <div class="hint-text" id="ep_cur_hint" style="margin:-2px 0 8px;">{{ T.usd_cur_hint_uzs }}</div>
          </div>
          <div class="row2" id="ep_buy_wrap">
            <div class="field">
              <label>{{ T.wh_purchase_price }}</label>
              <input id="ep_buy" type="number" min="0" oninput="onSumFieldEdited('ep_buy', 'ep_buy_usd')">
            </div>
            <div class="field" id="ep_usd_wrap">
              <label>{{ T.usd_buy_label }}</label>
              <input id="ep_buy_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('ep_buy_usd', 'ep_buy')">
            </div>
          </div>
          <div class="hint-text" id="ep_price_hint" style="margin:-4px 0 10px;">{{ T.whe_price_hint }}</div>
          <div class="row2">
            <div class="field">
              <label><span id="ep_stock_lbl">{{ T.whe_stock_label }}</span> (<span id="ep_unit"></span>)</label>
              <input id="ep_stock" type="number" min="0" step="0.5" oninput="onEditStockChanged()">
            </div>
            <div class="field" id="ep_reason_wrap" style="display:none;">
              <label>{{ T.whe_reason_label }}</label>
              <input id="ep_reason" placeholder="{{ T.whe_reason_ph }}">
            </div>
          </div>
          <div class="hint-text" id="ep_stock_hint" style="margin:-4px 0 10px;">{{ T.whe_stock_hint }}</div>
          <button class="submit" onclick="submitEditProduct()">{{ T.whe_save }}</button>
          <button class="close-btn" onclick="closeWhModal('editProductModal')">{{ T.modal_close }}</button>
        </div>
      </div>
      <div class="modal-overlay" id="shipModal">
        <div class="modal modal-wide ship-modal" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.shp_title }}</h3>
          <div class="row2">
            <div class="field"><label>{{ T.whn_from }}</label><select id="shp_from" onchange="loadShipPlan()"></select></div>
            <div class="field"><label>{{ T.whn_to }}</label><select id="shp_to" onchange="loadShipPlan()"></select></div>
          </div>
          <div class="wh-toolbar" style="margin-bottom:8px;">
            <div class="wh-search"><i class="fa-solid fa-magnifying-glass"></i><input id="shp_search" placeholder="{{ T.whs_search }}" oninput="renderShipRows()" autocomplete="off"></div>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px;">
            <button class="wh-tbtn wh-tbtn-sm" onclick="shipAutofill()"><i class="fa-solid fa-wand-magic-sparkles"></i> {{ T.shp_autofill }}</button>
            <button class="wh-tbtn wh-tbtn-sm" onclick="shipClear()"><i class="fa-solid fa-eraser"></i> {{ T.shp_clear }}</button>
            <label class="wh-tbtn wh-tbtn-sm" style="display:inline-flex; align-items:center; gap:6px; margin:0; text-transform:none; letter-spacing:0; color:var(--text);"><input type="checkbox" id="shp_only_selected" onchange="renderShipRows()" style="width:auto; margin:0;"> {{ T.shp_only_selected }}</label>
          </div>
          <div class="brand-chips" id="shp_cats"></div>
          <div id="shp_list" class="ship-list">{{ T.stats_loading }}</div>
          <div class="ship-foot">
            <span id="shp_summary"></span>
            <button class="submit" style="width:auto; padding:10px 18px; margin:0;" onclick="submitShip()"><i class="fa-solid fa-truck"></i> {{ T.shp_send }}</button>
          </div>
          <button class="close-btn" onclick="closeWhModal('shipModal')">{{ T.modal_close }}</button>
        </div>
      </div>

      <div class="modal-overlay" id="catalogModal">
        <div class="modal modal-wide" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.cat_title }}</h3>
          <div class="hint-text" style="margin-bottom:12px;">{{ T.cat_hint }}</div>
          <div class="field"><label>{{ T.cat_branch }}</label><select id="cat_branch"></select></div>
          <label style="display:block; margin:6px 0;">{{ T.cat_types }}</label>
          <div id="cat_types" style="display:flex; flex-direction:column; gap:6px; margin-bottom:12px;"></div>
          <button class="submit" onclick="submitCatalog()"><i class="fa-solid fa-copy"></i> {{ T.cat_copy }}</button>
          <button class="close-btn" onclick="closeWhModal('catalogModal')">{{ T.modal_close }}</button>
        </div>
      </div>

      <div class="modal-overlay" id="importModal">
        <div class="modal modal-wide ship-modal" style="text-align:left;">
          <h3 style="text-align:center; margin-top:0;">{{ T.imp_title }}</h3>
          <div class="imp-steps">
            <div><b>1.</b> {{ T.imp_step1 }} <a class="wh-tbtn wh-tbtn-sm" href="/api/products/import_template" style="text-decoration:none; display:inline-block; margin-left:4px;"><i class="fa-solid fa-download"></i> {{ T.imp_template }}</a></div>
            <div><b>2.</b> {{ T.imp_step2 }}</div>
            <div><b>3.</b> {{ T.imp_step3 }}</div>
          </div>
          <input type="file" id="imp_file" accept=".xlsx" onchange="previewImport()" style="margin:10px 0;">
          <div id="imp_preview"></div>
          <button class="submit" id="imp_apply_btn" style="display:none;" onclick="applyImport()"></button>
          <button class="close-btn" onclick="closeWhModal('importModal')">{{ T.modal_close }}</button>
        </div>
      </div>
  </div>
  {% endif %}
</div>
"""


MODAL_AND_SCRIPT = """
<div class="modal-overlay" id="restockModal">
  <div class="modal" style="text-align:left;">
    <h3 style="text-align:center;" id="restockModalTitle">{{ T.wh_restock_title }}</h3>
    <div class="field">
      <label>{{ T.wh_restock_qty }}</label>
      <input id="restock_qty" type="number">
    </div>
    <div class="field" {% if is_branch %}style="display:none;"{% endif %}>
      <label>{{ T.wh_purchase_price }}</label>
      <input id="restock_price" type="number" oninput="onSumFieldEdited('restock_price', 'restock_price_usd')">
    </div>
    <div class="field" {% if is_branch %}style="display:none;"{% endif %}>
      <label>{{ T.usd_price_label }}</label>
      <input id="restock_price_usd" type="number" step="0.01" placeholder="$" oninput="onUsdFieldEdited('restock_price_usd', 'restock_price')">
    </div>
    <div class="field">
      <label>{{ T.wh_restock_date }}</label>
      <input id="restock_date" type="date">
    </div>
    <button class="submit" onclick="submitRestock()">{{ T.wh_restock_btn }}</button>
    <button class="close-btn" onclick="closeRestockModal()">{{ T.modal_close }}</button>
  </div>
</div>

<div class="modal-overlay" id="linkModal">
  <div class="modal">
    <h3 id="modalPlate"></h3>
    <div class="hint-text">{{ T.modal_hint }}</div>
    <img id="modalQr" alt="QR">
    <div class="link-text" id="modalLink"></div>
    <a class="wa-btn" id="modalTg" href="#" target="_blank"><button class="submit" type="button" style="background:#2AABEE;">{{ T.modal_send_tg }}</button></a>
    <a class="wa-btn" id="modalWa" href="#" target="_blank"><button class="submit" type="button">{{ T.modal_send_wa }}</button></a>
    <button class="submit" onclick="copyLink()" style="background:var(--border);">{{ T.modal_copy }}</button>
    <button class="close-btn" onclick="closeModal()">{{ T.modal_close }}</button>
  </div>
</div>

<div class="modal-overlay" id="writeoffModal">
  <div class="modal" style="text-align:left; max-width:400px;">
    <h3 id="woTitle" style="margin-top:0;"></h3>
    <div id="woText" class="hint-text" style="font-size:13px; line-height:1.45; margin-bottom:10px;"></div>
    <div style="font-size:12px; font-weight:600; color:var(--hint);">{{ T.wo_reason }}</div>
    <div class="wo-reasons" id="woReasons"></div>
    <div class="wo-warn" id="woWarn" style="display:none;">{{ T.wo_input_error_hint }}</div>
    <div class="wo-btns">
      <button type="button" class="close-btn" onclick="closeWriteoff()">{{ T.wo_cancel }}</button>
      <button type="button" class="wo-go" onclick="confirmWriteoff()">{{ T.wo_confirm }}</button>
    </div>
  </div>
</div>

<div class="modal-overlay" id="editModal">
  <div class="modal modal-wide" style="text-align:left;">
    <h3 style="text-align:center;" id="svcModalTitle">{{ T.entry_edit_title }}</h3>
    <div class="field">
      <label>{{ T.field_mileage }}</label>
      <input id="edit_mileage" type="number">
    </div>
    <div class="field">
      <label>{{ T.field_next_mileage }}</label>
      <input id="edit_next_mileage" type="number">
    </div>
    {% if has_staff %}<div class="field" id="editMasterWrap">
      <label>{{ T.team_master }}</label>
      <select id="edit_master_id"></select>
    </div>{% endif %}

    {% if warehouse_enabled %}
    <div class="field pick-search">
      <label>{{ T.pick_search_label }}</label>
      <input id="svcPickSearch" type="search" placeholder="{{ T.pick_search_ph }}" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="search" oninput="renderPickResults('svc')" onkeydown="onPickKey(event, 'svc')">
      <div id="svcPickResults" class="pick-results"></div>
    </div>
    {% endif %}
    <div class="field">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.section_fluids }}</label>
    </div>
    <div id="svcFluidsList"></div>

    <div class="field" style="margin-top:10px;">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.section_filters }}</label>
    </div>
    <div id="svcFiltersList"></div>

    <div class="field" style="margin-top:10px;">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.section_other }}</label>
    </div>
    <div class="row2">
      <div class="field">
        <label>{{ T.field_other_name }}</label>
        <input id="svc_other_name" placeholder="{{ T.field_other_name_ph }}">
      </div>
      <div class="field">
        <label>{{ T.field_price }}</label>
        <input id="svc_other_price" type="number" placeholder="0" oninput="updateSvcTotal()">
      </div>
    </div>

    {% if warehouse_enabled %}
    <div class="field" style="margin-top:10px;">
      <label style="font-size:15px; color:var(--text); font-weight:600;">{{ T.wh_other_stock_title }}</label>
    </div>
    <div id="svcOtherStockRows"></div>
    <button type="button" class="submit" style="padding:8px; background:var(--border);" onclick="addOtherStockRow('svcOther')">{{ T.wh_add_row }}</button>
    {% endif %}

    <div class="field" style="margin-top:10px;">
      <label>{{ T.disc_title }}, {{ T.currency }}</label>
      <div style="display:flex; gap:6px;">
        <input id="svc_discount" type="number" inputmode="numeric" placeholder="0" style="flex:1; min-width:0;" oninput="updateSvcTotal()">
        <button type="button" class="disc-chip" onclick="svcDiscPct(5)">5%</button>
        <button type="button" class="disc-chip" onclick="svcDiscPct(10)">10%</button>
      </div>
      <div id="svcDiscHint" style="font-size:12px; color:var(--hint); margin-top:4px;"></div>
    </div>

    <div class="field" style="margin-top:10px; padding:12px; background:var(--field-bg); border-radius:10px;">
      <label style="font-size:15px;">{{ T.disc_to_pay }}</label>
      <div id="svcTotalCost" style="font-size:22px; font-weight:600; color:var(--btn); font-family:var(--font-mono);">0</div>
    </div>

    <div class="field" style="margin-top:10px;">
      <label>{{ T.payment_split_label }}</label>
      <div class="row2">
        <div class="field">
          <label style="font-size:11px;"><i class="fa-solid fa-money-bill"></i> {{ T.payment_cash }}</label>
          <input id="svc_pay_cash" type="number" placeholder="0" oninput="onSvcPayCashInput()">
        </div>
        <div class="field">
          <label style="font-size:11px;"><i class="fa-solid fa-credit-card"></i> {{ T.payment_card }}</label>
          <input id="svc_pay_card" type="number" placeholder="0" oninput="onSvcPayCardInput()">
        </div>
      </div>
    </div>

    <div class="field" style="margin-top:10px;">
      <label>{{ T.field_interval }}</label>
      <div style="display:flex; gap:8px;">
        <input id="edit_interval_value" type="number" style="flex:1;">
        <select id="edit_interval_unit" style="flex:1;">
          <option value="months">{{ T.unit_months }}</option>
          <option value="days">{{ T.unit_days }}</option>
        </select>
      </div>
    </div>
    <div class="field">
      <label>{{ T.field_notes }}</label>
      <textarea id="edit_notes" rows="2"></textarea>
    </div>
    <button class="submit" onclick="saveEdit()">{{ T.btn_save }}</button>
    <button class="close-btn" onclick="closeEditModal()">{{ T.modal_close }}</button>
  </div>
</div>

<script>
const T = {{ t_json|safe }};
const LANG = {{ lang|tojson }};
const WAREHOUSE_ENABLED = {{ warehouse_enabled|tojson }};
const STORE_ENABLED = {{ store_enabled|tojson }};  // «Склад магазина»: основной склад + магазин
const IS_BRANCH = {{ is_branch|tojson }};
const IS_EMP_TEAM = {{ is_employee|tojson }};
const MY_EMP_ID = {{ my_employee_id|tojson }};
const IS_EMPLOYEE = {{ is_employee|tojson }};
const CAR_MODELS = {{ car_models|tojson }};
let USD_RATE = {{ usd_rate|tojson }};
const BOT_USERNAME = {{ bot_username|tojson }};
function clientLink(token) { return token && BOT_USERNAME ? 'https://t.me/' + BOT_USERNAME + '?start=' + token : ''; }
// Графики (Chart.js, ~70 КБ) нужны только в «Статистике» — грузим их не при
// старте, а когда раздел открыли (или тихо в фоне через несколько секунд).
// Когда библиотека пришла, а статистика уже на экране — перерисовываем её.
let CHART_LOADING = false;
function ensureChartJs() {
  if (typeof Chart !== 'undefined' || CHART_LOADING) return;
  CHART_LOADING = true;
  const s = document.createElement('script');
  s.src = 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js';
  s.crossOrigin = 'anonymous';
  s.onload = () => { if (window.glChartTheme) glChartTheme(); if (CURRENT_TAB === 'stats') refreshCurrentView(); };
  s.onerror = () => { CHART_LOADING = false; s.remove(); };
  document.head.appendChild(s);
}
window.addEventListener('load', () => {
  if (document.getElementById('view-stats')) setTimeout(ensureChartJs, 4000);
});

let carsCache = [];
let lastKnownNextMileage = null;

function checkMileageVsDue() {
  const el = document.getElementById('mileageCompare');
  if (!el) return;
  const entered = parseFloat(document.getElementById('mileage').value);
  if (!lastKnownNextMileage || isNaN(entered)) { el.innerHTML = ''; return; }
  const diff = entered - lastKnownNextMileage;
  if (diff > 0) {
    el.innerHTML = `<div class="mileage-compare over">⚠️ ${T.mileage_over_due} ${lastKnownNextMileage.toLocaleString('ru-RU')} ${T.km_short} — ${T.mileage_over_by} ${diff.toLocaleString('ru-RU')} ${T.km_short}</div>`;
  } else {
    el.innerHTML = `<div class="mileage-compare ok">${T.mileage_within_due} ${lastKnownNextMileage.toLocaleString('ru-RU')} ${T.km_short}</div>`;
  }
}

let openHistoryRow = null;
let historyDataCache = {};  // { plate: [entry, entry, ...] } — чтобы кнопки не тащили сырые данные записи (с заметками, апострофами и т.п.) прямо в HTML-атрибут onclick, а брали их отсюда по id

let CURRENT_TAB = 'add';
function showTab(t, keepScroll) {
  CURRENT_TAB = t;
  document.getElementById('view-add').style.display = t === 'add' ? '' : 'none';
  document.getElementById('view-table').style.display = t === 'table' ? 'block' : 'none';
  document.getElementById('view-debts').style.display = t === 'debts' ? 'block' : 'none';
  document.getElementById('view-broadcast').style.display = t === 'broadcast' ? 'block' : 'none';
  document.getElementById('tab-add').classList.toggle('active', t === 'add');
  document.getElementById('tab-table').classList.toggle('active', t === 'table');
  document.getElementById('tab-debts').classList.toggle('active', t === 'debts');
  document.getElementById('tab-broadcast').classList.toggle('active', t === 'broadcast');
  const exportView = document.getElementById('view-export');
  const exportTab = document.getElementById('tab-export');
  if (exportView) exportView.style.display = t === 'export' ? 'block' : 'none';
  if (exportTab) exportTab.classList.toggle('active', t === 'export');
  const statsView = document.getElementById('view-stats');
  const statsTab = document.getElementById('tab-stats');
  if (statsView) statsView.style.display = t === 'stats' ? 'block' : 'none';
  if (statsTab) statsTab.classList.toggle('active', t === 'stats');
  const smsView = document.getElementById('view-sms');
  const smsTab = document.getElementById('tab-sms');
  if (smsView) smsView.style.display = t === 'sms' ? 'block' : 'none';
  if (smsTab) smsTab.classList.toggle('active', t === 'sms');
  const whView = document.getElementById('view-warehouse');
  const whTab = document.getElementById('tab-warehouse');
  if (whView) whView.style.display = t === 'warehouse' ? 'block' : 'none';
  if (whTab) whTab.classList.toggle('active', t === 'warehouse');
  const supView = document.getElementById('view-suppliers');
  const supTab = document.getElementById('tab-suppliers');
  if (supView) supView.style.display = t === 'suppliers' ? 'block' : 'none';
  if (supTab) supTab.classList.toggle('active', t === 'suppliers');
  const expView = document.getElementById('view-expenses');
  const expTab = document.getElementById('tab-expenses');
  if (expView) expView.style.display = t === 'expenses' ? 'block' : 'none';
  if (expTab) expTab.classList.toggle('active', t === 'expenses');
  if (t === 'table') { loadCars(); loadBaseDue(); }
  if (t === 'debts') loadDebts();
  if (t === 'expenses') loadExpensesTab();
  const rateView = document.getElementById('view-rate');
  if (rateView) rateView.style.display = t === 'rate' ? 'block' : 'none';
  if (t === 'rate') loadRateTab();
  if (t === 'broadcast') loadBroadcastInfo();
  document.querySelectorAll('[data-tab]').forEach(el => el.classList.toggle('active', el.dataset.tab === t));
  // пункт «Ещё» подсвечен, если открыт раздел, которого нет в нижней панели
  const sheet = document.getElementById('moreSheet');
  const bbMore = document.getElementById('bbMore');
  if (sheet && bbMore) bbMore.classList.toggle('active', !sheet.dataset.bar.split(',').includes(t));
  if (!keepScroll) window.scrollTo(0, 0);
  if (window.glEnter && !keepScroll) glEnter('view-' + t);
  if (t === 'stats') { ensureChartJs(); loadStats(); }
  if (t === 'warehouse') loadWarehouse();
  if (t === 'suppliers') loadSuppliersTab();
  const courseView = document.getElementById('view-course');
  const courseTab = document.getElementById('tab-course');
  if (courseView) courseView.style.display = t === 'course' ? 'block' : 'none';
  if (courseTab) courseTab.classList.toggle('active', t === 'course');
  if (t === 'course') loadCourse();
  const staffView = document.getElementById('view-staff');
  const staffTab = document.getElementById('tab-staff');
  if (staffView) staffView.style.display = t === 'staff' ? 'block' : 'none';
  if (staffTab) staffTab.classList.toggle('active', t === 'staff');
  if (t === 'staff') loadStaff();
  const myshopView = document.getElementById('view-myshop');
  const myshopTab = document.getElementById('tab-myshop');
  if (myshopView) myshopView.style.display = t === 'myshop' ? 'block' : 'none';
  if (myshopTab) myshopTab.classList.toggle('active', t === 'myshop');
  if (t === 'myshop') loadMyShop();
  const cashView = document.getElementById('view-cash');
  const cashTab = document.getElementById('tab-cash');
  if (cashView) cashView.style.display = t === 'cash' ? 'block' : 'none';
  if (cashTab) cashTab.classList.toggle('active', t === 'cash');
  if (t === 'cash') loadCash();
  const helpView = document.getElementById('view-help');
  const helpTab = document.getElementById('tab-help');
  if (helpView) helpView.style.display = t === 'help' ? 'block' : 'none';
  if (helpTab) helpTab.classList.toggle('active', t === 'help');
  const teamView = document.getElementById('view-team');
  if (teamView) teamView.style.display = t === 'team' ? 'block' : 'none';
  if (t === 'team') loadTeam();
}

// ---------- Команда: рейтинг, зарплата, награды ----------
const TEAM = { period: null, shop: null, data: null, seq: 0, shops: null, emp: null };
function teamPeriodNow() { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); }
function teamShift(n) {
  const p = TEAM.period.split('-').map(Number);
  const d = new Date(p[0], p[1] - 1 + n, 1);
  const next = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
  if (next > teamPeriodNow()) return;
  TEAM.period = next;
  loadTeam();
}
function teamPrevPeriod(per) { const p = per.split('-').map(Number); const d = new Date(p[0], p[1] - 2, 1); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); }
function teamMonthLabel(per) { const p = per.split('-').map(Number); return (String(T.team_months).split(',')[p[1] - 1] || p[1]) + ' ' + p[0]; }
function teamPos(code) { return T['team_pos_' + (code || 'master')] || code || ''; }
function teamMoney(n) { return fmtNum(Math.round(n || 0)) + ' ' + T.currency; }
function teamFmt(s, vars) { return String(s).replace(/{([a-z_]+)}/g, (m, k) => (k in vars ? vars[k] : m)); }
function teamInitials(name) {
  const parts = String(name || '?').trim().split(/ +/).filter(Boolean);
  return escapeHtml(((parts[0] || '?')[0] + (parts[1] ? parts[1][0] : '')).toUpperCase());
}
function teamShopQs() { return (TEAM.shop && TEAM.shop !== 'net') ? '&shop=' + encodeURIComponent(TEAM.shop) : ''; }
function teamParseAmount(raw, allowMinus) {
  const s = String(raw || '').trim();
  const neg = allowMinus && (s.startsWith('-') || s.startsWith('−'));
  const n = parseInt(s.replace(/[^0-9]/g, ''), 10) || 0;
  return neg ? -n : n;
}
function teamAmountInput(el) {
  const s = String(el.value || '');
  const neg = el.dataset.minus === '1' && (s.trim().startsWith('-') || s.trim().startsWith('−'));
  const digits = s.replace(/[^0-9]/g, '');
  el.value = (neg ? '−' : '') + (digits ? Number(digits).toLocaleString('ru-RU') : '');
}

async function loadTeam() {
  if (!TEAM.period) TEAM.period = teamPeriodNow();
  const box = document.getElementById('teamBox');
  if (!box) return;
  const seq = ++TEAM.seq;
  const url = TEAM.shop === 'net'
    ? '/api/team/network?period=' + TEAM.period
    : '/api/team?period=' + TEAM.period + teamShopQs();
  let d;
  try { d = await (await fetch(url, { credentials: 'same-origin', cache: 'no-store' })).json(); }
  catch (e) { if (seq === TEAM.seq) box.innerHTML = `<div class="card">${escapeHtml(T.msg_no_connection || T.team_err)}</div>`; return; }
  if (seq !== TEAM.seq) return;
  if (!d.ok) { box.innerHTML = `<div class="card">${escapeHtml(d.error || T.team_err)}</div>`; return; }
  TEAM.data = d;
  if (d.shops) TEAM.shops = d.shops;
  let body;
  if (TEAM.shop === 'net') body = teamBoardCard(d.board, true, null);
  else if (IS_EMP_TEAM) body = teamEmployeeHtml(d);
  else body = teamOwnerHtml(d);
  box.innerHTML = teamHeader(d) + body;
}

function teamHeader(d) {
  let sel = '';
  if (!IS_EMP_TEAM && TEAM.shops && TEAM.shops.length > 1) {
    const cur = TEAM.shop || String(TEAM.shops[0].id);
    sel = `<select onchange="TEAM.shop = this.value; loadTeam();">` +
      TEAM.shops.map((s, i) => `<option value="${s.id}" ${String(s.id) === cur ? 'selected' : ''}>${escapeHtml(i === 0 ? T.team_my_shop + ' · ' + s.name : s.name)}</option>`).join('') +
      `<option value="net" ${cur === 'net' ? 'selected' : ''}>${escapeHtml(T.team_net)}</option></select>`;
  }
  const done = d && d.finished ? ` <small style="color:var(--hint); font-size:12px;">· ${escapeHtml(T.team_finished)}</small>` : '';
  return `<div class="tm-head"><div class="tm-month">
      <button type="button" onclick="teamShift(-1)" aria-label="prev"><i class="fa-solid fa-chevron-left"></i></button>
      <b>${escapeHtml(teamMonthLabel(TEAM.period))}</b>
      <button type="button" onclick="teamShift(1)" aria-label="next" ${TEAM.period >= teamPeriodNow() ? 'style="visibility:hidden"' : ''}><i class="fa-solid fa-chevron-right"></i></button>
    </div>${sel}${done}</div>`;
}

function teamPodium(board) {
  // первые три по порядку (при равенстве очков у двоих одно и то же место)
  const top = board.filter(r => r.place).slice(0, 3);
  if (!top.length) return '';
  const pod = (i) => {
    const r = top[i];
    if (!r) return `<div class="tm-pod p${i + 1} empty"><div class="crown"></div><div class="av"></div><div class="nm">-</div><div class="pt">-</div><div class="st">${i + 1}</div></div>`;
    return `<div class="tm-pod p${i + 1}"><div class="crown">${r.place === 1 ? '<i class="fa-solid fa-crown"></i>' : ''}</div>
      <div class="av">${teamInitials(r.name)}</div><div class="nm">${escapeHtml(r.name)}</div>
      <div class="pt">${fmtNum(r.points)} ${escapeHtml(T.team_points)}</div><div class="st">${r.place}</div></div>`;
  };
  return `<div class="tm-podium">${pod(1)}${pod(0)}${pod(2)}</div>`;
}

function teamMove(r) {
  if (r.move === null || r.move === undefined || r.move === 0) return '';
  return r.move > 0 ? `<span class="tm-mv up">▲${r.move}</span>` : `<span class="tm-mv down">▼${-r.move}</span>`;
}

function teamBoardCard(board, network, meId) {
  if (!board || !board.length || !board.some(r => r.services > 0)) {
    return `<div class="tm-card"><div class="tm-card-t">${escapeHtml(T.team_rating)}</div><div class="hint-text" style="margin:0;">${escapeHtml(T.team_no_data)}</div></div>`;
  }
  const rule = (TEAM.data && TEAM.data.points_rule) || { service: 10, filter: 5, repeat: 5 };
  const rows = board.map(r => `<div class="tm-row ${meId && r.id === meId ? 'me' : ''}">
      <div class="pl">${r.place || '–'}</div><div class="av">${teamInitials(r.name)}</div>
      <div class="who"><b>${escapeHtml(r.name)}${teamMove(r)}</b><small>${escapeHtml(network ? (r.shop || '') : teamPos(r.position))}${r.is_active === 0 ? ' · ' + escapeHtml(T.team_inactive) : ''}</small></div>
      <div class="num"><b>${fmtNum(r.points)} ${escapeHtml(T.team_points)}</b><small>${fmtNum(r.services)} ${escapeHtml(T.team_services)}</small></div></div>`).join('');
  return `<div class="tm-card"><div class="tm-card-t">${escapeHtml(T.team_rating)}</div>${teamPodium(board)}
    <div style="margin-top:10px;">${rows}</div>
    <div class="tm-rule">${escapeHtml(teamFmt(T.team_points_rule, { s: rule.service, f: rule.filter, r: rule.repeat }))}</div></div>`;
}

function teamLeaderCard(d, withCert) {
  const b = d.board || [];
  const leaders = b.filter(r => r.place === 1);
  if (!leaders.length || !d.lead) return '';
  let sub;
  if (leaders.length > 1) sub = teamFmt(T.team_tie, { n: fmtNum(leaders[0].points) });
  else if (d.lead.over && d.lead.by > 0) sub = teamFmt(T.team_lead_by, { name: d.lead.over, n: fmtNum(d.lead.by) });
  else sub = teamFmt(T.team_cert_stats, { services: fmtNum(leaders[0].services), points: fmtNum(leaders[0].points) });
  const cert = withCert ? leaders.map(r => `<a href="/api/team/certificate?period=${TEAM.period}&emp=${r.id}${teamShopQs()}" target="_blank" rel="noopener"><i class="fa-solid fa-file-pdf"></i> ${escapeHtml(T.team_cert)}${leaders.length > 1 ? ' · ' + escapeHtml(r.name.split(' ')[0]) : ''}</a>`).join('') : '';
  return `<div class="tm-leader"><i class="fa-solid fa-award"></i><div style="min-width:0;">
      <div class="tl-t">${escapeHtml(d.finished ? T.team_leader : T.team_leader_so_far)}: ${escapeHtml(leaders.map(r => r.name).join(', '))}</div>
      <div class="tl-s">${escapeHtml(sub)}</div></div><div class="tl-certs">${cert}</div></div>`;
}

function teamPlanHtml(r) {
  if (!r.plan) return '';
  const pct = Math.min(100, Math.round(r.services * 100 / r.plan));
  return `<div class="tm-plan">${escapeHtml(teamFmt(T.team_plan, { done: fmtNum(r.services), plan: fmtNum(r.plan) }))}</div>
    <div class="tm-bar ${r.services >= r.plan ? 'done' : ''}"><i style="width:${pct}%"></i></div>`;
}

function teamOwnerHtml(d) {
  const tiles = `<div class="tm-tiles">
    <div class="tm-tile blue"><span>${escapeHtml(T.team_fund)}</span><b>${escapeHtml(fmtShort(d.fund))}</b></div>
    <div class="tm-tile"><span>${escapeHtml(T.team_paid)}</span><b>${escapeHtml(fmtShort(d.paid))}</b></div>
    <div class="tm-tile green"><span>${escapeHtml(T.team_due)}</span><b>${escapeHtml(fmtShort(d.due))}</b></div></div>`;
  const sal = (d.board || []).map(r => {
    const s = r.salary;
    return `<div class="tm-sal"><div class="tm-sal-h"><div class="av">${teamInitials(r.name)}</div>
        <div class="who"><b>${escapeHtml(r.name)}</b><small>${escapeHtml(teamPos(r.position))}${r.place ? ' · ' + r.place + ' ' + escapeHtml(T.team_place_short) : ''}</small></div>
        <div class="sum"><b>${escapeHtml(fmtShort(s.accrued))}</b>
          <small class="${s.due > 0 ? 'due' : ''}">${escapeHtml(T.team_due)}: ${escapeHtml(fmtShort(s.due))}</small></div></div>
      ${teamPlanHtml(r)}
      <div class="tm-btns"><button type="button" onclick="openTeamEmp(${r.id})">${escapeHtml(T.team_details)}</button>
        <button type="button" class="pay" onclick="openTeamEmp(${r.id}, true)">${escapeHtml(T.team_pay_btn)}</button></div></div>`;
  }).join('') || `<div class="hint-text" style="margin:0;">${escapeHtml(T.team_no_staff)}</div>`;
  const st = d.settings || { positions: {}, top_bonus: 0 };
  const posInputs = ['intern', 'master', 'senior', 'expert', 'cashier'].map(k =>
    `<div><label>${escapeHtml(teamPos(k))}</label><input id="tmPos_${k}" inputmode="numeric" autocomplete="off" oninput="teamAmountInput(this)" value="${fmtNum(st.positions[k] || 0)}"></div>`).join('');
  const settings = `<div class="tm-card"><details class="tm-details"><summary><i class="fa-solid fa-gear"></i>${escapeHtml(T.team_settings)}</summary>
      <div class="hint-text" style="margin:8px 0 0;">${escapeHtml(T.team_settings_hint)} ${escapeHtml(teamFmt(T.team_terms_from, { month: teamMonthLabel(TEAM.period) }))}</div>
      <div class="tm-grid2">${posInputs}<div><label>${escapeHtml(T.team_top_bonus)}</label><input id="tmTopBonus" inputmode="numeric" autocomplete="off" oninput="teamAmountInput(this)" value="${fmtNum(st.top_bonus || 0)}"></div></div>
      <button class="submit" type="button" onclick="saveTeamSettings()">${escapeHtml(T.team_save)}</button></details></div>`;
  const prevBanner = d.prev_due > 0 ? `<div class="cash-warn" style="margin:0 0 12px; font-size:13px; display:flex; gap:8px; align-items:center; justify-content:space-between;">
      <span>${escapeHtml(teamFmt(T.team_prev_due, { month: teamMonthLabel(teamPrevPeriod(TEAM.period)), sum: fmtShort(d.prev_due) }))}</span>
      <button type="button" class="staff-copy" style="margin:0; background:#B45309; flex:0 0 auto;" onclick="teamShift(-1)">${escapeHtml(T.team_open)}</button></div>` : '';
  return prevBanner + tiles + teamLeaderCard(d, true) + teamBoardCard(d.board, false, null)
    + `<div class="tm-card"><div class="tm-card-t">${escapeHtml(T.team_salary)}<small>${escapeHtml(teamMonthLabel(TEAM.period))}</small></div>${sal}</div>` + settings;
}

function teamSalaryLines(s, services) {
  const L = [];
  const line = (label, val, cls) => L.push(`<div class="tm-line ${cls || ''}"><span>${escapeHtml(label)}</span><b>${escapeHtml(val)}</b></div>`);
  line(T.team_l_fixed, teamMoney(s.fixed));
  if (s.pct_goods) line(teamFmt(T.team_l_goods, { p: s.pct_goods, sum: fmtShort(s.goods_money) }), teamMoney(s.from_goods));
  if (s.pct_work) line(teamFmt(T.team_l_work, { p: s.pct_work, sum: fmtShort(s.work_money) }), teamMoney(s.from_work));
  if (s.plan && s.plan_bonus_amount) line(teamFmt(T.team_l_plan, { n: fmtNum(s.plan) }), s.plan_done ? teamMoney(s.plan_bonus) : fmtNum(services) + ' / ' + fmtNum(s.plan), s.plan_done ? '' : 'muted');
  if (s.top_bonus) line(s.top_shared ? T.team_l_top_shared : T.team_l_top, teamMoney(s.top_bonus));
  if (s.top_bonus_possible) line(teamFmt(T.team_l_top_possible, { sum: fmtShort(s.top_bonus_possible) }), '', 'muted');
  if (s.adjust) line(T.team_l_adjust, (s.adjust > 0 ? '+' : '−') + teamMoney(Math.abs(s.adjust)));
  line(T.team_accrued, teamMoney(s.accrued));
  if (s.paid) line(T.team_l_paid, '−' + teamMoney(s.paid), 'muted');
  line(T.team_l_due, teamMoney(s.due), 'tot');
  return `<div class="tm-lines">${L.join('')}</div>`;
}

function teamBadgesHtml(b) {
  if (!b) return '';
  const out = [];
  (b.master_of_month || []).length && out.push(`<span class="tm-badge gold"><i class="fa-solid fa-crown"></i>${escapeHtml(teamFmt(T.team_badge_mom, { n: b.master_of_month.length }))}</span>`);
  (b.milestones || []).slice().reverse().forEach(m => out.push(`<span class="tm-badge"><i class="fa-solid fa-medal"></i>${escapeHtml(teamFmt(T.team_badge_n, { n: fmtNum(m) }))}</span>`));
  if (b.next_milestone) out.push(`<span class="tm-badge off"><i class="fa-solid fa-lock"></i>${escapeHtml(teamFmt(T.team_badge_next, { n: fmtNum(b.next_milestone), left: fmtNum(b.next_milestone - b.total_services) }))}</span>`);
  return `<div class="tm-badges">${out.join('')}</div>`;
}

function teamEmployeeHtml(d) {
  const me = (d.board || []).find(r => r.id === MY_EMP_ID);
  let head = '';
  if (me && me.salary) {
    head = `<div class="tm-me"><div class="l">${escapeHtml(T.team_my_salary)} · ${escapeHtml(teamMonthLabel(TEAM.period))}</div>
      <div class="v">${escapeHtml(teamMoney(me.salary.accrued))}</div>
      <div class="s">${escapeHtml(T.team_my_place)}: ${me.place ? '<b>' + me.place + '</b>' : escapeHtml(T.team_no_place)} · ${fmtNum(me.points)} ${escapeHtml(T.team_points)} · ${fmtNum(me.services)} ${escapeHtml(T.team_services)}</div>
      ${teamPlanHtml(me)}</div>
      <div class="tm-card"><div class="tm-card-t">${escapeHtml(T.team_salary)}</div>${teamSalaryLines(me.salary, me.services)}</div>`;
  }
  const badges = d.my_badges ? `<div class="tm-card"><div class="tm-card-t">${escapeHtml(T.team_badges)}</div>${teamBadgesHtml(d.my_badges)}</div>` : '';
  return head + teamLeaderCard(d, false) + teamBoardCard(d.board, false, MY_EMP_ID) + badges;
}

// ----- карточка сотрудника (владелец) -----
async function openTeamEmp(id, focusPay) {
  TEAM.emp = id;
  const body = document.getElementById('teamModalBody');
  body.innerHTML = escapeHtml(T.stats_loading);
  document.getElementById('teamModal').classList.add('open');
  await renderTeamEmp(focusPay);
}
function closeTeamModal() { document.getElementById('teamModal').classList.remove('open'); TEAM.emp = null; }

async function renderTeamEmp(focusPay) {
  const id = TEAM.emp;
  if (!id) return;
  let d;
  try { d = await (await fetch(`/api/team/emp/${id}?period=${TEAM.period}${teamShopQs()}`, { credentials: 'same-origin', cache: 'no-store' })).json(); }
  catch (e) { return; }
  if (id !== TEAM.emp) return;
  const body = document.getElementById('teamModalBody');
  if (!d.ok) { body.innerHTML = escapeHtml(d.error || T.team_err); return; }
  const r = d.row, s = r.salary, e = d.emp;
  TEAM.empRow = r;
  const posDef = (d.settings.positions || {})[e.position || 'master'] || 0;
  const hist = (d.ops || []).map(o => `<div class="tm-hist ${o.status !== 'active' ? 'cancelled' : ''}">
      <div><b>${o.kind === 'payout' ? escapeHtml(T.team_k_payout) : escapeHtml(T.team_k_adjust)} · ${(o.kind === 'adjust' && o.amount > 0 ? '+' : (o.amount < 0 ? '−' : ''))}${escapeHtml(teamMoney(Math.abs(o.amount)))}</b>
      <small>${escapeHtml(String(o.created_at || '').slice(0, 16))} · ${escapeHtml(teamMonthLabel(o.period))}${o.note ? ' · ' + escapeHtml(o.note) : ''}${o.status === 'removed' ? ' · ' + escapeHtml(T.team_removed) : ''}</small></div>
      ${o.status === 'active' ? `<button type="button" onclick="cancelTeamOp(${o.id})">${escapeHtml(T.cancel)}</button>` : ''}</div>`).join('');
  const posOpts = ['intern', 'master', 'senior', 'expert', 'cashier'].map(k => `<option value="${k}" ${k === (e.position || 'master') ? 'selected' : ''}>${escapeHtml(teamPos(k))}</option>`).join('');
  const v = (x) => (x === null || x === undefined || x === 0 || x === '') ? '' : x;
  body.innerHTML = `<div class="cash-m-title">${escapeHtml(r.name)}</div>
    <div class="cash-m-who">${escapeHtml(teamPos(e.position))} · ${escapeHtml(teamMonthLabel(TEAM.period))}${r.place ? ' · ' + r.place + ' ' + escapeHtml(T.team_place_short) : ''} · ${fmtNum(r.points)} ${escapeHtml(T.team_points)} · ${fmtNum(r.services)} ${escapeHtml(T.team_services)}</div>
    ${teamSalaryLines(s, r.services)}
    <div class="tm-sec">${escapeHtml(T.team_pay_title)} · ${escapeHtml(teamMonthLabel(TEAM.period))}</div>
    <label for="tmPayAmt">${escapeHtml(T.team_pay_amount)}</label>
    <input id="tmPayAmt" inputmode="numeric" autocomplete="off" oninput="teamAmountInput(this)" value="${s.due > 0 ? fmtNum(s.due) : ''}">
    <label for="tmPayNote">${escapeHtml(T.team_pay_note)}</label>
    <input id="tmPayNote" maxlength="200" autocomplete="off">
    <div class="hint-text">${escapeHtml(T.team_pay_hint)}</div>
    <button class="submit cash-ok-btn" type="button" onclick="submitTeamPay()">${escapeHtml(T.team_pay_btn)}</button>
    <div class="tm-sec">${escapeHtml(T.team_adj_title)}</div>
    <div class="hint-text" style="margin-top:0;">${escapeHtml(T.team_adj_hint)}</div>
    <div class="tm-grid2"><input id="tmAdjAmt" data-minus="1" inputmode="text" autocomplete="off" placeholder="+300 000 / −200 000" oninput="teamAmountInput(this)">
      <input id="tmAdjNote" maxlength="200" autocomplete="off" placeholder="${escapeHtml(T.team_adj_note_ph)}"></div>
    <div style="display:flex; gap:6px; margin-top:6px;"><button type="button" class="staff-copy" style="background:#16A34A;" onclick="submitTeamAdjust(1)">+ ${escapeHtml(T.team_adj_plus)}</button>
      <button type="button" class="staff-copy" style="background:#B3241C;" onclick="submitTeamAdjust(-1)">− ${escapeHtml(T.team_adj_minus)}</button></div>
    <div class="tm-sec">${escapeHtml(T.team_pay_rules)}</div>
    <div class="tm-grid2">
      <div><label>${escapeHtml(T.team_f_position)}</label><select id="tmPos" onchange="teamPosHint()">${posOpts}</select></div>
      <div><label>${escapeHtml(T.team_f_fixed)}</label><input id="tmFixed" inputmode="numeric" autocomplete="off" oninput="teamAmountInput(this)" value="${e.salary_fixed !== null && e.salary_fixed !== undefined ? fmtNum(e.salary_fixed) : ''}" placeholder="${escapeHtml(teamFmt(T.team_f_fixed_ph, { sum: fmtNum(posDef) }))}"></div>
      <div><label>${escapeHtml(T.team_f_pct_goods)}</label><input id="tmPctG" inputmode="decimal" autocomplete="off" value="${v(e.pct_goods)}" placeholder="0"></div>
      <div><label>${escapeHtml(T.team_f_pct_work)}</label><input id="tmPctW" inputmode="decimal" autocomplete="off" value="${v(e.pct_work)}" placeholder="0"></div>
      <div><label>${escapeHtml(T.team_f_plan)}</label><input id="tmPlan" inputmode="numeric" autocomplete="off" value="${v(e.plan_services)}" placeholder="0"></div>
      <div><label>${escapeHtml(T.team_f_plan_bonus)}</label><input id="tmPlanBonus" inputmode="numeric" autocomplete="off" oninput="teamAmountInput(this)" value="${e.plan_bonus ? fmtNum(e.plan_bonus) : ''}" placeholder="0"></div>
    </div>
    <div class="hint-text">${escapeHtml(T.team_f_hint)} ${escapeHtml(teamFmt(T.team_terms_from, { month: teamMonthLabel(TEAM.period) }))}</div>
    <button class="submit" type="button" onclick="saveTeamPaySettings()">${escapeHtml(T.team_save)}</button>
    <div class="tm-sec">${escapeHtml(T.team_badges)}</div>${teamBadgesHtml(d.badges)}
    ${hist ? `<div class="tm-sec">${escapeHtml(T.team_history)}</div>${hist}` : ''}`;
  if (focusPay) { const el = document.getElementById('tmPayAmt'); if (el) el.focus(); }
}
function teamPosHint() {
  const pos = document.getElementById('tmPos').value;
  const def = ((TEAM.data && TEAM.data.settings && TEAM.data.settings.positions) || {})[pos] || 0;
  document.getElementById('tmFixed').placeholder = teamFmt(T.team_f_fixed_ph, { sum: fmtNum(def) });
}
async function teamPost(url, payload) {
  try {
    const res = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    return await res.json();
  } catch (e) { return { ok: false, error: T.msg_no_connection || T.team_err }; }
}
function teamShopId() { return (TEAM.shop && TEAM.shop !== 'net') ? TEAM.shop : null; }
async function submitTeamPay() {
  const amount = teamParseAmount(document.getElementById('tmPayAmt').value, false);
  if (amount <= 0) { alertTeam(T.team_err_amount); return; }
  const row = TEAM.empRow;
  const due = row && row.salary ? row.salary.due : 0;
  if (amount > due && !confirm(teamFmt(T.team_pay_over_q, { sum: fmtNum(amount), due: fmtNum(Math.max(0, due)), month: teamMonthLabel(TEAM.period) }))) return;
  const d = await teamPost(`/api/team/emp/${TEAM.emp}/op`, { shop: teamShopId(), period: TEAM.period, kind: 'payout', amount, note: document.getElementById('tmPayNote').value });
  if (!d.ok) { alertTeam(d.error); return; }
  showMsg(T.team_paid_ok, true);
  await renderTeamEmp(); loadTeam();
}
async function submitTeamAdjust(sign) {
  const amount = Math.abs(teamParseAmount(document.getElementById('tmAdjAmt').value, true)) * sign;
  if (!amount) { alertTeam(T.team_err_amount); return; }
  const d = await teamPost(`/api/team/emp/${TEAM.emp}/op`, { shop: teamShopId(), period: TEAM.period, kind: 'adjust', amount, note: document.getElementById('tmAdjNote').value });
  if (!d.ok) { alertTeam(d.error); return; }
  await renderTeamEmp(); loadTeam();
}
async function cancelTeamOp(opId) {
  if (!confirm(T.team_cancel_q)) return;
  const d = await teamPost(`/api/team/op/${opId}/cancel`, { shop: teamShopId() });
  if (!d.ok) { alertTeam(d.error); return; }
  await renderTeamEmp(); loadTeam();
}
async function saveTeamPaySettings() {
  const fixedRaw = document.getElementById('tmFixed').value.trim();
  const payload = {
    shop: teamShopId(), period: TEAM.period, position: document.getElementById('tmPos').value,
    salary_fixed: fixedRaw ? teamParseAmount(fixedRaw, false) : null,
    pct_goods: document.getElementById('tmPctG').value.replace(',', '.'),
    pct_work: document.getElementById('tmPctW').value.replace(',', '.'),
    plan_services: document.getElementById('tmPlan').value,
    plan_bonus: teamParseAmount(document.getElementById('tmPlanBonus').value, false),
  };
  const d = await teamPost(`/api/team/emp/${TEAM.emp}/pay_settings`, payload);
  if (!d.ok) { alertTeam(d.error); return; }
  showMsg(T.team_saved, true);
  await renderTeamEmp(); loadTeam();
}
async function saveTeamSettings() {
  const positions = {};
  ['intern', 'master', 'senior', 'expert', 'cashier'].forEach(k => { positions[k] = teamParseAmount(document.getElementById('tmPos_' + k).value, false); });
  const d = await teamPost('/api/team/settings', { shop: teamShopId(), period: TEAM.period, positions, top_bonus: teamParseAmount(document.getElementById('tmTopBonus').value, false) });
  if (!d.ok) { alertTeam(d.error); return; }
  showMsg(T.team_saved, true);
  loadTeam();
}
function alertTeam(text) { alert(text || T.team_err); }

// ----- «Мастер» в форме замены -----
async function loadTeamMasters() {
  const sel = document.getElementById('master_id');
  if (!sel) return;
  let d;
  try { d = await (await fetch('/api/team/masters', { credentials: 'same-origin' })).json(); } catch (e) { return; }
  if (!d.ok) return;
  TEAM.masters = d.masters;
  const keep = sel.value;
  const opts = IS_EMP_TEAM ? [] : [`<option value="">${escapeHtml(T.team_master_me)}</option>`];
  d.masters.forEach(m => opts.push(`<option value="${m.id}">${escapeHtml(m.name)}</option>`));
  sel.innerHTML = opts.join('');
  if (keep && d.masters.some(m => String(m.id) === keep)) sel.value = keep;
  else if (IS_EMP_TEAM && MY_EMP_ID) sel.value = String(MY_EMP_ID);
}
loadTeamMasters();
function teamFillEditMaster(entry) {
  const sel = document.getElementById('edit_master_id');
  if (!sel) return;
  const list = TEAM.masters || [];
  let cur = '';
  if (entry) cur = entry.master_id === 0 ? '' : String(entry.master_id || entry.employee_id || '');
  const opts = [`<option value="">${escapeHtml(T.team_master_me)}</option>`]
    .concat(list.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`));
  if (cur && !list.some(m => String(m.id) === cur)) opts.push(`<option value="${escapeHtml(cur)}">(${escapeHtml(T.team_inactive)})</option>`);
  sel.innerHTML = opts.join('');
  sel.value = cur;
  sel.dataset.orig = cur;
}
function teamEditMasterPayload() {
  const sel = document.getElementById('edit_master_id');
  if (!sel || sel.value === sel.dataset.orig) return {};
  return { master_id: sel.value };
}

// ---------- Сотрудники: владелец точки сам ----------
let STAFF_SEQ = 0;
function staffFmt(s, vars) { return String(s).replace(/{([a-z_]+)}/g, (m, k) => (k in vars ? vars[k] : m)); }
function staffErr(field, text) {
  ['full_name', 'username', 'password'].forEach(f => {
    const el = document.getElementById('staff_err_' + f);
    if (el) { el.textContent = f === field ? (text || '') : ''; el.classList.toggle('on', f === field && !!text); }
  });
}
function staffShowCreds(title, login, password) {
  const text = staffFmt(T.staff_creds, { url: location.origin + '/login', login: login, password: password });
  const box = document.getElementById('staffCreds');
  box.innerHTML = `<div class="staff-creds"><div class="staff-creds-t">${escapeHtml(title)}</div>
    <div class="staff-creds-v" id="staffCredsText"></div>
    <button type="button" class="staff-copy" onclick="copyStaffCreds(this)">${escapeHtml(T.staff_copy)}</button></div>`;
  document.getElementById('staffCredsText').textContent = text;
  box.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
async function copyStaffCreds(btn) {
  const text = document.getElementById('staffCredsText').textContent;
  try { await navigator.clipboard.writeText(text); }
  catch (e) {
    const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta);
    ta.select(); try { document.execCommand('copy'); } catch (e2) {} ta.remove();
  }
  btn.textContent = T.staff_copied;
}
// ---- Журнал: удаления и правки сумм (видит только владелец) ----
async function loadActionLog() {
  const box = document.getElementById('actionLog');
  if (!box) return;
  let d;
  try { d = await (await fetch('/api/action_log', { credentials: 'same-origin' })).json(); } catch (e) { return; }
  if (!d || !d.ok) return;
  if (!d.log.length) { box.innerHTML = `<div class="hint-text">${escapeHtml(T.alog_empty)}</div>`; return; }
  const sum = v => (v == null ? '—' : fmtNum(v));
  box.innerHTML = d.log.map(r => {
    const x = r.details || {};
    const what = { delete_service: T.alog_delete_service, edit_service: T.alog_edit_service, delete_car: T.alog_delete_car }[r.action] || r.action;
    let info = [x.plate ? `<span class="pl-mini">${escapeHtml(x.plate)}</span>` : '', x.date ? escapeHtml(x.date) : ''].filter(Boolean).join(' · ');
    if (r.action === 'delete_service') info += ` · ${sum(x.cost)} ${T.currency}`;
    if (r.action === 'edit_service' && x.before && x.after) info += ` · ${sum(x.before.cost)} → <b>${sum(x.after.cost)}</b> ${T.currency}`;
    const who = escapeHtml(r.actor || '—') + (r.is_employee ? ` <span class="staff-pill">${escapeHtml(T.alog_employee)}</span>` : '');
    return `<div class="staff-row" style="${r.action === 'edit_service' ? '' : 'border-left:3px solid #DC2626;'}">
      <div class="staff-who"><b>${escapeHtml(what)}</b><span class="hint-text">${info}</span>
        <span class="hint-text">${escapeHtml(String(r.created_at || '').slice(0, 16))} · ${who}</span></div></div>`;
  }).join('');
}
async function loadStaff() {
  loadActionLog();
  const seq = ++STAFF_SEQ;
  let d;
  try { d = await (await fetch('/api/staff', { credentials: 'same-origin' })).json(); } catch (e) { return; }
  if (seq !== STAFF_SEQ || !d || !d.ok) return;
  const box = document.getElementById('staffList');
  if (!d.employees.length) { box.innerHTML = `<div class="hint-text">${escapeHtml(T.staff_empty)}</div>`; return; }
  box.innerHTML = d.employees.map(e => {
    const nm = escapeHtml(JSON.stringify(e.full_name || e.username));
    return `<div class="staff-row ${e.is_active ? '' : 'off'}">
      <div class="staff-who"><b>${escapeHtml(e.full_name || e.username)}</b>
        <span class="hint-text">@${escapeHtml(e.username)}</span>
        <span class="staff-pill ${e.is_active ? 'on' : ''}">${escapeHtml(e.is_active ? T.staff_active : T.staff_off)}</span></div>
      ${e.cash_balance ? `<div class="staff-cash">${escapeHtml(T.cash_in_hand)}: <b>${fmtNum(e.cash_balance)} ${escapeHtml(T.currency)}</b> · <a href="#" onclick="showTab('cash'); return false;">${escapeHtml(T.cash_accept_btn)}</a></div>` : ''}
      <div class="staff-btns">
        <button type="button" onclick="staffResetPw(${e.id}, ${nm}, ${escapeHtml(JSON.stringify(e.username))})"><i class="fa-solid fa-key"></i> ${escapeHtml(T.staff_btn_pw)}</button>
        <button type="button" onclick="staffToggle(${e.id}, ${e.is_active ? 0 : 1}, ${nm})">${e.is_active ? '<i class="fa-solid fa-pause"></i> ' + escapeHtml(T.staff_btn_off) : '<i class="fa-solid fa-play"></i> ' + escapeHtml(T.staff_btn_on)}</button>
        <button type="button" class="del" onclick="staffDelete(${e.id}, ${nm})"><i class="fa-solid fa-trash"></i> ${escapeHtml(T.staff_btn_del)}</button>
      </div></div>`;
  }).join('');
}
async function createStaff() {
  staffErr(null);
  const body = {
    full_name: document.getElementById('staff_name').value.trim(),
    username: document.getElementById('staff_login').value.trim(),
    password: document.getElementById('staff_pw').value,
  };
  if (body.full_name.length < 2) return staffErr('full_name', T.staff_err_name);
  if (!/^[A-Za-z0-9_]{3,30}$/.test(body.username)) return staffErr('username', T.staff_err_login);
  if (body.password && body.password.length < 8) return staffErr('password', T.staff_err_password);
  const res = await fetch('/api/staff', { method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
  const d = await res.json();
  if (!d.ok) { if (d.field) staffErr(d.field, d.error); else alert(d.error || 'Error'); return; }
  ['staff_name', 'staff_login', 'staff_pw'].forEach(id => { document.getElementById(id).value = ''; });
  staffShowCreds(T.staff_created, d.username, d.password);
  loadStaff();
}
async function staffResetPw(id, name, login) {
  if (!confirm(staffFmt(T.staff_confirm_pw, { name: name }))) return;
  const d = await (await fetch(`/api/staff/${id}/reset_password`, { method: 'POST', credentials: 'same-origin' })).json();
  if (!d.ok) { alert(d.error); return; }
  staffShowCreds(T.staff_new_pw, login, d.password);
}
async function staffToggle(id, on, name) {
  if (!on && !confirm(staffFmt(T.staff_confirm_off, { name: name }))) return;
  const d = await (await fetch(`/api/staff/${id}/active`, { method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ active: !!on }) })).json();
  if (!d.ok) { alert(d.error); return; }
  loadStaff();
}
async function staffDelete(id, name) {
  if (!confirm(staffFmt(T.staff_confirm_del, { name: name }))) return;
  const d = await (await fetch(`/api/staff/${id}`, { method: 'DELETE', credentials: 'same-origin' })).json();
  if (!d.ok) { alert(d.error); return; }
  document.getElementById('staffCreds').innerHTML = '';
  loadStaff();
}

// ---------- Касса сотрудника: наличные копятся, пока владелец не примет ----------
const CASH = { seq: 0, data: null, open: {}, acc: null };
function cashMoney(n) { return fmtNum(n) + ' ' + T.currency; }
function cashDate(d) {
  if (!d) return '';
  const p = String(d).slice(0, 10).split('-');
  return p.length === 3 ? `${p[2]}.${p[1]}.${p[0]}` : String(d);
}
function cashDateTime(d) {
  if (!d) return '';
  const t = String(d).slice(11, 16);
  return cashDate(d) + (t ? ' ' + t : '');
}
function cashParse(v) { const n = parseInt(String(v || '').replace(/[^0-9]/g, ''), 10); return isNaN(n) ? 0 : n; }
function cashLines(c) {
  const rows = [];
  if (c.services) rows.push(`<div class="cash-line"><span>${escapeHtml(staffFmt(T.cash_services_n, { n: c.services }))}${c.since ? ' · ' + escapeHtml(staffFmt(T.cash_since, { date: cashDate(c.since) })) : ''}</span><b></b></div>`);
  if (c.services_cash) rows.push(`<div class="cash-line"><span>${escapeHtml(T.cash_from_services)}</span><b>${cashMoney(c.services_cash)}</b></div>`);
  if (c.debt_cash) rows.push(`<div class="cash-line"><span>${escapeHtml(staffFmt(T.cash_from_debts, { n: c.debt_payments }))}</span><b>${cashMoney(c.debt_cash)}</b></div>`);
  if (c.carry) rows.push(`<div class="cash-line"><span>${escapeHtml(T.cash_carry)}</span><b>${c.carry > 0 ? '' : '−'}${cashMoney(Math.abs(c.carry))}</b></div>`);
  if (c.services_card) rows.push(`<div class="cash-line muted"><span>${escapeHtml(T.cash_card_info)}</span><b>${cashMoney(c.services_card)}</b></div>`);
  return rows.length ? `<div class="cash-lines">${rows.join('')}</div>` : '';
}
function cashBalHtml(c) {
  if (c.balance > 0) return `<div class="cash-bal"><span>${escapeHtml(T.cash_in_hand)}</span><b>${cashMoney(c.balance)}</b></div>`;
  if (c.balance < 0) return `<div class="cash-bal neg"><span>${escapeHtml(T.cash_in_hand)}</span><b>−${cashMoney(-c.balance)}</b></div>`;
  return `<div class="cash-bal zero"><b>${escapeHtml(T.cash_zero)}</b></div>`;
}
function cashEntriesHtml(entries) {
  if (!entries || !entries.length) return `<div class="hint-text" style="font-size:12.5px;">${escapeHtml(T.cash_entries_empty)}</div>`;
  return entries.map(x => `<div class="cash-row">
      <div class="cr-l"><b>${escapeHtml(x.plate || '—')}</b><small>${cashDate(x.d)}${x.kind === 'debt' ? ' · ' + escapeHtml(T.cash_kind_debt) : ''}</small></div>
      <div class="cr-r"><b>${cashMoney(x.cash)}</b>${x.card ? `<small>${escapeHtml(T.cash_card_short)} ${fmtNum(x.card)}</small>` : ''}</div>
    </div>`).join('');
}
function cashHistoryHtml(hist, canCancel) {
  if (!hist || !hist.length) return `<div class="hint-text" style="font-size:12.5px;">${escapeHtml(T.cash_hist_empty)}</div>`;
  const lastActive = hist.find(h => h.status === 'active');
  return hist.map(h => {
    const off = h.status !== 'active';
    const partial = !off && h.expected && h.expected !== h.amount;
    return `<div class="cash-row ${off ? 'cancelled' : ''}">
      <div class="cr-l"><b>${cashDateTime(h.created_at)}</b>${h.note ? `<small>${escapeHtml(h.note)}</small>` : ''}${off ? `<small>${escapeHtml(T.cash_hist_cancelled)}</small>` : ''}</div>
      <div class="cr-r"><b>${cashMoney(h.amount)}</b>${partial ? `<small>${escapeHtml(staffFmt(T.cash_hist_of, { sum: fmtNum(h.expected) }))}</small>` : ''}</div>
      ${canCancel && lastActive && lastActive.id === h.id ? `<button type="button" class="cr-x" onclick="cancelCashHandover(${h.id}, ${h.amount})">${escapeHtml(T.cash_hist_cancel)}</button>` : ''}
    </div>`;
  }).join('');
}
async function loadCash() {
  const seq = ++CASH.seq;
  if (IS_EMPLOYEE) {
    let d;
    try { d = await (await fetch('/api/cash/my', { credentials: 'same-origin' })).json(); } catch (e) { return; }
    if (seq !== CASH.seq || !d || !d.ok) return;
    const c = d.cash;
    document.getElementById('cashMy').innerHTML = `
      <div class="cash-total">
        <div class="ct-l">${escapeHtml(T.cash_my_title)}</div>
        <div class="ct-v">${c.balance < 0 ? '−' : ''}${cashMoney(Math.abs(c.balance))}</div>
        <div class="ct-h">${c.last_handover ? escapeHtml(staffFmt(T.cash_my_last, { date: cashDateTime(c.last_handover.created_at), sum: fmtNum(c.last_handover.amount) })) : escapeHtml(T.cash_my_hint)}</div>
      </div>
      <div class="cash-card">${cashLines(c) || `<div class="hint-text" style="margin:0;">${escapeHtml(T.cash_my_hint)}</div>`}</div>
      <div class="cash-card"><div class="cash-sec" style="margin-top:0;">${escapeHtml(T.cash_entries_title)}</div>${cashEntriesHtml(d.entries)}</div>
      <div class="cash-card"><div class="cash-sec" style="margin-top:0;">${escapeHtml(T.cash_hist_title)}</div>${cashHistoryHtml(d.history, false)}</div>`;
    return;
  }
  let d;
  try { d = await (await fetch('/api/cash/staff', { credentials: 'same-origin' })).json(); } catch (e) { return; }
  if (seq !== CASH.seq || !d || !d.ok) return;
  CASH.data = d.staff || [];
  const box = document.getElementById('cashOwner');
  if (!CASH.data.length) { box.innerHTML = `<div class="card"><div class="hint-text" style="margin:0;">${escapeHtml(T.cash_empty_staff)}</div></div>`; return; }
  const total = CASH.data.reduce((a, e) => a + Math.max(0, e.balance), 0);
  box.innerHTML = `
    <div class="cash-total">
      <div class="ct-l">${escapeHtml(T.cash_total_title)}</div>
      <div class="ct-v">${cashMoney(total)}</div>
      <div class="ct-h">${escapeHtml(T.cash_total_hint)}</div>
    </div>` + CASH.data.map(e => `
    <div class="cash-card ${e.is_active ? '' : 'off'}" id="cash_emp_${e.employee_id}">
      <div class="cash-head">
        <div><div class="cash-name">${escapeHtml(e.name)}</div>
          <div class="cash-sub">@${escapeHtml(e.username)}${e.is_active ? '' : ' · ' + escapeHtml(T.staff_off)}</div></div>
        ${cashBalHtml(e)}
      </div>
      ${cashLines(e)}
      ${e.balance < 0 ? `<div class="cash-warn">${escapeHtml(T.cash_negative)}</div>` : ''}
      <div class="cash-btns">
        <button type="button" class="acc" ${e.balance > 0 ? '' : 'disabled'} onclick="openCashAccept(${e.employee_id})"><i class="fa-solid fa-check"></i> ${escapeHtml(T.cash_accept_btn)}</button>
        <button type="button" class="det" onclick="toggleCashDetails(${e.employee_id})"><i class="fa-solid fa-list"></i> ${escapeHtml(T.cash_details)}</button>
      </div>
      <div class="cash-more" id="cash_more_${e.employee_id}" style="display:none;"></div>
    </div>`).join('');
  Object.keys(CASH.open).forEach(id => { if (CASH.open[id]) toggleCashDetails(Number(id), true); });
}
async function toggleCashDetails(id, forceOpen) {
  const box = document.getElementById('cash_more_' + id);
  if (!box) return;
  if (box.style.display !== 'none' && !forceOpen) { box.style.display = 'none'; CASH.open[id] = false; return; }
  CASH.open[id] = true;
  let d;
  try { d = await (await fetch(`/api/cash/staff/${id}`, { credentials: 'same-origin' })).json(); } catch (e) { return; }
  if (!d || !d.ok) return;
  box.innerHTML = `<div class="cash-sec">${escapeHtml(T.cash_entries_title)}</div>${cashEntriesHtml(d.entries)}
    <div class="cash-sec">${escapeHtml(T.cash_hist_title)}</div>${cashHistoryHtml(d.history, true)}`;
  box.style.display = 'block';
}
function openCashAccept(id) {
  const e = (CASH.data || []).find(x => x.employee_id === id);
  if (!e || e.balance <= 0) return;
  CASH.acc = { id: id, expected: e.balance };
  document.getElementById('cashAccWho').textContent = e.name;
  document.getElementById('cashAccExp').textContent = cashMoney(e.balance);
  document.getElementById('cashAccAmount').value = fmtNum(e.balance);
  document.getElementById('cashAccNote').value = '';
  cashAccInput();
  document.getElementById('cashAcceptModal').classList.add('open');
}
function closeCashAccept() {
  document.getElementById('cashAcceptModal').classList.remove('open');
  CASH.acc = null;
}
function cashAccInput() {
  if (!CASH.acc) return;
  const inp = document.getElementById('cashAccAmount');
  const n = cashParse(inp.value);
  const shown = n ? fmtNum(n) : '';
  if (inp.value !== shown) inp.value = shown;
  const rest = CASH.acc.expected - n;
  const restEl = document.getElementById('cashAccRest');
  const btn = document.getElementById('cashAccBtn');
  if (n <= 0 || rest < 0) {
    restEl.textContent = T.cash_err_amount;
    restEl.style.color = '#B3241C';
    btn.disabled = true;
    btn.textContent = T.cash_accept_btn;
    btn.style.opacity = '.5';
    return;
  }
  restEl.style.color = '';
  restEl.textContent = rest > 0 ? staffFmt(T.cash_modal_rest, { sum: fmtNum(rest) }) : T.cash_modal_full;
  btn.disabled = false;
  btn.style.opacity = '';
  btn.textContent = staffFmt(T.cash_modal_confirm, { sum: fmtNum(n) });
}
async function submitCashAccept() {
  if (!CASH.acc) return;
  const amount = cashParse(document.getElementById('cashAccAmount').value);
  if (amount <= 0 || amount > CASH.acc.expected) { cashAccInput(); return; }
  const id = CASH.acc.id;
  let res, d;
  try {
    res = await fetch(`/api/cash/staff/${id}/accept`, { method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ expected: CASH.acc.expected, amount: amount, note: document.getElementById('cashAccNote').value.trim() }) });
    d = await res.json();
  } catch (e) { showMsg(T.msg_error, false); return; }
  if (d && d.ok) {
    closeCashAccept();
    showMsg(T.cash_done, true);
    loadCash();
    return;
  }
  if (d && d.error === 'changed') {
    closeCashAccept();
    alert(staffFmt(T.cash_changed, { sum: fmtNum(d.balance) }));
    loadCash();
    return;
  }
  if (d && d.readonly) { closeCashAccept(); showMsg(d.error, false); return; }
  alert((d && d.error) || T.msg_error);
}
async function cancelCashHandover(hid, amount) {
  if (!confirm(staffFmt(T.cash_cancel_confirm, { sum: fmtNum(amount) }))) return;
  let d;
  try { d = await (await fetch(`/api/cash/handover/${hid}/cancel`, { method: 'POST', credentials: 'same-origin' })).json(); }
  catch (e) { showMsg(T.msg_error, false); return; }
  if (!d || !d.ok) { alert((d && d.error) || T.msg_error); return; }
  showMsg(T.cash_cancel_done, true);
  loadCash();
}

// ---------- Моя точка: телефон, адрес, часы, локация — то, что клиент видит в боте ----------
let MYSHOP_SEQ = 0;
function myShopLocText(s) { return (s.lat != null && s.lon != null) ? `${s.lat}, ${s.lon}` : ''; }
function myShopStatusHtml(s) {
  const miss = [];
  if (!s.phone) miss.push(T.myshop_phone);
  if (!s.address) miss.push(T.myshop_address);
  if (s.lat == null || s.lon == null) miss.push(T.myshop_location);
  return miss.length
    ? `<div class="msg err" style="margin:0 0 10px;">${escapeHtml(staffFmt(T.myshop_missing, { fields: miss.join(', ') }))}</div>`
    : `<div class="msg ok" style="margin:0 0 10px;">${escapeHtml(T.myshop_all_set)}</div>`;
}
async function loadMyShop() {
  const seq = ++MYSHOP_SEQ;
  let d;
  try { d = await (await fetch('/api/my_shop', { credentials: 'same-origin' })).json(); } catch (e) { return; }
  if (seq !== MYSHOP_SEQ || !d || !d.ok) return;
  document.getElementById('myshopList').innerHTML = d.shops.map(s => `
    <div class="card" style="margin-top:16px;">
      <label style="font-size:15px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">${escapeHtml(s.name || '')}${s.is_branch ? ` <span class="hint-text">· ${escapeHtml(T.myshop_branch)}</span>` : ''}</label>
      <div id="ms_status_${s.id}">${myShopStatusHtml(s)}</div>
      <div class="field"><label>${escapeHtml(T.myshop_phone)}</label><input id="ms_phone_${s.id}" maxlength="40" inputmode="tel" placeholder="+998 90 111 22 33" value="${escapeHtml(s.phone)}"></div>
      <div class="field"><label>${escapeHtml(T.myshop_address)}</label><input id="ms_address_${s.id}" maxlength="200" value="${escapeHtml(s.address)}"></div>
      <div class="field"><label>${escapeHtml(T.myshop_hours)}</label><input id="ms_hours_${s.id}" maxlength="80" placeholder="09:00–19:00" value="${escapeHtml(s.hours)}"></div>
      <div class="field"><label>${escapeHtml(T.myshop_location)}</label><input id="ms_loc_${s.id}" placeholder="40.782123, 72.344567" value="${escapeHtml(myShopLocText(s))}">
        <div class="hint-text">${escapeHtml(T.myshop_loc_hint)}</div>
        <button type="button" style="margin-top:8px; display:inline-flex; align-items:center; gap:6px; height:40px; padding:0 14px; border-radius:10px; border:1px solid var(--border); background:#fff; color:var(--blue); font-weight:600; font-size:14px; font-family:inherit; cursor:pointer;" onclick="myShopLocate(${s.id}, this)"><i class="fa-solid fa-location-crosshairs"></i> ${escapeHtml(T.myshop_locate_btn)}</button>
      </div>
      <div class="field"><label>${escapeHtml(T.myshop_offer)}</label><input id="ms_offer_${s.id}" type="number" inputmode="numeric" min="0" max="50" step="1" value="${escapeHtml(s.offer_pct || 0)}">
        <div class="hint-text">${escapeHtml(T.myshop_offer_hint)}</div>
      </div>
      <button class="submit" onclick="saveMyShop(${s.id})">${escapeHtml(T.btn_save)}</button>
      <div id="ms_msg_${s.id}"></div>
      ${s.anpr_token ? `<div style="margin-top:18px; padding-top:14px; border-top:1px solid var(--border);">
        <div style="font-weight:600; color:var(--text); margin-bottom:4px;"><i class="fa-solid fa-tv"></i> ${escapeHtml(T.myshop_display_title)}</div>
        <div class="hint-text" style="margin:0 0 6px;">${escapeHtml(T.myshop_display_hint)}</div>
        ${myShopLinkRow(T.myshop_display_tv, '/display/' + encodeURIComponent(s.anpr_token))}
        ${myShopLinkRow(T.myshop_display_scanner, '/scanner/' + encodeURIComponent(s.anpr_token))}
        <div class="hint-text" style="margin:12px 0 6px;">${escapeHtml(T.myshop_agent_hint)}</div>
        <a href="/download/plate-agent.zip" style="display:inline-flex; align-items:center; gap:6px; height:40px; padding:0 14px; border-radius:10px; border:1px solid var(--border); background:#fff; color:var(--blue); font-weight:600; font-size:14px; text-decoration:none;"><i class="fa-solid fa-download"></i> ${escapeHtml(T.myshop_agent_btn)}</a>
      </div>` : ''}
    </div>`).join('');
}
function myShopLinkRow(label, path) {
  const url = location.origin + path;
  return `<div style="margin-top:10px;">
    <div class="hint-text" style="margin:0 0 4px;">${escapeHtml(label)}</div>
    <div style="display:flex; gap:6px;">
      <input readonly value="${escapeHtml(url)}" style="flex:1; min-width:0;" onclick="this.select()">
      <button type="button" style="flex:none; height:40px; padding:0 12px; border-radius:10px; border:1px solid var(--border); background:#fff; color:var(--blue); font-weight:600; font-size:13px; font-family:inherit; cursor:pointer;" onclick="myShopCopy(this, ${escapeHtml(JSON.stringify(url))})">${escapeHtml(T.myshop_copy)}</button>
    </div></div>`;
}
async function myShopCopy(btn, text) {
  try { await navigator.clipboard.writeText(text); }
  catch (e) {
    const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta);
    ta.select(); try { document.execCommand('copy'); } catch (e2) {} ta.remove();
  }
  btn.textContent = T.myshop_copied;
}
function myShopLocate(id, btn) {
  if (!navigator.geolocation) { alert(T.myshop_loc_failed); return; }
  const label = btn.innerHTML;
  btn.disabled = true; btn.textContent = T.myshop_locating;
  navigator.geolocation.getCurrentPosition(pos => {
    document.getElementById('ms_loc_' + id).value = pos.coords.latitude.toFixed(6) + ', ' + pos.coords.longitude.toFixed(6);
    btn.disabled = false; btn.innerHTML = label;
  }, () => { btn.disabled = false; btn.innerHTML = label; alert(T.myshop_loc_failed); },
  { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
}
async function saveMyShop(id) {
  const val = k => document.getElementById(`ms_${k}_${id}`).value.trim();
  const msg = document.getElementById('ms_msg_' + id);
  const body = { phone: val('phone'), address: val('address'), hours: val('hours'), lat: '', lon: '',
                 offer_pct: val('offer') || 0 };
  const loc = val('loc');
  if (loc) {
    const parts = loc.split(',').map(p => p.trim()).filter(Boolean);
    if (parts.length !== 2 || isNaN(parseFloat(parts[0])) || isNaN(parseFloat(parts[1]))) {
      msg.innerHTML = `<div class="msg err">${escapeHtml(T.myshop_bad_location)}</div>`;
      return;
    }
    body.lat = parts[0]; body.lon = parts[1];
  }
  let d;
  try {
    d = await (await fetch('/api/my_shop/' + id, { method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) })).json();
  } catch (e) { d = { ok: false, error: T.bot_error }; }
  if (!d || !d.ok) { msg.innerHTML = `<div class="msg err">${escapeHtml((d && d.error) || 'Error')}</div>`; return; }
  document.getElementById('ms_status_' + id).innerHTML = myShopStatusHtml(d.shop);
  msg.innerHTML = `<div class="msg ok">${escapeHtml(T.myshop_saved)}</div>`;
}

// ---------- Обучение: карта курса ----------
let COURSE_SEQ = 0;
async function loadCourse() {
  const seq = ++COURSE_SEQ;
  const map = document.getElementById('courseMap');
  const list = document.getElementById('courseList');
  if (!map) return;
  let d;
  try {
    const r = await fetch('/api/course', { credentials: 'same-origin' });
    d = await r.json();
  } catch (e) { return; }
  if (seq !== COURSE_SEQ || !d || !d.ok) return;
  const mods = d.modules;
  const gate = d.gate || {};
  const done = mods.filter(m => m.passed).length;
  // курс закрыт (новая точка без годовой подписки): плашка «в подарок»
  let gateBox = document.getElementById('courseGate');
  if (!gateBox) {
    gateBox = document.createElement('div');
    gateBox.id = 'courseGate';
    const top = document.getElementById('courseTop');
    if (top) top.insertAdjacentElement('afterend', gateBox);
  }
  gateBox.innerHTML = gate.locked ? '<div class="course-gate"><span class="cg-tag">' + escapeHtml(T.cg_tag) + '</span>'
    + '<span class="cg-t">' + escapeHtml(T.cg_title.replace('{n}', gate.months || 12)) + '</span>'
    + '<span class="cg-d">' + escapeHtml(T.cg_desc) + '</span>'
    + (gate.owner ? '<a class="cg-btn" href="/subscription">' + escapeHtml(T.cg_btn) + '</a>' : '<span class="cg-d" style="margin-top:10px;">' + escapeHtml(T.cg_staff) + '</span>')
    + '</div>' : '';
  document.getElementById('courseHead').textContent = done === mods.length
    ? T.course_all_done
    : T.course_head.replace('{done}', done).replace('{left}', mods.length - done);
  // текущий — первый непройденный из ОТКРЫТЫХ модулей
  let cur = mods.find(m => !m.passed && !m.locked);
  const W = map.clientWidth || 340;
  const ROW = 96, TOP = 40;
  const xs = [0.5, 0.78, 0.5, 0.22];
  const pts = mods.map((m, i) => ({ x: Math.round(W * xs[i % 4]), y: TOP + i * ROW }));
  const H = TOP + (mods.length - 1) * ROW + 70;
  map.style.height = H + 'px';
  let path = 'M' + pts[0].x + ' ' + pts[0].y;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i], my = (a.y + b.y) / 2;
    path += ' C' + a.x + ' ' + my + ', ' + b.x + ' ' + my + ', ' + b.x + ' ' + b.y;
  }
  const curIdx = cur ? mods.indexOf(cur) : Math.max(0, mods.filter(m => !m.locked).length - 1);
  let donePath = 'M' + pts[0].x + ' ' + pts[0].y;
  for (let i = 1; i <= curIdx; i++) {
    const a = pts[i - 1], b = pts[i], my = (a.y + b.y) / 2;
    donePath += ' C' + a.x + ' ' + my + ', ' + b.x + ' ' + my + ', ' + b.x + ' ' + b.y;
  }
  let html = '<svg class="course-path" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" aria-hidden="true">'
    + '<path d="' + path + '" fill="none" stroke="rgba(255,255,255,0.14)" stroke-width="1.5" stroke-dasharray="2 7" stroke-linecap="round"/>'
    + (curIdx > 0 ? '<path d="' + donePath + '" fill="none" stroke="#8052ff" stroke-width="2" stroke-linecap="round"/>' : '')
    + '</svg>';
  mods.forEach((m, i) => {
    const p = pts[i];
    const isCur = cur && m.n === cur.n;
    const cls = isCur ? 'cur' : (m.locked ? 'lock' : (m.passed ? 'done' : 'open'));
    const sz = isCur ? 32 : 24;
    const href = m.locked ? (gate.owner ? '/subscription' : '#courseGate') : '/course/' + m.n;
    html += '<a class="cnode ' + cls + '" href="' + href + '" style="left:' + p.x + 'px; top:' + (p.y - sz) + 'px" aria-label="' + escapeHtml(m.n + '. ' + m.title) + '">' + (m.locked ? '<i class="fa-solid fa-lock"></i>' : m.n)
      + (m.passed && m.best != null ? '<span class="cscore">' + m.best + '/10</span>' : '') + '</a>';
  });
  if (cur) {
    const p = pts[curIdx];
    // карточка — на стороне, противоположной следующему кружку, чтобы его не закрывать
    const k = curIdx % 4;
    const toRight = (k === 2 || k === 3);
    const CW = Math.min(140, Math.round(W * 0.4));
    const left = toRight ? Math.min(p.x + 40, W - CW - 4) : Math.max(p.x - 40 - CW, 4);
    html += '<div class="ccard" style="left:' + left + 'px; top:' + (p.y - 58) + 'px; width:' + CW + 'px">'
      + '<span class="cc-meta">' + cur.n + ' · ' + cur.mins + ' ' + T.course_min + '</span>'
      + '<span class="cc-title">' + escapeHtml(cur.title) + '</span>'
      + '<a href="/course/' + cur.n + '">' + (cur.opened ? T.course_continue : T.course_start) + '</a></div>';
  }
  map.innerHTML = html;
  list.innerHTML = mods.map(m => '<a class="course-row' + (m.passed ? ' done' : '') + (m.locked ? ' lock' : '') + '" href="' + (m.locked ? (gate.owner ? '/subscription' : '#courseGate') : '/course/' + m.n) + '"><b>' + String(m.n).padStart(2, '0') + '</b><span class="cr-t">' + escapeHtml(m.title) + '</span>'
    + (m.locked ? '<span class="cr-s"><i class="fa-solid fa-lock"></i></span>' : (m.best != null ? '<span class="cr-s">' + m.best + '/10</span>' : (gate.locked && m.n === 1 ? '<span class="cr-s">' + escapeHtml(T.cg_free) + '</span>' : ''))) + '</a>').join('');
  const prog = document.getElementById('courseProg');
  if (prog) {
    prog.hidden = false;
    document.getElementById('courseProgN').textContent = done + ' / ' + mods.length;
    document.getElementById('courseProgBar').style.width = Math.round(done * 100 / mods.length) + '%';
  }
  const bonusBox = document.getElementById('courseBonus');
  const b = d.bonus;
  if (bonusBox && b) {
    bonusBox.innerHTML = '<a class="course-bonus" id="courseBonusCard" href="' + (b.locked ? (gate.owner ? '/subscription' : '#courseGate') : '/course/' + b.n) + '">'
      + '<span class="cb-tag">' + (b.locked ? '<i class="fa-solid fa-lock"></i> ' + escapeHtml(T.cg_bonus_tag) : escapeHtml(T.course_bonus_tag) + (b.passed ? ' · ' + b.best + '/10' : '')) + '</span>'
      + '<span class="cb-t">' + escapeHtml(b.title) + '</span>'
      + '<span class="cb-d">' + escapeHtml(T.course_bonus_desc) + '</span>'
      + '<span class="cb-foot"><span class="cb-btn">' + (b.locked ? (gate.owner ? T.cg_btn : T.cg_locked_btn) : (b.opened ? T.course_continue : T.course_start)) + '</span>'
      + '<span class="cb-m">' + b.mins + ' ' + T.course_min + '</span></span></a>';
    if (window.DalaFX) DalaFX.attach(document.getElementById('courseBonusCard'), { brain: true, seed: 5, cx: 0.86, r: 0.12 });
  }
  if (window.DalaFX) {
    DalaFX.attach(map.closest('.course-wrap'), { brain: false, seed: 3 });
    DalaFX.attach(document.getElementById('courseTop'), { brain: true, seed: 11 });
  }
}

// Данные на экране не должны «застревать»: если приложение было свёрнуто
// дольше минуты или страница восстановлена из кеша браузера (кнопка «назад»,
// возврат в приложение), тихо перезагружаем открытый раздел — без прокрутки вверх.
function refreshCurrentView() {
  if (CURRENT_TAB === 'add') return;  // форму ввода не трогаем — там могут быть несохранённые данные
  showTab(CURRENT_TAB, true);
  const vis = id => { const el = document.getElementById(id); return el && el.style.display !== 'none'; };
  if (CURRENT_TAB === 'warehouse') {
    if (vis('whBranchesView') && WH.branchId) selectWhBranch(WH.branchId);
    if (vis('whNetworkView')) { WH.net = null; loadNetworkStock(); }
  }
  if (CURRENT_TAB === 'stats' && vis('statsBranchesView')) { loadNetworkCompare(); loadNetwork(); }
}
let HIDDEN_AT = 0;
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { HIDDEN_AT = Date.now(); return; }
  if (HIDDEN_AT && Date.now() - HIDDEN_AT > 60 * 1000) refreshCurrentView();
  HIDDEN_AT = 0;
});
// страницу вернули из памяти браузера (кнопка «назад»): перезагружаем её —
// сервер сверит вход (после «Выйти» откроется страница входа, а не старые
// данные), а неизменённая страница придёт мгновенно (304). Незаконченный
// ввод замены восстановится из черновика.
window.addEventListener('pageshow', e => {
  if (!e.persisted) return;
  try { saveAddDraft(); } catch (x) {}
  document.documentElement.style.visibility = 'hidden';
  location.reload();
});
document.addEventListener('DOMContentLoaded', () => {
  if (new URLSearchParams(location.search).get('tab') === 'course') {
    showTab('course');
    history.replaceState(null, '', '/');
  }
  if (new URLSearchParams(location.search).get('tab') === 'help') {
    showTab('help');
    history.replaceState(null, '', '/');
  }
});

function openMore() {
  document.getElementById('moreSheet').classList.add('open');
  document.getElementById('moreBackdrop').classList.add('open');
}

function closeMore() {
  document.getElementById('moreSheet').classList.remove('open');
  document.getElementById('moreBackdrop').classList.remove('open');
}

(function setupMoreSheet() {
  // в шторке «Ещё» прячем то, что уже есть в нижней панели
  const sheet = document.getElementById('moreSheet');
  if (!sheet) return;
  const inBar = sheet.dataset.bar.split(',');
  sheet.querySelectorAll('[data-more-slot]').forEach(el => {
    if (inBar.includes(el.dataset.moreSlot)) el.classList.add('hidden-in-more');
  });
  // закрытие свайпом вниз
  let startY = null;
  sheet.addEventListener('touchstart', e => { startY = e.touches[0].clientY; }, { passive: true });
  sheet.addEventListener('touchend', e => {
    if (startY !== null && e.changedTouches[0].clientY - startY > 60) closeMore();
    startY = null;
  });
})();

async function refreshNavBadges() {
  // красная цифра — число просроченных долгов (видна на «Долгах» и на «Ещё»)
  try {
    const debts = await (await fetch('/api/debts')).json();
    const overdue = (debts || []).filter(d => d.is_overdue).length;
    document.querySelectorAll('[data-badge="debts"]').forEach(b => {
      b.textContent = overdue;
      b.classList.toggle('show', overdue > 0);
    });
    NAV_BADGES.debts = overdue;
    if (document.getElementById('tab-suppliers')) {
      const sd = await (await fetch('/api/suppliers')).json();
      if (sd && sd.ok) NAV_BADGES.suppliers = sd.totals.overdue_count;
    }
  } catch (e) {}
  renderNavBadges();
}
const NAV_BADGES = { debts: 0, suppliers: 0 };
function renderNavBadges() {
  // поставщики с просроченным долгом — красная цифра на «Поставщиках» и на «Ещё»
  document.querySelectorAll('[data-badge="suppliers"]').forEach(b => {
    b.textContent = NAV_BADGES.suppliers;
    b.classList.toggle('show', NAV_BADGES.suppliers > 0);
  });
  const sheet = document.getElementById('moreSheet');
  const moreBadge = document.getElementById('moreBadge');
  if (sheet && moreBadge) {
    const debtsInMore = !sheet.dataset.bar.split(',').includes('debts');
    const n = (debtsInMore ? NAV_BADGES.debts : 0) + NAV_BADGES.suppliers;
    moreBadge.textContent = n;
    moreBadge.classList.toggle('show', n > 0);
  }
}
refreshNavBadges();
setInterval(refreshNavBadges, 5 * 60 * 1000);

async function saveSmsSettings() {
  const emailEl = document.getElementById('eskiz_email');
  const passwordEl = document.getElementById('eskiz_password');
  if (!emailEl || !passwordEl) return;  // вкладка SMS не отрисована (выключена для этой точки)
  const email = emailEl.value.trim();
  const password = passwordEl.value;
  const res = await fetch('/api/sms_settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email, password})
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.sms_saved, true);
    document.getElementById('eskiz_password').value = '';
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

// ---- Склад ----
let productsCache = [];
let restockingProductId = null;

function renderWarehouseCategoryOptions() {
  const sel = document.getElementById('wh_new_category');
  if (!sel) return;
  const allKeys = FLUID_KEYS.concat(FILTER_KEYS);
  sel.innerHTML = allKeys.map(key => `<option value="${key}">${T[key]}</option>`).join('')
    + `<option value="other">${T.wh_category_other}</option>`;
}

function onWhCategoryChanged() {
  const sel = document.getElementById('wh_new_category');
  const unitRow = document.getElementById('wh_new_unit_row');
  if (unitRow) unitRow.style.display = sel.value === 'other' ? 'block' : 'none';
}

// ---- Склад: одна логика отрисовки для своего склада (ctx 'own', элементы wh*)
// и для склада выбранного филиала у главного (ctx 'br', элементы whb*).
const WH = { hasBranches: false, net: null, branchId: null, branches: [] };
const WHCTX = {
  own: { p: 'wh', products: [], summary: null, cat: 'all', showCost: !IS_BRANCH, shopId: null, name: '' },
  br:  { p: 'whb', products: [], summary: null, cat: 'all', showCost: true, shopId: null, name: '' },
};

async function loadWarehouse() {
  if (IS_EMPLOYEE) { if (STORE_ENABLED) loadStore(); return; }
  renderWarehouseCategoryOptions();
  let data = null;
  try { data = await (await fetch('/api/warehouse/overview')).json(); } catch (e) {}
  if (data && data.ok) {
    productsCache = data.products;
    WHCTX.own.summary = data.summary;
  } else {
    productsCache = await (await fetch('/api/products')).json();
    WHCTX.own.summary = null;
  }
  WHCTX.own.products = productsCache;
  WHCTX.own.name = ((document.querySelector('.side-shop') || {}).textContent || '').trim();
  renderWarehouseSummary('own');
  renderWhCategoryChips('own');
  renderProductCards('own');
  if (STORE_ENABLED) renderStore();
  loadRestockHistory();
  // склад мог поменяться — обновляем списки «марка» в формах замены
  renderItemLists();
  renderSvcItemLists();

  if (!IS_BRANCH) {
    if (document.getElementById('supList')) loadSuppliers();
    try {
      const branches = await (await fetch('/api/my_branches')).json();
      const branchBtn = document.getElementById('subwh-branches');
      WH.hasBranches = branches.length > 0;
      WH.branches = branches;
      const netBtn = document.getElementById('subwh-network');
      if (netBtn) netBtn.style.display = branches.length ? '' : 'none';
      if (branches.length) {
        branchBtn.style.display = '';
        document.getElementById('branchWarehouseSummary').innerHTML = branches.map(b => `
          <div class="whn-shop ${WH.branchId === b.id ? 'active' : ''}" onclick="selectWhBranch(${b.id})">
            <b>${escapeHtml(b.shop_name || b.username)}</b>
            <div class="v">${fmtShort(b.stock_value)} ${T.currency}</div>
            ${T.branch_products_count} ${b.product_count}${b.missing_price_count > 0 ? ` · <span style="color:#B3241C;">⚠️ ${T.branch_missing_price} ${b.missing_price_count}</span>` : ''}
          </div>`).join('');
      } else {
        branchBtn.style.display = 'none';
      }
      fitSubtabs(branchBtn.parentElement);
      renderProductCards('own');
    } catch (e) { /* не главный аккаунт — подвкладку не показываем */ }
  }
}

function whUnit(u) { return u === 'pc' ? T.unit_pc : T.unit_l; }

// ---- «Склад магазина» ----
// Продаём из магазина: в формах замены показываем остаток магазина. Хозяину
// дополнительно — сколько на основном складе (оттуда добирается нехватка).
function sellQty(p) { return STORE_ENABLED && !IS_EMPLOYEE ? (p.shop_qty || 0) : (p.stock_qty || 0); }
function mainQtyOf(p) {
  if (!STORE_ENABLED || IS_EMPLOYEE) return 0;
  return p.main_qty !== undefined ? (p.main_qty || 0) : Math.max(0, (p.stock_qty || 0) - (p.shop_qty || 0));
}
function mainTail(p, unitLabel) {
  const m = mainQtyOf(p);
  return STORE_ENABLED && !IS_EMPLOYEE && m > 0 ? ` · ${T.st_main_short} ${whQty(m)}` : '';
}

const ST = { products: [], summary: null, sel: {}, qty: null };

async function loadStore() {
  // сотрудник: свой запрос (только магазин); хозяин берёт данные основного склада
  let d = null;
  try { d = await (await fetch('/api/store/overview')).json(); } catch (e) {}
  if (d && d.ok) {
    ST.products = d.products;
    ST.summary = d.summary;
    if (!IS_EMPLOYEE) { WHCTX.own.products = d.products; productsCache = d.products; }
  }
  renderStore();
  renderItemLists();
  renderSvcItemLists();
}

function renderStore() {
  if (!IS_EMPLOYEE) { ST.products = WHCTX.own.products || []; ST.summary = WHCTX.own.summary; }
  const k = document.getElementById('stKpis');
  if (!k) return;
  const list = ST.products || [];
  const s = ST.summary || {};
  const inStore = list.filter(p => (p.shop_qty || 0) > 0).length;
  const suggest = list.filter(p => p.store_status !== 'ok' && (p.store_suggest || 0) > 0);
  const boxes = [
    `<div class="wh-kpi"><b>${inStore}</b><span>${T.st_kpi_items}</span></div>`,
    `<div class="wh-kpi ${s.store_low_count ? 'bad' : ''}"><b>${s.store_low_count || 0}</b><span>${T.st_kpi_low}</span></div>`,
    `<div class="wh-kpi ${s.store_out_count ? 'muted' : ''}"><b>${s.store_out_count || 0}</b><span>${T.st_kpi_out}</span></div>`,
  ];
  if (!IS_EMPLOYEE) boxes.push(`<div class="wh-kpi ${suggest.length ? 'bad' : 'good'}"><b>${suggest.length}</b><span>${T.st_kpi_suggest}</span></div>`);
  k.innerHTML = boxes.join('');
  const badge = document.getElementById('stTabBadge');
  if (badge) { badge.textContent = suggest.length || ''; badge.style.display = suggest.length ? '' : 'none'; }

  const att = document.getElementById('stAttention');
  const urgent = list.filter(p => p.store_status !== 'ok' && (IS_EMPLOYEE ? (p.per_day > 0 || (p.shop_qty || 0) > 0) : (p.main_qty || 0) > 0))
    .sort((a, b) => (a.store_days_left ?? 99) - (b.store_days_left ?? 99) || (a.shop_qty || 0) - (b.shop_qty || 0))
    .slice(0, 6);
  if (urgent.length) {
    att.innerHTML = `<div class="wh-att-title">${IS_EMPLOYEE ? T.st_att_title_emp : T.st_att_title}</div>` + urgent.map(p => `
      <div class="wh-att">
        <i class="fa-solid fa-triangle-exclamation" style="color:${(p.shop_qty || 0) <= 0 ? '#DC2626' : '#D97706'};"></i>
        <div class="wa-main"><b>${escapeHtml(p.name)}</b><span>${T.st_in_store} ${whQty(p.shop_qty)} ${whUnit(p.unit)}${IS_EMPLOYEE ? '' : ` · ${T.st_on_main} ${whQty(p.main_qty)} ${whUnit(p.unit)}`}</span></div>
        ${IS_EMPLOYEE ? '' : `<button class="wh-tbtn wh-tbtn-sm" onclick="openStoreMove(${p.id})">+${whQty(p.store_suggest || 0)} ${whUnit(p.unit)}</button>`}
      </div>`).join('');
  } else {
    att.innerHTML = list.length ? `<div class="wh-att-title" style="color:#15803D;"><i class="fa-solid fa-circle-check"></i> ${T.st_att_ok}</div>` : '';
  }
  const btnText = document.getElementById('stMoveBtnText');
  if (btnText) btnText.textContent = T.st_move_btn + (suggest.length ? ` (${suggest.length})` : '');
  renderStoreCards();
}

function storeInfoText(p) {
  const u = whUnit(p.unit);
  if ((p.shop_qty || 0) <= 0) return `<span class="warn">${T.st_kpi_out}</span>${p.per_day ? ` · ~${whQty(p.per_day)} ${u}${T.whs_per_day}` : ''}`;
  if (p.per_day) {
    const cls = p.store_status === 'low' ? 'warn' : '';
    return `~${whQty(p.per_day)} ${u}${T.whs_per_day} · <span class="${cls}">${T.whs_enough_for} ${p.store_days_left} ${T.whs_days}</span>`;
  }
  return p.store_status === 'low' ? `<span class="amber">${T.whs_low_left}</span>` : T.whs_no_sales_yet;
}

function renderStoreCards() {
  const box = document.getElementById('stCards');
  if (!box) return;
  const q = ((document.getElementById('stSearch') || {}).value || '').trim().toLowerCase();
  const rank = { out: 0, low: 1, ok: 2 };
  const all = ST.products || [];
  if (!all.length) { box.innerHTML = `<div class="hint-text" style="padding:14px 0;">${T.st_no_items}</div>`; return; }
  const list = all.filter(p => !q || p.name.toLowerCase().includes(q))
    // сверху — то, что есть в магазине и заканчивается; товары, которых нет нигде, — в конце
    .sort((a, b) => ((a.shop_qty || 0) <= 0 && !(a.main_qty > 0)) - ((b.shop_qty || 0) <= 0 && !(b.main_qty > 0))
      || (rank[a.store_status] ?? 2) - (rank[b.store_status] ?? 2) || a.name.localeCompare(b.name));
  if (!list.length) { box.innerHTML = `<div class="hint-text" style="padding:14px 0;">${T.whs_nothing_found}</div>`; return; }
  box.innerHTML = list.map(p => {
    const st = p.store_status || 'ok';
    const width = p.store_days_left !== null && p.store_days_left !== undefined
      ? Math.min(100, Math.max(3, p.store_days_left / 14 * 100))
      : ((p.shop_qty || 0) > 0 ? 60 : 3);
    const color = st === 'out' ? '#DC2626' : st === 'low' ? '#F59E0B' : '#22C55E';
    const actions = IS_EMPLOYEE ? '' : [
      (p.main_qty || 0) > 0 ? `<button class="wh-tbtn wh-tbtn-sm" onclick="openStoreMove(${p.id})"><i class="fa-solid fa-dolly"></i> ${T.st_move_one}</button>` : '',
      (p.shop_qty || 0) > 0 ? `<button class="wh-tbtn wh-tbtn-icon" title="${T.st_back}" onclick="openStoreQty('back', ${p.id})"><i class="fa-solid fa-rotate-left"></i></button>` : '',
      `<button class="wh-tbtn wh-tbtn-icon" title="${T.st_count}" onclick="openStoreQty('count', ${p.id})"><i class="fa-solid fa-pen"></i></button>`,
    ].join('');
    const sub = IS_EMPLOYEE ? '' : `<div class="whc-store"><i class="fa-solid fa-warehouse"></i> ${T.st_on_main} <b>${whQty(p.main_qty)} ${whUnit(p.unit)}</b></div>`;
    return `
      <div class="whc st-${st}">
        <div class="whc-top">
          <div class="whc-name"><b>${escapeHtml(p.name)}</b><span>${escapeHtml(p.category === 'other' ? T.wh_category_other : (T[p.category] || p.category))}</span></div>
          <div class="whc-qty">${whQty(p.shop_qty)} ${whUnit(p.unit)}</div>
        </div>
        <div class="whc-bar"><i style="width:${width}%; background:${color};"></i></div>
        <div class="whc-info">${storeInfoText(p)}</div>
        ${sub}
        <div class="whc-bottom">
          <span class="whc-price">${p.sell_price ? `${fmtNum(p.sell_price)} ${T.currency}` : '—'}</span>
          <div class="whc-actions">${actions}</div>
        </div>
      </div>`;
  }).join('');
}

// ---- перенос основной склад → магазин ----
function openStoreMove(onlyId) {
  const list = (WHCTX.own.products || []).filter(p => (p.main_qty || 0) > 0);
  if (!list.length) { showMsg(T.st_nothing_main, false); return; }
  ST.sel = {};
  list.forEach(p => {
    const want = onlyId ? p.id === onlyId : (p.store_status !== 'ok' && (p.store_suggest || 0) > 0);
    const qty = p.store_suggest > 0 ? p.store_suggest : '';
    ST.sel[p.id] = { on: !!want, qty: want ? (qty || '') : qty };
  });
  const sr = document.getElementById('smSearch');
  if (sr) sr.value = '';
  renderStoreMoveRows();
  document.getElementById('storeMoveModal').classList.add('open');
  if (onlyId) setTimeout(() => { const el = document.getElementById('sm_q_' + onlyId); if (el) { el.focus(); el.select(); } }, 150);
}

function renderStoreMoveRows() {
  const box = document.getElementById('smRows');
  const q = ((document.getElementById('smSearch') || {}).value || '').trim().toLowerCase();
  const list = (WHCTX.own.products || []).filter(p => (p.main_qty || 0) > 0)
    .filter(p => !q || p.name.toLowerCase().includes(q) || (ST.sel[p.id] || {}).on)
    .sort((a, b) => ((ST.sel[b.id] || {}).on ? 1 : 0) - ((ST.sel[a.id] || {}).on ? 1 : 0) || a.name.localeCompare(b.name));
  box.innerHTML = list.map(p => {
    const s = ST.sel[p.id] || { on: false, qty: '' };
    return `
    <div class="sm-row ${s.on ? 'on' : ''}">
      <input type="checkbox" id="sm_on_${p.id}" ${s.on ? 'checked' : ''} onchange="onStoreMoveEdit(${p.id})">
      <div class="sm-name" onclick="const c=document.getElementById('sm_on_${p.id}'); c.checked=!c.checked; onStoreMoveEdit(${p.id})"><b>${escapeHtml(p.name)}</b><span>${T.st_in_store} ${whQty(p.shop_qty)} · ${T.st_main_short} ${whQty(p.main_qty)} ${whUnit(p.unit)}</span></div>
      <input class="sm-qty" id="sm_q_${p.id}" type="number" min="0" step="${p.unit === 'pc' ? 1 : 0.5}" inputmode="decimal" value="${s.qty}" placeholder="0" oninput="onStoreMoveEdit(${p.id}, true)">
    </div>`;
  }).join('') || `<div class="hint-text" style="padding:10px 0;">${T.whs_nothing_found}</div>`;
  updateStoreMoveCount();
}

function onStoreMoveEdit(id, fromQty) {
  const cb = document.getElementById('sm_on_' + id);
  const qi = document.getElementById('sm_q_' + id);
  const s = ST.sel[id] || (ST.sel[id] = { on: false, qty: '' });
  s.qty = qi.value;
  if (fromQty) { s.on = parseFloat(qi.value) > 0; cb.checked = s.on; }
  else { s.on = cb.checked; if (s.on && !(parseFloat(qi.value) > 0)) qi.focus(); }
  cb.closest('.sm-row').classList.toggle('on', s.on);
  updateStoreMoveCount();
}

function updateStoreMoveCount() {
  const n = Object.values(ST.sel).filter(s => s.on && parseFloat(s.qty) > 0).length;
  const t = document.getElementById('smSubmitText');
  if (t) t.textContent = T.st_move_submit + (n ? ` (${n})` : '');
}

async function submitStoreMove() {
  const lines = Object.entries(ST.sel).filter(([, s]) => s.on && parseFloat(s.qty) > 0)
    .map(([id, s]) => ({ product_id: Number(id), qty: parseFloat(s.qty) }));
  if (!lines.length) { showMsg(T.st_err_empty, false); return; }
  const res = await fetch('/api/store/move', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ lines }) });
  const data = await res.json().catch(() => ({}));
  if (data.ok) {
    closeWhModal('storeMoveModal');
    showMsg(T.st_moved, true);
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + (data.error || ''), false);
  }
}

// ---- вернуть на основной склад / пересчёт магазина ----
function openStoreQty(mode, id) {
  const p = (ST.products || []).find(x => x.id === id);
  if (!p) return;
  ST.qty = { mode, p };
  document.getElementById('sqTitle').textContent = mode === 'back' ? T.st_back : T.st_count;
  document.getElementById('sqHint').innerHTML = `<b>${escapeHtml(p.name)}</b> · ${T.st_now_store} ${whQty(p.shop_qty)} ${whUnit(p.unit)}` + (mode === 'count' ? `<br>${T.st_count_hint}` : '');
  document.getElementById('sqLabel').textContent = (mode === 'back' ? T.st_back_label : T.st_count_label) + ` (${whUnit(p.unit)})`;
  const qi = document.getElementById('sqQty');
  qi.value = mode === 'back' ? '' : Math.round((p.shop_qty || 0) * 100) / 100;
  document.getElementById('sqReason').value = '';
  document.getElementById('sqReasonWrap').style.display = mode === 'count' ? '' : 'none';
  document.getElementById('storeQtyModal').classList.add('open');
  setTimeout(() => { qi.focus(); qi.select(); }, 150);
}

async function submitStoreQty() {
  if (!ST.qty) return;
  const { mode, p } = ST.qty;
  const v = parseFloat(document.getElementById('sqQty').value);
  if (isNaN(v) || v < 0 || (mode === 'back' && v <= 0)) { showMsg(T.st_err_qty, false); return; }
  const res = mode === 'back'
    ? await fetch('/api/store/move', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ back: true, lines: [{ product_id: p.id, qty: v }] }) })
    : await fetch('/api/store/count/' + p.id, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ qty: v, reason: document.getElementById('sqReason').value.trim() }) });
  const data = await res.json().catch(() => ({}));
  if (data.ok) {
    closeWhModal('storeQtyModal');
    showMsg(mode === 'back' ? T.st_backed : T.whe_saved, true);
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + (data.error || ''), false);
  }
}
function whQty(q) { return (Math.round((q || 0) * 100) / 100).toLocaleString('ru-RU'); }
function whEl(key, suffix) { return document.getElementById(WHCTX[key].p + suffix); }

function renderWarehouseSummary(key) {
  const ctx = WHCTX[key];
  const kpis = whEl(key, 'Kpis');
  if (!kpis) return;
  const s = ctx.summary;
  if (!s) { kpis.innerHTML = ''; return; }
  const problems = (s.low_count || 0) + (s.out_count || 0);
  const boxes = [];
  if (ctx.showCost) {
    const usdLine = (v, sign) => (USD_RATE > 0 && v != null) ? `<em class="wh-kpi-usd">≈ ${v < 0 ? '−' : (sign && v > 0 ? '+' : '')}${fmtUsdShort(Math.round(Math.abs(v) / USD_RATE))}</em>` : '';
    boxes.push(`<div class="wh-kpi"><b>${fmtShort(s.stock_value)}</b><span>${T.whs_kpi_value}</span>${usdLine(s.stock_value, false)}</div>`);
    const neg = s.potential_margin < 0;
    boxes.push(`<div class="wh-kpi ${neg ? 'bad' : 'good'}"><b>${neg ? '' : '+'}${fmtShort(s.potential_margin)}</b><span>${neg ? T.whs_kpi_margin_neg : T.whs_kpi_margin}</span>${usdLine(s.potential_margin, true)}</div>`);
  } else {
    boxes.push(`<div class="wh-kpi"><b>${s.product_count}</b><span>${T.whs_kpi_products}</span></div>`);
    boxes.push(`<div class="wh-kpi"><b>${s.reorder_count}</b><span>${T.whs_kpi_reorder}</span></div>`);
  }
  boxes.push(`<div class="wh-kpi ${problems ? 'bad' : ''}"><b>${problems}</b><span>${T.whs_kpi_low}</span></div>`);
  boxes.push(`<div class="wh-kpi ${s.dead_count ? 'muted' : ''}"><b>${s.dead_count}</b><span>${T.whs_kpi_dead}</span></div>`);
  kpis.innerHTML = boxes.join('') + whHealthHtml(ctx.products || []);
  if (window.glCount) glCount(kpis);

  const att = whEl(key, 'Attention');
  const list = ctx.products;
  const urgent = list.filter(p => p.status === 'out' || p.status === 'low')
    .sort((a, b) => (a.stock_qty || 0) - (b.stock_qty || 0)).slice(0, 6);
  const dead = list.filter(p => p.dead)
    .sort((a, b) => (b.stock_qty * (b.purchase_price || 0)) - (a.stock_qty * (a.purchase_price || 0))).slice(0, 4);
  const noPrice = ctx.showCost && key === 'br' ? list.filter(p => p.purchase_price == null) : [];
  let html = '';
  if (urgent.length) {
    html += `<div class="wh-att-title">${T.whs_att_urgent}</div>` + urgent.map(p => `
      <div class="wh-att">
        <i class="fa-solid fa-triangle-exclamation" style="color:${p.status === 'out' ? '#DC2626' : '#D97706'};"></i>
        <div class="wa-main"><b>${escapeHtml(p.name)}</b><span>${whStatusText(p)}</span></div>
        <button class="wh-tbtn wh-tbtn-sm" onclick="openRestockModal(${p.id}, ${escapeHtml(JSON.stringify(p.name))}, ${ctx.shopId || 'null'})">+ ${T.wh_restock_action}</button>
      </div>`).join('');
  }
  if (noPrice.length) {
    html += `<div class="wh-att-title">${T.whb_att_no_price}</div>` + noPrice.slice(0, 6).map(p => `
      <div class="wh-att">
        <i class="fa-solid fa-tag" style="color:#B3241C;"></i>
        <div class="wa-main"><b>${escapeHtml(p.name)}</b><span>${T.whb_no_price_hint}</span></div>
        <button class="wh-tbtn wh-tbtn-sm" onclick="openEditProductModal('br', ${p.id})">${T.whb_set_price}</button>
      </div>`).join('');
  }
  if (dead.length) {
    html += `<div class="wh-att-title">${T.whs_att_dead}</div>` + dead.map(p => `
      <div class="wh-att">
        <i class="fa-solid fa-hourglass-half" style="color:#94A3B8;"></i>
        <div class="wa-main"><b>${escapeHtml(p.name)}</b><span>${whQty(p.stock_qty)} ${whUnit(p.unit)}${ctx.showCost && p.purchase_price ? ` · ${T.whs_frozen} ${fmtShort(p.stock_qty * p.purchase_price)} ${T.currency}` : ''}</span></div>
      </div>`).join('');
  }
  if (!html && list.length) html = `<div class="wh-att-title" style="color:#15803D;"><i class="fa-solid fa-circle-check"></i> ${T.whs_att_ok}</div>`;
  if (key === 'own' && ctx.showCost && s) {
    if (s.usd_setup_done === false && list.some(p => p.purchase_price != null)) {
      html = `<div class="rate-banner" style="cursor:pointer;" onclick="showTab('rate')"><i class="fa-solid fa-dollar-sign"></i> ${T.usd_wh_banner} <b>${T.usd_wh_banner_btn} →</b></div>` + html;
    } else if (s.usd_reval && s.usd_reval.reval_amount) {
      const r = s.usd_reval;
      html = `<div class="rate-banner ok" style="cursor:pointer;" onclick="showTab('rate')"><i class="fa-solid fa-dollar-sign"></i> ${T.usd_wh_reval} ${rateFmt(r.prev_rate)} → ${rateFmt(r.rate)} (${rateDate(r.set_at)}): <b>${r.reval_amount > 0 ? '+' : '−'}${fmtShort(Math.abs(r.reval_amount))} ${T.currency}</b></div>` + html;
    }
  }
  att.innerHTML = html;
}

function whHealthHtml(list) {
  // инфографика «Здоровье склада»: доля товаров в норме / мало / нет / без продаж
  if (!list.length) return '';
  const out = list.filter(p => p.status === 'out').length;
  const low = list.filter(p => p.status === 'low').length;
  const dead = list.filter(p => p.status !== 'out' && p.status !== 'low' && p.dead).length;
  const ok = list.length - out - low - dead;
  const parts = [[ok, '#22C55E', T.ig_ok], [low, '#F59E0B', T.ig_low], [out, '#EF4444', T.ig_out], [dead, '#94A3B8', T.ig_dead]]
    .filter(x => x[0] > 0);
  const pct = Math.round(ok / list.length * 100);
  return `<div class="ig-health">
    <div class="ig-health-h"><span>${T.ig_health_title}</span><b>${T.ig_health_ok.replace('{pct}', pct)}</b></div>
    <div class="ig-bar">${parts.map(x => `<i style="width:${x[0] / list.length * 100}%; background:${x[1]};"></i>`).join('')}</div>
    <div class="ig-legend">${parts.map(x => `<span style="--c:${x[1]};">${x[2]} <b>${x[0]}</b></span>`).join('')}</div>
  </div>`;
}

function whStatusText(p) {
  const u = whUnit(p.unit);
  if (p.status === 'out') return `<span class="warn">${T.whs_out}</span>${p.per_day ? ` · ~${whQty(p.per_day)} ${u}${T.whs_per_day}` : ''}`;
  if (p.per_day) {
    const cls = p.status === 'low' ? 'warn' : (p.days_left < 14 ? 'amber' : '');
    let t = `~${whQty(p.per_day)} ${u}${T.whs_per_day} · <span class="${cls}">${T.whs_enough_for} ${p.days_left} ${T.whs_days}</span>`;
    if (p.reorder_qty > 0) t += ` · ${T.whs_order} ${whQty(p.reorder_qty)} ${u}`;
    return t;
  }
  if (p.dead) return T.whs_no_sales_30;
  if (p.status === 'low') return `<span class="amber">${T.whs_low_left}</span>`;
  return T.whs_no_sales_yet;
}

function renderWhCategoryChips(key) {
  const ctx = WHCTX[key];
  const el = whEl(key, 'CatChips');
  if (!el) return;
  const counts = {};
  ctx.products.forEach(p => { counts[p.category] = (counts[p.category] || 0) + 1; });
  const order = FLUID_KEYS.concat(FILTER_KEYS, ['other']).filter(k => counts[k]);
  if (ctx.cat !== 'all' && !counts[ctx.cat]) ctx.cat = 'all';
  el.innerHTML = [`<div class="brand-chip ${ctx.cat === 'all' ? 'active' : ''}" onclick="setWhCat('${key}', 'all')">${T.whs_all}<span class="bc-sub">${ctx.products.length}</span></div>`]
    .concat(order.map(k => `<div class="brand-chip ${ctx.cat === k ? 'active' : ''}" onclick="setWhCat('${key}', '${k}')">${escapeHtml(k === 'other' ? T.wh_category_other : (T[k] || k))}<span class="bc-sub">${counts[k]}</span></div>`))
    .join('');
}

function setWhCat(key, k) {
  WHCTX[key].cat = k;
  renderWhCategoryChips(key);
  renderProductCards(key);
}

function renderProductCards(key) {
  key = key || 'own';
  const ctx = WHCTX[key];
  const box = whEl(key, 'Cards');
  if (!box) return;
  const q = ((whEl(key, 'Search') || {}).value || '').trim().toLowerCase();
  const rank = { out: 0, low: 1, ok: 2 };
  const all = ctx.products;
  const list = all
    .filter(p => ctx.cat === 'all' || p.category === ctx.cat)
    .filter(p => !q || p.name.toLowerCase().includes(q))
    .sort((a, b) => (rank[a.status] ?? 2) - (rank[b.status] ?? 2) || a.name.localeCompare(b.name));
  const maxStock = Math.max(1, ...all.map(p => p.stock_qty || 0));

  const btn = whEl(key, 'PurchaseBtn');
  if (btn) {
    const n = all.filter(p => p.reorder_qty > 0 || p.status === 'out').length;
    btn.querySelector('span').textContent = `${T.whs_purchase_list}${n ? ` (${n})` : ''}`;
  }

  if (!all.length) { box.innerHTML = `<div class="hint-text" style="padding:14px 0;">${T.wh_no_products}</div>`; return; }
  if (!list.length) { box.innerHTML = `<div class="hint-text" style="padding:14px 0;">${T.whs_nothing_found}</div>`; return; }

  const canTransfer = !IS_BRANCH && WH.hasBranches;
  const storeOwn = STORE_ENABLED && key === 'own';
  box.innerHTML = list.map(p => {
    const st = p.status || 'ok';
    const width = (p.days_left !== null && p.days_left !== undefined)
      ? Math.min(100, Math.max(3, p.days_left / 60 * 100))
      : Math.min(100, Math.max(3, (p.stock_qty || 0) / maxStock * 100));
    const color = st === 'out' ? '#DC2626' : st === 'low' ? '#F59E0B' : (p.dead ? '#CBD5E1' : '#22C55E');
    const missingPrice = key === 'br' && p.purchase_price == null;
    const price = [
      p.sell_price ? `${fmtNum(p.sell_price)} ${T.currency}` : '',
      ctx.showCost && p.purchase_price ? `${T.whs_buy} ${fmtNum(p.purchase_price)}${p.purchase_currency === 'USD' && p.purchase_usd_cents != null ? `<span class="usd-tag">${fmtUsdShort(p.purchase_usd_cents / 100)}</span>` : ''}` : '',
      ctx.showCost && p.margin_pct !== null && p.margin_pct !== undefined
        ? (p.margin_pct < 0 ? `<span style="color:#B91C1C; font-weight:700;">⚠️ ${p.margin_pct}% ${T.whs_below_cost}</span>` : `<span class="mg">+${p.margin_pct}%</span>`) : '',
      missingPrice ? `<span style="color:#B3241C; font-weight:700;">⚠️ ${T.branch_missing_price.replace(':', '')}</span>` : '',
    ].filter(Boolean).join(' · ');
    const name = escapeHtml(JSON.stringify(p.name));
    const shopArg = ctx.shopId || 'null';
    const actions = [
      `<button class="wh-tbtn wh-tbtn-sm" onclick="openRestockModal(${p.id}, ${name}, ${shopArg})">+ ${T.wh_restock_action}</button>`,
      `<button class="wh-tbtn wh-tbtn-icon" title="${T.whe_title}" onclick="openEditProductModal('${key}', ${p.id})"><i class="fa-solid fa-pen"></i></button>`,
      canTransfer ? `<button class="wh-tbtn wh-tbtn-icon" title="${T.whn_transfer}" onclick="openTransferModal({fromShop: ${shopArg}, productId: ${p.id}})"><i class="fa-solid fa-right-left"></i></button>` : '',
      key === 'own' ? `<button class="wh-tbtn wh-tbtn-icon" title="${T.wh_delete_action}" onclick="deleteProduct(${p.id}, ${name})"><i class="fa-solid fa-trash-can"></i></button>` : '',
    ].join('');
    return `
      <div class="whc st-${st}">
        <div class="whc-top">
          <div class="whc-name"><b>${escapeHtml(p.name)}</b><span>${escapeHtml(p.category === 'other' ? T.wh_category_other : (T[p.category] || p.category))}</span></div>
          <div class="whc-qty">${whQty(storeOwn ? p.main_qty : p.stock_qty)} ${whUnit(p.unit)}</div>
        </div>
        <div class="whc-bar"><i style="width:${width}%; background:${color};"></i></div>
        <div class="whc-info">${whStatusText(p)}</div>
        ${storeOwn ? `<div class="whc-store"><i class="fa-solid fa-store"></i> ${T.st_in_store} <b>${whQty(p.shop_qty)} ${whUnit(p.unit)}</b>${p.store_status !== 'ok' && (p.main_qty || 0) > 0 ? ` · <a href="javascript:void(0)" onclick="openStoreMove(${p.id})">${T.st_move_one} →</a>` : ''}</div>` : ''}
        <div class="whc-bottom">
          <span class="whc-price">${price || '—'}</span>
          <div class="whc-actions">${actions}</div>
        </div>
      </div>`;
  }).join('');
}

function openAddProductModal() {
  renderWarehouseCategoryOptions();
  if (WHCTX.own.cat !== 'all') document.getElementById('wh_new_category').value = WHCTX.own.cat;
  onWhCategoryChanged();
  document.getElementById('addProductModal').classList.add('open');
}

function closeWhModal(id) {
  document.getElementById(id).classList.remove('open');
}

// ---- список закупки ----
function openPurchaseList(key) {
  key = key || 'own';
  const ctx = WHCTX[key];
  let items = ctx.products
    .filter(p => p.reorder_qty > 0 || p.status === 'out')
    .sort((a, b) => (a.days_left ?? -1) - (b.days_left ?? -1));
  // свой склад и есть поставщики — группируем список по поставщикам
  const grouped = key === 'own' && !IS_BRANCH && SUP.list.length > 0;
  const supKey = p => p.supplier_id ? '0' + supName(p.supplier_id).toUpperCase() : '1';
  if (grouped) items = items.slice().sort((a, b) => supKey(a).localeCompare(supKey(b)));
  let lastSup = -1;
  const groupHead = p => {
    if (!grouped || (p.supplier_id || 0) === lastSup) return '';
    lastSup = p.supplier_id || 0;
    return `<div class="pl-group">${escapeHtml(supName(p.supplier_id))}</div>`;
  };
  const orderBtn = document.getElementById('plOrderBtn');
  if (orderBtn) orderBtn.style.display = key === 'own' ? '' : 'none';
  document.getElementById('purchaseListBody').innerHTML = items.length ? items.map(p => groupHead(p) + `
    <div class="pl-row">
      <input type="checkbox" id="pl_on_${p.id}" checked>
      <div class="pl-name"><b>${escapeHtml(p.name)}</b><span>${T.whs_now} ${whQty(p.stock_qty)} ${whUnit(p.unit)}${p.per_day ? ` · ~${whQty(p.per_day)}${T.whs_per_day}` : ''}</span></div>
      <input type="number" id="pl_qty_${p.id}" value="${p.reorder_qty || ''}" placeholder="${T.whn_qty}" min="0">
      <span style="font-size:12px; color:#64748B;">${whUnit(p.unit)}</span>
    </div>`).join('') : `<div class="hint-text" style="padding:10px 0;">${T.whs_purchase_empty}</div>`;
  WH.purchaseItems = items;
  WH.purchaseShopName = ctx.name;
  document.getElementById('purchaseListModal').classList.add('open');
}

function buildPurchaseText() {
  const lines = [];
  (WH.purchaseItems || []).forEach(p => {
    const on = document.getElementById('pl_on_' + p.id);
    const qty = parseFloat((document.getElementById('pl_qty_' + p.id) || {}).value);
    if (on && on.checked && qty > 0) lines.push(`${lines.length + 1}. ${p.name} — ${whQty(qty)} ${whUnit(p.unit)}`);
  });
  if (!lines.length) return '';
  return `${T.whs_order_title} — ${(WH.purchaseShopName || '').trim()} (${fmtDate(new Date())})\\n` + lines.join('\\n');
}

async function sendPurchaseList(mode) {
  const text = buildPurchaseText();
  if (!text) { showMsg(T.whs_purchase_pick, false); return; }
  if (mode === 'tg') {
    window.open('https://t.me/share/url?url=' + encodeURIComponent(' ') + '&text=' + encodeURIComponent(text), '_blank');
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showMsg(T.whs_copied, true);
  } catch (e) {
    prompt(T.whs_copy, text);
  }
}

// ---- Поставщики и заказы поставщику (главная / самостоятельная точка) ----
// Путь заказа: черновик → отправлен → получен (товар лёг на склад с ценами
// закупки) → раздан по филиалам. Поставщик необязателен: заказ «Без
// поставщика» — это просто список покупок (например, поездка на рынок).
const SUP = { list: [], loaded: false, editId: null, assignId: null, checked: new Set() };
const ORD = { list: [], cur: null, mode: 'view', dist: null, distFor: null, limit: 40, total: 0, filter: 'active' };

async function ordFetch(url, method, body) {
  try {
    const opts = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return await (await fetch(url, opts)).json();
  } catch (e) { return { ok: false, error: 'network' }; }
}
function ordErr(d) {
  const code = (d && d.error) || '';
  let text = T['ord_err_' + code] || T['sup_err_' + code] || (T.msg_error + ' ' + code);
  if (code === 'problems' && d.problems) text = T.ord_err_not_enough + ': ' + d.problems.map(p => escapeHtml(p.name || '')).join(', ');
  else if (d && d.name) text += ': ' + escapeHtml(d.name);
  return text;
}
function ordDate(s) { return s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : ''; }
function supName(id) {
  const s = SUP.list.find(x => x.id === id);
  return s ? s.name : T.ord_no_supplier;
}
function whCatName(c) { return c === 'other' ? T.wh_category_other : (T[c] || c || ''); }

// ---- раздел «Поставщики» (главное меню) ----
// Долг ведётся в сумах; $ — справочно: в каждой операции сохранён курс того
// дня, а общий долг пересчитывается по текущему курсу (как на «Складе»).
function fmtUsd(x) {
  x = Number(x || 0);
  const v = Math.abs(x) >= 100 ? Math.round(x) : Math.round(x * 100) / 100;
  return '$' + v.toLocaleString('ru-RU');
}
function usdTail(sum) { return USD_RATE && sum ? ' · ≈ ' + fmtUsd(sum / USD_RATE) : ''; }
function supRateStr(r) { return r ? Number(r).toLocaleString('ru-RU') : ''; }

async function ensureOwnProducts() {
  // заказам нужны товары своего склада — подгружаем, если «Склад» ещё не открывали
  if (WHCTX.own.products && WHCTX.own.products.length) return;
  try {
    const d = await (await fetch('/api/warehouse/overview')).json();
    if (d && d.ok) { productsCache = d.products; WHCTX.own.products = d.products; WHCTX.own.summary = d.summary; }
  } catch (e) {}
}

async function loadSuppliersTab() {
  await ensureOwnProducts();
  await Promise.all([loadSuppliers(), loadOrders()]);
}
const loadOrdersTab = loadSuppliersTab;

async function loadSuppliers() {
  const d = await ordFetch('/api/suppliers');
  if (d.ok) {
    SUP.list = d.suppliers; SUP.loaded = true; SUP.botReady = !!d.bot_ready;
    SUP.totals = d.totals; SUP.archived = d.archived_count || 0;
    NAV_BADGES.suppliers = (d.totals && d.totals.overdue_count) || 0;
    renderNavBadges();
  }
  renderSuppliers();
}

function supInitials(name) {
  const w = String(name || '?').replace(/[«»"'()\\-]/g, ' ').trim().split(/\\s+/).filter(Boolean);
  return ((w[0] || '?')[0] + (w[1] ? w[1][0] : (w[0] || '').slice(1, 2))).toUpperCase();
}
function supDaysBetween(a, b) { return Math.round((new Date(b + 'T00:00:00') - new Date(a + 'T00:00:00')) / 86400000); }
function supToday() { return fmtDate(new Date()); }
// цвет и подпись статуса: r — просрочка, a — скоро платить, b — долг без срока / переплата, g — долга нет
function supStatus(s, d) {
  const bal = d ? d.balance : s.balance, overdue = d ? d.overdue : s.overdue;
  const oldest = d ? d.oldest_overdue : s.oldest_overdue, next = d ? d.next_due : s.next_due;
  if (overdue > 0) {
    const n = oldest ? supDaysBetween(oldest, supToday()) : 0;
    return { c: 'r', t: n >= 60 ? T.sp_chip_overdue_months.replace('{n}', Math.floor(n / 30)) : n > 0 ? T.sp_chip_overdue_days.replace('{n}', n) : T.sp_st_overdue };
  }
  if (bal > 0 && next) {
    const n = supDaysBetween(supToday(), next.date);
    return { c: n <= 3 ? 'a' : 'b', t: n <= 0 ? T.sp_chip_today : T.sp_chip_due.replace('{date}', ordDate(next.date).slice(0, 5)).replace('{n}', n) };
  }
  if (bal > 0) return { c: 'b', t: T.sp_st_no_terms };
  if (bal < 0) return { c: 'b', t: T.sp_st_overpaid };
  return { c: 'g', t: T.sd_no_debt };
}
function supShort(n) { return fmtShort(Math.round(n || 0)); }

function renderSupRatePill() {
  const el = document.getElementById('spRatePill');
  if (!el) return;
  el.textContent = USD_RATE ? '$ ' + Number(USD_RATE).toLocaleString('ru-RU') : T.sp_rate_none;
  el.classList.toggle('warn', !USD_RATE);
}

function renderSuppliers() {
  const el = document.getElementById('supList');
  if (!el) return;
  renderSupRatePill();
  const t = SUP.totals || { owe: 0, overdue: 0, overpaid: 0, overdue_count: 0 };
  const owing = SUP.list.filter(s => s.balance > 0).length;
  const hero = document.getElementById('spHero');
  if (hero) {
    if (t.owe > 0) {
      const op = Math.min(100, Math.round(t.overdue / t.owe * 100));
      hero.innerHTML = `<div class="sp-hero">
        <div class="l">${T.sp_hero_title}</div>
        <div class="x">${supShort(t.owe)}<small>${T.currency}</small></div>
        <div class="u">${USD_RATE ? '≈ ' + fmtUsd(t.owe / USD_RATE) + ' · ' : ''}${T.sp_hero_sup.replace('{n}', owing)}${t.overpaid > 0 ? ' · ' + T.sp_st_overpaid + ' ' + supShort(t.overpaid) : ''}</div>
        <div class="sp-bar">${op ? `<i class="o" style="width:${op}%"></i>` : ''}<i class="k" style="width:${100 - op}%"></i></div>
        <div class="sp-leg">${t.overdue > 0 ? `<span class="o">${T.sp_leg_overdue} ${supShort(t.overdue)}</span>` : ''}<span class="k">${T.sp_leg_ok} ${supShort(t.owe - t.overdue)}</span></div>
      </div>`;
    } else {
      hero.innerHTML = `<div class="sp-hero zero"><div class="l">${T.sp_hero_title}</div><div class="x">0<small>${T.currency}</small></div>
        <div class="u">${SUP.list.length ? T.sp_hero_zero : T.sp_hero_empty}${t.overpaid > 0 ? ' · ' + T.sp_st_overpaid + ' ' + supShort(t.overpaid) : ''}</div></div>`;
    }
  }
  const list = SUP.list.slice().sort((a, b) => (b.overdue > 0) - (a.overdue > 0) || b.balance - a.balance || a.name.localeCompare(b.name));
  el.innerHTML = list.length ? list.map(s => {
    const st = supStatus(s);
    const amt = s.balance ? `<b>${supShort(Math.abs(s.balance))}</b><span>${USD_RATE ? '≈ ' + fmtUsd(Math.abs(s.balance) / USD_RATE) : T.currency}</span>` : `<b>0</b><span>${T.currency}</span>`;
    return `<div class="sp-row" onclick="openSupplierCard(${s.id})">
      <div class="sp-av ${st.c}">${escapeHtml(supInitials(s.name))}</div>
      <div class="sp-mid"><div class="sp-nm">${escapeHtml(s.name)}${s.tg_connected ? ' <i class="fa-brands fa-telegram" style="color:#229ED9; font-size:13px;"></i>' : ''}</div><span class="sp-chip ${st.c}">${st.t}</span></div>
      <div class="sp-amt">${amt}${s.balance > 0 ? `<br><button class="sp-pay" onclick="event.stopPropagation(); openSupplierCard(${s.id}, 'payment');">${T.sp_pay_btn}</button>` : ''}</div>
    </div>`;
  }).join('') : `<div class="sp-empty">${T.sup_empty}<br><button class="sp-pay" onclick="openSupplierModal()"><i class="fa-solid fa-plus"></i> ${T.sp_menu_add}</button></div>`;
  const ma = document.getElementById('spMenuArchive');
  if (ma) ma.textContent = T.sp_archive + (SUP.archived ? ` (${SUP.archived})` : '');
}

function toggleSupMenu(e) {
  e.stopPropagation();
  document.getElementById('spMenu').classList.toggle('open');
}
function closeSupMenu() { const m = document.getElementById('spMenu'); if (m) m.classList.remove('open'); }
document.addEventListener('click', e => { if (!e.target.closest || !e.target.closest('.sp-menu-wrap')) closeSupMenu(); });

function openSupRate() { showTab('rate'); }

async function openSupArchive() {
  const m = document.getElementById('supCardModal');
  const body = document.getElementById('supCardBody');
  SUP.cardId = null;
  document.getElementById('supCardFoot').innerHTML = '';
  body.innerHTML = `<div class="hint-text" style="padding:14px 0;">${T.stats_loading}</div>`;
  m.classList.add('open');
  const d = await ordFetch('/api/suppliers?archived=1');
  if (!d.ok) { showMsg(ordErr(d), false); closeWhModal('supCardModal'); return; }
  body.innerHTML = `<div class="sp-head"><div class="t">${T.sp_archive}</div></div>
    <div class="hint-text" style="margin-bottom:8px;">${T.sp_archive_hint}</div>
    ${d.suppliers.length ? d.suppliers.map(s => `
      <div class="ord-line">
        <div class="pl-name" style="cursor:pointer;" onclick="openSupplierCard(${s.id})"><b>${escapeHtml(s.name)}</b>
          <span>${s.archived_at ? T.sp_archived_on + ' ' + ordDate(s.archived_at) : ''}${s.balance ? ' · ' + (s.balance > 0 ? T.sd_debt_short + ' ' : T.sp_st_overpaid + ' ') + fmtSum(Math.abs(s.balance)) : ''}</span></div>
        <button class="wh-tbtn wh-tbtn-sm" onclick="restoreSupplier(${s.id})">${T.sp_restore}</button>
      </div>`).join('') : `<div class="hint-text">${T.sp_archive_empty}</div>`}`;
}

async function restoreSupplier(id) {
  const d = await ordFetch(`/api/suppliers/${id}/restore`, 'POST');
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  showMsg(T.sp_restored, true);
  await loadSuppliers();
  openSupplierCard(id);
}

const SUP_FIELDS = ['name', 'phone', 'telegram', 'contact', 'delivery_days', 'note', 'pay_days'];

function openSupplierModal(id) {
  const s = id ? SUP.list.find(x => x.id === id) : null;
  SUP.editId = s ? s.id : null;
  document.getElementById('supModalTitle').textContent = s ? T.sup_edit : T.sup_add;
  SUP_FIELDS.forEach(k => { document.getElementById('sup_' + k).value = s && s[k] != null && s[k] !== '' ? (k === 'telegram' ? '@' + s[k] : s[k]) : ''; });
  document.getElementById('supDeleteBtn').style.display = s ? '' : 'none';
  renderSupTgBlock(s);
  document.getElementById('supplierModal').classList.add('open');
}

function renderSupTgBlock(s) {
  const el = document.getElementById('supTgBlock');
  if (!el) return;
  if (!s || !SUP.botReady) { el.style.display = 'none'; return; }
  el.style.display = '';
  el.innerHTML = `<b>${T.sup_tg_title}</b>
    ${s.tg_connected ? `<span class="ok">✓ ${T.sup_tg_connected}</span>` : `<span class="no">${T.sup_tg_not_connected}</span><div class="hint-text" style="margin-top:4px;">${T.sup_tg_hint}</div>`}
    <div>
      ${s.tg_connected ? '' : `<button class="wh-tbtn wh-tbtn-primary" onclick="shareSupplierLink(${s.id}, 'tg')"><i class="fa-brands fa-telegram"></i> ${T.sup_tg_send_link}</button>`}
      ${s.tg_connected ? '' : `<button class="wh-tbtn" onclick="shareSupplierLink(${s.id}, 'copy')"><i class="fa-regular fa-copy"></i> ${T.sup_tg_copy_link}</button>`}
      ${s.tg_connected ? `<button class="wh-tbtn" onclick="unlinkSupplierTg(${s.id})">${T.sup_tg_unlink}</button>` : ''}
    </div>`;
}

async function shareSupplierLink(id, how) {
  const d = await ordFetch(`/api/suppliers/${id}/tg_link`);
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  const s = SUP.list.find(x => x.id === id) || {};
  const shop = ((document.querySelector('.side-shop') || {}).textContent || '').trim();
  const text = T.sup_tg_invite.replace('{shop}', shop) + '\\n' + d.link;
  if (how === 'tg') {
    if (s.telegram) {
      try { await navigator.clipboard.writeText(text); } catch (e) {}
      window.open('https://t.me/' + encodeURIComponent(s.telegram) + '?text=' + encodeURIComponent(text), '_blank');
    } else {
      window.open('https://t.me/share/url?url=' + encodeURIComponent(d.link) + '&text=' + encodeURIComponent(T.sup_tg_invite.replace('{shop}', shop)), '_blank');
    }
    showMsg(T.sup_tg_after_send, true);
  } else {
    try { await navigator.clipboard.writeText(text); showMsg(T.whs_copied, true); } catch (e) { prompt(T.whs_copy, text); }
  }
}

async function unlinkSupplierTg(id) {
  if (!confirm(T.sup_tg_unlink_confirm)) return;
  const d = await ordFetch(`/api/suppliers/${id}/tg_unlink`, 'POST');
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  await loadSuppliers();
  renderSupTgBlock(SUP.list.find(x => x.id === id));
}

async function saveSupplier() {
  const body = {};
  SUP_FIELDS.forEach(k => { body[k] = document.getElementById('sup_' + k).value; });
  if (!body.name.trim()) { showMsg(T.sup_err_empty_name, false); return; }
  const isNew = !SUP.editId;
  const d = await ordFetch(isNew ? '/api/suppliers' : '/api/suppliers/' + SUP.editId, isNew ? 'POST' : 'PUT', body);
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  closeWhModal('supplierModal');
  showMsg(T.sup_saved, true);
  await loadSuppliers();
  if (!isNew && SUP.cardId === SUP.editId) { openSupplierCard(SUP.editId); return; }
  if (isNew && ordDraftOpen()) { ORD.cur.supplier_id = d.id; loadOrderSuggestion(); }
  // новому поставщику сразу предлагаем отметить его товары
  if (isNew && WHCTX.own.products.length) openSupProducts(d.id);
}

async function deleteSupplierBtn() {
  const cur = SUP.list.find(x => x.id === SUP.editId);
  const warn = cur && cur.balance ? '\\n\\n⚠️ ' + (cur.balance > 0 ? T.sp_archive_debt_warn : T.sp_archive_over_warn).replace('{sum}', fmtSum(Math.abs(cur.balance))) : '';
  if (!SUP.editId || !confirm(T.sup_delete_confirm + warn)) return;
  const d = await ordFetch('/api/suppliers/' + SUP.editId, 'DELETE');
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  WHCTX.own.products.forEach(p => { if (p.supplier_id === SUP.editId) p.supplier_id = null; });
  closeWhModal('supplierModal');
  showMsg(T.sup_deleted, true);
  loadSuppliers();
}

function openSupProducts(id) {
  const s = SUP.list.find(x => x.id === id);
  if (!s) return;
  SUP.assignId = id;
  document.getElementById('supProdTitle').textContent = s.name;
  document.getElementById('supProdSearch').value = '';
  SUP.checked = new Set(WHCTX.own.products.filter(p => p.supplier_id === id).map(p => p.id));
  renderSupProducts();
  document.getElementById('supProductsModal').classList.add('open');
}

function supVisibleProducts() {
  const q = (document.getElementById('supProdSearch').value || '').trim().toLowerCase();
  return WHCTX.own.products
    .filter(p => !q || p.name.toLowerCase().includes(q))
    .sort((a, b) => (a.category || '').localeCompare(b.category || '') || a.name.localeCompare(b.name));
}

function renderSupProducts() {
  const list = supVisibleProducts();
  const el = document.getElementById('supProdList');
  if (!WHCTX.own.products.length) el.innerHTML = `<div class="hint-text" style="padding:10px 0;">${T.wh_no_products}</div>`;
  else if (!list.length) el.innerHTML = `<div class="hint-text" style="padding:10px 0;">${T.whs_nothing_found}</div>`;
  else el.innerHTML = list.map(p => {
    const other = p.supplier_id && p.supplier_id !== SUP.assignId ? ' · ' + T.sup_other_supplier.replace('{name}', escapeHtml(supName(p.supplier_id))) : '';
    return `
      <label class="pl-row" style="cursor:pointer;">
        <input type="checkbox" ${SUP.checked.has(p.id) ? 'checked' : ''} onchange="toggleSupProduct(${p.id}, this.checked)">
        <div class="pl-name"><b>${escapeHtml(p.name)}</b><span>${escapeHtml(whCatName(p.category))}${other}</span></div>
      </label>`;
  }).join('');
  document.getElementById('supProdCount').textContent = T.sup_selected.replace('{n}', SUP.checked.size);
}

function toggleSupProduct(id, on) {
  if (on) SUP.checked.add(id); else SUP.checked.delete(id);
  document.getElementById('supProdCount').textContent = T.sup_selected.replace('{n}', SUP.checked.size);
}

function supSelectVisible(on) {
  supVisibleProducts().forEach(p => { if (on) SUP.checked.add(p.id); else SUP.checked.delete(p.id); });
  renderSupProducts();
}

async function saveSupplierProducts() {
  const id = SUP.assignId;
  const d = await ordFetch(`/api/suppliers/${id}/products`, 'POST', { product_ids: Array.from(SUP.checked) });
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  WHCTX.own.products.forEach(p => {
    if (SUP.checked.has(p.id)) p.supplier_id = id;
    else if (p.supplier_id === id) p.supplier_id = null;
  });
  closeWhModal('supProductsModal');
  showMsg(T.sup_assign_saved, true);
  loadSuppliers();
  if (ordDraftOpen() && ORD.cur.supplier_id === id) loadOrderSuggestion();
}

function ordDraftOpen() {
  const m = document.getElementById('orderModal');
  return !!(m && m.classList.contains('open') && ORD.cur && !ORD.cur.id && ORD.mode === 'edit');
}

// ---- список заказов ----
const ORD_ST_COLORS = { draft: ['#B45309', '#FEF3C7'], sent: ['#0F52BA', '#DBEAFE'], received: ['#7C3AED', '#EDE9FE'],
  done: ['#15803D', '#DCFCE7'], cancelled: ['#64748B', '#F1F5F9'] };
function ordBadge(st) {
  const c = ORD_ST_COLORS[st] || ORD_ST_COLORS.draft;
  return `<span class="ord-badge" style="color:${c[0]}; background:${c[1]};">${T['ord_st_' + st] || st}</span>`;
}

async function loadOrders() {
  const d = await ordFetch('/api/orders?limit=' + ORD.limit);
  if (d.ok) { ORD.list = d.orders; ORD.total = d.total || d.orders.length; }
  renderOrders();
}
function loadMoreOrders() { ORD.limit += 40; loadOrders(); }
const ORD_ACTIVE = ['draft', 'sent', 'received'];
function toggleAllOrders() { ORD.filter = ORD.filter === 'all' ? 'active' : 'all'; renderOrders(); }
function setOrderFilter(f) { ORD.filter = ORD.filter === f ? 'active' : f; renderOrders(); }

function renderOrders() {
  const el = document.getElementById('ordList');
  if (!el) return;
  const f = ORD.filter || 'active';
  const cnt = st => ORD.list.filter(o => st.includes(o.status)).length;
  const drafts = cnt(['draft']), transit = cnt(['sent', 'received']);
  const strip = document.getElementById('ordStrip');
  if (strip) strip.innerHTML = `
    <button class="${f === 'draft' ? 'on' : ''}" onclick="setOrderFilter('draft')"><b>${drafts}</b>${T.sp_ord_drafts}</button>
    <button class="${f === 'transit' ? 'on' : ''}" onclick="setOrderFilter('transit')"><b>${transit}</b>${T.sp_ord_transit}</button>
    <button class="new" onclick="openNewOrder()"><b>+</b>${T.sp_ord_new}</button>`;
  const tg = document.getElementById('ordToggle');
  if (tg) {
    tg.textContent = f === 'all' ? T.sp_ord_active : T.sp_ord_all.replace('{n}', ORD.total || ORD.list.length);
    tg.style.display = (ORD.total || ORD.list.length) ? '' : 'none';
  }
  const shown = ORD.list.filter(o => f === 'all' ? true : f === 'draft' ? o.status === 'draft'
    : f === 'transit' ? ['sent', 'received'].includes(o.status) : ORD_ACTIVE.includes(o.status));
  const more = document.getElementById('ordMoreBtn');
  if (more) more.style.display = f === 'all' && ORD.total > ORD.list.length ? '' : 'none';
  const wrap = document.getElementById('ordWrap');
  if (!shown.length) {
    el.innerHTML = `<div class="hint-text" style="padding:12px 0;">${ORD.list.length ? T.sp_ord_none_active : T.ord_empty}</div>`;
    if (wrap) wrap.style.display = ORD.list.length || f !== 'active' ? '' : 'none';
    return;
  }
  if (wrap) wrap.style.display = '';
  el.innerHTML = shown.map(o => `
    <div class="ord-row" onclick="openOrder(${o.id})" style="cursor:pointer;">
      <div class="sup-main"><b>${T.ord_title_n.replace('{n}', o.number)} · ${escapeHtml(o.supplier_name || T.ord_no_supplier)}</b>
        <span>${ordDate(o.created_at)} · ${o.line_count} ${T.ord_positions}${o.received_sum ? ' · ' + supShort(o.received_sum) + ' ' + T.currency : ''}</span></div>
      ${ordBadge(o.status)}
    </div>`).join('');
}

// ---- окно заказа ----
function ordHasBranches() { return !!(ORD.cur && ORD.cur.shops && ORD.cur.shops.length > 1); }
function ordShopName(id) { const s = ((ORD.cur && ORD.cur.shops) || []).find(x => x.id === +id); return s ? s.name : ''; }
function ordProduct(id) { return WHCTX.own.products.find(p => p.id === id); }

async function openNewOrder(supplierId) {
  if (!SUP.loaded) await loadSuppliers();
  if (supplierId === undefined) supplierId = SUP.list.length ? SUP.list[0].id : null;
  ORD.cur = { id: null, status: 'draft', supplier_id: supplierId || null, lines: [], shops: [] };
  ORD.mode = 'edit';
  document.getElementById('orderModal').classList.add('open');
  await loadOrderSuggestion();
}

async function loadOrderSuggestion() {
  const o = ORD.cur;
  document.getElementById('ordBody').innerHTML = `<div class="hint-text" style="padding:14px 0;">${T.stats_loading}</div>`;
  const d = await ordFetch('/api/orders/suggest?supplier_id=' + (o.supplier_id || ''));
  if (ORD.cur !== o) return;  // окно уже переключили на другой заказ
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  o.shops = d.shops;
  o.lines = d.lines.filter(l => l.qty > 0);
  renderOrderModal();
}

function onOrderSupplierChanged(v) {
  if (v === '__new') {
    // поставщика можно завести прямо отсюда — после сохранения он выберется сам
    document.getElementById('ord_supplier').value = ORD.cur.supplier_id || '';
    openSupplierModal();
    return;
  }
  ORD.cur.supplier_id = v ? parseInt(v, 10) : null;
  loadOrderSuggestion();
}

async function openOrder(id, mode) {
  if (!SUP.loaded) await loadSuppliers();
  const d = await ordFetch('/api/orders/' + id);
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  d.lines.forEach(l => { l.qty = l.qty_ordered; });
  ORD.cur = d;
  ORD.mode = mode || (d.status === 'draft' ? 'edit' : d.status === 'received' ? 'distribute' : 'view');
  document.getElementById('orderModal').classList.add('open');
  renderOrderModal();
}

function renderOrderModal() {
  const o = ORD.cur;
  const steps = ['draft', 'sent', 'received'].concat(ordHasBranches() ? ['done'] : []);
  const idx = { draft: 0, sent: 1, received: 2, done: steps.length - 1 }[o.status];
  const stepper = o.status === 'cancelled' ? '' : `<div class="ord-steps">${steps.map((st, i) =>
    `<div class="ord-step ${i <= idx ? 'on' : ''}">${i + 1} ${T['ord_step_' + st]}</div>`).join('')}</div>`;
  const dates = o.id ? [o.created_at ? `${T.ord_created} ${ordDate(o.created_at)}` : '', o.sent_at ? `${T.ord_sent_at} ${ordDate(o.sent_at)}` : '',
    o.received_at ? `${T.ord_received_at} ${ordDate(o.received_at)}` : ''].filter(Boolean).join(' · ') : '';
  const sup = o.supplier;
  const supLine = o.id ? `<div class="ord-sub">${escapeHtml(sup ? sup.name : T.ord_no_supplier)}${sup && sup.contact ? ' · ' + escapeHtml(sup.contact) : ''}${sup && sup.delivery_days ? ' · ' + escapeHtml(sup.delivery_days) : ''}</div>` : '';
  document.getElementById('ordHead').innerHTML = `
    <div class="ord-title"><b>${o.id ? T.ord_title_n.replace('{n}', o.number) : T.ord_new}</b>${o.id ? ordBadge(o.status) : ''}</div>
    ${supLine}${dates ? `<div class="ord-sub">${dates}</div>` : ''}${stepper}`;
  const render = { edit: renderOrderEdit, send: renderOrderSend, receive: renderOrderReceive, distribute: renderOrderDistribute }[ORD.mode] || renderOrderView;
  render();
}

function renderOrderEdit() {
  const o = ORD.cur;
  const supSel = o.id ? '' : `
    <div class="field"><label>${T.ord_supplier}</label>
      <select id="ord_supplier" onchange="onOrderSupplierChanged(this.value)">
        ${SUP.list.map(s => `<option value="${s.id}" ${o.supplier_id === s.id ? 'selected' : ''}>${escapeHtml(s.name)}</option>`).join('')}
        <option value="" ${!o.supplier_id ? 'selected' : ''}>${T.ord_no_supplier}</option>
        <option value="__new">+ ${T.sup_add}</option>
      </select>
      ${SUP.list.length ? '' : `<div class="hint-text" style="margin-top:6px;">${T.ord_no_suppliers_hint}</div>`}</div>`;
  const rows = o.lines.map((l, i) => {
    const parts = ordHasBranches() && l.alloc ? Object.entries(l.alloc).filter(e => e[1] > 0)
      .map(e => `${escapeHtml(ordShopName(e[0]))} ${whQty(e[1])}`).join(' · ') : '';
    const stock = l.stock_qty !== null && l.stock_qty !== undefined ? `${T.whs_now} ${whQty(l.stock_qty)} ${whUnit(l.unit)}` : '';
    return `
      <div class="ord-line">
        <div class="pl-name"><b>${escapeHtml(l.name)}</b><span>${[stock, parts].filter(Boolean).join(' · ')}</span></div>
        <input type="number" inputmode="decimal" min="0" step="any" value="${l.qty || ''}" oninput="setOrderQty(${i}, this.value)">
        <span class="ord-unit">${whUnit(l.unit)}</span>
        <button class="ord-x" onclick="removeOrderLine(${i})" aria-label="${T.wh_delete_action}"><i class="fa-solid fa-xmark"></i></button>
      </div>`;
  }).join('');
  const inOrder = new Set(o.lines.map(l => l.product_id));
  const mine = p => (p.supplier_id || null) === (o.supplier_id || null);
  const free = WHCTX.own.products.filter(p => !inOrder.has(p.id));
  const opt = p => `<option value="${p.id}">${escapeHtml(p.name)} (${whQty(p.stock_qty)} ${whUnit(p.unit)})</option>`;
  const own = free.filter(mine), others = free.filter(p => !mine(p));
  const addSel = `
    <select id="ord_add" onchange="addOrderLine(this.value)" style="margin-top:10px;">
      <option value="">+ ${T.ord_add_product}</option>
      <option value="__new">✨ ${T.onp_option}</option>
      ${own.length ? `<optgroup label="${o.supplier_id ? T.ord_grp_supplier : T.ord_no_supplier}">${own.map(opt).join('')}</optgroup>` : ''}
      ${others.length ? `<optgroup label="${T.ord_grp_other}">${others.map(opt).join('')}</optgroup>` : ''}
    </select>`;
  const draft = !!o.id;
  document.getElementById('ordBody').innerHTML = `
    ${supSel}
    <div class="hint-text" style="margin-bottom:4px;">${o.lines.length ? T.ord_auto_hint : T.ord_no_lines}</div>
    ${rows}${addSel}
    <div class="ord-total" id="ordTotal"></div>
    <button class="submit" onclick="sendOrder()"><i class="fa-solid fa-paper-plane"></i> ${T.ord_send_btn}</button>
    <button class="submit" onclick="saveOrderDraft()" style="background:var(--border); color:var(--text);">${T.ord_save_draft}</button>
    <button class="submit" onclick="receiveFromDraft()" style="background:#DCFCE7; color:#15803D;"><i class="fa-solid fa-box-open"></i> ${T.ord_receive_now}</button>
    ${draft ? `<button class="submit" onclick="cancelOrderBtn()" style="background:#FEE2E2; color:#B91C1C;">${T.ord_delete_draft}</button>` : ''}`;
  updateOrderTotal();
}

function setOrderQty(i, v) { ORD.cur.lines[i].qty = Math.max(0, parseFloat(v) || 0); updateOrderTotal(); }
function removeOrderLine(i) { ORD.cur.lines.splice(i, 1); renderOrderEdit(); }

function addOrderLine(pid) {
  if (pid === '__new') { document.getElementById('ord_add').value = ''; openOrderNewProduct(); return; }
  const p = ordProduct(parseInt(pid, 10));
  if (!p) return;
  ORD.cur.lines.push({ product_id: p.id, name: p.name, unit: p.unit, stock_qty: p.stock_qty, qty: 0, alloc: {} });
  renderOrderEdit();
  const inputs = document.querySelectorAll('#ordBody .ord-line input');
  if (inputs.length) inputs[inputs.length - 1].focus();
}

function updateOrderTotal() {
  const el = document.getElementById('ordTotal');
  if (!el) return;
  const lines = ORD.cur.lines.filter(l => l.qty > 0);
  let sum = 0;
  lines.forEach(l => { const p = ordProduct(l.product_id); if (p && p.purchase_price) sum += p.purchase_price * l.qty; });
  el.innerHTML = `<span>${lines.length} ${T.ord_positions}</span><span>${sum ? '≈ ' + fmtNum(Math.round(sum)) + ' ' + T.currency : ''}</span>`;
}

async function saveOrderLines(send) {
  const o = ORD.cur;
  const lines = o.lines.filter(l => l.qty > 0).map(l => ({ product_id: l.product_id, qty: l.qty, alloc: l.alloc || {} }));
  if (!lines.length) { showMsg(T.ord_err_empty, false); return null; }
  const d = await ordFetch(o.id ? '/api/orders/' + o.id : '/api/orders', o.id ? 'PUT' : 'POST',
    { supplier_id: o.supplier_id, lines, send: !!send });
  if (!d.ok) { showMsg(ordErr(d), false); return null; }
  return d.id;
}

async function saveOrderDraft() {
  const id = await saveOrderLines(false);
  if (!id) return;
  showMsg(T.ord_saved, true);
  closeWhModal('orderModal');
  loadOrders();
}

async function sendOrder() {
  // поставщик подключён к боту — заказ сразу уходит ему в Telegram
  const sup = SUP.list.find(x => x.id === ORD.cur.supplier_id);
  const viaBot = !!(sup && sup.tg_connected);
  const id = await saveOrderLines(!viaBot);
  if (!id) return;
  if (viaBot) {
    const d = await ordFetch(`/api/orders/${id}/send_tg`, 'POST');
    loadOrders();
    if (d.ok) { showMsg(T.ord_tg_sent, true); await openOrder(id, 'view'); return; }
    showMsg(ordErr(d), false);
    await openOrder(id, 'send');
    return;
  }
  loadOrders();
  await openOrder(id, 'send');
}

async function sendOrderBot() {
  const id = ORD.cur.id;
  const d = await ordFetch(`/api/orders/${id}/send_tg`, 'POST');
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  showMsg(T.ord_tg_sent, true);
  loadOrders();
  await openOrder(id, 'view');
}

async function receiveFromDraft() {
  const id = await saveOrderLines(false);
  if (!id) return;
  loadOrders();
  await openOrder(id, 'receive');
}

async function cancelOrderBtn() {
  const o = ORD.cur;
  if (!o.id) { closeWhModal('orderModal'); return; }
  if (!confirm(o.status === 'draft' ? T.ord_delete_confirm : T.ord_cancel_confirm)) return;
  const d = await ordFetch('/api/orders/' + o.id, 'DELETE');
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  closeWhModal('orderModal');
  loadOrders();
}

// ---- отправка поставщику ----
function orderText() {
  const o = ORD.cur;
  const shop = o.shop || {};
  const lines = o.lines.filter(l => l.qty_ordered > 0)
    .map((l, i) => `${i + 1}. ${l.name} — ${whQty(l.qty_ordered)} ${whUnit(l.unit)}`);
  const tail = [shop.address ? `${T.ord_msg_address}: ${shop.address}` : '', shop.phone ? `${T.ord_msg_phone}: ${shop.phone}` : ''].filter(Boolean);
  return [`${T.ord_title_n.replace('{n}', o.number)} — ${shop.name || ''}`, ordDate(o.sent_at || o.created_at), '']
    .concat(lines, tail.length ? [''].concat(tail) : []).join('\\n');
}

function renderOrderSend() {
  const s = ORD.cur.supplier || {};
  const bot = s.tg_connected ? `<button class="submit" onclick="sendOrderBot()" style="background:#2AABEE;"><i class="fa-solid fa-robot"></i> ${T.ord_send_bot}</button>` : '';
  const invite = !s.tg_connected && s.id && SUP.botReady ? `
    <div class="sup-tg"><b>${T.sup_tg_title}</b><div class="hint-text">${T.ord_tg_connect_hint}</div>
      <button class="wh-tbtn wh-tbtn-primary" onclick="shareSupplierLink(${s.id}, 'tg')"><i class="fa-brands fa-telegram"></i> ${T.sup_tg_send_link}</button></div>` : '';
  document.getElementById('ordBody').innerHTML = `
    <div class="hint-text">${T.ord_send_hint}</div>
    <pre class="ord-text">${escapeHtml(orderText())}</pre>
    ${bot}
    <button class="submit" onclick="sendOrderVia('tg')" style="${s.tg_connected ? 'background:var(--border); color:var(--text);' : 'background:#2AABEE;'}"><i class="fa-brands fa-telegram"></i> ${T.whs_send_tg}${s.telegram ? ' · @' + escapeHtml(s.telegram) : ''}</button>
    ${s.phone ? `<button class="submit" onclick="sendOrderVia('wa')" style="background:#25D366;"><i class="fa-brands fa-whatsapp"></i> WhatsApp · ${escapeHtml(s.phone)}</button>` : ''}
    <button class="submit" onclick="sendOrderVia('copy')" style="background:var(--border); color:var(--text);"><i class="fa-regular fa-copy"></i> ${T.whs_copy}</button>
    <button class="submit" onclick="ORD.mode='view'; renderOrderModal();" style="background:#DBEAFE; color:#0F52BA;">${T.ord_done_btn}</button>
    ${invite}`;
}

async function sendOrderVia(ch) {
  const text = orderText();
  const s = ORD.cur.supplier || {};
  if (ch === 'wa') {
    window.open('https://wa.me/' + (s.phone || '').replace(/\\D/g, '') + '?text=' + encodeURIComponent(text), '_blank');
  } else if (ch === 'tg' && s.telegram) {
    // открываем чат поставщика с уже вписанным текстом (остаётся нажать «Отправить»);
    // на всякий случай текст ещё и копируется — если приложение его не подставит
    try { await navigator.clipboard.writeText(text); } catch (e) {}
    window.open('https://t.me/' + encodeURIComponent(s.telegram) + '?text=' + encodeURIComponent(text), '_blank');
    showMsg(T.ord_tg_pasted, true);
  } else if (ch === 'tg') {
    window.open('https://t.me/share/url?url=' + encodeURIComponent(' ') + '&text=' + encodeURIComponent(text), '_blank');
  } else {
    try { await navigator.clipboard.writeText(text); showMsg(T.whs_copied, true); } catch (e) { prompt(T.whs_copy, text); }
  }
}

// ---- просмотр (отправлен / завершён / отменён) ----
function renderOrderView() {
  const o = ORD.cur;
  const st = o.status;
  let total = 0;
  const rows = o.lines.map(l => {
    if (st !== 'done') {
      return `<div class="ord-line"><div class="pl-name"><b>${escapeHtml(l.name)}</b></div><b>${whQty(l.qty_ordered)} ${whUnit(l.unit)}</b></div>`;
    }
    const sum = (l.qty_received || 0) * (l.purchase_price || 0);
    total += sum;
    const dist = Object.entries(l.dist || {}).filter(e => e[1] > 0).map(e => `${escapeHtml(ordShopName(e[0]))} ${whQty(e[1])}`).join(', ');
    const info = [`${T.ord_ordered} ${whQty(l.qty_ordered)}`, `${T.ord_received} ${whQty(l.qty_received)} ${whUnit(l.unit)}`,
      l.purchase_price ? `${fmtNum(l.purchase_price)} ${T.currency}/${T.whs_per_unit}` : '', dist ? '→ ' + dist : ''].filter(Boolean).join(' · ');
    return `<div class="ord-line"><div class="pl-name"><b>${escapeHtml(l.name)}</b><span>${info}</span></div><b style="white-space:nowrap;">${sum ? fmtNum(Math.round(sum)) : '—'}</b></div>`;
  }).join('');
  const buttons = st === 'sent' ? `
    <button class="submit" onclick="ORD.mode='receive'; renderOrderModal();"><i class="fa-solid fa-box-open"></i> ${T.ord_receive_btn}</button>
    <button class="submit" onclick="ORD.mode='send'; renderOrderModal();" style="background:var(--border); color:var(--text);"><i class="fa-solid fa-paper-plane"></i> ${T.ord_resend}</button>
    <button class="submit" onclick="cancelOrderBtn()" style="background:#FEE2E2; color:#B91C1C;">${T.ord_cancel_btn}</button>` : '';
  document.getElementById('ordBody').innerHTML = `${rows}
    ${st === 'done' && total ? `<div class="ord-total"><span>${T.ord_sum_total}</span><span>${fmtNum(Math.round(total))} ${T.currency}</span></div>` : '<div style="height:10px;"></div>'}
    ${buttons}`;
}

// ---- приёмка ----
function renderOrderReceive() {
  const o = ORD.cur;
  const rows = o.lines.map((l, i) => `
    <div class="ord-recv">
      <div class="pl-name"><b>${escapeHtml(l.name)}</b><span>${T.ord_ordered} ${whQty(l.qty_ordered)} ${whUnit(l.unit)}</span></div>
      <div class="ord-recv-grid">
        <label>${T.ord_received}, ${whUnit(l.unit)}<input type="number" inputmode="decimal" min="0" step="any" id="ordr_q_${i}" value="${l.qty_ordered}" oninput="updateRecvTotal()"></label>
        <label>${T.ord_price_unit}<input type="number" inputmode="numeric" min="0" id="ordr_p_${i}" value="${l.current_price ?? ''}" oninput="updateRecvTotal()"></label>
      </div>
    </div>`).join('');
  document.getElementById('ordBody').innerHTML = `
    <div class="hint-text">${T.ord_receive_hint}</div>
    ${rows}
    <div class="ord-total" id="ordRecvTotal"></div>
    ${o.supplier_id ? `<label class="pl-row" style="cursor:pointer; border:none;"><input type="checkbox" id="ordr_paid"><div class="pl-name"><b>${T.ord_paid_now}</b><span>${T.ord_paid_now_hint}</span></div></label>` : ''}
    <button class="submit" onclick="submitReceive()"><i class="fa-solid fa-check"></i> ${T.ord_accept_btn}</button>
    <button class="submit" onclick="ORD.mode=ORD.cur.status==='draft'?'edit':'view'; renderOrderModal();" style="background:var(--border); color:var(--text);">${T.ord_back}</button>`;
  updateRecvTotal();
}

function readReceiveLines() {
  return ORD.cur.lines.map((l, i) => {
    const pv = document.getElementById('ordr_p_' + i).value;
    return { line_id: l.id, qty_received: Math.max(0, parseFloat(document.getElementById('ordr_q_' + i).value) || 0),
      purchase_price: pv === '' ? null : Math.max(0, Math.round(parseFloat(pv) || 0)) };
  });
}

function updateRecvTotal() {
  const el = document.getElementById('ordRecvTotal');
  if (!el) return;
  let sum = 0;
  readReceiveLines().forEach(r => { sum += r.qty_received * (r.purchase_price || 0); });
  el.innerHTML = `<span>${T.ord_sum_total}</span><span>${fmtNum(Math.round(sum))} ${T.currency}</span>`;
}

async function submitReceive() {
  const lines = readReceiveLines();
  if (!lines.some(r => r.qty_received > 0)) { showMsg(T.ord_err_empty, false); return; }
  if (lines.some(r => r.qty_received > 0 && r.purchase_price === null) && !confirm(T.ord_no_price_confirm)) return;
  const id = ORD.cur.id;
  const paidEl = document.getElementById('ordr_paid');
  const d = await ordFetch(`/api/orders/${id}/receive`, 'POST', { lines, paid_now: !!(paidEl && paidEl.checked) });
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  showMsg(T.ord_received_ok, true);
  ORD.distFor = null;
  loadWarehouse();
  loadOrders();
  loadSuppliers();
  await openOrder(id);
}

// ---- раздача по филиалам ----
function renderOrderDistribute() {
  const o = ORD.cur;
  const branches = o.shops.filter(s => !s.is_head);
  if (ORD.distFor !== o.id) {
    // по умолчанию — доли филиалов из заказа; если пришло меньше, филиалы
    // получают по очереди, сколько хватит
    ORD.dist = o.lines.map(l => {
      let rest = l.qty_received || 0;
      const a = {};
      branches.forEach(b => { const v = Math.min((l.alloc || {})[String(b.id)] || 0, rest); a[b.id] = v; rest -= v; });
      return a;
    });
    ORD.distFor = o.id;
  }
  const rows = o.lines.map((l, i) => (l.qty_received > 0) ? `
    <div class="ord-dist">
      <div class="pl-name"><b>${escapeHtml(l.name)}</b><span>${T.ord_received} ${whQty(l.qty_received)} ${whUnit(l.unit)}</span></div>
      ${branches.map(b => `<label class="ord-dist-row"><span>${escapeHtml(b.name)}</span>
        <input type="number" inputmode="decimal" min="0" step="any" value="${ORD.dist[i][b.id] || ''}" placeholder="0" oninput="setDist(${i}, ${b.id}, this.value)"></label>`).join('')}
      <div class="ord-keep" id="ordKeep_${i}"></div>
    </div>` : '').join('');
  document.getElementById('ordBody').innerHTML = `
    <div class="hint-text">${T.ord_dist_hint}</div>
    ${rows}
    <div style="height:10px;"></div>
    <button class="submit" onclick="submitDistribute()"><i class="fa-solid fa-truck"></i> ${T.ord_dist_btn}</button>
    <button class="submit" onclick="keepAllOrder()" style="background:var(--border); color:var(--text);">${T.ord_keep_all}</button>`;
  o.lines.forEach((l, i) => updateKeep(i));
}

function updateKeep(i) {
  const el = document.getElementById('ordKeep_' + i);
  if (!el) return;
  const l = ORD.cur.lines[i];
  const keep = (l.qty_received || 0) - Object.values(ORD.dist[i]).reduce((a, b) => a + b, 0);
  el.textContent = keep < -1e-9 ? T.ord_err_too_much : `${T.ord_keep_head}: ${whQty(keep)} ${whUnit(l.unit)}`;
  el.classList.toggle('bad', keep < -1e-9);
}

function setDist(i, bid, v) { ORD.dist[i][bid] = Math.max(0, parseFloat(v) || 0); updateKeep(i); }

async function postDistribute(lines) {
  const id = ORD.cur.id;
  const d = await ordFetch(`/api/orders/${id}/distribute`, 'POST', { lines });
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  showMsg(d.branches ? T.ord_distributed_ok : T.ord_received_ok, true);
  loadWarehouse();
  loadOrders();
  await openOrder(id);
}

async function submitDistribute() {
  const o = ORD.cur;
  const lines = [];
  for (let i = 0; i < o.lines.length; i++) {
    const l = o.lines[i];
    const alloc = {};
    let sum = 0;
    Object.entries(ORD.dist[i] || {}).forEach(e => { if (e[1] > 0) { alloc[e[0]] = e[1]; sum += e[1]; } });
    if (sum > (l.qty_received || 0) + 1e-9) { showMsg(T.ord_err_too_much + ': ' + escapeHtml(l.name), false); return; }
    lines.push({ line_id: l.id, alloc });
  }
  if (!lines.some(x => Object.keys(x.alloc).length)) { keepAllOrder(); return; }
  await postDistribute(lines);
}

async function keepAllOrder() {
  if (!confirm(T.ord_keep_confirm)) return;
  await postDistribute([]);
}

// из «Списка закупки» — сразу в новый заказ поставщику
function purchaseToOrder() {
  const first = (WH.purchaseItems || []).find(p => p.supplier_id);
  closeWhModal('purchaseListModal');
  showTab('suppliers');
  openNewOrder(first ? first.supplier_id : null);
}

// ---- карточка поставщика: долг, оплаты, история цен ----
function fmtSum(n) { return fmtNum(Math.round(n || 0)) + ' ' + T.currency; }

async function openSupplierCard(id, then) {
  SUP.cardId = id;
  SUP.cardYear = null;
  SUP.pay = null;
  SUP.cardThen = then || null;  // 'payment' — сразу открыть форму оплаты
  const m = document.getElementById('supCardModal');
  document.getElementById('supCardFoot').innerHTML = '';
  document.getElementById('supCardBody').innerHTML = `<div class="hint-text" style="padding:24px 0; text-align:center;">${T.stats_loading}</div>`;
  m.classList.add('open');
  await reloadSupplierCard();
  if (SUP.cardThen && SUP.cardId === id && SUP.card && SUP.card.supplier.is_active) { const k = SUP.cardThen; SUP.cardThen = null; openSupPayForm(k); }
}

async function reloadSupplierCard(offset) {
  const id = SUP.cardId, year = SUP.cardYear;
  if (!id) return;
  const d = await ordFetch(`/api/suppliers/${id}/card?year=${year || ''}&offset=${offset || 0}`);
  if (SUP.cardId !== id || SUP.cardYear !== year) return;  // пока ждали ответ, открыли другое
  if (!d.ok) { showMsg(ordErr(d), false); closeWhModal('supCardModal'); return; }
  if (offset && SUP.card) { SUP.card.entries = SUP.card.entries.concat(d.entries); SUP.card.total_entries = d.total_entries; }
  else SUP.card = d;
  renderSupplierCard();
}

function supCardYear(y) {
  SUP.cardYear = y || null;
  reloadSupplierCard();
}

function supCardMore() { reloadSupplierCard(SUP.card.entries.length); }

const SUP_METHODS = ['cash', 'card', 'transfer'];
function supMethodName(m) { return SUP_METHODS.includes(m) ? T['sp_m_' + m] : ''; }

function supEntryLine(e) {
  const pay = e.type === 'payment';
  const off = e.status === 'cancelled';
  const title = e.type === 'order' ? T.ord_title_n.replace('{n}', e.number) : pay ? T.sd_payment : T.sd_charge;
  const click = e.type === 'order' ? `onclick="closeWhModal('supCardModal'); openOrder(${e.id});" style="cursor:pointer;"` : '';
  const act = SUP.card.supplier.is_active;
  const x = e.type !== 'order' && !off && act ? `<button class="ord-x" onclick="cancelSupPayment(${e.id})" aria-label="${T.sp_cancel}"><i class="fa-solid fa-xmark"></i></button>` : '';
  const meta = [ordDate(e.date), e.type === 'order' && e.positions ? e.positions + ' ' + T.ord_positions : '', supMethodName(e.method),
    e.note ? escapeHtml(e.note) : '', e.unpriced ? '⚠️ ' + T.sd_unpriced_short : '',
    off ? `<span style="color:#B91C1C;">${T.sp_cancelled}${e.cancel_reason ? ': ' + escapeHtml(e.cancel_reason) : ''}</span>` : ''].filter(Boolean).join(' · ');
  const usd = e.currency === 'USD' && e.amount_usd != null
    ? `${fmtUsd(e.amount_usd)} · ${T.sp_rate_short} ${supRateStr(e.usd_rate)}`
    : e.usd != null && e.amount ? `≈ ${fmtUsd(e.usd)} · ${T.sp_rate_short} ${supRateStr(e.usd_rate)}` : (e.amount ? T.sp_no_rate : '');
  return `<div class="ord-line ${off ? 'cancelled' : ''}" ${click}>
    <div class="pl-name"><b>${title}</b><span>${meta}</span></div>
    <div><b style="white-space:nowrap; display:block; text-align:right; color:${off ? '#94A3B8' : pay ? '#15803D' : '#B91C1C'};">${pay ? '−' : '+'}${fmtNum(e.amount)}</b><div class="sp-sub">${usd}</div></div>${x}
  </div>`;
}

function renderSupplierCard() {
  const c = SUP.card, s = c.supplier, d = c.debt;
  const act = !!s.is_active;
  const listed = SUP.list.find(x => x.id === s.id) || {};
  const st = supStatus(null, d);
  const contacts = [s.phone ? `<a href="tel:${escapeHtml(s.phone.replace(/[^0-9+]/g, ''))}" style="color:inherit;">${escapeHtml(s.phone)}</a>` : '',
    s.telegram ? `<a href="https://t.me/${escapeHtml(s.telegram)}" target="_blank" rel="noopener" style="color:inherit;">@${escapeHtml(s.telegram)}</a>` : '',
    s.contact ? escapeHtml(s.contact) : '', s.delivery_days ? escapeHtml(s.delivery_days) : '',
    s.tg_connected ? `<span class="sup-bot">✓ ${T.sup_tg_badge}</span>` : ''].filter(Boolean).join(' · ');
  const balCls = d.balance > 0 ? (d.overdue > 0 ? 'r' : 'b') : d.balance < 0 ? 'b' : 'g';
  const balLabel = d.balance > 0 ? T.sp_bal_owe : d.balance < 0 ? T.sd_overpaid : T.sd_no_debt;
  const abs = Math.abs(d.balance);
  const chips = [
    d.balance !== 0 || d.overdue ? `<span class="sp-chip ${st.c}">${st.t}</span>` : '',
    d.overdue > 0 && d.overdue < d.balance ? `<span class="sp-chip r">${T.sp_leg_overdue} ${supShort(d.overdue)}</span>` : '',
    d.next_due && d.overdue > 0 ? `<span class="sp-chip b">${T.sd_next_due.replace('{sum}', supShort(d.next_due.amount)).replace('{date}', ordDate(d.next_due.date))}</span>` : '',
    s.pay_days != null ? `<span class="sp-chip n">${T.sd_terms.replace('{n}', s.pay_days)}</span>` : '',
  ].filter(Boolean).join('');
  const notes = [
    s.pay_days == null && d.balance > 0 ? `<div class="hint-text" style="margin-top:8px;">${T.sd_no_terms}</div>` : '',
    d.unpriced_orders ? `<div class="sd-note warn" style="margin-top:8px;">${T.sd_unpriced}</div>` : '',
    !act ? `<div class="sd-note warn" style="margin-top:8px;">${T.sp_in_archive}</div>` : '',
  ].join('');
  const tt = c.period;
  const totals = `<div class="sp-tot" style="margin-top:12px;">
      <div>${T.sp_tot_bought}<b>${supShort(tt.bought)} ${T.currency}</b>${tt.bought ? '≈ ' + fmtUsd(tt.bought_usd) : ''}</div>
      <div>${T.sp_tot_paid}<b>${supShort(tt.paid)} ${T.currency}</b>${tt.paid ? '≈ ' + fmtUsd(tt.paid_usd) : ''}</div></div>
      ${tt.no_rate ? `<div class="hint-text">${T.sp_tot_no_rate.replace('{n}', tt.no_rate)}</div>` : ''}`;
  const yearChips = c.years.length > 1 ? `<div class="sp-chips"><button class="${!c.year ? 'on' : ''}" onclick="supCardYear(null)">${T.sp_all_years}</button>${c.years.map(y => `<button class="${c.year === y ? 'on' : ''}" onclick="supCardYear('${y}')">${y}</button>`).join('')}</div>` : '';
  const ops = c.entries.length ? c.entries.map(supEntryLine).join('') : `<div class="hint-text">${T.sd_no_ops}</div>`;
  const more = c.total_entries > c.entries.length ? `<button class="wh-tbtn wh-tbtn-wide" style="margin-top:8px;" onclick="supCardMore()">${T.sp_show_more} (${c.total_entries - c.entries.length})</button>` : '';
  const prices = c.prices.length ? c.prices.map(p => {
    const ch = p.change_pct;
    const badge = ch == null ? '' : `<span class="pr-badge ${ch > 0 ? 'up' : 'down'}">${ch > 0 ? '↑ +' : '↓ '}${ch}%</span>`;
    const hist = p.history.map(h => `<div class="pr-h"><span>${ordDate(h.date)} · №${h.number} · ${whQty(h.qty)} ${whUnit(p.unit)}</span><b>${fmtNum(h.price)}${h.usd != null ? ' · ' + fmtUsd(h.usd) : ''}</b></div>`).join('');
    return `<div class="pr-row" onclick="this.classList.toggle('open')">
      <div class="ord-line" style="border:none; padding:6px 0;">
        <div class="pl-name"><b>${escapeHtml(p.name)}</b><span>${ordDate(p.last_date)}${p.prev ? ' · ' + T.pr_was + ' ' + fmtNum(p.prev) : ''}${p.since_first_pct != null ? ' · ' + T.pr_since_first + ' ' + (p.since_first_pct > 0 ? '+' : '') + p.since_first_pct + '%' : ''}</span></div>
        <div style="text-align:right;"><b style="white-space:nowrap;">${fmtNum(p.last)}</b>${p.last_usd != null ? `<div class="sp-sub">${fmtUsd(p.last_usd)}</div>` : ''}<div>${badge}</div></div>
      </div>
      <div class="pr-hist">${hist}</div>
    </div>`;
  }).join('') : `<div class="hint-text">${T.pr_empty}</div>`;
  const yStart = c.year ? c.year + '-01-01' : (c.years.length ? c.years[c.years.length - 1] + '-01-01' : '');
  const yEnd = c.year && c.year !== String(new Date().getFullYear()) ? c.year + '-12-31' : fmtDate(new Date());
  const acts = act ? `<div class="sp-acts">
      <button onclick="closeWhModal('supCardModal'); openNewOrder(${s.id});"><i class="fa-solid fa-cart-plus"></i>${T.sup_order_btn}</button>
      <button onclick="closeWhModal('supCardModal'); openSupProducts(${s.id});"><i class="fa-solid fa-boxes-stacked"></i>${T.sup_assign_short}${listed.product_count ? ' · ' + listed.product_count : ''}</button>
      <button onclick="openSupPayForm('charge')"><i class="fa-solid fa-file-invoice"></i>${T.sp_charge_btn}</button>
      <button onclick="closeWhModal('supCardModal'); openSupplierModal(${s.id});"><i class="fa-solid fa-pen"></i>${T.sup_edit_short}</button>
    </div>` : '';
  document.getElementById('supCardBody').innerHTML = `
    <div class="sp-head"><div class="sp-av ${st.c}">${escapeHtml(supInitials(s.name))}</div>
      <div style="min-width:0;"><div class="t">${escapeHtml(s.name)}</div>${contacts ? `<div class="c">${contacts}</div>` : ''}</div></div>
    ${acts}
    <div class="sp-bal ${balCls}">
      <div class="l">${balLabel}</div>
      <div class="x">${abs ? supShort(abs) + ' ' + T.currency : '0'}</div>
      ${abs ? `<div class="f">${fmtSum(abs)}${USD_RATE ? ' · ≈ ' + fmtUsd(abs / USD_RATE) + ' ' + T.sp_by_rate + ' ' + supRateStr(USD_RATE) : ''}</div>` : ''}
      ${chips ? `<div class="chips">${chips}</div>` : ''}
      ${notes}
    </div>
    <div id="supPayForm" style="display:none;"></div>
    <details class="sp-det" open>
      <summary>${T.sd_ops}<span>${c.year ? T.sp_tot_year.replace('{y}', c.year) : T.sp_tot_all}</span></summary>
      <div class="sp-det-in">${yearChips}${totals}${ops}${more}</div>
    </details>
    <details class="sp-det">
      <summary>${T.pr_title}<span>${c.prices.length || ''}</span></summary>
      <div class="sp-det-in"><div class="hint-text" style="margin-bottom:4px;">${T.pr_hint}</div>${prices}</div>
    </details>
    <details class="sp-det">
      <summary>${T.ss_title}<span>Excel</span></summary>
      <div class="sp-det-in">
        <div class="hint-text" style="margin-bottom:6px;">${T.ss_hint}</div>
        <div class="ord-recv-grid">
          <label>${T.ss_from}<input type="date" id="ss_from" value="${yStart}"></label>
          <label>${T.ss_to}<input type="date" id="ss_to" value="${yEnd}"></label>
        </div>
        <button class="wh-tbtn wh-tbtn-wide" style="margin-top:8px;" onclick="downloadSupStatement()"><i class="fa-solid fa-file-excel"></i> ${T.ss_download}</button>
      </div>
    </details>`;
  renderSupCardFoot();
}

function renderSupCardFoot() {
  const foot = document.getElementById('supCardFoot');
  const c = SUP.card;
  if (!foot || !c) return;
  const s = c.supplier;
  if (!s.is_active) { foot.innerHTML = `<button class="main" onclick="restoreSupplier(${s.id})">${T.sp_restore}</button>`; return; }
  if (SUP.pay) {
    foot.innerHTML = `<button class="sec" onclick="closeSupPayForm()">${T.sp_cancel_form}</button>
      <button class="main" onclick="saveSupPayment('${SUP.pay.kind}')">${SUP.pay.kind === 'payment' ? T.sp_save_payment : T.sp_save_charge}</button>`;
    return;
  }
  foot.innerHTML = `<button class="main" onclick="openSupPayForm('payment')"><i class="fa-solid fa-money-bill-wave"></i> ${T.sp_pay_btn}</button>`;
}

function closeSupPayForm() {
  SUP.pay = null;
  const el = document.getElementById('supPayForm');
  if (el) { el.style.display = 'none'; el.innerHTML = ''; }
  renderSupCardFoot();
}

function downloadSupStatement() {
  const f = document.getElementById('ss_from').value, t = document.getElementById('ss_to').value;
  if (f && t && f > t) { showMsg(T.ss_err_period, false); return; }
  obDownload(`/api/suppliers/${SUP.cardId}/statement.xlsx?from=${encodeURIComponent(f)}&to=${encodeURIComponent(t)}`);
}

function supNewToken() {
  try { if (window.crypto && crypto.randomUUID) return crypto.randomUUID(); } catch (e) {}
  return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
}

function openSupPayForm(kind) {
  const el = document.getElementById('supPayForm');
  const d = SUP.card.debt;
  // один token на одну открытую форму: повторная отправка (плохая связь,
  // двойное нажатие) не создаст вторую оплату
  SUP.pay = { kind, cur: 'UZS', method: kind === 'payment' ? 'cash' : null, token: supNewToken() };
  el.style.display = '';
  el.className = 'sp-form';
  el.innerHTML = `
    <div class="sp-form-t">${kind === 'payment' ? T.sp_pay_title : T.sp_charge_title}</div>
    <div class="sp-form-now">${T.sp_debt_now}: <b>${d.balance < 0 ? T.sp_st_overpaid + ' ' : ''}${fmtSum(Math.abs(d.balance))}</b>${usdTail(Math.abs(d.balance))}</div>
    <div class="sp-seg">
      <button type="button" id="sp_cur_UZS" class="on" onclick="spSetCur('UZS')">${T.sp_cur_uzs}</button>
      <button type="button" id="sp_cur_USD" onclick="spSetCur('USD')">${T.sp_cur_usd}</button>
    </div>
    <div class="ord-recv-grid">
      <label><span id="sp_amount_lbl">${kind === 'payment' ? T.sd_pay_amount : T.sd_charge_amount}</span><input type="number" inputmode="decimal" min="0" step="any" id="sp_amount" oninput="spRecalc()" value="${kind === 'payment' && d.balance > 0 ? Math.round(d.balance) : ''}"></label>
      <label>${T.sp_rate_label}<input type="number" inputmode="decimal" min="0" step="any" id="sp_rate" oninput="spRecalc()" value="${USD_RATE || ''}" placeholder="12700"></label>
    </div>
    <div class="sp-eq" id="sp_eq"></div>
    ${kind === 'payment' ? `<div class="sp-chips" id="sp_methods">${SUP_METHODS.map(m => `<button type="button" class="${m === 'cash' ? 'on' : ''}" onclick="spSetMethod('${m}')" data-m="${m}">${T['sp_m_' + m]}</button>`).join('')}</div>` : ''}
    <div class="ord-recv-grid">
      <label>${T.sd_date}<input type="date" id="sp_date" value="${fmtDate(new Date())}" max="${fmtDate(new Date())}"></label>
      <label>${T.sd_note}<input id="sp_note" maxlength="200" placeholder="${kind === 'payment' ? T.sp_note_ph_pay : T.sd_note_ph_charge}"></label>
    </div>
    <div class="sp-after" id="sp_after"></div>`;
  spRecalc();
  renderSupCardFoot();
  el.scrollIntoView({ block: 'start', behavior: 'smooth' });
  setTimeout(() => { const a = document.getElementById('sp_amount'); if (a) a.focus({ preventScroll: true }); }, 250);
}

function spAmounts() {
  const v = parseFloat(document.getElementById('sp_amount').value);
  const rate = parseFloat(document.getElementById('sp_rate').value);
  const r = rate > 0 ? rate : null;
  if (!(v > 0)) return { sum: 0, usd: 0, rate: r };
  if (SUP.pay.cur === 'USD') return { sum: r ? Math.round(Math.round(v * 100) * r / 100) : 0, usd: Math.round(v * 100) / 100, rate: r };
  return { sum: Math.round(v), usd: r ? v / r : null, rate: r };
}

function spRecalc() {
  if (!SUP.pay) return;
  const a = spAmounts();
  const eq = document.getElementById('sp_eq');
  if (SUP.pay.cur === 'USD') eq.textContent = a.rate ? (a.usd ? `= ${fmtSum(a.sum)}` : T.sp_eq_hint_usd) : T.sp_err_rate;
  else eq.textContent = a.sum ? (a.rate ? `≈ ${fmtUsd(a.usd)}` : T.sp_no_rate_set) : T.sp_eq_hint_uzs;
  const after = document.getElementById('sp_after');
  const bal = SUP.card.debt.balance + (SUP.pay.kind === 'payment' ? -a.sum : a.sum);
  after.innerHTML = a.sum ? `${T.sp_debt_after}: <b style="color:${bal > 0 ? '#B91C1C' : '#15803D'};">${bal < 0 ? T.sp_st_overpaid + ' ' : ''}${fmtSum(Math.abs(bal))}</b>${usdTail(Math.abs(bal))}` : '';
}

function spSetCur(c) {
  if (!SUP.pay || SUP.pay.cur === c) return;
  const a = spAmounts();
  SUP.pay.cur = c;
  ['UZS', 'USD'].forEach(k => document.getElementById('sp_cur_' + k).classList.toggle('on', k === c));
  const inp = document.getElementById('sp_amount');
  // переводим уже введённую сумму в новую валюту, чтобы не набирать заново
  if (a.sum && a.rate) inp.value = c === 'USD' ? Math.round(a.sum / a.rate * 100) / 100 : a.sum;
  document.getElementById('sp_amount_lbl').textContent = c === 'USD'
    ? (SUP.pay.kind === 'payment' ? T.sp_pay_amount_usd : T.sp_charge_amount_usd)
    : (SUP.pay.kind === 'payment' ? T.sd_pay_amount : T.sd_charge_amount);
  spRecalc();
}

function spSetMethod(m) {
  SUP.pay.method = m;
  document.querySelectorAll('#sp_methods button').forEach(b => b.classList.toggle('on', b.dataset.m === m));
}

async function saveSupPayment(kind) {
  const a = spAmounts();
  if (SUP.pay.cur === 'USD' && !a.rate) { showMsg(T.sp_err_rate, false); return; }
  if (!(a.sum > 0)) { showMsg(T.sd_err_amount, false); return; }
  const body = { kind, currency: SUP.pay.cur, rate: a.rate, method: SUP.pay.method, token: SUP.pay.token,
    date: document.getElementById('sp_date').value, note: document.getElementById('sp_note').value };
  if (SUP.pay.cur === 'USD') body.amount_usd = a.usd; else body.amount = a.sum;
  const d = await ordFetch(`/api/suppliers/${SUP.cardId}/payments`, 'POST', body);
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  SUP.pay = null;
  showMsg(kind === 'payment' ? T.sd_payment_saved : T.sd_charge_saved, true);
  loadSuppliers();
  reloadSupplierCard();
}

async function cancelSupPayment(pid) {
  const reason = prompt(T.sp_cancel_prompt, '');
  if (reason === null) return;
  const d = await ordFetch(`/api/suppliers/${SUP.cardId}/payments/${pid}/cancel`, 'POST', { reason });
  if (!d.ok) { showMsg(ordErr(d), false); return; }
  showMsg(T.sp_cancel_done, true);
  loadSuppliers();
  reloadSupplierCard();
}

// ---- новый товар прямо из заказа ----
function openOrderNewProduct() {
  renderWarehouseCategoryOptions();
  const src = document.getElementById('wh_new_category');
  const sel = document.getElementById('onp_category');
  sel.innerHTML = src ? src.innerHTML : '';
  ['onp_name', 'onp_sell'].forEach(id => { document.getElementById(id).value = ''; });
  onOnpCategoryChanged();
  const s = SUP.list.find(x => x.id === ORD.cur.supplier_id);
  document.getElementById('onp_hint').textContent = s ? T.onp_hint_sup.replace('{name}', s.name) : T.onp_hint;
  document.getElementById('orderNewProductModal').classList.add('open');
  document.getElementById('onp_name').focus();
}

function onOnpCategoryChanged() {
  document.getElementById('onp_unit_row').style.display = document.getElementById('onp_category').value === 'other' ? '' : 'none';
}

async function saveOrderNewProduct() {
  const category = document.getElementById('onp_category').value;
  const name = document.getElementById('onp_name').value.replace(/\\s+/g, ' ').trim();
  if (!category || !name) { showMsg(T.wh_fill_required, false); return; }
  // такой товар уже есть на складе — просто добавляем его в заказ
  const same = WHCTX.own.products.find(p => p.category === category && p.name.replace(/\\s+/g, ' ').trim().toUpperCase() === name.toUpperCase());
  let product = same;
  if (!same) {
    const d = await ordFetch('/api/products', 'POST', { category, name, unit: document.getElementById('onp_unit').value,
      sell_price: document.getElementById('onp_sell').value || null, initial_stock: 0, supplier_id: ORD.cur.supplier_id || null });
    if (!d.ok) { showMsg(ordErr(d), false); return; }
    product = d.product;
    WHCTX.own.products.push({ ...product, stock_qty: 0, reorder_qty: 0, status: 'out' });
    loadSuppliers();
  }
  closeWhModal('orderNewProductModal');
  if (!ORD.cur.lines.some(l => l.product_id === product.id)) {
    ORD.cur.lines.push({ product_id: product.id, name: product.name, unit: product.unit, stock_qty: product.stock_qty || 0, qty: 0, alloc: {} });
  }
  renderOrderEdit();
  const inputs = document.querySelectorAll('#ordBody .ord-line input');
  if (inputs.length) inputs[inputs.length - 1].focus();
  showMsg(same ? T.onp_exists : T.onp_created, true);
}

// ---- склад выбранного филиала (главный) ----
// ---- накладная: отправка многих товаров сразу ----
const SHIP = { rows: [], qty: {}, cat: 'all' };

async function openShipModal(toShopId) {
  if (!WH.net) await loadNetworkStock();
  if (!WH.net) return;
  const shops = WH.net.shops;
  const opt = s => `<option value="${s.id}">${escapeHtml(s.name)}${s.is_head ? ' (' + T.branch_head_label + ')' : ''}</option>`;
  const head = shops.find(s => s.is_head) || shops[0];
  document.getElementById('shp_from').innerHTML = shops.map(opt).join('');
  document.getElementById('shp_to').innerHTML = shops.map(opt).join('');
  document.getElementById('shp_from').value = head.id;
  const firstBranch = shops.find(s => !s.is_head);
  document.getElementById('shp_to').value = toShopId || (firstBranch ? firstBranch.id : head.id);
  document.getElementById('shp_search').value = '';
  document.getElementById('shp_only_selected').checked = false;
  SHIP.cat = 'all';
  document.getElementById('shipModal').classList.add('open');
  loadShipPlan();
}

async function loadShipPlan() {
  const from = document.getElementById('shp_from').value;
  const to = document.getElementById('shp_to').value;
  SHIP.qty = {};
  const list = document.getElementById('shp_list');
  if (from === to) { SHIP.rows = []; list.innerHTML = `<div class="hint-text" style="padding:12px;">${T.whn_err_same}</div>`; updateShipSummary(); return; }
  list.innerHTML = `<div class="hint-text" style="padding:12px;">${T.stats_loading}</div>`;
  let data;
  const seq = (SHIP.seq = (SHIP.seq || 0) + 1);
  try { data = await (await fetch(`/api/warehouse/ship_plan?from=${from}&to=${to}`)).json(); } catch (e) { return; }
  if (seq !== SHIP.seq) return;
  if (!data.ok) { list.innerHTML = `<div class="hint-text" style="padding:12px;">${escapeHtml(data.error || '')}</div>`; return; }
  SHIP.rows = data.rows;
  renderShipCats();
  renderShipRows();
}

function renderShipCats() {
  const counts = {};
  SHIP.rows.forEach(r => { counts[r.category] = (counts[r.category] || 0) + 1; });
  const order = FLUID_KEYS.concat(FILTER_KEYS, ['other']).filter(k => counts[k]);
  document.getElementById('shp_cats').innerHTML =
    [`<div class="brand-chip ${SHIP.cat === 'all' ? 'active' : ''}" onclick="SHIP.cat='all'; renderShipCats(); renderShipRows();">${T.whs_all}<span class="bc-sub">${SHIP.rows.length}</span></div>`]
      .concat(order.map(k => `<div class="brand-chip ${SHIP.cat === k ? 'active' : ''}" onclick="SHIP.cat='${k}'; renderShipCats(); renderShipRows();">${escapeHtml(k === 'other' ? T.wh_category_other : (T[k] || k))}<span class="bc-sub">${counts[k]}</span></div>`))
      .join('');
}

function renderShipRows() {
  const q = document.getElementById('shp_search').value.trim().toLowerCase();
  const onlySel = document.getElementById('shp_only_selected').checked;
  const toName = (document.getElementById('shp_to').selectedOptions[0] || {}).textContent || '';
  const rows = SHIP.rows.filter(r =>
    (SHIP.cat === 'all' || r.category === SHIP.cat) &&
    (!q || r.name.toLowerCase().includes(q)) &&
    (!onlySel || SHIP.qty[r.id] > 0));
  const list = document.getElementById('shp_list');
  if (!rows.length) { list.innerHTML = `<div class="hint-text" style="padding:12px;">${T.whs_nothing_found}</div>`; updateShipSummary(); return; }
  // рисуем не больше 300 строк за раз — поиск и фильтр помогают сузить
  list.innerHTML = rows.slice(0, 300).map(r => {
    const v = SHIP.qty[r.id] || '';
    const u = whUnit(r.unit);
    const there = r.to_qty === null ? T.shp_not_there : `${whQty(r.to_qty)} ${u}${r.to_per_day ? ` · ~${whQty(r.to_per_day)}${T.whs_per_day}` : ''}`;
    return `
      <div class="sh-row ${v > 0 ? 'sel' : ''}" id="shr_${r.id}">
        <div class="sh-name">
          <b>${escapeHtml(r.name)}</b>
          <span>${T.shp_have} ${whQty(r.stock)} ${u} · ${escapeHtml(toName.split(' (')[0])}: ${there}${r.suggested > 0 ? ` · <span class="need">${T.shp_need} ${whQty(r.suggested)}</span>` : ''}</span>
        </div>
        <input type="number" min="0" step="0.5" value="${v}" placeholder="0" oninput="onShipQty(${r.id}, this)" class="${v > r.stock ? 'over' : ''}">
        <span class="sh-unit">${u}</span>
      </div>`;
  }).join('') + (rows.length > 300 ? `<div class="hint-text" style="padding:10px;">${T.shp_more_rows.replace('{n}', rows.length - 300)}</div>` : '');
  updateShipSummary();
}

function onShipQty(id, input) {
  const v = parseFloat(input.value);
  const row = SHIP.rows.find(r => r.id === id);
  if (v > 0) SHIP.qty[id] = v; else delete SHIP.qty[id];
  input.classList.toggle('over', v > (row ? row.stock : 0));
  const el = document.getElementById('shr_' + id);
  if (el) el.classList.toggle('sel', v > 0);
  updateShipSummary();
}

function updateShipSummary() {
  const ids = Object.keys(SHIP.qty).filter(id => SHIP.qty[id] > 0);
  const over = SHIP.rows.filter(r => SHIP.qty[r.id] > r.stock).length;
  document.getElementById('shp_summary').innerHTML = `${T.shp_selected} ${ids.length}` + (over ? ` · <span style="color:#B91C1C;">${T.shp_over} ${over}</span>` : '');
}

function shipAutofill() {
  let n = 0;
  SHIP.rows.forEach(r => { if (r.suggested > 0) { SHIP.qty[r.id] = r.suggested; n++; } });
  renderShipRows();
  showMsg(n ? `${T.shp_autofilled} ${n}` : T.shp_nothing_needed, !!n);
}

function shipClear() {
  SHIP.qty = {};
  renderShipRows();
}

async function submitShip() {
  const from = document.getElementById('shp_from').value;
  const to = document.getElementById('shp_to').value;
  const lines = Object.keys(SHIP.qty).filter(id => SHIP.qty[id] > 0).map(id => ({ product_id: parseInt(id), quantity: SHIP.qty[id] }));
  if (!lines.length) { showMsg(T.shp_pick, false); return; }
  if (SHIP.rows.some(r => SHIP.qty[r.id] > r.stock)) { showMsg(T.shp_fix_over, false); return; }
  const toName = (document.getElementById('shp_to').selectedOptions[0] || {}).textContent || '';
  if (!confirm(`${T.shp_confirm} ${lines.length} → ${toName}?`)) return;
  const res = await fetch('/api/warehouse/bulk_transfer', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ from_shop_id: from, to_shop_id: to, lines })
  });
  const data = await res.json();
  if (data.ok) {
    closeWhModal('shipModal');
    showMsg(`${T.shp_done} ${data.lines} (№ ${data.batch})`, true);
    WH.net = null;
    loadNetworkStock();
    loadWarehouse();
    if (WH.branchId) selectWhBranch(WH.branchId);
  } else if (data.error === 'problems') {
    const names = data.problems.map(p => `${escapeHtml(p.name || '#' + p.product_id)}${p.available !== undefined ? ` (${T.whn_available} ${whQty(p.available)})` : ''}`).join(', ');
    showMsg(`${T.whn_err_not_enough} ${names}`, false);
  } else {
    showMsg(T['whn_err_' + data.error] || data.error, false);
  }
}

// ---- скопировать каталог в филиал ----
function openCatalogModal(branchId) {
  const sel = document.getElementById('cat_branch');
  sel.innerHTML = WH.branches.map(b => `<option value="${b.id}">${escapeHtml(b.shop_name || b.username)}</option>`).join('');
  if (branchId) sel.value = branchId;
  const counts = {};
  WHCTX.own.products.forEach(p => { counts[p.category] = (counts[p.category] || 0) + 1; });
  const order = FLUID_KEYS.concat(FILTER_KEYS, ['other']).filter(k => counts[k]);
  document.getElementById('cat_types').innerHTML = order.map(k => `
    <label style="display:flex; align-items:center; gap:8px; font-size:14px; text-transform:none; letter-spacing:0; color:var(--text); margin:0;">
      <input type="checkbox" class="cat-type" value="${k}" checked style="width:auto; margin:0;">
      ${escapeHtml(k === 'other' ? T.wh_category_other : (T[k] || k))} <span class="hint-text" style="margin:0;">(${counts[k]})</span>
    </label>`).join('') || `<div class="hint-text">${T.wh_no_products}</div>`;
  document.getElementById('catalogModal').classList.add('open');
}

async function submitCatalog() {
  const branchId = document.getElementById('cat_branch').value;
  const cats = Array.from(document.querySelectorAll('.cat-type:checked')).map(c => c.value);
  if (!cats.length) { showMsg(T.cat_pick, false); return; }
  const res = await fetch('/api/warehouse/copy_catalog', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ branch_id: branchId, categories: cats })
  });
  const data = await res.json();
  if (data.ok) {
    closeWhModal('catalogModal');
    showMsg(`${T.cat_done} ${data.created}${data.skipped ? ` · ${T.cat_skipped} ${data.skipped}` : ''}`, true);
    WH.net = null;
    loadNetworkStock();
    loadWarehouse();
    if (WH.branchId) selectWhBranch(WH.branchId);
  } else {
    showMsg(T['whn_err_' + data.error] || data.error, false);
  }
}

// ---- загрузка склада из Excel ----
let IMPORT_ROWS = [];

function openImportModal() {
  document.getElementById('imp_file').value = '';
  document.getElementById('imp_preview').innerHTML = '';
  document.getElementById('imp_apply_btn').style.display = 'none';
  IMPORT_ROWS = [];
  document.getElementById('importModal').classList.add('open');
}

async function previewImport() {
  const f = document.getElementById('imp_file').files[0];
  const box = document.getElementById('imp_preview');
  const btn = document.getElementById('imp_apply_btn');
  btn.style.display = 'none';
  if (!f) return;
  box.innerHTML = `<div class="hint-text">${T.stats_loading}</div>`;
  const fd = new FormData();
  fd.append('file', f);
  let data;
  try { data = await (await fetch('/api/products/import_preview', { method: 'POST', body: fd })).json(); }
  catch (e) { box.innerHTML = `<div class="hint-text" style="color:#B91C1C;">${T.imp_err_bad_file}</div>`; return; }
  if (!data.ok) { box.innerHTML = `<div class="hint-text" style="color:#B91C1C;">${T['imp_err_' + data.error] || data.error}</div>`; return; }
  IMPORT_ROWS = data.rows;
  const errs = data.rows.filter(r => r.errors.length);
  const ok = data.rows.filter(r => !r.errors.length);
  const upd = ok.filter(r => r.exists).length;
  const errText = e => e.map(x => T['imp_bad_' + x] || x).join(', ');
  box.innerHTML = `
    <div class="imp-sum">
      <div><b style="color:#15803D;">${ok.length - upd}</b>${T.imp_new}</div>
      <div><b style="color:#1D4ED8;">${upd}</b>${T.imp_update}</div>
      <div><b style="color:#B91C1C;">${errs.length}</b>${T.imp_errors}</div>
    </div>
    ${errs.length ? `<div class="hint-text" style="color:#B91C1C; margin-bottom:6px;">${T.imp_errors_hint}</div>` : ''}
    <div style="max-height:36vh; overflow:auto; border:1px solid var(--border); border-radius:12px;">
      <table class="imp-table">
        <tbody>${data.rows.slice(0, 200).map(r => `
          <tr>
            <td style="color:#94A3B8;">${r.row}</td>
            <td><b>${escapeHtml(r.name || '—')}</b><br><span class="hint-text" style="margin:0;">${escapeHtml(r.category ? (r.category === 'other' ? T.wh_category_other : T[r.category]) : r.category_raw || '—')}</span></td>
            <td style="white-space:nowrap;">${r.quantity ? whQty(r.quantity) + ' ' + whUnit(r.unit) : '—'}</td>
            <td style="white-space:nowrap;">${r.sell_price != null ? fmtNum(r.sell_price) : '—'}${!IS_BRANCH && r.purchase_price != null ? `<br><span class="hint-text" style="margin:0;">${T.whs_buy} ${fmtNum(r.purchase_price)}</span>` : ''}</td>
            <td>${r.errors.length ? `<span class="imp-tag err">${errText(r.errors)}</span>` : (r.exists ? `<span class="imp-tag upd">${T.imp_tag_upd}</span>` : `<span class="imp-tag new">${T.imp_tag_new}</span>`)}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    ${data.rows.length > 200 ? `<div class="hint-text">${T.shp_more_rows.replace('{n}', data.rows.length - 200)}</div>` : ''}`;
  if (ok.length) {
    btn.style.display = '';
    btn.innerHTML = `<i class="fa-solid fa-file-import"></i> ${T.imp_apply} ${ok.length}`;
  }
}

async function applyImport() {
  const ok = IMPORT_ROWS.filter(r => !r.errors.length);
  if (!ok.length) return;
  const payload = ok.map(r => ({ category: r.category, name: r.name, unit: r.unit, sell_price: r.sell_price, purchase_price: r.purchase_price, quantity: r.quantity }));
  const btn = document.getElementById('imp_apply_btn');
  btn.disabled = true;
  const res = await fetch('/api/products/import_apply', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ rows: payload }) });
  const data = await res.json();
  btn.disabled = false;
  if (data.ok) {
    closeWhModal('importModal');
    showMsg(`${T.imp_done}: ${T.imp_new} ${data.created}, ${T.imp_restocked} ${data.restocked}${data.updated ? `, ${T.imp_prices} ${data.updated}` : ''}`, true);
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + (data.error || ''), false);
  }
}

// ---- изменение товара ----
let editingProduct = null;  // { key, shopId, p }

function openEditProductModal(key, productId) {
  const ctx = WHCTX[key];
  const p = ctx.products.find(x => x.id === productId);
  if (!p) return;
  editingProduct = { key, shopId: ctx.shopId, p };
  const canBuy = key === 'br' || !IS_BRANCH;
  document.getElementById('ep_category').textContent = (p.category === 'other' ? T.wh_category_other : (T[p.category] || p.category)) + ' · ' + whUnit(p.unit);
  document.getElementById('ep_name').value = p.name;
  document.getElementById('ep_sell').value = p.sell_price ?? '';
  document.getElementById('ep_buy').value = canBuy ? (p.purchase_price ?? '') : '';
  const isUsd = canBuy && p.purchase_currency === 'USD' && p.purchase_usd_cents != null;
  document.getElementById('ep_buy_usd').value = isUsd ? p.purchase_usd_cents / 100 : '';
  document.getElementById('ep_sell_usd').value = '';
  document.getElementById('ep_sell_usd_wrap').style.display = USD_RATE ? '' : 'none';
  document.getElementById('ep_buy_wrap').style.display = canBuy ? '' : 'none';
  document.getElementById('ep_cur_wrap').style.display = canBuy && (USD_RATE || isUsd) ? '' : 'none';
  curSet('ep', isUsd ? 'USD' : 'UZS');
  document.getElementById('ep_usd_wrap').style.display = canBuy && (USD_RATE || isUsd) ? '' : 'none';
  document.getElementById('ep_price_hint').style.display = canBuy ? '' : 'none';
  document.getElementById('ep_unit').textContent = whUnit(p.unit);
  document.getElementById('ep_stock').value = Math.round(epBaseQty(editingProduct) * 100) / 100;
  const stLbl = document.getElementById('ep_stock_lbl');
  if (stLbl) stLbl.textContent = epStoreMode(editingProduct) ? T.st_on_main.replace(':', '') : T.whe_stock_label;
  document.getElementById('ep_reason').value = '';
  document.getElementById('ep_reason_wrap').style.display = 'none';
  document.getElementById('editProductModal').classList.add('open');
}

// «Склад магазина»: на основном складе правим основной остаток, магазин не трогаем
function epStoreMode(ep) { return STORE_ENABLED && ep && ep.key === 'own'; }
function epBaseQty(ep) { return epStoreMode(ep) ? (ep.p.main_qty || 0) : (ep.p.stock_qty || 0); }

function onEditStockChanged() {
  if (!editingProduct) return;
  const v = parseFloat(document.getElementById('ep_stock').value);
  const changed = !isNaN(v) && Math.abs(v - epBaseQty(editingProduct)) > 1e-9;
  document.getElementById('ep_reason_wrap').style.display = changed ? '' : 'none';
}

async function submitEditProduct() {
  if (!editingProduct) return;
  const { key, shopId, p } = editingProduct;
  const canBuy = key === 'br' || !IS_BRANCH;
  const name = document.getElementById('ep_name').value.trim();
  const sell = document.getElementById('ep_sell').value.trim();
  const buy = document.getElementById('ep_buy').value.trim();
  const stock = document.getElementById('ep_stock').value.trim();
  if (!name) { showMsg(T.whe_err_name, false); return; }
  if (stock === '' || parseFloat(stock) < 0) { showMsg(T.whe_err_stock, false); return; }
  // отправляем только то, что действительно изменили
  const payload = {};
  if (name !== p.name) payload.name = name;
  if (sell !== String(p.sell_price ?? '')) payload.sell_price = sell;
  if (canBuy && buy !== String(p.purchase_price ?? '')) payload.purchase_price = buy;
  if (canBuy) {
    const cur = curGet('ep');
    const wasUsd = p.purchase_currency === 'USD' && p.purchase_usd_cents != null;
    if (cur === 'USD') {
      const usd = curUsdValue('ep');
      if (usd == null) { showMsg(T.usd_cur_need_usd, false); return; }
      if (!wasUsd || Math.round(usd * 100) !== p.purchase_usd_cents) {
        payload.purchase_currency = 'USD';
        payload.purchase_usd = usd;
        delete payload.purchase_price;
      }
    } else if (wasUsd) {
      payload.purchase_currency = 'UZS';
    }
  }
  if (Math.abs(parseFloat(stock) - epBaseQty(editingProduct)) > 1e-9) {
    payload.stock_qty = epStoreMode(editingProduct)
      ? String(Math.round((parseFloat(stock) + (p.shop_qty || 0)) * 1000) / 1000) : stock;
    payload.stock_reason = document.getElementById('ep_reason').value.trim();
  }
  if (!Object.keys(payload).length) { closeWhModal('editProductModal'); return; }
  if (payload.name && !confirm(T.whe_rename_confirm)) return;
  const url = shopId ? `/api/branches/${shopId}/products/${p.id}` : `/api/products/${p.id}`;
  const res = await fetch(url, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
  const data = await res.json();
  if (data.ok) {
    closeWhModal('editProductModal');
    showMsg(T.whe_saved, true);
    if (shopId) { selectWhBranch(shopId); WH.net = null; }
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function selectWhBranch(branchId) {
  WH.branchId = branchId;
  const seq = (WH.brSeq = (WH.brSeq || 0) + 1);
  document.querySelectorAll('#branchWarehouseSummary .whn-shop').forEach((el, i) => {
    el.classList.toggle('active', WH.branches[i] && WH.branches[i].id === branchId);
  });
  document.querySelectorAll('#whbChips .brand-chip').forEach(el => {
    el.classList.toggle('active', el.dataset.id === String(branchId));
  });
  const wrap = document.getElementById('whbDetail');
  wrap.style.display = 'block';
  let data;
  try { data = await (await fetch(`/api/branches/${branchId}/warehouse`)).json(); } catch (e) { return; }
  if (seq !== WH.brSeq) return;  // пока грузилось, выбрали другой филиал
  if (!data.ok) { showMsg(T.msg_error + ' ' + data.error, false); return; }
  const ctx = WHCTX.br;
  ctx.shopId = branchId;
  ctx.products = data.products;
  ctx.summary = data.summary;
  ctx.name = data.name;
  document.getElementById('whbTitle').textContent = data.name;
  renderWarehouseSummary('br');
  renderWhCategoryChips('br');
  renderProductCards('br');
  renderMovements(document.getElementById('whbHistory'), data.movements, true);
}

function renderWhBranchChips() {
  const el = document.getElementById('whbChips');
  if (!el) return;
  el.innerHTML = WH.branches.map(b => `<div class="brand-chip ${WH.branchId === b.id ? 'active' : ''}" data-id="${b.id}" onclick="selectWhBranch(${b.id})">${escapeHtml(b.shop_name || b.username)}</div>`).join('');
}

async function editBranchPrice(productId, name, current) {
  const val = prompt(`${T.whb_set_price}: ${name}`, current ?? '');
  if (val === null) return;
  const res = await fetch(`/api/branches/${WHCTX.br.shopId}/products/${productId}/purchase_price`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ purchase_price: val.trim() })
  });
  const data = await res.json();
  if (data.ok) { showMsg(T.whb_price_saved, true); selectWhBranch(WHCTX.br.shopId); loadWarehouse(); }
  else showMsg(T.msg_error + ' ' + data.error, false);
}

// ---- склады сети (главный) ----
async function loadNetworkStock() {
  const box = document.getElementById('whNetMatrix');
  if (!box) return;
  let data;
  try { data = await (await fetch('/api/warehouse/network')).json(); } catch (e) { return; }
  if (!data.ok) return;
  WH.net = data;
  if (!data.rows.length) { box.innerHTML = `<div class="hint-text">${T.wh_no_products}</div>`; return; }
  const shops = data.shops;
  box.innerHTML = `
    <div class="table-wrap"><table class="wh-mx">
      <thead><tr><th>${T.whn_product}</th>${shops.map(s => `<th>${escapeHtml(s.name)}${s.is_head ? `<br><span style="font-weight:500; color:#94A3B8;">${T.branch_head_label}</span>` : ''}</th>`).join('')}</tr></thead>
      <tbody>${data.rows.map((r, i) => `
        <tr>
          <td>${escapeHtml(r.name)}<span>${escapeHtml(r.category === 'other' ? T.wh_category_other : (T[r.category] || r.category))}</span></td>
          ${shops.map(s => {
            const c = r.cells[String(s.id)];
            if (!c) return `<td class="cell" onclick="openTransferModal({row: ${i}, to: ${s.id}})"><span class="q-none">—</span></td>`;
            const cls = c.status === 'out' ? 'q-out' : c.status === 'low' ? 'q-low' : '';
            return `<td class="cell" onclick="openTransferModal({row: ${i}, to: ${s.id}})"><span class="${cls}">${whQty(c.qty)}</span></td>`;
          }).join('')}
        </tr>`).join('')}
      </tbody>
    </table></div>
    <div class="rv-legend">
      <span><i style="background:#FEE2E2; border:1px solid #FCA5A5;"></i>${T.whs_out}</span>
      <span><i style="background:#FEF3C7; border:1px solid #FCD34D;"></i>${T.whn_legend_low}</span>
      <span>${T.whn_legend_click}</span>
    </div>`;
}

async function openTransferModal(opts) {
  if (!WH.net) await loadNetworkStock();
  if (!WH.net) return;
  const shops = WH.net.shops;
  const opt = s => `<option value="${s.id}">${escapeHtml(s.name)}${s.is_head ? ' (' + T.branch_head_label + ')' : ''}</option>`;
  const fromSel = document.getElementById('tr_from');
  const toSel = document.getElementById('tr_to');
  fromSel.innerHTML = shops.map(opt).join('');
  toSel.innerHTML = shops.map(opt).join('');
  const head = shops.find(s => s.is_head) || shops[0];
  let fromId = head.id, productKey = null, toId = null;

  if (opts.productId) {
    fromId = opts.fromShop || head.id;
    const row = WH.net.rows.find(r => r.cells[String(fromId)] && r.cells[String(fromId)].product_id === opts.productId);
    if (row) productKey = WH.net.rows.indexOf(row);
  }
  if (opts.row !== undefined) {
    productKey = opts.row;
    toId = opts.to;
    // отправляем с той точки, где этого товара больше всего
    const cells = WH.net.rows[opts.row].cells;
    const best = shops.filter(s => s.id !== opts.to && cells[String(s.id)] && cells[String(s.id)].qty > 0)
      .sort((a, b) => cells[String(b.id)].qty - cells[String(a.id)].qty)[0];
    if (best) fromId = best.id;
  }
  fromSel.value = fromId;
  const firstOther = shops.find(s => s.id !== fromId);
  toSel.value = toId && toId !== fromId ? toId : (firstOther ? firstOther.id : fromId);
  onTransferFromChanged(productKey);
  document.getElementById('tr_qty').value = '';
  document.getElementById('transferModal').classList.add('open');
}

function onTransferFromChanged(preselectRow) {
  const fromId = document.getElementById('tr_from').value;
  const sel = document.getElementById('tr_product');
  const rows = WH.net.rows.map((r, i) => ({ r, i })).filter(x => x.r.cells[fromId] && x.r.cells[fromId].qty > 0);
  sel.innerHTML = rows.length
    ? rows.map(x => `<option value="${x.i}">${escapeHtml(x.r.name)} — ${whQty(x.r.cells[fromId].qty)} ${whUnit(x.r.unit)}</option>`).join('')
    : `<option value="">${T.whn_nothing_to_send}</option>`;
  if (preselectRow !== undefined && preselectRow !== null && rows.some(x => x.i === preselectRow)) sel.value = preselectRow;
  onTransferProductChanged();
}

function onTransferProductChanged() {
  const fromId = document.getElementById('tr_from').value;
  const idx = document.getElementById('tr_product').value;
  const el = document.getElementById('tr_available');
  if (idx === '') { el.textContent = ''; return; }
  const r = WH.net.rows[idx];
  el.textContent = `${T.whn_available} ${whQty(r.cells[fromId].qty)} ${whUnit(r.unit)}`;
}

async function submitTransfer() {
  const fromId = document.getElementById('tr_from').value;
  const toId = document.getElementById('tr_to').value;
  const idx = document.getElementById('tr_product').value;
  const qty = parseFloat(document.getElementById('tr_qty').value);
  if (idx === '' || !(qty > 0)) { showMsg(T.whn_err_fill, false); return; }
  if (fromId === toId) { showMsg(T.whn_err_same, false); return; }
  const r = WH.net.rows[idx];
  const res = await fetch('/api/warehouse/transfer', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ from_shop_id: fromId, to_shop_id: toId, product_id: r.cells[fromId].product_id, quantity: qty })
  });
  const data = await res.json();
  if (data.ok) {
    closeWhModal('transferModal');
    showMsg(T.whn_done, true);
    WH.net = null;
    loadNetworkStock();
    loadWarehouse();
    if (WH.branchId) selectWhBranch(WH.branchId);
  } else {
    const msg = data.error === 'not_enough' ? `${T.whn_err_not_enough} ${whQty(data.available)}` : (T['whn_err_' + data.error] || data.error);
    showMsg(msg, false);
  }
}

function fitSubtabs(box) {
  if (!box) return;
  const n = [...box.children].filter(e => e.style.display !== 'none').length;
  box.classList.toggle('subtabs-many', n >= 4);
}
function showWhSubTab(t) {
  ['own', 'store', 'branches', 'network'].forEach(k => {
    const view = document.getElementById({ own: 'whOwnView', store: 'whStoreView', branches: 'whBranchesView', network: 'whNetworkView' }[k]);
    if (view) view.style.display = t === k ? 'block' : 'none';
    const tab = document.getElementById('subwh-' + k);
    if (tab) tab.classList.toggle('active', t === k);
  });
  if (t === 'network') { WH.net = null; loadNetworkStock(); }
  if (t === 'store') renderStore();
  if (t === 'branches') {
    if (!WH.branchId && WH.branches.length) selectWhBranch(WH.branches[0].id);
    else if (WH.branchId) selectWhBranch(WH.branchId);
  }
}

function onUsdFieldEdited(usdFieldId, sumFieldId) {
  const usdVal = parseFloat(document.getElementById(usdFieldId).value);
  const sumField = document.getElementById(sumFieldId);
  if (!USD_RATE || isNaN(usdVal)) return;
  sumField.value = Math.round(usdVal * USD_RATE);
}

function onSumFieldEdited(sumFieldId, usdFieldId) {
  // если сумма меняется вручную (не через пересчёт из $), поле $ больше не
  // соответствует новой сумме однозначно - просто очищаем его, чтобы не
  // вводить в заблуждение несоответствующим числом
  const usdField = document.getElementById(usdFieldId);
  if (usdField) usdField.value = '';
}

// ---------- Единый курс доллара ----------
const RATE = { setup: null, sel: new Set(), sugg: [], seq: 0 };
function rateFmt(n) { return Number(n || 0).toLocaleString('ru-RU', { maximumFractionDigits: 2 }); }
function rateDate(s) { s = String(s || ''); return s.length >= 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : s; }
function fmtUsdShort(x) { return x == null ? '' : '$' + Number(x).toLocaleString('ru-RU', { maximumFractionDigits: Math.abs(x) >= 100 ? 0 : 2 }); }
function usdApprox(x) { return x == null ? '' : '≈ ' + fmtUsdShort(x); }

async function loadRateTab() {
  const seq = ++RATE.seq;
  let data;
  try { data = await (await fetch('/api/usd_rate')).json(); } catch (e) { return; }
  if (seq !== RATE.seq || !data.ok) return;
  USD_RATE = data.rate || null;
  renderRateNow(data);
  if (!IS_BRANCH) loadRateSetup();
}

function renderRateNow(data) {
  document.getElementById('rateNow').textContent = data.rate ? rateFmt(data.rate) : '—';
  const scope = document.getElementById('rateScope');
  if (scope) scope.textContent = IS_BRANCH ? T.usd_scope_branch : (RATE.hasBranches ? T.usd_scope_head : T.usd_scope_single);
  const inp = document.getElementById('rate_input');
  if (inp && !inp.value && data.rate) inp.placeholder = String(data.rate);
  const hist = data.history || [];
  const el = document.getElementById('rateHistory');
  if (!el) return;
  el.innerHTML = hist.length ? `<div class="wh-att-title">${T.usd_hist_title}</div>` + hist.map(h => {
    const up = h.prev_rate && h.rate > h.prev_rate;
    const pct = h.prev_rate ? ((h.rate - h.prev_rate) / h.prev_rate * 100) : null;
    const reval = !IS_BRANCH && h.reval_amount ? ` · ${T.usd_hist_reval} ${h.reval_amount > 0 ? '+' : '−'}${fmtShort(Math.abs(h.reval_amount))}` : '';
    return `<div class="rate-h"><span>${rateDate(h.set_at)}${h.prev_rate ? ` · ${rateFmt(h.prev_rate)} →` : ''} <b>${rateFmt(h.rate)}</b></span>
      <span class="${up ? 'up' : 'down'}">${pct !== null ? (pct > 0 ? '+' : '') + pct.toFixed(1) + '%' : ''}${reval}</span></div>`;
  }).join('') : `<div class="hint-text" style="margin:0;">${T.usd_hist_empty}</div>`;
}

async function saveNetworkRate() {
  const inp = document.getElementById('rate_input');
  const rate = parseFloat(String(inp.value).replace(',', '.'));
  if (!(rate > 0)) { showMsg(T.usd_rate_error, false); return; }
  if (RATE.setup && !RATE.setup.done && RATE.setup.products.length && !confirm(T.usd_setup_first)) return;
  const res = await fetch('/api/usd_rate', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ rate }) });
  const data = await res.json();
  if (!data.ok) { showMsg(T.usd_rate_error + (data.error ? ': ' + data.error : ''), false); return; }
  USD_RATE = data.rate;
  inp.value = '';
  renderRateNow({ rate: data.rate, history: data.history });
  if (typeof SUP !== 'undefined' && SUP.loaded) { SUP.rate = USD_RATE; renderSuppliers(); }
  let msg = T.usd_rate_saved;
  if (data.reval) msg += ` · ${T.usd_hist_reval} ${data.reval > 0 ? '+' : '−'}${fmtShort(Math.abs(data.reval))} ${T.currency}`;
  showMsg(msg, true);
  loadRateSetup();
  if (data.suggestions && data.suggestions.length) openRatePrices(data);
}

function openRatePrices(data) {
  RATE.sugg = data.suggestions.map(x => ({ ...x, on: true }));
  document.getElementById('rpTitle').textContent = T.usd_rp_title.replace('{pct}', String(data.pct).replace('.', ','));
  document.getElementById('rpSub').textContent = T.usd_rp_sub.replace('{n}', RATE.sugg.length);
  renderRatePrices();
  document.getElementById('ratePriceModal').classList.add('open');
}

function renderRatePrices() {
  let lastShop = null;
  const multi = new Set(RATE.sugg.map(x => x.shop_id)).size > 1;
  document.getElementById('rpList').innerHTML = RATE.sugg.map((x, i) => {
    const head = multi && x.shop_id !== lastShop ? `<div class="rate-shop">${escapeHtml(x.shop_name || '')}</div>` : '';
    lastShop = x.shop_id;
    const mg = x.margin_pct != null ? `${T.usd_rp_margin} ${x.margin_pct}% → ${x.new_margin_pct}%` : '';
    return head + `<div class="rate-row" onclick="if (event.target.tagName !== 'INPUT') { const c = this.querySelector('input[type=checkbox]'); c.checked = !c.checked; RATE.sugg[${i}].on = c.checked; }">
      <input type="checkbox" ${x.on ? 'checked' : ''} onchange="RATE.sugg[${i}].on = this.checked">
      <div class="rr-main"><b>${escapeHtml(x.name)}</b><span>${fmtNum(x.sell_price)} → ${mg}</span></div>
      <div class="rr-price"><input type="number" inputmode="numeric" value="${x.proposed}" oninput="RATE.sugg[${i}].proposed = this.value"></div>
    </div>`;
  }).join('');
}
function rpSelect(on) { RATE.sugg.forEach(x => { x.on = on; }); renderRatePrices(); }

async function applyRatePrices() {
  const items = RATE.sugg.filter(x => x.on && parseFloat(x.proposed) > 0).map(x => ({ product_id: x.product_id, sell_price: x.proposed }));
  if (!items.length) { closeWhModal('ratePriceModal'); return; }
  const data = await (await fetch('/api/usd_rate/apply_prices', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ items }) })).json();
  if (!data.ok) { showMsg(T.msg_error + ' ' + (data.error || ''), false); return; }
  closeWhModal('ratePriceModal');
  showMsg(T.usd_rp_done.replace('{n}', data.updated), true);
}

async function loadRateSetup() {
  const card = document.getElementById('rateSetupCard');
  if (!card) return;
  let data;
  try { data = await (await fetch('/api/usd_rate/setup')).json(); } catch (e) { return; }
  if (!data.ok) { card.style.display = 'none'; return; }
  RATE.setup = data;
  RATE.hasBranches = new Set(data.products.map(p => p.shop_id)).size > 1 || data.products.some(p => !p.is_head);
  const scope = document.getElementById('rateScope');
  if (scope) scope.textContent = RATE.hasBranches ? T.usd_scope_head : T.usd_scope_single;
  RATE.sel = new Set(data.products.filter(p => p.purchase_currency === 'USD').map(p => p.id));
  const ent = document.getElementById('rate_setup_entered');
  if (ent && !ent.value && data.rate) ent.value = data.rate;
  card.style.display = data.products.length ? '' : 'none';
  document.getElementById('rateSetupBanner').innerHTML = data.done
    ? `<div class="rate-banner ok"><i class="fa-solid fa-circle-check"></i> ${T.usd_setup_done}</div>`
    : `<div class="rate-banner"><i class="fa-solid fa-triangle-exclamation"></i> ${T.usd_setup_todo}</div>`;
  document.querySelectorAll('[data-badge="rate"]').forEach(b => { b.textContent = data.done || !data.products.length ? '' : '!'; });
  renderRateSetup();
}

function renderRateSetup() {
  if (!RATE.setup) return;
  const q = (document.getElementById('rateSetupSearch').value || '').trim().toLowerCase();
  const list = RATE.setup.products.filter(p => !q || (p.name || '').toLowerCase().includes(q));
  const multi = new Set(RATE.setup.products.map(p => p.shop_id)).size > 1;
  let lastShop = null;
  document.getElementById('rateSetupList').innerHTML = list.map(p => {
    const head = multi && p.shop_id !== lastShop ? `<div class="rate-shop">${escapeHtml(p.shop_name || '')}</div>` : '';
    lastShop = p.shop_id;
    const isUsd = p.purchase_currency === 'USD' && p.purchase_usd_cents != null;
    const price = p.purchase_price == null ? `<span style="color:#B45309;">${T.usd_setup_no_price}</span>`
      : `${fmtNum(p.purchase_price)}<br><span class="hint-text" style="margin:0;">${isUsd ? fmtUsdShort(p.purchase_usd_cents / 100) : (USD_RATE ? usdApprox(p.purchase_price / USD_RATE) : '')}</span>`;
    return head + `<div class="rate-row" onclick="if (event.target.tagName !== 'INPUT') { const c = this.querySelector('input'); if (!c.disabled) { c.checked = !c.checked; rateSetupToggle(${p.id}, c.checked); } }">
      <input type="checkbox" ${RATE.sel.has(p.id) ? 'checked' : ''} ${p.purchase_price == null ? 'disabled' : ''} onchange="rateSetupToggle(${p.id}, this.checked)">
      <div class="rr-main"><b>${escapeHtml(p.name)}</b><span>${whCatName(p.category)} · ${whQty(p.stock_qty)} ${whUnit(p.unit)}</span></div>
      <div class="rr-price">${price}</div>
    </div>`;
  }).join('') || `<div class="hint-text">${T.wh_no_restocks}</div>`;
  document.getElementById('rateSetupCount').textContent = T.usd_setup_count.replace('{n}', RATE.sel.size);
}
function rateSetupToggle(id, on) { if (on) RATE.sel.add(id); else RATE.sel.delete(id); document.getElementById('rateSetupCount').textContent = T.usd_setup_count.replace('{n}', RATE.sel.size); }
function rateSetupSelect(on) {
  const q = (document.getElementById('rateSetupSearch').value || '').trim().toLowerCase();
  RATE.setup.products.filter(p => p.purchase_price != null && (!q || (p.name || '').toLowerCase().includes(q)))
    .forEach(p => { if (on) RATE.sel.add(p.id); else RATE.sel.delete(p.id); });
  renderRateSetup();
}

async function saveRateSetup() {
  const entered = parseFloat(String(document.getElementById('rate_setup_entered').value).replace(',', '.'));
  if (!(entered > 0)) { showMsg(T.usd_setup_err_rate, false); return; }
  const res = await fetch('/api/usd_rate/setup', { method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ product_ids: [...RATE.sel], entered_rate: entered }) });
  const data = await res.json();
  if (!data.ok) { showMsg(T.msg_error + ' ' + (data.error || ''), false); return; }
  let msg = T.usd_setup_saved.replace('{n}', data.marked);
  if (data.reval) msg += ` · ${T.usd_hist_reval} ${data.reval > 0 ? '+' : '−'}${fmtShort(Math.abs(data.reval))} ${T.currency}`;
  showMsg(msg, true);
  loadRateSetup();
}

// переключатель «закупка в сумах / в $» в формах товара
function curGet(prefix) { const b = document.querySelector(`#${prefix}_cur button.on`); return b ? b.dataset.cur : 'UZS'; }
function curSet(prefix, cur) {
  document.querySelectorAll(`#${prefix}_cur button`).forEach(b => b.classList.toggle('on', b.dataset.cur === cur));
  const sumEl = document.getElementById(prefix === 'ep' ? 'ep_buy' : 'wh_new_purchase_price');
  const usdWrap = document.getElementById(prefix === 'ep' ? 'ep_usd_wrap' : 'wh_new_purchase_usd_wrap');
  if (usdWrap) usdWrap.style.display = (cur === 'USD' || USD_RATE) ? '' : 'none';
  if (sumEl) sumEl.readOnly = cur === 'USD';
  const hint = document.getElementById(prefix + '_cur_hint');
  if (hint) hint.textContent = cur === 'USD' ? T.usd_cur_hint_usd : T.usd_cur_hint_uzs;
}
function curUsdValue(prefix) {
  const usdEl = document.getElementById(prefix === 'ep' ? 'ep_buy_usd' : 'wh_new_purchase_usd');
  const sumEl = document.getElementById(prefix === 'ep' ? 'ep_buy' : 'wh_new_purchase_price');
  const v = parseFloat(usdEl.value);
  if (!isNaN(v)) return Math.round(v * 100) / 100;
  const s = parseFloat(sumEl.value);
  return !isNaN(s) && USD_RATE ? Math.round(s / USD_RATE * 100) / 100 : null;
}

async function createProduct() {
  const catEl = document.getElementById('wh_new_category');
  const nameEl = document.getElementById('wh_new_name');
  if (!catEl || !nameEl) return;  // вкладка "Склад" не отрисована (выключена для этой точки)
  const category = catEl.value;
  const name = nameEl.value.trim();
  if (!category || !name) { showMsg(T.wh_fill_required, false); return; }
  const payload = {
    category, name,
    unit: document.getElementById('wh_new_unit').value,
    sell_price: document.getElementById('wh_new_sell_price').value || null,
    purchase_price: document.getElementById('wh_new_purchase_price').value || null,
    initial_stock: document.getElementById('wh_new_stock').value || 0,
  };
  if (!IS_BRANCH && curGet('wh_new') === 'USD') {
    const usd = curUsdValue('wh_new');
    if (usd == null) { showMsg(T.usd_cur_need_usd, false); return; }
    if (!USD_RATE) { showMsg(T.usd_cur_need_rate, false); return; }
    payload.purchase_currency = 'USD';
    payload.purchase_usd = usd;
  }
  const res = await fetch('/api/products', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.wh_product_added, true);
    ['wh_new_name','wh_new_sell_price','wh_new_purchase_price','wh_new_purchase_usd','wh_new_stock'].forEach(id => document.getElementById(id).value = '');
    if (!IS_BRANCH) curSet('wh_new', 'UZS');
    document.getElementById('wh_new_unit_row').style.display = 'none';
    closeWhModal('addProductModal');
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function deleteProduct(id, name) {
  if (!confirm(T.wh_delete_confirm)) return;
  const res = await fetch('/api/products/' + id, { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.wh_product_deleted, true);
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

let restockingShopId = null;  // null — свой склад; id филиала — пополнение склада филиала главным

function openRestockModal(id, name, shopId) {
  restockingProductId = id;
  restockingShopId = shopId || null;
  document.getElementById('restockModalTitle').textContent = T.wh_restock_title + ': ' + name;
  document.getElementById('restock_qty').value = '';
  document.getElementById('restock_price').value = '';
  const restockUsd = document.getElementById('restock_price_usd');
  if (restockUsd) restockUsd.value = '';
  document.getElementById('restock_date').value = fmtDate(new Date());
  document.getElementById('restockModal').classList.add('open');
}

function closeRestockModal() {
  document.getElementById('restockModal').classList.remove('open');
}

async function submitRestock() {
  const payload = {
    quantity: document.getElementById('restock_qty').value,
    purchase_price: document.getElementById('restock_price').value || null,
    purchase_usd: (document.getElementById('restock_price_usd') || {}).value || null,
    restock_date: document.getElementById('restock_date').value || null,
  };
  const url = restockingShopId
    ? `/api/branches/${restockingShopId}/products/${restockingProductId}/restock`
    : `/api/products/${restockingProductId}/restock`;
  const res = await fetch(url, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    closeRestockModal();
    showMsg(T.wh_restocked, true);
    if (restockingShopId) { selectWhBranch(restockingShopId); WH.net = null; loadNetworkStock(); }
    loadWarehouse();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function loadRestockHistory() {
  const el = document.getElementById('restockHistory');
  if (!el) return;
  let moves = [];
  try { moves = await (await fetch('/api/warehouse/movements')).json(); } catch (e) {}
  renderMovements(el, moves, !IS_BRANCH);
}

function renderMovements(el, moves, showPrice) {
  if (!el) return;
  if (!moves || !moves.length) { el.innerHTML = `<div class="hint-text">${T.wh_no_restocks}</div>`; return; }
  const icon = { restock: ['fa-arrow-down', '#15803D'], transfer_in: ['fa-right-to-bracket', '#0F52BA'], transfer_out: ['fa-right-from-bracket', '#B45309'], adjust: ['fa-scale-balanced', '#7C3AED'], to_store: ['fa-store', '#0F52BA'], from_store: ['fa-rotate-left', '#64748B'] };
  el.innerHTML = moves.slice(0, 30).map(m => {
    const [ic, col] = icon[m.type] || icon.restock;
    const sign = m.type === 'to_store' || m.type === 'from_store' ? '' : (m.type === 'transfer_out' || (m.type === 'adjust' && m.delta < 0) ? '−' : '+');
    const what = m.type === 'to_store' ? T.st_mv_to_store : m.type === 'from_store' ? T.st_mv_from_store : m.type === 'restock' ? T.whs_mv_restock + (m.order_number ? ' · ' + T.ord_title_n.replace('{n}', m.order_number) : '')
      : m.type === 'adjust' ? `${T.whe_mv_adjust}: ${whQty(m.old_qty)} → ${whQty(m.new_qty)}${m.reason ? ' · ' + escapeHtml(m.reason) : ''}`
      : (m.type === 'transfer_in' ? `${T.whs_mv_from} ${escapeHtml(m.other_shop || '')}` : `${T.whs_mv_to} ${escapeHtml(m.other_shop || '')}`) + (m.batch ? ` · ${T.shp_batch} ${escapeHtml(m.batch)}` : '');
    return `
    <div class="wh-att">
      <i class="fa-solid ${ic}" style="color:${col};"></i>
      <div class="wa-main"><b>${escapeHtml(m.product_name)}</b><span>${m.date} · ${what}${showPrice && m.purchase_price ? ` · ${fmtNum(m.purchase_price)} ${T.currency}/${T.whs_per_unit}` : ''}</span></div>
      <b style="color:${col}; white-space:nowrap;">${sign}${whQty(m.quantity)} ${whUnit(m.unit)}</b>
    </div>`;
  }).join('');
}


let revenueChartInstance = null;

function renderRevenueChart(dailyData) {
  revenueChartInstance = drawRevenueBars('revenueChart', 'revenueSummary', dailyData, revenueChartInstance);
}

function rvDateLabel(iso, withWeekday) {
  const [y, m, d] = iso.split('-').map(Number);
  const months = T.st_months.split(',');
  const wd = T.st_weekdays.split(',');  // с понедельника
  const dow = (new Date(y, m - 1, d).getDay() + 6) % 7;
  return (withWeekday ? wd[dow] + ', ' : '') + d + ' ' + months[m - 1];
}

function rvWeekdayHtml(dailyData) {
  const sum = [0, 0, 0, 0, 0, 0, 0], cnt = [0, 0, 0, 0, 0, 0, 0];
  (dailyData || []).forEach(d => {
    const [y, m, dd] = d.date.split('-').map(Number);
    const dow = (new Date(y, m - 1, dd).getDay() + 6) % 7;  // с понедельника
    sum[dow] += d.total || 0;
    cnt[dow] += 1;
  });
  const avgs = sum.map((s, i) => cnt[i] ? Math.round(s / cnt[i]) : 0);
  const max = Math.max(...avgs);
  if (!max) return '';
  const best = avgs.indexOf(max);
  const wd = T.st_weekdays.split(',');
  return `<div class="ig-wd-h"><span>${T.ig_wd_title}</span><b>${T.ig_wd_best.replace('{day}', wd[best]).replace('{sum}', fmtShort(max))}</b></div>
    <div class="ig-wd">${avgs.map((v, i) => `<div class="${i === best ? 'top' : ''}" title="${wd[i]}: ${fmtNum(v)} ${T.currency}"><em><i style="height:${Math.max(3, v / max * 100)}%;"></i></em><span>${wd[i]}</span></div>`).join('')}</div>`;
}

function drawRevenueBars(canvasId, summaryId, dailyData, prevInstance) {
  // Столбик на каждый день. Лучший день подсвечен красным, пунктир — средняя
  // выручка за рабочий день (дни без продаж в среднее не входят).
  const canvas = document.getElementById(canvasId);
  if (prevInstance) prevInstance.destroy();
  dailyData = dailyData || [];
  const totals = dailyData.map(d => d.total || 0);
  const sum = totals.reduce((a, b) => a + b, 0);
  const workDays = totals.filter(v => v > 0).length;
  const avg = workDays ? Math.round(sum / workDays) : 0;
  const maxVal = Math.max(0, ...totals);
  const bestIdx = maxVal > 0 ? totals.indexOf(maxVal) : -1;
  const visits = dailyData.reduce((a, d) => a + (d.count || 0), 0);

  const summaryEl = document.getElementById(summaryId);
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="rv-box"><b>${fmtShort(sum)}</b><span>${T.rv_total} · ${visits} ${T.brands_visits}</span></div>
      <div class="rv-box"><b>${fmtShort(avg)}</b><span>${T.rv_avg_day}</span></div>
      <div class="rv-box"><b>${workDays} / ${dailyData.length}</b><span>${T.rv_work_days}</span></div>
      ${bestIdx >= 0 ? `<div class="rv-box best"><b>${fmtShort(maxVal)}</b><span>${T.rv_best_day}: ${rvDateLabel(dailyData[bestIdx].date, false)}</span></div>` : ''}
    `;
  }
  if (!canvas || typeof Chart === 'undefined') return null;

  // легенда под графиком (создаём один раз)
  const wrap = canvas.parentElement;
  let legend = wrap.nextElementSibling;
  if (!legend || !legend.classList.contains('rv-legend')) {
    legend = document.createElement('div');
    legend.className = 'rv-legend';
    wrap.after(legend);
  }
  legend.innerHTML = `
    <span><i style="background:#0F52BA;"></i>${T.rv_legend_day}</span>
    ${bestIdx >= 0 ? `<span><i style="background:#E63946;"></i>${T.rv_best_day}</span>` : ''}
    ${avg ? `<span><i style="background:repeating-linear-gradient(90deg,#F59E0B 0 4px,transparent 4px 7px); height:3px; vertical-align:3px;"></i>${T.rv_avg_short}: ${fmtShort(avg)}</span>` : ''}
  `;
  // инфографика «по дням недели»: средняя выручка в понедельник, вторник…
  let wdEl = legend.nextElementSibling;
  if (!wdEl || !wdEl.classList.contains('ig-wd-wrap')) {
    wdEl = document.createElement('div');
    wdEl.className = 'ig-wd-wrap';
    legend.after(wdEl);
  }
  wdEl.innerHTML = rvWeekdayHtml(dailyData);
  wdEl.hidden = !wdEl.innerHTML;

  const colors = totals.map((v, i) => i === bestIdx ? '#E63946' : '#0F52BA');
  const avgLine = {
    id: 'avgLine',
    afterDatasetsDraw(chart) {
      if (!avg) return;
      const y = chart.scales.y.getPixelForValue(avg);
      const area = chart.chartArea;
      const ctx = chart.ctx;
      ctx.save();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = '#F59E0B';
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(area.left, y); ctx.lineTo(area.right, y); ctx.stroke();
      ctx.restore();
    }
  };

  const chart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: dailyData.map(d => rvDateLabel(d.date, false)),
      datasets: [{
        data: totals,
        backgroundColor: colors,
        hoverBackgroundColor: totals.map((v, i) => i === bestIdx ? '#C81E2B' : '#0A3D8F'),
        borderRadius: 5, borderSkipped: false,
        maxBarThickness: 26, categoryPercentage: 0.8, barPercentage: 0.9,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false, padding: 10,
          callbacks: {
            title: items => rvDateLabel(dailyData[items[0].dataIndex].date, true),
            label: item => `${fmtNum(item.raw)} ${T.currency}`,
            afterLabel: item => {
              const d = dailyData[item.dataIndex];
              return d.count ? `${d.count} ${T.brands_visits}` : T.rv_no_sales;
            },
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { autoSkip: true, maxTicksLimit: 8, maxRotation: 0, color: '#94A3B8', font: { size: 11 } },
        },
        y: {
          beginAtZero: true,
          border: { display: false },
          grid: { color: '#F1F5F9' },
          ticks: { maxTicksLimit: 5, color: '#94A3B8', font: { size: 11 }, callback: v => fmtShort(v) },
        }
      }
    },
    plugins: [avgLine],
  });
  return chart;
}

async function toggleCategoryBrands(categoryName, idx) {
  const panel = document.getElementById('catBrands_' + idx);
  if (!panel) return;
  const isOpen = panel.style.display !== 'none';
  document.querySelectorAll('.dash-brands-panel').forEach(el => { if (el !== panel) el.style.display = 'none'; });
  if (isOpen) { panel.style.display = 'none'; return; }
  panel.innerHTML = T.stats_loading;
  panel.style.display = 'block';
  const brands = await (await fetch('/api/dashboard/top_brands?category=' + encodeURIComponent(categoryName))).json();
  panel.innerHTML = brands.length ? brands.map((b, j) => `
    <div class="dash-row" style="padding-left:28px; font-size:12.5px;">
      <span class="dash-row-name">${j + 1}. ${escapeHtml(b.name)}</span>
      <span class="dash-row-value">${b.qty.toLocaleString('ru-RU')}</span>
    </div>
  `).join('') : `<div class="hint-text" style="padding-left:28px;">${T.dash_no_data}</div>`;
}

async function loadDashboard() {
  const res = await fetch('/api/dashboard');
  const data = await res.json();

  renderRevenueChart(data.daily_revenue);

  const netEl = document.getElementById('dashNetProfit');
  if (netEl && data.net_profit) netEl.innerHTML = renderNetProfitHtml(data.net_profit);
  const debtEl = document.getElementById('dashDebtSummary');
  if (debtEl) debtEl.innerHTML = renderDebtHtml(data.debt_summary);
  const lowEl = document.getElementById('dashLowStock');
  if (lowEl) lowEl.innerHTML = renderLowStockHtml(data.low_stock, false);
}

function renderNetProfitHtml(np) {
  // прибыль = товары со склада (продажа − закупка) + работа/услуги; минус расходы.
  // Продажи без цены закупки в прибыль не входят — показываем их отдельно.
  const isNegative = np.net_profit < 0;
  const services = np.services || 0;
  const unpriced = np.unpriced || 0;
  return `
    <div class="dash-summary-grid" style="grid-template-columns:repeat(3, minmax(0, 1fr)); gap:8px;">
      <div class="dash-summary-box">
        <div class="dsb-num" style="font-size:15px; white-space:nowrap;" title="${np.oil_profit.toLocaleString('ru-RU')} ${T.currency}">${fmtShort(np.oil_profit)}</div>
        <div class="dsb-label">${T.np_goods_label}</div>
      </div>
      <div class="dash-summary-box">
        <div class="dsb-num" style="font-size:15px; white-space:nowrap;" title="${services.toLocaleString('ru-RU')} ${T.currency}">${fmtShort(services)}</div>
        <div class="dsb-label">${T.np_services_label}</div>
      </div>
      <div class="dash-summary-box">
        <div class="dsb-num warn" style="font-size:15px; white-space:nowrap;" title="${np.expenses_total.toLocaleString('ru-RU')} ${T.currency}">−${fmtShort(np.expenses_total)}</div>
        <div class="dsb-label">${T.dash_expenses_label}</div>
      </div>
    </div>
    <div style="text-align:center; margin-top:12px; padding-top:12px; border-top:1px dashed #86EFAC;">
      <div style="font-size:24px; font-weight:700; font-family:var(--font-mono); color:${isNegative ? '#B3241C' : '#15803D'};">${np.net_profit.toLocaleString('ru-RU')} ${T.currency}</div>
      ${np.net_profit_usd != null ? `<div style="font-size:13px; font-family:var(--font-mono); color:var(--hint); margin-top:2px;">${usdApprox(np.net_profit_usd)} · ${T.usd_by_day_rate}</div>` : ''}
      <div style="font-size:11px; color:var(--hint); margin-top:2px;">${T.dash_net_profit_label}</div>
    </div>
    ${(np.discounts || 0) > 0 ? `
    <div style="margin-top:10px; font-size:12px; color:var(--hint); text-align:center;"><i class="fa-solid fa-tag"></i> ${T.np_discounts_1} <b>−${(np.discounts).toLocaleString('ru-RU')} ${T.currency}</b> ${T.np_discounts_2}</div>` : ''}
    ${(np.markups || 0) > 0 ? `
    <div style="margin-top:6px; font-size:12px; color:var(--hint); text-align:center;"><i class="fa-solid fa-arrow-trend-up"></i> ${T.np_markups_1} <b style="color:#15803D;">+${(np.markups).toLocaleString('ru-RU')} ${T.currency}</b> ${T.np_markups_2}</div>` : ''}
    ${unpriced > 0 ? `
    <div style="margin-top:12px; padding:10px 12px; background:#FFFBEB; border:1px solid #FCD34D; border-radius:12px; font-size:12.5px; color:#92400E;">
      ⚠️ ${T.np_unpriced_1} <b>${unpriced.toLocaleString('ru-RU')} ${T.currency}</b> ${T.np_unpriced_2}
    </div>` : ''}`;
}

function renderDebtHtml(ds) {
  return `
    <div class="dash-summary-grid">
      <div class="dash-summary-box">
        <div class="dsb-num">${ds.total_remaining.toLocaleString('ru-RU')} ${T.currency}</div>
        <div class="dsb-label">${T.dash_total_owed}</div>
      </div>
      <div class="dash-summary-box">
        <div class="dsb-num ${ds.overdue_count > 0 ? 'warn' : ''}">${ds.overdue_count} / ${ds.count}</div>
        <div class="dsb-label">${T.dash_overdue_of_total}</div>
      </div>
    </div>`;
}

function renderLowStockHtml(list, withShop) {
  if (!list || !list.length) return `<div class="hint-text">${T.dash_no_data}</div>`;
  return list.map(p => `
    <div class="dash-row">
      <span class="dash-row-name">${escapeHtml(p.name)}${withShop && p.shop_name ? ` <span class="hint-text">· ${escapeHtml(p.shop_name)}</span>` : ''}</span>
      <span class="dash-row-value warn">${p.stock_qty} ${p.unit === 'pc' ? T.unit_pc : T.unit_l}</span>
    </div>`).join('');
}

const BRAND_COLORS = ['#0F52BA', '#E63946', '#F4A261', '#2A9D8F', '#8E44AD', '#E9C46A', '#1D3557', '#06B6D4', '#84CC16', '#EC4899'];
const BRAND_OTHERS_COLOR = '#CBD5E1';
// Карточка брендов — одна логика для своей точки (prefix 'brand') и для сети
// филиалов (prefix 'netBrand', scope = 'all' или id филиала).
const BRAND_W = {};
function bw(p) {
  if (!BRAND_W[p]) BRAND_W[p] = { data: null, cat: null, days: 30, chart: null, scope: '' };
  return BRAND_W[p];
}

function fmtNum(n) { return Number(n || 0).toLocaleString('ru-RU'); }

function brandUnitLabel(unit) {
  if (unit === 'l') return T.unit_l;
  if (unit === 'pc') return T.unit_pc;
  return '';
}

function renderBrandPeriod(p) {
  const el = document.getElementById(p + 'Period');
  if (!el) return;
  const opts = [[30, T.brands_period_30], [90, T.brands_period_90], [365, T.brands_period_365]];
  el.innerHTML = opts.map(([d, label]) =>
    `<button class="${d === bw(p).days ? 'active' : ''}" onclick="setBrandDays('${p}', ${d})">${label}</button>`
  ).join('');
}

function setBrandDays(p, d) {
  bw(p).days = d;
  loadBrandStats(p);
}

async function loadBrandStats(p) {
  p = p || 'brand';
  const body = document.getElementById(p + 'Body');
  if (!body) return;
  renderBrandPeriod(p);
  const to = new Date();
  const from = new Date();
  from.setDate(to.getDate() - (bw(p).days - 1));
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  try {
    var brandSeq = (bw(p).seq = (bw(p).seq || 0) + 1);
    const scopeQs = bw(p).scope ? `&scope=${bw(p).scope}` : '';
    const res = await fetch(`/api/stats/brands?from=${iso(from)}&to=${iso(to)}${scopeQs}`);
    const fresh = await res.json();
    if (brandSeq !== bw(p).seq) return;  // пока грузилось, сменили период или точку
    bw(p).data = fresh;
  } catch (e) { bw(p).data = null; }
  const cats = (bw(p).data && bw(p).data.categories) || [];
  const chips = document.getElementById(p + 'CategoryChips');
  if (!cats.length) {
    chips.innerHTML = '';
    body.innerHTML = `<div class="hint-text">${T.brands_empty}</div>`;
    if (bw(p).chart) { bw(p).chart.destroy(); bw(p).chart = null; }
    return;
  }
  if (!cats.some(c => c.key === bw(p).cat)) bw(p).cat = cats[0].key;
  chips.innerHTML = cats.map(c => {
    const sub = c.metric === 'sum' ? '' : `<span class="bc-sub">${fmtNum(c.total_qty)} ${brandUnitLabel(c.unit)}</span>`;
    return `<div class="brand-chip ${c.key === bw(p).cat ? 'active' : ''}" onclick="selectBrandCategory('${p}', '${c.key}')">${escapeHtml(T[c.key] || c.key)}${sub}</div>`;
  }).join('');
  renderBrandCategory(p);
}

function selectBrandCategory(p, key) {
  bw(p).cat = key;
  document.querySelectorAll(`#${p}CategoryChips .brand-chip`).forEach(el => {
    el.classList.toggle('active', el.getAttribute('onclick').indexOf(`'${key}'`) !== -1);
  });
  renderBrandCategory(p);
}

function renderBrandCategory(p) {
  const body = document.getElementById(p + 'Body');
  const c = ((bw(p).data && bw(p).data.categories) || []).find(x => x.key === bw(p).cat);
  if (!c) return;
  const unit = brandUnitLabel(c.unit);
  const bySum = c.metric === 'sum';
  const mainVal = x => bySum ? `${fmtNum(x.sum)} ${T.currency}` : `${fmtNum(x.qty)} ${unit}`;
  const brandLabel = b => b.no_brand ? T.brands_no_brand : escapeHtml(b.name);

  // полоски считаем относительно лидера (лидер = полная полоска), а % справа — доля от всего
  const leaderVal = c.top.length ? (bySum ? c.top[0].sum : c.top[0].qty) || 1 : 1;
  const barW = x => Math.max(Math.round((bySum ? x.sum : x.qty) / leaderVal * 100), 2);
  const rows = c.top.map((b, i) => `
    <div class="brand-row">
      <div class="brand-row-top">
        <span class="brand-rank" style="background:${BRAND_COLORS[i]};">${i + 1}</span>
        <span class="brand-name">${brandLabel(b)}${i === 0 && c.top.length > 1 ? ' 🏆' : ''}</span>
        <span class="brand-val">${mainVal(b)}</span>
        <span class="brand-share">${b.share}%</span>
      </div>
      <div class="brand-bar"><i style="width:${barW(b)}%; background:${BRAND_COLORS[i]};"></i></div>
      <div class="brand-meta">${bySum ? '' : `${fmtNum(b.sum)} ${T.currency} · `}${b.visits} ${T.brands_visits}</div>
    </div>
  `).join('');
  const othersRow = c.others ? `
    <div class="brand-row">
      <div class="brand-row-top">
        <span class="brand-rank" style="background:${BRAND_OTHERS_COLOR}; color:#475569;">…</span>
        <span class="brand-name" style="color:#64748B;">${T.brands_others} (${c.others.count})</span>
        <span class="brand-val" style="color:#64748B;">${mainVal(c.others)}</span>
        <span class="brand-share">${c.others.share}%</span>
      </div>
      <div class="brand-bar"><i style="width:${Math.min(barW(c.others), 100)}%; background:${BRAND_OTHERS_COLOR};"></i></div>
    </div>` : '';

  body.innerHTML = `
    <div class="brand-summary">
      <div><b>${bySum ? fmtNum(c.top.reduce((a, b) => a + b.visits, 0)) : fmtNum(c.total_qty) + ' ' + unit}</b><span>${bySum ? T.brands_visits : T.brands_total_sold}</span></div>
      <div><b>${fmtNum(c.total_sum)}</b><span>${T.brands_revenue}, ${T.currency}</span></div>
      <div><b>${c.brand_count}</b><span>${bySum ? T.brands_items : T.brands_count}</span></div>
    </div>
    <div class="brand-donut-wrap"><canvas id="${p}Donut"></canvas></div>
    ${rows}${othersRow}
  `;
  renderBrandDonut(p, c, bySum ? `${fmtNum(c.total_sum)}` : `${fmtNum(c.total_qty)}`, bySum ? T.currency : unit);
}

function renderBrandDonut(p, c, centerValue, centerUnit) {
  const canvas = document.getElementById(p + 'Donut');
  if (!canvas || typeof Chart === 'undefined') return;
  if (bw(p).chart) bw(p).chart.destroy();
  const bySum = c.metric === 'sum';
  const labels = c.top.map(b => b.no_brand ? T.brands_no_brand : b.name);
  const values = c.top.map(b => bySum ? b.sum : b.qty);
  const colors = c.top.map((_, i) => BRAND_COLORS[i]);
  if (c.others) {
    labels.push(`${T.brands_others} (${c.others.count})`);
    values.push(bySum ? c.others.sum : c.others.qty);
    colors.push(BRAND_OTHERS_COLOR);
  }
  const centerText = {
    id: 'centerText',
    afterDraw(chart) {
      const meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data || !meta.data.length) return;
      const x = meta.data[0].x, y = meta.data[0].y;
      const ctx = chart.ctx;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = window.glColor ? glColor('#0F172A') : '#0F172A';
      ctx.font = "700 20px 'Space Grotesk', sans-serif";
      ctx.fillText(centerValue, x, y - 8);
      ctx.fillStyle = window.glColor ? glColor('#64748B') : '#64748B';
      ctx.font = "500 12px sans-serif";
      ctx.fillText(centerUnit, x, y + 13);
      ctx.restore();
    }
  };
  bw(p).chart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: '#fff', borderWidth: 2, hoverOffset: 6 }] },
    options: {
      responsive: true, cutout: '64%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => {
              const total = values.reduce((a, b) => a + b, 0) || 1;
              const pct = Math.round(item.raw / total * 1000) / 10;
              return ` ${item.label}: ${fmtNum(item.raw)} ${centerUnit} (${pct}%)`;
            }
          }
        }
      }
    },
    plugins: [centerText],
  });
}

function fmtShort(n) {
  // компактно для второстепенных цифр: 19 496 586 -> 19,5 млн; 710 000 -> 710 тыс
  n = Number(n || 0);
  const abs = Math.abs(n);
  if (abs >= 1e6) return (Math.round(n / 1e5) / 10).toLocaleString('ru-RU') + ' ' + T.st_mln;
  if (abs >= 1e4) return Math.round(n / 1e3).toLocaleString('ru-RU') + ' ' + T.st_thousand;
  return n.toLocaleString('ru-RU');
}

function stBadge(pct, extraClass) {
  if (pct === null || pct === undefined) return '';
  const up = pct >= 0;
  return `<span class="st-badge ${up ? 'up' : 'down'} ${extraClass || ''}">${up ? '↑' : '↓'} ${up ? '+' : ''}${String(pct).replace('.', ',')}%</span>`;
}

function stMoneyNote(d) {
  const parts = [];
  if (d.debt_out) parts.push(T.st_m_debt_out.replace('{sum}', fmtShort(d.debt_out)));
  if (d.repaid) parts.push(T.st_m_repaid.replace('{sum}', fmtShort(d.repaid)));
  if (!parts.length) return '';
  const txt = parts.join(' · ');
  return txt.charAt(0).toUpperCase() + txt.slice(1);
}

function renderStatCard(o) {
  // o = { label, d: {total,count,avg,paid_count,cash,card,repaid,debt_out,clients}, cmp, cmpNote, profit, orange }
  const d = o.d || {};
  const cmp = o.cmp || null;
  const cl = d.clients || { total: 0, new: 0, returning: 0 };
  const cash = d.cash || 0, card = d.card || 0, debtOut = d.debt_out || 0, repaid = d.repaid || 0;
  const received = cash + card + repaid;
  const paySum = (cash + card + debtOut) || 1;
  const clSum = cl.total || 1;
  const badgeLine = cmp && cmp.pct !== null && cmp.pct !== undefined
    ? `${stBadge(cmp.pct)}<span class="st-badge-note">${o.cmpNote || ''}</span>` : '';
  const empty = !d.count;
  const note = stMoneyNote(d);
  return `
    <div class="st-card ${o.orange ? 'orange' : ''}">
      <div class="st-label">${o.label}</div>
      <div class="st-money">
        <div><div class="st-money-k">${T.st_m_revenue}</div><div class="st-money-v rev">${fmtNum(d.total)}<small>${T.currency}</small></div></div>
        <div><div class="st-money-k">${T.st_m_received}</div><div class="st-money-v got">${fmtNum(received)}<small>${T.currency}</small></div></div>
      </div>
      ${badgeLine ? `<div class="st-badge-line" style="min-height:0;">${badgeLine}</div>` : ''}
      ${note ? `<div class="st-money-note">${note}</div>` : ''}
      ${empty ? `<div class="st-empty">${T.st_no_visits}</div>` : `
      <div class="st-row"><span>${T.st_services}</span><b>${d.count}</b></div>
      ${d.paid_count ? `<div class="st-row"><span>${T.st_avg}</span><b>${fmtNum(d.avg)} ${T.currency}${cmp ? stBadge(cmp.avg_pct) : ''}</b></div>` : ''}
      ${cl.total ? `
      <div class="st-block">
        <div class="st-block-head"><span>${T.st_clients}</span><b>${cl.total}</b></div>
        <div class="st-split"><i style="width:${cl.new / clSum * 100}%; background:#3B82F6;"></i><i style="width:${cl.returning / clSum * 100}%; background:#14B8A6;"></i></div>
        <div class="st-legend"><span style="--dot:#3B82F6;">${cl.new} ${T.st_new}</span><span style="--dot:#14B8A6;">${cl.returning} ${T.st_returning}</span></div>
      </div>` : ''}
      ${(cash || card || debtOut) ? `
      <div class="st-block">
        <div class="st-block-head"><span>${T.st_payment}</span></div>
        <div class="st-split"><i style="width:${cash / paySum * 100}%; background:#22C55E;"></i><i style="width:${card / paySum * 100}%; background:#6366F1;"></i>${debtOut ? `<i style="width:${debtOut / paySum * 100}%; background:#F59E0B;"></i>` : ''}</div>
        <div class="st-legend"><span style="--dot:#22C55E;">${T.st_cash} ${fmtShort(cash)}</span><span style="--dot:#6366F1;">${T.st_card} ${fmtShort(card)}</span>${debtOut ? `<span style="--dot:#F59E0B;">${T.st_debt_part} ${fmtShort(debtOut)}</span>` : ''}</div>
      </div>` : ''}
      ${o.profit !== null && o.profit !== undefined ? `<div class="st-row profit"><span>${T.st_profit}</span><b>${fmtNum(o.profit)} ${T.currency}${o.profitUsd != null ? `<small style="display:block; font-weight:500; color:var(--hint); font-size:11.5px;">${usdApprox(o.profitUsd)}</small>` : ''}</b></div>` : ''}
      `}
    </div>`;
}

function renderTodayStrip(d, profit, withDetails) {
  d = d || {};
  const cl = d.clients || {};
  const chips = d.count ? `
    <div class="st-today-chips">
      <span class="st-chip">${T.st_services}: <b>${d.count}</b></span>
      ${d.paid_count ? `<span class="st-chip">${T.st_avg}: <b>${fmtShort(d.avg)}</b></span>` : ''}
      ${cl.total ? `<span class="st-chip">${T.st_clients}: <b>${cl.total}</b> (${cl.new} ${T.st_new})</span>` : ''}
      ${profit !== null && profit !== undefined ? `<span class="st-chip" style="background:#DCFCE7;">${T.st_profit}: <b style="color:#15803D;">${fmtShort(profit)}</b></span>` : ''}
      ${(d.debt_out || d.repaid) ? `<span class="st-chip">${T.st_m_received}: <b style="color:#15803D;">${fmtShort((d.cash || 0) + (d.card || 0) + (d.repaid || 0))}</b></span>` : ''}
      ${d.debt_out ? `<span class="st-chip" style="background:#FEF3C7;">${T.st_debt_part}: <b style="color:#92400E;">${fmtShort(d.debt_out)}</b></span>` : ''}
    </div>` : `<div class="st-empty">${T.st_today_empty}</div>`;
  return `
    <div class="st-today">
      <div class="st-today-main">
        <span class="st-today-label">${T.stats_today}</span>
        <span class="st-today-amount">${fmtNum(d.total)}<small>${T.currency}</small></span>
        ${withDetails ? `<button type="button" class="st-day-btn" onclick="openDayDetails()"><i class="fa-solid fa-list-ul"></i> ${T.dd_btn}</button>` : ''}
      </div>
      ${chips}
    </div>`;
}

const ST_PERIODS = () => [
  ['week', T.stats_week, T.st_vs_week],
  ['month', T.stats_month, T.st_vs_month],
  ['year', T.stats_year, T.st_vs_year],
];

const NET = { scope: 'all', period: 'month', shops: [], revChart: null, cmpChart: null };

function setNetScope(scope) {
  NET.scope = String(scope);
  loadNetwork();
  const head = document.getElementById('netDetailHead');
  if (head) head.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function loadNetwork() {
  const grid = document.getElementById('netStatsGrid');
  if (!grid) return;
  let data;
  try {
    var netSeq = (NET.seq = (NET.seq || 0) + 1);
    data = await (await fetch(`/api/network/overview?scope=${encodeURIComponent(NET.scope)}`)).json();
  } catch (e) { return; }
  if (netSeq !== NET.seq) return;  // пока грузилось, выбрали другую точку
  if (!data.ok) return;
  NET.shops = data.shops || [];
  const isAll = NET.scope === 'all';

  document.getElementById('netScopeChips').innerHTML =
    [`<div class="brand-chip ${isAll ? 'active' : ''}" onclick="setNetScope('all')">${T.net_all}<span class="bc-sub">${NET.shops.length}</span></div>`]
      .concat(NET.shops.map(sh => `<div class="brand-chip ${NET.scope === String(sh.id) ? 'active' : ''}" onclick="setNetScope('${sh.id}')">${escapeHtml(sh.name)}${sh.is_head ? `<span class="bc-sub">${T.branch_head_label}</span>` : ''}</div>`))
      .join('');

  grid.innerHTML =
    renderTodayStrip(data.stats.today, data.profit.today) +
    `<div class="st-grid">${ST_PERIODS().map(([key, label, note]) => renderStatCard({
      label, d: data.stats[key], cmp: data.comparison[key], cmpNote: note,
      profit: data.profit[key], profitUsd: data.profit_usd ? data.profit_usd[key] : null, orange: isAll,
    })).join('')}</div>`;

  document.getElementById('netNetProfit').innerHTML = renderNetProfitHtml(data.net_profit);
  NET.revChart = drawRevenueBars('netRevenueChart', 'netRevenueSummary', data.daily_revenue, NET.revChart);
  document.getElementById('netDebtSummary').innerHTML = renderDebtHtml(data.debt_summary);
  document.getElementById('netLowStock').innerHTML = renderLowStockHtml(data.low_stock, isAll);

  bw('netBrand').scope = NET.scope;
  loadBrandStats('netBrand');

  document.querySelectorAll('#netCompareBody tbody tr').forEach(tr => {
    tr.classList.toggle('active', tr.dataset.shop === NET.scope);
  });
}

function setNetComparePeriod(p) {
  NET.period = p;
  loadNetworkCompare();
}

async function loadNetworkCompare() {
  const body = document.getElementById('netCompareBody');
  if (!body) return;
  document.getElementById('netComparePeriod').innerHTML =
    [['week', T.stats_week], ['month', T.stats_month], ['year', T.stats_year]]
      .map(([k, label]) => `<button class="${k === NET.period ? 'active' : ''}" onclick="setNetComparePeriod('${k}')">${label}</button>`).join('');
  let data;
  try {
    var cmpSeq = (NET.cseq = (NET.cseq || 0) + 1);
    data = await (await fetch(`/api/network/compare?period=${NET.period}`)).json();
  } catch (e) { return; }
  if (cmpSeq !== NET.cseq) return;
  if (!data.ok) return;
  const rows = data.rows || [];
  if (!rows.length) { body.innerHTML = `<div class="hint-text">${T.dash_no_data}</div>`; return; }

  // лучший показатель в каждой колонке подсвечиваем зелёным
  const maxOf = f => Math.max(...rows.map(f));
  const best = {
    total: maxOf(r => r.total), count: maxOf(r => r.count), avg: maxOf(r => r.avg),
    clients: maxOf(r => r.clients.total), profit: maxOf(r => r.profit), net: maxOf(r => r.net_profit),
  };
  const many = rows.length > 1;
  const cls = (v, b) => (many && v > 0 && v === b) ? 'best' : '';
  const sum = f => rows.reduce((a, r) => a + f(r), 0);
  const totPaid = sum(r => r.paid_count);
  const tot = {
    total: sum(r => r.total), count: sum(r => r.count),
    clients: sum(r => r.clients.total), newc: sum(r => r.clients.new),
    profit: sum(r => r.profit), expenses: sum(r => r.expenses), net: sum(r => r.net_profit),
  };
  const totAvg = totPaid ? Math.round(tot.total / totPaid) : 0;

  body.innerHTML = `
    <div class="table-wrap"><table class="net-cmp">
      <thead><tr>
        <th>${T.net_col_shop}</th><th>${T.net_col_revenue}</th><th>${T.net_col_change}</th>
        <th>${T.net_col_services}</th><th>${T.net_col_avg}</th><th>${T.net_col_clients}</th>
        <th>${T.net_col_profit}</th><th>${T.net_col_expenses}</th><th>${T.net_col_net}</th>
      </tr></thead>
      <tbody>${rows.map((r, i) => `
        <tr data-shop="${r.id}" class="${NET.scope === String(r.id) ? 'active' : ''}" onclick="setNetScope('${r.id}')">
          <td><div class="shop-cell"><span class="brand-rank" style="background:${BRAND_COLORS[i % BRAND_COLORS.length]};">${i + 1}</span>${escapeHtml(r.name)}${r.is_head ? ` <small>${T.branch_head_label}</small>` : ''}${i === 0 && many && r.total > 0 ? ' 🏆' : ''}</div></td>
          <td class="${cls(r.total, best.total)}">${fmtNum(r.total)}</td>
          <td>${r.pct === null || r.pct === undefined ? '—' : stBadge(r.pct)}</td>
          <td class="${cls(r.count, best.count)}">${r.count}</td>
          <td class="${cls(r.avg, best.avg)}">${r.paid_count ? fmtNum(r.avg) : '—'}</td>
          <td class="${cls(r.clients.total, best.clients)}">${r.clients.total} <span class="hint-text">(${r.clients.new})</span></td>
          <td class="${cls(r.profit, best.profit)}">${r.unpriced > 0 ? `<span title="${T.np_row_unpriced} ${fmtNum(r.unpriced)} ${T.currency}" style="cursor:help;">⚠️</span> ` : ''}${fmtNum(r.profit)}</td>
          <td>${fmtNum(r.expenses)}</td>
          <td class="${r.net_profit < 0 ? 'neg' : cls(r.net_profit, best.net)}">${fmtNum(r.net_profit)}</td>
        </tr>`).join('')}
      </tbody>
      <tfoot><tr>
        <td>${T.net_total_row}</td><td>${fmtNum(tot.total)}</td><td></td><td>${tot.count}</td>
        <td>${totPaid ? fmtNum(totAvg) : '—'}</td><td>${tot.clients} <span class="hint-text">(${tot.newc})</span></td>
        <td>${fmtNum(tot.profit)}</td><td>${fmtNum(tot.expenses)}</td>
        <td class="${tot.net < 0 ? 'neg' : ''}">${fmtNum(tot.net)}</td>
      </tr></tfoot>
    </table></div>
    <div class="hint-text" style="margin-top:6px;">${T.net_sum_note} ${T.currency}. ${T.net_clients_note}</div>`;

  // горизонтальные столбцы: выручка и чистая прибыль по каждой точке
  const wrap = document.getElementById('netCompareChartWrap');
  const canvas = document.getElementById('netCompareChart');
  if (!canvas || typeof Chart === 'undefined') return;
  wrap.style.height = (60 + rows.length * 56) + 'px';
  let legend = wrap.nextElementSibling;
  if (!legend || !legend.classList.contains('rv-legend')) {
    legend = document.createElement('div');
    legend.className = 'rv-legend';
    wrap.after(legend);
  }
  legend.innerHTML = `
    <span><i style="background:#0F52BA;"></i>${T.net_col_revenue}</span>
    <span><i style="background:#22C55E;"></i>${T.net_col_net}</span>
    <span><i style="background:#E63946;"></i>${T.net_loss}</span>`;
  if (NET.cmpChart) NET.cmpChart.destroy();
  NET.cmpChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => r.name),
      datasets: [
        { label: T.net_col_revenue, data: rows.map(r => r.total), backgroundColor: '#0F52BA', borderRadius: 5, maxBarThickness: 20 },
        { label: T.net_col_net, data: rows.map(r => r.net_profit), backgroundColor: rows.map(r => r.net_profit < 0 ? '#E63946' : '#22C55E'), borderRadius: 5, maxBarThickness: 20 },
      ]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: it => ` ${it.dataset.label}: ${fmtNum(it.raw)} ${T.currency}` } },
      },
      scales: {
        x: { beginAtZero: true, grid: { color: '#F1F5F9' }, border: { display: false }, ticks: { color: '#94A3B8', callback: v => fmtShort(v), maxTicksLimit: 5, maxRotation: 0 } },
        y: { grid: { display: false }, ticks: { color: '#0F172A', font: { weight: '600' } } },
      },
      onClick: (evt, els) => { if (els.length) setNetScope(String(rows[els[0].index].id)); },
    }
  });
}

async function loadStats() {
  loadDashboard();
  loadBrandStats();  // для сотрудника карточки нет — функция сама выйдет
  const res = await fetch('/api/stats');
  const s = await res.json();
  let profit = null;
  if (WAREHOUSE_ENABLED && !IS_BRANCH) {
    const pRes = await fetch('/api/profit_stats');
    profit = await pRes.json();
  }
  document.getElementById('statsGrid').innerHTML =
    renderTodayStrip(s.today, profit ? profit.today : null, true) +
    `<div class="st-grid">${ST_PERIODS().map(([key, label, note]) => renderStatCard({
      label, d: s[key], cmp: s.comparison && s.comparison[key], cmpNote: note,
      profit: profit ? profit[key] : null, profitUsd: profit && profit.usd ? profit.usd[key] : null,
    })).join('')}</div>`;
  if (window.glCount) glCount(document.getElementById('statsGrid'));

  if (!IS_BRANCH) {
    try {
      const agg = await (await fetch('/api/aggregated_stats')).json();
      const branchBtn = document.getElementById('substat-branches');
      if (agg.has_branches) {
        branchBtn.style.display = '';
        // сама сводка грузится при открытии вкладки (см. showStatsSubTab)
        if (document.getElementById('statsBranchesView').style.display !== 'none') {
          loadNetworkCompare();
          loadNetwork();
        }
      } else {
        branchBtn.style.display = 'none';
      }
    } catch (e) { /* не главный аккаунт или ошибка - просто не показываем подвкладку */ }
  }
}

function openDayDetails() {
  const inp = document.getElementById('ddDate');
  const d = new Date();
  const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  inp.max = today;
  inp.value = today;
  document.getElementById('dayDetailsModal').classList.add('open');
  loadDayDetails(today);
}

async function loadDayDetails(day) {
  // подробно за день: машины и работы, оплаты, долги, расходы, поставщики
  const body = document.getElementById('ddBody');
  body.innerHTML = T.stats_loading;
  const seq = (window.DD_SEQ = (window.DD_SEQ || 0) + 1);
  let data;
  try {
    data = await (await fetch('/api/stats/day?date=' + encodeURIComponent(day || ''))).json();
  } catch (e) { body.innerHTML = `<div class="dd-empty">${T.dd_load_error}</div>`; return; }
  if (seq !== window.DD_SEQ) return;  // пока грузилось, выбрали другой день
  if (!data.ok) { body.innerHTML = `<div class="dd-empty">${escapeHtml(data.error || '')}</div>`; return; }
  const t = data.totals;
  const money = n => `${fmtNum(n || 0)} ${T.currency}`;
  const tile = (label, val, color) => `<div><span>${label}</span><b${color ? ` style="color:${color};"` : ''}>${fmtNum(val || 0)}</b></div>`;
  let html = `<div class="dd-tot">
    ${tile(T.st_m_revenue, t.revenue)}
    ${tile(T.dd_income, t.income, '#15803D')}
    ${tile(T.dd_outcome, t.outcome, '#B91C1C')}
    ${tile(T.dd_balance, t.balance, t.balance < 0 ? '#B91C1C' : '#0F52BA')}
    ${tile(T.st_cash, t.cash)}
    ${tile(T.st_card, t.card)}
    ${t.debt_out ? tile(T.st_debt_part, t.debt_out, '#92400E') : ''}
    ${t.repaid ? tile(T.dd_repaid, t.repaid, '#15803D') : ''}
  </div>`;

  html += `<div class="dd-sec"><span>🚗 ${T.dd_services}</span><small>${t.count} · ${money(t.revenue)}</small></div>`;
  html += data.services.length ? data.services.map(s => {
    const car = [s.car_brand, s.car_model].filter(Boolean).join(' ');
    const owner = [s.owner_name, s.owner_phone].filter(Boolean).join(' · ');
    const lines = (s.items || []).map(i => {
      const unit = i.unit === 'pc' ? ' ' + T.unit_pc : (i.unit === 'l' ? ' ' + T.unit_l : '');
      const qty = i.qty ? ` × ${String(i.qty).replace('.', ',')}${unit}` : '';
      const brand = i.brand && i.brand !== i.name ? ` <span class="dd-sub" style="display:inline;">${escapeHtml(i.brand)}</span>` : '';
      return `<li><span>${escapeHtml(i.name || '')}${brand}${qty}</span><b>${fmtNum(i.total || 0)}</b></li>`;
    }).join('');
    const pays = [
      s.cash ? `<span>${T.st_cash}: <b>${fmtNum(s.cash)}</b></span>` : '',
      s.card ? `<span>${T.st_card}: <b>${fmtNum(s.card)}</b></span>` : '',
      s.debt ? `<span class="debt">${T.st_debt_part}: ${fmtNum(s.debt)}</span>` : '',
    ].join('');
    return `<div class="dd-item">
      <div class="dd-item-h"><span class="dd-plate">${escapeHtml(s.plate || '')}</span><b>${money(s.cost)}</b></div>
      ${car || owner ? `<div class="dd-sub">${escapeHtml(car)}${car && owner ? ' — ' : ''}${escapeHtml(owner)}</div>` : ''}
      ${s.mileage ? `<div class="dd-sub">${T.dd_mileage}: ${fmtNum(s.mileage)} ${T.dd_km}</div>` : ''}
      ${lines ? `<ul class="dd-lines">${lines}</ul>` : (s.service_type ? `<div class="dd-sub">${escapeHtml(s.service_type)}</div>` : '')}
      ${s.notes ? `<div class="dd-sub">📝 ${escapeHtml(s.notes)}</div>` : ''}
      ${pays ? `<div class="dd-pay">${pays}</div>` : ''}
    </div>`;
  }).join('') : `<div class="dd-empty">${T.dd_no_services}</div>`;

  if (data.repaid.length) {
    html += `<div class="dd-sec"><span>💰 ${T.dd_repaid}</span><small>${money(t.repaid)}</small></div>`;
    html += data.repaid.map(p => `<div class="dd-row"><span><b class="dd-plate" style="font-size:13px;">${escapeHtml(p.plate || '')}</b> ${escapeHtml(p.owner_name || '')}${p.remaining > 0 ? ` <span class="dd-sub" style="display:inline;">(${T.dd_left} ${fmtNum(p.remaining)})</span>` : ''}</span><b style="color:#15803D;">+${fmtNum(p.amount)}</b></div>`).join('');
  }
  html += `<div class="dd-sec"><span>🧾 ${T.dd_expenses}</span><small>${money(t.expenses)}</small></div>`;
  html += data.expenses.length
    ? data.expenses.map(e => `<div class="dd-row"><span>${escapeHtml(e.category || '')}${e.name ? ` — ${escapeHtml(e.name)}` : ''}</span><b style="color:#B91C1C;">−${fmtNum(e.amount)}</b></div>`).join('')
    : `<div class="dd-empty">${T.dd_none}</div>`;
  if (data.supplier_payments.length) {
    html += `<div class="dd-sec"><span>🚚 ${T.dd_suppliers}</span><small>${money(t.suppliers)}</small></div>`;
    html += data.supplier_payments.map(p => `<div class="dd-row"><span>${escapeHtml(p.supplier || '')}${p.note ? ` — ${escapeHtml(p.note)}` : ''}</span><b style="color:#B91C1C;">−${fmtNum(p.amount)}</b></div>`).join('');
  }
  body.innerHTML = html;
}

function showStatsSubTab(t) {
  document.getElementById('statsOwnView').style.display = t === 'own' ? 'block' : 'none';
  document.getElementById('statsBranchesView').style.display = t === 'branches' ? 'block' : 'none';
  document.getElementById('substat-own').classList.toggle('active', t === 'own');
  document.getElementById('substat-branches').classList.toggle('active', t === 'branches');
  if (t === 'branches') {
    loadNetworkCompare();
    loadNetwork();
  }
}

async function loadBranchProducts(branchId) {
  const panel = document.getElementById('branchProductsPanel');
  if (!branchId) { panel.innerHTML = ''; return; }
  const products = await (await fetch(`/api/branches/${branchId}/products`)).json();
  if (!products.length) { panel.innerHTML = `<div class="hint-text">${T.wh_no_products}</div>`; return; }
  panel.innerHTML = products.map(p => `
    <div style="padding:6px 0; border-bottom:1px dashed var(--border); font-size:13px;">
      <div>${escapeHtml(p.name)} <span class="hint-text">(${p.stock_qty} ${p.unit === 'pc' ? T.unit_pc : T.unit_l})</span></div>
      <div style="display:flex; align-items:center; gap:6px; margin-top:4px; flex-wrap:wrap;">
        <input id="branch_price_${branchId}_${p.id}" type="number" value="${p.purchase_price ?? ''}" placeholder="${T.wh_purchase_price}"
               style="width:100px; padding:5px 8px; font-size:12px; flex:none;"
               oninput="onSumFieldEdited('branch_price_${branchId}_${p.id}', 'branch_price_usd_${branchId}_${p.id}')">
        <input id="branch_price_usd_${branchId}_${p.id}" type="number" step="0.01" placeholder="$"
               style="width:80px; padding:5px 8px; font-size:12px; flex:none;"
               oninput="onUsdFieldEdited('branch_price_usd_${branchId}_${p.id}', 'branch_price_${branchId}_${p.id}')">
        <button class="badge active" style="flex:none;" onclick="setBranchPurchasePrice(${branchId}, ${p.id})">${T.branch_save_price}</button>
        <span id="branch_price_saved_${branchId}_${p.id}" style="display:none; color:#1B8A5A; font-size:15px; flex:none;">✓</span>
      </div>
    </div>
  `).join('');
}

async function setBranchPurchasePrice(branchId, productId) {
  const input = document.getElementById(`branch_price_${branchId}_${productId}`);
  await fetch(`/api/branches/${branchId}/products/${productId}/purchase_price`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({purchase_price: input.value})
  });
  const check = document.getElementById(`branch_price_saved_${branchId}_${productId}`);
  if (check) {
    check.style.display = 'inline';
    setTimeout(() => { check.style.display = 'none'; }, 1500);
  }
}

function fmtDate(d) {
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function setStatsRange(from, to) {
  document.getElementById('stats_from').value = fmtDate(from);
  document.getElementById('stats_to').value = fmtDate(to);
  applyStatsRange();
}

function renderStatsPresets() {
  const presetsEl = document.getElementById('statsPresets');
  if (!presetsEl) return;  // вкладка "Статистика" скрыта (например, для сотрудника)
  const today = new Date();
  const presets = [
    [T.stats_preset_today, () => setStatsRange(today, today)],
    [T.stats_preset_yesterday, () => {
      const y = new Date(today); y.setDate(y.getDate() - 1);
      setStatsRange(y, y);
    }],
    [T.stats_preset_7days, () => {
      const start = new Date(today); start.setDate(start.getDate() - 6);
      setStatsRange(start, today);
    }],
    [T.stats_preset_this_month, () => {
      const start = new Date(today.getFullYear(), today.getMonth(), 1);
      setStatsRange(start, today);
    }],
    [T.stats_preset_prev_month, () => {
      const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      const end = new Date(today.getFullYear(), today.getMonth(), 0);
      setStatsRange(start, end);
    }],
  ];
  document.getElementById('statsPresets').innerHTML = presets.map(([label], i) =>
    `<button class="lang-btn" onclick="STATS_PRESETS[${i}]()">${label}</button>`
  ).join('');
  window.STATS_PRESETS = presets.map(p => p[1]);
  const from = document.getElementById('stats_from');
  const to = document.getElementById('stats_to');
  if (!from.value) from.value = fmtDate(today);
  if (!to.value) to.value = fmtDate(today);
}

let currentRangeFrom = null, currentRangeTo = null;

async function applyStatsRange() {
  const from = document.getElementById('stats_from').value;
  const to = document.getElementById('stats_to').value;
  if (!from || !to) return;
  currentRangeFrom = from; currentRangeTo = to;
  const res = await fetch(`/api/stats/range?from=${from}&to=${to}`);
  const data = await res.json();
  if (!data.ok) { document.getElementById('statsRangeResult').innerHTML = ''; return; }
  const hasProfit = data.profit !== undefined;
  document.getElementById('statsRangeResult').innerHTML = `
    ${renderStatCard({ label: `${T.stats_range_result} ${from} — ${to}`, d: data, profit: hasProfit ? data.profit : null, profitUsd: hasProfit ? data.profit_usd : null })}
    ${hasProfit ? `
    <div class="stats-card" style="margin-top:10px; background:linear-gradient(135deg, #F0FDF4, #ECFDF5); border-color:#86EFAC;">
      ${renderNetProfitHtml({ oil_profit: data.goods_profit || 0, services: data.services || 0, unpriced: data.unpriced || 0, discounts: data.discounts || 0, markups: data.markups || 0, expenses_total: data.expenses || 0, net_profit: data.net_profit, net_profit_usd: data.net_profit_usd })}
    </div>
    ` : ''}
    <div class="stats-card" style="margin-top:10px;">
      <label style="font-size:14px; color:var(--text); font-weight:600; display:block; margin-bottom:10px;">${T.dash_revenue_chart_title}</label>
      <div id="rangeRevenueSummary" class="rv-summary"></div>
      <div class="rv-chart-wrap"><canvas id="rangeRevenueChart"></canvas></div>
    </div>
  `;
  renderRangeChart(data.daily_revenue);
}

let rangeChartInstance = null;
function renderRangeChart(dailyData) {
  rangeChartInstance = drawRevenueBars('rangeRevenueChart', 'rangeRevenueSummary', dailyData, rangeChartInstance);
}

async function toggleRangeCategoryBrands(categoryName, idx) {
  const panel = document.getElementById('rangeCatBrands_' + idx);
  if (!panel) return;
  const isOpen = panel.style.display !== 'none';
  document.querySelectorAll('.dash-brands-panel').forEach(el => { if (el !== panel) el.style.display = 'none'; });
  if (isOpen) { panel.style.display = 'none'; return; }
  panel.innerHTML = T.stats_loading;
  panel.style.display = 'block';
  const url = `/api/dashboard/top_brands?category=${encodeURIComponent(categoryName)}&from=${currentRangeFrom}&to=${currentRangeTo}`;
  const brands = await (await fetch(url)).json();
  panel.innerHTML = brands.length ? brands.map((b, j) => `
    <div class="dash-row" style="padding-left:28px; font-size:12.5px;">
      <span class="dash-row-name">${j + 1}. ${escapeHtml(b.name)}</span>
      <span class="dash-row-value">${b.qty.toLocaleString('ru-RU')}</span>
    </div>
  `).join('') : `<div class="hint-text" style="padding-left:28px;">${T.dash_no_data}</div>`;
}

renderStatsPresets();

function renderBranchStatsPresets() {
  const presetsEl = document.getElementById('branchStatsPresets');
  if (!presetsEl) return;  // подвкладка "Все филиалы" скрыта (нет филиалов) или недоступна
  const today = new Date();
  const presets = [
    [T.stats_preset_today, () => setBranchStatsRange(today, today)],
    [T.stats_preset_yesterday, () => {
      const y = new Date(today); y.setDate(y.getDate() - 1);
      setBranchStatsRange(y, y);
    }],
    [T.stats_preset_7days, () => {
      const start = new Date(today); start.setDate(start.getDate() - 6);
      setBranchStatsRange(start, today);
    }],
    [T.stats_preset_this_month, () => {
      const start = new Date(today.getFullYear(), today.getMonth(), 1);
      setBranchStatsRange(start, today);
    }],
    [T.stats_preset_prev_month, () => {
      const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      const end = new Date(today.getFullYear(), today.getMonth(), 0);
      setBranchStatsRange(start, end);
    }],
  ];
  presetsEl.innerHTML = presets.map(([label], i) =>
    `<button class="lang-btn" onclick="BRANCH_STATS_PRESETS[${i}]()">${label}</button>`
  ).join('');
  window.BRANCH_STATS_PRESETS = presets.map(p => p[1]);
  const from = document.getElementById('branch_stats_from');
  const to = document.getElementById('branch_stats_to');
  if (from && !from.value) from.value = fmtDate(today);
  if (to && !to.value) to.value = fmtDate(today);
}

function setBranchStatsRange(from, to) {
  document.getElementById('branch_stats_from').value = fmtDate(from);
  document.getElementById('branch_stats_to').value = fmtDate(to);
  applyBranchStatsRange();
}

async function applyBranchStatsRange() {
  const from = document.getElementById('branch_stats_from').value;
  const to = document.getElementById('branch_stats_to').value;
  if (!from || !to) return;
  const res = await fetch(`/api/aggregated_stats/range?from=${from}&to=${to}`);
  const data = await res.json();
  if (!data.ok) { document.getElementById('branchStatsRangeResult').innerHTML = ''; return; }

  const breakdown = data.breakdown || [];
  const breakdownRows = breakdown.map(r => `
    <tr>
      <td>${escapeHtml(r.shop_name)}${r.is_head ? ` <span class="hint-text">(${T.branch_head_label})</span>` : ''}</td>
      <td>${r.revenue.total.toLocaleString('ru-RU')} ${T.currency}</td>
      <td style="color:#1B8A5A;">${r.profit.toLocaleString('ru-RU')} ${T.currency}</td>
    </tr>
  `).join('');

  document.getElementById('branchStatsRangeResult').innerHTML = `
    <div style="margin-bottom:14px;">${renderStatCard({ label: `${T.stats_range_result} ${from} — ${to}`, d: data.revenue, profit: data.profit, orange: true })}</div>
    <div class="table-wrap"><table>
      <thead><tr><th>${T.branch_col_label}</th><th>${T.stats_revenue_label}</th><th>${T.stats_profit_label}</th></tr></thead>
      <tbody>${breakdownRows}</tbody>
    </table></div>
  `;

  renderBranchChart(breakdown);
}

function renderBranchChart(breakdown) {
  const wrap = document.getElementById('branchChartWrap');
  if (!wrap) return;
  if (typeof Chart === 'undefined' || !breakdown.length) { wrap.style.display = 'none'; return; }
  wrap.style.display = 'block';
  const canvas = document.getElementById('branchChart');
  if (window.branchChartInstance) { window.branchChartInstance.destroy(); }
  window.branchChartInstance = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: breakdown.map(r => r.shop_name),
      datasets: [
        { label: T.stats_revenue_label, data: breakdown.map(r => r.revenue.total), backgroundColor: '#E63946' },
        { label: T.branch_chart_profit_label, data: breakdown.map(r => r.profit), backgroundColor: '#1B8A5A' },
      ]
    },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true } } }
  });
}

renderBranchStatsPresets();

async function switchLanguage() {
  const newLang = LANG === 'ru' ? 'uz' : 'ru';
  await fetch('/api/set_language', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({language: newLang})
  });
  window.location.reload();
}

async function loadBroadcastInfo() {
  const res = await fetch('/api/broadcast/recipients');
  const data = await res.json();
  document.getElementById('broadcastRecipients').textContent =
    `${T.broadcast_recipients_text} ${data.count} ${T.broadcast_recipients_suffix}`;

  const res2 = await fetch('/api/broadcast/history');
  const items = await res2.json();
  document.getElementById('broadcastHistory').innerHTML = items.length ? items.map(b => `
    <div style="padding:8px 0;border-bottom:1px dashed var(--border);font-size:13px;">
      <div>${escapeHtml(b.message.length > 80 ? b.message.slice(0,80) + '…' : b.message)}</div>
      <div class="hint-text">${escapeHtml(b.created_at)} — ${T.broadcast_status_label} ${escapeHtml(b.status)}${b.status === 'done' ? `, ${T.broadcast_delivered} ${b.total_sent}, ${T.broadcast_failed} ${b.total_failed}` : ''}</div>
    </div>
  `).join('') : `<div class="hint-text">${T.broadcast_none_yet}</div>`;
}

async function sendBroadcast() {
  const message = document.getElementById('broadcast_message').value.trim();
  if (!message) { showMsg(T.broadcast_empty_msg, false); return; }
  if (!confirm(T.broadcast_confirm)) return;
  const res = await fetch('/api/broadcast', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({message})
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.broadcast_queued, true);
    document.getElementById('broadcast_message').value = '';
    setTimeout(loadBroadcastInfo, 4000);
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

function showMsg(text, ok) {
  const el = document.getElementById('msg');
  el.innerHTML = `<div class="msg ${ok ? 'ok' : 'err'}">${text}</div>`;
  setTimeout(() => { el.innerHTML = ''; }, 6000);
}

// ---- Жидкости и фильтры (детализация замены) ----
const FLUID_KEYS = ["fluid_0", "fluid_1", "fluid_2", "fluid_3", "fluid_4"];
const FILTER_KEYS = ["filter_0", "filter_1", "filter_2", "filter_3"];

// Общая логика для полей "марка" в форме внесения/редактирования замены —
// используется и в обычной форме "Внести замену", и в форме
// добавления/редактирования из истории (svcModal). Если для категории есть
// товары на складе — поле становится выпадающим списком с остатком и ценой,
// иначе (или если склад не включён точке) — обычное текстовое поле, как и
// раньше.
function productsForCategory(key) {
  return WAREHOUSE_ENABLED ? productsCache.filter(p => p.category === key) : [];
}

function brandFieldHtml(key, fieldId, onPickHandler) {
  const prods = productsForCategory(key);
  if (!prods.length) {
    return `<input id="${fieldId}" placeholder="${T.brand_ph}">`;
  }
  const options = ['<option value="">' + T.brand_ph + '</option>'].concat(
    prods.map(p => {
      const unitLabel = p.unit === 'pc' ? T.unit_pc : T.unit_l;
      const stockWarn = sellQty(p) < 0 || (STORE_ENABLED && !(sellQty(p) > 0)) ? ' ⚠️' : '';
      return `<option value="${p.id}" data-price="${p.sell_price || ''}" data-name="${escapeHtml(p.name)}">${escapeHtml(p.name)} (${whQty(sellQty(p))} ${unitLabel}${stockWarn}${mainTail(p, unitLabel)})</option>`;
    })
  ).join('');
  const sel = `<select id="${fieldId}" data-is-product="1" onchange="${onPickHandler}">${options}</select>`;
  // в основной форме на телефоне поверх списка лежит прозрачная кнопка —
  // она открывает удобную шторку выбора (поиск, остатки, прошлый товар сверху)
  if (fieldId.indexOf('svc_') === 0) return sel;
  return `<span class="pick-wrap">${sel}<button type="button" class="pick-ov" onclick="openPickSheet('${key}')" aria-label="${T.psh_choose}"></button></span>`;
}

function readBrandField(fieldId) {
  const el = document.getElementById(fieldId);
  if (!el) return { brand: null, product_id: null };
  if (el.tagName === 'SELECT') {
    if (!el.value) return { brand: null, product_id: null };
    const opt = el.options[el.selectedIndex];
    return { brand: opt.dataset.name || null, product_id: parseInt(el.value) };
  }
  return { brand: el.value.trim() || null, product_id: null };
}

function selectOrPreserveBrand(brandEl, it) {
  // Подставляет сохранённую позицию в поле "марка" при открытии редактирования.
  // Если это обычное текстовое поле — просто вписываем текст, как раньше.
  // Если это выпадающий список (склад включён и в категории есть товары) —
  // пытаемся выбрать ТОТ ЖЕ товар. Но если товар с тех пор удалили со склада
  // (его больше нет среди опций) — список НЕ должен молча показывать пустое
  // поле: тогда добавляем в список одноразовую "историческую" опцию с
  // сохранённым названием, чтобы при обычном пересохранении (без изменения
  // этого поля) марка не терялась.
  if (brandEl.tagName === 'INPUT') {
    brandEl.value = it.brand || '';
    return;
  }
  if (brandEl.tagName !== 'SELECT') return;
  if (it.product_id && [...brandEl.options].some(o => o.value === String(it.product_id))) {
    brandEl.value = String(it.product_id);
  } else if (it.brand) {
    const phantom = document.createElement('option');
    phantom.value = it.product_id || ('legacy_' + Math.random().toString(36).slice(2));
    phantom.textContent = it.brand + ' (' + T.wh_product_unavailable + ')';
    phantom.dataset.name = it.brand;
    if (!it.product_id) phantom.dataset.legacy = '1';
    brandEl.appendChild(phantom);
    brandEl.value = phantom.value;
  }
}

// ---- "Прочие товары" — динамический список строк (как в чеке), для товаров
// со склада, которые не подходят ни под одну из фиксированных категорий
// (жидкости/фильтры). prefix: 'other' — основная форма "Внести замену",
// 'svcOther' — форма редактирования/добавления из истории. ----
let otherStockRows = [];
let otherStockSeq = 0;
let svcOtherStockRows = [];
let svcOtherStockSeq = 0;

function renderOneOtherStockRow(prefix, id) {
  const prods = productsForCategory('other');
  const updateFn = prefix === 'other' ? 'updateTotal' : 'updateSvcTotal';
  const options = ['<option value="">' + T.brand_ph + '</option>'].concat(
    prods.map(p => {
      const unitLabel = p.unit === 'pc' ? T.unit_pc : T.unit_l;
      const stockWarn = sellQty(p) < 0 || (STORE_ENABLED && !(sellQty(p) > 0)) ? ' ⚠️' : '';
      return `<option value="${p.id}" data-price="${p.sell_price || ''}" data-name="${escapeHtml(p.name)}">${escapeHtml(p.name)} (${whQty(sellQty(p))} ${unitLabel}${stockWarn}${mainTail(p, unitLabel)})</option>`;
    })
  ).join('');
  return `
    <div class="other-stock-row" id="${prefix}_stockrow_${id}">
      <select id="${prefix}_stock_product_${id}" onchange="onOtherStockPicked('${prefix}', ${id})">${options}</select>
      <input id="${prefix}_stock_price_${id}" type="number" placeholder="${T.price_ph}" oninput="${updateFn}()">
      <input id="${prefix}_stock_qty_${id}" type="number" step="0.1" placeholder="${T.qty_ph}" oninput="${updateFn}()">
      <button type="button" onclick="removeOtherStockRow('${prefix}', ${id})">✕</button>
    </div>
  `;
}

function addOtherStockRow(prefix) {
  let id;
  if (prefix === 'other') { otherStockSeq++; id = otherStockSeq; otherStockRows.push(id); }
  else { svcOtherStockSeq++; id = svcOtherStockSeq; svcOtherStockRows.push(id); }
  const container = document.getElementById(prefix + 'StockRows');
  if (!container) return;
  // добавляем ТОЛЬКО новую строку в конец — не трогаем уже существующие,
  // чтобы не стереть то, что пользователь уже успел ввести в них
  container.insertAdjacentHTML('beforeend', renderOneOtherStockRow(prefix, id));
}

function removeOtherStockRow(prefix, id) {
  if (prefix === 'other') { otherStockRows = otherStockRows.filter(x => x !== id); }
  else { svcOtherStockRows = svcOtherStockRows.filter(x => x !== id); }
  // удаляем ТОЛЬКО конкретный элемент строки — соседние строки не трогаем
  const rowEl = document.getElementById(`${prefix}_stockrow_${id}`);
  if (rowEl) rowEl.remove();
  if (prefix === 'other') updateTotal(); else updateSvcTotal();
}

function renderOtherStockRows(prefix) {
  // Полная перерисовка С НУЛЯ — используется только при сбросе формы или
  // загрузке сохранённых позиций (когда в DOM ещё нет строк, которые можно
  // было бы случайно затереть). Для добавления/удаления ОДНОЙ строки к уже
  // заполненному списку используются addOtherStockRow/removeOtherStockRow —
  // они не перерисовывают соседние строки.
  const container = document.getElementById(prefix + 'StockRows');
  if (!container) return;
  const ids = prefix === 'other' ? otherStockRows : svcOtherStockRows;
  container.innerHTML = ids.map(id => renderOneOtherStockRow(prefix, id)).join('');
}

function onOtherStockPicked(prefix, id) {
  const el = document.getElementById(`${prefix}_stock_product_${id}`);
  const opt = el.options[el.selectedIndex];
  if (opt && opt.dataset.price) document.getElementById(`${prefix}_stock_price_${id}`).value = opt.dataset.price;
  if (prefix === 'other') updateTotal(); else updateSvcTotal();
}

function collectOtherStockItems(prefix) {
  const ids = prefix === 'other' ? otherStockRows : svcOtherStockRows;
  const items = [];
  ids.forEach(id => {
    const selectEl = document.getElementById(`${prefix}_stock_product_${id}`);
    const priceEl = document.getElementById(`${prefix}_stock_price_${id}`);
    const qtyEl = document.getElementById(`${prefix}_stock_qty_${id}`);
    if (!selectEl || !priceEl || !qtyEl) return;
    const price = parseFloat(priceEl.value) || 0;
    const qty = parseFloat(qtyEl.value) || 0;
    if (qty > 0 && selectEl.value) {
      const opt = selectEl.options[selectEl.selectedIndex];
      items.push({
        key: 'other_stock', name: opt.dataset.name || '', brand: null, product_id: parseInt(selectEl.value),
        unit_price: price, qty, total: Math.round(price * qty), _row: id,
      });
    }
  });
  return items;
}

function fillOtherStockRowsFrom(prefix, items) {
  // Восстанавливает СРАЗУ ВСЕ позиции "Прочее" при открытии редактирования.
  // Важно: сначала регистрируем id всех строк и рисуем их ОДНИМ вызовом
  // renderOtherStockRows — если рисовать по одной (вызывая render на каждую),
  // каждый следующий вызов полностью перерисовывает контейнер и стирает
  // выбор, уже сделанный в предыдущих строках.
  if (!items.length) return;
  const ids = items.map(() => {
    if (prefix === 'other') { otherStockSeq++; otherStockRows.push(otherStockSeq); return otherStockSeq; }
    svcOtherStockSeq++; svcOtherStockRows.push(svcOtherStockSeq); return svcOtherStockSeq;
  });
  renderOtherStockRows(prefix);
  items.forEach((it, i) => {
    const id = ids[i];
    const selectEl = document.getElementById(`${prefix}_stock_product_${id}`);
    if (selectEl) selectOrPreserveBrand(selectEl, { product_id: it.product_id, brand: it.name });
    document.getElementById(`${prefix}_stock_price_${id}`).value = it.unit_price ?? '';
    document.getElementById(`${prefix}_stock_qty_${id}`).value = it.qty ?? '';
  });
}

// ---- Быстрый поиск товара со склада при вводе замены ----
// Пишешь 2–3 кусочка названия в любом порядке ("mit 5w30 sp", "spark") —
// показываются подходящие товары; нажатие на товар ставит его в нужную
// строку формы (моторное масло, фильтр и т.д.) ровно так же, как выбор из
// выпадающего списка, и подставляет цену. Выпадающие списки остаются.
// ctx: 'main' — форма "Внести замену", 'svc' — окно добавления/редактирования.
const PICK_TR = {а:'a',б:'b',в:'v',г:'g',д:'d',е:'e',ё:'e',ж:'j',з:'z',и:'i',й:'i',к:'k',л:'l',м:'m',н:'n',о:'o',п:'p',р:'r',с:'s',т:'t',у:'u',ф:'f',х:'h',ц:'s',ч:'ch',ш:'sh',щ:'sh',ъ:'',ы:'i',ь:'',э:'e',ю:'yu',я:'ya',ў:'o',қ:'k',ғ:'g',ҳ:'h'};
const PICK = { main: [], svc: [] };

function pickNorm(s) {
  // регистр, дефисы, пробелы, точки не важны; кириллица = латиница; w = v
  return String(s || '').toLowerCase().split('').map(c => PICK_TR[c] ?? c).join('')
    .replace(/w/g, 'v').replace(/[^a-z0-9]/g, '');
}

function pickCatLabel(k) { return k === 'other' ? T.other : (T[k] || k); }

function pickEls(ctx) {
  return ctx === 'svc'
    ? { inp: document.getElementById('svcPickSearch'), box: document.getElementById('svcPickResults') }
    : { inp: document.getElementById('pickSearch'), box: document.getElementById('pickResults') };
}

function renderPickResults(ctx) {
  const { inp, box } = pickEls(ctx);
  if (!inp || !box) return;
  const words = inp.value.trim().split(' ').map(pickNorm).filter(Boolean);
  if (!words.length) { box.innerHTML = ''; PICK[ctx] = []; return; }
  const cats = FLUID_KEYS.concat(FILTER_KEYS, ['other']);
  const found = productsCache
    .filter(p => cats.includes(p.category))
    .map(p => {
      const n = pickNorm(p.name);
      const hay = n + '|' + pickNorm(pickCatLabel(p.category));
      if (!words.every(w => hay.includes(w))) return null;
      let score = 0;
      if (n.startsWith(words[0])) score -= 2;
      if (!(sellQty(p) > 0) && !(STORE_ENABLED && mainQtyOf(p) > 0)) score += 5;
      return { p, score };
    })
    .filter(Boolean)
    .sort((a, b) => a.score - b.score || String(a.p.name).localeCompare(String(b.p.name)))
    .slice(0, 8)
    .map(x => x.p);
  PICK[ctx] = found;
  if (!found.length) { box.innerHTML = `<div class="pick-note">${T.pick_nothing}</div>`; return; }
  box.innerHTML = found.map(p => {
    const unitLabel = p.unit === 'pc' ? T.unit_pc : T.unit_l;
    const stock = (sellQty(p) > 0
      ? `${whQty(sellQty(p))} ${unitLabel}`
      : `<span class="pi-out">${whQty(sellQty(p))} ${unitLabel} ⚠️</span>`) + mainTail(p, unitLabel);
    const price = p.sell_price ? fmtNum(p.sell_price) : '—';
    return `<div class="pick-item" role="button" tabindex="0" onclick="pickProduct('${ctx}', ${p.id})">
      <div class="pi-main"><div class="pi-name">${escapeHtml(p.name)}</div>
      <div class="pi-sub">${escapeHtml(pickCatLabel(p.category))} · ${stock}</div></div>
      <div class="pi-price">${price}</div></div>`;
  }).join('');
}

function onPickKey(e, ctx) {
  if (e.key !== 'Enter' || e.isComposing) return;
  e.preventDefault();
  e.stopPropagation();
  if (PICK[ctx] && PICK[ctx].length) pickProduct(ctx, PICK[ctx][0].id);
}

function pickProduct(ctx, id) {
  const p = productsCache.find(x => x.id === id);
  if (!p) return;
  const pre = ctx === 'svc' ? 'svc_' : '';
  const fi = FLUID_KEYS.indexOf(p.category);
  const ti = FILTER_KEYS.indexOf(p.category);
  let sel = null, focusEl = null;
  if (fi >= 0) {
    sel = document.getElementById(`${pre}fluid_brand_${fi}`);
    focusEl = document.getElementById(`${pre}fluid_liters_${fi}`);
  } else if (ti >= 0) {
    sel = document.getElementById(`${pre}filter_brand_${ti}`);
    focusEl = document.getElementById(`${pre}filter_price_${ti}`);
  } else {
    const prefix = ctx === 'svc' ? 'svcOther' : 'other';
    const rows = () => (prefix === 'other' ? otherStockRows : svcOtherStockRows);
    let rid = rows().find(r => {
      const s = document.getElementById(`${prefix}_stock_product_${r}`);
      return s && !s.value;
    });
    if (rid === undefined) { addOtherStockRow(prefix); rid = rows()[rows().length - 1]; }
    sel = document.getElementById(`${prefix}_stock_product_${rid}`);
    focusEl = document.getElementById(`${prefix}_stock_qty_${rid}`);
  }
  if (!sel || sel.tagName !== 'SELECT') return;
  sel.value = String(p.id);
  if (sel.value !== String(p.id)) return;
  sel.dispatchEvent(new Event('change'));

  const { inp, box } = pickEls(ctx);
  if (inp) inp.value = '';
  PICK[ctx] = [];
  if (box) {
    box.innerHTML = `<div class="pick-note ok">✓ ${escapeHtml(p.name)} → ${escapeHtml(pickCatLabel(p.category))}</div>`;
    setTimeout(() => { if (inp && !inp.value) box.innerHTML = ''; }, 3500);
  }
  const row = sel.closest('.item-row, .other-stock-row');
  if (row) {
    row.classList.remove('pick-flash');
    void row.offsetWidth;
    row.classList.add('pick-flash');
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  if (focusEl && !focusEl.value) setTimeout(() => focusEl.focus({ preventScroll: true }), 300);
}

function clearPick(ctx) {
  const { inp, box } = pickEls(ctx);
  if (inp) inp.value = '';
  if (box) box.innerHTML = '';
  PICK[ctx] = [];
}

// Списки позиций перерисовываются, когда приходит/меняется каталог склада
// (на слабом интернете — уже после того, как мастер начал вводить; при
// открытии «Склада»). Раньше это стирало выбранные марки, литры и цены, а
// «Итого» и сумма оплаты оставались старыми. Теперь введённое сохраняется.
function snapItemFields(listIds) {
  const snap = {};
  listIds.forEach(lid => {
    const box = document.getElementById(lid);
    if (!box) return;
    box.querySelectorAll('input[id], select[id]').forEach(el => {
      if (String(el.value || '').trim() === '') return;
      const isSel = el.tagName === 'SELECT';
      const opt = isSel ? el.options[el.selectedIndex] : null;
      snap[el.id] = { v: el.value, sel: isSel, name: opt ? (opt.dataset.name || '') : el.value };
    });
  });
  return snap;
}
function restoreItemFields(snap) {
  let n = 0;
  Object.keys(snap).forEach(id => {
    const el = document.getElementById(id);
    const s = snap[id];
    if (!el) return;
    if (el.tagName === 'SELECT') {
      const opts = Array.from(el.options);
      let o = s.sel ? opts.find(x => x.value === s.v) : null;
      if (!o && s.name) {
        const want = s.name.trim().toUpperCase();
        o = opts.find(x => x.value && (x.dataset.name || '').trim().toUpperCase() === want);
      }
      if (o) { el.value = o.value; n++; }
    } else {
      el.value = (s.sel && id.indexOf('_brand_') >= 0) ? s.name : s.v;
      n++;
    }
  });
  return n;
}

function renderItemLists() {
  const snap = snapItemFields(['fluidsList', 'filtersList']);
  document.getElementById('fluidsList').innerHTML = FLUID_KEYS.map((key, i) => `
    <div class="item-row" id="row_${key}">
      <span class="item-name">${T[key]}</span>
      ${brandFieldHtml(key, `fluid_brand_${i}`, `onFluidProductPicked(${i})`)}
      <input id="fluid_price_${i}" type="number" placeholder="${T.price_per_liter_ph}" oninput="updateTotal()">
      <span class="lit-step"><button type="button" onclick="stepLiters(${i}, -0.5)" aria-label="−0,5">−</button><input id="fluid_liters_${i}" type="number" inputmode="decimal" step="0.1" placeholder="${T.liters_ph}" oninput="updateTotal()"><button type="button" onclick="stepLiters(${i}, 0.5)" aria-label="+0,5">+</button></span>
      <button type="button" class="row-x" onclick="closeItemRow('${key}')" aria-label="${T.af_remove}">✕</button>
    </div>
  `).join('');
  document.getElementById('filtersList').innerHTML = FILTER_KEYS.map((key, i) => {
    const prods = productsForCategory(key);
    // поле марки есть всегда: без склада марку вписывают вручную в окне категории
    const brandField = brandFieldHtml(key, `filter_brand_${i}`, `onFilterProductPicked(${i})`);
    return `
    <div class="item-row" id="row_${key}">
      <span class="item-name" style="flex:${prods.length ? '1.3' : '2.3'};">${T[key]}</span>
      ${brandField}
      <input id="filter_price_${i}" type="number" placeholder="${T.price_ph}" oninput="updateTotal()">
      ${filterQtyHtml('', i)}
      <button type="button" class="row-x" onclick="closeItemRow('${key}')" aria-label="${T.af_remove}">✕</button>
    </div>
  `;
  }).join('');
  if (restoreItemFields(snap)) updateTotal();
  syncItemRows();
}

// Показываем только нужные строки товаров: по умолчанию моторное масло и
// масляный фильтр, остальные — кнопками «+ АКПП», «+ Антифриз»… Строка с
// заполненным значением видна всегда (после «Повторить прошлую», выбора из
// поиска по складу и т.п.). ✕ очищает строку и прячет её.
const ROW_DEFAULT = ['fluid_0'];
let ROW_OPEN = new Set(ROW_DEFAULT);
function rowFieldIds(key) {
  const fi = FLUID_KEYS.indexOf(key), ti = FILTER_KEYS.indexOf(key);
  if (fi >= 0) return [`fluid_brand_${fi}`, `fluid_price_${fi}`, `fluid_liters_${fi}`];
  if (ti >= 0) return [`filter_brand_${ti}`, `filter_price_${ti}`];
  return [];
}
function rowHasValue(key) {
  return rowFieldIds(key).some(id => { const el = document.getElementById(id); return el && String(el.value || '').trim() !== ''; });
}
function syncItemRows() {
  const hidden = [];
  FLUID_KEYS.concat(FILTER_KEYS).forEach(key => {
    const row = document.getElementById('row_' + key);
    if (!row) return;
    if (rowHasValue(key)) ROW_OPEN.add(key);
    const vis = ROW_OPEN.has(key);
    row.style.display = vis ? '' : 'none';
    if (!vis) hidden.push(key);
  });
  const box = document.getElementById('itemAddChips');
  // фильтры — плитками (renderFilterTiles), здесь только остальные жидкости
  if (box) box.innerHTML = hidden.filter(k => FILTER_KEYS.indexOf(k) < 0).map(k => `<button type="button" onclick="openItemRow('${k}')"><i class="fa-solid fa-plus"></i>${T[k]}</button>`).join('');
  renderFilterTiles();
  if (typeof renderCatTiles === 'function') renderCatTiles();
}

// ---- Фильтры плитками: нажал — фильтр в чеке, ещё раз — убран ----
function renderFilterTiles() {
  const box = document.getElementById('filterTiles');
  if (!box) return;
  box.innerHTML = FILTER_KEYS.map((key, i) => {
    const on = rowHasValue(key);
    const prods = productsForCategory(key);
    let sub = '';
    if (on) {
      const { brand } = readBrandField(`filter_brand_${i}`);
      const pr = parseFloat((document.getElementById(`filter_price_${i}`) || {}).value) || 0;
      const q = filterQty(i, '');
      sub = [brand, q > 1 ? '× ' + q : '', pr ? pr.toLocaleString('ru-RU') : ''].filter(Boolean).join(' · ');
    } else if (prods.length === 1 && prods[0].sell_price) {
      sub = Number(prods[0].sell_price).toLocaleString('ru-RU');
    } else if (prods.length > 1) {
      sub = prods.length + ' ' + T.psh_variants;
    }
    return `<button type="button" class="flt-tile${on ? ' on' : ''}" aria-pressed="${on}" onclick="toggleFilterTile('${key}')"><b>${T[key]}</b>${sub ? `<span>${escapeHtml(sub)}</span>` : ''}</button>`;
  }).join('');
}
function toggleFilterTile(key) {
  const ti = FILTER_KEYS.indexOf(key);
  if (ti < 0) return;
  if (rowHasValue(key)) { closeItemRow(key); return; }
  const prods = productsForCategory(key);
  const sel = document.getElementById(`filter_brand_${ti}`);
  if (sel && sel.tagName === 'SELECT') {
    if (prods.length === 1) { setProductInField(key, prods[0].id); return; }
    openPickSheet(key);
    return;
  }
  openItemRow(key);
}

// сколько штук фильтра (например, 2 топливных на машине с двумя баками);
// пустое поле = 1 шт. pre: '' — форма «Внести замену», 'svc_' — окно правки
function filterQtyHtml(pre, i) {
  return `<span class="lit-step"><button type="button" onclick="stepFilterQty(${i}, -1, '${pre}')" aria-label="−">−</button><input id="${pre}filter_qty_${i}" type="number" inputmode="numeric" min="1" step="1" placeholder="1 ${T.unit_pc}" aria-label="${T.qty_ph}" oninput="${pre ? 'updateSvcTotal' : 'updateTotal'}()"><button type="button" onclick="stepFilterQty(${i}, 1, '${pre}')" aria-label="+">+</button></span>`;
}
function filterQty(i, pre) {
  const el = document.getElementById(`${pre || ''}filter_qty_${i}`);
  const n = Math.round(parseFloat(el && el.value) || 1);
  return Math.min(Math.max(n, 1), 99);
}
function stepFilterQty(i, d, pre) {
  const el = document.getElementById(`${pre || ''}filter_qty_${i}`);
  if (!el) return;
  const v = Math.min(Math.max(filterQty(i, pre) + d, 1), 99);
  el.value = v > 1 ? String(v) : '';
  if (pre) updateSvcTotal(); else updateTotal();
}

// литры кнопками −/+ по 0,5 л
function stepLiters(i, d) {
  const el = document.getElementById(`fluid_liters_${i}`);
  if (!el) return;
  const cur = parseFloat(String(el.value).replace(',', '.')) || 0;
  const v = Math.max(0, Math.round((cur + d) * 10) / 10);
  el.value = v ? String(v) : '';
  updateTotal();
}

// «Работа / услуга» отдельной кнопкой: подставляет название и ставит курсор в цену
function addLabor() {
  if (document.getElementById('catSheet')) { closeObSheets(); openCatSheet('wk'); return; }
  const n = document.getElementById('other_name'), pr = document.getElementById('other_price');
  if (!n || !pr) return;
  if (!n.value.trim()) n.value = T.labor_name;
  pr.scrollIntoView({ block: 'center', behavior: 'smooth' });
  setTimeout(() => pr.focus(), 250);
}

// долг: «вернёт через 1 нед / 2 нед / 1 мес» — одним платежом весь остаток
function setDebtTerm(days) {
  const total = payTotal();
  const cash = parseFloat(document.getElementById('pay_cash').value) || 0;
  const card = parseFloat(document.getElementById('pay_card').value) || 0;
  const rest = Math.max(0, Math.round(total - cash - card));
  document.getElementById('debt_interval_days').value = days;
  if (rest > 0) document.getElementById('debt_installment_amount').value = rest;
  document.querySelectorAll('#debtTerms button').forEach(b => b.classList.toggle('on', b.dataset.d === String(days)));
}
function openItemRow(key) {
  ROW_OPEN.add(key);
  syncItemRows();
  const first = rowFieldIds(key).map(id => document.getElementById(id)).find(Boolean);
  if (first) setTimeout(() => first.focus(), 50);
}
function closeItemRow(key) {
  rowFieldIds(key).forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const qEl = document.getElementById(`filter_qty_${FILTER_KEYS.indexOf(key)}`);
  if (qEl) qEl.value = '';
  ROW_OPEN.delete(key);
  updateTotal();
}

// ===== «Товары и работа»: плитки категорий → окно категории → чек =====
// Данные позиций по-прежнему лежат в скрытых полях формы (fluid_*, filter_*,
// other_*, строки «прочих товаров») — collectItems() и сохранение не
// меняются. Плитки и окно только удобно заполняют эти поля.
let FREQ = {};
async function loadFrequentItems() {
  try { const r = await fetch('/api/frequent_items'); if (r.ok) FREQ = await r.json() || {}; } catch (e) {}
}
const CATS = [
  { id: 'oil', keys: ['fluid_0'], ic: 'fa-oil-can', cls: '' },
  { id: 'f0', keys: ['filter_0'], ic: 'fa-filter', cls: '' },
  { id: 'f1', keys: ['filter_1'], ic: 'fa-wind', cls: 'g' },
  { id: 'f2', keys: ['filter_2'], ic: 'fa-fan', cls: 'g' },
  { id: 'f3', keys: ['filter_3'], ic: 'fa-gas-pump', cls: 'g' },
  { id: 'fl', keys: ['fluid_1', 'fluid_2', 'fluid_3', 'fluid_4'], ic: 'fa-flask', cls: 'v' },
  { id: 'os', keys: ['other_stock'], ic: 'fa-box-open', cls: 'v' },
  { id: 'wk', keys: ['other'], ic: 'fa-screwdriver-wrench', cls: 'y' },
];
const CS = { cat: '', key: '', pid: '', qty: 0, manual: null };
function catTitle(c) {
  if (c.id === 'fl') return T.cat_fluids;
  if (c.id === 'os') return T.cat_goods;
  if (c.id === 'wk') return T.cat_work;
  return T[c.keys[0]] || '';
}
function catVisible(c) {
  return c.id !== 'os' || (WAREHOUSE_ENABLED && productsForCategory('other').length > 0);
}
function catOfKey(key) { return CATS.find(c => c.keys.indexOf(key) >= 0); }
function isFluidKey(k) { return FLUID_KEYS.indexOf(k) >= 0; }
const csMoney = v => (Math.round(Number(v) || 0)).toLocaleString('ru-RU');
const csQty = v => String(Math.round((Number(v) || 0) * 100) / 100).replace('.', ',');

function renderCatTiles() {
  const box = document.getElementById('catTiles');
  if (!box) return;
  const items = collectItems();
  box.innerHTML = CATS.filter(catVisible).map(c => {
    const mine = items.filter(it => c.keys.indexOf(it.key) >= 0);
    let sub;
    if (mine.length) {
      sub = mine.map(it => (it.key === 'other' ? String(it.name || '').replace(T.other_prefix + ': ', '') : (it.brand || it.name))
        + (isFluidKey(it.key) && it.qty ? ' · ' + csQty(it.qty) + ' ' + T.unit_l : '')
        + (FILTER_KEYS.indexOf(it.key) >= 0 && it.qty > 1 ? ' × ' + it.qty : '')).join(', ');
    } else if (c.id === 'wk') {
      sub = T.cat_work_sub;
    } else {
      const n = c.keys.reduce((a, k) => a + productsForCategory(k === 'other_stock' ? 'other' : k).length, 0);
      sub = n ? n + ' ' + T.cat_in_stock : (c.id === 'fl' ? T.cat_fluids_sub : T.cat_manual);
    }
    return `<button type="button" class="cat-tile${mine.length ? ' on' : ''}" onclick="openCatSheet('${c.id}')"><span class="ci ${c.cls}"><i class="fa-solid ${c.ic}"></i></span><div><b>${escapeHtml(catTitle(c))}</b><small>${escapeHtml(sub)}</small></div></button>`;
  }).join('');
}

function renderItRcpt(items, subtotal) {
  const box = document.getElementById('itRcpt');
  if (!box) return;
  items = items || collectItems();
  subtotal = subtotal == null ? itemsSubtotal(items) : subtotal;
  const plate = (document.getElementById('plate').value || '').trim().toUpperCase();
  const head = `<div class="ir-h"><span>${T.rcpt_title}</span><b>${escapeHtml(plate)}</b></div>`;
  if (!items.length) { box.innerHTML = head + `<div class="ir-empty">${T.cat_rcpt_empty}</div>`; return; }
  const lines = items.map((it, i) => {
    const c = catOfKey(it.key);
    const title = it.key === 'other' ? String(it.name || '').replace(T.other_prefix + ': ', '') : (it.brand || it.name);
    const catName = it.key === 'other_stock' ? T.cat_goods : (it.key === 'other' ? T.cat_work : (T[it.key] || ''));
    const fluid = isFluidKey(it.key);
    const qtyTxt = (it.qty && it.qty !== 1) || fluid ? csQty(it.qty) + (fluid ? ' ' + T.unit_l : '') + ' × ' + csMoney(it.unit_price) : '';
    const step = fluid || it.key === 'other_stock' || FILTER_KEYS.indexOf(it.key) >= 0
      ? `<span class="ir-step"><button type="button" onclick="irStep(${i}, -1)" aria-label="−">−</button><button type="button" onclick="irStep(${i}, 1)" aria-label="+">+</button></span>` : '';
    return `<div class="ir-line"><div class="ir-main" onclick="openCatSheet('${c ? c.id : ''}', '${it.key}')"><b>${escapeHtml(title || '')}</b><span>${escapeHtml(catName)}${qtyTxt ? ' · ' + qtyTxt : ''}</span></div>${step}<button type="button" class="ir-sum rc-sum" onclick="rcTotal(${i})" title="${T.rc_total_hint}">${csMoney(it.total)}${rcExtraHtml(it)}</button><button type="button" class="ir-x" onclick="rcRemove(${i})" aria-label="${T.af_remove}">✕</button></div>`;
  }).join('');
  const d = discountFor(subtotal);
  const disc = d ? `<div class="ir-line ir-disc"><div class="ir-main"><b>${T.disc_title}</b></div><span class="ir-sum">−${csMoney(d)}</span></div>` : '';
  box.innerHTML = head + lines + disc + `<div class="ir-tot"><span>${T.field_total}</span><b>${csMoney(subtotal - d)} ${T.currency}</b></div>`;
}

// литры масла: по 0,5 л; прочие товары: по 1 шт (или 0,5 л)
function irStep(i, dir) {
  const it = collectItems()[i];
  if (!it) return;
  if (isFluidKey(it.key)) { stepLiters(FLUID_KEYS.indexOf(it.key), dir * 0.5); return; }
  const ti = FILTER_KEYS.indexOf(it.key);
  if (ti >= 0) {
    // «−» у одного фильтра убирает его из чека, как у прочих товаров
    if (dir < 0 && filterQty(ti, '') <= 1) { closeItemRow(it.key); return; }
    stepFilterQty(ti, dir, '');
    return;
  }
  if (it.key === 'other_stock' && it._row) {
    const el = document.getElementById(`other_stock_qty_${it._row}`);
    if (!el) return;
    const p = productsCache.find(x => x.id === it.product_id);
    const step = p && p.unit !== 'pc' ? 0.5 : 1;
    const v = Math.round(((parseFloat(el.value) || 0) + dir * step) * 10) / 10;
    if (v <= 0) { removeOtherStockRow('other', it._row); return; }
    el.value = v;
    updateTotal();
  }
}

function openCatSheet(catId, key) {
  const c = CATS.find(x => x.id === catId);
  if (!c) return;
  CS.cat = c.id;
  if (!key || c.keys.indexOf(key) < 0) {
    // жидкости: открываем первую выбранную, иначе АКПП
    key = c.keys.find(k => isFluidKey(k) && rowHasValue(k)) || c.keys[0];
  }
  CS.key = key;
  csResetPick();
  const s = document.getElementById('cs_search');
  s.value = '';
  s.placeholder = '🔍 ' + T.cat_search_ph + ' ' + String(catTitle(c)).toLowerCase() + '…';
  document.getElementById('cs_title').textContent = catTitle(c);
  renderCatSheet();
  openObSheet('catSheet');
}
function csResetPick() {
  const key = CS.key;
  CS.pid = ''; CS.qty = 0; CS.manual = null;
  if (FLUID_KEYS.indexOf(key) >= 0 || FILTER_KEYS.indexOf(key) >= 0) {
    const sel = document.getElementById(brandFieldIdFor(key));
    if (sel && sel.tagName === 'SELECT') CS.pid = sel.value || '';
    if (isFluidKey(key)) {
      CS.qty = parseFloat((document.getElementById(`fluid_liters_${FLUID_KEYS.indexOf(key)}`) || {}).value) || 0;
      if (!CS.qty) {
        const prev = (LAST_VISIT_ITEMS || []).find(it => it.key === key && it.qty);
        const fr = (FREQ[key] || []).find(f => f.qty);
        CS.qty = Number(prev ? prev.qty : (fr ? fr.qty : (key === 'fluid_0' ? 4 : 1))) || 0;
      }
    }
  }
  if (key === 'other_stock') CS.qty = 1;
}
function csSetKey(k) { CS.key = k; csResetPick(); renderCatSheet(); }

function csHasProducts(key) {
  const sel = document.getElementById(brandFieldIdFor(key));
  return !!(sel && sel.tagName === 'SELECT');
}
function csFreqFor(key) {
  return (FREQ[key] || []).slice(0, 6);
}

function renderCatSheet() {
  const c = CATS.find(x => x.id === CS.cat);
  if (!c) return;
  const key = CS.key;
  csPlaceExtras(key);
  const tabs = document.getElementById('cs_tabs');
  tabs.innerHTML = c.keys.length > 1 ? c.keys.map(k => `<button type="button" class="${k === key ? 'on' : ''}${rowHasValue(k) ? ' has' : ''}" onclick="csSetKey('${k}')">${escapeHtml(T[k])}</button>`).join('') : '';
  const searchEl = document.getElementById('cs_search');
  const body = document.getElementById('cs_body');
  const foot = document.getElementById('cs_foot');
  if (key === 'other') { searchEl.style.display = 'none'; renderCsWork(body, foot); return; }
  if (key === 'other_stock') { searchEl.style.display = ''; renderCsGoods(body, foot); return; }
  if (!csHasProducts(key)) { searchEl.style.display = 'none'; renderCsManual(body, foot); return; }
  searchEl.style.display = '';
  const words = (searchEl.value || '').trim().split(' ').map(pickNorm).filter(Boolean);
  const all = productsForCategory(key);
  const prods = all.filter(p => !words.length || words.every(w => pickNorm(p.name).includes(w)));
  const availOf = p => (sellQty(p) || 0) + (STORE_ENABLED ? (mainQtyOf(p) || 0) : 0);
  const unitOf = p => p.unit === 'pc' ? T.unit_pc : T.unit_l;
  const fluid = isFluidKey(key);
  const row = p => {
    const q = availOf(p);
    const cls = !(q > 0) ? 'none' : (q <= (fluid ? 8 : 3) ? 'low' : '');
    const stock = !(q > 0) ? T.psh_out : `${T.psh_instock} ${whQty(q)} ${unitOf(p)}${cls === 'low' ? ' · ' + T.psh_low : ''}`;
    return `<button type="button" class="ps-item${String(p.id) === String(CS.pid) ? ' on' : ''}${!(q > 0) ? ' out' : ''}" onclick="csPick(${p.id})">
      <div><b>${escapeHtml(p.name)}</b><small class="${cls}">${stock}</small></div><em>${p.sell_price ? csMoney(p.sell_price) + (fluid ? '/' + T.unit_l : '') : '—'}</em></button>`;
  };
  let html = '';
  if (!words.length) {
    const byId = id => all.find(p => String(p.id) === String(id));
    const freq = csFreqFor(key).filter(f => f.product_id && byId(f.product_id));
    if (freq.length) {
      html += `<div class="ps-grp" style="margin-top:0;">${T.cat_freq}</div><div class="cs-freq">` + freq.map(f => {
        const p = byId(f.product_id);
        return `<button type="button" class="${String(p.id) === String(CS.pid) ? 'on' : ''}" onclick="csPick(${p.id}${fluid && f.qty ? ', ' + Number(f.qty) : ''})">${escapeHtml(p.name)}${fluid && f.qty ? ' · ' + csQty(f.qty) + ' ' + T.unit_l : ''}<em>${p.sell_price ? csMoney(p.sell_price) : ''}</em></button>`;
      }).join('') + `</div>`;
    }
    const prevIds = new Set((LAST_VISIT_ITEMS || []).filter(it => it.key === key && it.product_id).map(it => String(it.product_id)));
    const prev = all.filter(p => prevIds.has(String(p.id)));
    if (prev.length) html += `<div class="ps-grp">${T.psh_last}</div>` + prev.map(row).join('');
  }
  const rest = prods.slice().sort((a, b) => ((availOf(b) > 0) - (availOf(a) > 0)) || String(a.name).localeCompare(String(b.name)));
  html += `<div class="ps-grp">${T.cat_all_stock}</div>` + (rest.length ? rest.map(row).join('') : `<div class="pick-note">${T.pick_nothing}</div>`);
  body.innerHTML = html;
  foot.innerHTML = csFootHtml(fluid, !!CS.pid, rowHasValue(key));
}
function csFootHtml(fluid, ready, inRcpt) {
  let h = '';
  if (fluid) {
    const opts = [1, 3, 3.5, 4, 4.5, 5];
    h += `<div class="ps-grp" style="margin-top:0;">${T.psh_liters}</div><div class="ps-lit">` +
      opts.map(v => `<button type="button" class="${CS.qty === v ? 'on' : ''}" onclick="CS.qty=${v}; renderCatSheet()">${csQty(v)}</button>`).join('') + `</div>` +
      `<div class="cs-qty"><button type="button" onclick="CS.qty=Math.max(0.5, Math.round((CS.qty-0.5)*10)/10); renderCatSheet()">−</button><label><input id="csQtyIn" type="text" inputmode="decimal" autocomplete="off" value="${csQty(CS.qty)}" onfocus="this.select()" oninput="csQtyType(this)" onchange="csQtyDone(this)" onkeydown="if(event.key==='Enter'){this.blur();}"><span>${T.unit_l}</span></label><button type="button" onclick="CS.qty=Math.round((CS.qty+0.5)*10)/10; renderCatSheet()">+</button></div>`;
  }
  const ti = FILTER_KEYS.indexOf(CS.key);
  if (ti >= 0 && inRcpt) {
    // фильтр уже в чеке — сколько штук (2 топливных на машине с двумя баками)
    h += `<div class="ps-grp" style="margin-top:0;">${T.qty_ph}</div>` +
      `<div class="cs-qty"><button type="button" onclick="csFltStep(-1)" aria-label="−">−</button><b>${filterQty(ti, '')} ${T.unit_pc}</b><button type="button" onclick="csFltStep(1)" aria-label="+">+</button></div>`;
  }
  if (ready) h += `<button type="button" class="ps-go" id="csGoBtn" onclick="csApply()">${csGoText(fluid)}</button>`;
  if (inRcpt) h += `<button type="button" class="cs-del" onclick="csRemoveCur()">${T.cat_remove}</button>`;
  return h;
}
function csFltStep(d) {
  const ti = FILTER_KEYS.indexOf(CS.key);
  if (ti < 0) return;
  stepFilterQty(ti, d, '');
  renderCatSheet();
}
// тот же фильтр нажали ещё раз — ещё одна штука (а не замена на тот же товар)
function addSameFilter(key, id) {
  const ti = FILTER_KEYS.indexOf(key);
  if (ti < 0 || !rowHasValue(key)) return false;
  const sel = document.getElementById(`filter_brand_${ti}`);
  if (!sel || sel.tagName !== 'SELECT' || sel.value !== String(id)) return false;
  stepFilterQty(ti, 1, '');
  const p = productsCache.find(x => String(x.id) === String(id));
  showMsg(`${p ? p.name : T[key]} × ${filterQty(ti, '')}`, true);
  return true;
}
function csGoText(fluid) {
  return T.cat_add + (fluid && CS.qty ? ' · ' + csQty(CS.qty) + ' ' + T.unit_l : '');
}
// свой литраж вручную (например 3,8): пока печатают — только обновляем кнопку, без перерисовки
function csParseQty(v) {
  const n = parseFloat(String(v || '').replace(',', '.'));
  return n > 0 ? Math.min(Math.round(n * 100) / 100, 999) : 0;
}
function csQtyType(el) {
  el.value = el.value.replace(el.dataset.int ? /[^0-9]/g : /[^0-9.,]/g, '');
  const n = csParseQty(el.value);
  if (n) CS.qty = n;
  csQtyMark(el);
}
// подсветка готовых кнопок и текст «Добавить» — без перерисовки шторки,
// чтобы нажатие «Добавить» сразу после ввода не потерялось
function csQtyMark(el) {
  const box = el.closest('.cs-qty');
  const lit = box && box.previousElementSibling;
  if (lit && lit.classList.contains('ps-lit')) {
    lit.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.textContent.trim() === csQty(CS.qty)));
  }
  const b = document.getElementById('csGoBtn');
  if (b) b.textContent = csGoText(true);
}
function csQtyDone(el) {
  const n = csParseQty(el.value);
  if (n) CS.qty = n;
  el.value = csQty(CS.qty);
  csQtyMark(el);
}
function csPick(id, qty) {
  CS.pid = String(id);
  if (qty) CS.qty = qty;
  // фильтр — одним нажатием сразу в чек (повторное нажатие — ещё 1 шт);
  // масло — ждём литры и «Добавить»
  if (!isFluidKey(CS.key)) {
    if (addSameFilter(CS.key, id)) { closeObSheets(); return; }
    csApply();
    return;
  }
  renderCatSheet();
}
function csApply() {
  const key = CS.key;
  if (!CS.pid) return;
  setProductInField(key, CS.pid, isFluidKey(key) ? CS.qty : 0);
  ROW_OPEN.add(key);
  updateTotal();
  closeObSheets();
}
function csRemoveCur() {
  const key = CS.key;
  if (key === 'other') {
    document.getElementById('other_name').value = '';
    document.getElementById('other_price').value = '';
    updateTotal();
  } else {
    closeItemRow(key);
  }
  closeObSheets();
}

// категория без товаров на складе — ввод вручную: марка, цена, литры
function renderCsManual(body, foot) {
  const key = CS.key, fluid = isFluidKey(key);
  const fi = FLUID_KEYS.indexOf(key), ti = FILTER_KEYS.indexOf(key);
  const brandId = fi >= 0 ? `fluid_brand_${fi}` : `filter_brand_${ti}`;
  const priceId = fi >= 0 ? `fluid_price_${fi}` : `filter_price_${ti}`;
  if (!CS.manual) {
    const be = document.getElementById(brandId), pe = document.getElementById(priceId);
    CS.manual = { brand: be ? be.value : '', price: pe ? pe.value : '' };
  }
  const freq = csFreqFor(key).filter(f => f.label);
  let html = '';
  if (freq.length) {
    html += `<div class="ps-grp" style="margin-top:0;">${T.cat_freq}</div><div class="cs-freq">` + freq.map((f, i) =>
      `<button type="button" class="${(CS.manual.brand || '').trim().toUpperCase() === f.label.trim().toUpperCase() ? 'on' : ''}" onclick="csManFreq(${i})">${escapeHtml(f.label)}${fluid && f.qty ? ' · ' + csQty(f.qty) + ' ' + T.unit_l : ''}${f.price ? `<em>${csMoney(f.price)}</em>` : ''}</button>`).join('') + `</div>`;
  }
  html += `<div class="ps-grp">${T.cat_manual_title}</div><div class="cs-man">
    <input id="cs_m_brand" placeholder="${T.brand_ph}" value="${escapeHtml(CS.manual.brand || '')}" oninput="CS.manual.brand=this.value">
    <input id="cs_m_price" type="number" inputmode="numeric" placeholder="${fluid ? T.price_per_liter_ph : T.price_ph}" value="${escapeHtml(String(CS.manual.price || ''))}" oninput="CS.manual.price=this.value">
  </div>`;
  body.innerHTML = html;
  foot.innerHTML = csFootHtml(fluid, false, rowHasValue(key)).replace(/^/, '') + `<button type="button" class="ps-go" style="margin-top:4px;" onclick="csManApply()">${T.cat_add}</button>`;
}
function csManFreq(i) {
  const f = csFreqFor(CS.key).filter(x => x.label)[i];
  if (!f) return;
  CS.manual = { brand: f.label, price: f.price || '' };
  if (isFluidKey(CS.key) && f.qty) CS.qty = Number(f.qty);
  renderCatSheet();
}
function csManApply() {
  const key = CS.key, fi = FLUID_KEYS.indexOf(key), ti = FILTER_KEYS.indexOf(key);
  const price = parseFloat(CS.manual && CS.manual.price) || 0;
  const brand = (CS.manual && CS.manual.brand || '').trim();
  if (!brand && !price) { closeObSheets(); return; }
  if (fi >= 0) {
    document.getElementById(`fluid_brand_${fi}`).value = brand;
    document.getElementById(`fluid_price_${fi}`).value = price || '';
    document.getElementById(`fluid_liters_${fi}`).value = CS.qty || 1;
  } else {
    const be = document.getElementById(`filter_brand_${ti}`);
    if (be) be.value = brand;
    document.getElementById(`filter_price_${ti}`).value = price || '';
  }
  ROW_OPEN.add(key);
  paymentSplitTouched = false;
  updateTotal();
  closeObSheets();
}

// работа / услуга: частые услуги этой точки + своя
function renderCsWork(body, foot) {
  if (!CS.manual) {
    const n = (document.getElementById('other_name').value || '').trim();
    CS.manual = { brand: n, price: document.getElementById('other_price').value || '' };
  }
  const freq = csFreqFor('other').map(f => ({ ...f, label: String(f.label || '').replace(T.other_prefix + ': ', '') }))
    .filter(f => f.label && f.label !== T.other_unnamed);
  const presets = [T.labor_name, T.cat_work_wash, T.cat_work_flush].filter(x => x && !freq.some(f => f.label.toUpperCase() === x.toUpperCase()));
  let html = `<div class="ps-grp" style="margin-top:0;">${freq.length ? T.cat_freq : T.cat_work_quick}</div><div class="cs-freq">`
    + freq.map((f, i) => `<button type="button" class="${CS.manual.brand === f.label ? 'on' : ''}" onclick="csWorkFreq(${i})">${escapeHtml(f.label)}${f.price ? `<em>${csMoney(f.price)}</em>` : ''}</button>`).join('')
    + presets.map(x => `<button type="button" class="${CS.manual.brand === x ? 'on' : ''}" onclick="CS.manual.brand=${escapeHtml(JSON.stringify(x))}; renderCatSheet(); setTimeout(() => { const e = document.getElementById('cs_m_price'); if (e) e.focus(); }, 50)">${escapeHtml(x)}</button>`).join('')
    + `</div>`;
  html += `<div class="ps-grp">${T.cat_work_own}</div><div class="cs-man">
    <input id="cs_m_brand" placeholder="${T.field_other_name_ph}" value="${escapeHtml(CS.manual.brand || '')}" oninput="CS.manual.brand=this.value">
    <input id="cs_m_price" type="number" inputmode="numeric" placeholder="${T.field_price}" value="${escapeHtml(String(CS.manual.price || ''))}" oninput="CS.manual.price=this.value">
  </div>`;
  body.innerHTML = html;
  const has = (parseFloat(document.getElementById('other_price').value) || 0) > 0;
  foot.innerHTML = `<button type="button" class="ps-go" onclick="csWorkApply()">${T.cat_add}</button>` + (has ? `<button type="button" class="cs-del" onclick="csRemoveCur()">${T.cat_remove}</button>` : '');
}
function csWorkFreq(i) {
  const freq = csFreqFor('other').map(f => ({ ...f, label: String(f.label || '').replace(T.other_prefix + ': ', '') }))
    .filter(f => f.label && f.label !== T.other_unnamed);
  const f = freq[i];
  if (!f) return;
  CS.manual = { brand: f.label, price: f.price || '' };
  renderCatSheet();
}
function csWorkApply() {
  const price = parseFloat(CS.manual && CS.manual.price) || 0;
  document.getElementById('other_name').value = (CS.manual && CS.manual.brand || '').trim();
  document.getElementById('other_price').value = price || '';
  paymentSplitTouched = false;
  updateTotal();
  closeObSheets();
}

// прочие товары со склада: можно несколько, у каждого своё количество
function renderCsGoods(body, foot) {
  const words = (document.getElementById('cs_search').value || '').trim().split(' ').map(pickNorm).filter(Boolean);
  const all = productsForCategory('other');
  const prods = all.filter(p => !words.length || words.every(w => pickNorm(p.name).includes(w)));
  const inR = new Set(collectOtherStockItems('other').map(it => String(it.product_id)));
  const unitOf = p => p.unit === 'pc' ? T.unit_pc : T.unit_l;
  let html = '';
  const freq = words.length ? [] : csFreqFor('other_stock').filter(f => f.product_id && all.some(p => p.id === f.product_id));
  if (freq.length) html += `<div class="ps-grp" style="margin-top:0;">${T.cat_freq}</div><div class="cs-freq">` + freq.map(f => {
    const p = all.find(x => x.id === f.product_id);
    return `<button type="button" class="${String(p.id) === String(CS.pid) ? 'on' : ''}" onclick="CS.pid='${p.id}'; CS.qty=${Number(f.qty) || 1}; renderCatSheet()">${escapeHtml(p.name)}<em>${p.sell_price ? csMoney(p.sell_price) : ''}</em></button>`;
  }).join('') + `</div>`;
  html += `<div class="ps-grp">${T.cat_all_stock}</div>` + (prods.length ? prods.map(p => {
    const q = sellQty(p) || 0;
    return `<button type="button" class="ps-item${String(p.id) === String(CS.pid) ? ' on' : ''}${!(q > 0) ? ' out' : ''}" onclick="CS.pid='${p.id}'; CS.qty=1; renderCatSheet()">
      <div><b>${escapeHtml(p.name)}${inR.has(String(p.id)) ? ' ✓' : ''}</b><small class="${q > 0 ? '' : 'none'}">${q > 0 ? T.psh_instock + ' ' + whQty(q) + ' ' + unitOf(p) : T.psh_out}</small></div><em>${p.sell_price ? csMoney(p.sell_price) : '—'}</em></button>`;
  }).join('') : `<div class="pick-note">${T.pick_nothing}</div>`);
  body.innerHTML = html;
  if (CS.pid) {
    const p = all.find(x => String(x.id) === String(CS.pid));
    const step = p && p.unit !== 'pc' ? 0.5 : 1;
    foot.innerHTML = `<div class="cs-qty"><button type="button" onclick="CS.qty=Math.max(${step}, Math.round((CS.qty-${step})*10)/10); renderCatSheet()">−</button><label><input id="csQtyIn" type="text" inputmode="${step === 1 ? 'numeric' : 'decimal'}" data-int="${step === 1 ? 1 : ''}" autocomplete="off" value="${csQty(CS.qty)}" onfocus="this.select()" oninput="csQtyType(this)" onchange="csQtyDone(this)" onkeydown="if(event.key==='Enter'){this.blur();}"><span>${p ? unitOf(p) : ''}</span></label><button type="button" onclick="CS.qty=Math.round((CS.qty+${step})*10)/10; renderCatSheet()">+</button></div>`
      + `<button type="button" class="ps-go" onclick="csGoodsApply()">${T.cat_add}</button>`;
  } else {
    foot.innerHTML = '';
  }
}
function csGoodsApply() {
  const p = productsForCategory('other').find(x => String(x.id) === String(CS.pid));
  if (!p) return;
  // уже есть в чеке — меняем количество, иначе новая строка
  const ex = collectOtherStockItems('other').find(it => String(it.product_id) === String(p.id));
  if (ex && ex._row) {
    document.getElementById(`other_stock_qty_${ex._row}`).value = CS.qty;
  } else {
    addOtherStockRow('other');
    const id = otherStockSeq;
    const sel = document.getElementById(`other_stock_product_${id}`);
    if (sel) { sel.value = String(p.id); onOtherStockPicked('other', id); }
    const q = document.getElementById(`other_stock_qty_${id}`);
    if (q) q.value = CS.qty;
  }
  paymentSplitTouched = false;
  updateTotal();
  closeObSheets();
}

// ---- Шторки формы замены (телефон) ----
const PSH = { key: '', liters: 0 };
function openObSheet(id) {
  const sh = document.getElementById(id), bg = document.getElementById('obSheetBg');
  if (!sh || !bg) return;
  bg.classList.add('open'); sh.classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeObSheets() {
  document.querySelectorAll('.ob-sheet.open').forEach(x => x.classList.remove('open'));
  const bg = document.getElementById('obSheetBg');
  if (bg) bg.classList.remove('open');
  document.body.style.overflow = '';
  // блок «Оплата» возвращаем на место в форме
  const pay = document.querySelector('#rcPayHost .af-pay');
  const bar = document.querySelector('#view-add .af-bar');
  if (pay && bar) bar.parentNode.insertBefore(pay, bar);
  if (typeof csPlaceExtras === 'function') csPlaceExtras(null);
}
document.addEventListener('keydown', e => { if (e.key === 'Escape' && document.querySelector('.ob-sheet.open')) closeObSheets(); });

// Пробег и срок напоминания — внутри окна «Моторное масло» (весь блок «Пробег»
// с +5/+8 тыс. и пробегом в день) и окна «АКПП» (свои срок и пробег). Блоки
// переносятся в окно и обратно в скрытое хранилище формы: поля, их id и вся
// прежняя логика остаются теми же. Текущий пробег у машины один на визит.
var ATF = { manual: false, KM: 40000 };  // var: resetItemInputs может сработать раньше этой строки
function atfSync() {
  const mil = document.getElementById('mileage');
  const cur = document.getElementById('atf_cur'), next = document.getElementById('atf_next_mileage');
  const m = parseInt(mil.value);
  if (cur && document.activeElement !== cur) cur.value = mil.value;
  if (next && !ATF.manual) next.value = m > 0 ? m + ATF.KM : '';
}
function atfCurInput() {
  const mil = document.getElementById('mileage');
  mil.value = document.getElementById('atf_cur').value;
  mil.dispatchEvent(new Event('input', { bubbles: true }));
  atfSync();
}
function csPlaceExtras(key) {
  const box = document.getElementById('cs_extra'), hold = document.getElementById('csHold');
  if (!box || !hold) return;
  const mil = document.getElementById('afMil'), atf = document.getElementById('afAtf');
  const want = key === 'fluid_0' ? mil : (key === 'fluid_1' ? atf : null);
  [mil, atf].forEach(el => { if (el && el !== want && el.parentNode !== hold) hold.appendChild(el); });
  if (want && want.parentNode !== box) box.appendChild(want);
  if (want === atf) atfSync();
}
csPlaceExtras(null);

function brandFieldIdFor(key) {
  const fi = FLUID_KEYS.indexOf(key), ti = FILTER_KEYS.indexOf(key);
  return fi >= 0 ? `fluid_brand_${fi}` : (ti >= 0 ? `filter_brand_${ti}` : '');
}
function openPickSheet(key) {
  PSH.key = key;
  const fi = FLUID_KEYS.indexOf(key);
  PSH.liters = fi >= 0 ? (parseFloat((document.getElementById(`fluid_liters_${fi}`) || {}).value) || 0) : 0;
  if (fi >= 0 && !PSH.liters) {
    const prev = (LAST_VISIT_ITEMS || []).find(it => it.key === key);
    if (prev && prev.qty) PSH.liters = Number(prev.qty) || 0;
  }
  document.getElementById('pickSheetTitle').textContent = T[key] || '';
  const inp = document.getElementById('pickSheetSearch');
  inp.value = '';
  renderPickSheet();
  openObSheet('pickSheet');
}
function renderPickSheet() {
  const key = PSH.key;
  const list = document.getElementById('pickSheetList');
  const foot = document.getElementById('pickSheetFoot');
  if (!list) return;
  const words = (document.getElementById('pickSheetSearch').value || '').trim().split(' ').map(pickNorm).filter(Boolean);
  const sel = document.getElementById(brandFieldIdFor(key));
  const cur = sel && sel.tagName === 'SELECT' ? sel.value : '';
  const prevIds = new Set((LAST_VISIT_ITEMS || []).filter(it => it.key === key && it.product_id).map(it => String(it.product_id)));
  const prods = productsForCategory(key).filter(p => !words.length || words.every(w => pickNorm(p.name).includes(w)));
  const unitOf = p => p.unit === 'pc' ? T.unit_pc : T.unit_l;
  // в режиме «Склад магазина» недостающее берётся с основного склада — считаем оба
  const availOf = p => (sellQty(p) || 0) + (STORE_ENABLED ? (mainQtyOf(p) || 0) : 0);
  const row = p => {
    const q = availOf(p);
    const cls = !(q > 0) ? 'none' : (q <= (FLUID_KEYS.indexOf(key) >= 0 ? 8 : 3) ? 'low' : '');
    const stock = !(q > 0) ? T.psh_out : `${T.psh_instock} ${whQty(q)} ${unitOf(p)}${cls === 'low' ? ' · ' + T.psh_low : ''}`;
    return `<button type="button" class="ps-item${String(p.id) === cur ? ' on' : ''}${!(q > 0) ? ' out' : ''}" onclick="pickSheetChoose(${p.id})">
      <div><b>${escapeHtml(p.name)}</b><small class="${cls}">${stock}</small></div><em>${p.sell_price ? Number(p.sell_price).toLocaleString('ru-RU') : '—'}</em></button>`;
  };
  const prev = prods.filter(p => prevIds.has(String(p.id)));
  const rest = prods.filter(p => !prevIds.has(String(p.id)))
    .sort((a, b) => ((availOf(b) > 0) - (availOf(a) > 0)) || String(a.name).localeCompare(String(b.name)));
  let html = '';
  if (prev.length) html += `<div class="ps-grp">${T.psh_last}</div>` + prev.map(row).join('');
  if (rest.length) html += `<div class="ps-grp">${prev.length ? T.psh_other : T.psh_all}</div>` + rest.map(row).join('');
  list.innerHTML = html || `<div class="pick-note">${T.pick_nothing}</div>`;
  const fi = FLUID_KEYS.indexOf(key);
  if (fi >= 0) {
    const opts = [3, 3.5, 4, 4.5, 5, 6];
    foot.innerHTML = `<div class="ps-grp" style="margin-top:0;">${T.psh_liters}</div><div class="ps-lit">` +
      opts.map(v => `<button type="button" class="${PSH.liters === v ? 'on' : ''}" onclick="PSH.liters=${v}; renderPickSheet()">${String(v).replace('.', ',')}</button>`).join('') + `</div>` +
      (cur ? `<button type="button" class="ps-go" onclick="pickSheetChoose(${cur})">${T.psh_done}${PSH.liters ? ' · ' + String(PSH.liters).replace('.', ',') + ' ' + T.unit_l : ''}</button>` : '');
  } else {
    foot.innerHTML = '';
  }
}
function setProductInField(key, id, liters) {
  const sel = document.getElementById(brandFieldIdFor(key));
  if (!sel || sel.tagName !== 'SELECT') return false;
  sel.value = String(id);
  if (sel.value !== String(id)) return false;
  sel.dispatchEvent(new Event('change'));
  const fi = FLUID_KEYS.indexOf(key);
  if (fi >= 0 && liters) document.getElementById(`fluid_liters_${fi}`).value = liters;
  ROW_OPEN.add(key);
  paymentSplitTouched = false;
  updateTotal();
  return true;
}
function pickSheetChoose(id) {
  const fi = FLUID_KEYS.indexOf(PSH.key);
  // для масла: если литры ещё не выбраны — сначала отмечаем товар и ждём литры
  if (fi >= 0 && !PSH.liters) {
    setProductInField(PSH.key, id);
    renderPickSheet();
    return;
  }
  if (fi < 0 && addSameFilter(PSH.key, id)) { closeObSheets(); return; }
  setProductInField(PSH.key, id, fi >= 0 ? PSH.liters : 0);
  closeObSheets();
}

// ---- Чек-шторка: все позиции, ✕ и цена, оплата ----
function openReceiptSheet() {
  if (window.matchMedia && window.matchMedia('(min-width: 1200px)').matches) return;
  renderReceiptSheet();
  const pay = document.querySelector('#view-add .af-pay');
  const host = document.getElementById('rcPayHost');
  if (pay && host) host.appendChild(pay);
  openObSheet('rcSheet');
}
function renderReceiptSheet() {
  const box = document.getElementById('rcSheetLines');
  if (!box) return;
  const items = collectItems();
  const plate = (document.getElementById('plate').value || '').trim().toUpperCase();
  document.getElementById('rcSheetPlate').textContent = plate;
  const money = v => (Math.round(Number(v) || 0)).toLocaleString('ru-RU');
  box.innerHTML = items.length ? items.map((it, i) => {
    const title = it.brand || it.name;
    const q = it.qty && it.qty !== 1 ? `${String(it.qty).replace('.', ',')} × ${money(it.unit_price)}` : `1 × ${money(it.unit_price)}`;
    const canEdit = it.key !== 'other_stock';
    const step = FILTER_KEYS.indexOf(it.key) >= 0
      ? `<span class="ir-step"><button type="button" onclick="rcStep(${i}, -1)" aria-label="−">−</button><button type="button" onclick="rcStep(${i}, 1)" aria-label="+">+</button></span>` : '';
    return `<div class="rc-line"><div><b>${escapeHtml(title)}</b><span>${it.brand ? escapeHtml(it.name) + ' · ' : ''}${q}${canEdit ? ` · <a onclick="rcPrice(${i})">${T.rc_price}</a>` : ''}</span></div>${step}<button type="button" class="rc-sum" onclick="rcTotal(${i})" title="${T.rc_total_hint}">${money(it.total)}${rcExtraHtml(it)}</button>${canEdit ? `<button type="button" class="rc-x" onclick="rcRemove(${i})" aria-label="${T.af_remove}">✕</button>` : ''}</div>`;
  }).join('') + (() => {
    const d = discountFor(itemsSubtotal(items));
    return d ? `<div class="rc-line rc-disc"><div><b>${T.disc_title}</b></div><em>−${money(d)}</em></div>` : '';
  })() : `<div class="rcpt-empty" style="display:block;">${T.rcpt_empty}</div>`;
  document.getElementById('rcSheetTotal').textContent = money(payTotal(items));
}
function rcPriceField(it) {
  const fi = FLUID_KEYS.indexOf(it.key), ti = FILTER_KEYS.indexOf(it.key);
  if (fi >= 0) return document.getElementById(`fluid_price_${fi}`);
  if (ti >= 0) return document.getElementById(`filter_price_${ti}`);
  if (it.key === 'other') return document.getElementById('other_price');
  return null;
}
function rcPrice(i) {
  const it = collectItems()[i];
  const el = it && rcPriceField(it);
  if (!el) return;
  const raw = prompt(T.rc_price_prompt + ' ' + (it.brand || it.name), el.value || '');
  if (raw === null) return;
  const v = parseInt(String(raw).replace(/\\D/g, ''));
  if (!(v >= 0)) return;
  el.value = v;
  paymentSplitTouched = false;
  updateTotal();
  renderReceiptSheet();
}
function rcStep(i, dir) {
  irStep(i, dir);
  renderReceiptSheet();
}
function rcRemove(i) {
  const it = collectItems()[i];
  if (!it) return;
  if (it.key === 'other_stock') {
    if (it._row) removeOtherStockRow('other', it._row);
  } else if (it.key === 'other') {
    document.getElementById('other_name').value = '';
    document.getElementById('other_price').value = '';
    updateTotal();
  } else {
    closeItemRow(it.key);
  }
  renderReceiptSheet();
}

// ---- Экран «Сохранено»: итог, отправить клиенту, отмена 10 секунд ----
const SAVED = { id: null, timer: null, left: 0 };
function showSaved(data, payload, items) {
  const scr = document.getElementById('savedScreen');
  if (!scr) return false;
  const money = v => (Math.round(Number(v) || 0)).toLocaleString('ru-RU');
  const total = items.reduce((a, it) => a + it.total, 0);
  const debt = Number(payload.debt_amount) || 0;
  document.getElementById('svSub').textContent = [String(payload.plate || '').toUpperCase(), payload.owner_name, money(total) + ' ' + T.currency].filter(Boolean).join(' · ');
  const rows = [];
  const nm = parseInt(payload.next_mileage) || 0;
  rows.push([T.sv_next_change, (data.next_date || '—') + (nm ? ' · ' + nm.toLocaleString('ru-RU') + ' ' + T.km_short : '')]);
  if (debt > 0) rows.push([T.sv_debt, money(debt) + ' ' + T.currency]);
  const left = items.filter(it => it.product_id).map(it => {
    const p = productsCache.find(x => x.id === it.product_id);
    if (!p) return '';
    const avail = (sellQty(p) || 0) + (STORE_ENABLED ? (mainQtyOf(p) || 0) : 0);
    return `${p.name} — ${whQty(Math.max(0, avail - (Number(it.qty) || 0)))} ${p.unit === 'pc' ? T.unit_pc : T.unit_l}`;
  }).filter(Boolean);
  if (left.length) rows.push([T.sv_stock_left, left.slice(0, 2).join('<br>')]);
  document.getElementById('svCard').innerHTML = rows.map(r => `<div><span>${r[0]}</span><b>${r[1].indexOf('<br>') >= 0 ? r[1].split('<br>').map(escapeHtml).join('<br>') : escapeHtml(r[1])}</b></div>`).join('');
  const send = document.getElementById('svSend');
  if (data.client_link) {
    const link = data.client_link;
    let wa = '';
    if (payload.owner_phone) {
      let digits = String(payload.owner_phone).replace(/\\D/g, '');
      if (digits && !digits.startsWith('998') && digits.length <= 9) digits = '998' + digits;
      wa = `<a class="sv-wa" target="_blank" rel="noopener" href="https://wa.me/${digits}?text=${encodeURIComponent(T.share_text_wa + ' ' + link)}"><i class="fa-brands fa-whatsapp"></i> WhatsApp</a>`;
    }
    send.innerHTML = `<div class="ps-grp" style="margin-top:4px;">${T.sv_send}</div><div class="sv-send">
      <a class="sv-tg" target="_blank" rel="noopener" href="https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(T.share_text_tg)}"><i class="fa-brands fa-telegram"></i> Telegram</a>
      ${wa}</div>`;
    document.getElementById('svQrImg').src = 'https://api.qrserver.com/v1/create-qr-code/?size=520x520&margin=0&data=' + encodeURIComponent(link);
    setSavedQrMode(true);
  } else {
    send.innerHTML = `<div class="sv-note"><i class="fa-brands fa-telegram"></i> ${T.sv_sent_tg}</div>`;
    setSavedQrMode(false);
  }
  SAVED.id = data.oc_id || null;
  clearInterval(SAVED.timer);
  const undo = document.getElementById('svUndo');
  if (SAVED.id && !data.duplicate) {
    SAVED.left = 10;
    undo.hidden = false; undo.disabled = false;
    const tick = () => {
      undo.textContent = `${T.sv_undo} · ${SAVED.left} ${T.sv_sec}`;
      if (SAVED.left <= 0) { clearInterval(SAVED.timer); undo.disabled = true; undo.textContent = T.sv_undo; }
      SAVED.left--;
    };
    tick();
    SAVED.timer = setInterval(tick, 1000);
  } else {
    undo.hidden = true;
  }
  scr.hidden = false;
  document.body.style.overflow = 'hidden';
  return true;
}
function setSavedQrMode(on) {
  document.getElementById('svOk').hidden = on;
  document.getElementById('svBadge').hidden = !on;
  document.getElementById('svTitle').textContent = on ? T.sv_qr_title : T.sv_title;
  document.getElementById('svQrBox').hidden = !on;
  document.getElementById('svNext').textContent = on ? T.sv_ready_next : '+ ' + T.sv_next_car;
  const more = document.getElementById('svMore');
  more.hidden = !on; more.classList.remove('open');
  document.getElementById('svCard').classList.toggle('sv-hide', on);
}
function toggleSavedDetails() {
  const open = document.getElementById('svMore').classList.toggle('open');
  document.getElementById('svCard').classList.toggle('sv-hide', !open);
}
function closeSaved(next) {
  clearInterval(SAVED.timer);
  SAVED.id = null;
  const scr = document.getElementById('savedScreen');
  if (scr) scr.hidden = true;
  document.body.style.overflow = '';
  showTab('add');
  window.scrollTo(0, 0);
  if (next) setTimeout(() => { const pl = document.getElementById('plate'); if (pl) pl.focus(); }, 80);
}
async function undoSaved() {
  if (!SAVED.id || SAVED.left < 0) return;
  const id = SAVED.id;
  clearInterval(SAVED.timer);
  const undo = document.getElementById('svUndo');
  undo.disabled = true;
  let ok = false;
  try {
    const res = await fetch('/api/oil_change/' + id, { method: 'DELETE' });
    const d = await res.json();
    ok = !!d.ok;
  } catch (e) {}
  SAVED.id = null;
  const scr = document.getElementById('savedScreen');
  if (scr) scr.hidden = true;
  document.body.style.overflow = '';
  showTab('add');
  showMsg(ok ? T.sv_undone : T.sv_undo_fail, ok);
  if (ok && typeof fetchProducts === 'function') { try { fetchProducts(); } catch (e) {} }
}

// Оплата одной кнопкой: наличные / карта / наличные + карта / в долг.
let PAY_MODE = 'cash';
function setPayMode(m) {
  PAY_MODE = m;
  document.querySelectorAll('#paySeg button').forEach(b => b.classList.toggle('on', b.dataset.m === m));
  const inputs = document.getElementById('payInputs');
  if (inputs) inputs.style.display = (m === 'mix' || m === 'debt') ? 'block' : 'none';
  const debt = document.getElementById('debt_enabled');
  if (m === 'debt') {
    if (debt && !debt.checked) { debt.checked = true; toggleDebtSection(); }
    paymentSplitTouched = true;
    document.getElementById('pay_cash').value = '';
    document.getElementById('pay_card').value = '';
    updateDebtRemaining();
    return;
  }
  if (debt && debt.checked) { debt.checked = false; toggleDebtSection(); }
  paymentSplitTouched = false;
  updateTotal();
}

function onFluidProductPicked(i) {
  const el = document.getElementById(`fluid_brand_${i}`);
  const opt = el.options[el.selectedIndex];
  if (opt && opt.dataset.price) document.getElementById(`fluid_price_${i}`).value = opt.dataset.price;
  updateTotal();
}

function onFilterProductPicked(i) {
  const el = document.getElementById(`filter_brand_${i}`);
  const opt = el.options[el.selectedIndex];
  if (opt && opt.dataset.price) document.getElementById(`filter_price_${i}`).value = opt.dataset.price;
  updateTotal();
}

function collectItems() {
  const items = [];
  FLUID_KEYS.forEach((key, i) => {
    const price = parseFloat(document.getElementById(`fluid_price_${i}`).value) || 0;
    const liters = parseFloat(document.getElementById(`fluid_liters_${i}`).value) || 0;
    const { brand, product_id } = readBrandField(`fluid_brand_${i}`);
    // товар со склада списывается и при цене 0 (бесплатно, по гарантии) —
    // раньше такая позиция пропадала, и литры не уходили со склада
    if (liters > 0 && (price > 0 || product_id)) {
      items.push({
        key, name: T[key], brand, product_id,
        unit_price: price, qty: liters, total: Math.round(price * liters),
      });
    }
  });
  FILTER_KEYS.forEach((key, i) => {
    const price = parseFloat(document.getElementById(`filter_price_${i}`).value) || 0;
    const brandEl = document.getElementById(`filter_brand_${i}`);
    const { brand, product_id } = brandEl ? readBrandField(`filter_brand_${i}`) : { brand: null, product_id: null };
    if (price > 0 || product_id) {
      const qty = filterQty(i, '');
      items.push({key, name: T[key], brand, product_id, unit_price: price, qty, total: Math.round(price * qty)});
    }
  });
  const otherName = document.getElementById('other_name').value.trim();
  const otherPrice = parseFloat(document.getElementById('other_price').value) || 0;
  if (otherPrice > 0) {
    items.push({key: 'other', name: `${T.other_prefix}: ${otherName || T.other_unnamed}`, unit_price: otherPrice, qty: 1, total: Math.round(otherPrice)});
  }
  items.push(...collectOtherStockItems('other'));
  return withListPrice(items);
}

let paymentSplitTouched = false;

// Скидка клиенту: 0% / 5% / 10% / своя (% или сумма). Клиент платит сумму
// позиций минус скидку; при скидке процентом итог округляется до 1 000.
let DISC = { mode: 'pct', pct: 0, custom: false, value: 0 };
function itemsSubtotal(items) {
  return (items || collectItems()).reduce((sum, i) => sum + i.total, 0);
}
function discountFor(sub) {
  if (!(sub > 0)) return 0;
  let d = 0;
  if (DISC.mode === 'sum') {
    d = Math.round(DISC.value || 0);
  } else if (DISC.pct > 0) {
    const pay = Math.round(sub * (1 - Math.min(DISC.pct, 100) / 100) / 1000) * 1000;
    d = sub - pay;
  }
  return Math.max(0, Math.min(d, sub));
}
function discountPct() {
  return DISC.mode === 'pct' && DISC.pct > 0 ? Math.min(DISC.pct, 100) : null;
}
function payTotal(items) {
  const sub = itemsSubtotal(items);
  return sub - discountFor(sub);
}
function syncDiscUi() {
  document.querySelectorAll('#discSeg button').forEach(b => {
    const p = b.dataset.p;
    b.classList.toggle('on', DISC.custom ? p === 'c' : (DISC.mode === 'pct' && String(DISC.pct) === p));
  });
  const box = document.getElementById('discCustom');
  if (box) box.style.display = DISC.custom ? 'flex' : 'none';
  document.querySelectorAll('#discCustom .disc-unit button').forEach(b => b.classList.toggle('on', b.dataset.u === DISC.mode));
}
function renderDiscSummary(sub) {
  const el = document.getElementById('discSummary');
  if (!el) return;
  const d = discountFor(sub);
  const money = v => Math.round(v).toLocaleString('ru-RU');
  let warn = '';
  if (DISC.mode === 'sum' && (DISC.value || 0) > sub && sub > 0) warn = `<div class="disc-warn">${T.disc_too_big}</div>`;
  if (!d) { el.style.display = warn ? 'block' : 'none'; el.innerHTML = warn; return; }
  const pct = discountPct() || (sub ? Math.round(d / sub * 1000) / 10 : 0);
  el.style.display = 'block';
  el.innerHTML = `<div><span>${T.disc_subtotal}</span><b>${money(sub)}</b></div>`
    + `<div class="d-minus"><span>${T.disc_title} (${String(pct).replace('.', ',')}%)</span><b>−${money(d)}</b></div>`
    + `<div class="d-pay"><span>${T.disc_to_pay}</span><b>${money(sub - d)} ${T.currency}</b></div>` + warn;
}
function discChanged() {
  syncDiscUi();
  // разбивку оплаты не сбрасываем: без долга updateTotal сам подгонит
  // наличные под новую сумму (карту оставит), в долг — предоплата остаётся
  updateTotal();
  if (document.getElementById('rcSheet') && document.getElementById('rcSheet').classList.contains('open')) renderReceiptSheet();
}
function setDiscount(p) {
  DISC = { mode: 'pct', pct: p, custom: false, value: 0 };
  const v = document.getElementById('disc_value'); if (v) v.value = '';
  discChanged();
}
function setDiscountCustom() {
  DISC.custom = true;
  if (DISC.mode === 'pct') { DISC.value = DISC.pct || 0; }
  const v = document.getElementById('disc_value');
  if (v) { v.value = DISC.mode === 'sum' ? (DISC.value || '') : (DISC.pct || ''); setTimeout(() => v.focus(), 50); }
  discChanged();
}
function setDiscUnit(u) {
  DISC.mode = u;
  DISC.custom = true;
  onDiscInput();
}
function onDiscInput() {
  const v = document.getElementById('disc_value');
  const num = Math.max(0, parseFloat(String((v && v.value) || '').replace(',', '.')) || 0);
  if (DISC.mode === 'sum') { DISC.value = num; DISC.pct = 0; }
  else { DISC.pct = Math.min(num, 100); DISC.value = 0; }
  discChanged();
}
function resetDiscount() {
  DISC = { mode: 'pct', pct: 0, custom: false, value: 0 };
  const v = document.getElementById('disc_value'); if (v) v.value = '';
  syncDiscUi();
  renderDiscSummary(0);
}

// Обычная цена позиции (list_price): у товара со склада — цена продажи на
// складе, у вписанного вручную — та, что вписали. Если мастер поменял сумму
// позиции в чеке (rcTotal), разница с обычной ценой — наценка: её видно в
// чеке и в «Статистике» (сервер для товаров со склада ставит цену сам).
function withListPrice(items) {
  items.forEach(it => {
    if (it.list_price != null) return;
    const p = it.product_id ? productsCache.find(x => x.id === it.product_id) : null;
    it.list_price = p && p.sell_price ? Number(p.sell_price) : it.unit_price;
  });
  return items;
}
function itemExtra(it) {
  return Math.round((it.total || 0) - (it.list_price || 0) * (it.qty || 1));
}
// Нажали на сумму позиции в чеке — вписать свою (например 440 000 → 500 000):
// цена за литр/штуку пересчитывается, количество и склад — те же
function rcTotal(i) {
  const it = collectItems()[i];
  if (!it) return;
  const raw = prompt(`${T.rc_total_prompt} ${it.brand || it.name}`, Math.round(it.total));
  if (raw === null) return;
  const total = parseInt(String(raw).replace(/\\D/g, ''));
  if (!(total >= 0)) return;
  const unit = it.qty ? Math.round(total / it.qty * 100) / 100 : total;
  let el = null;
  if (it.key === 'other_stock' && it._row) el = document.getElementById(`other_stock_price_${it._row}`);
  else if (it.key === 'other') el = document.getElementById('other_price');
  else el = rcPriceField(it);
  if (!el) return;
  el.value = it.key === 'other' ? total : unit;
  paymentSplitTouched = false;
  updateTotal();
  if (document.getElementById('rcSheet') && document.getElementById('rcSheet').classList.contains('open')) renderReceiptSheet();
}
function rcExtraHtml(it) {
  const x = itemExtra(it);
  return x > 0 ? ` <span class="rc-up">+${x.toLocaleString('ru-RU')}</span>` : '';
}

// Чек справа (на компьютере): те же позиции, что уйдут в запись
function renderReceipt(items) {
  const box = document.getElementById('rcptLines');
  if (!box) return;
  const pl = document.getElementById('rcptPlate'), plate = document.getElementById('plate');
  if (pl && plate) pl.textContent = (plate.value || '').trim().toUpperCase();
  if (!items.length) { box.innerHTML = `<div class="rcpt-empty">${T.rcpt_empty}</div>`; return; }
  const money = v => (Math.round(Number(v) || 0)).toLocaleString('ru-RU');
  box.innerHTML = items.map((it, i) => {
    const title = it.brand ? it.brand : it.name;
    const sub = (it.brand ? it.name + ' · ' : '') + (it.qty && it.qty !== 1 ? `${it.qty} × ${money(it.unit_price)}` : '1 × ' + money(it.unit_price));
    // фильтр — сколько штук (−/+), как в чеке на телефоне
    const step = FILTER_KEYS.indexOf(it.key) >= 0
      ? `<span class="ir-step"><button type="button" onclick="irStep(${i}, -1)" aria-label="−">−</button><button type="button" onclick="irStep(${i}, 1)" aria-label="+">+</button></span>` : '';
    return `<div class="rcpt-line"><div><b>${escapeHtml(title)}</b><span>${escapeHtml(sub)}</span></div>${step}<button type="button" class="rc-sum" onclick="rcTotal(${i})" title="${T.rc_total_hint}">${money(it.total)}${rcExtraHtml(it)}</button></div>`;
  }).join('') + (() => {
    const d = discountFor(itemsSubtotal(items));
    return d ? `<div class="rcpt-line rcpt-disc"><div><b>${T.disc_title}</b></div><em>−${money(d)}</em></div>` : '';
  })();
}

function updateTotal() {
  const _items = collectItems();
  renderReceipt(_items);
  const subtotal = itemsSubtotal(_items);
  const total = subtotal - discountFor(subtotal);
  renderDiscSummary(subtotal);
  document.getElementById('totalCost').textContent = total.toLocaleString('ru-RU') + ' ' + T.currency;
  const payCash = document.getElementById('pay_cash');
  const payCard = document.getElementById('pay_card');
  if (payCash && payCard && !paymentSplitTouched) {
    if (typeof PAY_MODE !== 'undefined' && PAY_MODE === 'card') {
      payCash.value = '';
      payCard.value = total || '';
    } else {
      payCash.value = total || '';
      payCard.value = '';
    }
  } else if (payCash && payCard && !(document.getElementById('debt_enabled') || {}).checked) {
    // оплату уже меняли вручную, а потом добавили/изменили позиции — без
    // долга нал + карта должны оставаться равны сумме (карту не трогаем)
    const card = Math.min(parseFloat(payCard.value) || 0, total);
    payCard.value = card || '';
    payCash.value = Math.max(0, Math.round(total - card)) || '';
  }
  updateDebtRemaining();
  if (typeof syncItemRows === 'function') syncItemRows();
  if (typeof renderCatTiles === 'function') { renderCatTiles(); renderItRcpt(_items, subtotal); }
}

function onPayCashInput() {
  paymentSplitTouched = true;
  const debtEnabled = document.getElementById('debt_enabled').checked;
  if (!debtEnabled) {
    const total = payTotal();
    const cash = parseFloat(document.getElementById('pay_cash').value) || 0;
    document.getElementById('pay_card').value = Math.max(0, Math.round(total - cash));
  }
  updateDebtRemaining();
}

function onPayCardInput() {
  paymentSplitTouched = true;
  const debtEnabled = document.getElementById('debt_enabled').checked;
  if (!debtEnabled) {
    const total = payTotal();
    const card = parseFloat(document.getElementById('pay_card').value) || 0;
    document.getElementById('pay_cash').value = Math.max(0, Math.round(total - card));
  }
  updateDebtRemaining();
}

function updateDebtRemaining() {
  const debtEl = document.getElementById('debtRemaining');
  if (!debtEl) return;
  const total = payTotal();
  const cash = parseFloat(document.getElementById('pay_cash').value) || 0;
  const card = parseFloat(document.getElementById('pay_card').value) || 0;
  const remaining = Math.max(0, Math.round(total - cash - card));
  debtEl.textContent = remaining.toLocaleString('ru-RU') + ' ' + T.currency;
}

function toggleDebtSection() {
  const enabled = document.getElementById('debt_enabled').checked;
  document.getElementById('debtFields').style.display = enabled ? 'block' : 'none';
  if (!enabled) {
    // выключили - возвращаем обычное поведение (наличные/карта снова = вся сумма)
    paymentSplitTouched = false;
    updateTotal();
    document.getElementById('debt_installment_amount').value = '';
    document.getElementById('debt_interval_days').value = '';
  } else {
    updateDebtRemaining();
  }
}

// ---------- Быстрый ввод ----------
let LAST_VISIT_ITEMS = [];
// смена владельца машины (машину продали): KNOWN_OWNER — кто записан сейчас,
// NEW_OWNER — пользователь подтвердил, что вписывает нового владельца
let KNOWN_OWNER = null;
let NEW_OWNER = false;
let LAST_LOOKED_PLATE = '';  // номер, для которого карточка уже показана — не перерисовываем её зря

function startNewOwner() {
  NEW_OWNER = true;
  setKnownMode(false);
  document.getElementById('owner_name').value = '';
  document.getElementById('owner_phone').value = '';
  const box = document.getElementById('kcPersonBox');
  if (box) box.innerHTML = `<div class="kc-new-owner-box"><b><i class="fa-solid fa-user-pen"></i> ${T.kc_new_owner_title}</b>${T.kc_new_owner_hint}<br><button type="button" onclick="lookupPlate(true)">${T.kc_new_owner_cancel}</button></div>`;
  const nameEl = document.getElementById('owner_name');
  nameEl.scrollIntoView({behavior: 'smooth', block: 'center'});
  setTimeout(() => nameEl.focus(), 300);
}

// ---- Подбор масла по модели машины (справочник car_specs.py) ----
// Карточка под полями «Марка/Модель». Показывает вязкость, допуск и объём
// из справочника и масла со склада точки нужной вязкости (без продвижения
// брендов — только то, что есть у самой точки). «Заполнить масло» ставит
// товар, цену и литры в строку «Моторное масло».
const SPEC = { timer: null, seq: 0, list: [], cur: 0, hiddenFor: '' };
// Подбор масла отключён: карточка не показывается и справочник не запрашивается
function specSchedule(delay) { clearTimeout(SPEC.timer); if (typeof presetsSchedule === 'function') presetsSchedule(delay); }
async function loadSpecs() {
  const model = (document.getElementById('car_model').value || '').trim();
  const brand = document.getElementById('car_brand').value || '';
  const seq = ++SPEC.seq;
  if (model.length < 2) { SPEC.list = []; renderSpecCard(); return; }
  let data = null;
  try {
    data = await (await fetch('/api/car_specs?brand=' + encodeURIComponent(brand) + '&model=' + encodeURIComponent(model))).json();
  } catch (e) { return; }
  if (seq !== SPEC.seq) return;
  SPEC.list = (data && data.matches) || [];
  SPEC.cur = 0;
  renderSpecCard();
}
function specVisc(name) {
  const m = String(name || '').match(/(\\d{1,2})\\s*w\\s*-?\\s*(\\d{2})/i);
  return m ? (m[1] + 'W-' + m[2]) : null;
}
function specApprovalTokens(text) {
  const t = String(text || '').toLowerCase();
  const out = new Set();
  (t.match(/dexos\\s*[12]/g) || []).forEach(x => out.add(x.replace(/\\s+/g, '')));
  (t.match(/\\b\\d{3}\\s?\\d{2}\\b/g) || []).forEach(x => out.add(x.replace(/\\s+/g, '')));
  (t.match(/22[89]\\.\\d{1,2}/g) || []).forEach(x => out.add(x.replace('.', '')));
  (t.match(/ll-?\\d{2}/g) || []).forEach(x => out.add(x.replace('-', '')));
  (t.match(/rbs0-2ae/g) || []).forEach(x => out.add('rbs02ae'));
  return out;
}
function specProducts(s) {
  const prods = productsForCategory('fluid_0');
  const need = new Set(s.visc_list || []), hot = new Set(s.visc_hot || []);
  const tokens = specApprovalTokens(s.approval);
  return prods.map(p => {
    const v = specVisc(p.name);
    if (!v || (!need.has(v) && !hot.has(v))) return null;
    const nm = String(p.name).toLowerCase().replace(/[\\s\\.\\-]/g, '');
    const appr = [...tokens].some(tk => nm.indexOf(tk) >= 0);
    return { p, hot: !need.has(v), appr };
  }).filter(Boolean).sort((a, b) =>
    (a.hot - b.hot) || (b.appr - a.appr) || ((sellQty(b.p) || 0) - (sellQty(a.p) || 0)));
}
function renderSpecCard() {
  const box = document.getElementById('specCard');
  if (!box) return;
  const s = SPEC.list[SPEC.cur];
  const model = (document.getElementById('car_model').value || '').trim().toLowerCase();
  if (!s || SPEC.hiddenFor === model + '|' + s.id) { box.innerHTML = ''; return; }
  const alts = SPEC.list.map((x, i) => i === SPEC.cur ? '' :
    `<button type="button" onclick="SPEC.cur=${i}; renderSpecCard()">${escapeHtml(x.model)}</button>`).join('');
  const matches = specProducts(s);
  const unit = T.unit_l;
  const stock = matches.length ? matches.slice(0, 4).map(m => `
      <div class="sp-prod"><span>${escapeHtml(m.p.name)}${m.appr ? `<span class="sp-badge">${T.sp_appr_badge}</span>` : ''}${m.hot ? `<span class="sp-badge hot">${T.sp_hot_badge}</span>` : ''}</span><em>${whQty(sellQty(m.p))} ${unit}</em></div>`).join('')
    : `<div class="sp-note">${T.sp_stock_none}</div>`;
  const hot = (s.visc_hot || []).length ? `<span>${T.sp_hot}</span><div>${escapeHtml(s.visc_hot.join(' / '))} <i>— ${T.sp_hot_note}</i></div>` : '';
  const row = (label, val) => val ? `<span>${label}</span><div>${escapeHtml(val)}</div>` : '';
  box.innerHTML = `<div class="sp-card">
    <div class="sp-head"><i class="fa-solid fa-book-open" style="color:#1d4ed8;margin-top:2px;"></i>
      <b>${T.sp_title}: ${escapeHtml(s.model)}<small>${escapeHtml(s.engine)}</small></b>
      <button type="button" class="sp-x" onclick="hideSpecCard()" aria-label="${T.sp_hide}">✕</button></div>
    ${alts ? `<div class="sp-alt">${T.sp_other} ${alts}</div>` : ''}
    <div class="sp-grid">
      ${row(T.sp_oil, s.visc)}
      ${row(T.sp_approval, s.approval)}
      ${row(T.sp_volume, s.oil_vol)}
      ${hot}
    </div>
    ${WAREHOUSE_ENABLED ? `<div class="sp-stock"><div style="font-weight:600;margin-bottom:2px;">${T.sp_stock}</div>${stock}</div>` : ''}
    <button type="button" class="sp-fill" onclick="fillFromSpec()"><i class="fa-solid fa-wand-magic-sparkles"></i> ${T.sp_fill}</button>
    <details class="sp-more"><summary>${T.sp_more}</summary>
      <div class="sp-grid">${row(T.sp_trans, [s.trans, s.trans_spec].filter(Boolean).join('\\n'))}${row(T.sp_brake, s.brake)}${row(T.sp_coolant, s.coolant)}</div>
    </details>
    <div class="sp-note${s.approx ? ' warn' : ''}">${s.approx ? T.sp_approx : T.sp_note}</div>
  </div>`;
}
function hideSpecCard() {
  const s = SPEC.list[SPEC.cur];
  if (s) SPEC.hiddenFor = (document.getElementById('car_model').value || '').trim().toLowerCase() + '|' + s.id;
  renderSpecCard();
}
function fillFromSpec() {
  const s = SPEC.list[SPEC.cur];
  if (!s) return;
  const best = specProducts(s).find(m => !m.hot);
  const brandEl = document.getElementById('fluid_brand_0');
  let filledProduct = false;
  if (best && brandEl && brandEl.tagName === 'SELECT') {
    const opt = Array.from(brandEl.options).find(o => o.value === String(best.p.id));
    if (opt) {
      brandEl.value = opt.value;
      document.getElementById('fluid_price_0').value = opt.dataset.price || '';
      filledProduct = true;
    }
  }
  if (s.liters) document.getElementById('fluid_liters_0').value = s.liters;
  ROW_OPEN.add('fluid_0');
  syncItemRows();
  paymentSplitTouched = false;
  updateTotal();
  const multi = /\\)\\s*\\n|\\)\\s+[≈\\d]/.test(s.oil_vol || '');
  showMsg((filledProduct ? T.sp_filled : T.sp_filled_liters) + (multi ? ' ' + T.sp_volume_check : ''), true);
  const row = document.getElementById('row_fluid_0');
  if (row) row.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

function repeatLastVisit(itemsArg, doneMsg) {
  // «Как в прошлый раз»: те же масло/фильтры/литры, цены — текущие со склада
  // (если товар есть на складе), иначе цена прошлого визита.
  // С аргументами — то же для «Готового набора» (itemsArg — его позиции).
  const items = Array.isArray(itemsArg) ? itemsArg : (LAST_VISIT_ITEMS || []);
  if (!items.length) return;
  FLUID_KEYS.forEach((_, i) => {
    ['fluid_brand_', 'fluid_price_', 'fluid_liters_'].forEach(pfx => { const el = document.getElementById(pfx + i); if (el) el.value = ''; });
  });
  FILTER_KEYS.forEach((_, i) => {
    ['filter_brand_', 'filter_price_', 'filter_qty_'].forEach(pfx => { const el = document.getElementById(pfx + i); if (el) el.value = ''; });
  });
  document.getElementById('other_name').value = '';
  document.getElementById('other_price').value = '';
  otherStockRows = [];
  renderOtherStockRows('other');

  const missing = [];
  const pickBrand = (el, it) => {
    if (!el) return null;
    if (el.tagName !== 'SELECT') { el.value = it.brand || ''; return null; }
    const opts = Array.from(el.options);
    let opt = it.product_id ? opts.find(o => o.value === String(it.product_id)) : null;
    if (!opt && it.brand) {
      const want = it.brand.trim().toUpperCase();
      opt = opts.find(o => (o.dataset.name || '').trim().toUpperCase() === want);
    }
    if (opt && opt.value) { el.value = opt.value; return opt; }
    if (it.brand) missing.push(it.brand);
    return null;
  };
  items.forEach(it => {
    const fi = FLUID_KEYS.indexOf(it.key);
    const fl = FILTER_KEYS.indexOf(it.key);
    // если марки больше нет на складе — строку не заполняем: иначе сохранилась
    // бы позиция без товара (не списалась бы со склада и выпала бы из прибыли)
    const isSelect = id => { const el = document.getElementById(id); return el && el.tagName === 'SELECT'; };
    if (fi >= 0) {
      const opt = pickBrand(document.getElementById(`fluid_brand_${fi}`), it);
      if (isSelect(`fluid_brand_${fi}`) && !opt) return;
      document.getElementById(`fluid_price_${fi}`).value = (opt && opt.dataset.price) || it.unit_price || '';
      document.getElementById(`fluid_liters_${fi}`).value = it.qty || '';
    } else if (fl >= 0) {
      const opt = pickBrand(document.getElementById(`filter_brand_${fl}`), it);
      if (isSelect(`filter_brand_${fl}`) && !opt) return;
      document.getElementById(`filter_price_${fl}`).value = (opt && opt.dataset.price) || it.unit_price || '';
      const qEl = document.getElementById(`filter_qty_${fl}`);
      if (qEl) qEl.value = it.qty > 1 ? Math.round(it.qty) : '';
    } else if (it.key === 'other') {
      document.getElementById('other_name').value = String(it.name || '').replace(/^[^:]+:\\s*/, '');
      document.getElementById('other_price').value = it.unit_price || it.total || '';
    }
  });
  const stockItems = items.filter(it => it.key === 'other_stock');
  if (stockItems.length) fillOtherStockRowsFrom('other', stockItems);
  paymentSplitTouched = false;
  updateTotal();
  if (missing.length) showMsg(`${T.kc_repeat_missing} ${missing.join(', ')}`, false);
  else showMsg(doneMsg || T.kc_repeat_done, true);
  const mileageEl = document.getElementById('mileage');
  if (mileageEl) { mileageEl.focus(); mileageEl.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
}

// «Готовые наборы»: частые сочетания масла и фильтров этой точки для модели
// машины (сервер считает по истории за год). Клик — форма заполнена.
const PRESETS = { timer: null, seq: 0, model: '', sets: [] };
function presetsSchedule(delay) {
  clearTimeout(PRESETS.timer);
  PRESETS.timer = setTimeout(loadPresets, delay == null ? 450 : delay);
}
async function loadPresets() {
  const box = document.getElementById('presetBox');
  if (!box) return;
  const model = (document.getElementById('car_model').value || '').trim();
  if (model.toLowerCase() === PRESETS.model) return;
  PRESETS.model = model.toLowerCase();
  const seq = ++PRESETS.seq;
  if (model.length < 2) { PRESETS.sets = []; renderPresets(); return; }
  let data = null;
  try { data = await (await fetch('/api/entry_presets?model=' + encodeURIComponent(model))).json(); } catch (e) { return; }
  if (seq !== PRESETS.seq) return;
  PRESETS.sets = (data && data.sets) || [];
  renderPresets();
}
function renderPresets() {
  const box = document.getElementById('presetBox');
  const kc = document.getElementById('kcPresets');
  const money = v => (Math.round(Number(v) || 0)).toLocaleString('ru-RU');
  const sets = PRESETS.sets || [];
  const describe = set => {
    const fl = set.items.filter(it => String(it.key).indexOf('fluid_') === 0);
    const fi = set.items.filter(it => String(it.key).indexOf('filter_') === 0);
    return {
      head: fl.map(it => `${it.brand || it.name} · ${String(it.qty).replace('.', ',')} ${T.unit_l}`).join(' + '),
      tail: fi.map(it => T[it.key] || it.name).join(', '),
      sum: set.items.reduce((a, it) => a + (Number(it.total) || 0), 0),
      nf: fi.length,
    };
  };
  // у узнанного клиента наборы — короткими кнопками в его карточке
  if (kc) {
    kc.innerHTML = sets.map((set, i) => {
      const d = describe(set);
      const label = d.nf ? `${T.preset_short_oil} + ${d.nf} ${T.preset_short_filters}` : T.preset_short_oil;
      return `<button type="button" class="kc-preset" title="${escapeHtml(d.head + (d.tail ? ' + ' + d.tail : ''))}" onclick="applyPreset(${i})">${label} · ${money(d.sum)}</button>`;
    }).join('');
  }
  if (!box) return;
  if (kc || !sets.length) { box.hidden = true; box.innerHTML = ''; return; }
  box.innerHTML = `<div class="preset-h">${T.preset_title}<small>— ${T.preset_hint}</small></div><div class="preset-list">` +
    sets.map((set, i) => {
      const d = describe(set);
      return `<button type="button" class="preset-btn" onclick="applyPreset(${i})"><b>${escapeHtml(d.head)}</b>${d.tail ? `<span>+ ${escapeHtml(d.tail)}</span>` : ''}<em>${money(d.sum)}<small>${set.count} ${T.preset_times}</small></em></button>`;
    }).join('') + '</div>';
  box.hidden = false;
}
function applyPreset(i) {
  const set = PRESETS.sets[i];
  if (set) repeatLastVisit(set.items, T.preset_done);
}
document.addEventListener('DOMContentLoaded', () => {
  const p = document.getElementById('plate');
  if (p) p.addEventListener('input', () => {
    const pl = document.getElementById('rcptPlate'); if (pl) pl.textContent = (p.value || '').trim().toUpperCase();
    const ih = document.querySelector('#itRcpt .ir-h b'); if (ih) ih.textContent = (p.value || '').trim().toUpperCase();
  });
});

// Горячие клавиши (компьютер): F2 — новая замена, Ctrl+Enter — сохранить,
// F4 — «как в прошлый раз» для узнанного клиента.
document.addEventListener('keydown', e => {
  if (e.isComposing || e.altKey || e.metaKey) return;
  const addView = document.getElementById('view-add');
  const addOpen = addView && addView.style.display !== 'none' && addView.offsetParent !== null;
  if (e.key === 'F2' && !e.ctrlKey && !e.shiftKey) {
    if (document.querySelector('.modal-overlay.open')) return;
    e.preventDefault();
    showTab('add');
    setTimeout(() => { const pl = document.getElementById('plate'); if (pl) pl.focus(); }, 60);
    return;
  }
  if (!addOpen) return;
  if (e.key === 'Enter' && e.ctrlKey) {
    e.preventDefault(); e.stopImmediatePropagation();
    submitCar();
    return;
  }
  if (e.key === 'F4' && !e.ctrlKey && !e.shiftKey && LAST_VISIT_ITEMS.length) {
    e.preventDefault();
    repeatLastVisit();
  }
}, true);

// Следующая замена по пробегу: +5 тыс. / +8 тыс. / свой шаг. Выбор запоминается
// на этом телефоне. Если мастер сам поправил поле — больше его не перезаписываем.
const KM = { step: 0, custom: 0, manual: false };
try {
  KM.step = parseInt(localStorage.getItem('mb_km_step')) || 0;
  KM.custom = parseInt(localStorage.getItem('mb_km_custom')) || 0;
} catch (e) {}

function renderKmChips() {
  const el = document.getElementById('kmChips');
  if (!el) return;
  const opts = [5000, 8000];
  if (KM.custom && !opts.includes(KM.custom)) opts.push(KM.custom);
  el.innerHTML = opts.map(v => `<button type="button" class="km-chip ${KM.step === v ? 'on' : ''}" onclick="setKmStep(${v})">+${(v / 1000).toLocaleString('ru-RU')} ${T.km_thousand}</button>`).join('')
    + `<button type="button" class="km-chip" onclick="askKmStep()">${T.km_custom}</button>`;
}

function setKmStep(v, force) {
  KM.step = (KM.step === v && !force) ? 0 : v;
  try { localStorage.setItem('mb_km_step', KM.step); } catch (e) {}
  KM.manual = false;
  applyKmStep();
  renderKmChips();
}

function askKmStep() {
  const raw = prompt(T.km_prompt, KM.custom || 10000);
  if (raw === null) return;
  const v = parseInt(String(raw).replace(/\\D/g, ''));
  if (!(v > 0) || v > 100000) { showMsg(T.km_bad, false); return; }
  KM.custom = v;
  try { localStorage.setItem('mb_km_custom', v); } catch (e) {}
  setKmStep(v, true);
}

renderKmChips();

function applyKmStep() {
  if (!KM.step || KM.manual) return;
  const m = parseInt(document.getElementById('mileage').value);
  const next = document.getElementById('next_mileage');
  if (m > 0 && next) next.value = m + KM.step;
  applyDailyKm();
}

// Средний пробег в день → когда следующая замена. Пример: следующая замена
// через 5 000 км, машина проезжает 80 км в день → через 63 дня. Срок замены
// (поле «Интервал») выставляется сам в днях; если мастер поправил его вручную —
// больше не перезаписываем. Для знакомой машины пробег в день подставляется
// из прошлой замены или считается по прошлому визиту (пробег и дата).
const DK = { intervalManual: false, applied: false, last: null };

function dkDaysBetween(a, b) {
  const d1 = new Date(a + 'T00:00:00'), d2 = new Date(b + 'T00:00:00');
  return Math.round((d2 - d1) / 86400000);
}
function dkToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function dkFmtDate(d) {
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`;
}
// пробег в день по прошлому визиту: (пробег сейчас − пробег тогда) / дни
function dkFromHistory() {
  const L = DK.last;
  const m = parseInt(document.getElementById('mileage').value);
  if (!L || !L.mileage || !L.date || !(m > L.mileage)) return null;
  const days = dkDaysBetween(String(L.date).slice(0, 10), dkToday());
  if (days < 7) return null;
  const v = Math.round((m - L.mileage) / days);
  return v >= 1 && v <= 2000 ? { km: v, days } : null;
}
function useDkSuggest(v) {
  document.getElementById('daily_km').value = v;
  DK.intervalManual = false;
  applyDailyKm();
}
function applyDailyKm() {
  const el = document.getElementById('daily_km');
  const hint = document.getElementById('dkHint');
  const sug = document.getElementById('dkSuggest');
  if (!el || !hint) return;
  const daily = parseInt(el.value);
  const s = dkFromHistory();
  sug.innerHTML = s && s.km !== daily
    ? `<button type="button" class="km-chip" onclick="useDkSuggest(${s.km})">${T.daily_km_hist} ~${s.km} ${T.km_per_day} · ${T.daily_km_use}</button>`
    : '';
  if (!(daily > 0)) {
    hint.textContent = '';
    if (DK.applied && !DK.intervalManual) {
      document.getElementById('interval_value').value = 3;
      document.getElementById('interval_unit').value = 'months';
    }
    DK.applied = false;
    return;
  }
  const m = parseInt(document.getElementById('mileage').value);
  const n = parseInt(document.getElementById('next_mileage').value);
  if (!(m > 0) || !(n > m)) { hint.textContent = T.daily_km_need; return; }
  const days = Math.min(730, Math.max(1, Math.round((n - m) / daily)));
  const d = new Date();
  d.setDate(d.getDate() + days);
  if (!DK.intervalManual) {
    document.getElementById('interval_value').value = days;
    document.getElementById('interval_unit').value = 'days';
    DK.applied = true;
  }
  hint.innerHTML = `${T.daily_km_next} <b>${dkFmtDate(d)}</b> — ${T.daily_km_in} ${days} ${T.daily_km_days} ` +
    `(${(n - m).toLocaleString('ru-RU')} ${T.km_short} ÷ ${daily} ${T.km_per_day})` +
    (DK.intervalManual ? `<br><span style="color:#B45309">${T.daily_km_manual}</span> <button type="button" class="km-chip" onclick="DK.intervalManual = false; applyDailyKm()">${T.daily_km_apply} ${days} ${T.daily_km_days}</button>` : '');
}
function resetDailyKm() {
  const el = document.getElementById('daily_km');
  if (el) el.value = '';
  DK.intervalManual = false;
  DK.applied = false;
  DK.last = null;
  const hint = document.getElementById('dkHint');
  if (hint) hint.textContent = '';
  const sug = document.getElementById('dkSuggest');
  if (sug) sug.innerHTML = '';
}

// Клавиатура телефона: цифровая для чисел, «Далее» переходит к следующему полю.
function tuneNumberInputs(root) {
  (root || document).querySelectorAll('input[type=number]:not([inputmode])').forEach(el => {
    const step = el.getAttribute('step') || '';
    el.setAttribute('inputmode', step.includes('.') ? 'decimal' : 'numeric');
  });
}
tuneNumberInputs();
new MutationObserver(muts => muts.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1) tuneNumberInputs(n); })))
  .observe(document.body, { childList: true, subtree: true });

document.addEventListener('keydown', e => {
  if (e.key !== 'Enter' || e.isComposing) return;
  const el = e.target;
  const form = document.getElementById('view-add');
  if (!form || !form.contains(el) || !['INPUT', 'SELECT'].includes(el.tagName) || el.type === 'checkbox') return;
  e.preventDefault();
  const fields = Array.from(form.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([disabled]), select:not([disabled]), textarea'))
    .filter(f => f.offsetParent !== null);
  const next = fields[fields.indexOf(el) + 1];
  if (next) next.focus(); else el.blur();
});

function resetItemInputs() {
  FLUID_KEYS.forEach((_, i) => {
    document.getElementById(`fluid_brand_${i}`).value = '';
    document.getElementById(`fluid_price_${i}`).value = '';
    document.getElementById(`fluid_liters_${i}`).value = '';
  });
  FILTER_KEYS.forEach((_, i) => {
    document.getElementById(`filter_price_${i}`).value = '';
    const fb = document.getElementById(`filter_brand_${i}`);
    if (fb) fb.value = '';
    const fq = document.getElementById(`filter_qty_${i}`);
    if (fq) fq.value = '';
  });
  ['atf_cur', 'atf_next_mileage'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const atfInt = document.getElementById('atf_interval');
  if (atfInt) atfInt.value = 6;
  if (window.ATF) ATF.manual = false;
  document.getElementById('other_name').value = '';
  document.getElementById('other_price').value = '';
  document.getElementById('knownClientPanel').innerHTML = '';
  otherStockRows = [];
  renderOtherStockRows('other');
  clearPick('main');
  ROW_OPEN = new Set(ROW_DEFAULT);
  updateTotal();
}

let plateSuggestLoading = false;

async function ensureCarsCacheLoaded() {
  if (carsCache.length || plateSuggestLoading) return;
  plateSuggestLoading = true;
  try {
    await fetchCars();
  } catch (e) { /* тихо — просто не будет подсказок в этот раз */ }
  plateSuggestLoading = false;
}

async function onPlateInput() {
  const plateEl = document.getElementById('plate');
  if (plateEl.value !== plateEl.value.toUpperCase()) {
    const pos = plateEl.selectionStart;
    plateEl.value = plateEl.value.toUpperCase();
    try { plateEl.setSelectionRange(pos, pos); } catch (e) {}
  }
  const val = plateEl.value.trim().toUpperCase();
  const dropdown = document.getElementById('plateSuggest');
  if (!val) { dropdown.style.display = 'none'; dropdown.innerHTML = ''; return; }
  await ensureCarsCacheLoaded();
  const matches = carsCache.filter(c => (c.plate_number || '').toUpperCase().includes(val)).slice(0, 8);
  if (!matches.length) { dropdown.style.display = 'none'; dropdown.innerHTML = ''; return; }
  dropdown.innerHTML = matches.map(c => `
    <div class="ps-item" onmousedown="selectPlateSuggestion(${escapeHtml(JSON.stringify(c.plate_number))})">
      <div class="ps-plate">${escapeHtml(c.plate_number)}</div>
      <div class="ps-owner">${escapeHtml(c.owner_name || '')}${c.car_brand ? ' · ' + escapeHtml(c.car_brand) + (c.car_model ? ' ' + escapeHtml(c.car_model) : '') : ''}</div>
    </div>
  `).join('');
  dropdown.style.display = '';
}

function selectPlateSuggestion(plate) {
  document.getElementById('plate').value = plate;
  document.getElementById('plateSuggest').style.display = 'none';
  lookupPlate();
}

function onPlateBlur() {
  setTimeout(() => {
    const dropdown = document.getElementById('plateSuggest');
    if (dropdown) dropdown.style.display = 'none';
  }, 150);
  lookupPlate();
}

async function lookupPlate(force) {
  const plate = document.getElementById('plate').value.trim();
  const panel = document.getElementById('knownClientPanel');
  // тот же номер — карточка уже на экране; не перерисовываем (иначе уход
  // курсора из поля номера сбрасывал бы, например, режим «новый владелец»)
  if (!force && plate && plate === LAST_LOOKED_PLATE) return;
  LAST_LOOKED_PLATE = plate;
  KNOWN_OWNER = null;
  NEW_OWNER = false;
  if (!plate) { panel.innerHTML = ''; setKnownMode(false); lastKnownNextMileage = null; DK.last = null; applyDailyKm(); checkMileageVsDue(); return; }
  try {
    const res = await fetch('/api/history/' + encodeURIComponent(plate));
    const data = await res.json();

    const crossHtml = renderCrossNetworkHistory(data.cross_history);

    if (!data.car) {
      panel.innerHTML = crossHtml;
      setKnownMode(false);
      lastKnownNextMileage = null;
      DK.last = null;
      applyDailyKm();
      checkMileageVsDue();
      return;
    }

    document.getElementById('owner_name').value = data.car.owner_name || '';
    document.getElementById('owner_phone').value = data.car.owner_phone || '';
    KNOWN_OWNER = {name: (data.car.owner_name || '').trim(), phone: (data.car.owner_phone || '').trim()};
    if (data.car.car_brand) document.getElementById('car_brand').value = data.car.car_brand;
    document.getElementById('car_model').value = data.car.car_model || '';
    document.getElementById('vin').value = data.car.vin || '';
    if (typeof renderVinHint === 'function') renderVinHint();
    if (typeof renderQuickModels === 'function') renderQuickModels();
    specSchedule(0);

    const name = data.car.owner_name || T.kc_no_name;
    const initials = name.trim().split(/\\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?';
    const carLine = [data.car.car_brand, data.car.car_model].filter(Boolean).join(' ');
    const metaParts = [data.car.owner_phone, carLine].filter(Boolean);

    const last = data.history[0];
    const visitCount = data.history.length;
    lastKnownNextMileage = last ? last.next_mileage : null;
    DK.last = last ? { mileage: last.mileage, date: last.change_date, daily_km: last.daily_km } : null;
    const dkEl = document.getElementById('daily_km');
    if (dkEl && !dkEl.value) {
      const prevDaily = (data.history || []).find(h => h.daily_km);
      if (prevDaily) dkEl.value = prevDaily.daily_km;
    }
    applyDailyKm();
    let lastItemsHtml = '';
    LAST_VISIT_ITEMS = [];
    if (last && last.items_json) {
      try {
        const items = JSON.parse(last.items_json);
        LAST_VISIT_ITEMS = Array.isArray(items) ? items : [];
        lastItemsHtml = '<div class="kc-lv-items">' + items.map(it =>
          `<div class="kc-lv-item"><span>${escapeHtml(it.name)}${it.brand ? ' (' + escapeHtml(it.brand) + ')' : ''}${it.qty && it.qty !== 1 ? ' — ' + escapeHtml(it.qty) + ' ' + T.liters_ph : ''}</span><span>${(Number(it.total) || 0).toLocaleString('ru-RU')} ${T.currency}</span></div>`
        ).join('') + '</div>';
      } catch (e) { /* старая запись без items_json — просто не показываем разбивку */ }
    }
    const mileageParts = [];
    if (last && last.mileage) mileageParts.push(`${T.kc_last_mileage} ${last.mileage.toLocaleString('ru-RU')} ${T.km_short}`);
    if (last && last.next_mileage) mileageParts.push(`${T.kc_due_mileage} ${last.next_mileage.toLocaleString('ru-RU')} ${T.km_short}`);
    // «История»: все визиты в эту точку (новые сверху), у каждого — пробег,
    // что делали, сумма и заметка мастера
    const visitHtml = h => {
      let its = [];
      try { its = h.items_json ? (JSON.parse(h.items_json) || []) : []; } catch (e) { its = []; }
      const mp = [];
      if (h.mileage) mp.push(`${T.kc_last_mileage} ${h.mileage.toLocaleString('ru-RU')} ${T.km_short}`);
      if (h.next_mileage) mp.push(`${T.kc_due_mileage} ${h.next_mileage.toLocaleString('ru-RU')} ${T.km_short}`);
      return `
      <div class="kc-last-visit">
        <div class="kc-lv-top">
          <div>
            <div class="kc-lv-service">${escapeHtml(h.change_date || '')}</div>
            ${mp.length ? `<div class="kc-lv-date">${mp.join(' · ')}</div>` : ''}
          </div>
          <div class="kc-lv-cost">${h.cost ? h.cost.toLocaleString('ru-RU') + ' ' + T.currency : '—'}</div>
        </div>
        ${its.length ? '<div class="kc-lv-items">' + its.map(it =>
          `<div class="kc-lv-item"><span>${escapeHtml(it.name)}${it.brand ? ' (' + escapeHtml(it.brand) + ')' : ''}${it.qty && it.qty !== 1 ? ' — ' + escapeHtml(it.qty) + ' ' + T.liters_ph : ''}</span><span>${(Number(it.total) || 0).toLocaleString('ru-RU')} ${T.currency}</span></div>`
        ).join('') + (h.discount_amount > 0 ? `<div class="kc-lv-item" style="color:#B3241C;"><span>${T.disc_title}</span><span>−${Number(h.discount_amount).toLocaleString('ru-RU')} ${T.currency}</span></div>` : '') + '</div>'
          : (h.service_type ? `<div class="kc-lv-items"><div class="kc-lv-item"><span>${escapeHtml(h.service_type)}</span></div></div>` : '')}
        ${h.notes ? `<div class="kc-note"><i class="fa-solid fa-note-sticky"></i> ${escapeHtml(h.notes)}</div>` : ''}
      </div>`;
    };
    const lastVisitHtml = data.history.length
      ? data.history.slice(0, 30).map(visitHtml).join('')
      : `<div class="kc-last-visit"><span style="color:var(--hint); font-size:13px;">${T.kc_no_history}</span></div>`;

    // заметки сразу на карточке, без «Истории»: последние две — и свои, и
    // других мастеров OilBook (с названием их точки)
    const allNotes = [
      ...data.history.filter(h => h.notes).map(h => ({ date: h.change_date, text: h.notes, shop: '' })),
      ...(data.cross_history || []).filter(h => h.notes).map(h => ({ date: h.change_date, text: h.notes, shop: h.shop_name || '' })),
    ].sort((x, y) => String(y.date).localeCompare(String(x.date))).slice(0, 2);
    const notesHtml = allNotes.length ? `<div class="kc-notes-box">${allNotes.map(n =>
      `<div class="kc-note"><i class="fa-solid fa-note-sticky"></i> <b>${escapeHtml(n.date || '')}${n.shop ? ' · ' + escapeHtml(n.shop) : ''}:</b> ${escapeHtml(n.text)}</div>`).join('')}</div>` : '';

    // компактная карточка: имя + машина + одна строка «прошлый раз» +
    // быстрые кнопки; подробная история раскрывается по «История ›»
    const lastShort = last ? [
        last.change_date,
        last.mileage ? last.mileage.toLocaleString('ru-RU') + ' ' + T.km_short : '',
        LAST_VISIT_ITEMS.map(it => (it.brand || it.name) + (it.qty && it.qty !== 1 ? ' ' + String(it.qty).replace('.', ',') + ' ' + T.unit_l : '')).join(' + '),
      ].filter(Boolean).join(' · ') : T.kc_no_history;
    panel.innerHTML = `
      <div class="known-client kc-compact">
        <div class="kc-top">
          <div class="kc-avatar">${escapeHtml(initials)}</div>
          <div class="kc-top-main">
            <div class="kc-name">${escapeHtml(name)}${visitCount ? ` <span class="kc-visits">✓ ${visitCount} ${T.kc_visits_short}</span>` : ''}</div>
            <div class="kc-meta">${kcMetaHtml(data.car.owner_phone, carLine)}</div>
          </div>
          <button type="button" class="kc-more-btn" onclick="toggleKcDetails(this)" aria-expanded="false">${T.kc_history_btn} <i class="fa-solid fa-chevron-down"></i></button>
        </div>
        <div class="kc-last-line">${escapeHtml(lastShort)}${last && last.cost ? ` · <b>${last.cost.toLocaleString('ru-RU')}</b>` : ''}</div>
        ${notesHtml}
        ${LAST_VISIT_ITEMS.length ? `<div class="kc-quick"><button type="button" class="kc-repeat" onclick="repeatLastVisit()"><i class="fa-solid fa-rotate-right"></i> ${T.kc_repeat_short}<kbd class="af-kbd">F4</kbd></button><div id="kcPresets" class="kc-presets"></div></div>` : '<div class="kc-quick"><div id="kcPresets" class="kc-presets"></div></div>'}
        <div class="kc-details" hidden>
          <div class="kc-detail-actions">
            <button type="button" class="kc-edit-data" onclick="showOwnerFields()"><i class="fa-solid fa-pen"></i> ${T.kc_edit_data}</button>
            <div id="kcPersonBox"><button type="button" class="kc-new-owner" onclick="startNewOwner()"><i class="fa-solid fa-user-pen"></i>${T.kc_new_owner_btn}</button></div>
          </div>
          <div class="kc-history-label">${T.kc_all_visits} (${visitCount})</div>
          ${lastVisitHtml}
        </div>
      </div>
    ` + crossHtml;
    setKnownMode(!!(data.car.owner_name || '').trim());
    if (typeof renderPresets === 'function') renderPresets();
  } catch (e) {
    LAST_LOOKED_PLATE = '';
    panel.innerHTML = '';
    setKnownMode(false);
    lastKnownNextMileage = null;
    checkMileageVsDue();
  }
}

// Постоянный клиент: поля имени/телефона/модели уже заполнены — прячем их,
// чтобы на телефоне сразу было видно пробег и масло. «Изменить данные» —
// показать снова.
function setKnownMode(on) {
  const v = document.getElementById('view-add');
  if (v) v.classList.toggle('kc-known', !!on);
}
function showOwnerFields() {
  setKnownMode(false);
  const el = document.getElementById('owner_name');
  if (el) { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); setTimeout(() => el.focus(), 250); }
}

function toggleKcDetails(btn) {
  const card = btn.closest('.known-client');
  const box = card && card.querySelector('.kc-details');
  if (!box) return;
  box.hidden = !box.hidden;
  btn.setAttribute('aria-expanded', String(!box.hidden));
  btn.classList.toggle('open', !box.hidden);
}

function renderCrossNetworkHistory(crossHistory) {
  if (!crossHistory || !crossHistory.length) return '';
  const entries = crossHistory.map(h => {
    let itemsHtml = '';
    if (h.items_json) {
      try {
        const items = JSON.parse(h.items_json);
        itemsHtml = '<div class="kc-lv-items">' + items.map(it =>
          `<div class="kc-lv-item"><span>${escapeHtml(it.name)}${it.brand ? ' (' + escapeHtml(it.brand) + ')' : ''}${it.qty && it.qty !== 1 ? ' — ' + escapeHtml(it.qty) + ' ' + T.liters_ph : ''}</span></div>`
        ).join('') + '</div>';
      } catch (e) {}
    }
    return `
      <div class="cn-entry">
        <div class="cn-entry-top">
          <div>
            <div class="cn-entry-shop">${escapeHtml(h.shop_name || '—')}</div>
            <div class="cn-entry-date">${h.change_date}${h.mileage ? ' · ' + h.mileage.toLocaleString('ru-RU') + ' ' + T.km_short : ''}</div>
          </div>
        </div>
        ${itemsHtml}
        ${h.notes ? `<div class="kc-note"><i class="fa-solid fa-note-sticky"></i> ${escapeHtml(h.notes)}</div>` : ''}
      </div>
    `;
  }).join('');
  return `
    <div class="cross-network-card">
      <div class="cn-header"><i class="fa-solid fa-globe"></i><span>${T.cn_history_title}</span></div>
      <div class="cn-hint">${T.cn_history_hint}</div>
      ${entries}
    </div>
  `;
}

function focusNextEntry() {
  const mileage = document.getElementById('mileage');
  mileage.scrollIntoView({ behavior: 'smooth', block: 'center' });
  mileage.focus();
}

// Каталог склада для формы замены. На слабом интернете он может не прийти с
// первого раза — тогда поля «марка» временно текстовые, а каталог тихо
// запрашивается ещё несколько раз (и сразу, когда связь вернулась). Уже
// введённое при этом не стирается (см. renderItemLists).
let ITEM_CATALOG_OK = !WAREHOUSE_ENABLED;
let ITEM_CATALOG_TRY = 0;
async function loadItemCatalog() {
  if (ITEM_CATALOG_OK) return true;
  try {
    const res = await fetch('/api/products');
    const list = await res.json();
    if (!Array.isArray(list)) return false;
    productsCache = list;
    ITEM_CATALOG_OK = true;
    renderItemLists();
    renderSvcItemLists();
    return true;
  } catch (e) { return false; }
}
function retryItemCatalog() {
  if (ITEM_CATALOG_OK || ITEM_CATALOG_TRY >= 8) return;
  const wait = [3, 8, 15, 30, 60, 60, 120, 120][ITEM_CATALOG_TRY++] * 1000;
  setTimeout(async () => { if (!(await loadItemCatalog())) retryItemCatalog(); }, wait);
}
window.addEventListener('online', () => { if (!ITEM_CATALOG_OK) loadItemCatalog(); });
async function initItemForms() {
  loadFrequentItems();
  renderItemLists();
  renderSvcItemLists();
  if (WAREHOUSE_ENABLED && !(await loadItemCatalog())) retryItemCatalog();
  restoreAddDraft();
  updateTotal();
}

// ---- Черновик формы «Внести замену» ----
// Всё, что мастер успел ввести, сохраняется на этом телефоне. Если страница
// перезагрузилась (пропал интернет, телефон закрыл приложение в фоне,
// случайно обновили) — при следующем открытии ввод восстанавливается.
// После успешного сохранения черновик удаляется. Хранится до 24 часов.
const ADD_DRAFT_KEY = 'ob_add_draft_' + {{ draft_owner|tojson }};
const ADD_DRAFT_SKIP = ['plateSuggest', 'pickInput'];
let ADD_DRAFT_TIMER = null;
let ADD_DRAFT_READY = false;
function addDraftFields() {
  const view = document.getElementById('view-add');
  if (!view) return [];
  // блоки пробега, пока открыто окно масла/АКПП, лежат вне формы
  const extra = ['afMil', 'afAtf'].map(id => document.getElementById(id)).filter(b => b && !view.contains(b));
  return Array.from(view.querySelectorAll('input[id], select[id], textarea[id]'))
    .concat(...extra.map(b => Array.from(b.querySelectorAll('input[id], select[id]')))).filter(el =>
    el.type !== 'file' && el.type !== 'hidden' && el.type !== 'button' && !ADD_DRAFT_SKIP.includes(el.id)
    && !/_stock_(product|price|qty)_/.test(el.id) && !/^pick/.test(el.id) && !/^cs_/.test(el.id));
}
function saveAddDraft() {
  if (!ADD_DRAFT_READY) return;
  try {
    const f = {};
    addDraftFields().forEach(el => {
      if (el.type === 'checkbox') { if (el.checked) f[el.id] = { c: 1 }; return; }
      if (String(el.value || '').trim() === '') return;
      const opt = el.tagName === 'SELECT' ? el.options[el.selectedIndex] : null;
      f[el.id] = { v: el.value, sel: !!opt, name: opt ? (opt.dataset.name || '') : el.value };
    });
    const plate = (f.plate && f.plate.v) || '';
    const items = collectItems();
    if (!plate.trim() && !items.length) { localStorage.removeItem(ADD_DRAFT_KEY); return; }
    localStorage.setItem(ADD_DRAFT_KEY, JSON.stringify({
      at: Date.now(), f, stock: collectOtherStockItems('other'), pay: typeof PAY_MODE !== 'undefined' ? PAY_MODE : 'cash', disc: DISC,
      touched: !!paymentSplitTouched,
    }));
  } catch (e) { /* память телефона недоступна — просто без черновика */ }
}
function scheduleAddDraft() {
  clearTimeout(ADD_DRAFT_TIMER);
  ADD_DRAFT_TIMER = setTimeout(saveAddDraft, 500);
}
function clearAddDraft() {
  clearTimeout(ADD_DRAFT_TIMER);
  try { localStorage.removeItem(ADD_DRAFT_KEY); } catch (e) {}
}
function discardAddDraft() {
  clearAddDraft();
  ['plate', 'owner_name', 'owner_phone', 'car_model', 'vin', 'mileage', 'next_mileage', 'notes'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  resetItemInputs();
  resetDiscount();
  setPayMode('cash');
  document.getElementById('msg').innerHTML = '';
  SPEC.list = []; SPEC.hiddenFor = ''; renderSpecCard(); renderVinHint(); renderQuickModels();
  presetsSchedule(0);
}
function restoreAddDraft() {
  let d = null;
  try { d = JSON.parse(localStorage.getItem(ADD_DRAFT_KEY) || 'null'); } catch (e) { d = null; }
  ADD_DRAFT_READY = true;
  if (!d || !d.f || Date.now() - (d.at || 0) > 24 * 3600 * 1000) { clearAddDraft(); return; }
  const plateEl = document.getElementById('plate');
  if (plateEl && plateEl.value.trim()) return;  // в форме уже что-то вводят — не мешаем
  const pay = new Set(['pay_cash', 'pay_card', 'debt_enabled', 'debt_installment_amount', 'debt_interval_days', 'disc_value']);
  if (d.disc && typeof d.disc === 'object') {
    DISC = { mode: d.disc.mode === 'sum' ? 'sum' : 'pct', pct: Number(d.disc.pct) || 0, custom: !!d.disc.custom, value: Number(d.disc.value) || 0 };
    const dv = document.getElementById('disc_value');
    if (dv) dv.value = DISC.custom ? (DISC.mode === 'sum' ? (DISC.value || '') : (DISC.pct || '')) : '';
    syncDiscUi();
  }
  const main = {}, payF = {};
  Object.keys(d.f).forEach(id => { (pay.has(id) ? payF : main)[id] = d.f[id]; });
  Object.keys(main).forEach(id => {
    const el = document.getElementById(id);
    if (el && el.type === 'checkbox') { el.checked = true; delete main[id]; }
  });
  restoreItemFields(main);
  if (d.stock && d.stock.length) {
    otherStockRows = [];
    renderOtherStockRows('other');
    fillOtherStockRowsFrom('other', d.stock);
  }
  updateTotal();
  if (d.pay && d.pay !== 'cash') setPayMode(d.pay);
  if (payF.debt_enabled) {
    const cb = document.getElementById('debt_enabled');
    if (cb && !cb.checked) { cb.checked = true; toggleDebtSection(); }
  }
  ['pay_cash', 'pay_card', 'debt_installment_amount', 'debt_interval_days'].forEach(id => {
    const el = document.getElementById(id);
    if (el && payF[id]) el.value = payF[id].v;
  });
  paymentSplitTouched = !!d.touched;
  updateDebtRemaining();
  if (typeof checkMileageVsDue === 'function') checkMileageVsDue();
  showMsg(`<i class="fa-solid fa-clock-rotate-left"></i> ${T.draft_restored} `
    + `<button type="button" class="draft-clear" onclick="discardAddDraft()">${T.draft_clear}</button>`, true);
}
(function () {
  const view = document.getElementById('view-add');
  if (!view) return;
  view.addEventListener('input', scheduleAddDraft);
  view.addEventListener('change', scheduleAddDraft);
  view.addEventListener('click', e => { if (e.target.closest('button')) scheduleAddDraft(); });
  window.addEventListener('pagehide', saveAddDraft);
  document.addEventListener('visibilitychange', () => { if (document.hidden) saveAddDraft(); });
})();
initItemForms();

async function submitCar() {
  const items = collectItems();
  const payCashEl = document.getElementById('pay_cash');
  const payCardEl = document.getElementById('pay_card');
  const debtEnabled = document.getElementById('debt_enabled') && document.getElementById('debt_enabled').checked;
  const payload = {
    plate: document.getElementById('plate').value.trim(),
    owner_name: document.getElementById('owner_name').value.trim(),
    owner_phone: document.getElementById('owner_phone').value.trim(),
    car_brand: document.getElementById('car_brand').value,
    car_model: document.getElementById('car_model').value.trim(),
    vin: vsNorm(document.getElementById('vin').value),
    mileage: document.getElementById('mileage').value,
    next_mileage: document.getElementById('next_mileage').value,
    items: items,
    interval_value: document.getElementById('interval_value').value,
    interval_unit: document.getElementById('interval_unit').value,
    daily_km: (document.getElementById('daily_km') || {}).value || '',
    notes: document.getElementById('notes').value.trim(),
    cash_amount: payCashEl ? payCashEl.value : null,
    card_amount: payCardEl ? payCardEl.value : null,
    discount: discountFor(itemsSubtotal(items)),
    discount_pct: discountPct(),
    master_id: (document.getElementById('master_id') || {}).value || '',
  };
  if (items.some(i => i.key === 'fluid_1')) {
    // масло АКПП — своё напоминание: через сколько месяцев и на каком пробеге
    payload.atf_interval = document.getElementById('atf_interval').value || '6';
    payload.atf_next_mileage = document.getElementById('atf_next_mileage').value || '';
  }
  if (DISC.mode === 'sum' && (DISC.value || 0) > itemsSubtotal(items) && itemsSubtotal(items) > 0) {
    showMsg(T.disc_too_big, false);
    return;
  }
  if (debtEnabled) {
    const total = payTotal(items);
    const cash = parseFloat(payCashEl.value) || 0;
    const card = parseFloat(payCardEl.value) || 0;
    payload.debt_amount = Math.max(0, Math.round(total - cash - card));
    payload.installment_amount = document.getElementById('debt_installment_amount').value;
    payload.interval_days = document.getElementById('debt_interval_days').value;
    if (payload.debt_amount > 0 && (!payload.installment_amount || !payload.interval_days)) {
      showMsg(T.debt_fill_required, false);
      return;
    }
  }
  if (!payload.plate || !payload.owner_name || !payload.interval_value) {
    showMsg(T.msg_fill_required, false);
    return;
  }
  // имя/телефон известной машины изменили, но «Новый владелец» не нажали —
  // спрашиваем, иначе изменения молча терялись, а замена шла старому владельцу
  if (KNOWN_OWNER && !NEW_OWNER) {
    const nameChanged = payload.owner_name && payload.owner_name !== KNOWN_OWNER.name;
    const phoneChanged = payload.owner_phone && payload.owner_phone !== KNOWN_OWNER.phone;
    if ((nameChanged || phoneChanged) && confirm(T.kc_owner_changed_confirm)) NEW_OWNER = true;
  }
  payload.new_owner = NEW_OWNER;
  // номер отправки: при повторном нажатии (после обрыва связи) он тот же,
  // поэтому сервер не создаст дубль, а ответит «уже сохранено»
  // номер привязан к госномеру и живёт 10 минут: если после обрыва связи
  // вносят уже ДРУГУЮ машину (или ту же, но намного позже), это новая
  // замена — ей нужен новый номер, иначе сервер ответил бы «уже сохранено»
  // и она бы не записалась
  const tokenPlate = String(payload.plate || '').toUpperCase().replace(/\\s+/g, '');
  if (!window.ADD_TOKEN || window.ADD_TOKEN_PLATE !== tokenPlate || Date.now() - (window.ADD_TOKEN_AT || 0) > 10 * 60 * 1000) {
    window.ADD_TOKEN = (self.crypto && crypto.randomUUID) ? crypto.randomUUID() : (Date.now() + '-' + Math.random().toString(36).slice(2));
    window.ADD_TOKEN_PLATE = tokenPlate;
    window.ADD_TOKEN_AT = Date.now();
  }
  payload.token = window.ADD_TOKEN;
  let data;
  try {
    const res = await fetch('/api/add', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
    });
    data = await res.json();
  } catch (e) {
    showMsg(T.msg_no_connection, false);
    return;
  }
  if (data.ok) {
    window.ADD_TOKEN = null;
    clearAddDraft();
    setTimeout(loadFrequentItems, 1500);
    showMsg(`✅ ${data.duplicate ? T.msg_already_saved : T.msg_saved} ${data.next_date || '—'}.`, true);
    ['plate','owner_name','owner_phone','car_model','vin','mileage','next_mileage','notes'].forEach(id => document.getElementById(id).value = '');
    SPEC.list = []; SPEC.hiddenFor = ''; renderSpecCard(); renderVinHint();
    loadQuickModels(true);
    KM.manual = false;
    KNOWN_OWNER = null;
    NEW_OWNER = false;
    LAST_LOOKED_PLATE = '';
    LAST_VISIT_ITEMS = [];
    resetItemInputs();
    document.getElementById('interval_value').value = 3;
    document.getElementById('interval_unit').value = 'months';
    paymentSplitTouched = false;
    resetDailyKm();
    resetDiscount();
    setPayMode('cash');
    const payCash = document.getElementById('pay_cash');
    const payCard = document.getElementById('pay_card');
    if (payCash) payCash.value = '';
    if (payCard) payCard.value = '';
    const debtCheckbox = document.getElementById('debt_enabled');
    if (debtCheckbox) {
      debtCheckbox.checked = false;
      document.getElementById('debtFields').style.display = 'none';
      document.getElementById('debt_installment_amount').value = '';
      document.getElementById('debt_interval_days').value = '';
    }
    lastKnownNextMileage = null;
    document.getElementById('mileageCompare').innerHTML = '';
    document.getElementById('knownClientPanel').innerHTML = '';
    setKnownMode(false);
    document.querySelectorAll('#debtTerms button').forEach(b => b.classList.remove('on'));
    // экран «Сохранено»: следующая замена, отправить клиенту, отмена 10 с
    if (!showSaved(data, payload, items) && data.client_link) {
      openModal(payload.plate, data.client_link, payload.owner_phone);
    }
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

// «База»: сначала сразу показываем то, что уже есть на телефоне, потом
// тихо сверяемся с сервером — если ничего не поменялось, он отвечает
// пустым 204 и ничего не скачивается.
let CARS_VER = '';
let carsLoadSeq = 0;
function setCarsData(data, ver) {
  carsCache = data;
  CARS_VER = ver || '';
  CARS_CLIENTS = null;
}
async function fetchCars() {
  const seq = ++carsLoadSeq;
  const res = await fetch('/api/cars' + (CARS_VER && carsCache.length ? '?v=' + encodeURIComponent(CARS_VER) : ''));
  if (seq !== carsLoadSeq) return false;
  if (res.status === 204) return false;
  const data = await res.json();
  if (seq !== carsLoadSeq || !Array.isArray(data)) return false;
  setCarsData(data, res.headers.get('X-Data-Version'));
  return true;
}
async function loadCars() {
  if (carsCache.length) renderTable(true);
  else document.getElementById('table-body').innerHTML = `<div class="hint-text" style="text-align:center; padding:24px;">${T.history_loading}</div>`;
  if (await fetchCars()) renderTable(true);
}

const DEBTS = { tab: 'active', seq: 0, list: [], woId: null, woReason: 'not_paying' };
const WO_REASONS = ['not_paying', 'discount', 'input_error', 'other'];

function debtDate(v) {
  if (!v) return '';
  const p = String(v).slice(0, 10).split('-');
  return p.length === 3 ? `${p[2]}.${p[1]}.${p[0]}` : String(v);
}

function setDebtTab(tab) {
  DEBTS.tab = tab;
  loadDebts();
}

function renderDebtSummary(ov) {
  const el = document.getElementById('debtsSummary');
  if (!el || !ov) return;
  el.innerHTML = `
    <div><div class="k">${T.debts_sum_total}</div><div class="v">${fmtShort(ov.total_remaining)}</div></div>
    <div><div class="k">${T.debts_sum_overdue}</div><div class="v ${ov.overdue_remaining ? 'bad' : ''}">${fmtShort(ov.overdue_remaining)}</div></div>
    <div><div class="k">${T.debts_sum_repaid}</div><div class="v ok">${fmtShort(ov.repaid_month)}</div></div>`;
}

function renderActiveDebt(d) {
  const pct = d.total_amount ? Math.min(100, Math.round(d.paid_amount / d.total_amount * 100)) : 0;
  return `
    <div class="debt-card ${d.is_overdue ? 'overdue' : ''}">
      <div class="dc-top">
        <div>
          <div class="dc-owner">${escapeHtml(d.owner_name || T.kc_no_name)}</div>
          <div class="dc-meta">${escapeHtml(d.plate_number)}${d.owner_phone ? ' · ' + escapeHtml(d.owner_phone) : ''}</div>
        </div>
        <div>
          <div class="dc-remaining">${fmtNum(d.remaining)} ${T.currency}</div>
          <div class="dc-due ${d.is_overdue ? 'overdue-text' : ''}">${d.is_overdue ? T.debt_overdue : T.debt_next_due} ${debtDate(d.next_due_date)}</div>
        </div>
      </div>
      <div class="dc-prog">
        <div class="bar"><i style="width:${pct}%"></i></div>
        <div class="t"><span>${T.debt_paid_of.replace('{paid}', fmtNum(d.paid_amount)).replace('{total}', fmtNum(d.total_amount))}</span><span>${d.sale_date ? T.debt_since.replace('{date}', debtDate(d.sale_date)) : ''}</span></div>
      </div>
      <div class="dc-pay-row">
        <input id="debt_pay_${d.id}" type="number" inputmode="numeric" placeholder="${T.debt_pay_placeholder}" style="flex:1;">
        <button class="badge active" style="flex:none;" onclick="payDebt(${d.id})">${T.debt_pay_btn}</button>
      </div>
      ${(d.payments_count || !IS_EMPLOYEE) ? `
      <div class="dc-actions">
        ${d.payments_count ? `<button type="button" onclick="toggleDebtHistory(${d.id})">${T.debt_history} · ${d.payments_count}</button>` : ''}
        ${!IS_EMPLOYEE ? `<button type="button" class="danger" onclick="openWriteoff(${d.id})">${T.debt_writeoff_btn}</button>` : ''}
      </div>` : ''}
      <div class="dc-hist" id="debt_hist_${d.id}" style="display:none;"></div>
    </div>`;
}

function renderClosedDebt(d) {
  const status = d.status === 'written_off'
    ? `<div class="dc-status wo">${T.debt_status_written_off.replace('{sum}', fmtNum(d.written_off_amount)).replace('{date}', debtDate(d.closed_at))}${d.writeoff_reason ? ' · ' + (T['wo_r_' + d.writeoff_reason] || '') : ''}</div>`
    : `<div class="dc-status ok">${T.debt_status_completed.replace('{date}', debtDate(d.closed_at || d.next_due_date))}</div>`;
  return `
    <div class="debt-card closed">
      <div class="dc-top">
        <div>
          <div class="dc-owner">${escapeHtml(d.owner_name || T.kc_no_name)}</div>
          <div class="dc-meta">${escapeHtml(d.plate_number)}${d.sale_date ? ' · ' + T.debt_since.replace('{date}', debtDate(d.sale_date)) : ''}</div>
        </div>
        <div><div class="dc-remaining" style="color:var(--text);">${fmtNum(d.total_amount)} ${T.currency}</div></div>
      </div>
      ${status}
      <div class="dc-actions"><button type="button" onclick="toggleDebtHistory(${d.id})">${T.debt_history}</button></div>
      <div class="dc-hist" id="debt_hist_${d.id}" style="display:none;"></div>
    </div>`;
}

async function loadDebts() {
  const seq = ++DEBTS.seq;
  ['active', 'closed'].forEach(t => {
    const b = document.getElementById('dtab_' + t);
    if (b) b.classList.toggle('on', DEBTS.tab === t);
  });
  let ov, list;
  try {
    [ov, list] = await Promise.all([
      fetch('/api/debts/overview').then(r => r.json()),
      fetch(DEBTS.tab === 'closed' ? '/api/debts/closed' : '/api/debts').then(r => r.json()),
    ]);
  } catch (e) { return; }
  if (seq !== DEBTS.seq) return;  // пока грузилось, переключили вкладку
  renderDebtSummary(ov);
  DEBTS.list = Array.isArray(list) ? list : [];
  const el = document.getElementById('debtsList');
  if (!DEBTS.list.length) {
    el.innerHTML = `<div class="hint-text" style="text-align:center; padding:24px;">${DEBTS.tab === 'closed' ? T.debts_closed_empty : T.debts_empty}</div>`;
    return;
  }
  el.innerHTML = DEBTS.list.map(DEBTS.tab === 'closed' ? renderClosedDebt : renderActiveDebt).join('');
}

async function toggleDebtHistory(planId, forceOpen) {
  const box = document.getElementById('debt_hist_' + planId);
  if (!box) return;
  if (box.style.display !== 'none' && !forceOpen) { box.style.display = 'none'; return; }
  let rows = [];
  try { rows = await (await fetch(`/api/debts/${planId}/payments`)).json(); } catch (e) { return; }
  const plan = DEBTS.list.find(x => x.id === planId) || {};
  const canCancel = !IS_EMPLOYEE && plan.status !== 'written_off';
  box.innerHTML = rows.length ? rows.map(p => {
    const cancelled = p.status === 'cancelled';
    return `<div class="dh-row ${cancelled ? 'cancelled' : ''}">
      <span class="dh-date">${debtDate(p.paid_date)}</span><b>${fmtNum(p.amount)} ${T.currency}</b>
      ${cancelled ? `<span class="dh-tag">${T.debt_pay_cancelled}</span>`
        : (canCancel ? `<button type="button" class="dh-x" onclick="cancelDebtPayment(${planId}, ${p.id}, ${p.amount}, '${p.paid_date}')">${T.debt_pay_cancel}</button>` : '')}
    </div>`;
  }).join('') : `<div class="hint-text" style="font-size:12.5px;">${T.debt_hist_empty}</div>`;
  box.style.display = 'block';
}

async function payDebt(planId) {
  const input = document.getElementById(`debt_pay_${planId}`);
  const amount = input.value;
  if (!amount || parseFloat(amount) <= 0) { showMsg(T.debt_pay_invalid, false); return; }
  const res = await fetch(`/api/debts/${planId}/pay`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({amount})
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.debt_pay_success, true);
    loadDebts();
  } else if (data.error === 'overpay') {
    showMsg(T.debt_overpay.replace('{sum}', fmtNum(data.remaining)), false);
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function cancelDebtPayment(planId, paymentId, amount, date) {
  if (!confirm(T.debt_cancel_confirm.replace('{sum}', fmtNum(amount)).replace('{date}', debtDate(date)))) return;
  const res = await fetch(`/api/debts/${planId}/payments/${paymentId}/cancel`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.debt_cancel_done, true);
    // долг мог снова стать активным — показываем его там
    if (DEBTS.tab === 'closed' && data.plan && data.plan.status === 'active') DEBTS.tab = 'active';
    await loadDebts();
    toggleDebtHistory(planId, true);
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

function renderWoReasons() {
  document.getElementById('woReasons').innerHTML = WO_REASONS.map(r =>
    `<button type="button" class="${DEBTS.woReason === r ? 'on' : ''}" onclick="pickWoReason('${r}')">${T['wo_r_' + r]}</button>`).join('');
  document.getElementById('woWarn').style.display = DEBTS.woReason === 'input_error' ? 'block' : 'none';
}
function pickWoReason(r) { DEBTS.woReason = r; renderWoReasons(); }

function openWriteoff(planId) {
  const d = DEBTS.list.find(x => x.id === planId);
  if (!d) return;
  DEBTS.woId = planId;
  DEBTS.woReason = 'not_paying';
  document.getElementById('woTitle').textContent = T.wo_title.replace('{sum}', fmtNum(d.remaining));
  document.getElementById('woText').textContent = T.wo_text.replace('{client}', [d.owner_name, d.plate_number].filter(Boolean).join(' · '));
  renderWoReasons();
  document.getElementById('writeoffModal').classList.add('open');
}
function closeWriteoff() { document.getElementById('writeoffModal').classList.remove('open'); }

async function confirmWriteoff() {
  if (!DEBTS.woId) return;
  const res = await fetch(`/api/debts/${DEBTS.woId}/writeoff`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ reason: DEBTS.woReason })
  });
  const data = await res.json();
  if (data.ok) {
    closeWriteoff();
    DEBTS.woId = null;
    showMsg(T.wo_done, true);
    loadDebts();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

let expenseCategoriesCache = [];

async function loadExpenseCategoryOptions(selectId) {
  if (!expenseCategoriesCache.length) {
    expenseCategoriesCache = await (await fetch('/api/expenses/categories')).json();
  }
  const select = document.getElementById(selectId);
  if (!select) return;
  select.innerHTML = expenseCategoriesCache.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('')
    + `<option value="__custom__">${T.expense_custom_category_option}</option>`;
}

function onExpenseCategoryChange(selectId, customInputId) {
  const select = document.getElementById(selectId);
  const customInput = document.getElementById(customInputId);
  const isCustom = select.value === '__custom__';
  customInput.style.display = isCustom ? 'block' : 'none';
  if (isCustom) customInput.focus();
}

function getSelectedCategory(selectId, customInputId) {
  const select = document.getElementById(selectId);
  if (select.value === '__custom__') {
    return document.getElementById(customInputId).value.trim();
  }
  return select.value;
}

async function loadExpensesTab() {
  await loadExpenseCategoryOptions('exp_category');
  await loadExpenseCategoryOptions('rec_category');
  loadRecurringExpenses();
  loadExpensesJournal();
}

async function submitExpense() {
  const category = getSelectedCategory('exp_category', 'exp_category_custom');
  const name = document.getElementById('exp_name').value.trim();
  const amount = document.getElementById('exp_amount').value;
  if (!category || !amount) { showMsg(T.msg_fill_required, false); return; }
  const res = await fetch('/api/expenses', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category, name, amount}),
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.expense_saved, true);
    document.getElementById('exp_name').value = '';
    document.getElementById('exp_amount').value = '';
    document.getElementById('exp_category_custom').value = '';
    document.getElementById('exp_amount_usd').value = '';
    loadExpensesJournal();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function loadRecurringExpenses() {
  const list = await (await fetch('/api/recurring_expenses')).json();
  const el = document.getElementById('recurringExpensesList');
  if (!el) return;
  const today = new Date().toISOString().slice(0, 10);
  el.innerHTML = list.length ? list.map(r => `
    <div class="recur-exp-card ${r.next_due_date < today ? 'overdue' : ''}">
      <div class="rec-top">
        <div>
          <div class="rec-name">${escapeHtml(r.name || r.category)}</div>
          <div class="rec-meta">${escapeHtml(r.category)} · ${T.expense_next_due} ${r.next_due_date}</div>
        </div>
        <div class="rec-amount">${r.amount.toLocaleString('ru-RU')} ${T.currency}</div>
      </div>
      <div class="rec-actions">
        <button class="badge active" style="flex:1;" onclick="payRecurringExpense(${r.id})">${T.expense_mark_paid_btn}</button>
        <button class="badge inactive" style="flex:none;" onclick="deleteRecurringExpenseBtn(${r.id})">${T.entry_delete}</button>
      </div>
    </div>
  `).join('') : `<div class="hint-text">${T.expense_no_recurring}</div>`;
}

async function createRecurringExpense() {
  const category = getSelectedCategory('rec_category', 'rec_category_custom');
  const name = document.getElementById('rec_name').value.trim();
  const amount = document.getElementById('rec_amount').value;
  const day_of_month = document.getElementById('rec_day').value;
  if (!category || !amount || !day_of_month) { showMsg(T.msg_fill_required, false); return; }
  const res = await fetch('/api/recurring_expenses', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category, name, amount, day_of_month}),
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.expense_recurring_created, true);
    document.getElementById('rec_name').value = '';
    document.getElementById('rec_amount').value = '';
    document.getElementById('rec_day').value = '';
    document.getElementById('rec_category_custom').value = '';
    document.getElementById('rec_amount_usd').value = '';
    loadRecurringExpenses();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function payRecurringExpense(id) {
  const res = await fetch(`/api/recurring_expenses/${id}/pay`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.expense_mark_paid_success, true);
    loadRecurringExpenses();
    loadExpensesJournal();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function deleteRecurringExpenseBtn(id) {
  if (!confirm(T.expense_delete_recurring_confirm)) return;
  const res = await fetch(`/api/recurring_expenses/${id}`, { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.entry_deleted, true);
    loadRecurringExpenses();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

let journalCache = [];

async function loadExpensesJournal() {
  journalCache = await (await fetch('/api/expenses')).json();
  const el = document.getElementById('expensesJournal');
  if (!el) return;
  el.innerHTML = journalCache.length ? journalCache.slice(0, 30).map(e => `
    <div>
      <div class="journal-row">
        <div>
          <div class="jr-cat">${escapeHtml(e.name || e.category)}</div>
          <div class="jr-meta">${escapeHtml(e.category)} · ${e.expense_date}</div>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <div class="jr-amount">−${e.amount.toLocaleString('ru-RU')} ${T.currency}</div>
          <button type="button" class="jr-icon-btn" onclick="toggleExpenseEditForm(${e.id})" title="${T.entry_edit}"><i class="fa-solid fa-pen"></i></button>
          <button type="button" class="jr-icon-btn" style="color:#B3241C;" onclick="deleteExpenseEntry(${e.id})" title="${T.entry_delete}"><i class="fa-solid fa-trash"></i></button>
        </div>
      </div>
      <div id="jredit-${e.id}" class="jr-edit-form" style="display:none;"></div>
    </div>
  `).join('') : `<div class="hint-text">${T.dash_no_data}</div>`;
}

async function toggleExpenseEditForm(id) {
  const panel = document.getElementById('jredit-' + id);
  if (!panel) return;
  const isOpen = panel.style.display !== 'none';
  document.querySelectorAll('.jr-edit-form').forEach(el => { if (el !== panel) el.style.display = 'none'; });
  if (isOpen) { panel.style.display = 'none'; return; }
  const entry = journalCache.find(e => e.id === id);
  if (!entry) return;
  const catSelId = `jr_cat_${id}`, catCustomId = `jr_cat_custom_${id}`;
  await loadExpenseCategoryOptions(catSelId);
  const select = document.getElementById(catSelId);
  const isKnown = expenseCategoriesCache.includes(entry.category);
  panel.innerHTML = `
    <div class="field">
      <label>${T.expense_category_label}</label>
      <select id="${catSelId}" onchange="onExpenseCategoryChange('${catSelId}', '${catCustomId}')"></select>
      <input id="${catCustomId}" placeholder="${T.expense_custom_category_ph}" style="display:none; margin-top:6px;" value="${isKnown ? '' : escapeHtml(entry.category)}">
    </div>
    <div class="field">
      <label>${T.expense_name_label}</label>
      <input id="jr_name_${id}" value="${escapeHtml(entry.name || '')}">
    </div>
    <div class="row2">
      <div class="field">
        <label>${T.expense_amount_label}</label>
        <input id="jr_amount_${id}" type="number" value="${entry.amount}">
      </div>
      <div class="field">
        <label>${T.expense_date_label}</label>
        <input id="jr_date_${id}" type="date" value="${entry.expense_date}">
      </div>
    </div>
    <button class="submit" onclick="saveExpenseEdit(${id})">${T.btn_save}</button>
  `;
  await loadExpenseCategoryOptions(catSelId);
  const selectEl = document.getElementById(catSelId);
  if (isKnown) {
    selectEl.value = entry.category;
  } else {
    selectEl.value = '__custom__';
    onExpenseCategoryChange(catSelId, catCustomId);
  }
  panel.style.display = 'block';
}

async function saveExpenseEdit(id) {
  const category = getSelectedCategory(`jr_cat_${id}`, `jr_cat_custom_${id}`);
  const name = document.getElementById(`jr_name_${id}`).value.trim();
  const amount = document.getElementById(`jr_amount_${id}`).value;
  const expense_date = document.getElementById(`jr_date_${id}`).value;
  if (!category || !amount) { showMsg(T.msg_fill_required, false); return; }
  const res = await fetch(`/api/expenses/${id}`, {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category, name, amount, expense_date}),
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.expense_saved, true);
    loadExpensesJournal();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function deleteExpenseEntry(id) {
  if (!confirm(T.expense_delete_entry_confirm)) return;
  const res = await fetch(`/api/expenses/${id}`, { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.entry_deleted, true);
    loadExpensesJournal();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

function toggleSearchClearBtn() {
  const btn = document.getElementById('searchClearBtn');
  if (!btn) return;
  btn.style.display = document.getElementById('search').value ? 'block' : 'none';
}

function clearSearch() {
  document.getElementById('search').value = '';
  toggleSearchClearBtn();
  BASE_SHOWN = BASE_PAGE;
  renderTable();
}

// Защита от автозаполнения: браузер (Chrome/Яндекс) иногда вставляет
// сохранённый логин (например «admin») в поле поиска базы. Принимаем
// только то, что человек сам набрал/вставил; остальное стираем.
function guardBaseSearchAutofill() {
  const s = document.getElementById('search');
  if (!s || s.dataset.afGuard) return;
  s.dataset.afGuard = '1';
  let typed = false;
  const mark = () => { typed = true; };
  s.addEventListener('beforeinput', mark);
  s.addEventListener('keydown', mark);
  s.addEventListener('paste', mark);
  s.addEventListener('input', (e) => {
    if (!typed && s.value) {
      e.stopImmediatePropagation();
      s.value = '';
      toggleSearchClearBtn();
      BASE_SHOWN = BASE_PAGE;
      renderTable();
    }
    typed = false;
  }, true);
  const wipe = () => {
    if (document.activeElement !== s && s.value && !typed) {
      s.value = '';
      toggleSearchClearBtn();
    }
  };
  setTimeout(wipe, 300);
  setTimeout(wipe, 1500);
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', guardBaseSearchAutofill);
} else {
  guardBaseSearchAutofill();
}

// Показываем по 50 карточек — раньше рисовались сразу все (2 500 карточек
// на каждую букву поиска), и на простом телефоне поиск «тормозил».
const BASE_PAGE = 50;
let BASE_SHOWN = BASE_PAGE;
let CARS_CLIENTS = null;
let baseSearchTimer = null;
function normSearch(v) { return String(v || '').toLowerCase().split(' ').join(''); }
function carSearchKey(c) {
  if (c._k === undefined) c._k = normSearch([c.plate_number, c.owner_name, c.owner_phone, c.car_brand, c.car_model].join(''));
  return c._k;
}
function onBaseSearch() {
  clearTimeout(baseSearchTimer);
  baseSearchTimer = setTimeout(() => { BASE_SHOWN = BASE_PAGE; renderTable(); }, 200);
}
function showMoreCars() {
  BASE_SHOWN += 100;
  renderTable(true);
}

function renderTable(keepPanel) {
  const q = normSearch(document.getElementById('search').value);
  if (!keepPanel && openHistoryRow !== null) {
    const panel = document.getElementById('clientCardPanel');
    panel.style.display = 'none';
    panel.innerHTML = '';
    openHistoryRow = null;
  }
  const countEl = document.getElementById('baseClientCount');
  if (CARS_CLIENTS === null) CARS_CLIENTS = new Set(carsCache.map(c => c.client_id)).size;
  const rows = q ? carsCache.filter(c => carSearchKey(c).includes(q)) : carsCache;
  if (countEl) {
    countEl.textContent = `${T.base_total_clients} ${CARS_CLIENTS} · ${T.base_total_cars} ${carsCache.length}` + (q ? ` · ${T.base_found} ${rows.length}` : '');
  }
  const shown = rows.length > BASE_SHOWN ? rows.slice(0, BASE_SHOWN) : rows;
  const more = rows.length - shown.length;
  document.getElementById('table-body').innerHTML = shown.length ? shown.map((c, i) => `
    <div class="car-card" onclick="toggleHistory(${escapeHtml(JSON.stringify(c.plate_number))})">
      <div class="cc-top">
        <span class="cc-plate">${escapeHtml(c.plate_number)}</span>
        ${c.telegram_id
            ? `<span class="badge linked cc-linkbtn">${T.badge_linked}</span>`
            : `<button class="badge unlinked cc-linkbtn" onclick="event.stopPropagation(); openModal(${escapeHtml(JSON.stringify(c.plate_number))}, ${escapeHtml(JSON.stringify(clientLink(c.link_token)))}, ${escapeHtml(JSON.stringify(c.owner_phone || ''))})">${T.badge_unlinked_btn}</button>`}
      </div>
      <div class="cc-owner">${escapeHtml(c.owner_name || T.kc_no_name)}</div>
      <div class="cc-meta">${escapeHtml([c.owner_phone, [c.car_brand, c.car_model].filter(Boolean).join(' ')].filter(Boolean).join(' · '))}</div>
      <div class="cc-bottom">
        <div>
          <div class="cc-cost">${c.cost ? c.cost.toLocaleString('ru-RU') + ' ' + T.currency : '—'}</div>
          <div class="cc-cost-date">${c.change_date || '—'}</div>
        </div>
        <div class="cc-next">${T.th_next_change}<br>${c.next_change_date || '—'}</div>
        <i class="fa-solid fa-chevron-right cc-chevron"></i>
      </div>
    </div>
  `).join('') + (more > 0 ? `<button type="button" class="base-more" onclick="showMoreCars()">${T.base_show_more} (${more})</button>` : '')
    : `<div class="hint-text" style="text-align:center; padding:20px;">${T.table_empty}</div>`;
}

async function toggleHistory(plate) {
  const panel = document.getElementById('clientCardPanel');
  if (openHistoryRow === plate) {
    panel.style.display = 'none';
    panel.innerHTML = '';
    openHistoryRow = null;
    return;
  }
  openHistoryRow = plate;
  panel.style.display = '';
  panel.innerHTML = T.history_loading;
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const res = await fetch('/api/history/' + encodeURIComponent(plate));
  const data = await res.json();
  // пока шёл ответ, могли открыть другого клиента — тогда этот ответ уже не нужен
  if (openHistoryRow !== plate) return;
  const history = data.history || [];
  historyDataCache[plate] = history;
  const body = panel;

  const car = data.car || {};
  const name = car.owner_name || T.kc_no_name;
  const initials = name.trim().split(/\\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?';
  const carLine = [car.car_brand, car.car_model].filter(Boolean).join(' ');
  const metaParts = [car.owner_phone, carLine].filter(Boolean);

  const entriesHtml = history.length ? history.map(h => {
    let itemsHtml = '';
    if (h.items_json) {
      try {
        const items = JSON.parse(h.items_json);
        itemsHtml = '<div class="kc-he-items">' + items.map(it =>
          `${escapeHtml(it.name)}${it.brand ? ' (' + escapeHtml(it.brand) + ')' : ''}${it.qty && it.qty !== 1 ? ' — ' + escapeHtml(it.qty) + ' ' + T.liters_ph : ''}: ${(Number(it.total) || 0).toLocaleString('ru-RU')} ${T.currency}`
        ).join('<br>') + (h.discount_amount > 0
          ? `<br><span style="color:#B3241C; font-weight:700;"><i class="fa-solid fa-tag"></i> ${T.disc_title}${h.discount_pct ? ' ' + String(h.discount_pct).replace('.', ',') + '%' : ''}: −${Number(h.discount_amount).toLocaleString('ru-RU')} ${T.currency}</span>`
          : '') + '</div>';
      } catch (e) { /* старая запись без items_json */ }
    }
    return `
    <div class="kc-hist-entry" id="hist-entry-${h.id}">
      <div class="kc-he-top">
        <div>
          <div class="kc-he-service">${escapeHtml(h.service_type || T.history_service_fallback)}</div>
          <div class="kc-he-date">${h.change_date} · ${T.history_mileage_label} ${h.mileage || '—'} км</div>
        </div>
        <div class="kc-he-cost">${h.cost ? h.cost.toLocaleString('ru-RU') + ' ' + T.currency : '—'}</div>
      </div>
      <div class="kc-he-meta">${T.history_next_mileage_label} ${h.next_mileage || '—'} км · ${T.history_next_label} ${h.next_change_date || '—'}</div>
      ${itemsHtml}
      ${h.notes ? `<div class="kc-he-notes">${T.history_notes_label} ${escapeHtml(h.notes)}</div>` : ''}
      <div class="kc-he-actions">
        <button class="history-toggle" onclick="openEditModalById(${h.id}, ${escapeHtml(JSON.stringify(plate))})">${T.entry_edit}</button>
        &nbsp;·&nbsp;
        <button class="history-toggle" style="color:#B3241C;" onclick="deleteEntry(${h.id}, ${escapeHtml(JSON.stringify(plate))})">${T.entry_delete}</button>
      </div>
    </div>
  `;
  }).join('') : `<div class="kc-hist-entry" style="color:var(--hint); text-align:center;">${T.history_empty}</div>`;

  body.innerHTML = `
    <div class="known-client">
      <div class="kc-header"><i class="fa-solid fa-user"></i><span>${T.kc_history_card_title}</span>
        <button type="button" class="kc-close" onclick="closeClientCard()" aria-label="${T.kc_close}"><i class="fa-solid fa-xmark"></i></button></div>
      <div class="kc-body">
        <div class="kc-person">
          <div class="kc-avatar">${escapeHtml(initials)}</div>
          <div>
            <div class="kc-name">${escapeHtml(name)}</div>
            <div class="kc-meta">${kcMetaHtml(car.owner_phone, carLine)}</div>
          </div>
        </div>
        <button type="button" class="kc-action-btn" onclick="openAddServiceModal(${escapeHtml(JSON.stringify(plate))})"><i class="fa-solid fa-plus"></i>${T.kc_add_service_btn}</button>
        <div class="kc-pass-row">
          <button type="button" class="kc-pass-tg" onclick="sendPassportTg(${escapeHtml(JSON.stringify(plate))}, ${car.telegram_id ? 'true' : 'false'}, ${escapeHtml(JSON.stringify(car.passport_token || ''))})"><i class="fa-brands fa-telegram"></i> ${T.kc_passport_tg_btn}</button>
          <button type="button" class="kc-pass-open" onclick="sharePassport(${escapeHtml(JSON.stringify(car.passport_token || ''))})" title="${T.kc_passport_btn}" aria-label="${T.kc_passport_btn}"><i class="fa-solid fa-eye"></i></button>
        </div>
        <div style="display:flex; gap:8px; margin-top:8px;">
          <button type="button" class="history-toggle" style="flex:1;" onclick="toggleCarEditForm()">${T.kc_edit_car_btn}</button>
          <button type="button" class="history-toggle" style="flex:1; color:#B3241C;" onclick="deleteCarCompletely(${escapeHtml(JSON.stringify(plate))})">${T.kc_delete_car_btn}</button>
        </div>
        <div id="carEditForm" style="display:none; margin-top:10px; padding:12px; background:var(--field-bg); border-radius:10px;">
          <div class="field">
            <label style="font-size:11px;">${T.field_plate}</label>
            <input id="edit_car_plate" value="${escapeHtml(plate)}">
          </div>
          <div class="field">
            <label style="font-size:11px;">${T.field_owner_name}</label>
            <input id="edit_car_owner_name" value="${escapeHtml(name)}">
          </div>
          <div class="field">
            <label style="font-size:11px;">${T.field_owner_phone}</label>
            <input id="edit_car_owner_phone" value="${escapeHtml(car.owner_phone || '')}">
          </div>
          <div class="row2">
            <div class="field">
              <label style="font-size:11px;">${T.field_car_brand}</label>
              <input id="edit_car_brand" value="${escapeHtml(car.car_brand || '')}">
            </div>
            <div class="field">
              <label style="font-size:11px;">${T.field_car_model}</label>
              <input id="edit_car_model" value="${escapeHtml(car.car_model || '')}">
            </div>
          </div>
          <label style="display:flex; gap:8px; align-items:flex-start; font-size:12px; line-height:1.35; margin:2px 0 10px; color:var(--hint); cursor:pointer;">
            <input type="checkbox" id="edit_car_new_owner" style="width:auto; margin-top:2px; flex:none;">
            <span>${T.edit_new_owner_label}</span>
          </label>
          <button type="button" class="submit" onclick="saveCarEdit(${escapeHtml(JSON.stringify(plate))})">${T.btn_save}</button>
        </div>
        <div class="kc-hist-list">
          <div class="kc-history-label">${T.kc_full_history_label} (${history.length})</div>
          ${entriesHtml}
        </div>
      </div>
    </div>
  `;
}

// Телефон клиента — ссылка «позвонить» (tel:), рядом марка/модель
function kcMetaHtml(phone, carLine) {
  const parts = [];
  const ph = (phone || '').trim();
  if (ph) {
    const digits = ph.replace(/[^0-9+]/g, '');
    parts.push(digits.length >= 7
      ? `<a class="kc-call" href="tel:${escapeHtml(digits)}" onclick="event.stopPropagation()"><i class="fa-solid fa-phone"></i> ${escapeHtml(ph)}</a>`
      : escapeHtml(ph));
  }
  const d = phoneIntl(ph);
  if (d) parts.push(`<a class="kc-call" href="https://wa.me/${d}" target="_blank" rel="noopener" onclick="event.stopPropagation()"><i class="fa-brands fa-whatsapp"></i> WhatsApp</a>`
    + ` <a class="kc-call" href="https://t.me/+${d}" target="_blank" rel="noopener" onclick="event.stopPropagation()"><i class="fa-brands fa-telegram"></i> Telegram</a>`);
  if (carLine) parts.push(escapeHtml(carLine));
  return parts.join(' · ');
}

// номер для ссылок WhatsApp / Telegram: только цифры, с кодом страны (998…)
function phoneIntl(phone) {
  let d = String(phone || '').replace(/\\D/g, '');
  if (d.length === 9) d = '998' + d;
  return d.length >= 11 ? d : '';
}

// ---- «База»: кому пора на замену и обзвон ----
// Сегодня / завтра / неделя / месяц / просрочили: позвонить, WhatsApp с
// готовым текстом, Telegram по номеру, напомнить в боте, отметить звонок.
let BASE_DUE = null, BASE_TAB = null;
const BASE_SHOP_NAME = {{ shop_name|tojson }};
const BASE_GROUPS = ['recall', 'booked', 'today', 'tomorrow', 'week', 'month', 'overdue', 'lost'];
async function loadBaseDue() {
  try {
    const r = await fetch('/api/base/due');
    const d = await r.json();
    if (!d.ok) return;
    BASE_DUE = d;
    if (!BASE_TAB) BASE_TAB = ['recall', 'today', 'booked', 'tomorrow', 'week', 'month', 'overdue'].find(k => d.counts[k]) || 'today';
    renderBaseDue();
  } catch (e) { /* «База» работает и без этого блока */ }
}
function setBaseTab(k) { BASE_TAB = k; renderBaseDue(); }
function baseDay(s) { const p = String(s || '').slice(0, 10).split('-'); return p.length === 3 ? `${p[2]}.${p[1]}` : '—'; }
function baseWhat(e) {
  return e.kinds.map(k => k.kind === 'oil' ? T.base_oil : T.base_atf).join(T.base_and);
}
function baseMsg(e) {
  return T.base_msg_tpl.replace('{name}', e.owner_name ? ', ' + e.owner_name : '').replace('{car}', e.car || '')
    .replace('{plate}', e.plate).replace('{what}', baseWhat(e)).replace('{shop}', BASE_SHOP_NAME);
}
function baseDueRow(e) {
  const d = phoneIntl(e.owner_phone);
  const due = e.kinds.length
    ? e.kinds.map(k => `${k.kind === 'oil' ? T.base_oil : T.base_atf} · ${baseDay(k.due)}${k.km ? ' · ' + Number(k.km).toLocaleString('ru-RU') + ' ' + T.km_short : ''}`).join('<br>')
    : T.base_lost_since.replace('{n}', e.days_since || 0);
  const late = e.days < 0 ? `<span class="bd-late">${T.base_days_over.replace('{n}', -e.days)}</span>` : '';
  const st = e.call ? e.call.result : (e.booked ? 'booked' : '');
  const bf = e.call && e.call.result === 'booked' && e.call.booked_for
    ? ` · ${baseDay(e.call.booked_for)}${e.call.booked_for.length > 10 ? ' ' + e.call.booked_for.slice(11, 16) : ''}` : '';
  const btn = (r, ic) => `<button type="button" class="bd-r${st === r ? ' on' : ''}" onclick="${r === 'booked' ? `baseBookOpen(${e.car_id})` : `baseCall(${e.car_id}, '${r}')`}"><i class="fa-solid ${ic}"></i>${T['base_r_' + r]}</button>`;
  return `<div class="bd-row">
    <div class="bd-main" onclick="toggleHistory(${escapeHtml(JSON.stringify(e.plate))})">
      <div class="bd-top"><span class="cc-plate">${escapeHtml(e.plate)}</span>${late}${st ? `<span class="bd-st st-${st}">${T['base_r_' + st]}${escapeHtml(bf)}</span>` : ''}${e.bot_at ? `<span class="bd-st st-bot"><i class="fa-solid fa-robot"></i> ${baseDay(e.bot_at)}</span>` : ''}</div>
      <div class="bd-name">${escapeHtml(e.owner_name || T.kc_no_name)}${e.car ? ' · ' + escapeHtml(e.car) : ''}</div>
      <div class="bd-due">${due}</div>
      <div class="bd-last">${T.base_last} ${baseDay(e.last_date)}${e.last_mileage ? ' · ' + Number(e.last_mileage).toLocaleString('ru-RU') + ' ' + T.km_short : ''}${e.oil_brand ? ' · ' + escapeHtml(e.oil_brand) : ''}</div>
    </div>
    <div class="bd-act">
      ${d ? `<a class="bd-b call" href="tel:+${d}"><i class="fa-solid fa-phone"></i>${T.base_call}</a>
      <a class="bd-b wa" href="https://wa.me/${d}?text=${encodeURIComponent(baseMsg(e))}" target="_blank" rel="noopener"><i class="fa-brands fa-whatsapp"></i>WhatsApp</a>
      <a class="bd-b tg" href="https://t.me/+${d}" target="_blank" rel="noopener"><i class="fa-brands fa-telegram"></i>Telegram</a>` : `<span class="bd-nophone">${T.base_no_phone}</span>`}
      ${e.telegram ? `<button type="button" class="bd-b bot" onclick="baseRemind(${e.car_id}, this)"><i class="fa-solid fa-robot"></i>${T.base_bot}</button>` : ''}
    </div>
    <div class="bd-res">${btn('called', 'fa-check')}${btn('booked', 'fa-calendar-check')}${btn('no_answer', 'fa-phone-slash')}${btn('refused', 'fa-xmark')}</div>
    <div class="bd-book" id="bdBook_${e.car_id}" hidden></div>
  </div>`;
}
// «Записался» — на какой день и время: по умолчанию день срока (не раньше сегодня), 10:00
function baseBookOpen(carId) {
  const box = document.getElementById('bdBook_' + carId);
  if (!box) return;
  if (!box.hidden) { box.hidden = true; return; }
  const e = Object.values(BASE_DUE.groups).flat().find(x => x.car_id === carId) || {};
  const today = dkToday();
  const day = e.due && e.due > today ? e.due : today;
  box.innerHTML = `<label>${T.base_book_when}</label>
    <div class="bd-book-row"><input type="date" id="bdDate_${carId}" value="${day}" min="${today}">
    <input type="time" id="bdTime_${carId}" value="10:00" step="900">
    <button type="button" class="bd-b call" onclick="baseBookSave(${carId})"><i class="fa-solid fa-check"></i>${T.base_book_save}</button></div>`;
  box.hidden = false;
}
function baseBookSave(carId) {
  const d = (document.getElementById('bdDate_' + carId) || {}).value;
  const t = (document.getElementById('bdTime_' + carId) || {}).value;
  if (!d) return;
  baseCall(carId, 'booked', d + (t ? ' ' + t : ''));
}
function renderBaseDue() {
  const box = document.getElementById('baseDue');
  const d = BASE_DUE;
  if (!box || !d) return;
  const rows = d.groups[BASE_TAB] || [];
  box.innerHTML = `<div class="bd-card">
    <div class="bd-head"><b><i class="fa-solid fa-phone-volume"></i> ${T.base_title_due}</b><span>${T.base_clients} ${d.clients} · ${T.base_cars} ${d.cars}</span></div>
    <div class="bd-tabs">${BASE_GROUPS.filter(k => k !== 'recall' || d.counts.recall || BASE_TAB === 'recall').map(k => `<button type="button" class="${k === BASE_TAB ? 'on' : ''}${k === 'overdue' || k === 'recall' ? ' warn' : ''}" onclick="setBaseTab('${k}')">${T['base_g_' + k]}<em>${d.counts[k] || 0}</em></button>`).join('')}</div>
    <div class="bd-list">${rows.length ? rows.map(baseDueRow).join('') : `<div class="hint-text" style="padding:10px 2px;">${T.base_empty}</div>`}</div>
  </div>`;
}
async function baseCall(carId, result, bookedFor) {
  try {
    const r = await fetch('/api/base/call', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ car_id: carId, result, booked_for: bookedFor || '' }) });
    const j = await r.json();
    if (!j.ok) { showMsg(T.msg_error + ' ' + (j.error || ''), false); return; }
    await loadBaseDue();
  } catch (e) { showMsg(T.msg_error, false); }
}
async function baseRemind(carId, btn) {
  if (btn) btn.disabled = true;
  try {
    const r = await fetch('/api/base/remind', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ car_id: carId }) });
    const j = await r.json();
    showMsg(j.ok ? T.base_bot_sent : (j.error || T.msg_error), !!j.ok);
    if (j.ok) await loadBaseDue();
  } catch (e) { showMsg(T.msg_error, false); }
  if (btn) btn.disabled = false;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function closeClientCard() {
  const panel = document.getElementById('clientCardPanel');
  panel.style.display = 'none';
  panel.innerHTML = '';
  openHistoryRow = null;
  const list = document.getElementById('table-body');
  if (list) list.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Паспорт — клиенту в Telegram через бота. Если клиент ещё не подключён
// к боту, открываем «Поделиться» в Telegram — можно отправить вручную.
async function sendPassportTg(plate, linked, token) {
  if (!linked) {
    if (!token) { showMsg(T.kc_passport_no_token, false); return; }
    if (!confirm(T.kc_passport_tg_not_linked)) return;
    const link = window.location.origin + '/passport/' + token;
    window.open('https://t.me/share/url?url=' + encodeURIComponent(link) + '&text=' + encodeURIComponent(T.kc_passport_btn + ' · ' + plate), '_blank');
    return;
  }
  try {
    const res = await fetch('/api/passport/send_tg/' + encodeURIComponent(plate), { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.ok) showMsg(T.kc_passport_tg_sent, true);
    else showMsg(data.error || T.kc_passport_tg_failed, false);
  } catch (e) {
    showMsg(T.kc_passport_tg_failed, false);
  }
}

function sharePassport(token) {
  if (!token) { showMsg(T.kc_passport_no_token, false); return; }
  const link = window.location.origin + '/passport/' + token;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(link).then(() => {
      showMsg(T.kc_passport_copied, true);
    }).catch(() => {});
  }
  window.open(link, '_blank');
}

function openModal(plate, link, phone) {
  if (!link) { showMsg(T.modal_no_bot_username, false); return; }
  document.getElementById('modalPlate').textContent = plate;
  document.getElementById('modalLink').textContent = link;
  document.getElementById('modalQr').src = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(link);
  const tgBtn = document.getElementById('modalTg');
  tgBtn.href = 'https://t.me/share/url?url=' + encodeURIComponent(link) + '&text=' + encodeURIComponent(T.share_text_tg);
  const waBtn = document.getElementById('modalWa');
  if (phone) {
    let digits = phone.replace(/\\D/g, '');
    if (digits && !digits.startsWith('998') && digits.length <= 9) digits = '998' + digits;
    const text = encodeURIComponent(T.share_text_wa + ' ' + link);
    waBtn.href = 'https://wa.me/' + digits + '?text=' + text;
    waBtn.style.display = 'block';
  } else {
    waBtn.style.display = 'none';
  }
  document.getElementById('linkModal').classList.add('open');
}

function closeModal() {
  document.getElementById('linkModal').classList.remove('open');
}

function copyLink() {
  const text = document.getElementById('modalLink').textContent;
  navigator.clipboard.writeText(text).then(() => showMsg(T.link_copied, true));
}

// ---- Единое модальное окно: и "изменить запись", и "внести новую замену уже известному клиенту" ----
let svcModal = { mode: null, id: null, plate: null };  // mode: 'edit' | 'add'

function renderSvcItemLists() {
  const snap = snapItemFields(['svcFluidsList', 'svcFiltersList']);
  document.getElementById('svcFluidsList').innerHTML = FLUID_KEYS.map((key, i) => `
    <div class="item-row">
      <span class="item-name">${T[key]}</span>
      ${brandFieldHtml(key, `svc_fluid_brand_${i}`, `onSvcFluidProductPicked(${i})`)}
      <input id="svc_fluid_price_${i}" type="number" placeholder="${T.price_per_liter_ph}" oninput="updateSvcTotal()">
      <input id="svc_fluid_liters_${i}" type="number" step="0.1" placeholder="${T.liters_ph}" oninput="updateSvcTotal()">
    </div>
  `).join('');
  document.getElementById('svcFiltersList').innerHTML = FILTER_KEYS.map((key, i) => {
    const prods = productsForCategory(key);
    const brandField = prods.length ? brandFieldHtml(key, `svc_filter_brand_${i}`, `onSvcFilterProductPicked(${i})`) : '';
    return `
    <div class="item-row">
      <span class="item-name" style="flex:${prods.length ? '1.3' : '2.3'};">${T[key]}</span>
      ${brandField}
      <input id="svc_filter_price_${i}" type="number" placeholder="${T.price_ph}" oninput="updateSvcTotal()">
      ${filterQtyHtml('svc_', i)}
    </div>
  `;
  }).join('');
  if (restoreItemFields(snap) && typeof updateSvcTotal === 'function') updateSvcTotal();
}

function onSvcFluidProductPicked(i) {
  const el = document.getElementById(`svc_fluid_brand_${i}`);
  const opt = el.options[el.selectedIndex];
  if (opt && opt.dataset.price) document.getElementById(`svc_fluid_price_${i}`).value = opt.dataset.price;
  updateSvcTotal();
}

function onSvcFilterProductPicked(i) {
  const el = document.getElementById(`svc_filter_brand_${i}`);
  const opt = el.options[el.selectedIndex];
  if (opt && opt.dataset.price) document.getElementById(`svc_filter_price_${i}`).value = opt.dataset.price;
  updateSvcTotal();
}

function collectSvcItems() {
  const items = [];
  FLUID_KEYS.forEach((key, i) => {
    const price = parseFloat(document.getElementById(`svc_fluid_price_${i}`).value) || 0;
    const liters = parseFloat(document.getElementById(`svc_fluid_liters_${i}`).value) || 0;
    const { brand, product_id } = readBrandField(`svc_fluid_brand_${i}`);
    // товар со склада списывается и при цене 0 (бесплатно, по гарантии) —
    // раньше такая позиция пропадала, и литры не уходили со склада
    if (liters > 0 && (price > 0 || product_id)) {
      items.push({
        key, name: T[key], brand, product_id,
        unit_price: price, qty: liters, total: Math.round(price * liters),
      });
    }
  });
  FILTER_KEYS.forEach((key, i) => {
    const price = parseFloat(document.getElementById(`svc_filter_price_${i}`).value) || 0;
    const brandEl = document.getElementById(`svc_filter_brand_${i}`);
    const { brand, product_id } = brandEl ? readBrandField(`svc_filter_brand_${i}`) : { brand: null, product_id: null };
    if (price > 0 || product_id) {
      const qty = filterQty(i, 'svc_');
      items.push({key, name: T[key], brand, product_id, unit_price: price, qty, total: Math.round(price * qty)});
    }
  });
  const otherName = document.getElementById('svc_other_name').value.trim();
  const otherPrice = parseFloat(document.getElementById('svc_other_price').value) || 0;
  if (otherPrice > 0) {
    items.push({key: 'other', name: `${T.other_prefix}: ${otherName || T.other_unnamed}`, unit_price: otherPrice, qty: 1, total: Math.round(otherPrice)});
  }
  items.push(...collectOtherStockItems('svcOther'));
  return items;
}

let svcPaymentSplitTouched = false;
let svcHasDebt = false;  // открыта на исправление запись, по которой есть долг

let svcDiscPctVal = null;  // скидку поставили кнопкой 5% / 10%
function svcSubtotal() {
  return collectSvcItems().reduce((sum, i) => sum + i.total, 0);
}
function svcDiscount(sub) {
  const el = document.getElementById('svc_discount');
  const d = Math.round(parseFloat((el && el.value) || '') || 0);
  return Math.max(0, Math.min(d, sub));
}
function svcPayTotal() {
  const sub = svcSubtotal();
  return sub - svcDiscount(sub);
}
function svcDiscPct(p) {
  const sub = svcSubtotal();
  const pay = Math.round(sub * (1 - p / 100) / 1000) * 1000;
  document.getElementById('svc_discount').value = Math.max(0, sub - pay) || '';
  svcDiscPctVal = p;
  updateSvcTotal(true);
}
function updateSvcTotal(keepPct) {
  const del = document.getElementById('svc_discount');
  if (keepPct !== true && del) {
    if (document.activeElement === del) {
      svcDiscPctVal = null;  // вписали сумму руками — это уже «своя» скидка
    } else if (svcDiscPctVal) {
      // скидка процентом: позиции поменяли — пересчитываем от новой суммы
      const s0 = svcSubtotal();
      del.value = Math.max(0, s0 - Math.round(s0 * (1 - svcDiscPctVal / 100) / 1000) * 1000) || '';
    }
  }
  const sub = svcSubtotal();
  const disc = svcDiscount(sub);
  const total = sub - disc;
  const hint = document.getElementById('svcDiscHint');
  if (hint) hint.textContent = disc ? `${T.disc_subtotal}: ${sub.toLocaleString('ru-RU')} · −${(Math.round(disc / sub * 1000) / 10).toString().replace('.', ',')}%` : '';
  document.getElementById('svcTotalCost').textContent = total.toLocaleString('ru-RU') + ' ' + T.currency;
  const payCash = document.getElementById('svc_pay_cash');
  const payCard = document.getElementById('svc_pay_card');
  if (payCash && payCard && !svcPaymentSplitTouched) {
    payCash.value = total || '';
    payCard.value = '';
  } else if (payCash && payCard && !svcHasDebt) {
    // запись без долга: после изменения позиций нал + карта = новая сумма
    const card = Math.min(parseFloat(payCard.value) || 0, total);
    payCard.value = card || '';
    payCash.value = Math.max(0, Math.round(total - card)) || '';
  }
}

function onSvcPayCashInput() {
  svcPaymentSplitTouched = true;
  const total = svcPayTotal();
  const cash = parseFloat(document.getElementById('svc_pay_cash').value) || 0;
  document.getElementById('svc_pay_card').value = Math.max(0, Math.round(total - cash));
}

function onSvcPayCardInput() {
  svcPaymentSplitTouched = true;
  const total = svcPayTotal();
  const card = parseFloat(document.getElementById('svc_pay_card').value) || 0;
  document.getElementById('svc_pay_cash').value = Math.max(0, Math.round(total - card));
}

function resetSvcItemInputs() {
  FLUID_KEYS.forEach((_, i) => {
    document.getElementById(`svc_fluid_brand_${i}`).value = '';
    document.getElementById(`svc_fluid_price_${i}`).value = '';
    document.getElementById(`svc_fluid_liters_${i}`).value = '';
  });
  FILTER_KEYS.forEach((_, i) => {
    document.getElementById(`svc_filter_price_${i}`).value = '';
    const brandEl = document.getElementById(`svc_filter_brand_${i}`);
    if (brandEl) brandEl.value = '';
    document.getElementById(`svc_filter_qty_${i}`).value = '';
  });
  document.getElementById('svc_other_name').value = '';
  document.getElementById('svc_other_price').value = '';
  document.getElementById('svc_discount').value = '';
  svcDiscPctVal = null;
  svcOtherStockRows = [];
  renderOtherStockRows('svcOther');
  clearPick('svc');
  updateSvcTotal();
}

function fillSvcItemsFrom(items) {
  // подставляет уже сохранённые позиции в поля модалки (режим редактирования)
  const otherStockItems = [];
  (items || []).forEach(it => {
    if (!it.key) return;
    if (it.key === 'other') {
      const label = (it.name || '').replace(T.other_prefix + ': ', '');
      document.getElementById('svc_other_name').value = label === T.other_unnamed ? '' : label;
      document.getElementById('svc_other_price').value = it.total ?? '';
      return;
    }
    if (it.key === 'other_stock') {
      otherStockItems.push(it);
      return;
    }
    const fi = FLUID_KEYS.indexOf(it.key);
    if (fi !== -1) {
      const brandEl = document.getElementById(`svc_fluid_brand_${fi}`);
      selectOrPreserveBrand(brandEl, it);
      document.getElementById(`svc_fluid_price_${fi}`).value = it.unit_price ?? '';
      document.getElementById(`svc_fluid_liters_${fi}`).value = it.qty ?? '';
      return;
    }
    const filI = FILTER_KEYS.indexOf(it.key);
    if (filI !== -1) {
      const brandEl = document.getElementById(`svc_filter_brand_${filI}`);
      if (brandEl) selectOrPreserveBrand(brandEl, it);
      // цена за штуку и количество (раньше фильтр всегда был 1 шт, и цена = сумма)
      const q = Math.round(Number(it.qty) || 1);
      document.getElementById(`svc_filter_price_${filI}`).value = (q > 1 ? it.unit_price : (it.unit_price || it.total)) ?? '';
      document.getElementById(`svc_filter_qty_${filI}`).value = q > 1 ? q : '';
    }
  });
  fillOtherStockRowsFrom('svcOther', otherStockItems);
}

function openEditModalById(id, plate) {
  const entry = (historyDataCache[plate] || []).find(h => h.id === id);
  if (!entry) { showMsg(T.msg_error + ' запись не найдена в кэше, обновите список', false); return; }
  openEditModal(plate, entry);
}

function openEditModal(plate, entry) {
  svcModal = { mode: 'edit', id: entry.id, plate };
  document.getElementById('svcModalTitle').textContent = T.entry_edit_title;
  document.getElementById('edit_mileage').value = entry.mileage ?? '';
  document.getElementById('edit_next_mileage').value = entry.next_mileage ?? '';
  document.getElementById('edit_interval_value').value = entry.interval_months ?? '';
  document.getElementById('edit_interval_unit').value = entry.interval_unit || 'months';
  document.getElementById('edit_notes').value = entry.notes || '';
  resetSvcItemInputs();
  if (entry.items_json) {
    try { fillSvcItemsFrom(JSON.parse(entry.items_json)); } catch (e) {}
  }
  document.getElementById('svc_discount').value = entry.discount_amount || '';
  svcDiscPctVal = entry.discount_pct || null;
  updateSvcTotal(true);
  document.getElementById('svc_pay_cash').value = entry.cash_amount ?? entry.cost ?? '';
  document.getElementById('svc_pay_card').value = entry.card_amount ?? '';
  svcPaymentSplitTouched = true;  // это реальная сохранённая разбивка, не пересчитывать автоматически
  svcHasDebt = (entry.cost || 0) > (entry.cash_amount || 0) + (entry.card_amount || 0);
  teamFillEditMaster(entry);
  document.getElementById('editModal').classList.add('open');
}

function openAddServiceModal(plate) {
  svcModal = { mode: 'add', id: null, plate };
  teamFillEditMaster(null);
  svcHasDebt = false;
  document.getElementById('svcModalTitle').textContent = T.add_service_title;
  document.getElementById('edit_mileage').value = '';
  document.getElementById('edit_next_mileage').value = '';
  document.getElementById('edit_interval_value').value = 3;
  document.getElementById('edit_interval_unit').value = 'months';
  document.getElementById('edit_notes').value = '';
  svcPaymentSplitTouched = false;
  document.getElementById('svc_pay_cash').value = '';
  document.getElementById('svc_pay_card').value = '';
  resetSvcItemInputs();
  document.getElementById('editModal').classList.add('open');
}

function closeEditModal() {
  document.getElementById('editModal').classList.remove('open');
}

async function saveEdit() {
  const items = collectSvcItems();
  const mileage = document.getElementById('edit_mileage').value || null;
  const next_mileage = document.getElementById('edit_next_mileage').value || null;
  const interval_value = document.getElementById('edit_interval_value').value || null;
  const interval_unit = document.getElementById('edit_interval_unit').value;
  const notes = document.getElementById('edit_notes').value;
  const cash_amount = document.getElementById('svc_pay_cash').value || null;
  const card_amount = document.getElementById('svc_pay_card').value || null;
  const discount = svcDiscount(svcSubtotal());
  const discount_pct = discount ? svcDiscPctVal : null;

  let res;
  if (svcModal.mode === 'edit') {
    res = await fetch('/api/oil_change/' + svcModal.id, {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign({ mileage, next_mileage, interval_value, interval_unit, notes, items, cash_amount, card_amount, discount, discount_pct }, teamEditMasterPayload())),
    });
  } else {
    const carRow = carsCache.find(c => c.plate_number === svcModal.plate);
    res = await fetch('/api/add', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        plate: svcModal.plate, owner_name: carRow ? carRow.owner_name : '', mileage, next_mileage,
        interval_value, interval_unit, notes, items, cash_amount, card_amount, discount, discount_pct,
        master_id: (teamEditMasterPayload().master_id || ''),
      }),
    });
  }
  const data = await res.json();
  if (data.ok) {
    closeEditModal();
    showMsg(svcModal.mode === 'edit' ? T.entry_saved : T.service_added, true);
    openHistoryRow = null;  // чтобы toggleHistory ниже заново открыл панель со свежими данными, а не закрыл её
    toggleHistory(svcModal.plate);
    loadCars();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

function toggleCarEditForm() {
  const form = document.getElementById('carEditForm');
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function saveCarEdit(oldPlate) {
  const payload = {
    plate: document.getElementById('edit_car_plate').value.trim(),
    owner_name: document.getElementById('edit_car_owner_name').value.trim(),
    owner_phone: document.getElementById('edit_car_owner_phone').value.trim(),
    car_brand: document.getElementById('edit_car_brand').value.trim(),
    car_model: document.getElementById('edit_car_model').value.trim(),
    new_owner: !!(document.getElementById('edit_car_new_owner') && document.getElementById('edit_car_new_owner').checked),
  };
  if (!payload.plate || !payload.owner_name) {
    showMsg(T.msg_fill_required, false);
    return;
  }
  const res = await fetch('/api/car/' + encodeURIComponent(oldPlate), {
    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.kc_car_saved, true);
    openHistoryRow = null;
    toggleHistory(data.plate);
    loadCars();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function deleteCarCompletely(plate) {
  if (!confirm(T.kc_delete_car_confirm.replace('{plate}', plate))) return;
  const res = await fetch('/api/car/' + encodeURIComponent(plate), { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.kc_car_deleted, true);
    document.getElementById('clientCardPanel').style.display = 'none';
    document.getElementById('clientCardPanel').innerHTML = '';
    openHistoryRow = null;
    loadCars();
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

async function deleteEntry(id, plate) {
  if (!confirm(T.entry_delete_confirm)) return;
  const res = await fetch('/api/oil_change/' + id, { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) {
    showMsg(T.entry_deleted, true);
    openHistoryRow = null;
    toggleHistory(plate);
    loadCars();
  } else if (data.error === 'has_debt') {
    showMsg(T.entry_has_debt, false);
  } else {
    showMsg(T.msg_error + ' ' + data.error, false);
  }
}

// Защита от двойного нажатия: пока действие выполняется (запрос на сервер),
// повторные нажатия той же кнопки игнорируются — иначе на медленном
// интернете можно случайно дважды внести замену, списать товар или оплату.
function guardOnce(names) {
  names.forEach(name => {
    const fn = window[name];
    if (typeof fn !== 'function' || fn.__guarded) return;
    let busy = false;
    const wrapped = async function (...args) {
      if (busy) return;
      busy = true;
      // нажатая кнопка тускнеет, пока ждём сервер — на слабом интернете
      // видно, что нажатие принято и запрос идёт
      const ev = window.event;
      const btn = ev && ev.currentTarget && ev.currentTarget.tagName === 'BUTTON' ? ev.currentTarget : null;
      const wasDisabled = btn ? btn.disabled : false;
      if (btn) { btn.disabled = true; btn.classList.add('net-busy'); }
      try { return await fn.apply(this, args); } finally {
        busy = false;
        if (btn) { btn.disabled = wasDisabled; btn.classList.remove('net-busy'); }
      }
    };
    wrapped.__guarded = true;
    window[name] = wrapped;
  });
}
guardOnce(['submitCar', 'sendPassportTg', 'saveEdit', 'saveCarEdit', 'deleteEntry', 'deleteCarCompletely',
  'payDebt', 'cancelDebtPayment', 'confirmWriteoff', 'submitExpense', 'createRecurringExpense', 'payRecurringExpense', 'deleteRecurringExpenseBtn',
  'saveExpenseEdit', 'deleteExpenseEntry', 'sendBroadcast', 'saveSmsSettings', 'saveNetworkRate', 'saveRateSetup', 'applyRatePrices',
  'createProduct', 'deleteProduct', 'submitRestock', 'submitEditProduct', 'submitTransfer', 'submitShip',
  'submitCatalog', 'applyImport', 'editBranchPrice', 'submitStoreMove', 'submitStoreQty',
  'saveSupplier', 'deleteSupplierBtn', 'saveSupplierProducts', 'saveOrderDraft', 'sendOrder', 'receiveFromDraft',
  'cancelOrderBtn', 'submitReceive', 'submitDistribute', 'keepAllOrder', 'sendOrderBot', 'unlinkSupplierTg', 'saveSupPayment', 'cancelSupPayment', 'restoreSupplier', 'saveOrderNewProduct',
  'createStaff', 'staffResetPw', 'staffToggle', 'staffDelete', 'submitCashAccept', 'cancelCashHandover',
  'submitTeamPay', 'submitTeamAdjust', 'cancelTeamOp', 'saveTeamPaySettings', 'saveTeamSettings']);
</script>
</body>
</html>
"""


NET_GUARD_JS = """<style>
  #netBar { position: fixed; top: 0; left: 0; right: 0; height: 3px; z-index: 99999; pointer-events: none;
    background: linear-gradient(90deg, #0F52BA, #00A8E8, #0F52BA); background-size: 200% 100%;
    animation: netBarMove 1s linear infinite; display: none; }
  @keyframes netBarMove { from { background-position: 200% 0; } to { background-position: 0 0; } }
  #netOffline { position: fixed; top: 0; left: 0; right: 0; z-index: 99998; background: #B42318; color: #fff;
    text-align: center; font: 600 13px/1.2 system-ui, sans-serif; padding: 7px 10px calc(7px + env(safe-area-inset-top, 0px)); display: none; }
  #netToast { position: fixed; left: 0; right: 0; margin: 0 auto; width: fit-content; bottom: calc(86px + env(safe-area-inset-bottom, 0px));
    max-width: min(92vw, 460px); box-sizing: border-box; z-index: 99999; background: #1E293B; color: #fff; border-radius: 12px;
    padding: 12px 16px; font: 500 14px/1.35 system-ui, sans-serif; box-shadow: 0 8px 24px rgba(0,0,0,.25); display: none; }
  #netToast.err { background: #B42318; }
  #netToast.ok { background: #1B8A5A; }
  button.net-busy { opacity: .55; cursor: wait !important; }
  .draft-clear { margin-left: 8px; padding: 4px 10px; border-radius: 8px; border: 1px solid currentColor; background: transparent;
    color: inherit; font: inherit; font-weight: 700; cursor: pointer; }
  .base-more { display: block; width: 100%; margin: 6px 0 14px; padding: 13px; border-radius: 12px; border: 1.5px dashed #94A3B8;
    background: transparent; color: #0F52BA; font-weight: 700; font-size: 14px; cursor: pointer; }
</style>
<script>
(function () {
  // Общий сетевой слой: таймаут, понятные сообщения при плохом интернете,
  // защита от дублей при повторном нажатии, реакция на истёкший вход.
  const NT = {
    offline: {{ T.net_offline|tojson }},
    timeout: {{ T.net_timeout|tojson }},
    unsure: {{ T.net_unsure|tojson }},
    server: {{ T.net_server|tojson }},
    session: {{ T.net_session|tojson }},
    bar: {{ T.net_offline_bar|tojson }},
    back: {{ T.net_back_online|tojson }}
  };
  const origFetch = window.fetch.bind(window);
  // ключ запроса хранится, только пока исход неизвестен (обрыв связи):
  // повторное нажатие с теми же данными уйдёт с тем же ключом, и сервер
  // вернёт прежний результат вместо второй записи
  const pendingKeys = {};
  let active = 0, barTimer = null, toastTimer = null, lastToast = '', lastToastAt = 0;

  function el(id, make) {
    let e = document.getElementById(id);
    if (!e && make && document.body) { e = document.createElement('div'); e.id = id; document.body.appendChild(e); }
    return e;
  }
  function setBusy(delta) {
    active = Math.max(0, active + delta);
    const bar = el('netBar', true);
    if (!bar) return;
    if (active > 0 && !barTimer && bar.style.display !== 'block') {
      barTimer = setTimeout(() => { barTimer = null; if (active > 0) bar.style.display = 'block'; }, 350);
    }
    if (active === 0) { if (barTimer) { clearTimeout(barTimer); barTimer = null; } bar.style.display = 'none'; }
  }
  function toast(text, kind, ms) {
    const now = Date.now();
    if (text === lastToast && now - lastToastAt < 4000) return;  // не дублировать одно и то же
    lastToast = text; lastToastAt = now;
    const t = el('netToast', true);
    if (!t) { alert(text); return; }
    t.className = kind || '';
    t.textContent = text;
    t.style.display = 'block';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.style.display = 'none'; }, ms || 6000);
  }
  window.netToast = toast;
  function rid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return Date.now().toString(36) + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
  }
  function netError(kind, msg, shown) {
    const e = new Error(msg); e.oilNet = kind; e.oilShown = !!shown; return e;
  }
  function jsonResponse(obj, status) {
    return new Response(JSON.stringify(obj), { status: status, headers: { 'Content-Type': 'application/json' } });
  }

  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    const isApi = url.indexOf('/api/') === 0 || url.indexOf(location.origin + '/api/') === 0;
    if (!isApi) return origFetch(input, init);
    init = Object.assign({}, init || {});
    const method = (init.method || 'GET').toUpperCase();
    const write = method !== 'GET' && method !== 'HEAD';
    let key = null;
    if (write) {
      const headers = new Headers(init.headers || {});
      let id;
      if (typeof init.body === 'string' || init.body == null) {
        key = method + ' ' + url + ' ' + (init.body || '');
        id = pendingKeys[key] || rid();
        pendingKeys[key] = id;
      } else {
        id = rid();  // файл/форма — каждый раз новый запрос
      }
      headers.set('X-Request-Id', id);
      init.headers = headers;
    }
    const big = (typeof FormData !== 'undefined' && init.body instanceof FormData) || /backup|restore|import|export|statement/.test(url);
    const ms = big ? 180000 : (write ? 45000 : 30000);
    const ctrl = new AbortController();
    let timedOut = false, callerAborted = false;
    if (init.signal) {
      if (init.signal.aborted) { callerAborted = true; ctrl.abort(); }
      else init.signal.addEventListener('abort', () => { callerAborted = true; ctrl.abort(); });
    }
    init.signal = ctrl.signal;
    const timer = setTimeout(() => { timedOut = true; ctrl.abort(); }, ms);
    setBusy(1);
    let res;
    try {
      res = await origFetch(input, init);
    } catch (e) {
      if (callerAborted) throw e;
      const kind = timedOut ? 'timeout' : 'offline';
      if (write) {
        toast(NT.unsure, 'err', 9000);
        throw netError(kind, NT.unsure, true);
      }
      // чтение не удалось: многие разделы в этом случае просто оставляют
      // прежние цифры — сразу говорим, что данные не обновились (если нет
      // интернета вообще, это уже видно по красной полосе сверху)
      const msg = kind === 'timeout' ? NT.timeout : NT.offline;
      const offBar = document.getElementById('netOffline');
      const barShown = offBar && offBar.style.display === 'block';
      if (!document.hidden && !barShown) toast(msg, 'err');
      throw netError(kind, msg, true);
    } finally {
      clearTimeout(timer);
      setBusy(-1);
    }
    if (key) delete pendingKeys[key];  // ответ получен — исход известен
    if (res.status === 401) {
      toast(NT.session, 'err', 4000);
      setTimeout(() => { location.href = '/login'; }, 1500);
      throw netError('session', NT.session, true);
    }
    if (res.status === 402 && res.headers.get('X-OilBook-Readonly')) {
      // режим «только просмотр»: изменения не сохраняются — показываем,
      // как снова включить запись (оплатить подписку)
      if (window.obShowRo) { window.obShowRo(); return res; }
      location.href = '/subscription';
      throw netError('session', NT.session, true);
    }
    if (res.status === 402) {
      // подписка закончилась, пока панель была открыта
      location.href = '/subscription';
      throw netError('session', NT.session, true);
    }
    const ct = res.headers.get('Content-Type') || '';
    if (!res.ok && ct.indexOf('json') === -1) {
      // сервер ответил не данными, а страницей ошибки
      if (write) return jsonResponse({ ok: false, error: NT.server + ' (' + res.status + ')' }, res.status);
      throw netError('server', NT.server, false);
    }
    return res;
  };

  window.addEventListener('unhandledrejection', (e) => {
    const r = e.reason;
    if (r && r.oilNet) {
      if (!r.oilShown) toast(r.message, 'err');
      e.preventDefault();
    }
  });

  function showOffline(on) {
    const b = el('netOffline', true);
    if (!b) return;
    b.textContent = NT.bar;
    b.style.display = on ? 'block' : 'none';
  }
  window.addEventListener('offline', () => showOffline(true));
  window.addEventListener('online', () => { showOffline(false); toast(NT.back, 'ok', 2500); });
  document.addEventListener('DOMContentLoaded', () => { if (navigator.onLine === false) showOffline(true); });
})();
</script>
"""


PLATE_DECODE_JS = r"""
// ===== Расшифровка ответа модели номеров (общая для сканера в панели и /scanner) =====
// Модель отдаёт 10 позиций × 37 символов (0-9, A-Z, «_» = пусто). Подбираем
// вариант, лучше всего подходящий под известные форматы номеров. Между
// символами шаблона допускается «лишний» символ (разделитель региона,
// флаг, двойное прочтение буквы) — со штрафом, поэтому сдвиг на одну
// позицию больше не ломает весь номер.
const PLATE_ALPHA = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_';
const PLATE_RU_LET = 'ABEKMHOPCTYX';
// D — цифра, L — латинская буква, R — буква, которая бывает на российских номерах
const PLATE_TEMPLATES = [
  ['DDLDDDLL', 0],     // UZ физлица:            01 A 123 BC
  ['DDDDDLLL', 0],     // UZ юрлица (и KG):      01 123 ABC
  ['DDLDDDD', 0.4],    // UZ старый 1996–2008:   23 G 8107
  ['DDLDDDDDD', 0.8],  // UZ иностранцы/фирмы:   01 H 123456, 01 M 123456
  ['RDDDRRDD', 0.6],   // RU:                    A 123 BC 77
  ['RDDDRRDDD', 0.6],  // RU:                    A 123 BC 777
  ['DDDLLLDD', 0.6],   // KZ:                    123 ABC 01
  ['DDDLLDD', 0.8],    // KZ:                    123 AB 01
  ['DDDDLLDD', 0.6]    // TJ:                    1234 AB 01
];
const PLATE_JUNK = 2.0;        // штраф за лишний символ внутри номера
const PLATE_FREE_MARGIN = 3.0; // насколько «свободное» чтение должно быть лучше шаблона
const PLATE_CLASSES = (() => {
  const r = { D: [], L: [], R: [], A: [] };
  for (let j = 0; j < 36; j++) { (j < 10 ? r.D : r.L).push(j); r.A.push(j); }
  for (const ch of PLATE_RU_LET) r.R.push(PLATE_ALPHA.indexOf(ch));
  return r;
})();

function plateDecode(probs) {
  const L = [];
  for (let k = 0; k < 10; k++) {
    const row = [];
    for (let j = 0; j < 37; j++) row.push(Math.log(probs[k * 37 + j] + 1e-9));
    L.push(row);
  }
  // лучший символ каждого класса в каждой позиции
  const best = L.map(row => {
    const o = {};
    for (const c in PLATE_CLASSES) {
      let bj = PLATE_CLASSES[c][0];
      for (const j of PLATE_CLASSES[c]) if (row[j] > row[bj]) bj = j;
      o[c] = bj;
    }
    return o;
  });
  let cand = null;
  for (const [tpl, prior] of PLATE_TEMPLATES) {
    const n = tpl.length, NEG = -1e18;
    const dp = [], bk = [];
    for (let i = 0; i <= 10; i++) { dp.push(new Array(n + 1).fill(NEG)); bk.push(new Array(n + 1).fill(null)); }
    dp[0][0] = 0;
    for (let i = 0; i < 10; i++) for (let t = 0; t <= n; t++) {
      const s = dp[i][t];
      if (s === NEG) continue;
      if (t < n) {  // символ шаблона
        const j = best[i][tpl[t]], v = L[i][j];
        if (s + v > dp[i + 1][t + 1]) { dp[i + 1][t + 1] = s + v; bk[i + 1][t + 1] = [t, j, v]; }
      } else {      // после номера — пусто
        const v = L[i][36];
        if (s + v > dp[i + 1][t]) { dp[i + 1][t] = s + v; bk[i + 1][t] = [t, -2, v]; }
      }
      const jj = best[i].A, vj = L[i][jj];  // лишний символ
      if (s + vj - PLATE_JUNK > dp[i + 1][t]) { dp[i + 1][t] = s + vj - PLATE_JUNK; bk[i + 1][t] = [t, -1, vj]; }
    }
    let sc = dp[10][n];
    if (sc === NEG) continue;
    let out = '', raw = 0;
    for (let i = 10, t = n; i > 0; i--) {
      const b = bk[i][t];
      raw += b[2];
      if (b[1] >= 0) out = PLATE_ALPHA[b[1]] + out;
      t = b[0];
    }
    // регион «00» не бывает
    if (tpl.startsWith('DD') && out.startsWith('00')) { sc -= 4; raw -= 4; }
    sc -= prior;
    if (!cand || sc > cand.score) cand = { score: sc, raw: raw, plate: out, fmt: tpl };
  }
  // свободное чтение: в каждой позиции самый вероятный символ
  let fs = 0, fp = '';
  for (let k = 0; k < 10; k++) {
    let bj = 0;
    for (let j = 1; j < 37; j++) if (L[k][j] > L[k][bj]) bj = j;
    fs += L[k][bj];
    if (bj !== 36) fp += PLATE_ALPHA[bj];
  }
  if (fp.length >= 4 && (!cand || fs - PLATE_FREE_MARGIN > cand.score)) {
    return { plate: fp, conf: Math.exp(fs / 10), fmt: '' };
  }
  return { plate: cand.plate, conf: Math.exp(cand.raw / 10), fmt: cand.fmt };
}

// красивый вид номера с пробелами
function platePretty(p) {
  p = String(p || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  const m = [
    [/^([0-9]{2})([A-Z])([0-9]{3})([A-Z]{2})$/, '$1 $2 $3 $4'],
    [/^([0-9]{2})([0-9]{3})([A-Z]{3})$/, '$1 $2 $3'],
    [/^([0-9]{2})([A-Z])([0-9]{4})$/, '$1 $2 $3'],
    [/^([0-9]{2})([A-Z])([0-9]{6})$/, '$1 $2 $3'],
    [/^([A-Z])([0-9]{3})([A-Z]{2})([0-9]{2,3})$/, '$1 $2 $3 $4'],
    [/^([0-9]{3})([A-Z]{2,3})([0-9]{2})$/, '$1 $2 $3'],
    [/^([0-9]{4})([A-Z]{2})([0-9]{2})$/, '$1 $2 $3']
  ];
  for (const [re, f] of m) if (re.test(p)) return p.replace(re, f);
  return p;
}
"""


PLATE_SCAN_HTML = r"""<style>
  .plate-wrap #plate { padding-right:58px; }
  .ps-cam-btn {
    position:absolute; right:5px; top:50%; transform:translateY(-50%); width:44px; height:36px; border:none; border-radius:10px;
    background:var(--btn); color:#fff; font-size:16px; display:flex; align-items:center; justify-content:center; cursor:pointer;
    box-shadow:0 3px 8px rgba(230,57,70,.35); padding:0;
  }
  .ps-cam-btn:active { transform:translateY(-50%) scale(.94); }
  #psOverlay { position:fixed; inset:0; z-index:9000; background:#0b0f16; display:none; overflow:hidden; touch-action:none; }
  #psOverlay.open { display:block; }
  #psVideo { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; background:#0b0f16; }
  #psFrame { position:absolute; left:50%; transform:translateX(-50%); border-radius:12px; box-shadow:0 0 0 200vmax rgba(0,0,0,.5); }
  #psFrame b { position:absolute; width:26px; height:26px; border:4px solid #22d3ee; }
  #psFrame .a { left:-2px; top:-2px; border-right:0; border-bottom:0; border-radius:12px 0 0 0; }
  #psFrame .b { right:-2px; top:-2px; border-left:0; border-bottom:0; border-radius:0 12px 0 0; }
  #psFrame .c { left:-2px; bottom:-2px; border-right:0; border-top:0; border-radius:0 0 0 12px; }
  #psFrame .d { right:-2px; bottom:-2px; border-left:0; border-top:0; border-radius:0 0 12px 0; }
  #psFrame .ps-line { position:absolute; left:8px; right:8px; top:50%; height:2px; background:#22d3ee; box-shadow:0 0 12px #22d3ee; animation:psLine 1.6s ease-in-out infinite; }
  @keyframes psLine { 0%,100% { top:15%; } 50% { top:85%; } }
  #psFrame.ps-hit b { border-color:#34d399; }
  /* автопоиск: рамка-подсказка в центре бледная, а найденный номер
     обводится отдельной рамкой, которая сама переезжает на него */
  #psOverlay.auto #psFrame { visibility:hidden; }
  #psBox { position:absolute; left:0; top:0; width:0; height:0; border:3px solid #34d399; border-radius:8px; display:none; pointer-events:none;
           box-shadow:0 0 0 200vmax rgba(0,0,0,.35); transition:left .12s linear, top .12s linear, width .12s linear, height .12s linear; }
  #psOverlay.auto.found #psBox { display:block; }
  #psBox span { position:absolute; left:50%; bottom:calc(100% + 8px); transform:translateX(-50%); white-space:nowrap; background:#34d399; color:#052e1c;
                font-family:var(--font-mono); font-weight:800; font-size:15px; letter-spacing:1px; padding:4px 10px; border-radius:8px; }
  #psBox span:empty { display:none; }
  #psOverlay.result #psBox, #psOverlay.auto.found.result #psBox { display:none; }
  .ps-top { position:absolute; top:0; left:0; right:0; padding:calc(14px + env(safe-area-inset-top, 0px)) 14px 14px; color:#fff; display:flex; justify-content:space-between; align-items:center; font-weight:700; font-size:15px; }
  .ps-ib { width:40px; height:40px; border-radius:50%; background:rgba(255,255,255,.16); color:#fff; border:none; display:flex; align-items:center; justify-content:center; font-size:17px; cursor:pointer; }
  .ps-ib.on { background:#facc15; color:#111; }
  .ps-ib[hidden] { visibility:hidden; display:flex; }
  #psHint { position:absolute; left:16px; right:16px; text-align:center; color:#fff; font-size:14px; font-weight:600; text-shadow:0 1px 3px rgba(0,0,0,.6); }
  #psStatus { position:absolute; left:16px; right:16px; text-align:center; }
  #psStatus span { display:inline-block; background:rgba(34,211,238,.18); color:#a5f3fc; border:1px solid rgba(34,211,238,.4); font-size:13px; padding:7px 14px; border-radius:20px; font-weight:600; max-width:100%; }
  #psTap { position:absolute; left:50%; bottom:calc(120px + env(safe-area-inset-bottom, 0px)); transform:translateX(-50%); white-space:nowrap; z-index:5; border:0; border-radius:16px; background:#22D3EE; color:#062B33; font:inherit; font-size:16px; font-weight:800; padding:16px 22px; display:flex; align-items:center; gap:10px; cursor:pointer; max-width:calc(100% - 40px); }
  #psTap[hidden] { display:none; }
  #psOverlay.result #psTap { display:none; }
  #psStatus.err span { background:rgba(239,68,68,.2); color:#fecaca; border-color:rgba(239,68,68,.5); }
  .ps-bottom { position:absolute; left:0; right:0; bottom:calc(22px + env(safe-area-inset-bottom, 0px)); text-align:center; }
  .ps-manual { background:none; border:none; color:#fff; font-size:14px; text-decoration:underline; opacity:.85; cursor:pointer; padding:8px; font-family:inherit; }
  .ps-priv { color:#cbd5e1; font-size:12px; margin-top:8px; }
  #psSheet { position:absolute; left:0; right:0; bottom:0; background:var(--card, #fff); color:var(--text); border-radius:22px 22px 0 0; padding:14px 16px calc(20px + env(safe-area-inset-bottom, 0px)); box-shadow:0 -8px 24px rgba(0,0,0,.3); display:none; max-width:560px; margin:0 auto; }
  #psOverlay.result #psSheet { display:block; }
  #psOverlay.result #psVideo { filter:blur(4px) brightness(.6); }
  #psOverlay.result #psFrame, #psOverlay.result #psHint, #psOverlay.result #psStatus, #psOverlay.result .ps-bottom { display:none; }
  .ps-grab { width:40px; height:4px; border-radius:2px; background:#cbd5e1; margin:0 auto 12px; }
  .ps-lbl { font-size:11px; color:var(--hint); font-weight:700; text-transform:uppercase; letter-spacing:.5px; }
  .ps-plate-row { display:flex; align-items:center; gap:8px; margin:4px 0 12px; }
  .ps-plate { font-family:var(--font-mono); font-weight:700; font-size:24px; letter-spacing:1.5px; white-space:nowrap; }
  .ps-plate-input { font-family:var(--font-mono); font-weight:700; font-size:20px; letter-spacing:1px; text-transform:uppercase; flex:1; min-width:0; }
  .ps-edit { margin-left:auto; background:none; border:none; color:var(--blue); font-weight:700; font-size:13px; cursor:pointer; white-space:nowrap; font-family:inherit; }
  .ps-match { border-radius:14px; padding:11px 12px; display:flex; gap:10px; align-items:center; margin-bottom:12px; }
  .ps-match.ok { background:var(--ok-bg); border:1.5px solid #a7f3d0; }
  .ps-match.w { background:#FFFBEB; border:1.5px solid #fde68a; }
  .ps-match.n { background:var(--field-bg); border:1.5px solid var(--border); }
  .ps-av { width:40px; height:40px; border-radius:50%; background:var(--blue); color:#fff; font-weight:800; display:flex; align-items:center; justify-content:center; font-size:14px; flex:none; }
  .ps-match.w .ps-av { background:#B45309; }
  .ps-match.n .ps-av { background:#94A3B8; }
  .ps-tag { font-size:10.5px; font-weight:800; margin-bottom:3px; }
  .ps-match.ok .ps-tag { color:var(--ok); } .ps-match.w .ps-tag { color:#B45309; } .ps-match.n .ps-tag { color:var(--hint); }
  .ps-mt { font-size:14px; font-weight:700; }
  .ps-mt.mono { font-family:var(--font-mono); letter-spacing:1px; }
  .ps-ms { font-size:12px; color:#64748b; margin-top:2px; }
  .ps-alt { font-size:12.5px; color:#64748b; margin:-4px 0 12px; }
  .ps-alt b { font-family:var(--font-mono); color:var(--text); }
  .ps-btns { display:flex; gap:8px; }
  .ps-bt { flex:1; border-radius:12px; padding:13px; text-align:center; font-weight:800; font-size:14px; border:none; cursor:pointer; font-family:inherit; }
  .ps-bt.p { background:var(--btn); color:#fff; }
  .ps-bt.s { background:var(--field-bg); color:var(--text); border:1.5px solid var(--border); }
  .ps-lock { text-align:center; font-size:11px; color:var(--hint); margin-top:10px; }
</style>

<div id="psOverlay" role="dialog" aria-modal="true">
  <video id="psVideo" playsinline muted autoplay></video>
  <div id="psFrame"><b class="a"></b><b class="b"></b><b class="c"></b><b class="d"></b><div class="ps-line"></div></div>
  <div id="psBox"><span></span></div>
  <div class="ps-top">
    <button type="button" class="ps-ib" onclick="closePlateScanner()" aria-label="close"><i class="fa-solid fa-xmark"></i></button>
    <div>{{ T.ps_title }}</div>
    <button type="button" class="ps-ib" id="psTorch" onclick="psToggleTorch()" hidden aria-label="{{ T.ps_torch }}"><i class="fa-solid fa-bolt"></i></button>
  </div>
  <div id="psHint">{{ T.ps_hint }}</div>
  <div id="psStatus"><span></span></div>
  <button type="button" id="psTap" hidden onclick="psTapStart()"><i class="fa-solid fa-camera"></i> {{ T.ps_tap_start }}</button>
  <div class="ps-bottom">
    <button type="button" class="ps-manual" onclick="psManual()">{{ T.ps_manual }}</button>
    <div class="ps-priv"><i class="fa-solid fa-lock"></i> {{ T.ps_privacy }}</div>
  </div>
  <div id="psSheet"></div>
  <canvas id="psCanvas" width="128" height="64" style="display:none;"></canvas>
  <canvas id="psDetCanvas" width="384" height="384" style="display:none;"></canvas>
</div>

<script>
// ===== Сканер госномера =====
// Распознавание идёт прямо на телефоне (ONNX-модель в браузере): кадры с
// камеры никуда не отправляются и нигде не сохраняются, сервер только один
// раз отдаёт файлы модели (/ocr/v1/…), дальше они берутся из кэша.
// Форматы номеров и расшифровка ответа модели — в plateDecode() (PLATE_DECODE_JS).
/*__PLATE_DECODE_JS__*/
const PS = { stream: null, track: null, session: null, loading: null, running: false, timer: null,
             hits: {}, startedAt: 0, result: null, torch: false, editing: false, gen: 0 };
const PS_MIN_CONF = 0.55;     // кадр учитывается, если модель уверена хотя бы на столько
const PS_NEED_HITS = 2;       // сколько раз подряд должен прочитаться один и тот же номер
const PS_INSTANT_CONF = 0.97; // при такой уверенности хватает одного кадра
const PS_BASE_CONF = 0.5;     // для номера, который уже есть в базе, достаточно такой
const PS_DET = 256;           // размер кадра для «искателя» (облегчённая модель — быстрее на телефоне)
const PS_DET_MIN = 0.4;       // с какой уверенности «искатель» считает, что это номер

function psLoadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src; s.onload = resolve; s.onerror = () => reject(new Error('load ' + src));
    document.head.appendChild(s);
  });
}

function psLoadModel() {
  if (PS.session) return Promise.resolve(PS.session);
  if (!PS.loading) {
    PS.loading = (async () => {
      if (!window.ort) await psLoadScript('/ocr/v1/ort.wasm.min.js');
      ort.env.wasm.wasmPaths = '/ocr/v1/';
      ort.env.wasm.numThreads = 1;
      const sess = await ort.InferenceSession.create('/ocr/v1/plate_ocr_uz.onnx', { executionProviders: ['wasm'] });
      // «прогрев»: первый прогон всегда медленный — делаем его заранее
      try { await sess.run({ [sess.inputNames[0]]: new ort.Tensor('uint8', new Uint8Array(64 * 128 * 3), [1, 64, 128, 3]) }); } catch (e) {}
      PS.session = sess;
      return sess;
    })().catch(e => { PS.loading = null; throw e; });
  }
  return PS.loading;
}

// «искатель» номера: маленькая YOLO-модель смотрит на весь кадр и говорит,
// где номер. Работает в ОТДЕЛЬНОМ потоке (Web Worker), поэтому не тормозит
// обычное чтение: оно идёт каждый кадр, как раньше, а «искатель» в это время
// сам по себе ищет номер и подсказывает, где он. Если поток не запустился
// (старый телефон) — сканер просто работает по рамке в центре.
const PS_DET_WORKER = `
let sess = null, S = 256;
self.onmessage = async (e) => {
  const m = e.data;
  if (m.type === 'init') {
    try {
      S = m.size;
      importScripts(m.base + 'ort.wasm.min.js');
      ort.env.wasm.wasmPaths = m.base;
      ort.env.wasm.numThreads = 1;
      sess = await ort.InferenceSession.create(m.base + 'plate_det_s256.onnx', { executionProviders: ['wasm'] });
      try { await sess.run({ [sess.inputNames[0]]: new ort.Tensor('float32', new Float32Array(3 * S * S), [1, 3, S, S]) }); } catch (x) {}
      self.postMessage({ type: 'ready' });
    } catch (err) {
      self.postMessage({ type: 'fail', err: String(err) });
    }
    return;
  }
  if (m.type === 'frame' && sess) {
    const t0 = Date.now();
    const px = new Uint8ClampedArray(m.buf), n = S * S, f = new Float32Array(3 * n);
    for (let i = 0, j = 0; j < n; i += 4, j++) { f[j] = px[i] / 255; f[n + j] = px[i + 1] / 255; f[2 * n + j] = px[i + 2] / 255; }
    let boxes = [];
    try {
      const out = await sess.run({ [sess.inputNames[0]]: new ort.Tensor('float32', f, [1, 3, S, S]) });
      const d = out[sess.outputNames[0]].data;
      for (let k = 0; k + 6 < d.length; k += 7) boxes.push([d[k + 1], d[k + 2], d[k + 3], d[k + 4], d[k + 6]]);
    } catch (x) { boxes = []; }
    self.postMessage({ type: 'boxes', id: m.id, boxes, ms: Date.now() - t0 });
  }
};`;

function psInitDetector() {
  if (PS.detWorker || PS.detFailed) return;
  try {
    const url = URL.createObjectURL(new Blob([PS_DET_WORKER], { type: 'text/javascript' }));
    const w = new Worker(url);
    PS.detWorker = w;
    w.onmessage = e => psOnDetMessage(e.data);
    w.onerror = () => psDetFail();
    w.postMessage({ type: 'init', base: location.origin + '/ocr/v1/', size: PS_DET });
  } catch (e) {
    psDetFail();
  }
}
function psDetFail() {
  PS.detFailed = true; PS.det = false; PS.detBusy = false;
  try { if (PS.detWorker) PS.detWorker.terminate(); } catch (e) {}
  PS.detWorker = null;
  // без «искателя» — обычная рамка в центре, как раньше
  const ov = document.getElementById('psOverlay');
  if (ov) ov.classList.remove('auto', 'found');
  const h = document.getElementById('psHint');
  if (h && ov && ov.classList.contains('open') && !ov.classList.contains('result')) h.textContent = T.ps_hint;
}
function psOnDetMessage(m) {
  if (m.type === 'ready') { PS.det = true; psDetPump(); return; }
  if (m.type === 'fail') { psDetFail(); return; }
  if (m.type !== 'boxes') return;
  PS.detBusy = false;
  const map = PS.detMap;
  if (map && m.id === map.id && PS.running) psOnBoxes(m.boxes, map);
  // следующий кадр «искателю» — когда освободится, без очереди
  if (PS.running) setTimeout(psDetPump, 0);
}

// кадр камеры → «искателю»: весь кадр вписан в квадрат с серыми полями
function psDetPump() {
  if (!PS.det || PS.detBusy || !PS.running || !PS.detWorker) return;
  const v = document.getElementById('psVideo');
  const vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || !vh) { setTimeout(psDetPump, 100); return; }
  const S = PS_DET, r = Math.min(S / vw, S / vh);
  const nw = Math.round(vw * r), nh = Math.round(vh * r);
  const dx = Math.round((S - nw) / 2), dy = Math.round((S - nh) / 2);
  const c = document.getElementById('psDetCanvas');
  if (c.width !== S) { c.width = S; c.height = S; }
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.fillStyle = 'rgb(114,114,114)';
  ctx.fillRect(0, 0, S, S);
  ctx.drawImage(v, 0, 0, vw, vh, dx, dy, nw, nh);
  const buf = ctx.getImageData(0, 0, S, S).data.buffer;
  PS.detSeq = (PS.detSeq || 0) + 1;
  PS.detMap = { id: PS.detSeq, r, dx, dy, vw, vh };
  PS.detBusy = true;
  PS.detWorker.postMessage({ type: 'frame', id: PS.detSeq, buf }, [buf]);
}

// ответ «искателя»: выбираем номер (самый уверенный, при равенстве — ближе
// к центру и крупнее) и ставим на него рамку
function psOnBoxes(boxes, map) {
  let best = null, bestRank = 0;
  for (const bx of boxes) {
    const sc = bx[4];
    if (sc < PS_DET_MIN) continue;
    const x1 = (bx[0] - map.dx) / map.r, y1 = (bx[1] - map.dy) / map.r;
    const x2 = (bx[2] - map.dx) / map.r, y2 = (bx[3] - map.dy) / map.r;
    const cx = (x1 + x2) / 2 / map.vw - 0.5, cy = (y1 + y2) / 2 / map.vh - 0.5;
    const area = Math.max(0, x2 - x1) * Math.max(0, y2 - y1) / (map.vw * map.vh);
    const rank = sc + Math.min(area * 4, 0.15) - Math.min(Math.hypot(cx, cy) * 0.3, 0.2);
    if (rank > bestRank && x2 - x1 >= 12 && y2 - y1 >= 5) { bestRank = rank; best = { x1, y1, x2, y2, score: sc }; }
  }
  if (!best) {
    // номер пропал на кадр-другой (блик, тряска) — держим рамку, потом прячем
    PS.lost = (PS.lost || 0) + 1;
    if (PS.lost > 2) { PS.box = null; PS.boxSmall = false; psShowBox(null); }
    return;
  }
  if (PS.box) {  // сглаживаем, чтобы рамка не дёргалась
    const k = 0.6;
    best = { x1: PS.box.x1 + (best.x1 - PS.box.x1) * k, y1: PS.box.y1 + (best.y1 - PS.box.y1) * k,
             x2: PS.box.x2 + (best.x2 - PS.box.x2) * k, y2: PS.box.y2 + (best.y2 - PS.box.y2) * k, score: best.score };
  }
  PS.box = best; PS.lost = 0; PS.boxAt = Date.now();
  // мелкий номер (далеко) читается с ошибками — просим подойти ближе
  PS.boxSmall = (best.x2 - best.x1) < map.vw * 0.12;
  psShowBox(best);
}

function psSetStatus(text, isErr) {
  const st = document.getElementById('psStatus');
  st.classList.toggle('err', !!isErr);
  st.style.display = text ? '' : 'none';
  st.querySelector('span').textContent = text || '';
}

// рамка: ширина ~86% экрана (не больше 440px), пропорции как у номера с запасом
function psLayout() {
  const ov = document.getElementById('psOverlay');
  const W = ov.clientWidth, H = ov.clientHeight;
  const fw = Math.min(W * 0.86, 440), fh = Math.round(fw / 3.2);
  const top = Math.round(H * 0.42 - fh / 2);
  const fr = document.getElementById('psFrame');
  fr.style.width = Math.round(fw) + 'px'; fr.style.height = fh + 'px'; fr.style.top = top + 'px';
  document.getElementById('psHint').style.top = (top - 40) + 'px';
  document.getElementById('psStatus').style.top = (top + fh + 22) + 'px';
}

async function openPlateScanner() {
  const ov = document.getElementById('psOverlay');
  PS.gen++;
  PS.result = null; PS.editing = false; PS.hits = {};
  ov.classList.remove('result', 'found');
  // рамки в центре нет: номер ищется по всему кадру (если «искатель» доступен)
  ov.classList.toggle('auto', !PS.detFailed && typeof Worker !== 'undefined');
  PS.box = null; PS.lost = 0; PS.boxSmall = false; PS.detBusy = false;
  ov.classList.add('open');
  document.body.style.overflow = 'hidden';
  document.getElementById('psFrame').classList.remove('ps-hit');
  document.getElementById('psHint').textContent = ov.classList.contains('auto') ? T.ps_hint_auto : T.ps_hint;
  psLayout();
  ensureCarsCacheLoaded().then(psBuildPlateSet);
  psBuildPlateSet();
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    psSetStatus(T.ps_no_camera, true);
    return;
  }
  psSetStatus(PS.session ? T.ps_scanning : T.ps_loading);
  const gen = PS.gen;
  const modelP = psLoadModel();
  psInitDetector();
  try {
    await psStartCamera();
    // iPhone иногда отдаёт «пустую» камеру: картинки нет, хотя доступ дан
    // (первый запуск после разрешения, режим энергосбережения, камера
    // занята). Проверяем, что кадры правда идут, и чиним сами.
    if (!(await psVideoAlive(2500))) {
      if (gen !== PS.gen) return;
      const v = document.getElementById('psVideo');
      if (v.paused) {
        // видео не запустилось само — нужно нажатие пальцем
        document.getElementById('psTap').hidden = false;
        psSetStatus(T.ps_tap_hint);
        const ok = await new Promise(r => { PS.tapResolve = r; });
        if (gen !== PS.gen) return;
        if (!ok) { psSetStatus(T.ps_black, true); return; }
      }
      if (!(await psVideoAlive(1500))) {
        if (gen !== PS.gen) return;
        // перезапуск камеры — помогает при первом запуске на iPhone
        psStopCamera();
        await psStartCamera();
        if (!(await psVideoAlive(3000))) {
          if (gen !== PS.gen) return;
          psSetStatus(T.ps_black, true);
          return;
        }
      }
    }
  } catch (e) {
    if (gen !== PS.gen) return;
    const denied = e && (e.name === 'NotAllowedError' || e.name === 'SecurityError');
    const busy = e && (e.name === 'NotReadableError' || e.name === 'AbortError' || e.name === 'TrackStartError');
    psSetStatus(denied ? T.ps_denied : (busy ? T.ps_black : T.ps_no_camera), true);
    return;
  }
  try {
    await modelP;
  } catch (e) {
    if (gen !== PS.gen) return;
    psSetStatus(T.ps_load_fail, true);
    return;
  }
  if (gen !== PS.gen || !ov.classList.contains('open')) return;
  psSetStatus(T.ps_scanning);
  PS.running = true;
  PS.startedAt = Date.now();
  psTick(gen);
  psDetPump();
}

async function psStartCamera() {
  if (PS.stream) return;
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    // без жёсткого разрешения: камера включается быстрее, а модели хватает
    // и обычного качества (номер всё равно ужимается до 128×64)
    // «искателю» нужен чёткий кадр: просим HD (если камера не умеет — даст что может)
    video: PS.det || !PS.detFailed
      ? { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }
      : { facingMode: { ideal: 'environment' } }
  });
  if (!document.getElementById('psOverlay').classList.contains('open')) {
    stream.getTracks().forEach(t => t.stop());
    return;
  }
  PS.stream = stream;
  PS.track = stream.getVideoTracks()[0] || null;
  const v = document.getElementById('psVideo');
  v.srcObject = stream;
  try { await v.play(); } catch (e) {}
  if (PS.track) PS.track.onended = () => { if (PS.stream === stream) psSetStatus(T.ps_black, true); };
  // фонарик — только если телефон умеет
  PS.torch = false;
  const tb = document.getElementById('psTorch');
  tb.classList.remove('on');
  let caps = {};
  try { caps = PS.track && PS.track.getCapabilities ? PS.track.getCapabilities() : {}; } catch (e) {}
  tb.hidden = !caps.torch;
}

// идут ли кадры с камеры: видео играет, размер известен и время двигается
async function psVideoAlive(ms) {
  const v = document.getElementById('psVideo');
  const t0 = Date.now();
  let lastT = v.currentTime;
  while (Date.now() - t0 < ms) {
    await new Promise(r => setTimeout(r, 200));
    if (!document.getElementById('psOverlay').classList.contains('open')) return false;
    if (!v.paused && v.videoWidth > 0 && v.readyState >= 2 && v.currentTime !== lastT) return true;
    lastT = v.currentTime;
  }
  return false;
}

async function psTapStart() {
  const v = document.getElementById('psVideo');
  document.getElementById('psTap').hidden = true;
  let ok = true;
  try { await v.play(); } catch (e) { ok = false; }
  if (PS.tapResolve) { const r = PS.tapResolve; PS.tapResolve = null; r(ok); }
}

function psBuildPlateSet() {
  PS.plateSet = new Set((carsCache || []).map(c => psNorm(c.plate_number)));
}

function psStopCamera() {
  PS.running = false;
  if (PS.timer) { clearTimeout(PS.timer); PS.timer = null; }
  if (PS.stream) PS.stream.getTracks().forEach(t => t.stop());
  PS.stream = null; PS.track = null;
  const v = document.getElementById('psVideo');
  if (v) v.srcObject = null;
}

async function psToggleTorch() {
  if (!PS.track) return;
  PS.torch = !PS.torch;
  try { await PS.track.applyConstraints({ advanced: [{ torch: PS.torch }] }); }
  catch (e) { PS.torch = false; }
  document.getElementById('psTorch').classList.toggle('on', PS.torch);
}

function closePlateScanner() {
  PS.gen++;
  const tap = document.getElementById('psTap');
  if (tap) tap.hidden = true;
  if (PS.tapResolve) { const r = PS.tapResolve; PS.tapResolve = null; r(false); }
  psStopCamera();
  const ov = document.getElementById('psOverlay');
  ov.classList.remove('open', 'result', 'found');
  PS.box = null;
  document.getElementById('psSheet').innerHTML = '';
  document.body.style.overflow = '';
}

function psManual() {
  closePlateScanner();
  const el = document.getElementById('plate');
  if (el) el.focus();
}

// часть кадра под рамкой → тензор 1×64×128×3 (uint8, RGB)
function psCropTensor(inset) {
  const v = document.getElementById('psVideo');
  const vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || !vh) return null;
  const ew = v.clientWidth, eh = v.clientHeight;
  const scale = Math.max(ew / vw, eh / vh);
  const offX = (vw * scale - ew) / 2, offY = (vh * scale - eh) / 2;
  const fr = document.getElementById('psFrame').getBoundingClientRect();
  const vr = v.getBoundingClientRect();
  let fx = fr.left - vr.left, fy = fr.top - vr.top, fw = fr.width, fh = fr.height;
  fx += fw * inset[0]; fw *= (1 - 2 * inset[0]);
  fy += fh * inset[1]; fh *= (1 - 2 * inset[1]);
  const sx = (fx + offX) / scale, sy = (fy + offY) / scale, sw = fw / scale, sh = fh / scale;
  const c = document.getElementById('psCanvas');
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(v, sx, sy, sw, sh, 0, 0, 128, 64);
  const px = ctx.getImageData(0, 0, 128, 64).data;
  const rgb = new Uint8Array(128 * 64 * 3);
  for (let i = 0, j = 0; i < px.length; i += 4, j += 3) { rgb[j] = px[i]; rgb[j + 1] = px[i + 1]; rgb[j + 2] = px[i + 2]; }
  return new ort.Tensor('uint8', rgb, [1, 64, 128, 3]);
}

function psDecode(probs) { return plateDecode(probs); }

// найденный номер (в пикселях видео) → тензор для модели чтения, с запасом
// вокруг (pad — доля ширины/высоты), прямо из полного кадра камеры
function psBoxTensor(b, pad) {
  const v = document.getElementById('psVideo');
  const w = b.x2 - b.x1, h = b.y2 - b.y1;
  const sx = Math.max(0, b.x1 - w * pad[0]), sy = Math.max(0, b.y1 - h * pad[1]);
  const ex = Math.min(v.videoWidth, b.x2 + w * pad[0]), ey = Math.min(v.videoHeight, b.y2 + h * pad[1]);
  if (ex - sx < 4 || ey - sy < 2) return null;
  const c = document.getElementById('psCanvas');
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(v, sx, sy, ex - sx, ey - sy, 0, 0, 128, 64);
  const px = ctx.getImageData(0, 0, 128, 64).data;
  const rgb = new Uint8Array(128 * 64 * 3);
  for (let i = 0, j = 0; i < px.length; i += 4, j += 3) { rgb[j] = px[i]; rgb[j + 1] = px[i + 1]; rgb[j + 2] = px[i + 2]; }
  return new ort.Tensor('uint8', rgb, [1, 64, 128, 3]);
}

// рамка на экране поверх найденного номера (видео растянуто «cover»)
function psShowBox(b, label) {
  const v = document.getElementById('psVideo');
  const ov = document.getElementById('psOverlay');
  const box = document.getElementById('psBox');
  if (!b) {
    ov.classList.remove('found');
    box.querySelector('span').textContent = '';
    return;
  }
  const ew = v.clientWidth, eh = v.clientHeight, vw = v.videoWidth, vh = v.videoHeight;
  const scale = Math.max(ew / vw, eh / vh);
  const offX = (vw * scale - ew) / 2, offY = (vh * scale - eh) / 2;
  const padX = (b.x2 - b.x1) * 0.06, padY = (b.y2 - b.y1) * 0.18;
  box.style.left = Math.round((b.x1 - padX) * scale - offX) + 'px';
  box.style.top = Math.round((b.y1 - padY) * scale - offY) + 'px';
  box.style.width = Math.round((b.x2 - b.x1 + 2 * padX) * scale) + 'px';
  box.style.height = Math.round((b.y2 - b.y1 + 2 * padY) * scale) + 'px';
  if (label !== undefined) box.querySelector('span').textContent = label;
  ov.classList.add('found');
}

async function psRecognize() {
  const sess = PS.session;
  PS.tickN = (PS.tickN || 0) + 1;
  // чтение идёт каждый кадр, как раньше. Если «искатель» недавно нашёл номер —
  // читаем его место (два варианта запаса вокруг), а каждый третий кадр —
  // центр экрана: номер, наведённый в центр, читается без ожидания «искателя»
  const boxFresh = PS.box && Date.now() - (PS.boxAt || 0) < 900;
  let t = null, fromBox = false;
  if (boxFresh && PS.tickN % 3 !== 0) {
    t = psBoxTensor(PS.box, PS.tickN % 3 === 1 ? [0.08, 0.2] : [0.03, 0.1]);
    fromBox = true;
  }
  if (!t) t = psCropTensor(PS.tickN % 2 ? [0, 0] : [0.06, 0.14]);
  if (!t) return null;
  const out = await sess.run({ [sess.inputNames[0]]: t });
  const r = psDecode(out[sess.outputNames[0]].data);
  if (r) r.fromBox = fromBox;
  if (r && fromBox && r.fmt && r.conf >= 0.9) psShowBox(PS.box, psPretty(r.plate));
  return r;
}

async function psTick(gen) {
  if (gen !== PS.gen || !PS.running) return;
  let r = null;
  try { r = await psRecognize(); } catch (e) { r = null; }
  if (gen !== PS.gen || !PS.running) return;
  if (r && r.conf >= PS_MIN_CONF) {
    PS.hits[r.plate] = (PS.hits[r.plate] || 0) + 1;
    document.getElementById('psFrame').classList.add('ps-hit');
    // номер уже есть в базе этой точки — хватает одного уверенного кадра
    const inBase = r.conf >= PS_BASE_CONF && PS.plateSet && PS.plateSet.has(r.plate);
    // далёкий мелкий номер: только если уверенно и три раза подряд одинаково
    const smallOk = !(r.fromBox && PS.boxSmall) || (r.fmt && r.conf >= 0.8 && PS.hits[r.plate] >= 3);
    if (PS.boxSmall) document.getElementById('psHint').textContent = T.ps_closer;
    if (smallOk && (inBase || r.conf >= PS_INSTANT_CONF || PS.hits[r.plate] >= PS_NEED_HITS)) {
      if (navigator.vibrate) { try { navigator.vibrate(60); } catch (e) {} }
      psShowResult(r.plate);
      return;
    }
  } else {
    document.getElementById('psFrame').classList.remove('ps-hit');
    if (PS.boxSmall) document.getElementById('psHint').textContent = T.ps_closer;
  }
  if (PS.det && !PS.boxSmall && document.getElementById('psHint').textContent === T.ps_closer) {
    document.getElementById('psHint').textContent = T.ps_hint_auto;
  }
  if (Date.now() - PS.startedAt > 8000 && !PS.boxSmall) document.getElementById('psHint').textContent = PS.det ? T.ps_hint_slow_auto : T.ps_hint_slow;
  psNextFrame(gen);
}

// следующий кадр — сразу, как камера даст новый (без лишних пауз)
function psNextFrame(gen) {
  const v = document.getElementById('psVideo');
  if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(() => psTick(gen));
  else PS.timer = setTimeout(() => psTick(gen), 30);
}

// ---- результат ----
function psNorm(s) { return String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, ''); }
function psPretty(p) { return platePretty(p); }
function psDist(a, b) {
  if (Math.abs(a.length - b.length) > 1) return 9;
  const d = [];
  for (let i = 0; i <= a.length; i++) { d.push([i]); }
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length];
}
function psFindCar(plate) {
  const p = psNorm(plate);
  if (!p) return { kind: 'none' };
  let near = null;
  for (const c of (carsCache || [])) {
    const cp = psNorm(c.plate_number);
    if (cp === p) return { kind: 'exact', car: c };
    if (!near && cp.length >= 6 && psDist(cp, p) === 1) near = c;
  }
  return near ? { kind: 'near', car: near } : { kind: 'none' };
}
function psInitials(name) {
  return String(name || '').trim().split(' ').filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?';
}
function psDate(s) {
  const m = String(s || '').slice(0, 10).split('-');
  return m.length === 3 ? m[2] + '.' + m[1] + '.' + m[0] : '';
}
function psCarLine(c) {
  const parts = [[c.car_brand, c.car_model].filter(Boolean).join(' ')];
  const d = psDate(c.change_date);
  if (d) parts.push(T.ps_last + ' ' + d);
  return parts.filter(Boolean).join(' · ');
}

function psShowResult(plate) {
  psStopCamera();
  PS.result = psNorm(plate);
  PS.editing = false;
  document.getElementById('psOverlay').classList.add('result');
  psRenderSheet();
}

function psRenderSheet() {
  const sheet = document.getElementById('psSheet');
  const plate = PS.result;
  const m = psFindCar(plate);
  PS.match = m;
  const plateHtml = PS.editing
    ? `<input id="psPlateInput" class="ps-plate-input" value="${escapeHtml(plate)}" autocomplete="off" autocapitalize="characters" spellcheck="false" oninput="psOnEdit(this)">`
    : `<span class="ps-plate">${escapeHtml(psPretty(plate))}</span><button type="button" class="ps-edit" onclick="psStartEdit()"><i class="fa-solid fa-pen"></i> ${escapeHtml(T.ps_edit)}</button>`;
  sheet.innerHTML = `
    <div class="ps-grab"></div>
    <div class="ps-lbl">${escapeHtml(T.ps_recognized)}</div>
    <div class="ps-plate-row">${plateHtml}</div>
    <div id="psMatchBox">${psMatchHtml(m, plate)}</div>
    <div class="ps-lock"><i class="fa-solid fa-lock"></i> ${escapeHtml(T.ps_on_phone)}</div>`;
  if (PS.editing) {
    const inp = document.getElementById('psPlateInput');
    inp.focus();
    try { inp.setSelectionRange(inp.value.length, inp.value.length); } catch (e) {}
  }
}

function psMatchHtml(m, plate) {
  if (m.kind === 'exact') {
    const c = m.car;
    return `<div class="ps-match ok"><div class="ps-av">${escapeHtml(psInitials(c.owner_name))}</div><div style="min-width:0;">
        <div class="ps-tag"><i class="fa-solid fa-circle-check"></i> ${escapeHtml(T.ps_in_base)}</div>
        <div class="ps-mt">${escapeHtml(c.owner_name || T.kc_no_name)}</div>
        <div class="ps-ms">${escapeHtml(psCarLine(c))}</div></div></div>
      <div class="ps-btns"><button type="button" class="ps-bt s" onclick="openPlateScanner()"><i class="fa-solid fa-rotate"></i> ${escapeHtml(T.ps_again)}</button>
        <button type="button" class="ps-bt p" onclick="psApply(PS.match.car.plate_number)">${escapeHtml(T.ps_use)}</button></div>`;
  }
  if (m.kind === 'near') {
    const c = m.car;
    return `<div class="ps-match w"><div class="ps-av">${escapeHtml(psInitials(c.owner_name))}</div><div style="min-width:0;">
        <div class="ps-tag"><i class="fa-solid fa-circle-question"></i> ${escapeHtml(T.ps_maybe)}</div>
        <div class="ps-mt mono">${escapeHtml(psPretty(c.plate_number))}</div>
        <div class="ps-ms">${escapeHtml([c.owner_name, [c.car_brand, c.car_model].filter(Boolean).join(' ')].filter(Boolean).join(' · '))}</div></div></div>
      <div class="ps-alt">${escapeHtml(T.ps_or_new)} <b>${escapeHtml(plate)}</b></div>
      <div class="ps-btns"><button type="button" class="ps-bt s" onclick="psApply(PS.result)">${escapeHtml(T.ps_new_btn)}</button>
        <button type="button" class="ps-bt p" onclick="psApply(PS.match.car.plate_number)">${escapeHtml(T.ps_its_him)}</button></div>`;
  }
  return `<div class="ps-match n"><div class="ps-av"><i class="fa-solid fa-plus"></i></div><div>
        <div class="ps-tag">${escapeHtml(T.ps_new)}</div>
        <div class="ps-ms">${escapeHtml(T.ps_new_hint)}</div></div></div>
      <div class="ps-btns"><button type="button" class="ps-bt s" onclick="openPlateScanner()"><i class="fa-solid fa-rotate"></i> ${escapeHtml(T.ps_again)}</button>
        <button type="button" class="ps-bt p" onclick="psApply(PS.result)">${escapeHtml(T.ps_use)}</button></div>`;
}

function psStartEdit() { PS.editing = true; psRenderSheet(); }
function psOnEdit(inp) {
  const v = psNorm(inp.value);
  if (inp.value !== v) inp.value = v;
  PS.result = v;
  PS.match = psFindCar(v);
  document.getElementById('psMatchBox').innerHTML = psMatchHtml(PS.match, v);
}

function psApply(plate) {
  const p = psNorm(plate);
  if (!p) return;
  closePlateScanner();
  const el = document.getElementById('plate');
  el.value = p;
  const dd = document.getElementById('plateSuggest');
  if (dd) { dd.style.display = 'none'; dd.innerHTML = ''; }
  lookupPlate(true);
}

// ---------- Карточка мастера: машина у въезда (сканер / камера табло) ----------
// Сканер у въезда узнал номер — мастер сразу видит, кто подъехал и что
// предложить, и одним нажатием открывает клиента в форме замены.
let ARRIVAL_LAST = null;  // at последней показанной машины; null — ещё не спрашивали
async function pollArrival() {
  if (document.visibilityState === 'visible') {
    try {
      const d = await (await fetch('/api/arrival?after=' + (ARRIVAL_LAST || 0), { credentials: 'same-origin' })).json();
      const a = d && d.ok ? d.arrival : null;
      // первый ответ после открытия панели не показываем — это могла быть
      // машина, которая подъехала до того, как панель открыли
      if (ARRIVAL_LAST === null) ARRIVAL_LAST = a ? a.at : 0;
      else if (a && a.at > ARRIVAL_LAST) { ARRIVAL_LAST = a.at; showArrival(a); }
    } catch (e) {}
  }
  setTimeout(pollArrival, 5000);
}
function showArrival(a) {
  let box = document.getElementById('arrivalCard');
  if (!box) {
    box = document.createElement('div');
    box.id = 'arrivalCard';
    box.style.cssText = 'position:fixed; top:12px; left:50%; transform:translateX(-50%); z-index:9999; width:min(560px, calc(100% - 24px)); background:#0A2540; color:#fff; border-radius:16px; padding:14px 16px; box-shadow:0 12px 32px rgba(0,0,0,.28); font-size:15px; line-height:1.4;';
    document.body.appendChild(box);
  }
  const who = a.found ? escapeHtml(a.owner_name || T.kc_no_name) : escapeHtml(T.arr_new_client);
  const rec = a.rec_item
    ? `<div style="margin-top:6px; color:#FFD23F;">💡 ${escapeHtml(T.arr_rec)} <b>${escapeHtml(a.rec_item)}</b>${a.offer_pct ? ' · ' + escapeHtml(T.arr_offer.replace('{pct}', a.offer_pct)) : ''}</div>`
    : '';
  box.innerHTML = `<div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start;">
      <div style="min-width:0;">
        <div style="font-weight:700;">🚗 ${escapeHtml(T.arr_title)} <span style="font-family:ui-monospace, Menlo, Consolas, monospace; letter-spacing:1px;">${escapeHtml(psPretty(a.plate))}</span></div>
        <div style="opacity:.85; margin-top:2px;">${who}</div>${rec}
      </div>
      <button type="button" onclick="hideArrival()" aria-label="close" style="flex:none; background:none; border:none; color:#fff; font-size:22px; line-height:1; cursor:pointer;">×</button>
    </div>
    <button type="button" onclick="openArrival(${escapeHtml(JSON.stringify(a.plate))})" style="margin-top:10px; height:40px; padding:0 16px; border-radius:10px; border:none; background:#3FBE7E; color:#00140A; font-weight:700; font-size:14px; font-family:inherit; cursor:pointer;">${escapeHtml(T.arr_open)}</button>`;
  box.style.display = 'block';
  if (navigator.vibrate) { try { navigator.vibrate([80, 60, 80]); } catch (e) {} }
  clearTimeout(window.ARRIVAL_TIMER);
  window.ARRIVAL_TIMER = setTimeout(hideArrival, 90000);
}
function hideArrival() {
  const b = document.getElementById('arrivalCard');
  if (b) b.style.display = 'none';
}
function openArrival(plate) {
  hideArrival();
  showTab('add');
  psApply(plate);
}
setTimeout(pollArrival, 1500);

// заранее, в фоне, загружаем распознавание — к нажатию 📷 оно уже готово
// (файлы берутся из кэша телефона, интернет тратится только первый раз)
window.addEventListener('load', () => {
  if (!document.getElementById('plate') || !navigator.mediaDevices) return;
  const go = () => psLoadModel().catch(() => {});
  setTimeout(() => (window.requestIdleCallback ? requestIdleCallback(go, { timeout: 4000 }) : go()), 2500);
});

window.addEventListener('resize', () => { if (document.getElementById('psOverlay').classList.contains('open')) psLayout(); });
document.addEventListener('visibilitychange', () => {
  // свернули приложение — камеру выключаем (батарея и приватность)
  if (document.hidden && PS.stream) closePlateScanner();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.getElementById('psOverlay').classList.contains('open')) closePlateScanner();
});
</script>
"""


VIN_SCAN_HTML = r"""<style>
  .vin-wrap #vin { padding-right:58px; font-family:var(--font-mono); letter-spacing:.5px; text-transform:uppercase; }
  .vin-wrap #vin::placeholder { text-transform:none; letter-spacing:0; font-family:inherit; }
  .vin-hint { margin-top:6px; font-size:12.5px; color:#5b6b8c; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
  .vin-hint.err { color:#b91c1c; }
  .vin-hint button { border:1px solid #cfe0fb; background:#fff; color:#1d4ed8; border-radius:999px; padding:3px 10px; font-size:12px; font-weight:700; cursor:pointer; font-family:inherit; }
  .oil-lesson { display:flex; align-items:center; gap:10px; margin-top:10px; padding:10px 12px; border-radius:12px; background:#EEF4FF; border:1px solid #CFE0FB; color:#1D4ED8; font-size:13.5px; font-weight:600; text-decoration:none; }
  .oil-lesson span { flex:1; }
  .oil-lesson .fa-chevron-right { font-size:11px; opacity:.7; }
  .qm-row { display:flex; gap:6px; overflow-x:auto; padding:2px 0 6px; margin:8px 0 0; scrollbar-width:none; -webkit-overflow-scrolling:touch; }
  .qm-row::-webkit-scrollbar { display:none; }
  .qm-chip { flex:none; border:1.5px solid var(--border); background:var(--field-bg); color:var(--text); border-radius:999px; padding:7px 13px; font-size:13.5px; font-weight:700; cursor:pointer; font-family:inherit; white-space:nowrap; }
  .qm-chip.on { border-color:#1d4ed8; background:#eaf1ff; color:#1d4ed8; }
  #vsOverlay { position:fixed; inset:0; z-index:9001; background:#0b0f16; display:none; overflow:hidden; }
  #vsOverlay.open { display:block; }
  #vsPhotoBox { position:absolute; left:0; right:0; top:calc(64px + env(safe-area-inset-top, 0px)); bottom:0; display:flex; align-items:flex-start; justify-content:center; overflow:hidden; }
  #vsImg { max-width:100%; max-height:62vh; object-fit:contain; touch-action:manipulation; }
  #vsOverlay.tap #vsImg { cursor:crosshair; outline:3px solid #facc15; }
  #vsStatus { position:absolute; left:16px; right:16px; top:calc(64px + 62vh + 16px); text-align:center; }
  #vsStatus span { display:inline-block; background:rgba(34,211,238,.18); color:#a5f3fc; border:1px solid rgba(34,211,238,.4); font-size:13px; padding:7px 14px; border-radius:20px; font-weight:600; max-width:100%; }
  #vsStatus.err span { background:rgba(250,204,21,.18); color:#fde68a; border-color:rgba(250,204,21,.5); }
  #vsSheet { position:absolute; left:0; right:0; bottom:0; background:var(--card, #fff); color:var(--text); border-radius:22px 22px 0 0; padding:14px 16px calc(20px + env(safe-area-inset-bottom, 0px)); box-shadow:0 -8px 24px rgba(0,0,0,.3); display:none; max-width:560px; margin:0 auto; max-height:80vh; overflow-y:auto; }
  #vsOverlay.result #vsSheet { display:block; }
  #vsOverlay.result #vsStatus { display:none; }
  .vs-vin { font-family:var(--font-mono); font-weight:700; font-size:19px; letter-spacing:1px; width:100%; text-transform:uppercase; }
  .vs-info { display:grid; grid-template-columns:auto minmax(0,1fr); gap:4px 12px; margin:12px 0; font-size:14px; }
  .vs-info span { color:#64748b; }
  .vs-info b { font-weight:700; }
  .vs-src { font-size:11.5px; color:#64748b; font-weight:400; }
  .vs-chips { display:flex; flex-wrap:wrap; gap:6px; margin:4px 0 12px; }
  .vs-chips button { border:1.5px solid var(--border); background:var(--field-bg); color:var(--text); border-radius:999px; padding:6px 12px; font-size:13px; font-weight:600; cursor:pointer; font-family:inherit; }
  .vs-chips button.on { border-color:#1d4ed8; background:#eaf1ff; color:#1d4ed8; }
  .vs-warn { font-size:12.5px; color:#92600a; background:#fff4d6; border-radius:10px; padding:8px 10px; margin-bottom:12px; }
</style>

<input type="file" id="vsFile" accept="image/*" capture="environment" style="display:none;" onchange="vsOnPhoto(this)">
<div id="vsOverlay" role="dialog" aria-modal="true">
  <div class="ps-top">
    <button type="button" class="ps-ib" onclick="closeVinScanner()" aria-label="close"><i class="fa-solid fa-xmark"></i></button>
    <div>{{ T.vs_title }}</div>
    <button type="button" class="ps-ib" onclick="openVinScanner()" aria-label="{{ T.vs_retake }}"><i class="fa-solid fa-camera"></i></button>
  </div>
  <div id="vsPhotoBox"><img id="vsImg" alt="" onclick="vsOnTap(event)"></div>
  <div id="vsStatus"><span></span></div>
  <div id="vsSheet"></div>
  <canvas id="vsCanvas" style="display:none;"></canvas>
</div>

<script>
// ===== VIN по фото =====
// Мастер делает ОДНО фото обычной камерой телефона (с автофокусом, без
// наведения рамки). VIN ищется по всему снимку: штрихкод (если телефон умеет
// BarcodeDetector) + текст (Tesseract на телефоне; ~5 МБ скачиваются с
// бесплатного CDN один раз). Не нашлось — мастер касается VIN на фото, и
// читается только эта полоска. Фото никуда не отправляются.
const VS = { worker: null, loading: null, detector: null, gen: 0, result: null, info: null, pick: null, img: null };
const VS_OK = /^[A-HJ-NPR-Z0-9]{17}$/;
const VS_TR = { A:1,B:2,C:3,D:4,E:5,F:6,G:7,H:8,J:1,K:2,L:3,M:4,N:5,P:7,R:9,S:2,T:3,U:4,V:5,W:6,X:7,Y:8,Z:9 };
const VS_W = [8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2];
// известные коды производителей (первые 3 знака VIN) — с сервера
const VS_WMI = new Set(__VIN_WMI__);

function vsNorm(s) {
  return String(s || '').toUpperCase().replace(/O/g, '0').replace(/Q/g, '0').replace(/I/g, '1').replace(/[^A-Z0-9]/g, '');
}
function vsCheckOk(v) {
  let t = 0;
  for (let i = 0; i < 17; i++) t += (/[0-9]/.test(v[i]) ? +v[i] : (VS_TR[v[i]] || 0)) * VS_W[i];
  const r = t % 11;
  return v[8] === (r === 10 ? 'X' : String(r));
}
// из текста — кандидаты на VIN (17 знаков, последние 4 — цифры). Из одной
// строки берём один вариант: с известным кодом производителя, иначе с
// верной контрольной цифрой, иначе прижатый к концу строки.
function vsExtract(text) {
  const out = [];
  String(text || '').split(/\n/).forEach(line => {
    const s = vsNorm(String(line).replace(/\bVIN\b|\bV1N\b/gi, ' '));
    if (s.length < 17 || s.length > 24) return;
    const ws = [];
    for (let i = 0; i + 17 <= s.length; i++) {
      const w = s.slice(i, i + 17);
      if (VS_OK.test(w) && /[0-9]{4}$/.test(w)) ws.push(w);
    }
    if (!ws.length) return;
    out.push(ws.find(w => VS_WMI.has(w.slice(0, 3))) || ws.find(vsCheckOk) || ws[ws.length - 1]);
  });
  return out;
}
function vsBest(cands) {
  return cands.find(w => VS_WMI.has(w.slice(0, 3)) && vsCheckOk(w)) || cands.find(w => VS_WMI.has(w.slice(0, 3)))
    || cands.find(vsCheckOk) || cands[0] || null;
}

function vsSetStatus(text, isErr) {
  const st = document.getElementById('vsStatus');
  st.classList.toggle('err', !!isErr);
  st.style.display = text ? '' : 'none';
  st.querySelector('span').textContent = text || '';
}

function vsLoadOcr() {
  if (VS.worker) return Promise.resolve(VS.worker);
  if (!VS.loading) {
    VS.loading = (async () => {
      if (!window.Tesseract) await psLoadScript('https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js');
      const w = await Tesseract.createWorker('eng', 1);
      await w.setParameters({ tessedit_char_whitelist: 'ABCDEFGHJKLMNPRSTUVWXYZ0123456789' });
      VS.worker = w;
      return w;
    })().catch(e => { VS.loading = null; throw e; });
  }
  return VS.loading;
}

async function vsMakeDetector() {
  if (VS.detector !== null || !('BarcodeDetector' in window)) return;
  try {
    const sup = await BarcodeDetector.getSupportedFormats();
    const want = ['code_39', 'code_128', 'data_matrix', 'qr_code', 'pdf417'].filter(f => sup.includes(f));
    VS.detector = want.length ? new BarcodeDetector({ formats: want }) : false;
  } catch (e) { VS.detector = false; }
}

// кнопка камеры: сразу открываем камеру телефона, а распознавание
// загружаем в фоне, пока мастер фотографирует
function openVinScanner() {
  vsLoadOcr().catch(() => {});
  const f = document.getElementById('vsFile');
  f.value = '';
  f.click();
}

function closeVinScanner() {
  VS.gen++;
  const ov = document.getElementById('vsOverlay');
  ov.classList.remove('open', 'result', 'tap');
  document.getElementById('vsSheet').innerHTML = '';
  const img = document.getElementById('vsImg');
  if (img.src && img.src.startsWith('blob:')) URL.revokeObjectURL(img.src);
  img.removeAttribute('src');
  VS.img = null;
  document.body.style.overflow = '';
}

// фото (или его полоска) → серая картинка с растянутым контрастом
function vsToCanvas(img, sx, sy, sw, sh, maxW) {
  const k = Math.min(1, maxW / sw);
  const c = document.getElementById('vsCanvas');
  c.width = Math.round(sw * k); c.height = Math.round(sh * k);
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, c.width, c.height);
  const im = ctx.getImageData(0, 0, c.width, c.height), d = im.data;
  let lo = 255, hi = 0;
  for (let i = 0; i < d.length; i += 4) {
    const g = (d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114) | 0;
    d[i] = g; if (g < lo) lo = g; if (g > hi) hi = g;
  }
  const m = hi > lo ? 255 / (hi - lo) : 1;
  for (let i = 0; i < d.length; i += 4) { const g = Math.max(0, Math.min(255, (d[i] - lo) * m)); d[i] = d[i + 1] = d[i + 2] = g; }
  ctx.putImageData(im, 0, 0);
  return c;
}

async function vsOcr(canvas, psm) {
  const w = await vsLoadOcr();
  await w.setParameters({ tessedit_pageseg_mode: psm });
  return (await w.recognize(canvas)).data.text || '';
}

async function vsOnPhoto(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const gen = ++VS.gen;
  const ov = document.getElementById('vsOverlay');
  ov.classList.remove('result', 'tap');
  ov.classList.add('open');
  document.body.style.overflow = 'hidden';
  document.getElementById('vsSheet').innerHTML = '';
  const img = document.getElementById('vsImg');
  img.src = URL.createObjectURL(file);
  try { await img.decode(); } catch (e) {}
  if (gen !== VS.gen) return;
  VS.img = img;
  vsSetStatus(VS.worker ? T.vs_reading : T.vs_loading);
  // 1) штрихкод на наклейке
  await vsMakeDetector();
  if (VS.detector) {
    try {
      const codes = await VS.detector.detect(img);
      for (const c of codes) {
        const raw = vsNorm(c.rawValue);
        const v = raw.length === 17 && VS_OK.test(raw) ? raw : vsBest(vsExtract(c.rawValue));
        if (v && gen === VS.gen) { vsShowResult(v); return; }
      }
    } catch (e) {}
  }
  if (gen !== VS.gen) return;
  // 2) текст по всему фото
  const W = img.naturalWidth, H = img.naturalHeight;
  let found = null;
  try {
    const text = await vsOcr(vsToCanvas(img, 0, 0, W, H, 1800), '11');
    found = vsBest(vsExtract(text));
  } catch (e) {
    if (gen === VS.gen) { vsSetStatus(T.vs_load_fail, true); ov.classList.add('tap'); }
    return;
  }
  if (gen !== VS.gen) return;
  if (found) { vsShowResult(found); return; }
  // не нашли — мастер касается VIN на фото
  ov.classList.add('tap');
  vsSetStatus(T.vs_tap_hint, true);
}

// касание по фото: читаем горизонтальную полоску вокруг этого места
async function vsOnTap(ev) {
  const ov = document.getElementById('vsOverlay');
  if (!ov.classList.contains('tap') || !VS.img) return;
  const img = VS.img, r = img.getBoundingClientRect();
  const W = img.naturalWidth, H = img.naturalHeight;
  const y = (ev.clientY - r.top) / r.height * H;
  const band = Math.max(40, H * 0.09);
  const gen = VS.gen;
  vsSetStatus(T.vs_reading);
  let v = null;
  try {
    for (const k of [1, 1.8]) {
      const h = band * k, sy = Math.max(0, y - h / 2);
      const text = await vsOcr(vsToCanvas(img, 0, sy, W, Math.min(h, H - sy), 1600), '6');
      v = vsBest(vsExtract(text));
      if (v || gen !== VS.gen) break;
    }
  } catch (e) { v = null; }
  if (gen !== VS.gen) return;
  if (v) { vsShowResult(v); return; }
  vsSetStatus(T.vs_not_found, true);
  vsShowResult('');
}

// ---- результат ----
async function vinDecode(vin) {
  try { return await (await fetch('/api/vin/decode?vin=' + encodeURIComponent(vin))).json(); }
  catch (e) { return null; }
}

async function vsShowResult(vin) {
  VS.result = vin; VS.info = null; VS.pick = null;
  const ov = document.getElementById('vsOverlay');
  ov.classList.remove('tap');
  ov.classList.add('result');
  if (navigator.vibrate && vin) { try { navigator.vibrate(60); } catch (e) {} }
  vsRenderSheet();
  if (!VS_OK.test(vin)) return;
  const gen = VS.gen;
  const info = await vinDecode(vin);
  if (gen !== VS.gen || VS.result !== vin) return;
  VS.info = info;
  vsRenderSheet(true);
}

function vsOnEdit(el) {
  const v = vsNorm(el.value).slice(0, 17);
  if (v === VS.result) return;
  VS.result = v; VS.info = null; VS.pick = null;
  clearTimeout(VS.editTimer);
  if (VS_OK.test(v)) VS.editTimer = setTimeout(async () => {
    const info = await vinDecode(v);
    if (VS.result === v) { VS.info = info; vsRenderSheet(true); }
  }, 300);
  else vsRenderSheet(true);
}

function vsInfoHtml(info) {
  if (!VS.result) return `<div class="vs-warn">${escapeHtml(T.vs_not_found)}</div>`;
  if (!VS_OK.test(VS.result)) return `<div class="vs-src">${VS.result.length}/17</div>`;
  if (!info) return `<div class="vs-src" style="margin-top:8px;">${escapeHtml(T.vs_decoding)}</div>`;
  if (!info.ok) return `<div class="vs-warn">${escapeHtml(T.vs_invalid)}</div>`;
  const srcLabel = info.model_source === 'learned' ? T.vs_src_learned : (info.model_source === 'vpic' ? T.vs_src_vpic : '');
  let html = `<div class="vs-info">
      <span>${escapeHtml(T.field_car_brand)}</span><b>${escapeHtml(info.brand || T.vs_unknown)}</b>
      ${info.year ? `<span>${escapeHtml(T.vs_year)}</span><b>${info.year}</b>` : ''}
      <span>${escapeHtml(T.field_car_model)}</span><b>${escapeHtml(VS.pick || info.model || '—')}${srcLabel && !VS.pick ? ` <span class="vs-src">· ${escapeHtml(srcLabel)}</span>` : ''}</b>
    </div>`;
  if (!info.model && (info.choices || []).length) {
    html += `<div class="ps-lbl">${escapeHtml(T.vs_pick_model)}</div><div class="vs-chips">` +
      info.choices.map(m => `<button type="button" class="${VS.pick === m ? 'on' : ''}" onclick="vsPick(${escapeHtml(JSON.stringify(m))})">${escapeHtml(m)}</button>`).join('') + '</div>';
  }
  return html;
}

function vsCarHtml(info) {
  if (!info || !info.car) return '';
  const c = info.car;
  return `<div class="ps-match ok"><div class="ps-av">${escapeHtml(psInitials(c.owner_name))}</div><div style="min-width:0;">
      <div class="ps-tag"><i class="fa-solid fa-circle-check"></i> ${escapeHtml(T.vs_in_base)}</div>
      <div class="ps-mt mono">${escapeHtml(psPretty(c.plate_number))}</div>
      <div class="ps-ms">${escapeHtml([c.owner_name, [c.car_brand, c.car_model].filter(Boolean).join(' ')].filter(Boolean).join(' · '))}</div></div></div>`;
}

function vsRenderSheet(keepInput) {
  const sheet = document.getElementById('vsSheet');
  const info = VS.info;
  if (keepInput && document.getElementById('vsVinInput')) {
    document.getElementById('vsInfoBox').innerHTML = vsInfoHtml(info) + vsCarHtml(info);
    return;
  }
  sheet.innerHTML = `
    <div class="ps-grab"></div>
    <div class="ps-lbl">${escapeHtml(VS.result ? T.vs_recognized : T.vs_type_vin)}</div>
    <input id="vsVinInput" class="vs-vin" value="${escapeHtml(VS.result || '')}" maxlength="20" placeholder="XWB…" autocomplete="off" autocapitalize="characters" spellcheck="false" oninput="vsOnEdit(this)">
    <div class="vs-src" style="margin-top:4px;">${escapeHtml(T.vs_check_hint)}</div>
    <div id="vsInfoBox">${vsInfoHtml(info)}${vsCarHtml(info)}</div>
    <div class="ps-btns">
      <button type="button" class="ps-bt s" onclick="openVinScanner()"><i class="fa-solid fa-camera"></i> ${escapeHtml(T.vs_retake)}</button>
      <button type="button" class="ps-bt p" onclick="vsApply()">${escapeHtml(T.vs_apply)}</button>
    </div>
    <div class="ps-lock"><i class="fa-solid fa-lock"></i> ${escapeHtml(T.vs_on_phone)}</div>`;
  if (!VS.result) setTimeout(() => { const i = document.getElementById('vsVinInput'); if (i) i.focus(); }, 50);
}

function vsPick(m) { VS.pick = VS.pick === m ? null : m; vsRenderSheet(true); }

// подставить VIN, марку и модель в форму «Замена»
function applyVinInfo(vin, info, pickedModel) {
  document.getElementById('vin').value = vin || '';
  if (info && info.ok) {
    const model = pickedModel || info.model;
    const brandSel = document.getElementById('car_brand');
    const inList = info.brand && Array.from(brandSel.options).some(o => o.value === info.brand);
    if (inList) brandSel.value = info.brand;
    else if (info.brand) brandSel.value = 'Другое';
    if (model) {
      document.getElementById('car_model').value = (!inList && info.brand && model.toLowerCase().indexOf(info.brand.toLowerCase()) < 0)
        ? info.brand + ' ' + model : model;
    }
    if (info.car && !(document.getElementById('plate').value || '').trim() && typeof psApply === 'function') {
      psApply(info.car.plate_number);
    }
  }
  renderVinHint();
  renderQuickModels();
  if (typeof scheduleAddDraft === 'function') scheduleAddDraft();
  specSchedule(0);
}

function vsApply() {
  const v = VS.result;
  if (!VS_OK.test(v || '')) { showMsg(T.vs_invalid, false); return; }
  const info = VS.info, pick = VS.pick;
  closeVinScanner();
  applyVinInfo(v, info, pick);
}

// ---- ручной ввод VIN в форме ----
const VINF = { timer: null, info: null, vin: '' };
function onVinInput() {
  const el = document.getElementById('vin');
  const v = vsNorm(el.value).slice(0, 17);
  clearTimeout(VINF.timer);
  if (!VS_OK.test(v)) { VINF.info = null; VINF.vin = v; renderVinHint(); return; }
  VINF.timer = setTimeout(async () => {
    const info = await vinDecode(v);
    if (vsNorm(document.getElementById('vin').value) !== v) return;
    VINF.info = info; VINF.vin = v;
    if (info && info.ok && info.model && !(document.getElementById('car_model').value || '').trim()) {
      applyVinInfo(v, info, null);
      return;
    }
    renderVinHint();
  }, 350);
}

function renderVinHint() {
  const box = document.getElementById('vinHint');
  if (!box) return;
  const v = vsNorm((document.getElementById('vin') || {}).value || '');
  const info = VINF.vin === v ? VINF.info : null;
  if (!v) { box.innerHTML = ''; return; }
  if (v.length < 17) { box.innerHTML = `<div class="vin-hint">${v.length}/17</div>`; return; }
  if (!info) { box.innerHTML = ''; return; }
  if (!info.ok) { box.innerHTML = `<div class="vin-hint err">${escapeHtml(T.vs_invalid)}</div>`; return; }
  const line = [info.brand, info.year, info.model].filter(Boolean).join(' · ');
  const curModel = (document.getElementById('car_model').value || '').trim();
  const btn = info.model && curModel.toLowerCase() !== String(info.model).toLowerCase()
    ? `<button type="button" onclick="applyVinInfo(VINF.vin, VINF.info, null)">${escapeHtml(T.vs_apply)}</button>` : '';
  const choose = !info.model ? ` · ${escapeHtml(T.vs_model_unknown)}` : '';
  box.innerHTML = `<div class="vin-hint"><i class="fa-solid fa-circle-info"></i> ${escapeHtml(line || T.vs_unknown)}${choose} ${btn}</div>`;
}

// ---- быстрые кнопки моделей ----
// Самые частые модели этой точки (из её базы) + популярные в Узбекистане.
// Одно касание ставит марку и модель — и сразу показывается подбор масла.
// Кнопки-подсказки под «Моделью»: все модели выбранной марки
function brandModels() {
  const sel = document.getElementById('car_brand');
  return (sel && CAR_MODELS[sel.value]) || [];
}
function loadQuickModels() { renderQuickModels(); }
function onBrandChange() {
  // сменили марку: модель от прежней марки (выбранная кнопкой) больше не подходит
  const modelEl = document.getElementById('car_model');
  const cur = (modelEl.value || '').trim().toLowerCase();
  if (cur && !brandModels().some(m => m.toLowerCase() === cur)
      && Object.values(CAR_MODELS).some(list => list.some(m => m.toLowerCase() === cur))) modelEl.value = '';
  renderQuickModels();
  if (typeof scheduleAddDraft === 'function') scheduleAddDraft();
  specSchedule(0);
}
function renderQuickModels() {
  const box = document.getElementById('quickModels');
  if (!box) return;
  const models = brandModels();
  box.hidden = !models.length;
  const cur = (document.getElementById('car_model').value || '').trim().toLowerCase();
  box.innerHTML = models.map((m, i) =>
    `<button type="button" class="qm-chip${String(m).toLowerCase() === cur ? ' on' : ''}" onclick="pickQuickModel(${i})">${escapeHtml(m)}</button>`).join('');
}
function pickQuickModel(i) {
  const m = brandModels()[i];
  if (!m) return;
  document.getElementById('car_model').value = m;
  renderQuickModels();
  if (typeof scheduleAddDraft === 'function') scheduleAddDraft();
  specSchedule(0);
}
</script>
<script>loadQuickModels();</script>
"""
