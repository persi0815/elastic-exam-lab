"""Protect the old exams and the new exam's essential data preparation."""
import hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'data'))
from generate_e import extend,overrides

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class ExamDataTests(unittest.TestCase):
    def test_original_questions_preserved(self):
        tasks=json.loads((ROOT/'data/catalog.json').read_text())['tasks']
        self.assertEqual(digest(tasks[:40]),'9236483bcf95ff9d03c03f3df70fc8a67aab7b9dc6a64bda142c54cfdba513f0')
    def test_original_fixtures_preserved(self):
        fixtures=json.loads((ROOT/'data/fixtures.json').read_text())['indices']
        self.assertEqual(digest(fixtures[:19]),'323221377e1ccf109517408bf1b387c5ce636fc92194d1383282b7200e4e2eed')
    def test_extension_is_idempotent(self):
        fixtures=json.loads((ROOT/'data/fixtures.json').read_text())['indices']
        self.assertEqual(extend(fixtures),fixtures)
    def test_e_dates_do_not_change_old_blogs(self):
        fixtures=json.loads((ROOT/'data/fixtures.json').read_text())['indices']
        original=next(x for x in fixtures if x['cluster']=='cluster1' and x['index']=='blogs')
        updated=overrides(fixtures)[0]
        for old,new in zip(original['documents'],updated['documents']):
            a=dict(old['_source']);b=dict(new['_source'])
            self.assertTrue(a.pop('publish_date').startswith('2024-'))
            self.assertTrue(b.pop('publish_date').startswith('2025-'))
            self.assertEqual(a,b)
    def test_snapshot_has_positive_and_negative_products(self):
        fixtures=json.loads((ROOT/'data/fixtures.json').read_text())['indices']
        docs=next(x['documents'] for x in fixtures if x['index']=='moreblogs')
        self.assertEqual(len(docs),24)
        self.assertEqual(sum(x['_source']['tags']['product'].lower()=='elasticsearch' for x in docs),22)

if __name__=='__main__':unittest.main()
