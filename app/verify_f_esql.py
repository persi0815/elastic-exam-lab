"""Validate F ES|QL answers with real /_query columns and ordered values.

No exact reference-pipeline match is required: equivalent ES|QL expressions and
intermediate column names are accepted. The FROM/LOOKUP sources are constrained
to the exercise data, and ROW literals cannot replace the indexed source.
"""
from __future__ import annotations
import copy
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from console import Request, parse_console

SPECS = {
    'f_esql_orders': {'from': 'f-order-lines',
                      'columns': ['store', 'paid_cents', 'refund_cents', 'net_cents', 'cancelled_lines']},
    'f_esql_days': {'from': 'f-service-events',
                    'columns': ['day', 'requests', 'errors', 'slow', 'average_ms']},
    'f_esql_lookup': {'from': 'f-purchases', 'lookup': 'f-product-catalog',
                      'columns': ['department', 'purchase_rows', 'units', 'revenue_cents', 'unpriced_units']},
    'f_esql_tags': {'from': 'f-article-tags',
                    'columns': ['tag', 'articles', 'total_views']},
}


def is_esql(request):
    return urlsplit(request.path).path.rstrip('/') == '/_query'


def submitted(v):
    """Find the last Query API submission in the editor or native Console history."""
    parsed = parse_console(v.code) if v.code.strip() else []
    matching = [request for request in parsed if is_esql(request)]
    if matching:
        return matching[-1]
    for event in reversed(v.history):
        request = event.get('request', {})
        path = request.get('path', '')
        if urlsplit(path).path.rstrip('/') == '/_query':
            return Request(request.get('method', ''), path, request.get('body'),
                           None, 'application/json', 1)
    raise ValueError('검증할 POST /_query 요청이 없습니다. 편집기에 작성하거나 Console에서 실행하세요.')


def commands(query):
    """Split pipes outside literals/comments; this is a source guard, not a parser."""
    result, current = [], []
    i, quote, line_comment, block_comment = 0, None, False, False
    while i < len(query):
        char = query[i]
        pair = query[i:i + 2]
        if line_comment:
            if char == '\n':
                line_comment = False
                current.append(' ')
            i += 1
            continue
        if block_comment:
            if pair == '*/':
                block_comment = False
                current.append(' ')
                i += 2
            else:
                i += 1
            continue
        if quote:
            current.append(char)
            if char == '\\' and quote == '"' and i + 1 < len(query):
                current.append(query[i + 1])
                i += 2
                continue
            if char == quote:
                # Doubled backticks represent a literal backtick in an identifier.
                if quote == '`' and query[i:i + 2] == '``':
                    current.append('`')
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if pair == '//':
            line_comment = True
            i += 2
        elif pair == '/*':
            block_comment = True
            i += 2
        elif char in ('"', '`'):
            quote = char
            current.append(char)
            i += 1
        elif char == '|':
            result.append(''.join(current).strip())
            current = []
            i += 1
        else:
            current.append(char)
            i += 1
    result.append(''.join(current).strip())
    if quote or block_comment or any(not command for command in result):
        raise ValueError('ES|QL 파이프라인의 문자열·주석·명령 구분을 확인하세요.')
    return result


INDEX = r'(?P<name>"[^"\n]+"|`[^`\n]+`|[A-Za-z0-9_.-]+)'


def index_name(command, prefix):
    match = re.match(r'^' + prefix + r'\s+' + INDEX + r'(?P<rest>.*)$', command, re.I | re.S)
    if not match:
        return None, ''
    name = match.group('name')
    if name[:1] in ('"', '`'):
        name = name[1:-1]
    return name, match.group('rest').strip()


def source_contract(query, spec):
    pipeline = commands(query)
    name, rest = index_name(pipeline[0], 'FROM')
    from_ok = name == spec['from'] and (not rest or re.match(r'^METADATA\s+', rest, re.I))
    # Reject secondary source commands as well as a literal ROW source. The real
    # ES parser decides whether all remaining processing syntax is valid.
    sources = [command for command in pipeline
               if re.match(r'^(?:FROM|ROW|TS)\b', command, re.I)]
    # A secondary source hidden inside parentheses must not synthesize a result
    # table. Strip literal/quoted identifier contents before checking source words.
    outside_literals = re.sub(r'"(?:\\.|[^"\\])*"|`(?:``|[^`])*`', '""', '\n'.join(pipeline))
    source_words = re.findall(r'\b(?:FROM|ROW|TS)\b', outside_literals, re.I)
    from_ok = bool(from_ok and len(sources) == 1 and len(source_words) == 1)
    joins = [command for command in pipeline if re.match(r'^LOOKUP\s+JOIN\b', command, re.I)]
    if spec.get('lookup'):
        targets = [index_name(command, r'LOOKUP\s+JOIN') for command in joins]
        lookup_ok = (len(targets) == 1 and targets[0][0] == spec['lookup']
                     and bool(re.match(r'^ON\s+', targets[0][1], re.I)))
    else:
        lookup_ok = not joins
    return from_ok, lookup_ok


def scalar_equal(actual, expected, column_type):
    if actual is None or expected is None:
        return actual is expected
    if column_type in ('date', 'date_nanos'):
        try:
            def date(value):
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            return date(actual) == date(expected)
        except (AttributeError, TypeError, ValueError):
            return False
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6)
    return actual == expected


def ordered_values_equal(actual, expected, columns):
    if not isinstance(actual, list) or not isinstance(expected, list) or len(actual) != len(expected):
        return False
    return all(isinstance(left, list) and isinstance(right, list)
               and len(left) == len(right) == len(columns)
               and all(scalar_equal(a, b, spec.get('type')) for a, b, spec in zip(left, right, columns))
               for left, right in zip(actual, expected))


def run(v, body):
    payload = copy.deepcopy(body)
    # Columnar is an output serialization choice, not part of query semantics.
    payload['columnar'] = False
    return v.es.require(v.c, 'POST', '/_query?allow_partial_results=false', payload)


def query_check(v):
    spec = SPECS[v.t['check']]
    request = submitted(v)
    body = request.body if isinstance(request.body, dict) else {}
    query = body.get('query')
    api_ok = request.method == 'POST' and isinstance(query, str) and bool(query.strip())
    v.add('POST /_query의 ES|QL query 문자열', api_ok)
    if not api_ok:
        return
    from_ok, lookup_ok = source_contract(query, spec)
    v.add('실제 요구 인덱스 FROM / ROW 하드코딩 제외', from_ok, spec['from'])
    v.add('요구한 LOOKUP JOIN 대상', lookup_ok,
          spec.get('lookup', '이 문항은 다른 lookup 데이터를 사용하지 않습니다.'))
    if not from_ok or not lookup_ok:
        return
    actual = run(v, body)
    reference = next(q for q in reversed(parse_console(v.t['solution'])) if is_esql(q))
    expected = run(v, reference.body)
    actual_columns = actual.get('columns', [])
    expected_columns = expected.get('columns', [])
    actual_names = [column.get('name') for column in actual_columns]
    expected_names = [column.get('name') for column in expected_columns]
    v.add('요구된 출력 열 / 순서', actual_names == expected_names == spec['columns'],
          '요구: ' + ', '.join(spec['columns']))
    # Equivalent integer/double casts are allowed when actual values agree. Date
    # columns must remain dates so the exercise cannot pass using a display string.
    date_columns_ok = all(expected_column.get('type') not in ('date', 'date_nanos')
                          or actual_column.get('type') in ('date', 'date_nanos')
                          for actual_column, expected_column in zip(actual_columns, expected_columns))
    v.add('날짜 열 타입 / 완전한 실행 결과', date_columns_ok
          and not actual.get('is_partial', False) and not expected.get('is_partial', False))
    expected_values = expected.get('values', [])
    v.add('실제 모든 집계값 / 누락값 처리 / 행 정렬',
          bool(expected_values) and actual_names == expected_names
          and ordered_values_equal(actual.get('values'), expected_values, expected_columns),
          f'제출 {len(actual.get("values", []))}행 / 참조 {len(expected_values)}행. 실제 Query API 결과를 비교합니다.')


def state_check(v):
    raise ValueError('F ES|QL 문항은 POST /_query 실행 결과를 검증하는 query 문항입니다.')
