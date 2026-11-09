#!/usr/bin/env node
// Offline checklist lint. TRUE values are operator statements, not independent evidence.
// Explicitly never starts activation, OTP, or network.
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
const p=resolve(dirname(fileURLToPath(import.meta.url)),'..','gates','GATE_STATUS.json');
const g=JSON.parse(await readFile(p,'utf8'));
const required=[
'ao01_write_go','backend_source_sha_reconfirmed','db_isolation_approved',
'administrative_tenant_identity_confirmed','origin_security_cleared',
'concurrency_exclusivity_signed','cost_limit_approved_and_enforced',
'write_unlock_patch_independently_reviewed'
];
const missing=required.filter(k=>g[k]!==true);
console.log('TARGET='+g.target);
console.log('GATES_MISSING='+missing.join(','));
console.log('GATE_CHECK='+(!missing.length?'DECLARED_ONLY_NOT_INDEPENDENTLY_VERIFIED':'NO_GO'));
console.log('REMOTE_WRITES_ENABLED=false (script P0.2 retains independent lock)');
process.exitCode=missing.length?2:0;
