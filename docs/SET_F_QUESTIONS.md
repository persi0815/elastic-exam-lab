# F · Elastic 9.x 모의 시험

180분 · 10문항 · cluster1 · 직접 제작한 예상 실습 문제

Semantic Search 3문항, ES|QL 4문항, 실제 Kibana Classic Streams 3문항으로 구성합니다. 기존 A–E 50문항은 유지됩니다.

문서와 질의의 384차원 벡터는 실제 MiniLM 모델로 사전 생성했습니다. 외부 API 계정이나 ML 노드가 필요하지 않습니다. semantic_text 자동 inference 설정은 포함하지 않습니다.

새 세트 선택은 기존 실습 데이터를 초기화하므로 현재 시험을 마친 뒤 F를 선택하세요. 앱 배포 자체는 시험 데이터를 초기화하지 않습니다.

## F01 · 사전 계산한 embedding을 검색 가능한 벡터로 색인

대상: f-semantic-source

1. f-semantic-source의 32건을 새 f-semantic-target으로 재색인하고 모든 문서 ID와 필드를 보존한다.
2. embedding을 dims:384, index:true, similarity:cosine인 dense_vector로 매핑한다. 원본 배열을 보존하도록 index.mapping.exclude_source_vectors:false를 생성 시 설정한다.
3. title/content는 text, category/language/vector_model은 keyword, published는 boolean으로 매핑한다.
4. f-semantic-target의 primary shard는 1개, replica는 0개다. 기존 f-semantic-corpus는 변경하지 않는다.

실습 안내:

- 작성한 합성 안내문을 sentence-transformers/all-MiniLM-L6-v2(1110a243fdf4, Apache-2.0)로 실제 인코딩한 384차원 벡터다. 평균 pooling과 L2 정규화를 적용했다. 모델의 품질을 공식 시험 점수로 평가하는 문항은 아니다.
- 이 Docker는 ML 노드가 꺼져 있다. 문서·질의 embedding은 이미 준비되어 있으며 모델 다운로드나 외부 inference API 없이 검색한다. semantic_text의 자동 inference 설정은 이 실습 범위에 포함하지 않는다.
- 작은 32건 corpus는 양자화하지 않은 HNSW로 준비했다. 자동 검증은 실제 벡터·RRF 검색 결과를 확인하며 대규모 데이터의 ANN recall을 보장하는 벤치마크가 아니다.
- 이 문제는 이미 계산된 벡터를 올바르게 저장하는 문제다. text를 dense_vector로 자동 변환하거나 벡터를 임의로 바꾸지 않는다.

[공식 기능 문서](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector)

## F02 · 메타데이터를 먼저 제한하는 의미 기반 kNN 검색

대상: f-semantic-corpus, f-semantic-queries

1. f-semantic-corpus에서 질의 "Find help diagnosing slow searches and improving query response times."의 준비된 embedding을 사용한다. GET f-semantic-queries/_doc/latency의 embedding 배열을 query_vector에 넣는다.
2. category:search, language:en, published:true 세 조건을 kNN 내부 pre-filter에 넣는다. 검색 후 post_filter로 제한하는 풀이로 대체하지 않는다.
3. embedding 필드에 k:5, num_candidates:32를 설정하고 size:5로 유사도가 높은 5건을 반환한다.
4. 각 hit의 문서 필드는 title과 category만 반환하며 embedding과 content는 반환하지 않는다.

실습 안내:

- 작성한 합성 안내문을 sentence-transformers/all-MiniLM-L6-v2(1110a243fdf4, Apache-2.0)로 실제 인코딩한 384차원 벡터다. 평균 pooling과 L2 정규화를 적용했다. 모델의 품질을 공식 시험 점수로 평가하는 문항은 아니다.
- 이 Docker는 ML 노드가 꺼져 있다. 문서·질의 embedding은 이미 준비되어 있으며 모델 다운로드나 외부 inference API 없이 검색한다. semantic_text의 자동 inference 설정은 이 실습 범위에 포함하지 않는다.
- 작은 32건 corpus는 양자화하지 않은 HNSW로 준비했다. 자동 검증은 실제 벡터·RRF 검색 결과를 확인하며 대규모 데이터의 ANN recall을 보장하는 벤치마크가 아니다.
- F01을 풀지 않아도 이 문제를 풀 수 있도록 검색 가능한 f-semantic-corpus가 별도로 준비되어 있다.
- 관련성이 높은 draft와 다른 언어 문서가 포함되어 있다. 조건을 kNN 내부에 적용해야 허용된 후보 중에서 5건을 찾는다.

[공식 기능 문서](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-knn-query)

## F03 · BM25와 벡터 검색을 RRF로 결합

대상: f-semantic-corpus, f-semantic-queries

1. f-semantic-corpus를 대상으로 retriever.rrf를 사용하는 하이브리드 검색을 작성한다.
2. 첫 번째 standard retriever는 semantic search를 title^2와 content의 multi_match로 검색한다.
3. 두 번째 knn retriever는 GET f-semantic-queries/_doc/hybrid의 준비된 embedding을 사용하여 embedding 필드를 k:12, num_candidates:32로 검색한다.
4. language:en과 published:true를 두 retriever 모두에 적용한다. standard는 bool.filter, knn은 내부 filter를 사용한다. 검색 후 post_filter로만 제한하지 않는다. category는 제한하지 않는다.
5. RRF는 rank_constant:20, rank_window_size:12를 사용하고 최종 size:5로 반환한다. BM25 점수와 cosine 점수를 직접 합산하는 bool.should로 대체하지 않는다.
6. 문서 필드는 title과 category만 반환하며 위 두 조건 이외의 filter나 별도 sort는 사용하지 않는다.

실습 안내:

- 작성한 합성 안내문을 sentence-transformers/all-MiniLM-L6-v2(1110a243fdf4, Apache-2.0)로 실제 인코딩한 384차원 벡터다. 평균 pooling과 L2 정규화를 적용했다. 모델의 품질을 공식 시험 점수로 평가하는 문항은 아니다.
- 이 Docker는 ML 노드가 꺼져 있다. 문서·질의 embedding은 이미 준비되어 있으며 모델 다운로드나 외부 inference API 없이 검색한다. semantic_text의 자동 inference 설정은 이 실습 범위에 포함하지 않는다.
- 작은 32건 corpus는 양자화하지 않은 HNSW로 준비했다. 자동 검증은 실제 벡터·RRF 검색 결과를 확인하며 대규모 데이터의 ANN recall을 보장하는 벤치마크가 아니다.
- F01/F02의 실행 여부와 무관하게 준비된 corpus로 검색한다. 문서·질의 벡터는 같은 모델과 pooling으로 계산되어 있다.
- RRF는 서로 다른 검색 결과의 순위를 결합한다. 문서의 정확한 제품 이름과 의미 기반 이웃을 함께 활용하는 실습이다. 유효한 기존 trial 라이선스를 사용한다.

[공식 기능 문서](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/rrf-retriever)

## F04 · ES|QL · 상태별 매장 순매출

대상: f-order-lines

1. cluster1의 f-order-lines를 FROM으로 읽고 POST /_query의 query에 ES|QL 파이프라인을 작성한다.
2. store가 존재하고 quantity > 0, unit_price_cents >= 0인 paid/refunded/cancelled 행만 포함한다. 필수 수치가 없는 행과 다른 상태는 제외한다.
3. 행 금액은 quantity * unit_price_cents - discount_cents이다. 누락된 discount_cents는 0이며, 할인은 행 전체에 한 번 적용한다.
4. 매장별 paid_cents는 paid 금액 합계, refund_cents는 refunded 금액 합계, cancelled_lines는 cancelled 행 수를 구한다. 해당 상태가 없는 금액 합계는 0으로 반환한다.
5. net_cents = paid_cents - refund_cents로 계산한다. 취소 금액은 매출에 포함하지 않는다.
6. store, paid_cents, refund_cents, net_cents, cancelled_lines 순서로 이 5개 열만 반환한다. net_cents 내림차순, 동점은 store 오름차순으로 모든 매장을 반환한다.

실습 안내:

- 금액 단위는 센트 정수이다. 동률 매장과 paid가 전혀 없는 매장을 포함하는 합성 데이터다.

[공식 기능 문서](https://www.elastic.co/docs/reference/query-languages/esql/commands/stats-by)

## F05 · ES|QL · UTC 일별 운영 지연 집계

대상: f-service-events

1. f-service-events에서 environment가 production이고 @timestamp가 2026-09-01T00:00:00Z 이상, 2026-09-04T00:00:00Z 미만인 행만 집계한다.
2. UTC 자정 기준의 1일 버킷 day를 만든다. 원본 시간에 오프셋이 있어도 UTC로 해석하며 관측된 날짜만 반환한다.
3. 날짜별 requests는 전체 행 수, errors는 status_code >= 500인 행 수, slow는 latency_ms >= 500인 행 수다. 각 필드가 누락된 행은 해당 조건 건수에 포함하지 않는다.
4. average_ms는 누락된 latency_ms를 제외한 평균을 소수점 한 자리로 반올림한다. 0ms는 정상 관측값이다.
5. day, requests, errors, slow, average_ms 순서로 이 5개 열만 반환하고 day 오름차순으로 모든 버킷을 정렬한다.

실습 안내:

- 9.3.8에서 지원하는 기본 UTC 동작을 사용한다. 9.4부터 추가된 Query API time_zone 옵션은 필요하지 않다.

[공식 기능 문서](https://www.elastic.co/docs/reference/query-languages/esql/functions-operators/date-time-functions/date_trunc)

## F06 · ES|QL · Lookup 상품 가격과 누락 SKU

대상: f-purchases, f-product-catalog

1. f-purchases에서 state가 completed이고 quantity > 0인 구매 행을 읽는다.
2. sku를 키로 f-product-catalog에 LOOKUP JOIN한다. 상품 인덱스는 index.mode=lookup으로 준비되어 있고 sku는 양쪽 모두 keyword다.
3. 상품 정보가 없는 SKU 및 누락된 sku 행도 버리지 않는다. department 누락은 "unknown"으로, 단가 누락은 계산에 0으로 처리한다.
4. 부서별 purchase_rows는 구매 행 수, units는 수량 합계, revenue_cents는 quantity * 단가 합계, unpriced_units는 원래 단가가 없던 구매의 수량 합계다. 가격 0과 가격 누락을 구분한다.
5. department, purchase_rows, units, revenue_cents, unpriced_units 순서로 이 5개 열만 반환한다. revenue_cents 내림차순, 동점은 department 오름차순으로 모든 부서를 반환한다.

실습 안내:

- lookup의 sku는 고유하다. 알려진 부서이지만 단가가 누락된 상품도 있으므로 unknown 부서만 세면 틀린다.

[공식 기능 문서](https://www.elastic.co/docs/reference/query-languages/esql/esql-lookup-join)

## F07 · ES|QL · 다중 태그의 중복 없는 조회수

대상: f-article-tags

1. f-article-tags에서 published가 true인 글만 대상으로 한다. article_id는 문서마다 고유하다.
2. tags_csv를 쉼표로 나눠 multivalue로 만든 뒤 각 태그를 행으로 확장한다. 태그는 이미 소문자이며 공백이 없으므로 별도 정규화는 필요 없다.
3. 한 글에 같은 태그가 반복되면 그 글·태그 조합을 한 번만 센다. null 태그 및 빈 문자열 태그는 제외한다.
4. 태그별 articles는 고유 글 수, total_views는 그 태그를 가진 각 글의 views 합계다. 누락된 views는 0이고 여러 다른 태그에 속한 글은 각 태그에 한 번씩 기여한다.
5. tag, articles, total_views 순서로 이 3개 열만 반환한다. articles 내림차순, 이어서 total_views 내림차순, 마지막 tag 오름차순으로 모든 태그를 반환한다.

실습 안내:

- SPLIT으로 생성된 multivalue에는 반복 값이 남을 수 있다. MV_EXPAND 이후 최종 SORT로 결과 순서를 확정한다.

[공식 기능 문서](https://www.elastic.co/docs/reference/query-languages/esql/commands/mv_expand)

## F08 · Streams Processing으로 로그를 구조화

대상: logs-f08-app-default

1. Kibana Streams에서 logs-f08-app-default을 열고 Processing에 저장되는 처리 규칙을 구성한다.
2. message의 level, status, duration, service 값을 각각 log.level, http.response.status_code, event.duration_ms, service.name에 추출한다.
3. http.response.status_code와 event.duration_ms는 숫자 long으로 변환하며 원래 message와 event.id는 유지한다.
4. log.level이 error인 문서에만 event.kind=alert를 추가한다. info 문서에는 event.kind를 추가하지 않는다.
5. 규칙을 저장한 뒤 아래 두 새 문서를 정상 색인한다: f08-error-proof의 message는 level=error status=503 duration=175 service=checkout; f08-info-proof의 message는 level=info status=200 duration=24 service=catalog.
6. 두 새 문서의 @timestamp는 2026-10-01T00:00:00Z, event.id는 각각 지정된 proof 이름으로 제출한다.

실습 안내:

- Kibana cluster1에서 Streams를 검색해 해당 스트림을 연다. 이 문항은 기존 data stream을 관리하는 classic Streams를 사용한다.
- 예시의 kbn:/api/streams 요청은 Kibana API다. 이 실습의 Console 프록시는 kbn: 요청을 실제 Kibana로 전달한다. 일반 Elasticsearch /api/streams 요청으로 바꾸지 않는다.
- 9.3에서는 wired root가 logs이며 현재 환경에서 활성화하지 않았다. logs.ecs/logs.otel은 9.4 이후 조건이므로 이 문항에 사용하지 않는다.
- Processing 변경은 이후에 들어오는 문서에 적용된다. 준비된 기존 샘플이 자동으로 재처리되는 것은 아니다. 검증은 새 proof 문서를 확인한다.
- event.duration_ms는 밀리초 단위의 실습용 사용자 필드다. ECS event.duration의 나노초 값과 혼동하지 않는다.
- AI connector 없이 Create processor로 dissect, convert 두 개, 조건부 set을 직접 구성할 수 있다. 같은 결과를 내는 다른 Streams 처리 방식도 허용한다.

[공식 기능 문서](https://www.elastic.co/docs/solutions/observability/streams/parse-and-process)

## F09 · Streams Retention과 rollover 이후 쓰기 검증

대상: logs-f09-retention-default

1. Kibana Streams에서 logs-f09-retention-default을 열어 Retention을 직접 관리하도록 설정한다.
2. index template의 보존 설정 상속 대신 data stream lifecycle(DSL)로 7일 보존을 지정한다. ILM policy를 새로 만드는 문제가 아니다.
3. 기존 seed 문서 세 개를 보존하면서 한 번 이상 수동 rollover한다.
4. rollover 후 스트림 이름으로 새 문서를 추가한다. event.id는 f09-after-rollover, message는 After rollover, @timestamp는 2026-10-01T00:00:01Z다.
5. 새 문서는 현재 write backing index에 있고 seed 문서들은 이전 backing index에서 조회되어야 한다.

실습 안내:

- Kibana cluster1에서 Streams를 검색해 해당 스트림을 연다. 이 문항은 기존 data stream을 관리하는 classic Streams를 사용한다.
- 예시의 kbn:/api/streams 요청은 Kibana API다. 이 실습의 Console 프록시는 kbn: 요청을 실제 Kibana로 전달한다. 일반 Elasticsearch /api/streams 요청으로 바꾸지 않는다.
- 9.3에서는 wired root가 logs이며 현재 환경에서 활성화하지 않았다. logs.ecs/logs.otel은 9.4 이후 조건이므로 이 문항에 사용하지 않는다.
- Streams 화면의 Retention → Edit data retention에서 custom 7 days를 선택할 수 있다. API 예시는 동일한 Streams 설정을 저장한다.
- DSL 보존 기간은 삭제를 허용하는 최소 보존 기간이다. 설정 직후 모든 과거 문서가 삭제된다는 뜻이 아니다. backing index의 rollover 기준도 영향을 준다.
- 7일이 지나기를 기다릴 필요는 없다. 검증은 실제 Streams 설정, Elasticsearch lifecycle, rollover 결과와 문서의 backing index 위치를 확인한다.

[공식 기능 문서](https://www.elastic.co/guide/en/elasticsearch/reference/current/tutorial-manage-existing-data-stream.html)

## F10 · Streams Failure store로 매핑 오류 진단

대상: logs-f10-audit-default

1. Kibana Streams에서 logs-f10-audit-default의 Failure store를 활성화하고 실패 문서를 3일 보존하도록 설정한다.
2. event.id=f10-bad, message=Invalid audit timestamp, @timestamp=not-a-date인 문서를 해당 스트림에 색인한다.
3. 이 문서는 일반 backing index에 저장되지 않고 실제 failure store에 들어가야 한다. 원본 잘못된 날짜와 event.id가 실패 문서 안에 보존되어야 한다.
4. 실패 문서의 error.type은 document_parsing_exception이어야 하며 document.index는 대상 스트림 이름이어야 한다.
5. 같은 스트림에 event.id=f10-good-proof, message=Valid audit timestamp, @timestamp=2026-10-01T00:00:02Z 문서를 추가해 정상 색인이 계속되는 것도 확인한다.

실습 안내:

- Kibana cluster1에서 Streams를 검색해 해당 스트림을 연다. 이 문항은 기존 data stream을 관리하는 classic Streams를 사용한다.
- 예시의 kbn:/api/streams 요청은 Kibana API다. 이 실습의 Console 프록시는 kbn: 요청을 실제 Kibana로 전달한다. 일반 Elasticsearch /api/streams 요청으로 바꾸지 않는다.
- 9.3에서는 wired root가 logs이며 현재 환경에서 활성화하지 않았다. logs.ecs/logs.otel은 9.4 이후 조건이므로 이 문항에 사용하지 않는다.
- 9.3.8에서 failure store에 우회 저장된 잘못된 날짜 문서는 HTTP 201과 failure_store:used로 응답한다. 정상 문서로 해석하지 말고 응답의 저장 위치를 확인한다.
- ::failures selector는 failure store를 검색한다. document.source 내부의 원본 값은 보존되지만 일반 검색용으로 모두 색인되는 것은 아니므로 event.id로 term 검색하지 말고 반환된 _source를 확인한다.
- 현재 9.3.8 환경의 Significant events 저장 쿼리 기능은 비활성화되어 있다. 이 문항은 실제 사용 가능한 Streams failure store를 사용한다.

[공식 기능 문서](https://www.elastic.co/docs/manage-data/data-store/data-streams/failure-store)
