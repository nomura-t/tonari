// となり — 概念の位置の図（v0.5 から HTML）。置き場所に意味を固定する: 上=中心より広い言葉、下=中心の種類、
// 横=取り違えやすい相手、中心の箱の中=中心の部品。そのほかの関係は下に1行ずつの文で出す。
// 毎回同じ規則で置くので、図を何枚見ても「上にあるのは広いほう」と読める（配置の一貫性）。
// 入力は2つの形を受ける。答えの札（tonari-map の JSON）と、記録の地図（/api/concepts/:id/ego）。
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function srcKind(src) {
    const s = String(src || "");
    if (/〔[A-Za-z0-9_-]{6,64}/.test(s)) return "shelf";
    if (s.startsWith("一般")) return "general";
    return "inferred";
  }

  // つなぐ言葉が無い関係（v0.5 より前の記録）は、関係の種類と向きから言葉を作る。out＝中心から相手へ書かれた関係。
  // 「同時に出る」「似ている」は種類の名前だけでは中身が分からないので、理由（why）を文として出す
  const LINK_OUT = { "前提": "が先に要る", "原因": "が原因で起きる", "結果": "を結果として生む", "道具": "を道具として使う" };
  const LINK_IN = { "部分": "の部品のひとつ", "前提": "の前提になる", "原因": "を引き起こす", "結果": "の結果として起きる", "道具": "の道具として使われる" };
  const VAGUE = { "同時に出る": "と一緒に出てくる", "似ている": "と似ている" };

  // related の1つを、部品（中心の中に描く）か、文（主語・相手・つなぐ言葉）に分ける
  function relate(n, center) {
    const rel = String(n.rel || "").trim(), out = n.out !== false;
    if (out && rel === "部分") return { part: true };
    if (n.phrase) return out ? { subj: center, obj: n.label, link: n.phrase, node: "obj" } : { subj: n.label, obj: center, link: n.phrase, node: "subj" };
    const link = (out ? LINK_OUT : LINK_IN)[rel] || VAGUE[rel] || "とつながる";
    return { subj: center, obj: n.label, link, node: "obj", vague: !(out ? LINK_OUT : LINK_IN)[rel] };
  }

  // 答えの札（tonari-map の JSON）→ 共通の形
  function fromBlock(m) {
    const pick = (arr, dir) => (arr || []).map((it) => typeof it === "string" ? { label: it } : it)
      .map((it) => ({ label: it.label, axis: it.axis || "", rel: it.rel || "", phrase: it.link || "", out: true,
        why: it.why || "", src: srcKind(it.src), state: it.state || null, rstate: null, dir }));
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
      axis: dir === "opposite" ? (n.detail || "") : "", rel: dir === "related" ? (n.detail || "") : "", phrase: n.phrase || "",
      out: n.out !== false, why: n.why || "", src: n.src_kind || "inferred", state: n.state, rstate: n.rstate, dir }));
    return {
      center: { id: e.center.id, label: e.center.label, gist: e.center.gist, src: srcKind(e.center.gist_src), state: e.center.state },
      broader: pick(e.broader, "broader"), narrower: pick(e.narrower, "narrower"),
      opposite: pick(e.opposite, "opposite"), related: pick(e.related, "related"),
      examples: (e.examples || []).map((n) => n.label), nonexamples: (e.nonexamples || []).map((n) => n.label),
    };
  }

  const CAP = { broader: 3, narrower: 6, opposite: 2, parts: 8, links: 8 };
  const RSTATE = { known: ["✓", "この関係は確かめ済み"], shaky: ["△", "この関係はあやしい"], unknown: ["?", "この関係は分からない"] };

  // 位置の図（v0.5）。線の名前（上位・部分・同時に出る）を札にして放射に置く形をやめ、どの関係も
  // 「中心＋つなぐ言葉＋相手」の文として読める形にする（研究 f3: コンセプトマップの命題）。置き場所の意味は残す:
  // 上＝中心より広い言葉、下＝中心の種類、横＝取り違えやすい相手、中心の箱の中＝中心の部品。
  // そのほかの関係は、図の下に1行ずつの文で出す。states: { "概念の名前": "known" | "shaky" | "unknown" }
  function render(model, opts = {}) {
    const states = opts.states || {};
    const c = model.center, C = esc(c.label);
    const fold = (s) => String(s || "").normalize("NFKC").toLowerCase().replace(/\s+/g, "");
    const seen = new Set([fold(c.label)]);
    const uniq = (arr, cap) => (arr || []).filter((n) => { const f = fold(n.label); if (!f || seen.has(f)) return false; seen.add(f); return true; }).slice(0, cap);
    const node = (n, cls = "") => {
      const st = n.state || states[n.label] || null;
      return `<button class="node pm-n ${cls} e-${n.src || "inferred"}${st ? " s-" + st : ""}" data-label="${esc(n.label)}"` +
        `${n.id ? ` data-id="${n.id}"` : ""}${n.rid ? ` data-rid="${n.rid}"` : ""}${n.why ? ` title="${esc(n.why)}"` : ""}>${esc(n.label)}</button>`;
    };
    const mark = (n) => (n.rstate && RSTATE[n.rstate] ? `<i class="pm-rs r-${n.rstate}" title="${RSTATE[n.rstate][1]}">${RSTATE[n.rstate][0]}</i>` : "");
    const up = uniq(model.broader, CAP.broader), opp = uniq(model.opposite, CAP.opposite), down = uniq(model.narrower, CAP.narrower);
    const parts = [], links = [];
    for (const n of model.related || []) {
      const f = fold(n.label);
      if (!f || seen.has(f)) continue;
      const r = relate(n, c.label);
      if (r.part ? parts.length >= CAP.parts : links.length >= CAP.links) continue;
      seen.add(f);
      (r.part ? parts : links).push({ n, r });
    }
    const cst = c.state || states[c.label] || null;
    const centerBtn = `<button class="node pm-n pm-c${cst ? " s-" + cst : ""}" data-label="${C}"${c.id ? ` data-id="${c.id}"` : ""}>${C}</button>`;
    let h = "";
    if (up.length) {
      h += `<div class="pm-row pm-up"><span class="pm-k">広い言葉</span>${up.map((n) => node(n) + mark(n)).join("")}</div>` +
        `<p class="pm-say"><span class="pm-ar">↑</span><b>${C}</b> は、${up.length > 1 ? "これらの" : "この"}一種</p>`;
    }
    h += `<div class="pm-mid"><div class="pm-box">${centerBtn}` +
      (parts.length ? `<p class="pm-say in"><b>${C}</b> の中にあるもの（部品）</p><div class="pm-row pm-parts">${parts.map(({ n }) => node(n, "pm-part") + mark(n)).join("")}</div>` : "") +
      `</div>` +
      (opp.length ? `<div class="pm-opp"><span class="pm-k">取り違えやすい相手</span>${opp.map((n) =>
        `<div class="pm-o"><span class="pm-ar">⇄</span>${node(n)}${mark(n)}${n.axis ? `<small>違いは「${esc(n.axis)}」</small>` : ""}</div>`).join("")}</div>` : "") +
      `</div>`;
    if (down.length) {
      h += `<p class="pm-say"><span class="pm-ar">↓</span>${down.length > 1 ? "これらは" : "これは"}、<b>${C}</b> の一種</p>` +
        `<div class="pm-row pm-down"><span class="pm-k">種類</span>${down.map((n) => node(n) + mark(n)).join("")}</div>`;
    }
    if (links.length) {
      h += `<ul class="pm-links" aria-label="そのほかのつながり">` + links.map(({ n, r }) => {
        const S = r.node === "subj" ? node(n) : `<b>${esc(r.subj)}</b>`, O = r.node === "obj" ? node(n) : `<b>${esc(r.obj)}</b>`;
        // つなぐ言葉が中身を言わない関係（古い記録の「同時に出る」など）は、理由の文を主にする
        const why = n.why ? `<small class="${r.vague ? "pm-why main" : "pm-why"}">${esc(n.why)}</small>` : "";
        if (r.vague && n.why) return `<li>${S}<span class="pm-wa">と</span>${O}${mark(n)}${why}</li>`;
        return `<li>${S}<span class="pm-wa">は</span>${O}<span class="pm-link">${esc(r.link)}</span>${mark(n)}${why}</li>`;
      }).join("") + `</ul>`;
    }
    const empty = !(up.length || down.length || opp.length || parts.length || links.length);
    return `<div class="pm${opts.compact ? " compact" : ""}${empty ? " is-empty" : ""}" role="group" aria-label="${C} の位置の図">${h}</div>`;
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

  window.TonariMap = { fromBlock, fromEgo, render, chips, legend, relate };
})();
