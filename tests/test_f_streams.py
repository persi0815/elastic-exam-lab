"""Protect Streams grading against configuration-only and result-only shortcuts."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'data'))
from console import parse_console
from f_streams import (FAILURE_STREAM, FIXTURES, PROCESS_STREAM, PROOFS,
                       RETENTION_STREAM, STEPS, TASKS, document, ingest_body, message)
from verify_f_streams import field, state_check


def hit(source, index, identifier='unit-id'):
    return {'_index': index, '_id': identifier, '_source': source}


def search(documents):
    return {'_shards': {'failed': 0}, 'hits': {'total': {'value': len(documents)}, 'hits': documents}}


class FakeVerification:
    def __init__(self, task):
        self.t = task
        self.c = 'cluster1'
        self.checks = []
        self.es = self
        name = task['datasets'][0]
        self.stream = {'stream': {'name': name, **ingest_body()}, 'data_stream_exists': True,
                       'elasticsearch_assets': {}, 'effective_lifecycle': {'disabled': {}},
                       'effective_failure_store': {'disabled': {}}}
        self.responses = {}
        self.requests = []

    def add(self, label, ok, detail=''):
        self.checks.append({'label': label, 'ok': bool(ok), 'detail': detail})

    def kibana_require(self, cluster, method, path, body=None):
        self.requests.append(('kibana', method, path))
        if cluster != self.c or method != 'GET' or path != '/api/streams/' + self.t['datasets'][0]:
            raise AssertionError('Unexpected Kibana request')
        return self.stream

    def get(self, path, body=None):
        self.requests.append(('elasticsearch', 'GET', path))
        if path not in self.responses:
            raise AssertionError('Unexpected Elasticsearch request: ' + path)
        return self.responses[path]

    @property
    def complete(self):
        return bool(self.checks) and all(check['ok'] for check in self.checks)


def processing_case():
    v = FakeVerification(TASKS[0])
    v.stream['stream']['ingest']['processing']['steps'] = copy.deepcopy(STEPS)
    v.stream['elasticsearch_assets']['ingestPipeline'] = 'f08-app-pipeline'
    documents = []
    for identifier, proof in PROOFS.items():
        source = document(identifier, message(proof))
        source['log'] = {'level': proof['level']}
        source['service'] = {'name': proof['service']}
        source['http'] = {'response': {'status_code': proof['status']}}
        source['event']['duration_ms'] = proof['duration']
        if proof['level'] == 'error':
            source['event']['kind'] = 'alert'
        documents.append(hit(source, '.ds-' + PROCESS_STREAM + '-000001', identifier))
    v.responses['/' + PROCESS_STREAM + '/_search'] = search(documents)
    return v


def retention_case():
    v = FakeVerification(TASKS[1])
    old = '.ds-' + RETENTION_STREAM + '-000001'
    new = '.ds-' + RETENTION_STREAM + '-000002'
    v.stream['stream']['ingest']['lifecycle'] = {'dsl': {'data_retention': '7d'}}
    v.stream['effective_lifecycle'] = {'dsl': {'data_retention': '7d'}}
    v.responses['/_data_stream/' + RETENTION_STREAM + '/_lifecycle'] = {
        'data_streams': [{'name': RETENTION_STREAM, 'lifecycle': {'enabled': True, 'data_retention': '7d'}}]}
    v.responses['/_data_stream/' + RETENTION_STREAM] = {'data_streams': [{
        'name': RETENTION_STREAM, 'generation': 2,
        'indices': [{'index_name': old}, {'index_name': new}]}]}
    seed = next(item for item in FIXTURES if item['index'] == RETENTION_STREAM)
    documents = [hit(copy.deepcopy(doc['_source']), old, doc['_id']) for doc in seed['documents']]
    documents.append(hit(document('f09-after-rollover', 'After rollover', '2026-10-01T00:00:01Z'), new))
    v.responses['/' + RETENTION_STREAM + '/_search'] = search(documents)
    return v


def failure_case():
    v = FakeVerification(TASKS[2])
    config = {'lifecycle': {'enabled': {'data_retention': '3d'}}}
    v.stream['stream']['ingest']['failure_store'] = copy.deepcopy(config)
    v.stream['effective_failure_store'] = copy.deepcopy(config)
    v.responses['/_data_stream/' + FAILURE_STREAM + '/_options'] = {'data_streams': [{
        'name': FAILURE_STREAM, 'options': {'failure_store': {
            'enabled': True, 'lifecycle': {'enabled': True, 'data_retention': '3d'}}}}]}
    failed = {'document': {'index': FAILURE_STREAM,
                          'source': document('f10-bad', 'Invalid audit timestamp', 'not-a-date')},
              'error': {'type': 'document_parsing_exception', 'message': 'Cannot parse @timestamp'}}
    v.responses['/' + FAILURE_STREAM + '::failures/_search'] = search([hit(failed, '.fs-' + FAILURE_STREAM)])
    good = document('f10-good-proof', 'Valid audit timestamp', '2026-10-01T00:00:02Z')
    v.responses['/' + FAILURE_STREAM + '/_search'] = search([hit(good, '.ds-' + FAILURE_STREAM)])
    return v


class StreamsDataTests(unittest.TestCase):
    def test_three_independent_classic_streams_have_seed_data(self):
        self.assertEqual([task['id'] for task in TASKS], ['F08', 'F09', 'F10'])
        self.assertEqual(len({item['index'] for item in FIXTURES}), 3)
        self.assertEqual(sum(len(item['documents']) for item in FIXTURES), 9)
        for item in FIXTURES:
            self.assertTrue(item['data_stream'])
            self.assertTrue(item['documents'])
            self.assertEqual(item['mappings']['properties']['@timestamp']['type'], 'date')
            self.assertEqual(len({doc['_id'] for doc in item['documents']}), len(item['documents']))

    def test_reference_solutions_distinguish_kibana_from_elasticsearch(self):
        for task in TASKS:
            parsed = parse_console(task['solution'])
            self.assertTrue(any(request.path.startswith('/kbn:/api/streams/') for request in parsed))
            self.assertTrue(any(not request.path.startswith('/kbn:') for request in parsed))
            self.assertTrue(task['reconstructed'])
            self.assertEqual(task['kind'], 'state')

    def test_9_3_requests_omit_read_only_processing_timestamp(self):
        for task in TASKS:
            request = next(request for request in parse_console(task['solution'])
                           if request.method == 'PUT' and request.path.startswith('/kbn:'))
            self.assertNotIn('updated_at', request.body['ingest']['processing'])
            self.assertIn('classic', request.body['ingest'])

    def test_failure_example_has_invalid_date_but_normal_doc_is_valid(self):
        requests = [request for request in parse_console(TASKS[2]['solution']) if request.method == 'POST']
        self.assertEqual(requests[0].body['@timestamp'], 'not-a-date')
        self.assertEqual(requests[1].body['@timestamp'], '2026-10-01T00:00:02Z')


class StreamsVerifierTests(unittest.TestCase):
    def grade(self, case):
        state_check(case)
        self.assertTrue(all(method == 'GET' for _, method, _ in case.requests))
        return case.complete

    def test_all_three_complete_real_state_shapes(self):
        for factory in (processing_case, retention_case, failure_case):
            with self.subTest(task=factory.__name__):
                self.assertTrue(self.grade(factory()))

    def test_es_pipeline_results_do_not_replace_streams_configuration(self):
        v = processing_case()
        v.stream['stream']['ingest']['processing']['steps'] = []
        self.assertFalse(self.grade(v))

    def test_string_numbers_are_rejected_even_if_search_mapping_coerces_them(self):
        v = processing_case()
        v.responses['/' + PROCESS_STREAM + '/_search']['hits']['hits'][0]['_source']['event']['duration_ms'] = '175'
        self.assertFalse(self.grade(v))

    def test_unconditional_alert_on_info_document_is_rejected(self):
        v = processing_case()
        v.responses['/' + PROCESS_STREAM + '/_search']['hits']['hits'][1]['_source']['event']['kind'] = 'alert'
        self.assertFalse(self.grade(v))

    def test_saved_processing_without_new_ingested_proofs_is_rejected(self):
        v = processing_case()
        v.responses['/' + PROCESS_STREAM + '/_search'] = search([])
        self.assertFalse(self.grade(v))

    def test_ilm_or_template_inheritance_does_not_satisfy_dsl_task(self):
        for config in ({'ilm': {'policy': 'old-policy'}}, {'inherit': {}}):
            with self.subTest(config=config):
                v = retention_case()
                v.stream['stream']['ingest']['lifecycle'] = config
                self.assertFalse(self.grade(v))

    def test_declared_retention_without_elasticsearch_lifecycle_is_rejected(self):
        v = retention_case()
        v.responses['/_data_stream/' + RETENTION_STREAM + '/_lifecycle']['data_streams'][0]['lifecycle']['enabled'] = False
        self.assertFalse(self.grade(v))

    def test_rollover_without_new_document_in_write_index_is_rejected(self):
        v = retention_case()
        documents = v.responses['/' + RETENTION_STREAM + '/_search']['hits']['hits']
        documents[-1]['_index'] = documents[0]['_index']
        self.assertFalse(self.grade(v))

    def test_seed_loss_is_rejected_after_rollover(self):
        v = retention_case()
        v.responses['/' + RETENTION_STREAM + '/_search']['hits']['hits'].pop(0)
        self.assertFalse(self.grade(v))

    def test_failure_configuration_without_actual_failure_document_is_rejected(self):
        v = failure_case()
        v.responses['/' + FAILURE_STREAM + '::failures/_search'] = search([])
        self.assertFalse(self.grade(v))

    def test_fake_bad_document_in_ordinary_index_is_rejected(self):
        v = failure_case()
        response = v.responses['/' + FAILURE_STREAM + '/_search']
        response['hits']['hits'].append(hit(document('f10-bad', 'Invalid audit timestamp', 'not-a-date'), 'ordinary'))
        self.assertFalse(self.grade(v))

    def test_disabled_failure_store_is_rejected(self):
        v = failure_case()
        v.responses['/_data_stream/' + FAILURE_STREAM + '/_options']['data_streams'][0]['options']['failure_store']['enabled'] = False
        self.assertFalse(self.grade(v))

    def test_wrong_failure_cause_and_lost_original_input_are_rejected(self):
        for field_path in ('error.type', 'document.source.@timestamp'):
            with self.subTest(field=field_path):
                v = failure_case()
                source = v.responses['/' + FAILURE_STREAM + '::failures/_search']['hits']['hits'][0]['_source']
                if field_path == 'error.type':
                    source['error']['type'] = 'unrelated_exception'
                else:
                    source['document']['source']['@timestamp'] = '2026-10-01T00:00:00Z'
                self.assertFalse(self.grade(v))

    def test_flat_and_nested_source_fields_both_work(self):
        self.assertEqual(field({'event.id': 'proof'}, 'event.id'), 'proof')
        self.assertEqual(field({'event': {'id': 'proof'}}, 'event.id'), 'proof')


if __name__ == '__main__':
    unittest.main(verbosity=2)
