/* =========================================================
   OilBook taʼlimi — Dala effekti: uchburchaklardan yulduz turkumi
   DalaFX.attach(el, {brain:true}) — el ichiga canvas qo'yadi:
   o'ng tomonda «miya» bulut + fon bo'ylab suzuvchi zarrachalar.
   Ko'rinmasa yoki tab yashirin bo'lsa — to'xtaydi.
   ========================================================= */
(function () {
  "use strict";
  var RM = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var DPR = Math.min(window.devicePixelRatio || 1, 2);
  var PAL = ["#8052ff", "#a98bff", "#ffb829", "#ffd36b", "#2fd3b5", "#ff4fd8", "#4f8bff", "#ff7a59"];

  function rnd(seed) { return function () { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; }; }

  function build(brain, W, H, seed, opt) {
    var r = rnd(seed || 7), out = [], i;
    var narrow = W < 640;
    // telefonda «miya» sarlavha ustiga tushadi — faqat suzuvchi zarrachalar
    if (brain && W >= 600) {
      // «miya»: ikki yarim shardan iborat bulut, o'ng tomonda
      var cx = W * (opt.cx || (narrow ? 0.74 : 0.76)), cy = H * 0.5;
      var R = Math.min(W * (opt.r || (narrow ? 0.3 : 0.2)), H * 0.42);
      var N = narrow ? 170 : 340;
      for (i = 0; i < N; i++) {
        var a = r() * Math.PI * 2, d = Math.sqrt(r());
        var lobe = i % 2 ? 1 : -1;
        var x = Math.cos(a) * d * R * 0.62 + lobe * R * 0.42;
        var y = Math.sin(a) * d * R * 0.78 - Math.abs(Math.cos(a)) * R * 0.06;
        out.push({ bx: cx + x, by: cy + y, s: 2 + r() * 3.2, rot: r() * 6.28, vr: (r() - 0.5) * 0.01,
          c: PAL[(r() * PAL.length) | 0], o: 0.45 + r() * 0.5, ph: r() * 6.28, amp: 1 + r() * 3 });
      }
    }
    var M = narrow ? 26 : 60;
    for (i = 0; i < M; i++) {
      out.push({ bx: r() * W, by: r() * H, s: 1.5 + r() * 2.5, rot: r() * 6.28, vr: (r() - 0.5) * 0.006,
        c: PAL[(r() * PAL.length) | 0], o: 0.18 + r() * 0.3, ph: r() * 6.28, amp: 6 + r() * 14, drift: true });
    }
    return out;
  }

  function tri(ctx, x, y, s, rot) {
    ctx.moveTo(x + Math.cos(rot) * s, y + Math.sin(rot) * s);
    ctx.lineTo(x + Math.cos(rot + 2.094) * s, y + Math.sin(rot + 2.094) * s);
    ctx.lineTo(x + Math.cos(rot + 4.189) * s, y + Math.sin(rot + 4.189) * s);
    ctx.closePath();
  }

  function attach(box, opt) {
    if (!box) return;
    for (var c = box.firstElementChild; c; c = c.nextElementSibling) if (c.classList.contains("dala-fx")) return;
    opt = opt || {};
    if (getComputedStyle(box).position === "static") box.style.position = "relative";
    var cv = document.createElement("canvas");
    cv.className = "dala-fx"; cv.setAttribute("aria-hidden", "true");
    cv.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:0;display:block";
    box.insertBefore(cv, box.firstChild);
    var ctx = cv.getContext("2d"), W = 0, H = 0, P = [], raf = 0, visible = true, t0 = performance.now();
    var mx = -1e4, my = -1e4;

    function size() {
      var r = box.getBoundingClientRect();
      if (!r.width || !r.height) return;
      W = r.width; H = r.height;
      cv.width = Math.round(W * DPR); cv.height = Math.round(H * DPR);
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      P = build(opt.brain !== false, W, H, opt.seed, opt);
      draw(performance.now());
    }
    function draw(now) {
      var t = (now - t0) / 1000, intro = RM ? 1 : Math.min(1, t / 1.6), e = 1 - Math.pow(1 - intro, 3);
      ctx.clearRect(0, 0, W, H);
      ctx.lineWidth = 1.1;
      for (var i = 0; i < P.length; i++) {
        var p = P[i], x, y;
        if (p.drift) {
          x = p.bx + Math.sin(t * 0.15 + p.ph) * p.amp;
          y = ((p.by - t * 4 * (0.3 + p.o)) % H + H) % H;
        } else {
          x = p.bx + Math.cos(t * 0.3 + p.ph) * p.amp;
          y = p.by + Math.sin(t * 0.5 + p.ph) * p.amp;
          // yig'ilish: bulut atrofdan yig'ilib keladi
          x = x + (1 - e) * Math.cos(p.ph) * 140;
          y = y + (1 - e) * Math.sin(p.ph) * 90;
          var dx = x - mx, dy = y - my, dd = dx * dx + dy * dy;
          if (dd < 6400) { var dl = Math.sqrt(dd) || 1, k = (1 - dl / 80) * 14; x += dx / dl * k; y += dy / dl * k; }
        }
        var tw = 0.75 + 0.25 * Math.sin(t * 1.4 + p.ph * 3);
        ctx.globalAlpha = p.o * tw * (p.drift ? 1 : e);
        ctx.strokeStyle = p.c;
        ctx.beginPath(); tri(ctx, x, y, p.s, p.rot + t * p.vr * 60); ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }
    function frame(now) {
      raf = 0;
      if (!cv.isConnected) { io.disconnect(); return; }
      draw(now);
      if (visible && !RM && !document.hidden) raf = requestAnimationFrame(frame);
    }
    function wake() { if (visible && !raf && !document.hidden && !RM) raf = requestAnimationFrame(frame); }
    var io = new IntersectionObserver(function (en) { visible = en[0].isIntersecting; wake(); });
    io.observe(cv);
    document.addEventListener("visibilitychange", wake);
    if (window.ResizeObserver) new ResizeObserver(size).observe(box); else window.addEventListener("resize", size);
    box.addEventListener("pointermove", function (ev) { var r = cv.getBoundingClientRect(); mx = ev.clientX - r.left; my = ev.clientY - r.top; }, { passive: true });
    box.addEventListener("pointerleave", function () { mx = my = -1e4; });
    size();
    wake();
  }

  window.DalaFX = { attach: attach };

  function auto() {
    var les = document.querySelector("body.ob-les .hero");
    if (les) attach(les, { brain: true, seed: 11 });
    var main = document.getElementById("main");
    if (document.body.classList.contains("ob-ev") && main) {
      var hook = function () { var h = main.querySelector(".hero"); if (h) attach(h, { brain: false, seed: 5 }); };
      new MutationObserver(hook).observe(main, { childList: true });
      hook();
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", auto); else auto();
})();
