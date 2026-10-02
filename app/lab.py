"""Initialize only the dedicated disposable lab. Never seed arbitrary clusters."""
from __future__ import annotations
import json
import os
from pathlib import Path
import threading
import time
from elastic import Elastic

ROOT=Path(__file__).resolve().parents[1]
FIX=json.loads((ROOT/'data/fixtures.json').read_text(encoding='utf-8'))['indices']
E_FIX_PATH=ROOT/'data/fixtures-e.json'
E_FIX=json.loads(E_FIX_PATH.read_text(encoding='utf-8'))['indices'] if E_FIX_PATH.exists() else []
F_FIX_PATH=ROOT/'data/fixtures-f.json'
F_FIX=json.loads(F_FIX_PATH.read_text(encoding='utf-8'))['indices'] if F_FIX_PATH.exists() else []

def fixtures_for_set(set_id):
    if set_id=='F':return FIX+F_FIX
    if set_id=='E':
        overrides={(x['cluster'],x['index']):x for x in E_FIX}
        return [overrides.get((x['cluster'],x['index']),x) for x in FIX]
    return FIX
MARKER='ece-lab-control'
MARKER_VALUE='elastic-exam-lab-v2-disposable'

class Lab:
    def __init__(self,client:Elastic,state_dir:Path):
        self.es=client;self.state_dir=state_dir;self.lock=threading.RLock()
        self.info={'phase':'starting','message':'Elasticsearch 시작 대기 중','progress':0,'error':None,'active_set':'D','generation':0}
        self.state_dir.mkdir(parents=True,exist_ok=True)
        self.state_file=self.state_dir/'lab.json'
        if self.state_file.exists():
            try:
                saved=json.loads(self.state_file.read_text());self.info.update({k:saved[k] for k in ['active_set','generation'] if k in saved})
            except ValueError:pass
    def save(self):
        temp=self.state_file.with_suffix('.tmp');temp.write_text(json.dumps(self.info,ensure_ascii=False));temp.replace(self.state_file)
    def snapshot(self):
        with self.lock:return dict(self.info)
    def update(self,**kwargs):
        with self.lock:self.info.update(kwargs)
    def owned(self,cluster,allow_empty=False):
        root=self.es.require(cluster,'GET','/')
        if root.get('cluster_name')!=self.es.expected[cluster]:
            raise RuntimeError(f'안전장치: {cluster}의 cluster_name이 전용 실습 이름 {self.es.expected[cluster]}가 아닙니다. 초기화하지 않습니다.')
        marker=self.es.get(cluster,f'/{MARKER}/_doc/identity')
        if marker['status']==200:
            if marker['body'].get('_source',{}).get('owner')!=MARKER_VALUE:raise RuntimeError('실습 소유권 마커가 일치하지 않습니다.')
            return True
        if not allow_empty:raise RuntimeError('실습 소유권 마커가 없어 파괴적인 초기화를 중단했습니다.')
        indices=self.es.require(cluster,'GET','/_cat/indices?format=json&expand_wildcards=all')
        existing=[x['index'] for x in indices if not x['index'].startswith('.')]
        if existing:raise RuntimeError('소유권 마커 없이 기존 인덱스가 발견되어 초기 적재를 중단합니다: '+', '.join(existing))
        self.es.require(cluster,'PUT','/'+MARKER,{'settings':{'number_of_replicas':0},'mappings':{'properties':{'owner':{'type':'keyword'}}}})
        self.es.require(cluster,'PUT',f'/{MARKER}/_doc/identity?refresh=true',{'owner':MARKER_VALUE})
        return False
    def bootstrap(self):
        try:
            for attempt in range(240):
                if all(self.es.get(c,'/',timeout=3)['status']==200 for c in ('cluster1','cluster2')):break
                self.update(message=f'Elasticsearch 기동 및 인증 대기 중 ({attempt*5}초)',progress=1)
                time.sleep(5)
            else:raise RuntimeError('20분 동안 Elasticsearch에 연결하지 못했습니다. docker compose logs es01 server4를 확인하세요.')
            for c, nodes in (('cluster1', 3), ('cluster2', 1)):
                health = self.es.require(c, 'GET', f'/_cluster/health?wait_for_nodes={nodes}&timeout=120s', timeout=130)
                if health.get('timed_out') or health.get('number_of_nodes', 0) < nodes:
                    raise RuntimeError(f'{c}: 필요한 {nodes}개 노드가 준비되지 않았습니다.')
            existing=[self.owned(c,allow_empty=True) for c in ('cluster1','cluster2')]
            # The two native Kibana instances authenticate with the built-in service user.
            for c in ('cluster1','cluster2'):
                self.es.require(c, 'POST', '/_security/user/kibana_system/_password',
                                {'password': os.getenv('KIBANA_PASSWORD', 'KibanaLab2026')})
            markers=[self.es.get(c,f'/{MARKER}/_doc/seed')['body'] for c in ('cluster1','cluster2')]
            if all(existing) and all(isinstance(x,dict) and x.get('found') and x.get('_source',{}).get('version')==2 for x in markers):
                self.ensure_metrics_component()
                self.update(phase='ready',message='저장된 실습 환경을 이어서 사용합니다.',progress=100,error=None);self.save();return
            self.reset(self.info['active_set'],initial=True)
        except Exception as e:self.update(phase='error',message='초기 적재 실패',error=str(e))
    def cleanup(self,cluster):
        self.owned(cluster)
        es=self.es
        # F's managed classic Streams definitions must be reset together with
        # their data. Bootstrap never invokes this destructive reset path.
        for fixture in F_FIX:
            if fixture['cluster']!=cluster or not fixture.get('data_stream'):continue
            path='/api/streams/'+fixture['index']
            stream=es.kibana(cluster,'GET',path)
            if stream['status']==200:es.kibana_require(cluster,'DELETE',path)
            elif stream['status']!=404:
                raise RuntimeError(f'F Streams 초기화 확인 실패: {path} HTTP {stream["status"]}')
        # Stop policy-driven changes before deleting disposable user resources.
        es.call(cluster,'POST','/_ilm/stop');es.call(cluster,'POST','/_slm/stop')
        for action in ('*reindex','*byquery'):
            es.call(cluster,'POST',f'/_tasks/_cancel?actions={action}')
        active=es.get(cluster,'/_tasks?actions=*reindex,*byquery&detailed=true')['body']
        if isinstance(active,dict) and any(n.get('tasks') for n in active.get('nodes',{}).values()):
            time.sleep(2)
            active=es.get(cluster,'/_tasks?actions=*reindex,*byquery')['body']
            if isinstance(active,dict) and any(n.get('tasks') for n in active.get('nodes',{}).values()):
                raise RuntimeError('실행 중인 데이터 작업이 아직 종료되지 않았습니다. 종료 후 초기화를 다시 누르세요.')
        auto=es.get(cluster,'/_ccr/auto_follow')['body']
        if isinstance(auto,dict):
            for x in auto.get('patterns',[]):es.require(cluster,'DELETE','/_ccr/auto_follow/'+x['name'])
        # Stop snapshot policies before indexes, after workers stop. Repository
        # snapshots must be removed after mounted searchable indexes are gone.
        slm=es.get(cluster,'/_slm/policy')['body']
        if isinstance(slm,dict) and 'error' not in slm:
            for name in slm:es.require(cluster,'DELETE','/_slm/policy/'+name)
        user_indices=es.require(cluster,'GET','/_cat/indices?format=json&expand_wildcards=all')
        for item in user_indices:
            name=item['index']
            if name.startswith('.') or name==MARKER:continue
            es.call(cluster,'PUT',f'/{name}/_settings',{'index.default_pipeline':'_none','index.final_pipeline':'_none'})
        # Enrich policies cannot be removed while a pipeline references them.
        pipelines=es.get(cluster,'/_ingest/pipeline')['body']
        if isinstance(pipelines,dict) and 'error' not in pipelines:
            for name in pipelines:
                if not name.startswith('.') and '@' not in name:
                    es.require(cluster,'DELETE','/_ingest/pipeline/'+name)
        policies=es.get(cluster,'/_enrich/policy')['body']
        if isinstance(policies,dict):
            for policy in policies.get('policies',[]):
                name=next(iter(policy.get('config',{}).values()),{}).get('name')
                if name:es.require(cluster,'DELETE','/_enrich/policy/'+name)
        streams=es.get(cluster,'/_data_stream')['body']
        if isinstance(streams,dict):
            for stream in streams.get('data_streams',[]):es.require(cluster,'DELETE','/_data_stream/'+stream['name'])
        indices=es.require(cluster,'GET','/_cat/indices?format=json&expand_wildcards=all')
        for x in indices:
            name=x['index']
            if name.startswith('.') or name==MARKER:continue
            # pause is only relevant for followers; an ordinary index may return 400/404.
            es.call(cluster,'POST',f'/{name}/_ccr/pause_follow')
            es.require(cluster,'DELETE','/'+name)
        repos=es.get(cluster,'/_snapshot')['body']
        if isinstance(repos,dict) and 'error' not in repos:
            for name in repos:
                shots=es.get(cluster,f'/_snapshot/{name}/_all')['body']
                if isinstance(shots,dict) and 'snapshots' in shots:
                    for shot in shots['snapshots']:es.require(cluster,'DELETE',f'/_snapshot/{name}/{shot["snapshot"]}',timeout=120)
                es.require(cluster,'DELETE','/_snapshot/'+name)
        for endpoint,array,key in [('_index_template','index_templates','name'),('_component_template','component_templates','name')]:
            data=es.get(cluster,'/'+endpoint)['body']
            if isinstance(data,dict):
                for x in data.get(array,[]):
                    name=x[key]
                    # Built-in/internal templates are not modified.
                    if name.startswith('.') or '@' in name or x.get('index_template',x.get('component_template',{})).get('_meta',{}).get('managed'):continue
                    es.require(cluster,'DELETE',f'/{endpoint}/{name}')
        for endpoint in ('_ilm/policy',):
            data=es.get(cluster,'/'+endpoint)['body']
            if isinstance(data,dict) and 'error' not in data:
                for name in data:
                    if name.startswith('.') or '@' in name:continue
                    es.call(cluster,'DELETE',f'/{endpoint}/{name}')
        es.call(cluster,'DELETE','/_scripts/legacy-search-template')
        es.call(cluster,'DELETE','/_security/user/legacy-student')
        es.call(cluster,'DELETE','/_security/role/legacy-reader-role')
        if cluster=='cluster1':
            es.call(cluster,'DELETE','/_security/user/task1')
            es.call(cluster,'DELETE','/_security/role/task1_role')
    def ensure_metrics_component(self):
        """Supply the shared practice prerequisite without replacing user changes."""
        path='/_component_template/metrics-mappings'
        existing=self.es.get('cluster1',path)
        if existing['status']==200:return False
        if existing['status']!=404:
            raise RuntimeError(f'metrics-mappings 준비 상태 확인 실패: HTTP {existing["status"]}')
        result=self.es.call('cluster1','PUT',path+'?create=true',{
            'template':{'mappings':{'properties':{'@timestamp':{'type':'date'}}}},
            '_meta':{'description':'ECE Practice Exam synthetic prerequisite'}
        })
        if result['status']>=400:
            # A template may have been created after the GET. Never overwrite it.
            if result['status'] in (400,409) and self.es.get('cluster1',path)['status']==200:
                return False
            raise RuntimeError(f'metrics-mappings 준비 실패: HTTP {result["status"]}')
        return True
    def prepare_e(self):
        """Prepare prerequisites only when the user explicitly starts set E."""
        self.update(progress=94,message='E 세트의 component template과 검색 가능한 스냅샷 준비')
        self.ensure_metrics_component()
        repository='/_snapshot/snap-repo'
        snapshot=repository+'/moreblogs_snapshot'
        self.es.require('cluster1','PUT',repository,{
            'type':'fs','settings':{'location':'/mnt/elastic-snapshots/ece-practice-search'}
        })
        previous=self.es.get('cluster1',snapshot)
        if previous['status']==200:
            self.es.require('cluster1','DELETE',snapshot,timeout=120)
        elif previous['status']!=404:
            raise RuntimeError(f'E 스냅샷 확인 실패: HTTP {previous["status"]}')
        saved=self.es.require('cluster1','PUT',snapshot+'?wait_for_completion=true',{
            'indices':'moreblogs','include_global_state':False
        },timeout=240)
        if saved.get('snapshot',{}).get('state')!='SUCCESS':
            raise RuntimeError('E moreblogs 스냅샷이 정상 완료되지 않았습니다: '+json.dumps(saved,ensure_ascii=False)[:800])
        # Leave files on the shared filesystem, but require the learner to
        # register snap-repo and mount the index before searching it.
        self.es.require('cluster1','DELETE',repository)
        self.es.require('cluster1','DELETE','/moreblogs')
    def reset(self,set_id='D',initial=False):
        try:
            fixtures=fixtures_for_set(set_id)
            if set_id=='E':
                if not E_FIX:raise RuntimeError('E 세트 데이터가 없습니다. data/rebuild.py를 실행해 fixtures-e.json을 생성하세요.')
            if set_id=='F' and not F_FIX:raise RuntimeError('F 세트 데이터가 없습니다. data/rebuild.py를 실행해 fixtures-f.json을 생성하세요.')
            self.update(phase='seeding',message='실습 전용 환경을 확인합니다.',progress=2,error=None)
            if not initial:
                for c in ('cluster1','cluster2'):self.owned(c)
                for c in ('cluster1','cluster2'):self.cleanup(c)
            for c in ('cluster1','cluster2'):
                self.es.require(c,'PUT','/_cluster/settings',{'persistent':{'indices.lifecycle.poll_interval':'5s','cluster.routing.allocation.enable':'all','cluster.routing.allocation.exclude._name':None,'cluster.routing.allocation.include._name':None,'cluster.routing.allocation.require._name':None,'cluster.routing.allocation.awareness.attributes':None}})
            for j,item in enumerate(fixtures):
                c=item['cluster'];name=item['index'];self.update(progress=8+int(77*j/len(fixtures)),message=f'{c} / {name}: {len(item["documents"])}건 적재')
                exists=self.es.call(c,'HEAD','/'+name)['status']==200
                if exists:
                    if not initial:raise RuntimeError(f'초기화 후에도 {name}가 남아 있습니다.')
                    self.es.require(c,'DELETE','/'+name)
                if item.get('data_stream'):
                    self.es.require(c,'PUT','/_index_template/'+name,{
                        'index_patterns':[name],'data_stream':{},'priority':600,
                        'template':{'settings':item['settings'],'mappings':item['mappings']}})
                    self.es.require(c,'PUT','/_data_stream/'+name)
                else:self.es.require(c,'PUT','/'+name,{'settings':item['settings'],'mappings':item['mappings']})
                lines=[]
                for doc in item['documents']:
                    operation='create' if item.get('data_stream') else 'index'
                    lines.extend([json.dumps({operation:{'_id':doc['_id']}},ensure_ascii=False),json.dumps(doc['_source'],ensure_ascii=False)])
                r=self.es.require(c,'POST',f'/{name}/_bulk?refresh=true',raw='\n'.join(lines)+'\n',content_type='application/x-ndjson') if lines else {}
                if r.get('errors'):
                    failures=[x for x in r.get('items',[]) if next(iter(x.values())).get('error')]
                    raise RuntimeError(f'{name}: bulk 실패 '+json.dumps(failures[:2],ensure_ascii=False))
            self.es.require('cluster1','POST','/_aliases',{'actions':[{'add':{'index':'regions','alias':'region'}}]})
            baseline=self.es.require('cluster1','GET','/ingest-logs/_settings')['ingest-logs']['settings']['index']['uuid']
            self.es.require('cluster1','PUT',f'/{MARKER}/_doc/baselines?refresh=true',{'ingest_logs_uuid':baseline})
            self.update(progress=92,message='Remote Cluster 연결 및 데이터 개수 검증')
            self.es.require('cluster1','PUT','/_cluster/settings',{'persistent':{'cluster.remote.cluster2.mode':'sniff','cluster.remote.cluster2.seeds':[os.getenv('REMOTE_SEED','server4:9304')],'cluster.remote.cluster2.node_connections':1,'cluster.remote.cluster2.skip_unavailable':False}})
            remote=self.es.require('cluster1','GET','/_remote/info')
            if not remote.get('cluster2',{}).get('connected'):
                raise RuntimeError('cluster2 원격 연결에 실패했습니다. server4의 transport TLS 및 9304 포트를 확인하세요.')
            # All reference fixtures must be present; do not silently mark a partial seed ready.
            for item in fixtures:
                count=self.es.require(item['cluster'],'GET',f'/{item["index"]}/_count')['count']
                if count!=len(item['documents']):raise RuntimeError(f'{item["index"]} count 불일치: {count}')
            self.ensure_metrics_component()
            if set_id=='E':self.prepare_e()
            for c in ('cluster1','cluster2'):
                self.es.require(c,'POST','/_ilm/start');self.es.require(c,'POST','/_slm/start')
                self.es.require(c,'PUT',f'/{MARKER}/_doc/seed?refresh=true',{'version':2,'set':set_id,'synthetic':True})
            ready_fixtures=[x for x in fixtures if not (set_id=='E' and x['cluster']=='cluster1' and x['index']=='moreblogs')]
            message=f'{len(ready_fixtures)}개 인덱스 · 합성 문서 {sum(len(x["documents"]) for x in ready_fixtures):,}건 준비 완료'
            if set_id=='E':message+=' · moreblogs는 스냅샷으로 제공'
            self.update(phase='ready',message=message,progress=100,error=None,active_set=set_id,generation=self.info['generation']+1);self.save()
        except Exception as e:self.update(phase='error',message='초기화/적재 실패',error=str(e));self.save()
