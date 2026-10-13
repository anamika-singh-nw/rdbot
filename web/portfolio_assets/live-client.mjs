export class LiveClient {
  constructor(project, fetcher=globalThis.fetch.bind(globalThis)){this.project=project;this.fetcher=fetcher;this.history=[];this.state={};}
  reset(){this.history=[];this.state={};}
  async send(message){
    if(typeof globalThis.portfolioPrivacy?.ensureAIConsent !== 'function')throw new Error('Privacy controls could not load. Please reload before using the AI assistant.');
    if(!await globalThis.portfolioPrivacy.ensureAIConsent())throw new Error('Message not sent. AI processing permission was declined.');
    const response=await this.fetcher(`/api/portfolio/${this.project}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,history:this.history.slice(-6),state:this.state})});
    let data;try{data=await response.json();}catch{throw new Error('The assistant returned an unreadable response. Please try again.');}
    if(!response.ok)throw new Error(data.error||'The assistant could not answer. Please try again.');
    if(typeof data.text!=='string')throw new Error('The assistant response was incomplete. Please try again.');
    this.history.push({role:'user',text:message},{role:'assistant',text:data.text});
    this.history=this.history.slice(-6);this.state=data.state||{};
    return data;
  }
}
