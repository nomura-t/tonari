"""全体の地図（v0.6・DESIGN 17.13）。話題に出てきた言葉と関係の全部を、1枚の地図に置く。

読み出し（graph）と置き場所（layout）を分ける。置き場所は、記録と前の置き場所だけから決まる（同じなら同じ地図）。

- 島は話題。1つの話題は、名前の札の付いた1つの四角で、飛び地を作らない（研究 g5 の 4-1・4-2）。
- 話題をまたいで出てくる言葉は、出てくる島ごとに置き、島と島のあいだを橋で結ぶ（g5 の 4-4: どの話題どうしが
  言葉を共有しているかは、複製して結ぶ形の方がずっと読めた）。橋は曲げて束ねない（g5 の 7-2）。
- 島の中は、左から右へ伸びる木。骨は記録の関係そのもので、上位・下位を先に骨にし、次に部品、つながり、対の順に足す。
  木に入らなかった関係（輪になる分）は、細い線として別に返す。関係の種類は線の側に持たせ、置き場所は
  「左が広く、右が細かい」を約束しない（上位・下位の関係は全体の一部しか無い）。
- 木の根は、その話題で説明を受けた言葉（無ければ、いちばん先に出てきた言葉）から、上位の関係をたどった先。
  兄弟は、関係が記録された順に上から並ぶ。
- 島の場所は、前の置き場所（prev）があればそこに置く。新しい島は、言葉を共有する島の近くの空きに足す
  （開くたびに動かさない。g5 の 2-2。見やすさを削ってまでは守らない: 島が大きくなって隣と重なったら、番号の新しいほうの島を近くの空きへ移す）。
"""
from __future__ import annotations

import json
import math
import unicodedata

from . import db

FONT = 13.0            # 言葉の字（地図の単位。画面では倍率が掛かる）
HUB_FONT = 14.0        # 説明を受けた言葉（答えの中心になった言葉）の字
PADX = 9.0             # 札の左右の余白
ROW = 26.0             # 行の送り
GAPX = 30.0            # 親の札の右端から、子の札の左端まで
TITLE_H = 32.0         # 島の名前の行
TITLE_FONT = 13.0
TREE_GAP = 10.0        # 同じ島の中の、つながっていない木のあいだ
PAD = 14.0             # 島の四角の内側の余白
GUT = 14.0             # 島の四角の外側の余白（隣の島とのあいだの半分）
QW, QH = 90.0, 78.0    # 島の場所取りの刻み（言葉が少し増えても、場所取りが変わらないように。78 は3行ぶん）
STEP_X, STEP_Y = QW / 2, QH / 2
ASPECT = 1.6           # 横に広く並べる（窓の形に合わせる）
MAX_CHARS = 16         # 札に出す字の上限（超えた分は … にする）
MAX_TITLE = 26
REACH = 120            # 空きを探す範囲（刻みの数）
PREF = "atlas_place"


def short(label: str, n: int = MAX_CHARS) -> str:
    s = str(label or "")
    return s if len(s) <= n else s[:n - 1] + "…"


def text_w(s: str, size: float = FONT) -> float:
    """字の幅の見積もり（全角は1字ぶん、半角は 0.6字ぶん）。画面の実測より少し広めに出る。"""
    return sum(1.0 if unicodedata.east_asian_width(ch) in "WFA" else 0.6 for ch in s) * size


def node_w(label: str, hub: bool) -> float:
    return round(text_w(short(label), HUB_FONT if hub else FONT) * (1.05 if hub else 1.0) + 2 * PADX, 1)


class _UF:
    """まとまりを作る（代表は、いちばん小さい番号）。"""

    def __init__(self) -> None:
        self.p: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if ra > rb:
            ra, rb = rb, ra
        self.p[rb] = ra
        return True


def graph(con) -> dict:
    """話題に出てきた言葉（session_concept）と、そのあいだの関係（上位・対・つながり）。例と非例の文は入れない。"""
    sessions = {s["id"]: s for s in db.rows(con, "SELECT id, title, archived FROM session")}
    topics_of: dict[int, set[int]] = {}
    members: dict[int, list] = {}        # 話題 → [(その話題で最初に出てきた往復, 言葉)]
    for l in db.rows(con, "SELECT session_id, concept_id, first_turn FROM session_concept"):
        sid, cid = l["session_id"], l["concept_id"]
        if sid not in sessions:
            continue
        topics_of.setdefault(cid, set()).add(sid)
        members.setdefault(sid, []).append((l["first_turn"] if l["first_turn"] is not None else math.inf, cid))

    # 説明を受けた言葉（答えの中心）。話題ごとに、中心になった順
    hubs: dict[int, list[int]] = {}
    hub_n: dict[int, int] = {}
    for t in db.rows(con, """SELECT id, session_id, stage_ms FROM turn
                             WHERE status='done' AND stage_ms LIKE '%"center"%' ORDER BY id"""):
        try:
            c = json.loads(t["stage_ms"] or "{}").get("center")
        except ValueError:
            continue
        if isinstance(c, int) and not isinstance(c, bool) and t["session_id"] in topics_of.get(c, ()):
            hub_n[c] = hub_n.get(c, 0) + 1
            if c not in hubs.setdefault(t["session_id"], []):
                hubs[t["session_id"]].append(c)

    nodes = []
    for r in db.rows(con, """SELECT c.id, c.label, c.gist, m.state FROM concept c LEFT JOIN mastery m ON m.concept_id=c.id
                             WHERE c.id IN (SELECT concept_id FROM session_concept) ORDER BY c.id"""):
        if r["id"] in topics_of:
            nodes.append({"id": r["id"], "label": r["label"], "gist": r["gist"] or "", "state": r["state"],
                          "topics": sorted(topics_of[r["id"]]), "hub": hub_n.get(r["id"], 0)})

    edges = []
    for r in db.rows(con, """SELECT r.*, rm.state AS rstate, t.session_id AS topic FROM relation r
                             LEFT JOIN rel_mastery rm ON rm.relation_id=r.id LEFT JOIN turn t ON t.id=r.turn_id
                             WHERE r.rel IN ('broader','opposite','related') ORDER BY r.id"""):
        if r["src"] in topics_of and r["dst"] in topics_of and r["src"] != r["dst"]:
            edges.append({"id": r["id"], "src": r["src"], "dst": r["dst"], "rel": r["rel"], "detail": r.get("detail") or "",
                          "phrase": r.get("phrase") or "", "rstate": r.get("rstate"), "topic": r.get("topic")})

    topics = []
    for sid in sorted(members):
        ms = sorted(members[sid])
        topics.append({"id": sid, "title": sessions[sid]["title"], "archived": bool(sessions[sid]["archived"]),
                       "concepts": [c for _, c in ms], "hubs": hubs.get(sid, []),
                       "first": {str(c): (None if ft == math.inf else int(ft)) for ft, c in ms}})
    counts = {"concepts": len(nodes), "relations": len(edges), "checked": sum(1 for e in edges if e["rstate"]),
              "known": sum(1 for e in edges if e["rstate"] == "known"), "topics": len(topics), "hubs": len(hub_n),
              "shared": sum(1 for v in topics_of.values() if len(v) > 1), "empty_topics": len(sessions) - len(topics)}
    return {"topics": topics, "nodes": nodes, "edges": edges, "counts": counts}


def _pri(e: dict) -> int:
    if e["rel"] == "broader":
        return 0
    if e["rel"] == "related":
        return 1 if e["detail"] == "部分" else 2
    return 3


def _island(t: dict, nodes: dict, edges: list[dict]) -> dict:
    """1つの話題の島の中身を置く（島の左上を原点にした座標）。"""
    cids = t["concepts"]
    inset = set(cids)
    order = {c: ((t["first"].get(str(c)) if t["first"].get(str(c)) is not None else math.inf), c) for c in cids}
    hubs = set(t["hubs"])
    hub_rank = {c: i for i, c in enumerate(t["hubs"])}
    uf = _UF()
    tree, cross = [], []
    # 骨にする順: この話題の答えで記録された関係を先に（ほかの話題で記録された関係は、両端がこの島にあれば後から足す）
    for e in sorted((e for e in edges if e["src"] in inset and e["dst"] in inset),
                    key=lambda e: (0 if e.get("topic") == t["id"] else 1, _pri(e), e["id"])):
        (tree if uf.union(e["src"], e["dst"]) else cross).append(e)
    adj: dict[int, list] = {c: [] for c in cids}
    for e in tree:
        adj[e["src"]].append((e["dst"], e))
        adj[e["dst"]].append((e["src"], e))
    comps: dict[int, list[int]] = {}
    for c in cids:
        comps.setdefault(uf.find(c), []).append(c)

    def top_of(c: int) -> int:
        seen = {c}
        while True:
            up = [o for o, e in adj[c] if e["rel"] == "broader" and e["src"] == c and o not in seen]
            if not up:
                return c
            c = min(up)
            seen.add(c)

    children: dict[int, list] = {}
    parent: dict[int, int] = {}
    roots = []
    for ms in comps.values():
        # 根は、この話題で説明を受けた言葉（無ければ、いちばん先に出てきた言葉）から、上位の関係をたどった先
        hs = [c for c in ms if c in hub_rank]
        first = min(hs, key=hub_rank.get) if hs else min(ms, key=order.get)
        root = top_of(first)
        stack = [(root, None)]
        while stack:
            n, par = stack.pop()
            ch = sorted(((o, e) for o, e in adj[n] if o != par), key=lambda oe: oe[1]["id"])
            children[n] = ch
            for o, _ in ch:
                parent[o] = n
                stack.append((o, n))
        roots.append(((0, hub_rank[first], 0) if hs else (1, *order[first]), root))

    width = {c: node_w(nodes[c]["label"], c in hubs) for c in cids}
    title_w = text_w(short(t["title"], MAX_TITLE), TITLE_FONT) + 56     # 名前の右に、言葉の数の小さな字が付く
    pos: dict[int, tuple[float, float]] = {}
    y0, right = TITLE_H, title_w
    for _, root in sorted(roots):
        xs: dict[int, float] = {}
        stack = [(root, 0.0)]
        while stack:                       # 左から右へ: 子は、親の札の右端の先
            n, x = stack.pop()
            xs[n] = x
            right = max(right, x + width[n])
            for o, _ in children[n]:
                stack.append((o, x + width[n] + GAPX))
        cur = y0
        ys: dict[int, float] = {}
        walk = [(root, 0)]
        while walk:                        # 上から下へ: 葉は次の行、親は最初と最後の子の真ん中
            n, i = walk.pop()
            ch = children[n]
            if i < len(ch):
                walk.append((n, i + 1))
                walk.append((ch[i][0], 0))
            elif not ch:
                ys[n] = cur + ROW / 2
                cur += ROW
            else:
                ys[n] = (ys[ch[0][0]] + ys[ch[-1][0]]) / 2
        for n in xs:
            pos[n] = (xs[n], ys[n])
        y0 = cur + TREE_GAP
    links = [[e["id"], parent[c], c] for e in tree for c in ((e["src"],) if parent.get(e["src"]) == e["dst"] else (e["dst"],))]
    return {"pos": pos, "width": width, "links": links, "cross": [[e["id"], e["src"], e["dst"]] for e in cross],
            "w": right, "h": y0 - TREE_GAP, "trees": len(comps)}


def _pack(items: list[tuple[int, float, float]], prev: dict, share: dict[int, dict[int, int]] | None = None) -> dict[int, tuple[float, float]]:
    """島の場所取り。前の置き場所がある島は、空いていればそこに置く。無い島は、言葉を共有する島の近く
    （無ければ真ん中の近く）の空きへ足す。"""
    share = share or {}
    placed: dict[int, tuple[float, float, float, float]] = {}
    occ: set[tuple[int, int]] = set()      # 島が取っている、ますの集まり（空きの確かめを、島の数に依らない手間にする）
    floor = min(STEP_X / ASPECT, STEP_Y)

    def cells(x: float, y: float, w: float, h: float):
        return (range(math.floor(x / STEP_X + 1e-9), math.ceil((x + w) / STEP_X - 1e-9)),
                range(math.floor(y / STEP_Y + 1e-9), math.ceil((y + h) / STEP_Y - 1e-9)))

    def free(x: float, y: float, w: float, h: float) -> bool:
        xs, ys = cells(x, y, w, h)
        return not any((ix, iy) in occ for ix in xs for iy in ys)

    def put(k: int, x: float, y: float, w: float, h: float) -> None:
        placed[k] = (x, y, w, h)
        xs, ys = cells(x, y, w, h)
        occ.update((ix, iy) for ix in xs for iy in ys)

    def near(cx: float, cy: float, w: float, h: float) -> tuple[float, float]:
        bx, by = round((cx - w / 2) / STEP_X), round((cy - h / 2) / STEP_Y)
        best = None
        for r in range(REACH):
            for ix in range(-r, r + 1):
                for iy in (range(-r, r + 1) if abs(ix) == r else (-r, r)):
                    x, y = (bx + ix) * STEP_X, (by + iy) * STEP_Y
                    if free(x, y, w, h):
                        key = (round(math.hypot((x + w / 2 - cx) / ASPECT, y + h / 2 - cy), 3), y, x)
                        if best is None or key < best:
                            best = key
            # これより外の輪には、いまの候補より近い所が無い
            if best is not None and best[0] <= (r + 1) * floor - (STEP_X / ASPECT + STEP_Y):
                break
        if best is None:      # 探す範囲に空きが無い（ふつう起きない）。右の外へ置く
            return (max((px + pw for px, _, pw, _ in placed.values()), default=0.0), by * STEP_Y)
        return (best[2], best[1])

    for k, w, h in [it for it in items if str(it[0]) in prev]:
        x, y = float(prev[str(k)][0]), float(prev[str(k)][1])
        if not free(x, y, w, h):
            x, y = near(x + w / 2, y + h / 2, w, h)
        put(k, x, y, w, h)
    # 新しい島は、もう置いた島と言葉をいちばん多く共有する島から先に置く（つながった話題が、ひとかたまりに寄る）。
    # 共有の無い島は、古い順に、真ん中の近くへ
    pending = {k: (w, h) for k, w, h in items if str(k) not in prev}
    while pending:
        tie = {k: sum(n for o, n in (share.get(k) or {}).items() if o in placed) for k in pending}
        k = min(pending, key=lambda x: (-tie[x], x))
        w, h = pending.pop(k)
        if not placed:
            put(k, -math.floor(w / 2 / STEP_X) * STEP_X, -math.floor(h / 2 / STEP_Y) * STEP_Y, w, h)
            continue
        friends = [(o, n) for o, n in sorted((share.get(k) or {}).items()) if o in placed]
        if friends:
            tot = sum(n for _, n in friends)
            cx = sum((placed[o][0] + placed[o][2] / 2) * n for o, n in friends) / tot
            cy = sum((placed[o][1] + placed[o][3] / 2) * n for o, n in friends) / tot
        else:
            cx, cy = 0.0, 0.0
        x, y = near(cx, cy, w, h)
        put(k, x, y, w, h)
    return {k: (v[0], v[1]) for k, v in placed.items()}


def layout(g: dict, prev: dict | None = None) -> dict:
    """置き場所を決める。prev は前の島の置き場所（{話題の番号: [x, y]}）。返す anchors を次に渡すと、島は動かない。"""
    prev = prev or {}
    nodes = {n["id"]: n for n in g["nodes"]}
    if not g["topics"]:
        return {"places": {}, "links": [], "cross": [], "islands": [], "bridges": [], "anchors": {}, "box": [0, 0, 0, 0], "trees": 0}
    inner = {t["id"]: _island(t, nodes, g["edges"]) for t in g["topics"]}

    # 橋: 同じ言葉が出てくる島の組（言葉ごとに1本。束ねない）
    pair: dict[tuple[int, int], list[int]] = {}
    share: dict[int, dict[int, int]] = {}
    for n in g["nodes"]:
        ts = n["topics"]
        for i in range(len(ts)):
            for j in range(i + 1, len(ts)):
                pair.setdefault((ts[i], ts[j]), []).append(n["id"])
    for (a, b), cs in pair.items():
        share.setdefault(a, {})[b] = len(cs)
        share.setdefault(b, {})[a] = len(cs)

    foot = [(tid, math.ceil((isl["w"] + 2 * (PAD + GUT)) / QW) * QW, math.ceil((isl["h"] + 2 * (PAD + GUT)) / QH) * QH)
            for tid, isl in sorted(inner.items())]
    at = _pack(foot, prev, share)

    places: dict[str, list[float]] = {}
    links, cross, islands = [], [], []
    for tid, fw, fh in foot:
        isl, (ax, ay) = inner[tid], at[tid]
        ox, oy = ax + GUT + PAD, ay + GUT + PAD
        for c, (x, y) in isl["pos"].items():
            places[f"{tid}:{c}"] = [round(ox + x, 1), round(oy + y, 1), isl["width"][c]]
        links += [[rid, f"{tid}:{p}", f"{tid}:{c}"] for rid, p, c in isl["links"]]
        cross += [[rid, f"{tid}:{a}", f"{tid}:{b}"] for rid, a, b in isl["cross"]]
        islands.append({"topic": tid, "x": ax, "y": ay, "w": fw, "h": fh,                    # 場所取り（刻みに合わせた四角）
                        "bx": ax + GUT, "by": ay + GUT, "bw": fw - 2 * GUT, "bh": fh - 2 * GUT,   # 描く四角
                        "tx": ox, "ty": oy + TITLE_H / 2 - 4})
    bridges = [{"a": a, "b": b, "concepts": cs} for (a, b), cs in sorted(pair.items())]
    box = [min(i["x"] for i in islands), min(i["y"] for i in islands),
           max(i["x"] + i["w"] for i in islands), max(i["y"] + i["h"] for i in islands)]
    return {"places": places, "links": links, "cross": cross, "islands": islands, "bridges": bridges,
            "anchors": {str(i["topic"]): [i["x"], i["y"]] for i in islands}, "box": box,
            "trees": sum(isl["trees"] for isl in inner.values())}


def stored() -> dict:
    try:
        v = json.loads(db.get_pref(PREF, "{}"))
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def build(prev: dict | None = None) -> dict:
    with db.tx() as con:
        g = graph(con)
    return {**g, "layout": layout(g, stored() if prev is None else prev)}
