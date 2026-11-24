'use strict';
// Só para administradores: máquinas (Perfil › Ajustes) e Análise da equipe (Perfil › Análise).
// paineis.js chama window.Equipe.maquinas() e window.Equipe.analise() ao abrir cada aba.
(function () {
  const $ = id => document.getElementById(id);
  const num = v => Number(v || 0).toLocaleString('pt-BR');
  const dec = v => Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const pct = v => (Math.round((v || 0) * 1000) / 10).toLocaleString('pt-BR') + '%';
  const avisar = (texto, tipo) => { if (window.PontoCerto) window.PontoCerto.toast(texto, tipo); };
  const NS = 'http://www.w3.org/2000/svg';

  async function api(caminho, metodo, corpo) {
    const op = { method: metodo || 'GET' };
    if (corpo !== undefined) { op.headers = { 'Content-Type': 'application/json' }; op.body = JSON.stringify(corpo); }
    const r = await fetch(caminho, op);
    if (r.status === 401) { location.assign('/login'); throw Error('Sessão encerrada.'); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(d.erro || (typeof d.detail === 'string' ? d.detail : 'Não deu certo. Tente de novo.'));
    return d;
  }

  function el(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined && texto !== null) e.textContent = texto;
    return e;
  }

  function svg(tag, attrs) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  function iso(d) {
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-');
  }
  function diasAtras(n) { const d = new Date(); d.setDate(d.getDate() - n); return iso(d); }
  const dataCurta = s => s.split('-').reverse().slice(0, 2).join('/');
  const diaSemana = s => new Date(s + 'T12:00').toLocaleDateString('pt-BR', { weekday: 'short' }).replace('.', '');

  function iniciais(nome) {
    const p = String(nome || '?').split(/[\s@._-]+/).filter(Boolean);
    return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase();
  }
  function avatar(pessoa, classe) {
    const a = el('span', 'avatar' + (classe ? ' ' + classe : ''));
    a.setAttribute('aria-hidden', 'true');
    if (pessoa.avatar) { a.style.backgroundImage = 'url("' + pessoa.avatar + '")'; a.classList.add('com-foto'); }
    else a.textContent = pessoa.email ? iniciais(pessoa.nome) : '—';
    return a;
  }

  function quando(ts) {
    const d = new Date(ts * 1000), hoje = new Date();
    const mesmoDia = d.toDateString() === hoje.toDateString();
    const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    return mesmoDia ? 'hoje, ' + hora : d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ', ' + hora;
  }

  /* ======================================================================
   * MÁQUINAS (Ajustes)
   * ==================================================================== */

  const ICONE_MAQ = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 19.5h16"/><path d="M6 19.5V9.5a2 2 0 0 1 2-2h9.5a2 2 0 0 1 2 2v3H13"/><path d="M13 12.5v4"/><path d="M11.5 16.5h3"/><path d="M9 7.5V4.5h5"/></svg>';
  let editando = null; // id da máquina no formulário (null = nova)
  let listaMaq = [];

  async function maquinas() {
    const bloco = $('bloco-maquinas');
    if (!bloco) return;
    let d;
    try { d = await api('/api/maquinas'); } catch (e) { return; }
    bloco.hidden = !d.admin;
    if (!d.admin) return;
    listaMaq = d.maquinas || [];
    $('tipos-maquina').replaceChildren(...(d.tipos || []).map(t => { const o = el('option'); o.value = t; return o; }));
    pintarMaquinas();
  }

  function pintarMaquinas() {
    const ul = $('lista-maquinas');
    ul.replaceChildren();
    if (!listaMaq.length) {
      const li = el('li', 'maquinas-vazio');
      li.append(el('strong', null, 'Nenhuma máquina cadastrada'),
        el('span', null, 'Cadastre as máquinas da produção para acompanhar o ritmo e os defeitos de cada uma.'));
      ul.append(li);
      return;
    }
    for (const m of listaMaq) {
      const li = el('li', 'maquina-item');
      const ic = el('span', 'maquina-icone'); ic.innerHTML = ICONE_MAQ;
      const txt = el('span', 'maquina-texto');
      txt.append(el('strong', null, m.nome));
      const detalhe = [m.tipo, m.setor].filter(Boolean).join(' · ');
      if (detalhe) txt.append(el('small', null, detalhe));
      const acoes = el('span', 'linha-botoes');
      const editar = el('button', 'btn btn-quieto', 'Editar'); editar.type = 'button';
      editar.addEventListener('click', () => abrirForm(m));
      const remover = el('button', 'btn btn-quieto', 'Remover'); remover.type = 'button';
      remover.addEventListener('click', () => confirmarRemocao(li, m));
      acoes.append(editar, remover);
      li.append(ic, txt, acoes);
      ul.append(li);
    }
  }

  function confirmarRemocao(li, m) {
    const caixa = el('div', 'maquina-confirmar');
    caixa.append(el('span', null, 'Remover ' + m.nome + '? As peças já feitas nela continuam com o nome.'));
    const sim = el('button', 'btn btn-perigo btn-pequeno', 'Remover'); sim.type = 'button';
    const nao = el('button', 'btn btn-quieto', 'Cancelar'); nao.type = 'button';
    sim.addEventListener('click', async () => {
      sim.disabled = true;
      try { await api('/api/maquinas/' + encodeURIComponent(m.id), 'DELETE'); avisar(m.nome + ' removida.', 'ok'); maquinas(); }
      catch (e) { avisar(e.message, 'erro'); sim.disabled = false; }
    });
    nao.addEventListener('click', pintarMaquinas);
    const botoes = el('span', 'linha-botoes'); botoes.append(sim, nao);
    caixa.append(botoes);
    li.replaceChildren(caixa);
    nao.focus();
  }

  function abrirForm(m) {
    editando = m ? m.id : null;
    const form = $('form-maquina');
    form.hidden = false;
    $('btn-nova-maquina').hidden = true;
    $('maquina-nome').value = m ? m.nome : '';
    $('maquina-tipo').value = m ? (m.tipo || '') : '';
    $('maquina-setor').value = m ? (m.setor || '') : '';
    $('maquina-erro').textContent = '';
    form.querySelector('[type=submit]').textContent = m ? 'Salvar alterações' : 'Adicionar';
    $('maquina-nome').focus();
  }
  function fecharForm() {
    $('form-maquina').hidden = true;
    $('btn-nova-maquina').hidden = false;
    editando = null;
  }

  if ($('form-maquina')) {
    $('btn-nova-maquina').addEventListener('click', () => abrirForm(null));
    $('maquina-cancelar').addEventListener('click', fecharForm);
    $('form-maquina').addEventListener('submit', async e => {
      e.preventDefault();
      const corpo = { nome: $('maquina-nome').value, tipo: $('maquina-tipo').value, setor: $('maquina-setor').value };
      if (!corpo.nome.trim()) { $('maquina-erro').textContent = 'Dê um nome para a máquina.'; return; }
      const botao = e.target.querySelector('[type=submit]');
      botao.disabled = true;
      try {
        if (editando) await api('/api/maquinas/' + encodeURIComponent(editando), 'PUT', corpo);
        else await api('/api/maquinas', 'POST', corpo);
        avisar(editando ? 'Máquina atualizada.' : 'Máquina adicionada.', 'ok');
        fecharForm();
        maquinas();
      } catch (err) { $('maquina-erro').textContent = err.message; }
      finally { botao.disabled = false; }
    });
  }

  /* ======================================================================
   * ANÁLISE DA EQUIPE
   * ==================================================================== */

  const filtro = { usuario: '', maquina: '' };
  let seletorUsuario = null, seletorMaquina = null, ultimo = null;

  function prepararFiltros() {
    if (seletorUsuario || !window.Seletor) return;
    const ICONE_PESSOA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="8" r="4"/><path d="M4 20.5c.8-4 4-6 8-6s7.2 2 8 6"/></svg>';
    seletorUsuario = window.Seletor($('filtro-usuario'), {
      rotulo: 'Pessoa', icone: ICONE_PESSOA, compacto: true,
      vazio: { titulo: 'Toda a equipe' },
      aoEscolher: v => { filtro.usuario = v; return carregar(); }
    });
    seletorMaquina = window.Seletor($('filtro-maquina'), {
      rotulo: 'Máquina', icone: ICONE_MAQ, compacto: true,
      vazio: { titulo: 'Todas as máquinas' },
      aoEscolher: v => { filtro.maquina = v; return carregar(); }
    });
    if (!$('analise-ate').value) $('analise-ate').value = diasAtras(0);
    if (!$('analise-de').value) $('analise-de').value = diasAtras(6);
  }

  function consulta() {
    const qs = new URLSearchParams({ de: $('analise-de').value, ate: $('analise-ate').value });
    if (filtro.usuario) qs.set('usuario', filtro.usuario);
    if (filtro.maquina) qs.set('maquina', filtro.maquina);
    return '?' + qs.toString();
  }

  async function carregar() {
    const qs = consulta();
    $('analise-pdf').href = '/api/analise/pdf' + qs;
    $('aba-analise').classList.add('carregando');
    let r;
    try { r = await api('/api/analise' + qs); }
    catch (e) { avisar(e.message, 'erro'); return; }
    finally { $('aba-analise').classList.remove('carregando'); }
    ultimo = r;
    pintar(r);
  }

  function pintar(r) {
    seletorUsuario.opcoes(r.opcoes.usuarios.map(u => ({ valor: u.chave, titulo: u.nome, sub: u.email && u.email !== u.nome ? u.email : null })));
    seletorUsuario.valor(filtro.usuario);
    seletorMaquina.opcoes(r.opcoes.maquinas.map(m => ({ valor: m.chave, titulo: m.nome, sub: m.tipo })));
    seletorMaquina.valor(filtro.maquina);

    const t = r.totais;
    $('an-total').textContent = num(t.inspecionadas);
    $('an-ritmo').textContent = t.pecas_por_hora == null ? '—' : dec(t.pecas_por_hora);
    $('an-taxa').textContent = t.inspecionadas ? pct(t.taxa_defeito) : '—';
    $('an-defeitos').textContent = t.inspecionadas ? num(t.defeitos) + (t.defeitos === 1 ? ' peça' : ' peças') : '';
    $('an-acerto').textContent = t.acerto_ia == null ? '—' : pct(t.acerto_ia);
    $('an-conferidas').textContent = t.conferidas ? 'em ' + num(t.conferidas) : '';

    pintarFoco(r);
    graficoDias($('an-dias'), r.por_dia);
    $('an-melhor-dia').textContent = r.melhor_dia
      ? 'Dia mais produtivo: ' + diaSemana(r.melhor_dia.data) + ', ' + dataCurta(r.melhor_dia.data) + ', com ' + num(r.melhor_dia.total) + ' peças.'
      : '';
    tabelaEquipe($('an-equipe'), r.por_usuario);
    tabelaMaquinas($('an-maquinas'), r.por_maquina);
    graficoHoras($('an-horas'), r.por_hora);
    barrasTipos($('an-tipos'), r.defeitos_por_tipo, t.inspecionadas);
  }

  /* --- Ficha da pessoa escolhida no filtro ------------------------------- */

  function pintarFoco(r) {
    const caixa = $('analise-foco');
    const u = filtro.usuario && r.por_usuario.find(x => x.chave === filtro.usuario);
    caixa.hidden = !filtro.usuario;
    caixa.replaceChildren();
    if (!filtro.usuario) return;
    const opcao = r.opcoes.usuarios.find(x => x.chave === filtro.usuario) || { nome: filtro.usuario };
    const topo = el('div', 'foco-topo');
    topo.append(avatar(u || opcao, 'avatar-grande'));
    const nome = el('div');
    nome.append(el('h2', null, opcao.nome));
    if (opcao.email) nome.append(el('p', 'texto-apoio', opcao.email));
    topo.append(nome);
    const limpar = el('button', 'btn btn-quieto foco-limpar', 'Ver toda a equipe'); limpar.type = 'button';
    limpar.addEventListener('click', () => { filtro.usuario = ''; carregar(); });
    topo.append(limpar);
    caixa.append(topo);
    if (!u) { caixa.append(el('p', 'texto-apoio', 'Nenhuma peça desta pessoa no período.')); return; }
    const fatos = [
      ['Horário típico', u.horario ? u.horario.inicio + ' às ' + u.horario.fim : '—'],
      ['Média por dia trabalhado', dec(u.media_por_dia) + ' peças'],
      ['Tempo entre peças', u.intervalo_medio_s == null ? '—' : tempo(u.intervalo_medio_s)],
      ['Máquina mais usada', u.maquina_principal || 'Nenhuma'],
      ['Defeito mais comum', u.defeito_principal ? u.defeito_principal.nome + ' (' + num(u.defeito_principal.quantidade) + ')' : 'Nenhum'],
      ['Conferências feitas', num(u.conferencias_feitas) + (u.corrigidas ? ' · ' + num(u.corrigidas) + ' corrigiu a IA' : '')],
      ['Horas trabalhadas', dec(u.horas_ativas) + ' h em ' + num(u.dias_ativos) + (u.dias_ativos === 1 ? ' dia' : ' dias')],
      ['Aguardando conferência', num(u.pendentes)]
    ];
    const dl = el('dl', 'foco-fatos');
    for (const [k, v] of fatos) { const d = el('div'); d.append(el('dt', null, k), el('dd', null, v)); dl.append(d); }
    caixa.append(dl);
  }

  function tempo(s) {
    if (s < 60) return Math.round(s) + ' s';
    const m = Math.floor(s / 60), r = Math.round(s % 60);
    return m + ' min' + (r ? ' ' + r + ' s' : '');
  }

  /* --- Tabelas ----------------------------------------------------------- */

  function celula(tr, texto, classe, rotulo) {
    const td = el('td', classe, texto);
    if (rotulo) td.dataset.rotulo = rotulo;
    tr.append(td);
    return td;
  }

  function cabecalho(tabela, colunas) {
    const thead = el('thead'), tr = el('tr');
    colunas.forEach(([t, c]) => { const th = el('th', c, t); th.scope = 'col'; tr.append(th); });
    thead.append(tr); tabela.append(thead);
  }

  function taxa(td, v, total) {
    td.textContent = '';
    if (!total) { td.textContent = '—'; return; }
    const alta = v >= 0.1;
    const s = el('span', 'taxa' + (alta ? ' taxa-alta' : ''), pct(v));
    td.append(s);
  }

  function tabelaEquipe(host, linhas) {
    host.replaceChildren();
    if (!linhas.length) { host.append(el('p', 'texto-apoio vazio-tabela', 'Nenhuma peça no período.')); return; }
    const maior = Math.max(...linhas.map(u => u.inspecionadas), 1);
    const tabela = el('table', 'tabela tabela-fichas tabela-analise');
    cabecalho(tabela, [['Pessoa'], ['Peças', 'num'], ['Ritmo', 'num'], ['Com defeito', 'num'], ['Dias', 'num'], ['Acerto da IA', 'num'], ['Última peça']]);
    const tbody = el('tbody');
    for (const u of linhas) {
      const tr = el('tr', 'linha-filtro' + (filtro.usuario === u.chave ? ' selecionada' : ''));
      tr.tabIndex = 0;
      tr.setAttribute('aria-label', 'Ver só ' + u.nome);
      const pessoa = el('td', 'larga');
      const caixa = el('span', 'pessoa');
      const txt = el('span', 'pessoa-texto');
      txt.append(el('strong', null, u.nome), el('small', null, u.maquina_principal ? 'Mais na ' + u.maquina_principal : (u.email || '')));
      caixa.append(avatar(u), txt);
      pessoa.append(caixa);
      tr.append(pessoa);
      const pecas = celula(tr, '', 'num', 'Peças');
      const barra = el('span', 'mini-barra'); const i = el('i'); i.style.width = (u.inspecionadas / maior * 100).toFixed(1) + '%'; barra.append(i);
      pecas.append(el('span', null, num(u.inspecionadas)), barra);
      celula(tr, u.pecas_por_hora == null ? '—' : dec(u.pecas_por_hora) + '/h', 'num', 'Ritmo');
      taxa(celula(tr, '', 'num', 'Com defeito'), u.taxa_defeito, u.inspecionadas);
      celula(tr, num(u.dias_ativos), 'num', 'Dias');
      celula(tr, u.acerto_ia == null ? '—' : pct(u.acerto_ia), 'num', 'Acerto da IA');
      celula(tr, quando(u.ultima), null, 'Última peça');
      const escolher = () => { filtro.usuario = filtro.usuario === u.chave ? '' : u.chave; carregar(); $('aba-analise').scrollIntoView({ behavior: 'smooth', block: 'start' }); };
      tr.addEventListener('click', escolher);
      tr.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); escolher(); } });
      tbody.append(tr);
    }
    tabela.append(tbody);
    const rolagem = el('div', 'tabela-rolagem'); rolagem.append(tabela);
    host.append(rolagem);
  }

  function tabelaMaquinas(host, linhas) {
    host.replaceChildren();
    if (!linhas.length) { host.append(el('p', 'texto-apoio vazio-tabela', 'Nenhuma peça no período.')); return; }
    const tabela = el('table', 'tabela tabela-fichas tabela-analise');
    cabecalho(tabela, [['Máquina'], ['Peças', 'num'], ['Ritmo', 'num'], ['Com defeito', 'num'], ['Pessoas', 'num']]);
    const tbody = el('tbody');
    for (const m of linhas) {
      const tr = el('tr', 'linha-filtro' + (filtro.maquina === m.chave ? ' selecionada' : ''));
      tr.tabIndex = 0;
      const td = el('td', 'larga');
      const caixa = el('span', 'pessoa');
      const ic = el('span', 'maquina-icone' + (m.id ? '' : ' maquina-icone-vazia')); ic.innerHTML = ICONE_MAQ;
      const txt = el('span', 'pessoa-texto');
      txt.append(el('strong', null, m.nome));
      if (m.defeito_principal) txt.append(el('small', null, 'Mais comum: ' + m.defeito_principal.nome));
      else if (m.operador_principal) txt.append(el('small', null, 'Mais com ' + m.operador_principal));
      caixa.append(ic, txt); td.append(caixa); tr.append(td);
      celula(tr, num(m.inspecionadas), 'num', 'Peças');
      celula(tr, m.pecas_por_hora == null ? '—' : dec(m.pecas_por_hora) + '/h', 'num', 'Ritmo');
      taxa(celula(tr, '', 'num', 'Com defeito'), m.taxa_defeito, m.inspecionadas);
      celula(tr, num(m.operadores), 'num', 'Pessoas');
      const escolher = () => { filtro.maquina = filtro.maquina === m.chave ? '' : m.chave; carregar(); };
      tr.addEventListener('click', escolher);
      tr.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); escolher(); } });
      tbody.append(tr);
    }
    tabela.append(tbody);
    const rolagem = el('div', 'tabela-rolagem'); rolagem.append(tabela);
    host.append(rolagem);
  }

  function barrasTipos(host, tipos, total) {
    host.replaceChildren();
    if (!tipos.length) { host.append(el('p', 'texto-apoio', total ? 'Nenhum defeito no período.' : 'Nenhuma peça no período.')); return; }
    const ul = el('ul', 'barras barras-defeito');
    for (const d of tipos) {
      const li = el('li');
      const topo = el('div', 'barras-topo');
      topo.append(el('span', 'barras-rotulo', d.nome));
      const v = el('span', 'barras-valor', num(d.quantidade)); v.append(' ', el('small', null, pct(d.parcela)));
      topo.append(v);
      const tr = el('span', 'progresso'); const i = el('i'); i.style.width = (d.parcela * 100).toFixed(1) + '%'; tr.append(i);
      li.append(topo, tr); ul.append(li);
    }
    host.append(ul);
  }

  /* --- Gráficos (SVG feito à mão: barras finas, grade discreta, dica ao passar) ---- */

  let dica = null;
  function mostrarDica(alvo, linhas) {
    if (!dica) { dica = el('div', 'grafico-dica'); dica.setAttribute('role', 'tooltip'); document.body.append(dica); }
    dica.replaceChildren(...linhas.map((t, i) => el(i ? 'span' : 'strong', null, t)));
    dica.hidden = false;
    const r = alvo.getBoundingClientRect(), d = dica.getBoundingClientRect();
    const x = Math.min(window.innerWidth - d.width - 8, Math.max(8, r.left + r.width / 2 - d.width / 2));
    const y = r.top - d.height - 10 < 8 ? r.bottom + 10 : r.top - d.height - 10;
    dica.style.left = x + window.scrollX + 'px';
    dica.style.top = y + window.scrollY + 'px';
  }
  function esconderDica() { if (dica) dica.hidden = true; }
  window.addEventListener('scroll', esconderDica, { passive: true });

  function escala(maximo) {
    // Passo "redondo" para 3 ou 4 linhas de grade.
    const bruto = Math.max(1, maximo) / 3;
    const mag = Math.pow(10, Math.floor(Math.log10(bruto)));
    const passo = [1, 2, 2.5, 5, 10].map(m => m * mag).find(p => p >= bruto) || bruto;
    const topo = Math.max(passo, Math.ceil(maximo / passo) * passo);
    const marcas = [];
    for (let v = 0; v <= topo + 1e-9; v += passo) marcas.push(Math.round(v * 100) / 100);
    return { topo, marcas };
  }

  /** Barras verticais. series: [{chave, classe}] empilhadas de baixo para cima. */
  function barras(host, itens, op) {
    host.replaceChildren();
    const largura = Math.max(280, host.clientWidth || 600), altura = op.altura || 220;
    const m = { e: 34, d: 4, t: 10, b: 26 };
    const w = largura - m.e - m.d, h = altura - m.t - m.b;
    const total = it => op.series.reduce((s, x) => s + (it[x.chave] || 0), 0);
    const { topo, marcas } = escala(Math.max(0, ...itens.map(total)));
    const g = svg('svg', { viewBox: `0 0 ${largura} ${altura}`, width: largura, height: altura, role: 'img', 'aria-label': op.descricao });
    for (const v of marcas) {
      const y = m.t + h - (v / topo) * h;
      g.append(svg('line', { x1: m.e, x2: largura - m.d, y1: y, y2: y, class: v ? 'grade' : 'eixo' }));
      const t = svg('text', { x: m.e - 8, y: y + 4, class: 'rotulo-eixo', 'text-anchor': 'end' }); t.textContent = num(v); g.append(t);
    }
    const passo = w / itens.length;
    const larg = Math.max(2, Math.min(28, passo * 0.62));
    const cadaRotulo = Math.max(1, Math.ceil(itens.length / Math.floor(w / 46)));
    itens.forEach((it, i) => {
      const cx = m.e + passo * i + passo / 2;
      let base = m.t + h;
      op.series.forEach((s, j) => {
        const v = it[s.chave] || 0;
        if (!v) return;
        const alt = (v / topo) * h;
        const topoSerie = op.series.slice(j + 1).every(x => !(it[x.chave] || 0));
        const y = base - alt;
        // Só o topo da pilha ganha cantos arredondados; 2px de folga entre as partes.
        const r = topoSerie ? Math.min(4, larg / 2, alt) : 0;
        const caminho = `M${cx - larg / 2},${base} V${y + r} Q${cx - larg / 2},${y} ${cx - larg / 2 + r},${y} H${cx + larg / 2 - r} Q${cx + larg / 2},${y} ${cx + larg / 2},${y + r} V${base} Z`;
        g.append(svg('path', { d: caminho, class: 'barra ' + s.classe }));
        base = y - (topoSerie ? 0 : 2);
      });
      if (i % cadaRotulo === 0) {
        const t = svg('text', { x: cx, y: altura - 8, class: 'rotulo-eixo', 'text-anchor': 'middle' }); t.textContent = op.rotulo(it); g.append(t);
      }
      const alvo = svg('rect', { x: m.e + passo * i, y: m.t, width: passo, height: h, class: 'alvo', tabindex: '0' });
      alvo.setAttribute('aria-label', op.dica(it).join('. '));
      const entrar = () => { g.querySelectorAll('.alvo.ativo').forEach(a => a.classList.remove('ativo')); alvo.classList.add('ativo'); mostrarDica(alvo, op.dica(it)); };
      const sair = () => { alvo.classList.remove('ativo'); esconderDica(); };
      alvo.addEventListener('mouseenter', entrar); alvo.addEventListener('focus', entrar);
      alvo.addEventListener('mouseleave', sair); alvo.addEventListener('blur', sair);
      g.append(alvo);
    });
    host.append(g);
  }

  function graficoDias(host, dias) {
    const itens = dias.map(d => ({ ...d, aprovadas: d.total - d.defeitos }));
    barras(host, itens, {
      series: [{ chave: 'aprovadas', classe: 'barra-aprovada' }, { chave: 'defeitos', classe: 'barra-defeito' }],
      rotulo: d => dataCurta(d.data),
      dica: d => [diaSemana(d.data) + ', ' + dataCurta(d.data), num(d.total) + ' peças', num(d.aprovadas) + ' aprovadas', num(d.defeitos) + ' com defeito' + (d.total ? ' (' + pct(d.defeitos / d.total) + ')' : '')],
      descricao: 'Peças por dia no período, aprovadas e com defeito.'
    });
  }

  function graficoHoras(host, horas) {
    const comPeca = horas.filter(x => x.total);
    if (!comPeca.length) { host.replaceChildren(el('p', 'texto-apoio', 'Nenhuma peça no período.')); return; }
    const ini = Math.max(0, Math.min(7, comPeca[0].hora - 1)), fim = Math.min(23, Math.max(18, comPeca[comPeca.length - 1].hora + 1));
    barras(host, horas.slice(ini, fim + 1), {
      altura: 200,
      series: [{ chave: 'total', classe: 'barra-marca' }],
      rotulo: x => x.hora + 'h',
      dica: x => [x.hora + 'h às ' + (x.hora + 1) + 'h', num(x.total) + ' peças', num(x.defeitos) + ' com defeito'],
      descricao: 'Peças por hora do dia.'
    });
  }

  let redesenhar = null;
  window.addEventListener('resize', () => {
    clearTimeout(redesenhar);
    redesenhar = setTimeout(() => { if (ultimo && !$('aba-analise').hidden) { graficoDias($('an-dias'), ultimo.por_dia); graficoHoras($('an-horas'), ultimo.por_hora); } }, 150);
  });

  /* --- Período ----------------------------------------------------------- */

  function marcarPeriodo(dias) {
    document.querySelectorAll('[data-analise-dias]').forEach(b => b.setAttribute('aria-pressed', String(String(dias) === b.dataset.analiseDias)));
  }
  document.querySelectorAll('[data-analise-dias]').forEach(b => b.addEventListener('click', () => {
    $('analise-ate').value = diasAtras(0);
    $('analise-de').value = diasAtras(Number(b.dataset.analiseDias));
    marcarPeriodo(b.dataset.analiseDias);
    carregar();
  }));
  ['analise-de', 'analise-ate'].forEach(id => $(id) && $(id).addEventListener('change', () => { marcarPeriodo(null); carregar(); }));

  function analise() {
    prepararFiltros();
    carregar();
  }

  window.Equipe = { maquinas, analise };

  // paineis.js pode ter aberto o Perfil antes deste arquivo carregar.
  if ($('aba-ajustes') && !$('aba-ajustes').hidden) maquinas();
  if ($('aba-analise') && !$('aba-analise').hidden) analise();
})();
