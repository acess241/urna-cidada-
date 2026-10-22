'use strict';
// Carregado somente no pacote GitHub Pages. A chave pública não concede administração.
(()=>{
const config=window.urnaSupabase||{};let token='';
async function request(path,data,authorized=false){
 if(!config.url||!config.key)throw Error('Conexão ainda não configurada. O administrador precisa concluir a configuração do Supabase.');
 const headers={apikey:config.key,'Content-Type':'application/json'};
 if(authorized){if(!token)throw Error('Entre como administrador.');headers.Authorization='Bearer '+token;}
 let r;try{r=await fetch(config.url+path,{method:'POST',headers,body:JSON.stringify(data||{})});}catch{throw Error('Sem conexão. Se acabou de confirmar, não repita o voto automaticamente: ele pode ter sido recebido.');}
 const body=await r.json();if(!r.ok){if(body.code==='PGRST202')throw Error('A votação está em preparação. Falta instalar a estrutura da urna no Supabase.');throw Error(body.message||body.msg||body.error_description||'Não foi possível concluir a operação.');}return body;
}
window.urnaApi=async(path,data)=>{
 if(path==='/api/state')return request('/rest/v1/rpc/urna_state',{});
 if(path==='/api/login'){
  const auth=await request('/auth/v1/token?grant_type=password',{email:data.email,password:data.password});
  token=auth.access_token;
  try{await request('/rest/v1/rpc/urna_admin',{},true);}catch(err){token='';throw err;}
  return {ok:true};
 }
 if(path==='/api/logout'){try{await request('/auth/v1/logout',{},true);}finally{token='';}return {ok:true};}
 if(path==='/api/admin')return request('/rest/v1/rpc/urna_admin',{},true);
 if(path==='/api/configure')return request('/rest/v1/rpc/urna_configure',{p_title:data.title,p_digits:data.digits,p_candidates:data.candidates},true);
 if(path==='/api/start'||path==='/api/close')return request('/rest/v1/rpc/urna_transition',{p_action:path.split('/').pop()},true);
 if(path==='/api/vote')return request('/rest/v1/rpc/urna_vote',{p_cpf:data.cpf,p_choice:data.choice});
 throw Error('Operação desconhecida.');
};
})();
