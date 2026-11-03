"""声を文字にする。Apple（端末内・無料・約0.3秒）と ElevenLabs Scribe v2（用語の一覧つき）を並べて走らせる。

2026-10-29 の手元の試し（合成音声6本・社労士と学習科学の用語入り）では、Scribe に用語の一覧（keyterms）を
渡すと6本とも用語を正しく書き、渡さないと5本で用語を誤った。Apple の SpeechTranscriber は文脈の語を渡しても
結果が変わらなかったので、確信度の低い字と別候補を整形役への手がかりにする。
鍵は環境変数か .env の ELEVENLABS_API_KEY を読むだけで（config.ELEVEN_ENV_FILES）、写さない・記録に出さない。

2026-11-02: 端末内の2本目として speech.cpp の Haas-ja-v1.0（日本語特化・Apache-2.0）を足した。TONARI_LOCAL_ASR=haas の
ときだけ、Scribe を使わない回（端末だけ・鍵なし・口座の残りが下限）に Apple と並べて走らせる。既定は off。測った結果:
合成音声6本で、用語なしは CER 13.8%（Apple 14.2%）、用語つきは 6.0%、1本 0.22秒（読み込み込み・M4 Pro）。整形役を
通したあとは、用語集なしで Apple だけ 5回平均 5.2%・Apple＋Haas 4回平均 4.4% で、回ごとの揺れ（3.9〜9.1%）の方が大きい。
本人の肉声10本では、本人が通した文に対して Apple 14.3%・Haas 22.7%（基準の文が Apple を直したものなので Apple に有利）。
用語に寄せると前後の語を落とすことがある（用語つき6本中1本、読みも添えた6本中2本）ので、整形役が失敗したときに戻す元の文は Apple にする
（fixer.base_text）。Apple の無い PC（Windows など）では、既定の auto で Haas が1本目になる（SETUP-windows.md）。
"""
import asyncio
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

import httpx

from . import config, db

_sub_cache = {"at": 0.0, "remaining": None}


def eleven_key() -> str:
    return eleven_key_source()[0]


def eleven_key_source() -> tuple[str, str]:
    """鍵と、どこから読んだか（env＝環境変数・data＝記録の置き場の .env・repo＝作者の手元の .env・none）。"""
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if key:
        return key, "env"
    for f, src in zip(config.ELEVEN_ENV_FILES, ("data", "repo")):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("ELEVENLABS_API_KEY="):
                    k = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if k:
                        return k, src
        except OSError:
            pass
    return "", "none"


def ffmpeg_bin(name: str) -> str:
    """ffmpeg と ffprobe の場所。TONARI_FFMPEG_DIR、PATH、Windows では winget の置き場の順に見る。"""
    exe = name + (".exe" if sys.platform == "win32" else "")
    d = os.environ.get("TONARI_FFMPEG_DIR")
    if d and (Path(d) / exe).exists():
        return str(Path(d) / exe)
    w = shutil.which(name)
    if w:
        return w
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        c = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Links" / exe
        if c.exists():
            return str(c)
    return name


async def to_wav(src: Path) -> tuple[Path, float]:
    """録音（webm など）を 16kHz モノラルの wav にする。長さ（秒）も返す。"""
    dst = src.with_suffix(".wav")
    p = await asyncio.create_subprocess_exec(
        ffmpeg_bin("ffmpeg"), "-loglevel", "error", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(dst),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, err = await p.communicate()
    if p.returncode != 0:
        raise RuntimeError("録音を変換できませんでした: " + err.decode("utf-8", "replace")[:200])
    q = await asyncio.create_subprocess_exec(
        ffmpeg_bin("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dst),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, _ = await q.communicate()
    try:
        sec = float(out.decode().strip())
    except ValueError:
        sec = 0.0
    return dst, sec


def apple_available() -> bool:
    """Apple の聞き取りは Mac で stt/bin/stt-helper を作ったときだけ。"""
    return sys.platform == "darwin" and config.STT_BIN.exists()


async def apple(wav: Path) -> dict:
    p = await asyncio.create_subprocess_exec(
        str(config.STT_BIN), str(wav), "ja_JP", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(p.communicate(), 60)
    if p.returncode != 0:
        raise RuntimeError("Apple の文字起こしに失敗: " + err.decode("utf-8", "replace")[:200])
    return json.loads(out)


async def eleven_remaining() -> int | None:
    """口座の残り（文字数の枠）。10分は覚えておく。読めなければ None。"""
    if time.time() - _sub_cache["at"] < 600:
        return _sub_cache["remaining"]
    key = eleven_key()
    rem = None
    if key:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key})
            if r.status_code == 200:
                d = r.json()
                rem = int(d.get("character_limit", 0)) - int(d.get("character_count", 0))
        except Exception:
            rem = None
    _sub_cache.update(at=time.time(), remaining=rem)
    return rem


async def scribe_allowed() -> tuple[bool, str]:
    mode = db.get_pref("scribe", config.SCRIBE_MODE)
    if mode == "off":
        return False, "off"
    if not eleven_key():
        return False, "鍵なし"
    if mode == "always":
        return True, "always"
    rem = await eleven_remaining()
    if rem is None:
        return True, "auto（残り不明）"
    if rem < config.ELEVEN_MIN_REMAINING:
        return False, f"残り {rem} が下限 {config.ELEVEN_MIN_REMAINING} を切った"
    return True, f"auto（残り {rem}）"


async def scribe(wav: Path, keyterms: list[str]) -> tuple[str, int]:
    key = eleven_key()
    terms = []
    for t in keyterms:
        t = t.strip()
        if t and len(t) <= 50 and t not in terms:
            terms.append(t)
        if len(terms) >= 50:
            break
    # httpx は data を list で渡すと本文の流れとして扱って非同期で落ちるので、dict の値を list にして同じ名前の欄を並べる
    data: dict = {"model_id": "scribe_v2", "language_code": "jpn", "tag_audio_events": "false"}
    if terms:
        data["keyterms"] = terms
    t0 = time.time()
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.elevenlabs.io/v1/speech-to-text", headers={"xi-api-key": key},
                         data=data, files={"file": (wav.name, wav.read_bytes(), "audio/wav")})
    if r.status_code != 200:
        raise RuntimeError(f"Scribe が {r.status_code} を返しました: {r.text[:200]}")
    return (r.json().get("text") or "").strip(), int((time.time() - t0) * 1000)


def speech_bin() -> str | None:
    """speech.cpp の speech。Finder から開いた .app は PATH が短いので ~/.local/bin も見る。Windows の入れ方
    （install.ps1）は %LOCALAPPDATA%\\Programs\\speech.cpp\\current\\speech.exe に置く。"""
    win = str(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "speech.cpp" / "current" / "speech.exe") if os.environ.get("LOCALAPPDATA") else ""
    for c in (config.SPEECH_BIN, shutil.which("speech"), str(Path.home() / ".local/bin/speech"),
              str(Path.home() / ".local/bin/speech.exe"), win):
        if c and Path(c).exists():
            return c
    return None


def local_allowed() -> tuple[bool, str]:
    if config.LOCAL_ASR == "off" or (config.LOCAL_ASR == "auto" and apple_available()):
        return False, "off"
    if not speech_bin():
        return False, "speech が無い"
    return True, config.LOCAL_ASR_MODEL


def haas_keywords(keyterms: list[str]) -> str:
    """Haas の用語の一覧（1行1語）。「=」は読みの区切りなので外す。寄せすぎると言っていない語を書くので50語まで。"""
    terms = []
    for t in keyterms:
        t = t.replace("=", "").replace("\n", " ").strip()
        if t and len(t) <= 50 and t not in terms:
            terms.append(t)
        if len(terms) >= 50:
            break
    return "\n".join(terms)


async def haas(wav: Path, keyterms: list[str]) -> tuple[str, int]:
    args = [speech_bin() or "speech", "asr", config.LOCAL_ASR_MODEL, "--format", "json"]
    kw = haas_keywords(keyterms)
    if kw:
        args += ["--keywords", kw]
    t0 = time.time()
    p = await asyncio.create_subprocess_exec(*args, str(wav), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(p.communicate(), 60)
    if p.returncode not in (0, 3):   # 3 は長さの上限で止まった（文は書かれている）
        raise RuntimeError("Haas の文字起こしに失敗: " + err.decode("utf-8", "replace")[:200])
    lines = out.decode("utf-8", "replace").strip().splitlines()
    text = (json.loads(lines[-1]).get("text") or "").strip() if lines else ""
    return text, int((time.time() - t0) * 1000)


def log_usage(engine: str, sec: float) -> None:
    with db.tx() as con:
        con.execute("INSERT INTO stt_usage(engine, sec, at) VALUES(?,?,?)", (engine, sec, db.now()))


async def transcribe(src: Path, keyterms: list[str]) -> dict:
    """録音1本を Apple と2本目（Scribe か、使えなければ端末内の Haas）で並べて文字にする。片方が失敗しても続ける。
    Apple の無い PC では2本目だけで文字にする（整形役は apple が None のときも動く）。"""
    wav, sec = await to_wav(src)
    ok, why = await scribe_allowed()
    tasks = {"apple": asyncio.create_task(apple(wav))} if apple_available() else {}
    local = None
    if ok:
        tasks["scribe"] = asyncio.create_task(scribe(wav, keyterms))
    else:
        lok, local = local_allowed()
        if lok:
            tasks["haas"] = asyncio.create_task(haas(wav, keyterms))
    out = {"sec": sec, "scribe_mode": why, "local_mode": local, "apple": None, "scribe": None, "scribe_ms": None,
           "haas": None, "haas_ms": None, "errors": []}
    for name, t in tasks.items():
        try:
            r = await t
            if name == "apple":
                out["apple"] = r
            elif name == "scribe":
                out["scribe"], out["scribe_ms"] = r
                log_usage("scribe", sec)
            else:
                out["haas"], out["haas_ms"] = r
        except Exception as e:
            out["errors"].append(f"{name}: {e}")
    out["second_engine"] = "scribe" if out["scribe"] is not None else ("haas" if out["haas"] is not None else None)
    out["second"] = out["scribe"] if out["scribe"] is not None else out["haas"]
    if not tasks:
        out["errors"].append(f"使える聞き取りがありません（Apple なし・Scribe {why}・端末内 {local}）")
    if out["apple"] is None and out["second"] is None:
        raise RuntimeError("文字にできませんでした（" + " / ".join(out["errors"]) + "）")
    return out


def new_audio_name() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
