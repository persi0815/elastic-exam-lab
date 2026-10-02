"""F01-F03: real pretrained embeddings, prepared once outside Elasticsearch.

Rebuilding the ordinary lab reads committed vectors and never downloads a model.
See prepare_f_embeddings.py to reproduce their model revision and checksums.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path

MODEL_ID = 'sentence-transformers/all-MiniLM-L6-v2'
DENSE_DOCS = 'https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector'
KNN_DOCS = 'https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-knn-query'
RRF_DOCS = 'https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/rrf-retriever'
MODEL_DOCS = 'https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2'
SEMANTIC_TEXT_DOCS = 'https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/semantic-text-reference'

# Author-written sample text: no real customer data or copied documentation.
ROWS = [
    ('search', 'en', True, 'Reduce slow search responses', 'Diagnose query latency with the profile API. Narrow expensive filters and avoid retrieving large unnecessary fields.'),
    ('search', 'en', True, 'Improve response time for dashboards', 'Investigate slow searches by examining shard execution times, request caches and the number of concurrent queries.'),
    ('search', 'en', True, 'Expensive wildcard requests', 'Leading wildcards scan many terms. Use a suitable field mapping and more selective queries to make searches faster.'),
    ('search', 'en', True, 'Limit the result payload', 'Return only the title and summary instead of the entire document. Smaller search responses reduce network transfer and client processing.'),
    ('search', 'en', True, 'Measure shard request latency', 'Search profiling identifies expensive query clauses and aggregations. Compare measurements before and after an optimization.'),
    ('search', 'en', True, 'Tune vector retrieval candidates', 'Nearest neighbor retrieval balances recall and latency. Increase candidates carefully and measure search quality alongside response time.'),
    ('search', 'en', True, 'Find answers by meaning', 'A sentence encoder maps related questions to nearby vectors even when their words differ. Retrieve useful passages by cosine similarity.'),
    ('search', 'en', True, 'Semantic search with supplied vectors', 'Semantic search uses an embedding model to represent text meaning. Index the document embeddings and query with a vector produced by the same model.'),
    ('search', 'en', True, 'Hybrid semantic search ranking', 'Hybrid search combines lexical relevance and semantic search. Reciprocal rank fusion joins ranked lists without comparing raw BM25 and vector scores.'),
    ('search', 'en', True, 'Keyword relevance for exact names', 'BM25 matches the terms in a question to document text. Exact product names and identifiers may be easier to retrieve with lexical search.'),
    ('search', 'en', True, 'Vector metadata restrictions', 'Apply tenant and publication restrictions while nearest neighbor retrieval finds candidates. A filter applied after retrieval can return too few hits.'),
    ('search', 'en', True, 'Semantic search evaluation checklist', 'Evaluate semantic search with representative questions. Measure useful results, language coverage and ranking quality before changing the model.'),
    ('search', 'en', True, 'Search cache and repeated requests', 'Repeated identical search requests can benefit from caches. Benchmark realistic workloads because a cache hit does not represent every user query.'),
    ('search', 'en', True, 'Choose a useful retrieval window', 'A larger candidate window gives hybrid retrieval more documents to fuse. Keep the final page small and evaluate the tradeoff against latency.'),
    ('search', 'en', False, 'Unpublished latency diagnosis', 'Find help diagnosing slow searches and improving query response times. This draft contains internal performance experiments and must stay out of published results.'),
    ('search', 'fr', True, 'Requêtes lentes et temps de réponse', 'Analyser les recherches lentes, réduire les filtres coûteux et mesurer le temps de réponse des requêtes.'),
    ('observability', 'en', True, 'Trace a slow checkout', 'Follow distributed traces across checkout services. Identify database waits and network calls that increase customer transaction latency.'),
    ('observability', 'en', True, 'Monitor application error rates', 'Group failures by service and environment. Alert on a sustained increase in errors rather than an isolated request.'),
    ('observability', 'en', True, 'Read structured application logs', 'Parse timestamp, service name and severity from incoming logs. Search the resulting fields when diagnosing application incidents.'),
    ('observability', 'en', True, 'Choose infrastructure metrics', 'CPU, memory pressure and disk utilization describe host health. Correlate these measurements with service response time.'),
    ('observability', 'en', True, 'Track latency percentiles', 'Percentiles show how quickly typical and unusually slow requests finish. An average can hide the long tail experienced by some customers.'),
    ('observability', 'en', False, 'Draft service performance report', 'Investigate slow searches and service response time. The unpublished report includes production traces and detailed incident analysis.'),
    ('security', 'en', True, 'Grant the least required privileges', 'Separate cluster privileges from index privileges. Give an analyst read access to the permitted data without granting write permissions.'),
    ('security', 'en', True, 'Rotate application API keys', 'Replace old application credentials with new API keys. Revoke unused keys and use a restricted role descriptor.'),
    ('security', 'en', True, 'Restrict document visibility', 'Tenant restrictions must apply consistently to lexical and vector retrieval. A result from another tenant is unacceptable even when highly relevant.'),
    ('security', 'en', True, 'Encrypt traffic between nodes', 'Transport encryption protects cluster communications. Keep certificate names, trust configuration and renewal procedures consistent.'),
    ('storage', 'en', True, 'Restore a retained snapshot', 'Register the shared repository and inspect the snapshot before restoring an index. Verify the recovered document count and health.'),
    ('storage', 'en', True, 'Rollover a log data stream', 'A data stream routes append-only events to a write index. Rollover opens a new backing index when age or size conditions are met.'),
    ('storage', 'en', True, 'Retain recent data in hot storage', 'Use a lifecycle policy to move old indices to less expensive tiers. Keep frequently searched data on a tier appropriate for its workload.'),
    ('storage', 'en', True, 'Avoid oversized shards', 'Shard sizes affect recovery time and storage management. Choose a rollover threshold based on measurements from the actual workload.'),
    ('search', 'en', True, 'Semantic search field naming', 'The words semantic search also appear in this glossary. It lists field names and configuration labels but does not explain how meaning-based retrieval works.'),
    ('search', 'en', True, 'Paraphrases and useful passages', 'Questions with different wording can ask for the same information. Compare sentence embeddings to locate a passage that answers the underlying question.'),
]

QUERY_TEXTS = {
    'latency': 'Find help diagnosing slow searches and improving query response times.',
    'hybrid': 'semantic search',
}


def raw_documents():
    return [{'_id': f'guide-{i:02d}', '_source': {
        'category': category, 'language': language, 'published': published,
        'title': title, 'content': content, 'vector_model': MODEL_ID,
    }} for i, (category, language, published, title, content) in enumerate(ROWS, 1)]


def request(method, path, body=None):
    if body is None:
        return f'{method} {path}'
    # Keep supplied 384-value query vectors on one line in the example Console.
    text = json.dumps(body, ensure_ascii=False, indent=2)
    import re
    text = re.sub(r'"query_vector": \[\s*([-\d.eE+,\s]+)\s*\]',
                  lambda match: '"query_vector": [' + ', '.join(
                      part.strip() for part in match.group(1).split(',')) + ']', text)
    return f'{method} {path}\n{text}'


def build(data):
    provenance = data['provenance']
    documents = data['documents']
    vectors = data['queries']
    properties = {'title': {'type': 'text'}, 'content': {'type': 'text'},
                  'category': {'type': 'keyword'}, 'language': {'type': 'keyword'},
                  'published': {'type': 'boolean'}, 'vector_model': {'type': 'keyword'},
                  'embedding': {'type': 'dense_vector', 'dims': 384, 'index': True, 'similarity': 'cosine',
                                'index_options': {'type': 'hnsw'}}}
    raw_properties = copy.deepcopy(properties)
    raw_properties['embedding'] = {'type': 'float'}
    dense_settings = {'number_of_shards': 1, 'number_of_replicas': 0,
                      'index.mapping.exclude_source_vectors': False}
    meta = {'embedding_provenance': provenance}
    fixtures = [
        {'cluster': 'cluster1', 'index': 'f-semantic-source',
         'settings': {'number_of_shards': 1, 'number_of_replicas': 0},
         'mappings': {'properties': raw_properties, '_meta': meta}, 'documents': copy.deepcopy(documents)},
        {'cluster': 'cluster1', 'index': 'f-semantic-corpus', 'settings': dense_settings,
         'mappings': {'properties': properties, '_meta': meta}, 'documents': copy.deepcopy(documents)},
        {'cluster': 'cluster1', 'index': 'f-semantic-queries',
         'settings': {'number_of_shards': 1, 'number_of_replicas': 0},
         'mappings': {'properties': {'text': {'type': 'text'}, 'embedding': {'type': 'float'}}, '_meta': meta},
         'documents': [{'_id': key, '_source': {'text': value['text'], 'embedding': value['embedding']}}
                       for key, value in vectors.items()]},
    ]
    common_notes = [
        f'작성한 합성 안내문을 {MODEL_ID}({provenance["revision"][:12]}, Apache-2.0)로 실제 인코딩한 384차원 벡터다. 평균 pooling과 L2 정규화를 적용했다. 모델의 품질을 공식 시험 점수로 평가하는 문항은 아니다.',
        '이 Docker는 ML 노드가 꺼져 있다. 문서·질의 embedding은 이미 준비되어 있으며 모델 다운로드나 외부 inference API 없이 검색한다. semantic_text의 자동 inference 설정은 이 실습 범위에 포함하지 않는다.',
        '작은 32건 corpus는 양자화하지 않은 HNSW로 준비했다. 자동 검증은 실제 벡터·RRF 검색 결과를 확인하며 대규모 데이터의 ANN recall을 보장하는 벤치마크가 아니다.',
    ]

    def task(number, title, topic, requirements, datasets, solution, kind, check, docs, notes, hint):
        return {'id': f'F{number:02d}', 'set': 'F', 'number': number, 'title': title, 'topic': topic,
                'requirements': requirements, 'datasets': datasets, 'solution': solution,
                'kind': kind, 'check': check, 'cluster': 'cluster1', 'answer': '',
                'notes': common_notes + notes, 'hint': hint, 'reconstructed': False,
                'intro': '실제 Elasticsearch 9.3.8에서 실행하는 자체 제작 모의 문항입니다. 공식 기출 복원본이 아닙니다.',
                'source': {'document': None, 'pages': [], 'label': docs[0][0], 'url': docs[0][1]},
                'references': [{'label': label, 'url': url} for label, url in docs]
                              + [{'label': 'Embedding 모델과 라이선스', 'url': MODEL_DOCS},
                                 {'label': 'semantic_text와 inference 범위', 'url': SEMANTIC_TEXT_DOCS}]}

    mapping_solution = '\n\n'.join([
        request('PUT', 'f-semantic-target', {'settings': dense_settings, 'mappings': {'properties': properties}}),
        request('POST', '_reindex', {'source': {'index': 'f-semantic-source'}, 'dest': {'index': 'f-semantic-target'}}),
        request('GET', 'f-semantic-target/_mapping'), request('GET', 'f-semantic-target/_count'),
    ])
    prefilter = {'bool': {'filter': [{'term': {'category': 'search'}},
                                    {'term': {'language': 'en'}}, {'term': {'published': True}}]}}
    knn_body = {'size': 5, '_source': ['title', 'category'], 'knn': {
        'field': 'embedding', 'query_vector': vectors['latency']['embedding'],
        'k': 5, 'num_candidates': 32, 'filter': prefilter}}
    hybrid_filter = {'bool': {'filter': [{'term': {'language': 'en'}}, {'term': {'published': True}}]}}
    hybrid_body = {'size': 5, '_source': ['title', 'category'], 'retriever': {'rrf': {
        'retrievers': [
            {'standard': {'query': {'bool': {
                'must': {'multi_match': {'query': 'semantic search', 'fields': ['title^2', 'content']}},
                'filter': hybrid_filter['bool']['filter']}}}},
            {'knn': {'field': 'embedding', 'query_vector': vectors['hybrid']['embedding'],
                     'k': 12, 'num_candidates': 32, 'filter': hybrid_filter}},
        ], 'rank_constant': 20, 'rank_window_size': 12}}}
    tasks = [
        task(1, '사전 계산한 embedding을 검색 가능한 벡터로 색인', 'Semantic Search · Dense vector · Reindex', [
            'f-semantic-source의 32건을 새 f-semantic-target으로 재색인하고 모든 문서 ID와 필드를 보존한다.',
            'embedding을 dims:384, index:true, similarity:cosine인 dense_vector로 매핑한다. 원본 배열을 보존하도록 index.mapping.exclude_source_vectors:false를 생성 시 설정한다.',
            'title/content는 text, category/language/vector_model은 keyword, published는 boolean으로 매핑한다.',
            'f-semantic-target의 primary shard는 1개, replica는 0개다. 기존 f-semantic-corpus는 변경하지 않는다.',
        ], ['f-semantic-source'], mapping_solution, 'state', 'f_semantic_mapping',
             [('Elastic dense_vector 공식 문서', DENSE_DOCS)],
             ['이 문제는 이미 계산된 벡터를 올바르게 저장하는 문제다. text를 dense_vector로 자동 변환하거나 벡터를 임의로 바꾸지 않는다.'],
             '일반 float 배열과 dense_vector는 다르다. 목적지 매핑과 벡터 _source 설정을 먼저 만든다.'),
        task(2, '메타데이터를 먼저 제한하는 의미 기반 kNN 검색', 'Semantic Search · kNN · Pre-filter', [
            f'f-semantic-corpus에서 질의 "{QUERY_TEXTS["latency"]}"의 준비된 embedding을 사용한다. GET f-semantic-queries/_doc/latency의 embedding 배열을 query_vector에 넣는다.',
            'category:search, language:en, published:true 세 조건을 kNN 내부 pre-filter에 넣는다. 검색 후 post_filter로 제한하는 풀이로 대체하지 않는다.',
            'embedding 필드에 k:5, num_candidates:32를 설정하고 size:5로 유사도가 높은 5건을 반환한다.',
            '각 hit의 문서 필드는 title과 category만 반환하며 embedding과 content는 반환하지 않는다.',
        ], ['f-semantic-corpus', 'f-semantic-queries'],
             request('GET', 'f-semantic-queries/_doc/latency') + '\n\n' + request('GET', 'f-semantic-corpus/_search', knn_body),
             'query', 'f_semantic_knn', [('Elastic kNN 공식 문서', KNN_DOCS)],
             ['F01을 풀지 않아도 이 문제를 풀 수 있도록 검색 가능한 f-semantic-corpus가 별도로 준비되어 있다.',
              '관련성이 높은 draft와 다른 언어 문서가 포함되어 있다. 조건을 kNN 내부에 적용해야 허용된 후보 중에서 5건을 찾는다.'],
             'knn.filter의 bool.filter에 세 term 조건을 넣고 _source를 제한한다.'),
        task(3, 'BM25와 벡터 검색을 RRF로 결합', 'Semantic Search · Hybrid search · RRF', [
            'f-semantic-corpus를 대상으로 retriever.rrf를 사용하는 하이브리드 검색을 작성한다.',
            '첫 번째 standard retriever는 semantic search를 title^2와 content의 multi_match로 검색한다.',
            '두 번째 knn retriever는 GET f-semantic-queries/_doc/hybrid의 준비된 embedding을 사용하여 embedding 필드를 k:12, num_candidates:32로 검색한다.',
            'language:en과 published:true를 두 retriever 모두에 적용한다. standard는 bool.filter, knn은 내부 filter를 사용한다. 검색 후 post_filter로만 제한하지 않는다. category는 제한하지 않는다.',
            'RRF는 rank_constant:20, rank_window_size:12를 사용하고 최종 size:5로 반환한다. BM25 점수와 cosine 점수를 직접 합산하는 bool.should로 대체하지 않는다.',
            '문서 필드는 title과 category만 반환하며 위 두 조건 이외의 filter나 별도 sort는 사용하지 않는다.',
        ], ['f-semantic-corpus', 'f-semantic-queries'],
             request('GET', 'f-semantic-queries/_doc/hybrid') + '\n\n' + request('GET', 'f-semantic-corpus/_search', hybrid_body),
             'query', 'f_semantic_rrf', [('Elastic RRF retriever 공식 문서', RRF_DOCS)],
             ['F01/F02의 실행 여부와 무관하게 준비된 corpus로 검색한다. 문서·질의 벡터는 같은 모델과 pooling으로 계산되어 있다.',
              'RRF는 서로 다른 검색 결과의 순위를 결합한다. 문서의 정확한 제품 이름과 의미 기반 이웃을 함께 활용하는 실습이다. 유효한 기존 trial 라이선스를 사용한다.'],
             'retriever.rrf.retrievers 아래 standard와 knn을 형제 항목으로 넣고 각 후보 단계에 같은 공개·언어 조건을 적용한다.'),
    ]
    return tasks, fixtures


VECTOR_PATH = Path(__file__).with_name('f_semantic_embeddings.json')
TASKS, FIXTURES = build(json.loads(VECTOR_PATH.read_text(encoding='utf-8'))) if VECTOR_PATH.exists() else ([], [])
