"""二度目の判定役。先生役（opus）が当たり・半分と判定した答えを、別の役（sonnet）がもう一度判定する。

先生役は自分で作った確かめの問いを自分で採点するので、1回の判定を理解の記録の根拠にしない（研究 d の 1-3:
人の評定者どうしでも答えの段の判定は一致しにくい）。二度目と一致した当たり・半分だけを記録する（tutor.apply_grades）。
判定役は記録も問いも作らず、渡された材料だけで hit・partial・miss を返す。取れなかったときは None（記録しない側）。
"""
import json
import re

from . import brain, config, db, tutor

SYSTEM = """あなたは学習アプリの判定役です。先生役が出した確かめの問い（または確かめたい関係）と、本人の発言を読み、本人の発言がその関係を言えているかを判定します。

決まり
一、判定は hit（関係の決め手を本人が言えている）、partial（方向は合っているが決め手が欠けている、または一部が違う）、miss（言えていない・違う）の3つです。
二、根拠は本人の発言の中身だけです。発言に無いことを補って当たりにしません。言い回しや用語が想定の答えと違っても、決め手が同じなら hit です。
三、出力は JSON だけです。前置きもコードの囲みも付けません。

出力の形
{"results": ["hit か partial か miss", ...]}（渡した項目と同じ順・同じ数）"""

POOL = brain.SparePool(SYSTEM, config.FIXER_MODEL, config.FIXER_EFFORT)


def build_input(session_id: int, grades: list[dict], said: str) -> str:
    items = []
    with db.tx() as con:
        for i, g in enumerate(grades, 1):
            c, t, r = str(g.get("concept") or ""), str(g.get("target") or ""), str(g.get("rel") or "")
            q = db.row(con, """SELECT q, a FROM checkq WHERE session_id=? AND concept=? AND target=? AND rel=?
                               ORDER BY id DESC LIMIT 1""", (session_id, c, t, r))
            rid = tutor.find_relation(con, c, t, r)
            rel = db.row(con, "SELECT detail, why FROM relation WHERE id=?", (rid,)) if rid else None
            line = f"{i}. 中心 {c}・相手 {t}・関係の種類 {r}"
            if rel and (rel["detail"] or rel["why"]):
                line += f"・記録の関係の中身 {rel['detail'] or ''} {rel['why'] or ''}".rstrip()
            if q:
                line += f"\n   問い: {q['q']}\n   想定の答え: {q['a']}"
            items.append(line)
    return "<判定する項目>\n" + "\n".join(items) + "\n</判定する項目>\n<本人の発言>\n" + said + "\n</本人の発言>"


def parse(raw: str, n: int) -> list[str | None]:
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    i, j = s.find("{"), s.rfind("}")
    res = json.loads(s[i:j + 1]).get("results") if i >= 0 and j > i else None
    if not isinstance(res, list):
        return [None] * n
    return [x if x in ("hit", "partial", "miss") else None for x in res[:n]] + [None] * max(0, n - len(res))


async def second_opinion(session_id: int, grades: list[dict], said: str) -> list[str | None]:
    """当たり・半分の判定を、判定役がもう一度判定する。miss の項目と、判定役が使えないときは None。"""
    idx = [i for i, g in enumerate(grades) if g.get("result") in ("hit", "partial")]
    out: list[str | None] = [None] * len(grades)
    if not idx:
        return out
    try:
        s = await POOL.take()
        raw = await s.ask(build_input(session_id, [grades[i] for i in idx], said), timeout=45)
        for i, r in zip(idx, parse(raw, len(idx))):
            out[i] = r
    except Exception:
        pass   # 取れなかった当たり・半分は記録しない（apply_grades が一致しないものとして扱う）
    return out
