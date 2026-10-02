# v2 구조

Browser / localhost:8787
- 문제 화면: web/index.html, app.js, style.css
- 실제 Console iframe: /kibana1/app/dev_tools#/console 또는 /kibana2/...

Python app
- /api/*: 문제, 저장된 요청, 검증, 실습 초기화
- /kibana1/* → 실제 kibana1:5601
- /kibana2/* → 실제 kibana2:5601
- 프록시는 문자열 편집/자동완성/ES 실행을 흉내 내지 않음
- Console의 /api/console/proxy 요청에서 문항 쿠키와 method/path/body/status를 관찰해 이력 저장
- 압축된 정적 번들, CSP, 인증 쿠키, HTTP 응답은 그대로 전달

Kibana
- server.basePath + rewriteBasePath로 동일 출처의 경로 분리
- 각각 cluster1 / cluster2에 연결
- 익명 제공자는 전용 로컬 실습 관리자 자격증명을 사용
- 건강 상태 확인용 HTTP Basic scheme도 명시

Elasticsearch
- 9.3.8, 네 노드, 두 클러스터, 각자 데이터/스냅샷 볼륨
- cluster1 node1/node2/node3, node2 warm, node3 cold 역할 추가
- cluster2 server4, transport 9304
- 데이터/매핑은 data/fixtures.json, 문제/검증용 예시는 data/catalog.json

저장
- native Console 초안: Kibana 자체 기능
- 문항별 최종 답안: 브라우저 localStorage
- 실행 기록: appstate 볼륨 SQLite
- 상태/정책: 실제 ES의 인덱스/클러스터 상태

브라우저 여러 탭이 같은 추적 쿠키를 공유하므로 한 시험 탭을 권장합니다. 별도 Kibana 포트를 통해 우회한 요청은 캡처되지 않으며 최종 답안 칸으로 전달할 수 있습니다.

실습 보조 콘솔 /legacy.html은 기존 파서를 이용한 진단용 별도 화면이며 native Kibana로 표시하지 않습니다.
