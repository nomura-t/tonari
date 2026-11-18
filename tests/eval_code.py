"""コードと構成の表現（v0.7）を、本物の先生役で測る（DESIGN 18章）。pytest の対象外。

  uv run python -m tests.eval_code --n 2 --out 置き場/code.json          # 流して数える
  uv run python -m tests.eval_code --report 置き場/before.json 置き場/after.json   # 並べた表（1つでもよい）

測り方は tests/eval_grounding.py と同じ（記録の置き場は一時フォルダ・アプリと同じ経路・新しい話題・同時に3本まで）。
記録役と照らし合わせ役は止める（先生役の答えだけを見るため。先生役に渡す中身は変わらない）。
問いは eval_grounding の作り物の14問（前からの形が変わらないかを見る）に、エンジニアリングの作り物の問いを足したもの。

数えるもの。
(a) 前からの14問の図の形（たとえの塊とコードの塊を除いた図の種類。文だけなら text）。指示を変える前と後で同じか。
(b) エンジニアリングの問いの図の形が、狙いの形か。同じ構成についての3つの問い（何が何に依存するか・誰が誰に何を渡すか・
    何がどの順に起きるか）が、構成の図・しくみの絵・流れに分かれるか。
(c) コードの出方。コードを求めた問いにコードの塊（素の塊か、読むコード）が出たか。エンジニアリングでない問いにコードが出ていないか。
(d) 捨てた塊の数と理由。読むコードの注釈のうち、行に結べなかった数。
(e) 先生役の秒と、見える本文の字（図・たとえ・考え・コードの塊を除く）。
"""
import argparse
import asyncio
import json
import os
import re
import statistics
import time
from pathlib import Path

os.environ.setdefault("TONARI_RECORDER", "off")   # 記録役と照らし合わせ役を止める（server を読む前に）

from tests import eval_grounding as eg   # 読み込んだ時点で記録の置き場を一時フォルダへ向ける  # noqa: E402
from server import brain, config, corpus, db, judge, pipeline, tutor  # noqa: E402
from server import app as appmod  # noqa: E402

ENG = [
    # コードを求める問い
    ("cd1", "コード", "Python のデコレータって、どう書いてどう動くの？"),
    ("cd2", "コード", "JavaScript の async/await と、Promise の then でつなぐ書き方は、どう違うの？"),
    ("cd3", "コード", "Rust の所有権のムーブを、短いコードで見せて"),
    ("cd4", "コード", "SQL の LEFT JOIN と INNER JOIN で、結果がどう変わるのかを例で教えて"),
    # 同じ構成についての3つの問い（依存・受け渡し・順番）
    ("pr_dep", "依存", "ブラウザ・API サーバー・DB・キャッシュ・ジョブキュー・ワーカーでできた典型的な Web アプリで、何が何に依存しているの？"),
    ("pr_parts", "部品", "ブラウザ・API サーバー・DB・キャッシュ・ジョブキュー・ワーカーでできた典型的な Web アプリで、注文を1件受けたとき、どの部品がどの部品に何を渡すの？"),
    ("pr_flow", "仕組み", "ブラウザ・API サーバー・DB・キャッシュ・ジョブキュー・ワーカーでできた典型的な Web アプリで、注文を受けてから完了メールが出るまで、何がどの順に起きるの？"),
    # 依存と構成
    ("dp1", "依存", "クリーンアーキテクチャでは、どの層がどの層に依存していいの？"),
    ("dp2", "依存", "React のアプリで、画面のコンポーネント・状態の管理・API の呼び出しは、ふつうどういう依存関係にするの？"),
    ("ar1", "構成", "Kubernetes の全体の構成を教えて。コントロールプレーンとノードには、それぞれ何があるの？"),
    ("ar2", "構成", "マイクロサービスで作った EC サイトのアーキテクチャは、どういう構成になるの？"),
    # 状態・データ・型（mermaid）
    ("st1", "状態", "TCP の接続は、どういう状態をどう移り変わるの？"),
    ("er1", "データ", "EC サイトの注文まわりのテーブルは、どういう関係で設計するの？"),
    ("cl1", "型", "Strategy パターンでは、クラスどうしはどういう関係になるの？"),
    # ファイルの並び
    ("ft1", "ファイル", "Next.js の App Router のプロジェクトは、ふつうどういうフォルダ構成にするの？"),
]
QUESTIONS = list(eg.QUESTIONS) + ENG
BASE = {q for q, _, _ in eg.QUESTIONS}
# 狙いの形（どれかに当たればよい）。mermaid は「mermaid:最初の語」
EXPECT = {
    "pr_dep": {"arch"}, "pr_parts": {"parts"}, "pr_flow": {"flow"},
    "dp1": {"arch"}, "dp2": {"arch"}, "ar1": {"arch"}, "ar2": {"arch"},
    "st1": {"mermaid:stateDiagram-v2", "mermaid:stateDiagram"}, "er1": {"mermaid:erDiagram"}, "cl1": {"mermaid:classDiagram"},
    "ft1": {"tree"},
}
WANT_CODE = {"cd1", "cd2", "cd3", "cd4"}
NO_CODE = {"nm1", "cf_decide", "cf_overlap", "cf_define", "df2"}   # コードが出てはいけない問い（エンジニアリングの外・概念の定義）

FENCE = re.compile(r"```([^\n`]*)\n(.*?)```", re.S)
INLINE = re.compile(r"`[^`\n]+`")


def shape_of(md: str) -> str:
    views = tutor.parse_blocks(md or "")["views"]
    side = set(tutor.SIDE_TYPES) | {"code"}
    main = next((v for v in views if v["type"] not in side), None)
    if not main:
        return "text"
    if main["type"] == "mermaid":
        first = next((l.strip() for l in (main.get("code") or "").splitlines() if l.strip() and not l.strip().startswith("%%")), "")
        return "mermaid:" + (first.split()[0] if first else "?")
    return main["type"]


def analyse(r: dict) -> dict:
    if r["status"] != "done":
        return {}
    md = r["answer_md"] or ""
    st = json.loads(r["stage_ms"] or "{}")
    plain = [(k.strip(), body) for k, body in FENCE.findall(md) if not k.strip().startswith("tonari-") and k.strip() != "mermaid"]
    raw = [k.strip() for k, _ in FENCE.findall(md)]
    prose = FENCE.sub("", md)
    parsed = tutor.parse_blocks(md)
    code_views = [v for v in parsed["views"] if v["type"] == "code" and v.get("notes")]   # 読むコード（注釈つき）
    return {
        "tutor_s": round((st.get("tutor") or 0) / 1000, 1), "visible": len(prose.strip()), "total": len(md),
        "budget": (st.get("budget") or {}).get("chars"), "shape": shape_of(md),
        "plain": len(plain), "plain_langs": [k or "(なし)" for k, _ in plain], "plain_lines": sum(b.count("\n") for _, b in plain),
        "tcode": raw.count("tonari-code"), "tcode_shown": len(code_views),
        "notes": sum(len(v.get("notes") or []) for v in code_views),
        "inline": len(INLINE.findall(prose)),
        "errors": [e for e in (st.get("block_errors") or parsed["errors"]) if not e.startswith(eg.NOT_BLOCK)],
    }


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def load(path: Path) -> list[tuple[dict, dict]]:
    rows = [json.loads(l) for l in path.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return [(r, analyse(r)) for r in rows]


def report(path: Path) -> str:
    rows = load(path)
    done = [(r, a) for r, a in rows if r["status"] == "done"]
    out = [f"== {path.name}: 答え {len(done)}/{len(rows)}"]
    shapes: dict[str, list[str]] = {}
    for r, a in done:
        shapes.setdefault(r["qid"], []).append(a["shape"])
    out.append("(a) 前からの14問の形: " + "、".join(f"{q}={'/'.join(shapes.get(q, ['—']))}" for q, _, _ in eg.QUESTIONS))
    hit = sum(1 for q, ss in shapes.items() if q in EXPECT for s in ss if s in EXPECT[q])
    tot = sum(len(ss) for q, ss in shapes.items() if q in EXPECT)
    out.append(f"(b) エンジニアリングの問いの形（狙いどおり {hit}/{tot}）: " +
               "、".join(f"{q}={'/'.join(shapes.get(q, ['—']))}（狙い {'・'.join(sorted(EXPECT[q]))}）" for q, _, _ in ENG if q in EXPECT))
    has = lambda a: a["plain"] + a["tcode"] > 0   # noqa: E731
    out.append(f"(c) コードの塊が出た答え: コードを求めた問い {sum(1 for r, a in done if r['qid'] in WANT_CODE and has(a))}/"
               f"{sum(1 for r, _ in done if r['qid'] in WANT_CODE)}・出てはいけない問い {sum(1 for r, a in done if r['qid'] in NO_CODE and has(a))}/"
               f"{sum(1 for r, _ in done if r['qid'] in NO_CODE)}・前からの14問の全部 {sum(1 for r, a in done if r['qid'] in BASE and has(a))}/"
               f"{sum(1 for r, _ in done if r['qid'] in BASE)}")
    out.append(f"    素のコードの塊 {sum(a['plain'] for _, a in done)}（言語なし {sum(a['plain_langs'].count('(なし)') for _, a in done)}）・"
               f"読むコード 書いた {sum(a['tcode'] for _, a in done)}／画面に出る {sum(a['tcode_shown'] for _, a in done)}・注釈 {sum(a['notes'] for _, a in done)}・"
               f"文の中のコード {sum(a['inline'] for _, a in done)}")
    out.append("    問いごと: " + "、".join(f"{r['qid']}#{r['rep']}=素{a['plain']}/読{a['tcode_shown']}/{a['shape']}" for r, a in done if r["qid"] not in BASE))
    errs = [e for _, a in done for e in a["errors"]]
    out.append(f"(d) 捨てた塊・一部を捨てた記録 {len(errs)}: " + "／".join(sorted({e[:60] for e in errs})))
    for name, grp in (("前からの14問", [a for r, a in done if r["qid"] in BASE]), ("エンジニアリングの問い", [a for r, a in done if r["qid"] not in BASE])):
        out.append(f"(e) {name}: 先生役の秒 中央値 {med([a['tutor_s'] for a in grp])}・見える本文の字 中央値 {med([a['visible'] for a in grp])}・"
                   f"答えの字（塊を含む）中央値 {med([a['total'] for a in grp])}")
    return "\n".join(out)


async def run_one(qid: str, cat: str, q: str, rep: int, sem: asyncio.Semaphore, out_jsonl: Path) -> None:
    async with sem:
        t = db.now()
        with db.tx() as con:
            sid = con.execute("INSERT INTO session(title, model, created_at, updated_at, read_at) VALUES(?,?,?,?,?)",
                              ("新しい話題", config.TUTOR_MODEL, t, t, t)).lastrowid
            tid = appmod.new_turn(con, sid, "text", final_text=q, title=q[:16])
        try:
            await pipeline.run_text(tid, "question")
        finally:
            tu = brain.TUTORS.tutors.pop(sid, None)
            if tu:
                await tu.close()
        with db.tx() as con:
            row = db.row(con, "SELECT answer_md, status, error, stage_ms FROM turn WHERE id=?", (tid,))
        rec = {"qid": qid, "cat": cat, "rep": rep, "q": q, "status": row["status"], "error": row["error"],
               "answer_md": row["answer_md"], "stage_ms": row["stage_ms"]}
        with out_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        a = analyse(rec)
        print(f"{qid}#{rep} {rec['status']} 先生役{a.get('tutor_s')}秒 本文{a.get('visible')}字/目安{a.get('budget')} 形={a.get('shape')} "
              f"素のコード={a.get('plain')} 読むコード={a.get('tcode_shown')} 捨てた={len(a.get('errors') or [])}", flush=True)


async def main_run(n: int, out: Path, only: list[str] | None) -> None:
    db.init()
    info = await asyncio.to_thread(corpus.refresh)
    out_jsonl = out.with_suffix(".jsonl")
    sem = asyncio.Semaphore(3)
    jobs = [run_one(qid, cat, q, rep, sem, out_jsonl) for rep in range(1, n + 1) for qid, cat, q in QUESTIONS
            if not only or qid in only or cat in only]
    print(f"記録の置き場 {config.DATA_DIR}・先生役 {config.TUTOR_MODEL}・指示の印 {tutor.prompt_sig()}・棚 {info.get('pages')}・{len(jobs)}本", flush=True)
    try:
        await asyncio.gather(*jobs, return_exceptions=True)
    finally:
        await brain.TUTORS.close_all()
        for p in (judge.POOL, judge.PAIR_POOL):
            await p.close()
    print(report(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--report", type=Path, nargs="*")
    a = ap.parse_args()
    if a.report:
        for p in a.report:
            print(report(p))
    else:
        t0 = time.time()
        asyncio.run(main_run(a.n, a.out, a.only))
        print(f"{time.time() - t0:.0f}秒")
