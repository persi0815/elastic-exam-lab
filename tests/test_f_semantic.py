"""Prepared-vector data and verifier guards; no inference/network needed."""
from __future__ import annotations
import copy
import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'data')]
from console import parse_console
from f_semantic import TASKS, FIXTURES
import verify_f_semantic as verifier

TASKMAP = {task['id']: task for task in TASKS}
FIXMAP = {fixture['index']: fixture for fixture in FIXTURES}


class SemanticDataTests(unittest.TestCase):
    def test_real_pretrained_provenance(self):
        provenance = verifier.prepared()['provenance']
        self.assertEqual(provenance['model_id'], 'sentence-transformers/all-MiniLM-L6-v2')
        self.assertEqual(provenance['license'], 'Apache-2.0')
        self.assertEqual(len(provenance['revision']), 40)
        self.assertEqual(len(provenance['artifact_sha256']), 64)
        self.assertEqual(len(provenance['tokenizer_sha256']), 64)
        self.assertEqual(provenance['execution_provider'], 'CPUExecutionProvider')

    def test_all_vectors_normalized_and_384_dimensional(self):
        data = verifier.prepared()
        vectors = [d['_source']['embedding'] for d in data['documents']]
        vectors += [query['embedding'] for query in data['queries'].values()]
        self.assertEqual(len(vectors), 34)
        for vector in vectors:
            self.assertEqual(len(vector), 384)
            self.assertAlmostEqual(math.sqrt(sum(value * value for value in vector)), 1, places=6)

    def test_query_and_corpus_use_same_model(self):
        data = verifier.prepared()
        model = data['provenance']['model_id']
        self.assertTrue(all(d['_source']['vector_model'] == model for d in data['documents']))
        self.assertNotEqual(data['queries']['latency']['embedding'], data['queries']['hybrid']['embedding'])

    def test_candidates_challenge_prefilter(self):
        data = verifier.prepared()
        query = data['queries']['latency']['embedding']
        ranked = sorted(data['documents'], key=lambda d: verifier.cosine(query, d['_source']['embedding']), reverse=True)
        self.assertFalse(ranked[0]['_source']['published'])
        eligible = [d for d in ranked if d['_source']['category'] == 'search'
                    and d['_source']['language'] == 'en' and d['_source']['published']]
        self.assertGreater(len(eligible), 5)
        self.assertGreater(verifier.cosine(query, eligible[4]['_source']['embedding'])
                           - verifier.cosine(query, eligible[5]['_source']['embedding']), .005)

    def test_queries_independent_of_mapping_task(self):
        for id in ('F02', 'F03'):
            self.assertNotIn('f-semantic-target', TASKMAP[id]['datasets'])
            self.assertIn('f-semantic-corpus', TASKMAP[id]['datasets'])

    def test_raw_float_arrays_and_prepared_dense_vectors(self):
        self.assertEqual(FIXMAP['f-semantic-source']['mappings']['properties']['embedding'], {'type': 'float'})
        dense = FIXMAP['f-semantic-corpus']['mappings']['properties']['embedding']
        self.assertEqual(dense['type'], 'dense_vector')
        self.assertEqual(dense['dims'], 384)
        self.assertEqual(dense['index_options'], {'type': 'hnsw'})

    def test_every_example_is_console_syntax(self):
        for task in TASKS:
            self.assertTrue(parse_console(task['solution']))
            self.assertTrue(task['source']['url'].startswith('https://www.elastic.co/'))


class View:
    def __init__(self, id):
        self.c = 'cluster1'
        self.t = TASKMAP[id]
        self.query = [q for q in parse_console(self.t['solution']) if q.path.endswith('/_search')]
        self.query = self.query[-1] if self.query else None
        self.checks = []
        self.responses = {}
        self.documents = {name: {d['_id']: copy.deepcopy(d['_source']) for d in item['documents']}
                          for name, item in FIXMAP.items()}
        self.search = {'hits': {'hits': []}}

    def add(self, label, ok, detail=''):
        self.checks.append({'label': label, 'ok': bool(ok)})

    def props(self, index):
        return copy.deepcopy(FIXMAP['f-semantic-corpus']['mappings']['properties'])

    def get(self, path, c=None, body=None):
        return copy.deepcopy(self.responses[path])

    def docs(self, index):
        return copy.deepcopy(self.documents[index])

    def submitted(self):
        return self.query

    def run_search(self, q, body=None):
        return copy.deepcopy(self.search)

    def set_body(self, body):
        self.query = parse_console('GET f-semantic-corpus/_search\n' + json.dumps(body))[0]


class SemanticVerifierGuardTests(unittest.TestCase):
    def knn(self):
        v = View('F02')
        data = verifier.prepared()
        query = data['queries']['latency']['embedding']
        allowed = [d for d in data['documents'] if d['_source']['category'] == 'search'
                   and d['_source']['language'] == 'en' and d['_source']['published']]
        ranked = sorted(allowed, key=lambda d: verifier.cosine(query, d['_source']['embedding']), reverse=True)[:5]
        v.search = {'hits': {'hits': [{'_index': 'f-semantic-corpus', '_id': d['_id'],
            '_score': (1 + verifier.cosine(query, d['_source']['embedding'])) / 2,
            '_source': {key: d['_source'][key] for key in ('title', 'category')}} for d in ranked]}}
        return v

    def rrf(self):
        v = View('F03')
        docs = verifier.prepared()['documents'][:5]
        v.search = {'hits': {'hits': [{'_index': 'f-semantic-corpus', '_id': d['_id'],
            '_score': .1 - i * .001,
            '_source': {key: d['_source'][key] for key in ('title', 'category')}} for i, d in enumerate(docs)]}}
        return v

    def test_knn_reference_guards_pass(self):
        v = self.knn()
        verifier.query_check(v)
        self.assertTrue(all(c['ok'] for c in v.checks), v.checks)

    def test_empty_query_cannot_pass_with_same_fake_response(self):
        v = self.knn()
        v.set_body({})
        verifier.query_check(v)
        self.assertFalse(all(c['ok'] for c in v.checks))

    def test_postfilter_rejected_even_if_fake_results_match(self):
        v = self.knn()
        body = copy.deepcopy(v.query.body)
        body['post_filter'] = body['knn'].pop('filter')
        v.set_body(body)
        verifier.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if 'pre-filter' in c['label']))

    def test_unpublished_result_rejected(self):
        v = self.knn()
        v.search['hits']['hits'][0]['_id'] = 'guide-15'
        verifier.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if 'cosine top-5' in c['label']))

    def test_vector_field_leak_rejected(self):
        v = self.knn()
        v.search['hits']['hits'][0]['_source']['embedding'] = [1]
        verifier.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '문서 필드' in c['label']))

    def test_rrf_reference_guards_pass(self):
        v = self.rrf()
        verifier.query_check(v)
        self.assertTrue(all(c['ok'] for c in v.checks), v.checks)

    def test_raw_bool_score_sum_cannot_replace_rrf(self):
        v = self.rrf()
        v.set_body({'size': 5, 'query': {'bool': {'should': [{'match': {'content': 'semantic search'}}]}}})
        verifier.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '두 retriever' in c['label']))

    def test_rrf_wrong_constant_rejected(self):
        v = self.rrf()
        body = copy.deepcopy(v.query.body)
        body['retriever']['rrf']['rank_constant'] = 60
        v.set_body(body)
        verifier.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if 'rank_constant' in c['label']))

    def test_rrf_each_branch_must_filter_candidates(self):
        for index in (0, 1):
            with self.subTest(branch=index):
                v = self.rrf()
                body = copy.deepcopy(v.query.body)
                if index == 0:
                    body['retriever']['rrf']['retrievers'][0]['standard']['query']['bool'].pop('filter')
                else:
                    body['retriever']['rrf']['retrievers'][1]['knn'].pop('filter')
                v.set_body(body)
                verifier.query_check(v)
                self.assertFalse(next(c['ok'] for c in v.checks if '두 retriever 모두' in c['label']))

    def test_rrf_optional_filter_terms_are_not_candidate_restrictions(self):
        v = self.rrf()
        body = copy.deepcopy(v.query.body)
        boolean = body['retriever']['rrf']['retrievers'][1]['knn']['filter']['bool']
        boolean['should'] = boolean.pop('filter')
        v.set_body(body)
        verifier.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '두 retriever 모두' in c['label']))

    def test_rrf_mismatched_query_vector_rejected(self):
        v = self.rrf()
        body = copy.deepcopy(v.query.body)
        body['retriever']['rrf']['retrievers'][1]['knn']['query_vector'] = verifier.prepared()['queries']['latency']['embedding']
        v.set_body(body)
        verifier.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '동일 모델' in c['label']))

    def test_rrf_empty_hits_cannot_pass(self):
        v = self.rrf()
        v.search = {'hits': {'hits': []}}
        verifier.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '실제 RRF top-5' in c['label']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
