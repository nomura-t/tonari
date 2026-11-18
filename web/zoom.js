// となり — 図を大きく見る（v0.7）。答えの列の幅に合わせて縮んだ図（関係の図・構成の図・しくみの絵）を、別の窓に写して、
// 寄る・引く・動かすができるようにする。写した図は元の図と同じ部品なので、構成の図の「指すと光る」もそのまま動く。
// 寄り引きは svg の viewBox を動かす（字は線のまま大きくなる）。操作は全体の地図と同じ:
//   つかんで動かす・2本指で送る／つまむか、⌘（Ctrl）を押しながら回すと寄る・引く／+ - 0 と矢印のキー
(function () {
  const $ = (s) => document.querySelector(s);
  let Z = null, hooks = {};

  function open(fig) {
    const dlg = $("#figZoom"), body = $("#fzBody");
    if (!fig || !dlg || dlg.open) return;
    const src = [...fig.querySelectorAll(".v-body svg")].find((s) => s.getBoundingClientRect().width > 0) || fig.querySelector(".v-body svg");
    if (!src) return;
    const holder = document.createElement("div");
    holder.className = fig.className + " fz-fig";
    holder.dataset.type = fig.dataset.type || "";
    const inner = fig.querySelector(".v-body").cloneNode(true);
    holder.appendChild(inner);
    body.replaceChildren(holder);
    // 写した中の、同じ場所の svg を主にする（しくみの絵は横と縦の2枚があるので、見えていたほうだけ残す）
    const all = [...fig.querySelectorAll(".v-body svg")], idx = all.indexOf(src);
    const svgs = [...inner.querySelectorAll("svg")];
    const svg = svgs[idx];
    svgs.forEach((s, i) => { if (i !== idx && s.parentElement === svg.parentElement) s.remove(); });
    const vb = (svg.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
    const base = vb.length === 4 && vb.every(Number.isFinite) ? vb : [0, 0, src.getBoundingClientRect().width, src.getBoundingClientRect().height];
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    svg.style.cssText = "";
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.classList.add("fz-svg");
    svg.parentElement.classList.add("fz-stage");
    for (const k of ["pin", "deep", "akey"]) if (fig.dataset[k]) holder.dataset[k] = fig.dataset[k];
    $("#fzTitle").textContent = fig.querySelector(".v-name")?.textContent || "図";
    Z = { svg, base, k: 1, cx: base[0] + base[2] / 2, cy: base[1] + base[3] / 2, drag: null, moved: false };
    dlg.showModal();
    document.dispatchEvent(new CustomEvent("tonari:act", { detail: { what: "zoom" } }));
    apply();
    $("#fzClose").focus();
  }

  function apply() {
    if (!Z) return;
    const [bx, by, bw, bh] = Z.base, w = bw / Z.k, h = bh / Z.k;
    // 図の外へ行きすぎない（図の半分までは外へ出せる）
    Z.cx = Math.min(bx + bw + w / 4, Math.max(bx - w / 4, Z.cx));
    Z.cy = Math.min(by + bh + h / 4, Math.max(by - h / 4, Z.cy));
    Z.svg.setAttribute("viewBox", `${Z.cx - w / 2} ${Z.cy - h / 2} ${w} ${h}`);
    $("#fzNow").textContent = `${Math.round(Z.k * 100)}%`;
  }
  // 画面の1px が、図の座標でいくつか
  function unit() {
    const r = Z.svg.getBoundingClientRect();
    const [, , bw, bh] = Z.base;
    return Math.max(bw / Z.k / Math.max(1, r.width), bh / Z.k / Math.max(1, r.height));
  }
  function zoomBy(f, at) {
    if (!Z) return;
    const k = Math.min(8, Math.max(0.5, Z.k * f));
    if (at) {   // 指している点を動かさずに寄る
      const r = Z.svg.getBoundingClientRect(), u = unit();
      const px = Z.cx + (at.x - (r.left + r.width / 2)) * u, py = Z.cy + (at.y - (r.top + r.height / 2)) * u;
      Z.cx = px - (px - Z.cx) * (Z.k / k);
      Z.cy = py - (py - Z.cy) * (Z.k / k);
    }
    Z.k = k;
    apply();
  }
  function fit() {
    if (!Z) return;
    Z.k = 1;
    Z.cx = Z.base[0] + Z.base[2] / 2;
    Z.cy = Z.base[1] + Z.base[3] / 2;
    apply();
  }
  function close() {
    const dlg = $("#figZoom");
    if (dlg && dlg.open) dlg.close();
  }
  const isOpen = () => !!($("#figZoom") && $("#figZoom").open);

  function init(h) {
    hooks = h || {};
    const dlg = $("#figZoom");
    if (!dlg) return;
    dlg.addEventListener("close", () => {
      Z = null;
      $("#fzBody").replaceChildren();
      if (window.TonariArch) window.TonariArch.sync();   // 窓の中で留めた箱を、元の図にも映す
      if (hooks.onClose) hooks.onClose();
    });
    $("#fzClose").addEventListener("click", close);
    $("#fzFit").addEventListener("click", fit);
    $("#fzIn").addEventListener("click", () => zoomBy(1.25));
    $("#fzOut").addEventListener("click", () => zoomBy(0.8));
    const body = $("#fzBody");
    body.addEventListener("wheel", (e) => {
      if (!Z || !e.target.closest(".fz-stage")) return;
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) zoomBy(Math.exp(-e.deltaY * 0.01), { x: e.clientX, y: e.clientY });
      else { const u = unit(); Z.cx += e.deltaX * u; Z.cy += e.deltaY * u; apply(); }
    }, { passive: false });
    let g0 = 1;
    body.addEventListener("gesturestart", (e) => { if (Z) { e.preventDefault(); g0 = Z.k; } });
    body.addEventListener("gesturechange", (e) => { if (Z) { e.preventDefault(); zoomBy((g0 * e.scale) / Z.k, { x: e.clientX, y: e.clientY }); } });
    body.addEventListener("pointerdown", (e) => {
      if (!Z || e.button !== 0 || !e.target.closest(".fz-stage")) return;
      Z.drag = { x: e.clientX, y: e.clientY, cx: Z.cx, cy: Z.cy };
      Z.moved = false;
    });
    window.addEventListener("pointermove", (e) => {
      if (!Z || !Z.drag) return;
      const dx = e.clientX - Z.drag.x, dy = e.clientY - Z.drag.y;
      if (!Z.moved && Math.hypot(dx, dy) < 4) return;
      Z.moved = true;
      body.classList.add("fz-drag");
      const u = unit();
      Z.cx = Z.drag.cx - dx * u;
      Z.cy = Z.drag.cy - dy * u;
      apply();
    });
    window.addEventListener("pointerup", () => {
      if (!Z) return;
      Z.drag = null;
      body.classList.remove("fz-drag");
      // 動かした印は、この指を離した直後の押し（click）を止めるためだけの物。窓の外で離したときに残らないよう、すぐあとで消す
      setTimeout(() => { if (Z) Z.moved = false; }, 0);
    });
    // 動かしたあとに指を離したときの押しは、箱を押したことにしない
    body.addEventListener("click", (e) => { if (Z && Z.moved) { e.stopPropagation(); e.preventDefault(); Z.moved = false; } }, true);
    document.addEventListener("keydown", (e) => {
      if (!isOpen() || e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
      const step = () => unit() * 80;
      if (e.key === "+" || e.key === "=" || e.key === ";") zoomBy(1.25);
      else if (e.key === "-") zoomBy(0.8);
      else if (e.key === "0") fit();
      else if (e.key === "ArrowLeft") { Z.cx -= step(); apply(); }
      else if (e.key === "ArrowRight") { Z.cx += step(); apply(); }
      else if (e.key === "ArrowUp") { Z.cy -= step(); apply(); }
      else if (e.key === "ArrowDown") { Z.cy += step(); apply(); }
      else return;
      e.preventDefault();
    });
    document.addEventListener("click", (e) => {
      const b = e.target.closest ? e.target.closest("[data-zoom]") : null;
      if (b && (!hooks.canOpen || hooks.canOpen())) open(b.closest(".view"));
    });
  }

  window.TonariZoom = { init, open, close, isOpen, fit, zoomBy, state: () => Z };
})();
