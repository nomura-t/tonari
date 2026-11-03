// となり — 画面。話題を回しながら声で問い、答えは文字と図で読む。
// 押して話す（Space）→ もう一度押すと送る → 送ったら答えの届いた話題へ移る（⌘] でも移れる）。
(function () {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const { render: md, split, esc } = window.TonariMD;
  const M = window.TonariMap;
  const V = window.TonariViews;
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
    ["reveal", "予想せずに答えを開く"],
    ["cancel", "録音をやめる（送らない）"],
  ];
  const KEY_DEFAULTS = { new: `${MODK}+KeyN`, next: `${MODK}+BracketRight`, open: `${MODK}+Digit`, talk: "Space", reveal: "Enter", cancel: "Escape" };
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
    if (ev.t === "turn" && ev.note) S.notes[ev.turn_id] = ev.note;
    if (ev.t === "done") {
      // 答えが流れてくるのをこの画面で見ていたなら、届いた瞬間に畳まない（予想は見る前にだけ意味がある）
      if (ev.session_id === S.active && S.streams[ev.turn_id] && !document.hidden) {
        api("POST", `/api/turns/${ev.turn_id}/reveal`).catch(() => {});
      }
      delete S.streams[ev.turn_id];
      if (ev.session_id === S.active && !document.hidden) api("POST", `/api/sessions/${ev.session_id}/read`).catch(() => {});
      else chime();
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

  async function loadDetail(scroll = true) {
    if (!S.active) { S.detail = null; paintThread(); return; }
    S.detail = await api("GET", `/api/sessions/${S.active}`);
    for (const t of S.detail.turns) if (t.predict) S.predicting.delete(t.id);
    paintThread(scroll);
    paintTop();
    paintRetCheck();
  }

  async function loadStates() {
    const r = await api("GET", "/api/concepts");
    S.states = {};
    for (const c of r.concepts) if (c.state) S.states[c.label] = c.state;
    S.allConcepts = r.concepts;
  }

  async function open(id, opts = {}) {
    if (S.rec.phase === "recording") return;
    S.active = id;
    S.editing = null;
    try { localStorage.setItem("tonari.active", String(id)); } catch (e) { /* 保存できなくても動く */ }
    paintRail();
    S.showReturn = false;   // 前の話題の確かめを持ち越さない
    S.retSnap = null;
    await loadDetail(true);
    api("POST", `/api/sessions/${id}/read`).catch(() => {});
    S.egoId = null;
    S.showReturn = !opts.quiet;
    S.retSnap = S.detail ? S.detail.return_check : null;
    if (S.retSnap) paintThread(true);   // 確かめの問いの元の答えを畳んで描き直す
    paintRetCheck();
    paintSide();
    if (!opts.quiet) showResume();
  }

  // ── 読む前の予想と、戻ったときの確かめ（v0.3・研究 d） ─────────────
  // 予想: 届いた答えを開く前に、自分の問いを見て一言予想する（予想の直後に答え合わせをする順にする）。
  // 戻ったとき: 前に開いた答えの確かめの問いを、その答えを畳んで1つだけ出す（話題を回す動きを間隔反復にする）。
  function foldable(t) {
    return S.state && S.state.prefs.predict !== "0" && t.status === "done" && !t.revealed_at && t.via !== "click" &&
      (!t.kind || t.kind === "question");
  }

  function foldTarget() {
    const d = S.detail;
    return d ? d.turns.find((t) => foldable(t)) : null;
  }

  function retCheck() {
    // 話題を開いた瞬間に決まった問いだけを出す（開いたまま2分たっても、途中で帯は出さない）
    const rc = S.retSnap;
    if (!rc || !S.showReturn || S.retDone.has(rc.id) || foldTarget()) return null;
    return rc;
  }

  function setIntent() {
    if (S.rec.phase !== "idle") return;
    const f = foldTarget(), rc = retCheck();
    S.intent = f ? { kind: "predict", target: f.id } : rc ? { kind: "answer", check: rc.id } : null;
    paintTalk();
  }

  function paintRetCheck() {
    const box = $("#retcheck");
    const rc = retCheck();
    if (!rc) { box.hidden = true; box.innerHTML = ""; setIntent(); return; }
    box.innerHTML = `<div class="rc-k">前に読んだ答えの確かめ・${esc(rc.qtype || "")}</div>` +
      `<p class="rc-q">${esc(rc.q)}</p>` +
      `<p class="rc-hint">その答えは、いま畳んであります。<kbd>${K("talk")}</kbd> で声で答えると、先生役が判定します。</p>` +
      `<div class="rc-act"><button class="primary" data-rcvoice="${rc.id}">声で答える</button>` +
      `<button class="ghost" data-rcstate="unknown" data-rcid="${rc.id}">分からない</button>` +
      `<button class="ghost" data-rcstate="skipped" data-rcid="${rc.id}">飛ばす</button></div>`;
    box.hidden = false;
    setIntent();
  }

  async function reveal(tid) {
    await api("POST", `/api/turns/${tid}/reveal`);
    const t = S.detail && S.detail.turns.find((x) => x.id === tid);
    if (t) t.revealed_at = Date.now() / 1000;
    paintThread(false);
    paintRetCheck();
    paintSide();
  }

  // ── 左の話題の列 ──────────────────────────────────────
  const PHASE = {
    recorded: ["送りました", "busy"], transcribing: ["文字にしています", "busy"], fixing: ["聞き違いを直しています", "busy"],
    thinking: ["考えています", "busy"], done: ["待っています", "idle"], error: ["止まりました", "err"],
  };

  function sessionPhase(s) {
    if (S.rec.phase !== "idle" && s.id === S.active) return ["録音中", "rec"];
    if (s.unread > 0 && s.id !== S.active) return ["答えが届きました", "ready"];
    if (!s.last) return ["話しかけてください", "idle"];
    return PHASE[s.last.status] || ["待っています", "idle"];
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
        `<span class="sess-s"><i class="dot"></i>${label}${s.unread > 1 ? `（${s.unread}件）` : ""}</span>` +
        `<span class="sess-l">${esc(last)}</span>` +
        `<span class="sess-m">${s.concepts ? `概念 ${s.concepts}` : ""}<span>${ago(s.updated_at)}</span></span></button>`;
    }).join("") || `<p class="rail-empty">まだ話題がありません。<br><kbd>${K("new")}</kbd> で作ってすぐ話せます。</p>`;
    const ready = st.sessions.filter((s) => s.unread > 0 && s.id !== S.active).length;
    $("#nextCount").textContent = ready ? `${ready}` : "";
    $("#nextBtn").classList.toggle("has", ready > 0);
    const sc = st.scribe;
    $("#scribeMode").value = st.prefs.scribe;
    $("#autoNext").checked = st.prefs.auto_next === "1";
    $("#predictPref").checked = st.prefs.predict !== "0";
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
    const where = last.status === "done" ? (foldTarget() ? "答えは開く前です" : retCheck() ? "確かめのあいだ答えを畳んでいます" : "答えは下にあります") : last.status === "error" ? "止まっています" : "いま考えています";
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
    else p.push("文字");
    const st = t.stage || {};
    if (st.stt != null) p.push(`文字に ${(st.stt / 1000).toFixed(1)}秒`);
    if (st.fix != null) p.push(`直し ${(st.fix / 1000).toFixed(1)}秒`);
    if (st.tutor != null) p.push(`答え ${Math.round(st.tutor / 1000)}秒`);
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
    return `<div class="grades">` + t.grades.map((g) => `<div class="gr g-${esc(g.result)}"><b>${JA[g.result] || "?"}</b>` +
      `<span>${esc(g.concept)} と ${esc(g.target)}</span>${g.evidence ? `<q>${esc(g.evidence)}</q>` : ""}` +
      `${g.result !== "miss" && !g.verified ? `<em>根拠の字が発言に無いので記録していません</em>` : ""}</div>`).join("") + `</div>`;
  }

  // 答えの本文の [[view:N]] の置き場所に図を入れる。最初の段落が図でなければ、言い切りとして大きく出す
  function viewHTML(v) {
    const first = !S.seenAtBoot.has(v.type);
    if (first) S.seenNow.add(v.type);
    return V.render(v, { states: S.states, firstTime: first });
  }

  function bodyHTML(text, views, ctx, skip) {
    const blocks = String(text || "").split(/\n\s*\n/);
    let h = "", leadDone = false;
    for (const b of blocks) {
      const m = b.trim().match(/^\[\[view:(\d+)\]\]$/);
      if (m) {
        const i = Number(m[1]);
        if (!skip.has(i) && views[i]) h += viewHTML(views[i]);
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
    if (!t.ref_turn || !(t.views || []).length) return { html: "", skip: new Set() };
    const prev = S.detail.turns.find((x) => x.id === t.ref_turn) || (S.refCache[t.ref_turn] || null);
    const pv = prev && (prev.views || [])[0];
    const nv = t.views[0];
    const left = pv ? viewHTML(pv) : `<div class="pair-text">前の答えは文だけでした。</div>`;
    return {
      html: `<div class="pair"><div class="pair-col"><span class="pair-k">前の見せ方</span>${left}</div>` +
        `<div class="pair-col"><span class="pair-k now">いまの見せ方</span>${viewHTML(nv)}</div></div>`,
      skip: new Set([0]),
    };
  }

  function actionsHTML(t) {
    return `<div class="ans-act" role="group" aria-label="この答えを">` +
      `<button class="chip" data-redo="short" data-tid="${t.id}">短く</button>` +
      `<button class="chip" data-redo="other" data-tid="${t.id}">別の見せ方で</button>` +
      `<button class="chip" data-redo="long" data-tid="${t.id}">詳しく</button></div>`;
  }

  function foldHTML(t) {
    return `<div class="fold" data-fold="${t.id}"><p class="fold-q"><span>あなたの問い</span>${esc(t.final_text || "")}</p>` +
      `<p class="fold-hint">読む前に、答えはどうなると思いますか。<kbd>${K("talk")}</kbd> で一言話して送ると、答えが開きます。</p>` +
      `<div class="fold-act"><button class="primary" data-predict="${t.id}">予想を話す</button>` +
      `<button class="ghost" data-reveal="${t.id}">すぐ読む<kbd>${K("reveal")}</kbd></button></div></div>`;
  }

  function predictHTML(t) {
    if (t.predict) return `<div class="predict"><span>読む前の予想</span>${esc(t.predict)}</div>`;
    if (S.predicting.has(t.id)) return `<div class="predict wait"><span>読む前の予想</span>文字にしています</div>`;
    return "";
  }

  function answerHTML(t) {
    if (foldable(t)) return foldHTML(t);
    const rc = retCheck();
    if (rc && rc.turn_id === t.id && t.status === "done") {
      return `<div class="folded"><p>この答えは、確かめの問いに答えるあいだ畳んであります。</p>` +
        `<button class="ghost" data-rcstate="skipped" data-rcid="${rc.id}">問いを飛ばして答えを見る</button></div>`;
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
      h += checksHTML(t);
      h += actionsHTML(t);
      return h;
    }
    if (t.status === "error") {
      return `<div class="ans-err"><p>${esc(t.error || "止まりました")}</p><button class="ghost" data-retry="${t.id}">もう一度送る</button></div>`;
    }
    return `<div class="pending" data-pending="${t.id}">${pendingHTML(t)}</div>`;
  }

  function pendingHTML(t) {
    const steps = [["transcribing", "文字に"], ["fixing", "直し"], ["thinking", "考え中"]];
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
      `<div class="answer">${answerHTML(t)}</div></article>`).join("");
    renderMermaid();
    const fresh = [...S.seenNow];
    if (fresh.length) { S.seenNow.clear(); api("POST", "/api/seen-views", { types: fresh }).catch(() => {}); }
    if (scroll) {
      const firstUnread = d.turns.find((t) => t.status === "done" && t.done_at > (d.session.read_at || 0));
      const el = firstUnread ? th.querySelector(`[data-turn="${firstUnread.id}"]`) : th.lastElementChild;
      if (el) el.scrollIntoView({ block: firstUnread ? "start" : "end" });
    } else if (atBottom) th.scrollTop = th.scrollHeight;
    else th.scrollTop = keepY;
  }

  // mermaid は図があるときだけ読み込む（版を固定）
  let merP = null;
  function renderMermaid() {
    const srcs = $$(".mermaid-src");
    if (!srcs.length) return;
    if (!merP) {
      merP = new Promise((ok, ng) => {
        const s = document.createElement("script");
        s.src = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js";
        s.onload = () => {
          const dark = matchMedia("(prefers-color-scheme: dark)").matches;
          window.mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "neutral", securityLevel: "strict",
            fontFamily: getComputedStyle(document.body).fontFamily });
          ok(window.mermaid);
        };
        s.onerror = ng;
        document.head.appendChild(s);
      });
    }
    merP.then(async (mer) => {
      for (const pre of srcs) {
        const code = pre.textContent;
        try {
          const { svg } = await mer.render("m" + Math.random().toString(36).slice(2), code);
          const fig = pre.parentElement;
          fig.innerHTML = svg;
        } catch (e) { pre.classList.add("bad"); }
      }
    }).catch(() => {});
  }

  // ── 右の地図 ──────────────────────────────────────────
  async function paintSide() {
    const pane = $("#sidePane");
    $$("#side .tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === S.sideTab));
    if (foldTarget() || retCheck()) {
      // 予想の前と確かめのあいだは、地図（答えの中身・例と非例）を伏せる
      pane.innerHTML = `<p class="side-empty">${foldTarget() ? "答えを開くと、" : "確かめが済むと、"}この話題の地図がここに出ます。</p>`;
      return;
    }
    if (S.sideTab === "ego") {
      let id = S.egoId;
      if (!id && S.detail) {
        const lastCenter = [...S.detail.turns].reverse().find((t) => t.center);
        id = lastCenter ? lastCenter.center : null;
      }
      if (!id) { pane.innerHTML = `<p class="side-empty">答えが届くと、説明の中心になった概念の位置がここに出ます。図の札を押すと、その概念を中心に描き直します。</p>`; return; }
      const e = await api("GET", `/api/concepts/${id}/ego`);
      const model = M.fromEgo(e);
      const c = e.center;
      const cov = c.coverage || { known: 0, total: 0 };
      const JA = { known: "分かる", shaky: "あやしい", unknown: "分からない" };
      pane.innerHTML = `<div class="ego-head"><h3>${esc(c.label)}</h3>${c.gist ? `<p>${esc(c.gist)}</p>` : ""}</div>` +
        `<figure class="cmap side">${M.render(model, { compact: true })}</figure>${M.chips(model)}` +
        `<div class="ego-state"><span class="k">自分の申告</span>${["known", "shaky", "unknown"].map((k) =>
          `<button class="sb s-${k}${c.state === k ? " on" : ""}" data-cstate="${k}" data-cid="${c.id}">${JA[k]}</button>`).join("")}</div>` +
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
    const sid = S.sideTab === "list" ? S.active : null;
    const r = await api("GET", "/api/concepts" + (sid ? `?session_id=${sid}` : ""));
    const groups = { unknown: [], shaky: [], known: [], none: [] };
    for (const c of r.concepts) groups[c.state || "none"].push(c);
    const NAME = { unknown: "分からない", shaky: "あやしい", known: "分かる", none: "まだ申告していない" };
    pane.innerHTML = Object.entries(groups).filter(([, v]) => v.length).map(([k, v]) =>
      `<section class="cl"><h4 class="s-${k}">${NAME[k]}<span>${v.length}</span></h4>` + v.map((c) =>
        `<button class="cl-i" data-ego="${c.id}"><span>${esc(c.label)}</span>${c.coverage.total ? `<small>${c.coverage.known}/${c.coverage.total}</small>` : ""}</button>`).join("") +
      `</section>`).join("") || `<p class="side-empty">まだ概念がありません。</p>`;
  }

  function relList(e) {
    const rows = [];
    const JA = { known: "分かる", shaky: "あやしい", unknown: "分からない" };
    const DIR = { broader: "上位", narrower: "下位", opposite: "対", related: "関係" };
    for (const d of ["broader", "narrower", "opposite", "related"]) {
      for (const n of e[d] || []) {
        rows.push(`<div class="rl"><span class="rl-d">${DIR[d]}${n.detail ? "・" + esc(n.detail) : ""}</span>` +
          `<button class="rl-n" data-ego="${n.id}">${esc(n.label)}</button>` +
          `<span class="rl-b">${["known", "unknown"].map((k) => `<button class="mini s-${k}${n.rstate === k ? " on" : ""}" data-rstate="${k}" data-rid="${n.rid}" title="この関係が${JA[k]}">${k === "known" ? "✓" : "?"}</button>`).join("")}</span></div>`);
      }
    }
    return rows.length ? `<div class="rels">${rows.join("")}</div>` : "";
  }

  // ── 録音 ──────────────────────────────────────────────
  async function startRec(kind = null) {
    if (S.rec.phase !== "idle") return;
    if (!S.active) await newSession(false);
    const it = kind ? {} : (S.intent || {});
    S.rec.phase = "starting";
    S.rec.kind = kind || it.kind || null;
    S.rec.target = it.target || null;
    S.rec.check = kind ? null : (it.check || null);
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
    } catch (e) {
      S.rec.phase = "idle";
      paintTalk();
      toast("マイクが使えませんでした。システム設定のプライバシーでマイクを許可してください。");
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

  async function stopRec(send) {
    if (S.rec.phase === "starting") { S.rec.phase = "idle"; paintTalk(); return; }
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
    if (!send) { toast("録音をやめました"); paintRail(); setIntent(); return; }
    if (blob.size < 1500) { toast("短すぎて送りませんでした"); paintRail(); return; }
    const fd = new FormData();
    fd.append("audio", blob, "voice.webm");
    if (kind) fd.append("kind", kind);
    if (kind === "predict" && target) fd.append("ref_turn", String(target));
    if (kind === "answer" && check) fd.append("check_id", String(check));
    try {
      await api("POST", `/api/sessions/${sid}/voice`, fd);
    } catch (e) { toast("送れませんでした: " + e.message); return; }
    if (kind === "predict" && target) {
      // 予想は先生役に送らない。話し終えたらすぐ答えを開き、予想の文は文字になりしだい答えの上に出る
      S.predicting.add(target);
      await reveal(target);
      return;
    }
    if (kind === "answer" && check) { S.retDone.add(check); S.showReturn = false; paintRetCheck(); paintSide(); }
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
    $("#recHint").textContent = p === "recording" ? `もう一度 ${K("talk")} で送る・${K("cancel")} でやめる` : `${K("talk")} で話し始める`;
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
    if (startTalking) startRec();
  }

  async function sendText(text, kind = "question", via = "text") {
    if (!text.trim()) return;
    if (!S.active) await newSession(false);
    await api("POST", `/api/sessions/${S.active}/text`, { text, kind, via });
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
    if ($("#settings").open) return;
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
      if (f) { e.preventDefault(); reveal(f.id); return; }
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
    if (!S.capture && hit(e, "talk") && !typing()) e.preventDefault();
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
    const el = e.target.closest("button, a, .node, mark.edit, .term");
    if (!el) return;
    const d = el.dataset;
    if (el.classList.contains("sess")) { open(Number(d.id)); return; }
    if (el.id === "newSession") { newSession(true); return; }
    if (el.id === "nextBtn") { goNext(); return; }
    if (el.id === "talk") { if (S.rec.phase === "idle") startRec(S.rec.kind); else if (S.rec.phase === "recording") stopRec(true); return; }
    if (el.classList.contains("tab")) { S.sideTab = d.tab; paintSide(); return; }
    if (d.shelf) {
      e.preventDefault();
      try { const r = await api("GET", `/api/shelf/${d.shelf}`); window.open(r.url, "_blank"); } catch (err) { toast("棚に見つかりません"); }
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
    if (d.predict) { if (S.rec.phase === "idle") startRec(); return; }
    if (d.rcvoice) { if (S.rec.phase === "idle") startRec(); return; }
    if (d.rcstate) {
      const id = Number(d.rcid);
      await api("POST", "/api/mastery", { check_id: id, state: d.rcstate });
      S.retDone.add(id);
      S.showReturn = false;   // 戻ったときの確かめは、1回の戻りにつき1問だけ
      paintThread(false);
      paintRetCheck();
      paintSide();
      loadDetailSoon();
      return;
    }
    if (d.askc) { sendText(`${d.askc}を、私が分かっている周りの概念を足場にして説明して`, "question", "click"); return; }
    if (d.askrel) { sendText(`${d.askrel}の周りの関係を、確かめの問題にして出して`, "command", "click"); return; }
    if (d.ask) { sendText(`${d.ask}を説明して`, "question", "click"); return; }
    if (d.redo) {
      const t = S.detail.turns.find((x) => x.id === Number(d.tid));
      const name = t && t.views && t.views[0] ? t.views[0].name : "文だけ";
      const msg = {
        short: ["直前の答えを短くして（3文まで、図は1つまで）", "短く"],
        other: [`直前の答えを、別の見せ方で見せ直して（中身は同じ。いまの「${name}」とは違う形を、見せ方の選び方の次に当てはまるものから選ぶ）`, "別の見せ方で"],
        long: ["直前の答えを詳しくして（前の図は消さずに、足りない所を下に足す）", "詳しく"],
      }[d.redo];
      await api("POST", `/api/sessions/${S.active}/text`, { text: msg[0], kind: "command", via: "click", title: msg[1],
        ref_turn: d.redo === "other" ? Number(d.tid) : undefined });
      await loadState();
      loadDetail(false);
      return;
    }
    if (d.detail) {
      await api("PATCH", `/api/sessions/${S.active}`, { detail: d.detail });
      if (S.detail) S.detail.session.detail = d.detail;
      paintTop();
      toast({ auto: "詳しさは記録を見て先生役が決めます", short: "これからの答えを短くします", long: "これからの答えを詳しくします" }[d.detail]);
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

  $("#typed").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      const v = e.target.value;
      e.target.value = "";
      sendText(v, S.rec.kind === "answer" ? "answer" : "question");
      S.rec.kind = null;
      paintTalk();
    }
  });

  $("#title").addEventListener("change", async (e) => {
    if (!S.active) return;
    await api("PATCH", `/api/sessions/${S.active}`, { title: e.target.value });
  });
  $("#title").addEventListener("keydown", (e) => { if (e.key === "Enter") e.target.blur(); });

  $("#scribeMode").addEventListener("change", async (e) => { await api("POST", "/api/prefs", { scribe: e.target.value }); loadState(); });
  $("#autoNext").addEventListener("change", async (e) => { await api("POST", "/api/prefs", { auto_next: e.target.checked ? "1" : "0" }); loadState(); });
  $("#predictPref").addEventListener("change", async (e) => {
    await api("POST", "/api/prefs", { predict: e.target.checked ? "1" : "0" });
    await loadState();
    paintThread(false);
    paintRetCheck();
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
    if (!document.hidden && S.active) api("POST", `/api/sessions/${S.active}/read`).catch(() => {});
  });

  // ── 起動 ──────────────────────────────────────────────
  (async function boot() {
    paintKeys();
    listen();
    await Promise.all([loadState(), loadStates(),
      api("GET", "/api/seen-views").then((r) => { S.seenAtBoot = new Set(r.seen); }).catch(() => {})]);
    let last = null;
    try { last = Number(localStorage.getItem("tonari.active")); } catch (e) { /* なし */ }
    const ss = S.state.sessions;
    const pick = ss.find((s) => s.id === last) || ss[ss.length - 1];
    if (pick) await open(pick.id, { quiet: false });
    paintTalk();
    setInterval(paintRail, 30000);
    api("GET", "/api/health").then(paintSetupWarn).catch(() => {});
    window.tonari = { S, open, goNext, sendText, loadState, paintSide };
  })();
})();
