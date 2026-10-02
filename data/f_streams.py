"""Three independent, original classic Streams exercises for Kibana 9.3.8."""
from __future__ import annotations

import copy
import json

PROCESS_STREAM = 'logs-f08-app-default'
RETENTION_STREAM = 'logs-f09-retention-default'
FAILURE_STREAM = 'logs-f10-audit-default'
STREAM_NAMES = (PROCESS_STREAM, RETENTION_STREAM, FAILURE_STREAM)
PATTERN = ('level=%{log.level} status=%{http.response.status_code} '
           'duration=%{event.duration_ms} service=%{service.name}')
STEPS = [
    {'action': 'dissect', 'from': 'message', 'pattern': PATTERN},
    {'action': 'convert', 'from': 'http.response.status_code', 'type': 'long'},
    {'action': 'convert', 'from': 'event.duration_ms', 'type': 'long'},
    {'action': 'set', 'to': 'event.kind', 'value': 'alert',
     'where': {'field': 'log.level', 'eq': 'error'}},
]
PROOFS = {
    'f08-error-proof': {'level': 'error', 'status': 503, 'duration': 175, 'service': 'checkout'},
    'f08-info-proof': {'level': 'info', 'status': 200, 'duration': 24, 'service': 'catalog'},
}
PROPERTIES = {
    '@timestamp': {'type': 'date'}, 'message': {'type': 'text'},
    'event': {'properties': {'id': {'type': 'keyword'}, 'kind': {'type': 'keyword'},
                             'duration_ms': {'type': 'long'}}},
    'log': {'properties': {'level': {'type': 'keyword'}}},
    'service': {'properties': {'name': {'type': 'keyword'}}},
    'http': {'properties': {'response': {'properties': {'status_code': {'type': 'long'}}}}},
}


def message(proof):
    return (f'level={proof["level"]} status={proof["status"]} '
            f'duration={proof["duration"]} service={proof["service"]}')


def document(identifier, text, stamp='2026-10-01T00:00:00Z'):
    return {'@timestamp': stamp, 'message': text, 'event': {'id': identifier}}


def fixture(name, documents):
    return {'cluster': 'cluster1', 'index': name, 'data_stream': True,
            'settings': {'number_of_shards': 1, 'number_of_replicas': 0},
            'mappings': {'properties': copy.deepcopy(PROPERTIES)},
            'documents': [{'_id': f'{name}-{i:04d}', '_source': value}
                          for i, value in enumerate(documents, 1)]}


FIXTURES = [
    fixture(PROCESS_STREAM, [
        document('f08-seed-01', 'level=error status=503 duration=175 service=checkout'),
        document('f08-seed-02', 'level=info status=200 duration=24 service=catalog'),
        document('f08-seed-03', 'level=error status=500 duration=90 service=catalog'),
        document('f08-seed-04', 'level=info status=201 duration=51 service=checkout'),
    ]),
    fixture(RETENTION_STREAM, [document(f'f09-seed-{i:02d}', f'Retention seed document {i}')
                               for i in range(1, 4)]),
    fixture(FAILURE_STREAM, [document('f10-seed-01', 'Valid audit seed document 1'),
                             document('f10-seed-02', 'Valid audit seed document 2')]),
]


def ingest_body(*, steps=(), lifecycle=None, failure_store=None):
    """9.3 request shape; processing.updated_at is a read-only response field."""
    return {'ingest': {'classic': {}, 'processing': {'steps': copy.deepcopy(list(steps))},
                       'lifecycle': copy.deepcopy(lifecycle or {'inherit': {}}),
                       'settings': {},
                       'failure_store': copy.deepcopy(failure_store or {'inherit': {}})}}


def rq(method, path, body=None):
    return method + ' ' + path + ('\n' + json.dumps(body, ensure_ascii=False, indent=2)
                                  if body is not None else '')


def task(number, title, topic, requirements, solution, check, stream, url, notes, hint):
    return {'id': f'F{number:02d}', 'set': 'F', 'number': number,
            'title': title, 'topic': topic, 'requirements': requirements,
            'source': {'document': '', 'pages': [], 'label': 'Elastic 공식 Streams 문서', 'url': url},
            'cluster': 'cluster1', 'datasets': [stream], 'notes': notes,
            'hint': hint, 'solution': solution, 'kind': 'state', 'check': check,
            'answer': '', 'reconstructed': True,
            'intro': 'Elasticsearch/Kibana 9.3.8의 실제 Streams 기능을 활용하는 새 예상 실습 문항입니다.'}


COMMON_NOTES = [
    'Kibana cluster1에서 Streams를 검색해 해당 스트림을 연다. 이 문항은 기존 data stream을 관리하는 classic Streams를 사용한다.',
    '예시의 kbn:/api/streams 요청은 Kibana API다. 이 실습의 Console 프록시는 kbn: 요청을 실제 Kibana로 전달한다. 일반 Elasticsearch /api/streams 요청으로 바꾸지 않는다.',
    '9.3에서는 wired root가 logs이며 현재 환경에서 활성화하지 않았다. logs.ecs/logs.otel은 9.4 이후 조건이므로 이 문항에 사용하지 않는다.',
]
TASKS = [
    task(8, 'Streams Processing으로 로그를 구조화', 'Streams · Streamlang · Conditional processing', [
        f'Kibana Streams에서 {PROCESS_STREAM}을 열고 Processing에 저장되는 처리 규칙을 구성한다.',
        'message의 level, status, duration, service 값을 각각 log.level, http.response.status_code, event.duration_ms, service.name에 추출한다.',
        'http.response.status_code와 event.duration_ms는 숫자 long으로 변환하며 원래 message와 event.id는 유지한다.',
        'log.level이 error인 문서에만 event.kind=alert를 추가한다. info 문서에는 event.kind를 추가하지 않는다.',
        '규칙을 저장한 뒤 아래 두 새 문서를 정상 색인한다: f08-error-proof의 message는 level=error status=503 duration=175 service=checkout; f08-info-proof의 message는 level=info status=200 duration=24 service=catalog.',
        '두 새 문서의 @timestamp는 2026-10-01T00:00:00Z, event.id는 각각 지정된 proof 이름으로 제출한다.',
    ], '\n\n'.join([
        rq('GET', f'kbn:/api/streams/{PROCESS_STREAM}/_ingest'),
        rq('PUT', f'kbn:/api/streams/{PROCESS_STREAM}/_ingest', ingest_body(steps=STEPS)),
        *[rq('POST', f'{PROCESS_STREAM}/_doc?refresh=true', document(identifier, message(proof)))
          for identifier, proof in PROOFS.items()],
        rq('GET', f'{PROCESS_STREAM}/_search', {'query': {'terms': {'event.id': list(PROOFS)}}}),
    ]), 'f_stream_processing', PROCESS_STREAM,
         'https://www.elastic.co/docs/solutions/observability/streams/parse-and-process',
         COMMON_NOTES + [
             'Processing 변경은 이후에 들어오는 문서에 적용된다. 준비된 기존 샘플이 자동으로 재처리되는 것은 아니다. 검증은 새 proof 문서를 확인한다.',
             'event.duration_ms는 밀리초 단위의 실습용 사용자 필드다. ECS event.duration의 나노초 값과 혼동하지 않는다.',
             'AI connector 없이 Create processor로 dissect, convert 두 개, 조건부 set을 직접 구성할 수 있다. 같은 결과를 내는 다른 Streams 처리 방식도 허용한다.',
         ], 'Dissect로 키 값을 분리하고 Convert를 적용한 뒤 Set에 log.level == error 조건을 연결한다.'),
    task(9, 'Streams Retention과 rollover 이후 쓰기 검증', 'Streams · Data stream lifecycle · Rollover', [
        f'Kibana Streams에서 {RETENTION_STREAM}을 열어 Retention을 직접 관리하도록 설정한다.',
        'index template의 보존 설정 상속 대신 data stream lifecycle(DSL)로 7일 보존을 지정한다. ILM policy를 새로 만드는 문제가 아니다.',
        '기존 seed 문서 세 개를 보존하면서 한 번 이상 수동 rollover한다.',
        'rollover 후 스트림 이름으로 새 문서를 추가한다. event.id는 f09-after-rollover, message는 After rollover, @timestamp는 2026-10-01T00:00:01Z다.',
        '새 문서는 현재 write backing index에 있고 seed 문서들은 이전 backing index에서 조회되어야 한다.',
    ], '\n\n'.join([
        rq('GET', f'kbn:/api/streams/{RETENTION_STREAM}/_ingest'),
        rq('PUT', f'kbn:/api/streams/{RETENTION_STREAM}/_ingest',
           ingest_body(lifecycle={'dsl': {'data_retention': '7d'}})),
        rq('GET', f'_data_stream/{RETENTION_STREAM}/_lifecycle'),
        rq('POST', f'{RETENTION_STREAM}/_rollover'),
        rq('POST', f'{RETENTION_STREAM}/_doc?refresh=true',
           document('f09-after-rollover', 'After rollover', '2026-10-01T00:00:01Z')),
        rq('GET', f'{RETENTION_STREAM}/_search', {'size': 10, 'query': {'match_all': {}}}),
    ]), 'f_stream_retention', RETENTION_STREAM,
         'https://www.elastic.co/guide/en/elasticsearch/reference/current/tutorial-manage-existing-data-stream.html',
         COMMON_NOTES + [
             'Streams 화면의 Retention → Edit data retention에서 custom 7 days를 선택할 수 있다. API 예시는 동일한 Streams 설정을 저장한다.',
             'DSL 보존 기간은 삭제를 허용하는 최소 보존 기간이다. 설정 직후 모든 과거 문서가 삭제된다는 뜻이 아니다. backing index의 rollover 기준도 영향을 준다.',
             '7일이 지나기를 기다릴 필요는 없다. 검증은 실제 Streams 설정, Elasticsearch lifecycle, rollover 결과와 문서의 backing index 위치를 확인한다.',
         ], 'Streams에서 DSL 보존을 저장한 뒤 _rollover하고 기존 backing index와 새 write index의 문서를 비교한다.'),
    task(10, 'Streams Failure store로 매핑 오류 진단', 'Streams · Failure store · Mapping failure', [
        f'Kibana Streams에서 {FAILURE_STREAM}의 Failure store를 활성화하고 실패 문서를 3일 보존하도록 설정한다.',
        'event.id=f10-bad, message=Invalid audit timestamp, @timestamp=not-a-date인 문서를 해당 스트림에 색인한다.',
        '이 문서는 일반 backing index에 저장되지 않고 실제 failure store에 들어가야 한다. 원본 잘못된 날짜와 event.id가 실패 문서 안에 보존되어야 한다.',
        '실패 문서의 error.type은 document_parsing_exception이어야 하며 document.index는 대상 스트림 이름이어야 한다.',
        '같은 스트림에 event.id=f10-good-proof, message=Valid audit timestamp, @timestamp=2026-10-01T00:00:02Z 문서를 추가해 정상 색인이 계속되는 것도 확인한다.',
    ], '\n\n'.join([
        rq('GET', f'kbn:/api/streams/{FAILURE_STREAM}/_ingest'),
        rq('PUT', f'kbn:/api/streams/{FAILURE_STREAM}/_ingest',
           ingest_body(failure_store={'lifecycle': {'enabled': {'data_retention': '3d'}}})),
        rq('GET', f'_data_stream/{FAILURE_STREAM}/_options'),
        rq('POST', f'{FAILURE_STREAM}/_doc?refresh=true',
           document('f10-bad', 'Invalid audit timestamp', 'not-a-date')),
        rq('POST', f'{FAILURE_STREAM}/_doc?refresh=true',
           document('f10-good-proof', 'Valid audit timestamp', '2026-10-01T00:00:02Z')),
        rq('GET', f'{FAILURE_STREAM}::failures/_search', {'size': 10, 'query': {'match_all': {}},
            '_source': ['document.index', 'document.source', 'error.type', 'error.message']}),
        rq('GET', f'{FAILURE_STREAM}/_search', {'query': {'term': {'event.id': 'f10-good-proof'}}}),
    ]), 'f_stream_failures', FAILURE_STREAM,
         'https://www.elastic.co/docs/manage-data/data-store/data-streams/failure-store',
         COMMON_NOTES + [
             '9.3.8에서 failure store에 우회 저장된 잘못된 날짜 문서는 HTTP 201과 failure_store:used로 응답한다. 정상 문서로 해석하지 말고 응답의 저장 위치를 확인한다.',
             '::failures selector는 failure store를 검색한다. document.source 내부의 원본 값은 보존되지만 일반 검색용으로 모두 색인되는 것은 아니므로 event.id로 term 검색하지 말고 반환된 _source를 확인한다.',
             '현재 9.3.8 환경의 Significant events 저장 쿼리 기능은 비활성화되어 있다. 이 문항은 실제 사용 가능한 Streams failure store를 사용한다.',
         ], 'Streams의 failure_store lifecycle을 활성화한 뒤 날짜 매핑 오류를 만들고 ::failures에서 원본과 error를 함께 확인한다.'),
]
