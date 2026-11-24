#!/bin/sh
cd "$(dirname "$0")"
PORT=${PORT:-4000}
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then
  echo "이미 실행 중 (pid $(cat server.pid)) http://127.0.0.1:$PORT"
  exit 0
fi
PORT=$PORT nohup node server.mjs >> server.log 2>&1 &
echo $! > server.pid
echo "시작 (pid $!) http://127.0.0.1:$PORT"
