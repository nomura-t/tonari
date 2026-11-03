"""文字起こしの方式ごとの文字誤り率（CER）を測る。tests/audio の wav と texts.txt（1行1本・名前の番号の順）を使う。

  uv run python -m tests.stt_eval            # Apple だけ（無料）
  uv run python -m tests.stt_eval --scribe   # Scribe の用語あり・なしも（ElevenLabs の口座を少し使う）
  uv run python -m tests.stt_eval --fixer    # Apple の結果を整形役（sonnet・用語集つき）に通した CER
  uv run python -m tests.stt_eval --haas     # 端末内の Haas-ja-v1.0（speech.cpp）の用語あり・なしも
  uv run python -m tests.stt_eval --fixer --haas [--no-glossary]   # Apple と Haas の2本を整形役に。用語集を空にもできる

句読点・空白・記号を除き、NFKC で畳んでから比べる。本人の肉声での測り直しは、アプリの記録（turn の
apple_text・scribe_text・本人が直した final_text）から同じ関数で測れる。
"""
import asyncio
import re
import sys
import unicodedata
from pathlib import Path

from server import stt

AUDIO = Path(__file__).parent / "audio"


def wavs() -> list[Path]:
    """試しの音声。macOS の声の音声は再配布できないのでリポジトリに入れていない（tests/audio/make_mac.sh で作る）。"""
    w = sorted(AUDIO.glob("*.wav"))
    if not w:
        sys.exit("tests/audio に wav がありません。Mac は bash tests/audio/make_mac.sh で作り、ほかの PC は texts.txt を"
                 "読み上げて録った wav を「名前-行の番号.wav」で置いてください。")
    return w


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s、。，．,.!?！？「」『』・ー-]", "", s)


def cer(ref: str, hyp: str) -> tuple[int, int]:
    a, b = norm(ref), norm(hyp)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1], len(a)


async def main(use_scribe: bool, use_haas: bool = False) -> None:
    refs = [l for l in (AUDIO / "texts.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    terms = [l for l in (AUDIO / "keyterms.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    tot: dict[str, list[int]] = {}
    for wav in wavs():
        ref = refs[int(wav.stem.split("-")[1]) - 1]
        outs = {"apple": (await stt.apple(wav))["text"]}
        if use_scribe:
            outs["scribe"] = (await stt.scribe(wav, []))[0]
            outs["scribe+用語"] = (await stt.scribe(wav, terms))[0]
        if use_haas:
            outs["haas"] = (await stt.haas(wav, []))[0]
            outs["haas+用語"] = (await stt.haas(wav, terms))[0]
        for k, v in outs.items():
            e, n = cer(ref, v)
            tot.setdefault(k, [0, 0])
            tot[k][0] += e
            tot[k][1] += n
            print(f"{wav.name:12} {k:10} {e:3}/{n:3}  {v}")
    print()
    for k, (e, n) in tot.items():
        print(f"{k:10} CER {100 * e / n:5.1f}%（{e}/{n}）")




async def fixer_eval(use_haas: bool = False, glossary: bool = True) -> None:
    """Apple の結果（と、use_haas なら Haas の結果）を整形役に通したときの CER。Scribe を使えないときの落ち方を見る。

    glossary=False は用語集が空のとき（新しい話題の最初の発言）。Haas にも用語を渡さない。整形役の返事が読めない回は
    本番（fixer.fix）と同じく元の文（fixer.base_text）に戻して数える。
    """
    from server import fixer
    refs = [l for l in (AUDIO / "texts.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    terms = [l for l in (AUDIO / "keyterms.txt").read_text(encoding="utf-8").splitlines() if l.strip()] if glossary else []
    label = ("apple+haas+直し" if use_haas else "apple+直し") + ("" if glossary else "（用語集なし）")
    e_tot = n_tot = 0
    for wav in wavs():
        ref = refs[int(wav.stem.split("-")[1]) - 1]
        a = await stt.apple(wav)
        h = (await stt.haas(wav, terms))[0] if use_haas else None
        eng = "haas" if use_haas else "scribe"
        s = await fixer.POOL.take()
        raw = await s.ask(fixer.build_input(a, h, terms, [], "", eng), timeout=60)
        try:
            text = fixer.verify(fixer.parse(raw), a["text"], h, eng)["text"]
        except ValueError:
            text = fixer.base_text(a["text"], h, eng)
            print(f"{wav.name:12} 整形役の返事が読めないので元の文に戻した")
        e, n = cer(ref, text)
        e_tot += e
        n_tot += n
        print(f"{wav.name:12} {label} {e:3}/{n:3}  {text}")
    await fixer.POOL.close()
    print(f"{label} CER {100 * e_tot / n_tot:5.1f}%（{e_tot}/{n_tot}）")


if __name__ == "__main__":
    if "--fixer" in sys.argv:
        asyncio.run(fixer_eval("--haas" in sys.argv, "--no-glossary" not in sys.argv))
    else:
        asyncio.run(main("--scribe" in sys.argv, "--haas" in sys.argv))
