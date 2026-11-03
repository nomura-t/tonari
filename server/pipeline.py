"""1回の往復を進める: 録音 → 文字（Apple と Scribe）→ 直し（整形役）→ 先生役（opus）→ 札の取り込み。

段ごとに turn の status を書き換えて画面に知らせる。どの段で落ちても、そこまでの記録（生の文字起こし・直した文）は
残っているので、画面の「もう一度送る」でやり直せる。話題が違えば並んで進み、同じ話題の中は先生役の鍵で順番になる。
"""
import asyncio
import json
import re
import time
import traceback

from . import brain, config, corpus, db, events, fixer, judge, stt, tutor

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
    予想の往復は最初から superseded で作るので、往復の列にも話題の「最後」にも出ない。"""
    sid = t["session_id"]
    try:
        r = await stt.transcribe(config.AUDIO_DIR / t["audio"], keyterms(sid))
        if not ((r["apple"] or {}).get("text") or r["second"]):
            return
        f = await fixer.fix(sid, r["apple"], r["second"], prev_context(sid, t["seq"]), r["second_engine"] or "scribe")
        save_predict(turn_id, t["ref_turn"], f["text"])
    except Exception:
        traceback.print_exc()


def save_predict(turn_id: int, target: int | None, text: str) -> None:
    """読む前の予想（声）を、予想した答えの往復に書き添える。予想の往復そのものは列に出さない（superseded）。"""
    with db.tx() as con:
        r = db.row(con, "SELECT session_id, stage_ms, done_at FROM turn WHERE id=?", (target,)) if target else None
        if r:
            st = json.loads(r["stage_ms"] or "{}")
            st["predict"] = text[:400]
            st.setdefault("revealed_at", db.now())
            con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (db.jdump(st), target))
            con.execute("INSERT INTO log(kind, target, evidence, turn_id, at) VALUES('predict',?,?,?,?)",
                        (target, text[:400], turn_id, db.now()))
        con.execute("UPDATE turn SET status='superseded', final_text=? WHERE id=?", (text[:2000], turn_id))
    if r:
        events.publish({"t": "turn", "turn_id": target, "session_id": r["session_id"], "status": "done"})


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
            r = db.row(con, "SELECT answer_md FROM turn WHERE id=?", (t["ref_turn"],))
            views = tutor.parse_blocks(r["answer_md"] or "")["views"] if r else []
            ref = {"name": views[0]["name"], "type": views[0]["type"]} if views else {"name": None, "type": "text"}
    content = tutor.turn_content(sid, text, kind, via, unsure, s.get("detail") or "auto", ref, stage.get("hedges"),
                                 predict, check_id if kind == "answer" else None)
    t2 = time.time()
    md = ""
    for attempt in range(4):
        tu = brain.TUTORS.get(sid, tutor.system_prompt(), s["model"], s["claude_sid"])
        md = ""
        try:
            async for kind_, data in tu.ask(content):
                if kind_ == "text":
                    md += data
                    events.publish({"t": "delta", "turn_id": turn_id, "session_id": sid, "text": data})
                elif kind_ == "tool":
                    events.publish({"t": "tool", "turn_id": turn_id, "session_id": sid, "name": data})
                elif kind_ == "sid" and data != s["claude_sid"]:
                    with db.tx() as con:
                        con.execute("UPDATE session SET claude_sid=? WHERE id=?", (data, sid))
                    s["claude_sid"] = data
            break
        except brain.BrainError as e:
            msg = str(e)
            if attempt < 3 and (RATE_RE.search(msg) or "プロセスが止まりました" in msg):
                wait = 20 * (attempt + 1)
                events.publish({"t": "turn", "turn_id": turn_id, "session_id": sid, "status": "thinking",
                                "note": f"先生役が混んでいます。{wait}秒後にもう一度送ります"})
                if tu.resume_sid is None:
                    with db.tx() as con:
                        con.execute("UPDATE session SET claude_sid=NULL WHERE id=?", (sid,))
                    s["claude_sid"] = None
                await asyncio.sleep(wait)
                events.publish({"t": "reset", "turn_id": turn_id, "session_id": sid})
                continue
            raise
    stage["tutor"] = int((time.time() - t2) * 1000)
    stage["kind"] = kind
    grades = tutor.parse_blocks(md)["grade"]
    judged = None
    if grades:
        t3 = time.time()
        judged = await judge.second_opinion(sid, grades, text)
        stage["judge"] = int((time.time() - t3) * 1000)
    finish(turn_id, sid, md, text, stage, kind, judged, check_id if kind == "answer" else None)
    await brain.TUTORS.trim()


def finish(turn_id: int, sid: int, md: str, said: str, stage: dict, kind: str = "question",
           judged: list | None = None, check_id: int | None = None) -> None:
    blocks = tutor.parse_blocks(md)
    kept, dropped = tutor.filter_checks(blocks["check"], md)
    blocks["errors"] += dropped
    with db.tx() as con:
        center = tutor.merge_map(con, sid, turn_id, blocks["map"]) if blocks["map"] else None
        grades = tutor.apply_grades(con, sid, turn_id, blocks["grade"], said, kind, judged, check_id) if blocks["grade"] else []
        if kind == "answer" and check_id and not blocks["grade"]:
            con.execute("UPDATE checkq SET status='answered' WHERE id=? AND status='open'", (check_id,))
        checks = tutor.save_checks(con, sid, turn_id, kept) if kept else []
        old = db.row(con, "SELECT via, stage_ms FROM turn WHERE id=?", (turn_id,))
        st = json.loads(old["stage_ms"] or "{}") if old else {}
        st.update(stage)
        # 予想の帯を出さない答え（命令・確かめへの答え・図からの依頼・予想を止めている）は、届いた時点で開いたとみなす。
        # そうしないと、その答えの確かめの問いが戻ったときに出ない（return_check は開いた時刻から数える）
        if kind != "question" or (old and old["via"] == "click") or db.get_pref("predict", "1") == "0":
            st.setdefault("revealed_at", db.now())
        st["grades"] = grades
        st["center"] = center
        st["block_errors"] = blocks["errors"]
        # 選んだ見せ方を往復ごとに残す（あとで「どの形の答えのあとに確かめが当たったか」を数えるため）
        st["shapes"] = [{"type": v["type"], "name": v["name"], "why": v.get("why", "")} for v in blocks["views"]]
        con.execute("UPDATE turn SET answer_md=?, status='done', done_at=?, stage_ms=? WHERE id=?",
                    (md, db.now(), db.jdump(st), turn_id))
        con.execute("UPDATE session SET updated_at=? WHERE id=?", (db.now(), sid))
    events.publish({"t": "done", "turn_id": turn_id, "session_id": sid, "center": center, "checks": len(checks)})
