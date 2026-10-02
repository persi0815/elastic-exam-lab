'use strict';
// Problem shell only. The editor and results are supplied by the REAL Kibana iframe.
const $ = id => document.getElementById(id);
const STORE = 'elastic-exam-lab:v2';
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let previous = {};
try { previous = JSON.parse(localStorage.getItem(STORE) || '{}'); } catch {}
const state = {session:previous.session || globalThis.crypto?.randomUUID?.() || `session-${Date.now()}`, set:previous.set || 'D', taskId:previous.taskId || 'D01', tasks:previous.tasks || {}, exams:previous.exams || {}, width:previous.width || 360};
let catalog, serverStatus, busy = false, selectedCluster = 'cluster1', statusRunning = false, initialSync = false;
let activePanel = 'validation', lastEvents = [], historyTask = null;
const record = (id=state.taskId) => state.tasks[id] || (state.tasks[id] = {code:'',answer:'',cluster:null,flag:false,grade:null});
const current = () => catalog?.tasks.find(t => t.id === state.taskId);
function save() { try { localStorage.setItem(STORE, JSON.stringify(state)); } catch { toast('브라우저 저장 공간이 부족합니다. 답안을 내보내세요.', true); } }
function toast(message,error=false) { $('toast').textContent=message; $('toast').classList.toggle('error',error); $('toast').hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('toast').hidden=true,5000); }
async function api(path,body) {
  const res=await fetch(path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Request':'1'},body:JSON.stringify(body)});
  const data=await res.json(); if(!res.ok)throw new Error(typeof data.error==='string'?data.error:`HTTP ${res.status}`); return data;
}
function context() {
  // Cookies are consumed only by the local proxy to associate actual Console requests.
  document.cookie=`ece_session=${encodeURIComponent(state.session)}; Path=/; SameSite=Strict`;
  for(const c of ['cluster1','cluster2']) document.cookie=`ece_task_${c}=${state.taskId}; Path=/; SameSite=Strict`;
}
function examActive() { const e=state.exams[state.set]; return !!(e?.deadline&&!e.finished&&e.deadline>Date.now()); }
function ready() { return serverStatus?.lab?.phase==='ready' && serverStatus.lab.active_set===state.set; }
function controls() {
  $('checkBtn').disabled=busy||!ready()||examActive();
  $('setSelect').disabled=busy||['starting','seeding'].includes(serverStatus?.lab?.phase);
  $('resetBtn').disabled=busy||['starting','seeding'].includes(serverStatus?.lab?.phase);
  $('hintBtn').disabled=examActive(); $('solutionBtn').disabled=examActive();
  $('examBtn').textContent=examActive()?'시험 종료':'시험 시작'; $('modeLabel').textContent=examActive()?'시험 모드 · 힌트/검증 잠금':'연습 모드';
}
function renderNav() {
  const tasks=catalog.tasks.filter(t=>t.set===state.set);
  $('progressLabel').textContent=`${tasks.filter(t=>record(t.id).grade?.complete).length} / ${tasks.length}`;
  $('taskNav').innerHTML=tasks.map(t=>`<button class="task-button ${t.id===state.taskId?'active':''} ${record(t.id).grade?.complete?'done':''} ${record(t.id).flag?'flagged':''}" data-task="${t.id}" title="${esc(t.title)}" aria-label="${t.number}번 ${esc(t.title)}">${String(t.number).padStart(2,'0')}</button>`).join('');
  $('taskNav').querySelectorAll('button').forEach(b=>b.onclick=()=>selectTask(b.dataset.task));
}
function selectTask(id) {
  if(!catalog.tasks.some(t=>t.id===id))return;
  state.taskId=id; state.set=current().set; lastEvents=[]; historyTask=null;
  renderTask(); save();
}
function renderTask() {
  const t=current(),r=record(); if(!t)return;
  $('setSelect').value=state.set; $('taskNo').textContent=`TASK ${String(t.number).padStart(2,'0')} / 10`;
  $('taskTitle').textContent=t.title; $('topic').textContent=t.topic; $('taskCluster').textContent=t.cluster;
  $('kind').textContent={query:'검색 요청',text:'텍스트 답안',mixed:'상태 + 검색',state:'클러스터 상태'}[t.kind]||t.kind;
  $('intro').textContent=t.intro||'';
  $('requirements').innerHTML=t.requirements.map(s=>`<li>${esc(s)}</li>`).join('');
  $('datasets').innerHTML=t.datasets.map(d=>`<button data-index="${esc(d)}" title="매핑 확인 요청 복사">${esc(d)} ↗</button>`).join('');
  $('datasets').querySelectorAll('button').forEach(b=>b.onclick=()=>copy(`GET ${b.dataset.index}/_mapping`));
  $('notes').innerHTML=t.notes.map(n=>`<p>${esc(n)}</p>`).join(''); $('noteCount').textContent=`(${t.notes.length})`;
  $('sourceNotes').open=false; $('sourceNotes').hidden=!t.notes.length;
  $('sourceLink').href=t.source.url; $('sourceLink').textContent=t.source.label+(t.source.pages?.length?` · p.${t.source.pages.join(', ')}`:'')+' ↗';
  $('textAnswerBlock').hidden=t.kind!=='text'; $('textAnswer').value=r.answer||'';
  $('notebook').value=r.code||''; $('hint').hidden=true;
  $('flagBtn').textContent=r.flag?'⚑ 표시됨':'⚑ 다시 보기'; $('nextBtn').textContent=t.number===10?'첫 문제로 ↻':'다음 문제 →';
  selectedCluster=r.cluster||t.cluster; context(); renderNav(); renderGrade(); renderConsole(); controls();
  if(!$('drawer').hidden&&activePanel==='history')loadHistory();
}
function consoleUrl(c=selectedCluster) { return `/kibana${c==='cluster1'?1:2}/app/dev_tools#/console`; }
function renderConsole(force=false) {
  const health=serverStatus?.kibana?.[selectedCluster];
  document.querySelectorAll('[data-cluster]').forEach(b=>b.classList.toggle('active',b.dataset.cluster===selectedCluster));
  $('openConsole').href=consoleUrl();
  for(const [i,c] of ['cluster1','cluster2'].entries()) {
    const frame=$('kibanaFrame'+(i+1)),active=c===selectedCluster;
    frame.hidden=!active||!health?.connected;
    if(active&&health?.connected&&(!frame.getAttribute('src')||force))frame.src=consoleUrl(c);
  }
  $('loadingConsole').hidden=!!health?.connected;
  $('kibanaStatus').textContent=health?.connected?'':health?.error?`${selectedCluster} Kibana 연결 대기 · ${health.error}`:`${selectedCluster} Kibana가 시작 중입니다. 첫 기동에는 몇 분이 걸릴 수 있습니다.`;
}
async function pollStatus() {
  if(statusRunning)return; statusRunning=true;
  try {
    serverStatus=await api('/api/status');
    const lab=serverStatus.lab;
    $('statusText').textContent=lab.error?`${lab.message}: ${lab.error}`:lab.message;
    $('statusbar').className='statusbar '+(lab.phase==='ready'?'ready':lab.phase==='error'?'error':'');
    $('engineHealth').textContent=['cluster1','cluster2'].map(c=>`${c}: ${serverStatus.clusters[c]?.connected?serverStatus.clusters[c].health:'연결 대기'}`).join('  ·  ');
    if(!initialSync&&catalog&&lab.phase==='ready') {
      initialSync=true;
      if(lab.active_set!==state.set){state.set=lab.active_set;state.taskId=state.set+'01';renderTask();save();}
    }
    $('version').textContent=`ES / Kibana ${serverStatus.engine_version}`;
    renderConsole(); controls();
  } catch(e) {$('statusbar').className='statusbar error';$('statusText').textContent=`실습 서버에 연결하지 못했습니다: ${e.message}`;}
  finally {statusRunning=false;}
}
function renderGrade() {
  const g=record().grade;
  $('validationPanel').innerHTML=g?`<div class="grade-total">${g.passed} / ${g.total} 조건 통과</div>`+g.checks.map(x=>`<div class="check-row"><span class="${x.ok?'yes':'no'}">${x.ok?'✓':'×'}</span><div>${esc(x.label)}${x.detail?`<small>${esc(x.detail)}</small>`:''}</div></div>`).join('')+`<p class="muted">${esc(g.notice||'비공식 연습용 검증입니다.')}</p>`:'<p class="muted">Console에서 요청을 실행한 다음 답안 검증을 누르세요. 공식 채점기는 아닙니다.</p>';
}
function panel(name) {
  activePanel=name; $('drawer').hidden=false;
  for(const p of ['validation','history','notebook'])$(p+'Panel').hidden=p!==name;
  document.querySelectorAll('[data-panel]').forEach(b=>b.classList.toggle('active',b.dataset.panel===name));
  if(name==='history')loadHistory();
}
function payload() {return {session:state.session,task_id:state.taskId,cluster:selectedCluster};}
function requestText(q) {
  const raw=q.raw_body?.trim();
  const body=raw || (q.body===null||q.body===undefined?'':typeof q.body==='string'?q.body:JSON.stringify(q.body,null,2));
  return `${q.method} ${q.path}\n${body}`.trim();
}
async function loadHistory() {
  const id=state.taskId;
  try {
    const data=await api('/api/history',payload()); if(id!==state.taskId)return [];
    lastEvents=data.events||[]; historyTask=id;
    $('captureState').textContent=`${id} · 실제 Console/보조 실행 기록 ${lastEvents.length}개`;
    $('historyPanel').innerHTML=lastEvents.length?lastEvents.slice().reverse().map((e,i)=>`<div class="history-item"><strong>${esc(e.cluster)} · HTTP ${e.status}</strong> <span class="muted">${new Date(e.timestamp*1000).toLocaleTimeString()} · ${e.elapsed_ms} ms</span><pre>${esc(requestText(e.request))}</pre><button data-copy-event="${lastEvents.length-1-i}">요청 복사</button></div>`).join(''):'<p class="muted">현재 문항에서 수집된 실행 기록이 없습니다. 이 페이지의 Console에서 실행하세요. 별도 포트의 Kibana에서 실행한 요청은 자동 수집되지 않습니다. 그 경우 최종 답안 보관에 쿼리를 붙여 넣으면 검증할 수 있습니다.</p>';
    $('historyPanel').querySelectorAll('[data-copy-event]').forEach(b=>b.onclick=()=>copy(requestText(lastEvents[+b.dataset.copyEvent].request)));
    return lastEvents;
  } catch(e) {$('historyPanel').textContent=e.message; return [];}
}
async function check() {
  if(!ready()||busy||examActive())return;
  busy=true;controls();panel('validation');$('validationPanel').textContent='Elasticsearch의 실제 상태와 검색 결과를 확인하고 있습니다…';
  const id=state.taskId;
  try {const g=await api('/api/check',{...payload(),code:record().code||'',answer:record().answer||''});record(id).grade=g;save();if(id===state.taskId)renderGrade();renderNav();}
  catch(e){$('validationPanel').innerHTML=`<p class="warning">${esc(e.message)}</p>`;}
  finally{busy=false;controls();}
}
function modal(title,html,buttons=[]) {
  $('modalTitle').textContent=title;$('modalBody').innerHTML=html;$('modalFooter').innerHTML='';
  for(const b of buttons){const el=document.createElement('button');el.textContent=b.label;el.className=b.primary?'primary':'';el.onclick=b.click;$('modalFooter').appendChild(el);}
  if(!$('modal').open)$('modal').showModal();
}
async function copy(text) {try{await navigator.clipboard.writeText(text);toast('복사했습니다. Console에 붙여 넣으세요.');}catch{modal('복사할 텍스트',`<pre>${esc(text)}</pre>`,[{label:'닫기',click:()=>$('modal').close()}]);}}
async function solution() {
  if(examActive())return;const t=current();
  try{const d=await api('/api/solution/'+t.id);modal(t.id+' · 예시 풀이',`<p class="warning">이 실습 데이터에 맞춘 예시입니다. 정답이 한 가지뿐이라는 뜻은 아닙니다. 새 인덱스를 만드는 요청은 이미 실행했으면 충돌할 수 있습니다.</p><pre>${esc(d.solution)}</pre>${d.answer?`<p>텍스트 답안: ${esc(d.answer)}</p>`:''}`,[{label:'풀이 복사',primary:true,click:()=>copy(d.solution)},{label:'닫기',click:()=>$('modal').close()}]);}catch(e){toast(e.message,true);}
}
async function reset(setId=state.set) {
  const old=state.set;
  modal('세트 변경 / 실습 환경 초기화',`<p class="warning">전용 실습 클러스터 두 개의 사용자 인덱스·정책·파이프라인과 현재 풀이 결과를 삭제하고 합성 데이터를 다시 넣습니다. 브라우저에 보관한 답안 코드는 유지합니다.</p><p>선택할 세트: <strong>${esc(catalog.sets.find(s=>s.id===setId)?.name)}</strong></p><p>진행하려면 아래에 <code>RESET LAB</code>를 입력하세요.</p><input id="resetConfirm" placeholder="RESET LAB" autocomplete="off">`,[{label:'취소',click:()=>{$('setSelect').value=old;$('modal').close();}},{label:'초기화 실행',primary:true,click:async()=>{
    if($('resetConfirm').value!=='RESET LAB'){toast('RESET LAB을 정확히 입력하세요.',true);return;}
    try{await api('/api/reset',{confirmation:'RESET LAB',set:setId});state.set=setId;state.taskId=setId+'01';Object.values(state.tasks).forEach(r=>r.grade=null);state.exams[setId]={};initialSync=false;serverStatus.lab.phase='seeding';renderTask();save();$('modal').close();toast('초기화를 시작했습니다. 상단 상태를 확인하세요.');pollStatus();}
    catch(e){toast(e.message,true);$('setSelect').value=old;}
  }}]);
}
function tick() {
  const e=state.exams[state.set];let seconds=10800;
  if(e?.deadline)seconds=Math.max(0,Math.ceil(((e.finished||Date.now())>e.deadline?0:e.deadline-(e.finished||Date.now()))/1000));
  if(e?.deadline&&!e.finished&&seconds===0){e.finished=Date.now();save();toast('180분이 종료되었습니다. 답안을 내보내고 복습하세요.');controls();}
  $('timer').textContent=[Math.floor(seconds/3600),Math.floor(seconds%3600/60),seconds%60].map(v=>String(v).padStart(2,'0')).join(':');
}
function toggleExam() {
  if(examActive()){if(!confirm('시험을 종료하고 힌트와 검증을 다시 켤까요?'))return;state.exams[state.set].finished=Date.now();}
  else {if(!confirm('180분 시험을 시작합니다. 문제나 클러스터 데이터는 초기화하지 않고 힌트·예시 풀이·검증을 잠급니다.'))return;state.exams[state.set]={deadline:Date.now()+10800000};$('hint').hidden=true;$('drawer').hidden=true;}
  save();tick();controls();
}
async function exportAnswers() {
  await loadHistory();
  if(historyTask===state.taskId&&lastEvents.length)record().captured=lastEvents;
  const blob=new Blob([JSON.stringify({format:'ece-lab-answers',version:2,exported_at:new Date().toISOString(),...state},null,2)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`ece-answers-${state.set}-${new Date().toISOString().slice(0,10)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);toast('문항별 보관 답안과 현재 문항 실행 기록을 내보냈습니다.');
}
async function datasets() {
  try{const d=await api('/api/datasets');modal('준비된 데이터셋',`<p>모든 문서는 실습용 합성 데이터입니다. article의 title에 to가 매칭되는 문서는 357건이며 ingest-logs는 의도적으로 비어 있습니다. region은 regions의 alias입니다. E 세트의 moreblogs는 스냅샷에 준비되며 마운트 후 조회할 수 있습니다. 아래 건수는 준비된 fixture 기준입니다.</p><table><thead><tr><th>클러스터</th><th>인덱스</th><th>문서</th><th>확인 요청</th></tr></thead><tbody>${d.indices.map((x,i)=>`<tr><td>${x.cluster}</td><td>${esc(x.index)}</td><td>${x.count}</td><td><button data-dataset="${i}">매핑 복사</button></td></tr>`).join('')}</tbody></table>`,[{label:'닫기',click:()=>$('modal').close()}]);$('modalBody').querySelectorAll('[data-dataset]').forEach(b=>b.onclick=()=>copy(`GET ${d.indices[+b.dataset.dataset].index}/_mapping`));}catch(e){toast(e.message,true);}
}
function guide() {
  modal('실제 Kibana Console 사용 안내',`<h3>편집기와 결과는 진짜 Kibana입니다</h3><p>오른쪽은 Docker의 Kibana Dev Tools를 그대로 표시합니다. 자동완성, 여러 요청, 주석, 실행 버튼, 단축키, 응답 JSON은 Kibana가 처리합니다. Ctrl/Cmd + Enter는 현재 요청 실행, Ctrl/Cmd + I는 자동 정렬입니다.</p><h3>문제와 실행 기록</h3><p>Console은 클러스터별 작업장이라 문항을 이동해도 입력이 지워지지 않습니다. 실행 시 현재 선택한 문항에 요청 기록이 연결됩니다. 필요한 최종 스크립트는 하단 ‘문항별 답안·실행 기록 → 최종 답안 보관’에 붙여 넣으세요. 보관 답안이 있으면 검증은 그 답안을 우선합니다.</p><h3>실행되지 않을 때</h3><p>상단에서 해당 Kibana가 준비되었는지 확인하고 ↻ 또는 별도 창을 누르세요. <code>docker compose ps</code>와 <code>docker compose logs --tail=100 kibana1 kibana2 app</code>으로 확인할 수 있습니다. Docker 메모리는 이 구성에서 12GB 할당을 권장합니다.</p><h3>주의</h3><p>클러스터는 로컬 실습 전용이며 익명 접속이 실습 관리자 권한을 사용합니다. 외부 네트워크에 공개하거나 실제 업무 클러스터와 연결하면 안 됩니다. 세트 변경은 클러스터 상태를 초기화합니다.</p><p>이전 v1 답안 JSON도 가져올 수 있습니다. 기본 화면은 실제 Kibana이고, <a href="/legacy.html" target="_blank" rel="noopener">간단한 텍스트 보조 콘솔</a>은 진단용입니다.</p>`,[{label:'답안 가져오기',click:()=>$('importFile').click()},{label:'닫기',click:()=>$('modal').close()}]);
}
function bind() {
  $('modalClose').onclick=()=>$('modal').close();$('setSelect').onchange=()=>{const s=$('setSelect').value;if(s!==state.set){$('setSelect').value=state.set;reset(s);}};
  $('resetBtn').onclick=()=>reset();$('checkBtn').onclick=check;$('solutionBtn').onclick=solution;
  $('hintBtn').onclick=()=>{if(examActive())return;$('hint').textContent=current().hint;$('hint').hidden=!$('hint').hidden;};
  $('flagBtn').onclick=()=>{record().flag=!record().flag;renderNav();$('flagBtn').textContent=record().flag?'⚑ 표시됨':'⚑ 다시 보기';save();};
  $('nextBtn').onclick=()=>selectTask(state.set+String(current().number%10+1).padStart(2,'0'));
  $('textAnswer').oninput=()=>{record().answer=$('textAnswer').value;save();};
  $('notebook').oninput=()=>{record().code=$('notebook').value;record().grade=null;save();};
  document.querySelectorAll('[data-cluster]').forEach(b=>b.onclick=()=>{selectedCluster=b.dataset.cluster;record().cluster=selectedCluster;context();renderConsole();save();});
  $('reloadBtn').onclick=()=>{renderConsole(true);pollStatus();};$('collapseBtn').onclick=()=>document.querySelector('.workspace').classList.toggle('collapsed');
  $('notebookBtn').onclick=()=>panel('notebook');$('drawerClose').onclick=()=>$('drawer').hidden=true;
  document.querySelectorAll('[data-panel]').forEach(b=>b.onclick=()=>panel(b.dataset.panel));
  $('captureBtn').onclick=async()=>{const events=await loadHistory();if(!events.length)return toast('아직 실행 기록이 없습니다.',true);record().code=events.map(e=>`// ${e.cluster} · HTTP ${e.status}\n${requestText(e.request)}`).join('\n\n');$('notebook').value=record().code;save();toast('실행 기록을 보관했습니다. 불필요한 요청은 지우세요.');};
  $('copyAnswerBtn').onclick=()=>copy($('notebook').value);$('clearAnswerBtn').onclick=()=>{record().code='';$('notebook').value='';save();toast('검증에 마지막 실행 요청을 사용합니다.');};
  $('guideBtn').onclick=guide;$('dataBtn').onclick=datasets;$('exportBtn').onclick=exportAnswers;$('examBtn').onclick=toggleExam;
  $('importFile').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;const data=JSON.parse(await file.text());const imported=data.state?.tasks||data.tasks;if(!imported||typeof imported!=='object')throw Error('지원하는 답안 JSON이 아닙니다.');for(const [id,r]of Object.entries(imported))if(catalog.tasks.some(t=>t.id===id)&&r&&typeof r==='object')state.tasks[id]={...r,grade:null};save();renderTask();toast('답안을 가져왔습니다. 클러스터 데이터는 변경하지 않았습니다.');$('modal').close();}catch(e){toast(e.message,true);}finally{$('importFile').value='';}};
  $('resizer').onpointerdown=e=>{if(document.querySelector('.workspace').classList.contains('collapsed'))return;document.body.classList.add('resizing');$('resizer').setPointerCapture(e.pointerId);};
  $('resizer').onpointermove=e=>{if(!document.body.classList.contains('resizing'))return;state.width=Math.max(260,Math.min(innerWidth-480,e.clientX));document.documentElement.style.setProperty('--question-width',state.width+'px');};
  $('resizer').onpointerup=()=>{document.body.classList.remove('resizing');save();};
  $('resizer').onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();state.width=Math.max(260,Math.min(innerWidth-480,state.width+(e.key==='ArrowRight'?20:-20)));document.documentElement.style.setProperty('--question-width',state.width+'px');save();}};
}
async function init() {
  bind();
  try {
    catalog=await api('/api/catalog');$('setSelect').innerHTML=catalog.sets.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');
    if(!catalog.tasks.some(t=>t.id===state.taskId)){state.set=catalog.default_set||'D';state.taskId=state.set+'01';}
    document.documentElement.style.setProperty('--question-width',state.width+'px');renderTask();await pollStatus();
    setInterval(pollStatus,7000);setInterval(tick,1000);tick();
  }catch(e){$('statusText').textContent=`문제 로딩 실패: ${e.message}`;$('statusbar').className='statusbar error';$('kibanaStatus').textContent='ZIP 안의 HTML을 직접 열지 말고 docker compose up 후 localhost:8787에 접속하세요.';}
}
init();
