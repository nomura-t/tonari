"""全体の地図の入口の検査（v0.6）。開いたことを数として残す・島の置き場所を覚える・読むだけの口は記録を変えない・
並べ直しは本人が頼んだときだけ・地図の中でしたことは決まった種類だけを数える・キーの割り当てを変えられる。材料は作り物。"""
import json
import os
import tempfile

os.environ.setdefault("TONARI_DATA_DIR", tempfile.mkdtemp(prefix="tonari-test-"))
os.environ.setdefault("TONARI_RECORDER", "off")

from fastapi.testclient import TestClient  # noqa: E402

from server import app as appmod, atlas, db, tutor  # noqa: E402

H = {"X-Tonari": "1"}


def _client():
    return TestClient(appmod.app, base_url=f"http://127.0.0.1:{appmod.config.PORT}")


def _topic(title, center, parts):
    db.init()
    with db.tx() as con:
        sid = con.execute("INSERT INTO session(title, model, created_at, updated_at) VALUES(?,?,?,?)", (title, "opus", 0, 0)).lastrowid
        tid = con.execute("INSERT INTO turn(session_id, seq, via, status, created_at, final_text) VALUES(?,?,?,?,?,?)",
                          (sid, 1, "text", "done", 0, "問い")).lastrowid
        c = tutor.merge_map(con, sid, tid, {"center": center, "src": "一般", "related": [{"label": p, "rel": "部分", "src": "一般"} for p in parts]})
        con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (json.dumps({"center": c}), tid))
    return sid


def _logs(state=None):
    with db.tx() as con:
        return db.row(con, "SELECT COUNT(*) AS n FROM log WHERE kind='atlas'" + (" AND state=?" if state else ""), (state,) if state else ())["n"]


def test_opening_the_map_is_counted_and_the_places_of_islands_are_remembered():
    a = _topic("地図の検査の話題A", "地図検査の言葉A", ["地図検査の部品1", "地図検査の共通の部品"])
    b = _topic("地図の検査の話題B", "地図検査の言葉B", ["地図検査の共通の部品"])
    db.set_pref(atlas.PREF, "{}")
    c = _client()
    n = _logs("open")
    r = c.post("/api/atlas/open", headers=H)
    assert r.status_code == 200 and _logs("open") == n + 1
    d = r.json()
    assert {a, b} <= {t["id"] for t in d["topics"]} and {a, b} <= {i["topic"] for i in d["layout"]["islands"]}
    assert any(x["a"] == a and x["b"] == b for x in d["layout"]["bridges"])            # 共通の言葉があるので、橋がある
    assert atlas.stored() == d["layout"]["anchors"] and str(a) in atlas.stored()        # 置き場所を覚える
    again = c.post("/api/atlas/open", headers=H).json()
    assert again["layout"]["anchors"] == d["layout"]["anchors"] and again["layout"]["places"] == d["layout"]["places"]   # 開くたびに同じ


def test_reading_the_map_changes_nothing_and_relayout_only_on_request():
    a = _topic("地図の検査の話題C", "地図検査の言葉C", ["地図検査の部品C1"])
    c = _client()
    c.post("/api/atlas/open", headers=H)
    n, kept = _logs(), atlas.stored()
    r = c.get("/api/atlas", headers=H)
    assert r.status_code == 200 and _logs() == n and atlas.stored() == kept           # 読むだけの口は、数えないし、覚え直さない
    assert r.json()["layout"]["anchors"] == kept
    # 覚えている置き場所を、わざと離れた所に変えておく。開き直しても、その場所のまま（勝手に並べ直さない）
    far = dict(kept)
    far[str(a)] = [kept[str(a)][0] + atlas.QW * 60, kept[str(a)][1]]
    db.set_pref(atlas.PREF, json.dumps(far))
    assert c.post("/api/atlas/open", headers=H).json()["layout"]["anchors"][str(a)] == far[str(a)]
    # 本人が並べ直しを頼んだときだけ、決め直して覚える
    m = _logs("relayout")
    again = c.post("/api/atlas/open", headers=H, json={"reset": True}).json()
    assert again["layout"]["anchors"][str(a)] != far[str(a)] and atlas.stored() == again["layout"]["anchors"] and _logs("relayout") == m + 1


def test_actions_in_the_map_are_counted_by_kind_only():
    c = _client()
    n = _logs("concept")
    assert c.post("/api/atlas/act", headers=H, json={"what": "concept", "id": 1}).status_code == 200 and _logs("concept") == n + 1
    assert c.post("/api/atlas/act", headers=H, json={"what": "find"}).status_code == 200
    assert c.post("/api/atlas/act", headers=H, json={"what": "なにか"}).status_code == 400
    assert c.post("/api/atlas/act", json={"what": "concept"}).status_code == 403          # 見出しの無い呼び出しは断る
    with db.tx() as con:
        rows = db.rows(con, "SELECT evidence FROM log WHERE kind='atlas'")
    assert all(r["evidence"] is None for r in rows)                                       # 中身（言葉・話題の名前）は残さない


def test_the_key_for_the_map_can_be_changed():
    c = _client()
    before = c.get("/api/state", headers=H).json()["prefs"]["keys"]
    assert c.post("/api/prefs", headers=H, json={"keys": {**before, "atlas": "Alt+KeyG"}}).status_code == 200
    assert c.get("/api/state", headers=H).json()["prefs"]["keys"].get("atlas") == "Alt+KeyG"
    c.post("/api/prefs", headers=H, json={"keys": before})
