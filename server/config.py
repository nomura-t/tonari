"""設定。記録はリポジトリの外（Mac は ~/Library/Application Support/tonari/、Windows は %LOCALAPPDATA%\\tonari\\）に置く。"""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent          # tonari/
REPO_DIR = APP_DIR.parent                                  # 作者の手元では tonari/ を入れている親のリポジトリ


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "tonari"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/tonari"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "tonari"


DATA_DIR = Path(os.environ.get("TONARI_DATA_DIR") or _default_data_dir())
ENV_FILE = DATA_DIR / ".env"       # setup.py と設定の画面が書く（TONARI_* と ELEVENLABS_API_KEY）


def _load_env_file(path: Path) -> None:
    """記録の置き場の .env にある TONARI_* を、環境変数に無いものだけ読む。鍵の行は環境変数に入れない（stt.eleven_key が読む）。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        k, sep, v = line.strip().partition("=")
        if sep and k.startswith("TONARI_") and k != "TONARI_DATA_DIR":
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def write_env(key: str, value: str | None) -> None:
    """記録の置き場の .env の1行を書き換える（value が None なら消す）。ほかの行はそのまま残す。"""
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    lines = [l for l in lines if l.partition("=")[0].strip() != key]
    if value is not None:
        lines.append(f"{key}={value}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


_load_env_file(ENV_FILE)
DB_PATH = DATA_DIR / "tonari.db"
AUDIO_DIR = DATA_DIR / "audio"      # 本人の録音（webm と 16kHz の wav）
WORK_DIR = DATA_DIR / "work"        # 整形役を起動する場所（リポジトリの CLAUDE.md を読ませない）
CORPUS_DIR = DATA_DIR / "corpus"    # 棚の本文の写し（<id>.txt）。先生役はここだけを Read・Grep で読む

HOST = "127.0.0.1"
PORT = int(os.environ.get("TONARI_PORT", "4880"))
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

# 先生役（話題ごとに1本を常駐）。本人の指定で opus。
TUTOR_MODEL = os.environ.get("TONARI_TUTOR_MODEL", "opus")
TUTOR_EFFORT = os.environ.get("TONARI_TUTOR_EFFORT", "") or None
TUTOR_MAX_ALIVE = int(os.environ.get("TONARI_TUTOR_MAX_ALIVE", "6"))     # 同時に常駐させる上限（超えたら一番古いものを閉じる）
TUTOR_IDLE_SEC = int(os.environ.get("TONARI_TUTOR_IDLE_SEC", "1800"))    # これだけ使わなければ閉じる（再開は --resume）
# 整形役（文字起こしの直し）。1回ごとに温めた予備を使い捨てる（話題をまたいで文脈を持ち越さない）。
FIXER_MODEL = os.environ.get("TONARI_FIXER_MODEL", "sonnet")
FIXER_EFFORT = os.environ.get("TONARI_FIXER_EFFORT", "low") or None

# Apple の聞き取り（Mac だけ。stt/build.sh で作る）。無い PC では端末内の Haas か Scribe だけで文字にする
STT_BIN = Path(os.environ.get("TONARI_STT_BIN") or APP_DIR / "stt" / "bin" / "stt-helper")
# ElevenLabs の鍵。環境変数 ELEVENLABS_API_KEY が無ければ、上から順に .env の ELEVENLABS_API_KEY= の行を読む
# （記録の置き場の .env、作者の手元で tonari/ を入れている親のリポジトリの .env）。鍵は写さない・記録に出さない
ELEVEN_ENV_FILES = [ENV_FILE, REPO_DIR / "02-マーケ配信" / "tools" / ".env"]
# Scribe: always=毎回 / auto=口座の残りが下限より多いときだけ / off=使わない（Apple と整形役だけ）
SCRIBE_MODE = os.environ.get("TONARI_SCRIBE", "auto")
ELEVEN_MIN_REMAINING = int(os.environ.get("TONARI_ELEVEN_MIN_REMAINING", "5000"))
# 端末内の2本目の聞き取り（speech.cpp の Haas）。Scribe を使わないときに Apple と並べる。既定は off（2026-11-02 の測りで、
# Mac では整形役を通したあとの得が回ごとの揺れより小さく、本人の肉声で Apple より良い証拠も無かった）。
# auto=Apple の聞き取りが無い PC（Windows など）でだけ使う / haas=Mac でも Apple と並べる / off=使わない
LOCAL_ASR = os.environ.get("TONARI_LOCAL_ASR", "auto")
LOCAL_ASR_MODEL = os.environ.get("TONARI_LOCAL_ASR_MODEL", "haas-ja-v1.0")
SPEECH_BIN = os.environ.get("TONARI_SPEECH_BIN", "")

# 答えを開いてからこれだけたって話題に戻ったら、その答えの確かめの問いを1つ出す（v0.3）
RETURN_AFTER_SEC = int(os.environ.get("TONARI_RETURN_AFTER_SEC", "120"))

# 棚（アーティファクト棚の写し）。本文の写しは棚の shelf.guide.build_mirror をそのまま使う。
SHELF_TOOL_DIR = REPO_DIR / ".claude" / "tools" / "artifact-shelf"
SHELF_LIB = Path(os.environ.get("TONARI_SHELF_LIB", REPO_DIR / ".claude" / ".artifacts"))


def ensure_dirs() -> None:
    for d in (DATA_DIR, AUDIO_DIR, WORK_DIR, CORPUS_DIR):
        d.mkdir(parents=True, exist_ok=True)
