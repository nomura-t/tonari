// delay=1
// 構成の図（v0.7）: まとまりは書かれた順に上から下・使う側が上・箱は重ならない・循環と、層に逆らう線に印・箱を指すと、使うものと
// 使われる相手が色を分けて光る・押すと留まり、間接も含められる・箱の中を聞ける・線を文で読める・大きく見る窓（覆っているあいだに
// 届いた答えは、閉じるまで読んだことにしない）・ファイルの並び
(async () => {
  PRE
  await fresh();
  await ask("Web アプリの構成を教えて"); await lastDone();
  await until(() => last(".v-arch .ar-svg"), 5000);
  let ts = await turnsNow();
  const t = ts[ts.length - 1], v = t.views[0];
  const fig = last(".v-arch");
  const node = (name, root = fig) => [...root.querySelectorAll(".ar-node")].find((g) => g.dataset.name === name);
  const box = (name) => node(name).querySelector("rect").getBoundingClientRect();
  const over = (el) => el.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
  expect("構成の図が、答えの図として出る", v.type === "arch" && !!v.lay && fig.querySelector(".v-name").textContent === "構成の図", v.type);
  expect("箱は7つ、線は8本（両端が箱に無い線は捨てて、記録に残す）", fig.querySelectorAll(".ar-node").length === 7 && fig.querySelectorAll(".ar-edge").length === 8 &&
    (t.stage.block_errors || []).some((e) => e.includes("tonari-arch: 一部を捨てた") && e.includes("両端が箱に無い線")), t.stage.block_errors);
  const bnds = [...fig.querySelectorAll(".ar-band")];
  const by = bnds.map((b) => b.querySelector("rect").getBoundingClientRect());
  expect("まとまりは、書かれた順に上から下へ並ぶ", [...fig.querySelectorAll(".ar-bl")].map((x) => x.textContent).join("/") === "画面の層/アプリの層/データの層" && by[0].bottom <= by[1].top && by[1].bottom <= by[2].top, by.map((r) => [Math.round(r.top), Math.round(r.bottom)]));
  expect("使う側が上、使われる側が下に来る", box("利用者").bottom < box("Web 画面").top && box("Web 画面").bottom < box("API サーバー").top && box("API サーバー").bottom < box("DB").top && box("DB").bottom < box("メールの外部サービス").top);
  expect("箱は、自分のまとまりの枠の中にある", box("Web 画面").top >= by[0].top && box("Web 画面").bottom <= by[0].bottom && box("ワーカー").top >= by[1].top && box("ワーカー").bottom <= by[1].bottom && box("ジョブキュー").top >= by[2].top && box("利用者").bottom <= by[0].top);
  const rects = [...fig.querySelectorAll(".ar-node > rect")].map((r) => r.getBoundingClientRect());
  expect("箱は重ならない", !rects.some((p, i) => rects.slice(i + 1).some((q) => p.left < q.right - 0.5 && q.left < p.right - 0.5 && p.top < q.bottom - 0.5 && q.top < p.bottom - 0.5)));
  const edge = (a, b, root = fig) => [...root.querySelectorAll(".ar-edge")].find((g) => g.dataset.from === a && g.dataset.to === b);
  expect("循環を作る線と、層に逆らう線に印が付く", edge("db", "api").classList.contains("cyc") && edge("db", "api").classList.contains("up") && edge("api", "db").classList.contains("cyc") && !edge("api", "db").classList.contains("up") && !edge("web", "api").classList.contains("cyc"));
  expect("見つけたことは、この図の上のこととして文で出る", !!fig.querySelector(".ar-flag.f-cyc") && fig.querySelector(".ar-flag.f-cyc").textContent.includes("この図の上では") && fig.querySelector(".ar-flag.f-cyc").textContent.includes("「API サーバー」・「DB」") &&
    fig.querySelector(".ar-flag.f-up").textContent.includes("DB → API サーバー"), [...fig.querySelectorAll(".ar-flag")].map((x) => x.textContent));
  expect("線の読み方と、線を確かめていないことを書く", fig.querySelector(".ar-how").textContent.includes("A は B を使う") && fig.querySelector(".ar-src").textContent.includes("実際のコードとは照らしていません") && fig.querySelector(".ar-src").textContent.includes("線の形だけ"));
  expect("箱の種類は、小さな印と言葉の凡例で分ける", [...fig.querySelectorAll(".ar-legend span")].map((x) => x.textContent).join("/") === "人/画面/サービス/保存する所/キュー/外の仕組み" && !!node("DB").querySelector(".ar-gl"), [...fig.querySelectorAll(".ar-legend span")].map((x) => x.textContent));
  const dOf = (g) => g.querySelector(".ar-line").getAttribute("d");
  expect("行きと帰りの線は、重ねずに並べる", dOf(edge("api", "db")).split(" ")[0] !== dOf(edge("db", "api")).split(" ").slice(-2, -1)[0] && Math.abs(edge("api", "db").getBoundingClientRect().left - edge("db", "api").getBoundingClientRect().left) > 4, [dOf(edge("api", "db")), dOf(edge("db", "api"))]);
  const lb = [...fig.querySelectorAll(".ar-el")].map((x) => x.getBoundingClientRect()), bl = [...fig.querySelectorAll(".ar-bl")].map((x) => x.getBoundingClientRect());
  const hit2 = (p, q) => p.left < q.right && q.left < p.right && p.top < q.bottom && q.top < p.bottom;
  expect("線の名前は、ほかの線の名前にも、まとまりの名前にも重ならない", lb.length === 3 && !lb.some((p, i) => lb.slice(i + 1).some((q) => hit2(p, q)) || bl.some((q) => hit2(p, q))), lb.map((r) => [Math.round(r.left), Math.round(r.top)]));
  expect("使っている技術は、箱の中の2行目に出る", node("API サーバー").querySelector(".ar-tech").textContent === "FastAPI");
  // 指す
  const marks = (root = fig) => Object.fromEntries(["sel", "uses", "usedby"].map((c) => [c, [...root.querySelectorAll(".ar-node." + c)].map((g) => g.dataset.name).sort().join("・")]));
  over(node("ワーカー"));
  await w(60);
  expect("箱を指すと、その箱が使うものが光る", fig.classList.contains("has-sel") && JSON.stringify(marks()) === JSON.stringify({ sel: "ワーカー", uses: "DB・ジョブキュー・メールの外部サービス", usedby: "" }), marks());
  expect("指した中身が、文でも読める", fig.querySelector(".ar-read .rd.uses").textContent.includes("「ワーカー」が使うのは、3つ") && fig.querySelector(".ar-read .rd.usedby").textContent.includes("この図にはありません"), fig.querySelector(".ar-read").textContent);
  expect("関係のない線は薄くなる", edge("job", "q").classList.contains("on") && !edge("web", "api").classList.contains("on") && getComputedStyle(edge("web", "api")).opacity < 0.5);
  over(node("API サーバー"));
  await w(60);
  expect("使うものと、使われる相手を分けて示す（循環の相手は両方）", JSON.stringify(marks()) === JSON.stringify({ sel: "API サーバー", uses: "DB・ジョブキュー", usedby: "DB・Web 画面" }), marks());
  over($("#typed"));
  await w(60);
  expect("図の外へ出ると、元に戻る", !fig.classList.contains("has-sel") && fig.querySelector(".ar-read").textContent.includes("箱を指すと、その箱が使うもの（青）と、その箱を使うもの（緑）") && fig.querySelector(".ar-act").hidden);
  // 押して留める・間接も含める
  node("ワーカー").dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await w(60);
  over($("#typed"));
  await w(60);
  expect("箱を押すと留まり、外へ出ても光ったまま", fig.dataset.pin === "job" && marks().sel === "ワーカー" && !fig.querySelector(".ar-act").hidden);
  fig.querySelector("[data-ardeep]").click();
  await w(60);
  expect("「間接も含める」で、たどれる先まで光る", marks().uses === "API サーバー・DB・ジョブキュー・メールの外部サービス" && fig.querySelector("[data-ardeep]").getAttribute("aria-pressed") === "true" && fig.querySelector(".ar-read").textContent.includes("たどれる先まで"), marks());
  // 用語と箱
  const term = $$(".turn:last-child .term").find((x) => x.dataset.term === "API サーバー");
  expect("本文の『用語』と、同じ名前の箱が結ばれる", !!term && !!term.dataset.link && node("API サーバー").dataset.link === term.dataset.link);
  const cw = $$(".turn:last-child .prose code").find((x) => x.textContent === "DB");
  expect("図の箱の名前がコードの語で書かれていても、同じ名前の箱と結ばれる", !!cw && !!cw.dataset.link && node("DB").dataset.link === cw.dataset.link);
  // 線を文で読む
  const rows = [...fig.querySelectorAll(".ar-list .ar-row")];
  expect("線は、文の一覧でも読める", rows.length === 8 && rows[1].textContent.replace(/\s+/g, "") === "Web画面→APIサーバーHTTPS" && rows[7].textContent.includes("循環") && rows[7].textContent.includes("層に逆らう"), rows.map((r) => r.textContent));
  // 大きく見る
  fig.querySelector(".ar-svg").dispatchEvent(new MouseEvent("click", { bubbles: true }));   // 留めたのを外す
  await w(60);
  expect("図の空いた所を押すと、留めたのが外れる", !fig.dataset.pin && !fig.classList.contains("has-sel"));
  fig.querySelector("[data-zoom]").click();
  await until(() => T.Zoom.isOpen(), 3000);
  const dlg = $("#figZoom"), zs = dlg.querySelector(".fz-svg");
  expect("「大きく見る」で、図が大きな窓に写る", T.Zoom.isOpen() && !!zs && dlg.querySelectorAll(".ar-node").length === 7 && zs.getBoundingClientRect().width > fig.querySelector(".ar-svg").getBoundingClientRect().width, zs && zs.getBoundingClientRect().width);
  const vb0 = zs.getAttribute("viewBox");
  T.Zoom.zoomBy(2);
  await w(50);
  const vb1 = zs.getAttribute("viewBox").split(" ").map(Number), b0 = vb0.split(" ").map(Number);
  expect("寄ると、見える範囲が半分になる", Math.abs(vb1[2] - b0[2] / 2) < 1 && $("#fzNow").textContent === "200%", [vb0, zs.getAttribute("viewBox")]);
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "0", bubbles: true }));
  await w(50);
  expect("0 のキーで、全体に戻る", zs.getAttribute("viewBox").split(" ").map(Number).every((x, i) => Math.abs(x - b0[i]) < 0.01) && $("#fzNow").textContent === "100%", zs.getAttribute("viewBox"));
  over(node("ワーカー", dlg));
  await w(60);
  expect("大きな窓の中でも、指すと光る", marks(dlg.querySelector(".v-arch")).uses === "DB・ジョブキュー・メールの外部サービス", marks(dlg.querySelector(".v-arch")));
  // 覆っているあいだに届いた答え
  const n0 = (await turnsNow()).length;
  await T.sendText("受付って何をする役？");
  await until(async () => { const x = await turnsNow(); return x.length > n0 && x[x.length - 1].status === "done"; }, 20000);
  await w(400);
  ts = await turnsNow();
  expect("大きな窓が覆っているあいだに届いた答えは、まだ読んだことにしない", !ts[ts.length - 1].revealed_at, ts[ts.length - 1].revealed_at);
  $("#fzClose").click();
  await until(async () => { const x = await turnsNow(); return x[x.length - 1].revealed_at; }, 5000);
  ts = await turnsNow();
  expect("窓を閉じると、読める形で出したことになる", !T.Zoom.isOpen() && !!ts[ts.length - 1].revealed_at && !$("#fzBody").children.length);
  // 箱の中を聞く
  const fig2 = $$(".v-arch")[0];
  node("ワーカー", fig2).focus();
  node("ワーカー", fig2).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await w(60);
  expect("箱を押したあと、焦点は箱に残らない（話すキーを箱が受けない）", document.activeElement !== node("ワーカー", fig2) && fig2.dataset.pin === "job");
  // キー: Space は受けない（アプリの話すキー）。Enter は留める・外す。押し続けの繰り返しは受けない
  let heard = 0;
  const hear = (e) => { if (e.code === "F13") heard++; };
  document.addEventListener("keydown", hear);
  node("DB", fig2).dispatchEvent(new KeyboardEvent("keydown", { key: " ", code: "F13", bubbles: true }));
  expect("箱に焦点があっても、Space は箱が受けない", heard === 1 && fig2.dataset.pin === "job", [heard, fig2.dataset.pin]);
  node("DB", fig2).dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "F13", bubbles: true, repeat: true }));
  expect("押し続けの Enter は受けない", fig2.dataset.pin === "job" && heard === 2);
  node("DB", fig2).dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "F13", bubbles: true }));
  expect("Enter で、焦点のある箱を留める", fig2.dataset.pin === "db" && heard === 2, [fig2.dataset.pin, heard]);
  document.removeEventListener("keydown", hear);
  node("ワーカー", fig2).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  fig2.querySelector("[data-ardeep]").click();
  await w(60);
  // 往復の列が描き直されても、留めた箱は留まったまま
  await T.loadDetail(false);
  await w(400);
  const fig3 = $$(".v-arch")[0];
  expect("往復の列を描き直しても、留めた箱と「間接も含める」は残る", fig3 !== fig2 && fig3.dataset.pin === "job" && fig3.dataset.deep === "1" && marks(fig3).sel === "ワーカー" &&
    marks(fig3).uses === "API サーバー・DB・ジョブキュー・メールの外部サービス" && !fig3.querySelector(".ar-act").hidden, [fig3.dataset.pin, fig3.dataset.deep, marks(fig3)]);
  const n1 = (await turnsNow()).length;
  fig3.querySelector("[data-arask]").click();
  await until(async () => (await turnsNow()).length > n1, 6000);
  ts = await turnsNow();
  expect("留めた箱の「中を聞く」で、その箱の中の構成を問いとして送る", ts.length === n1 + 1 && ts[ts.length - 1].final_text.includes("『ワーカー』の中の構成"), ts[ts.length - 1].final_text);
  await lastDone();
  // ファイルの並び
  await ask("フォルダの並びを教えて"); await lastDone();
  await until(() => last(".ft"), 5000);
  const ft = last(".ft");
  expect("フォルダとファイルの並びは、等幅の字の入れ子で出る", !!ft && ft.querySelectorAll(".ft-n").length === 7 && [...ft.querySelectorAll(".ft-dir > .ft-name")].map((x) => x.textContent).join(" ") === "my-app/ app/ lib/" &&
    getComputedStyle(ft).fontFamily.includes("Mono"), ft && [...ft.querySelectorAll(".ft-n")].map((x) => x.textContent));
  expect("ファイルの並びにも、初めて見るときの読み方が付く", last(".v-tree .v-read") && last(".v-tree .v-read").textContent.includes("フォルダ"));
  $$(".v-arch")[0].scrollIntoView({ block: "start" });
  await w(250);
  return { ok, ng };
})()
