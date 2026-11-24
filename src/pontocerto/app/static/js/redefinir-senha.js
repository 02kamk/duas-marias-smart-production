// O link do e-mail do Supabase chega como /redefinir-senha#access_token=...&type=recovery
// (ou #error=...&error_description=... quando expirou). O fragmento não vai ao servidor.
const el=id=>document.querySelector('#'+id);
const params=new URLSearchParams(location.hash.slice(1));
const token=params.get('access_token');
history.replaceState(null,'',location.pathname);  // tira o token da barra de endereço

function semLink(msg){
  el('form').hidden=true;
  el('message').textContent=msg;
}
if(params.get('error'))semLink('O link expirou ou já foi usado. Na tela de entrar, use "Esqueci a senha" para pedir outro.');
else if(!token)semLink('Abra esta página pelo link que chegou no seu e-mail.');

el('ver-senha').onchange=e=>{for(const id of ['password','password2'])el(id).type=e.target.checked?'text':'password'};
el('form').onsubmit=async e=>{
  e.preventDefault();
  el('message').className='campo-erro';el('message').textContent='';
  if(el('password').value!==el('password2').value){el('message').textContent='As senhas não conferem.';return}
  const b=el('submit');b.disabled=true;
  try{
    const r=await fetch('/api/auth/nova-senha',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({access_token:token,password:el('password').value})});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'Não foi possível salvar a senha.');
    el('form').hidden=true;
    el('message').className='campo-ok';
    el('message').textContent='Senha salva. Agora é só entrar com ela.';
  }catch(err){el('message').textContent=err.message}finally{b.disabled=false}
};
