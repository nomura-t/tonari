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
    parts: "箱が部品で、箱の中の箱はその中にある部品です。矢印は受け渡しで、丸の番号が起きる順です。下の一覧の行か丸を指すと、その矢印と両端の箱が光ります。",
    compare: "上の行が共通点、「決め手」の付いた行がいちばん大きな違いです。",
    overlap: "重なっている所は両方に当てはまり、外側はどちらか一方だけです。",
    calc: "式に数字を入れて、上から一段ずつ計算します。",
    analogy: "左がたとえの側、右が実際の名前、真ん中が両方に共通する働きです。番号と色は本文の同じ語と同じで、指すと相手が光ります。下の欄は、たとえが成り立たない所です。",
    tree: "上が大きな分類で、下へ行くほど細かくなります。",
    map: "上は広い言葉、下は具体的な言葉、左右は比べる相手、斜めはつながる言葉です。",
    mermaid: "箱が物事、線がそのつながりです。",
  };
  const NUMBERS = { example: "例の数字", unverified: "確かめていない数字" };
  const READ_CASE = { flow: "「例」の札は、上の実例がその段でどうなるかです。",
    parts: "一覧の「例」は、上の実例でそのやりとりに渡る実際の値です。" };

  // 図の札（v0.4）: たとえの持ち主と、判定役が確かめられなかった対応
  function tags(v) {
    if (v.type !== "analogy") return "";
    return (v.by === "user" ? `<span class="v-tag t-user">あなたのたとえ</span>` : "") +
      (v.checked === false ? `<span class="v-tag t-unchecked" title="判定役が対応を確かめられませんでした">確かめていない対応</span>` : "");
  }

  function frame(v, body, opts) {
    const read = opts.firstTime && READ[v.type] ? `<p class="v-read">${READ[v.type]}${v.case ? READ_CASE[v.type] || "" : ""}</p>` : "";
    const num = v.numbers && NUMBERS[v.numbers] ? `<span class="v-num n-${v.numbers}">${NUMBERS[v.numbers]}</span>` : "";
    // B4: 図を自分の言葉に訳す（押すと言い直し＝confirm として話し始める）。たとえの塊は図でないので付けない
    const say = v.type !== "analogy" && !opts.noSay ? `<div class="v-say"><button class="chip say" data-say="1">この図を自分の言葉で言う</button></div>` : "";
    return `<figure class="view v-${v.type}" data-type="${v.type}"${opts.vi != null ? ` data-vi="${opts.vi}"` : ""}>` +
      `<figcaption class="v-head"><span class="v-name">${esc(v.name)}</span>${v.why ? `<span class="v-why">${esc(v.why)}</span>` : ""}${num}${tags(v)}</figcaption>` +
      read + `<div class="v-body">${body}</div>${say}</figure>`;
  }
  // B3: 図のラベル（本文の『用語』と同じ字なら、指したときに相手を光らせる）。どの図も同じ印 data-lab を付ける
  const lab = (s) => ` data-lab="${esc(s)}"`;

  const unsure = (u) => (u ? `<em class="v-unsure">${esc(u)}</em>` : "");

  // ── 分岐の木 ──
  function decideNode(n) {
    if (n.result !== undefined) {
      return `<div class="dt-res src-${esc(n.src || "inferred")}"><b${lab(n.result)}>${esc(n.result)}</b>${n.note ? `<small>${esc(n.note)}</small>` : ""}${unsure(n.unsure)}</div>`;
    }
    return `<div class="dt-node"><div class="dt-ask"><span${lab(n.ask)}>${esc(n.ask)}</span>${unsure(n.unsure)}</div><div class="dt-brs">` +
      n.branches.map((b) => `<div class="dt-br"><span class="dt-lab"${lab(b.label)}>${esc(b.label)}</span>${decideNode(b.node)}</div>`).join("") +
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
      h += `<text class="tl-lane" x="0" y="${y + 4}"${lab(ln.label)}>${esc(ln.label)}</text>`;
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
        `<text class="tl-mark-t" x="${x}" y="${12 + (i % 2) * 13}" text-anchor="middle"${lab(m.label)}>${esc(m.label)}</text>`;
    });
    return `<div class="v-scroll"><svg class="tl-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(v.name)}">${h}</svg></div>`;
  }

  // ── 流れ（v0.4 の B1: 実例を1つ通すときは、上に実例の名前、各段の下に「例」の札） ──
  function flow(v) {
    let html = "", lastGroup = null;
    v.steps.forEach((s, i) => {
      const g = s.group && s.group !== lastGroup ? `<span class="fl-group">${esc(s.group)}</span>` : "";
      lastGroup = s.group || lastGroup;
      html += `<li class="fl-step">${g}<span class="fl-n">${i + 1}</span><b${lab(s.label)}>${esc(s.label)}</b>${s.note ? `<small>${esc(s.note)}</small>` : ""}` +
        `${s.ex ? `<span class="fl-ex"><i>例</i>${esc(s.ex)}</span>` : ""}${unsure(s.unsure)}</li>`;
    });
    return (v.case ? `<p class="fl-case"><span>通す実例</span>${esc(v.case)}</p>` : "") + `<ol class="fl">${html}</ol>`;
  }

  // ── しくみの絵（v0.4 作業B の B2）: 部品の箱と、番号つきの受け渡しの矢印。置き場所はここで決める ──
  // 横の並び（h）と縦の並び（v）の2枚を描き、幅で切り替える（app.css の @container）。座標は「主の軸 m」（上の段の
  // 部品が並ぶ向き）と「横の軸 c」で計算し、h は (x,y)=(m,c)、v は (x,y)=(c,m) に写す。入れ子の部品は親の箱の中に
  // 横の軸の向きに並べ、親の名前は横の軸の始まり（h は上・v は左）に置く。矢印は直角に折れる線だけで、
  //   隣の列どうし＝列の間の溝を通る（端の高さが同じならまっすぐ）、離れた列どうし＝行きは並びの手前・帰りは向こうの
  //   帯を通る（行きと帰りを上下にずらす）、同じ親の中の隣どうし＝子の箱の間、親と子＝親の内側の余白、を通る。
  // 1つの辺に複数の矢印が付くときは、辺の真ん中から 22px おきに並べる（箱は足りなければ伸ばす）。
  let ptSeq = 0;
  const PT = { SP: 22, LANE0: 22, LSP: 22, R: 9, FS: 13, NFS: 11, HEAD: 7 };
  const units = (s) => [...String(s || "")].reduce((n, ch) => n + (/[\x20-\x7e]/.test(ch) ? 0.62 : 1), 0);

  function partsLayout(v, H) {
    const { SP } = PT;
    const P = v.parts.map((p, i) => ({ ...p, i, kids: [], ports: { ms: [], me: [], cs: [], ce: [] }, nPC: 0, nSibM: 0 }));
    const byId = Object.fromEntries(P.map((p) => [p.id, p]));
    for (const p of P) if (p.in && byId[p.in]) { byId[p.in].kids.push(p); p.parent = byId[p.in]; }
    const tops = P.filter((p) => !p.parent);
    tops.forEach((t, k) => { t.col = k; t.kids.forEach((c, j) => { c.col = k; c.j = j; }); });
    // やりとりを通り道で分け、端の辺に付ける
    const L = v.links.map((l, k) => {
      const a = byId[l.from], b = byId[l.to], o = { ...l, k: k + 1, a, b };
      if (a.col !== b.col) {
        o.fwd = b.col > a.col;
        o.kind = Math.abs(b.col - a.col) === 1 ? "adj" : "lane";
        const g = o.kind === "lane" ? (o.fwd ? 0 : 2) : 1;
        a.ports[o.fwd ? "me" : "ms"].push({ o, g });
        b.ports[o.fwd ? "ms" : "me"].push({ o, g });
      } else if (a.parent && a.parent === b.parent) {
        const down = b.j > a.j;
        if (Math.abs(b.j - a.j) === 1) {
          o.kind = "sib";
          o.down = down;
          a.ports[down ? "ce" : "cs"].push({ o, g: 1 });
          b.ports[down ? "cs" : "ce"].push({ o, g: 1 });
          (down ? a : b).linkNext = true;
        } else {
          o.kind = "sibm";
          o.mi = a.parent.nSibM++;
          a.ports.me.push({ o, g: 1.5 });
          b.ports.me.push({ o, g: 1.5 });
        }
      } else {
        o.child = a.parent === b ? a : b;
        o.par = o.child.parent;
        if (o.child.j === 0) {   // 親と最初の子: 親の名前の下から子の箱へまっすぐ（間をあける）
          o.kind = "pc0";
          o.par.headGap = 40;
          o.child.ports.cs.push({ o, g: 1 });
        } else {                 // 親とそれより後の子: 親の内側の手前の余白を通る
          o.kind = "pc";
          o.mi = o.par.nPC++;
          o.child.ports.ms.push({ o, g: 0.5 });
        }
      }
      return o;
    });
    for (const p of P) for (const s of Object.values(p.ports)) s.sort((x, y) => x.g - y.g || x.o.k - y.o.k);
    // 大きさ（m と c の向きの長さ）
    const need = (n) => (n > 1 ? (n - 1) * SP + 28 : 0);
    const toA = (w, h) => (H ? { sm: w, sc: h } : { sm: h, sc: w });
    const sizeLeaf = (p) => {
      const a = toA(Math.max(68, Math.max(units(p.label) * PT.FS, units(p.note) * PT.NFS) + 28), 36 + (p.note ? 15 : 0));
      p.sm = Math.max(a.sm, need(Math.max(p.ports.cs.length, p.ports.ce.length)));
      p.sc = Math.max(a.sc, need(Math.max(p.ports.ms.length, p.ports.me.length)));
    };
    const kidGap = (k) => (k.linkNext ? 40 : 12);
    for (const t of tops) {
      t.kids.forEach(sizeLeaf);
      if (!t.kids.length) { sizeLeaf(t); continue; }
      const lw = Math.max(units(t.label) * PT.FS, units(t.note) * PT.NFS), lh = 18 + (t.note ? 15 : 0);
      t.padS = 14 + (t.nPC ? 4 + 24 * t.nPC : 0);   // 親と後の子の矢印は親の内側の手前の余白を通る（丸の番号が収まる幅）
      t.padE = 14 + (t.nSibM ? 4 + 24 * t.nSibM : 0); // 離れた兄弟の矢印は向こうの余白を通る
      t.headC = (H ? lh + 18 : lw + 26) + (t.headGap || 0);
      t.kidM = Math.max(...t.kids.map((c) => c.sm));
      const kidC = t.kids.reduce((s, c, j) => s + c.sc + (j < t.kids.length - 1 ? kidGap(c) : 0), 0);
      t.sm = Math.max(H ? lw + 30 : lh + 22, t.padS + t.kidM + t.padE);
      t.sc = Math.max(t.headC + kidC + 14, need(Math.max(t.ports.ms.length, t.ports.me.length)));
    }
    // c の置き場所: 上の段の部品は真ん中をそろえる。子は親の名前のあとに順に並べる
    const cRow = Math.max(...tops.map((t) => t.sc)) / 2;
    for (const t of tops) {
      t.c0 = cRow - t.sc / 2;
      let c = t.c0 + (t.headC || 0);
      for (const k of t.kids) { k.c0 = c; c += k.sc + kidGap(k); }
    }
    // 子を持たない上の段の部品は、やりとりの相手（親の中の子など）の高さにそろえる（矢印がまっすぐになりやすい）。
    // そろえるのは並びの帯（いちばん大きい箱の範囲）の中だけ
    const band = [cRow - Math.max(...tops.map((t) => t.sc)) / 2, cRow + Math.max(...tops.map((t) => t.sc)) / 2];
    for (let pass = 0; pass < 2; pass++) for (const t of tops) {
      if (t.kids.length) continue;
      const mates = L.filter((o) => o.a === t || o.b === t).map((o) => (o.a === t ? o.b : o.a)).filter((p) => p !== t);
      if (!mates.length) continue;
      const want = mates.reduce((s, p) => s + p.c0 + p.sc / 2, 0) / mates.length;
      t.c0 = Math.min(Math.max(want - t.sc / 2, band[0]), band[1] - t.sc);
    }
    // m の向きの辺（ms・me）の端の c。まず隣の列どうしの組を、2つの箱の重なる高さにそろえて置く（まっすぐな矢印）。
    // 残りは、空いている所に置く（手前の帯へ行く矢印は上から、向こうの帯へ行く矢印は下から、ほかは真ん中から）
    const ent = (p, side, o) => p.ports[side].find((x) => x.o === o);
    const far = (cs, c) => cs.every((x) => Math.abs(x - c) >= SP - 0.5);
    const groups = {};
    for (const o of L) if (o.kind === "adj") (groups[[o.a.i, o.b.i].sort().join("-")] ||= []).push(o);
    for (const grp of Object.values(groups)) {
      const o0 = grp[0], a = o0.a, b = o0.b, sa = o0.fwd ? "me" : "ms", sb = o0.fwd ? "ms" : "me";
      const lo = Math.max(a.c0, b.c0) + 9, hi = Math.min(a.c0 + a.sc, b.c0 + b.sc) - 9, n = grp.length;
      if (hi - lo < (n - 1) * SP) continue;
      const takenA = a.ports[sa].filter((x) => x.c != null).map((x) => x.c), takenB = b.ports[sb].filter((x) => x.c != null).map((x) => x.c);
      for (const shift of [0, SP, -SP, 2 * SP, -2 * SP]) {
        const mid = (lo + hi) / 2 + shift;
        const cs = grp.map((_, k) => mid + (k - (n - 1) / 2) * SP);
        if (cs[0] < lo - 0.5 || cs[n - 1] > hi + 0.5 || !cs.every((c) => far(takenA, c) && far(takenB, c))) continue;
        grp.forEach((o, k) => { ent(a, sa, o).c = ent(b, sb, o).c = cs[k]; });   // 帰り（b→a）も同じ辺どうし
        break;
      }
    }
    for (const p of P) for (const side of ["ms", "me"]) {
      const s = p.ports[side], lo = p.c0 + 10, hi = p.c0 + p.sc - 10, cc = p.c0 + p.sc / 2;
      const taken = s.filter((x) => x.c != null).map((x) => x.c);
      const cand = [];
      for (let k = -40; k <= 40; k++) { const c = cc + k * SP / 2; if (c >= lo - 0.5 && c <= hi + 0.5) cand.push(c); }
      for (const e of s) {
        if (e.c != null) continue;
        const pref = e.g < 1 ? [...cand].sort((x, y) => x - y) : e.g >= 2 ? [...cand].sort((x, y) => y - x)
          : [...cand].sort((x, y) => Math.abs(x - cc) - Math.abs(y - cc));
        const ok = pref.find((c) => far(taken, c));
        e.c = ok != null ? ok : pref.reduce((best, c) => (Math.min(...taken.map((x) => Math.abs(x - c))) > Math.min(...taken.map((x) => Math.abs(x - best))) ? c : best), pref[0] ?? cc);
        taken.push(e.c);
      }
    }
    for (const o of L) {
      if (o.kind === "adj" || o.kind === "lane") {
        o.ca = ent(o.a, o.fwd ? "me" : "ms", o).c;
        o.cb = ent(o.b, o.fwd ? "ms" : "me", o).c;
        o.straight = o.kind === "adj" && Math.abs(o.ca - o.cb) < 1;
      } else if (o.kind === "sibm") {
        o.ca = ent(o.a, "me", o).c;
        o.cb = ent(o.b, "me", o).c;
      } else if (o.kind === "pc") o.cc = ent(o.child, "ms", o).c;
    }
    // 列の間の溝: 折れる矢印の縦の線の数で幅を決め、線ごとに置き場所を分ける
    const gaps = Array.from({ length: Math.max(0, tops.length - 1) }, () => []);
    for (const o of L) {
      if (o.kind === "adj" && !o.straight) gaps[o.fwd ? o.a.col : o.a.col - 1].push({ o, end: "x" });
      if (o.kind === "lane") {
        gaps[o.fwd ? o.a.col : o.a.col - 1].push({ o, end: "a" });
        gaps[o.fwd ? o.b.col - 1 : o.b.col].push({ o, end: "b" });
      }
    }
    const gw = gaps.map((g) => Math.max(H ? 70 : 54, g.length * 16 + 34));
    let m = 0;
    tops.forEach((t, i) => { t.m0 = m; m += t.sm + (gw[i] || 0); });
    for (const t of tops) for (const k of t.kids) k.m0 = t.m0 + t.padS + (t.kidM - k.sm) / 2;
    gaps.forEach((g, i) => {
      const s = tops[i].m0 + tops[i].sm;
      g.forEach((x, j) => { x.o["slot_" + x.end] = s + gw[i] * (j + 1) / (g.length + 1); });
    });
    const portM = (p, side, o) => {
      const s = p.ports[side], i = s.findIndex((x) => x.o === o);
      return p.m0 + p.sm / 2 + (i - (s.length - 1) / 2) * SP;
    };
    // 通り道（m, c の点の列）
    const cMin = Math.min(...tops.map((t) => t.c0)), cMax = Math.max(...tops.map((t) => t.c0 + t.sc));
    let nf = 0, nb = 0;
    for (const o of L) {
      const a = o.a, b = o.b, m1 = (p) => p.m0 + p.sm, c1 = (p) => p.c0 + p.sc;
      if (o.kind === "adj" || o.kind === "lane") {
        const ea = o.fwd ? m1(a) : a.m0, eb = o.fwd ? b.m0 : m1(b);
        if (o.kind === "adj") {
          o.pts = o.straight ? [[ea, o.ca], [eb, o.cb]] : [[ea, o.ca], [o.slot_x, o.ca], [o.slot_x, o.cb], [eb, o.cb]];
        } else {
          const cl = o.fwd ? cMin - PT.LANE0 - PT.LSP * nf++ : cMax + PT.LANE0 + PT.LSP * nb++;
          o.pts = [[ea, o.ca], [o.slot_a, o.ca], [o.slot_a, cl], [o.slot_b, cl], [o.slot_b, o.cb], [eb, o.cb]];
        }
      } else if (o.kind === "sib") {
        const ma = portM(a, o.down ? "ce" : "cs", o), mb = portM(b, o.down ? "cs" : "ce", o);
        o.pts = o.down ? [[ma, c1(a)], [mb, b.c0]] : [[ma, a.c0], [mb, c1(b)]];
      } else if (o.kind === "sibm") {
        const mm = m1(a.parent) - 12 - 24 * o.mi;
        o.pts = [[m1(a), o.ca], [mm, o.ca], [mm, o.cb], [m1(b), o.cb]];
      } else if (o.kind === "pc0") {
        const mc = portM(o.child, "cs", o), ch = o.par.c0 + o.par.headC - o.par.headGap - 6;
        const down = [[mc, ch], [mc, o.child.c0]];
        o.pts = o.a === o.par ? down : down.reverse();
      } else {
        const mm = o.par.m0 + 14 + 24 * o.mi, ch = o.par.c0 + o.par.headC - (o.par.headGap || 0) - 8;
        const down = [[mm, ch], [mm, o.cc], [o.child.m0, o.cc]];
        o.pts = o.a === o.par ? down : down.reverse();
      }
    }
    // 実際の座標へ写して、全体を余白つきで原点に寄せる
    const xy = ([mm, cc]) => (H ? [mm, cc] : [cc, mm]);
    const rect = (p) => (H ? { x: p.m0, y: p.c0, w: p.sm, h: p.sc } : { x: p.c0, y: p.m0, w: p.sc, h: p.sm });
    const boxes = P.map((p) => ({ p, r: rect(p) }));
    for (const o of L) o.xy = o.pts.map(xy);
    // 丸の番号は、いちばん長い区間の真ん中。ほかの丸と近すぎれば、その区間に沿ってずらす
    const placed = [];
    for (const o of L) {
      let best = 0, bl = -1;
      for (let i = 1; i < o.xy.length; i++) {
        const l = Math.abs(o.xy[i][0] - o.xy[i - 1][0]) + Math.abs(o.xy[i][1] - o.xy[i - 1][1]);
        if (l > bl) { bl = l; best = i; }
      }
      const [p, q] = [o.xy[best - 1], o.xy[best]];
      const dx = Math.sign(q[0] - p[0]), dy = Math.sign(q[1] - p[1]);
      let bx = (p[0] + q[0]) / 2, by = (p[1] + q[1]) / 2;
      for (const step of [0, 22, -22, 44, -44]) {
        const x = bx + dx * step, y = by + dy * step;
        if (!placed.some(([u, w]) => Math.hypot(u - x, w - y) < 21)) { bx = x; by = y; break; }
      }
      o.badge = [bx, by];
      placed.push(o.badge);
    }
    const xs = [], ys = [];
    for (const { r } of boxes) { xs.push(r.x, r.x + r.w); ys.push(r.y, r.y + r.h); }
    for (const o of L) { for (const [x, y] of o.xy) { xs.push(x); ys.push(y); } xs.push(o.badge[0] - 10, o.badge[0] + 10); ys.push(o.badge[1] - 10, o.badge[1] + 10); }
    const ox = 6 - Math.min(...xs), oy = 6 - Math.min(...ys);
    const W = Math.ceil(Math.max(...xs) + ox + 6), Ht = Math.ceil(Math.max(...ys) + oy + 6);
    for (const b of boxes) { b.r.x += ox; b.r.y += oy; }
    for (const o of L) { o.xy = o.xy.map(([x, y]) => [x + ox, y + oy]); o.badge = [o.badge[0] + ox, o.badge[1] + oy]; }
    return { boxes, L, W, H: Ht };
  }

  function arrowHead(p, q) {
    const dx = Math.sign(q[0] - p[0]), dy = Math.sign(q[1] - p[1]), s = PT.HEAD, w = 4.2;
    const bx = q[0] - dx * s, by = q[1] - dy * s;
    return `${q[0]},${q[1]} ${bx - dy * w},${by + dx * w} ${bx + dy * w},${by - dx * w}`;
  }

  function partsSVG(v, H, pg) {
    const lay = partsLayout(v, H);
    const touch = {};
    for (const o of lay.L) for (const id of [o.from, o.to]) (touch[id] = touch[id] || []).push(o.k);
    let boxes = "", links = "";
    // 親の箱を先に（子の箱がその上に重なる）
    for (const { p, r } of [...lay.boxes].sort((a, b) => (a.p.kids.length ? 0 : 1) - (b.p.kids.length ? 0 : 1))) {
      const par = p.kids.length > 0;
      const tx = par ? r.x + 12 : r.x + r.w / 2, anchor = par ? "start" : "middle";
      const ty = par ? r.y + 22 : r.y + r.h / 2 + (p.note ? -2 : 5);
      boxes += `<g class="pt-box${par ? " pt-par" : ""}" data-pg="${pg}" data-pb="${(touch[p.id] || []).join(" ")}"${lab(p.label)}>` +
        `<rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" rx="${par ? 12 : 9}"/>` +
        `<text class="pt-lab" x="${tx}" y="${ty}" text-anchor="${anchor}">${esc(p.label)}</text>` +
        (p.note ? `<text class="pt-note" x="${tx}" y="${ty + 15}" text-anchor="${anchor}">${esc(p.note)}</text>` : "") +
        `<title>${esc(p.label)}${p.note ? "：" + esc(p.note) : ""}</title></g>`;
    }
    for (const o of lay.L) {
      const pts = o.xy.map((q) => [...q]);
      const n = pts.length, last = pts[n - 1], prev = pts[n - 2];
      const dx = Math.sign(last[0] - prev[0]), dy = Math.sign(last[1] - prev[1]);
      const end = [last[0] - dx * (PT.HEAD - 1), last[1] - dy * (PT.HEAD - 1)];
      const d = "M" + [...pts.slice(0, -1), end].map((q) => q.map((x) => +x.toFixed(1)).join(" ")).join(" L");
      const [bx, by] = o.badge;
      links += `<g class="pt-link" data-pg="${pg}" data-pl="${o.k}" tabindex="0" role="button" aria-label="やりとり${o.k}">` +
        `<path class="pt-hit" d="${d}"/><path class="pt-line" d="${d}"/><polygon class="pt-arr" points="${arrowHead(prev, last)}"/>` +
        `<circle cx="${bx}" cy="${by}" r="${PT.R}"/><text class="pt-n" x="${bx}" y="${by + 4}" text-anchor="middle">${o.k}</text>` +
        `<title>${o.k}. ${esc(o.label || "")}</title></g>`;
    }
    return { W: lay.W, svg: `<svg class="pt-svg ${H ? "pt-h" : "pt-v"}" viewBox="0 0 ${lay.W} ${lay.H}" width="${lay.W}" role="img" aria-label="${esc(v.name)}">${boxes}${links}</svg>` };
  }

  function parts(v) {
    const pg = `pf${++ptSeq}`;
    const name = Object.fromEntries(v.parts.map((p) => [p.id, p.label]));
    const h = partsSVG(v, true, pg), vv = partsSVG(v, false, pg);
    const rows = v.links.map((l, i) => `<li class="pt-row" data-pg="${pg}" data-pl="${i + 1}" tabindex="0">` +
      `<span class="pt-no">${i + 1}</span><span class="pt-ft">${esc(name[l.from])}<i aria-hidden="true">→</i>${esc(name[l.to])}</span>` +
      `<span class="pt-what">${esc(l.label || "—")}</span>${l.ex ? `<span class="fl-ex"><i>例</i>${esc(l.ex)}</span>` : ""}</li>`).join("");
    // 横に並べると広すぎる（760px を超える）ときは、広い所でも縦の並びを使う
    return (v.case ? `<p class="fl-case"><span>通す実例</span>${esc(v.case)}</p>` : "") +
      `<div class="pt-wrap${h.W > 760 ? " pt-tall" : ""}">${h.svg}${vv.svg}</div><ol class="pt-list">${rows}</ol>`;
  }

  // ── 比較の表 ──
  function compare(v) {
    const n = v.items.length;
    const head = `<tr><th>観点</th>${v.items.map((x) => `<th${lab(x)}>${esc(x)}</th>`).join("")}</tr>`;
    const rows = v.rows.map((r) => "same" in r
      ? `<tr class="cp-same"><td>${esc(r.axis)}<span class="cp-tag">共通</span></td><td colspan="${n}">${esc(r.same)}</td></tr>`
      : `<tr class="${r.key ? "cp-key" : ""}"><td>${esc(r.axis)}${r.key ? `<span class="cp-tag key">決め手</span>` : ""}${unsure(r.unsure)}</td>${r.values.map((x) => `<td>${esc(x)}</td>`).join("")}</tr>`).join("");
    return `<div class="v-scroll"><table class="cp"><thead>${head}</thead><tbody>${rows}</tbody></table></div>`;
  }

  // ── 重なりの図（2つはオイラー図、3つは線形の図）──
  function regionList(items, x, y, anchor) {
    const shown = items.slice(0, 5), more = items.length - shown.length;
    return shown.map((it, i) => `<text class="ov-it" x="${x}" y="${y + i * 17}" text-anchor="${anchor}"${lab(it)}>${esc(it)}</text>`).join("") +
      (more > 0 ? `<text class="ov-more" x="${x}" y="${y + shown.length * 17}" text-anchor="${anchor}">ほか${more}つ</text>` : "");
  }
  function overlap(v) {
    if (v.sets.length === 3) return linear(v);
    const A = v.elements.filter((e) => e.in.length === 1 && e.in[0] === 0).map((e) => e.label);
    const B = v.elements.filter((e) => e.in.length === 1 && e.in[0] === 1).map((e) => e.label);
    const AB = v.elements.filter((e) => e.in.length === 2).map((e) => e.label);
    const W = 620, H = 250, cy = 128;
    let h = "";
    const label = (x, y, t, a) => `<text class="ov-set" x="${x}" y="${y}" text-anchor="${a}"${lab(t)}>${esc(t)}</text>`;
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
    const head = `<tr><th></th>${els.map((e) => `<th class="ln-el"><span${lab(e.label)}>${esc(e.label)}</span></th>`).join("")}</tr>`;
    const rows = v.sets.map((s, i) => `<tr><th class="ln-set"${lab(s)}>${esc(s)}</th>${els.map((e) => `<td class="${e.in.includes(i) ? `on s${i}` : ""}"></td>`).join("")}</tr>`).join("");
    return `<div class="v-scroll"><table class="ln">${head}${rows}</table></div>`;
  }

  // ── 計算の例 ──
  function calc(v) {
    const vars = v.vars.length ? `<table class="cc-vars">${v.vars.map((x) => `<tr><td${lab(x.name)}>${esc(x.name)}</td><td class="num">${esc(x.value)}</td><td>${esc(x.note)}</td></tr>`).join("")}</table>` : "";
    const steps = v.steps.length ? `<ol class="cc-steps">${v.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : "";
    return (v.title ? `<p class="cc-title">${esc(v.title)}</p>` : "") +
      (v.formula ? `<p class="cc-formula">${esc(v.formula)}</p>` : "") + vars + steps +
      `<p class="cc-result"><span>答え</span>${esc(v.result)}</p>`;
  }

  // ── たとえ（v0.4 の A6）: たとえの側｜共通する働き｜実際の名前 を対ごとに同じ行にそろえ、番号と色を振る。
  // 本文の同じ語にも同じ番号と色が付く（app.js の markAnswer）。v0.4 より前の答え（legacy）は前の形で描く ──
  const breaksHTML = (v) => `<div class="an-breaks"><b>たとえが成り立たない所</b>${v.breaks.map((b) => `<p>${esc(b)}</p>`).join("")}</div>`;
  function analogyOld(v) {
    return `<div class="an"><div class="an-h">${esc(v.source)}</div><div></div><div class="an-h">${esc(v.target)}</div>` +
      v.pairs.map((p) => `<div class="an-s">${esc(p.s)}</div><div class="an-eq" aria-hidden="true">↔</div><div class="an-t">${esc(p.t)}</div>`).join("") +
      `</div>` + breaksHTML(v);
  }
  function analogy(v) {
    if (v.legacy || !v.pairs.some((p) => "role" in p)) return analogyOld(v);
    const rows = v.pairs.map((p, i) => {
      const k = i + 1;
      return `<tr class="an-row" data-gp="${k}" style="--pc: var(--pair-${k})" tabindex="0">` +
        `<td class="an-sc"><span class="an-no" aria-label="対${k}">${k}</span><span class="an-sn">${esc(p.s)}</span>${p.s_val ? `<span class="an-val">${esc(p.s_val)}</span>` : ""}</td>` +
        `<td class="an-role">${esc(p.role || "—")}</td>` +
        `<td class="an-tc"><span class="an-tn">${esc(p.t)}</span>${p.t_val ? `<span class="an-val">${esc(p.t_val)}</span>` : ""}</td></tr>`;
    }).join("");
    return (v.relation ? `<p class="an-rel">${esc(v.relation)}</p>` : "") +
      `<div class="v-scroll"><table class="an3"><thead><tr><th>たとえの側<small>${esc(v.source)}</small></th><th>共通する働き</th>` +
      `<th>実際の名前<small>${esc(v.target)}</small></th></tr></thead><tbody>${rows}</tbody></table></div>` +
      ((v.unmapped || []).length ? `<div class="an-un"><b>たとえに相手が無いもの</b>${v.unmapped.map((u) => `<span class="an-unit">${esc(u)}</span>`).join("")}</div>` : "") +
      breaksHTML(v);
  }

  // ── 階層の木 ──
  function treeNode(node, depth) {
    const kids = (node.children || []).slice(0, 8).map((k) => `<li>${treeNode(k, depth + 1)}</li>`).join("");
    const label = node.root || node.label;
    return `<button class="tree-n d${depth}" data-ask="${esc(label)}"${lab(label)}>${esc(label)}${node.note ? `<small>${esc(node.note)}</small>` : ""}</button>` +
      (kids && depth < 3 ? `<ul>${kids}</ul>` : "");
  }
  function tree(v) { return `<div class="tree"><ul><li>${treeNode(v, 0)}</li></ul></div>`; }

  // ── 位置の図 ──
  function map(v, opts) {
    const model = M.fromBlock(v);
    return M.render(model, { states: opts.states || {} }) + (v.gist ? `<p class="mp-gist"><b>${esc(v.center)}</b>：${esc(v.gist)}</p>` : "") + M.chips(model);
  }

  function mermaid(v) { return `<pre class="mermaid-src">${esc(v.code)}</pre>`; }

  const R = { decide, timeline, flow, parts, compare, overlap, calc, analogy, tree, map, mermaid };

  function render(v, opts = {}) {
    const f = R[v.type];
    if (!f) return "";
    try { return frame(v, f(v, opts), opts); } catch (e) { return ""; }
  }

  window.TonariViews = { render, READ };
})();
