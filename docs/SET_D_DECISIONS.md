# D세트: 원문과 재현용 규격 구분

원문: `sources/recall-2026-09-19.md`. 다른 날짜 문제를 참조하는 부분은 `sources/recall-collection.pdf` 1~4쪽과 대조했습니다.

| 문항 | 원문에서 확인되는 것 | 실습에서 지정한 것 / 불확실성 |
|---|---|---|
| D01 | article, [10,3,5,4,1,2], kNN, 10건, tags term, title/category | vector.cosine 경로와 cosine metric; term을 리터럴 값으로 해석; 일반 _source 필터 또는 fields 반환 허용 |
| D02 | article.region과 region_id를 매칭, region_info에 세 필드 추가 | region/regions 혼용은 regions + region alias로 제공. 결과 index task2는 실습 선택 |
| D03 | task3, text/keyword only, to/the/and, 357→0 | 합성 article 480건 중357건을 to 포함 title로 구성. 나머지 매핑에 벡터를 포함 |
| D04 | 4/14 Task6과 동일 | 정책 이름 task6, cluster2, listings2 등을 참조 원문 그대로 유지 |
| D05 | Data stream이라고 적으면서 4/14 Task7 참조 | PDF Task7은 집계라 일치하지 않음. 주제를 따라 Task8 활용. template task5, pattern mymetrics-*-*, stream mymetrics-system-prod 명시 |
| D06 | 4/14 Task5와 동일 | food-ingredients/name/brand/manufacturer/potato chips 유지. article로 임의 변경하지 않음 |
| D07 | kubernetes 점수O, devops 점수X, featured 선택 가산점, 20번부터5개, 날짜 정렬 | 20번째를 포함한다고 해석하여 from19; 정렬방향desc 선택. 둘 모두 원문에서 확정 불가 |
| D08 | 4/14 Task10과 동일 | movie_data의 me/my 및 romantic comedy 조건 유지 |
| D09 | 기존 빈 인덱스 보존, task9 기본pipeline, grok, convert integer, raw_time→@timestamp | 인덱스 ingest-logs, 원문 response_stauts 오타와 ?? 패턴 보완, ISO8601 샘플 제공. duration_ms의 mapping까지 integer는 실습에서 추가해 명시 |
| D10 | 4/14 Task7 유형, AVG(a),MAX(b) | article, @timestamp,2012년월별로 지정. 원래 세부필드/데이터는 회고만으로 확정할 수 없음 |

원문의 ‘빈 인덱스라 _simulate가 동작하지 않는다’는 설명을 기술적 사실로 채택하지 않았습니다. 인덱스가 비어 있어도 docs 배열에 샘플 _source를 직접 주면 processor 시뮬레이션은 가능합니다. 다만 default pipeline과 실제 매핑까지 검증하려면 실제 색인 요청도 실행해야 합니다. 이 점을 D09 보완 사항에 표시했습니다.

이 자료는 원본 문제은행이 아닌 회고를 재현 가능한 연습으로 만든 것입니다. 출제 빈도·배점·합격 가능성을 보증하지 않습니다.
