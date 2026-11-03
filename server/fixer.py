"""整形役。声の文字起こし（Apple と、2本目の Scribe か端末内の Haas）を突き合わせて、聞き違いだけを直す。

言い換え・要約・足し算はしない。直した箇所は edits に1つずつ出し、画面がそれを下線で見せて、本人が1つずつ戻せる。
直しすぎの見張り: 直した文が元の文（base_text）と大きく違えば直しを捨てて元の文を使う。元の文は、Scribe があれば
Scribe、それ以外は Apple。Haas は用語に寄せると前後の語を落とすことがあり（「の違い」が消えた）、用語を直すと字数も
変わるので長さでは見分けられない。用語が崩れても語が欠けない Apple の方を戻す先にする。
"""
import difflib
import json
import re

from . import brain, config, corpus, db
from .db import fold

SYSTEM = """あなたは声の文字起こしの直し役です。本人が学習アプリに声で話しかけた内容を、2つの文字起こし（Apple と、2本目の Scribe か Haas）から、本人が実際に言った文に戻します。

決まり
一、直すのは聞き違いだけです。同じ音の別の字（伴奏→伴走、寡婦→加付）、用語の崩れ、数字の取り違え、明らかな誤変換を直します。言い換え・要約・敬語への直し・内容の足し算はしません。話し言葉のままにします。
二、「えー」「あの」「えっと」のような言いよどみは消してかまいません（edits には出しません）。言い直しは最後の言い方を残します。
三、手がかりは、用語集（これまでに出た概念の名前。この話題のものが先）、棚のページの題、本人の過去の聞き違い、直前のやりとり、Apple の確信度の低い字（low）と別候補（alts）、2つの文字起こしの違いです。2本目（Scribe か Haas）には用語の一覧を渡してあるので、用語は2本目が正しいことが多いです。ただし Haas は用語に寄せたときに前後の語を落とすことがあります。Apple にあって Haas に無い語は、聞き違いでなければ Apple から戻します。
四、決めきれない箇所は勝手に決めず、もっともらしい方を本文に書いたうえで unsure に候補を並べます。
五、出力は JSON だけです。前置きもコードの囲みも付けません。

出力の形
{"text": "直した文", "edits": [{"from": "文字起こしの字", "to": "直した字", "why": "10字以内の理由"}], "unsure": [{"span": "本文の字", "options": ["候補1", "候補2"]}], "title": "この発言の見出し（16字以内・体言止め）", "kind": "question か answer か confirm か command"}

kind は、新しい問いなら question、直前に先生役が出した確かめの問いへの答えなら answer、前の答えの中身を自分の言葉で言い直して合っているかを確かめる発言（「確認ですけど」「〜ってことですよね」「つまり〜」）なら confirm、「もっと詳しく」「図にして」「次へ」のような進め方の指示なら command です。"""

POOL = brain.SparePool(SYSTEM, config.FIXER_MODEL, config.FIXER_EFFORT)


def glossary(session_id: int, limit: int = 120) -> list[str]:
    """この話題で出た概念の名前（新しい順）を先に、ほかの話題の概念の名前（新しい順）を後に並べる。"""
    with db.tx() as con:
        here = [r["label"] for r in db.rows(con, """
            SELECT c.label FROM session_concept sc JOIN concept c ON c.id = sc.concept_id
            WHERE sc.session_id = ? ORDER BY sc.last_turn DESC LIMIT ?""", (session_id, limit))]
        known = [r["label"] for r in db.rows(con, "SELECT label FROM concept ORDER BY updated_at DESC LIMIT ?", (limit,))]
    out = []
    for x in here + known:
        if x not in out:
            out.append(x)
    return out[:limit]


def mishears(limit: int = 40) -> list[dict]:
    with db.tx() as con:
        return db.rows(con, "SELECT heard, meant, n FROM mishear ORDER BY n DESC, updated_at DESC LIMIT ?", (limit,))


ENGINE_NAMES = {"scribe": "Scribe", "haas": "Haas"}
KINDS = ("question", "answer", "confirm", "command")


def base_text(apple_text: str, second: str | None, engine: str = "scribe") -> str:
    """直しを捨てるときに戻す元の文。Scribe はそのまま。Haas は語を落とすことがあるので Apple（Apple が無いときだけ Haas）。"""
    if not second:
        return apple_text
    if engine == "haas" and apple_text:
        return apple_text
    return second


def build_input(apple: dict | None, scribe: str | None, terms: list[str], miss: list[dict], context: str,
                engine: str = "scribe") -> str:
    parts = []
    parts.append("<用語集>\n" + ("、".join(terms) if terms else "（まだありません）") + "\n</用語集>")
    titles = corpus.titles()
    if titles:
        parts.append("<棚のページの題（本人がよく話す話題の言葉）>\n" + "、".join(titles) + "\n</棚のページの題>")
    if miss:
        parts.append("<過去の聞き違い>\n" + "\n".join(f"{m['heard']} → {m['meant']}（{m['n']}回）" for m in miss) + "\n</過去の聞き違い>")
    parts.append("<直前のやりとり>\n" + (context or "（この話題の最初の発言です）") + "\n</直前のやりとり>")
    if apple:
        low = "、".join(f"{x['text']}({x['conf']})" for x in apple.get("low", [])[:20]) or "なし"
        alts = "、".join(f"{x['text']}→{'/'.join(x['alts'])}" for x in apple.get("alts", [])[:20]) or "なし"
        parts.append(f"<Apple>\n{apple.get('text', '')}\n確信度の低い字: {low}\n別候補: {alts}\n</Apple>")
    else:
        parts.append("<Apple>（失敗）</Apple>")
    name = ENGINE_NAMES.get(engine, "Scribe")
    parts.append(f"<{name}>\n{scribe}\n</{name}>" if scribe is not None else "<2本目>（使っていません）</2本目>")
    return "\n\n".join(parts)


def parse(raw: str) -> dict:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < 0:
        raise ValueError("JSON がありません")
    return json.loads(s[i:j + 1])


def verify(d: dict, apple_text: str, scribe_text: str | None, engine: str = "scribe") -> dict:
    """整形役の結果を確かめる。直しすぎなら元の文に戻し、根拠の無い edits は落とす。scribe_text は2本目の文。"""
    base = base_text(apple_text, scribe_text, engine)
    text = str(d.get("text") or "").strip()
    fallback = None
    if not text:
        text, fallback = base, "空の直し"
    else:
        ratio = difflib.SequenceMatcher(None, fold(base), fold(text)).ratio()
        if ratio < 0.6:
            text, fallback = base, f"直しすぎ（元の文との一致 {ratio:.2f}）"
    raw_all = fold(apple_text) + "\n" + fold(scribe_text or "")
    edits = []
    if not fallback:
        for e in d.get("edits") or []:
            fr, to = str(e.get("from") or "").strip(), str(e.get("to") or "").strip()
            if fr and to and fr != to and fold(to) in fold(text) and fold(fr) in raw_all:
                edits.append({"from": fr, "to": to, "why": str(e.get("why") or "")[:20]})
    unsure = []
    for u in d.get("unsure") or []:
        span = str(u.get("span") or "").strip()
        opts = [str(o) for o in (u.get("options") or []) if str(o).strip()][:4]
        if span and fold(span) in fold(text) and opts:
            unsure.append({"span": span, "options": opts})
    title = str(d.get("title") or "").strip()[:20] or text[:16]
    kind = d.get("kind") if d.get("kind") in KINDS else "question"
    return {"text": text, "edits": edits, "unsure": unsure, "title": title, "kind": kind, "fallback": fallback}


async def fix(session_id: int, apple: dict | None, scribe: str | None, context: str, engine: str = "scribe") -> dict:
    apple_text = (apple or {}).get("text", "")
    terms = glossary(session_id)
    content = build_input(apple, scribe, terms, mishears(), context, engine)
    try:
        s = await POOL.take()
        raw = await s.ask(content, timeout=45)
        d = parse(raw)
    except Exception as e:
        base = base_text(apple_text, scribe, engine)
        return {"text": base, "edits": [], "unsure": [], "title": base[:16], "kind": "question",
                "fallback": f"整形役が使えませんでした（{e}）"}
    return verify(d, apple_text, scribe, engine)
