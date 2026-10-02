#!/usr/bin/env python3
"""Opt-in isolated E01-E10 integration test against the existing Docker lab.

Run inside the app container after deploying E. All Elasticsearch resources use a
fresh UUID namespace. Existing fixture indices, answers, cluster settings and the
active exam set are preserved. Reference requests go through real Kibana Console;
grading uses the real Verify implementation with a resource-name adapter, rather
than the app's /api/check endpoint. Native capture uses the current active set's
first task because the app records only requests belonging to the active set.
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from console import parse_console
from elastic import Elastic
from lab import Lab
from verify import Verify


class Names:
    """Single-pass substitutions preserve passwords and field/analyzer names."""
    def __init__(self, prefix, tasks):
        originals = {'blogs', 'categories', 'web_traffic', 'moreblogs',
                     'task1', 'task3', 'web_traffic_pipeline', 'categories_policy',
                     'categories_pipeline', 'ccr_blogs', 'my-metrics-policy',
                     'my-metrics-template', 'metrics-mappings',
                     'my.metrics-system-dev', 'snap-repo', 'moreblogs_snapshot'}
        systems = {'_security': 2, '_ingest': 2, '_enrich': 2,
                   '_ilm': 2, '_index_template': 1, '_component_template': 1,
                   '_snapshot': 1, '_data_stream': 1}
        for task in tasks:
            originals.update(task.get('datasets', []))
            for request in parse_console(task['solution']):
                parts = request.path.split('?')[0].strip('/').split('/')
                if not parts or not parts[0]:
                    continue
                if not parts[0].startswith('_'):
                    originals.add(parts[0])
                elif parts[0] in systems and len(parts) > systems[parts[0]]:
                    originals.add(parts[systems[parts[0]]])
                    if parts[0] == '_snapshot' and len(parts) > 2:
                        originals.add(parts[2])
        originals = {name for name in originals
                     if not name.startswith('_') and '*' not in name and ',' not in name}
        self.mapping = {name: prefix + name for name in originals}
        # Template patterns and the repository directory need the same isolation.
        self.mapping['my.metrics-'] = prefix + 'my.metrics-'
        self.mapping['/mnt/elastic-snapshots/ece-practice-search'] = (
            '/mnt/elastic-snapshots/' + prefix + 'search')
        self.forward = self._pattern(self.mapping)
        self.inverse = {value: key for key, value in self.mapping.items()}
        # Generated backing/enrich index names append date suffixes. The random
        # prefix makes unbounded reverse replacement unambiguous there too.
        self.backward = re.compile('|'.join(re.escape(item) for item in
                                            sorted(self.inverse, key=len, reverse=True)))

    @staticmethod
    def _pattern(mapping):
        alternatives = sorted(mapping, key=len, reverse=True)
        # The metrics prefix intentionally matches a following wildcard/suffix.
        return re.compile('|'.join(re.escape(item) if item.endswith('my.metrics-')
                                   or item.startswith('/mnt/') else
                                   r'(?<![A-Za-z0-9_.-])' + re.escape(item) +
                                   r'(?![A-Za-z0-9_.-])' for item in alternatives))

    def rewrite(self, value, reverse=False):
        mapping, pattern = ((self.inverse, self.backward) if reverse else
                            (self.mapping, self.forward))
        if isinstance(value, str):
            return pattern.sub(lambda match: mapping[match.group()], value)
        if isinstance(value, list):
            return [self.rewrite(item, reverse) for item in value]
        if isinstance(value, tuple):
            return tuple(self.rewrite(item, reverse) for item in value)
        if isinstance(value, dict):
            return {self.rewrite(key, reverse): self.rewrite(item, reverse)
                    for key, item in value.items()}
        return value

    def body(self, value, trail=()):
        """Map API resource references while preserving document/field strings."""
        resource_keys = {'index', 'indices', 'leader_index', 'policy_name',
                         'index.lifecycle.name', 'composed_of', 'roles', 'names',
                         'repository', 'location', 'index_patterns'}
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == '_source':
                    result[key] = copy.deepcopy(item)
                elif (key in resource_keys or key == 'pipeline' and isinstance(item, str)
                      or key == 'name' and trail and trail[-1] == 'lifecycle'):
                    result[key] = self.rewrite(item) if not isinstance(item, dict) else self.body(item, trail + (key,))
                else:
                    result[key] = self.body(item, trail + (key,))
            return result
        if isinstance(value, list):
            return [self.body(item, trail) for item in value]
        return copy.deepcopy(value)

    def raw(self, value, content_type):
        if value is None:
            return None
        if content_type == 'application/x-ndjson':
            return '\n'.join(json.dumps(self.body(json.loads(line))) for line in
                             value.splitlines() if line.strip()) + '\n'
        return json.dumps(self.body(json.loads(value))) if value.strip() else value


class IsolatedElastic(Elastic):
    """Real ES adapter used only by Verify and this smoke test."""
    def __init__(self, names, prefix):
        super().__init__()
        self.names, self.prefix = names, prefix
        self.resources = {kind: set() for kind in
                          ('index', 'data_stream', 'pipeline', 'enrich', 'ilm',
                           'template', 'component', 'user', 'role', 'repo')}
        self.snapshots = set()

    def owned(self, name):
        return name.startswith(self.prefix)

    def record(self, cluster, method, path, body=None):
        """Reject global writes; record exact resources before any HTTP request."""
        if method in ('GET', 'HEAD'):
            return
        parts = path.split('?')[0].strip('/').split('/')
        if method == 'POST' and parts[:3] == ['_ingest', 'pipeline', '_simulate']:
            return  # Inline pipeline simulation creates no persistent resource.
        if method == 'POST' and parts[:2] == ['_index_template', '_simulate']:
            if len(parts) == 3 and self.owned(parts[2]):
                return  # A named template simulation is also read-only.
            raise RuntimeError('Template simulation is outside the namespace.')
        if not parts or not parts[0]:
            raise RuntimeError('An empty ES mutation target is forbidden.')
        kind, name = None, None
        if not parts[0].startswith('_'):
            kind, name = 'index', parts[0]
        elif parts[0] in ('_index_template', '_component_template', '_data_stream'):
            kind = {'_index_template': 'template', '_component_template': 'component',
                    '_data_stream': 'data_stream'}[parts[0]]
            name = parts[1] if len(parts) > 1 else None
        elif parts[0] in ('_ingest', '_enrich', '_ilm', '_security'):
            kinds = {('_ingest', 'pipeline'): 'pipeline', ('_enrich', 'policy'): 'enrich',
                     ('_ilm', 'policy'): 'ilm', ('_security', 'user'): 'user',
                     ('_security', 'role'): 'role'}
            kind = kinds.get(tuple(parts[:2]))
            name = parts[2] if len(parts) > 2 else None
        elif parts[0] == '_snapshot':
            kind, name = 'repo', parts[1] if len(parts) > 1 else None
            if len(parts) > 2 and not parts[2].startswith('_'):
                if not self.owned(parts[2]):
                    raise RuntimeError('Snapshot name is outside the namespace.')
                self.snapshots.add((cluster, name, parts[2]))
        elif parts[0] == '_reindex':
            source = body.get('source', {}).get('index', '') if isinstance(body, dict) else ''
            destination = body.get('dest', {}).get('index', '') if isinstance(body, dict) else ''
            sources = source if isinstance(source, list) else [source]
            if not sources or not all(self.owned(item) for item in sources) or not self.owned(destination):
                raise RuntimeError('Reindex source/destination are outside the namespace.')
            self.resources['index'].add((cluster, destination))
            return
        else:
            raise RuntimeError(f'Global mutation is forbidden in isolated smoke: {method} {path}')
        if not kind or not name or not self.owned(name) or '*' in name or ',' in name:
            raise RuntimeError(f'Mutation is outside the namespace: {method} {path}')
        self.resources[kind].add((cluster, name))

    def call(self, cluster, method, path, body=None, *, raw=None,
             content_type='application/json', timeout=120, auth=None):
        path = self.names.rewrite(path)
        body = self.names.body(body)
        raw = self.names.raw(raw, content_type)
        self.record(cluster, method, path, body)
        # Only rename the username; the task's literal password remains unchanged.
        auth = (self.names.rewrite(auth[0]), auth[1]) if auth else None
        result = super().call(cluster, method, path, body, raw=raw,
                              content_type=content_type, timeout=timeout, auth=auth)
        return dict(result, body=self.names.rewrite(result['body'], reverse=True))

    def cleanup(self):
        failures = []
        def delete(cluster, method, path, accepted=(200, 201, 404), body=None):
            result = super(IsolatedElastic, self).call(cluster, method, path, body, timeout=120)
            if result['status'] not in accepted:
                failures.append({'cluster': cluster, 'method': method, 'path': path,
                                 'http': result['status'], 'response': result['body']})
        # Re-registering only our recorded repository allows snapshot cleanup if a
        # solution/preparation unregistered it. No other repository is touched.
        for cluster, name in self.resources['repo']:
            result = super().call(cluster, 'GET', '/_snapshot/' + name)
            if result['status'] == 404:
                location = '/mnt/elastic-snapshots/' + self.prefix + 'search'
                super().call(cluster, 'PUT', '/_snapshot/' + name,
                             {'type': 'fs', 'settings': {'location': location}})
        for cluster, name in sorted(self.resources['data_stream']):
            delete(cluster, 'DELETE', '/_data_stream/' + name)
        for cluster, name in sorted(self.resources['index']):
            # pause_follow is meaningful only for followers; ordinary-index errors
            # are expected and deletion below still targets the exact owned index.
            super().call(cluster, 'POST', f'/{name}/_ccr/pause_follow')
            delete(cluster, 'DELETE', '/' + name)
        # A mounted searchable index must be removed before its snapshot.
        for cluster, repo, snapshot in sorted(self.snapshots):
            delete(cluster, 'DELETE', f'/_snapshot/{repo}/{snapshot}')
        endpoints = [('template', '/_index_template/'), ('component', '/_component_template/'),
                     ('pipeline', '/_ingest/pipeline/'), ('enrich', '/_enrich/policy/'),
                     ('ilm', '/_ilm/policy/'), ('user', '/_security/user/'),
                     ('role', '/_security/role/'), ('repo', '/_snapshot/')]
        for kind, endpoint in endpoints:
            for cluster, name in sorted(self.resources[kind]):
                delete(cluster, 'DELETE', endpoint + name)
        # Enrich generates system indices whose exact names are not known before
        # executing a policy. Read their names, then delete only our policy's exact
        # generated indices. There is never a wildcard DELETE.
        for cluster, policy in sorted(self.resources['enrich']):
            result = super().call(cluster, 'GET', '/_cat/indices?format=json&expand_wildcards=all')
            if result['status'] == 200 and isinstance(result['body'], list):
                for index in result['body']:
                    name = index.get('index', '')
                    if name.startswith('.enrich-' + policy + '-'):
                        delete(cluster, 'DELETE', '/' + name)
        return failures

    def leftovers(self):
        found = []
        for cluster in ('cluster1', 'cluster2'):
            for endpoint, key in (('/_cat/indices?format=json&expand_wildcards=all', 'index'),
                                  ('/_cat/aliases?format=json&expand_wildcards=all', 'alias')):
                result = super().call(cluster, 'GET', endpoint)
                if result['status'] == 200 and isinstance(result['body'], list):
                    for item in result['body']:
                        name = item.get(key, '')
                        if self.prefix in name:
                            found.append({'cluster': cluster, 'kind': key, 'name': name})
        endpoints = {'pipeline': '/_ingest/pipeline/', 'enrich': '/_enrich/policy/',
                     'ilm': '/_ilm/policy/', 'template': '/_index_template/',
                     'component': '/_component_template/', 'data_stream': '/_data_stream/',
                     'user': '/_security/user/', 'role': '/_security/role/', 'repo': '/_snapshot/'}
        for kind, endpoint in endpoints.items():
            for cluster, name in sorted(self.resources[kind]):
                result = super().call(cluster, 'GET', endpoint + name)
                if result['status'] != 404:
                    # Security APIs return an empty object for a missing principal.
                    if result['status'] == 200 and (result['body'] == {}
                            or kind == 'enrich' and result['body'] == {'policies': []}):
                        continue
                    found.append({'cluster': cluster, 'kind': kind, 'name': name,
                                  'http': result['status']})
        return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8787')
    parser.add_argument('--output', default=str(Path(os.getenv('LAB_STATE_DIR', ROOT / 'state')) /
                                              'e-smoke-report.json'))
    parser.add_argument('--run-isolated', action='store_true')
    args = parser.parse_args()
    if not args.run_isolated:
        parser.error('--run-isolated is required to create temporary namespaced ES resources.')
    if urlsplit(args.url).hostname not in ('localhost', '127.0.0.1', '::1'):
        parser.error('Only a loopback lab URL is allowed.')
    output = Path(args.output)
    if not output.is_absolute():
        parser.error('--output must be an absolute path.')
    catalog = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
    tasks = [task for task in catalog['tasks'] if task['set'] == 'E']
    if [task['id'] for task in tasks] != [f'E{i:02d}' for i in range(1, 11)]:
        parser.error('E01-E10 must exist in order in the deployed catalog.')
    namespace = 'ece-e-smoke-' + uuid.uuid4().hex + '-'
    session = namespace + 'session'
    names = Names(namespace, tasks)
    es = IsolatedElastic(names, namespace)
    auth = 'Basic ' + base64.b64encode(f'{es.user}:{es.password}'.encode()).decode()
    state = Path(os.getenv('LAB_STATE_DIR', ROOT / 'state'))

    def app_call(path, body=None, headers=None, raw=None):
        supplied = {'Content-Type': 'application/json', 'X-Lab-Request': '1'}
        supplied.update(headers or {})
        data = raw.encode() if raw is not None else json.dumps(body).encode() if body is not None else None
        try:
            with urlopen(Request(args.url.rstrip('/') + path, data=data, headers=supplied), timeout=240) as response:
                payload = response.read().decode()
                return response.status, json.loads(payload) if payload else {}
        except HTTPError as error:
            payload = error.read().decode()
            try:
                payload = json.loads(payload)
            except ValueError:
                pass
            return error.code, payload

    def capture(task_id):
        database = state / 'history.sqlite3'
        with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
            rows = connection.execute('SELECT request,status,cluster FROM events WHERE session=? AND task_id=? ORDER BY id',
                                      (session, task_id)).fetchall()
        return [{'request': names.rewrite(json.loads(request), reverse=True),
                 'status': status, 'cluster': cluster} for request, status, cluster in rows]

    report = {'namespace': namespace, 'session': session,
              'scope': 'Real local ES and Kibana Console proxy; E checks use Verify with an isolated resource adapter. '
                       'Native capture is recorded under an existing active-set task in a dedicated session. '
                       'No reset, active-set change, or /api/check E end-to-end call is made.',
              'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'results': []}
    try:
        code, status = app_call('/api/status')
        if code != 200 or status['lab']['phase'] != 'ready':
            raise RuntimeError('The existing lab must be ready before the isolated smoke test.')
        if not all(status['kibana'][cluster]['connected'] for cluster in ('cluster1', 'cluster2')):
            raise RuntimeError('Both genuine Kibana instances must be connected.')
        report['lab_before'] = {key: status['lab'][key] for key in ('active_set', 'generation')}
        active_task = next(task['id'] for task in catalog['tasks']
                           if task['set'] == status['lab']['active_set'])
        report['capture_task_id'] = active_task
        fixtures = json.loads((ROOT / 'data/fixtures.json').read_text(encoding='utf-8'))['indices']
        overrides = ROOT / 'data/fixtures-e.json'
        if overrides.exists():
            extra = json.loads(overrides.read_text(encoding='utf-8'))
            extra = extra['indices'] if isinstance(extra, dict) else extra
            replacement = {(item['cluster'], item['index']): item for item in extra}
            fixtures = [replacement.get((item['cluster'], item['index']), item) for item in fixtures]
        selected = {('cluster1', 'blogs'), ('cluster1', 'categories'), ('cluster1', 'web_traffic'),
                    ('cluster1', 'moreblogs'), ('cluster2', 'blogs')}
        for fixture in fixtures:
            if (fixture['cluster'], fixture['index']) not in selected:
                continue
            cluster, index = fixture['cluster'], fixture['index']
            es.require(cluster, 'PUT', '/' + index, {'settings': fixture['settings'], 'mappings': fixture['mappings']})
            lines = []
            for document in fixture['documents']:
                lines.extend([json.dumps({'index': {'_id': document['_id']}}), json.dumps(document['_source'])])
            result = es.require(cluster, 'POST', f'/{index}/_bulk?refresh=true', raw='\n'.join(lines) + '\n',
                                content_type='application/x-ndjson')
            if result.get('errors'):
                raise RuntimeError(f'Fixture bulk failed: {cluster}/{index}')
        # Exercise the application's actual preparation method on isolated ES
        # resources and a throwaway state directory. Never call reset/cleanup.
        with tempfile.TemporaryDirectory(prefix=namespace) as temporary_state:
            Lab(es, Path(temporary_state)).prepare_e()
        for task in tasks:
            print(task['id'], task['title'], flush=True)
            checked = {'id': task['id'], 'complete': False}
            report['results'].append(checked)
            execution = []
            try:
                cluster = task['cluster']
                kibana = '1' if cluster == 'cluster1' else '2'
                before = len(capture(active_task))
                for request in parse_console(task['solution']):
                    path = names.rewrite(request.path)
                    body = names.body(request.body)
                    es.record(cluster, request.method, path, body)
                    headers = {'Authorization': auth, 'kbn-xsrf': 'true',
                               'x-elastic-internal-origin': 'Kibana',
                               'kbn-version': catalog['engine_version'],
                               'Content-Type': request.content_type,
                               'Cookie': f'ece_session={session}; ece_task_cluster1={active_task}; ece_task_cluster2={active_task}'}
                    proxy = f'/kibana{kibana}/api/console/proxy?' + urlencode({'path': path.lstrip('/'), 'method': request.method})
                    raw = names.raw(request.raw_body, request.content_type) if request.raw_body is not None else json.dumps(body) if body is not None else ''
                    http, response = app_call(proxy, headers=headers, raw=raw)
                    if http >= 400 or isinstance(response, dict) and any(response.get(key) for key in ('error', 'failures', 'errors')):
                        execution.append({'method': request.method, 'path': path, 'http': http, 'response': response})
                        break
                events = capture(active_task)[before:]
                checked['native_console_capture'] = any(event['request'].get('source') == 'kibana-console' for event in events)
                if execution:
                    checked['execution_failures'] = execution
                else:
                    for attempt in range(12):
                        result = Verify(es, task, cluster, task['solution'], task.get('answer', ''), history=events).run()
                        if result['complete']:
                            break
                        if attempt < 11:
                            time.sleep(3)
                    checked.update(result)
                    checked['complete'] = checked['complete'] and checked['native_console_capture']
                print('  PASS' if checked['complete'] else '  FAIL', flush=True)
            except Exception as error:
                checked['error'] = str(error)
                print('  FAIL', error, flush=True)
    except Exception as error:
        report['error'] = str(error)
        print('Preparation failed:', error, flush=True)
    finally:
        try:
            report['cleanup_failures'] = es.cleanup()
            report['leftovers'] = es.leftovers()
        except Exception as error:
            report['cleanup_failures'] = [{'error': str(error)}]
            report['leftovers'] = [{'error': 'Cleanup inspection did not finish.'}]
        code, status = app_call('/api/status')
        if code == 200:
            report['lab_after'] = {key: status['lab'][key] for key in ('active_set', 'generation')}
            report['current_set_preserved'] = report.get('lab_before') == report['lab_after']
        report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        report['complete'] = (len(report['results']) == 10 and all(item['complete'] for item in report['results'])
                              and not report.get('error') and not report['cleanup_failures']
                              and not report['leftovers'] and report.get('current_set_preserved', False))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{sum(item["complete"] for item in report["results"])}/10 passed. {output}', flush=True)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
