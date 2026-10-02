"""Protect existing sets and verify F-only preparation and Kibana transport."""
import hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from elastic import Elastic
from lab import FIX,F_FIX,fixtures_for_set
from console import parse_console

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class SetIntegrationTests(unittest.TestCase):
    def test_existing_questions_preserved(self):
        current=json.loads((ROOT/'data/catalog.json').read_text())
        self.assertEqual(digest(current['tasks'][:50]),'d131e6fc3bae6529907b85a236dfc2833079f3166c766f6c598502d6d1434bc6')
        self.assertEqual([s['id'] for s in current['sets']],list('ABCDEF'))
        self.assertEqual(len(current['tasks']),60)
    def test_f_fixtures_only_in_f_set(self):
        self.assertTrue(F_FIX)
        for set_id in 'ABCD':self.assertEqual(fixtures_for_set(set_id),FIX)
        self.assertEqual(fixtures_for_set('F'),FIX+F_FIX)
        self.assertEqual({(x['cluster'],x['index']) for x in FIX}&{(x['cluster'],x['index']) for x in F_FIX},set())
        self.assertEqual(json.loads((ROOT/'data/fixtures.json').read_text())['seed_version'],2)
        self.assertEqual(digest(FIX),'8f6dba65ee67984586d60008120c5ff160b1f7fbe72441431575a9af9dec8ca6')
    def test_all_new_solutions_parse_and_have_detailed_requirements(self):
        tasks=json.loads((ROOT/'data/catalog.json').read_text())['tasks'][50:]
        for task in tasks:
            with self.subTest(task=task['id']):
                self.assertTrue(parse_console(task['solution']))
                self.assertGreaterEqual(len(task['requirements']),4)
                self.assertTrue(task['source']['url'].startswith('https://www.elastic.co/'))
                self.assertTrue(task['check'].startswith('f_'))
    def test_kibana_console_path_supported(self):
        request=parse_console('PUT kbn:/api/streams/logs-f-parse-default/_ingest\n{"test":true}')[0]
        self.assertEqual(request.path,'/kbn:/api/streams/logs-f-parse-default/_ingest')
    def test_fixed_kibana_transport_has_base_path_and_xsrf(self):
        client=Elastic()
        with patch.object(client,'_http',return_value={'status':200,'body':{}}) as request:
            client.kibana('cluster1','GET','/api/streams/f-test')
            args,kwargs=request.call_args
            self.assertEqual(args[0],client.kibana_urls['cluster1'])
            self.assertEqual(args[2],'/kibana1/api/streams/f-test')
            self.assertEqual(kwargs['extra_headers'],{'kbn-xsrf':'ece-exam-lab'})
    def test_kibana_rejects_non_api_target(self):
        client=Elastic()
        with self.assertRaises(ValueError):client.kibana('cluster1','GET','https://outside.invalid/')
        with self.assertRaises(ValueError):client.kibana('cluster1','GET','/app/streams')
        with self.assertRaises(ValueError):client.kibana('other','GET','/api/streams')

if __name__=='__main__':unittest.main()
