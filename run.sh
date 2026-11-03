#!/bin/zsh
# となりを起動する（手元の Mac だけで動く。止めるときは Ctrl+C）。ふだんは ~/Applications/Tonari.app を開けばよい。
set -e
cd "$(dirname "$0")"
[ -x stt/bin/stt-helper ] || ./stt/build.sh
PORT=${TONARI_PORT:-4880}
URL="http://127.0.0.1:$PORT/"
(
  until curl -s -o /dev/null -H "X-Tonari: 1" "${URL}api/state"; do sleep 0.5; done
  if [ -d "/Applications/Google Chrome.app" ]; then open -a "Google Chrome" "$URL"; else open "$URL"; fi
) &
exec uv run --quiet uvicorn server.app:app --host 127.0.0.1 --port "$PORT"
