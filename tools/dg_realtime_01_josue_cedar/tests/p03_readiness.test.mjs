import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,rm,copyFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {inspectLocal,P02_HASHES,REQUIRED_GATES} from '../scripts/p03_readiness.mjs';

const source=resolve(import.meta.dirname,'..');
async function setup() {
  const root=await mkdtemp(join(tmpdir(),'dg-p03-'));
  await mkdir(join(root,'tests'),{recursive:true});
  await mkdir(join(root,'gates'),{recursive:true});
  for(const n of Object.keys(P02_HASHES)) {
    await copyFile(join(source,n),join(root,n));
  }
  await copyFile(join(source,'gates/GATE_STATUS.json'),join(root,'gates/GATE_STATUS.json'));
  return root;
}
test('untouched P0.2, all flags false -> NO_GO',async t=>{
  const root=await setup();t.after(()=>rm(root,{recursive:true,force:true}));
  const r=await inspectLocal(root);
  assert.equal(r.p02_immutable,true);
  assert.equal(r.execution,'NO_GO');
  assert.equal(r.gates_missing.length,8);
});
test('manually setting all booleans true never grants GO',async t=>{
  const root=await setup();t.after(()=>rm(root,{recursive:true,force:true}));
  const f=join(root,'gates/GATE_STATUS.json');
  const d=JSON.parse(await readFile(f,'utf8'));
  for(const k of REQUIRED_GATES) d[k]=true;
  await writeFile(f,JSON.stringify(d));
  const r=await inspectLocal(root);
  assert.equal(r.execution,'NO_GO');
  assert.equal(r.gates_missing.length,0);
  assert.equal(r.gates_self_declared.length,8);
});
test('tampered P0.2 script is flagged as source drift',async t=>{
  const root=await setup();t.after(()=>rm(root,{recursive:true,force:true}));
  const f=join(root,'josue_cedar_activation.mjs');
  await writeFile(f,(await readFile(f,'utf8')).replace('REMOTE_WRITES_ENABLED = false','REMOTE_WRITES_ENABLED = true'));
  const r=await inspectLocal(root);
  assert.equal(r.p02_immutable,false);
  assert.equal(r.reason,'P02_SOURCE_DRIFT');
  assert.equal(r.execution,'NO_GO');
});
test('tampered P0.2 tests flagged as source drift',async t=>{
  const root=await setup();t.after(()=>rm(root,{recursive:true,force:true}));
  const f=join(root,'tests/activation.test.mjs');
  await writeFile(f,(await readFile(f,'utf8'))+'\n// changed\n');
  assert.equal((await inspectLocal(root)).p02_immutable,false);
});
test('missing schema field is fail-closed',async t=>{
  const root=await setup();t.after(()=>rm(root,{recursive:true,force:true}));
  const f=join(root,'gates/GATE_STATUS.json');
  const d=JSON.parse(await readFile(f,'utf8'));
  delete d.ao01_write_go;
  await writeFile(f,JSON.stringify(d));
  await assert.rejects(inspectLocal(root),/INVALID_GATE_SCHEMA/);
});
test('incorrect target fails closed',async t=>{
  const root=await setup();t.after(()=>rm(root,{recursive:true,force:true}));
  const f=join(root,'gates/GATE_STATUS.json');
  const d=JSON.parse(await readFile(f,'utf8'));
  d.target='production';
  await writeFile(f,JSON.stringify(d));
  await assert.rejects(inspectLocal(root),/TARGET_GATE_MISMATCH/);
});
