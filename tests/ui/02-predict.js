// delay=5
// 待つあいだの予想: 帯の欄に打って送る（先生役には送らない）・打ちかけなら届いた答えを畳んでおく・取り違えの戻し
(async () => {
  PRE
  await fresh();
  await ask("倉庫が空だとどうなる？");
  expect("最初の問いで誘う", strip() === "s-predict", strip());
  const n1 = (await turnsNow()).length;
  $("#stripText").value = "たぶん、無いと返す";
  await T.sendStrip(); await w(400);
  expect("予想は往復を増やさない（先生役に送らない）", (await turnsNow()).length === n1);
  expect("待ちの表示の上に予想が出る", !!last(".predict") && !!last(".pending"));
  expect("予想を送ると帯は消える", strip() === null, strip());
  await lastDone(); await w(600);
  expect("届いた答えの上に予想が残る", !!last(".predict") && !!last(".lead"));
  // 取り違えの戻し: 予想として残った文を、質問として送り直す
  last("[data-unpredict]").click();
  await until(async () => (await turnsNow()).length === n1 + 1, 5000);
  let ts = await turnsNow();
  expect("予想を外して、質問として送り直せる", ts[ts.length - 1].final_text === "たぶん、無いと返す" && !ts[ts.length - 2].predict, [ts[ts.length - 1].final_text, ts[ts.length - 2].predict]);
  await lastDone(); await w(400);
  // 打ちかけのまま答えが届く → 送るまで畳んでおく
  await ask("受付はなぜ倉庫に聞くの？");
  expect("予想したあとは、続けて誘う", strip() === "s-predict", strip());
  $("#stripText").value = "倉庫しか中身を知らないから";
  await lastDone(); await w(700);
  expect("打ちかけの予想があると、届いた答えを畳んでおく", !!last(".folded [data-release]") && !last(".lead"));
  expect("帯が「答えが届きました」に変わっても、打ちかけの字は消えない", $("#stripText").value === "倉庫しか中身を知らないから" && /届きました/.test($("#strip .st-k").innerText));
  await T.sendStrip(); await w(700);
  expect("予想を送ると答えが開く", !!last(".lead") && !!last(".predict") && strip() === null);
  ts = await turnsNow();
  expect("開いた時刻が付く", ts[ts.length - 1].revealed_at > 0);
  // 予想せずに読む
  await ask("受付はどこにいる？");
  expect("予想した次の問いでは、続けて誘ってよい", strip() === "s-predict", strip());
  $("#stripText").value = "えーと";
  await lastDone(); await w(700);
  last("[data-release]").click(); await w(500);
  expect("打ちかけても、予想せずに読める", !!last(".lead") && !last(".predict") && strip() === null);
  await ask("窓口って何？");
  expect("誘いに乗らなかった次は誘わない", strip() === null, strip());
  await lastDone();
  // 打ちかけの予想で畳んでいた答えがあるまま、下の欄から別の問いを送ると、畳んでいた答えは開く
  await ask("倉庫は何を返す？");
  if (strip() === "s-predict") {
    $("#stripText").value = "品物だと思";
    const held = S.detail.turns[S.detail.turns.length - 1].id;
    await lastDone(); await w(700);
    expect("打ちかけで畳んでいる", S.hold === held && !!last(".folded [data-release]"));
    await ask("窓口と受付は同じ？");
    expect("別の問いを送ると、畳んでいた答えは開く", S.hold === null && !!document.querySelector(`.turn[data-turn="${held}"] .lead`) && !document.querySelector(`.turn[data-turn="${held}"] .folded`));
    await lastDone(); await w(400);
  } else expect("誘いが出る（打ちかけの場面の前提）", false, strip());
  // 「やめる」を押した誘いは、その問いではもう出さない
  await api("POST", "/api/prefs", { predict: "both" });   // 誘いの間引きの印を消して、誘いが出る状態にする
  await ask("受付は何を持たない？");
  expect("誘いが出る", strip() === "s-predict", strip());
  $("#strip [data-stripx]").click(); await w(300);
  expect("やめるを押すと帯は消える", strip() === null, strip());
  await T.loadDetail(false); await w(200);
  expect("描き直しても、やめた誘いは出ない", strip() === null, strip());
  await lastDone();
  return { ok, ng };
})()
