#!/usr/bin/env python3
"""Local-only exam UI + real Elasticsearch reverse proxy (Python stdlib)."""
from __future__ import annotations
import json,os,re,secrets,sqlite3,threading,time,mimetypes
from pathlib import Path
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,unquote
from console import parse_console,ConsoleError
from elastic import Elastic
from lab import Lab,FIX,ROOT,fixtures_for_set
from verify import Verify
import kibana_proxy

STATE=Path(os.getenv('LAB_STATE_DIR',str(ROOT/'state')))
STATE.mkdir(parents=True,exist_ok=True)
CATALOG=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
TASKS={x['id']:x for x in CATALOG['tasks']}
CLIENT=Elastic();LAB=Lab(CLIENT,STATE)
DB=STATE/'history.sqlite3'
DB_LOCK=threading.Lock()

@contextmanager
def database():
    with closing(sqlite3.connect(DB)) as con:
        with con:
            yield con

def db_init():
    with database() as con:
        con.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, session TEXT, task_id TEXT, generation INTEGER, cluster TEXT, timestamp REAL, request TEXT, status INTEGER, elapsed REAL)')
        con.execute('CREATE INDEX IF NOT EXISTS history_lookup ON events(session,task_id,generation)')

def log_event(session,task_id,cluster,request,response):
    with DB_LOCK,database() as con:
        con.execute('INSERT INTO events(session,task_id,generation,cluster,timestamp,request,status,elapsed) VALUES(?,?,?,?,?,?,?,?)',(session,task_id,LAB.info['generation'],cluster,time.time(),json.dumps(request,ensure_ascii=False),response['status'],response['elapsed_ms']))

def history(session,task_id):
    with database() as con:
        rows=con.execute('SELECT request,status,cluster,timestamp,elapsed FROM events WHERE session=? AND task_id=? AND generation=? ORDER BY id DESC LIMIT 100',(session,task_id,LAB.info['generation'])).fetchall()
    return [{'request':json.loads(q),'status':status,'cluster':cluster,'timestamp':t,'elapsed_ms':elapsed} for q,status,cluster,t,elapsed in reversed(rows)]

def status():
    clusters={}
    for c in ('cluster1','cluster2'):
        r=CLIENT.get(c,'/_cluster/health',timeout=2)
        if r['status']==200:
            license=CLIENT.get(c,'/_license',timeout=2)
            l=license['body'].get('license',{}) if isinstance(license['body'],dict) else {}
            clusters[c]={'connected':True,'health':r['body'].get('status'),'nodes':r['body'].get('number_of_nodes'),
                         'name':r['body'].get('cluster_name'),'license':l.get('type'),'license_status':l.get('status'),'expiry_date':l.get('expiry_date')}
        else:clusters[c]={'connected':False,'error':r['body']}
    fixtures=fixtures_for_set(LAB.info['active_set'])
    return {'kibana':kibana_proxy.health(CLIENT.password),'lab':LAB.snapshot(),'clusters':clusters,'engine_version':CATALOG['engine_version'],'fixture_indices':len(fixtures),'fixture_documents':sum(len(x['documents']) for x in fixtures)}

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    server_version='ElasticExamLab/2.0'
    def log_message(self,fmt,*args):
        print(f'[{time.strftime("%H:%M:%S")}] {fmt % args}',flush=True)
    def send(self,status,body,content_type='application/json; charset=utf-8'):
        if isinstance(body,(dict,list)):body=json.dumps(body,ensure_ascii=False).encode('utf-8')
        elif isinstance(body,str):body=body.encode('utf-8')
        self.send_response(status)
        if status>=400:
            self.send_header('Connection','close');self.close_connection=True
        self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
        self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def native(self):
        cluster=kibana_proxy.identify(self.path)
        if not cluster:return False
        def guard(captured):
            q=captured['request'];path=q['path'].split('?')[0]
            if 'ece-lab-control' in path and q['method'] not in ('GET','HEAD'):
                return '실습 소유권 및 인덱스 UUID 기준 정보는 수정할 수 없습니다.'
            if q['method']=='DELETE' and path.strip('/') in ('','*','_all'):
                return '전체 인덱스 삭제는 보호됩니다. 특정 실습 인덱스나 환경 초기화를 사용하세요.'
        def observe(captured,c,response):
            task=TASKS.get(captured['task_id'])
            if task and task['set']==LAB.info['active_set']:
                log_event(captured['session'],captured['task_id'],c,captured['request'],response)
        kibana_proxy.proxy(self,cluster,observe,guard)
        return True
    def do_HEAD(self):
        if self.native():return
        self.send(405,{'error':'Use GET for lab APIs.'})
    def do_PUT(self):
        if self.native():return
        self.send(405,{'error':'Unsupported lab method.'})
    do_DELETE=do_PUT
    do_PATCH=do_PUT
    def do_OPTIONS(self):
        if self.native():return
        self.send(405,{'error':'Cross-origin access is not supported.'})
    def do_GET(self):
        if self.native():return
        path=unquote(urlsplit(self.path).path)
        if path=='/api/health':return self.send(200,{'ok':True,'phase':LAB.info['phase']})
        if path=='/api/ready':return self.send(200 if LAB.info['phase']=='ready' else 503,LAB.snapshot())
        if path=='/api/catalog':
            cat={k:v for k,v in CATALOG.items() if k!='tasks'}
            cat['tasks']=[{k:v for k,v in t.items() if k not in ('solution','answer')} for t in CATALOG['tasks']]
            return self.send(200,cat)
        if path=='/api/status':return self.send(200,status())
        if path=='/api/datasets':return self.send(200,{'synthetic':True,'indices':[{'cluster':x['cluster'],'index':x['index'],'count':len(x['documents']),'mappings':x['mappings']} for x in fixtures_for_set(LAB.info['active_set'])]})
        if path.startswith('/api/solution/'):
            t=TASKS.get(path.rsplit('/',1)[-1])
            return self.send(200,{'solution':t['solution'],'answer':t['answer'],'hint':t['hint'],'notes':t['notes']}) if t else self.send(404,{'error':'문항을 찾을 수 없습니다.'})
        base=ROOT/'sources' if path.startswith('/sources/') else ROOT/'web'
        rel=path[len('/sources/'):] if path.startswith('/sources/') else path.lstrip('/') or 'index.html'
        target=(base/rel).resolve()
        if not target.is_relative_to(base.resolve()) or not target.is_file():return self.send(404,'Not found','text/plain; charset=utf-8')
        mime=mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if mime.startswith('text/') or mime in ('application/javascript',):mime+='; charset=utf-8'
        self.send(200,target.read_bytes(),mime)
    def do_POST(self):
        if self.native():return
        # Local app: no cross-origin POST, no simple HTML form submissions, no arbitrary targets.
        origin=self.headers.get('Origin')
        expected='http://'+self.headers.get('Host','')
        if self.headers.get('X-Lab-Request')!='1' or (origin and origin not in (expected,expected.replace('http:','https:'))):
            return self.send(403,{'error':'동일 출처의 실습 화면에서 요청하세요.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<0 or size>2_100_000:return self.send(413,{'error':'요청 크기 제한: 2 MB'})
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError('JSON 객체가 필요합니다.')
            path=urlsplit(self.path).path
            if path=='/api/reset':
                if data.get('confirmation')!='RESET LAB':return self.send(400,{'error':'초기화 확인 문구가 필요합니다.'})
                if LAB.info['phase'] in ('starting','seeding'):return self.send(409,{'error':'이미 초기화 중입니다.'})
                set_id=data.get('set','A')
                if set_id not in {s['id'] for s in CATALOG['sets']}:raise ValueError('잘못된 세트입니다.')
                LAB.update(phase='seeding',message='초기화 시작',progress=0)
                threading.Thread(target=LAB.reset,args=(set_id,),daemon=True).start()
                return self.send(202,{'started':True,'set':set_id})
            if LAB.info['phase']!='ready':return self.send(409,{'error':'실습 데이터가 아직 준비되지 않았습니다. 상단 상태 또는 Docker 로그를 확인하세요.','lab':LAB.snapshot()})
            cluster=data.get('cluster','cluster1')
            if cluster not in ('cluster1','cluster2'):raise ValueError('cluster1 또는 cluster2를 선택하세요.')
            session=str(data.get('session','local'))[:128];task_id=data.get('task_id')
            if task_id not in TASKS:raise ValueError('잘못된 문항 ID입니다.')
            task=TASKS[task_id]
            if task['set']!=LAB.info['active_set']:return self.send(409,{'error':'선택한 세트와 현재 데이터 세트가 다릅니다. 세트 변경/환경 초기화를 완료하세요.'})
            if path=='/api/execute':
                requests=parse_console(data.get('code',''));results=[]
                for r in requests:
                    if 'ece-lab-control' in r.path and r.method not in ('GET','HEAD'):
                        response={'status':403,'body':{'error':'실습 소유권 마커는 수정할 수 없습니다.'},'elapsed_ms':0,'warnings':[]}
                    elif r.method=='DELETE' and r.path.split('?')[0].strip('/') in ('*','_all',''):
                        response={'status':403,'body':{'error':'전체 인덱스 와일드카드 삭제는 보호됩니다. 특정 인덱스 이름 또는 환경 초기화를 사용하세요.'},'elapsed_ms':0,'warnings':[]}
                    elif r.path.startswith('/kbn:/'):
                        response=CLIENT.kibana(cluster,r.method,r.path[len('/kbn:'):],r.body)
                    else:response=CLIENT.call(cluster,r.method,r.path,r.body,raw=r.raw_body,content_type=r.content_type)
                    log_event(session,task_id,cluster,r.public(),response)
                    results.append(dict(response,request=r.public()))
                    if response['status']>=400 and data.get('stop_on_error',True):break
                return self.send(200,{'results':results,'requested':len(requests),'executed':len(results)})
            if path=='/api/check':
                result=Verify(CLIENT,task,cluster,data.get('code',''),str(data.get('answer','')),history(session,task_id)).run()
                return self.send(200,result)
            if path=='/api/history':return self.send(200,{'events':history(session,task_id)})
            return self.send(404,{'error':'없는 API입니다.'})
        except (ValueError,ConsoleError) as e:return self.send(400,{'error':str(e)})
        except Exception as e:return self.send(500,{'error':str(e),'hint':'이 응답은 실습 웹 서버에서 발생했습니다. docker compose logs app을 확인하세요.'})

if __name__=='__main__':
    db_init()
    if os.getenv('LAB_SKIP_BOOTSTRAP')!='1':threading.Thread(target=LAB.bootstrap,daemon=True).start()
    else:LAB.update(phase='starting',message='UI 테스트 모드 · Elasticsearch 실행은 제공하지 않음')
    host=os.getenv('LAB_BIND','0.0.0.0');port=int(os.getenv('PORT','8787'))
    print(f'Elastic Exam Lab listening on {host}:{port}',flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()
