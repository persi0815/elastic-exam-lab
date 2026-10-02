"""Four independently seeded ES|QL exercises for Elasticsearch 9.3.8.

These are authored practice questions with synthetic data. Official documentation
is a syntax reference, not source exam content or executable instructions.
"""
from __future__ import annotations
import copy
import json

DOCS = 'https://www.elastic.co/docs/reference/query-languages/esql/'


def fixture(index, properties, documents, *, lookup=False):
    settings = {'number_of_shards': 1, 'number_of_replicas': 0}
    if lookup:
        settings['index.mode'] = 'lookup'
    return {'cluster': 'cluster1', 'index': index, 'settings': settings,
            'mappings': {'dynamic': 'strict', 'properties': properties},
            'documents': [{'_id': f'{index}-{i:03d}', '_source': copy.deepcopy(source)}
                          for i, source in enumerate(documents, 1)]}


def task(number, title, topic, requirements, datasets, query, check, doc,
         hint, notes=()):
    return {'id': f'F{number:02d}', 'set': 'F', 'number': number, 'title': title,
            'topic': topic, 'requirements': list(requirements),
            'source': {'document': 'Elastic ES|QL 공식 문서', 'pages': [],
                       'label': '자체 출제 · Elasticsearch 9.3.8 호환 ES|QL',
                       'url': DOCS + doc},
            'cluster': 'cluster1', 'datasets': list(datasets), 'notes': list(notes),
            'hint': hint,
            'solution': 'POST /_query\n' + json.dumps({'query': query}, ensure_ascii=False, indent=2),
            'kind': 'query', 'check': check, 'answer': '',
            'intro': '실제 Elasticsearch ES|QL Query API로 결과 표를 반환하세요. 문자열 답안이 아닌 실행 결과를 검증합니다.',
            'reconstructed': False}


FIXTURES = [
    fixture('f-order-lines', {
        'store': {'type': 'keyword'}, 'status': {'type': 'keyword'},
        'quantity': {'type': 'long'}, 'unit_price_cents': {'type': 'long'},
        'discount_cents': {'type': 'long'}}, [
        {'store': 'north', 'status': 'paid', 'quantity': 2, 'unit_price_cents': 1000, 'discount_cents': 100},
        {'store': 'north', 'status': 'paid', 'quantity': 1, 'unit_price_cents': 2500},
        {'store': 'north', 'status': 'refunded', 'quantity': 1, 'unit_price_cents': 1000},
        {'store': 'north', 'status': 'cancelled', 'quantity': 5, 'unit_price_cents': 10000},
        {'store': 'south', 'status': 'paid', 'quantity': 3, 'unit_price_cents': 500, 'discount_cents': 100},
        {'store': 'south', 'status': 'refunded', 'quantity': 1, 'unit_price_cents': 500, 'discount_cents': 50},
        {'store': 'south', 'status': 'cancelled', 'quantity': 1, 'unit_price_cents': 800},
        {'store': 'south', 'status': 'cancelled', 'quantity': 2, 'unit_price_cents': 800},
        {'store': 'east', 'status': 'refunded', 'quantity': 2, 'unit_price_cents': 700},
        {'store': 'east', 'status': 'cancelled', 'quantity': 1, 'unit_price_cents': 700},
        {'store': 'west', 'status': 'paid', 'quantity': 1, 'unit_price_cents': 950},
        {'store': 'west', 'status': 'paid', 'quantity': 0, 'unit_price_cents': 9999},
        {'status': 'paid', 'quantity': 1, 'unit_price_cents': 9999},
        {'store': 'south', 'status': 'pending', 'quantity': 1, 'unit_price_cents': 9999},
        {'store': 'north', 'status': 'paid', 'unit_price_cents': 9999},
        {'store': 'north', 'status': 'paid', 'quantity': 1},
        {'store': 'east', 'status': 'paid', 'quantity': -1, 'unit_price_cents': 1000},
    ]),
    fixture('f-service-events', {
        '@timestamp': {'type': 'date'}, 'environment': {'type': 'keyword'},
        'status_code': {'type': 'long'}, 'latency_ms': {'type': 'long'}}, [
        {'@timestamp': '2026-09-01T00:00:00Z', 'environment': 'production', 'status_code': 200, 'latency_ms': 100},
        {'@timestamp': '2026-09-01T12:00:00Z', 'environment': 'production', 'status_code': 500, 'latency_ms': 600},
        {'@timestamp': '2026-09-02T08:59:59+09:00', 'environment': 'production', 'status_code': 200, 'latency_ms': 900},
        {'@timestamp': '2026-09-01T23:59:59Z', 'environment': 'production', 'status_code': 503},
        {'@timestamp': '2026-09-02T09:00:00+09:00', 'environment': 'production', 'status_code': 200, 'latency_ms': 250},
        {'@timestamp': '2026-09-02T10:00:00Z', 'environment': 'production', 'status_code': 502, 'latency_ms': 800},
        {'@timestamp': '2026-09-02T18:00:00Z', 'environment': 'production', 'latency_ms': 500},
        {'@timestamp': '2026-09-03T00:00:00Z', 'environment': 'production', 'status_code': 201, 'latency_ms': 0},
        {'@timestamp': '2026-09-03T12:00:00Z', 'environment': 'production', 'status_code': 500},
        {'@timestamp': '2026-09-03T23:59:59.999Z', 'environment': 'production', 'status_code': 200, 'latency_ms': 150},
        {'@timestamp': '2026-08-31T23:59:59.999Z', 'environment': 'production', 'status_code': 500, 'latency_ms': 9999},
        {'@timestamp': '2026-09-04T00:00:00Z', 'environment': 'production', 'status_code': 500, 'latency_ms': 9999},
        {'@timestamp': '2026-09-02T12:00:00Z', 'environment': 'development', 'status_code': 500, 'latency_ms': 9999},
        {'environment': 'production', 'status_code': 500, 'latency_ms': 9999},
    ]),
    fixture('f-purchases', {
        'sku': {'type': 'keyword'}, 'state': {'type': 'keyword'}, 'quantity': {'type': 'long'}}, [
        {'sku': 'book-a', 'state': 'completed', 'quantity': 2},
        {'sku': 'device-b', 'state': 'completed', 'quantity': 1},
        {'sku': 'device-b', 'state': 'completed', 'quantity': 3},
        {'sku': 'device-c', 'state': 'completed', 'quantity': 4},
        {'sku': 'unlisted-d', 'state': 'completed', 'quantity': 2},
        {'sku': 'book-a', 'state': 'completed', 'quantity': 1},
        {'sku': 'free-e', 'state': 'completed', 'quantity': 2},
        {'state': 'completed', 'quantity': 1},
        {'sku': 'book-a', 'state': 'pending', 'quantity': 5},
        {'sku': 'device-b', 'state': 'cancelled', 'quantity': 2},
        {'sku': 'book-a', 'state': 'completed', 'quantity': 0},
        {'sku': 'book-a', 'state': 'completed', 'quantity': -1},
        {'sku': 'book-a', 'state': 'completed'},
    ]),
    fixture('f-product-catalog', {
        'sku': {'type': 'keyword'}, 'department': {'type': 'keyword'},
        'unit_price_cents': {'type': 'long'}}, [
        {'sku': 'book-a', 'department': 'books', 'unit_price_cents': 1200},
        {'sku': 'device-b', 'department': 'electronics', 'unit_price_cents': 5000},
        {'sku': 'device-c', 'department': 'electronics'},
        {'sku': 'free-e', 'department': 'books', 'unit_price_cents': 0},
    ], lookup=True),
    fixture('f-article-tags', {
        'article_id': {'type': 'keyword'}, 'published': {'type': 'boolean'},
        'tags_csv': {'type': 'keyword'}, 'views': {'type': 'long'}}, [
        {'article_id': 'a1', 'published': True, 'tags_csv': 'search,data,search', 'views': 100},
        {'article_id': 'a2', 'published': True, 'tags_csv': 'search,observability', 'views': 50},
        {'article_id': 'a3', 'published': True, 'tags_csv': 'data,data', 'views': 25},
        {'article_id': 'a4', 'published': True, 'tags_csv': 'observability,,search', 'views': 75},
        {'article_id': 'a5', 'published': True, 'tags_csv': '', 'views': 10},
        {'article_id': 'a6', 'published': True, 'views': 20},
        {'article_id': 'a7', 'published': False, 'tags_csv': 'search', 'views': 999},
        {'article_id': 'a8', 'published': True, 'tags_csv': 'search'},
        {'article_id': 'a9', 'published': True, 'tags_csv': 'data,observability', 'views': 0},
        {'article_id': 'a10', 'published': True, 'tags_csv': 'data', 'views': 10},
    ]),
]

TASKS = [
    task(4, 'ES|QL · 상태별 매장 순매출', 'ES|QL · WHERE / EVAL / 조건 집계', [
        'cluster1의 f-order-lines를 FROM으로 읽고 POST /_query의 query에 ES|QL 파이프라인을 작성한다.',
        'store가 존재하고 quantity > 0, unit_price_cents >= 0인 paid/refunded/cancelled 행만 포함한다. 필수 수치가 없는 행과 다른 상태는 제외한다.',
        '행 금액은 quantity * unit_price_cents - discount_cents이다. 누락된 discount_cents는 0이며, 할인은 행 전체에 한 번 적용한다.',
        '매장별 paid_cents는 paid 금액 합계, refund_cents는 refunded 금액 합계, cancelled_lines는 cancelled 행 수를 구한다. 해당 상태가 없는 금액 합계는 0으로 반환한다.',
        'net_cents = paid_cents - refund_cents로 계산한다. 취소 금액은 매출에 포함하지 않는다.',
        'store, paid_cents, refund_cents, net_cents, cancelled_lines 순서로 이 5개 열만 반환한다. net_cents 내림차순, 동점은 store 오름차순으로 모든 매장을 반환한다.',
    ], ['f-order-lines'], '''FROM f-order-lines
| WHERE store IS NOT NULL AND quantity > 0 AND unit_price_cents >= 0 AND status IN ("paid", "refunded", "cancelled")
| EVAL line_cents = quantity * unit_price_cents - COALESCE(discount_cents, 0)
| STATS paid_cents = SUM(line_cents) WHERE status == "paid", refund_cents = SUM(line_cents) WHERE status == "refunded", cancelled_lines = COUNT(*) WHERE status == "cancelled" BY store
| EVAL paid_cents = COALESCE(paid_cents, 0), refund_cents = COALESCE(refund_cents, 0)
| EVAL net_cents = paid_cents - refund_cents
| SORT net_cents DESC, store ASC
| KEEP store, paid_cents, refund_cents, net_cents, cancelled_lines''',
         'f_esql_orders', 'commands/stats-by',
         '집계 전체 앞의 WHERE와 각 SUM/COUNT 뒤의 WHERE는 다른 역할이다. 조건별로 행을 먼저 모두 제거하지 않는다.',
         ['금액 단위는 센트 정수이다. 동률 매장과 paid가 전혀 없는 매장을 포함하는 합성 데이터다.']),
    task(5, 'ES|QL · UTC 일별 운영 지연 집계', 'ES|QL · DATE_TRUNC / 날짜 경계 / Null', [
        'f-service-events에서 environment가 production이고 @timestamp가 2026-09-01T00:00:00Z 이상, 2026-09-04T00:00:00Z 미만인 행만 집계한다.',
        'UTC 자정 기준의 1일 버킷 day를 만든다. 원본 시간에 오프셋이 있어도 UTC로 해석하며 관측된 날짜만 반환한다.',
        '날짜별 requests는 전체 행 수, errors는 status_code >= 500인 행 수, slow는 latency_ms >= 500인 행 수다. 각 필드가 누락된 행은 해당 조건 건수에 포함하지 않는다.',
        'average_ms는 누락된 latency_ms를 제외한 평균을 소수점 한 자리로 반올림한다. 0ms는 정상 관측값이다.',
        'day, requests, errors, slow, average_ms 순서로 이 5개 열만 반환하고 day 오름차순으로 모든 버킷을 정렬한다.',
    ], ['f-service-events'], '''FROM f-service-events
| WHERE environment == "production" AND @timestamp >= "2026-09-01T00:00:00Z" AND @timestamp < "2026-09-04T00:00:00Z"
| EVAL day = DATE_TRUNC(1 day, @timestamp)
| STATS requests = COUNT(*), errors = COUNT(*) WHERE status_code >= 500, slow = COUNT(*) WHERE latency_ms >= 500, average_ms = ROUND(AVG(latency_ms), 1) BY day
| SORT day ASC
| KEEP day, requests, errors, slow, average_ms''',
         'f_esql_days', 'functions-operators/date-time-functions/date_trunc',
         '범위의 상한은 미포함이며 DATE_TRUNC(1 day, @timestamp)는 UTC 날짜 경계를 사용한다.',
         ['9.3.8에서 지원하는 기본 UTC 동작을 사용한다. 9.4부터 추가된 Query API time_zone 옵션은 필요하지 않다.']),
    task(6, 'ES|QL · Lookup 상품 가격과 누락 SKU', 'ES|QL · LOOKUP JOIN / lookup index / 집계', [
        'f-purchases에서 state가 completed이고 quantity > 0인 구매 행을 읽는다.',
        'sku를 키로 f-product-catalog에 LOOKUP JOIN한다. 상품 인덱스는 index.mode=lookup으로 준비되어 있고 sku는 양쪽 모두 keyword다.',
        '상품 정보가 없는 SKU 및 누락된 sku 행도 버리지 않는다. department 누락은 "unknown"으로, 단가 누락은 계산에 0으로 처리한다.',
        '부서별 purchase_rows는 구매 행 수, units는 수량 합계, revenue_cents는 quantity * 단가 합계, unpriced_units는 원래 단가가 없던 구매의 수량 합계다. 가격 0과 가격 누락을 구분한다.',
        'department, purchase_rows, units, revenue_cents, unpriced_units 순서로 이 5개 열만 반환한다. revenue_cents 내림차순, 동점은 department 오름차순으로 모든 부서를 반환한다.',
    ], ['f-purchases', 'f-product-catalog'], '''FROM f-purchases
| WHERE state == "completed" AND quantity > 0
| LOOKUP JOIN f-product-catalog ON sku
| EVAL department = COALESCE(department, "unknown"), line_cents = quantity * COALESCE(unit_price_cents, 0), unpriced = CASE(unit_price_cents IS NULL, quantity, 0)
| STATS purchase_rows = COUNT(*), units = SUM(quantity), revenue_cents = SUM(line_cents), unpriced_units = SUM(unpriced) BY department
| SORT revenue_cents DESC, department ASC
| KEEP department, purchase_rows, units, revenue_cents, unpriced_units''',
         'f_esql_lookup', 'esql-lookup-join',
         'LOOKUP JOIN은 일치하지 않는 원본 행도 유지한다. COALESCE로 바꾸기 전에 가격 누락 여부를 기록한다.',
         ['lookup의 sku는 고유하다. 알려진 부서이지만 단가가 누락된 상품도 있으므로 unknown 부서만 세면 틀린다.']),
    task(7, 'ES|QL · 다중 태그의 중복 없는 조회수', 'ES|QL · SPLIT / MV_DEDUPE / MV_EXPAND', [
        'f-article-tags에서 published가 true인 글만 대상으로 한다. article_id는 문서마다 고유하다.',
        'tags_csv를 쉼표로 나눠 multivalue로 만든 뒤 각 태그를 행으로 확장한다. 태그는 이미 소문자이며 공백이 없으므로 별도 정규화는 필요 없다.',
        '한 글에 같은 태그가 반복되면 그 글·태그 조합을 한 번만 센다. null 태그 및 빈 문자열 태그는 제외한다.',
        '태그별 articles는 고유 글 수, total_views는 그 태그를 가진 각 글의 views 합계다. 누락된 views는 0이고 여러 다른 태그에 속한 글은 각 태그에 한 번씩 기여한다.',
        'tag, articles, total_views 순서로 이 3개 열만 반환한다. articles 내림차순, 이어서 total_views 내림차순, 마지막 tag 오름차순으로 모든 태그를 반환한다.',
    ], ['f-article-tags'], '''FROM f-article-tags
| WHERE published == true
| EVAL tag = MV_DEDUPE(SPLIT(tags_csv, ",")), article_views = COALESCE(views, 0)
| MV_EXPAND tag
| WHERE tag IS NOT NULL AND tag != ""
| STATS articles = COUNT_DISTINCT(article_id), total_views = SUM(article_views) BY tag
| SORT articles DESC, total_views DESC, tag ASC
| KEEP tag, articles, total_views''',
         'f_esql_tags', 'commands/mv_expand',
         'MV_EXPAND 뒤에만 COUNT_DISTINCT를 쓰면 조회수 SUM의 중복은 남는다. 먼저 태그를 dedupe하거나 글·태그별로 중간 집계한다.',
         ['SPLIT으로 생성된 multivalue에는 반복 값이 남을 수 있다. MV_EXPAND 이후 최종 SORT로 결과 순서를 확정한다.']),
]
