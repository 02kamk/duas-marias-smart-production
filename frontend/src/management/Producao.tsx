import { useState } from 'react';
import { api, dataBR, num, type Recommendation, type State } from './api';

type Agir = (task: () => Promise<unknown>, sucesso?: string, recarregar?: boolean) => Promise<void>;

function Apontamento({ state, agir, busy }: { state: State; agir: Agir; busy: boolean }) {
  const abertos = state.orders.filter(o => o.status !== 'Concluído');
  const [operacao, setOperacao] = useState('Revisão final');
  // Só aparece quem está ativo e habilitado na operação escolhida.
  const habilitadas = state.employees.filter(e => e.active && e.skills[operacao]);
  return (
    <section className="card">
      <h2>Registrar produção</h2>
      <p>Só a operação <strong>Revisão final</strong> conta peças prontas no lote. As outras ficam registradas por etapa.</p>
      {!abertos.length && <p>Nenhum lote em aberto. Receba uma OP primeiro.</p>}
      <form onSubmit={e => {
        e.preventDefault();
        const form = e.currentTarget;
        const f = new FormData(form);
        void agir(async () => {
          await api('/records', {
            orderId: f.get('orderId'), employeeId: f.get('employeeId'), operation: operacao,
            goodQuantity: Number(f.get('good')), reworkQuantity: Number(f.get('rework')), day: f.get('day'),
          });
          form.reset();
        }, 'Produção registrada.', true);
      }}>
        <div className="fields">
          <label>Lote<select name="orderId" required>{abertos.map(o => <option key={o.id} value={o.id}>{o.code} · faltam {num(o.quantity - o.produced)}</option>)}</select></label>
          <label>Operação<select value={operacao} onChange={e => setOperacao(e.target.value)}>{state.operations.map(o => <option key={o}>{o}</option>)}</select></label>
          <label>Quem fez<select name="employeeId" required>{habilitadas.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
          <label>Peças boas<input name="good" type="number" min={0} max={1000000} required defaultValue={0} /></label>
          <label>Peças para retrabalho<input name="rework" type="number" min={0} max={1000000} required defaultValue={0} /></label>
          <label>Data<input name="day" type="date" max={state.referenceDate} defaultValue={state.referenceDate} required /></label>
        </div>
        {!habilitadas.length && <p className="error">Ninguém está habilitado em {operacao}. Ajuste na aba Equipe.</p>}
        <button disabled={busy || !abertos.length || !habilitadas.length}>Registrar produção</button>
      </form>
    </section>
  );
}

function Distribuicao({ state, agir, busy }: { state: State; agir: Agir; busy: boolean }) {
  const abertos = state.orders.filter(o => o.status !== 'Concluído');
  const [lote, setLote] = useState(abertos[0]?.id || '');
  const [operacao, setOperacao] = useState('Revisão final');
  const [minutos, setMinutos] = useState(60);
  const [dia, setDia] = useState(state.referenceDate);
  const [recs, setRecs] = useState<Recommendation | null>(null);
  const consulta = `/recommendations?operation=${encodeURIComponent(operacao)}&period=${dia}&minutes=${minutos}`;
  const limpar = () => setRecs(null);
  const nomeLote = (id: string) => state.orders.find(o => o.id === id)?.code || '—';
  const nomePessoa = (id: string) => state.employees.find(e => e.id === id)?.name || '—';
  const futuras = state.assignments.filter(a => a.period >= state.referenceDate);

  return (
    <section className="card">
      <h2>Distribuir tarefas</h2>
      <p>Escolha o lote, a operação e quanto tempo leva. O sistema mostra quem está habilitado e tem tempo livre no dia.</p>
      <div className="fields">
        <label>Lote<select value={lote} onChange={e => { setLote(e.target.value); limpar(); }}>{abertos.map(o => <option key={o.id} value={o.id}>{o.code} · {o.model}</option>)}</select></label>
        <label>Operação<select value={operacao} onChange={e => { setOperacao(e.target.value); limpar(); }}>{state.operations.map(o => <option key={o}>{o}</option>)}</select></label>
        <label>Minutos<input type="number" min={1} max={480} value={minutos} onChange={e => { setMinutos(Number(e.target.value)); limpar(); }} /></label>
        <label>Dia<input type="date" min={state.referenceDate} value={dia} onChange={e => { setDia(e.target.value); limpar(); }} /></label>
      </div>
      <button disabled={busy || !lote || minutos < 1 || minutos > 480} onClick={() => void agir(async () => setRecs(await api<Recommendation>(consulta)))}>Ver quem pode fazer</button>

      {recs && (
        <div className="candidatos">
          {!recs.eligible.length && <p>Ninguém disponível para esta tarefa no dia.</p>}
          {recs.eligible.map(c => (
            <article className="candidato" key={c.employeeId}>
              <div>
                <strong>{c.name}</strong>
                <small>{c.rate != null ? `${num(c.rate)} peças/h · ${num((c.quality || 0) * 100)}% de qualidade · ` : 'Sem histórico nesta operação · '}{c.availableMinutes} min livres</small>
              </div>
              <button disabled={busy} onClick={() => void agir(async () => {
                await api('/assignments', { orderId: lote, employeeId: c.employeeId, operation: operacao, minutes: minutos, period: dia });
                setRecs(await api<Recommendation>(consulta));
              }, `Tarefa atribuída a ${c.name}.`, true)}>Atribuir</button>
            </article>
          ))}
          {recs.excluded.length > 0 && (
            <details><summary>Indisponíveis ({recs.excluded.length})</summary>{recs.excluded.map(e => <p key={e.employeeId}>{e.name}: {e.reason}</p>)}</details>
          )}
        </div>
      )}

      <h3>Tarefas distribuídas</h3>
      {!futuras.length && <p>Nenhuma tarefa distribuída para hoje em diante.</p>}
      {futuras.map(a => (
        <article className="candidate" key={a.id}>
          <p><strong>{nomeLote(a.orderId)}</strong> · {a.operation} · {nomePessoa(a.employeeId)} · {a.minutes} min · {dataBR(a.period)}</p>
          <details>
            <summary>Passar para outra pessoa</summary>
            <form onSubmit={e => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void agir(() => api(`/assignments/${a.id}/reallocate`, {
                employeeId: f.get('employee'), minutes: a.minutes, period: a.period,
                reason: String(f.get('reason') || '') || 'Tarefa passada para outra pessoa',
              }), 'Tarefa passada para outra pessoa.', true);
            }}>
              <div className="fields">
                <label>Para<select name="employee">{state.employees.filter(e => e.active && e.skills[a.operation] && e.id !== a.employeeId).map(e => <option value={e.id} key={e.id}>{e.name}</option>)}</select></label>
                <label>Motivo (opcional)<input name="reason" maxLength={300} /></label>
              </div>
              <button disabled={busy}>Confirmar</button>
            </form>
          </details>
        </article>
      ))}
    </section>
  );
}

function Historico({ state }: { state: State }) {
  const [lote, setLote] = useState('');
  const linhas = state.records.filter(r => !lote || r.orderId === lote).slice().reverse();
  return (
    <section className="card">
      <details>
        <summary><h2 className="inline">Produção registrada</h2></summary>
        <label>Lote<select value={lote} onChange={e => setLote(e.target.value)}><option value="">Todos</option>{state.orders.map(o => <option key={o.id} value={o.id}>{o.code}</option>)}</select></label>
        <div className="table-scroll">
          <table>
            <thead><tr>{['Data', 'Lote', 'Quem fez', 'Operação', 'Boas', 'Retrabalho'].map(t => <th key={t}>{t}</th>)}</tr></thead>
            <tbody>{linhas.map(r => (
              <tr key={r.id}><td>{dataBR(r.day)}</td><td>{state.orders.find(o => o.id === r.orderId)?.code}</td><td>{state.employees.find(e => e.id === r.employeeId)?.name}</td><td>{r.operation}</td><td>{r.goodQuantity}</td><td>{r.reworkQuantity}</td></tr>
            ))}</tbody>
          </table>
        </div>
        {!linhas.length && <p>Nenhum registro.</p>}
      </details>
    </section>
  );
}

export default function Producao(props: { state: State; agir: Agir; busy: boolean }) {
  return (<><Apontamento {...props} /><Distribuicao {...props} /><Historico state={props.state} /></>);
}
