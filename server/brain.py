"""Claude Code（Max プランのログイン）を子プロセスとして動かす。

Claude の API キーは使わない。子の環境から ANTHROPIC_* を外し、手を加えていない `claude` を本人の Mac で
起動する（作者の別のアプリで確かめた経路）。--bare は OAuth を読まないので使わない。

先生役（Tutor）は話題ごとに1本を常駐させ、`--restricted --tools Read,Grep,Glob` で作業フォルダ（棚の本文の写し）
だけを読めるようにする。会話は Claude Code の記録に残し（--no-session-persistence を付けない）、閉じたあとは
`--resume <会話の id>` で続きから始める（2026-10-29 に stream-json の入力で再開できることを確かめた）。
`--resume` した会話は、会話を始めたときの指示を使い続け、`--system-prompt-file` を渡し直しても替わらない（2026-11-10・
claude 2.1.322 で確かめた）。指示が変わった話題は、続けるかどうかを pipeline.ask_tutor が tutor.resume_plan で決める。
整形役（Spare）は温めた予備を1回だけ使って閉じる（話題をまたいで文脈を持ち越さない）。
"""
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import AsyncIterator

from . import config

_DROP_ENV_PREFIXES = ("ANTHROPIC_",)
_DROP_ENV = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT"}


class BrainError(RuntimeError):
    pass


def claude_bin() -> str:
    if sys.platform == "win32":   # ネイティブ版の claude.exe を npm 版の claude.cmd より先に探す
        return (os.environ.get("TONARI_CLAUDE") or shutil.which("claude.exe") or shutil.which("claude")
                or str(Path.home() / ".local" / "bin" / "claude.exe"))
    return os.environ.get("TONARI_CLAUDE") or shutil.which("claude") or str(Path.home() / ".local/bin/claude")


def child_env() -> dict:
    """子の環境。ANTHROPIC_* を外してログインのまま動かす。claude を API キーなどで動かしている PC は
    TONARI_KEEP_ANTHROPIC_ENV=1 で外さない（その PC で claude を打って動く設定をそのまま使う）。"""
    keep = os.environ.get("TONARI_KEEP_ANTHROPIC_ENV") == "1"
    env = {k: v for k, v in os.environ.items()
           if (keep or not k.startswith(_DROP_ENV_PREFIXES)) and k not in _DROP_ENV}
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    return env


async def _read_stderr(proc, n=2000) -> str:
    if not proc.stderr:
        return ""
    try:
        return (await asyncio.wait_for(proc.stderr.read(n), 1)).decode("utf-8", "replace")
    except asyncio.TimeoutError:
        return ""


class Tutor:
    """先生役。1つの話題に1本。ask() は ("text", 差分) / ("tool", 説明) / ("sid", 会話の id) を順に返す。"""

    def __init__(self, session_id: int, system_prompt: str, model: str, resume_sid: str | None):
        self.session_id = session_id
        self.system_prompt = system_prompt
        self.model = model
        self.resume_sid = resume_sid
        self.proc: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()
        self.last_used = time.time()
        self.prompt_file = config.WORK_DIR / f"tutor-{session_id}.txt"

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def start(self) -> None:
        config.ensure_dirs()
        self.prompt_file.write_text(self.system_prompt, encoding="utf-8")
        args = [claude_bin(), "-p", "--safe-mode", "--restricted", "--tools", "Read,Grep,Glob",
                "--model", self.model,
                "--input-format", "stream-json", "--output-format", "stream-json",
                "--include-partial-messages", "--verbose",
                "--system-prompt-file", str(self.prompt_file)]
        if config.TUTOR_EFFORT:
            args += ["--effort", config.TUTOR_EFFORT]
        if self.resume_sid:
            args += ["--resume", self.resume_sid]
        self.proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=str(config.CORPUS_DIR), env=child_env(),
            limit=32 * 1024 * 1024)

    async def ask(self, content: str, timeout: float = 600) -> AsyncIterator[tuple[str, str]]:
        async with self.lock:
            if not self.alive:
                await self.start()
            self.last_used = time.time()
            assert self.proc and self.proc.stdin and self.proc.stdout
            msg = {"type": "user", "message": {"role": "user", "content": content}}
            self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
            await self.proc.stdin.drain()
            got_delta = False
            deadline = time.time() + timeout
            while True:
                try:
                    line = await asyncio.wait_for(self.proc.stdout.readline(), max(1, deadline - time.time()))
                except asyncio.TimeoutError:
                    self.proc.kill()
                    raise BrainError(f"先生役が {timeout:.0f} 秒で答え終わりませんでした")
                if not line:
                    err = await _read_stderr(self.proc)
                    if self.resume_sid and "No conversation found" in err:
                        self.resume_sid = None   # 記録が消えていたら新しい会話で始め直す（呼び出し側が再送する）
                    raise BrainError("先生役のプロセスが止まりました: " + err[:300])
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                t = ev.get("type")
                if t == "system" and ev.get("subtype") == "init" and ev.get("session_id"):
                    self.resume_sid = ev["session_id"]
                    yield ("sid", ev["session_id"])
                elif t == "stream_event":
                    e = ev.get("event", {})
                    et = e.get("type")
                    if et == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta":
                        got_delta = True
                        yield ("text", e["delta"]["text"])
                    elif et == "content_block_start" and e.get("content_block", {}).get("type") == "tool_use":
                        yield ("tool", e["content_block"].get("name", ""))
                elif t == "assistant" and not got_delta:
                    for block in ev.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            yield ("text", block["text"])
                elif t == "user":
                    got_delta = False   # 道具の結果のあとの文は、また差分で来る
                elif t == "result":
                    if ev.get("session_id"):
                        self.resume_sid = ev["session_id"]
                        yield ("sid", ev["session_id"])
                    if ev.get("is_error"):
                        raise BrainError("先生役がエラーを返しました: " + str(ev.get("result"))[:300])
                    return

    async def close(self) -> None:
        if self.alive and self.proc:
            try:
                self.proc.stdin.close()
                await asyncio.wait_for(self.proc.wait(), 5)
            except Exception:
                self.proc.kill()
        self.proc = None


class TutorPool:
    """話題ごとの先生役。常駐は TUTOR_MAX_ALIVE 本まで、使わなくなったものは閉じる（続きは --resume）。"""

    def __init__(self):
        self.tutors: dict[int, Tutor] = {}

    def get(self, session_id: int, system_prompt: str, model: str, resume_sid: str | None) -> Tutor:
        t = self.tutors.get(session_id)
        if t is None or t.model != model:
            t = Tutor(session_id, system_prompt, model, resume_sid)
            self.tutors[session_id] = t
        return t

    async def trim(self) -> None:
        now = time.time()
        live = sorted((t for t in self.tutors.values() if t.alive and not t.lock.locked()), key=lambda t: t.last_used)
        for t in live:
            if now - t.last_used > config.TUTOR_IDLE_SEC:
                await t.close()
        live = [t for t in live if t.alive]
        while len([t for t in self.tutors.values() if t.alive]) > config.TUTOR_MAX_ALIVE and live:
            await live.pop(0).close()

    async def close_all(self) -> None:
        for t in list(self.tutors.values()):
            await t.close()


TUTORS = TutorPool()


class Spare:
    """整形役の予備。起動して待たせておき、1回だけ問いを流して閉じる。"""

    def __init__(self, system_prompt: str, model: str, effort: str | None):
        self.system_prompt = system_prompt
        self.model = model
        self.effort = effort
        self.proc: asyncio.subprocess.Process | None = None
        self.started = time.time()
        self.prompt_file = config.WORK_DIR / f"fixer-{os.getpid()}-{time.time_ns()}.txt"

    async def start(self) -> None:
        config.ensure_dirs()
        self.prompt_file.write_text(self.system_prompt, encoding="utf-8")
        args = [claude_bin(), "-p", "--safe-mode", "--tools", "", "--no-session-persistence",
                "--model", self.model,
                "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                "--system-prompt-file", str(self.prompt_file)]
        if self.effort:
            args += ["--effort", self.effort]
        self.proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=str(config.WORK_DIR), env=child_env(),
            limit=16 * 1024 * 1024)
        self.started = time.time()

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def ask(self, content: str, timeout: float = 60) -> str:
        assert self.proc and self.proc.stdin and self.proc.stdout
        msg = {"type": "user", "message": {"role": "user", "content": content}}
        self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

        async def read() -> str:
            while True:
                line = await self.proc.stdout.readline()
                if not line:
                    raise BrainError("整形役のプロセスが止まりました: " + (await _read_stderr(self.proc))[:300])
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("type") == "result":
                    if ev.get("is_error"):
                        raise BrainError("整形役がエラーを返しました: " + str(ev.get("result"))[:300])
                    return ev.get("result") or ""
        try:
            return await asyncio.wait_for(read(), timeout)
        except asyncio.TimeoutError:
            raise BrainError(f"整形役が {timeout:.0f} 秒で返しませんでした")
        finally:
            await self.close()

    async def close(self) -> None:
        if self.alive and self.proc:
            try:
                self.proc.stdin.close()
                await asyncio.wait_for(self.proc.wait(), 3)
            except Exception:
                self.proc.kill()
        self.prompt_file.unlink(missing_ok=True)


class SparePool:
    """予備を1本だけ温めておく。古くなった予備（30分）は立て直す。"""

    def __init__(self, system_prompt: str, model: str, effort: str | None):
        self.system_prompt, self.model, self.effort = system_prompt, model, effort
        self.spare: Spare | None = None
        self.lock = asyncio.Lock()
        self.warming: asyncio.Task | None = None

    async def _new(self) -> Spare:
        s = Spare(self.system_prompt, self.model, self.effort)
        await s.start()
        return s

    def warm(self) -> None:
        if self.warming and not self.warming.done():
            return

        async def go():
            async with self.lock:
                if self.spare and self.spare.alive and time.time() - self.spare.started < 1800:
                    return
                if self.spare:
                    await self.spare.close()
                self.spare = await self._new()
        self.warming = asyncio.create_task(go())

    async def take(self) -> Spare:
        if self.warming and not self.warming.done():
            try:
                await self.warming
            except Exception:
                pass
        async with self.lock:
            s = self.spare if self.spare and self.spare.alive else None
            self.spare = None
        if s is None:
            s = await self._new()
        self.warm()
        return s

    async def close(self) -> None:
        if self.spare:
            await self.spare.close()
            self.spare = None
