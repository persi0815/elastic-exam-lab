"""E verifier guard contracts; fake responses do not test ES semantics."""
from __future__ import annotations
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from console import parse_console
import verify_e


class View:
    def __init__(self, check, body=None, index='blogs'):
        self.c = 'cluster1'
        self.t = {'check': check, 'solution': f'GET /{index}/_search\n' + json.dumps(body or {})}
        self.code = self.t['solution']
        self.history = []
        self.query = parse_console(self.code)[0]
        self.checks = []
        self.responses = {}
        self.documents = {}
        self.search = {'hits': {'hits': []}}
        self.es = self

    def add(self, label, ok, detail=''):
        self.checks.append({'label': label, 'ok': bool(ok)})

    def get(self, path, *args, **kwargs):
        if args and path == 'cluster1':
            return {'status': 200, 'body': {'username': 'task1'}}
        return copy.deepcopy(self.responses[path])

    def require(self, cluster, method, path, body=None):
        return self.get(path)

    def docs(self, index, cluster=None):
        return copy.deepcopy(self.documents[index])

    def props(self, index):
        return self.get(f'/{index}/_mapping')[index]['mappings']['properties']

    def submitted(self):
        return self.query

    def run_search(self, request, body=None):
        return copy.deepcopy(self.search)

    def set_body(self, body):
        self.query = parse_console(f'GET {self.query.path}\n' + json.dumps(body))[0]


YEARLY = {'size': 0, 'query': {'match_phrase': {'content': 'open source'}},
          'aggs': {'any_name': {'date_histogram': {'field': 'publish_date', 'calendar_interval': 'year'},
                               'aggs': {'different_name': {'cardinality': {'field': 'authors.uid'}}}}}}

CERTIFIED = {'from': 10, 'size': 5,
             'query': {'bool': {'must': [{'match': {'content': 'certified engineer'}}],
                                'should': [{'match_phrase': {'content': 'certified engineer'}}],
                                'filter': [{'range': {'publish_date': {'gte': 'now-2y/d', 'lte': 'now'}}}]}},
             'sort': ['_score', '_doc'], 'highlight': {'fields': {'content': {}}}}


class EQueryGuardTests(unittest.TestCase):
    def yearly(self):
        v = View('e_yearly_authors', YEARLY)
        v.search = {'aggregations': {'any_name': {'buckets': [
            {'key': 1735689600000, 'doc_count': 4, 'different_name': {'value': 3}}]}}}
        return v

    def certified(self):
        v = View('e_certified', CERTIFIED)
        v.search = {'hits': {'hits': [{'_index': 'blogs', '_id': str(i), 'sort': [1.4, i],
                                      'highlight': {'content': ['<em>certified</em> engineer']}}
                                     for i in range(5)]}}
        return v

    def test_yearly_reference_structure_passes(self):
        v = self.yearly()
        verify_e.query_check(v)
        self.assertTrue(all(c['ok'] for c in v.checks), v.checks)

    def test_empty_yearly_body_cannot_pass_even_with_same_fake_response(self):
        v = self.yearly()
        v.set_body({})
        verify_e.query_check(v)
        self.assertFalse(all(c['ok'] for c in v.checks))

    def test_nonexistent_keyword_multifield_rejected(self):
        v = self.yearly()
        body = copy.deepcopy(YEARLY)
        body['aggs']['any_name']['aggs']['different_name']['cardinality']['field'] = 'authors.uid.keyword'
        v.set_body(body)
        verify_e.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '고유 개수' in c['label']))

    def test_certified_reference_structure_passes(self):
        v = self.certified()
        verify_e.query_check(v)
        self.assertTrue(all(c['ok'] for c in v.checks), v.checks)

    def test_certified_and_search_does_not_meet_or_requirement(self):
        v = self.certified()
        body = copy.deepcopy(CERTIFIED)
        body['query']['bool']['must'][0]['match']['content'] = {'query': 'certified engineer', 'operator': 'and'}
        v.set_body(body)
        verify_e.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if 'OR 검색' in c['label']))

    def test_certified_empty_page_cannot_pass(self):
        v = self.certified()
        v.search = {'hits': {'hits': []}}
        verify_e.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if c['label'] == '실제 3번째 페이지'))

    def test_certified_future_dates_must_be_excluded(self):
        v = self.certified()
        body = copy.deepcopy(CERTIFIED)
        body['query']['bool']['filter'][0]['range']['publish_date'].pop('lte')
        v.set_body(body)
        verify_e.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '최근 2년' in c['label']))

    def test_certified_wrong_pagination_rejected(self):
        v = self.certified()
        body = copy.deepcopy(CERTIFIED)
        body['from'] = 0
        v.set_body(body)
        verify_e.query_check(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '페이지당 5건' in c['label']))


class EStateGuardTests(unittest.TestCase):
    def security(self):
        v = View('e_security')
        v.responses = {'/_security/user/task1': {'task1': {'roles': ['chosen_name'],
            'full_name': 'Elastic Search', 'email': 'elastic@search.com'}},
            '/_security/role/chosen_name': {'chosen_name': {'cluster': ['all'], 'indices': [
                {'names': ['*'], 'privileges': ['read']}, {'names': ['task1'], 'privileges': ['all']}],
                'applications': [{'application': 'kibana-.kibana', 'privileges': ['space_all'],
                                  'resources': ['space:default']}]}}}
        return v

    def test_security_accepts_arbitrary_role_name(self):
        v = self.security()
        verify_e.security(v)
        self.assertTrue(all(c['ok'] for c in v.checks), v.checks)

    def test_security_rejects_write_access_to_other_indices(self):
        v = self.security()
        v.responses['/_security/role/chosen_name']['chosen_name']['indices'][0]['privileges'].append('write')
        verify_e.security(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '읽기 전용' in c['label']))

    def test_security_requires_default_space(self):
        v = self.security()
        v.responses['/_security/role/chosen_name']['chosen_name']['applications'][0]['resources'] = ['space:other']
        verify_e.security(v)
        self.assertFalse(next(c['ok'] for c in v.checks if 'Default space' in c['label']))

    def test_keyword_template_cannot_hide_exception(self):
        self.assertTrue(verify_e.keyword_template({'dynamic_templates': [
            {'strings': {'match_mapping_type': 'string', 'mapping': {'type': 'keyword'}}}]}))
        self.assertFalse(verify_e.keyword_template({'dynamic_templates': [
            {'strings': {'match_mapping_type': 'string', 'unmatch': 'secret', 'mapping': {'type': 'keyword'}}}]}))

    def test_nested_conditions_cannot_use_two_different_authors(self):
        orig = {'1': {'authors': [{'first_name': 'david', 'job_title': 'engineer'}]}}
        body = {'query': {'bool': {'must': [
            {'nested': {'path': 'authors', 'query': {'match': {'authors.first_name': 'david'}}}},
            {'nested': {'path': 'authors', 'query': {'match': {'authors.job_title': 'engineer'}}}}]}}}
        v = View('e_nested', body, 'task5')
        v.responses['/task5/_mapping'] = {'task5': {'mappings': {'properties': {'authors': {'type': 'nested'}}}}}
        v.documents['task5'] = orig
        v.search = {'hits': {'hits': [{'_index': 'task5', '_id': '1'}]}}
        with patch.object(verify_e, 'fixture', return_value=orig):
            verify_e.nested(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '한 nested' in c['label']))

    def test_categories_preserves_missing_category_documents(self):
        orig = {'1': {'category': 'c1', 'title': 'A'}, '2': {'title': 'B'}}
        refs = {'c1': {'uid': 'c1', 'title': 'News'}}
        v = View('e_categories')
        v.documents['task6'] = {'1': {'title': 'A', 'categories': {'uid': 'c1', 'title': 'News'}},
                                '2': {'title': 'B'}}
        v.responses['/_ingest/pipeline'] = {'chosen_pipeline': {'processors': [
            {'enrich': {'field': 'category', 'target_field': 'categories', 'ignore_missing': True}}]}}
        with patch.object(verify_e, 'fixture', side_effect=lambda v, name: orig if name == 'blogs' else refs):
            verify_e.categories(v)
        self.assertTrue(all(c['ok'] for c in v.checks), v.checks)

    def test_categories_rejects_dropped_missing_category_document(self):
        orig = {'1': {'category': 'c1'}, '2': {'title': 'missing category'}}
        refs = {'c1': {'uid': 'c1', 'title': 'News'}}
        v = View('e_categories')
        v.documents['task6'] = {'1': {'categories': {'uid': 'c1', 'title': 'News'}}}
        v.responses['/_ingest/pipeline'] = {}
        with patch.object(verify_e, 'fixture', side_effect=lambda v, name: orig if name == 'blogs' else refs):
            verify_e.categories(v)
        self.assertFalse(next(c['ok'] for c in v.checks if '원본 전체 문서 ID' in c['label']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
