"""Offline browser DOM regression: API, storage, cookie jar, iframe are TEST DOUBLES.
This test does NOT execute genuine Kibana, ES, browser authentication or Docker.
HTTP proxy tests are separate in test_v2.py. Run: python tests/ui_smoke.py
"""
from pathlib import Path
import json,os
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
CAT=json.loads((ROOT/'data/catalog.json').read_text());FIX=json.loads((ROOT/'data/fixtures.json').read_text())['indices']
html=(ROOT/'web/index.html').read_text().replace('<script defer src="/app.js"></script>','').replace('<link rel="stylesheet" href="/style.css">','<style>'+(ROOT/'web/style.css').read_text()+'</style>')
mock=r'''
window.__calls=[];window.__cookies={};window.confirm=()=>true;
Object.defineProperty(window,'localStorage',{value:{getItem:k=>__store[k]||null,setItem:(k,v)=>__store[k]=v}});
Object.defineProperty(document,'cookie',{get:()=>Object.entries(__cookies).map(([k,v])=>k+'='+v).join('; '),set:v=>{let p=v.split(';')[0];__cookies[p.slice(0,p.indexOf('='))]=p.slice(p.indexOf('=')+1);}});
Object.defineProperty(HTMLIFrameElement.prototype,'src',{get(){return this.getAttribute('src')||''},set(v){this.setAttribute('data-test-url',v);this.srcdoc='<html><body><h2>TEST DOUBLE — NOT REAL KIBANA</h2><p>Only shell navigation is being tested.</p><textarea id="test-input"></textarea></body></html>';}});
// Preserve getAttribute(src) for the shell's navigation guard without making network requests.
const nativeGet=Element.prototype.getAttribute;
Element.prototype.getAttribute=function(k){return this.tagName==='IFRAME'&&k==='src'?nativeGet.call(this,'data-test-url'):nativeGet.call(this,k)};
window.__lab={phase:'ready',active_set:'D',message:'화면 테스트 · 실제 Elasticsearch 미연결',generation:1};window.__nativeReady=true;
window.fetch=async(path,opts={})=>{
 const body=opts.body?JSON.parse(opts.body):{};__calls.push({path,body});let data={};
 if(path==='/api/catalog')data={...__cat,tasks:__cat.tasks.map(({solution,answer,...t})=>t)};
 else if(path==='/api/status')data={lab:__lab,engine_version:'9.3.8',clusters:{cluster1:{connected:__nativeReady,health:'test-double'},cluster2:{connected:__nativeReady,health:'test-double'}},kibana:{cluster1:{connected:__nativeReady,error:'제작 환경에서 Docker 미실행 — 화면만 확인'},cluster2:{connected:__nativeReady,error:'제작 환경에서 Docker 미실행 — 화면만 확인'}}};
 else if(path==='/api/reset'){__lab={...__lab,active_set:body.set};data={started:true};}
 else if(path==='/api/history')data={events:[{request:{method:'GET',path:'/article/_search',body:{query:{match_all:{}}},source:'kibana-console'},status:200,cluster:'cluster1',timestamp:1,elapsed_ms:1}]};
 else if(path==='/api/check')data={complete:true,passed:1,total:1,checks:[{label:'TEST DOUBLE — 실제 검색 검증 아님',ok:true}],notice:'테스트 모의 응답'};
 else if(path==='/api/datasets')data={indices:__fix.map(f=>({cluster:f.cluster,index:f.index,count:f.documents.length}))};
 else if(path.startsWith('/api/solution/'))data=__cat.tasks.find(t=>t.id===path.split('/').pop());
 return {ok:true,status:200,json:async()=>data};
};
URL.createObjectURL=blob=>{window.__export=blob;return 'blob:test'};URL.revokeObjectURL=()=>{};
const clickAnchor=HTMLAnchorElement.prototype.click;
HTMLAnchorElement.prototype.click=function(){if(this.download){window.__downloadName=this.download;return;}clickAnchor.call(this);};
'''
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
    errors=[]
    def new_page(store=None):
        page=browser.new_page(viewport={'width':1680,'height':1050});page.on('pageerror',lambda e:errors.append(str(e)))
        page.set_content(html);page.evaluate('(x)=>{window.__cat=x.cat;window.__fix=x.fix;window.__store=x.store}',{'cat':CAT,'fix':FIX,'store':store or {}})
        page.add_script_tag(content=mock);page.add_script_tag(content=(ROOT/'web/app.js').read_text());page.wait_for_selector('.task-button');page.wait_for_selector('#kibanaFrame1:not([hidden])');return page
    page=new_page()
    assert page.locator('.task-button').count()==10 and page.locator('#setSelect option').count()==6
    assert page.locator('#taskTitle').inner_text()=='필터를 적용한 kNN 검색'
    page.frame_locator('#kibanaFrame1').locator('#test-input').fill('request preserved')
    page.locator('[data-task="D02"]').click();assert page.frame_locator('#kibanaFrame1').locator('#test-input').input_value()=='request preserved'
    assert page.evaluate('__cookies.ece_task_cluster1')=='D02'
    page.locator('[data-task="D04"]').click();page.wait_for_selector('#kibanaFrame2:not([hidden])')
    assert page.locator('[data-cluster="cluster2"]').evaluate('(e)=>e.classList.contains("active")')
    page.locator('[data-task="D05"]').click();page.locator('#sourceNotes').evaluate('(e)=>e.open=true');assert 'Task7' in page.locator('#notes').inner_text()
    page.locator('#notebookBtn').click();page.locator('#notebook').fill('GET article/_search\n{"size":10}')
    store=page.evaluate('__store');page.close();page=new_page(store);page.locator('#notebookBtn').click()
    assert page.locator('#notebook').input_value()=='GET article/_search\n{"size":10}'
    page.locator('#clearAnswerBtn').click();page.locator('#captureBtn').click();page.wait_for_function('document.getElementById("notebook").value.includes("match_all")')
    page.locator('#checkBtn').click();page.wait_for_selector('.grade-total');assert '1 / 1' in page.locator('.grade-total').inner_text()
    assert page.evaluate("__calls.filter(x=>x.path==='/api/check').at(-1).body.task_id")=='D05'
    page.locator('#dataBtn').click();assert page.locator('#modal tbody tr').count()==22;page.locator('#modalClose').click()
    page.locator('#drawerClose').click();page.locator('#hintBtn').click();assert page.locator('#hint').is_visible()
    page.locator('#solutionBtn').click();assert '_index_template/task5' in page.locator('#modalBody').inner_text();page.locator('#modalClose').click()
    page.locator('#examBtn').click();assert page.locator('#checkBtn').is_disabled() and page.locator('#hint').is_hidden()
    page.locator('#examBtn').click();assert page.locator('#hintBtn').is_enabled() and page.locator('#checkBtn').is_enabled()
    page.locator('#setSelect').select_option('A');page.locator('#resetConfirm').fill('RESET LAB');page.locator('#modalFooter button').filter(has_text='초기화 실행').click()
    page.wait_for_selector('[data-task="A01"]');assert page.evaluate("__calls.filter(x=>x.path==='/api/reset').at(-1).body.set")=='A'
    page.evaluate('pollStatus()');page.wait_for_selector('#checkBtn:not([disabled])')
    page.locator('#exportBtn').click();page.wait_for_function('!!window.__downloadName');assert page.evaluate('__downloadName').startswith('ece-answers-A')
    assert json.loads(page.evaluate('__export.text()'))['version']==2
    page.locator('#collapseBtn').click();assert page.locator('.workspace').evaluate('(e)=>e.classList.contains("collapsed")');page.locator('#collapseBtn').click()
    for w,h in [(1680,1050),(1440,900),(1280,800),(1024,768)]:
        page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(50)
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),f'overflow {w}'
        box=page.locator('#kibanaFrame1').bounding_box();assert box['width']>400 and box['height']>250,(w,box)
    assert not errors,errors
    page.locator('#setSelect').select_option('E');page.locator('#resetConfirm').fill('RESET LAB');page.locator('#modalFooter button').filter(has_text='초기화 실행').click()
    page.wait_for_selector('[data-task="E01"]');page.evaluate('pollStatus()')
    assert page.locator('.task-button').count()==10
    assert page.locator('#taskTitle').inner_text()=='사용자와 Default 공간 권한'
    page.locator('[data-task="E09"]').click();assert page.locator('#sourceLink').get_attribute('href').endswith('ece-practice-exam.pdf#page=16')
    page.locator('#solutionBtn').click();assert 'moreblogs_snapshot/_mount' in page.locator('#modalBody').inner_text();page.locator('#modalClose').click()
    page.locator('#setSelect').select_option('F');page.locator('#resetConfirm').fill('RESET LAB');page.locator('#modalFooter button').filter(has_text='초기화 실행').click()
    page.wait_for_selector('[data-task="F01"]');page.evaluate('pollStatus()')
    assert page.locator('.task-button').count()==10
    for task in [t for t in CAT['tasks'] if t['set']=='F']:
        page.locator('[data-task="'+task['id']+'"]').click()
        assert page.locator('#taskTitle').inner_text()==task['title']
        assert page.locator('#requirements li').count()==len(task['requirements'])
        assert page.locator('#sourceLink').get_attribute('href').startswith('https://www.elastic.co/')
    page.locator('#solutionBtn').click();assert 'failure_store' in page.locator('#modalBody').inner_text();page.locator('#modalClose').click()
    assert not errors,errors
    # Screenshot accurately shows a pending real Kibana, NEVER a mock success/editor.
    page.evaluate("__lab.active_set='D';__nativeReady=false;state.set='D';state.taskId='D01';initialSync=false;renderTask();pollStatus();")
    page.wait_for_selector('#loadingConsole:not([hidden])');page.set_viewport_size({'width':1680,'height':1050});page.wait_for_timeout(50)
    out=ROOT/'tests/artifacts';out.mkdir(exist_ok=True);page.screenshot(path=str(out/'shell-preview.png'),full_page=True)
    (out/'ui-report.json').write_text(json.dumps({'passed':True,'scope':'Offline problem-shell DOM. APIs, storage, cookies, and iframe are TEST DOUBLES. Genuine Kibana, Elasticsearch, browser authentication and Docker were NOT run.','checks':['6 sets / 60 tasks','E selection / 10 tasks / PDF / mount solution','F selection / all 10 requirements / documentation / Streams solution','iframe navigation and persistence','context-cookie construction','source conflict notes','notebook serialization/reload','history import','grading display','22 base fixture entries','hint/solution modal','exam lock/unlock including validation button','set reset confirmation','answer export serialization','pane collapse','4 desktop viewport sizes','no JavaScript page errors'],'errors':errors},ensure_ascii=False,indent=2))
    browser.close();print('UI smoke PASS — offline shell + TEST DOUBLES; not live Kibana/ES.')
