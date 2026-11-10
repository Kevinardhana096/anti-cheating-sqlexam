const {test}=require('node:test');
const assert=require('node:assert/strict');
const {environment}=require('./audit_admin_behaviors.cjs');
test('untrusted names are data attributes, never inline handlers',async()=>{
 for(const name of ["O'Brien","');window.auditInjected=true;//"]){
  const e=environment();e.ctx.network=async()=>({ok:true,json:async()=>({students:[{nim:'AUDIT',name}]})});
  await e.run('loadDashboardData()');
  assert.doesNotMatch(e.get('student-table-body').innerHTML,/onclick=/);
  assert.match(e.get('student-table-body').innerHTML,/data-admin-action="unlock"/);
  assert.equal(e.ctx.auditInjected,undefined);
  let received;
  e.ctx.clearStudentSessionLock=(...args)=>{received=args};
  e.ctx.events.click({target:{closest:()=>({dataset:{adminAction:'unlock',nim:'AUDIT',name}})}});
  assert.deepEqual(received,['AUDIT',name]);
 }
});
test('failed admin reads preserve the last dashboard',async()=>{
 const e=environment();e.get('stat-total-students').textContent='24';
 await e.run('loadDashboardData()');
 assert.equal(e.get('stat-total-students').textContent,'24');
 assert.ok(e.ctx.toasts.some(t=>t[1]==='warning'));
});
test('invalid question SQL displays validation reason and keeps the form',async()=>{
 const e=environment();
 const fields={'modal-q-id':'','modal-q-category':'A','modal-q-num':'1','modal-q-title':'Test',
  'modal-q-desc':'Description','modal-q-weight':'10','modal-q-expected':'random words','modal-q-target-db':'pagila'};
 for(const [id,value] of Object.entries(fields))e.get(id).value=value;
 e.get('question-modal').style.display='flex';
 e.ctx.network=async()=>({ok:false,status:400,json:async()=>({detail:'Kunci jawaban bukan SQL yang valid.'})});
 await e.ctx.saveQuestionForm({preventDefault(){}});
 assert.deepEqual(e.ctx.toasts.at(-1),['Kunci jawaban bukan SQL yang valid.','warning']);
 assert.equal(e.get('modal-q-expected').value,'random words');
 assert.equal(e.get('question-modal').style.display,'flex');
});
test('gallery navigation rejects executable URLs and removes opener access',()=>{
 const e=environment(),opened=[];
 e.ctx.open=(...args)=>opened.push(args);
 const click=url=>e.ctx.events.click({target:{closest:()=>({dataset:{adminAction:'open-image',url}})}});
 click('javascript:window.auditInjected=true');
 assert.equal(opened.length,0);
 click('https://example.com/image.png');
 assert.equal(opened[0][2],'noopener,noreferrer');
});
for(const action of ['deleteAllQuestions','confirmClearLogs','executeClearSessions']){
 test(action+' cannot display success on HTTP rejection',async()=>{
  const e=environment();e.ctx.loadQuestionsData=()=>{};e.ctx.loadDashboardData=()=>{};e.ctx.loadLogsData=()=>{};
  await e.run(action+'()');
  assert.ok(e.ctx.toasts.some(t=>t[1]==='danger'));
  assert.ok(!e.ctx.toasts.some(t=>t[1]==='success'||t[0].includes('berhasil')));
 });
}
test('old polling responses cannot replace newer data',async()=>{
 const e=environment(),pending=[];
 e.ctx.network=()=>new Promise(resolve=>pending.push(resolve));
 const a=e.run('loadDashboardData()'),b=e.run('loadDashboardData()');
 pending[1]({ok:true,json:async()=>({students:[{nim:'NEW',name:'Current'}]})});await b;
 pending[0]({ok:true,json:async()=>({students:[{nim:'OLD',name:'Stale'}]})});await a;
 assert.match(e.get('student-table-body').innerHTML,/NEW/);
 assert.doesNotMatch(e.get('student-table-body').innerHTML,/OLD/);
});
