"""Read-only checks of real Kibana classic Streams and Elasticsearch results."""
from __future__ import annotations

from datetime import datetime

PROCESS_STREAM = 'logs-f08-app-default'
RETENTION_STREAM = 'logs-f09-retention-default'
FAILURE_STREAM = 'logs-f10-audit-default'


def duration(value):
    from verify import duration as seconds
    return seconds(value)


def field(source, path):
    if path in source:
        return source[path]
    value = source
    for part in path.split('.'):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def timestamp(value, expected):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')) == datetime.fromisoformat(expected.replace('Z', '+00:00'))
    except (ValueError, TypeError, AttributeError):
        return False


def kb_stream(v, name):
    result = v.es.kibana_require(v.c, 'GET', '/api/streams/' + name)
    stream = result.get('stream', {})
    v.add('실제 Kibana classic Streams 대상', stream.get('name') == name
          and 'classic' in stream.get('ingest', {}) and result.get('data_stream_exists') is True)
    return result


def hits(v, name, query=None):
    response = v.get('/' + name + '/_search', body={'size': 100, 'track_total_hits': True,
                                                   'query': query or {'match_all': {}}})
    v.add('검색 중 shard 오류 없음', response.get('_shards', {}).get('failed', 0) == 0
          and not response.get('timed_out', False))
    return response.get('hits', {}).get('hits', [])


def processing(v):
    result = kb_stream(v, PROCESS_STREAM)
    steps = result.get('stream', {}).get('ingest', {}).get('processing', {}).get('steps', [])
    v.add('Streams에 처리 규칙이 저장됨', bool(steps))
    v.add('실제 ingest pipeline 자산 존재', bool(result.get('elasticsearch_assets', {}).get('ingestPipeline')))
    documents = hits(v, PROCESS_STREAM, {'terms': {'event.id': ['f08-error-proof', 'f08-info-proof']}})
    for identifier, level, status, latency, service in [
        ('f08-error-proof', 'error', 503, 175, 'checkout'),
        ('f08-info-proof', 'info', 200, 24, 'catalog'),
    ]:
        matched = [hit.get('_source', {}) for hit in documents
                   if field(hit.get('_source', {}), 'event.id') == identifier]
        v.add(identifier + ' 새 문서 존재', bool(matched))
        expected_message = f'level={level} status={status} duration={latency} service={service}'
        v.add(identifier + ' 추출 값과 원본 보존', bool(matched) and all(
            field(doc, 'log.level') == level and field(doc, 'service.name') == service
            and doc.get('message') == expected_message
            and timestamp(doc.get('@timestamp'), '2026-10-01T00:00:00Z') for doc in matched))
        v.add(identifier + ' long 숫자 변환', bool(matched) and all(
            type(field(doc, 'http.response.status_code')) is int
            and field(doc, 'http.response.status_code') == status
            and type(field(doc, 'event.duration_ms')) is int
            and field(doc, 'event.duration_ms') == latency for doc in matched))
        v.add(identifier + ' 조건부 alert', bool(matched) and all(
            field(doc, 'event.kind') == ('alert' if level == 'error' else None) for doc in matched))


def retention(v):
    result = kb_stream(v, RETENTION_STREAM)
    configured = result.get('stream', {}).get('ingest', {}).get('lifecycle', {})
    effective = result.get('effective_lifecycle', {})
    v.add('Streams DSL 직접 설정 7일', duration(configured.get('dsl', {}).get('data_retention')) == 7 * 86400
          and duration(effective.get('dsl', {}).get('data_retention')) == 7 * 86400)
    lifecycle = v.get('/_data_stream/' + RETENTION_STREAM + '/_lifecycle')
    item = next((x for x in lifecycle.get('data_streams', []) if x.get('name') == RETENTION_STREAM), {})
    cfg = item.get('lifecycle', {})
    v.add('Elasticsearch DSL 활성화 / 보존 7일', cfg.get('enabled') is True
          and duration(cfg.get('data_retention')) == 7 * 86400)
    stream = v.get('/_data_stream/' + RETENTION_STREAM).get('data_streams', [{}])[0]
    indices = [x['index_name'] for x in stream.get('indices', []) if 'index_name' in x]
    v.add('실제 rollover와 backing index 증가', len(indices) >= 2 and stream.get('generation', 0) >= 2)
    documents = hits(v, RETENTION_STREAM)
    for identifier in ['f09-seed-01', 'f09-seed-02', 'f09-seed-03']:
        seed = [hit for hit in documents if field(hit.get('_source', {}), 'event.id') == identifier]
        v.add(identifier + ' 이전 backing index에서 보존', bool(seed) and bool(indices)
              and all(hit.get('_index') in indices[:-1] for hit in seed))
    proof = [hit for hit in documents if field(hit.get('_source', {}), 'event.id') == 'f09-after-rollover']
    v.add('새 문서가 현재 write backing index에 저장됨', bool(proof) and bool(indices) and all(
        hit.get('_index') == indices[-1] and hit['_source'].get('message') == 'After rollover'
        and timestamp(hit['_source'].get('@timestamp'), '2026-10-01T00:00:01Z') for hit in proof))


def failures(v):
    result = kb_stream(v, FAILURE_STREAM)
    saved = result.get('stream', {}).get('ingest', {}).get('failure_store', {})
    effective = result.get('effective_failure_store', {})
    v.add('Streams failure store 보존 3일',
          duration(saved.get('lifecycle', {}).get('enabled', {}).get('data_retention')) == 3 * 86400
          and duration(effective.get('lifecycle', {}).get('enabled', {}).get('data_retention')) == 3 * 86400)
    options = v.get('/_data_stream/' + FAILURE_STREAM + '/_options')
    item = next((x for x in options.get('data_streams', []) if x.get('name') == FAILURE_STREAM), {})
    config = item.get('options', {}).get('failure_store', {})
    v.add('Elasticsearch failure store 활성화 / lifecycle 3일', config.get('enabled') is True
          and config.get('lifecycle', {}).get('enabled') is True
          and duration(config.get('lifecycle', {}).get('data_retention')) == 3 * 86400)
    failed = hits(v, FAILURE_STREAM + '::failures')
    marked = [hit.get('_source', {}) for hit in failed
              if field(hit.get('_source', {}), 'document.source.event.id') == 'f10-bad']
    v.add('실제 실패 문서와 매핑 오류 원인', bool(marked) and all(
        field(doc, 'document.index') == FAILURE_STREAM
        and field(doc, 'document.source.@timestamp') == 'not-a-date'
        and field(doc, 'document.source.message') == 'Invalid audit timestamp'
        and field(doc, 'error.type') == 'document_parsing_exception' for doc in marked))
    ordinary = hits(v, FAILURE_STREAM, {'terms': {'event.id': ['f10-bad', 'f10-good-proof']}})
    v.add('실패 문서는 일반 backing index에 없음', not any(
        field(hit.get('_source', {}), 'event.id') == 'f10-bad' for hit in ordinary))
    good = [hit.get('_source', {}) for hit in ordinary
            if field(hit.get('_source', {}), 'event.id') == 'f10-good-proof']
    v.add('오류 이후 정상 문서 색인 가능', bool(good) and all(
        doc.get('message') == 'Valid audit timestamp'
        and timestamp(doc.get('@timestamp'), '2026-10-01T00:00:02Z') for doc in good))


def state_check(v):
    handlers = {'f_stream_processing': processing, 'f_stream_retention': retention,
                'f_stream_failures': failures}
    handler = handlers.get(v.t['check'])
    if not handler:
        raise RuntimeError('알 수 없는 Streams 검증 유형입니다.')
    handler(v)


def query_check(v):
    state_check(v)
