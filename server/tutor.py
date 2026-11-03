"""先生役の指示と、答えの札の読み取り、地図（概念と関係）と理解度への取り込み。

答えは「文（Markdown）＋札の塊（```tonari-…``` と ```mermaid```）」で返させる。opus の --json-schema は1回約20秒
かかった（作者の別のアプリでの測り）ので使わず、流れてくる文から札の塊を切り出す。

v0.2（2026-10-30・研究 c）: 見せ方を中身の形で選ぶ。上から順の問い（一言か→場合分けか→期間か→手順か→比べるか→
重なりか→計算か→分類か→関係の網か→定義か）で最初に当てはまった形の図を1つだけ出し、文と組にする。位置の図は
定義の答えで関係が実在するときだけ描き、それ以外は記録だけにする（show:false）。どの図にも表現の名前（name）と
構造上の理由（why）を付けさせ、確かでない所は一人称の短い言葉（unsure）にさせる。図の塊はそれぞれ機械の決まり
（verify_view）で確かめ、決まりに合わない塊は捨てて本文だけ残す。
"""
import json
import re

from . import corpus, db
from .db import fold

SYSTEM = """あなたは本人（この Mac の持ち主・日本語話者・エンジニア）の学びの先生役です。本人は声で質問し、その文字起こしを直し役が整えてからあなたに届きます。直し役が決めきれなかった箇所は「聞き取りで決めきれなかった箇所」として添えます。そこが答えを左右するなら、両方の読みに触れるか、どちらの意味かを短く確かめてください。

あなたの答えは文字と図で画面に出ます（声では読み上げません）。本人は答えを待つあいだ別の話題に移っていて、戻ってきてから読みます。

理解の考え方
本人の考えでは、言葉や概念は、その周りの言葉との関係が分かっていれば分かります。説明は、本人が「分かる」と記録した周りの概念を足場にし、分からない概念をさらに分からない言葉で説明しません。ただし、図を見て納得することと、何も見ずに言えることは別です。だから最後に確かめの問いを出します。

見せ方の選び方（答えを書く前に毎回決める）
中身の形を、次の問いに上から順に当て、最初に当てはまったもので決めます。
一、一言で足りるか（単純な事実・はい/いいえ・一つの数字。項目が3つ未満で関係が1つ）→ 文だけ（図の塊を出さない）
二、場合によって結論が変わるか（要件・条件・場合分け）→ 分岐の木 ```tonari-decide```
三、期間・年齢・期限・日付の区間が中身か → 時間軸 ```tonari-timeline```
四、順番のある手順か、原因から結果へ進む仕組みか → 流れ ```tonari-flow```
五、2つ以上を観点ごとに比べるか → 比較の表 ```tonari-compare```
六、集合の重なり・含む含まれない・例外か → 重なりの図 ```tonari-overlap```
七、金額・日数・割合を計算するか → 計算の例 ```tonari-calc```
八、種類と下位の種類（分類・全体像・目次）か → 階層の木 ```tonari-tree```
九、多対多の関係の網・データやシステムの関係か → 関係の図 ```mermaid```（erDiagram・flowchart・sequenceDiagram のどれか。ノード12個まで。ラベルは日本語）
十、一つの概念の意味（定義）か → 文と、例と非例。上位・下位・対の関係が実在するときだけ位置の図（```tonari-map``` の show を true）
抽象的な仕組みで、本人がよく知る物にたとえると分かりやすいときは、四の代わりに たとえ ```tonari-analogy``` を使えます（たとえが成り立たない所を必ず書く）。
図は1つの答えに1つで、文と組にします。質問が主に求めているものの形を選びます。同じ中身を2つの図で繰り返しません。中身に合わない図を出すくらいなら文だけにします。図の塊には必ず "name"（表現の名前・1〜2語。例「分岐の木」）と "why"（中身の構造の説明。例「場合分けが2段あるので」。正しさの主張は書かない）を入れます。確かでない項目には "unsure": "ここは自信がありません" のような一人称の短い言葉を入れます（あいまいな関係を図で断定しないため）。

記録の地図
概念が出てくる答えでは、図の種類にかかわらず ```tonari-map``` を必ず1つ出します（本人の知識の地図に溜めるため）。答えに位置の図として描くのは十（定義）で関係が実在するときだけで、そのときだけ "show": true、それ以外は "show": false（記録だけ・画面には出ない）にします。

詳しさ
<詳しさ> が「短く」なら、3文まで・図は1つまで・確かめの問いは0〜1個。「詳しく」なら1200字まで。「自動」なら記録を見て決めます。中心の概念の関係を本人が確かめの問いで答えられている（関係の確かめ＝分かる）なら短く、そうでなければ800字までにします。

答えの型（この順）
一、最初の段落で、問いに1〜2文で答えます。
二、選んだ図の塊を、それが要る場所に1つ置きます（文だけのときは置かない）。
三、説明の本文を段落の散文で書きます。
四、最後に ```tonari-check``` で、確かめの問いを1〜2個出します。この問いは、本人が次にこの話題に戻ったときに、この答えを畳んだ状態で出ます。だから、答えの本文をそのまま写せば答えられる問い（想定の答えが本文の字と同じになる問い）と、関係の名前だけを問う問い（「上位概念は何か」「何の軸で対になるか」）は出しません。問いの型は次の4つから中身に合うものを選び、type に書きます。もしも＝仕組みや手順の質問のときに「もし〜が無かったら（違っていたら）どうなるか、なぜか」。変えるのは条件・順番・依存だけにし、法令や制度の金額・日数・年齢の値を変える問いは出しません（存在しない制度を作らないため）。当てはめ＝やり方や判断の質問のときに「次の場面ならどうするか」。共通点＝例を2つ以上出したときに「〜と〜に共通するのは何か」。見分け＝言葉の意味の質問のときに「〜は〜の例と言えるか、決め手は何か」。
話題の最初の答えでは、最後に「あとで、いまの話をあなたの言葉で説明してもらいます」と一言添えます（先に予告したときだけ、声で説明する学びが効くため）。
本人の発言が前に出した確かめの問いへの答え（種類=answer）のときと、前の答えの中身を自分の言葉で言い直して合っているかを確かめる発言（種類=confirm、または「確認ですけど」「〜ってことですよね」「つまり〜」のような言い方）のときは、最初に ```tonari-grade``` で判定を出します。言い直しのときは、本人が言い直した中身のうち、記録の地図にある関係（<この話題の関係> に並べたもの）に当たるものを判定します。当たるものが無ければ tonari-grade は出さずに、合っている所と違う所を文で返します。
判定のあとの返し方。違う所や足りない所があれば、本人の言葉をそのまま使って1文で名指しし（「あなたは『〜』と言いましたが」）、そうではないと打ち消し、正しい説明を厚めに書き、本人の考えのどこで推論がずれたかを1文で言います。合っていれば、合っている決め手を1文で言い、次に確かめるとよい点を1つだけ示します。ほめ言葉（すごい・完璧・さすが・素晴らしい）、点数、ほかの人との比較は書きません。間違った理由を本人にもっと説明させる問いは出しません（誤った筋道を言い直すほど残るため）。「聞き取りで決めきれなかった箇所」に当たる語は、言い間違いかもしれないので名指しの対象にしません。
本人が「別の見せ方で」と頼んだときは、<見せ直しの元> の図と違う形を選びます（画面は前の図と新しい図を横に並べます）。本文の最後に、2つの図を結びつける問いを1つだけ書きます（答えなくてよい問いとして）。

書き方の決まり
本文は段落の散文で書きます。箇条書きは使いません。見出しは使わないか、使っても1つの答えに1つまでにします。もっと要るときは「続きは『もっと詳しく』と言ってください」と書きます。
根拠: 作業フォルダには、本人が Claude と作った調査・計画・メモのページ（アーティファクト棚）の本文の写しが <id>.txt で入っています。話題が棚にありそうなら Grep で探して Read で読み、根拠にします。「」は棚の本文の字をそのまま写すときだけに使います（画面が「」の中身を棚の本文と照らします）。強調・言い換え・会話の引用・用語には「」を使わず、用語は『』で囲みます。ページを示すときは 〔ページのid｜見出しの字〕 と書きます。棚に無いことは一般の知識で答えてかまいませんが、出どころ（src）に「一般」と書きます。研究や事実の数字を、出典を確かめずに断定しません。推測は推測と書きます。道具を使う前の前置き（「確かめます」など）は書きません。作業フォルダの外は読めません。

塊の形（JSON・キーは英字のまま・name と why は図の塊すべてに入れる）
```tonari-decide``` {"name": "分岐の木", "why": "…", "q": "何を判定するか", "root": {"ask": "問い", "branches": [{"label": "はい", "next": {"ask": "…", "branches": [ … ]}}, {"label": "いいえ", "result": "結論", "note": "補足（任意）", "src": "出どころ", "unsure": "（任意）"}]}}
深さは4段まで。結論（result）の枝には src を必ず付けます。
```tonari-timeline``` {"name": "時間軸", "why": "…", "unit": "歳か年か月か日", "from": 数, "to": 数, "lanes": [{"label": "帯の名前", "spans": [{"from": 数, "to": 数, "label": "（任意）"}]}], "marks": [{"at": 数, "label": "出来事"}], "src": "出どころ", "example": false}
```tonari-flow``` {"name": "流れ", "why": "…", "kind": "手順か仕組み", "steps": [{"label": "段階（15字以内）", "note": "補足（任意・30字以内）", "group": "段階のまとまりの名前（任意）"}]}
段階は2〜8つ。
```tonari-compare``` {"name": "比較の表", "why": "…", "items": ["比べるもの1", "比べるもの2"], "rows": [{"axis": "観点", "same": "共通の値"}, {"axis": "観点", "values": ["1の値", "2の値"], "key": true}]}
比べるものは2〜4つ。共通の行（same）を先に、違いの行（values）を後に並べ、決め手の行に "key": true を付けます。
```tonari-overlap``` {"name": "重なりの図", "why": "…", "sets": ["集合1", "集合2"], "elements": [{"label": "要素", "in": [0]}, {"label": "要素", "in": [0, 1]}]}
集合は2〜3つ。in は属する集合の番号（0から）。
```tonari-calc``` {"name": "計算の例", "why": "…", "title": "何の計算か", "formula": "式（言葉で）", "vars": [{"name": "項目", "value": "値", "note": "（任意）"}], "steps": ["一段ずつの計算"], "result": "答え", "src": "出どころ", "example": true か false}
数字が棚の本文や確かめた出典に無いときは "example": true にし、例の数字として扱います。
```tonari-analogy``` {"name": "たとえ", "why": "…", "source": "よく知っているもの", "target": "学ぶもの", "pairs": [{"s": "元の側", "t": "学ぶ側"}], "breaks": ["たとえが成り立たない所"]}
breaks は1つ以上必ず書きます。
```tonari-tree``` {"name": "階層の木", "why": "…", "root": "話題", "children": [{"label": "…", "note": "10字以内", "children": [ … ]}]}
3段まで・各段8個まで。
```mermaid``` 1行目に「%% name: 関係の図 | why: 理由」と書き、2行目から図を書きます。

```tonari-map``` {"show": true か false, "name": "位置の図", "why": "…", "center": "中心の概念", "gist": "一文の説明（40字以内）", "src": "出どころ",
 "broader": [{"label": "上位概念", "why": "なぜ上位か（20字以内）", "src": "出どころ"}],
 "narrower": [{"label": "下位概念", "why": "…", "src": "…"}],
 "opposite": [{"label": "対の概念", "axis": "何の軸で対か（15字以内）", "src": "…"}],
 "related": [{"label": "関係する概念", "rel": "前提・原因・結果・部分・道具・同時に出る・似ている のどれか（部分＝中心の構成要素）", "why": "…", "src": "…"}],
 "examples": ["具体例"], "nonexamples": ["まぎらわしいが違うもの"]}
対の概念の第一候補は、中心と同じ上位概念の下にいて、よく取り違えられる兄弟です（決め手の1点だけが違うもの）。尺度の両端の反意語を置くときは、何の尺度かを axis に書きます。自然な対が無ければ opposite は空の配列にします（無理に作らない）。非例は、中心の例と見かけはそろっていて決め手だけが違うものを選びます。下位概念は「中心の一種」と言えるものだけです。中心の部品・構成要素は related の「部分」にします。上位概念も「中心は〜の一種」と言えるものだけです。地図に置くのは概念（言葉）だけで、ページの名前・作業の記録・文の要約は置きません。数の上限は broader 2・narrower 5・opposite 2・related 6・examples 3・nonexamples 2。出どころは、棚に根拠があれば 〔id｜見出し〕、一般の知識なら「一般」、推測なら「推測」です。概念の名前は、<理解の記録> と <この話題の概念> に同じものがあれば同じ字で書きます。

```tonari-check``` [{"q": "問い", "a": "想定の答え（本文の字の写しにしない）", "type": "もしも か 当てはめ か 共通点 か 見分け", "concept": "中心の概念", "rel": "broader か narrower か opposite か related", "target": "相手の概念"}]

```tonari-grade``` [{"concept": "概念", "target": "相手の概念", "rel": "broader など", "result": "hit か partial か miss", "evidence": "本人の発言から写した字（言い換えない）"}]
evidence は本人の発言の字をそのまま写します。写せる字が無ければ result は miss にします。

棚の目録（id｜題｜棚｜公開日）。起動したときのものです。
"""

VIEW_TYPES = ("decide", "timeline", "flow", "compare", "overlap", "calc", "analogy", "tree", "map")
VIEW_NAMES = {"decide": "分岐の木", "timeline": "時間軸", "flow": "流れ", "compare": "比較の表", "overlap": "重なりの図",
              "calc": "計算の例", "analogy": "たとえ", "tree": "階層の木", "map": "位置の図", "mermaid": "関係の図"}
BLOCK_RE = re.compile(r"```(tonari-[a-z]+|mermaid)[ \t]*\n(.*?)```", re.S)
REL_DIRS = ("broader", "narrower", "opposite", "related")
MERMAID_HEAD = re.compile(r"^\s*%%\s*name\s*:\s*([^|\n]+?)\s*(?:\|\s*why\s*:\s*([^\n]*))?\s*$")


def system_prompt() -> str:
    return SYSTEM + corpus.catalog() + "\n"


def src_kind(src: str) -> tuple[str, str]:
    s = (src or "").strip()
    m = corpus.ID_RE.search(s)
    if m:
        return ("shelf" if corpus.title_of(m.group(1)) else "inferred"), s
    if s.startswith("一般"):
        return "general", s
    return "inferred", s


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _s(x, n=80) -> str:
    return str(x if x is not None else "").strip()[:n]


def _numbers(d: dict, kind: str) -> str:
    """数字の出どころの印。例の数字・確かめた出どころ（棚か一般）・確かめていない数字のどれか。"""
    if d.get("example"):
        return "example"
    return "checked" if kind in ("shelf", "general") else "unverified"


def _decide_node(n, depth: int):
    if not isinstance(n, dict) or depth > 4:
        return None
    if n.get("result") not in (None, ""):
        kind, ref = src_kind(_s(n.get("src"), 120))
        return {"result": _s(n.get("result"), 60), "note": _s(n.get("note"), 60),
                "src": kind, "src_ref": ref, "unsure": _s(n.get("unsure"), 30)}
    br = []
    for b in (n.get("branches") or [])[:5]:
        if not isinstance(b, dict):
            continue
        child = _decide_node(b.get("next"), depth + 1) if b.get("next") is not None else _decide_node(b, depth + 1)
        if child:
            br.append({"label": _s(b.get("label"), 30), "node": child})
    if not n.get("ask") or len(br) < 2:
        return None
    return {"ask": _s(n.get("ask"), 50), "branches": br, "unsure": _s(n.get("unsure"), 30)}


def verify_view(t: str, d) -> tuple[dict | None, str | None]:
    """図の塊を機械の決まりで確かめる。合えば（整えた塊, None）、合わなければ（None, 捨てた理由）。"""
    if not isinstance(d, dict):
        return None, "形が JSON の辞書でない"
    v = {"name": _s(d.get("name"), 12) or VIEW_NAMES[t], "why": _s(d.get("why"), 60)}
    if t == "decide":
        root = _decide_node(d.get("root"), 1)
        if not root:
            return None, "分岐の木: 問いと2本以上の枝がそろっていない"
        v.update(q=_s(d.get("q"), 50), root=root)
    elif t == "timeline":
        a, b = _num(d.get("from")), _num(d.get("to"))
        if a is None or b is None or a >= b:
            return None, "時間軸: from と to が数でない・順が逆"
        lanes = []
        for ln in (d.get("lanes") or [])[:6]:
            if not isinstance(ln, dict):
                continue
            spans = []
            for sp in (ln.get("spans") or [])[:6]:
                x, y = (_num(sp.get("from")), _num(sp.get("to"))) if isinstance(sp, dict) else (None, None)
                if x is None or y is None or x >= y:
                    continue
                spans.append({"from": max(a, x), "to": min(b, y), "label": _s(sp.get("label"), 20)})
            if spans:
                lanes.append({"label": _s(ln.get("label"), 20), "spans": spans})
        marks = []
        for m in (d.get("marks") or [])[:8]:
            at = _num(m.get("at")) if isinstance(m, dict) else None
            if at is not None and a <= at <= b:
                marks.append({"at": at, "label": _s(m.get("label"), 24)})
        if not lanes and not marks:
            return None, "時間軸: 帯も出来事も無い"
        kind, ref = src_kind(_s(d.get("src"), 120))
        v.update({"unit": _s(d.get("unit"), 4), "from": a, "to": b, "lanes": lanes, "marks": marks,
                  "src": kind, "src_ref": ref, "numbers": _numbers(d, kind)})
    elif t == "flow":
        steps = [{"label": _s(x.get("label"), 24), "note": _s(x.get("note"), 40), "group": _s(x.get("group"), 14),
                  "unsure": _s(x.get("unsure"), 30)} for x in (d.get("steps") or []) if isinstance(x, dict) and x.get("label")]
        if not 2 <= len(steps) <= 10:
            return None, "流れ: 段階が2〜10でない"
        v.update(kind=_s(d.get("kind"), 4) or "手順", steps=steps[:8])
    elif t == "compare":
        items = [_s(x, 20) for x in (d.get("items") or []) if _s(x)]
        if not 2 <= len(items) <= 4:
            return None, "比較の表: 比べるものが2〜4でない"
        rows = []
        for r in d.get("rows") or []:
            if not isinstance(r, dict) or not r.get("axis"):
                continue
            if r.get("same") not in (None, ""):
                rows.append({"axis": _s(r["axis"], 16), "same": _s(r["same"], 60)})
            elif isinstance(r.get("values"), list) and len(r["values"]) == len(items):
                rows.append({"axis": _s(r["axis"], 16), "values": [_s(x, 50) for x in r["values"]],
                             "key": bool(r.get("key")), "unsure": _s(r.get("unsure"), 30)})
        if not rows:
            return None, "比較の表: 行が無い"
        rows.sort(key=lambda r: 0 if "same" in r else 1)   # 共通の行を先に（研究 c: 共通点を先に探すほうが学べる）
        v.update(items=items, rows=rows[:8])
    elif t == "overlap":
        sets = [_s(x, 16) for x in (d.get("sets") or []) if _s(x)]
        if not 2 <= len(sets) <= 3:
            return None, "重なりの図: 集合が2〜3でない"
        els = []
        for e in d.get("elements") or []:
            if not isinstance(e, dict) or not e.get("label"):
                continue
            ins = sorted({int(i) for i in (e.get("in") or []) if isinstance(i, (int, float)) and 0 <= int(i) < len(sets)})
            if ins:
                els.append({"label": _s(e["label"], 16), "in": ins})
        if len(els) < 2:
            return None, "重なりの図: 要素が2つ未満"
        v.update(sets=sets, elements=els[:16])
    elif t == "calc":
        steps = [_s(x, 80) for x in (d.get("steps") or []) if _s(x)]
        if not d.get("result") or not (steps or d.get("formula")):
            return None, "計算の例: 答えか式が無い"
        kind, ref = src_kind(_s(d.get("src"), 120))
        v.update(title=_s(d.get("title"), 40), formula=_s(d.get("formula"), 100),
                 vars=[{"name": _s(x.get("name"), 20), "value": _s(x.get("value"), 30), "note": _s(x.get("note"), 40)}
                       for x in (d.get("vars") or [])[:8] if isinstance(x, dict) and x.get("name")],
                 steps=steps[:8], result=_s(d.get("result"), 60), src=kind, src_ref=ref, numbers=_numbers(d, kind))
    elif t == "analogy":
        pairs = [{"s": _s(x.get("s"), 30), "t": _s(x.get("t"), 30)} for x in (d.get("pairs") or [])
                 if isinstance(x, dict) and x.get("s") and x.get("t")]
        breaks = [_s(x, 60) for x in (d.get("breaks") or []) if _s(x)]
        if len(pairs) < 2:
            return None, "たとえ: 対応が2つ未満"
        if not breaks:
            return None, "たとえ: 成り立たない所が書かれていない（研究 c: 限界を示さないたとえは誤解を招く）"
        v.update(source=_s(d.get("source"), 20), target=_s(d.get("target"), 20), pairs=pairs[:6], breaks=breaks[:3])
    elif t == "tree":
        if not d.get("root"):
            return None, "階層の木: root が無い"
        v.update(root=_s(d.get("root"), 30), children=d.get("children") or [])
    elif t == "map":
        if not d.get("center"):
            return None, "位置の図: center が無い"
        v.update({k: d.get(k) for k in ("center", "gist", "src", "broader", "narrower", "opposite", "related",
                                         "examples", "nonexamples")})
    return v, None


def parse_blocks(md: str) -> dict:
    """答えの文から札の塊を取り出す。

    map・check・grade・tree は記録への取り込みに使い、views は画面に描く図（出てきた順）。
    text は塊を [[view:N]] の置き場所に置き換えた本文（記録だけの塊と確かめ・判定の塊は消す）。
    読めない塊・決まりに合わない塊は errors に理由を入れて本文から消す。"""
    out = {"map": None, "check": [], "grade": [], "tree": None, "mermaid": [], "views": [], "errors": [], "text": ""}
    parts, last = [], 0
    for m in BLOCK_RE.finditer(md):
        parts.append(md[last:m.start()])
        last = m.end()
        kind, body = m.group(1), m.group(2).strip()
        if kind == "mermaid":
            first, _, rest = body.partition("\n")
            head = MERMAID_HEAD.match(first)
            name, why = (head.group(1).strip()[:12], (head.group(2) or "").strip()[:60]) if head else ("関係の図", "")
            code = rest if head else body
            out["mermaid"].append(code)
            parts.append(f"\n\n[[view:{len(out['views'])}]]\n\n")
            out["views"].append({"type": "mermaid", "name": name, "why": why, "code": code})
            continue
        t = kind[len("tonari-"):]
        try:
            d = json.loads(body)
        except ValueError as e:
            out["errors"].append(f"{kind}: JSON が読めない（{e}）")
            continue
        if t == "check":
            if isinstance(d, list):
                out["check"] = [x for x in d if isinstance(x, dict) and x.get("q")][:3]
            continue
        if t == "grade":
            if isinstance(d, list):
                out["grade"] = [x for x in d if isinstance(x, dict)]
            continue
        if t not in VIEW_TYPES:
            out["errors"].append(f"{kind}: 知らない塊")
            continue
        if t == "map" and isinstance(d, dict) and d.get("center"):
            out["map"] = d
        if t == "tree" and isinstance(d, dict) and d.get("root"):
            out["tree"] = d
        if t == "map" and isinstance(d, dict) and d.get("show") is False:
            continue   # 記録だけの位置の図（画面に描かない）
        v, why = verify_view(t, d)
        if v is None:
            out["errors"].append(f"{kind}: {why}")
            continue
        v["type"] = t
        parts.append(f"\n\n[[view:{len(out['views'])}]]\n\n")
        out["views"].append(v)
    parts.append(md[last:])
    out["text"] = re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip()
    return out


def strip_blocks(md: str) -> str:
    return BLOCK_RE.sub("", md).strip()


# ── 地図への取り込み ──────────────────────────────────────────
def upsert_concept(con, label: str, gist: str | None = None, gsrc: str | None = None) -> int | None:
    label = (label or "").strip()[:60]
    f = fold(label)
    if not f:
        return None
    r = db.row(con, "SELECT id FROM concept WHERE fold=?", (f,))
    t = db.now()
    if r:
        if gist:
            con.execute("UPDATE concept SET gist=?, gist_src=?, updated_at=? WHERE id=?", (gist[:120], gsrc, t, r["id"]))
        return r["id"]
    cur = con.execute("INSERT INTO concept(label, fold, gist, gist_src, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                      (label, f, (gist or "")[:120] or None, gsrc, t, t))
    return cur.lastrowid


def upsert_relation(con, a: int, b: int, rel: str, detail: str | None, why: str | None,
                    src: str | None, turn_id: int) -> int | None:
    if not a or not b or a == b:
        return None
    if rel == "opposite" and a > b:   # 対は向きを持たないので id の小さい方を src にそろえる
        a, b = b, a
    kind, ref = src_kind(src or "")
    t = db.now()
    r = db.row(con, "SELECT id, src_kind FROM relation WHERE src=? AND dst=? AND rel=?", (a, b, rel))
    if r:
        # 根拠の強いほう（棚 > 一般 > 推測）を残す
        rank = {"shelf": 3, "general": 2, "inferred": 1}
        if rank[kind] >= rank.get(r["src_kind"], 0):
            con.execute("UPDATE relation SET detail=?, why=?, src_kind=?, src_ref=?, turn_id=?, updated_at=? WHERE id=?",
                        (detail, why, kind, ref, turn_id, t, r["id"]))
        return r["id"]
    cur = con.execute("""INSERT INTO relation(src, dst, rel, detail, why, src_kind, src_ref, turn_id, created_at, updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""", (a, b, rel, detail, why, kind, ref, turn_id, t, t))
    return cur.lastrowid


def link_session(con, session_id: int, cid: int | None, turn_id: int) -> None:
    if not cid:
        return
    con.execute("""INSERT INTO session_concept(session_id, concept_id, first_turn, last_turn) VALUES(?,?,?,?)
                   ON CONFLICT(session_id, concept_id) DO UPDATE SET last_turn=excluded.last_turn""",
                (session_id, cid, turn_id, turn_id))


def merge_map(con, session_id: int, turn_id: int, m: dict) -> int | None:
    def s(x, n=40):
        return str(x or "").strip()[:n]
    center = upsert_concept(con, s(m.get("center"), 60), s(m.get("gist"), 120), s(m.get("src"), 120))
    link_session(con, session_id, center, turn_id)
    for it in (m.get("broader") or [])[:2]:
        b = upsert_concept(con, s(it.get("label"), 60))
        link_session(con, session_id, b, turn_id)
        upsert_relation(con, center, b, "broader", None, s(it.get("why")), s(it.get("src"), 120), turn_id)
    for it in (m.get("narrower") or [])[:5]:
        n = upsert_concept(con, s(it.get("label"), 60))
        link_session(con, session_id, n, turn_id)
        upsert_relation(con, n, center, "broader", None, s(it.get("why")), s(it.get("src"), 120), turn_id)
    for it in (m.get("opposite") or [])[:2]:
        o = upsert_concept(con, s(it.get("label"), 60))
        link_session(con, session_id, o, turn_id)
        upsert_relation(con, center, o, "opposite", s(it.get("axis"), 20), None, s(it.get("src"), 120), turn_id)
    for it in (m.get("related") or [])[:6]:
        r = upsert_concept(con, s(it.get("label"), 60))
        link_session(con, session_id, r, turn_id)
        upsert_relation(con, center, r, "related", s(it.get("rel"), 12), s(it.get("why")), s(it.get("src"), 120), turn_id)
    for lab in (m.get("examples") or [])[:3]:
        e = upsert_concept(con, s(lab, 60))
        upsert_relation(con, e, center, "example", None, None, s(m.get("src"), 120), turn_id)
    for lab in (m.get("nonexamples") or [])[:2]:
        e = upsert_concept(con, s(lab, 60))
        upsert_relation(con, e, center, "nonexample", None, None, s(m.get("src"), 120), turn_id)
    return center


def find_relation(con, concept: str, target: str, rel: str) -> int | None:
    a = db.row(con, "SELECT id FROM concept WHERE fold=?", (fold(concept),))
    b = db.row(con, "SELECT id FROM concept WHERE fold=?", (fold(target),))
    if not a or not b:
        return None
    a, b = a["id"], b["id"]
    cands = {
        "broader": [(a, b, "broader")],
        "narrower": [(b, a, "broader")],
        "opposite": [(min(a, b), max(a, b), "opposite")],
        "related": [(a, b, "related"), (b, a, "related")],
    }.get(rel, [(a, b, "broader"), (b, a, "broader"), (min(a, b), max(a, b), "opposite"), (a, b, "related"), (b, a, "related")])
    for x, y, r in cands:
        hit = db.row(con, "SELECT id FROM relation WHERE src=? AND dst=? AND rel=?", (x, y, r))
        if hit:
            return hit["id"]
    return None


def set_rel_mastery(con, rid: int, state: str, by: str, evidence: str | None, turn_id: int | None) -> None:
    t = db.now()
    con.execute("""INSERT INTO rel_mastery(relation_id, state, by, evidence, updated_at) VALUES(?,?,?,?,?)
                   ON CONFLICT(relation_id) DO UPDATE SET state=excluded.state, by=excluded.by,
                   evidence=excluded.evidence, updated_at=excluded.updated_at""", (rid, state, by, evidence, t))
    con.execute("INSERT INTO log(kind, target, state, by, evidence, turn_id, at) VALUES('rel_mastery',?,?,?,?,?,?)",
                (rid, state, by, evidence, turn_id, t))


def set_mastery(con, cid: int, state: str, by: str, turn_id: int | None = None) -> None:
    t = db.now()
    con.execute("""INSERT INTO mastery(concept_id, state, by, updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(concept_id) DO UPDATE SET state=excluded.state, by=excluded.by, updated_at=excluded.updated_at""",
                (cid, state, by, t))
    con.execute("INSERT INTO log(kind, target, state, by, turn_id, at) VALUES('mastery',?,?,?,?,?)", (cid, state, by, turn_id, t))


def apply_grades(con, session_id: int, turn_id: int, grades: list[dict], said: str, kind: str = "answer",
                 judged: list[str | None] | None = None, check_id: int | None = None) -> list[dict]:
    """判定を記録する。根拠（本人の発言の逐語）が発言に無い当たり・半分は記録しない。

    judged は二度目の判定役（judge.py）の結果で、渡されたときは当たり・半分が一致したものだけを記録する
    （先生役が自分で作った問いを自分で採点するので、1回の判定を記録の根拠にしない）。手つかずの確かめの問いを
    「答えた」にするのは、本人が確かめの問いに答えたとき（kind=answer）だけ。言い直し（confirm）では消さない。"""
    out = []
    fs = fold(said)
    for i, g in enumerate(grades):
        ev = str(g.get("evidence") or "").strip()
        res = g.get("result") if g.get("result") in ("hit", "partial", "miss") else "miss"
        verified = bool(ev) and len(fold(ev)) >= 2 and fold(ev) in fs
        rid = find_relation(con, str(g.get("concept") or ""), str(g.get("target") or ""), str(g.get("rel") or ""))
        state = {"hit": "known", "partial": "shaky", "miss": "unknown"}[res]
        if res != "miss" and not verified:
            state = None   # 当たりと言うのに根拠の字が無い判定は記録しない
        extra = {}
        if judged is not None and res != "miss":
            j = judged[i] if i < len(judged) else None
            extra = {"judge": j, "agreed": j == res}
            if j != res:
                state = None   # 二度目の判定と食い違う（または取れなかった）当たり・半分は記録しない
        if rid and state:
            set_rel_mastery(con, rid, state, "check", ev or None, turn_id)
        out.append({**g, "verified": verified, "recorded": bool(rid and state), **extra})
    if kind == "answer":
        if check_id:   # 戻ったときに出した問い1つに答えた
            con.execute("UPDATE checkq SET status='answered' WHERE id=? AND status='open'", (check_id,))
        else:
            con.execute("UPDATE checkq SET status='answered' WHERE session_id=? AND status='open'", (session_id,))
    return out


QTYPES = ("もしも", "当てはめ", "共通点", "見分け")


def filter_checks(checks: list[dict], md: str) -> tuple[list[dict], list[str]]:
    """本文をそのまま写せば答えられる問い（想定の答えの字が本文にある）を外す。型が無ければ「その他」にする。"""
    body = fold(strip_blocks(md))
    keep, dropped = [], []
    for c in checks:
        a = fold(str(c.get("a") or ""))
        if len(a) >= 4 and a in body:
            dropped.append(f"確かめの問いを外した（想定の答えが本文にそのまま書いてある）: {str(c.get('q'))[:40]}")
            continue
        keep.append({**c, "type": c.get("type") if c.get("type") in QTYPES else "その他"})
    return keep, dropped


def save_checks(con, session_id: int, turn_id: int, checks: list[dict]) -> list[dict]:
    out = []
    for c in checks:
        cur = con.execute("""INSERT INTO checkq(turn_id, session_id, q, a, concept, target, rel, qtype, created_at)
                             VALUES(?,?,?,?,?,?,?,?,?)""",
                          (turn_id, session_id, str(c.get("q"))[:200], str(c.get("a") or "")[:200],
                           str(c.get("concept") or "")[:60], str(c.get("target") or "")[:60],
                           str(c.get("rel") or "")[:12], str(c.get("type") or "その他")[:8], db.now()))
        out.append({**c, "id": cur.lastrowid, "status": "open"})
    return out


# ── 先生役に渡す1回分 ──────────────────────────────────────────
def record_text(session_id: int) -> str:
    """この話題の概念と、本人の理解の記録（申告と確かめ）を短く渡す。"""
    with db.tx() as con:
        here = db.rows(con, """SELECT c.id, c.label, m.state FROM session_concept sc JOIN concept c ON c.id=sc.concept_id
                               LEFT JOIN mastery m ON m.concept_id=c.id WHERE sc.session_id=? ORDER BY sc.last_turn DESC LIMIT 80""",
                       (session_id,))
        known_all = db.rows(con, """SELECT c.label, m.state FROM mastery m JOIN concept c ON c.id=m.concept_id
                                    ORDER BY m.updated_at DESC LIMIT 80""")
        rels = db.rows(con, """SELECT a.label AS a, b.label AS b, r.rel, rm.state FROM rel_mastery rm
                               JOIN relation r ON r.id=rm.relation_id JOIN concept a ON a.id=r.src JOIN concept b ON b.id=r.dst
                               ORDER BY rm.updated_at DESC LIMIT 40""")
    by = {"known": [], "shaky": [], "unknown": []}
    seen = set()
    for r in known_all:
        if r["state"] in by and r["label"] not in seen:
            by[r["state"]].append(r["label"])
            seen.add(r["label"])
    lines = [f"分かる: {'、'.join(by['known']) or 'なし'}", f"あやしい: {'、'.join(by['shaky']) or 'なし'}",
             f"分からない: {'、'.join(by['unknown']) or 'なし'}"]
    if rels:
        jp = {"known": "分かる", "shaky": "あやしい", "unknown": "分からない"}
        name = {"broader": "の上位が", "opposite": "と対", "related": "と関係", "example": "の例が", "nonexample": "の非例が"}
        lines.append("関係の確かめ: " + "、".join(f"{r['a']}{name.get(r['rel'], '—')}{r['b']}＝{jp.get(r['state'], '?')}" for r in rels[:20]))
    here_labels = [r["label"] for r in here]
    return ("<理解の記録>\n" + "\n".join(lines) + "\n</理解の記録>\n<この話題の概念>\n"
            + ("、".join(here_labels) or "（まだありません）") + "\n</この話題の概念>")


DETAIL_JA = {"auto": "自動", "short": "短く", "long": "詳しく"}


def session_relations(session_id: int, limit: int = 30) -> list[str]:
    """この話題の概念どうしの関係（言い直しの判定で、記録の地図にある関係を名指しさせるため）。"""
    name = {"broader": "の上位が", "opposite": "と対", "related": "と関係"}
    with db.tx() as con:
        rows = db.rows(con, """SELECT a.label AS a, b.label AS b, r.rel, r.detail FROM relation r
                               JOIN concept a ON a.id=r.src JOIN concept b ON b.id=r.dst
                               WHERE r.rel IN ('broader','opposite','related')
                                 AND r.src IN (SELECT concept_id FROM session_concept WHERE session_id=?)
                                 AND r.dst IN (SELECT concept_id FROM session_concept WHERE session_id=?)
                               ORDER BY r.id DESC LIMIT ?""", (session_id, session_id, limit))
    return [f"{r['a']}{name[r['rel']]}{r['b']}（rel={r['rel']}{'・' + r['detail'] if r['detail'] else ''}）" for r in rows]


def turn_content(session_id: int, text: str, kind: str, via: str, unsure: list[dict],
                 detail: str = "auto", ref: dict | None = None, hedges: list[str] | None = None,
                 predict: str | None = None, check_id: int | None = None) -> str:
    parts = [f"<詳しさ>{DETAIL_JA.get(detail, '自動')}</詳しさ>"]
    if ref:
        parts.append(f"<見せ直しの元>前の答えの図は「{ref.get('name') or 'なし（文だけ）'}」（{ref.get('type') or 'text'}）でした。"
                     f"中身は同じで、違う形で見せ直します。</見せ直しの元>")
    parts += [f"<本人の発言 種類={kind} 経路={via}>", text]
    if unsure:
        parts.append("聞き取りで決めきれなかった箇所: " + "、".join(f"『{u['span']}』は {' か '.join(u['options'])}" for u in unsure))
    if hedges:
        parts.append("言い方の迷い（本人が自信の無さを言葉にした所）: " + "、".join(hedges))
    parts.append("</本人の発言>")
    if predict:
        parts.append(f"<前の答えを読む前の本人の予想>{predict}</前の答えを読む前の本人の予想>")
    if kind == "confirm":
        rels = session_relations(session_id)
        if rels:
            parts.append("<この話題の関係>\n" + "\n".join(rels) + "\n</この話題の関係>")
    if kind == "answer":
        with db.tx() as con:
            if check_id:
                qs = db.rows(con, "SELECT q, a, concept, target, rel FROM checkq WHERE id=? AND session_id=?", (check_id, session_id))
            else:
                qs = db.rows(con, "SELECT q, a, concept, target, rel FROM checkq WHERE session_id=? AND status='open' ORDER BY id", (session_id,))
        if qs:
            parts.append("<確かめの問い（本人はこれに答えています）>\n" + "\n".join(
                f"問い: {q['q']}（中心 {q['concept']}・相手 {q['target']}・関係 {q['rel']}・想定の答え {q['a']}）" for q in qs)
                + "\n</確かめの問い>")
    parts.append(record_text(session_id))
    return "\n".join(parts)
