#!/usr/bin/env bash
cd "$(dirname "$0")"
bash start.sh
result=$?
if [ "$result" -ne 0 ]; then read -r -p '실행 오류입니다. Enter를 누르면 닫습니다. ' _; fi
exit "$result"
