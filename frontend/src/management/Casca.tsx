import { useEffect, useState, type ReactNode } from 'react';
import {
  Camera, ClipboardCheck, FileText, History, Layers, LogOut, Menu, SlidersHorizontal, Users,
  type LucideIcon,
} from 'lucide-react';

// O mesmo menu da Inspeção (src/pontocerto/app/static/index.html). Ao mudar um, mude o outro.
type Item = { href: string; nome: string; Icone: LucideIcon; id?: string; badge?: boolean };
const CHAO: Item[] = [
  { href: '/#ao-vivo', nome: 'Inspecionar', Icone: Camera },
  { href: '/#conferir', nome: 'Conferir', Icone: ClipboardCheck, badge: true },
  { href: '/#historico', nome: 'Histórico', Icone: History },
  { href: '#lotes', nome: 'Lotes', Icone: Layers, id: 'lotes' },
];
// Receber OP e Produção saíram do menu; as telas seguem em ReceberOP.tsx e Producao.tsx.
const GESTAO: Item[] = [
  { href: '#equipe', nome: 'Equipe', Icone: Users, id: 'equipe' },
  { href: '/#relatorios', nome: 'Relatórios', Icone: FileText },
];
const AJUSTES: Item = { href: '/#ajustes', nome: 'Ajustes', Icone: SlidersHorizontal };
const porNome = (nome: string) => [...CHAO, ...GESTAO, AJUSTES].find(i => i.nome === nome)!;

function sair() { void fetch('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).finally(() => location.assign('/login')); }

export default function Casca({ ativa, local, children }: { ativa: string; local: boolean; children: ReactNode }) {
  const [pendentes, setPendentes] = useState(0);
  const [mais, setMais] = useState(false);
  useEffect(() => {
    fetch('/api/eventos?limite=500&pendentes=true').then(r => r.json())
      .then(d => setPendentes(Array.isArray(d?.eventos) ? d.eventos.length : 0)).catch(() => {});
  }, []);
  useEffect(() => { setMais(false); }, [ativa]);

  const link = ({ href, nome, Icone, id, badge }: Item) => (
    <a key={nome} href={href} className={`nav-item ${id && id === ativa ? 'ativo' : ''}`} aria-current={id && id === ativa ? 'page' : undefined}>
      <Icone aria-hidden="true" /><span className="nav-texto">{nome}</span>
      {badge && pendentes > 0 && <span className="nav-badge">{pendentes >= 500 ? '500+' : pendentes}</span>}
    </a>
  );
  const marca = (
    <a className="marca" href="/#ao-vivo" aria-label="Duas Marias - início">
      <svg viewBox="0 0 34 34" width="26" height="26" fill="none" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M28 5.5 13 20.5" stroke="var(--terracota)" strokeWidth="3" />
        <path d="M13 20.5 8.5 25" stroke="var(--barro)" strokeWidth="3" />
        <path d="M26.8 9.6c2.1 3.9-1 6-3.4 7.5-2.4 1.5-4 4-1.6 6.6" stroke="var(--terracota-claro)" strokeWidth="2" />
        <path d="M2.5 29.5h29" stroke="var(--terracota-claro)" strokeWidth="3" strokeDasharray="5 4" />
      </svg>
      <span className="marca-nome">Duas<span>Marias</span></span>
    </a>
  );

  return (
    <div className="casca">
      <nav className="menu" aria-label="Navegação principal">
        {marca}
        <div className="menu-grupo"><p className="menu-titulo">Chão de fábrica</p>{CHAO.map(link)}</div>
        <div className="menu-grupo"><p className="menu-titulo">Gestão</p>{GESTAO.map(link)}</div>
        <div className="menu-rodape">
          {local && <p className="menu-estado">Dados neste computador</p>}
          {link(AJUSTES)}
          <button type="button" className="nav-item" onClick={sair}><LogOut aria-hidden="true" /><span className="nav-texto">Sair</span></button>
        </div>
      </nav>
      <header className="topo-movel">{marca}</header>
      <main className="conteudo">{children}</main>
      <nav className="tabbar" aria-label="Navegação inferior">
        {['Inspecionar', 'Conferir', 'Lotes', 'Equipe'].map(n => link(porNome(n)))}
        <button type="button" className="nav-item" aria-haspopup="true" aria-expanded={mais} onClick={() => setMais(!mais)}>
          <Menu aria-hidden="true" /><span className="nav-texto">Mais</span>
        </button>
      </nav>
      {mais && (
        <div className="menu-mais">
          {['Histórico', 'Relatórios', 'Ajustes'].map(n => link(porNome(n)))}
          <button type="button" className="nav-item" onClick={sair}><LogOut aria-hidden="true" /><span className="nav-texto">Sair</span></button>
        </div>
      )}
    </div>
  );
}
