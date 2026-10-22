const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require(process.env.JSDOM_PATH||'jsdom');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
async function panel(){
 const dom=new JSDOM(fs.readFileSync('pages-dist/admin.html','utf8'),{url:'https://example.test/urna/admin.html',runScripts:'outside-only'});
 const w=dom.window;
 let state={title:'Minha votação',status:'draft',digits:2,candidates:[]};
 const calls=[];let failure='';
 w.urnaSupabase={url:'https://test.supabase.co',key:'public-test-key'};
 w.confirm=()=>true;
 w.fetch=async(url,options)=>{
  const path=new URL(url).pathname,data=JSON.parse(options.body||'{}');calls.push({path,data});let result;
  if(path==='/auth/v1/token')result={access_token:'test-token'};
  else if(path==='/rest/v1/rpc/urna_admin')result={state:structuredClone(state),csrf:'bearer-auth'};
  else if(path==='/rest/v1/rpc/urna_configure'){
   if(failure)return {ok:false,json:async()=>({message:failure})};
   state={...state,title:data.p_title,digits:data.p_digits,candidates:data.p_candidates};result={ok:true};
  }else if(path==='/rest/v1/rpc/urna_transition'){
   if(state.candidates.length<2)throw Error('unsaved election');
   state.status=data.p_action==='start'?'open':'closed';result={ok:true};
  }else throw Error('Unexpected endpoint '+path);
  return {ok:true,json:async()=>result};
 };
 w.eval(fs.readFileSync('public/supabase-adapter.js','utf8'));w.eval(fs.readFileSync('public/app.js','utf8'));await settle();
 w.document.getElementById('adminEmail').value='admin@example.test';w.document.getElementById('password').value='test-password';
 w.document.getElementById('login').dispatchEvent(new w.Event('submit',{cancelable:true}));await settle();
 assert.equal(w.document.getElementById('panel').hidden,false);calls.length=0;
 return {dom,w,calls,setFailure:value=>failure=value,state:()=>state};
}
function fill(p,values=[['1','Ana'],['2','Bruno']]){
 const rows=p.w.document.querySelectorAll('.candidate-input');
 for(let i=0;i<values.length;i++){
  rows[i].querySelector('[data-key=number]').value=values[i][0];rows[i].querySelector('[data-key=name]').value=values[i][1];
 }
}
function submit(p){p.w.document.getElementById('config').dispatchEvent(new p.w.Event('submit',{cancelable:true}));}
function message(p){return p.w.document.getElementById('notice').textContent;}
test('cadastro vazio mostra erro e não tenta salvar',async()=>{
 const p=await panel();try{assert.equal(p.w.document.getElementById('config').noValidate,true);submit(p);await settle();assert.match(message(p),/pelo menos 2/);assert.equal(p.calls.length,0);}finally{p.dom.window.close();}
});
test('salva candidatos e confirma persistência',async()=>{
 const p=await panel();try{fill(p);submit(p);await settle();assert.deepEqual(p.state().candidates.map(c=>c.number),['01','02']);assert.equal(p.state().candidates[0].name,'Ana');assert.match(message(p),/2 candidatos salvos no banco/);assert.equal(p.w.document.querySelector('[data-key=number]').value,'01');}finally{p.dom.window.close();}
});
test('iniciar salva o formulário antes de abrir a votação',async()=>{
 const p=await panel();try{fill(p);p.w.document.getElementById('start').click();await settle();assert.deepEqual(p.calls.slice(0,2).map(c=>c.path),['/rest/v1/rpc/urna_configure','/rest/v1/rpc/urna_transition']);assert.equal(p.state().status,'open');assert.equal(p.w.document.getElementById('start').disabled,true);assert.equal(p.w.document.getElementById('close').disabled,false);assert.match(message(p),/Votação iniciada/);}finally{p.dom.window.close();}
});
test('erro preserva os dados e impede abertura',async()=>{
 const p=await panel();try{fill(p);p.setFailure('Falha de autorização de teste');p.w.document.getElementById('start').click();await settle();assert.match(message(p),/Falha de autorização/);assert.equal(p.w.document.querySelector('[data-key=name]').value,'Ana');assert.equal(p.state().status,'draft');assert.equal(p.calls.some(c=>c.path.endsWith('urna_transition')),false);assert.equal(p.w.document.getElementById('start').disabled,false);}finally{p.dom.window.close();}
});
test('explica números duplicados antes de enviar',async()=>{
 const p=await panel();try{fill(p,[['1','Ana'],['01','Bruno']]);submit(p);await settle();assert.match(message(p),/repetido/);assert.equal(p.calls.length,0);}finally{p.dom.window.close();}
});
