"""Deterministic practice fixtures; never claimed to be actual exam documents."""
from pathlib import Path
import json, random
from generate import generate, entry, text
ROOT=Path(__file__).resolve().parent

def generate_v2():
    result=generate()
    rng=random.Random(20260919)
    articles=[]
    for i in range(480):
        v=[rng.randint(-8,18) for _ in range(6)]
        if not any(v):v[0]=1
        if i<32:
            # Near neighbors, both allowed and disallowed by tags, make pre-filter relevant.
            v=[10+i%3,3+(i//3)%3,5,4,1+(i//9),2]
        title=(f'To the cloud and reliable systems {i}' if i<357 else f'Reliable distributed platforms {i}')
        body=('kubernetes platform operations and search' if i%3 else 'database storage and analytics')
        tags=['devops' if i%4 else 'observability']
        if i%5<3:tags.append('term')
        stamp=f'{2012 if i<240 else 2015}-{1+i%12:02d}-{1+(i//12)%27:02d}T{(i//27)%24:02d}:{i%60:02d}:00Z'
        articles.append({'article_id':f'art-{i+1:04d}','title':title,'body':body,
                         'category':['platform','search','data'][i%3], 'tags':tags,
                         'featured':i%7==0,'@timestamp':stamp,'date_time':stamp,
                         'region':['us-northest','kr-central','eu-west'][i%3],
                         'vector':{'cosine':v},'a':round(10+(i%23)*1.25,2),'b':100+(i*37)%997})
    props={'article_id':text(),'title':text(),'body':text(),'category':{'type':'keyword'},
           'tags':{'type':'keyword'},'featured':{'type':'boolean'},'@timestamp':{'type':'date'},
           'date_time':{'type':'date'},'region':{'type':'keyword'},'a':{'type':'double'},'b':{'type':'long'},
           'vector':{'properties':{'cosine':{'type':'dense_vector','dims':6,'index':True,
                                          'similarity':'cosine','index_options':{'type':'hnsw'}}}}}
    art=entry('article',props,articles)
    art['settings']['index.mapping.exclude_source_vectors']=False
    result.append(art)
    result.append(entry('regions',{'region_id':{'type':'keyword'},'region_name':{'type':'keyword'},
                                   'description':{'type':'text'}},[
        {'region_id':'us-northest','region_name':'US','description':'Northeastern United States — synthetic lookup'},
        {'region_id':'kr-central','region_name':'KR','description':'Central Korea — synthetic lookup'},
        {'region_id':'eu-west','region_name':'EU','description':'Western Europe — synthetic lookup'}]))
    # D09 intentionally starts empty; no initial properties or document insertion.
    blank=entry('ingest-logs',{},[])
    blank['mappings']={}
    result.append(blank)
    return result

if __name__=='__main__':
    data=generate_v2()
    (ROOT/'fixtures.json').write_text(json.dumps({'synthetic':True,'seed_version':2,'indices':data},ensure_ascii=False,indent=2))
    print('indices',len(data),'documents',sum(len(x['documents']) for x in data))
