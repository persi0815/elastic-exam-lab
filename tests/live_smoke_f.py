#!/usr/bin/env python3
"""Opt-in real F integration in a UUID namespace, preserving the active exam.

ES and Kibana kbn: solutions use the real Kibana Console proxy and fixed Kibana
API routing. Verify uses a resource-name adapter;
this does not reset the lab or switch the user to F for /api/check.
"""
import argparse,base64,copy,json,os,re,sys,time,uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from elastic import Elastic
from console import parse_console
from verify import Verify
from live_smoke_e import IsolatedElastic as BaseIsolatedElastic

class Names:
    def __init__(self,prefix,tasks,fixtures):
        names={x['index'] for x in fixtures}
        for task in tasks:
            names.update(re.findall(r'(?<![\w.-])(?:f-[\w.-]+|logs-f[\w.-]*)(?![\w.-])',task['solution']))
            names.update(task['datasets'])
        self.mapping={name:('logs-'+prefix+name[5:] if name.startswith('logs-') else prefix+name) for name in names}
        self.forward=re.compile('|'.join(r'(?<![\w.-])'+re.escape(k)+r'(?![\w.-])' for k in sorted(names,key=len,reverse=True)))
        self.inverse={v:k for k,v in self.mapping.items()}
        self.backward=re.compile('|'.join(re.escape(k) for k in sorted(self.inverse,key=len,reverse=True)))
    def rewrite(self,value,reverse=False):
        mapping,pattern=(self.inverse,self.backward) if reverse else (self.mapping,self.forward)
        if isinstance(value,str):return pattern.sub(lambda m:mapping[m.group()],value)
        if isinstance(value,list):return [self.rewrite(x,reverse) for x in value]
        if isinstance(value,tuple):return tuple(self.rewrite(x,reverse) for x in value)
        if isinstance(value,dict):return {self.rewrite(k,reverse):self.rewrite(v,reverse) for k,v in value.items()}
        return value
    def body(self,value):return self.rewrite(value)
    def raw(self,value,content_type):
        if value is None:return None
        if content_type=='application/x-ndjson':return '\n'.join(json.dumps(self.body(json.loads(x))) for x in value.splitlines() if x.strip())+'\n'
        return json.dumps(self.body(json.loads(value))) if value.strip() else value

class IsolatedElastic(BaseIsolatedElastic):
    def __init__(self,names,prefix):
        super().__init__(names,prefix);self.streams=set()
    def owned(self,name):return name.startswith(self.prefix) or name.startswith('logs-'+self.prefix)
    def record(self,cluster,method,path,body=None):
        if method=='POST' and path.split('?')[0]=='/_query':
            query=(body or {}).get('query','')
            if self.prefix not in query:raise RuntimeError('ES|QL source is outside the test namespace.')
            return
        return super().record(cluster,method,path,body)
    def kibana(self,cluster,method,path,body=None,**kwargs):
        path=self.names.rewrite(path);body=self.names.body(body)
        if method not in ('GET','HEAD'):
            parts=path.split('?')[0].strip('/').split('/')
            if len(parts)<3 or parts[:2]!=['api','streams'] or not self.owned(parts[2]):
                raise RuntimeError('Kibana write is outside the isolated stream.')
            self.streams.add((cluster,parts[2]))
        result=Elastic.kibana(self,cluster,method,path,body,**kwargs)
        return dict(result,body=self.names.rewrite(result['body'],True))
    def cleanup(self):
        errors=[]
        for cluster,name in sorted(self.streams):
            result=Elastic.kibana(self,cluster,'DELETE','/api/streams/'+name)
            if result['status'] not in (200,204,404):errors.append({'kind':'stream','name':name,'result':result})
        errors+=super().cleanup()
        # Streams creates managed templates/pipelines outside the direct ES
        # request list. Delete only exact names containing our fresh UUID.
        for endpoint,key in (('/_index_template','index_templates'),('/_component_template','component_templates'),('/_ingest/pipeline',None)):
            result=Elastic.call(self,'cluster1','GET',endpoint)
            if result['status']!=200:
                errors.append({'kind':'cleanup inspection','endpoint':endpoint,'status':result['status']});continue
            names=[x['name'] for x in result['body'].get(key,[])] if key else list(result['body'])
            for name in names:
                if self.prefix not in name:continue
                deleted=Elastic.call(self,'cluster1','DELETE',endpoint+'/'+name)
                if deleted['status'] not in (200,404):errors.append({'kind':'managed resource','name':name,'result':deleted})
        return errors
    def leftovers(self):
        found=super().leftovers()
        result=Elastic.kibana(self,'cluster1','GET','/api/streams')
        for stream in result.get('body',{}).get('streams',[]):
            if self.prefix in stream.get('name',''):found.append({'kind':'stream','name':stream['name']})
        for endpoint,key in (('/_index_template','index_templates'),('/_component_template','component_templates'),('/_ingest/pipeline',None)):
            result=Elastic.call(self,'cluster1','GET',endpoint)
            if result['status']!=200:found.append({'kind':'inspection failure','endpoint':endpoint,'status':result['status']});continue
            names=[x['name'] for x in result['body'].get(key,[])] if key else list(result['body'])
            found.extend({'kind':'managed resource','endpoint':endpoint,'name':name} for name in names if self.prefix in name)
        return found

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-isolated',action='store_true')
    parser.add_argument('--url',default='http://127.0.0.1:8787')
    parser.add_argument('--output',default=str(ROOT/'state/f-smoke-report.json'))
    args=parser.parse_args()
    if not args.run_isolated:parser.error('--run-isolated explicitly opts into disposable test resources')
    catalog=json.loads((ROOT/'data/catalog.json').read_text())
    tasks=[t for t in catalog['tasks'] if t['set']=='F']
    fixtures=json.loads((ROOT/'data/fixtures-f.json').read_text())['indices']
    prefix='ece-f-smoke-'+uuid.uuid4().hex[:12]+'-'
    names=Names(prefix,tasks,fixtures);es=IsolatedElastic(names,prefix)
    session=prefix+'session'
    auth='Basic '+base64.b64encode((es.user+':'+es.password).encode()).decode()
    def app(path,body=None,headers=None,raw=None):
        supplied={'Content-Type':'application/json','X-Lab-Request':'1',**(headers or {})}
        data=raw.encode() if raw is not None else json.dumps(body).encode() if body is not None else None
        try:
            with urlopen(Request(args.url+path,data=data,headers=supplied),timeout=150) as r:return r.status,json.loads(r.read())
        except HTTPError as error:
            raw=error.read().decode()
            try:raw=json.loads(raw)
            except ValueError:pass
            return error.code,raw
    status=app('/api/status')[1];before={k:status['lab'][k] for k in ('active_set','generation')}
    if status['lab']['phase']!='ready':raise RuntimeError('Existing lab must be ready.')
    active=next(t['id'] for t in catalog['tasks'] if t['set']==before['active_set'])
    def history():
        return app('/api/history',{'session':session,'task_id':active,'cluster':'cluster1'})[1].get('events',[])
    report={'namespace':prefix,'scope':__doc__,'lab_before':before,'results':[]}
    try:
        for fixture in fixtures:
            name=fixture['index'];cluster=fixture['cluster']
            template={'settings':fixture['settings'],'mappings':fixture['mappings']}
            if fixture.get('data_stream'):
                es.require(cluster,'PUT','/_index_template/'+name,{'index_patterns':[name],'data_stream':{},'priority':600,'template':template})
                es.require(cluster,'PUT','/_data_stream/'+name)
            else:es.require(cluster,'PUT','/'+name,template)
            lines=[]
            for doc in fixture['documents']:
                lines.extend([json.dumps({'create' if fixture.get('data_stream') else 'index':{'_id':doc['_id']}}),json.dumps(doc['_source'])])
            if lines:
                result=es.require(cluster,'POST',f'/{name}/_bulk?refresh=true',raw='\n'.join(lines)+'\n',content_type='application/x-ndjson')
                if result.get('errors'):raise RuntimeError('Fixture indexing failed: '+json.dumps(result)[:1000])
        for task in tasks:
            print(task['id'],task['title'],flush=True)
            checked={'id':task['id'],'complete':False};report['results'].append(checked)
            start=len(history());execution=[]
            for request in parse_console(task['solution']):
                path=names.rewrite(request.path);body=names.body(request.body)
                if path.startswith('/kbn:/'):
                    parts=path[len('/kbn:'):].strip('/').split('/')
                    if request.method not in ('GET','HEAD'):
                        if len(parts)<3 or parts[:2]!=['api','streams'] or not es.owned(parts[2]):raise RuntimeError('Kibana write outside namespace')
                        es.streams.add((task['cluster'],parts[2]))
                else:
                    es.record(task['cluster'],request.method,path,body)
                headers={'Authorization':auth,'kbn-xsrf':'true','x-elastic-internal-origin':'Kibana','kbn-version':catalog['engine_version'],
                    'Content-Type':request.content_type,'Cookie':f'ece_session={session}; ece_task_cluster1={active}; ece_task_cluster2={active}'}
                raw=names.raw(request.raw_body,request.content_type) if request.raw_body is not None else ''
                proxy='/kibana1/api/console/proxy?'+urlencode({'path':path.lstrip('/'),'method':request.method})
                http,response=app(proxy,headers=headers,raw=raw)
                if http>=400 or isinstance(response,dict) and any(response.get(k) for k in ('error','failures','errors')):
                    execution.append({'path':path,'status':http,'response':response});break
            events=names.rewrite(history()[start:],True)
            if execution:checked['execution_failures']=execution
            else:
                for attempt in range(8):
                    checked.update(Verify(es,task,task['cluster'],task['solution'],history=events).run())
                    if checked['complete']:break
                    if attempt<7:time.sleep(2)
                checked['native_console_capture']=any(e['request'].get('source')=='kibana-console' for e in events)
                checked['complete']=checked['complete'] and checked['native_console_capture']
            print(' PASS' if checked['complete'] else ' FAIL',flush=True)
    except Exception as error:report['error']=str(error);print('Error:',error,flush=True)
    finally:
        try:report['cleanup_failures']=es.cleanup()
        except Exception as error:report['cleanup_failures']=[{'error':str(error)}]
        try:report['leftovers']=es.leftovers()
        except Exception as error:report['leftovers']=[{'error':str(error)}]
        try:
            after=app('/api/status')[1];report['lab_after']={k:after['lab'][k] for k in before}
            report['current_set_preserved']=report['lab_after']==before
        except Exception as error:report['status_error']=str(error);report['current_set_preserved']=False
        report['complete']=len(report['results'])==10 and all(t['complete'] for t in report['results']) and not report.get('error') and not report['cleanup_failures'] and not report['leftovers'] and report['current_set_preserved']
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(sum(t['complete'] for t in report['results']),'of 10 passed;',args.output,flush=True)
    return 0 if report['complete'] else 1

if __name__=='__main__':sys.exit(main())
