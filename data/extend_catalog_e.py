"""Append exactly one 10-task practice set from the user-provided ECE PDF."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
cat=json.loads((ROOT/'catalog.json').read_text())
tasks=[]
def rq(method,path,body=None):
    return method+' '+path+('\n'+json.dumps(body,ensure_ascii=False,indent=2) if body is not None else '')
def join(*parts):return '\n\n'.join(parts)
def task(n,title,topic,requirements,pages,solution,check,*,datasets=(),notes=(),hint='',kind='state'):
    tasks.append(dict(id=f'E{n:02d}',set='E',number=n,title=title,topic=topic,
        requirements=requirements,source={'document':'ece-practice-exam.pdf','pages':pages,
        'label':f'ECE Practice Exam · Task {n}','url':f'/sources/ece-practice-exam.pdf#page={pages[0]}'},
        cluster='cluster1',datasets=list(datasets),notes=list(notes),hint=hint,solution=solution,
        kind=kind,check=check,answer='',intro='첨부 ECE Practice Exam의 조건을 현재 Docker 실습 환경에 맞춘 문항입니다.',reconstructed=False))

task(1,'사용자와 Default 공간 권한','Security · Role · Kibana',[
    'cluster1에 task1 사용자를 생성하고 클러스터 전체 권한을 부여한다.',
    '모든 일반 인덱스에는 읽기 전용 권한을, task1 인덱스에는 전체 권한을 부여한다.',
    'Kibana Default 공간의 모든 기능에 전체 권한을 부여한다.',
    'full_name은 Elastic Search, email은 elastic@search.com, password는 youknowforsearch로 설정한다.'],[4,5],join(
    rq('PUT','_security/role/task1_role',{'cluster':['all'],'indices':[{'names':['*'],'privileges':['read']},{'names':['task1'],'privileges':['all']}],
        'applications':[{'application':'kibana-.kibana','privileges':['space_all'],'resources':['space:default']}]}),
    rq('PUT','_security/user/task1',{'password':'youknowforsearch','roles':['task1_role'],'full_name':'Elastic Search','email':'elastic@search.com'}),
    rq('GET','_security/user/task1')),'e_security',notes=[
    '역할 이름은 원문의 예시처럼 task1_role을 사용한다. 같은 권한을 부여하는 다른 역할 이름도 가능하다.',
    'Kibana Stack Management → Roles/Users에서 구성할 수도 있다. Console 예시는 이 환경의 Kibana application privilege를 사용한다.',
    '보안 시스템 인덱스는 일반 인덱스와 다르다. 이 실습은 원문의 일반 인덱스 권한 범위를 검사한다.'],hint='클러스터, 인덱스, Kibana 공간 권한은 역할의 서로 다른 항목이다.')

yearly={'size':0,'query':{'match_phrase':{'content':'open source'}},'aggs':{'yearly':{'date_histogram':{'field':'publish_date','calendar_interval':'year'},'aggs':{'unique_authors':{'cardinality':{'field':'authors.uid'}}}}}}
task(2,'연도별 고유 저자 수','Phrase · Date histogram · Cardinality',[
    'blogs의 content에 open source가 이 순서의 구문으로 일치하는 문서만 검색한다.',
    'publish_date의 달력 연도별로 authors.uid의 고유한 저자 수를 구한다.',
    '개별 문서 hits는 반환하지 않는다.'],[5],rq('GET','blogs/_search',yearly),'e_yearly_authors',kind='query',datasets=['blogs'],notes=[
    'PDF 해설은 authors.uid.keyword를 사용하지만 기존 실습의 authors.uid는 이미 keyword 타입이므로 authors.uid를 집계한다.',
    '저자 배열의 고유 uid를 세며 블로그 문서 수를 세는 문제가 아니다.'],hint='match_phrase → calendar_interval:year → cardinality를 연도 버킷 안에 연결한다.')

blog_mapping={'dynamic_templates':[{'strings_as_keywords':{'match_mapping_type':'string','mapping':{'type':'keyword'}}}],
    'properties':{'authors':{'properties':{'full_name':{'type':'text','analyzer':'standard'}}},
    'content':{'type':'text','analyzer':'content_analyzer','fields':{'eng':{'type':'text','analyzer':'english'}}},
    'title':{'type':'text','analyzer':'standard','fields':{'search':{'type':'search_as_you_type'}}}}}
task(3,'블로그 분석기와 멀티필드','Analyzer · Dynamic template · Reindex',[
    'blogs의 모든 문서를 cluster1의 새 task3 인덱스로 재색인한다.',
    'content, title, authors.full_name을 제외한 문자열 필드는 keyword only로 매핑한다.',
    'authors.full_name과 title은 text이며 standard analyzer를 사용한다.',
    'content는 text이며 content_analyzer(html_strip character filter, standard tokenizer, lowercase token filter)를 사용한다.',
    'content.eng는 english analyzer를 사용하는 text, title.search는 search_as_you_type 멀티필드로 만든다.'],[5,6,7],join(
    rq('PUT','task3',{'settings':{'number_of_replicas':0,'analysis':{'analyzer':{'content_analyzer':{'type':'custom','char_filter':['html_strip'],'tokenizer':'standard','filter':['lowercase']}}}},'mappings':blog_mapping}),
    rq('POST','_reindex',{'source':{'index':'blogs'},'dest':{'index':'task3'}}),rq('GET','task3/_mapping')),'e_blog_mapping',datasets=['blogs'],notes=['문자열 필드는 Elasticsearch의 text/keyword 필드를 뜻한다. PDF 예시처럼 날짜 감지를 유지하므로 publish_date는 date로 매핑된다.'],hint='명시한 text 필드는 properties에 정의하고 나머지 새 문자열에는 dynamic_templates를 적용한다.')

traffic_pipeline={'processors':[{'remove':{'field':'is_https','ignore_missing':True}},
    {'rename':{'field':'geoip_location_lat','target_field':'geo.location.lat','ignore_missing':True}},
    {'rename':{'field':'geoip_location_lon','target_field':'geo.location.lon','ignore_missing':True}},
    {'user_agent':{'field':'user_Agent','ignore_missing':True}}, {'remove':{'field':'user_Agent','ignore_missing':True}}]}
traffic_mapping={'dynamic_templates':[{'strings_as_keywords':{'match_mapping_type':'string','mapping':{'type':'keyword'}}}],
    'properties':{'geo':{'properties':{'location':{'type':'geo_point'}}},'@timestamp':{'type':'date'},
    'runtime_ms':{'type':'long'},'bytes_sent':{'type':'long'},'response':{'type':'keyword'},
    'content_type':{'type':'keyword'},'request':{'type':'keyword'},'verb':{'type':'keyword'}}}
task(4,'웹 로그 정제와 위치 매핑','Ingest · User agent · Geo point',[
    'web_traffic을 새 task4 인덱스로 재색인하며 is_https를 제거한다.',
    'geoip_location_lat/lon을 geo.location.lat/lon으로 옮기고 geo.location을 geo_point로 매핑한다.',
    'user_Agent에 user_agent processor를 적용하고 원래 user_Agent 필드는 제거한다.',
    '@timestamp는 date, runtime_ms와 bytes_sent는 long, 나머지 값 필드는 keyword로 매핑한다.',
    'task4는 primary shard 6개, replica 0개를 사용한다.'],[7,8,9,10],join(
    rq('PUT','_ingest/pipeline/web_traffic_pipeline',traffic_pipeline),
    rq('PUT','task4',{'settings':{'number_of_shards':6,'number_of_replicas':0},'mappings':traffic_mapping}),
    rq('POST','_reindex',{'source':{'index':'web_traffic'},'dest':{'index':'task4','pipeline':'web_traffic_pipeline'}}),
    rq('GET','task4/_search',{'size':2})),'e_traffic',datasets=['web_traffic'],notes=[
    'PDF 해설의 매핑에는 JSON 쉼표 오류와 예시 로그에 없는 status_code/url이 있다. 실습은 실제 로그의 response/request와 문제의 타입 조건을 따른다.',
    'user_agent가 생성하는 객체의 문자열 값에도 keyword 동적 템플릿을 적용한다.'],hint='목적지 매핑을 먼저 만들고 reindex의 dest.pipeline에 정제 파이프라인을 지정한다.')

nested={'query':{'nested':{'path':'authors','query':{'bool':{'must':[{'match':{'authors.first_name':'david'}},{'match':{'authors.job_title':'engineer'}}]}}}}}
task(5,'동일 저자 객체의 이름과 직책','Nested · Reindex · Query',[
    'blogs의 모든 문서를 새 task5 인덱스로 재색인하고 authors를 nested로 매핑한다.',
    '같은 authors 객체에서 first_name이 david이고 job_title에 engineer 토큰이 포함된 블로그를 검색한다.'],[10,11],join(
    rq('PUT','task5',{'settings':{'number_of_replicas':0},'mappings':{'properties':{'authors':{'type':'nested'}}}}),
    rq('POST','_reindex',{'source':{'index':'blogs'},'dest':{'index':'task5'}}),rq('GET','task5/_search',nested)),
    'e_nested',kind='mixed',datasets=['blogs'],notes=[
    'PDF 본문은 task5를 생성하면서 검색 대상을 nested_authors라고 적고, 해설은 task5를 검색한다. 실습은 생성한 task5를 검색한다.',
    '본문의 first_name 조건을 따른다. PDF 해설은 full_name을 사용한다. 원본의 22건은 복원하지 않았으며 합성 데이터의 결과는 28건이다.'],hint='이름과 직책 조건을 같은 nested.query 안에 넣어 서로 다른 저자 사이의 거짓 일치를 제외한다.')

task(6,'카테고리 정보 보강','Enrich · Missing field · Reindex',[
    'blogs를 새 task6 인덱스로 재색인한다.',
    'blogs.category를 categories.uid에 매칭하여 categories 객체에 uid와 title을 추가한다.',
    '기존 category 필드를 제거하고 category가 없는 문서도 오류 없이 처리한다.',
    '나머지 필드와 모든 문서 ID를 유지한다.'],[11,12],join(
    rq('PUT','_enrich/policy/categories_policy',{'match':{'indices':'categories','match_field':'uid','enrich_fields':['title']}}),
    rq('POST','_enrich/policy/categories_policy/_execute'),
    rq('PUT','_ingest/pipeline/categories_pipeline',{'processors':[{'enrich':{'field':'category','policy_name':'categories_policy','target_field':'categories','ignore_missing':True}},{'remove':{'field':'category','ignore_missing':True}}]}),
    rq('POST','_reindex',{'source':{'index':'blogs'},'dest':{'index':'task6','pipeline':'categories_pipeline'}}),
    rq('GET','task6/_search',{'query':{'match':{'categories.title':'news'}}})),'e_categories',datasets=['blogs','categories'],notes=[
    'PDF의 News 537건은 원본 데이터 기준이다. 이 실습은 84건의 합성 blogs와 category 누락 문서를 사용한다.'],hint='policy 생성과 실행을 구분한다. enrich와 remove 모두 ignore_missing으로 누락된 category를 처리한다.')

task(7,'원격 블로그 인덱스 복제','Cross-cluster replication',[
    'cluster2의 blogs를 leader로 하여 cluster1에 ccr_blogs follower를 생성한다.',
    '복제는 active 상태여야 하며 7건의 문서가 동기화되어야 한다.'],[13,14],join(
    rq('GET','_remote/info'),rq('PUT','ccr_blogs/_ccr/follow?wait_for_active_shards=1',{'remote_cluster':'cluster2','leader_index':'blogs','settings':{'index.number_of_replicas':0}}),
    rq('GET','ccr_blogs/_ccr/info'),rq('GET','ccr_blogs/_count')),'e_ccr',datasets=['cluster2:blogs'],notes=[
    '기존 Docker 환경의 cluster2 연결을 사용하며 E 세트 초기화 때 cluster2에 합성 blogs 7건을 준비한다.',
    '일반 follow API는 복제를 시작한다. 이미 pause한 follower에만 resume_follow를 사용한다.',
    'CCR에는 유효한 라이선스가 필요하다. 이 Docker 환경은 기존 trial을 사용한다.'],hint='follower를 만들 요청은 cluster1 Console에서 실행한다.')

task(8,'시간 기반 메트릭 데이터 스트림','ILM · Component template · Data stream',[
    'cluster1에 my.metrics-system-dev 데이터 스트림을 생성한다.',
    'Hot에서 최대 2분에 rollover하고 rollover 직후 Warm에서 read-only로 만든다.',
    'rollover 후 3분에 Cold로 이동하며 삭제 단계 없이 유지한다.',
    'my-metrics-template 템플릿은 준비된 metrics-mappings component template과 my-metrics-policy를 사용한다.'],[14,15,16],join(
    rq('GET','_component_template/metrics-mappings'),
    rq('PUT','_ilm/policy/my-metrics-policy',{'policy':{'phases':{'hot':{'actions':{'rollover':{'max_age':'2m'}}},'warm':{'min_age':'0m','actions':{'readonly':{}}},'cold':{'min_age':'3m','actions':{}}}}}),
    rq('PUT','_index_template/my-metrics-template',{'index_patterns':['my.metrics-*-*'],'data_stream':{},'composed_of':['metrics-mappings'],'priority':500,'template':{'settings':{'index.lifecycle.name':'my-metrics-policy','number_of_shards':1,'number_of_replicas':0}}}),
    rq('PUT','_data_stream/my.metrics-system-dev')),'e_stream',notes=[
    'PDF 본문 metrics-mapping과 해설 metrics-mappings의 표기가 다르다. 실습에서 준비된 이름은 metrics-mappings다.',
    'PDF 템플릿 이름도 혼재하므로 my-metrics-template으로 통일한다. Cold min_age는 rollover 이후 기준이다.',
    '빈 스트림은 기본 ILM 설정에서 자동 rollover하지 않는다. 시간 전환을 관찰하려면 @timestamp가 있는 샘플 문서를 별도로 넣는다. 자동 검증은 정책·연결·스트림을 확인한다.'],hint='ILM 정책 → component를 포함한 index template → 실제 data stream 순서로 생성한다.')

task(9,'스냅샷 마운트와 검색','Repository · Searchable snapshot',[
    'cluster1에 이름이 snap-repo인 fs repository를 /mnt/elastic-snapshots/ece-practice-search에 등록한다.',
    '이미 준비된 moreblogs_snapshot에는 moreblogs만 있다. searchable snapshot으로 moreblogs를 마운트한다.',
    'moreblogs에서 tags.product에 elasticsearch가 일치하는 블로그를 검색한다.'],[16,17],join(
    rq('PUT','_snapshot/snap-repo',{'type':'fs','settings':{'location':'/mnt/elastic-snapshots/ece-practice-search'}}),
    rq('GET','_snapshot/snap-repo/moreblogs_snapshot'),
    rq('POST','_snapshot/snap-repo/moreblogs_snapshot/_mount?wait_for_completion=true',{'index':'moreblogs','index_settings':{'index.number_of_replicas':0}}),
    rq('GET','moreblogs/_search',{'query':{'match':{'tags.product':'elasticsearch'}}})),'e_searchable',kind='mixed',datasets=['moreblogs'],notes=[
    'PDF 경로 /var/tmp/repo/search는 현재 Docker의 path.repo에 맞춰 /mnt/elastic-snapshots/ece-practice-search로 변경했다.',
    'E 세트 초기화는 합성 moreblogs 24건의 실제 스냅샷을 준비한 뒤 원본 인덱스와 repository 등록을 제거한다. 저장된 스냅샷 파일을 다시 등록·마운트하는 문제다.',
    '합성 데이터에서 elasticsearch 매칭은 22건이다. searchable snapshots에는 유효한 라이선스가 필요하다.'],hint='일반 restore 대신 _mount를 사용한 뒤 마운트한 인덱스를 검색한다.')

certified={'from':10,'size':5,'query':{'bool':{'must':[{'match':{'content':'certified engineer'}}],
    'should':[{'match_phrase':{'content':'certified engineer'}}], 'filter':[{'range':{'publish_date':{'gte':'now-2y/d','lte':'now'}}}]}},
    'sort':[{'_score':'desc'},{'_doc':'asc'}],'highlight':{'fields':{'content':{}}}}
task(10,'최근 인증 관련 블로그와 페이징','Relevance · Date math · Highlight',[
    'blogs의 content에서 certified engineer를 검색한다. 기본 match OR 의미로 검색한다.',
    'content에 certified engineer가 이 순서의 구문으로 일치하면 점수를 추가한다.',
    '최근 2년부터 현재까지 발행된 블로그만 반환한다.',
    '_score 내림차순, 동률이면 _doc 오름차순으로 정렬한다.',
    '페이지당 5건인 3번째 페이지를 반환하고 content의 검색어를 highlight한다.'],[17,18],rq('GET','blogs/_search',certified),'e_certified',kind='query',datasets=['blogs'],notes=[
    'E 세트에서는 기존 blogs의 날짜 연도만 2025로 바꾼 별도 합성 fixture를 사용한다. 2026년 10월 기준 3번째 페이지가 존재하며 A–D 원본 fixture는 유지한다.',
    '최근 2년은 실행 시각을 기준으로 평가한다. 시간이 지나면 결과 수가 달라질 수 있다.',
    '_doc는 내부 문서 순서다. 자동 검증은 완전히 동률인 문서에 특정 ID 순서를 강제하지 않는다.'],hint='필수 match, 선택적 match_phrase, 날짜 filter를 나누고 from:10 / size:5를 사용한다.')

cat['tasks']=[t for t in cat['tasks'] if t['set']!='E']+tasks
cat['sets']=[s for s in cat['sets'] if s['id']!='E']+[{'id':'E','name':'E · ECE Practice Exam','description':'첨부 PDF 10문제 · 권한 / 로그 정제 / CCR / searchable snapshot','duration_minutes':180}]
(ROOT/'catalog.json').write_text(json.dumps(cat,ensure_ascii=False,indent=2)+'\n')
print('Catalog:',len(cat['sets']),'sets /',len(cat['tasks']),'tasks')
