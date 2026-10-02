"""Local unit / HTTP contract tests. These do NOT start Elasticsearch."""
from __future__ import annotations
import json, os, sys, tempfile, unittest, threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request as HTTPRequest, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from console import parse_console, ConsoleError
from verify import canon_agg, equivalent, duration, sort_spec
from lab import Lab, FIX

class ParserTests(unittest.TestCase):
    def test_multiple_requests(self):
        r=parse_console('GET blogs/_mapping\n\nGET blogs/_search\n{"size":0}')
        self.assertEqual(len(r),2);self.assertEqual(r[1].body,{'size':0})
    def test_comments(self):
        r=parse_console('// 앞\nPUT index // 주석\n{\n/*주석*/ "mappings": {"properties":{}} # 뒤\n}')[0]
        self.assertEqual(r.body,{'mappings':{'properties':{}}})
    def test_url_inside_body(self):
        r=parse_console('POST index/_doc\n{"url":"https://example.test/a#b//c"}')[0]
        self.assertEqual(r.body['url'],'https://example.test/a#b//c')
    def test_triple_quote_painless(self):
        r=parse_console('POST index/_update_by_query\n{"script":{"source":"""\nctx._source.x = "hello";\n// script comment\n"""}}')[0]
        self.assertIn('ctx._source.x = "hello";',r.body['script']['source'])
        self.assertIn('// script comment',r.body['script']['source'])
    def test_header_inside_script_not_split(self):
        self.assertEqual(len(parse_console('POST _scripts/a\n{"script":{"source":"""GET something\nPOST another"""}}\nGET index/_count')),2)
    def test_duplicate_key(self):
        with self.assertRaisesRegex(ConsoleError,'중복 JSON 키'):parse_console('PUT _ingest/pipeline/p\n{"processors":[{"rename":{},"rename":{}}]}')
    def test_bulk(self):
        r=parse_console('POST index/_bulk\n{"index":{"_id":"1"}}\n{"name":"검색"}')[0]
        self.assertEqual(r.content_type,'application/x-ndjson');self.assertTrue(r.raw_body.endswith('\n'))
        self.assertEqual(len(r.body),2)
    def test_remote_cluster_alias(self):
        r=parse_console('GET cluster2:blogs/_search')[0]
        self.assertEqual(r.path,'/cluster2:blogs/_search')
    def test_wildcard_remote(self):
        self.assertEqual(parse_console('GET local,APAC_*:blogs/_search')[0].path,'/local,APAC_*:blogs/_search')
    def test_unsafe_paths(self):
        for path in ('https://evil.test/a','//evil.test/a','/../foo','/%2e%2e/foo'):
            with self.subTest(path=path),self.assertRaises(ConsoleError):parse_console('GET '+path)
    def test_error_messages(self):
        for code in ('','curl localhost:9200','GET x\n{"a":1,}','GET x\nNaN','GET x\n{"a":"x}'):
            with self.subTest(code=code),self.assertRaises((ConsoleError,ValueError)):parse_console(code)
    def test_maximum_request_count(self):
        with self.assertRaises(ConsoleError):parse_console('\n'.join('GET /' for _ in range(101)))
    def test_enrich_put_is_accepted(self):
        self.assertEqual(parse_console('PUT _enrich/policy/p/_execute')[0].method,'PUT')
    def test_head_delete_no_body(self):
        r=parse_console('HEAD task2\nDELETE task2')
        self.assertIsNone(r[0].body);self.assertEqual(r[1].path,'/task2')

class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog=json.loads((ROOT/'data/catalog.json').read_text())
    def test_question_counts(self):
        tasks=self.catalog['tasks'];self.assertEqual(len(tasks),60)
        self.assertEqual([s['id'] for s in self.catalog['sets']],list('ABCDEF'))
        for set_id in 'ABCDEF':self.assertEqual(len([t for t in tasks if t['set']==set_id]),10)
    def test_all_reference_solutions_parse(self):
        for t in self.catalog['tasks']:
            with self.subTest(id=t['id']):self.assertTrue(parse_console(t['solution']))
    def test_unique_ids(self):
        self.assertEqual(len({t['id'] for t in self.catalog['tasks']}),60)
    def test_source_pdfs_exist(self):
        for t in self.catalog['tasks']:
            with self.subTest(id=t['id']):
                if t['source']['url'].startswith('/sources/'):
                    self.assertTrue((ROOT/'sources'/t['source']['document']).exists())
                else:self.assertTrue(t['source']['url'].startswith('https://www.elastic.co/'))
    def test_reconstruction_labels(self):
        for t in self.catalog['tasks']:
            if t['set']=='C':self.assertTrue(t['reconstructed']);self.assertTrue(t['notes'])
    def test_fixture_counts(self):
        self.assertEqual(len(FIX),22);self.assertEqual(sum(len(f['documents']) for f in FIX),1585)
    def test_unique_fixture_doc_ids(self):
        for f in FIX:self.assertEqual(len({d['_id'] for d in f['documents']}),len(f['documents']))
    def test_referenced_datasets_exist(self):
        from lab import F_FIX
        names={f['index'] for f in FIX+F_FIX}
        for t in self.catalog['tasks']:
            for name in t['datasets']:self.assertIn(name.split(':')[-1],names)
    def fixture(self,name):return next(x for x in FIX if x['index']==name)['documents']
    def test_boundaries_and_paginations(self):
        stocks=self.fixture('stock-prices');diffs={round(x['_source']['closing-price']-x['_source']['opening-price'],2) for x in stocks}
        self.assertTrue({-5,0,5}.issubset(diffs))
        movies=self.fixture('movie_data');profit={x['_source']['revenue']-x['_source']['budget'] for x in movies}
        self.assertTrue({0,1000000}.issubset(profit))
        self.assertGreaterEqual(sum('star' in x['_source']['title'].lower() for x in movies),20)
        self.assertGreaterEqual(sum('repair' in x['_source']['item'].lower() for x in self.fixture('inspections')),30)
    def test_missing_reference_values(self):
        blogs=self.fixture('blogs');self.assertTrue(any('category' not in x['_source'] for x in blogs))
    def test_primary_count_one_for_aggregations(self):
        self.assertEqual(next(f for f in FIX if f['index']=='flights')['settings']['number_of_shards'],1)

class CheckHelperTests(unittest.TestCase):
    def test_aggregation_names_are_ignored(self):
        a={'a':{'buckets':[{'key':1,'doc_count':2,'average':{'value':3.5}}]}}
        b={'x':{'buckets':[{'key':1,'key_as_string':'date','doc_count':2,'b':{'value':3.5}}]}}
        self.assertEqual(canon_agg(a),canon_agg(b))
    def test_float_tolerance(self):self.assertTrue(equivalent(1.0,1.00000001));self.assertFalse(equivalent(1.0,1.1))
    def test_duration(self):self.assertEqual(duration('3m'),180);self.assertEqual(duration('180s'),180)
    def test_sort_defaults(self):self.assertEqual(sort_spec({'sort':['_score','_doc']}),[('_score','desc'),('_doc','asc')])

class OwnershipTests(unittest.TestCase):
    def test_refuses_wrong_cluster(self):
        class Wrong:
            expected={'cluster1':'ece-lab-cluster1'}
            def require(self,*a,**k):return {'cluster_name':'production'}
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(RuntimeError,'안전장치'):
            Lab(Wrong(),Path(d)).owned('cluster1',allow_empty=True)
    def test_refuses_unmarked_nonempty_cluster(self):
        class Nonempty:
            expected={'cluster1':'ece-lab-cluster1'}
            def get(self,*a,**k):return {'status':404,'body':{}}
            def require(self,c,m,p,*a,**k):return {'cluster_name':'ece-lab-cluster1'} if p=='/' else [{'index':'important'}]
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(RuntimeError,'기존 인덱스'):
            Lab(Nonempty(),Path(d)).owned('cluster1',allow_empty=True)

class HTTPContractTests(unittest.TestCase):
    """A fake upstream validates proxy behavior, NOT Elasticsearch semantics."""
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();os.environ['LAB_STATE_DIR']=cls.temp.name
        import server
        cls.module=server;server.db_init();server.LAB.update(phase='ready',active_set='A',generation=1)
        class FakeUpstream:
            def call(self,cluster,method,path,body=None,**kwargs):
                return {'status':400 if path=='/fail' else 200,'body':{'test_mock':True,'cluster':cluster,'method':method,'path':path,'received':body},'elapsed_ms':1,'warnings':[]}
        cls.original=server.CLIENT;server.CLIENT=FakeUpstream()
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.port=cls.http.server_address[1]
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.module.CLIENT=cls.original;cls.temp.cleanup()
    def request(self,path,body=None,headers=None):
        h={'Content-Type':'application/json','X-Lab-Request':'1'};h.update(headers or {})
        req=HTTPRequest(f'http://127.0.0.1:{self.port}{path}',data=None if body is None else json.dumps(body).encode(),headers=h)
        try:
            with urlopen(req) as res:return res.status,res.read()
        except HTTPError as e:return e.code,e.read()
    def post(self,path,body,headers=None):
        status,data=self.request(path,body,headers);return status,json.loads(data)
    def payload(self,code,**kw):return dict(task_id='A01',cluster='cluster1',session='unit-tests',code=code,**kw)
    def test_catalog_does_not_ship_solutions(self):
        status,data=self.request('/api/catalog');self.assertEqual(status,200)
        self.assertNotIn('solution',json.loads(data)['tasks'][0])
    def test_selected_cluster_routing(self):
        payload=self.payload('GET blogs/_mapping');payload['cluster']='cluster2'
        status,data=self.post('/api/execute',payload);self.assertEqual(status,200);self.assertEqual(data['results'][0]['body']['cluster'],'cluster2')
    def test_stop_on_upstream_error(self):
        _,data=self.post('/api/execute',self.payload('GET /fail\nGET /later'))
        self.assertEqual(data['requested'],2);self.assertEqual(data['executed'],1)
    def test_json_error_no_upstream_call(self):
        code='PUT index\n{"x":1,"x":2}';status,data=self.post('/api/execute',self.payload(code))
        self.assertEqual(status,400);self.assertIn('중복',data['error'])
    def test_cross_origin_blocked(self):
        status,_=self.post('/api/execute',self.payload('GET /'),{'Origin':'https://evil.test'})
        self.assertEqual(status,403)
    def test_control_index_protected(self):
        _,data=self.post('/api/execute',self.payload('DELETE ece-lab-control'))
        self.assertEqual(data['results'][0]['status'],403)
    def test_global_delete_protected(self):
        _,data=self.post('/api/execute',self.payload('DELETE *'))
        self.assertEqual(data['results'][0]['status'],403)
    def test_wrong_set_rejected(self):
        p=self.payload('GET /');p['task_id']='B01';status,_=self.post('/api/execute',p);self.assertEqual(status,409)
    def test_history_persists(self):
        self.post('/api/execute',self.payload('GET /history-example'))
        status,data=self.post('/api/history',self.payload(''))
        self.assertEqual(status,200);self.assertTrue(any(e['request']['path']=='/history-example' for e in data['events']))
    def test_reset_confirmation_required(self):
        status,_=self.post('/api/reset',{'set':'A'});self.assertEqual(status,400)
    def test_source_pdf_served(self):
        status,data=self.request('/sources/recall-2026-02-26.pdf')
        self.assertEqual(status,200);self.assertTrue(data.startswith(b'%PDF'))

if __name__=='__main__':unittest.main(verbosity=2)
