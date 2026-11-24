'use strict';
// Telas Início, Relatórios e Perfil, e o perfil no rodapé do menu.
// app.js troca as páginas e chama window.Paineis[pagina]() ao entrar em cada uma.
(function () {
  const $ = id => document.getElementById(id);
  const num = v => Number(v || 0).toLocaleString('pt-BR');
  const pct = v => (Math.round((v || 0) * 1000) / 10).toLocaleString('pt-BR') + '%';
  const avisar = (texto, tipo) => { if (window.PontoCerto) window.PontoCerto.toast(texto, tipo); };

  async function api(caminho, corpo) {
    const r = await fetch(caminho, corpo === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo)
    });
    if (r.status === 401) { location.assign('/login'); throw Error('Sessão encerrada.'); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      const det = d.erro || d.detail;
      throw Error(typeof det === 'string' ? det : 'Não deu certo. Tente de novo.');
    }
    return d;
  }

  function el(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined && texto !== null) e.textContent = texto;
    return e;
  }

  function hojeISO(deslocamento) {
    const d = new Date();
    d.setDate(d.getDate() - (deslocamento || 0));
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-');
  }
  const dataBR = iso => iso.split('-').reverse().slice(0, 2).join('/');

  /** Lista de barras: [{rotulo, valor, detalhe, largura 0..1}] */
  function barras(host, itens, vazio, classe) {
    host.replaceChildren();
    if (!itens.length) { host.append(el('p', 'texto-apoio', vazio)); return; }
    const ul = el('ul', 'barras' + (classe ? ' ' + classe : ''));
    for (const it of itens) {
      const li = el('li');
      const topo = el('div', 'barras-topo');
      topo.append(el('span', 'barras-rotulo', it.rotulo));
      const valor = el('span', 'barras-valor', it.valor);
      if (it.detalhe) valor.append(' ', el('small', null, it.detalhe));
      topo.append(valor);
      const trilho = el('span', 'progresso');
      const i = el('i'); i.style.width = (Math.max(0, Math.min(1, it.largura)) * 100).toFixed(1) + '%';
      trilho.append(i);
      li.append(topo, trilho);
      ul.append(li);
    }
    host.append(ul);
  }

  /* --- Perfil no menu ---------------------------------------------------- */

  let perfil = null;

  function iniciais(p) {
    const base = (p && (p.nome || p.email)) || '';
    const partes = base.split('@')[0].split(/[\s._-]+/).filter(Boolean);
    return ((partes[0] || '?')[0] + (partes.length > 1 ? partes[partes.length - 1][0] : '')).toUpperCase();
  }

  function pintarAvatar(alvo, p, avatar) {
    const foto = avatar === undefined ? p && p.avatar : avatar;
    alvo.textContent = foto ? '' : iniciais(p);
    alvo.style.backgroundImage = foto ? 'url("' + foto + '")' : '';
    alvo.classList.toggle('com-foto', !!foto);
  }

  function pintarPerfil() {
    if (!perfil) return;
    document.querySelectorAll('[data-avatar]').forEach(a => {
      if (a.id !== 'perfil-avatar') pintarAvatar(a, perfil);
    });
    document.querySelectorAll('[data-perfil-nome]').forEach(n => { n.textContent = perfil.nome || 'Seu perfil'; });
    document.querySelectorAll('[data-perfil-email]').forEach(n => { n.textContent = perfil.email; });
    // Análise da equipe: só para administradores.
    const abaAnalise = $('aba-btn-analise');
    if (abaAnalise) abaAnalise.hidden = !perfil.admin;
  }

  const perfilPronto = api('/api/perfil').then(p => { perfil = p; pintarPerfil(); return p; }).catch(() => null);

  /* --- Início ------------------------------------------------------------- */

  function saudacao() {
    const h = new Date().getHours();
    return h < 12 ? 'Bom dia' : h < 18 ? 'Boa tarde' : 'Boa noite';
  }

  async function inicio() {
    $('inicio-data').textContent = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' });
    perfilPronto.then(p => {
      const nome = p && p.nome ? p.nome.split(' ')[0] : '';
      $('inicio-saudacao').textContent = saudacao() + (nome ? ', ' + nome : '');
    });
    let d;
    try { d = await api('/api/inicio'); } catch (e) { avisar(e.message, 'erro'); return; }
    const h = d.hoje;
    $('inicio-total').textContent = num(h.total);
    $('inicio-aprovadas').textContent = num(h.aprovadas);
    $('inicio-defeitos-n').textContent = num(h.defeitos);
    $('inicio-taxa').textContent = h.total ? pct(h.taxa_defeito) : '';
    $('inicio-pendentes').textContent = num(h.pendentes);
    $('inicio-pendentes-card').classList.toggle('alerta', h.pendentes > 0);
    $('inicio-aviso-conferir').hidden = !h.pendentes;
    $('inicio-aviso-texto').textContent = h.pendentes === 1
      ? '1 peça está esperando alguém conferir.' : num(h.pendentes) + ' peças estão esperando alguém conferir.';

    const tipos = $('inicio-defeitos');
    if (!h.total) {
      tipos.replaceChildren(el('p', 'texto-apoio', 'Nenhuma peça inspecionada hoje ainda.'));
    } else {
      const maior = h.defeitos_por_tipo.length ? h.defeitos_por_tipo[0].quantidade : 1;
      barras(tipos, h.defeitos_por_tipo.map(t => ({
        rotulo: t.nome, valor: num(t.quantidade), largura: t.quantidade / maior
      })), 'Nenhum defeito hoje.', 'barras-defeito');
    }

    const lotes = $('inicio-lotes');
    lotes.replaceChildren();
    if (d.erro_lotes) { lotes.append(el('p', 'texto-apoio', d.erro_lotes)); return; }
    if (!d.lotes.length) {
      const p = el('p', 'texto-apoio', 'Nenhum lote em aberto. ');
      const a = el('a', null, 'Criar lote'); a.href = '/#lotes';
      p.append(a); lotes.append(p); return;
    }
    const ativo = d.lote_ativo && d.lote_ativo.id;
    const ul = el('ul', 'inicio-lotes');
    for (const l of d.lotes) {
      const li = el('li');
      const a = el('a'); a.href = '/#lotes';
      const topo = el('span', 'barras-topo');
      const nome = el('span', 'barras-rotulo');
      nome.append(el('strong', null, l.codigo), el('small', null, l.cliente));
      topo.append(nome, el('span', 'barras-valor', num(l.inspecionadas) + ' de ' + num(l.quantidade)));
      const trilho = el('span', 'progresso');
      const i = el('i'); i.style.width = (l.quantidade ? Math.min(1, l.inspecionadas / l.quantidade) * 100 : 0).toFixed(1) + '%';
      trilho.append(i);
      const rodape = el('span', 'inicio-lote-rodape',
        l.inspecionadas ? num(l.reprovadas) + ' com defeito (' + pct(l.taxa_defeito) + ')' : 'Nenhuma peça ainda');
      if (l.id === ativo) rodape.append(' · ', el('span', 'estado estado-ok', 'Inspecionando agora'));
      a.append(topo, trilho, rodape);
      li.append(a); ul.append(li);
    }
    lotes.append(ul);
    if (d.total_lotes > d.lotes.length) lotes.append(el('p', 'texto-apoio', 'e mais ' + (d.total_lotes - d.lotes.length) + ' lotes.'));
  }

  /* --- Relatórios --------------------------------------------------------- */

  function marcarPeriodo(dias) {
    document.querySelectorAll('[data-periodo]').forEach(b => {
      b.setAttribute('aria-pressed', String(String(dias) === b.dataset.periodo));
    });
  }

  async function relatorios() {
    const de = $('relatorio-de'), ate = $('relatorio-ate');
    if (!ate.value) ate.value = hojeISO(0);
    if (!de.value) de.value = ate.value;
    const qs = '?de=' + encodeURIComponent(de.value) + '&ate=' + encodeURIComponent(ate.value);
    $('relatorio-pdf').href = '/api/relatorios/pdf' + qs;
    let r;
    try { r = await api('/api/relatorios/resumo' + qs); } catch (e) { avisar(e.message, 'erro'); return; }
    $('rel-escopo').hidden = r.escopo !== 'equipe';
    $('rel-total').textContent = num(r.total);
    $('rel-aprovadas').textContent = num(r.aprovadas);
    $('rel-defeitos').textContent = num(r.defeitos);
    $('rel-taxa').textContent = r.total ? pct(r.taxa_defeito) : '';
    $('rel-conferidas').textContent = num(r.conferidas);
    $('rel-corrigidas').textContent = r.corrigidas ? num(r.corrigidas) + (r.corrigidas === 1 ? ' corrigida' : ' corrigidas') : '';

    barras($('rel-tipos'), r.defeitos_por_tipo.map(t => ({
      rotulo: t.nome, valor: num(t.quantidade), detalhe: pct(t.parcela), largura: t.parcela
    })), r.total ? 'Nenhum defeito no período.' : 'Nenhuma peça inspecionada no período.', 'barras-defeito');

    barras($('rel-lotes'), r.por_lote.map(l => ({
      rotulo: l.codigo || 'Sem lote', valor: num(l.inspecionadas),
      detalhe: num(l.defeitos) + ' com defeito (' + pct(l.taxa_defeito) + ')',
      largura: l.inspecionadas ? l.defeitos / l.inspecionadas : 0
    })), 'Nenhuma peça no período.', 'barras-defeito');

    const varios = r.por_dia.length > 1;
    $('rel-dias-bloco').hidden = !varios;
    if (varios) {
      const maior = Math.max(...r.por_dia.map(x => x.total));
      barras($('rel-dias'), r.por_dia.map(x => ({
        rotulo: dataBR(x.data), valor: num(x.total), detalhe: num(x.defeitos) + ' com defeito', largura: x.total / maior
      })), '');
    }
  }

  document.querySelectorAll('[data-periodo]').forEach(b => b.addEventListener('click', () => {
    const dias = Number(b.dataset.periodo);
    $('relatorio-ate').value = hojeISO(0);
    $('relatorio-de').value = hojeISO(dias);
    marcarPeriodo(dias);
    relatorios();
  }));
  ['relatorio-de', 'relatorio-ate'].forEach(id => $(id) && $(id).addEventListener('change', () => {
    marcarPeriodo(null);
    relatorios();
  }));

  /* --- Perfil ------------------------------------------------------------- */

  let fotoNova; // undefined: sem mudança; null: remover; string: foto nova

  async function telaPerfil() {
    const p = await perfilPronto.then(x => x || api('/api/perfil'));
    perfil = p;
    fotoNova = undefined;
    $('perfil-nome').value = p.nome || '';
    $('perfil-email').value = p.email;
    pintarAvatar($('perfil-avatar'), p);
    $('perfil-remover-foto').hidden = !p.avatar;
    mostrarSenha(false);
  }

  async function carregarAtividade() {
    let d;
    try { d = await api('/api/perfil/atividade'); } catch { return; }
    $('ativ-hoje').textContent = num(d.hoje);
    $('ativ-semana').textContent = num(d.semana);
    $('ativ-corrigidas').textContent = num(d.corrigidas);
    const lista = $('ativ-ultimas');
    lista.replaceChildren();
    $('ativ-vazio').hidden = d.total > 0;
    $('ativ-titulo').hidden = !d.total;
    lista.hidden = !d.total;
    for (const x of d.ultimas) {
      const li = el('li');
      if (x.imagem) {
        const img = el('img'); img.src = x.imagem; img.alt = ''; img.loading = 'lazy'; li.append(img);
      } else li.append(el('span', 'ativ-sem-foto'));
      const txt = el('span');
      const quando = new Date(x.quando * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
      txt.append(el('strong', null, x.nome),
        el('small', null, (x.corrigida ? 'Corrigida' : 'Confirmada') + ' · ' + quando + (x.lote ? ' · ' + x.lote : '')));
      li.append(txt);
      lista.append(li);
    }
  }

  /** Recorta o centro da foto em quadrado de 160 px: fica leve para guardar na conta. */
  function reduzirFoto(arquivo) {
    return new Promise((ok, falha) => {
      const url = URL.createObjectURL(arquivo);
      const img = new Image();
      img.onload = () => {
        const lado = Math.min(img.naturalWidth, img.naturalHeight);
        const tela = document.createElement('canvas');
        tela.width = tela.height = 160;
        tela.getContext('2d').drawImage(img, (img.naturalWidth - lado) / 2, (img.naturalHeight - lado) / 2, lado, lado, 0, 0, 160, 160);
        URL.revokeObjectURL(url);
        ok(tela.toDataURL('image/jpeg', 0.85));
      };
      img.onerror = () => { URL.revokeObjectURL(url); falha(Error('Não consegui abrir essa foto.')); };
      img.src = url;
    });
  }

  $('perfil-arquivo').addEventListener('change', async e => {
    const arquivo = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!arquivo) return;
    try {
      fotoNova = await reduzirFoto(arquivo);
      pintarAvatar($('perfil-avatar'), perfil, fotoNova);
      $('perfil-remover-foto').hidden = false;
      avisar('Foto escolhida. Toque em Salvar para guardar.', 'info');
    } catch (err) { avisar(err.message, 'erro'); }
  });

  $('perfil-remover-foto').addEventListener('click', () => {
    fotoNova = null;
    pintarAvatar($('perfil-avatar'), { ...perfil, nome: $('perfil-nome').value }, null);
    $('perfil-remover-foto').hidden = true;
  });

  $('perfil-nome').addEventListener('input', () => {
    if (!(fotoNova || (fotoNova === undefined && perfil && perfil.avatar))) {
      pintarAvatar($('perfil-avatar'), { ...perfil, nome: $('perfil-nome').value }, null);
    }
  });

  $('form-perfil').addEventListener('submit', async e => {
    e.preventDefault();
    const botao = e.target.querySelector('[type=submit]');
    botao.disabled = true;
    try {
      perfil = await api('/api/perfil', {
        nome: $('perfil-nome').value,
        avatar: fotoNova === undefined ? (perfil.avatar || null) : fotoNova
      });
      fotoNova = undefined;
      pintarPerfil();
      avisar('Perfil salvo.', 'ok');
    } catch (err) { avisar(err.message, 'erro'); } finally { botao.disabled = false; }
  });

  function mostrarSenha(abrir) {
    $('form-senha').hidden = !abrir;
    $('btn-abrir-senha').hidden = abrir;
    $('btn-abrir-senha').setAttribute('aria-expanded', String(abrir));
    if (abrir) $('senha-atual').focus();
    else { $('form-senha').reset(); $('senha-erro').textContent = ''; }
  }
  $('btn-abrir-senha').addEventListener('click', () => mostrarSenha(true));
  $('btn-cancelar-senha').addEventListener('click', () => mostrarSenha(false));

  $('form-senha').addEventListener('submit', async e => {
    e.preventDefault();
    const erro = $('senha-erro');
    erro.textContent = '';
    if (!$('senha-atual').value || !$('senha-nova').value) { erro.textContent = 'Preencha a senha atual e a nova.'; return; }
    if ($('senha-nova').value !== $('senha-nova2').value) { erro.textContent = 'As senhas novas não conferem.'; return; }
    const botao = e.target.querySelector('[type=submit]');
    botao.disabled = true;
    try {
      await api('/api/perfil/senha', { atual: $('senha-atual').value, nova: $('senha-nova').value });
      mostrarSenha(false);
      avisar('Senha trocada. Nos outros aparelhos, entre de novo com a senha nova.', 'ok');
    } catch (err) { erro.textContent = err.message; } finally { botao.disabled = false; }
  });

  /* --- Ligação com app.js -------------------------------------------------- */

  function mostrarAba(nome) {
    if (nome === 'analise' && !(perfil && perfil.admin)) nome = 'dados';
    document.querySelectorAll('.abas-perfil [data-aba]').forEach(b => {
      const ativa = b.dataset.aba === nome;
      b.classList.toggle('ativo', ativa);
      b.setAttribute('aria-selected', String(ativa));
    });
    $('aba-dados').hidden = nome !== 'dados';
    $('aba-ajustes').hidden = nome !== 'ajustes';
    $('aba-analise').hidden = nome !== 'analise';
    if (nome === 'ajustes') {
      if (window.PontoCerto && window.PontoCerto.carregarAjustes) window.PontoCerto.carregarAjustes();
      if (window.listarContas) window.listarContas();
      if (window.Equipe) window.Equipe.maquinas();
    }
    if (nome === 'analise' && window.Equipe) window.Equipe.analise();
  }
  document.querySelectorAll('.abas-perfil [data-aba]').forEach(b => b.addEventListener('click', () => mostrarAba(b.dataset.aba)));

  function abrirPerfil() {
    const estado = window.PontoCerto && window.PontoCerto.estado;
    const aba = (estado && estado.abaPerfil) || 'dados';
    if (estado) estado.abaPerfil = null;
    if (location.hash === '#ajustes') history.replaceState(null, '', '#perfil');
    // A aba da análise depende de saber se a pessoa é administradora.
    if (aba === 'analise') perfilPronto.then(() => mostrarAba(aba)); else mostrarAba(aba);
    telaPerfil();
    carregarAtividade();
  }

  window.Paineis = { inicio, relatorios, perfil: abrirPerfil };

  // app.js pode ter aberto a página antes deste arquivo carregar.
  const aberta = document.querySelector('.pagina.ativa');
  const nome = aberta && aberta.id.replace('pagina-', '');
  if (nome && window.Paineis[nome]) window.Paineis[nome]();
})();
