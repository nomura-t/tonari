// delay=5
// 声: 帯のキーから予想・確かめへの答えを話す。話すキーはいつも先生役への発言。マイクと録音の部品は作り物
(async () => {
  PRE
  const sent = fakeMic();
  await fresh();
  await ask("受付はなぜ倉庫に聞くの？");
  expect("誘いが出る", strip() === "s-predict", strip());
  const target = S.detail.turns[S.detail.turns.length - 1].id;
  if (document.activeElement) document.activeElement.blur();
  key("Enter", "Enter");
  await until(() => S.rec.phase === "recording", 4000);
  expect("帯のキーで、予想として話し始める", S.rec.kind === "predict" && S.rec.target === target, [S.rec.phase, S.rec.kind]);
  expect("帯と入力欄に、予想の録音中と出る", !!$("#strip .st-rec") && /予想/.test($("#recHint").textContent));
  await lastDone(); await w(600);
  expect("話している途中に届いた答えは、送るまで畳んでおく", S.hold === target && !last(".lead") && S.rec.phase === "recording");
  key("Space", " ");
  await until(() => sent.length === 1, 6000); await w(800);
  expect("予想として送られる（先生役への発言にしない）", !!sent[0] && sent[0].kind === "predict" && Number(sent[0].ref_turn) === target && !sent[0].check_id, sent[0]);
  expect("送ると答えが開く", !!last(".lead") && strip() === null && S.hold === null);
  await until(() => !last(".predict.wait"), 20000);
  expect("聞き取れなかった予想は、「文字にしています」を残さない", !last(".predict.wait"));
  // 話すキーは、いつも先生役への発言（種類を付けない）
  key("Space", " ");
  await until(() => S.rec.phase === "recording", 4000);
  expect("話すキーは先生役への発言として録る", S.rec.kind === null && !S.rec.target && !S.rec.check, [S.rec.kind]);
  key("Escape", "Escape");
  await until(() => S.rec.phase === "idle", 4000);
  expect("やめると送らない", sent.length === 1, sent.length);
  // 確かめの帯のキー
  await until(async () => (await turnsNow())[0].checks.length > 0, 10000);
  await T.open(S.active); await w(3400); await T.open(S.active);
  expect("確かめの帯が出る", strip() === "s-check", strip());
  const cid = S.retSnap && S.retSnap.id;
  if (document.activeElement) document.activeElement.blur();
  key("Enter", "Enter");
  await until(() => S.rec.phase === "recording", 4000);
  expect("帯のキーで、確かめへの答えとして話し始める", S.rec.kind === "answer" && S.rec.check === cid, [S.rec.kind, S.rec.check]);
  key("Space", " ");
  await until(() => sent.length === 2, 6000); await w(500);
  expect("その問いへの答えとして送られる", !!sent[1] && sent[1].kind === "answer" && Number(sent[1].check_id) === cid, sent[1]);
  expect("送ると帯は消える", strip() === null, strip());
  // マイクが使えなかったとき: 発言の種類の印を残さない（次に打つ・話す発言が、予想や確かめへの答えにならない）
  await api("POST", "/api/prefs", { predict: "both" });       // 誘いの間引きの印を消す
  await ask("倉庫はなぜ品物を持つの？");
  if (strip() === "s-predict") {
    Object.defineProperty(MediaDevices.prototype, "getUserMedia", { value: async () => { throw new Error("使えない"); }, configurable: true, writable: true });
    if (document.activeElement) document.activeElement.blur();
    key("Enter", "Enter");
    await until(() => /マイクが使えません/.test($("#toast").textContent), 4000);
    await w(200);
    expect("マイクが使えなかったら、種類の印を残さない", S.rec.phase === "idle" && S.rec.kind === null && S.rec.target === null && $("#talkLabel").textContent === "話す", [S.rec.phase, S.rec.kind, $("#talkLabel").textContent]);
    const n3 = (await turnsNow()).length;
    const ta3 = $("#typed");
    ta3.value = "受付は何を受け取る？";
    ta3.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", metaKey: true, ctrlKey: true, bubbles: true }));
    await until(async () => (await turnsNow()).length === n3 + 1, 5000);
    await lastDone(); await w(300);
    const t3 = (await turnsNow()).pop();
    expect("そのあと下の欄に打った文は、質問として先生役に送られる", t3.final_text === "受付は何を受け取る？" && t3.kind === "question" && !t3.check_id && !!t3.answer, [t3.kind, t3.check_id]);
    fakeMic();
  } else expect("誘いが出る（マイクの失敗の場面の前提）", false, strip());
  // 新しい話題で自動で始まった録音は、文字を打ち始めたらやめる
  $("#newSession").click();
  await until(() => S.rec.phase === "recording", 6000);
  const ta = $("#typed");
  ta.value = "打つ"; ta.dispatchEvent(new Event("input", { bubbles: true }));
  await until(() => S.rec.phase === "idle", 4000);
  expect("新しい話題の自動の録音は、打ち始めたらやめる（送らない）", S.rec.phase === "idle" && sent.length === 2, [S.rec.phase, sent.length]);
  ta.value = "";
  return { ok, ng };
})()
