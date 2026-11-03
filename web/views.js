// となり — 答えの中の図（見せ方の語彙）。どの図も同じ見た目の決まりで描く:
// 上に表現の名前（1〜2語）と、その形にした中身の構造の理由。初めて見る形には読み方を1行。
// 札の箱・出どころの線の種類（実線＝棚・破線＝一般・点線＝推測）・確かでない所の一人称の言葉は、位置の図と共通。
// 研究 c（tonari/research/c-表現の選び方-2026-10.md）: 矢印は時間と因果の流れ（流れ・分岐）にだけ使う。
// 重なりはオイラー図（2つ）か線形の図（3つ）で、空の領域は描かない。比較の表は共通の行が先。
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const M = window.TonariMap;

  const READ = {
    decide: "上の問いから順に答えて枝をたどると、結論に着きます。",
    timeline: "左から右へ時間が進みます。帯は続いている期間、縦の線は出来事です。",
    flow: "矢印は進む順です。上の名前は段階のまとまりです。",
    compare: "上の行が共通点、「決め手」の付いた行がいちばん大きな違いです。",
    overlap: "重なっている所は両方に当てはまり、外側はどちらか一方だけです。",
    calc: "式に数字を入れて、上から一段ずつ計算します。",
    analogy: "左がよく知っているもの、右が学ぶもの。下の欄は、たとえが成り立たない所です。",
    tree: "上が大きな分類で、下へ行くほど細かくなります。",
    map: "上は広い言葉、下は具体的な言葉、左右は比べる相手、斜めはつながる言葉です。",
    mermaid: "箱が物事、線がそのつながりです。",
  };
  const NUMBERS = { example: "例の数字", unverified: "確かめていない数字" };

  function frame(v, body, opts) {
    const read = opts.firstTime && READ[v.type] ? `<p class="v-read">${READ[v.type]}</p>` : "";
    const num = v.numbers && NUMBERS[v.numbers] ? `<span class="v-num n-${v.numbers}">${NUMBERS[v.numbers]}</span>` : "";
    return `<figure class="view v-${v.type}" data-type="${v.type}">` +
      `<figcaption class="v-head"><span class="v-name">${esc(v.name)}</span>${v.why ? `<span class="v-why">${esc(v.why)}</span>` : ""}${num}</figcaption>` +
      read + `<div class="v-body">${body}</div></figure>`;
  }

  const unsure = (u) => (u ? `<em class="v-unsure">${esc(u)}</em>` : "");

  // ── 分岐の木 ──
  function decideNode(n) {
    if (n.result !== undefined) {
      return `<div class="dt-res src-${esc(n.src || "inferred")}"><b>${esc(n.result)}</b>${n.note ? `<small>${esc(n.note)}</small>` : ""}${unsure(n.unsure)}</div>`;
    }
    return `<div class="dt-node"><div class="dt-ask">${esc(n.ask)}${unsure(n.unsure)}</div><div class="dt-brs">` +
      n.branches.map((b) => `<div class="dt-br"><span class="dt-lab">${esc(b.label)}</span>${decideNode(b.node)}</div>`).join("") +
      `</div></div>`;
  }
  function decide(v) {
    return (v.q ? `<p class="dt-q">${esc(v.q)}</p>` : "") + `<div class="dt">${decideNode(v.root)}</div>`;
  }

  // ── 時間軸 ──
  function niceStep(span) {
    const raw = span / 6, p = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const k of [1, 2, 5, 10]) if (raw <= k * p) return k * p;
    return 10 * p;
  }
  function timeline(v) {
    const W = 680, L = 128, R = 16, lanes = v.lanes || [], marks = v.marks || [];
    const top = marks.length ? 34 : 14, laneH = 34, H = top + lanes.length * laneH + 34;
    const sx = (x) => L + (W - L - R) * (x - v.from) / (v.to - v.from);
    const step = niceStep(v.to - v.from);
    let h = "";
    for (let t = Math.ceil(v.from / step) * step; t <= v.to + 1e-9; t += step) {
      h += `<line class="tl-grid" x1="${sx(t)}" y1="${top - 6}" x2="${sx(t)}" y2="${H - 26}"/>` +
        `<text class="tl-tick" x="${sx(t)}" y="${H - 10}" text-anchor="middle">${+t.toFixed(2)}${esc(v.unit || "")}</text>`;
    }
    lanes.forEach((ln, i) => {
      const y = top + i * laneH + laneH / 2;
      h += `<text class="tl-lane" x="0" y="${y + 4}">${esc(ln.label)}</text>`;
      for (const sp of ln.spans) {
        const x = sx(sp.from), w = Math.max(3, sx(sp.to) - x);
        h += `<rect class="tl-span" x="${x}" y="${y - 11}" width="${w}" height="22" rx="6"><title>${esc(ln.label)} ${sp.from}〜${sp.to}${esc(v.unit || "")}</title></rect>`;
        const lab = sp.label || `${+sp.from}〜${+sp.to}${v.unit || ""}`;
        if (w > lab.length * 11 + 12) h += `<text class="tl-span-t" x="${x + w / 2}" y="${y + 4}" text-anchor="middle">${esc(lab)}</text>`;
      }
    });
    marks.forEach((m, i) => {
      const x = sx(m.at);
      h += `<line class="tl-mark" x1="${x}" y1="${top - 8}" x2="${x}" y2="${H - 26}"/>` +
        `<text class="tl-mark-t" x="${x}" y="${12 + (i % 2) * 13}" text-anchor="middle">${esc(m.label)}</text>`;
    });
    return `<div class="v-scroll"><svg class="tl-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(v.name)}">${h}</svg></div>`;
  }

  // ── 流れ ──
  function flow(v) {
    let html = "", lastGroup = null;
    v.steps.forEach((s, i) => {
      const g = s.group && s.group !== lastGroup ? `<span class="fl-group">${esc(s.group)}</span>` : "";
      lastGroup = s.group || lastGroup;
      html += `<li class="fl-step">${g}<span class="fl-n">${i + 1}</span><b>${esc(s.label)}</b>${s.note ? `<small>${esc(s.note)}</small>` : ""}${unsure(s.unsure)}</li>`;
    });
    return `<ol class="fl">${html}</ol>`;
  }

  // ── 比較の表 ──
  function compare(v) {
    const n = v.items.length;
    const head = `<tr><th>観点</th>${v.items.map((x) => `<th>${esc(x)}</th>`).join("")}</tr>`;
    const rows = v.rows.map((r) => "same" in r
      ? `<tr class="cp-same"><td>${esc(r.axis)}<span class="cp-tag">共通</span></td><td colspan="${n}">${esc(r.same)}</td></tr>`
      : `<tr class="${r.key ? "cp-key" : ""}"><td>${esc(r.axis)}${r.key ? `<span class="cp-tag key">決め手</span>` : ""}${unsure(r.unsure)}</td>${r.values.map((x) => `<td>${esc(x)}</td>`).join("")}</tr>`).join("");
    return `<div class="v-scroll"><table class="cp"><thead>${head}</thead><tbody>${rows}</tbody></table></div>`;
  }

  // ── 重なりの図（2つはオイラー図、3つは線形の図）──
  function regionList(items, x, y, anchor) {
    const shown = items.slice(0, 5), more = items.length - shown.length;
    return shown.map((it, i) => `<text class="ov-it" x="${x}" y="${y + i * 17}" text-anchor="${anchor}">${esc(it)}</text>`).join("") +
      (more > 0 ? `<text class="ov-more" x="${x}" y="${y + shown.length * 17}" text-anchor="${anchor}">ほか${more}つ</text>` : "");
  }
  function overlap(v) {
    if (v.sets.length === 3) return linear(v);
    const A = v.elements.filter((e) => e.in.length === 1 && e.in[0] === 0).map((e) => e.label);
    const B = v.elements.filter((e) => e.in.length === 1 && e.in[0] === 1).map((e) => e.label);
    const AB = v.elements.filter((e) => e.in.length === 2).map((e) => e.label);
    const W = 620, H = 250, cy = 128;
    let h = "";
    const label = (x, y, t, a) => `<text class="ov-set" x="${x}" y="${y}" text-anchor="${a}">${esc(t)}</text>`;
    if (!AB.length) {          // 交わらない
      h += `<circle class="ov-c a" cx="165" cy="${cy}" r="105"/><circle class="ov-c b" cx="455" cy="${cy}" r="105"/>` +
        label(165, 16, v.sets[0], "middle") + label(455, 16, v.sets[1], "middle") +
        regionList(A, 165, cy - 26, "middle") + regionList(B, 455, cy - 26, "middle");
    } else if (!A.length || !B.length) {   // 片方がもう片方に含まれる
      const inner = !A.length ? 0 : 1, outer = 1 - inner;
      const innerItems = AB, outerItems = inner === 0 ? B : A;
      h += `<ellipse class="ov-c ${outer ? "b" : "a"}" cx="310" cy="${cy}" rx="290" ry="112"/>` +
        `<ellipse class="ov-c ${inner ? "b" : "a"}" cx="215" cy="${cy}" rx="150" ry="80"/>` +
        label(310, 12, v.sets[outer], "middle") + label(215, cy - 88, v.sets[inner], "middle") +
        regionList(innerItems, 215, cy - 22, "middle") + regionList(outerItems, 480, cy - 30, "middle");
    } else {                    // 一部が重なる
      h += `<circle class="ov-c a" cx="230" cy="${cy}" r="112"/><circle class="ov-c b" cx="390" cy="${cy}" r="112"/>` +
        label(190, 12, v.sets[0], "middle") + label(430, 12, v.sets[1], "middle") +
        regionList(A, 170, cy - 26, "middle") + regionList(AB, 310, cy - 26, "middle") + regionList(B, 450, cy - 26, "middle");
    }
    return `<div class="v-scroll"><svg class="ov-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(v.name)}">${h}</svg></div>`;
  }
  function linear(v) {
    const els = [...v.elements].sort((a, b) => a.in.join(",").localeCompare(b.in.join(",")));
    const head = `<tr><th></th>${els.map((e) => `<th class="ln-el"><span>${esc(e.label)}</span></th>`).join("")}</tr>`;
    const rows = v.sets.map((s, i) => `<tr><th class="ln-set">${esc(s)}</th>${els.map((e) => `<td class="${e.in.includes(i) ? `on s${i}` : ""}"></td>`).join("")}</tr>`).join("");
    return `<div class="v-scroll"><table class="ln">${head}${rows}</table></div>`;
  }

  // ── 計算の例 ──
  function calc(v) {
    const vars = v.vars.length ? `<table class="cc-vars">${v.vars.map((x) => `<tr><td>${esc(x.name)}</td><td class="num">${esc(x.value)}</td><td>${esc(x.note)}</td></tr>`).join("")}</table>` : "";
    const steps = v.steps.length ? `<ol class="cc-steps">${v.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : "";
    return (v.title ? `<p class="cc-title">${esc(v.title)}</p>` : "") +
      (v.formula ? `<p class="cc-formula">${esc(v.formula)}</p>` : "") + vars + steps +
      `<p class="cc-result"><span>答え</span>${esc(v.result)}</p>`;
  }

  // ── たとえ ──
  function analogy(v) {
    return `<div class="an"><div class="an-h">${esc(v.source)}</div><div></div><div class="an-h">${esc(v.target)}</div>` +
      v.pairs.map((p) => `<div class="an-s">${esc(p.s)}</div><div class="an-eq" aria-hidden="true">↔</div><div class="an-t">${esc(p.t)}</div>`).join("") +
      `</div><div class="an-breaks"><b>たとえが成り立たない所</b>${v.breaks.map((b) => `<p>${esc(b)}</p>`).join("")}</div>`;
  }

  // ── 階層の木 ──
  function treeNode(node, depth) {
    const kids = (node.children || []).slice(0, 8).map((k) => `<li>${treeNode(k, depth + 1)}</li>`).join("");
    const label = node.root || node.label;
    return `<button class="tree-n d${depth}" data-ask="${esc(label)}">${esc(label)}${node.note ? `<small>${esc(node.note)}</small>` : ""}</button>` +
      (kids && depth < 3 ? `<ul>${kids}</ul>` : "");
  }
  function tree(v) { return `<div class="tree"><ul><li>${treeNode(v, 0)}</li></ul></div>`; }

  // ── 位置の図 ──
  function map(v, opts) {
    const model = M.fromBlock(v);
    return M.render(model, { states: opts.states || {} }) + (v.gist ? `<p class="mp-gist"><b>${esc(v.center)}</b>：${esc(v.gist)}</p>` : "") + M.chips(model);
  }

  function mermaid(v) { return `<pre class="mermaid-src">${esc(v.code)}</pre>`; }

  const R = { decide, timeline, flow, compare, overlap, calc, analogy, tree, map, mermaid };

  function render(v, opts = {}) {
    const f = R[v.type];
    if (!f) return "";
    try { return frame(v, f(v, opts), opts); } catch (e) { return ""; }
  }

  window.TonariViews = { render, READ };
})();
