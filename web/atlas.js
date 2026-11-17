// となり — 全体の地図（v0.6・DESIGN 17.13）。話題に出てきた言葉と関係の全部を、1枚に置いて見渡す。
// 置き場所はサーバーが決める（server/atlas.py）。島は話題で、話題をまたぐ言葉は出てくる島ごとに置き、橋で結ぶ。
// 研究 g2・g5 から: 最初の画面にしない（押したときに開く）・全部の線を一度に束ねない・島には名前の札を付ける・
// 理解の段を色で塗らない（事実の印だけ）・探すのは検索と一覧、関係を読むのは地図。
(function () {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const { esc } = window.TonariMD;
  const M = window.TonariMap;
  const PILL = 21, FAR = 0.62, KMIN = 0.12, KMAX = 2.4;
  const fold = (s) => String(s || "").normalize("NFKC").toLowerCase().replace(/\s+/g, "");
  const short = (s, n) => (String(s).length <= n ? String(s) : String(s).slice(0, n - 1) + "…");
  const A = { hooks: null, data: null, k: 1, tx: 0, ty: 0, sel: null, q: "", hits: [], hitAt: -1, anim: 0, drag: null, moved: false };
  let N = new Map(), T = new Map(), E = new Map(), P = {}, I = new Map(), HUE = new Map(), KIDS = new Map(), PAR = new Map();

  function index() {
    const d = A.data, L = d.layout;
    N = new Map(d.nodes.map((n) => [n.id, n]));
    T = new Map(d.topics.map((t) => [t.id, t]));
    E = new Map(d.edges.map((e) => [e.id, e]));
    P = L.places;
    I = new Map(L.islands.map((i) => [i.topic, i]));
    HUE = new Map(d.topics.map((t, i) => [t.id, Math.round((212 + i * 137.508) % 360)]));
    KIDS = new Map(); PAR = new Map();
    for (const [rid, p, c] of L.links) {
      if (!KIDS.has(p)) KIDS.set(p, []);
      KIDS.get(p).push({ k: c, rid });
      PAR.set(c, { k: p, rid });
    }
  }
  const tidOf = (key) => Number(key.split(":")[0]);
  const cidOf = (key) => Number(key.split(":")[1]);
  const isHub = (key) => T.get(tidOf(key)).hubs.includes(cidOf(key));

  // ── 描く ──────────────────────────────────────────────
  // 関係の種類ごとの線。上位・下位は、広い側に小さな三角。部品は、部品の側に小さな四角。対は破線。つながりは細い線
  function linkHTML(rid, pk, ck) {
    const e = E.get(rid), a = P[pk], b = P[ck];
    if (!e || !a || !b) return "";
    const x1 = a[0] + a[2], y1 = a[1], x2 = b[0], y2 = b[1], dx = Math.max(12, (x2 - x1) * 0.55);
    const kind = e.rel === "broader" ? "broader" : e.rel === "opposite" ? "opp" : e.detail === "部分" ? "part" : "rel";
    let mark = "";
    if (kind === "broader") {
      // e.src の上位が e.dst。広い側（dst）に三角を置く
      const atParent = cidOf(pk) === e.dst;
      const [tx, ty, s] = atParent ? [x1 + 1, y1, 1] : [x2 - 1, y2, -1];
      mark = `<path class="lk-tri" d="M${tx} ${ty} l${8 * s} -4.5 v9 z"/>`;
    } else if (kind === "part") {
      const atChild = cidOf(ck) === e.dst;      // 部品は dst（中心 src の中にあるもの）
      const [qx, qy] = atChild ? [x2 - 7, y2 - 2.5] : [x1 + 2, y1 - 2.5];
      mark = `<rect class="lk-sq" x="${qx}" y="${qy}" width="5" height="5"/>`;
    }
    const ok = e.rstate === "known" ? `<circle class="lk-ok" cx="${(x1 + x2) / 2}" cy="${(y1 + y2) / 2}" r="3.2"><title>確かめて「分かる」になった関係</title></circle>` : "";
    return `<g class="lk k-${kind}${e.rstate === "known" ? " known" : ""}" data-rid="${rid}" data-a="${pk}" data-b="${ck}">` +
      `<path d="M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}"/>${mark}${ok}</g>`;
  }
  // 木に入らなかった関係（輪になる分）は、右に張り出す細い点線
  function crossHTML(rid, ak, bk) {
    const a = P[ak], b = P[bk];
    if (!a || !b) return "";
    const x1 = a[0] + a[2], x2 = b[0] + b[2], bx = Math.max(x1, x2) + 26;
    return `<path class="lk-x" data-rid="${rid}" data-a="${ak}" data-b="${bk}" d="M${x1} ${a[1]} C${bx} ${a[1]} ${bx} ${b[1]} ${x2} ${b[1]}"/>`;
  }
  // 島の四角の中心どうしを結ぶ線を、四角の縁で切る
  function clip(i, tx, ty) {
    const cx = i.bx + i.bw / 2, cy = i.by + i.bh / 2, dx = tx - cx, dy = ty - cy;
    if (!dx && !dy) return [cx, cy];
    const s = Math.min(dx ? (i.bw / 2) / Math.abs(dx) : Infinity, dy ? (i.bh / 2) / Math.abs(dy) : Infinity);
    return [cx + dx * s, cy + dy * s];
  }
  function bridgeHTML(b) {
    const ia = I.get(b.a), ib = I.get(b.b);
    if (!ia || !ib) return "";
    const ca = [ia.bx + ia.bw / 2, ia.by + ia.bh / 2], cb = [ib.bx + ib.bw / 2, ib.by + ib.bh / 2];
    const p = clip(ia, cb[0], cb[1]), q = clip(ib, ca[0], ca[1]), n = b.concepts.length;
    const mx = (p[0] + q[0]) / 2, my = (p[1] + q[1]) / 2;
    // 引いて見るとき: 島と島のあいだの1本の橋（太さと数で、共有する言葉の数を出す。束ねて曲げない）
    let h = `<g class="br" data-bridge="${b.a}:${b.b}"><line class="br-a" x1="${p[0]}" y1="${p[1]}" x2="${q[0]}" y2="${q[1]}" style="stroke-width:${2.5 + 1.8 * Math.min(n, 6)}"/>` +
      `<g transform="translate(${mx} ${my})"><g class="br-n"><circle r="9.5"/><text dy="3.8">${n}</text></g></g>`;
    // 寄って見るとき: 同じ言葉の札どうしを結ぶ太く薄い線（言葉ごとに1本）
    for (const c of b.concepts) {
      const a = P[`${b.a}:${c}`], z = P[`${b.b}:${c}`];
      if (!a || !z) continue;
      const [l, r] = a[0] <= z[0] ? [a, z] : [z, a];
      const sep = l[0] + l[2] < r[0];
      const x1 = sep ? l[0] + l[2] : l[0] + l[2] / 2, x2 = sep ? r[0] : r[0] + r[2] / 2;
      const y1 = sep ? l[1] : l[1] + (r[1] > l[1] ? PILL / 2 : -PILL / 2), y2 = sep ? r[1] : r[1] + (r[1] > l[1] ? -PILL / 2 : PILL / 2);
      h += `<line class="br-c" data-c="${c}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
    }
    return h + `</g>`;
  }
  function nodeHTML(key) {
    const [x, y, w] = P[key], n = N.get(cidOf(key)), hub = isHub(key), shared = n.topics.length > 1;
    const tip = n.label + (n.gist ? ` — ${n.gist}` : "") + (shared ? `（${n.topics.length}つの話題に出てくる言葉）` : "");
    return `<g class="nd${hub ? " hub" : ""}${shared ? " shared" : ""}${n.state ? " s-" + n.state : ""}" data-k="${key}" data-c="${n.id}" style="--h:${HUE.get(tidOf(key))}" transform="translate(${x} ${y})">` +
      `<title>${esc(tip)}</title><rect x="0" y="${-PILL / 2}" width="${w}" height="${PILL}" rx="${PILL / 2}"/>` +
      `<text x="${hub ? 9.5 : 9}" dy="4.5"${hub ? ` data-full="${esc(short(n.label, 16))}" data-w="${w + 70}"` : ""}>${esc(short(n.label, 16))}</text>${shared ? `<circle class="nd-sh" cx="${w - 1}" cy="${-PILL / 2 + 2}" r="3.4"/>` : ""}</g>`;
  }
  function islandHTML(i) {
    const t = T.get(i.topic), cur = A.hooks.active() === t.id;
    return `<g class="isl${t.archived ? " arch" : ""}${cur ? " cur" : ""}" data-topic="${t.id}" style="--h:${HUE.get(t.id)}">` +
      `<rect class="isl-bg" x="${i.bx}" y="${i.by}" width="${i.bw}" height="${i.bh}" rx="14"/>` +
      `<text class="isl-t" x="${i.tx}" y="${i.ty}" dy="5" data-full="${esc(short(t.title, 26))}" data-w="${i.bw - 28}">${esc(short(t.title, 26))}<tspan class="isl-n" dx="10">${t.concepts.length}語${t.archived ? "・片づけ済み" : ""}${cur ? "・いま開いている話題" : ""}</tspan></text></g>`;
  }
  function draw() {
    const d = A.data, L = d.layout, svg = $("#atSvg");
    if (!L.islands.length) {
      svg.innerHTML = "";
      $("#atEmpty").hidden = false;
      return;
    }
    $("#atEmpty").hidden = true;
    A.titleKey = null;
    svg.innerHTML = `<g id="atVp">` +
      `<g class="g-isl">${L.islands.map(islandHTML).join("")}</g>` +
      `<g class="g-br">${L.bridges.map(bridgeHTML).join("")}</g>` +
      `<g class="g-lk">${L.cross.map((x) => crossHTML(...x)).join("")}${L.links.map((x) => linkHTML(...x)).join("")}</g>` +
      `<g class="g-nd">${Object.keys(P).sort((x, y) => isHub(x) - isHub(y)).map(nodeHTML).join("")}</g></g>`;
    apply();
  }

  // ── 見る場所（寄る・引く・動かす） ────────────────────────
  function apply() {
    const vp = $("#atVp"), svg = $("#atSvg");
    if (!vp) return;
    vp.setAttribute("transform", `translate(${A.tx.toFixed(2)} ${A.ty.toFixed(2)}) scale(${A.k.toFixed(4)})`);
    svg.style.setProperty("--k", A.k.toFixed(4));
    svg.classList.toggle("far", A.k < FAR);
    $("#atZoomNow").textContent = Math.round(A.k * 100) + "%";
    fitTitles();
  }
  // 引いて見るとき、島の名前は読める大きさのまま、島の幅に収まる字数に切る（隣の島の名前に重ねない）
  const em = (s) => [...s].reduce((n, ch) => n + (/[\u0000-\u00ff\uff61-\uff9f]/.test(ch) ? 0.6 : 1), 0);
  function fitTitles() {
    const far = A.k < FAR, key = far ? Math.round(A.k * 40) : -1;
    if (A.titleKey === key) return;
    A.titleKey = key;
    for (const el of $$("#atSvg .isl-t, #atSvg .nd.hub text")) {
      const full = el.dataset.full, px = el.classList.contains("isl-t") ? Math.max(12.5, 13 * A.k) : Math.max(10.5, 14 * A.k);
      let s = full;
      if (far) {
        const room = (Number(el.dataset.w) * A.k) / px;     // 入る字数（全角で数える）
        if (em(full) > room) {
          let out = "";
          for (const ch of full) { if (em(out + ch) > room - 1) break; out += ch; }
          s = out ? out + "…" : "";
        }
      }
      if (el.firstChild && el.firstChild.nodeType === 3 && el.firstChild.nodeValue !== s) el.firstChild.nodeValue = s;
    }
  }
  const view = () => $("#atView").getBoundingClientRect();
  function target(box, maxK = 1.15, pad = 36) {
    const v = view(), w = box[2] - box[0], h = box[3] - box[1];
    const k = Math.max(KMIN, Math.min(maxK, (v.width - pad * 2) / Math.max(w, 1), (v.height - pad * 2) / Math.max(h, 1)));
    return { k, tx: (v.width - w * k) / 2 - box[0] * k, ty: (v.height - h * k) / 2 - box[1] * k };
  }
  // 段を移るときは、動きで前後をつなぐ（g5 の 3-1）。窓が隠れている・動きを減らす設定のときは、すぐ移る
  function fly(to, anim = true) {
    cancelAnimationFrame(A.anim);
    clearTimeout(A.animT);
    const still = !anim || document.hidden || (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
    if (still) { Object.assign(A, to); apply(); return; }
    const from = { k: A.k, tx: A.tx, ty: A.ty }, t0 = performance.now(), ms = 260;
    const done = () => { cancelAnimationFrame(A.anim); clearTimeout(A.animT); Object.assign(A, to); apply(); };
    const step = (now) => {
      const p = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - p, 3);
      A.k = from.k + (to.k - from.k) * e; A.tx = from.tx + (to.tx - from.tx) * e; A.ty = from.ty + (to.ty - from.ty) * e;
      apply();
      if (p < 1) A.anim = requestAnimationFrame(step); else done();
    };
    A.anim = requestAnimationFrame(step);
    A.animT = setTimeout(done, ms + 120);   // 描く合図が来ない窓でも、必ず行き先に着く
  }
  const fit = (anim = true) => fly(target(A.data.layout.box), anim);
  function zoomAt(f, cx, cy, anim = false) {
    const v = view(), x = cx - v.left, y = cy - v.top, k = Math.max(KMIN, Math.min(KMAX, A.k * f));
    fly({ k, tx: x - (x - A.tx) * (k / A.k), ty: y - (y - A.ty) * (k / A.k) }, anim);
  }
  const zoomBy = (f) => { const v = view(); zoomAt(f, v.left + v.width / 2, v.top + v.height / 2, true); };
  function boxOf(keys) {
    const ps = keys.map((k) => P[k]).filter(Boolean);
    if (!ps.length) return null;
    return [Math.min(...ps.map((p) => p[0])) - 30, Math.min(...ps.map((p) => p[1])) - 40, Math.max(...ps.map((p) => p[0] + p[2])) + 30, Math.max(...ps.map((p) => p[1])) + 40];
  }
  const islandBox = (tid) => { const i = I.get(tid); return i ? [i.bx, i.by, i.bx + i.bw, i.by + i.bh] : null; };
  // 選んだ物が見える所まで動かす。もう読める大きさで窓の中にあれば、動かさない
  function reveal(box, minK = 0.8) {
    if (!box) return;
    const v = view(), l = box[0] * A.k + A.tx, top = box[1] * A.k + A.ty, r = box[2] * A.k + A.tx, b = box[3] * A.k + A.ty;
    if (A.k >= minK - 0.001 && l >= 8 && top >= 8 && r <= v.width - 8 && b <= v.height - 8) return;
    fly(target(box, Math.min(1.15, Math.max(A.k, minK))), true);
  }

  // ── 選ぶ ──────────────────────────────────────────────
  const keysOfConcept = (cid) => (N.get(cid) ? N.get(cid).topics.map((t) => `${t}:${cid}`).filter((k) => P[k]) : []);
  const edgesOf = (cid) => A.data.edges.filter((e) => e.src === cid || e.dst === cid);
  function paintSel() {
    const svg = $("#atSvg"), s = A.sel;
    $$(".on, .nb, .onc, .in", svg).forEach((el) => el.classList.remove("on", "nb", "onc", "in"));
    svg.classList.toggle("has-sel", !!s);
    if (!s) return;
    const on = (sel) => $$(sel, svg).forEach((el) => el.classList.add("on"));
    if (s.type === "c") {
      on(`.nd[data-c="${s.cid}"]`);
      on(`.br-c[data-c="${s.cid}"]`);
      for (const e of edgesOf(s.cid)) {
        on(`.lk[data-rid="${e.id}"], .lk-x[data-rid="${e.id}"]`);
        $$(`.nd[data-c="${e.src === s.cid ? e.dst : e.src}"]`, svg).forEach((el) => el.classList.add("nb"));
      }
      for (const x of A.data.layout.bridges) if (x.concepts.includes(s.cid)) $$(`.br[data-bridge="${x.a}:${x.b}"]`, svg).forEach((el) => el.classList.add("onc"));
    } else if (s.type === "t") {
      on(`.isl[data-topic="${s.tid}"]`);
      for (const c of T.get(s.tid).concepts) $$(`.nd[data-k="${s.tid}:${c}"]`, svg).forEach((el) => el.classList.add("in"));
      $$(`.lk, .lk-x`, svg).forEach((el) => { if (tidOf(el.dataset.a) === s.tid) el.classList.add("in"); });
      $$(`.br[data-bridge]`, svg).forEach((el) => { if (el.dataset.bridge.split(":").map(Number).includes(s.tid)) el.classList.add("on"); });
    } else if (s.type === "b") {
      on(`.br[data-bridge="${s.a}:${s.b}"]`);
      on(`.isl[data-topic="${s.a}"], .isl[data-topic="${s.b}"]`);
      const b = A.data.layout.bridges.find((x) => x.a === s.a && x.b === s.b);
      for (const c of (b ? b.concepts : [])) on(`.nd[data-k="${s.a}:${c}"], .nd[data-k="${s.b}:${c}"]`);
    }
  }
  function select(s, opts = {}) {
    A.sel = s;
    paintSel();
    paintSide();
    if (s && opts.log !== false) A.hooks.api("POST", "/api/atlas/act", { what: s.type === "c" ? "concept" : "topic", id: s.type === "c" ? s.cid : s.type === "t" ? s.tid : s.a }).catch(() => {});
    if (!s || opts.move === false) return;
    if (s.type === "c") reveal(boxOf(s.key ? [s.key] : keysOfConcept(s.cid).slice(0, 1)));
    if (s.type === "t") reveal(islandBox(s.tid), Math.min(0.8, target(islandBox(s.tid), 0.8).k));
  }

  // ── 右の欄（探すのは一覧、関係を読むのは地図） ────────────────
  // 関係を、位置の図と同じ読み方の文にする（中心 は 相手 つなぐ言葉）
  function relRow(e, cid) {
    const out = e.src === cid, o = N.get(out ? e.dst : e.src), me = N.get(cid);
    if (!o) return "";
    const btn = `<button class="at-w" data-at-c="${o.id}">${esc(o.label)}</button>`, ok = e.rstate === "known" ? `<i class="at-ok" title="確かめて「分かる」になった関係">✓</i>` : "";
    if (e.rel === "broader") return `<li><span class="at-k">${out ? "広い言葉" : "種類"}</span>${btn}${ok}</li>`;
    if (e.rel === "opposite") return `<li><span class="at-k">取り違えやすい相手</span>${btn}${e.detail ? `<small>違いは「${esc(e.detail)}」</small>` : ""}${ok}</li>`;
    const r = M.relate({ rel: e.detail, phrase: e.phrase, out, label: o.label }, me.label);
    if (r.part) return `<li><span class="at-k">部品</span>${btn}${ok}</li>`;
    return r.node === "subj" ? `<li>${btn}<span class="at-wa">は</span><b>${esc(r.obj)}</b><span class="at-link">${esc(r.link)}</span>${ok}</li>`
      : `<li><b>${esc(r.subj)}</b><span class="at-wa">は</span>${btn}<span class="at-link">${esc(r.link)}</span>${ok}</li>`;
  }
  // 島の中の言葉を、木の順に字下げで並べた一覧（g5: 字下げの一覧を超える木の見せ方は無かった）
  function outline(tid) {
    const t = T.get(tid), keys = t.concepts.map((c) => `${tid}:${c}`).filter((k) => P[k]);
    const roots = keys.filter((k) => !PAR.has(k)).sort((a, b) => P[a][1] - P[b][1]);
    const tag = (k) => {
      const p = PAR.get(k);
      if (!p) return "";
      const e = E.get(p.rid), child = cidOf(k);
      if (e.rel === "broader") return e.dst === child ? "広い言葉" : "種類";
      if (e.rel === "opposite") return "取り違えやすい相手";
      if (e.detail === "部分") return e.dst === child ? "部品" : "これを部品に持つ";
      return e.phrase && e.dst === child ? e.phrase : "つながり";
    };
    const row = (k, depth) => {
      const n = N.get(cidOf(k)), kids = (KIDS.get(k) || []).map((x) => x.k).sort((a, b) => P[a][1] - P[b][1]);
      return `<li style="--d:${depth}"><button class="at-w${isHub(k) ? " hub" : ""}" data-at-k="${k}">${esc(n.label)}</button>` +
        `${tag(k) ? `<small>${esc(tag(k))}</small>` : ""}${n.topics.length > 1 ? `<i class="at-sh" title="ほかの話題にも出てくる言葉">${n.topics.length}</i>` : ""}</li>` + kids.map((c) => row(c, depth + 1)).join("");
    };
    return `<ul class="at-out">${roots.map((k) => row(k, 0)).join("")}</ul>`;
  }
  function legendHTML() {
    return `<div class="at-legend"><p><svg width="46" height="14"><g class="lk k-broader"><path d="M2 7 H44"/><path class="lk-tri" d="M3 7 l8 -4.5 v9 z"/></g></svg>種類の関係（三角の側が広い言葉）</p>` +
      `<p><svg width="46" height="14"><g class="lk k-part"><path d="M2 7 H44"/><rect class="lk-sq" x="37" y="4.5" width="5" height="5"/></g></svg>部品（四角の側が部品）</p>` +
      `<p><svg width="46" height="14"><g class="lk k-opp"><path d="M2 7 H44"/></g></svg>取り違えやすい相手</p>` +
      `<p><svg width="46" height="14"><g class="lk k-rel"><path d="M2 7 H44"/></g></svg>そのほかのつながり</p>` +
      `<p><svg width="46" height="14"><line class="br-c on" x1="3" y1="7" x2="43" y2="7"/></svg>同じ言葉（話題をまたいで出てくる）</p>` +
      `<p><b class="at-hubmark">太字</b>説明を受けた言葉（答えの中心になった言葉）</p>` +
      `<p class="tiny">色は話題の見分けで、理解の度合いではありません。緑の点は、確かめて「分かる」になった関係です。</p></div>`;
  }
  function paintSide() {
    const el = $("#atSide"), s = A.sel, d = A.data, c = d.counts;
    if (!s) {
      const rows = [...d.topics].reverse().map((t) => `<li><button class="at-topic" data-at-t="${t.id}" style="--h:${HUE.get(t.id)}"><i></i><span>${esc(t.title)}</span></button>` +
        `<small>${t.concepts.length}語${t.archived ? "・片づけ済み" : ""}</small></li>`).join("");
      el.innerHTML = `<h3>全体の地図</h3>` +
        `<p class="at-sum">話題 ${c.topics}・言葉 ${c.concepts}・関係 ${c.relations}・話題をまたいで出てくる言葉 ${c.shared}・確かめて分かるになった関係 ${c.known}</p>` +
        `<p class="tiny">島は話題です。同じ言葉が別の話題にも出てくるときは、島と島を線で結びます。言葉か島を押すと、ここに中身が出ます。</p>` +
        (c.empty_topics ? `<p class="tiny">まだ言葉の無い話題 ${c.empty_topics} は、地図に出ていません。</p>` : "") +
        `<h4>話題（新しい順）</h4><ul class="at-topics">${rows}</ul>` + legendHTML() +
        `<p class="at-re tiny">島の置き場所は、開くたびに同じです。話題が増えて見にくくなったら、<button class="link" data-at-relayout="1">島を並べ直す</button>と、言葉を共有する話題を寄せ直します（置き場所が変わります）。</p>`;
      return;
    }
    if (s.type === "c") {
      const n = N.get(s.cid), es = edgesOf(s.cid);
      el.innerHTML = `<button class="link at-back" data-at-clear="1">← 全体の一覧へ</button><h3>${esc(n.label)}</h3>` +
        (n.gist ? `<p class="at-gist">${esc(n.gist)}</p>` : "") +
        `<p class="tiny">${n.hub ? `説明を受けた言葉（${n.hub}回）・` : ""}${n.topics.length > 1 ? `${n.topics.length}つの話題に出てくる` : "1つの話題に出てくる"}</p>` +
        `<div class="at-chips">${n.topics.map((t) => `<button class="at-topic" data-at-t="${t}" style="--h:${HUE.get(t)}"><i></i><span>${esc(T.get(t).title)}</span></button>`).join("")}</div>` +
        (es.length ? `<h4>この言葉の関係</h4><ul class="at-rels">${es.map((e) => relRow(e, s.cid)).join("")}</ul>` : `<p class="tiny">まだ関係の記録がありません。</p>`) +
        `<div class="at-act"><button class="primary" data-at-ego="${n.id}">位置の図で見る</button><button class="ghost" data-at-ask="${esc(n.label)}">これを説明して</button></div>`;
      return;
    }
    if (s.type === "t") {
      const t = T.get(s.tid), shared = t.concepts.filter((x) => N.get(x).topics.length > 1).length;
      el.innerHTML = `<button class="link at-back" data-at-clear="1">← 全体の一覧へ</button><h3>${esc(t.title)}</h3>` +
        `<p class="at-sum">言葉 ${t.concepts.length}・説明を受けた言葉 ${t.hubs.length}・ほかの話題にも出てくる言葉 ${shared}${t.archived ? "・片づけ済み" : ""}</p>` +
        `<div class="at-act"><button class="primary" data-at-open="${t.id}">${t.archived ? "一覧に戻して開く" : "この話題を開く"}</button></div>` +
        `<h4>この話題の言葉</h4>${outline(t.id)}`;
      return;
    }
    const b = d.layout.bridges.find((x) => x.a === s.a && x.b === s.b);
    el.innerHTML = `<button class="link at-back" data-at-clear="1">← 全体の一覧へ</button><h3>2つの話題に出てくる言葉</h3>` +
      `<div class="at-chips">${[s.a, s.b].map((t) => `<button class="at-topic" data-at-t="${t}" style="--h:${HUE.get(t)}"><i></i><span>${esc(T.get(t).title)}</span></button>`).join("")}</div>` +
      `<ul class="at-rels">${(b ? b.concepts : []).map((cid) => `<li><button class="at-w" data-at-c="${cid}">${esc(N.get(cid).label)}</button></li>`).join("")}</ul>`;
  }

  // ── 探す ──────────────────────────────────────────────
  function find(q) {
    A.q = q;
    const f = fold(q), svg = $("#atSvg");
    $$(".hit", svg).forEach((el) => el.classList.remove("hit"));
    A.hits = f ? Object.keys(P).filter((k) => fold(N.get(cidOf(k)).label).includes(f)) : [];
    const topics = f ? A.data.topics.filter((t) => fold(t.title).includes(f)).map((t) => t.id) : [];
    A.hits.forEach((k) => { const el = $(`.nd[data-k="${k}"]`, svg); if (el) el.classList.add("hit"); });
    topics.forEach((t) => { const el = $(`.isl[data-topic="${t}"]`, svg); if (el) el.classList.add("hit"); });
    svg.classList.toggle("has-find", !!f);
    A.hitAt = -1;
    $("#atFindN").textContent = f ? `${new Set(A.hits.map(cidOf)).size}語${topics.length ? `・話題 ${topics.length}` : ""}` : "";
    A.hitTopics = topics;
  }
  function nextHit() {
    if (!A.hits.length) { if (A.hitTopics && A.hitTopics.length) select({ type: "t", tid: A.hitTopics[0] }); return; }
    A.hitAt = (A.hitAt + 1) % A.hits.length;
    const k = A.hits[A.hitAt];
    select({ type: "c", cid: cidOf(k), key: k });
    A.hooks.api("POST", "/api/atlas/act", { what: "find" }).catch(() => {});
  }

  // ── 開く・閉じる ────────────────────────────────────────
  // 選んだ印・探した印を消す（開き直したとき・並べ直したときに、前の印で全部の札が薄いままにならないように）
  function clearMarks() {
    A.sel = null; A.q = ""; A.hits = []; A.hitTopics = [];
    $("#atFind").value = ""; $("#atFindN").textContent = "";
    $("#atSvg").classList.remove("has-sel", "has-find");
  }
  async function open() {
    const dlg = $("#atlas");
    if (dlg.open || A.opening || !A.hooks.canOpen()) return false;
    A.opening = true;
    let data;
    try { data = await A.hooks.api("POST", "/api/atlas/open"); } catch (e) { A.hooks.toast("地図を開けませんでした: " + e.message); return false; } finally { A.opening = false; }
    // 応答を待つあいだに録音が始まった・ほかの小窓が開いたときは、開かない（録音の上に地図を重ねない）
    if (dlg.open || !A.hooks.canOpen()) return false;
    A.data = data;
    index();
    clearMarks();
    $("#atNews").hidden = true;
    A.closed = false; A.leave = false;
    dlg.showModal();
    draw();
    paintSide();
    if (A.data.layout.islands.length) fit(false);
    return true;
  }
  // 島を並べ直す（本人が押したときだけ。前の置き場所を使わずに決め直して、それを覚える）
  async function relayout() {
    let data;
    try { data = await A.hooks.api("POST", "/api/atlas/open", { reset: true }); } catch (e) { A.hooks.toast("並べ直せませんでした: " + e.message); return; }
    if (!isOpen()) return;
    A.data = data;
    index();
    clearMarks();
    draw();
    paintSide();
    fit(true);
  }
  // 閉じる。閉じたあとの後始末（覆っているあいだに届いた答えを、読める形で出したことにする）は、その場で終える。
  // 閉じてすぐ別の話題へ移るとき（leave）は、前の話題の答えを読んだことにしない
  function finishClose() {
    if (A.closed) return;
    A.closed = true;
    cancelAnimationFrame(A.anim);
    clearTimeout(A.animT);
    A.drag = null;
    A.hooks.onClose({ reveal: !A.leave });
  }
  function close(opts = {}) {
    const dlg = $("#atlas");
    if (!dlg.open) return;
    A.leave = !!opts.leave;
    dlg.close();
    finishClose();
  }
  const isOpen = () => $("#atlas").open;
  // 地図を開いているあいだに、答えが届いた（地図は往復の列を覆っているので、ここで知らせる）
  function news(n) { const b = $("#atNews"); if (!isOpen()) return; b.hidden = !n; b.textContent = n ? `答えが届きました（${n}）・読みに戻る` : ""; }

  function wire() {
    const dlg = $("#atlas"), viewEl = $("#atView"), svg = $("#atSvg");
    dlg.addEventListener("close", finishClose);     // Esc で閉じたとき（close() からは、その場で済ませてある）
    // Esc は、探す字 → 選んだ物 → 地図、の順に閉じる
    dlg.addEventListener("cancel", (e) => {
      if ($("#atFind").value) { e.preventDefault(); $("#atFind").value = ""; find(""); return; }
      if (A.sel) { e.preventDefault(); select(null); }
    });
    $("#atClose").addEventListener("click", () => close());
    $("#atFit").addEventListener("click", () => { fit(true); });
    $("#atIn").addEventListener("click", () => zoomBy(1.3));
    $("#atOut").addEventListener("click", () => zoomBy(1 / 1.3));
    $("#atHere").addEventListener("click", () => { const t = A.hooks.active(); if (t && I.has(t)) select({ type: "t", tid: t }); else A.hooks.toast("いま開いている話題には、まだ言葉がありません"); });
    // 「読みに戻る」: いま開いている話題に届いた答えがあれば、地図を閉じてそこへ。無ければ、答えの届いた別の話題へ
    $("#atNews").addEventListener("click", () => { const stay = A.hooks.unreadHere(); close({ leave: !stay }); if (!stay) A.hooks.goNext(); });
    $("#atFind").addEventListener("input", (e) => find(e.target.value));
    $("#atFind").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); nextHit(); } });

    // 動かす（つかんで動かす・2本指で送る）、寄る・引く（つまむ・⌘ か Ctrl を押しながら回す）
    viewEl.addEventListener("wheel", (e) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) zoomAt(Math.exp(-e.deltaY * 0.012), e.clientX, e.clientY);
      else fly({ k: A.k, tx: A.tx - e.deltaX, ty: A.ty - e.deltaY }, false);
    }, { passive: false });
    let g0 = 1;
    viewEl.addEventListener("gesturestart", (e) => { e.preventDefault(); g0 = A.k; });
    viewEl.addEventListener("gesturechange", (e) => { e.preventDefault(); zoomAt((g0 * e.scale) / A.k, e.clientX, e.clientY); });
    viewEl.addEventListener("gestureend", (e) => e.preventDefault());
    viewEl.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      A.drag = { x: e.clientX, y: e.clientY, tx: A.tx, ty: A.ty };
      A.moved = false;
    });
    window.addEventListener("pointermove", (e) => {
      if (!A.drag) return;
      const dx = e.clientX - A.drag.x, dy = e.clientY - A.drag.y;
      if (!A.moved && Math.hypot(dx, dy) < 4) return;
      A.moved = true;
      viewEl.classList.add("grab");
      fly({ k: A.k, tx: A.drag.tx + dx, ty: A.drag.ty + dy }, false);
    });
    window.addEventListener("pointerup", () => { A.drag = null; viewEl.classList.remove("grab"); });
    viewEl.addEventListener("dblclick", (e) => { if (!e.target.closest(".nd")) zoomAt(1.5, e.clientX, e.clientY, true); });
    svg.addEventListener("click", (e) => {
      if (A.moved) { A.moved = false; return; }      // つかんで動かした終わりは、押したことにしない
      const nd = e.target.closest(".nd"), br = e.target.closest(".br"), isl = e.target.closest(".isl");
      if (nd) { select({ type: "c", cid: Number(nd.dataset.c), key: nd.dataset.k }, { move: false }); return; }
      if (br) { const [a, b] = br.dataset.bridge.split(":").map(Number); select({ type: "b", a, b }, { move: false }); return; }
      if (isl) { select({ type: "t", tid: Number(isl.dataset.topic) }, { move: false }); return; }
      select(null);
    });
    $("#atSide").addEventListener("click", (e) => {
      const el = e.target.closest("button");
      if (!el) return;
      const d = el.dataset;
      if (d.atClear) { select(null); return; }
      if (d.atRelayout) { relayout(); return; }
      if (d.atT) { select({ type: "t", tid: Number(d.atT) }); return; }
      if (d.atC) { const cid = Number(d.atC), here = A.sel && A.sel.key ? `${tidOf(A.sel.key)}:${cid}` : null; select({ type: "c", cid, key: here && P[here] ? here : keysOfConcept(cid)[0] }); return; }
      if (d.atK) { select({ type: "c", cid: cidOf(d.atK), key: d.atK }); return; }
      if (d.atOpen) { const t = T.get(Number(d.atOpen)); A.hooks.api("POST", "/api/atlas/act", { what: "open_topic", id: t.id }).catch(() => {}); close({ leave: t.id !== A.hooks.active() }); A.hooks.openTopic(t.id, t.archived); return; }
      if (d.atEgo) { A.hooks.api("POST", "/api/atlas/act", { what: "ego", id: Number(d.atEgo) }).catch(() => {}); close(); A.hooks.showEgo(Number(d.atEgo)); return; }
      if (d.atAsk) { A.hooks.api("POST", "/api/atlas/act", { what: "ask" }).catch(() => {}); close(); A.hooks.ask(d.atAsk); }
    });
    // 地図のキー。地図の何も無い所を押すと焦点が地図の外へ移るので、文書の全体で受ける（開いているあいだだけ）。
    // 下の画面の操作（話す・新しい話題）は、地図を開いているあいだは app.js の側が受けない
    document.addEventListener("keydown", (e) => {
      if (!isOpen() || e.isComposing) return;
      const typing = e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA");
      if ((e.metaKey || e.ctrlKey) && e.code === "KeyF") { e.preventDefault(); $("#atFind").focus(); return; }
      if (A.hooks.isKey(e)) { e.preventDefault(); if (!e.repeat) close(); return; }
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
      const step = 90;
      if (e.key === "+" || e.key === "=" || e.key === ";") { e.preventDefault(); zoomBy(1.3); }
      else if (e.key === "-") { e.preventDefault(); zoomBy(1 / 1.3); }
      else if (e.key === "0") { e.preventDefault(); fit(true); }
      else if (e.key === "/") { e.preventDefault(); $("#atFind").focus(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); fly({ k: A.k, tx: A.tx + step, ty: A.ty }, false); }
      else if (e.key === "ArrowRight") { e.preventDefault(); fly({ k: A.k, tx: A.tx - step, ty: A.ty }, false); }
      else if (e.key === "ArrowUp") { e.preventDefault(); fly({ k: A.k, tx: A.tx, ty: A.ty + step }, false); }
      else if (e.key === "ArrowDown") { e.preventDefault(); fly({ k: A.k, tx: A.tx, ty: A.ty - step }, false); }
    });
  }

  window.TonariAtlas = {
    init(hooks) { A.hooks = hooks; wire(); },
    open, close, isOpen, news, relayout,
    state: A, select, fit, find, nextHit, zoomBy,
  };
})();
