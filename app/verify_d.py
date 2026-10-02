"""Additional September practice checks. No official exam scoring is implied."""
from __future__ import annotations
import copy,math
from datetime import datetime
from console import parse_console

def subset(expected,actual):
    if isinstance(expected,dict):return isinstance(actual,dict) and all(k in actual and subset(v,actual[k]) for k,v in expected.items())
    if isinstance(expected,list):return isinstance(actual,list) and len(expected)==len(actual) and all(subset(a,b) for a,b in zip(expected,actual))
    if isinstance(expected,(int,float)) and isinstance(actual,(int,float)):return math.isclose(expected,actual,rel_tol=1e-6,abs_tol=1e-6)
    return expected==actual

def walk(v):
    if isinstance(v,dict):
        yield v
        for x in v.values():yield from walk(x)
    elif isinstance(v,list):
        for x in v:yield from walk(x)

def leaf(v):return v.get('value') if isinstance(v,dict) else v

def query_check(v):
    q=v.submitted();b=q.body or {};kind=v.t['check']
    v.add('대상 article',q.path.split('?')[0].rstrip('/')=='/article/_search')
    if kind=='knn':
        spec=next((x['knn'] for x in walk(b) if isinstance(x.get('knn'),dict)),{})
        v.add('kNN 벡터 필드 / 입력 벡터',spec.get('field')=='vector.cosine' and spec.get('query_vector')==[10,3,5,4,1,2])
        v.add('k와 size가 모두 10',spec.get('k',b.get('size',10))==10 and b.get('size',10)==10)
        v.add('kNN 내부 tags pre-filter',any(leaf(x.get('term',{}).get('tags'))=='term' for x in walk(spec.get('filter',{}))))
        result=v.run_search(q);hits=result.get('hits',{}).get('hits',[])
        fixtures=v.fixture('article');query=[10,3,5,4,1,2]
        def cosine(vector):return sum(a*c for a,c in zip(query,vector))/(math.sqrt(sum(a*a for a in query))*math.sqrt(sum(a*a for a in vector)))
        allowed={i:d for i,d in fixtures.items() if 'term' in d['tags']}
        cutoff=sorted((cosine(d['vector']['cosine']) for d in allowed.values()),reverse=True)[9]
        v.add('필터를 만족하는 실제 결과 10건',len(hits)==10 and len({h['_id'] for h in hits})==10 and all(h['_id'] in allowed for h in hits))
        v.add('cosine top-10 이웃 / 경계 동점 허용',len(hits)==10 and all(h['_id'] in allowed and cosine(allowed[h['_id']]['vector']['cosine'])>=cutoff-1e-6 for h in hits),
              '작은 합성 데이터의 exact cosine 기준과 비교합니다. ANN 경계 결과는 수동 검토가 필요할 수 있습니다.')
        v.add('title/category만 문서 필드로 반환',bool(hits) and all(set(h.get('_source',{}))|set(h.get('fields',{}))=={'title','category'} for h in hits))
        return
    # D07: keep scoring vs filters distinct, but compare actual date-sorted results too.
    ref=[r for r in parse_console(v.t['solution']) if r.path.endswith('/_search')][-1]
    boolean=b.get('query',{}).get('bool',{})
    v.add('body kubernetes는 must',any((x.get('match',{}).get('body',{}).get('query') if isinstance(x.get('match',{}).get('body'),dict) else x.get('match',{}).get('body'))=='kubernetes' for x in walk(boolean.get('must',[]))))
    v.add('tags devops는 filter',any(leaf(x.get('term',{}).get('tags'))=='devops' for x in walk(boolean.get('filter',[]))))
    v.add('featured true는 선택적 should',any(leaf(x.get('term',{}).get('featured')) is True for x in walk(boolean.get('should',[]))) and int(boolean.get('minimum_should_match',0))==0)
    v.add('20번째부터 5건 (실습 명시 from:19)',b.get('from',0)==19 and b.get('size',10)==5)
    from verify import sort_spec,equivalent
    v.add('date_time 내림차순',sort_spec(b)==[('date_time','desc')])
    actual=v.run_search(q).get('hits',{}).get('hits',[]);expected=v.run_search(ref).get('hits',{}).get('hits',[])
    v.add('실제 페이지 결과',len(actual)==5 and {h['_id'] for h in actual}=={h['_id'] for h in expected})

def state_check(v):
    kind=v.t['check']
    if kind in ('article_enrich','article_stop'):
        dest='task2' if kind=='article_enrich' else 'task3'
        orig=v.fixture('article');docs=v.docs(dest)
        v.add('480개 문서 ID 유지',set(orig)==set(docs))
        if kind=='article_enrich':
            refs={d['region_id']:d for d in v.fixture('regions').values()}
            expected={i:dict(copy.deepcopy(d),region_info=copy.deepcopy(refs[d['region']])) for i,d in orig.items()}
            v.add('region_info에 id/name/description 보강',all(docs.get(i,{}).get('region_info')==refs[d['region']] for i,d in orig.items()))
            v.add('기존 region 및 모든 문서 필드 유지',subset(expected,docs) and all(set(docs.get(i,{}))==set(d) for i,d in expected.items()))
        else:
            from verify import FIXTURES
            p=v.props('task3');source=FIXTURES[('cluster1','article')]['mappings']['properties']
            v.add('title text only',p.get('title',{}).get('type')=='text' and not p.get('title',{}).get('fields'))
            v.add('article_id keyword only',p.get('article_id',{}).get('type')=='keyword' and not p.get('article_id',{}).get('fields'))
            v.add('기타 매핑 유지 (vector 포함)',all(subset(x,p.get(k)) for k,x in source.items() if k not in ('title','article_id')))
            v.add('원본 필드 및 데이터 보존',subset(orig,docs) and all(set(docs.get(i,{}))==set(d) for i,d in orig.items()))
            for word in ('to','the','and'):
                r=v.get('/task3/_search',body={'size':0,'query':{'match':{'title':word}}})
                v.add(f'{word} 검색 0건',r['hits']['total']['value']==0)
            a=v.es.require(v.c,'POST','/task3/_analyze',{'field':'title','text':'to the and'})
            v.add('title analyzer에서 세 토큰 제거',not a.get('tokens'))
            r=v.get('/article/_search',body={'size':0,'track_total_hits':True,'query':{'match':{'title':'to'}}})
            v.add('원본 article의 to 357건 유지',r['hits']['total']['value']==357)
        return
    if kind=='default_pipeline':
        p=v.get('/_ingest/pipeline/task9')['task9'];steps=p.get('processors',[])
        settings=v.get('/ingest-logs/_settings')['ingest-logs']['settings']['index']
        baseline=v.get('/ece-lab-control/_doc/baselines')['_source']['ingest_logs_uuid']
        v.add('기존 인덱스 UUID 유지 (재생성 없음)',settings.get('uuid')==baseline)
        v.add('default pipeline task9',settings.get('default_pipeline')=='task9')
        v.add('grok이 message에서 추출',any(x.get('grok',{}).get('field')=='message' for x in steps))
        v.add('convert duration_ms integer',any(x.get('convert',{}).get('field')=='duration_ms' and x.get('convert',{}).get('type')=='integer' for x in steps))
        props=v.props('ingest-logs')
        v.add('duration_ms integer / @timestamp date 매핑',props.get('duration_ms',{}).get('type')=='integer' and props.get('@timestamp',{}).get('type')=='date')
        samples=[{'message':'HTTP 200 ABC 125','raw_time':'2015-12-31T00:00:00Z'},
                 {'message':'HTTP 503 ABC 37','raw_time':'2012-06-01T12:34:56Z'}]
        out=v.es.require(v.c,'POST','/_ingest/pipeline/task9/_simulate',{'docs':[{'_source':d} for d in samples]})
        results=[x.get('doc',{}).get('_source',{}) for x in out.get('docs',[])]
        def parsed_date(text):
            try:return datetime.fromisoformat(text.replace('Z','+00:00')).isoformat()
            except (ValueError,AttributeError):return None
        v.add('두 샘플을 올바르게 파싱',len(results)==2 and all(str(d.get('response_status'))==s['message'].split()[1] and d.get('duration_ms')==int(s['message'].split()[-1]) and parsed_date(d.get('@timestamp'))==parsed_date(s['raw_time']) and 'raw_time' not in d for d,s in zip(results,samples)))
        docs=v.docs('ingest-logs')
        v.add('실제 색인 결과 존재',any(d.get('duration_ms')==125 and str(d.get('response_status'))=='200' and parsed_date(d.get('@timestamp'))==parsed_date(samples[0]['raw_time']) and 'raw_time' not in d for d in docs.values()))
        requests=[h.get('request',{}) for h in v.history]
        requests += [r.public() for r in parse_console(v.code)] if v.code.strip() else []
        v.add('pipeline 쿼리 파라미터 없이 실제 색인',any(r.get('method') in ('POST','PUT') and r.get('path','').startswith('/ingest-logs/_doc') and 'pipeline=' not in r.get('path','') for r in requests),
              '실제 Kibana Console 실행 기록을 자동 수집합니다. 별도 포트에서 실행했다면 답안에 해당 요청도 붙여 넣으세요.')
        return
    raise ValueError('Unknown D check '+kind)
