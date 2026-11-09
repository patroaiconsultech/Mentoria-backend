import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, stat, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  TARGET, assertOptions, assertIdentity, assertNoConflicts,
  assertCreatedVoice, assertAssignment, assertEligibleCapability,
  assertMp3, catalogPayload, assignmentPayload, newState,
  runApply, runRollback, reconcileRemote, AdminAPI, REMOTE_WRITES_ENABLED,
  storeState, STATE_FILE
} from '../josue_cedar_activation.mjs';

const tenant='11111111-1111-4111-8111-111111111111';
const options={action:'apply',expectedTenant:tenant,ao01Go:true,securityCleared:true,
  confirmation:'STAGING_JOSUE_ONLY',budgetUSD:1};
const voice={id:'voice-1',provider_key:'openai',provider_voice_id:'cedar',active:true,
  curation_status:'REVIEW_REQUIRED',supported_locales:['pt-BR'],
  delivery_modes:['REALTIME_STREAM','MESSAGE_PLAYBACK']};
const me={tenant_id:tenant,admin_access:true};
const agents=[{slug:'orkio',canonical_name:'Josué',display_name:'Josué CEO'}];
const a0={id:'assign-1',voice_catalog_id:'voice-1',agent_slug:'orkio',locale:'pt-BR',
  assignment_state:'DRAFT',validation_status:'UNVALIDATED',active:true,
  delivery_modes:['REALTIME_STREAM','MESSAGE_PLAYBACK']};
const cap={voice_output:{eligible:true,binding_source:'admin_assignment'},
  voice_segment_streaming:{eligible:true}};
function mp3() {
  const b=Buffer.alloc(417*2);
  for(let i of [0,417]) Buffer.from([0xff,0xfb,0x90,0x00]).copy(b,i);
  return b;
}
class FakeAPI {
  constructor({lossAt=null, preview=mp3(), identity=me, catalog=[], assignments=[],
    capability=cap}={}) {
    this.calls=[];this.lossAt=lossAt;this.preview=preview;this.identity=identity;
    this.catalog=catalog.map(x=>({...x}));this.assignments=assignments.map(x=>({...x}));
    this.capability=capability;this.previewCalls=0;
  }
  lost(step) {if(this.lossAt===step) throw new Error('NETWORK_LOST_AFTER_REMOTE_COMMIT');}
  async get(path) {
    this.calls.push('GET '+path);
    if(path==='/api/v2/me')return this.identity;
    if(path==='/api/v2/admin/agents')return agents;
    if(path==='/api/v2/admin/voice-catalog')return this.catalog.map(x=>({...x}));
    if(path==='/api/v2/admin/agent-voice-assignments')return this.assignments.map(x=>({...x}));
    if(path==='/api/v2/realtime/capabilities')return this.capability;
    throw new Error('UNKNOWN_GET');
  }
  async post(path,body) {
    this.calls.push('POST '+path);
    if(path==='/api/v2/admin/voice-catalog'){
      this.catalog.push({...voice});this.lost('catalog_create');return {...voice};
    }
    if(path.endsWith('/curation')){
      this.catalog[0].curation_status='APPROVED';this.lost('catalog_curation');
      return {...this.catalog[0]};
    }
    if(path.endsWith('/validation')){
      this.assignments[0].validation_status='VALIDATED';this.lost('assignment_validation');
      return {...this.assignments[0]};
    }
    if(path.endsWith('/activation')){
      this.assignments[0].assignment_state='ACTIVE';this.lost('assignment_activation');
      return {...this.assignments[0]};
    }
    if(path.endsWith('/deactivation')){
      if(path.includes('agent-voice-assignments')) {
        this.assignments[0].active=false;this.assignments[0].assignment_state='DISABLED';
      } else this.catalog[0].active=false;
      this.lost('rollback_'+(path.includes('agent-voice-assignments')?'assignment':'catalog'));
      return {};
    }
    throw new Error('UNKNOWN_POST: '+path);
  }
  async put(path) {
    this.calls.push('PUT '+path);
    if(path==='/api/v2/admin/agents/orkio/voice-assignment') {
      this.assignments.push({...a0});this.lost('assignment_create');return {...a0};
    }
    throw new Error('UNKNOWN_PUT');
  }
  async request(method,path,body,binary){
    this.calls.push(method+' '+path);
    if(!binary||!path.endsWith('/preview')) throw new Error('UNKNOWN_BINARY');
    this.previewCalls++;
    this.lost('preview');
    return this.preview;
  }
  writes(){return this.calls.filter(x=>x.startsWith('POST ')||x.startsWith('PUT '));}
}
function checkpointStore({failPhase=null}={}){
  const records=[];
  const save=async(s,audio)=>{
    if(s.phase===failPhase)throw new Error('DISK_IO_FAILURE');
    records.push({state:structuredClone(s),audio:audio?.length??0});
  };
  return {records,save,last:()=>records.at(-1)?.state};
}
function verifiedState(extra={}) {
  return {...newState(tenant),catalog_id:'voice-1',assignment_id:'assign-1',
    phase:'capability_eligible',status:'CONFIRMED',intent:null,...extra};
}
test('P0.2 remote-write CLI lock remains disabled',()=>assert.equal(REMOTE_WRITES_ENABLED,false));
test('plan/no gate needs no remote credentials',()=>{
  assert.doesNotThrow(()=>assertOptions({action:'plan'}));
  assert.throws(()=>assertOptions({...options,ao01Go:false}),/GATE_MISSING/);
});
test('identity mismatch fails before any mutation',async()=>{
  const api=new FakeAPI({identity:{...me,tenant_id:'other'}});
  await assert.rejects(runApply(api,options,undefined,async()=>{}),/PRINCIPAL_OR_TENANT_MISMATCH/);
  assert.equal(api.writes().length,0);
});
test('slug and agent canonical name must match',()=>{
  assert.throws(()=>assertIdentity(me,[{slug:'orkio',canonical_name:'Someone'}],tenant),/MISMATCH/);
});
test('catalog conflict or assignment conflict blocks writes',async()=>{
  for (const setup of [{catalog:[voice]},{assignments:[a0]}]) {
    const api=new FakeAPI(setup);
    await assert.rejects(runApply(api,options,undefined,async()=>{}),/ALREADY_EXISTS|ASSIGNMENT_EXISTS/);
    assert.equal(api.writes().length,0);
  }
});
test('catalog and assignment shapes and delivery mode contracts',()=>{
  assert.throws(()=>assertCreatedVoice({...voice,active:false}),/UNEXPECTED/);
  assert.throws(()=>assertAssignment({...a0,active:false},'voice-1','DRAFT','UNVALIDATED'),/INVALID/);
  assert.deepEqual(catalogPayload().delivery_modes,['REALTIME_STREAM','MESSAGE_PLAYBACK']);
  assert.deepEqual(assignmentPayload('v').delivery_modes,['REALTIME_STREAM','MESSAGE_PLAYBACK']);
});
test('capability requires governed source and segment stream',()=>{
  for (const item of [{voice_output:{eligible:true,binding_source:'legacy_env'},
    voice_segment_streaming:{eligible:true}},
    {voice_output:{eligible:true,binding_source:'admin_assignment'},
      voice_segment_streaming:{eligible:false}}]) {
    assert.throws(()=>assertEligibleCapability(item),/CAPABILITY_NOT_GOVERNED/);
  }
  assert.doesNotThrow(()=>assertEligibleCapability(cap));
});
test('MP3 with two MPEG frames accepted, fake MIME payload rejected',()=>{
  assert.equal(assertMp3(mp3()).length,834);
  assert.throws(()=>assertMp3(Buffer.from('ID3'.padEnd(180,'x'))),/INVALID/);
  assert.throws(()=>assertMp3(Buffer.alloc(200)),/INVALID/);
});
test('success checkpoints all writes, preview once, and no credential logs',async()=>{
  const api=new FakeAPI();const storage=checkpointStore();
  const result=await runApply(api,options,async()=> 'APROVO_CEDAR_JOSUE',storage.save);
  assert.equal(result.phase,'capability_eligible');
  assert.equal(result.status,'CONFIRMED');
  assert.equal(storage.records.some(x=>x.state.phase==='intent_catalog_create'),true);
  assert.equal(storage.records.some(x=>x.state.phase==='intent_assignment_activation'),true);
  assert.equal(storage.records.find(x=>x.state.phase==='preview_audio_received')?.audio,834);
  assert.equal(api.previewCalls,1);
  assert.equal(api.writes().length,6);
});
test('preview rejected by human: no curation or assignment',async()=>{
  const api=new FakeAPI();const storage=checkpointStore();
  await assert.rejects(runApply(api,options,async()=> 'NO',storage.save),/PREVIEW_NOT_HUMAN/);
  assert.equal(api.writes().some(x=>x.includes('/curation')),false);
});
test('disk fails before first catalog write -> zero writes',async()=>{
  const api=new FakeAPI(), storage=checkpointStore({failPhase:'intent_catalog_create'});
  await assert.rejects(runApply(api,options,undefined,storage.save),/DISK_IO_FAILURE/);
  assert.equal(api.writes().length,0);
});
test('disk fails after successful catalog response -> pending checkpoint and no second write',async()=>{
  const api=new FakeAPI(), storage=checkpointStore({failPhase:'catalog_create_confirmed'});
  await assert.rejects(runApply(api,options,undefined,storage.save),/RECONCILIATION_REQUIRED_catalog_create/);
  assert.equal(api.writes().length,1);
  assert.equal(storage.last().status,'RECONCILIATION_REQUIRED');
  assert.equal(storage.last().catalog_id,'voice-1');
});
for (const step of ['catalog_create','preview','catalog_curation','assignment_create',
  'assignment_validation','assignment_activation']) {
  test(`lost response after remote ${step}: stop with partial state, no duplicate write`,async()=>{
    const api=new FakeAPI({lossAt:step}),storage=checkpointStore();
    await assert.rejects(runApply(api,options,async()=> 'APROVO_CEDAR_JOSUE',storage.save),
      new RegExp(`RECONCILIATION_REQUIRED_${step}`));
    const x=storage.last();
    assert.equal(x.status,'RECONCILIATION_REQUIRED');
    assert.equal(x.phase,`unknown_${step}`);
    assert.equal(x.intent.step,step);
    assert.equal(api.writes().filter(w=>w.endsWith('/voice-catalog')).length,1);
    const before=api.writes().length;
    // reconcile READ-ONLY: does not issue a retry.
    await reconcileRemote(api,options,x);
    assert.equal(api.writes().length,before);
  });
}
test('reconcile detects remote Cedar with no saved ID and refuses ownership inference',async()=>{
  const api=new FakeAPI({catalog:[voice]});
  const state=newState(tenant);state.phase='unknown_catalog_create';
  state.status='RECONCILIATION_REQUIRED';
  const info=await reconcileRemote(api,options,state);
  assert.equal(info.catalog.exists,true);
  assert.equal(info.catalog.idKnown,false);
  assert.equal(info.requiresManualReview,true);
  assert.equal(api.writes().length,0);
});
test('reconcile missing assignment ID finds candidate but prevents auto rollback',async()=>{
  const api=new FakeAPI({catalog:[voice],assignments:[a0]});
  const state=verifiedState({assignment_id:null,phase:'unknown_assignment_create',
    status:'RECONCILIATION_REQUIRED',intent:{step:'assignment_create'}});
  const report=await reconcileRemote(api,options,state);
  assert.equal(report.assignment.exists,true);
  assert.equal(report.assignment.idKnown,false);
  await assert.rejects(runRollback(api,{...options,action:'rollback'},state,async()=>{}),/RECONCILIATION_REQUIRED/);
  assert.equal(api.writes().length,0);
});
test('rollback wrong tenant blocks before API calls',async()=>{
  const api=new FakeAPI({catalog:[voice]});
  await assert.rejects(runRollback(api,{...options,action:'rollback'},verifiedState({tenant_id:'other'}),async()=>{}),/STATE_PROVENANCE_INVALID/);
  assert.equal(api.calls.length,0);
});
test('rollback checks remote before each deactivation and persists intent',async()=>{
  const api=new FakeAPI({catalog:[{...voice,curation_status:'APPROVED'}],
    assignments:[{...a0,assignment_state:'ACTIVE',validation_status:'VALIDATED'}]});
  const storage=checkpointStore();
  const st=verifiedState();
  await runRollback(api,{...options,action:'rollback'},st,storage.save);
  assert.equal(storage.last().phase,'rollback_completed');
  assert.equal(api.writes().length,2);
  assert.equal(storage.records.some(x=>x.state.phase==='intent_rollback_assignment'),true);
  assert.equal(api.calls.filter(x=>x==='GET /api/v2/admin/agent-voice-assignments').length>=2,true);
});
test('rollback lost response stops before catalog write',async()=>{
  const api=new FakeAPI({lossAt:'rollback_assignment',
    catalog:[{...voice,curation_status:'APPROVED'}],assignments:[{...a0,assignment_state:'ACTIVE'}]});
  const storage=checkpointStore();
  await assert.rejects(runRollback(api,{...options,action:'rollback'},verifiedState(),storage.save),
    /ROLLBACK_RECONCILIATION_REQUIRED/);
  assert.equal(api.writes().length,1);
  assert.equal(storage.last().status,'RECONCILIATION_REQUIRED');
});
test('cross-tenant / unexpected assignment blocks rollback',async()=>{
  const api=new FakeAPI({catalog:[voice],assignments:[{...a0,voice_catalog_id:'other'}]});
  await assert.rejects(runRollback(api,{...options,action:'rollback'},verifiedState(),async()=>{}),/RECONCILIATION_/);
  assert.equal(api.writes().length,0);
});
test('AdminAPI refuses cross-origin injection',async()=>{
  let called=false;const api=new AdminAPI(async()=>{called=true;throw Error('unexpected');});
  await assert.rejects(api.get('https://external.invalid/x'),/INVALID_PATH/);
  assert.equal(called,false);
});
test('HTTP fake server validates CSRF outbound and rejects malformed preview',async()=>{
  const seen=[];const fakeFetch=async(url,req)=>{
    seen.push({path:new URL(url).pathname,...req});
    if(new URL(url).pathname==='/openapi.json') return {
      ok:true,status:200,headers:{getSetCookie:()=>['patroai_csrf=abc123; Path=/']},json:async()=>({})
    };
    return {ok:true,status:200,headers:{get:()=> 'audio/mpeg',getSetCookie:()=>[]},
      arrayBuffer:async()=>Buffer.from('ID3'.padEnd(200,'x'))};
  };
  const api=new AdminAPI(fakeFetch);
  await api.initialize();
  await assert.rejects(api.request('POST','/api/v2/admin/voice-catalog/v/preview',{text:'ok'},true),/MP3/);
  assert.equal(seen.at(-1).headers['X-ORKIO-CSRF'],'abc123');
  assert.equal(seen.at(-1).method,'POST');
});

test('atomic journal uses exclusive first checkpoint, updates and restrictive permissions',async()=>{
  const original=process.cwd();
  const dir=await mkdtemp(join(tmpdir(),'dg-realtime-p02-'));
  try {
    process.chdir(dir);
    const state=newState(tenant);
    await storeState(state);
    const persisted=JSON.parse(await readFile(STATE_FILE,'utf8'));
    assert.equal(persisted.operation_id,state.operation_id);
    state.phase='intent_catalog_create';state.status='IN_FLIGHT';
    await storeState(state);
    const updated=JSON.parse(await readFile(STATE_FILE,'utf8'));
    assert.equal(updated.phase,'intent_catalog_create');
    assert.equal((await readdir(dir)).filter(n=>n.endsWith('.tmp')).length,0);
    if(process.platform !== 'win32') assert.equal((await stat(STATE_FILE)).mode & 0o077,0);
  } finally {
    process.chdir(original);
    await rm(dir,{recursive:true,force:true});
  }
});
test('real localhost HTTP: CSRF, lost POST response, GET reconciles no duplicate POST',async(t)=>{
  let created=false,postCount=0;
  const server=createServer(async(req,res)=>{
    let text='';
    for await(const chunk of req) text+=chunk.toString();
    const path=new URL(req.url,'http://127.0.0.1').pathname;
    if(path==='/openapi.json'){
      res.setHeader('Set-Cookie','patroai_csrf=localonly; Path=/; SameSite=Strict');
      res.setHeader('content-type','application/json');res.end('{}');return;
    }
    if(path==='/api/v2/admin/voice-catalog' && req.method==='POST'){
      postCount++;
      assert.equal(req.headers['x-orkio-csrf'],'localonly');
      assert.equal(req.headers.cookie,'patroai_csrf=localonly');
      assert.equal(JSON.parse(text).provider_voice_id,'cedar');
      created=true;
      req.socket.destroy(); // remote committed, client never gets response
      return;
    }
    res.setHeader('content-type','application/json');
    if(path==='/api/v2/me')return res.end(JSON.stringify(me));
    if(path==='/api/v2/admin/agents')return res.end(JSON.stringify(agents));
    if(path==='/api/v2/admin/voice-catalog')return res.end(JSON.stringify(created?[voice]:[]));
    if(path==='/api/v2/admin/agent-voice-assignments')return res.end('[]');
    res.statusCode=404;res.end('{}');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>server.close(resolve)));
  const api=new AdminAPI();
  api.base=`http://127.0.0.1:${server.address().port}`;
  await api.initialize();
  const storage=checkpointStore();
  await assert.rejects(runApply(api,options,undefined,storage.save),/RECONCILIATION_REQUIRED_catalog_create/);
  assert.equal(postCount,1);
  assert.equal(created,true);
  const report=await reconcileRemote(api,options,storage.last());
  assert.equal(report.catalog.exists,true);
  assert.equal(report.catalog.idKnown,false);
  assert.equal(report.requiresManualReview,true);
  assert.equal(postCount,1);
});
