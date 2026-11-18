// となり — 構成の図（v0.7・DESIGN 18章）。箱（モジュール・層・サービス・保存する所など）と、向きのある線（A が B を使う）。
// 段の割り振りと置き場所はサーバーが決める（server/arch.py。同じ塊なら同じ置き場所）。ここは描くことと、指したときの見え方だけ。
//   線は「使う側 → 使われる側」。上の段が使う側になるように並んでいるので、ふつうの線は下向き。
//   循環を閉じる線・下のまとまりから上のまとまりへ向かう線は、矢じりが上を向く（色と破線でも分ける）。
//   箱を指す（か焦点を置く）と、その箱が使うもの（下流）と、その箱を使うもの（上流）が、色を分けて光る。
//   箱を押すと留まり、「間接も含める」（たどれる先を全部）と「この箱の中を聞く」が出る。
// 機械が見つけるのは、この図に描かれた線の性質（循環・層の向き）だけで、線の中身が正しいかは確かめていない（図の下に書く）。
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const KIND = { person: "人", ui: "画面", service: "サービス", module: "モジュール", store: "保存する所", queue: "キュー", external: "外の仕組み" };
  // 種類の小さな印（14px の枠の中。線だけで描く）。形と、凡例の言葉の2つで見分ける
  const GLYPH = {
    person: '<circle cx="7" cy="4.2" r="2.6"/><path d="M2 13c0-3 2.2-4.6 5-4.6s5 1.6 5 4.6"/>',
    ui: '<rect x="1.5" y="2.5" width="11" height="9" rx="1.5"/><path d="M1.5 5.5h11"/>',
    service: '<path d="M7 1.5l4.8 2.75v5.5L7 12.5 2.2 9.75v-5.5z"/>',
    module: '<rect x="1.5" y="1.5" width="6.5" height="6.5" rx="1"/><rect x="6" y="6" width="6.5" height="6.5" rx="1"/>',
    store: '<ellipse cx="7" cy="3.6" rx="4.8" ry="2"/><path d="M2.2 3.6v6.8c0 1.1 2.1 2 4.8 2s4.8-.9 4.8-2V3.6"/>',
    queue: '<rect x="1.5" y="4" width="11" height="6" rx="1"/><path d="M5.2 4v6M8.8 4v6"/>',
    external: '<path d="M4 11.5h6.2a2.6 2.6 0 0 0 .5-5.15A3.6 3.6 0 0 0 3.8 5.4 3.05 3.05 0 0 0 4 11.5z"/>',
  };
  const FS = 13, TFS = 11, HEAD = 7;

  function path(pts) {
    // 最後の点は矢じりの分だけ手前で止める
    const p = pts.map((q) => [...q]);
    const n = p.length, dy = Math.sign(p[n - 1][1] - p[n - 2][1]) || 1;
    p[n - 1][1] -= dy * (HEAD - 1);
    let d = `M${p[0][0]} ${p[0][1]}`;
    for (let i = 1; i < n; i++) {
      const [x1, y1] = p[i - 1], [x2, y2] = p[i];
      d += Math.abs(x1 - x2) < 0.6 ? ` L${x2} ${y2}` : ` C${x1} ${(y1 + y2) / 2} ${x2} ${(y1 + y2) / 2} ${x2} ${y2}`;
    }
    return d;
  }
  function arrow(pts) {
    const [x, y] = pts[pts.length - 1], dy = Math.sign(y - pts[pts.length - 2][1]) || 1;
    return `${x},${y} ${x - 4.2},${y - dy * HEAD} ${x + 4.2},${y - dy * HEAD}`;
  }

  function render(v) {
    const lay = v.lay;
    if (!lay) return `<p class="ar-read">この図の置き場所を決められませんでした。</p>`;
    const name = Object.fromEntries(v.nodes.map((n) => [n.id, n.label]));
    const verb = v.arrow || "使う", pv = (v.particle || "を") + verb;   // 「使う」と「を使う」（助詞つき）
    const outs = Object.create(null), ins = Object.create(null);   // 箱の id が constructor などでも、継いだ物を引かない
    v.edges.forEach((e) => { (outs[e.from] ||= []).push(e.to); (ins[e.to] ||= []).push(e.from); });
    let bands = "", bandNames = "", edges = "", labels = "", nodes = "";
    (v.groups || []).forEach((g, i) => {
      const b = lay.bands[i];
      bands += `<g class="ar-band"><rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="12"/></g>`;
      bandNames += `<text class="ar-bl" x="${b.x + 12}" y="${b.y + 16}">${esc(g.label)}</text>`;   // 名前は線より手前に描く（線が上を通っても読める）
    });
    v.edges.forEach((e, k) => {
      const p = lay.edges[k], cls = `ar-edge${e.cyc ? " cyc" : ""}${e.up ? " up" : ""}`;
      const say = `${name[e.from]} は ${name[e.to]} ${pv}${e.label ? `（${e.label}）` : ""}`;
      edges += `<g class="${cls}" data-e="${k}" data-from="${esc(e.from)}" data-to="${esc(e.to)}" tabindex="0" role="button" aria-label="${esc(say)}">` +
        `<path class="ar-hit" d="${path(p.pts)}"/><path class="ar-line" d="${path(p.pts)}"/><polygon class="ar-arr" points="${arrow(p.pts)}"/><title>${esc(say)}</title></g>`;
      if (p.lab) labels += `<text class="ar-el" data-e="${k}" x="${p.lab[0]}" y="${p.lab[1] + 4}" text-anchor="middle">${esc(e.label)}</text>`;
    });
    for (const n of v.nodes) {
      const [x, y, w, h] = lay.nodes[n.id];
      const gl = n.kind && GLYPH[n.kind] ? `<g class="ar-gl" transform="translate(${x + 10} ${y + (n.tech ? 9 : h / 2 - 7)})">${GLYPH[n.kind]}</g>` : "";
      const tx = x + (gl ? 30 : w / 2), anchor = gl ? "start" : "middle";
      const about = [n.kind ? KIND[n.kind] : "", n.tech, n.note].filter(Boolean).join("・");
      nodes += `<g class="ar-node${n.kind ? " k-" + n.kind : ""}" data-id="${esc(n.id)}" data-out="${esc((outs[n.id] || []).join(" "))}" data-in="${esc((ins[n.id] || []).join(" "))}" ` +
        `data-lab="${esc(n.label)}" data-name="${esc(n.label)}" tabindex="0" role="button" aria-label="${esc(n.label)}${about ? "（" + esc(about) + "）" : ""}">` +
        `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="9"/>${gl}` +
        `<text class="ar-lab" x="${tx}" y="${y + (n.tech ? 16 : h / 2 + 4.5)}" text-anchor="${anchor}">${esc(n.label)}</text>` +
        (n.tech ? `<text class="ar-tech" x="${tx}" y="${y + 31}" text-anchor="${anchor}">${esc(n.tech)}</text>` : "") +
        `<title>${esc(n.label)}${about ? "：" + esc(about) : ""}</title></g>`;
    }
    const svg = `<svg class="ar-svg" viewBox="0 0 ${lay.w} ${lay.h}" width="${lay.w}" height="${lay.h}" role="img" aria-label="${esc(v.name)}">${bands}${edges}${bandNames}${labels}${nodes}</svg>`;
    // 機械が見つけた、この図の線の性質
    const flags = [];
    for (const c of v.cycles || []) flags.push(`<p class="ar-flag f-cyc"><i class="ar-smp" aria-hidden="true"></i><b>循環</b>この図の上では、${c.map((x) => `「${esc(x)}」`).join("・")} が、線をたどると自分に戻ります（互いに${esc(verb)}形）。</p>`);
    const ups = v.edges.filter((e) => e.up);
    if (ups.length) flags.push(`<p class="ar-flag f-up"><i class="ar-smp" aria-hidden="true"></i><b>層に逆らう線</b>この図の上では、下の層から上の層へ向かう線が ${ups.length}本あります（${ups.slice(0, 3).map((e) => `${esc(name[e.from])} → ${esc(name[e.to])}`).join("、")}${ups.length > 3 ? " ほか" : ""}）。</p>`);
    const kinds = [...new Set(v.nodes.map((n) => n.kind).filter((k) => k && GLYPH[k]))];
    const legend = kinds.length ? `<p class="ar-legend">${kinds.map((k) => `<span><svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true">${GLYPH[k]}</svg>${KIND[k]}</span>`).join("")}</p>` : "";
    const rows = v.edges.map((e, k) => `<li class="ar-row${e.cyc ? " cyc" : ""}${e.up ? " up" : ""}" data-e="${k}" tabindex="0"><span>${esc(name[e.from])}</span><i aria-hidden="true">→</i><span>${esc(name[e.to])}</span>` +
      `<em>${e.label ? esc(e.label) : ""}${e.cyc ? `<small>循環</small>` : ""}${e.up ? `<small>層に逆らう</small>` : ""}</em></li>`).join("");
    // 線の中身は確かめていないことを、いつも文で添える（機械の印が、中身の正しさまで保証しているように読まれないため。研究 h2 の9章）
    const from = v.src === "shelf" ? "棚のページの記述によるものです" : v.src === "general" ? "一般の例としての、先生役の知識です" : "先生役の推測です";
    const src = `<p class="ar-src">箱と線は、${from}。あなたの実際のコードとは照らしていません。循環や層の向きの印は、この図に描かれた線の形だけを見たものです。</p>`;
    const idle = `箱を指すと、その箱が${esc(verb)}もの（青）と、その箱${esc(pv)}もの（緑）が光ります。押すと留まります。`;
    return `<p class="ar-how">線は <b>A → B</b> で「A は B ${esc(pv)}」と読みます。上の段が${esc(verb)}側です。</p>` +
      `<div class="ar-wrap" data-verb="${esc(verb)}" data-pv="${esc(pv)}">${svg}</div>${legend}${flags.join("")}` +
      `<p class="ar-read" role="status" data-idle="${idle}">${idle}</p>` +
      `<div class="ar-act" hidden><button class="chip" type="button" data-ardeep="1" aria-pressed="false">間接も含める</button>` +
      `<button class="chip" type="button" data-arask="">この箱の中を聞く</button><button class="chip" type="button" data-arimpact="">これを変えると響く所を聞く</button></div>` +
      `<details class="ar-list"><summary>線を文で読む（${v.edges.length}本）</summary><ol>${rows}</ol></details>${src}`;
  }

  // ── 指したときの見え方 ──
  const figOf = (el) => (el && el.closest ? el.closest(".v-arch") : null);
  function reach(fig, id, attr, deep) {
    const got = new Set(), todo = [id];
    while (todo.length) {
      const cur = todo.pop();
      const el = fig.querySelector(`.ar-node[data-id="${CSS.escape(cur)}"]`);
      for (const nx of (el ? el.dataset[attr] : "").split(" ").filter(Boolean)) {
        if (nx === id || got.has(nx)) continue;
        got.add(nx);
        if (deep) todo.push(nx);
      }
    }
    return got;
  }
  function clear(fig) {
    fig.classList.remove("has-sel");
    fig.querySelectorAll(".sel, .uses, .usedby, .on").forEach((x) => x.classList.remove("sel", "uses", "usedby", "on"));
  }
  const names = (fig, ids) => [...ids].map((i) => fig.querySelector(`.ar-node[data-id="${CSS.escape(i)}"]`)?.dataset.name || i);
  function show(fig, id) {
    clear(fig);
    const read = fig.querySelector(".ar-read"), act = fig.querySelector(".ar-act");
    const pin = fig.dataset.pin || "";
    if (act) act.hidden = !pin;
    if (!id) { if (read) read.textContent = read.dataset.idle; return; }
    const deep = fig.dataset.deep === "1";
    const node = fig.querySelector(`.ar-node[data-id="${CSS.escape(id)}"]`);
    if (!node) return;
    const down = reach(fig, id, "out", deep), up = reach(fig, id, "in", deep);
    fig.classList.add("has-sel");
    node.classList.add("sel");
    for (const n of fig.querySelectorAll(".ar-node")) {
      if (down.has(n.dataset.id)) n.classList.add("uses");
      if (up.has(n.dataset.id)) n.classList.add("usedby");   // 循環の中の箱は、両方の印が付く
    }
    const inDown = (x) => x === id || down.has(x), inUp = (x) => x === id || up.has(x);
    for (const e of fig.querySelectorAll(".ar-edge, .ar-row, .ar-el")) {
      const g = e.classList.contains("ar-edge") ? e : fig.querySelector(`.ar-edge[data-e="${e.dataset.e}"]`);
      const a = g.dataset.from, b = g.dataset.to;
      const on = deep ? ((inDown(a) && inDown(b) && down.has(b)) || (inUp(a) && inUp(b) && up.has(a))) : (a === id || b === id);
      if (on) e.classList.add("on");
    }
    const wrap = fig.querySelector(".ar-wrap"), verb = wrap?.dataset.verb || "使う", pv = wrap?.dataset.pv || "を使う";
    const list = (s) => `${s.size}つ（${names(fig, s).slice(0, 6).join("・")}${s.size > 6 ? " ほか" : ""}）`;
    const nm0 = node.dataset.name, far = deep ? "（たどれる先まで）" : "";
    // 2つの文の頭の色の印は、図の中の色（使うもの＝青・使われる相手＝緑）と同じ
    if (read) read.innerHTML =
      `<span class="rd uses">${esc(down.size ? `「${nm0}」が${verb}のは、${list(down)}${far}。` : `「${nm0}」が${verb}ものは、この図にはありません。`)}</span>` +
      `<span class="rd usedby">${esc(up.size ? `「${nm0}」${pv}のは、${list(up)}${far}。` : `「${nm0}」${pv}ものは、この図にはありません。`)}</span>`;
    if (act && pin) {
      const nm = node.dataset.name;
      act.querySelector("[data-arask]").dataset.arask = `『${nm}』の中の構成を、同じ構成の図で見せて（中の部品と、その間の${verb}向き）`;
      act.querySelector("[data-arimpact]").dataset.arimpact = `『${nm}』を変えると、どこに、なぜ響きますか。響く順に短く教えて`;
      act.querySelector("[data-ardeep]").setAttribute("aria-pressed", deep ? "true" : "false");
    }
  }
  function edgeOn(fig, k) {
    clear(fig);
    const g = fig.querySelector(`.ar-edge[data-e="${k}"]`);
    if (!g) return;
    fig.classList.add("has-sel");
    fig.querySelectorAll(`[data-e="${k}"]`).forEach((x) => x.classList.add("on"));
    for (const [id, cls] of [[g.dataset.from, "sel"], [g.dataset.to, "uses"]]) fig.querySelector(`.ar-node[data-id="${CSS.escape(id)}"]`)?.classList.add(cls);
    const read = fig.querySelector(".ar-read");
    if (read) read.textContent = g.getAttribute("aria-label");
  }
  function point(target) {
    const fig = figOf(target);
    if (!fig) return;
    const node = target.closest(".ar-node"), edge = target.closest(".ar-edge, .ar-row");
    if (node) show(fig, node.dataset.id);
    else if (edge) edgeOn(fig, edge.dataset.e);
    else show(fig, fig.dataset.pin || "");
  }
  let last = null;
  const leave = (e) => { const fig = figOf(e.target); if (fig && !fig.contains(e.relatedTarget)) show(fig, fig.dataset.pin || ""); };
  document.addEventListener("mouseover", (e) => { if (figOf(e.target)) { last = figOf(e.target); point(e.target); } else if (last) { if (last.isConnected) show(last, last.dataset.pin || ""); last = null; } });
  document.addEventListener("focusin", (e) => { if (figOf(e.target)) point(e.target); });
  document.addEventListener("focusout", leave);
  // 留めた箱は、図ごとの名前（data-akey。往復と図の番号を app.js が付ける）で覚えておく。往復の列が描き直されても、
  // 大きく見る窓で留めても、同じ図なら同じ箱が留まったままになる
  const PINS = new Map();
  function remember(fig) {
    const key = fig.dataset.akey;
    if (!key) return;
    if (fig.dataset.pin) PINS.set(key, { pin: fig.dataset.pin, deep: fig.dataset.deep === "1" });
    else PINS.delete(key);
  }
  function restore(fig) {
    const p = fig.dataset.akey ? PINS.get(fig.dataset.akey) : null;
    const pin = p && fig.querySelector(`.ar-node[data-id="${CSS.escape(p.pin)}"]`) ? p.pin : "";
    if ((fig.dataset.pin || "") === pin && (fig.dataset.deep === "1") === !!(p && p.deep && pin)) return;
    fig.dataset.pin = pin;
    fig.dataset.deep = p && p.deep && pin ? "1" : "0";
    show(fig, pin);
  }
  const sync = () => document.querySelectorAll(".v-arch[data-akey]").forEach(restore);
  function press(e) {
    const fig = figOf(e.target);
    if (!fig) return;
    const act = (what) => document.dispatchEvent(new CustomEvent("tonari:act", { detail: { what } }));
    if (e.target.closest("[data-ardeep]")) { fig.dataset.deep = fig.dataset.deep === "1" ? "0" : "1"; if (fig.dataset.deep === "1") act("deep"); remember(fig); show(fig, fig.dataset.pin || ""); return; }
    const node = e.target.closest(".ar-node");
    if (node) {
      fig.dataset.pin = fig.dataset.pin === node.dataset.id ? "" : node.dataset.id;
      if (fig.dataset.pin) act("pin"); else fig.dataset.deep = "0";
      remember(fig);
      show(fig, fig.dataset.pin || node.dataset.id);
      // 押したあとに焦点を箱に残さない（残ると、話すキーや答えを開くキーを箱が受けてしまう）
      if (e.type === "click" && node.blur) node.blur();
      return;
    }
    if (e.target.closest(".ar-svg") && !e.target.closest(".ar-edge")) { fig.dataset.pin = ""; fig.dataset.deep = "0"; remember(fig); show(fig, ""); }
  }
  document.addEventListener("click", press);
  // キーで留めるのは Enter だけ（Tab で箱に焦点を置いたとき）。Space はアプリの話すキーなので受けない。押し続けの繰り返しも受けない
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.repeat || e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
    if (e.target.closest && e.target.closest(".ar-node")) { e.preventDefault(); e.stopPropagation(); press(e); }
  }, true);

  window.TonariArch = { render, KIND, show, restore, sync };
})();
