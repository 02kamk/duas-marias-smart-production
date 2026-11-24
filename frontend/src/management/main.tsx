import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, erroTexto, type Agir, type Avisar, type State } from './api';
import './style.css';
import Casca from './Casca';
import Lotes from './Lotes';
import ReceberOP from './ReceberOP';
import Producao from './Producao';
import Equipe from './Equipe';

const ABAS = ['lotes', 'receber', 'producao', 'distribuir', 'equipe'] as const;
type Aba = typeof ABAS[number];
const TITULOS: Record<Aba, string> = { lotes: 'Lotes', receber: 'Receber OP', producao: 'Produção', distribuir: 'Produção', equipe: 'Equipe' };
// Receber OP e Produção não aparecem mais no menu, mas seguem abrindo pelo endereço
// (#receber, #producao, #distribuir) para dar para trazer de volta sem reescrever.
// Endereços antigos continuam funcionando.
const APELIDOS: Record<string, Aba> = { painel: 'lotes', recebimento: 'receber', colaboradores: 'equipe' };

function abaDoEndereco(): Aba {
  const h = location.hash.replace('#', '');
  return (ABAS as readonly string[]).includes(h) ? h as Aba : APELIDOS[h] || 'lotes';
}

type Toast = { id: number; tipo: 'ok' | 'erro'; texto: string };

export function App() {
  const [state, setState] = useState<State | null>(null);
  const [aba, setAba] = useState<Aba>(abaDoEndereco);
  const [falha, setFalha] = useState('');
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);

  async function refresh() { setState(await api<State>('/state')); }
  const carregar = () => { setFalha(''); void refresh().catch(e => setFalha(erroTexto(e))); };
  useEffect(carregar, []);
  useEffect(() => {
    const aoMudar = () => setAba(abaDoEndereco());
    window.addEventListener('hashchange', aoMudar);
    return () => window.removeEventListener('hashchange', aoMudar);
  }, []);

  // Avisos flutuantes, iguais aos da Inspeção: ficam à vista em qualquer ponto da página.
  const fechar = (id: number) => setToasts(t => t.filter(x => x.id !== id));
  const avisar: Avisar = (tipo, texto) => {
    if (!texto) return;
    const id = ++seq.current;
    setToasts(t => [...t.slice(-2), { id, tipo, texto }]);
    setTimeout(() => fechar(id), tipo === 'erro' ? 8000 : 4000);
  };

  const agir: Agir = async (task, sucesso = '', recarregar = false) => {
    setBusy(true);
    try { await task(); if (recarregar) await refresh(); avisar('ok', sucesso); }
    catch (e) { avisar('erro', erroTexto(e)); }
    finally { setBusy(false); }
  };

  return (
    <>
      <Casca ativa={aba === 'distribuir' ? 'producao' : aba} local={!!state && state.storage !== 'supabase'}>
        <div className="pagina-cabecalho"><h1>{TITULOS[aba]}</h1></div>
        {!state
          ? <div className="vazio">
              {falha
                ? <><strong>Não foi possível carregar</strong>{falha}<div className="linha-botoes" style={{ justifyContent: 'center', marginTop: 12 }}><button className="btn btn-secundario" onClick={carregar}>Tentar novamente</button></div></>
                : <span role="status">Carregando…</span>}
            </div>
          : <>
              {aba === 'lotes' && <Lotes state={state} agir={agir} busy={busy} />}
              {aba === 'receber' && <ReceberOP state={state} refresh={refresh} avisar={avisar} />}
              {(aba === 'producao' || aba === 'distribuir') && <Producao state={state} agir={agir} busy={busy} aba={aba} />}
              {aba === 'equipe' && <Equipe state={state} agir={agir} busy={busy} />}
            </>}
      </Casca>
      <div className="toasts" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id} className={`toast toast-${t.tipo}`} role={t.tipo === 'erro' ? 'alert' : 'status'} onClick={() => fechar(t.id)}>
            <span className="toast-texto">{t.texto}</span>
          </div>
        ))}
      </div>
    </>
  );
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);
