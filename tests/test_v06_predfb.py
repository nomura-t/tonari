"""予想と答えの照らし合わせの規則の検査（v0.6）。答えの核を機械で抜き出すこと、返しの取り出し（抜き出した字が予想や答えに
無い項目は出さない）、走らせる時機（予想と答えがそろったとき・二重に走らせない・予想を外したら返しも外す）。
本物の claude は使わない。材料は作り物。"""
import asyncio
import json
import os
import tempfile

os.environ.setdefault("TONARI_DATA_DIR", tempfile.mkdtemp(prefix="tonari-test-"))
os.environ.setdefault("TONARI_RECORDER", "off")

from fastapi.testclient import TestClient  # noqa: E402

from server import app as appmod, db, pipeline, predfb  # noqa: E402

H = {"X-Tonari": "1"}
ANSWER = ("受付は、頼みを受け取って、倉庫から品物を出して返す役です。\n\n"
          "決め手は、『受付』が『倉庫』の中身を自分では持たないことです。品物があるかどうかは、倉庫に聞くまで分かりません。")
PRED = "頼みを受け取って、倉庫に聞いて渡すんだと思う。たぶん鍵も預かる"


def _raw(**kw):
    d = {"core": "out", "core_q": "", "key": "", "key_q": "", "diff": "", "diff_q": "", "open_q": ""}
    d.update(kw)
    return json.dumps(d, ensure_ascii=False)


def _done_turn(pred=None, status="done"):
    db.init()
    with db.tx() as con:
        sid = con.execute("INSERT INTO session(title, model, created_at, updated_at) VALUES(?,?,?,?)", ("t", "opus", 0, 0)).lastrowid
        tid = con.execute("INSERT INTO turn(session_id, seq, via, status, created_at, final_text, answer_md, stage_ms) VALUES(?,?,?,?,?,?,?,?)",
                          (sid, 1, "text", status, db.now(), "受付って何をする役？", ANSWER if status == "done" else None,
                           json.dumps({"predict": pred} if pred else {}))).lastrowid
    return sid, tid


def _stage(tid):
    with db.tx() as con:
        return json.loads(db.row(con, "SELECT stage_ms FROM turn WHERE id=?", (tid,))["stage_ms"] or "{}")


def _on(monkeypatch, result):
    """照らし合わせ役を作り物にして、走らせる口（spawn）を捕まえる。"""
    started = []
    monkeypatch.setattr(predfb, "ENABLED", True)
    monkeypatch.setattr(pipeline, "spawn", started.append)

    async def judge(said, pred, prose):
        if isinstance(result, Exception):
            raise result
        return predfb.parse(result, pred, prose)
    monkeypatch.setattr(predfb, "judge", judge)
    return started


# ── 答えの核を機械で抜き出す ──
def test_the_core_of_an_answer_is_taken_from_its_first_paragraph_and_the_decisive_sentence():
    c = predfb.core_of(ANSWER)
    assert c["lead"].startswith("受付は、頼みを受け取って") and c["show"] == "受付は、頼みを受け取って、倉庫から品物を出して返す役です。"
    assert c["key"] == "決め手は、『受付』が『倉庫』の中身を自分では持たないことです。"
    # 表・見出し・箇条書きで始まる答えでも、最初の文の段落を核にする。記号は外す
    md = "| 列 | 列 |\n|---|---|\n| a | b |\n\n## 見出し\n\n**キャッシュ**は、`手元`に置いた写しを返す仕組みです。くわしくは下です。\n\n- 箇条"
    assert predfb.core_of(md)["show"] == "キャッシュは、手元に置いた写しを返す仕組みです。くわしくは下です。"   # 最初の文が短いので、次の文まで
    # 最初の文が短いときは、次の文までを出す。決め手が最初の段落の中にあるときは、決め手を別に出さない
    one = "はい、できます。決め手は、鍵が2つあることです。\n\nそのほかの話。"
    assert predfb.core_of(one) == {"lead": "はい、できます。決め手は、鍵が2つあることです。", "show": "はい、できます。決め手は、鍵が2つあることです。", "key": ""}
    assert len(predfb.core_of("あ" * 300)["show"]) == predfb.SHOW_MAX and predfb.core_of("")["lead"] == ""
    assert "<答えの核>\n受付は、頼みを受け取って" in predfb.build_input("問い", PRED, ANSWER) and "<決め手>" in predfb.build_input("問い", PRED, ANSWER)


def test_the_core_keeps_plain_marks_and_drops_only_emphasis_and_source_tags():
    md = "同時に送れるのは **10~20件** で、`a_b` のような名前も使えます〔abc123｜見出し〕。次の文です。"
    assert predfb.core_of(md)["show"].startswith("同時に送れるのは 10~20件 で、a_b のような名前も使えます。")   # ~ と _ は字として残す
    assert predfb.core_of("・箇条だけの段落です\n\n本文の段落は、ここから始まる一文です。")["show"] == "本文の段落は、ここから始まる一文です。"
    # 照らし合わせ役に渡す核は、画面に出す核と同じ文（最初の段落の3文目から先は渡さない）
    long = "受付は、頼みを受け取って、倉庫から品物を出して返す役です。次に、番号札を渡します。最後に、帳簿へ書きます。\n\nあとの段落。"
    body = predfb.build_input("問い", PRED, long)
    core = body[body.index("<答えの核>"):body.index("</答えの核>")]
    assert "倉庫から品物を出して返す役です" in core and "帳簿へ書きます" not in core


def test_a_quote_that_any_sentence_would_contain_is_not_evidence():
    assert not predfb._backed("だと", "倉庫に聞くんだと思う") and not predfb._backed("だと思う", "倉庫に聞くんだと思う")   # かなだけの短い字
    assert predfb._backed("倉庫に聞く", "倉庫に聞くんだと思う") and predfb._backed("ふくらむからだ", "卵でふくらむからだと思う")
    assert predfb._backed("倉庫", "倉庫に聞くんだと思う")                                   # かな以外の字を含む言葉は、2字でも根拠になる
    assert not predfb._backed("はい", "はい、そうだと思う") and predfb._backed("はい", "はい", own=True)   # 予想の全部なら短くてもよい
    assert not predfb._backed("金庫", "倉庫に聞くんだと思う")                                # 元の文に無い字
    got = predfb.parse(_raw(core="in", core_q="だと", key="out"), "鍵を預かる役だと思う", ANSWER)
    assert got["core"] == "unknown"


# ── 返しの取り出し ──
def test_parse_shows_only_words_taken_from_the_prediction_or_the_answer():
    got = predfb.parse(_raw(core="in", core_q="頼みを受け取って", key="out", diff="予想では鍵も預かるとしていますが、答えでは品物を出して返す役だとしています。",
                            diff_q="倉庫から品物を出して返す役", open_q="たぶん鍵も預かる"), PRED, ANSWER)
    assert got == {"core": "in", "lead": "受付は、頼みを受け取って、倉庫から品物を出して返す役です。", "core_q": "頼みを受け取って",
                   "key": "out", "keyline": "決め手は、『受付』が『倉庫』の中身を自分では持たないことです。",
                   "diff": "予想では鍵も預かるとしていますが、答えでは品物を出して返す役だとしています。", "open_q": "たぶん鍵も預かる"}
    # 入っていなかったときは、答えの核（先生役の答えの最初の文）をそのまま返す。照らし合わせ役の文は使わない
    got = predfb.parse(_raw(core="out", key="out"), "鍵を預かる役だと思う", ANSWER)
    assert got["core"] == "out" and got["lead"].startswith("受付は、") and got["keyline"].startswith("決め手は、") and "core_q" not in got
    # 予想に無い字を根拠にした「入っていた」は、入っていたとも、いなかったとも出さない
    got = predfb.parse(_raw(core="in", core_q="品物を出して返す", key="out"), "鍵を預かる役だと思う", ANSWER)
    assert got["core"] == "unknown" and got["key"] == "out"
    assert predfb.parse(_raw(core="in", core_q="品物を出して返す"), "鍵を預かる役だと思う", ANSWER) is None    # ほかに出す物が無ければ、取れなかった扱い
    # 決め手が入っていたの根拠も、予想の字に無ければ出さない。食い違いは、答えの字の根拠が無ければ出さない
    got = predfb.parse(_raw(core="out", key="in", key_q="自分では持たない", diff="予想では逆です。", diff_q="どこにも無い字"), "鍵を預かる役だと思う", ANSWER)
    assert "key" not in got and "diff" not in got and got["core"] == "out"
    got = predfb.parse(_raw(core="out", key="in", key_q="自分では持たない"), "中身は自分では持たないんだと思う", ANSWER)
    assert got["key"] == "in" and got["key_q"] == "自分では持たない"
    assert "diff" not in predfb.parse(_raw(core="out", diff="あ" * 130, diff_q="倉庫に聞くまで分かりません"), PRED, ANSWER)   # 長すぎる文は出さない


def test_parse_reads_the_shapes_and_refuses_what_is_outside_the_rules():
    assert predfb.parse(_raw(core="none"), PRED, ANSWER) == {"core": "none"}
    assert predfb.parse("これは JSON ではありません", PRED, ANSWER) is None
    assert predfb.parse(_raw(core="すごい"), PRED, ANSWER) is None
    fenced = "```json\n" + _raw(core="in", core_q="頼みを 受け取って、") + "\n```"
    assert predfb.parse(fenced, PRED, ANSWER)["core"] == "in"                    # 囲み・空白・句読点の違いは数えない
    assert "key" not in predfb.parse(_raw(core="out", key="out"), PRED, "受付は、頼みを受け取る役です。そのあと倉庫に聞きます。品物を返します。")   # 決め手の文が無い答え


def test_eligible_needs_a_prediction_and_an_answer(monkeypatch):
    monkeypatch.setattr(predfb, "ENABLED", True)
    assert predfb.eligible(PRED, ANSWER)
    assert not predfb.eligible("", ANSWER) and not predfb.eligible("あ", ANSWER) and not predfb.eligible(PRED, "短い")
    assert not predfb.eligible(PRED, "| a | b |\n|---|---|\n| c | d |\n\n| e | f |\n|---|---|\n| g | h |" * 3)   # 核を抜き出せない答え
    monkeypatch.setattr(predfb, "ENABLED", False)
    assert not predfb.eligible(PRED, ANSWER)


# ── 走らせる時機 ──
def test_feedback_runs_once_when_prediction_and_answer_are_both_there(monkeypatch):
    started = _on(monkeypatch, _raw(core="in", core_q="頼みを受け取って", key="out"))
    sid, tid = _done_turn()
    with db.tx() as con:
        before = (db.row(con, "SELECT COUNT(*) AS n FROM mastery")["n"], db.row(con, "SELECT COUNT(*) AS n FROM rel_mastery")["n"])
    assert pipeline.save_predict(None, tid, PRED, "text")             # 届いている答えに予想を書き添えると、すぐ走る
    assert len(started) == 1 and _stage(tid)["predict_fb"]["state"] == "run"
    assert not pipeline.maybe_predict_fb(tid)                         # 走っているあいだは、もう1本走らせない
    asyncio.run(started[0])
    fb = _stage(tid)["predict_fb"]
    assert fb["state"] == "done" and fb["core"] == "in" and fb["core_q"] == "頼みを受け取って" and fb["key"] == "out"
    assert not pipeline.maybe_predict_fb(tid) and len(started) == 1   # 返してある往復には走らせない
    with db.tx() as con:
        assert db.row(con, "SELECT state FROM log WHERE kind='predict_fb' AND target=?", (tid,))["state"] == "in"
        after = (db.row(con, "SELECT COUNT(*) AS n FROM mastery")["n"], db.row(con, "SELECT COUNT(*) AS n FROM rel_mastery")["n"])
    assert after == before                                            # 理解の記録には入れない


def test_prediction_made_while_waiting_gets_feedback_when_the_answer_arrives(monkeypatch):
    started = _on(monkeypatch, _raw(core="out", key="out"))
    monkeypatch.setattr(predfb.POOL, "warm", lambda: None)
    sid, tid = _done_turn(status="thinking")
    assert pipeline.save_predict(None, tid, "鍵を預かる役だと思う", "text")
    assert started == [] and "predict_fb" not in _stage(tid)          # 答えがまだなら走らせない
    with db.tx() as con:
        con.execute("UPDATE turn SET status='done', answer_md=? WHERE id=?", (ANSWER, tid))
    assert pipeline.maybe_predict_fb(tid) and len(started) == 1       # 答えが届いたとき（ask_tutor が呼ぶ）
    asyncio.run(started[0])
    fb = _stage(tid)["predict_fb"]
    assert fb["state"] == "done" and fb["core"] == "out" and fb["lead"].startswith("受付は、") and fb["keyline"].startswith("決め手は、")


def test_no_feedback_without_a_prediction_and_removed_with_the_prediction(monkeypatch):
    started = _on(monkeypatch, _raw(core="none"))
    sid, tid = _done_turn()
    assert not pipeline.maybe_predict_fb(tid) and started == []       # 予想の無い往復
    pipeline.save_predict(None, tid, PRED, "text")
    asyncio.run(started[0])
    assert _stage(tid)["predict_fb"] == {"state": "done", "core": "none"}
    assert pipeline.clear_predict(tid) == PRED
    assert "predict_fb" not in _stage(tid) and "predict" not in _stage(tid)   # 予想を外したら、返しも外す


def test_failed_or_stale_feedback_can_be_run_again(monkeypatch):
    started = _on(monkeypatch, RuntimeError("取れない"))
    client = TestClient(appmod.app, base_url=f"http://127.0.0.1:{appmod.config.PORT}")
    sid, tid = _done_turn()
    pipeline.save_predict(None, tid, PRED, "text")
    asyncio.run(started[0])
    assert _stage(tid)["predict_fb"] == {"state": "fail"}
    assert not pipeline.maybe_predict_fb(tid)                         # 取れなかった分は、自動ではやり直さない
    assert client.post(f"/api/turns/{tid}/predict-fb", headers=H).status_code == 200 and len(started) == 2
    started[1].close()
    # 走り始めの印のまま止まった分（サーバーが途中で止まった）は、画面には取れなかったと出し、やり直せる
    with db.tx() as con:
        st = _stage(tid)
        st["predict_fb"] = {"state": "run", "at": db.now() - predfb.STALE_SEC - 1}
        con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (json.dumps(st), tid))
    view = next(t for t in client.get(f"/api/sessions/{sid}", headers=H).json()["turns"] if t["id"] == tid)
    assert view["predict_fb"] == {"state": "fail"} and view["predict"] == PRED
    assert pipeline.maybe_predict_fb(tid) and len(started) == 3
    started[2].close()
    monkeypatch.setattr(predfb, "ENABLED", False)
    assert client.post(f"/api/turns/{tid}/predict-fb", headers=H).status_code == 409


def test_feedback_for_a_replaced_prediction_is_not_written(monkeypatch):
    started = _on(monkeypatch, _raw(core="in", core_q="頼みを受け取って"))
    sid, tid = _done_turn()
    pipeline.save_predict(None, tid, PRED, "text")
    pipeline.save_predict(None, tid, "やっぱり、鍵を預かる役だと思う", "text")      # 返しが届く前に言い直した
    assert len(started) == 2
    asyncio.run(started[0])                                           # 古い予想への返しは書かない
    assert _stage(tid)["predict_fb"]["state"] == "run" and len(started) == 2
    asyncio.run(started[1])                                           # 言い直した予想への返しは書く（根拠の字が新しい予想に無いので、取れなかった扱い）
    assert _stage(tid)["predict_fb"] == {"state": "fail"}


def test_asking_back_from_the_feedback_is_counted(monkeypatch):
    monkeypatch.setattr(appmod.pipeline, "spawn", lambda coro: coro.close())
    client = TestClient(appmod.app, base_url=f"http://127.0.0.1:{appmod.config.PORT}")
    sid, tid = _done_turn(PRED)
    r = client.post(f"/api/sessions/{sid}/text", headers=H, json={"text": "私の予想のどこが違うのかを説明して", "via": "click", "pfb": True})
    assert r.status_code == 200 and _stage(r.json()["turn_id"]).get("pfb_ask") is True
    r = client.post(f"/api/sessions/{sid}/text", headers=H, json={"text": "ふつうの問い", "pfb": True})
    assert "pfb_ask" not in _stage(r.json()["turn_id"])               # 画面の「聞き返す」からでなければ数えない


def test_the_entry_is_offered_only_for_predictions_that_can_be_compared(monkeypatch):
    monkeypatch.setattr(predfb, "ENABLED", True)
    monkeypatch.setattr(pipeline, "spawn", lambda coro: coro.close())
    client = TestClient(appmod.app, base_url=f"http://127.0.0.1:{appmod.config.PORT}")
    sid, tid = _done_turn(PRED)
    sid2, tid2 = _done_turn("あ")                                     # 短すぎる予想
    view = {t["id"]: t for s in (sid, sid2) for t in client.get(f"/api/sessions/{s}", headers=H).json()["turns"]}
    assert view[tid]["predict_fb_can"] is True and view[tid2]["predict_fb_can"] is False
    r = client.post(f"/api/turns/{tid2}/predict-fb", headers=H)
    assert r.status_code == 409 and "照らし合わせられる予想と答えがありません" in r.json()["detail"]
    assert client.post(f"/api/turns/{tid}/predict-fb", headers=H).status_code == 200
    r = client.post(f"/api/turns/{tid}/predict-fb", headers=H)        # 走っているあいだ
    assert r.status_code == 409 and "いま照らし合わせています" in r.json()["detail"]


def test_state_tells_the_screen_whether_feedback_is_on(monkeypatch):
    client = TestClient(appmod.app, base_url=f"http://127.0.0.1:{appmod.config.PORT}")
    monkeypatch.setattr(predfb, "ENABLED", True)
    assert client.get("/api/state", headers=H).json()["predict_fb"] is True
    monkeypatch.setattr(predfb, "ENABLED", False)
    assert client.get("/api/state", headers=H).json()["predict_fb"] is False
