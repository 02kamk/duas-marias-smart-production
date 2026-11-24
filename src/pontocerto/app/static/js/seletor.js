'use strict';
/* Seletor: botão com ícone, rótulo e valor que abre uma lista própria.
 * Substitui o <select> nativo onde a escolha importa (lote, máquina, filtros
 * da análise): cada opção mostra título, detalhe e, quando faz sentido, uma
 * barrinha de andamento. Teclado: setas, Home/End, Enter, Esc e digitar para buscar.
 *
 *   const s = Seletor(host, { rotulo, icone, vazio: {titulo, sub}, rodape: {texto, href},
 *                             aoEscolher: valor => Promise, compacto, semResultado })
 *   s.opcoes([{ valor, titulo, sub, meta, progresso }]); s.valor('12'); s.valor()
 */
(function () {
  let contador = 0;
  const CHEVRON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="m6.5 9.5 5.5 5.5 5.5-5.5"/></svg>';
  const CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  const LUPA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true" focusable="false"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/></svg>';
  const abertos = new Set();

  function el(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto != null) e.textContent = texto;
    return e;
  }
  const semAcento = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  document.addEventListener('click', e => {
    abertos.forEach(s => { if (!s.host.contains(e.target)) s.fechar(); });
  });

  function Seletor(host, op) {
    op = op || {};
    const id = 'seletor-' + (++contador);
    let lista = [], atual = '', foco = -1, ocupado = false;

    host.classList.add('seletor');
    if (op.compacto) host.classList.add('seletor-compacto');
    host.replaceChildren();

    const gatilho = el('button', 'seletor-gatilho');
    gatilho.type = 'button';
    gatilho.setAttribute('aria-haspopup', 'listbox');
    gatilho.setAttribute('aria-expanded', 'false');
    gatilho.setAttribute('aria-controls', id + '-painel');
    const icone = el('span', 'seletor-icone');
    icone.innerHTML = op.icone || '';
    const textos = el('span', 'seletor-textos');
    const rotulo = el('span', 'seletor-rotulo', op.rotulo || '');
    const titulo = el('strong', 'seletor-valor');
    const sub = el('span', 'seletor-sub');
    textos.append(rotulo, titulo, sub);
    const seta = el('span', 'seletor-seta');
    seta.innerHTML = CHEVRON;
    if (op.icone) gatilho.append(icone);
    gatilho.append(textos, seta);

    const painel = el('div', 'seletor-painel');
    painel.id = id + '-painel';
    painel.hidden = true;
    const busca = el('label', 'seletor-busca');
    busca.innerHTML = LUPA;
    const campo = el('input');
    campo.type = 'search';
    campo.placeholder = 'Buscar';
    campo.setAttribute('aria-label', 'Buscar ' + (op.rotulo || '').toLowerCase());
    campo.autocomplete = 'off';
    busca.append(campo);
    const ul = el('ul', 'seletor-lista');
    ul.setAttribute('role', 'listbox');
    ul.id = id + '-lista';
    ul.setAttribute('aria-label', op.rotulo || 'Opções');
    const rodape = el('div', 'seletor-rodape');
    painel.append(busca, ul, rodape);
    host.append(gatilho, painel);

    function todas() {
      const vazio = op.vazio ? [{ valor: '', titulo: op.vazio.titulo, sub: op.vazio.sub, vazio: true }] : [];
      return vazio.concat(lista);
    }

    function visiveis() {
      const termo = semAcento(campo.value.trim());
      return todas().filter(o => !termo || o.vazio || semAcento(o.titulo + ' ' + (o.sub || '') + ' ' + (o.meta || '')).includes(termo));
    }

    function pintarGatilho() {
      const o = todas().find(x => String(x.valor) === String(atual));
      titulo.textContent = o ? o.titulo : (op.vazio ? op.vazio.titulo : '—');
      sub.textContent = o && !o.vazio ? (o.sub || '') : '';
      sub.hidden = !sub.textContent;
      host.classList.toggle('seletor-escolhido', !!(o && !o.vazio));
    }

    function pintarLista() {
      const itens = visiveis();
      ul.replaceChildren();
      itens.forEach((o, i) => {
        const li = el('li', 'seletor-opcao' + (o.vazio ? ' seletor-opcao-vazia' : ''));
        li.id = id + '-op-' + i;
        li.setAttribute('role', 'option');
        const marcado = String(o.valor) === String(atual);
        li.setAttribute('aria-selected', String(marcado));
        li.dataset.valor = o.valor;
        const corpo = el('span', 'seletor-opcao-corpo');
        const linha = el('span', 'seletor-opcao-linha');
        linha.append(el('span', 'seletor-opcao-titulo', o.titulo));
        if (o.meta) linha.append(el('span', 'seletor-opcao-meta', o.meta));
        corpo.append(linha);
        if (o.sub) corpo.append(el('span', 'seletor-opcao-sub', o.sub));
        if (o.progresso != null) {
          const trilho = el('span', 'seletor-trilho');
          const i2 = el('i');
          i2.style.width = (Math.max(0, Math.min(1, o.progresso)) * 100).toFixed(1) + '%';
          trilho.append(i2);
          corpo.append(trilho);
        }
        const marca = el('span', 'seletor-marca');
        marca.innerHTML = marcado ? CHECK : '';
        li.append(corpo, marca);
        li.addEventListener('mousemove', () => marcarFoco(i));
        li.addEventListener('click', () => escolher(o.valor));
        ul.append(li);
      });
      if (!lista.length && op.semOpcoes) {
        ul.append(el('li', 'seletor-aviso', op.semOpcoes));
      } else if (!itens.filter(o => !o.vazio).length && campo.value.trim()) {
        ul.append(el('li', 'seletor-aviso', 'Nada encontrado.'));
      }
      busca.hidden = todas().length < 7;
      marcarFoco(Math.max(0, itens.findIndex(o => String(o.valor) === String(atual))));
    }

    function marcarFoco(i) {
      const itens = ul.querySelectorAll('[role=option]');
      if (!itens.length) { foco = -1; gatilho.removeAttribute('aria-activedescendant'); return; }
      foco = Math.max(0, Math.min(itens.length - 1, i));
      itens.forEach((li, j) => li.classList.toggle('foco', j === foco));
      const ativo = itens[foco];
      const alvo = painel.hidden ? gatilho : (busca.hidden ? ul : campo);
      alvo.setAttribute('aria-activedescendant', ativo.id);
      if (!painel.hidden) ativo.scrollIntoView({ block: 'nearest' });
    }

    function abrir() {
      if (!painel.hidden) return;
      abertos.forEach(s => s.fechar());
      campo.value = '';
      painel.hidden = false;
      host.classList.add('aberto');
      gatilho.setAttribute('aria-expanded', 'true');
      pintarLista();
      // Perto do fim da tela o painel abre para cima.
      const r = gatilho.getBoundingClientRect();
      host.classList.toggle('para-cima', window.innerHeight - r.bottom < 320 && r.top > 320);
      (busca.hidden ? ul : campo).focus({ preventScroll: true });
      abertos.add(api);
    }

    function fechar(devolverFoco) {
      if (painel.hidden) return;
      painel.hidden = true;
      host.classList.remove('aberto');
      gatilho.setAttribute('aria-expanded', 'false');
      abertos.delete(api);
      if (devolverFoco) gatilho.focus();
    }

    async function escolher(valor) {
      fechar(true);
      if (String(valor) === String(atual) || ocupado) return;
      const anterior = atual;
      atual = String(valor);
      pintarGatilho();
      if (!op.aoEscolher) return;
      ocupado = true;
      host.classList.add('ocupado');
      try { await op.aoEscolher(atual); } catch (e) { atual = anterior; pintarGatilho(); }
      finally { ocupado = false; host.classList.remove('ocupado'); }
    }

    function teclado(e) {
      const itens = ul.querySelectorAll('[role=option]');
      if (e.key === 'ArrowDown') { e.preventDefault(); if (painel.hidden) abrir(); else marcarFoco(foco + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); if (painel.hidden) abrir(); else marcarFoco(foco - 1); }
      else if (e.key === 'Home' && !painel.hidden && e.target !== campo) { e.preventDefault(); marcarFoco(0); }
      else if (e.key === 'End' && !painel.hidden && e.target !== campo) { e.preventDefault(); marcarFoco(itens.length - 1); }
      else if (e.key === 'Enter' && !painel.hidden) { e.preventDefault(); if (itens[foco]) escolher(itens[foco].dataset.valor); }
      else if (e.key === 'Escape' && !painel.hidden) { e.preventDefault(); fechar(true); }
      else if (e.key === 'Tab' && !painel.hidden) fechar(false);
    }

    gatilho.addEventListener('click', () => (painel.hidden ? abrir() : fechar(true)));
    host.addEventListener('keydown', teclado);
    ul.tabIndex = -1;
    campo.addEventListener('input', pintarLista);

    function pintarRodape() {
      rodape.replaceChildren();
      const r = op.rodape;
      rodape.hidden = !r;
      if (!r) return;
      const a = el('a', null, r.texto);
      a.href = r.href;
      a.addEventListener('click', () => fechar(false));
      rodape.append(a);
    }

    const api = {
      host,
      fechar,
      opcoes(novas) { lista = (novas || []).map(o => ({ ...o, valor: String(o.valor) })); pintarGatilho(); if (!painel.hidden) pintarLista(); },
      valor(v) { if (v === undefined) return atual; atual = v == null ? '' : String(v); pintarGatilho(); if (!painel.hidden) pintarLista(); },
      rodape(r) { op.rodape = r; pintarRodape(); },
      semOpcoes(texto) { op.semOpcoes = texto; },
      desabilitar(sim) { gatilho.disabled = !!sim; host.classList.toggle('desabilitado', !!sim); }
    };
    pintarGatilho();
    pintarRodape();
    return api;
  }

  window.Seletor = Seletor;
})();
