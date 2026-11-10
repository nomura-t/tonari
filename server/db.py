"""記録（SQLite）。表の意味は DESIGN の「データの形」の ER 図と同じ。

話題（session）ごとの往復（turn）に、声の生の文字起こし（Apple・Scribe）・整形役の直し・本人が確かめた文を
別々に残す。概念（concept）と関係（relation）は話題をまたいで1つの地図に溜め、理解度は概念ごと（mastery）と
関係ごと（rel_mastery）に持つ。申告と確かめの記録は log に足すだけで、今の状態はそこから引き直せる。
"""
import json
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS session (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '新しい話題',
  model TEXT NOT NULL,
  claude_sid TEXT,                    -- 先生役の会話の id（--resume で続きから。指示が変わったら新しい会話・prompt_sig）
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  read_at REAL NOT NULL DEFAULT 0,    -- 本人が最後にこの話題を開いていた時刻（未読の判定）
  archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS turn (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES session(id),
  seq INTEGER NOT NULL,
  via TEXT NOT NULL,                  -- voice / text / click（地図の札から「説明して」）
  audio TEXT,                         -- 録音のファイル名（AUDIO_DIR の中）
  audio_sec REAL,
  apple_text TEXT, apple_json TEXT,   -- Apple の生の結果（low＝確信度の低い字・alts＝別候補）
  scribe_text TEXT, scribe_ms INTEGER,
  fixed_text TEXT, edits_json TEXT, unsure_json TEXT,   -- 整形役の直しと、決めきれなかった箇所
  final_text TEXT,                    -- 先生役に送った文（本人が直したらそれ）
  title TEXT,                         -- 往復の見出し（話題の札と「前回」に出す）
  answer_md TEXT,                     -- 先生役の答え（文と札の塊をそのまま）
  status TEXT NOT NULL,               -- recorded / transcribing / fixing / thinking / done / error / superseded
  error TEXT,
  stage_ms TEXT,                      -- 段ごとの時間（JSON）
  created_at REAL NOT NULL,
  done_at REAL
);
CREATE INDEX IF NOT EXISTS turn_session ON turn(session_id, seq);
CREATE TABLE IF NOT EXISTS concept (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL,
  fold TEXT NOT NULL UNIQUE,          -- 突き合わせ用（NFKC・空白なし・小文字）
  gist TEXT,                          -- 一文の説明（最後に先生役が出したもの）
  gist_src TEXT,                      -- その出どころ（〔id｜見出し〕 / 一般 / 推測）
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS session_concept (
  session_id INTEGER NOT NULL, concept_id INTEGER NOT NULL, first_turn INTEGER, last_turn INTEGER,
  PRIMARY KEY (session_id, concept_id)
);
CREATE TABLE IF NOT EXISTS relation (
  id INTEGER PRIMARY KEY,
  src INTEGER NOT NULL REFERENCES concept(id),   -- 下位・例・対の片方など（向きは rel ごとに DESIGN の表）
  dst INTEGER NOT NULL REFERENCES concept(id),
  rel TEXT NOT NULL,                  -- broader（src の上位が dst）/ opposite / related / example / nonexample
  detail TEXT,                        -- related の種類（前提・原因・結果・部分・道具 など）や対の軸
  why TEXT,
  src_kind TEXT NOT NULL,             -- shelf（棚に根拠）/ general（一般の知識）/ inferred（推測）
  src_ref TEXT,
  turn_id INTEGER,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  UNIQUE (src, dst, rel)
);
CREATE TABLE IF NOT EXISTS mastery (
  concept_id INTEGER PRIMARY KEY, state TEXT NOT NULL, by TEXT NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rel_mastery (
  relation_id INTEGER PRIMARY KEY, state TEXT NOT NULL, by TEXT NOT NULL, evidence TEXT, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS log (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,                 -- mastery / rel_mastery / check / mishear / revert
  target INTEGER, state TEXT, by TEXT, evidence TEXT, turn_id INTEGER, at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS checkq (
  id INTEGER PRIMARY KEY,
  turn_id INTEGER NOT NULL, session_id INTEGER NOT NULL,
  q TEXT NOT NULL, a TEXT, concept TEXT, target TEXT, rel TEXT,
  status TEXT NOT NULL DEFAULT 'open',   -- open / known / shaky / unknown / answered / skipped（戻ったときの問いを飛ばした）
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mishear (
  heard TEXT NOT NULL, meant TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 1, updated_at REAL NOT NULL,
  PRIMARY KEY (heard, meant)
);
CREATE TABLE IF NOT EXISTS stt_usage (
  id INTEGER PRIMARY KEY, engine TEXT NOT NULL, sec REAL NOT NULL, at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pref (k TEXT PRIMARY KEY, v TEXT NOT NULL);
-- v0.4（A8）: 話題のたとえ。画面に出したたとえの塊を残し、次の答えに最新のものを渡して元の世界をそろえる。
-- 表ごと足すので、すでにある記録の DB にも init のたびの CREATE TABLE IF NOT EXISTS で入る（列を足す MIGRATIONS とは別）
CREATE TABLE IF NOT EXISTS analogy (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL,
  turn_id INTEGER NOT NULL,
  source TEXT NOT NULL,               -- 元の世界
  target TEXT,                        -- 学ぶもの
  by TEXT NOT NULL,                   -- tutor（先生役のたとえ）/ user（本人が持ち込んだたとえ）
  json TEXT NOT NULL,                 -- relation・pairs・unmapped・breaks
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS analogy_session ON analogy(session_id, id);
"""


def fold(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or "")).lower()


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    con = sqlite3.connect(config.DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


MIGRATIONS = [
    # (表, 列, 足す SQL)。すでにある記録の DB に後から列を足す（v0.2 の表現の語彙）
    ("session", "detail", "ALTER TABLE session ADD COLUMN detail TEXT NOT NULL DEFAULT 'auto'"),   # auto / short / long
    ("turn", "ref_turn", "ALTER TABLE turn ADD COLUMN ref_turn INTEGER"),                         # 見せ直しの元の往復
    ("turn", "haas_text", "ALTER TABLE turn ADD COLUMN haas_text TEXT"),                          # 端末内の2本目（speech.cpp の Haas）
    ("turn", "haas_ms", "ALTER TABLE turn ADD COLUMN haas_ms INTEGER"),
    ("checkq", "qtype", "ALTER TABLE checkq ADD COLUMN qtype TEXT"),                              # 確かめの問いの型（もしも・当てはめ・共通点・見分け）
    # v0.4 作業B（C1）: 確かめの問いのヒント（JSON の文字の配列・2段まで）と、戻ったときの帯で本人が出した段の数
    ("checkq", "hints", "ALTER TABLE checkq ADD COLUMN hints TEXT"),
    ("checkq", "hints_used", "ALTER TABLE checkq ADD COLUMN hints_used INTEGER NOT NULL DEFAULT 0"),
    # 先生役の会話を始めたときの指示の印（tutor.prompt_sig）。claude -p の --resume は会話を始めたときの指示を使い続け、
    # --system-prompt-file を渡し直しても変わらない（2026-11-10・claude 2.1.322 で確かめた）。印が今の指示と違えば
    # --resume せずに新しい会話を始め、これまでの往復の要約を添える（DESIGN 15.11）
    ("session", "prompt_sig", "ALTER TABLE session ADD COLUMN prompt_sig TEXT"),
]


def init() -> None:
    with tx() as con:
        con.executescript(SCHEMA)
        for table, col, sql in MIGRATIONS:
            cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
            if col not in cols:
                con.execute(sql)
        # v0.3: 答えを「開いた」時刻（revealed_at）で、読む前の予想と戻ったときの確かめを決める。
        # それより前の答えは開いたものとして扱う（古い答えが全部畳まれないように）。1回だけ
        if not con.execute("SELECT 1 FROM pref WHERE k='revealed_backfill'").fetchone():
            for r in con.execute("SELECT id, stage_ms, done_at FROM turn WHERE status='done'").fetchall():
                st = json.loads(r["stage_ms"] or "{}")
                if "revealed_at" not in st:
                    st["revealed_at"] = r["done_at"] or 0
                    con.execute("UPDATE turn SET stage_ms=? WHERE id=?", (jdump(st), r["id"]))
            con.execute("INSERT INTO pref(k, v) VALUES('revealed_backfill', '1')")
        # 前回、途中で閉じた往復は「止まった」にする（再送は画面のボタンから）
        con.execute("UPDATE turn SET status='error', error='アプリを閉じたので止まりました' "
                    "WHERE status IN ('recorded','transcribing','fixing','thinking')")


def rows(con, sql: str, args=()) -> list[dict]:
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def row(con, sql: str, args=()) -> dict | None:
    r = con.execute(sql, args).fetchone()
    return dict(r) if r else None


def now() -> float:
    return time.time()


def get_pref(key: str, default: str) -> str:
    with tx() as con:
        r = row(con, "SELECT v FROM pref WHERE k=?", (key,))
    return r["v"] if r else default


def set_pref(key: str, value: str) -> None:
    with tx() as con:
        con.execute("INSERT INTO pref(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, value))


def jdump(x) -> str:
    return json.dumps(x, ensure_ascii=False)
