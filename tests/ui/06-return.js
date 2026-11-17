// delay=3
// 戻ったときの予想: 別の話題にいるあいだに届いた答えは畳んで誘う。話すキーも文字の欄も予想になる。すぐ読むこともできる
(async () => {
  PRE
  const sent = fakeMic();
  const a = await fresh();
  // 話題 a で問い、答えを待たずに話題 b へ移る。a の答えが届いたら a へ戻る
  const leaveAndReturn = async (b) => { await T.open(b, { quiet: true }); await doneIn(a); await w(400); await T.open(a); await w(300); };
  await ask("受付はなぜ倉庫に聞くの？");
  expect("同じ話題にいるあいだは、帯で誘う", strip() === "s-predict", strip());
  const b = await newTopic();
  await doneIn(a); await w(400);
  expect("別の話題にいるあいだに届いた答えは、左の列に届いたと出る", !!document.querySelector(`.sess.ready[data-id="${a}"]`));
  await T.open(a); await w(300);
  expect("戻ると、その答えは畳まれている", !!last(".fold") && !last(".lead"));
  expect("帯が入力欄の上に出て、話すボタンと文字の欄が予想になる",
    strip() === "s-fold" && $("#talkLabel").textContent === "予想を話す" && /予想/.test($("#typed").placeholder), [strip(), $("#talkLabel").textContent, $("#typed").placeholder]);
  expect("往復の列の上の帯は1本まで", bands().length <= 1, bands());
  expect("まだ読んでいない答えの中身は、右の列に出さない", !$("#sidePane .pm"));
  expect("畳んであるあいだは、開いた時刻を付けない", S.detail.turns.some((t) => !t.revealed_at));
  // 文字の欄に予想を打って送る → 予想として残り、答えが開く（先生役には送らない）
  let n = (await turnsNow()).length;
  const ta = $("#typed");
  ta.value = "倉庫しか中身を知らないから";
  ta.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", metaKey: true, ctrlKey: true, bubbles: true }));
  await until(() => last(".lead"), 5000); await w(400);
  expect("文字の欄に打った文は予想になり、先生役には送られない", (await turnsNow()).length === n && !!last(".predict"), (await turnsNow()).length - n);
  expect("答えが開き、話すボタンと文字の欄は元に戻る",
    !!last(".lead") && $("#talkLabel").textContent === "話す" && !/予想/.test($("#typed").placeholder) && strip() === null, [strip(), $("#typed").placeholder]);
  expect("取り違えたときの戻しが付く", !!last("[data-unpredict]"));
  expect("開いた答えの位置の図が、右の列に出る", !!(await until(() => $("#sidePane .pm"), 3000)));
  // すぐ読む（Enter）→ 次の1回は誘わない
  await ask("受付はどこにいる？");
  expect("予想したあとは、続けて誘う", strip() === "s-predict", strip());
  await leaveAndReturn(b);
  expect("また畳まれている", !!last(".fold"));
  expect("畳んでいるあいだ、右の列には前に開いた答えの位置の図を出す", !!$("#sidePane .pm") && !$("#sidePane .side-empty"));
  if (document.activeElement) document.activeElement.blur();
  key("Enter", "Enter");
  await until(() => last(".lead"), 4000); await w(300);
  expect("Enter ですぐ読める（予想は付かない）", !!last(".lead") && !last(".predict") && strip() === null, strip());
  await ask("窓口って何？");
  expect("すぐ読んだ次の1回は誘わない", strip() === null, strip());
  await lastDone(); await w(400);
  // 話すキーで予想する
  await ask("倉庫って何？");
  expect("その次はまた誘う", strip() === "s-predict", strip());
  const tid = S.detail.turns[S.detail.turns.length - 1].id;
  await leaveAndReturn(b);
  expect("畳まれている", !!last(".fold"));
  if (document.activeElement) document.activeElement.blur();
  key("Space", " ");
  await until(() => S.rec.phase === "recording", 4000);
  expect("畳んであるあいだの話すキーは、予想として録る", S.rec.kind === "predict" && S.rec.target === tid, [S.rec.kind, S.rec.target]);
  expect("帯に、予想の録音中と出る", !!$("#strip .st-rec"));
  key("Space", " ");
  await until(() => sent.length === 1, 6000); await w(700);
  expect("予想として送られ、答えが開く", !!sent[0] && sent[0].kind === "predict" && Number(sent[0].ref_turn) === tid && !!last(".lead"), sent[0]);
  // 待ちの往復がある話題に戻っても、確かめは出さない（待っている答えが先。確かめの途中で答えが届いて帯が消えることも無い）
  await w(3400);                                            // 開いた答えの問いが、出せる時間になる
  await T.sendText("受付はどこで休む？");                    // 送ってすぐ別の話題へ（答えはまだ届かない）
  await T.open(b, { quiet: true });
  expect("話題を移るときは、列の上に置く印を持ち越さない", S.jump === false && S.pin === null);
  await T.open(a); await w(300);
  expect("待ちの往復がある話題では、確かめを出さない", strip() !== "s-check" && !!last(".pending"), strip());
  await lastDone(); await w(500);
  expect("待っていた答えは、そのまま読める", !!last(".lead") && strip() !== "s-check", strip());
  // 声で予想したあとは、続けて誘ってよい（声の予想が文字になる前に答えが開いても、乗らなかった扱いにしない）
  await api("POST", "/api/prefs", { predict: "both" });     // 上の問いの誘いの間引きの印を消す
  await ask("受付は何を返す？");
  expect("声で予想した次の問いでも誘う", strip() === "s-predict", strip());
  await lastDone(); await w(400);
  expect("同じ話題で待っていた答えは畳まない", !last(".fold") && !!last(".lead"));
  return { ok, ng };
})()
