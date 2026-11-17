"""話の間合い・記録役・考えの塊を、本物の先生役で測る（DESIGN 16.7・16.8）。pytest の対象外。

  uv run python -m tests.eval_tempo --n 2 --out 置き場/tempo.json
  uv run python -m tests.eval_tempo --report 置き場/tempo.json

測り方は tests/eval_grounding.py と同じ（記録の置き場は一時フォルダ・アプリと同じ経路・新しい話題・同時に3本まで）。
問いは eval_grounding の作り物の14問に、考えを求める問い2・詳しくを頼む問い1・Web で調べる必要のある問い1を足した18問。

数えるもの。
(a) 先生役だけの秒（送ってから答えが届くまで）と、答えの見える本文の字数（塊を除く）。字数の目安ごとに並べる。
(b) 先生役が自分で書いた見えない塊（記録用の地図・確かめの問い）の数。狙いは0（位置の図を答えの図にした往復を除く）。
(c) 記録役の秒と、記録役が足した地図・確かめの問いの数、機械が外した問いの数、取れなかった回数。
(d) 図の形（eval_grounding の (c) と同じ見方）。迷いやすい4問としくみの絵の2問が狙いの形か。
(e) 考えの塊が出た答えの数。考えを求めた問いでは出る、事実の問いでは出ないのが狙い。
(f) Web で調べる入口（tonari-lookup）が出た答え。
(g) 地図の related のうち、つなぐ言葉（link）が決まりを通った割合。
"""
import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

from tests import eval_grounding as eg   # 読み込んだ時点で記録の置き場を一時フォルダへ向ける
from server import brain, config, corpus, db, judge, pipeline, recorder, tutor  # noqa: E402
from server import app as appmod  # noqa: E402

EXTRA = [
    ("th1", "考え", "マイクロサービスは小さいチームでも採るべきだと思う？あなたの考えを聞かせて"),
    ("th2", "考え", "推測でいいので、5年後に SQL を手で書く仕事はどうなっていると思う？"),
    ("lg1", "詳しく", "TLS のハンドシェイクを詳しく教えて"),
    ("lk1", "調べ", "Python のいちばん新しい安定版はいくつで、いつ出た？"),
]
QUESTIONS = list(eg.QUESTIONS) + EXTRA
FACT = {q for q, c, _ in QUESTIONS if c in ("定義", "仕組み", "数", "迷う", "部品")}


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
            first = db.row(con, "SELECT answer_md, status, error FROM turn WHERE id=?", (tid,))
        for _ in range(150):   # 記録役を待つ（裏で走る）
            with db.tx() as con:
                row = db.row(con, "SELECT * FROM turn WHERE id=?", (tid,))
            st = json.loads(row["stage_ms"] or "{}")
            if row["status"] != "done" or "recorder" in st or len(tutor.strip_blocks(row["answer_md"] or "")) < 40:
                break
            await asyncio.sleep(1)
        with db.tx() as con:
            rels = db.rows(con, "SELECT rel, detail, phrase FROM relation WHERE turn_id=?", (tid,))
            checks = db.rows(con, "SELECT id FROM checkq WHERE turn_id=?", (tid,))
        rec = {"qid": qid, "cat": cat, "rep": rep, "status": row["status"], "error": row["error"],
               "tutor_md": first["answer_md"], "answer_md": row["answer_md"], "stage_ms": row["stage_ms"],
               "rels": rels, "n_checks": len(checks)}
        with out_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        a = analyse(rec)
        print(f"{qid}#{rep} {rec['status']} 先生役{a.get('tutor_s')}秒 本文{a.get('visible')}字/目安{a.get('budget')} 形={a.get('shape')} "
              f"考え={a.get('think')} 記録役{a.get('recorder_s')}秒 地図={a.get('rec_map')} 問い={a.get('n_checks')}", flush=True)


def analyse(r: dict) -> dict:
    if r["status"] != "done":
        return {}
    st = json.loads(r["stage_ms"] or "{}")
    own = tutor.parse_blocks(r["tutor_md"] or "")
    views = own["views"]
    main = tutor.main_view(views)
    raw_kinds = [k for k, _ in tutor.BLOCK_RE.findall(r["tutor_md"] or "")]
    related = [x for x in r["rels"] if x["rel"] == "related"]
    return {
        "tutor_s": round((st.get("tutor") or 0) / 1000, 1), "visible": len(tutor.strip_blocks(r["tutor_md"] or "")),
        "total": len(r["tutor_md"] or ""), "budget": (st.get("budget") or {}).get("chars"),
        "shape": main["type"] if main else "text", "think": sum(1 for v in views if v["type"] == "think"),
        "own_check": raw_kinds.count("tonari-check"), "own_map": raw_kinds.count("tonari-map"),
        "lookup": bool(own.get("lookup")),
        "recorder_s": round(st["recorder"] / 1000, 1) if "recorder" in st else None,
        "recorder_error": st.get("recorder_error"), "rec_map": (st.get("recorded") or {}).get("map"),
        "n_checks": r["n_checks"], "related": len(related), "linked": sum(1 for x in related if x["phrase"]),
        "errors": [e for e in st.get("block_errors") or []],
    }


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def report(path: Path) -> str:
    rows = [json.loads(l) for l in path.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    done = [(r, analyse(r)) for r in rows if r["status"] == "done"]
    out = [f"答え {len(done)}/{len(rows)}"]
    base14 = [a for r, a in done if r["qid"] in {q for q, _, _ in eg.QUESTIONS}]
    out.append(f"(a) 作り物の14問: 先生役の秒の中央値 {med([a['tutor_s'] for a in base14])}・見える本文の字の中央値 "
               f"{med([a['visible'] for a in base14])}・答えの字（塊を含む）の中央値 {med([a['total'] for a in base14])}")
    for b in sorted({a["budget"] for _, a in done if a["budget"]}):
        g = [a for _, a in done if a["budget"] == b]
        out.append(f"    目安 {b}字: {len(g)}答え・本文の字 中央値 {med([a['visible'] for a in g])}（最小 {min(a['visible'] for a in g)}・"
                   f"最大 {max(a['visible'] for a in g)}）・目安の1.3倍を超えた {sum(1 for a in g if a['visible'] > b * 1.3)}・先生役の秒 {med([a['tutor_s'] for a in g])}")
    out.append(f"(b) 先生役が自分で書いた 確かめの問いの塊 {sum(a['own_check'] for _, a in done)}・地図の塊 {sum(a['own_map'] for _, a in done)}"
               f"（うち位置の図を答えの図にした {sum(1 for _, a in done if a['shape'] == 'map')}）")
    rec = [a for _, a in done if a["recorder_s"] is not None]
    out.append(f"(c) 記録役が走った {len(rec)}・秒の中央値 {med([a['recorder_s'] for a in rec])}・取れなかった {sum(1 for a in rec if a['recorder_error'])}・"
               f"地図を足した {sum(1 for a in rec if a['rec_map'])}・確かめの問いが1つ以上 {sum(1 for _, a in done if a['n_checks'])}/{len(done)}")
    shapes = {}
    for r, a in done:
        shapes.setdefault(r["qid"], []).append(a["shape"])
    exp = {**eg.EXPECT, **eg.EXPECT_PARTS}
    out.append("(d) 形: " + "、".join(f"{q}={'/'.join(v)}{'' if q not in exp else '（狙い ' + exp[q] + '）'}" for q, v in shapes.items()))
    out.append(f"(e) 考えの塊: 考えを求めた問い {sum(1 for r, a in done if r['cat'] == '考え' and a['think'])}/{sum(1 for r, _ in done if r['cat'] == '考え')}・"
               f"事実の問い {sum(1 for r, a in done if r['qid'] in FACT and a['think'])}/{sum(1 for r, _ in done if r['qid'] in FACT)}")
    out.append(f"(f) Web で調べる入口: 調べの問い {sum(1 for r, a in done if r['cat'] == '調べ' and a['lookup'])}/{sum(1 for r, _ in done if r['cat'] == '調べ')}・"
               f"ほかの問い {sum(1 for r, a in done if r['cat'] != '調べ' and a['lookup'])}/{sum(1 for r, _ in done if r['cat'] != '調べ')}")
    out.append(f"(g) 地図の related {sum(a['related'] for _, a in done)}・つなぐ言葉が通った {sum(a['linked'] for _, a in done)}")
    errs = [e for _, a in done for e in a["errors"]]
    out.append(f"捨てた塊と外した問いの記録 {len(errs)}: " + "／".join(sorted({e.split('（')[0][:30] for e in errs})))
    return "\n".join(out)


async def main_run(n: int, out: Path, only: list[str] | None) -> None:
    db.init()
    info = await asyncio.to_thread(corpus.refresh)
    out_jsonl = out.with_suffix(".jsonl")
    sem = asyncio.Semaphore(3)
    jobs = [run_one(qid, cat, q, rep, sem, out_jsonl) for rep in range(1, n + 1) for qid, cat, q in QUESTIONS
            if not only or qid in only]
    print(f"記録の置き場 {config.DATA_DIR}・先生役 {config.TUTOR_MODEL}・記録役 {config.RECORDER_MODEL}・棚 {info.get('pages')}・{len(jobs)}本", flush=True)
    try:
        await asyncio.gather(*jobs, return_exceptions=True)
    finally:
        await brain.TUTORS.close_all()
        for p in (judge.POOL, judge.PAIR_POOL, recorder.POOL):
            await p.close()
    print(report(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    if a.report:
        print(report(a.report))
    else:
        t0 = time.time()
        asyncio.run(main_run(a.n, a.out, a.only))
        print(f"{time.time() - t0:.0f}秒")
