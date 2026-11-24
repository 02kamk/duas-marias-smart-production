import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from './main';
import type { State } from './api';

const state: State = {
  storage: 'local',
  orders: [{ id: '1', code: 'OP-001', client: 'Cliente A', model: 'Camiseta', quantity: 3000, produced: 1950, dueDate: '2026-10-23', capacityPerDay: 286, recentRate: 220, reworkRate: .05, status: 'Em andamento', forecast: { late: true, remaining: 1050, estimatedDeliveryDate: '2026-10-25' } }],
  employees: [
    { id: '1', name: 'Ana', active: true, availableMinutes: 240, skills: { 'Revisão final': { rate: 40, quality: .95, experience: 3 } } },
    { id: '2', name: 'Bia', active: true, availableMinutes: 240, skills: { Gola: { rate: 30, quality: .9, experience: 2 } } },
  ],
  operations: ['Gola', 'Revisão final'], records: [], referenceDate: '2026-10-20', assignments: [], receipts: [],
};

function setup() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    let body: unknown = state;
    if (url.endsWith('/analysis')) body = { estimatedDeliveryDate: '2026-10-25', mlAvailable: false, ml: null, notice: '', suggestions: ['Aumente a produção em cerca de 130 peças por dia, ou renegocie o prazo.'], snapshot: { remaining: 1050, days: 3, requiredPerDay: 350, estimatedDaysAtRecentRate: 5, baselineLate: true, factors: [] } };
    if (url.includes('/recommendations')) body = { eligible: [{ employeeId: '1', name: 'Ana', availableMinutes: 240, rate: 40, quality: .95 }], excluded: [{ employeeId: '2', name: 'Bia', reason: 'Sem habilitação' }] };
    if (url.endsWith('/integrations')) body = { outlookConfigured: false };
    if (url.endsWith('/intake')) body = { order: { ...state.orders[0], id: '9', code: 'OP-900', quantity: 100 }, receipt: { differences: [] } };
    if (init?.method === 'POST' && !url.endsWith('/intake')) body = { id: 'new' };
    return { ok: true, status: 200, json: async () => body } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<App />);
  return fetchMock;
}
const corpo = (mock: ReturnType<typeof setup>, fim: string) =>
  JSON.parse(String(mock.mock.calls.find(([u, i]) => String(u).endsWith(fim) && i?.method === 'POST')?.[1]?.body));

beforeEach(() => { location.hash = ''; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('mostra o risco de atraso já na lista e abre o lote com previsão de entrega e o que fazer', async () => {
  setup();
  await screen.findByRole('heading', { name: 'Lotes' });
  // O mesmo menu da Inspeção, nos dois sentidos.
  expect(screen.getAllByRole('link', { name: /Inspecionar/ })[0].getAttribute('href')).toBe('/#ao-vivo');
  expect(screen.getAllByRole('link', { name: /Relatórios/ })[0].getAttribute('href')).toBe('/#relatorios');
  // Receber OP e Produção saíram do menu.
  expect(screen.queryByRole('link', { name: /Receber OP/ })).toBeNull();
  expect(screen.queryByRole('link', { name: /^Produção$/ })).toBeNull();
  // Antes do clique a lista já diz que o lote está em risco e para quando fica.
  expect(screen.getByText('Em risco', { selector: '.estado' })).toBeTruthy();
  expect(screen.getByText('prevista 25/10')).toBeTruthy();
  fireEvent.click(screen.getByLabelText('Abrir lote OP-001'));
  expect(await screen.findByText('Risco de atrasar')).toBeTruthy();
  expect(screen.getByText(/Entrega prevista: 25\/10\/2026/)).toBeTruthy();
  expect(screen.getByText(/Aumente a produção/)).toBeTruthy();
});

it('recebe a OP num formulário só, com a quantidade tirada da grade', async () => {
  location.hash = '#receber';
  const fetchMock = setup();
  await screen.findByRole('heading', { name: 'Receber OP', level: 1 });
  fireEvent.change(screen.getByLabelText('Código da OP'), { target: { value: 'OP-900' } });
  fireEvent.change(screen.getByLabelText('Cliente'), { target: { value: 'Cliente B' } });
  fireEvent.change(screen.getByLabelText('Peça'), { target: { value: 'Blusa' } });
  fireEvent.change(screen.getByLabelText('Prazo de entrega'), { target: { value: '2026-11-30' } });
  fireEvent.change(screen.getByLabelText('Pedido P'), { target: { value: '60' } });
  fireEvent.change(screen.getByLabelText('Pedido M'), { target: { value: '40' } });
  expect(screen.getByText('100')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Salvar recebimento' }));
  expect(await screen.findByText(/Lote OP-900 recebido: 100 peças/)).toBeTruthy();
  const enviado = corpo(fetchMock, '/intake');
  expect(enviado.grade).toEqual([{ name: 'P', expected: 60, received: 60 }, { name: 'M', expected: 40, received: 40 }]);
  expect(enviado).not.toHaveProperty('capacityPerDay');
});

it('registra produção só com quem é habilitado na operação', async () => {
  location.hash = '#producao';
  const fetchMock = setup();
  await screen.findByRole('heading', { name: 'Registrar produção' });
  const quem = screen.getByLabelText('Quem fez') as HTMLSelectElement;
  expect(within(quem).queryByText('Bia')).toBeNull();
  fireEvent.change(screen.getByLabelText('Peças boas'), { target: { value: '20' } });
  fireEvent.change(screen.getByLabelText('Peças para retrabalho'), { target: { value: '3' } });
  fireEvent.click(screen.getByRole('button', { name: 'Registrar produção' }));
  await screen.findByText('Produção registrada.');
  expect(corpo(fetchMock, '/records')).toEqual({ orderId: '1', employeeId: '1', operation: 'Revisão final', goodQuantity: 20, reworkQuantity: 3, day: '2026-10-20' });
});

it('avisa o que falta em vez de travar o botão de salvar o recebimento', async () => {
  location.hash = '#receber';
  const fetchMock = setup();
  await screen.findByRole('heading', { name: 'Receber OP', level: 1 });
  fireEvent.click(screen.getByRole('button', { name: 'Salvar recebimento' }));
  expect((await screen.findByRole('alert')).textContent).toContain('o código da OP');
  expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/intake'))).toBe(false);
});

it('não registra produção com zero peças', async () => {
  location.hash = '#producao';
  const fetchMock = setup();
  await screen.findByRole('heading', { name: 'Registrar produção' });
  fireEvent.click(screen.getByRole('button', { name: 'Registrar produção' }));
  expect((await screen.findByRole('alert')).textContent).toContain('ao menos uma peça');
  expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith('/records') && i?.method === 'POST')).toBe(false);
});

it('corrige um apontamento já registrado, pedindo o motivo', async () => {
  location.hash = '#producao';
  state.records = [{ id: 'r1', orderId: '1', employeeId: '1', operation: 'Revisão final', day: '2026-10-20', goodQuantity: 20, reworkQuantity: 3 }];
  const fetchMock = setup();
  fireEvent.click(await screen.findByRole('button', { name: 'Editar apontamento de Ana no lote OP-001' }));
  fireEvent.change(screen.getAllByLabelText('Peças boas')[1], { target: { value: '25' } });
  fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'Contei errado' } });
  fireEvent.click(screen.getByRole('button', { name: 'Salvar correção' }));
  await screen.findByText('Apontamento corrigido.');
  const pedido = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith('/records/r1') && i?.method === 'PATCH')!;
  expect(JSON.parse(String(pedido[1]?.body))).toEqual({ goodQuantity: 25, reworkQuantity: 3, reason: 'Contei errado' });
  state.records = [];
});

it('distribui uma tarefa com um toque, sem justificativa obrigatória', async () => {
  location.hash = '#distribuir';
  const fetchMock = setup();
  await screen.findByRole('heading', { name: 'Distribuir tarefas' });
  fireEvent.click(screen.getByRole('button', { name: 'Ver quem pode fazer' }));
  expect(await screen.findByText(/40 peças\/h · 95% de qualidade · 4 h livres/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Atribuir' }));
  await screen.findByText('Tarefa atribuída a Ana.');
  expect(corpo(fetchMock, '/assignments')).toEqual({ orderId: '1', employeeId: '1', operation: 'Revisão final', minutes: 60, period: '2026-10-20' });
});

it('cadastra colaboradora marcando operações em caixas de seleção', async () => {
  location.hash = '#equipe';
  const fetchMock = setup();
  fireEvent.click(await screen.findByRole('button', { name: 'Nova colaboradora' }));
  await screen.findByRole('heading', { name: 'Nova colaboradora' });
  fireEvent.change(screen.getByLabelText('Nome'), { target: { value: 'Carla' } });
  const form = screen.getByRole('button', { name: 'Cadastrar' }).closest('form')!;
  fireEvent.click(within(form).getByLabelText('Gola'));
  fireEvent.click(within(form).getByRole('button', { name: 'Cadastrar' }));
  await screen.findByText('Colaboradora cadastrada.');
  await waitFor(() => expect(corpo(fetchMock, '/employees')).toEqual({ name: 'Carla', availableMinutes: 240, operations: ['Gola', 'Revisão final'] }));
});
