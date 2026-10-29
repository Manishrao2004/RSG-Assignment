import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AgentMessageContent } from './components/AgentMessageContent';
import './styles.css';

type Evidence = {query_id:string; sql?:string; executed_sql?:string; parameters?:Record<string,unknown>; columns:string[]; rows:Record<string,unknown>[]; truncated:boolean; report?:unknown};
type Message = {role:'user'|'assistant'; message:string; type?:string; evidence?:Evidence[]};
type Reply = Message & {thread_id:string};
async function request<T>(url:string, init?:RequestInit):Promise<T>{
  const response=await fetch(url,init);
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Please enter a question between 3 and 2,000 characters.');
  return data;
}
function App(){
  const [messages,setMessages]=useState<Message[]>([]);
  const [thread,setThread]=useState<string|null>(()=>localStorage.getItem('rsg-chat-thread'));
  const [question,setQuestion]=useState('');
  const [busy,setBusy]=useState(false);
  const [restoring,setRestoring]=useState(Boolean(thread));
  const [error,setError]=useState('');
  const [configured,setConfigured]=useState<boolean|null>(null);
  const bottom=useRef<HTMLDivElement>(null);
  const input=useRef<HTMLTextAreaElement>(null);
  useEffect(()=>{request<{mode:string}>('/api/health').then(data=>setConfigured(data.mode==='groq')).catch(()=>setError('Cannot reach the backend. Start it on port 8000.'));},[]);
  useEffect(()=>{
    if(!thread){setRestoring(false);return;}
    let cancelled=false;
    request<{messages:Message[]}>(`/api/conversations/${thread}`).then(data=>{if(!cancelled)setMessages(data.messages);}).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setRestoring(false);});
    return()=>{cancelled=true;};
  },[]);
  useEffect(()=>{bottom.current?.scrollIntoView({behavior:'smooth'});},[messages,busy,error]);
  async function send(event:React.FormEvent){
    event.preventDefault();
    const text=question.trim();
    if(!text||busy||restoring)return;
    setError('');setBusy(true);setQuestion('');
    setMessages(old=>[...old,{role:'user',message:text}]);
    try{
      const reply=await request<Reply>('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,thread_id:thread})});
      setThread(reply.thread_id);localStorage.setItem('rsg-chat-thread',reply.thread_id);
      setMessages(old=>[...old,{...reply,role:'assistant'}]);
    }catch(e){setError(e instanceof Error?e.message:'Request failed. Please try again.');setQuestion(text);}
    finally{setBusy(false);input.current?.focus();}
  }
  function newChat(){setThread(null);setMessages([]);setError('');setQuestion('');localStorage.removeItem('rsg-chat-thread');input.current?.focus();}
  return <div className="chat-app"><header><div><strong>Sales assistant</strong><span>Groq · LangGraph</span></div><button onClick={newChat} disabled={busy||restoring}>New chat</button></header>
    <main aria-label="Conversation">
      {!messages.length&&!restoring&&<div className="empty"><h1>Ask about your sales data</h1><p>Try “Which product generated the most revenue?”<br/>Then follow up with “And the least?” or “Only in North?”</p></div>}
      {restoring&&<p role="status" className="status">Restoring conversation…</p>}
      {messages.map((item,index)=><article key={index} className={`message ${item.role}`}><div className="role">{item.role==='user'?'You':'Assistant'}</div><div className="message-body">{item.role==='assistant'?<AgentMessageContent text={item.message}/>:<p>{item.message}</p>}{item.evidence?.map(e=><details key={e.query_id}><summary>Supporting figures and query</summary><div className="table-scroll"><table><thead><tr>{e.columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{e.rows.map((row,i)=><tr key={i}>{e.columns.map(column=><td key={column}>{row[column]===null?'Not available':typeof row[column]==='number'?new Intl.NumberFormat('en-US',{maximumFractionDigits:4}).format(row[column] as number):String(row[column]??'')}</td>)}</tr>)}</tbody></table></div>{e.truncated&&<small>Results limited to 100 rows. Ask for a narrower query.</small>}{e.executed_sql&&<><h3>Executed SQL</h3><pre>{e.executed_sql}</pre><small>Parameters: {JSON.stringify(e.parameters)}</small></>}{e.report!==undefined&&<pre>{JSON.stringify(e.report,null,2)}</pre>}</details>)}</div></article>)}
      {busy&&<p role="status" className="status">Thinking and checking the database…</p>}
      {error&&<div role="alert" className="error">{error}<button onClick={()=>setError('')} aria-label="Dismiss error">Dismiss</button></div>}
      <div ref={bottom}/>
    </main>
    <div className="composer"><form onSubmit={send}><label className="sr-only" htmlFor="question">Message the sales assistant</label><textarea ref={input} id="question" rows={2} value={question} onChange={e=>setQuestion(e.target.value)} maxLength={2000} placeholder="Ask a question or follow up…" disabled={busy||restoring} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();e.currentTarget.form?.requestSubmit();}}}/><button type="submit" disabled={busy||restoring||!question.trim()}>{busy?'Working…':'Send'}</button></form><p>{configured===false?'Set GROQ_API_KEY in rsg-backend/.env to enable chat.':'Completed orders · Net revenue after line discount · Currency unspecified'}</p></div>
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
