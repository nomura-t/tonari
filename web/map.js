// となり — 概念の位置の図（SVG）。置き場所に意味を固定する: 上=上位概念、下=下位概念、左右=対の概念、斜め=関係する概念。
// 毎回同じ規則で置くので、図を何枚見ても「上にあるのは広いほう」と読める（配置の一貫性）。
// 入力は2つの形を受ける。答えの札（tonari-map の JSON）と、記録の地図（/api/concepts/:id/ego）。
(function () {
  // 置き場所は2組。広い（答えの中・680×420）と、狭い（右の地図・400×440。縮めても字が小さくならないように）
  const LAYOUTS = {
    wide: { W: 680, H: 420, CX: 340, CY: 210, cut: 9, SLOTS: {
      broader: [[340, 52], [190, 52], [490, 52]],
      narrower: [[340, 368], [190, 368], [490, 368], [60, 368], [620, 368]],
      opposite: [[590, 210], [90, 210]],
      related: [[175, 128], [505, 128], [175, 292], [505, 292], [60, 128], [620, 292]],
    } },
    compact: { W: 400, H: 460, CX: 200, CY: 230, cut: 7, SLOTS: {
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

  // 和文は空白で切れないので、字数で2行に割る（9字まで×2行、超えたら…）
  function lines(label) {
    const s = String(label || "");
    if (s.length <= CUT) return [s];
    const a = s.slice(0, CUT), b = s.slice(CUT);
    return [a, b.length > CUT ? b.slice(0, CUT - 1) + "…" : b];
  }

  function nodeBox(x, y, label, cls, center) {
    const ls = lines(label);
    const fs = center ? 15 : 12.5;
    const w = Math.max(...ls.map((l) => l.length)) * fs * 1.02 + (center ? 34 : 22);
    const h = ls.length * fs * 1.35 + (center ? 18 : 12);
    const ty = y - (ls.length - 1) * fs * 0.675;
    const text = ls.map((l, i) => `<tspan x="${x}" y="${ty + i * fs * 1.35}">${esc(l)}</tspan>`).join("");
    return { w, h, svg: `<rect x="${x - w / 2}" y="${y - h / 2}" width="${w}" height="${h}" rx="${center ? 12 : 9}" class="n-box"/>` +
      `<text class="n-text" dominant-baseline="middle" text-anchor="middle" style="font-size:${fs}px">${text}</text>` };
  }

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
    for (const dir of ["broader", "narrower", "opposite", "related"]) {
      (model[dir] || []).slice(0, SLOTS[dir].length).forEach((n, i) => {
        const [x, y] = SLOTS[dir][i];
        const ek = `e-${n.src}` + (n.rstate ? ` r-${n.rstate}` : "");
        edges += `<line x1="${CX}" y1="${CY}" x2="${x}" y2="${y}" class="edge ${ek}"/>`;
        // 対の軸の言葉は長くなりやすく、中心との間に収まらないので、相手の札の下に置く
        const under = dir === "opposite";
        const mx = under ? x : (CX + x) / 2, my = under ? y + 30 : (CY + y) / 2;
        const word = String(n.edge || "").slice(0, 10);
        labels += `<g class="e-label"><rect x="${mx - word.length * 5.6 - 6}" y="${my - 9}" width="${word.length * 11.2 + 12}" height="18" rx="9"/>` +
          `<text x="${mx}" y="${my + 0.5}" dominant-baseline="middle" text-anchor="middle">${esc(word)}</text></g>`;
        const b = nodeBox(x, y, n.label, "", false);
        const s = st(n);
        nodes += `<g class="node d-${dir}${s ? " s-" + s : ""}" data-label="${esc(n.label)}"${n.id ? ` data-id="${n.id}"` : ""}${n.rid ? ` data-rid="${n.rid}"` : ""} tabindex="0" role="button" aria-label="${esc(n.label)}（${esc(n.edge)}）">` +
          `<title>${esc(n.label)}${n.why ? "：" + esc(n.why) : ""}</title>${b.svg.replace('<text ', `<text x="${x}" `)}</g>`;
      });
    }
    CUT += 2;   // 中心の札は大きいので、1行に2字多く入れる
    const cb = nodeBox(CX, CY, c.label, "", true);
    const cs = st(c);
    nodes += `<g class="node center${cs ? " s-" + cs : ""}" data-label="${esc(c.label)}"${c.id ? ` data-id="${c.id}"` : ""} tabindex="0" role="button" aria-label="中心: ${esc(c.label)}">` +
      `<title>${esc(c.label)}${c.gist ? "：" + esc(c.gist) : ""}</title>${cb.svg.replace('<text ', `<text x="${CX}" `)}</g>`;
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
