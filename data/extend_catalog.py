"""Add source-labelled September recollection. Run after build_catalog.py."""
from pathlib import Path
import copy,json
ROOT=Path(__file__).resolve().parent
cat=json.loads((ROOT/'catalog.json').read_text())
fix=json.loads((ROOT/'fixtures.json').read_text())['indices']
base={t['id']:t for t in cat['tasks']}
def rq(method,path,body=None):return method+' '+path+('\n'+json.dumps(body,ensure_ascii=False,indent=2) if body is not None else '')
def join(*x):return '\n\n'.join(x)
def make(n,title,topic,req,notes,solution,check,kind='state',cluster='cluster1',datasets=('article',)):
    return dict(id=f'D{n:02d}',set='D',number=n,title=title,topic=topic,requirements=req,notes=notes,
                source={'document':'recall-2026-09-19.md','pages':[], 'label':f'사용자 제공 2026.09.19 회고 · #{n}',
                        'url':'/sources/recall-2026-09-19.md'},cluster=cluster,datasets=list(datasets),
                hint='',solution=solution,kind=kind,check=check,answer='',intro='9.X 회고 기반. 실제 시험 데이터가 아닌 재현용 합성 데이터입니다.',reconstructed=True)
D=[]
knn={'size':10,'_source':['title','category'],'query':{'knn':{'field':'vector.cosine','query_vector':[10,3,5,4,1,2],
     'k':10,'num_candidates':100,'filter':{'term':{'tags':'term'}}}}}
D.append(make(1,'필터를 적용한 kNN 검색','kNN · Pre-filter · Source filtering',[
'article의 vector.cosine에서 query vector [10, 3, 5, 4, 1, 2]에 가장 가까운 10개 문서를 검색한다.',
'KNN Query 내부의 filter를 사용해 tags에 term 값이 있는 문서만 대상으로 한다.',
'반환하는 문서 필드는 title과 category만 포함한다.'],[
'회고는 벡터 필드명을 완전히 제공하지 않았다. vector.cosine, 6차원, cosine similarity로 실습 규격을 명시했다.',
'회고의 “term”은 이 세트에서 tags의 리터럴 값으로 해석한다. “의미”는 제공 벡터의 유사도로만 계산하며 ML 모델로 만든 임베딩이 아니다.',
'회고의 “fields만 반환”은 _source 필터링 또는 _source:false + fields 둘 다 허용한다. _id/_index/_score 같은 응답 메타데이터는 제외 대상이 아니다.'],rq('GET','article/_search',knn),'knn',kind='query'))
D[-1]['hint']='vector 매핑을 확인하고 query.knn의 filter 안에 tags 조건을 둔다. size와 k는 서로 다른 옵션이다.'
D.append(make(2,'지역 참조 정보를 객체로 추가','Enrich · Reindex',[
'article을 task2에 reindex하면서 article.region과 regions.region_id를 매칭한다.',
'일치하는 region_id, region_name, description을 region_info 객체에 추가한다.',
'기존 region과 나머지 원본 필드는 유지한다.'],[
'원문에 region 인덱스와 regions 인덱스가 혼재한다. 실습 인덱스는 regions로 통일하고 region이라는 검색 alias도 제공한다.',
'결과 인덱스명은 원문에서 확인되지 않으므로 task2로 지정했다. ignore_missing 처리는 연습 편의를 위한 방어 코드이며 원문 요구로 단정하지 않는다.',
'Enrich는 매 문서마다 live 원본 index를 join하는 것이 아니라 policy execute로 생성한 enrich index를 조회한다.'],join(
 rq('PUT','_enrich/policy/d-region-policy',{'match':{'indices':'regions','match_field':'region_id','enrich_fields':['region_name','description']}}),
 rq('PUT','_enrich/policy/d-region-policy/_execute'),
 rq('PUT','_ingest/pipeline/d-region-pipeline',{'processors':[{'enrich':{'policy_name':'d-region-policy','field':'region','target_field':'region_info','ignore_missing':True}}]}),
 rq('PUT','task2',{'settings':{'number_of_replicas':0,'index.mapping.exclude_source_vectors':False},'mappings':copy.deepcopy(next(x['mappings'] for x in fix if x['index']=='article'))}),
 rq('POST','_reindex',{'source':{'index':'article'},'dest':{'index':'task2','pipeline':'d-region-pipeline'}})
),'article_enrich',datasets=('article','regions')))
D[-1]['hint']='match_field는 참조 인덱스의 region_id, processor.field는 입력 문서의 region이다. region_info에는 match_field도 함께 들어간다.'
p=copy.deepcopy(next(x['mappings'] for x in fix if x['index']=='article'))
p['properties']['title']={'type':'text','analyzer':'article_stop_analyzer'}
p['properties']['article_id']={'type':'keyword'}
D.append(make(3,'기사 매핑과 세 불용어','Analyzer · Mapping · Reindex',[
'article의 모든 문서를 task3에 reindex한다. title은 text only, article_id는 keyword only다.',
'title 검색에서 to, the, and를 불용어로 처리한다. 다른 필드의 mapping과 데이터는 유지한다.',
'초기 article에서 title에 to를 match 검색하면 357건, task3에서는 0건이어야 한다.'],[
'원문에 적힌 357 hits를 재현하도록 480개 합성 문서 중 정확히 357개 title에 to를 넣었다. 실제 시험 데이터가 아니다.',
'vector.cosine도 “나머지 매핑”에 포함된다. 원본 _mapping을 조회해서 복사한 뒤 두 필드만 수정한다.'],join(
 rq('GET','article/_mapping'),rq('PUT','task3',{'settings':{'number_of_replicas':0,'index.mapping.exclude_source_vectors':False,
 'analysis':{'analyzer':{'article_stop_analyzer':{'type':'custom','tokenizer':'standard','filter':['lowercase','article_stop']}},
             'filter':{'article_stop':{'type':'stop','stopwords':['to','the','and']}}}},'mappings':p}),
 rq('POST','_reindex',{'source':{'index':'article'},'dest':{'index':'task3'}}),
 rq('GET','task3/_search',{'query':{'match':{'title':'to'}}})
),'article_stop'))
D[-1]['hint']='keyword multi-field만 지우는 것이 아니라 title 자체의 analyzer를 바꿔야 한다. _analyze로 세 단어가 모두 사라지는지 확인한다.'
b=copy.deepcopy(base['B06'])
D.append(make(4,'매시간 Snapshot Lifecycle Policy','SLM · Repository',b['requirements'],[
'사용자 회고가 2026.04.14 Task6과 동일하다고 참조하므로, 원문대로 policy 이름은 task6, 대상은 cluster2의 listings2로 유지했다.',*b['notes']],b['solution'],'slm',cluster='cluster2',datasets=('listings2',)))
D[-1]['hint']=b['hint']
b=copy.deepcopy(base['B08'])
req=[x.replace('task8','task5') for x in b['requirements']]
D.append(make(5,'데이터 스트림과 backing index 매핑','Data stream · Index template',req,[
'회고에는 “Data stream 생성 = 4/14 Task7”이라고 쓰여 있지만 첨부 PDF의 Task7은 집계, Task8이 Data Stream이다.',
'여기서는 회고의 주제(Data stream)를 따라 4/14 Task8을 실습용으로 연결했다. 번호 불일치를 원문 수정 사실처럼 취급하지 않는다.',
'원문 누락 패턴과 이름은 mymetrics-*-*, task5, mymetrics-system-prod로 실습 규격을 지정했다.'],b['solution'].replace('_index_template/task8','_index_template/task5'),'d_metrics',datasets=()))
D[-1]['hint']=b['hint']
b=copy.deepcopy(base['B05'])
D.append(make(6,'세 필드의 구문 검색','Multi match · Phrase',b['requirements'],[
'“4/14 Task5와 동일”이라는 명시적 참조를 우선해 food-ingredients/name/brand/manufacturer 및 potato chips를 유지했다.',
'“대부분 article 사용”이라는 총평만으로 이 문제까지 article로 바꾸지 않았다.'],b['solution'],'phrase',kind='query',datasets=('food-ingredients',)))
D[-1]['hint']=b['hint']
qb={'from':19,'size':5,'track_scores':True,'query':{'bool':{'must':[{'match':{'body':'kubernetes'}}],
 'filter':[{'term':{'tags':'devops'}}],'should':[{'term':{'featured':True}}],'minimum_should_match':0}},
 'sort':[{'date_time':'desc'}]}
D.append(make(7,'필수 검색·필터·선택 가산점','Bool · Score · Pagination',[
'article.body에 kubernetes가 필수로 매칭되고 그 조건은 점수에도 반영된다.',
'같은 문서의 tags에는 devops가 필수로 포함되지만 이 조건은 점수에 반영하지 않는다.',
'featured:true이면 점수를 추가하되 false인 문서도 필수 조건을 만족하면 검색된다.',
'date_time 내림차순 정렬 후 20번째 문서부터 5개를 반환한다. 실습에서는 1부터 센 20번째이므로 from:19로 정의한다.'],[
'회고는 “20번 문서부터”라고만 써서 from:19/from:20 해석이 갈린다. UI와 검증은 20번째 포함(from:19)으로 명시했다.',
'date_time 정렬 방향은 회고에 없어서 실습에서는 desc를 선택했다. 실제 시험 방향을 확인했다는 의미는 아니다.',
'날짜 정렬이 우선이므로 featured 가산점이 날짜 정렬을 앞지를 필요는 없다. track_scores:true는 점수를 관찰하기 위한 예시이며 필수 채점 조건은 아니다.'],rq('GET','article/_search',qb),'article_bool',kind='query'))
D[-1]['hint']='must(match) + filter(term) + should(term). “선택적 가산점”을 minimum_should_match:1로 바꾸지 않는다.'
b=copy.deepcopy(base['B10'])
D.append(make(8,'OR 검색과 선택적 Boosting','Bool · Boosting',b['requirements'],[
'“4/14 Task10과 동일”을 그대로 따라 movie_data/title/me my/tags/romantic comedy를 유지했다. 임의로 article로 치환하지 않았다.',*b['notes']],b['solution'],'boost',kind='query',datasets=('movie_data',)))
D[-1]['hint']=b['hint']
grok='^HTTP %{NUMBER:response_status} ABC %{NUMBER:duration_ms}$'
pipeline={'processors':[{'grok':{'field':'message','patterns':[grok]}},
 {'convert':{'field':'duration_ms','type':'integer'}},
 {'date':{'field':'raw_time','target_field':'@timestamp','formats':['ISO8601']}},
 {'remove':{'field':'raw_time'}}]}
doc={'message':'HTTP 200 ABC 125','raw_time':'2015-12-31T00:00:00Z'}
D.append(make(9,'빈 인덱스에 기본 Pipeline 연결','Grok · Convert · Date · Default pipeline',[
'ingest-logs는 이미 존재하며 문서 0건, properties 없는 상태가 정상이다. 삭제하거나 재생성하지 않는다.',
'이름이 task9인 ingest pipeline을 만들고 ingest-logs의 index.default_pipeline으로 설정한다.',
'message 패턴 HTTP <status> ABC <duration>에서 response_status와 duration_ms를 grok으로 추출한다.',
'convert processor로 duration_ms를 integer로 변환한다. 인덱스의 duration_ms 매핑도 integer로 명시한다.',
'raw_time의 ISO8601 값을 date processor로 파싱하여 @timestamp에 저장하고 원본 raw_time은 제거한다. @timestamp 매핑은 date다.',
'pipeline을 명시하지 않은 색인 요청으로 샘플 {"message":"HTTP 200 ABC 125","raw_time":"2015-12-31T00:00:00Z"}를 넣어 기본 pipeline의 적용을 확인한다.'],[
'원문에서 주어진 인덱스명이 빠져 있어 ingest-logs로 보완했다. 초기 mapping/documents는 정말 비어 있다.',
'원문 grok은 %{??:duration_ms}로 불완전하고 response_stauts 오타가 있다. 실습 규격은 NUMBER:duration_ms, response_status로 명시했다.',
'raw_time 포맷도 생략되어 있어 ISO8601로 지정했다. duration_ms mapping integer 요구와 검증용 샘플은 실습을 위한 보완이다.',
'회고의 “빈 인덱스이므로 _simulate가 동작하지 않음”은 일반 API 제약이 아니다. _simulate는 docs에 직접 제공한 샘플로 실행 가능하다. 이 문제는 실제 색인으로 default pipeline 연결까지 검증한다.'],join(
 rq('GET','ingest-logs/_mapping'),rq('GET','ingest-logs/_count'),
 rq('PUT','_ingest/pipeline/task9',pipeline),
 rq('PUT','ingest-logs/_mapping',{'properties':{'duration_ms':{'type':'integer'},'@timestamp':{'type':'date'}}}),
 rq('PUT','ingest-logs/_settings',{'index.default_pipeline':'task9'}),
 rq('POST','_ingest/pipeline/task9/_simulate',{'docs':[{'_source':doc}]}),
 rq('POST','ingest-logs/_doc?refresh=true',doc),rq('GET','ingest-logs/_search')
),'default_pipeline',datasets=('ingest-logs',)))
D[-1]['hint']='pipeline을 만드는 것과 index.default_pipeline 설정은 별개다. 빈 인덱스에도 PUT index/_mapping과 PUT index/_settings를 사용할 수 있다.'
agg={'size':0,'query':{'range':{'@timestamp':{'gte':'2012-01-01','lt':'2013-01-01'}}},
 'aggs':{'months':{'date_histogram':{'field':'@timestamp','calendar_interval':'month'},
 'aggs':{'avg_a':{'avg':{'field':'a'}},'max_b':{'max':{'field':'b'}}}}}}
D.append(make(10,'월별 평균과 최댓값','Date histogram · AVG · MAX',[
'article에서 2012년 데이터를 대상으로 월별 집계를 수행한다.',
'각 월에서 a의 평균과 b의 최댓값을 각각 반환한다. 개별 hits는 반환하지 않는다.'],[
'회고는 4/14 Task7과 동일하되 AVG(a), MAX(b)로 변경되었다고만 적었다. a와 b의 실제 필드명은 제공되지 않았다.',
'실습은 “대부분 article” 설명을 적용해 article에 숫자 필드 a/b, 날짜 @timestamp를 만들었다. 2012년 제한은 참조한 4/14 Task7에서 가져왔다. 실제 시험의 인덱스/날짜 필드명을 확정한 것이 아니다.'],rq('GET','article/_search',agg),'monthly',kind='query'))
D[-1]['hint']='같은 date_histogram 버킷의 하위에 avg와 max를 형제 집계로 둔다.'
cat['tasks']=[t for t in cat['tasks'] if t['set']!='D']+D
cat['engine_version']='9.3.8'
cat['version']='2.0.0'
cat['default_set']='D'
cat['sets']=[s for s in cat['sets'] if s['id']!='D']+[{'id':'D','name':'D · 2026.09.19 · 9.X 회고',
    'description':'10문제 · kNN / article / 기본 pipeline 추가 · 누락 조건 공개','duration_minutes':180}]
cat['references']=[{'title':'Kibana Console','url':'https://www.elastic.co/docs/explore-analyze/query-filter/tools/console'},
 {'title':'kNN query','url':'https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-knn-query'},
 {'title':'Kibana authentication','url':'https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/kibana-authentication'},
 {'title':'Simulate pipeline','url':'https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-ingest-simulate'}]
(ROOT/'catalog.json').write_text(json.dumps(cat,ensure_ascii=False,indent=2))
print('questions',len(cat['tasks']))

# Keep corpus metadata in sync with the extension.
cat['disclaimer'] = '첨부 회고에 기반한 비공식 로컬 실습 도구. 원본 시험 데이터나 공식 채점기는 포함하지 않습니다. 1,530건은 합성 데이터이고 누락 조건을 명시적으로 보완했습니다. 최신 공식 범위 전체를 나타내지는 않습니다.'
(ROOT/'catalog.json').write_text(json.dumps(cat,ensure_ascii=False,indent=2), encoding='utf-8')
