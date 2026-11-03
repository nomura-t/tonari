"""となりを起動する（Windows・Mac・Linux で同じ）。サーバーを裏で立て、アプリの窓（Edge か Chrome の --app）で開く。
窓を閉じると、サーバーは15秒後に自分で止まる（TONARI_EXIT_WHEN_CLOSED・server/app.py の exit_when_closed）。
すでに動いていれば窓だけ開く。Mac のふだんの起動は となり.app（app/）で、これは主に Windows 用。

  python launch.py                                # ふだん（Windows のショートカットは .venv\\Scripts\\pythonw.exe launch.py）
  python launch.py --headless --close-after 8     # 窓を出さずに、起動→開く→閉じる→止まるまでを確かめる

pythonw.exe では標準出力が無いので、経過は記録の置き場の launch.log に書き、起動できないときは窓で知らせる。
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from server import config  # noqa: E402  記録の置き場の .env（TONARI_*）もここで読む

URL = f"http://127.0.0.1:{config.PORT}/"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW


def log(msg: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(config.DATA_DIR / "launch.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    if sys.stdout:
        print(line, flush=True)


def alert(msg: str) -> None:
    """起動できないときに知らせる（Windows は窓、ほかは標準出力）。"""
    log(msg)
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "となり", 0x10)


def alive() -> bool:
    try:
        req = urllib.request.Request(URL + "api/state", headers={"X-Tonari": "1"})
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def start_server() -> subprocess.Popen:
    config.ensure_dirs()
    out = open(config.DATA_DIR / "server.log", "ab")
    env = {**os.environ, "PYTHONUTF8": "1", "TONARI_EXIT_WHEN_CLOSED": "1"}
    # --reload や --workers は付けない（Windows では子プロセスを立てられないイベントループに変わり、先生役が起動しない）
    # 止めるときに接続の終わりを長く待たない（画面への流れは events.close_all で先に閉じる。これは念のための上限）
    return subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", str(config.PORT),
                             "--timeout-graceful-shutdown", "5"],
                            cwd=HERE, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                            creationflags=NO_WINDOW)


def browser() -> str | None:
    """アプリの窓にできるブラウザ（Chromium 系）。Windows は Edge を先に探す。"""
    c: list = []
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                c += [Path(base) / "Microsoft/Edge/Application/msedge.exe", Path(base) / "Google/Chrome/Application/chrome.exe"]
        c += [shutil.which("msedge"), shutil.which("chrome")]
    elif sys.platform == "darwin":
        c += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
              Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")]
    else:
        c += [shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")]
    return next((str(p) for p in c if p and Path(p).exists()), None)


def open_window(headless: bool) -> subprocess.Popen | None:
    b = browser()
    if not b:
        log("Edge も Chrome も見つからないので、ふだんのブラウザで開きます")
        webbrowser.open(URL)
        return None
    # 専用の置き場にすると、ふだんのブラウザと分かれ、マイクの許可もこの窓だけに残る
    args = [b, f"--app={URL}", f"--user-data-dir={config.DATA_DIR / 'browser'}", "--no-first-run",
            "--no-default-browser-check", "--window-size=1440,900"]
    if headless:
        args.append("--headless=new")
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    ap = argparse.ArgumentParser(description="となりを起動する")
    ap.add_argument("--headless", action="store_true", help="窓を出さずに開く（確かめ用）")
    ap.add_argument("--close-after", type=float, default=0, help="この秒数で窓を閉じる（確かめ用）")
    a = ap.parse_args()

    if alive():
        log(f"もう動いているので窓だけ開きます（{URL}）")
        open_window(a.headless)
        return 0
    srv = start_server()
    log(f"サーバーを起動しました（pid {srv.pid}・{URL}）")
    t0 = time.time()
    while not alive():
        if srv.poll() is not None or time.time() - t0 > 90:
            tail = (config.DATA_DIR / "server.log").read_text(encoding="utf-8", errors="replace")[-600:]
            alert(f"となりを起動できませんでした。記録: {config.DATA_DIR / 'server.log'}\n\n{tail}")
            if srv.poll() is None:
                srv.terminate()
            return 1
        time.sleep(0.4)
    log(f"起動まで {time.time() - t0:.1f}秒")
    win = open_window(a.headless)
    if a.close_after and win:
        time.sleep(a.close_after)
        win.terminate()
        log("確かめのため窓を閉じました")
    srv.wait()
    log(f"サーバーが止まりました（終了コード {srv.returncode}）")
    if win and win.poll() is None:
        win.terminate()   # 窓を閉じてもブラウザが裏に残っていたら止める（この窓専用の置き場なので、ほかの窓には触れない）
    return 0


if __name__ == "__main__":
    sys.exit(main())
