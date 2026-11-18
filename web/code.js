// となり — 答えの中のコード（v0.7・DESIGN 18章）。素のコードの塊と、行のまとまりに注釈を結んだ「読むコード」を、同じ枠で描く。
// 色分けは自前の小さな字句分け（外の部品を読まない。ネットが無くても同じに出る）。分けるのは、注釈・文字列・数・
// 予約語・値（true や None）・定義する名前・呼ぶ名前・型らしい名前・印（@…）・項目の名前（JSON や YAML のキー）だけ。
// 言語の文法を全部は読まない（読み違えても字はそのまま出る。色が薄くなるだけ）。
// 行は1行ずつの箱にして、行番号は字にしない（選んで写したときに番号が混ざらない）。
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const W = (s) => new Set(s.split(/\s+/).filter(Boolean));

  const NAMES = { python: "Python", javascript: "JavaScript", typescript: "TypeScript", go: "Go", rust: "Rust", swift: "Swift", kotlin: "Kotlin",
    java: "Java", c: "C", cpp: "C++", csharp: "C#", ruby: "Ruby", php: "PHP", sql: "SQL", bash: "シェル", console: "端末", json: "JSON",
    yaml: "YAML", toml: "TOML", ini: "INI", xml: "HTML", css: "CSS", scss: "SCSS", diff: "差分", dockerfile: "Dockerfile", makefile: "Makefile",
    markdown: "Markdown", lua: "Lua", r: "R", graphql: "GraphQL", hcl: "HCL", "": "テキスト" };
  // 表を名前で引くときは、自分の持ち物だけを見る（言語の名前が constructor や __proto__ のとき、継いだ物を引いて落ちないように）
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const langName = (id) => (own(NAMES, id) ? NAMES[id] : id);
  const rules = (lang) => (own(L, lang) ? L[lang] : L.generic);

  // 言語ごとの決まり。line＝行の注釈の始まり、block＝/* */ の注釈、triple＝""" の文字列、tmpl＝` の文字列、deco＝@名前 の印、
  // kw＝予約語、lit＝値、defs＝この語の次の名前が「定義する名前」
  const C_KW = "break case catch class const continue default do else enum extends finally for if import new return static struct switch this throw try while";
  const L = {
    python: { line: "#", triple: true, deco: true, kw: W("and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case"), lit: W("True False None self cls"), defs: W("def class") },
    javascript: { line: "//", block: true, tmpl: true, deco: true, kw: W(C_KW + " async await debugger delete export from function get in instanceof let of set super typeof var void with yield"), lit: W("true false null undefined NaN Infinity"), defs: W("function class") },
    go: { line: "//", block: true, tmpl: true, kw: W("break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var"), lit: W("true false nil iota"), defs: W("func type") },
    rust: { line: "//", block: true, chars: true, attr: true, kw: W("as async await break const continue crate dyn else enum extern fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait type unsafe use where while"), lit: W("true false None Some Ok Err"), defs: W("fn struct enum trait mod type") },
    swift: { line: "//", block: true, triple: true, deco: true, kw: W("actor any as associatedtype async await break case catch class continue default defer deinit do else enum extension fallthrough fileprivate for func guard if import in indirect init inout internal is lazy let mutating nonisolated open operator override private protocol public repeat rethrows return some static struct subscript super switch throw throws try typealias var weak where while"), lit: W("true false nil self Self"), defs: W("func class struct enum protocol extension actor typealias") },
    kotlin: { line: "//", block: true, triple: true, deco: true, kw: W(C_KW + " as by companion constructor data fun in init interface internal is lateinit object open operator override package private protected public sealed super suspend typealias val var when"), lit: W("true false null it"), defs: W("fun class interface object typealias") },
    java: { line: "//", block: true, deco: true, kw: W(C_KW + " abstract assert boolean byte char double final float implements instanceof int interface long native package private protected public record short super synchronized throws transient var void volatile"), lit: W("true false null"), defs: W("class interface enum record") },
    c: { line: "//", block: true, pre: true, kw: W(C_KW + " auto char double extern float goto inline int long register short signed sizeof typedef union unsigned void volatile bool namespace template typename using virtual public private protected nullptr_t override final constexpr"), lit: W("true false NULL nullptr"), defs: W("struct class enum union namespace") },
    csharp: { line: "//", block: true, kw: W(C_KW + " abstract as async await base bool byte char decimal delegate double event explicit float foreach get implicit in int interface internal is lock long namespace object out override params private protected public readonly record ref sealed set short string using var virtual void where yield"), lit: W("true false null"), defs: W("class interface struct enum record namespace") },
    ruby: { line: "#", kw: W("alias and begin break case class def do else elsif end ensure for if in module next not or redo rescue retry return super then unless until when while yield require require_relative attr_accessor attr_reader"), lit: W("true false nil self"), defs: W("def class module") },
    php: { line: "//", block: true, vars: true, kw: W(C_KW + " abstract as echo elseif endif endforeach fn foreach function global implements interface namespace private protected public require require_once trait use var yield match readonly"), lit: W("true false null"), defs: W("function class interface trait") },
    sql: { line: "--", block: true, nocase: true, single: true, kw: W("select from where and or not in is null as on join left right inner outer full cross group by order having limit offset insert into values update set delete create table index view drop alter add column primary key foreign references unique default check constraint union all distinct case when then else end exists between like asc desc with returning begin commit rollback transaction grant revoke if"), lit: W("true false null"), defs: W("") },
    bash: { line: "#", vars: true, kw: W("if then else elif fi for in do done while until case esac function return exit export local readonly set unset source alias cd echo"), lit: W("true false"), defs: W("function") },
    yaml: { line: "#", keys: "yaml", kw: W(""), lit: W("true false null yes no on off"), defs: W("") },
    toml: { line: "#", keys: "toml", kw: W(""), lit: W("true false"), defs: W("") },
    json: { keys: "json", kw: W(""), lit: W("true false null"), defs: W("") },
    css: { block: true, keys: "css", kw: W(""), lit: W(""), defs: W("") },
    lua: { line: "--", kw: W("and break do else elseif end for function goto if in local not or repeat return then until while"), lit: W("true false nil"), defs: W("function") },
    dockerfile: { line: "#", vars: true, kw: W("FROM RUN CMD LABEL EXPOSE ENV ADD COPY ENTRYPOINT VOLUME USER WORKDIR ARG ONBUILD STOPSIGNAL HEALTHCHECK SHELL AS"), lit: W(""), defs: W("") },
    generic: { kw: W(""), lit: W(""), defs: W("") },
  };
  L.typescript = { ...L.javascript, kw: new Set([...L.javascript.kw, ...W("abstract as declare enum implements interface keyof namespace private protected public readonly satisfies type is infer override")]),
    lit: new Set([...L.javascript.lit, ...W("any unknown never string number boolean object symbol bigint void")]), defs: W("function class interface type enum namespace") };
  L.cpp = L.c;
  L.scss = { ...L.css, line: "//" };
  L.ini = L.toml;
  L.makefile = { ...L.bash, kw: W("ifeq ifneq ifdef ifndef else endif include define endef export") };
  L.r = { line: "#", kw: W("if else for while repeat function return next break in library"), lit: W("TRUE FALSE NULL NA"), defs: W("") };
  L.hcl = { line: "#", block: true, kw: W("resource variable output module provider data locals terraform"), lit: W("true false null"), defs: W("") };
  L.graphql = { line: "#", kw: W("query mutation subscription fragment on type interface union enum input scalar schema extend implements directive"), lit: W("true false null"), defs: W("type interface enum input fragment") };

  const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const cache = new Map();
  function master(lang) {
    if (cache.has(lang)) return cache.get(lang);
    const c = rules(lang);
    const alt = [];
    // 複数の行にまたがる形の終わりは、閉じの印か、コードの終わり（m の印を付けているので、$ は行の終わりに当たってしまう）
    if (c.block) alt.push("(?<com>\\/\\*[\\s\\S]*?(?:\\*\\/|(?![\\s\\S])))");
    if (c.line) alt.push(`(?<lcom>${reEsc(c.line)}[^\\n]*)`);
    if (c.triple) alt.push('(?<tri>"""[\\s\\S]*?(?:"""|(?![\\s\\S]))|\'\'\'[\\s\\S]*?(?:\'\'\'|(?![\\s\\S])))');
    if (c.tmpl) alt.push("(?<tmpl>`(?:\\\\[\\s\\S]|[^`\\\\])*(?:`|(?![\\s\\S])))");
    alt.push('(?<dq>"(?:\\\\.|[^"\\\\\\n])*(?:"|(?=\\n)|$))');
    if (c.chars) alt.push("(?<sq>'(?:\\\\.|[^'\\\\\\n])'|b'(?:\\\\.|[^'\\\\\\n])')");   // Rust: 'a' は文字、'a（閉じない）は寿命の名前
    else alt.push("(?<sq>'(?:\\\\.|[^'\\\\\\n])*(?:'|(?=\\n)|$))");
    if (c.attr) alt.push("(?<meta>#!?\\[[^\\]\\n]*\\])");
    if (c.pre) alt.push("(?<meta>^[ \\t]*#[ \\t]*[a-z]+)");
    if (c.deco) alt.push("(?<meta>@[A-Za-z_][\\w.]*)");
    if (c.vars) alt.push("(?<vr>\\$\\{[^}\\n]*\\}|\\$[A-Za-z_]\\w*|\\$[0-9@#?*!$-])");
    alt.push("(?<num>\\b0[xXbBoO][0-9a-fA-F_]+\\b|\\b\\d[\\d_]*(?:\\.\\d[\\d_]*)?(?:[eE][+-]?\\d+)?[a-zA-Z%]{0,3}\\b)");
    alt.push("(?<id>[A-Za-z_$][\\w$]*)");
    const re = new RegExp(alt.map((a, i) => a.replace(/\(\?<meta>/, `(?<meta${i}>`)).join("|"), "gm");
    cache.set(lang, re);
    return re;
  }

  // コードを（種類, 字）の列に分ける。種類が空のものは地の字
  function tokens(code, lang) {
    if (lang === "diff") return [["", code]];
    if (lang === "xml") return xmlTokens(code);
    if (lang === "console") return consoleTokens(code);
    const c = rules(lang), re = master(lang), out = [];
    const low = (s) => (c.nocase ? s.toLowerCase() : s);
    let at = 0, m, prevWord = "";
    re.lastIndex = 0;
    while ((m = re.exec(code))) {
      if (!m[0]) { re.lastIndex++; continue; }
      if (m.index > at) out.push(["", code.slice(at, m.index)]);
      const g = m.groups, s = m[0];
      let k = "";
      if (g.com !== undefined || g.lcom !== undefined) k = "com";
      else if (g.tri !== undefined || g.tmpl !== undefined || g.dq !== undefined || g.sq !== undefined) {
        k = "str";
        // 項目の名前: JSON の "名前": 、YAML・TOML の引用符つきの名前
        if (c.keys && /^[ \t]*:/.test(code.slice(re.lastIndex, re.lastIndex + 8)) && (c.keys === "json" || /(^|\n)[ \t-]*$/.test(code.slice(Math.max(0, m.index - 80), m.index)))) k = "prop";
      } else if (g.vr !== undefined) k = "var";
      else if (g.num !== undefined) k = "num";
      else if (g.id !== undefined) {
        const rest = code.slice(re.lastIndex, re.lastIndex + 40);
        const lineStart = /(^|\n)[ \t-]*$/.test(code.slice(Math.max(0, m.index - 80), m.index));
        if (c.keys === "yaml" && lineStart && /^[\w.\-/ ]*:(\s|$)/.test(rest)) k = "prop";
        else if (c.keys === "toml" && lineStart && /^[\w.\-]*[ \t]*=/.test(rest)) k = "prop";
        else if (c.keys === "css" && /^[\w-]*[ \t]*:/.test(rest) && /[{;]\s*$|^\s*$/.test(code.slice(Math.max(0, m.index - 40), m.index).split("\n").pop() || "")) k = "prop";
        else if (c.kw.has(low(s))) k = "kw";
        else if (c.lit.has(low(s))) k = "lit";
        else if (c.defs.has(low(prevWord))) k = "def";
        else if (/^\s*\(/.test(rest) && !c.keys) k = "fn";
        else if (/^[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*$/.test(s) && !c.nocase && !c.keys) k = "type";
        prevWord = s;
      } else k = "meta";
      if (k !== "kw" && g.id === undefined) prevWord = "";
      out.push([k, s]);
      at = re.lastIndex;
    }
    if (at < code.length) out.push(["", code.slice(at)]);
    return out;
  }

  function xmlTokens(code) {
    const out = [];
    const re = /(<!--[\s\S]*?(?:-->|$))|(<\/?)([A-Za-z][\w:.-]*)|("[^"\n]*"|'[^'\n]*')|([A-Za-z_:@][\w:.-]*)(?==)|(\/?>)/g;
    let at = 0, m, inTag = false;
    while ((m = re.exec(code))) {
      if (m.index > at) out.push(["", code.slice(at, m.index)]);
      if (m[1] !== undefined) out.push(["com", m[1]]);
      else if (m[2] !== undefined) { out.push(["", m[2]], ["kw", m[3]]); inTag = true; }
      else if (m[4] !== undefined) out.push([inTag ? "str" : "", m[4]]);
      else if (m[5] !== undefined) out.push([inTag ? "prop" : "", m[5]]);
      else { out.push(["", m[6]]); inTag = false; }
      at = re.lastIndex;
    }
    if (at < code.length) out.push(["", code.slice(at)]);
    return out;
  }

  // 端末のやりとり: 「$ 」「% 」「> 」で始まる行が打った命令、ほかの行は出てきた字
  function consoleTokens(code) {
    const out = [];
    code.split("\n").forEach((l, i, a) => {
      const m = l.match(/^(\s*(?:[\w@.~:\/-]*[$%#>]|PS [^>]*>)\s)(.*)$/);
      if (m) out.push(["meta", m[1]], ["", m[2]]);
      else out.push(["out", l]);
      if (i < a.length - 1) out.push(["", "\n"]);
    });
    return out;
  }

  // 字句の列を、行ごとの HTML にする（複数の行にまたがる注釈や文字列は、行ごとに同じ種類の印を付け直す）
  function lineHTML(code, lang) {
    const lines = [[]];
    for (const [k, s] of tokens(code, lang)) {
      s.split("\n").forEach((part, i) => {
        if (i > 0) lines.push([]);
        if (part) lines[lines.length - 1].push(k ? `<span class="tk-${k}">${esc(part)}</span>` : esc(part));
      });
    }
    return lines.map((x) => x.join(""));
  }

  const READ = "右（狭いときは下）の注釈を指すと、コードのその行が光ります。行の左の番号は、注釈の番号です。本文の中の `名前` を指すと、コードの同じ名前が光ります。";
  let seq = 0;

  // 1つのコードの塊（図と同じ枠）。opts.firstTime なら、読むコードの読み方を1行添える
  function figure(v, opts = {}) {
    const html = lineHTML(v.code, v.lang);
    const notes = v.notes || [];
    const g = `cd${++seq}`;
    // 行ごとの、結ぶ注釈（重なったら、範囲の短いほう＝細かいほう）と、その行から始まる注釈の番号
    // （広い注釈を指したときに、その中の細かい注釈の行も光るように。光らせる仕組みは、しくみの絵と同じ data-pg・data-pl・data-pb）
    const near = html.map(() => 0), all = html.map(() => []), starts = html.map(() => []);
    notes.forEach((n, k) => {
      starts[n.from - 1].push(k + 1);
      for (let i = n.from; i <= n.to && i <= html.length; i++) {
        const cur = near[i - 1];
        all[i - 1].push(k + 1);
        if (!cur || (n.to - n.from) < (notes[cur - 1].to - notes[cur - 1].from)) near[i - 1] = k + 1;
      }
    });
    const diff = v.lang === "diff";
    const rows = html.map((h, i) => {
      const k = near[i];
      const cls = ["cdl"];
      if (k) cls.push("in-note");
      if (diff) { const ch = v.code.split("\n")[i][0]; if (ch === "+") cls.push("d-add"); else if (ch === "-") cls.push("d-del"); else if (ch === "@") cls.push("d-at"); }
      return `<span class="${cls.join(" ")}" data-n="${i + 1}"${k ? ` data-pg="${g}" data-pl="${k}" data-pb="${all[i].join(" ")}"` : ""}${starts[i].length ? ` data-k="${starts[i].join("・")}"` : ""}>` +
        `<span class="cdl-t">${h}</span></span>`;
    }).join("");
    const at = (n) => (n.from === n.to ? `${n.from}行目` : `${n.from}〜${n.to}行目`);
    const list = notes.length ? `<ol class="cd-notes">` + notes.map((n, k) =>
      `<li class="cd-note" data-pg="${g}" data-pl="${k + 1}" tabindex="0"><span class="cd-no" aria-hidden="true">${k + 1}</span>` +
      `<div>${n.label ? `<b>${esc(n.label)}</b>` : ""}<p>${window.TonariMD.inline(n.text, {})}</p></div><span class="cd-at">${at(n)}</span></li>`).join("") + `</ol>` : "";
    const head = notes.length
      ? `<figcaption class="v-head"><span class="v-name">${esc(v.name)}</span>${v.why ? `<span class="v-why">${esc(v.why)}</span>` : ""}</figcaption>` +
        (opts.firstTime ? `<p class="v-read">${READ}</p>` : "") : "";
    const say = notes.length && !opts.noSay ? `<div class="v-say"><button class="chip say" data-say="1">このコードがすることを、自分の言葉で言う</button></div>` : "";
    return `<figure class="view v-code${notes.length ? " has-notes" : ""}" data-type="code"${opts.vi != null ? ` data-vi="${opts.vi}"` : ""}>${head}` +
      `<div class="v-body"><div class="cd-wrap"><div class="cd-box">` +
      `<div class="cd-bar"><span class="cd-lang">${esc(langName(v.lang))}</span>${v.title ? `<span class="cd-title">${esc(v.title)}</span>` : ""}` +
      `<button class="cd-copy" type="button" data-copy="1" aria-label="このコードを写す">写す</button></div>` +
      `<pre class="cd-pre${html.length < 3 ? " cd-short" : ""}" tabindex="0"><code class="cd-code" data-lang="${esc(v.lang)}">${rows}</code></pre>` +
      (v.cut ? `<p class="cd-cut">長いので、ここから先は省きました。</p>` : "") + `</div>${list}</div></div>${say}</figure>`;
  }

  const codeText = (fig) => [...fig.querySelectorAll(".cd-code .cdl-t")].map((x) => x.textContent).join("\n");

  async function copy(btn) {
    const fig = btn.closest(".v-code");
    if (!fig) return;
    const text = codeText(fig);
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
      const ta = document.createElement("textarea");   // 窓の中の部品が写す許しを持たないとき
      ta.value = text;
      ta.style.cssText = "position:fixed;left:-9999px;top:0";
      document.body.appendChild(ta);
      ta.select();
      try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
      ta.remove();
    }
    if (ok) document.dispatchEvent(new CustomEvent("tonari:act", { detail: { what: "copy" } }));
    btn.textContent = ok ? "写しました" : "写せませんでした";
    btn.classList.toggle("done", ok);
    clearTimeout(btn._t);
    btn._t = setTimeout(() => { btn.textContent = "写す"; btn.classList.remove("done"); }, 1600);
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest ? e.target.closest("[data-copy]") : null;
    if (b) { e.preventDefault(); copy(b); }
  });

  // 本文の中のコードの語（`名前`）と、コードの中の同じ字を結ぶ（指すと両方が光る。app.js の data-link の仕組みに乗せる）。
  // 語が1つの字句に収まらないとき（`logged(add)` など）は、その字を含む行ごと結ぶ
  const wordy = (ch) => /[\w$]/.test(ch || "");
  function linkWords(art, key) {
    const figs = [...art.querySelectorAll(".view.v-code")];
    if (!figs.length) return;
    let n = 0;
    const seen = new Map();
    for (const el of art.querySelectorAll(".lead code[data-code], .prose code[data-code], .cd-note code[data-code]")) {
      const word = el.dataset.code;
      if (word.length < 2 || word.length > 48) continue;
      if (!seen.has(word)) {
        const id = `${key}~w${n++}`;
        let hits = 0;
        for (const fig of figs) {
          for (const line of fig.querySelectorAll(".cdl")) {
            const text = line.textContent;
            let from = text.indexOf(word), any = false;
            while (from >= 0) {
              const okL = !wordy(word[0]) || !wordy(text[from - 1]), okR = !wordy(word[word.length - 1]) || !wordy(text[from + word.length]);
              if (okL && okR) { any = true; if (wrapAt(line, from, word.length, id)) hits++; else { line.dataset.link = id; hits++; } }
              from = text.indexOf(word, from + word.length);
            }
            if (any && !line.querySelector(`[data-link="${id}"]`)) line.dataset.link = id;
          }
        }
        seen.set(word, hits ? id : null);
      }
      const id = seen.get(word);
      if (id) el.dataset.link = id;
    }
  }
  // 行の中の from 文字目から len 字が、1つの文字の節に収まっていれば、そこを包む
  function wrapAt(line, from, len, id) {
    const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
    let pos = 0, node;
    while ((node = walker.nextNode())) {
      const end = pos + node.nodeValue.length;
      if (from >= pos && from + len <= end) {
        if (node.parentElement.classList.contains("tok-ref") && node.parentElement.dataset.link === id) return true;
        const mid = node.splitText(from - pos);
        mid.splitText(len);
        const sp = document.createElement("span");
        sp.className = "tok-ref";
        sp.dataset.link = id;
        mid.replaceWith(sp);
        sp.appendChild(mid);
        return true;
      }
      pos = end;
    }
    return false;
  }

  window.TonariCode = { figure, tokens, lineHTML, linkWords, langName, codeText, READ };
})();
