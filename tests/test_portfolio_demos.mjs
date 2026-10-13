import test from 'node:test';
import assert from 'node:assert/strict';
import {runDemo} from '../web/portfolio_assets/demo-engine.mjs';

test('donor segment excludes other sample supporters',()=>{
  const result=runDemo('fundbot','education','education',{});
  assert.deepEqual(result.rows.filter(r=>r[0]==='Audience').map(r=>r[1]),['Supporter A, Supporter C']);
  assert.equal(result.status,'Preview only — no email sent');
});
test('FHIR lookup returns the newest component observation',()=>{
  const result=runDemo('clinical-fhir','blood-pressure','',{});
  assert.ok(result.rows.some(r=>r[0]==='Date'&&r[1]==='2026-09-18'));
  assert.ok(result.rows.some(r=>r[0]==='Value'&&r[1]==='120 / 78 mmHg'));
});
test('FHIR observation choices do not use another observation code',()=>{
  const result=runDemo('clinical-fhir','heart-rate','',{});
  assert.ok(result.rows.some(r=>r[0]==='LOINC code'&&r[1]==='8867-4'));
  assert.ok(result.rows.some(r=>r[0]==='Value'&&r[1]==='72 /min'));
});
test('post-discharge task state is session-local and can be read back',()=>{
  const state={};const result=runDemo('post-discharge','confirm','',state);
  assert.deepEqual(state,{});
  assert.equal(result.state.confirmed,true);
  assert.ok(runDemo('post-discharge','plan','',result.state).rows.some(r=>r[0]==='Read the provided plan'&&r[1]==='Confirmed in this demo'));
});
test('AID sample medication profile exposes a review tool without claiming live lookup',()=>{
  const result=runDemo('aid','medication','',{});
  assert.ok(result.trace.includes('check_medications'));
  assert.equal(result.status,'Scripted example — no live clinical or regulatory lookup');
});
test('unsupported project or scenario is rejected',()=>{
  assert.throws(()=>runDemo('unknown','x','',{}));
  assert.throws(()=>runDemo('clinical-fhir','invalid','',{}));
});
