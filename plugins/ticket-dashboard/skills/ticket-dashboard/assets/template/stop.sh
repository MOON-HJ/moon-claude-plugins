#!/bin/sh
cd "$(dirname "$0")"
[ -f server.pid ] && kill "$(cat server.pid)" 2>/dev/null && echo "중지" || echo "실행 중 아님"
rm -f server.pid
