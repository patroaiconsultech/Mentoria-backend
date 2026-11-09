#!/usr/bin/env node
// DG-REALTIME-01 P0.3 local release-readiness verifier.
// NO NETWORK, NO OPERATOR CREDENTIALS, NO WRITES, NO REMOTE GO.
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {dirname, resolve} from 'node:path';

export const P02_HASHES = Object.freeze({
  'josue_cedar_activation.mjs': '339cb80d33032a14d821db3ee4f2db4d20678f9e6a0d351f12bb362b384b943b',
  'tests/activation.test.mjs': 'e72bc95edbdaab398e518a67f9f12b18ddb45b14bdf83e49c404ab67bbefa00f'
});
export const REQUIRED_GATES = Object.freeze([
  'ao01_write_go', 'backend_source_sha_reconfirmed',
  'db_isolation_approved', 'administrative_tenant_identity_confirmed',
  'origin_security_cleared', 'concurrency_exclusivity_signed',
  'cost_limit_approved_and_enforced', 'write_unlock_patch_independently_reviewed'
]);

export async function inspectLocal(root) {
  const report={target:'staging-web01',agent:'orkio',p02_immutable:true,
    gates_missing:[],gates_self_declared:[],execution:'NO_GO',
    reason:'NO_INDEPENDENT_REMOTE_VERIFICATION'};
  for (const [name, expected] of Object.entries(P02_HASHES)) {
    const bytes=await readFile(resolve(root,name));
    if(createHash('sha256').update(bytes).digest('hex')!==expected) {
      report.p02_immutable=false;
    }
  }
  const source=await readFile(resolve(root,'josue_cedar_activation.mjs'),'utf8');
  if(!source.includes('export const REMOTE_WRITES_ENABLED = false;')) report.p02_immutable=false;
  const gate=JSON.parse(await readFile(resolve(root,'gates/GATE_STATUS.json'),'utf8'));
  if(gate.target!=='staging-web01' || gate.agent!=='orkio/Josué') {
    throw new Error('TARGET_GATE_MISMATCH');
  }
  for (const key of REQUIRED_GATES) {
    if(typeof gate[key]!=='boolean') throw new Error('INVALID_GATE_SCHEMA_'+key);
    if(gate[key]) report.gates_self_declared.push(key);
    else report.gates_missing.push(key);
  }
  // These values are self-reported only. An operator can set booleans true;
  // they NEVER constitute audit evidence or unlock a release.
  if(!report.p02_immutable) report.reason='P02_SOURCE_DRIFT';
  else if(report.gates_missing.length) report.reason='GATES_PENDING';
  return report;
}

async function main() {
  const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
  const report=await inspectLocal(root);
  console.log(JSON.stringify(report,null,2));
  process.exitCode=2; // Explicitly NO-GO even if all local booleans are true.
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(e=>{
    console.error('READINESS_CHECK_FAILED: '+String(e.message).slice(0,100));
    process.exitCode=2;
  });
}
