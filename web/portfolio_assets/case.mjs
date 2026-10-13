import {runDemo} from './demo-engine.mjs';
import {LiveClient} from './live-client.mjs?v=privacy-4';
const data=JSON.parse(document.getElementById('case-data').textContent);
document.documentElement.style.setProperty('--accent',data.color);
const set=(id,text)=>document.getElementById(id).textContent=text;
for(const key of ['category','problem','approach','lesson','limitations'])set(key,data[key]);
set('demo-title',data.demoTitle);set('demo-description',data.demoDescription);set('run',data.action);
for(const [id,values,tag]of [['architecture',data.architecture,'div'],['stack',data.stack,'span'],['capabilities',data.capabilities,'li'],['evidence',data.evidence,'li']]){
  const parent=document.getElementById(id);for(const value of values){const el=document.createElement(tag);el.textContent=value;parent.append(el);}
}
for(const [id,values]of [['scenario',data.options],['segment',data.secondary]]){
  for(const value of values){const option=document.createElement('option');option.value=value.value;option.textContent=value.label;document.getElementById(id).append(option);}
}
document.getElementById('segment-field').hidden=data.secondary.length===0;
let state={};
function render(){
  const result=runDemo(data.slug,document.getElementById('scenario').value,document.getElementById('segment').value,state);state=result.state;
  set('result-heading',result.heading);set('result-body',result.body);set('result-status',result.status);
  const rows=document.getElementById('result-rows');rows.replaceChildren();
  for(const [label,value]of result.rows){const row=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;row.append(dt,dd);rows.append(row);}
  const trace=document.getElementById('trace');trace.replaceChildren();for(const value of result.trace){const li=document.createElement('li');li.textContent=value;trace.append(li);}
}
document.getElementById('demo-form').addEventListener('submit',event=>{event.preventDefault();try{render();}catch{set('result-status','Choose a supported scenario and try again.');}});
document.getElementById('reset').addEventListener('click',()=>{state={};document.getElementById('scenario').selectedIndex=0;document.getElementById('segment').selectedIndex=0;render();});
render();

const live=new LiveClient(data.slug),log=document.getElementById('chat-log');
const input=document.getElementById('live-message'),sendButton=document.getElementById('live-send'),resetButton=document.getElementById('live-reset');
const examples={
  fundbot:['What sample campaigns can supporters help with?','Draft a short education campaign email for education supporters.'],
  'post-discharge':['Show the sample care plan and next follow-up.','Confirm I have read the sample care plan.'],
  'clinical-fhir':['What is the sample patient’s latest blood pressure, and which record is it from?','Show the heart rate and weight with their dates.'],
  aid:['Prepare a brief of the sample patient’s recorded observations and information gaps.','Which evidence is available here, and what would need a live lookup?']
};
const promptButtons=[];
for(const prompt of examples[data.slug]){const button=document.createElement('button');button.type='button';button.textContent=prompt;button.addEventListener('click',()=>{input.value=prompt;input.focus();});document.getElementById('chat-examples').append(button);promptButtons.push(button);}
function message(role,text,tools=[]){
  const article=document.createElement('article');article.className=`chat-message ${role}`;
  const label=document.createElement('strong');label.textContent=role==='user'?'You':'Live assistant';
  const body=document.createElement('p');body.textContent=text;article.append(label,body);
  if(tools.length){const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent=`Inspect ${tools.length} tool result${tools.length===1?'':'s'}`;details.append(summary);for(const tool of tools){const title=document.createElement('h4'),pre=document.createElement('pre');title.textContent=tool.name;pre.textContent=JSON.stringify(tool.result,null,2);details.append(title,pre);}article.append(details);}
  log.append(article);article.scrollIntoView({block:'nearest',behavior:'auto'});
}
let busy=false;
function lock(value){busy=value;sendButton.disabled=value;resetButton.disabled=value;input.readOnly=value;promptButtons.forEach(button=>button.disabled=value);log.setAttribute('aria-busy',String(value));}
document.getElementById('live-form').addEventListener('submit',async event=>{
  event.preventDefault();const text=input.value.trim();if(!text||busy)return;
  lock(true);set('live-status','The assistant is thinking and checking the sample data…');message('user',text);
  try{const result=await live.send(text);message('assistant',result.text,result.tool_calls||[]);input.value='';set('live-status',result.emergency?'The emergency screen responded before model inference.':'Answered live through AWS Bedrock using synthetic data.');}
  catch(error){set('live-status',error.message||'The connection failed. Please retry.');}
  finally{lock(false);input.focus();}
});
resetButton.addEventListener('click',()=>{if(busy)return;live.reset();log.replaceChildren();input.value='';set('live-status','New conversation. Sample state and recent history were cleared.');input.focus();});
