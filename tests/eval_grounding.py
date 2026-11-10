"""たとえと実物の結びつき・図の形・答えまでの時間を、本物の先生役で測る（DESIGN 15.7・15.9）。pytest の対象外。

  uv run python -m tests.eval_grounding --n 3 --out 置き場/baseline.json    # 12問×3回を流して数える
  uv run python -m tests.eval_grounding --rejudge 置き場/baseline.json      # 保存した答えで、数える役だけやり直す
  uv run python -m tests.eval_grounding --report 置き場/baseline.json 置き場/after.json   # 並べた表

記録の置き場（TONARI_DATA_DIR）は起動のたびに新しい一時フォルダにする（本人の記録には触らない）。先生役はアプリと
同じ経路（pipeline.run_text → brain.Tutor の claude -p・新しい話題）で1問ずつ流し、同時に動かすのは3本まで。
アプリの起動と同じく、棚の写し（corpus.refresh）を作ってから流す（--no-corpus で外せる）。
問いは作り物の8問（一般的な技術やお金の話題）と、DESIGN 12.4 の迷いやすい4問の文。

数えるもの。
(a) たとえの塊の対の実際の名前（t）が、塊の外の本文に同じ字（fold）で出ている割合。先生役が書いたままの塊（raw）と、
    画面に出る塊（shown・機械の決まりと判定役を通ったあと）の2つ。
(b) 判定役（sonnet・judge.py と同じ呼び方）に本文を渡して数えさせる、塊に結ばれていない文の中のたとえの数（loose）と、
    最初の段落の比喩の動詞・名詞の数（lead）。数える役の指示（COUNT_SYSTEM）は変えない（変えたら両方を --rejudge する）。
(c) 問いごとの図の形（たとえの塊を除いた図の種類。文だけなら text）が3回とも同じか。
(d) 送ってから答えが届くまでの秒（壁時計。判定役の分も入る）の中央値と、先生役だけの秒。
(e) 捨てた塊の数と理由（確かめの問いを外した記録は除く）。
(f) v0.4 作業B: しくみの絵を狙う2問の形、確かめの問いにヒントが付いた割合と、機械が外したヒントの数（答えの字を含む段）。
"""
import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

# 本人の記録に触らないよう、server を読む前に必ず一時フォルダへ向ける（config は読み込んだ時点の値を使う）
_TMP = Path(tempfile.mkdtemp(prefix="tonari-eval-"))
os.environ["TONARI_DATA_DIR"] = str(_TMP)

from server import brain, config, corpus, db, judge, pipeline, tutor  # noqa: E402
from server import app as appmod  # noqa: E402

assert config.DATA_DIR == _TMP and config.DATA_DIR != config._default_data_dir(), "記録の置き場が一時フォルダでない"

QUESTIONS = [
    # (id, 種類, 問い)。作り物の8問
    ("an1", "たとえ", "公開鍵暗号を、たとえを使って説明して"),
    ("an2", "たとえ", "TCP の再送の仕組みを、身近なものにたとえて説明して"),
    ("df1", "定義", "キャッシュって何？"),
    ("df2", "定義", "冪等性ってどういう意味？"),
    ("mc1", "仕組み", "DNS の名前解決の仕組みを教えて"),
    ("mc2", "仕組み", "ガベージコレクションは、どうやって要らなくなったメモリを見つけるの？"),
    ("mc3", "仕組み", "HTTPS で通信が始まるまでに、裏で何が起きているの？"),
    ("nm1", "数", "複利ってどういうこと？実際の数字で"),
    # DESIGN 12.4 の迷いやすい4問（表の文のまま）
    ("cf_decide", "迷う", "遺族基礎年金をもらえるかどうかは、どう判断するの？"),
    ("cf_overlap", "迷う", "社会保険と労働保険には、それぞれどの保険が入る？重なるものはある？"),
    ("cf_compare", "迷う", "Kafka と RabbitMQ の違いは？"),
    ("cf_define", "迷う", "コンセプトマップの「命題」ってどういう意味？"),
    # v0.4 作業B: しくみの絵（部品と受け渡しが中身の、作り物の一般的な問い）
    ("pt1", "部品", "ブラウザで URL を開いてからページが出るまで、どの部品がどう受け渡しをするの？"),
    ("pt2", "部品", "メールを送ってから相手の受信箱に届くまで、どの部品が何を受け渡すの？"),
]
EXPECT = {"cf_decide": "decide", "cf_overlap": "overlap", "cf_compare": "compare", "cf_define": "map"}
EXPECT_PARTS = {"pt1": "parts", "pt2": "parts"}   # 作業B で足した2問（迷いやすい4問の /4 とは別に数える）
BASE12 = [q for q, _, _ in QUESTIONS if q not in EXPECT_PARTS]   # 作業A と同じ12問（秒を比べるとき）
PARTIAL = ("対を捨てた", "一部を捨てた")                          # 塊は残して一部を捨てた・直した記録
NOT_BLOCK = ("確かめの問いを外した", "確かめのヒントを外した")      # 塊を捨てた記録でないもの

COUNT_SYSTEM = """あなたは文章の検査役です。学習アプリの先生役が書いた答えを読み、比喩の出方を数えます。採点や感想は書きません。

数えるものは2つです。
一、loose（たとえの塊に結ばれていない、文の中のたとえ）。<本文> の中で、説明している物事を、別の世界の物や出来事になぞらえて説明している文を数えます。「〜のようなもの」「〜にたとえると」「いわば〜」「〜みたいに」のような明示の言い方も、明示の言い方なしに別の世界の物として語る文（例「DNS はインターネットの電話帳です」）も数えます。1つの文に同じたとえが何度出ても1つです。ただし <たとえの塊> に書かれた元の世界（source）とその対の物（s）を使って、その塊のたとえを指している文は数えません（塊に結ばれているため）。その分野で実際に使われる名前（『キャッシュ』『ファイアウォール』『公開鍵』など）は、名前の元が比喩でも数えません。
二、lead（最初の段落の比喩の動詞・名詞）。<最初の段落> の中で、字どおりの意味でなく比喩として使われている動詞と名詞を1語ずつ数えます（例「門番」「橋渡しする」「引き出しにしまう」）。その分野で実際に使われる用語は数えません。

出力は JSON だけです。前置きもコードの囲みも付けません。
{"loose": [{"phrase": "本文から写した字（40字まで）", "source": "元の世界"}], "lead": [{"word": "本文から写した語", "literal": "実際には何のことか"}]}
数えるものが無ければ空の配列にします。"""

ANALOGY_RE = re.compile(r"```tonari-analogy[ \t]*\n(.*?)```", re.S)


def raw_analogies(md: str) -> list[dict]:
    """先生役が書いたままのたとえの塊（機械の決まりを通す前）。"""
    out = []
    for m in ANALOGY_RE.finditer(md or ""):
        try:
            d = json.loads(m.group(1).strip())
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def first_paragraph(md: str) -> str:
    """画面が大きく出す言い切り（図の置き場所でない最初の段落）。"""
    text = tutor.parse_blocks(md or "")["text"]
    for b in re.split(r"\n\s*\n", text):
        if b.strip() and not re.fullmatch(r"\s*\[\[view:\d+\]\]\s*", b):
            return b.strip()
    return ""


def grounded(pairs: list, body_fold: str) -> tuple[int, int]:
    n = hit = 0
    for p in pairs:
        if isinstance(p, dict) and p.get("t"):
            n += 1
            hit += db.fold(str(p["t"])) in body_fold
    return hit, n


def count_input(md: str) -> str:
    blocks = raw_analogies(md)
    an = "\n".join(f"元の世界 {d.get('source', '')}・学ぶもの {d.get('target', '')}・対の物 " +
                   "、".join(str(p.get("s", "")) for p in d.get("pairs") or [] if isinstance(p, dict))
                   for d in blocks) or "なし"
    return (f"<たとえの塊>\n{an}\n</たとえの塊>\n<最初の段落>\n{first_paragraph(md)}\n</最初の段落>\n"
            f"<本文>\n{tutor.strip_blocks(md or '')}\n</本文>")


def parse_count(raw: str) -> dict | None:
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    i, j = s.find("{"), s.rfind("}")
    try:
        d = json.loads(s[i:j + 1]) if i >= 0 and j > i else None
    except ValueError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("loose"), list) or not isinstance(d.get("lead"), list):
        return None
    return {"loose": d["loose"], "lead": d["lead"]}


async def count(md: str) -> dict:
    """数える役（sonnet・judge.py と同じ model と effort）。読めなければ1回だけやり直す。"""
    last = ""
    for _ in range(2):
        s = brain.Spare(COUNT_SYSTEM, config.FIXER_MODEL, config.FIXER_EFFORT)
        try:
            await s.start()
            last = await s.ask(count_input(md), timeout=120)
        except Exception as e:   # noqa: BLE001
            last = f"ERROR {type(e).__name__}: {e}"
            continue
        c = parse_count(last)
        if c is not None:
            return {**c, "raw": last}
    return {"loose": None, "lead": None, "raw": last}


def analyse(row: dict) -> dict:
    """1回分の答えから、(a) (c) (e) と時間を取り出す（数える役は使わない）。"""
    md = row.get("answer_md") or ""
    st = json.loads(row.get("stage_ms") or "{}")
    body_fold = db.fold(tutor.strip_blocks(md))
    raw = raw_analogies(md)
    a_raw = [grounded(d.get("pairs") or [], body_fold) for d in raw]
    v = appmod.turn_view(row) if md else {"views": []}
    shown = [x for x in v.get("views") or [] if x["type"] == "analogy"]
    a_shown = [grounded(x.get("pairs") or [], body_fold) for x in shown]
    shape = [x["type"] for x in v.get("views") or [] if x["type"] != "analogy"] or ["text"]
    errs = [e for e in st.get("block_errors") or [] if not e.startswith(NOT_BLOCK)]
    # (f) ヒント: 先生役が書いたまま（raw）・機械の決まりのあと（kept）・答えの字を含むとして外した段（dropped）
    raw_checks = tutor.parse_blocks(md)["check"]
    kept_checks, _ = tutor.filter_checks(raw_checks, md)
    hint_raw = sum(len([h for h in (c.get("hints") or []) if isinstance(h, str) and h.strip()]) for c in raw_checks
                   if isinstance(c.get("hints"), list))
    kept_q = {c.get("q") for c in kept_checks}
    hint_dropped = sum(tutor.filter_hints(r.get("hints"), db.fold(str(r.get("a") or "")))[1] for r in raw_checks if r.get("q") in kept_q)
    return {
        "shape": "+".join(shape),
        "analogy_raw": len(raw), "analogy_shown": len(shown),
        "a_raw": [sum(h for h, _ in a_raw), sum(n for _, n in a_raw)],
        "a_shown": [sum(h for h, _ in a_shown), sum(n for _, n in a_shown)],
        "sources": [str(d.get("source", "")) for d in raw],
        "by": [x.get("by") for x in shown], "checked": [x.get("checked") for x in shown],
        "flow_case": [x.get("case") for x in v.get("views") or [] if x["type"] == "flow"],
        "flow_ex": [sum(1 for s in x.get("steps") or [] if s.get("ex")) for x in v.get("views") or [] if x["type"] == "flow"],
        "block_errors": errs,
        "tutor_s": (st.get("tutor") or 0) / 1000,
        "pair_judge_s": (st.get("pair_judge") or 0) / 1000,
        "pair_verdicts": st.get("analogy"),
        "chars": len(tutor.strip_blocks(md)),
        "checks": len(kept_checks), "checks_with_hints": sum(1 for c in kept_checks if c.get("hints")),
        "hints_raw": hint_raw, "hints_kept": sum(len(c.get("hints") or []) for c in kept_checks), "hints_dropped": hint_dropped,
        "parts": [{"n_parts": len(x.get("parts") or []), "n_links": len(x.get("links") or []),
                   "nested": sum(1 for p in x.get("parts") or [] if p.get("in")), "case": bool(x.get("case"))}
                  for x in v.get("views") or [] if x["type"] == "parts"],
    }


async def run_one(qid: str, cat: str, q: str, rep: int, sem: asyncio.Semaphore, out_jsonl: Path) -> dict:
    async with sem:
        t = db.now()
        with db.tx() as con:
            sid = con.execute("INSERT INTO session(title, model, created_at, updated_at, read_at) VALUES(?,?,?,?,?)",
                              ("新しい話題", config.TUTOR_MODEL, t, t, t)).lastrowid
            tid = appmod.new_turn(con, sid, "text", final_text=q, title=q[:16])
        t0 = time.time()
        try:
            await pipeline.run_text(tid, "question")
        finally:
            tu = brain.TUTORS.tutors.pop(sid, None)
            if tu:
                await tu.close()
        wall = time.time() - t0
        with db.tx() as con:
            row = db.row(con, "SELECT * FROM turn WHERE id=?", (tid,))
        rec = {"qid": qid, "cat": cat, "q": q, "rep": rep, "status": row["status"], "error": row["error"],
               "wall_s": round(wall, 1), "answer_md": row["answer_md"], "stage_ms": row["stage_ms"]}
        if row["status"] == "done":
            rec.update(analyse(row))
            rec["count"] = await count(row["answer_md"] or "")
        with out_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{qid}#{rep} {rec['status']} {rec['wall_s']}秒 形={rec.get('shape')} "
              f"たとえ={rec.get('analogy_raw')} loose={len((rec.get('count') or {}).get('loose') or [])} "
              f"lead={len((rec.get('count') or {}).get('lead') or [])}", flush=True)
        return rec


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[(r["qid"], r["rep"])] = r   # 同じ問いと回は後の行が勝つ（やり直し）
    return list(out.values())


def summarize(runs: list[dict]) -> dict:
    done = [r for r in runs if r["status"] == "done"]
    def ratio(key):
        h = sum(r[key][0] for r in done)
        n = sum(r[key][1] for r in done)
        return {"hit": h, "pairs": n, "rate": round(h / n, 3) if n else None}
    counted = [r for r in done if (r.get("count") or {}).get("loose") is not None]
    shapes = {}
    for qid, _, _ in QUESTIONS:
        ss = [r["shape"] for r in sorted(done, key=lambda r: r["rep"]) if r["qid"] == qid]
        shapes[qid] = {"shapes": ss, "same": len(set(ss)) == 1 if ss else None, "expect": EXPECT.get(qid)}
    every = [e for r in done for e in r.get("block_errors") or [] if not e.startswith(NOT_BLOCK)]
    errs = [e for e in every if not any(m in e for m in PARTIAL)]   # 塊ごと捨てたもの
    pair_errs = [e for e in every if any(m in e for m in PARTIAL)]  # 塊は残して対・部品・やりとりの一部を捨てたもの
    by_cat = {}
    for r in done:
        c = by_cat.setdefault(r["cat"], {"runs": 0, "analogy": 0, "loose": 0, "lead": 0, "wall": []})
        c["runs"] += 1
        c["analogy"] += r["analogy_raw"] > 0
        c["loose"] += len((r.get("count") or {}).get("loose") or [])
        c["lead"] += len((r.get("count") or {}).get("lead") or [])
        c["wall"].append(r["wall_s"])
    for c in by_cat.values():
        c["wall_median"] = statistics.median(c.pop("wall"))
    return {
        "runs": len(runs), "done": len(done), "errors": [r.get("error") for r in runs if r["status"] != "done"],
        "a_raw": ratio("a_raw"), "a_shown": ratio("a_shown"),
        "loose_total": sum(len(r["count"]["loose"]) for r in counted),
        "lead_total": sum(len(r["count"]["lead"]) for r in counted), "counted": len(counted),
        "shapes": shapes,
        "confusing_same": sum(1 for q in EXPECT if shapes[q]["same"] and shapes[q]["shapes"][0] == EXPECT[q]),
        "parts_same": sum(1 for q in EXPECT_PARTS if shapes[q]["same"] and shapes[q]["shapes"][0] == EXPECT_PARTS[q]),
        "wall_median": statistics.median([r["wall_s"] for r in done]) if done else None,
        "tutor_median": statistics.median([r["tutor_s"] for r in done]) if done else None,
        "wall_median_12": statistics.median(w) if (w := [r["wall_s"] for r in done if r["qid"] in BASE12]) else None,
        "tutor_median_12": statistics.median(w) if (w := [r["tutor_s"] for r in done if r["qid"] in BASE12]) else None,
        "checks": sum(r.get("checks", 0) for r in done),
        "checks_with_hints": sum(r.get("checks_with_hints", 0) for r in done),
        "hints_raw": sum(r.get("hints_raw", 0) for r in done), "hints_kept": sum(r.get("hints_kept", 0) for r in done),
        "hints_dropped": sum(r.get("hints_dropped", 0) for r in done),
        "blocks_dropped": len(errs), "block_errors": errs, "pair_drops": pair_errs,
        "unchecked": sum(1 for r in done for c in r.get("checked") or [] if c is False),
        "by_cat": by_cat,
    }


def write_json(out: Path, runs: list[dict], meta: dict) -> None:
    out.write_text(json.dumps({"meta": meta, "summary": summarize(runs), "runs": runs}, ensure_ascii=False, indent=1),
                   encoding="utf-8")


async def main_run(n: int, out: Path, only: list[str] | None, use_corpus: bool) -> None:
    db.init()
    info = await asyncio.to_thread(corpus.refresh) if use_corpus else {"pages": 0, "skipped": True}
    out_jsonl = out.with_suffix(".jsonl")
    have = {(r["qid"], r["rep"]) for r in load_jsonl(out_jsonl) if r["status"] == "done"}
    sem = asyncio.Semaphore(3)
    jobs = [run_one(qid, cat, q, rep, sem, out_jsonl) for rep in range(1, n + 1) for qid, cat, q in QUESTIONS
            if (not only or qid in only) and (qid, rep) not in have]
    print(f"記録の置き場 {config.DATA_DIR}・先生役 {config.TUTOR_MODEL}・棚 {info.get('pages')}・{len(jobs)}本", flush=True)
    try:
        await asyncio.gather(*jobs, return_exceptions=True)
    finally:
        await brain.TUTORS.close_all()
        await judge.POOL.close()
        for name in ("PAIR_POOL",):
            p = getattr(judge, name, None)
            if p:
                await p.close()
    meta = {"model": config.TUTOR_MODEL, "counter": f"{config.FIXER_MODEL}/{config.FIXER_EFFORT}", "n": n,
            "corpus_pages": info.get("pages"), "at": time.strftime("%Y-%m-%d %H:%M")}
    write_json(out, load_jsonl(out_jsonl), meta)
    print(json.dumps(summarize(load_jsonl(out_jsonl)), ensure_ascii=False, indent=1))


async def main_rejudge(path: Path) -> None:
    d = json.loads(path.read_text(encoding="utf-8"))
    sem = asyncio.Semaphore(3)

    async def one(r):
        async with sem:
            if r["status"] == "done":
                r["count"] = await count(r["answer_md"] or "")
    await asyncio.gather(*(one(r) for r in d["runs"]))
    d["meta"]["rejudged"] = time.strftime("%Y-%m-%d %H:%M")
    write_json(path, d["runs"], d["meta"])


def report(paths: list[Path]) -> str:
    ds = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    names = [p.stem for p in paths]
    S = [summarize(d["runs"]) for d in ds]   # 保存した1本ずつから数え直す（数え方を直しても両方そろう）
    def pct(x):
        return f"{x['hit']}/{x['pairs']}（{x['rate'] * 100:.0f}%）" if x["pairs"] else "対なし"
    lines = ["| 数えたもの | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    rows = [
        ("流した数（届いた数）", [f"{s['runs']}（{s['done']}）" for s in S]),
        ("(a) 対の実際の名前が本文にある・書いたまま", [pct(s["a_raw"]) for s in S]),
        ("(a) 同・画面に出る対", [pct(s["a_shown"]) for s in S]),
        ("(b) 塊に結ばれていない文のたとえ（合計）", [f"{s['loose_total']}（{s['counted']}答え）" for s in S]),
        ("(b) 最初の段落の比喩の語（合計）", [f"{s['lead_total']}（{s['counted']}答え）" for s in S]),
        ("(c) 迷いやすい4問で3回とも狙いの形", [f"{s['confusing_same']}/4" for s in S]),
        ("(d) 答えまでの秒の中央値（壁時計）", [f"{s['wall_median']:.1f}" if s["wall_median"] else "—" for s in S]),
        ("(d) 先生役だけの秒の中央値", [f"{s['tutor_median']:.1f}" if s["tutor_median"] else "—" for s in S]),
        ("(d) 作業A と同じ12問の秒の中央値（壁時計）", [f"{s['wall_median_12']:.1f}" if s.get("wall_median_12") else "—" for s in S]),
        ("(d) 同・先生役だけ", [f"{s['tutor_median_12']:.1f}" if s.get("tutor_median_12") else "—" for s in S]),
        ("(f) しくみの絵を狙う2問で3回ともしくみの絵", [f"{s['parts_same']}/2" if any(s["shapes"][q]["shapes"] for q in EXPECT_PARTS) else "—" for s in S]),
        ("(f) ヒントの付いた確かめの問い", [f"{s['checks_with_hints']}/{s['checks']}" for s in S]),
        ("(f) ヒントの段（書いたまま→残した・答えの字で外した）", [f"{s['hints_raw']}→{s['hints_kept']}・{s['hints_dropped']}" for s in S]),
        ("(e) 捨てた塊", [str(s["blocks_dropped"]) for s in S]),
        ("(e) 塊は残して対を捨てた答え", [str(len(s["pair_drops"])) for s in S]),
        ("判定役が取れず「確かめていない対応」の塊", [str(s["unchecked"]) for s in S]),
    ]
    lines += [f"| {k} | " + " | ".join(v) + " |" for k, v in rows]
    lines += ["", "| 問い | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for qid, cat, _ in QUESTIONS:
        lines.append(f"| {qid}（{cat}） | " + " | ".join(
            (",".join(s["shapes"][qid]["shapes"]) + ("" if s["shapes"][qid]["same"] else "（割れた）")) if s["shapes"][qid]["shapes"] else "—"
            for s in S) + " |")
    lines += ["", "| 種類 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for cat in dict.fromkeys(c for _, c, _ in QUESTIONS):
        def cell(s):
            c = s["by_cat"].get(cat)
            return f"たとえ{c['analogy']}/{c['runs']}・loose {c['loose']}・lead {c['lead']}・{c['wall_median']:.0f}秒" if c else "—"
        lines.append(f"| {cat} | " + " | ".join(cell(s) for s in S) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--no-corpus", action="store_true")
    ap.add_argument("--rejudge", type=Path)
    ap.add_argument("--report", type=Path, nargs="+")
    a = ap.parse_args()
    if a.report:
        print(report(a.report))
    elif a.rejudge:
        asyncio.run(main_rejudge(a.rejudge))
    elif a.out:
        asyncio.run(main_run(a.n, a.out, a.only, not a.no_corpus))
    else:
        sys.exit("--out か --rejudge か --report を付けてください")
