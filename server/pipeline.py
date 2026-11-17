"""1回の往復を進める: 録音 → 文字（Apple と Scribe）→ 直し（整形役）→ 先生役（opus）→ 札の取り込み。

段ごとに turn の status を書き換えて画面に知らせる。どの段で落ちても、そこまでの記録（生の文字起こし・直した文）は
残っているので、画面の「もう一度送る」でやり直せる。話題が違えば並んで進み、同じ話題の中は先生役の鍵で順番になる。
"""
import asyncio
import json
import re
import time
import traceback

from . import brain, config, corpus, db, events, fixer, flow, judge, predfb, readings, recorder, research, stt, tutor

TASKS: set[asyncio.Task] = set()
RATE_RE = re.compile(r"rate.?limit|429|overloaded|usage limit|529", re.I)


def spawn(coro) -> None:
    t = asyncio.create_task(coro)
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)


def set_turn(turn_id: int, **kw) -> None:
    if not kw:
        return
    keys = ", ".join(f"{k}=?" for k in kw)
    with db.tx() as con:
        con.execute(f"UPDATE turn SET {keys} WHERE id=?", (*kw.values(), turn_id))
        sid = db.row(con, "SELECT session_id FROM turn WHERE id=?", (turn_id,))["session_id"]
        con.execute("UPDATE session SET updated_at=? WHERE id=?", (db.now(), sid))
    ev = {"t": "turn", "turn_id": turn_id, "session_id": sid}
    ev.update({k: v for k, v in kw.items() if k in ("status", "error", "title", "final_text", "fixed_text")})
    events.publish(ev)


def prev_context(session_id: int, before_seq: int) -> str:
    with db.tx() as con:
        r = db.row(con, """SELECT final_text, answer_md FROM turn WHERE session_id=? AND seq<? AND status='done'
                           ORDER BY seq DESC LIMIT 1""", (session_id, before_seq))
    if not r:
        return ""
    ans = tutor.strip_blocks(r["answer_md"] or "")[:300]
    return f"本人: {r['final_text']}\n先生役: {ans}"


# 本人が自信の無さを言葉にした所（研究 d の 4-9 の確信度つき回答を、聞かずに取る）。今は記録と先生役への添え書きだけ
HEDGE_RE = re.compile(r"でしたっけ|だっけ|たぶん|多分|かもしれ|気がする|ですよね|でしたよね|だよね|あってる|合ってる|自信(?:が)?ない|よく分から|よくわから")


def hedges(*texts: str | None) -> list[str]:
    found: list[str] = []
    for t in texts:
        for m in HEDGE_RE.findall(t or ""):
            if m not in found:
                found.append(m)
    return found


def keyterms(session_id: int) -> list[str]:
    terms = fixer.glossary(session_id, 40)   # Scribe と Haas の用語は50まで（stt.scribe・stt.haas_keywords で切る）
    for m in fixer.mishears(20):
        if m["meant"] not in terms:
            terms.append(m["meant"])
    return terms


async def run_voice(turn_id: int, kind_hint: str | None = None) -> None:
    with db.tx() as con:
        t = db.row(con, "SELECT * FROM turn WHERE id=?", (turn_id,))
    sid, stage = t["session_id"], json.loads(t["stage_ms"] or "{}")
    if kind_hint == "predict":
        await run_predict(turn_id, t)
        return
    try:
        set_turn(turn_id, status="transcribing")
        t0 = time.time()
        r = await stt.transcribe(config.AUDIO_DIR / t["audio"], keyterms(sid))
        stage["stt"] = int((time.time() - t0) * 1000)
        apple = r["apple"]
        how = {"scribe_mode": r["scribe_mode"], "local_mode": r["local_mode"], "second": r["second_engine"], "stt_errors": r["errors"],
               "hedges": hedges((apple or {}).get("text"), r["second"])}
        set_turn(turn_id, audio_sec=r["sec"], apple_text=(apple or {}).get("text"),
                 apple_json=db.jdump(apple) if apple else None, scribe_text=r["scribe"], scribe_ms=r["scribe_ms"],
                 haas_text=r["haas"], haas_ms=r["haas_ms"], stage_ms=db.jdump({**stage, **how}))
        if not ((apple or {}).get("text") or r["second"]):
            set_turn(turn_id, status="error", error="声が聞き取れませんでした（無音か短すぎます）")
            return
        set_turn(turn_id, status="fixing")
        t1 = time.time()
        f = await fixer.fix(sid, apple, r["second"], prev_context(sid, t["seq"]), r["second_engine"] or "scribe")
        stage["fix"] = int((time.time() - t1) * 1000)
        set_turn(turn_id, fixed_text=f["text"], final_text=f["text"], edits_json=db.jdump(f["edits"]),
                 unsure_json=db.jdump(f["unsure"]), title=f["title"],
                 stage_ms=db.jdump({**stage, **how, "fix_fallback": f["fallback"]}))
        name_session(sid, f["title"])
        await ask_tutor(turn_id, f["text"], kind_hint or f["kind"], "voice", f["unsure"], {**stage, "hedges": how["hedges"]})
    except Exception as e:
        traceback.print_exc()
        set_turn(turn_id, status="error", error=f"{type(e).__name__}: {e}"[:300])


async def run_predict(turn_id: int, t: dict) -> None:
    """読む前の予想（声）を文字にして直し、予想した答えに書き添える。先生役には送らない。
    予想の往復は最初から superseded で作るので、往復の列にも話題の「最後」にも出ない。
    聞き取れなかったときは、画面に知らせる（「文字にしています」のまま残さない）。"""
    sid = t["session_id"]
    try:
        r = await stt.transcribe(config.AUDIO_DIR / t["audio"], keyterms(sid))
        if (r["apple"] or {}).get("text") or r["second"]:
            f = await fixer.fix(sid, r["apple"], r["second"], prev_context(sid, t["seq"]), r["second_engine"] or "scribe")
            if save_predict(turn_id, t["ref_turn"], f["text"]):
                return
    except Exception:
        traceback.print_exc()
    events.publish({"t": "predict_failed", "turn_id": t["ref_turn"], "session_id": sid})


def save_predict(turn_id: int | None, target: int | None, text: str, via: str = "voice") -> bool:
    """読む前の予想（声か文字）を、予想した答えの往復に書き添える。声の予想の往復そのものは列に出さない（superseded）。
    v0.6: 答えを待つあいだの予想は、答えがまだ届いていない往復に付く。そのときは開いた時刻を付けない
    （開いた時刻は、戻ったときの確かめの時計なので、答えが画面に出たときに付ける）。"""
    with db.tx() as con:
        r = db.row(con, "SELECT session_id, status, stage_ms, done_at FROM turn WHERE id=?", (target,)) if target else None
        if r:
            st = json.loads(r["stage_ms"] or "{}")
            st["predict"] = text[:2000]   # 送り直し（質問として）で欠けないよう、発言と同じ長さまで残す
            st["predict_via"] = via
            st.pop("predict_fb", None)    # 前の予想への照らし合わせは外す（新しい予想に付け直す）
            if r["status"] == "done":
                st.setdefault("revealed_at", db.now())
            con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (db.jdump(st), target))
            con.execute("INSERT INTO log(kind, target, evidence, turn_id, by, at) VALUES('predict',?,?,?,?,?)",
                        (target, text[:400], turn_id, via, db.now()))
            flow.note_predict(con)
        if turn_id:
            con.execute("UPDATE turn SET status='superseded', final_text=? WHERE id=?", (text[:2000], turn_id))
    if r:
        events.publish({"t": "turn", "turn_id": target, "session_id": r["session_id"]})
        # 予想と答えの照らし合わせ（v0.6）。答えがもう届いていればすぐ、まだなら届いたときに走らせる（予備だけ温めておく）
        if r["status"] == "done":
            maybe_predict_fb(target)
        elif predfb.ENABLED:
            predfb.POOL.warm()
    return bool(r)


def maybe_predict_fb(turn_id: int, force: bool = False) -> bool:
    """予想と答えがそろった往復に、照らし合わせ役を走らせる（v0.6）。走っている・済んでいる往復には走らせない
    （force は、前の版でした予想に付けるときと、取れなかったあとのやり直し）。"""
    if not predfb.ENABLED:
        return False
    with db.tx() as con:
        r = db.row(con, "SELECT session_id, status, final_text, answer_md, stage_ms FROM turn WHERE id=?", (turn_id,))
        if not r or r["status"] != "done" or not r["answer_md"]:
            return False
        st = json.loads(r["stage_ms"] or "{}")
        prose = tutor.strip_blocks(r["answer_md"])
        if not predfb.eligible(st.get("predict"), prose):
            return False
        fb = st.get("predict_fb") or {}
        if fb.get("state") == "run":
            if db.now() - float(fb.get("at") or 0) < predfb.STALE_SEC:
                return False            # いま走っている
        elif fb and not force:
            return False                # もう返してある（取れなかった分のやり直しは force）
        st["predict_fb"] = {"state": "run", "at": db.now()}
        con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (db.jdump(st), turn_id))
    spawn(run_predict_fb(turn_id, r["session_id"], r["final_text"] or "", st["predict"], prose))
    events.publish({"t": "predict_fb", "turn_id": turn_id, "session_id": r["session_id"]})
    return True


async def run_predict_fb(turn_id: int, sid: int, said: str, pred: str, prose: str) -> None:
    """照らし合わせ役の返しを、その往復に書き添える。取れなかったときは、取れなかった印を残す（画面がやり直しを出す）。
    理解の記録（分かる・分からない）には入れない。段の数だけを log に残す。"""
    res = None
    try:
        res = await predfb.judge(said, pred, prose)
    except Exception:
        traceback.print_exc()
    with db.tx() as con:
        old = db.row(con, "SELECT stage_ms FROM turn WHERE id=?", (turn_id,))
        if not old:
            return
        st = json.loads(old["stage_ms"] or "{}")
        if st.get("predict") != pred:
            return      # 待つあいだに、予想が外されたか言い直された。古い予想への返しは書かない（言い直しには別に走っている）
        st["predict_fb"] = {"state": "done", **res} if res else {"state": "fail"}
        con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (db.jdump(st), turn_id))
        if res:
            con.execute("INSERT INTO log(kind, target, state, turn_id, at) VALUES('predict_fb',?,?,?,?)",
                        (turn_id, res["core"], turn_id, db.now()))
    events.publish({"t": "predict_fb", "turn_id": turn_id, "session_id": sid})


def clear_predict(target: int) -> str | None:
    """書き添えた予想を外す（取り違えたときの戻し。v0.6）。外した予想の文を返す。"""
    with db.tx() as con:
        r = db.row(con, "SELECT session_id, stage_ms FROM turn WHERE id=?", (target,))
        if not r:
            return None
        st = json.loads(r["stage_ms"] or "{}")
        text = st.pop("predict", None)
        st.pop("predict_via", None)
        st.pop("predict_fb", None)
        if text is None:
            return None
        con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (db.jdump(st), target))
        con.execute("INSERT INTO log(kind, target, evidence, at) VALUES('unpredict',?,?,?)", (target, text[:400], db.now()))
    events.publish({"t": "turn", "turn_id": target, "session_id": r["session_id"]})
    return text


async def run_text(turn_id: int, kind: str = "question") -> None:
    with db.tx() as con:
        t = db.row(con, "SELECT * FROM turn WHERE id=?", (turn_id,))
    name_session(t["session_id"], t["title"] or t["final_text"][:16])
    try:
        await ask_tutor(turn_id, t["final_text"], kind, t["via"], json.loads(t["unsure_json"] or "[]"),
                        {"hedges": hedges(t["final_text"])} if t["via"] == "text" else {})
    except Exception as e:
        traceback.print_exc()
        set_turn(turn_id, status="error", error=f"{type(e).__name__}: {e}"[:300])


def name_session(session_id: int, title: str) -> None:
    if not title:
        return
    with db.tx() as con:
        s = db.row(con, "SELECT title FROM session WHERE id=?", (session_id,))
        if s and s["title"] == "新しい話題":
            con.execute("UPDATE session SET title=? WHERE id=?", (title[:24], session_id))
            events.publish({"t": "session", "session_id": session_id, "title": title[:24]})


async def ask_tutor(turn_id: int, text: str, kind: str, via: str, unsure: list[dict], stage: dict) -> None:
    with db.tx() as con:
        t = db.row(con, "SELECT session_id FROM turn WHERE id=?", (turn_id,))
        s = db.row(con, "SELECT * FROM session WHERE id=?", (t["session_id"],))
    sid = s["id"]
    set_turn(turn_id, status="thinking")
    ref = None
    with db.tx() as con:
        t = db.row(con, "SELECT ref_turn, seq, stage_ms FROM turn WHERE id=?", (turn_id,))
        check_id = json.loads(t["stage_ms"] or "{}").get("check_id") if t else None
        # 直前の答えを読む前に本人が言った予想（あれば先生役に添える）
        pv = db.row(con, """SELECT stage_ms FROM turn WHERE session_id=? AND seq<? AND status='done'
                            ORDER BY seq DESC LIMIT 1""", (sid, t["seq"])) if t else None
        predict = json.loads(pv["stage_ms"] or "{}").get("predict") if pv else None
        if t and t["ref_turn"]:
            r = db.row(con, "SELECT answer_md, stage_ms FROM turn WHERE id=?", (t["ref_turn"],))
            views = tutor.turn_blocks(r["answer_md"], json.loads(r["stage_ms"] or "{}"))["views"] if r else []
            mv = tutor.main_view(views)   # たとえの塊は図に数えない
            ref = {"name": mv["name"], "type": mv["type"]} if mv else {"name": None, "type": "text"}
    # 会話を始めたときの指示が今の指示と違えば --resume せずに新しい会話で始め、これまでの往復を添える（--resume は
    # 始めたときの指示を使い続けるため。tutor.resume_plan）。この起動ですでに動いている先生役は今の指示で始めたもの
    sig = tutor.prompt_sig()
    alive = sid in brain.TUTORS.tutors and brain.TUTORS.tutors[sid].alive
    resume, need_recap = (s["claude_sid"], False) if alive else tutor.resume_plan(s["claude_sid"], s.get("prompt_sig"), sig)
    recap = tutor.recap_text(sid, t["seq"]) if need_recap and t else None
    if need_recap:
        stage["fresh_prompt"] = True   # 指示が変わったので新しい会話で始めた往復の印
    plan = tutor.detail_plan(sid, text, kind, s.get("detail") or "auto", ref, t["seq"] if t else None)
    stage["budget"] = plan   # この答えの本文の字数の目安と理由（v0.5・話の間合い）
    # v0.6: 答えを待つあいだに予想を誘うか（flow.predict_offer）。種類と誘いは、答えが届く前に記録へ書く（画面が待ちの間に読む）
    stage["kind"] = kind
    with db.tx() as con:
        if t and flow.predict_offer(con, text, kind, via, bool(t["ref_turn"])):
            stage["offer"] = "predict"
        now_st = json.loads((db.row(con, "SELECT stage_ms FROM turn WHERE id=?", (turn_id,)) or {}).get("stage_ms") or "{}")
        now_st.update({k: stage[k] for k in ("kind", "offer", "budget") if k in stage})
    set_turn(turn_id, stage_ms=db.jdump(now_st))
    content = tutor.turn_content(sid, text, kind, via, unsure, s.get("detail") or "auto", ref, stage.get("hedges"),
                                 predict, check_id if kind == "answer" else None, recap, plan)
    if config.RECORDER != "off":
        recorder.POOL.warm()   # 答えが流れるあいだに記録役を立てておく
    t2 = time.time()
    md = ""
    for attempt in range(4):
        tu = brain.TUTORS.get(sid, tutor.system_prompt(), s["model"], resume)
        md = ""
        warmed = False
        try:
            async for kind_, data in tu.ask(content):
                if kind_ == "text":
                    md += data
                    if not warmed and "```tonari-analogy" in md:
                        judge.PAIR_POOL.warm()   # 答えの残りが流れるあいだに、対を確かめる判定役を立てておく
                        warmed = True
                    events.publish({"t": "delta", "turn_id": turn_id, "session_id": sid, "text": data})
                elif kind_ == "tool":
                    events.publish({"t": "tool", "turn_id": turn_id, "session_id": sid, "name": data})
                elif kind_ == "sid" and (data != s["claude_sid"] or s.get("prompt_sig") != sig):
                    with db.tx() as con:
                        con.execute("UPDATE session SET claude_sid=?, prompt_sig=? WHERE id=?", (data, sig, sid))
                    s["claude_sid"], s["prompt_sig"] = data, sig
            break
        except brain.BrainError as e:
            msg = str(e)
            if attempt < 3 and (RATE_RE.search(msg) or "プロセスが止まりました" in msg):
                wait = 20 * (attempt + 1)
                events.publish({"t": "turn", "turn_id": turn_id, "session_id": sid, "status": "thinking",
                                "note": f"先生役が混んでいます。{wait}秒後にもう一度送ります"})
                if tu.resume_sid is None and not need_recap:   # 新しい会話で始め直す途中なら前の会話の id は残す（要約の元）
                    with db.tx() as con:
                        con.execute("UPDATE session SET claude_sid=NULL WHERE id=?", (sid,))
                    s["claude_sid"] = None
                await asyncio.sleep(wait)
                events.publish({"t": "reset", "turn_id": turn_id, "session_id": sid})
                continue
            raise
    stage["tutor"] = int((time.time() - t2) * 1000)
    stage["kind"] = kind
    pre = tutor.parse_blocks(md)
    grades = pre["grade"]
    judged = None
    if grades:
        t3 = time.time()
        judged = await judge.second_opinion(sid, grades, text, check_id if kind == "answer" else None)
        stage["judge"] = int((time.time() - t3) * 1000)
    analogies = [v for v in pre["views"] if v["type"] == "analogy"]
    if analogies:
        # A5: 機械の決まりを通ったたとえの対を、判定役がもう一度確かめる（結果は読み直しでも当てる）
        t4 = time.time()
        stage["analogy"] = await judge.check_pairs(tutor.strip_blocks(md), analogies)
        stage["pair_judge"] = int((time.time() - t4) * 1000)
    finish(turn_id, sid, md, text, stage, kind, judged, check_id if kind == "answer" else None)
    spawn(run_recorder(turn_id, sid, md, text))
    maybe_predict_fb(turn_id)   # 待つあいだに予想していれば、届いた答えと照らし合わせる（v0.6）
    # v0.6: 話題の最初の問いは、答えを届けたあとに、別の読みがあったかを読みの判定役が確かめる（readings.py）
    with db.tx() as con:
        first = t is not None and db.row(con, "SELECT COUNT(*) AS n FROM turn WHERE session_id=? AND seq<? AND status='done'",
                                         (sid, t["seq"]))["n"] == 0
    prose = tutor.strip_blocks(md)
    if readings.eligible(kind, via, first, bool(t and t["ref_turn"]), text, prose):
        readings.POOL.warm()
        spawn(run_readings(turn_id, sid, text, prose))
    if pre.get("lookup") and db.get_pref("auto_lookup", "0") == "1":
        start_research(sid, pre["lookup"]["q"], turn_id)   # 設定で「聞かずに調べる」にしているとき
    await brain.TUTORS.trim()


async def run_recorder(turn_id: int, sid: int, md: str, said: str) -> None:
    """答えを届けたあとに、記録役が記録用の地図と確かめの問いを作って、この往復に足す（v0.5）。
    先生役が自分で書いた塊（位置の図を答えの図にした・古い指示の会話）があれば、その分は作らない。"""
    pre = tutor.parse_blocks(md)
    need_map, need_check = pre["map"] is None, not pre["check"]
    if config.RECORDER == "off" or not (need_map or need_check) or len(tutor.strip_blocks(md)) < 40:
        return
    t0 = time.time()
    try:
        extra = await recorder.record(sid, said, md, need_map, need_check)
    except Exception as e:
        traceback.print_exc()
        extra, err = "", f"{type(e).__name__}: {e}"[:200]
    else:
        err = None
    ms = int((time.time() - t0) * 1000)
    add = tutor.parse_blocks(extra) if extra else None
    with db.tx() as con:
        old = db.row(con, "SELECT answer_md, stage_ms, status FROM turn WHERE id=?", (turn_id,))
        if not old or old["status"] != "done" or old["answer_md"] != md:
            return   # 記録役を待つあいだに、この往復が送り直された
        st = json.loads(old["stage_ms"] or "{}")
        st["recorder"] = ms
        checks = []
        if err:
            st["recorder_error"] = err
        if add:
            kept, dropped = tutor.filter_checks(add["check"], md)
            if add["map"] and need_map:
                st["center"] = tutor.merge_map(con, sid, turn_id, add["map"])
            checks = tutor.save_checks(con, sid, turn_id, kept) if kept and need_check else []
            st["block_errors"] = (st.get("block_errors") or []) + add["errors"] + dropped
            st["recorded"] = {"map": bool(add["map"] and need_map), "checks": len(checks)}
            md2 = md.rstrip() + "\n\n" + extra
        else:
            md2 = md
        con.execute("UPDATE turn SET answer_md=?, stage_ms=? WHERE id=?", (md2, db.jdump(st), turn_id))
    events.publish({"t": "recorded", "turn_id": turn_id, "session_id": sid, "center": st.get("center"), "checks": len(checks)})


async def run_readings(turn_id: int, sid: int, said: str, prose: str) -> None:
    """読みの判定役の結果（別の読み）を、その往復に書き添える。取れなかった・無かったときは何もしない。"""
    try:
        alt = await readings.judge(said, prose)
    except Exception:
        traceback.print_exc()
        return
    if not alt:
        return
    with db.tx() as con:
        old = db.row(con, "SELECT stage_ms, status FROM turn WHERE id=?", (turn_id,))
        if not old or old["status"] != "done":
            return
        st = json.loads(old["stage_ms"] or "{}")
        st["alt"] = alt
        con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (db.jdump(st), turn_id))
    events.publish({"t": "alt", "turn_id": turn_id, "session_id": sid})


def start_research(sid: int, question: str, from_turn: int | None = None) -> int:
    """Web で調べる往復を話題に足して、調べ役を走らせる（v0.5）。答えの往復と同じ列に並び、待つあいだ別の話題へ移れる。"""
    from .app import new_turn
    with db.tx() as con:
        st = {"kind": "research", **({"from_turn": from_turn} if from_turn else {})}   # 開いた時刻は画面が出したときに付く
        tid = new_turn(con, sid, "research", final_text=question[:1000], title=("調べ: " + question)[:16], stage_ms=db.jdump(st))
    events.publish({"t": "turn", "turn_id": tid, "session_id": sid, "status": "recorded", "new": True})
    spawn(run_research(tid))
    return tid


async def run_research(turn_id: int) -> None:
    with db.tx() as con:
        t = db.row(con, "SELECT * FROM turn WHERE id=?", (turn_id,))
        s = db.row(con, "SELECT model FROM session WHERE id=?", (t["session_id"],))
    sid, stage = t["session_id"], json.loads(t["stage_ms"] or "{}")
    set_turn(turn_id, status="thinking")
    loop = asyncio.get_running_loop()

    def on_tool(name: str, inp: dict) -> None:   # 調べ役の進み（検索の語・開いたページ）を画面に出す
        what = inp.get("query") or inp.get("url") or ""
        loop.call_soon_threadsafe(events.publish, {"t": "tool", "turn_id": turn_id, "session_id": sid,
                                                    "name": f"{'検索' if name == 'WebSearch' else '読む'}: {str(what)[:60]}"})
    t0 = time.time()
    try:
        page = await research.run(t["final_text"], config.RESEARCH_MODEL or s["model"], on_tool)
        page["session_id"], page["turn_id"] = sid, turn_id
        research.save(page)
        await asyncio.to_thread(corpus.refresh)   # 写しに混ぜる（先生役が次から読める・「」と札を照らせる）
    except Exception as e:
        traceback.print_exc()
        set_turn(turn_id, status="error", error=f"調べられませんでした（{type(e).__name__}: {e}）"[:300])
        return
    stage.update(research=int((time.time() - t0) * 1000), page=page["id"], counts=page.get("counts"), rules=4)
    with db.tx() as con:
        con.execute("UPDATE turn SET answer_md=?, status='done', done_at=?, stage_ms=? WHERE id=?",
                    (research.summary_md(page), db.now(), db.jdump(stage), turn_id))
        con.execute("UPDATE session SET updated_at=? WHERE id=?", (db.now(), sid))
    events.publish({"t": "done", "turn_id": turn_id, "session_id": sid, "center": None, "checks": 0})


def finish(turn_id: int, sid: int, md: str, said: str, stage: dict, kind: str = "question",
           judged: list | None = None, check_id: int | None = None) -> None:
    blocks = tutor.parse_blocks(md, pair_verdicts=stage.get("analogy"))
    kept, dropped = tutor.filter_checks(blocks["check"], md)
    blocks["errors"] += dropped
    with db.tx() as con:
        center = tutor.merge_map(con, sid, turn_id, blocks["map"]) if blocks["map"] else None
        tutor.save_analogies(con, sid, turn_id, blocks["views"])
        grades = tutor.apply_grades(con, sid, turn_id, blocks["grade"], said, kind, judged, check_id) if blocks["grade"] else []
        if kind == "answer" and check_id and not blocks["grade"]:
            con.execute("UPDATE checkq SET status='answered' WHERE id=? AND status='open'", (check_id,))
        checks = tutor.save_checks(con, sid, turn_id, kept) if kept else []
        old = db.row(con, "SELECT via, stage_ms FROM turn WHERE id=?", (turn_id,))
        st = json.loads(old["stage_ms"] or "{}") if old else {}
        st.update(stage)
        # 予想の帯を出さない答え（命令・確かめへの答え・図からの依頼・予想を止めている）は、届いた時点で開いたとみなす。
        # そうしないと、その答えの確かめの問いが戻ったときに出ない（return_check は開いた時刻から数える）
        # 開いた時刻（revealed_at）は、届いた時点では付けない（v0.6）。画面が答えを読める形で出したとき（同じ話題で
        # 待っていた・話題を開いた）か、戻って予想するか「すぐ読む」で開いたときに、画面の側から付ける。v0.5 までは、
        # 予想の帯を通らない答え（命令・言い直し・確かめへの答え・図から・予想を出さない設定）に届いた時点で付けていたが、
        # 本人が別の話題にいるあいだに届くと時計が先に進み、読んでいない答えの確かめが出ていた
        st["grades"] = grades
        st["center"] = center
        st["block_errors"] = blocks["errors"]
        st["rules"] = 4   # v0.4 の決まりで読んだ答えの印（読み直しで、たとえを前の決まりに戻さない）
        if blocks.get("lookup"):
            st["lookup"] = blocks["lookup"]   # 先生役が「Web で調べるとよい」とした問い（画面が入口を出す）
        # 選んだ見せ方を往復ごとに残す（あとで「どの形の答えのあとに確かめが当たったか」を数えるため）
        st["shapes"] = [{"type": v["type"], "name": v["name"], "why": v.get("why", "")} for v in blocks["views"]]
        con.execute("UPDATE turn SET answer_md=?, status='done', done_at=?, stage_ms=? WHERE id=?",
                    (md, db.now(), db.jdump(st), turn_id))
        con.execute("UPDATE session SET updated_at=? WHERE id=?", (db.now(), sid))
    events.publish({"t": "done", "turn_id": turn_id, "session_id": sid, "center": center, "checks": len(checks)})
