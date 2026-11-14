import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import Receiving from './Receiving';
import type {State} from './api';
const state:State={orders:[{id:'1',code:'OP-001',client:'Demo',model:'Teste',quantity:100,produced:0,dueDate:'2026-11-20',capacityPerDay:50,recentRate:40,reworkRate:0,status:'Planejado'}],employees:[],operations:[],records:[],referenceDate:'2026-11-14',notice:'Teste',audit:[],assignments:[],decisions:[],receipts:[]};
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
it('envia a conferência de grade e mantém a produção separada',async()=>{
 const fetch=vi.fn(async()=>({ok:true,json:async()=>({id:'receipt'})}));vi.stubGlobal('fetch',fetch);
 const refresh=vi.fn(async()=>{});render(<Receiving state={state} refresh={refresh}/>);
 fireEvent.change(screen.getByLabelText('Esperado M'),{target:{value:'100'}});fireEvent.change(screen.getByLabelText('Recebido M'),{target:{value:'98'}});
 fireEvent.click(screen.getByRole('button',{name:'Salvar conferência'}));
 await screen.findByText('Conferência salva. Revise as divergências abaixo.');
 const [,options]=fetch.mock.calls[0] as unknown as [string,RequestInit];
 expect(JSON.parse(String(options.body))).toEqual({day:'2026-11-14',note:'',grade:['PP','P','M','G','GG'].map(name=>({name,expected:name==='M'?100:0,received:name==='M'?98:0})),supplies:[]});
 expect(refresh).toHaveBeenCalledOnce();expect(state.orders[0].produced).toBe(0);
});
