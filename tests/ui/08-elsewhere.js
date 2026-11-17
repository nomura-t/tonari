// delay=2
// 起動したときの差し出し: ほかの話題（片づけた話題を含む）にいま出せる確かめがあれば、1問だけ思い出すよう誘う
(async () => {
  PRE
  const a = await fresh();
  await ask("受付って何をする役？"); await lastDone();
  await until(async () => (await turnsNow())[0].checks.length > 0, 10000);     // 記録役が確かめの問いを足す
  await T.open(a); await w(300);
  const before = (await api("GET", "/api/checks/due")).n;
  await w(3400);                                                               // 開いてから3秒（試しの設定）たつ
  const due = await api("GET", "/api/checks/due");
  expect("開いて時間がたった答えの問いが、出せる問いとして数えられる", due.n === before + 1 && !!due.next, [before, due.n]);
  // a を片づけて、別の話題にいる状態で、起動したときと同じ差し出しを呼ぶ
  await api("PATCH", "/api/sessions/" + a, { archived: true });
  const b = await newTopic();
  await T.offerElsewhere(); await w(300);
  expect("ほかの話題に出せる確かめがあると、帯で誘う", strip() === "s-elsewhere", strip());
  expect("数は、いま出せる問いの数", new RegExp("（" + (await api("GET", "/api/checks/due?exclude=" + b)).n + "問）").test($("#strip .st-k").innerText), $("#strip .st-k").innerText);
  expect("帯が出ていても、話すボタンは先生役への発言のまま", $("#talkLabel").textContent === "話す");
  // あとで → 帯は下がる。もう一度呼べば、また誘える
  $("#strip [data-stripx]").click(); await w(200);
  expect("あとでで下がる", strip() === null, strip());
  await T.offerElsewhere(); await w(300);
  const target = S.elsewhere && S.elsewhere.next;
  expect("いちばん古い問いのある話題を指す", !!target);
  $("#strip [data-elsewhere]").click();
  await until(() => S.active === target.session_id && strip() === "s-check", 6000);
  expect("押すと、その話題を開いて確かめを1問出す", S.active === target.session_id && strip() === "s-check", [S.active, strip()]);
  expect("片づけた話題は、一覧に戻る", S.state.sessions.some((s) => s.id === target.session_id));
  expect("その話題で確かめが出ているあいだは、差し出しを重ねない", !S.elsewhere);
  // 先生役へ発言を送ると、差し出しは下がる
  await T.open(b, { quiet: true }); await w(200);
  await T.offerElsewhere(); await w(300);
  if (strip() === "s-elsewhere") {
    await ask("窓口はどこにある？");
    expect("発言を送ると、差し出しは下がる", strip() !== "s-elsewhere", strip());
    await lastDone();
  } else expect("差し出しが出る（ほかの話題に出せる問いが残っている）", false, strip());
  return { ok, ng };
})()
