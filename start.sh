#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v docker >/dev/null 2>&1; then
  echo 'Docker Desktop 또는 Docker Engine + Compose를 설치하고 실행하세요.' >&2; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo 'Docker Desktop이 실행되지 않았습니다. 먼저 켜 주세요.' >&2; exit 1
fi
docker compose version >/dev/null
[ -f .env ] || cp .env.example .env
PORT=$(sed -n 's/^LAB_PORT=//p' .env | head -1 | tr -d '\r');PORT=${PORT:-8787}
if command -v curl >/dev/null 2>&1; then
  old=$(curl -fsS --max-time 2 "http://localhost:$PORT/api/catalog" 2>/dev/null || true)
  if printf '%s' "$old" | grep -q '"version": "1.'; then
    echo '이전 v1이 같은 포트를 사용 중입니다. 이전 폴더에서 docker compose down 후 다시 실행하세요.' >&2
    echo 'down에 -v를 붙이지 마세요. 기존 볼륨/데이터를 보존합니다.' >&2; exit 1
  fi
fi
printf '\n실제 Elasticsearch 4개 + Kibana 2개를 시작합니다. Docker 메모리 12GB 할당을 권장합니다.\n'
docker compose config -q
docker compose up -d --build
printf '\n문제 + 실제 Kibana: http://localhost:%s\n' "$PORT"
printf '첫 시작은 이미지 다운로드/초기화 때문에 몇 분이 걸릴 수 있습니다.\n'
printf '상태 확인: docker compose exec app python tools/doctor.py\n'
case "$(uname -s)" in
  Darwin) open "http://localhost:$PORT" ;;
  Linux) if command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:$PORT" >/dev/null 2>&1 || true; fi ;;
esac
