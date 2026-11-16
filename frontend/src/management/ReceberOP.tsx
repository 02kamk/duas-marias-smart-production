import { useEffect, useState } from 'react';
import { api, dataBR, erroTexto, type Avisar, type Count, type Order, type ReceiptRow, type State } from './api';

type Leitura = { text: string; suggestions: Partial<Order>; grade: Count[]; notice: string };
const TAMANHOS = ['PP', 'P', 'M', 'G', 'GG', 'XGG'];
const gradeVazia = () => TAMANHOS.map(name => ({ name, expected: 0, received: 0 }));
const lerDestinatario = () => { try { return localStorage.getItem('gestao.destinatario') || ''; } catch { return ''; } };
const inteiro = (valor: string) => Math.max(0, Math.floor(Number(valor) || 0));

/** Grade na horizontal, como vem na OP em papel: uma coluna por tamanho. */
function Grade({ linhas, setLinhas, comRecebido }: { linhas: Count[]; setLinhas: (l: Count[]) => void; comRecebido: boolean }) {
  const mudar = (i: number, campo: keyof Count, valor: string) =>
    setLinhas(linhas.map((l, j) => j === i ? { ...l, [campo]: campo === 'name' ? valor : inteiro(valor) } : l));
  const fixo = (l: Count) => TAMANHOS.includes(l.name);
  return (
    <div className="grade-tamanhos">
      <table>
        <thead>
          <tr>
            <th scope="row">Tamanho</th>
            {linhas.map((l, i) => (
              <th key={i} scope="col">
                {fixo(l) ? l.name : (
                  <span style={{ display: 'flex', gap: 4 }}>
                    <input className="entrada" aria-label={`Nome do tamanho ${i + 1}`} value={l.name} maxLength={60} placeholder="Ex.: 38" onChange={e => mudar(i, 'name', e.target.value)} />
                    <button type="button" className="btn btn-quieto btn-icone" aria-label={`Remover tamanho ${l.name || i + 1}`} onClick={() => setLinhas(linhas.filter((_, j) => j !== i))}>×</button>
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Pedido</th>
            {linhas.map((l, i) => (
              <td key={i}><input className="entrada" aria-label={`Pedido ${l.name || i + 1}`} type="number" inputMode="numeric" min={0} max={1000000} value={l.expected || ''} placeholder="0" onChange={e => mudar(i, 'expected', e.target.value)} /></td>
            ))}
          </tr>
          {comRecebido && (
            <tr>
              <th scope="row">Recebido</th>
              {linhas.map((l, i) => (
                <td key={i} className={l.received !== l.expected ? 'divergente' : ''}><input className="entrada" aria-label={`Recebido ${l.name || i + 1}`} type="number" inputMode="numeric" min={0} max={1000000} value={l.received || ''} placeholder="0" onChange={e => mudar(i, 'received', e.target.value)} /></td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function Aviamentos({ linhas, setLinhas, comRecebido }: { linhas: Count[]; setLinhas: (l: Count[]) => void; comRecebido: boolean }) {
  const mudar = (i: number, campo: keyof Count, valor: string) =>
    setLinhas(linhas.map((l, j) => j === i ? { ...l, [campo]: campo === 'name' ? valor : inteiro(valor) } : l));
  return (
    <table className="tabela">
      <thead><tr><th>Item</th><th>Pedido</th>{comRecebido && <th>Recebido</th>}<th><span className="so-leitor">Remover</span></th></tr></thead>
      <tbody>
        {linhas.map((l, i) => (
          <tr key={i}>
            <td><input className="entrada" aria-label={`Nome do aviamento ${i + 1}`} value={l.name} maxLength={60} placeholder="Ex.: etiqueta de composição" onChange={e => mudar(i, 'name', e.target.value)} /></td>
            <td><input className="entrada" aria-label={`Pedido de ${l.name || 'aviamento ' + (i + 1)}`} type="number" min={0} max={1000000} value={l.expected || ''} placeholder="0" onChange={e => mudar(i, 'expected', e.target.value)} /></td>
            {comRecebido && <td><input className="entrada" aria-label={`Recebido de ${l.name || 'aviamento ' + (i + 1)}`} type="number" min={0} max={1000000} value={l.received || ''} placeholder="0" onChange={e => mudar(i, 'received', e.target.value)} /></td>}
            <td className="acoes"><button type="button" className="btn btn-quieto btn-icone" aria-label={`Remover ${l.name || 'aviamento'}`} onClick={() => setLinhas(linhas.filter((_, j) => j !== i))}>×</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function ReceberOP({ state, refresh, avisar }: { state: State; refresh: () => Promise<void>; avisar: Avisar }) {
  const [campos, setCampos] = useState({ code: '', client: '', model: '', fabric: '', dueDate: '' });
  const [grade, setGrade] = useState<Count[]>(gradeVazia);
  const [aviamentos, setAviamentos] = useState<Count[]>([]);
  const [igual, setIgual] = useState(true);
  const [nota, setNota] = useState('');
  const [leitura, setLeitura] = useState<Leitura | null>(null);
  const [foto, setFoto] = useState('');
  const [conferiOP, setConferiOP] = useState(false);
  const [busy, setBusy] = useState(false);
  const [faltando, setFaltando] = useState<string[]>([]);
  const [outlook, setOutlook] = useState(false);
  const [destinatario, setDestinatario] = useState(lerDestinatario);
  const [enviando, setEnviando] = useState('');

  useEffect(() => { api<{ outlookConfigured: boolean }>('/integrations').then(d => setOutlook(!!d.outlookConfigured)).catch(() => {}); }, []);
  useEffect(() => () => { if (foto) URL.revokeObjectURL(foto); }, [foto]);

  const total = grade.reduce((s, l) => s + l.expected, 0);
  const recebido = igual ? total : grade.reduce((s, l) => s + l.received, 0);
  const diferencas = igual ? [] : grade.filter(l => l.received !== l.expected && (l.expected || l.received));

  // Ao marcar "Há diferença", o recebido começa igual ao pedido: a pessoa só corrige o que mudou.
  function mudarIgual(novo: boolean) {
    if (!novo) {
      setGrade(grade.map(l => ({ ...l, received: l.expected })));
      setAviamentos(aviamentos.map(l => ({ ...l, received: l.expected })));
    }
    setIgual(novo);
  }

  async function lerFoto(file?: File) {
    if (!file) return;
    setLeitura(null); setFoto(URL.createObjectURL(file)); setBusy(true);
    try {
      const form = new FormData(); form.append('arquivo', file);
      const r = await fetch('/api/gestao/op/read', { method: 'POST', body: form });
      const d = await r.json();
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Não foi possível ler a foto.');
      setLeitura(d);
      const s = d.suggestions || {};
      setCampos(c => ({ ...c, code: s.code || c.code, client: s.client || c.client, model: s.model || c.model }));
      if (d.grade?.length) setGrade(d.grade.map((g: Count) => ({ ...g, received: g.expected })));
      avisar('ok', Object.keys(s).length || d.grade?.length
        ? 'Rascunho lido da foto. Confira cada campo com a OP antes de salvar.'
        : 'Não consegui tirar os campos da foto. Preencha à mão.');
    } catch (e) { avisar('erro', erroTexto(e)); } finally { setBusy(false); }
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    // O botão fica sempre ativo; em vez de travar, a tela diz o que falta.
    const falta = [
      !campos.code.trim() && 'o código da OP', !campos.client.trim() && 'o cliente', !campos.model.trim() && 'a peça',
      !campos.dueDate && 'o prazo de entrega', !total && 'a quantidade de pelo menos um tamanho',
      grade.some(l => !l.name.trim() && (l.expected || l.received)) && 'o nome do tamanho novo',
      !!leitura && !conferiOP && 'a confirmação de que conferiu os dados lidos da foto',
    ].filter(Boolean) as string[];
    setFaltando(falta);
    if (falta.length) return;
    setBusy(true);
    try {
      const linhas = (rows: Count[]) => rows.filter(l => l.name.trim() && (l.expected || l.received))
        .map(l => ({ name: l.name.trim(), expected: l.expected, received: igual ? l.expected : l.received }));
      const r = await api<{ order: Order; receipt: ReceiptRow }>('/intake', {
        ...campos, day: state.referenceDate, grade: linhas(grade), supplies: linhas(aviamentos), note: nota,
      });
      await refresh();
      setCampos({ code: '', client: '', model: '', fabric: '', dueDate: '' });
      setGrade(gradeVazia()); setAviamentos([]); setNota(''); setLeitura(null); setFoto(''); setConferiOP(false); setIgual(true);
      avisar('ok', r.receipt.differences.length
        ? `Lote ${r.order.code} recebido com diferenças. Veja em Últimos recebimentos.`
        : `Lote ${r.order.code} recebido: ${r.order.quantity} peças, tudo conferido.`);
    } catch (e) { avisar('erro', erroTexto(e)); } finally { setBusy(false); }
  }

  async function enviarAviso(r: ReceiptRow) {
    setBusy(true);
    try {
      try { localStorage.setItem('gestao.destinatario', destinatario); } catch { /* sem armazenamento */ }
      await api(`/receipts/${r.id}/notify`, { recipient: destinatario, confirm: true });
      await refresh();
      setEnviando('');
      avisar('ok', 'Aviso enviado pelo Outlook.');
    } catch (e) { avisar('erro', erroTexto(e)); } finally { setBusy(false); }
  }

  const campo = (k: keyof typeof campos, rotulo: string, extra: Record<string, unknown> = {}) => (
    <label className="campo"><span className="campo-rotulo">{rotulo}</span><input className="entrada" value={campos[k]} onChange={e => setCampos({ ...campos, [k]: e.target.value })} {...extra} /></label>
  );
  const recentes = (state.receipts || []).slice().reverse().slice(0, 10);

  return (
    <>
      <form className="formulario" noValidate onSubmit={e => void salvar(e)}>
        <section className="bloco">
          <div className="bloco-cabecalho">
            <h2><span className="passo">1 de 3 · </span>Dados da OP</h2>
            <label className="btn btn-secundario btn-pequeno">
              {busy && !leitura && foto ? 'Lendo…' : 'Ler da foto da OP'}
              <input className="input-oculto" type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={e => { void lerFoto(e.target.files?.[0]); e.target.value = ''; }} />
            </label>
          </div>
          {foto && <img src={foto} alt="Foto da OP para conferência" className="foto-op" />}
          {leitura && <details><summary>Texto lido da foto</summary><pre>{leitura.text || 'Nenhum texto legível.'}</pre></details>}
          <div className="campos">
            {campo('code', 'Código da OP', { maxLength: 40 })}
            {campo('client', 'Cliente', { maxLength: 100 })}
            {campo('model', 'Peça', { maxLength: 100 })}
            {campo('fabric', 'Tecido (opcional)', { maxLength: 60 })}
            {campo('dueDate', 'Prazo de entrega', { type: 'date', min: state.referenceDate })}
          </div>
        </section>

        <section className="bloco">
          <h2><span className="passo">2 de 3 · </span>Grade pedida</h2>
          <Grade linhas={grade} setLinhas={setGrade} comRecebido={!igual} />
          <div className="bloco-cabecalho">
            <p className="grade-total">
              Total pedido <strong>{total}</strong> peças
              {!igual && <> · recebido <strong>{recebido}</strong>{diferencas.map(l => (
                <span key={l.name} className="falta"> · {l.received < l.expected ? 'faltam' : 'sobram'} {Math.abs(l.received - l.expected)} no {l.name || 'tamanho novo'}</span>
              ))}</>}
            </p>
            <button type="button" className="btn btn-quieto" onClick={() => setGrade([...grade, { name: '', expected: 0, received: 0 }])}>+ Outro tamanho</button>
          </div>
        </section>

        <section className="bloco">
          <h2><span className="passo">3 de 3 · </span>Conferência</h2>
          <fieldset className="opcoes">
            <legend className="so-leitor">O que chegou</legend>
            <label className="check"><input type="radio" name="conferencia" checked={igual} onChange={() => mudarIgual(true)} /> Recebi tudo certo</label>
            <label className="check"><input type="radio" name="conferencia" checked={!igual} onChange={() => mudarIgual(false)} /> Há diferença no que chegou</label>
          </fieldset>
          {!igual && <p className="texto-apoio">Corrija na linha <strong>Recebido</strong> da grade o que chegou diferente.</p>}
          <details open={aviamentos.length > 0}>
            <summary>Aviamentos (opcional)</summary>
            {aviamentos.length > 0 && <Aviamentos linhas={aviamentos} setLinhas={setAviamentos} comRecebido={!igual} />}
            <button type="button" className="btn btn-quieto" onClick={() => setAviamentos([...aviamentos, { name: '', expected: 0, received: 0 }])}>+ Aviamento</button>
          </details>
          <label className="campo"><span className="campo-rotulo">Observação (opcional)</span><input className="entrada" value={nota} maxLength={1000} onChange={e => setNota(e.target.value)} /></label>
          {leitura && <label className="check"><input type="checkbox" checked={conferiOP} onChange={e => setConferiOP(e.target.checked)} /> Conferi os dados lidos com a OP</label>}
          {faltando.length > 0 && <p className="aviso aviso-erro" role="alert">Falta preencher: {faltando.join(', ')}.</p>}
          <div className="linha-botoes"><button className="btn btn-principal" disabled={busy}>{busy ? 'Salvando…' : 'Salvar recebimento'}</button></div>
        </section>
      </form>

      <section className="bloco">
        <h2>Últimos recebimentos</h2>
        {outlook && (
          <label className="campo"><span className="campo-rotulo">E-mail para avisos de diferença</span>
            <input className="entrada" type="email" value={destinatario} onChange={e => setDestinatario(e.target.value)} placeholder="responsavel@empresa.com.br" />
          </label>
        )}
        {!recentes.length && <p className="texto-apoio">Nenhum recebimento ainda.</p>}
        {recentes.map(r => (
          <article className="candidato" style={{ display: 'block' }} key={r.id}>
            <div className="bloco-cabecalho">
              <h3>{state.orders.find(o => o.id === r.orderId)?.code} · {dataBR(r.day)}</h3>
              <span className={`estado ${r.differences.length ? 'estado-atencao' : 'estado-ok'}`}>{r.differences.length ? 'Com diferença' : 'Conferido'}</span>
            </div>
            {r.differences.map((d, i) => <p className="texto-apoio" key={i}>{d.group === 'grade' ? 'Tamanho' : 'Aviamento'} {d.name}: {d.difference < 0 ? 'faltam' : 'sobram'} {Math.abs(d.difference)}</p>)}
            {r.differences.length > 0 && <details><summary>Ver aviso</summary><pre>{r.message}</pre></details>}
            {outlook && r.differences.length > 0 && (
              r.mailStatus === 'enviado' ? <small>Aviso enviado.</small>
                : enviando === r.id
                  ? <div className="linha-botoes">
                      <span>Enviar o aviso para {destinatario}?</span>
                      <button type="button" className="btn btn-principal btn-pequeno" disabled={busy} onClick={() => void enviarAviso(r)}>Enviar</button>
                      <button type="button" className="btn btn-quieto" onClick={() => setEnviando('')}>Cancelar</button>
                    </div>
                  : <button type="button" className="btn btn-secundario btn-pequeno" disabled={busy || !destinatario || r.mailStatus === 'em envio'} onClick={() => setEnviando(r.id)}>Enviar aviso por e-mail</button>
            )}
          </article>
        ))}
      </section>
    </>
  );
}
