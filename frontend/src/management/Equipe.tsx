import { useState } from 'react';
import { api, horas, num, type Agir, type Employee, type State } from './api';

type Props = { state: State; agir: Agir; busy: boolean };

function Operacoes({ todas, marcadas, nome }: { todas: string[]; marcadas: string[]; nome: string }) {
  return (
    <fieldset>
      <legend className="campo-rotulo">Operações que faz</legend>
      <div className="opcoes">
        {todas.map(op => (
          <label key={op} className="check"><input type="checkbox" name={nome} value={op} defaultChecked={marcadas.includes(op)} /> {op}</label>
        ))}
      </div>
    </fieldset>
  );
}

const CampoHoras = ({ padrao }: { padrao: number }) => (
  <label className="campo"><span className="campo-rotulo">Horas por dia</span>
    <input className="entrada" name="hours" type="number" min={0.5} max={8} step={0.5} defaultValue={padrao / 60} required />
  </label>
);
const minutosDoForm = (f: FormData) => Math.round(Number(f.get('hours')) * 60);

function Pessoa({ e, state, agir, busy }: Props & { e: Employee }) {
  const [editando, setEditando] = useState(false);
  const ops = Object.keys(e.skills);
  const temHistorico = Object.values(e.skills).some(s => s.rate != null);
  if (editando) return (
    <tr>
      <td colSpan={5}>
        <form className="formulario" onSubmit={ev => {
          ev.preventDefault();
          const f = new FormData(ev.currentTarget);
          void agir(async () => {
            await api(`/employees/${e.id}`, { availableMinutes: minutosDoForm(f), operations: f.getAll('ops') }, 'PATCH');
            setEditando(false);
          }, 'Cadastro atualizado.', true);
        }}>
          <strong>{e.name}</strong>
          <div className="campos"><CampoHoras padrao={e.availableMinutes} /></div>
          <Operacoes todas={state.operations} marcadas={ops} nome="ops" />
          {temHistorico && (
            <details><summary>Desempenho por operação</summary>
              {Object.entries(e.skills).map(([op, s]) => <p className="texto-apoio" key={op}>{op}: {s.rate == null ? 'sem histórico' : `${num(s.rate)} peças/h · ${num((s.quality || 0) * 100)}% de qualidade`}</p>)}
            </details>
          )}
          <div className="linha-botoes">
            <button className="btn btn-principal btn-pequeno" disabled={busy}>Salvar</button>
            <button type="button" className="btn btn-quieto" onClick={() => setEditando(false)}>Cancelar</button>
          </div>
        </form>
      </td>
    </tr>
  );
  return (
    <tr>
      <td><strong>{e.name}</strong></td>
      <td className="num" data-rotulo="Por dia:">{horas(e.availableMinutes)}</td>
      <td className="larga"><div className="etiquetas">{ops.map(op => <span className="etiqueta" key={op}>{op}</span>)}</div></td>
      <td><span className={`estado ${e.active ? 'estado-ok' : 'estado-neutro'}`}>{e.active ? 'Ativa' : 'Inativa'}</span></td>
      <td className="acoes">
        <button type="button" className="btn btn-quieto" aria-label={`Editar ${e.name}`} onClick={() => setEditando(true)}>Editar</button>
        <button type="button" className="btn btn-quieto" aria-label={`${e.active ? 'Desativar' : 'Reativar'} ${e.name}`} disabled={busy} onClick={() => void agir(() => api(`/employees/${e.id}`, { active: !e.active }, 'PATCH'), e.active ? 'Colaboradora desativada.' : 'Colaboradora reativada.', true)}>{e.active ? 'Desativar' : 'Reativar'}</button>
      </td>
    </tr>
  );
}

export default function Equipe({ state, agir, busy }: Props) {
  const [nova, setNova] = useState(false);
  return (
    <>
      {!nova
        ? <div className="linha-botoes"><button type="button" className="btn btn-principal" onClick={() => setNova(true)}>Nova colaboradora</button></div>
        : (
          <section className="bloco">
            <h2>Nova colaboradora</h2>
            <form className="formulario" onSubmit={ev => {
              ev.preventDefault();
              const form = ev.currentTarget;
              const f = new FormData(form);
              void agir(async () => {
                await api('/employees', { name: f.get('name'), availableMinutes: minutosDoForm(f), operations: f.getAll('operations') });
                form.reset(); setNova(false);
              }, 'Colaboradora cadastrada.', true);
            }}>
              <div className="campos">
                <label className="campo"><span className="campo-rotulo">Nome</span><input className="entrada" name="name" required minLength={2} maxLength={100} autoFocus /></label>
                <CampoHoras padrao={240} />
              </div>
              <Operacoes todas={state.operations} marcadas={['Revisão final']} nome="operations" />
              <div className="linha-botoes">
                <button className="btn btn-principal" disabled={busy}>Cadastrar</button>
                <button type="button" className="btn btn-quieto" onClick={() => setNova(false)}>Cancelar</button>
              </div>
            </form>
          </section>
        )}
      <section className="bloco" style={{ padding: 0 }}>
        <div className="tabela-rolagem">
          <table className="tabela tabela-fichas">
            <thead><tr><th>Nome</th><th className="num">Por dia</th><th>Operações</th><th>Situação</th><th><span className="so-leitor">Ações</span></th></tr></thead>
            <tbody>{state.employees.map(e => <Pessoa key={e.id} e={e} state={state} agir={agir} busy={busy} />)}</tbody>
          </table>
        </div>
        {!state.employees.length && <p className="vazio" style={{ border: 0 }}>Ninguém cadastrado ainda.</p>}
      </section>
    </>
  );
}
