"""Same-origin proxy to genuine Kibana; it does not implement or imitate Console.

Targets are fixed by server configuration. Static bundles, CSP, authentication cookies
and Console's own ES proxy API pass through unchanged. Only explicitly executed
Console requests are observed for per-question practice history.
"""
from __future__ import annotations
import base64,http.client,json,os,re,time,threading
from http.cookies import SimpleCookie
from urllib.parse import urlsplit,parse_qs

HOP={'connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade'}
PREFIX={'cluster1':'/kibana1','cluster2':'/kibana2'}
TARGETS={'cluster1':os.getenv('KIBANA1_URL','http://kibana1:5601'),
         'cluster2':os.getenv('KIBANA2_URL','http://kibana2:5601')}
MAX_BODY=20_000_000

def identify(path):
    p=urlsplit(path).path
    for cluster,prefix in PREFIX.items():
        if p==prefix or p.startswith(prefix+'/'):return cluster
    return None

def console_request(path,raw,cookies,cluster):
    """Return metadata only for actual Console run requests, not autocomplete APIs."""
    u=urlsplit(path)
    if not u.path.endswith('/api/console/proxy'):return None
    args=parse_qs(u.query)
    method=args.get('method',[''])[0].upper();target=args.get('path',[''])[0]
    if method not in ('GET','POST','PUT','DELETE','PATCH','HEAD') or not target:return None
    try:
        jar=SimpleCookie();jar.load(cookies or '')
        session=jar.get('ece_session');task=jar.get('ece_task_'+cluster)
        session=session.value[:128] if session else 'local'
        task=task.value if task else ''
    except Exception:return None
    try:body=json.loads(raw.decode('utf-8')) if raw.strip() else None
    except (UnicodeError,ValueError):body=None
    return {'session':session,'task_id':task,'request':{'method':method,'path':'/'+target.lstrip('/'),
             'body':body,'raw_body':raw.decode('utf-8',errors='replace'),'line':1,'source':'kibana-console'}}

def proxy(handler,cluster,log_callback=None,guard=None):
    target=urlsplit(TARGETS[cluster]);conn=None
    if target.scheme!='http' or not target.hostname:
        return handler.send(500,{'error':'KIBANA URL must be a fixed internal http endpoint.'})
    try:
        length=int(handler.headers.get('Content-Length','0'))
        if length<0 or length>MAX_BODY:return handler.send(413,{'error':'Kibana request limit is 20 MB.'})
        raw=handler.rfile.read(length) if length else b''
        captured=console_request(handler.path,raw,handler.headers.get('Cookie'),cluster)
        if captured and guard:
            error=guard(captured)
            if error:return handler.send(403,{'error':error})
        origin=handler.headers.get('Origin')
        if handler.command not in ('GET','HEAD','OPTIONS') and origin:
            if urlsplit(origin).netloc!=handler.headers.get('Host'):
                return handler.send(403,{'error':'Only same-origin Kibana requests are allowed.'})
        headers={k:v for k,v in handler.headers.items() if k.lower() not in HOP|{'host','content-length'}}
        headers['Host']=target.netloc
        headers['X-Forwarded-Host']=handler.headers.get('Host','localhost:8787')
        headers['X-Forwarded-Proto']='http'
        upstream_path=handler.path;upstream_method=handler.command
        if captured and captured['request']['path'].startswith('/kbn:'):
            # Older native Console builds send kbn: through the Console proxy.
            # Forward it to the REAL fixed Kibana API, with no simulated response.
            api_path=captured['request']['path'][len('/kbn:'):]
            if not api_path.startswith('/api/'):
                return handler.send(400,{'error':'Kibana 내부 /api/ 경로만 허용합니다.'})
            upstream_path=PREFIX[cluster]+api_path
            upstream_method=captured['request']['method']
            headers['kbn-xsrf']='ece-exam-lab'
        # Never pass app's private tracking cookies to Kibana itself.
        cookie=headers.get('Cookie','')
        if cookie:headers['Cookie']='; '.join(v.strip() for v in cookie.split(';') if not v.strip().startswith('ece_'))
        if raw:headers['Content-Length']=str(len(raw))
        t=time.perf_counter()
        conn=http.client.HTTPConnection(target.hostname,target.port or 80,timeout=180)
        conn.request(upstream_method,upstream_path,body=raw or None,headers=headers)
        response=conn.getresponse()
        # Stream large Kibana bundles without buffering them. Chunking is decoded by http.client.
        upstream_length=response.getheader('Content-Length')
        if captured and log_callback:
            log_callback(captured,cluster,{'status':response.status,'elapsed_ms':round((time.perf_counter()-t)*1000,1)})
        handler.send_response(response.status)
        for key,value in response.getheaders():
            if key.lower() not in HOP|{'content-length'}:handler.send_header(key,value)
        if upstream_length is not None:handler.send_header('Content-Length',upstream_length)
        else:
            handler.send_header('Connection','close');handler.close_connection=True
        handler.end_headers()
        if handler.command!='HEAD':
            while True:
                chunk=response.read(65536)
                if not chunk:break
                try:handler.wfile.write(chunk)
                except (BrokenPipeError,ConnectionResetError):break
    except (OSError,TimeoutError,http.client.HTTPException) as exc:
        try:handler.send(502,{'error':'Kibana is starting or unavailable. Open the lab status panel.',
             'cluster':cluster,'detail':str(exc),'hint':'docker compose logs '+('kibana1' if cluster=='cluster1' else 'kibana2')})
        except (BrokenPipeError,ConnectionResetError):pass
    finally:
        if conn:conn.close()

_CACHE={'time':0,'value':{}};_LOCK=threading.Lock()
def health(password='ExamLab2026'):
    with _LOCK:
        if time.time()-_CACHE['time']<5:return _CACHE['value']
        value={}
        for c,u in TARGETS.items():
            target=urlsplit(u);conn=None
            try:
                conn=http.client.HTTPConnection(target.hostname,target.port or 80,timeout=1)
                auth=base64.b64encode(('elastic:'+password).encode()).decode()
                conn.request('GET',PREFIX[c]+'/api/status',headers={'Authorization':'Basic '+auth})
                r=conn.getresponse();data=r.read(2_000_000)
                parsed=json.loads(data)
                level=parsed.get('status',{}).get('overall',{}).get('level','unknown')
                value[c]={'connected':r.status==200,'status':r.status,'level':level,
                          'version':parsed.get('version',{}).get('number'),'url':PREFIX[c]+'/app/dev_tools#/console'}
            except Exception as e:value[c]={'connected':False,'level':'starting','error':str(e),'url':PREFIX[c]+'/app/dev_tools#/console'}
            finally:
                if conn:conn.close()
        _CACHE.update(time=time.time(),value=value)
        return value
