# ECE Practice Lab v2 — 실제 Kibana Console + Elastic 9.x 세트

**문제는 왼쪽, 실제 Kibana Dev Tools Console은 오른쪽에 표시하는 로컬 실습 환경입니다.**
기존 자체 제작 편집기를 기본 화면에서 제거했습니다. 편집·자동완성·요청 실행·응답 표시는 Docker에서 실행되는 Kibana 자체가 담당합니다.

기존 A–E 50문제를 유지하고, 직접 제작한 Elastic 9.x의 F 10문제를 추가했습니다. 모두 6세트·60문제입니다. F는 Semantic Search 3문항, ES|QL 4문항, 실제 Kibana Classic Streams 3문항입니다. 세트 선택 메뉴에서 시작하며 기존과 동일하게 RESET LAB 확인을 거쳐 초기화합니다.
F의 Semantic Search는 실제 MiniLM 모델로 미리 생성한 384차원 문서·질의 벡터를 제공합니다. 현재 Docker의 ML 기능을 켜거나 외부 inference 계정을 추가할 필요가 없습니다. `semantic_text` 자동 inference 설정은 이 세트의 범위에 포함하지 않습니다. F의 새 데이터는 F를 명시적으로 선택할 때만 준비하므로 앱 배포만으로 진행 중인 시험을 초기화하지 않습니다.
공식 시험 환경·원본 데이터·공식 채점기가 아니며, 누락된 조건과 실습용 가정은 문항별로 공개합니다.

## 1. 기존 버전을 사용 중이라면

1. 기존 화면에서 중요한 답안을 내보내세요.
2. **기존 v1 폴더에서** 다음 명령으로 컨테이너만 중지합니다.

```bash
docker compose down
```

**`-v`는 붙이지 마세요. 기존 볼륨을 삭제하지 않습니다.**

3. 이 ZIP은 **새 폴더 `elastic-exam-lab-v2`에 풀어 사용하세요.** 이전 파일 위에 덮어쓰지 않습니다.
4. v2의 Compose 프로젝트 이름과 볼륨은 v1과 다릅니다. 8.x 데이터 볼륨을 9.x에 직접 붙이지 않습니다.
5. 새 화면의 사용 안내 → 답안 가져오기로 v1 답안 JSON을 가져올 수 있습니다. 코드만 가져오며 클러스터 상태는 이전하지 않습니다.

## 2. 시작

Docker Desktop 또는 Docker Engine + Compose가 실행되어 있어야 합니다.
실습 기본 구성은 Elasticsearch 4개 + Kibana 2개입니다. **이 패키지의 자원 배분 기준으로 Docker 메모리 12GB 이상, CPU 4개 이상을 권장**합니다. 공식 시험 하드웨어 요구가 아니라 이 로컬 구성의 권장값입니다.
첫 실행은 공식 이미지 다운로드 때문에 인터넷과 여유 디스크가 필요합니다. 브라우저 편집기용 CDN 다운로드는 없습니다.

ZIP을 푼 후 **compose.yaml이 있는 폴더에서**:

```bash
bash start.sh
```

또는:

```bash
docker compose up -d --build
```

브라우저:

```text
http://localhost:8787
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Mac에서 스크립트 실행 권한 문제가 나면 더블클릭 대신 `bash start.sh`를 사용합니다.
**HTML 파일을 직접 열어서는 실행되지 않습니다.**

첫 기동 순서는 인증서 → Elasticsearch → 데이터 적재 → Kibana입니다. 문제 화면이 먼저 보여도 Kibana가 초기화 중일 수 있습니다. 데이터가 준비되고 오른쪽 실제 Console이 나타날 때까지 기다리세요.

## 3. 실제 Kibana 직접 열기

문제와 나란히 표시하는 대신 전체 화면도 사용할 수 있습니다. 오른쪽 ‘별도 창’을 누르면 됩니다.

```text
cluster1: http://localhost:8787/kibana1/app/dev_tools#/console
cluster2: http://localhost:8787/kibana2/app/dev_tools#/console
```

모두 **실제 Kibana**입니다. 기본 화면은 iframe으로 위 주소를 표시합니다.
로컬 연습 편의를 위해 Kibana의 익명 인증 제공자가 실습 관리자 계정을 사용합니다. 로그인 화면을 거치지 않도록 구성했습니다.

프록시를 거치지 않는 진단용 직접 주소도 있습니다.

```text
http://localhost:15601/kibana1/app/dev_tools#/console
http://localhost:15602/kibana2/app/dev_tools#/console
```

직접 포트로 접속하면 요청 자동 수집을 우회합니다. 그 경우 최종 스크립트를 ‘최종 답안 보관’에 붙여 넣은 뒤 검증하세요.

## 4. Console과 답안 저장

오른쪽에서 일반 Kibana처럼 작성합니다.

```http
GET article/_mapping

GET article/_search
{
  "size": 10,
  "_source": ["title", "category"],
  "query": {
    "knn": {
      "field": "vector.cosine",
      "query_vector": [10, 3, 5, 4, 1, 2],
      "k": 10,
      "num_candidates": 100,
      "filter": {
        "term": {"tags": "term"}
      }
    }
  }
}
```

Kibana의 실행 버튼 또는 Ctrl/Cmd + Enter로 실행합니다. Ctrl/Cmd + I는 정렬입니다. 자동완성·괄호 처리·여러 요청·주석·응답 JSON은 Kibana 기능을 그대로 사용합니다.

- 문제를 바꿔도 Console 작업장을 강제로 지우지 않습니다.
- 프록시를 통과한 실제 Console 실행 요청은 **현재 선택된 문항**에 연결됩니다.
- 하단 **문항별 답안·실행 기록**에서 요청 기록과 검증 결과를 확인합니다.
- **최종 답안 보관**은 문항별 스크립트 저장용 일반 텍스트 칸입니다. 실행용 IDE가 아닙니다.
- 보관 답안에 코드가 있으면 검증은 그 코드의 검색 요청을 우선합니다. 비워 두면 수집된 마지막 검색 요청을 사용합니다.
- 관리 작업 문제는 Elasticsearch의 실제 매핑·정책·데이터 상태를 확인합니다. 보관 답안만 작성하고 실행하지 않으면 완료되지 않습니다.
- 보관 답안은 브라우저 localStorage, 실행 기록은 실습 서버 SQLite에 저장됩니다.
- 답안 내보내기는 문항별 보관 코드와 현재 문항의 수집 기록을 내보냅니다. **Kibana 편집기에 아직 실행하지 않은 내용은 자동 추출하지 않으므로 중요한 초안은 보관 칸에 붙여 넣으세요.**
- 문제 선택과 실행의 연결은 쿠키를 이용합니다. 여러 시험 탭을 동시에 쓰면 마지막으로 선택한 문항 기준이 될 수 있으므로 한 시험 탭을 권장합니다.

180분 시험 모드는 힌트·예시 풀이·검증을 잠그는 연습 기능입니다. 공식 감독/보안 기능은 아닙니다.

## 5. 세트 D — 2026.09.19 회고

| 번호 | 실습 유형 | 준비 데이터 / 결과 |
|---|---|---|
| 1 | kNN + 내부 filter + 결과 필드 제한 | article, vector.cosine 6차원, tags=term, 10건 |
| 2 | 지역 Enrich + Reindex | article + regions → task2.region_info |
| 3 | Analyzer / Mapping / Reindex | article → task3; to/the/and 제거; 원본 to 357건 |
| 4 | SLM + Repository | 4월 Task6 조건 유지, cluster2의 listings2 |
| 5 | Data Stream + Template | 참조 번호 불일치 공개; 4월 Task8 주제로 구성 |
| 6 | Multi-field Phrase | 4월 Task5 조건 유지: food-ingredients |
| 7 | must/filter/should + Pagination | article; 실습에서 from:19, date_time desc 지정 |
| 8 | 검색 OR + 가산점 | 4월 Task10 조건 유지: movie_data |
| 9 | Grok / Convert / Date / Default Pipeline | 빈 ingest-logs, task9 pipeline; UUID 유지 검증 |
| 10 | 월별 AVG(a), MAX(b) | article, 2012년, @timestamp; 실습 규격 공개 |

회고가 9.X라고만 적었으므로 패키지 버전은 **Elasticsearch/Kibana 9.3.8로 맞춘 실습 선택**입니다. 실제 응시 버전의 정확한 패치 번호를 확인했다는 뜻은 아닙니다.

문제·데이터·검증을 만들기 위해 채운 항목은 [SET_D_DECISIONS.md](docs/SET_D_DECISIONS.md)에 정리했습니다.

### 중요한 원문 불일치

- D05는 ‘Data stream = 4/14 Task7’이라고 적혀 있지만 PDF의 Task7은 집계, Task8은 Data Stream입니다. 주제를 따라 Task8을 참조했음을 UI에 명시했습니다.
- D07의 ‘20번 문서부터’와 날짜 정렬 방향은 애매합니다. 실습에서 **20번째 포함 → from:19**, **desc**로 정했습니다. 실제 기출 정답이라고 주장하지 않습니다.
- D09의 `response_stauts`, `%{??:duration_ms}`는 불완전합니다. 실습 패턴과 ISO8601 샘플을 별도로 제공했습니다.
- ‘빈 인덱스라 _simulate가 안 된다’는 회고의 설명은 원문에 보존했습니다. **실제 `_simulate`는 docs에 샘플을 제공하면 대상 인덱스가 비어 있어도 실행할 수 있습니다.** 실습 예시에는 이 별도 검증 방법을 넣었습니다.
- ‘대부분 article 사용’만으로 D06/D08까지 바꾸지 않았습니다. 명시적으로 참조한 4월 문제의 인덱스를 유지합니다.

## E 세트 — ECE Practice Exam 추가

사용자 제공 PDF의 10개 문항을 원래 순서대로 추가했습니다. 기존 UI·180분 시험 모드·문항별 답안 보관·실제 Kibana Console을 사용합니다. 권한, 집계, 분석기, 웹 로그, nested, enrich, CCR, ILM, searchable snapshot, 검색/페이징을 실습합니다.

E 초기화에서만 blogs 날짜를 2025년으로 바꾸고 moreblogs_snapshot을 준비합니다. metrics-mappings component는 모든 세트의 공통 준비물이며, 초기화와 앱 재시작 때 없으면 추가하고 기존 내용을 보존합니다. 원본 PDF의 필드·경로·이름 불일치는 문항별 메모에 표시했습니다. 배포는 앱만 재빌드하며 기존 Elasticsearch 데이터·Kibana·볼륨을 유지합니다.

추가 fixture는 web_traffic 24건, cluster2 blogs 7건, moreblogs 24건입니다. 전체 준비 자료는 22개 fixture/1,585문서이며, E 초기화 직후 moreblogs는 스냅샷 안에 있으므로 실제 일반 인덱스는 21개/1,561문서입니다. 기존 A–D fixture 19개/1,530문서는 유지했습니다.

검증 및 차이: [SET_E_REPORT.md](docs/SET_E_REPORT.md).

## 6. 데이터

기존 A–D의 기본 자료는 **19개 인덱스, 합성 문서 1,530건**입니다. E 자료까지 포함한 준비 자료는 위 추가 설명을 참조하세요. region은 regions의 alias이므로 인덱스 수에 따로 포함하지 않습니다. Kibana 시스템 인덱스와 실습 제어 인덱스도 이 19개에서 제외합니다.

기존 16개 인덱스/1,047건에 다음을 추가했습니다.

- article 480건: 6차원 벡터, title, body, article_id, tags, featured, region, category, date_time, @timestamp, a, b.
- regions 3건: region_id, region_name, description.
- ingest-logs 0건: 인덱스만 존재하고 필드 매핑과 문서는 없는 정상 시작 상태.

article은 title에 `to`가 토큰으로 존재하는 문서를 정확히 357개 넣었습니다. 숫자 벡터는 수치 검색 재현용이며 학습 모델로 만든 의미 임베딩은 아닙니다. 문장 내용과 벡터 의미가 자연어 수준으로 일치한다고 가정하지 마세요.

기존 데이터셋은 food-ingredients, inspections, flights, movie_data, stock-prices, earthquakes, magnitude_type, listings, listings2, city_population, city_populations, blogs, categories 등입니다. 자세한 목록은 화면의 데이터셋 메뉴에서 확인합니다.

## 7. 초기화와 중지

세트 변경 또는 환경 초기화는 **두 전용 실습 클러스터의 사용자 데이터·설정 결과를 삭제하고 다시 적재합니다.** 문항별 보관 코드는 유지하지만 검증 결과는 지웁니다. 원본 index를 수정하는 문제 때문에 세트별 초기화를 권장합니다.

중지하면서 볼륨 유지:

```bash
bash stop.sh
```

컨테이너를 다시 실행하면 기존 데이터와 상태를 재사용합니다. 브라우저 저장 데이터도 같은 origin이면 유지됩니다.

## 8. 문제 발생 시

```bash
docker compose ps
docker compose logs --tail=100 kibana1 kibana2 app
docker compose exec app python tools/doctor.py
```

| 증상 | 먼저 확인할 것 |
|---|---|
| 포트가 이미 사용 중 | 이전 v1 폴더에서 docker compose down. 다른 서비스를 종료하지 말고 충돌 포트를 확인 |
| 오른쪽 준비 화면이 계속됨 | Kibana 로그, 메모리, ES 인증, doctor.py 출력 |
| 서버는 준비됐지만 Console 흰 화면 | 새로고침 ↻ / 별도 창. 프록시가 아닌 진단용 직접 주소도 비교 |
| Kibana authentication failed | ELASTIC_PASSWORD/KIBANA_PASSWORD를 생성 후 변경했는지. 기존 ES 비밀번호는 env 변경만으로 바뀌지 않음 |
| OOMKilled 또는 Exit 137 | Docker 메모리 부족. ES 4개, Kibana 2개가 동시에 실행됨 |
| 502 후 요청이 안 끝난 것 같음 | ES의 _tasks / 결과 상태 확인. 동일 변경 요청을 무조건 반복하지 않기 |
| native 실행 기록이 없음 | localhost:8787 프록시 경로로 실행했는지. 최종 답안 칸에 쿼리를 붙여 넣어 검증 가능 |
| template/pipeline/index already exists | 재실행 충돌 여부 확인. 실습 초기화 후 다시 풀거나 해당 리소스만 의도적으로 수정 |

Kibana만 재시작:

```bash
docker compose restart kibana1 kibana2
```

텍스트 기반 보조 콘솔은 `/legacy.html`에 유지했습니다. 기본 화면과 달리 **Kibana가 아닌 진단용 자체 콘솔**입니다.

## 9. 검증 범위와 실제 통합 테스트

기존 v2 제작 당시에는 Docker 통합 테스트를 실행하지 못했습니다. **이번 E 추가 작업은 현재 실행 중인 Docker에서 실제 Kibana/ES 통합 검증 10/10, 단위·HTTP 테스트 87개를 통과했습니다.** 기존 인덱스와 현재 D 세트 상태를 보존했습니다. 세부 범위는 [SET_E_REPORT.md](docs/SET_E_REPORT.md)를 참조하세요. 브라우저 자동완성이나 ILM 시간 전환 전체를 검사한 것은 아닙니다.

수행한 검증:

- Python 단위/HTTP 계약 테스트 67개 통과: 기존 파서, 데이터, 요구 조건, 프록시 전달, gzip, 쿠키, 요청 수집.
- 실제 Chromium의 **오프라인 문제 화면 DOM 테스트** 통과. iframe/API/storage/cookie는 명시적인 test double입니다.
- JS 구문, Python 컴파일, 셸 구문, Compose/Kibana YAML 정적 구조 검사.

상세: [TEST_REPORT.md](docs/TEST_REPORT.md).

로컬에서 진짜 Kibana의 Console API를 통해 D세트 예시 전체를 실행하고 실제 ES 결과를 검증하려면:

```bash
# 주의: 두 실습 클러스터의 풀이 데이터를 초기화하고 예시 답안을 실행합니다.
docker compose exec app python tests/live_smoke.py --sets D --confirm-reset
```

A/B/C/D 모두:

```bash
docker compose exec app python tests/live_smoke.py --sets ABCD --confirm-reset
```

보고서 복사:

```bash
docker compose cp app:/opt/lab/live-test-report.json ./live-test-report.json
```

테스트 후 연습하려면 화면에서 환경 초기화를 한 번 하세요. 이 스크립트는 브라우저 입력 동작까지 검사하지는 않습니다.

개발용 테스트:

```bash
python3 -m unittest discover -s tests -p 'test*.py' -v
node --check web/app.js
# optional: playwright/Chromium 설치 환경에서만
python3 tests/ui_smoke.py
```

## 10. 보안 및 범위

로컬 전용입니다. 모든 공개 포트는 127.0.0.1에 바인딩합니다. 익명 사용자가 실습 관리자 권한을 갖도록 설정했으므로 0.0.0.0으로 포트를 공개하거나 터널로 노출하지 마세요. 업무용 클러스터에 연결하거나 인증서/비밀번호를 재사용하지 마세요.

고정된 전용 cluster_name과 소유권 마커를 확인한 뒤 초기화합니다. 이 보호가 모든 위험한 Elasticsearch 요청을 막는 보안 샌드박스는 아닙니다. 작업자는 실습 관리자 권한을 갖습니다.

trial 라이선스로 CCR 등을 연습합니다. 기간 만료 후 해당 기능은 사용 조건에 따라 제한될 수 있습니다. Docker 이미지/Elastic 라이선스는 해당 배포자의 조건을 따릅니다.

## 공식 구현 참고

- Kibana Console: https://www.elastic.co/docs/explore-analyze/query-filter/tools/console
- Kibana Docker: https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-kibana-with-docker
- Kibana anonymous/HTTP authentication: https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/kibana-authentication
- Kibana basePath / embedding headers: https://www.elastic.co/docs/reference/kibana/configuration-reference/general-settings
- kNN query: https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-knn-query
- Ingest simulate: https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-ingest-simulate

공식 문서는 구현 동작을 확인하는 근거이고, D세트의 기출 사실은 사용자 제공 회고에 근거합니다.
