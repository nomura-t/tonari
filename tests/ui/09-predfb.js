// delay=3
// 予想と答えの照らし合わせ: 答えが届くと、答えの終わりに返しが出る（読んでいる答えは描き直さない）・点も段も出さない・
// 出す字は予想と答えの字そのまま・次の一手を1つ・取れなかったらやり直せる・照らせない予想・予想を外したら返しも消える
(async () => {
  PRE
  const a = await fresh();
  // 待つあいだの予想（答えの核と違う予想） → 答えが届く → 答えの終わりに返し
  await ask("受付は何を持たない？");
  expect("問いの形の発言で誘う", strip() === "s-predict", strip());
  $("#stripText").value = "鍵を持たないんだと思う";
  await T.sendStrip(); await w(300);
  expect("答えが届く前は、返しを出さない", !!last(".predict") && !last(".pfb"));
  await lastDone();
  await until(() => last(".lead"), 5000);
  const lead = last(".lead");
  lead.__keep = 1;
  const fb = await until(() => last(".pfb[data-core]"), 10000);
  expect("答えが届くと、答えの本文の終わりに照らし合わせが出る", !!fb && !!(lead.compareDocumentPosition(fb) & Node.DOCUMENT_POSITION_FOLLOWING) && !!(fb.compareDocumentPosition(last(".ans-act")) & Node.DOCUMENT_POSITION_FOLLOWING), fb && fb.className);
  expect("返しが届いても、読んでいる答えは描き直さない", last(".lead") === lead && lead.__keep === 1);
  expect("入っていなかったときは、先生役の答えの最初の文をそのまま返す", !!fb && fb.dataset.core === "out" && /入っていませんでした/.test(fb.querySelector(".pfb-v").innerText) && /頼みを受け取り/.test(fb.querySelector(".r-miss").innerText), fb && fb.innerText);
  expect("予想に無かった決め手も、答えの字のまま返す", !!fb && /自分では持たない/.test(fb.innerText) && /予想に無かった決め手/.test(fb.innerText), fb && fb.innerText);
  expect("食い違いは、あるときだけ1文で返す", !!fb && !!fb.querySelector(".r-diff") && /鍵/.test(fb.querySelector(".r-diff").innerText));
  expect("点も成績も段も出さない", !!fb && !/\d+\s*点|％|%|ほぼ|一部が|別のところ|当たり|はずれ/.test(fb.innerText), fb && fb.innerText);
  expect("ほめ言葉を出さない", !!fb && !/すばらしい|惜しい|よく/.test(fb.innerText));
  expect("返しを使う次の一手は1つだけ", !!fb && fb.querySelectorAll(".pfb-next button").length === 1 && /なぜ違ったか/.test(fb.querySelector(".pfb-next").innerText));
  let ts = await turnsNow();
  expect("返しは往復に残る", ts[ts.length - 1].predict_fb && ts[ts.length - 1].predict_fb.state === "done", ts[ts.length - 1].predict_fb);
  // 次の一手を押すと、予想を添えて聞き返す
  const n0 = ts.length;
  fb.querySelector(".pfb-next button").click();
  await until(async () => (await turnsNow()).length === n0 + 1, 5000);
  ts = await turnsNow();
  expect("押すと、予想を添えた問いが送られる", /鍵を持たないんだと思う/.test(ts[ts.length - 1].final_text) && ts[ts.length - 1].via === "click", ts[ts.length - 1].final_text);
  await lastDone(); await w(400);
  expect("聞き返したあとの前の往復には、次の一手を出さない", !document.querySelector(`.turn[data-turn="${ts[ts.length - 2].id}"] .pfb-next`));
  // 戻ったときの予想（文字の欄・答えの核が入っている予想）にも返しが出る
  await api("POST", "/api/prefs", { predict: "both" });
  await ask("受付はなぜ倉庫に聞くの？");
  const b = await newTopic();
  await doneIn(a); await w(400);
  await T.open(a); await w(300);
  expect("戻ると畳まれている", !!last(".fold"));
  const ta = $("#typed");
  ta.value = "頼みを受けたら、中身は自分では持たないので倉庫に聞くんだと思う";
  ta.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", metaKey: true, ctrlKey: true, bubbles: true }));
  await until(() => last(".lead"), 5000);
  const fb2 = await until(() => last(".pfb[data-core]"), 10000);
  expect("戻って予想しても、照らし合わせが出る", !!fb2 && fb2.dataset.core === "in" && /入っていました/.test(fb2.querySelector(".pfb-v").innerText), fb2 && fb2.innerText);
  expect("合っていた所は、予想の中の字で返す", !!fb2 && /予想の「頼みを受け」/.test(fb2.innerText) && /決め手も合っていた所/.test(fb2.innerText) && !fb2.querySelector(".r-miss"), fb2 && fb2.innerText);
  expect("ほぼ合っていたときは短く、次の一手も出さない", !!fb2 && !fb2.querySelector(".pfb-next") && fb2.querySelectorAll(".pfb-r").length === 2);
  // 予想を外すと、返しも消える（質問として送り直す）
  const n = (await turnsNow()).length;
  last("[data-unpredict]").click();
  await until(async () => (await turnsNow()).length === n + 1, 5000);
  ts = await turnsNow();
  expect("予想を外したら、返しも外れる", !ts[ts.length - 2].predict && !ts[ts.length - 2].predict_fb, ts[ts.length - 2].predict_fb);
  await lastDone(); await w(400);
  // 本物に近い長さの答え: 照らし合わせの箱は答えの終わりにあって、開いた直後には窓に入らないことがある。
  // 上の予想の箱の中に、結果の1行が見えていて、押すと箱まで送れる
  await api("POST", "/api/prefs", { predict: "both" });
  await ask("受付の一日は、長めに言うとどう進むの？");
  $("#stripText").value = "頼みを受けて、倉庫から出して返すのを繰り返すんだと思う";
  await T.sendStrip();
  await lastDone();
  await until(() => last(".lead"), 5000); await w(150);
  const lead2 = last(".lead"), top2 = topOf(".turn:last-child .lead");
  expect("答えが出た時点で、予想の箱に知らせの行がある（あとから本文を動かさない）", !!last(".predict .pfb-cue"), last(".predict") && last(".predict").innerText);
  const cue = await until(() => last('.predict .pfb-cue[data-cue="in"]'), 10000);
  expect("照らし合わせが届くと、予想のすぐ下に結果の1行が出る", !!cue && /核心は、予想に入っていました/.test(cue.innerText) && inView(".turn:last-child .pfb-cue"), cue && cue.innerText);
  expect("届いても、読んでいる答えは動かない", last(".lead") === lead2 && Math.abs(topOf(".turn:last-child .lead") - top2) <= 1, [top2, topOf(".turn:last-child .lead")]);
  const far = !inView(".turn:last-child .pfb");
  expect("長い答えでは、照らし合わせの箱は開いた直後の窓に入りきらない（だから上に1行を出す）", far, far);
  cue.querySelector("[data-pfbjump]").click(); await w(300);
  expect("「照らし合わせを見る」を押すと、箱が窓の中に来る", inView(".turn:last-child .pfb"));
  // 照らせない予想
  await api("POST", "/api/prefs", { predict: "both" });
  await ask("窓口はいつ開くの？");
  $("#stripText").value = "分からない";
  await T.sendStrip();
  await lastDone();
  const none = await until(() => last(".pfb.none"), 10000);
  expect("照らせない予想には、そう書く", !!none && !none.querySelector(".pfb-v"), none && none.innerText);
  // 取れなかったときは、やり直しを出す
  await ask("倉庫はどこにあるの？");
  $("#stripText").value = "こわれた返しの試し";
  await T.sendStrip();
  await lastDone();
  const fail = await until(() => last(".pfb.ask [data-pfb]"), 10000);
  expect("取れなかったときは、やり直しの口を出す", !!fail);
  const tid = S.detail.turns[S.detail.turns.length - 1].id;
  if (fail) fail.click();
  await until(async () => { const t = (await turnsNow()).find((x) => x.id === tid); return t.predict_fb && t.predict_fb.state === "run"; }, 3000);
  const again = await until(async () => { const t = (await turnsNow()).find((x) => x.id === tid); return t.predict_fb && t.predict_fb.state === "fail"; }, 10000);
  expect("やり直しは、もう一度照らし合わせ役を走らせる", !!again);
  return { ok, ng };
})()
