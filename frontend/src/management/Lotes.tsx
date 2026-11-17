import { useEffect, useState } from 'react';
import { api, dataBR, diaMes, num, erroTexto, type Agir, type Analysis, type InspecaoLote, type Order, type State } from './api';

type Situacao = { texto: string; detalhe?: string; classe: string; ordem: number };

/** Situação do lote na lista. O risco vem calculado do servidor (order.forecast). */
export function situacao(o: Order, referencia: string): Situacao {
  if (o.status === 'Concluído') return { texto: 'Concluído', classe: 'estado-neutro', ordem: 3 };
  if (o.dueDate < referencia) return { texto: 'Atrasado', classe: 'estado-defeito', ordem: 0 };
  if (o.forecast?.late) {
    const prevista = o.forecast.estimatedDeliveryDate;
    return { texto: 'Em risco', detalhe: prevista ? `prevista ${diaMes(prevista)}` : undefined, classe: 'estado-atencao', ordem: 1 };
  }
  return { texto: 'No prazo', classe: 'estado-ok', ordem: 2 };
}

type Inspecao = { porLote: Record<string, InspecaoLote>; ativo: string };

function DetalheLote({ order, inspecao, agir, busy }: { order: Order; inspecao?: InspecaoLote; agir: Agir; busy: boolean }) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [erro, setErro] = useState('');
  useEffect(() => {
    setAnalysis(null); setErro('');
    api<Analysis>(`/orders/${order.id}/analysis`).then(setAnalysis).catch(e => setErro(erroTexto(e)));
  }, [order.id, order.recentRate, order.capacityPerDay, order.dueDate, order.produced]);

  const s = analysis?.snapshot;
  const atrasado = !!s?.baselineLate;
  return (
    <section className="bloco detalhe-lote" aria-label={`Lote ${order.code}`}>
      <div>
        <h2>{order.code} · {order.model}</h2>
        <p className="texto-apoio">{order.client}{order.fabric ? ` · ${order.fabric}` : ''} · prazo {dataBR(order.dueDate)}</p>
      </div>
      <div>
        <progress value={order.produced} max={order.quantity} aria-label={`Progresso ${order.code}`} />
        <p className="texto-apoio num">{num(order.produced)} de {num(order.quantity)} peças prontas</p>
      </div>
      {erro && <p className="aviso aviso-erro">{erro}</p>}
      {s && (
        <>
          <div className={`aviso ${s.remaining === 0 ? '' : atrasado ? 'aviso-atencao' : 'aviso-ok'}`}>
            <strong>{s.remaining === 0 ? 'Lote concluído' : atrasado ? 'Risco de atrasar' : 'No prazo'}</strong>
            {s.remaining > 0 && <div>Entrega prevista: {dataBR(analysis?.estimatedDeliveryDate)} (prazo {dataBR(order.dueDate)})</div>}
          </div>
          {s.remaining > 0 && (
            <div className="detalhe-numeros">
              <div><small>Faltam</small><strong>{num(s.remaining)}</strong><small>peças</small></div>
              <div><small>Precisa por dia</small><strong>{num(s.requiredPerDay)}</strong><small>peças</small></div>
              <div><small>Ritmo atual</small><strong>{num(order.recentRate)}</strong><small>peças por dia</small></div>
            </div>
          )}
          <div>
            <h3>O que fazer agora</h3>
            <ul className="lista-marcada">{analysis!.suggestions.map(t => <li key={t}>{t}</li>)}</ul>
          </div>
        </>
      )}
      {inspecao && inspecao.inspecionadas > 0 && (
        <p className="texto-apoio">
          Inspeção: {num(inspecao.inspecionadas)} peças, {num(inspecao.defeitos)} com defeito
          {inspecao.pendentes > 0 && <> · <a href="/#conferir">{num(inspecao.pendentes)} para conferir</a></>}
        </p>
      )}
      <details>
        <summary>Ajustar prazo e ritmo</summary>
        <form key={order.id} className="formulario" onSubmit={e => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          void agir(() => api(`/orders/${order.id}/plan`, {
            dueDate: f.get('due'), capacityPerDay: Number(f.get('capacity')), recentRate: Number(f.get('rate')),
            reworkRate: Number(f.get('rework')) / 100, reason: String(f.get('reason') || '') || 'Ajuste de planejamento',
          }, 'PATCH'), 'Planejamento atualizado.', true);
        }}>
          <div className="campos dois">
            <label className="campo"><span className="campo-rotulo">Prazo</span><input className="entrada" name="due" type="date" defaultValue={order.dueDate} required /></label>
            <label className="campo"><span className="campo-rotulo">Retrabalho (%)</span><input className="entrada" name="rework" type="number" min={0} max={30} step={0.1} defaultValue={Math.round(order.reworkRate * 1000) / 10} required /></label>
            <label className="campo"><span className="campo-rotulo">Ritmo atual (peças/dia)</span><input className="entrada" name="rate" type="number" min={0} max={11000} defaultValue={order.recentRate} required /><span className="campo-ajuda">Quantas peças estão saindo por dia.</span></label>
            <label className="campo"><span className="campo-rotulo">Capacidade (peças/dia)</span><input className="entrada" name="capacity" type="number" min={1} max={10000} defaultValue={order.capacityPerDay} required /><span className="campo-ajuda">O máximo que a equipe consegue por dia.</span></label>
          </div>
          <label className="campo"><span className="campo-rotulo">Motivo (opcional)</span><input className="entrada" name="reason" maxLength={300} /></label>
          <div className="linha-botoes"><button className="btn btn-secundario" disabled={busy}>Salvar ajuste</button></div>
        </form>
      </details>
      {analysis?.mlAvailable && analysis.ml && (
        <details>
          <summary>Estimativa experimental</summary>
          <p className="texto-apoio">Ritmo futuro estimado: {num(analysis.ml.futureRate)} peças por dia. {analysis.notice}</p>
        </details>
      )}
    </section>
  );
}

export default function Lotes({ state, agir, busy }: { state: State; agir: Agir; busy: boolean }) {
  const [busca, setBusca] = useState('');
  const [mostrarConcluidos, setMostrarConcluidos] = useState(false);
  const [selecionado, setSelecionado] = useState('');
  const [inspecao, setInspecao] = useState<Inspecao>({ porLote: {}, ativo: '' });

  // Números da inspeção e lote em inspeção agora: vêm de outro endereço e não bloqueiam a lista.
  useEffect(() => {
    api<{ lotes?: { id: string; inspecao: InspecaoLote }[]; ativo?: { ordem_id?: string } | null }>('/inspecao')
      .then(d => setInspecao({
        porLote: Object.fromEntries((d.lotes || []).map(l => [l.id, l.inspecao])),
        ativo: d.ativo?.ordem_id || '',
      })).catch(() => {});
  }, [state.orders.length]);

  // No celular o detalhe fica abaixo da lista: rola até ele ao escolher um lote.
  const escolher = (id: string) => {
    setSelecionado(id);
    setTimeout(() => document.querySelector('.detalhe-lote')?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' }), 50);
  };
  const inspecionar = (o: Order) => void agir(async () => {
    await api(`/orders/${o.id}/inspecionar`, {});
    location.assign('/#ao-vivo');
  });

  const ref = state.referenceDate;
  const abertos = state.orders.filter(o => o.status !== 'Concluído');
  const pecasAbertas = abertos.reduce((s, o) => s + o.quantity, 0);
  const prontasAbertas = abertos.reduce((s, o) => s + Math.min(o.produced, o.quantity), 0);
  const emRisco = abertos.filter(o => situacao(o, ref).ordem === 1).length;
  const atrasados = abertos.filter(o => situacao(o, ref).ordem === 0).length;
  const lista = state.orders
    .filter(o => (mostrarConcluidos || o.status !== 'Concluído') &&
      `${o.code} ${o.client} ${o.model}`.toLowerCase().includes(busca.toLowerCase()))
    .map(o => ({ o, sit: situacao(o, ref) }))
    // Quem precisa de atenção primeiro; dentro do grupo, o prazo mais próximo.
    .sort((a, b) => a.sit.ordem - b.sit.ordem || a.o.dueDate.localeCompare(b.o.dueDate));
  const order = state.orders.find(o => o.id === selecionado);

  return (
    <>
      <dl className="resumo">
        <div><dt>Lotes em aberto</dt><dd>{abertos.length}</dd></div>
        <div className={emRisco ? 'alerta' : ''}><dt>Em risco</dt><dd>{emRisco}</dd></div>
        <div className={atrasados ? 'alerta' : ''}><dt>Atrasados</dt><dd>{atrasados}</dd></div>
        <div><dt>Peças a entregar</dt><dd>{num(pecasAbertas - prontasAbertas)}</dd></div>
        <div><dt>Progresso dos lotes abertos</dt><dd>{pecasAbertas ? Math.round(100 * prontasAbertas / pecasAbertas) : 0}%</dd></div>
      </dl>
      <div className="filtros">
        <label className="campo" style={{ flex: 1 }}><span className="campo-rotulo">Buscar</span><input className="entrada" value={busca} onChange={e => setBusca(e.target.value)} placeholder="Código, cliente ou peça" /></label>
        <label className="check"><input type="checkbox" checked={mostrarConcluidos} onChange={e => setMostrarConcluidos(e.target.checked)} /> Mostrar concluídos</label>
        <a href="/api/gestao/report.pdf" className="btn btn-quieto" download>Baixar em PDF</a>
      </div>
      <div className="lotes-grade">
        <section className="bloco lotes" style={{ padding: 0, gap: 0 }} aria-label="Lista de lotes">
          <div className="linha-cabecalho" aria-hidden="true"><span>Lote</span><span>Entrega</span><span>Prontas</span><span>Situação</span><span /></div>
          <div className="linhas">
            {lista.map(({ o, sit }) => (
              <div key={o.id} className={`linha linha-clicavel ${o.id === selecionado ? 'selecionada' : ''}`} onClick={() => escolher(o.id)}>
                <button type="button" className="lote-nome" style={{ textAlign: 'left' }} aria-label={`Abrir lote ${o.code}`} aria-expanded={o.id === selecionado}>
                  <strong>{o.code}</strong>
                  <small>{o.model} · {o.client}</small>
                </button>
                <span className="lote-entrega num"><span className="so-celular">entrega </span>{diaMes(o.dueDate)}</span>
                <div className="lote-progresso">
                  <span className="num">{num(o.produced)} / {num(o.quantity)}</span>
                  <div className="progresso" aria-hidden="true"><i style={{ width: `${Math.min(100, 100 * o.produced / o.quantity)}%` }} /></div>
                </div>
                <span className="lote-situacao"><span className={`estado ${sit.classe}`}>{sit.texto}</span>{sit.detalhe && <small>{sit.detalhe}</small>}</span>
                <span className="lote-acao" onClick={e => e.stopPropagation()}>
                  {o.status === 'Concluído' ? null : o.id === inspecao.ativo
                    ? <a className="btn btn-quieto btn-pequeno" href="/#ao-vivo">Em inspeção</a>
                    : <button type="button" className="btn btn-secundario btn-pequeno" disabled={busy} onClick={() => inspecionar(o)}>Inspecionar</button>}
                </span>
              </div>
            ))}
          </div>
          {!lista.length && <p className="vazio" style={{ border: 0 }}><strong>Nenhum lote encontrado</strong>{busca ? 'Tente outra busca.' : 'Os lotes cadastrados aparecem aqui.'}</p>}
        </section>
        {order
          ? <DetalheLote order={order} inspecao={inspecao.porLote[order.id]} agir={agir} busy={busy} />
          : lista.length > 0 && <p className="vazio detalhe-vazio">Escolha um lote para ver a previsão de entrega e o que fazer.</p>}
      </div>
    </>
  );
}
