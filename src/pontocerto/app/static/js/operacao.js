'use strict';
// Partes operacionais fora da inspeção: aplicativo instalável, sair da conta,
// menu "Mais" do celular e contas em Ajustes.
document.addEventListener('DOMContentLoaded', () => {
  const $ = id => document.getElementById(id);
  let installPrompt = null;

  async function api(path, body) {
    const r = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (r.status === 401) { location.assign('/login'); throw Error('Sessão encerrada'); }
    const d = await r.json();
    if (!r.ok || d.erro) throw Error(d.erro || (typeof d.detail === 'string' ? d.detail : (Array.isArray(d.detail) && d.detail[0] && d.detail[0].msg) || 'Operação recusada.'));
    return d;
  }

  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});

  const botoesInstalar = () => document.querySelectorAll('#instalar-app,[data-instalar]');
  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault();
    installPrompt = e;
    botoesInstalar().forEach(b => { b.hidden = false; });
  });
  botoesInstalar().forEach(b => b.addEventListener('click', async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    installPrompt = null;
    botoesInstalar().forEach(x => { x.hidden = true; });
  }));

  document.querySelectorAll('[data-sair]').forEach(b => b.addEventListener('click', async () => {
    try { await api('/api/auth/logout', {}); } finally { location.assign('/login'); }
  }));

  // Menu "Mais" da barra inferior do celular.
  const mais = $('tab-mais'), menu = $('menu-mais');
  function fecharMenu() { if (menu) { menu.hidden = true; mais.setAttribute('aria-expanded', 'false'); } }
  if (mais && menu) {
    mais.addEventListener('click', e => {
      e.stopPropagation();
      menu.hidden = !menu.hidden;
      mais.setAttribute('aria-expanded', String(!menu.hidden));
    });
    document.addEventListener('click', e => { if (!menu.hidden && !menu.contains(e.target)) fecharMenu(); });
    menu.addEventListener('click', e => { if (e.target.closest('[data-pagina]')) fecharMenu(); });
  }

  // Contas: quem tem acesso, com redefinir senha e remover na própria tela.
  const avisar = (texto, tipo) => { if (window.PontoCerto) window.PontoCerto.toast(texto, tipo); };
  const REGRA_SENHA = 'A senha precisa de 8 caracteres ou mais, com maiúscula, minúscula, número e símbolo.';

  function linhaConta(conta, atual, souAdmin) {
    const email = conta.email;
    const linha = document.createElement('div'); linha.className = 'conta-linha';
    const nome = document.createElement('span'); nome.className = 'conta-nome';
    const inicial = document.createElement('span'); inicial.className = 'avatar'; inicial.setAttribute('aria-hidden', 'true');
    inicial.textContent = email.charAt(0).toUpperCase();
    const textoEmail = document.createElement('span'); textoEmail.textContent = email;
    nome.append(inicial, textoEmail);
    if (email === atual) { const voce = document.createElement('small'); voce.className = 'etiqueta'; voce.textContent = 'você'; nome.append(voce); }
    if (conta.admin) { const adm = document.createElement('small'); adm.className = 'etiqueta etiqueta-neutra'; adm.textContent = 'administrador'; nome.append(adm); }
    if (!conta.aprovado) { const pend = document.createElement('small'); pend.className = 'etiqueta etiqueta-atencao'; pend.textContent = 'aguardando aprovação'; nome.append(pend); }
    const acoes = document.createElement('span'); acoes.className = 'linha-botoes';
    const area = document.createElement('div'); area.className = 'conta-form'; area.hidden = true;

    const redefinir = document.createElement('button');
    redefinir.type = 'button'; redefinir.className = 'btn btn-quieto'; redefinir.textContent = 'Redefinir senha';
    redefinir.onclick = () => {
      area.replaceChildren();
      const campo = document.createElement('label'); campo.className = 'campo';
      const rotulo = document.createElement('span'); rotulo.className = 'campo-rotulo'; rotulo.textContent = 'Nova senha de ' + email;
      const senha = document.createElement('input'); senha.type = 'password'; senha.className = 'entrada'; senha.autocomplete = 'new-password'; senha.maxLength = 128;
      const ajuda = document.createElement('span'); ajuda.className = 'campo-ajuda'; ajuda.textContent = REGRA_SENHA;
      campo.append(rotulo, senha, ajuda);
      const salvar = document.createElement('button'); salvar.type = 'button'; salvar.className = 'btn btn-secundario'; salvar.textContent = 'Salvar senha';
      salvar.onclick = async () => {
        salvar.disabled = true;
        try {
          await api('/api/auth/password', { email, password: senha.value });
          area.hidden = true;
          avisar(email === atual ? 'Senha trocada. Entre de novo com a senha nova.' : 'Senha trocada. Passe a senha nova para a pessoa.', 'ok');
          if (email === atual) setTimeout(() => location.assign('/login'), 1500);
        } catch (err) { avisar(err.message, 'erro'); } finally { salvar.disabled = false; }
      };
      const cancelar = document.createElement('button'); cancelar.type = 'button'; cancelar.className = 'btn btn-quieto'; cancelar.textContent = 'Cancelar';
      cancelar.onclick = () => { area.hidden = true; };
      area.append(campo, salvar, cancelar); area.hidden = false; senha.focus();
    };
    // Conta nova: o administrador aprova ou recusa.
    if (souAdmin && !conta.aprovado) {
      const aprovar = document.createElement('button');
      aprovar.type = 'button'; aprovar.className = 'btn btn-principal btn-pequeno'; aprovar.textContent = 'Aprovar';
      aprovar.onclick = async () => {
        aprovar.disabled = true;
        try { await api('/api/auth/aprovar', { email }); avisar('Acesso aprovado. ' + email + ' já pode entrar.', 'ok'); listarContas(); }
        catch (err) { avisar(err.message, 'erro'); aprovar.disabled = false; }
      };
      const recusar = document.createElement('button');
      recusar.type = 'button'; recusar.className = 'btn btn-quieto btn-pequeno'; recusar.textContent = 'Recusar';
      recusar.onclick = async () => {
        recusar.disabled = true;
        try { await api('/api/auth/remove', { email }); avisar('Pedido de acesso recusado.', 'ok'); listarContas(); }
        catch (err) { avisar(err.message, 'erro'); recusar.disabled = false; }
      };
      acoes.append(aprovar, recusar);
      linha.append(nome, acoes);
      return linha;
    }
    // A própria senha se troca em Perfil › Meus dados; aqui é só para ajudar outra pessoa.
    if (souAdmin && email !== atual) acoes.append(redefinir);

    if (souAdmin && email !== atual) {
      const remover = document.createElement('button');
      remover.type = 'button'; remover.className = 'btn btn-quieto'; remover.textContent = 'Remover';
      remover.onclick = () => {
        area.replaceChildren();
        const texto = document.createElement('span'); texto.textContent = 'Remover o acesso de ' + email + '?';
        const sim = document.createElement('button'); sim.type = 'button'; sim.className = 'btn btn-perigo btn-pequeno'; sim.textContent = 'Remover acesso';
        sim.onclick = async () => {
          sim.disabled = true;
          try { await api('/api/auth/remove', { email }); avisar('Acesso removido.', 'ok'); listarContas(); }
          catch (err) { avisar(err.message, 'erro'); sim.disabled = false; }
        };
        const nao = document.createElement('button'); nao.type = 'button'; nao.className = 'btn btn-quieto'; nao.textContent = 'Cancelar';
        nao.onclick = () => { area.hidden = true; };
        area.append(texto, sim, nao); area.hidden = false;
      };
      acoes.append(remover);
    }
    linha.append(nome, acoes, area);
    return linha;
  }

  async function listarContas() {
    const host = $('contas-lista');
    if (!host) return;
    try {
      const d = await api('/api/auth/users');
      const contas = (d.contas || d.users.map(email => ({ email, aprovado: true })))
        .sort((a, b) => Number(a.aprovado) - Number(b.aprovado));
      host.replaceChildren(...contas.map(c => linhaConta(c, d.atual, d.admin)));
    } catch (e) { host.textContent = e.message; }
  }
  window.listarContas = listarContas;
  // Perfil pode ter aberto direto na aba Ajustes antes deste arquivo terminar de carregar.
  if ($('aba-ajustes') && !$('aba-ajustes').hidden) listarContas();

});
