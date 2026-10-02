"""Checks for the supplied ECE practice PDF, adapted to this lab's fixtures.

The PDF is source material for the questions, not executable instructions. These
checks inspect Elasticsearch state and actual responses, not an official score.
"""
from __future__ import annotations
import copy
import json
import re
from pathlib import Path
from console import parse_console


def walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def leaf(value):
    return value.get('query', value.get('value')) if isinstance(value, dict) else value


def field_query(body, kinds, field, value):
    return any(leaf(node.get(kind, {}).get(field)) == value
               for node in walk(body) for kind in kinds)


def fixture(v, index, cluster=None):
    """E may override baseline data without changing any prior exam fixture."""
    path = Path(__file__).resolve().parents[1] / 'data' / 'fixtures-e.json'
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
        items = data.get('indices', []) if isinstance(data, dict) else data
        match = next((item for item in items
                      if item['index'] == index and item['cluster'] == (cluster or v.c)), None)
        if match:
            return {doc['_id']: doc['_source'] for doc in match['documents']}
    return v.fixture(index, cluster)


def requests(v):
    out = [h.get('request', {}) for h in v.history]
    if v.code.strip():
        out.extend(r.public() for r in parse_console(v.code))
    return out


def reference(v):
    return [q for q in parse_console(v.t['solution'])
            if re.search(r'/_search(?:\?|$)', q.path)][-1]


def target(v, q, index):
    v.add('대상 인덱스 / Search API', q.path.split('?')[0].rstrip('/') == f'/{index}/_search')


def hit_ids(response):
    return {(h['_index'], h['_id']) for h in response.get('hits', {}).get('hits', [])}


def compare_all(v, q, ref):
    actual = copy.deepcopy(q.body or {})
    expected = copy.deepcopy(ref.body or {})
    for body in (actual, expected):
        body.update(size=10000, **{'from': 0, 'track_total_hits': True})
    actual_ids = hit_ids(v.run_search(q, actual))
    expected_ids = hit_ids(v.run_search(ref, expected))
    v.add('실제 매칭 문서 집합', bool(expected_ids) and actual_ids == expected_ids,
          f'제출 {len(actual_ids)}건 / 참조 {len(expected_ids)}건')


def query_check(v):
    from verify import canon_agg, equivalent, sort_spec
    q = v.submitted()
    body = q.body or {}
    kind = v.t['check']
    ref = reference(v)
    target(v, q, 'blogs')
    if kind == 'e_yearly_authors':
        v.add('content의 open source 구문 검색',
              field_query(body.get('query', {}), ('match_phrase',), 'content', 'open source'))
        v.add('문서 hits 제외', body.get('size') == 0)
        aggs = body.get('aggs', body.get('aggregations', {}))
        yearly = [node for node in walk(aggs)
                  if node.get('date_histogram', {}).get('field') == 'publish_date'
                  and node.get('date_histogram', {}).get('calendar_interval') in ('year', '1y')]
        v.add('publish_date의 calendar year 집계', bool(yearly))
        v.add('각 연도의 authors.uid 고유 개수', any(
            node.get('cardinality', {}).get('field') == 'authors.uid'
            for year in yearly for node in walk(year.get('aggs', year.get('aggregations', {})))))
        actual = v.run_search(q).get('aggregations', {})
        expected = v.run_search(ref).get('aggregations', {})
        v.add('연도별 버킷·문서 수·고유 author 수',
              bool(actual) and bool(expected) and equivalent(canon_agg(actual), canon_agg(expected)),
              '집계 이름은 자유이며 실제 참조 결과와 비교합니다.')
        return
    if kind == 'e_certified':
        boolean = body.get('query', {}).get('bool', {})
        matches = [node.get('match', {}).get('content') for node in walk(boolean.get('must', []))]
        v.add('content certified engineer가 필수 OR 검색', any(
            leaf(item) == 'certified engineer'
            and (not isinstance(item, dict) or item.get('operator', 'or').lower() == 'or')
            for item in matches))
        v.add('구문 일치는 선택적 점수 조건',
              bool(boolean.get('must'))
              and boolean.get('minimum_should_match', 0) in (0, '0')
              and field_query(boolean.get('should', []), ('match_phrase',), 'content', 'certified engineer'))
        ranges = [node.get('range', {}).get('publish_date', {})
                  for node in walk(boolean.get('filter', []))]
        v.add('최근 2년은 filter로 제한', any(
            item.get('gte') in ('now-2y/d', 'now/d-2y') and item.get('lte') == 'now' for item in ranges))
        v.add('3번째 페이지 / 페이지당 5건', body.get('from', 0) == 10 and body.get('size', 10) == 5)
        v.add('_score 내림차순 다음 _doc 오름차순',
              sort_spec(body) == [('_score', 'desc'), ('_doc', 'asc')])
        v.add('content 하이라이트 설정', 'content' in body.get('highlight', {}).get('fields', {}))
        compare_all(v, q, ref)
        actual = v.run_search(q).get('hits', {}).get('hits', [])
        expected = v.run_search(ref).get('hits', {}).get('hits', [])
        v.add('실제 3번째 페이지', len(actual) == 5 and len(expected) == 5
              and equivalent([h.get('sort') for h in actual], [h.get('sort') for h in expected]),
              '실제 score와 _doc 정렬 값으로 비교하며, 완전 동률 문서 ID는 따로 강제하지 않습니다.')
        v.add('실제 content 하이라이트 응답',
              bool(actual) and all(h.get('highlight', {}).get('content') for h in actual))
        return
    raise ValueError('Unknown E query check ' + kind)


def primary_fields(properties, prefix=''):
    """Visit source fields, excluding generated multi-fields."""
    for name, mapping in properties.items():
        path = f'{prefix}.{name}' if prefix else name
        if 'properties' in mapping:
            yield from primary_fields(mapping['properties'], path)
        else:
            yield path, mapping


def string_paths(value, prefix=''):
    if isinstance(value, dict):
        for name, item in value.items():
            path = f'{prefix}.{name}' if prefix else name
            yield from string_paths(item, path)
    elif isinstance(value, list):
        for item in value:
            yield from string_paths(item, prefix)
    elif isinstance(value, str):
        yield prefix


def keyword_template(mapping):
    for item in mapping.get('dynamic_templates', []):
        spec = next(iter(item.values()), {})
        if (spec.get('match_mapping_type') == 'string'
                and spec.get('match', '*') == '*'
                and spec.get('path_match', '*') == '*'
                and not any(key in spec for key in ('unmatch', 'path_unmatch'))):
            return spec.get('mapping', {}).get('type') == 'keyword' and not spec.get('mapping', {}).get('fields')
    return False


def security(v):
    users = v.get('/_security/user/task1')
    user = users.get('task1', {})
    role_names = user.get('roles', [])
    roles = v.get('/_security/role/' + ','.join(role_names)) if role_names else {}
    all_roles = [roles[name] for name in role_names if name in roles]
    v.add('task1 사용자 / 이름 / 이메일',
          bool(user) and user.get('enabled', True)
          and user.get('full_name') == 'Elastic Search'
          and user.get('email') == 'elastic@search.com')
    v.add('full cluster privileges', any('all' in role.get('cluster', []) for role in all_roles))
    indices = [item for role in all_roles for item in role.get('indices', [])]
    v.add('모든 인덱스 read', any('*' in item.get('names', [])
          and 'read' in item.get('privileges', []) and not item.get('query')
          and not item.get('field_security') for item in indices))
    v.add('task1 인덱스 full privileges', any('task1' in item.get('names', [])
          and 'all' in item.get('privileges', []) and not item.get('query')
          and not item.get('field_security') for item in indices))
    read_only = {'read', 'read_cross_cluster', 'view_index_metadata'}
    v.add('task1 이외에는 읽기 전용', bool(indices) and all(
        set(item.get('names', [])) <= {'task1'}
        or set(item.get('privileges', [])) <= read_only for item in indices))
    applications = [item for role in all_roles for item in role.get('applications', [])]
    v.add('Default space의 Kibana 전체 기능 All', any(
        item.get('application') == 'kibana-.kibana'
        and 'space:default' in item.get('resources', [])
        and bool({'space_all', 'all'} & set(item.get('privileges', []))) for item in applications))
    auth = v.es.get(v.c, '/_security/_authenticate', auth=('task1', 'youknowforsearch'))
    v.add('지정 비밀번호로 실제 인증', auth['status'] == 200
          and auth.get('body', {}).get('username') == 'task1')


def blog_mapping(v):
    mapping = v.get('/task3/_mapping')['task3']['mappings']
    p = mapping.get('properties', {})
    v.add('원본 blogs 전체 문서 / 필드 보존', v.docs('task3') == fixture(v, 'blogs'))
    v.add('새 문자열은 keyword only', keyword_template(mapping))
    exceptions = {'content', 'title', 'authors.full_name'}
    source_strings = {name for doc in fixture(v, 'blogs').values() for name in string_paths(doc)}
    fields = dict(primary_fields(p))
    # Date detection precedes the string template in the PDF reference solution.
    string_fields = [fields.get(name, {}) for name in source_strings - exceptions
                     if fields.get(name, {}).get('type') != 'date']
    v.add('그 외 문자열 keyword only', bool(string_fields) and all(
        spec.get('type') == 'keyword' and not spec.get('fields') for spec in string_fields))
    content = p.get('content', {})
    v.add('content text / content_analyzer',
          content.get('type') == 'text' and content.get('analyzer') == 'content_analyzer')
    v.add('content.eng text / english', content.get('fields', {}).get('eng', {}).get('type') == 'text'
          and content.get('fields', {}).get('eng', {}).get('analyzer') == 'english')
    title = p.get('title', {})
    v.add('title text / standard / search_as_you_type', title.get('type') == 'text'
          and title.get('analyzer', 'standard') == 'standard'
          and title.get('fields', {}).get('search', {}).get('type') == 'search_as_you_type')
    author = p.get('authors', {}).get('properties', {}).get('full_name', {})
    v.add('authors.full_name text / standard',
          author.get('type') == 'text' and author.get('analyzer', 'standard') == 'standard')
    settings = v.get('/task3/_settings')['task3']['settings']['index']
    analyzer = settings.get('analysis', {}).get('analyzer', {}).get('content_analyzer', {})
    v.add('html_strip / standard tokenizer / lowercase', analyzer.get('tokenizer') == 'standard'
          and analyzer.get('char_filter') == ['html_strip'] and analyzer.get('filter') == ['lowercase'])
    analyzed = v.es.require(v.c, 'POST', '/task3/_analyze',
                            {'field': 'content', 'text': '<b>HELLO</b> Open SOURCE'})
    v.add('실제 HTML 제거와 소문자 토큰',
          [item.get('token') for item in analyzed.get('tokens', [])] == ['hello', 'open', 'source'])


def traffic(v):
    from verify import flatten
    orig = fixture(v, 'web_traffic')
    docs = v.docs('task4')
    v.add('원본 전체 문서 ID 보존', bool(orig) and set(docs) == set(orig))
    settings = flatten(v.get('/task4/_settings')['task4']['settings'])
    v.add('primary 6 / replica 0', str(settings.get('index.number_of_shards')) == '6'
          and str(settings.get('index.number_of_replicas')) == '0')
    p = v.props('task4')
    v.add('geo.location geo_point', p.get('geo', {}).get('properties', {}).get('location', {}).get('type') == 'geo_point')
    allowed = {'geo.location': 'geo_point', '@timestamp': 'date', 'runtime_ms': 'long', 'bytes_sent': 'long'}
    fields = dict(primary_fields(p))
    v.add('요구된 모든 필드 타입 / keyword only', all(
        spec.get('type') == allowed.get(name, 'keyword') and not spec.get('fields')
        for name, spec in fields.items())
        and all(fields.get(name, {}).get('type') == kind for name, kind in allowed.items()))
    pipelines = v.get('/_ingest/pipeline')
    v.add('user_Agent에 실제 user_agent processor', any(
        node.get('user_agent', {}).get('field') == 'user_Agent'
        for pipeline in pipelines.values() for node in walk(pipeline.get('processors', []))))
    ids = list(orig)
    result = v.es.require(v.c, 'POST', '/_ingest/pipeline/_simulate', {
        'pipeline': {'processors': [{'user_agent': {'field': 'user_Agent', 'ignore_missing': True}}]},
        'docs': [{'_source': copy.deepcopy(orig[i])} for i in ids]})
    expected = {}
    for i, item in zip(ids, result.get('docs', [])):
        source = item.get('doc', {}).get('_source', {})
        source.pop('is_https', None)
        source.pop('user_Agent', None)
        lat = source.pop('geoip_location_lat', None)
        lon = source.pop('geoip_location_lon', None)
        if lat is not None or lon is not None:
            source['geo'] = {'location': {}}
            if lat is not None:
                source['geo']['location']['lat'] = lat
            if lon is not None:
                source['geo']['location']['lon'] = lon
        expected[i] = source
    v.add('필드 제거·좌표 이동·user-agent 파싱 및 데이터 보존',
          len(expected) == len(orig) and docs == expected,
          'Elasticsearch user_agent processor의 실제 결과와 비교합니다.')


def nested(v):
    v.add('authors nested 매핑', v.props('task5').get('authors', {}).get('type') == 'nested')
    orig = fixture(v, 'blogs')
    v.add('원본 blogs 전체 문서 / 필드 보존', v.docs('task5') == orig)
    q = v.submitted()
    target(v, q, 'task5')
    clauses = [node['nested'].get('query', {}) for node in walk(q.body or {})
               if node.get('nested', {}).get('path') == 'authors']
    v.add('한 nested author 안에서 두 조건 검색', any(
        field_query(clause, ('match', 'match_phrase', 'term'), 'authors.first_name', 'david')
        and field_query(clause, ('match', 'match_phrase', 'term'), 'authors.job_title', 'engineer')
        for clause in clauses))
    body = copy.deepcopy(q.body or {})
    body.update(size=10000, **{'from': 0})
    hits = v.run_search(q, body).get('hits', {}).get('hits', [])
    expected = {i for i, doc in orig.items() if any(
        a.get('first_name', '').lower() == 'david'
        and 'engineer' in re.findall(r'\w+', a.get('job_title', '').lower())
        for a in doc.get('authors', []))}
    v.add('동일 author가 david와 engineer를 만족하는 실제 결과',
          bool(expected) and {h['_id'] for h in hits} == expected)


def categories(v):
    orig = fixture(v, 'blogs')
    refs = {doc['uid']: doc['title'] for doc in fixture(v, 'categories').values()}
    expected = {}
    for i, doc in orig.items():
        output = copy.deepcopy(doc)
        cat = output.pop('category', None)
        if cat in refs:
            output['categories'] = {'uid': cat, 'title': refs[cat]}
        expected[i] = output
    docs = v.docs('task6')
    v.add('원본 전체 문서 ID 유지 / 없는 category 처리', set(docs) == set(orig))
    v.add('categories.uid/title 보강 / category 제거 / 다른 필드 보존', docs == expected)
    pipelines = v.get('/_ingest/pipeline')
    enrich = [node.get('enrich', {}) for pipeline in pipelines.values()
              for node in walk(pipeline.get('processors', [])) if 'enrich' in node]
    v.add('category에서 categories로 enrich processor 사용', any(
        item.get('field') == 'category' and item.get('target_field') == 'categories'
        and item.get('ignore_missing') is True for item in enrich))


def ccr(v):
    info = v.get('/ccr_blogs/_ccr/info').get('follower_indices', [])
    item = info[0] if info else {}
    v.add('cluster2의 blogs를 ccr_blogs로 follow',
          item.get('leader_index') == 'blogs' and item.get('remote_cluster') == 'cluster2')
    v.add('follower active', item.get('status') == 'active', str(item.get('status')))
    expected = fixture(v, 'blogs', 'cluster2')
    v.add('원격 원본 7건 및 follower 동기화', len(expected) == 7
          and v.docs('blogs', 'cluster2') == expected and v.docs('ccr_blogs') == expected,
          '초기 복제 중이면 잠시 후 다시 검증하세요.')


def stream(v):
    from verify import duration, flatten
    template = v.get('/_index_template/my-metrics-template')['index_templates'][0]['index_template']
    v.add('data stream 패턴 / component template 사용',
          'data_stream' in template and 'my.metrics-*-*' in template.get('index_patterns', [])
          and 'metrics-mappings' in template.get('composed_of', []))
    resolved = v.es.require(v.c, 'POST', '/_index_template/_simulate/my-metrics-template')['template']
    settings = flatten(resolved.get('settings', {}))
    policy_name = settings.get('index.lifecycle.name')
    v.add('my-metrics-policy 연결', policy_name == 'my-metrics-policy')
    phases = v.get('/_ilm/policy/my-metrics-policy')['my-metrics-policy']['policy']['phases']
    rollover = phases.get('hot', {}).get('actions', {}).get('rollover', {})
    v.add('Hot rollover 최대 나이 2분', duration(rollover.get('max_age')) == 120)
    warm = phases.get('warm', {})
    v.add('Warm 즉시 이동 / readonly', 'warm' in phases
          and duration(warm.get('min_age', '0ms')) == 0 and 'readonly' in warm.get('actions', {}))
    v.add('Cold rollover 후 3분 / 무기한 유지', duration(phases.get('cold', {}).get('min_age')) == 180
          and 'delete' not in phases)
    data = v.get('/_data_stream/my.metrics-system-dev').get('data_streams', [])
    item = data[0] if data else {}
    v.add('실제 my.metrics-system-dev 데이터 스트림', item.get('name') == 'my.metrics-system-dev'
          and item.get('template') == 'my-metrics-template' and bool(item.get('indices')))
    backing = [i['index_name'] for i in item.get('indices', [])]
    index_settings = v.get('/' + ','.join(backing) + '/_settings') if backing else {}
    v.add('실제 backing index에 ILM 정책 적용', bool(backing) and all(
        index_settings.get(name, {}).get('settings', {}).get('index', {}).get('lifecycle', {}).get('name')
        == 'my-metrics-policy' for name in backing))


def searchable(v):
    from verify import flatten
    repo = v.get('/_snapshot/snap-repo')['snap-repo']
    v.add('공유 파일 시스템 repository / 실습 경로', repo.get('type') == 'fs'
          and repo.get('settings', {}).get('location') == '/mnt/elastic-snapshots/ece-practice-search')
    shots = v.get('/_snapshot/snap-repo/moreblogs_snapshot').get('snapshots', [])
    shot = shots[0] if shots else {}
    v.add('moreblogs만 포함한 성공 스냅샷', shot.get('state') == 'SUCCESS'
          and set(shot.get('indices', [])) == {'moreblogs'})
    settings = flatten(v.get('/moreblogs/_settings')['moreblogs']['settings'])
    v.add('moreblogs를 searchable snapshot으로 mount', settings.get('index.store.type') == 'snapshot'
          and settings.get('index.store.snapshot.repository_name') == 'snap-repo'
          and settings.get('index.store.snapshot.snapshot_name') == 'moreblogs_snapshot')
    v.add('스냅샷 전체 문서 보존', v.docs('moreblogs') == fixture(v, 'moreblogs'))
    q = v.submitted()
    target(v, q, 'moreblogs')
    v.add('tags.product elasticsearch 검색',
          field_query((q.body or {}).get('query', {}), ('match', 'match_phrase', 'term'),
                      'tags.product', 'elasticsearch'))
    compare_all(v, q, reference(v))


def state_check(v):
    checks = {'e_security': security, 'e_blog_mapping': blog_mapping,
              'e_traffic': traffic, 'e_nested': nested, 'e_categories': categories,
              'e_ccr': ccr, 'e_stream': stream, 'e_searchable': searchable}
    if v.t['check'] not in checks:
        raise ValueError('Unknown E state check ' + v.t['check'])
    checks[v.t['check']](v)
