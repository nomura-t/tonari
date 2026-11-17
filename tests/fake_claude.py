#!/usr/bin/env python3
"""確かめ用の、作り物の claude。本物の claude -p の代わりに、決まった答えを stream-json で返す。

画面の流れ（待つあいだの予想・確かめの帯・片づけた話題）を、Max の枠を使わずに何度でも確かめるための物（v0.6）。
使い方は、サーバーを `TONARI_CLAUDE=<このファイル>` で起動するだけ。先生役・記録役・判定役・整形役のどれとして
呼ばれたかは、渡された指示のファイルの冒頭で見分ける。答えの中身は作り物で、学びの中身としては意味を持たない。

  TONARI_FAKE_DELAY       先生役が答え始めるまでの秒（既定 1.5。待つあいだの帯を確かめるときは長くする）
  TONARI_FAKE_DELAY_FILE  秒を書いたファイル。あれば、答えるたびに読んで上の秒より先に使う（動かしたまま変えられる）
"""
from __future__ import annotations

import json
import os
import sys
import time

ARGS = sys.argv[1:]
DELAY = float(os.environ.get("TONARI_FAKE_DELAY", "1.5"))


def delay() -> float:
    try:
        return float(open(os.environ["TONARI_FAKE_DELAY_FILE"], encoding="utf-8").read().strip())
    except (KeyError, OSError, ValueError):
        return DELAY


def arg(name: str) -> str | None:
    return ARGS[ARGS.index(name) + 1] if name in ARGS and ARGS.index(name) + 1 < len(ARGS) else None


def out(ev: dict) -> None:
    sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def said_of(content: str) -> str:
    """先生役に渡された1回分から、本人の発言の文だけを取り出す。"""
    a, b = content.find("<本人の発言"), content.find("</本人の発言>")
    if a < 0 or b < 0:
        return content[:80]
    return content[content.find(">", a) + 1:b].strip().split("\n")[0][:80]


TUTOR_ANSWER = """作り物の答えです。『受付』が頼みを受け取り、『倉庫』から品物を出して返します。

```tonari-flow
{"name": "流れ", "why": "受け取ってから返すまでに順番があるので", "kind": "仕組み", "steps": [{"label": "頼みを受ける"}, {"label": "倉庫で探す"}, {"label": "品物を返す"}]}
```

決め手は、『受付』が『倉庫』の中身を自分では持たないことです。品物があるかどうかは、倉庫に聞くまで分かりません。

ほかに、倉庫が空のときの扱いの話があります。"""

# 発言に「長めに」があるときの答え（本物の答えに近い長さ。答えの終わりが、開いた直後には窓に入らない場面を確かめる）
LONG_ANSWER = """作り物の長めの答えです。『受付』は朝に窓口を開け、頼みを受け取り、『倉庫』から品物を出して返します。

```tonari-flow
{"name": "流れ", "why": "一日の中に順番があるので", "kind": "仕組み", "steps": [{"label": "窓口を開ける"}, {"label": "頼みを受ける"}, {"label": "倉庫で探す"}, {"label": "品物を返す"}]}
```

決め手は、『受付』が『倉庫』の中身を自分では持たないことです。品物があるかどうかは、倉庫に聞くまで分かりません。だから受付は、頼みを受けるたびに倉庫へ問い合わせ、返ってきた結果をそのまま相手に伝えます。

昼のあいだは、同じ流れを頼みの数だけ繰り返します。頼みが重なったときは、受け取った順に番号札を渡し、番号の順に倉庫へ問い合わせます。倉庫が空のときは、無いことを伝えて、入る見込みの日を答えます。

夕方には窓口を閉め、その日に受けた頼みと返した品物の数を帳簿に書きます。数が合わないときは、倉庫の在庫表と照らして、どこでずれたかを確かめます。

ほかに、夜間受付の当番と、倉庫が遠いときの取り寄せの話があります。"""

GRADE_ANSWER = """```tonari-grade
[{"concept": "受付", "target": "倉庫", "rel": "related", "result": "partial", "evidence": "__EV__"}]
```

方向は合っています。足りないのは、倉庫が空のときに受付がどう返すかです。"""

RECORD = """```tonari-map
{"center": "受付", "gist": "頼みを受け取り、倉庫から品物を出して返す役", "src": "一般", "broader": [{"label": "窓口", "why": "頼みを受ける役の一種", "src": "一般"}], "narrower": [], "opposite": [], "related": [{"label": "倉庫", "rel": "道具", "link": "から品物を出す", "why": "中身は倉庫が持つ", "src": "一般"}], "examples": ["来た人に番号札を渡す場面"], "nonexamples": ["倉庫の棚卸しの作業"]}
```

```tonari-check
[{"q": "もし倉庫が空だったら、受付は頼みにどう返すことになるか。なぜか。", "a": "品物が無いと返す。受付は中身を自分で持たないから", "hints": ["受付が自分で持っているものを考える", "倉庫に聞いた結果をそのまま伝える"], "type": "もしも", "concept": "受付", "rel": "related", "target": "倉庫"}]
```"""


# 発言に「会計」があるときの記録（全体の地図の場面用）。「倉庫」は上の記録にも出るので、話題をまたぐ言葉になる
RECORD_KAIKEI = """```tonari-map
{"center": "会計", "gist": "お金の出入りを数える役", "src": "一般", "broader": [{"label": "事務", "why": "事務の仕事の一種", "src": "一般"}], "narrower": [{"label": "現金の会計", "why": "その場で払う形", "src": "一般"}, {"label": "掛けの会計", "why": "あとで払う形", "src": "一般"}], "opposite": [{"label": "受付", "axis": "数えるか、受け取るか", "src": "一般"}], "related": [{"label": "倉庫", "rel": "道具", "link": "の在庫を数える", "why": "数える相手", "src": "一般"}, {"label": "帳簿", "rel": "部分", "why": "会計の部品", "src": "一般"}], "examples": [], "nonexamples": []}
```"""


def tutor() -> None:
    sid = arg("--resume") or f"fake-{os.getpid()}"
    out({"type": "system", "subtype": "init", "session_id": sid})
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        content = msg.get("message", {}).get("content", "")
        time.sleep(delay())
        if "種類=answer" in content or "種類=confirm" in content:
            text = GRADE_ANSWER.replace("__EV__", said_of(content)[:12])
        elif "長めに" in said_of(content):
            text = LONG_ANSWER
        else:
            text = TUTOR_ANSWER
        for i in range(0, len(text), 40):
            out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text[i:i + 40]}}})
            time.sleep(0.01)
        out({"type": "result", "session_id": sid, "is_error": False, "result": text})


def spare() -> None:
    system = ""
    f = arg("--system-prompt-file")
    if f:
        try:
            system = open(f, encoding="utf-8").read()[:200]
        except OSError:
            pass
    line = sys.stdin.readline()
    if not line:
        return
    content = json.loads(line).get("message", {}).get("content", "")
    if "照らし合わせる役" in system:
        # 作り物の決まり: 予想に「頼みを受け」があれば答えの核が入っていたことに、「分からない」だけなら照らせないことに、
        # 「こわれた返し」があれば形の崩れた返しに、ほかは入っていなかったことにする。「鍵」があれば食い違いを、
        # 「たぶん」があれば答えが触れていない点を足す。決め手は、予想に「自分では持たない」があれば入っていたことにする
        pred = content[content.find("<本人の予想>") + 7:content.find("</本人の予想>")].strip()
        d = {"core": "out", "core_q": "", "key": "out", "key_q": "", "diff": "", "diff_q": "", "open_q": ""}
        if "頼みを受け" in pred:
            d.update(core="in", core_q="頼みを受け")
        if "自分では持たない" in pred:
            d.update(key="in", key_q="自分では持たない")
        if "鍵" in pred:
            d.update(diff="予想では鍵を持つとしていますが、答えでは倉庫から品物を出して返すとしています。", diff_q="倉庫』から品物を出して返します")
        if "たぶん" in pred:
            d.update(open_q="たぶん")
        if "こわれた返し" in pred:
            res = "これは JSON ではありません"
        elif "分からない" in pred:
            res = json.dumps({"core": "none"})
        else:
            res = json.dumps(d, ensure_ascii=False)
    elif "読みを確かめる役" in system:
        # 作り物の決まり: 発言に「の知識」があれば、別の読みがあったことにする
        said = content[content.find("<本人の発言>") + 8:content.find("</本人の発言>")].strip()
        res = json.dumps({"alt": True, "took": "受付という役の説明", "others": [{"label": "手元の受付の手引きの中身", "ask": "手元の受付の手引きに書いてある中身を教えて"}]}
                         if "の知識" in said else {"alt": False}, ensure_ascii=False)
    elif "記録役" in system:
        res = RECORD_KAIKEI if "会計" in content[:content.find("</本人の発言>")] else RECORD
    elif "判定役" in system and "たとえ" in system:
        res = json.dumps({"results": []})
    elif "判定役" in system:
        res = json.dumps({"results": ["partial"] * max(1, content.count("中心 "))})
    elif "直し役" in system:
        res = json.dumps({"text": "作り物の聞き取り", "edits": [], "unsure": [], "title": "作り物", "kind": "question"}, ensure_ascii=False)
    else:
        res = "{}"
    out({"type": "result", "is_error": False, "result": res})


if __name__ == "__main__":
    spare() if "--no-session-persistence" in ARGS else tutor()
