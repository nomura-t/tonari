"""v0.5 の規則の検査（話の間合い・考えの塊・記録役・つなぐ言葉・Web で調べたページの照らし）。本物の claude も Web も使わない。"""
import asyncio
import json
import os
import tempfile

os.environ.setdefault("TONARI_DATA_DIR", tempfile.mkdtemp(prefix="tonari-test-"))
os.environ.setdefault("TONARI_RECORDER", "off")

from server import config, corpus, db, graph, pipeline, recorder, research, tutor  # noqa: E402


def _blk(kind, d):
    return f"```tonari-{kind}\n{json.dumps(d, ensure_ascii=False)}\n```"


# ── 考えの塊と、調べる入口 ──
def test_think_block_is_a_side_view_and_not_prose():
    md = ("事実の段落。\n\n```tonari-think\n種類: 仮定\n利用者は1人だと置きます。\n```\n\n"
          "```tonari-think\n思うに、たぶんこうです。\n```\n\n" + _blk("lookup", {"q": "Python の最新の安定版はいくつか", "why": "版は変わるため"}))
    b = tutor.parse_blocks(md)
    kinds = [(v["type"], v["kind"]) for v in b["views"]]
    assert kinds == [("think", "仮定"), ("think", "推測")]            # 種類が無い塊は「推測」（事実として出さない側）
    assert b["views"][0]["md"] == "利用者は1人だと置きます。"
    assert tutor.main_view(b["views"]) is None                        # 図には数えない
    assert tutor.strip_blocks(md) == "事実の段落。"                    # 字数の目安と確かめの問いの照らしに入らない
    assert b["lookup"] == {"q": "Python の最新の安定版はいくつか", "why": "版は変わるため"}
    assert "tonari-lookup" not in b["text"] and b["text"].count("[[view:") == 2


def test_think_blocks_are_capped_at_three_and_empty_is_dropped():
    md = "\n\n".join(f"```tonari-think\n種類: 推測\n考え{i}\n```" for i in range(5)) + "\n\n```tonari-think\n種類: 推測\n```"
    b = tutor.parse_blocks(md)
    assert len(b["views"]) == 3 and sum("4つ目から" in e for e in b["errors"]) == 2 and any("中身が空" in e for e in b["errors"])


# ── 話の間合い ──
def test_detail_plan_is_decided_by_fixed_rules():
    db.init()
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO session(id, title, model, created_at, updated_at) VALUES(80,'t','opus',0,0)")
    P = lambda text, kind="question", detail="auto", ref=None: tutor.detail_plan(80, text, kind, detail, ref)["chars"]  # noqa: E731
    assert P("キャッシュって何？") == tutor.BUDGET["talk"] == 250
    assert P("TLS のハンドシェイクを詳しく教えて") == tutor.BUDGET["deep"]
    assert P("一言で言うと何？") == tutor.BUDGET["word"] and P("ざっくり教えて") == tutor.BUDGET["word"]
    assert P("要するに写しを返すってことですよね", kind="confirm") == tutor.BUDGET["grade"]   # 判定の返しは語より先に決める
    for said in ("TTL を短くするとどうなる？", "もっと速くする方法はある？", "全部で何種類ある？", "詳細設計とは何？", "簡単に実装できる？"):
        assert P(said) == tutor.BUDGET["talk"], said                                       # 中身の語には当てない
    assert P("続きを。直前の答えで省いた点を、同じくらいの長さで（前の答えの中身は繰り返さない）") == tutor.BUDGET["talk"]
    assert P("あ" * 201) == tutor.BUDGET["mid"]
    assert P("キャッシュって何？", detail="short") == tutor.BUDGET["word"] and P("x", detail="long") == tutor.BUDGET["long"]
    assert P("別の見せ方で", ref={"name": "流れ", "type": "flow"}) == tutor.BUDGET["talk"]
    c = tutor.turn_content(80, "キャッシュって何？", "question", "text", [])
    assert "<詳しさ>本文の目安 250字（会話の間合い" in c
    with db.tx() as con:   # この話題で続けて詳しくを頼んでいたら、頼まれなくても中くらいにする
        for i, t in enumerate(["もっと詳しく", "そこを詳しく教えて"], 1):
            con.execute("INSERT INTO turn(session_id, seq, via, status, created_at, final_text) VALUES(80,?,'text','done',0,?)", (i, t))
    assert P("では TTL は？") == tutor.BUDGET["mid"]


def test_system_prompt_no_longer_asks_the_tutor_for_checks_or_the_record_map():
    s = tutor.SYSTEM
    assert "```tonari-check``` [" not in s and '"show"' not in s and "あとで、いまの話をあなたの言葉で説明してもらいます" not in s
    assert "tonari-think" in s and "tonari-lookup" in s and "同時に出る・似ている のどれか" not in s
    assert "tonari-check" in recorder.SYSTEM and "link" in recorder.SYSTEM


# ── つなぐ言葉と、位置の図の向き ──
def test_link_phrases_that_say_nothing_are_dropped():
    assert tutor.clean_link("に問い合わせる。") == "に問い合わせる"
    for bad in ("と関係がある", "同時に出る", "と似ている", "に関連する", "", "あ" * 19, None):
        assert tutor.clean_link(bad) is None


def test_relation_keeps_its_phrase_and_ego_tells_the_direction():
    db.init()
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO session(id, title, model, created_at, updated_at) VALUES(81,'t','opus',0,0)")
        c = tutor.merge_map(con, 81, 1, {"center": "キャッシュ層v05", "related": [
            {"label": "オリジン鯖v05", "rel": "", "link": "に問い合わせる", "why": "写しが無いとき", "src": "一般"},
            {"label": "保存領域v05", "rel": "部分", "link": "同時に出る", "src": "一般"}]})
        m = db.row(con, "SELECT id FROM concept WHERE label='オリジン鯖v05'")["id"]
        # 同じ関係を、つなぐ言葉なしでもう一度取り込んでも、前の言葉は消えない
        tutor.merge_map(con, 81, 2, {"center": "キャッシュ層v05", "related": [{"label": "オリジン鯖v05", "rel": "", "src": "一般"}]})
    out = {n["label"]: n for n in graph.ego(c)["related"]}
    assert out["オリジン鯖v05"]["phrase"] == "に問い合わせる" and out["オリジン鯖v05"]["out"] is True
    assert out["保存領域v05"]["phrase"] is None and out["保存領域v05"]["detail"] == "部分"
    back = {n["label"]: n for n in graph.ego(m)["related"]}
    assert back["キャッシュ層v05"]["out"] is False and back["キャッシュ層v05"]["phrase"] == "に問い合わせる"   # 相手の側から見ると向きが逆


def test_phrase_column_is_added_to_an_old_db(monkeypatch, tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.executescript(db.SCHEMA)
    con.commit()
    con.close()
    monkeypatch.setattr(config, "DB_PATH", p)
    db.init()
    with db.tx() as c2:
        assert "phrase" in {r["name"] for r in c2.execute("PRAGMA table_info(relation)").fetchall()}


# ── 記録役 ──
def test_recorder_output_keeps_only_the_blocks_that_were_asked_for():
    raw = ("前置き\n" + _blk("map", {"center": "キャッシュ", "show": True}) + "\n" + _blk("check", [{"q": "もしも？", "a": "止まる"}])
           + "\n" + _blk("map", {"center": "二つ目"}) + "\n" + _blk("analogy", {"x": 1}))
    both = recorder.pick_blocks(raw, True, True)
    b = tutor.parse_blocks(both)
    assert b["map"]["center"] == "キャッシュ" and b["map"]["show"] is False and b["views"] == [] and len(b["check"]) == 1
    only = recorder.pick_blocks(raw, False, True)
    assert "tonari-map" not in only and "tonari-check" in only
    assert recorder.pick_blocks("塊なし", True, True) == ""


def test_recorder_adds_the_map_and_checks_after_the_answer(monkeypatch):
    db.init()
    md = "キャッシュは、取り出しに時間のかかる結果を手元に置いておく仕組みです。次に同じものを頼まれたら、手元の写しを返します。"
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO session(id, title, model, created_at, updated_at) VALUES(82,'t','opus',0,0)")
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text, answer_md, stage_ms) "
                    "VALUES(820,82,1,'text','done',0,'キャッシュって何',?,'{\"rules\": 4}')", (md,))
    extra = (_blk("map", {"show": False, "center": "キャッシュv05", "gist": "結果を手元に置く仕組み", "src": "一般",
                          "related": [{"label": "オリジンv05", "rel": "", "link": "の写しを持つ", "src": "一般"}]}) + "\n\n"
             + _blk("check", [{"q": "もし写しを消さなかったらどうなるか", "a": "古い中身を返し続ける", "type": "もしも", "concept": "キャッシュv05",
                               "rel": "related", "target": "オリジンv05", "hints": ["元が変わったときを考える"]},
                              {"q": "何を手元に置くか", "a": "時間のかかる結果", "type": "見分け"}]))   # 2問目は本文の写しで答えられる

    async def fake(sid, said, m, need_map, need_check):
        assert need_map and need_check and m == md
        return extra
    monkeypatch.setattr(recorder, "record", fake)
    monkeypatch.setattr(config, "RECORDER", "on")
    asyncio.run(pipeline.run_recorder(820, 82, md, "キャッシュって何"))
    with db.tx() as con:
        t = db.row(con, "SELECT answer_md, stage_ms FROM turn WHERE id=820")
        qs = db.rows(con, "SELECT q FROM checkq WHERE turn_id=820")
        rel = db.row(con, "SELECT phrase FROM relation WHERE turn_id=820")
    st = json.loads(t["stage_ms"])
    assert t["answer_md"].startswith(md) and "tonari-map" in t["answer_md"]
    assert st["recorded"] == {"map": True, "checks": 1} and st["center"] and "recorder" in st
    assert [q["q"] for q in qs] == ["もし写しを消さなかったらどうなるか"] and rel["phrase"] == "の写しを持つ"
    assert any("確かめの問いを外した" in e for e in st["block_errors"])
    assert tutor.turn_blocks(t["answer_md"], st)["views"] == []      # 記録用の地図は画面に出ない

    async def boom(*a):
        raise RuntimeError("取れない")
    with db.tx() as con:
        con.execute("INSERT INTO turn(id, session_id, seq, via, status, created_at, final_text, answer_md, stage_ms) "
                    "VALUES(821,82,2,'text','done',0,'q',?,'{}')", (md,))
    monkeypatch.setattr(recorder, "record", boom)
    asyncio.run(pipeline.run_recorder(821, 82, md, "q"))
    with db.tx() as con:
        t = db.row(con, "SELECT answer_md, stage_ms FROM turn WHERE id=821")
    assert t["answer_md"] == md and "recorder_error" in json.loads(t["stage_ms"])   # 取れなくても答えは残る


def test_recorder_is_skipped_when_the_tutor_wrote_both_blocks(monkeypatch):
    called = []

    async def fake(*a):
        called.append(a)
        return ""
    monkeypatch.setattr(recorder, "record", fake)
    monkeypatch.setattr(config, "RECORDER", "on")
    md = "古い指示の答え。" * 8 + _blk("map", {"center": "x", "show": False}) + _blk("check", [{"q": "q", "a": "a"}])
    asyncio.run(pipeline.run_recorder(999999, 82, md, "q"))
    assert called == []


# ── Web で調べたページ ──
PAGE_RAW = "```tonari-page\n" + json.dumps({
    "title": "Python 3.14 の公開日", "answer": "3.14.0 は 2025年10月7日に出た [1]。次は 3.15 の予定 [3]。関係ない番号 [9]。",
    "sections": [{"h": "公開日", "body": "公式の公開ページに日付がある [1]。"}],
    "claims": [{"n": 1, "text": "Python 3.14.0 は 2025-10-07 に公開された", "url": "https://www.python.org/downloads/release/python-3140/",
                "quote": "Release date: Oct. 7, 2025", "kind": "一次"},
               {"n": 3, "text": "3.15 は 2026年10月の予定", "url": "https://peps.python.org/pep-0790/", "quote": "3.15.0 final: “Thursday”, 2026-10-01", "kind": "一次"},
               {"n": 4, "text": "内向きの番地の主張", "url": "http://127.0.0.1:4880/api/state", "quote": "sessions sessions", "kind": "個人"},
               {"n": 5, "text": "引用が違う主張", "url": "https://example.com/a", "quote": "this sentence is not on the page", "kind": "へん"}],
    "guesses": [{"text": "3.16 も同じ時期に出そうだ", "because": "毎年10月に出ているから"}], "open": ["3.15 の新機能の確定版は分からなかった"]},
    ensure_ascii=False) + "\n```"


def test_page_is_parsed_renumbered_and_unsafe_urls_are_dropped():
    p = research.parse_page(PAGE_RAW)
    assert [c["n"] for c in p["claims"]] == [1, 2, 3, 4]
    assert "[1]" in p["answer"] and "[2]" in p["answer"] and "[9]" not in p["answer"] and "[3]" not in p["answer"]
    assert p["claims"][2]["url"] == "" and p["claims"][3]["kind"] == "二次"
    assert research.parse_page("塊なし") is None and research.parse_page('```tonari-page\n{"title": "t", "claims": []}\n```') is None


def test_urls_to_this_machine_and_private_networks_are_refused():
    for bad in ("http://127.0.0.1/", "http://localhost:4880/", "http://10.0.0.5/x", "http://192.168.1.1/", "http://169.254.169.254/latest",
                "file:///etc/passwd", "ftp://example.com/", "http://user:pw@example.com/", "http://[::1]/", "http://printer.local/", "nope"):
        assert research.url_shape_ok(bad) is False and research.safe_url(bad) is False, bad
    assert research.url_shape_ok("https://www.python.org/downloads/") and research.url_shape_ok("http://93.184.216.34/x")


def test_quote_is_matched_by_characters_ignoring_quote_marks_and_spaces():
    html = "<html><head><style>.x{}</style><script>var a='Release date: fake'</script></head><body><p>Release&nbsp;date: <b>Oct. 7,</b>\n 2025</p>" \
           "<p>3.15.0 final: \"Thursday\", 2026-10-01</p></body></html>"
    text = research.page_text(html)
    assert "fake" not in text
    assert research.find_quote("Release date: Oct. 7, 2025", text)[0]
    assert research.find_quote("3.15.0 final: “Thursday”, 2026-10-01", text)[0]        # 曲がった引用符の違いは無視する
    assert not research.find_quote("Release date: Oct. 8, 2025", text)[0]               # 字が違えば一致しない
    assert not research.find_quote("2025", text)[0]                                     # 短すぎる引用は照らさない


def test_verify_marks_each_claim_and_the_page_is_mixed_into_the_mirror(monkeypatch, tmp_path):
    page = research.parse_page(PAGE_RAW)
    pages = {"https://www.python.org/downloads/release/python-3140/": ("<p>Release date: Oct. 7, 2025</p>", ""),
             "https://peps.python.org/pep-0790/": ("<p>3.15.0 final: \"Thursday\", 2026-10-01 (expected)</p>", ""),
             "https://example.com/a": ("<p>nothing here</p>", "")}

    async def fetcher(url):
        body, why = pages.get(url, (None, "HTTP 404"))
        return (research.page_text(body) if body else None), why

    async def checker(found):
        assert [c["n"] for c in found] == [1, 2] and all(c["context"] for c in found)
        return ["ok", "partial"]
    page = asyncio.run(research.verify(page, fetcher, checker))
    assert [c["status"] for c in page["claims"]] == ["ok", "weak", "unreachable", "not_found"]
    assert page["counts"] == {"ok": 1, "weak": 1, "quote_only": 0, "not_found": 1, "unreachable": 1}
    assert all("context" not in c for c in page["claims"])
    page.update(id="web-20261113-abc123", question="Python のいちばん新しい安定版は", at="2026-11-13 10:00")
    monkeypatch.setattr(research, "PAGES_DIR", tmp_path / "pages")
    monkeypatch.setattr(config, "CORPUS_DIR", tmp_path / "corpus")
    monkeypatch.setattr(config, "SHELF_LIB", tmp_path / "no-shelf")
    (tmp_path / "corpus").mkdir()
    research.save(page)
    assert research.load("web-20261113-abc123")["title"] == "Python 3.14 の公開日" and research.load("../x") is None
    info = corpus.refresh()                                  # 棚が無い PC でも、調べたページは写しに入る
    assert info["web"] == 1 and "error" not in info
    txt = (tmp_path / "corpus" / "web-20261113-abc123.txt").read_text(encoding="utf-8")
    assert "［引用が主張を支えている・一次］" in txt and "未照合（ページを取れなかった）" in txt and "## 調べ役の推測（事実ではない）" in txt
    assert "web-20261113-abc123｜Python 3.14 の公開日｜Web調べ" in corpus.catalog()
    s = research.summary_md(page)
    assert "主張 4 のうち、出どころの引用が支えている 1・支えきれていない 1・未照合 2。〔web-20261113-abc123｜Python 3.14 の公開日〕" in s
    assert corpus.cards(s)[0]["known"] is True
    assert corpus.check_quotes("ページには「Release date: Oct. 7, 2025」とある")[0]["found"] == "web-20261113-abc123"


def test_checker_failure_leaves_the_claim_as_quote_only():
    page = research.parse_page(PAGE_RAW)
    page["claims"] = page["claims"][:1]

    async def fetcher(url):
        return "Release date: Oct. 7, 2025", ""

    async def checker(found):
        raise RuntimeError("取れない")
    page = asyncio.run(research.verify(page, fetcher, checker))
    assert page["claims"][0]["status"] == "quote_only"


def test_checker_output_with_a_correction_uses_the_last_block():
    raw = '{"results": ["ok", "ng"]}\n\nWait, 2 is ok.\n\n{"results": ["ok", "partial"]}'
    assert research.parse_check(raw, 2) == ["ok", "partial"]
    assert research.parse_check('```json\n{"results": ["ok"]}\n```', 1) == ["ok"]
    assert research.parse_check('{"results": ["ok"]}', 2) == [None, None] and research.parse_check("読めない", 1) == [None]
