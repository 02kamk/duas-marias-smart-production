import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Camera, ClipboardList, LayoutDashboard, LogOut, PackageCheck, Users } from 'lucide-react';
import { api, erroTexto, type State } from './api';
import './style.css';
import Painel from './Painel';
import ReceberOP from './ReceberOP';
import Producao from './Producao';
import Equipe from './Equipe';

const ABAS = [
  { id: 'painel', nome: 'Painel', Icone: LayoutDashboard },
  { id: 'receber', nome: 'Receber OP', Icone: PackageCheck },
  { id: 'producao', nome: 'Produção', Icone: ClipboardList },
  { id: 'equipe', nome: 'Equipe', Icone: Users },
] as const;
type Aba = typeof ABAS[number]['id'];
// Endereços antigos continuam funcionando.
const APELIDOS: Record<string, Aba> = { recebimento: 'receber', lotes: 'painel', colaboradores: 'equipe' };

function abaDoEndereco(): Aba {
  const h = location.hash.replace('#', '');
  return (ABAS.find(a => a.id === h)?.id) || APELIDOS[h] || 'painel';
}

export function App() {
  const [state, setState] = useState<State | null>(null);
  const [aba, setAba] = useState<Aba>(abaDoEndereco);
  const [erro, setErro] = useState('');
  const [aviso, setAviso] = useState('');
  const [busy, setBusy] = useState(false);

  async function refresh() { setState(await api<State>('/state')); }
  useEffect(() => { void refresh().catch(e => setErro(erroTexto(e))); }, []);
  useEffect(() => {
    const aoMudar = () => { setAba(abaDoEndereco()); setErro(''); setAviso(''); };
    window.addEventListener('hashchange', aoMudar);
    return () => window.removeEventListener('hashchange', aoMudar);
  }, []);

  async function agir(task: () => Promise<unknown>, sucesso = '', recarregar = false) {
    setBusy(true); setErro(''); setAviso('');
    try { await task(); if (recarregar) await refresh(); setAviso(sucesso); }
    catch (e) { setErro(erroTexto(e)); }
    finally { setBusy(false); }
  }

  const titulo = ABAS.find(a => a.id === aba)!.nome;
  return (
    <div className="workspace">
      <aside>
        <a className="brand" href="/">Duas<span>Marias</span></a>
        <nav aria-label="Gestão">
          <a className="nav-link" href="/"><Camera size={18} /> Inspeção</a>
          {ABAS.map(({ id, nome, Icone }) => (
            <a key={id} href={`#${id}`} className={`nav-link ${aba === id ? 'active' : ''}`} aria-current={aba === id ? 'page' : undefined}>
              <Icone size={18} /> {nome}
            </a>
          ))}
        </nav>
        <button className="sair" onClick={() => void fetch('/api/auth/logout', { method: 'POST' }).finally(() => location.assign('/login'))}>
          <LogOut size={16} /> Sair da conta
        </button>
      </aside>
      <main>
        <header>
          <h1>{titulo}</h1>
          {state && state.storage !== 'supabase' && <span className="badge" title="Os dados ficam guardados neste computador.">Neste computador</span>}
        </header>
        {erro && <div className="error" role="alert">{erro}</div>}
        {aviso && <div className="success" role="status">{aviso}</div>}
        {!state
          ? <section className="card"><p role="status">{erro ? 'Não foi possível carregar.' : 'Carregando…'}</p>{erro && <button onClick={() => void refresh().catch(e => setErro(erroTexto(e)))}>Tentar novamente</button>}</section>
          : <>
              {aba === 'painel' && <Painel state={state} agir={agir} busy={busy} />}
              {aba === 'receber' && <ReceberOP state={state} refresh={refresh} />}
              {aba === 'producao' && <Producao state={state} agir={agir} busy={busy} />}
              {aba === 'equipe' && <Equipe state={state} agir={agir} busy={busy} />}
            </>}
      </main>
    </div>
  );
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);
