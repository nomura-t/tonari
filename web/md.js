// となり — 答えの文（Markdown の小さな部分集合）を HTML にする。外の部品を読まずに済むよう自前で持つ。
// 扱うのは段落・表・見出し・太字・文の中のコード・箇条書き（番号つき・入れ子1段）・引用の段・リンク・
// 〔id｜見出し〕の札・「」の引用（棚の本文と照らした印つき）。コードの塊は、サーバーが答えから切り出して図と同じ枠で出す
// （web/code.js）。ここに残る ``` の塊は、考えの塊や調べたページの中のものだけ。
// v0.7: 文の中のコード（`…`）を先に取り置いてから、ほかの書式を当てる。前は、1つの段落に `**kwargs` が2つあると間が
// 太字になり、表のますの `a | b` で列が割れていた。* や _ の強調は扱わない（コードの語と取り違えるため）。
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const unesc = (s) => s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
  const HOLD = "\u0001";   // 取り置いたコードの語の置き場所（本文には出ない字）

  // 文の中のコード（`…`。中に ` を含む ``a`b`` の形も）を取り置く。開いたのと同じ数の ` の並びを、同じ行の中で探して閉じる。
  // 正規表現でなく1字ずつ見る（` が何千も続く行で、正規表現の後戻りが10秒かかったため）
  function takeCode(s, put) {
    let out = "", i = 0;
    const n = s.length;
    while (i < n) {
      if (s[i] !== "`") {
        const j = s.indexOf("`", i);
        if (j < 0) { out += s.slice(i); break; }
        out += s.slice(i, j);
        i = j;
        continue;
      }
      let k = i;
      while (k < n && s[k] === "`") k++;
      const len = k - i;
      let p = k, close = -1;
      while (p < n && s[p] !== "\n") {
        if (s[p] !== "`") { p++; continue; }
        let q = p;
        while (q < n && s[q] === "`") q++;
        if (q - p === len) { close = p; break; }
        p = q;
      }
      const body = close >= 0 ? s.slice(k, close).trim() : "";
      if (body) { out += put(body); i = close + len; } else { out += s.slice(i, k); i = k; }
    }
    return out;
  }

  function inline(s, ctx) {
    const held = [];
    const hold = (html) => { held.push(html); return `${HOLD}${held.length - 1}${HOLD}`; };
    // 文の中のコード: ``a`b`` の形（中に ` を含む）も読む。中身には、ほかの書式を当てない
    // 置き場所の字そのものが本文に書かれていても、取り置きの番号として読まない（先に消す）
    let t = takeCode(String(s ?? "").replace(/\u0001/g, ""), (code) => hold(`<code data-code="${esc(code)}">${esc(code)}</code>`));
    // リンク: [字](https://…) と、文の中の https://…。開くのは外のブラウザ（data-href）
    // 住所には、取り置きの置き場所の字を通さない（住所の中のコードの語が、属性の中で HTML に戻って属性を作れてしまった）。
    // リンクの字の中のコードの語は、ここで戻しておく（戻すのは要素の中身だけ。属性の中には置き場所を残さない）
    t = t.replace(/\[([^\]\n]{1,120})\]\((https?:\/\/[^\s)\u0001]{1,400})\)/g, (m, label, url) =>
      hold(`<a class="ext" href="#" data-href="${esc(url)}" title="${esc(url)}">${esc(label).replace(/\u0001(\d+)\u0001/g, (m2, i) => held[Number(i)] ?? "")}</a>`));
    t = t.replace(/https?:\/\/[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]{4,400}/g, (url) => {
      const tail = (url.match(/[.,;:!?)\]]+$/) || [""])[0];   // 文の終わりの句読点はリンクに入れない
      const u = tail ? url.slice(0, -tail.length) : url;
      return hold(`<a class="ext" href="#" data-href="${esc(u)}" title="${esc(u)}">${esc(u.replace(/^https?:\/\//, "").slice(0, 60))}${u.length > 68 ? "…" : ""}</a>`) + tail;
    });
    let h = esc(t);
    h = h.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/〔([A-Za-z0-9_-]{6,64})(?:｜([^〕]*))?〕/g, (m, id, head) => {
      const card = (ctx.cards || []).find((c) => c.id === id);
      const title = card && card.title ? card.title : "棚のページ";
      return `<a class="shelf-card${card && card.known ? "" : " unknown"}" data-shelf="${id}" href="#" title="アーティファクト棚のページを開く">` +
        `<span class="sc-t">${esc(title)}</span>${head ? `<span class="sc-h">${head}</span>` : ""}</a>`;
    });
    h = h.replace(/「([^「」]{1,400})」/g, (m, q) => {
      if (q.includes(HOLD)) return m;   // コードの語やリンクをまたぐ「」は、棚の本文と照らさない
      const hit = (ctx.quotes || []).find((x) => x.quote === unesc(q));
      if (!hit) return `「${q}」`;
      return hit.found
        ? `<q class="qv ok" title="棚の本文と一致">「${q}」</q>`
        : `<q class="qv no" title="棚の本文には見つからない言い回し（言い換えか一般の話）">「${q}」</q>`;
    });
    h = h.replace(/『([^『』\u0001]{1,60})』/g, '<span class="term" data-term="$1">『$1』</span>');
    // 取り置いた物を戻す（1回だけ。戻した物の中に置き場所は残っていない。置き場所があるのは要素の中身だけで、属性の中には無い）
    return h.replace(/\u0001(\d+)\u0001/g, (m, i) => held[Number(i)] ?? "");
  }

  // 表のますを分ける。文の中のコード（`…`）の中の | と、\| は区切りにしない
  function cells(row) {
    const out = [];
    let cur = "";
    const r = row.replace(/^\s*\|/, "").replace(/\|\s*$/, "");
    for (let i = 0; i < r.length; i++) {
      const ch = r[i];
      if (ch === "\\" && r[i + 1] === "|") { cur += "|"; i++; continue; }
      if (ch === "`") {
        let n = 1;
        while (r[i + n] === "`") n++;
        // 同じ数の ` で閉じる所があるときだけ、コードの語として | を守る（閉じていない ` で、行の残りを1つのますにしない）
        let p = i + n, close = -1;
        while (p < r.length) {
          if (r[p] !== "`") { p++; continue; }
          let q = p;
          while (r[q] === "`") q++;
          if (q - p === n) { close = q; break; }
          p = q;
        }
        if (close > 0) { cur += r.slice(i, close); i = close - 1; } else { cur += r.slice(i, i + n); i += n - 1; }
        continue;
      }
      if (ch === "|") { out.push(cur.trim()); cur = ""; continue; }
      cur += ch;
    }
    out.push(cur.trim());
    return out;
  }

  function table(rows, ctx) {
    const head = cells(rows[0]);
    const body = rows.slice(2).map(cells);
    return `<div class="tbl-wrap"><table><thead><tr>${head.map((c) => `<th>${inline(c, ctx)}</th>`).join("")}</tr></thead><tbody>` +
      body.map((r) => `<tr>${r.map((c) => `<td>${inline(c, ctx)}</td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
  }

  // 箇条書き。行の頭の印が「- * ・」なら点、「1. 1)」なら番号。字下げ（2字以上）の行は、すぐ上の項目の中の入れ子（1段まで）
  const ITEM = /^(\s*)(?:([-*・])|(\d{1,3})[.)])\s+(.*)$/;
  function list(ls, i, ctx) {
    const first = ls[i].match(ITEM);
    const ordered = first[3] !== undefined, base = first[1].length;
    const items = [];
    while (i < ls.length) {
      const m = ls[i].match(ITEM);
      if (!m) break;
      const indent = m[1].length;
      if (indent >= base + 2 && items.length) {          // 入れ子
        const sub = { ordered: m[3] !== undefined, items: [] };
        while (i < ls.length) {
          const k = ls[i].match(ITEM);
          if (!k || k[1].length < base + 2) break;
          sub.items.push(k[4]);
          i++;
        }
        items[items.length - 1].sub = sub;
        continue;
      }
      if (indent < base || (m[3] !== undefined) !== ordered) break;
      items.push({ text: m[4] });
      i++;
    }
    const li = (it) => `<li>${inline(it.text, ctx)}${it.sub ? `<${it.sub.ordered ? "ol" : "ul"}>${it.sub.items.map((x) => `<li>${inline(x, ctx)}</li>`).join("")}</${it.sub.ordered ? "ol" : "ul"}>` : ""}</li>`;
    const start = ordered && Number(first[3]) !== 1 ? ` start="${Number(first[3])}"` : "";
    return { html: `<${ordered ? "ol" : "ul"}${start}>${items.map(li).join("")}</${ordered ? "ol" : "ul"}>`, next: i };
  }

  function render(md, ctx = {}) {
    const out = [];
    const ls = String(md || "").replace(/\r/g, "").split("\n");
    let i = 0, para = [];
    // 段落の中の改行: 日本語の行どうしは詰め、英数字で終わる行と英数字で始まる行の間だけ空白を入れる（語がくっつかないように）
    const joinLines = (xs) => xs.reduce((a, b) => a + (/[\x21-\x7e]$/.test(a) && /^[\x21-\x7e]/.test(b) ? " " : "") + b);
    const flush = () => { if (para.length) { out.push(`<p>${inline(joinLines(para), ctx)}</p>`); para = []; } };
    while (i < ls.length) {
      const l = ls[i];
      const fm = l.match(/^\s*```\s*([A-Za-z0-9_+#.-]*)\s*$/);
      if (fm) {
        flush();
        const buf = [];
        i++;
        while (i < ls.length && !/^\s*```\s*$/.test(ls[i])) buf.push(ls[i++]);
        i++;
        out.push(`<pre class="md-pre"><code${fm[1] ? ` data-lang="${esc(fm[1].toLowerCase())}"` : ""}>${esc(buf.join("\n"))}</code></pre>`);
        continue;
      }
      if (/^\s*\|/.test(l) && i + 1 < ls.length && /^\s*\|?\s*:?-{2,}/.test(ls[i + 1])) {
        flush();
        const rows = [];
        while (i < ls.length && /^\s*\|/.test(ls[i])) rows.push(ls[i++]);
        out.push(table(rows, ctx));
        continue;
      }
      const hm = l.match(/^(#{1,4})\s+(.*)$/);
      if (hm) { flush(); out.push(`<h4>${inline(hm[2], ctx)}</h4>`); i++; continue; }
      if (ITEM.test(l)) {
        flush();
        const r = list(ls, i, ctx);
        out.push(r.html);
        i = r.next;
        continue;
      }
      if (/^\s*>\s?/.test(l)) {
        flush();
        const buf = [];
        while (i < ls.length && /^\s*>\s?/.test(ls[i])) buf.push(ls[i++].replace(/^\s*>\s?/, ""));
        out.push(`<blockquote>${inline(buf.join(""), ctx)}</blockquote>`);
        continue;
      }
      if (!l.trim()) { flush(); i++; continue; }
      para.push(l);
      i++;
    }
    flush();
    return out.join("\n");
  }

  // 最初の段落（答えの言い切り）と残りに分ける
  function split(md) {
    const s = String(md || "").trim();
    const k = s.search(/\n\s*\n/);
    return k < 0 ? [s, ""] : [s.slice(0, k).trim(), s.slice(k).trim()];
  }

  window.TonariMD = { render, split, inline, esc, cells };
})();
