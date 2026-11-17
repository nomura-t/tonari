"""画面の流れの確かめ（v0.6）。作り物の先生役（tests/fake_claude.py）でサーバーを立て、アプリの検算の窓（窓を出さない）で
tests/ui/ の場面を順に流し、場面が返した「落ちた項目」を数える。Claude の枠は使わない。本人の記録にも触らない
（記録の置き場は、流すたびに作る一時のフォルダ）。Mac だけ（アプリ となり.app の実行ファイルが要る）。

  uv run python tests/ui_flow.py                    全部の場面
  uv run python tests/ui_flow.py 02 04              名前にその字を含む場面だけ
  uv run python tests/ui_flow.py 03 --shot x.png    場面の終わりの画面を撮る（1つ選んだときだけ）

場面は tests/ui/NN-名前.js で、1行目に `// delay=秒`（作り物の先生役が答え始めるまでの秒）、本体は
`(async () => { PRE … return { ok, ng }; })()` の形。PRE の行に tests/ui/pre.js の共通の道具が入る。
pytest の対象ではない（アプリの実行ファイルと数分の時間が要るため）。
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
UI_DIR = APP_DIR / "tests" / "ui"
APP_BIN = Path(os.environ.get("TONARI_APP_BIN") or Path.home() / "Applications" / "となり.app" / "Contents" / "MacOS" / "Tonari")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def alive(port: int) -> bool:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/state", headers={"X-Tonari": "1"})
    try:
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return r.status == 200
    except OSError:
        return False


def wrap(src: str) -> str:
    """場面を、二重に評価されても1回だけ走る形に包む（検算の窓は、まれに同じ式を2回評価する）。"""
    body = "\n".join(l for l in src.strip().splitlines() if not l.startswith("//")).strip()
    head, tail = "(async () => {", "})()"
    if not (body.startswith(head) and body.endswith(tail)):
        raise SystemExit("場面の形が違います（(async () => { … })() で書く）")
    inner = body[len(head):-len(tail)].replace("  PRE\n", (UI_DIR / "pre.js").read_text(encoding="utf-8"))
    return "(window.__sc = window.__sc || (async () => {" + inner + "})())"


def run_scene(path: Path, port: int, delay_file: Path, shot: str | None) -> dict:
    src = path.read_text(encoding="utf-8")
    m = re.search(r"^// delay=([0-9.]+)", src, re.M)
    delay_file.write_text(m.group(1) if m else "2", encoding="utf-8")
    cmd = [str(APP_BIN), "--selftest", "--port", str(port), "--js", wrap(src)] + (["--snapshot", shot] if shot else [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=420)
    except subprocess.TimeoutExpired:
        return {"ok": [], "ng": ["時間切れ（420秒）"]}
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith("SELFTEST JS ERROR"):
            return {"ok": [], "ng": [line[:600]]}
        if line.startswith("SELFTEST JS "):
            try:
                out = json.loads(line[len("SELFTEST JS "):])
            except ValueError:
                return {"ok": [], "ng": ["結果を読めませんでした: " + line[:300]]}
            return out if isinstance(out, dict) and "ng" in out else {"ok": [], "ng": ["場面が { ok, ng } を返しませんでした"]}
    return {"ok": [], "ng": ["結果がありません: " + (r.stdout + r.stderr)[-400:]]}


def main() -> int:
    args = sys.argv[1:]
    shot = None
    if "--shot" in args:
        i = args.index("--shot")
        shot = args[i + 1]
        del args[i:i + 2]
    if not APP_BIN.exists():
        print(f"アプリの実行ファイルがありません: {APP_BIN}（Mac で bash app/build_app.sh を流すか、TONARI_APP_BIN で指す）")
        return 2
    scenes = [p for p in sorted(UI_DIR.glob("[0-9]*.js")) if not args or any(a in p.name for a in args)]
    if not scenes:
        print("場面がありません")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="tonari-ui-"))
    port, delay_file = free_port(), tmp / "delay"
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
    env.update(TONARI_DATA_DIR=str(tmp / "data"), TONARI_PORT=str(port), TONARI_SHELF_LIB=str(tmp / "no-shelf"),
               TONARI_CLAUDE=str(APP_DIR / "tests" / "fake_claude.py"), TONARI_FAKE_DELAY_FILE=str(delay_file),
               TONARI_RETURN_AFTER_SEC="3", TONARI_RECORDER="on", TONARI_SCRIBE="off")
    log = open(tmp / "server.log", "w", encoding="utf-8")
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", str(port)],
                           cwd=APP_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
    bad = 0
    try:
        t0 = time.time()
        while not alive(port):
            if srv.poll() is not None or time.time() - t0 > 60:
                print(f"サーバーが立ち上がりませんでした（ログ: {tmp / 'server.log'}）")
                return 2
            time.sleep(0.3)
        for p in scenes:
            t1 = time.time()
            out = run_scene(p, port, delay_file, shot if len(scenes) == 1 else None)
            bad += len(out["ng"])
            print(f"{p.name}: 通った {len(out['ok'])}・落ちた {len(out['ng'])}（{time.time() - t1:.0f}秒）")
            for x in out["ng"]:
                print("  落ちた: " + x)
        errs = (tmp / "server.log").read_text(encoding="utf-8").count("Traceback")
        print(f"場面 {len(scenes)}・落ちた項目 {bad}・サーバーの例外 {errs}（作り物の音を聞き取れない分を含む）・ログ {tmp / 'server.log'}")
    finally:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", data=b"", method="POST", headers={"X-Tonari": "1"})
            urllib.request.urlopen(req, timeout=3).read()
        except OSError:
            pass
        try:
            srv.wait(timeout=6)
        except subprocess.TimeoutExpired:
            srv.terminate()
        log.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
