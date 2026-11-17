"""往復の流れの決まり（v0.6）。読む前の予想をいつ誘うかを、機械の決まった規則で決める。

v0.3〜v0.5 は、届いた答えを畳んで「読む前に予想を一言」と出していた。本人の記録（DESIGN 17.1）では、声で話題を回して
戻ってきたときの予想には使われていた一方で、文字で打った予想は新しい質問として先生役に送られ、頼みの形の発言の答えも
畳まれ、畳まれたまま開かれない答えがあった。v0.6 の既定は次の2つを合わせた形にする。
  同じ話題で答えを待っているあいだ … 答えは畳まず、入力欄の上の帯で誘うだけ（DESIGN 7.4 の候補・研究 d の 3-7・g1 の 2-1）
  別の話題にいるあいだに届いた答え … 戻ったときに畳んで誘う（v0.3 の形。声でも文字でも予想になる）
誘うのは問いの形の発言だけで、誘いに乗らなかったら次の1回は誘わない。先生役の指示（tutor.SYSTEM）は変えていない。
"""
import json
import re

from . import db

PREDICT_MODES = ("both", "wait", "off")
TEXT_SIZES = ("s", "m", "l")


def predict_mode(con=None) -> str:
    """読む前の予想の出し方。both＝待つあいだは帯で誘い、別の話題にいるあいだに届いた答えは戻ったときに畳んで誘う（既定）、
    wait＝待つあいだだけ誘う（答えは畳まない）、off＝出さない。v0.5 までの記録の値は "1"（出す）と "0"（出さない）。
    con を渡すと、その接続で読む（書き込みの途中の接続の中から呼ぶとき）。"""
    if con is not None:
        r = db.row(con, "SELECT v FROM pref WHERE k='predict'")
        v = r["v"] if r else "both"
    else:
        v = db.get_pref("predict", "both")
    v = {"1": "both", "fold": "both", "0": "off"}.get(v, v)
    return v if v in PREDICT_MODES else "both"


def text_size() -> str:
    v = db.get_pref("text_size", "m")
    return v if v in TEXT_SIZES else "m"


# 問いの形（疑問の語か、文の終わりの「か」「かな」「っけ」、？）。予想の誘いは、問いの形の発言にだけ出す。
# 「〜を整理したい」「〜を教えて」「まとめて」のような頼みの形だけの発言は、答えの形を予想しにくいので誘わない
_WH = re.compile(
    r"なぜ(?!か|なら)|なんで(?!も|か)|どう(?!ぞ|も|せ|にか|しても|やら|でも)"
    r"|何(?!か|度も|回も|より|とか|らか|だか|となく|も)|(?<!ん)なに(?!か|も|より)"
    r"|(?<![なほ])どの|どれ(?!も|か|でも)|どっち(?!も|か|でも)|どちら(?!も|か|でも)"
    r"|いつ(?!も|か|でも|まで)|(?<!ろ)どこ(?!ろ|か|も|でも)|誰(?!か|も|でも)|だれ(?!か|も|でも)"
    r"|いくつ(?!か|も)|いくら(?!か|も|でも)|とは(?=[\s　]*(?:何|なに|どう|どんな|[？?]|$))|の違い")
_END = re.compile(r"(?:ですか|ますか|のか|るか|たか|いか|ないか|だろうか|でしょうか|かな|っけ|なの|何か)$")


def looks_like_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if "？" in t or "?" in t or _WH.search(t):
        return True
    return any(_END.search(s.strip(" 　、。!！")) for s in re.split(r"[。\n]", t) if s.strip())


def predict_offer(con, text: str, kind: str, via: str, has_ref: bool) -> bool:
    """この往復で、予想を誘うか。誘うのは、声か文字の問い（question）で、問いの形をしていて、見せ直しでないとき。
    直前の誘いに乗らなかった（予想せずに答えを読んだ）あとは、次の1回は誘わない（話題を問わない。その印はここで消す）。"""
    if predict_mode(con) == "off" or kind != "question" or via not in ("voice", "text") or has_ref:
        return False
    if not looks_like_question(text):
        return False
    r = db.row(con, "SELECT v FROM pref WHERE k='predict_skip'")
    if r and r["v"] == "1":
        con.execute("UPDATE pref SET v='0' WHERE k='predict_skip'")
        return False
    return True


def note_reveal(con, turn_id: int, st: dict) -> None:
    """答えを開いたとき。誘った往復を予想なしで開いたら、「誘いに乗らなかった」の印を付ける（次の1回は誘わない）。
    声の予想は、文字になる前に答えが開くので、その往復を指す予想の録音があれば、乗ったとみなす。"""
    if st.get("offer") != "predict" or st.get("predict"):
        return
    if db.row(con, "SELECT 1 AS x FROM turn WHERE ref_turn=? AND via='voice' AND audio IS NOT NULL AND status='superseded' LIMIT 1", (turn_id,)):
        return
    con.execute("INSERT INTO pref(k, v) VALUES('predict_skip', '1') ON CONFLICT(k) DO UPDATE SET v='1'")


def note_predict(con) -> None:
    """予想した。次の問いでも誘ってよい。"""
    con.execute("INSERT INTO pref(k, v) VALUES('predict_skip', '0') ON CONFLICT(k) DO UPDATE SET v='0'")


def due_checks(con, after_sec: float, exclude: int | None = None) -> dict:
    """いま出せる確かめの問い（型のある開いた問いで、元の答えを開いてから after_sec 以上たったもの）の数と、
    いちばん古い問いのある話題。片づけた話題の問いも数える（話題の中でしか出ない作りだと、片づけた話題の問いに出る道が無い）。
    直近に済んだ3問がすべて飛ばしの話題は数えない（話題の中の決まりと同じ）。exclude の話題は数えない。"""
    rows = db.rows(con, """SELECT c.id, c.session_id, c.status, s.archived, t.stage_ms FROM checkq c
                           JOIN session s ON s.id=c.session_id JOIN turn t ON t.id=c.turn_id
                           WHERE c.qtype IS NOT NULL ORDER BY c.id""")
    by: dict[int, list[dict]] = {}
    for r in rows:
        by.setdefault(r["session_id"], []).append(r)
    now, due = db.now(), []
    for sid, cs in by.items():
        done = [c for c in cs if c["status"] != "open"]
        if sid == exclude or (len(done) >= 3 and all(c["status"] == "skipped" for c in done[-3:])):
            continue
        for c in cs:
            r = json.loads(c["stage_ms"] or "{}").get("revealed_at")
            if c["status"] == "open" and r and now - r >= after_sec:
                due.append(c)
    first = min(due, key=lambda c: c["id"]) if due else None
    return {"n": len(due), "next": {"session_id": first["session_id"], "archived": bool(first["archived"])} if first else None}


def archived_rows(con, limit: int = 200) -> list[dict]:
    """片づけた話題（新しい順）。往復の数と、まだ出していない確かめの問いの数を添える。"""
    rows = db.rows(con, "SELECT id, title, updated_at FROM session WHERE archived=1 ORDER BY updated_at DESC LIMIT ?", (limit,))
    for s in rows:
        s["turns"] = db.row(con, "SELECT COUNT(*) AS n FROM turn WHERE session_id=? AND status='done'", (s["id"],))["n"]
        s["open_checks"] = db.row(con, "SELECT COUNT(*) AS n FROM checkq WHERE session_id=? AND status='open' AND qtype IS NOT NULL",
                                  (s["id"],))["n"]
    return rows
