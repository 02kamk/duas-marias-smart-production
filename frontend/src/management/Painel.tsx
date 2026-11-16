import { useEffect, useState } from 'react';
import { api, dataBR, num, erroTexto, type Analysis, type Order, type State } from './api';

type Agir = (task: () => Promise<unknown>, sucesso?: string, recarregar?: boolean) => Promise<void>;

function situacao(o: Order, referencia: string) {
  if (o.status === 'Concluído') return { texto: 'Concluído', classe: 'ok' };
  if (o.dueDate < referencia) return { texto: 'Prazo vencido', classe: 'ruim' };
  return { texto: o.status, classe: '' };
}

function DetalheLote({ order, agir, busy }: { order: Order; agir: Agir; busy: boolean }) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [erro, setErro] = useState('');
  useEffect(() => {
    setAnalysis(null); setErro('');
    api<Analysis>(`/orders/${order.id}/analysis`).then(setAnalysis).catch(e => setErro(erroTexto(e)));
  }, [order.id, order.recentRate, order.capacityPerDay, order.dueDate, order.produced]);

  const s = analysis?.snapshot;
  const atrasado = !!s?.baselineLate;
  return (
    <section className="card detalhe-lote" aria-label={`Lote ${order.code}`}>
      <h2>{order.code} · {order.model}</h2>
      <p className="sub">{order.client}{order.fabric ? ` · ${order.fabric}` : ''} · prazo {dataBR(order.dueDate)}</p>
      <progress value={order.produced} max={order.quantity} aria-label={`Progresso ${order.code}`} />
      <p>{num(order.produced)} de {num(order.quantity)} peças prontas</p>
      {erro && <p className="error">{erro}</p>}
      {s && (
        <>
          <div className={`aviso-prazo ${atrasado ? 'ruim' : 'ok'}`}>
            <strong>{s.remaining === 0 ? 'Lote concluído' : atrasado ? 'Risco de atrasar' : 'No prazo'}</strong>
            {s.remaining > 0 && <span>Entrega prevista: {dataBR(analysis?.estimatedDeliveryDate)} (prazo {dataBR(order.dueDate)})</span>}
          </div>
          {s.remaining > 0 && (
            <div className="stats compacto">
              <div><small>Faltam</small><strong>{num(s.remaining)}</strong><small>peças</small></div>
              <div><small>Precisa por dia</small><strong>{num(s.requiredPerDay)}</strong><small>peças</small></div>
              <div><small>Ritmo atual</small><strong>{num(order.recentRate)}</strong><small>peças por dia</small></div>
            </div>
          )}
          <h3>O que fazer agora</h3>
          <ul>{analysis!.suggestions.map(t => <li key={t}>{t}</li>)}</ul>
        </>
      )}
      <details>
        <summary>Ajustar prazo e ritmo</summary>
        <form key={order.id} onSubmit={e => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          void agir(() => api(`/orders/${order.id}/plan`, {
            dueDate: f.get('due'), capacityPerDay: Number(f.get('capacity')), recentRate: Number(f.get('rate')),
            reworkRate: Number(f.get('rework')) / 100, reason: String(f.get('reason') || '') || 'Ajuste de planejamento',
          }, 'PATCH'), 'Planejamento atualizado.', true);
        }}>
          <div className="fields">
            <label>Prazo<input name="due" type="date" defaultValue={order.dueDate} required /></label>
            <label>Ritmo atual (peças/dia)<input name="rate" type="number" min={0} max={11000} defaultValue={order.recentRate} required /></label>
            <label>Capacidade (peças/dia)<input name="capacity" type="number" min={1} max={10000} defaultValue={order.capacityPerDay} required /></label>
            <label>Retrabalho (%)<input name="rework" type="number" min={0} max={30} step={0.1} defaultValue={Math.round(order.reworkRate * 1000) / 10} required /></label>
          </div>
          <label>Motivo (opcional)<input name="reason" maxLength={300} /></label>
          <button disabled={busy}>Salvar ajuste</button>
        </form>
      </details>
      {analysis?.mlAvailable && analysis.ml && (
        <details>
          <summary>Estimativa experimental</summary>
          <p>Ritmo futuro estimado: {num(analysis.ml.futureRate)} peças por dia. {analysis.notice}</p>
        </details>
      )}
    </section>
  );
}

export default function Painel({ state, agir, busy }: { state: State; agir: Agir; busy: boolean }) {
  const [busca, setBusca] = useState('');
  const [mostrarConcluidos, setMostrarConcluidos] = useState(false);
  const [selecionado, setSelecionado] = useState('');
  // No celular o detalhe fica abaixo da tabela: rola até ele ao escolher um lote.
  const escolher = (id: string) => {
    setSelecionado(id);
    setTimeout(() => document.querySelector('.detalhe-lote')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }), 50);
  };
  const ref = state.referenceDate;
  const abertos = state.orders.filter(o => o.status !== 'Concluído');
  const hoje = state.records.filter(r => r.day === ref && r.operation === 'Revisão final');
  const vencidos = abertos.filter(o => o.dueDate < ref).length;
  const lista = state.orders.filter(o =>
    (mostrarConcluidos || o.status !== 'Concluído') &&
    `${o.code} ${o.client} ${o.model}`.toLowerCase().includes(busca.toLowerCase()));
  const order = state.orders.find(o => o.id === selecionado);

  return (
    <>
      <div className="stats">
        {[
          ['Lotes em aberto', abertos.length, 'em produção ou planejados'],
          ['Peças prontas hoje', hoje.reduce((s, r) => s + r.goodQuantity, 0), 'na revisão final'],
          ['Retrabalho hoje', hoje.reduce((s, r) => s + r.reworkQuantity, 0), 'peças separadas'],
          ['Prazos vencidos', vencidos, 'lotes em aberto'],
        ].map(([titulo, valor, legenda]) => (
          <section className="card" key={String(titulo)}><p>{titulo}</p><strong className="metric">{valor}</strong><small>{legenda}</small></section>
        ))}
      </div>
      <div className="painel-grade">
        <section className="card">
          <div className="linha-titulo">
            <h2>Lotes</h2>
            <a href="/api/gestao/report.pdf" className="link-acao" download>Exportar PDF</a>
          </div>
          <div className="filtros">
            <label className="busca">Buscar<input value={busca} onChange={e => setBusca(e.target.value)} placeholder="Código, cliente ou peça" /></label>
            <label className="check"><input type="checkbox" checked={mostrarConcluidos} onChange={e => setMostrarConcluidos(e.target.checked)} /> Mostrar concluídos</label>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr>{['Lote', 'Cliente / peça', 'Prontas', 'Prazo', 'Situação'].map(t => <th key={t}>{t}</th>)}</tr></thead>
              <tbody>
                {lista.map(o => {
                  const sit = situacao(o, ref);
                  return (
                    <tr key={o.id} className={o.id === selecionado ? 'selecionado' : ''} onClick={() => escolher(o.id)}
                        tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') escolher(o.id); }} aria-label={`Abrir lote ${o.code}`}>
                      <td><strong>{o.code}</strong></td>
                      <td>{o.client}<small>{o.model}</small></td>
                      <td>{num(o.produced)} / {num(o.quantity)}<progress value={o.produced} max={o.quantity} aria-hidden="true" /></td>
                      <td>{dataBR(o.dueDate)}</td>
                      <td><span className={`etiqueta ${sit.classe}`}>{sit.texto}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!lista.length && <p>Nenhum lote encontrado. Receba uma OP na aba <a href="#receber">Receber OP</a>.</p>}
          </div>
        </section>
        {order
          ? <DetalheLote order={order} agir={agir} busy={busy} />
          : <section className="card vazio"><p>Toque num lote para ver a previsão de entrega e o que fazer.</p></section>}
      </div>
    </>
  );
}
