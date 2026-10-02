#!/usr/bin/env python3
"""OPT-IN DESTRUCTIVE integration test against this disposable Docker lab only.
Executes reference solutions THROUGH GENUINE KIBANA'S CONSOLE API, then checks ES.
Not run in the delivery environment: Docker and external downloads are unavailable.
"""
from __future__ import annotations
import argparse,base64,json,os,sys,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode,urlsplit
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from console import parse_console
CAT=json.loads((ROOT/'data/catalog.json').read_text())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://localhost:8787');p.add_argument('--confirm-reset',action='store_true');p.add_argument('--sets',default='D');a=p.parse_args()
    if not a.confirm_reset:p.error('--confirm-reset required: BOTH lab clusters and existing answers are reset.')
    if urlsplit(a.url).hostname not in ('localhost','127.0.0.1','::1'):p.error('Only a loopback lab URL is allowed.')
    allowed={s['id'] for s in CAT['sets']}
    if any(s not in allowed for s in a.sets) or not a.sets:p.error('--sets must contain catalog set IDs: '+''.join(sorted(allowed)))
    env={}
    if (ROOT/'.env').exists():
        for l in (ROOT/'.env').read_text().splitlines():
            if '=' in l and not l.startswith('#'):k,v=l.split('=',1);env[k]=v
    pw=os.getenv('ELASTIC_PASSWORD',env.get('ELASTIC_PASSWORD','ExamLab2026'))
    auth='Basic '+base64.b64encode(('elastic:'+pw).encode()).decode()
    session='live-native-'+str(int(time.time()))
    def call(path,body=None,headers=None,raw=None,timeout=240):
        h={'Content-Type':'application/json','X-Lab-Request':'1'};h.update(headers or {})
        data=raw.encode() if raw is not None else None if body is None else json.dumps(body).encode()
        req=Request(a.url.rstrip('/')+path,data=data,headers=h)
        try:
            with urlopen(req,timeout=timeout) as r:
                data=r.read().decode();return r.status,json.loads(data) if data else {}
        except HTTPError as e:
            raw=e.read().decode()
            try:body=json.loads(raw)
            except ValueError:body=raw
            return e.code,body
    def api(path,body=None):
        code,result=call(path,body)
        if code>=400:raise RuntimeError(f'{path}: HTTP {code} {result}')
        return result
    def ready():
        for _ in range(240):
            s=api('/api/status')
            if s['lab']['phase']=='error':raise RuntimeError(s['lab'].get('error'))
            if s['lab']['phase']=='ready' and all(s['kibana'][c]['connected'] for c in ('cluster1','cluster2')):return s
            print('  Waiting:',s['lab']['message'],flush=True);time.sleep(5)
        raise RuntimeError('Readiness timeout')
    ready();report=[]
    for group in a.sets:
        api('/api/reset',{'set':group,'confirmation':'RESET LAB'});ready()
        for t in [x for x in CAT['tasks'] if x['set']==group]:
            print(t['id'],t['title'],flush=True);execution=[]
            n=1 if t['cluster']=='cluster1' else 2
            h={'Authorization':auth,'kbn-xsrf':'true','x-elastic-internal-origin':'Kibana','kbn-version':CAT['engine_version'],
               'Cookie':f'ece_session={session}; ece_task_cluster1={t["id"]}; ece_task_cluster2={t["id"]}'}
            for q in parse_console(t['solution']):
                h['Content-Type']=q.content_type
                path=f'/kibana{n}/api/console/proxy?'+urlencode({'path':q.path.lstrip('/'),'method':q.method})
                raw=q.raw_body if q.raw_body is not None else json.dumps(q.body) if q.body is not None else ''
                code,out=call(path,headers=h,raw=raw)
                if code>=400 or isinstance(out,dict) and (out.get('error') or out.get('failures') or out.get('errors')):
                    execution.append({'method':q.method,'path':q.path,'http':code,'response':out});break
            if execution:
                report.append({'id':t['id'],'complete':False,'execution_failures':execution});print('  EXECUTION FAIL',execution[0],flush=True);continue
            payload={'task_id':t['id'],'cluster':t['cluster'],'session':session,'code':t['solution'],'answer':t.get('answer','')}
            checked={}
            for _ in range(12):
                checked=api('/api/check',payload)
                if checked['complete']:break
                time.sleep(3)
            # Ensure native proxy capture works even though grading also has an explicit script.
            hist=api('/api/history',payload)['events'];captured=any(e['request'].get('source')=='kibana-console' for e in hist)
            checked.update(id=t['id'],native_console_capture=captured)
            if not captured:checked['complete']=False
            report.append(checked);print('  PASS' if checked['complete'] else '  CHECK FAIL',flush=True)
    output=ROOT/'live-test-report.json';output.write_text(json.dumps({'ran_at':time.strftime('%Y-%m-%dT%H:%M:%S'),'scope':'Real local ES + real Kibana HTTP API. Browser interaction is not tested.','results':report},ensure_ascii=False,indent=2))
    passed=sum(x.get('complete',False) for x in report);print(f'{passed}/{len(report)} passed. {output}')
    return 0 if passed==len(report) else 1
if __name__=='__main__':sys.exit(main())
