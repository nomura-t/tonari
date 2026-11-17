// となり — 画面。話題を回しながら声で問い、答えは文字と図で読む。
// 押して話す（Space）→ もう一度押すと送る → 送ったら答えの届いた話題へ移る（⌘] でも移れる）。
(function () {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const { render: md, split, esc } = window.TonariMD;
  const M = window.TonariMap;
  const V = window.TonariViews;
  const Atlas = window.TonariAtlas;
  const H = { "X-Tonari": "1" };
  // ── キーの割り当て（設定の画面で変えられる。変えていない操作は OS の既定） ─────
  // 形は e.code を + でつないだもの（例 "Alt+KeyN"）。open だけは修飾キー＋数字（"Alt+Digit"）。
  // 保存するのは既定から変えたものだけ（prefs.keys）なので、何も変えなければ今までと同じに動く。
  const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  const MODK = IS_MAC ? "Meta" : "Alt";   // Ctrl+N・Ctrl+1〜9 はブラウザが先に取るので、Mac 以外は Alt
  const KEY_ACTIONS = [
    ["new", "新しい話題を作って話し始める"],
    ["next", "答えの届いた話題へ移る"],
    ["open", "左の列の番号で話題を開く（1〜9）"],
    ["talk", "話し始める・もう一度で送る"],
    ["reveal", "帯の声の操作（予想・確かめ）と「続きを」"],
    ["atlas", "全体の地図を開く・閉じる"],
    ["cancel", "録音をやめる（送らない）"],
  ];
  const KEY_DEFAULTS = { new: `${MODK}+KeyN`, next: `${MODK}+BracketRight`, open: `${MODK}+Digit`, talk: "Space", reveal: "Enter", atlas: `${MODK}+KeyM`, cancel: "Escape" };
  let KEYS = { ...KEY_DEFAULTS };
  const MOD_NAMES = ["Ctrl", "Alt", "Shift", "Meta"];
  const MOD_PROP = { Ctrl: "ctrlKey", Alt: "altKey", Shift: "shiftKey", Meta: "metaKey" };
  const MOD_SHOW = IS_MAC ? { Ctrl: "⌃", Alt: "⌥", Shift: "⇧", Meta: "⌘" } : { Ctrl: "Ctrl+", Alt: "Alt+", Shift: "Shift+", Meta: "Win+" };
  const CODE_SHOW = { BracketRight: "]", BracketLeft: "[", Backslash: "\\", Space: "Space", Enter: "Enter", Escape: "Esc", Comma: ",", Period: ".",
    Slash: "/", Semicolon: ";", Quote: "'", Minus: "-", Equal: "=", Backquote: "`", Tab: "Tab", Backspace: "Backspace",
    ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→", IntlRo: "\\", IntlYen: "¥" };

  function setKeys(over) {
    KEYS = { ...KEY_DEFAULTS };
    for (const [a, c] of Object.entries(over || {})) if (a in KEY_DEFAULTS && typeof c === "string") KEYS[a] = c;
  }
  function splitCombo(c) { const p = String(c || "").split("+"); const code = p.pop(); return { mods: p, code }; }
  function codeName(code) {
    if (code === "Digit") return "1〜9";
    return CODE_SHOW[code] || code.replace(/^Key/, "").replace(/^Digit/, "").replace(/^Numpad/, "テンキー");
  }
  function keyLabel(c) {
    if (!c) return "なし";
    const { mods, code } = splitCombo(c);
    return MOD_NAMES.filter((m) => mods.includes(m)).map((m) => MOD_SHOW[m]).join("") + codeName(code);
  }
  const K = (a) => keyLabel(KEYS[a]);
  function openLabel(n) { const { mods } = splitCombo(KEYS.open); return MOD_NAMES.filter((m) => mods.includes(m)).map((m) => MOD_SHOW[m]).join("") + n; }
  function hasMods(c) { return splitCombo(c).mods.length > 0; }
  function modsMatch(e, mods) { return MOD_NAMES.every((m) => !!e[MOD_PROP[m]] === mods.includes(m)); }
  function hit(e, a) {
    const c = KEYS[a];
    if (!c) return false;
    const { mods, code } = splitCombo(c);
    if (!modsMatch(e, mods)) return false;
    if (code === "Digit") return /^Digit[1-9]$/.test(e.code);
    if (e.code === code) return true;
    // 既定のままなら、配列の違うキーボード（JIS の ]、英字の配列違い）も今までどおり拾う
    if (c === KEY_DEFAULTS[a] && a === "next") return e.key === "]" || e.code === "Backslash";
    if (c === KEY_DEFAULTS[a] && a === "new") return e.key.toLowerCase() === "n";
    if (c === KEY_DEFAULTS[a] && a === "atlas") return e.key.toLowerCase() === "m";
    return false;
  }
  function comboOf(e) { return [...MOD_NAMES.filter((m) => e[MOD_PROP[m]]), e.code].join("+"); }
  // 画面の固定の表記（<kbd data-key>・ボタンの説明）を今の割り当てで書き直す
  function paintKeys() {
    $$("kbd[data-key]").forEach((k) => {
      const a = k.dataset.key;
      k.textContent = a === "open1" ? openLabel(1) : a === "open9" ? openLabel(9) : K(a);
    });
    $("#nextBtn").title = `答えの届いた話題へ（${K("next")}）`;
    $("#talk").setAttribute("aria-label", `話す・送る（${K("talk")}）`);
  }

  const S = {
    state: null,          // /api/state
    active: null,         // 開いている話題の id
    detail: null,         // /api/sessions/:id
    streams: {},          // turn_id → 途中の答えの文
    tools: {},            // turn_id → 読んでいる道具
    notes: {},            // turn_id → 待ちの知らせ
    rec: { phase: "idle", mr: null, chunks: [], stream: null, started: 0, timer: null, ctx: null, raf: 0, kind: null, target: null, check: null },
    intent: null,         // 話すキーで話すと何になるか（{kind: "predict", target} か {kind: "answer", check}）
    capture: null,        // 設定の画面でキーを取り込んでいる操作
    showReturn: false,    // 話題に戻った直後だけ、戻ったときの確かめを出す
    retDone: new Set(),   // この画面で済ませた戻ったときの確かめ
    predicting: new Set(), // 予想を送って文字になるのを待っている往復
    sideTab: "ego",
    egoId: null,
    states: {},           // 概念の名前 → 理解の状態（図に重ねる）
    editing: null,        // 直して聞き直す中の turn_id
    seenAtBoot: new Set(), // 起動した時点で読み方を見たことのある図の形（初めての形にだけ読み方を1行出す）
    seenNow: new Set(),
    refCache: {},
    typedKind: null,      // 文字の欄で送る発言の種類（図を自分の言葉で言うときは confirm）
    present: new Set(),   // この話題を開いているあいだに届いた答え（戻ったときの予想の対象にしない。畳まずに出す）
    hold: null,           // 予想を言い終えるまで畳んでおく、届いた答え（待つあいだに予想を始めたときだけ・v0.6）
    stripOff: new Set(),  // この画面で「やめる」を押した予想の誘い（turn_id）
    stripKey: "",         // いま描いてある帯（同じ帯を描き直して、打ちかけの字を消さないため）
    elsewhere: null,      // ほかの話題にある、いま出せる確かめの問い（起動したときに1回だけ差し出す）
    autoRec: false,       // 新しい話題を作ったときに自動で始まった録音か（文字を打ち始めたらやめる）
    jump: false,          // 自分が送った往復を、次に描くときに列の上へ送る
    pin: null,            // 列の上に置いた往復（本人が列を動かしたら外れる）
  };

  async function api(method, path, body) {
    const opt = { method, headers: { ...H } };
    if (body instanceof FormData) opt.body = body;
    else if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    const r = await fetch(path, opt);
    if (!r.ok) {
      let m = r.statusText;
      try { m = (await r.json()).detail || m; } catch (e) { /* 本文なし */ }
      throw new Error(m);
    }
    return r.json();
  }

  // ── 知らせの受け口（ndjson を開きっぱなし） ──────────────────
  async function listen() {
    for (;;) {
      try {
        const r = await fetch("/api/events", { headers: H });
        const rd = r.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await rd.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let k;
          while ((k = buf.indexOf("\n")) >= 0) {
            const line = buf.slice(0, k);
            buf = buf.slice(k + 1);
            if (line.trim()) onEvent(JSON.parse(line));
          }
        }
      } catch (e) { /* 切れたら少し待ってつなぎ直す */ }
      await new Promise((ok) => setTimeout(ok, 1500));
    }
  }

  let railTimer = 0;
  function refreshRailSoon() { clearTimeout(railTimer); railTimer = setTimeout(loadState, 150); }

  function onEvent(ev) {
    if (ev.t === "delta") {
      S.streams[ev.turn_id] = (S.streams[ev.turn_id] || "") + ev.text;
      if (ev.session_id === S.active) paintStream(ev.turn_id);
      return;
    }
    if (ev.t === "tool") { S.tools[ev.turn_id] = ev.name; if (ev.session_id === S.active) paintStream(ev.turn_id); return; }
    if (ev.t === "reset") { delete S.streams[ev.turn_id]; return; }
    if (ev.t === "predict_failed") {   // 声の予想を聞き取れなかった（「文字にしています」のまま残さない）
      S.predicting.delete(ev.turn_id);
      if (ev.session_id === S.active) { paintThread(false); paintStrip(); toast("予想を聞き取れませんでした"); }
      return;
    }
    if (ev.t === "turn" && ev.note) S.notes[ev.turn_id] = ev.note;
    if (ev.t === "done") {
      if (ev.session_id === S.active) {
        S.present.add(ev.turn_id);   // この話題で待っていた答えは畳まない（別の話題にいるあいだに届いた答えだけ、戻ったときに畳む）
        if (predictingFor(ev.turn_id)) S.hold = ev.turn_id;   // 予想を話している・打っている途中に届いた答えは、送るまで畳んでおく
      }
      delete S.streams[ev.turn_id];
      const covered = document.hidden || Atlas.isOpen();   // 窓が隠れている・全体の地図が往復の列を覆っている
      if (ev.session_id === S.active && !covered) api("POST", `/api/sessions/${ev.session_id}/read`).catch(() => {});
      else chime();
      if (Atlas.isOpen()) Atlas.news(S.atlasNews = (S.atlasNews || 0) + 1);
    }
    // 記録役が、届いた答えに記録用の地図と確かめの問いを足した（v0.5）。答えの表示は変わらないので、地図だけ描き直す
    // 読んでいる最中の答えを描き直さない（選んだ字と図が消える）。往復の中身だけ取り直して、右の地図を描く
    if (ev.t === "alt") {
      if (ev.session_id === S.active) api("GET", `/api/sessions/${S.active}`).then((d) => {
        if (d.session.id !== S.active) return;
        S.detail = d;
        const t = d.turns.find((x) => x.id === ev.turn_id), box = document.querySelector(`.turn[data-turn="${ev.turn_id}"] .answer`);
        if (!t || !box || box.querySelector(".alt") || !box.querySelector(".ans-act")) return;
        box.querySelector(".ans-act").insertAdjacentHTML("beforebegin", altHTML(t));
      }).catch(() => {});
      return;
    }
    // 予想と答えの照らし合わせが走り始めた・届いた（v0.6）。読んでいる最中の答えは描き直さず、予想の下の箱だけを差し替える
    if (ev.t === "predict_fb") {
      if (ev.session_id === S.active) api("GET", `/api/sessions/${S.active}`).then((d) => {
        if (d.session.id !== S.active) return;
        S.detail = d;
        const t = d.turns.find((x) => x.id === ev.turn_id), box = document.querySelector(`.turn[data-turn="${ev.turn_id}"] .answer`);
        if (!t || !box || box.querySelector(".fold, .folded")) return;
        const old = box.querySelector(".pfb"), html = pfbHTML(t);
        const at = box.querySelector(".checks, .lookup, .alt, .ans-act");   // 答えの本文の終わり（確かめ・入口・操作の前）
        if (old) old.outerHTML = html;
        else if (at && box.querySelector(".predict:not(.wait)")) at.insertAdjacentHTML("beforebegin", html);
        // 上の予想の箱の中の1行も、同じ結果に差し替える
        const pre = box.querySelector(".predict:not(.wait)"), cue = pre && pre.querySelector(".pfb-cue");
        if (cue) cue.outerHTML = pfbCue(t);
        else if (pre) pre.insertAdjacentHTML("beforeend", pfbCue(t));
      }).catch(() => {});
      return;
    }
    if (ev.t === "recorded") {
      refreshRailSoon();
      if (ev.session_id === S.active) api("GET", `/api/sessions/${S.active}`).then((d) => { if (d.session.id === S.active) { S.detail = d; paintSide(); } }).catch(() => {});
      return;
    }
    if (["turn", "done", "session", "read"].includes(ev.t)) {
      refreshRailSoon();
      if (ev.session_id === S.active && ev.t !== "read") loadDetailSoon();
    }
    if (ev.t === "mastery") { loadStates().then(() => { paintSide(); if (S.detail) paintThread(false); }); }
  }

  let detailTimer = 0;
  function loadDetailSoon() { clearTimeout(detailTimer); detailTimer = setTimeout(() => loadDetail(false), 120); }

  // ── 読み込み ──────────────────────────────────────────
  async function loadState() {
    S.state = await api("GET", "/api/state");
    setKeys(S.state.prefs.keys);
    paintKeys();
    paintRail();
    paintTalk();
    if ($("#settings").open) paintSettings();
  }

  async function loadDetail(scroll = true, force = false) {
    if (!S.active) { S.detail = null; paintThread(); paintStrip(); return; }
    const want = S.active, got = await api("GET", `/api/sessions/${want}`);
    if (want !== S.active) return 0;   // 応答が戻る前に話題を移った（前の話題の中身を、いまの話題として描かない）
    S.detail = got;
    for (const t of S.detail.turns) if (t.predict) S.predicting.delete(t.id);
    if (S.hold && !S.detail.turns.some((t) => t.id === S.hold)) S.hold = null;
    const fresh = revealShown(force);
    if (fresh) S.showReturn = false;   // 読んでいない答えがあるときは、そちらが先（確かめは次に戻ったとき）
    paintThread(scroll);
    paintTop();
    paintStrip();
    if (fresh) paintSide();
    return fresh;
  }

  // 画面に出した答えに、開いた時刻を付ける（v0.6）。答えを畳まない出し方では、読める形で画面に出たときが「開いた」。
  // 開いた時刻は戻ったときの確かめの時計なので、本人が別の話題にいるあいだに届いた答えには、ここで初めて付く
  function revealShown(force = false, note = true) {
    const d = S.detail;
    if (!d || Atlas.isOpen() || (document.hidden && !force)) return 0;
    const ids = d.turns.filter((t) => t.status === "done" && t.answer != null && !t.revealed_at && t.id !== S.hold && !foldable(t)).map((t) => t.id);
    if (!ids.length) return 0;
    const now = Date.now() / 1000;
    for (const t of d.turns) if (ids.includes(t.id)) t.revealed_at = now;
    api("POST", `/api/sessions/${d.session.id}/reveal`, { turn_ids: ids, note }).catch(() => {});
    return ids.length;
  }

  async function loadStates() {
    const r = await api("GET", "/api/concepts");
    S.states = {};
    for (const c of r.concepts) if (c.state) S.states[c.label] = c.state;
    S.allConcepts = r.concepts;
  }

  async function open(id, opts = {}) {
    if (S.rec.phase !== "idle") return;   // 録音中・マイクの準備中・送っている途中は移らない（声の相手の話題がずれる）
    S.jump = false;                       // 列の上に置く印は、送った話題の中だけで使う
    S.pin = null;
    S.active = id;
    S.editing = null;
    typeFor(null);   // 「この図を自分の言葉で言う」の文字の欄は、話題を移ったら持ち越さない
    try { localStorage.setItem("tonari.active", String(id)); } catch (e) { /* 保存できなくても動く */ }
    paintRail();
    S.showReturn = false;   // 前の話題の確かめを持ち越さない
    S.retSnap = null;
    S.hold = null;
    // 話題を開くのは本人の操作なので、窓が隠れていても答えを開いたとみなす。読んでいない答えがあった戻りでは、
    // 確かめを出さない（新しい答えを読むのが先。確かめは次に戻ったとき）
    const fresh = await loadDetail(true, true);
    api("POST", `/api/sessions/${id}/read`).catch(() => {});
    S.egoId = null;
    S.showReturn = !opts.quiet && !fresh && !foldTarget();   // 畳んである答え（まだ読んでいない）がある戻りでも、確かめは出さない
    S.retSnap = S.detail ? S.detail.return_check : null;
    if (retCheck()) paintThread(true);   // 確かめの問いの元の答えを畳んで描き直す
    paintStrip();
    paintSide();
    if (!opts.quiet) showResume();
  }

  // ── 読む前の予想と、戻ったときの確かめ（v0.3・研究 d） ─────────────
  // 予想: 届いた答えを開く前に、自分の問いを見て一言予想する（予想の直後に答え合わせをする順にする）。
  // 戻ったとき: 前に開いた答えの確かめの問いを、その答えを畳んで1つだけ出す（話題を回す動きを間隔反復にする）。
  // v0.6 の予想の出し方（設定の「答えを読む前の予想」）。誘う往復はサーバーが決める（t.offer＝問いの形の発言だけ・
  // 誘いに乗らなかった次の1回は誘わない）。
  //   both（既定）… 同じ話題で待つあいだは、答えを畳まずに入力欄の上の帯で誘う。別の話題にいるあいだに届いた答えは、
  //                 戻ったときに畳んで誘う（声で話しても、文字で打っても予想になる。すぐ読むこともできる）
  //   wait … 待つあいだだけ誘う（答えは畳まない）　off … 出さない
  // 確かめの問いも、往復の列の上ではなく入力欄の上の帯に出す
  const predictMode = () => (S.state ? S.state.prefs.predict : "both");
  const PENDING = ["recorded", "transcribing", "fixing", "thinking"];
  function foldable(t) {
    return predictMode() === "both" && t.status === "done" && t.answer != null && !t.revealed_at && t.offer === "predict" &&
      !t.predict && !S.predicting.has(t.id) && !S.present.has(t.id) && S.hold !== t.id;
  }

  // 答えを待つあいだの予想の誘い（wait）。サーバーが決めた往復（offer）のうち、まだ予想が無く、待ちの途中のもの
  function offerTarget() {
    const d = S.detail;
    if (!d || predictMode() === "off") return null;
    const t = [...d.turns].reverse().find((x) => x.offer === "predict");
    if (!t || t.predict || S.predicting.has(t.id) || S.stripOff.has(t.id)) return null;
    return PENDING.includes(t.status) || S.hold === t.id ? t : null;
  }

  // 入力欄の上の帯に出すもの。確かめ → 畳んだ答えの予想 → 待つあいだの予想の誘い、の順
  function stripState() {
    const rc = retCheck();
    if (rc) return { kind: "answer", rc };
    const f = foldTarget();
    if (f) return { kind: "fold", t: f };
    const t = offerTarget();
    if (t) return { kind: "predict", t };
    return S.elsewhere ? { kind: "elsewhere", e: S.elsewhere } : null;
  }

  // 起動したときに1回だけ、ほかの話題（片づけた話題を含む）の確かめを1問、道具の側から差し出す（v0.6）。
  // 押して出すだけの入口はほとんど使われない（研究 g1 の 1-1）。数は、やれば減る数だけを出す（g4 の 2-1）
  async function offerElsewhere() {
    if (stripState()) return;
    const d = await api("GET", "/api/checks/due" + (S.active ? `?exclude=${S.active}` : "")).catch(() => null);
    if (d && d.n > 0 && d.next) { S.elsewhere = d; paintStrip(); }
  }
  async function goElsewhere() {
    const e = S.elsewhere;
    S.elsewhere = null;
    if (!e || !e.next) { paintStrip(); return; }
    if (e.next.archived) await api("PATCH", `/api/sessions/${e.next.session_id}`, { archived: false });
    await loadState();
    await open(e.next.session_id);
  }

  // 予想を話している・帯の欄に打っている途中か（その往復の答えが届いても、送るまで畳んでおく）
  function predictingFor(tid) {
    if (S.rec.phase !== "idle" && S.rec.kind === "predict" && S.rec.target === tid) return true;
    const st = stripState(), ta = $("#stripText");
    return !!(st && st.kind === "predict" && st.t.id === tid && ta && ta.value.trim());
  }

  function foldTarget() {
    const d = S.detail;
    return d ? d.turns.find((t) => foldable(t)) : null;
  }

  function retCheck() {
    // 話題を開いた瞬間に決まった問いだけを出す（開いたまま2分たっても、途中で帯は出さない）
    const rc = S.retSnap;
    if (!rc || !S.showReturn || S.retDone.has(rc.id) || foldTarget()) return null;
    // 待ちの往復がある話題では出さない（待っている答えが先。確かめに答えている途中で答えが届いて、帯が消えることも無くなる）
    if (S.detail && S.detail.turns.some((t) => PENDING.includes(t.status)) && !(S.rec.phase !== "idle" && S.rec.check === rc.id)) return null;
    return rc;
  }

  // 話すキーと文字の欄の意味が変わるのは、戻ったときに答えが畳まれているあいだだけ（どちらも予想になる。帯と話すボタンと
  // 文字の欄がそう示す）。それ以外では、話すキーと文字の欄はいつも先生役への発言で、待つあいだの予想と確かめへの答えは、
  // 帯の欄と帯のボタンから送る
  function setIntent() {
    if (S.rec.phase !== "idle") return;
    const f = foldTarget();
    S.intent = f ? { kind: "predict", target: f.id } : null;
    if (!S.typedKind) $("#typed").placeholder = f ? `予想を打つ（${SEND_SHOW} で送る）` : TYPED_HINT;
    $("#composer").classList.toggle("predicting", !!f);   // 文字の欄の枠の色でも示す（表示は2つ以上重ねる・研究 g3 の 4-3）
    paintTalk();
  }

  // 入力欄の上の帯（v0.6）。確かめの問いと、待つあいだの予想の誘い。帯の中に打つ欄と声のボタンを持ち、
  // 下の入力欄（先生役への発言）の意味は変えない。試験でなく「当ててみる」調子にする（ほめ言葉・点数は出さない）
  function paintStrip(fresh = -1) {
    const box = $("#strip");
    const st = stripState();
    if (!st) {
      if (!box.hidden || S.stripKey) { box.hidden = true; box.innerHTML = ""; S.stripKey = ""; }
      setIntent();
      return;
    }
    const rec = S.rec.phase === "recording" && S.rec.kind === (st.kind === "fold" ? "predict" : st.kind);
    const held = st.kind === "predict" && S.hold === st.t.id;
    const key = st.kind === "answer" ? `a${st.rc.id}:${(st.rc.hints || []).length}:${rec}`
      : st.kind === "elsewhere" ? `e${st.e.n}:${st.e.next.session_id}` : `${st.kind[0]}${st.t.id}:${held}:${rec}`;
    if (key === S.stripKey && !box.hidden) { setIntent(); return; }
    const old = $("#stripText"), keep = old && S.stripKey.split(":")[0] === key.split(":")[0] ? old.value : "", hadFocus = old && document.activeElement === old;
    const voice = (label) => rec
      ? `<span class="st-rec">録音しています。もう一度 <kbd>${K("talk")}</kbd> で送る・<kbd>${K("cancel")}</kbd> でやめる</span>`
      : `<button class="primary" data-stripvoice="1">${label}<kbd>${K("reveal")}</kbd></button>`;
    const field = (ph) => `<textarea id="stripText" rows="1" placeholder="${ph}（${SEND_SHOW} で送る）"></textarea>` +
      `<button class="ghost" data-stripsend="1">送る</button>`;
    if (st.kind === "answer") {
      const rc = st.rc, shown = rc.hints || [], n = rc.hints_n || 0;
      const hints = shown.length ? `<ol class="rc-hints">${shown.map((h, i) => `<li${i === fresh ? ` class="rc-new"` : ""}><span>ヒント${i + 1}</span>${esc(h)}</li>`).join("")}</ol>` : "";
      const more = n > shown.length ? `<button class="ghost small" data-rchint="${rc.id}">${shown.length ? "もう一段ヒント" : "ヒントをもらう"}</button>` : "";
      box.className = "strip s-check";
      box.innerHTML = `<div class="st-head"><span class="st-k">前に読んだ答えから、ひとつ思い出してみる${rc.qtype ? `<i>${esc(rc.qtype)}</i>` : ""}</span>` +
        `<button class="link" data-stripx="1" title="いまは答えない（次にこの話題に戻ったときに、また出ます）">あとで</button></div>` +
        `<p class="st-q">${esc(rc.q)}</p>` + hints +
        `<div class="st-row">${field("思い浮かんだことを打つ")}${voice("声で言う")}</div>` +
        `<div class="st-act">${more}<button class="ghost small" data-rcstate="unknown" data-rcid="${rc.id}">思い出せない</button>` +
        `<button class="ghost small" data-rcstate="skipped" data-rcid="${rc.id}">飛ばす</button>` +
        `<span class="tiny">元の答えは畳んであります。先生役が、合っている所と違う所を返します。</span></div>`;
    } else if (st.kind === "elsewhere") {
      box.className = "strip s-elsewhere";
      box.innerHTML = `<div class="st-head"><span class="st-k">ほかの話題に、まだ答えていない確かめの問いがあります（${st.e.n}問）</span>` +
        `<button class="link" data-stripx="1" title="いまはやらない">あとで</button></div>` +
        `<div class="st-act"><button class="primary" data-elsewhere="1">1問だけ思い出してみる</button>` +
        `<span class="tiny">いちばん古い問いのある話題を開いて、1問だけ出します。${st.e.next.archived ? "片づけた話題は一覧に戻します。" : ""}</span></div>`;
    } else if (st.kind === "fold") {
      // 戻ったときに畳んである答え。このあいだは、話すキーも下の文字の欄も予想になる（帯がそれを入力欄のすぐ上で示す）
      box.className = "strip s-fold";
      box.innerHTML = `<div class="st-head"><span class="st-k">読む前に、予想を一言どうぞ（任意）</span>` +
        `<button class="link" data-reveal="${st.t.id}">すぐ読む<kbd>${K("reveal")}</kbd></button></div>` +
        (rec ? `<p class="st-line"><span class="st-rec">予想を録音しています。もう一度 <kbd>${K("talk")}</kbd> で送る・<kbd>${K("cancel")}</kbd> でやめる</span></p>`
          : `<p class="st-line">いま<kbd>${K("talk")}</kbd>で話す内容と、下の欄に打って送る内容は、予想として答えの上に残ります（先生役には送りません）。</p>`);
    } else {
      box.className = "strip s-predict";
      box.innerHTML = `<div class="st-head"><span class="st-k">${held ? "答えが届きました。予想を送ると開きます" : "答えを待つあいだに、予想を一言どうぞ（任意）"}</span>` +
        (held ? `<button class="link" data-release="${st.t.id}">予想せずに読む</button>`
          : `<button class="link" data-stripx="1" title="この問いでは予想しない">やめる</button>`) + `</div>` +
        `<div class="st-row">${field("予想を打つ")}${voice("声で予想")}</div>` +
        `<p class="tiny">予想は先生役には送らず、届いた答えの上に残ります。</p>`;
    }
    box.hidden = false;
    S.stripKey = key;
    const ta = $("#stripText");
    if (ta) { ta.value = keep; fitStrip(); if (hadFocus) ta.focus(); }
    setIntent();
  }

  function fitStrip() {
    const ta = $("#stripText");
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight + 2, 120) + "px";
  }

  // 帯の欄の文を送る。確かめへの答えは先生役が判定し、予想は先生役に送らずに答えの上に残す
  async function sendStrip() {
    const st = stripState(), ta = $("#stripText");
    const text = ta ? ta.value.trim() : "";
    if (!st || st.kind === "fold" || st.kind === "elsewhere" || !text) return;
    ta.value = "";
    if (st.kind === "answer") {
      const id = st.rc.id;
      try { await api("POST", `/api/sessions/${S.active}/text`, { text, kind: "answer", check_id: id }); }
      catch (e) { ta.value = text; toast("送れませんでした: " + e.message); return; }
      S.retDone.add(id);
      S.showReturn = false;
      S.jump = true;
      paintStrip();
      paintSide();
      await loadState();
      loadDetail(false);
      return;
    }
    if (!(await sendPredictText(st.t.id, text)) && $("#stripText")) $("#stripText").value = text;   // 残せなかったら字を戻す
  }

  // 文字の予想を、その往復に書き添える（先生役には送らない）
  async function sendPredictText(tid, text) {
    try { await api("POST", `/api/sessions/${S.active}/predict`, { turn_id: tid, text }); } catch (e) { toast("予想を残せませんでした: " + e.message); return false; }
    const t = S.detail && S.detail.turns.find((x) => x.id === tid);
    if (t) { t.predict = text; t.predict_via = "text"; }
    await afterPredict(tid);
    return true;
  }

  // 予想を送ったあと。答えがもう届いていれば開き、まだなら待ちの表示に予想を添える
  async function afterPredict(tid) {
    if (S.hold === tid) S.hold = null;
    const t = S.detail && S.detail.turns.find((x) => x.id === tid);
    if (t && t.status === "done" && !t.revealed_at) { await reveal(tid); return; }
    paintThread(false);
    paintStrip();
    paintSide();
  }

  // 帯の声のボタン（と、答えを開くキー）: 予想か、確かめへの答えとして話し始める
  function stripVoice() {
    const st = stripState();
    if (!st || st.kind === "elsewhere" || S.rec.phase !== "idle") return;
    if (st.kind === "answer") startRec("answer", { check: st.rc.id });
    else startRec("predict", { target: st.t.id });   // 畳んだ答え（fold）のときも、その答えへの予想
  }

  // 帯を閉じる。確かめは「あとで」（問いは残り、次に戻ったときにまた出る）。予想の誘いはこの問いでは出さない
  function closeStrip() {
    const st = stripState();
    if (!st) return;
    if (st.kind === "answer") { S.opening = st.rc.turn_id; S.showReturn = false; paintThread(false); }
    else if (st.kind === "elsewhere") S.elsewhere = null;
    else if (st.kind === "fold") { reveal(st.t.id); return; }
    else { S.stripOff.add(st.t.id); releaseHold(st.t.id); }
    paintStrip();
    paintSide();
  }

  // 予想の途中で届いて畳んでおいた答えを、予想せずに開く
  function releaseHold(tid) {
    if (S.hold !== tid) return;
    S.hold = null;
    S.opening = tid;
    revealShown(true);
    paintThread(false);
    paintStrip();
    paintSide();
  }

  async function askHint(id) {
    const rc = S.retSnap;
    if (!rc || rc.id !== id) return;
    const r = await api("POST", `/api/checks/${id}/hint`);
    const before = (rc.hints || []).length;
    rc.hints = r.hints;
    rc.hints_n = r.hints_n;
    paintStrip(r.hints.length > before ? r.hints.length - 1 : -1);
  }

  async function reveal(tid) {
    await api("POST", `/api/turns/${tid}/reveal`);
    const t = S.detail && S.detail.turns.find((x) => x.id === tid);
    if (t) t.revealed_at = Date.now() / 1000;
    S.opening = tid;   // 開いた答えだけ、短く現れる
    paintThread(false);
    paintStrip();
    paintSide();
  }

  // ── 左の話題の列 ──────────────────────────────────────
  const PHASE = {
    recorded: ["送りました", "busy"], transcribing: ["声を文字にしています", "busy"], fixing: ["聞き違いを直しています", "busy"],
    thinking: ["先生役が答えを書いています", "busy"], done: ["", "idle"], error: ["止まりました", "err"],
  };

  function sessionPhase(s) {
    if (S.rec.phase !== "idle" && s.id === S.active) return ["録音中", "rec"];
    if (s.unread > 0 && s.id !== S.active) return ["答えが届きました", "ready"];
    if (!s.last) return ["話しかけてください", "idle"];
    return PHASE[s.last.status] || ["", "idle"];
  }

  function ago(t) {
    if (!t) return "";
    const d = Date.now() / 1000 - t;
    if (d < 60) return "いま";
    if (d < 3600) return `${Math.floor(d / 60)}分前`;
    if (d < 86400) return `${Math.floor(d / 3600)}時間前`;
    return `${Math.floor(d / 86400)}日前`;
  }

  function paintRail() {
    const st = S.state;
    if (!st) return;
    const list = $("#sessions");
    list.innerHTML = st.sessions.map((s, i) => {
      const [label, cls] = sessionPhase(s);
      const last = s.last ? (s.last.title || s.last.final_text || "") : "";
      return `<button class="sess ${cls}${s.id === S.active ? " on" : ""}" data-id="${s.id}" aria-current="${s.id === S.active}">` +
        `<span class="sess-k">${i < 9 ? openLabel(i + 1) : ""}</span>` +
        `<span class="sess-t">${esc(s.title)}</span>` +
        (label ? `<span class="sess-s"><i class="dot"></i>${label}${s.unread > 1 ? `（${s.unread}件）` : ""}</span>` : "") +
        `<span class="sess-l">${esc(last)}</span>` +
        `<span class="sess-m">${s.concepts ? `概念 ${s.concepts}` : ""}<span>${ago(s.updated_at)}</span></span></button>`;
    }).join("") || `<p class="rail-empty">まだ話題がありません。<br><kbd>${K("new")}</kbd> で作ってすぐ話せます。</p>`;
    // 片づけた話題（v0.6）。押すと一覧に戻して開く
    const ar = st.archived || [];
    $("#archived").hidden = !ar.length;
    $("#archCount").textContent = ar.length;
    $("#archList").innerHTML = ar.map((a) => `<button class="arch" data-restore="${a.id}" title="一覧に戻して開く">` +
      `<span class="arch-t">${esc(a.title)}</span><span class="arch-m">${ago(a.updated_at)}・${a.turns}往復` +
      `${a.open_checks ? `・確かめ ${a.open_checks}問` : ""}</span></button>`).join("");
    const ready = st.sessions.filter((s) => s.unread > 0 && s.id !== S.active).length;
    $("#nextCount").textContent = ready ? `${ready}` : "";
    $("#nextBtn").classList.toggle("has", ready > 0);
    const sc = st.scribe;
    $("#scribeMode").value = st.prefs.scribe;
    $("#autoNext").checked = st.prefs.auto_next === "1";
    $("#predictPref").value = st.prefs.predict;
    $("#textSize").value = st.prefs.text_size || "m";
    $("#chimePref").checked = st.prefs.chime !== "0";
    document.documentElement.dataset.size = st.prefs.text_size || "m";
    $("#autoLookup").checked = st.prefs.auto_lookup === "1";
    const lc = st.local || {};
    const offOpt = $('#scribeMode option[value="off"]');
    if (offOpt) offOpt.textContent = lc.apple === false ? "端末だけ（Haas）" : "端末だけ（Apple）";
    $("#scribeInfo").textContent = (sc.active ? "Scribe 使用中" : `Scribe 停止（${sc.why}）` +
      (lc.active ? (lc.apple === false ? "・端末の Haas で聞く" : "・端末の Haas と2本で聞く") : lc.apple === false ? "・聞き取りが使えません" : "")) +
      (sc.month_sec ? `・今月 ${Math.round(sc.month_sec / 60)}分` : "");
    $("#counts").textContent = `概念 ${st.counts.concepts}・関係 ${st.counts.relations}・分かる ${st.counts.known}`;
    document.title = ready ? `となり（${ready}）` : "となり";
    $("#empty").hidden = st.sessions.length > 0;
    $("#main").hidden = !S.active;
  }

  // ── 上の帯と「前回」の手がかり ──────────────────────────
  function paintTop() {
    const s = S.detail && S.detail.session;
    if (!s) return;
    const t = $("#title");
    if (document.activeElement !== t) t.value = s.title;
    $("#modelChip").textContent = s.model;
    $$("#detail button").forEach((b) => b.classList.toggle("on", b.dataset.detail === (s.detail || "auto")));
  }

  function showResume() {
    const d = S.detail;
    const box = $("#resume");
    if (!d || !d.turns.length) { box.hidden = true; return; }
    const turns = d.turns;
    const last = turns[turns.length - 1];
    const sess = (S.state.sessions || []).find((x) => x.id === S.active);
    const where = last.status === "done" ? (foldTarget() ? "答えは開く前です" : "答えは下にあります") : last.status === "error" ? "止まっています" : "先生役が答えを書いています";
    box.innerHTML = `<span class="rs-k">前回</span><span class="rs-q">${esc(last.title || last.final_text || "")}</span>` +
      `<span class="rs-m">${ago(last.created_at)}・${where}${sess && sess.concepts ? `・この話題の概念 ${sess.concepts}` : ""}</span>`;
    box.hidden = false;
    box.classList.remove("flash");
    void box.offsetWidth;
    box.classList.add("flash");
  }

  // ── 往復の列 ──────────────────────────────────────────
  function saidHTML(t) {
    let h = esc(t.final_text || "");
    if (t.final_text === t.fixed_text) {
      for (const [i, e] of (t.edits || []).entries()) {
        const to = esc(e.to);
        h = h.replace(to, `<mark class="edit" data-i="${i}" title="聞き取りでは「${esc(e.from)}」（${esc(e.why)}）">${to}</mark>`);
      }
      for (const u of t.unsure || []) {
        const sp = esc(u.span);
        h = h.replace(sp, `<span class="unsure" title="決めきれなかった候補: ${esc(u.options.join(" / "))}">${sp}</span>`);
      }
    }
    return h;
  }

  function stageLine(t) {
    const p = [];
    if (t.via === "voice") p.push(`声 ${t.audio_sec ? t.audio_sec.toFixed(1) + "秒" : ""}`);
    else if (t.via === "click") p.push("図から");
    else if (t.via === "research") p.push("Web で調べる");
    else p.push("文字");
    const st = t.stage || {};
    if (st.stt != null) p.push(`文字に ${(st.stt / 1000).toFixed(1)}秒`);
    if (st.fix != null) p.push(`直し ${(st.fix / 1000).toFixed(1)}秒`);
    if (st.tutor != null) p.push(`答え ${Math.round(st.tutor / 1000)}秒`);
    if (st.research != null) p.push(`調べ ${Math.round(st.research / 1000)}秒`);
    if (st.scribe_mode && t.via === "voice") p.push(engineLabel(t));
    return p.join("・");
  }

  // 聞き取りに使ったエンジン（Apple の無い PC では2本目だけになる）
  function engineLabel(t) {
    const e = [t.scribe_text != null && "Scribe", t.haas_text != null && "Haas", t.apple_text != null && "Apple"].filter(Boolean);
    return e.length === 1 ? `${e[0]} のみ` : e.join("＋");
  }

  function checksHTML(t) {
    if (!t.checks || !t.checks.length) return "";
    const typed = t.checks.filter((c) => c.qtype);
    if (typed.length) {
      // v0.3 の問いは答えの下では見せず、次にこの話題に戻ったときに答えを畳んで1つずつ出す
      const open = typed.filter((c) => c.status === "open").length;
      const JA = { answered: "答えた", unknown: "分からない", skipped: "飛ばした", known: "分かる", shaky: "あやしい" };
      const done = typed.filter((c) => c.status !== "open");
      return `<div class="checks"><div class="ck-head">確かめ</div>` +
        (open ? `<p class="ck-note">確かめの問い ${open}問は、次にこの話題に戻ったときに、この答えを畳んで出します。</p>` : "") +
        done.map((c) => `<p class="ck-past"><span class="ck-st">${JA[c.status] || esc(c.status)}</span>${esc(c.q)}</p>`).join("") + `</div>`;
    }
    const JA = { known: "分かる", shaky: "あやしい", unknown: "分からない" };
    return `<div class="checks"><div class="ck-head">確かめ</div>` + t.checks.map((c) => {
      const done = c.status !== "open";
      return `<div class="ck${done ? " done" : ""}" data-check="${c.id}">` +
        `<p class="ck-q">${esc(c.q)}</p>` +
        `<details class="ck-a"><summary>答えを見る</summary><p>${esc(c.a || "")}</p></details>` +
        `<div class="ck-btns">${["known", "shaky", "unknown"].map((k) => `<button class="sb s-${k}${c.status === k ? " on" : ""}" data-ckstate="${k}">${JA[k]}</button>`).join("")}` +
        `<button class="ghost" data-ckvoice="${c.id}">声で答える</button></div></div>`;
    }).join("") + `</div>`;
  }

  function gradesHTML(t) {
    if (!t.grades || !t.grades.length) return "";
    const JA = { hit: "当たり", partial: "半分", miss: "まだ" };
    // C2: 戻ったときの問いが当たりで記録されたら、読んでから答えるまでの間を事実だけ添える（最初の1行だけ）
    const at = t.recall ? t.grades.findIndex((g) => g.result === "hit" && g.recorded) : -1;
    return `<div class="grades">` + t.grades.map((g, i) => `<div class="gr g-${esc(g.result)}"><b>${JA[g.result] || "?"}</b>` +
      `<span>${esc(g.concept)} と ${esc(g.target)}</span>${g.evidence ? `<q>${esc(g.evidence)}</q>` : ""}` +
      `${g.result !== "miss" && !g.verified ? `<em>根拠の字が発言に無いので記録していません</em>` : ""}` +
      `${i === at ? `<span class="gr-recall">${esc(t.recall.text)}</span>` : ""}</div>`).join("") + `</div>`;
  }

  // 答えの本文の [[view:N]] の置き場所に図を入れる。最初の段落が図でなければ、言い切りとして大きく出す
  function viewHTML(v, vi, extra = {}) {
    const first = !S.seenAtBoot.has(v.type);
    if (first) S.seenNow.add(v.type);
    return V.render(v, { states: S.states, firstTime: first, vi, ...extra });
  }

  // 答えの図（たとえの塊は図に数えない添え物なので飛ばす）
  const mainIdx = (views) => (views || []).findIndex((v) => v.type !== "analogy" && v.type !== "think");

  // 考えの塊（v0.5）: 先生役の推測・仮定・考えの筋道。事実の段落と見分けられるように、札と破線の枠で出す
  const THINK_NOTE = { "推測": "根拠はあるが、確かめていない見立てです", "仮定": "答えの前提として置いたことです", "考えの筋道": "こう考えると筋が通る、という説明です（頭の中の記録そのものではありません）" };
  function thinkHTML(v, ctx) {
    return `<aside class="think k-${v.kind === "仮定" ? "assume" : v.kind === "考えの筋道" ? "path" : "guess"}" aria-label="先生役の${esc(v.kind)}">` +
      `<p class="think-head"><b>先生役の${esc(v.kind)}</b><span>${THINK_NOTE[v.kind] || ""}</span></p>` +
      `<div class="think-body">${md(v.md, ctx)}</div></aside>`;
  }

  function bodyHTML(text, views, ctx, skip) {
    const blocks = String(text || "").split(/\n\s*\n/);
    let h = "", leadDone = false;
    for (const b of blocks) {
      const m = b.trim().match(/^\[\[view:(\d+)\]\]$/);
      if (m) {
        const i = Number(m[1]);
        if (!skip.has(i) && views[i]) h += views[i].type === "think" ? thinkHTML(views[i], ctx) : viewHTML(views[i], i);
        leadDone = true;
        continue;
      }
      if (!b.trim()) continue;
      if (!leadDone) { h += `<div class="lead">${md(b, ctx)}</div>`; leadDone = true; }
      else h += `<div class="prose">${md(b, ctx)}</div>`;
    }
    return h;
  }

  // 見せ直しの答えは、前の図と新しい図を横に並べる（研究 c: 置き換えより並べて対応を見せるほうがよい）
  function pairHTML(t) {
    const ni = mainIdx(t.views);
    if (!t.ref_turn || ni < 0) return { html: "", skip: new Set() };
    const prev = S.detail.turns.find((x) => x.id === t.ref_turn) || (S.refCache[t.ref_turn] || null);
    const pv = prev && (prev.views || [])[mainIdx(prev.views)];
    // 前の図は別の往復のものなので、この往復の印（番号・色・光らせる相手）を付けない
    const left = pv ? viewHTML(pv, null, { noSay: true }) : `<div class="pair-text">前の答えは文だけでした。</div>`;
    return {
      html: `<div class="pair"><div class="pair-col"><span class="pair-k">前の見せ方</span>${left}</div>` +
        `<div class="pair-col"><span class="pair-k now">いまの見せ方</span>${viewHTML(t.views[ni], ni)}</div></div>`,
      skip: new Set([ni]),
    };
  }

  // 別の読みでしたか（v0.6）。話題の最初の問いに別の読みがあったとき、読みの判定役が見つけた読みを札で出す。
  // 押すと、その読みで聞き直す。もう押した・自分で言い直した（あとに往復がある）ときは出さない
  function altHTML(t) {
    const last = S.detail.turns[S.detail.turns.length - 1];
    if (!t.alt || !last || last.id !== t.id) return "";
    return `<div class="alt"><span class="alt-k">別の読みでしたか</span>` +
      t.alt.others.map((o) => `<button class="chip" data-altask="${esc(o.ask)}" title="${esc(o.ask)}">${esc(o.label)}</button>`).join("") +
      `<span class="tiny">いまの答えは「${esc(t.alt.took)}」として答えています。違っていたら、押すか、自分の言葉で言い直してください。</span></div>`;
  }

  function actionsHTML(t) {
    // 短い答え（目安 300字まで）には「続きを」を先頭に出す（研究 f1: 続きは本人が「詳しく」を探すのでなく、操作1つで出す）。
    // いちばん新しい答えでは、答えを開くキーと同じキーで押せる
    const last = S.detail.turns[S.detail.turns.length - 1];
    const more = t.budget && t.budget.chars <= 300
      ? `<button class="chip more" data-redo="next" data-tid="${t.id}">続きを${last && last.id === t.id && !stripState() ? `<kbd>${K("reveal")}</kbd>` : ""}</button>` : "";
    return `<div class="ans-act" role="group" aria-label="この答えを">` + more +
      `<button class="chip" data-redo="short" data-tid="${t.id}">短く</button>` +
      `<button class="chip" data-redo="other" data-tid="${t.id}">別の見せ方で</button>` +
      `<button class="chip" data-redo="long" data-tid="${t.id}">詳しく</button>` +
      (t.budget ? `<span class="ans-budget" title="この答えの本文の字数の目安と、そう決めた理由">目安 ${t.budget.chars}字・${esc(t.budget.why)}</span>` : "") + `</div>`;
  }

  function foldHTML(t) {
    return `<div class="fold" data-fold="${t.id}">` +
      `<p class="fold-hint">答えが届いています。読む前に、どうなると思うかを一言どうぞ（任意）。予想を送ると答えが開きます。</p>` +
      `<div class="fold-act"><button class="primary" data-predict="${t.id}">予想を話す<kbd>${K("talk")}</kbd></button>` +
      `<button class="ghost" data-reveal="${t.id}">すぐ読む<kbd>${K("reveal")}</kbd></button></div></div>`;
  }

  function predictHTML(t) {
    if (t.predict) {
      // いちばん新しい往復の予想には戻しを付ける（予想の欄に質問を打ってしまったとき、1回で質問として送り直せる）
      const last = S.detail.turns[S.detail.turns.length - 1];
      const undo = last && last.id === t.id ? `<button class="link" data-unpredict="${t.id}" title="この文を予想から外して、質問として先生役に送る">質問として送り直す</button>` : "";
      return `<div class="predict"><span>読む前の予想${undo}</span>${esc(t.predict)}${pfbCue(t)}</div>`;
    }
    if (S.predicting.has(t.id)) return `<div class="predict wait"><span>読む前の予想</span>文字にしています</div>`;
    return "";
  }

  // 予想と答えの照らし合わせ（v0.6・server/predfb.py）。答えが届いたあとに照らし合わせ役が返す。研究 g6 に合わせて:
  // 答えの終わりに置く（読む途中に割り込まない）。点も成績も段も付けず、出すのは「答えの核心が予想に入っていたか」の2つだけ。
  // 画面の字は、予想の中の字か、先生役の答えの中の字をそのまま出す（照らし合わせ役が書くのは、食い違いの1文だけ）。
  // 返しを使う次の一手を、1つだけ添える（いちばん新しい往復だけ）
  const cut = (s, n) => (String(s).length <= n ? String(s) : String(s).slice(0, n - 1) + "…");
  function pfbHTML(t) {
    if (!t.predict) return "";
    const fb = t.predict_fb;
    const head = `<p class="pfb-h"><span>予想と答えの照らし合わせ</span><q>${esc(cut(t.predict, 70))}</q></p>`;
    if (!fb) {
      return S.state && S.state.predict_fb && t.predict_fb_can
        ? `<div class="pfb ask"><button class="link" data-pfb="${t.id}">この予想を、答えと照らし合わせる</button></div>` : "";
    }
    if (fb.state === "run") return `<div class="pfb wait">${head}<p class="pfb-w">照らし合わせています</p></div>`;
    if (fb.state === "fail") return `<div class="pfb ask">予想と答えの照らし合わせを取れませんでした。<button class="link" data-pfb="${t.id}">もう一度</button></div>`;
    if (fb.core === "none") return `<div class="pfb none">${head}<p class="pfb-w">この予想には、答えと照らし合わせられる中身が足りませんでした。</p></div>`;
    const q = (s) => `予想の「${esc(s)}」`;
    const row = (k, name, html) => (html ? `<p class="pfb-r r-${k}"><i>${name}</i><span>${html}</span></p>` : "");
    const verdict = fb.core === "in" ? "答えの核心は、予想に入っていました" : fb.core === "out" ? "答えの核心は、予想に入っていませんでした" : "";
    const last = S.detail.turns[S.detail.turns.length - 1];
    const why = `私は「${t.predict}」と予想しました。この予想のどこが、なぜ違うのかを説明して`;
    const next = !last || last.id !== t.id ? null
      : fb.diff ? ["なぜ違ったかを聞く", why]
        : fb.core === "out" ? ["予想のどこが違ったかを聞く", why]
          : fb.open_q ? ["この点も合っているか聞く", `私の予想の「${fb.open_q}」という点は、合っていますか`] : null;
    return `<div class="pfb" data-core="${fb.core}">${head}` + (verdict ? `<p class="pfb-v v-${fb.core}">${verdict}</p>` : "") +
      row("hit", "合っていた所", fb.core === "in" ? q(fb.core_q) : "") +
      row("miss", "答えの核心", fb.core === "out" ? esc(fb.lead) : "") +
      row("hit", "決め手も合っていた所", fb.key === "in" ? q(fb.key_q) : "") +
      row("miss", "予想に無かった決め手", fb.key === "out" ? esc(fb.keyline) : "") +
      row("diff", "食い違っていた所", fb.diff ? esc(fb.diff) : "") +
      row("open", "答えが触れていない所", fb.open_q ? q(fb.open_q) : "") +
      (next ? `<p class="pfb-next"><button class="chip" data-pfbask="${esc(next[1])}">${next[0]}</button></p>` : "") + `</div>`;
  }

  // 照らし合わせの知らせ（上の予想の箱の中の1行）。箱は答えの終わりにあって、予想した直後には見えないことがあるので、
  // 結果の1行だけを予想のすぐ下に出し、押すと箱まで送る。行の場所は答えが出た時点で取る（届いたときに本文を動かさない）
  function pfbCue(t) {
    const fb = t.predict_fb;
    if (!t.predict || !fb || t.status !== "done" || t.answer == null || foldable(t) || S.hold === t.id) return "";
    const jump = `<button class="link" data-pfbjump="${t.id}">照らし合わせを見る</button>`;
    const text = fb.state === "run" ? "答えと照らし合わせています。結果は、答えの終わりに出します。"
      : fb.state === "fail" ? `照らし合わせを取れませんでした。<button class="link" data-pfb="${t.id}">もう一度</button>`
        : fb.core === "in" ? `答えの核心は、予想に入っていました。${jump}`
          : fb.core === "out" ? `答えの核心は、予想に入っていませんでした。${jump}`
            : fb.core === "none" ? "この予想には、答えと照らし合わせられる中身が足りませんでした。"
              : `照らし合わせを、答えの終わりに出しました。${jump}`;
    return `<p class="pfb-cue${fb.state === "run" ? " wait" : ""}" data-cue="${fb.state === "done" ? fb.core : fb.state}">${text}</p>`;
  }

  function answerHTML(t) {
    if (foldable(t)) return foldHTML(t);
    if (S.hold === t.id) {
      return predictHTML(t) + `<div class="folded"><p>答えが届きました。下の帯で予想を送ると開きます。</p>` +
        `<button class="ghost" data-release="${t.id}">予想せずに読む</button></div>`;
    }
    const rc = retCheck();
    if (rc && rc.turn_id === t.id && t.status === "done") {
      return `<div class="folded"><p>この答えは、下の問いを思い出して言うあいだ畳んであります。</p>` +
        `<button class="ghost" data-stripx="1">あとで（答えを見る）</button></div>`;
    }
    if (t.status === "done" && t.answer != null) {
      const ctx = { quotes: t.quotes, cards: t.cards };
      const views = t.views || [];
      const pair = pairHTML(t);
      let h = predictHTML(t) + gradesHTML(t);
      if (pair.html) {
        // 言い切りの段落のあとに並べた図を置く
        const blocks = String(t.answer).split(/\n\s*\n/);
        const leadIdx = blocks.findIndex((b) => b.trim() && !/^\[\[view:\d+\]\]$/.test(b.trim()));
        const lead = leadIdx >= 0 ? blocks.splice(leadIdx, 1)[0] : "";
        h += (lead ? `<div class="lead">${md(lead, ctx)}</div>` : "") + pair.html;
        h += bodyHTML(blocks.join("\n\n"), views, ctx, pair.skip).replace(/^<div class="lead">/, '<div class="prose">');
      } else {
        h += bodyHTML(t.answer, views, ctx, new Set());
      }
      h += pfbHTML(t) + checksHTML(t);
      h += t.via === "research" ? researchActHTML(t) : lookupHTML(t) + altHTML(t) + actionsHTML(t);
      return h;
    }
    if (t.status === "error") {
      return `<div class="ans-err"><p>${esc(t.error || "止まりました")}</p><button class="ghost" data-retry="${t.id}">もう一度送る</button></div>`;
    }
    return predictHTML(t) + `<div class="pending" data-pending="${t.id}">${pendingHTML(t)}</div>`;
  }

  // Web で調べる入口（v0.5）。先生役が「調べるとよい」とした答えに出す。もう調べた答えには出さない
  function lookupHTML(t) {
    if (!t.lookup || (S.detail.turns || []).some((x) => x.from_turn === t.id)) return "";
    return `<div class="lookup"><p><b>Web で確かめられます</b>${t.lookup.why ? `<span>${esc(t.lookup.why)}</span>` : ""}</p>` +
      `<p class="lookup-q">${esc(t.lookup.q)}</p>` +
      `<button class="primary" data-lookup="${t.id}">Web で調べてページにする</button>` +
      `<span class="tiny">問いの文が検索に送られます。数分かかるので、待つあいだ別の話題へ移れます。</span></div>`;
  }
  function researchActHTML(t) {
    if (!t.page) return "";
    return `<div class="ans-act"><button class="primary" data-page="${esc(t.page)}">調べたページを開く</button>` +
      `<button class="chip" data-usepage="${esc(t.page)}" data-q="${esc(t.final_text || "")}">このページをもとに説明して</button></div>`;
  }

  // 調べたページ（主張ごとに、照らした結果・出どころ・引用を出す。調べ役の推測は事実と別の欄）
  const CLAIM_CLS = { ok: "c-ok", weak: "c-weak", quote_only: "c-quote", not_found: "c-un", unreachable: "c-un" };
  async function openPage(pid) {
    let p;
    try { p = await api("GET", `/api/pages/${pid}`); } catch (e) { toast("ページが見つかりません"); return; }
    const cref = (html) => html.replace(/\[(\d+)\]/g, (m, n) => `<a class="cref" href="#claim-${n}" data-cref="${n}">${n}</a>`);
    const c = p.counts || {};
    const un = (c.not_found || 0) + (c.unreachable || 0);
    $("#pageTitle").textContent = p.title || "Web で調べたページ";
    $("#pageBody").innerHTML =
      `<p class="pg-meta">問い: ${esc(p.question || "")}<br>${esc(p.at || "")}・主張 ${p.claims.length}（引用が支えている ${c.ok || 0}` +
      `${c.quote_only ? "・引用の字だけ一致 " + c.quote_only : ""}${c.weak ? "・支えきれていない " + c.weak : ""}${un ? "・未照合 " + un : ""}）・${esc(p.id)}</p>` +
      `<div class="lead">${cref(md(p.answer || "", {}))}</div>` +
      (p.sections || []).map((s) => `${s.h ? `<h3>${esc(s.h)}</h3>` : ""}<div class="prose">${cref(md(s.body || "", {}))}</div>`).join("") +
      `<h3>主張と出どころ</h3><ol class="claims">` + p.claims.map((x) =>
        `<li id="claim-${x.n}" class="${CLAIM_CLS[x.status] || "c-un"}"><p class="cl-t"><span class="cl-s">${esc((p.status_ja || {})[x.status] || "未照合")}</span>` +
        `<span class="cl-k">${esc(x.kind || "")}${x.date ? "・" + esc(x.date) : ""}</span></p><p>${esc(x.text)}</p>` +
        (x.quote ? `<blockquote>${esc(x.quote)}</blockquote>` : "") +
        (x.url ? `<a class="cl-u" href="#" data-href="${esc(x.url)}">${esc(x.url.replace(/^https?:\/\//, "").slice(0, 80))}</a>` : "") +
        (x.note ? `<small>${esc(x.note)}</small>` : "") + `</li>`).join("") + `</ol>` +
      ((p.guesses || []).length ? `<h3>調べ役の推測</h3>` + p.guesses.map((g) =>
        `<aside class="think k-guess"><p class="think-head"><b>調べ役の推測</b><span>事実ではありません</span></p><div class="think-body"><p>${esc(g.text)}</p>` +
        (g.because ? `<p class="tiny">理由: ${esc(g.because)}</p>` : "") + `</div></aside>`).join("") : "") +
      ((p.open || []).length ? `<h3>分からなかったこと</h3><ul class="prose">${p.open.map((o) => `<li>${esc(o)}</li>`).join("")}</ul>` : "");
    if (!$("#pageView").open) $("#pageView").showModal();
    $("#pageBody").scrollTop = 0;
  }

  function pendingHTML(t) {
    if (t.via === "research") {
      const tool = S.tools[t.id] ? `<span class="pg-tool">${esc(S.tools[t.id])}</span>` : "";
      return `<div class="pg-row"><span class="pg on">Web を調べています</span>${tool}</div>` +
        `<p class="tiny">出どころを開いて確かめるので、数分かかります。待つあいだ、別の話題へ移れます。</p>`;
    }
    const steps = [["transcribing", "声を文字に"], ["fixing", "聞き違いを直す"], ["thinking", "先生役が答えを書いています"]];
    const idx = { recorded: -1, transcribing: 0, fixing: 1, thinking: 2 }[t.status] ?? 2;
    const bar = steps.filter((s) => t.via === "voice" || s[0] === "thinking")
      .map(([k, l]) => { const i = steps.findIndex((x) => x[0] === k); return `<span class="pg${i < idx ? " ok" : i === idx ? " on" : ""}">${l}</span>`; }).join("");
    const tool = S.tools[t.id] ? `<span class="pg-tool">棚を読んでいます（${esc(S.tools[t.id])}）</span>` : "";
    const note = S.notes[t.id] ? `<span class="pg-tool">${esc(S.notes[t.id])}</span>` : "";
    const live = S.streams[t.id] ? `<div class="live">${esc(S.streams[t.id].replace(/```[\s\S]*?(```|$)/g, "（図を描いています）")).slice(-1800)}</div>` : "";
    return `<div class="pg-row">${bar}${tool}${note}</div>${live}`;
  }

  function paintStream(turnId) {
    const el = document.querySelector(`[data-pending="${turnId}"]`);
    if (!el || !S.detail) return;
    const t = S.detail.turns.find((x) => x.id === turnId);
    if (t) { t.status = "thinking"; el.innerHTML = pendingHTML(t); }
  }

  function paintThread(scroll = true) {
    const th = $("#thread");
    const d = S.detail;
    if (!d) { th.innerHTML = ""; return; }
    if (!d.turns.length) {
      th.innerHTML = `<div class="first">話しかけると始まります。<kbd>${K("talk")}</kbd> を押して話し、もう一度押すと送ります。<br>` +
        `<span>例: 「知識空間理論って何？ベイズ知識追跡との違いも」</span></div>`;
      return;
    }
    const keepY = th.scrollTop, atBottom = th.scrollHeight - th.scrollTop - th.clientHeight < 80;
    // 自分が送った往復の問いを列の上に置いたあと、本人が列を動かしていなければ、答えが届いても問いを上に置いたままにする
    const lastT = d.turns[d.turns.length - 1];
    const pinned = !!(S.pin && lastT && lastT.id === S.pin.id);
    th.innerHTML = d.turns.map((t) => `<article class="turn" data-turn="${t.id}">` +
      `<div class="said">` +
      (S.editing === t.id
        ? `<textarea class="said-edit" rows="3">${esc(t.final_text || "")}</textarea><div class="said-act"><button class="primary" data-resend="${t.id}">この文で聞き直す</button><button class="ghost" data-cancel>やめる</button></div>`
        : `<p class="said-text">${saidHTML(t)}</p>`) +
      `<div class="said-meta"><span>${esc(stageLine(t))}</span>` +
      (t.via === "voice" && (t.apple_text || t.scribe_text || t.haas_text) ? `<details class="raw"><summary>聞き取りの元</summary>` +
        `${t.scribe_text != null ? `<p><b>Scribe</b>${esc(t.scribe_text)}</p>` : ""}${t.haas_text != null ? `<p><b>Haas</b>${esc(t.haas_text)}</p>` : ""}${t.apple_text ? `<p><b>Apple</b>${esc(t.apple_text)}</p>` : ""}` +
        `${(t.stage && t.stage.fix_fallback) ? `<p><b>直し</b>${esc(t.stage.fix_fallback)}</p>` : ""}</details>` : "") +
      (S.editing !== t.id && t.final_text ? `<button class="link" data-edit="${t.id}">直して聞き直す</button>` : "") +
      `</div></div>` +
      `<div class="answer${S.opening === t.id ? " ans-open" : ""}">${answerHTML(t)}</div></article>`).join("");
    S.opening = null;
    for (const art of $$(".turn", th)) {
      const t = d.turns.find((x) => x.id === Number(art.dataset.turn));
      if (t) markAnswer(art, t);
    }
    paintHL();
    renderMermaid();
    const fresh = [...S.seenNow];
    if (fresh.length) { S.seenNow.clear(); api("POST", "/api/seen-views", { types: fresh }).catch(() => {}); }
    if ((S.jump || pinned) && th.lastElementChild) {
      S.jump = false;
      jumpTo(th.lastElementChild);
    } else if (scroll) {
      S.pin = null;
      const firstUnread = d.turns.find((t) => t.status === "done" && t.done_at > (d.session.read_at || 0));
      const el = firstUnread ? th.querySelector(`[data-turn="${firstUnread.id}"]`) : th.lastElementChild;
      if (el) el.scrollIntoView({ block: firstUnread ? "start" : "end" });
    } else if (atBottom) th.scrollTop = th.scrollHeight;
    else th.scrollTop = keepY;
  }

  // 往復の頭を列の上に置く（v0.6）。送った問いが上に来て、答えの頭がすぐ下に見える。届くたびに下へ追いかけない。
  // 列の送りはどれも即時にした（app.css）。なめらかな送りは、途中で列を描き直すと途中の位置で止まっていた
  function jumpTo(el) {
    el.scrollIntoView({ block: "start" });
    S.pin = { id: Number(el.dataset.turn) };
  }
  // 本人が列を動かしたら（ホイール・指・キー・送りの棒）、上に置くのをやめる
  const unpin = () => { S.pin = null; };
  $("#thread").addEventListener("wheel", unpin, { passive: true });
  $("#thread").addEventListener("touchmove", unpin, { passive: true });
  $("#thread").addEventListener("mousedown", (e) => { if (e.target === e.currentTarget && e.offsetX > e.currentTarget.clientWidth - 18) unpin(); });
  document.addEventListener("keydown", (e) => { if (["PageUp", "PageDown", "Home", "End", "ArrowUp", "ArrowDown"].includes(e.key) && !typing()) unpin(); });

  // ── 実物に結ぶ（v0.4）: たとえの対と本文の同じ語に同じ番号と色（A6）、図のラベルと本文の『用語』（B3） ──
  // 照らし方はサーバーの fold と同じ（NFKC・空白を除く・小文字）。長い語を先に当て、重なる短い語は当てない。
  // 描くたびに #thread を作り直すので、ここも描くたびに一から付ける（付けた印の中は二度と包まない）。
  const foldStr = (s) => String(s || "").normalize("NFKC").toLowerCase().replace(/\s+/g, "");
  function foldMap(s) {
    let f = "", i = 0;
    const st = [], en = [];
    for (const ch of s) {
      const n = ch.normalize("NFKC").toLowerCase().replace(/\s+/g, "");
      for (let j = 0; j < n.length; j++) { st.push(i); en.push(i + ch.length); }
      f += n;
      i += ch.length;
    }
    return { f, st, en };
  }

  function wrapTerms(roots, terms) {
    const list = terms.filter((t) => t.f).sort((a, b) => b.f.length - a.f.length);
    if (!list.length) return;
    const numbered = new Set();
    for (const root of roots) {
      const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: (n) => (n.parentElement.closest(".view, code, pre, .gx, a, button") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
      });
      const nodes = [];
      while (walk.nextNode()) nodes.push(walk.currentNode);
      for (const node of nodes) {
        const s = node.nodeValue, m = foldMap(s), hits = [];
        for (const t of list) {
          for (let p = m.f.indexOf(t.f); p >= 0; p = m.f.indexOf(t.f, p + t.f.length)) {
            const a = m.st[p], b = m.en[p + t.f.length - 1];
            if (!hits.some((h) => a < h.b && b > h.a)) hits.push({ a, b, t });
          }
        }
        if (!hits.length) continue;
        hits.sort((x, y) => x.a - y.a);
        const frag = document.createDocumentFragment();
        let last = 0;
        for (const h of hits) {
          frag.append(s.slice(last, h.a));
          const sp = document.createElement("span");
          sp.className = h.t.cls;
          for (const [k, v] of Object.entries(h.t.attrs)) sp.setAttribute(k, v);
          sp.textContent = s.slice(h.a, h.b);
          if (!numbered.has(h.t.key)) {   // 番号は最初に出た所にだけ付ける（色は全部）
            numbered.add(h.t.key);
            const no = document.createElement("sup");
            no.className = "gx-no";
            no.textContent = h.t.num;
            sp.append(no);
          }
          frag.append(sp);
          last = h.b;
        }
        frag.append(s.slice(last));
        node.replaceWith(frag);
      }
    }
  }

  function markAnswer(art, t) {
    const roots = $$(".answer .lead, .answer .prose", art);
    if (!roots.length) return;
    const terms = [];
    (t.views || []).forEach((v, i) => {
      if (v.type !== "analogy" || v.legacy || !(v.pairs || []).some((p) => "role" in p)) return;
      const fig = art.querySelector(`.view.v-analogy[data-vi="${i}"]`);
      if (!fig) return;
      const g = `${t.id}-${i}`;
      $$(".an-row", fig).forEach((r) => { r.dataset.g = g; });
      v.pairs.forEach((p, j) => {
        const k = String(j + 1), style = `--pc: var(--pair-${k})`;
        terms.push({ f: foldStr(p.t), cls: "gx gx-t", num: k, key: `${g}:${k}:t`,
          attrs: { "data-g": g, "data-gp": k, style, title: `実際の名前（対${k}。たとえの側は「${p.s}」）` } });
        terms.push({ f: foldStr(p.s), cls: "gx gx-s", num: k, key: `${g}:${k}:s`,
          attrs: { "data-g": g, "data-gp": k, style, title: `たとえの側（対${k}。実際の名前は「${p.t}」）` } });
      });
    });
    wrapTerms(roots, terms);
    // しくみの絵の光らせる組（data-pg）を、描き直しても変わらない名前（往復と図の番号）にする
    (t.views || []).forEach((v, i) => {
      if (v.type !== "parts") return;
      const fig = art.querySelector(`.view.v-parts[data-vi="${i}"]`);
      if (fig) $$("[data-pg]", fig).forEach((x) => { x.dataset.pg = `${t.id}-${i}`; });
    });
    // B3: 図のラベルと同じ字の『用語』を結ぶ（全部の図の型で同じ印 data-lab・位置の図は札の data-label）
    const labs = new Map();
    for (const el of $$(".view [data-lab], .view .node[data-label]", art)) {
      if (el.closest(".pair-col:first-child")) continue;   // 見せ直しの「前の見せ方」は別の往復の図
      const f = foldStr(el.dataset.lab ?? el.dataset.label);
      if (!f) continue;
      if (!labs.has(f)) labs.set(f, []);
      labs.get(f).push(el);
    }
    let n = 0;
    for (const term of $$(".lead .term, .prose .term", art)) {
      const els = labs.get(foldStr(term.dataset.term));
      if (!els) continue;
      const id = els[0].dataset.link || `${t.id}~${n++}`;
      term.dataset.link = id;
      els.forEach((e) => { e.dataset.link = id; });
    }
  }

  // 指す（カーソル・焦点）か押すと、対の相手・表の行・図のラベルが光る。常には光らせない
  // しくみの絵（B2）は、一覧の行か矢印（data-pl）を指すと、その矢印と一覧の行と両端の箱（data-pb に番号）が光る
  const LINKED = "[data-g][data-gp], [data-pg][data-pl], [data-link]";
  let hoverSel = null, pinSel = null;
  function linkSel(el) {
    if (!el) return null;
    if (el.dataset.g && el.dataset.gp) return `[data-g="${el.dataset.g}"][data-gp="${el.dataset.gp}"]`;
    if (el.dataset.pg && el.dataset.pl) {
      const g = el.dataset.pg, k = el.dataset.pl;
      return `[data-pg="${g}"][data-pl="${k}"], [data-pg="${g}"][data-pb~="${k}"]`;
    }
    return el.dataset.link ? `[data-link="${el.dataset.link}"]` : null;
  }
  function paintHL() {
    $$(".hl").forEach((x) => x.classList.remove("hl"));
    for (const s of [hoverSel, pinSel]) if (s) $$(s).forEach((x) => x.classList.add("hl"));
  }
  function hoverAt(target) {
    const s = linkSel(target && target.closest ? target.closest(LINKED) : null);
    if (s !== hoverSel) { hoverSel = s; paintHL(); }
  }
  document.addEventListener("mouseover", (e) => hoverAt(e.target));
  document.addEventListener("focusin", (e) => hoverAt(e.target));
  document.addEventListener("click", (e) => {
    const s = linkSel(e.target.closest ? e.target.closest(LINKED) : null);
    pinSel = s && s !== pinSel ? s : null;
    paintHL();
  });

  // ── 「実際には何のこと？」（v0.4 の A10）: 答えの文を選ぶと近くに札を出し、押すと実際の名前と値を聞き直す ──
  const groundBtn = document.createElement("button");
  groundBtn.id = "groundBtn";
  groundBtn.className = "ground-pop";
  groundBtn.type = "button";
  groundBtn.hidden = true;
  groundBtn.textContent = "実際には何のこと？";
  document.body.appendChild(groundBtn);
  let groundText = "";
  function inAnswer(n) {
    const e = n && (n.nodeType === 1 ? n : n.parentElement);
    return !!(e && e.closest("#thread .answer") && !e.closest("textarea, button, .fold, .folded, .pending"));
  }
  function placeGround() {
    const sel = window.getSelection();
    const txt = sel && !sel.isCollapsed ? sel.toString().replace(/\s+/g, " ").trim().replace(/^[『「]+|[』」]+$/g, "") : "";
    if (!txt || !inAnswer(sel.anchorNode) || !inAnswer(sel.focusNode) || S.rec.phase !== "idle") { groundBtn.hidden = true; return; }
    groundText = txt.slice(0, 120);
    const r = sel.getRangeAt(0).getBoundingClientRect();
    groundBtn.hidden = false;
    const w = groundBtn.offsetWidth, h = groundBtn.offsetHeight;
    let top = r.bottom + 8;
    if (top + h > innerHeight - 8) top = r.top - h - 8;
    groundBtn.style.top = `${Math.max(8, top)}px`;
    groundBtn.style.left = `${Math.min(Math.max(8, r.left), innerWidth - w - 8)}px`;
  }
  document.addEventListener("mouseup", () => setTimeout(placeGround, 0));
  document.addEventListener("keyup", (e) => { if (e.shiftKey || e.key === "Shift") placeGround(); });
  $("#thread").addEventListener("scroll", () => { groundBtn.hidden = true; });
  groundBtn.addEventListener("mousedown", (e) => e.preventDefault());   // 押しても選んだ字が消えないように
  async function askGround() {
    const txt = groundText;
    groundBtn.hidden = true;
    window.getSelection().removeAllRanges();
    if (!txt || !S.active) return;
    await sendText(`『${txt}』は、実際には何のことですか。実際の名前と、実際の値か実例で、短く答えてください`, "question", "click", { ground: true });
  }

  // ── 図を自分の言葉で言う（v0.4 の B4）: 言い直し（confirm）として話し始める。録音できない所では文字の欄へ ──
  const canRecord = () => !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) && typeof MediaRecorder !== "undefined";
  // 文字の欄は Enter で改行、⌘Enter（Mac）・Ctrl+Enter（ほか）で送る（2026-11-10 本人「Enter でなく cmd+Enter で送る」。
  // 日本語入力の確定の Enter で送ってしまうのを避ける）
  const SEND_SHOW = IS_MAC ? "⌘Enter" : "Ctrl+Enter";
  const TYPED_HINT = `打って送る（${SEND_SHOW}・Enter は改行）`;
  function typeFor(kind) {
    S.typedKind = kind;
    const ta = $("#typed");
    ta.placeholder = kind === "confirm" ? `この図を自分の言葉で（${SEND_SHOW} で送る）` : TYPED_HINT;
    if (kind) ta.focus();
  }
  function sayInOwnWords() {
    if (S.rec.phase !== "idle") return;
    if (canRecord()) startRec("confirm");
    else typeFor("confirm");
  }

  // mermaid は図があるときだけ読み込む（版を固定）。色・線・字はアプリの変数（app.css の :root）から取り、描くたびに
  // 今の明暗で初めの設定をし直す（作業B）。変数は oklch なので、1点の canvas に塗って #rrggbb にしてから渡す
  let merP = null;
  function cssHex(name) {
    const probe = document.createElement("span");
    probe.style.color = `var(${name})`;
    document.body.appendChild(probe);
    const c = getComputedStyle(probe).color;
    probe.remove();
    const cv = document.createElement("canvas");
    cv.width = cv.height = 1;
    const x = cv.getContext("2d", { willReadFrequently: true });
    x.fillStyle = "#808080";
    x.fillStyle = c;
    x.fillRect(0, 0, 1, 1);
    const [r, g, b] = x.getImageData(0, 0, 1, 1).data;
    return "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
  }
  function merTheme() {
    const v = Object.fromEntries(["--bg", "--surface", "--surface-2", "--line", "--edge", "--ink", "--ink-2", "--warn-soft", "--accent-soft"]
      .map((n) => [n, cssHex(n)]));
    const lum = parseInt(v["--bg"].slice(1, 3), 16);
    const font = getComputedStyle(document.body).fontFamily;
    return { startOnLoad: false, securityLevel: "strict", theme: "base", fontFamily: font,
      themeVariables: { darkMode: lum < 128, fontFamily: font, fontSize: "13.5px", background: v["--bg"],
        primaryColor: v["--bg"], primaryTextColor: v["--ink"], primaryBorderColor: v["--edge"], lineColor: v["--edge"],
        secondaryColor: v["--surface-2"], tertiaryColor: v["--surface"], textColor: v["--ink"], mainBkg: v["--bg"],
        nodeBorder: v["--edge"], clusterBkg: v["--surface"], clusterBorder: v["--line"], titleColor: v["--ink"],
        edgeLabelBackground: v["--surface"], noteBkgColor: v["--warn-soft"], noteTextColor: v["--ink"], noteBorderColor: v["--line"],
        actorBkg: v["--bg"], actorBorder: v["--edge"], actorTextColor: v["--ink"], actorLineColor: v["--line"],
        signalColor: v["--ink-2"], signalTextColor: v["--ink"], labelBoxBkgColor: v["--surface"], labelBoxBorderColor: v["--line"],
        labelTextColor: v["--ink"], loopTextColor: v["--ink-2"], activationBkgColor: v["--surface-2"],
        activationBorderColor: v["--edge"], sequenceNumberColor: v["--bg"],
        attributeBackgroundColorOdd: v["--bg"], attributeBackgroundColorEven: v["--surface"] } };
  }
  function renderMermaid() {
    const srcs = $$(".mermaid-src");
    if (!srcs.length) return;
    if (!merP) {
      merP = new Promise((ok, ng) => {
        const s = document.createElement("script");
        s.src = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js";
        s.onload = () => ok(window.mermaid);
        s.onerror = ng;
        document.head.appendChild(s);
      });
    }
    merP.then(async (mer) => {
      mer.initialize(merTheme());
      for (const pre of srcs) {
        const code = pre.textContent;
        const id = "m" + Math.random().toString(36).slice(2);
        try {
          // 読めない記述は描かせない。mermaid は描けなかったとき「Syntax error」の絵を body の末尾に残し、
          // 話題を移っても消えずに画面の下を押し上げていた（2026-11-10 に erDiagram の日本語の名前で起きた）
          if (!(await mer.parse(code, { suppressErrors: true }))) { pre.classList.add("bad"); continue; }
          const { svg } = await mer.render(id, code);
          const fig = pre.parentElement;
          fig.innerHTML = `<div class="mer-wrap">${svg}</div>`;
        } catch (e) {
          pre.classList.add("bad");
          for (const x of [id, "d" + id, "i" + id]) document.getElementById(x)?.remove();
        }
      }
    }).catch(() => {});
  }

  // ── 右の地図 ──────────────────────────────────────────
  async function paintSide() {
    const pane = $("#sidePane");
    const checking = !!retCheck(), folded = foldTarget();
    // 確かめのあいだは言葉の一覧だけ、畳んだ答えがあるあいだは、その前に開いた答えの位置の図だけを出す
    const tab = checking ? "list" : folded ? "ego" : S.sideTab;
    $$("#side .tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
    $("#side").classList.toggle("checking", checking || !!folded);
    if (tab === "ego") {
      let id = S.egoId;
      if (!id && S.detail) {
        // 畳んである答え（まだ読んでいない）の中身は地図に出さない。その前に開いた答えの中心を出す
        const lastCenter = [...S.detail.turns].reverse().find((t) => t.center && !(folded && t.id === folded.id));
        id = lastCenter ? lastCenter.center : null;
      }
      if (!id && folded) { pane.innerHTML = `<p class="side-empty">答えを開くと、この話題の地図がここに出ます。</p>`; return; }
      if (!id) { pane.innerHTML = `<p class="side-empty">答えが届くと、説明の中心になった概念の位置がここに出ます。図の札を押すと、その概念を中心に描き直します。</p>`; return; }
      const e = await api("GET", `/api/concepts/${id}/ego`);
      const model = M.fromEgo(e);
      const c = e.center;
      const cov = c.coverage || { known: 0, total: 0 };
      const JA = { known: "分かる", shaky: "あやしい", unknown: "分からない" };
      const stateRow = `<div class="ego-state${c.state ? "" : " ask"}"><span class="k">${c.state ? "自分の申告" : "この言葉、いま人に説明できそうですか（任意）"}</span>${["known", "shaky", "unknown"].map((k) =>
        `<button class="sb s-${k}${c.state === k ? " on" : ""}" data-cstate="${k}" data-cid="${c.id}">${JA[k]}</button>`).join("")}</div>`;
      pane.innerHTML = `<div class="ego-head"><h3>${esc(c.label)}</h3>${c.gist ? `<p>${esc(c.gist)}</p>` : ""}</div>` +
        (c.state ? "" : stateRow) +
        `<figure class="cmap side">${M.render(model, { compact: true })}</figure>${M.chips(model)}` +
        (c.state ? stateRow : "") +
        `<div class="cov"><span class="k">関係で見た理解</span><div class="cov-bar"><i style="width:${cov.total ? (100 * cov.known / cov.total) : 0}%"></i></div>` +
        `<span class="cov-n">${cov.known} / ${cov.total} の関係を確かめ済み</span>` +
        (c.state === "known" && cov.total > 0 && cov.known === 0
          ? `<p class="cov-warn">申告は「分かる」ですが、周りの関係はまだ1つも確かめていません。「関係を問題にして」で確かめると、分かったつもりかどうかが分かります。</p>` : "") +
        `</div>` +
        relList(e) +
        `<div class="ego-act"><button class="primary" data-askc="${esc(c.label)}">これを説明して</button>` +
        `<button class="ghost" data-askrel="${esc(c.label)}">関係を問題にして</button></div>` +
        (e.sessions && e.sessions.length > 1 ? `<div class="ego-sess"><span class="k">出てきた話題</span>${e.sessions.map((s) => `<button class="chip" data-open="${s.id}">${esc(s.title)}</button>`).join("")}</div>` : "") +
        M.legend();
      return;
    }
    if (tab === "all") { await paintAll(pane); return; }
    const sid = S.active;
    const r = await api("GET", "/api/concepts" + (sid ? `?session_id=${sid}` : ""));
    // 確かめのあいだは、位置の図（関係と例＝答えの中身）を伏せて、この話題の言葉の一覧だけを出す
    const note = checking ? `<p class="side-note">確かめのあいだは位置の図を伏せています。この話題に出てきた言葉は下のとおりです。</p>` : "";
    const groups = { unknown: [], shaky: [], known: [], none: [] };
    for (const c of r.concepts) groups[c.state || "none"].push(c);
    const NAME = { unknown: "分からない", shaky: "あやしい", known: "分かる", none: "まだ申告していない" };
    pane.innerHTML = note + (Object.entries(groups).filter(([, v]) => v.length).map(([k, v]) =>
      `<section class="cl"><h4 class="s-${k}">${NAME[k]}<span>${v.length}</span></h4>` + v.map((c) =>
        `<button class="cl-i" ${checking ? "disabled" : `data-ego="${c.id}"`}><span>${esc(c.label)}</span>${c.coverage.total ? `<small>${c.coverage.known}/${c.coverage.total}</small>` : ""}</button>`).join("") +
      `</section>`).join("") || `<p class="side-empty">まだ概念がありません。</p>`);
  }

  // 「全部」: 話題ごとの言葉の一覧（v0.6）。新しい話題から順に、片づけた話題も入れる。例と非例の文は並べない。
  // 数は事実だけを出す（研究 g2: ふれただけの数を理解の段として見せた研究は無い。地図より一覧が主）
  async function paintAll(pane) {
    const r = await api("GET", "/api/concepts/by-topic");
    const c = r.counts || {};
    const q = foldStr(S.allFilter || "");
    const JA = { known: "分かる", shaky: "あやしい", unknown: "分からない" };
    const groups = r.topics.map((t) => ({ ...t, concepts: t.concepts.filter((x) => !q || foldStr(x.label).includes(q)) })).filter((t) => t.concepts.length);
    pane.innerHTML = `<p class="all-sum">話題に出てきた言葉 ${c.concepts || 0}・関係 ${c.relations || 0}・確かめの記録がある関係 ${c.checked || 0}` +
      `${c.known ? `（うち分かる ${c.known}）` : ""}<button class="link all-atlas" data-openatlas="1">全体の地図で見る</button></p>` +
      `<input id="allFilter" class="all-filter" type="search" placeholder="言葉を探す" value="${esc(S.allFilter || "")}" aria-label="言葉を探す">` +
      (groups.map((t) => `<section class="cl"><h4><button class="cl-topic" ${t.archived ? `data-restore="${t.id}" title="片づけた話題（押すと一覧に戻して開く）"` : `data-open="${t.id}"`}>` +
        `${esc(t.title)}${t.archived ? `<i>片づけ済み</i>` : ""}</button><span>${t.concepts.length}</span></h4>` +
        t.concepts.map((x) => `<button class="cl-i" data-ego="${x.id}"><span>${esc(x.label)}${x.state ? `<i class="cl-st s-${x.state}">${JA[x.state]}</i>` : ""}</span>` +
          `${x.coverage.total ? `<small title="周りの関係のうち、確かめて分かるになった数">${x.coverage.known}/${x.coverage.total}</small>` : ""}</button>`).join("") +
        `</section>`).join("") || `<p class="side-empty">${q ? "当てはまる言葉がありません。" : "まだ言葉がありません。"}</p>`);
    const f = $("#allFilter");
    if (S.allFocus && f) { f.focus(); f.setSelectionRange(f.value.length, f.value.length); }
  }

  function relList(e) {
    const rows = [];
    const JA = { known: "分かる", shaky: "あやしい", unknown: "分からない" };
    const DIR = { broader: "上位", narrower: "下位", opposite: "対", related: "関係" };
    for (const d of ["broader", "narrower", "opposite", "related"]) {
      for (const n of e[d] || []) {
        const word = d === "related" ? (n.phrase || (n.detail && n.detail !== "同時に出る" ? n.detail : "つながり")) : DIR[d] + (n.detail ? "・" + n.detail : "");
        rows.push(`<div class="rl"><span class="rl-d">${esc(word)}</span>` +
          `<button class="rl-n" data-ego="${n.id}">${esc(n.label)}</button>` +
          `<span class="rl-b">${["known", "unknown"].map((k) => `<button class="mini s-${k}${n.rstate === k ? " on" : ""}" data-rstate="${k}" data-rid="${n.rid}" title="この関係が${JA[k]}">${k === "known" ? "✓" : "?"}</button>`).join("")}</span></div>`);
      }
    }
    return rows.length ? `<div class="rels">${rows.join("")}</div>` : "";
  }

  // ── 録音 ──────────────────────────────────────────────
  async function startRec(kind = null, ref = {}) {
    if (S.rec.phase !== "idle") return;
    if (!S.active) await newSession(false);
    if (S.typedKind) typeFor(null);   // 声で話し始めたら、文字の欄の言い直しの待ちはやめる
    const it = kind ? ref : (S.intent || {});
    S.rec.phase = "starting";
    S.rec.kind = kind || it.kind || null;
    S.rec.target = it.target || null;
    S.rec.check = it.check || null;   // 帯の声のボタンからは、答える確かめの問いを渡す（無ければ、開いている問いすべてへの答え）
    paintTalk();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      if (S.rec.phase !== "starting") { stream.getTracks().forEach((x) => x.stop()); return; }
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      S.rec = { ...S.rec, phase: "recording", mr, stream, chunks: [], started: Date.now(), sid: S.active };
      mr.ondataavailable = (e) => { if (e.data.size) S.rec.chunks.push(e.data); };
      mr.start(250);
      meter(stream);
      S.rec.timer = setTimeout(() => stopRec(true), 180000);   // 3分で自動で送る
      paintTalk();
      paintRail();
      paintStrip();
    } catch (e) {
      S.rec = { ...S.rec, phase: "idle", kind: null, target: null, check: null };   // 種類の印を残さない（次の発言が確かめへの答えや予想にならないように）
      S.autoRec = false;
      paintTalk();
      paintStrip();
      toast("マイクが使えませんでした。システム設定のプライバシーでマイクを許可してください。");
      if (kind === "confirm") typeFor("confirm");   // 図を自分の言葉で言う: 文字で言えるようにする
    }
  }

  function meter(stream) {
    try {
      const ctx = new AudioContext();
      const an = ctx.createAnalyser();
      an.fftSize = 512;
      ctx.createMediaStreamSource(stream).connect(an);
      const buf = new Uint8Array(an.fftSize);
      const bar = $("#meter i");
      const loop = () => {
        an.getByteTimeDomainData(buf);
        let p = 0;
        for (const v of buf) p = Math.max(p, Math.abs(v - 128));
        bar.style.transform = `scaleX(${Math.min(1, p / 64)})`;
        const s = Math.floor((Date.now() - S.rec.started) / 1000);
        $("#recTime").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
        S.rec.raf = requestAnimationFrame(loop);
      };
      S.rec.ctx = ctx;
      loop();
    } catch (e) { /* 目盛りが無くても録れる */ }
  }

  async function stopRec(send, why = "") {
    S.autoRec = false;
    if (S.rec.phase === "starting") {
      S.rec = { ...S.rec, phase: "idle", kind: null, target: null, check: null };
      paintTalk();
      paintStrip();
      if (why) toast(why);
      return;
    }
    if (S.rec.phase !== "recording") return;
    const { mr, stream, sid, kind, target, check } = S.rec;
    clearTimeout(S.rec.timer);
    cancelAnimationFrame(S.rec.raf);
    if (S.rec.ctx) S.rec.ctx.close().catch(() => {});
    S.rec.phase = send ? "sending" : "idle";
    paintTalk();
    await new Promise((ok) => { mr.onstop = ok; mr.stop(); });
    stream.getTracks().forEach((x) => x.stop());
    const blob = new Blob(S.rec.chunks, { type: "audio/webm" });
    S.rec = { ...S.rec, phase: "idle", mr: null, stream: null, chunks: [], kind: null, target: null, check: null };
    paintTalk();
    if (!send || blob.size < 1500) {
      toast(send ? "短すぎて送りませんでした" : why || "録音をやめました");
      paintRail();
      if (kind === "predict" && target && S.hold === target && !predictingFor(target)) releaseHold(target);   // 予想をやめたら、届いていた答えを開く
      paintStrip();
      return;
    }
    const fd = new FormData();
    fd.append("audio", blob, "voice.webm");
    if (kind) fd.append("kind", kind);
    if (kind === "predict" && target) fd.append("ref_turn", String(target));
    if (kind === "answer" && check) fd.append("check_id", String(check));
    try {
      await api("POST", `/api/sessions/${sid}/voice`, fd);
    } catch (e) { toast("送れませんでした: " + e.message); return; }
    if (kind === "predict" && target) {
      // 予想は先生役に送らない。答えが届いていればすぐ開き、予想の文は文字になりしだい答えの上に出る
      S.predicting.add(target);
      await afterPredict(target);
      return;
    }
    if (kind === "answer" && check) { S.retDone.add(check); S.showReturn = false; paintStrip(); paintSide(); }
    else if (retCheck()) { S.showReturn = false; paintThread(false); paintStrip(); paintSide(); }   // 確かめに答えずに話したら、帯は下げる（次に戻ったときにまた出る）
    if (S.hold && kind !== "answer") releaseHold(S.hold);
    S.elsewhere = null;
    S.jump = true;
    await loadState();
    if (S.state.prefs.auto_next === "1") goNext(true);
    else loadDetail(false);
  }

  function paintTalk() {
    const b = $("#talk");
    const p = S.rec.phase;
    b.dataset.phase = p;
    const k = p === "idle" ? ((S.intent && S.intent.kind) || S.rec.kind) : S.rec.kind;
    $("#talkLabel").textContent = { idle: k === "answer" ? "答えを話す" : k === "predict" ? "予想を話す" : "話す", starting: "マイクを準備中", recording: "送る", sending: "送っています" }[p];
    $("#composer").classList.toggle("recording", p === "recording");
    const what = { predict: "予想を録音中・", answer: "確かめの答えを録音中・", confirm: "言い直しを録音中・" }[S.rec.kind] || "";
    $("#recHint").textContent = p === "recording" ? `${what}もう一度 ${K("talk")} で送る・${K("cancel")} でやめる` : `${K("talk")} で話し始める`;
  }

  // ── 話題の移動 ────────────────────────────────────────
  function goNext(afterSend = false) {
    const ss = (S.state && S.state.sessions) || [];
    if (!ss.length) return;
    const ready = ss.filter((s) => s.unread > 0 && s.id !== S.active)
      .sort((a, b) => ((a.last && a.last.done_at) || 0) - ((b.last && b.last.done_at) || 0));
    if (ready.length) { open(ready[0].id); return; }
    const i = ss.findIndex((s) => s.id === S.active);
    const idle = [...ss.slice(i + 1), ...ss.slice(0, Math.max(0, i))].filter((s) => !s.busy);
    if (afterSend) {
      toast(idle.length ? `ほかの答えはまだです。${K("new")} で新しい話題、${K("next")} で待っている話題へ` : `ほかの話題は考え中です。${K("new")} で新しい話題を作れます`);
      loadDetail(false);
      return;
    }
    if (idle.length) open(idle[0].id);
    else toast("ほかの話題は考え中です");
  }

  async function newSession(startTalking = true) {
    const r = await api("POST", "/api/sessions", {});
    await loadState();
    await open(r.id, { quiet: true });
    $("#resume").hidden = true;
    if (startTalking && S.rec.phase === "idle") { S.autoRec = true; startRec(); }   // 録音中に押したときは、自動の録音の印を付けない
  }

  async function sendText(text, kind = "question", via = "text", extra = {}) {
    if (!text.trim()) return;
    if (!S.active) await newSession(false);
    await api("POST", `/api/sessions/${S.active}/text`, { text, kind, via, ...extra });
    if (retCheck()) { S.showReturn = false; paintThread(false); paintStrip(); paintSide(); }   // 確かめに答えずに送ったら、帯は下げる
    if (S.hold) releaseHold(S.hold);   // 打ちかけの予想で畳んでいた答えは開く（帯は新しい往復のものに替わるので、畳んだままにしない）
    S.elsewhere = null;   // ほかの話題の確かめの差し出しも下げる（主な経路が先）
    S.jump = true;
    await loadState();
    loadDetail(false);
  }

  // ── 小物 ──────────────────────────────────────────────
  let toastT = 0;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("on");
    clearTimeout(toastT);
    toastT = setTimeout(() => t.classList.remove("on"), 3200);
  }

  let actx = null;
  function chime() {
    if (S.state && S.state.prefs.chime === "0") return;
    try {
      actx = actx || new AudioContext();
      const o = actx.createOscillator(), g = actx.createGain();
      o.type = "sine";
      o.frequency.setValueAtTime(880, actx.currentTime);
      o.frequency.exponentialRampToValueAtTime(1320, actx.currentTime + 0.12);
      g.gain.setValueAtTime(0.0001, actx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.06, actx.currentTime + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, actx.currentTime + 0.35);
      o.connect(g).connect(actx.destination);
      o.start();
      o.stop(actx.currentTime + 0.4);
    } catch (e) { /* 音が出なくても困らない */ }
  }

  function typing() {
    const a = document.activeElement;
    return a && (a.tagName === "TEXTAREA" || a.tagName === "INPUT" || a.tagName === "SELECT" || a.isContentEditable);
  }

  // ── 操作 ──────────────────────────────────────────────
  // 修飾キーつきの操作は文字の欄にいても効く（⌘N など）。修飾キーの無い操作は文字の欄にいるときは効かない
  const allowed = (a, e) => !e.isComposing && (hasMods(KEYS[a]) || !typing());
  document.addEventListener("keydown", (e) => {
    if (S.capture) { captureKey(e); return; }
    if ($("#settings").open || Atlas.isOpen() || Atlas.state.opening) return;   // 地図のキーは web/atlas.js が受ける
    if (hit(e, "atlas") && allowed("atlas", e)) { e.preventDefault(); if (!e.repeat) openAtlas(); return; }
    if (hit(e, "new") && allowed("new", e)) { e.preventDefault(); newSession(true); return; }
    if (hit(e, "next") && allowed("next", e)) { e.preventDefault(); goNext(); return; }
    if (hit(e, "open") && allowed("open", e)) {
      const s = S.state && S.state.sessions[Number(e.code.slice(5)) - 1];
      if (s) { e.preventDefault(); open(s.id); }
      return;
    }
    if (hit(e, "cancel") && S.rec.phase !== "idle") { e.preventDefault(); stopRec(false); return; }
    if (hit(e, "reveal") && allowed("reveal", e) && S.rec.phase === "idle") {
      const f = foldTarget();
      if (f) { e.preventDefault(); if (!e.repeat) reveal(f.id); return; }
      // 帯が出ていれば、同じキーで帯の声の操作（予想を話す・確かめに声で答える）
      if (stripState() && !document.querySelector("dialog[open]")) { e.preventDefault(); if (!e.repeat) stripVoice(); return; }
      // 畳んだ答えが無ければ、同じキーで、いちばん新しい短い答えの「続きを」を押す（dialog が開いているあいだは押さない）
      // 誤って1往復を走らせないよう、焦点がボタンや入力に無く、この話題に待ちの往復が無いときだけ
      const ae = document.activeElement, free = !ae || ae === document.body || ae.id === "thread";
      const more = free && !document.querySelector("dialog[open]") && !retCheck() && !document.querySelector("#thread .pending") &&
        document.querySelector(".turn:last-child .chip.more");
      if (more && !e.repeat) { e.preventDefault(); more.click(); return; }
    }
    if (hit(e, "talk") && allowed("talk", e)) {
      e.preventDefault();
      if (e.repeat) return;
      if (S.rec.phase === "idle") startRec(S.rec.kind);
      else if (S.rec.phase === "recording") stopRec(true);
    }
  });

  // 押したボタンに focus が残っていると、話すキーを離したときにそのボタンも押されるので止める
  document.addEventListener("keyup", (e) => {
    if (Atlas.isOpen()) return;   // 全体の地図の中では、話すキー（Space）でボタンを押せるままにする
    if (!S.capture && hit(e, "talk") && !typing()) e.preventDefault();
  });

  // ── 全体の地図（v0.6・web/atlas.js） ──────────────────────
  // 主な経路の外の寄り道なので、押したときにだけ開く。録音中・ほかの小窓が開いているあいだは開かない
  function openAtlas() {
    S.atlasNews = 0;
    return Atlas.open();
  }
  Atlas.init({
    api,
    toast: (m) => { const el = $("#atMsg"); el.textContent = m; clearTimeout(el._t); el._t = setTimeout(() => { el.textContent = ""; }, 3200); if (!Atlas.isOpen()) toast(m); },
    active: () => S.active,
    canOpen: () => S.rec.phase === "idle" && !document.querySelector("dialog[open]"),
    isKey: (e) => hit(e, "atlas"),
    goNext: () => goNext(),
    // 話題を開く（片づけた話題は、一覧に戻してから開く）
    openTopic: async (id, archived) => {
      if (archived) { await api("PATCH", `/api/sessions/${id}`, { archived: false }); await loadState(); }
      open(id);
    },
    showEgo: (cid) => { S.egoId = cid; S.sideTab = "ego"; paintSide(); },
    ask: (label) => sendText(`${label}を、私が分かっている周りの概念を足場にして説明して`, "question", "click"),
    // いま開いている話題に、地図が覆っているあいだに届いて、まだ読める形で出していない答えがあるか
    unreadHere: () => !!(S.detail && S.detail.session.id === S.active &&
      S.detail.turns.some((t) => t.status === "done" && t.answer != null && !t.revealed_at && !foldable(t) && t.id !== S.hold)),
    // 地図を閉じた: 覆っているあいだに届いた答えを、ここで初めて読める形で出したことにする。
    // 閉じてすぐ別の話題へ移るとき（reveal が偽）は、いまの話題の答えを読んだことにしない
    onClose: (o = {}) => {
      S.atlasNews = 0;
      if (o.reveal !== false) {
        if (S.active && !document.hidden) api("POST", `/api/sessions/${S.active}/read`).catch(() => {});
        if (revealShown()) { paintThread(false); paintSide(); }
      }
      paintStrip();
      refreshRailSoon();
    },
  });

  // ── 設定の画面 ────────────────────────────────────────
  async function openSettings() {
    const d = $("#settings");
    if (!d.open) d.showModal();
    paintSettings();
    paintHealth(null);
    paintHealth(await api("GET", "/api/health").catch((e) => ({ error: e.message })));
  }
  function paintSettings() {
    const st = S.state;
    if (!st) return;
    $("#tutorModel").value = st.prefs.tutor_model || "";
    $('#tutorModel option[value=""]').textContent = `既定（${st.tutor_default}）`;
    const over = st.prefs.keys || {};
    $("#keyRows").innerHTML = KEY_ACTIONS.map(([a, name]) => {
      const cap = S.capture === a;
      return `<tr data-action="${a}"><th scope="row">${esc(name)}</th>` +
        `<td>${cap ? `<span class="capturing">キーを押してください</span>` : `<kbd>${esc(a === "open" ? `${openLabel(1)}〜${openLabel(9)}` : K(a))}</kbd>`}` +
        `${a in over ? `<span class="tiny changed">変えてあります</span>` : ""}</td>` +
        `<td class="key-act">${cap ? `<button class="ghost small" data-key-cancel>やめる</button>` : `<button class="ghost small" data-key-change="${a}">変える</button>`}` +
        `${a in over && !cap ? `<button class="ghost small" data-key-default="${a}">既定に戻す</button>` : ""}</td></tr>`;
    }).join("");
  }
  function paintHealth(h) {
    const box = $("#healthList");
    if (!h) { box.innerHTML = `<p class="tiny">確かめています</p>`; return; }
    if (h.error) { box.innerHTML = `<p class="tiny">確かめられませんでした（${esc(h.error)}）</p>`; return; }
    box.innerHTML = h.items.map((i) =>
      `<div class="h-row ${i.ok ? "ok" : i.need ? "ng" : "opt"}"><span class="h-mark">${i.ok ? "使えます" : i.need ? "要対応" : "なし"}</span>` +
      `<span class="h-body"><b>${esc(i.label)}</b><span class="tiny">${esc(i.detail)}</span>${i.fix ? `<span class="h-fix">${esc(i.fix)}</span>` : ""}</span></div>`).join("");
    $("#healthWhere").textContent = `記録の置き場: ${h.data_dir}（設定の .env: ${h.env_file}）`;
    paintSetupWarn(h);
  }
  // 足りないものがあれば、左の列と最初の画面に1行で出す
  function paintSetupWarn(h) {
    const miss = h && !h.error ? h.items.filter((i) => i.need && !i.ok).map((i) => i.label) : [];
    const msg = miss.length ? `準備が足りません: ${miss.join("、")}。「設定を開く」の「この PC の準備」に直し方があります。` : "";
    for (const id of ["#setupWarn", "#emptyWarn"]) { $(id).textContent = msg; $(id).hidden = !msg; }
  }
  async function saveKeys(over) {
    const res = await fetch("/api/prefs", { method: "POST", headers: { ...H, "Content-Type": "application/json" }, body: JSON.stringify({ keys: over }) });
    if (!res.ok) { $("#keyMsg").textContent = "保存できませんでした: " + ((await res.json().catch(() => ({}))).detail || res.status); return false; }
    await loadState();
    return true;
  }
  function captureKey(e) {
    e.preventDefault();
    e.stopPropagation();
    if (["Shift", "Control", "Alt", "Meta", "CapsLock", "Process"].includes(e.key) || e.isComposing) return;   // 修飾キーだけ・日本語入力中は待つ
    const a = S.capture;
    let c = comboOf(e);
    if (a === "open") {
      if (!/^Digit[1-9]$/.test(e.code)) { $("#keyMsg").textContent = "修飾キー（Alt など）を押したまま、1〜9 のどれかを押してください。"; return; }
      if (!hasMods(c)) { $("#keyMsg").textContent = "数字だけだと文字の入力とぶつかるので、Alt や Ctrl と一緒に押してください。"; return; }
      c = c.replace(/Digit[1-9]$/, "Digit");
    }
    const clash = KEY_ACTIONS.find(([b]) => b !== a && (KEYS[b] === c ||
      (b === "open" && /Digit[1-9]$/.test(c) && c.replace(/Digit[1-9]$/, "Digit") === KEYS.open) ||
      (a === "open" && /Digit[1-9]$/.test(KEYS[b] || "") && KEYS[b].replace(/Digit[1-9]$/, "Digit") === c)));
    if (clash) { $("#keyMsg").textContent = `${keyLabel(c)} は「${clash[1]}」と重なっています。別のキーにしてください。`; return; }
    const over = { ...((S.state && S.state.prefs.keys) || {}) };
    if (c === KEY_DEFAULTS[a]) delete over[a]; else over[a] = c;
    S.capture = null;
    saveKeys(over).then((ok) => { if (ok) $("#keyMsg").textContent = `「${KEY_ACTIONS.find(([b]) => b === a)[1]}」を ${a === "open" ? openLabel("1〜9") : keyLabel(c)} にしました。`; paintSettings(); });
  }

  document.addEventListener("click", async (e) => {
    const el = e.target.closest("button, a, .node[data-label], mark.edit, .term");   // mermaid の箱（.node）は除く
    if (!el) return;
    const d = el.dataset;
    if (el.classList.contains("sess")) { open(Number(d.id)); return; }
    if (el.id === "newSession") { newSession(true); return; }
    if (el.id === "openAtlas" || d.openatlas) { openAtlas(); return; }
    if (el.closest("#atlas")) return;   // 全体の地図の中のボタンは、地図が自分で受ける（web/atlas.js）
    if (el.id === "nextBtn") { goNext(); return; }
    if (el.id === "groundBtn") { askGround(); return; }
    if (d.say) { sayInOwnWords(); return; }
    if (el.id === "talk") { if (S.rec.phase === "idle") startRec(S.rec.kind); else if (S.rec.phase === "recording") stopRec(true); return; }
    if (el.classList.contains("tab")) { S.sideTab = d.tab; paintSide(); return; }
    if (d.shelf) {
      e.preventDefault();
      try { const r = await api("GET", `/api/shelf/${d.shelf}`); if (r.page) openPage(r.page); else window.open(r.url, "_blank"); } catch (err) { toast("棚に見つかりません"); }
      return;
    }
    if (d.href) { e.preventDefault(); window.open(d.href, "_blank"); return; }
    if (d.cref) { e.preventDefault(); document.getElementById(`claim-${d.cref}`)?.scrollIntoView({ block: "center" }); return; }
    if (d.page) { openPage(d.page); return; }
    if (d.usepage) { sendText(`Web で調べたページ（${d.usepage}）をもとに、「${d.q}」に答えて`, "question", "click"); return; }
    if (d.lookup) {
      const t = S.detail.turns.find((x) => x.id === Number(d.lookup));
      if (t && t.lookup) { el.disabled = true; await api("POST", `/api/sessions/${S.active}/research`, { q: t.lookup.q, from_turn: t.id }).catch((err) => toast(err.message)); }
      return;
    }
    if (el.classList.contains("node")) {
      if (d.id) { S.egoId = Number(d.id); S.sideTab = "ego"; paintSide(); return; }
      try { const r = await api("GET", `/api/concepts/find?label=${encodeURIComponent(d.label)}`); S.egoId = r.id; S.sideTab = "ego"; paintSide(); }
      catch (err) { toast("まだ記録に無い概念です"); }
      return;
    }
    if (el.classList.contains("term")) {
      try { const r = await api("GET", `/api/concepts/find?label=${encodeURIComponent(d.term)}`); S.egoId = r.id; S.sideTab = "ego"; paintSide(); } catch (err) { /* 地図に無い語 */ }
      return;
    }
    if (d.ego) { S.egoId = Number(d.ego); S.sideTab = "ego"; paintSide(); return; }
    if (d.open) { open(Number(d.open)); return; }
    if (d.cstate) {
      const cur = el.classList.contains("on");
      await api("POST", "/api/mastery", { concept_id: Number(d.cid), state: cur ? "clear" : d.cstate });
      return;
    }
    if (d.rstate) { await api("POST", "/api/mastery", { relation_id: Number(d.rid), state: d.rstate }); return; }
    if (d.ckstate) {
      const ck = el.closest("[data-check]");
      await api("POST", "/api/mastery", { check_id: Number(ck.dataset.check), state: d.ckstate });
      return;
    }
    if (d.ckvoice) { S.rec.kind = "answer"; paintTalk(); startRec("answer"); return; }
    if (d.reveal) { reveal(Number(d.reveal)); return; }
    if (d.predict) { if (S.rec.phase === "idle") startRec("predict", { target: Number(d.predict) }); return; }
    if (d.stripvoice) { stripVoice(); return; }
    if (d.stripsend) { sendStrip(); return; }
    if (d.stripx) { closeStrip(); return; }
    if (d.elsewhere) { goElsewhere(); return; }
    if (d.release) { releaseHold(Number(d.release)); return; }
    if (d.pfbask) { sendText(d.pfbask, "question", "click", { pfb: true }); return; }
    if (d.pfbjump) {
      const box = document.querySelector(`.turn[data-turn="${d.pfbjump}"] .pfb`);
      if (box) { S.pin = null; box.scrollIntoView({ block: "center" }); }   // 本人が動かしたので、問いを上に置くのはやめる
      return;
    }
    if (d.pfb) {
      el.disabled = true;
      await api("POST", `/api/turns/${d.pfb}/predict-fb`).catch((err) => toast("照らし合わせを始められませんでした: " + err.message));
      return;
    }
    if (d.unpredict) {
      el.disabled = true;
      await api("POST", `/api/turns/${d.unpredict}/unpredict`, { resend: true }).catch((err) => toast("送り直せませんでした: " + err.message));
      S.jump = true;
      await loadState();
      loadDetail(false);
      return;
    }
    if (d.restore) {
      await api("PATCH", `/api/sessions/${d.restore}`, { archived: false });
      await loadState();
      open(Number(d.restore));
      return;
    }
    if (d.rchint) { askHint(Number(d.rchint)).catch((err) => toast("ヒントを出せませんでした: " + err.message)); return; }
    if (d.rcstate) {
      const id = Number(d.rcid);
      await api("POST", "/api/mastery", { check_id: id, state: d.rcstate });
      S.retDone.add(id);
      S.opening = S.retSnap && S.retSnap.id === id ? S.retSnap.turn_id : null;
      S.showReturn = false;   // 戻ったときの確かめは、1回の戻りにつき1問だけ
      paintThread(false);
      paintStrip();
      paintSide();
      loadDetailSoon();
      return;
    }
    if (d.askc) { sendText(`${d.askc}を、私が分かっている周りの概念を足場にして説明して`, "question", "click"); return; }
    if (d.askrel) { sendText(`${d.askrel}の周りの関係を、確かめの問題にして出して`, "command", "click"); return; }
    if (d.ask) { sendText(`${d.ask}を説明して`, "question", "click"); return; }
    if (d.altask) { sendText(d.altask, "question", "click", { alt: true }); return; }
    if (d.redo) {
      const t = S.detail.turns.find((x) => x.id === Number(d.tid));
      const mv = t && t.views ? t.views[mainIdx(t.views)] : null;   // たとえの塊は図に数えない
      const name = mv ? mv.name : "文だけ";
      const msg = {
        short: ["直前の答えを短くして（3文まで、図は1つまで）", "短く"],
        other: [`直前の答えを、別の見せ方で見せ直して（中身は同じ。いまの「${name}」とは違う形を、見せ方の選び方の次に当てはまるものから選ぶ）`, "別の見せ方で"],
        long: ["直前の答えを詳しくして（前の図は消さずに、足りない所を下に足す）", "詳しく"],
        next: ["続きを。直前の答えで省いた点を、同じくらいの長さで（前の答えの中身は繰り返さない）", "続きを"],
      }[d.redo];
      await api("POST", `/api/sessions/${S.active}/text`, { text: msg[0], kind: "command", via: "click", title: msg[1],
        ref_turn: d.redo === "other" ? Number(d.tid) : undefined });
      S.jump = true;
      await loadState();
      loadDetail(false);
      return;
    }
    if (d.detail) {
      await api("PATCH", `/api/sessions/${S.active}`, { detail: d.detail });
      if (S.detail) S.detail.session.detail = d.detail;
      paintTop();
      toast({ auto: "詳しさは発言から決めます（ふつうは短く、頼まれたら詳しく）", short: "これからの答えを短くします", long: "これからの答えを詳しくします" }[d.detail]);
      return;
    }
    if (d.retry) {
      const t = S.detail.turns.find((x) => x.id === Number(d.retry));
      if (t && t.final_text) await api("POST", `/api/turns/${t.id}/resend`, { text: t.final_text });
      else toast("送り直せる文がありません。もう一度話してください");
      return;
    }
    if (d.edit) { S.editing = Number(d.edit); paintThread(false); const ta = $(".said-edit"); if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); } return; }
    if ("cancel" in d) { S.editing = null; paintThread(false); return; }
    if (d.resend) {
      const ta = $(".said-edit");
      const text = ta ? ta.value.trim() : "";
      if (!text) return;
      S.editing = null;
      await api("POST", `/api/turns/${d.resend}/resend`, { text });
      return;
    }
    if (el.matches("mark.edit")) {
      // 直しを1つ戻す（戻した文で聞き直す画面を開く）
      const t = S.detail.turns.find((x) => x.id === Number(el.closest("[data-turn]").dataset.turn));
      const ed = t && t.edits[Number(d.i)];
      if (!ed) return;
      S.editing = t.id;
      paintThread(false);
      const ta = $(".said-edit");
      if (ta) { ta.value = ta.value.replace(ed.to, ed.from); ta.focus(); }
      toast(`「${ed.to}」を聞き取りどおりの「${ed.from}」に戻しました。よければ聞き直してください`);
    }
  });

  document.addEventListener("dblclick", (e) => {
    const n = e.target.closest(".node");
    if (n && n.dataset.label) sendText(`${n.dataset.label}を説明して`, "question", "click");
  });

  // 文字の欄の高さを中身に合わせる（Enter で改行できるので、6行ぶんまで伸ばし、それより長いと欄の中で上下に送る）
  function fitTyped() {
    const ta = $("#typed");
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight + 2, 168) + "px";
  }
  $("#typed").addEventListener("input", (e) => {
    fitTyped();
    // 新しい話題を作ると録音が始まる。そこで文字を打ち始めたら、録音はやめる（打つつもりの人の録音を残さない）
    if (S.autoRec && S.rec.phase !== "idle" && e.target.value.trim()) stopRec(false, "文字で打つので、録音をやめました");
  });
  $("#typed").placeholder = TYPED_HINT;

  $("#typed").addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.isComposing || e.keyCode === 229) return;   // 日本語入力の確定の Enter は送らない
    if (!(e.metaKey || e.ctrlKey)) return;   // Enter だけ・Shift+Enter は改行（textarea の既定のまま）
    e.preventDefault();
    const v = e.target.value;
    if (!v.trim()) return;
    e.target.value = "";
    fitTyped();
    if (S.intent && S.intent.kind === "predict" && !S.typedKind) { sendPredictText(S.intent.target, v.trim()); return; }
    sendText(v, S.typedKind || (S.rec.kind === "answer" ? "answer" : "question"));
    S.rec.kind = null;
    typeFor(null);
    paintTalk();
  });

  $("#sidePane").addEventListener("input", (e) => {
    if (e.target.id !== "allFilter") return;
    S.allFilter = e.target.value;
    S.allFocus = true;
    clearTimeout(S.allTimer);
    S.allTimer = setTimeout(() => paintSide().then(() => { S.allFocus = false; }), 150);
  });

  $("#title").addEventListener("change", async (e) => {
    if (!S.active) return;
    await api("PATCH", `/api/sessions/${S.active}`, { title: e.target.value });
  });
  $("#title").addEventListener("keydown", (e) => { if (e.key === "Enter") e.target.blur(); });

  $("#scribeMode").addEventListener("change", async (e) => { await api("POST", "/api/prefs", { scribe: e.target.value }); loadState(); });
  $("#autoNext").addEventListener("change", async (e) => { await api("POST", "/api/prefs", { auto_next: e.target.checked ? "1" : "0" }); loadState(); });
  $("#autoLookup").addEventListener("change", async (e) => { await api("POST", "/api/prefs", { auto_lookup: e.target.checked ? "1" : "0" }); loadState(); });
  $("#closePage").addEventListener("click", () => $("#pageView").close());
  $("#predictPref").addEventListener("change", async (e) => {
    await api("POST", "/api/prefs", { predict: e.target.value });
    await loadState();
    S.hold = null;
    revealShown(true, false);   // 出し方を変えて畳まなくなった答えは、開いた扱いにする（誘いに乗らなかったの印は付けない）
    paintThread(false);
    paintStrip();
    paintSide();
  });
  $("#textSize").addEventListener("change", async (e) => { await api("POST", "/api/prefs", { text_size: e.target.value }); loadState(); });
  $("#chimePref").addEventListener("change", async (e) => { await api("POST", "/api/prefs", { chime: e.target.checked ? "1" : "0" }); loadState(); });
  // 帯の欄: ⌘Enter（Ctrl+Enter）で送る。Enter は改行
  $("#strip").addEventListener("input", (e) => { if (e.target.id === "stripText") fitStrip(); });
  $("#strip").addEventListener("keydown", (e) => {
    if (e.target.id !== "stripText" || e.key !== "Enter" || e.isComposing || e.keyCode === 229) return;
    if (!(e.metaKey || e.ctrlKey)) return;
    e.preventDefault();
    sendStrip();
  });
  $("#openSettings").addEventListener("click", openSettings);
  $("#closeSettings").addEventListener("click", () => $("#settings").close());
  $("#settings").addEventListener("cancel", (e) => { if (S.capture) e.preventDefault(); });
  $("#settings").addEventListener("close", () => { S.capture = null; $("#keyMsg").textContent = ""; $("#elevenKey").value = ""; });
  $("#healthAgain").addEventListener("click", async () => { paintHealth(null); paintHealth(await api("GET", "/api/health").catch((e) => ({ error: e.message }))); });
  $("#keyRows").addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.keyChange) { S.capture = b.dataset.keyChange; $("#keyMsg").textContent = ""; b.blur(); }
    else if ("keyCancel" in b.dataset) S.capture = null;
    else if (b.dataset.keyDefault) {
      const over = { ...((S.state && S.state.prefs.keys) || {}) };
      delete over[b.dataset.keyDefault];
      if (await saveKeys(over)) $("#keyMsg").textContent = "既定に戻しました。";
    }
    paintSettings();
  });
  $("#keysReset").addEventListener("click", async () => { S.capture = null; if (await saveKeys({})) $("#keyMsg").textContent = "すべて既定に戻しました。"; paintSettings(); });
  $("#tutorModel").addEventListener("change", async (e) => { await api("POST", "/api/prefs", { tutor_model: e.target.value }); loadState(); });
  async function saveEleven(key) {
    const res = await fetch("/api/settings/eleven-key", { method: "POST", headers: { ...H, "Content-Type": "application/json" }, body: JSON.stringify({ key }) });
    const r = await res.json().catch(() => ({}));
    $("#elevenKey").value = "";
    if (!res.ok) { $("#elevenMsg").textContent = "保存できませんでした: " + (r.detail || res.status); return; }
    $("#elevenMsg").textContent = key ? "鍵を保存しました。" : r.present ? "設定で入れた鍵は消しました（ほかの場所の鍵はまだ使います）。" : "鍵を消しました。";
    await loadState();
    paintHealth(await api("GET", "/api/health").catch((e) => ({ error: e.message })));
  }
  $("#elevenSave").addEventListener("click", () => { const k = $("#elevenKey").value.trim(); if (k) saveEleven(k); else $("#elevenMsg").textContent = "鍵を貼ってから押してください。"; });
  $("#elevenClear").addEventListener("click", () => saveEleven(""));
  $("#archive").addEventListener("click", async () => {
    if (!S.active) return;
    await api("PATCH", `/api/sessions/${S.active}`, { archived: true });
    S.active = null;
    await loadState();
    const first = S.state.sessions[0];
    if (first) open(first.id); else paintThread();
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && S.active) {
      api("POST", `/api/sessions/${S.active}/read`).catch(() => {});
      if (revealShown()) { paintThread(false); paintSide(); }   // 窓が隠れているあいだに届いた答え
    }
  });

  // 往復の列の高さを CSS に渡す（最後の往復を列の上まで送れるように、最後の往復の高さの下限にする）
  // 帯が出たり消えたりして列の高さが変わったときも、上に置いた往復は上に置いたままにする
  const fitThread = () => {
    const th = $("#thread");
    th.style.setProperty("--th-h", Math.max(0, th.clientHeight - 60) + "px");
    const el = S.pin && th.lastElementChild && Number(th.lastElementChild.dataset.turn) === S.pin.id ? th.lastElementChild : null;
    if (el) jumpTo(el);
  };
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(fitThread).observe($("#thread"));
  window.addEventListener("resize", fitThread);

  // ── 起動 ──────────────────────────────────────────────
  (async function boot() {
    paintKeys();
    fitThread();
    listen();
    await Promise.all([loadState(), loadStates(),
      api("GET", "/api/seen-views").then((r) => { S.seenAtBoot = new Set(r.seen); }).catch(() => {})]);
    let last = null;
    try { last = Number(localStorage.getItem("tonari.active")); } catch (e) { /* なし */ }
    const ss = S.state.sessions;
    const pick = ss.find((s) => s.id === last) || ss[ss.length - 1];
    if (pick) await open(pick.id, { quiet: false });
    offerElsewhere();
    paintTalk();
    setInterval(paintRail, 30000);
    api("GET", "/api/health").then(paintSetupWarn).catch(() => {});
    window.tonari = { S, open, goNext, sendText, loadState, loadDetail, paintSide, paintStrip, stripState, sendStrip, closeStrip, offerElsewhere, openAtlas, Atlas };
  })();
})();
