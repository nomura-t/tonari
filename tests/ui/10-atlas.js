// delay=1
// 全体の地図: 押したときに開く・話題ごとに島が1つ・話題をまたぐ言葉は島ごとに置いて結ぶ・引くと島の名前と説明を受けた言葉だけ・
// 言葉と島を選ぶと右に中身・探す・話題を開く・地図が往復の列を覆っているあいだの答えは、閉じるまで読んだことにしない
(async () => {
  PRE
  const A = T.Atlas, dlg = $("#atlas"), svg = $("#atSvg");
  const nd = (label) => $$("#atSvg .nd").filter((g) => g.querySelector("text").textContent === label);
  const shown = (el) => !!el && getComputedStyle(el).display !== "none";
  const center = (sid) => until(async () => { const ts = await turnsOf(sid); return ts.length && ts[ts.length - 1].center; }, 10000);
  // 話題を2つ作る（受付の話と会計の話。「倉庫」と「受付」は両方に出る）
  const a = await fresh();
  await ask("受付って何をする役？"); await lastDone(); await center(a);
  const b = await newTopic();
  await ask("会計って何をする役？"); await lastDone(); await center(b);
  expect("地図は、押すまで開かない（最初の画面にしない）", !dlg.open && !!$("#openAtlas"));
  await T.openAtlas();
  await until(() => dlg.open && $$("#atSvg .nd").length, 5000);
  expect("入口を押すと、窓いっぱいに開く", dlg.open && dlg.getBoundingClientRect().width >= innerWidth - 2, dlg.getBoundingClientRect().width);
  const mine = $$("#atSvg .isl").filter((g) => [a, b].includes(Number(g.dataset.topic)));
  expect("話題ごとに島が1つあり、名前の札が付く", mine.length === 2 && mine.every((g) => g.querySelector(".isl-t").textContent.length > 2), mine.length);
  expect("いま開いている話題の島に印が付く", !!$(`#atSvg .isl.cur[data-topic="${b}"]`) && !$(`#atSvg .isl.cur[data-topic="${a}"]`));
  expect("話題をまたぐ言葉は、出てくる島ごとに置く", nd("倉庫").filter((g) => [a, b].includes(Number(g.dataset.k.split(":")[0]))).length === 2 && nd("倉庫").every((g) => g.classList.contains("shared")), nd("倉庫").length);
  expect("島と島のあいだに橋がある", !!$(`#atSvg .br[data-bridge="${a}:${b}"]`) && $$(`#atSvg .br[data-bridge="${a}:${b}"] .br-c`).length >= 1);
  expect("説明を受けた言葉は太字の札", nd("会計").some((g) => g.classList.contains("hub")) && !nd("帳簿")[0].classList.contains("hub"));
  expect("例の文は地図に出さない", !nd("来た人に番号札を渡す場面").length);
  const v = $("#atView").getBoundingClientRect();
  const inside = (g) => { const r = g.getBoundingClientRect(); return r.left >= v.left - 1 && r.right <= v.right + 1 && r.top >= v.top - 1 && r.bottom <= v.bottom + 1; };
  expect("開いたときは、全体が窓に収まる", $$("#atSvg .nd").every(inside) && $$("#atSvg .isl-bg").every(inside), A.state.k);
  const boxes = $$("#atSvg .nd rect").map((r) => r.getBoundingClientRect());
  const hitAny = boxes.some((p, i) => boxes.slice(i + 1).some((q) => p.left < q.right - 0.5 && q.left < p.right - 0.5 && p.top < q.bottom - 0.5 && q.top < p.bottom - 0.5));
  expect("札は重ならない", !hitAny);
  expect("寄って見るときは、言葉の字と、同じ言葉を結ぶ線が出る", !svg.classList.contains("far") && shown(nd("帳簿")[0].querySelector("text")) && shown($("#atSvg .br-c")) && !shown($("#atSvg .br-a")), A.state.k);
  // 引いて見る: 島の名前と、説明を受けた言葉だけを残す。橋は島と島の1本に
  for (let i = 0; i < 6 && A.state.k >= 0.6; i++) { A.zoomBy(1 / 1.4); await w(450); }
  expect("引くと、説明を受けた言葉と島の名前だけを字で残し、橋は1本の線と数になる",
    svg.classList.contains("far") && !shown(nd("帳簿")[0].querySelector("text")) && shown(nd("会計")[0].querySelector("text")) && shown($("#atSvg .br-a")) && !shown($("#atSvg .br-c")) && /\d/.test($("#atSvg .br-n text").textContent), [A.state.k, svg.className.baseVal]);
  const fz = parseFloat(getComputedStyle($("#atSvg .isl-t")).fontSize) * A.state.k;
  expect("引いても、島の名前は読める大きさ", fz >= 11.5, fz);
  A.fit(false); await w(200);
  // 言葉を選ぶ
  nd("倉庫").find((g) => Number(g.dataset.k.split(":")[0]) === b).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await w(200);
  expect("言葉を押すと、同じ言葉の札がどの島でも光る", $$("#atSvg .nd.on").length === nd("倉庫").length && svg.classList.contains("has-sel"), $$("#atSvg .nd.on").length);
  expect("右の欄に、その言葉と関係の文が出る", $("#atSide h3").textContent === "倉庫" && $$("#atSide .at-rels li").length >= 2 && !!$("#atSide [data-at-ego]") && !!$("#atSide [data-at-ask]"), $("#atSide").innerText.slice(0, 80));
  expect("出てくる話題が札で並ぶ", $$("#atSide .at-chips .at-topic").length >= 2);
  $("#atSide .at-rels [data-at-c]").click(); await w(400);
  expect("関係の相手を押すと、その言葉に移る", $("#atSide h3").textContent !== "倉庫" && !!A.state.sel && A.state.sel.type === "c", $("#atSide h3").textContent);
  // Esc は、選んだ物 → 地図の順に閉じる
  let ev = new Event("cancel", { cancelable: true });
  dlg.dispatchEvent(ev);
  expect("選んでいるあいだの Esc は、選んだ物を外すだけ", ev.defaultPrevented && A.state.sel === null && dlg.open && !svg.classList.contains("has-sel"));
  ev = new Event("cancel", { cancelable: true });
  dlg.dispatchEvent(ev);
  expect("何も選んでいなければ、Esc で地図を閉じられる", !ev.defaultPrevented);
  // 探す
  const f = $("#atFind");
  f.value = "倉"; f.dispatchEvent(new Event("input", { bubbles: true })); await w(150);
  expect("探すと、当たった言葉だけが残る", $$("#atSvg .nd.hit").length === nd("倉庫").length && svg.classList.contains("has-find") && /語/.test($("#atFindN").textContent), $("#atFindN").textContent);
  f.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await w(400);
  expect("Enter で、当たった言葉を選ぶ", !!A.state.sel && A.state.sel.type === "c" && $("#atSide h3").textContent === "倉庫");
  f.value = ""; f.dispatchEvent(new Event("input", { bubbles: true }));
  // 地図の中のキーは、下の画面に渡さない
  $("#atView").dispatchEvent(new KeyboardEvent("keydown", { code: "Space", key: " ", bubbles: true })); await w(200);
  expect("地図を開いているあいだ、話すキーは録音を始めない", S.rec.phase === "idle");
  // 島を選ぶ → 字下げの一覧 → 話題を開く
  $(`#atSvg .isl[data-topic="${a}"] .isl-t`).dispatchEvent(new MouseEvent("click", { bubbles: true })); await w(200);
  expect("島を押すと、その話題の言葉が字下げの一覧で出る", !!$("#atSide .at-out") && $$("#atSide .at-out li").length === $$(`#atSvg .nd[data-k^="${a}:"]`).length && !!$("#atSide [data-at-open]"), $$("#atSide .at-out li").length);
  expect("一覧の字下げは、木の親子に合う", $$("#atSide .at-out li").some((li) => li.style.getPropertyValue("--d") === "1") && $$("#atSide .at-out li").some((li) => li.style.getPropertyValue("--d") === "0"));
  $("#atSide [data-at-open]").click();
  await until(() => !dlg.open && S.active === a && S.detail && S.detail.session.id === a, 5000);
  expect("「この話題を開く」で、地図を閉じてその話題を開く", !dlg.open && S.active === a);
  // 地図が往復の列を覆っているあいだに届いた答えは、閉じるまで読んだことにしない
  await api("POST", "/api/prefs", { predict: "off" }); await T.loadState();
  await T.sendText("受付はどこにいる？");
  const tid = (await until(async () => { const ts = await turnsNow(); return ts[ts.length - 1].status !== "done" && ts[ts.length - 1]; }, 3000) || {}).id;
  await T.openAtlas();
  await doneIn(a); await w(700);
  let t = (await turnsNow()).find((x) => x.id === tid);
  expect("地図を開いているあいだに届いた答えには、開いた時刻を付けない", dlg.open && !!t && t.status === "done" && !t.revealed_at, t && t.revealed_at);
  expect("地図の上に、答えが届いた知らせが出る", !$("#atNews").hidden && /届きました/.test($("#atNews").textContent), $("#atNews").textContent);
  T.Atlas.close();
  await until(async () => ((await turnsNow()).find((x) => x.id === tid) || {}).revealed_at, 4000);
  t = (await turnsNow()).find((x) => x.id === tid);
  expect("地図を閉じると、その答えが読める形で出て、開いた時刻が付く", !dlg.open && t.revealed_at > 0 && !!document.querySelector(`.turn[data-turn="${tid}"] .lead`), t.revealed_at);
  await api("POST", "/api/prefs", { predict: "both" }); await T.loadState();
  // 片づけた話題も地図に出て、そこから戻して開ける
  await api("PATCH", `/api/sessions/${b}`, { archived: true }); await T.loadState();
  await T.openAtlas();
  await until(() => dlg.open && $(`#atSvg .isl[data-topic="${b}"]`), 5000);
  expect("片づけた話題も地図に出る", !!$(`#atSvg .isl.arch[data-topic="${b}"]`));
  $(`#atSvg .isl[data-topic="${b}"] .isl-bg`).dispatchEvent(new MouseEvent("click", { bubbles: true })); await w(200);
  expect("片づけた話題は「一覧に戻して開く」", /戻して開く/.test($("#atSide [data-at-open]").textContent));
  $("#atSide [data-at-open]").click();
  await until(() => !dlg.open && S.active === b && S.state.sessions.some((s) => s.id === b), 5000);
  expect("押すと、一覧に戻って開く", S.active === b && S.state.sessions.some((s) => s.id === b) && !S.state.archived.some((s) => s.id === b));
  // キーで開く・閉じる
  if (document.activeElement) document.activeElement.blur();
  document.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyM", key: "m", metaKey: true, bubbles: true }));
  await until(() => dlg.open, 3000);
  expect("キーで開く", dlg.open);
  $("#atView").dispatchEvent(new KeyboardEvent("keydown", { code: "KeyM", key: "m", metaKey: true, bubbles: true })); await w(200);
  expect("同じキーで閉じる", !dlg.open);
  // 「全部」の一覧の上からも入れる
  document.querySelector('#side .tab[data-tab="all"]').click();
  await until(() => $("#sidePane [data-openatlas]"), 4000);
  $("#sidePane [data-openatlas]").click();
  await until(() => dlg.open && $$("#atSvg .nd").length, 4000);
  expect("「全部」の一覧の上から、地図へ入れる", dlg.open);
  // 並べ直すのは、本人が押したときだけ。押すと決め直して、選んだ物は外れる
  const before = JSON.stringify(A.state.data.layout.anchors);
  $(`#atSvg .isl[data-topic="${a}"] .isl-bg`).dispatchEvent(new MouseEvent("click", { bubbles: true })); await w(150);
  $("#atSide [data-at-clear]").click(); await w(150);
  expect("一覧へ戻ると、並べ直しの口がある", !!$("#atSide [data-at-relayout]") && A.state.sel === null);
  $("#atSide [data-at-relayout]").click();
  await w(700);
  const boxes2 = $$("#atSvg .isl-bg").map((r) => r.getBoundingClientRect());
  const over = boxes2.some((p, i) => boxes2.slice(i + 1).some((q) => p.left < q.right - 0.5 && q.left < p.right - 0.5 && p.top < q.bottom - 0.5 && q.top < p.bottom - 0.5));
  expect("並べ直しても、島は重ならず、全部の島が残る", !over && $$("#atSvg .isl").length === Object.keys(JSON.parse(before)).length && dlg.open, $$("#atSvg .isl").length);
  T.Atlas.close(); await w(150);
  // 選んだまま・探す字を残したまま閉じても、次に開いたときに薄いままにならない
  await T.openAtlas(); await until(() => dlg.open && $$("#atSvg .nd").length, 4000);
  nd("倉庫")[0].dispatchEvent(new MouseEvent("click", { bubbles: true })); await w(150);
  f.value = "倉"; f.dispatchEvent(new Event("input", { bubbles: true })); await w(150);
  expect("選んで、探した印が付いている", svg.classList.contains("has-sel") && svg.classList.contains("has-find"));
  $("#atClose").click(); await w(150);
  await T.openAtlas(); await until(() => dlg.open && $$("#atSvg .nd").length, 4000);
  expect("開き直すと、選んだ印も探した印も残っていない", !svg.classList.contains("has-sel") && !svg.classList.contains("has-find") && f.value === "" && !$("#atSvg .nd.on") && !$("#atSvg .nd.hit"), svg.className.baseVal);
  // 地図の何も無い所を押したあと（焦点が地図の外）でも、地図のキーが効く
  if (document.activeElement) document.activeElement.blur();
  const k0 = A.state.k;
  document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "-", code: "Minus", bubbles: true })); await w(450);
  expect("焦点が地図の外にあっても、引くキーが効く", A.state.k < k0 - 0.01, [k0, A.state.k]);
  document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "0", code: "Digit0", bubbles: true })); await w(450);
  expect("全体に戻すキーが効く", Math.abs(A.state.k - k0) < 0.01, [k0, A.state.k]);
  // 地図の中では、話すキー（Space）でボタンを押せるままにする（下の画面は、Space でボタンが押されるのを止めている）
  let up = new KeyboardEvent("keyup", { code: "Space", key: " ", bubbles: true, cancelable: true });
  $("#atFit").dispatchEvent(up);
  expect("地図の中の Space は、止めない", !up.defaultPrevented);
  T.Atlas.close(); await w(150);
  up = new KeyboardEvent("keyup", { code: "Space", key: " ", bubbles: true, cancelable: true });
  document.body.dispatchEvent(up);
  expect("地図の外では、今までどおり止める", up.defaultPrevented);
  // 開くのを待つあいだに録音が始まったら、地図は開かない
  const opening = T.openAtlas();
  S.rec.phase = "recording";
  await opening; await w(150);
  expect("待つあいだに録音が始まったら、地図を開かない", !dlg.open);
  S.rec.phase = "idle";
  // 「読みに戻る」: いまの話題に届いた答えがあれば、別の話題へ移らずに、その答えを読める形で出す
  await api("POST", "/api/prefs", { predict: "off" }); await T.loadState();
  await T.open(a); await w(300);
  await T.sendText("受付は何時まで？");
  const t1 = (await until(async () => { const ts = await turnsNow(); return ts[ts.length - 1].status !== "done" && ts[ts.length - 1]; }, 3000) || {}).id;
  await T.openAtlas();
  await doneIn(a); await until(() => !$("#atNews").hidden, 4000);
  $("#atNews").click();
  await until(async () => ((await turnsOf(a)).find((x) => x.id === t1) || {}).revealed_at, 4000);
  expect("いまの話題に届いた答えの「読みに戻る」は、その話題のまま答えを出す", !dlg.open && S.active === a && !!document.querySelector(`.turn[data-turn="${t1}"] .lead`) && ((await turnsOf(a)).find((x) => x.id === t1) || {}).revealed_at > 0);
  // 地図から別の話題へ移るときは、前の話題に届いた答えを読んだことにしない
  await T.sendText("受付は何人いる？");
  const t2 = (await until(async () => { const ts = await turnsNow(); return ts[ts.length - 1].status !== "done" && ts[ts.length - 1]; }, 3000) || {}).id;
  await T.openAtlas();
  await doneIn(a); await w(500);
  $(`#atSvg .isl[data-topic="${b}"] .isl-bg`).dispatchEvent(new MouseEvent("click", { bubbles: true })); await w(150);
  $("#atSide [data-at-open]").click();
  await until(() => !dlg.open && S.active === b && S.detail && S.detail.session.id === b, 5000); await w(500);
  expect("地図から別の話題へ移ると、前の話題の答えには開いた時刻が付かない", S.active === b && !((await turnsOf(a)).find((x) => x.id === t2) || {}).revealed_at, ((await turnsOf(a)).find((x) => x.id === t2) || {}).revealed_at);
  await T.open(a); await w(400);
  expect("その話題に戻ったときに、読める形で出て時刻が付く", ((await turnsOf(a)).find((x) => x.id === t2) || {}).revealed_at > 0);
  await api("POST", "/api/prefs", { predict: "both" }); await T.loadState();
  const st = await api("GET", "/api/atlas");
  expect("島の置き場所は、開くたびに同じ", JSON.stringify(st.layout.anchors) === JSON.stringify((await api("GET", "/api/atlas")).layout.anchors) && Object.keys(st.layout.anchors).length >= 2);
  return { ok, ng };
})()
