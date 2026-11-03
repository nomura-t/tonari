#!/bin/zsh
# 3本の opus を同時に起動して、1秒以内に問いを投げたときの応答時間と失敗を見る
for i in 1 2 3; do
  ( s=$(date +%s.%N); env -u ANTHROPIC_API_KEY -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 claude -p --safe-mode --tools "" --no-session-persistence --model opus --output-format json "「上位概念」と「下位概念」の違いを1文で。" > out$i.json 2> err$i.txt; e=$(date +%s.%N); echo "run$i exit=$? sec=$(( e - s ))" ) &
done
wait
for i in 1 2 3; do python3 -c "import json,sys; d=json.load(open('out$i.json')); print($i, d.get('is_error'), d.get('duration_ms'), d.get('modelUsage') and list(d['modelUsage'].keys()), (d.get('result') or '')[:80])" 2>&1; cat err$i.txt | head -3; done
