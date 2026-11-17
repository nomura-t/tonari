// delay=3
// 片づけた話題を戻す・字の大きさ・予想の出し方のほかの設定（待つあいだだけ・出さない）
(async () => {
  PRE
  const sid = await fresh();
  await ask("受付って何をする役？"); await lastDone(); await w(300);
  const n = S.state.sessions.length;
  $("#archive").click();
  await until(() => S.state.sessions.length === n - 1, 4000); await w(300);
  expect("片づけると一覧から消え、片づけた話題に並ぶ",
    !S.state.sessions.some((s) => s.id === sid) && S.state.archived.some((a) => a.id === sid) && !$("#archived").hidden);
  $("#archived").open = true;
  $(`.arch[data-restore="${sid}"]`).click();
  await until(() => S.active === sid && S.detail && S.detail.session.id === sid, 4000); await w(300);
  expect("押すと一覧に戻って開く", S.state.sessions.some((s) => s.id === sid) && !S.state.archived.some((a) => a.id === sid) && $$("#thread .turn").length === 1);
  // 「全部」は、話題ごとの言葉の一覧（片づけた話題も入る。例と非例の文は並べない）
  await until(async () => (await turnsNow())[0].center, 8000);
  document.querySelector('#side .tab[data-tab="all"]').click();
  await until(() => $("#sidePane .cl-topic"), 4000);
  expect("「全部」は話題ごとに言葉を並べ、数は事実だけを出す", $$("#sidePane .cl-topic").length >= 1 && /話題に出てきた言葉/.test($("#sidePane .all-sum").innerText));
  expect("例の文は並べない", !$$("#sidePane .cl-i").some((b) => /番号札|棚卸し/.test(b.innerText)) && $$("#sidePane .cl-i").length >= 2);
  const f = $("#allFilter");
  f.value = "倉庫"; f.dispatchEvent(new Event("input", { bubbles: true }));
  await until(() => $$("#sidePane .cl-i").length > 0 && $$("#sidePane .cl-i").every((b) => /倉庫/.test(b.innerText)), 3000);
  expect("言葉を探す欄で絞れる", $$("#sidePane .cl-i").length > 0 && $$("#sidePane .cl-i").every((b) => /倉庫/.test(b.innerText)));
  f.value = ""; f.dispatchEvent(new Event("input", { bubbles: true })); await w(400);
  document.querySelector('#side .tab[data-tab="ego"]').click(); await w(300);
  expect("申告の無い言葉では、申告の行を位置の図の上に出す", !!$("#sidePane .ego-state.ask") && $("#sidePane .ego-state.ask").compareDocumentPosition($("#sidePane .cmap")) & Node.DOCUMENT_POSITION_FOLLOWING);
  // 字の大きさ
  const size = async (v) => { await api("POST", "/api/prefs", { text_size: v }); await T.loadState(); return getComputedStyle($(".prose")).fontSize; };
  const sizes = [await size("s"), await size("l"), await size("m")];
  expect("答えの字の大きさを3段から選べる", sizes.join() === "15px,19px,17px", sizes);
  expect("字を変えても1行は40字ほど", Math.abs($(".prose").getBoundingClientRect().width / 17 - 40) <= 1, $(".prose").getBoundingClientRect().width / 17);
  // 待つあいだだけ誘う設定: 別の話題にいるあいだに届いた答えも畳まない
  await api("POST", "/api/prefs", { predict: "wait" }); await T.loadState();
  await ask("受付はなぜ窓口の一種なの？");
  expect("待つあいだだけの設定でも、待つあいだは誘う", strip() === "s-predict", strip());
  await newTopic();                                  // 答えを待たずに別の話題へ
  await doneIn(sid); await w(400);
  await T.open(sid); await w(300);
  expect("待つあいだだけの設定では、戻っても答えを畳まない", !last(".fold") && !!last(".lead") && strip() !== "s-fold", strip());
  // 出さない
  await api("POST", "/api/prefs", { predict: "off" }); await T.loadState();
  await ask("窓口はいつ開くの？");
  expect("出さない設定では誘わない", strip() === null, strip());
  await lastDone(); await w(500);
  expect("出さない設定でも、答えはそのまま読める", !!last(".lead") && !last(".fold"));
  await api("POST", "/api/prefs", { predict: "both" }); await T.loadState();
  expect("既定に戻せる", S.state.prefs.predict === "both", S.state.prefs.predict);
  return { ok, ng };
})()
