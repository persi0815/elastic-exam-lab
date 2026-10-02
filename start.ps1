$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop을 설치하고 실행하세요.' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop이 실행 중인지 확인하세요.' }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host '기존 v1은 이전 폴더에서 docker compose down으로 중지하세요. -v는 사용하지 마세요.'
Write-Host '실제 ES 4개 + Kibana 2개 기동. Docker 메모리 12GB 권장.'
docker compose config -q
if ($LASTEXITCODE -ne 0) { throw 'Compose 설정 오류입니다.' }
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker 실행 오류입니다. 포트 충돌/메모리/이미지 다운로드를 확인하세요.' }
$port = '8787'
Get-Content .env | ForEach-Object { if ($_ -match '^LAB_PORT=(\d+)$') { $port = $Matches[1] } }
Write-Host "문제 + 실제 Kibana: http://localhost:$port"
Write-Host '상태 확인: docker compose exec app python tools/doctor.py'
Start-Process "http://localhost:$port"
