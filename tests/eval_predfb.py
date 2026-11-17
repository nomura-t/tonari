"""予想の照らし合わせ役（server/predfb.py）の測り。作り物の問い・答え・予想の組を本物の照らし合わせ役（sonnet）に流し、
「答えの核が予想に入っていたか」の判断が狙いと合うか、甘い側に外れた数（入っていない予想を入っていたとした数）、
抜き出した字が照らせずに機械が外した項目の数を数える（DESIGN 17.12）。Claude の枠を使う。pytest の対象外。

  uv run python -m tests.eval_predfb --n 2 --out <置き場>/predfb.json

組は、5つの答え（どれも作り物の一般の話）に、核を言っている予想（in）・脇の点だけ合う予想（side。核は入っていないので out が狙い）・
別のところにある予想（out）を1つずつと、照らせない予想（none: 分からない・問いになっている・関係の無い発言）、
聞き取りの揺れのある予想を足したもの。照らし合わせ役の指示に書いた言葉とは別の題材にしてある。
"""
import argparse
import asyncio
import json
import os
import re
import tempfile
from pathlib import Path

os.environ.setdefault("TONARI_DATA_DIR", tempfile.mkdtemp(prefix="tonari-eval-"))

from server import predfb  # noqa: E402

TOPICS = {
    "cache": ("キャッシュはなぜ速くなるの？",
              "キャッシュは、一度取ってきた結果を手元に置いておき、同じ頼みが来たら取りに行かずに手元から返す仕組みです。\n\n"
              "決め手は、遠くまで取りに行く回数が減ることです。たとえばブラウザは、一度読み込んだ画像を PC の中に置いておき、次に同じページを開くときはサーバーに頼まずに表示します。\n\n"
              "注意は、元の中身が変わっても、手元の写しは古いままになることです。"),
    "2fa": ("二段階認証はなぜ安全になるの？",
            "二段階認証は、パスワードに加えて、もう1つ別の種類の確かめを求める仕組みです。\n\n"
            "決め手は、2つの確かめが別々の経路にあることです。パスワードは「知っているもの」、スマホに届くコードは「持っているもの」なので、パスワードが漏れても、スマホを持っていない相手は入れません。\n\n"
            "弱点は、コードを聞き出す詐欺で、本人が相手に伝えてしまうと破られます。"),
    "fukuri": ("複利だとなぜお金が増えやすいの？",
               "複利は、付いた利息を元本に足して、次の利息を「元本＋利息」に対して計算する仕組みです。\n\n"
               "決め手は、利息が利息を生むことです。年5％なら、100万円は1年目に5万円増え、2年目は105万円に対して5万2,500円増えます。単利は元本の100万円にだけ利息が付くので、毎年5万円のままです。\n\n"
               "差は年数が長いほど開きます。"),
    "server": ("サーバーを2台にするとなぜ止まりにくいの？",
               "サーバーを2台にするのは、1台が壊れても、もう1台が代わりに応える形にするためです。これを冗長化と言います。\n\n"
               "決め手は、同時に2台とも壊れる見込みが、1台が壊れる見込みよりずっと小さいことです。ふだんは前に置いた振り分け役が2台に頼みを配り、片方が応えなくなったら、もう片方だけに配ります。\n\n"
               "注意は、振り分け役そのものが1台だと、そこが止まると全部止まることです。"),
    "pan": ("パンはなぜ膨らむの？",
            "パンが膨らむのは、生地の中の酵母が糖を食べて、二酸化炭素を出すからです。\n\n"
            "決め手は、小麦粉をこねてできる網（グルテン）が、その気体を逃がさずに包むことです。気体は生地の中で小さな泡になり、焼くと熱で泡が広がって、さらに膨らみます。\n\n"
            "酵母は温かいとよく働き、冷たいと働きが鈍ります。"),
}

# (題材, 狙いの段, 予想)
CASES = [
    ("cache", "in", "前に取ってきたものを手元に取っておいて、同じのが来たらそれを返すから速いんだと思う"),
    ("cache", "in", "一度読み込んだものを保存しておいて、次はそれを使うからだと思う。たぶん圧縮もしている"),
    ("cache", "out", "回線を太くして、一度にたくさん送れるようにするからだと思う"),
    ("2fa", "in", "パスワードのほかに、もう1つ別の確かめをさせるからだと思う"),
    ("2fa", "side", "コードを聞き出す詐欺には弱そうだけど、まちがって他人が入ることは減るんだと思う"),
    ("2fa", "out", "パスワードを長くするから、当てられにくくなるんだと思う"),
    ("fukuri", "in", "付いた利息も元本に入れて、次の利息を計算するからだと思う"),
    ("fukuri", "side", "長く預けるほど差が出るからだと思う。利率が高いのもありそう"),
    ("fukuri", "out", "銀行が特別に上乗せしてくれるからだと思う"),
    ("server", "in", "片方が壊れても、もう片方が代わりに動くからだと思う"),
    ("server", "side", "頼みを2台に配るから、1台あたりが楽になって壊れにくいんだと思う"),
    ("server", "out", "2台あると計算が2倍速くなるからだと思う"),
    ("pan", "in", "イーストが糖を食べてガスを出すからだと思う"),
    ("pan", "side", "焼くと中の泡が熱で広がるからだと思う"),
    ("pan", "out", "卵の力でふくらむんだと思う"),
    ("pan", "in", "イーストがガスお出して、記事の中にたまるからだと思う"),      # 聞き取りの揺れ（を→お・生地→記事）
    ("cache", "none", "うーん、分からない"),
    ("2fa", "none", "それってどういうこと？"),
    ("server", "none", "今日はちょっと眠い"),
]
KINDS = ("core_q", "key_q", "diff", "open_q")     # 照らし合わせ役が字を抜き出す・文を書く項目


def raw_lines(raw: str) -> int:
    """照らし合わせ役が書いた項目の数（機械が字を照らす前）。"""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    try:
        d = json.loads(s[s.find("{"):s.rfind("}") + 1])
    except ValueError:
        return 0
    return sum(1 for k in KINDS if str(d.get(k) or "").strip()) if isinstance(d, dict) else 0


async def run(n: int) -> dict:
    sem = asyncio.Semaphore(3)
    rows = []

    async def one(i: int, topic: str, want: str, pred: str, k: int) -> None:
        said, ans = TOPICS[topic]
        async with sem:
            try:
                s = await predfb.POOL.take()
                raw = await s.ask(predfb.build_input(said, pred, ans), timeout=predfb.TIMEOUT)
                got = predfb.parse(raw, pred, ans)
                rows.append({"i": i, "topic": topic, "want": want, "run": k, "got": got, "written": raw_lines(raw), "raw": raw, "error": None})
            except Exception as e:   # 取れなかった回（画面では「取れませんでした」と出る）
                rows.append({"i": i, "topic": topic, "want": want, "run": k, "got": None, "written": 0, "raw": "", "error": f"{type(e).__name__}: {e}"[:200]})

    await asyncio.gather(*[one(i, t, w, p, k) for i, (t, w, p) in enumerate(CASES) for k in range(n)])
    await predfb.POOL.close()
    return {"n": n, "rows": sorted(rows, key=lambda r: (r["i"], r["run"]))}


def report(d: dict) -> None:
    rows = d["rows"]
    print(f"流した回数 {len(rows)}・取れなかった {sum(bool(r['error']) for r in rows)}・返しを取り出せなかった {sum(1 for r in rows if not r['error'] and not r['got'])}")
    # 狙い: in は「入っていた」、side と out は「入っていなかった」、none は「照らせない」
    want = {"in": "in", "side": "out", "out": "out", "none": "none"}
    for w in ("in", "side", "out", "none"):
        rs = [r for r in rows if r["want"] == w]
        got = [(r["got"] or {}).get("core", "x") for r in rs]
        same = sum(g == want[w] for g in got)
        soft = sum(1 for g in got if want[w] != "in" and g == "in")       # 入っていない予想を、入っていたとした
        hard = sum(1 for g in got if want[w] == "in" and g == "out")      # 入っていた予想を、入っていなかったとした
        print(f"狙い {w}（{want[w]}）: {len(rs)}回のうち、同じ {same}・甘い側 {soft}・厳しい側 {hard}（返した: {' '.join(got)}）")
    kept = sum(sum(1 for k in KINDS if (r["got"] or {}).get(k)) for r in rows)
    written = sum(r["written"] for r in rows)
    print(f"抜き出した字・書いた文 {written}・うち照らせて残った {kept}・機械が外した {written - kept}")
    print(f"食い違いを書いた返し {sum(1 for r in rows if (r['got'] or {}).get('diff'))}（狙い in の組では {sum(1 for r in rows if r['want'] == 'in' and (r['got'] or {}).get('diff'))}）")
    praise = re.compile(r"すばらし|素晴らし|惜し|よく考え|いい線|さすが|お見事|がんば|頑張")
    print(f"ほめ言葉・励ましの入った返し {sum(1 for r in rows if r['got'] and praise.search(json.dumps(r['got'], ensure_ascii=False)))}")
    for r in rows:
        g = r["got"] or {}
        print(f"  {r['i'] + 1:>2}#{r['run']} {r['topic']:<6} 狙い {r['want']:<4} → core {g.get('core', 'x'):<7} key {str(g.get('key') or '-'):<3} "
              + " / ".join(f"{k}: {g[k]}" for k in KINDS if g.get(k)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    if a.report:
        report(json.loads(a.report.read_text(encoding="utf-8")))
        return
    d = asyncio.run(run(a.n))
    if a.out:
        a.out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    report(d)


if __name__ == "__main__":
    main()
