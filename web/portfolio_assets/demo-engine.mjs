const supporters=[{name:'Supporter A',segment:'education'},{name:'Supporter B',segment:'community'},{name:'Supporter C',segment:'education'}];
const bundle={resourceType:'Bundle',entry:[
  {resource:{resourceType:'Patient',id:'DEMO-001',name:[{given:['Sample'],family:'Patient'}]}},
  {resource:{resourceType:'Observation',id:'bp-earlier',code:{coding:[{code:'55284-4'}]},effectiveDateTime:'2026-09-10T09:00:00Z',component:[{code:{coding:[{code:'8480-6'}]},valueQuantity:{value:124,unit:'mmHg'}},{code:{coding:[{code:'8462-4'}]},valueQuantity:{value:80,unit:'mmHg'}}]}},
  {resource:{resourceType:'Observation',id:'bp-latest',code:{coding:[{code:'55284-4'}]},effectiveDateTime:'2026-09-18T09:00:00Z',component:[{code:{coding:[{code:'8480-6'}]},valueQuantity:{value:120,unit:'mmHg'}},{code:{coding:[{code:'8462-4'}]},valueQuantity:{value:78,unit:'mmHg'}}]}},
  {resource:{resourceType:'Observation',id:'heart-rate',code:{coding:[{code:'8867-4'}]},effectiveDateTime:'2026-09-18T09:00:00Z',valueQuantity:{value:72,unit:'/min'}}},
  {resource:{resourceType:'Observation',id:'weight',code:{coding:[{code:'29463-7'}]},effectiveDateTime:'2026-09-18T09:00:00Z',valueQuantity:{value:68,unit:'kg'}}}
]};
const supported={fundbot:['education','meals'],'post-discharge':['plan','confirm','followup'],'clinical-fhir':['blood-pressure','heart-rate','weight'],aid:['followup','medication']};

export function runDemo(slug, choice, segment='', state={}){
  if(!supported[slug]?.includes(choice))throw new Error('Choose a supported demo scenario.');
  const result={heading:'',rows:[],body:'',trace:[],status:'',state:{...state}};
  if(slug==='fundbot'){
    if(!['all','education','community'].includes(segment))throw new Error('Choose a supported donor segment.');
    const audience=supporters.filter(s=>segment==='all'||s.segment===segment);
    const topic=choice==='education'?'learning materials':'community meals';
    result.heading='Campaign draft preview';
    result.rows=[['Audience',audience.map(s=>s.name).join(', ')],['Example supporters',String(audience.length)],['Campaign',topic]];
    result.body=`Dear ${audience[0].name},\n\nWe are sharing an example ${topic} campaign. If this cause interests you, please contact the organization to learn about the campaign and how to participate.\n\nThank you for your support.\n\nThis is a sample draft using fictional supporter data.`;
    result.trace=['Choose campaign topic','Filter synthetic donor segment','Preview a personalized draft','Await human review'];
    result.status='Preview only — no email sent';
  }else if(slug==='clinical-fhir'){
    const code={'blood-pressure':'55284-4','heart-rate':'8867-4',weight:'29463-7'}[choice];
    const observations=bundle.entry.map(e=>e.resource).filter(r=>r.resourceType==='Observation'&&r.code.coding.some(c=>c.code===code)).sort((a,b)=>Date.parse(b.effectiveDateTime)-Date.parse(a.effectiveDateTime));
    const latest=observations[0];
    const value=latest.component?`${latest.component.find(c=>c.code.coding[0].code==='8480-6').valueQuantity.value} / ${latest.component.find(c=>c.code.coding[0].code==='8462-4').valueQuantity.value} mmHg`:`${latest.valueQuantity.value} ${latest.valueQuantity.unit}`;
    result.heading='Structured observation result';
    result.rows=[['Patient','Sample Patient · DEMO-001'],['LOINC code',code],['Date',latest.effectiveDateTime.slice(0,10)],['Value',value],['Matching observations',String(observations.length)],['Source',`Synthetic FHIR fixture · Observation/${latest.id}`]];
    result.body='The lookup returns dated source values without a diagnosis or treatment recommendation.';
    result.trace=['Map observation name to code','Filter Observation resources','Order matching timestamps','Extract latest values'];
    result.status='Synthetic observation — no real patient record accessed';
  }else if(slug==='post-discharge'){
    result.trace=['Select sample patient','Read synthetic care-plan data','Return the requested workflow information'];
    if(choice==='confirm')result.state.confirmed=true;
    if(choice==='followup'){
      result.heading='Sample follow-up';result.rows=[['Patient','Sample Patient'],['Follow-up','Care-team review'],['Example date','2026-09-25'],['Status','Illustrative entry; no appointment booked']];
    }else{
      result.heading=choice==='confirm'?'Task confirmed in the demo':'Sample care-plan checklist';
      result.rows=[['Read the provided plan',result.state.confirmed?'Confirmed in this demo':'Not yet confirmed'],['Prepare questions','Write down questions for the care team'],['Review appointment information','Confirm details with the provider']];
    }
    result.body='This demonstrates reading a workflow and updating temporary UI state. Clinical instructions must come from the treating care team.';
    result.status='Browser-only example — no AWS record updated';
  }else if(slug==='aid'){
    result.heading='Example evidence-review plan';
    result.rows=[['Patient fact','Synthetic profile: Sample Patient'],['Record context',choice==='medication'?'A medication list is present in the sample profile':'A follow-up entry is present in the sample profile'],['Information gap','No live source data or external evidence has been fetched'],['Review boundary','A clinician reviews facts and any retrieved evidence']];
    result.trace=choice==='medication'?['get_patient_fhir','check_medications','Separate record facts from external evidence','Present sources and information gaps']:['get_patient_fhir','Review sample follow-up context','Identify missing information','Present sources and information gaps'];
    result.body='This scripted example illustrates context selection and relevant tool routing. It is not an AI-generated clinical brief and makes no medical recommendation.';
    result.status='Scripted example — no live clinical or regulatory lookup';
  }
  return result;
}
