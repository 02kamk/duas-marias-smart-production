import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {App} from './main';
import type {State} from './api';
const state:State={orders:[{id:'1',code:'OP-001',client:'Demo',model:'Camiseta',quantity:3000,produced:1950,dueDate:'2026-10-23',capacityPerDay:286,recentRate:220,reworkRate:.05,status:'Em andamento'}],employees:[{id:'1',name:'Ana Demo',active:true,availableMinutes:240,skills:{'Revisão final':{rate:40,quality:.95,experience:3}}}],operations:['Gola','Revisão final'],records:[],referenceDate:'2026-10-20',notice:'Demonstração local',audit:[],assignments:[],decisions:[]};
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
function setup(analysisMode='ready'){
 const fetchMock=vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const url=String(input);let body:unknown=state;
  if(url.endsWith('/model'))body={available:false,notice:'Treino sintético'};
  if(url.endsWith('/analysis'))body={mlAvailable:analysisMode==='ready',ml:analysisMode==='ready'?{riskScore:.8,futureRate:200,estimatedDays:5.25}:null,reason:'Execute o treino.',notice:'Não validado na empresa',generatedAt:'2026-10-20',modelVersion:'v1',snapshot:{remaining:1050,days:3,requiredPerDay:350,baselineLate:true,factors:['Capacidade insuficiente']},suggestions:['Revisar capacidade']};
  if(url.includes('/recommendations'))body={eligible:[],excluded:[{employeeId:'1',name:'Ana Demo',reason:'Disponibilidade insuficiente'}],notice:'Heurística'};
  if(init?.method==='POST')body={id:'new'};
  return {ok:true,json:async()=>body} as Response;
 });vi.stubGlobal('fetch',fetchMock);render(<App/>);return fetchMock;
}
it('navega sem remover acesso à câmera e mostra inferência sintética separada',async()=>{setup();await screen.findByRole('heading',{name:'Resumo'});expect(screen.getByRole('link',{name:/Inspeção, câmera e fotos/}).getAttribute('href')).toBe('/');fireEvent.click(screen.getByRole('button',{name:'Atrasos e capacidade'}));fireEvent.click(screen.getByRole('button',{name:'Analisar atraso e produção'}));await screen.findByRole('heading',{name:'Score de atraso da Random Forest: 80%'});expect(screen.getByText('Não validado na empresa')).toBeTruthy();expect(screen.getByText('Capacidade insuficiente')).toBeTruthy();});
it('exibe indisponibilidade em vez de retorno mock oculto',async()=>{setup('missing');await screen.findByRole('heading',{name:'Resumo'});fireEvent.click(screen.getByRole('button',{name:'Atrasos e capacidade'}));fireEvent.click(screen.getByRole('button',{name:'Analisar atraso e produção'}));expect(await screen.findByText(/Inferência indisponível: Execute o treino/)).toBeTruthy();expect(screen.queryByText(/Score de atraso da Random Forest/)).toBeNull()});
it('envia apontamento com operação, lote e contagens separadas',async()=>{const fetchMock=setup();await screen.findByRole('heading',{name:'Resumo'});fireEvent.click(screen.getByRole('button',{name:'Produção'}));fireEvent.change(screen.getByLabelText('Peças boas'),{target:{value:'20'}});fireEvent.change(screen.getByLabelText('Peças para retrabalho'),{target:{value:'3'}});fireEvent.click(screen.getByRole('button',{name:'Registrar produção demo'}));await screen.findByText('Apontamento salvo; indicadores e saldo atualizados.');const call=fetchMock.mock.calls.find(([url,init])=>String(url).endsWith('/records')&&init?.method==='POST');expect(JSON.parse(String(call?.[1]?.body))).toEqual({orderId:'1',employeeId:'1',operation:'Revisão final',goodQuantity:20,reworkQuantity:3,day:'2026-10-20'})});
it('consulta elegibilidade e mostra exclusões',async()=>{setup();await screen.findByRole('heading',{name:'Resumo'});fireEvent.click(screen.getByRole('button',{name:'Balanceamento'}));fireEvent.click(screen.getByRole('button',{name:'Consultar recomendações'}));expect(await screen.findByText('Sem candidato elegível para este período.')).toBeTruthy();expect(screen.getByText('Ana Demo: Disponibilidade insuficiente')).toBeTruthy()});
