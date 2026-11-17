// delay=2
// 別の読みでしたか: 話題の最初の問いに別の読みがあったとき、答えの下に札が出る。押すと、その読みで聞き直す
// （作り物の読みの判定役は、発言に「の知識」があれば別の読みがあったことにする）
(async () => {
  PRE
  await fresh();
  await ask("受付の知識を付けたい");
  expect("頼みの形の発言なので、予想は誘わない", strip() === null, strip());
  await lastDone();
  const alt = await until(() => last(".alt"), 8000);
  expect("話題の最初の問いに別の読みがあると、答えの下に札が出る", !!alt && !!last(".alt [data-altask]"));
  expect("札は、読んでいる答えを描き直さずに足される（答えはそのまま）", !!last(".lead") && !!last(".ans-act"));
  expect("いまの答えがどの読みで答えたかを添える", /として答えています/.test(last(".alt").innerText));
  const n = (await turnsNow()).length;
  last(".alt [data-altask]").click();
  await until(async () => (await turnsNow()).length === n + 1, 5000);
  let ts = await turnsNow();
  const t = ts[ts.length - 1];
  expect("札を押すと、その読みで聞き直す", t.final_text === "手元の受付の手引きに書いてある中身を教えて" && t.via === "click", [t.final_text, t.via]);
  await lastDone(); await w(500);
  expect("聞き直したあとは、前の答えの札を出さない", $$(".alt").length === 0, $$(".alt").length);
  // 2つ目からの問いには、判定役を回さない（前の往復が読みの手がかりになる）
  await ask("倉庫の知識を付けたい"); await lastDone(); await w(2500);
  ts = await turnsNow();
  expect("話題の2つ目からの問いには札を出さない", !ts[ts.length - 1].alt && $$(".alt").length === 0);
  // 読みが1通りの最初の問いには出さない
  await newTopic();
  await ask("受付って何をする役？"); await lastDone(); await w(2500);
  ts = await turnsNow();
  expect("別の読みが無い問いには札を出さない", !ts[0].alt && $$(".alt").length === 0);
  return { ok, ng };
})()
