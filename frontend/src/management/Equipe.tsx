import { useState } from 'react';
import { api, num, type Employee, type State } from './api';

type Agir = (task: () => Promise<unknown>, sucesso?: string, recarregar?: boolean) => Promise<void>;

function Operacoes({ todas, marcadas, nome }: { todas: string[]; marcadas: string[]; nome: string }) {
  return (
    <fieldset className="operacoes">
      <legend>Operações que faz</legend>
      {todas.map(op => (
        <label key={op} className="check"><input type="checkbox" name={nome} value={op} defaultChecked={marcadas.includes(op)} /> {op}</label>
      ))}
    </fieldset>
  );
}

function Pessoa({ e, state, agir, busy }: { e: Employee; state: State; agir: Agir; busy: boolean }) {
  const [editando, setEditando] = useState(false);
  const ops = Object.keys(e.skills);
  return (
    <section className={`card pessoa ${e.active ? '' : 'inativa'}`}>
      <div className="linha-titulo">
        <h3>{e.name}</h3>
        {!e.active && <span className="etiqueta">Inativa</span>}
      </div>
      <p>{e.availableMinutes} min por dia · {ops.join(', ')}</p>
      {Object.entries(e.skills).some(([, s]) => s.rate != null) && (
        <details><summary>Desempenho por operação</summary>
          {Object.entries(e.skills).map(([op, s]) => <p key={op}>{op}: {s.rate == null ? 'sem histórico' : `${num(s.rate)} peças/h · ${num((s.quality || 0) * 100)}% de qualidade`}</p>)}
        </details>
      )}
      {editando ? (
        <form onSubmit={ev => {
          ev.preventDefault();
          const f = new FormData(ev.currentTarget);
          void agir(async () => {
            await api(`/employees/${e.id}`, { availableMinutes: Number(f.get('minutes')), operations: f.getAll('ops') }, 'PATCH');
            setEditando(false);
          }, 'Cadastro atualizado.', true);
        }}>
          <label>Minutos por dia<input name="minutes" type="number" min={1} max={480} defaultValue={e.availableMinutes} required /></label>
          <Operacoes todas={state.operations} marcadas={ops} nome="ops" />
          <div className="botoes"><button disabled={busy}>Salvar</button><button type="button" className="subtle" onClick={() => setEditando(false)}>Cancelar</button></div>
        </form>
      ) : (
        <div className="botoes">
          <button type="button" className="subtle" onClick={() => setEditando(true)}>Editar</button>
          <button type="button" className="subtle" disabled={busy} onClick={() => void agir(() => api(`/employees/${e.id}`, { active: !e.active }, 'PATCH'), e.active ? 'Colaboradora desativada.' : 'Colaboradora reativada.', true)}>{e.active ? 'Desativar' : 'Reativar'}</button>
        </div>
      )}
    </section>
  );
}

export default function Equipe({ state, agir, busy }: { state: State; agir: Agir; busy: boolean }) {
  return (
    <>
      <section className="card">
        <h2>Nova colaboradora</h2>
        <form onSubmit={ev => {
          ev.preventDefault();
          const form = ev.currentTarget;
          const f = new FormData(form);
          void agir(async () => {
            await api('/employees', { name: f.get('name'), availableMinutes: Number(f.get('availableMinutes')), operations: f.getAll('operations') });
            form.reset();
          }, 'Colaboradora cadastrada.', true);
        }}>
          <div className="fields">
            <label>Nome<input name="name" required minLength={2} maxLength={100} /></label>
            <label>Minutos por dia<input name="availableMinutes" type="number" min={1} max={480} defaultValue={240} required /></label>
          </div>
          <Operacoes todas={state.operations} marcadas={['Revisão final']} nome="operations" />
          <button disabled={busy}>Cadastrar</button>
        </form>
      </section>
      <div className="grid-two">
        {state.employees.map(e => <Pessoa key={e.id} e={e} state={state} agir={agir} busy={busy} />)}
      </div>
    </>
  );
}
