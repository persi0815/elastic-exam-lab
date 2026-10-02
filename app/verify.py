"""Transparent practice checks, not Elastic's scoring algorithm.

Checks query results against this lab's reference query and inspects actual cluster state.
Some equivalent implementations can require manual review. No eval/exec of student code.
"""
from __future__ import annotations
import copy,json,math,re
from urllib.parse import urlsplit
from console import parse_console,ConsoleError
from lab import FIX,F_FIX

FIXTURES={(x['cluster'],x['index']):x for x in FIX+F_FIX}

def flatten(d,prefix=''):
    out={}
    if not isinstance(d,dict):return out
    for k,v in d.items():
        path=f'{prefix}.{k}' if prefix else k
        if isinstance(v,dict):out.update(flatten(v,path))
        else:out[path]=v
    return out

def walk(value):
    if isinstance(value,dict):
        yield value
        for v in value.values():yield from walk(v)
    elif isinstance(value,list):
        for v in value:yield from walk(v)

def equivalent(a,b):
    if isinstance(a,(float,int)) and isinstance(b,(float,int)) and not isinstance(a,bool):
        return math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-6)
    if type(a)!=type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(equivalent(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
    return a==b

def canon_agg(value):
    # Names of aggregation nodes, bucket display labels and date formats are not grading constraints.
    if isinstance(value,dict):
        if 'buckets' in value:
            buckets=value['buckets'];buckets=list(buckets.values()) if isinstance(buckets,dict) else buckets
            out=[]
            for b in buckets:
                ident={k:b[k] for k in ('from','to','doc_count') if k in b}
                if 'from' not in b and 'to' not in b and 'key' in b:ident['key']=b['key']
                ident['metrics']=sorted([canon_agg(v) for k,v in b.items() if k not in ('key','key_as_string','from','to','from_as_string','to_as_string','doc_count') and isinstance(v,dict)],key=lambda x:json.dumps(x,sort_keys=True))
                out.append(ident)
            return {'buckets':out}
        if 'value' in value:return {'value':value['value']}
        return sorted([canon_agg(v) for v in value.values() if isinstance(v,dict)],key=lambda x:json.dumps(x,sort_keys=True))
    return value

def duration(value):
    if value is None:return 0
    m=re.fullmatch(r'(\d+(?:\.\d+)?)(ms|s|m|h|d)',str(value))
    return float(m.group(1))*{'ms':.001,'s':1,'m':60,'h':3600,'d':86400}[m.group(2)] if m else -1

def sort_spec(body):
    out=[]
    for x in body.get('sort',[]):
        if isinstance(x,str):out.append((x,'desc' if x=='_score' else 'asc'))
        elif isinstance(x,dict):
            for k,v in x.items():out.append((k,v.get('order','desc' if k=='_score' else 'asc') if isinstance(v,dict) else v))
    return out

class Verify:
    def __init__(self,es,task,cluster,code,answer='',history=()):
        self.es=es;self.t=task;self.c=cluster;self.code=code;self.answer=answer;self.history=history;self.checks=[]
    def add(self,label,ok,detail=''):
        self.checks.append({'label':label,'ok':bool(ok),'detail':detail})
    def get(self,path,c=None,body=None):
        r=self.es.get(c or self.c,path,body)
        if r['status']>=400:raise RuntimeError(f'GET {path}: HTTP {r["status"]} {json.dumps(r["body"],ensure_ascii=False)[:600]}')
        return r['body']
    def props(self,index):return self.get(f'/{index}/_mapping')[index]['mappings'].get('properties',{})
    def docs(self,index,c=None):
        self.es.require(c or self.c, 'POST', f'/{index}/_refresh')
        r=self.get(f'/{index}/_search',c,{'size':10000,'query':{'match_all':{}},'track_total_hits':True,'_source':{'exclude_vectors':False}})
        return {h['_id']:h['_source'] for h in r.get('hits',{}).get('hits',[])}
    def fixture(self,index,c=None):return {x['_id']:x['_source'] for x in FIXTURES[(c or self.c,index)]['documents']}
    def submitted(self):
        try:requests=parse_console(self.code)
        except ConsoleError:requests=[]
        queries=[r for r in requests if re.search(r'/_(?:search|async_search)(?:/template)?(?:\?|$)',r.path)]
        if queries:return queries[-1]
        for h in reversed(self.history):
            q=h.get('request',{})
            if re.search(r'/_(?:search|async_search)(?:/template)?(?:\?|$)',q.get('path','')):
                from console import Request
                return Request(q['method'],q['path'],q.get('body'),None,'application/json',1)
        raise RuntimeError('검증할 검색 요청이 없습니다. 편집기에 검색 요청을 작성하거나 먼저 실행하세요.')
    def run_search(self,request,body=None):
        b=request.body if body is None else body
        # Reference checks use synchronous retrieval for full result comparison. For async
        # task the submitted endpoint is checked separately and is still actually executed.
        path=request.path
        if '/_async_search' in path:path=path.split('/_async_search')[0]+'/_search'
        return self.get(path,body=b)
    def check_query(self):
        if self.t['check'].startswith('f_'):
            from verify_f import query_check
            return query_check(self)
        if self.t['check'].startswith('e_'):
            from verify_e import query_check
            return query_check(self)
        if self.t['check'] in ('knn','article_bool'):
            from verify_d import query_check
            return query_check(self)
        q=self.submitted();body=q.body or {}
        ref=[r for r in parse_console(self.t['solution']) if re.search(r'/_(?:search|async_search)(?:\?|$)',r.path)][-1]
        expected_path=ref.path.split('?')[0];actual_path=q.path.split('?')[0]
        self.add('대상 인덱스 / API',set(actual_path.split('/_')[0].strip('/').split(','))==set(expected_path.split('/_')[0].strip('/').split(',')),actual_path)
        kind=self.t['check']
        if kind=='weekly':self.add('Async Search API 사용',actual_path.endswith('/_async_search') and q.method=='POST')
        if kind in ('weekly','profit','stock','monthly'):
            self.add('개별 문서 hits 제외',body.get('size')==0)
            if kind in ('profit','stock'):
                name='profit' if kind=='profit' else 'difference'
                self.add('검색 시 runtime field 생성',name in body.get('runtime_mappings',{}))
                self.add('runtime field로 범위 집계',any(x.get('range',{}).get('field')==name for x in walk(body.get('aggs',body.get('aggregations',{})))))
            result=self.run_search(q);expected=self.run_search(ref)
            self.add('모든 버킷 경계·문서 수·집계 값',equivalent(canon_agg(result.get('aggregations',{})),canon_agg(expected.get('aggregations',{}))),'집계 이름은 달라도 됩니다. 이 실습 데이터의 참조 결과와 비교합니다.')
            return
        if kind in ('page_movies','page_inspections'):
            self.add('from / size',body.get('from',0)==ref.body['from'] and body.get('size',10)==5)
            self.add('정렬 우선순위 / 방향',sort_spec(body)==sort_spec(ref.body))
            actual=self.run_search(q).get('hits',{});expected=self.run_search(ref).get('hits',{})
            a=[h.get('sort') for h in actual.get('hits',[])];b=[h.get('sort') for h in expected.get('hits',[])]
            self.add('해당 페이지의 실제 정렬 값',bool(a) and equivalent(a,b),'완전 동률 문서의 내부 순서는 따로 강제하지 않습니다.')
            return
        # Compare all matching ids instead of only the first page, even when the user asks for 10.
        b=copy.deepcopy(body);b['size']=10000;b['from']=0;b['track_total_hits']=True
        er=copy.deepcopy(ref.body);er['size']=10000;er['from']=0;er['track_total_hits']=True
        result=self.run_search(q,b);expected=self.run_search(ref,er)
        actual_hits=result.get('hits',{}).get('hits',[]);expected_hits=expected.get('hits',{}).get('hits',[])
        aset={(h['_index'],h['_id']) for h in actual_hits};eset={(h['_index'],h['_id']) for h in expected_hits}
        self.add('매칭 문서 집합',aset==eset,f'제출 쿼리 {len(aset)}건 / 참조 쿼리 {len(eset)}건')
        if kind=='field_count':
            em={h['_id']:h['_score'] for h in expected_hits}
            self.add('점수 = 일치한 필드 개수',len(actual_hits)==len(expected_hits) and all(equivalent(h['_score'],em.get(h['_id'],-1)) for h in actual_hits))
        elif kind=='phrase':
            self.add('phrase 검색 사용',any('match_phrase' in x or x.get('multi_match',{}).get('type')=='phrase' for x in walk(body)))
        elif kind=='ccs':
            self.add('로컬/원격 클러스터를 모두 검색',',' in q.path and 'cluster2:listings2' in q.path)
            self.add('구문 검색 포함',any('match_phrase' in x or x.get('multi_match',{}).get('type')=='phrase' for x in walk(body)))
        elif kind=='boost':
            bs=body.get('query',{}).get('bool',{})
            self.add('추가 점수 조건이 선택적',bool(bs.get('should')) and bool(bs.get('must') or bs.get('filter')) and bs.get('minimum_should_match',0) in (0,'0'))
            self.add('tags phrase 점수 조건',any(x.get('match_phrase',{}).get('tags') in ('romantic comedy',) or (isinstance(x.get('match_phrase',{}).get('tags'),dict) and x['match_phrase']['tags'].get('query')=='romantic comedy') for x in walk(bs.get('should',[]))))
        elif kind=='highlight':
            self.add('content 하이라이트 설정','content' in body.get('highlight',{}).get('fields',{}))
            h=body.get('highlight',{});local=h.get('fields',{}).get('content',{})
            self.add('태그 설정',local.get('pre_tags',h.get('pre_tags'))==['<strong>'] and local.get('post_tags',h.get('post_tags'))==['</strong>'])
            self.add('정렬 우선순위',sort_spec(body)==sort_spec(ref.body))
            self.add('실제 highlight 응답',any(h.get('highlight',{}).get('content') for h in actual_hits))
        elif kind=='most_fields':
            m=body.get('query',{}).get('multi_match',{})
            self.add('most_fields 타입',m.get('type')=='most_fields')
            self.add('title boost 3','title^3' in m.get('fields',[]) or 'title^3.0' in m.get('fields',[]))
            self.add('정렬 우선순위',sort_spec(body)==sort_spec(ref.body))
    def check_state(self):
        k=self.t['check']
        if k.startswith('f_'):
            from verify_f import state_check
            return state_check(self)
        if k.startswith('e_'):
            from verify_e import state_check
            return state_check(self)
        if k in ('article_enrich','article_stop','default_pipeline'):
            from verify_d import state_check
            return state_check(self)
        if k in ('stop_food','stop_movies'):
            original,dest,field,other,word=('food-ingredients','task2','ingredients','weight','for') if k=='stop_food' else ('movie_data','task3','title','movie_id','to')
            p=self.props(dest);orig=self.fixture(original)
            self.add('원본 문서 전체 보존',self.docs(dest)==orig)
            self.add(f'{field}: text only',p.get(field,{}).get('type')=='text' and not p.get(field,{}).get('fields'))
            self.add(f'{other}: keyword only',p.get(other,{}).get('type')=='keyword' and not p.get(other,{}).get('fields'))
            old=FIXTURES[(self.c,original)]['mappings']['properties']
            self.add('나머지 mapping 동일',all(p.get(key)==v for key,v in old.items() if key not in (field,other)))
            result=self.get(f'/{dest}/_search',body={'size':0,'query':{'match':{field:word}}})
            self.add('불용어 단독 검색 0건',result['hits']['total']['value']==0)
        elif k=='address':
            docs=self.docs('inspections');orig=self.fixture('inspections')
            self.add('전체 문서 유지',set(docs)==set(orig))
            self.add('주소 문자열과 필드 보존',bool(docs) and all(d.get('complete_address')==' '.join(str(orig[i][f]) for f in ('street_number','street_name','neighborhood','zipcode')) and {key:val for key,val in d.items() if key!='complete_address'}==orig[i] for i,d in docs.items() if i in orig))
            routes=[h.get('request',{}).get('path','') for h in self.history]+[r.path for r in parse_console(self.code)]
            self.add('pipeline으로 기존 문서 업데이트',any('inspections/_update_by_query' in p and 'pipeline=' in p for p in routes),'실행 기록/현재 스크립트에서 pipeline 적용을 확인합니다.')
        elif k=='ilm':
            template=self.get('/_index_template/task1')['index_templates'][0]['index_template']
            self.add('템플릿 패턴 / data_stream','mylogs-*-*' in template.get('index_patterns',[]) and 'data_stream' in template)
            settings=flatten(template.get('template',{}).get('settings',{}))
            policy=settings.get('index.lifecycle.name');self.add('ILM 정책 연결',bool(policy))
            if policy:
                phases=self.get('/_ilm/policy/'+policy)[policy]['policy']['phases']
                self.add('Hot: rollover 5분',duration(phases.get('hot',{}).get('actions',{}).get('rollover',{}).get('max_age'))==300)
                self.add('Warm: rollover 직후','warm' in phases and duration(phases['warm'].get('min_age','0ms'))==0)
                self.add('Cold: rollover 후 3분',duration(phases.get('cold',{}).get('min_age'))==180)
                self.add('Delete: rollover 후 6분',duration(phases.get('delete',{}).get('min_age'))==360 and 'delete' in phases.get('delete',{}).get('actions',{}))
            stream=self.get('/_data_stream/mylogs-system.env-prod');self.add('데이터 스트림 생성',bool(stream.get('data_streams')))
        elif k=='snapshot':
            repo=self.get('/_snapshot/task9')['task9'];snap=self.get('/_snapshot/task9/city_population_1')['snapshots'][0]
            self.add('공유 파일 시스템 / 경로',repo.get('type')=='fs' and repo.get('settings',{}).get('location')=='/mnt/elastic-snapshots')
            self.add('city_population만 포함',set(snap.get('indices',[]))=={'city_population'})
            self.add('스냅샷 성공',snap.get('state')=='SUCCESS',str(snap.get('state')))
        elif k in ('enrich','legacy_enrich'):
            source,dest=('earthquakes','task2') if k=='enrich' else ('blogs','legacy-enriched')
            orig=self.fixture(source);docs=self.docs(dest)
            self.add('원본 문서 수 / ID 유지',set(orig)==set(docs))
            if k=='enrich':
                ref={d['MagnitudeType']:d['MagnitudeTypeDesc'] for d in self.fixture('magnitude_type').values()}
                self.add('최상위 설명 필드 보강',all(docs.get(i,{}).get('MagnitudeTypeDesc')==ref[d['MagnitudeType']] for i,d in orig.items()))
                self.add('기존 필드 유지 / 임시 객체 제거',all(docs.get(i)==dict(d,MagnitudeTypeDesc=ref[d['MagnitudeType']]) for i,d in orig.items()))
            else:
                ref={d['uid']:d['title'] for d in self.fixture('categories').values()};expected={}
                for i,d in orig.items():
                    x=copy.deepcopy(d);cat=x.pop('category',None)
                    if cat in ref:x['category_title']=ref[cat]
                    expected[i]=x
                self.add('최상위 category_title 및 없는 category 처리',docs==expected)
        elif k=='ccr':
            info=self.get('/task4/_ccr/info')['follower_indices'][0]
            self.add('leader / remote alias',info.get('leader_index')=='city_populations' and info.get('remote_cluster')=='cluster2')
            self.add('follower active',info.get('status')=='active',str(info.get('status')))
            self.add('문서 동기화',self.docs('task4')==self.docs('city_populations','cluster2'),'초기 복제 중이라면 잠시 후 다시 검증하세요.')
        elif k=='slm':
            item=self.get('/_slm/policy/task6')['task6']['policy'];repo=self.get('/_snapshot/'+item['repository'])[item['repository']]
            self.add('매시간 정각',item.get('schedule') in ('0 0 * * * ?','0 0 0/1 * * ?','0 0 * * * ? *'))
            self.add('이름에 prefix와 날짜 수학',item.get('name','').startswith('<hourly-snapshots-') and '{now' in item.get('name',''))
            indices=item.get('config',{}).get('indices',[]);indices=indices.split(',') if isinstance(indices,str) else indices
            self.add('listings2만 대상',indices==['listings2'])
            self.add('repository 경로',repo.get('type')=='fs' and repo.get('settings',{}).get('location')=='/mnt/elastic-snapshots')
        elif k in ('metrics','d_metrics'):
            template=self.get('/_index_template/'+('task5' if k=='d_metrics' else 'task8'))['index_templates'][0]['index_template'];s=flatten(template.get('template',{}).get('settings',{}));p=template.get('template',{}).get('mappings',{}).get('properties',{})
            self.add('data stream 템플릿 / 패턴','data_stream' in template and 'mymetrics-*-*' in template.get('index_patterns',[]))
            self.add('primary 1 / replica 2',str(s.get('index.number_of_shards',s.get('number_of_shards')))=='1' and str(s.get('index.number_of_replicas',s.get('number_of_replicas')))=='2')
            self.add('timestamp/host/tags 매핑',p.get('@timestamp',{}).get('type')=='date' and p.get('host',{}).get('properties',{}).get('name',{}).get('type')=='keyword' and p.get('tags',{}).get('type')=='keyword')
            e=p.get('error',{}).get('properties',{}).get('message',{});self.add('error.message fingerprint',e.get('type')=='text' and e.get('analyzer')=='fingerprint')
            stream=self.get('/_data_stream/mymetrics-system-prod');self.add('실제 데이터 스트림',bool(stream.get('data_streams')))
        elif k=='allocation':
            for name,nodes in [('legacy-index1',{'node2','node3'}),('legacy-index2',{'node1'})]:
                shards=self.get('/_cat/shards/'+name+'?format=json');self.add(name+' 노드 배치',bool(shards) and all(x.get('state')=='STARTED' and x.get('node') in nodes for x in shards))
                self.add(name+' 문서 보존',self.docs(name)==self.fixture(name))
                raw=self.get('/'+name+'/_settings')[name]['settings']['index'];expected=FIXTURES[(self.c,name)]['settings'];self.add(name+' shard/replica 유지',str(raw.get('number_of_shards'))==str(expected['number_of_shards']) and str(raw.get('number_of_replicas'))==str(expected['number_of_replicas']))
            self.add('cluster health green',self.get('/_cluster/health').get('status')=='green')
        elif k=='dynamic':
            p=self.props('legacy-dynamic');m=self.get('/legacy-dynamic/_mapping')['legacy-dynamic']['mappings'];self.add('동적 템플릿 존재',bool(m.get('dynamic_templates')))
            self.add('문자열 keyword only',all(p.get(f,{}).get('type')=='keyword' and not p.get(f,{}).get('fields') for f in ('category_id','label')))
            self.add('t_count long',p.get('t_count',{}).get('type')=='long')
        elif k=='normalization':
            self.add('원문 전체 보존',self.docs('legacy-normalized')==self.fixture('legacy-drinks'))
            for word in ('yoo-hoo','yoohoo'):
                r=self.get('/legacy-normalized/_search',body={'query':{'match':{'name':word}}});self.add(word+' 검색 2건',r.get('hits',{}).get('total',{}).get('value')==2)
        elif k=='nested':
            self.add('authors nested 매핑',self.props('legacy-nested').get('authors',{}).get('type')=='nested')
            self.add('문서 보존',self.docs('legacy-nested')==self.fixture('blogs'))
            q=self.submitted();b=copy.deepcopy(q.body or {});b.update(size=10000)
            self.add('nested query 사용',any(x.get('nested',{}).get('path')=='authors' for x in walk(b)))
            result=self.run_search(q,b);ids={h['_id'] for h in result.get('hits',{}).get('hits',[])}
            expected={i for i,d in self.fixture('blogs').items() if any(a['first_name']=='david' and 'engineer' in a['job_title'] for a in d['authors'])}
            self.add('동일 객체 내 두 조건',ids==expected)
        elif k=='search_template':
            t=self.get('/_scripts/legacy-search-template');self.add('저장된 Mustache 템플릿',t.get('script',{}).get('lang')=='mustache')
            r=self.es.require(self.c,'POST','/_render/template',{'id':'legacy-search-template','params':{'start_date':'2024-12-01'}})
            v=json.dumps(r.get('template_output',{}));self.add('기본 end_date now','now' in v and '2024-12-01' in v and '{{' not in v)
            result=self.es.require(self.c,'POST','/blogs/_search/template',{'id':'legacy-search-template','params':{'start_date':'2024-12-01'}})
            self.add('템플릿 검색 성공',not result.get('_shards',{}).get('failed'))
        elif k=='language':
            self.es.require(self.c,'POST','/legacy-language/_refresh')
            p=self.props('legacy-language').get('content',{});fields=p.get('fields',{})
            self.add('content text/standard',p.get('type')=='text' and p.get('analyzer','standard')=='standard')
            for field,analyzer in [('eng','english'),('nld','dutch')]:self.add('content.'+field,fields.get(field,{}).get('type')=='text' and fields.get(field,{}).get('analyzer')==analyzer)
            self.add('문서 색인',self.get('/legacy-language/_count').get('count',0)>0)
        elif k=='rbac':
            role=self.get('/_security/role/legacy-reader-role')['legacy-reader-role'];user=self.get('/_security/user/legacy-student')['legacy-student']
            self.add('cluster monitor',set(role.get('cluster',[]))=={'monitor'})
            self.add('일반 인덱스 read',any(x.get('names')==['*'] and x.get('privileges')==['read'] for x in role.get('indices',[])))
            self.add('legacy-secure all',any(x.get('names')==['legacy-secure'] and x.get('privileges')==['all'] for x in role.get('indices',[])))
            self.add('사용자 역할/이름',user.get('roles')==['legacy-reader-role'] and user.get('full_name')=='Practice Student')
            self.add('지정 비밀번호 인증',self.es.get(self.c,'/_security/_authenticate',auth=('legacy-student','StudyOnly2026!'))['status']==200)
        elif k=='airlines':
            q=[r for r in parse_console(self.t['solution']) if '_search' in r.path][-1];r=self.run_search(q)
            expected=[b['key'] for b in r['aggregations']['airlines']['buckets']]
            answer=[s for s in re.split(r'[,\s/]+',self.answer.strip().upper()) if s]
            self.add('항공사 코드 2개',len(answer)==2 and set(answer)==set(expected),'쿼리가 아니라 별도 텍스트 답안으로 제출합니다.')
        else:raise RuntimeError('이 문제의 자동 검증은 제공되지 않습니다. 요구조건과 해설을 직접 비교하세요.')
    def run(self):
        self.add('요청을 보낸 클러스터',self.c==self.t['cluster'],f'필요: {self.t["cluster"]} / 선택: {self.c}')
        try:
            if self.t['kind']=='query':self.check_query()
            else:self.check_state()
        except Exception as e:
            self.add('검증 실행',False,str(e))
        passed=sum(x['ok'] for x in self.checks)
        return {'task_id':self.t['id'],'checks':self.checks,'passed':passed,'total':len(self.checks),'complete':passed==len(self.checks),
                'notice':'실습 데이터에 대한 참고 검증입니다. 공식 채점기가 아니며, 동일한 결과를 내는 다른 구현은 일부 구조 검사에서 수동 확인이 필요할 수 있습니다.'}
