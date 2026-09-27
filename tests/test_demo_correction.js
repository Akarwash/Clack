/* Exercise the actual asynchronous Demo correction function with delayed responses. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('clack/ui/demo.js', 'utf8');
const code = source.slice(source.indexOf('async function correctWithClaude('), source.indexOf('// ---- render ----'));
function fixture() {
  const elements = new Map();
  const requests = [];
  const element = id => {
    if (!elements.has(id)) elements.set(id, {textContent:'', classList:{remove(){}}, querySelector(){return element(id+'_label');}});
    return elements.get(id);
  };
  const context = vm.createContext({$:element, AbortController, recordingGeneration:1, correctionControllers:[],
    renderTranscript(el,text){el.textContent=text;},
    fetch(url,opts){return new Promise(resolve => requests.push({url,opts,resolve}));}
  });
  vm.runInContext(code,context);
  return {context,requests,element,run:(clip,protectedInput=false)=>context.correctWithClaude(clip,protectedInput,1)};
}
const response = text => ({ok:true,json:async()=>({text,provider:'claude',correction_ms:10,usage:{input_tokens:4,output_tokens:2}})});

test('two panels make independent candidate-only requests',async()=>{
  const f=fixture();
  const raw={per_key:[[['a',1]]]}, protectedClip={per_key:[[['b',1]]]};
  const first=f.run(raw),second=f.run(protectedClip,true);
  assert.equal(f.requests.length,2);
  assert.deepEqual(JSON.parse(f.requests[0].opts.body),{provider:'claude',candidates:raw.per_key});
  assert.deepEqual(JSON.parse(f.requests[1].opts.body),{provider:'claude',candidates:protectedClip.per_key});
  f.requests[1].resolve(response('b')); await second;
  assert.equal(f.element('protected_corrected').textContent,'b');
  assert.equal(f.element('corrected').textContent,'');
  f.requests[0].resolve(response('a')); await first;
  assert.equal(f.element('corrected').textContent,'a');
});
test('a stale response cannot overwrite a newer recording',async()=>{
  const f=fixture();const pending=f.run({per_key:[[['a',1]]]});
  f.context.recordingGeneration=2;f.element('corrected').textContent='new result';
  f.requests[0].resolve(response('old result'));await pending;
  assert.equal(f.element('corrected').textContent,'new result');
});
test('fallback is explicitly labeled',async()=>{
  const f=fixture();const pending=f.run({per_key:[[['a',1]]]});
  f.requests[0].resolve({ok:true,json:async()=>({text:'a',provider:'local',correction_ms:3,fallback_reason:'refused'})});await pending;
  assert.match(f.element('correctedPanel_label').textContent,/fallback/);
  assert.match(f.element('correctionStatus').textContent,/refused/);
});
