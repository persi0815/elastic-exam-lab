# F 세트 구현 및 검증

- A–E 50문항 및 기존 fixture 22개·1585문서의 정규화 SHA256 보존 확인.
- F 10문항, 독립 준비 데이터 11개·133문서. F를 명시적으로 선택한 경우에만 추가 데이터를 적재. seed_version=2 유지.
- Semantic: pinned MiniLM 실제 384차원 임베딩, mapping/reindex, kNN pre-filter, 두 후보 단계 필터와 RRF. 모델 생성용 Python 의존성과 90MB 모델은 Docker에 포함하지 않음.
- ES|QL: 실제 POST /_query 결과의 열·값·순서 비교. Lookup 가격 누락과 무료 상품, UTC 날짜 경계, multivalue 중복을 포함.
- Streams: 실제 Kibana 9.3.8 classic Streams processing, DSL 7d rollover, failure store 3d. Console의 kbn: 경로는 고정 Kibana API로 전달하고 실제 응답·실행 기록을 보관.
- 단위 테스트 161개 통과. 독립 브라우저 화면 검사 통과.
- 배포 전 실제 Docker 서비스 통합 테스트: 10/10문항, 87/87조건 통과. 고유 UUID 임시 자원만 사용했고 데이터 스트림·인덱스·관리 템플릿·파이프라인 정리 확인.
- 통합 테스트는 현재 활성 시험을 변경하지 않기 위해 namespaced resource adapter로 Verify를 호출함. F로 전환하여 /api/check를 호출하는 전체 사용자 흐름은 실행하지 않음. 기본 화면의 세트 선택과 요구사항 표시는 별도 검사.

- 배포 후 실제 앱 통합 테스트도 10/10문항·87/87조건 통과. 현재 활성 B 세트 generation 8 유지. 최초 사용자 인덱스 24개의 UUID·문서 수·문서 원문 해시가 모두 동일함. 작업 중 추가된 task2/task3/task4는 정리하지 않고 유지.
