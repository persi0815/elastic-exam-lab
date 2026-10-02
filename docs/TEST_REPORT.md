# v2 검증 보고서

## 수행한 검증

**단위 및 HTTP 계약 테스트: 67개 통과.**

```bash
python -m unittest discover -s tests -p 'test*.py' -v
```

기존 42개: 콘솔 파서/중복키/주석/삼중 따옴표/bulk/다중요청, 데이터 경계값, 요청 클러스터 라우팅, 출처, 명시적 초기화 확인, 실습 소유권 등.

추가 25개: 기사480건/6차원/0벡터없음/to357건/참조키, 빈 ingest 인덱스, 날짜와 featured 조건, D세트참조불일치표시, 실제Kibana프록시설정, 코드구조, HTTP경로/압축/header/cookie전달/실행기록수집 등.

프록시 HTTP 테스트는 루프백의 **가짜 upstream 서버**를 명시적으로 사용했습니다. 요청/응답 전달 검증이지 Elasticsearch의 검색 동작 검증은 아닙니다.

**Chromium 문제 화면 DOM 테스트: 통과.**

```bash
python tests/ui_smoke.py
```

4세트/문항이동/클러스터전환/iframe유지/쿠키구성/주석표시/보관코드직렬화와복원/실행기록가져오기/검증표시/데이터셋/힌트와풀이/시험모드잠금/초기화확인/내보내기/패널접기/4가지데스크톱크기를 확인했습니다. 페이지 JavaScript 오류는 없었습니다.

이 브라우저 테스트는 오프라인이며 **API, localStorage, 쿠키 저장소, iframe은 test double**입니다. 브라우저 인증 정책이나 실제 Kibana Monaco/자동완성/검색실행을 검증한 것은 아닙니다. 실제 네트워크 쿠키 전달은 앞의 별도 HTTP 계약 테스트 범위입니다.

**추가 정적 검사: 통과.**

- `node --check web/app.js` / legacy-app.js
- Python 전체 모듈 py_compile
- `bash -n start.sh start.command stop.sh infra/setup.sh`
- Compose/Kibana YAML 구문 및 서비스 참조, loopback포트, basePath/authentication/encryptionkey구조
- 40개 예시 스크립트 콘솔 파서 통과

## 수행하지 못한 검증

제작 환경에 Docker가 없고 외부 프로그램 다운로드가 불가능했습니다.

따라서 **실제 Elasticsearch 9.3.8 네 노드와 실제 Kibana 두 개를 동시에 실행한 테스트, 모든 답안에 대한 실제 엔진 통합 테스트, 실제 Kibana의 브라우저 자동완성/인증/입력 테스트는 수행하지 못했습니다.**

Docker Compose의 실제 `docker compose config`도 제작 환경에서는 실행하지 못했으며, YAML 정적 검사만 수행했습니다. start.sh에서 사용자의 Docker Compose로 실제 검증하도록 했습니다.

## 로컬 통합 검증

```bash
docker compose exec app python tools/doctor.py
```

위 명령은 실제 클러스터 준비 상태 및 두 Kibana의 상태 API를 확인하며 데이터를 변경하지 않습니다.

```bash
# 아래 명령은 두 실습 클러스터의 데이터를 초기화합니다.
docker compose exec app python tests/live_smoke.py --sets D --confirm-reset
```

이 스크립트는 진짜 Kibana Console API를 통해 예시 요청을 보내고 실제 ES 결과 및 요청캡처를 확인합니다. 실제 브라우저 키보드 입력까지 테스트하는 스크립트는 아닙니다.

보고서가 없는데 실제 통합 테스트를 완료했다고 간주하지 마세요. 실패 시 `live-test-report.json`에 어떤 요청/조건이 실패했는지 기록됩니다.

`shell-preview.png`는 Kibana 미연결 상태의 문제 화면 미리보기입니다. 실제 Kibana 실행 화면을 가장한 이미지는 포함하지 않았습니다.
