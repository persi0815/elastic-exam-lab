# E — ECE Practice Exam 추가

2026-10-01, 사용자 제공 `ECE-Practice Exam.pdf`를 참고 자료로 사용해 E01–E10 한 회차만 추가했다. 문서의 시험 환경 안내는 이 작업에 대한 실행 지시로 취급하지 않았다.

기존 A–D 40문항과 기존 19개 fixture의 내용은 그대로다. 새 화면이나 별도 시험 플랫폼 없이 기존 세트 메뉴, 답안 보관, 180분 시험 모드와 실제 Kibana를 사용한다.

| 문항 | 내용 | 적용한 실습 차이 |
|---|---|---|
| E01 | 사용자·역할·Default 공간 전체 권한 | 기존 Kibana application privilege 사용 |
| E02 | 연도별 고유 저자 수 | 이미 keyword인 authors.uid 사용 |
| E03 | 블로그 분석기·멀티필드·재색인 | PDF처럼 date detection 유지, 문자열 keyword template 적용 |
| E04 | 웹 로그 정제·user_agent·geo_point | JSON 오류 수정, 실제 response 필드 매핑 |
| E05 | nested 저자 검색 | task5와 first_name을 본문 조건에 맞춰 사용, 합성 결과 28건 |
| E06 | category enrich | 누락된 category 포함 84건 보존, 원본 537건은 재현하지 않음 |
| E07 | CCR | cluster2 blogs 7건, 기존 원격 연결 사용 |
| E08 | 2분 rollover·Warm readonly·3분 Cold | 이름 통일, metrics-mappings 사전 준비 |
| E09 | repository·searchable snapshot | Docker path.repo 아래 실제 스냅샷 준비, 22건 검색 |
| E10 | 최근 2년·가산점·3번째 페이지·highlight | E 전용 blogs 날짜만 2025년으로 변경 |

새 자료는 web_traffic 24건, cluster2 blogs 7건, 스냅샷용 moreblogs 24건이다. 전체 fixture는 22개/1,585문서다. E 초기화 직후에는 moreblogs를 스냅샷에 보관하고 원본 인덱스를 제거하므로 21개/1,561문서이며, E09에서 마운트하면 moreblogs가 나타난다.

배포는 `docker compose up -d --build --no-deps app`으로 앱만 교체한다. seed version을 올리지 않아 현재 실습 상태를 자동 초기화하지 않는다. E 시작은 기존 UI의 `RESET LAB` 확인을 사용한다.

검증기는 실제 인증, 분석기 토큰, ingest 결과, 문서 보존, 복제 상태, 정책 연결과 검색 결과를 검사한다. 공식 채점기가 아니며 ILM의 실제 분 단위 전환 완료나 브라우저 자동완성 정확도를 보장하는 테스트는 아니다.

## 2026-10-01 검증 결과

- 단위·HTTP·기존 데이터 보존 테스트 87개 통과.
- 실제 Chrome으로 오프라인 UI 테스트 통과: E 세트 선택, 10문항, PDF 링크, 스냅샷 풀이 표시. API·iframe은 명시적 test double을 사용했다.
- 앱 컨테이너 재빌드 및 배포 완료. 카탈로그 5세트/50문항, PDF HTTP 200, 두 Kibana available 확인.
- 실제 Kibana Console 프록시로 E01–E10 참고 풀이 실행: 10/10 통과, 검증 항목 총 73/73 통과.
- 실제 Lab.prepare_e()를 임시 UUID 자원에 적용하고, Verify 검증기는 동일한 자원 이름 변환 어댑터로 실행했다. 현재 세트를 유지하므로 E의 /api/check HTTP 엔드포인트 전체 흐름과 전체 환경 reset은 실행하지 않았다. 네이티브 요청 수집은 현재 D 문항에 별도 테스트 세션으로 연결해 확인했다.
- 테스트 임시 인덱스·정책·pipeline·사용자·repository·snapshot을 정리했고 남은 임시 자원은 없다.
- 배포 전후 기존 24개 사용자 인덱스의 UUID·문서 수·_source SHA-256이 모두 동일하다. 현재 세트 D, generation 1 유지.
- 실제 화면에서 E 선택 시 기존 초기화 확인창이 표시되는 것을 확인하고 취소했다. 실제 Kibana Console 화면도 정상 표시된다.

다시 실행하려면 `docker compose exec -T app python tests/live_smoke_e.py --run-isolated`를 사용한다. 보고서는 `/opt/lab/state/e-smoke-report.json`에 저장한다. 이 검증은 기존 세트의 풀이를 초기화하지 않는다.

구현 참고: [Kibana 권한](https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/kibana-privileges), [공유 파일 시스템 repository](https://www.elastic.co/docs/reference/elasticsearch/configuration-reference/fs-repository-settings), [스냅샷 mount API](https://www.elastic.co/guide/en/elasticsearch/reference/current/searchable-snapshots-api-mount-snapshot.html).


## metrics-mappings 누락 수정

E 전용 초기화만 component template을 준비했기 때문에 다른 세트로 환경을 초기화하면 `metrics-mappings`가 없어졌다. 현재 C 세트에서 누락을 확인하고 cluster1에 공통 준비물만 추가했다. 기존 인덱스와 시험 상태는 초기화하지 않았다.

`ensure_metrics_component()`를 공통 초기화와 저장된 환경 재사용 경로에 연결했다. 기존 template이 있으면 유지하며, 404일 때만 `create=true`로 생성하여 사용자 변경을 덮어쓰지 않는다. E의 snapshot 준비는 계속 E 전용 경로에만 남는다.

실제 cluster1에서 component 조회와 저장 없는 index template simulation이 정상임을 확인했다.

전체 회귀 테스트 96개 통과(이번 누락·보존·동시 생성·C 초기화 관련 9개 추가). [Component template API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-cluster-put-component-template)의 생성 전용 옵션을 사용한다.
