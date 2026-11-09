#!/usr/bin/env node
// Read-only checks: manifest integrity, syntax, and P0.2 offline tests.
// Does not import activation module into a write-capable runtime, does not use fetch.
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname, resolve} from 'node:path';

const base=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const lines=(await readFile(resolve(base,'SHA256SUMS.txt'),'utf8')).trim().split(/\r?\n/);
let good=0;
for(const line of lines){
  const m=line.match(/^([a-f0-9]{64})  (.+)$/);
  if(!m) throw new Error('MANIFEST_INVALID_LINE');
  const filename=resolve(base,m[2]);
  if(!filename.startsWith(base+'/') && !filename.startsWith(base+'\\\\')) throw new Error('MANIFEST_TRAVERSAL');
  const hash=createHash('sha256').update(await readFile(filename)).digest('hex');
  if(hash!==m[1]) throw new Error('HASH_MISMATCH: '+m[2]);
  good++;
}
console.log('HASHES_PASS='+good);
for(const args of [
  ['--check','josue_cedar_activation.mjs'],
  ['josue_cedar_activation.mjs','--plan'],
  ['--test','tests/activation.test.mjs'],
]){
  const run=spawnSync(process.execPath,args,{cwd:base,stdio:'inherit',timeout:60000});
  if(run.error || run.status!==0) throw new Error('OFFLINE_CHECK_FAILED: '+args.join(' '));
}
console.log('OFFLINE_VALIDATION_PASS');
console.log('REMOTE_WRITES_NOT_EXECUTED');
