"""棚（アーティファクト棚の写し）の本文を、先生役の作業フォルダに写す。

写し方は棚の案内係と同じ shelf.guide.build_mirror をそのまま呼ぶ（見出しの行に # を付けた <id>.txt）。
先生役はこのフォルダだけを Read・Grep で読む。答えの「」の中身は、ここの本文と畳んだ字で照らして、
見つからなければ画面に「本文に無い」と出す（捏造ゼロ）。
"""
import re
import sys
import threading
from pathlib import Path

from . import config
from .db import fold

_lock = threading.Lock()
_state = {"rows": {}, "folded": {}, "sig": None}
ID_RE = re.compile(r"〔([A-Za-z0-9_-]{6,64})(?:｜([^〕]*))?〕")
QUOTE_RE = re.compile(r"「([^「」]{8,400})」")


def _guide():
    p = str(config.SHELF_TOOL_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)
    from shelf import guide  # noqa: E402  棚の道具（読み取りだけ）
    return guide


def refresh() -> dict:
    """写しを作り直す（中身が同じ1枚は書かない）。目録の行数と字数を返す。"""
    config.ensure_dirs()
    if not (config.SHELF_LIB / "shelf-data.json").exists():
        with _lock:
            _state.update(rows={}, folded={})
        return {"pages": 0, "chars": 0, "error": "棚の写しが見つかりません"}
    g = _guide()
    rows, marked = g.build_mirror(config.SHELF_LIB, config.CORPUS_DIR)
    folded = {iid: fold(t) for iid, t in marked.items()}
    with _lock:
        _state.update(rows=rows, folded=folded)
    return {"pages": len(rows), "chars": sum(len(t) for t in marked.values())}


def catalog() -> str:
    with _lock:
        rows = dict(_state["rows"])
    out = []
    for iid, it in rows.items():
        cat = str(it.get("category") or "")
        when = str(it.get("published_at") or it.get("updated") or "")[:10]
        out.append(f"{iid}｜{it.get('title', '')}｜{cat}｜{when}")
    return "\n".join(out)


def titles() -> list[str]:
    with _lock:
        rows = dict(_state["rows"])
    out = []
    for it in rows.values():
        t = str(it.get("title") or "").strip()
        if t and t not in out:
            out.append(t)
    return out


def title_of(iid: str) -> str | None:
    with _lock:
        it = _state["rows"].get(iid)
    return str(it.get("title")) if it else None


def check_quotes(md: str) -> list[dict]:
    """答えの中の「」（8字以上）を棚の本文と照らす。札のあるページを先に見て、無ければ全体を見る。"""
    with _lock:
        folded = dict(_state["folded"])
    cited = [m.group(1) for m in ID_RE.finditer(md)]
    out = []
    for m in QUOTE_RE.finditer(md):
        q = m.group(1)
        fq = fold(q)
        where = None
        for iid in cited:
            if fq in folded.get(iid, ""):
                where = iid
                break
        if where is None:
            for iid, t in folded.items():
                if fq in t:
                    where = iid
                    break
        out.append({"quote": q, "found": where})
    return out


def cards(md: str) -> list[dict]:
    """〔id｜見出し〕 の札を、題つきで返す（目録に無い id は known=False）。"""
    out, seen = [], set()
    for m in ID_RE.finditer(md):
        key = (m.group(1), m.group(2) or "")
        if key in seen:
            continue
        seen.add(key)
        t = title_of(m.group(1))
        out.append({"id": m.group(1), "heading": m.group(2) or "", "title": t or "", "known": t is not None})
    return out


def shelf_page_path(iid: str) -> Path | None:
    p = config.SHELF_LIB / "pages" / f"{iid}.html"
    return p if p.exists() else None
