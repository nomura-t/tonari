// delay=3
// 主な経路: 文字で問う → 同じ話題で待つあいだだけ予想の帯 → 答えは畳まれずにそのまま読める → 送った問いが列の上に来る
(async () => {
  PRE
  await fresh();
  expect("予想の出し方の既定は、待つあいだは帯・戻ったときは畳む", S.state.prefs.predict === "both", S.state.prefs.predict);
  await ask("受付って何をする役？");
  expect("問いの形の発言では、待つあいだに予想の帯が出る", strip() === "s-predict", strip());
  expect("帯が出ていても、話すボタンは先生役への発言のまま", $("#talkLabel").textContent === "話す", $("#talkLabel").textContent);
  await lastDone(); await w(600);
  expect("同じ話題で待っていた答えは畳まれず、追加の操作なしで読める", !$(".fold") && !!last(".lead"));
  expect("答えが届いたら予想の帯は消える", strip() === null, strip());
  expect("往復の列の上の帯は1本まで", bands().length <= 1, bands());
  expect("画面に出した答えに、開いた時刻が付く", S.detail.turns.every((t) => t.revealed_at));
  await ask("受付はどこにいる？");
  expect("誘いに乗らなかった次の1回は誘わない", strip() === null, strip());
  expect("送った問いが列の上に来る", topOf(".turn:last-child") <= 24, topOf(".turn:last-child"));
  await lastDone(); await w(600);
  expect("答えが届いても、問いは上に置いたまま", topOf(".turn:last-child") <= 24, topOf(".turn:last-child"));
  expect("答えの頭が見えている", inView(".turn:last-child .lead"));
  $("#thread").dispatchEvent(new WheelEvent("wheel", { deltaY: -200 }));
  $("#thread").scrollTop -= 200; await w(100);
  const y = $("#thread").scrollTop;
  await T.loadDetail(false); await w(200);
  expect("本人が列を動かしたあとは、描き直しても位置を変えない", Math.abs($("#thread").scrollTop - y) < 4, [$("#thread").scrollTop, y]);
  await ask("整理したい");
  expect("頼みの形の発言では誘わない", strip() === null, strip());
  await lastDone(); await w(600);
  // 窓が隠れているあいだに届いた答え: 同じ話題で待っていたので畳まないが、開いた時刻は窓に戻るまで付けない
  setHidden(true);
  await ask("受付はどこで働く？");
  await lastDone(); await w(600);
  expect("窓が隠れているあいだに届いた答えには、開いた時刻を付けない", S.detail.turns.some((t) => !t.revealed_at));
  expect("同じ話題で待っていた答えは、窓が隠れていても畳まない", !$(".fold") && !!last(".lead"));
  await T.open(S.active);
  expect("話題を開くと、出した答えに開いた時刻が付く", S.detail.turns.every((t) => t.revealed_at));
  expect("読んでいない答えがあった戻りでは、確かめを出さない", strip() === null, strip());
  setHidden(false);
  expect("開いた答えのある話題で、右の列が空にならない", !$("#sidePane .side-empty") && $("#sidePane").innerText.length > 10);
  expect("読み終えた話題に、あいまいな状態の字を出さない", !$(".sess.on .sess-s"));
  return { ok, ng };
})()
