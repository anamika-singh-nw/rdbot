import test, {beforeEach, afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {LiveClient} from '../web/portfolio_assets/live-client.mjs';
beforeEach(() => { globalThis.portfolioPrivacy = {ensureAIConsent: async () => true}; });
afterEach(() => { delete globalThis.portfolioPrivacy; });

test('default browser fetch keeps its global receiver',async t=>{
  t.mock.method(globalThis,'fetch',function(){
    if(this!==globalThis)throw new TypeError("Failed to execute 'fetch' on 'Window': Illegal invocation");
    return Promise.resolve({ok:true,json:async()=>({text:'Bound fetch works',state:{}})});
  });
  const client=new LiveClient('fundbot');
  assert.equal((await client.send('Show sample campaigns')).text,'Bound fetch works');
});

test('client sends successful conversation history and returned state on followup',async()=>{
  const requests=[];
  const client=new LiveClient('post-discharge',async(url,options)=>{
    requests.push({url,body:JSON.parse(options.body)});
    return {ok:true,json:async()=>({text:'Done',state:{plan_read:true},tool_calls:[]})};
  });
  await client.send('Confirm I read the plan');
  await client.send('Show my status');
  assert.equal(requests[0].url,'/api/portfolio/post-discharge');
  assert.deepEqual(requests[1].body.history,[{role:'user',text:'Confirm I read the plan'},{role:'assistant',text:'Done'}]);
  assert.equal(requests[1].body.state.plan_read,true);
});
test('failed requests do not pollute history and show the server error',async()=>{
  const client=new LiveClient('aid',async()=>({ok:false,json:async()=>({error:'Demo limit reached'})}));
  await assert.rejects(client.send('Show sample record'),/Demo limit reached/);
  assert.deepEqual(client.history,[]);
});
test('new conversation clears history and sample state',async()=>{
  const client=new LiveClient('fundbot',async()=>({ok:true,json:async()=>({text:'Sample answer',state:{plan_read:true}})}));
  await client.send('What campaigns?');client.reset();
  assert.deepEqual(client.history,[]);assert.deepEqual(client.state,{});
});

test('declining AI processing sends no request and preserves empty history', async t => {
  const previous = globalThis.portfolioPrivacy;
  globalThis.portfolioPrivacy = {ensureAIConsent: async () => false};
  t.after(() => { if (previous === undefined) delete globalThis.portfolioPrivacy; else globalThis.portfolioPrivacy = previous; });
  let requests = 0;
  const client = new LiveClient('fundbot', async () => { requests++; });
  await assert.rejects(client.send('Do not transmit this'), /permission was declined/);
  assert.equal(requests, 0);
  assert.deepEqual(client.history, []);
});

test('agreeing to AI processing permits the chosen request', async t => {
  const previous = globalThis.portfolioPrivacy;
  globalThis.portfolioPrivacy = {ensureAIConsent: async () => true};
  t.after(() => { if (previous === undefined) delete globalThis.portfolioPrivacy; else globalThis.portfolioPrivacy = previous; });
  let requests = 0;
  const client = new LiveClient('fundbot', async () => { requests++; return {ok:true,json:async()=>({text:'Permitted answer'})}; });
  assert.equal((await client.send('Public sample question')).text, 'Permitted answer');
  assert.equal(requests, 1);
});


test('missing privacy controls fail closed before any network request', async () => {
  delete globalThis.portfolioPrivacy;
  let requests = 0;
  const client = new LiveClient('fundbot', async () => { requests++; });
  await assert.rejects(client.send('Do not transmit this'), /Privacy controls could not load/);
  assert.equal(requests, 0);
  assert.deepEqual(client.history, []);
});
