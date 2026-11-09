#!/usr/bin/env node
// DG-REALTIME-01 | EFATA 777 | staging only | proposal-only until AO-01 GO.
// Requires Node.js >= 20; Node 24 is available on the operator workstation.
// Uses only canonical authenticated API endpoints. No database SQL or bypass.
import { writeFile, readFile, access, open, rename, unlink } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';

export const TARGET = Object.freeze({
  baseUrl: 'https://efata-777-backend-staging-web01-staging-web01.up.railway.app',
  environment: 'staging-web01',
  agentSlug: 'orkio',
  agentName: 'Josué',
  tenantLocale: 'pt-BR',
  provider: 'openai',
  voice: 'cedar',
  model: 'gpt-4o-mini-tts',
  deliveryModes: ['REALTIME_STREAM', 'MESSAGE_PLAYBACK'],
  previewText: 'Olá. Eu sou Josué, da EFATÀ 777. Este é um teste controlado de voz.',
});
export const STATE_FILE = 'DG_REALTIME_01_JOSUE_STATE_LOCAL.json';
export const PREVIEW_FILE = 'DG_REALTIME_01_CEDAR_PREVIEW_LOCAL.mp3';
// Reviewed for offline tests only. AO-01 P0.2 has NO-GO for real writes.
export const REMOTE_WRITES_ENABLED = false;

export function fail(message) { throw new Error(message); }
export function normalized(x) {
  return String(x ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}
export function assertOptions(opts) {
  if (opts.action === 'plan') return;
  if (!['apply', 'rollback', 'reconcile'].includes(opts.action)) fail('ACTION_NOT_ALLOWED');
  if (!(opts.securityCleared && opts.confirmation === 'STAGING_JOSUE_ONLY' && (opts.action === 'reconcile' || opts.ao01Go))) {
    fail('GATE_MISSING: AO01_GO, SECURITY_CLEARED e confirmacao sao obrigatorios.');
  }
  if (!/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(opts.expectedTenant ?? '')) {
    fail('EXPECTED_TENANT_REQUIRED: obtenha tenant_id legitimamente; nao inferir.');
  }
  if (opts.action === 'apply' && opts.budgetUSD !== 1) {
    fail('PREVIEW_BUDGET_NOT_CONFIRMED: teto proposto US$ 1; nao e limite automatico do provider.');
  }
}
export function assertIdentity(me, agents, expectedTenant) {
  if (!me || me.tenant_id !== expectedTenant || me.admin_access !== true) {
    fail('PRINCIPAL_OR_TENANT_MISMATCH');
  }
  if (!Array.isArray(agents)) fail('AGENT_CATALOG_NOT_ARRAY');
  const matched = agents.filter(x => x.slug === TARGET.agentSlug);
  if (matched.length !== 1) fail('JOSUE_SLUG_NOT_UNIQUE');
  const label = [matched[0].canonical_name, matched[0].display_name].join(' ');
  if (!normalized(label).includes('josue')) fail('JOSUE_CANONICAL_IDENTITY_MISMATCH');
}
export function assertNoConflicts(catalog, assignments) {
  if (!Array.isArray(catalog) || !Array.isArray(assignments)) fail('ADMIN_LIST_INVALID');
  if (catalog.some(x => x.provider_key === TARGET.provider && x.provider_voice_id === TARGET.voice)) {
    fail('CEDAR_ALREADY_EXISTS: revisar estado, nao sobrescrever.');
  }
  if (assignments.some(x => x.agent_slug === TARGET.agentSlug && x.locale === TARGET.tenantLocale)) {
    fail('JOSUE_ASSIGNMENT_EXISTS: nao substituir uma voz anterior.');
  }
}
export function assertCreatedVoice(v) {
  if (!v || typeof v.id !== 'string' || !v.id || v.provider_key !== TARGET.provider ||
      v.provider_voice_id !== TARGET.voice || v.active !== true ||
      v.curation_status !== 'REVIEW_REQUIRED') fail('UNEXPECTED_CATALOG_CREATE_RESPONSE');
}
export function assertAssignment(a, voiceId, expectedState, validation) {
  if (!a || !a.id || a.voice_catalog_id !== voiceId ||
      a.agent_slug !== TARGET.agentSlug || a.locale !== TARGET.tenantLocale ||
      a.assignment_state !== expectedState || a.validation_status !== validation ||
      a.active !== true) fail('ASSIGNMENT_RESPONSE_INVALID');
}
export function assertEligibleCapability(cap) {
  if (cap?.voice_output?.eligible !== true || cap?.voice_output?.binding_source !== 'admin_assignment' || cap?.voice_segment_streaming?.eligible !== true) {
    fail('CAPABILITY_NOT_GOVERNED_OR_SEGMENT_READY');
  }
  // This is tenant-level, not agent-specific. Agent proof requires the
  // authenticated assignment response plus later runtime call evidence.
}
export function catalogPayload() {
  return {
    provider_key: TARGET.provider,
    provider_voice_id: TARGET.voice,
    display_name: 'Josué CEO — Cedar',
    provider_model: TARGET.model,
    source_type: 'BUILT_IN',
    license_label: 'PROVIDER_TERMS',
    cost_class: 'API_USAGE_BILLED',
    provenance_url: 'https://developers.openai.com/api/docs/guides/text-to-speech',
    catalog_version: '1',
    supported_locales: [TARGET.tenantLocale],
    delivery_modes: [...TARGET.deliveryModes],
  };
}
export function assignmentPayload(id) {
  return {
    voice_catalog_id: id,
    locale: TARGET.tenantLocale,
    delivery_modes: [...TARGET.deliveryModes],
    presentation_label: 'MASCULINA',
    timbre_label: 'GRAVE_EXECUTIVO',
    energy_label: 'FORTE_CONTROLADA',
  };
}
function cookieFromHeader(line) {
  const first = String(line).split(';', 1)[0];
  const at = first.indexOf('=');
  if (at <= 0) return null;
  const name = first.slice(0, at);
  if (!['patroai_csrf', '__Host-patroai_session', 'patroai_session'].includes(name)) return null;
  return [name, first.slice(at + 1)];
}

// Validate MPEG Layer III frame structure, not only Content-Type / "ID3" prefix.
// Accept optional ID3v2 tag, require two consecutive complete frames.
export function assertMp3(buf) {
  if (!Buffer.isBuffer(buf) || buf.length < 100 || buf.length > 3_000_000) fail('PREVIEW_AUDIO_INVALID_SIZE');
  let pos = 0;
  if (buf.subarray(0, 3).toString('ascii') === 'ID3') {
    if (buf.length < 10 || [...buf.subarray(6,10)].some(x => x & 0x80)) fail('PREVIEW_ID3_INVALID');
    const tag = (buf[6]<<21)|(buf[7]<<14)|(buf[8]<<7)|buf[9];
    pos = 10 + tag + ((buf[5]&0x10) ? 10 : 0);
  }
  function frame(at) {
    if (at+4>buf.length) return null;
    const h = buf.readUInt32BE(at);
    if (((h>>>21)&2047)!==2047) return null;
    const version=(h>>>19)&3, layer=(h>>>17)&3;
    const br=(h>>>12)&15, sr=(h>>>10)&3, pad=(h>>>9)&1;
    if (version===1 || layer!==1 || br===0 || br===15 || sr===3) return null;
    const bitrate = (version===3
      ? [0,32,40,48,56,64,80,96,112,128,160,192,224,256,320,0]
      : [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160,0])[br];
    const samplerate = [44100,48000,32000][sr] / (version===3?1:version===2?2:4);
    const length = Math.floor((version===3?144:72)*bitrate*1000/samplerate)+pad;
    return length > 4 && at+length <= buf.length ? length : null;
  }
  const first=frame(pos);
  if (!first || !frame(pos+first)) fail('PREVIEW_MP3_FRAME_INVALID');
  return buf;
}

export class AdminAPI {
  constructor(fetchImpl = fetch) {
    this.fetchImpl = fetchImpl;
    this.cookies = new Map();
    this.base = TARGET.baseUrl;
  }
  cookieHeader() {
    return [...this.cookies].map(([k,v]) => `${k}=${v}`).join('; ');
  }
  async request(method, path, body = undefined, binary = false) {
    if (!path.startsWith('/') || path.startsWith('//') || path.includes('://')) fail('INVALID_PATH');
    const url = new URL(path, this.base);
    if (url.origin !== new URL(this.base).origin) fail('CROSS_ORIGIN_BLOCKED');
    const headers = { Accept: binary ? 'audio/mpeg' : 'application/json' };
    if (this.cookies.size) headers.Cookie = this.cookieHeader();
    if (!['GET','HEAD'].includes(method)) {
      const csrf = this.cookies.get('patroai_csrf');
      if (!csrf) fail('CSRF_COOKIE_MISSING');
      headers['X-ORKIO-CSRF'] = csrf;
    }
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let res;
    try {
      res = await this.fetchImpl(url, {
        method, headers, redirect: 'error',
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(20000),
      });
    } catch (_) {
      fail(`NETWORK_OR_TLS_FAILURE ${method} ${path}`);
    }
    for (const line of res.headers.getSetCookie?.() ?? []) {
      const pair = cookieFromHeader(line);
      if (pair) this.cookies.set(pair[0], pair[1]);
    }
    if (!res.ok) fail(`HTTP_${res.status} ${method} ${path}; STOP sem retry.`);
    if (binary) {
      const type = (res.headers.get('content-type') ?? '').split(';')[0].trim();
      if (type !== 'audio/mpeg') fail('PREVIEW_MIME_INVALID');
      const contentLength = Number(res.headers.get('content-length') || 0);
      if (contentLength > 3_000_000) fail('PREVIEW_TOO_LARGE');
      const buf = Buffer.from(await res.arrayBuffer());
      return assertMp3(buf);
    }
    return await res.json();
  }
  get(path) { return this.request('GET', path); }
  post(path, data) { return this.request('POST', path, data); }
  put(path, data) { return this.request('PUT', path, data); }
  async initialize() { await this.get('/openapi.json'); }
}
async function ttyPrompt(question, masked = false) {
  if (!process.stdin.isTTY || !process.stdout.isTTY) fail('INTERACTIVE_TTY_REQUIRED');
  process.stdout.write(question);
  return await new Promise((resolve, reject) => {
    let s = '';
    const oldRaw = process.stdin.isRaw ?? false;
    const onData = chunk => {
      for (const ch of String(chunk)) {
        if (ch === '\r' || ch === '\n') { cleanup(); process.stdout.write('\n'); resolve(s); return; }
        if (ch === '\u0003') { cleanup(); process.stdout.write('\n'); reject(new Error('CANCELLED')); return; }
        if (ch === '\u007f' || ch === '\b') { s = s.slice(0,-1); continue; }
        if (ch >= ' ') { s += ch; if (!masked) process.stdout.write(ch); }
      }
    };
    function cleanup() {
      process.stdin.removeListener('data', onData);
      process.stdin.setRawMode(oldRaw);
      process.stdin.pause();
    }
    process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.on('data', onData);
  });
}
async function loginAdmin(api, prompt = ttyPrompt) {
  await api.initialize(); // obtains CSRF cookie. No auth bypass.
  const email = (await prompt('Email administrativo da STAGING: ')).trim();
  let password = await prompt('Senha (oculta): ', true);
  const start = await api.post('/api/v2/auth/admin/otp/start', { email, password });
  password = ''; // no file/logging; an ephemeral in-memory variable only
  if (start?.status !== 'OTP_SENT' || !start?.challenge_token) fail('ADMIN_OTP_START_FAILED');
  const code = await prompt('OTP de 6 digitos (oculto): ', true);
  if (!/^\d{6}$/.test(code)) fail('OTP_FORMAT_INVALID');
  const verified = await api.post('/api/v2/auth/admin/otp/verify', {
    challenge_token: start.challenge_token, code,
  });
  if (verified?.authenticated !== true || !api.cookies.has('__Host-patroai_session') &&
      !api.cookies.has('patroai_session')) fail('ADMIN_AUTH_NOT_VERIFIED');
}
export async function checkTarget(api, expectedTenant, requireNoConflicts = true) {
  const me = await api.get('/api/v2/me');
  const agents = await api.get('/api/v2/admin/agents');
  assertIdentity(me, agents, expectedTenant);
  const catalog = await api.get('/api/v2/admin/voice-catalog');
  const assignments = await api.get('/api/v2/admin/agent-voice-assignments');
  if (requireNoConflicts) assertNoConflicts(catalog, assignments);
  return {me, catalog, assignments};
}

function matchAssignment(x, voiceId) {
  return x && x.agent_slug === TARGET.agentSlug && x.locale === TARGET.tenantLocale &&
    (!voiceId || x.voice_catalog_id === voiceId);
}
function matchVoice(x) {
  return x && x.provider_key === TARGET.provider && x.provider_voice_id === TARGET.voice;
}
function safeId(id) {
  if (typeof id !== 'string' || !/^[a-zA-Z0-9_-]{1,120}$/.test(id)) fail('REMOTE_IDENTIFIER_INVALID');
  return encodeURIComponent(id);
}
export function newState(tenant) {
  return {
    state_version:2, target:TARGET.environment, tenant_id:tenant, agent_slug:TARGET.agentSlug,
    catalog_id:null, assignment_id:null, phase:'preflight', status:'CONFIRMED',
    intent:null, created_at:new Date().toISOString(), operation_id:randomUUID(),
    preflight_empty_catalog:true, preflight_empty_assignment:true,
  };
}
function validateState(state, expectedTenant) {
  if (state?.state_version !== 2 || state.target !== TARGET.environment ||
    state.tenant_id !== expectedTenant || state.agent_slug !== TARGET.agentSlug ||
    typeof state.operation_id !== 'string') fail('STATE_PROVENANCE_INVALID');
  if (state.catalog_id !== null) safeId(state.catalog_id);
  if (state.assignment_id !== null) safeId(state.assignment_id);
}
export async function reconcileRemote(api, opts, state) {
  validateState(state, opts.expectedTenant);
  const ctx = await checkTarget(api, opts.expectedTenant, false);
  const voices = ctx.catalog.filter(matchVoice);
  const assignments = ctx.assignments.filter(x => matchAssignment(x, state.catalog_id));
  const unrelated = ctx.assignments.filter(x => matchAssignment(x, null) &&
    state.catalog_id && x.voice_catalog_id !== state.catalog_id);
  if (voices.length > 1 || assignments.length > 1 || unrelated.length) fail('RECONCILIATION_AMBIGUOUS');
  const voice = voices[0] ?? null;
  if (state.catalog_id && (!voice || voice.id !== state.catalog_id)) fail('RECONCILIATION_CATALOG_MISMATCH');
  const assignment = assignments[0] ?? null;
  if (state.assignment_id && (!assignment || assignment.id !== state.assignment_id)) {
    fail('RECONCILIATION_ASSIGNMENT_MISMATCH');
  }
  if (assignment && (!voice || assignment.voice_catalog_id !== voice.id)) fail('RECONCILIATION_RELATION_MISMATCH');
  // A matching row with no locally saved ID is NOT ownership proof:
  // another admin could have concurrently created it. Require independent review.
  const ownerVerified = (!voice || state.catalog_id === voice.id) &&
    (!assignment || state.assignment_id === assignment.id);
  return {
    phase:state.phase, status:state.status,
    catalog:{exists:Boolean(voice),idKnown: Boolean(voice && state.catalog_id===voice.id),
      active:voice?.active??null,curation_status:voice?.curation_status??null},
    assignment:{exists:Boolean(assignment),idKnown:Boolean(assignment && state.assignment_id===assignment.id),
      active:assignment?.active??null,assignment_state:assignment?.assignment_state??null,
      validation_status:assignment?.validation_status??null},
    ownerVerified, requiresManualReview:!ownerVerified ||
      state.status === 'RECONCILIATION_REQUIRED' ||
      state.intent !== null,
    // Never expose tenant ID, user, auth header, or candidate IDs in CLI output.
  };
}
export async function runApply(api, opts, prompt = ttyPrompt, save) {
  assertOptions(opts);
  if (typeof save !== "function") fail("DURABLE_CHECKPOINT_HANDLER_REQUIRED");
  const ctx = await checkTarget(api, opts.expectedTenant);
  const state = newState(ctx.me.tenant_id);
  await save({...state}); // durable preflight before any write
  const checkpoint = async (phase) => {
    state.phase = phase; state.intent = null; state.status='CONFIRMED';
    await save({...state});
  };
  async function writeStep(step, method, path, body, check, binary=false) {
    state.phase=`intent_${step}`;
    state.status='IN_FLIGHT';
    state.intent={step,method,path,at:new Date().toISOString()};
    await save({...state}); // if disk fails, NEVER start the request
    try {
      const response = binary
        ? await api.request(method,path,body,true)
        : method==='PUT' ? await api.put(path,body) : await api.post(path,body);
      if (check) await check(response);
      // Checkpoint response before permitting another remote action.
      await checkpoint(`${step}_confirmed`);
      return response;
    } catch (e) {
      const original = e;
      state.status='RECONCILIATION_REQUIRED';
      state.phase=`unknown_${step}`;
      try { await save({...state}); }
      catch { fail('CHECKPOINT_FAILURE_AFTER_POSSIBLE_REMOTE_WRITE: stop, preserve journal, manual recovery'); }
      // DO NOT automatically retry, continue, or rollback an ambiguous POST.
      fail(`RECONCILIATION_REQUIRED_${step}: ${original?.message?.slice(0,90)??'UNKNOWN'}`);
    }
  }
  const voice = await writeStep('catalog_create','POST','/api/v2/admin/voice-catalog',
    catalogPayload(), v=>{assertCreatedVoice(v);state.catalog_id=v.id;});
  const audio = await writeStep('preview','POST',
    `/api/v2/admin/voice-catalog/${safeId(voice.id)}/preview`,
    {text:TARGET.previewText,locale:TARGET.tenantLocale},
    buf=>save({...state,phase:'preview_audio_received',status:'IN_FLIGHT'},assertMp3(buf)),true);
  // MP3 stored locally, but audible playback remains a manual evidence gate.
  const consent = (await prompt('Ouviu o MP3 e APROVA a voz? Digite APROVO_CEDAR_JOSUE: ')).trim();
  if (consent !== 'APROVO_CEDAR_JOSUE') fail('PREVIEW_NOT_HUMAN_APPROVED');
  const evidence = `DG_REALTIME_01:human-preview:${state.operation_id}`;
  await writeStep('catalog_curation','POST',
    `/api/v2/admin/voice-catalog/${safeId(voice.id)}/curation`,
    {curation_status:'APPROVED',evidence_ref:evidence},
    v=>{ if(v?.id!==voice.id||v?.curation_status!=='APPROVED') fail('CURATION_RESPONSE_INVALID'); });
  const latest = await api.get('/api/v2/admin/agent-voice-assignments');
  if (!Array.isArray(latest) || latest.some(x=>matchAssignment(x,null))) fail('CONCURRENT_ASSIGNMENT_DETECTED');
  const assignment = await writeStep('assignment_create','PUT',
    `/api/v2/admin/agents/${TARGET.agentSlug}/voice-assignment`,
    assignmentPayload(voice.id),
    a=>{assertAssignment(a,voice.id,'DRAFT','UNVALIDATED');state.assignment_id=a.id;});
  await writeStep('assignment_validation','POST',
    `/api/v2/admin/agent-voice-assignments/${safeId(assignment.id)}/validation`,
    {validation_status:'VALIDATED',evidence_ref:evidence},
    a=>assertAssignment(a,voice.id,'DRAFT','VALIDATED'));
  await writeStep('assignment_activation','POST',
    `/api/v2/admin/agent-voice-assignments/${safeId(assignment.id)}/activation`,
    {evidence_ref:evidence},a=>assertAssignment(a,voice.id,'ACTIVE','VALIDATED'));
  const cap=await api.get('/api/v2/realtime/capabilities');
  assertEligibleCapability(cap);
  await checkpoint('capability_eligible');
  return {...state};
}
export async function runRollback(api, opts, state, save) {
  assertOptions(opts);
  if (typeof save !== "function") fail("DURABLE_CHECKPOINT_HANDLER_REQUIRED");
  validateState(state, opts.expectedTenant);
  const report = await reconcileRemote(api,opts,state); // always GET first
  if (report.requiresManualReview) fail('ROLLBACK_BLOCKED_RECONCILIATION_REQUIRED');
  if (!state.catalog_id || !report.catalog.exists) fail('ROLLBACK_CATALOG_ID_REQUIRED');
  // If an assignment could be present but not uniquely matched, reconcileRemote stops.
  if (report.assignment.exists && !state.assignment_id) fail('ROLLBACK_UNKNOWN_ASSIGNMENT_ID');
  const evidence=`DG_REALTIME_01:rollback:${state.operation_id}`;
  const undo = async (step,path) => {
    state.phase=`intent_rollback_${step}`; state.intent={step,method:'POST',path};
    state.status='IN_FLIGHT';
    await save({...state}); // write-ahead
    try {
      await api.post(path,{evidence_ref:evidence});
      state.intent=null; state.status='CONFIRMED'; state.phase=`rollback_${step}_confirmed`;
      await save({...state});
    } catch {
      state.status='RECONCILIATION_REQUIRED'; state.phase=`rollback_unknown_${step}`;
      try {await save({...state});} catch { fail('ROLLBACK_LOCAL_STATE_FAILED'); }
      fail('ROLLBACK_RECONCILIATION_REQUIRED');
    }
  };
  if (report.assignment.exists && report.assignment.active) {
    await undo('assignment',`/api/v2/admin/agent-voice-assignments/${safeId(state.assignment_id)}/deactivation`);
  }
  // GET again: do not deactivate voice if remote state has changed or there is an unknown assignment.
  const fresh = await reconcileRemote(api,opts,state);
  if (fresh.requiresManualReview || fresh.assignment.active) fail('ROLLBACK_CATALOG_BLOCKED');
  if (fresh.catalog.active) {
    await undo('catalog',`/api/v2/admin/voice-catalog/${safeId(state.catalog_id)}/deactivation`);
  }
  state.intent=null; state.phase='rollback_completed';state.status='CONFIRMED';
  await save({...state});
  return {...state};
}

function parseArgs(argv) {
  const opt = {
    action:'plan',expectedTenant:null,ao01Go:false,securityCleared:false,
    confirmation:'',budgetUSD:0
  };
  for (let i=0;i<argv.length;i++) {
    const a=argv[i];
    if (a==='--plan') opt.action='plan';
    else if (a==='--apply') opt.action='apply';
    else if (a==='--rollback') opt.action='rollback';
    else if (a==='--reconcile') opt.action='reconcile';
    else if (a==='--ao01-go') opt.ao01Go=true;
    else if (a==='--security-cleared') opt.securityCleared=true;
    else if (['--expected-tenant','--confirm','--budget-usd'].includes(a)) {
      const val=argv[++i]; if (!val) fail(`MISSING_VALUE ${a}`);
      if (a==='--expected-tenant') opt.expectedTenant=val;
      if (a==='--confirm') opt.confirmation=val;
      if (a==='--budget-usd') opt.budgetUSD=Number(val);
    } else fail(`UNKNOWN_ARGUMENT ${a}`);
  }
  return opt;
}

// Durable and restrictive local journal: atomic replace, 0600, fsync before rename.
// First write is exclusive; never silently overwrite an existing journal.
let firstStateWrite=true;
export async function storeState(state, audio) {
  if (audio) {
    const handle=await open(PREVIEW_FILE,'wx',0o600);
    try {await handle.writeFile(assertMp3(audio)); await handle.sync();}
    finally {await handle.close();}
  }
  const temp=`${STATE_FILE}.${randomUUID()}.tmp`;
  let handle;
  try {
    handle=await open(temp,'wx',0o600);
    await handle.writeFile(JSON.stringify(state,null,2)+'\n');
    await handle.sync();
    await handle.close();handle=null;
    if (firstStateWrite && await exists(STATE_FILE)) {
      if (state.phase === 'preflight') fail('LOCAL_JOURNAL_EXISTS');
      const previous=JSON.parse(await readFile(STATE_FILE,'utf8'));
      if (previous.operation_id !== state.operation_id ||
          previous.tenant_id !== state.tenant_id ||
          previous.target !== state.target) fail('LOCAL_JOURNAL_PROVENANCE_MISMATCH');
    }
    await rename(temp,STATE_FILE);
    firstStateWrite=false;
  } catch(e) {
    if(handle) await handle.close();
    await unlink(temp).catch(()=>{});
    throw e;
  }
}
async function exists(file) {
  try { await access(file); return true; } catch { return false; }
}
async function cli() {
  const opts=parseArgs(process.argv.slice(2));
  if (opts.action==='plan') {
    console.log('P0.2 PROPOSAL_ONLY — staging-web01, orkio/Josue, OpenAI cedar.');
    console.log('No network, no credentials, no DB change. Remote writes LOCKED while AO-01 NO-GO.');
    console.log('After each uncertain write: stop + RECONCILIATION_REQUIRED + read-only GET.');
    return;
  }
  assertOptions(opts);
  if (opts.action!=='reconcile' && !REMOTE_WRITES_ENABLED) fail('EXECUTION_LOCKED_P02_AO01_NO_GO');
  if (opts.action==='apply' && ((await exists(STATE_FILE)) || (await exists(PREVIEW_FILE)))) {
    fail('EXISTING_STATE_BLOCKS_NEW_APPLY');
  }
  const state = opts.action==='apply' ? null : JSON.parse(await readFile(STATE_FILE,'utf8'));
  if (state) validateState(state,opts.expectedTenant);
  const api=new AdminAPI();
  await loginAdmin(api);
  if (opts.action==='reconcile') {
    const report=await reconcileRemote(api,opts,state);
    console.log(JSON.stringify(report,null,2));
    if (report.requiresManualReview) process.exitCode=2;
    return;
  }
  if (opts.action==='apply') {
    const result=await runApply(api,opts,ttyPrompt,storeState);
    console.log(`CAPABILITY_GOVERNED_READY phase=${result.phase} (NOT audio E2E proof)`);
  } else {
    const result=await runRollback(api,opts,state,storeState);
    console.log(`ROLLBACK_FINISHED phase=${result.phase}`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  cli().catch(err => { console.error(`STOP: ${String(err.message || 'UNEXPECTED_ERROR')}`); process.exitCode=1; });
}
