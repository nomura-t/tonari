  // 場面の共通の道具（tests/ui_flow.py が、場面の「PRE」の行にこの中身を差し込む）
  const w = (ms) => new Promise((r) => setTimeout(r, ms));
  const until = async (f, ms = 20000) => { const t0 = Date.now(); for (;;) { const v = await f(); if (v) return v; if (Date.now() - t0 > ms) return null; await w(100); } };
  const T = window.tonari, S = T.S, $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
  const api = async (m, p, b) => (await fetch(p, { method: m, headers: { "X-Tonari": "1", "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined })).json();
  const turnsOf = async (sid) => (await api("GET", "/api/sessions/" + sid)).turns;
  const turnsNow = () => turnsOf(S.active);
  const doneIn = (sid) => until(async () => { const ts = await turnsOf(sid); return ts.length && ts[ts.length - 1].status === "done"; }, 25000);
  const lastDone = () => doneIn(S.active);
  // 文字で送って、サーバーが往復の種類（と、予想を誘うか）を決めるまで待つ
  const ask = async (q) => { const n = S.active ? (await turnsNow()).length : 0; await T.sendText(q); await until(async () => { const ts = await turnsNow(); return ts.length > n && ts[ts.length - 1].kind; }, 6000); await w(250); };
  const bands = () => [...$("#main").children].filter((e) => !e.hidden && !["topbar", "thread", "foot"].includes(e.id)).map((e) => e.id);
  const strip = () => ($("#strip").hidden ? null : $("#strip").className.replace("strip ", ""));
  const key = (code, k) => document.dispatchEvent(new KeyboardEvent("keydown", { code, key: k, bubbles: true }));
  const topOf = (sel) => { const e = document.querySelector(sel), th = $("#thread"); return e ? Math.round(e.getBoundingClientRect().top - th.getBoundingClientRect().top) : null; };
  const inView = (sel) => { const e = document.querySelector(sel); if (!e) return false; const r = e.getBoundingClientRect(), t = $("#thread").getBoundingClientRect(); return r.top >= t.top && r.bottom <= t.bottom; };
  const last = (sel) => document.querySelector(".turn:last-child " + sel);
  // 検算の窓は隠れている（document.hidden が真）。本人が窓を見ているときの動きを確かめるので、見えている扱いにする。
  // 隠れているあいだの動きを確かめる場面だけ、setHidden(true) にする
  let hiddenNow = false;
  Object.defineProperty(Document.prototype, "hidden", { get: () => hiddenNow, configurable: true });
  const setHidden = (v) => { hiddenNow = v; document.dispatchEvent(new Event("visibilitychange")); };
  // 新しい話題を作って開く
  const newTopic = async () => { const r = await api("POST", "/api/sessions", {}); await T.loadState(); await T.open(r.id, { quiet: true }); return r.id; };
  // 場面の始め: 予想の出し方を既定に戻し（「次の1回は誘わない」の印も消える）、新しい話題で始める
  const fresh = async () => { await api("POST", "/api/prefs", { predict: "both" }); return newTopic(); };
  // 確かめた項目。ng に残ったものが落ちた項目
  const ok = [], ng = [];
  const expect = (name, cond, got) => { (cond ? ok : ng).push(cond ? name : name + " → " + JSON.stringify(got === undefined ? cond : got)); };
  // マイクと録音の部品を作り物にする（本物のマイクは使わない・許可の問い合わせも出さない）。差し替えは型の側に付ける
  const fakeMic = () => {
    Object.defineProperty(MediaDevices.prototype, "getUserMedia", { value: async () => ({ getTracks: () => [] }), configurable: true, writable: true });
    window.MediaRecorder = class {
      static isTypeSupported() { return true; }
      start() { this.t = setInterval(() => this.ondataavailable && this.ondataavailable({ data: new Blob([new Uint8Array(2000)]) }), 100); }
      stop() { clearInterval(this.t); setTimeout(() => this.onstop && this.onstop(), 0); }
    };
    const sent = [], of = window.fetch;
    window.fetch = function (u, o) {
      if (o && o.method === "POST" && String(u).endsWith("/voice") && o.body instanceof FormData) sent.push({ kind: o.body.get("kind"), ref_turn: o.body.get("ref_turn"), check_id: o.body.get("check_id") });
      return of.apply(this, arguments);
    };
    return sent;
  };
