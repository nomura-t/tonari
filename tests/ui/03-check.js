// delay=2
// 戻ったときの確かめ: 帯は入力欄の上に出る・上の帯は増えない・右の列は空にしない・帯の欄に打って答えられる・あとで
(async () => {
  PRE
  await fresh();
  await ask("受付って何をする役？"); await lastDone();
  await until(async () => (await turnsNow())[0].checks.length > 0, 10000);   // 記録役が確かめの問いを足す
  await T.open(S.active);                                                     // 読んだ（開いた時刻が付く）
  expect("読んだ直後は確かめを出さない", strip() === null, strip());
  await w(3400);
  await T.open(S.active);                                                     // 時間をおいて戻る（試しの設定は3秒）
  expect("戻ると、確かめの帯が入力欄の上に出る", strip() === "s-check", strip());
  expect("往復の列の上の帯は1本まで", bands().length <= 1, bands());
  expect("帯が出ていても、話すボタンは先生役への発言のまま", $("#talkLabel").textContent === "話す", $("#talkLabel").textContent);
  expect("元の答えは畳まれる", $$(".folded [data-stripx]").length === 1);
  await until(() => $("#sidePane .side-note"), 3000);                          // 右の列は、言葉の一覧を取ってから描く
  expect("右の列は空にせず、位置の図を伏せて言葉の一覧を出す",
    $("#side").classList.contains("checking") && !!$("#sidePane .side-note") && !$("#sidePane .pm") && $$("#sidePane .cl-i").length > 0);
  // ヒントは1段ずつ。帯を描き直しても打ちかけの字は消えない
  $("#stripText").value = "打ちかけ";
  $("#strip [data-rchint]").click(); await until(() => $$("#strip .rc-hints li").length === 1, 3000);
  expect("ヒントを出しても、打ちかけの字は消えない", $("#stripText").value === "打ちかけ" && $$("#strip .rc-hints li").length === 1);
  $("#stripText").value = "";
  // あとで: 帯は下がり、畳んでいた答えが開く。問いは残り、次に戻るとまた出る
  const rc = S.retSnap.id;
  $("#strip [data-stripx]").click(); await w(400);
  expect("あとで: 帯が下がり、答えと位置の図が戻る", strip() === null && $$(".folded").length === 0 && !$("#side").classList.contains("checking"));
  await T.open(S.active); await w(300);
  expect("あとでにした問いは、次に戻るとまた出る", strip() === "s-check" && S.retSnap.id === rc);
  // 先生役への発言を送ると、帯は下がる（主な経路が先）
  await ask("受付はどこにいる？");
  expect("確かめに答えずに送ると、帯は下がる", strip() !== "s-check", strip());
  let ts = await turnsNow();
  expect("その発言は質問として送られる（確かめへの答えにしない）", ts[ts.length - 1].kind === "question" && !ts[ts.length - 1].check_id, [ts[ts.length - 1].kind, ts[ts.length - 1].check_id]);
  await lastDone(); await w(300);
  await T.open(S.active); await w(3400); await T.open(S.active);
  // 帯の欄に打って答える → その問いへの答えとして先生役が判定する
  expect("時間をおいて戻ると、また出る", strip() === "s-check", strip());
  const cid = S.retSnap.id, n0 = (await turnsNow()).length;
  $("#stripText").value = "倉庫が空なら、受付は無いと返す。受付は中身を持たないから";
  await T.sendStrip();
  await until(async () => (await turnsNow()).length === n0 + 1, 5000);
  await lastDone(); await w(600);
  ts = await turnsNow();
  const a = ts[ts.length - 1];
  expect("帯の欄の文は、その問いへの答えとして送られる", a.kind === "answer" && a.check_id === cid, [a.kind, a.check_id]);
  expect("判定が出る", (a.grades || []).length > 0 && !!last(".grades"));
  const st = ts.flatMap((t) => t.checks || []).find((c) => c.id === cid).status;
  expect("答えた問いは済みになる", st === "answered", st);
  expect("答えたら帯は消え、位置の図が戻る", strip() === null && !$("#side").classList.contains("checking"));
  // 思い出せない: 記録に「分からない」で入り、問いは済む
  await T.open(S.active); await w(3400); await T.open(S.active);
  if (strip() === "s-check") {
    const c2 = S.retSnap.id;
    $("#strip [data-rcstate=unknown]").click(); await w(600);
    const s2 = (await turnsNow()).flatMap((t) => t.checks || []).find((c) => c.id === c2).status;
    expect("思い出せない: 問いは「分からない」で済みになり、帯は消える", s2 === "unknown" && strip() === null, [s2, strip()]);
  } else expect("次の確かめが出る", false, strip());
  return { ok, ng };
})()
