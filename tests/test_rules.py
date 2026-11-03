"""機械で決める規則の検査（整形役の直しすぎ・判定の根拠・札の読み取り・聞き違いの拾い方・「」の照合）。"""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("TONARI_DATA_DIR", tempfile.mkdtemp(prefix="tonari-test-"))

from server import app as appmod, corpus, db, fixer, tutor  # noqa: E402


def test_fixer_keeps_term_fixes():
    d = {"text": "遺族厚生年金の中高齢寡婦加算を教えて", "edits": [{"from": "中、高齢化価算", "to": "中高齢寡婦加算", "why": "用語"}],
         "unsure": [], "title": "中高齢寡婦加算", "kind": "question"}
    v = fixer.verify(d, "遺族厚生年金の中、高齢化価算を教えて", None)
    assert v["fallback"] is None
    assert v["edits"] == [{"from": "中、高齢化価算", "to": "中高齢寡婦加算", "why": "用語"}]


def test_fixer_rejects_rewrite():
    # 言い換え・要約で元の文から大きく離れたら、直しを捨てて元の文（Scribe）を使う
    d = {"text": "年金の加算制度について詳しい解説をお願いします", "edits": [], "unsure": [], "title": "", "kind": "question"}
    v = fixer.verify(d, "合格ともそうのアプリで寡婦加算の違いを教えて", "合格伴走のアプリで寡婦加算の違いを教えて")
    assert v["text"] == "合格伴走のアプリで寡婦加算の違いを教えて"
    assert v["fallback"].startswith("直しすぎ")


def test_fixer_base_text_haas_drops_words():
    # Haas は用語に寄せると語を落とすことがある（下の short は「の違い」が消えた実例・字数は43→40で長さでは見分けられない）。
    # 直しを捨てるときの元の文は Apple にする。Scribe は今までどおり Scribe。Apple が無いときだけ Haas
    apple = "合格ともそうのアプリで、遺族厚生年金の中高齢化負荷と経過的か負荷の違いを教えてください"
    short = "合格伴走のアプリで、遺族厚生年金の中高齢化負荷と、経過的寡婦加算を教えてください"
    assert fixer.base_text(apple, short, "haas") == apple
    assert fixer.base_text(apple, short, "scribe") == short
    assert fixer.base_text("", short, "haas") == short
    assert fixer.base_text(apple, None, "haas") == apple
    d = {"text": "", "edits": []}
    assert fixer.verify(d, apple, short, "haas")["text"] == apple


def test_haas_keywords_are_lines_without_readings_marks():
    from server import stt
    kw = stt.haas_keywords(["寡婦加算", "a=b", "寡婦加算", "", "x" * 60] + [f"語{i}" for i in range(80)])
    lines = kw.split("\n")
    assert lines[0] == "寡婦加算" and lines[1] == "ab" and len(lines) == 50 and "=" not in kw


def test_fixer_drops_edit_without_source():
    # from が どちらの文字起こしにも無い edit は見せない
    d = {"text": "ベイズ知識追跡とは", "edits": [{"from": "ベース", "to": "ベイズ", "why": "x"}], "unsure": [], "kind": "question"}
    v = fixer.verify(d, "レイズ知識追跡とは", None)
    assert v["edits"] == []


def test_parse_blocks():
    md = "答えです。\n\n```tonari-map\n{\"center\": \"A\", \"broader\": [{\"label\": \"B\", \"src\": \"一般\"}]}\n```\n本文\n" \
         "```tonari-check\n[{\"q\": \"Aの上位は\", \"a\": \"B\", \"concept\": \"A\", \"rel\": \"broader\", \"target\": \"B\"}]\n```\n" \
         "```mermaid\nflowchart LR\nA-->B\n```\n```tonari-grade\n{壊れた\n```"
    b = tutor.parse_blocks(md)
    assert b["map"]["center"] == "A"
    assert b["check"][0]["target"] == "B"
    assert b["mermaid"] == ["flowchart LR\nA-->B"]
    assert len(b["errors"]) == 1
    assert "```" not in tutor.strip_blocks(md)


def test_grade_needs_verbatim_evidence():
    db.init()
    with db.tx() as con:
        con.execute("INSERT INTO session(id, title, model, created_at, updated_at) VALUES(1,'t','opus',0,0)")
        tutor.merge_map(con, 1, 1, {"center": "知識空間理論", "opposite": [{"label": "ベイズ知識追跡", "axis": "構造か時間か", "src": "一般"}]})
        said = "構造を見るか時間の変化を見るかで対になる"
        out = tutor.apply_grades(con, 1, 1, [
            {"concept": "知識空間理論", "target": "ベイズ知識追跡", "rel": "opposite", "result": "hit", "evidence": "言っていない言葉"},
        ], said)
        assert out[0]["verified"] is False and out[0]["recorded"] is False
        out = tutor.apply_grades(con, 1, 1, [
            {"concept": "知識空間理論", "target": "ベイズ知識追跡", "rel": "opposite", "result": "hit", "evidence": "時間の変化を見るかで対になる"},
        ], said)
        assert out[0]["verified"] is True and out[0]["recorded"] is True
        rm = db.row(con, "SELECT state, by FROM rel_mastery")
        assert rm == {"state": "known", "by": "check"}


def test_opposite_is_undirected():
    db.init()
    with db.tx() as con:
        a = tutor.upsert_concept(con, "甲")
        b = tutor.upsert_concept(con, "乙")
        r1 = tutor.upsert_relation(con, b, a, "opposite", "軸", None, "一般", 1)
        r2 = tutor.upsert_relation(con, a, b, "opposite", "軸", None, "推測", 2)
        assert r1 == r2
        # 根拠の弱い推測では、一般の知識の根拠を上書きしない
        assert db.row(con, "SELECT src_kind FROM relation WHERE id=?", (r1,))["src_kind"] == "general"


def test_mishear_pairs():
    assert appmod.mishear_pairs("合格バンドのアプリで", "合格伴走のアプリで", "voice") == [("バンド", "伴走")]
    assert appmod.mishear_pairs("合格バンドのアプリで", "合格伴走のアプリで", "text") == []


def test_quote_check():
    with corpus._lock:
        corpus._state["rows"] = {"AAAAAAAAAA": {"title": "試し"}}
        corpus._state["folded"] = {"AAAAAAAAAA": db.fold("要点ごとに、分かっている確からしさ p と記憶の安定度 s（日）を持つ。")}
    q = corpus.check_quotes("〔AAAAAAAAAA｜推定〕に「分かっている確からしさ p と記憶」とある。「棚に無い言い回しの例です」")
    assert q[0]["found"] == "AAAAAAAAAA"
    assert q[1]["found"] is None


# ── 見せ方の語彙（v0.2）: 図の塊ごとの機械の決まり ──
def _blk(t, d):
    import json as _j
    return f"```tonari-{t}\n{_j.dumps(d, ensure_ascii=False)}\n```"


def test_views_placeholders_and_record_only_map():
    md = "言い切り。\n\n" + _blk("map", {"show": False, "center": "A", "broader": [{"label": "B", "src": "一般"}]}) + \
         "\n\n" + _blk("flow", {"name": "流れ", "why": "順番があるので", "steps": [{"label": "1"}, {"label": "2"}]}) + "\n\n本文。"
    b = tutor.parse_blocks(md)
    assert b["map"]["center"] == "A"            # 記録には入る
    assert [v["type"] for v in b["views"]] == ["flow"]   # 画面には流れだけ
    assert "[[view:0]]" in b["text"] and "```" not in b["text"]


def test_analogy_needs_breaks():
    d = {"name": "たとえ", "source": "図書館", "target": "知識空間理論", "pairs": [{"s": "棚", "t": "構造"}, {"s": "本", "t": "問題"}]}
    v, why = tutor.verify_view("analogy", d)
    assert v is None and "成り立たない" in why
    v, why = tutor.verify_view("analogy", {**d, "breaks": ["本は増えるが問題の集合は固定"]})
    assert v and v["breaks"]


def test_compare_same_rows_first_and_bad_rows_dropped():
    d = {"items": ["A", "B"], "rows": [{"axis": "違い", "values": ["x", "y"], "key": True},
                                       {"axis": "壊れ", "values": ["x"]}, {"axis": "共通", "same": "z"}]}
    v, _ = tutor.verify_view("compare", d)
    assert [r["axis"] for r in v["rows"]] == ["共通", "違い"]


def test_overlap_rules():
    v, why = tutor.verify_view("overlap", {"sets": ["A"], "elements": []})
    assert v is None
    v, _ = tutor.verify_view("overlap", {"sets": ["A", "B"], "elements": [
        {"label": "x", "in": [0]}, {"label": "y", "in": [0, 1]}, {"label": "z", "in": [5]}]})
    assert [e["label"] for e in v["elements"]] == ["x", "y"]


def test_timeline_and_calc_number_marks():
    base = {"from": 40, "to": 80, "unit": "歳", "lanes": [{"label": "加算", "spans": [{"from": 40, "to": 65}]}]}
    assert tutor.verify_view("timeline", {**base, "from": 80, "to": 40})[0] is None
    assert tutor.verify_view("timeline", {**base, "src": "一般"})[0]["numbers"] == "checked"
    assert tutor.verify_view("timeline", {**base, "src": "推測"})[0]["numbers"] == "unverified"
    assert tutor.verify_view("calc", {"result": "1万円", "formula": "a×b", "example": True})[0]["numbers"] == "example"
    assert tutor.verify_view("calc", {"formula": "a×b"})[0] is None


def test_decide_rules():
    one = {"root": {"ask": "子がいるか", "branches": [{"label": "はい", "result": "出る", "src": "一般"}]}}
    assert tutor.verify_view("decide", one)[0] is None          # 枝が1本だけ
    two = {"root": {"ask": "子がいるか", "branches": [{"label": "はい", "result": "出る"}, {"label": "いいえ", "result": "出ない", "src": "一般"}]}}
    v, _ = tutor.verify_view("decide", two)
    assert v["root"]["branches"][0]["node"]["src"] == "inferred"   # 出どころの無い結論は推測として描く
    assert v["root"]["branches"][1]["node"]["src"] == "general"


def test_mermaid_head():
    b = tutor.parse_blocks("```mermaid\n%% name: 関係の図 | why: 多対多なので\nerDiagram\n  A ||--o{ B : has\n```")
    assert b["views"][0]["name"] == "関係の図" and b["views"][0]["why"] == "多対多なので"
    assert b["views"][0]["code"].startswith("erDiagram")


def test_confirm_keeps_open_checks_and_judge_must_agree():
    # 言い直し（confirm）の判定では手つかずの確かめの問いを消さない。二度目の判定と食い違う当たりは記録しない
    db.init()
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO session(id, title, model, created_at, updated_at) VALUES(2,'t','opus',0,0)")
        tutor.merge_map(con, 2, 5, {"center": "SSR", "opposite": [{"label": "SSG", "axis": "HTMLを作る時", "src": "一般"}]})
        tutor.save_checks(con, 2, 5, [{"q": "もしビルドが無かったら？", "a": "要求ごとに作るしかない", "type": "もしも",
                                       "concept": "SSR", "target": "SSG", "rel": "opposite"}])
        said = "確認ですけど、SSGはビルドのときに作るってことですよね"
        g = [{"concept": "SSR", "target": "SSG", "rel": "opposite", "result": "hit", "evidence": "SSGはビルドのときに作る"}]
        out = tutor.apply_grades(con, 2, 6, g, said, "confirm", ["partial"])
        assert out[0]["verified"] and out[0]["agreed"] is False and out[0]["recorded"] is False
        assert db.row(con, "SELECT status FROM checkq WHERE session_id=2")["status"] == "open"
        assert db.row(con, "SELECT qtype FROM checkq WHERE session_id=2")["qtype"] == "もしも"
        out = tutor.apply_grades(con, 2, 7, g, said, "confirm", ["hit"])
        assert out[0]["agreed"] and out[0]["recorded"]
        out = tutor.apply_grades(con, 2, 8, g, said, "answer", [None])   # 判定役が取れなかった当たりは記録しない
        assert out[0]["recorded"] is False
        assert db.row(con, "SELECT status FROM checkq WHERE session_id=2")["status"] == "answered"


def test_checks_copyable_from_answer_are_dropped():
    md = "SSRはページが要求されるたびにサーバーでHTMLを作ります。\n\n```tonari-check``` ignored"
    keep, dropped = tutor.filter_checks([
        {"q": "SSRはいつHTMLを作るか", "a": "ページが要求されるたびに", "type": "見分け"},
        {"q": "もしキャッシュが無かったら？", "a": "毎回サーバーが作り直して遅くなる", "type": "もしも"},
        {"q": "型の無い問い", "a": "短い"},
    ], md)
    assert [c["q"] for c in keep] == ["もしキャッシュが無かったら？", "型の無い問い"]
    assert keep[1]["type"] == "その他" and len(dropped) == 1


def test_hedges_and_judge_parse():
    from server import judge, pipeline
    assert pipeline.hedges("サーバーで作る、時の違いでしたっけ", "たぶんそうですよね") == ["でしたっけ", "たぶん", "ですよね"]
    assert pipeline.hedges(None, "") == []
    assert judge.parse('{"results": ["hit", "xx"]}', 3) == ["hit", None, None]
    assert judge.parse("読めない", 2) == [None, None]


def test_return_check_picks_old_typed_open_question_and_stops_after_skips():
    now = db.now()
    views = [{"id": 10, "revealed_at": now - 600}, {"id": 11, "revealed_at": now - 10}, {"id": 12, "revealed_at": None}]
    def ck(i, turn, status="open", qtype="もしも"):
        return {"id": i, "turn_id": turn, "q": f"問い{i}", "qtype": qtype, "status": status}
    # 型の無い古い問い・開いてすぐの答え・まだ開いていない答えの問いは出さない
    assert appmod.return_check(views, [ck(1, 10, qtype=None), ck(2, 11), ck(3, 12)]) is None
    assert appmod.return_check(views, [ck(1, 10, qtype=None), ck(4, 10), ck(5, 10)])["id"] == 4
    # 直近に済んだ3問がすべて飛ばしなら、この話題では出さない
    skipped = [ck(6, 10, "skipped"), ck(7, 10, "skipped"), ck(8, 10, "skipped")]
    assert appmod.return_check(views, skipped + [ck(9, 10)]) is None
    assert appmod.return_check(views, skipped + [ck(13, 10, "answered"), ck(9, 10)])["id"] == 9


def test_predict_is_attached_to_the_answer_and_hidden():
    from server import pipeline
    db.init()
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO session(id, title, model, created_at, updated_at) VALUES(3,'t','opus',0,0)")
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text) VALUES(30,3,1,'text','done',0,'問い')")
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, ref_turn) VALUES(31,3,2,'voice','superseded',0,30)")
    pipeline.save_predict(31, 30, "たぶんビルドのときだと思う")
    with db.tx() as con:
        import json as _j
        st = _j.loads(db.row(con, "SELECT stage_ms FROM turn WHERE id=30")["stage_ms"])
        assert st["predict"] == "たぶんビルドのときだと思う" and st["revealed_at"] > 0
        assert db.row(con, "SELECT status FROM turn WHERE id=31")["status"] == "superseded"
        assert db.row(con, "SELECT kind FROM log WHERE kind='predict' AND target=30")


def test_answers_without_predict_band_count_as_revealed():
    # 確かめへの答え（kind=answer）のあとの答えは予想の帯を出さないので、届いた時点で開いたとみなす。
    # そうしないと、その答えに付いた確かめの問いが戻ったときに出ない
    from server import pipeline
    import json as _j
    db.init()
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO session(id, title, model, created_at, updated_at) VALUES(4,'t','opus',0,0)")
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text) VALUES(40,4,1,'text','thinking',0,'答え')")
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text) VALUES(41,4,2,'text','thinking',0,'問い')")
    md = 'まだです。\n```tonari-check\n[{"q": "もし順番が逆なら？", "a": "後ろの段が前の結果を使えず止まる", "type": "もしも"}]\n```'
    pipeline.finish(40, 4, md, "答え", {}, "answer")
    pipeline.finish(41, 4, md.replace("まだです", "説明"), "問い", {}, "question")
    with db.tx() as con:
        st40 = _j.loads(db.row(con, "SELECT stage_ms FROM turn WHERE id=40")["stage_ms"])
        st41 = _j.loads(db.row(con, "SELECT stage_ms FROM turn WHERE id=41")["stage_ms"])
        assert st40["revealed_at"] > 0 and "revealed_at" not in st41   # 問いへの答えは予想の帯を通ってから開く
        con.execute("UPDATE turn SET stage_ms=? WHERE id=40", (_j.dumps({**st40, "revealed_at": db.now() - 600}),))
        checks = db.rows(con, "SELECT * FROM checkq WHERE session_id=4 ORDER BY id")
        turns = [{"id": r["id"], "revealed_at": _j.loads(r["stage_ms"]).get("revealed_at")} for r in db.rows(con, "SELECT id, stage_ms FROM turn WHERE session_id=4")]
    assert appmod.return_check(turns, checks)["turn_id"] == 40


def test_no_apple_pc_uses_local_engine_and_mac_keeps_apple(monkeypatch, tmp_path):
    """Apple の聞き取りが無い PC（Windows など）では auto で Haas を使い、Mac で Apple があるときは従来どおり使わない。"""
    from server import config, stt
    fake = tmp_path / "speech"
    fake.write_text("")
    monkeypatch.setattr(config, "SPEECH_BIN", str(fake))
    monkeypatch.setattr(config, "LOCAL_ASR", "auto")
    monkeypatch.setattr(stt, "apple_available", lambda: False)
    assert stt.local_allowed() == (True, config.LOCAL_ASR_MODEL)
    monkeypatch.setattr(stt, "apple_available", lambda: True)
    assert stt.local_allowed() == (False, "off")
    monkeypatch.setattr(config, "LOCAL_ASR", "haas")
    assert stt.local_allowed()[0] is True
    monkeypatch.setattr(config, "LOCAL_ASR", "off")
    monkeypatch.setattr(stt, "apple_available", lambda: False)
    assert stt.local_allowed() == (False, "off")
    # 整形役が使えないときに戻す文は、Apple が無ければ2本目
    assert fixer.base_text("", "ハースの文", "haas") == "ハースの文"


def test_eleven_key_is_read_from_env_files_in_order(monkeypatch, tmp_path):
    from server import config, stt
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    a, b = tmp_path / "a.env", tmp_path / "b.env"
    b.write_text("OTHER=1\nELEVENLABS_API_KEY='k-b'\n", encoding="utf-8")
    monkeypatch.setattr(config, "ELEVEN_ENV_FILES", [a, b])
    assert stt.eleven_key() == "k-b"
    a.write_text("ELEVENLABS_API_KEY=k-a\n", encoding="utf-8")
    assert stt.eleven_key() == "k-a"


def test_env_file_sets_tonari_settings_but_not_the_key(tmp_path):
    """記録の置き場の .env の TONARI_* は設定として読み、鍵は環境変数に入れない。環境変数があればそちらが勝つ。"""
    import subprocess
    import sys
    (tmp_path / ".env").write_text("TONARI_TUTOR_MODEL=sonnet\nTONARI_PORT=4999\nELEVENLABS_API_KEY=abcdefghijkl\n", encoding="utf-8")
    code = ("import os; from server import config; "
            "print(config.TUTOR_MODEL, config.PORT, 'ELEVENLABS_API_KEY' in os.environ)")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("TONARI_", "ELEVENLABS"))}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=Path(__file__).parent.parent,
                         env={**env, "TONARI_DATA_DIR": str(tmp_path), "TONARI_PORT": "4888"}).stdout.split()
    assert out == ["sonnet", "4888", "False"]


def test_write_env_keeps_other_lines(monkeypatch, tmp_path):
    from server import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    config.write_env("TONARI_SPEECH_BIN", "C:/x/speech.exe")
    config.write_env("ELEVENLABS_API_KEY", "k1234567890")
    config.write_env("ELEVENLABS_API_KEY", None)
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "TONARI_SPEECH_BIN=C:/x/speech.exe\n"


def test_health_never_returns_the_key(monkeypatch, tmp_path):
    import json as _json
    from server import config, health
    f = tmp_path / ".env"
    f.write_text("ELEVENLABS_API_KEY=secret-key-1234567\n", encoding="utf-8")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(config, "ELEVEN_ENV_FILES", [f])
    h = health.check()
    assert "secret-key-1234567" not in _json.dumps(h, ensure_ascii=False)
    sc = next(i for i in h["items"] if i["id"] == "scribe")
    assert sc["ok"] and "設定で入れた鍵" in sc["detail"]
    assert {i["id"] for i in h["items"]} >= {"claude", "ffmpeg", "stt", "scribe", "haas"}


def test_key_prefs_are_whitelisted_and_conflicts_refused():
    from fastapi.testclient import TestClient
    c = TestClient(appmod.app, base_url=f"http://127.0.0.1:{appmod.config.PORT}")
    h = {"X-Tonari": "1"}
    r = c.post("/api/prefs", headers=h, json={"keys": {"new": "Ctrl+KeyM", "bogus": "Alt+KeyX", "next": "Alt+Bad Key"}})
    assert r.status_code == 200 and appmod.key_prefs() == {"new": "Ctrl+KeyM"}
    r = c.post("/api/prefs", headers=h, json={"keys": {"new": "Alt+KeyN", "next": "Alt+KeyN"}})
    assert r.status_code == 400 and appmod.key_prefs() == {"new": "Ctrl+KeyM"}
    c.post("/api/prefs", headers=h, json={"keys": {}, "tutor_model": "sonnet"})
    sid = c.post("/api/sessions", headers=h, json={}).json()["id"]
    with db.tx() as con:
        assert db.row(con, "SELECT model FROM session WHERE id=?", (sid,))["model"] == "sonnet"
    c.post("/api/prefs", headers=h, json={"tutor_model": ""})
    assert appmod.key_prefs() == {}


def test_event_streams_end_on_close_and_do_not_reopen():
    """止めるときに画面への流れを終わらせ、つなぎ直しも受けない（つながったままだと uvicorn が止まりきらない）。"""
    import asyncio
    from server import events

    async def run():
        g = events.subscribe()
        assert (await g.__anext__())["t"] == "hello"
        nxt = asyncio.ensure_future(g.__anext__())
        await asyncio.sleep(0)
        events.close_all()
        try:
            await asyncio.wait_for(nxt, 2)
            return "続いた"
        except StopAsyncIteration:
            pass
        late = [ev async for ev in events.subscribe()]
        return late
    try:
        assert asyncio.run(run()) == []
    finally:
        events._closed = False
