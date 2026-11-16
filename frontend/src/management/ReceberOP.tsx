import { useEffect, useState } from 'react';
import { api, dataBR, erroTexto, type Count, type Order, type ReceiptRow, type State } from './api';

type Leitura = { text: string; suggestions: Partial<Order>; grade: Count[]; notice: string };
const TAMANHOS = ['PP', 'P', 'M', 'G', 'GG', 'XGG'];
const gradeVazia = () => TAMANHOS.map(name => ({ name, expected: 0, received: 0 }));
const lerDestinatario = () => { try { return localStorage.getItem('gestao.destinatario') || ''; } catch { return ''; } };

function Tabela({ titulo, linhas, setLinhas, igual, nomesFixos }: {
  titulo: string; linhas: Count[]; setLinhas: (l: Count[]) => void; igual: boolean; nomesFixos?: boolean;
}) {
  const mudar = (i: number, campo: keyof Count, valor: string) =>
    setLinhas(linhas.map((l, j) => j === i ? { ...l, [campo]: campo === 'name' ? valor : Math.max(0, Number(valor) || 0) } : l));
  return (
    <table className="grade">
      <thead><tr><th>{titulo}</th><th>Esperado</th>{!igual && <th>Recebido</th>}<th aria-label="Remover" /></tr></thead>
      <tbody>
        {linhas.map((l, i) => (
          <tr key={i} className={!igual && l.received !== l.expected ? 'divergente' : ''}>
            <td>{nomesFixos && TAMANHOS.includes(l.name)
              ? l.name
              : <input aria-label={`Nome do item ${i + 1}`} value={l.name} maxLength={60} required onChange={e => mudar(i, 'name', e.target.value)} />}</td>
            <td><input aria-label={`Esperado ${l.name || i + 1}`} type="number" min={0} max={1000000} value={l.expected || ''} placeholder="0" onChange={e => mudar(i, 'expected', e.target.value)} /></td>
            {!igual && <td><input aria-label={`Recebido ${l.name || i + 1}`} type="number" min={0} max={1000000} value={l.received || ''} placeholder="0" onChange={e => mudar(i, 'received', e.target.value)} /></td>}
            <td><button type="button" className="subtle icone" aria-label={`Remover ${l.name || 'item'}`} onClick={() => setLinhas(linhas.filter((_, j) => j !== i))}>×</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function ReceberOP({ state, refresh }: { state: State; refresh: () => Promise<void> }) {
  const [campos, setCampos] = useState({ code: '', client: '', model: '', fabric: '', dueDate: '' });
  const [grade, setGrade] = useState<Count[]>(gradeVazia);
  const [aviamentos, setAviamentos] = useState<Count[]>([]);
  const [igual, setIgual] = useState(true);
  const [nota, setNota] = useState('');
  const [leitura, setLeitura] = useState<Leitura | null>(null);
  const [foto, setFoto] = useState('');
  const [conferiOP, setConferiOP] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mensagem, setMensagem] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const [outlook, setOutlook] = useState(false);
  const [destinatario, setDestinatario] = useState(lerDestinatario);

  useEffect(() => { api<{ outlookConfigured: boolean }>('/integrations').then(d => setOutlook(d.outlookConfigured)).catch(() => {}); }, []);
  useEffect(() => () => { if (foto) URL.revokeObjectURL(foto); }, [foto]);

  const total = grade.reduce((s, l) => s + l.expected, 0);
  const recebido = igual ? total : grade.reduce((s, l) => s + l.received, 0);

  async function lerFoto(file?: File) {
    if (!file) return;
    setMensagem(null); setLeitura(null); setFoto(URL.createObjectURL(file)); setBusy(true);
    try {
      const form = new FormData(); form.append('arquivo', file);
      const r = await fetch('/api/gestao/op/read', { method: 'POST', body: form });
      const d = await r.json();
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Não foi possível ler a foto.');
      setLeitura(d);
      const s = d.suggestions || {};
      setCampos(c => ({ ...c, code: s.code || c.code, client: s.client || c.client, model: s.model || c.model }));
      if (d.grade?.length) setGrade(d.grade.map((g: Count) => ({ ...g, received: g.expected })));
      setMensagem({ tipo: 'success', texto: Object.keys(s).length || d.grade?.length
        ? 'Rascunho lido da foto. Confira cada campo com a OP antes de salvar.'
        : 'Não consegui tirar os campos da foto. Preencha à mão.' });
    } catch (e) { setMensagem({ tipo: 'error', texto: erroTexto(e) }); } finally { setBusy(false); }
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setMensagem(null);
    try {
      const linhas = (rows: Count[]) => rows.filter(l => l.name.trim() && (l.expected || l.received))
        .map(l => ({ name: l.name.trim(), expected: l.expected, received: igual ? l.expected : l.received }));
      const r = await api<{ order: Order; receipt: ReceiptRow }>('/intake', {
        ...campos, day: state.referenceDate, grade: linhas(grade), supplies: linhas(aviamentos), note: nota,
      });
      await refresh();
      setCampos({ code: '', client: '', model: '', fabric: '', dueDate: '' });
      setGrade(gradeVazia()); setAviamentos([]); setNota(''); setLeitura(null); setFoto(''); setConferiOP(false); setIgual(true);
      setMensagem({ tipo: 'success', texto: r.receipt.differences.length
        ? `Lote ${r.order.code} recebido com divergências. Veja o aviso abaixo.`
        : `Lote ${r.order.code} recebido: ${r.order.quantity} peças, tudo conferido.` });
    } catch (e) { setMensagem({ tipo: 'error', texto: erroTexto(e) }); } finally { setBusy(false); }
  }

  async function avisar(r: ReceiptRow) {
    if (!window.confirm(`Enviar o aviso "${r.subject}" para ${destinatario}?`)) return;
    setBusy(true);
    try {
      try { localStorage.setItem('gestao.destinatario', destinatario); } catch { /* sem armazenamento */ }
      await api(`/receipts/${r.id}/notify`, { recipient: destinatario, confirm: true });
      await refresh();
      setMensagem({ tipo: 'success', texto: 'Aviso enviado pelo Outlook.' });
    } catch (e) { setMensagem({ tipo: 'error', texto: erroTexto(e) }); } finally { setBusy(false); }
  }

  const campo = (k: keyof typeof campos, rotulo: string, extra: Record<string, unknown> = {}) => (
    <label>{rotulo}<input value={campos[k]} onChange={e => setCampos({ ...campos, [k]: e.target.value })} {...extra} /></label>
  );
  const recentes = (state.receipts || []).slice().reverse().slice(0, 10);

  return (
    <>
      <section className="card">
        <h2>Receber OP</h2>
        <p>Cadastre o lote e confira a grade numa tela só. A quantidade do lote é a soma da grade.</p>
        {mensagem && <div className={mensagem.tipo} role="status">{mensagem.texto}</div>}
        <form onSubmit={e => void salvar(e)}>
          <div className="grid-two">
            <div>
              <label className="arquivo">Ler foto da OP (opcional)
                <input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={e => void lerFoto(e.target.files?.[0])} />
              </label>
              {foto && <img src={foto} alt="Foto da OP para conferência" className="foto-op" />}
              {leitura && <details><summary>Texto lido da foto</summary><pre>{leitura.text || 'Nenhum texto legível.'}</pre></details>}
              <div className="fields dois">
                {campo('code', 'Código da OP', { required: true, maxLength: 40 })}
                {campo('client', 'Cliente', { required: true, maxLength: 100 })}
                {campo('model', 'Peça', { required: true, maxLength: 100 })}
                {campo('fabric', 'Tecido (opcional)', { maxLength: 60 })}
                {campo('dueDate', 'Prazo de entrega', { required: true, type: 'date', min: state.referenceDate })}
              </div>
            </div>
            <div>
              <label className="check"><input type="checkbox" checked={igual} onChange={e => setIgual(e.target.checked)} /> Recebi exatamente o que a OP pede</label>
              <Tabela titulo="Tamanho" linhas={grade} setLinhas={setGrade} igual={igual} nomesFixos />
              <button type="button" className="subtle" onClick={() => setGrade([...grade, { name: '', expected: 0, received: 0 }])}>+ Tamanho</button>
              <p className="total">Total: <strong>{total}</strong> peças{!igual && <> · recebidas: <strong className={recebido !== total ? 'ruim' : ''}>{recebido}</strong></>}</p>
              <details open={aviamentos.length > 0}>
                <summary>Aviamentos (opcional)</summary>
                {aviamentos.length > 0 && <Tabela titulo="Item" linhas={aviamentos} setLinhas={setAviamentos} igual={igual} />}
                <button type="button" className="subtle" onClick={() => setAviamentos([...aviamentos, { name: '', expected: 0, received: 0 }])}>+ Aviamento</button>
              </details>
              <label>Observação (opcional)<input value={nota} maxLength={1000} onChange={e => setNota(e.target.value)} /></label>
              {leitura && <label className="check"><input type="checkbox" required checked={conferiOP} onChange={e => setConferiOP(e.target.checked)} /> Conferi os dados lidos com a OP</label>}
              <button disabled={busy || !total}>{busy ? 'Salvando…' : 'Salvar recebimento'}</button>
            </div>
          </div>
        </form>
      </section>

      <section className="card">
        <h2>Últimos recebimentos</h2>
        {outlook && (
          <label>E-mail para avisos de divergência
            <input type="email" value={destinatario} onChange={e => setDestinatario(e.target.value)} placeholder="responsavel@empresa.com.br" />
          </label>
        )}
        {!recentes.length && <p>Nenhum recebimento ainda.</p>}
        {recentes.map(r => (
          <article className="candidate" key={r.id}>
            <h3>{state.orders.find(o => o.id === r.orderId)?.code} · {dataBR(r.day)} · <span className={`etiqueta ${r.differences.length ? 'ruim' : 'ok'}`}>{r.differences.length ? 'Com divergência' : 'Conferido'}</span></h3>
            {r.differences.map((d, i) => <p key={i}>{d.group === 'grade' ? 'Tamanho' : 'Aviamento'} {d.name}: {d.difference < 0 ? 'faltam' : 'sobram'} {Math.abs(d.difference)}</p>)}
            {r.differences.length > 0 && (
              <details><summary>Ver aviso</summary><pre>{r.message}</pre></details>
            )}
            {outlook && r.differences.length > 0 && (
              r.mailStatus === 'enviado'
                ? <small>Aviso enviado.</small>
                : <button disabled={busy || !destinatario || r.mailStatus === 'em envio'} onClick={() => void avisar(r)}>Enviar aviso por e-mail</button>
            )}
          </article>
        ))}
      </section>
    </>
  );
}
