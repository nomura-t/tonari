"""初回の用意の仕上げ（setup.ps1 が uv・ffmpeg・speech.cpp を入れたあとに呼ぶ。名前を setup.py にしないのは、Python の道具が包みの設定と取り違えるため。Mac でも動く）。

  uv run python prepare.py                     # 全部（場所の記録・Haas のモデル・先生役のモデル・確かめ・ショートカット）
  uv run python prepare.py --no-model-check    # claude で1回だけ聞く確かめ（opus が使えるか）を飛ばす
  uv run python prepare.py --no-shortcut       # Windows のショートカットを作らない

すること。PATH に無い speech・ffmpeg の場所を記録の置き場の .env に書く（TONARI_SPEECH_BIN・TONARI_FFMPEG_DIR）。
Haas のモデルは最初に使うときに speech が取りに行くので、無音1秒で一度走らせて取らせる。claude に1回だけ短く聞いて、
opus が使えなければ TONARI_TUTOR_MODEL=sonnet を書く。最後に health.check() の結果を表で出し、Windows では
スタートメニューとデスクトップに「となり」のショートカットを作る。足りないものがあれば終了コード 1。
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from server import brain, config, health, stt  # noqa: E402

NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def say(msg: str) -> None:
    print(msg, flush=True)


def record_paths() -> None:
    sb = stt.speech_bin()
    if sb and not shutil.which("speech") and not os.environ.get("TONARI_SPEECH_BIN"):
        config.write_env("TONARI_SPEECH_BIN", sb)
        say(f"speech の場所を記録しました: {sb}")
    ff = stt.ffmpeg_bin("ffmpeg")
    if Path(ff).is_absolute() and not shutil.which("ffmpeg") and not os.environ.get("TONARI_FFMPEG_DIR"):
        config.write_env("TONARI_FFMPEG_DIR", str(Path(ff).parent))
        say(f"ffmpeg の場所を記録しました: {Path(ff).parent}")


def fetch_haas_model() -> None:
    sb = stt.speech_bin()
    if not sb or stt.apple_available():
        return
    ff = stt.ffmpeg_bin("ffmpeg")
    wav = config.WORK_DIR / "setup-silence.wav"
    r = subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "1", str(wav)],
                       capture_output=True, **NO_WINDOW)
    if r.returncode != 0:
        say("無音の wav を作れなかったので、Haas のモデルは最初に話したときに取ります")
        return
    say("Haas のモデルを用意しています（初回はダウンロードに数分かかることがあります）")
    t0 = time.time()
    r = subprocess.run([sb, "asr", config.LOCAL_ASR_MODEL, "--format", "json", str(wav)], capture_output=True, timeout=1800, **NO_WINDOW)
    ok = r.returncode in (0, 3)
    say(f"Haas: {'使えます' if ok else '失敗しました'}（{time.time() - t0:.1f}秒）"
        + ("" if ok else "\n" + r.stderr.decode("utf-8", "replace")[-400:]))


def ask_claude(model: str) -> bool:
    args = [brain.claude_bin(), "-p", "--model", model, "--output-format", "json", "--safe-mode", "--tools", "",
            "--no-session-persistence", "OK とだけ返してください。"]
    try:
        r = subprocess.run(args, capture_output=True, timeout=180, cwd=config.WORK_DIR, env=brain.child_env(), **NO_WINDOW)
        d = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
        return r.returncode == 0 and not d.get("is_error") and bool(str(d.get("result") or "").strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def check_tutor_model() -> None:
    m = config.TUTOR_MODEL
    say(f"先生役のモデル {m} を claude で1回だけ確かめています")
    if ask_claude(m):
        say(f"{m}: 使えます")
        return
    if m != "sonnet" and ask_claude("sonnet"):
        config.write_env("TONARI_TUTOR_MODEL", "sonnet")
        say(f"{m} は使えなかったので、先生役を sonnet にしました（設定の画面でも変えられます）")
        return
    say("claude で答えが返りませんでした。claude を一度起動してログインしてから、もう一度 setup.ps1（Mac は prepare.py）を流してください")


def make_shortcuts() -> None:
    if sys.platform != "win32":
        return
    pyw = HERE / ".venv" / "Scripts" / "pythonw.exe"
    if not pyw.exists():
        say(f"{pyw} が無いのでショートカットを作れません（uv sync を先に流してください）")
        return
    ps = ("$w = New-Object -ComObject WScript.Shell; "
          "foreach ($d in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) { "
          "$s = $w.CreateShortcut((Join-Path $d 'となり.lnk')); "
          f"$s.TargetPath = '{pyw}'; $s.Arguments = '\"{HERE / 'launch.py'}\"'; $s.WorkingDirectory = '{HERE}'; "
          "$s.Description = '声で回す学び'; $s.Save(); Write-Output (Join-Path $d 'となり.lnk') }")
    enc = base64.b64encode(ps.encode("utf-16-le")).decode()
    r = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", enc], capture_output=True, **NO_WINDOW)
    out = r.stdout.decode("utf-8", "replace").strip()
    say("ショートカットを作りました: " + out.replace("\r\n", "、") if r.returncode == 0 else
        "ショートカットを作れませんでした: " + r.stderr.decode("utf-8", "replace")[-300:])


def main() -> int:
    ap = argparse.ArgumentParser(description="となりの初回の用意")
    ap.add_argument("--no-model-check", action="store_true")
    ap.add_argument("--no-shortcut", action="store_true")
    a = ap.parse_args()
    config.ensure_dirs()
    say(f"記録の置き場: {config.DATA_DIR}")
    record_paths()
    fetch_haas_model()
    if not a.no_model_check:
        check_tutor_model()
    h = health.check()
    say("")
    for i in h["items"]:
        say(f"{'使えます' if i['ok'] else '要対応' if i['need'] else 'なし'}  {i['label']}: {i['detail']}" + (f"\n        直し方: {i['fix']}" if i["fix"] else ""))
    if not a.no_shortcut:
        make_shortcuts()
    say("\n用意ができました。" if h["ready"] else "\n足りないものがあります（上の「要対応」）。")
    return 0 if h["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
