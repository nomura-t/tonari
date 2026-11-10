"""二度目の判定役。先生役（opus）が当たり・半分と判定した答えを、別の役（sonnet）がもう一度判定する。

先生役は自分で作った確かめの問いを自分で採点するので、1回の判定を理解の記録の根拠にしない（研究 d の 1-3:
人の評定者どうしでも答えの段の判定は一致しにくい）。二度目と一致した当たり・半分だけを記録する（tutor.apply_grades）。
判定役は記録も問いも作らず、渡された材料だけで hit・partial・miss を返す。取れなかったときは None（記録しない側）。

v0.4（A5）: たとえの塊の対も、本文と対の一覧を渡して対ごとに ok・ng を返させる（check_pairs）。ng の対は捨てる。
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


def build_input(session_id: int, grades: list[dict], said: str, check_id: int | None = None) -> str:
    """判定役に渡す文。戻ったときの問いに答えた往復（check_id）は、その問いと想定の答えを渡す。それ以外は、判定の
    中心・相手・関係の種類が同じ問いを引く（同じ組の問いが2つあると新しいほうになるので、check_id があればそれを使う）。"""
    items = []
    with db.tx() as con:
        asked = db.row(con, "SELECT q, a FROM checkq WHERE id=? AND session_id=?", (check_id, session_id)) if check_id else None
        for i, g in enumerate(grades, 1):
            c, t, r = str(g.get("concept") or ""), str(g.get("target") or ""), str(g.get("rel") or "")
            q = asked or db.row(con, """SELECT q, a FROM checkq WHERE session_id=? AND concept=? AND target=? AND rel=?
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


PAIR_SYSTEM = """あなたは学習アプリの判定役です。先生役が書いた答えの本文と、たとえの対応の一覧を読み、対ごとに、書かれた「共通する働き」が、たとえの側の物と実際の名前の両方で成り立つかを判定します。

決まり
一、ok は、共通する働きが、たとえの側の物（元の世界）でも、実際の名前（学ぶもの）でも成り立ち、本文の説明とも食い違わないときです。
二、ng は、どちらかの側で働きが成り立たないとき、実際の名前の働きが事実として誤っているとき、本文の説明と食い違うとき、働きの違う物どうしが結ばれているときです。
三、根拠は、本文と一覧と、その分野の一般に確かめられる事実だけです。
四、出力は JSON だけです。前置きもコードの囲みも付けません。

出力の形
{"results": ["ok か ng", ...]}（渡した対と同じ順・同じ数）"""

# たとえの対の二度目の確かめ（v0.4 の A5）。先生役が自分のたとえを自分で確かめないため（13.1 の二度目の判定と同じ考え）
PAIR_POOL = brain.SparePool(PAIR_SYSTEM, config.FIXER_MODEL, config.FIXER_EFFORT)
PAIR_TIMEOUT = 30


def pair_input(body: str, v: dict) -> str:
    lines = [f"{i}. たとえの側「{p['s']}」{'（' + p['s_val'] + '）' if p.get('s_val') else ''} ＝ 実際の名前「{p['t']}」"
             f"{'（' + p['t_val'] + '）' if p.get('t_val') else ''}・共通する働き「{p.get('role') or '書かれていない'}」"
             for i, p in enumerate(v["pairs"], 1)]
    return (f"<たとえ>\n元の世界: {v.get('source')}・学ぶもの: {v.get('target')}・共通する関係: {v.get('relation') or '書かれていない'}\n"
            + "\n".join(lines) + "\n</たとえ>\n<本文>\n" + body + "\n</本文>")


def parse_pairs(raw: str, n: int) -> list[str] | None:
    """対ごとの ok / ng。数が合わない・読めない結果は None（確かめていない扱い）。"""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    i, j = s.find("{"), s.rfind("}")
    try:
        res = json.loads(s[i:j + 1]).get("results") if i >= 0 and j > i else None
    except ValueError:
        return None
    if not isinstance(res, list) or len(res) != n or any(x not in ("ok", "ng") for x in res):
        return None
    return res


async def check_pairs(body: str, views: list[dict]) -> list[dict]:
    """たとえの塊ごとに、判定役が対を確かめる。返すのは塊ごとの {checked, ng（捨てる対の実際の名前）, res}。
    判定役が取れなかった塊は checked=False（塊は出して「確かめていない対応」の札を付ける）。"""
    out = []
    for v in views:
        res = None
        try:
            s = await PAIR_POOL.take()
            res = parse_pairs(await s.ask(pair_input(body, v), timeout=PAIR_TIMEOUT), len(v["pairs"]))
        except Exception:
            res = None
        if res is None:
            out.append({"checked": False})
        else:
            out.append({"checked": True, "res": res, "ng": [p["t"] for p, r in zip(v["pairs"], res) if r == "ng"]})
    return out


async def second_opinion(session_id: int, grades: list[dict], said: str, check_id: int | None = None) -> list[str | None]:
    """当たり・半分の判定を、判定役がもう一度判定する。miss の項目と、判定役が使えないときは None。
    check_id は、戻ったときに出した問いに答えた往復のその問い（判定役にはその問いと想定の答えを渡す）。"""
    idx = [i for i, g in enumerate(grades) if g.get("result") in ("hit", "partial")]
    out: list[str | None] = [None] * len(grades)
    if not idx:
        return out
    try:
        s = await POOL.take()
        raw = await s.ask(build_input(session_id, [grades[i] for i in idx], said, check_id), timeout=45)
        for i, r in zip(idx, parse(raw, len(idx))):
            out[i] = r
    except Exception:
        pass   # 取れなかった当たり・半分は記録しない（apply_grades が一致しないものとして扱う）
    return out
