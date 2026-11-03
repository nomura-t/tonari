"""地図の読み出し。概念1つを中心に、上位・下位・対・関係・例・非例を集める（画面の図はこの並びで描く）。

本人の仮説を数える形にしたのが coverage: 概念Aの周りの関係のうち、本人が「分かる」と確かめた（か申告した）関係の割合。
"""
from . import db

DIRS = ("broader", "narrower", "opposite", "related", "examples", "nonexamples")


def _node(con, cid: int) -> dict:
    c = db.row(con, """SELECT c.id, c.label, c.gist, c.gist_src, m.state, m.by FROM concept c
                       LEFT JOIN mastery m ON m.concept_id=c.id WHERE c.id=?""", (cid,))
    return c or {}


def ego(cid: int) -> dict:
    with db.tx() as con:
        center = _node(con, cid)
        if not center:
            return {}
        rels = db.rows(con, """SELECT r.*, rm.state AS rstate, rm.by AS rby, rm.evidence FROM relation r
                               LEFT JOIN rel_mastery rm ON rm.relation_id=r.id WHERE r.src=? OR r.dst=?""", (cid, cid))
        out = {d: [] for d in DIRS}
        for r in rels:
            other = r["dst"] if r["src"] == cid else r["src"]
            if r["rel"] == "broader":
                d = "broader" if r["src"] == cid else "narrower"
            elif r["rel"] == "opposite":
                d = "opposite"
            elif r["rel"] == "related":
                d = "related"
            elif r["rel"] == "example" and r["dst"] == cid:
                d = "examples"
            elif r["rel"] == "nonexample" and r["dst"] == cid:
                d = "nonexamples"
            else:
                continue
            n = _node(con, other)
            n.update(rid=r["id"], detail=r["detail"], why=r["why"], src_kind=r["src_kind"], src_ref=r["src_ref"],
                     rstate=r["rstate"], rby=r["rby"], evidence=r["evidence"])
            out[d].append(n)
        sessions = db.rows(con, """SELECT s.id, s.title FROM session_concept sc JOIN session s ON s.id=sc.session_id
                                   WHERE sc.concept_id=? AND s.archived=0 ORDER BY s.updated_at DESC""", (cid,))
    core = [n for d in ("broader", "narrower", "opposite", "related") for n in out[d]]
    known = sum(1 for n in core if n.get("rstate") == "known")
    center["coverage"] = {"known": known, "total": len(core)}
    return {"center": center, **out, "sessions": sessions}


def concepts(session_id: int | None = None) -> list[dict]:
    with db.tx() as con:
        if session_id:
            rows = db.rows(con, """SELECT c.id, c.label, c.gist, m.state, sc.last_turn FROM session_concept sc
                                   JOIN concept c ON c.id=sc.concept_id LEFT JOIN mastery m ON m.concept_id=c.id
                                   WHERE sc.session_id=? ORDER BY sc.last_turn DESC, c.id DESC""", (session_id,))
        else:
            rows = db.rows(con, """SELECT c.id, c.label, c.gist, m.state FROM concept c
                                   LEFT JOIN mastery m ON m.concept_id=c.id ORDER BY c.updated_at DESC LIMIT 400""")
        cov = {r["cid"]: (r["known"], r["total"]) for r in db.rows(con, """
            SELECT cid, SUM(CASE WHEN rstate='known' THEN 1 ELSE 0 END) AS known, COUNT(*) AS total FROM (
              SELECT r.src AS cid, rm.state AS rstate FROM relation r LEFT JOIN rel_mastery rm ON rm.relation_id=r.id
                WHERE r.rel IN ('broader','opposite','related')
              UNION ALL
              SELECT r.dst AS cid, rm.state AS rstate FROM relation r LEFT JOIN rel_mastery rm ON rm.relation_id=r.id
                WHERE r.rel IN ('broader','opposite','related')
            ) GROUP BY cid""")}
    for r in rows:
        k, t = cov.get(r["id"], (0, 0))
        r["coverage"] = {"known": k, "total": t}
    return rows
