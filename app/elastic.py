"""Fixed-target Elasticsearch HTTP client. No fabricated ES responses."""
from __future__ import annotations
import base64
import json
import os
import time
import socket
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
from urllib.parse import quote

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class Elastic:
    def __init__(self):
        self.urls={'cluster1':os.getenv('CLUSTER1_URL','http://es01:9200').rstrip('/'),
                   'cluster2':os.getenv('CLUSTER2_URL','http://server4:9200').rstrip('/')}
        self.expected={'cluster1':os.getenv('CLUSTER1_NAME','ece-lab-cluster1'),
                       'cluster2':os.getenv('CLUSTER2_NAME','ece-lab-cluster2')}
        self.kibana_urls={'cluster1':os.getenv('KIBANA1_URL','http://kibana1:5601').rstrip('/'),
                         'cluster2':os.getenv('KIBANA2_URL','http://kibana2:5601').rstrip('/')}
        self.user=os.getenv('ELASTIC_USER','elastic')
        self.password=os.getenv('ELASTIC_PASSWORD','ExamLab2026')
        self.opener=build_opener(NoRedirect())
    def call(self,cluster,method,path,body=None,*,raw=None,content_type='application/json',timeout=120,auth=None):
        if cluster not in self.urls: raise ValueError('지원하는 클러스터는 cluster1, cluster2입니다.')
        return self._http(self.urls[cluster],method,path,body,raw=raw,content_type=content_type,timeout=timeout,auth=auth)
    def kibana(self,cluster,method,path,body=None,*,timeout=120):
        if cluster not in self.kibana_urls:raise ValueError('지원하는 클러스터는 cluster1, cluster2입니다.')
        if not path.startswith('/api/'):raise ValueError('Kibana 내부 /api/ 경로만 허용합니다.')
        prefix='/kibana1' if cluster=='cluster1' else '/kibana2'
        return self._http(self.kibana_urls[cluster],method,prefix+path,body,timeout=timeout,
                          extra_headers={'kbn-xsrf':'ece-exam-lab'})
    def kibana_require(self,cluster,method,path,body=None,**kwargs):
        result=self.kibana(cluster,method,path,body,**kwargs)
        if result['status']>=400:raise RuntimeError(f'{cluster} Kibana {method} {path} → {result["status"]}: {json.dumps(result["body"],ensure_ascii=False)[:1200]}')
        return result['body']
    def _http(self,target,method,path,body=None,*,raw=None,content_type='application/json',timeout=120,auth=None,extra_headers=None):
        if not path.startswith('/'):path='/'+path
        start=time.perf_counter()
        data=raw.encode('utf-8') if raw is not None else json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None
        username,password=auth or (self.user,self.password)
        headers={'Content-Type':content_type,'Authorization':'Basic '+base64.b64encode(f'{username}:{password}'.encode()).decode(),'X-Opaque-Id':'ece-exam-lab'}
        headers.update(extra_headers or {})
        # Encode date math, spaces and non-ASCII. Preserve API/query delimiters.
        url=target+quote(path,safe='/%?:,=+*&-_.!~\'()')
        status=0;response=None;warnings=[]
        try:
            req=Request(url,data=data,headers=headers,method=method)
            with self.opener.open(req,timeout=timeout) as r:
                status=r.status;payload=r.read(16_000_001);warnings=r.headers.get_all('Warning',[])
                if len(payload)>16_000_000:
                    response={'error':'응답이 16 MB를 넘었습니다. size/_source/filter_path로 결과를 줄이세요. Elasticsearch 요청 자체는 실행되었을 수 있습니다.'}
                else:
                    txt=payload.decode('utf-8',errors='replace')
                    try:response=json.loads(txt)
                    except (ValueError,TypeError):response=txt if txt else {'status':status}
        except HTTPError as e:
            status=e.code;txt=e.read(16_000_000).decode('utf-8',errors='replace')
            try:response=json.loads(txt)
            except ValueError:response={'error':txt or e.reason}
        except (URLError,socket.timeout,TimeoutError,OSError) as e:
            status=502
            response={'error':{'type':'lab_connection_error','reason':str(e),
                'hint':'연결 상태와 docker compose logs를 확인하세요. 시간 초과라면 작업이 계속 실행 중일 수 있습니다. _tasks와 _count를 확인한 뒤 재시도하세요.'}}
        return {'status':status,'body':response,'elapsed_ms':round((time.perf_counter()-start)*1000,1),'warnings':warnings}
    def get(self,cluster,path,body=None,**kwargs):return self.call(cluster,'GET',path,body,**kwargs)
    def require(self,cluster,method,path,body=None,**kwargs):
        r=self.call(cluster,method,path,body,**kwargs)
        if r['status']>=400:raise RuntimeError(f'{cluster} {method} {path} → {r["status"]}: {json.dumps(r["body"],ensure_ascii=False)[:1200]}')
        return r['body']
