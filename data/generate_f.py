"""Append one authored set and build prerequisites loaded only for set F."""
import json
from pathlib import Path
from f_semantic import TASKS as SEMANTIC_TASKS,FIXTURES as SEMANTIC_FIXTURES
from f_esql import TASKS as ESQL_TASKS,FIXTURES as ESQL_FIXTURES
from f_streams import TASKS as STREAMS_TASKS,FIXTURES as STREAMS_FIXTURES

ROOT=Path(__file__).resolve().parent

def build():
    tasks=sorted(SEMANTIC_TASKS+ESQL_TASKS+STREAMS_TASKS,key=lambda t:t['number'])
    fixtures=SEMANTIC_FIXTURES+ESQL_FIXTURES+STREAMS_FIXTURES
    assert [t['id'] for t in tasks]==[f'F{i:02d}' for i in range(1,11)]
    assert len({(x['cluster'],x['index']) for x in fixtures})==len(fixtures)
    catalog=json.loads((ROOT/'catalog.json').read_text(encoding='utf-8'))
    catalog['sets']=[s for s in catalog['sets'] if s['id']!='F']+[
        {'id':'F','name':'F · Elastic 9.x · Semantic / ES|QL / Streams',
         'description':'직접 제작한 180분 실습 예상 시험 · Semantic Search 3문항, ES|QL 4문항, Kibana Streams 3문항'}]
    catalog['tasks']=[t for t in catalog['tasks'] if t['set']!='F']+tasks
    (ROOT/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'fixtures-f.json').write_text(json.dumps({'seed_version':2,'set':'F','synthetic':True,
        'indices':fixtures},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'F: {len(tasks)} tasks, {len(fixtures)} prerequisite datasets, {sum(len(x["documents"]) for x in fixtures)} documents')

if __name__=='__main__':build()
