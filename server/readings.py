"""読みの判定役（v0.6）。話題の最初の発言に別の読みがあったかを、答えが届いたあとに確かめる。

本人の記録に、短い依頼の読みが2通りあり、先生役が片方の読みで答えて、最後の1文で別の読みに触れただけだった往復が
あった（DESIGN 17.6）。LLM は、読みが割れていても聞き返さずに片方で答えるのがふつうで、割れを見つける判定は答えを
書く段と分けた方が当たる（研究 g3 の 1-4）。答える前に止めて聞き返す形は、外れたときの損と待ちが重なる（g3 の 1-3・1-6）
ので、答えはそのまま届け、別の読みがあったときだけ、答えの下に「別の読みでしたか」の札を出す（g3 の四つめ・六つめ）。

判定役は sonnet の予備を1回で使い捨てる。先生役の指示（tutor.SYSTEM）とも記録役とも別で、取れなかったら何も出さない。
`TONARI_READINGS=off` で止められる。
"""
import json
import os
import re

from . import brain, config

# 記録役を止めているとき（TONARI_RECORDER=off。検査と、答えのあとの役を使わない設定）は、読みの判定役も動かさない
ENABLED = os.environ.get("TONARI_READINGS", "on") != "off" and config.RECORDER != "off"
MODEL = os.environ.get("TONARI_READINGS_MODEL", "") or config.RECORDER_MODEL
SAID_MAX, ANSWER_MAX, TIMEOUT = 600, 3000, 60
LABEL_MAX, ASK_MAX, OTHERS_MAX = 40, 100, 2

SYSTEM = """あなたは学習アプリの、発言の読みを確かめる役です。本人（学ぶ人）が話題の最初に言った発言と、先生役がそれに返した答えの本文を読み、発言に別の読みがあったかを判定します。

決まり
一、別の読みがあると言えるのは、発言の中の語や頼みの向きが2通り以上に取れ、どの読みで答えるかで、説明する対象そのものが変わるときだけです。たとえば「契約書の知識を付けたい」は、「契約書という書類の読み方・書き方の知識」とも、「自分の契約書に書いてある中身の知識」とも取れます。「ブランチを整理したい」は、「ブランチという考え方を学びたい」とも、「いまあるブランチを片づける手順を知りたい」とも取れます。
二、詳しさ・切り口・範囲・例の違い（もっと詳しく・別の例で・歴史も・初心者向けに）は、別の読みではありません。略語や同じ音の別の語（別の分野の同じ略語）を、発言に手がかりが無いのに持ち出しません。
三、先生役の答えが、どちらの読みでも足りる答えになっているときは、別の読みは無いとします。答えの中で別の読みに一言触れているだけで、その読みの中身には答えていないときは、別の読みがあるとします。
四、迷ったら「無い」にします。外れた聞き返しは、聞かないより悪いからです。
五、出力は JSON だけです。前置きもコードの囲みも付けません。

出力の形
別の読みが無いとき: {"alt": false}
あるとき: {"alt": true, "took": "先生役が答えた読み（24字以内）", "others": [{"label": "ほかの読み（24字以内。何のことかが分かる具体的な言い方）", "ask": "その読みで聞き直す文（60字以内。本人の言い方に合わせ、読みがはっきり分かるように書く）"}]}
others は1〜2個です。"""

POOL = brain.SparePool(SYSTEM, MODEL, config.RECORDER_EFFORT)


def eligible(kind: str, via: str, first: bool, has_ref: bool, said: str, prose: str) -> bool:
    """判定役に回す往復。話題の最初の、声か文字の問いだけ（2つ目からは、前の往復が読みを決める手がかりになる）。"""
    return (ENABLED and kind == "question" and via in ("voice", "text") and first and not has_ref
            and len((said or "").strip()) >= 4 and len(prose or "") >= 40)


def build_input(said: str, prose: str) -> str:
    return (f"<本人の発言>\n{(said or '')[:SAID_MAX]}\n</本人の発言>\n"
            f"<先生役の答えの本文>\n{(prose or '')[:ANSWER_MAX]}\n</先生役の答えの本文>")


def parse(raw: str) -> dict | None:
    """判定役の出力から、別の読みを取り出す。形が決まりの外なら無いとする（出さない側に倒す）。"""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    i, j = s.rfind('{"alt"'), s.rfind("}")
    if i < 0:
        i = s.find("{")
    try:
        d = json.loads(s[i:j + 1]) if i >= 0 and j > i else None
    except ValueError:
        return None
    if not isinstance(d, dict) or d.get("alt") is not True:
        return None
    took = str(d.get("took") or "").strip()[:LABEL_MAX]
    others = []
    for o in d.get("others") or []:
        if not isinstance(o, dict):
            continue
        label, ask = str(o.get("label") or "").strip(), str(o.get("ask") or "").strip()
        if label and ask and len(label) <= LABEL_MAX and len(ask) <= ASK_MAX and label != took:
            others.append({"label": label, "ask": ask})
    if not took or not others:
        return None
    return {"took": took, "others": others[:OTHERS_MAX]}


async def judge(said: str, prose: str) -> dict | None:
    """別の読み（無ければ None）。取れなかったら例外。"""
    s = await POOL.take()
    return parse(await s.ask(build_input(said, prose), timeout=TIMEOUT))
