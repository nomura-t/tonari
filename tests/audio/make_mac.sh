#!/bin/bash
# 試しの音声6本を Mac の say で作る（16kHz の wav）。macOS の声（Kyoko・Eddy）で作った音声は、macOS の使用許諾で
# 公開や再配布が認められていないので、リポジトリには入れず手元で作る。texts.txt の1行目から順に -1〜-3。
# ほかの PC では、自分で読み上げて録った wav を「名前-番号.wav」（番号は texts.txt の行）で置けば tests/stt_eval.py で測れる。
set -e
cd "$(dirname "$0")"
i=0
while IFS= read -r t; do
  [ -n "$t" ] || continue
  i=$((i + 1))
  say -v Kyoko --file-format=WAVE --data-format=LEI16@16000 -o "Kyoko-$i.wav" "$t"
  say -v "Eddy (日本語（日本）)" --file-format=WAVE --data-format=LEI16@16000 -o "Eddy-$i.wav" "$t"
done < texts.txt
ls *.wav
