export interface Order {
  id: string; code: string; client: string; model: string; fabric?: string;
  quantity: number; produced: number; dueDate: string;
  capacityPerDay: number; recentRate: number; reworkRate: number; status: string;
  // Calculado pelo servidor em /state: risco de atraso sem precisar abrir o lote.
  forecast?: { late: boolean; remaining: number; estimatedDeliveryDate: string | null };
}
export interface Skill { rate: number | null; quality: number | null; experience: number | null }
export interface Employee { id: string; name: string; active: boolean; availableMinutes: number; skills: Record<string, Skill> }
export interface RecordRow { id: string; orderId: string; employeeId: string; operation: string; day: string; goodQuantity: number; reworkQuantity: number }
export interface Assignment { id: string; orderId: string; employeeId: string; operation: string; minutes: number; period: string; at: string }
export interface Count { name: string; expected: number; received: number }
export interface ReceiptRow {
  id: string; orderId: string; day: string; status: string; mailStatus: string;
  subject: string; message: string; differences: { group: string; name: string; difference: number }[];
}
export interface State {
  storage?: string; orders: Order[]; employees: Employee[]; operations: string[];
  records: RecordRow[]; referenceDate: string; assignments: Assignment[]; receipts?: ReceiptRow[];
}
export interface Analysis {
  estimatedDeliveryDate?: string | null; suggestions: string[];
  snapshot: { remaining: number; days: number; requiredPerDay: number | null; estimatedDaysAtRecentRate: number | null; baselineLate: boolean; factors: string[] };
  mlAvailable: boolean; ml: null | { riskScore: number; futureRate: number }; reason?: string; notice: string;
}
export interface Candidate { employeeId: string; name: string; availableMinutes: number; rate: number | null; quality: number | null }
export interface Recommendation { eligible: Candidate[]; excluded: { employeeId: string; name: string; reason: string }[] }

export async function api<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  const response = await fetch('/api/gestao' + path, body === undefined ? {} : {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (response.status === 401) { location.assign('/login'); throw new Error('Sessão encerrada. Entre novamente.'); }
  const data: unknown = await response.json();
  if (!response.ok) {
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === 'string') throw new Error(detail);
    // Erros de validação do FastAPI chegam como lista; mostra a primeira mensagem legível.
    if (Array.isArray(detail) && detail[0]?.msg) throw new Error(String(detail[0].msg).replace(/^Value error, /, ''));
    throw new Error('Confira os campos e tente novamente.');
  }
  return data as T;
}

export const dataBR = (iso?: string | null) => (iso ? iso.slice(0, 10).split('-').reverse().join('/') : '—');
export const num = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : n.toLocaleString('pt-BR', { maximumFractionDigits: digits });
/** Minutos em linguagem de fábrica: 420 -> "7 h", 90 -> "1 h 30", 45 -> "45 min". */
export const horas = (min: number) => {
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  return h ? (m ? `${h} h ${String(m).padStart(2, '0')}` : `${h} h`) : `${m} min`;
};
export const diaMes = (iso?: string | null) => (iso ? iso.slice(5, 10).split('-').reverse().join('/') : '—');
export type Agir = (task: () => Promise<unknown>, sucesso?: string, recarregar?: boolean) => Promise<void>;
export type Avisar = (tipo: 'ok' | 'erro', texto: string) => void;
export interface InspecaoLote { inspecionadas: number; defeitos: number; pendentes: number }
export const erroTexto = (e: unknown) => (e instanceof Error ? e.message : String(e));
