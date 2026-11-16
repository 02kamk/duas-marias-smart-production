'use strict';
// Partes operacionais fora da inspeção: aplicativo instalável, sair da conta,
// menu "Mais" do celular e resumo dos relatórios.
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

  function linhaConta(email, atual) {
    const linha = document.createElement('div'); linha.className = 'conta-linha';
    const nome = document.createElement('span');
    nome.textContent = email + (email === atual ? ' (você)' : '');
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
    acoes.append(redefinir);

    if (email !== atual) {
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
      host.replaceChildren(...d.users.map(email => linhaConta(email, d.atual)));
    } catch (e) { host.textContent = e.message; }
  }
  if ($('form-conta')) $('form-conta').addEventListener('submit', async e => {
    e.preventDefault();
    const botao = e.target.querySelector('button');
    botao.disabled = true;
    try {
      await api('/api/auth/register', { email: $('conta-email').value, password: $('conta-senha').value });
      e.target.reset();
      if ($('nova-conta')) $('nova-conta').open = false;
      listarContas();
      avisar('Conta criada. Passe o e-mail e a senha inicial para a pessoa.', 'ok');
    } catch (err) { avisar(err.message, 'erro'); } finally { botao.disabled = false; }
  });
  window.addEventListener('hashchange', () => { if (location.hash === '#ajustes') listarContas(); });
  if (location.hash === '#ajustes') listarContas();

  // Relatórios: atualiza sozinho ao abrir a página ou trocar o dia.
  async function reportSummary() {
    const dia = $('relatorio-dia');
    if (!dia) return;
    if (!dia.value) {
      const d = new Date();
      dia.value = [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-');
    }
    const suffix = '?dia=' + encodeURIComponent(dia.value);
    $('relatorio-pdf').href = '/api/relatorios/pdf' + suffix;
    try {
      const data = await api('/api/relatorios/resumo' + suffix);
      const host = $('relatorio-indicadores');
      host.replaceChildren();
      for (const [title, value] of [['Inspeções', data.total], ['Com defeito', data.defeitos], ['Conferidas', data.revisadas], ['Aguardando conferência', data.pendentes]]) {
        const card = document.createElement('article');
        const label = document.createElement('span'); label.textContent = title;
        const num = document.createElement('strong'); num.textContent = value;
        card.append(label, num); host.append(card);
      }
      const classes = $('relatorio-classes');
      classes.replaceChildren();
      if (!data.total) {
        const p = document.createElement('p'); p.className = 'texto-apoio'; p.textContent = 'Nenhuma inspeção neste dia.';
        classes.append(p);
      }
      for (const [label, count] of Object.entries(data.classes)) {
        const row = document.createElement('p'); row.textContent = label + ': ' + count;
        const bar = document.createElement('progress'); bar.max = Math.max(1, data.total); bar.value = count; bar.setAttribute('aria-label', label);
        row.append(bar); classes.append(row);
      }
    } catch (e) { $('relatorio-indicadores').textContent = e.message; }
  }
  if ($('relatorio-dia')) $('relatorio-dia').onchange = reportSummary;
  window.addEventListener('hashchange', () => { if (location.hash === '#relatorios') reportSummary(); });
  if (location.hash === '#relatorios') reportSummary();

});
