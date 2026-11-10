// となり — 概念の位置の図（SVG）。置き場所に意味を固定する: 上=上位概念、下=下位概念、左右=対の概念、斜め=関係する概念。
// 毎回同じ規則で置くので、図を何枚見ても「上にあるのは広いほう」と読める（配置の一貫性）。
// 入力は2つの形を受ける。答えの札（tonari-map の JSON）と、記録の地図（/api/concepts/:id/ego）。
(function () {
  // 置き場所は2組。広い（答えの中・680×420）と、狭い（右の地図・400×440。縮めても字が小さくならないように）
  const LAYOUTS = {
    wide: { W: 680, H: 420, CX: 340, CY: 210, cut: 10, SLOTS: {
      broader: [[340, 52], [190, 52], [490, 52]],
      narrower: [[340, 368], [190, 368], [490, 368], [60, 368], [620, 368]],
      opposite: [[590, 210], [90, 210]],
      related: [[175, 128], [505, 128], [175, 292], [505, 292], [60, 128], [620, 292]],
    } },
    compact: { W: 400, H: 460, CX: 200, CY: 230, cut: 8, SLOTS: {
      broader: [[200, 40], [80, 40], [320, 40]],
      narrower: [[200, 420], [80, 420], [320, 420], [80, 372], [320, 372]],
      opposite: [[335, 230], [65, 230]],
      related: [[85, 132], [315, 132], [85, 328], [315, 328], [200, 132], [200, 328]],
    } },
  };
  let W, H, CX, CY, SLOTS, CUT;
  const REL_WORD = { broader: "上位", narrower: "下位" };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function srcKind(src) {
    const s = String(src || "");
    if (/〔[A-Za-z0-9_-]{6,64}/.test(s)) return "shelf";
    if (s.startsWith("一般")) return "general";
    return "inferred";
  }

  // 札の字の幅（全角＝1・半角＝0.6）。札の幅はこの幅で決める（字数で決めると半角の多い名前が間延びする）
  const uw = (s) => [...String(s || "")].reduce((n, ch) => n + (/[\x20-\x7e]/.test(ch) ? 0.6 : 1), 0);
  const kindOf = (ch) => (/[\x20-\x7e]/.test(ch) ? "a" : /[゠-ヿ]/.test(ch) ? "k" : /[぀-ゟ]/.test(ch) ? "h" : "x");
  const NOSTART = /^[ーッャュョァィゥェォっゃゅょぁぃぅぇぉ、。・）」』\)]/;
  // 2行に割るのは1行に入らないときだけ。割る所は、空白・中黒・括弧の前後か、字の種類が変わる所（漢字のあとの送り仮名は除く）
  // を選び、2行の幅がなるべくそろう所にする。1字だけの行は作らない。割れない長い語は、1行のまま札を広げる
  function lines(label) {
    const s = String(label || ""), chars = [...s];
    if (uw(s) <= CUT) return [s];
    let best = -1, bestScore = Infinity, bestNatural = false;
    for (let i = 2; i <= chars.length - 2; i++) {
      const a = chars.slice(0, i).join(""), b = chars.slice(i).join("");
      const c1 = chars[i - 1], c2 = chars[i], k1 = kindOf(c1), k2 = kindOf(c2);
      const natural = " ・／/（(".includes(c2) || " ・／/、）)".includes(c1) || (k1 !== k2 && !(k1 === "x" && k2 === "h"));
      // 語の切れ目なら1行目を4割まで広げてよい（「コンテキストウィンドウ／外の忘却」）。語の途中は CUT まで
      if (NOSTART.test(b) || uw(a) > (natural ? CUT * 1.4 : CUT)) continue;
      const score = Math.abs(uw(a) - uw(b)) + (natural ? 0 : 8) + Math.max(0, uw(b) - CUT * 1.4) * 4;
      if (score < bestScore) { bestScore = score; best = i; bestNatural = natural; }
    }
    // 割る所が語の途中しか無く、1.6倍までの幅に入るなら割らない（「ハルシネーショ／ン」のような折れ方をしない）
    if (best < 0 || (!bestNatural && uw(s) <= CUT * 1.6)) return [uw(s) > CUT * 2.2 ? chars.slice(0, Math.floor(CUT * 2)).join("") + "…" : s];
    const a = chars.slice(0, best).join("");
    let b = chars.slice(best);
    if (uw(b.join("")) > CUT * 1.4) {   // 2行目も入らなければ、末尾を「…」にする
      while (b.length > 2 && uw(b.join("") + "…") > CUT * 1.4) b = b.slice(0, -1);
      b = [...b, "…"];
    }
    return [a, b.join("")];
  }

  function nodeBox(x, y, label, cls, center) {
    const ls = lines(label);
    const fs = center ? 15 : 12.5;
    const w = Math.max(...ls.map(uw)) * fs * 1.04 + (center ? 34 : 22);
    const h = ls.length * fs * 1.35 + (center ? 18 : 12);
    return { w, h, ls, fs };
  }
  function boxSVG(x, y, b, center) {
    // 字の高さの真ん中を札の真ん中に置く（WebKit は dominant-baseline を tspan に引き継がないので、基線をずらして置く）
    const ty = y - (b.ls.length - 1) * b.fs * 0.675 + b.fs * 0.36;
    const text = b.ls.map((l, i) => `<tspan x="${x}" y="${(ty + i * b.fs * 1.35).toFixed(1)}">${esc(l)}</tspan>`).join("");
    return `<rect x="${x - b.w / 2}" y="${y - b.h / 2}" width="${b.w}" height="${b.h}" rx="${center ? 12 : 9}" class="n-box"/>` +
      `<text class="n-text" x="${x}" text-anchor="middle" style="font-size:${b.fs}px">${text}</text>`;
  }
  const overlapArea = (a, b) => Math.max(0, Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1)) * Math.max(0, Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1));
  const rectAt = (x, y, w, h, pad = 0) => ({ x1: x - w / 2 - pad, x2: x + w / 2 + pad, y1: y - h / 2 - pad, y2: y + h / 2 + pad });

  // 答えの札（tonari-map）→ 共通の形
  function fromBlock(m) {
    const pick = (arr, dir) => (arr || []).map((it) => typeof it === "string" ? { label: it } : it)
      .map((it) => ({ label: it.label, edge: dir === "opposite" ? (it.axis || "対") : dir === "related" ? (it.rel || "関係") : REL_WORD[dir],
        why: it.why || it.axis || "", src: srcKind(it.src), state: it.state || null, rstate: null }));
    return {
      center: { label: m.center, gist: m.gist, src: srcKind(m.src), state: null },
      broader: pick(m.broader, "broader"), narrower: pick(m.narrower, "narrower"),
      opposite: pick(m.opposite, "opposite"), related: pick(m.related, "related"),
      examples: m.examples || [], nonexamples: m.nonexamples || [],
    };
  }

  // 記録の地図（ego）→ 共通の形
  function fromEgo(e) {
    const pick = (arr, dir) => (arr || []).map((n) => ({ id: n.id, rid: n.rid, label: n.label,
      edge: dir === "opposite" ? (n.detail || "対") : dir === "related" ? (n.detail || "関係") : REL_WORD[dir],
      why: n.why || "", src: n.src_kind || "inferred", state: n.state, rstate: n.rstate }));
    return {
      center: { id: e.center.id, label: e.center.label, gist: e.center.gist, src: srcKind(e.center.gist_src), state: e.center.state },
      broader: pick(e.broader, "broader"), narrower: pick(e.narrower, "narrower"),
      opposite: pick(e.opposite, "opposite"), related: pick(e.related, "related"),
      examples: (e.examples || []).map((n) => n.label), nonexamples: (e.nonexamples || []).map((n) => n.label),
    };
  }

  // states: { "概念の名前": "known" | "shaky" | "unknown" }（答えの札には状態が無いので、記録から重ねる）
  function render(model, opts = {}) {
    ({ W, H, CX, CY, SLOTS, cut: CUT } = LAYOUTS[opts.compact ? "compact" : "wide"]);
    const states = opts.states || {};
    const st = (n) => n.state || states[n.label] || null;
    let edges = "", nodes = "", labels = "";
    const c = model.center;
    // 置く札を決める: 同じ概念（畳んだ字が同じ）は、中心・上位・下位・対・関係の順で最初の1つだけにまとめる
    const fold = (s) => String(s || "").normalize("NFKC").toLowerCase().replace(/\s+/g, "");
    const seen = new Set([fold(c.label)]);
    const placed = [];
    for (const dir of ["broader", "narrower", "opposite", "related"]) {
      for (const n of model[dir] || []) {
        const f = fold(n.label);
        if (!f || seen.has(f)) continue;
        if (placed.filter((p) => p.dir === dir).length >= SLOTS[dir].length) continue;
        seen.add(f);
        const [x, y] = SLOTS[dir][placed.filter((p) => p.dir === dir).length];
        placed.push({ n, dir, x, y, b: nodeBox(x, y, n.label, "", false) });
      }
    }
    CUT += 2;   // 中心の札は大きいので、1行に2字多く入れる
    const cb = nodeBox(CX, CY, c.label, "", true);
    CUT -= 2;
    // 札どうしが重なれば、中心から遠いほうを横（同じ段）か縦に押し出す。絵の外には出さない
    const clamp = (p) => {
      p.x = Math.min(Math.max(p.x, p.b.w / 2 + 4), W - p.b.w / 2 - 4);
      p.y = Math.min(Math.max(p.y, p.b.h / 2 + 4), H - p.b.h / 2 - 4);
    };
    const all = [{ x: CX, y: CY, b: cb, fixed: true }, ...placed];
    // 同じ段に並ぶ札の幅の合計が絵の幅に入らなければ、1つおきに中心の側へずらす（押し合いで行き来しないように）
    const rows = {};
    for (const p of placed) (rows[p.y] ||= []).push(p);
    for (const row of Object.values(rows)) {
      if (row.length < 2 || row.reduce((s, p) => s + p.b.w + 8, 0) <= W - 8) continue;
      const hmax = Math.max(...row.map((p) => p.b.h));
      row.sort((a, b) => a.x - b.x).forEach((p, i) => { if (i % 2 === 1) p.y += (p.y > CY ? -1 : 1) * (hmax + 10); });
    }
    placed.forEach(clamp);
    for (let round = 0; round < 12; round++) {
      let moved = false;
      for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
        const p = all[i], q = all[j];
        const ox = (p.b.w + q.b.w) / 2 + 8 - Math.abs(p.x - q.x), oy = (p.b.h + q.b.h) / 2 + 6 - Math.abs(p.y - q.y);
        if (ox <= 0 || oy <= 0) continue;
        const far = p.fixed ? q : q.fixed ? p : Math.hypot(p.x - CX, p.y - CY) >= Math.hypot(q.x - CX, q.y - CY) ? p : q;
        const near = far === p ? q : p;
        const left = () => [(p.b.w + q.b.w) / 2 + 8 - Math.abs(p.x - q.x), (p.b.h + q.b.h) / 2 + 6 - Math.abs(p.y - q.y)];
        const push = (a, b, dx, dy) => {   // a を b から離す（横か縦）。絵の端で止まったら、そこまで
          if (dx > 0) a.x += (a.x >= b.x ? 1 : -1) * dx;
          if (dy > 0) a.y += (Math.abs(a.y - b.y) < 1 ? (a.y > CY ? -1 : 1) : a.y > b.y ? 1 : -1) * dy;   // 同じ段なら中心の側へ
          clamp(a);
        };
        if (ox < oy * 2.5) push(far, near, ox, 0);
        let [rx, ry] = left();
        if (rx > 0 && ry > 0 && !near.fixed && ox < oy * 2.5) push(near, far, rx, 0);   // 端で止まったら近いほうも譲る
        [rx, ry] = left();
        if (rx > 0 && ry > 0) push(far, near, 0, ry);                                  // それでも重なれば縦に押す
        moved = true;
      }
      if (!moved) break;
    }
    // 線の名前の札: 線の上で、札にも、先に置いた名前の札にも重ならない所を探す（対の軸は相手の札の下か上から）
    const blocks = all.map((p) => rectAt(p.x, p.y, p.b.w, p.b.h, 3));
    for (const p of placed) {
      const { n, dir, x, y } = p;
      const ek = `e-${n.src}` + (n.rstate ? ` r-${n.rstate}` : "");
      edges += `<line x1="${CX}" y1="${CY}" x2="${x}" y2="${y}" class="edge ${ek}"/>`;
      const word = String(n.edge || "").slice(0, 14), lw = uw(word) * 10.5 + 14, lh = 18;
      const cands = (dir === "opposite" ? [[x, y + p.b.h / 2 + 13], [x, y - p.b.h / 2 - 13]] : [])
        .concat([0.5, 0.42, 0.58, 0.34, 0.66, 0.27, 0.73].map((t) => [CX + (x - CX) * t, CY + (y - CY) * t]));
      let best = null, bestA = Infinity;
      for (const [mx, my] of cands) {
        const r = rectAt(mx, my, lw, lh);
        if (r.x1 < 0 || r.x2 > W || r.y1 < 0 || r.y2 > H) continue;
        const a = blocks.reduce((s, q) => s + overlapArea(r, q), 0);
        if (a < bestA) { bestA = a; best = [mx, my]; }
        if (a === 0) break;
      }
      const [mx, my] = best || [(CX + x) / 2, (CY + y) / 2];
      blocks.push(rectAt(mx, my, lw, lh, 2));
      labels += `<g class="e-label"><rect x="${mx - lw / 2}" y="${my - lh / 2}" width="${lw}" height="${lh}" rx="9"/>` +
        `<text x="${mx}" y="${my + 0.5}" dominant-baseline="middle" text-anchor="middle">${esc(word)}</text></g>`;
      const s = st(n);
      nodes += `<g class="node d-${dir}${s ? " s-" + s : ""}" data-label="${esc(n.label)}"${n.id ? ` data-id="${n.id}"` : ""}${n.rid ? ` data-rid="${n.rid}"` : ""} tabindex="0" role="button" aria-label="${esc(n.label)}（${esc(n.edge)}）">` +
        `<title>${esc(n.label)}${n.why ? "：" + esc(n.why) : ""}</title>${boxSVG(x, y, p.b, false)}</g>`;
    }
    const cs = st(c);
    nodes += `<g class="node center${cs ? " s-" + cs : ""}" data-label="${esc(c.label)}"${c.id ? ` data-id="${c.id}"` : ""} tabindex="0" role="button" aria-label="中心: ${esc(c.label)}">` +
      `<title>${esc(c.label)}${c.gist ? "：" + esc(c.gist) : ""}</title>${boxSVG(CX, CY, cb, true)}</g>`;
    // 方角の目印（置き場所の意味を覚えるための薄い字）
    const guide = opts.compact ? "" : `<g class="guide"><text x="${W - 10}" y="22" text-anchor="end">↑ 上位（広い）</text>` +
      `<text x="${W - 10}" y="${H - 10}" text-anchor="end">↓ 下位（狭い・具体）</text>` +
      `<text x="10" y="${CY - 34}">← 対 →</text><text x="10" y="22">↖ 関係 ↗</text></g>`;
    const empty = !["broader", "narrower", "opposite", "related"].some((d) => (model[d] || []).length);
    return `<svg viewBox="0 0 ${W} ${H}" class="cmap-svg${empty ? " is-empty" : ""}" role="img" aria-label="${esc(c.label)} の位置の図">` +
      guide + edges + labels + nodes + `</svg>`;
  }

  function chips(model) {
    const ex = (model.examples || []).map((x) => `<span class="chip ex">${esc(x)}</span>`).join("");
    const nx = (model.nonexamples || []).map((x) => `<span class="chip nx">${esc(x)}</span>`).join("");
    if (!ex && !nx) return "";
    return `<div class="cmap-chips">${ex ? `<span class="cmap-k">例</span>${ex}` : ""}${nx ? `<span class="cmap-k">例ではない</span>${nx}` : ""}</div>`;
  }

  function legend() {
    return `<div class="cmap-legend"><span><i class="lg solid"></i>棚に根拠</span><span><i class="lg dash"></i>一般の知識</span>` +
      `<span><i class="lg dot"></i>推測</span><span><i class="lg sw s-known"></i>分かる</span><span><i class="lg sw s-shaky"></i>あやしい</span>` +
      `<span><i class="lg sw s-unknown"></i>分からない</span></div>`;
  }

  window.TonariMap = { fromBlock, fromEgo, render, chips, legend };
})();
