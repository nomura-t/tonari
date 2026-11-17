"""予想の照らし合わせ役（v0.6）。読む前の予想と、届いた答えを照らし合わせて、答えの終わりに短く返す。

本人の指摘（2026-11-15）: 予想を言っても何も返らず、空中に投げ出されたままになる。予想の効き目は、外れたときの驚きが
正しい答えへの注意を上げることにあり、それは「どこが予想と違ったか」を本人が見分けられたときに出る（研究 d の 3-5・3-6・3-9）。
返しが繰り返し来ないと成績は下がり、良かった点と足りなかった点を短い言葉で返すと、成績も、もっとやりたい気持ちも
上がった（研究 g6 の 6-1）。v0.6 の最初の形は、予想を答えの上に見せ直すだけだった（DESIGN 17.12）。

作りは研究 g6 に合わせる。
- 大事な点は、照らし合わせ役に選ばせない（LLM の返しが人にいちばん劣ったのは、大事な点を選ぶ力だった。g6 の 4-1）。
  先生役の答えの最初の段落（問いへの答えそのもの）と「決め手」の文を機械で抜き出して「答えの核」として渡し、
  照らし合わせ役には、それが予想に入っていたかだけを判断させる。
- 画面に出す字は、予想の中の字か答えの中の字をそのまま使う。照らし合わせ役が文を書くのは、食い違いの1文だけで、
  食い違いは探させない（はっきりあるときだけ。g6 の 4-2）。抜き出した字は機械が照らし、根拠の無い項目は出さない。
- 点も成績も付けない。全体の出来を段で判定させない（g6 の 2-1・2-2・3-2）。出すのは、決まった基準の2つ
  （答えの核が予想に入っていたか、いなかったか）だけ（g6 の 2-4）。
- 理解の記録（分かる・分からない）には入れない（予想は読む前の当て推量で、外れてよい。g6 の 6-2）。

照らし合わせ役は sonnet の予備を1回で使い捨てる。先生役の指示（tutor.SYSTEM）とも記録役とも別で、答えの表示は遅らせない。
`TONARI_PREDICT_FEEDBACK=off` で止められる。
"""
import json
import os
import re
import unicodedata

from . import brain, config

# 記録役を止めているとき（TONARI_RECORDER=off。検査と、答えのあとの役を使わない設定）は、照らし合わせ役も動かさない
ENABLED = os.environ.get("TONARI_PREDICT_FEEDBACK", "on") != "off" and config.RECORDER != "off"
MODEL = os.environ.get("TONARI_PREDICT_FEEDBACK_MODEL", "") or config.RECORDER_MODEL
SAID_MAX, PRED_MAX, ANSWER_MAX, TIMEOUT = 600, 800, 3500, 60
DIFF_MAX, QUOTE_MAX, LEAD_MAX, SHOW_MAX = 110, 60, 220, 110
STALE_SEC = 120          # 走り始めの印がこれより古ければ、取れなかったものとして扱う（サーバーが途中で止まった分）

SYSTEM = """あなたは学習アプリの、予想と答えを照らし合わせる役です。本人（学ぶ人）は、問いを送ったあと、答えを読む前に「答えはこうなると思う」という予想を一言言いました。渡されるのは、本人の問い、本人の予想、先生役の答えの本文、その本文から機械が抜き出した「答えの核」（問いへの答えそのもの）と、あれば「決め手」の文です。予想と答えを照らし合わせた結果を返します。

決まり
一、照らし合わせる相手は、渡された先生役の答えだけです。あなた自身の知識で、予想や答えの正しさを判定しません。
二、core は、予想が「答えの核」と同じことを言っているかです。言い回しが違っても、同じ中身を言っていれば in です。核の脇の点にしか触れていない・核と違うことを言っている・核に触れていないときは out です。迷ったら out にします。in のときは、核と同じことを言っている予想の中の字を core_q にそのまま抜き出します（40字以内。予想に実際にある字だけ）。
三、key は、「決め手」の文が渡されたときだけ判断します。予想が決め手と同じことを言っていれば in にして、その予想の中の字を key_q に抜き出します。言っていなければ out です。「決め手」が渡されていなければ、key は空の文字にします。
四、diff は、予想が答えと食い違っているとき（予想が言ったことを、答えが別のこととして述べているとき）だけ書きます。食い違いを探しにいかず、はっきりあるときだけです。予想が言ったことと答えが言っていることの両方が分かる1文（70字以内・です・ます）にし、根拠になる答えの本文の字を diff_q にそのまま抜き出します（40字以内。答えに実際にある字だけ）。無ければ空の文字にします。
五、open_q は、予想のうち、答えが触れていない点（合っているとも違うとも、この答えからは言えない点）があれば、その予想の中の字をそのまま抜き出します（30字以内）。無ければ空の文字にします。
六、予想が、照らし合わせられる中身を持たないとき（短すぎる・問いになっている・「分からない」だけ・問いと関係が無い）は、core を none にして、ほかは空にします。
七、diff の文には、ほめ言葉・励まし・人への評価を書きません。「あなた」と呼びかけず、「予想では」「答えでは」と書きます。
八、予想は声を文字にしたものかもしれません。言い回しの小さな違いや聞き取りの揺れは、違いとして数えません。
九、出力は JSON だけです。前置きもコードの囲みも付けません。

出力の形
{"core": "in か out か none", "core_q": "", "key": "in か out か 空", "key_q": "", "diff": "", "diff_q": "", "open_q": ""}"""

POOL = brain.SparePool(SYSTEM, MODEL, config.RECORDER_EFFORT)
# 強調の印（** __ ~~ `）と、棚の出どころの札（〔…〕）は、核の字から外す。1つだけの ~ _ * は字として残す（「10~20件」を壊さない）
_MARK = re.compile(r"\*\*|__|~~|`+|〔[^〕]{1,80}〕")


def _sentences(par: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[。！？!?])\s*|\n+", par) if s.strip()]


def core_of(prose: str) -> dict:
    """答えの核を、答えの本文から機械で抜き出す。lead＝最初の段落（問いへの答えそのもの。照らし合わせ役に渡す）、
    show＝そのうち画面に出す分（最初の文。短ければ2文）、key＝「決め手」の文（最初の段落の外にあるときだけ）。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", prose or "") if p.strip()]
    paras = [p for p in paras if not re.match(r"^(\||#|>|```|\[\[|[-*]\s|・|\d+[.)]\s)", p)]
    if not paras:
        return {"lead": "", "show": "", "key": ""}
    lead = _MARK.sub("", paras[0])[:LEAD_MAX]
    ss = _sentences(lead)
    show = ss[0] if ss else lead
    if len(ss) > 1 and len(show) < 30 and len(show) + len(ss[1]) <= SHOW_MAX:
        show = show + ss[1]
    if len(show) > SHOW_MAX:
        show = show[:SHOW_MAX - 1] + "…"
    key = ""
    for p in paras[1:]:
        hit = next((s for s in _sentences(_MARK.sub("", p)) if "決め手" in s), None)
        if hit:
            key = hit if len(hit) <= SHOW_MAX else hit[:SHOW_MAX - 1] + "…"
            break
    return {"lead": lead, "show": show, "key": key}


def eligible(pred: str | None, prose: str | None) -> bool:
    """照らし合わせに回す往復。予想があり、答えの本文が届いていて、核を抜き出せる。"""
    return ENABLED and len((pred or "").strip()) >= 2 and len(prose or "") >= 40 and bool(core_of(prose)["lead"])


def build_input(said: str, pred: str, prose: str) -> str:
    c = core_of(prose)
    return (f"<本人の問い>\n{(said or '')[:SAID_MAX]}\n</本人の問い>\n"
            f"<本人の予想>\n{(pred or '')[:PRED_MAX]}\n</本人の予想>\n"
            f"<答えの核>\n{c['show']}\n</答えの核>\n"     # 照らす核は、画面に出す核と同じ文にする
            + (f"<決め手>\n{c['key']}\n</決め手>\n" if c["key"] else "")
            + f"<先生役の答えの本文>\n{(prose or '')[:ANSWER_MAX]}\n</先生役の答えの本文>")


def _fold(s: str) -> str:
    """字を照らすときの形（全角半角・空白・かぎ・句読点の違いを数えない）。"""
    return re.sub(r"[\s『』「」（）()、。，．,.・*`_~#>\-…]+", "", unicodedata.normalize("NFKC", s or "")).lower()


# どの予想にもある言い回し（〜だと思う・たぶん・〜から）。抜き出した字からこれを除いた残りで、根拠になるかを見る
_HEDGE = re.compile(r"(?:だ|な|ん)?と(?:思|おも)(?:う|います|った|って)|気がする|たぶん|おそらく|きっと|かな|から|ので|です|ます")


def _backed(quote: str, source: str, own: bool = False) -> bool:
    """抜き出した字が、元の文に実際にあるか。どの文にもある字（「だと」「だと思う」）は根拠にしない:
    言い回しを除いた残りが4字以上か、かな以外の字を含む2字以上。own（予想の中の字）は、予想の全部と同じなら短くてもよい。"""
    q, s = _fold(quote), _fold(source)
    if not q or q not in s:
        return False
    if own and q == s:
        return True
    rest = _HEDGE.sub("", q)
    return len(rest) >= 4 or (len(rest) >= 2 and re.search(r"[^ぁ-ゖー]", rest) is not None)


def parse(raw: str, pred: str, prose: str) -> dict | None:
    """照らし合わせ役の出力から、返しを取り出す。抜き出した字が予想や答えに無い項目は出さない。形が決まりの外なら None。
    返す形: core（in・out・none・unknown）、core_q・key（in・out）・key_q・diff・open_q と、画面に出す答えの核（lead・keyline）。"""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    i, j = s.rfind('{"core"'), s.rfind("}")
    if i < 0:
        i = s.find("{")
    try:
        d = json.loads(s[i:j + 1]) if i >= 0 and j > i else None
    except ValueError:
        return None
    if not isinstance(d, dict) or d.get("core") not in ("in", "out", "none"):
        return None
    if d["core"] == "none":
        return {"core": "none"}
    core = core_of(prose)

    def quote(key: str, source: str) -> str:
        q = str(d.get(key) or "").strip()
        return q if q and len(q) <= QUOTE_MAX and _backed(q, source, own=source is pred) else ""

    out: dict = {"core": d["core"], "lead": core["show"]}
    if d["core"] == "in":
        cq = quote("core_q", pred)
        if cq:
            out["core_q"] = cq
        else:
            out["core"] = "unknown"     # 「入っていた」の根拠の字が予想に無い。入っていたとも、いなかったとも出さない
    if core["key"] and d.get("key") in ("in", "out"):
        if d["key"] == "out":
            out["key"], out["keyline"] = "out", core["key"]
        else:
            kq = quote("key_q", pred)
            if kq:
                out["key"], out["key_q"] = "in", kq
    diff = str(d.get("diff") or "").strip()
    if diff and len(diff) <= DIFF_MAX and quote("diff_q", prose):
        out["diff"] = diff
    oq = quote("open_q", pred)
    if oq:
        out["open_q"] = oq
    if out["core"] == "unknown" and not (out.get("key") or out.get("diff") or out.get("open_q")):
        return None
    return out


async def judge(said: str, pred: str, prose: str) -> dict | None:
    """照らし合わせの返し（取り出せなければ None）。取れなかったら例外。"""
    s = await POOL.take()
    return parse(await s.ask(build_input(said, pred, prose), timeout=TIMEOUT), pred, prose)
