// delay=1
// コードの見せ方（v0.7）: 素のコードの塊は空行ごとそのまま・色分けは行をまたぐ文字列でも崩れない・読むコードは注釈を指すと行が光る・
// 行に結べない注釈は出ない・本文の `名前` とコードの同じ字が結ばれる・写すと行番号が混ざらない・文の部品（** の入ったコードの語・
// ますに | のある表・番号つきの箇条書きと入れ子・リンク）
(async () => {
  PRE
  await fresh();
  await ask("デコレータをコードで見せて"); await lastDone();
  await until(() => last(".v-code"), 5000);
  const ts = await turnsNow(), t = ts[ts.length - 1];
  expect("コードの塊が3つ、答えの中の順に出る", JSON.stringify(t.views.map((v) => v.type + ":" + v.lang)) === '["code:python","code:javascript","code:diff"]', t.views.map((v) => v.type + ":" + v.lang));
  const figs = $$(".turn:last-child .v-code"), rd = figs[0], js = figs[1], df = figs[2];
  const lines = (f) => [...f.querySelectorAll(".cdl")];
  const text = (f) => lines(f).map((l) => l.textContent.replace(/^ $/, ""));
  // 読むコード
  expect("注釈つきのコードは「読むコード」の名前と理由が付く", rd.classList.contains("has-notes") && rd.querySelector(".v-name").textContent === "読むコード" && rd.querySelector(".v-why").textContent.includes("まとまり"));
  expect("言語の名前と題が出る", rd.querySelector(".cd-lang").textContent === "Python" && rd.querySelector(".cd-title").textContent === "呼び出しの前後に処理を足す");
  expect("空行は空行のまま（2行続く空行も）", lines(rd).length === 14 && text(rd)[5] === "" && text(rd)[9] === "" && text(rd)[10] === "", [lines(rd).length, text(rd)]);
  expect("行番号は字にしない（選んで写しても混ざらない）", text(rd)[0] === "def logged(fn):" && lines(rd)[0].dataset.n === "1");
  const kinds = (f, k) => [...f.querySelectorAll(".tk-" + k)].map((x) => x.textContent);
  expect("予約語・定義する名前・印に色の印が付く", kinds(rd, "kw").includes("def") && kinds(rd, "kw").includes("return") && JSON.stringify(kinds(rd, "def")) === '["logged","wrapper","add"]' && kinds(rd, "meta").includes("@logged"), [kinds(rd, "kw"), kinds(rd, "def"), kinds(rd, "meta")]);
  expect("行をまたぐ文字列は、どの行も文字列の色", !!lines(rd)[2].querySelector(".tk-str") && !!lines(rd)[3].querySelector(".tk-str") && lines(rd)[3].querySelector(".tk-str").textContent.includes("記録を残す"));
  const notes = [...rd.querySelectorAll(".cd-note")];
  expect("行に結べた注釈だけが出る（5つのうち4つ）", notes.length === 4 && notes.map((n) => n.querySelector("b").textContent).join("/") === "包む関数を作る/始まりを残す/包んだ関数を返す/付ける", notes.map((n) => n.textContent));
  expect("結べなかった注釈は、捨てた記録に残る", (t.stage.block_errors || []).some((e) => e.includes("tonari-code: 一部を捨てた") && e.includes("z = 0")), t.stage.block_errors);
  expect("注釈には、結んだ行の範囲が出る", notes[0].querySelector(".cd-at").textContent === "2〜8行目" && notes[1].querySelector(".cd-at").textContent === "5行目" && notes[2].querySelector(".cd-at").textContent === "9行目" && notes[3].querySelector(".cd-at").textContent === "12行目", notes.map((n) => n.querySelector(".cd-at").textContent));
  expect("注釈の始まる行に、注釈の番号が付く", lines(rd)[1].dataset.k === "1" && lines(rd)[4].dataset.k === "2" && lines(rd)[8].dataset.k === "3" && lines(rd)[11].dataset.k === "4");
  notes[0].dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
  await w(60);
  const lit = lines(rd).map((l, i) => (l.classList.contains("hl") ? i + 1 : 0)).filter(Boolean);
  expect("広い注釈を指すと、中の細かい注釈の行も含めて、そのまとまりの行が光る", JSON.stringify(lit) === "[2,3,4,5,6,7,8]" && notes[0].classList.contains("hl") && !notes[1].classList.contains("hl"), lit);
  lines(rd)[8].dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
  await w(60);
  expect("行を指すと、その行の注釈が光る", notes[2].classList.contains("hl") && !notes[0].classList.contains("hl"));
  lines(rd)[4].dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
  await w(60);
  expect("2つの注釈が重なる行を指すと、細かいほうの注釈が光る", notes[1].classList.contains("hl") && !notes[0].classList.contains("hl") && lines(rd).filter((l) => l.classList.contains("hl")).length === 1);
  expect("初めて見るときは、読み方を1行添える", !!rd.querySelector(".v-read") && rd.querySelector(".v-read").textContent.includes("注釈を指すと"));
  expect("読むコードには「自分の言葉で言う」が付く", !!rd.querySelector(".v-say [data-say]") && rd.querySelector(".v-say").textContent.includes("このコードがすること"));
  // 本文のコードの語と、コードの中の同じ字
  const word = (w0) => $$(".turn:last-child .lead code, .turn:last-child .prose code").find((c) => c.textContent === w0);
  const lg = word("logged");
  expect("本文の `logged` は、コードの同じ字と結ばれる", !!lg && !!lg.dataset.link && rd.querySelectorAll(`.tok-ref[data-link="${lg.dataset.link}"]`).length === 2, lg && lg.dataset.link);
  lg.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
  await w(60);
  expect("指すと、コードの中の同じ字が光る", rd.querySelectorAll(".tok-ref.hl").length === 2 && [...rd.querySelectorAll(".tok-ref.hl")].every((x) => x.textContent === "logged"));
  expect("ほかの語の一部に入っている字は結ばない（fn と fn.__name__ は結び、fn を含む別の語は結ばない）", (() => { const f = word("fn"); return !!f && [...rd.querySelectorAll(`.tok-ref[data-link="${f.dataset.link}"]`)].every((x) => x.textContent === "fn") && rd.querySelectorAll(`.tok-ref[data-link="${f.dataset.link}"]`).length === 3; })());
  // 素のコードと差分
  expect("素のコードは、名前の札を付けずにコードの箱だけを出す", !js.querySelector(".v-name") && !js.querySelector(".v-say") && js.querySelector(".cd-lang").textContent === "JavaScript");
  expect("素のコードの中の空行も残る", text(js).length === 4 && text(js)[2] === "" && kinds(js, "com").join("") === "// 値段だけ取り出す" && kinds(js, "kw").includes("const"), text(js));
  expect("差分は、足した行と消した行に色が付く", df.querySelectorAll(".cdl.d-add").length === 1 && df.querySelectorAll(".cdl.d-del").length === 1 && df.querySelector(".cd-lang").textContent === "差分");
  expect("写す字は、元のコードと1字も違わない（空白1つだけの行も残す）", window.TonariCode.codeText(df) === "-old line\n+new line\n \n same" && lines(df)[2].getBoundingClientRect().height > 10, window.TonariCode.codeText(df));
  // 写す
  let copied = null;
  Object.defineProperty(Navigator.prototype, "clipboard", { get: () => ({ writeText: async (s) => { copied = s; } }), configurable: true });
  rd.querySelector("[data-copy]").click();
  await until(() => copied !== null, 2000);
  expect("写すと、コードの字だけが空行ごと写る", !!copied && copied.startsWith("def logged(fn):\n    def wrapper(*args, **kwargs):") && copied.includes('print("start", fn.__name__)\n\n        result') && copied.endsWith("    return a + b") && !/^\s*\d+\s/m.test(copied), copied);
  expect("写したことが、ボタンの字で分かる", rd.querySelector("[data-copy]").textContent === "写しました");
  // 文の部品
  const prose = $$(".turn:last-child .prose");
  const kw = prose.find((p) => p.textContent.includes("決め手は"));
  expect("1つの段落に ** の入ったコードの語が2つあっても、太字にならない", !!kw && !kw.querySelector("strong") && [...kw.querySelectorAll("code")].filter((c) => c.textContent === "**kwargs").length === 2, kw && kw.innerHTML);
  const rows = $$(".turn:last-child .tbl-wrap tr");
  expect("表のますの中のコードの | で、列が割れない", rows.length === 3 && rows.every((r) => r.children.length === 2) && rows[1].children[0].querySelector("code").textContent === "a | b", rows.map((r) => r.children.length));
  const ol = $(".turn:last-child .prose ol");
  expect("番号つきの箇条書きと、その中の入れ子", !!ol && ol.children.length === 3 && !!ol.children[1].querySelector("ul li") && ol.children[1].querySelector("ul li").textContent === "付けた関数が包まれる", ol && ol.outerHTML);
  const a = $(".turn:last-child a.ext");
  expect("文の中の住所は、リンクになる（後ろの日本語は含めない）", !!a && a.dataset.href === "https://example.com/docs/decorators" && a.textContent === "example.com/docs/decorators", a && a.outerHTML);
  // 答えの文から HTML へ差し込めないこと（答えは先生役が書き、Web で調べたページの影響も受けうる）
  const built = (s) => { const d = document.createElement("div"); d.innerHTML = window.TonariMD.inline(s, {}); return [...d.querySelectorAll("*")]; };
  const evil = ["[見る](https://a.com/`x onmouseover=alert(1)//`)", "`<img src=x onerror=alert(1)>`", '[<b>k</b>](https://x.y/z" onclick="alert(1))', "『<i onload=alert(1)>』",
    'https://a.b/"><script>alert(1)</script>', "[a](https://x.y/\u00010\u0001) `k`", "「<svg onload=alert(1)>」"];
  const leaks = evil.filter((s) => built(s).some((el) => !["A", "CODE", "SPAN", "STRONG", "Q"].includes(el.tagName) || [...el.attributes].some((a) => /^on/i.test(a.name))));
  expect("答えの文から、出来事の属性や、許していない要素を差し込めない", leaks.length === 0, leaks);
  expect("リンクの字がコードの語でも、字が出る", (() => { const els = built("[`fetch`](https://example.com/api)"); return els.length === 2 && els[0].tagName === "A" && els[0].textContent === "fetch" && els[0].dataset.href === "https://example.com/api"; })());
  // 図とは別に数える・幅
  expect("コードは図に数えない（図の形の記録は code が3つ）", t.shapes.every((s) => s.type === "code") && !!last('[data-redo="other"]'));
  const tw = $("#thread").getBoundingClientRect();
  expect("コードの箱は、往復の列からはみ出さない", figs.every((f) => f.getBoundingClientRect().right <= tw.right + 1 && f.getBoundingClientRect().width > 300), figs.map((f) => Math.round(f.getBoundingClientRect().width)));
  rd.scrollIntoView({ block: "start" });
  await w(200);
  return { ok, ng };
})()
