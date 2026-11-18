"""v0.6 の規則の検査（主な経路の壁を取る: 予想は待つあいだに誘う・答えは畳まない・帯の欄から文字でも送れる・
取り違えの戻し・片づけた話題）。本物の claude も Web も使わない。材料はどれも作り物。"""
import json
import os
import tempfile

os.environ.setdefault("TONARI_DATA_DIR", tempfile.mkdtemp(prefix="tonari-test-"))
os.environ.setdefault("TONARI_RECORDER", "off")

from fastapi.testclient import TestClient  # noqa: E402

from server import app as appmod, db, flow, graph, pipeline, readings, tutor  # noqa: E402

H = {"X-Tonari": "1"}


def _client(monkeypatch):
    monkeypatch.setattr(appmod.pipeline, "spawn", lambda coro: coro.close())   # 先生役は呼ばない
    return TestClient(appmod.app, base_url=f"http://127.0.0.1:{appmod.config.PORT}")


def _stage(tid):
    with db.tx() as con:
        return json.loads(db.row(con, "SELECT stage_ms FROM turn WHERE id=?", (tid,))["stage_ms"] or "{}")


def _turn(con, sid, seq, text="問い", status="done", stage=None, via="text"):
    cur = con.execute("INSERT INTO turn(session_id, seq, via, status, created_at, final_text, stage_ms) VALUES(?,?,?,?,?,?,?)",
                      (sid, seq, via, status, db.now(), text, json.dumps(stage) if stage is not None else None))
    return cur.lastrowid


def _session(con, title="t"):
    return con.execute("INSERT INTO session(title, model, created_at, updated_at) VALUES(?,?,?,?)", (title, "opus", 0, 0)).lastrowid


# ── 予想の出し方 ──
def test_predict_mode_defaults_to_both_and_reads_old_values():
    db.init()
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k='predict'")
    assert flow.predict_mode() == "both"            # 何も変えていなければ、待つあいだは帯で誘い、戻ったときは畳んで誘う
    for stored, mode in (("1", "both"), ("fold", "both"), ("0", "off"), ("wait", "wait"), ("off", "off"), ("なにか", "both")):
        db.set_pref("predict", stored)
        assert flow.predict_mode() == mode, stored
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k='predict'")


def test_offer_only_for_question_shaped_utterances():
    yes = ["キャッシュって何？", "なぜ再送するの", "TLS と SSH はどう違う", "これは正しいですか", "いつ切れるのかな",
           "DNS の違いを教えて", "どっちが速い", "合ってましたっけ", "キャッシュとは", "TTL とは何のこと", "どの層で動くの",
           "どこに保存されるの", "誰が署名するの", "いくつまで増やせるの", "これは何か", "なにが違うの"]
    no = ["キャッシュについて教えて", "知識の整理をしたい", "図にして", "まとめてください", "どうも", "いつもありがとう",
          "間違いを直して", "",
          # 字の並びの偶然（などの・ほどの・ことは・そんなに・勘違い・ところどころ）と、問いでない言い方（何か・誰も・いくつか）
          "TCPなどの仕組みを整理して", "先ほどの図を短くして", "そのことは分かった。図にして", "そんなに長くなくていいのでまとめて",
          "勘違いしていた所を直して", "ところどころ難しいので易しくして", "これほどの量は要らないので短く",
          "何か例を足して", "誰でも分かるように書き直して", "いくつか例を挙げて", "どれも大事なのでまとめて", "なぜなら速いからと書いて"]
    for t in yes:
        assert flow.looks_like_question(t), t
    for t in no:
        assert not flow.looks_like_question(t), t


def test_offer_is_skipped_once_after_an_ignored_offer():
    db.init()
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k IN ('predict', 'predict_skip')")
        sid = _session(con)
        P = lambda text="なぜ？", kind="question", via="text", ref=False: flow.predict_offer(con, text, kind, via, ref)  # noqa: E731
        assert P()                                                     # 問いの形の発言には誘う
        # 誘わない発言: 頼みの形・確かめへの答え・言い直し・命令・図からの依頼・見せ直し・Web で調べる
        assert not P("整理したい") and not P(kind="answer") and not P(kind="confirm") and not P(kind="command")
        assert not P(via="click") and not P(via="research") and not P(ref=True)
        # 誘った往復を、予想なしで開いた → 次の1回は誘わない（話題を問わない）→ その次はまた誘う
        t1 = _turn(con, sid, 1, stage={"offer": "predict"})
        flow.note_reveal(con, t1, {"offer": "predict"})
        assert not P("整理したい")                                      # 誘わない発言は、印を使わない
        assert not P() and P()
        # 予想してから開いた・誘っていない往復を開いた → 印は付かない
        flow.note_reveal(con, t1, {"offer": "predict", "predict": "たぶん A"})
        flow.note_reveal(con, t1, {})
        assert P()
        # 声の予想は文字になる前に答えが開くので、その往復を指す予想の録音があれば、乗ったとみなす
        t2 = _turn(con, sid, 2, stage={"offer": "predict"})
        con.execute("INSERT INTO turn(session_id, seq, via, status, created_at, audio, ref_turn) VALUES(?,?,?,?,?,?,?)",
                    (sid, 3, "voice", "superseded", 0, "x.webm", t2))
        flow.note_reveal(con, t2, {"offer": "predict"})
        assert P()
        # 予想したら印は消える
        flow.note_reveal(con, t1, {"offer": "predict"})
        flow.note_predict(con)
        assert P()
        # 出さない設定では誘わない。待つあいだだけの設定では誘う（畳むかどうかは画面が決める）
        con.execute("INSERT INTO pref(k, v) VALUES('predict', 'off')")
        assert not P()
        con.execute("UPDATE pref SET v='wait' WHERE k='predict'")
        assert P()
        con.execute("DELETE FROM pref WHERE k IN ('predict', 'predict_skip')")


def test_revealing_an_offered_answer_without_a_prediction_skips_the_next_offer(monkeypatch):
    c = _client(monkeypatch)
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k IN ('predict', 'predict_skip')")
        sid = _session(con)
        a = _turn(con, sid, 1, status="done", stage={"offer": "predict"})
        b = _turn(con, sid, 2, status="done", stage={"offer": "predict", "predict": "たぶん"})
        p = _turn(con, sid, 3, status="thinking", stage={"offer": "predict"})
    skip = lambda: db.get_pref("predict_skip", "0")  # noqa: E731
    c.post(f"/api/turns/{b}/reveal", headers=H)
    assert skip() == "0"                                               # 予想した往復を開いても、印は付かない
    c.post(f"/api/turns/{p}/reveal", headers=H)
    assert "revealed_at" not in _stage(p) and skip() == "0"            # 答えがまだ届いていない往復は、開いた扱いにしない
    c.post(f"/api/sessions/{sid}/reveal", headers=H, json={"turn_ids": [a]})
    assert _stage(a)["revealed_at"] > 0 and skip() == "1"              # 誘ったのに予想なしで開いた
    c.post("/api/prefs", headers=H, json={"predict": "both"})
    assert skip() == "0"                                               # 出し方を選び直すと、印は消える
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k IN ('predict', 'predict_skip')")


# ── 文字の予想と、取り違えの戻し ──
def test_typed_prediction_is_attached_without_asking_the_tutor(monkeypatch):
    c = _client(monkeypatch)
    sid = c.post("/api/sessions", headers=H, json={}).json()["id"]
    tid = c.post(f"/api/sessions/{sid}/text", headers=H, json={"text": "なぜ再送するの？"}).json()["turn_id"]
    n = len(c.get(f"/api/sessions/{sid}", headers=H).json()["turns"])
    assert c.post(f"/api/sessions/{sid}/predict", headers=H, json={"turn_id": tid, "text": "届かなかったから"}).status_code == 200
    d = c.get(f"/api/sessions/{sid}", headers=H).json()
    assert len(d["turns"]) == n                                        # 予想は往復を増やさない（先生役に送らない）
    t = d["turns"][-1]
    assert t["predict"] == "届かなかったから" and t["predict_via"] == "text"
    assert not t.get("revealed_at")                                    # 答えがまだ届いていない往復に、開いた時刻を付けない
    with db.tx() as con:
        assert db.row(con, "SELECT by FROM log WHERE kind='predict' AND target=?", (tid,))["by"] == "text"
    # ほかの話題の往復・空の文は断る
    other = c.post("/api/sessions", headers=H, json={}).json()["id"]
    assert c.post(f"/api/sessions/{other}/predict", headers=H, json={"turn_id": tid, "text": "x"}).status_code == 404
    assert c.post(f"/api/sessions/{sid}/predict", headers=H, json={"turn_id": tid, "text": " "}).status_code == 400


def test_prediction_on_an_arrived_answer_counts_as_opening_it():
    db.init()
    with db.tx() as con:
        sid = _session(con)
        done = _turn(con, sid, 1, status="done", stage={})
        wait = _turn(con, sid, 2, status="thinking", stage={})
    assert pipeline.save_predict(None, done, "こうだと思う", "text") and pipeline.save_predict(None, wait, "たぶん", "text")
    assert _stage(done)["revealed_at"] > 0 and "revealed_at" not in _stage(wait)
    assert not pipeline.save_predict(None, 999999, "x", "text")


def test_unpredict_removes_the_prediction_and_can_resend_it_as_a_question(monkeypatch):
    c = _client(monkeypatch)
    sid = c.post("/api/sessions", headers=H, json={}).json()["id"]
    tid = c.post(f"/api/sessions/{sid}/text", headers=H, json={"text": "なぜ再送するの？"}).json()["turn_id"]
    c.post(f"/api/sessions/{sid}/predict", headers=H, json={"turn_id": tid, "text": "再送の間隔はどう決まる？"})
    r = c.post(f"/api/turns/{tid}/unpredict", headers=H, json={"resend": True}).json()
    d = c.get(f"/api/sessions/{sid}", headers=H).json()
    assert d["turns"][0]["predict"] is None and "predict" not in _stage(tid)
    assert d["turns"][-1]["id"] == r["turn_id"] and d["turns"][-1]["final_text"] == "再送の間隔はどう決まる？"
    assert c.post(f"/api/turns/{tid}/unpredict", headers=H, json={}).status_code == 404      # もう予想が無い
    with db.tx() as con:
        assert db.row(con, "SELECT evidence FROM log WHERE kind='unpredict' AND target=?", (tid,))


# ── 開いた時刻は、画面が答えを出したときに付ける ──
def test_reveal_marks_only_arrived_answers_and_only_once(monkeypatch):
    c = _client(monkeypatch)
    db.init()
    with db.tx() as con:
        sid = _session(con)
        a = _turn(con, sid, 1, status="done", stage={})
        b = _turn(con, sid, 2, status="done", stage={"revealed_at": 5.0})
        p = _turn(con, sid, 3, status="thinking", stage={})
    r = c.post(f"/api/sessions/{sid}/reveal", headers=H, json={"turn_ids": [a, b, p]}).json()
    assert r["revealed"] == [a]                                        # 届いた答えで、まだ時刻の無いものだけ
    assert _stage(a)["revealed_at"] > 5 and _stage(b)["revealed_at"] == 5.0 and "revealed_at" not in _stage(p)
    assert c.post(f"/api/sessions/{sid}/reveal", headers=H, json={}).json()["revealed"] == []


def test_no_answer_is_marked_open_on_arrival(monkeypatch):
    # 開いた時刻は、届いた時点では付けない（問い・命令・言い直し・確かめへの答え・図からの依頼・予想を出さない設定の
    # どれでも）。本人が別の話題にいるあいだに届いた答えの時計が先に進むと、読んでいない答えの確かめが出てしまう
    db.init()
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k='predict'")
        sid = _session(con)
        ids = {k: _turn(con, sid, i, status="thinking", via="click" if k == "click" else "text")
               for i, k in enumerate(("question", "command", "confirm", "answer", "click", "off"), 1)}
    for k in ("question", "command", "confirm", "answer"):
        pipeline.finish(ids[k], sid, "答えです。", "発言", {}, k)
    pipeline.finish(ids["click"], sid, "答えです。", "発言", {}, "question")
    db.set_pref("predict", "off")
    pipeline.finish(ids["off"], sid, "答えです。", "発言", {}, "question")
    assert all("revealed_at" not in _stage(i) for i in ids.values())
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k='predict'")
    monkeypatch.setattr(pipeline, "spawn", lambda coro: coro.close())   # 調べ役は呼ばない
    assert "revealed_at" not in _stage(pipeline.start_research(sid, "調べる問いです"))   # Web で調べる往復も同じ


def test_kind_and_offer_are_written_before_the_answer_arrives(monkeypatch):
    # 待つあいだの帯は、答えが届く前に、往復の種類と誘いの印を読む
    import asyncio
    from server import brain
    db.init()
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k IN ('predict', 'predict_skip')")
        sid = _session(con)
        tid = _turn(con, sid, 1, text="なぜ再送するの？", status="recorded")
    seen = {}

    class Fake:
        alive = False
        resume_sid = None

        async def ask(self, content):
            seen.update(_stage(tid))            # 先生役が答え始める時点の記録
            yield ("sid", "conv")
            yield ("text", "答えです。")

    monkeypatch.setattr(brain.TUTORS, "get", lambda *a: Fake())
    asyncio.run(pipeline.ask_tutor(tid, "なぜ再送するの？", "question", "text", [], {}))
    assert seen.get("kind") == "question" and seen.get("offer") == "predict" and seen["budget"]["chars"] == 250
    st = _stage(tid)
    assert st["offer"] == "predict" and st["kind"] == "question" and "revealed_at" not in st


def test_voice_prediction_needs_a_turn_of_the_same_topic(monkeypatch):
    c = _client(monkeypatch)
    a = c.post("/api/sessions", headers=H, json={}).json()["id"]
    b = c.post("/api/sessions", headers=H, json={}).json()["id"]
    ta = c.post(f"/api/sessions/{a}/text", headers=H, json={"text": "なぜ再送するの？"}).json()["turn_id"]
    wav = {"audio": ("voice.webm", b"x" * 2000, "audio/webm")}
    n = lambda sid: len(c.get(f"/api/sessions/{sid}", headers=H).json()["turns"])  # noqa: E731
    # 相手の往復が無い・別の話題の往復 → 断る（ふつうの発言として先生役に送らない）
    assert c.post(f"/api/sessions/{b}/voice", headers=H, files=wav, data={"kind": "predict"}).status_code == 400
    assert c.post(f"/api/sessions/{b}/voice", headers=H, files=wav, data={"kind": "predict", "ref_turn": str(ta)}).status_code == 400
    assert n(b) == 0
    # 同じ話題の往復への予想 → 往復の列に出ない往復（superseded）として録音を残す
    r = c.post(f"/api/sessions/{a}/voice", headers=H, files=wav, data={"kind": "predict", "ref_turn": str(ta)}).json()
    with db.tx() as con:
        row = db.row(con, "SELECT status, ref_turn, via FROM turn WHERE id=?", (r["turn_id"],))
    assert row == {"status": "superseded", "ref_turn": ta, "via": "voice"} and n(a) == 1
    # 確かめへの答えは、その話題の問いの番号だけを受け取る
    with db.tx() as con:
        ck = con.execute("INSERT INTO checkq(turn_id, session_id, q, a, qtype, created_at) VALUES(?,?,?,?,?,?)", (ta, a, "問い", "答え", "もしも", 0)).lastrowid
    ok = c.post(f"/api/sessions/{a}/voice", headers=H, files=wav, data={"kind": "answer", "check_id": str(ck)}).json()["turn_id"]
    ng = c.post(f"/api/sessions/{b}/voice", headers=H, files=wav, data={"kind": "answer", "check_id": str(ck)}).json()["turn_id"]
    assert _stage(ok).get("check_id") == ck and "check_id" not in _stage(ng)


def test_failed_voice_prediction_is_reported_to_the_screen(monkeypatch):
    import asyncio
    from server import events, stt
    got = []
    monkeypatch.setattr(events, "publish", got.append)

    async def boom(*a, **k):
        raise RuntimeError("聞き取れない")

    monkeypatch.setattr(stt, "transcribe", boom)
    asyncio.run(pipeline.run_predict(1, {"session_id": 5, "audio": "x.webm", "ref_turn": 77, "seq": 2}))
    assert {"t": "predict_failed", "turn_id": 77, "session_id": 5} in got


def test_long_prediction_is_kept_whole_for_resending_and_settings_reveal_leaves_no_skip_mark(monkeypatch):
    c = _client(monkeypatch)
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k IN ('predict', 'predict_skip')")
    sid = c.post("/api/sessions", headers=H, json={}).json()["id"]
    tid = c.post(f"/api/sessions/{sid}/text", headers=H, json={"text": "なぜ再送するの？"}).json()["turn_id"]
    long = "あ" * 900
    c.post(f"/api/sessions/{sid}/predict", headers=H, json={"turn_id": tid, "text": long})
    r = c.post(f"/api/turns/{tid}/unpredict", headers=H, json={"resend": True}).json()
    assert c.get(f"/api/sessions/{sid}", headers=H).json()["turns"][-1]["final_text"] == long   # 質問として送り直すときに欠けない
    # 出し方の設定を変えて開いた扱いにするとき（note: false）は、「誘いに乗らなかった」の印を付けない
    with db.tx() as con:
        t2 = _turn(con, sid, 9, status="done", stage={"offer": "predict"})
        t3 = _turn(con, sid, 10, status="done", stage={"offer": "predict"})
    c.post(f"/api/sessions/{sid}/reveal", headers=H, json={"turn_ids": [t2], "note": False})
    assert _stage(t2)["revealed_at"] > 0 and db.get_pref("predict_skip", "0") == "0"
    c.post(f"/api/sessions/{sid}/reveal", headers=H, json={"turn_ids": [t3]})
    assert db.get_pref("predict_skip", "0") == "1" and r["turn_id"]
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k IN ('predict', 'predict_skip')")


def test_prediction_made_while_waiting_survives_the_arrival_of_the_answer():
    # 待つあいだに付いた予想と誘いの印は、答えが届いたときの書き込みで消えない
    db.init()
    with db.tx() as con:
        sid = _session(con)
        tid = _turn(con, sid, 1, status="thinking", stage={"kind": "question", "offer": "predict", "budget": {"chars": 250, "why": "会話の間合い"}})
    pipeline.save_predict(None, tid, "たぶんこう", "text")
    pipeline.finish(tid, sid, "答えです。", "なぜ？", {"tutor": 1200, "kind": "question", "offer": "predict"}, "question")
    st = _stage(tid)
    assert st["predict"] == "たぶんこう" and st["offer"] == "predict" and st["tutor"] == 1200


# ── 片づけた話題 ──
def test_archived_topics_are_listed_and_can_be_restored(monkeypatch):
    c = _client(monkeypatch)
    sid = c.post("/api/sessions", headers=H, json={"title": "作り物の話題"}).json()["id"]
    with db.tx() as con:
        t = _turn(con, sid, 1, status="done", stage={})
        con.execute("INSERT INTO checkq(turn_id, session_id, q, a, qtype, created_at) VALUES(?,?,?,?,?,?)", (t, sid, "問い", "答え", "もしも", 0))
        con.execute("INSERT INTO checkq(turn_id, session_id, q, a, created_at) VALUES(?,?,?,?,?)", (t, sid, "古い問い", "答え", 0))
    ids = lambda key: [s["id"] for s in c.get("/api/state", headers=H).json()[key]]  # noqa: E731
    assert sid in ids("sessions") and sid not in ids("archived")
    c.patch(f"/api/sessions/{sid}", headers=H, json={"archived": True})
    st = c.get("/api/state", headers=H).json()
    row = next(s for s in st["archived"] if s["id"] == sid)
    assert sid not in ids("sessions") and row["title"] == "作り物の話題" and row["turns"] == 1 and row["open_checks"] == 1
    c.patch(f"/api/sessions/{sid}", headers=H, json={"archived": False})
    assert sid in ids("sessions") and sid not in ids("archived")
    with db.tx() as con:
        kinds = [r["kind"] for r in db.rows(con, "SELECT kind FROM log WHERE target=? AND kind IN ('archive','restore') ORDER BY id", (sid,))]
    assert kinds == ["archive", "restore"]


# ── 設定 ──
def test_prefs_accept_the_new_values_and_map_the_old_ones(monkeypatch):
    c = _client(monkeypatch)
    P = lambda body: (c.post("/api/prefs", headers=H, json=body), c.get("/api/state", headers=H).json()["prefs"])[1]  # noqa: E731
    assert P({"predict": "wait"})["predict"] == "wait" and P({"predict": "0"})["predict"] == "off"
    assert P({"predict": "1"})["predict"] == "both" and P({"predict": "off"})["predict"] == "off"
    assert P({"predict": "へん"})["predict"] == "off" and P({"predict": "both"})["predict"] == "both"
    assert P({"text_size": "l"})["text_size"] == "l" and P({"text_size": "xl"})["text_size"] == "l"
    assert P({"chime": "0"})["chime"] == "0" and P({"chime": "1", "text_size": "m"})["chime"] == "1"
    with db.tx() as con:
        con.execute("DELETE FROM pref WHERE k IN ('predict','predict_skip','text_size','chime')")


# ── ほかの話題の確かめ（起動したときの差し出し）と、話題ごとの言葉の一覧 ──
def test_due_checks_count_open_typed_checks_of_opened_answers_in_any_topic():
    db.init()
    with db.tx() as con:
        con.execute("DELETE FROM checkq")
        now = db.now()
        ck = lambda sid, tid, status="open", qtype="もしも": con.execute(  # noqa: E731
            "INSERT INTO checkq(turn_id, session_id, q, a, qtype, status, created_at) VALUES(?,?,?,?,?,?,?)", (tid, sid, "問い", "答え", qtype, status, 0)).lastrowid
        a = _session(con)                                              # 片づけた話題: 開いて時間のたった答えの問い2つ
        con.execute("UPDATE session SET archived=1 WHERE id=?", (a,))
        ta = _turn(con, a, 1, stage={"revealed_at": now - 600})
        first = ck(a, ta)
        ck(a, ta)
        b = _session(con)                                              # 開いたばかり・まだ開いていない・型の無い古い問い → 数えない
        ck(b, _turn(con, b, 1, stage={"revealed_at": now - 5}))
        ck(b, _turn(con, b, 2, stage={}))
        ck(b, _turn(con, b, 3, stage={"revealed_at": now - 600}), qtype=None)
        c = _session(con)                                              # 直近の3問がすべて飛ばしの話題 → 数えない
        tc = _turn(con, c, 1, stage={"revealed_at": now - 600})
        for _ in range(3):
            ck(c, tc, status="skipped")
        ck(c, tc)
        d = flow.due_checks(con, 120)
        assert d == {"n": 2, "next": {"session_id": a, "archived": True}}
        assert db.row(con, "SELECT session_id FROM checkq WHERE id=?", (first,))["session_id"] == d["next"]["session_id"]
        assert flow.due_checks(con, 120, exclude=a) == {"n": 0, "next": None}   # いま開いている話題の分は数えない
        con.execute("DELETE FROM checkq")


def test_all_tab_lists_words_by_topic_without_example_sentences():
    db.init()
    with db.tx() as con:
        a = _session(con, "作り物の話題A")
        ta = _turn(con, a, 1, stage={})
        m = {"center": "検査の言葉ア", "gist": "説明", "src": "一般", "broader": [{"label": "検査の言葉イ", "src": "一般"}],
             "related": [{"label": "検査の言葉ウ", "rel": "部分", "link": "を中に持つ", "src": "一般"}],
             "examples": ["これは検査の例の文です"], "nonexamples": ["これは検査の非例の文です"]}
        tutor.merge_map(con, a, ta, m)
    r = graph.by_topic()
    t = next(x for x in r["topics"] if x["id"] == a)
    labels = [c["label"] for c in t["concepts"]]
    assert t["title"] == "作り物の話題A" and t["archived"] is False
    assert set(labels) == {"検査の言葉ア", "検査の言葉イ", "検査の言葉ウ"}            # 例と非例の文は並べない
    assert all("例の文" not in c["label"] for x in r["topics"] for c in x["concepts"])
    center = next(c for c in t["concepts"] if c["label"] == "検査の言葉ア")
    assert center["coverage"] == {"known": 0, "total": 2} and center["state"] is None
    assert r["counts"]["concepts"] >= 3 and r["counts"]["relations"] >= 2 and "checked" in r["counts"]


# ── 別の読み（読みの判定役） ──
def test_readings_output_is_kept_only_when_it_is_well_formed():
    ok = '{"alt": true, "took": "書類の書き方", "others": [{"label": "手元の書類の中身", "ask": "手元の書類に書いてある中身を教えて"}]}'
    assert readings.parse(ok) == {"took": "書類の書き方", "others": [{"label": "手元の書類の中身", "ask": "手元の書類に書いてある中身を教えて"}]}
    assert readings.parse("```json\n" + ok + "\n```")["took"] == "書類の書き方"           # 囲みが付いていても読む
    assert readings.parse('考えます。{"alt": false}\n言い直します。' + ok)["took"] == "書類の書き方"   # 言い直したら最後の塊
    assert readings.parse('{"alt": false}') is None and readings.parse("読めない") is None and readings.parse("") is None
    assert readings.parse('{"alt": true, "took": "", "others": [{"label": "x", "ask": "y"}]}') is None        # 答えた読みが空
    assert readings.parse('{"alt": true, "took": "書き方", "others": []}') is None                             # 別の読みが無い
    assert readings.parse('{"alt": true, "took": "書き方", "others": [{"label": "書き方", "ask": "y"}]}') is None  # 同じ読み
    long = '{"alt": true, "took": "書き方", "others": [{"label": "' + "あ" * 41 + '", "ask": "y"}, {"label": "中身", "ask": "z"}]}'
    assert readings.parse(long) == {"took": "書き方", "others": [{"label": "中身", "ask": "z"}]}                # 長すぎる札は捨てる
    three = '{"alt": true, "took": "t", "others": [{"label": "a", "ask": "1"}, {"label": "b", "ask": "2"}, {"label": "c", "ask": "3"}]}'
    assert [o["label"] for o in readings.parse(three)["others"]] == ["a", "b"]                                # 札は2つまで


def test_readings_judge_runs_only_for_the_first_question_of_a_topic(monkeypatch):
    monkeypatch.setattr(readings, "ENABLED", True)
    E = lambda kind="question", via="text", first=True, ref=False, said="議事録の知識を付けたい", prose="あ" * 60: \
        readings.eligible(kind, via, first, ref, said, prose)  # noqa: E731
    assert E() and E(via="voice")
    assert not E(first=False) and not E(kind="confirm") and not E(kind="answer") and not E(kind="command")
    assert not E(via="click") and not E(via="research") and not E(ref=True) and not E(said="あ") and not E(prose="短い")
    monkeypatch.setattr(readings, "ENABLED", False)
    assert not E()                                                     # 止めているとき（検査・記録役を使わない設定）


def test_alt_is_attached_to_the_turn_and_a_pick_is_marked(monkeypatch):
    import asyncio
    c = _client(monkeypatch)
    sid = c.post("/api/sessions", headers=H, json={}).json()["id"]
    with db.tx() as con:
        tid = _turn(con, sid, 1, text="議事録の知識を付けたい", status="done", stage={})
        wait = _turn(con, sid, 2, status="thinking", stage={})
    alt = {"took": "書き方", "others": [{"label": "手元の議事録の中身", "ask": "手元の議事録の中身を教えて"}]}

    async def found(said, prose):
        return alt

    async def none(said, prose):
        return None

    async def broken(said, prose):
        raise RuntimeError("取れない")

    monkeypatch.setattr(readings, "judge", found)
    asyncio.run(pipeline.run_readings(tid, sid, "議事録の知識を付けたい", "答え"))
    asyncio.run(pipeline.run_readings(wait, sid, "x", "y"))           # 届いていない往復には付けない
    assert _stage(tid)["alt"] == alt and "alt" not in _stage(wait)
    assert c.get(f"/api/sessions/{sid}", headers=H).json()["turns"][0]["alt"] == alt
    with db.tx() as con:
        t2 = _turn(con, sid, 3, status="done", stage={})
    for f in (none, broken):                                           # 無い・取れなかったときは何も足さない
        monkeypatch.setattr(readings, "judge", f)
        asyncio.run(pipeline.run_readings(t2, sid, "x", "y"))
    assert "alt" not in _stage(t2)
    # 札を押して聞き直した往復には、押した印が付く（文字の欄からの送信には付けない）
    a = c.post(f"/api/sessions/{sid}/text", headers=H, json={"text": "手元の議事録の中身を教えて", "via": "click", "alt": True}).json()["turn_id"]
    b = c.post(f"/api/sessions/{sid}/text", headers=H, json={"text": "ふつうの問い", "alt": True}).json()["turn_id"]
    assert _stage(a).get("alt_pick") is True and "alt_pick" not in _stage(b)


def test_changing_the_tutor_instructions_is_a_deliberate_step():
    # 先生役の指示（tutor.SYSTEM）の印。v0.6 は指示を変えていない（v0.5 と同じ印 7bfeab1c25820cc6）。v0.7（2026-11-17・DESIGN 18章）で、
    # コードの決まりと、構成の図・状態と型と表の図・ファイルの並びを足して変えた。
    # 指示を変えると、いまある話題はすべて次の往復で新しい会話に替わる（DESIGN 15.11）。変えるときは、形とコードの測り
    # （tests/eval_code.py。前からの14問の形が変わらないかも見る）を流し直してから、この印を新しい値に書き換える
    assert tutor.prompt_sig() == "33bcd86d6ce8eb41"
