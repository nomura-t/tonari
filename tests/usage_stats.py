"""記録の数を読む小さな道具（DESIGN 15.5 の C3）。pytest の対象外。数だけを出し、話題の名前・発言・問いの文は出さない。

  uv run python tests/usage_stats.py                 # 記録の置き場（TONARI_DATA_DIR か OS の既定）の tonari.db を読む
  uv run python tests/usage_stats.py --db <path>     # 別の記録（試すときは一時の記録で）
  uv run python tests/usage_stats.py --json          # 数を JSON で

記録は SQLite の mode=ro（読み取り専用）で開く。server.db は通さない（connect が置き場を作り、WAL に切り替えるため）。
まだ新しい版で起動していない記録（hints の列や analogy の表が無い）でも、無いものは「列なし」として数える。

数えるもの。使った日数（往復を送った日の数・端末の時刻で）、往復の数（予想の往復と聞き直しで畳んだ往復を除く）、
確かめの問いに答えた率（答えた・分からない・分かる・あやしい を答えたに数える。飛ばしと手つかずは別に出す）、
ヒントの段数の合計、「実際には？」を押した回数（stage_ms.ground）とそのうち直前の答えにたとえの塊があった数、
たとえの塊が出た往復の数（stage_ms.shapes に analogy がある往復）、しくみの絵が出た往復の数。
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def default_db() -> Path:
    """server/config.py の _default_data_dir と同じ決め方（読み込むと置き場を触るので写して持つ）。"""
    if os.environ.get("TONARI_DATA_DIR"):
        return Path(os.environ["TONARI_DATA_DIR"]) / "tonari.db"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "tonari"
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support/tonari"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "tonari"
    return base / "tonari.db"


def open_ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        sys.exit(f"記録がありません: {path}")
    uri = path.resolve().as_uri() + "?mode=ro"   # Windows の C:\ も file:///C:/… になる（空白は %20）
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def cols(con, table: str) -> set[str]:
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


def stats(con) -> dict:
    ft = ", final_text" if "final_text" in cols(con, "turn") else ""
    turns = [dict(r) for r in con.execute(
        f"SELECT id, session_id, seq, via, status, stage_ms, created_at{ft} FROM turn WHERE status!='superseded' ORDER BY session_id, seq")]
    said = {t["id"]: t.pop("final_text", None) or "" for t in turns}   # 数えるためだけに読む（中身は出さない）
    st = {t["id"]: json.loads(t["stage_ms"] or "{}") for t in turns}
    days = sorted({time.strftime("%Y-%m-%d", time.localtime(t["created_at"])) for t in turns})
    shapes = {tid: {x.get("type") for x in (s.get("shapes") or []) if isinstance(x, dict)} for tid, s in st.items()}
    # 「実際には？」と、その直前の届いた答え（同じ話題）にたとえの塊があったか
    ground = after_analogy = 0
    prev_done: dict[int, int] = {}
    for t in turns:
        if st[t["id"]].get("ground"):
            ground += 1
            p = prev_done.get(t["session_id"])
            after_analogy += bool(p and "analogy" in shapes.get(p, set()))
        if t["status"] == "done":
            prev_done[t["session_id"]] = t["id"]
    cq = cols(con, "checkq")
    checks = [dict(r) for r in con.execute("SELECT status" + (", hints, hints_used" if "hints_used" in cq else "") + " FROM checkq")]
    answered = sum(c["status"] in ("answered", "unknown", "known", "shaky") for c in checks)
    out = {
        "days_used": len(days), "first_day": days[0] if days else None, "last_day": days[-1] if days else None,
        "turns": len(turns), "turns_done": sum(t["status"] == "done" for t in turns),
        "turns_by_via": {v: sum(t["via"] == v for t in turns) for v in ("voice", "text", "click")},
        "checks": len(checks), "checks_answered": answered,
        "checks_skipped": sum(c["status"] == "skipped" for c in checks),
        "checks_open": sum(c["status"] == "open" for c in checks),
        "answer_rate": round(answered / len(checks), 3) if checks else None,
        "hints_used_total": sum(int(c.get("hints_used") or 0) for c in checks) if "hints_used" in cq else "列なし",
        "checks_with_hints": sum(bool(json.loads(c.get("hints") or "[]")) for c in checks) if "hints" in cq else "列なし",
        "ground_clicks": ground, "ground_after_analogy": after_analogy,
        "turns_with_analogy": sum("analogy" in s for s in shapes.values()),
        "turns_with_parts": sum("parts" in s for s in shapes.values()),
        # v0.5 の物差し（DESIGN 16.8）: 続きを・詳しくを頼んだ回数、考えの塊、Web で調べた往復と入口
        "more_clicks": sum(x.startswith("続きを") for x in said.values()),
        "deeper_asks": sum(("詳しく" in x or "くわしく" in x) and not x.startswith("続きを") for x in said.values()),
        "turns_with_think": sum("think" in s for s in shapes.values()),
        "lookup_offered": sum(bool(s.get("lookup")) for s in st.values()),
        "research_turns": sum(t["via"] == "research" for t in turns),
        "budget_median": (lambda b: sorted(b)[len(b) // 2] if b else None)([s["budget"]["chars"] for s in st.values() if isinstance(s.get("budget"), dict)]),
    }
    # v0.6 の物差し（DESIGN 17章）: 予想の誘いと予想した数（声・文字）、届いたのに開いていない答え、確かめへの答えの往復、
    # 片づけた話題と戻した回数、予想を質問として送り直した回数
    done = [t for t in turns if t["status"] == "done"]
    tbl = tables(con)   # 古い記録や試しの記録には、表が無いことがある
    logs = {r["kind"]: r["n"] for r in con.execute("SELECT kind, COUNT(*) AS n FROM log GROUP BY kind")} if "log" in tbl else {}
    scols = cols(con, "session") if "session" in tbl else set()
    out.update({
        "predict_offered": sum(st[t["id"]].get("offer") == "predict" for t in turns),
        "predict_after_offer": sum(st[t["id"]].get("offer") == "predict" and bool(st[t["id"]].get("predict")) for t in turns),
        "predicted": sum(bool(st[t["id"]].get("predict")) for t in turns),
        "predicted_by_via": {v: sum(bool(st[t["id"]].get("predict")) and (st[t["id"]].get("predict_via") or "voice") == v for t in turns)
                             for v in ("voice", "text")},
        "unopened_answers": sum("revealed_at" not in st[t["id"]] for t in done),
        "check_answer_turns": {v: sum(st[t["id"]].get("kind") == "answer" and bool(st[t["id"]].get("check_id")) and t["via"] == v for t in turns)
                               for v in ("voice", "text")},
        "topics": con.execute("SELECT COUNT(*) FROM session").fetchone()[0] if "session" in tbl else len({t["session_id"] for t in turns}),
        "topics_archived": con.execute("SELECT COUNT(*) FROM session WHERE archived=1").fetchone()[0] if "archived" in scols else 0,
        "topics_restored": logs.get("restore", 0),
        "unpredict": logs.get("unpredict", 0),
        "alt_shown": sum(bool(st[t["id"]].get("alt")) for t in turns),
        "alt_picked": sum(bool(st[t["id"]].get("alt_pick")) for t in turns),
    })
    # 予想と答えの照らし合わせ（DESIGN 17.12）と、全体の地図（17.13）。数だけ
    fbs = [st[t["id"]].get("predict_fb") or {} for t in turns if st[t["id"]].get("predict")]
    acts = ({r["state"]: r["n"] for r in con.execute("SELECT state, COUNT(*) AS n FROM log WHERE kind='atlas' GROUP BY state")}
            if "log" in tbl else {})
    out.update({
        "predict_fb": sum(f.get("state") == "done" for f in fbs),
        "predict_fb_core": {k: sum(f.get("state") == "done" and f.get("core") == k for f in fbs) for k in ("in", "out", "unknown", "none")},
        "predict_fb_asks": sum(bool(st[t["id"]].get("pfb_ask")) for t in turns),
        "predict_fb_failed": sum(f.get("state") == "fail" for f in fbs),
        "atlas_opens": acts.get("open", 0),
        "atlas_then": {k: acts.get(k, 0) for k in ("concept", "topic", "open_topic", "ego", "ask", "find")},
    })
    return out


def tables(con) -> set[str]:
    return {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


LABELS = [("days_used", "使った日数"), ("first_day", "最初の日"), ("last_day", "最後の日"), ("turns", "往復"),
          ("turns_done", "うち答えが届いた往復"), ("turns_by_via", "経路ごとの往復（声・文字・図から）"),
          ("checks", "確かめの問い"), ("checks_answered", "答えた問い"), ("checks_skipped", "飛ばした問い"),
          ("checks_open", "手つかずの問い"), ("answer_rate", "答えた率"), ("hints_used_total", "出したヒントの段の合計"),
          ("checks_with_hints", "ヒントのある問い"), ("ground_clicks", "「実際には？」の回数"),
          ("ground_after_analogy", "うち直前の答えにたとえの塊があった回数"), ("turns_with_analogy", "たとえの塊が出た往復"),
          ("turns_with_parts", "しくみの絵が出た往復"), ("more_clicks", "「続きを」の回数"), ("deeper_asks", "詳しくを頼んだ回数"),
          ("turns_with_think", "考えの塊が出た往復"), ("lookup_offered", "Web で調べる入口が出た往復"),
          ("research_turns", "Web で調べた往復（上の往復の数に含む）"), ("budget_median", "字数の目安の中央値"),
          ("predict_offered", "待つあいだに予想を誘った往復"), ("predict_after_offer", "うち予想した往復"),
          ("predicted", "予想した往復（畳む形のころの分を含む）"), ("predicted_by_via", "予想の経路（声・文字）"),
          ("unopened_answers", "届いたのに開いていない答え"), ("check_answer_turns", "確かめの問いへの答えの往復（声・文字）"),
          ("topics", "話題"), ("topics_archived", "うち片づけた話題"), ("topics_restored", "片づけた話題を戻した回数"),
          ("unpredict", "予想を質問として送り直した回数"),
          ("alt_shown", "「別の読みでしたか」の札が出た往復"), ("alt_picked", "その札を押して聞き直した回数"),
          ("predict_fb", "予想に照らし合わせを返した往復"), ("predict_fb_core", "その内訳（答えの核心が予想に入っていた・いなかった・どちらとも出さなかった・照らせない）"),
          ("predict_fb_asks", "照らし合わせの下の「聞き返す」を押した回数"),
          ("predict_fb_failed", "照らし合わせを取れなかった往復"),
          ("atlas_opens", "全体の地図を開いた回数"),
          ("atlas_then", "地図の中でしたこと（言葉を選ぶ・話題を選ぶ・話題を開く・位置の図へ・説明を頼む・探す）")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    path = a.db or default_db()
    con = open_ro(path)
    try:
        s = stats(con)
    finally:
        con.close()
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return
    for k, name in LABELS:
        v = s[k]
        if k == "turns_by_via":
            v = "・".join(str(v[x]) for x in ("voice", "text", "click"))
        elif k in ("predicted_by_via", "check_answer_turns"):
            v = "・".join(str(v[x]) for x in ("voice", "text"))
        elif k == "predict_fb_core":
            v = "・".join(str(v[x]) for x in ("in", "out", "unknown", "none"))
        elif k == "atlas_then":
            v = "・".join(str(v[x]) for x in ("concept", "topic", "open_topic", "ego", "ask", "find"))
        elif k == "answer_rate" and v is not None:
            v = f"{v * 100:.0f}%"
        print(f"{name}: {v}")


if __name__ == "__main__":
    main()
