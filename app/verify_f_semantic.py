"""Real state/result checks for F01-F03. No model invocation or student eval."""
from __future__ import annotations
import copy
import json
import math
import re
from pathlib import Path
from console import parse_console


def prepared():
    return json.loads((Path(__file__).resolve().parents[1] / 'data' /
                       'f_semantic_embeddings.json').read_text(encoding='utf-8'))


def walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def leaf(value):
    return value.get('value') if isinstance(value, dict) else value


def terms(body):
    return {(field, leaf(value)) for node in walk(body)
            for field, value in node.get('term', {}).items()}


def conjoined_terms(value):
    """Only count term predicates whose Boolean placement requires all of them."""
    if isinstance(value, list):
        groups = [conjoined_terms(item) for item in value]
        return set().union(*groups) if all(group is not None for group in groups) else None
    if not isinstance(value, dict):
        return None
    if set(value) == {'term'}:
        return {(field, leaf(item)) for field, item in value['term'].items()}
    if set(value) == {'bool'} and set(value['bool']) <= {'filter', 'must'}:
        return conjoined_terms(list(value['bool'].values()))
    return None


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(
        sum(x * x for x in a) * sum(y * y for y in b))


def reference(v):
    return [q for q in parse_console(v.t['solution'])
            if re.search(r'/_search(?:\?|$)', q.path)][-1]


def target(v, q):
    v.add('준비된 corpus / Search API', q.path.split('?')[0].rstrip('/') == '/f-semantic-corpus/_search')


def projected(v, hits):
    v.add('title/category만 문서 필드로 반환', bool(hits) and all(
        set(hit.get('_source', {})) | set(hit.get('fields', {})) == {'title', 'category'}
        for hit in hits))


def state_check(v):
    from verify import equivalent, flatten
    if v.t['check'] != 'f_semantic_mapping':
        raise ValueError('Unknown semantic state check ' + v.t['check'])
    p = v.props('f-semantic-target')
    vector = p.get('embedding', {})
    v.add('384차원 / cosine / indexed dense_vector', vector.get('type') == 'dense_vector'
          and vector.get('dims') == 384 and vector.get('index', True) is True
          and vector.get('similarity', 'cosine') == 'cosine')
    required = {'title': 'text', 'content': 'text', 'category': 'keyword',
                'language': 'keyword', 'vector_model': 'keyword', 'published': 'boolean'}
    v.add('문서와 메타데이터 필드 매핑', all(p.get(name, {}).get('type') == kind
          for name, kind in required.items()))
    settings = flatten(v.get('/f-semantic-target/_settings')['f-semantic-target']['settings'])
    v.add('primary 1 / replica 0', str(settings.get('index.number_of_shards')) == '1'
          and str(settings.get('index.number_of_replicas')) == '0')
    v.add('생성 시 원본 vector _source 저장',
          str(settings.get('index.mapping.exclude_source_vectors')).lower() == 'false')
    orig = {d['_id']: d['_source'] for d in prepared()['documents']}
    docs = v.docs('f-semantic-target')
    v.add('32건 ID 및 원본 문서·벡터 보존', len(docs) == 32 and equivalent(orig, docs))
    v.add('원본 source와 준비된 corpus 유지', equivalent(v.docs('f-semantic-source'), orig)
          and equivalent(v.docs('f-semantic-corpus'), orig))
    result = v.get('/f-semantic-target/_search', body={'size': 1, '_source': ['title'],
        'knn': {'field': 'embedding', 'query_vector': prepared()['queries']['latency']['embedding'],
                'k': 1, 'num_candidates': 32}})
    v.add('실제 kNN 검색 가능한 목적지', len(result.get('hits', {}).get('hits', [])) == 1)


def query_check(v):
    from verify import equivalent
    q = v.submitted()
    body = q.body or {}
    target(v, q)
    data = prepared()
    kind = v.t['check']
    if kind == 'f_semantic_knn':
        specs = [node['knn'] for node in walk(body) if isinstance(node.get('knn'), dict)]
        spec = specs[0] if len(specs) == 1 else {}
        expected_vector = data['queries']['latency']['embedding']
        v.add('embedding / 제공된 동일 모델 query vector',
              spec.get('field') == 'embedding' and equivalent(spec.get('query_vector'), expected_vector))
        v.add('k:5 / num_candidates:32 / size:5', spec.get('k') == 5
              and spec.get('num_candidates') == 32 and body.get('size', 10) == 5)
        required_filters = {('category', 'search'), ('language', 'en'), ('published', True)}
        v.add('세 메타데이터 조건을 kNN pre-filter로 적용',
              required_filters <= terms(spec.get('filter', {})) and 'post_filter' not in body)
        v.add('순수 kNN 검색 / 별도 점수 쿼리 없음',
              'retriever' not in body and (not body.get('query') or body['query'].get('knn') == spec)
              and not body.get('sort'))
        hits = v.run_search(q).get('hits', {}).get('hits', [])
        allowed = {d['_id']: d['_source'] for d in data['documents']
                   if d['_source']['category'] == 'search' and d['_source']['language'] == 'en'
                   and d['_source']['published'] is True}
        ranked = sorted(((cosine(expected_vector, source['embedding']), id)
                         for id, source in allowed.items()), reverse=True)
        expected_ids = {id for _, id in ranked[:5]}
        v.add('허용된 후보 중 실제 cosine top-5', len(hits) == 5
              and {hit['_id'] for hit in hits} == expected_ids,
              '제공된 32개 벡터의 직접 cosine 계산과 비교합니다. corpus는 비양자화 HNSW로 준비합니다.')
        expected = v.run_search(reference(v)).get('hits', {}).get('hits', [])
        v.add('실제 검색 점수와 순위', len(hits) == 5 and len(expected) == 5
              and equivalent([hit.get('_score') for hit in hits], [hit.get('_score') for hit in expected]))
        projected(v, hits)
        return
    if kind == 'f_semantic_rrf':
        spec = body.get('retriever', {}).get('rrf', {})
        children = spec.get('retrievers', [])
        standard = [child.get('standard', {}) for child in children if 'standard' in child]
        knn = [child.get('knn', {}) for child in children if 'knn' in child]
        v.add('RRF의 standard와 knn 두 retriever',
              len(children) == 2 and len(standard) == 1 and len(knn) == 1)
        boolean = standard[0].get('query', {}).get('bool', {}) if standard else {}
        multi = next((node['multi_match'] for node in walk(boolean.get('must', []))
                      if 'multi_match' in node), {})
        v.add('BM25 semantic search / title^2 + content', multi.get('query') == 'semantic search'
              and set(multi.get('fields', [])) in ({'title^2', 'content'}, {'title^2.0', 'content'}))
        vector = knn[0] if knn else {}
        v.add('동일 모델의 hybrid query vector / k:12 / 후보 32',
              vector.get('field') == 'embedding'
              and equivalent(vector.get('query_vector'), data['queries']['hybrid']['embedding'])
              and vector.get('k') == 12 and vector.get('num_candidates') == 32)
        restrictions = {('language', 'en'), ('published', True)}
        v.add('두 retriever 모두 공개 영어 문서로 후보 제한',
              conjoined_terms(boolean.get('filter', [])) == restrictions
              and conjoined_terms(vector.get('filter', {})) == restrictions
              and 'post_filter' not in body)
        v.add('rank_constant:20 / rank_window_size:12 / size:5',
              spec.get('rank_constant') == 20 and spec.get('rank_window_size') == 12 and body.get('size', 10) == 5)
        v.add('추가 filter·sort·점수 쿼리 없음',
              not body.get('query') and not body.get('sort') and 'post_filter' not in body
              and not spec.get('filter')
              and conjoined_terms(boolean.get('filter', [])) == restrictions
              and conjoined_terms(vector.get('filter', {})) == restrictions)
        actual = v.run_search(q).get('hits', {}).get('hits', [])
        ref = reference(v)
        ref_body = copy.deepcopy(ref.body)
        ref_body['size'] = 12
        expected = v.run_search(ref, ref_body).get('hits', {}).get('hits', [])
        score_map = {hit['_id']: hit.get('_score') for hit in expected}
        cutoff = expected[4].get('_score') if len(expected) >= 5 else None
        valid = len(actual) == 5 and len({hit['_id'] for hit in actual}) == 5 and cutoff is not None
        valid = valid and all(hit['_id'] in score_map
            and isinstance(score_map[hit['_id']], (int, float))
            and score_map[hit['_id']] >= cutoff - 1e-6
            and equivalent(hit.get('_score'), score_map[hit['_id']]) for hit in actual)
        valid = valid and equivalent([hit.get('_score') for hit in actual],
                                    [hit.get('_score') for hit in expected[:5]])
        v.add('실제 RRF top-5 문서와 fusion 점수', valid,
              '참조 RRF 결과의 문서·점수로 비교하며 완전 동점 문서는 특정 ID 순서를 강제하지 않습니다.')
        projected(v, actual)
        return
    raise ValueError('Unknown semantic query check ' + kind)
