"""コードの塊・読むコード・構成の図・ファイルの木の規則の検査（v0.7・DESIGN 18章）。本物の claude は使わない。材料は作り物。"""
import json
import os
import random
import tempfile
import time

os.environ.setdefault("TONARI_DATA_DIR", tempfile.mkdtemp(prefix="tonari-test-"))
os.environ.setdefault("TONARI_RECORDER", "off")

from fastapi.testclient import TestClient  # noqa: E402

from server import app as appmod, arch, db, tutor  # noqa: E402
from tests import usage_stats  # noqa: E402

H = {"X-Tonari": "1"}

PY = "def logged(fn):\n    def wrapper(*args, **kwargs):\n        print(\"start\", fn.__name__)\n\n        result = fn(*args, **kwargs)\n        return result\n    return wrapper\n\n\n@logged\ndef add(a, b):\n    return a + b"


def test_a_plain_code_fence_becomes_a_view_and_keeps_its_blank_lines():
    md = f"最初の段落です。\n\n```python\n{PY}\n```\n\n説明の段落です。"
    b = tutor.parse_blocks(md)
    assert [v["type"] for v in b["views"]] == ["code"] and b["errors"] == []
    v = b["views"][0]
    assert v["lang"] == "python" and v["name"] == "コード" and v["notes"] == []
    assert v["code"] == PY                                   # 空行が2つ続く所も、そのまま（本文の空行の詰めに巻き込まれない）
    assert b["text"] == "最初の段落です。\n\n[[view:0]]\n\n説明の段落です。"
    assert tutor.strip_blocks(md) == "最初の段落です。\n\n\n\n説明の段落です。".replace("\n\n\n\n", "\n\n\n\n")
    assert "def logged" not in tutor.strip_blocks(md)         # 字数の目安と本文との照らしに、コードは入らない
    assert tutor.main_view(b["views"]) is None                # コードは図に数えない


def test_code_languages_are_normalised_and_a_fence_without_a_language_is_plain_text():
    for raw, want in (("py", "python"), ("TS", "typescript"), ("sh", "bash"), ("console", "console"), ("c++", "cpp"),
                      ("", ""), ("text", ""), ("rust", "rust"), ("yml", "yaml")):
        b = tutor.parse_blocks(f"前。\n\n```{raw}\nx = 1\n```\n")
        assert b["views"][0]["lang"] == want, raw


def test_a_fence_only_closes_on_a_line_of_its_own():
    md = "```markdown\n本文に ``` を書く例です。\n次の行。\n```\n\nあと。"
    b = tutor.parse_blocks(md)
    assert b["views"][0]["code"] == "本文に ``` を書く例です。\n次の行。" and b["text"] == "[[view:0]]\n\nあと。"
    # 行の途中から始まる ``` は、コードの塊にしない（文の一部）
    assert tutor.parse_blocks("記号の ``` は塊の区切りです。")["views"] == []
    # 中身が空の塊は出さない
    b = tutor.parse_blocks("前。\n\n```python\n\n```\n\nあと。")
    assert b["views"] == [] and b["errors"] == ["コード: 中身が空"]


def test_older_blocks_are_read_exactly_as_before():
    md = ("答えです。\n\n```tonari-flow\n{\"name\": \"流れ\", \"why\": \"順番があるので\", \"steps\": [{\"label\": \"一\"}, {\"label\": \"二\"}]}```\n\n"
          "```mermaid\n%% name: 関係の図 | why: 網なので\nflowchart LR\n  A --> B\n```\n\n```js\nconst a = 1;\n```")
    b = tutor.parse_blocks(md)
    assert [v["type"] for v in b["views"]] == ["flow", "mermaid", "code"]     # 閉じが行の途中の塊も、前のとおり読む
    assert tutor.main_view(b["views"])["type"] == "flow"
    assert tutor.strip_blocks(md) == "答えです。"


def test_too_many_or_too_long_code_blocks():
    md = "\n\n".join(f"```python\nx = {i}\n```" for i in range(tutor.CODE_MAX + 1))
    b = tutor.parse_blocks(md)
    assert len(b["views"]) == tutor.CODE_MAX and b["errors"] == [f"コード: {tutor.CODE_MAX + 1}つ目からのコードの塊"]
    long = "\n".join(f"line{i}" for i in range(tutor.CODE_LINES + 20))
    v = tutor.parse_blocks(f"```\n{long}\n```")["views"][0]
    assert v["cut"] is True and v["code"].count("\n") == tutor.CODE_LINES - 1


READING = f"""```tonari-code
lang: py
title: 呼び出しの前後に処理を足す
why: 3つのまとまりに分かれるので
---
{PY}
---
def wrapper(*args, **kwargs):〜return result｜包む関数を作る｜元の関数の前後に処理を足す関数を、中で作ります。
return wrapper｜包んだ関数を返す｜logged は wrapper そのものを返します。
@logged｜付ける｜add = logged(add) と同じ意味です。
```"""


def test_reading_code_ties_each_note_to_lines_by_a_fragment_of_the_line():
    b = tutor.parse_blocks("デコレータは関数を包みます。\n\n" + READING + "\n\n説明。")
    assert b["errors"] == []
    v = b["views"][0]
    assert (v["type"], v["name"], v["lang"], v["title"], v["why"]) == ("code", "読むコード", "python", "呼び出しの前後に処理を足す", "3つのまとまりに分かれるので")
    assert v["code"] == PY
    assert [(n["from"], n["to"], n["label"]) for n in v["notes"]] == [(2, 6, "包む関数を作る"), (7, 7, "包んだ関数を返す"), (10, 10, "付ける")]
    assert v["notes"][0]["text"].startswith("元の関数の前後")


def test_a_note_that_cannot_be_tied_to_a_line_is_dropped_and_recorded():
    body = ("lang: python\n---\nx = load()\ny = x + 1\nprint(y)\n---\n"
            "y  =  x+1｜足す｜空白の数が違っても結ぶ。\n"                 # 空白の違いは無視
            "z = 0｜無い行｜コードに無い字なので捨てる。\n"
            "3｜行の番号｜番号では結ばない。\n"
            "print(y)｜｜見出しは空でもよい。\n"
            "x = load()｜読む｜\n")                                        # 説明が空
    v, bad = tutor.reading_code(body)
    assert [(n["from"], n["to"], n["label"]) for n in v["notes"]] == [(2, 2, "足す"), (3, 3, "")]
    assert bad == ["注釈を捨てた（コードの行に結べない: z = 0）", "注釈を捨てた（コードの行に結べない: 3）", "注釈を捨てた（説明が空: 読む）"]
    b = tutor.parse_blocks("```tonari-code\n" + body + "```")
    assert b["errors"] == ["tonari-code: 一部を捨てた（" + "・".join(bad) + "）"]


def test_reading_code_repeated_lines_notes_follow_the_order_of_the_code():
    body = "---\nopen()\nwork()\nclose()\nopen()\nwork()\nclose()\n---\nopen()｜開く1｜一回目。\nclose()｜閉じる1｜一回目。\nopen()｜開く2｜二回目。\nclose()｜閉じる2｜二回目。"
    v, bad = tutor.reading_code(body)
    assert bad == [] and [(n["from"], n["label"]) for n in v["notes"]] == [(1, "開く1"), (3, "閉じる1"), (4, "開く2"), (6, "閉じる2")]


def test_reading_code_without_notes_or_header_and_with_dashes_inside_the_code():
    v, bad = tutor.reading_code("x = 1\ny = 2")                                  # 頭も注釈も無い: 素のコードと同じ
    assert (v["name"], v["code"], v["notes"], v["lang"], bad) == ("コード", "x = 1\ny = 2", [], "", [])
    v, _ = tutor.reading_code("lang: yaml\n---\na: 1\n---\nb: 2")               # コードの中の --- は、コードのまま
    assert v["code"] == "a: 1\n---\nb: 2" and v["lang"] == "yaml" and v["notes"] == []
    v, _ = tutor.reading_code("lang: yaml\n---\na: 1\n---\nb: 2\n---\nb: 2｜二つ目｜二つ目の文書です。")
    assert v["code"] == "a: 1\n---\nb: 2" and [(n["from"], n["label"]) for n in v["notes"]] == [(3, "二つ目")]
    v, _ = tutor.reading_code("x = 1\n---\nx = 1｜代入｜x に 1 を入れます。")       # 頭なしで、コードと注釈
    assert v["code"] == "x = 1" and v["notes"][0]["from"] == 1
    v, bad = tutor.reading_code("lang: js\n---\nmain();\n---\nmain();｜呼ぶ｜ここで動き始めます。\n---\n")   # 注釈のあとを --- で閉じる書き方
    assert (v["code"], [(n["from"], n["label"]) for n in v["notes"]], bad) == ("main();", [(1, "呼ぶ")], [])
    assert tutor.reading_code("lang: python\n---\n\n")[0] is None


def test_a_reading_code_whose_fence_closes_inside_a_line_is_still_read():
    b = tutor.parse_blocks("```tonari-code\nlang: go\n---\nx := 1```\n\nあと。")
    assert b["views"][0]["code"] == "x := 1" and b["views"][0]["lang"] == "go"


# ── 構成の図 ──
WEB = {"name": "構成の図", "why": "使う向きが中身なので", "arrow": "使う", "src": "一般",
       "nodes": [{"id": "br", "label": "ブラウザ", "kind": "ui"}, {"id": "api", "label": "API サーバー", "kind": "service", "tech": "FastAPI"},
                 {"id": "db", "label": "DB", "kind": "store", "tech": "PostgreSQL"}, {"id": "cache", "label": "キャッシュ", "kind": "cache"},
                 {"id": "q", "label": "ジョブキュー", "kind": "queue"}, {"id": "w", "label": "ワーカー", "kind": "worker"}],
       "edges": [{"from": "br", "to": "api", "label": "HTTPS"}, {"from": "api", "to": "db", "label": "SQL"}, {"from": "api", "to": "cache"},
                 {"from": "api", "to": "q"}, {"from": "w", "to": "q"}, {"from": "w", "to": "db"}]}


def rows_of(v):
    return {n["label"]: n["row"] for n in v["nodes"]}


def test_arch_rows_put_the_user_above_what_it_uses():
    v, why = arch.check(WEB)
    assert why is None and "dropped" not in v
    r = rows_of(v)
    assert r["ブラウザ"] < r["API サーバー"] < r["DB"] and r["API サーバー"] < r["キャッシュ"] and r["ワーカー"] < r["ジョブキュー"]
    assert v["cycles"] == [] and not any(e.get("cyc") or e.get("up") or e.get("rev") for e in v["edges"])
    kinds = {n["label"]: n.get("kind") for n in v["nodes"]}
    assert kinds == {"ブラウザ": "ui", "API サーバー": "service", "DB": "store", "キャッシュ": "store", "ジョブキュー": "queue", "ワーカー": "service"}


def test_arch_drops_what_breaks_the_rules_and_says_so():
    d = {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "a", "label": "重なり"}, {"label": ""},
                   {"id": "long", "label": "名前ではなく文になってしまっている、とても長い箱の名前の例です"}],
         "edges": [{"from": "a", "to": "b"}, {"from": "a", "to": "b"}, {"from": "a", "to": "a"}, {"from": "a", "to": "zz"}, {"from": "B", "to": "A"}]}
    v, why = arch.check(d)
    assert why is None and [n["id"] for n in v["nodes"]] == ["a", "b"]
    assert [(e["from"], e["to"]) for e in v["edges"]] == [("a", "b"), ("b", "a")]      # 名前で指した線も同じ箱に結ぶ
    assert v["dropped"] == ["id が重なる箱（a）", "名前が空の箱", "名前でなく文の箱（31字）", "同じ向きの線の重なり", "自分から自分への線", "両端が箱に無い線"]
    assert arch.check({"nodes": [{"label": "A"}], "edges": []})[0] is None
    assert arch.check({"nodes": [{"label": "A"}, {"label": "B"}], "edges": []})[1].startswith("構成の図: 線が無い")
    many = {"nodes": [{"id": f"n{i}", "label": f"箱{i}"} for i in range(20)], "edges": [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(19)]}
    v, _ = arch.check(many)
    assert len(v["nodes"]) == arch.NODES_MAX and len(v["edges"]) == arch.NODES_MAX - 1 and "17個目からの箱（4つ）" in v["dropped"]


def test_arch_finds_cycles_in_the_drawing():
    d = {"nodes": [{"id": x, "label": x.upper()} for x in "abcde"],
         "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "a"}, {"from": "c", "to": "d"}, {"from": "d", "to": "e"}]}
    v, _ = arch.check(d)
    assert v["cycles"] == [["A", "B", "C"]]
    assert [(e["from"], e["to"]) for e in v["edges"] if e.get("cyc")] == [("a", "b"), ("b", "c"), ("c", "a")]
    assert [(e["from"], e["to"]) for e in v["edges"] if e.get("rev")] == [("c", "a")]   # 循環を閉じる線だけ、置き場所の向きを逆にする
    r = rows_of(v)
    assert r["A"] < r["B"] < r["C"] < r["D"] < r["E"]
    two = arch.check({"nodes": [{"label": "X"}, {"label": "Y"}], "edges": [{"from": "X", "to": "Y"}, {"from": "Y", "to": "X"}]})[0]
    assert two["cycles"] == [["X", "Y"]] and sum(1 for e in two["edges"] if e.get("rev")) == 1


LAYERS = {"layered": True, "groups": [{"id": "ui", "label": "画面の層"}, {"id": "app", "label": "アプリの層"}, {"id": "dom", "label": "ドメインの層"}],
          "nodes": [{"id": "v", "label": "View", "in": "ui"}, {"id": "uc", "label": "UseCase", "in": "app"}, {"id": "svc", "label": "Service", "in": "app"},
                    {"id": "e", "label": "Entity", "in": "dom"}, {"id": "x", "label": "外部の決済", "kind": "external"}, {"id": "u", "label": "利用者", "kind": "person"}],
          "edges": [{"from": "v", "to": "uc"}, {"from": "uc", "to": "svc"}, {"from": "svc", "to": "e"}, {"from": "e", "to": "v"},
                    {"from": "svc", "to": "x"}, {"from": "u", "to": "v"}]}


def test_arch_groups_stack_in_the_given_order_and_upward_lines_are_marked_only_when_layered():
    v, _ = arch.check(LAYERS)
    r = rows_of(v)
    assert r["利用者"] < r["View"] < r["UseCase"] < r["Service"] < r["Entity"] < r["外部の決済"]   # 入っていない箱: 使うだけなら上、ほかは下
    assert [(g["label"], g["rows"]) for g in v["groups"]] == [("画面の層", [1, 1]), ("アプリの層", [2, 3]), ("ドメインの層", [4, 4])]
    assert [(e["from"], e["to"]) for e in v["edges"] if e.get("up")] == [("e", "v")]            # 下の層から上の層へ
    assert v["layered"] is True and v["cycles"] == [["View", "UseCase", "Service", "Entity"]]
    free = arch.check({**LAYERS, "layered": False})[0]
    assert not any(e.get("up") for e in free["edges"]) and [e for e in free["edges"] if e.get("rev")][0]["from"] == "e"
    # まとまりが1つだけ・箱の無いまとまりは、層の決まりにしない
    one = arch.check({**LAYERS, "groups": LAYERS["groups"][:1] + [{"id": "none", "label": "空"}]})[0]
    assert one["layered"] is False and [g["label"] for g in one["groups"]] == ["画面の層"]


def test_arch_splits_a_row_with_more_than_five_boxes():
    d = {"nodes": [{"id": "top", "label": "入口"}] + [{"id": f"m{i}", "label": f"部品{i}"} for i in range(8)],
         "edges": [{"from": "top", "to": f"m{i}"} for i in range(8)]}
    v, _ = arch.check(d)
    per_row = {}
    for n in v["nodes"]:
        per_row.setdefault(n["row"], []).append(n["label"])
    assert max(len(x) for x in per_row.values()) <= arch.ROW_MAX and v["rows"] == 3


def overlap(a, b, gap=0):
    return a[0] < b[0] + b[2] + gap and b[0] < a[0] + a[2] + gap and a[1] < b[1] + b[3] + gap and b[1] < a[1] + a[3] + gap


def check_layout(v):
    lay = arch.layout(v)
    boxes = lay["nodes"]
    ids = list(boxes)
    for i in range(len(ids)):
        x, y, w, h = boxes[ids[i]]
        assert x >= 0 and y >= 0 and x + w <= lay["w"] + 0.5 and y + h <= lay["h"] + 0.5, (ids[i], boxes[ids[i]], lay["w"], lay["h"])
        for j in range(i + 1, len(ids)):
            assert not overlap(boxes[ids[i]], boxes[ids[j]], 4), (ids[i], ids[j])
    rows = {n["id"]: n["row"] for n in v["nodes"]}
    for a in ids:
        for b in ids:
            if rows[a] < rows[b]:
                assert boxes[a][1] + boxes[a][3] < boxes[b][1], (a, b)          # 上の段の箱は、下の段の箱より上
    assert len(lay["edges"]) == len(v["edges"])
    for e, p in zip(v["edges"], lay["edges"]):
        pts = p["pts"]
        assert len(pts) >= 2
        (x1, y1), (x2, y2) = pts[0], pts[-1]
        fx, fy, fw, fh = boxes[e["from"]]
        tx, ty, tw, th = boxes[e["to"]]
        assert fx - 0.5 <= x1 <= fx + fw + 0.5 and tx - 0.5 <= x2 <= tx + tw + 0.5, (e, pts)   # 線は、使う側の箱から出て使われる側の箱に入る
        if e.get("rev"):
            assert abs(y1 - fy) < 0.6 and abs(y2 - (ty + th)) < 0.6 and y2 < y1                 # 逆向きの線は、下の箱の上の辺から上の箱の下の辺へ
        else:
            assert abs(y1 - (fy + fh)) < 0.6 and abs(y2 - ty) < 0.6 and y1 < y2
    for e, p in zip(v["edges"], lay["edges"]):          # 線の名前は、図の左右の端からはみ出さない
        if "lab" in p:
            half = (arch.units(e["label"]) * arch.NFS + 8) / 2
            assert p["lab"][0] - half >= 0 and p["lab"][0] + half <= lay["w"], (e, p["lab"], lay["w"])
    for g, b in zip(v["groups"], lay["bands"]):
        inside = [boxes[n["id"]] for n in v["nodes"] if n.get("in") == g["id"]]
        assert all(b["x"] <= x and b["y"] <= y and x + w <= b["x"] + b["w"] and y + h <= b["y"] + b["h"] for x, y, w, h in inside)
        outside = [boxes[n["id"]] for n in v["nodes"] if n.get("in") != g["id"]]
        assert not any(overlap((b["x"], b["y"], b["w"], b["h"]), o) for o in outside), g["label"]   # まとまりの枠に、ほかの箱が入らない
    for i in range(len(lay["bands"])):
        for j in range(i + 1, len(lay["bands"])):
            bi, bj = lay["bands"][i], lay["bands"][j]
            assert bi["y"] + bi["h"] <= bj["y"]
    return lay


def test_arch_layout_of_the_examples():
    for d in (WEB, LAYERS):
        v, _ = arch.check(d)
        lay = check_layout(v)
        assert lay == arch.layout(v)                       # 同じ塊なら同じ置き場所
    lay = arch.layout(arch.check(WEB)[0])
    assert lay["cross"] <= 1 and lay["w"] < 760            # 典型の6つの箱は、列の幅に収まる（2つの箱が同じ2つを使う形は、段に並べると1回は交わる）
    assert rows_of(arch.check(WEB)[0])["ワーカー"] == rows_of(arch.check(WEB)[0])["API サーバー"]   # 使う相手のすぐ上まで下げる
    assert sum(1 for p in lay["edges"] if "lab" in p) == 2
    # 箱より外へ出る線の名前があれば、図の幅を広げる（本物の先生役の図で、名前が右端で切れていた）
    wide = arch.check({"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
                       "edges": [{"from": "a", "to": "c", "label": "request.user を読む"}, {"from": "a", "to": "b", "label": "get_response を呼ぶ"},
                                 {"from": "b", "to": "c", "label": "とても長い名前の線です"}]})[0]
    check_layout(wide)


def test_arch_layout_holds_for_random_drawings():
    rnd = random.Random(7)
    t0 = time.time()
    for case in range(300):
        n = rnd.randint(2, arch.NODES_MAX)
        ng = rnd.choice([0, 0, 2, 3, 4])
        d = {"layered": rnd.random() < 0.5, "groups": [{"id": f"g{k}", "label": f"まとまり{k}"} for k in range(ng)],
             "nodes": [{"id": f"n{i}", "label": "箱" * rnd.randint(1, 9) + str(i), "tech": rnd.choice(["", "", "FastAPI 0.11"]),
                        "kind": rnd.choice(["", "service", "store"]), "in": rnd.choice([""] + [f"g{k}" for k in range(ng)])} for i in range(n)],
             "edges": [{"from": f"n{rnd.randrange(n)}", "to": f"n{rnd.randrange(n)}", "label": rnd.choice(["", "", "HTTP"])}
                       for _ in range(rnd.randint(1, min(arch.EDGES_MAX, n * 2)))]}
        v, why = arch.check(d)
        if v is None:
            assert "線が無い" in why
            continue
        row = {x["id"]: x["row"] for x in v["nodes"]}
        for e in v["edges"]:                                # 置き場所の向きにそろえると、どの線も上の段から下の段へ
            a, b = (e["to"], e["from"]) if e.get("rev") else (e["from"], e["to"])
            assert row[a] < row[b], (case, e)
        check_layout(v)
    assert time.time() - t0 < 20


def test_arch_through_the_answer_and_file_tree():
    md = ("API サーバーが真ん中です。\n\n```tonari-arch\n" + json.dumps({**WEB, "edges": WEB["edges"] + [{"from": "zz", "to": "db"}]}, ensure_ascii=False)
          + "\n```\n\n```tonari-tree\n" + json.dumps({"name": "ファイルの並び", "why": "入れ子なので", "kind": "files", "root": "app/",
                                                      "children": [{"label": "page.tsx", "note": "入口"}]}, ensure_ascii=False) + "\n```")
    b = tutor.parse_blocks(md)
    assert [v["type"] for v in b["views"]] == ["arch", "tree"]
    a = b["views"][0]
    assert (a["name"], a["src"], a["arrow"], a["particle"]) == ("構成の図", "general", "使う", "を") and "dropped" not in a
    # 線の意味は、助詞と動詞に分けて持つ（「A は B に依存する」と文にするため）。助詞が無ければ動詞から決める
    assert [arch.arrow_parts(x) for x in ("に依存する", "依存する", "を呼ぶ", "呼ぶ", "", "から読む", "読み書きする")] == \
        [("に", "依存する"), ("に", "依存する"), ("を", "呼ぶ"), ("を", "呼ぶ"), ("を", "使う"), ("から", "読む"), ("を", "読み書きする")]
    assert b["errors"] == ["tonari-arch: 一部を捨てた（両端が箱に無い線）"]
    assert b["views"][1]["kind"] == "files"
    assert tutor.main_view(b["views"])["type"] == "arch"
    assert tutor.VIEW_NAMES["arch"] == "構成の図" and tutor.VIEW_NAMES["code"] == "コード"
    bad = tutor.parse_blocks("```tonari-arch\n{\"nodes\": [{\"label\": \"A\"}], \"edges\": []}\n```")
    assert bad["views"] == [] and bad["errors"][0].startswith("tonari-arch: 構成の図: 箱が2つ未満")


def test_what_is_done_on_figures_and_code_is_kept_as_counts_only():
    db.init()
    with TestClient(appmod.app, base_url=f"http://127.0.0.1:{appmod.config.PORT}") as c:
        for what in ("copy", "copy", "zoom", "pin", "deep", "inside", "impact"):
            assert c.post("/api/view/act", headers=H, json={"what": what}).status_code == 200
        assert c.post("/api/view/act", headers=H, json={"what": "x"}).status_code == 400
    with db.tx() as con:
        got = usage_stats.stats(con)
    assert got["view_acts"]["copy"] >= 2 and all(got["view_acts"][k] >= 1 for k in ("zoom", "pin", "deep", "inside", "impact"))
    assert {"turns_with_code", "turns_with_reading_code", "turns_with_arch"} <= set(got)


def test_the_answer_view_carries_the_layout_of_an_arch_figure():
    db.init()
    md = "API サーバーが真ん中です。\n\n```tonari-arch\n" + json.dumps(WEB, ensure_ascii=False) + "\n```\n\n```python\nx = 1\n```"
    t = db.now()
    with db.tx() as con:
        sid = con.execute("INSERT INTO session(title, model, created_at, updated_at, read_at) VALUES(?,?,?,?,?)", ("構成", "opus", t, t, t)).lastrowid
        tid = appmod.new_turn(con, sid, "text", final_text="構成は？", title="構成")
        con.execute("UPDATE turn SET status='done', answer_md=?, done_at=?, stage_ms=? WHERE id=?", (md, t, json.dumps({"rules": 4}), tid))
        row = db.row(con, "SELECT * FROM turn WHERE id=?", (tid,))
    v = appmod.turn_view(row)
    assert [x["type"] for x in v["views"]] == ["arch", "code"] and v["answer"] == "API サーバーが真ん中です。\n\n[[view:0]]\n\n[[view:1]]"
    lay = v["views"][0]["lay"]
    assert set(lay["nodes"]) == {n["id"] for n in WEB["nodes"]} and len(lay["edges"]) == len(WEB["edges"]) and lay["w"] > 0 and lay["h"] > 0


def test_the_tutor_is_told_about_code_and_the_new_figures():
    s = tutor.SYSTEM
    for word in ("```tonari-arch```", "```tonari-code```", "stateDiagram-v2", "classDiagram", "erDiagram", '"kind": "files"',
                 "使う側 → 使われる側", "行の番号ではなく、その行から写した字", "実行の途中の変数の値を1歩ずつ並べた表は書きません",
                 "コードの塊は数えません"):
        assert word in s, word
    assert "erDiagram は日本語の名前を描けないので使わない" not in s
    plan = {"chars": 250, "why": "会話の間合い"}
    db.init()
    assert "コードの塊は数えない" in tutor.turn_content(1, "x", "question", "text", [], plan=plan)


def test_a_decision_tree_with_four_levels_of_questions_keeps_its_conclusions():
    def tree(levels):
        node = {"ask": f"問い{levels}", "branches": [{"label": "はい", "result": "結論A", "src": "一般"}, {"label": "いいえ", "result": "結論B", "src": "一般"}]}
        for k in range(levels - 1, 0, -1):
            node = {"ask": f"問い{k}", "branches": [{"label": "いいえ", "result": "外れ", "src": "一般"}, {"label": "はい", "next": node}]}
        return {"name": "分岐の木", "why": "段があるので", "q": "判定", "root": node}
    v, why = tutor.verify_view("decide", tree(4))
    assert why is None                                             # 問いが4段（指示の上限）なら、4段目の下の結論まで読む
    n = v["root"]
    for _ in range(3):
        n = n["branches"][1]["node"]
    assert [b["node"]["result"] for b in n["branches"]] == ["結論A", "結論B"]
    assert tutor.verify_view("decide", tree(5))[0] is None         # 問いが5段の木は、前と同じく捨てる


# ── 見直し役（読むだけ）が見つけた入力（DESIGN 18.9）──
FLOW = '{"name": "流れ", "why": "順番があるので", "steps": [{"label": "一"}, {"label": "二"}]}'
CHECK = '[{"q": "問い", "a": "答え", "concept": "A", "rel": "related", "target": "B"}]'


def test_indented_blocks_are_still_read_as_figures_and_records():
    b = tutor.parse_blocks("答えです。\n\n  ```tonari-flow\n  " + FLOW + "\n  ```\n\n   ```tonari-check\n   " + CHECK + "\n   ```\n\n  ```mermaid\n  flowchart LR\n    A --> B\n  ```")
    assert [v["type"] for v in b["views"]] == ["flow", "mermaid"] and len(b["check"]) == 1       # 字下げされていても、素のコードの箱にしない
    b = tutor.parse_blocks("前。\n\n  ```tonari-code\n  lang: py\n  ---\n  x = 1\n  y = 2\n  ---\n  y = 2｜足す｜二つ目の値です。\n  ```")
    assert b["views"][0]["type"] == "code" and b["views"][0]["notes"][0]["from"] == 2


def test_a_code_fence_does_not_swallow_what_follows():
    tail = "\n\n説明の段落。\n\n```tonari-flow\n" + FLOW + "\n```\n\n```tonari-check\n" + CHECK + "\n```"
    for head in ("```python:main.py", "```js title=app.js", "```python {linenos}"):       # 言語の名前のあとに題などが続く開きの行
        b = tutor.parse_blocks("前。\n\n" + head + "\nx = 1\n```" + tail)
        assert [v["type"] for v in b["views"]] == ["code", "flow"] and b["views"][0]["code"] == "x = 1" and len(b["check"]) == 1, head
        assert b["views"][0]["lang"] in ("python", "javascript")
    for broken in ("```python\nx = 1", "```python\nx = 1```", "```\nx = 1"):               # 閉じていない・閉じが行の途中
        b = tutor.parse_blocks("前。\n\n" + broken + tail)
        assert [v["type"] for v in b["views"] if v["type"] != "code"] == ["flow"] and len(b["check"]) == 1, broken
        assert "説明の段落。" in b["text"], broken                                              # 段落を、コードの箱に飲み込まない
    # 記録役があとから足す塊（記録用の地図と確かめの問い）も、閉じていないコードの塊に巻き込まれない
    added = "前。\n\n```python\nx = 1\n\n" + "```tonari-map\n" + json.dumps({"center": "中心", "show": False}, ensure_ascii=False) + "\n```\n\n```tonari-check\n" + CHECK + "\n```"
    b = tutor.parse_blocks(added)
    assert b["map"]["center"] == "中心" and len(b["check"]) == 1 and b["views"] == []
    t0 = time.time()
    tutor.parse_blocks("".join(f"文{i}\n\n```python\nx = {i}\n\n" for i in range(10000)))        # 閉じの無い開きが1万個
    assert time.time() - t0 < 2


def test_names_that_appear_only_in_a_code_block_still_count_as_in_the_answer():
    parts = {"name": "しくみの絵", "why": "受け渡しがあるので", "parts": [{"id": "a", "label": "Client"}, {"id": "b", "label": "Server"}],
             "links": [{"from": "a", "to": "b", "label": "頼む"}]}
    md = "受け渡しの絵です。\n\n```python\nclass Client: ...\nclass Server: ...\n```\n\n```tonari-parts\n" + json.dumps(parts, ensure_ascii=False) + "\n```"
    b = tutor.parse_blocks(md)
    assert [v["type"] for v in b["views"]] == ["code", "parts"] and b["errors"] == []          # v0.6 まで出ていた図が、消えない
    assert "Client" not in tutor.strip_blocks(md)                                              # 字数の目安の本文には、コードを入れない


def test_code_keeps_trailing_spaces_and_reading_code_edge_cases():
    v = tutor.parse_blocks("```diff\n-old\n \n+new  \n same\n```")["views"][0]
    assert v["code"] == "-old\n \n+new  \n same"                                                 # 行末の空白と、空白1つだけの行を落とさない
    v, bad = tutor.reading_code("name: CI\non: push\njobs:\n  test: {}")                         # 区切りが無い YAML。name: の行を頭と取り違えない
    assert v["code"].startswith("name: CI\n") and v["lang"] == ""
    v, bad = tutor.reading_code("lang: yaml\ntitle: 設定\nname: CI\non: push")                    # 区切りが無くても、1行目が lang: なら頭を読む
    assert (v["lang"], v["title"], v["code"]) == ("yaml", "設定", "name: CI\non: push")
    v, bad = tutor.reading_code("lang: py\n---\ndef add(a, b):\n    return a + b\n---\n")        # 注釈が無いまま --- で閉じた
    assert v["code"] == "def add(a, b):\n    return a + b" and v["notes"] == []
    v, bad = tutor.reading_code("---\nvalue = f(\n    a,\n    b,\n)\ng()\n---\nvalue = f(〜)｜呼ぶ｜引数を縦に並べた呼び出しです。")
    assert [(n["from"], n["to"]) for n in v["notes"]] == [(1, 4)]                                # 終わりの字が短くても、始めの行の次から探す


def test_an_arch_block_with_the_wrong_shapes_never_raises():
    for bad in ({"groups": {"a": 1}, "nodes": [{"label": "A"}, {"label": "B"}], "edges": [{"from": "A", "to": "B"}]},
                {"groups": 3, "nodes": [{"label": "A"}, {"label": "B"}], "edges": [{"from": "A", "to": "B"}]},
                {"groups": True, "nodes": 5, "edges": []}, {"nodes": [{"label": "A"}, {"label": "B"}], "edges": 7},
                {"nodes": "x", "edges": "y"}, {"nodes": [1, "a", None], "edges": [None, 2]}):
        v, why = arch.check(bad)
        assert v is None or arch.layout(v)["w"] > 0
    b = tutor.parse_blocks('答え。\n\n```tonari-arch\n{"groups": {"a": 1}, "nodes": 5, "edges": 7}\n```')
    assert b["views"] == [] and b["errors"][0].startswith("tonari-arch: 構成の図: 箱が2つ未満")
    # どの図でも、決まりの確かめが例外で落ちたら、その塊だけを捨てて記録に残す（答えごと失わない）
    b = tutor.parse_blocks('答え。\n\n```tonari-timeline\n{"from": 0, "to": 10, "lanes": 5, "marks": 7}\n```')
    assert b["text"] == "答え。" and b["views"] == [] and len(b["errors"]) == 1
