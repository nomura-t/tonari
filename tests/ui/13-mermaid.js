// delay=1
// 関係の図（mermaid）の状態・型・表の図（v0.7）。描く部品はネットから読むので、ネットが無い所では元の記述のまま出る。
// どちらでも成り立つことだけを確かめる（読めない記述の印が付かない・名前と理由が付く）。描けたときは、大きく見る窓も確かめる
(async () => {
  PRE
  await fresh();
  await ask("関係の図を3つ見せて"); await lastDone();
  await until(() => last(".v-mermaid"), 5000);
  const ts = await turnsNow(), t = ts[ts.length - 1];
  expect("関係の図が3つ出る（状態・型・表）", t.views.length === 3 && t.views.every((v) => v.type === "mermaid") && t.views.map((v) => v.name).join("/") === "状態の図/型の図/表の図", t.views.map((v) => v.name));
  const drawn = await until(() => $$(".turn:last-child .v-mermaid .mer-wrap svg").length === 3, 12000);
  const figs = $$(".turn:last-child .v-mermaid");
  expect("読めない記述の印は付かない", !$(".turn:last-child .mermaid-src.bad"), $$(".turn:last-child .mermaid-src.bad").map((x) => x.textContent.slice(0, 40)));
  expect("図の名前と理由と「大きく見る」が付く", figs.length === 3 && figs.every((f) => f.querySelector(".v-name") && f.querySelector(".v-why") && f.querySelector("[data-zoom]")));
  expect("初めて見る形には、その形の読み方を添える（状態・型・表で別の文）", figs[0].querySelector(".v-read").textContent.includes("状態") && figs[1].querySelector(".v-read").textContent.includes("クラス") && figs[2].querySelector(".v-read").textContent.includes("表で"), figs.map((f) => f.querySelector(".v-read") && f.querySelector(".v-read").textContent.slice(0, 12)));
  if (drawn) {
    expect("描けたときは、状態・型・表の名前が図の中に出る", figs[0].textContent.includes("LISTEN") && figs[1].textContent.includes("Strategy") && figs[2].textContent.includes("ORDERS"));
    const tw = $("#thread").getBoundingClientRect();
    expect("図は、往復の列からはみ出さない", figs.every((f) => f.querySelector("svg").getBoundingClientRect().right <= tw.right + 1));
    figs[1].querySelector("[data-zoom]").click();
    await until(() => T.Zoom.isOpen(), 3000);
    const zs = $("#figZoom .fz-svg");
    expect("関係の図も、大きく見る窓に写る", !!zs && zs.getBoundingClientRect().width > figs[1].querySelector("svg").getBoundingClientRect().width && $("#fzTitle").textContent === "型の図", zs && zs.getBoundingClientRect().width);
    T.Zoom.close();
    await w(100);
  } else ok.push("（ネットが無いので、描いたあとの確かめは飛ばした）");
  figs[0].scrollIntoView({ block: "start" });
  await w(200);
  return { ok, ng };
})()
