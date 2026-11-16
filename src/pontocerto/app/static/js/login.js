let setup=false;
const el=id=>document.querySelector('#'+id);
fetch('/api/auth/status').then(r=>r.json()).then(s=>{
  if(s.user){location.replace('/');return}
  setup=s.setupRequired;
  if(setup){
    el('title').textContent='Criar primeiro acesso';
    el('help').textContent='Crie a conta de quem vai cuidar do sistema. A senha precisa de 8 caracteres ou mais, com maiúscula, minúscula, número e símbolo.';
    el('help').hidden=false;
    el('submit').textContent='Criar conta e entrar';
    el('password').autocomplete='new-password';
    el('esqueceu').hidden=true;
  }
}).catch(()=>el('message').textContent='Servidor indisponível. Tente novamente.');
el('ver-senha').onchange=e=>{el('password').type=e.target.checked?'text':'password'};
el('form').onsubmit=async e=>{
  e.preventDefault();
  const b=el('submit');b.disabled=true;el('message').textContent='';
  const body=JSON.stringify({email:el('email').value,password:el('password').value});
  try{
    for(const path of (setup?['register','login']:['login'])){
      const r=await fetch('/api/auth/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body});
      const d=await r.json();
      if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'Confira e-mail e senha.');
    }
    location.replace('/');
  }catch(err){el('message').textContent=err.message}finally{b.disabled=false}
};
