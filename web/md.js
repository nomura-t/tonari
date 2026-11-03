// となり — 答えの文（Markdown の小さな部分集合）を HTML にする。外の部品を読まずに済むよう自前で持つ。
// 扱うのは段落・表・見出し・太字・コード・箇条書き・〔id｜見出し〕の札・「」の引用（棚の本文と照らした印つき）。
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function inline(s, ctx) {
    let h = esc(s);
    h = h.replace(/`([^`]+)`/g, "<code>$1</code>");
    h = h.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/〔([A-Za-z0-9_-]{6,64})(?:｜([^〕]*))?〕/g, (m, id, head) => {
      const card = (ctx.cards || []).find((c) => c.id === id);
      const title = card && card.title ? card.title : "棚のページ";
      return `<a class="shelf-card${card && card.known ? "" : " unknown"}" data-shelf="${id}" href="#" title="アーティファクト棚のページを開く">` +
        `<span class="sc-t">${esc(title)}</span>${head ? `<span class="sc-h">${head}</span>` : ""}</a>`;
    });
    h = h.replace(/「([^「」]{1,400})」/g, (m, q) => {
      const raw = q.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
      const hit = (ctx.quotes || []).find((x) => x.quote === raw);
      if (!hit) return `「${q}」`;
      return hit.found
        ? `<q class="qv ok" title="棚の本文と一致">「${q}」</q>`
        : `<q class="qv no" title="棚の本文には見つからない言い回し（言い換えか一般の話）">「${q}」</q>`;
    });
    h = h.replace(/『([^『』]{1,60})』/g, '<span class="term" data-term="$1">『$1』</span>');
    return h;
  }

  function table(rows, ctx) {
    const cells = (r) => r.replace(/^\s*\||\|\s*$/g, "").split("|").map((c) => c.trim());
    const head = cells(rows[0]);
    const body = rows.slice(2).map(cells);
    return `<div class="tbl-wrap"><table><thead><tr>${head.map((c) => `<th>${inline(c, ctx)}</th>`).join("")}</tr></thead><tbody>` +
      body.map((r) => `<tr>${r.map((c) => `<td>${inline(c, ctx)}</td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
  }

  function render(md, ctx = {}) {
    const out = [];
    const ls = String(md || "").replace(/\r/g, "").split("\n");
    let i = 0, para = [];
    const flush = () => { if (para.length) { out.push(`<p>${inline(para.join(""), ctx)}</p>`); para = []; } };
    while (i < ls.length) {
      const l = ls[i];
      if (/^```/.test(l)) {
        flush();
        const buf = [];
        i++;
        while (i < ls.length && !/^```/.test(ls[i])) buf.push(ls[i++]);
        i++;
        out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`);
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
      if (/^\s*[-*・]\s+/.test(l)) {
        flush();
        const items = [];
        while (i < ls.length && /^\s*[-*・]\s+/.test(ls[i])) items.push(ls[i++].replace(/^\s*[-*・]\s+/, ""));
        out.push(`<ul>${items.map((x) => `<li>${inline(x, ctx)}</li>`).join("")}</ul>`);
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

  window.TonariMD = { render, split, inline, esc };
})();
