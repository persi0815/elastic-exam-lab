#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Stop this project's containers, retaining all named volumes.
docker compose down
