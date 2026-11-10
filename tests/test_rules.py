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


# ── 実物に結ぶ（v0.4 作業A）: たとえの塊の新しい決まり・判定役の結果・流れの実例 ──
_AN_BODY = ("公開鍵暗号では、受け取る人が『公開鍵』と『秘密鍵』の組を作ります。送る人は公開鍵で暗号にし、"
            "受け取る人だけが秘密鍵で元に戻せます。『暗号文』は途中で読まれても中身が分かりません。")


def _an(pairs, **kw):
    return {"name": "たとえ", "why": "閉めるのと開けるのが別の物なので", "by": "tutor", "source": "南京錠と鍵",
            "target": "公開鍵暗号", "relation": "誰でも閉められるが、開けられるのは一人だけ", "pairs": pairs,
            "unmapped": ["鍵の長さ"], "breaks": ["南京錠は配り直せないが、公開鍵は何度でも配れる"], **kw}


_AN_PAIRS = [{"s": "開いた南京錠", "t": "公開鍵", "role": "誰でも閉められる"},
             {"s": "手元の鍵", "t": "秘密鍵", "role": "持ち主だけが開けられる", "t_val": "2048ビット"},
             {"s": "閉じた箱", "t": "暗号文", "role": "途中で開けられない"}]


def test_analogy_pairs_must_be_names_found_in_the_body():
    # 本文に無い実際の名前の対と、名前でなく文の対は捨てる。残りが2つ未満なら塊ごと捨てる（A4）
    pairs = _AN_PAIRS[:2] + [{"s": "判子", "t": "電子署名", "role": "本人が押した印"},
                             {"s": "南京錠は誰にでも配ってよいということ", "t": "公開鍵は誰に配っても安全だということ", "role": "配る"}]
    v, why = tutor.verify_view("analogy", _an(pairs), _AN_BODY)
    assert [p["t"] for p in v["pairs"]] == ["公開鍵", "秘密鍵"]
    assert v["pairs"][1]["t_val"] == "2048ビット" and v["pairs"][0]["role"] == "誰でも閉められる"
    assert v["relation"] and v["unmapped"] == ["鍵の長さ"] and v["by"] == "tutor"
    assert any("本文に無い" in x for x in v["dropped"]) and any("文の対" in x for x in v["dropped"])
    v, why = tutor.verify_view("analogy", _an([_AN_PAIRS[0], pairs[2]]), _AN_BODY)
    assert v is None and "2つ未満" in why
    # 本文の字は畳んで（NFKC・空白・大文字小文字）照らす
    v, _ = tutor.verify_view("analogy", _an([{"s": "箱", "t": "ＴＣＰ"}, {"s": "札", "t": "ack"}]), "tcp は ACK を返す")
    assert v and len(v["pairs"]) == 2
    # 対は5つまで
    many = [{"s": f"物{i}", "t": f"語{i}"} for i in range(7)]
    v, _ = tutor.verify_view("analogy", _an(many), "".join(f"語{i}" for i in range(7)))
    assert len(v["pairs"]) == 5


def test_old_analogy_is_still_drawn_when_a_saved_answer_is_read_again():
    # v0.4 より前に保存した答え（stage_ms に rules の印が無い）は、文の対でも本文に無い名前でも、前の決まりで描く
    old = {"name": "たとえ", "source": "図書館", "target": "知識空間理論",
           "pairs": [{"s": "棚に本が並ぶ順番", "t": "問題どうしの前提の関係"}, {"s": "貸し出しの記録", "t": "解けた問題の集合"}],
           "breaks": ["本は増えるが問題の集合は固定"]}
    md = "言い切り。\n\n" + _blk("analogy", old) + "\n\n本文。"
    b = tutor.turn_blocks(md, {})
    assert [v["type"] for v in b["views"]] == ["analogy"] and b["views"][0]["legacy"] and not b["errors"]
    assert tutor.turn_blocks(md, {"rules": 4})["views"] == []       # v0.4 の答えなら捨てる
    row = {"id": 1, "seq": 1, "via": "text", "status": "done", "error": None, "title": "t", "final_text": "q",
           "fixed_text": None, "apple_text": None, "scribe_text": None, "haas_text": None, "audio_sec": None,
           "created_at": 0, "done_at": 0, "edits_json": None, "unsure_json": None, "answer_md": md,
           "stage_ms": '{"revealed_at": 1}', "ref_turn": None}
    assert appmod.turn_view(row)["views"][0]["pairs"][0]["s"] == "棚に本が並ぶ順番"


def test_pair_judge_result_is_applied_at_finish_and_on_reload():
    import json as _j
    from server import pipeline
    db.init()
    md = _AN_BODY + "\n\n" + _blk("analogy", _an(_AN_PAIRS)) + "\n\n公開鍵で暗号にした暗号文は、秘密鍵でだけ戻せます。"
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO session(id, title, model, created_at, updated_at) VALUES(5,'t','opus',0,0)")
        for i in (50, 51, 52):
            con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text) VALUES(?,5,?,'text','thinking',0,'q')",
                        (i, i))
    # 1つを捨てても2つ残る
    pipeline.finish(50, 5, md, "q", {"analogy": [{"checked": True, "res": ["ok", "ng", "ok"], "ng": ["秘密鍵"]}]})
    # 2つ捨てると塊ごと捨てる
    pipeline.finish(51, 5, md, "q", {"analogy": [{"checked": True, "res": ["ok", "ng", "ng"], "ng": ["秘密鍵", "暗号文"]}]})
    # 判定役が取れなかったら出して、確かめていない印
    pipeline.finish(52, 5, md, "q", {"analogy": [{"checked": False}]})
    with db.tx() as con:
        rows = {r["id"]: r for r in db.rows(con, "SELECT * FROM turn WHERE id IN (50,51,52)")}
        saved = db.rows(con, "SELECT turn_id, source, by FROM analogy WHERE session_id=5 ORDER BY id")
    v50 = appmod.turn_view(rows[50])["views"]
    assert [p["t"] for p in v50[0]["pairs"]] == ["公開鍵", "暗号文"] and v50[0]["checked"] is True
    st50 = _j.loads(rows[50]["stage_ms"])
    assert st50["rules"] == 4 and any("秘密鍵" in e for e in st50["block_errors"])
    assert appmod.turn_view(rows[51])["views"] == []
    assert any("2つ未満" in e for e in _j.loads(rows[51]["stage_ms"])["block_errors"])
    v52 = appmod.turn_view(rows[52])["views"]
    assert len(v52[0]["pairs"]) == 3 and v52[0]["checked"] is False
    # 画面に出した塊だけが話題のたとえとして残り、次の往復で先生役に渡る（A8）
    assert [(r["turn_id"], r["source"], r["by"]) for r in saved] == [(50, "南京錠と鍵", "tutor"), (52, "南京錠と鍵", "tutor")]
    content = tutor.turn_content(5, "次の問い", "question", "text", [])
    assert "<この話題のたとえ>元の世界: 南京錠と鍵（先生役のたとえ）" in content and "開いた南京錠＝公開鍵" in content


def test_flow_example_runs_through_every_step_or_none():
    steps = [{"label": "キャッシュを見る", "ex": "無かった"}, {"label": "リゾルバに頼む", "ex": "8.8.8.8 へ送る"},
             {"label": "答えを返す", "ex": "93.184.215.14"}]
    v, _ = tutor.verify_view("flow", {"case": "example.com を引く", "steps": steps})
    assert v["case"] == "example.com を引く" and [s["ex"] for s in v["steps"]] == ["無かった", "8.8.8.8 へ送る", "93.184.215.14"]
    v, _ = tutor.verify_view("flow", {"case": "example.com を引く", "steps": steps[:2] + [{"label": "答えを返す"}]})
    assert "case" not in v and all("ex" not in s for s in v["steps"])
    # 8段に切ったあとの段で決める（9段目にだけ実例が無くても、残した8段に全部あれば通す）
    nine = [{"label": f"段{i}", "ex": f"値{i}"} for i in range(8)] + [{"label": "段8"}]
    v, _ = tutor.verify_view("flow", {"case": "例", "steps": nine})
    assert len(v["steps"]) == 8 and all(s.get("ex") for s in v["steps"]) and v["case"] == "例"


def test_main_view_skips_analogy_and_pair_judge_parse():
    import asyncio
    from server import judge
    views = [{"type": "analogy", "name": "たとえ"}, {"type": "flow", "name": "流れ"}]
    assert tutor.main_view(views)["type"] == "flow" and tutor.main_view(views[:1]) is None
    assert judge.parse_pairs('{"results": ["ok", "ng"]}', 2) == ["ok", "ng"]
    assert judge.parse_pairs('{"results": ["ok"]}', 2) is None and judge.parse_pairs("読めない", 1) is None
    assert judge.parse_pairs('```json\n{"results": ["ok", "maybe"]}\n```', 2) is None

    class Down:
        async def take(self):
            raise RuntimeError("判定役が立たない")
    keep = judge.PAIR_POOL
    judge.PAIR_POOL = Down()
    try:
        out = asyncio.run(judge.check_pairs(_AN_BODY, [{"pairs": _AN_PAIRS, "source": "南京錠と鍵"}]))
    finally:
        judge.PAIR_POOL = keep
    assert out == [{"checked": False}]
    assert "共通する働き「誰でも閉められる」" in judge.pair_input(_AN_BODY, {"pairs": _AN_PAIRS, "source": "s", "target": "t"})


def test_ground_click_is_marked_on_the_turn(monkeypatch):
    # A10: 「実際には何のこと？」は via=click で送り、往復に ground の印を残す（押した回数を数えるため）
    import json as _j
    from fastapi.testclient import TestClient
    monkeypatch.setattr(appmod.pipeline, "spawn", lambda coro: coro.close())   # 先生役は呼ばない
    c = TestClient(appmod.app, base_url=f"http://127.0.0.1:{appmod.config.PORT}")
    h = {"X-Tonari": "1"}
    sid = c.post("/api/sessions", headers=h, json={}).json()["id"]
    q = "『リゾルバ』は、実際には何のことですか。実際の名前と、実際の値か実例で、短く答えてください"
    tid = c.post(f"/api/sessions/{sid}/text", headers=h, json={"text": q, "via": "click", "ground": True}).json()["turn_id"]
    tid2 = c.post(f"/api/sessions/{sid}/text", headers=h, json={"text": "ふつうの問い", "ground": True}).json()["turn_id"]
    with db.tx() as con:
        r = db.row(con, "SELECT via, stage_ms FROM turn WHERE id=?", (tid,))
        r2 = db.row(con, "SELECT via, stage_ms FROM turn WHERE id=?", (tid2,))
    assert r["via"] == "click" and _j.loads(r["stage_ms"])["ground"] is True
    assert r2["stage_ms"] is None        # 文字の欄から送った問いには付けない


# ── しくみの絵（v0.4 作業B の B2）: 部品は本文にある名前だけ・やりとりの両端は部品・入れ子は1段・実例は全部か無しか ──
_PT_BODY = ("『ブラウザ』は URL の名前を『DNS リゾルバ』に問い合わせて IP アドレスを受け取り、その住所の『Web サーバー』に"
            "HTTP の要求を送ります。ブラウザの中では『レンダラ』が届いた HTML を画面に描きます。")


def _pt(parts, links, **kw):
    return {"name": "しくみの絵", "why": "部品の間で名前と住所とページが渡るので", "parts": parts, "links": links, **kw}


_PT_PARTS = [{"id": "br", "label": "ブラウザ"}, {"id": "dns", "label": "DNS リゾルバ", "note": "名前を住所にする"},
             {"id": "web", "label": "Web サーバー"}, {"id": "rd", "label": "レンダラ", "in": "br"}]
_PT_LINKS = [{"from": "br", "to": "dns", "label": "名前を問う", "ex": "example.com"},
             {"from": "dns", "to": "br", "label": "住所を返す", "ex": "93.184.215.14"},
             {"from": "br", "to": "web", "label": "要求を送る", "ex": "GET /"},
             {"from": "web", "to": "rd", "label": "HTML を返す", "ex": "index.html"}]


def test_parts_keep_only_parts_named_in_the_body_and_links_between_them():
    parts = _PT_PARTS + [{"id": "cdn", "label": "CDN"}, {"id": "lb", "label": "ロードバランサ"}]
    links = _PT_LINKS + [{"from": "br", "to": "cdn", "label": "画像を取る"}, {"from": "web", "to": "nowhere", "label": "x"},
                         {"from": "dns", "to": "dns", "label": "自分に聞く"}, {"from": "ブラウザ", "to": "Web サーバー", "label": "名前で指す"}]
    v, why = tutor.verify_view("parts", _pt(parts, links, case="example.com を開く"), _PT_BODY)
    assert [p["id"] for p in v["parts"]] == ["br", "dns", "web", "rd"]            # 本文に無い CDN・ロードバランサは捨てる
    assert [(l["from"], l["to"]) for l in v["links"]] == [("br", "dns"), ("dns", "br"), ("br", "web"), ("web", "rd"), ("br", "web")]
    assert v["parts"][1]["note"] == "名前を住所にする" and v["parts"][3]["in"] == "br"
    d = v["dropped"]
    assert any("『CDN』が本文に無い" in x for x in d) and sum("両端が部品に無い" in x for x in d) == 2
    assert any("自分から自分" in x for x in d)
    # 実例は全部のやりとりにあるときだけ残す（名前で指した5本目に ex が無いので、全部から外し、case も出さない）
    assert all("ex" not in l for l in v["links"]) and "case" not in v
    v, _ = tutor.verify_view("parts", _pt(_PT_PARTS, _PT_LINKS, case="example.com を開く"), _PT_BODY)
    assert [l["ex"] for l in v["links"]] == ["example.com", "93.184.215.14", "GET /", "index.html"] and v["case"] == "example.com を開く"
    assert "dropped" not in v
    # 部品が2つ未満・やりとりが無いなら塊ごと捨てる
    v, why = tutor.verify_view("parts", _pt([_PT_PARTS[0], {"id": "x", "label": "本文に無い部品"}], _PT_LINKS[:1]), _PT_BODY)
    assert v is None and "2つ未満" in why
    v, why = tutor.verify_view("parts", _pt(_PT_PARTS[:2], [{"from": "br", "to": "zz", "label": "x"}]), _PT_BODY)
    assert v is None and "やりとりが無い" in why
    # 本文との照らしは畳んだ字（NFKC・空白・大小）で
    v, _ = tutor.verify_view("parts", _pt([{"id": "a", "label": "ＤＮＳリゾルバ"}, {"id": "b", "label": "web サーバー"}],
                                           [{"from": "a", "to": "b", "label": "x"}]), _PT_BODY)
    assert v and len(v["parts"]) == 2


def test_parts_nesting_is_one_level_and_bad_parents_are_removed():
    parts = [{"id": "os", "label": "ブラウザ"}, {"id": "a", "label": "レンダラ", "in": "os"},
             {"id": "b", "label": "DNS リゾルバ", "in": "a"},           # 2段目（親のレンダラにも親がある）
             {"id": "c", "label": "Web サーバー", "in": "c"}]           # 自分自身
    v, _ = tutor.verify_view("parts", _pt(parts + [{"id": "d", "label": "HTML", "in": "ghost"}],   # 無い親
                                          [{"from": "os", "to": "c", "label": "x"}]), _PT_BODY)
    got = {p["id"]: p.get("in") for p in v["parts"]}
    assert got == {"os": None, "a": "os", "b": None, "c": None, "d": None}
    assert sum("入れ子を外した" in x for x in v["dropped"]) == 3
    # 互いを親にした2つは、どちらも2段目なので両方外す（決まった答えになる）
    v, _ = tutor.verify_view("parts", _pt([{"id": "a", "label": "ブラウザ", "in": "b"}, {"id": "b", "label": "レンダラ", "in": "a"}],
                                          [{"from": "a", "to": "b", "label": "x"}]), _PT_BODY)
    assert all("in" not in p for p in v["parts"])
    # 部品は6つまで・やりとりは8つまで（並んだ順のまま）
    six = "".join(f"『部品{i}』" for i in range(8))
    many = [{"id": f"p{i}", "label": f"部品{i}"} for i in range(8)]
    lk = [{"from": f"p{i % 6}", "to": f"p{(i + 1) % 6}", "label": f"渡す{i}"} for i in range(10)]
    v, _ = tutor.verify_view("parts", _pt(many, lk), six)
    assert len(v["parts"]) == 6 and [l["label"] for l in v["links"]] == [f"渡す{i}" for i in range(8)]


def test_parts_block_in_an_answer_is_drawn_and_partial_drops_are_logged():
    md = _PT_BODY + "\n\n" + _blk("parts", _pt(_PT_PARTS + [{"id": "cdn", "label": "CDN"}], _PT_LINKS)) + "\n\n本文の続き。"
    b = tutor.parse_blocks(md)
    assert [v["type"] for v in b["views"]] == ["parts"] and b["views"][0]["name"] == "しくみの絵"
    assert any(e.startswith("tonari-parts: 一部を捨てた") and "CDN" in e for e in b["errors"])
    assert tutor.main_view(b["views"])["type"] == "parts"
    # 本文の名前は塊の外で照らす（塊の中にだけ出る名前の部品は捨てる）
    md2 = "答え。\n\n" + _blk("parts", _pt(_PT_PARTS, _PT_LINKS))
    b2 = tutor.parse_blocks(md2)
    assert b2["views"] == [] and any("しくみの絵: 部品が2つ未満" in e for e in b2["errors"])


# ── ヒントつきの確かめ（v0.4 作業B の C1・C2・C3） ──
def test_hints_containing_the_answer_are_dropped_and_kept_to_two():
    md = "DNS は名前を IP アドレスに変えます。\n\n" + _blk("check", [])
    keep, dropped = tutor.filter_checks([
        {"q": "もし住所が返らなかったら？", "a": "要求を送れずに止まる", "type": "もしも",
         "hints": ["次に何ができないかを考える", "答えは、要求を送れずに止まる", "宛先が決まらない段を探す", "4つ目"]},
        {"q": "短い答え", "a": "止まる", "type": "もしも", "hints": ["止まるかどうか", 5, "", "  "]},   # 4字未満の答えは照らさない
        {"q": "ヒントの無い問い", "a": "どこかで止まる", "type": "当てはめ"},
    ], md)
    assert keep[0]["hints"] == ["次に何ができないかを考える", "宛先が決まらない段を探す"]   # 答えを含む段を外し、2段まで
    assert keep[1]["hints"] == ["止まるかどうか"] and keep[2]["hints"] == []
    assert sum(d.startswith("確かめのヒントを外した") for d in dropped) == 1
    # 外す・残すの照らしは畳んだ字（全角・空白）で
    assert tutor.filter_hints(["ヒントは Ｇｅｔ です"], db.fold("GET /"))[0] == ["ヒントは Ｇｅｔ です"]
    assert tutor.filter_hints(["ヒントは ＧＥＴ/ です"], db.fold("GET /"))[1] == 1


def test_hint_columns_are_added_to_an_old_db(monkeypatch, tmp_path):
    import sqlite3
    from server import config
    old = tmp_path / "old.db"
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE checkq (id INTEGER PRIMARY KEY, turn_id INTEGER NOT NULL, session_id INTEGER NOT NULL, "
                "q TEXT NOT NULL, a TEXT, concept TEXT, target TEXT, rel TEXT, status TEXT NOT NULL DEFAULT 'open', created_at REAL NOT NULL)")
    con.execute("INSERT INTO checkq(turn_id, session_id, q, created_at) VALUES(1, 1, '前の問い', 0)")
    con.commit()
    con.close()
    monkeypatch.setattr(config, "DB_PATH", old)
    db.init()
    with db.tx() as c2:
        names = {r["name"] for r in c2.execute("PRAGMA table_info(checkq)").fetchall()}
        r = db.row(c2, "SELECT hints, hints_used, qtype FROM checkq")
    assert {"qtype", "hints", "hints_used"} <= names and r == {"hints": None, "hints_used": 0, "qtype": None}


def test_return_check_gives_hints_one_step_at_a_time_and_recall_is_attached():
    import json as _j
    from fastapi.testclient import TestClient
    db.init()   # 話題の番号は、ほかの試験が API で作る話題と重ならない 60 にする
    now = db.now()
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO session(id, title, model, created_at, updated_at) VALUES(60,'t','opus',0,0)")
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, done_at, final_text, stage_ms) "
                    "VALUES(600,60,1,'text','done',?,?,'問い',?)", (now - 3 * 86400 - 400, now - 3 * 86400 - 300,
                                                                 _j.dumps({"revealed_at": now - 3 * 86400 - 200})))
        [c] = tutor.save_checks(con, 60, 600, [{"q": "もし順番が逆なら？", "a": "後ろの段が止まる", "type": "もしも",
                                             "hints": ["何が先に要るかを考える", "前の段が作る物を思い出す"]}])
    cl = TestClient(appmod.app, base_url=f"http://127.0.0.1:{appmod.config.PORT}")
    h = {"X-Tonari": "1"}
    rc = cl.get("/api/sessions/60", headers=h).json()["return_check"]
    assert rc["id"] == c["id"] and rc["hints_n"] == 2 and rc["hints"] == []     # まだ出していない段の文は渡さない
    assert cl.post(f"/api/checks/{c['id']}/hint", headers=h).json()["hints"] == ["何が先に要るかを考える"]
    assert cl.get("/api/sessions/60", headers=h).json()["return_check"]["hints"] == ["何が先に要るかを考える"]
    for _ in range(2):   # 2段より先は増えない
        r = cl.post(f"/api/checks/{c['id']}/hint", headers=h).json()
    assert r["hints"] == ["何が先に要るかを考える", "前の段が作る物を思い出す"]
    with db.tx() as con:
        assert db.row(con, "SELECT hints_used FROM checkq WHERE id=?", (c["id"],))["hints_used"] == 2
        assert db.row(con, "SELECT COUNT(*) AS n FROM log WHERE kind='hint' AND target=?", (c["id"],))["n"] == 2
        # 戻ったときの問いに答えた往復（kind=answer・check_id）
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, done_at, final_text, stage_ms) "
                    "VALUES(601,60,2,'voice','done',?,?,'答え',?)", (now, now, _j.dumps({"kind": "answer", "check_id": c["id"]})))
    turns = cl.get("/api/sessions/60", headers=h).json()["turns"]
    assert "recall" not in turns[0]
    assert turns[1]["recall"]["text"] == "読んでから3日あけて、何も見ずに言えた（ヒント2段）"
    assert appmod.gap_text(2 * 3600 + 5) == "2時間" and appmod.gap_text(30) == "1分" and appmod.gap_text(59 * 60) == "59分"


def test_usage_stats_counts_numbers_only_and_opens_read_only(tmp_path):
    import json as _j
    import sqlite3
    import subprocess
    import sys
    from tests import usage_stats
    p = tmp_path / "tonari.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE turn (id INTEGER PRIMARY KEY, session_id INTEGER, seq INTEGER, via TEXT, status TEXT, stage_ms TEXT, created_at REAL)")
    con.execute("CREATE TABLE checkq (id INTEGER PRIMARY KEY, status TEXT, hints TEXT, hints_used INTEGER)")
    day = 86400
    rows = [(1, 1, 1, "voice", "done", {"shapes": [{"type": "flow"}, {"type": "analogy"}]}, 0),
            (2, 1, 2, "click", "done", {"ground": True}, 10),
            (3, 1, 3, "voice", "superseded", {}, 20),                       # 予想の往復は数えない
            (4, 2, 1, "text", "done", {"shapes": [{"type": "parts"}]}, 2 * day),
            (5, 2, 2, "click", "error", {"ground": True}, 2 * day + 5)]
    for r in rows:
        con.execute("INSERT INTO turn VALUES(?,?,?,?,?,?,?)", (*r[:5], _j.dumps(r[5]), r[6] + 1_700_000_000))
    for s, hs, used in [("answered", ["a", "b"], 2), ("skipped", [], 0), ("open", ["a"], 1), ("unknown", None, 0)]:
        con.execute("INSERT INTO checkq(status, hints, hints_used) VALUES(?,?,?)", (s, _j.dumps(hs) if hs is not None else None, used))
    con.commit()
    con.close()
    ro = usage_stats.open_ro(p)
    s = usage_stats.stats(ro)
    try:
        ro.execute("DELETE FROM turn")
        wrote = True
    except sqlite3.OperationalError:
        wrote = False
    ro.close()
    assert wrote is False
    assert (s["days_used"], s["turns"], s["turns_done"]) == (2, 4, 3)
    assert s["turns_by_via"] == {"voice": 1, "text": 1, "click": 2}
    assert (s["checks"], s["checks_answered"], s["checks_skipped"], s["checks_open"], s["answer_rate"]) == (4, 2, 1, 1, 0.5)
    assert (s["hints_used_total"], s["checks_with_hints"]) == (3, 2)
    assert (s["ground_clicks"], s["ground_after_analogy"], s["turns_with_analogy"], s["turns_with_parts"]) == (2, 1, 1, 1)
    out = subprocess.run([sys.executable, "tests/usage_stats.py", "--db", str(p)], capture_output=True, text=True,
                         cwd=Path(__file__).parent.parent).stdout
    assert "答えた率: 50%" in out and "使った日数: 2" in out


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


def test_resume_plan_keeps_the_conversation_only_while_the_instructions_are_the_same(monkeypatch):
    # claude -p の --resume は会話を始めたときの指示を使い続ける（2026-11-10・claude 2.1.322）。印が今の指示と同じ会話だけ続ける
    sig = tutor.prompt_sig()
    assert tutor.resume_plan(None, None, sig) == (None, False)        # まだ会話が無い話題
    assert tutor.resume_plan("c-1", sig, sig) == ("c-1", False)       # 今の指示で始めた会話は続ける
    assert tutor.resume_plan("c-1", None, sig) == (None, True)        # v0.4 より前に始めた会話（印が無い）
    assert tutor.resume_plan("c-1", "0" * 16, sig) == (None, True)    # 指示が変わった
    monkeypatch.setattr(corpus, "catalog", lambda: "id1｜題｜棚｜2026-11-10")
    assert tutor.prompt_sig() == sig                                    # 棚の目録が変わっても印は変わらない


def test_recap_has_the_prose_of_earlier_turns_without_blocks():
    old = {"name": "たとえ", "source": "店の伝票差し", "target": "待ち行列",
           "pairs": [{"s": "伝票を差す", "t": "仕事を積む"}, {"s": "伝票を取る", "t": "仕事を取り出す"}], "breaks": ["伝票は減らない"]}
    md1 = "一つ目の答え。\n\n" + _blk("analogy", old) + "\n\n```tonari-check\n[{\"q\": \"もしも？\", \"a\": \"止まる\"}]\n```"
    db.init()
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO session(id, title, model, created_at, updated_at) VALUES(70,'t','opus',0,0)")
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text, answer_md, stage_ms) "
                    "VALUES(700,70,1,'text','done',0,'一つ目の問い',?,'{}')", (md1,))
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text) VALUES(701,70,2,'text','superseded',0,'消した問い')")
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text, answer_md, stage_ms) "
                    "VALUES(702,70,3,'text','done',0,'二つ目の問い','二つ目の答え。','{\"rules\": 4}')")
    assert tutor.recap_text(70, 1) is None
    r = tutor.recap_text(70, 4)
    assert r.startswith("<これまでの会話>") and r.endswith("</これまでの会話>") and "話題の最初の答えではありません" in r
    assert "```" not in r and "もしも？" not in r and "消した問い" not in r       # 塊（古い形）と畳んだ往復は入れない
    assert "（図: たとえ（元の世界: 店の伝票差し））" in r
    assert r.index("本人: 一つ目の問い") < r.index("本人: 二つ目の問い")
    c = tutor.turn_content(70, "三つ目の問い", "question", "text", [], recap=r)
    assert c.startswith("<これまでの会話>") and "<本人の発言 種類=question 経路=text>\n三つ目の問い" in c
    assert not tutor.turn_content(70, "三つ目の問い", "question", "text", []).startswith("<これまでの会話>")


def test_old_conversation_is_restarted_with_a_recap_and_then_resumed(monkeypatch):
    import asyncio
    import json as _j
    from server import brain, pipeline
    db.init()
    with db.tx() as con:   # v0.4 より前に始めた会話（claude_sid はあるが指示の印が無い）
        con.execute("INSERT OR IGNORE INTO session(id, title, model, claude_sid, created_at, updated_at) VALUES(71,'t','opus','old-conv',0,0)")
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text, answer_md, stage_ms) "
                    "VALUES(710,71,1,'text','done',0,'前の問い','前の答え。','{}')")
        for tid, seq in ((711, 2), (712, 3)):
            con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text) VALUES(?,71,?,'text','recorded',0,'問い')",
                        (tid, seq))
    started = []

    class Fake:
        alive = False

        def __init__(self, resume):
            self.resume_sid = resume
            self.content = None

        async def ask(self, content):
            self.content = content
            yield ("sid", self.resume_sid or "new-conv")
            yield ("text", "答えです。")

    def get(sid, prompt, model, resume):
        started.append(Fake(resume))
        return started[-1]
    monkeypatch.setattr(brain.TUTORS, "get", get)
    asyncio.run(pipeline.ask_tutor(711, "問い", "question", "text", [], {}))
    asyncio.run(pipeline.ask_tutor(712, "問い", "question", "text", [], {}))
    assert started[0].resume_sid is None and started[0].content.startswith("<これまでの会話>") and "前の答え。" in started[0].content
    assert started[1].resume_sid == "new-conv" and "<これまでの会話>" not in started[1].content
    with db.tx() as con:
        s = db.row(con, "SELECT claude_sid, prompt_sig FROM session WHERE id=71")
        st = {r["id"]: _j.loads(r["stage_ms"]) for r in db.rows(con, "SELECT id, stage_ms FROM turn WHERE id IN (711, 712)")}
    assert s == {"claude_sid": "new-conv", "prompt_sig": tutor.prompt_sig()}
    assert st[711].get("fresh_prompt") is True and "fresh_prompt" not in st[712]


def test_prompt_sig_column_is_added_to_an_old_db(monkeypatch, tmp_path):
    import sqlite3
    from server import config
    old = tmp_path / "old.db"
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE session (id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '新しい話題', model TEXT NOT NULL, "
                "claude_sid TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, read_at REAL NOT NULL DEFAULT 0, "
                "archived INTEGER NOT NULL DEFAULT 0)")
    con.execute("INSERT INTO session(model, claude_sid, created_at, updated_at) VALUES('opus', 'old-conv', 0, 0)")
    con.commit()
    con.close()
    monkeypatch.setattr(config, "DB_PATH", old)
    db.init()
    with db.tx() as c2:
        r = db.row(c2, "SELECT claude_sid, prompt_sig, detail FROM session")
    assert r == {"claude_sid": "old-conv", "prompt_sig": None, "detail": "auto"}


def test_judge_gets_the_question_that_was_asked_when_two_share_concept_target_rel():
    from server import judge
    db.init()
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO session(id, title, model, created_at, updated_at) VALUES(72,'t','opus',0,0)")
        a, b = tutor.save_checks(con, 72, 720, [
            {"q": "古いほうの問い", "a": "古いほうの想定", "concept": "X", "target": "Y", "rel": "related", "type": "もしも"},
            {"q": "新しいほうの問い", "a": "新しいほうの想定", "concept": "X", "target": "Y", "rel": "related", "type": "当てはめ"}])
    g = [{"concept": "X", "target": "Y", "rel": "related", "result": "hit"}]
    asked = judge.build_input(72, g, "答え", a["id"])   # 戻ったときに出したのは古いほう（return_check は古い順）
    assert "問い: 古いほうの問い" in asked and "想定の答え: 古いほうの想定" in asked and "新しいほう" not in asked
    assert "問い: 新しいほうの問い" in judge.build_input(72, g, "答え")   # 問いの決まらない往復は、同じ組の新しい問い
    other = [{"concept": "別", "target": "組", "rel": "broader", "result": "hit"}]
    assert "問い: 古いほうの問い" in judge.build_input(72, other, "答え", a["id"])   # 判定の組が問いと違っても、答えた問いを渡す
