'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {unreviewed:'미검토',confirmed:'실제 결함',false_positive:'오탐',deferred:'판단 보류',open:'미처리',in_progress:'진행 중',fixed:'수정 완료',verified:'검증 완료',completed:'정상 완료',failed:'실패',cancelled:'중단'};
const badge = v => `<span class="badge ${esc(v)}">${esc(labels[v] || v)}</span>`;
const date = v => v ? new Date(v).toLocaleString('ko-KR') : '—';
let scope = {}, page = 1, groupPage = 1, query = '', mode = 'all', current = null, generation = 0;
let actor = localStorage.getItem('defectActor') || '';
const api = async (path, options={}) => {
  const res = await fetch(path, {...options, headers:{'X-Requested-With':'DefectHub', ...(options.headers || {})}});
  if (!res.ok) { let msg; try { const err=await res.json(); msg=typeof err.detail==='string'?err.detail:JSON.stringify(err.detail); } catch { msg=`HTTP ${res.status}`; } throw new Error(msg); }
  return res.json();
};
const params = extra => new URLSearchParams({...scope,...extra}).toString();
const notice = error => { $('#message').hidden=false; $('#message').textContent=error.message || error; };
const guard = fn => (...args) => {try {return Promise.resolve(fn(...args)).catch(notice);} catch(e) {notice(e);} };
const table = (heads, rows) => `<div class="table-wrap"><table><thead><tr>${heads.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
function remember(value) { actor=value.trim();localStorage.setItem('defectActor',actor); }
function setScope(next) { scope=next;page=1;groupPage=1;query='';history.replaceState(null,'',location.pathname);render(); }
function breadcrumbs(extra='') {
  const items=[['전체',{}]];let next={};
  for(const key of ['release','branch','part','cl']) if(scope[key]) {next={...next,[key]:scope[key]};items.push([key==='cl'?`CL ${scope[key]}`:scope[key],{...next}]);}
  $('#breadcrumbs').innerHTML=items.map(([name],i)=>`<button data-crumb="${i}">${esc(name)}</button>`).join('<span>/</span>')+(extra?`<span>/</span><span>${esc(extra)}</span>`:'');
  document.querySelectorAll('[data-crumb]').forEach(b=>b.onclick=()=>setScope(items[Number(b.dataset.crumb)][1]));
}
async function render() {
  const epoch=++generation; current=null;$('#message').hidden=true;breadcrumbs();
  const level=!scope.release?'release':!scope.branch?'branch':!scope.part?'part':'cl';
  $('#content').innerHTML='<div class="empty">결과를 불러오는 중…</div>';
  try {
    const [groups,runs,stats]=await Promise.all([api('/api/groups?'+params({level,page:groupPage})),api('/api/runs?'+params({page,q:query})),api('/api/stats?'+params({mode}))]);
    if(epoch!==generation)return;
    $('#navigation').innerHTML=groups.map((g,i)=>`<button class="navbutton" data-group="${i}">${esc(level==='cl'?'CL '+g.name:g.name)}<small>${g.runs}회 실행 · ${g.findings} Findings</small></button>`).join('')+`<div class="pagination"><button id="group-prev" ${groupPage===1?'disabled':''} aria-label="탐색 목록 이전">‹</button><small>${groupPage}</small><button id="group-next" ${groups.length<200?'disabled':''} aria-label="탐색 목록 다음">›</button></div>`;
    $('#group-prev').onclick=()=>{groupPage--;render();};$('#group-next').onclick=()=>{groupPage++;render();};
    const navigationScope={...scope};
    document.querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>setScope({...navigationScope,[level]:groups[Number(b.dataset.group)].name}));
    const total=stats.items.reduce((a,r)=>{for(const k of ['runs','completed','failed','findings','confirmed','false_positive','unreviewed','deferred'])a[k]=(a[k]||0)+r[k];return a;},{});
    const decided=(total.confirmed||0)+(total.false_positive||0), rate=decided?((total.false_positive||0)/decided*100).toFixed(1)+'%':'—';
    const title=scope.cl?'CL '+scope.cl:scope.part||[scope.release,scope.branch].filter(Boolean).join(' ')||'전체 검사 결과';
    $('#content').innerHTML=`<div class="title-row"><div><div class="eyebrow">DEFECT WORKSPACE</div><h1>${esc(title)}</h1><p class="muted">변경 코드 검사 결과와 팀의 검토 현황을 확인하세요.</p></div><div class="controls"><select id="stats-mode" aria-label="통계 실행 범위"><option value="all">전체 실행 집계</option><option value="latest">CL별 최신 실행 집계</option></select><a class="button" href="/api/stats.csv?${esc(params({mode}))}">CSV 다운로드</a></div></div>
    <div class="metrics"><div class="metric">검사 실행<b>${total.runs||0}</b><small>정상 완료 ${total.completed||0} · 실패 ${total.failed||0}</small></div><div class="metric">검출 Findings<b>${total.findings||0}</b><small>정상 완료 실행 기준</small></div><div class="metric">실제 결함<b>${total.confirmed||0}</b><small>미검토 ${total.unreviewed||0} · 보류 ${total.deferred||0}</small></div><div class="metric">오탐률<b>${rate}</b><small>오탐 / (실제 결함 + 오탐)</small></div></div>
    <section class="panel"><div class="panel-head"><h2>버전 · 파트별 통계</h2><small>${mode==='all'?'재스캔을 포함한 전체 실행':'CL별 마지막 등록 실행'}</small></div>${stats.items.length?table(['릴리스 / 브랜치','파트','실행','Findings','실제 결함','오탐','미검토 / 보류','오탐률','검토율'],stats.items.map(r=>`<tr><td>${esc(r.release)} / ${esc(r.branch)}</td><td>${esc(r.part)}</td><td>${r.runs}</td><td>${r.findings}</td><td>${r.confirmed}</td><td>${r.false_positive}</td><td>${r.unreviewed} / ${r.deferred}</td><td>${r.false_positive_rate===null?'—':r.false_positive_rate+'%'}</td><td>${r.review_rate===null?'—':r.review_rate+'%'}</td></tr>`)):'<div class="empty">등록된 결과가 없습니다. ‘결과 등록’으로 첫 실행을 추가하세요.</div>'}<p class="muted"><small>${esc(stats.basis)}</small></p></section>
    <section class="panel"><div class="panel-head"><h2>실행 이력</h2><form id="search" class="controls"><input name="q" placeholder="CL · 실행 ID · MD 본문 검색" value="${esc(query)}" aria-label="검색어" maxlength="200"><button>검색</button></form></div>${runs.items.length?table(['CL / 실행 ID','릴리스 · 브랜치','파트','실행 결과','Finding 수','등록자','등록 시각'],runs.items.map(r=>`<tr><td><button class="finding-link" data-run="${r.id}">CL ${esc(r.cl)}</button><br><small>${esc(r.execution_id)}</small></td><td>${esc(r.release)} ${esc(r.branch)}</td><td>${esc(r.part)}</td><td>${badge(r.status)}</td><td>${r.finding_count}</td><td>${esc(r.uploader)}</td><td>${esc(date(r.created_at))}</td></tr>`)):'<div class="empty">해당 조건의 실행이 없습니다.</div>'}<div class="pagination"><small>${runs.total}회 실행 · ${page}페이지</small><button id="prev" ${page===1?'disabled':''}>이전</button><button id="next" ${page*30>=runs.total?'disabled':''}>다음</button></div></section>`;
    $('#stats-mode').value=mode;$('#stats-mode').onchange=e=>{mode=e.target.value;render();};
    $('#search').onsubmit=e=>{e.preventDefault();query=new FormData(e.target).get('q');page=1;render();};
    $('#prev').onclick=()=>{page--;render();};$('#next').onclick=()=>{page++;render();};
    document.querySelectorAll('[data-run]').forEach(b=>b.onclick=guard(()=>showRun(Number(b.dataset.run))));
  }catch(e){if(epoch===generation)notice(e);}
}
async function showRun(id, findingPage=1) {
  const epoch=++generation;const r=await api(`/api/runs/${id}?page=${findingPage}`);if(epoch!==generation)return;
  scope={release:r.release,branch:r.branch,part:r.part,cl:r.cl};breadcrumbs(r.execution_id);history.replaceState(null,'',`#run=${id}`);
  $('#content').innerHTML=`<div class="title-row"><div><div class="eyebrow">SCAN EXECUTION</div><h1>CL ${esc(r.cl)}</h1><p class="muted">${esc(r.execution_id)} · ${esc(r.release)} ${esc(r.branch)} / ${esc(r.part)}</p></div><button id="back-list">CL 실행 이력</button></div><div class="panel"><div class="panel-head"><h2>검사 결과</h2>${badge(r.status)}</div><div class="info-list"><span>등록자</span><div>${esc(r.uploader)}</div><span>등록 시각</span><div>${esc(date(r.created_at))}</div><span>Finding 수</span><div>${r.finding_count}</div><span>검사 범위</span><div>해당 CL의 변경 코드</div></div><details><summary>수행 메타데이터</summary><pre class="metadata">${esc(JSON.stringify(r.metadata,null,2))}</pre></details></div><section class="panel"><h2>Finding 보고서</h2>${r.findings.length?table(['보고서','결함 판단','수정 진행','담당자'],r.findings.map(f=>`<tr><td><button class="finding-link" data-finding="${f.id}">${esc(f.title)}</button><br><small>${esc(f.filename)}</small></td><td>${badge(f.judgment)}</td><td>${badge(f.progress)}</td><td>${esc(f.assignee||'미지정')}</td></tr>`)):`<div class="empty">${r.status==='completed'?'정상 완료 · Finding이 없습니다.':'실패 또는 중단된 검사입니다. 정상 완료 0건 결과로 집계하지 않습니다.'}</div>`}<div class="pagination"><button id="find-prev" ${findingPage===1?'disabled':''}>이전</button><span>${findingPage}페이지</span><button id="find-next" ${findingPage*50>=r.finding_count?'disabled':''}>다음</button></div></section>`;
  $('#back-list').onclick=()=>setScope(scope);$('#find-prev').onclick=guard(()=>showRun(id,findingPage-1));$('#find-next').onclick=guard(()=>showRun(id,findingPage+1));
  document.querySelectorAll('[data-finding]').forEach(b=>b.onclick=guard(()=>showFinding(Number(b.dataset.finding))));
}
async function showFinding(id,eventPage=1) {
  const epoch=++generation;const [f,events]=await Promise.all([api(`/api/findings/${id}`),api(`/api/findings/${id}/events?page=${eventPage}`)]);if(epoch!==generation)return;current=f;
  scope={release:f.run.release,branch:f.run.branch,part:f.run.part,cl:f.run.cl};breadcrumbs(f.filename);history.replaceState(null,'',`#finding=${id}`);
  const options=(values,selected)=>values.map(v=>`<option value="${v}" ${v===selected?'selected':''}>${labels[v]}</option>`).join('');
  $('#content').innerHTML=`<div class="title-row"><div><div class="eyebrow">FINDING REPORT · CL ${esc(f.run.cl)}</div><h1>${esc(f.title)}</h1><p class="muted">${esc(f.filename)} · ${esc(f.run.execution_id)}</p></div><div class="controls"><button id="back-run">실행 결과</button><a class="button" href="/api/findings/${id}/raw">원본 MD</a></div></div><div class="detail-grid"><article class="panel markdown">${f.html}</article><div><section class="panel"><h2>검토 · 처리</h2><form id="review"><label>작성자 이름<input name="actor" value="${esc(actor)}" maxlength="80" required></label><label>결함 판단<select name="judgment">${options(['unreviewed','confirmed','false_positive','deferred'],f.judgment)}</select></label><label>수정 진행<select name="progress">${options(['open','in_progress','fixed','verified'],f.progress)}</select></label><label>담당자<input name="assignee" value="${esc(f.assignee)}" maxlength="80"></label><button class="primary">변경 저장</button></form><small>이름은 자기 기입 방식입니다. 현재 로그인 인증은 없습니다.</small></section><section class="panel"><h2>검토 의견</h2><form id="comment"><label>작성자<input name="actor" value="${esc(actor)}" maxlength="80" required></label><label>의견<textarea name="text" rows="4" maxlength="10000" required></textarea></label><button>의견 등록</button></form></section></div></div><section class="panel"><h2>의견 · 변경 이력</h2>${events.items.length?events.items.map(e=>`<div class="event"><strong>${esc(e.actor)}</strong> <small>${esc(date(e.created_at))} · ${e.kind==='comment'?'의견':'상태 변경'}</small><p>${e.kind==='comment'?esc(e.detail.text):Object.entries(e.detail).map(([k,v])=>`${esc({judgment:'판단',progress:'진행',assignee:'담당자'}[k])}: ${esc(labels[v.before]||v.before||'미지정')} → ${esc(labels[v.after]||v.after||'미지정')}`).join('<br>')||'동일한 상태를 저장했습니다.'}</p></div>`).join(''):'<p class="muted">아직 등록된 이력이 없습니다.</p>'}<div class="pagination"><button id="event-prev" ${eventPage===1?'disabled':''}>이전</button><span>${eventPage}페이지</span><button id="event-next" ${eventPage*50>=events.total?'disabled':''}>다음</button></div></section>`;
  $('#back-run').onclick=guard(()=>showRun(f.run_id));
  $('#review').onsubmit=guard(async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target));remember(body.actor);body.revision=f.revision;await api(`/api/findings/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});await showFinding(id);});
  $('#comment').onsubmit=guard(async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target));remember(body.actor);await api(`/api/findings/${id}/comments`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});await showFinding(id);});
  $('#event-prev').onclick=guard(()=>showFinding(id,eventPage-1));$('#event-next').onclick=guard(()=>showFinding(id,eventPage+1));
}
$('#home').onclick=()=>setScope({});
$('#upload-open').onclick=()=>{const form=$('#upload-form');form.reset();for(const key of ['release','branch','part'])if(scope[key])form.elements[key].value=scope[key];form.elements.cl.value=scope.cl||'';form.elements.uploader.value=actor;form.elements.execution_id.value=crypto.randomUUID?crypto.randomUUID():`manual-${Date.now()}-${Math.random().toString(16).slice(2)}`;$('#upload-error').textContent='';$('#upload-dialog').showModal();};
$('#upload-close').onclick=()=>$('#upload-dialog').close();
$('#upload-form').onsubmit=async e=>{
  e.preventDefault();const form=e.target,submit=form.querySelector('[type=submit]');submit.disabled=true;$('#upload-error').textContent='';
  try{const meta=Object.fromEntries(new FormData(form));delete meta.files;meta.no_findings=form.elements.no_findings.checked;if(meta.status==='failed'){meta.error=meta.notes;meta.notes='';}
    const body=new FormData();body.append('metadata',JSON.stringify(meta));for(const f of form.elements.files.files)body.append('files',f);
    remember(meta.uploader);const r=await api('/api/manual/runs',{method:'POST',body});$('#upload-dialog').close();await showRun(r.id);
  }catch(err){$('#upload-error').textContent=err.message;}finally{submit.disabled=false;}
};
guard(async()=>{const config=await api('/api/config');$('#upload-form').elements.part.innerHTML=config.parts.map(p=>`<option>${esc(p)}</option>`).join('');const hash=new URLSearchParams(location.hash.slice(1));if(hash.has('finding'))await showFinding(Number(hash.get('finding')));else if(hash.has('run'))await showRun(Number(hash.get('run')));else await render();})();
