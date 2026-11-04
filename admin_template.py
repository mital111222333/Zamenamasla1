"""HTML-шаблон админ-панели платформы (/admin).

Только разметка, стили и скрипт страницы. В webapp.py к нему добавляются
общие куски (защита сети, панель Telegram, заставка), а маршруты админки —
в admin_routes.py."""

ADMIN_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OilBook — админ-панель</title>
<link rel="manifest" href="/static/manifest.json?v=2">
<meta name="theme-color" content="#0A2540">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=Space+Grotesk:wght@600;700&family=Sora:wght@700;800&family=IBM+Plex+Mono:wght@500;600&family=Inter:wght@200;300;400;500;600&display=swap" crossorigin="anonymous" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=Space+Grotesk:wght@600;700&family=Sora:wght@700;800&family=IBM+Plex+Mono:wght@500;600&family=Inter:wght@200;300;400;500;600&display=swap"></noscript>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" crossorigin="anonymous" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"></noscript>
<style>
  :root {
    --bg:#F1F5F9; --text:#1E293B; --hint:#94A3B8; --btn:#E63946; --btn-text:#FFFFFF; --blue:#0F52BA; --darkblue:#0A2540; --cyan:#00A8E8;
    --card:#FFFFFF; --border:#E2E8F0; --field-bg:#F4F7FA; --ok:#059669; --ok-bg:#ECFDF5; --danger:#B3241C; --danger-bg:#FDECEA;
    --font-display:'Space Grotesk', sans-serif; --font-body:'Plus Jakarta Sans', -apple-system, sans-serif; --font-mono:'IBM Plex Mono', monospace;
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: var(--font-body); }
  .speedline { height:6px; width:100%; background: linear-gradient(90deg, var(--blue) 0%, var(--blue) 33%, #fff 33%, #fff 38%, var(--btn) 38%, var(--btn) 70%, #fff 70%, #fff 75%, var(--cyan) 75%, var(--cyan) 100%); }
  .container { padding: 12px; max-width: 900px; margin: 0 auto; }
  .topbar { display:flex; justify-content:space-between; align-items:center; margin: 14px 0 16px; }
  .logo-badge {
    display:inline-flex; align-items:center; justify-content:center; width:40px; height:40px;
    background:var(--darkblue); color:var(--cyan); border-radius:12px; transform:rotate(-8deg);
    box-shadow:0 4px 10px rgba(10,37,64,.25); font-size:16px; flex:none;
  }
  h1 { font-family: var(--font-display); font-weight:800; font-style:italic; letter-spacing:-0.3px; font-size: 20px; margin: 0; line-height:1.1; color:var(--darkblue); }
  .logo-sub { font-size:10px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase; color:var(--hint); }
  .brand-line { text-transform:none; letter-spacing:0; font-size:12px; display:flex; align-items:baseline; gap:4px; flex-wrap:wrap; margin-top:2px; }
  .brand-line .role-tag { font-size:11px; font-weight:700; letter-spacing:.8px; text-transform:uppercase; }
  .wordmark { font-family:'Sora', var(--font-display), sans-serif; font-style:normal; font-weight:800; font-size:17px; letter-spacing:-0.4px; line-height:1; white-space:nowrap; }
  .wordmark .wm-oil { background:linear-gradient(135deg, #0EA5E9 0%, #1D4ED8 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
  .wordmark .wm-book { color:#0B1B3A; }
  .logout { color: var(--btn); font-size: 12px; font-weight:700; text-decoration:none; background:var(--danger-bg); padding:6px 10px; border-radius:10px; }
  .card { background: #fff; border:2px solid #DBEAFE; border-radius: 22px; padding: 16px; margin-bottom: 16px; box-shadow: 0 10px 25px -5px rgba(15,82,186,.08); }
  .field { margin-bottom: 10px; }
  .row2 { display:flex; gap:10px; }
  .row2 .field { flex:1; }
  label { display:block; font-size: 12px; color: var(--hint); margin-bottom: 4px; text-transform:uppercase; letter-spacing:0.4px; }
  input { width: 100%; padding: 10px; border-radius: 10px; border: 1.5px solid var(--border); background: var(--field-bg); color: var(--text); font-size: 15px; font-family: var(--font-body); }
  input:focus { outline:none; border-color: var(--blue); box-shadow:0 0 0 3px rgba(15,82,186,.12); }
  .field select { width:100%; padding:10px; border-radius:10px; border:1.5px solid var(--border); background:var(--field-bg); color:var(--text); font-size:15px; font-family:var(--font-body); }
  button.submit { width: 100%; padding: 14px; border: none; border-radius: 14px; background: linear-gradient(135deg, #1D4ED8 0%, #1E40AF 55%, #312E81 100%); color:#fff; font-size: 15px; font-weight: 700; font-family: var(--font-display); letter-spacing:0.5px; text-transform:uppercase; cursor: pointer; margin-top: 6px; box-shadow: 0 8px 18px rgba(29,78,216,.30); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
  th { color:#fff; background:#1E293B; font-weight: 700; font-size:10px; text-transform:uppercase; letter-spacing:0.4px; }
  .badge { display:inline-block; padding: 3px 9px; border-radius: 20px; font-size: 11px; font-weight:600; cursor:pointer; border:none; text-transform:uppercase; letter-spacing:0.3px; }
  .badge.active { background: var(--ok-bg); color: var(--ok); }
  .badge.inactive { background: var(--danger-bg); color: var(--danger); }
  .hint-text { color: var(--hint); font-size: 12px; margin-top: 6px; }
  .msg { padding: 12px; border-radius: 10px; margin-bottom: 10px; font-size: 14px; }
  .msg.ok { background:var(--ok-bg); color:var(--ok); }
  .msg.err { background:var(--danger-bg); color:var(--danger); }
  .new-creds { background:var(--field-bg); border:1px dashed var(--blue); border-radius:10px; padding:10px; font-size:13px; margin-top:10px; font-family: var(--font-mono); }
  .adm-stats { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin-bottom:14px; }
  .adm-stat { background:#fff; border:1px solid var(--border); border-radius:14px; padding:10px 12px; }
  .adm-stat b { display:block; font-family:var(--font-display); font-size:22px; color:var(--darkblue); line-height:1.1; }
  .adm-stat span { font-size:11.5px; color:#64748B; }
  details.adm-sec { background:#fff; border:1px solid var(--border); border-radius:16px; margin-bottom:10px; overflow:hidden; }
  details.adm-sec > summary { list-style:none; cursor:pointer; display:flex; align-items:center; gap:12px; padding:14px 16px; font-weight:700; font-size:15px; color:var(--text); -webkit-tap-highlight-color:transparent; }
  details.adm-sec > summary::-webkit-details-marker { display:none; }
  details.adm-sec > summary .ic { width:34px; height:34px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:15px; flex:none; }
  details.adm-sec > summary .sub { display:block; font-size:12px; font-weight:500; color:#64748B; margin-top:1px; }
  details.adm-sec > summary .chev { margin-left:auto; color:#94A3B8; transition:transform .2s; }
  details.adm-sec[open] > summary .chev { transform:rotate(180deg); }
  details.adm-sec[open] > summary { border-bottom:1px solid #F1F5F9; }
  details.adm-sec .sec-body { padding:14px 16px 16px; }
  details.adm-sec.danger { border-color:#FCA5A5; }
  .list-head { display:flex; align-items:center; justify-content:space-between; gap:10px; margin:22px 0 10px; }
  .list-head h2 { font-family:var(--font-display); font-size:18px; margin:0; color:var(--darkblue); }
  .adm-filters { display:flex; gap:6px; flex-wrap:wrap; margin:8px 0 12px; }
  .adm-filters button { border:1px solid var(--border); background:#fff; border-radius:999px; padding:6px 12px; font-size:12.5px; font-weight:600; color:#475569; cursor:pointer; font-family:inherit; }
  .adm-filters button.on { background:var(--blue); border-color:var(--blue); color:#fff; }
  .grp-title { font-weight:800; color:var(--blue); font-size:13px; margin:16px 2px 8px; }
  .shop-card { background:#fff; border:1px solid var(--border); border-radius:16px; padding:14px; margin-bottom:10px; }
  .shop-card.off { background:#FAFAFA; border-style:dashed; }
  .sc-head { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }
  .sc-name { font-weight:800; font-size:16px; color:var(--text); }
  .sc-login { font-family:var(--font-mono); font-size:12.5px; color:#64748B; }
  .sc-meta { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:12.5px; color:#475569; margin:8px 0 10px; }
  .sc-meta .ok { color:#15803D; font-weight:700; }
  .sc-meta .no { color:#B3241C; font-weight:700; }
  .sc-row { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:6px; }
  .sc-row .lbl { font-size:11.5px; color:#94A3B8; margin-right:2px; }
  .sc-btn { border:1px solid var(--border); background:#fff; border-radius:10px; padding:6px 10px; font-size:12.5px; font-weight:600; color:#334155; cursor:pointer; font-family:inherit; }
  .sc-btn:hover { background:#F8FAFC; }
  .sc-panel { margin-top:10px; padding:12px; background:var(--field-bg); border-radius:12px; }
  .sc-edit input { font-size:13px; padding:7px 9px; margin-top:4px; }
  code { font-family:var(--font-mono); font-size:12px; background:#F1F5F9; padding:1px 5px; border-radius:5px; }
  .sc-toggles { display:flex; flex-wrap:wrap; align-items:center; gap:10px 18px; font-size:13px; font-weight:600; color:#334155; }
  .sw { position:relative; width:40px; height:23px; border-radius:12px; border:none; background:#CBD5E1; cursor:pointer; vertical-align:middle; margin-left:6px; padding:0; transition:background .15s; }
  .sw::after { content:''; position:absolute; top:3px; left:3px; width:17px; height:17px; border-radius:50%; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.2); transition:left .15s; }
  .sw.on { background:#16A34A; }
  .sw.on::after { left:20px; }
  .grp-chip { display:inline-flex; align-items:center; gap:4px; background:#F1F5F9; border-radius:999px; padding:0 4px 0 10px; font-size:12.5px; color:#475569; }
  .grp-chip input { border:none !important; background:transparent !important; box-shadow:none !important; padding:5px 6px !important; width:110px; font-size:12.5px; margin:0; }
  .sc-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; margin-top:12px; }
  .sc-tile { border:1px solid var(--border); background:#fff; border-radius:12px; padding:10px 4px 8px; text-align:center; font-size:12px; font-weight:600; color:#475569; cursor:pointer; font-family:inherit; }
  .sc-tile i { display:block; font-size:18px; color:var(--darkblue); margin-bottom:4px; }
  .sc-tile:hover { background:#F8FAFC; }
  .sc-tile.open { border-color:var(--blue); background:#EFF6FF; color:var(--blue); }
  .sc-tile.open i { color:var(--blue); }
  .sc-tile[disabled] { opacity:.4; cursor:default; }
  @media (max-width:560px) { .row2 { flex-direction:column; gap:0; } }
  .sc-sub { margin:10px 0; padding:10px 12px; border-radius:12px; background:#F8FAFC; border:1px solid var(--border); font-size:13px; }
  .sc-sub.bad { background:#FEF2F2; border-color:#FCA5A5; }
  .sc-sub.warn { background:#FFF7ED; border-color:#FDBA74; }
  .sc-sub-top { display:flex; flex-wrap:wrap; align-items:center; gap:6px 10px; }
  .sub-pill { font-size:12px; font-weight:700; padding:3px 9px; border-radius:999px; white-space:nowrap; }
  .sub-pill.ok { background:#DCFCE7; color:#166534; }
  .sub-pill.warn { background:#FFEDD5; color:#9A3412; }
  .sub-pill.bad { background:#B3241C; color:#fff; }
  .sub-pill.life { background:#0F52BA; color:#fff; }
  .sub-pill.unset { background:#E2E8F0; color:#334155; }
  .sc-sub-btns { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  .sc-sub-btns button { border:1.5px solid #0F52BA; background:#fff; color:#0F52BA; border-radius:8px; padding:6px 10px; font-size:12.5px; font-weight:700; cursor:pointer; }
  .sc-sub-btns button.grey { border-color:#CBD5E1; color:#334155; }
  .sc-sub-chk { margin-top:8px; padding:8px 10px; border-radius:10px; background:#FEF3C7; display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
  .sc-sub-chk button { border:0; border-radius:8px; padding:6px 10px; font-weight:700; cursor:pointer; color:#fff; }
  .sc-sub-chk .ok { background:#16A34A; } .sc-sub-chk .no { background:#DC2626; }
  .pay-item { border:1px solid var(--border); border-radius:12px; padding:10px 12px; margin-bottom:8px; font-size:13px; }
  .pay-item .pay-cap { white-space:pre-line; }
  .pay-item .pay-act { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; white-space:normal; }
  .pay-item .pay-act button, .pay-item .pay-act a { border:0; border-radius:8px; padding:7px 12px; font-weight:700; cursor:pointer; color:#fff; text-decoration:none; font-size:13px; }
  .pay-act .ok { background:#16A34A; } .pay-act .no { background:#DC2626; } .pay-act a { background:#0F52BA; }
  .ref-cp { border:1px solid #CBD5E1; background:#fff; border-radius:7px; width:30px; height:28px; margin-left:4px; cursor:pointer; color:#0F52BA; }
  .adm-tabs { display:flex; gap:6px; background:#E2E8F0; padding:4px; border-radius:12px; margin-bottom:14px; }
  .adm-tabs button { flex:1; height:42px; border:0; border-radius:9px; background:transparent; font-weight:700; font-size:14px; color:#475569; cursor:pointer; font-family:inherit; }
  .adm-tabs button.on { background:#fff; color:var(--blue); box-shadow:0 1px 3px rgba(15,23,42,.12); }
  .map-kpis { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; margin-bottom:10px; }
  @media (min-width:700px) { .map-kpis { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .map-kpi { background:#fff; border:1px solid var(--border); border-radius:14px; padding:10px 12px; }
  .map-kpi b { display:block; font-family:var(--font-display); font-size:20px; color:var(--darkblue); line-height:1.15; }
  .map-kpi span { font-size:11.5px; color:#64748B; }
  .map-bar { display:flex; gap:6px; flex-wrap:wrap; align-items:center; margin-bottom:8px; }
  .map-seg { display:inline-flex; background:#E2E8F0; border-radius:10px; padding:3px; }
  .map-seg button { border:0; background:transparent; border-radius:8px; padding:6px 10px; font-size:12.5px; font-weight:700; color:#475569; cursor:pointer; font-family:inherit; }
  .map-seg button.on { background:#fff; color:var(--blue); box-shadow:0 1px 2px rgba(15,23,42,.12); }
  .map-bar select { border:1px solid var(--border); border-radius:10px; padding:7px 10px; font-size:12.5px; font-family:inherit; background:#fff; color:var(--text); }
  .map-bar label.chk { display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600; color:#475569; text-transform:none; letter-spacing:0; margin:0; cursor:pointer; }
  .map-bar label.chk input { width:auto; }
  .map-wrap { position:relative; border-radius:18px; overflow:hidden; border:2px solid #DBEAFE; background:#E5E7EB; }
  #admMapBox { height:62vh; min-height:340px; max-height:640px; width:100%; }
  #admMapBox.picking { cursor:crosshair; }
  .map-legend { display:flex; gap:12px; flex-wrap:wrap; font-size:12px; color:#475569; margin:8px 2px 4px; }
  .map-legend i.dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; vertical-align:-1px; }
  .map-pick { position:absolute; left:10px; right:10px; bottom:26px; z-index:1000; background:#0A2540; color:#fff; border-radius:14px; padding:10px 12px; font-size:13.5px; box-shadow:0 8px 20px rgba(0,0,0,.25); display:none; }
  .map-pick .pk-act { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
  .map-pick button { border:0; border-radius:9px; padding:8px 12px; font-weight:700; font-size:13px; cursor:pointer; font-family:inherit; }
  .map-pick .pk-geo { background:#00A8E8; color:#fff; } .map-pick .pk-cancel { background:#fff; color:#0A2540; }
  .map-pop { font-family:var(--font-body); min-width:220px; }
  .map-pop .mp-name { font-weight:800; font-size:15px; color:var(--darkblue); }
  .map-pop .mp-kind { font-size:11.5px; color:#64748B; margin:2px 0 6px; }
  .map-pop .mp-st { font-size:12.5px; font-weight:700; margin-bottom:6px; }
  .map-pop .mp-grid { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin:6px 0; }
  .map-pop .mp-grid div { background:#F1F5F9; border-radius:8px; padding:6px 8px; font-size:11px; color:#64748B; }
  .map-pop .mp-grid b { display:block; font-size:14px; color:var(--darkblue); font-family:var(--font-display); }
  .map-pop .mp-addr { font-size:12px; color:#475569; margin:4px 0; }
  .map-pop .mp-snap { display:block; width:100%; margin-top:8px; border:0; border-radius:10px; padding:10px; background:#0F52BA; color:#fff; font-weight:800; font-size:13px; cursor:pointer; font-family:inherit; }
  .map-pop .mp-act { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
  .map-pop .mp-act button, .map-pop .mp-act a { border:0; border-radius:8px; padding:6px 9px; font-size:12px; font-weight:700; cursor:pointer; text-decoration:none; font-family:inherit; }
  .map-pop .mp-act .b1 { background:#0F52BA; color:#fff; } .map-pop .mp-act .b2 { background:#E2E8F0; color:#1E293B; }
  .map-list { background:#fff; border:1px solid var(--border); border-radius:16px; margin-top:12px; overflow:hidden; }
  .map-list h3 { margin:0; padding:12px 14px; font-size:14.5px; font-family:var(--font-display); color:var(--darkblue); border-bottom:1px solid #F1F5F9; }
  .map-row { display:flex; align-items:center; gap:10px; padding:10px 14px; border-bottom:1px solid #F1F5F9; cursor:pointer; }
  .map-row:last-child { border-bottom:0; }
  .map-row .mr-n { font-weight:800; color:#94A3B8; width:20px; font-size:12px; flex:none; }
  .map-row .mr-dot { width:10px; height:10px; border-radius:50%; flex:none; }
  .map-row .mr-name { flex:1; min-width:0; font-size:13.5px; font-weight:700; }
  .map-row .mr-name small { display:block; font-weight:500; color:#64748B; font-size:11.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .map-row .mr-val { text-align:right; font-family:var(--font-mono); font-size:13px; font-weight:600; white-space:nowrap; }
  .map-row .mr-val small { display:block; font-size:11px; font-family:var(--font-body); }
  .map-row .mr-pin { border:0; background:#EFF6FF; color:var(--blue); border-radius:9px; padding:7px 10px; font-weight:700; font-size:12px; cursor:pointer; font-family:inherit; flex:none; }
  .leaflet-container { font-family:var(--font-body); }
  @media (max-width:440px) { .adm-tabs button { font-size:12.5px; } .adm-tabs button i { display:none; } }
  .ana-sel { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px; }
  .ana-sel select { flex:1; min-width:140px; border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:13px; font-family:inherit; background:#fff; color:var(--text); }
  .ana-chips { display:flex; gap:6px; overflow-x:auto; padding-bottom:4px; margin-bottom:10px; -webkit-overflow-scrolling:touch; }
  .ana-chips button { flex:none; border:1px solid var(--border); background:#fff; border-radius:999px; padding:6px 12px; font-size:12.5px; font-weight:600; color:#475569; cursor:pointer; font-family:inherit; white-space:nowrap; }
  .ana-chips button.on { background:var(--blue); border-color:var(--blue); color:#fff; }
  .ana-card { background:#fff; border:1px solid var(--border); border-radius:16px; margin-bottom:12px; overflow:hidden; }
  .ana-card > h3 { margin:0; padding:12px 14px; font-size:14.5px; font-family:var(--font-display); color:var(--darkblue); border-bottom:1px solid #F1F5F9; display:flex; align-items:center; gap:8px; }
  .ana-card > h3 small { margin-left:auto; font-family:var(--font-body); font-weight:500; font-size:11.5px; color:#94A3B8; }
  .ana-card .ana-note { padding:8px 14px; font-size:12px; color:#64748B; background:#F8FAFC; border-bottom:1px solid #F1F5F9; }
  .ana-row { display:flex; align-items:center; gap:10px; padding:9px 14px; border-bottom:1px solid #F1F5F9; }
  .ana-row:last-child { border-bottom:0; }
  .ana-row.click { cursor:pointer; }
  .ana-row .ar-main { flex:1; min-width:0; }
  .ana-row .ar-name { font-size:13.5px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .ana-row .ar-sub { font-size:11.5px; color:#64748B; margin-top:1px; }
  .ana-row .ar-bar { height:6px; background:#F1F5F9; border-radius:3px; margin-top:5px; overflow:hidden; }
  .ana-row .ar-bar i { display:block; height:100%; background:#0F52BA; border-radius:3px; }
  .ana-row .ar-bar i.mital { background:#EAB308; }
  .ana-row .ar-val { text-align:right; font-family:var(--font-mono); font-size:13px; font-weight:600; white-space:nowrap; }
  .ana-row .ar-val small { display:block; font-family:var(--font-body); font-size:11px; color:#64748B; font-weight:500; }
  .mital-tag { display:inline-block; background:#FEF3C7; color:#B45309; border-radius:6px; padding:1px 6px; font-size:10px; font-weight:800; margin-left:5px; vertical-align:1px; letter-spacing:.3px; }
  .ana-tbl-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .ana-tbl { width:100%; border-collapse:collapse; font-size:12.5px; }
  .ana-tbl .ar-sub { font-weight:500; color:#64748B; font-size:11px; margin-top:2px; }
  .ana-range { padding:4px 14px 10px; font-size:12px; color:#475569; line-height:1.6; }
  .ana-range b { font-family:var(--font-mono); color:var(--darkblue); }
  .ana-tbl th { background:#F8FAFC; color:#64748B; font-size:10px; text-transform:uppercase; letter-spacing:.2px; font-weight:700; text-align:right; padding:8px 6px; border-bottom:1px solid var(--border); }
  .ana-tbl th:first-child, .ana-tbl td:first-child { padding-left:14px; } .ana-tbl th:last-child, .ana-tbl td:last-child { padding-right:14px; }
  .ana-tbl th:first-child, .ana-tbl td:first-child { text-align:left; }
  .ana-tbl td { padding:8px 6px; border-bottom:1px solid #F1F5F9; text-align:right; font-family:var(--font-mono); white-space:nowrap; font-size:12px; }
  .ana-tbl td:first-child { font-family:var(--font-body); font-weight:700; white-space:normal; }
  .ana-tbl tr.click { cursor:pointer; }
  .ana-tbl tr.sum td { background:#F8FAFC; font-weight:700; }
  .ana-btn { border:0; background:#EFF6FF; color:var(--blue); border-radius:9px; padding:8px 12px; font-weight:700; font-size:12.5px; cursor:pointer; font-family:inherit; }
  .ana-dq { display:flex; gap:10px; align-items:center; flex-wrap:wrap; background:#fff; border:1px solid var(--border); border-radius:14px; padding:10px 12px; margin-bottom:12px; font-size:12.5px; color:#475569; }
  .ana-dq .dq-txt { flex:1; min-width:200px; line-height:1.5; }
  .ana-dq .dq-txt b { color:var(--darkblue); }
  .ana-dq .dq-act { display:flex; gap:6px; flex-wrap:wrap; }
  .nm-card { padding:12px 14px; }
  .nm-card .ar-sub, .ana-row .ar-sub { font-size:11.5px; color:#64748B; margin-top:2px; }
  .nm-spell { font-weight:800; font-size:14.5px; color:var(--darkblue); word-break:break-word; }
  .nm-spell small { display:block; font-weight:500; font-size:11.5px; color:#64748B; margin-top:2px; }
  .nm-sug { font-size:13px; margin-top:8px; color:#334155; }
  .nm-act { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
  .nm-act button { border:0; border-radius:9px; padding:8px 12px; font-weight:700; font-size:12.5px; cursor:pointer; font-family:inherit; background:#E2E8F0; color:#1E293B; }
  .nm-act button.ok { background:#16A34A; color:#fff; }
  .nm-act button.no { background:#FEE2E2; color:#B91C1C; }
  .nm-form { margin-top:10px; }
  .nm-form label { margin-top:6px; }
  .snap-ov { position:fixed; inset:0; z-index:5000; background:rgba(15,23,42,.55); display:none; }
  .snap-box { position:absolute; left:0; right:0; bottom:0; top:max(24px, env(safe-area-inset-top, 0px)); background:var(--bg); border-radius:20px 20px 0 0; overflow-y:auto; -webkit-overflow-scrolling:touch; }
  @media (min-width:900px) { .snap-box { left:50%; transform:translateX(-50%); width:760px; top:30px; bottom:30px; border-radius:20px; } }
  .snap-head { position:sticky; top:0; z-index:2; background:#0A2540; color:#fff; padding:14px 16px 12px; display:flex; gap:10px; align-items:flex-start; }
  .snap-head .sh-name { font-family:var(--font-display); font-weight:700; font-size:17px; line-height:1.2; }
  .snap-head .sh-sub { font-size:12px; color:#93C5FD; margin-top:3px; }
  .snap-head .sh-x { margin-left:auto; border:0; background:rgba(255,255,255,.12); color:#fff; width:36px; height:36px; border-radius:10px; font-size:18px; cursor:pointer; flex:none; }
  .snap-body { padding:12px 12px calc(24px + env(safe-area-inset-bottom, 0px)); }
  .snap-sec { font-family:var(--font-display); font-size:16px; color:var(--darkblue); margin:16px 2px 8px; display:flex; align-items:center; gap:8px; }
  .snap-wh-row { display:flex; gap:10px; align-items:center; padding:10px 14px; border-bottom:1px solid #F1F5F9; }
  .snap-wh-row:last-child { border-bottom:0; }
  .snap-wh-row .sw-main { flex:1; min-width:0; }
  .snap-wh-row .sw-name { font-weight:700; font-size:13.5px; }
  .snap-wh-row .sw-sub { font-size:11.5px; color:#64748B; margin-top:2px; }
  .snap-wh-row .sw-price { text-align:right; font-family:var(--font-mono); font-size:12.5px; white-space:nowrap; }
  .snap-wh-row .sw-price small { display:block; font-family:var(--font-body); font-size:11px; color:#64748B; }
  .snap-wh-row .sw-m { display:inline-block; margin-top:3px; padding:1px 7px; border-radius:7px; font-size:11.5px; font-weight:700; background:#ECFDF5; color:#047857; font-family:var(--font-body); }
  .snap-wh-row .sw-m.low { background:#FEF2F2; color:#B91C1C; }
  .snap-wh-row .sw-m.none { background:#F1F5F9; color:#94A3B8; }
  details.sup-card > summary { list-style:none; display:flex; align-items:center; gap:10px; padding:12px 14px; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  details.sup-card > summary::-webkit-details-marker { display:none; }
  details.sup-card > summary .ar-main { flex:1; min-width:0; }
  details.sup-card > summary .ar-name { font-size:14px; font-weight:800; color:var(--darkblue); }
  details.sup-card > summary .ar-sub { font-size:11.5px; color:#64748B; margin-top:2px; }
  details.sup-card > summary .ar-val { text-align:right; font-family:var(--font-mono); font-size:14px; font-weight:700; white-space:nowrap; }
  details.sup-card > summary .ar-val small { display:block; font-family:var(--font-body); font-size:11px; font-weight:500; color:#64748B; }
  details.sup-card .sup-chev { color:#94A3B8; transition:transform .2s; }
  details.sup-card[open] .sup-chev { transform:rotate(180deg); }
  details.sup-card[open] > summary { border-bottom:1px solid #F1F5F9; }
  .sup-contacts { display:flex; flex-wrap:wrap; gap:8px; padding:10px 14px 0; font-size:12.5px; }
  .sup-contacts > * { background:#EFF6FF; color:var(--blue); border-radius:8px; padding:5px 9px; text-decoration:none; font-weight:600; }
  .sup-h { padding:10px 14px 4px; font-size:11px; font-weight:800; color:#64748B; text-transform:uppercase; letter-spacing:.4px; }
  .ana-cmp b.ana-bad, .ar-val small.ana-bad { color:#DC2626; } .ana-cmp b.ana-good, .ar-val small.ana-good { color:#16A34A; }
  .ana-good { color:#16A34A; } .ana-bad { color:#DC2626; } .ana-mute { color:#94A3B8; }
  .ana-brands { display:flex; flex-wrap:wrap; gap:5px; margin-top:5px; }
  .ana-brands span { background:#F1F5F9; border-radius:7px; padding:2px 7px; font-size:11.5px; color:#334155; }
  .ana-brands span.m { background:#FEF3C7; color:#B45309; font-weight:700; }
  .ana-cmp { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; padding:12px 14px; }
  @media (min-width:700px) { .ana-cmp { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .ana-cmp div { background:#F8FAFC; border-radius:10px; padding:8px 10px; font-size:11.5px; color:#64748B; }
  .ana-cmp b { display:block; font-family:var(--font-display); font-size:17px; color:var(--darkblue); }
  .inc-grid { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; margin-bottom:12px; }
  @media (min-width:900px) { .inc-grid { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .inc-kpi { background:#fff; border:1px solid var(--border); border-radius:14px; padding:12px 14px; }
  .inc-kpi .k-l { font-size:12px; color:var(--hint); font-weight:600; }
  .inc-kpi .k-v { font-family:var(--font-mono, monospace); font-size:20px; font-weight:700; color:var(--darkblue); margin:4px 0 2px; white-space:nowrap; }
  .inc-kpi .k-s { font-size:12px; color:var(--hint); }
  .inc-kpi.main { background:#0B1F3A; border-color:#0B1F3A; }
  .inc-kpi.main .k-l, .inc-kpi.main .k-s { color:#B9C6DA; } .inc-kpi.main .k-v { color:#fff; }
  .inc-card { background:#fff; border:1px solid var(--border); border-radius:14px; padding:14px; margin-bottom:12px; }
  .inc-card h3 { margin:0 0 10px; font-size:15px; display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; }
  .inc-seg { display:flex; background:#EEF2F7; border-radius:9px; padding:3px; gap:3px; }
  .inc-seg button { border:0; background:transparent; border-radius:7px; padding:6px 10px; font-size:12px; font-weight:700; color:#475569; cursor:pointer; font-family:inherit; }
  .inc-seg button.on { background:#fff; color:var(--blue); }
  .inc-bars { display:flex; align-items:flex-end; gap:4px; height:170px; padding-top:18px; }
  .inc-bar { flex:1; min-width:0; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; height:100%; }
  .inc-bar .b { width:100%; max-width:34px; background:#93C5FD; border-radius:6px 6px 2px 2px; min-height:2px; }
  .inc-bar.cur .b { background:#0F52BA; }
  .inc-bar .v { font-size:10px; color:#334155; font-weight:700; margin-bottom:3px; white-space:nowrap; }
  .inc-bar .m { font-size:10.5px; color:var(--hint); margin-top:4px; }
  @media (max-width:600px) { .inc-bar .v { display:none; } .inc-bar.cur .v, .inc-bar.mx .v { display:block; } }
  .inc-stack { display:flex; height:14px; border-radius:999px; overflow:hidden; background:#EEF2F7; margin-bottom:10px; }
  .inc-leg { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:6px 12px; font-size:13px; }
  .inc-leg span i { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; vertical-align:-1px; }
  .inc-term { display:flex; align-items:center; gap:8px; font-size:13px; margin:6px 0; }
  .inc-term .t-n { width:52px; font-weight:700; }
  .inc-term .t-bar { flex:1; height:10px; background:#EEF2F7; border-radius:999px; overflow:hidden; }
  .inc-term .t-bar div { height:100%; background:#0F52BA; border-radius:999px; }
  .inc-term .t-c { width:64px; text-align:right; color:var(--hint); }
  .inc-row { display:flex; justify-content:space-between; gap:10px; padding:9px 0; border-top:1px solid #EEF2F7; font-size:13px; }
  .inc-row:first-of-type { border-top:0; }
  .inc-row .r-s { font-size:12px; color:var(--hint); margin-top:2px; }
  .inc-row .r-v { font-family:var(--font-mono, monospace); font-weight:700; white-space:nowrap; }
  .inc-jact { display:flex; gap:6px; margin-top:6px; }
  .inc-jact button { border:1px solid #CBD5E1; background:#fff; border-radius:7px; padding:4px 8px; font-size:11.5px; font-weight:700; color:#334155; cursor:pointer; }
  .ix-dates[hidden], .ix-bulk[hidden], .ix-sug[hidden], .ix-tabs .cnt[hidden], #ixShops[hidden], #ixPays[hidden], #ixSet[hidden], #ixOv[hidden] { display:none !important; }
  .ix-tabs { display:flex; gap:4px; background:#fff; border:1px solid var(--border); padding:4px; border-radius:12px; margin-bottom:12px; position:sticky; top:0; z-index:20; }
  .ix-tabs button { flex:1; height:38px; border:0; border-radius:9px; background:transparent; font-weight:700; font-size:13.5px; color:#475569; cursor:pointer; font-family:inherit; display:flex; align-items:center; justify-content:center; gap:6px; white-space:nowrap; }
  .ix-tabs button.on { background:#0B1F3A; color:#fff; }
  .ix-tabs .cnt { background:#E63946; color:#fff; border-radius:999px; font-size:11px; padding:1px 6px; }
  @media (max-width:440px) { .ix-tabs button { font-size:12.5px; } .ix-tabs button i { display:none; } }
  .ix-per { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:12px; }
  .ix-per .inc-seg { flex-wrap:wrap; }
  .ix-dates { display:flex; gap:6px; align-items:center; font-size:13px; color:#475569; }
  .ix-dates input { width:150px; padding:7px 8px; font-size:13px; }
  .ix-btn { border:1px solid #CBD5E1; background:#fff; border-radius:9px; padding:7px 12px; font-size:13px; font-weight:700; color:#0B1F3A; cursor:pointer; font-family:inherit; display:inline-flex; align-items:center; gap:6px; white-space:nowrap; }
  .ix-btn.pri { background:#0B1F3A; border-color:#0B1F3A; color:#fff; }
  .ix-btn.ok { background:#059669; border-color:#059669; color:#fff; }
  .ix-btn.no { color:#B3241C; border-color:#F3C4C7; }
  .ix-btn:disabled { opacity:.5; cursor:default; }
  .ix-chg { font-size:12px; font-weight:700; }
  .ix-chg.up { color:#059669; } .ix-chg.dn { color:#B3241C; }
  .ix-2 { display:grid; grid-template-columns:minmax(0,1fr); gap:12px; }
  @media (min-width:760px) { .ix-2 { grid-template-columns:repeat(2, minmax(0,1fr)); } .ix-2 > .inc-card { margin-bottom:0; } }
  .ix-2 { margin-bottom:12px; }
  .ix-stat-row { display:flex; justify-content:space-between; align-items:center; gap:8px; padding:8px 0; border-top:1px solid #EEF2F7; font-size:13.5px; cursor:pointer; }
  .ix-stat-row:first-of-type { border-top:0; }
  .ix-stat-row b { font-family:var(--font-mono); }
  .ix-stat-row .dot { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:8px; vertical-align:-1px; }
  .ix-meter { display:flex; height:10px; border-radius:999px; overflow:hidden; background:#EEF2F7; margin:8px 0 10px; }
  .ix-tbl { width:100%; border-collapse:collapse; font-size:13px; }
  .ix-tbl th { background:transparent; color:var(--hint); font-size:11px; text-transform:none; letter-spacing:0; padding:6px 4px; border-bottom:1px solid var(--border); font-weight:700; }
  .ix-tbl td { padding:8px 4px; border-bottom:1px solid #EEF2F7; }
  .ix-tbl td.n, .ix-tbl th.n { text-align:right; font-family:var(--font-mono); white-space:nowrap; }
  .ix-tbl tr.clk { cursor:pointer; } .ix-tbl tr.clk:hover td { background:#F8FAFC; }
  .ix-tools { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
  .ix-tools .ix-search { flex:1 1 220px; position:relative; }
  .ix-tools .ix-search input { padding-left:34px; }
  .ix-tools .ix-search i { position:absolute; left:12px; top:50%; transform:translateY(-50%); color:var(--hint); }
  .ix-tools select { padding:9px 10px; border-radius:10px; border:1.5px solid var(--border); background:#fff; font-family:inherit; font-size:14px; color:var(--text); max-width:100%; }
  .ix-chips { display:flex; gap:6px; overflow-x:auto; padding-bottom:4px; margin-bottom:10px; scrollbar-width:none; }
  .ix-chips::-webkit-scrollbar { display:none; }
  .ix-chips button { flex:none; border:1px solid var(--border); background:#fff; border-radius:999px; padding:6px 11px; font-size:12.5px; font-weight:700; color:#334155; cursor:pointer; font-family:inherit; white-space:nowrap; }
  .ix-chips button.on { background:#0B1F3A; border-color:#0B1F3A; color:#fff; }
  .ix-chips button span { opacity:.7; margin-left:3px; }
  .ix-sum { display:flex; justify-content:space-between; align-items:center; gap:10px; font-size:13px; color:#475569; margin:0 2px 8px; flex-wrap:wrap; }
  .ix-sum label { text-transform:none; letter-spacing:0; font-size:13px; color:#334155; display:flex; align-items:center; gap:6px; margin:0; cursor:pointer; }
  .ix-sum input[type=checkbox], .ix-row input[type=checkbox] { width:18px; height:18px; margin:0; accent-color:#0B1F3A; flex:none; }
  .ix-list { background:#fff; border:1px solid var(--border); border-radius:14px; overflow:hidden; }
  .ix-row { display:grid; grid-template-columns:24px minmax(0,1fr) auto; gap:10px; align-items:center; padding:10px 12px; border-top:1px solid #EEF2F7; cursor:pointer; }
  .ix-row:first-child { border-top:0; }
  .ix-row:hover { background:#F8FAFC; }
  .ix-row.sel { background:#EFF6FF; }
  .ix-row .nm { font-weight:700; font-size:14px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ix-row .sb { font-size:12px; color:#64748B; margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ix-row .rt { text-align:right; }
  .ix-row .rt b { display:block; font-family:var(--font-mono); font-size:13px; white-space:nowrap; }
  .ix-row .cols { display:none; }
  @media (min-width:760px) {
    .ix-row { grid-template-columns:24px minmax(0,1.6fr) 120px 100px 110px 110px; }
    .ix-row .rt { display:none; }
    .ix-row .cols { display:contents; }
    .ix-row .cols > div { font-size:13px; text-align:right; font-family:var(--font-mono); white-space:nowrap; }
    .ix-row .cols > div.st { text-align:left; font-family:inherit; }
    .ix-head { display:grid !important; }
  }
  .ix-head { display:none; grid-template-columns:24px minmax(0,1.6fr) 120px 100px 110px 110px; gap:10px; padding:8px 12px; font-size:11px; font-weight:700; color:var(--hint); background:#F8FAFC; border-bottom:1px solid var(--border); }
  .ix-head > div:nth-child(n+4) { text-align:right; }
  .ix-head .srt { cursor:pointer; } .ix-head .srt.on { color:#0B1F3A; }
  .ix-pill { display:inline-block; border-radius:999px; padding:2px 8px; font-size:11.5px; font-weight:700; white-space:nowrap; }
  .ix-pill.trial { background:#EDE9FE; color:#5B21B6; }
  .ix-pill.paying { background:#DCFCE7; color:#166534; }
  .ix-pill.soon { background:#FEF3C7; color:#92400E; }
  .ix-pill.grace { background:#FFEDD5; color:#9A3412; }
  .ix-pill.blocked { background:#FEE2E2; color:#991B1B; }
  .ix-pill.lifetime { background:#DBEAFE; color:#1E40AF; }
  .ix-pill.unset, .ix-pill.off { background:#F1F5F9; color:#475569; }
  .ix-pill.chk { background:#FEF3C7; color:#92400E; margin-left:4px; }
  .ix-pager { display:flex; justify-content:center; align-items:center; gap:10px; margin:12px 0; font-size:13px; color:#475569; }
  .ix-bulk { position:sticky; bottom:10px; z-index:30; background:#0B1F3A; color:#fff; border-radius:14px; padding:10px 12px; margin-top:10px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; box-shadow:0 10px 30px rgba(11,31,58,.35); }
  .ix-bulk .t { font-weight:700; font-size:13.5px; margin-right:auto; }
  .ix-bulk button { border:0; background:rgba(255,255,255,.14); color:#fff; border-radius:9px; padding:8px 10px; font-size:12.5px; font-weight:700; cursor:pointer; font-family:inherit; }
  .ix-bulk button.x { background:transparent; font-size:16px; padding:4px 8px; }
  .ix-day { display:flex; justify-content:space-between; font-size:12px; font-weight:800; color:#64748B; text-transform:uppercase; letter-spacing:.4px; padding:12px 4px 6px; }
  .ix-pay { background:#fff; border:1px solid var(--border); border-radius:12px; padding:10px 12px; margin-bottom:6px; display:flex; justify-content:space-between; gap:10px; }
  .ix-pay.st-cancelled, .ix-pay.st-rejected { opacity:.55; }
  .ix-pay.st-pending { border-color:#FCD34D; background:#FFFBEB; }
  .ix-pay .nm { font-weight:700; font-size:14px; cursor:pointer; }
  .ix-pay .sb { font-size:12px; color:#64748B; margin-top:2px; }
  .ix-pay .am { font-family:var(--font-mono); font-weight:700; white-space:nowrap; text-align:right; }
  .ix-pay .act { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
  .ix-pay .act button, .ix-pay .act a { border:1px solid #CBD5E1; background:#fff; border-radius:7px; padding:4px 9px; font-size:12px; font-weight:700; color:#334155; cursor:pointer; text-decoration:none; font-family:inherit; }
  .ix-pay .act .ok { background:#059669; color:#fff; border-color:#059669; }
  .ix-pay .act .no { color:#B3241C; border-color:#F3C4C7; }
  .ix-ov { position:fixed; inset:0; z-index:5000; background:rgba(15,23,42,.55); display:none; }
  .ix-ov.open { display:block; }
  .ix-box { position:absolute; left:0; right:0; bottom:0; top:max(24px, env(safe-area-inset-top, 0px)); background:var(--bg); border-radius:20px 20px 0 0; overflow-y:auto; -webkit-overflow-scrolling:touch; padding:0 14px 30px; }
  .ix-box.sm { top:auto; max-height:92vh; }
  @media (min-width:900px) { .ix-box { left:50%; transform:translateX(-50%); width:720px; top:30px; bottom:30px; border-radius:20px; } .ix-box.sm { top:auto; bottom:auto; top:50%; transform:translate(-50%, -50%); width:520px; } }
  .ix-bh { position:sticky; top:0; background:var(--bg); display:flex; justify-content:space-between; align-items:flex-start; gap:10px; padding:16px 0 10px; z-index:2; }
  .ix-bh .t { font-weight:800; font-size:18px; color:var(--darkblue); }
  .ix-bh .s { font-size:12.5px; color:#64748B; margin-top:3px; }
  .ix-bh .x { border:0; background:#E2E8F0; width:34px; height:34px; border-radius:50%; font-size:15px; cursor:pointer; flex:none; }
  .ix-acts { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; }
  @media (min-width:600px) { .ix-acts { grid-template-columns:repeat(4, minmax(0,1fr)); } }
  .ix-acts button { border:1px solid #CBD5E1; background:#fff; border-radius:12px; padding:10px 6px; font-size:13px; font-weight:700; color:#0B1F3A; cursor:pointer; font-family:inherit; line-height:1.25; }
  .ix-acts button small { display:block; font-weight:600; color:#64748B; font-size:11.5px; margin-top:2px; }
  .ix-acts button.main { background:#0B1F3A; color:#fff; border-color:#0B1F3A; } .ix-acts button.main small { color:#B9C6DA; }
  .ix-form .field label { text-transform:none; letter-spacing:0; font-size:12.5px; color:#475569; font-weight:600; }
  .ix-sug { background:#fff; border:1px solid var(--border); border-radius:10px; margin-top:4px; max-height:220px; overflow-y:auto; }
  .ix-sug div { padding:9px 12px; font-size:14px; cursor:pointer; border-top:1px solid #EEF2F7; }
  .ix-sug div:first-child { border-top:0; } .ix-sug div:hover { background:#F1F5F9; }
  .ix-seg2 { display:flex; gap:6px; flex-wrap:wrap; }
  .ix-seg2 button { border:1.5px solid var(--border); background:#fff; border-radius:10px; padding:8px 12px; font-size:14px; font-weight:700; cursor:pointer; font-family:inherit; color:#334155; }
  .ix-seg2 button.on { border-color:#0B1F3A; background:#0B1F3A; color:#fff; }
  .ix-set h4 { margin:18px 0 8px; font-size:14px; color:var(--darkblue); }
  .ix-set h4:first-child { margin-top:0; }
  .ix-set .field label { text-transform:none; letter-spacing:0; font-size:12.5px; color:#475569; font-weight:600; }
  .ix-empty { text-align:center; color:var(--hint); padding:30px 10px; font-size:14px; }
  .ix-fc { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; }
  .ix-fc div { background:#F8FAFC; border-radius:10px; padding:10px; }
  .ix-fc b { display:block; font-family:var(--font-mono); font-size:15px; margin:3px 0; }
  .ix-fc span { font-size:12px; color:#64748B; }
  .inc-alert { display:flex; align-items:center; gap:10px; background:#FEF3C7; border:1.5px solid #FCD34D; border-radius:12px; padding:10px 12px; margin-bottom:12px; font-size:13.5px; font-weight:600; cursor:pointer; }
</style>
</head>
<body>
<div class="speedline"></div>
<div class="container">
  <div class="topbar">
    <div style="display:flex; align-items:center; gap:10px;">
      <div class="logo-badge"><i class="fa-solid fa-droplet"></i></div>
      <div>
        <h1 style="margin:0; line-height:1;"><span class="wordmark" style="font-size:28px;"><span class="wm-oil">Oil</span><span class="wm-book">Book</span></span></h1>
        <div class="logo-sub">Админ-панель платформы</div>
      </div>
    </div>
    <div style="display:flex; align-items:center; gap:14px;">
      <a class="logout" href="/admin/help"><i class="fa-solid fa-circle-question"></i> Справка</a>
      <a class="logout" href="/logout"><i class="fa-solid fa-arrow-right-from-bracket"></i> Выйти</a>
    </div>
  </div>

  <div id="msg"></div>

  <div class="adm-tabs" id="admTabs">
    <button class="on" data-t="main" onclick="admTab('main')"><i class="fa-solid fa-store"></i> Точки</button>
    <button data-t="income" onclick="admTab('income')"><i class="fa-solid fa-sack-dollar"></i> Доходы</button>
    <button data-t="map" onclick="admTab('map')"><i class="fa-solid fa-map-location-dot"></i> Карта</button>
    <button data-t="analytics" onclick="admTab('analytics')"><i class="fa-solid fa-chart-pie"></i> Аналитика</button>
  </div>
  <div id="admMain">

  <div class="adm-stats" id="admStats">
    <div class="adm-stat"><b>—</b><span>точек</span></div>
    <div class="adm-stat"><b>—</b><span>активных</span></div>
    <div class="adm-stat"><b>—</b><span>клиентов</span></div>
  </div>

  <details class="adm-sec" id="secReg">
    <summary>
      <span class="ic" style="background:#EFF6FF; color:#1D4ED8;"><i class="fa-solid fa-user-plus"></i></span>
      <span>Заявки на регистрацию<span class="sub" id="regSecSub">точки, которые зарегистрировались сами</span></span>
      <i class="fa-solid fa-chevron-down chev"></i>
    </summary>
    <div class="sec-body">
      <div id="regPending"><div class="hint-text">Загружаю…</div></div>
      <div style="font-weight:700; font-size:13px; margin:14px 0 8px;">Последние решения</div>
      <div id="regDone"></div>
      <div class="hint-text" style="margin-top:10px;">Ссылка для владельцев точек: <b id="regLink"></b></div>
    </div>
  </details>

  <details class="adm-sec" id="secAdd">
    <summary>
      <span class="ic" style="background:#ECFDF5; color:#059669;"><i class="fa-solid fa-plus"></i></span>
      <span>Добавить новую точку<span class="sub">логин, телефон, адрес, локация</span></span>
      <i class="fa-solid fa-chevron-down chev"></i>
    </summary>
    <div class="sec-body">
      <div class="field">
        <label>Название точки</label>
        <input id="new_shop_name" placeholder="Avto Servis Namangan">
      </div>
      <div class="field">
        <label>Группа (необяз.) — только чтобы точки одного владельца стояли рядом в списке</label>
        <input id="new_client_group" list="clientGroupsList" placeholder="например: Sinov01">
        <datalist id="clientGroupsList"></datalist>
      </div>
      <div class="row2">
        <div class="field">
          <label>Логин</label>
          <input id="new_username" placeholder="namangan_point">
        </div>
        <div class="field">
          <label>Пароль (пусто = сгенерировать)</label>
          <input id="new_password" placeholder="необязательно">
        </div>
      </div>
      <div class="row2">
        <div class="field">
          <label>Телефон точки</label>
          <input id="new_phone" placeholder="+998901112233">
        </div>
        <div class="field">
          <label>Telegram ID для уведомлений (необяз.)</label>
          <input id="new_notify_id" placeholder="123456789">
        </div>
      </div>
      <div class="field">
        <label>Адрес</label>
        <input id="new_address" placeholder="Наманган, ул. ...">
      </div>
      <div class="field">
        <label>Локация (необяз.) — широта и долгота из Google Карт через запятую</label>
        <input id="new_location" placeholder="40.782123, 72.344567">
        <div class="hint-text">Открой точку на Google Картах, нажми и удержи на месте — внизу появятся два числа через запятую, скопируй их сюда целиком.</div>
      </div>
      <div class="hint-text" style="margin:-2px 0 10px; color:#B45309;">⚠️ Это <b>самостоятельная</b> точка: она видит свою прибыль и закупочные цены. Если нужен <b>филиал</b> (без прибыли, с общим складом и статистикой у главного) — открой карточку главной точки → плитка «Филиалы» → «+ Добавить филиал».</div>
      <button class="submit" onclick="createShop()">Создать точку</button>
      <div id="newCreds"></div>
    </div>
  </details>

  <details class="adm-sec" id="secRef">
    <summary>
      <span class="ic" style="background:#FEF9C3; color:#A16207;"><i class="fa-solid fa-gift"></i></span>
      <span>Реферальная программа<span class="sub" id="refSecSub">бонусы за приглашённые точки</span></span>
      <i class="fa-solid fa-chevron-down chev"></i>
    </summary>
    <div class="sec-body">
      <div class="adm-stats" style="margin-bottom:12px;">
        <div class="adm-stat"><b id="refPendSum">—</b><span>к выплате, сум</span></div>
        <div class="adm-stat"><b id="refPaidSum">—</b><span>выплачено, сум</span></div>
        <div class="adm-stat"><b id="refWaitCnt">—</b><span>ещё не оплатили</span></div>
      </div>
      <div style="font-weight:700; font-size:13px; margin-bottom:8px;">К выплате</div>
      <div id="refPending"><div class="hint-text">Загружаю…</div></div>
      <div style="font-weight:700; font-size:13px; margin:14px 0 8px;">Приглашены, но ещё не оплатили</div>
      <div id="refWaiting"></div>
      <div style="font-weight:700; font-size:13px; margin:14px 0 8px;">Выплаченные</div>
      <div id="refPaid"></div>
      <div style="font-weight:700; font-size:13px; margin:16px 0 8px;">Указать вручную, кто пригласил точку</div>
      <div class="row2">
        <div class="field"><label>Приглашённая точка</label><select id="refSetShop"></select></div>
        <div class="field"><label>Кто пригласил</label><select id="refSetBy"></select></div>
      </div>
      <button class="submit" style="width:auto; padding:10px 20px;" onclick="saveReferrer()">Сохранить</button>
      <div class="hint-text" style="margin-top:10px;">Нужно, если точку создали в админке, а не по ссылке. Если точка уже платила — бонус начислится с её первой оплаты. Бонус = <span id="refPct">50</span>% от первой оплаты подписки, один раз. Деньги переводишь сам на карту из списка и нажимаешь «Выплачено» — точке придёт сообщение в Telegram.</div>
    </div>
  </details>

  <details class="adm-sec" id="secBackup">
    <summary>
      <span class="ic" style="background:#EFF6FF; color:var(--blue);"><i class="fa-solid fa-box-archive"></i></span>
      <span>Резервная копия<span class="sub">приходит в Telegram каждую ночь</span></span>
      <i class="fa-solid fa-chevron-down chev"></i>
    </summary>
    <div class="sec-body">
      <p class="hint-text" style="margin-top:0;">Если сомневаешься, что копия доходит, отправь её прямо сейчас. Если копии нет в чате с ботом, напиши боту <code>/myid</code> и сверь число с <code>ADMIN_TELEGRAM_ID</code> в настройках Render (Environment).</p>
      <button class="submit" style="width:auto; padding:10px 20px;" onclick="triggerBackupNow()"><i class="fa-solid fa-paper-plane"></i> Отправить сейчас</button>
      <div id="backupResult" style="margin-top:10px;"></div>
    </div>
  </details>

  <details class="adm-sec danger" id="secRestore">
    <summary>
      <span class="ic" style="background:#FEF2F2; color:#B3241C;"><i class="fa-solid fa-clock-rotate-left"></i></span>
      <span style="color:#B3241C;">Восстановить базу из копии<span class="sub">заменяет все данные — только при необходимости</span></span>
      <i class="fa-solid fa-chevron-down chev"></i>
    </summary>
    <div class="sec-body">
      <p class="hint-text" style="margin-top:0;">
        <b>Внимание:</b> это заменит АБСОЛЮТНО ВСЕ текущие данные платформы (все точки, клиентов, историю) на содержимое загруженного файла.
        Всё, что было добавлено после даты этой копии, будет потеряно безвозвратно.<br>
        Перед заменой мы сами отправим тебе копию ТЕКУЩЕГО состояния — на случай, если восстановление окажется ошибкой.
      </p>
      <div class="field">
        <label>Файл резервной копии (.db)</label>
        <input type="file" id="restore_file" multiple>
      </div>
      <div class="field">
        <label>Чтобы подтвердить, впиши слово <code>ЗАМЕНИТЬ</code></label>
        <input id="restore_confirm" placeholder="ЗАМЕНИТЬ">
      </div>
      <button class="submit" style="width:auto; padding:10px 20px; background:linear-gradient(135deg, #DC2626, #991B1B);" onclick="triggerRestore()">Восстановить из этого файла</button>
      <div id="restoreResult" style="margin-top:10px;"></div>
    </div>
  </details>

  <div class="list-head">
    <h2>Все точки</h2>
  </div>
  <input id="shopSearch" type="search" name="oilbook_shop_q" autocomplete="off" spellcheck="false" placeholder="🔍 Поиск по названию, логину или телефону..." oninput="filterShops()">
  <div class="adm-filters" id="admFilters">
    <button class="on" data-f="all" onclick="setShopFilter('all')">Все</button>
    <button data-f="active" onclick="setShopFilter('active')">Активные</button>
    <button data-f="off" onclick="setShopFilter('off')">Выключенные</button>
    <button data-f="notg" onclick="setShopFilter('notg')">Без Telegram</button>
    <button data-f="debt" onclick="setShopFilter('debt')">Должники</button>
    <button data-f="soon" onclick="setShopFilter('soon')">Скоро истекает</button>
    <button data-f="check" onclick="setShopFilter('check')">Чек ждёт</button>
    <button data-f="life" onclick="setShopFilter('life')">∞ Бессрочные</button>
    <button data-f="unset" onclick="setShopFilter('unset')">Без даты</button>
    <button data-f="trial" onclick="setShopFilter('trial')">🎁 Пробные</button>
  </div>
  <div id="shops-body"></div>
  </div>
  <div id="admIncome" style="display:none;">
    <div class="ix-tabs" id="ixTabs">
      <button class="on" data-x="ov" onclick="ixTab('ov')"><i class="fa-solid fa-chart-line"></i> Обзор</button>
      <button data-x="shops" onclick="ixTab('shops')"><i class="fa-solid fa-store"></i> Точки</button>
      <button data-x="pays" onclick="ixTab('pays')"><i class="fa-solid fa-receipt"></i> Оплаты <span class="cnt" id="ixChkCnt" hidden></span></button>
      <button data-x="set" onclick="ixTab('set')"><i class="fa-solid fa-sliders"></i> Настройки</button>
    </div>
    <div class="ix-per" id="ixPer">
      <span class="inc-seg" id="ixPerSeg">
        <button data-p="month" class="on" onclick="ixSetPeriod('month')">Этот месяц</button>
        <button data-p="prev" onclick="ixSetPeriod('prev')">Прошлый</button>
        <button data-p="3m" onclick="ixSetPeriod('3m')">3 мес</button>
        <button data-p="year" onclick="ixSetPeriod('year')">Год</button>
        <button data-p="custom" onclick="ixSetPeriod('custom')">Свой</button>
      </span>
      <span class="ix-dates" id="ixDates" hidden>
        <input type="date" id="ixFrom" onchange="ixCustomDates()"> — <input type="date" id="ixTo" onchange="ixCustomDates()">
      </span>
      <button class="ix-btn" onclick="ixExport()" style="margin-left:auto;"><i class="fa-solid fa-file-excel" style="color:#15803D;"></i> Excel</button>
    </div>
    <div id="ixOv"><div class="hint-text">Загружаю…</div></div>
    <div id="ixShops" hidden>
      <div class="ix-tools">
        <div class="ix-search"><i class="fa-solid fa-magnifying-glass"></i><input id="ixQ" placeholder="Название, логин, телефон, адрес" oninput="ixSearchSoon()"></div>
        <select id="ixGroup" onchange="IX.s.group = this.value; IX.s.page = 1; ixLoadShops();"><option value="*">Все сети</option></select>
        <select id="ixSort" onchange="IX.s.sort = this.value; IX.s.page = 1; ixLoadShops();">
          <option value="until">Сначала кому продлевать</option>
          <option value="monthly">Дороже в месяц</option>
          <option value="paid">Больше всего заплатили</option>
          <option value="last">Недавно платили</option>
          <option value="new">Новые точки</option>
          <option value="name">По названию</option>
        </select>
      </div>
      <div class="ix-chips" id="ixChips"></div>
      <div class="ix-sum" id="ixShopSum"></div>
      <div class="ix-list" id="ixShopList"></div>
      <div class="ix-pager" id="ixShopPager"></div>
      <div class="ix-bulk" id="ixBulk" hidden>
        <span class="t" id="ixBulkT"></span>
        <button onclick="ixBulkExtend()">Продлить</button>
        <button onclick="ixBulkDays()">+ Дни</button>
        <button onclick="ixBulkPrice()">Цена</button>
        <button onclick="ixBulkMsg()">Сообщение</button>
        <button class="x" onclick="ixClearSel()" aria-label="Снять выбор">✕</button>
      </div>
    </div>
    <div id="ixPays" hidden>
      <div class="ix-tools">
        <div class="ix-search"><i class="fa-solid fa-magnifying-glass"></i><input id="ixPQ" placeholder="Точка" oninput="ixPaySearchSoon()"></div>
        <select id="ixPMethod" onchange="IX.p.method = this.value; IX.p.page = 1; ixLoadPays();">
          <option value="">Любой способ</option><option value="card">Перевод (чек)</option><option value="hamyon">Автооплата</option><option value="cash">Наличные</option>
        </select>
        <select id="ixPKind" onchange="IX.p.kind = this.value; IX.p.page = 1; ixLoadPays();">
          <option value="">Всё</option><option value="extend">Продление</option><option value="both">Продление + филиалы</option><option value="branches">Филиалы</option><option value="lifetime">Бессрочная</option>
        </select>
        <button class="ix-btn pri" onclick="ixRecordOpen()"><i class="fa-solid fa-plus"></i> Записать оплату</button>
      </div>
      <div class="ix-chips" id="ixPStatus">
        <button data-s="confirmed" class="on" onclick="ixPayStatus('confirmed')">Оплачено</button>
        <button data-s="pending" onclick="ixPayStatus('pending')">На проверке</button>
        <button data-s="cancelled" onclick="ixPayStatus('cancelled')">Отменённые</button>
        <button data-s="all" onclick="ixPayStatus('all')">Все</button>
      </div>
      <div class="ix-sum" id="ixPaySum"></div>
      <div id="ixPayList"></div>
      <div class="ix-pager" id="ixPayPager"></div>
    </div>
    <div id="ixSet" hidden>
      <div class="inc-card ix-set">
        <h4>Цены в месяц, сум</h4>
        <div class="row2">
          <div class="field"><label>Главная точка</label><input id="ss_price_main" inputmode="numeric"></div>
          <div class="field"><label>Каждый филиал</label><input id="ss_price_branch" inputmode="numeric"></div>
        </div>
        <h4>Скидки за срок, %</h4>
        <div class="row2">
          <div class="field"><label>1 мес</label><input id="ss_disc_1" inputmode="numeric"></div>
          <div class="field"><label>3 мес</label><input id="ss_disc_3" inputmode="numeric"></div>
          <div class="field"><label>6 мес</label><input id="ss_disc_6" inputmode="numeric"></div>
          <div class="field"><label>12 мес</label><input id="ss_disc_12" inputmode="numeric"></div>
        </div>
        <div class="field"><label>Скидка на первый месяц для новых точек (после пробного периода), %</label><input id="ss_first_disc" inputmode="numeric"></div>
        <h4>Сроки и напоминания</h4>
        <div class="row2">
          <div class="field"><label>Пробный период, дней</label><input id="ss_trial_days" inputmode="numeric"></div>
          <div class="field"><label>Льготные дни после окончания</label><input id="ss_grace_days" inputmode="numeric"></div>
        </div>
        <div class="field"><label>Напоминать владельцу за … дней до конца (через запятую)</label><input id="ss_remind_days" placeholder="5,3,1"></div>
        <div class="hint-text" style="margin:-4px 0 6px;">Льготные дни: оплата закончилась, но точка ещё работает как обычно. 0 — режим просмотра со следующего дня.</div>
        <h4>♾ Безлимит (разовая оплата навсегда)</h4>
        <div class="row2">
          <div class="field"><label>Главная точка, $</label><input id="ss_lifetime_usd" inputmode="numeric"></div>
          <div class="field"><label>Каждый филиал, $</label><input id="ss_lifetime_branch_usd" inputmode="numeric"></div>
        </div>
        <div class="field"><label>Свой курс доллара, сум (0 — курс ЦБ автоматически)</label><input id="ss_usd_rate_manual" inputmode="numeric"></div>
        <div class="hint-text" id="ssRate" style="margin:0 0 6px;"></div>
        <h4>Реферальная программа</h4>
        <div class="field"><label>Бонус пригласившему, % от первой оплаты</label><input id="ss_ref_pct" inputmode="numeric"></div>
        <h4>Реквизиты для оплаты</h4>
        <div class="row2">
          <div class="field"><label>Номер карты</label><input id="ss_card_number" inputmode="numeric" placeholder="5614 0000 0000 0000"></div>
          <div class="field"><label>Имя на карте</label><input id="ss_card_holder" placeholder="Имя Фамилия"></div>
        </div>
        <div class="field"><label>Контакт поддержки (Telegram или телефон, необяз.)</label><input id="ss_support_contact" placeholder="@username или +998..."></div>
        <div class="hint-text" id="ssAuto" style="margin:0 0 10px;"></div>
        <button class="ix-btn pri" style="padding:12px 22px; font-size:14px;" onclick="saveSubSettings()"><i class="fa-solid fa-check"></i> Сохранить настройки</button>
        <div class="hint-text" style="margin-top:12px;">Точки «без даты» работают как раньше — поставь им дату в карточке точки, и подписка начнёт действовать. Данные при блокировке не удаляются.</div>
      </div>
    </div>
  </div>
  <div class="ix-ov" id="ixOvl" onclick="if (event.target === this) ixClose()"><div class="ix-box" id="ixBox"></div></div>
  <div id="admMap" style="display:none;">
    <div class="map-kpis" id="mapKpis"></div>
    <div class="map-bar">
      <div class="map-seg" id="mapDaysSeg">
        <button data-d="7" onclick="setMapDays(7)">7 дн</button>
        <button class="on" data-d="30" onclick="setMapDays(30)">30 дн</button>
        <button data-d="90" onclick="setMapDays(90)">3 мес</button>
      </div>
      <div class="map-seg" id="mapMetricSeg">
        <button class="on" data-m="count" onclick="setMapMetric('count')">Замены</button>
        <button data-m="total" onclick="setMapMetric('total')">Выручка</button>
      </div>
    </div>
    <div class="map-bar">
      <div class="map-seg" id="mapSubSeg">
        <button class="on" data-s="all" onclick="setMapSub('all')">Все</button>
        <button data-s="paid" onclick="setMapSub('paid')">Оплачено</button>
        <button data-s="soon" onclick="setMapSub('soon')">Скоро истекает</button>
        <button data-s="blocked" onclick="setMapSub('blocked')">Заблокировано</button>
      </div>
    </div>
    <div class="map-bar">
      <div class="map-seg" id="mapFilterSeg">
        <button class="on" data-f="all" onclick="setMapFilter('all')">Все</button>
        <button data-f="green" onclick="setMapFilter('green')">Работают</button>
        <button data-f="yellow" onclick="setMapFilter('yellow')">Реже</button>
        <button data-f="red" onclick="setMapFilter('red')">Молчат</button>
        <button data-f="off" onclick="setMapFilter('off')">Выкл.</button>
      </div>
      <select id="mapGroup" onchange="mapGroupSel=this.value; renderMap();"><option value="">Все сети</option></select>
      <label class="chk"><input type="checkbox" id="mapLinksChk" checked onchange="renderMap()"> Связи филиалов</label>
    </div>
    <div class="map-wrap">
      <div id="admMapBox"></div>
      <div class="map-pick" id="mapPick">
        <div id="mapPickText"></div>
        <div class="pk-act">
          <button class="pk-geo" onclick="mapPickHere()"><i class="fa-solid fa-location-crosshairs"></i> Я сейчас здесь</button>
          <button class="pk-cancel" onclick="mapPickCancel()">Отмена</button>
        </div>
      </div>
    </div>
    <div class="map-legend">
      <span><i class="dot" style="background:#16A34A"></i>замена за последние 3 дня</span>
      <span><i class="dot" style="background:#EAB308"></i>4–14 дней назад</span>
      <span><i class="dot" style="background:#DC2626"></i>больше 14 дней / не было</span>
      <span><i class="dot" style="background:#94A3B8"></i>выключена</span>
      <span>толстая обводка — главная точка</span>
    </div>
    <div class="map-list" id="mapNoCoords" style="display:none;"></div>
    <div class="map-list" id="mapRating"></div>
  </div>
  <div id="admAna" style="display:none;">
    <div class="map-bar" id="anaDaysBar">
      <div class="map-seg" id="anaDaysSeg">
        <button class="on" data-d="30" onclick="setAnaDays(30)">30 дн</button>
        <button data-d="90" onclick="setAnaDays(90)">3 мес</button>
        <button data-d="365" onclick="setAnaDays(365)">Год</button>
      </div>
    </div>
    <div id="anaFilters">
    <div class="ana-sel">
      <select id="anaGroup" onchange="anaGroup=this.value; anaShop=0; renderAna();"></select>
      <select id="anaShopSel" onchange="anaShop=Number(this.value)||0; renderAna();"></select>
    </div>
    <div class="ana-chips" id="anaCats"></div>
    </div>
    <div id="anaBody"><div class="hint-text">Загружаю…</div></div>
  </div>
</div>
<div class="snap-ov" id="snapOv" onclick="if (event.target === this) closeSnapshot()">
  <div class="snap-box">
    <div class="snap-head">
      <div><div class="sh-name" id="snapName">—</div><div class="sh-sub" id="snapSub"></div></div>
      <button class="sh-x" onclick="closeSnapshot()" aria-label="Закрыть">✕</button>
    </div>
    <div class="snap-body" id="snapBody"></div>
  </div>
</div>

<script>
function showMsg(text, ok) {
  const el = document.getElementById('msg');
  el.innerHTML = `<div class="msg ${ok ? 'ok' : 'err'}">${text}</div>`;
  setTimeout(() => { el.innerHTML = ''; }, 8000);
}

function showMsgSticky(text) {
  // не исчезает сама - для одноразовых паролей, которые больше нигде не
  // будут показаны повторно, чтобы админ точно успел их скопировать
  const el = document.getElementById('msg');
  el.innerHTML = `<div class="msg ok" style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
    <span>${text}</span>
    <button type="button" onclick="this.closest('.msg').remove()" style="flex:none; background:none; border:none; color:inherit; font-size:18px; cursor:pointer; padding:0 4px;">×</button>
  </div>`;
  // #msg находится в самом верху страницы — если действие вызвано далеко
  // внизу (например, сброс пароля филиала в развёрнутой панели), человек
  // иначе может не увидеть, что пароль вообще появился
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

let allShopsCache = [];

const fmtSum = n => (n == null ? '—' : Number(n).toLocaleString('ru-RU'));
function fmtDay(s) {
  if (!s) return '—';
  const p = String(s).slice(0, 10).split('-');
  return p.length === 3 ? `${p[2]}.${p[1]}.${p[0]}` : s;
}

function renderSubBlock(s) {
  const u = s.sub;
  if (!u) return '';
  let pill, cls = '';
  if (u.lifetime) pill = '<span class="sub-pill life">∞ бессрочная</span>';
  else if (!u.paid_until) pill = '<span class="sub-pill unset">без даты — работает</span>';
  else if (u.trial && u.expired) { pill = `<span class="sub-pill bad">пробный закончился ${fmtDay(u.paid_until)}</span>`; cls = 'bad'; }
  else if (u.trial) { pill = `<span class="sub-pill warn">🎁 пробный · ${u.days_left === 0 ? 'последний день' : 'осталось ' + (u.days_left + 1) + ' дн.'}</span>`; }
  else if (u.expired) { pill = `<span class="sub-pill bad">заблокирована с ${fmtDay(addDays(u.paid_until, 1))}</span>`; cls = 'bad'; }
  else if (u.days_left <= 5) { pill = `<span class="sub-pill warn">${u.days_left === 0 ? 'сегодня последний день' : 'осталось ' + u.days_left + ' дн.'}</span>`; cls = 'warn'; }
  else pill = '<span class="sub-pill ok">оплачено</span>';
  const name = escapeHtml(JSON.stringify(s.shop_name || s.username));
  const chk = u.pending_payment ? `
    <div class="sc-sub-chk">🧾 Чек на проверке: <b>${fmtSum(u.pending_payment.amount)} сум</b>
      ${u.pending_payment.has_receipt ? `<a href="/api/admin/sub/receipt/${u.pending_payment.id}" target="_blank" rel="noopener">открыть чек</a>` : ''}
      <button class="ok" onclick="decideSub(${u.pending_payment.id}, 1)">✅ Подтвердить</button>
      <button class="no" onclick="decideSub(${u.pending_payment.id}, 0)">❌ Отклонить</button>
    </div>` : '';
  const br = u.pending_branches ? `<div style="margin-top:6px; color:#9A3412;">⏳ Филиалов ждут оплаты: <b>${u.pending_branches}</b> — открой «Филиалы»</div>` : '';
  const lp = u.lifetime_payment;
  const btns = u.lifetime ? `
      ${lp ? `<button onclick="editPayAmount(${lp.id}, ${lp.amount || 0})">✏️ Сумма покупки</button>` : ''}
      <button class="grey" onclick="subLifetime(${s.id}, 0, ${name})">Снять ∞ (вернуть подписку)</button>` : `
      <button onclick="subExtend(${s.id}, 1, ${name})">+1 мес</button>
      <button onclick="subExtend(${s.id}, 3, ${name})">+3</button>
      <button onclick="subExtend(${s.id}, 6, ${name})">+6</button>
      <button onclick="subExtend(${s.id}, 12, ${name})">+12</button>
      <button class="grey" onclick="subSetDate(${s.id}, ${escapeHtml(JSON.stringify(u.paid_until || ''))})">📅 Дата</button>
      <button class="grey" onclick="subPrice(${s.id}, ${u.custom_price || 0}, ${name})">💲 Цена</button>
      <button class="grey" onclick="subLifetime(${s.id}, 1, ${name})">∞ Разовая покупка</button>`;
  return `
    <div class="sc-sub ${cls}">
      <div class="sc-sub-top">${pill}
        ${!u.lifetime ? `${u.paid_until ? `<span>до <b>${fmtDay(u.paid_until)}</b></span>` : ''}<span>${fmtSum(u.monthly)} сум/мес${u.branch_count ? ' · ' + u.branch_count + ' фил.' : ''}</span>${u.custom_price ? `<span class="sub-pill unset">индив. цена ${fmtSum(u.custom_price)}</span>` : ''}`
          : `<span>${lp && lp.amount ? 'куплено за <b>' + fmtSum(lp.amount) + ' сум</b>' : '<span style="color:#B45309;">сумма покупки не указана</span>'}</span>`}
      </div>
      ${chk}${br}
      <div class="sc-sub-btns">${btns}</div>
    </div>`;
}


function regCard(r, withButtons) {
  const tgPh = r.tg_phone || '—';
  const same = r.tg_phone && r.phone && r.tg_phone.replace(/[^0-9]/g, '') === r.phone.replace(/[^0-9]/g, '');
  const tg = r.tg_username ? '@' + r.tg_username : 'без @username';
  const st = r.status === 'approved' ? '<span class="sub-pill ok">одобрена</span>'
           : r.status === 'rejected' ? '<span class="sub-pill unset">отклонена</span>' : '';
  const lines = [
    `<b>${escapeHtml(r.shop_name)}</b> ${st}`,
    `Владелец: ${escapeHtml(r.owner_name || '—')} · ${escapeHtml(r.city || '')}`,
    `Адрес: ${escapeHtml(r.address || '—')}`,
    `Телефон: ${escapeHtml(r.phone || '—')} · в Telegram: ${escapeHtml(tgPh)} ${r.tg_phone ? (same ? '✅' : '⚠️ отличается') : ''}`,
    `Telegram: ${escapeHtml(tg)} · ${escapeHtml(r.tg_name || '')}`,
    `Локация: ${r.lat != null && r.lon != null ? `<a href="https://maps.google.com/?q=${Number(r.lat).toFixed(6)},${Number(r.lon).toFixed(6)}" target="_blank" rel="noopener">📍 открыть на карте</a>` : '—'}`,
    `Логин: <b>${escapeHtml(r.username)}</b> · язык ${escapeHtml((r.language || 'ru').toUpperCase())}`,
  ];
  if (r.ref_name) lines.push(`🎁 Пригласил: <b>${escapeHtml(r.ref_name)}</b>`);
  const when = withButtons ? `подтверждена ${escapeHtml(r.confirmed_at || r.created_at || '')}` : `решение ${escapeHtml(r.decided_at || '')}`;
  return `<div class="pay-item"><div class="pay-cap" style="white-space:normal; line-height:1.6;">${lines.join('<br>')}</div>
    <div class="hint-text" style="margin-top:4px;">№${r.id} · ${when}</div>
    ${withButtons ? `<div class="pay-act">
      <button class="ok" onclick="decideReg(${r.id}, 1)">✅ Одобрить (3 дня)</button>
      <button class="no" onclick="decideReg(${r.id}, 0)">❌ Отклонить</button></div>` : ''}
  </div>`;
}

async function loadRegs() {
  try {
    const res = await fetch('/api/admin/registrations');
    const d = await res.json();
    if (!d.ok) return;
    const pend = d.pending || [], done = d.done || [];
    document.getElementById('regPending').innerHTML = pend.length ? pend.map(r => regCard(r, true)).join('')
      : '<div class="hint-text">Новых заявок нет.</div>';
    document.getElementById('regDone').innerHTML = done.length ? done.map(r => regCard(r, false)).join('')
      : '<div class="hint-text">Пока пусто.</div>';
    document.getElementById('regSecSub').textContent = pend.length ? `ждут решения: ${pend.length}` : 'точки, которые зарегистрировались сами';
    document.getElementById('regLink').textContent = location.origin + '/register';
    const sec = document.getElementById('secReg');
    if (pend.length && !sec.dataset.autoOpened) { sec.open = true; sec.dataset.autoOpened = '1'; }
  } catch (e) {}
}

let REF = null;
function refItem(r, withBtn) {
  const card = r.ref_card ? `<b style="font-family:var(--font-mono, monospace);">${escapeHtml(r.ref_card)}</b>
      <button type="button" class="ref-cp" onclick="copyRefCard(this, ${JSON.stringify(r.ref_card).replace(/"/g, '&quot;')})"><i class="fa-regular fa-copy"></i></button>`
    : '<span style="color:#B45309;">карта не указана — точка вписывает её в разделе «Пригласи друга»</span>';
  const lines = [
    `<b>${escapeHtml(r.ref_name || '—')}</b> <span class="hint-text">@${escapeHtml(r.ref_username || '')}</span>`,
    `За точку: ${escapeHtml(r.new_name || '—')} <span class="hint-text">@${escapeHtml(r.new_username || '')}</span>`,
    `Оплата ${fmtSum(r.base_amount)} сум → бонус <b>${fmtSum(r.reward_amount)} сум</b>`,
    withBtn ? `Карта: ${card}` : `Выплачено ${escapeHtml(fmtDay(r.paid_at))}`,
  ];
  return `<div class="pay-item"><div class="pay-cap" style="white-space:normal; line-height:1.6;">${lines.join('<br>')}</div>
    ${withBtn ? `<div class="pay-act"><button class="ok" onclick="refMarkPaid(${r.id}, ${JSON.stringify(fmtSum(r.reward_amount))}, ${JSON.stringify(r.ref_name || '').replace(/"/g, '&quot;')})">✅ Выплачено</button></div>` : ''}
  </div>`;
}

async function loadRefs() {
  try {
    const res = await fetch('/api/admin/referrals');
    const d = await res.json();
    if (!d.ok) return;
    REF = d;
    document.getElementById('refPendSum').textContent = fmtSum(d.pending_sum);
    document.getElementById('refPaidSum').textContent = fmtSum(d.paid_sum);
    document.getElementById('refWaitCnt').textContent = d.waiting.length;
    document.getElementById('refPct').textContent = d.pct;
    document.getElementById('refPending').innerHTML = d.pending.length ? d.pending.map(r => refItem(r, true)).join('')
      : '<div class="hint-text">Нечего выплачивать.</div>';
    document.getElementById('refPaid').innerHTML = d.paid.length ? d.paid.map(r => refItem(r, false)).join('')
      : '<div class="hint-text">Пока пусто.</div>';
    document.getElementById('refWaiting').innerHTML = d.waiting.length ? d.waiting.map(w =>
      `<div class="inc-row"><div>${escapeHtml(w.new_name || w.new_username)}<div class="r-s">пригласил: ${escapeHtml(w.ref_name || w.ref_username || '—')}</div></div>
       <div class="r-s">${escapeHtml(fmtDay(w.created_at))}</div></div>`).join('')
      : '<div class="hint-text">Пока пусто.</div>';
    document.getElementById('refSecSub').textContent = d.pending.length
      ? `к выплате: ${d.pending.length} на ${fmtSum(d.pending_sum)} сум` : 'бонусы за приглашённые точки';
    const opt = s => `<option value="${s.id}">${escapeHtml(s.shop_name || s.username)} (@${escapeHtml(s.username)})</option>`;
    const a = document.getElementById('refSetShop'), b = document.getElementById('refSetBy');
    const keepA = a.value, keepB = b.value;
    a.innerHTML = '<option value="">— выберите —</option>' + d.shops.map(opt).join('');
    b.innerHTML = '<option value="0">— никто (убрать) —</option>' + d.shops.map(opt).join('');
    a.value = keepA; b.value = keepB || '0';
    a.onchange = () => { const s = d.shops.find(x => String(x.id) === a.value); b.value = s && s.referred_by ? String(s.referred_by) : '0'; };
    const sec = document.getElementById('secRef');
    if (d.pending.length && !sec.dataset.autoOpened) { sec.open = true; sec.dataset.autoOpened = '1'; }
  } catch (e) {}
}

function copyRefCard(btn, card) {
  const plain = String(card).replace(/[^0-9]/g, '');
  const done = () => { const old = btn.innerHTML; btn.innerHTML = '<i class="fa-solid fa-check"></i>'; setTimeout(() => { btn.innerHTML = old; }, 1500); };
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(plain).then(done, () => prompt('Скопируйте:', plain));
  else prompt('Скопируйте:', plain);
}

async function refMarkPaid(id, sum, name) {
  if (!confirm(`Ты перевёл ${sum} сум точке «${name}»? Точке придёт сообщение, что бонус выплачен.`)) return;
  const res = await fetch(`/api/admin/referrals/${id}/paid`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) showMsg('✅ Отмечено как выплачено', true);
  else showMsg('Ошибка: ' + data.error, false);
  loadRefs();
}

async function saveReferrer() {
  const shopId = document.getElementById('refSetShop').value;
  const by = document.getElementById('refSetBy').value;
  if (!shopId) { showMsg('Выберите приглашённую точку', false); return; }
  const res = await fetch(`/api/admin/shops/${shopId}/referrer`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({referrer_id: Number(by) || null})
  });
  const data = await res.json();
  if (data.ok) showMsg(Number(by) ? '✅ Сохранено' : '✅ Привязка убрана', true);
  else showMsg('Ошибка: ' + data.error, false);
  loadRefs();
}

async function decideReg(id, ok) {
  if (!ok && !confirm('Отклонить заявку? Человеку придёт сообщение в Telegram.')) return;
  const res = await fetch(`/api/admin/registrations/${id}/${ok ? 'approve' : 'reject'}`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) showMsg(ok ? `✅ Точка создана, пробный период до ${fmtDay(data.paid_until)}` : 'Заявка отклонена', true);
  else showMsg('Ошибка: ' + data.error, false);
  loadRegs(); loadShops();
}

function addDays(day, n) {
  const d = new Date(String(day).slice(0, 10) + 'T00:00:00');
  d.setDate(d.getDate() + n);
  const z = x => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}

async function subAction(shopId, body) {
  const res = await fetch(`/api/admin/shops/${shopId}/sub`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  return res.json();
}

async function subExtend(shopId, months, name) {
  if (!confirm(`Продлить «${name}» на ${months} мес. (оплата наличными)?`)) return;
  const data = await subAction(shopId, {action: 'extend', months});
  if (data.ok) { showMsg(`✅ Продлено до ${fmtDay(data.paid_until)}`, true); loadShops(); }
  else showMsg('Ошибка: ' + data.error, false);
}

async function subSetDate(shopId, current) {
  const v = prompt('Оплачено до (ДД.ММ.ГГГГ). Пусто — убрать дату (точка работает без подписки):', current ? fmtDay(current) : '');
  if (v === null) return;
  const data = await subAction(shopId, {action: 'set_until', date: v.trim()});
  if (data.ok) { showMsg(data.paid_until ? `✅ Дата: ${fmtDay(data.paid_until)}` : '✅ Дата убрана', true); loadShops(); }
  else showMsg('Ошибка: ' + data.error, false);
}

function askSum(text, current) {
  // null — нажали «Отмена»; '' — оставили пустым
  const v = prompt(text, current ? String(current) : '');
  if (v === null) return null;
  return v.replace(/[^0-9]/g, '');
}

async function subLifetime(shopId, on, name) {
  let amount = '';
  if (on) {
    amount = askSum(`«${name}» — разовая покупка (∞, без ежемесячной оплаты).\\nСумма, которую заплатили, в сумах (для статистики доходов):`, '');
    if (amount === null) return;
  } else if (!confirm(`Вернуть «${name}» на ежемесячную подписку? Запись о разовой покупке уберётся из статистики.`)) return;
  const data = await subAction(shopId, {action: 'lifetime', on: !!on, amount});
  if (data.ok) { showMsg('✅ Готово', true); loadShops(); } else showMsg('Ошибка: ' + data.error, false);
}

async function subPrice(shopId, current, name) {
  const v = askSum(`Индивидуальная цена главной точки «${name}», сум в месяц.\\nСкидки за срок к ней не применяются. Пусто — обычная цена.`, current || '');
  if (v === null) return;
  const data = await subAction(shopId, {action: 'price', price: v});
  if (data.ok) { showMsg(v ? `✅ Цена ${fmtSum(v)} сум/мес` : '✅ Обычная цена', true); loadShops(); }
  else showMsg('Ошибка: ' + data.error, false);
}

async function editPayAmount(paymentId, current) {
  const v = askSum('Сумма оплаты в сумах:', current || '');
  if (v === null) return;
  const res = await fetch(`/api/admin/sub/payments/${paymentId}/amount`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({amount: v})
  });
  const data = await res.json();
  if (data.ok) { showMsg('✅ Сумма сохранена', true); loadShops(); if (INC) loadIncome(); }
  else showMsg('Ошибка: ' + data.error, false);
}

async function cancelPayment(paymentId) {
  if (!confirm('Убрать эту оплату из статистики? Дата «оплачено до» не изменится — если нужно, поправьте её кнопкой «📅 Дата».')) return;
  const res = await fetch(`/api/admin/sub/payments/${paymentId}/cancel`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) { showMsg('✅ Убрано', true); loadIncome(); loadShops(); } else showMsg('Ошибка: ' + data.error, false);
}

async function decideSub(paymentId, ok) {
  if (!ok && !confirm('Отклонить этот чек? Точке придёт сообщение, что чек не принят.')) return;
  const res = await fetch(`/api/admin/sub/payments/${paymentId}/${ok ? 'confirm' : 'reject'}`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) showMsg(ok ? `✅ Подтверждено — до ${fmtDay(data.new_until)}` : 'Чек отклонён', true);
  else showMsg('Ошибка: ' + data.error, false);
  loadShops(); loadSubPanel();
}

async function markBranchPaid(shopId, branchId, name) {
  const amount = askSum(`Филиал «${name}» оплачен — он сразу заработает.\\nСумма, которую заплатили, в сумах (для статистики):`, '');
  if (amount === null) return;
  const res = await fetch(`/api/admin/branches/${branchId}/sub_paid`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({amount})
  });
  const data = await res.json();
  if (data.ok) { showMsg('✅ Филиал включён', true); loadBranches(shopId); }
  else showMsg('Ошибка: ' + data.error, false);
}

function admTab(t) {
  document.querySelectorAll('#admTabs button').forEach(b => b.classList.toggle('on', b.dataset.t === t));
  document.getElementById('admMain').style.display = t === 'main' ? '' : 'none';
  document.getElementById('admIncome').style.display = t === 'income' ? '' : 'none';
  document.getElementById('admMap').style.display = t === 'map' ? '' : 'none';
  document.getElementById('admAna').style.display = t === 'analytics' ? '' : 'none';
  if (t !== 'map' && typeof mapPickCancel === 'function' && mapPickId) mapPickCancel();
  try { history.replaceState(null, '', t === 'main' ? location.pathname : '#' + t); } catch (e) {}
  if (t === 'income') loadIncome();
  if (t === 'map') loadMap();
  if (t === 'analytics') loadAna();
  window.scrollTo(0, 0);
}

const MONTHS_RU = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const MONTHS_FULL = ['январе', 'феврале', 'марте', 'апреле', 'мае', 'июне', 'июле', 'августе', 'сентябре', 'октябре', 'ноябре', 'декабре'];
function fmtShort(n) {
  n = Number(n) || 0;
  if (n >= 1000000) return (n / 1000000).toFixed(1).replace('.', ',').replace(',0', '') + ' млн';
  if (n >= 1000) return Math.round(n / 1000) + ' тыс';
  return String(n);
}
// ---------- Доходы: Обзор / Точки / Оплаты / Настройки ----------
const IX_ST = {
  trial: ['Пробный', '#7C3AED'], paying: ['Платит', '#16A34A'], soon: ['Скоро продление', '#F59E0B'],
  grace: ['Льготные дни', '#EA580C'], blocked: ['Заблокирована', '#DC2626'], lifetime: ['∞ Бессрочная', '#0F52BA'],
  unset: ['Без даты', '#94A3B8'], off: ['Выключена', '#CBD5E1']
};
const IX_KIND = { extend: 'продление', both: 'продление + филиалы', branches: 'филиалы', lifetime: '∞ бессрочная' };
const IX_METHOD = { cash: 'наличные', card: 'перевод (чек)', hamyon: 'автооплата' };
const IX = {
  tab: 'ov', period: 'month', from: '', to: '', ov: null, ovChart: 'auto',
  s: { q: '', status: 'all', group: '*', sort: 'until', page: 1, data: null, sel: new Set() },
  p: { q: '', status: 'confirmed', method: '', kind: '', page: 1, data: null },
  shop: null, loaded: {}
};
let INC = null;
function loadIncome() { ixTab(IX.tab, true); }

function ixIso(d) { const z = n => String(n).padStart(2, '0'); return d.getFullYear() + '-' + z(d.getMonth() + 1) + '-' + z(d.getDate()); }
function ixRange() {
  const now = new Date();
  if (IX.period === 'custom' && IX.from && IX.to) return [IX.from, IX.to];
  if (IX.period === 'prev') { const a = new Date(now.getFullYear(), now.getMonth() - 1, 1); const b = new Date(now.getFullYear(), now.getMonth(), 0); return [ixIso(a), ixIso(b)]; }
  if (IX.period === '3m') return [ixIso(new Date(now.getFullYear(), now.getMonth() - 2, 1)), ixIso(now)];
  if (IX.period === 'year') return [ixIso(new Date(now.getFullYear(), now.getMonth() - 11, 1)), ixIso(now)];
  return [ixIso(new Date(now.getFullYear(), now.getMonth(), 1)), ixIso(now)];
}
function ixQS(obj) { return Object.entries(obj).filter(([, v]) => v !== '' && v !== null && v !== undefined).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&'); }
async function ixGet(url) {
  const res = await fetch(url, { cache: 'no-store' });
  const d = await res.json();
  if (!d.ok) throw new Error(d.error || 'Ошибка');
  return d.data;
}
async function ixPost(url, body) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  let d = {};
  try { d = await res.json(); } catch (e) { d = { ok: false, error: 'нет ответа от сервера' }; }
  return d;
}
function ixPct(a, b) {
  if (!b) return a ? '<span class="ix-chg up">новое</span>' : '';
  const p = Math.round((a - b) / b * 100);
  return `<span class="ix-chg ${p >= 0 ? 'up' : 'dn'}">${p >= 0 ? '▲' : '▼'} ${Math.abs(p)}%</span>`;
}
function ixPill(st) { const s = IX_ST[st] || [st, '#94A3B8']; return `<span class="ix-pill ${st}">${s[0]}</span>`; }
function ixDaysTxt(h) {
  if (h.status === 'lifetime') return 'навсегда';
  if (h.days_left === null || h.days_left === undefined) return 'без даты';
  if (h.days_left < 0) return Math.abs(h.days_left) + ' дн. назад';
  if (h.days_left === 0) return 'сегодня последний день';
  return 'через ' + h.days_left + ' дн.';
}

function ixTab(t, force) {
  IX.tab = t;
  document.querySelectorAll('#ixTabs button').forEach(b => b.classList.toggle('on', b.dataset.x === t));
  document.getElementById('ixOv').hidden = t !== 'ov';
  document.getElementById('ixShops').hidden = t !== 'shops';
  document.getElementById('ixPays').hidden = t !== 'pays';
  document.getElementById('ixSet').hidden = t !== 'set';
  document.getElementById('ixPer').style.display = (t === 'ov' || t === 'pays') ? '' : 'none';
  if (t === 'ov') ixLoadOv();
  if (t === 'shops') ixLoadShops();
  if (t === 'pays') ixLoadPays();
  if (t === 'set') loadSubPanel();
  try { history.replaceState(null, '', '#income' + (t === 'ov' ? '' : '-' + t)); } catch (e) {}
}

function ixSetPeriod(p) {
  IX.period = p;
  document.querySelectorAll('#ixPerSeg button').forEach(b => b.classList.toggle('on', b.dataset.p === p));
  const dates = document.getElementById('ixDates');
  dates.hidden = p !== 'custom';
  if (p === 'custom') {
    const [f, t] = IX.from && IX.to ? [IX.from, IX.to] : ixRange();
    document.getElementById('ixFrom').value = f; document.getElementById('ixTo').value = t;
    IX.from = f; IX.to = t;
  }
  IX.p.page = 1;
  if (IX.tab === 'ov') ixLoadOv(); else if (IX.tab === 'pays') ixLoadPays();
}
function ixCustomDates() {
  const f = document.getElementById('ixFrom').value, t = document.getElementById('ixTo').value;
  if (!f || !t) return;
  IX.from = f; IX.to = t; IX.p.page = 1;
  if (IX.tab === 'ov') ixLoadOv(); else ixLoadPays();
}
function ixExport() {
  const [f, t] = ixRange();
  window.open('/api/admin/income/export?' + ixQS({ from: f, to: t }), '_blank');
}

// ----- Обзор -----
let ixOvSeq = 0;
async function ixLoadOv() {
  const box = document.getElementById('ixOv');
  const [f, t] = ixRange();
  const seq = ++ixOvSeq;
  if (!IX.ov) box.innerHTML = '<div class="hint-text">Загружаю…</div>';
  try {
    const d = await ixGet('/api/admin/income/overview?' + ixQS({ from: f, to: t }));
    if (seq !== ixOvSeq) return;
    IX.ov = d; INC = d;
    ixRenderOv();
  } catch (e) {
    if (seq === ixOvSeq) box.innerHTML = `<div class="msg err">${escapeHtml(e.message || 'Не удалось загрузить — проверьте интернет')}</div>`;
  }
}
function ixSetChart(m) { IX.ovChart = m; ixRenderOv(); }
function ixGoShops(status, group) {
  IX.s.status = status || 'all'; IX.s.page = 1; IX.s.sel.clear();
  if (group !== undefined) { IX.s.group = group; }
  ixTab('shops');
}
function ixRenderOv() {
  const d = IX.ov;
  if (!d) return;
  const c = d.counts;
  const per = `${fmtDay(d.from)} — ${fmtDay(d.to)}`;
  const alerts = [];
  if (d.pending.count) alerts.push(`<div class="inc-alert" onclick="ixPayStatus('pending'); ixTab('pays');">🧾 <span style="flex:1;">Чеков на проверке: ${d.pending.count} на ${fmtSum(d.pending.sum)} сум</span><i class="fa-solid fa-chevron-right"></i></div>`);
  if (c.blocked) alerts.push(`<div class="inc-alert" style="background:#FEF2F2; border-color:#FCA5A5;" onclick="ixGoShops('blocked')">🔒 <span style="flex:1;">Заблокированы, не продлили: ${c.blocked}</span><i class="fa-solid fa-chevron-right"></i></div>`);
  if (d.ref_owed && d.ref_owed.count) alerts.push(`<div class="inc-alert" style="background:#F0F9FF; border-color:#7DD3FC;" onclick="admTab('main'); const s = document.getElementById('secRef'); if (s) { s.open = true; s.scrollIntoView({behavior: 'smooth'}); }">🎁 <span style="flex:1;">Реферальные бонусы к выплате: ${d.ref_owed.count} на ${fmtSum(d.ref_owed.sum)} сум</span><i class="fa-solid fa-chevron-right"></i></div>`);
  const kpis = `
    <div class="inc-grid">
      <div class="inc-kpi main"><div class="k-l">Доход в месяц (подписки)</div><div class="k-v">${fmtSum(d.mrr)}</div><div class="k-s">${d.paying} точек платят · ${fmtShort(d.arr)} в год</div></div>
      <div class="inc-kpi"><div class="k-l">Получено за период</div><div class="k-v">${fmtSum(d.received)}</div><div class="k-s">${d.payments} оплат · ${ixPct(d.received, d.prev_received)} к прошлому</div></div>
      <div class="inc-kpi"><div class="k-l">Средний чек</div><div class="k-v">${fmtSum(d.avg)}</div><div class="k-s">доход с точки ${fmtShort(d.arpu)}/мес</div></div>
      <div class="inc-kpi"><div class="k-l">Новые платящие</div><div class="k-v">${d.new_paying}</div><div class="k-s">первая оплата за период</div></div>
      <div class="inc-kpi"><div class="k-l">Отток</div><div class="k-v" style="color:${d.churn_pct > 5 ? '#B3241C' : 'var(--darkblue)'};">${d.churn_pct}%</div><div class="k-s">${d.churned_count} не продлили · −${fmtShort(d.lost_mrr)}/мес</div></div>
      <div class="inc-kpi"><div class="k-l">Пробный → оплата</div><div class="k-v">${d.trial_conv === null ? '—' : d.trial_conv + '%'}</div><div class="k-s">${d.trial_total ? d.trial_paid + ' из ' + d.trial_total + ' новых' : 'новых регистраций нет'}</div></div>
      <div class="inc-kpi"><div class="k-l">Ожидается продлений</div><div class="k-v">${fmtSum(d.forecast[0] ? d.forecast[0].sum : 0)}</div><div class="k-s">в этом месяце · ${d.forecast[0] ? d.forecast[0].count : 0} точек</div></div>
      <div class="inc-kpi"><div class="k-l">Всего точек</div><div class="k-v">${d.total_shops}</div><div class="k-s">${c.trial} пробных · ${c.lifetime} бессрочных</div></div>
    </div>`;
  // график
  let mode = IX.ovChart;
  if (mode === 'auto') mode = d.daily.length && d.daily.length <= 92 ? 'days' : 'months';
  let series, labels, cur = -1, hint;
  if (mode === 'days' && d.daily.length) {
    series = d.daily.map(x => x[1]); labels = d.daily.map(x => x[0].slice(8)); hint = 'Деньги по дням выбранного периода.';
    cur = d.daily.findIndex(x => x[0] === ixIso(new Date()));
  } else {
    const src = mode === 'spread' ? d.months_spread : d.months_received;
    series = src; labels = d.months.map(m => MONTHS_RU[Number(m.slice(5)) - 1]); cur = series.length - 1;
    hint = mode === 'spread' ? 'Оплата за N месяцев разложена поровну на эти месяцы — реальный доход в месяц.' : 'Деньги в месяц, когда оплата подтверждена.';
  }
  const max = Math.max(1, ...series);
  const bars = series.map((v, i) => `<div class="inc-bar ${i === cur ? 'cur' : ''} ${v === max && v ? 'mx' : ''}" title="${labels[i]}: ${fmtSum(v)} сум"><span class="v">${v ? fmtShort(v) : ''}</span><div class="b" style="height:${Math.round(v / max * 100)}%;"></div><span class="m">${series.length > 16 && i % (series.length > 45 ? 7 : 3) ? '' : labels[i]}</span></div>`).join('');
  const chart = `
    <div class="inc-card">
      <h3>Поступления
        <span class="inc-seg">${d.daily.length ? `<button class="${mode === 'days' ? 'on' : ''}" onclick="ixSetChart('days')">По дням</button>` : ''}<button class="${mode === 'months' ? 'on' : ''}" onclick="ixSetChart('months')">12 месяцев</button><button class="${mode === 'spread' ? 'on' : ''}" onclick="ixSetChart('spread')">В пересчёте</button></span>
      </h3>
      <div class="inc-bars" style="${series.length > 40 ? 'gap:1px;' : ''}">${bars}</div>
      <div class="hint-text" style="margin-top:8px;">${hint} Период: ${per}.</div>
    </div>`;
  // статусы
  const order = ['paying', 'soon', 'trial', 'grace', 'blocked', 'lifetime', 'unset', 'off'];
  const tot = Math.max(1, d.total_shops);
  const stat = `
    <div class="inc-card">
      <h3>Точки по статусу <span class="hint-text" style="font-weight:600;">нажми, чтобы открыть список</span></h3>
      <div class="ix-meter">${order.filter(k => c[k]).map(k => `<div style="width:${c[k] / tot * 100}%; background:${IX_ST[k][1]};"></div>`).join('')}</div>
      ${order.map(k => `<div class="ix-stat-row" onclick="ixGoShops('${k}')"><span><i class="dot" style="background:${IX_ST[k][1]};"></i>${IX_ST[k][0]}</span><span><b>${c[k]}</b> <i class="fa-solid fa-chevron-right" style="color:#CBD5E1; font-size:11px;"></i></span></div>`).join('')}
    </div>`;
  const fc = `
    <div class="inc-card">
      <h3>Прогноз продлений</h3>
      <div class="ix-fc">${d.forecast.map(x => `<div><span>${MONTHS_RU[Number(x.month.slice(5)) - 1]} ${x.month.slice(0, 4)}</span><b>${fmtShort(x.sum)}</b><span>${x.count} точек</span></div>`).join('')}</div>
      <div class="hint-text" style="margin-top:8px;">Если все, у кого заканчивается оплата, продлят на тот же срок.</div>
    </div>`;
  const methTot = Math.max(1, d.by_method.card + d.by_method.hamyon + d.by_method.cash);
  const mcol = { card: '#0F52BA', hamyon: '#00A8E8', cash: '#16A34A' };
  const meth = `
    <div class="inc-card">
      <h3>Как платят <span class="hint-text" style="font-weight:600;">за период</span></h3>
      <div class="ix-meter">${['card', 'hamyon', 'cash'].filter(k => d.by_method[k]).map(k => `<div style="width:${d.by_method[k] / methTot * 100}%; background:${mcol[k]};"></div>`).join('')}</div>
      ${['card', 'hamyon', 'cash'].map(k => `<div class="ix-stat-row" style="cursor:default;"><span><i class="dot" style="background:${mcol[k]};"></i>${IX_METHOD[k]}</span><b>${fmtSum(d.by_method[k])}</b></div>`).join('')}
      <div style="height:8px;"></div>
      ${Object.keys(IX_KIND).map(k => `<div class="ix-stat-row" style="cursor:default;"><span>${IX_KIND[k]}</span><b>${fmtSum(d.by_kind[k] || 0)}</b></div>`).join('')}
    </div>`;
  const tTotal = Math.max(1, Object.values(d.terms).reduce((a, b) => a + b, 0));
  const terms = `
    <div class="inc-card">
      <h3>Какой срок выбирают <span class="hint-text" style="font-weight:600;">за период</span></h3>
      ${[1, 3, 6, 12].map(m => `<div class="inc-term"><span class="t-n">${m} мес</span><span class="t-bar"><div style="width:${(d.terms[m] || 0) / tTotal * 100}%;"></div></span><span class="t-c">${d.terms[m] || 0} · ${Math.round((d.terms[m] || 0) / tTotal * 100)}%</span></div>`).join('')}
    </div>`;
  const grp = d.groups.length > 1 || (d.groups[0] && d.groups[0].name) ? `
    <div class="inc-card">
      <h3>Сети <span class="hint-text" style="font-weight:600;">${d.groups_count} · по доходу в месяц</span></h3>
      <div style="overflow-x:auto;"><table class="ix-tbl">
        <tr><th>Сеть</th><th class="n">Точек</th><th class="n">Платят</th><th class="n">В месяц</th><th class="n">За период</th></tr>
        ${d.groups.map(g => `<tr class="clk" onclick='ixGoShops("all", ${JSON.stringify(g.name).replace(/'/g, "&#39;")})'><td>${g.name ? escapeHtml(g.name) : '<span style="color:var(--hint);">без сети</span>'}</td><td class="n">${g.shops}${g.branches ? ' +' + g.branches : ''}</td><td class="n">${g.paying}</td><td class="n">${fmtSum(g.mrr)}</td><td class="n">${fmtSum(g.received)}</td></tr>`).join('')}
      </table></div>
      <div class="hint-text" style="margin-top:6px;">«+N» — филиалы. Нажми на сеть — откроется список её точек.</div>
    </div>` : '';
  const churn = d.churned.length ? `
    <div class="inc-card">
      <h3>Не продлили за период <span class="hint-text" style="font-weight:600;">−${fmtSum(d.lost_mrr)} сум/мес</span></h3>
      ${d.churned.slice(0, 10).map(x => `<div class="inc-row" style="cursor:pointer;" onclick="ixOpenShop(${x.id})"><div><b>${escapeHtml(x.name)}</b><div class="r-s">${x.trial ? 'пробный закончился' : 'было оплачено до'} ${fmtDay(x.paid_until)}</div></div><span class="r-v" style="color:#B3241C;">${fmtSum(x.monthly)}/мес</span></div>`).join('')}
      ${d.churned_count > 10 ? `<button class="ix-btn" style="margin-top:8px;" onclick="ixGoShops('blocked')">Все заблокированные →</button>` : ''}
    </div>` : '';
  document.getElementById('ixOv').innerHTML = alerts.join('') + kpis + chart +
    `<div class="ix-2">${stat}${fc}</div><div class="ix-2">${meth}${terms}</div>` + grp + churn;
}

// ----- Точки -----
let ixShopSeq = 0, ixSearchT = null;
function ixSearchSoon() {
  clearTimeout(ixSearchT);
  ixSearchT = setTimeout(() => { IX.s.q = document.getElementById('ixQ').value.trim(); IX.s.page = 1; ixLoadShops(); }, 300);
}
function ixSetStatus(st) { IX.s.status = st; IX.s.page = 1; ixLoadShops(); }
function ixPage(n) { IX.s.page = n; ixLoadShops(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
async function ixLoadShops() {
  const seq = ++ixShopSeq;
  const list = document.getElementById('ixShopList');
  if (!IX.s.data) list.innerHTML = '<div class="ix-empty">Загружаю…</div>';
  const qs = ixQS({ q: IX.s.q, status: IX.s.status, group: IX.s.group === '*' ? '' : IX.s.group, sort: IX.s.sort, page: IX.s.page, per: 50 });
  try {
    const d = await ixGet('/api/admin/income/shops?' + qs + (IX.s.group === '' ? '&group=' : ''));
    if (seq !== ixShopSeq) return;
    IX.s.data = d;
    ixRenderShops();
  } catch (e) {
    if (seq === ixShopSeq) list.innerHTML = `<div class="ix-empty">${escapeHtml(e.message || 'Ошибка загрузки')}</div>`;
  }
}
function ixRenderShops() {
  const d = IX.s.data;
  if (!d) return;
  document.getElementById('ixQ').value !== IX.s.q && document.activeElement !== document.getElementById('ixQ') && (document.getElementById('ixQ').value = IX.s.q);
  const gs = document.getElementById('ixGroup');
  const cur = IX.s.group;
  gs.innerHTML = '<option value="*">Все сети</option>' + d.groups.map(g => `<option value="${escapeHtml(g)}">${g ? escapeHtml(g) : 'Без сети'}</option>`).join('');
  gs.value = cur;
  document.getElementById('ixSort').value = IX.s.sort;
  const c = d.counts;
  const chips = [['all', 'Все', c.all], ['attention', 'Требуют внимания', c.soon + c.grace + c.blocked + c.trial], ['check', '🧾 Чек или филиал ждёт', c.check],
    ['paying', 'Платят', c.paying], ['soon', 'Скоро продление', c.soon], ['trial', 'Пробные', c.trial], ['grace', 'Льготные', c.grace],
    ['blocked', 'Заблокированы', c.blocked], ['lifetime', '∞', c.lifetime], ['unset', 'Без даты', c.unset], ['off', 'Выкл.', c.off]];
  document.getElementById('ixChips').innerHTML = chips.filter(x => x[0] === 'all' || x[0] === IX.s.status || x[2])
    .map(x => `<button class="${IX.s.status === x[0] ? 'on' : ''}" onclick="ixSetStatus('${x[0]}')">${x[1]}<span>${x[2]}</span></button>`).join('');
  const allSel = d.ids.length && d.ids.every(id => IX.s.sel.has(id));
  document.getElementById('ixShopSum').innerHTML = `
    <label><input type="checkbox" ${allSel ? 'checked' : ''} onchange="ixSelAll(this.checked)"> Выбрать все ${d.total}</label>
    <span>Найдено <b>${d.total}</b> · платят на <b>${fmtSum(d.sum_monthly)}</b> сум/мес</span>`;
  const head = `<div class="ix-head"><div></div><div class="srt ${IX.s.sort === 'name' ? 'on' : ''}" onclick="ixSort('name')">Точка</div><div>Статус</div><div class="srt ${IX.s.sort === 'until' ? 'on' : ''}" onclick="ixSort('until')">До</div><div class="srt ${IX.s.sort === 'monthly' ? 'on' : ''}" onclick="ixSort('monthly')">В месяц</div><div class="srt ${IX.s.sort === 'paid' ? 'on' : ''}" onclick="ixSort('paid')">Всего</div></div>`;
  const rows = d.rows.map(h => {
    const sel = IX.s.sel.has(h.id);
    const sub = [h.client_group, h.phone, h.branches ? h.branches + ' фил.' : '', h.custom_price ? 'своя цена' : ''].filter(Boolean).map(escapeHtml).join(' · ');
    const chk = h.pending ? '<span class="ix-pill chk">🧾 чек</span>' : (h.branches_pending ? '<span class="ix-pill chk">филиал ждёт</span>' : '');
    return `<div class="ix-row ${sel ? 'sel' : ''}" onclick="ixOpenShop(${h.id})">
      <input type="checkbox" ${sel ? 'checked' : ''} onclick="event.stopPropagation(); ixSel(${h.id}, this.checked)">
      <div style="min-width:0;"><div class="nm">${escapeHtml(h.name)}${chk}</div><div class="sb">${sub || escapeHtml(h.username)}</div></div>
      <div class="rt">${ixPill(h.status)}<b>${h.status === 'lifetime' ? '∞' : fmtSum(h.monthly)}</b><span class="sb">${ixDaysTxt(h)}</span></div>
      <div class="cols"><div class="st">${ixPill(h.status)}</div><div>${h.paid_until ? fmtDay(h.paid_until) : '—'}</div><div>${h.status === 'lifetime' ? '∞' : fmtSum(h.monthly)}</div><div>${fmtSum(h.paid_total)}</div></div>
    </div>`;
  }).join('');
  document.getElementById('ixShopList').innerHTML = d.rows.length ? head + rows : '<div class="ix-empty">Ничего не найдено</div>';
  document.getElementById('ixShopPager').innerHTML = d.pages > 1 ? `
    <button class="ix-btn" ${d.page <= 1 ? 'disabled' : ''} onclick="ixPage(${d.page - 1})">‹ Назад</button>
    <span>${d.page} из ${d.pages}</span>
    <button class="ix-btn" ${d.page >= d.pages ? 'disabled' : ''} onclick="ixPage(${d.page + 1})">Дальше ›</button>` : '';
  ixBulkBar();
}
function ixSort(k) { IX.s.sort = k; IX.s.page = 1; ixLoadShops(); }
function ixSel(id, on) { if (on) IX.s.sel.add(id); else IX.s.sel.delete(id); ixRenderShops(); }
function ixSelAll(on) { (IX.s.data ? IX.s.data.ids : []).forEach(id => on ? IX.s.sel.add(id) : IX.s.sel.delete(id)); ixRenderShops(); }
function ixClearSel() { IX.s.sel.clear(); ixRenderShops(); }
function ixBulkBar() {
  const n = IX.s.sel.size;
  document.getElementById('ixBulk').hidden = !n;
  document.getElementById('ixBulkT').textContent = 'Выбрано: ' + n;
}
async function ixBulk(body, okText) {
  const d = await ixPost('/api/admin/income/bulk', Object.assign({ ids: [...IX.s.sel] }, body));
  if (!d.ok) { showMsg('Ошибка: ' + escapeHtml(d.error || ''), false); return; }
  showMsg(`✅ ${okText}: ${d.done}${d.skipped ? ' · пропущено ' + d.skipped : ''}`, true);
  IX.s.sel.clear(); IX.ov = null; ixLoadShops(); loadShops();
}
function ixBulkExtend() {
  ixModal('Продлить выбранные', `Выбрано точек: ${IX.s.sel.size}. Каждой запишется оплата наличными по её цене. Бессрочные и выключенные пропустятся.`,
    `<div class="ix-acts">${[1, 3, 6, 12].map(m => `<button onclick="ixClose(); ixBulk({action: 'extend', months: ${m}}, 'Продлено')">+${m} мес</button>`).join('')}</div>`);
}
function ixBulkDays() {
  ixModal('Подарить дни', `Выбрано точек: ${IX.s.sel.size}. Дни добавятся без записи об оплате (например, компенсация за сбой). Отрицательное число — убрать дни.`,
    `<div class="ix-form"><div class="field"><label>Сколько дней</label><input id="ixBD" inputmode="numeric" value="7"></div>
     <button class="ix-btn pri" onclick="const v = parseInt(document.getElementById('ixBD').value, 10); if (!v) return; ixClose(); ixBulk({action: 'days', days: v}, 'Готово')">Добавить</button></div>`);
}
function ixBulkPrice() {
  ixModal('Своя цена', `Выбрано точек: ${IX.s.sel.size}. Цена главной точки в месяц; скидки за срок к ней не применяются. Пусто — вернуть обычную цену.`,
    `<div class="ix-form"><div class="field"><label>Цена, сум в месяц</label><input id="ixBP" inputmode="numeric" placeholder="обычная цена"></div>
     <button class="ix-btn pri" onclick="const v = document.getElementById('ixBP').value.replace(/[^0-9]/g, ''); ixClose(); ixBulk({action: 'price', price: v}, v ? 'Цена задана' : 'Обычная цена')">Сохранить</button></div>`);
}
function ixBulkMsg() {
  ixModal('Сообщение в Telegram', `Выбрано точек: ${IX.s.sel.size}. Придёт владельцам, у кого подключён Telegram.`,
    `<div class="ix-form"><div class="field"><label>Текст</label><textarea id="ixBM" rows="5" style="width:100%; padding:10px; border-radius:10px; border:1.5px solid var(--border); font-family:inherit; font-size:15px;"></textarea></div>
     <button class="ix-btn pri" onclick="ixBulkMsgSend()"><i class="fa-brands fa-telegram"></i> Отправить</button></div>`);
}
async function ixBulkMsgSend() {
  const text = document.getElementById('ixBM').value.trim();
  if (text.length < 2) { showMsg('Напишите текст сообщения', false); return; }
  ixClose();
  const d = await ixPost('/api/admin/income/bulk', { ids: [...IX.s.sel], action: 'message', text });
  if (!d.ok) { showMsg('Ошибка: ' + escapeHtml(d.error || ''), false); return; }
  showMsg(`📨 Отправляется ${d.done} точкам${d.skipped ? ' · без Telegram: ' + d.skipped : ''}. Итог придёт тебе в Telegram.`, true);
  IX.s.sel.clear(); ixRenderShops();
}

// ----- Модальное окно -----
function ixModal(title, sub, body, small) {
  const box = document.getElementById('ixBox');
  box.className = 'ix-box' + (small === false ? '' : ' sm');
  box.innerHTML = `<div class="ix-bh"><div><div class="t">${title}</div>${sub ? `<div class="s">${sub}</div>` : ''}</div><button class="x" onclick="ixClose()" aria-label="Закрыть">✕</button></div>${body}`;
  document.getElementById('ixOvl').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function ixClose() {
  document.getElementById('ixOvl').classList.remove('open');
  document.body.style.overflow = '';
  IX.shop = null;
}

// ----- Карточка точки -----
async function ixOpenShop(id) {
  ixModal('Загружаю…', '', '<div class="hint-text">…</div>', false);
  try {
    const d = await ixGet('/api/admin/income/shop/' + id);
    IX.shop = d;
    ixRenderShop();
  } catch (e) { ixModal('Ошибка', escapeHtml(e.message || ''), '', true); }
}
function ixRenderShop() {
  const d = IX.shop;
  if (!d) return;
  const h = d.shop;
  const nm = escapeHtml(JSON.stringify(h.name));
  const life = h.status === 'lifetime';
  const info = `
    <div class="inc-grid">
      <div class="inc-kpi"><div class="k-l">Статус</div><div style="margin-top:6px;">${ixPill(h.status)}</div><div class="k-s" style="margin-top:4px;">${ixDaysTxt(h)}</div></div>
      <div class="inc-kpi"><div class="k-l">Оплачено до</div><div class="k-v">${life ? '∞' : (h.paid_until ? fmtDay(h.paid_until) : '—')}</div><div class="k-s">${h.last_period_months ? 'последний срок ' + h.last_period_months + ' мес' : '&nbsp;'}</div></div>
      <div class="inc-kpi"><div class="k-l">В месяц</div><div class="k-v">${fmtSum(h.monthly)}</div><div class="k-s">${h.custom_price ? 'своя цена ' + fmtSum(h.custom_price) : 'обычная цена'}${h.branches ? ' · ' + h.branches + ' фил.' : ''}</div></div>
      <div class="inc-kpi"><div class="k-l">Всего заплатила</div><div class="k-v">${fmtSum(h.paid_total)}</div><div class="k-s">${h.paid_count} оплат${h.last_paid ? ' · последняя ' + fmtDay(h.last_paid) : ''}</div></div>
    </div>`;
  const pend = d.payments.find(p => p.status === 'pending');
  const chk = pend ? `<div class="inc-alert" style="cursor:default; flex-wrap:wrap;">🧾 <span style="flex:1;">Чек на проверке: <b>${fmtSum(pend.amount)} сум</b> · ${pend.kind === 'lifetime' ? '∞' : (pend.months ? pend.months + ' мес' : IX_KIND[pend.kind] || '')}</span>
      ${pend.has_receipt ? `<a class="ix-btn" href="/api/admin/sub/receipt/${pend.id}" target="_blank" rel="noopener">Открыть чек</a>` : ''}
      <button class="ix-btn ok" onclick="ixDecide(${pend.id}, 1)">✅ Подтвердить</button><button class="ix-btn no" onclick="ixDecide(${pend.id}, 0)">Отклонить</button></div>` : '';
  const opt = m => (d.options.find(o => o.months === m) || {});
  const acts = life ? `
    <div class="ix-acts">
      <button onclick="ixShopLifetime(0)">Вернуть подписку<small>снять ∞</small></button>
    </div>` : `
    <div class="ix-acts">
      ${[1, 3, 6, 12].map(m => `<button class="${m === (h.last_period_months || 1) ? 'main' : ''}" onclick="ixShopExtend(${m})">+${m} мес<small>${fmtSum(opt(m).amount)}${opt(m).discount ? ' · −' + opt(m).discount + '%' : ''}</small></button>`).join('')}
      <button onclick="ixRecordOpen(${h.id}, ${nm})">Своя сумма<small>записать оплату</small></button>
      <button onclick="ixShopDays()">+ Дни<small>подарить</small></button>
      <button onclick="ixShopDate()">📅 Дата<small>оплачено до</small></button>
      <button onclick="ixShopPrice()">💲 Цена<small>${h.custom_price ? 'своя' : 'обычная'}</small></button>
      <button onclick="ixShopLifetime(1)">∞ Навсегда<small>разовая покупка</small></button>
    </div>`;
  const br = d.branches.length ? `
    <div class="inc-card" style="margin-top:12px;"><h3>Филиалы</h3>
      ${d.branches.map(b => `<div class="inc-row"><div><b>${escapeHtml(b.shop_name || b.username)}</b><div class="r-s">${b.is_active ? (b.branch_pending ? '⏳ ждёт оплаты' : 'работает') : 'выключен'}</div></div>
        ${b.branch_pending ? `<button class="ix-btn ok" onclick="ixBranchPaid(${b.id}, ${escapeHtml(JSON.stringify(b.shop_name || b.username))})">Оплачен</button>` : ''}</div>`).join('')}
    </div>` : '';
  const stName = { confirmed: '', pending: ' · на проверке', rejected: ' · отклонён', cancelled: ' · отменён' };
  const pays = `
    <div class="inc-card" style="margin-top:12px;"><h3>История оплат</h3>
      ${d.payments.length ? d.payments.map(p => `<div class="inc-row" style="${p.status === 'cancelled' || p.status === 'rejected' ? 'opacity:.5;' : ''}"><div><b>${fmtDay(p.day)}</b> · ${p.kind === 'extend' || p.kind === 'both' ? (p.months || '?') + ' мес' + (p.kind === 'both' ? ' + филиалы' : '') : IX_KIND[p.kind] || p.kind}
        <div class="r-s">${IX_METHOD[p.method || 'card'] || ''}${p.discount ? ' · скидка ' + p.discount + '%' : ''}${p.new_until ? ' · до ' + fmtDay(p.new_until) : ''}${stName[p.status] || ''}${p.note ? ' · ' + escapeHtml(p.note) : ''}</div>
        ${p.status === 'confirmed' ? `<div class="inc-jact">${p.method === 'cash' ? `<button onclick="ixEditAmount(${p.id}, ${p.amount || 0})">✏️ сумма</button>` : ''}<button onclick="ixCancelPay(${p.id})">🗑 убрать</button></div>` : ''}</div>
        <span class="r-v">${p.amount ? fmtSum(p.amount) : '<span style="color:#B45309; font-family:inherit; font-size:12px;">без суммы</span>'}</span></div>`).join('') : '<div class="hint-text">Оплат пока не было.</div>'}
    </div>`;
  const sub = [escapeHtml(h.username), h.phone ? escapeHtml(h.phone) : '', h.client_group ? 'сеть ' + escapeHtml(h.client_group) : '', h.has_tg ? 'Telegram ✓' : 'без Telegram'].filter(Boolean).join(' · ');
  ixModal(escapeHtml(h.name), sub, info + chk + acts + br + pays, false);
}
async function ixAfterChange(msg) {
  showMsg(msg, true);
  IX.ov = null;
  if (IX.shop) await ixOpenShop(IX.shop.shop.id);
  if (IX.tab === 'shops') ixLoadShops();
  if (IX.tab === 'pays') ixLoadPays();
  if (IX.tab === 'ov') ixLoadOv();
  loadShops();
}
async function ixShopExtend(m) {
  const h = IX.shop.shop;
  if (!confirm(`Продлить «${h.name}» на ${m} мес.? Запишется оплата наличными.`)) return;
  const d = await subAction(h.id, { action: 'extend', months: m });
  if (d.ok) ixAfterChange(`✅ Продлено до ${fmtDay(d.paid_until)}`); else showMsg('Ошибка: ' + escapeHtml(d.error || ''), false);
}
function ixShopDays() {
  const h = IX.shop.shop;
  const v = prompt(`«${h.name}» — сколько дней подарить? (без записи об оплате; минус — убрать дни)`, '7');
  if (v === null) return;
  const n = parseInt(v, 10);
  if (!n) return;
  ixPost('/api/admin/income/days', { shop_id: h.id, days: n }).then(d => d.ok ? ixAfterChange(`✅ Теперь до ${fmtDay(d.paid_until)}`) : showMsg('Ошибка: ' + escapeHtml(d.error || ''), false));
}
async function ixShopDate() {
  const h = IX.shop.shop;
  const v = prompt('Оплачено до (ДД.ММ.ГГГГ). Пусто — убрать дату (точка работает без подписки):', h.paid_until ? fmtDay(h.paid_until) : '');
  if (v === null) return;
  const d = await subAction(h.id, { action: 'set_until', date: v.trim() });
  if (d.ok) ixAfterChange(d.paid_until ? `✅ Дата: ${fmtDay(d.paid_until)}` : '✅ Дата убрана'); else showMsg('Ошибка: ' + escapeHtml(d.error || ''), false);
}
async function ixShopPrice() {
  const h = IX.shop.shop;
  const v = askSum(`Своя цена главной точки «${h.name}», сум в месяц. Скидки за срок к ней не применяются. Пусто — обычная цена.`, h.custom_price || '');
  if (v === null) return;
  const d = await subAction(h.id, { action: 'price', price: v });
  if (d.ok) ixAfterChange(v ? `✅ Цена ${fmtSum(v)} сум/мес` : '✅ Обычная цена'); else showMsg('Ошибка: ' + escapeHtml(d.error || ''), false);
}
async function ixShopLifetime(on) {
  const h = IX.shop.shop;
  let amount = '';
  if (on) {
    amount = askSum(`«${h.name}» — разовая покупка (∞, без ежемесячной оплаты). Сумма в сумах для статистики:`, '');
    if (amount === null) return;
  } else if (!confirm(`Вернуть «${h.name}» на ежемесячную подписку? Запись о разовой покупке уберётся из статистики.`)) return;
  const d = await subAction(h.id, { action: 'lifetime', on: !!on, amount });
  if (d.ok) ixAfterChange('✅ Готово'); else showMsg('Ошибка: ' + escapeHtml(d.error || ''), false);
}
async function ixBranchPaid(branchId, name) {
  const amount = askSum(`Филиал «${name}» оплачен — он сразу заработает. Сумма в сумах (для статистики):`, '');
  if (amount === null) return;
  const d = await ixPost(`/api/admin/branches/${branchId}/sub_paid`, { amount });
  if (d.ok) ixAfterChange('✅ Филиал включён'); else showMsg('Ошибка: ' + escapeHtml(d.error || ''), false);
}
async function ixDecide(id, ok) {
  if (!ok && !confirm('Отклонить этот чек? Точке придёт сообщение, что чек не принят.')) return;
  const d = await ixPost(`/api/admin/sub/payments/${id}/${ok ? 'confirm' : 'reject'}`);
  if (d.ok) { ixAfterChange(ok ? `✅ Подтверждено — до ${fmtDay(d.new_until)}` : 'Чек отклонён'); loadSubPanel(); }
  else showMsg('Ошибка: ' + escapeHtml(d.error || ''), false);
}
async function ixEditAmount(id, cur) {
  const v = askSum('Сумма оплаты в сумах:', cur || '');
  if (v === null) return;
  const d = await ixPost(`/api/admin/sub/payments/${id}/amount`, { amount: v });
  if (d.ok) ixAfterChange('✅ Сумма сохранена'); else showMsg('Ошибка: ' + escapeHtml(d.error || ''), false);
}
async function ixCancelPay(id) {
  if (!confirm('Убрать эту оплату из статистики? Дата «оплачено до» не изменится — при необходимости поправь её кнопкой «📅 Дата».')) return;
  const d = await ixPost(`/api/admin/sub/payments/${id}/cancel`);
  if (d.ok) ixAfterChange('✅ Убрано'); else showMsg('Ошибка: ' + escapeHtml(d.error || ''), false);
}

// ----- Оплаты -----
let ixPaySeq = 0, ixPayT = null;
function ixPaySearchSoon() {
  clearTimeout(ixPayT);
  ixPayT = setTimeout(() => { IX.p.q = document.getElementById('ixPQ').value.trim(); IX.p.page = 1; ixLoadPays(); }, 300);
}
function ixPayStatus(s) {
  IX.p.status = s; IX.p.page = 1;
  document.querySelectorAll('#ixPStatus button').forEach(b => b.classList.toggle('on', b.dataset.s === s));
  if (IX.tab === 'pays') ixLoadPays();
}
function ixPayPage(n) { IX.p.page = n; ixLoadPays(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
async function ixLoadPays() {
  const seq = ++ixPaySeq;
  const box = document.getElementById('ixPayList');
  if (!IX.p.data) box.innerHTML = '<div class="ix-empty">Загружаю…</div>';
  let [f, t] = ixRange();
  // «На проверке» — все непроверенные чеки, за любой срок
  if (IX.p.status === 'pending') { f = '2020-01-01'; t = ixIso(new Date()); }
  try {
    const d = await ixGet('/api/admin/income/payments?' + ixQS({ from: f, to: t, status: IX.p.status, method: IX.p.method, kind: IX.p.kind, q: IX.p.q, page: IX.p.page, per: 100 }));
    if (seq !== ixPaySeq) return;
    IX.p.data = d;
    ixRenderPays();
  } catch (e) {
    if (seq === ixPaySeq) box.innerHTML = `<div class="ix-empty">${escapeHtml(e.message || 'Ошибка загрузки')}</div>`;
  }
}
function ixRenderPays() {
  const d = IX.p.data;
  if (!d) return;
  document.getElementById('ixPaySum').innerHTML = IX.p.status === 'pending'
    ? `<span>Чеков на проверке: <b>${d.total}</b></span>`
    : `<span>${fmtDay(d.from)} — ${fmtDay(d.to)}</span><span>${d.total} записей${IX.p.status === 'confirmed' || IX.p.status === 'all' ? ' · пришло <b>' + fmtSum(d.sum) + '</b> сум' : ''}</span>`;
  const byDay = {};
  const order = [];
  d.rows.forEach(r => { if (!byDay[r.day]) { byDay[r.day] = []; order.push(r.day); } byDay[r.day].push(r); });
  const stTxt = { pending: '🧾 на проверке', rejected: 'отклонён', cancelled: 'отменён' };
  const html = order.map(day => {
    const sum = byDay[day].filter(r => r.status === 'confirmed').reduce((a, r) => a + (r.amount || 0), 0);
    return `<div class="ix-day"><span>${fmtDay(day)}</span><span>${sum ? '+' + fmtSum(sum) : ''}</span></div>` + byDay[day].map(r => `
      <div class="ix-pay st-${r.status}">
        <div style="min-width:0;">
          <div class="nm" onclick="ixOpenShop(${r.shop_id})">${escapeHtml(r.name)}</div>
          <div class="sb">${r.kind === 'extend' || r.kind === 'both' ? (r.months || '?') + ' мес' + (r.kind === 'both' ? ' + филиалы' : '') : IX_KIND[r.kind] || r.kind} · ${IX_METHOD[r.method || 'card'] || ''}${r.discount ? ' · −' + r.discount + '%' : ''}${r.new_until ? ' · до ' + fmtDay(r.new_until) : ''}${stTxt[r.status] ? ' · ' + stTxt[r.status] : ''}${r.note ? ' · ' + escapeHtml(r.note) : ''}</div>
          <div class="act">
            ${r.has_receipt ? `<a href="/api/admin/sub/receipt/${r.id}" target="_blank" rel="noopener">чек</a>` : ''}
            ${r.status === 'pending' ? `<button class="ok" onclick="ixDecide(${r.id}, 1)">✅ Подтвердить</button><button class="no" onclick="ixDecide(${r.id}, 0)">Отклонить</button>` : ''}
            ${r.status === 'confirmed' && r.method === 'cash' ? `<button onclick="ixEditAmount(${r.id}, ${r.amount || 0})">✏️ сумма</button>` : ''}
            ${r.status === 'confirmed' ? `<button onclick="ixCancelPay(${r.id})">🗑 убрать</button>` : ''}
          </div>
        </div>
        <div class="am">${r.amount ? (r.status === 'confirmed' ? '+' : '') + fmtSum(r.amount) : '<span style="color:#B45309; font-size:12px;">без суммы</span>'}</div>
      </div>`).join('');
  }).join('');
  document.getElementById('ixPayList').innerHTML = html || `<div class="ix-empty">${IX.p.status === 'pending' ? 'Новых чеков нет' : 'За этот период оплат нет'}</div>`;
  document.getElementById('ixPayPager').innerHTML = d.pages > 1 ? `
    <button class="ix-btn" ${d.page <= 1 ? 'disabled' : ''} onclick="ixPayPage(${d.page - 1})">‹ Новее</button>
    <span>${d.page} из ${d.pages}</span>
    <button class="ix-btn" ${d.page >= d.pages ? 'disabled' : ''} onclick="ixPayPage(${d.page + 1})">Старее ›</button>` : '';
}

// ----- Записать оплату вручную -----
const IXR = { shop: null, months: 1, opts: [], method: 'cash' };
function ixRecordOpen(shopId, name) {
  IXR.shop = shopId ? { id: shopId, name } : null; IXR.months = 1; IXR.opts = []; IXR.method = 'cash';
  ixModal('Записать оплату', 'Точка продлится на выбранный срок, сумма попадёт в доходы.', `
    <div class="ix-form">
      <div class="field"><label>Точка</label>
        <input id="ixRShop" placeholder="Начни вводить название" autocomplete="off" oninput="ixRSuggest()" value="${shopId ? escapeHtml(name) : ''}">
        <div class="ix-sug" id="ixRSug" hidden></div></div>
      <div class="field"><label>Срок</label><div class="ix-seg2" id="ixRMonths">${[1, 3, 6, 12].map(m => `<button data-m="${m}" class="${m === 1 ? 'on' : ''}" onclick="ixRMonths(${m})">${m} мес</button>`).join('')}<input id="ixRMx" inputmode="numeric" placeholder="другой" style="width:90px;" oninput="ixRMonths(parseInt(this.value, 10) || 0, true)"></div></div>
      <div class="row2">
        <div class="field"><label>Сумма, сум</label><input id="ixRAmt" inputmode="numeric" placeholder="по цене точки"></div>
        <div class="field"><label>Дата оплаты</label><input id="ixRDate" type="date" value="${ixIso(new Date())}"></div>
      </div>
      <div class="field"><label>Как заплатили</label><div class="ix-seg2" id="ixRMethod"><button data-k="cash" class="on" onclick="ixRMethod('cash')">Наличные</button><button data-k="card" onclick="ixRMethod('card')">Перевод</button></div></div>
      <div class="field"><label>Заметка (необяз.)</label><input id="ixRNote" maxlength="200"></div>
      <button class="ix-btn pri" style="padding:12px 20px; font-size:14px;" onclick="ixRSave()"><i class="fa-solid fa-check"></i> Записать</button>
    </div>`, true);
  if (shopId) ixRLoadOpts();
}
let ixRSugT = null;
function ixRSuggest() {
  IXR.shop = null;
  clearTimeout(ixRSugT);
  ixRSugT = setTimeout(async () => {
    const q = document.getElementById('ixRShop').value.trim();
    const box = document.getElementById('ixRSug');
    if (q.length < 2) { box.hidden = true; return; }
    try {
      const d = await ixGet('/api/admin/income/shops?' + ixQS({ q, per: 10, sort: 'name' }));
      box.innerHTML = d.rows.length ? d.rows.map(h => `<div onclick='ixRPick(${h.id}, ${JSON.stringify(h.name).replace(/'/g, "&#39;")})'>${escapeHtml(h.name)} <span style="color:var(--hint); font-size:12px;">${escapeHtml(h.username)} · ${IX_ST[h.status] ? IX_ST[h.status][0] : ''}</span></div>`).join('') : '<div style="color:var(--hint);">не найдено</div>';
      box.hidden = false;
    } catch (e) {}
  }, 250);
}
function ixRPick(id, name) {
  IXR.shop = { id, name };
  document.getElementById('ixRShop').value = name;
  document.getElementById('ixRSug').hidden = true;
  ixRLoadOpts();
}
async function ixRLoadOpts() {
  try {
    const d = await ixGet('/api/admin/income/shop/' + IXR.shop.id);
    IXR.opts = d.options || [];
    IXR.monthly = d.shop.monthly;
    ixRMonths(IXR.months);
  } catch (e) {}
}
function ixRMonths(m, fromInput) {
  IXR.months = m;
  document.querySelectorAll('#ixRMonths button').forEach(b => b.classList.toggle('on', Number(b.dataset.m) === m));
  if (!fromInput) { const mx = document.getElementById('ixRMx'); if (mx) mx.value = ''; }
  const o = IXR.opts.find(x => x.months === m);
  const amt = document.getElementById('ixRAmt');
  if (amt) amt.placeholder = o ? fmtSum(o.amount) + ' (по цене)' : (IXR.monthly && m ? fmtSum(Math.round(IXR.monthly * m / 1000) * 1000) + ' (по цене)' : 'по цене точки');
}
function ixRMethod(k) {
  IXR.method = k;
  document.querySelectorAll('#ixRMethod button').forEach(b => b.classList.toggle('on', b.dataset.k === k));
}
async function ixRSave() {
  if (!IXR.shop) { showMsg('Выбери точку из списка', false); return; }
  if (!IXR.months || IXR.months < 1 || IXR.months > 36) { showMsg('Срок — от 1 до 36 месяцев', false); return; }
  const body = { shop_id: IXR.shop.id, months: IXR.months, amount: document.getElementById('ixRAmt').value.replace(/[^0-9]/g, ''),
    date: document.getElementById('ixRDate').value, method: IXR.method, note: document.getElementById('ixRNote').value };
  const d = await ixPost('/api/admin/income/record', body);
  if (!d.ok) { showMsg('Ошибка: ' + escapeHtml(d.error || ''), false); return; }
  ixClose();
  ixAfterChange(`✅ Записано ${fmtSum(d.amount)} сум · «${escapeHtml(IXR.shop.name)}» до ${fmtDay(d.paid_until)}`);
}

async function loadSubPanel() {
  try {
    const [pr, sr] = await Promise.all([fetch('/api/admin/sub/payments?status=pending'), fetch('/api/admin/sub/settings')]);
    const pd = await pr.json(), sd = await sr.json();
    const n = (pd.payments || []).length;
    const cnt = document.getElementById('ixChkCnt');
    if (cnt) { cnt.hidden = !n; cnt.textContent = n; }
    const tb = document.querySelector('#admTabs button[data-t="income"]');
    if (tb) {
      let b = tb.querySelector('.cnt');
      if (n && !b) { b = document.createElement('span'); b.className = 'cnt'; b.style.cssText = 'background:#E63946; color:#fff; border-radius:999px; font-size:11px; padding:1px 6px; margin-left:4px;'; tb.appendChild(b); }
      if (b) { b.textContent = n; b.hidden = !n; }
    }
    const st = sd.settings || {};
    ['card_number', 'card_holder', 'support_contact', 'remind_days', 'price_main', 'price_branch', 'disc_1', 'disc_3', 'disc_6', 'disc_12', 'first_disc', 'lifetime_usd', 'lifetime_branch_usd', 'usd_rate_manual', 'trial_days', 'grace_days', 'ref_pct']
      .forEach(k => { const el = document.getElementById('ss_' + k); if (el && document.activeElement !== el) el.value = st[k] == null ? '' : st[k]; });
    const rt = document.getElementById('ssRate');
    if (rt) rt.innerHTML = sd.usd_rate
      ? 'Сейчас курс: <b>' + fmtSum(Math.round(sd.usd_rate)) + '</b> сум (' + (sd.usd_src === 'manual' ? 'свой курс' : 'ЦБ, обновляется сам') + ') → безлимит главной точки = <b>' + fmtSum(sd.lt_example) + '</b> сум'
      : '⚠️ Курс ЦБ пока не получен — тариф «Безлимит» скрыт. Укажи свой курс или подожди 10 минут.';
    const au = document.getElementById('ssAuto');
    if (au) au.innerHTML = sd.auto
      ? '💳 Автооплата Hamyon: <b style="color:#0E6B3E;">подключена</b>. В Hamyon укажи COMPLETE_URL: <b>' + escapeHtml(sd.complete_url || '') + '</b>'
      : '💳 Автооплата Hamyon: <b style="color:#B3241C;">не подключена</b> — добавь в Render переменные HAMYON_SHOP_ID и HAMYON_SHOP_KEY. Пока оплата идёт по чеку.';
  } catch (e) {}
}

async function saveSubSettings() {
  const body = {};
  ['card_number', 'card_holder', 'support_contact', 'remind_days'].forEach(k => body[k] = document.getElementById('ss_' + k).value.trim());
  for (const k of ['price_main', 'price_branch', 'disc_1', 'disc_3', 'disc_6', 'disc_12', 'first_disc', 'lifetime_usd', 'lifetime_branch_usd', 'usd_rate_manual', 'trial_days', 'grace_days', 'ref_pct']) {
    const raw = document.getElementById('ss_' + k).value.replace(/[^0-9]/g, '');
    if (raw === '') { showMsg('Заполните все цены и скидки', false); return; }
    body[k] = Number(raw);
  }
  const res = await fetch('/api/admin/sub/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const data = await res.json();
  if (data.ok) { showMsg('✅ Настройки сохранены', true); loadSubPanel(); loadShops(); IX.ov = null; } else showMsg('Ошибка: ' + data.error, false);
}

async function loadShops() {
  const res = await fetch('/api/admin/shops');
  allShopsCache = await res.json();

  // список известных групп — для автодополнения в форме создания новой точки
  const groupNames = [...new Set(allShopsCache.map(s => s.client_group).filter(Boolean))].sort();
  document.getElementById('clientGroupsList').innerHTML = groupNames.map(g => `<option value="${escapeHtml(g)}">`).join('');

  const st = document.getElementById('admStats');
  const active = allShopsCache.filter(s => s.is_active).length;
  const clients = allShopsCache.reduce((a, s) => a + (s.client_count || 0), 0);
  st.innerHTML = `
    <div class="adm-stat"><b>${allShopsCache.length}</b><span>точек</span></div>
    <div class="adm-stat"><b>${active}</b><span>активных</span></div>
    <div class="adm-stat"><b>${clients.toLocaleString('ru-RU')}</b><span>клиентов</span></div>`;
  filterShops();
}

let shopFilter = 'all';
function setShopFilter(f) {
  shopFilter = f;
  document.querySelectorAll('#admFilters button').forEach(b => b.classList.toggle('on', b.dataset.f === f));
  filterShops();
}

function filterShops() {
  const q = document.getElementById('shopSearch').value.trim().toLowerCase();
  const filtered = allShopsCache.filter(s =>
    (!q || (s.shop_name || '').toLowerCase().includes(q) ||
      (s.username || '').toLowerCase().includes(q) ||
      (s.phone || '').toLowerCase().includes(q)) &&
    (shopFilter === 'all' ||
      (shopFilter === 'active' && s.is_active) ||
      (shopFilter === 'off' && !s.is_active) ||
      (shopFilter === 'notg' && !s.notify_telegram_id) ||
      (shopFilter === 'debt' && s.sub && s.sub.expired) ||
      (shopFilter === 'soon' && s.sub && !s.sub.lifetime && s.sub.days_left !== null && s.sub.days_left >= 0 && s.sub.days_left <= 5) ||
      (shopFilter === 'check' && s.sub && s.sub.pending_payment) ||
      (shopFilter === 'life' && s.sub && s.sub.lifetime) ||
      (shopFilter === 'unset' && s.sub && !s.sub.lifetime && !s.sub.paid_until) ||
      (shopFilter === 'trial' && s.sub && s.sub.trial))
  );
  renderShopsTable(filtered);
}

function renderShopsTable(shops) {
  // карточки вместо широкой таблицы: на телефоне всё видно без прокрутки вбок.
  // id элементов прежние — на них опираются функции изменения/сотрудников/филиалов.
  const grouped = {};
  const standalone = [];
  shops.forEach(s => {
    if (s.client_group) (grouped[s.client_group] = grouped[s.client_group] || []).push(s);
    else standalone.push(s);
  });

  function renderShopCard(s) {
    const name = escapeHtml(JSON.stringify(s.username));
    const link = s.owner_link ? escapeHtml(JSON.stringify(s.owner_link)) : null;
    return `
    <div class="shop-card ${s.is_active ? '' : 'off'}">
      <div class="sc-head">
        <div style="min-width:0;">
          <div class="sc-name" id="name_view_${s.id}">${escapeHtml(s.shop_name || '—')}</div>
          <div class="sc-login">@<span id="username_view_${s.id}">${escapeHtml(s.username)}</span></div>
          <div class="sc-edit" id="name_edit_${s.id}" style="display:none;">
            <input id="name_input_${s.id}" value="${escapeHtml(s.shop_name || '')}" placeholder="Название">
          </div>
          <div class="sc-edit" id="username_edit_${s.id}" style="display:none;">
            <input id="username_input_${s.id}" value="${escapeHtml(s.username)}" placeholder="Логин">
            <button class="badge active" style="margin-top:6px; padding:6px 12px;" onclick="saveIdentity(${s.id})">💾 сохранить</button>
          </div>
        </div>
        <button class="badge ${s.is_active ? 'active' : 'inactive'}" style="flex:none;" onclick="toggleShop(${s.id}, ${s.is_active ? 0 : 1})">${s.is_active ? '● активна' : '○ выключена'}</button>
      </div>

      <div class="sc-meta">
        <span><i class="fa-solid fa-users"></i> ${s.client_count} клиентов</span>
        ${s.phone ? `<span><i class="fa-solid fa-phone"></i> ${escapeHtml(s.phone)}</span>` : ''}
        ${s.notify_telegram_id ? '<span class="ok"><i class="fa-brands fa-telegram"></i> Telegram</span>' : '<span class="no"><i class="fa-brands fa-telegram"></i> нет Telegram</span>'}
      </div>
      ${renderSubBlock(s)}

      <div class="sc-toggles">
        <span>SMS<button class="sw ${s.sms_enabled ? 'on' : ''}" title="${s.sms_enabled ? 'выключить' : 'включить'}" onclick="toggleSms(${s.id}, ${s.sms_enabled ? 0 : 1})"></button></span>
        <span>Склад<button class="sw ${s.warehouse_enabled ? 'on' : ''}" title="${s.warehouse_enabled ? 'выключить' : 'включить'}" onclick="toggleWarehouse(${s.id}, ${s.warehouse_enabled ? 0 : 1})"></button></span>
        <span title="Склад магазина: основной склад + магазин в одном аккаунте. Сотрудники видят только магазин.">Магазин<button class="sw ${s.store_enabled && s.warehouse_enabled ? 'on' : ''}" title="${s.store_enabled && s.warehouse_enabled ? 'выключить склад магазина' : 'включить склад магазина'}" onclick="toggleStore(${s.id}, ${s.store_enabled && s.warehouse_enabled ? 0 : 1})"></button></span>
        <span class="grp-chip">🏷<input value="${escapeHtml(s.client_group || '')}" list="clientGroupsList" placeholder="без группы" onchange="setClientGroup(${s.id}, this.value)"></span>
      </div>

      <div class="sc-grid">
        <button class="sc-tile" id="tile-br-${s.id}" onclick="toggleBranches(${s.id}); this.classList.toggle('open')"><i class="fa-solid fa-building"></i>Филиалы</button>
        <button class="sc-tile" id="tile-emp-${s.id}" onclick="toggleEmployees(${s.id}); this.classList.toggle('open')"><i class="fa-solid fa-users"></i>Сотрудники</button>
        <button class="sc-tile" onclick="toggleIdentityEdit(${s.id}); this.classList.toggle('open')"><i class="fa-solid fa-pen"></i>Изменить</button>
        <button class="sc-tile" onclick="resetPassword(${s.id}, ${name})"><i class="fa-solid fa-key"></i>Пароль</button>
        <button class="sc-tile" ${link ? `onclick="copyOwnerLink(${link}, this)"` : 'disabled title="ссылки пока нет"'}><i class="fa-solid fa-link"></i>Ссылка</button>
        <button class="sc-tile" onclick="testNotifyTelegram(${s.id})"><i class="fa-solid fa-paper-plane"></i>Тест TG</button>
      </div>

      <details style="margin-top:10px;">
        <summary style="font-size:12px; color:var(--hint); cursor:pointer;">Telegram ID вручную</summary>
        <div style="display:flex; gap:6px; margin-top:6px;">
          <input id="notify_id_${s.id}" value="${escapeHtml(s.notify_telegram_id || '')}" placeholder="123456789" style="max-width:180px; font-size:13px; padding:7px 9px;">
          <button class="badge active" style="padding:6px 12px;" onclick="saveNotifyTelegram(${s.id})">сохранить</button>
        </div>
      </details>

      <div id="branch-row-${s.id}" style="display:none;"><div class="sc-panel" id="branch-panel-${s.id}">…</div></div>
      <div id="emp-row-${s.id}" style="display:none;"><div class="sc-panel" id="emp-panel-${s.id}">…</div></div>
    </div>`;
  }

  let html = '';
  Object.keys(grouped).sort().forEach(group => {
    html += `<div class="grp-title">🏷️ ${escapeHtml(group)} · ${grouped[group].length}</div>`;
    grouped[group].forEach(s => html += renderShopCard(s));
  });
  if (standalone.length && Object.keys(grouped).length) html += `<div class="grp-title" style="color:#64748B;">Без группы · ${standalone.length}</div>`;
  standalone.forEach(s => html += renderShopCard(s));

  document.getElementById('shops-body').innerHTML = html || `<div class="hint-text" style="padding:14px;">Ничего не найдено.</div>`;
}

async function setClientGroup(shopId, value) {
  await fetch(`/api/admin/shops/${shopId}/client_group`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({client_group: value.trim()})
  });
  loadShops();
}

async function toggleEmployees(shopId) {
  const row = document.getElementById(`emp-row-${shopId}`);
  const opening = row.style.display === 'none';
  row.style.display = opening ? '' : 'none';
  if (opening) await loadEmployees(shopId);
}

async function loadEmployees(shopId) {
  const panel = document.getElementById(`emp-panel-${shopId}`);
  const res = await fetch(`/api/admin/shops/${shopId}/employees`);
  const employees = await res.json();
  const list = employees.length ? employees.map(e => `
    <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px dashed var(--border); font-size:13px;">
      <span style="${e.is_active ? '' : 'opacity:.55;'}">${escapeHtml(e.full_name || e.username)} <span class="hint-text">(${escapeHtml(e.username)})</span>${e.is_active ? '' : ' <span class="hint-text">· выключен</span>'}</span>
      <span style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; justify-content:flex-end;">
        <button class="badge" style="background:var(--border);color:var(--hint);" onclick="toggleEmployeeActive(${e.id}, ${shopId}, ${e.is_active ? 0 : 1})">${e.is_active ? 'выключить' : 'включить'}</button>
        <button class="badge" style="background:var(--border);color:var(--hint);" onclick="resetEmployeePassword(${e.id}, ${shopId}, ${escapeHtml(JSON.stringify(e.username))})">сбросить</button>
        <button class="badge inactive" onclick="deleteEmployee(${e.id}, ${shopId}, ${escapeHtml(JSON.stringify(e.username))})">удалить</button>
      </span>
    </div>
  `).join('') : `<div class="hint-text">Пока нет сотрудников у этой точки.</div>`;
  panel.innerHTML = `
    <div style="font-weight:700; font-size:13px; margin-bottom:8px;">Сотрудники точки (ограниченный доступ — без статистики, прибыли, экспорта, склада)</div>
    ${list}
    <div style="display:flex; gap:6px; margin-top:10px;">
      <input id="new-emp-username-${shopId}" placeholder="логин сотрудника" style="flex:1;">
      <button class="badge active" style="padding:6px 14px;" onclick="createEmployee(${shopId})">+ добавить</button>
    </div>
  `;
}

async function createEmployee(shopId) {
  const input = document.getElementById(`new-emp-username-${shopId}`);
  const username = input.value.trim();
  if (!username) return;
  const res = await fetch(`/api/admin/shops/${shopId}/employees`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username})
  });
  const data = await res.json();
  if (data.ok) {
    showMsgSticky(`✅ Сотрудник «${username}» создан. Пароль (больше не увидите — сохраните сейчас): <b>${data.password}</b>`);
    loadEmployees(shopId);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function resetEmployeePassword(employeeId, shopId, username) {
  if (!confirm(`Сбросить пароль для сотрудника «${username}»?`)) return;
  const res = await fetch(`/api/admin/employees/${employeeId}/reset_password`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({shop_id: shopId})
  });
  const data = await res.json();
  if (data.ok) {
    showMsgSticky(`✅ Новый пароль для «${username}» (больше не увидите — сохраните сейчас): <b>${data.password}</b>`);
    loadEmployees(shopId);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function toggleEmployeeActive(employeeId, shopId, on) {
  const res = await fetch(`/api/admin/employees/${employeeId}/active`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({shop_id: shopId, active: !!on})
  });
  const data = await res.json();
  if (data.ok) loadEmployees(shopId); else showMsg('Ошибка: ' + data.error, false);
}

async function deleteEmployee(employeeId, shopId, username) {
  if (!confirm(`Удалить сотрудника «${username}»? Он больше не сможет войти.`)) return;
  const res = await fetch(`/api/admin/employees/${employeeId}?shop_id=${shopId}`, { method: 'DELETE' });
  const data = await res.json();
  if (data.ok) { loadEmployees(shopId); } else { showMsg('Ошибка: ' + data.error, false); }
}

async function toggleBranches(shopId) {
  const row = document.getElementById(`branch-row-${shopId}`);
  const opening = row.style.display === 'none';
  row.style.display = opening ? '' : 'none';
  if (opening) await loadBranches(shopId);
}

async function loadBranches(shopId) {
  const panel = document.getElementById(`branch-panel-${shopId}`);
  const res = await fetch(`/api/admin/shops/${shopId}/branches`);
  const branches = await res.json();
  const list = branches.length ? branches.map(b => `
    <div style="padding:8px 0; border-bottom:1px dashed var(--border); font-size:13px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <span>${escapeHtml(b.shop_name || b.username)} <span class="hint-text">(${b.username}, клиентов: ${b.client_count})</span></span>
        <span style="display:flex; align-items:center; gap:8px;">
          <span class="hint-text">🔒 скрыт</span>
          <button class="badge" style="background:var(--border);color:var(--hint);" onclick="resetPassword(${b.id}, ${escapeHtml(JSON.stringify(b.username))})">сбросить</button>
        </span>
      </div>
      <div id="branch-edit-${b.id}" style="display:none;"></div>
      <div style="display:flex; gap:6px; flex-wrap:wrap;">
        ${b.branch_pending ? `<span class="sub-pill warn" style="align-self:center;">⏳ ждёт оплаты</span><button class="badge active" onclick="markBranchPaid(${shopId}, ${b.id}, ${escapeHtml(JSON.stringify(b.shop_name || b.username))})">✅ отметить оплату</button>` : ''}
        <button class="badge ${b.is_active ? 'active' : 'inactive'}" onclick="toggleBranchField(${shopId}, ${b.id}, 'toggle', ${b.is_active ? 0 : 1})">${b.is_active ? 'активен' : 'выключен'}</button>
        <button class="badge ${b.sms_enabled ? 'active' : 'inactive'}" onclick="toggleBranchField(${shopId}, ${b.id}, 'toggle_sms', ${b.sms_enabled ? 0 : 1})">SMS: ${b.sms_enabled ? 'включён' : 'выключен'}</button>
        <button class="badge ${b.warehouse_enabled ? 'active' : 'inactive'}" onclick="toggleBranchField(${shopId}, ${b.id}, 'toggle_warehouse', ${b.warehouse_enabled ? 0 : 1})">Склад: ${b.warehouse_enabled ? 'включён' : 'выключен'}</button>
        <button class="badge" style="background:#EFF6FF; color:#0F52BA;" onclick='openBranchEdit(${shopId}, ${escapeHtml(JSON.stringify(b))})'>✏️ изменить</button>
        <button class="badge" style="background:#FEF2F2; color:#B3241C;" onclick="deleteBranch(${shopId}, ${b.id})">🗑 удалить</button>
      </div>
    </div>
  `).join('') : `<div class="hint-text">У этой точки пока нет филиалов.</div>`;
  panel.innerHTML = `
    <div style="font-weight:700; font-size:13px; margin-bottom:8px;">Филиалы (полноценные точки — свой склад, своя база, без цены закупки и без прибыли по отдельности)</div>
    ${list}
    <details style="margin-top:12px; padding-top:10px; border-top:1px solid var(--border);">
      <summary style="cursor:pointer; font-weight:700; color:#059669; font-size:13px; padding:4px 0;">+ Добавить филиал</summary>
      <div class="field" style="margin-top:8px;">
        <label>Название филиала</label>
        <input id="new-branch-name-${shopId}" placeholder="название филиала">
      </div>
      <div class="row2">
        <div class="field">
          <label>Логин</label>
          <input id="new-branch-username-${shopId}" placeholder="логин">
        </div>
        <div class="field">
          <label>Пароль (пусто = сгенерировать)</label>
          <input id="new-branch-password-${shopId}" placeholder="необязательно">
        </div>
      </div>
      <div class="row2">
        <div class="field">
          <label>Телефон филиала</label>
          <input id="new-branch-phone-${shopId}" placeholder="+998901112233">
        </div>
        <div class="field">
          <label>Telegram ID для уведомлений (необяз.)</label>
          <input id="new-branch-notify-${shopId}" placeholder="123456789">
        </div>
      </div>
      <div class="field">
        <label>Адрес</label>
        <input id="new-branch-address-${shopId}" placeholder="Наманган, ул. ...">
      </div>
      <div class="field">
        <label>Локация (необяз.) — широта и долгота из Google Карт через запятую</label>
        <input id="new-branch-location-${shopId}" placeholder="40.782123, 72.344567">
      </div>
      <button class="badge active" style="padding:6px 14px; margin-top:6px;" onclick="createBranch(${shopId})">+ добавить филиал</button>
    </details>
  `;
}

function openBranchEdit(shopId, b) {
  const box = document.getElementById(`branch-edit-${b.id}`);
  if (box.style.display !== 'none') { box.style.display = 'none'; return; }
  const v = x => escapeHtml(x == null ? '' : String(x));
  const loc = (b.lat != null && b.lon != null) ? `${b.lat}, ${b.lon}` : '';
  box.innerHTML = `
    <div style="background:#F8FAFC; border:1px solid var(--border); border-radius:12px; padding:12px; margin:8px 0;">
      <div class="row2">
        <div class="field"><label>Название филиала</label><input id="be-name-${b.id}" value="${v(b.shop_name)}"></div>
        <div class="field"><label>Логин</label><input id="be-user-${b.id}" value="${v(b.username)}"></div>
      </div>
      <div class="row2">
        <div class="field"><label>Телефон</label><input id="be-phone-${b.id}" value="${v(b.phone)}" placeholder="+998901112233"></div>
        <div class="field"><label>Telegram ID для уведомлений</label><input id="be-notify-${b.id}" value="${v(b.notify_telegram_id)}"></div>
      </div>
      <div class="field"><label>Адрес</label><input id="be-address-${b.id}" value="${v(b.address)}"></div>
      <div class="row2">
        <div class="field"><label>Часы работы</label><input id="be-hours-${b.id}" value="${v(b.hours)}" placeholder="09:00–19:00"></div>
        <div class="field"><label>Локация (широта, долгота)</label><input id="be-loc-${b.id}" value="${v(loc)}" placeholder="40.782123, 72.344567"></div>
      </div>
      <div style="display:flex; gap:8px; flex-wrap:wrap;">
        <button class="badge active" style="padding:6px 14px;" onclick="saveBranchEdit(${shopId}, ${b.id})">💾 сохранить</button>
        <button class="badge" style="padding:6px 14px; background:var(--border); color:var(--hint);" onclick="document.getElementById('branch-edit-${b.id}').style.display='none'">отмена</button>
      </div>
      <div class="hint-text" style="margin-top:6px;">Пароль меняется кнопкой «сбросить».</div>
    </div>`;
  box.style.display = 'block';
}

async function saveBranchEdit(shopId, branchId) {
  const g = id => document.getElementById(`${id}-${branchId}`).value.trim();
  const payload = {
    shop_name: g('be-name'), username: g('be-user'), phone: g('be-phone'),
    notify_telegram_id: g('be-notify'), address: g('be-address'), hours: g('be-hours'),
  };
  if (!payload.shop_name || !payload.username) { showMsg('Укажите название и логин.', false); return; }
  const loc = g('be-loc');
  if (loc) {
    const parts = loc.split(',').map(p => p.trim()).filter(Boolean);
    if (parts.length !== 2 || isNaN(parseFloat(parts[0])) || isNaN(parseFloat(parts[1]))) {
      showMsg('Локация должна быть в формате: широта, долгота (два числа через запятую).', false);
      return;
    }
    payload.lat = parts[0]; payload.lon = parts[1];
  } else {
    payload.lat = ''; payload.lon = '';
  }
  const res = await fetch(`/api/admin/branches/${branchId}`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsg('✅ Филиал сохранён', true);
    loadBranches(shopId);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function deleteBranch(shopId, branchId) {
  const pre = await (await fetch(`/api/admin/branches/${branchId}/delete_preview`)).json();
  if (!pre.ok) { showMsg('Ошибка: ' + pre.error, false); return; }
  const c = pre.counts;
  const warn = `Удалить филиал «${pre.name}» НАВСЕГДА?\n\n` +
    `Вместе с ним удалятся: клиентов — ${c.clients}, машин — ${c.cars}, записей о заменах — ${c.services}, ` +
    `товаров склада — ${c.products}, долгов — ${c.debts}, сотрудников — ${c.employees}.\n\n` +
    `Перед удалением вся база автоматически отправится резервной копией в Telegram.\n` +
    `Если нужно просто закрыть доступ и сохранить историю — нажмите «Отмена» и используйте кнопку «активен/выключен».`;
  if (!confirm(warn)) return;
  const typed = prompt(`Для подтверждения впишите название филиала точно так:\n${pre.name}`);
  if (typed === null) return;
  if (typed.trim() !== pre.name) { showMsg('Название не совпало — филиал не удалён.', false); return; }
  showMsg('⏳ Отправляю резервную копию и удаляю филиал…', true);
  const res = await fetch(`/api/admin/branches/${branchId}`, {
    method: 'DELETE', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ confirm_name: typed.trim() })
  });
  const data = await res.json();
  if (data.ok) {
    showMsgSticky(`🗑 Филиал «${escapeHtml(pre.name)}» удалён. Резервная копия базы до удаления — в Telegram.`);
    loadBranches(shopId);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function createBranch(shopId) {
  const shopName = document.getElementById(`new-branch-name-${shopId}`).value.trim();
  const username = document.getElementById(`new-branch-username-${shopId}`).value.trim();
  if (!shopName || !username) { showMsg('Укажите название филиала и логин.', false); return; }
  const payload = {
    shop_name: shopName,
    username,
    password: document.getElementById(`new-branch-password-${shopId}`).value.trim(),
    phone: document.getElementById(`new-branch-phone-${shopId}`).value.trim(),
    notify_telegram_id: document.getElementById(`new-branch-notify-${shopId}`).value.trim(),
    address: document.getElementById(`new-branch-address-${shopId}`).value.trim(),
  };
  const loc = document.getElementById(`new-branch-location-${shopId}`).value.trim();
  if (loc) {
    const parts = loc.split(',').map(p => p.trim()).filter(Boolean);
    if (parts.length === 2 && !isNaN(parseFloat(parts[0])) && !isNaN(parseFloat(parts[1]))) {
      payload.lat = parts[0];
      payload.lon = parts[1];
    } else {
      showMsg('Локация должна быть в формате: широта, долгота (два числа через запятую).', false);
      return;
    }
  }
  const res = await fetch(`/api/admin/shops/${shopId}/branches`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showMsgSticky(`✅ Филиал «${shopName}» создан. Логин: <b>${username}</b>, пароль (больше не увидите — сохраните сейчас): <b>${data.password}</b>` +
      (data.sub_pending ? '<br>⏳ Филиал заработает после оплаты: владелец оплатит его в разделе «Подписка», или нажми «✅ отметить оплату» (наличные / 100 $ у бессрочной сети).' : ''));
    loadBranches(shopId);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function toggleStore(id, makeEnabled) {
  if (!makeEnabled && !confirm('Выключить «Склад магазина»? Остатки магазина перестанут учитываться отдельно (общий остаток не изменится).')) return;
  await fetch(`/api/admin/shops/${id}/toggle_store`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: !!makeEnabled})
  });
  loadShops();
}

async function toggleWarehouse(id, makeEnabled) {
  await fetch(`/api/admin/shops/${id}/toggle_warehouse`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: !!makeEnabled})
  });
  loadShops();
}

async function toggleShop(id, makeActive) {
  await fetch(`/api/admin/shops/${id}/toggle`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({active: !!makeActive})
  });
  loadShops();
}

async function toggleBranchField(headShopId, branchId, endpoint, value) {
  const bodyKey = endpoint === 'toggle' ? 'active' : 'enabled';
  await fetch(`/api/admin/shops/${branchId}/${endpoint}`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({[bodyKey]: !!value})
  });
  loadBranches(headShopId);
}

async function toggleSms(id, makeEnabled) {
  await fetch(`/api/admin/shops/${id}/toggle_sms`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: !!makeEnabled})
  });
  loadShops();
}

async function triggerBackupNow() {
  const btn = event.target;
  const resultEl = document.getElementById('backupResult');
  btn.disabled = true;
  btn.textContent = 'Отправляю...';
  resultEl.innerHTML = '';
  try {
    const res = await fetch('/api/admin/backup_now', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      const botLine = data.bot_username
        ? `Открой чат с ботом <b>@${data.bot_username}</b> в Telegram — <a href="https://t.me/${data.bot_username}" target="_blank" style="color:#0F52BA; font-weight:700;">нажми сюда, чтобы открыть сразу</a>.`
        : `Имя бота не настроено на сервере (BOT_USERNAME) — но сообщение реально ушло, просто не могу подсказать точный чат.`;
      resultEl.innerHTML = `<div class="msg ok">✅ Копия отправлена в Telegram (${data.size_mb} МБ). ${botLine}</div>`;
    } else {
      resultEl.innerHTML = `<div class="msg err">❌ Не отправилось: ${data.error}</div>`;
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="msg err">❌ Ошибка сети: ${e}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Отправить сейчас';
  }
}

async function triggerRestore() {
  const fileInput = document.getElementById('restore_file');
  const confirmInput = document.getElementById('restore_confirm');
  const resultEl = document.getElementById('restoreResult');
  const file = fileInput.files[0];
  if (!file) { resultEl.innerHTML = `<div class="msg err">Выбери файл резервной копии (если копия пришла частями — выбери все части сразу)</div>`; return; }
  if (confirmInput.value.trim() !== 'ЗАМЕНИТЬ') {
    resultEl.innerHTML = `<div class="msg err">Впиши точно слово ЗАМЕНИТЬ, чтобы подтвердить</div>`;
    return;
  }
  if (!confirm(`Точно заменить ВСЮ текущую базу файлом «${file.name}»? Это необратимо без отдельной копии.`)) return;

  const btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Восстанавливаю...';
  resultEl.innerHTML = '';
  try {
    const formData = new FormData();
    for (const f of fileInput.files) formData.append('file', f);
    formData.append('confirm', confirmInput.value.trim());
    const res = await fetch('/api/admin/restore_backup', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.ok) {
      resultEl.innerHTML = `<div class="msg ok">✅ База восстановлена. Копия прежнего состояния отправлена тебе в Telegram на всякий случай. Обнови страницу.</div>`;
      confirmInput.value = '';
      fileInput.value = '';
    } else {
      resultEl.innerHTML = `<div class="msg err">❌ Не удалось: ${data.error}</div>`;
    }
  } catch (e) {
    resultEl.innerHTML = `<div class="msg err">❌ Ошибка сети: ${e}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Восстановить из этого файла';
  }
}

function toggleIdentityEdit(id) {
  const nameEdit = document.getElementById(`name_edit_${id}`);
  const usernameEdit = document.getElementById(`username_edit_${id}`);
  const isOpen = nameEdit.style.display !== 'none';
  nameEdit.style.display = isOpen ? 'none' : 'block';
  usernameEdit.style.display = isOpen ? 'none' : 'block';
}

async function saveIdentity(id) {
  const shop_name = document.getElementById(`name_input_${id}`).value.trim();
  const username = document.getElementById(`username_input_${id}`).value.trim();
  if (!shop_name || !username) { showMsg('Укажите и название, и логин.', false); return; }
  const res = await fetch(`/api/admin/shops/${id}/identity`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({shop_name, username})
  });
  const data = await res.json();
  if (data.ok) {
    document.getElementById(`name_view_${id}`).textContent = data.shop_name;
    document.getElementById(`username_view_${id}`).textContent = data.username;
    toggleIdentityEdit(id);
    showMsg('✅ Название и логин обновлены', true);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function resetPassword(id, username) {
  if (!confirm(`Сбросить пароль для «${username}»? Старый пароль перестанет работать.`)) return;
  const res = await fetch(`/api/admin/shops/${id}/reset_password`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    showMsgSticky(`✅ Новый пароль для «${username}» (больше не увидите — сохраните сейчас): <b>${data.password}</b>`);
    loadShops();
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

function copyOwnerLink(link, btn) {
  const done = () => {
    const original = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-check" style="color:#16A34A;"></i>скопировано';
    setTimeout(() => { btn.innerHTML = original; }, 1500);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(link).then(done).catch(() => {
      prompt('Скопируйте ссылку вручную:', link);
    });
  } else {
    prompt('Скопируйте ссылку вручную:', link);
  }
}

async function saveNotifyTelegram(id) {
  const notify_telegram_id = document.getElementById(`notify_id_${id}`).value.trim();
  const res = await fetch(`/api/admin/shops/${id}/notify_telegram`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({notify_telegram_id}),
  });
  const data = await res.json();
  if (data.ok) {
    showMsg('✅ Telegram ID сохранён', true);
  } else {
    showMsg('Ошибка: ' + data.error, false);
  }
}

async function testNotifyTelegram(id) {
  const res = await fetch(`/api/admin/shops/${id}/test_telegram`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    showMsg('✅ Тестовое сообщение доставлено — связь работает', true);
  } else {
    showMsgSticky(`❌ Не удалось отправить: ${data.error}`);
  }
}

async function createShop() {
  const payload = {
    shop_name: document.getElementById('new_shop_name').value.trim(),
    client_group: document.getElementById('new_client_group').value.trim(),
    username: document.getElementById('new_username').value.trim(),
    password: document.getElementById('new_password').value.trim(),
    phone: document.getElementById('new_phone').value.trim(),
    notify_telegram_id: document.getElementById('new_notify_id').value.trim(),
    address: document.getElementById('new_address').value.trim(),
  };
  const loc = document.getElementById('new_location').value.trim();
  if (loc) {
    const parts = loc.split(',').map(p => p.trim()).filter(Boolean);
    if (parts.length === 2 && !isNaN(parseFloat(parts[0])) && !isNaN(parseFloat(parts[1]))) {
      payload.lat = parts[0];
      payload.lon = parts[1];
    } else {
      showMsg('Локация должна быть в формате: широта, долгота (два числа через запятую).', false);
      return;
    }
  }
  if (!payload.shop_name || !payload.username) {
    showMsg('Заполните хотя бы название точки и логин.', false);
    return;
  }
  const res = await fetch('/api/admin/shops', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('newCreds').innerHTML =
      `<div class="new-creds">✅ Точка создана. Логин: <b>${data.username}</b>, пароль: <b>${data.password}</b><br>
       Сохраните пароль сейчас — второй раз он нигде не показывается.</div>`;
    ['new_shop_name','new_client_group','new_username','new_password','new_phone','new_notify_id','new_address','new_location'].forEach(id => document.getElementById(id).value = '');
    loadShops();
  } else {
    showMsg('Ошибка: ' + data.error, false);
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
guardOnce(['refMarkPaid', 'saveReferrer', 'createShop', 'createBranch', 'createEmployee', 'toggleEmployeeActive', 'saveBranchEdit', 'deleteBranch',
  'deleteEmployee', 'resetPassword', 'resetEmployeePassword', 'saveIdentity', 'saveNotifyTelegram',
  'triggerBackupNow', 'triggerRestore', 'toggleShop', 'toggleSms', 'toggleWarehouse', 'toggleBranchField',
  'subExtend', 'subSetDate', 'subLifetime', 'decideSub', 'markBranchPaid', 'saveSubSettings',
  'subPrice', 'editPayAmount', 'cancelPayment', 'decideReg',
  'ixBulk', 'ixBulkMsgSend', 'ixShopExtend', 'ixShopDate', 'ixShopPrice', 'ixShopLifetime', 'ixBranchPaid', 'ixDecide',
  'ixEditAmount', 'ixCancelPay', 'ixRSave']);
loadShops();
loadSubPanel();
loadRegs();
setInterval(() => { if (!document.hidden) loadRegs(); }, 60000);
loadRefs();
// ---------- Карта точек с аналитикой ----------
let MAP = null, MAPDATA = null, mapLayer = null, mapDays = 30, mapMetric = 'count', mapFilt = 'all', mapSub = 'all', mapGroupSel = '';
let mapMarkers = {}, mapPickId = null, mapFitted = false, mapSaving = false, leafletPromise = null;
const MAP_COLORS = { green: '#16A34A', yellow: '#EAB308', red: '#DC2626', off: '#94A3B8' };

function loadLeaflet() {
  if (window.L) return Promise.resolve();
  if (leafletPromise) return leafletPromise;
  leafletPromise = new Promise((resolve, reject) => {
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css';
    document.head.appendChild(css);
    const js = document.createElement('script');
    js.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
    js.onload = () => resolve();
    js.onerror = () => { leafletPromise = null; reject(new Error('leaflet')); };
    document.head.appendChild(js);
  });
  return leafletPromise;
}

function mapStatus(p) {
  if (!p.is_active) return 'off';
  if (p.days_idle === null || p.days_idle === undefined) return 'red';
  if (p.days_idle <= 3) return 'green';
  if (p.days_idle <= 14) return 'yellow';
  return 'red';
}
function mapIdleText(p) {
  if (!p.is_active) return 'Точка выключена';
  if (!p.last_date) return 'Замен ещё не было';
  if (p.days_idle === 0) return `Сегодня замен: ${p.today}`;
  if (p.days_idle === 1) return 'Последняя замена вчера';
  return `Последняя замена ${p.days_idle} дн. назад`;
}
function mapKindText(p) {
  if (p.kind === 'branch') return 'Филиал · ' + escapeHtml(p.parent_name || p.parent_username || '');
  if (p.kind === 'main') return `Главная точка · филиалов: ${p.branch_count}`;
  return 'Самостоятельная точка';
}
function mapSubText(p) {
  if (p.sub_lifetime) return '∞ Бессрочная лицензия';
  if (!p.sub_until) return 'Дата оплаты не указана';
  const d = p.sub_until.split('-').reverse().join('.');
  if (p.sub_status === 'blocked') return `Заблокировано за неуплату · с ${d} (${-p.sub_left} дн.)`;
  if (p.sub_status === 'soon') return `Скоро истекает · до ${d} (осталось ${p.sub_left} дн.)`;
  return `Оплачено до ${d}`;
}
const MAP_SUB_COLORS = { paid: '#16A34A', soon: '#EAB308', blocked: '#DC2626', unset: '#94A3B8' };
function mapPctHtml(pct) {
  if (pct === null || pct === undefined) return '<span style="color:#94A3B8">—</span>';
  const up = pct >= 0;
  return `<span style="color:${up ? '#16A34A' : '#DC2626'}">${up ? '▲' : '▼'} ${Math.abs(pct)}%</span>`;
}
function mapVisible() {
  if (!MAPDATA) return [];
  return MAPDATA.points.filter(p =>
    (!mapGroupSel || (p.client_group || '') === mapGroupSel) &&
    (mapFilt === 'all' || mapStatus(p) === mapFilt) &&
    (mapSub === 'all' || p.sub_status === mapSub));
}

async function loadMap() {
  const kp = document.getElementById('mapKpis');
  if (!MAPDATA) kp.innerHTML = '<div class="hint-text">Загружаю карту…</div>';
  try {
    await loadLeaflet();
  } catch (e) {
    kp.innerHTML = '<div class="msg err">Не удалось загрузить карту — проверь интернет и открой вкладку ещё раз.</div>';
    return;
  }
  let data;
  try {
    const res = await fetch(`/api/admin/map?days=${mapDays}`);
    data = await res.json();
  } catch (e) {
    if (!MAPDATA) kp.innerHTML = '<div class="msg err">Не удалось получить данные точек.</div>';
    return;
  }
  if (!data || !data.points) return;
  MAPDATA = data;
  if (!MAP) {
    MAP = L.map('admMapBox', { zoomControl: true }).setView([40.8, 71.8], 8);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; OpenStreetMap'
    }).addTo(MAP);
    mapLayer = L.layerGroup().addTo(MAP);
    MAP.on('click', e => { if (mapPickId) mapSaveLocation(mapPickId, e.latlng.lat, e.latlng.lng); });
  }
  const groups = [...new Set(MAPDATA.points.map(p => p.client_group).filter(Boolean))].sort();
  const sel = document.getElementById('mapGroup');
  sel.innerHTML = '<option value="">Все сети</option>' + groups.map(g =>
    `<option value="${escapeHtml(g)}"${g === mapGroupSel ? ' selected' : ''}>${escapeHtml(g)}</option>`).join('');
  sel.style.display = groups.length ? '' : 'none';
  setTimeout(() => { MAP.invalidateSize(); renderMap(); }, 30);
}

function renderMap() {
  if (!MAP || !MAPDATA) return;
  const pts = mapVisible();
  const withXY = pts.filter(p => p.lat !== null && p.lon !== null);
  const noXY = pts.filter(p => p.lat === null || p.lon === null);
  const all = MAPDATA.points;
  const sum = (arr, k) => arr.reduce((a, p) => a + (Number(p[k]) || 0), 0);
  const per = MAPDATA.days === 7 ? '7 дней' : MAPDATA.days === 90 ? '3 месяца' : '30 дней';

  document.getElementById('mapKpis').innerHTML = `
    <div class="map-kpi"><b>${withXY.length} <small style="font-size:13px;color:#94A3B8">из ${all.length}</small></b><span>на карте</span></div>
    <div class="map-kpi"><b style="color:#16A34A">${all.filter(p => p.is_active && p.today > 0).length}</b><span>работали сегодня</span></div>
    <div class="map-kpi"><b style="color:#DC2626">${all.filter(p => mapStatus(p) === 'red').length}</b><span>молчат больше 14 дней</span></div>
    <div class="map-kpi"><b>${fmtShort(sum(pts, 'total'))}</b><span>${sum(pts, 'count').toLocaleString('ru-RU')} замен · ${per}</span></div>`;
  const subCnt = k => all.filter(p => p.sub_status === k).length;
  [['all', 'Все', all.length], ['paid', 'Оплачено', subCnt('paid')], ['soon', 'Скоро истекает', subCnt('soon')],
   ['blocked', 'Заблокировано', subCnt('blocked')]].forEach(([k, t, n]) => {
    const b = document.querySelector('#mapSubSeg button[data-s="' + k + '"]');
    if (b) b.textContent = k === 'all' ? t : `${t} · ${n}`;
  });

  mapLayer.clearLayers();
  mapMarkers = {};
  if (document.getElementById('mapLinksChk').checked) {
    const byId = {};
    MAPDATA.points.forEach(p => { byId[p.id] = p; });
    withXY.forEach(p => {
      const par = p.kind === 'branch' ? byId[p.parent_shop_id] : null;
      if (par && par.lat !== null && par.lon !== null) {
        L.polyline([[par.lat, par.lon], [p.lat, p.lon]], { color: '#0F52BA', weight: 2, opacity: .55, dashArray: '6 6', interactive: false }).addTo(mapLayer);
      }
    });
  }
  withXY.slice().sort((a, b) => (Number(b[mapMetric]) || 0) - (Number(a[mapMetric]) || 0)).forEach(p => {
    const st = mapStatus(p);
    const r = 9;  // одинаковый размер у всех точек, цвет — по активности
    const m = L.circleMarker([p.lat, p.lon], {
      radius: r, color: p.kind === 'main' ? '#0A2540' : '#fff', weight: p.kind === 'main' ? 4 : 2,
      fillColor: MAP_COLORS[st], fillOpacity: .9
    }).addTo(mapLayer);
    m.bindPopup(() => mapPopupHtml(p), { maxWidth: 280 });
    m.bindTooltip(escapeHtml(p.shop_name || p.username), { direction: 'top', offset: [0, -r] });
    mapMarkers[p.id] = m;
  });
  if (!mapFitted && withXY.length) {
    mapFitted = true;
    if (withXY.length === 1) MAP.setView([withXY[0].lat, withXY[0].lon], 14);
    else MAP.fitBounds(withXY.map(p => [p.lat, p.lon]), { padding: [30, 30], maxZoom: 14 });
  }

  const nc = document.getElementById('mapNoCoords');
  if (noXY.length) {
    nc.style.display = '';
    nc.innerHTML = `<h3><i class="fa-solid fa-location-dot" style="color:#DC2626"></i> Нет на карте (${noXY.length})</h3>` +
      noXY.map(p => `<div class="map-row" style="cursor:default">
        <span class="mr-dot" style="background:${MAP_COLORS[mapStatus(p)]}"></span>
        <span class="mr-name">${escapeHtml(p.shop_name || p.username)}<small>${mapKindText(p)}</small></span>
        <button class="mr-pin" onclick="mapStartPick(${p.id})"><i class="fa-solid fa-map-pin"></i> Указать</button>
      </div>`).join('');
  } else {
    nc.style.display = 'none';
  }

  const ranked = pts.slice().sort((a, b) => (Number(b[mapMetric]) || 0) - (Number(a[mapMetric]) || 0));
  document.getElementById('mapRating').innerHTML = `<h3><i class="fa-solid fa-ranking-star" style="color:#EAB308"></i> Рейтинг за ${per} — по ${mapMetric === 'total' ? 'выручке' : 'заменам'}</h3>` +
    (ranked.length ? ranked.map((p, i) => `<div class="map-row" onclick="mapFocus(${p.id})">
        <span class="mr-n">${i + 1}</span>
        <span class="mr-dot" style="background:${MAP_COLORS[mapStatus(p)]}"></span>
        <span class="mr-name">${escapeHtml(p.shop_name || p.username)}<small>${mapKindText(p)} · ${mapIdleText(p)}</small></span>
        <span class="mr-val">${mapMetric === 'total' ? fmtShort(p.total) : p.count + ' зам.'}<small>${mapPctHtml(p.pct)}</small></span>
      </div>`).join('') : '<div class="hint-text" style="padding:12px 14px">Нет точек под этот фильтр.</div>');
}

function mapPopupHtml(p) {
  const st = mapStatus(p);
  const addr = [p.address, p.hours].filter(Boolean).map(escapeHtml).join(' · ');
  const per = MAPDATA.days === 7 ? '7 дн' : MAPDATA.days === 90 ? '3 мес' : '30 дн';
  return `<div class="map-pop">
    <div class="mp-name">${escapeHtml(p.shop_name || p.username)}</div>
    <div class="mp-kind">${mapKindText(p)}${p.client_group ? ' · ' + escapeHtml(p.client_group) : ''}</div>
    <div class="mp-st" style="color:${MAP_COLORS[st]}">● ${mapIdleText(p)}</div>
    <div class="mp-st" style="color:${MAP_SUB_COLORS[p.sub_status] || '#94A3B8'}"><i class="fa-solid fa-credit-card"></i> ${mapSubText(p)}</div>
    <div class="mp-grid">
      <div><b>${p.count}</b>замен · ${per}</div>
      <div><b>${fmtShort(p.total)}</b>выручка ${mapPctHtml(p.pct)}</div>
      <div><b>${fmtShort(p.avg)}</b>средний чек</div>
      <div><b>${p.clients}</b>клиентов · всего ${p.client_count}</div>
    </div>
    ${addr ? `<div class="mp-addr"><i class="fa-solid fa-location-dot"></i> ${addr}</div>` : ''}
    ${p.phone ? `<div class="mp-addr"><i class="fa-solid fa-phone"></i> <a href="tel:${escapeHtml(p.phone)}">${escapeHtml(p.phone)}</a></div>` : ''}
    <button class="mp-snap" onclick="openSnapshot(${p.id})"><i class="fa-solid fa-oil-can"></i> Статистика, склад и поставщики</button>
    <div class="mp-act">
      <button class="b2" onclick="mapOpenCard(${p.id})">Карточка</button>
      <a class="b2" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lon}">Маршрут</a>
      <button class="b2" onclick="anaOpenFromMap(${p.id})">Аналитика</button>
      <button class="b2" onclick="mapStartPick(${p.id})">Переместить</button>
    </div>
  </div>`;
}

function setMapDays(d) {
  mapDays = d;
  document.querySelectorAll('#mapDaysSeg button').forEach(b => b.classList.toggle('on', Number(b.dataset.d) === d));
  loadMap();
}
function setMapMetric(m) {
  mapMetric = m;
  document.querySelectorAll('#mapMetricSeg button').forEach(b => b.classList.toggle('on', b.dataset.m === m));
  renderMap();
}
function setMapSub(s) {
  mapSub = s;
  document.querySelectorAll('#mapSubSeg button').forEach(b => b.classList.toggle('on', b.dataset.s === s));
  renderMap();
}
function setMapFilter(f) {
  mapFilt = f;
  document.querySelectorAll('#mapFilterSeg button').forEach(b => b.classList.toggle('on', b.dataset.f === f));
  renderMap();
}
function mapFocus(id) {
  const p = MAPDATA.points.find(x => x.id === id);
  if (!p) return;
  if (p.lat === null || p.lon === null) { mapStartPick(id); return; }
  document.querySelector('#admMap .map-wrap').scrollIntoView({ behavior: 'smooth', block: 'center' });
  MAP.setView([p.lat, p.lon], Math.max(MAP.getZoom(), 14));
  setTimeout(() => { if (mapMarkers[id]) mapMarkers[id].openPopup(); }, 350);
}
function mapOpenCard(id) {
  const p = MAPDATA.points.find(x => x.id === id);
  if (!p) return;
  admTab('main');
  setShopFilter('all');
  const search = document.getElementById('shopSearch');
  search.value = p.kind === 'branch' ? (p.parent_username || '') : (p.username || '');
  filterShops();
  setTimeout(() => search.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
}
function mapStartPick(id) {
  const p = MAPDATA.points.find(x => x.id === id);
  if (!p) return;
  if (MAP) MAP.closePopup();
  mapPickId = id;
  document.getElementById('mapPickText').innerHTML = `<i class="fa-solid fa-map-pin"></i> Нажми на карте, где находится <b>${escapeHtml(p.shop_name || p.username)}</b>. Можно приблизить карту пальцами.`;
  document.getElementById('mapPick').style.display = 'block';
  document.getElementById('admMapBox').classList.add('picking');
  document.querySelector('#admMap .map-wrap').scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function mapPickCancel() {
  mapPickId = null;
  document.getElementById('mapPick').style.display = 'none';
  document.getElementById('admMapBox').classList.remove('picking');
}
function mapPickHere() {
  if (!mapPickId) return;
  if (!navigator.geolocation) { showMsg('Телефон не даёт определить местоположение.', false); return; }
  const id = mapPickId;
  navigator.geolocation.getCurrentPosition(
    pos => mapSaveLocation(id, pos.coords.latitude, pos.coords.longitude),
    () => showMsg('Не удалось определить местоположение — разреши доступ к геолокации или нажми место на карте.', false),
    { enableHighAccuracy: true, timeout: 15000 });
}
async function mapSaveLocation(id, lat, lon) {
  if (mapSaving) return;
  const p = MAPDATA.points.find(x => x.id === id);
  const name = p ? (p.shop_name || p.username) : '';
  if (!confirm(`Поставить «${name}» сюда?\\n${lat.toFixed(6)}, ${lon.toFixed(6)}`)) return;
  mapSaving = true;
  try {
    const res = await fetch(`/api/admin/shops/${id}/location`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat: lat, lon: lon })
    });
    const data = await res.json();
    if (!data.ok) { showMsg(data.error || 'Не удалось сохранить место.', false); return; }
    if (p) { p.lat = data.lat; p.lon = data.lon; }
    mapPickCancel();
    renderMap();
    MAP.setView([data.lat, data.lon], Math.max(MAP.getZoom(), 15));
    showMsg(`Точка «${escapeHtml(name)}» на карте.`, true);
  } catch (e) {
    showMsg('Не удалось сохранить место — проверь интернет.', false);
  } finally {
    mapSaving = false;
  }
}
// ---------- Аналитика продаж: бренды, доля MITAL, цены, возможности ----------
let ANA_CATLIST = [];
let anaView = 'main', NAMES = null, nmTab = 'review', nmEdit = null, nmSearch = '', PRICEPROB = null, ppShop = 0;
let ANA = null, anaDays = 30, anaGroup = '', anaShop = 0, anaCat = 'all', anaProduct = '', anaLoading = false;
const ANA_CATS = [
  ['all', 'Все товары'], ['fluid_0', 'Моторное'], ['fluid_1', 'АКПП/МКПП'], ['fluid_2', 'Антифриз'],
  ['fluid_3', 'Тормозная'], ['fluid_4', 'Редуктор'], ['filters', 'Фильтры'], ['other', 'Прочие товары']
];

async function loadAna() {
  if (anaLoading) return;
  anaLoading = true;
  if (!ANA) document.getElementById('anaBody').innerHTML = '<div class="hint-text">Загружаю…</div>';
  try {
    const res = await fetch(`/api/admin/analytics?days=${anaDays}`);
    const data = await res.json();
    if (data && data.rows) { ANA = data; ANA_CATLIST = data.categories || ANA_CATLIST; }
  } catch (e) {
    if (!ANA) document.getElementById('anaBody').innerHTML = '<div class="msg err">Не удалось получить данные — проверь интернет.</div>';
  } finally {
    anaLoading = false;
  }
  if (ANA) renderAna();
}
function setAnaDays(d) {
  anaDays = d;
  document.querySelectorAll('#anaDaysSeg button').forEach(b => b.classList.toggle('on', Number(b.dataset.d) === d));
  if (anaView === 'prices') { PRICEPROB = null; renderPriceProblems(); loadPriceProblems(); }
  loadAna();
}
function setAnaCat(c) { anaCat = c; anaProduct = ''; renderAna(); }
function anaPickShop(id) {
  anaShop = id || 0;
  renderAna();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function anaOpenFromMap(id) {
  anaView = 'main';
  document.getElementById('anaFilters').style.display = '';
  document.getElementById('anaDaysBar').style.display = '';
  admTab('analytics');
  anaShop = id;
  if (ANA) renderAna();
}
function anaPickProduct(key) {
  anaProduct = key;
  renderAna();
  const el = document.getElementById('anaPrices');
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function anaKey(k) { return encodeURIComponent(k).replace(/'/g, '%27'); }
function anaCatOk(c) {
  return anaCat === 'all' || c === anaCat || (anaCat === 'filters' && String(c).indexOf('filter_') === 0);
}
function anaUnit(c) { return String(c).indexOf('fluid_') === 0 ? 'л' : 'шт'; }
function anaCatLabel(c) {
  const f = (ANA.categories || []).find(x => x.key === c);
  return f ? f.label : c;
}
function anaPoint(id) { return ANA.points.find(p => p.id === id); }
function anaPointName(p) { return p ? (p.shop_name || p.username) : '—'; }
function anaPointSub(p) {
  if (!p) return '';
  if (p.kind === 'branch') return 'филиал · ' + escapeHtml(p.parent_name || '');
  if (p.kind === 'main') return 'главная точка';
  return 'самостоятельная';
}
// точки в рамках выбранной сети (без учёта выбранной точки)
function anaGroupIds() {
  const ids = new Set();
  ANA.points.forEach(p => { if (!anaGroup || (p.client_group || '') === anaGroup) ids.add(p.id); });
  return ids;
}
function anaRows(withShop) {
  const ids = anaGroupIds();
  return ANA.rows.filter(r => ids.has(r.s) && anaCatOk(r.c) && (!withShop || !anaShop || r.s === anaShop));
}
function anaTotals(rows) {
  const t = { t: 0, m: 0, cs: 0, ct: 0, bad: 0, q: 0, ut: 0 };
  rows.forEach(r => { t.t += r.t; t.q += r.q; t.cs += r.cs; t.ct += r.ct; t.bad += r.bad; t.ut += r.ut || 0; if (r.m) t.m += r.t; });
  t.share = t.t ? Math.round(t.m / t.t * 100) : null;
  t.markup = t.cs ? Math.round((t.ct - t.cs) / t.cs * 100) : null;
  return t;
}
function anaQuality(ids) {
  let lines = 0, stock = 0, cost = 0;
  ANA.points.forEach(p => { if (ids.has(p.id)) { lines += p.quality.lines; stock += p.quality.stock; cost += p.quality.cost; } });
  return { lines, stock, cost, stockPct: lines ? Math.round(stock / lines * 100) : null, costPct: lines ? Math.round(cost / lines * 100) : null };
}
function anaPct(v) { return v === null || v === undefined ? '—' : v + '%'; }
function anaMoney(v) { return v === null || v === undefined || isNaN(v) ? '—' : Math.round(v).toLocaleString('ru-RU'); }
function anaQty(q, unit) {
  const n = Math.round(q * 10) / 10;
  return n.toLocaleString('ru-RU') + ' ' + unit;
}
// бренды: сумма, количество (если единица одна), доля
function anaBrands(rows) {
  const by = {};
  rows.forEach(r => {
    const k = r.b || '—';
    const b = by[k] = by[k] || { name: k === '—' ? 'без марки' : k, t: 0, q: 0, units: new Set(), m: r.m };
    b.t += r.t; b.q += r.q; b.units.add(anaUnit(r.c));
  });
  return Object.values(by).sort((a, b) => b.t - a.t);
}
// товары: агрегируем по категории + названию
function anaProducts(rows) {
  const by = {};
  rows.forEach(r => {
    const k = r.c + '|' + r.k;
    const p = by[k] = by[k] || { key: k, name: r.p || 'без названия', c: r.c, m: r.m, t: 0, q: 0, pt: 0, pq: 0, cs: 0, cq: 0, ct: 0, bad: 0, shops: new Set() };
    p.t += r.t; p.q += r.q; p.pt += r.pt; p.pq += r.pq; p.cs += r.cs; p.cq += r.cq; p.ct += r.ct; p.bad += r.bad; p.shops.add(r.s);
  });
  return Object.values(by).sort((a, b) => b.t - a.t);
}
function anaMarkupHtml(ct, cs) {
  if (!cs) return '<span class="ana-mute">—</span>';
  const v = Math.round((ct - cs) / cs * 100);
  return `<span class="${v < 10 ? 'ana-bad' : ''}">${v}%</span>`;
}

function renderAna() {
  if (anaView === 'names') { renderNames(); return; }
  if (anaView === 'prices') { renderPriceProblems(); return; }
  if (!ANA) return;
  document.getElementById('anaFilters').style.display = '';
  // фильтры: сеть, точка, категория
  const groups = [...new Set(ANA.points.map(p => p.client_group).filter(Boolean))].sort();
  const gSel = document.getElementById('anaGroup');
  gSel.innerHTML = '<option value="">Все сети</option>' + groups.map(g =>
    `<option value="${escapeHtml(g)}"${g === anaGroup ? ' selected' : ''}>${escapeHtml(g)}</option>`).join('');
  gSel.style.display = groups.length ? '' : 'none';
  const ids = anaGroupIds();
  if (anaShop && !ids.has(anaShop)) anaShop = 0;
  const sSel = document.getElementById('anaShopSel');
  sSel.innerHTML = `<option value="0">Все точки (${ids.size})</option>` + ANA.points.filter(p => ids.has(p.id)).map(p =>
    `<option value="${p.id}"${p.id === anaShop ? ' selected' : ''}>${escapeHtml(anaPointName(p))}${p.kind === 'branch' ? ' (филиал)' : ''}</option>`).join('');
  document.getElementById('anaCats').innerHTML = ANA_CATS.map(([k, l]) =>
    `<button class="${k === anaCat ? 'on' : ''}" onclick="setAnaCat('${k}')">${l}</button>`).join('');

  const rows = anaRows(true);
  const netRows = anaRows(false);
  const tot = anaTotals(rows);
  const netTot = anaTotals(netRows);
  const scopeIds = anaShop ? new Set([anaShop]) : ids;
  const ql = anaQuality(scopeIds);
  const netQl = anaQuality(ids);
  const per = anaDays === 365 ? 'год' : anaDays === 90 ? '3 месяца' : '30 дней';
  const vsNet = (v, n) => anaShop ? `<small style="display:block;font-size:11px;color:#94A3B8;font-weight:500">сеть: ${n}</small>` : '';
  let h = '';

  // ---- 1. ключевые цифры ----
  h += `<div class="map-kpis">
    <div class="map-kpi"><b>${fmtShort(tot.t)}</b><span>продажи товаров · ${per}</span></div>
    <div class="map-kpi"><b style="color:#B45309">${anaPct(tot.share)}</b><span>доля MITAL по сумме</span>${vsNet(tot.share, anaPct(netTot.share))}</div>
    <div class="map-kpi"><b>${anaPct(tot.markup)}</b><span>средняя наценка</span>${vsNet(tot.markup, anaPct(netTot.markup))}</div>
    <div class="map-kpi"><b style="color:${ql.stockPct !== null && ql.stockPct < 50 ? '#DC2626' : '#16A34A'}">${anaPct(ql.stockPct)}</b><span>позиций со склада</span>${vsNet(ql.stockPct, anaPct(netQl.stockPct))}</div>
  </div>`;
  if (!rows.length) {
    h += '<div class="ana-card"><div class="hint-text" style="padding:14px">За этот период и фильтр продаж товаров нет.</div></div>';
    document.getElementById('anaBody').innerHTML = h;
    return;
  }
  const utPct = tot.t ? Math.round(tot.ut / tot.t * 1000) / 10 : 0;
  h += `<div class="ana-dq">
    <div class="dq-txt"><b>Точность данных</b><br>
      ${utPct > 0 ? `<span class="${utPct >= 5 ? 'ana-bad' : ''}">Не распознано: ${utPct}% продаж (${fmtShort(tot.ut)})</span>` : '<span class="ana-good">Все названия распознаны ✓</span>'}
      · ${tot.bad ? `<span class="ana-bad">подозрительных цен: ${tot.bad}</span> — не входят в цены и наценку` : '<span class="ana-good">подозрительных цен нет</span>'}</div>
    <div class="dq-act"><button class="ana-btn" onclick="anaOpenView('names')"><i class="fa-solid fa-spell-check"></i> Сопоставление</button>
      <button class="ana-btn" onclick="anaOpenView('prices')"><i class="fa-solid fa-triangle-exclamation"></i> Проблемные цены</button></div>
  </div>`;

  // ---- 3. карточка выбранной точки ----
  if (anaShop) {
    const p = anaPoint(anaShop);
    const oilRows = ANA.rows.filter(r => r.s === anaShop && r.c === 'fluid_0');
    const netOil = ANA.rows.filter(r => ids.has(r.s) && r.c === 'fluid_0');
    const lp = rs => { const q = rs.reduce((a, r) => a + r.pq, 0); return q ? rs.reduce((a, r) => a + r.pt, 0) / q : null; };
    const cp = rs => { const q = rs.reduce((a, r) => a + r.cq, 0); return q ? rs.reduce((a, r) => a + r.cs, 0) / q : null; };
    h += `<div class="ana-card"><h3><i class="fa-solid fa-store" style="color:var(--blue)"></i> ${escapeHtml(anaPointName(p))}<small>${anaPointSub(p)}</small></h3>
      <div class="ana-cmp">
        <div><b>${anaMoney(lp(oilRows))}</b>моторное масло, сум/л · сеть ${anaMoney(lp(netOil))}</div>
        <div><b>${anaMoney(cp(oilRows))}</b>закупка масла, сум/л · сеть ${anaMoney(cp(netOil))}</div>
        <div><b>${anaPct(ql.costPct)}</b>позиций с ценой закупки · сеть ${anaPct(netQl.costPct)}</div>
        <div><b>${ql.lines}</b>проданных позиций за ${per}</div>
      </div>
      <div class="ana-note">${ql.stockPct !== null && ql.stockPct < 50 ? '⚠️ Больше половины масла и фильтров точка вписывает вручную, не со склада — наценка и закупка по ним неизвестны. Цифры точки пока неполные.' : 'Данные точки достаточно полные: большая часть товаров выбирается со склада.'}</div>
      <div style="padding:10px 14px; display:flex; gap:8px; flex-wrap:wrap;">
        <button class="ana-btn" onclick="anaPickShop(0)"><i class="fa-solid fa-arrow-left"></i> Вся сеть</button>
        <button class="ana-btn" onclick="openSnapshot(${anaShop})"><i class="fa-solid fa-oil-can"></i> Статистика и склад точки</button>
        <button class="ana-btn" onclick="admTab('map'); setTimeout(() => { if (MAPDATA) mapFocus(${anaShop}); }, 600);"><i class="fa-solid fa-map-location-dot"></i> На карте</button>
      </div></div>`;
  }

  // ---- 1. бренды ----
  const brands = anaBrands(rows);
  const top = brands.slice(0, 12);
  const rest = brands.slice(12);
  h += `<div class="ana-card"><h3><i class="fa-solid fa-tags" style="color:#EAB308"></i> Бренды — что продаётся<small>по сумме</small></h3>` +
    top.map(b => {
      const share = tot.t ? Math.round(b.t / tot.t * 1000) / 10 : 0;
      const qty = b.units.size === 1 ? anaQty(b.q, [...b.units][0]) : '';
      return `<div class="ana-row"><div class="ar-main">
        <div class="ar-name">${escapeHtml(b.name)}${b.m ? '<span class="mital-tag">MITAL</span>' : ''}</div>
        <div class="ar-bar"><i class="${b.m ? 'mital' : ''}" style="width:${Math.max(2, Math.min(100, share))}%"></i></div>
      </div><div class="ar-val">${fmtShort(b.t)}<small>${share}%${qty ? ' · ' + qty : ''}</small></div></div>`;
    }).join('') +
    (rest.length ? `<div class="ana-row"><div class="ar-main"><div class="ar-name ana-mute">Остальные (${rest.length})</div></div><div class="ar-val">${fmtShort(rest.reduce((a, b) => a + b.t, 0))}</div></div>` : '') +
    '</div>';

  // ---- 1. топ товаров ----
  const prods = anaProducts(rows);
  h += `<div class="ana-card"><h3><i class="fa-solid fa-ranking-star" style="color:var(--blue)"></i> Топ товаров<small>нажми — цены по точкам</small></h3>
    <div class="ana-tbl-wrap"><table class="ana-tbl"><tr><th>Товар</th><th>Цена</th><th>Закупка</th><th>Нац.</th></tr>` +
    prods.slice(0, 15).map(p => `<tr class="click" onclick="anaPickProduct('${anaKey(p.key)}')">
      <td>${escapeHtml(p.name)}${p.m ? '<span class="mital-tag">MITAL</span>' : ''}${p.bad ? ' ⚠️' : ''}<div class="ar-sub">${escapeHtml(anaCatLabel(p.c))} · ${anaQty(p.q, anaUnit(p.c))} · ${fmtShort(p.t)} сум</div></td>
      <td>${anaMoney(p.pq ? p.pt / p.pq : null)}</td>
      <td>${p.cq ? anaMoney(p.cs / p.cq) : '<span class="ana-mute">—</span>'}</td>
      <td>${anaMarkupHtml(p.ct, p.cs)}</td></tr>`).join('') +
    '</table></div></div>';

  // ---- 2. цены по точкам ----
  const netProds = anaProducts(netRows).filter(p => p.shops.size >= 1);
  if (!anaProduct || !netProds.find(p => anaKey(p.key) === anaProduct)) {
    const first = netProds.find(p => p.shops.size > 1) || netProds[0];
    anaProduct = first ? anaKey(first.key) : '';
  }
  const cur = netProds.find(p => anaKey(p.key) === anaProduct);
  if (cur) {
    const unit = anaUnit(cur.c);
    const pr = netRows.filter(r => r.c + '|' + r.k === cur.key).sort((a, b) => (b.pq ? b.pt / b.pq : 0) - (a.pq ? a.pt / a.pq : 0));
    const sales = pr.filter(r => r.pq > 0).map(r => r.pt / r.pq);
    const costs = pr.filter(r => r.cq > 0).map(r => r.cs / r.cq);
    const mn = a => a.length ? Math.min(...a) : null, mx = a => a.length ? Math.max(...a) : null;
    const minS = mn(sales), maxS = mx(sales), minC = mn(costs), maxC = mx(costs);
    const multi = pr.length > 1;
    h += `<div class="ana-card" id="anaPrices"><h3><i class="fa-solid fa-scale-balanced" style="color:#16A34A"></i> Цены по точкам</h3>
      <div style="padding:10px 14px 4px"><select style="width:100%;border:1px solid var(--border);border-radius:10px;padding:9px 10px;font-size:13px;font-family:inherit;background:#fff" onchange="anaPickProduct(this.value)">` +
      netProds.slice(0, 200).map(p => `<option value="${anaKey(p.key)}"${anaKey(p.key) === anaProduct ? ' selected' : ''}>${escapeHtml(p.name)} — ${p.shops.size} точ.</option>`).join('') +
      `</select></div>
      <div class="ana-tbl-wrap"><table class="ana-tbl"><tr><th>Точка</th><th>Цена/${unit}</th><th>Закупка</th><th>Нац.</th></tr>` +
      pr.map(r => {
        const sp = r.pq ? r.pt / r.pq : null, cp = r.cq ? r.cs / r.cq : null;
        const p = anaPoint(r.s);
        const sCls = multi && sp === maxS ? 'ana-bad' : multi && sp === minS ? 'ana-good' : '';
        const cCls = multi && cp !== null && costs.length > 1 && cp === minC ? 'ana-good' : multi && cp !== null && costs.length > 1 && cp === maxC ? 'ana-bad' : '';
        return `<tr class="click${r.s === anaShop ? ' sum' : ''}" onclick="anaPickShop(${r.s})"><td>${escapeHtml(anaPointName(p))}${r.bad ? ' ⚠️' : ''}<div class="ar-sub">${anaPointSub(p)} · ${anaQty(r.q, unit)}</div></td>
          <td class="${sCls}">${anaMoney(sp)}</td>
          <td class="${cCls}">${cp === null ? '<span class="ana-mute">—</span>' : anaMoney(cp)}</td><td>${anaMarkupHtml(r.ct, r.cs)}</td></tr>`;
      }).join('') +
      ''+
      `</table></div>` +
      (multi ? `<div class="ana-range">Продажа за ${unit}: мин <b>${anaMoney(minS)}</b> · средн. <b>${anaMoney(cur.pq ? cur.pt / cur.pq : null)}</b> · макс <b>${anaMoney(maxS)}</b>` +
        (costs.length ? `<br>Закупка за ${unit}: мин <b>${anaMoney(minC)}</b> · средн. <b>${anaMoney(cur.cs / cur.cq)}</b> · макс <b>${anaMoney(maxC)}</b>` : '') +
        `<br>Всего продано: <b>${anaQty(cur.q, unit)}</b> · наценка по сети ${anaMarkupHtml(cur.ct, cur.cs)}</div>` : '') +
      `<div class="ana-note">Зелёный — самая низкая цена, красный — самая высокая. Нажми на точку, чтобы открыть её аналитику.</div></div>`;
  }

  // ---- 3. сравнение точек (только для всей сети) ----
  if (!anaShop) {
    const per_shop = {};
    netRows.forEach(r => { (per_shop[r.s] = per_shop[r.s] || []).push(r); });
    const list = ANA.points.filter(p => ids.has(p.id)).map(p => ({ p, t: anaTotals(per_shop[p.id] || []), q: p.quality }))
      .sort((a, b) => b.t.t - a.t.t);
    h += `<div class="ana-card"><h3><i class="fa-solid fa-store" style="color:var(--blue)"></i> Точки<small>нажми — аналитика точки</small></h3>
      <div class="ana-tbl-wrap"><table class="ana-tbl"><tr><th>Точка</th><th>Продажи</th><th>MITAL</th><th>Нац.</th><th>Склад</th></tr>` +
      list.map(x => {
        const sp = x.q.lines ? Math.round(x.q.stock / x.q.lines * 100) : null;
        return `<tr class="click" onclick="anaPickShop(${x.p.id})"><td>${escapeHtml(anaPointName(x.p))}<div class="ar-sub">${anaPointSub(x.p)}</div></td>
        <td>${fmtShort(x.t.t)}</td><td style="color:#B45309">${anaPct(x.t.share)}</td><td>${anaPct(x.t.markup)}</td>
        <td class="${sp !== null && sp < 50 ? 'ana-bad' : ''}">${anaPct(sp)}</td></tr>`;
      }).join('') + '</table></div><div class="ana-note">Нац. — средняя наценка. Склад — какая доля масла и фильтров выбрана со склада: чем выше, тем точнее цифры точки.</div></div>';
  }

  // ---- 4. возможности для продаж ----
  const opp = {};
  netRows.forEach(r => {
    if (anaShop && r.s !== anaShop) return;
    const o = opp[r.s] = opp[r.s] || { s: r.s, other: 0, mital: 0, brands: {} };
    if (r.m) o.mital += r.t; else o.other += r.t;
    const b = o.brands[r.b || 'без марки'] = o.brands[r.b || 'без марки'] || { name: r.b || 'без марки', t: 0, q: 0, units: new Set(), m: r.m };
    b.t += r.t; b.q += r.q; b.units.add(anaUnit(r.c));
  });
  const oppList = Object.values(opp).filter(o => o.other > 0).sort((a, b) => b.other - a.other);
  h += `<div class="ana-card"><h3><i class="fa-solid fa-bullseye" style="color:#DC2626"></i> Возможности для продаж<small>что точки берут у других</small></h3>
    <div class="ana-note">Сколько точка продала товаров других брендов — это объём, который можно предложить заменить. Жёлтым — бренды MITAL.</div>` +
    (oppList.length ? oppList.slice(0, 30).map(o => {
      const p = anaPoint(o.s);
      const all = o.other + o.mital;
      const share = all ? Math.round(o.mital / all * 100) : 0;
      const bs = Object.values(o.brands).sort((a, b) => b.t - a.t).slice(0, 6);
      return `<div class="ana-row click" onclick="anaPickShop(${o.s})"><div class="ar-main">
        <div class="ar-name">${escapeHtml(anaPointName(p))} <span class="ar-sub" style="display:inline">${anaPointSub(p)}</span></div>
        <div class="ana-brands">${bs.map(b => `<span class="${b.m ? 'm' : ''}">${escapeHtml(b.name)} ${b.units.size === 1 ? anaQty(b.q, [...b.units][0]) : fmtShort(b.t)}</span>`).join('')}</div>
        <div class="ar-bar"><i class="mital" style="width:${Math.max(share ? 2 : 0, share)}%"></i></div>
      </div><div class="ar-val ana-bad">${fmtShort(o.other)}<small>MITAL ${share}%</small></div></div>`;
    }).join('') : '<div class="hint-text" style="padding:12px 14px">Здесь все продажи — бренды MITAL. 👍</div>') +
    '</div>';

  document.getElementById('anaBody').innerHTML = h;
}
// ---------- Сопоставление названий и проблемные цены ----------
function anaOpenView(v) {
  anaView = v;
  nmEdit = null;
  document.getElementById('anaFilters').style.display = v === 'main' ? '' : 'none';
  document.getElementById('anaDaysBar').style.display = v === 'names' ? 'none' : '';
  if (v === 'names') { renderNames(); loadNames(); }
  else if (v === 'prices') { renderPriceProblems(); loadPriceProblems(); }
  else { if (ANA) renderAna(); loadAna(); }
  window.scrollTo(0, 0);
}
async function loadNames() {
  try {
    const res = await fetch('/api/admin/names?days=365');
    const data = await res.json();
    if (data && data.review) NAMES = data;
  } catch (e) {
    if (!NAMES) document.getElementById('anaBody').innerHTML = '<div class="msg err">Не удалось загрузить — проверь интернет.</div>';
    return;
  }
  if (anaView === 'names') renderNames();
}
function nmBack() { return `<button class="ana-btn" style="margin-bottom:10px" onclick="anaOpenView('main')"><i class="fa-solid fa-arrow-left"></i> Аналитика</button>`; }
function nmCats(cats) { return (cats || []).map(c => { const f = ANA_CATLIST.find(x => x.key === c); return f ? f.label : c; }).join(', '); }
function nmList() { return NAMES ? (NAMES[nmTab] || []) : []; }

function renderNames() {
  const box = document.getElementById('anaBody');
  if (!NAMES) { box.innerHTML = nmBack() + '<div class="hint-text">Загружаю…</div>'; return; }
  const N = NAMES;
  const sug = N.review.filter(g => g.sug);
  let h = nmBack();
  h += `<div class="ana-card"><h3><i class="fa-solid fa-spell-check" style="color:var(--blue)"></i> Сопоставление названий<small>за год</small></h3>
    <div class="ana-note">Точки вписывают названия по-разному («Митанол», «Mitonol 5-30»). Здесь ты один раз указываешь, что это за товар, — и аналитика всей сети, включая прошлое, сразу считается правильно. Данные самих точек не меняются.</div>
    <div class="ana-cmp">
      <div><b class="${N.unresolved_pct >= 5 ? 'ana-bad' : ''}">${N.unresolved_pct}%</b>продаж не распознано</div>
      <div><b>${fmtShort(N.unresolved_sum)}</b>сумма нераспознанных</div>
      <div><b>${N.review.length}</b>названий проверить</div>
      <div><b>${N.auto.length}</b>исправлено автоматически</div>
    </div></div>`;
  h += `<div class="ana-chips">
    <button class="${nmTab === 'review' ? 'on' : ''}" onclick="nmTab='review'; nmEdit=null; renderNames()">Проверить (${N.review.length})</button>
    <button class="${nmTab === 'auto' ? 'on' : ''}" onclick="nmTab='auto'; nmEdit=null; renderNames()">Исправлено авто (${N.auto.length})</button>
    <button class="${nmTab === 'mapped' ? 'on' : ''}" onclick="nmTab='mapped'; nmEdit=null; renderNames()">Подтверждено (${N.mapped.length})</button>
  </div>`;
  h += `<datalist id="nmBrands">${(N.brands || []).map(b => `<option value="${escapeHtml(b)}">`).join('')}</datalist>`;
  const list = nmList();
  if (nmTab === 'review' && sug.length > 1) {
    h += `<button class="ana-btn" style="margin-bottom:10px" onclick="nmAcceptAll()"><i class="fa-solid fa-check-double"></i> Принять все подсказки (${sug.length})</button>`;
  }
  if (nmTab === 'auto' && list.length > 1) {
    h += `<button class="ana-btn" style="margin-bottom:10px" onclick="nmConfirmAuto()"><i class="fa-solid fa-check-double"></i> Всё верно — подтвердить все (${list.length})</button>`;
  }
  if (nmTab === 'mapped') {
    h += `<input placeholder="🔍 Поиск" value="${escapeHtml(nmSearch)}" oninput="nmSearch=this.value; renderNamesList()" style="margin-bottom:10px">`;
  }
  h += '<div id="nmList"></div>';
  box.innerHTML = h;
  renderNamesList();
}

function renderNamesList() {
  const el = document.getElementById('nmList');
  if (!el) return;
  let list = nmList().map((g, i) => [g, i]);
  if (nmTab === 'mapped' && nmSearch.trim()) {
    const q = nmSearch.trim().toUpperCase();
    list = list.filter(([g]) => (g.raw + ' ' + (g.brand || '') + ' ' + (g.product || '')).toUpperCase().includes(q));
  }
  if (!list.length) {
    el.innerHTML = `<div class="ana-card"><div class="hint-text" style="padding:14px">${nmTab === 'review' ? 'Всё распознано — проверять нечего 👍' : 'Пусто.'}</div></div>`;
    return;
  }
  el.innerHTML = list.slice(0, 150).map(([g, i]) => nmCard(g, i)).join('') +
    (list.length > 150 ? `<div class="hint-text">Показаны первые 150 из ${list.length}.</div>` : '');
}

function nmCard(g, i) {
  const spell = (g.spellings && g.spellings.length) ? g.spellings : [g.raw];
  const meta = g.lines ? `${g.shops} точ. · ${g.lines} продаж · ${fmtShort(g.sum)} сум${g.cats.length ? ' · ' + escapeHtml(nmCats(g.cats)) : ''}` : 'в продажах за год не встречалось';
  let body = `<div class="nm-spell">${escapeHtml(spell[0])}${spell.length > 1 ? `<small>также: ${spell.slice(1).map(escapeHtml).join(' · ')}</small>` : ''}</div>
    <div class="ar-sub">${meta}</div>`;
  if (nmEdit === nmTab + i) {
    const b0 = g.sug ? g.sug.brand : (g.brand || '');
    const p0 = g.sug ? g.sug.product : (g.product || g.raw);
    body += `<div class="nm-form">
      <label>Бренд</label><input id="nmB" list="nmBrands" value="${escapeHtml(b0)}" placeholder="например, MITANOL" autocapitalize="characters">
      <label>Товар (как показывать в аналитике)</label><input id="nmP" value="${escapeHtml(p0)}" placeholder="например, MITANOL 5W-30 SL">
      <div class="nm-act"><button class="ok" onclick="nmSaveEdit('${nmTab}', ${i})">Сохранить</button>
        <button onclick="nmEdit=null; renderNamesList()">Отмена</button></div></div>`;
  } else if (nmTab === 'review') {
    if (g.sug) {
      body += `<div class="nm-sug">Похоже на: <b>${escapeHtml(g.sug.product)}</b>${(NAMES.mital_brands || []).includes(g.sug.brand) ? '<span class="mital-tag">MITAL</span>' : ''}</div>
        <div class="nm-act"><button class="ok" onclick="nmAccept(${i})">✓ Да, это оно</button>
          <button onclick="nmEdit='review${i}'; renderNamesList()">✏️ Другое</button>
          <button onclick="nmNoBrand('review', ${i})">Не бренд</button></div>`;
    } else {
      body += `<div class="nm-sug ana-mute">Бренд не найден в словаре</div>
        <div class="nm-act"><button class="ok" onclick="nmNewBrand(${i})">✓ Новый бренд «${escapeHtml(g.brand || '')}»</button>
          <button onclick="nmEdit='review${i}'; renderNamesList()">✏️ Указать бренд</button>
          <button onclick="nmNoBrand('review', ${i})">Не бренд</button></div>`;
    }
  } else if (nmTab === 'auto') {
    body += `<div class="nm-sug">Исправлено на: <b>${escapeHtml(g.product)}</b> <span class="ana-mute">(${Math.round((g.conf || 0) * 100)}%)</span></div>
      <div class="nm-act"><button class="ok" onclick="nmConfirmOne(${i})">✓ Верно</button>
        <button onclick="nmEdit='auto${i}'; renderNamesList()">✏️ Исправить</button></div>`;
  } else {
    body += `<div class="nm-sug">${g.alias_status === 'nobrand' ? '<b>Не бренд</b>' : `→ <b>${escapeHtml(g.product || g.brand)}</b> · бренд ${escapeHtml(g.brand || '')}`}</div>
      <div class="nm-act"><button onclick="nmEdit='mapped${i}'; renderNamesList()">✏️ Изменить</button>
        <button class="no" onclick="nmUndo(${i})">Отменить</button></div>`;
  }
  return `<div class="ana-card nm-card">${body}</div>`;
}

async function nmPost(items) {
  try {
    const res = await fetch('/api/admin/names', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items }) });
    const data = await res.json();
    if (!data.ok) { showMsg(data.error || 'Не удалось сохранить.', false); return false; }
    ANA = null;  // аналитика пересчитается при возврате
    nmEdit = null;
    await loadNames();
    return true;
  } catch (e) {
    showMsg('Не удалось сохранить — проверь интернет.', false);
    return false;
  }
}
function nmAccept(i) {
  const g = NAMES.review[i];
  if (g && g.sug) nmPost([{ raw: g.raw, brand: g.sug.brand, product: g.sug.product }]);
}
function nmNewBrand(i) {
  const g = NAMES.review[i];
  if (g && g.brand) nmPost([{ raw: g.raw, brand: g.brand, product: g.product }]);
}
function nmNoBrand(tab, i) {
  const g = NAMES[tab][i];
  if (g) nmPost([{ raw: g.raw, status: 'nobrand', product: g.raw }]);
}
function nmSaveEdit(tab, i) {
  const g = NAMES[tab][i];
  const brand = document.getElementById('nmB').value.trim();
  const product = document.getElementById('nmP').value.trim();
  if (!brand) { showMsg('Впиши бренд.', false); return; }
  nmPost([{ raw: g.raw, brand, product: product || brand }]);
}
function nmConfirmOne(i) {
  const g = NAMES.auto[i];
  if (g) nmPost([{ raw: g.raw, brand: g.brand, product: g.product }]);
}
function nmAcceptAll() {
  const items = NAMES.review.filter(g => g.sug).map(g => ({ raw: g.raw, brand: g.sug.brand, product: g.sug.product }));
  if (!items.length) return;
  if (!confirm(`Принять все подсказки (${items.length})? Сначала пролистай список — если какая-то подсказка неверная, исправь её отдельно.`)) return;
  nmPost(items);
}
function nmConfirmAuto() {
  const items = NAMES.auto.map(g => ({ raw: g.raw, brand: g.brand, product: g.product }));
  if (!items.length || !confirm(`Подтвердить все автоисправления (${items.length})?`)) return;
  nmPost(items);
}
async function nmUndo(i) {
  const g = NAMES.mapped[i];
  if (!g || !confirm(`Отменить сопоставление «${g.raw}»? Название снова будет распознаваться автоматически.`)) return;
  try {
    await fetch('/api/admin/names/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ raw: g.raw }) });
    ANA = null;
    await loadNames();
  } catch (e) {
    showMsg('Не удалось — проверь интернет.', false);
  }
}

async function loadPriceProblems() {
  try {
    const res = await fetch(`/api/admin/price_problems?days=${anaDays}`);
    const data = await res.json();
    if (Array.isArray(data)) PRICEPROB = data;
  } catch (e) {
    if (!PRICEPROB) document.getElementById('anaBody').innerHTML = '<div class="msg err">Не удалось загрузить — проверь интернет.</div>';
    return;
  }
  if (!ANA) await loadAna();
  if (anaView === 'prices') renderPriceProblems();
}
function renderPriceProblems() {
  const box = document.getElementById('anaBody');
  if (!PRICEPROB || !ANA) { box.innerHTML = nmBack() + '<div class="hint-text">Загружаю…</div>'; return; }
  const per = anaDays === 365 ? 'год' : anaDays === 90 ? '3 месяца' : '30 дней';
  const shops = [...new Set(PRICEPROB.map(x => x.s))];
  const list = PRICEPROB.filter(x => !ppShop || x.s === ppShop);
  let h = nmBack();
  h += `<div class="ana-card"><h3><i class="fa-solid fa-triangle-exclamation" style="color:#DC2626"></i> Проблемные цены<small>${per}</small></h3>
    <div class="ana-note">Цена продажи или закупки сильно отличается от обычной цены этого товара по сети (в 2 раза и больше), или закупка дороже продажи — чаще всего это цена за коробку/канистру вместо литра или штуки. Такие позиции не входят в средние цены и наценку. Исправить может только сама точка — в «Базе» или на складе (✏️).</div>
    <div style="padding:10px 14px"><select style="width:100%;border:1px solid var(--border);border-radius:10px;padding:9px 10px;font-size:13px;font-family:inherit;background:#fff" onchange="ppShop=Number(this.value)||0; renderPriceProblems()">
      <option value="0">Все точки (${PRICEPROB.length})</option>
      ${shops.map(id => `<option value="${id}"${id === ppShop ? ' selected' : ''}>${escapeHtml(anaPointName(anaPoint(id)))} (${PRICEPROB.filter(x => x.s === id).length})</option>`).join('')}
    </select></div></div>`;
  if (!list.length) {
    h += '<div class="ana-card"><div class="hint-text" style="padding:14px">Подозрительных цен нет 👍</div></div>';
  } else {
    h += '<div class="ana-card">' + list.map(x => {
      const unit = anaUnit(x.c);
      const p = anaPoint(x.s);
      const what = x.kind === 'sale'
        ? `Продажа <b class="ana-bad">${anaMoney(x.unit)}</b> за ${unit}${x.med_sale ? ` — обычно ${anaMoney(x.med_sale)}` : ''}`
        : `Закупка <b class="ana-bad">${anaMoney(x.cost)}</b> за ${unit}${x.med_cost ? ` — обычно ${anaMoney(x.med_cost)}` : ` при продаже ${anaMoney(x.unit)}`}`;
      return `<div class="ana-row"><div class="ar-main">
        <div class="ar-name" style="white-space:normal">${escapeHtml(anaPointName(p))} · <span style="font-weight:600">${escapeHtml(x.label || x.product)}</span></div>
        <div class="ar-sub">${fmtDay(x.date)} · ${anaQty(x.qty, unit)} за ${anaMoney(x.total)} сум</div>
        <div style="font-size:12.5px;margin-top:3px">${what}</div>
      </div>${x.dev ? `<div class="ar-val ana-bad">×${x.dev >= 1 ? String(Math.round(x.dev * 10) / 10).replace('.', ',') : String(Math.round(1 / x.dev * 10) / 10).replace('.', ',') + '↓'}</div>` : ''}</div>`;
    }).join('') + '</div>';
  }
  box.innerHTML = h;
}
// ---------- Копия статистики брендов и склада одной точки ----------
let SNAP = null, snapId = 0, snapDays = 30, snapWh = 'oil', snapSeq = 0;
const SNAP_UNIT = { l: 'л', pc: 'шт', '': '' };

function openSnapshot(id) {
  snapId = id;
  SNAP = null;
  snapWh = 'oil';
  if (MAP) MAP.closePopup();
  const p = (MAPDATA && MAPDATA.points.find(x => x.id === id)) || (ANA && anaPoint(id));
  document.getElementById('snapName').textContent = p ? (p.shop_name || p.username) : '…';
  document.getElementById('snapSub').textContent = '';
  document.getElementById('snapOv').style.display = 'block';
  document.body.style.overflow = 'hidden';
  renderSnapshot();
  loadSnapshot();
}
function closeSnapshot() {
  document.getElementById('snapOv').style.display = 'none';
  document.body.style.overflow = '';
  snapSeq++;
}
document.addEventListener('keydown', e => { if (e.key === 'Escape' && document.getElementById('snapOv').style.display === 'block') closeSnapshot(); });

async function loadSnapshot() {
  const seq = ++snapSeq;
  try {
    const res = await fetch(`/api/admin/shops/${snapId}/snapshot?days=${snapDays}`);
    const data = await res.json();
    if (seq !== snapSeq) return;
    if (!data || !data.shop) {
      document.getElementById('snapBody').innerHTML = `<div class="msg err">${escapeHtml((data && data.error) || 'Не удалось загрузить.')}</div>`;
      return;
    }
    SNAP = data;
  } catch (e) {
    if (seq === snapSeq) document.getElementById('snapBody').innerHTML = '<div class="msg err">Не удалось загрузить — проверь интернет.</div>';
    return;
  }
  renderSnapshot();
}
function setSnapDays(d) { snapDays = d; renderSnapshot(); loadSnapshot(); }
function setSnapWh(w) { snapWh = w; renderSnapshot(); }

function renderSnapshot() {
  const body = document.getElementById('snapBody');
  const seg = `<div class="map-seg" style="margin-bottom:10px">
    ${[[30, '30 дней'], [90, '3 месяца'], [365, 'Год']].map(([d, l]) => `<button class="${d === snapDays ? 'on' : ''}" onclick="setSnapDays(${d})">${l}</button>`).join('')}
  </div>`;
  if (!SNAP) { body.innerHTML = seg + '<div class="hint-text">Загружаю…</div>'; return; }
  const S = SNAP;
  document.getElementById('snapName').textContent = S.shop.name;
  document.getElementById('snapSub').textContent = (S.shop.role === 'branch' ? 'Филиал' + (S.shop.parent_name ? ' · ' + S.shop.parent_name : '') : 'Точка') +
    (S.shop.address ? ' · ' + S.shop.address : '');
  const rv = S.revenue || {};
  let h = seg;
  h += `<div class="map-kpis">
    <div class="map-kpi"><b>${fmtShort(rv.total || 0)}</b><span>выручка</span></div>
    <div class="map-kpi"><b>${rv.count || 0}</b><span>замен и услуг</span></div>
    <div class="map-kpi"><b>${fmtShort(rv.avg || 0)}</b><span>средний чек</span></div>
    <div class="map-kpi"><b>${(rv.clients && rv.clients.total) || 0}</b><span>клиентов</span></div>
  </div>`;

  // --- бренды: копия экрана точки ---
  h += '<div class="snap-sec"><i class="fa-solid fa-oil-can" style="color:#EAB308"></i> Бренды: что продаётся</div>';
  if (!S.brands.length) {
    h += '<div class="ana-card"><div class="hint-text" style="padding:14px">За этот период продаж с указанием масла и фильтров нет.</div></div>';
  }
  S.brands.forEach(c => {
    const unit = SNAP_UNIT[c.unit] !== undefined ? SNAP_UNIT[c.unit] : '';
    const bySum = c.metric === 'sum';
    h += `<div class="ana-card"><h3>${escapeHtml(c.label)}<small>${bySum ? fmtShort(c.total_sum) + ' сум' : anaQty(c.total_qty, unit) + ' · ' + fmtShort(c.total_sum) + ' сум'}</small></h3>` +
      c.top.map(b => `<div class="ana-row"><div class="ar-main">
          <div class="ar-name">${b.no_brand ? '<span class="ana-mute">без марки</span>' : escapeHtml(b.name)}</div>
          <div class="ar-bar"><i style="width:${Math.max(2, Math.min(100, b.share))}%"></i></div>
        </div><div class="ar-val">${bySum ? fmtShort(b.sum) : anaQty(b.qty, unit)}<small>${b.share}% · ${b.visits} раз${bySum ? '' : ' · ' + fmtShort(b.sum)}</small></div></div>`).join('') +
      (c.others ? `<div class="ana-row"><div class="ar-main"><div class="ar-name ana-mute">Остальные (${c.others.count})</div></div>
        <div class="ar-val">${bySum ? fmtShort(c.others.sum) : anaQty(c.others.qty, unit)}<small>${c.others.share}%</small></div></div>` : '') +
      '</div>';
  });

  // --- склад: копия склада точки ---
  const all = S.warehouse.products || [];
  h += '<div class="snap-sec"><i class="fa-solid fa-warehouse" style="color:var(--blue)"></i> Склад</div>';
  if (!all.length) {
    h += `<div class="ana-card"><div class="hint-text" style="padding:14px">${S.shop.warehouse_enabled ? 'На складе точки пока нет товаров.' : 'Склад у этой точки выключен — товары не ведутся.'}</div></div>`;
    body.innerHTML = h + snapSuppliersHtml(S);
    return;
  }
  const isOil = p => String(p.category).indexOf('fluid_') === 0;
  const isFil = p => String(p.category).indexOf('filter_') === 0;
  const prods = all.filter(p => snapWh === 'all' || (snapWh === 'oil' && isOil(p)) || (snapWh === 'filter' && isFil(p)) || (snapWh === 'other' && !isOil(p) && !isFil(p)));
  h += `<div class="ana-chips">
    <button class="${snapWh === 'oil' ? 'on' : ''}" onclick="setSnapWh('oil')">Масла (${all.filter(isOil).length})</button>
    <button class="${snapWh === 'filter' ? 'on' : ''}" onclick="setSnapWh('filter')">Фильтры (${all.filter(isFil).length})</button>
    <button class="${snapWh === 'other' ? 'on' : ''}" onclick="setSnapWh('other')">Прочее (${all.filter(p => !isOil(p) && !isFil(p)).length})</button>
    <button class="${snapWh === 'all' ? 'on' : ''}" onclick="setSnapWh('all')">Всё (${all.length})</button>
  </div>`;
  let buyV = 0, sellV = 0, noBuy = 0;
  prods.forEach(p => {
    const st = Math.max(0, Number(p.stock) || 0);
    if (p.buy !== null && p.buy !== undefined) buyV += st * p.buy; else noBuy++;
    if (p.sell) sellV += st * p.sell;
  });
  h += `<div class="ana-cmp" style="padding:0 0 10px">
    <div><b>${fmtShort(buyV)}</b>остаток по закупке</div>
    <div><b>${fmtShort(sellV)}</b>если продать всё</div>
    <div><b>${fmtShort(sellV - buyV)}</b>возможная наценка</div>
    <div><b class="${noBuy ? 'ana-bad' : ''}">${noBuy}</b>без цены закупки</div>
  </div>`;
  const sorted = prods.slice().sort((a, b) => String(a.category).localeCompare(String(b.category)) || String(a.name).localeCompare(String(b.name)));
  h += '<div class="ana-card">' + (sorted.length ? sorted.map(p => {
    const unit = SNAP_UNIT[p.unit] !== undefined ? SNAP_UNIT[p.unit] : p.unit;
    const stCls = p.status === 'out' ? 'ana-bad' : p.status === 'low' ? 'ana-bad' : '';
    const m = p.margin_pct;
    const mHtml = m === null || m === undefined ? '<span class="sw-m none">наценка —</span>'
      : `<span class="sw-m ${m < 10 ? 'low' : ''}">+${m}%</span>`;
    return `<div class="snap-wh-row"><div class="sw-main">
        <div class="sw-name">${escapeHtml(p.name)}</div>
        <div class="sw-sub">${escapeHtml(p.category_label)} · <span class="${stCls}">остаток ${anaQty(Number(p.stock) || 0, unit)}</span>${p.sold_30d ? ` · продано за 30 дн ${anaQty(p.sold_30d, unit)}` : ''}</div>
      </div><div class="sw-price">${p.buy !== null && p.buy !== undefined ? anaMoney(p.buy) : '<span class="ana-bad">—</span>'} → ${p.sell ? anaMoney(p.sell) : '—'}
        <small>закупка → продажа, за ${unit}</small>${mHtml}</div></div>`;
  }).join('') : '<div class="hint-text" style="padding:14px">В этой группе товаров нет.</div>') + '</div>';
  body.innerHTML = h + snapSuppliersHtml(S);
}
function snapSuppliersHtml(S) {
  const SP = S.suppliers || { list: [] };
  const per = snapDays === 365 ? 'год' : snapDays === 90 ? '3 мес' : '30 дн';
  let h = '<div class="snap-sec"><i class="fa-solid fa-truck-field" style="color:#16A34A"></i> Поставщики</div>';
  if (!SP.list.length) {
    return h + `<div class="ana-card"><div class="hint-text" style="padding:14px">Точка не ведёт поставщиков в OilBook.${SP.no_supplier_products ? ` Товаров на складе без поставщика: ${SP.no_supplier_products}.` : ''}</div></div>`;
  }
  h += `<div class="ana-cmp" style="padding:0 0 10px">
    <div><b>${fmtShort(SP.owe)}</b>долг поставщикам</div>
    <div><b class="${SP.overdue ? 'ana-bad' : ''}">${fmtShort(SP.overdue)}</b>просрочено</div>
    <div><b>${fmtShort(SP.bought_period)}</b>взято товара · ${per}</div>
    <div><b>${SP.list.length}</b>поставщиков${SP.no_supplier_products ? ` · ${SP.no_supplier_products} товар. без поставщика` : ''}</div>
  </div>`;
  SP.list.forEach(s => {
    const bal = s.balance > 0
      ? `<span class="${s.overdue ? 'ana-bad' : ''}">${fmtShort(s.balance)}</span><small>${s.overdue ? 'просрочено ' + fmtShort(s.overdue) : 'долг'}</small>`
      : s.balance < 0 ? `<span class="ana-good">${fmtShort(-s.balance)}</span><small>переплата</small>` : `<span class="ana-mute">0</span><small>долга нет</small>`;
    const terms = [s.pay_days !== null && s.pay_days !== undefined ? `оплата через ${s.pay_days} дн` : '', s.delivery_days ? 'привоз: ' + escapeHtml(s.delivery_days) : '']
      .filter(Boolean).join(' · ');
    const contacts = [
      s.contact ? `<span><i class="fa-solid fa-user"></i> ${escapeHtml(s.contact)}</span>` : '',
      s.phone ? `<a href="tel:${escapeHtml(s.phone)}"><i class="fa-solid fa-phone"></i> ${escapeHtml(s.phone)}</a>` : '',
      s.telegram ? `<a target="_blank" rel="noopener" href="https://t.me/${encodeURIComponent(s.telegram)}"><i class="fa-brands fa-telegram"></i> @${escapeHtml(s.telegram)}</a>` : ''
    ].filter(Boolean).join('');
    const prices = (s.prices || []).map(p => {
      const unit = SNAP_UNIT[p.unit] !== undefined ? SNAP_UNIT[p.unit] : p.unit;
      const ch = p.change_pct === null || p.change_pct === undefined ? ''
        : `<small class="${p.change_pct > 0 ? 'ana-bad' : 'ana-good'}">${p.change_pct > 0 ? '▲' : '▼'} ${Math.abs(p.change_pct)}%</small>`;
      return `<div class="ana-row"><div class="ar-main"><div class="ar-name">${escapeHtml(p.name)}</div>
        <div class="ar-sub">последняя закупка ${fmtDay(p.last_date)} · закупок: ${p.times}</div></div>
        <div class="ar-val">${anaMoney(p.last)} <span style="font-size:11px;color:#64748B">/${unit}</span>${ch}</div></div>`;
    }).join('');
    const noHist = (s.products || []).filter(n => !(s.prices || []).some(p => p.name === n));
    h += `<details class="ana-card sup-card"><summary>
        <div class="ar-main"><div class="ar-name">${escapeHtml(s.name)}</div><div class="ar-sub">${terms || 'условия не указаны'}</div></div>
        <div class="ar-val">${bal}</div><i class="fa-solid fa-chevron-down sup-chev"></i>
      </summary>
      ${contacts ? `<div class="sup-contacts">${contacts}</div>` : ''}
      <div class="ana-cmp">
        <div><b>${fmtShort(s.bought_period)}</b>взято · ${per}</div>
        <div><b>${fmtShort(s.paid_period)}</b>оплачено · ${per}</div>
        <div><b>${fmtShort(s.bought_all)}</b>взято за всё время · ${s.order_count} заказ.</div>
        <div><b>${fmtShort(s.paid_all)}</b>оплачено за всё время</div>
      </div>
      <div class="ana-note">Последний заказ: ${fmtDay(s.last_order)} · последняя оплата: ${fmtDay(s.last_payment)}${s.next_due ? ` · следующий платёж до ${fmtDay(s.next_due.date)} — ${fmtShort(s.next_due.amount)}` : ''}${s.oldest_overdue ? ` · <span class="ana-bad">просрочка с ${fmtDay(s.oldest_overdue)}</span>` : ''}</div>
      ${prices ? '<div class="sup-h">Цены закупки у этого поставщика</div>' + prices : ''}
      ${noHist.length ? `<div class="sup-h">Товары поставщика без принятых заказов</div><div class="ana-brands" style="padding:0 14px 12px">${noHist.map(n => `<span>${escapeHtml(n)}</span>`).join('')}</div>` : ''}
      ${s.note ? `<div class="ana-note">📝 ${escapeHtml(s.note)}</div>` : ''}
    </details>`;
  });
  return h;
}
if (location.hash.indexOf('#income') === 0) { const m = location.hash.split('-')[1]; if (m && ['shops', 'pays', 'set'].indexOf(m) >= 0) IX.tab = m; admTab('income'); }
if (location.hash === '#analytics') admTab('analytics');
if (location.hash === '#map') admTab('map');
</script>
</body>
</html>
"""
