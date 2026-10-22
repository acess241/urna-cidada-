'use strict';
const $=id=>document.getElementById(id), admin=document.body.dataset.admin==='true';
let csrf='',election,input='',blank=false,ready=0,sending=false,completed=false,timer;
const text=(tag,content,cls)=>{const e=document.createElement(tag);e.textContent=content;if(cls)e.className=cls;return e;};
function notice(message,error=false){$('notice').textContent=message;$('notice').className=error?'notice error':'notice';}
async function api(path,data){if(window.urnaApi)return window.urnaApi(path,data);const options={credentials:'same-origin',headers:{}};if(data!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-CSRF-Token':csrf};options.body=JSON.stringify(data);}let r;try{r=await fetch(path,options);}catch{throw Error('Sem conexão. Se você acabou de confirmar um voto, ele pode ter sido recebido. Não repita automaticamente.');}const body=await r.json();if(!r.ok)throw Error(body.error||'Falha ao processar.');return body;}
function candidateChoice(){if(blank)return {name:'VOTO EM BRANCO'};if(input.length!==election.digits)return null;return election.candidates.find(c=>c.number===input)||{name:'VOTO NULO'};}
function draw(){clearTimeout(timer);$('digits').replaceChildren(...Array.from({length:election.digits},(_,i)=>text('span',blank?'—':input[i]||'',i===input.length?'digit next':'digit')));const c=candidateChoice();$('choice').replaceChildren();if(c){$('choice').append(text('strong',c.name));if(c.party)$('choice').append(text('small',c.party));}else $('choice').textContent='Digite o número e confira sua escolha.';$('confirm').disabled=sending||!c||Date.now()<ready;$('correct').disabled=sending;$('blank').disabled=sending;if(c&&Date.now()<ready)timer=setTimeout(draw,Math.max(10,ready-Date.now()+10));}
function digit(n){if(sending||completed||blank||input.length>=election.digits)return;input+=n;ready=Date.now()+1000;draw();}
async function refresh(){try{election=await api('/api/state');$('title').textContent=election.title;$('status').textContent={draft:'Aguardando abertura pelo administrador.',open:'A votação está aberta. Confira sua escolha antes de confirmar.',closed:'A votação foi encerrada. Confira os totais abaixo.'}[election.status];$('ballot').hidden=election.status!=='open'||completed;$('waiting').hidden=election.status!=='draft';$('done').hidden=!completed||election.status!=='open';$('results').hidden=election.status!=='closed';if(election.status==='open'&&!completed){$('contest').textContent=election.title;$('candidates').replaceChildren(...election.candidates.map(c=>{const row=text('div','', 'candidate'),info=text('div','');info.append(text('strong',c.name),text('small',c.party));row.append(info,text('b',c.number));return row;}));draw();}if(election.status==='closed')renderResults();}catch(err){$('status').textContent='Votação indisponível no momento.';notice(err.message,true);}}
function renderResults(){const totals=election.totals||{},valid=election.candidates.reduce((n,c)=>n+(totals[c.number]||0),0),all=Object.values(totals).reduce((a,n)=>a+n,0),rank=[...election.candidates].sort((a,b)=>(totals[b.number]||0)-(totals[a.number]||0)),max=rank.length?totals[rank[0].number]||0:0,tie=max>0&&rank.filter(c=>totals[c.number]===max).length>1;$('ranking').replaceChildren(...rank.map(c=>{const row=text('div','', 'result-row');row.append(text('strong',c.name+' · '+c.number),text('span',(totals[c.number]||0)+' voto(s) · '+(valid?((totals[c.number]||0)/valid*100).toFixed(1):'0,0')+'%'));return row;}));$('summary').textContent=`${all} voto(s) no total · ${valid} válido(s) · ${totals.branco||0} branco(s) · ${totals.nulo||0} nulo(s). ${tie?'Empate na maior contagem.':valid?'Maior contagem: '+rank[0].name+'.':'Não houve votos válidos.'}`;}
async function vote(){if(sending||!candidateChoice()||Date.now()<ready)return;const cpf=$('cpf').value;if(!cpf.trim()){notice('Informe seu CPF para votar.',true);$('cpf').focus();return;}if(!window.confirm('Confirmar '+candidateChoice().name+'? Após o envio não será possível alterar o voto.'))return;sending=true;draw();try{await api('/api/vote',{choice:blank?'branco':input,cpf});completed=true;$('cpf').value='';input='';blank=false;notice('Voto recebido. Sua escolha não aparece em registros individuais.');await refresh();}catch(err){notice(err.message,true);}finally{sending=false;draw();}}
let adminBusy=false;
function candidateRow(c={}){
 const row=text('div','','candidate-input');
 for(const [key,label,max] of [['number','Número',5],['name','Nome do candidato',80],['party','Grupo / partido (opcional)',60]]){
  const field=document.createElement('input');
  field.placeholder=label;field.setAttribute('aria-label',label);field.dataset.key=key;
  field.value=c[key]||'';field.maxLength=max;
  if(key==='number')field.inputMode='numeric';
  row.append(field);
 }
 const remove=text('button','×','remove');remove.type='button';remove.setAttribute('aria-label','Remover candidato');
 remove.onclick=()=>{row.remove();markUnsaved();};row.append(remove);return row;
}
function markUnsaved(){if($('configStatus'))$('configStatus').textContent='Alterações ainda não salvas.';}
function adminControls(busy){
 adminBusy=busy;
 const draft=election?.status==='draft';
 $('config').querySelectorAll('input,button,select').forEach(el=>el.disabled=busy||!draft);
 $('start').disabled=busy||!draft;$('close').disabled=busy||election?.status!=='open';
 $('save').textContent=busy?'Aguarde…':'Salvar candidatos';
 $('start').textContent=busy?'Aguarde…':'Salvar e iniciar votação';
}
async function loadAdmin(){
 const data=await api('/api/admin');csrf=data.csrf;election=data.state;
 $('login').hidden=true;$('panel').hidden=false;
 $('adminStatus').textContent={draft:'RASCUNHO · Cadastre pelo menos 2 candidatos',open:'ABERTA · Recebendo votos',closed:'ENCERRADA · Resultado publicado'}[election.status];
 $('electionTitle').value=election.title;$('digitCount').value=election.digits;
 $('candidateRows').replaceChildren(...(election.candidates.length?election.candidates:[{},{}]).map(candidateRow));
 if($('configStatus'))$('configStatus').textContent=election.candidates.length?election.candidates.length+' candidatos salvos no banco.':'Nenhum candidato salvo ainda. Preencha pelo menos 2 nomes e números.';
 adminControls(false);
}
function collectConfig(){
 const title=$('electionTitle').value.trim(),digits=Number($('digitCount').value);
 if(!title){$('electionTitle').focus();throw Error('Preencha o título da votação.');}
 const candidates=[],numbers=new Set();
 for(const row of $('candidateRows').children){
  const fields=Object.fromEntries([...row.querySelectorAll('input')].map(el=>[el.dataset.key,el]));
  const name=fields.name.value.trim(),party=fields.party.value.trim(),raw=fields.number.value.trim();
  if(!name&&!party&&!raw)continue;
  if(!name){fields.name.focus();throw Error('Preencha o nome de cada candidato. Remova as linhas que não vai usar.');}
  if(!/^[0-9]+$/.test(raw)||raw.length>digits){fields.number.focus();throw Error('Informe um número com até '+digits+' dígitos para '+name+'.');}
  const number=raw.padStart(digits,'0');
  if(numbers.has(number)){fields.number.focus();throw Error('O número '+number+' está repetido. Cada candidato precisa de um número diferente.');}
  numbers.add(number);fields.number.value=number;candidates.push({number,name,party});
 }
 if(candidates.length<2)throw Error('Cadastre pelo menos 2 candidatos: preencha nome e número de cada um.');
 if(candidates.length>100)throw Error('O limite é de 100 candidatos.');
 return {title,digits,access:'cpf',candidates};
}
async function saveCandidates(start=false){
 if(adminBusy)return;
 try{
  const config=collectConfig();adminControls(true);
  notice(start?'Salvando candidatos e iniciando a votação…':'Salvando candidatos…');
  await api('/api/configure',config);
  if(start)await api('/api/start',{});
  await loadAdmin();
  notice(start?'Votação iniciada. A página dos eleitores já pode receber votos.':config.candidates.length+' candidatos salvos no banco. Você já pode iniciar a votação.');
 }catch(err){
  notice(err.message,true);$('notice').scrollIntoView?.({block:'nearest'});
 }finally{adminControls(false);}
}
async function action(path,data={}){
 if(adminBusy)return;
 adminControls(true);
 try{
  await api(path,data);
  if(path==='/api/logout'){$('login').hidden=false;$('panel').hidden=true;notice('Você saiu da administração.');return;}
  await loadAdmin();notice(path==='/api/close'?'Votação encerrada. O resultado já está público.':'Alteração concluída.');
 }catch(err){notice(err.message,true);}finally{adminControls(false);}
}
if(admin){
 $('config').noValidate=true;
 $('login').onsubmit=async ev=>{
  ev.preventDefault();
  try{
   await api('/api/login',{password:$('password').value,email:$('adminEmail')?.value});
   $('password').value='';await loadAdmin();notice('');
  }catch(err){notice(err.message,true);}
 };
 $('add').onclick=()=>{$('candidateRows').append(candidateRow());markUnsaved();};
 $('config').addEventListener('input',markUnsaved);
 $('config').onsubmit=ev=>{ev.preventDefault();saveCandidates();};
 $('start').onclick=()=>saveCandidates(true);
 $('close').onclick=()=>{if(window.confirm('Encerrar definitivamente e publicar os totais para todos?'))action('/api/close');};
 $('logout').onclick=()=>action('/api/logout');
 loadAdmin().catch(()=>{$('login').hidden=false;$('panel').hidden=true;});
}else{$('numbers').replaceChildren(...[1,2,3,4,5,6,7,8,9,0].map(n=>{const b=text('button',String(n));b.onclick=()=>digit(String(n));return b;}));$('blank').onclick=()=>{if(sending||completed)return;if(input){notice('Use CORRIGE antes de escolher BRANCO.',true);return;}blank=true;ready=Date.now()+1000;draw();};$('correct').onclick=()=>{if(sending)return;input='';blank=false;notice('Escolha apagada.');draw();};$('confirm').onclick=vote;document.addEventListener('keydown',ev=>{if(!election||election.status!=='open'||completed||['INPUT','BUTTON','A','SUMMARY'].includes(document.activeElement.tagName))return;if(/^\d$/.test(ev.key))digit(ev.key);else if(ev.key==='Backspace'){ev.preventDefault();$('correct').click();}else if(ev.key==='Enter')vote();});refresh();setInterval(()=>{if(!sending)refresh();},10000);}
