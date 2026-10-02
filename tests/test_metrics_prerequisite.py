"""Prerequisite recovery preserves existing practice work; no Docker is used."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from lab import FIX, Lab, MARKER, MARKER_VALUE

COMPONENT = '/_component_template/metrics-mappings'
CUSTOM = {
    'template': {'mappings': {'properties': {
        '@timestamp': {'type': 'date'}, 'custom_metric': {'type': 'double'}
    }}},
    '_meta': {'description': 'Learner-owned customization'},
}


class FakeElastic:
    """A stateful HTTP double supports the real Lab orchestration methods."""
    expected = {'cluster1': 'ece-lab-cluster1', 'cluster2': 'ece-lab-cluster2'}

    def kibana(self,cluster,method,path,body=None,**kwargs):
        self.calls.append((cluster,method,path,copy.deepcopy(body)))
        return {'status':404,'body':{'error':'Stream does not exist in this test'}}

    def __init__(self, component=None, *, get_error=None, put_error=None,
                 race_status=None, race_visible=True):
        self.component = copy.deepcopy(component)
        self.get_error = get_error
        self.put_error = put_error
        self.race_status = race_status
        self.race_visible = race_visible
        self.raced = False
        self.calls = []
        self.events = []
        self.indices = {('cluster1', 'user-progress'): {
            'count': 1, 'settings': {'index': {'uuid': 'preserved-uuid'}},
            'source': {'answer': 'Keep my practice work'},
        }}
        self.snapshots = {'user-snapshot': {'state': 'SUCCESS'}}

    def call(self, cluster, method, path, body=None, **kwargs):
        self.calls.append((cluster, method, path, copy.deepcopy(body)))
        self.events.append(('http', method, path))
        endpoint = urlsplit(path).path
        result = {'status': 200, 'body': {'acknowledged': True}}
        if endpoint == COMPONENT:
            if method == 'GET':
                if self.get_error:
                    return {'status': self.get_error, 'body': {'error': 'component lookup unavailable'}}
                if self.component is None:
                    return {'status': 404, 'body': {'error': 'component_template_missing_exception'}}
                return {'status': 200, 'body': {'component_templates': [{
                    'name': 'metrics-mappings', 'component_template': copy.deepcopy(self.component)
                }]}}
            if method == 'PUT':
                if self.race_status and not self.raced:
                    self.raced = True
                    if self.race_visible:
                        self.component = copy.deepcopy(CUSTOM)
                    return {'status': self.race_status, 'body': {'error': 'already exists'}}
                if self.put_error:
                    return {'status': self.put_error, 'body': {'error': 'component creation failed'}}
                if 'create=true' in path and self.component is not None:
                    return {'status': 409, 'body': {'error': 'already exists'}}
                self.component = copy.deepcopy(body)
            if method == 'DELETE':
                self.component = None
            return result
        if method == 'GET' and endpoint == '/':
            return {'status': 200, 'body': {'cluster_name': self.expected[cluster]}}
        if method == 'GET' and endpoint == '/_cluster/health':
            return {'status': 200, 'body': {'number_of_nodes': 3 if cluster == 'cluster1' else 1}}
        if endpoint == f'/{MARKER}/_doc/identity':
            return {'status': 200, 'body': {'found': True, '_source': {'owner': MARKER_VALUE}}}
        if endpoint == f'/{MARKER}/_doc/seed':
            return {'status': 200, 'body': {'found': True, '_source': {'version': 2, 'set': 'C'}}}
        if endpoint == '/_cat/indices':
            names = [name for (c, name) in self.indices if c == cluster]
            return {'status': 200, 'body': [{'index': name} for name in names + [MARKER]]}
        if endpoint == '/_remote/info':
            return {'status': 200, 'body': {'cluster2': {'connected': True}}}
        if endpoint == '/_component_template':
            templates = [] if self.component is None else [{
                'name': 'metrics-mappings', 'component_template': copy.deepcopy(self.component)
            }]
            return {'status': 200, 'body': {'component_templates': templates}}
        if endpoint.startswith('/_snapshot/snap-repo/moreblogs_snapshot'):
            if method == 'GET':
                shot = self.snapshots.get('moreblogs_snapshot')
                return {'status': 200 if shot else 404,
                        'body': {'snapshots': [shot]} if shot else {}}
            if method == 'PUT':
                shot = {'state': 'SUCCESS', 'indices': ['moreblogs']}
                self.snapshots['moreblogs_snapshot'] = shot
                return {'status': 200, 'body': {'snapshot': shot}}
            if method == 'DELETE':
                self.snapshots.pop('moreblogs_snapshot', None)
            return result
        if endpoint.startswith('/_') or endpoint.startswith(f'/{MARKER}/'):
            return {'status': 200, 'body': {}}
        parts = endpoint.strip('/').split('/')
        name = parts[0]
        key = (cluster, name)
        if method == 'HEAD':
            return {'status': 200 if key in self.indices else 404, 'body': {}}
        if method == 'PUT' and len(parts) == 1:
            self.indices[key] = {'count': 0, 'settings': {'index': {'uuid': name + '-uuid'}}}
        elif method == 'DELETE' and len(parts) == 1:
            self.indices.pop(key, None)
        elif len(parts) == 2 and parts[1] == '_bulk':
            self.indices[key]['count'] = len(kwargs['raw'].splitlines()) // 2
            return {'status': 200, 'body': {'errors': False}}
        elif len(parts) == 2 and parts[1] == '_count':
            return {'status': 200, 'body': {'count': self.indices[key]['count']}}
        elif len(parts) == 2 and parts[1] == '_settings' and method == 'GET':
            return {'status': 200, 'body': {name: {'settings': self.indices[key]['settings']}}}
        return result

    def get(self, cluster, path, body=None, **kwargs):
        return self.call(cluster, 'GET', path, body, **kwargs)

    def require(self, cluster, method, path, body=None, **kwargs):
        result = self.call(cluster, method, path, body, **kwargs)
        if result['status'] >= 400:
            raise RuntimeError(f'{method} {path}: HTTP {result["status"]} {result["body"]}')
        return result['body']


class MetricsPrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state_dir = Path(self.directory.name)

    def make_lab(self, client, *, saved=False):
        if saved:
            (self.state_dir / 'lab.json').write_text(json.dumps({'active_set': 'C', 'generation': 3}))
        lab = Lab(client, self.state_dir)
        original_update = lab.update
        def observe_update(**kwargs):
            client.events.append(('phase', kwargs.get('phase')))
            original_update(**kwargs)
        lab.update = observe_update
        return lab

    def component_puts(self, client):
        return [call for call in client.calls if call[1] == 'PUT' and urlsplit(call[2]).path == COMPONENT]

    def test_missing_component_creates_minimal_date_mapping(self):
        client = FakeElastic()
        lab = self.make_lab(client)
        self.assertTrue(lab.ensure_metrics_component())
        self.assertEqual(client.component['template'], {
            'mappings': {'properties': {'@timestamp': {'type': 'date'}}}
        })
        puts = self.component_puts(client)
        self.assertEqual(len(puts), 1)
        self.assertEqual(puts[0][0], 'cluster1')
        self.assertIn('create=true', puts[0][2])

    def test_existing_custom_template_is_not_overwritten(self):
        client = FakeElastic(CUSTOM)
        self.assertFalse(self.make_lab(client).ensure_metrics_component())
        self.assertEqual(client.component, CUSTOM)
        self.assertEqual(self.component_puts(client), [])

    def test_lookup_failure_raises_without_mutation(self):
        client = FakeElastic(get_error=503)
        original_indices = copy.deepcopy(client.indices)
        original_snapshots = copy.deepcopy(client.snapshots)
        with self.assertRaises(RuntimeError):
            self.make_lab(client).ensure_metrics_component()
        self.assertFalse(any(call[1] != 'GET' for call in client.calls))
        self.assertEqual(client.indices, original_indices)
        self.assertEqual(client.snapshots, original_snapshots)

    def test_concurrent_creation_preserves_new_custom_template(self):
        for status in (400, 409):
            with self.subTest(status=status):
                client = FakeElastic(race_status=status)
                self.assertFalse(self.make_lab(client).ensure_metrics_component())
                self.assertEqual(client.component, CUSTOM)
                self.assertEqual(len(self.component_puts(client)), 1)
                self.assertIn('create=true', self.component_puts(client)[0][2])

    def test_failed_creation_does_not_treat_absence_as_success(self):
        for options in ({'race_status': 400, 'race_visible': False},
                        {'race_status': 409, 'race_visible': False}, {'put_error': 500}):
            with self.subTest(options=options):
                client = FakeElastic(**options)
                with self.assertRaises(RuntimeError):
                    self.make_lab(client).ensure_metrics_component()
                self.assertIsNone(client.component)

    def test_resume_current_c_preserves_progress_and_never_prepares_snapshot(self):
        client = FakeElastic()
        original_indices = copy.deepcopy(client.indices)
        original_snapshots = copy.deepcopy(client.snapshots)
        lab = self.make_lab(client, saved=True)
        with patch.object(lab, 'reset', side_effect=AssertionError('resume must not reset')) as reset, \
             patch.object(lab, 'prepare_e', side_effect=AssertionError('C must not prepare E')) as prepare:
            lab.bootstrap()
        reset.assert_not_called()
        prepare.assert_not_called()
        self.assertEqual(lab.info['phase'], 'ready', lab.info.get('error'))
        self.assertEqual((lab.info['active_set'], lab.info['generation']), ('C', 3))
        saved = json.loads(lab.state_file.read_text())
        self.assertEqual((saved['active_set'], saved['generation']), ('C', 3))
        self.assertEqual(client.indices, original_indices)
        self.assertEqual(client.snapshots, original_snapshots)
        self.assertFalse(any('/_snapshot' in call[2] for call in client.calls))
        mutations = [call for call in client.calls if call[1] not in ('GET', 'HEAD')]
        self.assertTrue(all(urlsplit(call[2]).path in {
            COMPONENT, '/_security/user/kibana_system/_password'
        } for call in mutations), mutations)
        create_event = next(i for i, event in enumerate(client.events)
                            if event[:2] == ('http', 'PUT') and urlsplit(event[2]).path == COMPONENT)
        self.assertLess(create_event, client.events.index(('phase', 'ready')))

    def test_resume_lookup_failure_surfaces_error_without_reset(self):
        client = FakeElastic(get_error=503)
        lab = self.make_lab(client, saved=True)
        with patch.object(lab, 'reset') as reset, patch.object(lab, 'prepare_e') as prepare:
            lab.bootstrap()
        reset.assert_not_called()
        prepare.assert_not_called()
        self.assertEqual(lab.info['phase'], 'error')
        self.assertTrue(lab.info['error'])
        self.assertEqual((lab.info['active_set'], lab.info['generation']), ('C', 3))
        self.assertEqual(self.component_puts(client), [])

    def test_c_reset_restores_prerequisite_after_verified_seeding(self):
        client = FakeElastic(CUSTOM)
        lab = self.make_lab(client, saved=True)
        with patch.object(lab, 'prepare_e', side_effect=AssertionError('C must not prepare E')) as prepare:
            lab.reset('C')
        prepare.assert_not_called()
        self.assertEqual(lab.info['phase'], 'ready', lab.info.get('error'))
        self.assertEqual((lab.info['active_set'], lab.info['generation']), ('C', 4))
        self.assertEqual(client.component['template']['mappings']['properties']['@timestamp'], {'type': 'date'})
        for fixture in FIX:
            self.assertEqual(client.indices[(fixture['cluster'], fixture['index'])]['count'],
                             len(fixture['documents']))
        count_events = [i for i, event in enumerate(client.events)
                        if event[:2] == ('http', 'GET') and urlsplit(event[2]).path.endswith('/_count')]
        create_event = next(i for i, event in enumerate(client.events)
                            if event[:2] == ('http', 'PUT') and urlsplit(event[2]).path == COMPONENT)
        self.assertLess(max(count_events), create_event)
        self.assertLess(create_event, client.events.index(('phase', 'ready')))
        self.assertFalse(any(call[1] == 'PUT' and call[2].startswith('/_snapshot') for call in client.calls))

    def test_direct_e_preparation_ensures_component_and_preserves_customization(self):
        for existing in (None, CUSTOM):
            with self.subTest(existing=existing is not None):
                client = FakeElastic(existing)
                client.indices[('cluster1', 'moreblogs')] = {'count': 24}
                lab = self.make_lab(client)
                lab.prepare_e()
                self.assertEqual(len(self.component_puts(client)), 0 if existing else 1)
                self.assertIsNotNone(client.component)
                if existing:
                    self.assertEqual(client.component, CUSTOM)
                self.assertEqual(client.snapshots['moreblogs_snapshot']['state'], 'SUCCESS')
                self.assertNotIn(('cluster1', 'moreblogs'), client.indices)
                first_snapshot = next(i for i, event in enumerate(client.events)
                                      if event[0] == 'http' and event[2].startswith('/_snapshot'))
                component_lookup = next(i for i, event in enumerate(client.events)
                                        if event[:2] == ('http', 'GET') and event[2] == COMPONENT)
                self.assertLess(component_lookup, first_snapshot)


if __name__ == '__main__':
    unittest.main(verbosity=2)
