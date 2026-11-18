"""構成の図（v0.7・tonari-arch）。箱（モジュール・層・サービス・保存する所など）と、向きのある線（A が B を使う）で、
依存の向きと全体の構成を見せる。DESIGN 18章。

先生役が書くのは、箱・まとまり（層や境界）・線だけ。段の割り振りと置き場所は機械が決める。
  check   塊を決まりで確かめて整える。循環（A→B→A）と、層の決まりに逆らう線（下のまとまりから上のまとまりへ）を見つけて印を付ける。
          見つけるのは「この図に描かれた線」の性質で、線の中身（本当に依存しているか）は確かめていない。
  layout  箱の置き場所と線の通り道（段ごとに並べる。線は上から下へ流す。逆向きの線と循環を閉じる線は、矢じりだけ上を向く）。

段の決め方。まとまり（groups）は書かれた順に上から下へ並べ、まとまりの中は「使う側が上、使われる側が下」になるように段を分ける。
まとまりに入っていない箱は、線が出るだけの箱（使う側だけ）なら上、それ以外は下に置く。1段に並べる箱は5つまでで、超えたら段を分ける。
"""
from .db import fold

KINDS = ("person", "ui", "service", "module", "store", "queue", "external")
KIND_ALIASES = {"人": "person", "user": "person", "actor": "person", "画面": "ui", "client": "ui", "frontend": "ui", "app": "ui",
                "サービス": "service", "server": "service", "process": "service", "api": "service", "worker": "service",
                "モジュール": "module", "lib": "module", "library": "module", "package": "module", "class": "module", "component": "module",
                "layer": "module", "file": "module", "保存": "store", "db": "store", "database": "store", "cache": "store", "storage": "store",
                "キュー": "queue", "topic": "queue", "stream": "queue", "外部": "external", "ext": "external", "saas": "external"}
NODES_MAX, EDGES_MAX, GROUPS_MAX, ROW_MAX = 16, 36, 6, 5
LABEL_CAP, TECH_CAP, NOTE_CAP, ELABEL_CAP, ARROW_CAP = 28, 22, 34, 18, 10


def _s(x, n: int) -> str:
    return str(x if x is not None else "").strip()[:n]


NI_VERBS = ("依存", "頼", "従", "属", "アクセス", "問い合わせ", "送", "書き込", "つな", "委", "接続")   # 「に」を取る動詞の頭


def arrow_parts(x) -> tuple[str, str]:
    """線の意味（「を使う」「に依存する」）を、助詞と動詞に分ける。助詞が書かれていなければ、動詞から決める（既定は「を」）。
    画面は「A は B に依存する」「X に依存するのは…」のように、助詞ごと文にする。"""
    a = _s(x, ARROW_CAP + 2) or "使う"
    for p in ("から", "を", "に", "へ", "と"):
        if a.startswith(p) and len(a) > len(p):
            return p, a[len(p):]
    return ("に" if a.startswith(NI_VERBS) else "を"), a


def check(d: dict) -> tuple[dict | None, str | None]:
    """塊を決まりで確かめる。合えば（整えた塊, None）、合わなければ（None, 捨てた理由）。一部を捨てたときは dropped に理由。"""
    bad: list[str] = []
    groups, gids = [], set()

    def rows_of(key: str) -> list:   # 配列でない物（辞書・数・真偽）が来ても落ちない
        x = d.get(key)
        return x if isinstance(x, list) else []

    for g in rows_of("groups")[:GROUPS_MAX + 4]:
        if not isinstance(g, dict):
            continue
        lab = _s(g.get("label"), LABEL_CAP)
        gid = _s(g.get("id"), 24) or lab
        if not lab or gid in gids:
            continue
        gids.add(gid)
        groups.append({"id": gid, "label": lab})
    g_by_label = {fold(g["label"]): g["id"] for g in groups}

    nodes, ids = [], set()
    for x in rows_of("nodes"):
        if not isinstance(x, dict):
            continue
        lab = str(x.get("label") or "").strip()
        nid = _s(x.get("id"), 24) or lab[:24]
        if not lab:
            bad.append("名前が空の箱")
        elif nid in ids:
            bad.append(f"id が重なる箱（{nid}）")
        elif len(lab) > LABEL_CAP:
            bad.append(f"名前でなく文の箱（{len(lab)}字）")
        else:
            ids.add(nid)
            kind = str(x.get("kind") or "").strip().lower()
            kind = kind if kind in KINDS else KIND_ALIASES.get(kind, "")
            grp = str(x.get("in") or "").strip()
            grp = grp if grp in gids else g_by_label.get(fold(grp), "") if grp else ""
            nodes.append({"id": nid, "label": lab, "kind": kind, "tech": _s(x.get("tech"), TECH_CAP),
                          "note": _s(x.get("note"), NOTE_CAP), "in": grp})
    if len(nodes) > NODES_MAX:
        bad.append(f"{NODES_MAX + 1}個目からの箱（{len(nodes) - NODES_MAX}つ）")
        nodes = nodes[:NODES_MAX]
    ids = {n["id"] for n in nodes}
    by_label = {fold(n["label"]): n["id"] for n in nodes}

    def ref(v) -> str | None:
        v = str(v or "").strip()
        return v if v in ids else by_label.get(fold(v)) if v else None

    edges, seen = [], set()
    for x in rows_of("edges"):
        if not isinstance(x, dict):
            continue
        a, b = ref(x.get("from")), ref(x.get("to"))
        if not a or not b:
            bad.append("両端が箱に無い線")
        elif a == b:
            bad.append("自分から自分への線")
        elif (a, b) in seen:
            bad.append("同じ向きの線の重なり")
        else:
            seen.add((a, b))
            edges.append({"from": a, "to": b, "label": _s(x.get("label"), ELABEL_CAP)})
    if len(edges) > EDGES_MAX:
        bad.append(f"{EDGES_MAX + 1}本目からの線（{len(edges) - EDGES_MAX}本）")
        edges = edges[:EDGES_MAX]
    if len(nodes) < 2:
        return None, "構成の図: 箱が2つ未満（" + "・".join(bad[:4] or ["箱が無い"]) + "）"
    if not edges:
        return None, "構成の図: 線が無い（" + "・".join(bad[:4] or ["線が無い"]) + "）"

    used = {n["in"] for n in nodes if n["in"]}
    groups = [g for g in groups if g["id"] in used][:GROUPS_MAX]
    kept = {g["id"] for g in groups}
    for n in nodes:
        if n["in"] not in kept:
            n["in"] = ""
    layered = bool(d.get("layered")) and len(groups) >= 2
    particle, verb = arrow_parts(d.get("arrow"))
    v = {"arrow": verb, "particle": particle, "layered": layered, "groups": groups, "nodes": nodes, "edges": edges}
    analyse(v)
    for n in nodes:
        for k in ("kind", "tech", "note", "in"):
            if not n[k]:
                n.pop(k)
    if bad:
        v["dropped"] = bad
    return v, None


def _scc(ids: list[str], out: dict[str, list[str]]) -> list[list[str]]:
    """強連結成分（Tarjan・繰り返しで書く）。2つ以上の箱でできた成分＝循環。"""
    index, low, on, stack, res = {}, {}, set(), [], []
    n = 0
    for root in ids:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = n
                n += 1
                stack.append(v)
                on.add(v)
            nxt = out.get(v, [])
            if i < len(nxt):
                work.append((v, i + 1))
                w = nxt[i]
                if w not in index:
                    work.append((w, 0))
                elif w in on:
                    low[v] = min(low[v], index[w])
                continue
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    res.append(comp)
            if work:
                p = work[-1][0]
                low[p] = min(low[p], low[v])
    return res


def analyse(v: dict) -> None:
    """循環・逆向きの線・段を決めて、塊に書き込む（nodes の row、edges の cyc・up・rev、groups の rows、cycles）。"""
    nodes, edges, groups = v["nodes"], v["edges"], v["groups"]
    order = {n["id"]: i for i, n in enumerate(nodes)}
    ids = [n["id"] for n in nodes]
    out: dict[str, list[str]] = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for e in edges:
        out[e["from"]].append(e["to"])
        indeg[e["to"]] += 1
    comps = _scc(ids, out)
    comp_of = {i: k for k, c in enumerate(comps) for i in c}
    label = {n["id"]: n["label"] for n in nodes}
    v["cycles"] = [[label[i] for i in sorted(c, key=order.get)] for c in comps]
    for e in edges:
        e.pop("cyc", None), e.pop("up", None), e.pop("rev", None)
        if e["from"] in comp_of and comp_of[e["from"]] == comp_of.get(e["to"], -1):
            e["cyc"] = True

    # まとまりの順番（上から）。入っていない箱は、線が出るだけなら上（-1）、ほかは下（まとまりの数）
    gi = {g["id"]: k for k, g in enumerate(groups)}
    band = {}
    for n in nodes:
        if n["in"] in gi:
            band[n["id"]] = gi[n["in"]]
        elif not groups:
            band[n["id"]] = 0
        else:
            band[n["id"]] = -1 if indeg[n["id"]] == 0 and out[n["id"]] else len(groups)
    # 置き場所を決めるための向き（上の段→下の段）。まとまりをまたぐ線は、まとまりの順で向きが決まる
    lay: dict[str, list[str]] = {i: [] for i in ids}
    inner = []
    for e in edges:
        a, b = e["from"], e["to"]
        if band[a] < band[b]:
            lay[a].append(b)
        elif band[a] > band[b]:
            lay[b].append(a)
            e["rev"] = True
            if v["layered"] and a in gi_nodes(nodes, gi) and b in gi_nodes(nodes, gi):
                e["up"] = True   # 層の決まりがある図で、下の層から上の層へ向かう線
        else:
            inner.append(e)
    # 同じまとまりの中の線: 深さ優先でたどり、たどっている途中の箱へ戻る線（循環を閉じる線）を逆向きにして置く
    inner_out: dict[str, list[tuple[str, dict]]] = {i: [] for i in ids}
    for e in inner:
        inner_out[e["from"]].append((e["to"], e))
    state: dict[str, int] = {}
    for root in ids:
        if root in state:
            continue
        work = [(root, 0)]
        state[root] = 1
        while work:
            x, i = work.pop()
            nxt = inner_out[x]
            if i < len(nxt):
                work.append((x, i + 1))
                w, e = nxt[i]
                if state.get(w) == 1:
                    e["rev"] = True
                elif w not in state:
                    state[w] = 1
                    work.append((w, 0))
            else:
                state[x] = 2
    for e in inner:
        a, b = (e["to"], e["from"]) if e.get("rev") else (e["from"], e["to"])
        lay[a].append(b)
    # まとまりの中の段（使う側が上）。同じまとまりの中の線だけで、いちばん長い道の長さを段にする
    same = {i: [w for w in lay[i] if band[w] == band[i]] for i in ids}
    depth: dict[str, int] = {}

    def longest(i: str) -> int:
        stack = [(i, 0)]
        while stack:
            x, k = stack.pop()
            if x in depth:
                continue
            pend = [w for w in same_in[x] if w not in depth]
            if pend:
                stack.append((x, k))
                stack.extend((w, 0) for w in pend)
                continue
            depth[x] = 1 + max((depth[w] for w in same_in[x]), default=-1)
        return depth[i]

    same_in: dict[str, list[str]] = {i: [] for i in ids}
    for a in ids:
        for b in same[a]:
            same_in[b].append(a)
    for i in ids:
        longest(i)
    # 使う相手のすぐ上まで下げる（線を短くする。使う側が上、の順は変わらない）。深い段の箱から順に決める
    for i in sorted(ids, key=lambda x: -depth[x]):
        if same[i]:
            depth[i] = min(depth[w] for w in same[i]) - 1
    # 段を通しの番号にする。1段に ROW_MAX を超える箱は、段を分ける（同じ段の箱どうしに線は無い）
    rows: list[list[str]] = []
    grows: dict[int, list[int]] = {}
    for b in sorted(set(band.values())):
        members = [i for i in ids if band[i] == b]
        for dep in range(max(depth[i] for i in members) + 1):
            line = [i for i in members if depth[i] == dep]
            parts = -(-len(line) // ROW_MAX)
            size = -(-len(line) // parts) if parts else 0
            for k in range(parts):
                grows.setdefault(b, []).append(len(rows))
                rows.append(line[k * size:(k + 1) * size])
    row_of = {i: r for r, line in enumerate(rows) for i in line}
    for n in nodes:
        n["row"] = row_of[n["id"]]
    for k, g in enumerate(groups):
        g["rows"] = [grows[k][0], grows[k][-1]]
    v["rows"] = len(rows)


def gi_nodes(nodes: list[dict], gi: dict) -> set[str]:
    return {n["id"] for n in nodes if n["in"] in gi}


# ── 置き場所 ──────────────────────────────────────────
FS, TFS, NFS = 13, 11, 11
NODE_H, TECH_H, PADX, GLYPH = 36, 15, 14, 20
GAP_X, GAP_Y, BAND_PAD, BAND_HEAD, BAND_GAP, MARGIN = 26, 48, 12, 22, 14, 8
DUMMY_W = 10


def units(s: str) -> float:
    return sum(0.62 if "\x20" <= ch <= "\x7e" else 1.0 for ch in str(s or ""))


def node_size(n: dict) -> tuple[float, float]:
    w = max(units(n["label"]) * FS, units(n.get("tech")) * TFS * 0.95) + PADX * 2 + (GLYPH if n.get("kind") else 0)
    return max(72.0, round(w, 1)), NODE_H + (TECH_H if n.get("tech") else 0)


def crossings(rows: list[list[str]], links: list[tuple[str, str]]) -> int:
    """隣り合う段の間の線の交わりの数（置き方を比べるのに使う）。"""
    pos = {x: (r, k) for r, line in enumerate(rows) for k, x in enumerate(line)}
    by_gap: dict[int, list[tuple[int, int]]] = {}
    for a, b in links:
        (ra, ka), (rb, kb) = pos[a], pos[b]
        if rb - ra == 1:
            by_gap.setdefault(ra, []).append((ka, kb))
    n = 0
    for seg in by_gap.values():
        for i in range(len(seg)):
            for j in range(i + 1, len(seg)):
                (a1, b1), (a2, b2) = seg[i], seg[j]
                if (a1 - a2) * (b1 - b2) < 0:
                    n += 1
    return n


def layout(v: dict) -> dict:
    """箱の置き場所（左上と大きさ）・まとまりの枠・線の通り道（使う側から使われる側へ。点の列）。同じ塊なら同じ結果。"""
    nodes, edges, groups = v["nodes"], v["edges"], v["groups"]
    size = {n["id"]: node_size(n) for n in nodes}
    row_of = {n["id"]: n["row"] for n in nodes}
    rows: list[list[str]] = [[] for _ in range(v["rows"])]
    for n in nodes:
        rows[n["row"]].append(n["id"])
    # 2段以上をまたぐ線は、間の段に通り道の点（幅の小さい見えない箱）を置く
    links: list[tuple[str, str]] = []
    chains: list[list[str]] = []
    for k, e in enumerate(edges):
        a, b = (e["to"], e["from"]) if e.get("rev") else (e["from"], e["to"])
        chain = [a]
        for r in range(row_of[a] + 1, row_of[b]):
            dm = f"\x00{k}:{r}"
            rows[r].append(dm)
            size[dm] = (DUMMY_W, 0)
            chain.append(dm)
        chain.append(b)
        chains.append(chain)
        links += list(zip(chain, chain[1:]))
    up: dict[str, list[str]] = {}
    down: dict[str, list[str]] = {}
    for a, b in links:
        down.setdefault(a, []).append(b)
        up.setdefault(b, []).append(a)

    # 段の中の並び: 隣の段のつながる相手の平均の位置で並べ替えるのを、上から・下からと繰り返し、交わりが最も少ない並びを残す
    def sweep(order: list[list[str]], nb: dict[str, list[str]], rng) -> None:
        for r in rng:
            pos = {x: k for line in order for k, x in enumerate(line)}
            key = {x: (sum(pos[w] for w in nb[x]) / len(nb[x]) if nb.get(x) else k) for k, x in enumerate(order[r])}
            order[r] = sorted(order[r], key=lambda x: (key[x], order[r].index(x)))

    best, best_n = [list(line) for line in rows], crossings(rows, links)
    cur = [list(line) for line in rows]
    for _ in range(6):
        sweep(cur, up, range(1, len(cur)))
        sweep(cur, down, range(len(cur) - 2, -1, -1))
        n = crossings(cur, links)
        if n < best_n:
            best, best_n = [list(line) for line in cur], n
        if best_n == 0:
            break
    rows = best

    # 横の位置: まず左から詰めて真ん中をそろえ、そのあと、つながる相手の真上・真下へ寄せる（並びと間は保つ）
    cx: dict[str, float] = {}
    for line in rows:
        x = 0.0
        for i in line:
            cx[i] = x + size[i][0] / 2
            x += size[i][0] + GAP_X
        shift = (x - GAP_X) / 2
        for i in line:
            cx[i] -= shift

    def place(line: list[str], want: dict[str, float]) -> None:
        left, x = {}, None
        for i in line:
            c = want[i] if x is None else max(want[i], x + GAP_X + size[i][0] / 2)
            left[i] = c
            x = c + size[i][0] / 2
        right, x = {}, None
        for i in reversed(line):
            c = want[i] if x is None else min(want[i], x - GAP_X - size[i][0] / 2)
            right[i] = c
            x = c - size[i][0] / 2
        mid = {i: (left[i] + right[i]) / 2 for i in line}
        x = None   # 平均で間が詰まった所を、左から直す
        for i in line:
            c = mid[i] if x is None else max(mid[i], x + GAP_X + size[i][0] / 2)
            cx[i] = c
            x = c + size[i][0] / 2

    for it in range(8):
        rng = range(1, len(rows)) if it % 2 == 0 else range(len(rows) - 2, -1, -1)
        nb = up if it % 2 == 0 else down
        for r in rng:
            want = {i: (sum(cx[w] for w in nb[i]) / len(nb[i]) if nb.get(i) else cx[i]) for i in rows[r]}
            place(rows[r], want)

    # 縦の位置: 段ごとに箱の高さの最大をとり、まとまりの名前と枠の分をあける
    row_h = [max((size[i][1] for i in line), default=0) or NODE_H for line in rows]
    head_at = {g["rows"][0]: g for g in groups}
    tail_at = {g["rows"][1]: g for g in groups}
    y, row_y = float(MARGIN), []
    for r in range(len(rows)):
        if r in head_at:
            y += BAND_HEAD + BAND_PAD
        row_y.append(y)
        y += row_h[r]
        if r in tail_at:
            y += BAND_PAD + BAND_GAP - GAP_Y * 0.35
        y += GAP_Y
    height = y - GAP_Y + MARGIN
    min_x = min(cx[i] - size[i][0] / 2 for line in rows for i in line)
    max_x = max(cx[i] + size[i][0] / 2 for line in rows for i in line)
    pad = BAND_PAD + 4 if groups else 0
    off = MARGIN + pad - min_x
    width = max_x - min_x + 2 * (MARGIN + pad)
    box = {}
    for n in nodes:
        i = n["id"]
        w, h = size[i]
        box[i] = [round(cx[i] + off - w / 2, 1), round(row_y[row_of[i]] + (row_h[row_of[i]] - h) / 2, 1), w, h]
    bands = []
    for g in groups:
        r0, r1 = g["rows"]
        top = row_y[r0] - BAND_HEAD - BAND_PAD
        bands.append({"id": g["id"], "x": MARGIN, "y": round(top, 1), "w": round(width - 2 * MARGIN, 1),
                      "h": round(row_y[r1] + row_h[r1] + BAND_PAD - top, 1)})

    # 線の通り道。箱の下の辺から出て、次の段の箱の上の辺に入る。1つの辺に複数の線が付くときは、相手の横の位置の順に
    # 1本ずつ場所を分ける（同じ相手との行きと帰りの線も、重ねずに並べる）
    bottom: dict[str, list[tuple[float, int]]] = {i: [] for i in box}
    top: dict[str, list[tuple[float, int]]] = {i: [] for i in box}
    for k, chain in enumerate(chains):
        bottom[chain[0]].append((cx[chain[1]], k))
        top[chain[-1]].append((cx[chain[-2]], k))

    def spread(i: str, side: dict) -> dict[int, float]:
        ks = sorted(side[i])
        step = min(18.0, (size[i][0] - 24) / max(1, len(ks) - 1)) if len(ks) > 1 else 0
        return {k: cx[i] + off + (j - (len(ks) - 1) / 2) * step for j, (_, k) in enumerate(ks)}

    out_port = {i: spread(i, bottom) for i in box}
    in_port = {i: spread(i, top) for i in box}

    def curve_x(p: list[float], q: list[float], y: float) -> float:
        """p から q への線（画面が描くのと同じ、縦に出て縦に入る曲線）の、高さ y の所の横の位置。"""
        (x1, y1), (x2, y2) = p, q
        if abs(x1 - x2) < 0.6 or y2 == y1:
            return x1
        ym, lo, hi = (y1 + y2) / 2, 0.0, 1.0
        for _ in range(24):
            t = (lo + hi) / 2
            yt = (1 - t) ** 3 * y1 + 3 * (1 - t) ** 2 * t * ym + 3 * (1 - t) * t * t * ym + t ** 3 * y2
            lo, hi = (t, hi) if yt < y else (lo, t)
        t = (lo + hi) / 2
        return ((1 - t) ** 3 + 3 * (1 - t) ** 2 * t) * x1 + (3 * (1 - t) * t * t + t ** 3) * x2

    paths = []
    placed: list[tuple[float, float, float]] = []
    n_lab = sum(1 for e in edges if e.get("label"))
    for k, (e, chain) in enumerate(zip(edges, chains)):
        pts = []
        for j, i in enumerate(chain):
            if i in box:
                bx, by, bw, bh = box[i]
                pts.append([round(out_port[i][k], 1), round(by + bh, 1)] if j == 0 else [round(in_port[i][k], 1), round(by, 1)])
            else:   # 通り道の点は、その段の上の端と下の端をまっすぐ通る
                r = int(i.split(":")[1])
                x = round(cx[i] + off, 1)
                pts += [[x, round(row_y[r], 1)], [x, round(row_y[r] + row_h[r], 1)]]
        item = {}
        if e.get("label") and n_lab <= 12:
            # 線の名前は、上の箱を出てすぐの、段と段の間の空いた帯に置く（まとまりの枠と名前の行には重ねない）。
            # ほかの線の名前と重なるなら、帯の中で上下にずらす
            r0 = row_of[chain[0]]
            ya = pts[0][1] + (BAND_PAD + 4 if r0 in tail_at else 3)
            yb = row_y[r0 + 1] - (BAND_HEAD + BAND_PAD + 4 if r0 + 1 in head_at else 3)
            w = units(e["label"]) * NFS + 8
            mid = (ya + yb) / 2
            spots = [mid + d for d in (0, -12, 12) if ya + 5 <= mid + d <= yb - 5] or [mid]
            side = w / 2 + 12   # 線の上に置けないときは、線のすぐ横へずらす（行きと帰りの線が並ぶ所など）
            cands = [(dx, y) for y in spots[:1] for dx in (0, side, -side)] + [(dx, y) for y in spots[1:] for dx in (0, side, -side)]
            lx, ly = curve_x(pts[0], pts[1], spots[0]), spots[0]
            for dx, y in cands:
                x = curve_x(pts[0], pts[1], y) + dx
                if not any(abs(x - px) < (w + pw) / 2 + 3 and abs(y - py) < 15 for px, py, pw in placed):
                    lx, ly = x, y
                    break
            placed.append((lx, ly, w))
            item["lab"] = [round(lx, 1), round(ly, 1)]
        if e.get("rev"):
            pts.reverse()   # 矢じりは、使われる側（線の向かう先）に付ける
        item["pts"] = pts
        paths.append(item)
    # 線の名前が図の左右の端からはみ出すなら、図を広げる（線のすぐ横へずらした名前が、右端で切れていた）
    left = min([lx - w / 2 for lx, _, w in placed] + [MARGIN]) - 2
    right = max([lx + w / 2 for lx, _, w in placed] + [width - MARGIN]) + 2
    dx = round(max(0.0, MARGIN - left), 1)
    width = max(width, right + MARGIN) + dx
    if dx:
        for b in box.values():
            b[0] = round(b[0] + dx, 1)
        for item in paths:
            item["pts"] = [[round(x + dx, 1), y] for x, y in item["pts"]]
            if "lab" in item:
                item["lab"][0] = round(item["lab"][0] + dx, 1)
    for b in bands:   # まとまりの枠は、図の幅いっぱい
        b["w"] = round(width - 2 * MARGIN, 1)
    return {"w": round(width, 1), "h": round(height, 1), "nodes": box, "bands": bands, "edges": paths, "cross": best_n}
