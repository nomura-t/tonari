"""全体の地図の規則の検査（v0.6）。読み出し（話題に出てきた言葉だけ）と、置き場所（話題ごとに島が1つ・話題をまたぐ言葉は
出てくる島ごとに置いて橋で結ぶ・同じ記録なら同じ地図・札が重ならない・島は動かない）。材料はどれも作り物で、
ここだけの記録の置き場に作る。"""
import json
import os
import sqlite3
import tempfile

os.environ.setdefault("TONARI_DATA_DIR", tempfile.mkdtemp(prefix="tonari-test-"))
os.environ.setdefault("TONARI_RECORDER", "off")

from server import atlas, db, tutor  # noqa: E402


def _fresh():
    con = sqlite3.connect(os.path.join(tempfile.mkdtemp(prefix="tonari-atlas-"), "t.db"))
    con.row_factory = sqlite3.Row
    con.executescript(db.SCHEMA)
    for table, col, sql in db.MIGRATIONS:
        if col not in {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}:
            con.execute(sql)
    return con


def _topic(con, title):
    return con.execute("INSERT INTO session(title, model, created_at, updated_at) VALUES(?,?,?,?)", (title, "opus", 0, 0)).lastrowid


def _answer(con, sid, m):
    """1往復ぶん: 往復を足し、答えの地図を記録に入れ、その中心を往復に書く。"""
    seq = con.execute("SELECT COUNT(*) FROM turn WHERE session_id=?", (sid,)).fetchone()[0] + 1
    tid = con.execute("INSERT INTO turn(session_id, seq, via, status, created_at, final_text) VALUES(?,?,?,?,?,?)",
                      (sid, seq, "text", "done", 0, "問い")).lastrowid
    center = tutor.merge_map(con, sid, tid, m)
    con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (json.dumps({"center": center}), tid))
    return center


def _world():
    """作り物の記録。A と B は「倉庫」を共有し、C は離れていて、D は A の言葉を聞き直しただけ、E は言葉が無い。"""
    con = _fresh()
    a, b, c, d, e = (_topic(con, t) for t in ("受付のしごと", "配達のながれ", "会計のきほん", "受付をもう一度", "まだ何も聞いていない"))
    _answer(con, a, {"center": "受付", "gist": "頼みを受け取る役", "src": "一般",
                     "broader": [{"label": "窓口", "src": "一般"}],
                     "narrower": [{"label": "総合受付", "src": "一般"}, {"label": "夜間受付", "src": "一般"}],
                     "opposite": [{"label": "倉庫番", "axis": "持ち場", "src": "一般"}],
                     "related": [{"label": "倉庫", "rel": "道具", "link": "から品物を出す", "src": "一般"},
                                 {"label": "番号札", "rel": "部分", "src": "一般"}],
                     "examples": ["来た人に番号札を渡す場面"], "nonexamples": ["棚卸しの作業"]})
    _answer(con, a, {"center": "倉庫", "gist": "品物を置く所", "src": "一般",
                     "narrower": [{"label": "冷蔵倉庫", "src": "一般"}],
                     "related": [{"label": "棚", "rel": "部分", "src": "一般"}, {"label": "在庫表", "rel": "道具", "src": "一般"},
                                 {"label": "番号札", "rel": "結果", "src": "一般"}]})
    _answer(con, b, {"center": "配達", "gist": "品物を届ける", "src": "一般",
                     "related": [{"label": "倉庫", "rel": "前提", "src": "一般"}, {"label": "トラック", "rel": "道具", "src": "一般"}]})
    _answer(con, c, {"center": "会計", "gist": "お金を数える", "src": "一般",
                     "narrower": [{"label": "現金", "src": "一般"}, {"label": "掛け", "src": "一般"}]})
    _answer(con, d, {"center": "受付", "gist": "頼みを受け取る役", "src": "一般",
                     "related": [{"label": "番号札", "rel": "部分", "src": "一般"}]})
    con.commit()
    return con, (a, b, c, d, e)


def _boxes(lay):
    """札の四角（左・上・右・下）。行の送りより少し低い。"""
    return {k: (x, y - atlas.ROW / 2 + 2, x + w, y + atlas.ROW / 2 - 2) for k, (x, y, w) in lay["places"].items()}


def _hit(p, q):
    return p[0] < q[2] and q[0] < p[2] and p[1] < q[3] and q[1] < p[3]


def _rect(i, drawn=False):
    return (i["bx"], i["by"], i["bx"] + i["bw"], i["by"] + i["bh"]) if drawn else (i["x"], i["y"], i["x"] + i["w"], i["y"] + i["h"])


def test_graph_takes_only_words_of_topics():
    con, (a, b, c, d, e) = _world()
    g = atlas.graph(con)
    labels = {n["label"]: n for n in g["nodes"]}
    assert "来た人に番号札を渡す場面" not in labels and "棚卸しの作業" not in labels      # 例と非例の文は地図に出さない
    assert len(labels) == len(g["nodes"]) == 15
    assert labels["倉庫"]["topics"] == [a, b] and labels["受付"]["topics"] == [a, d]
    assert labels["受付"]["hub"] == 2 and labels["倉庫"]["hub"] == 1 and labels["棚"]["hub"] == 0
    assert all(x["rel"] in ("broader", "opposite", "related") for x in g["edges"])
    assert g["counts"]["topics"] == 4 and g["counts"]["empty_topics"] == 1 and g["counts"]["shared"] == 3
    by = {t["id"]: t for t in g["topics"]}
    assert e not in by                                                                    # 言葉の無い話題は地図に出ない
    assert by[a]["hubs"] == [labels["受付"]["id"], labels["倉庫"]["id"]] and by[b]["hubs"] == [labels["配達"]["id"]]
    assert set(by[d]["concepts"]) == {labels["受付"]["id"], labels["番号札"]["id"]}


def test_every_topic_is_one_island_and_shared_words_sit_in_each_island_joined_by_bridges():
    con, (a, b, c, d, e) = _world()
    g = atlas.graph(con)
    lay = atlas.layout(g)
    assert [i["topic"] for i in lay["islands"]] == [a, b, c, d]         # 言葉がどれも A で先に出ている D にも、島が1つある
    label = {n["id"]: n["label"] for n in g["nodes"]}
    where = {}
    for k in lay["places"]:
        t, cid = (int(x) for x in k.split(":"))
        where.setdefault(label[cid], []).append(t)
    assert sorted(where["倉庫"]) == [a, b] and sorted(where["受付"]) == [a, d] and sorted(where["番号札"]) == [a, d]
    assert where["棚"] == [a] and len(lay["places"]) == sum(len(t["concepts"]) for t in g["topics"])
    names = {(x["a"], x["b"]): sorted(label[cid] for cid in x["concepts"]) for x in lay["bridges"]}
    assert names == {(a, b): ["倉庫"], (a, d): ["受付", "番号札"]}                        # 橋は、同じ言葉が出てくる島の組
    # 札は、自分の島の四角の中の、名前の行より下にある（飛び地を作らない・名前に重ねない）
    isl = {i["topic"]: i for i in lay["islands"]}
    for k, (x, y, w) in lay["places"].items():
        i = isl[int(k.split(":")[0])]
        assert i["bx"] <= x and x + w <= i["bx"] + i["bw"] and i["by"] + atlas.PAD + atlas.TITLE_H <= y - atlas.ROW / 2 + 0.01
        assert y + atlas.ROW / 2 <= i["by"] + i["bh"]


def test_inside_an_island_the_words_form_trees_with_the_hierarchy_as_bones():
    con, (a, b, c, d, e) = _world()
    g = atlas.graph(con)
    lay = atlas.layout(g)
    assert len(lay["links"]) == len(lay["places"]) - lay["trees"]
    label = {n["id"]: n["label"] for n in g["nodes"]}
    rel = {x["id"]: x for x in g["edges"]}
    in_a = [x for x in g["edges"] if all(f"{a}:{cid}" in lay["places"] for cid in (x["src"], x["dst"]))]
    used = {rid for rid, p, _ in lay["links"] if p.startswith(f"{a}:")} | {rid for rid, p, _ in lay["cross"] if p.startswith(f"{a}:")}
    assert used == {x["id"] for x in in_a}                                               # 島の中の関係は、骨か細い線のどちらかに必ず出る
    bones = {rid for rid, _, _ in lay["links"]}
    assert all(x["id"] in bones for x in in_a if x["rel"] == "broader")                   # 上位・下位は必ず骨に入る
    par = {c_: p for _, p, c_ in lay["links"]}
    uke = next(i for i, l in label.items() if l == "受付")
    assert label[int(par[f"{a}:{uke}"].split(":")[1])] == "窓口"                          # 広い言葉が根の側に来る
    assert f"{d}:{uke}" not in par                                                        # D の島では、受付が根
    for _, p, c_ in lay["links"]:                                                         # 子は親の札の右端より右
        assert lay["places"][c_][0] >= lay["places"][p][0] + lay["places"][p][2] + atlas.GAPX - 0.01
    assert any(rel[rid]["rel"] == "related" for rid, _, _ in lay["cross"])                # 輪になる関係（倉庫と番号札）は細い線


def test_cards_never_overlap_and_islands_never_overlap():
    con, _ = _world()
    lay = atlas.layout(atlas.graph(con))
    boxes = list(_boxes(lay).values())
    for i, p in enumerate(boxes):
        assert not any(_hit(p, q) for q in boxes[i + 1:])
    isl = [_rect(i) for i in lay["islands"]]
    for i, p in enumerate(isl):
        assert not any(_hit(p, q) for q in isl[i + 1:])


def test_same_record_gives_the_same_map():
    con, _ = _world()
    con2, _ = _world()
    g = atlas.graph(con)
    assert atlas.layout(g) == atlas.layout(g) == atlas.layout(atlas.graph(con2))


def test_adding_a_word_does_not_move_other_islands():
    con, (a, b, c, d, e) = _world()
    lay = atlas.layout(atlas.graph(con))
    # C に言葉を1つ足す。前の置き場所を渡せば、ほかの島も、ほかの島の札も、1つも動かない
    _answer(con, c, {"center": "会計", "src": "一般", "narrower": [{"label": "手形", "src": "一般"}]})
    lay2 = atlas.layout(atlas.graph(con), lay["anchors"])
    assert all(lay2["anchors"][k] == v for k, v in lay["anchors"].items() if k != str(c))
    assert all(lay2["places"][k] == v for k, v in lay["places"].items() if not k.startswith(f"{c}:"))
    assert f"{c}:" in "".join(lay2["places"]) and len(lay2["places"]) == len(lay["places"]) + 1
    # A に言葉をたくさん足して島を大きくする。前の置き場所を渡せば、A の島は同じ所から広がり、重ならなかった島は動かない
    _answer(con, a, {"center": "受付", "src": "一般",
                     "narrower": [{"label": f"受付の種類{i}", "src": "一般"} for i in range(5)],
                     "related": [{"label": f"受付の道具{i}", "rel": "道具", "src": "一般"} for i in range(6)]})
    lay3 = atlas.layout(atlas.graph(con), lay2["anchors"])
    assert lay3["anchors"][str(a)] == lay2["anchors"][str(a)]
    grown = next(i for i in lay3["islands"] if i["topic"] == a)
    before = {i["topic"]: i for i in lay2["islands"]}
    assert (grown["w"], grown["h"]) != (before[a]["w"], before[a]["h"])
    for i in lay3["islands"]:
        if i["topic"] != a and not _hit(_rect(grown), _rect(before[i["topic"]])):
            assert lay3["anchors"][str(i["topic"])] == lay2["anchors"][str(i["topic"])]
    isl = [_rect(i) for i in lay3["islands"]]
    for i, p in enumerate(isl):
        assert not any(_hit(p, q) for q in isl[i + 1:])


def test_a_new_shared_word_adds_a_bridge_without_moving_the_islands():
    con, (a, b, c, d, e) = _world()
    lay = atlas.layout(atlas.graph(con))
    _answer(con, c, {"center": "会計", "src": "一般", "related": [{"label": "倉庫", "rel": "道具", "src": "一般"}]})
    g2 = atlas.graph(con)
    lay2 = atlas.layout(g2, lay["anchors"])
    assert [i["topic"] for i in lay2["islands"]] == [a, b, c, d]         # 島は話題ごとのまま
    assert all(lay2["anchors"][k] == v for k, v in lay["anchors"].items() if k != str(c))   # 言葉が増えた C のほかは動かない
    assert {(x["a"], x["b"]) for x in lay2["bridges"]} == {(a, b), (a, c), (a, d), (b, c)}
    isl = [_rect(i) for i in lay2["islands"]]
    for i, p in enumerate(isl):
        assert not any(_hit(p, q) for q in isl[i + 1:])


def test_topics_that_share_words_are_placed_next_to_each_other():
    # 1 と 5 が言葉を共有し、2〜4 は関係が無い。5 は 1 のすぐ隣に置かれる（あいだに無関係の島を挟まない）
    w, h = atlas.QW * 3, atlas.QH * 3
    share = {1: {5: 2}, 5: {1: 2}}
    at = atlas._pack([(k, w, h) for k in range(1, 6)], {}, share)
    assert at[5] == atlas._pack([(1, w, h), (5, w, h)], {}, share)[5]    # 無関係の島より先に、いちばん近い空きを取る
    touch = (abs(at[5][0] - at[1][0]) == w and at[5][1] == at[1][1]) or (abs(at[5][1] - at[1][1]) == h and at[5][0] == at[1][0])
    assert touch
    # 言葉の多い共有から先に寄せる
    share = {1: {3: 1, 4: 5}, 3: {1: 1}, 4: {1: 5}}
    at = atlas._pack([(k, w, h) for k in range(1, 5)], {}, share)
    assert at[4] == atlas._pack([(1, w, h), (4, w, h)], {}, share)[4]


def test_a_new_island_goes_near_the_island_it_shares_words_with():
    w, h = atlas.QW * 3, atlas.QH * 3
    prev = {"1": [0.0, 0.0], "2": [atlas.QW * 40, 0.0]}
    at = atlas._pack([(1, w, h), (2, w, h), (3, w, h)], prev, {3: {2: 2}, 2: {3: 2}})
    assert at[1] == (0.0, 0.0) and at[2] == (atlas.QW * 40, 0.0)
    assert abs(at[3][0] - at[2][0]) < abs(at[3][0] - at[1][0])           # 言葉を共有する島のそばに置く
    alone = atlas._pack([(1, w, h), (2, w, h), (3, w, h)], prev, {})
    assert abs(alone[3][0] - alone[1][0]) < abs(alone[3][0] - alone[2][0])   # 共有が無ければ、真ん中の近く


def test_empty_record_gives_an_empty_map():
    con = _fresh()
    g = atlas.graph(con)
    assert g["nodes"] == [] and g["topics"] == []
    lay = atlas.layout(g)
    assert lay["places"] == {} and lay["islands"] == [] and lay["bridges"] == []


def test_many_islands_pack_without_overlap_and_stay_when_one_is_added():
    items = [(i + 1, atlas.QW * (2 + i % 4), atlas.QH * (2 + i % 3)) for i in range(40)]
    at = atlas._pack(items, {})
    rects = [(at[k][0], at[k][1], at[k][0] + w, at[k][1] + h) for k, w, h in items]
    for i, p in enumerate(rects):
        assert not any(_hit(p, q) for q in rects[i + 1:])
    prev = {str(k): list(v) for k, v in at.items()}
    at2 = atlas._pack(items + [(41, atlas.QW * 3, atlas.QH * 3)], prev)
    assert all(at2[k] == at[k] for k in at)                               # 足しても、前からある島は動かない
    assert atlas._pack(items, {}) == at


def test_packing_many_islands_stays_fast():
    # 置き場所の計算はサーバーの中で回るので、話題が増えても待たせない（空きの確かめを、島の数に依らない手間にしてある）
    import time
    items = [(i + 1, atlas.QW * (2 + i % 5), atlas.QH * (2 + i % 4)) for i in range(100)]
    share = {i + 1: {i + 2: 1} for i in range(0, 98, 3)}
    t0 = time.time()
    at = atlas._pack(items, {}, share)
    assert time.time() - t0 < 4.0, time.time() - t0     # 手元では 100の話題で 0.7秒・200で 2.7秒（最初に開くときと並べ直しのときだけ。開き直しは 0.02秒）
    rects = sorted((at[k][0], at[k][1], at[k][0] + w, at[k][1] + h) for k, w, h in items)
    for i, p in enumerate(rects):
        assert not any(_hit(p, q) for q in rects[i + 1:i + 60] if q[0] < p[2])


def test_long_labels_are_cut_for_the_card():
    assert atlas.short("あ" * 30) == "あ" * 15 + "…" and atlas.short("受付") == "受付"
    assert atlas.node_w("あ" * 30, False) == atlas.node_w("あ" * 15 + "…", False)
    assert atlas.text_w("abc") < atlas.text_w("あいう")
