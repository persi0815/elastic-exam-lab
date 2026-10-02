"""Fixture edge cases and verifier contracts; mocked API tests are not live ES tests."""
from __future__ import annotations
import copy
import json
import sys
import unittest
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'data'))
from console import parse_console
from f_esql import TASKS, FIXTURES
import verify_f_esql as verifier

BY_TASK = {task['id']: task for task in TASKS}
BY_INDEX = {item['index']: item for item in FIXTURES}


def documents(index):
    return [doc['_source'] for doc in BY_INDEX[index]['documents']]


class FixtureEdges(unittest.TestCase):
    def test_four_independent_tasks_and_lookup_mode(self):
        self.assertEqual([task['id'] for task in TASKS], ['F04', 'F05', 'F06', 'F07'])
        self.assertEqual(len(BY_INDEX), 5)
        for task in TASKS:
            self.assertEqual(len(parse_console(task['solution'])), 1)
            request = parse_console(task['solution'])[0]
            self.assertEqual((request.method, request.path), ('POST', '/_query'))
            self.assertTrue(set(task['datasets']) <= set(BY_INDEX))
        lookup = BY_INDEX['f-product-catalog']
        self.assertEqual(lookup['settings']['index.mode'], 'lookup')
        self.assertEqual(lookup['settings']['number_of_shards'], 1)
        skus = [doc['sku'] for doc in documents('f-product-catalog')]
        self.assertEqual(len(skus), len(set(skus)))

    def test_orders_include_zero_filtered_sums_and_net_tie(self):
        groups = defaultdict(lambda: [0, 0, 0])
        for doc in documents('f-order-lines'):
            if (not doc.get('store') or doc.get('quantity', 0) <= 0
                    or doc.get('unit_price_cents', -1) < 0
                    or doc.get('status') not in ('paid', 'refunded', 'cancelled')):
                continue
            paid, refunded, cancelled = groups[doc['store']]
            amount = doc['quantity'] * doc['unit_price_cents'] - doc.get('discount_cents', 0)
            if doc['status'] == 'paid':
                paid += amount
            elif doc['status'] == 'refunded':
                refunded += amount
            else:
                cancelled += 1
            groups[doc['store']] = [paid, refunded, cancelled]
        rows = [[store, paid, refund, paid - refund, cancel]
                for store, (paid, refund, cancel) in groups.items()]
        self.assertEqual(sorted(rows, key=lambda row: (-row[3], row[0])), [
            ['north', 4400, 1000, 3400, 1], ['south', 1400, 450, 950, 2],
            ['west', 950, 0, 950, 0], ['east', 0, 1400, -1400, 1]])

    def test_daily_data_covers_utc_offsets_null_latency_and_bounds(self):
        groups = defaultdict(list)
        for doc in documents('f-service-events'):
            if doc.get('environment') != 'production' or '@timestamp' not in doc:
                continue
            timestamp = datetime.fromisoformat(doc['@timestamp'].replace('Z', '+00:00')).astimezone(timezone.utc)
            if '2026-09-01' <= timestamp.date().isoformat() < '2026-09-04':
                groups[timestamp.date().isoformat()].append(doc)
        rows = []
        for day, docs in sorted(groups.items()):
            latencies = [doc['latency_ms'] for doc in docs if 'latency_ms' in doc]
            rows.append([day, len(docs), sum(doc.get('status_code', 0) >= 500 for doc in docs),
                         sum(doc.get('latency_ms', 0) >= 500 for doc in docs), round(sum(latencies) / len(latencies), 1)])
        self.assertEqual(rows, [['2026-09-01', 4, 2, 2, 533.3],
                                ['2026-09-02', 3, 1, 2, 516.7],
                                ['2026-09-03', 3, 1, 0, 75.0]])

    def test_lookup_distinguishes_free_missing_and_unknown_products(self):
        catalog = {doc['sku']: doc for doc in documents('f-product-catalog')}
        groups = defaultdict(lambda: [0, 0, 0, 0])
        for purchase in documents('f-purchases'):
            qty = purchase.get('quantity', 0)
            if purchase['state'] != 'completed' or qty <= 0:
                continue
            product = catalog.get(purchase.get('sku'), {})
            group = groups[product.get('department', 'unknown')]
            group[0] += 1
            group[1] += qty
            group[2] += qty * product.get('unit_price_cents', 0)
            group[3] += qty if 'unit_price_cents' not in product else 0
        rows = [[department] + values for department, values in groups.items()]
        self.assertEqual(sorted(rows, key=lambda row: (-row[3], row[0])), [
            ['electronics', 3, 8, 20000, 4], ['books', 3, 5, 3600, 0], ['unknown', 2, 3, 0, 3]])

    def test_multivalue_duplicate_tokens_change_sum_without_dedup(self):
        groups, naive = defaultdict(lambda: [set(), 0]), defaultdict(int)
        for doc in documents('f-article-tags'):
            if not doc['published'] or not doc.get('tags_csv'):
                continue
            tags = doc['tags_csv'].split(',')
            for tag in tags:
                if tag:
                    naive[tag] += doc.get('views', 0)
            for tag in set(tags) - {''}:
                groups[tag][0].add(doc['article_id'])
                groups[tag][1] += doc.get('views', 0)
        rows = [[tag, len(ids), views] for tag, (ids, views) in groups.items()]
        self.assertEqual(sorted(rows, key=lambda row: (-row[1], -row[2], row[0])), [
            ['search', 4, 225], ['data', 4, 135], ['observability', 3, 125]])
        self.assertEqual(naive['search'], 325)
        self.assertEqual(naive['data'], 160)


ORDER_ROWS = [['north', 4400, 1000, 3400, 1], ['south', 1400, 450, 950, 2],
              ['west', 950, 0, 950, 0], ['east', 0, 1400, -1400, 1]]


def response(task_id='F04'):
    task = BY_TASK[task_id]
    columns = verifier.SPECS[task['check']]['columns']
    types = ['keyword'] + ['long'] * (len(columns) - 1)
    values = ORDER_ROWS
    if task_id == 'F05':
        types = ['date', 'long', 'long', 'long', 'double']
        values = [['2026-09-01T00:00:00.000Z', 4, 2, 2, 533.3],
                  ['2026-09-02T00:00:00.000Z', 3, 1, 2, 516.7],
                  ['2026-09-03T00:00:00.000Z', 3, 1, 0, 75.0]]
    return {'columns': [{'name': name, 'type': kind} for name, kind in zip(columns, types)],
            'values': copy.deepcopy(values), 'is_partial': False}


class View:
    def __init__(self, task_id='F04'):
        self.t, self.c = copy.deepcopy(BY_TASK[task_id]), 'cluster1'
        self.code, self.history, self.checks = self.t['solution'], [], []
        self.actual, self.expected = response(task_id), response(task_id)
        self.es, self.calls = self, []

    def add(self, label, ok, detail=''):
        self.checks.append({'label': label, 'ok': bool(ok), 'detail': detail})

    def require(self, cluster, method, path, body=None):
        self.calls.append((cluster, method, path, copy.deepcopy(body)))
        return copy.deepcopy(self.actual if len(self.calls) % 2 else self.expected)

    def query(self, query, **options):
        self.code = 'POST /_query\n' + json.dumps(dict(query=query, **options))

    def passed(self):
        verifier.query_check(self)
        return bool(self.checks) and all(check['ok'] for check in self.checks)


class QueryContracts(unittest.TestCase):
    def test_live_api_execution_is_required_and_columnar_is_normalized(self):
        view = View()
        query = parse_console(view.code)[0].body['query']
        view.query(query, columnar=True)
        self.assertTrue(view.passed(), view.checks)
        self.assertEqual(len(view.calls), 2)
        self.assertTrue(all(call[:3] == ('cluster1', 'POST', '/_query?allow_partial_results=false')
                            and call[3]['columnar'] is False for call in view.calls))

    def test_equivalent_intermediate_alias_and_comments_are_accepted(self):
        view = View()
        query = parse_console(view.code)[0].body['query']
        view.query('/* authored equivalent */\n' + query.replace('line_cents', 'subtotal') + '\n// done')
        self.assertTrue(view.passed(), view.checks)

    def test_row_literal_cannot_pass_with_correct_table(self):
        view = View()
        view.query('ROW store="north", net_cents=3400')
        self.assertFalse(view.passed())
        self.assertEqual(view.calls, [])

    def test_additional_remote_or_wildcard_sources_are_rejected(self):
        for source in ('f-order-lines,*', 'f-order-lines,remote:f-order-lines',
                       'f-order-*', 'remote:f-order-lines', 'f-order-lines,f-purchases'):
            with self.subTest(source=source):
                view = View()
                view.query('FROM ' + source + ' | KEEP store')
                self.assertFalse(view.passed())
                self.assertEqual(view.calls, [])

    def test_nested_row_source_is_rejected(self):
        view = View()
        view.query('FROM f-order-lines | WHERE store IN (ROW store="north")')
        self.assertFalse(view.passed())
        self.assertEqual(view.calls, [])

    def test_source_words_inside_literals_do_not_block_valid_query(self):
        spec = verifier.SPECS['f_esql_orders']
        self.assertEqual(verifier.source_contract('FROM "f-order-lines" | EVAL note="ROW | FROM TS" | DROP note', spec), (True, True))

    def test_missing_query_string_does_not_make_api_call(self):
        view = View()
        view.query(None)
        self.assertFalse(view.passed())
        self.assertEqual(view.calls, [])

    def test_native_history_is_used_when_editor_has_no_query(self):
        view = View()
        request = parse_console(view.code)[0]
        view.history = [{'request': dict(request.public(), source='kibana-console')}]
        view.code = ''
        self.assertTrue(view.passed(), view.checks)

    def test_editor_submission_takes_priority_over_history(self):
        view = View()
        view.history = [{'request': parse_console(view.code)[0].public()}]
        view.query('ROW wrong=1')
        self.assertFalse(view.passed())

    def test_lookup_must_read_the_required_lookup_index(self):
        task = BY_TASK['F06']
        query = parse_console(task['solution'])[0].body['query']
        spec = verifier.SPECS[task['check']]
        self.assertEqual(verifier.source_contract(query, spec), (True, True))
        self.assertEqual(verifier.source_contract(query.replace('f-product-catalog', 'other-lookup'), spec), (True, False))
        self.assertEqual(verifier.source_contract(query.replace('| LOOKUP JOIN f-product-catalog ON sku', ''), spec), (True, False))

    def test_wrong_value_fails_even_if_query_text_is_the_reference(self):
        view = View()
        view.actual['values'][0][3] += 1
        self.assertFalse(view.passed())

    def test_wrong_row_order_and_missing_rows_are_rejected(self):
        view = View()
        view.actual['values'].reverse()
        self.assertFalse(view.passed())
        view = View()
        view.actual['values'].pop()
        self.assertFalse(view.passed())

    def test_column_order_is_required(self):
        view = View()
        view.actual['columns'][1], view.actual['columns'][2] = view.actual['columns'][2], view.actual['columns'][1]
        for row in view.actual['values']:
            row[1], row[2] = row[2], row[1]
        self.assertFalse(view.passed())

    def test_equivalent_numeric_cast_is_allowed(self):
        view = View()
        view.actual['columns'][3]['type'] = 'double'
        for row in view.actual['values']:
            row[3] = float(row[3])
        self.assertTrue(view.passed(), view.checks)

    def test_date_serialization_can_vary_but_type_must_stay_temporal(self):
        view = View('F05')
        view.actual['values'][0][0] = '2026-09-01T09:00:00+09:00'
        self.assertTrue(view.passed(), view.checks)
        view = View('F05')
        view.actual['columns'][0]['type'] = 'keyword'
        self.assertFalse(view.passed())

    def test_partial_or_empty_reference_results_cannot_pass(self):
        view = View()
        view.actual['is_partial'] = True
        self.assertFalse(view.passed())
        view = View()
        view.actual['values'], view.expected['values'] = [], []
        self.assertFalse(view.passed())


if __name__ == '__main__':
    unittest.main(verbosity=2)
