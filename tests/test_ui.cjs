// Dependency-free regression checks for browser state transitions.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');

function workspace(responses) {
  const nodes = new Map();
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {innerHTML:'', hidden:false, value:'', checked:false, disabled:false});
    return nodes.get(selector);
  };
  node('#upload-form').elements = {
    status: {value:'completed'}, no_findings: {checked:false}, files: {value:'finding.md'}
  };
  const requests = [];
  const context = vm.createContext({
    document: {querySelector:node, querySelectorAll:()=>[]},
    localStorage: {getItem:()=>'',setItem:()=>{}},
    location: {pathname:'/',hash:''}, history: {replaceState:()=>{}},
    URLSearchParams, FormData, crypto: {randomUUID:()=> 'manual-test'},
    fetch: async path => {
      requests.push(path);
      // Leave startup pending; each test explicitly selects a view.
      if(path === '/api/config') return new Promise(()=>{});
      const value = responses(path);
      assert.notEqual(value, undefined, `Unexpected request: ${path}`);
      return {ok:true,json:async()=>value};
    }
  });
  vm.runInContext(source,context);
  return {node,requests,run:expression=>vm.runInContext(expression,context)};
}

const run = {id:2,release:'SVR26B',branch:'INTEG',part:'VP',cl:'123456',
  execution_id:'scan-2',status:'completed',uploader:'QA',finding_count:0,metadata:{},findings:[]};
const groups = [{name:'123456',runs:2,findings:0}];

test('run and direct finding views load navigation for their own scope and clear old errors',async()=>{
  const ui = workspace(path => path.startsWith('/api/groups?') ? groups :
    path.startsWith('/api/runs/2') ? run :
    path === '/api/findings/1' ? {id:1,run_id:2,run,title:'Report',filename:'a.md',html:'<p>Body</p>'} :
    path.startsWith('/api/findings/1/events') ? {items:[],total:0} : undefined);
  await ui.run('showRun(2)');
  assert.match(ui.node('#navigation').innerHTML,/CL 123456/);
  assert.equal(ui.node('#message').hidden,true);
  ui.node('#navigation').innerHTML=''; ui.node('#message').hidden=false;
  await ui.run('showFinding(1)');
  assert.match(ui.node('#navigation').innerHTML,/CL 123456/);
  assert.equal(ui.node('#message').hidden,true);
  const scope = new URLSearchParams(ui.requests.filter(p=>p.startsWith('/api/groups?')).at(-1).split('?')[1]);
  assert.equal(scope.get('level'),'cl'); assert.equal(scope.get('part'),'VP');
});

test('upload controls prevent contradictory zero-finding and failed/cancelled results',()=>{
  const ui = workspace(()=>undefined), form=ui.node('#upload-form').elements;
  form.no_findings.checked=true;
  ui.run('syncUploadControls()');
  assert.equal(form.files.disabled,true); assert.equal(form.files.value,'');
  for(const status of ['failed','cancelled']) {
    form.status.value=status; form.no_findings.checked=true;
    ui.run('syncUploadControls()');
    assert.equal(form.no_findings.disabled,true); assert.equal(form.no_findings.checked,false);
    assert.equal(form.files.disabled,false);
  }
  form.status.value='completed'; ui.run('syncUploadControls()');
  assert.equal(form.no_findings.disabled,false);
});

test('dashboard accounts for cancelled executions in the run summary',async()=>{
  const ui = workspace(path => path.startsWith('/api/groups?') ? [] :
    path.startsWith('/api/runs?') ? {items:[],total:0} :
    path.startsWith('/api/stats?') ? {items:[{runs:3,completed:1,failed:1,cancelled:1}],basis:'test'} : undefined);
  await ui.run('render()');
  assert.match(ui.node('#content').innerHTML,/정상 완료 1 · 실패 1 · 중단 1/);
});
