"""記録役（v0.5）。先生役の答えが届いたあとに、その答えから記録用の地図と確かめの問いを作る。

v0.4 までは先生役（opus）が答えの中で、画面に出ない塊（記録用の地図 tonari-map の show:false と、戻ったときに出す
確かめの問い tonari-check）も書いていた。本人の記録20往復で数えると、見える本文 413〜1,175字に対して見えない塊が
0〜1,841字あり、答えが届くまでの秒の半分近くが、本人がすぐには読まない塊を書く時間だった。そこで、この2つを
別の役（sonnet・1回で使い捨て）に分け、答えを届けたあとに裏で作る。確かめの問いは答えを開いて2分以上たって戻った
ときにしか出ないので、遅れて届いても画面は変わらない。記録役が取れなかった往復は、答えだけが残る（地図と問いは無い）。

先生役が位置の図（tonari-map）を答えの図として出した往復は、その地図をそのまま記録にも使い、記録役は問いだけを作る。
"""
import json

from . import brain, config, tutor

SYSTEM = """あなたは学習アプリの記録役です。本人（学ぶ人）の発言と、先生役がそれに返した答えを読み、2つの塊を作ります。出力は塊だけです。前置きも説明も書きません。

一、記録用の地図 ```tonari-map```（答えに出てきた中心の概念と、その周りの概念の関係。本人の知識の地図に溜めます）
二、確かめの問い ```tonari-check```（本人があとでこの話題に戻ったときに、答えを畳んだ状態で1問ずつ出ます）

根拠は、渡された答えの本文と図だけです。答えに書かれていない関係や事実を足しません。答えの中の ```tonari-think```（先生役の推測・仮定・考えの筋道）に書かれたことは事実ではないので、地図に入れるなら出どころを「推測」にし、確かめの問いにはしません。

地図の決まり
```tonari-map``` {"center": "中心の概念", "gist": "一文の説明（40字以内）", "src": "出どころ",
 "broader": [{"label": "上位概念", "why": "なぜ上位か（20字以内）", "src": "出どころ"}],
 "narrower": [{"label": "下位概念", "why": "…", "src": "…"}],
 "opposite": [{"label": "対の概念", "axis": "何の軸で対か（15字以内）", "src": "…"}],
 "related": [{"label": "関係する概念", "rel": "部分・前提・原因・結果・道具 のどれか（部分＝中心の構成要素。どれでもなければ空）", "link": "中心を主語にして相手へ続く言葉（14字以内。例『を呼び出す』『が無いと動かない』『の入力になる』）", "why": "…", "src": "…"}],
 "examples": ["具体例"], "nonexamples": ["まぎらわしいが違うもの"]}
地図は、線を1本ずつ「中心＋つなぐ言葉＋相手」の文として読めるように描かれます。related には link を必ず書き、「（中心）は（相手）link」と続けて読んで文になる言葉にします（「関係がある」「同時に出る」「似ている」のような、中身を言わない言葉は使いません。文にできない関係は置きません）。対の概念の第一候補は、中心と同じ上位概念の下にいて、よく取り違えられる兄弟です（決め手の1点だけが違うもの）。尺度の両端の反意語を置くときは、何の尺度かを axis に書きます。自然な対が無ければ opposite は空の配列にします（無理に作らない）。非例は、中心の例と見かけはそろっていて決め手だけが違うものを選びます。下位概念は「中心の一種」と言えるものだけです。中心の部品・構成要素は related の「部分」にします。上位概念も「中心は〜の一種」と言えるものだけです。地図に置くのは概念（言葉）だけで、ページの名前・作業の記録・文の要約は置きません。数の上限は broader 2・narrower 5・opposite 2・related 6・examples 3・nonexamples 2。出どころは、答えが 〔id｜見出し〕 の札を付けていればその札、一般の知識なら「一般」、推測なら「推測」です。概念の名前は、<理解の記録> と <この話題の概念> に同じものがあれば同じ字で書きます。答えが概念を扱っていない（あいさつ・操作の返事・一言の事実だけ）ときは、地図を出しません。

確かめの問いの決まり
```tonari-check``` [{"q": "問い", "a": "想定の答え（本文の字の写しにしない）", "hints": ["一段目（考える方向だけ・30字以内）", "二段目（もう一歩近づける手がかり・40字以内）"], "type": "もしも か 当てはめ か 共通点 か 見分け", "concept": "中心の概念", "rel": "broader か narrower か opposite か related", "target": "相手の概念"}]
問いは1〜2個です。答えの本文をそのまま写せば答えられる問い（想定の答えが本文の字と同じになる問い）と、関係の名前だけを問う問い（「上位概念は何か」「何の軸で対になるか」）は出しません。問いの型は次の4つから中身に合うものを選び、type に書きます。もしも＝仕組みや手順の答えのときに「もし〜が無かったら（違っていたら）どうなるか、なぜか」。変えるのは条件・順番・依存だけにし、法令や制度の金額・日数・年齢の値を変える問いは出しません（存在しない制度を作らないため）。当てはめ＝やり方や判断の答えのときに「次の場面ならどうするか」。共通点＝例が2つ以上あるときに「〜と〜に共通するのは何か」。見分け＝言葉の意味の答えのときに「〜は〜の例と言えるか、決め手は何か」。答えがたとえ（```tonari-analogy```）を出しているときは、実際の名前で問い、たとえが成り立たない所か、たとえに相手が無いものを優先して問います。hints は本人が頼んだときに1段ずつ出ます。どちらの段にも想定の答えの字を書きません。concept・target は地図の概念と同じ字にします。答えが短い事実だけで、問う中身が無いときは、問いを出しません。"""

POOL = brain.SparePool(SYSTEM, config.RECORDER_MODEL, config.RECORDER_EFFORT)
TIMEOUT = 90
ANSWER_MAX = 9000


def build_input(session_id: int, said: str, md: str, need_map: bool, need_check: bool) -> str:
    want = "地図と確かめの問いの両方" if need_map and need_check else "確かめの問いだけ（地図は先生役が答えの図として出したので作らない）" \
        if need_check else "地図だけ"
    return (f"<作るもの>{want}</作るもの>\n<本人の発言>\n{(said or '')[:2000]}\n</本人の発言>\n"
            f"<先生役の答え>\n{(md or '')[:ANSWER_MAX]}\n</先生役の答え>\n" + tutor.record_text(session_id))


def pick_blocks(raw: str, need_map: bool, need_check: bool) -> str:
    """記録役の出力から、頼んだ塊だけを最初の1つずつ取り出す（ほかの塊・文は捨てる）。記録用の地図は show:false にする。"""
    out, seen = [], set()
    for m in tutor.BLOCK_RE.finditer(raw or ""):
        kind, body = m.group(1), m.group(2).strip()
        if kind in seen:
            continue
        if kind == "tonari-map" and need_map:
            try:
                d = json.loads(body)
            except ValueError:
                continue
            if not isinstance(d, dict) or not d.get("center"):
                continue
            d["show"] = False   # 記録だけ（画面には描かない）
            out.append("```tonari-map\n" + json.dumps(d, ensure_ascii=False) + "\n```")
            seen.add(kind)
        elif kind == "tonari-check" and need_check:
            out.append(f"```tonari-check\n{body}\n```")
            seen.add(kind)
    return "\n\n".join(out)


async def record(session_id: int, said: str, md: str, need_map: bool, need_check: bool) -> str:
    """足す塊の文（無ければ空）。取れなかったら例外。"""
    s = await POOL.take()
    raw = await s.ask(build_input(session_id, said, md, need_map, need_check), timeout=TIMEOUT)
    return pick_blocks(raw, need_map, need_check)
