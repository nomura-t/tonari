"""手元のサーバー。127.0.0.1 だけで待ち受け、/api には独自の見出し X-Tonari を必須にする
（ほかのサイトのページから localhost を叩かれても、本人の Max プランの枠と学びの記録に触れさせないため）。"""
import asyncio
import difflib
import json
import os
import re
import signal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import brain, config, corpus, db, events, fixer, graph, health, judge, pipeline, stt, tutor

app = FastAPI(title="となり", docs_url=None, redoc_url=None, openapi_url=None)
WEB_DIR = config.APP_DIR / "web"
STATE_JA = {"known": "分かる", "shaky": "あやしい", "unknown": "分からない"}
# 設定の画面で変えられるキーの操作（web/app.js の KEY_ACTIONS と同じ）と、受け付ける形（e.code を + でつないだもの）
KEY_ACTIONS = ("new", "next", "open", "talk", "reveal", "cancel")
KEY_RE = re.compile(r"^(?:(?:Ctrl|Alt|Shift|Meta)\+){0,4}[A-Za-z0-9]{1,20}$")
TUTOR_MODELS = ("", "opus", "sonnet")


def key_prefs() -> dict:
    try:
        d = json.loads(db.get_pref("keys", "{}"))
    except ValueError:
        return {}
    return {k: v for k, v in d.items() if k in KEY_ACTIONS and isinstance(v, str) and KEY_RE.match(v)} if isinstance(d, dict) else {}


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.headers.get("host", "") not in config.ALLOWED_HOSTS:
        return JSONResponse({"error": "この住所からは使えません"}, status_code=403)
    if request.url.path.startswith("/api") and request.headers.get("x-tonari") != "1":
        return JSONResponse({"error": "見出しが足りません"}, status_code=403)
    return await call_next(request)


@app.on_event("startup")
async def startup():
    db.init()
    info = await asyncio.to_thread(corpus.refresh)
    print("棚の写し:", info, flush=True)
    fixer.POOL.warm()

    async def trimmer():
        while True:
            await asyncio.sleep(120)
            await brain.TUTORS.trim()
    pipeline.spawn(trimmer())
    if os.environ.get("TONARI_EXIT_WHEN_CLOSED") == "1":
        pipeline.spawn(exit_when_closed())


async def exit_when_closed():
    """launch.py から起動したときだけ。画面が閉じられて15秒たったら（開き直しの間は待つ）、または2分たっても
    画面が一度もつながらなければ、先生役を閉じてサーバーを止める。窓を閉じてもブラウザが裏に残る場合でも止まる。"""
    seen, idle = False, 0
    while True:
        await asyncio.sleep(1)
        if events.count():
            seen, idle = True, 0
            continue
        idle += 1
        if (seen and idle >= 15) or (not seen and idle >= 120):
            print("画面が閉じられたのでサーバーを止めます", flush=True)
            await shutdown()
            os.kill(os.getpid(), signal.SIGTERM)
            return


@app.on_event("shutdown")
async def shutdown():
    events.close_all()
    await brain.TUTORS.close_all()
    await fixer.POOL.close()
    await judge.POOL.close()


@app.post("/api/shutdown")
async def api_shutdown():
    await shutdown()
    asyncio.get_running_loop().call_later(0.2, os.kill, os.getpid(), signal.SIGTERM)
    return {"ok": True}


def ndjson(gen):
    async def body():
        async for ev in gen:
            yield (json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8")
    return StreamingResponse(body(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


@app.get("/api/events")
async def api_events():
    return ndjson(events.subscribe())


# ── 話題 ──────────────────────────────────────────────
def session_rows(con) -> list[dict]:
    rows = db.rows(con, "SELECT * FROM session WHERE archived=0 ORDER BY id")
    for s in rows:
        last = db.row(con, "SELECT id, seq, status, title, final_text, created_at, done_at, error FROM turn "
                           "WHERE session_id=? AND status!='superseded' ORDER BY seq DESC LIMIT 1", (s["id"],))
        s["last"] = last
        s["unread"] = db.row(con, "SELECT COUNT(*) AS n FROM turn WHERE session_id=? AND status='done' AND done_at>?",
                              (s["id"], s["read_at"]))["n"]
        s["busy"] = db.row(con, "SELECT COUNT(*) AS n FROM turn WHERE session_id=? AND status IN "
                                "('recorded','transcribing','fixing','thinking')", (s["id"],))["n"]
        s["concepts"] = db.row(con, "SELECT COUNT(*) AS n FROM session_concept WHERE session_id=?", (s["id"],))["n"]
    return rows


@app.get("/api/state")
async def api_state():
    with db.tx() as con:
        sessions = session_rows(con)
        usage = db.row(con, "SELECT COALESCE(SUM(sec),0) AS sec, COUNT(*) AS n FROM stt_usage WHERE engine='scribe' "
                            "AND at > strftime('%s','now','start of month')")
        counts = db.row(con, "SELECT (SELECT COUNT(*) FROM concept) AS concepts, (SELECT COUNT(*) FROM relation) AS relations, "
                             "(SELECT COUNT(*) FROM mastery WHERE state='known') AS known")
    ok, why = await stt.scribe_allowed()
    lok, lwhy = stt.local_allowed()
    return {"sessions": sessions, "prefs": {"scribe": db.get_pref("scribe", config.SCRIBE_MODE),
                                            "auto_next": db.get_pref("auto_next", "1"),
                                            "predict": db.get_pref("predict", "1"),
                                            "keys": key_prefs(), "tutor_model": db.get_pref("tutor_model", "")},
            "tutor_default": config.TUTOR_MODEL,
            "scribe": {"active": ok, "why": why, "month_sec": usage["sec"], "month_n": usage["n"]},
            "local": {"active": lok, "why": lwhy, "apple": stt.apple_available()},
            "counts": counts, "model": config.TUTOR_MODEL}


@app.post("/api/sessions")
async def api_new_session(req: Request):
    body = await req.json() if (await req.body()) else {}
    t = db.now()
    with db.tx() as con:
        cur = con.execute("INSERT INTO session(title, model, created_at, updated_at, read_at) VALUES(?,?,?,?,?)",
                          ((body.get("title") or "新しい話題")[:24],
                           body.get("model") or db.get_pref("tutor_model", "") or config.TUTOR_MODEL, t, t, t))
        sid = cur.lastrowid
    events.publish({"t": "session", "session_id": sid})
    return {"id": sid}


@app.patch("/api/sessions/{sid}")
async def api_patch_session(sid: int, req: Request):
    body = await req.json()
    with db.tx() as con:
        if "title" in body:
            con.execute("UPDATE session SET title=? WHERE id=?", (str(body["title"])[:24] or "新しい話題", sid))
        if "archived" in body:
            con.execute("UPDATE session SET archived=? WHERE id=?", (1 if body["archived"] else 0, sid))
        if body.get("detail") in ("auto", "short", "long"):
            con.execute("UPDATE session SET detail=? WHERE id=?", (body["detail"], sid))
    if body.get("archived"):
        t = brain.TUTORS.tutors.pop(sid, None)
        if t:
            await t.close()
    events.publish({"t": "session", "session_id": sid})
    return {"ok": True}


def turn_view(t: dict) -> dict:
    v = {k: t[k] for k in ("id", "seq", "via", "status", "error", "title", "final_text", "fixed_text", "apple_text",
                           "scribe_text", "haas_text", "audio_sec", "created_at", "done_at")}
    v["edits"] = json.loads(t["edits_json"] or "[]")
    v["unsure"] = json.loads(t["unsure_json"] or "[]")
    st = json.loads(t["stage_ms"] or "{}")
    v["stage"] = {k: st.get(k) for k in ("stt", "fix", "tutor", "scribe_mode", "local_mode", "second", "fix_fallback", "stt_errors", "block_errors")}
    v["grades"] = st.get("grades") or []
    v["center"] = st.get("center")
    v["ref_turn"] = t.get("ref_turn")
    v["shapes"] = st.get("shapes")
    v["revealed_at"] = st.get("revealed_at")
    v["kind"] = st.get("kind")
    v["predict"] = st.get("predict")
    if t["answer_md"]:
        b = tutor.parse_blocks(t["answer_md"])
        v["answer"] = b["text"]          # 図の置き場所は [[view:N]]
        v["views"] = b["views"]
        v["map"] = b["map"]
        v["quotes"] = corpus.check_quotes(t["answer_md"])
        v["cards"] = corpus.cards(t["answer_md"])
    return v


@app.get("/api/sessions/{sid}")
async def api_session(sid: int):
    with db.tx() as con:
        s = db.row(con, "SELECT * FROM session WHERE id=?", (sid,))
        if not s:
            raise HTTPException(404, "話題がありません")
        turns = db.rows(con, "SELECT * FROM turn WHERE session_id=? AND status!='superseded' ORDER BY seq", (sid,))
        checks = db.rows(con, "SELECT * FROM checkq WHERE session_id=? ORDER BY id", (sid,))
    views = [turn_view(t) for t in turns]
    by_turn: dict[int, list] = {}
    for c in checks:
        by_turn.setdefault(c["turn_id"], []).append(c)
    for v in views:
        v["checks"] = by_turn.get(v["id"], [])
    return {"session": s, "turns": views, "return_check": return_check(views, checks)}


def return_check(views: list[dict], checks: list[dict]) -> dict | None:
    """戻ったときに出す確かめの問い。型のある（v0.3 以降の）開いた問いのうち古いものを1つ。

    直近に済んだ3問がすべて「飛ばした」なら、この話題では出さない（煩わしさの見張り。研究 d の 5-13）。"""
    typed = [c for c in checks if c.get("qtype")]
    done = [c for c in typed if c["status"] != "open"]
    if len(done) >= 3 and all(c["status"] == "skipped" for c in done[-3:]):
        return None
    revealed = {v["id"]: v.get("revealed_at") for v in views}
    now = db.now()
    for c in typed:
        r = revealed.get(c["turn_id"])
        if c["status"] == "open" and r and now - r >= config.RETURN_AFTER_SEC:
            return {"id": c["id"], "q": c["q"], "qtype": c["qtype"], "turn_id": c["turn_id"]}
    return None


@app.post("/api/turns/{tid}/reveal")
async def api_reveal(tid: int):
    """読む前の予想の帯を閉じて答えを開いた（予想を言った・すぐ読む）。"""
    with db.tx() as con:
        t = db.row(con, "SELECT session_id, stage_ms FROM turn WHERE id=?", (tid,))
        if not t:
            raise HTTPException(404, "往復がありません")
        st = json.loads(t["stage_ms"] or "{}")
        st.setdefault("revealed_at", db.now())
        con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (db.jdump(st), tid))
    events.publish({"t": "turn", "turn_id": tid, "session_id": t["session_id"], "status": "done"})
    return {"ok": True}


@app.post("/api/sessions/{sid}/read")
async def api_read(sid: int):
    with db.tx() as con:
        con.execute("UPDATE session SET read_at=? WHERE id=?", (db.now(), sid))
    events.publish({"t": "read", "session_id": sid})
    return {"ok": True}


def new_turn(con, sid: int, via: str, **kw) -> int:
    seq = db.row(con, "SELECT COALESCE(MAX(seq),0)+1 AS n FROM turn WHERE session_id=?", (sid,))["n"]
    cols = {"session_id": sid, "seq": seq, "via": via, "status": "recorded", "created_at": db.now(), **kw}
    cur = con.execute(f"INSERT INTO turn({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})", tuple(cols.values()))
    return cur.lastrowid


@app.post("/api/sessions/{sid}/voice")
async def api_voice(sid: int, audio: UploadFile = File(...), kind: str | None = Form(None),
                    ref_turn: int | None = Form(None), check_id: int | None = Form(None)):
    config.ensure_dirs()
    name = stt.new_audio_name() + ".webm"
    data = await audio.read()
    if len(data) < 800:
        raise HTTPException(400, "録音が短すぎます")
    (config.AUDIO_DIR / name).write_bytes(data)
    extra = {}
    with db.tx() as con:
        if kind == "predict" and ref_turn and db.row(con, "SELECT id FROM turn WHERE id=? AND session_id=?", (ref_turn, sid)):
            extra["ref_turn"] = ref_turn
        if kind == "answer" and check_id and db.row(con, "SELECT id FROM checkq WHERE id=? AND session_id=?", (check_id, sid)):
            extra["stage_ms"] = db.jdump({"check_id": check_id})
        if extra.get("ref_turn"):
            extra["status"] = "superseded"   # 予想は往復の列に出さない（pipeline.run_predict）
        tid = new_turn(con, sid, "voice", audio=name, **extra)
    if kind != "predict":
        events.publish({"t": "turn", "turn_id": tid, "session_id": sid, "status": "recorded", "new": True})
    hint = "predict" if kind == "predict" and extra.get("ref_turn") else (kind if kind in fixer.KINDS else None)
    pipeline.spawn(pipeline.run_voice(tid, hint))
    return {"turn_id": tid}


@app.post("/api/sessions/{sid}/text")
async def api_text(sid: int, req: Request):
    body = await req.json()
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "文が空です")
    via = body.get("via") if body.get("via") in ("text", "click") else "text"
    kind = body.get("kind") if body.get("kind") in fixer.KINDS else "question"
    ref = body.get("ref_turn")
    with db.tx() as con:
        extra = {"ref_turn": int(ref)} if isinstance(ref, int) and db.row(con, "SELECT id FROM turn WHERE id=? AND session_id=?", (ref, sid)) else {}
        cid = body.get("check_id")
        if kind == "answer" and isinstance(cid, int) and db.row(con, "SELECT id FROM checkq WHERE id=? AND session_id=?", (cid, sid)):
            extra["stage_ms"] = db.jdump({"check_id": cid})
        tid = new_turn(con, sid, via, final_text=text[:2000], title=(body.get("title") or text)[:16], **extra)
    events.publish({"t": "turn", "turn_id": tid, "session_id": sid, "status": "recorded", "new": True})
    pipeline.spawn(pipeline.run_text(tid, kind))
    return {"turn_id": tid}


def mishear_pairs(old: str, new: str, via: str) -> list[tuple[str, str]]:
    """声の往復で本人が書き換えた字（置き換えの区間・両方20字以内）を「聞き違い」として拾う。"""
    if via != "voice":
        return []
    out = []
    sm = difflib.SequenceMatcher(None, old, new)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace":
            a, b = old[i1:i2].strip(), new[j1:j2].strip()
            if a and b and a != b and len(a) <= 20 and len(b) <= 20:
                out.append((a, b))
    return out[:5]


@app.post("/api/turns/{tid}/resend")
async def api_resend(tid: int, req: Request):
    """本人が直した文（または整形役の直しを戻した文）で聞き直す。元の往復は畳み、戻した直しは聞き違いの台帳に入れない。
    本人が書き換えた字は「聞き違い」として台帳に足し、次から整形役と Scribe の用語に渡す。"""
    body = await req.json()
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "文が空です")
    with db.tx() as con:
        t = db.row(con, "SELECT * FROM turn WHERE id=?", (tid,))
        if not t:
            raise HTTPException(404, "往復がありません")
        for heard, meant in mishear_pairs(t["final_text"] or "", text, t["via"]):
                con.execute("""INSERT INTO mishear(heard, meant, n, updated_at) VALUES(?,?,1,?)
                               ON CONFLICT(heard, meant) DO UPDATE SET n=n+1, updated_at=excluded.updated_at""",
                            (heard, meant, db.now()))
                con.execute("INSERT INTO log(kind, evidence, turn_id, at) VALUES('mishear',?,?,?)",
                            (f"{heard}→{meant}", tid, db.now()))
        con.execute("UPDATE turn SET status='superseded' WHERE id=?", (tid,))
        nid = new_turn(con, t["session_id"], t["via"], audio=t["audio"], audio_sec=t["audio_sec"],
                       apple_text=t["apple_text"], apple_json=t["apple_json"], scribe_text=t["scribe_text"],
                       haas_text=t["haas_text"], fixed_text=t["fixed_text"], edits_json=t["edits_json"], final_text=text[:2000],
                       title=t["title"] or text[:16])
    events.publish({"t": "turn", "turn_id": nid, "session_id": t["session_id"], "status": "recorded", "new": True})
    pipeline.spawn(pipeline.run_text(nid, body.get("kind") or "question"))
    return {"turn_id": nid}


# ── 地図と理解度 ──────────────────────────────────────────
@app.get("/api/concepts")
async def api_concepts(session_id: int | None = None):
    return {"concepts": graph.concepts(session_id)}


@app.get("/api/concepts/{cid}/ego")
async def api_ego(cid: int):
    e = graph.ego(cid)
    if not e:
        raise HTTPException(404, "概念がありません")
    return e


@app.get("/api/concepts/find")
async def api_find(label: str):
    with db.tx() as con:
        r = db.row(con, "SELECT id FROM concept WHERE fold=?", (db.fold(label),))
    if not r:
        raise HTTPException(404, "概念がありません")
    return {"id": r["id"]}


@app.post("/api/mastery")
async def api_mastery(req: Request):
    body = await req.json()
    state = body.get("state")
    with db.tx() as con:
        if body.get("concept_id"):
            if state in STATE_JA:
                tutor.set_mastery(con, int(body["concept_id"]), state, "self")
            else:
                con.execute("DELETE FROM mastery WHERE concept_id=?", (int(body["concept_id"]),))
        if body.get("relation_id") and state in STATE_JA:
            tutor.set_rel_mastery(con, int(body["relation_id"]), state, "self", None, None)
        if body.get("check_id") and state == "skipped":   # 戻ったときの問いを飛ばした（理解の記録には入れない）
            con.execute("UPDATE checkq SET status='skipped' WHERE id=? AND status='open'", (int(body["check_id"]),))
        if body.get("check_id") and state in STATE_JA:
            c = db.row(con, "SELECT * FROM checkq WHERE id=?", (int(body["check_id"]),))
            if c:
                con.execute("UPDATE checkq SET status=? WHERE id=?", (state, c["id"]))
                rid = tutor.find_relation(con, c["concept"] or "", c["target"] or "", c["rel"] or "")
                if rid:
                    tutor.set_rel_mastery(con, rid, state, "self", None, c["turn_id"])
    events.publish({"t": "mastery"})
    return {"ok": True}


@app.post("/api/prefs")
async def api_prefs(req: Request):
    body = await req.json()
    if body.get("scribe") in ("always", "auto", "off"):
        db.set_pref("scribe", body["scribe"])
    if body.get("auto_next") in ("0", "1"):
        db.set_pref("auto_next", body["auto_next"])
    if body.get("predict") in ("0", "1"):
        db.set_pref("predict", body["predict"])
    if body.get("tutor_model") in TUTOR_MODELS:
        db.set_pref("tutor_model", body["tutor_model"])
    if isinstance(body.get("keys"), dict):
        keys = {k: v for k, v in body["keys"].items() if k in KEY_ACTIONS and isinstance(v, str) and KEY_RE.match(v)}
        if len(set(keys.values())) != len(keys):
            raise HTTPException(400, "同じキーが2つの操作に割り当てられています")
        db.set_pref("keys", json.dumps(keys))
    return {"ok": True}


@app.get("/api/health")
async def api_health():
    return await asyncio.to_thread(health.check)


@app.post("/api/settings/eleven-key")
async def api_eleven_key(req: Request):
    """設定の画面から Scribe の鍵を入れる・消す。記録の置き場の .env に書き、中身は返さない。"""
    key = str((await req.json()).get("key") or "").strip()
    if key and not re.fullmatch(r"[A-Za-z0-9_\-]{10,200}", key):
        raise HTTPException(400, "鍵の形が違います（英数字と - _ だけ）")
    config.write_env("ELEVENLABS_API_KEY", key or None)
    stt._sub_cache.update(at=0.0, remaining=None)
    _, src = stt.eleven_key_source()
    return {"present": src != "none", "source": src}


@app.get("/api/seen-views")
async def api_seen_views():
    return {"seen": json.loads(db.get_pref("seen_views", "[]"))}


@app.post("/api/seen-views")
async def api_seen_views_add(req: Request):
    body = await req.json()
    seen = set(json.loads(db.get_pref("seen_views", "[]")))
    seen.update(str(x)[:12] for x in (body.get("types") or []))
    db.set_pref("seen_views", json.dumps(sorted(seen)))
    return {"seen": sorted(seen)}


@app.post("/api/corpus/refresh")
async def api_corpus_refresh():
    info = await asyncio.to_thread(corpus.refresh)
    return info


@app.get("/api/shelf/{iid}")
async def api_shelf_url(iid: str):
    with corpus._lock:
        it = corpus._state["rows"].get(iid)
    if not it:
        raise HTTPException(404, "棚にありません")
    return {"url": it.get("url") or f"https://claude.ai/artifact/{iid}", "title": it.get("title")}


# ── 画面 ──────────────────────────────────────────────
@app.get("/")
async def index():
    """部品（css・js）の住所に更新時刻を付けて渡す（アプリの WebKit が古い部品を使い続けないように）。"""
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.css", "md.js", "map.js", "views.js", "app.js"):
        v = int((WEB_DIR / name).stat().st_mtime)
        html = html.replace(f"/web/{name}\"", f"/web/{name}?v={v}\"")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
