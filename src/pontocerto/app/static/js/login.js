let modo='entrar', recuperacao=false;
const el=id=>document.querySelector('#'+id);
const telas={
  entrar:{titulo:'Entrar',botao:'Entrar',ajuda:''},
  criar:{titulo:'Criar conta',botao:'Criar conta e entrar',
    ajuda:'A senha precisa de 8 caracteres ou mais, com maiúscula, minúscula, número e símbolo.'},
  esqueci:{titulo:'Redefinir a senha',botao:'Enviar link por e-mail',
    ajuda:'Digite seu e-mail. Se ele tiver conta, chega um link para criar uma senha nova.'},
};

function trocarModo(novo){
  modo=novo;
  const t=telas[modo], criar=modo==='criar', esqueci=modo==='esqueci';
  el('title').textContent=t.titulo;
  el('submit').textContent=t.botao;
  el('help').textContent=t.ajuda; el('help').hidden=!t.ajuda;
  el('campo-senha').hidden=esqueci; el('password').required=!esqueci;
  el('password').autocomplete=criar?'new-password':'current-password';
  el('campo-senha2').hidden=!criar; el('password2').required=criar;
  el('campo-ver').hidden=esqueci;
  el('ir-criar').hidden=modo!=='entrar';
  el('ir-entrar').hidden=modo==='entrar';
  el('ir-entrar-texto').textContent=esqueci?'Lembrou a senha?':'Já tem conta?';
  el('ir-esqueci').hidden=modo!=='entrar'||!recuperacao;
  el('esqueceu').hidden=modo!=='entrar'||recuperacao;
  el('message').textContent=''; el('message').className='campo-erro';
  el(esqueci?'email':(el('email').value?'password':'email')).focus();
}
document.querySelectorAll('[data-modo]').forEach(b=>b.onclick=()=>trocarModo(b.dataset.modo));
el('ver-senha').onchange=e=>{for(const id of ['password','password2'])el(id).type=e.target.checked?'text':'password'};

fetch('/api/auth/status').then(r=>r.json()).then(s=>{
  if(s.user){location.replace('/');return}
  recuperacao=!!s.recuperacao;
  el('ir-esqueci').hidden=!recuperacao;
  el('esqueceu').hidden=recuperacao;
}).catch(()=>el('message').textContent='Servidor indisponível. Tente novamente.');

async function enviar(path,dados){
  const r=await fetch('/api/auth/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(dados)});
  const d=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'Confira e-mail e senha.');
  return d;
}
el('form').onsubmit=async e=>{
  e.preventDefault();
  el('message').textContent='';el('message').className='campo-erro';
  if(modo==='criar'&&el('password').value!==el('password2').value){el('message').textContent='As senhas não conferem.';return}
  const b=el('submit');b.disabled=true;
  try{
    if(modo==='esqueci'){
      await enviar('esqueci',{email:el('email').value});
      el('message').className='campo-ok';
      el('message').textContent='Pronto. Se esse e-mail tiver conta, o link chega em alguns minutos. Confira também o spam.';
      return;
    }
    const dados={email:el('email').value,password:el('password').value};
    if(modo==='criar'){
      const r=await enviar('register',dados);
      if(r.pendente){
        trocarModo('entrar');
        el('password').value='';
        el('message').className='campo-ok';
        el('message').textContent='Conta criada. Um administrador precisa aprovar seu acesso; depois é só entrar.';
        return;
      }
    }
    await enviar('login',dados);
    location.replace('/');
  }catch(err){el('message').textContent=err.message}finally{b.disabled=false}
};
