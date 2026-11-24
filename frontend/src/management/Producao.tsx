import { useState } from 'react';
import { api, dataBR, horas, num, type Agir, type RecordRow, type Recommendation, type State } from './api';

type Props = { state: State; agir: Agir; busy: boolean };
const DURACOES = [15, 30, 45, 60, 90, 120, 180, 240, 360, 480];

function Apontamento({ state, agir, busy }: Props) {
  const abertos = state.orders.filter(o => o.status !== 'Concluído');
  const [operacao, setOperacao] = useState('Revisão final');
  const [erro, setErro] = useState('');
  // Só aparece quem está ativo e habilitado na operação escolhida.
  const habilitadas = state.employees.filter(e => e.active && e.skills[operacao]);
  return (
    <section className="bloco">
      <h2>Registrar produção</h2>
      {!abertos.length && <p className="aviso">Nenhum lote em aberto. <a href="#receber">Receba uma OP</a> primeiro.</p>}
      <form className="formulario" onSubmit={e => {
        e.preventDefault();
        const form = e.currentTarget;
        const f = new FormData(form);
        const boas = Number(f.get('good')), retrabalho = Number(f.get('rework'));
        if (boas + retrabalho < 1) { setErro('Informe ao menos uma peça boa ou de retrabalho.'); return; }
        setErro('');
        void agir(async () => {
          await api('/records', {
            orderId: f.get('orderId'), employeeId: f.get('employeeId'), operation: operacao,
            goodQuantity: boas, reworkQuantity: retrabalho, day: f.get('day'),
          });
          form.reset();
        }, 'Produção registrada.', true);
      }}>
        <div className="campos">
          <label className="campo"><span className="campo-rotulo">Lote</span><select className="entrada" name="orderId" required>{abertos.map(o => <option key={o.id} value={o.id}>{o.code} · faltam {num(o.quantity - o.produced)}</option>)}</select></label>
          <label className="campo"><span className="campo-rotulo">Operação</span><select className="entrada" value={operacao} onChange={e => setOperacao(e.target.value)}>{state.operations.map(o => <option key={o}>{o}</option>)}</select>
            <span className="campo-ajuda">{operacao === 'Revisão final' ? 'Conta como peça pronta no lote.' : 'Fica registrada por etapa; só a Revisão final conta peça pronta.'}</span></label>
          <label className="campo"><span className="campo-rotulo">Quem fez</span><select className="entrada" name="employeeId" required>{habilitadas.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
          <label className="campo"><span className="campo-rotulo">Peças boas</span><input className="entrada" name="good" type="number" inputMode="numeric" min={0} max={1000000} placeholder="0" /></label>
          <label className="campo"><span className="campo-rotulo">Peças para retrabalho</span><input className="entrada" name="rework" type="number" inputMode="numeric" min={0} max={1000000} placeholder="0" /></label>
          <label className="campo"><span className="campo-rotulo">Data</span><input className="entrada" name="day" type="date" max={state.referenceDate} defaultValue={state.referenceDate} required /></label>
        </div>
        {!habilitadas.length && <p className="aviso aviso-erro">Ninguém está habilitado em {operacao}. Ajuste em <a href="#equipe">Equipe</a>.</p>}
        {erro && <p className="aviso aviso-erro" role="alert">{erro}</p>}
        <div className="linha-botoes"><button className="btn btn-principal" disabled={busy || !abertos.length || !habilitadas.length}>Registrar produção</button></div>
      </form>
    </section>
  );
}

/** Uma linha do que já foi registrado, com correção e exclusão (sempre com motivo). */
function Registro({ r, state, agir, busy }: Props & { r: RecordRow }) {
  const [modo, setModo] = useState<'' | 'editar' | 'excluir'>('');
  const lote = state.orders.find(o => o.id === r.orderId)?.code || '—';
  const quem = state.employees.find(e => e.id === r.employeeId)?.name || '—';
  if (!modo) return (
    <tr>
      <td>{dataBR(r.day)}</td><td>{lote}</td><td>{quem}</td><td>{r.operation}</td>
      <td className="num" data-rotulo="Boas:">{num(r.goodQuantity)}</td><td className="num" data-rotulo="Retrabalho:">{num(r.reworkQuantity)}</td>
      <td className="acoes">
        <button type="button" className="btn btn-quieto" aria-label={`Editar apontamento de ${quem} no lote ${lote}`} onClick={() => setModo('editar')}>Editar</button>
        <button type="button" className="btn btn-quieto" aria-label={`Excluir apontamento de ${quem} no lote ${lote}`} onClick={() => setModo('excluir')}>Excluir</button>
      </td>
    </tr>
  );
  return (
    <tr>
      <td colSpan={7}>
        <form className="formulario" onSubmit={e => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const reason = String(f.get('reason') || '').trim();
          void agir(async () => {
            if (modo === 'editar') await api(`/records/${r.id}`, { goodQuantity: Number(f.get('good')), reworkQuantity: Number(f.get('rework')), reason }, 'PATCH');
            else await api(`/records/${r.id}`, { reason }, 'DELETE');
            setModo('');
          }, modo === 'editar' ? 'Apontamento corrigido.' : 'Apontamento excluído.', true);
        }}>
          <strong>{modo === 'editar' ? 'Corrigir' : 'Excluir'} apontamento: {dataBR(r.day)} · {lote} · {quem} · {r.operation}</strong>
          <div className="campos">
            {modo === 'editar' && <>
              <label className="campo"><span className="campo-rotulo">Peças boas</span><input className="entrada" name="good" type="number" min={0} max={1000000} defaultValue={r.goodQuantity} required /></label>
              <label className="campo"><span className="campo-rotulo">Peças para retrabalho</span><input className="entrada" name="rework" type="number" min={0} max={1000000} defaultValue={r.reworkQuantity} required /></label>
            </>}
            <label className="campo"><span className="campo-rotulo">Motivo</span><input className="entrada" name="reason" required minLength={3} maxLength={300} placeholder="Ex.: digitei a quantidade errada" /></label>
          </div>
          {modo === 'excluir' && <p className="texto-apoio">As {num(r.goodQuantity)} peças boas voltam para o saldo do lote.</p>}
          <div className="linha-botoes">
            <button className={`btn ${modo === 'excluir' ? 'btn-perigo' : 'btn-principal'} btn-pequeno`} disabled={busy}>{modo === 'editar' ? 'Salvar correção' : 'Excluir apontamento'}</button>
            <button type="button" className="btn btn-quieto" onClick={() => setModo('')}>Cancelar</button>
          </div>
        </form>
      </td>
    </tr>
  );
}

function Registros(props: Props) {
  const { state } = props;
  const [lote, setLote] = useState('');
  const [todos, setTodos] = useState(false);
  const linhas = state.records.filter(r => !lote || r.orderId === lote).slice().reverse();
  const visiveis = todos ? linhas : linhas.slice(0, 15);
  return (
    <section className="bloco">
      <div className="bloco-cabecalho">
        <h2>Já registrado</h2>
        <label className="campo campo-inline"><span className="campo-rotulo">Lote</span><select className="entrada" value={lote} onChange={e => setLote(e.target.value)}><option value="">Todos</option>{state.orders.map(o => <option key={o.id} value={o.id}>{o.code}</option>)}</select></label>
      </div>
      {!linhas.length ? <p className="texto-apoio">Nenhum apontamento ainda.</p> : (
        <div className="tabela-rolagem">
          <table className="tabela tabela-fichas">
            <thead><tr><th>Data</th><th>Lote</th><th>Quem fez</th><th>Operação</th><th className="num">Boas</th><th className="num">Retrabalho</th><th><span className="so-leitor">Ações</span></th></tr></thead>
            <tbody>{visiveis.map(r => <Registro key={r.id} r={r} {...props} />)}</tbody>
          </table>
        </div>
      )}
      {linhas.length > visiveis.length && <div className="linha-botoes"><button type="button" className="btn btn-quieto" onClick={() => setTodos(true)}>Ver todos ({linhas.length})</button></div>}
    </section>
  );
}

function Distribuicao({ state, agir, busy }: Props) {
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
    <>
      <section className="bloco">
        <h2>Distribuir tarefas</h2>
        <p className="texto-apoio">Reserva o tempo de uma pessoa para uma operação. Não conta peça: a produção é registrada na aba Apontamento.</p>
        <div className="campos">
          <label className="campo"><span className="campo-rotulo">Lote</span><select className="entrada" value={lote} onChange={e => { setLote(e.target.value); limpar(); }}>{abertos.map(o => <option key={o.id} value={o.id}>{o.code} · {o.model}</option>)}</select></label>
          <label className="campo"><span className="campo-rotulo">Operação</span><select className="entrada" value={operacao} onChange={e => { setOperacao(e.target.value); limpar(); }}>{state.operations.map(o => <option key={o}>{o}</option>)}</select></label>
          <label className="campo"><span className="campo-rotulo">Duração</span><select className="entrada" value={minutos} onChange={e => { setMinutos(Number(e.target.value)); limpar(); }}>{DURACOES.map(m => <option key={m} value={m}>{horas(m)}</option>)}</select></label>
          <label className="campo"><span className="campo-rotulo">Dia</span><input className="entrada" type="date" min={state.referenceDate} value={dia} onChange={e => { setDia(e.target.value); limpar(); }} /></label>
        </div>
        <div className="linha-botoes"><button className="btn btn-principal" disabled={busy || !lote} onClick={() => void agir(async () => setRecs(await api<Recommendation>(consulta)))}>Ver quem pode fazer</button></div>

        {recs && (
          <div>
            {!recs.eligible.length && <p className="aviso">Ninguém disponível para esta tarefa no dia.</p>}
            {recs.eligible.map(c => (
              <article className="candidato" key={c.employeeId}>
                <div>
                  <strong>{c.name}</strong>
                  <small>{c.rate != null ? `${num(c.rate)} peças/h · ${num((c.quality || 0) * 100)}% de qualidade · ` : 'Sem histórico nesta operação · '}{horas(c.availableMinutes)} livres</small>
                </div>
                <button className="btn btn-secundario btn-pequeno" disabled={busy} onClick={() => void agir(async () => {
                  await api('/assignments', { orderId: lote, employeeId: c.employeeId, operation: operacao, minutes: minutos, period: dia });
                  setRecs(await api<Recommendation>(consulta));
                }, `Tarefa atribuída a ${c.name}.`, true)}>Atribuir</button>
              </article>
            ))}
            {recs.excluded.length > 0 && (
              <details><summary>Indisponíveis ({recs.excluded.length})</summary>{recs.excluded.map(e => <p className="texto-apoio" key={e.employeeId}>{e.name}: {e.reason}</p>)}</details>
            )}
          </div>
        )}
      </section>

      <section className="bloco">
        <h2>Tarefas distribuídas</h2>
        {!futuras.length && <p className="texto-apoio">Nenhuma tarefa de hoje em diante.</p>}
        {futuras.map(a => (
          <article className="candidato" style={{ display: 'block' }} key={a.id}>
            <p><strong>{nomeLote(a.orderId)}</strong> · {a.operation} · {nomePessoa(a.employeeId)} · {horas(a.minutes)} · {dataBR(a.period)}</p>
            <details>
              <summary>Passar para outra pessoa</summary>
              <form className="formulario" onSubmit={e => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void agir(() => api(`/assignments/${a.id}/reallocate`, {
                  employeeId: f.get('employee'), minutes: a.minutes, period: a.period,
                  reason: String(f.get('reason') || '') || 'Tarefa passada para outra pessoa',
                }), 'Tarefa passada para outra pessoa.', true);
              }}>
                <div className="campos dois">
                  <label className="campo"><span className="campo-rotulo">Para</span><select className="entrada" name="employee">{state.employees.filter(e => e.active && e.skills[a.operation] && e.id !== a.employeeId).map(e => <option value={e.id} key={e.id}>{e.name}</option>)}</select></label>
                  <label className="campo"><span className="campo-rotulo">Motivo (opcional)</span><input className="entrada" name="reason" maxLength={300} /></label>
                </div>
                <div className="linha-botoes"><button className="btn btn-secundario btn-pequeno" disabled={busy}>Confirmar</button></div>
              </form>
            </details>
          </article>
        ))}
      </section>
    </>
  );
}

export default function Producao(props: Props & { aba: 'producao' | 'distribuir' }) {
  const { aba, ...resto } = props;
  return (
    <>
      <nav className="abas" aria-label="Produção">
        <a href="#producao" className={`aba ${aba === 'producao' ? 'ativa' : ''}`} aria-current={aba === 'producao' ? 'page' : undefined}>Apontamento</a>
        <a href="#distribuir" className={`aba ${aba === 'distribuir' ? 'ativa' : ''}`} aria-current={aba === 'distribuir' ? 'page' : undefined}>Distribuir tarefas</a>
      </nav>
      {aba === 'producao' ? <><Apontamento {...resto} /><Registros {...resto} /></> : <Distribuicao {...resto} />}
    </>
  );
}
