# 출처와 합성 데이터

A: sources/recall-2026-02-26.pdf 10문제.
B: sources/recall-collection.pdf 4/14 상세회고를 중심으로10문제.
C: 같은 모음집의 과거 유형을 재구성한10문제. 하나의 원본 회차가 아님.
D: sources/recall-2026-09-19.md 사용자 제공회고 + 명시된 4월 참조로10문제.

모든 문항의 source/notes/reconstructed 필드가 출처와 보완 내용을 나타냅니다.
원본 시험 데이터는 제공되지 않았습니다. 모든 문서는 코드에서 새로 만든 합성 데이터입니다.

생성 순서(개발자용):

```bash
python3 data/generate_v2.py
python3 data/build_catalog.py
python3 data/extend_catalog.py
```

fixtures.json: 19개 사용자 인덱스,1,530문서. region alias, ece-lab-control, Kibana 시스템 인덱스는 미포함.
article480 + regions3 + ingest-logs0을 이전16indices/1047docs에 추가.

D의 가정은 SET_D_DECISIONS.md 참고. ref API 검증은 실습 데이터에 대한 조건 확인으로 공식 채점과 다릅니다.
벡터는 모델 임베딩이 아니라 결정적 수치 샘플입니다. title의 to 검색357건도 합성 데이터에서만 재현하는 기준입니다.
