"""v2 regression tests. Fake upstream tests exercise HTTP plumbing, not Elasticsearch."""
from __future__ import annotations
import gzip,json,math,sys,threading,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import kibana_proxy
from lab import FIX
from console import parse_console
from verify_d import subset
CAT=json.loads((ROOT/'data/catalog.json').read_text())
TASKS={t['id']:t for t in CAT['tasks']}
FIXMAP={f['index']:f for f in FIX}

class SeptemberDataTests(unittest.TestCase):
    def test_article_to_exact_count(self):
        self.assertEqual(sum('to' in d['_source']['title'].lower().split() for d in FIXMAP['article']['documents']),357)
    def test_vector_dimensions(self):
        docs=FIXMAP['article']['documents'];self.assertEqual(len(docs),480)
        self.assertTrue(all(len(d['_source']['vector']['cosine'])==6 for d in docs))
        self.assertTrue(all(sum(x*x for x in d['_source']['vector']['cosine'])>0 for d in docs))
    def test_vector_source_preserved(self):self.assertFalse(FIXMAP['article']['settings']['index.mapping.exclude_source_vectors'])
    def test_knn_filter_has_enough_candidates(self):
        docs=FIXMAP['article']['documents'];self.assertGreater(sum('term' in d['_source']['tags'] for d in docs),10)
        self.assertTrue(any('term' not in d['_source']['tags'] for d in docs[:32]))
    def test_every_article_has_reference(self):
        keys={d['_source']['region_id'] for d in FIXMAP['regions']['documents']}
        self.assertTrue(all(d['_source']['region'] in keys for d in FIXMAP['article']['documents']))
    def test_empty_ingest_index(self):
        self.assertEqual(FIXMAP['ingest-logs']['mappings'],{})
        self.assertEqual(FIXMAP['ingest-logs']['documents'],[])
    def test_bool_pagination_has_both_featured_values(self):
        values=[d['_source'] for d in FIXMAP['article']['documents'] if 'kubernetes' in d['_source']['body'].lower().split() and 'devops' in d['_source']['tags']]
        self.assertGreater(len(values),24);self.assertEqual({d['featured'] for d in values},{True,False})
    def test_months_have_values(self):
        dates={d['_source']['@timestamp'][5:7] for d in FIXMAP['article']['documents'] if d['_source']['@timestamp'].startswith('2012')}
        self.assertEqual(len(dates),12)
    def test_native_default_both_configured(self):
        s=(ROOT/'compose.yaml').read_text();self.assertNotIn('profiles:',s)
        for x in ['kibana1:','kibana2:','name: ece-exam-lab-v2','9.3.8']:self.assertIn(x,s)
    def test_same_origin_basepaths_and_http_auth(self):
        for n in (1,2):
            s=(ROOT/f'infra/kibana{n}.yml').read_text()
            self.assertIn(f'server.basePath: "/kibana{n}"',s);self.assertIn('server.rewriteBasePath: true',s)
            self.assertIn('xpack.security.authc.http.schemes: [apikey, bearer, basic]',s)
    def test_native_editor_not_overlay(self):
        s=(ROOT/'web/index.html').read_text();self.assertIn('kibanaFrame1',s);self.assertIn('kibanaFrame2',s)
        self.assertNotIn('id="editor"',s);self.assertNotIn('cdn.',s)
    def test_preserved_references(self):
        self.assertEqual(TASKS['D06']['datasets'],['food-ingredients'])
        self.assertEqual(TASKS['D08']['datasets'],['movie_data'])
        self.assertEqual(TASKS['D04']['cluster'],'cluster2')
        self.assertEqual(TASKS['D04']['solution'],TASKS['B06']['solution'])
    def test_conflicts_are_explicit(self):
        for id,needle in [('D05','Task7'),('D07','from:19/from:20'),('D09','response_stauts'),('D10','a/b')]:
            self.assertIn(needle,' '.join(TASKS[id]['notes']))
    def test_no_d9_index_recreate(self):
        qs=parse_console(TASKS['D09']['solution'])
        self.assertFalse(any(q.method in ('DELETE','PUT') and q.path=='/ingest-logs' for q in qs))
    def test_d9_pipeline_format(self):
        qs=parse_console(TASKS['D09']['solution']);p=next(q.body for q in qs if q.path=='/_ingest/pipeline/task9')
        self.assertEqual([next(iter(x)) for x in p['processors']],['grok','convert','date','remove'])
        self.assertTrue(any(q.path=='/_ingest/pipeline/task9/_simulate' and q.body['docs'] for q in qs))
    def test_subsets_account_for_es_defaults(self):
        self.assertTrue(subset({'type':'dense_vector','dims':6},{'type':'dense_vector','dims':6,'index':True}))
        self.assertFalse(subset({'type':'keyword'},{'type':'text'}))

class ConsoleCaptureTests(unittest.TestCase):
    def test_extract_nested_knn_body(self):
        q={'query':{'knn':{'field':'vector.cosine'}}}
        c=kibana_proxy.console_request('/kibana1/api/console/proxy?path=article%2F_search&method=GET',json.dumps(q).encode(),'ece_session=abc; ece_task_cluster1=D01','cluster1')
        self.assertEqual(c['task_id'],'D01');self.assertEqual(c['request']['path'],'/article/_search');self.assertEqual(c['request']['body'],q)
    def test_autocomplete_not_captured(self):self.assertIsNone(kibana_proxy.console_request('/kibana1/api/console/autocomplete_entities',b'','', 'cluster1'))
    def test_cluster_two_cookie(self):
        c=kibana_proxy.console_request('/kibana2/api/console/proxy?path=_snapshot&method=GET',b'','ece_task_cluster1=D01; ece_task_cluster2=D04','cluster2')
        self.assertEqual(c['task_id'],'D04')
    def test_bulk_kept_as_raw(self):
        raw=b'{"index":{}}\n{"a":1}\n'
        c=kibana_proxy.console_request('/kibana1/api/console/proxy?path=example%2F_bulk&method=POST',raw,'','cluster1')
        self.assertIsNone(c['request']['body']);self.assertEqual(c['request']['raw_body'],raw.decode())
    def test_known_prefix_only(self):
        self.assertEqual(kibana_proxy.identify('/kibana1/app/dev_tools'),'cluster1')
        self.assertIsNone(kibana_proxy.identify('/kibana1-evil/foo'));self.assertIsNone(kibana_proxy.identify('/api/execute'))

class NativeProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.received=[];cls.captured=[]
        class Upstream(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*a):pass
            def do_GET(self):self.reply()
            def do_POST(self):self.reply()
            def reply(self):
                raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
                cls.received.append({'path':self.path,'headers':dict(self.headers),'raw':raw})
                data=json.dumps({'test_mock':True,'path':self.path,'received':raw.decode()}).encode()
                compressed=self.path.endswith('/bundle.js')
                if compressed:data=gzip.compress(data)
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)));self.send_header('X-Frame-Options','SAMEORIGIN')
                self.send_header('Content-Security-Policy',"frame-ancestors 'self'")
                self.send_header('Set-Cookie','sid=test; Path=/kibana1; HttpOnly; SameSite=Lax')
                if compressed:self.send_header('Content-Encoding','gzip')
                self.end_headers();self.wfile.write(data)
        cls.up=ThreadingHTTPServer(('127.0.0.1',0),Upstream);threading.Thread(target=cls.up.serve_forever,daemon=True).start()
        cls.orig=dict(kibana_proxy.TARGETS);kibana_proxy.TARGETS['cluster1']=f'http://127.0.0.1:{cls.up.server_address[1]}'
        class Proxy(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*a):pass
            def send(self,status,body):
                data=json.dumps(body).encode();self.send_response(status);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def do_GET(self):kibana_proxy.proxy(self,'cluster1',lambda *x:cls.captured.append(x))
            def do_POST(self):self.do_GET()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Proxy);threading.Thread(target=cls.server.serve_forever,daemon=True).start();cls.url=f'http://127.0.0.1:{cls.server.server_address[1]}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.up.shutdown();cls.up.server_close();kibana_proxy.TARGETS.update(cls.orig)
    def test_preserve_basepath_and_headers(self):
        with urlopen(self.url+'/kibana1/app/dev_tools') as r:
            self.assertEqual(r.headers['X-Frame-Options'],'SAMEORIGIN')
            self.assertEqual(r.headers['Content-Security-Policy'],"frame-ancestors 'self'")
            self.assertIn('Path=/kibana1',r.headers['Set-Cookie']);self.assertEqual(json.load(r)['path'],'/kibana1/app/dev_tools')
    def test_gzip_bundle(self):
        with urlopen(self.url+'/kibana1/bundle.js') as r:
            self.assertEqual(r.headers['Content-Encoding'],'gzip');self.assertTrue(json.loads(gzip.decompress(r.read()))['test_mock'])
    def test_native_execution_capture(self):
        n=len(self.captured)
        req=Request(self.url+'/kibana1/api/console/proxy?path=article%2F_search&method=GET',data=b'{"size":10}',headers={'Cookie':'ece_session=unit; ece_task_cluster1=D01; sid=real','kbn-xsrf':'true','Origin':self.url})
        with urlopen(req) as r:self.assertEqual(r.status,200);r.read()
        import time
        for _ in range(20):
            if len(self.captured)>n:break
            time.sleep(.01)
        self.assertEqual(self.captured[-1][0]['task_id'],'D01')
        self.assertEqual(self.received[-1]['headers']['Cookie'],'sid=real')
    def test_cross_origin_post_rejected(self):
        req=Request(self.url+'/kibana1/api/foo',data=b'{}',headers={'Origin':'https://evil.invalid'})
        with self.assertRaises(HTTPError) as e:urlopen(req)
        self.assertEqual(e.exception.code,403)

    def test_kibana_console_api_uses_real_fixed_kibana_target(self):
        request=Request(self.url+'/kibana1/api/console/proxy?path=kbn%3A%2Fapi%2Fstreams%2Flogs-f08-app-default&method=GET',
                        data=b'',headers={'Cookie':'ece_session=unit; ece_task_cluster1=D01','Origin':self.url})
        with urlopen(request) as response:
            self.assertEqual(response.status,200)
            self.assertEqual(json.load(response)['path'],'/kibana1/api/streams/logs-f08-app-default')
        self.assertEqual(self.captured[-1][0]['request']['path'],'/kbn:/api/streams/logs-f08-app-default')

if __name__=='__main__':unittest.main(verbosity=2)
