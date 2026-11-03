"""画面への知らせ（話題の状態・答えの差分）。画面は /api/events を開きっぱなしにして ndjson で受け取る。"""
import asyncio

_subs: set[asyncio.Queue] = set()
_CLOSE = object()   # 流れを終わらせる印
_closed = False     # 止め始めたら、つなぎ直しも受けない


def count() -> int:
    """いま開いている画面の数（/api/events をつないでいる数）。"""
    return len(_subs)


def close_all() -> None:
    """止めるときに、開いている画面への流れを終わらせる。つながったままだと uvicorn が接続の終わりを待って止まりきらない
    （2026-11-03 に、見えない Chrome がつないだまま /api/shutdown すると止まらないのを見つけた）。"""
    global _closed
    _closed = True
    for q in list(_subs):
        try:
            q.put_nowait(_CLOSE)
        except asyncio.QueueFull:
            pass


def publish(ev: dict) -> None:
    for q in list(_subs):
        try:
            q.put_nowait(ev)
        except asyncio.QueueFull:
            pass


async def subscribe():
    if _closed:
        return
    q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    _subs.add(q)
    try:
        yield {"t": "hello"}
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), 20)
                if ev is _CLOSE:
                    return
                yield ev
            except asyncio.TimeoutError:
                yield {"t": "ping"}
    finally:
        _subs.discard(q)
