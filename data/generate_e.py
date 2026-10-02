"""Append deterministic fixtures for the supplied ECE Practice Exam, preserving A-D."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from generate import entry, text

ROOT = Path(__file__).resolve().parent
E_KEYS = {('cluster1', 'web_traffic'), ('cluster2', 'blogs'), ('cluster1', 'moreblogs')}


def extend(indices):
    """Only the three E fixtures are replaced when this extension is rerun."""
    result = [copy.deepcopy(item) for item in indices
              if (item['cluster'], item['index']) not in E_KEYS]
    blogs = next(item for item in result
                 if item['cluster'] == 'cluster1' and item['index'] == 'blogs')

    agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
        '(KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (compatible; MJ12bot/v1.4.8; http://mj12bot.com/)',
    ]
    locations = [(39.1029, -94.5713), (37.5665, 126.9780),
                 (52.5200, 13.4050), (51.5074, -0.1278)]
    traffic = []
    for i in range(24):
        lat, lon = locations[i % len(locations)]
        traffic.append({
            '@timestamp': f'2021-03-{1 + i:02d}T19:25:05.000-06:00',
            'bytes_sent': 26774 + 137 * i,
            'content_type': 'text/html; charset=utf-8' if i % 3 else 'application/json',
            'geoip_location_lat': lat,
            'geoip_location_lon': lon,
            'is_https': i % 5 != 0,
            'request': ['/blog/introducing-elastic-endpoint-security',
                        '/blog/open-source-search', '/docs/search'][i % 3],
            'response': [200, 200, 201, 404][i % 4],
            'runtime_ms': 191 + 7 * i,
            'user_Agent': agents[i % len(agents)],
            'verb': 'POST' if i % 4 == 2 else 'GET',
        })
    result.append(entry('web_traffic', {
        '@timestamp': {'type': 'date'},
        'bytes_sent': {'type': 'long'},
        'content_type': {'type': 'keyword'},
        'geoip_location_lat': {'type': 'double'},
        'geoip_location_lon': {'type': 'double'},
        'is_https': {'type': 'boolean'},
        'request': {'type': 'keyword'},
        'response': {'type': 'long'},
        'runtime_ms': {'type': 'long'},
        'user_Agent': {'type': 'keyword'},
        'verb': {'type': 'keyword'},
    }, traffic))

    leader = copy.deepcopy(blogs)
    leader['cluster'] = 'cluster2'
    # The PDF explicitly supplies seven leader documents. Reuse synthetic blog
    # content and stable blogs-0001..blogs-0007 IDs, without changing cluster1.
    leader['documents'] = leader['documents'][:7]
    result.append(leader)

    archive = copy.deepcopy(blogs)
    archive['index'] = 'moreblogs'
    archive['mappings']['properties']['tags'] = {'properties': {'product': text()}}
    archive['documents'] = archive['documents'][:24]
    for i, document in enumerate(archive['documents'], 1):
        document['_id'] = f'moreblogs-{i:04d}'
        document['_source']['tags'] = {
            'product': 'Elasticsearch' if i <= 22 else ('Kibana' if i == 23 else 'Logstash')
        }
    result.append(archive)
    return result


def overrides(indices):
    """E10 uses explicit 2025 dates so its relative two-year window has hits."""
    blogs = copy.deepcopy(next(item for item in indices
                               if item['cluster'] == 'cluster1' and item['index'] == 'blogs'))
    for document in blogs['documents']:
        date = document['_source']['publish_date']
        document['_source']['publish_date'] = '2025' + date[4:]
    return [blogs]


if __name__ == '__main__':
    path = ROOT / 'fixtures.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['indices'] = extend(payload['indices'])
    # Preserve seed_version=2 so deploying the new catalog does not reset the
    # already running lab. New fixtures are loaded by an explicit set reset.
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'fixtures-e.json').write_text(
        json.dumps({'indices': overrides(payload['indices'])}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    print('indices', len(payload['indices']),
          'documents', sum(len(item['documents']) for item in payload['indices']))
