"""使う前の確かめ（設定の画面の「この PC の準備」と setup.py が使う）。鍵の中身は返さない。

need の項目が1つでも欠けていると、となりは声の往復ができない。直し方（fix）は OS ごとに書く。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import brain, config, stt

_NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}   # CREATE_NO_WINDOW


def _run(args: list[str], timeout: int = 20) -> tuple[int | None, str]:
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, **_NO_WINDOW)
        return p.returncode, (p.stdout or p.stderr).decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)


def _found(c: str) -> str | None:
    """名前か場所を受けて、実行できる場所を返す。"""
    if Path(c).is_absolute():
        return c if Path(c).exists() else None
    return shutil.which(c)


def check() -> dict:
    win, mac = sys.platform == "win32", sys.platform == "darwin"
    items: list[dict] = []

    def add(key: str, label: str, ok: bool, detail: str, fix: str = "", need: bool = True) -> None:
        items.append({"id": key, "label": label, "ok": bool(ok), "detail": detail, "fix": "" if ok else fix, "need": need})

    cb = _found(brain.claude_bin())
    rc, out = _run([cb, "--version"]) if cb else (None, "claude が見つかりません")
    add("claude", "Claude Code", rc == 0, f"{out[:60]}（{cb}）" if rc == 0 else out[:160],
        "Claude Code を入れて、一度 claude を起動してログインしてから、となりを開き直してください。")

    ff, fp = _found(stt.ffmpeg_bin("ffmpeg")), _found(stt.ffmpeg_bin("ffprobe"))
    add("ffmpeg", "ffmpeg（録音の変換）", bool(ff and fp), ff or "ffmpeg か ffprobe が見つかりません",
        "PowerShell で winget install --id Gyan.FFmpeg -e を打ち、となりを開き直してください。" if win
        else "brew install ffmpeg を打ち、となりを開き直してください。")

    apple = stt.apple_available()
    if mac:
        add("apple", "Apple の聞き取り（端末内）", apple, str(config.STT_BIN) if apple else "stt-helper がまだ作られていません",
            "bash stt/build.sh を打ってください。", need=False)

    sb = stt.speech_bin()
    lok, lwhy = stt.local_allowed()
    add("haas", "Haas の聞き取り（端末内・speech.cpp）", bool(sb),
        f"{sb}（{'使う' if lok else 'Apple があるので使わない' if apple else lwhy}）" if sb else "speech が見つかりません",
        "setup.ps1 をもう一度流すと speech.cpp が入ります。" if win else "Mac では Apple があるので要りません。", need=False)
    if win:
        vk = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "vulkan-1.dll"
        add("vulkan", "Vulkan（Haas が使う GPU の部品）", vk.exists(), str(vk) if vk.exists() else "vulkan-1.dll がありません",
            "GPU（NVIDIA・AMD・Intel）のドライバを入れ直すと入ります。入らない PC では Haas が動かないので、下の Scribe の鍵を入れてください。",
            need=False)

    key, src = stt.eleven_key_source()
    where = {"env": "環境変数から", "data": "設定で入れた鍵", "repo": "作者の手元の .env から"}.get(src, "")
    add("scribe", "Scribe の鍵（任意・録音を ElevenLabs に送る）", bool(key), f"鍵あり（{where}）" if key else "鍵なし（無くても動きます）",
        "ElevenLabs の鍵を入れると、聞き取りの精度がいちばん高い Scribe を使えます。", need=False)

    engines = [n for n, ok in (("Apple", apple), ("Haas", bool(sb) and lok), ("Scribe", bool(key))) if ok]
    add("stt", "声を文字にする方法", bool(engines), "・".join(engines) if engines else "ありません",
        "Haas（speech.cpp）を入れるか、Scribe の鍵を入れてください。")

    return {"os": sys.platform, "data_dir": str(config.DATA_DIR), "env_file": str(config.ENV_FILE),
            "ready": all(i["ok"] for i in items if i["need"]), "items": items}
